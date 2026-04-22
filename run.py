"""
This script converts an extract from Neat into a format Wave can understand
"""

import csv
import enum
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import List

import click
from pydantic import BaseModel, Field


class TransactionRecord(BaseModel):
    """Represents a standardized transaction record."""

    tx_datetime: datetime = Field(description="Transaction date")
    amount: str = Field(
        description="Transaction amount (positive for deposits, negative for withdrawals)"
    )
    description: str = Field(description="Transaction description")


class InputSource(enum.Enum):
    AIRWALLEX = enum.auto()
    CURRENXIE = enum.auto()
    ERSTEBANK = enum.auto()
    NEAT = enum.auto()
    PAYONEER = enum.auto()
    REVOLUT = enum.auto()
    STARLING = enum.auto()
    WISE = enum.auto()


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


def read_input(
    start_datetime: datetime, in_path: Path, source: InputSource, is_reimbursement: bool
) -> List[TransactionRecord]:
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
        return _extract_revolut_data(
            start_datetime, csv.DictReader(lines), is_reimbursement
        )
    elif source == InputSource.WISE:
        lines = in_path.read_text().splitlines()
        return _extract_wise_data(start_datetime, csv.DictReader(lines))
    elif source == InputSource.STARLING:
        lines = in_path.read_text(encoding="unicode_escape").splitlines()
        return _extract_starling_data(
            start_datetime, csv.DictReader(lines), is_reimbursement
        )
    elif source == InputSource.PAYONEER:
        lines = in_path.read_text(encoding="utf-8-sig").splitlines()
        return _extract_payoneer_data(start_datetime, csv.DictReader(lines))
    elif source == InputSource.CURRENXIE:
        lines = in_path.read_text().splitlines()
        return _extract_currenxie_data(start_datetime, csv.DictReader(lines))
    else:
        raise ValueError(f"Unknown source: {source}")


def _extract_neat_data(
    start_datetime: datetime, content: csv.DictReader
) -> List[TransactionRecord]:
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
            TransactionRecord(
                description=c[description_header],
                amount=c[transaction_amount_header],
                tx_datetime=c_dt,
            )
        ]
    return result


def _extract_airwallex_data(
    start_datetime: datetime, content: csv.DictReader
) -> List[TransactionRecord]:
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
            TransactionRecord(
                description=description,
                amount=c[amount_header],
                tx_datetime=c_dt,
            )
        ]

    return result


def _extract_erste_data(
    start_datetime: datetime, content: csv.DictReader
) -> List[TransactionRecord]:
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
        inbound: str = (
            c[deposit_header].replace(".", "").replace(",", ".")
        )  # use . as decimal (instead of ,)
        outbound: str = (
            c[payment_header].replace(".", "").replace(",", ".")
        )  # use . as decimal (instead of ,)
        if inbound and outbound:
            raise ValueError(
                f"Both inbound and outbound transactions for {description} (line {i})"
            )
        elif inbound:
            amount = inbound
            if beneficiary := c[beneficiary_header]:
                description += f" from {beneficiary}"
        else:
            amount = "-" + outbound
            if beneficiary := c[beneficiary_header]:
                description += f" to {beneficiary}"

        result += [
            TransactionRecord(
                description=description,
                amount=amount,
                tx_datetime=c_dt,
            )
        ]

    return result


def _extract_revolut_data(
    start_datetime: datetime, content: csv.DictReader, is_reimbursement: bool
) -> List[TransactionRecord]:
    result = []
    transaction_date_header = "Completed Date"
    description_header = "Description"
    amount_header = "Amount"
    state_header = "State"

    for i, c in enumerate(content):
        # skip non completed transactions (e.g. reverted), these won't have a completed date, so we need to check it 1st
        if c[state_header] != "COMPLETED":
            continue

        c_dt = datetime.strptime(c[transaction_date_header], "%Y-%m-%d %H:%M:%S")
        # ignore lines older than the start datetime,
        if c_dt <= start_datetime:
            continue

        description: str = c[description_header].replace(",", "")
        if is_reimbursement:
            # for reimbursements, we don't care about refunds
            if Decimal(c[amount_header]) > 0:
                continue
            amount = str(
                -Decimal(c[amount_header]).quantize(Decimal(".01"), ROUND_HALF_UP)
            )
        else:
            amount = c[amount_header]
        result += [
            TransactionRecord(
                description=description,
                amount=amount,
                tx_datetime=c_dt,
            )
        ]

    return result


def _extract_starling_data(
    start_datetime: datetime, content: csv.DictReader, is_reimbursement: bool
) -> List[TransactionRecord]:
    result = []
    transaction_date_header = "Date"
    counter_party_header = "Counter Party"
    reference_header = "Reference"
    amount_header = "Amount (GBP)"

    for i, c in enumerate(content):
        c_dt = datetime.strptime(c[transaction_date_header], "%d/%m/%Y")
        # ignore lines older than the start datetime,
        if c_dt <= start_datetime:
            continue

        counter_party = c[counter_party_header].strip()
        reference = c[reference_header].strip()
        if counter_party.lower() == reference.lower():
            description = counter_party
        else:
            description = f"{reference} (to: {counter_party})"

        if is_reimbursement:
            # for reimbursements, we don't care about refunds
            if Decimal(c[amount_header]) > 0:
                continue
            amount = str(
                -Decimal(c[amount_header]).quantize(Decimal(".01"), ROUND_HALF_UP)
            )
        else:
            amount = c[amount_header]
        result += [
            TransactionRecord(
                description=description,
                amount=amount,
                tx_datetime=c_dt,
            )
        ]

    return result


def _extract_wise_data(
    start_datetime: datetime, content: csv.DictReader
) -> List[TransactionRecord]:
    result = []
    amount_header = "Source amount (after fees)"
    fees_header = "Source fee amount"
    transaction_date_header = "Created on"
    direction_header = "Direction"
    source_header = "Source name"
    destination_header = "Target name"

    for i, c in enumerate(content):
        c_dt = datetime.strptime(c[transaction_date_header], "%Y-%m-%d %H:%M:%S")
        # ignore lines older than the start datetime
        if c_dt <= start_datetime:
            continue

        transfer_direction = c[direction_header]
        amount = c[amount_header]
        fees = c[fees_header]
        if transfer_direction == "IN":
            description = f"Received from {c[source_header]}"
        elif transfer_direction == "OUT":
            amount = f"-{amount}"
            fees = f"-{fees}"
            description = f"Sent to {c[destination_header]}"
        else:
            raise ValueError(f"Unexpected transfer direction {c['direction']}")

        result += [
            TransactionRecord(
                description=description,
                amount=amount,
                tx_datetime=c_dt,
            )
        ]
        if Decimal(fees) != Decimal(0):
            result += [
                TransactionRecord(
                    description=f"Fee: {description}",
                    amount=fees,
                    tx_datetime=c_dt,
                )
            ]

    return result


def _extract_payoneer_data(
    start_datetime: datetime, content: csv.DictReader
) -> List[TransactionRecord]:
    result = []

    transaction_date_header = "Transaction date"
    transaction_time_header = "Transaction time"
    timezone_header = "Time zone"
    credit_amount_header = "Credit amount"
    debit_amount_header = "Debit amount"
    description_header = "Description"

    for i, c in enumerate(content):
        # Combine date, time, and timezone to create datetime
        date_str = c[transaction_date_header]
        time_str = c[transaction_time_header]
        timezone_str = c[timezone_header]

        # Parse the datetime (assuming format MM-DD-YYYY HH:MM:SS TZ)
        datetime_str = f"{date_str} {time_str} {timezone_str}"
        c_dt = datetime.strptime(datetime_str, "%m-%d-%Y %H:%M:%S %Z")

        # ignore lines older than the start datetime
        if c_dt <= start_datetime:
            continue

        # Get credit and debit amounts
        credit_str = c[credit_amount_header].replace(",", "").strip()
        debit_str = c[debit_amount_header].replace(",", "").strip()

        # Convert to Decimal for validation
        credit = Decimal(credit_str) if credit_str else Decimal("0")
        debit = Decimal(debit_str) if debit_str else Decimal("0")

        # Validate amount logic
        if credit == Decimal("0") and debit == Decimal("0"):
            raise ValueError(
                f"Both credit and debit amounts are zero for transaction on {c_dt} (line {i})"
            )

        if credit < Decimal("0"):
            raise ValueError(
                f"Credit amount cannot be negative: {credit} for transaction on {c_dt} (line {i})"
            )

        if debit > Decimal("0"):
            raise ValueError(
                f"Debit amount cannot be positive: {debit} for transaction on {c_dt} (line {i})"
            )

        if credit != Decimal("0") and debit != Decimal("0"):
            raise ValueError(
                f"Both credit and debit amounts are non-zero for transaction on {c_dt} (line {i})"
            )

        # Determine the amount (credit is positive, debit is negative)
        if credit != Decimal("0"):
            amount = str(credit)
        else:
            amount = str(debit)  # debit should already be negative

        # Clean description
        description: str = c[description_header].replace(",", "")

        result += [
            TransactionRecord(
                description=description,
                amount=amount,
                tx_datetime=c_dt,
            )
        ]

    return result


def _extract_currenxie_data(
    start_datetime: datetime, content: csv.DictReader
) -> List[TransactionRecord]:
    result = []
    description_header = "Description"
    reference_header = "Reference"
    transaction_amount_header = "*Amount"
    transaction_date_header = "*Date (MM/DD/YYYY)"
    for i, c in enumerate(content):
        c_dt = datetime.strptime(c[transaction_date_header], "%m/%d/%Y")
        # ignore lines older than the start datetime
        if c_dt <= start_datetime:
            continue

        description = c[description_header]
        if reference := c[reference_header]:
            description = f"{description} - {reference}".strip()
        result += [
            TransactionRecord(
                description=description,
                amount=c[transaction_amount_header],
                tx_datetime=c_dt,
            )
        ]
    return result


def write_output(
    destination: OutputSource, out_path: Path, content: List[TransactionRecord]
) -> None:
    is_wave = destination == OutputSource.WAVE
    date_format = "%Y-%m-%d" if is_wave else "%d/%m/%Y"
    with out_path.open("w", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[CSV_DATE_HEADER, CSV_AMOUNT_HEADER, CSV_DESCRIPTION_HEADER],
        )
        # Wave wants headers, Freeagent doesn't
        if is_wave:
            writer.writeheader()
        # Convert TransactionRecord objects to dictionaries for CSV writing
        rows = [
            {
                CSV_DATE_HEADER: record.tx_datetime.strftime(date_format),
                CSV_AMOUNT_HEADER: record.amount,
                CSV_DESCRIPTION_HEADER: record.description,
            }
            for record in content
        ]
        writer.writerows(rows)


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
    "--target",
    "target_platform",
    type=click.Choice([i.name for i in OutputSource], case_sensitive=False),
    required=False,
    help="Target platform.",
    default=OutputSource.WAVE.name,
)
@click.option(
    "--reimbursement",
    "is_reimbursement",
    is_flag=True,
    show_default=True,
    default=False,
    help="Is a reimbursement account?",
)
@click.option(
    "--from",
    "from_date",
    help="Date from which we want to convert the file",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=datetime(2000, 1, 1),
)
def main(
    file_path: Path,
    file_type: str,
    target_platform: str,
    is_reimbursement: bool,
    from_date: datetime,
) -> None:
    file_type_enum = InputSource[file_type.upper()]
    target_platform_enum = OutputSource[target_platform.upper()]
    out_path = file_path.with_name(
        file_path.stem
        + f"_CONVERTED_{file_type_enum.name}_TO_{target_platform_enum.name}"
        + file_path.suffix
    )
    if out_path.exists():
        click.confirm(
            f"Target file '{out_path.as_posix()}' already exists. Do you want to overwrite?",
            abort=True,
            default=False,
        )
    if file_type_enum in [InputSource.STARLING] and not is_reimbursement:
        raise click.BadParameter("Expected reimbursement flag")
    if is_reimbursement and (
        file_type_enum not in [InputSource.REVOLUT, InputSource.STARLING]
        or target_platform_enum != OutputSource.WAVE
    ):
        raise click.BadParameter("Did not expect reimbursement flag")

    result = read_input(
        start_datetime=from_date,
        in_path=file_path,
        source=file_type_enum,
        is_reimbursement=is_reimbursement,
    )
    write_output(target_platform_enum, out_path, result)
    click.echo(f"Done. Converted csv written to\n{out_path}.")


if __name__ == "__main__":
    main()
