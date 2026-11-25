"""Generate the independent scan fixtures for decimals of more than 38 digits (requires fastavro)."""

from decimal import Decimal, localcontext
from pathlib import Path

from fastavro import writer

test_dir = Path(__file__).resolve().parent.parent / "test"

# Avro puts no limit on the precision of a decimal. 39 is the first width DuckDB stores as a BIGNUM, 76 the widest
# decimal of Arrow and 255 and 300 are on either side of the widths that fit in a byte.
decimal_types = [(39, 0), (76, 10), (255, 3), (300, 10)]
fields = [{"name": "row_id", "type": "int"}]
for index, (precision, scale) in enumerate(decimal_types):
    # Both encodings of a decimal, and both orders of the nullable union
    if index % 2 == 0:
        decimal_type = {"type": "bytes", "logicalType": "decimal", "precision": precision, "scale": scale}
    else:
        decimal_type = {
            "type": "fixed",
            "name": f"fixed_{precision}_{scale}",
            # deliberately larger than the minimum size, which readers may not rely on
            "size": 130,
            "logicalType": "decimal",
            "precision": precision,
            "scale": scale,
        }
    fields.append(
        {
            "name": f"decimal_{precision}_{scale}",
            "type": ["null", decimal_type] if index < 2 else [decimal_type, "null"],
        }
    )
schema = {"type": "record", "name": "wide_decimals", "fields": fields}

# Values around a change in encoded length exercise the sign byte and the carry of the two's complement
unscaled_values = [None, "min", -(2**128), -65536, -65535, -256, -255, -129, -128, -1, 0, 1, 127, 128, 255, 256]
unscaled_values += [65535, 2**64, 2**127, 2**128 - 1, "max"]
rows = []
with localcontext() as context:
    context.prec = 400
    for row_id, value in enumerate(unscaled_values):
        row = {"row_id": row_id}
        for precision, scale in decimal_types:
            unscaled = value
            if value == "min":
                unscaled = -(10**precision - 1)
            elif value == "max":
                unscaled = 10**precision - 1
            row[f"decimal_{precision}_{scale}"] = None if unscaled is None else Decimal(unscaled).scaleb(-scale)
        rows.append(row)

    with (test_dir / "wide_decimal_bytes.avro").open("wb") as output:
        writer(output, schema, rows, codec="null", sync_marker=b"wide-decimals!!!")

# A file whose values have more digits than the precision it declares: 10^39 and -(10^39) in a decimal(39, 0). The
# bytes are written as is, the writer of fastavro would reject the values.
overflow_schema = {
    "type": "record",
    "name": "wide_decimal_overflow",
    "fields": [
        {"name": "row_id", "type": "int"},
        {"name": "d", "type": {"type": "bytes", "logicalType": "decimal", "precision": 39, "scale": 0}},
    ],
}
overflow_values = [10**39 - 1, 10**39, -(10**39)]
overflow_rows = [
    {"row_id": row_id, "d": value.to_bytes(17, byteorder="big", signed=True)}
    for row_id, value in enumerate(overflow_values)
]
with (test_dir / "wide_decimal_overflow.avro").open("wb") as output:
    writer(output, overflow_schema, overflow_rows, codec="null", sync_marker=b"wide-decimals!!!")

# A precision that is not valid
invalid_schema = {
    "type": "record",
    "name": "zero_precision",
    "fields": [{"name": "d", "type": {"type": "bytes", "logicalType": "decimal", "precision": 0, "scale": 0}}],
}
with (test_dir / "decimal_zero_precision.avro").open("wb") as output:
    writer(output, invalid_schema, [{"d": b"\x01"}], codec="null", sync_marker=b"wide-decimals!!!", validator=None)
