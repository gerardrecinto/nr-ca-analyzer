import pytest
from pathlib import Path
from ca_analyzer.parser import NR5GLogParser
from ca_analyzer.classifier import CAEventClassifier
from ca_analyzer.stats import compute_stats

FIXTURES = Path(__file__).parent.parent / 'fixtures'


class TestNR5GLogParser:
    def setup_method(self):
        self.parser = NR5GLogParser()

    def test_parse_pcell_establish(self):
        entries = list(self.parser.parse(FIXTURES / 'sample_events.log'))
        pcell = next(e for e in entries if e.event_type == 'PCELL_ESTABLISH')
        assert pcell.fields['band'] == 'n77'
        assert pcell.fields['pci'] == 456
        assert pcell.fields['rsrp'] == -82

    def test_parse_scel_add(self):
        entries = list(self.parser.parse(FIXTURES / 'sample_events.log'))
        adds = [e for e in entries if e.event_type == 'SCEL_ADD']
        assert len(adds) == 3
        assert adds[0].fields['band'] == 'n41'
        assert adds[0].fields['arfcn'] == 523020

    def test_parse_scel_deact(self):
        entries = list(self.parser.parse(FIXTURES / 'sample_events.log'))
        deacts = [e for e in entries if e.event_type == 'SCEL_DEACT']
        assert len(deacts) == 1
        assert deacts[0].fields['reason'] == 'LOW_RSRP'
        assert deacts[0].fields['rsrp'] == -105

    def test_parse_ca_state_transitions(self):
        entries = list(self.parser.parse(FIXTURES / 'sample_events.log'))
        states = [e for e in entries if e.event_type == 'CA_STATE']
        assert len(states) >= 4
        masks = [(e.fields['old_mask'], e.fields['new_mask']) for e in states]
        assert (0x01, 0x03) in masks
        assert (0x03, 0x07) in masks

    def test_parse_throughput(self):
        entries = list(self.parser.parse(FIXTURES / 'sample_events.log'))
        tput = [e for e in entries if e.event_type == 'PDSCH_THROUGHPUT']
        assert len(tput) == 3
        assert tput[2].fields['total_mbps'] == 1060

    def test_parse_meas_report(self):
        entries = list(self.parser.parse(FIXTURES / 'sample_events.log'))
        meas = [e for e in entries if e.event_type == 'MEAS_REPORT']
        assert len(meas) == 1
        assert meas[0].fields['event'] == 'A3'
        assert meas[0].fields['neighbor_rsrp'] == -84

    def test_parse_rlf(self):
        entries = list(self.parser.parse(FIXTURES / 'sample_rlf.log'))
        rlf = [e for e in entries if e.event_type == 'RLF']
        assert len(rlf) == 1
        assert rlf[0].fields['reason'] == 'T310_EXPIRY'
        assert rlf[0].fields['rlf_cause'] == 'BEAM_FAILURE'

    def test_skips_comments_and_blank_lines(self):
        entries = list(self.parser.parse(FIXTURES / 'sample_events.log'))
        assert all(e.raw.startswith('[') for e in entries)

    def test_ts_seconds_conversion(self):
        entries = list(self.parser.parse(FIXTURES / 'sample_events.log'))
        expected = 9 * 3600 + 15 * 60 + 30.001
        assert entries[0].ts_seconds == pytest.approx(expected)

    def test_subsystem_parsed(self):
        entries = list(self.parser.parse(FIXTURES / 'sample_events.log'))
        subsystems = {e.subsystem for e in entries}
        assert 'NR5G-MAC' in subsystems
        assert 'NR5G-RRC' in subsystems
        assert 'NR5G-PHY' in subsystems


class TestCAEventClassifier:
    def _classify_file(self, filename: str):
        parser = NR5GLogParser()
        classifier = CAEventClassifier()
        entries = parser.parse(FIXTURES / filename)
        events = list(classifier.classify(entries))
        return events, classifier.state

    def test_peak_cc_reached_3(self):
        _, state = self._classify_file('sample_events.log')
        assert state.peak_cc == 3

    def test_peak_throughput(self):
        _, state = self._classify_file('sample_events.log')
        assert state.peak_throughput == 1060

    def test_rlf_increments_count(self):
        _, state = self._classify_file('sample_rlf.log')
        assert state.rlf_count == 1

    def test_rlf_clears_scells(self):
        events, _ = self._classify_file('sample_rlf.log')
        rlf_events = [e for e in events if e.kind == 'RLF']
        assert len(rlf_events) == 1
        assert rlf_events[0].scells == ()

    def test_scel_add_updates_state(self):
        events, _ = self._classify_file('sample_events.log')
        adds = [e for e in events if e.kind == 'SCEL_ADD']
        assert len(adds) == 3

    def test_scel_deact_removes_from_state(self):
        events, _ = self._classify_file('sample_events.log')
        deacts = [e for e in events if e.kind == 'SCEL_DEACT']
        assert len(deacts) == 1
        assert 'LOW_RSRP' in deacts[0].details

    def test_ca_state_change_all_cc_count_positive(self):
        events, _ = self._classify_file('sample_events.log')
        state_changes = [e for e in events if e.kind == 'CA_STATE_CHANGE']
        assert len(state_changes) >= 3
        assert all(e.cc_count > 0 for e in state_changes)

    def test_pcell_establish_sets_state(self):
        events, state = self._classify_file('sample_events.log')
        pcell_events = [e for e in events if e.kind == 'PCELL_ESTABLISH']
        assert len(pcell_events) >= 1
        assert state.pcell is not None
        assert state.pcell.band == 'n77'

    def test_throughput_events_classified(self):
        events, _ = self._classify_file('sample_events.log')
        tput = [e for e in events if e.kind == 'THROUGHPUT']
        assert len(tput) == 3
        assert tput[2].throughput_mbps == 1060

    def test_rlf_reason_captured(self):
        events, _ = self._classify_file('sample_rlf.log')
        rlf = [e for e in events if e.kind == 'RLF']
        assert rlf[0].rlf_reason == 'T310_EXPIRY'


class TestCAStats:
    def _stats(self, filename: str):
        parser = NR5GLogParser()
        classifier = CAEventClassifier()
        events = list(classifier.classify(parser.parse(FIXTURES / filename)))
        return compute_stats(events)

    def test_peak_cc(self):
        stats = self._stats('sample_events.log')
        assert stats.peak_cc == 3

    def test_peak_throughput(self):
        stats = self._stats('sample_events.log')
        assert stats.peak_throughput_mbps == 1060

    def test_rlf_count(self):
        stats = self._stats('sample_rlf.log')
        assert stats.rlf_count == 1

    def test_band_combos_include_n77(self):
        stats = self._stats('sample_events.log')
        assert any('n77' in combo for combo in stats.band_combos)

    def test_3cc_duration_positive(self):
        stats = self._stats('sample_events.log')
        assert 3 in stats.cc_duration
        assert stats.cc_duration[3] > 0
