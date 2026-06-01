from __future__ import annotations
import argparse
import sys
from pathlib import Path
from .parser import NR5GLogParser
from .classifier import CAEventClassifier
from .reporter import TerminalReporter, JSONReporter, CSVReporter, StatsReporter
from .stats import compute_stats


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog='nr-ca-analyzer',
        description='5G NR Carrier Aggregation Log Analyzer',
    )
    sub = p.add_subparsers(dest='command', required=True)

    analyze = sub.add_parser('analyze', help='Analyze a 5G NR CA log file')
    analyze.add_argument('log', type=Path, help='Path to NR5G log file')
    analyze.add_argument(
        '--format', choices=['terminal', 'json', 'csv'], default='terminal',
        help='Output format (default: terminal)',
    )
    analyze.add_argument(
        '--no-throughput', action='store_true',
        help='Hide PDSCH throughput events (terminal format only)',
    )
    analyze.add_argument(
        '--filter-kind', metavar='KIND[,KIND...]',
        help='Show only these event kinds, e.g. SCEL_ADD,RLF',
    )
    analyze.add_argument(
        '--band', metavar='BAND[,BAND...]',
        help='Show only events involving these NR bands, e.g. --band n41,n78',
    )
    analyze.add_argument(
        '--since', metavar='HH:MM:SS',
        help='Show events at or after this timestamp',
    )
    analyze.add_argument(
        '--until', metavar='HH:MM:SS',
        help='Show events at or before this timestamp',
    )

    stats_cmd = sub.add_parser('stats', help='CA efficiency breakdown for a log file')
    stats_cmd.add_argument('log', type=Path, help='Path to NR5G log file')

    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    match args.command:
        case 'analyze':
            return _cmd_analyze(args)
        case 'stats':
            return _cmd_stats(args)
        case _:
            parser.print_help()
            return 1


def _cmd_analyze(args: argparse.Namespace) -> int:
    if not args.log.exists():
        print(f"error: file not found: {args.log}", file=sys.stderr)
        return 1

    log_parser = NR5GLogParser()
    classifier = CAEventClassifier()
    events = list(classifier.classify(log_parser.parse(args.log)))

    if args.since:
        events = [e for e in events if e.timestamp >= args.since]
    if args.until:
        events = [e for e in events if e.timestamp <= args.until]

    if args.band:
        bands = {b.lower() for b in args.band.split(',')}

        def involves_band(e) -> bool:
            if e.pcell and e.pcell.band.lower() in bands:
                return True
            if any(s.band.lower() in bands for s in e.scells):
                return True
            if e.kind == 'SCEL_DEACT':
                return any(b in e.details.lower() for b in bands)
            return False

        events = [e for e in events if involves_band(e)]

    if args.filter_kind:
        kinds = set(args.filter_kind.upper().split(','))
        events = [e for e in events if e.kind in kinds]

    match args.format:
        case 'json':
            reporter = JSONReporter()
        case 'csv':
            reporter = CSVReporter()
        case _:
            reporter = TerminalReporter(show_throughput=not args.no_throughput)

    reporter.report(events, classifier.state, sys.stdout)
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    if not args.log.exists():
        print(f"error: file not found: {args.log}", file=sys.stderr)
        return 1
    classifier = CAEventClassifier()
    events = list(classifier.classify(NR5GLogParser().parse(args.log)))
    StatsReporter().report(compute_stats(events), sys.stdout)
    return 0


if __name__ == '__main__':
    sys.exit(main())
