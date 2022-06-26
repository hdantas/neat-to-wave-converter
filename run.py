"""
This script converts an extract from Neat into a format Wave can understand
"""
import csv
import enum
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List


class InputSource(enum.Enum):
    NEAT = enum.auto()
    AIRWALLEX = enum.auto()


class AirwallexType(enum.Enum):
    DEPOSIT = "Deposit"
    FEE = "Fee"
    PAYOUT = "Payout"


def read_input(start_datetime: datetime, in_path: str, source: InputSource) -> List[Dict]:
    lines = Path(in_path).read_text().splitlines()

    if source == InputSource.NEAT:
        func = _extract_neat_data
    elif source == InputSource.AIRWALLEX:
        func = _extract_airwallex_data
        # skip the first 5 lines in the airwallex csv since it has useless gibberish
        lines = lines[5:]
    else:
        raise ValueError(f"Unknown source: {source}")

    content = func(start_datetime, csv.DictReader(lines))
    return content


def _extract_neat_data(start_datetime: datetime, content: csv.DictReader) -> List[Dict]:
    result = []
    description_header = "Description"
    settlement_amount_header = "Settlement Amount (GBP)"
    transaction_amount_header = "Transaction Amount"
    transaction_date_header = "Transaction Date"
    for i, c in enumerate(content):
        c_dt = datetime.strptime(c[transaction_date_header], "%Y-%m-%d %H:%M:%S")
        # ignore lines older than the start datetime
        if c_dt <= start_datetime:
            continue
        amount = c[transaction_amount_header]
        settlement = c[settlement_amount_header]
        if amount != settlement:
            print(f"Line {i} amounts don't match {amount} != {settlement}")
        result += [
            {
                description_header: c[description_header],
                transaction_amount_header: amount,
                transaction_date_header: c_dt.strftime("%Y-%m-%d"),
            }
        ]
    return result


def _extract_airwallex_data(start_datetime: datetime, content: csv.DictReader) -> List[Dict]:
    result = []
    description_header = "Type"
    amount_header = "Net Amount"
    transaction_date_header = "Created At"
    transaction_type_header = "Type"
    remitter_header = "Remitter Name"
    beneficiary_header = "Beneficiary Bank Account Name"

    for i, c in enumerate(content):
        c_dt = datetime.strptime(c[transaction_date_header], "%Y-%m-%d %H:%M:%S")
        # ignore lines older than the start datetime
        if c_dt <= start_datetime:
            continue

        description = c[transaction_type_header]
        if AirwallexType(c[transaction_type_header]) == AirwallexType.DEPOSIT:
            description += f" from {c[remitter_header]}"
        elif AirwallexType(c[transaction_type_header]) == AirwallexType.PAYOUT:
            description += f" to {c[beneficiary_header]}"

        result += [
            {
                description_header: description,
                amount_header: c[amount_header],
                transaction_date_header: c_dt.strftime("%Y-%m-%d"),
            }
        ]

    return result


def write_output(out_path: str, content: List[Dict]) -> None:
    with Path(out_path).open("w", encoding="utf-8") as file:
        headers = content[0].keys()
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(content)


def main():
    print("Where is the file to be converted?")
    while 1:
        in_path = input()
        if Path(in_path).exists():
            break
        print("File does not exist. Try again.")

    print("Is the file from Neat or Airwallex? [N/A]")
    source_txt = input().lower()
    if source_txt in ["n", "neat"]:
        source = InputSource.NEAT
    elif source_txt in ["a", "airwallex"]:
        source = InputSource.AIRWALLEX
    else:
        sys.exit(f"Unknown source {source_txt}. Aborting")

    print(
        "When was the last transaction imported to Wave (eg 2020-07-28 14:48:43)? "
        "Press enter to include all."
    )
    while 1:
        start_date_str = input()
        if not start_date_str:
            start_date_dt = datetime(2000, 1, 1)
            break
        try:
            start_date_dt = datetime.strptime(start_date_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            print("Date doesn't match format (eg 2020-07-28 14:48:43). Try again.")
        else:
            break

    filename, ext = in_path.rsplit(".", 1)
    out_path = f"{filename}_CONVERTED.{ext}"
    if Path(out_path).exists():
        print(f"Target file '{out_path}' already exists. Do you want to overwrite y/N?")
        overwrite = input()
        if overwrite.lower() not in ["y", "yes"]:
            sys.exit("Aborting")

    result = read_input(start_datetime=start_date_dt, in_path=in_path, source=source)
    write_output(out_path, result)
    print(f"Done. Converted csv written to\n{out_path}")


if __name__ == "__main__":
    main()
