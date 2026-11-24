# SQL Data Types, NULL, and Three-Valued Logic

A syntactically valid query can still produce wrong results if you choose inappropriate data types or treat `NULL` as an ordinary value. This is essential groundwork before using JDBC, Spring JDBC, JPA, or any data-access tool: Java tools convert data, yet **type rules and comparison semantics remain governed by the database management system (DBMS)**.

After this lesson, you will be able to:
- Choose appropriate SQL type families for numbers, strings, dates/times, binary data, and extended types, while recognizing differences across DBMSs.
- Distinguish `NULL` from the number 0, an empty string, `FALSE`, and a default value.
- Predict `TRUE` / `FALSE` / `UNKNOWN` outcomes of SQL expressions, especially when filtering with `WHERE`, `JOIN`, and `HAVING`.
- Avoid common pitfalls with `= NULL`, `NOT IN`, `COUNT`, `CHECK`, and outer joins.
- Map nullable values safely when reading and writing data via JDBC and Spring `JdbcTemplate`.

> **Example scope:** The table-creation statements and `WITH ... VALUES` queries below use modern PostgreSQL syntax for consistent testing. Principles around `NULL`, three-valued logic, and aggregation are broad SQL principles; wherever syntax or behavior differs by DBMS, it is noted explicitly. When deploying on MySQL, SQL Server, Oracle, or H2, verify against the documentation for the exact version in use.

## 1. What Do SQL Data Types Describe?

Each column has a **data type** that determines its valid value domain, storage format, operations, precision, and conversion rules. For example, an invoice code `'00125'` is a text identifier; storing it as an integer drops the leading zeros. Conversely, a total amount must be a numeric type for addition, comparison, and constraint checks.

Common type families:

| Family | Common Types | Used For | What to Watch For |
| --- | --- | --- | --- |
| Integer | `SMALLINT`, `INTEGER`/`INT`, `BIGINT` | Quantities, numeric keys, counters | Range limits; avoid overflow in calculations. |
| Exact decimal | `DECIMAL(p,s)`, `NUMERIC(p,s)` | Money, ratios needing fixed precision | `p` is total digits; `s` is digits after the decimal point. |
| Approximate numeric | `REAL`, `FLOAT`, `DOUBLE PRECISION` | Measurements, scientific computing | Approximate binary representation; unsuitable for exact equality checks on money. |
| Character | `CHAR(n)`, `VARCHAR(n)`, `TEXT` | Names, descriptions, codes | `CHAR` may be space-padded; `TEXT` and length limits vary by DBMS. |
| Date/time | `DATE`, `TIME`, `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE` | Birth dates, creation instants, schedules | Must distinguish calendar date, zoneless local time, and true instant. |
| Boolean | `BOOLEAN` | Feature flags, true/false states | Nullable columns also allow `NULL`; some DBMSs use numeric types instead. |
| Binary | `BINARY`, `VARBINARY`, `BLOB`/`BYTEA` | Files, bytes, checksums | Type names and size limits depend on the DBMS. |
| Extended | `UUID`, `JSON`/`JSONB`, `ARRAY`, `ENUM` | UUID identifiers, JSON documents, value sets | Not all belong to the same standard syntax or exist in every DBMS. |

### 1.1. Exact Types vs. Approximate Types

With `DECIMAL(15,2)`, a value has at most 15 decimal digits in total, of which 2 are fractional; in terms of range, at most 13 digits lie in the integer part. Rounding/conversion rules and overflow handling must be checked per DBMS.

- **Money:** use `DECIMAL`/`NUMERIC`, and in Java typically use `BigDecimal`.
- **Approximate measurements:** floating-point types can be used; do not assume binary addition produces exact decimal results.
- **Identifiers:** `phone`, `postal_code`, or product codes with leading zeros should use strings, even if they contain only digits.

### 1.2. Temporal Types Have Different Semantics

`DATE` is a calendar date, not an absolute instant; `TIME` is time of day. `TIMESTAMP WITHOUT TIME ZONE` stores local date and time without carrying time zone metadata. In PostgreSQL, `TIMESTAMP WITH TIME ZONE` (`timestamptz`) represents an instant in time and is interpreted/displayed in the session's time zone; it **does not preserve the original time zone name or offset**. Some DBMSs follow different rules. In Java, typically choose `LocalDate` for `DATE`, `LocalDateTime` for local time, and `OffsetDateTime`/`Instant` for true instants, depending on JDBC driver support and column type.

## 2. Sample Table Design and the Meaning of NULL

PostgreSQL example:

```sql
CREATE TABLE invoices (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    invoice_no  VARCHAR(30) NOT NULL UNIQUE,
    amount      DECIMAL(15, 2) NOT NULL CHECK (amount >= 0),
    due_on      DATE,
    paid_at     TIMESTAMP WITH TIME ZONE,
    note        VARCHAR(200),
    active      BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO invoices
    (customer_id, invoice_no, amount, due_on, paid_at, note)
VALUES
    (7, 'INV-00125', 125000.50, DATE '2026-11-15', NULL, NULL);
```

Here, `paid_at IS NULL` means **payment timestamp information is not present**. Do not automatically infer that the invoice is overdue or definitively unpaid if the workflow has other states. `note IS NULL` means the note field has no value, which differs from `note = ''` (empty string) in PostgreSQL. `amount` has a `NOT NULL` constraint because an invoice must have an amount.

**NULL is not** the number 0, `FALSE`, the string `'NULL'`, an empty string, the date `1970-01-01`, or an unrendered UI cell. It is a **marker for a missing or unknown value** in the SQL model. The reason for absence could be unknown, not applicable, or not yet provided; if you need to distinguish these states, design an explicit status column or separate model rather than overloading every `NULL` with one fixed business meaning.

### 2.1. NULL, DEFAULT, and Constraints

- `NOT NULL` forces a column to have a non-null value.
- `DEFAULT TRUE` is used when a column is **omitted** in `INSERT` or when the `DEFAULT` keyword is passed; explicitly passing `NULL` is not synonymous with asking for the default. On a `NOT NULL` column, passing `NULL` is typically rejected.
- `PRIMARY KEY` uniquely identifies a record and forbids `NULL`.
- `UNIQUE` and `NULL` differ across DBMSs: many DBMSs allow multiple rows with `NULL` in a unique column, while some rules/index types differ. Do not assume this behavior is portable.
- A nullable foreign key may point to no parent record; for a single-column foreign key, `NULL` is not treated as a referencing key requiring a parent row.
- `CHECK (amount >= 0)` only rejects **FALSE** expressions. If `amount` is `NULL`, `amount >= 0` evaluates to **UNKNOWN**, so this `CHECK` alone does not exclude `NULL`. Pair it with `NOT NULL` if the field is required.

## 3. SQL Uses **Three-Valued Logic**

In many programming languages, conditional expressions mostly yield `true` or `false`. In SQL, because of `NULL`, an ordinary comparison can evaluate to:

- **TRUE (T):** the condition holds.
- **FALSE (F):** the condition does not hold.
- **UNKNOWN (U):** value missing to determine true or false.

Illustrative expressions:

| Expression | Result | Reason |
| --- | --- | --- |
| `5 = 5` | T | Two known values are equal. |
| `5 <> 8` | T | Two known values differ. |
| `NULL = 5` | U | Missing value to compare against. |
| `NULL <> 5` | U | Cannot deduce "not equal to 5". |
| `NULL = NULL` | U | Two NULL markers do not form a TRUE equality. |
| `NOT (NULL = 5)` | U | Negating UNKNOWN remains UNKNOWN. |
| `NULL IS NULL` | T | `IS NULL` tests for the presence of NULL. |
| `5 IS NOT NULL` | T | The value 5 is present. |

Core rule: with `=`, `<>`, `<`, `>`, `<=`, `>=`, when an operand is `NULL`, the result is usually `UNKNOWN`; never use `= NULL` or `<> NULL` to check for missing values.

### 3.1. Truth Tables for NOT, AND, OR

`NOT`:

| P | NOT P |
| --- | --- |
| T | F |
| F | T |
| U | U |

`AND`:

| P \ Q | T | F | U |
| --- | --- | --- | --- |
| T | T | F | U |
| F | F | F | F |
| U | U | F | U |

`OR`:

| P \ Q | T | F | U |
| --- | --- | --- | --- |
| T | T | T | T |
| F | T | F | U |
| U | T | U | U |

Watch out for counterintuitive cases: `FALSE AND UNKNOWN = FALSE`, `TRUE OR UNKNOWN = TRUE`, and `NOT UNKNOWN = UNKNOWN`. Consequently, `x = 10 OR x <> 10` is **not always TRUE**: when `x IS NULL`, both sides are UNKNOWN and the result is UNKNOWN. The familiar "law of excluded middle" from two-valued logic cannot be applied mechanically to nullable SQL comparisons.

## 4. How WHERE, HAVING, and JOIN Handle UNKNOWN

`WHERE` and `HAVING` keep only rows/groups whose condition evaluates to **TRUE**. Both FALSE and UNKNOWN are filtered out.

Standalone test data runnable in PostgreSQL:

```sql
WITH samples(id, score) AS (
    VALUES (1, 5), (2, 10), (3, NULL)
)
SELECT id, score
FROM samples
WHERE score <> 5
ORDER BY id;
```

**Result:** only row `id = 2, score = 10`. Row `id = 3` is excluded because `NULL <> 5` is UNKNOWN, not TRUE. Replacing `WHERE score <> 5` with `WHERE NOT (score = 5)` still returns only `id = 2`.

To select values other than 5 **or unknown**, state it explicitly:

```sql
WHERE score <> 5 OR score IS NULL
```

If the DBMS supports it, `score IS DISTINCT FROM 5` is a "NULL-aware not-equal" comparison: on the dataset above, it is TRUE for both `score = 10` **and** `score IS NULL`. Conversely, `IS NOT DISTINCT FROM` is a NULL-aware equality comparison; two NULL values are treated as not distinct. PostgreSQL supports both, while MySQL provides the null-safe operator `<=>` with semantics equivalent to `IS NOT DISTINCT FROM`. Check DBMS support before using.

### 4.1. JOIN: ON and WHERE Are Not Freely Interchangeable

For `INNER JOIN`, a pair of rows matches only when the `ON` condition is TRUE; UNKNOWN produces no match. For `LEFT JOIN`, an unmatched left-side row is still kept and right-side columns are padded with NULL. Thus condition placement is critical.

```sql
-- Keep all customers; only join invoices where active = TRUE.
SELECT c.id, i.invoice_no
FROM customers AS c
LEFT JOIN invoices AS i
    ON i.customer_id = c.id AND i.active = TRUE;
```

In the query above, customers with no active invoice still appear with `i.invoice_no` as NULL. However, if `i.active = TRUE` is moved down to `WHERE`:

```sql
SELECT c.id, i.invoice_no
FROM customers AS c
LEFT JOIN invoices AS i
    ON i.customer_id = c.id
WHERE i.active = TRUE;
```

The NULL-padded rows are eliminated by `WHERE`; the result no longer keeps all customers. Both examples assume a `customers` table with key `id` and the `invoices` table created in section 2.

## 5. Common Traps with IN and NOT IN

Logically, `IN` is equivalent to a chain of equality comparisons combined with `OR`. If the list contains NULL:

- `5 IN (5, NULL)` → TRUE because a matching element exists.
- `8 IN (5, NULL)` → UNKNOWN because `8 = 5` is FALSE and `8 = NULL` is UNKNOWN.
- `8 NOT IN (5, NULL)` → UNKNOWN because it is the negation of UNKNOWN.
- `NULL IN (5, NULL)` → UNKNOWN; NULL does not "match itself" via `=`.

Because `WHERE` discards UNKNOWN, `NOT IN` can easily return **unexpectedly empty results** if the subquery yields even a single NULL:

```sql
-- Prone to error if invoices.customer_id can contain NULL:
SELECT c.id
FROM customers AS c
WHERE c.id NOT IN (
    SELECT i.customer_id FROM invoices AS i
);
```

A usually safer way to find customers **without** invoices is an anti-join using `NOT EXISTS`:

```sql
SELECT c.id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM invoices AS i
    WHERE i.customer_id = c.id
);
```

`EXISTS` only asks whether the subquery produces at least one row; it does not depend on the column values in `SELECT 1`. The correlated condition `i.customer_id = c.id` does not match `i.customer_id IS NULL`, so NULLs in the child table do not "poison" the entire result like `NOT IN`. In the sample schema, `invoices.customer_id` already has `NOT NULL`; the `NOT IN` trap is especially important on other schemas or subqueries that can produce NULLs from joins or expressions.

## 6. NULL with Aggregate Functions, DISTINCT, and GROUP BY

Aggregate functions do not treat NULL identically:

| Expression | Meaning |
| --- | --- |
| `COUNT(*)` | Counts **all rows**, regardless of which columns are NULL. |
| `COUNT(col)` | Counts rows where `col IS NOT NULL`. |
| `COUNT(DISTINCT col)` | Counts distinct **non-NULL** values. |
| `SUM(col)`, `AVG(col)` | Ignores NULL; `AVG` divides by the count of non-NULL values. |
| `MIN(col)`, `MAX(col)` | Ignores NULL. |

Verify with a standalone query:

```sql
WITH samples(id, score) AS (
    VALUES (1, 5), (2, 10), (3, NULL)
)
SELECT COUNT(*) AS all_rows,
       COUNT(score) AS known_scores,
       SUM(score) AS total_score,
       AVG(score) AS average_score
FROM samples;
```

Logical result values: `all_rows = 3`, `known_scores = 2`, `total_score = 15`, `average_score = 7.5`. Decimal formatting may vary by DBMS. If there are no input rows (or every argument to `SUM` is NULL), `SUM` returns NULL while `COUNT` returns 0. To display 0 when there are no numbers to sum, use `COALESCE(SUM(score), 0)`.

In `GROUP BY col`, rows with `col IS NULL` are gathered into **one NULL group**. `SELECT DISTINCT col` likewise returns a single NULL entry among distinct values. This **does not** mean `NULL = NULL` becomes TRUE in normal comparisons; it is a specific rule for grouping and deduplication.

Sort ordering of NULL is not uniform across DBMSs. PostgreSQL lets you specify `ORDER BY col NULLS FIRST` or `NULLS LAST`; this syntax is not universal across every DBMS. Do not base business logic on default NULL placement.

## 7. Writing NULL-Handling Expressions Correctly

### 7.1. IS NULL / IS NOT NULL

```sql
SELECT invoice_no
FROM invoices
WHERE paid_at IS NULL;
```

This is the standard way to find invoices missing payment timestamp information. `WHERE paid_at = NULL` fails to match these rows.

### 7.2. COALESCE: Choosing the First Non-NULL Value

`COALESCE(a, b, ...)` returns the first non-NULL argument; if all are NULL, it returns NULL. Arguments must have compatible convertible types under DBMS rules.

```sql
SELECT invoice_no,
       COALESCE(note, '(no note)') AS display_note
FROM invoices;
```

Use `COALESCE` at **presentation boundaries** when a fallback value truly fits. `COALESCE(score, 0)` turns "unknown score" into "score 0"; this can alter statistics and data semantics. For instance, `AVG(score)` skips NULLs, whereas `AVG(COALESCE(score, 0))` turns missing values into 0 and changes the denominator.

### 7.3. NULLIF, CASE, and Type Casting

- `NULLIF(a, b)` returns NULL if `a = b` is TRUE; otherwise it returns `a`. You can use `NULLIF(quantity, 0)` to turn a zero denominator into NULL before division, though the expression result also becomes NULL instead of raising a divide-by-zero error.
- `CASE WHEN condition THEN x ELSE y END` takes a `WHEN` branch only when the condition is TRUE; FALSE and UNKNOWN proceed to subsequent branches or `ELSE`.
- `CAST(value AS type)` performs explicit conversion. Converting strings to numbers or dates can fail on invalid data; "try-cast returning NULL" functions have DBMS-specific names/syntax and are not portable SQL.

```sql
SELECT invoice_no,
       CASE
           WHEN paid_at IS NOT NULL THEN 'Payment timestamp recorded'
           WHEN due_on IS NULL THEN 'No due date'
           ELSE 'No payment timestamp yet'
       END AS payment_information
FROM invoices;
```

This expression classifies the **level of information present in columns** by branch order, without fully concluding business status such as "paid" or "overdue." Distinguish observed data from business policy.

## 8. Interacting with JDBC and Spring Data Access

SQL `NULL` commonly maps to Java `null` for reference types. However, not every read method preserves missingness. JDBC passes SQL types through the driver; corresponding Java types must be chosen based on the data and nullability:

| SQL | Common Java Type | Notes |
| --- | --- | --- |
| Nullable `INTEGER` | `Integer` | Do not use `int` if you need to distinguish NULL from 0. |
| `BIGINT` | `Long`/`long` | Use primitive `long` only when the column is guaranteed `NOT NULL`. |
| `DECIMAL`/`NUMERIC` | `BigDecimal` | Preserves precision; never switch to `double` for money. |
| `VARCHAR` | `String` | Java `null` and `""` can carry different meanings. |
| `DATE` | `LocalDate` | Prefer JDBC 4.2 / drivers supporting `java.time` types. |
| `TIMESTAMP WITH TIME ZONE` | `OffsetDateTime`/`Instant` per driver | Verify driver, normalization behavior, and connection time zone. |
| Nullable `BOOLEAN` | `Boolean` | Three Java states: `true`, `false`, `null`. |

`ResultSet.getInt(...)`, `getLong(...)`, and `getBoolean(...)` return primitives, so when the SQL column is NULL, they return default values `0`/`false`. To know if it was genuinely NULL, **call `rs.wasNull()` immediately after that read**, before reading another column. When supported by the JDBC driver, `rs.getObject("score", Integer.class)` reads into a nullable object. `rs.getBigDecimal(...)` returns `BigDecimal` or `null`.

This is **an illustrative class using Spring JDBC**, requiring Spring JDBC dependencies, a configured `JdbcTemplate`, and the `invoices` table in the DB; it is not a standalone program runnable with `java` alone:

```java
import java.math.BigDecimal;
import java.sql.Types;
import java.time.LocalDate;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;

public final class InvoiceReader {
    private final JdbcTemplate jdbc;

    public InvoiceReader(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record InvoiceView(long id, BigDecimal amount, LocalDate dueOn) {}

    public List<InvoiceView> withoutPaymentTimestamp() {
        RowMapper<InvoiceView> mapper = (rs, rowNum) -> new InvoiceView(
            rs.getLong("id"),                       // PK NOT NULL
            rs.getBigDecimal("amount"),              // DECIMAL
            rs.getObject("due_on", LocalDate.class)  // nullable
        );

        return jdbc.query(
            "SELECT id, amount, due_on FROM invoices WHERE paid_at IS NULL",
            mapper
        );
    }

    public int clearNote(long invoiceId) {
        return jdbc.update(
            "UPDATE invoices SET note = ? WHERE id = ?",
            ps -> {
                ps.setNull(1, Types.VARCHAR); // explicit typed SQL NULL
                ps.setLong(2, invoiceId);
            }
        );
    }
}
```

Key observations:
1. `InvoiceView.dueOn` uses `LocalDate` (a reference type) because `due_on` can be NULL.
2. `id` and `amount` are `NOT NULL` in the DDL; `rs.getLong("id")` is appropriate for the primary key. `getBigDecimal` still returns an object reference.
3. `PreparedStatement.setNull(position, Types.VARCHAR)` writes **SQL NULL**, not the string `"null"`; choose a `Types` code matching the column and driver.
4. Dynamic values are bound via `?` parameters, avoiding concatenating user input into SQL strings.
5. Do not write `WHERE note = ?` and bind null expecting to match NULL notes; `=` still yields UNKNOWN. Use `IS NULL` or a DBMS-supported null-safe comparison.

With Spring Data JPA, nullable Java types and queries still must reflect SQL `NULL`; returning `Optional<T>` at the repository boundary expresses "record present/absent," yet **does not automatically solve** nullable attributes or UNKNOWN outcomes in `WHERE`. Always inspect the generated SQL when writing derived queries or JPQL involving nullable conditions.

## 9. Common Mistakes and Fixes

| Common Mistake | Consequence | Correct Approach by Goal |
| --- | --- | --- |
| `WHERE x = NULL` | Evaluates to UNKNOWN; fails to match missing rows. | `WHERE x IS NULL`. |
| `WHERE x <> NULL` | Does not select known rows as expected. | `WHERE x IS NOT NULL` if goal is "has a value". |
| `WHERE x <> 5` assuming it includes NULL | NULL rows are excluded. | `x <> 5 OR x IS NULL`, or `x IS DISTINCT FROM 5` if supported. |
| `NOT IN (subquery)` when subquery has NULL | May return zero rows. | `NOT EXISTS` with correlated key condition. |
| Moving right-side `LEFT JOIN` condition to `WHERE` | Drops unmatched left-side rows. | Keep right-side row filter in `ON` when preserving left rows. |
| `AVG(COALESCE(x, 0))` to "ignore NULL" | Accidentally counts missing data as zero. | `AVG(x)` to skip missing values. |
| `CHECK(x > 0)` assuming x cannot be NULL | UNKNOWN still passes CHECK. | Combine `x NOT NULL` and `CHECK(x > 0)`. |
| Reading nullable SQL `INTEGER` with `getInt` without `wasNull` | Cannot tell NULL apart from 0. | `getObject(..., Integer.class)` or `getInt` + `wasNull`. |
| Using `DOUBLE` for money | Floating-point rounding errors affect math. | `DECIMAL` in SQL, `BigDecimal` in Java. |

Another design error is replacing every `NULL` with a sentinel like `-1`, `'N/A'`, or a fake date. Sentinels become **real values** to the SQL engine: they get averaged, compared, stored as invalid foreign keys, or included in statistics. Use a sentinel only when it is genuinely a meaningful domain value governed by consistent rules.

## 10. Self-Check

Given a test dataset:

| id | score |
| --- | --- |
| 1 | 5 |
| 2 | 10 |
| 3 | NULL |

**Question 1.** Which IDs does `WHERE score = 5 OR score <> 5` return? **Answer:** 1 and 2. Row 3 produces UNKNOWN on both comparisons, so UNKNOWN OR UNKNOWN = UNKNOWN.

**Question 2.** Do `WHERE NOT (score = 5)` and `WHERE score IS DISTINCT FROM 5` return the same result? **Answer:** No. The first returns id 2; the second (in supporting DBMSs) returns ids 2 and 3.

**Question 3.** What are `COUNT(*)`, `COUNT(score)`, and `AVG(score)` respectively? **Answer:** 3, 2, and 7.5. `AVG` ignores the NULL row.

**Question 4.** Can a column `quantity INTEGER CHECK (quantity > 0)` accept NULL? **Answer:** Yes, unless `NOT NULL` or another constraint forbids it: `NULL > 0` is UNKNOWN, and `CHECK` only rejects FALSE.

**Question 5.** Why is `NOT EXISTS` usually more reliable than `NOT IN` when a subquery might return NULL? **Answer:** `NOT EXISTS` decides based on whether a row satisfies the correlated condition, whereas a single NULL in `NOT IN`'s value set can turn comparisons into UNKNOWN and cause `WHERE` to reject everything.

### Checklist When Writing Real Queries

- Does the SQL type represent the **exact business meaning** and required precision?
- Does the column allow NULL, and what kind of missingness does NULL represent?
- Have all nullable comparisons in `WHERE`/`HAVING`/`JOIN ON` accounted for UNKNOWN?
- With `LEFT JOIN`, does placing conditions in `ON` vs. `WHERE` preserve the desired row set?
- Are `COUNT`/`AVG`/`SUM` ignoring NULL intentionally, or should missing-value counts be reported separately?
- Could an anti-existence query suffer from `NOT IN` breaking on NULL?
- Does Java/JDBC preserve the distinction between `NULL` and `0`, `false`, empty strings, and defaults?
- Have DBMS-specific syntax/behaviors (`IDENTITY`, `UUID`, `JSONB`, `IS DISTINCT FROM`, date/time types, NULL sorting) been verified on the target DBMS?

**Key takeaway:** Data types determine valid values; `NULL` represents missing values; and SQL expressions can evaluate to **UNKNOWN**. Only **TRUE** conditions pass `WHERE` and `HAVING`. Understanding these three points lets you predict query results accurately before bringing data into Spring.
