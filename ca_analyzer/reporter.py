from __future__ import annotations
import json
import sys
import csv
from typing import Iterable, Protocol, TextIO
from .classifier import CAEvent, CAState
from .stats import CAStats

_RESET  = '\033[0m'
_BOLD   = '\033[1m'
_GREEN  = '\033[92m'
_YELLOW = '\033[93m'
_RED    = '\033[91m'
_CYAN   = '\033[96m'
_DIM    = '\033[2m'

_KIND_COLOR = {
    'PCELL_ESTABLISH': _CYAN,
    'SCEL_ADD':        _GREEN,
    'SCEL_DEACT':      _YELLOW,
    'CA_STATE_CHANGE': _CYAN,
    'RLF':             _RED,
    'THROUGHPUT':      _DIM,
    'REESTABLISHMENT': _YELLOW,
}


class Reporter(Protocol):
    def report(self, events: Iterable[CAEvent], state: CAState, out: TextIO) -> None: ...


class TerminalReporter:
    def __init__(self, *, show_throughput: bool = True) -> None:
        self._show_throughput = show_throughput

    def report(
        self,
        events: Iterable[CAEvent],
        state: CAState,
        out: TextIO = sys.stdout,
    ) -> None:
        bar = '─' * 60
        print(f"{_BOLD}{bar}{_RESET}", file=out)
        print(f"{_BOLD}  nr-ca-analyzer{_RESET}", file=out)
        print(bar, file=out)

        for event in events:
            if not self._show_throughput and event.kind == 'THROUGHPUT':
                continue
            color = _KIND_COLOR.get(event.kind, '')
            tag = f"[{event.kind}]".ljust(20)
            print(
                f"  {_DIM}{event.timestamp}{_RESET}  {color}{tag}{_RESET}  {event.details}",
                file=out,
            )

        print(bar, file=out)
        print(f"  Peak CCs:         {state.peak_cc}", file=out)
        print(f"  Peak Throughput:  {state.peak_throughput} Mbps", file=out)
        print(f"  RLF count:        {state.rlf_count}", file=out)
        if state.pcell:
            print(f"  Final PCell:      {state.pcell.band} PCI={state.pcell.pci}", file=out)
        if state.scells:
            bands = ', '.join(s.band for s in state.scells)
            print(f"  Active SCells:    {bands}", file=out)
        print(bar, file=out)


class JSONReporter:
    def report(
        self,
        events: Iterable[CAEvent],
        state: CAState,
        out: TextIO = sys.stdout,
    ) -> None:
        event_list = []
        for e in events:
            event_list.append({
                'timestamp': e.timestamp,
                'kind': e.kind,
                'cc_count': e.cc_count,
                'details': e.details,
                'throughput_mbps': e.throughput_mbps,
                'rlf_reason': e.rlf_reason,
            })
        result = {
            'events': event_list,
            'summary': {
                'peak_cc': state.peak_cc,
                'peak_throughput_mbps': state.peak_throughput,
                'rlf_count': state.rlf_count,
                'final_pcell_band': state.pcell.band if state.pcell else None,
            },
        }
        json.dump(result, out, indent=2)
        print(file=out)


class CSVReporter:
    def report(
        self,
        events: Iterable[CAEvent],
        state: CAState,
        out: TextIO = sys.stdout,
    ) -> None:
        writer = csv.writer(out)
        writer.writerow(['timestamp', 'kind', 'cc_count', 'throughput_mbps', 'rlf_reason', 'details'])
        for e in events:
            writer.writerow([e.timestamp, e.kind, e.cc_count, e.throughput_mbps, e.rlf_reason, e.details])


class StatsReporter:
    def report(self, stats: CAStats, out: TextIO = sys.stdout) -> None:
        bar = '-' * 40
        print(bar, file=out)
        print('CA Efficiency Report', file=out)
        print(bar, file=out)
        minutes = int(stats.total_seconds // 60)
        secs = stats.total_seconds % 60
        print(f'Duration:  {minutes}m {secs:.1f}s', file=out)
        print(file=out)
        print('CC breakdown:', file=out)
        for cc in sorted(stats.cc_duration):
            dur = stats.cc_duration[cc]
            pct = stats.cc_pct(cc)
            print(f'  {cc}CC  {dur:.1f}s  ({pct:.1f}%)', file=out)
        if stats.band_combos:
            print(file=out)
            print('Band combinations:', file=out)
            for combo, dur in sorted(stats.band_combos.items(), key=lambda x: -x[1]):
                pct = dur / stats.total_seconds * 100 if stats.total_seconds else 0.0
                print(f'  {combo:<20}  {dur:.1f}s  ({pct:.1f}%)', file=out)
        print(file=out)
        print(f'Peak CCs:        {stats.peak_cc}', file=out)
        print(f'Peak throughput: {stats.peak_throughput_mbps} Mbps', file=out)
        if stats.throughput_samples:
            avg = sum(stats.throughput_samples) // len(stats.throughput_samples)
            print(f'Avg throughput:  {avg} Mbps', file=out)
        print(f'RLF events:      {stats.rlf_count}', file=out)
        print(bar, file=out)
