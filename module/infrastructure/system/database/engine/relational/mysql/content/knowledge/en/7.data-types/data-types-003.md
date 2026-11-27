# DECIMAL vs. FLOAT/DOUBLE and Monetary Data Precision

## Objectives

After this lesson, you will be able to:

- Distinguish the exact numeric type `DECIMAL` from the approximate floating-point types `FLOAT` and `DOUBLE`.
- Explain why many decimal numbers, such as `0.1`, cannot be represented accurately in binary floating-point.
- Choose precision and scale for currency, quantity, tax, and exchange rate columns.
- Calculate, round, and aggregate monetary amounts with consistent rules in MySQL.
- Map `DECIMAL` to `BigDecimal` in Java and avoid introducing floating-point errors into financial data.
- Plan migrations from `FLOAT`/`DOUBLE` columns to `DECIMAL` without masking historical data discrepancies.

## 1. Why Numeric Data Types Matter for Money

A retail system may calculate product prices, discounts, taxes, shipping fees, payments, and refunds. These calculations are often summed across thousands or millions of transactions. A tiny error in a single calculation can accumulate or cause mismatches during reconciliation.

MySQL offers two common numeric groups:

- **Exact-value numbers:** `INTEGER`, `BIGINT`, `DECIMAL`, and related types. `DECIMAL` stores numbers in decimal digits with a specified precision/scale.
- **Approximate-value numbers:** `FLOAT` and `DOUBLE`. They use binary floating-point representation, suitable for wide dynamic ranges and scientific computing, but many decimal fractions cannot be represented accurately.

For account balances, selling prices, invoice amounts, taxes, or payment amounts, you should typically use `DECIMAL` or an integer representation in the smallest currency unit. `FLOAT`/`DOUBLE` are better suited for sensor measurements, simulations, and scientific calculations where approximation error is acceptable.

## 2. How DECIMAL, FLOAT, and DOUBLE Differ

| Type | Representation | Characteristics | Common Use Cases |
|---|---|---|---|
| `DECIMAL(M,D)` | Exact decimal number with specified total digits and fractional digits | Stored and computed in decimal; avoids binary representation errors for standard decimal fractions | Currency, taxes, rates requiring exact rules, accounting figures |
| `FLOAT` | Single-precision binary floating-point | Approximate, limited precision, typically smaller storage than DOUBLE | Measurements or scientific models needing wide range |
| `DOUBLE` | Double-precision binary floating-point | Approximate, higher precision than FLOAT but still cannot represent every decimal fraction exactly | Scientific computing, statistics, data where approximation error is acceptable |

In MySQL, `FLOAT` typically uses 4 bytes and `DOUBLE` typically uses 8 bytes. `DECIMAL` uses a packed decimal representation whose size depends on precision and scale. Do not choose a type based solely on byte count; consider precision requirements, value domains, and workload.

### 2.1. Precision and Scale of DECIMAL

Syntax:

```sql
DECIMAL(M, D)
```

- `M` (*precision*) is the maximum total number of digits, including both integer and fractional parts.
- `D` (*scale*) is the maximum number of digits to the right of the decimal point.
- The integer part has at most `M - D` digits.
- In MySQL, the maximum precision of `DECIMAL` is 65 digits; the maximum scale is 30 and cannot exceed precision.

Examples:

| Type | Max Integer Digits | Fractional Digits | Maximum Positive Value |
|---|---:|---:|---:|
| `DECIMAL(8,2)` | 6 | 2 | `999999.99` |
| `DECIMAL(12,2)` | 10 | 2 | `9999999999.99` |
| `DECIMAL(19,4)` | 15 | 4 | `999999999999999.9999` |
| `DECIMAL(10,6)` | 4 | 6 | `9999.999999` |

Choose `M` based on the maximum value the business can reach, accounting for totals, balances, quantities, and future growth. Choose `D` based on the required storage precision. `DECIMAL(19,2)` does not mean 19 integer digits; it has 17 integer digits and 2 fractional digits.

### 2.2. Why Do FLOAT/DOUBLE Have Rounding Errors?

Computers represent `FLOAT` and `DOUBLE` in base 2. Some decimal fractions have non-terminating repeating binary representations, much like (1/3) has the decimal representation `0.3333...`. Since the system must store a finite number of bits, the value is rounded to the nearest representable binary floating-point number.

Illustrative example in MySQL:

```sql
SELECT
    CAST('0.1' AS DOUBLE) + CAST('0.2' AS DOUBLE) AS approximate_sum,
    CAST('0.1' AS DECIMAL(3,1)) + CAST('0.2' AS DECIMAL(3,1)) AS exact_sum;
```

The `approximate_sum` column may display a value very close to `0.3`, such as `0.30000000000000004`, depending on client formatting. The `exact_sum` column preserves the exact decimal result `0.3` within the expression's precision/scale.

In MySQL, decimal literals like `0.1` are treated as exact values; literals in scientific notation like `0.1E0` are approximate values. When testing behavior, pay attention to operand types rather than just how the client formats numbers.

```sql
-- Exact decimal literal values
SELECT 0.1 + 0.2 AS exact_literal_sum;

-- Scientific notation literals are approximate values
SELECT 0.1E0 + 0.2E0 AS approximate_literal_sum;
```

Avoid using exact equality (`=`) on `FLOAT`/`DOUBLE` results when business logic needs to check close values. If approximate types are required, define an acceptable tolerance and compare within that tolerance. For money, the better solution is usually to store and compute with exact types from the start.

## 3. Choosing DECIMAL for Monetary Data

### 3.1. Determine Currency Units and Fractional Digits

Not all currencies share the same number of fractional digits. Some currencies use 0 decimal places in their minor unit, many use 2, and some use 3. Additionally, a system may need to store intermediate values or exchange rates with higher precision than the final payment amount.

Before designing columns, determine:

1. Is money stored in major units (e.g., USD) or minor units (e.g., cents)?
2. Which currency codes does the system support, and what are the fractional digit rules for each currency?
3. How many fractional digits do unit prices, exchange rates, taxes, and final amounts require?
4. Are calculations rounded at the line level, invoice level, or payment total level?
5. What are the maximum values for a line item, an invoice, an account balance, and a transaction total?

For a system handling only 2-decimal-place currencies, you might start with `DECIMAL(19,2)` for amounts. If exchange rates or intermediate values require more digits, use a larger scale, such as `DECIMAL(20,10)` for exchange rates, and then apply rounding rules when converting to the payable amount. These are design examples; actual precision/scale must come from business limits.

### 3.2. Store Currency Codes Alongside Amounts

An amount lacks full meaning without its currency. `100.00` could be 100 USD, 100 EUR, or 100 units of another currency. Therefore, store an explicit currency code alongside the amount:

```sql
CREATE TABLE payments (
    payment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    currency_code CHAR(3) NOT NULL,
    amount DECIMAL(19,2) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (payment_id),
    KEY idx_currency_created (currency_code, created_at)
) ENGINE = InnoDB;
```

Sample data:

```sql
INSERT INTO payments (currency_code, amount, created_at)
VALUES
    ('USD', 125.50, '2026-01-10 09:00:00'),
    ('EUR', 89.99, '2026-01-10 09:05:00');
```

Never sum amounts across different currencies as if they share the same unit. To aggregate, group by currency or convert using a clearly defined exchange rate along with its timestamp and rate source.

### 3.3. Choosing Between DECIMAL and Integer Minor Units

Another approach is storing monetary amounts as integers in the smallest currency unit. For example, `12345` represents 123.45 USD when the convention is cents.

| Storage Approach | Advantages | Limitations |
|---|---|---|
| `DECIMAL(19,2)` | Human-readable, represents money directly; SQL computes with exact decimal arithmetic | Must explicitly define scale and rounding rules |
| `BIGINT` in minor units | Exact and simple integer addition/subtraction; useful for currencies with fixed decimal places | Must know each currency's minor unit exponent; multiplication/division and FX require custom scale handling; risk of integer overflow |

If the system supports multiple currencies, varying fractional digits, or intermediate calculations, `DECIMAL` is usually easier to express. If choosing integers, store or enforce each currency's unit convention reliably; never assume every currency divides by 100.

## 4. Designing Precision/Scale for Prices, Quantities, Taxes, and Exchange Rates

Fields serving different purposes do not necessarily share the same scale.

| Quantity | Example Data Type | Reason |
|---|---|---|
| Payable amount in a 2-decimal currency | `DECIMAL(19,2)` | Stores final amount in standard minor units |
| Unit price that may have more fractional digits | `DECIMAL(19,4)` or business-defined scale | Avoids premature rounding of unit prices |
| Item quantity with fractional units | `DECIMAL(12,3)` | Supports kg, liters, or fractional measurement units |
| Percentage rate | `DECIMAL(9,6)` | Keeps enough digits for rates depending on domain |
| Foreign exchange rate | `DECIMAL(20,10)` | Preserves higher precision than final amounts |
| Final tax amount | Scale per currency, e.g. `DECIMAL(19,2)` | Rounded per tax and currency rules |

Do not copy example types blindly into every system. Very small unit prices, large quantities, or specialized exchange rates may require different precision. Calculate the maximum value of intermediate expressions, not only of a single column.

The simple schema below assumes the currency stored in `line_total` has 2 decimal places. If supporting currencies with different scale rules, store per-currency rules and adjust scale/rounding when computing final amounts.

```sql
CREATE TABLE invoice_lines (
    line_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    currency_code CHAR(3) NOT NULL,
    unit_price DECIMAL(19,4) NOT NULL,
    quantity DECIMAL(12,3) NOT NULL,
    tax_rate DECIMAL(9,6) NOT NULL,
    line_total DECIMAL(19,2) NOT NULL,
    PRIMARY KEY (line_id),
    KEY idx_currency (currency_code)
) ENGINE = InnoDB;
```

In this model, `unit_price`, `quantity`, and `tax_rate` are calculation inputs; `line_total` is the amount rounded per currency policy. Real-world systems may also need to store subtotal, discount, tax amount, total, and rounding adjustments separately to explain how the final figure was derived.

## 5. Arithmetic and Rounding in MySQL

### 5.1. Keep Calculations in Exact Types

MySQL evaluates arithmetic on exact and approximate values according to data type rules. When operands are `DECIMAL` or integers, the results of many operations remain exact within MySQL's supported precision/scale limits. Once `FLOAT`/`DOUBLE` enters an expression, the result can become approximate.

Example calculating a line total:

```sql
SELECT
    CAST('19.99' AS DECIMAL(10,2)) * 3 AS exact_line_amount,
    CAST('19.99' AS DOUBLE) * 3 AS approximate_line_amount;
```

Keep monetary values in `DECIMAL` throughout the calculation pipeline. Do not convert to `DOUBLE` just to multiply or sum.

### 5.2. Define the Rounding Point

Rounding is a business decision. For example, a system might round each line item and then sum them, or sum unrounded values and round once at the invoice level. The two methods can yield different totals.

Suppose three lines have unrounded amounts of 0.335, 0.335, and 0.335 in a 2-decimal currency:

- Round per line: 0.34 + 0.34 + 0.34 = 1.02.
- Sum first, then round: 0.335 + 0.335 + 0.335 = 1.005, which rounds to 1.01 under MySQL's half-away-from-zero rule for exact values.

The results differ by one minor unit. The system must select and consistently enforce one policy aligned with contracts, accounting/tax regulations, and reconciliation requirements.

### 5.3. ROUND and TRUNCATE

Example:

```sql
SELECT
    ROUND(CAST('12.345' AS DECIMAL(8,3)), 2) AS rounded_value,
    TRUNCATE(CAST('12.349' AS DECIMAL(8,3)), 2) AS truncated_value;
```

- `ROUND(value, d)` rounds to `d` fractional digits.
- `TRUNCATE(value, d)` drops digits beyond the specified scale without rounding up.

For exact values, MySQL rounds exact midpoints away from zero (*half away from zero*). For approximate values, the result depends on the platform's math library and may vary. Therefore, if financial policy requires deterministic rounding, convert to `DECIMAL` before rounding and test both positive and negative numbers.

### 5.4. Check Digits When Writing to Columns

When storing a value with more fractional digits than the column's scale, MySQL converts the value to the column's scale according to rounding rules. For example, a `DECIMAL(8,2)` column stores only 2 fractional digits:

```sql
CREATE TABLE decimal_rounding_demo (
    amount DECIMAL(8,2) NOT NULL
) ENGINE = InnoDB;

INSERT INTO decimal_rounding_demo (amount)
VALUES (12.345);

SELECT amount
FROM decimal_rounding_demo;
```

The value is stored at scale 2. For values exceeding the precision range, the outcome may be an error or a warning depending on SQL mode and context. Check `SHOW WARNINGS`, `@@sql_mode`, and test boundary values before bulk loading.

```sql
-- Run immediately after INSERT/UPDATE/DDL to inspect warnings
SHOW WARNINGS;

-- View the current session SQL mode
SELECT @@SESSION.sql_mode;
```

Do not treat MySQL's implicit rounding on column write as an unspoken financial policy. Round explicitly at the right business step, document the rule, and verify the result before persisting.

### 5.5. SUM and AVG with DECIMAL

MySQL returns `DECIMAL` for `SUM()` and `AVG()` when the argument is an exact-value type; if the argument is `FLOAT` or `DOUBLE`, the result is approximate. This is an important reason to store amounts as `DECIMAL` from the outset.

```sql
SELECT
    currency_code,
    SUM(amount) AS total_amount,
    AVG(amount) AS average_amount
FROM payments
GROUP BY currency_code;
```

The query groups by currency to avoid summing different monetary units. When reporting at a specific scale, apply `CAST` or `ROUND` explicitly after confirming the rounding policy.

## 6. Working with DECIMAL in Java

In Java, the appropriate type for SQL `DECIMAL` is `java.math.BigDecimal`. `BigDecimal` supports exact decimal arithmetic and explicit scale. Avoid using `float` or `double` as an intermediate representation for money.

### 6.1. Constructing BigDecimal Properly

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal price = new BigDecimal("19.99");
BigDecimal quantity = BigDecimal.valueOf(3);

BigDecimal subtotal = price.multiply(quantity);
BigDecimal total = subtotal.setScale(2, RoundingMode.HALF_UP);

System.out.println(total); // 59.97
```

Prefer the `String` constructor or `BigDecimal.valueOf(long)` for integer inputs. `BigDecimal.valueOf(double)` can help when receiving an existing `double`, but it does not turn an approximate floating-point calculation into exact monetary math. Do not write:

```java
BigDecimal unsafe = new BigDecimal(0.1);
```

The `double` constructor preserves the exact approximate binary value held by the `double`; it does not recover the original decimal intent of `0.1`. Use:

```java
BigDecimal safe = new BigDecimal("0.1");
```

### 6.2. Division and Rounding

Decimal division can produce a non-terminating decimal, such as 1 divided by 3. `BigDecimal.divide()` without a scale or rounding mode throws `ArithmeticException` if the quotient has no finite decimal representation.

```java
BigDecimal amount = new BigDecimal("100.00");
BigDecimal rate = new BigDecimal("3");

BigDecimal converted = amount.divide(
    rate,
    2,
    RoundingMode.HALF_UP
);
```

`HALF_UP` is only an example. Depending on policy, you may use `HALF_EVEN`, `DOWN`, `CEILING`, or another rule. Do not pick a rounding mode out of developer habit; align it with business requirements.

### 6.3. Comparing BigDecimal

`BigDecimal.equals()` compares both value and scale. Thus, `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` returns `false`, even though both numbers have the same numeric value. Use `compareTo()` when comparing numeric value:

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

boolean sameNumericValue = a.compareTo(b) == 0;
```

If scale carries meaning in business logic or currency formatting, check scale separately. Do not confuse numeric comparison with representation comparison.

### 6.4. Reading and Writing DECIMAL via JDBC

Use `setBigDecimal()` for writing and `getBigDecimal()` for reading:

```java
String sql = "INSERT INTO payments (currency_code, amount, created_at) "
           + "VALUES (?, ?, NOW())";

try (var statement = connection.prepareStatement(sql)) {
    statement.setString(1, "USD");
    statement.setBigDecimal(2, new BigDecimal("125.50"));
    statement.executeUpdate();
}

try (var statement = connection.prepareStatement(
        "SELECT amount FROM payments WHERE payment_id = ?")) {
    statement.setLong(1, paymentId);
    try (var result = statement.executeQuery()) {
        if (result.next()) {
            BigDecimal amountFromDb = result.getBigDecimal("amount");
        }
    }
}
```

Prepared statements pass values with the right types and avoid SQL string concatenation. Do not read `DECIMAL` via `getDouble()` if the application must preserve exact monetary amounts.

## 7. Avoiding Errors in Totals and Currency Conversions

A payment processing pipeline should clearly define its steps:

1. Read prices and quantities from exact types.
2. Compute subtotal, discount, and tax using `DECIMAL`/`BigDecimal` with sufficient precision.
3. Choose the rounding point according to business rules.
4. Store the final amount together with its currency code.
5. When converting currencies, store the exchange rate, rate source, effective timestamp, and converted amount.

Example schema for storing conversion transactions:

```sql
CREATE TABLE currency_conversions (
    conversion_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_currency CHAR(3) NOT NULL,
    target_currency CHAR(3) NOT NULL,
    source_amount DECIMAL(19,2) NOT NULL,
    exchange_rate DECIMAL(20,10) NOT NULL,
    target_amount DECIMAL(19,2) NOT NULL,
    rate_at DATETIME NOT NULL,
    rate_source VARCHAR(100) NOT NULL,
    PRIMARY KEY (conversion_id)
) ENGINE = InnoDB;
```

This schema persists the exchange rate and converted result so transactions can be audited later. You must define whether the rate represents how many target units per one source unit or vice versa, as well as how `target_amount` is rounded. You cannot infer conversion direction merely by looking at two currency codes and a rate.

Avoid common mistakes:

- Summing amounts across multiple currencies without converting.
- Using `DOUBLE` for amounts and casting to `DECIMAL` at the end.
- Rounding unit prices too early before multiplying by quantity.
- Rounding both lines and invoices using two conflicting rules unintentionally.
- Using the current exchange rate to recompute a historical transaction instead of the rate applied at transaction time.
- Using insufficient precision so that sums over many rows overflow the domain.

## 8. Finding and Fixing Designs Using FLOAT/DOUBLE for Money

If an existing system stores money using `FLOAT` or `DOUBLE`, do not simply run `ALTER TABLE ... MODIFY amount DECIMAL(...)` and assume the original data has been recovered accurately. Legacy binary values may already have lost precision from the original decimal numbers; casting only converts the stored binary value to decimal per conversion rules.

Assessment process:

1. Identify all columns and expressions using `FLOAT`/`DOUBLE` for prices, taxes, fees, balances, or payments.
2. Sample real values, including negative numbers, very small numbers, large values, values with many fractional digits, and edge cases.
3. Reconcile against authoritative source records such as orders, invoices, payment files, or transaction logs if still available.
4. Define scale and rounding mode per business rules; do not infer scale solely from currently displayed digits.
5. Add a new `DECIMAL` column or staging table; convert according to approved rules.
6. Compare before/after values, aggregates by date/currency, and verify critical transactions.
7. Switch the application to read/write `BigDecimal`, test thoroughly, and then cut over and drop the old column via migration procedures.

Illustrative example copying test data to a new column:

```sql
ALTER TABLE legacy_payments
ADD COLUMN amount_decimal DECIMAL(19,2) NULL;

UPDATE legacy_payments
SET amount_decimal = ROUND(amount_double, 2)
WHERE amount_decimal IS NULL;
```

This is only a technical example. `ROUND(amount_double, 2)` does not accurately recover what a user originally entered if the underlying data was stored in approximate binary form. Use this conversion only after deciding that rounding to two decimal places is the right policy and reconciling against authoritative sources.

After verification, you can confirm converted values:

```sql
SELECT
    COUNT(*) AS total_rows,
    SUM(amount_decimal IS NULL) AS missing_converted_amounts,
    MIN(amount_decimal) AS min_amount,
    MAX(amount_decimal) AS max_amount,
    SUM(amount_decimal) AS total_amount
FROM legacy_payments;
```

Reconcile totals by the same currency and the same transaction set. Do not compare totals across different currencies or compare data pulled at different times with new incoming transactions without a consistent snapshot.

## 9. Checking Precision, Scale, and Limits

Before creating a column, calculate its maximum value domain. For example, if an amount can reach up to 12 integer digits and needs 2 fractional digits, `DECIMAL(14,2)` provides 14 total digits. If growth headroom is needed, choose a higher precision still within MySQL limits.

Inspect column type and metadata:

```sql
SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    NUMERIC_PRECISION,
    NUMERIC_SCALE,
    IS_NULLABLE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'payments'
  AND COLUMN_NAME = 'amount';
```

Check SQL mode to understand how the server handles out-of-range data or conversions:

```sql
SELECT @@SESSION.sql_mode;
```

Do not rely on the server emitting warnings or adjusting values as an excuse to skip application input validation. Validate data in the application layer, use wide-enough column types, and monitor write errors.

### 9.1. Avoiding Overflow in Intermediate Expressions

A column may fit its own domain while multiplication or summing across many rows produces a larger result. For example, unit price multiplied by a large quantity or the sum of millions of transactions can exceed expected precision.

Calculate bounds for:

- Maximum value of a single line.
- Maximum quantity multiplied by maximum unit price.
- Total amount of a single invoice.
- Total balance or revenue across the entire system.
- Exchange rates and converted results.

Verify the return types of expressions and aggregates in your MySQL version. If necessary, apply explicit `CAST(... AS DECIMAL(p,s))` at calculation boundaries, choosing a precision large enough for intermediate results before rounding to the final storage scale.

### 9.2. Indexing DECIMAL Columns

`DECIMAL` can be indexed like other suitable InnoDB column types. Example:

```sql
CREATE INDEX idx_payments_currency_amount
ON payments (currency_code, amount);
```

An index helps when queries filter by currency and amount ranges. However, do not create an index merely because a column is `DECIMAL`; base it on filter predicates, sort order, and real workloads. Avoid wrapping indexed columns in functions or unnecessary casts in filter conditions if doing so prevents the optimizer from using the index.

## 10. Monetary Data Design Checklist

- [ ] Monetary amounts use `DECIMAL` or a standardized integer minor-unit convention.
- [ ] Every amount is paired with an explicit currency code.
- [ ] Precision covers maximum single values and cumulative sums.
- [ ] Scale reflects currency rules and required precision for prices, exchange rates, and taxes.
- [ ] Rounding rules and rounding points are defined.
- [ ] Amounts are never cast to `FLOAT`/`DOUBLE` in SQL or Java.
- [ ] Java applications use `BigDecimal`, JDBC `setBigDecimal()`, and `getBigDecimal()`.
- [ ] Division specifies an explicit rounding mode and scale.
- [ ] Aggregations never mix multiple currencies together.
- [ ] Boundary values, overflow, SQL mode, and migration data are tested.
- [ ] If migrating from `FLOAT`/`DOUBLE`, values are reconciled against source data and `CAST` is not assumed to restore original digits.

## 11. Conclusion

`DECIMAL` represents exact decimal numbers within declared precision and scale, making it suitable for money and financial data. `FLOAT` and `DOUBLE` use approximate binary representation, which fits many scientific problems but can introduce errors when representing and accumulating decimal numbers.

Choose precision/scale based on value domains and currency rules, store currency codes alongside amounts, define rounding points explicitly, and use `BigDecimal` in Java. If legacy monetary data resides in `FLOAT`/`DOUBLE`, reconcile against authoritative sources before migrating because a new `DECIMAL` column cannot automatically recover digits lost during approximate storage.
