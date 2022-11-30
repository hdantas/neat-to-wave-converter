"""
This script converts an extract from Neat into a format Wave can understand
"""
import csv
import enum
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import click


class InputSource(enum.Enum):
    AIRWALLEX = enum.auto()
    CURRENXIE = enum.auto()
    ERSTEBANK = enum.auto()
    NEAT = enum.auto()
    PAYONEER = enum.auto()
    REVOLUT = enum.auto()


class OutputSource(enum.Enum):
    FREEAGENT = enum.auto()
    WAVE = enum.auto()


class AirwallexType(enum.Enum):
    DEPOSIT = "Deposit"
    FEE = "Fee"
    PAYOUT = "Payout"


CSV_DATE_HEADER = "date"
CSV_AMOUNT_HEADER = "amount"
CSV_DESCRIPTION_HEADER = "description"


def read_input(start_datetime: datetime, in_path: Path, source: InputSource) -> List[Dict]:

    if source == InputSource.NEAT:
        lines = in_path.read_text().splitlines()
        return _extract_neat_data(start_datetime, csv.DictReader(lines))
    elif source == InputSource.AIRWALLEX:
        # skip the first 5 lines in the airwallex csv since it has useless gibberish
        lines = in_path.read_text().splitlines()
        lines = lines[5:]
        return _extract_airwallex_data(start_datetime, csv.DictReader(lines))
    elif source == InputSource.ERSTEBANK:
        lines = in_path.read_text(encoding="windows-1252").splitlines()
        # skip the first 1 line in the erste csv since it has useless gibberish
        lines = lines[1:]
        return _extract_erste_data(start_datetime, csv.DictReader(lines, delimiter=";"))
    elif source == InputSource.REVOLUT:
        lines = in_path.read_text().splitlines()
        return _extract_revolut_data(start_datetime, csv.DictReader(lines))
    elif source == InputSource.PAYONEER:
        lines = in_path.read_text(encoding="utf-8-sig").splitlines()
        return _extract_payoneer_data(start_datetime, csv.DictReader(lines))
    elif source == InputSource.CURRENXIE:
        lines = in_path.read_text().splitlines()
        return _extract_currenxie_data(start_datetime, csv.DictReader(lines))
    else:
        raise ValueError(f"Unknown source: {source}")


def _extract_neat_data(start_datetime: datetime, content: csv.DictReader) -> List[Dict]:
    result = []
    description_header = "Description"
    transaction_amount_header = "Transaction Amount"
    transaction_date_header = "Transaction Date"
    for i, c in enumerate(content):
        c_dt = datetime.strptime(c[transaction_date_header], "%Y-%m-%d %H:%M:%S")
        # ignore lines older than the start datetime
        if c_dt <= start_datetime:
            continue
        result += [
            {
                CSV_DESCRIPTION_HEADER: c[description_header],
                CSV_AMOUNT_HEADER: c[transaction_amount_header],
                CSV_DATE_HEADER: c_dt.strftime("%Y-%m-%d"),
            }
        ]
    return result


def _extract_airwallex_data(start_datetime: datetime, content: csv.DictReader) -> List[Dict]:
    result = []
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
                CSV_DESCRIPTION_HEADER: description,
                CSV_AMOUNT_HEADER: c[amount_header],
                CSV_DATE_HEADER: c_dt.strftime("%Y-%m-%d"),
            }
        ]

    return result


def _extract_erste_data(start_datetime: datetime, content: csv.DictReader) -> List[Dict]:
    result = []
    transaction_date_header = "Datum izvršenja"  # execution date
    description_header = "Opis plaæanja, kurs"  # Payment description
    deposit_header = "Uplate"  # incoming transfers
    payment_header = "Isplate"  # outgoing payments
    beneficiary_header = "Primalac"  # Recipient

    for i, c in enumerate(content):
        c_dt = datetime.strptime(c[transaction_date_header], "%d.%m.%Y")
        # ignore lines older than the start datetime
        if c_dt <= start_datetime:
            continue

        description: str = c[description_header]
        inbound: str = c[deposit_header].replace(".", "").replace(",", ".")  # use . as decimal (instead of ,)
        outbound: str = c[payment_header].replace(".", "").replace(",", ".")  # use . as decimal (instead of ,)
        if inbound and outbound:
            raise ValueError(f"Both inbound and outbound transactions for {description} (line {i})")
        elif inbound:
            amount = inbound
            if beneficiary := c[beneficiary_header]:
                description += f" from {beneficiary}"
        else:
            amount = "-" + outbound
            if beneficiary := c[beneficiary_header]:
                description += f" to {beneficiary}"

        result += [
            {CSV_DESCRIPTION_HEADER: description, CSV_AMOUNT_HEADER: amount, CSV_DATE_HEADER: c_dt.strftime("%Y-%m-%d")}
        ]

    return result


def _extract_revolut_data(start_datetime: datetime, content: csv.DictReader) -> List[Dict]:
    result = []
    transaction_date_header = "Completed Date"
    description_header = "Description"
    amount_header = "Amount"

    for i, c in enumerate(content):
        c_dt = datetime.strptime(c[transaction_date_header], "%Y-%m-%d %H:%M:%S")
        # ignore lines older than the start datetime
        if c_dt <= start_datetime:
            continue

        description: str = c[description_header].replace(",", "")
        result += [
            {
                CSV_DESCRIPTION_HEADER: description,
                CSV_AMOUNT_HEADER: c[amount_header],
                CSV_DATE_HEADER: c_dt.strftime("%d/%m/%Y"),
            }
        ]

    return result


def _extract_payoneer_data(start_datetime: datetime, content: csv.DictReader) -> List[Dict]:
    result = []
    transaction_date_header = "Date"
    description_header = "Description"  # Payment description
    amount_header = "Amount"

    for i, c in enumerate(content):
        c_dt = datetime.strptime(c[transaction_date_header], "%d %b, %Y")
        # ignore lines older than the start datetime
        if c_dt <= start_datetime:
            continue

        # remove , since freeagent doesn't want them
        amount: str = c[amount_header].replace(",", "")
        description: str = c[description_header].replace(",", "")

        result += [
            {CSV_DESCRIPTION_HEADER: description, CSV_AMOUNT_HEADER: amount, CSV_DATE_HEADER: c_dt.strftime("%d/%m/%Y")}
        ]

    return result


def _extract_currenxie_data(start_datetime: datetime, content: csv.DictReader) -> List[Dict]:
    result = []
    description_header = "Description"
    reference_header = "Reference"
    transaction_amount_header = "*Amount"
    transaction_date_header = "*Date"
    for i, c in enumerate(content):
        c_dt = datetime.strptime(c[transaction_date_header], "%m/%d/%Y")
        # ignore lines older than the start datetime
        if c_dt <= start_datetime:
            continue

        description = c[description_header]
        if reference := c[reference_header]:
            description = f"{description} - {reference}".strip()
        result += [
            {
                CSV_DESCRIPTION_HEADER: description,
                CSV_AMOUNT_HEADER: c[transaction_amount_header],
                CSV_DATE_HEADER: c_dt.strftime("%Y-%m-%d"),
            }
        ]
    return result


def write_output(destination: OutputSource, out_path: Path, content: List[Dict]) -> None:
    # Wave wants headers, Freeagent doesn't
    write_header = destination == OutputSource.WAVE
    with out_path.open("w", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=[CSV_DATE_HEADER, CSV_AMOUNT_HEADER, CSV_DESCRIPTION_HEADER])
        if write_header:
            writer.writeheader()
        writer.writerows(content)


@click.command()
@click.option(
    "--path",
    "file_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, resolve_path=True, path_type=Path),
    help="Path for file to be converted.",
    prompt=True,
)
@click.option(
    "--type",
    "file_type",
    type=click.Choice([i.name for i in InputSource], case_sensitive=False),
    required=True,
    help="Path for file to be converted.",
    prompt=True,
)
@click.option(
    "--from",
    "from_date",
    help="Date from which we want to convert the file",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=datetime(2000, 1, 1),
)
def main(file_path: Path, file_type: str, from_date: datetime) -> None:
    file_type = InputSource[file_type.upper()]
    if file_type in [InputSource.REVOLUT, InputSource.PAYONEER]:
        destination = OutputSource.FREEAGENT
    else:
        destination = OutputSource.WAVE
    out_path = file_path.with_name(
        file_path.stem + f"_CONVERTED_{file_type.name}_TO_{destination.name}" + file_path.suffix
    )
    if out_path.exists():
        click.confirm(
            f"Target file '{out_path.as_posix()}' already exists. Do you want to overwrite?", abort=True, default=False
        )

    result = read_input(start_datetime=from_date, in_path=file_path, source=file_type)
    write_output(destination, out_path, result)
    click.echo(f"Done. Converted csv written to\n{out_path}.")


if __name__ == "__main__":
    main()
