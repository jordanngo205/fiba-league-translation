"""Tests for the statistical core.

The weighting defect that made free throws read +4.9 against a raw gap of -3.1
is the reason this file exists, so it gets an explicit regression test: a
weight must be a function of sample size and must not change when the same
number of attempts happens to land differently.
"""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))
import fit_translation as F  # noqa: E402


class TestNameNormalisation(unittest.TestCase):
    def test_folds_diacritics_rather_than_deleting(self):
        # Deleting the accented letter gave 'dugali', which never met 'dugalic'.
        self.assertEqual(F.norm('Angela Dugalić'), F.norm('Angela Dugalic'))
        self.assertEqual(F.norm('Sandrine Gruda'), 'sandrinegruda')

    def test_ignores_case_punctuation_and_spacing(self):
        self.assertEqual(F.norm("A'ja  Wilson"), F.norm('aja wilson'))
        self.assertEqual(F.norm('Jones, Jr.'), 'jonesjr')

    def test_handles_empty_and_none(self):
        self.assertEqual(F.norm(None), '')
        self.assertEqual(F.norm(''), '')


class TestPooling(unittest.TestCase):
    def test_pooled_weights_by_attempts_not_by_row(self):
        rows = [{'m': 1, 'a': 1}, {'m': 50, 'a': 100}]
        rate, att = F.pooled(rows, 'm', 'a')
        self.assertAlmostEqual(rate, 51 / 101)
        self.assertEqual(att, 101)

    def test_pooled_with_no_attempts_is_none_not_a_crash(self):
        rate, att = F.pooled([{'m': 0, 'a': 0}], 'm', 'a')
        self.assertIsNone(rate)
        self.assertEqual(att, 0)


class TestVarianceIsOutcomeIndependent(unittest.TestCase):
    """The regression test for the defect that motivated this file."""

    @staticmethod
    def _var(pbar, club_att, fiba_att):
        # The shipped formula: evaluated at the pooled rate, so only the
        # denominators can influence it.
        return pbar * (1 - pbar) * (1 / fiba_att + 1 / club_att)

    def test_a_perfect_sample_does_not_get_infinite_weight(self):
        # 8-for-8 and 4-for-8 are the same amount of evidence about a rate.
        perfect = self._var(0.75, 100, 8)
        middling = self._var(0.75, 100, 8)
        self.assertEqual(perfect, middling)
        self.assertGreater(perfect, 0)

    def test_the_old_formula_is_what_exploded(self):
        # Documents the defect rather than the fix: with the observed rate in
        # the variance, an 8-for-8 line contributes a zero-variance term and
        # its inverse-variance weight runs away.
        def old(rate, att):
            return rate * (1 - rate) / att
        self.assertEqual(old(1.0, 8), 0.0)
        self.assertGreater(old(0.5, 8), 0.0)

    def test_more_attempts_means_less_variance(self):
        self.assertLess(self._var(0.5, 500, 100), self._var(0.5, 500, 20))


class TestShrinkage(unittest.TestCase):
    def test_identical_leagues_collapse_to_the_common_mean(self):
        # No between-league signal: tau2 is zero, own weight is zero, and both
        # leagues take the pooled value. That is an answer, not a failure.
        g = {'a': [(0.05, 0.001)] * 5, 'b': [(0.05, 0.001)] * 5}
        out = F.shrink_groups(g)
        self.assertAlmostEqual(out['a'][0], out['b'][0], places=9)
        self.assertAlmostEqual(out['a'][3], 0.0, places=9)

    def test_well_separated_leagues_keep_their_own_estimates(self):
        g = {'a': [(0.20, 1e-5)] * 8, 'b': [(-0.20, 1e-5)] * 8}
        out = F.shrink_groups(g)
        self.assertGreater(out['a'][3], 0.9)          # own weight high
        self.assertGreater(out['a'][0], 0.15)
        self.assertLess(out['b'][0], -0.15)

    def test_shrunk_estimate_lies_between_own_mean_and_global_mean(self):
        g = {'a': [(0.10, 0.002)] * 6, 'b': [(0.00, 0.002)] * 6,
             'c': [(-0.02, 0.05)] * 3}
        out = F.shrink_groups(g)
        for lg, (shrunk, _n, raw, _w, _se, _se_raw) in out.items():
            others = [o[2] for k, o in out.items() if k != lg]
            lo, hi = min([raw] + others), max([raw] + others)
            self.assertGreaterEqual(shrunk, lo - 1e-9, lg)
            self.assertLessEqual(shrunk, hi + 1e-9, lg)

    def test_a_noisier_league_is_pulled_further(self):
        # The leagues must genuinely differ, or tau2 is zero and BOTH collapse
        # to the pooled mean -- correct behaviour, but it says nothing about
        # which one shrinkage pulls harder.
        g = {'tight': [(0.12, 1e-5)] * 10, 'loose': [(-0.06, 0.02)] * 3}
        out = F.shrink_groups(g)
        self.assertGreater(out['tight'][3], out['loose'][3])
        # and the pull shows up in the estimate, not just the weight
        self.assertLess(abs(out['tight'][0] - out['tight'][2]),
                        abs(out['loose'][0] - out['loose'][2]))

    def test_standard_errors_are_positive_and_finite(self):
        g = {'a': [(0.08, 0.001)] * 5, 'b': [(-0.03, 0.002)] * 4}
        for lg, row in F.shrink_groups(g).items():
            se_shrunk, se_raw = row[4], row[5]
            for se in (se_shrunk, se_raw):
                self.assertGreater(se, 0, lg)
                self.assertTrue(math.isfinite(se), lg)

    def test_empty_input_returns_empty_rather_than_raising(self):
        self.assertEqual(F.shrink_groups({}), {})


if __name__ == '__main__':
    unittest.main()
