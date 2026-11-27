# Testing Numeric Precision, UNSIGNED, and Java Mappings

In the `DATABASE_MYSQL` module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, privilege management, backups, and handling relational database operational issues. This lesson guides testing numeric types between MySQL and Java, focusing on `DECIMAL`, `BigDecimal`, `UNSIGNED` integer types, value range boundaries, rounding, and conversions across JDBC/JPA.

Arithmetic bugs are often hard to spot because the application keeps running and data continues to be written. A monetary total can drift by a small fraction after several calculations; a `BIGINT UNSIGNED` value can exceed Java's `long` range; a cast can round or lose data unnoticed by ordinary tests. You must test at range boundaries, verify round-trips, and use real MySQL in integration tests.

## 1. Choosing Numeric Types Based on Data Semantics

MySQL provides integer types, exact fixed-point decimal types, and approximate floating-point types. Each group has different representations and limits.

| Group | MySQL types | Characteristics | Example usage |
|---|---|---|---|
| Integers | `TINYINT`, `SMALLINT`, `MEDIUMINT`, `INT`, `BIGINT` | Stores integers within a defined range; `UNSIGNED` can be used for a wider non-negative range. | IDs, quantities, counters, retry counts. |
| Exact decimals | `DECIMAL(p,s)`, `NUMERIC(p,s)` | Stores decimal values with specified precision and scale. | Money, taxes, rates requiring exact rules, measurements with fixed scale. |
| Floating-point | `FLOAT`, `DOUBLE` | Stores approximate binary floating-point values; some decimal fractions cannot be represented exactly. | Scientific computing, modeling, measurements accepting error tolerance. |

Do not choose `DOUBLE` merely because it holds more digits than `DECIMAL`. If the domain requires exact decimal values such as monetary amounts, use `DECIMAL` in MySQL and `BigDecimal` in Java. If the data represents approximate measurements, `FLOAT`/`DOUBLE` may fit, provided tests use tolerances instead of exact equality assertions.

## 2. Precision and Scale of DECIMAL

The `DECIMAL(p,s)` syntax takes two parameters:

- `p` (precision): maximum total number of digits, covering both integer and fractional parts.
- `s` (scale): number of digits to the right of the decimal point.

For example, `DECIMAL(12,2)` holds up to 12 digits total, with 2 fractional digits and 10 integer digits. The signed range is `-9999999999.99` to `9999999999.99`. With `DECIMAL(12,2) UNSIGNED`, the range starts at `0` and ends at `9999999999.99`.

MySQL supports a maximum precision of 65 digits and a maximum scale of 30 digits for `DECIMAL`. Scale cannot exceed precision. When designing columns, determine the maximum value, valid decimal places, and business rounding rules.

```sql
CREATE TABLE invoice_line (
    id BIGINT NOT NULL AUTO_INCREMENT,
    quantity DECIMAL(12,3) NOT NULL,
    unit_price DECIMAL(19,4) NOT NULL,
    line_total DECIMAL(20,4) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

Do not assume `DECIMAL(10,2)` fits every monetary amount. A system might need exchange rates with 8 decimal places, quantities with 3 decimal places, or financial totals exceeding a 10-digit cap. Derive precision and scale from domain requirements and verify total digits across all intermediate calculations.

## 3. BigDecimal in Java

Java's `BigDecimal` represents decimal numbers using an arbitrary-precision unscaled integer value and a scale. It is suitable for mapping to MySQL `DECIMAL`.

Construct `BigDecimal` from a string to avoid introducing `double` inaccuracy into the value:

```java
BigDecimal price = new BigDecimal("19.99");
BigDecimal quantity = new BigDecimal("3.000");
BigDecimal total = price.multiply(quantity);
```

Avoid:

```java
BigDecimal wrong = new BigDecimal(0.1);
```

`0.1` has no finite binary representation in `double`, so the constructor above converts the approximate `double` value into `BigDecimal`. Use `new BigDecimal("0.1")` or `BigDecimal.valueOf(0.1)` if the input genuinely originates as a `double` and the source cannot be changed.

### Scale and Comparison Methods

`BigDecimal.equals()` compares both value and scale:

```java
new BigDecimal("10.0").equals(new BigDecimal("10.00")); // false
```

`compareTo()` compares numeric value:

```java
new BigDecimal("10.0").compareTo(new BigDecimal("10.00")) == 0; // true
```

In tests, choose the comparison method according to the data contract:

- If only numeric equality is needed, use `compareTo() == 0` or a value-comparing assertion.
- If scale is part of the contract—for example, all monetary amounts must have exactly 2 decimal places—assert `scale()` explicitly too.
- If verifying that the database preserves column scale, read the value back and assert both value and scale.

Normalize scale explicitly before computing or persisting:

```java
BigDecimal amount = new BigDecimal("125.5")
        .setScale(2, RoundingMode.HALF_UP);
```

Never call `setScale()` and ignore its return value because `BigDecimal` is immutable. If scale changes without specifying a `RoundingMode` and nonzero digits would be discarded, Java throws `ArithmeticException`; this can be desirable behavior for catching invalid data.

## 4. Testing Java and MySQL Rounding

Rounding must be specified at the business level. For example, `HALF_UP` rounds midpoints away from zero; `HALF_EVEN` rounds midpoints toward the nearest even neighbor.

```java
BigDecimal value = new BigDecimal("1.005");

BigDecimal halfUp = value.setScale(2, RoundingMode.HALF_UP);
BigDecimal halfEven = value.setScale(2, RoundingMode.HALF_EVEN);

// halfUp  = 1.01
// halfEven = 1.00
```

For negative numbers, `HALF_UP` also rounds midpoints away from zero: `-1.005` becomes `-1.01`.

MySQL's `ROUND()` on exact types such as `DECIMAL` uses the round-half-away-from-zero rule. On approximate types such as `DOUBLE`, results can depend on the platform and binary representation. Therefore, currency tests must pass `BigDecimal` and verify against `DECIMAL` columns rather than substituting `double`.

Verification example in MySQL:

```sql
SELECT
    ROUND(CAST('1.005' AS DECIMAL(10,3)), 2) AS positive_half,
    ROUND(CAST('-1.005' AS DECIMAL(10,3)), 2) AS negative_half;
```

When writing a value with more decimal digits than the column scale, MySQL may round it to fit the scale. Do not assume `STRICT_TRANS_TABLES` rejects every excess-scale case. Explicitly test rounding, overflow, and warning behavior on your production MySQL version and `sql_mode`.

## 5. Value Ranges of UNSIGNED Integers

`UNSIGNED` removes the negative range and extends the positive range of integer types. Key ranges:

| MySQL type | Signed | Unsigned |
|---|---|---|
| `TINYINT` | -128 to 127 | 0 to 255 |
| `SMALLINT` | -32,768 to 32,767 | 0 to 65,535 |
| `MEDIUMINT` | -8,388,608 to 8,388,607 | 0 to 16,777,215 |
| `INT` | -2,147,483,648 to 2,147,483,647 | 0 to 4,294,967,295 |
| `BIGINT` | -9,223,372,036,854,775,808 to 9,223,372,036,854,775,807 | 0 to 18,446,744,073,709,551,615 |

Several `UNSIGNED` types fit into a wider signed Java type; `BIGINT UNSIGNED` does not fit in `long` across its entire range. Do not rely only on current data being smaller than the limit; define invariants and test the real limits.

| MySQL | Java type capable of holding the full unsigned range | Notes |
|---|---|---|
| `TINYINT UNSIGNED` | `short` or `int` | Signed `byte` cannot hold 128–255. |
| `SMALLINT UNSIGNED` | `int` | Signed `short` cannot hold 32,768–65,535. |
| `MEDIUMINT UNSIGNED` | `int` | Unsigned range fits within `Integer.MAX_VALUE`. |
| `INT UNSIGNED` | `long` | Signed `int` cannot hold the upper half of the range. |
| `BIGINT UNSIGNED` | `BigInteger` | Signed `long` cannot hold values above `Long.MAX_VALUE`. |

If the Java application uses `Long` for IDs, a signed MySQL `BIGINT` column is usually appropriate and avoids range mismatches. If full-range `BIGINT UNSIGNED` is mandatory, map it to `BigInteger` or another safe representation and test the specific driver/provider.

## 6. Numeric Mapping Over JDBC

For `DECIMAL`, use `PreparedStatement.setBigDecimal()` and `ResultSet.getBigDecimal()`:

```java
String sql = "INSERT INTO payment (amount) VALUES (?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, new BigDecimal("123456789012.3400"));
    ps.executeUpdate();
}

try (PreparedStatement ps = connection.prepareStatement(
        "SELECT amount FROM payment WHERE id = ?")) {
    ps.setLong(1, paymentId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            BigDecimal amount = rs.getBigDecimal("amount");
        }
    }
}
```

Do not use `getDouble()` for `DECIMAL` columns when exact values must be preserved. `getDouble()` converts the value to an approximate floating-point number.

### Reading BIGINT UNSIGNED Greater Than Long.MAX_VALUE

Do not use `ResultSet.getLong()` to read the full `BIGINT UNSIGNED` range. Read it as `BigDecimal`, then convert cleanly to `BigInteger`:

```java
BigDecimal raw = rs.getBigDecimal("unsigned_counter");
BigInteger value = raw.toBigIntegerExact();
```

`toBigIntegerExact()` detects whether the value has a fractional part. For integer columns, this provides a checked conversion. `getObject()` can also be used, though the returned Java type can depend on Connector/J and its version; if used, verify `DatabaseMetaData`, runtime type, and boundaries in integration tests.

To write a `BIGINT UNSIGNED` value greater than `Long.MAX_VALUE`, represent it as `BigInteger` and convert to `BigDecimal` when binding:

```java
BigInteger maxUnsignedBigint = new BigInteger("18446744073709551615");

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO unsigned_value (value) VALUES (?)")) {
    ps.setBigDecimal(1, new BigDecimal(maxUnsignedBigint));
    ps.executeUpdate();
}
```

Test this binding with the exact Connector/J and MySQL versions you deploy. If using JPA/Hibernate, mapping `BigInteger` to a `BIGINT UNSIGNED` column must also be verified across DDL, dialect, and driver; do not assume the `@Column` annotation automatically guarantees the full unsigned range.

## 7. Mapping DECIMAL in JPA/Hibernate

For exact decimal values, use `BigDecimal` and declare precision and scale:

```java
@Column(name = "amount", precision = 19, scale = 4, nullable = false)
private BigDecimal amount;
```

DDL should be managed via migrations:

```sql
CREATE TABLE payment (
    id BIGINT NOT NULL AUTO_INCREMENT,
    amount DECIMAL(19,4) NOT NULL,
    currency CHAR(3) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

Do not only verify that the entity can persist. Inspect the actual schema via `SHOW CREATE TABLE payment`, JDBC metadata, and round-trip tests. If Hibernate generates DDL, inspect the dialect-emitted DDL. In production, prefer controlled migrations and `ddl-auto=validate` over `ddl-auto=update`.

### BIGINT UNSIGNED with JPA

If you must store the full `BIGINT UNSIGNED` range, Java `BigInteger` is the right type for range coverage. However, how the Hibernate dialect maps `BigInteger` to a JDBC numeric type and how Connector/J returns data must be verified on the real stack. `columnDefinition = "bigint unsigned"` can describe DDL in some configurations, though it does not automatically solve all JDBC type or schema-validation differences.

If you do not need values exceeding `Long.MAX_VALUE`, choosing signed `BIGINT` and Java `Long` is usually simpler. If requirements genuinely demand the full unsigned range, write integration tests for values near `Long.MAX_VALUE`, above `Long.MAX_VALUE`, and near `18446744073709551615`.

## 8. How SQL Mode Affects Numeric Errors

When a value exceeds a column's range, MySQL behavior depends on `sql_mode`. In strict mode, out-of-range values are normally rejected with an error. In non-strict mode, MySQL may clamp to the boundary value and emit a warning. This can cause wrong data to be saved unnoticed if the application checks only the updated row count.

Check the active mode:

```sql
SELECT @@GLOBAL.sql_mode, @@SESSION.sql_mode;
```

Global mode and session mode can differ. Tests must inspect the session of the actual connection used to execute statements.

Example out-of-range value for `INT UNSIGNED`:

```sql
CREATE TABLE unsigned_probe (
    value INT UNSIGNED NOT NULL
) ENGINE=InnoDB;

INSERT INTO unsigned_probe (value) VALUES (4294967295);
```

`4294967295` is the valid upper boundary. `4294967296` is out of range. Run tests inside a separate transaction or table so other fixtures stay clean.

Immediately after a statement that might emit warnings, inspect them:

```sql
SHOW WARNINGS;
```

`SHOW WARNINGS` must run immediately after the statement under test because another statement can overwrite the warning list. Do not assume every warning becomes an exception at the JDBC layer; configure strict mode and verify exceptions/warnings per application policy.

### CHECK Constraints for Business Rules

Since MySQL 8.0.16, `CHECK` constraints are enforced. Example:

```sql
CREATE TABLE product_stock (
    product_id BIGINT NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(19,4) NOT NULL,
    CONSTRAINT chk_stock_quantity CHECK (quantity >= 0),
    CONSTRAINT chk_stock_price CHECK (unit_price >= 0),
    PRIMARY KEY (product_id)
) ENGINE=InnoDB;
```

`UNSIGNED` expresses non-negativity at the data type level; `CHECK` expresses a business rule. You may need both or just one depending on requirements. If supporting versions older than 8.0.16, do not assume `CHECK` constraints are enforced; verify the target MySQL version.

## 9. Designing Boundary Test Suites

For every numeric column, build test cases across four zones:

1. **Normal values:** typical values encountered in business operations.
2. **Valid boundary values:** minimum, maximum, zero, negative numbers if allowed, and values with maximum scale.
3. **Just-outside-boundary values:** one unit below min or one unit above max at the column's storage precision.
4. **Conversion values:** excess scale, excess precision, values larger than narrower Java types, and `NULL` if nullable.

Example matrix for `DECIMAL(8,2)`:

| Test case | Value | Expected result |
|---|---:|---|
| Zero | `0.00` | Stored and read back accurately. |
| Normal positive | `125.50` | Stored and read back accurately. |
| Maximum value | `999999.99` | Stored. |
| Minimum signed value | `-999999.99` | Stored if column is not `UNSIGNED`. |
| Exceeds precision | `1000000.00` | Rejected in strict mode. |
| Excess scale | `1.005` | Verify rounding rule to `1.01` on MySQL exact `DECIMAL`. |
| Negative on `UNSIGNED` column | `-0.01` | Rejected in strict mode; check warnings if non-strict. |

For `INT UNSIGNED`, test `0`, `1`, `2147483647`, `2147483648`, `4294967295`, and `4294967296`. For `BIGINT UNSIGNED`, test `9223372036854775807`, `9223372036854775808`, and `18446744073709551615` using decimal strings or `BigInteger`, never `long` literals for out-of-range values.

## 10. Integration Test Examples with Spring JDBC and JUnit

Tests must run against real MySQL, ideally matching the major/minor version of production. Example using `JdbcTemplate` for `DECIMAL` round-trip testing:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;

@JdbcTest
class DecimalMappingTest {

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void decimalRoundTripPreservesValueAndScale() {
        BigDecimal input = new BigDecimal("1234567890123.4500");

        jdbc.update("INSERT INTO payment_probe(amount) VALUES (?)", input);

        BigDecimal actual = jdbc.queryForObject(
            "SELECT amount FROM payment_probe ORDER BY id DESC LIMIT 1",
            BigDecimal.class
        );

        assertThat(actual).isNotNull();
        assertThat(actual.compareTo(input)).isZero();
        assertThat(actual.scale()).isEqualTo(4);
    }
}
```

The `payment_probe` fixture must be created by a test migration or `@Sql`:

```sql
CREATE TABLE payment_probe (
    id BIGINT NOT NULL AUTO_INCREMENT,
    amount DECIMAL(19,4) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

With `@JdbcTest`, Spring Boot may replace the datasource with an embedded database under default configuration. To test MySQL semantics, use Testcontainers MySQL or a MySQL test datasource and configure `@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)`.

### Testing Rounding and Boundaries

```java
@Test
void mysqlRoundsExactDecimalAtColumnScale() {
    jdbc.update("INSERT INTO decimal_probe(amount) VALUES (?)",
        new BigDecimal("1.005"));

    BigDecimal actual = jdbc.queryForObject(
        "SELECT amount FROM decimal_probe ORDER BY id DESC LIMIT 1",
        BigDecimal.class
    );

    assertThat(actual).isEqualByComparingTo("1.01");
}
```

This test requires a `DECIMAL(...,2)` column and real MySQL. It tests MySQL's scale conversion behavior, not replacing domain-level rounding tests in Java. Maintain separate tests for `RoundingMode` in your services.

### Testing UNSIGNED Over JDBC

```java
@Test
void readsUnsignedBigintAboveLongMaxValue() throws Exception {
    BigInteger expected = new BigInteger("9223372036854775808");

    jdbc.update(
        "INSERT INTO unsigned_probe_bigint(value) VALUES (?)",
        new BigDecimal(expected)
    );

    BigDecimal raw = jdbc.queryForObject(
        "SELECT value FROM unsigned_probe_bigint ORDER BY id DESC LIMIT 1",
        BigDecimal.class
    );

    assertThat(raw.toBigIntegerExact()).isEqualTo(expected);
}
```

Fixture:

```sql
CREATE TABLE unsigned_probe_bigint (
    id BIGINT NOT NULL AUTO_INCREMENT,
    value BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

This test verifies the path from Java `BigInteger` through `BigDecimal`/JDBC to MySQL and back. Add tests near the maximum unsigned value as well as negative tests catching accidental use of `getLong()`.

## 11. Verifying Metadata and Runtime Mappings

Beyond values, check the exact column types MySQL actually created:

```sql
SHOW CREATE TABLE payment;

SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    DATA_TYPE,
    NUMERIC_PRECISION,
    NUMERIC_SCALE,
    IS_NULLABLE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'payment'
ORDER BY ORDINAL_POSITION;
```

`COLUMN_TYPE` shows details like `bigint unsigned`; `NUMERIC_PRECISION` and `NUMERIC_SCALE` verify `DECIMAL`. In JDBC, `DatabaseMetaData.getColumns()` lets you inspect `TYPE_NAME`, `COLUMN_SIZE`, and `DECIMAL_DIGITS`. Compare metadata against entity/migration contracts to catch schema drift.

With Connector/J, check actual types from `ResultSetMetaData` or `ResultSet.getObject()` on the exact driver version locked in dependency management. Do not write production code depending on untested runtime types when upgrading drivers.

## 12. Testing with Real MySQL Instead of Only H2

H2 and MySQL can differ in:

- `UNSIGNED` support and value ranges.
- `DECIMAL` rounding, overflow, and warning behavior.
- How `sql_mode` and strict mode are applied.
- JDBC types returned for unsigned integers.
- DDL, constraints, and Hibernate dialect schema validation.
- `JSON` types, generated columns, and MySQL-specific functions.

Unit tests can use H2 for pure Java logic, such as `BigDecimal` arithmetic and range validation. Integration tests for `DECIMAL`, `UNSIGNED`, JDBC mappings, strict mode, and DDL must run on MySQL. Testcontainers provides a disposable MySQL instance at a pinned version while avoiding dependencies on shared databases.

Do not test against an arbitrary MySQL version. If production runs MySQL 8.4, the test container should use the same branch and equivalent `sql_mode` configuration. Whenever upgrading MySQL or Connector/J, re-run boundary tests to catch mapping changes.

## 13. Common Bugs and Remedies

| Symptom | Common cause | How to resolve |
|---|---|---|
| Monetary amounts drift after saving | Using `double`, unclear scale, or rounding at multiple layers. | Use `BigDecimal`/`DECIMAL`, define one rounding rule, and run round-trip tests. |
| `BigDecimal` test fails despite identical display values | `BigDecimal.equals()` checks scale too. | Use `compareTo()` for numeric equality; assert `scale()` separately if required. |
| `BIGINT UNSIGNED` becomes negative or fails on read | Using `getLong()`/`Long` above `Long.MAX_VALUE`. | Use `getBigDecimal()` then `toBigIntegerExact()`; or switch schema to signed `BIGINT` if appropriate. |
| Out-of-range values still get saved | Session is not in strict mode and MySQL clamps with a warning. | Check `@@SESSION.sql_mode`, `SHOW WARNINGS`, and configure strict mode. |
| `BigInteger` entity incompatible with unsigned column | Hibernate dialect/driver maps to an unexpected JDBC type. | Inspect DDL and metadata; write integration tests on exact Hibernate/Connector/J/MySQL stack. |
| `DECIMAL` values get rounded on insert | Column scale is smaller than input scale. | Define business scale, normalize before persisting, and test exact rounding points. |
| H2 passes while MySQL fails | Differences in numeric types, `UNSIGNED`, or SQL mode. | Run integration tests on real MySQL or Testcontainers. |

## 14. Practice Exercise

A sales service stores product prices, stock quantities, invoice totals, and a sync counter. Design and test on MySQL:

1. Create `unit_price DECIMAL(19,4)`, `quantity INT UNSIGNED`, `invoice_total DECIMAL(20,4)`, and `sync_counter BIGINT UNSIGNED`.
2. Map `unit_price` and `invoice_total` to `BigDecimal`; choose suitable Java types for quantity and sync counter.
3. Write a service computing totals with `BigDecimal`, specifying scale and `RoundingMode` at each business step.
4. Test normal values, zero, maximums, negative values, excess scale, and precision overflow.
5. Test the `INT UNSIGNED` range at `0`, `2147483647`, `2147483648`, `4294967295`, and `4294967296`.
6. Test `BIGINT UNSIGNED` at `Long.MAX_VALUE`, `Long.MAX_VALUE + 1`, and maximum value using `BigInteger`.
7. Write and read data over JDBC, verifying `BigDecimal`/`BigInteger` round-trips and column metadata.
8. Run the same tests in strict mode and non-strict mode in a test environment; record errors, warnings, and actual stored values.
9. Run integration tests on real MySQL matching the production version; compare results with Java unit tests.
10. Document the contract for each field: value range, precision/scale, Java type, rounding rule, nullability, and out-of-range behavior.

After the exercise, learners should be able to explain why money uses `DECIMAL`/`BigDecimal`, why `BigDecimal.equals()` can fail tests, why `BIGINT UNSIGNED` cannot map its full range to `long`, and why strict mode plus real MySQL integration tests are essential to numeric data testing. This provides the foundation to ensure numeric values are never silently altered between Java, JDBC, and MySQL.

## Official References

- [MySQL 8.4 Reference Manual: Fixed-Point Types (Exact Value)](https://dev.mysql.com/doc/refman/8.4/en/fixed-point-types.html)
- [MySQL 8.4 Reference Manual: Integer Types](https://dev.mysql.com/doc/refman/8.4/en/integer-types.html)
- [MySQL 8.4 Reference Manual: Out-of-Range and Overflow Handling](https://dev.mysql.com/doc/refman/8.4/en/out-of-range-and-overflow.html)
- [MySQL 8.4 Reference Manual: SQL Modes](https://dev.mysql.com/doc/refman/8.4/en/sql-mode.html)
- [Java BigDecimal API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
- [JDBC ResultSet API](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/ResultSet.html)
- [Spring Boot Reference: Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
