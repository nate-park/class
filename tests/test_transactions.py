import os
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from src.transactions import history
from src.transactions.history import Filter, Transaction


def tx(id, day, desc, category, kind, amount):
    return Transaction(id, date(2026, 9, day), desc, category, kind, Decimal(amount))


ROWS = [
    tx('TX1', 1, 'Payroll deposit', 'Salary', 'credit', '2000.00'),
    tx('TX2', 3, 'Kroger', 'Groceries', 'debit', '54.20'),
    tx('TX3', 3, 'Starbucks', 'Dining', 'debit', '6.75'),
    tx('TX4', 10, 'Monthly rent', 'Rent', 'debit', '1100.00'),
    tx('TX5', 15, 'Venmo from friend', 'Transfer', 'credit', '25.00'),
]


class FilterTests(unittest.TestCase):
    def ids(self, flt, **kwargs):
        return [t.id for t in history.apply(ROWS, flt, **kwargs)]

    def test_empty_filter_returns_all_newest_first(self):
        self.assertEqual(self.ids(Filter()), ['TX5', 'TX4', 'TX3', 'TX2', 'TX1'])

    def test_text_search_is_case_insensitive_and_matches_id(self):
        self.assertEqual(self.ids(Filter(text='  KROGER ')), ['TX2'])
        self.assertEqual(self.ids(Filter(text='tx4')), ['TX4'])

    def test_date_range_is_inclusive(self):
        self.assertEqual(self.ids(Filter(start=date(2026, 9, 3), end=date(2026, 9, 10))), ['TX4', 'TX3', 'TX2'])

    def test_categories_type_and_amount(self):
        self.assertEqual(self.ids(Filter(categories=frozenset({'Dining', 'Rent'}))), ['TX4', 'TX3'])
        self.assertEqual(self.ids(Filter(type='credit')), ['TX5', 'TX1'])
        self.assertEqual(self.ids(Filter(min_amount=Decimal('25'), max_amount=Decimal('1100'))), ['TX5', 'TX4', 'TX2'])

    def test_combined_filters_and_no_matches(self):
        self.assertEqual(self.ids(Filter(type='debit', max_amount=Decimal('60'), text='kro')), ['TX2'])
        self.assertEqual(self.ids(Filter(text='nothing matches')), [])

    def test_sorting(self):
        self.assertEqual(self.ids(Filter(), sort_key='amount', descending=False), ['TX3', 'TX5', 'TX2', 'TX4', 'TX1'])
        self.assertEqual(self.ids(Filter(), sort_key='description', descending=False), ['TX2', 'TX4', 'TX1', 'TX3', 'TX5'])
        with self.assertRaises(ValueError):
            history.apply(ROWS, Filter(), sort_key='bogus')

    def test_summary(self):
        s = history.summarize(ROWS)
        self.assertEqual((s.count, s.credits, s.debits, s.net), (5, Decimal('2025.00'), Decimal('1160.95'), Decimal('864.05')))
        self.assertEqual(history.summarize([]).net, 0)


class PagingAndParsingTests(unittest.TestCase):
    def test_paging_clamps(self):
        rows = list(range(7))
        self.assertEqual(history.page_count(7, 3), 3)
        self.assertEqual(history.page_count(0, 3), 1)
        self.assertEqual(history.page(rows, 3, 3), [6])
        self.assertEqual(history.page(rows, 99, 3), [6])
        self.assertEqual(history.page(rows, 0, 3), [0, 1, 2])
        with self.assertRaises(ValueError):
            history.page(rows, 1, 0)

    def test_parse_inputs(self):
        self.assertIsNone(history.parse_date('  '))
        self.assertEqual(history.parse_date('2026-09-01'), date(2026, 9, 1))
        self.assertEqual(history.parse_amount('$1,200.50'), Decimal('1200.50'))
        self.assertIsNone(history.parse_amount(''))
        for bad in ['9/1/2026', '2026-13-01']:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                history.parse_date(bad)
        for bad in ['abc', '-5', 'NaN', 'Infinity']:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                history.parse_amount(bad)


class CsvTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix='.csv')
        os.close(handle)
        self.addCleanup(os.remove, self.path)

    def write(self, text):
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write(text)

    def test_round_trip(self):
        history.save_csv(self.path, ROWS)
        self.assertEqual(history.load_csv(self.path), ROWS)

    def test_bad_csv_reports_line(self):
        self.write('id,date,description\nTX1,2026-09-01,x\n')
        with self.assertRaisesRegex(ValueError, 'missing columns'):
            history.load_csv(self.path)
        self.write('id,date,description,category,type,amount\nTX1,2026-09-01,x,Dining,refund,5\n')
        with self.assertRaisesRegex(ValueError, 'Line 2'):
            history.load_csv(self.path)

    def test_sample_data_is_deterministic_and_valid(self):
        a = history.sample_transactions(today=date(2026, 10, 1))
        self.assertEqual(a, history.sample_transactions(today=date(2026, 10, 1)))
        self.assertEqual(len({t.id for t in a}), len(a))
        self.assertTrue(all(t.amount > 0 and t.type in history.TYPES for t in a))


if __name__ == '__main__':
    unittest.main()
