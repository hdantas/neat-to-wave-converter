"""
This script converts an extract from Neat into a format Wave can understand
"""
import csv
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List


def read_input(start_datetime: datetime, in_path: str) -> List[Dict]:
    with Path(in_path).open("r", encoding="utf-8") as file:
        content = _extract_data(start_datetime, csv.DictReader(file))
    return content


def _extract_data(start_datetime: datetime, content: csv.DictReader) -> List[Dict]:
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

    result = read_input(start_datetime=start_date_dt, in_path=in_path)
    write_output(out_path, result)
    print(f"Done. Converted csv written to\n{out_path}")


if __name__ == "__main__":
    main()
