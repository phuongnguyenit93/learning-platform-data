# NULL in Unique Constraints and Choosing NULLS NOT DISTINCT in PostgreSQL

When designing user, order, or integration tables, we often add `UNIQUE` so two records cannot share the same email, identifier, or business key combination. Yet an important question is easily overlooked: **if one or more columns in a `UNIQUE` constraint contain `NULL`, are two rows considered duplicates or not?**

In PostgreSQL, the default answer is: **`NULL` values are treated as distinct when checking uniqueness**. Thus, a column `email TEXT UNIQUE` still permits multiple rows with `email IS NULL`. Starting in **PostgreSQL 15**, you can select the opposite behavior using **`UNIQUE NULLS NOT DISTINCT`** or **`CREATE UNIQUE INDEX ... NULLS NOT DISTINCT`**, treating two `NULL` values in the same position as non-distinct during uniqueness checks.

This is not merely a syntactic detail. It reflects a **data rule**:

- May accounts without a provided email appear multiple times?
- Within each organization, may multiple records exist with an unknown external reference code?
- How should a composite key `(tenant_id, external_code)` handle `external_code IS NULL`?
- When using `INSERT ... ON CONFLICT`, do two writes with `NULL` insert two rows or update the same row?
- If a table already contains multiple `NULL` values, how must they be handled before switching to `NULLS NOT DISTINCT`?

This lesson belongs to the **Constraints** chapter of the *Database Engine Relational PostgreSQL* module. We will practice with dedicated tables, compare default `UNIQUE` with `NULLS NOT DISTINCT`, analyze composite keys, unique indexes, duplicate detection, and safe deployment scenarios.

> **Version requirement:** `NULLS NOT DISTINCT` for unique constraints and indexes is supported starting in **PostgreSQL 15**. On PostgreSQL 14 or earlier, do not run commands using that syntax; the end of this lesson covers workarounds for certain cases. Run `SHOW server_version;` before practicing.

## 1. Reviewing NULL and UNIQUE

### 1.1. NULL Is Not an Ordinary Value

In SQL, `NULL` represents an **absent or unknown** value, not an empty string `''`, zero `0`, or the literal string `'NULL'`.

```sql
SELECT
    NULL = NULL AS so_sanh_bang,
    NULL <> NULL AS so_sanh_khac,
    NULL IS NULL AS kiem_tra_null,
    NULL IS NOT DISTINCT FROM NULL AS hai_gia_tri_khong_phan_biet;
```

Result:

| so_sanh_bang | so_sanh_khac | kiem_tra_null | hai_gia_tri_khong_phan_biet |
|---|---|---|---|
| `NULL` | `NULL` | `true` | `true` |

Both `=` and `<>` with `NULL` normally evaluate to **unknown** (displayed as `NULL`), not `true` or `false`. To test for missing values, use `IS NULL` or `IS NOT NULL`.

PostgreSQL also supports:

```sql
SELECT
    10 IS DISTINCT FROM 10       AS a,
    10 IS DISTINCT FROM NULL     AS b,
    NULL IS DISTINCT FROM NULL   AS c,
    NULL IS NOT DISTINCT FROM NULL AS d;
```

The results are `false`, `true`, `false`, and `true` respectively. `IS DISTINCT FROM` and `IS NOT DISTINCT FROM` always produce a clear boolean result even when `NULL` is involved.

**Important:** Adding `NULLS NOT DISTINCT` to a `UNIQUE` constraint **does not change `NULL = NULL` across the database**. It only adjusts how two keys are compared for duplicates within that specific unique constraint or index.

### 1.2. What Does UNIQUE Protect?

A `UNIQUE` constraint requires that no two rows share **a key combination considered duplicate** under the constraint semantics and the relevant data types/collations.

Single-column example:

```sql
CREATE TABLE demo_unique_basic (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT UNIQUE
);
```

When `email` is non-NULL, two equal values such as `'a@example.test'` and `'a@example.test'` cannot coexist. By default, however, PostgreSQL **does not treat two `NULL` values as a duplicate key** in `UNIQUE`.

### 1.3. How UNIQUE Differs from PRIMARY KEY

| Constraint | Enforces Uniqueness? | Allows NULL? |
|---|---|---|
| `PRIMARY KEY (id)` | Yes | **No**: primary key columns must be `NOT NULL` |
| `UNIQUE (email)` | Yes | Yes, and by default **multiple `NULL`s** |
| `UNIQUE NULLS NOT DISTINCT (email)` | Yes | Yes, but **at most one `NULL` row** in a single-column key |
| `UNIQUE (email)` + `email NOT NULL` | Yes | No; with no NULLs possible, NULL distinctness has no effect |

A table can have many `UNIQUE` constraints but only one `PRIMARY KEY`. `PRIMARY KEY` defines the mandatory row identifier; `UNIQUE` typically protects secondary business keys.

## 2. Preparing the Practice Environment

To keep examples isolated from other data, create a separate schema:

```sql
SHOW server_version;
SHOW server_version_num;

CREATE SCHEMA IF NOT EXISTS null_unique_lab;
```

The tables use distinct names such as `users_default`, `users_strict`, and `tenant_refs_default`. On a shared database, ensure you have privileges to create schemas/tables, and do not run `DROP` cleanup statements unless you own the demo environment.

Some tests intentionally trigger duplicate-key errors. They are **commented out** so you can run all valid SQL blocks sequentially first; when you want to observe an error message, uncomment **one statement at a time** in your lab environment.

## 3. Default UNIQUE: Permitting Multiple NULLs

Create a table storing optional emails:

```sql
CREATE TABLE null_unique_lab.users_default (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT,
    display_name TEXT NOT NULL,
    CONSTRAINT uq_users_default_email UNIQUE (email)
);
```

Insert data:

```sql
INSERT INTO null_unique_lab.users_default (email, display_name)
VALUES
    (NULL, 'Account without email A'),
    (NULL, 'Account without email B'),
    ('an@example.test', 'An'),
    ('binh@example.test', 'Binh');

SELECT id, email, display_name
FROM null_unique_lab.users_default
ORDER BY id;
```

Expected result:

| id | email | display_name |
|---:|---|---|
| 1 | `NULL` | Account without email A |
| 2 | `NULL` | Account without email B |
| 3 | an@example.test | An |
| 4 | binh@example.test | Binh |

Assuming a fresh table with identity starting at 1 as usual, **both rows with `email = NULL` succeed**, even though the column has a `UNIQUE` constraint.

If you try inserting an existing email:

```sql
-- Run separately in the lab to observe the error:
-- INSERT INTO null_unique_lab.users_default (email, display_name)
-- VALUES ('an@example.test', 'Another An');
```

PostgreSQL rejects it because the non-NULL email duplicates. Typical error:

```text
ERROR: duplicate key value violates unique constraint "uq_users_default_email"
SQLSTATE: 23505
```

### 3.1. What Does the Default Rule Mean?

Here `NULL` can represent **unknown or not yet provided email**. If 1,000 accounts have not provided an email yet, permitting 1,000 `NULL` values is usually the sensible choice.

`UNIQUE` still ensures **provided** emails never duplicate. Therefore, **do not blindly replace every nullable `UNIQUE` constraint with `NULLS NOT DISTINCT`**: for optional emails, doing so would allow only one account in the entire table to lack an email.

### 3.2. This Default Does Not Mean “UNIQUE Is Broken”

Many people write:

```sql
CREATE TABLE example_code (
    code TEXT UNIQUE
);
```

then notice multiple `code IS NULL` rows and think PostgreSQL is failing to enforce the constraint. In fact, PostgreSQL is enforcing it properly: **non-NULL** values must be unique, while `NULL` is by default treated as distinct from other `NULL`s **specifically under UNIQUE semantics**.

This is intentional standard behavior, not a race condition and not controlled by a global server toggle.

## 4. NULLS NOT DISTINCT: Treating NULL as a Duplicate in UNIQUE

Starting in PostgreSQL 15, change the semantics with:

```sql
CREATE TABLE null_unique_lab.users_strict (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT,
    display_name TEXT NOT NULL,
    CONSTRAINT uq_users_strict_email
        UNIQUE NULLS NOT DISTINCT (email)
);
```

Insert one row without an email:

```sql
INSERT INTO null_unique_lab.users_strict (email, display_name)
VALUES
    (NULL, 'Single account without email'),
    ('an@example.test', 'An'),
    ('binh@example.test', 'Binh');
```

However, inserting a second `NULL` violates the constraint:

```sql
-- Run separately in the lab to observe the error on PostgreSQL 15+:
-- INSERT INTO null_unique_lab.users_strict (email, display_name)
-- VALUES (NULL, 'Second account without email');
```

Because of `UNIQUE NULLS NOT DISTINCT (email)`, PostgreSQL treats both rows' `NULL` keys as **not distinct**, forbidding them from coexisting.

### 4.1. NULLS NOT DISTINCT Does Not Mean NOT NULL

These two definitions are **not equivalent**:

```sql
-- A: Forbids all NULLs.
CREATE TABLE null_unique_lab.sample_not_null (
    email TEXT NOT NULL UNIQUE
);

-- B: Allows one NULL, but forbids two NULLs.
CREATE TABLE null_unique_lab.sample_one_null (
    email TEXT UNIQUE NULLS NOT DISTINCT
);
```

Differences:

| Data to Store | `NOT NULL UNIQUE` | `UNIQUE NULLS NOT DISTINCT` |
|---|---|---|
| No NULL rows | Valid | Valid |
| One NULL row | **Invalid** | Valid |
| Two NULL rows | Invalid | **Invalid** |
| Two `'A'` rows | Invalid | Invalid |
| `'A'` and `'B'` | Valid | Valid |

If the requirement is **“must not be missing”**, use `NOT NULL`. If the requirement is **“may be missing, but only one row may lack a value within this key/scope”**, `NULLS NOT DISTINCT` may fit.

### 4.2. Explicit NULLS DISTINCT Syntax

PostgreSQL 15+ also allows declaring the default explicitly:

```sql
CREATE TABLE null_unique_lab.users_explicit_default (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT,
    CONSTRAINT uq_users_explicit_default_email
        UNIQUE NULLS DISTINCT (email)
);
```

`NULLS DISTINCT` is simply the **existing default behavior** of `UNIQUE`. When you do not need to emphasize `NULL` handling, `UNIQUE (email)` is sufficient and stays compatible with older PostgreSQL versions.

### 4.3. Effect Is Scoped to Each Constraint or Index

`NULLS NOT DISTINCT` is a property of a **specific `UNIQUE` constraint or index**. It **does not**:

- Make the `=` operator evaluate `NULL = NULL` as `true`.
- Change how other `UNIQUE` constraints in the database behave.
- Make a column `NOT NULL`.
- Change `CHECK`, foreign key, or `JOIN ... ON a = b` rules.

To compare two values including `NULL` in queries, you still must use an appropriate operator such as `IS NOT DISTINCT FROM`.

## 5. Composite Keys: Where Careful Thought Matters Most

In multi-tenant systems, business keys often consist of two or more columns, such as `(tenant_id, external_code)`. When one column allows `NULL`, default `UNIQUE` behavior is frequently misunderstood.

### 5.1. Default UNIQUE(tenant_id, external_code)

```sql
CREATE TABLE null_unique_lab.tenant_refs_default (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    external_code TEXT,
    description TEXT NOT NULL,
    CONSTRAINT uq_tenant_refs_default
        UNIQUE (tenant_id, external_code)
);

INSERT INTO null_unique_lab.tenant_refs_default
    (tenant_id, external_code, description)
VALUES
    (10, NULL, 'Org 10: unknown code, entry 1'),
    (10, NULL, 'Org 10: unknown code, entry 2'),
    (10, 'A-01', 'Org 10: code A-01'),
    (20, NULL, 'Org 20: unknown code'),
    (20, 'A-01', 'Org 20: code A-01');
```

All these rows are valid. Specifically:

- Two `(10, NULL)` rows are accepted because `NULL` is distinct by default in `UNIQUE`.
- `(10, 'A-01')` and `(20, 'A-01')` do not conflict because `tenant_id` differs.
- Inserting `(10, 'A-01')` again would be rejected because **both non-NULL key components match**.

### 5.2. UNIQUE NULLS NOT DISTINCT on a Composite Key

```sql
CREATE TABLE null_unique_lab.tenant_refs_strict (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    external_code TEXT,
    description TEXT NOT NULL,
    CONSTRAINT uq_tenant_refs_strict
        UNIQUE NULLS NOT DISTINCT (tenant_id, external_code)
);

INSERT INTO null_unique_lab.tenant_refs_strict
    (tenant_id, external_code, description)
VALUES
    (10, NULL, 'Org 10 record with unknown code'),
    (10, 'A-01', 'Org 10 record with code A-01'),
    (20, NULL, 'Org 20 record with unknown code'),
    (20, 'A-01', 'Org 20 record with code A-01');
```

Now inserting `(10, NULL)` a second time fails:

```sql
-- Intentionally fails due to duplicate key combination in PostgreSQL 15+:
-- INSERT INTO null_unique_lab.tenant_refs_strict
--     (tenant_id, external_code, description)
-- VALUES (10, NULL, 'Another record missing a code');
```

PostgreSQL rejects it because `(10, NULL)` and `(10, NULL)` are **not distinct** under the constraint definition.

However, `(20, NULL)` can still coexist with `(10, NULL)` because `tenant_id` differs. Thus the behavior is **at most one `external_code IS NULL` row per tenant**, not one `NULL` row in the entire database.

### 5.3. Truth Table for Composite Key Uniqueness

Suppose the table already has the row on the left; can the row on the right be inserted?

| Existing Key | New Key | Default `UNIQUE` | `UNIQUE NULLS NOT DISTINCT` |
|---|---|---|---|
| `(10, 'A')` | `(10, 'A')` | No | No |
| `(10, 'A')` | `(10, 'B')` | Yes | Yes |
| `(10, 'A')` | `(20, 'A')` | Yes | Yes |
| `(10, NULL)` | `(10, NULL)` | **Yes** | **No** |
| `(10, NULL)` | `(20, NULL)` | Yes | Yes |
| `(10, NULL)` | `(10, 'A')` | Yes | Yes |

This illustrates the meaning of “`NULLS NOT DISTINCT`”: two rows are considered duplicates **if every corresponding component of the key tuple is non-distinct**, where two `NULL`s in the same position are treated as equivalent for uniqueness checking.

### 5.4. When Both Columns Are Nullable

Consider a composite key `(group_id, slot_code)` where **both columns can be NULL**:

```sql
CREATE TABLE null_unique_lab.optional_pairs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_id INTEGER,
    slot_code TEXT,
    CONSTRAINT uq_optional_pairs
        UNIQUE NULLS NOT DISTINCT (group_id, slot_code)
);

INSERT INTO null_unique_lab.optional_pairs (group_id, slot_code)
VALUES
    (NULL, NULL),
    (NULL, 'A'),
    (NULL, 'B'),
    (10, NULL),
    (20, NULL),
    (10, 'A');
```

All six rows are distinct as key tuples. Inserting another row matching any of those combinations—including `(NULL, NULL)`, `(NULL, 'A')`, or `(10, NULL)`—will be rejected.

**Do not interpret** `NULLS NOT DISTINCT` as “any row with a NULL collides with every other row containing a NULL”. PostgreSQL still compares **position by position**; non-NULL components must still match.

### 5.5. What If You Really Want to Forbid Missing Codes?

Do not use `NULLS NOT DISTINCT` to express a rule like “every row must have an `external_code`”. Instead:

```sql
CREATE TABLE null_unique_lab.tenant_refs_required (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    external_code TEXT NOT NULL,
    CONSTRAINT uq_tenant_refs_required
        UNIQUE (tenant_id, external_code)
);
```

`NOT NULL` expresses requirement; `UNIQUE` expresses non-duplication. Separating the two keeps the schema clear and ensures error messages match the true failure.

## 6. Choosing NULLS DISTINCT vs. NULLS NOT DISTINCT by Business Rules

No single setting fits every column. Ask **what `NULL` represents** and **how many rows without a value are permitted within the same scope**.

| Scenario | Usually Appropriate Choice | Explanation |
|---|---|---|
| Email is optional; many customers have no email yet | `UNIQUE (email)` | Provided emails must be unique; many accounts lacking an email is normal |
| Order code is required and unique | `NOT NULL UNIQUE` | Missing codes are forbidden |
| Each tenant has at most one “default slot” represented by `NULL` | `UNIQUE NULLS NOT DISTINCT (tenant_id, slot_code)` | Two `(tenant, NULL)` rows will conflict |
| Each tenant may have many records awaiting an external code | `UNIQUE (tenant_id, external_code)` | Multiple unknown codes can coexist |
| Multi-part optional key where identical tuples—including NULL positions—must not repeat | `UNIQUE NULLS NOT DISTINCT (col1, col2, ...)` | Identical tuples with matching values and NULLs are treated as duplicates |
| Uniqueness applies only while a record is “active” | **Partial unique index** with `WHERE` | Filters by business state; can combine with `NULLS NOT DISTINCT` if needed |

### 6.1. Do Not Abuse NULL as a “Default Record”

Some systems use `NULL` to mean “default value” or “applies globally”. That can work when documented explicitly, but it is often ambiguous because `NULL` traditionally means “unknown/absent”.

If business logic must distinguish “code not yet known” from “default code”, consider a status column, a separate record, or an explicit identifier. `NULLS NOT DISTINCT` solves **uniqueness**, not **ambiguity in what NULL means**.

## 7. UNIQUE Constraints and UNIQUE Indexes

PostgreSQL normally enforces a `UNIQUE` constraint via an underlying **unique index**. Administrators can also create a unique index directly.

### 7.1. Creating UNIQUE NULLS NOT DISTINCT via a Constraint

Example in table definition:

```sql
CREATE TABLE null_unique_lab.login_aliases (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    alias TEXT,
    CONSTRAINT uq_login_aliases_tenant_alias
        UNIQUE NULLS NOT DISTINCT (tenant_id, alias)
);
```

The constraint has an explicit name, appears in `unique_violation` error details, and can be referenced via `ON CONFLICT ON CONSTRAINT` where appropriate.

### 7.2. Creating a Unique Index Directly

On PostgreSQL 15+:

```sql
CREATE TABLE null_unique_lab.aliases_by_index (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    alias TEXT
);

CREATE UNIQUE INDEX uq_aliases_by_index
ON null_unique_lab.aliases_by_index (tenant_id, alias)
NULLS NOT DISTINCT;
```

This index still enforces uniqueness even without a separate `UNIQUE` constraint declared in `pg_constraint`.

### 7.3. Syntax Comparison

| Purpose | Basic Syntax on PostgreSQL 15+ |
|---|---|
| Default nullable UNIQUE | `UNIQUE (email)` |
| Explicit default | `UNIQUE NULLS DISTINCT (email)` |
| Treat NULL as duplicate | `UNIQUE NULLS NOT DISTINCT (email)` |
| Default unique index | `CREATE UNIQUE INDEX ... ON table (email);` |
| Unique index treating NULL as duplicate | `CREATE UNIQUE INDEX ... ON table (email) NULLS NOT DISTINCT;` |

Notice where `NULLS NOT DISTINCT` sits in **table constraints** vs. **CREATE INDEX**: in a constraint it comes **before the column list**, whereas in `CREATE UNIQUE INDEX` it comes **after the column list**. Mixing up the placement is a common syntax error when converting between the two forms.

### 7.4. Not Every Unique Index Is a UNIQUE Constraint

A unique index can contain expressions or a `WHERE` predicate. In PostgreSQL, such an index still enforces uniqueness over matching rows, but is not completely equivalent to a standard `UNIQUE` table constraint.

Example:

```sql
CREATE TABLE null_unique_lab.active_emails (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT,
    deleted_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX uq_active_emails_normalized
ON null_unique_lab.active_emails (lower(email))
WHERE deleted_at IS NULL AND email IS NOT NULL;
```

Rule: no two **active** (`deleted_at IS NULL`) rows with a **non-NULL email** may share the same `lower(email)` under the index's comparison semantics.

This is a **partial expression unique index**, not an ordinary `UNIQUE (email)` constraint. Soft-deleted rows or rows without an email are not restricted in the same way.

### 7.5. Partial Unique Index Combined with NULLS NOT DISTINCT

If a table only needs uniqueness among **active rows**, PostgreSQL 15+ allows:

```sql
CREATE TABLE null_unique_lab.active_slots (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    slot_code TEXT,
    archived_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX uq_active_slots
ON null_unique_lab.active_slots (tenant_id, slot_code)
NULLS NOT DISTINCT
WHERE archived_at IS NULL;
```

Meaning:

- Two active `(tenant_id=10, slot_code=NULL)` rows cannot coexist.
- Once a row has `archived_at IS NOT NULL`, it drops out of this partial index.
- Rows belonging to different tenants do not conflict.

Note: a partial index requires the `WHERE` predicate to reflect actual lifecycle state; it does not delete old records or replace application lifecycle rules.

## 8. Composite Keys with NULL and Lookup Queries

To look up a key tuple that may contain `NULL`, write:

```sql
SELECT *
FROM null_unique_lab.tenant_refs_strict
WHERE tenant_id = 10
  AND external_code IS NULL;
```

Do not write:

```sql
-- Logically wrong when searching for NULL:
-- WHERE external_code = NULL
```

### 8.1. When an Input Parameter Might Be NULL

If a query is prepared and the reference code may be `NULL`, `IS NOT DISTINCT FROM` compares with **two NULLs matching** semantics:

```sql
PREPARE find_tenant_ref(INTEGER, TEXT) AS
SELECT id, tenant_id, external_code, description
FROM null_unique_lab.tenant_refs_strict
WHERE tenant_id = $1
  AND external_code IS NOT DISTINCT FROM $2;

EXECUTE find_tenant_ref(10, NULL);
EXECUTE find_tenant_ref(10, 'A-01');

DEALLOCATE find_tenant_ref;
```

This handles both cases: whether the passed code is a real string or `NULL`. It **does not alter** the uniqueness mechanism; it simply lets `WHERE` apply the same “not distinct” comparison when searching.

### 8.2. Index Usage Still Depends on the Query Plan

Logical equivalence does not guarantee that every query using `IS NOT DISTINCT FROM` receives the exact same execution plan as `=` or `IS NULL`. PostgreSQL's optimizer evaluates statistics, operators, index types, row counts, and parameters. For critical queries, inspect `EXPLAIN (ANALYZE, BUFFERS)` on representative data rather than assuming.

## 9. INSERT ... ON CONFLICT When Keys Contain NULL

A common real-world pattern is **upsert**: if a matching record exists, update it; otherwise, insert it.

### 9.1. With Default UNIQUE: NULL Does Not Conflict

On `tenant_refs_default`:

```sql
INSERT INTO null_unique_lab.tenant_refs_default
    (tenant_id, external_code, description)
VALUES (10, NULL, 'Next write with unknown code')
ON CONFLICT ON CONSTRAINT uq_tenant_refs_default
DO UPDATE
SET description = EXCLUDED.description
RETURNING id, tenant_id, external_code, description;
```

Because `NULL`s are **treated as distinct** in the default `UNIQUE` constraint, the new `(10, NULL)` row **does not conflict** with existing `(10, NULL)` rows. Consequently, PostgreSQL **inserts another new row** rather than taking the `DO UPDATE` branch.

`ON CONFLICT` does not invent its own definition of duplication. It uses the **uniqueness rules of the arbiter constraint or index**.

### 9.2. With NULLS NOT DISTINCT: NULL Triggers Conflict

On `tenant_refs_strict`:

```sql
INSERT INTO null_unique_lab.tenant_refs_strict
    (tenant_id, external_code, description)
VALUES (10, NULL, 'Updated tenant 10 record missing code')
ON CONFLICT ON CONSTRAINT uq_tenant_refs_strict
DO UPDATE
SET description = EXCLUDED.description
RETURNING id, tenant_id, external_code, description;
```

Since `(10, NULL)` already exists in the table, the new row **conflicts** with it under `NULLS NOT DISTINCT`, so the `DO UPDATE` branch executes. If you change `tenant_id` to 30 where no matching key exists, it inserts a new row.

### 9.3. ON CONFLICT DO NOTHING Also Differs

```sql
INSERT INTO null_unique_lab.tenant_refs_strict
    (tenant_id, external_code, description)
VALUES (10, NULL, 'Skipped because it already exists')
ON CONFLICT ON CONSTRAINT uq_tenant_refs_strict
DO NOTHING;
```

This does not insert a second `(10, NULL)` row. By contrast, with a default `UNIQUE` constraint, the same tuple containing `NULL` would be inserted as an additional row.

**Do not equate** `DO NOTHING` with “skip if all columns have identical values”. It only reacts to conflicts detected by the specified arbiter.

### 9.4. Be Careful When Multiple Unique Indexes Exist

When writing `ON CONFLICT (tenant_id, external_code)`, PostgreSQL uses *index inference* to pick a matching unique index. If a table has multiple unique indexes on those columns with different purposes or predicates, know exactly which arbiter is inferred.

With a named, non-deferrable unique **constraint**, `ON CONFLICT ON CONSTRAINT constraint_name` makes the conflict target explicit. A standalone **partial unique index** has no constraint name for `ON CONSTRAINT`; to infer a partial index, write the matching conflict target columns and `WHERE` predicate.

### 9.5. DEFERRABLE Constraints Are a Special Case

`UNIQUE` can be declared `DEFERRABLE` to postpone uniqueness checks until appropriate points in a transaction. However, **`ON CONFLICT DO UPDATE` does not support deferrable unique constraints as arbiters**. Do not mark constraints `DEFERRABLE` by default just for bulk-update convenience.

Syntax reference for a separate transaction:

```sql
-- Feature illustration only; do not use this table for upsert examples:
CREATE TABLE null_unique_lab.deferred_demo (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code TEXT,
    CONSTRAINT uq_deferred_demo
        UNIQUE NULLS NOT DISTINCT (code)
        DEFERRABLE INITIALLY DEFERRED
);
```

When a constraint is deferred, duplicate errors may surface at `COMMIT` rather than immediately on the write statement. That changes how applications handle errors, without removing the constraint.

## 10. Adding NULLS NOT DISTINCT to a Table with Existing Data

Adding a new constraint to an existing table is more than changing a keyword. If the table already holds **key combinations considered duplicates under the new semantics**, PostgreSQL will fail to create the unique constraint or index.

### 10.1. Inspect Existing Data First

On `tenant_refs_default` created in Section 5:

```sql
SELECT
    tenant_id,
    external_code,
    COUNT(*) AS so_hang
FROM null_unique_lab.tenant_refs_default
GROUP BY tenant_id, external_code
HAVING COUNT(*) > 1
ORDER BY tenant_id, external_code NULLS FIRST;
```

The output will include at least the `(10, NULL)` group with multiple rows. `GROUP BY` is ideal for finding duplicate combinations **including `NULL`s**.

### 10.2. Why Does GROUP BY Catch Duplicate NULLs While Default UNIQUE Permits Them?

**Grouping** rules and **unique constraint** rules are not the same. In SQL/PostgreSQL, `NULL`s are grouped into **one group** by `GROUP BY` or `SELECT DISTINCT`, whereas default `UNIQUE` treats `NULL`s as distinct when checking keys.

There is no contradiction: different operators apply **different semantic rules** in their respective contexts.

Do not use:

```sql
SELECT COUNT(DISTINCT external_code)
FROM null_unique_lab.tenant_refs_default;
```

to detect duplicate combinations containing `NULL`, because `COUNT(DISTINCT external_code)` ignores `NULL` values.

### 10.3. Counting Duplicate NULLs Within a Tenant

If `tenant_id` is always `NOT NULL` and only `external_code` is nullable, you can run a targeted query:

```sql
SELECT
    tenant_id,
    COUNT(*) AS so_ma_null
FROM null_unique_lab.tenant_refs_default
WHERE external_code IS NULL
GROUP BY tenant_id
HAVING COUNT(*) > 1
ORDER BY tenant_id;
```

If default `UNIQUE` already prevented duplicate non-NULL codes, **NULL-code groups** are typically the main conflict risk before migrating to `NULLS NOT DISTINCT`. For keys with multiple nullable columns, `GROUP BY` across **all key columns** to catch every duplicate under the new semantics.

### 10.4. List Rows for Review Instead of Auto-Deleting

If you need to inspect each row in a duplicate group:

```sql
WITH danh_dau AS (
    SELECT
        id,
        tenant_id,
        external_code,
        description,
        COUNT(*) OVER (
            PARTITION BY tenant_id, external_code
        ) AS so_hang_cung_khoa,
        ROW_NUMBER() OVER (
            PARTITION BY tenant_id, external_code
            ORDER BY id
        ) AS thu_tu_trong_nhom
    FROM null_unique_lab.tenant_refs_default
)
SELECT *
FROM danh_dau
WHERE so_hang_cung_khoa > 1
ORDER BY tenant_id, external_code NULLS FIRST, id;
```

`ROW_NUMBER` helps operators **inspect** records in each group, not decide automatically that row 2 should be deleted. In real businesses, two `external_code IS NULL` records may represent two valid entities; reducing them to one requires a merge, code-assignment, or data-modeling rule, not arbitrary deletion.

## 11. Migration Workflow from Default UNIQUE to NULLS NOT DISTINCT

Suppose a large table currently uses `UNIQUE (tenant_id, external_code)`, and the organization confirms a new requirement: **each tenant may have at most one row without a code**.

### 11.1. Step 1: Confirm True Scope and Requirements

Answer:

- Do you truly want at most one `NULL` **per tenant**, or should `NULL` be forbidden entirely?
- Are there `deleted_at` or `archived_at` columns indicating some rows are outside uniqueness scope?
- Are any transactions or jobs actively creating new `NULL` rows?
- Does application code rely on `ON CONFLICT` referencing the old constraint name?
- Is the table partitioned, and does the unique key include the partition key?
- Does existing data already contain duplicates under the new rule?

Do not alter the constraint before confirming semantics: a syntactically valid change can break active write paths that legitimately rely on multiple `NULL`s.

### 11.2. Step 2: Find Conflicting Data

```sql
SELECT tenant_id, external_code, COUNT(*)
FROM null_unique_lab.tenant_refs_default
GROUP BY tenant_id, external_code
HAVING COUNT(*) > 1;
```

An empty result **at read time** does not guarantee a safe migration if another process inserts duplicates concurrently while you check. Coordinate cutover timing, write locking/coordination, or concurrent index builds to prevent race conditions.

### 11.3. Step 3: Resolve Duplicates per Business Rules

Options include:

- Populate real `external_code` values on `NULL` rows if an authoritative source can supply them.
- Merge duplicate records that represent the same entity according to business rules.
- Mark obsolete rows inactive and apply a **partial unique index** over active rows only.
- Keep `NULLS DISTINCT` if the original requirement is still valid—no migration needed.

Never blindly `DELETE` everything except `MIN(id)`: foreign keys, transaction history, and data integrity can be broken.

### 11.4. Step 4: Create the New Constraint on Small Tables or During a Maintenance Window

Once data is clean and maintenance is scheduled, a straightforward option is:

```sql
-- PostgreSQL 15+ syntax example; run only on a verified table.
ALTER TABLE null_unique_lab.tenant_refs_default
ADD CONSTRAINT uq_tenant_refs_default_strict
UNIQUE NULLS NOT DISTINCT (tenant_id, external_code);
```

Once the new constraint succeeds, duplicates under the new semantics are blocked. If the old `UNIQUE` constraint on the same columns still exists, you will temporarily have **two indexes protecting the same column set**; plan to drop the old constraint once safe to avoid redundant index overhead.

Example syntax for dropping the old constraint—**do not run before confirming application references are updated**:

```sql
-- After verifying dependencies and ON CONFLICT targets:
-- ALTER TABLE null_unique_lab.tenant_refs_default
-- DROP CONSTRAINT uq_tenant_refs_default;
```

`ALTER TABLE ... ADD CONSTRAINT UNIQUE` scans and validates data and acquires locks affecting reads/writes. On large tables, assess real lock and resource impact.

### 11.5. Step 5: On Large Tables, Consider CREATE UNIQUE INDEX CONCURRENTLY

PostgreSQL supports building indexes concurrently to reduce certain blocking during index creation:

```sql
-- Run only after data is cleaned and a maintenance plan is in place.
CREATE UNIQUE INDEX CONCURRENTLY
    idx_tenant_refs_default_strict
ON null_unique_lab.tenant_refs_default
    (tenant_id, external_code)
NULLS NOT DISTINCT;
```

**Important operational limitations:**

- `CREATE INDEX CONCURRENTLY` **cannot run inside a transaction block**.
- It takes longer and consumes significant I/O.
- If duplicates are encountered or the build fails, PostgreSQL may leave an **`INVALID` index** that must be inspected and cleaned up properly.
- Concurrent writers must still be coordinated so invalid new data is not written; concurrent index building does not bypass consistency requirements.
- On real systems, verify PostgreSQL version, topology, and privileges before choosing this route.

Once the unique index builds cleanly and meets eligibility rules (valid, non-partial, non-expression, supported types), PostgreSQL allows **attaching the index as a table constraint**:

```sql
-- Example only for a completed, eligible index:
ALTER TABLE null_unique_lab.tenant_refs_default
ADD CONSTRAINT uq_tenant_refs_default_strict
UNIQUE USING INDEX idx_tenant_refs_default_strict;
```

With `USING INDEX`, PostgreSQL reuses the existing index instead of rebuilding a new one, though attaching the constraint still requires appropriate privileges and locks. Do not attempt this with a **partial index** or **expression index**, as those cannot become standard unique constraints this way.

**Note:** Direct `ADD CONSTRAINT ... UNIQUE NULLS NOT DISTINCT` and `CREATE INDEX ...; ADD CONSTRAINT ... USING INDEX` are **two alternative paths**—do not execute both on the same table with the same constraint name.

### 11.6. Step 6: Verify the Application After Cutover

After the new constraint is live:

1. Test inserting a new, unseen key combination.
2. Test inserting an existing combination containing `NULL` and confirm error `23505`.
3. Test upserts with the updated `ON CONFLICT ON CONSTRAINT` if the app uses it.
4. Confirm no code still depends on a dropped old constraint name.
5. Check for redundant indexes, query latency, and error logs.
6. Document the new business rule in schema/API documentation.

**A successful `ALTER` statement alone is not enough** if the application still has write paths expecting multiple `NULL`s to succeed.

## 12. Inspecting Existing Constraints and Indexes

To avoid accidental changes, inspect what properties existing constraints currently have.

### 12.1. Viewing Constraint Definitions from the Catalog

```sql
SELECT
    conname AS constraint_name,
    contype,
    condeferrable,
    condeferred,
    pg_get_constraintdef(oid) AS constraint_definition
FROM pg_constraint
WHERE conrelid = 'null_unique_lab.tenant_refs_strict'::regclass
  AND contype IN ('u', 'p')
ORDER BY conname;
```

In `pg_constraint`:

- `contype = 'u'` indicates a unique constraint.
- `contype = 'p'` indicates a primary key.
- `condeferrable` and `condeferred` indicate deferrability properties.
- `pg_get_constraintdef` returns the SQL definition of the constraint.

For `NULLS NOT DISTINCT` constraints on PostgreSQL 15+, the returned definition displays that attribute for easy identification.

### 12.2. Checking indnullsnotdistinct in pg_index

PostgreSQL 15+ includes `pg_index.indnullsnotdistinct`:

```sql
SELECT
    i.indexrelid::regclass AS index_name,
    i.indisunique AS is_unique,
    i.indnullsnotdistinct AS nulls_not_distinct,
    i.indisvalid AS is_valid,
    pg_get_indexdef(i.indexrelid) AS index_definition
FROM pg_index AS i
WHERE i.indrelid = 'null_unique_lab.tenant_refs_strict'::regclass
ORDER BY index_name;
```

When `indnullsnotdistinct = true` on a unique index, PostgreSQL treats `NULL` as non-distinct. On a primary key, columns are already `NOT NULL`, so `NULL` distinctness has no practical effect.

**Version caution:** `indnullsnotdistinct` does not exist on PostgreSQL 14 or earlier. Do not copy this catalog query verbatim onto older versions without adjustment.

### 12.3. Viewing Indexes via pg_indexes

A query usable across versions:

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'null_unique_lab'
ORDER BY tablename, indexname;
```

`indexdef` displays the index syntax created, such as `UNIQUE`, `NULLS NOT DISTINCT`, or a partial index's `WHERE` clause. However, it does not replace checking dependencies, privileges, and constraints in the catalog before schema changes.

## 13. Pre-PostgreSQL 15 Alternatives

On PostgreSQL 14 or older, `UNIQUE NULLS NOT DISTINCT` syntax does not exist. Equivalent rules for specific cases can be built by **combining conditional unique indexes**, depending on business scope.

### 13.1. One Nullable Column with NOT NULL tenant_id

Requirement: each `tenant_id` may have at most one `external_code IS NULL` row, while non-NULL `external_code` values must be unique per tenant.

```sql
CREATE TABLE null_unique_lab.legacy_tenant_refs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    external_code TEXT,
    description TEXT NOT NULL,
    CONSTRAINT uq_legacy_tenant_code
        UNIQUE (tenant_id, external_code)
);

-- At most one external_code IS NULL row per tenant_id.
CREATE UNIQUE INDEX uq_legacy_one_null_per_tenant
ON null_unique_lab.legacy_tenant_refs (tenant_id)
WHERE external_code IS NULL;
```

Explanation:

- `UNIQUE (tenant_id, external_code)` prevents duplicate non-NULL codes within the same tenant.
- The partial unique index on `tenant_id` **covers only rows where `external_code IS NULL`**, preventing two `NULL` rows in the same tenant.
- `tenant_id NOT NULL` is an essential assumption: if `tenant_id` were also nullable, the rule for those keys would need a separate design.

This is a **workaround for a specific pattern**, not a general syntax that automatically converts arbitrary multi-nullable-column keys to PostgreSQL 15 semantics.

### 13.2. When Only Non-NULL Values Must Be Unique

For a single nullable column:

```sql
CREATE UNIQUE INDEX uq_optional_external_code_nonnull
ON null_unique_lab.legacy_tenant_refs (external_code)
WHERE external_code IS NOT NULL;
```

**Semantic warning:** this example index enforces uniqueness of `external_code` **across the entire table**, not per tenant. If uniqueness should be **within each tenant**, use `(tenant_id, external_code)`:

```sql
CREATE UNIQUE INDEX uq_legacy_nonnull_by_tenant
ON null_unique_lab.legacy_tenant_refs (tenant_id, external_code)
WHERE external_code IS NOT NULL;
```

With composite keys, both the columns and the `WHERE` predicate define the scope. On a schema that already has default `UNIQUE (tenant_id, external_code)`, this partial index is normally **unnecessary** for guarding non-NULL duplicates because the existing constraint already does so; use it only as an alternative design or for specific index/performance needs.

### 13.3. Using COALESCE with a Sentinel Value Carries Risk

Before PostgreSQL 15, people sometimes used expression indexes:

```sql
-- Technique illustration; do not copy blindly:
-- CREATE UNIQUE INDEX uq_expr
-- ON some_table (tenant_id, COALESCE(external_code, '<MISSING>'));
```

This maps `NULL` to a sentinel value for comparison, but **can collide with real data** if a legitimate record ever uses the literal string `'<MISSING>'`. In that case, the index conflates two semantically distinct situations into one key.

If you use this technique, you must **guarantee the sentinel cannot appear in valid data** via constraints/business rules and check types, collations, privileges, and performance. On PostgreSQL 15+, `NULLS NOT DISTINCT` is much more direct and clearer.

### 13.4. Is a Pre-INSERT Check Trigger Enough?

A checking trigger:

```sql
-- Prone to errors without concurrency control:
-- IF EXISTS (
--     SELECT 1 FROM table_name
--     WHERE tenant_id = NEW.tenant_id
--       AND external_code IS NOT DISTINCT FROM NEW.external_code
-- ) THEN ...
```

suffers from **race conditions**: two transactions can both check “no row exists” and both insert before either commits. A unique constraint/index is the atomic mechanism PostgreSQL uses to resolve this contention. Do not replace a uniqueness requirement with `SELECT EXISTS` in application code or a naive trigger lacking proper locking/concurrency design.

## 14. Error 23505 and Concurrency Handling

PostgreSQL enforces uniqueness at the storage/index layer on writes. If two transactions simultaneously attempt to insert a conflicting key combination, one transaction may wait for the other to resolve and then fail with **SQLSTATE 23505**.

This matters because the pattern below is **unsafe**:

```text
App A: SELECT checks key does not exist
App B: SELECT checks key does not exist
App A: INSERT key
App B: INSERT key
```

Application-level checks alone cannot prevent concurrent duplicate writes. Use a **semantically accurate constraint/index**, combined with `ON CONFLICT` or `23505` handling suited to the operation.

### 14.1. Distinguishing unique_violation from Other Errors

In PostgreSQL SQLSTATE codes:

| Code | Name | Meaning |
|---|---|---|
| `23505` | `unique_violation` | Unique constraint/index violation |
| `23502` | `not_null_violation` | `NOT NULL` violation |
| `23514` | `check_violation` | `CHECK` violation |
| `23503` | `foreign_key_violation` | Foreign key violation |

Do not catch all database exceptions and return the same message “email already exists”. For instance, `23502` means a required value is missing, whereas `23505` means a key combination is already in use.

### 14.2. JDBC Error Handling Example

In Java, match on `SQLState` rather than relying solely on message strings that can vary by locale or version:

```java
import java.sql.SQLException;

public class UniqueErrorHandler {
    public static void handleWriteError(SQLException e)
            throws SQLException {
        if ("23505".equals(e.getSQLState())) {
            // Translate into an appropriate business error
            // or return HTTP 409 per the API contract.
            throw new IllegalStateException(
                "Business key already exists",
                e
            );
        }
        throw e;
    }
}
```

In schemas with multiple unique constraints, `23505` only tells you **a uniqueness violation occurred**, not specifically which column failed. If you need constraint-specific messages, extract the constraint name from structured driver error metadata where available rather than parsing prose messages.

### 14.3. When Does ON CONFLICT Fit?

`ON CONFLICT DO UPDATE` works well when business rules genuinely mean “overwrite/update the record matching this key”. `ON CONFLICT DO NOTHING` fits idempotent retries that should ignore duplicate inserts. When two requests represent distinct entities colliding on a code, the right response is usually **returning an error** so the caller corrects the input.

Choosing `NULLS NOT DISTINCT` and choosing conflict-handling behavior are related decisions, but they are **not the same decision**.

## 15. UNIQUE, CHECK, and NULL: Three-Valued Logic Rules

`UNIQUE` is not the only constraint with `NULL` subtleties. `CHECK` also warrants attention: it accepts expressions returning `true` **or `unknown/NULL`**, rejecting a row only when the expression evaluates to `false`.

Example:

```sql
CREATE TABLE null_unique_lab.optional_codes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code TEXT,
    CONSTRAINT chk_code_nonempty CHECK (code <> ''),
    CONSTRAINT uq_code UNIQUE (code)
);
```

`CHECK (code <> '')` **does not forbid `code = NULL`**, because `NULL <> ''` evaluates to unknown. Default `UNIQUE (code)` also permits **multiple `NULL`s**.

If `code` is required:

```sql
CREATE TABLE null_unique_lab.required_codes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code TEXT NOT NULL,
    CONSTRAINT chk_code_nonempty CHECK (code <> ''),
    CONSTRAINT uq_required_code UNIQUE (code)
);
```

If `code` may be missing, but only for one record:

```sql
CREATE TABLE null_unique_lab.one_optional_code (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code TEXT,
    CONSTRAINT chk_code_nonempty CHECK (code <> ''),
    CONSTRAINT uq_one_optional_code
        UNIQUE NULLS NOT DISTINCT (code)
);
```

Do not try to express three separate rules—**required**, **valid format**, and **unique**—with a single constraint. Separating `NOT NULL`, `CHECK`, and `UNIQUE` makes the table reflect business rules clearly.

## 16. NULL, Empty Strings, and “Unknown” Values

These inputs are not equivalent:

```sql
SELECT
    NULL::TEXT IS NULL AS la_null,
    ''::TEXT IS NULL AS empty_co_phai_null,
    ''::TEXT = ''::TEXT AS hai_chuoi_rong_bang_nhau;
```

The results are `true`, `false`, `true`.

In a unique constraint, two empty strings `''` **count as duplicates** because they are known, equal values. Therefore:

- `UNIQUE (email)` can hold many `NULL`s.
- It can hold at most **one `''`** under standard comparison rules.
- `UNIQUE NULLS NOT DISTINCT (email)` can hold at most one `NULL` **and** at most one `''`, because those are **two different keys**.

If an application treats “empty string means not provided”, normalize input **explicitly**; never assume PostgreSQL automatically turns `''` into `NULL`.

### 16.1. Normalizing Emails and Identifiers

Two strings like:

```text
Alice@Example.Test
alice@example.test
```

may need to be treated as the same email under login rules; however, `UNIQUE (email)` on `TEXT` with standard collation does not automatically enforce case-insensitivity.

You may need application-side normalization or an expression index on `lower(email)`. Still, email normalization has protocol, Unicode, and provider nuances; do not blindly apply `lower()` if strict rules are needed.

**`NULLS NOT DISTINCT` only controls how `NULL`s are compared in a unique key**—it does not solve case-insensitive uniqueness, diacritics, whitespace, or Unicode normalization.

## 17. UNIQUE and Partitioned Tables

When a table uses **declarative partitioning**, `PRIMARY KEY` and `UNIQUE` constraints on the **partitioned parent table** have specific rules: typically, the partition key columns must be included in the unique/primary key per PostgreSQL's requirements.

Concept example:

```sql
CREATE TABLE null_unique_lab.orders_partitioned (
    tenant_id INTEGER NOT NULL,
    created_on DATE NOT NULL,
    external_ref TEXT,
    payload TEXT
) PARTITION BY RANGE (created_on);
```

A unique constraint on the partitioned parent with only `(tenant_id, external_ref)` can be **invalid** because it omits the partition key `created_on`. When uniqueness is needed on a partitioned table, include the partition key appropriately and check your PostgreSQL version and partition strategy requirements.

For instance, a key could include it:

```sql
-- Illustrates a key including the partition key; applies only
-- when the business rule is uniqueness within each day:
ALTER TABLE null_unique_lab.orders_partitioned
ADD CONSTRAINT uq_orders_partitioned
UNIQUE NULLS NOT DISTINCT (created_on, tenant_id, external_ref);
```

This states that **within the same day**, each tenant has at most one `external_ref` tuple (including `NULL`). It **does not guarantee** that the same `external_ref` is unique across **all days**. If business rules require global uniqueness across partition boundaries, choose another design rather than assuming a partitioned constraint can enforce it automatically.

## 18. Performance: Does NULLS NOT DISTINCT Make Indexes Faster?

`UNIQUE NULLS NOT DISTINCT` is first and foremost a **data integrity constraint**, not a speed-optimization switch.

### 18.1. Cost of Maintaining Uniqueness

Every `INSERT`/`UPDATE` touching indexed columns must be checked against the uniqueness rule. Under large datasets and high concurrency, account for:

- Index storage size and I/O.
- Key-check latency, including waiting on concurrent transactions under contention.
- WAL write overhead for table/index updates.
- Overhead of multiple overlapping indexes.
- Index build or constraint validation duration during migrations.

Choose `NULLS NOT DISTINCT` because it matches business semantics, not in pursuit of unmeasured performance gains.

### 18.2. Indexes Containing NULLs Are Still Maintained by PostgreSQL

Do not interpret “default UNIQUE ignores duplicate NULLs” as meaning the index **omits entries for NULL**. A standard unique B-tree index still stores/indexes `NULL` entries; the difference is **how duplicate checks decide to reject new rows**.

If you want to exclude a subset of rows from the index, consider a **partial index `WHERE ...`** and understand its scope. Never use `NULLS NOT DISTINCT` as a substitute for a partial-index predicate.

### 18.3. Checking EXPLAIN When Needed

```sql
EXPLAIN
SELECT id, tenant_id, external_code, description
FROM null_unique_lab.tenant_refs_strict
WHERE tenant_id = 10
  AND external_code IS NULL;
```

On a small lab table, PostgreSQL may pick a sequential scan despite having a unique index, because scanning a few rows is cheaper than index traversal. That plan does not mean the index is broken.

On real systems, run `EXPLAIN (ANALYZE, BUFFERS)` on representative read queries, considering query cost and table volume. Defining uniqueness **does not guarantee** every query will automatically use an index scan.

## 19. Cleaning Up Practice Data

When finished, drop the demo tables only if you are certain you are in your practice database/schema and do not need the data:

```sql
-- Drop statements are optional; run individually after confirming.
-- DROP TABLE IF EXISTS null_unique_lab.orders_partitioned;
-- DROP TABLE IF EXISTS null_unique_lab.deferred_demo;
-- DROP TABLE IF EXISTS null_unique_lab.active_slots;
-- DROP TABLE IF EXISTS null_unique_lab.active_emails;
-- DROP TABLE IF EXISTS null_unique_lab.aliases_by_index;
-- DROP TABLE IF EXISTS null_unique_lab.login_aliases;
-- DROP TABLE IF EXISTS null_unique_lab.legacy_tenant_refs;
-- DROP TABLE IF EXISTS null_unique_lab.optional_codes;
-- DROP TABLE IF EXISTS null_unique_lab.required_codes;
-- DROP TABLE IF EXISTS null_unique_lab.one_optional_code;
-- DROP TABLE IF EXISTS null_unique_lab.sample_not_null;
-- DROP TABLE IF EXISTS null_unique_lab.sample_one_null;
-- DROP TABLE IF EXISTS null_unique_lab.optional_pairs;
-- DROP TABLE IF EXISTS null_unique_lab.tenant_refs_required;
-- DROP TABLE IF EXISTS null_unique_lab.tenant_refs_strict;
-- DROP TABLE IF EXISTS null_unique_lab.tenant_refs_default;
-- DROP TABLE IF EXISTS null_unique_lab.users_explicit_default;
-- DROP TABLE IF EXISTS null_unique_lab.users_strict;
-- DROP TABLE IF EXISTS null_unique_lab.users_default;
```

Do not use `DROP SCHEMA ... CASCADE` as a “quick cleanup” in a shared database: it can delete objects outside this lesson if anyone else uses the schema.

## 20. Common Misconceptions

**1. “UNIQUE always forbids two NULLs.”** False. PostgreSQL's default `UNIQUE` allows multiple `NULL`s in a single-column key.

**2. “Two NULLs are always equal in SQL.”** False. `NULL = NULL` yields unknown; `IS NOT DISTINCT FROM` returns true when both are `NULL`.

**3. “NULLS NOT DISTINCT is just another way to write NOT NULL.”** False. `NULLS NOT DISTINCT` still permits one `NULL` per unique key; `NOT NULL` forbids all `NULL`s.

**4. “NULLS NOT DISTINCT is a database-wide setting.”** False. It is a property of each individual unique constraint or index.

**5. “UNIQUE NULLS NOT DISTINCT (tenant_id, ref) allows only one NULL in the whole table.”** False when tenants differ. It protects the key tuple; each tenant may have one `ref NULL`.

**6. “If any composite key column is NULL, every row with a NULL collides.”** False. All corresponding key components must be non-distinct; non-NULL parts must still match.

**7. “UNIQUE NULLS NOT DISTINCT works in all PostgreSQL versions.”** False. It requires PostgreSQL **15+**.

**8. “You can just switch UNIQUE to NULLS NOT DISTINCT even if existing data has multiple NULLs.”** False. Conflicting tuples under the new rule must be resolved first.

**9. “ON CONFLICT DO UPDATE always catches two INSERTs with NULL.”** False under default `UNIQUE`; two `NULL`s do not conflict.

**10. “COUNT(DISTINCT code) reveals duplicate NULL records.”** False. `COUNT(DISTINCT code)` ignores `NULL`.

**11. “GROUP BY NULL and UNIQUE NULL must follow the same rule.”** False. `GROUP BY` groups `NULL`s together even while default `UNIQUE` allows multiple `NULL` rows.

**12. “Every unique index is a table constraint.”** False. Partial and expression unique indexes enforce different rules and cannot be attached as standard constraints via `USING INDEX`.

**13. “An index on (tenant_id, code) is the same as an index on (code).”** False. Composite uniqueness is scoped per tenant, unlike table-wide single-column uniqueness.

**14. “A SELECT EXISTS trigger is enough to prevent concurrent duplicate inserts.”** Unsafe without proper locking/concurrency design.

**15. “A unique violation always means duplicate email.”** False. Identify the specific failing constraint or index in schemas with multiple unique keys.

**16. “NULL and empty string are the same.”** False in PostgreSQL. Two empty strings collide as duplicates, whereas two `NULL`s depend on distinctness rules.

**17. “NOT NULL + UNIQUE and NULLS NOT DISTINCT behave differently even if the column is never NULL.”** For valid non-NULL data, their duplicate protection is equivalent; the difference is whether `NULL` is permitted or forbidden.

**18. “Adding a unique index concurrently has zero impact and always succeeds.”** False. It consumes resources, has transaction restrictions, and can leave an invalid index if it fails.

**19. “Setting NULLS NOT DISTINCT solves case-insensitive email duplicates.”** False. That requires normalization, collation, or expression indexes.

**20. “A unique constraint on a partitioned parent automatically enforces any business key across partitions.”** False. You must account for partition-key inclusion rules and actual uniqueness scope.

## 21. Practice Exercises with Answers

### Exercise 1 — Can Multiple NULLs Be Stored?

Table:

```sql
CREATE TABLE null_unique_lab.exercise_1 (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT UNIQUE
);
```

**Question:** Will inserting three `email=NULL` rows and one `email='a@example.test'` row succeed?

**Answer:** Yes, assuming no other constraint is violated. Default `UNIQUE` treats `NULL`s as distinct; non-NULL emails must still be unique.

### Exercise 2 — One NULL Table-Wide

**Requirement:** create a table with a `coupon_code` column that may be `NULL`, but only one row may have `coupon_code IS NULL`; all non-NULL values must also be unique.

**PostgreSQL 15+ Answer:**

```sql
CREATE TABLE null_unique_lab.exercise_2 (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    coupon_code TEXT,
    CONSTRAINT uq_exercise_2_coupon
        UNIQUE NULLS NOT DISTINCT (coupon_code)
);
```

Do not add `NOT NULL` because **one** `NULL` row is still permitted.

### Exercise 3 — One NULL per Tenant

**Requirement:** each tenant has an optional `fallback_code`, but at most one row per tenant may lack a code.

**Answer:**

```sql
CREATE TABLE null_unique_lab.exercise_3 (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    fallback_code TEXT,
    CONSTRAINT uq_exercise_3
        UNIQUE NULLS NOT DISTINCT (tenant_id, fallback_code)
);
```

`(1, NULL)` and `(2, NULL)` can coexist; inserting `(1, NULL)` a second time is rejected.

### Exercise 4 — Comparing Behavior on a Composite Key

Suppose the table already holds `(tenant_id, external_code) = (7, NULL)`.

| Row to Insert | Default UNIQUE | NULLS NOT DISTINCT |
|---|---|---|
| `(7, NULL)` | Allowed | Rejected |
| `(8, NULL)` | Allowed | Allowed |
| `(7, 'X')` | Allowed | Allowed |
| `(7, 'X')` second time | Rejected | Rejected |

**Explanation:** `tenant_id` is part of the key. Only matching both tenant and code (including both `NULL` when `NULLS NOT DISTINCT` is set) forms a duplicate tuple.

### Exercise 5 — Finding Data to Clean Before Migration

**Requirement:** list `(tenant_id, external_code)` combinations appearing more than once.

**Answer:**

```sql
SELECT tenant_id, external_code, COUNT(*) AS so_luong
FROM null_unique_lab.tenant_refs_default
GROUP BY tenant_id, external_code
HAVING COUNT(*) > 1;
```

`GROUP BY` groups `NULL`s together, making this the right query to detect tuples that would conflict with `NULLS NOT DISTINCT`.

### Exercise 6 — What Does ON CONFLICT Do with NULL?

**Question:** A table has default `UNIQUE (code)` and one row with `code=NULL`. Does `INSERT ... VALUES(NULL) ON CONFLICT (code) DO NOTHING` skip the insert?

**Answer:** Not necessarily; under default uniqueness, two `NULL`s do not conflict, so it **inserts another row**. With `UNIQUE NULLS NOT DISTINCT (code)` on PostgreSQL 15+, the second `NULL` conflicts and `DO NOTHING` skips it.

### Exercise 7 — When Not to Use NULLS NOT DISTINCT?

A system has thousands of users who have not provided an email yet. Non-NULL emails must be unique, while users may register first and add an email later.

**Answer:** Default `UNIQUE (email)` fits better. `NULLS NOT DISTINCT` would permit only one account with a `NULL` email across the entire table, breaking the business requirement.

### Exercise 8 — Pre-PostgreSQL 15 Workaround

**Requirement:** `tenant_id NOT NULL`, `external_code` nullable; within each tenant at most one row may be `NULL`, and non-NULL codes cannot duplicate. PostgreSQL 14.

**Answer:** Combine:

```sql
CREATE TABLE null_unique_lab.exercise_8 (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    external_code TEXT,
    UNIQUE (tenant_id, external_code)
);

CREATE UNIQUE INDEX uq_exercise_8_one_null
ON null_unique_lab.exercise_8 (tenant_id)
WHERE external_code IS NULL;
```

The first constraint protects concrete codes; the partial unique index limits `NULL` to one per tenant. If other columns are also nullable, additional tailored rules are needed.

### Exercise 9 — Checking with pg_catalog

**Requirement:** on PostgreSQL 15+, find unique indexes using `NULLS NOT DISTINCT` in the lab schema.

**Answer:**

```sql
SELECT
    ns.nspname AS schema_name,
    rel.relname AS table_name,
    idx.indexrelid::regclass AS index_name,
    pg_get_indexdef(idx.indexrelid) AS definition
FROM pg_index AS idx
JOIN pg_class AS rel
    ON rel.oid = idx.indrelid
JOIN pg_namespace AS ns
    ON ns.oid = rel.relnamespace
WHERE ns.nspname = 'null_unique_lab'
  AND idx.indisunique
  AND idx.indnullsnotdistinct
ORDER BY table_name, index_name;
```

On PostgreSQL 14, `indnullsnotdistinct` does not exist yet, so the query will not run as-is.

### Exercise 10 — Does NULLS NOT DISTINCT Make NULL = NULL True?

**Answer:** No. Run:

```sql
SELECT
    NULL = NULL AS so_sanh_thuong,
    NULL IS NOT DISTINCT FROM NULL AS so_sanh_null_safe;
```

The results remain `NULL` and `true`, regardless of any unique constraints defined on tables.

### Exercise 11 — What If You Want to Forbid NULL Completely?

A contract code must have a value and be unique across the whole table.

**Answer:** `contract_code TEXT NOT NULL UNIQUE`. Using `UNIQUE NULLS NOT DISTINCT` is insufficient because it still permits one `NULL`.

### Exercise 12 — One Active Record per Key

A table holds active records and archived records (`archived_at IS NOT NULL`); each tenant may have at most one matching code, including `NULL`, **among active records**.

**PostgreSQL 15+ Answer:**

```sql
CREATE UNIQUE INDEX uq_exercise_active
ON null_unique_lab.active_slots (tenant_id, slot_code)
NULLS NOT DISTINCT
WHERE archived_at IS NULL;
```

*Note:* Section 7's lab already created index `uq_active_slots` enforcing the same rule; the query above is an **illustrative syntax answer** and does not need to be re-run on that table unless the earlier index was dropped in your test environment.

## 22. Decision Process When Designing a Unique Constraint

When given a requirement like “codes must not duplicate”, proceed in order:

1. **Identify the business key:** a single column or a composite tuple like `(tenant_id, external_code)`?
2. **Identify the scope:** table-wide, per tenant, per day, or only active rows?
3. **Define NULL behavior:** forbidden, permitted multiple times, or permitted once per scope?
4. **Choose the construct:** `NOT NULL UNIQUE` if `NULL` is forbidden; default `UNIQUE` if multiple `NULL`s are valid; `UNIQUE NULLS NOT DISTINCT` when `NULL`s must count as duplicates.
5. **If row-filtered:** consider a partial unique index with `WHERE`.
6. **If multiple key columns are nullable:** verify every `NULL` combination, not just a single simple case.
7. **If upserting:** specify conflict targets and `DO UPDATE`/`DO NOTHING` behavior for `NULL` explicitly.
8. **If the table has existing data:** query `GROUP BY ... HAVING COUNT(*) > 1` and resolve duplicates per business rules before adding the new constraint.
9. **If the table is large:** evaluate `CREATE UNIQUE INDEX CONCURRENTLY`, locks, I/O, invalid-index cleanup, and attachment dependencies.
10. **If PostgreSQL 14 or older must be supported:** use a scope-appropriate workaround or upgrade rather than running PostgreSQL 15+ syntax on older servers.
11. **If the table is partitioned:** account for partition-key inclusion rules and actual uniqueness scope.
12. **Post-deployment:** test duplicate inserts, `23505` handling, concurrent connections, upserts, and catalog index/constraint definitions.

## 23. Summary

In PostgreSQL, **default `UNIQUE` treats `NULL` values as distinct during uniqueness checks**, so a nullable column can hold multiple `NULL` rows. Starting in **PostgreSQL 15**, **`UNIQUE NULLS NOT DISTINCT`** and **`CREATE UNIQUE INDEX ... NULLS NOT DISTINCT`** let you treat two `NULL`s as **non-distinct**, blocking identical key combinations even when components are missing.

Three decisions to keep clear:

- **Value is required:** use `NOT NULL`, plus `UNIQUE` if uniqueness is needed.
- **Multiple records without a value are valid:** default `UNIQUE` is usually right.
- **At most one tuple with `NULL` per scope:** consider `NULLS NOT DISTINCT`, especially for tenant-scoped composite keys or default entities.

This setting only affects **the declared unique constraint or index**, never altering `NULL = NULL` or general SQL comparisons. When applying it to populated tables, check for duplicate tuples, understand `ON CONFLICT`, assess locks and migration costs, and test with concurrent transactions. **A good constraint is not just DDL that runs—it is one that accurately encodes business rules when data contains `NULL`.**

Official PostgreSQL documentation references:

- [Unique Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-UNIQUE-CONSTRAINTS).
- [CREATE TABLE](https://www.postgresql.org/docs/current/sql-createtable.html).
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html).
- [INSERT and ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html).
- [Indexes on Expressions / Partial Indexes](https://www.postgresql.org/docs/current/indexes-expressional.html), [Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html).
