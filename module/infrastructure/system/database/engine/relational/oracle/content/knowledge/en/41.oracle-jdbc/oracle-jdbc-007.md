# Mapping NUMBER to BigDecimal and Controlling Precision in Oracle JDBC

## 1. Why control numeric types between Oracle and Java?

Oracle Database commonly uses the `NUMBER` type to store integers, decimals, monetary amounts, rates, quantities, and many other business values. In Java, the best matching type for `NUMBER` is `java.math.BigDecimal`, because both represent decimal numbers using base-10 semantics rather than binary floating-point numbers like `double`.

If an application reads `NUMBER` via `double`, computes with `double`, and writes back to the database, rounding errors can arise. For monetary amounts or financial figures, even tiny discrepancies can cause reconciliation, total amount, or reporting mismatches.

This lesson belongs to the **Database Engine Relational Oracle** module, **Oracle JDBC** chapter, focusing on **mapping NUMBER to BigDecimal and controlling precision**. Core objectives:

- Understand precision and scale of Oracle `NUMBER(p,s)`.
- Use `ResultSet.getBigDecimal()` and `PreparedStatement.setBigDecimal()` properly.
- Avoid converting through `double`/`float`, which loses precision.
- Explicitly define rounding, scale, overflow, and null rules.
- Inspect metadata, validate inputs, and design APIs.
- Write integration tests to catch arithmetic errors between Java and Oracle.

Core principle: keep data in decimal form end-to-end from input, Java, and JDBC to Oracle; convert to approximate types only when business requirements genuinely tolerate inaccuracy.

## 2. How does Oracle NUMBER represent numbers?

`NUMBER` is Oracle's decimal numeric type. It can represent integers and decimals with high decimal precision. Common declarations:

```sql
NUMBER
NUMBER(p)
NUMBER(p, s)
```

Where:
- `p` is precision: the total number of significant digits allowed.
- `s` is scale: the number of digits to the right of the decimal point; a negative scale means rounding to the left of the decimal point.

Oracle `NUMBER` supports up to 38 significant digits. With `NUMBER(p,s)` declarations, precision `p` typically ranges from 1 to 38; scale `s` ranges from -84 to 127. These values are limits of the Oracle type, not limits of `BigDecimal`.

### 2.1. Precision and scale

Example:

```sql
CREATE TABLE invoice_line (
    line_id NUMBER(12,0),
    quantity NUMBER(10,3),
    unit_price NUMBER(12,2),
    tax_rate NUMBER(7,6),
    adjustment NUMBER(8,-2)
);
```

| Declaration | Meaning | Example valid value |
|---|---|---|
| `NUMBER(12,0)` | Up to 12 digits, no fractional part | `123456789012` |
| `NUMBER(10,3)` | Total 10 digits, 3 decimal digits | `1234567.125` |
| `NUMBER(12,2)` | Total 12 digits, 2 decimal digits | `1234567890.12` |
| `NUMBER(7,6)` | Total 7 digits, 6 decimal digits | `0.123456` |
| `NUMBER(8,-2)` | Rounded to hundreds, up to 8 significant digits | `12345600` |

With `NUMBER(12,2)`, the integer part has at most 10 digits and the fractional part has 2 digits. Values exceeding the declared precision can trigger `ORA-01438`.

### 2.2. Negative scale

A negative scale is not "number of digits after the decimal point". For example:

```sql
amount_rounded NUMBER(6,-2)
```

Values are stored in multiples of 100 after applying Oracle's scale rules. A value like `12345` is rounded to the nearest hundred when assigned to this column. Therefore, negative scale must be modeled explicitly in Java if the application also needs to reflect the same rule.

### 2.3. NUMBER without declared precision/scale

Declaring `NUMBER` without `(p,s)` allows storing a wider range of precision/scale than a fixed-scale column, within the limits of the NUMBER type. This is useful when data has variable precision, but it makes the application's data contract less explicit.

For business data, declare explicit precision/scale when domain rules are known. For example, currency, rates, quantities, and measurement metrics usually have specific rules.

### 2.4. NUMBER vs. BINARY_FLOAT and BINARY_DOUBLE

Oracle also has `BINARY_FLOAT` and `BINARY_DOUBLE`, which are binary floating-point types. They suit scientific or engineering calculations needing floating point, but they do not share decimal semantics with `NUMBER`.

| Oracle type | Common Java type | Characteristics |
|---|---|---|
| `NUMBER` | `BigDecimal` | Decimal, suited for exact data |
| `BINARY_FLOAT` | `float` | 32-bit binary floating point |
| `BINARY_DOUBLE` | `double` | 64-bit binary floating point |

Do not switch a `NUMBER` column to `double` merely for coding convenience. Choose the Java type according to data semantics.

## 3. BigDecimal in Java

`BigDecimal` represents a decimal number via an unscaled integer value (unscaled value) together with a scale. Conceptually:

\[
value = unscaledValue \times 10^{-scale}
\]

Example:

```java
BigDecimal a = new BigDecimal("123.45");
```

This value has:
- Unscaled value: `12345`
- Scale: `2`
- Precision: `5`

Another number:

```java
BigDecimal b = new BigDecimal("1.2300");
```

`b` has scale 4 and precision 5. The two values `1.23` and `1.2300` are numerically equal, yet have different scales.

### 3.1. BigDecimal is immutable

Operations return a new `BigDecimal`:

```java
BigDecimal amount = new BigDecimal("10.00");
amount.add(new BigDecimal("2.50"));

System.out.println(amount); // 10.00
```

The result `12.50` is discarded because `add()` does not mutate the original object. Right way:

```java
amount = amount.add(new BigDecimal("2.50"));
```

Immutability makes `BigDecimal` safer to pass across layers, but developers must always capture the returned value.

### 3.2. Precision is not the same as scale

```java
BigDecimal x = new BigDecimal("123.4500");

System.out.println(x.precision()); // 7
System.out.println(x.scale());     // 4
```

- `precision()` returns the number of digits in the unscaled value.
- `scale()` returns the number of digits to the right of the decimal point; scale can be negative.

Do not use `precision()` to infer decimal places or `scale()` to infer total digits.

### 3.3. equals() and compareTo()

```java
BigDecimal x = new BigDecimal("1.0");
BigDecimal y = new BigDecimal("1.00");

System.out.println(x.equals(y));        // false
System.out.println(x.compareTo(y) == 0); // true
```

`equals()` compares both value and scale. `compareTo()` compares numerical value.

When checking whether two monetary amounts are business-equal, usually use:

```java
if (x.compareTo(y) == 0) {
    // Same numerical value
}
```

If the contract requires a fixed scale, normalize the scale before comparing or serializing.

## 4. JDBC mapping: NUMBER to BigDecimal

The Oracle JDBC driver maps Oracle `NUMBER` to Java `java.math.BigDecimal` following standard decimal number mapping. JDBC also provides direct methods to retrieve and bind `BigDecimal`.

### 4.1. Reading with ResultSet.getBigDecimal()

```java
String sql = """
    SELECT invoice_id, total_amount
    FROM app.invoice
    WHERE invoice_id = ?
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, invoiceId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            long id = resultSet.getLong("invoice_id");
            BigDecimal total = resultSet.getBigDecimal("total_amount");

            // total == null if the SQL column is NULL
        }
    }
}
```

`getBigDecimal()` is the preferred choice when the Oracle column is `NUMBER` and the application needs to preserve decimal precision.

### 4.2. Binding with PreparedStatement.setBigDecimal()

```java
String sql = """
    INSERT INTO app.invoice (invoice_id, total_amount)
    VALUES (?, ?)
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, invoiceId);
    statement.setBigDecimal(2, new BigDecimal("1250.75"));

    statement.executeUpdate();
}
```

`setBigDecimal()` sends the decimal value over JDBC as a bind parameter. There is no need to convert to a SQL string literal, avoiding dependence on the database session's NLS decimal separator.

### 4.3. Do not concatenate BigDecimal into SQL strings

Avoid:

```java
String sql = "INSERT INTO app.invoice(total_amount) VALUES ("
        + amount.toString() + ")";
statement.executeUpdate(sql);
```

This approach:
- Foregoes bind variable benefits.
- Causes SQL text to change for every value.
- Increases parse overhead.
- Risks formatting errors and SQL injection when combined with other inputs.
- Makes NLS control difficult if numbers pass through strings.

Use `?` placeholders and `setBigDecimal()`.

### 4.4. getObject() and mapping

For Oracle `NUMBER`, `ResultSet.getObject()` normally returns `BigDecimal` per the driver's JDBC mapping. However, code needing an explicit type should call `getBigDecimal()` directly:

```java
BigDecimal amount = resultSet.getBigDecimal("amount");
```

Do not rely on casting `getObject()` if drivers, column types, or mapping layers might change. With JDBC 4.2, typed `getObject(column, BigDecimal.class)` can be used when supported by the driver, though `getBigDecimal()` is direct and readable.

### 4.5. Reading and binding NULL

`getBigDecimal()` returns `null` when the SQL value is `NULL`. There is no need to call `wasNull()` after `getBigDecimal()` to distinguish null.

When binding null, declare the JDBC type explicitly:

```java
if (amount == null) {
    statement.setNull(2, java.sql.Types.NUMERIC);
} else {
    statement.setBigDecimal(2, amount);
}
```

Do not replace null with `BigDecimal.ZERO` unless business rules explicitly define them as equivalent. SQL NULL indicates an absent/unknown value; zero is an actual numeric value.

## 5. Why not use double for Oracle NUMBER?

Java `double` uses IEEE 754 binary floating-point representation. Many finite base-10 decimals cannot be represented exactly in binary.

Example:

```java
double d = 0.1 + 0.2;
System.out.println(d); // typically prints 0.30000000000000004
```

Whereas decimal arithmetic:

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");

System.out.println(a.add(b)); // 0.3
```

### 5.1. Pitfall of new BigDecimal(double)

Avoid:

```java
BigDecimal amount = new BigDecimal(0.1);
```

The constructor taking `double` converts the existing approximate binary representation into the exact decimal of that binary value. The result can be a long string such as `0.10000000000000000555...`.

Prefer:

```java
BigDecimal amount = new BigDecimal("0.1");
```

Or if the input is an integer:

```java
BigDecimal count = BigDecimal.valueOf(123L);
```

`BigDecimal.valueOf(double)` uses `Double`'s canonical string conversion, avoiding long tails like the `double` constructor, though it cannot recover precision already lost if the source data was already rounded in `double`. For monetary data, it is best to receive decimals as strings or decimal types from the start.

### 5.2. Accumulated error

If each invoice line passes through `double`, the sum of thousands of lines can diverge from the total computed in Oracle `NUMBER`. Discrepancies also appear when:
- Calculating tax ratios.
- Allocating discounts.
- Converting currencies.
- Calculating interest rates.
- Computing averages and cost allocations.

Using `BigDecimal` end-to-end keeps decimal rules under clear control.

### 5.3. When is double appropriate?

`double` may be suitable for:
- Scientific simulations.
- Graphics or approximation algorithms.
- Sensor data where error tolerance is acceptable.
- Numerical computations where binary floating point is naturally required.

Never use `double` for monetary amounts, balances, taxes, exchange rates, or values requiring exact reconciliation when stored in Oracle `NUMBER`.

## 6. Controlling scale before writing to the database

A `NUMBER(12,2)` column only holds two decimal places. Java should clearly define whether the application will:
- Reject values with more than two decimal places.
- Round according to business rules.
- Or pass them as-is and let Oracle apply scale.

Do not let this behavior happen accidentally in the database without an explicit contract.

### 6.1. Reject if rounding would be needed

Use `RoundingMode.UNNECESSARY` to require that no information is rounded away:

```java
BigDecimal normalized = amount.setScale(
    2,
    RoundingMode.UNNECESSARY
);
```

If `amount` has fractional digits beyond 2 places and cannot be represented exactly at scale 2, Java throws `ArithmeticException`.

Examples:
- `12.3` becomes `12.30` with no loss of information.
- `12.345` is rejected.
- `12.340` can be normalized to `12.34` because the dropped digits are all zeros.

### 6.2. Rounding with a chosen rule

```java
BigDecimal normalized = amount.setScale(
    2,
    RoundingMode.HALF_UP
);
```

`HALF_UP` rounds to nearest; ties round away from zero. This is a common rule, though not the right rule for every business case.

Common modes:

| RoundingMode | Behavior |
|---|---|
| `UP` | Rounds away from zero if digits must be discarded |
| `DOWN` | Truncates toward zero |
| `CEILING` | Rounds toward positive infinity |
| `FLOOR` | Rounds toward negative infinity |
| `HALF_UP` | Nearest; ties round away from zero |
| `HALF_DOWN` | Nearest; ties round toward zero |
| `HALF_EVEN` | Nearest; ties round toward even digit |
| `UNNECESSARY` | Disallows rounding |

### 6.3. Do not assume every currency has 2 decimal places

Some currencies have 0, 2, or 3 decimal places by convention. Rounding rules can also depend on:
- Transaction type.
- Country and accounting regulations.
- Currency unit.
- Calculation level (line, invoice, settlement).
- Tax and payment rules.

Do not hardcode `setScale(2)` for every monetary value. Retrieve currency scale from a managed domain/configuration and apply the appropriate rule.

### 6.4. Round once at a defined boundary

For example, calculating discounts:
- Compute per line and round each line.
- Sum first and round afterward.
- Round tax per line or across the whole invoice.

These approaches can yield different results. Business rules must define the rounding point and apply it consistently between Java and SQL.

## 7. Controlling precision and overflow

For a `NUMBER(p,s)` column, check both scale and precision before binding.

Example:

```sql
CREATE TABLE app.payment (
    payment_id NUMBER(18,0) PRIMARY KEY,
    amount     NUMBER(12,2) NOT NULL
);
```

`amount` allows at most 10 integer digits and 2 fractional digits.

### 7.1. Normalization and validation helper for NUMBER(p,s)

A simple helper when you want to reject data that requires rounding:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public final class OracleNumberValidator {
    private OracleNumberValidator() {
    }

    public static BigDecimal requireNumber(
            BigDecimal value,
            int precision,
            int scale) {

        if (value == null) {
            throw new IllegalArgumentException("value must not be null");
        }
        if (precision < 1 || precision > 38) {
            throw new IllegalArgumentException("precision must be 1..38");
        }
        if (scale < -84 || scale > 127) {
            throw new IllegalArgumentException("scale must be -84..127");
        }

        BigDecimal normalized =
                value.setScale(scale, RoundingMode.UNNECESSARY);

        if (normalized.precision() > precision) {
            throw new IllegalArgumentException(
                    "value exceeds NUMBER(" + precision + "," + scale + ")"
            );
        }

        return normalized;
    }
}
```

This helper enforces a "do not auto-round" policy. If business rules allow rounding, normalize using the agreed rounding mode before checking precision.

### 7.2. Examples

With `NUMBER(12,2)`:

```java
BigDecimal a = OracleNumberValidator.requireNumber(
    new BigDecimal("1234567890.12"), 12, 2
); // Valid

BigDecimal b = OracleNumberValidator.requireNumber(
    new BigDecimal("12345678901.12"), 12, 2
); // Rejected: precision exceeds limit

BigDecimal c = OracleNumberValidator.requireNumber(
    new BigDecimal("12.345"), 12, 2
); // Rejected: requires rounding
```

### 7.3. Why check precision after setScale?

`NUMBER(p,s)` defines the storage scale. Once scale is normalized, `BigDecimal.precision()` reflects the significant digits in the normalized representation. Comparing against `p` catches overflows.

With negative scale, `setScale(-2, ...)` rounds/normalizes to multiples of 100 before checking precision. Use this only if business logic truly requires negative scale.

### 7.4. The database remains the final safeguard

Java-side validation improves error messages and avoids unnecessary round trips. The database still needs:
- Proper `NUMBER(p,s)` column type.
- `NOT NULL` when required.
- `CHECK` constraints for value ranges.
- Unique/foreign keys when related rules apply.

Never drop database constraints just because the application validates. Batches, jobs, or other applications may write to the same table.

## 8. Rounding in Java and Oracle

Oracle can round values when assigning to a fixed-scale `NUMBER(p,s)` column. For instance, a value with extra decimal digits stored into `NUMBER(8,2)` may be rounded to two decimal places; if precision then exceeds the limit, `ORA-01438` can occur.

To avoid Java and Oracle rounding differently:
1. Choose the business rounding mode.
2. Normalize `BigDecimal` before binding.
3. Bind with `setBigDecimal()`.
4. Keep column DDL precision/scale accurate.
5. Test tie cases, negative numbers, and overflows.

### 8.1. ROUND example

```java
BigDecimal price = new BigDecimal("10.125");

BigDecimal halfUp = price.setScale(2, RoundingMode.HALF_UP);
BigDecimal halfEven = price.setScale(2, RoundingMode.HALF_EVEN);

System.out.println(halfUp);   // 10.13
System.out.println(halfEven); // 10.12
```

Results differ because tie-breaking rules differ. Do not pick a rounding mode based only on one positive example; test negative values too.

### 8.2. ROUND in SQL

Oracle provides the `ROUND(number, integer)` function:

```sql
SELECT ROUND(10.125, 2)
FROM dual;
```

If Java computes part of a calculation and SQL computes another, determine which system is the source of truth for rounding rules. Avoid rounding in both layers with two different policies.

### 8.3. RoundingMode.HALF_EVEN

`HALF_EVEN` rounds ties toward the even last digit. It can reduce cumulative bias in certain calculations, but use it only when business/accounting rules allow it.

### 8.4. RoundingMode.DOWN is not FLOOR

`DOWN` rounds toward zero:
- `1.239` at scale 2 becomes `1.23`.
- `-1.239` at scale 2 becomes `-1.23`.

`FLOOR` rounds toward negative infinity:
- `1.239` at scale 2 becomes `1.23`.
- `-1.239` at scale 2 becomes `-1.24`.

Confusing the two modes causes discrepancies when handling negative numbers.

## 9. BigDecimal operations and MathContext

`BigDecimal` supports addition, subtraction, multiplication, division, and remainder. Every operation requires considering scale and rounding.

### 9.1. Addition and subtraction

```java
BigDecimal subtotal = new BigDecimal("125.50");
BigDecimal discount = new BigDecimal("10.25");

BigDecimal total = subtotal.subtract(discount); // 115.25
```

Result scale normally derives from the scales of the two operands. Normalize at business boundaries when a fixed scale is needed.

### 9.2. Multiplication

```java
BigDecimal unitPrice = new BigDecimal("12.50");
BigDecimal quantity = new BigDecimal("3.000");

BigDecimal lineTotal = unitPrice.multiply(quantity); // 37.50000
```

Multiplication can produce a scale equal to the sum of the two operands' scales. If the target column is `NUMBER(12,2)`, apply rounding/validation rules before saving.

### 9.3. Division

Decimal division can produce non-terminating repeating decimals:

```java
BigDecimal result = new BigDecimal("10")
        .divide(new BigDecimal("3"));
```

This throws `ArithmeticException` because the quotient has no exact finite decimal representation.

Specify scale and rounding explicitly:

```java
BigDecimal result = new BigDecimal("10")
        .divide(new BigDecimal("3"), 4, RoundingMode.HALF_UP);
// 3.3333
```

Or use `MathContext` when business rules define precision by significant digits:

```java
MathContext mc = new MathContext(12, RoundingMode.HALF_EVEN);

BigDecimal result = new BigDecimal("10")
        .divide(new BigDecimal("3"), mc);
```

### 9.4. MathContext vs. scale

`MathContext(12, ...)` limits precision to 12 significant digits. `setScale(2, ...)` requires 2 digits to the right of the decimal point. The two concepts are not interchangeable.

### 9.5. Splitting money and allocating remainders

When splitting a total amount across multiple people or lines, the sum of rounded shares may not equal the original total. Define a remainder allocation rule, e.g.:
- Split proportionally.
- Round each share.
- Compute the remaining difference.
- Allocate the remainder by a deterministic rule so the final sum matches the source total.

Do not discard remainders, as discrepancies accumulate across reports.

## 10. Reading and writing NUMBER with JDBC in real applications

### 10.1. Repository method reading a single value

```java
public BigDecimal findInvoiceTotal(
        DataSource dataSource,
        long invoiceId) throws SQLException {

    String sql = """
        SELECT total_amount
        FROM app.invoice
        WHERE invoice_id = ?
        """;

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setLong(1, invoiceId);

        try (ResultSet resultSet = statement.executeQuery()) {
            if (!resultSet.next()) {
                return null; // Or Optional per repository API
            }

            return resultSet.getBigDecimal("total_amount");
        }
    }
}
```

In production code, distinguish "no row found" from "row has NULL amount". If both cases have distinct meanings, use an explicit result type instead of returning null for both.

### 10.2. Repository method writing a value

```java
public int updateInvoiceTotal(
        DataSource dataSource,
        long invoiceId,
        BigDecimal total) throws SQLException {

    String sql = """
        UPDATE app.invoice
        SET total_amount = ?
        WHERE invoice_id = ?
        """;

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        if (total == null) {
            statement.setNull(1, Types.NUMERIC);
        } else {
            BigDecimal normalized =
                    OracleNumberValidator.requireNumber(total, 12, 2);
            statement.setBigDecimal(1, normalized);
        }

        statement.setLong(2, invoiceId);
        return statement.executeUpdate();
    }
}
```

This example assumes `TOTAL_AMOUNT` is `NUMBER(12,2)`. For a nullable column, null is bound as SQL NULL; if the column is `NOT NULL`, the database will reject it and the application should validate early.

### 10.3. Batch insert

```java
String sql = """
    INSERT INTO app.invoice_line (invoice_id, line_no, amount)
    VALUES (?, ?, ?)
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    connection.setAutoCommit(false);

    for (InvoiceLine line : lines) {
        statement.setLong(1, line.invoiceId());
        statement.setInt(2, line.lineNo());

        BigDecimal amount = OracleNumberValidator.requireNumber(
                line.amount(), 12, 2);

        statement.setBigDecimal(3, amount);
        statement.addBatch();
    }

    int[] counts = statement.executeBatch();
    connection.commit();
}
```

Production code must handle exceptions with rollback and proper resource cleanup. Do not ignore `BatchUpdateException`; a batch can have partial results depending on driver/database, so understand transaction boundaries and commit policy.

### 10.4. CallableStatement and OUT NUMBER

A stored procedure can return `NUMBER`:

```sql
CREATE OR REPLACE PROCEDURE app.get_invoice_total (
    p_invoice_id IN NUMBER,
    p_total OUT NUMBER
) AS
BEGIN
    SELECT total_amount
    INTO p_total
    FROM app.invoice
    WHERE invoice_id = p_invoice_id;
END;
/
```

Java:

```java
try (Connection connection = dataSource.getConnection();
     CallableStatement call = connection.prepareCall(
             "{ call app.get_invoice_total(?, ?) }")) {

    call.setLong(1, invoiceId);
    call.registerOutParameter(2, Types.NUMERIC);
    call.execute();

    BigDecimal total = call.getBigDecimal(2);
}
```

Use `getBigDecimal()` for `NUMBER` OUT parameters to preserve decimals. If the procedure can return NULL, the Java result can also be null.

## 11. Using metadata to inspect column precision and scale

When building generic mappers or schema validation, JDBC metadata can provide precision and scale.

### 11.1. ResultSetMetaData

```java
try (PreparedStatement statement =
             connection.prepareStatement(
                 "SELECT amount FROM app.invoice_line WHERE 1 = 0");
     ResultSet resultSet = statement.executeQuery()) {

    ResultSetMetaData metadata = resultSet.getMetaData();

    int precision = metadata.getPrecision(1);
    int scale = metadata.getScale(1);
    int jdbcType = metadata.getColumnType(1);
    String typeName = metadata.getColumnTypeName(1);
}
```

Metadata lets mappers inspect column type and the precision/scale reported by the driver. Exact metadata values can vary by declaration, driver version, and `NUMBER` columns without `(p,s)`.

### 11.2. DatabaseMetaData.getColumns()

Table metadata can be retrieved:

```java
DatabaseMetaData dbmd = connection.getMetaData();

try (ResultSet columns = dbmd.getColumns(
        connection.getCatalog(),
        "APP",
        "INVOICE_LINE",
        "AMOUNT")) {

    while (columns.next()) {
        String columnName = columns.getString("COLUMN_NAME");
        int dataType = columns.getInt("DATA_TYPE");
        int precision = columns.getInt("COLUMN_SIZE");
        int scale = columns.getInt("DECIMAL_DIGITS");
    }
}
```

Schema/table names usually need to be uppercase when querying Oracle metadata if objects were created with unquoted identifiers. If quoted identifiers were used, pass exact case-sensitive names.

### 11.3. Metadata does not replace schema contracts

Do not rely solely on runtime metadata to decide currency or rounding rules. Schema contracts and domain models must explicitly define numeric meaning. Metadata assists verification and mapping; it does not replace business decisions.

## 12. When to map NUMBER to other Java types?

Not every `NUMBER` needs to stay `BigDecimal` across every layer. However, conversions must be controlled and done only when value ranges fit.

| Oracle column | Java type to consider | Condition |
|---|---|---|
| `NUMBER(5,0)` | `Integer` or `BigDecimal` | Value fits int range with no fractional part |
| `NUMBER(18,0)` | `Long` or `BigDecimal` | Value fits long range |
| `NUMBER(19,0)` | `BigDecimal`/`BigInteger` | Not every 19-digit value fits in `long` |
| `NUMBER(p,s)` with `s > 0` | `BigDecimal` | Exact fractional digits must be preserved |
| Unconstrained `NUMBER` | `BigDecimal` | Precision/scale may vary |
| `BINARY_FLOAT` | `Float` | Binary floating point acceptable |
| `BINARY_DOUBLE` | `Double` | Binary floating point acceptable |

### 12.1. Converting safely to long

```java
long id = decimalValue.longValueExact();
```

`longValueExact()` throws `ArithmeticException` if the value has a fractional part or overflows `long`.

Avoid:

```java
long id = decimalValue.longValue();
```

`longValue()` silently drops fractional digits and loses information on overflow.

### 12.2. Converting safely to int

```java
int count = decimalValue.intValueExact();
```

Use when business logic genuinely requires an integer in the `int` range. Never cast an arbitrary `BigDecimal` to `int`.

### 12.3. BigInteger for very large integers

If a column holds integers that may exceed `long`, use:

```java
BigInteger number = decimalValue.toBigIntegerExact();
```

This throws an error if the number has a non-zero fractional part. For Oracle `NUMBER` columns with scale, still verify domain rules before converting.

## 13. BigDecimal in DTOs and APIs

Keep `BigDecimal` in the domain/repository layers to avoid precision loss. At API boundaries, define serialization explicitly.

### 13.1. JSON numbers can lose precision in consumers

Some JavaScript clients parse JSON numbers into IEEE 754 `Number`. Integers larger than `2^53 - 1` are no longer represented accurately. Decimals such as monetary amounts can also become binary floating point.

Therefore, APIs should consider:
- Returning currency/exact decimal numbers as decimal strings.
- Or explicitly requiring consumers to use a decimal library.
- Documenting scale, currency, and rounding rules.
- Never letting the frontend round based on locale.

JSON string format example:

```json
{
  "amount": "12345678901234567890.12",
  "currency": "VND"
}
```

String format preserves digits, but the API must document it as a decimal string using a dot decimal separator and no thousands separators.

### 13.2. Do not locale-format machine-readable payloads

Do not send `"1.234,56"` or `"1,234.56"` as API values unless the contract explicitly specifies a locale. Machine-readable data should use an invariant format such as `"1234.56"`.

User-facing display formatting can be applied in the UI per locale; storage/transport formats should be locale-independent.

### 13.3. DTOs should not use double if the domain is decimal

```java
public record InvoiceResponse(
        String invoiceId,
        BigDecimal totalAmount,
        String currency
) {}
```

If the serializer or client cannot guarantee exact decimals, use `String totalAmount` in the contract. Align this decision with API consumers and versioning.

## 14. NLS and number-to-string conversions

Oracle sessions have NLS parameters affecting how numbers are parsed/formatted when converted via strings in SQL. For example, decimal separators can vary with `NLS_NUMERIC_CHARACTERS`.

JDBC binding with `BigDecimal` avoids manually constructing numeric strings in SQL:

```java
statement.setBigDecimal(1, amount);
```

Do not do:

```java
String sql = "SELECT * FROM app.invoice WHERE total_amount = "
        + amount.toString();
```

If converting a number to a string in SQL is truly required, specify an explicit format model and NLS parameter:

```sql
SELECT TO_CHAR(
    total_amount,
    'FM9999999990D00',
    'NLS_NUMERIC_CHARACTERS = ''.,'''
)
FROM app.invoice;
```

The format model must fit the actual precision/scale. Do not use a fixed short format string for all values.

### 14.1. Locale in Java

`DecimalFormat` is for locale-aware display; its output should not be used as SQL bind values or canonical decimal payloads. For instance, a locale's decimal comma can be misinterpreted when sent to another system.

Keep `BigDecimal` in the domain and format only for display.

## 15. Data constraints in Oracle

Java validation provides early feedback, but Oracle must act as the final safeguard so every client obeys the same rules.

### 15.1. NUMBER(p,s) and NOT NULL

```sql
CREATE TABLE app.payment (
    payment_id NUMBER(18,0) PRIMARY KEY,
    amount NUMBER(12,2) NOT NULL,
    currency_code VARCHAR2(3) NOT NULL
);
```

`NUMBER(12,2)` bounds precision/scale. `NOT NULL` prevents SQL NULL values.

### 15.2. CHECK constraints

```sql
ALTER TABLE app.payment
ADD CONSTRAINT payment_amount_nonnegative_ck
CHECK (amount >= 0);
```

Constraints protect data whether writes come from JDBC, SQL*Plus, batch jobs, or another application.

### 15.3. Distinguishing NULL and zero

```sql
SELECT COUNT(*) AS total_rows,
       COUNT(amount) AS non_null_amounts,
       SUM(amount) AS total_amount
FROM app.payment;
```

`COUNT(amount)` skips NULL; `SUM` also skips NULL and returns NULL if no valid values exist. Do not replace NULL with 0 when business logic needs to distinguish "unknown" from "zero money".

### 15.4. Numeric domain constraints

Beyond precision/scale, define:
- Whether negative values are valid.
- Valid range for rates.
- Whether quantities allow fractions.
- Minimum/maximum values.
- Whether zero is permitted.
- Whether currency/unit must accompany the value.

Use appropriate CHECK constraints and domain validation.

## 16. Common mistakes when mapping numbers

| Mistake | Consequence | Resolution |
|---|---|---|
| `getDouble()` for monetary NUMBER columns | Binary floating-point error | Use `getBigDecimal()` |
| `setDouble()` to write NUMBER | May store approximate value | Use `setBigDecimal()` |
| `new BigDecimal(0.1)` | Imports double error into decimal | Use string or decimal source |
| `BigDecimal.equals()` to compare numbers | Different scales treated as unequal | Use `compareTo()` for numerical comparison |
| Forgetting to capture `add()`/`multiply()` result | BigDecimal stays unchanged | Assign the returned value |
| `divide()` without rounding | ArithmeticException on repeating decimals | Specify scale/rounding or MathContext |
| `setScale()` without rounding mode | May fail or leave policy unclear | Specify RoundingMode explicitly |
| Using `DOWN` instead of `FLOOR` | Negative numbers yield different results | Choose the right rounding direction |
| `longValue()` on arbitrary numbers | Loses fractions or overflows | Use `longValueExact()` |
| Concatenating numbers into SQL | NLS/parsing/security issues | Bind with PreparedStatement |
| Treating NULL as zero | Broken business semantics | Preserve null or handle explicitly |
| Using scale 2 for every currency | Violates currency rules | Determine scale by currency/domain |
| Validating only in Java | Other clients can write invalid data | Enforce constraints in the database |
| Uncontrolled BigDecimal JSON number serialization | Consumers may parse as double and lose precision | Specify decimal strings or decimal-aware consumers |

## 17. Handling Oracle precision-related errors

### 17.1. ORA-01438

`ORA-01438: value larger than specified precision allowed for this column` occurs when a value exceeds a `NUMBER(p,s)` column's precision after scale rules apply.

Investigate:
- Value before binding.
- `precision()` and `scale()` of the BigDecimal.
- Column DDL.
- Whether rounding occurred before writing.
- Whether the value was computed in Java or SQL.
- Schema differences across environments.

Do not resolve this by silently increasing precision without assessing business ranges and storage/API impact.

### 17.2. ORA-01426

`ORA-01426: numeric overflow` can occur when a numeric operation exceeds Oracle's range. Check expressions, data types, intermediate results, and casts.

### 17.3. ORA-06502

`ORA-06502: PL/SQL numeric or value error` can appear when assigning a value to a PL/SQL variable with insufficient precision/scale or invalid conversion.

Inspect PL/SQL variable declarations, procedure parameters, and target columns.

### 17.4. Catching SQLException

```java
try {
    statement.executeUpdate();
} catch (SQLException e) {
    int oracleCode = e.getErrorCode();
    String sqlState = e.getSQLState();

    // Log error code and non-sensitive context.
    // Do not log full payloads or credentials.
    throw e;
}
```

With Oracle JDBC, `getErrorCode()` returns the vendor error code. Do not rely solely on parsing message text, as messages vary by language/driver. Also inspect exception chains and batch update exceptions.

## 18. Testing precision and scale

Testing with H2 or mocks helps verify Java logic, but it does not replace integration tests against the actual Oracle Database and Oracle JDBC driver. NUMBER semantics, rounding, metadata, and driver mappings must be tested in the matching environment.

### 18.1. Test value suite

For a `NUMBER(12,2)` column, test:

| Input | Purpose |
|---|---|
| `0` | Zero |
| `0.01` | Smallest value at scale 2 |
| `-0.01` | Negative value |
| `9999999999.99` | Valid upper bound |
| `10000000000.00` | Exceeds precision |
| `12.3` | Normalized with trailing zero |
| `12.340` | Extra trailing zero |
| `12.345` | Requires rounding or rejection |
| `-12.345` | Rounding negative number |
| SQL NULL | Null mapping |

### 18.2. Round-trip test

Round-trip test:
1. Construct `BigDecimal` from a decimal string.
2. Bind to a NUMBER column using `setBigDecimal`.
3. Commit.
4. Read back with `getBigDecimal`.
5. Compare values per the defined scale rules.

Example:

```java
BigDecimal input = new BigDecimal("12345.67");

try (PreparedStatement insert = connection.prepareStatement(
        "INSERT INTO app.number_test(id, amount) VALUES (?, ?)")) {
    insert.setLong(1, 1L);
    insert.setBigDecimal(2, input);
    insert.executeUpdate();
}

try (PreparedStatement query = connection.prepareStatement(
        "SELECT amount FROM app.number_test WHERE id = ?")) {
    query.setLong(1, 1L);

    try (ResultSet rs = query.executeQuery()) {
        if (rs.next()) {
            BigDecimal actual = rs.getBigDecimal(1);
            if (actual.compareTo(input) != 0) {
                throw new AssertionError("Decimal round trip mismatch");
            }
        }
    }
}
```

In real tests, manage transactions/rollbacks and isolated test data to avoid lock contention.

### 18.3. Testing rounding boundaries

Test:
- Value just below midpoint.
- Exact midpoint value.
- Value just above midpoint.
- Same three cases for negative numbers.
- All rounding modes permitted by business rules.

Example for scale 2: `1.234`, `1.235`, `1.236`, and `-1.235`.

### 18.4. Testing concurrency and batching

For batch inserts/updates:
- Verify every bind parameter preserves decimals.
- Check `BatchUpdateException`.
- Verify rollback when part of a batch fails per transaction policy.
- Ensure retries do not create duplicate records.
- Verify data read back after commit.

### 18.5. Testing NLS

Run tests with sessions using different `NLS_NUMERIC_CHARACTERS`. With `setBigDecimal`, numeric results should not depend on client comma/dot formatting. If an application manually builds SQL literals from strings, tests can uncover NLS-dependent bugs.

## 19. Oracle JDBC implementation checklist

### Schema
- DDL declares appropriate precision/scale.
- `NOT NULL`/`CHECK` constraints exist where business rules require.
- Distinguished `NUMBER`, `BINARY_FLOAT`, and `BINARY_DOUBLE`.
- Schema metadata verified across environments.

### Java
- `BigDecimal` used for Oracle `NUMBER` requiring precision.
- Never construct `BigDecimal` from `double` when exact decimals are needed.
- Operations capture return values because BigDecimal is immutable.
- Explicit rounding modes defined.
- Division uses appropriate scale/MathContext.
- Conversions to primitives use exact conversion methods.
- NULL distinguished from zero.

### JDBC
- `getBigDecimal()` used for reading.
- `setBigDecimal()` used for binding.
- `setNull(..., Types.NUMERIC)` used for null.
- PreparedStatement used; numbers never concatenated into SQL.
- OUT parameters and batch mappings verified.
- Compatible driver version used.

### API and testing
- Decimal serialization defined explicitly.
- Consumers do not accidentally parse exact numbers into double.
- Round-trip integration tests against Oracle exist.
- Boundary, rounding, negative, null, and NLS tests exist.
- Precision/overflow error tests exist.
- Java and SQL results reconciled under the same rules.

## 20. Comprehensive hands-on lab

This lab uses a dedicated schema and an Oracle database with a compatible JDBC driver. Never run DDL on business schemas.

### Step 1. Create the test table

```sql
CREATE TABLE app.number_precision_lab (
    id NUMBER(10,0) PRIMARY KEY,
    amount NUMBER(12,2),
    rate NUMBER(8,6),
    rounded_hundred NUMBER(8,-2)
);
```

### Step 2. Insert values from SQL to understand schema behavior

```sql
INSERT INTO app.number_precision_lab
    (id, amount, rate, rounded_hundred)
VALUES
    (1, 12345.67, 0.123456, 12345);

COMMIT;
```

Read back and observe storage scale:

```sql
SELECT id,
       amount,
       rate,
       rounded_hundred,
       DUMP(amount)
FROM app.number_precision_lab
WHERE id = 1;
```

### Step 3. Write JDBC insert

Use `PreparedStatement.setBigDecimal()` for `amount`, `rate`, and `rounded_hundred`. Construct inputs using the string constructor.

### Step 4. Read with getBigDecimal

Read back the columns and print:
- `toPlainString()`
- `precision()`
- `scale()`

Do not use `double` to print or compare values.

### Step 5. Test values needing rounding

Write `12.345` to the `NUMBER(12,2)` column:
- Once validating with `UNNECESSARY` to confirm rejection.
- Once normalizing with the chosen rounding mode and binding.
- Read back to compare against the expected value.

### Step 6. Test overflow

Try a value whose integer part exceeds `NUMBER(12,2)` limits. Verify the Java validator catches it before sending SQL. Then in a separate test, bypass the validator to observe the database error.

### Step 7. Test null

Bind SQL NULL using `setNull(..., Types.NUMERIC)`, read back with `getBigDecimal()`, and confirm the Java result is null.

### Step 8. Inspect metadata

Use `ResultSetMetaData` or `DatabaseMetaData.getColumns()` to inspect precision, scale, and type name of each column. Compare across driver versions if the application supports multiple environments.

### Step 9. Reconcile Java and Oracle

Evaluate an expression in Java using `BigDecimal`, evaluate the same expression in SQL using `NUMBER`, and compare. Clearly identify rounding points on each side.

### Step 10. Clean up the lab

Drop the test table only when certain the data is no longer needed:

```sql
DROP TABLE app.number_precision_lab PURGE;
```

Never run cleanup commands on business tables.

## 21. Self-check questions

**Question 1.** Which Java type should Oracle `NUMBER` map to when decimal precision is required?

**Answer:** `java.math.BigDecimal`.

**Question 2.** How do precision and scale differ?

**Answer:** Precision is the total number of significant digits; scale is the number of digits to the right of the decimal point and can be negative.

**Question 3.** Why should `getDouble()` not be used for monetary values in NUMBER?

**Answer:** `double` is binary floating point, cannot represent many decimals accurately, and introduces calculation errors.

**Question 4.** Why is `new BigDecimal(0.1)` discouraged?

**Answer:** It converts the approximate binary floating-point value of `0.1` into decimal, carrying binary error.

**Question 5.** Which API is used to read NUMBER?

**Answer:** `ResultSet.getBigDecimal()`.

**Question 6.** Which API is used to bind BigDecimal?

**Answer:** `PreparedStatement.setBigDecimal()`.

**Question 7.** How do `BigDecimal.equals()` and `compareTo()` differ?

**Answer:** `equals()` checks scale as well; `compareTo()` compares numerical value.

**Question 8.** What does `setScale(2, UNNECESSARY)` do?

**Answer:** Normalizes to scale 2 while throwing an error if rounding would discard information.

**Question 9.** How do HALF_UP and HALF_EVEN differ?

**Answer:** At exact midpoints, HALF_UP rounds away from zero; HALF_EVEN picks the result with an even trailing digit.

**Question 10.** What does `MathContext` control?

**Answer:** Precision by significant digits and rounding mode, not a fixed number of decimal places.

**Question 11.** Why can BigDecimal division throw ArithmeticException?

**Answer:** The quotient may be a repeating infinite decimal that cannot be represented exactly without specifying scale/rounding or MathContext.

**Question 12.** How do you safely convert BigDecimal to long?

**Answer:** Use `longValueExact()` to detect fractional parts or overflows.

**Question 13.** What should you do when binding SQL NULL for NUMBER?

**Answer:** Use `setNull(index, Types.NUMERIC)` and keep NULL semantics distinct from zero.

**Question 14.** Why check precision after setScale?

**Answer:** Because `NUMBER(p,s)` applies scale before enforcing the total significant digit limit.

**Question 15.** What does ORA-01438 usually indicate?

**Answer:** A value exceeds the declared column precision after applying scale.

**Question 16.** Why are database constraints still necessary even when Java validates?

**Answer:** Multiple clients or transactions can write concurrently; the database enforces integrity across all write paths.

**Question 17.** Do JSON numbers always preserve BigDecimal?

**Answer:** No. Some consumers, especially JavaScript Number, convert to binary floating point and lose precision; APIs may need decimal strings.

**Question 18.** Which tests are essential for NUMBER mapping?

**Answer:** Round-trip, precision boundary, scale, midpoint rounding, negative numbers, null, overflow, batching, and NLS tests.

## 22. Conclusion

Oracle `NUMBER` is a decimal type capable of exact numeric representation within database limits; Java `BigDecimal` is the matching type for reading, computing, and writing those values. Use `ResultSet.getBigDecimal()` and `PreparedStatement.setBigDecimal()` to keep decimals intact across JDBC. Avoid converting through `double` or `float` when data requires exact reconciliation, and never construct `BigDecimal` from a `double` that already carries binary error.

Precision and scale must be treated as part of the data contract. For `NUMBER(p,s)`, normalize scale per business rules, validate precision, choose an explicit rounding mode, and let database constraints guard every write path. Distinguish `equals()` from `compareTo()`, `MathContext` from scale, SQL NULL from zero, and convert to primitives with exact conversion methods when needed.

A reliable implementation requires round-trip integration tests on a real Oracle JDBC driver covering precision boundaries, scale, rounding, negative numbers, nulls, overflows, and NLS. APIs must also specify decimal serialization so consumers do not inadvertently convert values into floating point. Only when Java and Oracle enforce a single clear decimal contract can numeric data remain consistent from input through storage, retrieval, calculation, and cross-system exchange.
