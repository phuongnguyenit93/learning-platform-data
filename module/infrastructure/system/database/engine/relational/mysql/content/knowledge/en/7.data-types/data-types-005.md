# BOOLEAN/BOOL, TINYINT, and Validating True/False Domains

In MySQL, `BOOLEAN` and `BOOL` are readable aliases for `TINYINT(1)`. They are not an independent boolean type whose domain consists solely of `TRUE` and `FALSE`. Physically, MySQL still uses a small integer; without constraints, a boolean column can hold values like `2`, `-1`, or `17`.

The distinction between the **stored value**, **how MySQL evaluates expressions in conditional contexts**, and **the domain allowed by business rules** is crucial. A column named `is_active` may be queried as a true/false condition, but that alone does not guarantee the data contains only `0` or `1`. To guarantee the domain, you must design appropriate `NOT NULL`, `DEFAULT`, and `CHECK` definitions, and verify that the MySQL version actually enforces the constraint.

## Learning Objectives

After this lesson, you will be able to:

- Explain the relationship between `BOOLEAN`, `BOOL`, `TINYINT(1)`, and `TINYINT`.
- Distinguish `0`, `1`, non-zero integers, and `NULL` in conditional expressions.
- Recognize why `flag = TRUE` differs from `flag IS TRUE` when data contains out-of-domain values.
- Design boolean columns with `NOT NULL`, `DEFAULT`, and `CHECK`.
- Detect invalid boolean data in legacy tables and plan controlled normalization.
- Avoid common pitfalls when aggregating, filtering, and indexing boolean columns.

## 1. What Are BOOLEAN and BOOL Actually?

MySQL defines `BOOL` and `BOOLEAN` as synonyms for `TINYINT(1)`. `TRUE` evaluates to `1`, and `FALSE` evaluates to `0`.

```sql
SELECT
    TRUE AS true_value,
    FALSE AS false_value,
    TRUE + 0 AS true_as_number,
    FALSE + 0 AS false_as_number;
```

The results are `1`, `0`, `1`, and `0`, respectively. You can use `TRUE`/`FALSE` in SQL statements to express intent more clearly:

```sql
CREATE TABLE feature_setting (
    setting_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    feature_name VARCHAR(80) NOT NULL,
    is_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (setting_id)
);

INSERT INTO feature_setting (feature_name, is_enabled)
VALUES ('new_checkout', TRUE),
       ('legacy_report', FALSE);

SELECT setting_id, feature_name, is_enabled
FROM feature_setting;
```

In query results, values typically appear as `1` or `0` because the underlying storage type is `TINYINT(1)`. When inspecting `SHOW CREATE TABLE`, you may also see MySQL display a `BOOLEAN` column as `tinyint(1)`.

## 2. TINYINT and Numeric Value Domains

`TINYINT` is a one-byte integer type. Without `UNSIGNED`, the value ranges are:

| Type | Minimum Value | Maximum Value |
|---|---:|---:|
| `TINYINT` | -128 | 127 |
| `TINYINT UNSIGNED` | 0 | 255 |

`TINYINT(1)` still has the full numeric range of `TINYINT`; the `1` in parentheses is the historical display width, not a digit limit or value count limit. Therefore, `TINYINT(1)` can store `2`, `10`, or `-1` if the value is within the type's range and no constraint prevents it. Display width for integer types was deprecated starting in MySQL 8.0.17; do not rely on it for data validation.

Example creating a `TINYINT(1)` column without constraints:

```sql
CREATE TABLE boolean_without_check (
    id INT NOT NULL PRIMARY KEY,
    enabled TINYINT(1) NOT NULL
);

INSERT INTO boolean_without_check (id, enabled)
VALUES (1, 0), (2, 1), (3, 2), (4, -1);

SELECT id, enabled
FROM boolean_without_check
ORDER BY id;
```

The values `2` and `-1` lie within the signed `TINYINT` range, so they are stored. Naming a column `enabled` or declaring `TINYINT(1)` does not automatically restrict the data domain to `0` and `1`.

For values exceeding the numeric type range, behavior depends on SQL mode. In strict mode, MySQL typically rejects out-of-range values; in non-strict mode, some cases may be clamped to the boundary value with a warning. A constraint validating the boolean domain is still needed even in strict mode, because `2` and `-1` are valid numbers within `TINYINT`.

## 3. How Does MySQL Evaluate Truth Values?

In MySQL boolean contexts, `0` is treated as false and any non-zero number is treated as true. This applies to `WHERE` predicates, `IF()`, and many logical expressions.

```sql
SELECT
    IF(0, 'TRUE', 'FALSE') AS zero_result,
    IF(1, 'TRUE', 'FALSE') AS one_result,
    IF(2, 'TRUE', 'FALSE') AS two_result,
    IF(-1, 'TRUE', 'FALSE') AS negative_result;
```

The results are `FALSE`, `TRUE`, `TRUE`, and `TRUE`, respectively. Thus, if a legacy column contains `2` or `-1`, the following query still treats those rows as true:

```sql
SELECT id, enabled
FROM boolean_without_check
WHERE enabled;
```

### 3.1. `= TRUE` Differs from `IS TRUE`

This is an easy source of bugs when data contains non-standard values:

```sql
SELECT
    enabled,
    enabled = TRUE AS equals_true,
    enabled IS TRUE AS is_true,
    enabled = FALSE AS equals_false,
    enabled IS FALSE AS is_false
FROM boolean_without_check
ORDER BY id;
```

`TRUE` is the numeric constant `1`, and `FALSE` is the numeric constant `0`. Therefore, `enabled = TRUE` only matches values equal to `1`; `enabled IS TRUE` checks whether the value evaluates as true—meaning non-zero and not `NULL`. Similarly, `enabled = FALSE` and `enabled IS FALSE` evaluate false according to truth-test semantics.

| Stored Value | `value = TRUE` | `value IS TRUE` | `value = FALSE` | `value IS FALSE` |
|---:|---:|---:|---:|---:|
| `0` | 0 | 0 | 1 | 1 |
| `1` | 1 | 1 | 0 | 0 |
| `2` | 0 | 1 | 0 | 0 |
| `-1` | 0 | 1 | 0 | 0 |
| `NULL` | `NULL` | 0 | `NULL` | 0 |

When the schema guarantees only `0` and `1`, both `= TRUE` and `IS TRUE` behave identically as expected. When you are unsure whether the data is clean, use explicit predicates and inspect the value domain before drawing conclusions.

### 3.2. NULL Produces the UNKNOWN State

SQL uses three-valued logic: `TRUE`, `FALSE`, and `UNKNOWN`. When an expression involves `NULL`, the result is often `UNKNOWN` (displayed as `NULL`). Example:

```sql
SELECT
    NULL = TRUE AS null_equals_true,
    NULL = FALSE AS null_equals_false,
    NULL IS TRUE AS null_is_true,
    NULL IS FALSE AS null_is_false,
    NULL IS UNKNOWN AS null_is_unknown;
```

The two `=` comparisons yield `NULL`; `IS TRUE` and `IS FALSE` return `0`; `IS UNKNOWN` returns `1`. In a `WHERE` clause, rows whose condition evaluates to `UNKNOWN` are not selected.

`NULL` is not synonymous with `FALSE`. If a field can legitimately be in an unknown state—such as an unverified status—decide explicitly whether to store `NULL` or use a dedicated business status. Do not blindly convert every `NULL` to `0` if doing so erases the "unknown" distinction.

## 4. Designing Boolean Columns to Enforce a 0/1 Domain

A column representing true/false typically requires three decisions:

1. Is the column required to have a value? If yes, declare `NOT NULL`.
2. What is the default when omitted? Use `DEFAULT TRUE` or `DEFAULT FALSE` per business rules.
3. Should the database reject any value outside `0` and `1`? Use `CHECK`.

Example:

```sql
CREATE TABLE account_preference (
    account_id BIGINT UNSIGNED NOT NULL,
    email_notifications BOOLEAN NOT NULL DEFAULT TRUE,
    marketing_consent BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (account_id),
    CONSTRAINT chk_email_notifications_boolean
        CHECK (email_notifications IN (0, 1)),
    CONSTRAINT chk_marketing_consent_boolean
        CHECK (marketing_consent IN (0, 1))
) ENGINE = InnoDB;
```

Both constraints enforce that values belong to the set `0` or `1`. `NOT NULL` forbids unknown values; `DEFAULT` only applies when a statement omits the column or explicitly specifies `DEFAULT`, and it does not silently replace an explicitly passed `NULL`.

### 4.1. Why Are Both NOT NULL and CHECK Needed?

In MySQL, a `CHECK` expression passes if it evaluates to `TRUE` or `UNKNOWN`; only `FALSE` violates the constraint. Hence, writing only:

```sql
CHECK (marketing_consent IN (0, 1))
```

does not prevent `NULL` if the column is nullable. When `marketing_consent` is `NULL`, the `IN` expression evaluates to `UNKNOWN`, so `CHECK` does not reject it. If the business requires strictly one of two states, combine it with `NOT NULL`.

If `NULL` has genuine business meaning, you can allow nulls and use the constraint to accept only `NULL`, `0`, and `1`; in that case, document the meaning of all three states and handle them consistently in queries.

### 4.2. MySQL Versions That Enforce CHECK

MySQL enforces `CHECK` constraints starting in version 8.0.16. Older MySQL versions may accept the syntax while ignoring enforcement. Therefore, before relying on `CHECK` to protect a boolean domain, check the version:

```sql
SELECT VERSION();
```

After creating the table, inspect the constraint definition:

```sql
SHOW CREATE TABLE account_preference;
```

On versions exposing `ENFORCED` metadata, you can verify constraint status directly:

```sql
SELECT
    tc.CONSTRAINT_NAME,
    tc.ENFORCED,
    cc.CHECK_CLAUSE
FROM information_schema.table_constraints AS tc
JOIN information_schema.check_constraints AS cc
    ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
   AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
WHERE tc.TABLE_SCHEMA = DATABASE()
  AND tc.TABLE_NAME = 'account_preference'
  AND tc.CONSTRAINT_TYPE = 'CHECK';
```

On MySQL 8.0.16 and later, confirm the constraint is present and `ENFORCED = 'YES'`. If running an older version that does not enforce `CHECK`, upgrade or apply an equivalent validation mechanism appropriate for your architecture; never treat accepted syntax as proof of enforcement.

## 5. Hands-On Validation of Valid and Invalid Data

Run this example in a sandbox database:

```sql
INSERT INTO account_preference
    (account_id, email_notifications, marketing_consent)
VALUES
    (101, TRUE, FALSE),
    (102, FALSE, TRUE),
    (103, 1, 0),
    (104, 0, 1);

SELECT *
FROM account_preference
ORDER BY account_id;
```

Both `TRUE`/`FALSE` and `1`/`0` are stored as `1` or `0`.

The following statements are meant to be run individually and are expected to be rejected:

```sql
-- Value 2 is outside the 0/1 domain
INSERT INTO account_preference
    (account_id, email_notifications, marketing_consent)
VALUES (105, 2, 0);

-- Value -1 is outside the 0/1 domain
INSERT INTO account_preference
    (account_id, email_notifications, marketing_consent)
VALUES (106, -1, 0);

-- NULL violates NOT NULL
INSERT INTO account_preference
    (account_id, email_notifications, marketing_consent)
VALUES (107, NULL, 0);
```

The first two statements violate `CHECK`; the third violates `NOT NULL`. Read the error messages and verify that the constraints are enforced. If `2` or `-1` is still accepted, check the MySQL version, table definition, and constraint enforcement status.

Query rows with true and false values:

```sql
SELECT account_id
FROM account_preference
WHERE marketing_consent IS TRUE;

SELECT account_id
FROM account_preference
WHERE marketing_consent IS FALSE;
```

Because the value domain is constrained, every non-null row falls into one of the two groups. If the column allows `NULL`, query the unknown group separately:

```sql
SELECT account_id
FROM account_preference
WHERE marketing_consent IS NULL;
```

## 6. BOOL/BOOLEAN or TINYINT?

Because `BOOL` and `BOOLEAN` are aliases for `TINYINT(1)`, these three declarations do not create three distinct storage types. The main difference is the intent conveyed to readers of the schema.

| Declaration | Recommended Usage | Notes |
|---|---|---|
| `BOOLEAN` | True/false fields | Most readable when the business domain is boolean |
| `BOOL` | Equivalent to `BOOLEAN` | Valid, though less common in modern schemas |
| `TINYINT` | Small integer with multiple numeric states | Use when a numeric range wider than boolean is needed |
| `TINYINT(1)` | Storage alias commonly seen after declaring boolean | `(1)` does not restrict values to 0/1 |
| `TINYINT UNSIGNED` | Small non-negative integer | Suitable for small counts or numeric status codes; add a separate constraint if the domain is finite |

If a column represents a true/false attribute, using `BOOLEAN` makes intent clear. If a column stores a multi-state status such as `PENDING`, `APPROVED`, `REJECTED`, avoid cramming it into a boolean or undocumented numeric code. Use `VARCHAR` with `CHECK`, `ENUM` where appropriate, or a status lookup table if extensibility and state governance are needed.

## 7. NULL, DEFAULT, and Business Meaning

Not every boolean column should default to `FALSE`. Determine the meaning of omitting a value:

| Scenario | Suggested Design |
|---|---|
| Omitting the value means disabled | `BOOLEAN NOT NULL DEFAULT FALSE` |
| Omitting the value means enabled by policy | `BOOLEAN NOT NULL DEFAULT TRUE` |
| State is unknown and must remain distinct from false | `BOOLEAN NULL` with explicit null-handling rules |
| Three distinct business states exist | Consider a `status` column with named values like `PENDING`, `YES`, `NO` |

Example of a verification flag:

```sql
CREATE TABLE customer_verification (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    is_verified BOOLEAN NULL,
    CONSTRAINT chk_customer_is_verified
        CHECK (is_verified IN (0, 1))
);
```

In this design, `NULL` can mean no verification result yet; `0` means verified and failed; `1` means verified and passed. If business rules must also distinguish pending, rejected, expired, or documentation-needed states, a `verification_status` column with named states is usually clearer than a nullable boolean.

## 8. Filtering, Aggregating, and Summarizing Booleans

When the domain is guaranteed to be `0` and `1`, numeric aggregations can be used:

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(marketing_consent) AS rows_with_known_value,
    SUM(marketing_consent) AS consented_rows,
    SUM(marketing_consent = TRUE) AS consented_rows_by_comparison,
    SUM(marketing_consent IS FALSE) AS declined_rows
FROM account_preference;
```

`COUNT(*)` counts all rows; `COUNT(column)` ignores `NULL`; `SUM(boolean_column)` adds the stored numeric values. If the column contains `2` or `-1`, `SUM()` no longer represents the count of true rows. With nullable data, `SUM()` also ignores `NULL` and can return `NULL` when no rows match; use `COALESCE` if reports must show `0`.

To accurately count truthy rows even when legacy data has non-zero integers:

```sql
SELECT COUNT(*) AS truthy_rows
FROM boolean_without_check
WHERE enabled IS TRUE;
```

For business queries on normalized columns, use explicit predicates such as `is_enabled = TRUE`, `is_enabled IS TRUE`, or `is_enabled = 1` per team convention. What matters most is that the schema enforces the domain so queries do not depend on anomalous data.

### 8.1. Should You Create a Separate Index on a Boolean?

Boolean columns typically have only two values, meaning low cardinality. A standalone index on a `0`/`1` column may not help if each value matches a large portion of the table. The optimizer may prefer a full table scan because traversing an index and fetching many rows randomly is still costly.

If queries frequently filter on a boolean combined with another column, evaluate a composite index ordered by real query selectivity, such as `(is_enabled, created_at)`. Test with `EXPLAIN` on realistic data volumes and measure before/after timings; never add an index solely because a column appears in `WHERE`.

## 9. Detecting and Normalizing Boolean Data in Legacy Tables

A system may have used `TINYINT(1)` for years without `CHECK`. Before adding a constraint, profile all existing values:

```sql
SELECT enabled, COUNT(*) AS row_count
FROM legacy_feature
GROUP BY enabled
ORDER BY enabled;
```

Find rows outside the expected domain while checking `NULL` separately:

```sql
SELECT id, enabled
FROM legacy_feature
WHERE enabled IS NULL
   OR enabled NOT IN (0, 1);
```

Do not use only `enabled NOT IN (0,1)` to find bad data if the column is nullable: comparing against `NULL` yields `UNKNOWN`, so null rows will not be returned by `WHERE`.

Before modifying data, verify the meaning of each legacy value with business owners. For example, `2` might have meant "pending" and `-1` might have meant "not applicable". Never automatically map every non-zero value to `1`, as doing so can destroy state information.

A safe migration workflow:

1. Count occurrences of each distinct value, null rows, and affected record scope.
2. Define mapping rules from legacy values to `0`, `1`, or new statuses with business stakeholders.
3. Back up and test the migration on a copy of the data.
4. Run updates in batches or within an appropriate change window, verifying row counts before and after.
5. Verify no out-of-domain values remain; add the constraint only after the data satisfies it.
6. Audit applications, reports, APIs, and background jobs to ensure none send out-of-domain values.

Once the data is cleaned and the column is required:

```sql
ALTER TABLE legacy_feature
    MODIFY enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ADD CONSTRAINT chk_legacy_feature_enabled
        CHECK (enabled IN (0, 1));
```

Only use `DEFAULT FALSE` if the business confirms false is the intended default. If `NULL` is meaningful, do not add `NOT NULL` until proper handling and backfill rules are in place. `ALTER TABLE` can rebuild the table or acquire locks depending on MySQL version, engine, table size, and change type; evaluate duration, resources, and deployment windows before running in production.

## 10. Common Mistakes

- Assuming `BOOLEAN` is a dedicated type that only accepts `TRUE` or `FALSE`; MySQL uses `TINYINT(1)`.
- Assuming `TINYINT(1)` stores only a single digit or two values; display width does not limit numeric range.
- Writing `WHERE flag` and assuming data only contains `1`; any non-zero number is truthy in conditional context.
- Using `flag = TRUE` when intending to match all truthy values; that comparison only checks equality with `1`.
- Adding `CHECK` without `NOT NULL`, allowing `NULL` to pass because the constraint expression evaluates to `UNKNOWN`.
- Relying on `CHECK` in MySQL versions earlier than 8.0.16, where constraints are not enforced.
- Blindly converting all non-zero values to `1` without checking business semantics.
- Using a boolean to represent a multi-state workflow such as pending, approved, rejected, and expired.
- Creating a standalone index on a low-cardinality boolean column without verifying with `EXPLAIN`.

## 11. Boolean Design and Verification Checklist

- Confirmed whether the column truly has only two states or needs multiple business states.
- Chose `BOOLEAN`/`BOOL` for true/false semantics or `TINYINT` when a wider small-integer range is needed.
- Understood that `BOOLEAN` is an alias for `TINYINT(1)` and display width does not constrain values.
- Explicitly decided whether `NULL` has meaning.
- Specified `NOT NULL` when strictly two states are allowed.
- Selected `DEFAULT TRUE` or `DEFAULT FALSE` according to business rules.
- Added `CHECK (column IN (0,1))` if the MySQL version enforces constraints.
- Verified server version, `SHOW CREATE TABLE`, and `ENFORCED` status.
- Audited legacy data before adding constraints or changing column types.
- Tested queries against `0`, `1`, non-zero integers, and `NULL`.
- Evaluated boolean indexes based on selectivity and real queries.

In MySQL, the `BOOLEAN` type name improves schema readability but does not automatically enforce true/false data integrity. `TINYINT(1)` can still hold various integers, and SQL conditions treat any non-zero number as true. Combining `NOT NULL`, `DEFAULT`, and version-verified `CHECK` constraints—alongside auditing legacy data before migration—ensures clear, consistent boolean domains from database to application.
