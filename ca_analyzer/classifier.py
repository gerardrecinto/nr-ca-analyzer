from __future__ import annotations
from dataclasses import dataclass, field
from typing import Iterator
from .parser import LogEntry


@dataclass(slots=True, frozen=True)
class CellRecord:
    band: str
    pci: int
    arfcn: int
    rsrp: int = 0
    rsrq: int = 0


@dataclass(slots=True, frozen=True)
class CAEvent:
    timestamp: str
    kind: str
    pcell: CellRecord | None
    scells: tuple[CellRecord, ...]
    cc_count: int
    details: str
    throughput_mbps: int = 0
    rlf_reason: str = ''


@dataclass(slots=True)
class CAState:
    pcell: CellRecord | None = None
    scells: list[CellRecord] = field(default_factory=list)
    peak_cc: int = 0
    peak_throughput: int = 0
    rlf_count: int = 0

    @property
    def cc_count(self) -> int:
        return (1 if self.pcell else 0) + len(self.scells)

    def snapshot_scells(self) -> tuple[CellRecord, ...]:
        return tuple(self.scells)


class CAEventClassifier:
    """Stateful classifier: consumes LogEntry stream, emits CAEvent stream."""

    def __init__(self) -> None:
        self._state = CAState()

    @property
    def state(self) -> CAState:
        return self._state

    def classify(self, entries: Iterator[LogEntry]) -> Iterator[CAEvent]:
        for entry in entries:
            event = self._dispatch(entry)
            if event is not None:
                yield event

    def _dispatch(self, e: LogEntry) -> CAEvent | None:
        match e.event_type:
            case 'PCELL_ESTABLISH':
                return self._handle_pcell(e)
            case 'SCEL_ADD':
                return self._handle_scel_add(e)
            case 'SCEL_DEACT':
                return self._handle_scel_deact(e)
            case 'CA_STATE':
                return self._handle_ca_state(e)
            case 'RLF':
                return self._handle_rlf(e)
            case 'PDSCH_THROUGHPUT':
                return self._handle_throughput(e)
            case 'MEAS_REPORT':
                return self._handle_meas_report(e)
            case 'REESTABLISHMENT':
                return self._handle_reestablishment(e)
            case _:
                return None

    def _handle_pcell(self, e: LogEntry) -> CAEvent:
        f = e.fields
        cell = CellRecord(f['band'], f['pci'], f['arfcn'], f['rsrp'], f['rsrq'])
        self._state.pcell = cell
        self._state.scells.clear()
        return CAEvent(
            timestamp=e.timestamp,
            kind='PCELL_ESTABLISH',
            pcell=cell,
            scells=(),
            cc_count=1,
            details=f"PCell established: {f['band']} PCI={f['pci']} RSRP={f['rsrp']} dBm",
        )

    def _handle_scel_add(self, e: LogEntry) -> CAEvent:
        f = e.fields
        cell = CellRecord(f['band'], f['pci'], f['arfcn'], f['rsrp'], f['rsrq'])
        if not any(s.pci == cell.pci for s in self._state.scells):
            self._state.scells.append(cell)
        cc = self._state.cc_count
        if cc > self._state.peak_cc:
            self._state.peak_cc = cc
        return CAEvent(
            timestamp=e.timestamp,
            kind='SCEL_ADD',
            pcell=self._state.pcell,
            scells=self._state.snapshot_scells(),
            cc_count=cc,
            details=(
                f"SCell added: {f['band']} PCI={f['pci']} RSRP={f['rsrp']} dBm"
                f" → {cc}CC active"
            ),
        )

    def _handle_scel_deact(self, e: LogEntry) -> CAEvent:
        f = e.fields
        pci = f['pci']
        self._state.scells = [s for s in self._state.scells if s.pci != pci]
        rsrp_str = f" RSRP={f['rsrp']} dBm" if 'rsrp' in f else ''
        return CAEvent(
            timestamp=e.timestamp,
            kind='SCEL_DEACT',
            pcell=self._state.pcell,
            scells=self._state.snapshot_scells(),
            cc_count=self._state.cc_count,
            details=(
                f"SCell deactivated: {f['band']} PCI={pci}{rsrp_str}"
                f" reason={f['reason']}"
            ),
        )

    def _handle_ca_state(self, e: LogEntry) -> CAEvent | None:
        f = e.fields
        if f['old_cc_count'] == f['new_cc_count']:
            return None
        direction = 'UP' if f['new_cc_count'] > f['old_cc_count'] else 'DOWN'
        return CAEvent(
            timestamp=e.timestamp,
            kind='CA_STATE_CHANGE',
            pcell=self._state.pcell,
            scells=self._state.snapshot_scells(),
            cc_count=f['new_cc_count'],
            details=(
                f"CA state {direction}: "
                f"{f['old_cc_count']}CC → {f['new_cc_count']}CC"
            ),
        )

    def _handle_rlf(self, e: LogEntry) -> CAEvent:
        f = e.fields
        self._state.rlf_count += 1
        self._state.scells.clear()
        cause = f.get('rlf_cause', '')
        return CAEvent(
            timestamp=e.timestamp,
            kind='RLF',
            pcell=self._state.pcell,
            scells=(),
            cc_count=0,
            details=(
                f"RLF on {f['cell']} PCI={f['pci']} reason={f['reason']}"
                + (f" cause={cause}" if cause else '')
            ),
            rlf_reason=f['reason'],
        )

    def _handle_meas_report(self, e: LogEntry) -> CAEvent:
        f = e.fields
        return CAEvent(
            timestamp=e.timestamp,
            kind='MEAS_REPORT',
            pcell=self._state.pcell,
            scells=self._state.snapshot_scells(),
            cc_count=self._state.cc_count,
            details=(
                f"MeasReport {f['event']}: serving={f['serving_rsrp']} dBm"
                f" neighbor={f['neighbor_rsrp']} dBm ({f['band']} PCI={f['pci']})"
            ),
        )

    def _handle_reestablishment(self, e: LogEntry) -> CAEvent:
        f = e.fields
        return CAEvent(
            timestamp=e.timestamp,
            kind='REESTABLISHMENT',
            pcell=self._state.pcell,
            scells=self._state.snapshot_scells(),
            cc_count=self._state.cc_count,
            details=(
                f"Reestablishment attempt: target={f['target_cell']} PCI={f['pci']}"
            ),
        )

    def _handle_throughput(self, e: LogEntry) -> CAEvent:
        f = e.fields
        total = f['total_mbps']
        if total > self._state.peak_throughput:
            self._state.peak_throughput = total
        ccs: dict = f['ccs']
        cc_str = '  '.join(f"CC[{k}]={v}Mbps" for k, v in ccs.items())
        return CAEvent(
            timestamp=e.timestamp,
            kind='THROUGHPUT',
            pcell=self._state.pcell,
            scells=self._state.snapshot_scells(),
            cc_count=self._state.cc_count,
            details=f"DL {cc_str}  total={total}Mbps",
            throughput_mbps=total,
        )
