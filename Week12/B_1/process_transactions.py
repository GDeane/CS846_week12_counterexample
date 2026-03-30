from __future__ import annotations
import csv
import math
import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Dict, Iterable, Optional, Set


@dataclass
class Account:
	account_id: str
	customer_name: str
	email: str
	currency: str
	balance: Decimal


@dataclass
class BlacklistRule:
	rule_id: str
	account_id: str
	applies_to: str
	txn_type: str
	min_amount: Optional[Decimal]
	max_amount: Optional[Decimal]
	currency: Optional[str]
	counterparty_account: Optional[str]


def _parse_decimal_amount(value: str) -> Optional[Decimal]:
	try:
		d = Decimal(value)
	except (InvalidOperation, TypeError):
		return None
	if not d.is_finite():
		return None
	return d


def _parse_account_id(raw: str) -> Optional[str]:
	if raw is None:
		return None
	s = str(raw).strip()
	return s or None


def load_accounts(path: str) -> Dict[str, Account]:
	accounts: Dict[str, Account] = {}
	with open(path, newline="") as f:
		transactions = csv.DictReader(f)
		for transaction in transactions:
			try:
				account_id = _parse_account_id(transaction.get("account_id", ""))
				if not account_id:
					continue

				currency = (transaction.get("currency") or "").strip()
				if not currency:
					continue

				balance_raw = (transaction.get("balance") or "").strip()
				balance = _parse_decimal_amount(balance_raw)
				if balance is None:
					continue

				accounts[account_id] = Account(
					account_id=account_id,
					customer_name=(transaction.get("customer_name") or "").strip(),
					email=(transaction.get("email") or "").strip(),
					currency=currency,
					balance=balance,
				)
			except Exception:
				continue
	return accounts


def load_blacklist(path: str) -> list[BlacklistRule]:
	rules: list[BlacklistRule] = []
	with open(path, newline="") as f:
		reader = csv.DictReader(f)
		for row in reader:
			try:
				rule_id = (row.get("rule_id") or "").strip()
				account_id = _parse_account_id(row.get("account_id") or "")
				applies_to = (row.get("applies_to") or "").strip().lower()
				txn_type = (row.get("txn_type") or "").strip().lower()
				if not rule_id or not account_id or applies_to not in {"from", "to"} or not txn_type:
					continue

				min_amount_raw = (row.get("min_amount") or "").strip()
				max_amount_raw = (row.get("max_amount") or "").strip()
				min_amount = _parse_decimal_amount(min_amount_raw) if min_amount_raw else None
				max_amount = _parse_decimal_amount(max_amount_raw) if max_amount_raw else None
				currency = (row.get("currency") or "").strip() or None
				counterparty = _parse_account_id(row.get("counterparty_account") or "")

				rules.append(
					BlacklistRule(
						rule_id=rule_id,
						account_id=account_id,
						applies_to=applies_to,
						txn_type=txn_type,
						min_amount=min_amount,
						max_amount=max_amount,
						currency=currency,
						counterparty_account=counterparty,
					)
				)
			except Exception:
				continue
	return rules


def _is_blacklisted(
	rules: list[BlacklistRule],
	*,
	txn_type: str,
	amount: Decimal,
	currency: str,
	from_acct: Optional[str],
	to_acct: Optional[str],
) -> bool:
	"""Return True if any rule blocks this transaction (silent skip)."""
	i = 0
	while i < len(rules):
		r = rules[i]
		i += 1

		if r.txn_type != txn_type:
			continue
		if r.currency is not None and r.currency != currency:
			continue
		if r.min_amount is not None and amount < r.min_amount:
			continue
		if r.max_amount is not None and amount > r.max_amount:
			continue

		# Which side does the rule apply to?
		subject = from_acct if r.applies_to == "from" else to_acct
		counterparty = to_acct if r.applies_to == "from" else from_acct
		if subject is None:
			continue
		if subject != r.account_id:
			continue
		if r.counterparty_account is not None and counterparty != r.counterparty_account:
			continue

		return True

	return False


def write_accounts(path: str, accounts: Dict[str, Account]) -> None:
	fieldnames = ["account_id", "customer_name", "email", "currency", "balance"]
	with open(path, "w", newline="") as f:
		writer = csv.DictWriter(f, fieldnames=fieldnames)
		writer.writeheader()
		for account_id in sorted(accounts.keys(), key=lambda x: (len(x), x)):
			a = accounts[account_id]
			writer.writerow(
				{
					"account_id": a.account_id,
					"customer_name": a.customer_name,
					"email": a.email,
					"currency": a.currency,
					"balance": f"{a.balance:.2f}",
				}
			)


def apply_transactions(accounts: Dict[str, Account], transactions_path: str, blacklist_rules: list[BlacklistRule]) -> None:
	seen_ids: Set[str] = set()
	with open(transactions_path, newline="") as f:
		transactions = csv.DictReader(f)
		for transaction in transactions:
			try:
				txn_id = (transaction.get("txn_id") or "").strip()
				if not txn_id or txn_id in seen_ids:
					continue

				txn_type = (transaction.get("type") or "").strip().lower()
				currency = (transaction.get("currency") or "").strip()
				amount = _parse_decimal_amount((transaction.get("amount") or "").strip())
				if amount is None or amount <= 0:
					continue

				from_acct = _parse_account_id(transaction.get("from_account", ""))
				to_acct = _parse_account_id(transaction.get("to_account", ""))

				if _is_blacklisted(
					blacklist_rules,
					txn_type=txn_type,
					amount=amount,
					currency=currency,
					from_acct=from_acct,
					to_acct=to_acct,
				):
					continue

				if txn_type == "deposit":
					if from_acct is not None or to_acct is None:
						continue
					if to_acct not in accounts:
						continue
					if accounts[to_acct].currency != currency:
						continue
					accounts[to_acct].balance += amount

				elif txn_type == "withdrawal":
					if to_acct is not None or from_acct is None:
						continue
					if from_acct not in accounts:
						continue
					if accounts[from_acct].currency != currency:
						continue
					if accounts[from_acct].balance < amount:
						continue
					accounts[from_acct].balance -= amount

				elif txn_type == "transfer":
					if from_acct is None or to_acct is None:
						continue
					if from_acct == to_acct:
						continue
					if from_acct not in accounts or to_acct not in accounts:
						continue
					if accounts[from_acct].currency != currency or accounts[to_acct].currency != currency:
						continue
					if accounts[from_acct].balance < amount:
						continue
					accounts[from_acct].balance -= amount
					accounts[to_acct].balance += amount

				else:
					continue

				seen_ids.add(txn_id)
			except Exception:
				continue


def main() -> None:
	here = os.path.dirname(os.path.abspath(__file__))
	accounts_path = os.path.join(here, "accounts.csv")
	transactions_path = os.path.join(here, "transactions.csv")
	blacklist_path = os.path.join(here, "blacklist.csv")

	accounts = load_accounts(accounts_path)
	blacklist_rules = load_blacklist(blacklist_path)
	apply_transactions(accounts, transactions_path, blacklist_rules)
	write_accounts(accounts_path, accounts)


if __name__ == "__main__":
	main()