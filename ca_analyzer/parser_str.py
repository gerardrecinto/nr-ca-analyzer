from __future__ import annotations
from typing import Any, Iterator
from pathlib import Path
from .parser import LogEntry


def _extract_ts(line: str) -> str | None:
    if not line.startswith('['):
        return None
    end = line.find(']')
    if end == -1:
        return None
    return line[1:end]


def _extract_subsys(line: str) -> str | None:
    start = line.find('[NR5G-')
    if start == -1:
        return None
    end = line.find(']', start)
    if end == -1:
        return None
    return line[start + 1:end]


def _kv(line: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for token in line.split():
        if '=' in token:
            k, _, v = token.partition('=')
            out[k] = v
    return out


def _classify_str(line: str) -> tuple[str, dict[str, Any]] | None:
    if 'SCell ADD:' in line:
        kv = _kv(line)
        return 'SCEL_ADD', {
            'band': kv['band'], 'pci': int(kv['pci']),
            'arfcn': int(kv['arfcn']), 'rsrp': int(kv['rsrp']),
            'rsrq': int(kv['rsrq']),
        }

    if 'SCell DEACT:' in line:
        kv = _kv(line)
        fields: dict[str, Any] = {
            'band': kv['band'], 'pci': int(kv['pci']),
            'arfcn': int(kv['arfcn']), 'reason': kv['reason'],
        }
        if 'rsrp' in kv:
            fields['rsrp'] = int(kv['rsrp'])
        return 'SCEL_DEACT', fields

    if 'SCell ACT:' in line:
        kv = _kv(line)
        return 'SCEL_ACT', {
            'band': kv['band'], 'pci': int(kv['pci']), 'arfcn': int(kv['arfcn']),
        }

    if 'CA State:' in line:
        idx = line.index('CA State:')
        rest = line[idx + len('CA State:'):].strip()
        parts = rest.split()
        old = int(parts[0], 16)
        new = int(parts[2], 16)
        return 'CA_STATE', {
            'old_mask': old, 'new_mask': new,
            'old_cc_count': bin(old).count('1'),
            'new_cc_count': bin(new).count('1'),
        }

    if 'PCell ESTABLISH:' in line:
        kv = _kv(line)
        return 'PCELL_ESTABLISH', {
            'band': kv['band'], 'pci': int(kv['pci']),
            'arfcn': int(kv['arfcn']), 'rsrp': int(kv['rsrp']),
            'rsrq': int(kv['rsrq']),
        }

    if 'MeasReport' in line:
        kv = _kv(line)
        mr_start = line.index('MeasReport')
        event_code = line[mr_start:].split()[1].rstrip(':')
        return 'MEAS_REPORT', {
            'event': event_code,
            'serving_rsrp': int(kv['serving_rsrp']),
            'neighbor_rsrp': int(kv['neighbor_rsrp']),
            'band': kv['band'], 'pci': int(kv['pci']), 'arfcn': int(kv['arfcn']),
        }

    if 'RLF:' in line:
        kv = _kv(line)
        fields = {
            'cell': kv['cell'], 'pci': int(kv['pci']),
            'arfcn': int(kv['arfcn']), 'reason': kv['reason'],
        }
        if 'rlf_cause' in kv:
            fields['rlf_cause'] = kv['rlf_cause']
        return 'RLF', fields

    if 'PDSCH Throughput:' in line:
        kv = _kv(line)
        ccs: dict[str, int] = {}
        remaining = line
        while 'CC[' in remaining:
            s = remaining.index('CC[')
            e = remaining.index(']', s)
            name = remaining[s + 3:e]
            eq = remaining.index('=', e)
            sp = remaining.find(' ', eq)
            val = remaining[eq + 1:sp] if sp != -1 else remaining[eq + 1:]
            ccs[name] = int(val)
            remaining = remaining[sp:] if sp != -1 else ''
        return 'PDSCH_THROUGHPUT', {'ccs': ccs, 'total_mbps': int(kv['total'])}

    if 'Reestablishment:' in line:
        kv = _kv(line)
        return 'REESTABLISHMENT', {
            'target_cell': kv['target_cell'], 'pci': int(kv['pci']),
            'arfcn': int(kv['arfcn']),
        }

    return None


class NR5GStrParser:
    """LogParser using str.split/find/partition/index instead of regex."""

    def parse(self, path: Path) -> Iterator[LogEntry]:
        with path.open() as fh:
            for line in fh:
                line = line.rstrip()
                if not line or line.startswith('#'):
                    continue
                ts = _extract_ts(line)
                subsys = _extract_subsys(line)
                if ts is None or subsys is None:
                    continue
                result = _classify_str(line)
                if result is None:
                    continue
                event_type, fields = result
                yield LogEntry(
                    timestamp=ts,
                    subsystem=subsys,
                    event_type=event_type,
                    raw=line,
                    fields=fields,
                )
