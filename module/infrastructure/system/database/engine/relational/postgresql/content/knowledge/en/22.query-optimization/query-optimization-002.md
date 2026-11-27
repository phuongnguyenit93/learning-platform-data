# Indexable Predicates and Type-Casting Pitfalls in PostgreSQL

The existence of an index does not mean PostgreSQL will use it in every statement that mentions the indexed column. This query can look up rows very quickly:

```sql
SELECT *
FROM orders
WHERE order_id = 12345;
```

Yet a seemingly equivalent query can force the engine to scan far more data:

```sql
SELECT *
FROM orders
WHERE order_id::text = '12345';
```

The difference lies in **the expression being compared**. In the first statement, the predicate compares the raw `order_id` column directly, which typically fits a B-tree on that column. In the second, PostgreSQL must evaluate **the result of converting each `order_id` to text**; a regular B-tree index on `order_id BIGINT` does not necessarily provide the ordering or comparison semantics of the expression `order_id::text`.

You should not jump to a rigid rule like “any `CAST` destroys index usage.” Some casts are **binary-compatible**, and some types share cross-type comparison operators within the same **operator family**; PostgreSQL can still use an index in those cases. The question to analyze is:

> **Does the filter still match the values, expressions, and operators supported by the index? Can the planner prove that match and determine that the index is cheaper than alternative access paths?**

This lesson belongs to the **Query Optimization** chapter of the *Database Engine Relational PostgreSQL* module, focusing on how to write *indexable predicates* (often referred to as *sargable predicates*) and the kinds of data conversions that prevent indexes from being used effectively.

After this lesson, you will:

- Understand what kinds of comparisons a B-tree index supports and why a logically valid `WHERE` clause does not guarantee a good access path.
- Distinguish **casting on the column**, **casting a literal**, and **properly typed bind parameters**.
- Know how to write **time-range filters** instead of `created_at::date` or `date_trunc(created_at)`.
- Optimize string searches with `LIKE`, `ILIKE`, `lower()`, `text_pattern_ops`, and `pg_trgm` where appropriate.
- Recognize the impact of `COALESCE`, arithmetic operations, string functions, JSONB, `OR`, `IS NULL`, and joins across mismatched column types.
- Use **expression indexes**, **partial indexes**, **multi-column indexes**, and normalized data when the query expression itself cannot be changed.
- Read `EXPLAIN`/`EXPLAIN ANALYZE` to distinguish **cannot use an index** from **can use an index, but the planner chose not to**.
- Apply proper parameter typing in PostgreSQL, JDBC, and prepared statements.

> **Safety scope:** Table and index creation commands in this lesson use a dedicated schema `idx_cast_lab`. Test only in a learning database. The `EXPLAIN (ANALYZE)` statements here are pure read-only `SELECT`s on demo data; for `UPDATE`/`DELETE`/`INSERT`, `EXPLAIN ANALYZE` **actually executes the DML**.

---

## 1. What Is an Indexable Predicate?

### 1.1. Visualizing a B-Tree Index

Suppose you have an index:

```sql
CREATE INDEX orders_customer_id_idx
ON orders (customer_id);
```

Conceptually, the index maintains keys in a searchable sorted order:

```text
           B-tree(customer_id)

          [100] [200] [300]
             |     |     |
        ordered index entries

WHERE customer_id = 200
    -> locate key range 200
    -> fetch matching rows
```

If the filter turns the column into an expression:

```sql
WHERE customer_id + 100 = 300
```

mathematically this may equal `customer_id=200`, yet the planner **cannot be assumed** to invert arbitrary arithmetic or functions so it can apply the condition directly to the index.

### 1.2. Two Questions That Must Be Separated

**Question A — Does the predicate have a compatible index access path?**

- Is the column used directly?
- Does the expression match an existing expression index?
- Is the operator supported by the access method and operator class/family?
- For a partial index, does the query's `WHERE` imply the index predicate?
- For a multi-column index, does the predicate align with key order?

**Question B — If so, does the planner choose the index?**

- Is the table too small?
- Does the query fetch a few rows or nearly the entire table?
- Is the filter value selective?
- Must many heap pages be fetched?
- Do `ORDER BY` and `LIMIT` match the index order?
- Do statistics and cost settings reflect the workload?

An index **being usable** while PostgreSQL still picks `Seq Scan` is completely valid. Never treat a Seq Scan as automatic proof that `WHERE` syntax “broke the index.”

### 1.3. “Sargable” Is a Practical Term, Not a Standard SQL Label

In query optimization literature, *sargable* refers to a predicate that can leverage an access structure to narrow the row set rather than evaluating the expression across nearly every row.

In PostgreSQL, we need to be more specific:

| Component | Why It Matters |
|---|---|
| **Access method** | B-tree, GIN, GiST, and BRIN have different capabilities and access patterns |
| **Operator class/family** | Determines which operators and comparison types an index understands |
| **Index key/expression** | An index on `x` differs from an index on `lower(x)` |
| **Collation** | Affects string ordering and comparison |
| **Query predicate** | Determines how tightly the index scan can be bounded |
| **Planner estimates** | Determines whether choosing the index is cost-effective |

Therefore, rather than just listing “functions that break indexes,” this lesson explains **why**, **the exceptions**, and how to verify via plans.

---

## 2. Which Predicates Does a B-Tree Support?

For a column with a B-tree index and operators matching its operator class, favorable predicates typically include:

```sql
WHERE id = 100
WHERE id < 100
WHERE id <= 100
WHERE id > 100
WHERE id >= 100
WHERE id BETWEEN 100 AND 200
WHERE id IN (100, 101, 102)
```

PostgreSQL can use a B-tree for equality and range lookups, and sometimes to satisfy `ORDER BY` ordering.

### 2.1. Good Pattern: Equality

```sql
SELECT *
FROM some_table
WHERE id = 100;
```

With a unique key, fetching a few rows usually favors an index. However, a query fetching the whole table via `WHERE status='active'` when 99% of rows are active may still prefer a Seq Scan, even though `=` is an indexable operator.

### 2.2. Good Pattern: Half-Open Range

```sql
WHERE created_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00'
```

This keeps the raw timestamp column on the index key side and bounds the range with two explicit endpoints.

### 2.3. `BETWEEN` Is Inclusive on Both Ends

```sql
WHERE amount BETWEEN 100 AND 200
```

is equivalent to:

```sql
WHERE amount >= 100
  AND amount <= 200
```

For **timestamps** spanning an entire day or month, a **half-open** upper bound is safer than `BETWEEN ... 23:59:59` because timestamps have sub-second precision.

### 2.4. `IS NULL` Can Use a B-Tree

```sql
WHERE deleted_at IS NULL
```

A B-tree index on `deleted_at` can serve `IS NULL` lookups in many situations. Saying “B-trees never index NULLs” is false. Selectivity and cost still govern the final plan.

### 2.5. Not Every Operator Fits a B-Tree

Conditions such as:

```sql
WHERE email LIKE '%gmail.com'
WHERE body ~ 'some_regex'
WHERE payload @> '{"category":"audit"}'::jsonb
```

do not by default have good access paths via a plain B-tree on the same column. They may require **trigram GIN/GiST**, **JSONB GIN**, or an expression index depending on the operator and workload.

---

## 3. Lab Environment: Data with Numbers, Strings, UUIDs, and Timestamps

To observe casting effects, we need a table with diverse data types and a large enough row distribution.

### 3.1. Confirm the Lab Database

```sql
SHOW server_version;
SELECT current_database(), current_user;
```

The following steps assume the test database does not yet have an `idx_cast_lab` schema. If another user already owns a schema with that name, **do not overwrite or drop it**; pick a different lab database.

### 3.2. Create Schema and Table

```sql
CREATE SCHEMA idx_cast_lab;

CREATE TABLE idx_cast_lab.events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    state TEXT NOT NULL
        CHECK (state IN ('queued', 'running', 'done', 'failed')),
    customer_email TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    external_id UUID NOT NULL,
    deleted_at TIMESTAMPTZ,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb
);
```

These columns set up typical query challenges:

| Column | Type | Common Filters |
|---|---|---|
| `event_id` | `BIGINT` | Primary key lookups, ID lists |
| `tenant_id` | `INTEGER` | Organization scoping |
| `state` | `TEXT` | Status filtering |
| `customer_email` | `TEXT` | Exact email lookup, case-insensitive lookup, prefix search |
| `event_time` | `TIMESTAMPTZ` | Day, month, and timezone filtering |
| `amount` | `NUMERIC(12,2)` | Monetary equality and range checks |
| `external_id` | `UUID` | External system identifier lookups |
| `deleted_at` | `TIMESTAMPTZ` nullable | Active-record filtering |
| `payload` | `JSONB` | Filtering on JSON attributes |

### 3.3. Generate 100,000 Demo Events

```sql
INSERT INTO idx_cast_lab.events
    (tenant_id, state, customer_email, event_time,
     amount, external_id, deleted_at, payload)
SELECT
    1 + (g % 20) AS tenant_id,
    CASE
        WHEN (g * 37) % 101 < 7  THEN 'queued'
        WHEN (g * 37) % 101 < 20 THEN 'running'
        WHEN (g * 37) % 101 < 85 THEN 'done'
        ELSE 'failed'
    END AS state,
    'User' || (1 + (g % 5000))::text || '@Example.test',
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + g * INTERVAL '1 minute',
    ((g % 1000) + 1)::numeric / 10,
    (
        '00000000-0000-0000-0000-'
        || lpad(g::text, 12, '0')
    )::uuid,
    CASE WHEN g % 100 < 7
         THEN TIMESTAMPTZ '2026-03-01 00:00:00+00'
         ELSE NULL::timestamptz
    END,
    jsonb_build_object(
        'category', CASE
            WHEN g % 9 = 0 THEN 'audit' ELSE 'normal'
        END,
        'source_no', g
    )
FROM generate_series(1, 100000) AS gs(g);
```

This is synthetic data. `event_id` is assigned by identity on a fresh load. `external_id` uses a deterministic UUID pattern for easy lookup—**not a secure or distributed UUID generation pattern for production**.

**Load only once.** Running the insert again adds duplicate rows and invalidates row-count and ID assumptions.

### 3.4. Create Baseline Indexes

```sql
-- event_id already has a B-tree index from the PRIMARY KEY.

CREATE INDEX events_tenant_time_idx
ON idx_cast_lab.events
    (tenant_id, event_time DESC, event_id DESC);

CREATE INDEX events_amount_idx
ON idx_cast_lab.events (amount);

CREATE INDEX events_email_idx
ON idx_cast_lab.events (customer_email);

CREATE INDEX events_external_id_idx
ON idx_cast_lab.events (external_id);

ANALYZE idx_cast_lab.events;
```

These indexes let us compare direct predicates against cast expressions on the same dataset.

### 3.5. Verify Data and Statistics

```sql
SELECT COUNT(*) AS total_rows
FROM idx_cast_lab.events;

SELECT state, COUNT(*) AS rows_in_state
FROM idx_cast_lab.events
GROUP BY state
ORDER BY state;

SELECT MIN(event_time), MAX(event_time)
FROM idx_cast_lab.events;
```

If run exactly once, `total_rows=100000`. Status counts only **approximate** the modulo ratios; do not rely on guessing exact row counts without running the check.

---

## 4. Using `EXPLAIN` to Distinguish Indexability

### 4.1. Inspect the Plan Without Executing `SELECT`

```sql
EXPLAIN
SELECT event_id, amount
FROM idx_cast_lab.events
WHERE event_id = 1000;
```

The plan may show:

```text
Index Scan using events_pkey on events
  Index Cond: (event_id = 1000)
```

The actual primary key index name is typically `events_pkey` when created as above, but always inspect your own server's output instead of assuming a fixed template.

### 4.2. Inspect Actual Rows and Buffers on Pure `SELECT`s

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, amount
FROM idx_cast_lab.events
WHERE event_id = 1000;
```

Check:

- `Index Scan`, `Index Only Scan`, `Bitmap Heap Scan`, or `Seq Scan`.
- `Index Cond` vs `Filter`.
- Estimated `rows` vs `actual rows`.
- `Rows Removed by Filter`.
- `Buffers: shared hit/read`.
- `Planning Time` and `Execution Time`.

### 4.3. What Makes a Well-Founded Conclusion?

Never say “the query uses an index” merely because DDL defines one. Observe the real plan. Equally, never say “the function broke the index” just because you see a Seq Scan on a 5-row test table: **the planner may choose Seq Scan because it is cheaper**.

Analysis workflow:

```text
SQL Query
   |
   +-- Which column/expression is in the predicate?
   |
   +-- Does the operator match the index and data types?
   |
   +-- Do index keys/predicates align?
   |
   +-- Does EXPLAIN show Index Cond or only Filter?
   |
   +-- Are estimated/actual rows reasonable?
   |
   +-- Conclusion: aligned in semantics, plan, and cost
```

### 4.4. `EXPLAIN ANALYZE` Is Not Automatically Safe for DML

`EXPLAIN (ANALYZE) UPDATE/DELETE/INSERT` **executes the write statement**. Never carry habits from demo `SELECT`s over to write statements in production. Even a `SELECT` calling `nextval()` or a notification function can produce side effects.

---

## 5. `CAST` on the Column Side vs `CAST` on the Value Side

### 5.1. Direct Condition on `BIGINT`

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, state
FROM idx_cast_lab.events
WHERE event_id = 1000;
```

`event_id` is `BIGINT` with a primary-key B-tree. This is a unique-key lookup, typically ideal for an index.

### 5.2. Casting `BIGINT` to `TEXT` on the Column Side

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, state
FROM idx_cast_lab.events
WHERE event_id::text = '1000';
```

The comparison is no longer `BIGINT = BIGINT` on the index key, but a comparison on the **expression converting `event_id` to text**.

A B-tree index on `event_id BIGINT` is built for BIGINT ordering and comparison operators; it does not have a structure for quickly locating values **after conversion to strings**.

### 5.3. Casting the Search Value to `BIGINT`

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, state
FROM idx_cast_lab.events
WHERE event_id = '1000'::bigint;
```

Now the column remains untouched. PostgreSQL can use the B-tree on `event_id`.

**Practical rule:** when the column has the right type, convert the **literal/parameter** to the column's valid type rather than casting the entire column to the input's type.

### 5.4. Untyped String Literals Do Not Always Break Indexes

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE event_id = '1000';
```

This does **not** mean PostgreSQL takes every `event_id` and calls `::text`.

An untyped SQL string literal initially has type `unknown`; PostgreSQL uses operator context to resolve it to `BIGINT`, so the predicate can still use the index.

**Contrast:**

```text
event_id = '1000'
    unknown literal is resolved to BIGINT

event_id::text = '1000'
    the column expression itself has been converted to TEXT
```

Do not infer from these two cases that every string sent via JDBC is implicitly resolved the same way: typed prepared-statement parameters follow their own rules.

### 5.5. Unparseable Literals Fail Rather Than Falling Back Indefinitely

```sql
-- Expected invalid_input_syntax error for BIGINT:
-- SELECT *
-- FROM idx_cast_lab.events
-- WHERE event_id = 'abc';
```

Do not “fix” this by writing `event_id::text` just to accept arbitrary junk strings. Validate input format, return a proper validation error, or parse the value into the right type before querying.

### 5.6. Why Cross-Type Comparison Also Causes Semantic Issues

`BIGINT` and `TEXT` have different **orderings**:

```text
Numeric: 2 < 10
Text:   '10' < '2'  (lexicographical order in many collations)
```

Thus, an index sorted numerically cannot automatically serve text-comparison ordering.

---

## 6. Not Every Cast Blocks B-Tree Usage

PostgreSQL uses an extensible system of operators and **operator classes/families**. A B-tree operator family can support comparisons across distinct types when their ordering semantics are compatible.

### 6.1. `INTEGER` and `BIGINT`

Example:

```sql
EXPLAIN
SELECT event_id
FROM idx_cast_lab.events
WHERE event_id = 1000::integer;
```

`event_id` is `BIGINT`, while the right-hand side is `INTEGER`. PostgreSQL provides cross-type comparison operators across integer types and can use the corresponding B-tree **without forcing `event_id::integer`**.

This disproves the claim “both sides must have identical types to use an index.”

### 6.2. `VARCHAR` and `TEXT`

Certain conversions between `VARCHAR` and `TEXT` are representation-compatible. Predicates like:

```sql
-- Columns/literals in different schemas:
-- text_col = varchar_parameter
-- varchar_col = text_parameter
```

do not inherently break indexes. The planner can apply operators/casts compatible with the B-tree and collation.

Never treat the appearance of a cast in `EXPLAIN` as automatic proof of lost index usage. Observe **the exact column/expression inside `Index Cond`**.

### 6.3. Why Type Conversions Can Alter Results

Conversions can:

- **Lose precision**: `NUMERIC` to `DOUBLE PRECISION`.
- **Depend on session timezone**: `TIMESTAMPTZ` to `DATE` or timestamp without time zone.
- **Depend on collation**: string comparison and normalization.
- **Lack a valid implicit conversion**: `TEXT` to `UUID`/`BIGINT` depending on context.

Even when the planner can still use an index, a cast may alter **required semantics**. Optimization must preserve correctness first.

### 6.4. A Better Rule Than “Avoid All `CAST`s”

Check four things:

1. The column's actual data type.
2. The value/parameter's actual data type.
3. The operator PostgreSQL chose after type resolution.
4. The index opclass/family and the actual plan.

If a `CAST` turns the column into a **new expression** lacking a matching index, treat that as a signal to rewrite the query or deliberately add an expression index.

---

## 7. Casting on Numeric, Monetary, and Arithmetic Columns

### 7.1. Querying `NUMERIC` with a Direct Condition

```sql
EXPLAIN
SELECT event_id, amount
FROM idx_cast_lab.events
WHERE amount = 50.00::numeric;
```

`amount` has a B-tree index and the predicate uses a compatible numeric type—a good pattern for equality lookup.

### 7.2. Converting a `NUMERIC` Column to String

```sql
EXPLAIN
SELECT event_id, amount
FROM idx_cast_lab.events
WHERE amount::text = '50.00';
```

This puts the conversion on the column, incompatible with the B-tree on `amount NUMERIC`. Moreover, string formatting introduces scale/representation subtleties (`'50'` vs `'50.00'`), so string equality does not always match numeric equality.

**Fix for numeric lookup:**

```sql
WHERE amount = 50.00::numeric
```

### 7.3. Converting `NUMERIC` to `DOUBLE PRECISION`

```sql
-- Avoid if business logic requires monetary comparison with NUMERIC precision:
-- WHERE amount::double precision = 50.0::double precision
```

Converting to binary floating point can lose precision or alter equality on decimal fractions. An index on `NUMERIC` is not automatically an index on `amount::double precision`.

Never convert monetary columns to floating point just to match a client parameter type; use `BigDecimal`/`NUMERIC`.

### 7.4. Arithmetic on the Column Side

```sql
EXPLAIN
SELECT event_id
FROM idx_cast_lab.events
WHERE amount + 5 = 55;
```

Mathematically, for finite values in the same domain:

```sql
WHERE amount = 50
```

expresses the intent more simply. PostgreSQL is not expected to algebraically rewrite arbitrary expressions to use the B-tree on `amount`.

### 7.5. Do Not Apply Algebraic Rewrites Unconditionally

Algebraic transformations can be wrong when:

- `NULL` is involved.
- Overflow or type bounds exist.
- Rounding or casting occurs.
- Functions are impure or non-injective.
- Timezone, collation, or other rules apply.

While `x * 2 = 10` may map to `x = 5` in an appropriate numeric domain, never build a blind rewrite engine across arbitrary data types.

---

## 8. `TIMESTAMPTZ::date`: A Very Common Trap

An API fetching events for February 10, 2026 often writes:

```sql
SELECT event_id, event_time
FROM idx_cast_lab.events
WHERE event_time::date = DATE '2026-02-10';
```

This looks readable, yet it has two flaws:

1. **The column is passed through a conversion** from `TIMESTAMPTZ` to `DATE`; a B-tree on `event_time` does not automatically index the converted expression.
2. For `TIMESTAMPTZ`, `::date` depends on the **session's `TimeZone`**. A “calendar day” has no absolute meaning without specifying a time zone.

### 8.1. Check `TimeZone`

```sql
SHOW TIME ZONE;
```

An instant such as `2026-02-09 18:00:00+00` is February 9 in UTC, yet February 10 in Vietnam (+07). Therefore:

```sql
WHERE event_time::date = DATE '2026-02-10'
```

can select **different sets of rows** depending on the session's `TimeZone`.

### 8.2. Rewrite as a Half-Open Range on the Raw Column

To fetch **February 10, 2026 in UTC**:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, event_time
FROM idx_cast_lab.events
WHERE tenant_id = 3
  AND event_time >=
      TIMESTAMPTZ '2026-02-10 00:00:00+00'
  AND event_time <
      TIMESTAMPTZ '2026-02-11 00:00:00+00'
ORDER BY event_time DESC, event_id DESC;
```

The index `(tenant_id, event_time DESC, event_id DESC)` supports the tenant equality filter, the time range, and the `ORDER BY` sort order.

### 8.3. Range for a Vietnam Local Day

If the requirement specifies “February 10 in Ho Chi Minh City,” convert **both local endpoints** to instants:

```sql
SELECT event_id, event_time
FROM idx_cast_lab.events
WHERE tenant_id = 3
  AND event_time >= (
      TIMESTAMP '2026-02-10 00:00:00'
          AT TIME ZONE 'Asia/Ho_Chi_Minh'
  )
  AND event_time < (
      TIMESTAMP '2026-02-11 00:00:00'
          AT TIME ZONE 'Asia/Ho_Chi_Minh'
  )
ORDER BY event_time DESC, event_id DESC;
```

Both boundary expressions evaluate to `TIMESTAMPTZ`. The column `event_time` stays untouched, allowing the B-tree to bound the range.

### 8.4. Why Not Simply Add 24 Hours for All Time Zones?

Many time zones observe **daylight saving time (DST)**; a local calendar day can be 23 or 25 hours long. Instead of taking local midnight and adding a fixed 24-hour UTC interval, **convert both the start day and next day** from the local time zone into instants.

Although `Asia/Ho_Chi_Minh` has no DST today, computing both endpoints explicitly expresses the rule cleanly and works across DST zones as well.

### 8.5. Avoid `BETWEEN` with `23:59:59`

```sql
-- May miss rows with fractional seconds:
-- WHERE event_time BETWEEN
--       '2026-02-10 00:00:00+07'
--   AND '2026-02-10 23:59:59+07'
```

Use:

```sql
WHERE event_time >= :begin_instant
  AND event_time <  :next_day_begin_instant
```

`:begin_instant` is an application-layer placeholder notation, **not standard `psql` bind syntax**; in JDBC, use `?`.

---

## 9. `DATE_TRUNC`, `TO_CHAR`, `EXTRACT`, and Timestamp Functions

### 9.1. `DATE_TRUNC` for Grouping vs `DATE_TRUNC` for Filtering

A reporting query:

```sql
SELECT date_trunc('month', event_time) AS month_start,
       COUNT(*)
FROM idx_cast_lab.events
GROUP BY date_trunc('month', event_time);
```

uses `date_trunc` to **group** by month. However, to filter a specific month, writing:

```sql
WHERE date_trunc('month', event_time)
    = TIMESTAMPTZ '2026-02-01 00:00+00'
```

applies the function to the **column**; a standard B-tree on `event_time` cannot directly derive scan bounds from it.

To filter a UTC month, it is clearer and more index-friendly to write:

```sql
WHERE event_time >= TIMESTAMPTZ '2026-02-01 00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-03-01 00:00+00'
```

### 9.2. `TO_CHAR` Converts Timestamps into `TEXT`

```sql
-- Easily turns the indexed column into a text expression:
-- WHERE to_char(event_time, 'YYYY-MM') = '2026-02'
```

Beyond index issues, `to_char` introduces formatting and time-zone subtleties. When filtering a time interval, use explicit timestamp range bounds. Reserve `to_char` primarily for **display formatting** when needed.

### 9.3. `EXTRACT(YEAR ...)` Does Not Map to a Single Range in All Contexts

```sql
WHERE EXTRACT(YEAR FROM event_time) = 2026
```

transforms the column. To retrieve instants falling in 2026 UTC:

```sql
WHERE event_time >= TIMESTAMPTZ '2026-01-01 00:00+00'
  AND event_time <  TIMESTAMPTZ '2027-01-01 00:00+00'
```

If business logic uses another time zone, convert the year start boundaries using that time zone.

### 9.4. Why an Expression Index on `TIMESTAMPTZ::date` Is Not Straightforward

PostgreSQL requires expressions in an index to be **IMMUTABLE**. Casting `TIMESTAMPTZ` to `date` depends on the session's `TimeZone`, so you cannot simply create a valid immutable expression index with:

```sql
-- Invalid example for TIMESTAMPTZ:
-- CREATE INDEX idx_event_day
-- ON idx_cast_lab.events ((event_time::date));
```

Do not “work around” this by marking a session-dependent wrapper function as `IMMUTABLE` when it is not truly immutable.

If you genuinely need an expression index for a **UTC date**, you can consider **pinning the time zone** in an expression that satisfies immutability and verify it on your server version. Still, for range filtering, a direct index on `event_time` with two bounds is usually simpler.

---

## 10. `LOWER(email)` and Expression Indexes

### 10.1. Case-Insensitive Queries

The lab data stores addresses like `User42@Example.test`. A user enters `user42@example.test` and expects a case-insensitive lookup.

This SQL query:

```sql
EXPLAIN
SELECT event_id, customer_email
FROM idx_cast_lab.events
WHERE lower(customer_email) = 'user42@example.test';
```

may match the **case-folding** rules chosen by the application. Yet the baseline index `events_email_idx` is a B-tree on the **original `customer_email`**, not on `lower(customer_email)`.

### 10.2. Creating an Expression Index

```sql
CREATE INDEX events_lower_email_idx
ON idx_cast_lab.events (lower(customer_email));

ANALYZE idx_cast_lab.events;
```

Now the query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, customer_email
FROM idx_cast_lab.events
WHERE lower(customer_email) = 'user42@example.test';
```

**can** use the matching expression index, subject to selectivity and planner cost.

### 10.3. An Expression Index Does Not Speed Up Every Email Query

An index:

```sql
ON events (lower(customer_email))
```

serves queries using the **matching expression**:

```sql
WHERE lower(customer_email) = lower('USER42@example.test')
```

However, it does not replace an index on `customer_email` for **case-sensitive** conditions:

```sql
WHERE customer_email = 'User42@Example.test'
```

The two predicates have different semantics and may require separate indexes.

### 10.4. Expression Indexes Have Write Costs

Whenever an INSERT or UPDATE modifies the email, PostgreSQL must compute and maintain the expression key. The index takes disk space and can affect HOT-update eligibility.

Therefore, use expression indexes when **you cannot or should not rewrite the query onto the raw column**, not as an excuse to index every function appearing in `SELECT`.

### 10.5. Collation and Unicode

`lower()` is not a complete email normalization rule for all domains, Unicode characters, and collations. When business rules require case-insensitive matching, clarify:

- Input string normalization rules.
- Which collation is used.
- Whether locale-aware case folding is required.
- Whether `citext` (extension) or a specific case-insensitive collation is appropriate.
- That indexes and queries share consistent semantics.

Do not switch from `=` to `lower()` if business requirements demand case sensitivity.

---

## 11. `LIKE`, `ILIKE`, and Wildcard Position

A B-tree index on `TEXT` can assist certain prefix queries, depending on the **pattern** and the **collation/operator class**.

### 11.1. `LIKE` with a Fixed Prefix

```sql
SELECT event_id, customer_email
FROM idx_cast_lab.events
WHERE customer_email LIKE 'User1%';
```

The pattern starts with a **fixed prefix** `User1`, so it can potentially become a B-tree range scan when the operator class/collation supports it.

### 11.2. `text_pattern_ops` Under Non-Default Collations

In databases not using the `C` collation, a B-tree text index with the default operator class may not optimize `LIKE 'prefix%'` as expected. PostgreSQL provides an operator class specifically for prefix patterns:

```sql
CREATE INDEX events_email_pattern_idx
ON idx_cast_lab.events
    (customer_email text_pattern_ops);
```

Test:

```sql
EXPLAIN
SELECT event_id
FROM idx_cast_lab.events
WHERE customer_email LIKE 'User1%';
```

The planner can apply prefix bounds using the pattern opclass. It may still choose a Seq Scan if most rows share that prefix or the table is small.

**Do not assume every collation behaves identically**, especially with nondeterministic collations and across different PostgreSQL versions.

### 11.3. Leading Wildcards

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE customer_email LIKE '%example.test';
```

There is no fixed prefix for a standard B-tree to locate a contiguous range in string order. A `text_pattern_ops` index does not turn suffix matching into a prefix lookup.

### 11.4. `ILIKE` and Case-Insensitive Matching

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE customer_email ILIKE 'user1%';
```

Do not assume a plain B-tree handles every `ILIKE` efficiently, because case-insensitivity and collation rules can prevent deriving a simple range.

If the application standardizes on `lower()` semantics:

```sql
WHERE lower(customer_email) LIKE 'user1%'
```

you can consider an expression index with the pattern opclass:

```sql
CREATE INDEX events_lower_email_pattern_idx
ON idx_cast_lab.events
    ((lower(customer_email)) text_pattern_ops);
```

### 11.5. Trigram Indexes for Substring Matching

If the workload frequently runs:

```sql
WHERE customer_email ILIKE '%user42%'
```

the `pg_trgm` extension with a GIN/GiST trigram index is usually a better fit than B-tree:

```sql
-- Depends on database privileges and extension installation policy.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX events_email_trgm_idx
ON idx_cast_lab.events
USING gin (customer_email gin_trgm_ops);
```

`pg_trgm` is not free: it requires an extension, consumes storage, adds write cost, and very short or low-selectivity patterns can perform poorly. If you lack permission to install extensions, ask a DBA to evaluate rather than elevating privileges yourself.

### 11.6. Pattern Filters and Expected Row Counts

Even when an index supports `LIKE`/`ILIKE`, a query matching 90% of the table may still run faster as a Seq Scan. This is different from a leading-wildcard query that **cannot use a B-tree prefix structure at all**.

---

## 12. `COALESCE`, `CASE`, `NULL`, and Functions Around Columns

### 12.1. Nullable Columns in `WHERE`

`deleted_at` is a nullable `TIMESTAMPTZ`.

To fetch active rows:

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE deleted_at IS NULL;
```

This condition is explicit and can be backed by a B-tree on `deleted_at` or an appropriate partial index.

### 12.2. Using `COALESCE` to Replace `NULL` with a Sentinel Value

```sql
-- Not the preferred pattern if you only need NULL:
-- WHERE COALESCE(deleted_at,
--      TIMESTAMPTZ '9999-12-31 00:00+00')
--      = TIMESTAMPTZ '9999-12-31 00:00+00'
```

Aside from wrapping the column in a function, this assumes **no real row ever holds the sentinel value**. If real data contains that value, semantics break.

**Proper rewrite:** `WHERE deleted_at IS NULL`.

### 12.3. Creating a Partial Index for Live Rows

```sql
CREATE INDEX events_live_tenant_time_idx
ON idx_cast_lab.events (tenant_id, event_time DESC)
WHERE deleted_at IS NULL;
```

Query:

```sql
SELECT event_id, event_time
FROM idx_cast_lab.events
WHERE tenant_id = 3
  AND deleted_at IS NULL
  AND event_time >= TIMESTAMPTZ '2026-02-01 00:00+00'
ORDER BY event_time DESC
LIMIT 20;
```

has filters that imply `deleted_at IS NULL`, making the partial index applicable.

### 12.4. `CASE` Inside `WHERE`

```sql
-- A logical expression written unnecessarily complex:
-- WHERE CASE WHEN deleted_at IS NULL
--            THEN 1 ELSE 0 END = 1
```

If the intent is simply `IS NULL`, write it directly to preserve clarity and indexability.

### 12.5. B-Trees Can Also Support `IS NOT NULL`

```sql
WHERE deleted_at IS NOT NULL
```

Do not assume `IS NOT NULL` can “never use an index.” It can work with certain B-tree access paths or partial indexes; the planner decides based on NULL fraction.

---

## 13. Expression Indexes: When You Cannot Remove the Function on the Column

Not every requirement can be rewritten as a raw column predicate.

### 13.1. Example Index on `lower(email)`

```sql
CREATE INDEX events_lower_email_idx
ON idx_cast_lab.events (lower(customer_email));
```

In the lab, this index was already created in section 10. The SQL here repeats the definition **conceptually**; do not create the same-named index twice.

### 13.2. Matching the Expression Is Key

An index on:

```sql
lower(customer_email)
```

matches queries with:

```sql
WHERE lower(customer_email) = 'user42@example.test'
```

but does not automatically serve other expressions such as:

```sql
WHERE trim(lower(customer_email)) = 'user42@example.test'
```

If trimming is required, normalize input on write or design a different expression index.

### 13.3. Immutability Requirement for Expression Indexes

PostgreSQL requires functions and operators in an index expression to be **IMMUTABLE**. Functions depending on wall-clock time, session settings, or external data are invalid.

Example you should not attempt to index:

```sql
-- Invalid because now() is not IMMUTABLE:
-- CREATE INDEX bad_idx
-- ON idx_cast_lab.events ((event_time < now()));
```

Even if you can write a wrapper marked `IMMUTABLE`, **lying about volatility** causes the index to become out of sync with actual query evaluation.

### 13.4. Expression Indexes Must Be Maintained

Every relevant INSERT/UPDATE evaluates and updates the expression index. It costs disk/WAL and can block HOT updates. Make sure to:

- Base the index on a real workload.
- Prefer simple, semantically sound expressions.
- Avoid duplicate indexes.
- Measure read and write costs before/after.
- Verify in plans that the index is actually used.

### 13.5. Generated Columns vs Normalization on Write

If many queries rely on `lower(email)` or another normalized key, consider:

- Normalizing on write, if business rules permit.
- Maintaining a derived column with clear rules.
- Using a generated column when the expression satisfies PostgreSQL's requirements.
- Using an expression index on a stable expression.

Each option has different storage, update, and migration costs. Do not add a derived column just to avoid fixing a simple `WHERE` clause.

---

## 14. `UUID`: Avoid Converting Keys to `TEXT` When Searching

`external_id` in the lab is `UUID` with its own index.

### 14.1. Comparing `UUID` with the Proper Type

```sql
EXPLAIN
SELECT event_id
FROM idx_cast_lab.events
WHERE external_id =
    '00000000-0000-0000-0000-000000000100'::uuid;
```

Both the column and the value remain `UUID`. The B-tree index on `external_id` can perform an exact lookup.

### 14.2. Casting `UUID` to `TEXT`

```sql
EXPLAIN
SELECT event_id
FROM idx_cast_lab.events
WHERE external_id::text =
    '00000000-0000-0000-0000-000000000100';
```

An index on `UUID` values is not an index on formatted UUID strings. When querying by UUID, **parse the input into `UUID`** instead of casting the entire column to text.

### 14.3. Invalid UUID Strings Should Error

```sql
-- An invalid UUID string will fail when cast:
-- WHERE external_id = 'not-a-uuid'::uuid
```

This is expected behavior: the client should return an appropriate validation error. Never “fix” invalid input by casting every UUID column to text.

### 14.4. `UUID` and JDBC

In Java:

```java
import java.util.UUID;

UUID externalId =
    UUID.fromString(requestExternalId);

preparedStatement.setObject(1, externalId);
```

With pgJDBC supporting `java.util.UUID`, binding a properly typed UUID gives the server the right parameter type. Do not bind a UUID as a `String` and force `external_id::text` just to make it match.

---

## 15. `JSONB`: Containment `@>` vs Text Extraction

`JSONB` clearly illustrates that “index usage” depends on both **index type** and **operator**.

### 15.1. Filtering with the Containment Operator

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE payload @> '{"category":"audit"}'::jsonb;
```

The `@>` operator can leverage an appropriate **GIN index** on `JSONB`.

```sql
CREATE INDEX events_payload_gin_idx
ON idx_cast_lab.events
USING gin (payload);
```

### 15.2. Filtering with `->>` Returning `TEXT`

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE payload ->> 'category' = 'audit';
```

`payload ->> 'category'` is **an expression returning `TEXT`**. A GIN index over the whole JSONB document does not automatically act as a B-tree equality index for that extracted text expression.

If the workload frequently filters by `category`:

```sql
CREATE INDEX events_payload_category_idx
ON idx_cast_lab.events ((payload ->> 'category'));
```

This creates a B-tree **expression index** on the extracted text value.

### 15.3. Which Approach to Choose?

| Need | Common Index Strategy |
|---|---|
| Broad containment queries `payload @> ...` | GIN tailored for JSONB and needed operators |
| Equality on a single text field `payload->>'category'` | B-tree expression index |
| Range queries on numbers inside JSONB | Controlled cast, or promote to a typed column if queried often |
| Full-text / substring matching | Full-text or trigram depending on goal |

### 15.4. Casting Numbers Extracted from `JSONB` Can Be Fragile

```sql
-- Illustrating the requirement:
-- WHERE (payload ->> 'total')::numeric >= 100
```

If any row contains `"total":"unknown"`, casting to numeric throws an error. An expression index on that cast will also fail to build if unconvertible values exist.

Do not build expression indexes over unvalidated JSONB values. If the field is important and queried by range often, consider a **constrained `NUMERIC` column** or a data normalization pipeline.

---

## 16. Joining Columns of Different Types: The Cast-in-`ON` Trap

Legacy systems often have newer tables using `BIGINT` keys alongside older staging/import tables storing the same IDs as `TEXT`.

### 16.1. Create a Staging Table with String IDs

```sql
CREATE TABLE idx_cast_lab.legacy_event_links (
    link_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    raw_event_id TEXT NOT NULL,
    link_type TEXT NOT NULL
);

INSERT INTO idx_cast_lab.legacy_event_links
    (raw_event_id, link_type)
SELECT event_id::text, 'export'
FROM idx_cast_lab.events
WHERE event_id BETWEEN 1 AND 30;

CREATE INDEX legacy_event_links_raw_id_idx
ON idx_cast_lab.legacy_event_links (raw_event_id);
```

### 16.2. Joining by Casting `BIGINT` to `TEXT`

```sql
EXPLAIN
SELECT e.event_id, l.link_id
FROM idx_cast_lab.events AS e
JOIN idx_cast_lab.legacy_event_links AS l
  ON e.event_id::text = l.raw_event_id;
```

PostgreSQL can execute this join correctly, yet **the B-tree on `e.event_id BIGINT` cannot be used directly for `e.event_id::text`**.

The planner may scan `events`, hash join, or use the index on `raw_event_id` depending on table sizes and join order. Do not claim the whole query “cannot use any index”; the specific issue is that **the BIGINT index lookup path into `e`** is blocked.

### 16.3. Joining by Casting `TEXT` to `BIGINT`

```sql
EXPLAIN
SELECT e.event_id, l.link_id
FROM idx_cast_lab.events AS e
JOIN idx_cast_lab.legacy_event_links AS l
  ON e.event_id = l.raw_event_id::bigint;
```

Because every demo row holds a valid integer string, this allows direct lookups into `events.event_id` from the cast staging value.

**However:** if `raw_event_id` contains `'abc'`, values overflowing `BIGINT`, unexpected whitespace/formatting, or non-standard values, the cast will fail at runtime. Never deploy this to production without validating the data.

### 16.4. Long-Term Design: Standardize Key Types

A more sustainable design uses properly typed columns:

```sql
CREATE TABLE idx_cast_lab.typed_event_links (
    link_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id BIGINT NOT NULL
        REFERENCES idx_cast_lab.events(event_id),
    link_type TEXT NOT NULL
);

-- Works only because demo data was generated from valid event_ids.
INSERT INTO idx_cast_lab.typed_event_links
    (event_id, link_type)
SELECT raw_event_id::bigint, link_type
FROM idx_cast_lab.legacy_event_links;

CREATE INDEX typed_event_links_event_id_idx
ON idx_cast_lab.typed_event_links (event_id);
```

The join query now has matching types:

```sql
EXPLAIN
SELECT e.event_id, l.link_id
FROM idx_cast_lab.events AS e
JOIN idx_cast_lab.typed_event_links AS l
  ON e.event_id = l.event_id;
```

### 16.5. What to Audit Before a Real Migration

Before migrating a legacy `TEXT` column to `BIGINT`:

1. Which values are not valid integers?
2. Do any values exceed the `BIGINT` range?
3. Does zero-padding carry business meaning (e.g., `'00042'` vs `'42'`)?
4. Are there `NULL`s or empty strings?
5. How will FKs, constraints, and indexes change?
6. Do any applications or APIs still expect strings?
7. Can the migration run online or does it need a maintenance window?
8. Are rollback steps and reconciliation checks in place?

If `'00042'` is a **string identifier**, do not coerce it into a number just for joins. Choose data types based on **data semantics**, not solely index speed.

---

## 17. Multi-Column Indexes: Usable, But the Leading Column Matters

Baseline index:

```sql
CREATE INDEX events_tenant_time_idx
ON idx_cast_lab.events
    (tenant_id, event_time DESC, event_id DESC);
```

was created in section 3; it is repeated here for analysis.

### 17.1. Tenant Equality + Time Range

```sql
SELECT event_id, event_time
FROM idx_cast_lab.events
WHERE tenant_id = 3
  AND event_time >= TIMESTAMPTZ '2026-02-01 00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-02-02 00:00+00'
ORDER BY event_time DESC, event_id DESC
LIMIT 20;
```

This is a favorable pattern: equality on the leading key, range on the next key, and matching sort order.

### 17.2. Time Range Only

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE event_time >= TIMESTAMPTZ '2026-02-01 00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-02-02 00:00+00';
```

There is no predicate on `tenant_id`. The planner **can** still consider the multi-column index in some scenarios depending on version and scan techniques, yet it usually **cannot exploit it as efficiently** as when the leading key is constrained. A separate index on `event_time` may be needed if the workload mainly queries across all tenants.

Do not claim “without the leading column, a multi-column index can never be used” across all PostgreSQL versions.

### 17.3. Casting the Leading Key Causes Clear Damage

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE tenant_id::text = '3'
  AND event_time >= TIMESTAMPTZ '2026-02-01 00:00+00';
```

Converting `tenant_id` to text prevents the leading key from acting as a direct `tenant_id=3` lookup. The query can lose fast tenant-slice narrowing in the composite index.

**Fix:**

```sql
WHERE tenant_id = 3::integer
  AND event_time >= TIMESTAMPTZ '2026-02-01 00:00+00'
```

### 17.4. B-Tree Ordering and Range Boundaries

In `(tenant_id, event_time, event_id)`, a range on `event_time` narrows the scan slice while trailing `event_id` breaks ties within the same timestamp. However, conditions on columns after a range **do not bound the scan as tightly as leading equality keys**.

Design key order around actual workload queries, not the order columns happen to appear in `SELECT`.

---

## 18. Partial Indexes and Predicate Implication

A partial index includes only rows satisfying its definition predicate.

```sql
CREATE INDEX events_queued_tenant_time_idx
ON idx_cast_lab.events (tenant_id, event_time)
WHERE state = 'queued';
```

### 18.1. Query Covered by the Partial Index

```sql
SELECT event_id, event_time
FROM idx_cast_lab.events
WHERE state = 'queued'
  AND tenant_id = 3
  AND event_time <
      TIMESTAMPTZ '2026-03-01 00:00+00';
```

Every row needed by the query satisfies `state='queued'`, so the query logically implies the partial index predicate.

### 18.2. Query That Does Not Imply the Predicate

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE state IN ('queued', 'running');
```

The query also needs `'running'` rows, which live outside the partial index. The queued partial index **cannot cover** the result on its own.

### 18.3. Generic Prepared Plans and Status Parameters

```sql
PREPARE find_by_state(TEXT, INTEGER) AS
SELECT event_id
FROM idx_cast_lab.events
WHERE state = $1
  AND tenant_id = $2;
```

If PostgreSQL generates a **generic plan** valid for any `$1`, it cannot assume `$1='queued'`. A **custom plan** that sees the bound value can make a different choice.

In an environment supporting `plan_cache_mode`:

```sql
SET plan_cache_mode = force_custom_plan;
EXPLAIN EXECUTE find_by_state('queued', 3);

SET plan_cache_mode = force_generic_plan;
EXPLAIN EXECUTE find_by_state('queued', 3);

RESET plan_cache_mode;
DEALLOCATE find_by_state;
```

**This is a plan-measurement example**, not a recommendation to force `force_custom_plan` application-wide. A custom plan may also skip the partial index if estimated cost favors another path.

### 18.4. Dedicated Query Contract for `queued`

If an endpoint genuinely **only fetches queued items**, keep the state filter as a constant:

```sql
PREPARE find_queued(INTEGER) AS
SELECT event_id
FROM idx_cast_lab.events
WHERE state = 'queued'
  AND tenant_id = $1;
```

The query easily proves predicate implication even when `tenant_id` is parameterized. Never hardcode `queued` if the endpoint must also support `running` or `done`.

---

## 19. `OR`, `IN`, `ANY`, `NOT`, and Selectivity

### 19.1. `IN` Usually Works Well for Equality Lookups

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE event_id IN (100, 101, 102);
```

The primary-key B-tree can handle small key sets efficiently.

### 19.2. `= ANY` with a Typed Array

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE event_id = ANY(ARRAY[100,101,102]::bigint[]);
```

`ANY` is a clean way to pass an ID list as an array; the predicate stays directly on `event_id` without turning the column into text. Efficiency still depends on list size, distribution, and plan choice.

### 19.3. `OR` Can Use `BitmapOr` or `Seq Scan`

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE event_id = 100
   OR external_id =
      '00000000-0000-0000-0000-000000000200'::uuid;
```

Because each branch has its own index, the planner can combine results or pick another access path.

```text
Bitmap Heap Scan
  -> BitmapOr
      -> Bitmap Index Scan on events_pkey
      -> Bitmap Index Scan on events_external_id_idx
```

This is an **illustrative plan tree**, not a guaranteed exact output. `OR` does not automatically disable all indexes.

### 19.4. `OR` Over Cast Expressions

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE event_id::text = '100'
   OR external_id::text =
      '00000000-0000-0000-0000-000000000200';
```

Both branches apply TEXT expressions to columns indexed in their native types. The plan can be substantially worse than using typed operators on both sides.

### 19.5. `!=` and `NOT IN`

```sql
WHERE state <> 'done'
```

is not inherently a narrow lookup. If many rows are not `'done'`, the planner may need to read a large share of the table. `NOT IN` also has **NULL semantics** to watch out for: if the right-hand side contains `NULL`, results can differ from expectations.

Do not rewrite `NOT IN` as `NOT EXISTS` solely for index usage; first verify semantics, NULL behavior, and cardinality.

### 19.6. Prefix `LIKE` with `OR`

```sql
WHERE customer_email LIKE 'User1%'
   OR customer_email LIKE 'User2%'
```

The planner can consider matching pattern indexes and combine them. If one branch is `LIKE '%42%'`, that branch can prevent a B-tree prefix index from efficiently covering the whole query.

---

## 20. Prepared Statements: Parameter Types Must Be Intentional

### 20.1. `PREPARE` with `BIGINT`

```sql
PREPARE get_event(BIGINT) AS
SELECT event_id, state
FROM idx_cast_lab.events
WHERE event_id = $1;

EXPLAIN EXECUTE get_event(1000);
DEALLOCATE get_event;
```

`$1` is declared as `BIGINT`. The predicate leaves the column untouched.

### 20.2. `PREPARE` with `TEXT` and Casting on the Right Side

If an API receives text IDs and client code cannot be changed immediately:

```sql
PREPARE get_event_from_text(TEXT) AS
SELECT event_id, state
FROM idx_cast_lab.events
WHERE event_id = $1::bigint;

EXPLAIN EXECUTE get_event_from_text('1000');
DEALLOCATE get_event_from_text;
```

The cast applies to the **parameter**, not the `event_id` column. However, invalid text values will still throw an error during casting.

**Better solution:** validate and bind the ID with the proper type directly in the API/driver layer.

### 20.3. Do Not “Normalize” via `CAST(event_id AS text)`

```sql
-- Not preferred:
-- WHERE event_id::text = $1
```

This solves a type mismatch backwards: converting every indexed column value to match the client's input type.

### 20.4. When Typed Parameters Still Aren't Enough

If the query contains:

```sql
WHERE lower(customer_email) = $1::text
```

even though `$1` is valid text, you still need an index on **`lower(customer_email)`** or a different schema design. Proper parameter binding **does not eliminate** functions wrapped around the column.

### 20.5. Generic Plans Differ from Custom Plans

Even without harmful casts in SQL, a generic plan sometimes cannot exploit the high selectivity of a specific parameter value. On skewed workloads, the planner may pick different paths when generating value-specific custom plans.

Distinguish:

- **Type issue:** mismatched types, operators, or index keys.
- **Selectivity / plan cache issue:** the query can use an index, yet a generic plan or bad estimates pick another path.

Do not alter type casting to “fix” a plan-cache problem when the root cause is data skew.

---

## 21. Java/JDBC: Binding Proper Types to Keep Predicates Indexable

### 21.1. Looking Up `BIGINT` with `setLong`

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class EventRepository {
    public String findState(Connection connection, long eventId)
            throws SQLException {
        String sql = """
            SELECT state
            FROM idx_cast_lab.events
            WHERE event_id = ?
            """;

        try (PreparedStatement ps =
                 connection.prepareStatement(sql)) {
            ps.setLong(1, eventId);

            try (ResultSet rs = ps.executeQuery()) {
                return rs.next() ? rs.getString("state") : null;
            }
        }
    }
}
```

The driver sends a numeric parameter matching `BIGINT`, requiring no cast on the column.

### 21.2. Parse Input Outside the Database Transaction

If the API receives a string:

```java
public long parseEventId(String rawId) {
    try {
        return Long.parseLong(rawId);
    } catch (NumberFormatException e) {
        throw new IllegalArgumentException(
            "eventId must be a valid 64-bit integer", e
        );
    }
}
```

The application should distinguish malformed input from “valid ID not found,” rather than passing arbitrary strings into `WHERE event_id::text = ?`.

### 21.3. Looking Up `UUID`

```java
import java.util.UUID;

UUID id = UUID.fromString(rawExternalId);
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT event_id FROM idx_cast_lab.events "
      + "WHERE external_id = ?")) {
    ps.setObject(1, id);
    try (ResultSet rs = ps.executeQuery()) {
        // Read results per the application contract.
    }
}
```

Avoid `external_id::text = ?` when the real intent is UUID comparison.

### 21.4. Exact Decimals

```java
import java.math.BigDecimal;

BigDecimal amount = new BigDecimal("50.00");
ps.setBigDecimal(1, amount);
```

Preserve `NUMERIC` for monetary values rather than casting `amount::double precision` or `amount::text` to fit client data.

### 21.5. Timestamps and Date Ranges

Convert the **business-timezone calendar day** into two instants in application code, then bind two typed endpoints.

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.OffsetDateTime;

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate day = LocalDate.of(2026, 2, 10);

ZonedDateTime startLocal = day.atStartOfDay(zone);
ZonedDateTime endLocal = day.plusDays(1).atStartOfDay(zone);

OffsetDateTime begin = startLocal.toOffsetDateTime();
OffsetDateTime end = endLocal.toOffsetDateTime();

String sql = """
    SELECT event_id, event_time
    FROM idx_cast_lab.events
    WHERE tenant_id = ?
      AND event_time >= ?
      AND event_time < ?
    ORDER BY event_time
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, tenantId);
    ps.setObject(2, begin);
    ps.setObject(3, end);
    // Execute query and process ResultSet.
}
```

Converting each local day boundary independently handles DST transitions in DST-observing zones far better than assuming every day is 24 hours.

**Note:** this JDBC example relies on a driver supporting `OffsetDateTime` binding for `TIMESTAMPTZ`. Verify your driver/framework version; if a framework manages transactions and connections, follow its boundaries.

### 21.6. Never Concatenate User Input as Literals

Avoid:

```java
// Do not do:
// String sql = "WHERE event_id = " + rawId;
```

Using `PreparedStatement` prevents SQL injection and makes parameter types explicit. **However**, parameterization alone does not guarantee index usage; column types, parameter types, expressions, and plans still matter.

---

## 22. Expression Index, Regular Index, or Schema Change?

When a query is slow due to a cast, do not rush to create an expression index for every query. Pick the solution matching the data's meaning.

| Scenario | Preferred Approach |
|---|---|
| `id::text = '123'` where ID is actually numeric | Convert literal/parameter to BIGINT and use the ID index |
| `created_at::date = day` to filter a calendar day | Use a half-open timestamp range with explicit time zone |
| Frequent `lower(email) = ...` with case-insensitive semantics | Expression index on `lower(email)` or normalization strategy |
| Frequent `payload->>'category' = ...` lookup | Expression index, promoted typed column, or suited JSONB design |
| Frequent `LIKE '%term%'` | Trigram or full-text depending on semantics, not plain B-tree |
| Joining `TEXT` key to `BIGINT` key | Standardize typed schema/staging and validate data |
| Hot low-volume status filter | Partial index with matching predicate |
| Tenant + time + `ORDER BY` queries | Composite index with proper key order |
| Very large time ranges with physical order | Consider BRIN or partitioning depending on workload |

### 22.1. Rewriting the Query Is Usually Lower Risk Than Changing the Schema

If results remain identical for all valid rows:

```sql
WHERE event_id = $1::bigint
```

is usually easier to ship than creating and permanently maintaining a new index on `event_id::text`.

Likewise, writing a timestamp range preserves existing indexes without adding an expression index.

### 22.2. When Does an Expression Index Make Sense?

When business logic **genuinely needs the transformed value** and no simple equivalent exists on the raw column:

```sql
WHERE lower(customer_email) = ...
```

or:

```sql
WHERE payload ->> 'category' = ...
```

Expression indexes precompute and store the searchable value, trading write overhead and storage space for read speed.

### 22.3. When Is a Schema Change the Long-Term Fix?

If the system repeatedly casts between `TEXT` and `BIGINT` in joins across millions of rows, that often signals **mismatched column types in the data model**. A key-standardization migration (with validation and backward compatibility) is cleaner than scattering expression indexes everywhere.

Do not convert `TEXT` to numbers when the text carries leading zeros, multiple formats, or alphabetic characters.

---

## 23. Statistics and Selectivity: An Indexable Query May Still Seq Scan

### 23.1. Comparing Narrow vs Broad Queries

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id
FROM idx_cast_lab.events
WHERE event_id = 1000;
```

versus:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM idx_cast_lab.events
WHERE amount >= 1;
```

In the seeded data, nearly every row satisfies `amount>=1`, so Seq Scan can be the optimal plan even though `amount` has a B-tree.

### 23.2. Inspecting Per-Column Statistics

```sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    correlation
FROM pg_stats
WHERE schemaname = 'idx_cast_lab'
  AND tablename = 'events'
  AND attname IN ('state', 'tenant_id', 'amount', 'deleted_at');
```

Statistics help the planner estimate frequencies and distributions. They are **estimates** and can become stale after bulk writes.

### 23.3. Refreshing Statistics

```sql
ANALYZE idx_cast_lab.events;
```

`ANALYZE table` gathers statistics; it differs from `EXPLAIN ANALYZE SELECT`, which **executes the `SELECT` to measure it**.

### 23.4. Correlated Columns

If `tenant_id`, `state`, and event types have correlated distributions, single-column statistics can yield poor cardinality estimates. PostgreSQL supports **extended statistics** for dependencies and MCVs:

```sql
CREATE STATISTICS events_tenant_state_stats
    (dependencies, mcv)
ON tenant_id, state
FROM idx_cast_lab.events;

ANALYZE idx_cast_lab.events;
```

Do not assume extended statistics fix every join or cast expression. They are a targeted tool when observed row estimates are off.

### 23.5. Buffers and Actual Rows Reveal True Cost

A plan showing:

```text
Seq Scan on events
  Filter: (event_id::text = '1000')
  Rows Removed by Filter: ...
```

indicates the column-side expression prevented direct index-key lookup. Still, to decide if fixing it is worthwhile, inspect row counts, runtime, buffers, and application call frequency.

---

## 24. Collation, Operator Class, and Index Eligibility

### 24.1. Collation Affects More Than `ORDER BY`

Collation governs text comparison and sorting rules. For a B-tree text index, key order and `LIKE` support depend on both collation and operator class.

```sql
SELECT
    current_setting('lc_collate') AS database_collate;
```

This shows the environment setting; individual columns or queries can override collation, so never assume all text columns share identical semantics.

### 24.2. `text_pattern_ops`

```sql
CREATE INDEX events_email_pattern_idx
ON idx_cast_lab.events
    (customer_email text_pattern_ops);
```

This index was created in section 11 and is shown again as a reminder. That operator class targets prefix/pattern predicates.

Do not assume a pattern index optimizes locale-based range comparisons the way a default text index does. Different opclasses serve different purposes.

### 24.3. `COLLATE` on a Column Can Alter the Query Expression

```sql
-- Example query changing collation on the expression:
-- WHERE customer_email COLLATE "C" = 'User42@Example.test'
```

If the index uses a different collation, PostgreSQL may be unable to use it for operations requiring the query's collation. For complex text queries, inspect **index collation, expression collation, and `EXPLAIN`**.

### 24.4. `CITEXT` and Nondeterministic Collations

`citext` is an extension offering a case-insensitive text type with its own semantics. Nondeterministic collations also offer specific behaviors depending on PostgreSQL version. Neither is a drop-in equivalent to `lower(text)` across all applications.

Before altering column types or collations on live data, evaluate uniqueness, pattern-query support, Unicode behavior, migration impact, and performance.

---

## 25. Cleanup and Safe Experimentation

### 25.1. Never Drop Shared Schemas

This lesson assumes `idx_cast_lab` was created solely for your practice session. Only after confirming nobody else uses it and that you have permission:

```sql
-- Use only in the lab database after confirming scope:
-- DROP SCHEMA idx_cast_lab CASCADE;
```

Never run `DROP SCHEMA ... CASCADE` in a shared environment where it could destroy others' objects.

### 25.2. Don't Force Every Plan to Use an Index

```sql
-- Diagnostic test on an isolated session; do not leave enabled long-term:
SET enable_seqscan = off;

EXPLAIN
SELECT event_id
FROM idx_cast_lab.events
WHERE event_id = 1000;

RESET enable_seqscan;
```

`enable_seqscan=off` merely adds a large cost penalty to Seq Scan rather than forbidding it outright. It is a diagnostic probe, **not a production tuning method**.

### 25.3. Capturing Plans in Real Environments

When investigating a slow query, record:

- PostgreSQL version.
- SQL text and parameter types.
- Role, tenant, and RLS policies if active.
- DDL of relevant indexes.
- Estimated plan from `EXPLAIN`.
- Actual plan from `EXPLAIN (ANALYZE, BUFFERS)` when safe to run.
- Row counts, loops, buffers, execution time, and query frequency.
- Data distribution, `ANALYZE` history, and cache state.

Never paste personal data or secrets embedded in SQL into public logs.

---

## 26. Common Mistakes

**1. “If a column is indexed, every `WHERE` mentioning it uses the index.”** False. Expressions, operators, opclasses, and costs matter.

**2. “Any `CAST` destroys index usage.”** Too absolute. Compatible casts and cross-type operators still have index support.

**3. “Casting a `BIGINT` column to `TEXT` is the same as casting the literal to `BIGINT`.”** No. Access paths and semantics differ.

**4. “`event_id = '100'` always converts the column to `TEXT`.”** False. Untyped string literals can be resolved as `BIGINT` from context.

**5. “Passing every parameter as `String` is fine.”** No. Use bind types matching the schema and domain logic.

**6. “`event_id::text='abc'` is a good way to handle invalid ID inputs.”** Bad design. Validate inputs and use numeric types.

**7. “`amount::double precision` is identical to `NUMERIC` for money.”** False. Precision loss and semantic shifts occur.

**8. “`amount+5=55` will definitely be rewritten to `amount=50` by the planner.”** Not guaranteed for arbitrary expressions.

**9. “`event_time::date=...` is always fast because dates are smaller than timestamps.”** No. It casts the column and can prevent using a standard index.

**10. “`TIMESTAMPTZ::date` does not depend on `TimeZone`.”** False. Local calendar dates depend on session time zone.

**11. “Every day is 24 hours in every time zone.”** False in DST-observing zones.

**12. “`BETWEEN 00:00 and 23:59:59` covers every timestamp in a day.”** It can miss fractional seconds.

**13. “`date_trunc()` and `to_char()` on a column don't affect access paths.”** They can prevent using a B-tree on the raw column.

**14. “Creating an expression index on `TIMESTAMPTZ::date` is always valid.”** No. Session-timezone-dependent expressions are not immutable.

**15. “An index on raw email covers all `lower(email)` queries.”** Not by default; an expression index may be required.

**16. “An expression index on `lower(email)` makes `email=...` case-insensitive.”** No. The SQL predicate determines semantics.

**17. “`LIKE '%term%'` uses a B-tree prefix index just like `LIKE 'term%'`.”** No. Leading wildcards eliminate the fixed prefix.

**18. “`LIKE 'prefix%'` is always indexed under every collation.”** No. Check pattern opclass, collation, and the plan.

**19. “`ILIKE` is handled identically to `LIKE` by every B-tree.”** False in general.

**20. “`pg_trgm` is free.”** No. The extension and index carry write/storage overhead and pattern limitations.

**21. “`COALESCE(deleted_at, sentinel)` is always equivalent to `IS NULL`.”** Not if real data can contain the sentinel value.

**22. “`IS NULL` cannot use a B-tree.”** False. PostgreSQL can index and look up NULLs.

**23. “A `JSONB` index automatically speeds up all `->>` text equality checks.”** No. Distinguish GIN containment from B-tree expression indexes.

**24. “Casting every `JSONB` value to `NUMERIC` is always safe.”** No. Non-numeric values cause runtime errors.

**25. “Joining `BIGINT::TEXT` to `TEXT` is always as optimal as `BIGINT=BIGINT`.”** No. One side may lose numeric index lookup.

**26. “Replacing all `TEXT` codes with `BIGINT` is a sound optimization.”** Wrong if codes include letters or meaningful leading zeros.

**27. “Composite indexes work equally well regardless of column order.”** No. Leading keys, equality vs range, and `ORDER BY` matter.

**28. “Without the leading key, PostgreSQL can never consider a multi-column index.”** Too absolute, though effectiveness usually differs significantly.

**29. “A partial index on `queued` covers `queued` or `running` queries.”** False. `running` lies outside the predicate.

**30. “`state=$1` in a generic plan always proves `state='queued'`.”** False. `$1` could be any state.

**31. “A custom plan is guaranteed to pick the partial index.”** No. Cost and statistics still decide.

**32. “`OR` always disables all indexes.”** False. PostgreSQL may use `BitmapOr` or other plans.

**33. “`NOT IN` with `NULL` behaves identically to `NOT EXISTS`.”** Not by default; NULLs affect SQL three-valued logic.

**34. “`Index Scan` is always faster than `Seq Scan`.”** No. Fetching most of a table is often faster sequentially.

**35. “Seeing `Index Cond` in `EXPLAIN` proves the API is fast.”** No. Actual rows, heap fetches, buffers, network, and app time also matter.

**36. “Setting `enable_seqscan=off` is how you fix the planner.”** No. It is mainly diagnostic; fix statistics, indexes, or queries instead.

**37. “To use an index, cast the column to match the input rather than fixing the input.”** Usually backwards when the column already has the right type.

**38. “An expression index on a non-immutable function is fine if the developer knows it ‘rarely changes’.”** No. True immutability must be respected.

**39. “Adding indexes never hurts writes.”** False. Indexes add storage, WAL, and maintenance work.

**40. “A plan on a tiny table proves behavior for all production workloads.”** No. Data size, version, parameters, cache, collation, and concurrency all differ.

---

## 27. Practice Exercises with Guided Answers

### Exercise 1 — Identifying Where the Cast Occurs

Compare two predicates:

```sql
WHERE event_id::text = '1000'
WHERE event_id = '1000'::bigint
```

**Answer:** The second keeps the `BIGINT` column intact and fits the primary-key B-tree. The first converts the column to a TEXT expression with no matching index in the lab.

### Exercise 2 — Untyped String Literal

```sql
WHERE event_id = '1000'
```

**Question:** Does the planner necessarily cast `event_id` to text?

**Answer:** No. The literal `'1000'` starts as `unknown`, and PostgreSQL can resolve it to `BIGINT` from the comparison context.

### Exercise 3 — Properly Typed `NUMERIC` Filter

**Task:** find events with amount equal to 50.00 using the index on `amount`.

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE amount = 50.00::numeric;
```

Do not convert the column to text or double just to match a literal.

### Exercise 4 — Cast on a Monetary Column

```sql
WHERE amount::text = '50.00'
```

**Answer:** The predicate evaluates a text expression rather than the numeric key; use `WHERE amount=50.00::numeric` if the business intent is numeric comparison.

### Exercise 5 — Filtering a UTC Day

**Task:** retrieve all of February 10, 2026 UTC without using `event_time::date`.

```sql
WHERE event_time >= TIMESTAMPTZ '2026-02-10 00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-02-11 00:00+00'
```

### Exercise 6 — Filtering a Calendar Day in Vietnam

**Answer:**

```sql
WHERE event_time >=
    (TIMESTAMP '2026-02-10 00:00:00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh')
  AND event_time <
    (TIMESTAMP '2026-02-11 00:00:00'
       AT TIME ZONE 'Asia/Ho_Chi_Minh')
```

Convert both local endpoints separately to represent the calendar day accurately in that time zone.

### Exercise 7 — Why Does `TIMESTAMPTZ::DATE` Require Caution?

**Answer:** It depends on session `TimeZone` and places a conversion on the column. When querying a local calendar day, build a timestamp range with an explicit time zone.

### Exercise 8 — Not Every Function Can Be Indexed

```sql
-- CREATE INDEX ... ON ... ((event_time::date));
```

where `event_time` is `TIMESTAMPTZ`.

**Answer:** Converting `timestamptz` to `date` depends on time zone, failing the immutability requirement for standard index expressions.

### Exercise 9 — `LOWER(email)`

**Task:** create an index suited for case-insensitive email queries.

```sql
CREATE INDEX email_lower_exercise_idx
ON idx_cast_lab.events (lower(customer_email));
```

The lab already has an equivalent `events_lower_email_idx`, so this illustrates syntax; avoid duplicate indexes in production.

### Exercise 10 — Prefix `LIKE`

**Question:** How do `LIKE 'User1%'` and `LIKE '%User1%'` differ for a B-tree?

**Answer:** The first has a fixed prefix and can use a B-tree/pattern opclass when appropriate; the second starts with a wildcard and lacks a contiguous prefix range.

### Exercise 11 — Substring `ILIKE`

**Task:** propose an index for `ILIKE '%user42%'`.

**Answer:** Consider `pg_trgm` with a GIN/GiST trigram index and benchmark the workload. Do not rely on a plain text B-tree as the default fix.

### Exercise 12 — `IS NULL` and `COALESCE`

**Task:** fetch live rows using `deleted_at`.

```sql
WHERE deleted_at IS NULL
```

**Answer:** Explicit condition, avoiding fake sentinel values in `COALESCE`. Can pair with a partial index `WHERE deleted_at IS NULL`.

### Exercise 13 — `UUID`

**Task:** compare `external_id UUID` against a client-supplied ID.

**Answer:** Parse or bind a proper `UUID` on the client; in SQL use `external_id = ?` with a typed parameter or `'...'::uuid` literal. Avoid `external_id::text = ?`.

### Exercise 14 — `JSONB`

**Question:** Will `payload->>'category'='audit'` automatically be served by a GIN index on `payload` like a text B-tree?

**Answer:** No. That is text-expression equality. Consider a B-tree expression index or rewrite to containment `payload @> '{"category":"audit"}'::jsonb` with a suited GIN index.

### Exercise 15 — Joining Mismatched Key Types

```sql
ON e.event_id::text = l.raw_event_id
```

**Answer:** This can block the index on `e.event_id BIGINT` because `e`'s side becomes a text expression. With validated legacy data, you can cast the staging side to `bigint`; long-term, standardize the key type.

### Exercise 16 — Non-Numeric Legacy Data

**Question:** Should you immediately use `raw_event_id::bigint` on unvalidated imported data?

**Answer:** No. Non-numeric characters or out-of-range values will cause errors; first inspect data semantics and validate/clean the data.

### Exercise 17 — Composite Index

Index:

```sql
ON events (tenant_id, event_time DESC, event_id DESC)
```

**Task:** write a query that utilizes it well.

```sql
SELECT event_id
FROM idx_cast_lab.events
WHERE tenant_id = 3
  AND event_time >= TIMESTAMPTZ '2026-02-01 00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-02-02 00:00+00'
ORDER BY event_time DESC, event_id DESC
LIMIT 20;
```

### Exercise 18 — Composite Index and Leading-Key Cast

```sql
WHERE tenant_id::text = '3'
  AND event_time > TIMESTAMPTZ '2026-02-01 00:00+00'
```

**Answer:** Casting the leading key prevents efficient tenant narrowing. If `tenant_id` is numeric, write `tenant_id=3::integer`.

### Exercise 19 — Partial Index on `queued`

Index:

```sql
ON events (tenant_id, event_time)
WHERE state='queued'
```

**Question:** Does `WHERE state IN ('queued','running')` imply the predicate?

**Answer:** No; the query also needs `running`. The queued partial index cannot cover the full result set on its own.

### Exercise 20 — Generic Prepared Statement

**Question:** Does `WHERE state=$1` always let a generic plan use the partial index `state='queued'`?

**Answer:** No. A generic plan must remain valid when `$1` is `done` or `running`. A custom plan with `'queued'` can consider the index, still subject to cost.

### Exercise 21 — `OR` and Indexes

```sql
WHERE event_id = 100
   OR external_id =
       '00000000-0000-0000-0000-000000000200'::uuid
```

**Answer:** PostgreSQL can combine the two indexes via `BitmapOr` or pick another plan; `OR` does not inherently disable all indexes.

### Exercise 22 — Comparing Selectivity

**Question:** Will `amount>=1`, which returns nearly the whole table, still use the `amount` index?

**Answer:** It is technically indexable, yet the planner may choose `Seq Scan` because nearly all rows match and index/heap fetches cost more.

### Exercise 23 — `EXPLAIN` vs `EXPLAIN ANALYZE`

**Question:** Is it safe to run `EXPLAIN ANALYZE DELETE` “just to see the plan”?

**Answer:** No. It executes the `DELETE`. Use `EXPLAIN DELETE` without `ANALYZE` to inspect the estimated plan.

### Exercise 24 — Using `EXPLAIN` to Verify Casts

**Task:** compare the plans of:

```sql
EXPLAIN
SELECT event_id FROM idx_cast_lab.events
WHERE event_id = 1000;

EXPLAIN
SELECT event_id FROM idx_cast_lab.events
WHERE event_id::text = '1000';
```

**Answer:** Inspect `Index Cond` vs `Filter`, access path, and estimated rows. Never assume both use the same B-tree.

### Exercise 25 — Choosing the Right Fix

**Scenario:** the application always needs case-insensitive email lookups, while the table stores mixed-case emails.

**Answer:** Use `lower(customer_email)` with an expression index, or adopt normalized storage / a type / a collation with a clear contract. Never use `WHERE customer_email = ...` and claim case-insensitivity if database semantics differ.

### Exercise 26 — Performance vs Semantics

**Question:** Just to get an index used, can you change `amount::text='50.00'` to `amount=50` without checking requirements?

**Answer:** Always verify semantics first. If business logic genuinely searches for **numeric 50**, the change is right; if it searches for a specific string formatting, the two conditions may not be strictly equivalent. Optimization must never silently alter business results.

---

## 28. Checklist for Optimizing Indexable Predicates

### Before Editing SQL

1. **Clarify intent:** is the query matching a number, text, local calendar date, or absolute timestamp?
2. **Check column types:** `BIGINT`, `TEXT`, `UUID`, `NUMERIC`, `TIMESTAMPTZ`, `JSONB`?
3. **Check parameter types:** what does JDBC/ORM bind? Is a string input mistaken for the column's type?
4. **Inspect real indexes:** keys, expressions, opclasses, collations, partial predicates, and key order.
5. **Inspect operators:** does B-tree support that operator and comparison type?
6. **Spot column-side functions:** `::text`, `::date`, `lower()`, `COALESCE`, `date_trunc`, `to_char`, arithmetic?
7. **Avoid rigid rules:** some compatible casts and cross-type operators still use indexes.

### When Rewriting

8. **Keep columns raw:** cast literals/parameters when semantics remain unchanged.
9. **Filter time via two bounds:** `>= begin` and `< end` with an explicit time zone.
10. **Don't drop fractional seconds:** avoid `23:59:59`.
11. **Preserve NULL semantics:** use `IS NULL` and `IS NOT NULL`, avoiding arbitrary sentinels.
12. **Match string semantics:** case-sensitive vs insensitive, collation, prefix vs substring?
13. **Prefix `LIKE`:** consider `text_pattern_ops` or trigram indexes as appropriate.
14. **Preserve monetary types:** avoid unnecessary conversion from `NUMERIC` to floating point.
15. **Join on matching key types:** avoid forcing one side to cast every row when schema standardization is feasible.
16. **Composite indexes:** filter on leading keys, ranges, and matching `ORDER BY`.
17. **Partial indexes:** ensure queries imply the predicate; check prepared generic/custom plans.
18. **Expression indexes:** use only when the transformation cannot be removed and the function is truly immutable.

### During Measurement and Rollout

19. **Compare real `EXPLAIN` output:** `Index Cond`, `Filter`, row estimates, sort/heap fetches.
20. **Use `ANALYZE` safely on `SELECT`s:** check actual rows, buffers, and timings.
21. **Never run `EXPLAIN ANALYZE` carelessly on DML:** it executes real writes.
22. **Account for selectivity:** an indexable query may rightly pick a `Seq Scan`.
23. **Keep stats fresh:** run `ANALYZE` and add extended statistics when needed.
24. **Measure before/after repeatedly:** control cache, data, parameters, and concurrency.
25. **Check write cost:** every added index affects `INSERT`/`UPDATE`/`DELETE`.
26. **Test under the real role:** RLS and collation/session settings can change plans.
27. **Never fix plans via server-wide planner overrides:** avoid leaving `enable_seqscan=off` enabled.
28. **Document changes and verify post-rollout:** correctness, latency, index size, and rollback readiness.

---

## 29. Summary

**A predicate is indexable when its operator, data types, and expression match the structure stored by an index; only then does the PostgreSQL planner decide whether choosing that index is cost-effective.**

Key principles:

- **Do not transform an indexed column needlessly**: `event_id::text`, `amount::text`, `event_time::date`, or arithmetic around the column can block standard B-tree access.
- **Keep values and parameters properly typed**: `event_id=$1::bigint`, `amount=$1::numeric`, `external_id=$1::uuid`; in JDBC, bind `long`, `BigDecimal`, and `UUID` directly.
- **Not all casts disable indexes**: PostgreSQL supports binary-compatible casts and cross-type operators; verify via opclass/family and `EXPLAIN`.
- **Use half-open timestamp ranges instead of casting timestamps to dates**, and specify the business time zone to avoid selecting the wrong rows.
- **When querying transformed values is unavoidable**, consider expression indexes (`lower(email)`, JSONB field extraction) or schema normalization, while accounting for write overhead.
- **String matching is its own problem space**: prefix `LIKE`, `ILIKE`, collation, pattern opclasses, and trigram substring search are not interchangeable.
- **Multi-column and partial indexes depend on predicate structure**: key order, predicate implication, generic/custom prepared plans, and statistics.
- **Indexability does not guarantee index selection**: `Seq Scan` remains sensible when fetching most of a table, and one `EXPLAIN` never represents every parameter or workload.

**The question to ask before every optimization:** “Is this predicate comparing the **indexed column value** or the **result of transforming that column**? If the transformation is required, which index actually stores that expression? If it is not required, can we convert the input to the proper type and leave the column intact?”

### Official PostgreSQL Documentation

- [Indexes — Overview](https://www.postgresql.org/docs/current/indexes.html).
- [Index Types](https://www.postgresql.org/docs/current/indexes-types.html).
- [Multicolumn Indexes](https://www.postgresql.org/docs/current/indexes-multicolumn.html).
- [Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html).
- [Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html).
- [Operator Classes and Operator Families](https://www.postgresql.org/docs/current/indexes-opclass.html).
- [Indexes and Collations](https://www.postgresql.org/docs/current/indexes-collations.html).
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html) and [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html).
- [Type Conversion](https://www.postgresql.org/docs/current/typeconv.html).
- [Data Type Formatting Functions](https://www.postgresql.org/docs/current/functions-formatting.html).
- [Date/Time Functions and Operators](https://www.postgresql.org/docs/current/functions-datetime.html).
- [Pattern Matching](https://www.postgresql.org/docs/current/functions-matching.html).
- [pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html).
- [PREPARE — generic/custom plans](https://www.postgresql.org/docs/current/sql-prepare.html).
