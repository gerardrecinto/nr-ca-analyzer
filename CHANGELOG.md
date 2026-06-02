# Changelog

## v0.1.0 - 2026-06-01

Initial public release of `nr-ca-analyzer`, a Python 3.11+ CLI for parsing and analyzing 5G NR carrier aggregation field logs.

### Added

- `nr-ca-analyzer analyze` for terminal, JSON, and CSV reporting.
- `nr-ca-analyzer stats` for CA efficiency reports.
- Streaming NR5G log parser with compiled regex patterns for RRC, MAC, and PHY events.
- Stateful CA event classifier for PCell, SCell, CA state, throughput, RLF, measurement, and reestablishment events.
- Sample CA ramp-up and RLF fixture logs.
- Jenkins validation pipeline.
- 25 pytest tests covering parser, classifier, reporter, CLI, and stats behavior.
