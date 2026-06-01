from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Any, Iterator, Protocol
from pathlib import Path

_TS       = re.compile(r'^\[(\d{2}:\d{2}:\d{2}\.\d{3})\]')
_SUBSYS   = re.compile(r'\[(NR5G-\w+)\]')
_SCEL_ADD = re.compile(
    r'SCell ADD: band=(\w+) pci=(\d+) arfcn=(\d+) rsrp=(-?\d+) rsrq=(-?\d+)'
)
_SCEL_DEACT = re.compile(
    r'SCell DEACT: band=(\w+) pci=(\d+) arfcn=(\d+) reason=(\w+)'
    r'(?:\s+rsrp=(-?\d+))?'
)
_SCEL_ACT = re.compile(r'SCell ACT: band=(\w+) pci=(\d+) arfcn=(\d+)')
_CA_STATE = re.compile(r'CA State: (0x[\da-f]+) -> (0x[\da-f]+)')
_PCELL    = re.compile(
    r'PCell ESTABLISH: band=(\w+) pci=(\d+) arfcn=(\d+) rsrp=(-?\d+) rsrq=(-?\d+)'
)
_MEAS     = re.compile(
    r'MeasReport (\w+): serving_rsrp=(-?\d+) neighbor_rsrp=(-?\d+)'
    r' band=(\w+) pci=(\d+) arfcn=(\d+)'
)
_RLF      = re.compile(
    r'RLF: cell=(\w+) pci=(\d+) arfcn=(\d+) reason=(\w+)'
    r'(?:\s+rlf_cause=(\w+))?'
)
_PDSCH    = re.compile(
    r'PDSCH Throughput:((?:\s+CC\[\w+-\w+\]=\d+)+)\s+total=(\d+) Mbps'
)
_REEST    = re.compile(
    r'Reestablishment: target_cell=(\w+) pci=(\d+) arfcn=(\d+)'
)


@dataclass(slots=True)
class LogEntry:
    timestamp: str
    subsystem: str
    event_type: str
    raw: str
    fields: dict[str, Any]

    @property
    def ts_seconds(self) -> float:
        h, m, rest = self.timestamp.split(':')
        s, ms = rest.split('.')
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


class LogParser(Protocol):
    def parse(self, path: Path) -> Iterator[LogEntry]: ...


def _classify_and_extract(line: str) -> tuple[str, dict[str, Any]] | None:
    if m := _SCEL_ADD.search(line):
        return 'SCEL_ADD', {
            'band': m.group(1), 'pci': int(m.group(2)),
            'arfcn': int(m.group(3)), 'rsrp': int(m.group(4)),
            'rsrq': int(m.group(5)),
        }
    if m := _SCEL_DEACT.search(line):
        fields: dict[str, Any] = {
            'band': m.group(1), 'pci': int(m.group(2)),
            'arfcn': int(m.group(3)), 'reason': m.group(4),
        }
        if m.group(5):
            fields['rsrp'] = int(m.group(5))
        return 'SCEL_DEACT', fields
    if m := _SCEL_ACT.search(line):
        return 'SCEL_ACT', {
            'band': m.group(1), 'pci': int(m.group(2)), 'arfcn': int(m.group(3)),
        }
    if m := _CA_STATE.search(line):
        old = int(m.group(1), 16)
        new = int(m.group(2), 16)
        return 'CA_STATE', {
            'old_mask': old, 'new_mask': new,
            'old_cc_count': bin(old).count('1'),
            'new_cc_count': bin(new).count('1'),
        }
    if m := _PCELL.search(line):
        return 'PCELL_ESTABLISH', {
            'band': m.group(1), 'pci': int(m.group(2)),
            'arfcn': int(m.group(3)), 'rsrp': int(m.group(4)),
            'rsrq': int(m.group(5)),
        }
    if m := _MEAS.search(line):
        return 'MEAS_REPORT', {
            'event': m.group(1), 'serving_rsrp': int(m.group(2)),
            'neighbor_rsrp': int(m.group(3)), 'band': m.group(4),
            'pci': int(m.group(5)), 'arfcn': int(m.group(6)),
        }
    if m := _RLF.search(line):
        f: dict[str, Any] = {
            'cell': m.group(1), 'pci': int(m.group(2)),
            'arfcn': int(m.group(3)), 'reason': m.group(4),
        }
        if m.group(5):
            f['rlf_cause'] = m.group(5)
        return 'RLF', f
    if m := _PDSCH.search(line):
        cc_part = m.group(1).strip()
        ccs: dict[str, int] = {}
        for cc_m in re.finditer(r'CC\[(\w+-\w+)\]=(\d+)', cc_part):
            ccs[cc_m.group(1)] = int(cc_m.group(2))
        return 'PDSCH_THROUGHPUT', {'ccs': ccs, 'total_mbps': int(m.group(2))}
    if m := _REEST.search(line):
        return 'REESTABLISHMENT', {
            'target_cell': m.group(1), 'pci': int(m.group(2)), 'arfcn': int(m.group(3)),
        }
    return None


class NR5GLogParser:
    """Parses NR5G field test logs into structured LogEntry objects."""

    def parse(self, path: Path) -> Iterator[LogEntry]:
        with path.open() as fh:
            for line in fh:
                line = line.rstrip()
                if not line or line.startswith('#'):
                    continue
                ts_m = _TS.match(line)
                sub_m = _SUBSYS.search(line)
                if not ts_m or not sub_m:
                    continue
                result = _classify_and_extract(line)
                if result is None:
                    continue
                event_type, fields = result
                yield LogEntry(
                    timestamp=ts_m.group(1),
                    subsystem=sub_m.group(1),
                    event_type=event_type,
                    raw=line,
                    fields=fields,
                )
