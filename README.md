# nr-ca-analyzer

> From raw 5G NR field logs to carrier aggregation timeline in under a second.

Python 3.11+ CLI for parsing and classifying 5G NR Carrier Aggregation events from field test logs. Rule-based classifier with 8 compiled NR5G regex patterns, streaming generator-based parser, stateful CA tracker, and three output reporters. Built as a hands-on study companion for the Qualcomm Academy 5G NR CA Log Analysis Workshop (June 2, 2026).

![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)
![Tests](https://img.shields.io/badge/Tests-20%20passed-brightgreen)
![License](https://img.shields.io/badge/License-MIT-lightgrey)
![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux-lightgrey)

---

## What it looks like in practice

Terminal output (default):

```
$ nr-ca-analyzer analyze fixtures/sample_events.log

────────────────────────────────────────────────────────────
  nr-ca-analyzer
────────────────────────────────────────────────────────────
  09:15:30.001  [PCELL_ESTABLISH]     PCell established: n77 PCI=456 RSRP=-82 dBm
  09:15:33.412  [SCEL_ADD]            SCell added: n41 PCI=127 RSRP=-91 dBm → 2CC active
  09:15:33.415  [CA_STATE_CHANGE]     CA state UP: 1CC → 2CC
  09:15:40.334  [THROUGHPUT]          DL CC[PCell-n77]=450Mbps  CC[SCell0-n41]=280Mbps  total=730Mbps
  09:16:12.556  [SCEL_DEACT]         SCell deactivated: n41 PCI=127 RSRP=-105 dBm reason=LOW_RSRP
  09:16:45.889  [SCEL_ADD]            SCell added: n78 PCI=789 RSRP=-84 dBm → 2CC active
  09:17:45.001  [SCEL_ADD]            SCell added: n41 PCI=127 RSRP=-88 dBm → 3CC active
  09:17:45.004  [CA_STATE_CHANGE]     CA state UP: 2CC → 3CC
  09:18:10.556  [THROUGHPUT]          DL CC[PCell-n77]=380Mbps  CC[SCell0-n78]=410Mbps  CC[SCell1-n41]=270Mbps  total=1060Mbps
────────────────────────────────────────────────────────────
  Peak CCs:         3
  Peak Throughput:  1060 Mbps
  RLF count:        0
  Final PCell:      n77 PCI=456
  Active SCells:    n78, n41
────────────────────────────────────────────────────────────
```

RLF scenario with JSON output:

```
$ nr-ca-analyzer analyze fixtures/sample_rlf.log --format json
```

```json
{
  "events": [
    { "timestamp": "09:20:26.445", "kind": "SCEL_DEACT", "details": "SCell deactivated: n78 PCI=789 RSRP=-118 dBm reason=WEAK_SIGNAL" },
    { "timestamp": "09:20:26.448", "kind": "SCEL_DEACT", "details": "SCell deactivated: n41 PCI=127 RSRP=-121 dBm reason=WEAK_SIGNAL" },
    { "timestamp": "09:20:27.003", "kind": "RLF",        "details": "RLF on n77 PCI=456 reason=T310_EXPIRY cause=BEAM_FAILURE", "rlf_reason": "T310_EXPIRY" }
  ],
  "summary": {
    "peak_cc": 3,
    "peak_throughput_mbps": 780,
    "rlf_count": 1,
    "final_pcell_band": "n77"
  }
}
```

---

## Architecture

> Open `docs/architecture.drawio` in [diagrams.net](https://diagrams.net) for the interactive diagram.

```
5G NR field log (QCAT / modem debug / custom)
            │
            ▼
┌─────────────────────────────────────────────────────────┐
│                    nr-ca-analyzer                        │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │           NR5GLogParser  (LogParser Protocol)     │   │
│  │  8 compiled NR5G regex patterns                  │   │
│  │  Streaming line-by-line via generator            │   │
│  │  LogEntry: timestamp · subsystem · event_type    │   │
│  └────────────────────┬─────────────────────────────┘   │
│                       │ Iterator[LogEntry]               │
│                       ▼                                  │
│  ┌──────────────────────────────────────────────────┐   │
│  │         CAEventClassifier                        │   │
│  │  match/case dispatch across 8 event kinds        │   │
│  │  CAState: pcell · scells · peak_cc · rlf_count   │   │
│  │  CAEvent: frozen dataclass per classified event  │   │
│  └────────────────────┬─────────────────────────────┘   │
│                       │ Iterator[CAEvent]                │
│                       ▼                                  │
│  ┌──────────────────────────────────────────────────┐   │
│  │           Reporter  (Protocol)                   │   │
│  │  TerminalReporter  — ANSI color, summary footer  │   │
│  │  JSONReporter      — events + summary dict       │   │
│  │  CSVReporter       — spreadsheet-friendly rows   │   │
│  └────────────────────┬─────────────────────────────┘   │
│                       │                                  │
│         ┌─────────────┼─────────┬────────┐           │
│         ▼             ▼          ▼                    │
│      Terminal        JSON        CSV                     │
│      (ANSI)       (stdout)   (file / pipe)               │
└─────────────────────────────────────────────────────────┘
```

---

## Event Types

| Kind | Trigger | Key Fields |
|---|---|---|
| `PCELL_ESTABLISH` | PCell connection established | band, pci, arfcn, rsrp, rsrq |
| `SCEL_ADD` | MAC CE SCell add command | band, pci, arfcn, rsrp, rsrq |
| `SCEL_DEACT` | MAC CE SCell deactivation | band, pci, reason, rsrp |
| `CA_STATE_CHANGE` | CA bitmask CC count changes | old_mask, new_mask, cc_count delta |
| `MEAS_REPORT` | RRC A3/B1 measurement report | event, serving_rsrp, neighbor_rsrp, band |
| `RLF` | Radio Link Failure (T310 expiry) | cell, pci, reason, rlf_cause |
| `THROUGHPUT` | PHY PDSCH throughput sample | per-CC Mbps, total Mbps |
| `REESTABLISHMENT` | RRC reestablishment attempt | target_cell, pci, arfcn |

---

## Log Format

The parser expects newline-delimited text in this structure (QCAT-compatible):

```
[HH:MM:SS.mmm] [NR5G-SUBSYS] <event text>
```

| Subsystem tag | Source layer |
|---|---|
| `NR5G-RRC` | Radio Resource Control (connection, measurement, RLF) |
| `NR5G-MAC` | Medium Access Control (SCell add/deact, CA state bitmap) |
| `NR5G-PHY` | Physical layer (PDSCH throughput, SINR samples) |

See `fixtures/` for annotated sample logs covering a normal CA ramp-up and an RLF scenario.

---

## Python 3.11+ Concepts Demonstrated

**`@dataclass(slots=True, frozen=True)` for immutable value objects**
- `CellRecord` — PCI, ARFCN, RSRP, RSRQ per cell; hashable, used in `tuple[CellRecord, ...]` snapshots on `CAEvent`
- `CAEvent` — per-event immutable record; `scells: tuple[CellRecord, ...]` guarantees no mutation after classification

**`@dataclass(slots=True)` for mutable running state**
- `CAState` — tracks live pcell, scells list, peak_cc, peak_throughput, rlf_count across the log stream; `slots=True` reduces overhead on large logs

**`match/case` for event dispatch**
- `CAEventClassifier._dispatch()` — matches on `event_type` string; each arm calls a dedicated `_handle_*` method; `case _: return None` for unknown events without an elif chain

**Module-level compiled `re.Pattern` constants**
- 8 patterns compiled once at import time in `parser.py`; avoids per-line regex compilation on multi-MB field logs

**`Protocol` for structural subtyping**
- `LogParser` — any class with `parse(path: Path) -> Iterator[LogEntry]` satisfies it without inheritance
- `Reporter` — `TerminalReporter`, `JSONReporter`, `CSVReporter` are structurally compatible; no shared base class

**Generator-based streaming**
- `NR5GLogParser.parse()` yields `LogEntry` objects one at a time; classifier consumes the iterator without loading the full log into memory

**`from __future__ import annotations`**
- All modules use deferred annotation evaluation; enables `CellRecord | None` and `tuple[CellRecord, ...]` syntax cleanly on Python 3.11

---

## Jenkinsfile

```groovy
pipeline {
    agent { label 'python311' }

    options {
        timestamps()
        timeout(time: 10, unit: 'MINUTES')
    }

    environment {
        PYTHONDONTWRITEBYTECODE = '1'
        PYTHONUNBUFFERED = '1'
    }

    stages {
        stage('Validate') {
            steps {
                sh 'python -m py_compile ca_analyzer/*.py tests/*.py'
            }
        }
        stage('Test') {
            steps {
                sh 'python -m pytest tests/ -v --tb=short --junit-xml=test-results/results.xml'
            }
            post {
                always {
                    junit 'test-results/results.xml'
                }
            }
        }
        stage('Smoke') {
            steps {
                sh '''
                    python -m ca_analyzer.cli analyze fixtures/sample_events.log
                    python -m ca_analyzer.cli analyze fixtures/sample_rlf.log --format json | python -m json.tool
                    python -m ca_analyzer.cli analyze fixtures/sample_events.log --filter-kind SCEL_ADD,RLF
                '''
            }
        }
    }
}
```

---

## Install

```bash
git clone https://github.com/gerardrecinto/nr-ca-analyzer.git
cd nr-ca-analyzer
pip install -e .
```

Or run directly without install:

```bash
python -m ca_analyzer.cli analyze fixtures/sample_events.log
```

---

## Usage

```bash
# Terminal output (default)
nr-ca-analyzer analyze path/to/nr5g.log

# JSON output
nr-ca-analyzer analyze path/to/nr5g.log --format json | jq '.summary'

# CSV output
nr-ca-analyzer analyze path/to/nr5g.log --format csv > ca_events.csv

# Hide throughput lines
nr-ca-analyzer analyze path/to/nr5g.log --no-throughput

# Filter to specific event kinds
nr-ca-analyzer analyze path/to/nr5g.log --filter-kind SCEL_ADD,SCEL_DEACT,RLF
```

---

## Tests

```bash
python -m pytest tests/ -v
python -m pytest tests/ --tb=short
```

---

## Workshop Context

Built as a study companion for the **Qualcomm Academy 5G NR Carrier Aggregation Log Analysis Workshop** (June 2, 2026 — instructed by Joakim Hulten). The fixture logs and event taxonomy mirror patterns covered in the workshop: SCell add/deact MAC CE procedures, A3/B1 measurement reports, CA state bitmap transitions, and RLF root cause classification (T310 expiry, beam failure, SCG failure).
