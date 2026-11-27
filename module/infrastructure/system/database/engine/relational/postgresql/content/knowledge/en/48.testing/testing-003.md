# Testing Constraints, NULLs, Time Zones, and Data Type Boundaries

Database testing is not just confirming that an SQL statement runs successfully. A correct schema must reject invalid data, accept valid data at boundaries, handle NULL according to SQL semantics, store instants consistently across time zones, and prevent unintended overflow or rounding. These bugs often appear on uncommon values: empty strings, NULL, leap days, DST transition instants, numbers right next to type limits, decimals with many digits, multi-byte strings, or two transactions writing the same key concurrently.

In PostgreSQL, constraints are enforced on the server and protect data regardless of whether it arrives from an application, batch job, import, or SQL console. However, constraints are only correct when designed around business rules and tested with valid values, invalid values, NULL, lower bounds, upper bounds, and concurrent operations.

The testing workflow in this lesson centers on four areas:

1. **Constraints:** NOT NULL, CHECK, UNIQUE, PRIMARY KEY, FOREIGN KEY, exclusion, and deferrable constraints.
2. **NULL:** three-valued logic, NULL in UNIQUE/FK/CHECK, NULL in expressions, arrays, and JSON.
3. **Time:** date/time/timestamp/timestamptz, UTC, timezone conversion, DST gaps/folds, and interval.
4. **Type boundaries:** integer/numeric/floating-point, text/byte length, date/time ranges, casts, rounding, and overflow.

This lesson belongs to the **Testing** chapter of the *Database Engine Relational PostgreSQL* module. The goal is to design repeatable test cases, explain why an input must be accepted or rejected, and uncover bugs that only show up at boundaries or under concurrency.

After this lesson, you will be able to:

- Build a test matrix for each constraint.
- Distinguish SQL NULL, empty string, zero, and JSON null.
- Predict the outcome of TRUE/FALSE/UNKNOWN expressions.
- Test UNIQUE with NULL and NULLS NOT DISTINCT.
- Test FOREIGN KEY with NULL and composite keys.
- Test deferred constraints at the end of a transaction.
- Test timezone conversion and DST transitions.
- Choose the right timestamp type for instants, local time, and calendar dates.
- Verify overflow, rounding, precision/scale, and text length.
- Use transactions/savepoints to isolate expected errors.
- Check race conditions using two sessions.
- Organize SQL tests and pgTAP into a regression suite.

---

## 1. Data Testing Principles

### 1.1. Test business rules at the database boundary

Applications can validate input before sending SQL, but application-layer validation does not replace database constraints. Multiple writers may access the database concurrently; an import script or another service may bypass application validation.

For example, an application checks that an email does not exist yet and then runs INSERT. Two concurrent requests may both read that the email does not exist and both run INSERT. A UNIQUE constraint is the final safeguard ensuring only one transaction succeeds.

### 1.2. Distinguish acceptance tests from rejection tests

Each rule needs at least two groups:

- **Positive test:** valid values are stored and read back accurately.
- **Negative test:** invalid values are rejected with the expected constraint/error.

A test that only checks whether an INSERT statement succeeds is not enough. You must verify that the data is stored with the right representation and is not truncated, rounded, or timezone-shifted unintentionally.

### 1.3. Test boundary values

For each type/rule, identify:

- Smallest valid value.
- Largest valid value.
- Value immediately below the minimum.
- Value immediately above the maximum.
- NULL if the column/rule allows it.
- Empty string/empty array/empty range if meaningful.
- Repeated or conflicting values.
- Values with precision/length right at the limit.

For example, CHECK quantity BETWEEN 1 AND 100 needs tests for 0, 1, 2, 99, 100, 101, and NULL. Do not only test a normal value like 10.

### 1.4. Identify the layer being tested

A database test can exercise multiple layers:

| Layer | Question |
|---|---|
| Parser/type input | Is the literal parsed into the type? |
| Cast/conversion | Is the conversion accurate and lossless? |
| Constraint | Does the database accept/reject correctly? |
| Transaction | Does the error roll back the right scope? |
| Concurrency | Do two concurrent transactions violate an invariant? |
| Client/driver | Do sent/received values preserve timezone/precision? |

When a test fails, isolate the layers to find the root cause. For example, a shifted timestamp could come from session TimeZone, driver serialization, or the application converting the instant incorrectly before sending SQL.

### 1.5. Use independent fixtures and repeatable tests

Tests should create the data they need without depending on the execution order of other tests. Use a dedicated test schema/database, transaction rollback, or fixture setup/teardown. Avoid relying on specific sequence values unless the sequence is reset in the fixture.

### 1.6. Check SQLSTATE and constraint name

Negative tests should verify the error type, not just that "an exception occurred." PostgreSQL SQLSTATE codes are more stable than message text. For example:

| Error | SQLSTATE |
|---|---|
| not_null_violation | 23502 |
| foreign_key_violation | 23503 |
| unique_violation | 23505 |
| check_violation | 23514 |
| exclusion_violation | 23P01 |
| numeric_value_out_of_range | 22003 |
| invalid_datetime_format | 22007 |
| datetime_field_overflow | 22008 |

Constraint names make tests clearer when a table has multiple constraints of the same kind. Do not depend on exact error message wording unless necessary.

---

## 2. Preparing the Test Environment

### 2.1. Verify server and session settings

Some results depend on server version, collation, timezone database, and session settings. Record the environment:

```sql
SELECT
    version(),
    current_setting('server_version') AS server_version,
    current_setting('TimeZone') AS timezone,
    current_setting('DateStyle') AS date_style,
    current_setting('IntervalStyle') AS interval_style,
    current_setting('lc_numeric') AS lc_numeric;
```

Check encoding and collation:

```sql
SHOW server_encoding;
SHOW client_encoding;

SELECT
    datname,
    pg_encoding_to_char(encoding) AS encoding,
    datcollate,
    datctype
FROM pg_database
WHERE datname = current_database();
```

### 2.2. Use a dedicated test schema

```sql
CREATE SCHEMA IF NOT EXISTS test_constraints;
SET search_path = test_constraints, public;
```

In test automation, schema-qualify object names or set `search_path` explicitly. Do not let tests accidentally resolve tables/functions with the same name in another schema.

### 2.3. Transactions and savepoints

For manual SQL testing, savepoints allow continuing after an expected-to-fail statement:

```sql
BEGIN;

SAVEPOINT before_invalid_insert;
INSERT INTO test_constraints.accounts(account_id, balance)
VALUES (1, -10);

-- After observing the error, roll back to the savepoint:
ROLLBACK TO SAVEPOINT before_invalid_insert;

-- Continue with other assertions:
SELECT count(*) FROM test_constraints.accounts;

ROLLBACK;
```

When a statement fails inside a transaction, the transaction enters an aborted state until rolled back or rolled back to a savepoint. An automated harness typically catches the exception on the client and rolls back the corresponding transaction.

### 2.4. Test database, not production

Negative tests intentionally trigger constraint violations, locks, and transaction aborts. Run them in a test database with isolated fixtures. Do not experiment by inserting dummy data into production tables and deleting it afterward.

---

## 3. Testing NOT NULL and CHECK Constraints

### 3.1. NOT NULL

NOT NULL ensures a column cannot contain SQL NULL:

```sql
CREATE TABLE test_constraints.products (
    product_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text NOT NULL,
    price numeric(12,2) NOT NULL
);
```

Test these cases:

| Input | Expected result |
|---|---|
| sku = 'A-100', price = 10.00 | Accepted |
| sku = NULL | Rejected |
| price = NULL | Rejected |
| sku = '', price = 0 | NOT NULL accepts; other rules decide |
| sku = '   ', price = 0 | NOT NULL accepts; other rules decide |

NOT NULL does not mean non-empty. If empty strings are invalid, add a CHECK constraint:

```sql
ALTER TABLE test_constraints.products
ADD CONSTRAINT products_sku_not_blank
CHECK (length(btrim(sku)) > 0);
```

For text containing Unicode whitespace or special space characters, `btrim` by default does not necessarily strip every kind of whitespace. If business rules define whitespace more broadly, use an explicit normalization function and test according to encoding/collation.

### 3.2. CHECK constraint

A CHECK constraint accepts a row when the expression evaluates to TRUE or NULL/UNKNOWN; only FALSE violates it. This is a common pitfall:

```sql
CREATE TABLE test_constraints.accounts (
    account_id bigint PRIMARY KEY,
    balance numeric(12,2),
    CONSTRAINT accounts_balance_nonnegative
        CHECK (balance >= 0)
);
```

Inserting `balance = -1` is rejected, but `balance = NULL` is accepted because `NULL >= 0` returns UNKNOWN. If `balance` is required, declare NOT NULL separately.

### 3.3. Test the three states of CHECK

```sql
SELECT
    (-1 >= 0) AS negative_check,
    (0 >= 0) AS zero_check,
    (NULL::numeric >= 0) AS null_check;
```

The results are FALSE, TRUE, and NULL respectively. Therefore, CHECK does not automatically turn UNKNOWN into a violation.

### 3.4. Combining CHECK and NOT NULL

```sql
CREATE TABLE test_constraints.inventory (
    item_id bigint PRIMARY KEY,
    quantity integer NOT NULL,
    CONSTRAINT inventory_quantity_range
        CHECK (quantity BETWEEN 0 AND 100000)
);
```

Test NULL, -1, 0, 1, 100000, and 100001. The two rules serve distinct purposes: NOT NULL forbids absence; CHECK restricts the value domain.

### 3.5. Multi-column CHECK

```sql
CREATE TABLE test_constraints.discount (
    regular_price numeric(12,2) NOT NULL,
    sale_price numeric(12,2) NOT NULL,
    CONSTRAINT discount_price_order
        CHECK (sale_price <= regular_price),
    CONSTRAINT discount_price_nonnegative
        CHECK (sale_price >= 0 AND regular_price >= 0)
);
```

Test:

- Sale price equal to regular price.
- Sale price less than regular price.
- Sale price greater than regular price.
- Price equal to 0.
- Negative price.
- NULL in each column.

If both columns are NOT NULL, NULL cases are blocked by NOT NULL before CHECK is evaluated.

### 3.6. CHECK is not a cross-row constraint

CHECK should evaluate the current row. PostgreSQL does not guarantee that a CHECK constraint can maintain invariants based on other rows or values that change over time. For example, a CHECK depending on `SELECT max` from another table is not supported as a guarantee for cross-row integrity.

For cross-row invariants, consider UNIQUE, FOREIGN KEY, EXCLUDE, transaction logic, or carefully designed triggers.

### 3.7. Inspecting existing constraints

List constraints:

```sql
SELECT
    conname,
    contype,
    convalidated,
    condeferrable,
    condeferred,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'test_constraints.inventory'::regclass
ORDER BY conname;
```

`convalidated = false` indicates the constraint has not yet been validated against all existing data. When testing migrations, verify that validation completes as expected.

---

## 4. Testing UNIQUE and PRIMARY KEY

### 4.1. Basic UNIQUE

```sql
CREATE TABLE test_constraints.customer_email (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL,
    CONSTRAINT customer_email_unique UNIQUE (email)
);
```

Positive test: insert a new email. Negative test: insert the same email a second time. Verify SQLSTATE 23505 and constraint name `customer_email_unique`.

### 4.2. NULL in default UNIQUE

By default, PostgreSQL treats NULL values as distinct in a unique constraint/index. Thus, a nullable UNIQUE column can hold multiple NULL rows:

```sql
CREATE TABLE test_constraints.external_identity (
    identity_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider_subject text UNIQUE
);

INSERT INTO test_constraints.external_identity(provider_subject)
VALUES (NULL), (NULL);
```

Both rows above are accepted by default. This may be appropriate if NULL means "no external identity yet."

### 4.3. NULLS NOT DISTINCT

If business rules allow at most one row without a value, PostgreSQL supports:

```sql
CREATE TABLE test_constraints.optional_code (
    row_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text,
    CONSTRAINT optional_code_unique
        UNIQUE NULLS NOT DISTINCT (code)
);
```

Test:

1. Insert one NULL: succeeds.
2. Insert a second NULL: unique violation.
3. Insert two different codes: succeeds.
4. Insert an existing code: unique violation.

NULLS NOT DISTINCT is an option on unique constraints/indexes in supported PostgreSQL versions; check the target major version before using it.

### 4.4. Composite UNIQUE

```sql
CREATE TABLE test_constraints.membership (
    tenant_id bigint NOT NULL,
    username text NOT NULL,
    CONSTRAINT membership_tenant_username_uq
        UNIQUE (tenant_id, username)
);
```

Test that the same username across two different tenants is accepted, while the same tenant and username is rejected. This is why testing individual columns separately is insufficient: the invariant applies to the multi-column tuple.

### 4.5. Composite UNIQUE and NULL

With default UNIQUE, rows `(1, NULL)` and `(1, NULL)` can coexist because NULLs are treated as distinct. If different semantics are needed, use NULLS NOT DISTINCT or normalize data into a non-nullable key according to business rules.

### 4.6. PRIMARY KEY

PRIMARY KEY is equivalent to unique and not-null for the column set:

```sql
CREATE TABLE test_constraints.document_key (
    tenant_id bigint,
    document_id bigint,
    PRIMARY KEY (tenant_id, document_id)
);
```

Test duplicate composite keys and NULL in each component. PRIMARY KEY does not allow any component to be NULL.

### 4.7. Case sensitivity and collation

UNIQUE on text follows the equality semantics of the type/collation/index opclass. `Alice@example.test` and `alice@example.test` can be treated as two different values under standard collations.

If business rules require case-insensitive uniqueness, define the semantics explicitly, for example:

```sql
CREATE UNIQUE INDEX customer_email_lower_uq
ON test_constraints.customer_email (lower(email));
```

Test case variants, Unicode case folding, and the collation provider matching your requirements. `lower()` under a collation is not identical to every application Unicode normalization/case-folding algorithm.

### 4.8. Partial unique index

```sql
CREATE TABLE test_constraints.users (
    user_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL,
    deleted_at timestamptz
);

CREATE UNIQUE INDEX users_active_email_uq
ON test_constraints.users (lower(email))
WHERE deleted_at IS NULL;
```

Test that two active users with the same email are rejected; after one user is soft-deleted, a new active row can reuse that email. Query predicates must be compatible with the partial index predicate for the planner to use the index.

### 4.9. UNIQUE and concurrency

Uniqueness cannot be tested only with a single sequential session. Two sessions can both check "does not exist" and then both insert. A UNIQUE index resolves this race in the database.

Test with two sessions:

1. Session A starts a transaction and inserts key K.
2. Session B inserts the same key K before A commits.
3. Session B may wait for the outcome of transaction A.
4. If A commits, B receives a unique violation.
5. If A rolls back, B can insert successfully.

Tests must verify the final invariant rather than depending on exact timing or message text.

---

## 5. Testing FOREIGN KEY, Exclusion, and Deferrable Constraints

### 5.1. Basic FOREIGN KEY

```sql
CREATE TABLE test_constraints.departments (
    department_id bigint PRIMARY KEY,
    name text NOT NULL
);

CREATE TABLE test_constraints.employees (
    employee_id bigint PRIMARY KEY,
    department_id bigint,
    CONSTRAINT employees_department_fk
        FOREIGN KEY (department_id)
        REFERENCES test_constraints.departments(department_id)
);
```

Test inserting an employee with an existing `department_id`: succeeds. Inserting a nonexistent `department_id`: foreign key violation. Deleting a referenced department: outcome depends on the ON DELETE action.

### 5.2. NULL in FOREIGN KEY

By default (`MATCH SIMPLE`), if any component of a foreign key is NULL, the row does not need to match a referenced row. Therefore, a nullable FK can contain NULL.

If the relationship is mandatory, declare the FK column NOT NULL. FK and NOT NULL are two separate rules.

### 5.3. Composite foreign keys and MATCH SIMPLE

```sql
CREATE TABLE test_constraints.tenant_users (
    tenant_id bigint NOT NULL,
    user_id bigint NOT NULL,
    PRIMARY KEY (tenant_id, user_id)
);

CREATE TABLE test_constraints.audit_events (
    event_id bigint PRIMARY KEY,
    tenant_id bigint,
    user_id bigint,
    FOREIGN KEY (tenant_id, user_id)
        REFERENCES test_constraints.tenant_users(tenant_id, user_id)
);
```

With MATCH SIMPLE, if `tenant_id` or `user_id` is NULL, the FK check is skipped. This can allow partial-null states that business rules do not intend.

### 5.4. MATCH FULL

MATCH FULL requires all FK columns to be NULL or all to be non-NULL and match a referenced row:

```sql
ALTER TABLE test_constraints.audit_events
ADD CONSTRAINT audit_events_tenant_user_fk
FOREIGN KEY (tenant_id, user_id)
REFERENCES test_constraints.tenant_users(tenant_id, user_id)
MATCH FULL;
```

Test:

- `(NULL, NULL)`: accepted.
- `(10, 20)` with parent: accepted.
- `(10, 20)` without parent: rejected.
- `(10, NULL)`: rejected.
- `(NULL, 20)`: rejected.

MATCH PARTIAL cannot be used in PostgreSQL.

### 5.5. ON DELETE and ON UPDATE

Common actions:

| Action | Meaning |
|---|---|
| NO ACTION | Raises an error if the constraint is still violated when checked |
| RESTRICT | Immediately rejects the referenced operation, without allowing deferral the way NO ACTION can |
| CASCADE | Deletes/updates corresponding child rows |
| SET NULL | Sets FK columns to NULL |
| SET DEFAULT | Sets FK columns to their default |

Test each action on both parent delete and parent key update. With SET NULL/SET DEFAULT, also check NOT NULL, CHECK, and defaults on the child table; the action can still fail if the post-update state violates another rule.

### 5.6. Deferrable constraints

Some constraints can have their check deferred until the end of the transaction:

```sql
CREATE TABLE test_constraints.nodes (
    node_id integer PRIMARY KEY,
    parent_id integer,
    CONSTRAINT nodes_parent_fk
        FOREIGN KEY (parent_id)
        REFERENCES test_constraints.nodes(node_id)
        DEFERRABLE INITIALLY DEFERRED
);
```

This allows a transaction to create/update multiple rows where an intermediate state temporarily violates the FK, as long as the end of the transaction is valid.

### 5.7. SET CONSTRAINTS

```sql
BEGIN;
SET CONSTRAINTS nodes_parent_fk DEFERRED;

INSERT INTO test_constraints.nodes(node_id, parent_id)
VALUES (2, 1);

INSERT INTO test_constraints.nodes(node_id, parent_id)
VALUES (1, NULL);

SET CONSTRAINTS nodes_parent_fk IMMEDIATE;
COMMIT;
```

`SET CONSTRAINTS ... IMMEDIATE` checks deferred violations immediately when switching modes. Test both commit-time failures and explicit `SET CONSTRAINTS` failures.

### 5.8. Deferrable UNIQUE

PostgreSQL supports deferrable UNIQUE constraints:

```sql
CREATE TABLE test_constraints.display_order (
    item_id integer PRIMARY KEY,
    position integer,
    CONSTRAINT display_order_position_uq
        UNIQUE (position)
        DEFERRABLE INITIALLY DEFERRED
);
```

Deferrable uniqueness can be used when swapping positions within a single transaction. However, deferrable unique constraints cannot be used as ON CONFLICT arbiters; verify application semantics before choosing this.

### 5.9. Exclusion constraints

An exclusion constraint guarantees that for any two rows, at least one specified operator comparison returns FALSE or NULL. It is commonly used to prevent overlaps:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE test_constraints.reservations (
    room_id integer NOT NULL,
    during tstzrange NOT NULL,
    EXCLUDE USING gist (
        room_id WITH =,
        during WITH &&
    )
);
```

Test same room with overlapping ranges: rejected. Same room with adjacent, non-overlapping ranges: accepted if bounds are defined appropriately. Different rooms with the same range: accepted.

### 5.10. Exclusion and NULL

Exclusion semantics can allow a pair when an operator comparison returns NULL. If `room_id` or `range` can be NULL, test explicitly and usually add NOT NULL if business rules require a value. Do not assume exclusion implicitly replaces NOT NULL.

### 5.11. Exclusion and concurrency

Two sessions booking the same resource/time range can run concurrently. The exclusion constraint must ensure two conflicting reservations cannot both commit. Test with two sessions and confirm one transaction is rejected or waits depending on interleaving.

---

## 6. NULL and Three-Valued Logic

### 6.1. NULL is not a regular value

NULL represents absence/unknown under SQL semantics. It is distinct from:

- Zero: the number 0 is a valid numeric value.
- Empty string: text of length zero.
- Empty array: an array with no elements.
- Empty range: an empty range.
- JSON null: a JSON value named null.

Applications often conflate these concepts into "blank," but the database distinguishes them.

### 6.2. TRUE, FALSE, and UNKNOWN

SQL boolean expressions have three logical outcomes. Comparing NULL with a value using standard operators returns UNKNOWN:

```sql
SELECT
    NULL = NULL AS eq,
    NULL <> NULL AS ne,
    NULL < 10 AS less_than,
    NULL IS NULL AS is_null,
    NULL IS NOT NULL AS is_not_null;
```

The first three expressions return NULL; the two IS NULL/IS NOT NULL expressions return TRUE/FALSE.

### 6.3. AND truth table

| A | B | A AND B |
|---|---|---|
| TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE |
| TRUE | NULL | NULL |
| FALSE | NULL | FALSE |
| NULL | NULL | NULL |

### 6.4. OR truth table

| A | B | A OR B |
|---|---|---|
| TRUE | NULL | TRUE |
| FALSE | NULL | NULL |
| NULL | NULL | NULL |
| FALSE | FALSE | FALSE |
| TRUE | FALSE | TRUE |

### 6.5. NOT

NOT TRUE = FALSE; NOT FALSE = TRUE; NOT NULL = NULL. Thus, a WHERE clause only keeps rows where the predicate evaluates to TRUE. Both FALSE and UNKNOWN are filtered out.

### 6.6. WHERE and NULL

```sql
SELECT *
FROM test_constraints.products
WHERE price > 0;
```

Rows with NULL price are not returned because the predicate is UNKNOWN. To include NULL rows, write it explicitly:

```sql
SELECT *
FROM test_constraints.products
WHERE price > 0 OR price IS NULL;
```

### 6.7. IS DISTINCT FROM

IS DISTINCT FROM and IS NOT DISTINCT FROM provide NULL-safe comparisons:

```sql
SELECT
    NULL IS DISTINCT FROM NULL AS same_nulls,
    NULL IS DISTINCT FROM 1 AS null_vs_value,
    1 IS NOT DISTINCT FROM 1 AS equal_values;
```

Two NULLs are considered not distinct; NULL and non-NULL are distinct. This is useful for comparing nullable values in tests, UPSERT logic, and change detection.

### 6.8. COALESCE and NULLIF

COALESCE returns the first non-NULL argument:

```sql
SELECT COALESCE(NULL::text, '', 'fallback');
```

The result is an empty string, not `'fallback'`. NULLIF returns NULL when both arguments are equal:

```sql
SELECT NULLIF('', '') IS NULL;
```

Test these expressions when the application converts empty strings to NULL or uses default values.

### 6.9. NOT IN and the NULL trap

```sql
SELECT 5 NOT IN (1, 2, NULL);
```

The result is UNKNOWN, not TRUE, because it cannot be concluded that 5 differs from NULL. Therefore, NOT IN with a subquery that might contain NULL often produces unexpected results. NOT EXISTS with a correlation predicate is usually a safer way to express an anti-join.

### 6.10. NULL in aggregates

`COUNT(*)` counts all rows; `COUNT(column)` ignores NULL. `SUM`/`AVG`/`MIN`/`MAX` generally ignore NULL inputs and return NULL when there are no non-NULL inputs.

```sql
SELECT
    count(*) AS all_rows,
    count(price) AS rows_with_price,
    sum(price) AS total_price,
    avg(price) AS average_price
FROM test_constraints.products;
```

Test empty tables, all-NULL columns, mixed NULL/non-NULL values, and zero values. SUM on an empty or all-NULL input returns NULL; use COALESCE if business rules expect zero.

### 6.11. NULL in DISTINCT and GROUP BY

In GROUP BY and DISTINCT, NULLs are grouped into a single group/equivalence class for deduplication purposes. This differs from default UNIQUE semantics, where multiple NULLs are allowed. Test each context separately rather than inferring behavior from another context.

### 6.12. NULL in arrays

An array can be NULL, an empty array, or contain NULL elements:

```sql
SELECT
    NULL::integer[] AS null_array,
    ARRAY[]::integer[] AS empty_array,
    ARRAY[1, NULL, 3] AS array_with_null;
```

ANY/ALL expressions and array operators can produce UNKNOWN when NULL elements are involved:

```sql
SELECT
    2 = ANY (ARRAY[1, NULL, 3]) AS any_result,
    2 = ALL (ARRAY[1, NULL, 3]) AS all_result;
```

Test NULL arrays, empty arrays, arrays containing NULL, duplicate elements, and array dimensions.

### 6.13. SQL NULL and JSON null

JSONB has a JSON null value that differs from SQL NULL:

```sql
SELECT
    'null'::jsonb IS NULL AS json_null_is_sql_null,
    NULL::jsonb IS NULL AS sql_null_is_sql_null,
    jsonb_typeof('null'::jsonb) AS json_value_type;
```

JSON null is not SQL NULL. For JSONB columns, test column SQL NULL, JSON scalar null, missing keys, and keys with value null. JSON extraction can return SQL NULL when a key does not exist, so check key presence separately if business rules distinguish missing from explicit null.

### 6.14. NULL in UNIQUE, FK, and CHECK

Do not apply a single blanket rule:

- Default UNIQUE allows multiple NULLs.
- UNIQUE NULLS NOT DISTINCT treats NULLs as equal for uniqueness.
- FOREIGN KEY MATCH SIMPLE skips the check if any FK column is NULL.
- CHECK accepts TRUE or UNKNOWN expressions; only FALSE is rejected.
- NOT NULL forbids SQL NULL.

Each rule needs separate testing with both single-column and composite cases.

---

## 7. Date/Time Types and Time Zones in PostgreSQL

### 7.1. Choose the right type for the data semantics

| Type | Meaning | Business example |
|---|---|---|
| date | Calendar date, no time or timezone | Birth date, invoice date |
| time | Time of day, no date or timezone | Opening hours |
| time with time zone | Time of day with offset | Rarely used for business data |
| timestamp without time zone | Local date-time, does not identify an instant | Local appointment time without an attached zone |
| timestamp with time zone (timestamptz) | An instant on the timeline | Timestamp when a payment/event occurred |
| interval | Time span/calendar duration | 2 hours, 3 months |

Do not use `timestamp without time zone` to store a global instant. Do not use `timestamptz` for birth dates or calendar dates just because the application has a timezone.

### 7.2. timestamp without time zone

`timestamp without time zone` stores calendar date/time components without converting by session TimeZone. If a literal has an offset and is cast to `timestamp without time zone`, the offset is ignored:

```sql
SELECT
    timestamp '2026-06-01 09:00:00' AS local_time,
    timestamp '2026-06-01 09:00:00+07' AS offset_ignored;
```

Both literals can produce the same local timestamp. This test is important because the input appears to carry an offset, yet the target type does not preserve it.

### 7.3. timestamptz

`timestamptz` represents an instant. PostgreSQL converts input with an offset/zone into a UTC-based internal instant; on display, the server converts the instant to the session TimeZone.

```sql
SET TIME ZONE 'UTC';
SELECT timestamptz '2026-06-01 09:00:00+07';

SET TIME ZONE 'Asia/Ho_Chi_Minh';
SELECT timestamptz '2026-06-01 09:00:00+07';
```

Both SELECTs display the same instant in two different timezones. The stored value does not change when `SET TIME ZONE` runs; only the output representation changes.

### 7.4. Input without timezone for timestamptz

If a `timestamptz` input has no offset or zone, PostgreSQL interprets it using the session TimeZone at parse time:

```sql
SET TIME ZONE 'UTC';
SELECT timestamptz '2026-06-01 09:00:00';

SET TIME ZONE 'Asia/Ho_Chi_Minh';
SELECT timestamptz '2026-06-01 09:00:00';
```

The two results are two different instants. Therefore, tests must control the session TimeZone, and applications should send instants with explicit offsets or bind an instant properly represented by the driver.

### 7.5. Two-way AT TIME ZONE

AT TIME ZONE has two semantics depending on the input type:

```sql
-- An instant rendered as a local timestamp in a zone:
SELECT timestamptz '2026-06-01 02:00:00+00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh';

-- A local timestamp interpreted in a zone as an instant:
SELECT timestamp '2026-06-01 09:00:00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh';
```

- `timestamptz AT TIME ZONE zone` returns `timestamp without time zone`.
- `timestamp without time zone AT TIME ZONE zone` returns `timestamptz`.

Test the output data type alongside the value; the two directions are not the same conversion.

### 7.6. TimeZone setting

```sql
SHOW TimeZone;
SELECT current_setting('TimeZone');
SELECT current_setting('TimeZone') = 'UTC';
```

TimeZone can be set at the server, database, role, connection, or session level. Test automation should explicitly `SET TIME ZONE` in each connection rather than relying on the test runner host's default.

### 7.7. Time zone names vs. fixed offsets

IANA zones such as `Asia/Ho_Chi_Minh` or `America/New_York` have historical rules and DST changes. Fixed offsets like `+07` have no history or DST. If business logic needs the local time of a location, store the zone name or reference the zone per business rules; a bare offset is insufficient to reproduce all local-time behavior.

### 7.8. Inspecting timezone names

```sql
SELECT name, abbrev, utc_offset, is_dst
FROM pg_timezone_names
WHERE name IN (
    'UTC',
    'Asia/Ho_Chi_Minh',
    'America/New_York',
    'Europe/Berlin'
)
ORDER BY name;
```

Do not rely on ambiguous abbreviations like `CST`. A single abbreviation can represent multiple offsets/regions; use IANA zone names for local calendar logic.

### 7.9. DateStyle and input ambiguity

DateStyle affects how PostgreSQL interprets certain ambiguously formatted date strings:

```sql
SHOW DateStyle;
SET DateStyle = 'ISO, MDY';
SELECT date '01/02/2026';

SET DateStyle = 'ISO, DMY';
SELECT date '01/02/2026';
```

Avoid ambiguous date strings in tests and applications. Use ISO 8601 such as `YYYY-MM-DD` or typed parameters so behavior does not depend on DateStyle.

---

## 8. Testing DST: Skipped Hours and Repeated Hours

### 8.1. DST gap

In regions observing daylight saving time, clocks can jump forward over a local time interval in spring. For example, a zone transitions from `01:59:59` to `03:00:00`; local time `02:30` does not exist.

A local timestamp input without a zone can still be stored as a calendar value because PostgreSQL does not know which zone it represents. When interpreting a local timestamp in an IANA zone as `timestamptz`, test how PostgreSQL resolves nonexistent times.

### 8.2. DST fold

In autumn, clocks can fall back, causing a local time interval to occur twice. For example, `01:30` can correspond to two distinct instants. A `timestamp without time zone` does not hold enough information to distinguish the two occurrences.

### 8.3. America/New_York example

```sql
SET TIME ZONE 'UTC';

SELECT
    timestamp '2026-03-08 02:30:00'
        AT TIME ZONE 'America/New_York' AS spring_gap,
    timestamp '2026-11-01 01:30:00'
        AT TIME ZONE 'America/New_York' AS autumn_fold;
```

Exact dates depend on the year's DST schedule. PostgreSQL applies timezone database rules when interpreting local times; for ambiguous or invalid times, PostgreSQL uses the standard-time offset. For a spring gap, this can produce an instant that renders back to a different local time in that zone than the input.

### 8.4. Testing two instants in a fold

Provide explicit offsets to distinguish both occurrences of `01:30`:

```sql
SELECT
    timestamptz '2026-11-01 01:30:00-04' AS first_occurrence,
    timestamptz '2026-11-01 01:30:00-05' AS second_occurrence,
    timestamptz '2026-11-01 01:30:00-04'
      <> timestamptz '2026-11-01 01:30:00-05' AS different_instants;
```

The two values differ by one hour even though the local clock text is identical.

### 8.5. Round-trip testing

An important test is converting a local timestamp to an instant and back to local time:

```sql
WITH input(local_time) AS (
    VALUES
        (timestamp '2026-03-08 02:30:00'),
        (timestamp '2026-11-01 01:30:00')
)
SELECT
    local_time,
    local_time AT TIME ZONE 'America/New_York' AS instant,
    (local_time AT TIME ZONE 'America/New_York')
        AT TIME ZONE 'America/New_York' AS round_trip
FROM input;
```

At a gap/fold, the round-trip may not preserve the original local timestamp or cannot uniquely identify the instant. Tests must define the business policy: reject nonexistent times, pick the earlier/later occurrence, or require the user to supply an offset.

### 8.6. Local appointment vs. global event

Two kinds of data require different semantics:

- **Appointment at 09:00 at a clinic:** can store local date/time plus an IANA zone, because the appointment is tied to the local calendar.
- **Payment that occurred at an instant:** store `timestamptz`, because it is a single point on the timeline.

For appointments, storing only `timestamptz` can lose the "09:00 local" intent if timezone rules change in the future. For event instants, storing only `timestamp without time zone` loses the zone/offset needed to pinpoint the moment.

### 8.7. Testing timezone database updates

Timezone rules can change due to legislation. When OS/tzdata or PostgreSQL timezone data is updated, test affected future appointments and recurring schedules. Distinguish:

- Past instants: must not change.
- Future local appointments: may need reinterpretation per the new policy.
- Recurring schedules: should retain local time and zone, computing each occurrence under current rules.

---

## 9. Testing Date, Time, and Interval Boundaries

### 9.1. Date boundaries

`date` supports a wider range than typical business dates. Test your application's domain rather than relying only on PostgreSQL limits:

- Start/end of business periods.
- Leap day Feb 29.
- Day before/after leap day.
- Start/end of month.
- Start/end of year.
- Infinity values if the application disallows them.

```sql
SELECT
    date '2024-02-28' + 1 AS leap_day,
    date '2024-02-29' + 1 AS next_day,
    date '2026-01-31' + interval '1 month' AS month_arithmetic;
```

Note that adding an `interval` month to a month-end date follows calendar rules, which is not equivalent to adding a fixed number of days.

### 9.2. Invalid dates

```sql
SELECT date '2024-02-29';
```

This is a valid date. Values like `2023-02-29` or month 13 must be rejected. Test leap years divisible by 4, century years not divisible by 400, and century years divisible by 400.

### 9.3. Time boundaries

Test:

- `00:00:00`.
- `23:59:59.999999`.
- Fractional seconds at higher precision than the target column.
- `24:00:00` if permitted by the PostgreSQL input format/type.
- Leap-second input if the application has special requirements.

Do not assume every client parser and every timezone library handles edge values identically.

### 9.4. Timestamp precision

PostgreSQL timestamps store microsecond resolution. A column typmod can limit fractional precision from 0 to 6:

```sql
CREATE TABLE test_constraints.timestamp_precision (
    ts0 timestamp(0),
    ts3 timestamp(3),
    ts6 timestamp(6)
);

INSERT INTO test_constraints.timestamp_precision
VALUES (
    timestamp '2026-01-01 12:00:00.123456',
    timestamp '2026-01-01 12:00:00.123456',
    timestamp '2026-01-01 12:00:00.123456'
);

SELECT * FROM test_constraints.timestamp_precision;
```

Test rounding/truncation behavior at fractional boundaries. Do not compare timestamps after converting to milliseconds in the application if the database retains microseconds.

### 9.5. Interval is not always a fixed duration

An `interval` has months, days, and time components. A month does not have a fixed number of days; a calendar day does not always equal 24 elapsed hours when DST applies.

```sql
SET TIME ZONE 'America/New_York';

SELECT
    timestamptz '2026-03-07 12:00:00-05' + interval '1 day'
        AS same_local_time_next_day,
    timestamptz '2026-03-07 12:00:00-05' + interval '24 hours'
        AS twenty_four_elapsed_hours;
```

Around DST, the two results can differ. If the business rule is "same local time tomorrow," use calendar arithmetic with an explicit timezone. If it is "after exactly 24 hours," use explicit duration semantics.

### 9.6. Infinity

PostgreSQL `date`/`timestamp` types support `infinity` and `-infinity`. If the application does not expect these values, add a CHECK constraint or validation:

```sql
CREATE TABLE test_constraints.validity_period (
    valid_until timestamptz NOT NULL,
    CHECK (isfinite(valid_until))
);
```

Test both finite minimums/maximums in the business domain and infinity. Do not let special values flow into drivers/clients without an explicit mapping.

### 9.7. Half-open intervals

For validity periods, `[start, end)` intervals—inclusive start, exclusive end—are commonly used:

```sql
SELECT
    tstzrange(
        timestamptz '2026-01-01 00:00:00+00',
        timestamptz '2026-02-01 00:00:00+00',
        '[)'
    ) @> timestamptz '2026-02-01 00:00:00+00' AS includes_end;
```

The result is FALSE. Half-open intervals allow two adjacent ranges without overlap. Test exact start, just-before-end, exact end, and zero-length ranges.

---

## 10. Testing Integer and Numeric Boundaries

### 10.1. Integer ranges

PostgreSQL integer types have these limits:

| Type | Minimum | Maximum |
|---|---:|---:|
| smallint | -32,768 | 32,767 |
| integer | -2,147,483,648 | 2,147,483,647 |
| bigint | -9,223,372,036,854,775,808 | 9,223,372,036,854,775,807 |

Test min, max, min-1, and max+1:

```sql
SELECT
    '-32768'::smallint AS smallint_min,
    '32767'::smallint AS smallint_max,
    '-2147483648'::integer AS integer_min,
    '2147483647'::integer AS integer_max,
    '-9223372036854775808'::bigint AS bigint_min,
    '9223372036854775807'::bigint AS bigint_max;
```

Try out-of-range values in negative tests and verify `numeric_value_out_of_range` (`22003`).

### 10.2. Arithmetic overflow

A value may be valid in a column, yet an operation on it can still overflow:

```sql
SELECT 2147483647::integer + 1;
```

Test arithmetic, casts, and aggregates separately. For example, `SUM(integer)` returns `bigint`, while `SUM(bigint)` returns `numeric` in PostgreSQL; do not assume an aggregate preserves the input type.

### 10.3. Casting from text

Test the input parser with:

- Valid numeric strings.
- Leading/trailing whitespace.
- `+` and `-` signs.
- Empty string.
- Whitespace-only string.
- Decimal into integer.
- Exponent notation.
- Non-numeric characters.
- Out-of-range values.

```sql
SELECT
    ' 42 '::integer,
    '+42'::integer,
    '4.2'::numeric;
```

Invalid casts should be verified with the appropriate SQLSTATE. Do not use regex validation in the application as a substitute for testing the database parser and type conversion.

### 10.4. Numeric precision and scale

`numeric(p,s)` constrains total precision and digits after the decimal point. With `numeric(5,2)`, there are at most 5 significant decimal digits, of which 2 are after the decimal point; the largest positive value is `999.99`.

```sql
CREATE TABLE test_constraints.money_amount (
    amount numeric(5,2) NOT NULL
);

INSERT INTO test_constraints.money_amount VALUES
    (-999.99),
    (-0.01),
    (0),
    (0.01),
    (999.99);
```

Test `1000.00`, which must overflow. Test `1.234` to verify scale handling. Numeric scale coercion can round input to the column's scale before storing; verify the value read back.

### 10.5. Numeric rounding

PostgreSQL `numeric` rounds ties away from zero:

```sql
SELECT
    round( 1.235::numeric, 2) AS positive_tie,
    round(-1.235::numeric, 2) AS negative_tie,
    round( 1.234::numeric, 2) AS below_tie;
```

Test positive/negative numbers, tie values, and values on both sides of a tie. Do not assume `numeric` and floating-point rounding behave the same way.

### 10.6. Numeric column scale coercion

```sql
TRUNCATE test_constraints.money_amount;

INSERT INTO test_constraints.money_amount(amount)
VALUES (12.345), (-12.345);

SELECT amount FROM test_constraints.money_amount ORDER BY amount;
```

Results are coerced to the column scale. Clarify whether business rules require rounding, rejecting, or preserving higher precision; if extra fractional digits must be rejected, separate validation is needed before coercion discards information.

### 10.7. Unconstrained numeric

`numeric` without declared precision/scale can store more digits and larger scale than fixed `numeric(p,s)`. It is suitable for arbitrary-precision decimals but costs more storage/CPU than integer or floating-point. Test business limits with CHECK if arbitrary scales should not be accepted.

### 10.8. Numeric special values

PostgreSQL `numeric` supports `NaN` and in modern versions `Infinity`/`-Infinity`. These special values have specific behavior in comparisons and arithmetic; constrained numeric columns with scale do not necessarily accept infinity. If the domain only allows finite numbers:

```sql
CREATE TABLE test_constraints.finite_measure (
    value numeric NOT NULL,
    CHECK (value <> 'NaN'::numeric),
    CHECK (value NOT IN ('Infinity'::numeric, '-Infinity'::numeric))
);
```

Or use `isfinite` for types that provide it. Verify function/operator availability for your type/version; write explicit checks and test each special value.

### 10.9. Money

`money` is locale-sensitive for input/output and has fractional precision dependent on build/configuration. It is usually not a good choice for interchange/API values because formatting can depend on `lc_monetary`.

If using `money`, test input/output under the actual locale and do not parse a formatted money string as a standalone decimal in the application. For financial systems, `numeric(p,s)` or integer minor units usually provide a clearer contract.

### 10.10. Identity and sequence boundaries

Identity/serial columns rely on sequences. Sequences have type/range, increment, min/max, cycle, and cache settings. Test when a sequence approaches its limit, when increment is negative, when `CYCLE` is used, and when the application passes explicit identity values.

```sql
CREATE SEQUENCE test_constraints.small_sequence
    AS smallint
    START WITH 32766
    INCREMENT BY 1
    NO CYCLE;

SELECT nextval('test_constraints.small_sequence');
SELECT nextval('test_constraints.small_sequence');
-- The next call exceeds smallint max and must error.
```

Do not test sequence exhaustion in production. Sequence values are not transactional like table rows; rolling back a transaction does not undo `nextval`.

---

## 11. Testing Floating-Point and Other Numeric Types

### 11.1. real and double precision

`real` (`float4`) and `double precision` (`float8`) store binary floating-point approximations. Many decimal fractions cannot be represented exactly, such as `0.1`.

```sql
SELECT
    0.1::double precision + 0.2::double precision
        = 0.3::double precision AS exact_equal,
    0.1::double precision + 0.2::double precision
        AS actual_sum;
```

Test numeric equality with a tolerance when semantics are approximate:

```sql
SELECT abs(
    (0.1::double precision + 0.2::double precision) - 0.3
) < 1e-12 AS within_tolerance;
```

Tolerance must be based on magnitude, precision, and domain; a fixed epsilon does not fit all scales.

### 11.2. NaN

PostgreSQL has special behavior for `NaN` to support sorting/indexing: `NaN` is considered equal to `NaN` and greater than all non-NaN values in PostgreSQL ordering. This differs from standard IEEE comparisons in some languages.

```sql
SELECT
    'NaN'::double precision = 'NaN'::double precision AS nan_equal,
    'NaN'::double precision > 'Infinity'::double precision AS nan_order;
```

Test `NaN` with UNIQUE, ORDER BY, MIN/MAX, CHECK, and application serialization. If the domain rejects `NaN`, forbid it explicitly.

### 11.3. Infinity

Floating-point types can store `Infinity` and `-Infinity`. Test them alongside finite max/min values, arithmetic, and comparisons. A validation that only checks `value >= 0` will accept positive infinity.

### 11.4. Comparing numeric and float

`numeric` is arbitrary-precision decimal; `float` is approximate binary. Casting between them can round or alter representation. Do not use `float` for currency or quantities requiring decimal exactness.

### 11.5. Signed zero

Floating-point has `+0` and `-0` representations. They generally compare equal in PostgreSQL, but may differ in textual representation or certain computations. If the application depends on the sign of zero, test it separately and decide whether normalization is needed.

### 11.6. Rounding and formatting

Do not compare formatted strings instead of numeric values. Formatting depends on locale, scale, and client. Test:

- Value stored in the database.
- Value returned over the text protocol.
- Value returned over the binary protocol if the driver uses it.
- Value deserialized in the application.

### 11.7. Bit strings and binary values

For `bit(n)`, `varbit`, and `bytea`, check:

- Bit/byte length.
- Empty value.
- Leading zero bits.
- Binary zero bytes.
- Hex/base64 encode/decode.
- Equality after round-trip.

Byte length and character length are different quantities.

---

## 12. Testing Text, Unicode, and Length Boundaries

### 12.1. varchar(n) counts characters, not bytes

In a UTF-8 database, `varchar(n)` limits the number of characters by character count, not byte count. A Unicode character can occupy multiple bytes.

```sql
SELECT
    char_length('é') AS characters,
    octet_length('é') AS bytes,
    char_length('😀') AS emoji_characters,
    octet_length('😀') AS emoji_bytes;
```

The byte count depends on encoding. In UTF-8, these characters use more bytes than a single ASCII character.

### 12.2. varchar(n) boundary

```sql
CREATE TABLE test_constraints.short_text (
    value varchar(3)
);

INSERT INTO test_constraints.short_text VALUES ('abc');
```

Test exactly `n` characters, `n+1` characters, multibyte characters, and trailing spaces. When assigning a string exceeding the length, PostgreSQL typically raises value too long; if the excess consists only of spaces, trailing excess spaces may be trimmed per `varchar` rules.

### 12.3. Explicit cast can truncate

An explicit cast to `varchar(n)` can truncate strings longer than `n` characters:

```sql
SELECT 'abcdef'::varchar(3);
```

This differs from directly INSERTing an overly long string into `varchar(3)`, which is normally rejected. Test the cast path and assignment path separately so data is not silently lost.

### 12.4. char(n) and trailing spaces

`char(n)` (`bpchar`) blank-pads values to length `n`; comparisons ignore trailing spaces per the type's semantics. `varchar`/`text` preserve trailing spaces.

```sql
SELECT
    'a'::char(3) = 'a  '::char(3) AS char_equal,
    'a'::varchar = 'a '::varchar AS varchar_equal;
```

Test trailing spaces, explicit casts, length functions, and unique indexes. Avoid `char(n)` if the application must preserve trailing whitespace exactly.

### 12.5. Unicode normalization

Two strings can look identical yet have different byte/code-point sequences, such as an accented character represented as composed vs. base character plus combining mark. Equality does not automatically apply all Unicode normalization forms.

If business rules require canonical equivalence, normalize at a well-defined layer or use an appropriate extension/function; test composed/decomposed inputs and uniqueness.

### 12.6. Case folding

`lower()` and case-insensitive collations have semantics depending on locale/Unicode implementation. Test characters with special case mappings, not just ASCII A-Z. If business rules require case-insensitive identity, define an explicit normalization policy and enforce the same policy across all writers.

### 12.7. Empty string and whitespace

Test:

- Empty string.
- One ASCII space.
- Tab/newline.
- Non-breaking space.
- Unicode whitespace.
- Leading/trailing spaces.

`length(text)` counts characters, `octet_length(text)` counts bytes. `btrim` by default trims space characters per PostgreSQL behavior; it is not full Unicode whitespace normalization.

### 12.8. Collation and ordering

Collation affects comparison, sorting, pattern matching, and can affect index behavior. Test case/accent ordering, locale-specific comparisons, and the collation provider/version used in production. When a collation version changes, check mismatch warnings and reindex as guided.

---

## 13. Testing Domains, Ranges, Arrays, and JSON Values

### 13.1. Domain constraints

A domain can combine NOT NULL and CHECK:

```sql
CREATE DOMAIN test_constraints.positive_amount AS numeric(12,2)
    NOT NULL
    CHECK (VALUE > 0);

CREATE TABLE test_constraints.invoice_lines (
    line_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    amount test_constraints.positive_amount
);
```

Test positive amounts, zero, negative, NULL, and numeric overflow. Domain NOT NULL applies when the value is used in the domain; the column can also carry its own constraints.

### 13.2. Domain CHECK and UNKNOWN

CHECK in a domain also follows SQL three-valued logic. If a domain allows NULL and CHECK returns UNKNOWN, the value can be accepted. When a value is required, use domain NOT NULL or column NOT NULL according to the desired semantics.

### 13.3. Range boundaries

Range types distinguish inclusive/exclusive bounds, empty ranges, unbounded bounds, and normalized representations:

```sql
SELECT
    int4range(1, 5, '[)') AS half_open,
    int4range(1, 5, '[]') AS closed,
    int4range(1, 1, '[)') AS empty_range,
    int4range(NULL, 5, '(]') AS unbounded_lower;
```

Test:

- Lower bound right at the boundary.
- Upper bound right at the boundary.
- Element immediately before/after the boundary.
- Inclusive and exclusive endpoints.
- Empty range.
- Unbounded range.
- NULL range column.
- Overlap, adjacency, contains, and contained-by.

### 13.4. Canonical range representations

Some discrete range types have canonicalization; for example, integer ranges can normalize to an equivalent lower-inclusive, upper-exclusive representation. Test equality/round-trip by semantic range, not just output string comparison.

### 13.5. Multirange

A multirange is a normalized set of non-overlapping ranges. Test empty multirange, single range, multiple disjoint ranges, adjacent ranges, and merged/canonicalized ranges. Verify contains/overlap operators and aggregate operations if used by the application.

### 13.6. Arrays

Arrays can vary in:

- SQL NULL array.
- Empty array.
- Array with NULL elements.
- Dimensions and lower bounds.
- Multidimensional arrays.
- Duplicate elements.

PostgreSQL allows flexible array dimensions/lower bounds. If the application assumes arrays are always 1-based or one-dimensional, test constraints or normalize data according to that contract.

```sql
SELECT
    array_length(ARRAY[]::integer[], 1) AS empty_length,
    cardinality(ARRAY[]::integer[]) AS empty_cardinality,
    array_lower('[0:2]={10,20,30}'::integer[], 1) AS lower_bound,
    array_dims(ARRAY[[1,2],[3,4]]) AS dimensions;
```

### 13.7. JSONB field presence

JSON objects can distinguish a missing key from a key with JSON null:

```sql
SELECT
    '{}'::jsonb ? 'nickname' AS key_missing,
    '{"nickname":null}'::jsonb ? 'nickname' AS key_present,
    '{"nickname":null}'::jsonb -> 'nickname' AS json_null_value,
    '{"nickname":null}'::jsonb ->> 'nickname' AS text_extraction;
```

The JSON extraction operator `->>` can return SQL NULL for both a missing key and JSON null, so use the key-existence operator or `jsonb_typeof` to distinguish them if business rules require it.

### 13.8. JSON type validation

```sql
SELECT
    jsonb_typeof('null'::jsonb),
    jsonb_typeof('42'::jsonb),
    jsonb_typeof('"42"'::jsonb),
    jsonb_typeof('true'::jsonb),
    jsonb_typeof('[]'::jsonb),
    jsonb_typeof('{}'::jsonb);
```

The number `42` and string `"42"` are two different JSON types. Test type coercion when the application deserializes JSON and when using JSONPath.

### 13.9. JSONB numeric range

JSONB numbers are stored using PostgreSQL `numeric` semantics. Test very large numbers, decimal scales, exponent notation, and values invalid for the business domain. JSONB does not enforce a schema on its own; use CHECK, generated columns, constraints, or validation functions to enforce critical invariants.

### 13.10. UUID

UUID is a fixed-size 128-bit identifier. Test:

- Canonical UUID format.
- Upper/lowercase hex input.
- Hyphen positions.
- Invalid characters/length.
- NULL and duplicate values.
- Round-trip through driver and JSON serialization.

UUID equality does not depend on the casing of the textual input representation; the database stores the UUID type, not an arbitrary formatted string.

### 13.11. Generated columns

Generated columns can depend on expressions and type coercion:

```sql
CREATE TABLE test_constraints.line_totals (
    quantity integer NOT NULL,
    unit_price numeric(10,2) NOT NULL,
    total numeric(14,2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED
);
```

Test boundary multiplication, rounding, overflow, and NULL propagation. Generated expressions must use allowed functions/operators with appropriate volatility per PostgreSQL requirements.

### 13.12. Casts and implicit conversions

PostgreSQL has explicit casts, assignment casts, and implicit casts. Queries can resolve operators differently depending on literal/parameter types. Test prepared statements with parameter types matching what the driver sends; a string parameter does not always have the same semantics as a typed numeric parameter.

Do not rely on implicit casts if they can lose precision or prevent index usage. Casting a column in WHERE can change operator resolution and indexability.

---

## 14. Testing Transactions, Concurrency, and Race Conditions

### 14.1. Why multiple sessions are needed

Constraints like UNIQUE, FOREIGN KEY, and EXCLUDE must uphold invariants across concurrent transactions. A single-session test only verifies sequential behavior; it does not uncover race conditions.

### 14.2. Unique insert race

Create a unique key and run two sessions:

```sql
CREATE TABLE test_constraints.concurrent_keys (
    key text PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Sequence:

1. Session A: BEGIN; INSERT key K; do not COMMIT yet.
2. Session B: BEGIN; INSERT key K; the statement typically waits on Session A.
3. Session A: COMMIT.
4. Session B receives a unique violation.
5. Roll back Session B.

Repeat with Session A performing ROLLBACK; then Session B can insert successfully.

### 14.3. Foreign key parent delete race

Test one transaction deleting a parent while another transaction inserts a child referencing that parent. FK locking/checking must guarantee no orphan child commits. Define expected outcomes based on transaction order and the ON DELETE action.

### 14.4. Exclusion race

Two sessions concurrently insert reservations for the same resource and overlapping ranges. The exclusion constraint must ensure two conflicting rows cannot both commit. Test both overlapping and adjacent ranges, as well as transaction rollback.

### 14.5. Write skew and cross-row invariants

An invariant such as "total allocations do not exceed capacity" cannot be protected by a per-row CHECK constraint alone. Two transactions can concurrently read the current total and insert different allocations that exceed capacity.

Options include:

- Designing the schema to express the invariant with UNIQUE/FK/EXCLUDE.
- Locking a parent row or resource row inside the transaction.
- Using SERIALIZABLE isolation and retrying serialization failures.
- Using triggers/transaction logic with appropriate locking.

Test concurrency at the production isolation level and verify the application retries SQLSTATE `40001` if using SERIALIZABLE.

### 14.6. Deferred constraint failures

An `INITIALLY DEFERRED` constraint can allow individual statements to succeed while COMMIT fails. The test harness must check for errors at COMMIT, not just on each INSERT/UPDATE.

### 14.7. Savepoints and error recovery

In a transactional test, a statement error aborts the transaction until rollback. Use SAVEPOINT to isolate a negative case, then `ROLLBACK TO SAVEPOINT`. Check the transaction state before continuing assertions.

### 14.8. Idempotency and retries

If the application retries a transaction after a timeout, test:

- Client does not know whether the transaction committed.
- Duplicate request identifier.
- Unique idempotency key.
- Retry after serialization/deadlock error.
- Partial work in external systems.

A unique constraint on an idempotency key often prevents duplicate processing; test the conflict path and how the application reads the existing result.

### 14.9. Deadlocks

Two transactions locking rows in opposite orders can deadlock. Create a controlled test in an isolated environment, verify one transaction aborts with SQLSTATE `40P01`, and verify the application has a bounded retry policy.

### 14.10. Lock timeout and statement timeout

Test behavior when `lock_timeout` and `statement_timeout` are configured. Distinguish lock-wait timeouts from query execution timeouts; the application must roll back the transaction and not continue using a connection in an aborted state.

---

## 15. Testing Through Client Drivers and Applications

### 15.1. Timestamp serialization

Drivers can serialize timestamp values differently depending on language types and protocol. Test:

- Instant with explicit UTC offset.
- Instant with non-zero offset.
- Local timestamp without zone.
- Microsecond precision.
- DST gap/fold.
- Session TimeZone other than UTC.

Send parameters with explicit types if the driver supports it; do not concatenate timestamps into arbitrary SQL text.

### 15.2. Numeric serialization

Some language runtimes use binary floating-point for all numbers. Sending currency as a `double` can lose precision before PostgreSQL receives it. Use the driver's decimal type or integer minor units and test round-trip.

### 15.3. NULL parameter binding

SQL NULL is not the string `"NULL"`. The driver must bind null with the appropriate parameter type. Test:

- NULL parameter.
- Empty string.
- Zero.
- False.
- JSON null.
- Missing JSON property.

Inspect generated SQL/parameter bindings in test diagnostics without logging secrets.

### 15.4. Prepared statement type inference

Untyped NULL literals or parameters can cause ambiguity when PostgreSQL cannot infer the type. Use explicit casts or explicit parameter types in prepared statements. Test the same SQL called first with NULL and next with non-NULL to catch type inference issues.

### 15.5. Connection pool session state

Connection pools reuse sessions. If one request sets `SET TIME ZONE`, `SET DateStyle`, or changes `search_path` without resetting, the next request can inherit unintended session state.

Test connection checkout/checkin and verify session settings are reset or transaction-local:

```sql
BEGIN;
SET LOCAL TIME ZONE 'UTC';
SELECT current_setting('TimeZone');
COMMIT;
```

`SET LOCAL` applies only within the current transaction. With pooled connections, this is usually safer than session-level `SET` for request-scoped behavior.

### 15.6. Text encoding

Test `client_encoding`, `server_encoding`, and Unicode characters. Verify round-trip does not drop combining marks, emoji, or supplementary-plane characters. Do not test ASCII only.

### 15.7. Error mapping

The application should map SQLSTATE/constraint names to appropriate domain errors. Test that unique violation, FK violation, check violation, overflow, and invalid datetime are distinguished; avoid turning every error into a generic HTTP 500 or exposing raw database messages to end users.

---

## 16. Organizing Regression Tests with SQL and pgTAP

### 16.1. Plain SQL scripts

A simple test script can create a fixture schema, run assertions, and roll back:

```sql
BEGIN;

CREATE TEMP TABLE test_values (
    id integer PRIMARY KEY,
    amount numeric(5,2) NOT NULL CHECK (amount >= 0)
);

INSERT INTO test_values VALUES (1, 0), (2, 999.99);

DO $$
BEGIN
    IF (SELECT count(*) FROM test_values) <> 2 THEN
        RAISE EXCEPTION 'unexpected row count';
    END IF;

    IF (SELECT max(amount) FROM test_values) <> 999.99 THEN
        RAISE EXCEPTION 'unexpected maximum amount';
    END IF;
END
$$;

ROLLBACK;
```

Negative tests need savepoints or a harness that catches exceptions so the transaction can continue.

### 16.2. DO block checking expected SQLSTATE

```sql
DO $$
BEGIN
    BEGIN
        INSERT INTO test_values(id, amount) VALUES (3, -1);
        RAISE EXCEPTION 'expected check violation did not occur';
    EXCEPTION
        WHEN check_violation THEN
            NULL; -- Expected error.
    END;
END
$$;
```

In a production test suite, use an explicit exception condition or SQLSTATE. Avoid catching all exceptions with `WHEN OTHERS` and treating it as a pass; that can mask unrelated bugs.

### 16.3. pgTAP

pgTAP is an extension providing assertion functions for PostgreSQL tests. Example schema/constraint tests:

```sql
CREATE EXTENSION IF NOT EXISTS pgtap;

BEGIN;
SELECT plan(5);

SELECT has_table('test_constraints', 'products');
SELECT col_not_null('test_constraints', 'products', 'sku');
SELECT col_type('test_constraints', 'products', 'price', 'numeric(12,2)');

SELECT lives_ok(
    $$INSERT INTO test_constraints.products(sku, price)
      VALUES ('T-100', 12.50)$$,
    'valid product is accepted'
);

SELECT throws_ok(
    $$INSERT INTO test_constraints.products(sku, price)
      VALUES (NULL, 12.50)$$,
    '23502',
    'null sku is rejected'
);

SELECT * FROM finish();
ROLLBACK;
```

Assertion names and signatures should be checked against the installed pgTAP version. Test suites can call `throws_ok` with SQLSTATE, message, and description matching the signature provided by that version.

### 16.4. Test fixtures and isolation

Each test should have independent setup/teardown. Use transaction rollback when the test does not need to verify commit-time behavior or concurrency. For testing COMMIT/deferred constraints, separate transactions and a harness that catches errors from COMMIT may be needed.

### 16.5. Structuring the test suite by semantics

A structure you can use:

```text
tests/
  constraints/
    not_null.sql
    check.sql
    unique.sql
    foreign_key.sql
    exclusion.sql
    deferred.sql
    concurrency/
  nulls/
    boolean_logic.sql
    unique_nulls.sql
    json_null.sql
    arrays.sql
  time/
    timestamp_types.sql
    timezone_conversion.sql
    dst_gap_fold.sql
    intervals.sql
  types/
    integer_boundaries.sql
    numeric_precision.sql
    floating_point.sql
    text_unicode.sql
```

### 16.6. CI matrix

Run tests across the PostgreSQL major versions supported by the application. Record:

- Server major/minor version.
- OS/container image.
- Timezone database/tzdata.
- Locale/collation provider.
- Client driver version.
- Extensions and versions.

Tests involving timezone rules or collation can differ across environments; pinning the environment aids reproducibility, while a multi-environment matrix uncovers portability issues.

---

## 17. Building a Test Matrix for Boundary Cases

### 17.1. Constraint matrix

For each table, document the rule, input class, expected result, and SQLSTATE:

| Rule | Input | Expected result |
|---|---|---|
| NOT NULL | NULL | 23502 |
| NOT NULL | Empty string | Accepted unless another rule forbids it |
| CHECK amount >= 0 | -0.01 | 23514 |
| CHECK amount >= 0 | 0 | Accepted |
| CHECK amount >= 0 | NULL | UNKNOWN, accepted by CHECK if not NOT NULL |
| UNIQUE | Duplicate non-NULL key | 23505 |
| Default UNIQUE | Multiple NULLs | Accepted |
| UNIQUE NULLS NOT DISTINCT | Second NULL | 23505 |
| FOREIGN KEY | Missing parent | 23503 |
| FOREIGN KEY MATCH SIMPLE | One FK component NULL | Match check skipped |
| FOREIGN KEY MATCH FULL | Partial NULL | 23503 |
| EXCLUDE | Overlap conflict | 23P01 |

### 17.2. Timezone matrix

| Scenario | Input | Assertion |
|---|---|---|
| UTC instant | Timestamp with +00 | Read back same instant |
| Offset input | Same instant with +07 | Equality with UTC representation |
| Session timezone change | Different SET TIME ZONE | Instant unchanged, display changes |
| Timestamp without zone | Input with offset | Offset not preserved |
| DST gap | Nonexistent local time | Result matches defined policy |
| DST fold | Local time occurring twice | Occurrence selected via offset/policy |
| Calendar day | interval 1 day | Preserves calendar intent per zone |
| Elapsed duration | interval 24 hours | Exact 24 elapsed hours |
| Microseconds | Fractional precision 6 | Round-trip preserves precision |

### 17.3. Numeric matrix

| Type | Boundary tests |
|---|---|
| smallint | -32768, 32767, -32769, 32768 |
| integer | -2147483648, 2147483647, and out of range |
| bigint | Min/max and out of range |
| numeric(5,2) | -999.99, 999.99, 1000.00, 1.234 |
| numeric unconstrained | Large scale, many digits, special values |
| real/double | Approximation, NaN, Infinity, signed zero |
| sequence AS smallint | Last valid value and exhaustion |

### 17.4. Text matrix

| Scenario | Assertion |
|---|---|
| varchar(n) exact n chars | Accepted |
| varchar(n) n+1 chars | Assignment rejected unless excess characters are spaces |
| Explicit cast varchar(n) | Can truncate |
| Multibyte Unicode | Character count differs from byte count |
| Trailing spaces | Text/varchar preserve, char semantics differ |
| Composed/decomposed Unicode | Equality per normalization policy |
| Case variants | Equality/uniqueness per case policy |
| Empty/whitespace | Distinguished per CHECK/validation |

### 17.5. NULL matrix

For each nullable column, test at least:

1. SQL NULL.
2. Empty string or empty collection if supported by the type.
3. Zero/false if the type is numeric/boolean.
4. JSON null if the type is JSON/JSONB.
5. Missing key if the value lives inside a JSON object.
6. Mixed NULL/non-NULL in composite keys, arrays, and expressions.

### 17.6. Driver matrix

Run the same input set through:

- Direct SQL literals.
- Prepared statements with typed parameters.
- Prepared statements with NULL parameters.
- Text protocol.
- Binary protocol if the driver uses it.
- Application serializer/deserializer.

Compare type, value, and precision after round-trip. Tests should mirror the exact driver/version used in production.

### 17.7. Categorizing expected errors

Do not lump all negative cases into a single "throws" assertion. Use SQLSTATE/constraint name to distinguish:

- Input parser error.
- Cast error.
- NOT NULL/CHECK/UNIQUE/FK/EXCLUDE violation.
- Overflow.
- Deferred failure at COMMIT.
- Serialization failure/deadlock.
- Lock/statement timeout.

---

## 18. End-to-End Regression Test Example

### 18.1. Create the sample schema

```sql
CREATE SCHEMA IF NOT EXISTS qa_boundary;

CREATE TABLE qa_boundary.bookings (
    booking_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id integer NOT NULL,
    customer_email text NOT NULL,
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    amount numeric(8,2) NOT NULL,
    CONSTRAINT bookings_amount_nonnegative
        CHECK (amount >= 0),
    CONSTRAINT bookings_time_order
        CHECK (ends_at > starts_at),
    CONSTRAINT bookings_email_uq
        UNIQUE (customer_email)
);
```

The sample schema combines NOT NULL, CHECK, UNIQUE, and `timestamptz`/`numeric` types. In a test environment, an exclusion constraint on room/time overlap can be added if business rules forbid overlapping bookings.

### 18.2. Positive boundary cases

```sql
INSERT INTO qa_boundary.bookings (
    room_id, customer_email, starts_at, ends_at, amount
)
VALUES (
    1,
    'a@example.test',
    timestamptz '2026-06-01 02:00:00+00',
    timestamptz '2026-06-01 03:00:00+00',
    0.00
);

INSERT INTO qa_boundary.bookings (
    room_id, customer_email, starts_at, ends_at, amount
)
VALUES (
    2,
    'b@example.test',
    timestamptz '2026-06-01 09:00:00+07',
    timestamptz '2026-06-01 10:00:00+07',
    999999.99
);
```

Both rows lie within the `numeric(8,2)` domain, have valid time intervals, and use distinct emails.

### 18.3. Negative cases

The following tests must be run independently or inside savepoints because each error puts the current transaction into an aborted state:

```sql
-- NOT NULL
INSERT INTO qa_boundary.bookings
    (room_id, customer_email, starts_at, ends_at, amount)
VALUES
    (1, NULL, now(), now() + interval '1 hour', 10);

-- CHECK: end must be after start
INSERT INTO qa_boundary.bookings
    (room_id, customer_email, starts_at, ends_at, amount)
VALUES
    (1, 'bad-time@example.test', now(), now(), 10);

-- CHECK: amount must be nonnegative
INSERT INTO qa_boundary.bookings
    (room_id, customer_email, starts_at, ends_at, amount)
VALUES
    (1, 'negative@example.test', now(), now() + interval '1 hour', -0.01);

-- UNIQUE
INSERT INTO qa_boundary.bookings
    (room_id, customer_email, starts_at, ends_at, amount)
VALUES
    (1, 'a@example.test', now(), now() + interval '1 hour', 10);

-- Numeric precision overflow
INSERT INTO qa_boundary.bookings
    (room_id, customer_email, starts_at, ends_at, amount)
VALUES
    (1, 'overflow@example.test', now(), now() + interval '1 hour', 1000000.00);
```

Each statement must fail for its corresponding constraint/type. Do not run the entire block in one transaction and ignore the aborted state; use a harness that handles each expected exception.

### 18.4. Verify timezone equality

```sql
SET TIME ZONE 'UTC';

SELECT
    timestamptz '2026-06-01 09:00:00+07'
    =
    timestamptz '2026-06-01 02:00:00+00'
    AS same_instant;
```

The assertion must be TRUE. This verifies two different representations of the same instant.

### 18.5. Verify output timezone

```sql
SET TIME ZONE 'UTC';
SELECT starts_at FROM qa_boundary.bookings WHERE customer_email = 'a@example.test';

SET TIME ZONE 'Asia/Ho_Chi_Minh';
SELECT starts_at FROM qa_boundary.bookings WHERE customer_email = 'a@example.test';
```

The two text outputs differ, but the underlying instant is identical.

### 18.6. Verify final data

```sql
SELECT
    count(*) AS rows,
    min(amount) AS minimum_amount,
    max(amount) AS maximum_amount,
    bool_and(ends_at > starts_at) AS all_time_ranges_valid,
    bool_and(amount >= 0) AS all_amounts_nonnegative
FROM qa_boundary.bookings;
```

Aggregate assertions are an additional check layer. They do not replace constraints and do not by themselves prove that negative test cases were executed.

---

## 19. Common Testing Mistakes

1. **Testing only the happy path:** skipping NULL, empty, min/max, and invalid inputs.
2. **Assuming CHECK forbids NULL:** a CHECK expression evaluating to UNKNOWN is accepted.
3. **Equating NULL with empty string:** they are distinct values.
4. **Assuming UNIQUE allows only one NULL:** by default PostgreSQL allows multiple NULLs.
5. **Forgetting composite FK MATCH SIMPLE:** one NULL component can skip the entire FK check.
6. **Not testing MATCH FULL:** partial-null composite keys can violate rules.
7. **Checking only statements, not COMMIT:** deferred constraints can fail at the end of a transaction.
8. **Using SELECT before INSERT to guarantee uniqueness:** race conditions can still occur; a UNIQUE constraint is required.
9. **Storing instants in timestamp without time zone:** loses offset/timezone context.
10. **Relying on default session TimeZone:** results depend on connection state.
11. **Using ambiguous abbreviations:** prefer IANA timezone names.
12. **Not testing DST gap/fold:** local times can fail to exist or occur twice.
13. **Treating interval 1 day as always 24 hours:** calendar arithmetic can differ from elapsed duration across DST.
14. **Using float for currency:** binary approximation can break rounding/equality.
15. **Not testing numeric coercion:** `numeric(p,s)` can round before storing.
16. **Testing only column range, missing arithmetic overflow:** calculations can overflow even when operands are valid.
17. **Confusing varchar length with bytes:** `varchar(n)` limits characters.
18. **Not testing explicit casts:** casts can truncate differently from assignment.
19. **Ignoring Unicode normalization/collation:** strings that look identical may not compare equal.
20. **Treating JSON null as SQL NULL:** they are two different states.
21. **Not testing driver bindings:** applications may send timestamps/numerics/NULLs differently from SQL literals.
22. **Catching every exception as expected:** can mask unexpected bugs.
23. **Testing only a single session:** misses race conditions, deadlocks, and write skew.
24. **Relying on message text:** SQLSTATE and constraint names are more stable.
25. **Order-dependent tests:** non-independent fixtures cause flaky tests.

---

## 20. Checklist and Summary

### Constraints

1. Test NOT NULL with NULL, empty string, and whitespace.
2. Test CHECK with TRUE, FALSE, and UNKNOWN.
3. Test UNIQUE with duplicates, NULL, and NULLS NOT DISTINCT.
4. Test composite keys and case/collation semantics.
5. Test FOREIGN KEY with missing parent, NULL, and MATCH modes.
6. Test ON DELETE/ON UPDATE actions.
7. Test deferred constraints at SET CONSTRAINTS and COMMIT.
8. Test exclusion overlap, adjacency, and concurrency.

### NULL semantics

9. Test TRUE/FALSE/UNKNOWN in WHERE, AND, OR, and NOT.
10. Test IS NULL, IS DISTINCT FROM, COALESCE, and NULLIF.
11. Test NOT IN with NULL.
12. Test aggregates, DISTINCT, and GROUP BY.
13. Distinguish SQL NULL, JSON null, missing key, empty array, and array containing NULL.

### Timezone and date/time

14. Choose date/time/timestamp/timestamptz according to domain.
15. Explicitly set TimeZone in tests.
16. Test explicit offsets and inputs without timezone.
17. Test two-way AT TIME ZONE.
18. Test DST gap/fold and local-time policy.
19. Test leap days, month ends, fractional seconds, and infinity.
20. Distinguish interval calendar day from elapsed hours.

### Type boundaries and application

21. Test integer min/max and overflow.
22. Test numeric precision/scale, rounding, and special values.
23. Test floating-point tolerance, NaN, Infinity, and signed zero.
24. Test varchar character count, byte length, casts, trailing spaces, and Unicode.
25. Test UUID, arrays, ranges, JSONB, domains, and generated expressions.
26. Test prepared statements, typed NULL parameters, and connection pool session state.
27. Test driver round-trip over text/binary protocols matching the production stack.

### Automation and concurrency

28. Use SQLSTATE/constraint names for negative assertions.
29. Use savepoints or a harness to handle expected errors.
30. Test UNIQUE/FK/EXCLUDE with multiple sessions.
31. Test serialization/deadlock retry behavior if required by the application.
32. Run the suite across supported PostgreSQL versions, collations, and timezone environments.
33. Keep fixtures independent, deterministic, and repeatable.

Testing constraints, NULLs, time zones, and data type boundaries requires focusing on the semantics SQL actually enforces. CHECK does not forbid NULL on its own; default UNIQUE treats NULLs as distinct; composite FKs have MATCH behavior; `timestamptz` stores an instant but displays in the session timezone; DST introduces nonexistent or repeated local times; and numeric/float/text types follow different precision, rounding, and length rules.

A solid regression suite verifies both accepted and rejected data, checks post-commit state, simulates concurrency, and runs through the exact driver/session settings of production. When tests are designed around a boundary matrix and SQLSTATE codes, hard-to-reproduce data bugs become automatically verifiable cases.

**Self-check question:** A column has `CHECK (amount >= 0)` without `NOT NULL`. Does a test where `INSERT NULL` succeeds prove the constraint is broken? No. The CHECK expression evaluates to UNKNOWN for NULL and PostgreSQL accepts the row; if business rules require `amount` to always be present, `NOT NULL` must be added.

### Official PostgreSQL Documentation

- [Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html).
- [Comparison Functions and Operators](https://www.postgresql.org/docs/current/functions-comparison.html).
- [Logical Operators](https://www.postgresql.org/docs/current/functions-logical.html).
- [Date/Time Types](https://www.postgresql.org/docs/current/datatype-datetime.html).
- [Date/Time Functions and Operators](https://www.postgresql.org/docs/current/functions-datetime.html).
- [Numeric Types](https://www.postgresql.org/docs/current/datatype-numeric.html).
- [Character Types](https://www.postgresql.org/docs/current/datatype-character.html).
- [JSON Types](https://www.postgresql.org/docs/current/datatype-json.html).
- [Range Types](https://www.postgresql.org/docs/current/rangetypes.html).
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html).
- [pgTAP Documentation](https://pgtap.org/documentation.html).
