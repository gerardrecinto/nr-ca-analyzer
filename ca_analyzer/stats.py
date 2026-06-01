from __future__ import annotations
from dataclasses import dataclass, field
from .classifier import CAEvent


@dataclass(slots=True)
class CAStats:
    total_seconds: float = 0.0
    cc_duration: dict[int, float] = field(default_factory=dict)
    band_combos: dict[str, float] = field(default_factory=dict)
    peak_cc: int = 0
    peak_throughput_mbps: int = 0
    rlf_count: int = 0
    throughput_samples: list[int] = field(default_factory=list)

    def cc_pct(self, cc: int) -> float:
        if self.total_seconds == 0:
            return 0.0
        return self.cc_duration.get(cc, 0.0) / self.total_seconds * 100


def _ts_to_sec(ts: str) -> float:
    h, m, rest = ts.split(':')
    s, ms = rest.split('.')
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def compute_stats(events: list[CAEvent]) -> CAStats:
    stats = CAStats()
    prev_ts: float | None = None
    prev_cc: int = 0
    prev_bands: str = ''

    for event in events:
        ts = _ts_to_sec(event.timestamp)

        if prev_ts is not None:
            delta = ts - prev_ts
            stats.total_seconds += delta
            stats.cc_duration[prev_cc] = stats.cc_duration.get(prev_cc, 0.0) + delta
            if prev_bands:
                stats.band_combos[prev_bands] = (
                    stats.band_combos.get(prev_bands, 0.0) + delta
                )

        prev_ts = ts
        prev_cc = event.cc_count

        parts: list[str] = []
        if event.pcell:
            parts.append(event.pcell.band)
        for sc in event.scells:
            parts.append(sc.band)
        prev_bands = '+'.join(parts)

        if event.kind == 'RLF':
            stats.rlf_count += 1
        if event.throughput_mbps > stats.peak_throughput_mbps:
            stats.peak_throughput_mbps = event.throughput_mbps
        if event.kind == 'THROUGHPUT':
            stats.throughput_samples.append(event.throughput_mbps)
        if event.cc_count > stats.peak_cc:
            stats.peak_cc = event.cc_count

    return stats
