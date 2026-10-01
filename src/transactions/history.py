"""Transaction history model, loading, filtering, and summaries (no GUI code)."""
from __future__ import annotations

import csv
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Iterable, List, Optional

TYPES = ('credit', 'debit')
CATEGORIES = ('Groceries', 'Dining', 'Rent', 'Utilities', 'Transport', 'Entertainment', 'Salary', 'Transfer', 'Shopping', 'Health')
SORT_KEYS = ('date', 'description', 'category', 'type', 'amount')
CSV_FIELDS = ('id', 'date', 'description', 'category', 'type', 'amount')


@dataclass(frozen=True)
class Transaction:
    id: str
    date: date
    description: str
    category: str
    type: str
    amount: Decimal  # always positive; `type` says which direction

    @property
    def signed_amount(self) -> Decimal:
        return self.amount if self.type == 'credit' else -self.amount


@dataclass
class Filter:
    text: str = ''
    start: Optional[date] = None
    end: Optional[date] = None
    categories: frozenset = field(default_factory=frozenset)  # empty = all
    type: Optional[str] = None  # None = all
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None

    def matches(self, t: Transaction) -> bool:
        needle = self.text.strip().casefold()
        return ((not needle or needle in t.description.casefold() or needle in t.id.casefold())
                and (self.start is None or t.date >= self.start)
                and (self.end is None or t.date <= self.end)
                and (not self.categories or t.category in self.categories)
                and (self.type is None or t.type == self.type)
                and (self.min_amount is None or t.amount >= self.min_amount)
                and (self.max_amount is None or t.amount <= self.max_amount))


@dataclass(frozen=True)
class Summary:
    count: int
    credits: Decimal
    debits: Decimal

    @property
    def net(self) -> Decimal:
        return self.credits - self.debits


def apply(transactions: Iterable[Transaction], flt: Filter, sort_key: str = 'date', descending: bool = True) -> List[Transaction]:
    if sort_key not in SORT_KEYS:
        raise ValueError(f'Unknown sort key: {sort_key}')
    key = (lambda t: getattr(t, sort_key).casefold()) if sort_key in ('description', 'category', 'type') else (lambda t: getattr(t, sort_key))
    # Secondary key on id keeps ordering deterministic for equal values.
    rows = sorted((t for t in transactions if flt.matches(t)), key=lambda t: t.id, reverse=descending)
    return sorted(rows, key=key, reverse=descending)


def summarize(transactions: Iterable[Transaction]) -> Summary:
    count, credits, debits = 0, Decimal('0'), Decimal('0')
    for t in transactions:
        count += 1
        if t.type == 'credit':
            credits += t.amount
        else:
            debits += t.amount
    return Summary(count, credits, debits)


def page(rows: List[Transaction], number: int, size: int) -> List[Transaction]:
    """Return 1-based page `number`; out-of-range pages are clamped."""
    if size < 1:
        raise ValueError('Page size must be positive')
    number = max(1, min(number, page_count(len(rows), size)))
    return rows[(number - 1) * size:number * size]


def page_count(total: int, size: int) -> int:
    return max(1, -(-total // size))


def parse_date(text: str) -> Optional[date]:
    """Parse YYYY-MM-DD; blank returns None, anything else raises ValueError."""
    text = text.strip()
    return date.fromisoformat(text) if text else None


def parse_amount(text: str) -> Optional[Decimal]:
    """Parse a non-negative amount like '12.50' or '$1,200'; blank returns None."""
    text = text.strip().replace('$', '').replace(',', '')
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f'Invalid amount: {text!r}') from None
    if not value.is_finite() or value < 0:
        raise ValueError(f'Invalid amount: {text!r}')
    return value


def load_csv(path) -> List[Transaction]:
    """Load transactions from a CSV with columns id,date,description,category,type,amount."""
    with open(path, newline='', encoding='utf-8') as handle:
        reader = csv.DictReader(handle)
        missing = set(CSV_FIELDS) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f'CSV is missing columns: {", ".join(sorted(missing))}')
        rows = []
        for line, row in enumerate(reader, start=2):
            try:
                kind = row['type'].strip().lower()
                if kind not in TYPES:
                    raise ValueError(f'type must be credit or debit, got {row["type"]!r}')
                amount = parse_amount(row['amount'])
                if amount is None:
                    raise ValueError('amount is required')
                rows.append(Transaction(row['id'].strip(), date.fromisoformat(row['date'].strip()),
                                        row['description'].strip(), row['category'].strip(), kind, amount))
            except ValueError as error:
                raise ValueError(f'Line {line}: {error}') from None
        return rows


def save_csv(path, transactions: Iterable[Transaction]) -> None:
    with open(path, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_FIELDS)
        for t in transactions:
            writer.writerow([t.id, t.date.isoformat(), t.description, t.category, t.type, f'{t.amount:.2f}'])


def sample_transactions(count: int = 250, seed: int = 7, today: Optional[date] = None) -> List[Transaction]:
    """Deterministic demo data spanning roughly the last six months."""
    rng = random.Random(seed)
    today = today or date.today()
    merchants = {
        'Groceries': ['Kroger', 'Trader Joe\'s', 'Whole Foods'], 'Dining': ['Chipotle', 'Starbucks', 'Local Diner'],
        'Rent': ['Monthly rent'], 'Utilities': ['Electric bill', 'Internet', 'Water bill'],
        'Transport': ['Uber', 'Gas station', 'Transit pass'], 'Entertainment': ['Spotify', 'Movie theater', 'Steam'],
        'Salary': ['Payroll deposit'], 'Transfer': ['Venmo from friend', 'Zelle transfer'],
        'Shopping': ['Amazon', 'Target', 'Best Buy'], 'Health': ['Pharmacy', 'Gym membership'],
    }
    ranges = {'Rent': (900, 1400), 'Salary': (1200, 2500), 'Utilities': (30, 150), 'Transfer': (10, 300), 'Shopping': (15, 400)}
    rows = []
    for i in range(count):
        category = rng.choice(CATEGORIES)
        low, high = ranges.get(category, (3, 120))
        kind = 'credit' if category in ('Salary', 'Transfer') and (category == 'Salary' or rng.random() < 0.5) else 'debit'
        rows.append(Transaction(f'TX{i + 1:05d}', today - timedelta(days=rng.randint(0, 180)), rng.choice(merchants[category]),
                                category, kind, Decimal(str(round(rng.uniform(low, high), 2))).quantize(Decimal('0.01'))))
    return rows
