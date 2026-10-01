"""Tkinter GUI for browsing and filtering transaction history.

Run with sample data:   python -m src.transactions.gui
Run with your own CSV:  python -m src.transactions.gui path/to/transactions.csv
"""
from __future__ import annotations

import sys
import tkinter as tk
from datetime import date, timedelta
from tkinter import filedialog, messagebox, ttk

from src.transactions import history
from src.transactions.history import Filter

COLUMNS = (('date', 'Date', 100, 'w'), ('description', 'Description', 220, 'w'), ('category', 'Category', 120, 'w'),
           ('type', 'Type', 70, 'center'), ('amount', 'Amount', 110, 'e'))
PAGE_SIZES = ('25', '50', '100', '250')
DEBOUNCE_MS = 250


def money(value) -> str:
    return f'-${-value:,.2f}' if value < 0 else f'${value:,.2f}'


class TransactionHistoryApp(ttk.Frame):
    def __init__(self, master, transactions, source='Sample data'):
        super().__init__(master, padding=10)
        self.master = master
        self.transactions = list(transactions)
        self.source = source
        self.filtered = []
        self.sort_key, self.descending = 'date', True
        self.page_number = 1
        self._pending = None

        self.text = tk.StringVar()
        self.start = tk.StringVar()
        self.end = tk.StringVar()
        self.kind = tk.StringVar(value='All')
        self.min_amount = tk.StringVar()
        self.max_amount = tk.StringVar()
        self.page_size = tk.StringVar(value='50')
        self.status = tk.StringVar()
        self.summary = tk.StringVar()
        self.page_label = tk.StringVar()

        self._build_menu()
        self._build_filters()
        self._build_table()
        self._build_footer()
        self.grid(sticky='nsew')
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)

        for var in (self.text, self.start, self.end, self.kind, self.min_amount, self.max_amount):
            var.trace_add('write', lambda *_: self._schedule_refresh())
        self.page_size.trace_add('write', lambda *_: self._refresh(reset_page=True))
        self._load_categories()
        self._refresh()

    # ----- layout -----
    def _build_menu(self):
        menu = tk.Menu(self.master)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label='Open CSV…', command=self.open_csv, accelerator='Ctrl+O')
        file_menu.add_command(label='Export filtered CSV…', command=self.export_csv, accelerator='Ctrl+S')
        file_menu.add_command(label='Load sample data', command=lambda: self.set_transactions(history.sample_transactions(), 'Sample data'))
        file_menu.add_separator()
        file_menu.add_command(label='Quit', command=self.master.destroy)
        menu.add_cascade(label='File', menu=file_menu)
        self.master.config(menu=menu)
        self.master.bind_all('<Control-o>', lambda _: self.open_csv())
        self.master.bind_all('<Control-s>', lambda _: self.export_csv())
        self.master.bind_all('<Control-f>', lambda _: self.search_entry.focus_set())

    def _build_filters(self):
        box = ttk.LabelFrame(self, text='Filters', padding=8)
        box.grid(row=0, column=0, sticky='ew')
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text='Search').grid(row=0, column=0, sticky='w')
        self.search_entry = ttk.Entry(box, textvariable=self.text)
        self.search_entry.grid(row=0, column=1, columnspan=3, sticky='ew', padx=4, pady=2)

        ttk.Label(box, text='From (YYYY-MM-DD)').grid(row=1, column=0, sticky='w')
        self.start_entry = ttk.Entry(box, textvariable=self.start, width=12)
        self.start_entry.grid(row=1, column=1, sticky='w', padx=4, pady=2)
        ttk.Label(box, text='To').grid(row=1, column=2, sticky='e')
        self.end_entry = ttk.Entry(box, textvariable=self.end, width=12)
        self.end_entry.grid(row=1, column=3, sticky='w', padx=4, pady=2)

        quick = ttk.Frame(box)
        quick.grid(row=2, column=1, columnspan=3, sticky='w', padx=4)
        for label, days in (('Last 7 days', 7), ('Last 30 days', 30), ('Last 90 days', 90), ('All time', None)):
            ttk.Button(quick, text=label, command=lambda d=days: self.quick_range(d)).pack(side='left', padx=(0, 4))

        ttk.Label(box, text='Type').grid(row=3, column=0, sticky='w')
        ttk.Combobox(box, textvariable=self.kind, values=('All', 'credit', 'debit'), state='readonly', width=10).grid(row=3, column=1, sticky='w', padx=4, pady=2)

        ttk.Label(box, text='Min amount').grid(row=4, column=0, sticky='w')
        self.min_entry = ttk.Entry(box, textvariable=self.min_amount, width=12)
        self.min_entry.grid(row=4, column=1, sticky='w', padx=4, pady=2)
        ttk.Label(box, text='Max').grid(row=4, column=2, sticky='e')
        self.max_entry = ttk.Entry(box, textvariable=self.max_amount, width=12)
        self.max_entry.grid(row=4, column=3, sticky='w', padx=4, pady=2)

        cats = ttk.Frame(box)
        cats.grid(row=0, column=4, rowspan=5, sticky='nsew', padx=(16, 0))
        ttk.Label(cats, text='Categories (none selected = all)').pack(anchor='w')
        self.category_list = tk.Listbox(cats, selectmode='multiple', height=6, exportselection=False)
        self.category_list.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(cats, orient='vertical', command=self.category_list.yview)
        scroll.pack(side='left', fill='y')
        self.category_list.config(yscrollcommand=scroll.set)
        self.category_list.bind('<<ListboxSelect>>', lambda _: self._schedule_refresh())

        ttk.Button(box, text='Reset filters', command=self.reset_filters).grid(row=5, column=4, sticky='e', pady=(6, 0))

    def _build_table(self):
        frame = ttk.Frame(self)
        frame.grid(row=1, column=0, sticky='nsew', pady=8)
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(frame, columns=[c[0] for c in COLUMNS], show='headings', selectmode='browse')
        for key, title, width, anchor in COLUMNS:
            self.tree.heading(key, text=title, command=lambda k=key: self.sort_by(k))
            self.tree.column(key, width=width, anchor=anchor, stretch=key == 'description')
        self.tree.tag_configure('credit', foreground='#1a7f37')
        self.tree.tag_configure('debit', foreground='#b42318')
        self.tree.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(frame, orient='vertical', command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        self.tree.config(yscrollcommand=scroll.set)
        self.tree.bind('<Double-1>', lambda _: self.show_details())
        self.tree.bind('<Return>', lambda _: self.show_details())

    def _build_footer(self):
        footer = ttk.Frame(self)
        footer.grid(row=2, column=0, sticky='ew')
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.summary).grid(row=0, column=0, sticky='w')

        nav = ttk.Frame(footer)
        nav.grid(row=0, column=1, sticky='e')
        ttk.Label(nav, text='Rows per page').pack(side='left')
        ttk.Combobox(nav, textvariable=self.page_size, values=PAGE_SIZES, state='readonly', width=5).pack(side='left', padx=(4, 12))
        self.prev_button = ttk.Button(nav, text='◀ Prev', command=lambda: self.go_to_page(self.page_number - 1))
        self.prev_button.pack(side='left')
        ttk.Label(nav, textvariable=self.page_label, width=14, anchor='center').pack(side='left')
        self.next_button = ttk.Button(nav, text='Next ▶', command=lambda: self.go_to_page(self.page_number + 1))
        self.next_button.pack(side='left')
        ttk.Button(nav, text='Export…', command=self.export_csv).pack(side='left', padx=(12, 0))

        ttk.Label(footer, textvariable=self.status, foreground='#b42318').grid(row=1, column=0, columnspan=2, sticky='w')

    # ----- behaviour -----
    def _load_categories(self):
        self.category_list.delete(0, 'end')
        for name in sorted({t.category for t in self.transactions}):
            self.category_list.insert('end', name)

    def _schedule_refresh(self):
        if self._pending is not None:
            self.after_cancel(self._pending)
        self._pending = self.after(DEBOUNCE_MS, lambda: self._refresh(reset_page=True))

    def current_filter(self) -> Filter:
        """Build a Filter from the inputs; raises ValueError naming the bad field."""
        errors, values = [], {}
        for name, var, parse in (('From date', self.start, history.parse_date), ('To date', self.end, history.parse_date),
                                 ('Min amount', self.min_amount, history.parse_amount), ('Max amount', self.max_amount, history.parse_amount)):
            try:
                values[name] = parse(var.get())
            except ValueError:
                errors.append(name)
        if not errors and values['From date'] and values['To date'] and values['From date'] > values['To date']:
            errors.append('From date is after To date')
        if not errors and values['Min amount'] is not None and values['Max amount'] is not None and values['Min amount'] > values['Max amount']:
            errors.append('Min amount is greater than Max amount')
        if errors:
            raise ValueError('Check: ' + ', '.join(errors))
        return Filter(text=self.text.get(), start=values['From date'], end=values['To date'],
                      categories=frozenset(self.category_list.get(i) for i in self.category_list.curselection()),
                      type=None if self.kind.get() == 'All' else self.kind.get(),
                      min_amount=values['Min amount'], max_amount=values['Max amount'])

    def _refresh(self, reset_page=False):
        self._pending = None
        try:
            flt = self.current_filter()
        except ValueError as error:
            self.status.set(str(error))
            return  # keep showing the last valid results
        self.status.set('')
        self.filtered = history.apply(self.transactions, flt, self.sort_key, self.descending)
        if reset_page:
            self.page_number = 1
        self._render()

    def _render(self):
        size = int(self.page_size.get())
        pages = history.page_count(len(self.filtered), size)
        self.page_number = max(1, min(self.page_number, pages))
        self.tree.delete(*self.tree.get_children())
        for t in history.page(self.filtered, self.page_number, size):
            self.tree.insert('', 'end', iid=t.id, tags=(t.type,),
                             values=(t.date.isoformat(), t.description, t.category, t.type, money(t.signed_amount)))
        for key, title, *_ in COLUMNS:
            arrow = (' ▼' if self.descending else ' ▲') if key == self.sort_key else ''
            self.tree.heading(key, text=title + arrow)
        s = history.summarize(self.filtered)
        self.summary.set(f'{s.count} of {len(self.transactions)} transactions  |  In: {money(s.credits)}  '
                         f'Out: {money(s.debits)}  Net: {money(s.net)}  |  {self.source}')
        self.page_label.set(f'Page {self.page_number} of {pages}')
        self.prev_button.state(['!disabled'] if self.page_number > 1 else ['disabled'])
        self.next_button.state(['!disabled'] if self.page_number < pages else ['disabled'])

    def sort_by(self, key):
        # Clicking the active column flips direction; a new column starts descending for date/amount.
        if key == self.sort_key:
            self.descending = not self.descending
        else:
            self.sort_key, self.descending = key, key in ('date', 'amount')
        self._refresh(reset_page=True)

    def go_to_page(self, number):
        self.page_number = number
        self._render()

    def quick_range(self, days):
        latest = max((t.date for t in self.transactions), default=date.today())
        self.start.set('' if days is None else (latest - timedelta(days=days - 1)).isoformat())
        self.end.set('' if days is None else latest.isoformat())

    def reset_filters(self):
        for var in (self.text, self.start, self.end, self.min_amount, self.max_amount):
            var.set('')
        self.kind.set('All')
        self.category_list.selection_clear(0, 'end')
        self._refresh(reset_page=True)

    def set_transactions(self, transactions, source):
        self.transactions, self.source = list(transactions), source
        self._load_categories()
        self.reset_filters()

    def show_details(self):
        selected = self.tree.selection()
        if not selected:
            return
        t = next(t for t in self.filtered if t.id == selected[0])
        messagebox.showinfo('Transaction details', f'ID: {t.id}\nDate: {t.date:%A, %B %d, %Y}\nDescription: {t.description}\n'
                                                   f'Category: {t.category}\nType: {t.type}\nAmount: {money(t.signed_amount)}', parent=self.master)

    def open_csv(self):
        path = filedialog.askopenfilename(title='Open transactions CSV', filetypes=[('CSV files', '*.csv'), ('All files', '*.*')])
        if not path:
            return
        try:
            self.set_transactions(history.load_csv(path), path)
        except (OSError, ValueError) as error:
            messagebox.showerror('Could not open file', str(error), parent=self.master)

    def export_csv(self):
        path = filedialog.asksaveasfilename(title='Export filtered transactions', defaultextension='.csv',
                                            initialfile='transactions_filtered.csv', filetypes=[('CSV files', '*.csv')])
        if not path:
            return
        try:
            history.save_csv(path, self.filtered)
            self.status.set('')
            messagebox.showinfo('Export complete', f'Saved {len(self.filtered)} transactions to\n{path}', parent=self.master)
        except OSError as error:
            messagebox.showerror('Could not save file', str(error), parent=self.master)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        transactions, source = history.load_csv(argv[0]), argv[0]
    else:
        transactions, source = history.sample_transactions(), 'Sample data'
    root = tk.Tk()
    root.title('Transaction History')
    root.geometry('980x640')
    root.minsize(760, 480)
    TransactionHistoryApp(root, transactions, source)
    root.mainloop()


if __name__ == '__main__':
    main()
