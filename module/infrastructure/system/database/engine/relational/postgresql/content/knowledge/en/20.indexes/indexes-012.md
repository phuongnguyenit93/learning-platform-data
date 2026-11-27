# Unique Indexes, NULLs, and Data Constraints

A user registration application needs to prevent two accounts from sharing the same email. A multi-tenant system requires emails to be unique **within each tenant**. A table storing external partner reference codes allows missing codes (`NULL`), yet each tenant may only have at most one record with a missing code. A **soft-delete** table must allow re-creating an email after an older account has been soft-deleted, while prohibiting two active accounts from sharing the same email.

All of these revolve around **uniqueness**, yet none can be solved accurately by mechanically slapping `UNIQUE` on a column.

In PostgreSQL:

- A **`UNIQUE` constraint** protects a data invariant and is enforced by a **unique B-tree index**.
- A **unique index** can be created directly, including flexible variants such as **expression indexes** and **partial unique indexes** that standard table constraints cannot express directly.
- By default, **`NULL` values are treated as distinct** during uniqueness checks; therefore, multiple rows can share the same key combination containing `NULL`.
- Starting in **PostgreSQL 15**, `NULLS NOT DISTINCT` allows treating `NULL` values as equal for uniqueness enforcement.
- **`PRIMARY KEY`** enforces not only uniqueness but also **`NOT NULL`** on every key column.
- Uniqueness enforcement is safe under **concurrency**; a `SELECT` finding no row does not prove another concurrent transaction has not inserted that key.
- **`ON CONFLICT`** enables atomic handling of key collisions, yet carries important limitations regarding **deferrable constraints** and index types.

This lesson progresses from syntax and semantics to real-world data modeling, large-table migrations, deduplication, catalog inspection, Java/JDBC handling, and exercises.

> **Environment:** This lesson targets modern PostgreSQL. Examples using `NULLS NOT DISTINCT` require **PostgreSQL 15 or newer**. Only run table, index, constraint creation/deletion, or cleanup commands inside a **lab database**. In production, verify server version, existing data, lock plans, write load, and migration policies before altering uniqueness rules.

## 1. What Problem Does a Unique Index Solve?

Suppose a customer table stores:

| account_id | tenant_id | email |
|---:|---:|---|
| 1 | 10 | an@example.test |
| 2 | 10 | binh@example.test |
| 3 | 20 | an@example.test |

If the requirement is “**no two accounts within a tenant may share the same email**,” the data above is valid: An's email appears in **different tenants**, so it does not violate the composite key.

However, inserting:

| account_id | tenant_id | email |
|---:|---:|---|
| 4 | 10 | an@example.test |

violates the invariant.

At the PostgreSQL layer, the constraint:

```sql
UNIQUE (tenant_id, email)
```

forces the engine to detect and reject operations producing two rows with the same `(tenant_id, email)` combination under the applicable equality, collation, and NULL rules.

### Why Not Just SELECT Before INSERT?

```sql
SELECT 1
FROM accounts
WHERE tenant_id = 10
  AND email = 'an@example.test';

-- No row found, then:
INSERT INTO accounts (...);
```

Two transactions can **both `SELECT` and see no existing row**, then both `INSERT`. This is a classic race condition:

```text
Transaction A                  Transaction B
-------------------------      -------------------------
SELECT key => not found
                               SELECT key => not found
INSERT key
                               INSERT key
COMMIT
                               COMMIT ?
```

Without a database-level unique constraint, both rows can be persisted. With a unique constraint/index, PostgreSQL coordinates conflicts at the storage and transaction layers so **two violating records can never both commit**.

**Never treat application-level checks as a substitute for database constraints.** Pre-write validation helps return friendly error messages, yet a unique constraint is the final safeguard against races.

## 2. UNIQUE Constraint vs. UNIQUE Index: Similarities and Differences

Two common approaches:

```sql
-- Option 1: declare constraint in table schema.
CREATE TABLE accounts_example (
    account_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email TEXT NOT NULL,
    CONSTRAINT uq_accounts_tenant_email
        UNIQUE (tenant_id, email)
);
```

```sql
-- Option 2: create a unique index directly.
CREATE UNIQUE INDEX ux_accounts_tenant_email
ON accounts_example (tenant_id, email);
```

These two snippets are **independent examples**; do not create both on the same table because they enforce the identical key combination and cause redundant index overhead.

| Criterion | `UNIQUE` constraint | `CREATE UNIQUE INDEX` |
|---|---|---|
| Expressive purpose | Data invariant in relational schema. | Index structure enforcing uniqueness. |
| Enforcement mechanism | Backed by a unique index. | The unique index itself enforces uniqueness. |
| Multi-column keys | Yes. | Yes. |
| `NULLS NOT DISTINCT` (PostgreSQL 15+) | Yes. | Yes. |
| Expressions like `lower(email)` | Cannot declare expressions directly in constraint column list. | Yes. |
| Predicate `WHERE deleted_at IS NULL` | No direct partial unique constraint syntax. | Supports partial unique indexes. |
| `DEFERRABLE` | Yes, on eligible constraints. | Directly created indexes are not deferrable constraints. |
| Foreign key target | Can serve as referenced key if eligible. | Non-partial unique indexes on plain columns can also serve as referenced keys. |
| Build `CONCURRENTLY` | Not directly via `ALTER TABLE ... ADD UNIQUE`. | `CREATE UNIQUE INDEX CONCURRENTLY` is supported. |

**How to choose:** prefer a `UNIQUE` constraint when expressing a data rule over **plain columns**. Use a direct unique index when you need **expressions**, **filter predicates**, or online concurrent index deployment strategies.

### A UNIQUE Constraint Already Creates an Index

Declaring:

```sql
CONSTRAINT uq_accounts_tenant_email UNIQUE (tenant_id, email)
```

already builds the backing unique B-tree index. Do not additionally create:

```sql
CREATE UNIQUE INDEX ...
ON accounts (tenant_id, email);
```

when it serves the exact same purpose. Redundant indexes waste disk space, WAL volume, and `INSERT`/`UPDATE`/`DELETE` time.

## 3. Preparing the Lab Database

Create a dedicated schema:

```sql
CREATE SCHEMA IF NOT EXISTS lesson_unique;
```

Create an accounts table with a composite unique key:

```sql
CREATE TABLE lesson_unique.accounts (
    account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_accounts_tenant_email
        UNIQUE (tenant_id, email)
);
```

Insert valid data:

```sql
INSERT INTO lesson_unique.accounts (
    tenant_id, email, display_name
)
VALUES
    (10, 'an@example.test', 'An in tenant 10'),
    (10, 'binh@example.test', 'Binh in tenant 10'),
    (20, 'an@example.test', 'An in tenant 20');
```

Inspect:

```sql
SELECT
    account_id,
    tenant_id,
    email,
    display_name
FROM lesson_unique.accounts
ORDER BY tenant_id, email;
```

### Triggering unique_violation

```sql
INSERT INTO lesson_unique.accounts (
    tenant_id, email, display_name
)
VALUES (
    10, 'an@example.test', 'Duplicate account'
);
```

PostgreSQL rejects the new row, typically reporting:

```text
ERROR: duplicate key value violates unique constraint
       "uq_accounts_tenant_email"
DETAIL: Key (tenant_id, email)=(10, an@example.test)
        already exists.
SQLSTATE: 23505
```

**Transaction note:** If you execute a failing statement inside `BEGIN ... COMMIT`, the transaction enters an **aborted** state and requires `ROLLBACK` or a valid `ROLLBACK TO SAVEPOINT` before issuing further statements. Run error-inducing lab examples in autocommit mode or manage rollbacks explicitly.

## 4. A UNIQUE Constraint Can Span Multiple Columns

The constraint:

```sql
UNIQUE (tenant_id, email)
```

ensures the **combination** is unique, not that each column individually is unique.

| tenant_id | email | Valid? |
|---:|---|---|
| 10 | an@example.test | First row; valid. |
| 10 | binh@example.test | Valid because email differs. |
| 20 | an@example.test | Valid because tenant differs. |
| 10 | an@example.test | **Invalid** because the entire tuple collides. |

### Not Equivalent to Two Single-Column UNIQUE Constraints

```sql
UNIQUE (tenant_id),
UNIQUE (email)
```

is completely different from:

```sql
UNIQUE (tenant_id, email)
```

The first form forces every `tenant_id` to appear at most once **and** every email to appear at most once across the entire table—almost always wrong for multi-user multi-tenant apps.

### Column Order Affects Query Performance

Regarding **tuple uniqueness**, `UNIQUE (tenant_id, email)` and `UNIQUE (email, tenant_id)` enforce the same duplicate set. However, column order in the backing **B-tree index** affects which filter and sort queries can leverage the index, such as:

```sql
WHERE tenant_id = 10 AND email = ?
```

or:

```sql
WHERE tenant_id = 10 ORDER BY email
```

Never add two reversed-order unique indexes solely for the same constraint. Pick column order from workload needs and check execution plans.

## 5. SQL NULL Is Not an Ordinary Value

`NULL` represents a **missing/unknown value**, not an empty string, zero, or special sentinel character.

Ordinary comparisons:

```sql
SELECT
    NULL = NULL AS equal_result,
    NULL <> NULL AS not_equal_result,
    NULL IS NULL AS is_null_result,
    NULL IS NOT NULL AS is_not_null_result;
```

Conceptual results:

| Expression | Result |
|---|---|
| `NULL = NULL` | SQL `NULL` (*unknown*). |
| `NULL <> NULL` | SQL `NULL` (*unknown*). |
| `NULL IS NULL` | `true`. |
| `NULL IS NOT NULL` | `false`. |

When comparing two nullable values with “nulls treated as non-distinct” semantics:

```sql
SELECT
    NULL IS NOT DISTINCT FROM NULL AS same_null,
    NULL IS DISTINCT FROM 5 AS differs_from_five,
    5 IS NOT DISTINCT FROM 5 AS same_value;
```

All three evaluate to `true`.

**Never write `column = NULL` to filter missing values.** Use `column IS NULL`.

### NULL vs. Empty String

```sql
SELECT
    '' IS NULL AS empty_is_null,
    '' = '' AS empty_equals_empty;
```

An empty string is an **actual non-null text value**. It participates in unique checks like any non-null string and can collide on duplicates depending on key rules.

## 6. Default UNIQUE Allows Multiple NULLs

This is one of the most surprising rules in this topic.

```sql
CREATE TABLE lesson_unique.codes_default (
    id INTEGER PRIMARY KEY,
    optional_code TEXT UNIQUE
);
```

Try inserting:

```sql
INSERT INTO lesson_unique.codes_default(id, optional_code)
VALUES
    (1, NULL),
    (2, NULL),
    (3, 'CODE-A'),
    (4, 'CODE-B');
```

**This succeeds** under default unique semantics: **two rows both have `NULL`** in `optional_code`.

By contrast:

```sql
INSERT INTO lesson_unique.codes_default(id, optional_code)
VALUES (5, 'CODE-A');
-- ERROR 23505 because CODE-A already exists.
```

### Why Are Multiple NULLs Permitted?

Under PostgreSQL's default semantics, null values in a unique index/constraint are treated as **distinct** (*`NULLS DISTINCT`*) for uniqueness checking. Because two unknown values cannot be proven equal, the database allows multiple null rows.

This is **`UNIQUE`-specific behavior**, not a universal rule across SQL constructs:

- `GROUP BY` groups null rows together into one group.
- `IS NOT DISTINCT FROM` considers two nulls non-distinct.
- Default `UNIQUE` allows multiple nulls.

Never infer `UNIQUE` behavior directly from `GROUP BY` output.

## 7. Multi-Column UNIQUE When One Component Is NULL

Create a table:

```sql
CREATE TABLE lesson_unique.refs_default (
    ref_id INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    external_ref TEXT,
    CONSTRAINT uq_refs_default
        UNIQUE (tenant_id, external_ref)
);
```

The following inserts **are permitted**:

```sql
INSERT INTO lesson_unique.refs_default(
    ref_id, tenant_id, external_ref
)
VALUES
    (1, 10, NULL),
    (2, 10, NULL),
    (3, 10, 'EXT-A'),
    (4, 20, 'EXT-A'),
    (5, 20, NULL);
```

Explanation:

- Two `(10, NULL)` rows are allowed even within the same tenant.
- `(10, 'EXT-A')` and `(20, 'EXT-A')` are allowed because `tenant_id` differs.
- A **second** `(10, 'EXT-A')` row violates uniqueness.

### General Rule

With default `UNIQUE (a, b)`, when one or more key values are `NULL`, rows containing those combinations can coexist without triggering a violation the way matching all-non-null tuples would.

That is why the rule:

> “Each tenant may have at most one record with an unknown `external_ref`”

is **not enforced** by default `UNIQUE (tenant_id, external_ref)` when `external_ref` is nullable.

## 8. NULLS NOT DISTINCT Starting in PostgreSQL 15

PostgreSQL 15 introduced the option:

```sql
UNIQUE NULLS NOT DISTINCT (column_name)
```

or:

```sql
CREATE UNIQUE INDEX ...
ON some_table (column_name) NULLS NOT DISTINCT;
```

With this setting, two nulls are treated as **not distinct** during uniqueness checks, matching `IS NOT DISTINCT FROM` semantics across key components.

### Single-Column Table

```sql
CREATE TABLE lesson_unique.codes_strict (
    id INTEGER PRIMARY KEY,
    optional_code TEXT,
    CONSTRAINT uq_codes_strict
        UNIQUE NULLS NOT DISTINCT (optional_code)
);
```

Insert the first row:

```sql
INSERT INTO lesson_unique.codes_strict(id, optional_code)
VALUES (1, NULL);
```

Insert a second row with `NULL`:

```sql
INSERT INTO lesson_unique.codes_strict(id, optional_code)
VALUES (2, NULL);
-- ERROR 23505 on PostgreSQL 15+.
```

Now **at most one null row** is permitted in the table for `optional_code`, absent other scoping conditions.

### Do Not Confuse With NOT NULL

- `NOT NULL`: permits **zero nulls**.
- Default `UNIQUE`: permits **multiple nulls**, rejects duplicate non-nulls.
- `UNIQUE NULLS NOT DISTINCT`: permits **at most one null** (on a single-column key), rejects duplicate non-nulls.

These three options enforce **three distinct data invariants**.

## 9. NULLS NOT DISTINCT with Composite Keys

```sql
CREATE TABLE lesson_unique.refs_strict (
    ref_id INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    external_ref TEXT,
    CONSTRAINT uq_refs_strict
        UNIQUE NULLS NOT DISTINCT (
            tenant_id,
            external_ref
        )
);
```

This enforces: **each `(tenant_id, external_ref)` pair is unique, even when `external_ref` is null**.

```sql
INSERT INTO lesson_unique.refs_strict(
    ref_id, tenant_id, external_ref
)
VALUES
    (1, 10, NULL),
    (2, 20, NULL),
    (3, 10, 'EXT-A'),
    (4, 20, 'EXT-A');
```

All four rows succeed. Each tenant now has one null row and one `'EXT-A'` row.

```sql
INSERT INTO lesson_unique.refs_strict(
    ref_id, tenant_id, external_ref
)
VALUES (5, 10, NULL);
-- ERROR 23505: (10, NULL) already exists.
```

Whereas:

```sql
INSERT INTO lesson_unique.refs_strict(
    ref_id, tenant_id, external_ref
)
VALUES (6, 30, NULL);
-- Succeeds because tenant_id=30 differs.
```

**It does not limit the entire table to one `NULL`** when the unique key spans multiple columns. Uniqueness evaluates the **full key tuple**, so `(10, NULL)` and `(20, NULL)` remain distinct because `tenant_id` differs.

### Multiple Nullable Columns

With `UNIQUE NULLS NOT DISTINCT (a, b, c)`, two rows collide when **every corresponding component is non-distinct**, including matching nulls in the same column positions. If even one non-null component differs, the tuples remain distinct.

## 10. Creating a Unique Index Directly with NULLS NOT DISTINCT

Instead of a table constraint, you can write:

```sql
CREATE TABLE lesson_unique.codes_indexed (
    id BIGINT PRIMARY KEY,
    optional_code TEXT
);

CREATE UNIQUE INDEX ux_codes_indexed_not_distinct
ON lesson_unique.codes_indexed (optional_code)
NULLS NOT DISTINCT;
```

This index enforces **no two rows share the same `optional_code`, including `NULL`**.

### When to Choose a Constraint Instead?

If this represents a straightforward data-model invariant, placing:

```sql
CONSTRAINT uq_optional_code
UNIQUE NULLS NOT DISTINCT (optional_code)
```

in the table definition is clearer.

When building an index directly to support online migrations or needing expressions/partial predicates, use the corresponding `CREATE UNIQUE INDEX` syntax. Simple eligible unique indexes can later be attached as constraints under PostgreSQL's supported conditions.

### Versions Older Than PostgreSQL 15

Before PostgreSQL 15, `NULLS NOT DISTINCT` syntax is unsupported. Do not run it on older servers assuming PostgreSQL ignores the clause.

Check server version:

```sql
SHOW server_version;

SELECT current_setting('server_version_num')::integer
       AS server_version_num;
```

If you need “at most one NULL” on older versions, design an alternative such as scoped partial unique indexes or adjust the schema model.

## 11. Legacy Technique: Partial Unique Index Allowing One NULL

On PostgreSQL older than 15, a nullable `code` column could be constrained via:

```sql
CREATE TABLE lesson_unique.legacy_codes (
    id BIGINT PRIMARY KEY,
    code TEXT
);

-- Non-null codes must be unique.
CREATE UNIQUE INDEX ux_legacy_code_nonnull
ON lesson_unique.legacy_codes (code)
WHERE code IS NOT NULL;

-- Only one row may have code IS NULL.
CREATE UNIQUE INDEX ux_legacy_code_null
ON lesson_unique.legacy_codes ((true))
WHERE code IS NULL;
```

Because all rows where `code IS NULL` are indexed under the constant expression key `true`, the second unique index rejects more than one row in that subset.

### Pros and Cons

- Expresses the rule on pre-15 PostgreSQL.
- Yet requires **two indexes** and more subtle logic.
- Error-prone when extended across multiple columns/tenants.
- Not a standard `UNIQUE NULLS NOT DISTINCT` constraint.
- Migrations and `ON CONFLICT` require careful arbiter index inference.

On PostgreSQL 15+, `NULLS NOT DISTINCT` is typically cleaner and more direct.

## 12. How Does PRIMARY KEY Differ from UNIQUE?

`PRIMARY KEY` requires every participating key column to be **non-null** and **unique**. A table can have only **one primary key constraint** (which may span multiple columns), yet can have multiple unique constraints.

```sql
CREATE TABLE lesson_unique.products (
    product_id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    barcode TEXT UNIQUE,
    product_name TEXT NOT NULL
);
```

Meaning:

- `product_id`: non-null, unique, primary identifier.
- `sku`: non-null, unique; can act as an **alternate key**.
- `barcode`: unique among known non-null values, yet **permits multiple `NULL`s** by default.
- `product_name`: non-null yet **not unique**; multiple products can share a name.

### Composite Primary Key

```sql
CREATE TABLE lesson_unique.order_items (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, line_no)
);
```

Two rows cannot share the same `(order_id, line_no)`. All primary key columns automatically carry `NOT NULL`.

### Should You Replace PRIMARY KEY with a Nullable UNIQUE?

If a column is a mandatory identity referenced across the system, `PRIMARY KEY` communicates intent better. If an optional external code may initially be unknown, nullable `UNIQUE` fits better.

Do not substitute `UNIQUE NULLS NOT DISTINCT` for a `PRIMARY KEY` when business rules genuinely require **zero nulls**.

## 13. NOT NULL and UNIQUE Answer Two Different Questions

Example:

```sql
CREATE TABLE lesson_unique.api_clients (
    client_id BIGINT PRIMARY KEY,
    client_key TEXT NOT NULL,
    tenant_id BIGINT NOT NULL,
    CONSTRAINT uq_api_clients_tenant_key
        UNIQUE (tenant_id, client_key)
);
```

- `NOT NULL`: the key must be present.
- `UNIQUE`: the key must not repeat **within a tenant**.

Constraints can also add format rules:

```sql
ALTER TABLE lesson_unique.api_clients
ADD CONSTRAINT ck_api_client_key_nonblank
CHECK (length(btrim(client_key)) > 0);
```

Even then, `client_key = 'ABC'` and `client_key = 'abc'` are still distinct under default comparison/collation rules.

**Valid data relies on layered constraints:** `NOT NULL`, `UNIQUE`, `CHECK`, foreign keys, and other rules guard orthogonal invariants.

## 14. CHECK Is No Substitute for UNIQUE

`CHECK` validates conditions on **the row currently being written**, not across all rows in a table.

Valid example:

```sql
CHECK (quantity >= 0)
```

Flawed design attempt:

```sql
-- Invalid pattern to mimic UNIQUE with CHECK:
-- CHECK (
--    NOT EXISTS (
--      SELECT 1 FROM this_table WHERE ... 
--    )
-- )
```

PostgreSQL does not allow arbitrary subqueries in `CHECK` constraints that way. Even attempting to hide a table lookup inside a user-defined function within `CHECK` is unsafe and unstable under concurrency, and can break dump/restore.

**Use `UNIQUE`/unique indexes for uniqueness; use `CHECK` for single-row validity rules.**

## 15. Soft Delete: Why UNIQUE(tenant_id, email, deleted_at) Usually Fails

Consider:

```sql
CREATE TABLE lesson_unique.members_wrong (
    member_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email TEXT NOT NULL,
    deleted_at TIMESTAMPTZ,
    UNIQUE (tenant_id, email, deleted_at)
);
```

You intend:

- Each tenant has **at most one active member** per email.
- Active members have `deleted_at IS NULL`.
- Soft-deleted records have non-null `deleted_at` and stay archived for audit.

However, the following statement **succeeds and inserts both rows**:

```sql
INSERT INTO lesson_unique.members_wrong(
    member_id, tenant_id, email, deleted_at
)
VALUES
    (1, 10, 'an@example.test', NULL),
    (2, 10, 'an@example.test', NULL);
```

Because a default unique constraint treats `NULL` in `deleted_at` as **distinct**, it fails to reject two rows with trailing nulls.

### Does NULLS NOT DISTINCT Properly Solve Soft Delete?

If you declare:

```sql
UNIQUE NULLS NOT DISTINCT (
    tenant_id, email, deleted_at
)
```

active duplicate emails (where `deleted_at` is null) are blocked. However, the constraint also applies to **deleted rows** sharing the exact same `deleted_at` timestamp—which is often not what the business wants, and deletion timestamps are awkward identity keys anyway.

**Cleaner design:** use a **partial unique index scoped strictly to active rows**.

## 16. Partial Unique Index for Active Records

```sql
CREATE TABLE lesson_unique.members (
    member_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    deleted_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX ux_members_active_email
ON lesson_unique.members (tenant_id, email)
WHERE deleted_at IS NULL;
```

Semantics:

- The index includes only rows matching `deleted_at IS NULL`.
- Within the **active** subset, `(tenant_id, email)` must be unique.
- Soft-deleted rows (`deleted_at IS NOT NULL`) **do not enter this index**, allowing unlimited historical copies with the same email.

Example:

```sql
INSERT INTO lesson_unique.members(
    member_id, tenant_id, email, display_name, deleted_at
)
VALUES
    (1, 10, 'an@example.test', 'Old An',
        TIMESTAMPTZ '2026-01-01 00:00:00+00'),
    (2, 10, 'an@example.test', 'Current An', NULL),
    (3, 20, 'an@example.test', 'An tenant 20', NULL);
```

All three rows are valid.

Now attempt a second active row in tenant 10:

```sql
INSERT INTO lesson_unique.members(
    member_id, tenant_id, email, display_name, deleted_at
)
VALUES (4, 10, 'an@example.test', 'Duplicate An', NULL);
-- ERROR 23505: conflict within the active subset.
```

### Soft Delete and Re-Create

```sql
UPDATE lesson_unique.members
SET deleted_at = now()
WHERE member_id = 2;

INSERT INTO lesson_unique.members(
    member_id, tenant_id, email, display_name, deleted_at
)
VALUES (5, 10, 'an@example.test', 'New An', NULL);
```

Once member 2 no longer satisfies the predicate, member 5 can be inserted if no other active conflict exists.

### No Direct Partial UNIQUE Constraint Syntax

This uses **index** syntax:

```sql
CREATE UNIQUE INDEX ...
WHERE deleted_at IS NULL;
```

PostgreSQL has no `CONSTRAINT UNIQUE (...) WHERE deleted_at IS NULL` syntax in standard table constraint definitions. Hence you cannot convert a **partial unique index** into a standard unique constraint via `ALTER TABLE ... ADD CONSTRAINT UNIQUE USING INDEX`.

## 17. One Tenant, Multiple Emails, and Conditional Unique Keys

Different requirements call for different definitions:

| Business Rule | Typical Design |
|---|---|
| Globally unique non-null email | `email TEXT NOT NULL UNIQUE`. |
| Email unique per tenant | `UNIQUE (tenant_id, email)`. |
| Optional email, multiple missing emails allowed | Default `UNIQUE (email)` or composite key. |
| Nullable email, at most one `NULL` | `UNIQUE NULLS NOT DISTINCT (email)` (PG15+). |
| Unique only among active emails | `CREATE UNIQUE INDEX ... WHERE deleted_at IS NULL`. |
| Case-insensitive email uniqueness | Expression index like `lower(email)` or suitable type/collation. |
| Unique only for non-null active emails | Partial unique index with combined predicate; verify null handling. |

### The WHERE Predicate Must Match the Exact Definition of “Active”

An application might define active as:

```sql
deleted_at IS NULL AND status = 'ACTIVE'
```

rather than merely `deleted_at IS NULL`. If the index predicate diverges from business rules, the database may allow duplicates you expected to forbid, or reject combinations the application wants to permit.

**A partial unique index predicate is part of the data invariant.** Review it like a business rule, not merely a query optimization hint.

## 18. Expression Unique Indexes: Uniqueness on Computed Expressions

Sometimes two email inputs must collide even when letter casing or surrounding whitespace differs:

```text
An@Example.Test
an@example.test
 an@example.test 
```

An expression unique index handles this:

```sql
CREATE TABLE lesson_unique.normalized_accounts (
    account_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email TEXT NOT NULL
);

CREATE UNIQUE INDEX ux_normalized_accounts_email
ON lesson_unique.normalized_accounts (
    tenant_id,
    lower(btrim(email))
);
```

Here `lower(btrim(email))` acts as the **index key**, rather than the raw stored `email` string.

Example:

```sql
INSERT INTO lesson_unique.normalized_accounts(
    account_id, tenant_id, email
)
VALUES (1, 10, 'An@Example.Test');

INSERT INTO lesson_unique.normalized_accounts(
    account_id, tenant_id, email
)
VALUES (2, 10, ' an@example.test ');
-- Fails with ERROR 23505 because both key expressions match.
```

### Requirements for Expression Indexes

PostgreSQL requires index key functions/expressions to satisfy immutability rules—typically **`IMMUTABLE`** functions. Never base a unique index on values varying with current time, external state, or session GUCs.

### Caution Regarding Email and Unicode

`lower(btrim(email))` is strictly an **illustrative normalization rule**. Case mapping depends on collation/locale and application rules. Never assume every email standard treats the local-part as strictly case-insensitive via simple `lower`/`btrim`.

In internationalized systems, align on Unicode normalization, collation, canonicalization, and email parsing policies before enforcing uniqueness.

## 19. Combining Expression and Partial Unique Indexes

Two requirements:

1. Within a tenant, no two active members may share the same **normalized** email.
2. Multiple soft-deleted records with the same email are permitted.

Definition:

```sql
CREATE TABLE lesson_unique.members_normalized (
    member_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    deleted_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX ux_members_normalized_active
ON lesson_unique.members_normalized (
    tenant_id,
    lower(btrim(email))
)
WHERE deleted_at IS NULL;
```

This single index enforces uniqueness only on active rows, keyed by **normalized text**. It is simultaneously:

- A **Unique index**.
- An **Expression index**.
- A **Partial index**.

### API-Layer Validation

Suppose a user submits `" AN@example.test "`. Applications should normalize/validate before inserting so error messages stay clear. Still, the database unique index remains the authoritative enforcement guard under concurrent requests.

### Cannot Reference Partial/Expression Indexes via ON CONSTRAINT

`ON CONFLICT ON CONSTRAINT name` expects a **constraint name**, not an arbitrary index name. `ux_members_normalized_active` is an **index**, not a `UNIQUE` constraint attached via `ALTER TABLE`.

To UPSERT against this index, use **conflict-target inference** matching the exact expression and predicate—or consider schema alternatives like a stored generated column for simplicity.

## 20. Case-Insensitive Uniqueness: lower, citext, and Collations

Several strategies exist:

### Approach A — Expression Index

```sql
CREATE UNIQUE INDEX ux_email_lower
ON lesson_unique.normalized_accounts (
    tenant_id, lower(email)
);
```

In production, avoid maintaining both `ux_email_lower` and `ux_normalized_accounts_email` if they target the same rule with conflicting trim semantics; commit to **one clear policy**.

### Approach B — citext

PostgreSQL ships the `citext` extension providing case-insensitive text comparisons per extension/collation semantics:

```sql
-- Run only if permissions and extensions allow:
CREATE EXTENSION IF NOT EXISTS citext;

-- Standalone example:
CREATE TABLE lesson_unique.citext_users (
    user_id BIGINT PRIMARY KEY,
    email CITEXT NOT NULL UNIQUE
);
```

Using an extension requires checking deployment environments, extension dependencies, and collation rules. `citext` does not automatically solve Unicode normalization, whitespace trimming, or business-specific email parsing rules.

### Approach C — Nondeterministic Collations

Modern PostgreSQL supports **nondeterministic** collations for case- or accent-insensitive comparison depending on provider/locale and version. When adopting one, check operator limitations, performance implications, and ICU upgrade behavior.

**Never mix approaches haphazardly.** Different comparison configurations define different notions of “equality,” yielding different uniqueness behavior.

## 21. INCLUDE Columns Do Not Participate in Uniqueness

A B-tree index can store extra payload columns to support index-only scans:

```sql
CREATE TABLE lesson_unique.customer_directory (
    customer_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL
);

CREATE UNIQUE INDEX ux_customer_directory_email
ON lesson_unique.customer_directory (tenant_id, email)
INCLUDE (display_name);
```

This index defines:

- **Key columns:** `tenant_id` and `email`.
- **Included/non-key column:** `display_name`.

Uniqueness is enforced **solely on the key columns**, excluding `display_name`.

### Example

Two rows:

```text
(tenant=10, email='a@example.test', display_name='A')
(tenant=10, email='a@example.test', display_name='B')
```

still violate uniqueness despite having different display names.

### INCLUDE Is Not Free

`INCLUDE` columns enlarge the index and raise write work. Index-only scans still depend on visibility map state and workloads—never guaranteed solely by `INCLUDE`. Measure with `EXPLAIN (ANALYZE, BUFFERS)` when tuning.

## 22. DEFERRABLE UNIQUE Constraints

By default, unique constraints check **immediately during the statement**, yet PostgreSQL supports **deferrable unique constraints** to postpone validation.

```sql
CREATE TABLE lesson_unique.priority_slots (
    slot_id INTEGER PRIMARY KEY,
    position INTEGER NOT NULL,
    CONSTRAINT uq_priority_position
        UNIQUE (position)
        DEFERRABLE INITIALLY IMMEDIATE
);

INSERT INTO lesson_unique.priority_slots(slot_id, position)
VALUES (1, 10), (2, 20);
```

### Why Use DEFERRABLE?

Suppose you need to **swap positions 10 and 20** between two rows. Intermediate states during multi-statement or row-by-row updates may temporarily duplicate a position even when the final state is valid.

A transaction can defer validation:

```sql
BEGIN;

SET CONSTRAINTS uq_priority_position DEFERRED;

UPDATE lesson_unique.priority_slots
SET position = CASE
    WHEN slot_id = 1 THEN 20
    WHEN slot_id = 2 THEN 10
END
WHERE slot_id IN (1, 2);

COMMIT;
```

When deferred, intermediate states may temporarily collide, provided the final state satisfies the constraint at check time.

### INITIALLY IMMEDIATE vs. INITIALLY DEFERRED

- `DEFERRABLE INITIALLY IMMEDIATE`: checks immediately by default, yet can switch to deferred within a transaction.
- `DEFERRABLE INITIALLY DEFERRED`: defers validation until transaction end by default unless overridden.
- `NOT DEFERRABLE`: cannot be deferred with `SET CONSTRAINTS`.

### Errors May Surface at COMMIT

If two rows still collide at transaction end, **`COMMIT` fails with `23505`**. Never treat prior successful `UPDATE` statements as proof the transaction will commit.

**Not every constraint supports deferrability identically.** `NOT NULL` and `CHECK` follow different rules; never assume `SET CONSTRAINTS ALL DEFERRED` postpones every PostgreSQL check.

## 23. DEFERRABLE Differs from Directly Created Unique Indexes

`CREATE UNIQUE INDEX` builds index-level uniqueness enforcement. It **does not create a deferrable unique constraint**.

When you need to switch between immediate and deferred mode:

```sql
CONSTRAINT uq_priority_position
UNIQUE (position)
DEFERRABLE
```

rather than merely:

```sql
CREATE UNIQUE INDEX ...
ON ... (position);
```

### DEFERRABLE and ON CONFLICT

A critical restriction: **deferrable unique constraints cannot serve as arbiters for `INSERT ... ON CONFLICT DO UPDATE`**. PostgreSQL requires immediate conflict arbitration semantics.

Therefore, if your workload relies heavily on UPSERTs on `(tenant_id, external_id)`, a **`NOT DEFERRABLE`** unique constraint is generally needed.

Never add `DEFERRABLE` simply because it sounds “more flexible,” only to discover UPSERT fails.

## 24. ALTER TABLE ADD CONSTRAINT and Existing Data Checks

A table containing duplicate rows cannot simply “attach a unique constraint” while leaving violations intact.

```sql
ALTER TABLE lesson_unique.accounts
ADD CONSTRAINT uq_accounts_email_global
UNIQUE (email);
```

This fails against our sample dataset because `an@example.test` exists in both tenant 10 and tenant 20. PostgreSQL scans the data, detects the conflict, and aborts constraint creation.

### Principle

Before adding a constraint:

1. Confirm the exact business key.
2. Audit existing duplicates under the exact `NULL`/normalization semantics.
3. Choose surviving canonical records if deduplicating.
4. Inspect impacted foreign keys, audit logs, and references.
5. Plan locking and index build duration.
6. Add the constraint only once existing rows comply.

### Do Not Treat NOT VALID as a General Workaround for UNIQUE

PostgreSQL supports `NOT VALID` for constraints like foreign keys and `CHECK`, yet you cannot use `ADD CONSTRAINT ... UNIQUE NOT VALID` to bypass validating existing rows.

For large tables, the common online rollout technique is **building a unique index concurrently and then attaching it as a constraint** once valid.

## 25. CREATE UNIQUE INDEX CONCURRENTLY

When a table is large and actively taking traffic, standard index creation can block concurrent writes heavily. PostgreSQL offers:

```sql
CREATE UNIQUE INDEX CONCURRENTLY ux_accounts_tenant_email_new
ON lesson_unique.accounts (tenant_id, email);
```

This is a **syntax illustration**; there is no need to create a duplicate of the constraint already present in the lab.

### Benefits

`CREATE INDEX CONCURRENTLY` reduces blocking of concurrent `INSERT`/`UPDATE`/`DELETE` operations compared to standard index builds by building and validating across multiple phases.

### Caveats

- **Cannot run inside an explicit transaction block** (`BEGIN ... COMMIT`).
- Takes longer and consumes significant I/O and CPU.
- Can still **fail** if existing duplicates exist or concurrent writers introduce a conflict mid-build.
- During phases of a concurrent unique build, uniqueness checks can begin rejecting conflicting writes in other transactions **before the index becomes fully valid**.
- A failed build can leave an **`INVALID`** index requiring controlled investigation and cleanup.

**`CONCURRENTLY` does not mean “lock-free” or “risk-free.”** It still coordinates with concurrent transactions and waits on active snapshots across phases.

## 26. Attaching a Unique Index as a Constraint

Once a valid qualifying unique index is built:

```sql
-- Migration example on a table lacking the constraint:
CREATE UNIQUE INDEX CONCURRENTLY ux_future_unique_key
ON some_schema.some_table (tenant_id, business_key);

ALTER TABLE some_schema.some_table
ADD CONSTRAINT uq_future_unique_key
UNIQUE USING INDEX ux_future_unique_key;
```

This is a **migration pattern**; `some_schema.some_table` is not created in the lab.

Conceptual workflow:

1. Table has zero duplicate keys.
2. Build the unique index `CONCURRENTLY` outside a transaction block.
3. Verify the index completed **successfully and is valid**.
4. Attach it with `ALTER TABLE ... ADD CONSTRAINT ... USING INDEX`.

### Key Prerequisites

The index being attached must satisfy PostgreSQL's rules—typically a **valid unique B-tree index** on plain table columns (not a partial or expression index). Ordering/attribute rules are also verified.

If attaching as a `PRIMARY KEY`, every key column must already be `NOT NULL`, which may require setting `NOT NULL` safely beforehand.

### ALTER TABLE Still Acquires Locks

Even after building the index concurrently, `ALTER TABLE ... ADD CONSTRAINT ... USING INDEX` acquires a strong metadata lock briefly. Deploy within safe maintenance windows with `lock_timeout` and retry controls per operational policy.

## 27. INVALID Indexes After a Failed CREATE INDEX CONCURRENTLY

A concurrent build can fail due to:

- Pre-existing duplicates.
- Concurrent writers inserting duplicates during build.
- Deadlocks, cancellations, resource limits, or operational interrupts.

Catalog query to inspect state:

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS index_name,
    i.indisunique,
    i.indisvalid,
    i.indisready
FROM pg_catalog.pg_index AS i
JOIN pg_catalog.pg_class AS c
  ON c.oid = i.indexrelid
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'lesson_unique'
ORDER BY c.relname;
```

Specifically:

- `indisvalid = false`: the planner generally will not use the index for queries.
- `indisready`: indicates whether the index is ready to receive writes per catalog state.
- An `INVALID` unique index can sometimes **still incur write overhead or uniqueness checks** depending on failure phase—never assume `INVALID` means completely harmless.

### Recovery Plan

1. Inspect the build error message and catalog flags.
2. Locate existing duplicates and the concurrent writer source.
3. Once approved, drop the broken index safely:

```sql
DROP INDEX CONCURRENTLY IF EXISTS
    lesson_unique.ux_failed_build_example;
```

This is **illustrative syntax**; never run it without confirming the exact index and dependencies. `DROP INDEX CONCURRENTLY` also cannot run in a transaction block and cannot directly drop constraint-backing indexes.

4. Clean duplicate rows and fix ingestion.
5. Re-run the index build via your migration process.

Never rely on `IF NOT EXISTS` to guarantee an existing index matches your intended definition: an identically named `INVALID` or misconfigured index still requires explicit inspection.

## 28. Using UNIQUE as an Arbiter in ON CONFLICT

`INSERT ... ON CONFLICT` lets you specify how inserts behave when encountering an existing unique key.

Example **ignoring conflicts**:

```sql
INSERT INTO lesson_unique.accounts(
    tenant_id, email, display_name
)
VALUES (10, 'an@example.test', 'An re-submitting')
ON CONFLICT (tenant_id, email)
DO NOTHING
RETURNING account_id;
```

Because `(10, 'an@example.test')` already exists, no new row is inserted and `RETURNING` returns **0 rows**.

### DO NOTHING Does Not Return Existing Rows

If the caller wants the ID of the already existing record, `DO NOTHING RETURNING` does not return it. Applications need a follow-up lookup query or a carefully designed business-appropriate UPSERT accounting for concurrency and snapshots.

### DO UPDATE

```sql
INSERT INTO lesson_unique.accounts AS a (
    tenant_id, email, display_name
)
VALUES (10, 'an@example.test', 'Updated Display Name')
ON CONFLICT (tenant_id, email)
DO UPDATE SET
    display_name = EXCLUDED.display_name
RETURNING a.account_id, a.display_name;
```

`EXCLUDED` represents the proposed row from `INSERT`, used to compute new values inside `DO UPDATE`.

**Not every workflow should overwrite on conflict.** On signup endpoints, two requests with the same email should normally reject with “already exists” rather than overwriting the existing user's display name.

## 29. ON CONFLICT ON CONSTRAINT

With a **named constraint**, you can write:

```sql
INSERT INTO lesson_unique.accounts(
    tenant_id, email, display_name
)
VALUES (10, 'an@example.test', 'An signing up again')
ON CONFLICT ON CONSTRAINT uq_accounts_tenant_email
DO NOTHING;
```

This explicitly names the **unique constraint** used for conflict arbitration.

### An Index Name Is Not a Constraint Name

If you create:

```sql
CREATE UNIQUE INDEX ux_members_active_email
ON lesson_unique.members (tenant_id, email)
WHERE deleted_at IS NULL;
```

`ux_members_active_email` is an **index**, not a named `UNIQUE` constraint selectable via `ON CONSTRAINT ux_members_active_email`.

For index-based inference, specify the matching column/expression list and predicate.

### ON CONFLICT DO NOTHING Can Omit the Target

```sql
INSERT INTO lesson_unique.accounts(
    tenant_id, email, display_name
)
VALUES (10, 'an@example.test', 'Another An')
ON CONFLICT DO NOTHING;
```

Omitting the target is valid for `DO NOTHING`, yet use caution: it **silently ignores conflicts on any unique index/constraint** rather than only the intended business conflict. Prefer explicit conflict targets for clarity and safety.

## 30. ON CONFLICT with NULLS NOT DISTINCT

Against `refs_strict`:

```sql
INSERT INTO lesson_unique.refs_strict(
    ref_id, tenant_id, external_ref
)
VALUES (7, 10, NULL)
ON CONFLICT (tenant_id, external_ref)
DO NOTHING
RETURNING ref_id;
```

Because `(10, NULL)` already exists under `NULLS NOT DISTINCT`, the statement detects a conflict and skips insertion.

If the table only has default `UNIQUE`:

```sql
INSERT INTO lesson_unique.refs_default(
    ref_id, tenant_id, external_ref
)
VALUES (7, 10, NULL)
ON CONFLICT (tenant_id, external_ref)
DO NOTHING
RETURNING ref_id;
```

then **there is no conflict on `(10, NULL)`**, so the insert succeeds provided `ref_id` is unused.

### Takeaway

`ON CONFLICT` behavior with nulls depends entirely on the **arbiter index's null semantics**. Never write “insert if absent” code without verifying whether the arbiter uses `NULLS DISTINCT` or `NULLS NOT DISTINCT`.

## 31. ON CONFLICT with Partial Unique Indexes

Using `lesson_unique.members`:

```sql
CREATE UNIQUE INDEX ux_members_active_email
ON lesson_unique.members (tenant_id, email)
WHERE deleted_at IS NULL;
```

When inserting an active member:

```sql
INSERT INTO lesson_unique.members(
    member_id, tenant_id, email, display_name, deleted_at
)
VALUES (6, 10, 'an@example.test', 'An re-registering', NULL)
ON CONFLICT (tenant_id, email)
WHERE deleted_at IS NULL
DO NOTHING
RETURNING member_id;
```

The clause:

```sql
ON CONFLICT (tenant_id, email)
WHERE deleted_at IS NULL
```

lets PostgreSQL **infer** the matching partial index when keys and predicate match under supported rules.

### Do Not Confuse the Two WHERE Positions

The `WHERE` right after the conflict target **infers a partial index**:

```sql
ON CONFLICT (tenant_id, email)
WHERE deleted_at IS NULL
```

Whereas the `WHERE` after `DO UPDATE SET` conditionally filters whether the `UPDATE` executes on the conflicting target row:

```sql
ON CONFLICT (...) DO UPDATE
SET ...
WHERE <condition_for_update>
```

These are **two completely separate clauses**. Index inference predicates do not filter the incoming `INSERT` rows.

### Protect Keys on Status Transitions via UPDATE

Updating a row from `deleted_at IS NOT NULL` back to `NULL` **moves it into the active subset**. The partial unique index enforces uniqueness on that `UPDATE` too—uniqueness is not an `INSERT`-only check.

## 32. ON CONFLICT with Expression Unique Indexes

Against `members_normalized`:

```sql
CREATE UNIQUE INDEX ux_members_normalized_active
ON lesson_unique.members_normalized (
    tenant_id, lower(btrim(email))
)
WHERE deleted_at IS NULL;
```

A conflict target can infer the corresponding expression and predicate:

```sql
INSERT INTO lesson_unique.members_normalized(
    member_id, tenant_id, email, display_name, deleted_at
)
VALUES
    (1, 10, 'An@Example.Test', 'An', NULL)
ON CONFLICT (
    tenant_id,
    (lower(btrim(email)))
)
WHERE deleted_at IS NULL
DO NOTHING;
```

Parentheses around the expression in the conflict target denote an **index expression**. Inference depends on matching the exact expression, column set, and predicate per PostgreSQL's rules.

### When Logic Gets Complex

If key normalization involves multiple transformations and UPSERTs happen in many queries, consider:

- Maintaining a dedicated canonical column reliably in application logic.
- Using a **stored generated column** and placing `UNIQUE` on that column.
- Using a named unique constraint when no `WHERE` predicate is required.

Avoid duplicating slightly divergent normalization expressions across multiple write paths.

## 33. Partial Unique Indexes and the Query Planner

A partial index covers only rows matching its predicate. It can enforce uniqueness while simultaneously accelerating matching queries.

Example:

```sql
EXPLAIN
SELECT member_id, display_name
FROM lesson_unique.members
WHERE tenant_id = 10
  AND email = 'an@example.test'
  AND deleted_at IS NULL;
```

Because the query contains `deleted_at IS NULL`, PostgreSQL can match the partial index predicate.

However, if a query **cannot prove** it touches only rows inside the predicate:

```sql
SELECT *
FROM lesson_unique.members
WHERE tenant_id = 10
  AND email = 'an@example.test';
```

an active-only partial index **excludes deleted rows**, so it cannot serve a query expecting all rows.

### Prepared Statements and Parameters

Whether the planner proves a query implies a partial index predicate depends on expressions and plan generation. Generic parameterized predicates like `status = $1` cannot generally prove `status = 'ACTIVE'` across reusable plans.

**Never assume every query hits a partial index.** Check `EXPLAIN` with actual queries and parameter styles.

## 34. UNIQUE and NULL Across Collations and Types

A unique B-tree index does not always compare raw text bytes directly. **Operator classes and collations** define key equality and ordering.

Examples:

- Deterministic `text` collations typically treat `'A'` and `'a'` as distinct.
- `citext` applies case-insensitive comparison semantics.
- `lower(email)` collapses different casing into matching index keys when results match.
- Nondeterministic collations can treat distinct byte strings as equal per collation rules.

### Why Do Collation Upgrades Matter?

When system collation/ICU libraries change versions or rules, text ordering and equality can shift. Plan inspection and reindex procedures per PostgreSQL upgrade guidelines—do not ignore collation dependencies after initial DDL deployment.

### Do Not Use UNIQUE as Format Validation

A unique email value could still be:

```text
not-an-email
```

`UNIQUE` answers **“does this key collide?”**, not **“is this string validly formatted?”**. Format checks belong in `CHECK` constraints or application validation.

## 35. Unique Indexes and Concurrency

A unique index must handle in-flight uncommitted transactions when two requests insert the same key concurrently.

```text
Session A                                Session B
----------------------------------       ----------------------------------
BEGIN;
INSERT key=('tenant10','A');
-- not yet COMMITted
                                        INSERT key=('tenant10','A');
                                        -- may WAIT on A
COMMIT;
                                        -- typically fails with 23505
```

If Session A executes **`ROLLBACK`** instead of `COMMIT`, Session B is allowed to insert the key.

### Uniqueness Visibility Goes Beyond SELECT Snapshots

Under `READ COMMITTED`, Session B's `SELECT` cannot see Session A's uncommitted row. Yet the unique index must enforce **global uniqueness**, forcing Session B to wait for Session A's transaction outcome.

That coordination between index enforcement and transaction status is precisely why constraints prevent races that unsynchronized pre-insert `SELECT` checks miss.

### MVCC Does Not Make Uniqueness Snapshot-Scoped

A unique constraint never means “unique only within my snapshot.” If it did, two concurrent transactions could commit conflicting rows. PostgreSQL detects conflicts even across rows invisible to normal snapshots.

## 36. Two-Session Concurrency Lab

Create a dedicated table:

```sql
CREATE TABLE lesson_unique.concurrent_keys (
    row_id BIGINT PRIMARY KEY,
    business_key TEXT NOT NULL UNIQUE
);
```

**Session A:**

```sql
BEGIN;

INSERT INTO lesson_unique.concurrent_keys(
    row_id, business_key
)
VALUES (1, 'KEY-X');

-- Leave transaction open.
```

**Session B:**

```sql
BEGIN;

SELECT *
FROM lesson_unique.concurrent_keys
WHERE business_key = 'KEY-X';
-- Does not see A's uncommitted row.

INSERT INTO lesson_unique.concurrent_keys(
    row_id, business_key
)
VALUES (2, 'KEY-X');
-- Blocks waiting on Session A.
```

**Session A:**

```sql
COMMIT;
```

**Session B:** receives `23505`. Since B is inside an explicit aborted transaction:

```sql
ROLLBACK;
```

Repeat the experiment with Session A calling `ROLLBACK` instead of `COMMIT` (on clean lab data) to watch Session B succeed.

### Checking pg_locks While B Waits

From a monitoring session:

```sql
SELECT
    a.pid,
    a.wait_event_type,
    a.wait_event,
    pg_catalog.pg_blocking_pids(a.pid) AS blockers
FROM pg_catalog.pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.wait_event_type = 'Lock';
```

Unique key contention may appear as waiting on a transaction ID. Use this for diagnosis rather than treating one specific lock wait pattern as universal.

## 37. Handling Unique Violations Properly in Application Code

When a duplicate insert fails:

```text
SQLSTATE 23505
unique_violation
```

Applications should classify it properly:

1. If conflict is an **expected domain outcome**, map to HTTP 409 / “already exists” or design an `ON CONFLICT` flow.
2. If conflict indicates an **upstream pipeline bug**, log and investigate the duplicate source.
3. Inside an explicit transaction, the error aborts the transaction—roll back cleanly.
4. In generic retry middleware, **never infinitely retry `23505`**; retrying with an unchanged key only generates wasted load.
5. In an UPSERT targeting one unique index, colliding with **a different unique index** still throws an error.

### SQLSTATE vs. Error Message Parsing

Avoid brittle checks like:

```java
if (e.getMessage().contains("duplicate key")) { ... }
```

Error messages vary by locale and PostgreSQL version. Inspect `SQLException.getSQLState()` and driver-provided constraint/index metadata when distinguishing specific constraints.

**Never leak raw database `DETAIL` messages directly to end users** if they expose emails, business keys, or internal schema details.

## 38. Foreign Keys Require an Eligible Referenced Key

A foreign key must reference columns backed by PostgreSQL-eligible uniqueness enforcement.

Example:

```sql
CREATE TABLE lesson_unique.tenants (
    tenant_id BIGINT PRIMARY KEY,
    tenant_name TEXT NOT NULL UNIQUE
);

CREATE TABLE lesson_unique.tenant_profiles (
    profile_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL
        REFERENCES lesson_unique.tenants(tenant_id),
    profile_name TEXT NOT NULL
);
```

Primary keys are natural referenced targets.

Additionally, FK targets may be columns covered by a **non-deferrable unique/primary key constraint** or a qualifying **non-partial unique index** on plain columns per PostgreSQL rules. Partial or expression unique indexes cannot arbitrarily act as FK targets.

### Why Cannot a Partial Unique Index Serve as an FK Target?

A partial unique index enforces uniqueness only over a **subset** of rows. Foreign keys need a well-defined stable reference across all matching target rows. An index scoped to `WHERE deleted_at IS NULL` does not establish a general FK target.

### NULLs in Foreign Keys Are a Separate Topic

Foreign keys have their own `MATCH` and null-handling rules on the referencing side. Never conflate FK null behavior with `UNIQUE NULLS NOT DISTINCT` on the target table; configure `MATCH`, `NOT NULL`, and target keys intentionally.

## 39. Unique Constraints on Partitioned Tables

For **declarative partitioned tables**, PostgreSQL enforces an important rule on primary key and unique constraints: the unique key on the parent table must typically **include all partition key columns** (within version-supported rules). Because uniqueness is physically enforced via per-partition indexes, PostgreSQL must be able to guarantee duplicate keys cannot land in separate partitions.

Example partitioned by tenant:

```sql
CREATE TABLE lesson_unique.partitioned_events (
    tenant_id INTEGER NOT NULL,
    event_id BIGINT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (tenant_id, event_id)
) PARTITION BY LIST (tenant_id);

CREATE TABLE lesson_unique.partitioned_events_t10
PARTITION OF lesson_unique.partitioned_events
FOR VALUES IN (10);

CREATE TABLE lesson_unique.partitioned_events_t20
PARTITION OF lesson_unique.partitioned_events
FOR VALUES IN (20);
```

The primary key `(tenant_id, event_id)` includes the partition key `tenant_id`.

### Why Is Standalone UNIQUE(event_id) Disallowed?

If separate partitions could independently accept the same `event_id` while each checks only its local index, global uniqueness across the parent cannot be guaranteed.

If business logic demands `event_id` be unique **across all tenants**, you need an appropriate architecture (coordinated global ID allocation, a dedicated registry/lookup table with a unique key, or another strategy). Never assume a partitioned parent supports arbitrary cross-partition global unique indexes like an unpartitioned table.

### Partitioning and Unique NULLs

`NULLS NOT DISTINCT` still operates within valid partition-key/unique-key constraints and does not bypass cross-partition uniqueness limits.

## 40. Inspecting UNIQUE Metadata in Catalogs

Useful PostgreSQL catalogs:

- `pg_constraint`: describes constraints, constraint types, deferrability flags, and supporting indexes.
- `pg_index`: tracks unique flags, valid/ready status, and null semantics.
- `pg_class`: stores table and index names.
- `pg_namespace`: schemas.
- `pg_indexes`: view showing index definitions per schema.

### Listing Constraints

```sql
SELECT
    n.nspname AS schema_name,
    t.relname AS table_name,
    c.conname AS constraint_name,
    c.contype AS constraint_type,
    c.condeferrable,
    c.condeferred,
    pg_catalog.pg_get_constraintdef(c.oid) AS definition
FROM pg_catalog.pg_constraint AS c
JOIN pg_catalog.pg_class AS t
  ON t.oid = c.conrelid
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = t.relnamespace
WHERE n.nspname = 'lesson_unique'
  AND c.contype IN ('p', 'u')
ORDER BY t.relname, c.conname;
```

Legend:

- `contype = 'p'`: primary key.
- `contype = 'u'`: unique constraint.
- `condeferrable`: whether the constraint can be deferred.
- `condeferred`: whether the constraint starts initially deferred.

### Listing Index Definitions

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname = 'lesson_unique'
ORDER BY tablename, indexname;
```

This displays **directly created unique indexes as well**—such as partial or expression unique indexes lacking a matching `pg_constraint` row.

## 41. Inspecting indnullsnotdistinct in PostgreSQL 15+

In PostgreSQL 15 and newer, `pg_index` exposes:

```sql
SELECT
    tbl_ns.nspname AS table_schema,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    pi.indisunique,
    pi.indnullsnotdistinct,
    pi.indisvalid,
    pg_catalog.pg_get_indexdef(idx.oid) AS index_definition
FROM pg_catalog.pg_index AS pi
JOIN pg_catalog.pg_class AS idx
  ON idx.oid = pi.indexrelid
JOIN pg_catalog.pg_class AS tbl
  ON tbl.oid = pi.indrelid
JOIN pg_catalog.pg_namespace AS tbl_ns
  ON tbl_ns.oid = tbl.relnamespace
WHERE tbl_ns.nspname = 'lesson_unique'
ORDER BY tbl.relname, idx.relname;
```

- `indisunique`: marks a unique index.
- `indnullsnotdistinct`: indicates nulls are treated as non-distinct for uniqueness.
- `indisvalid`: index validity status.

**Do not query `indnullsnotdistinct` on PostgreSQL versions older than 15**, as the column does not exist there and fails with `undefined_column`. Gate version-specific queries using `server_version_num`.

### Catalogs Are Not Long-Term ORM Contracts

Admin scripts may inspect system catalogs directly, yet migrations and ORMs must account for PostgreSQL version differences. Do not query newly added catalog columns unconditionally if your product still supports older servers.

## 42. information_schema.table_constraints

For portable SQL queries across tools, `information_schema` provides:

```sql
SELECT
    table_schema,
    table_name,
    constraint_name,
    constraint_type,
    is_deferrable,
    initially_deferred
FROM information_schema.table_constraints
WHERE table_schema = 'lesson_unique'
ORDER BY table_name, constraint_name;
```

It lists table constraints nicely, yet **does not replace `pg_indexes`** when inspecting directly created partial or expression unique indexes.

### psql Meta-Commands

Inside `psql`:

```text
\d lesson_unique.accounts
\d lesson_unique.members
\di lesson_unique.*
```

These are **`psql` meta-commands**, not SQL statements sent over JDBC.

## 43. Finding Duplicates Before Creating UNIQUE

Suppose a staging table records repeated deliveries of the same business key:

```sql
CREATE TABLE lesson_unique.raw_contacts (
    contact_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    external_key TEXT,
    received_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);

INSERT INTO lesson_unique.raw_contacts(
    contact_id, tenant_id, external_key,
    received_at, payload
)
VALUES
    (1, 10, 'A', TIMESTAMPTZ '2026-11-10 09:00:00+07',
        '{"v":1}'::jsonb),
    (2, 10, 'A', TIMESTAMPTZ '2026-11-11 09:00:00+07',
        '{"v":2}'::jsonb),
    (3, 10, NULL, TIMESTAMPTZ '2026-11-11 10:00:00+07',
        '{"v":1}'::jsonb),
    (4, 10, NULL, TIMESTAMPTZ '2026-11-12 10:00:00+07',
        '{"v":2}'::jsonb),
    (5, 20, 'A', TIMESTAMPTZ '2026-11-12 11:00:00+07',
        '{"v":1}'::jsonb);
```

### Counting Duplicates Under NULLS NOT DISTINCT Semantics

```sql
SELECT
    tenant_id,
    external_key,
    COUNT(*) AS row_count
FROM lesson_unique.raw_contacts
GROUP BY tenant_id, external_key
HAVING COUNT(*) > 1
ORDER BY tenant_id, external_key NULLS FIRST;
```

Output for tenant 10 shows:

- `(10, 'A')`: 2 rows.
- `(10, NULL)`: 2 rows.

**Subtle nuance:** `GROUP BY` coalesces `NULL`s into one group. This query fits when preparing to add **`UNIQUE NULLS NOT DISTINCT`**. If you plan to add a **default `UNIQUE`**, group `(10, NULL)` is **not a uniqueness violation** even though `GROUP BY` reported `COUNT(*) > 1`.

### Match Your Policy Before Deleting

Never delete every `COUNT(*) > 1` group blindly when the target constraint permits multiple nulls carrying distinct valid records. Your duplicate-detection query must match the **target invariant**, not just `GROUP BY` defaults.

## 44. Selecting Surviving Records with ROW_NUMBER

If business rules keep one row per `(tenant_id, external_key)` preferring the **most recent `received_at`**:

```sql
WITH ranked AS (
    SELECT
        c.*,
        ROW_NUMBER() OVER (
            PARTITION BY c.tenant_id, c.external_key
            ORDER BY
                c.received_at DESC,
                c.contact_id DESC
        ) AS rn
    FROM lesson_unique.raw_contacts AS c
)
SELECT
    tenant_id,
    external_key,
    contact_id,
    received_at,
    rn
FROM ranked
ORDER BY tenant_id, external_key NULLS FIRST, rn;
```

In this example:

- `(10, 'A')`: keeps contact 2.
- `(10, NULL)`: keeps contact 4 **if `NULL` is treated as a single unique key**.
- `(20, 'A')`: keeps contact 5.

### Do Not Pick Tie-Breakers Arbitrarily

When two rows share `received_at`, `contact_id DESC` makes selection deterministic. Yet a larger ID does not automatically guarantee the **newest upstream payload**. If an authoritative `source_version` exists, sort by it first.

### NULL in PARTITION BY

`PARTITION BY (tenant_id, external_key)` groups null keys in the same tenant into one partition, just like `GROUP BY`. Keep this in mind when using window functions to prepare for `NULLS NOT DISTINCT`.

## 45. Previewing Rows Before Deletion

First run a **read-only `SELECT`**:

```sql
WITH ranked AS (
    SELECT
        c.contact_id,
        c.tenant_id,
        c.external_key,
        c.received_at,
        ROW_NUMBER() OVER (
            PARTITION BY c.tenant_id, c.external_key
            ORDER BY
                c.received_at DESC,
                c.contact_id DESC
        ) AS rn
    FROM lesson_unique.raw_contacts AS c
)
SELECT *
FROM ranked
WHERE rn > 1
ORDER BY tenant_id, external_key NULLS FIRST, rn;
```

In the lab, this selects contact 1 and contact 3 as redundant rows **under the policy keeping at most one null per tenant**.

Before actually deleting, verify:

- The colliding rows represent the same entity, not distinct valid historical events.
- You have identified the authoritative winner.
- Whether foreign keys reference the rows to be deleted.
- Whether rows must be archived or audited before deletion.
- Whether concurrent writers are still inserting conflicting keys.
- Whether backups/rollback or repair procedures exist if anything goes wrong.

## 46. Deleting Duplicates Inside a Lab Transaction

Cleanup pattern:

```sql
BEGIN;

WITH ranked AS (
    SELECT
        c.contact_id,
        ROW_NUMBER() OVER (
            PARTITION BY c.tenant_id, c.external_key
            ORDER BY
                c.received_at DESC,
                c.contact_id DESC
        ) AS rn
    FROM lesson_unique.raw_contacts AS c
)
DELETE FROM lesson_unique.raw_contacts AS c
USING ranked AS r
WHERE c.contact_id = r.contact_id
  AND r.rn > 1
RETURNING
    c.contact_id,
    c.tenant_id,
    c.external_key;

-- Learning demo only; revert deletion:
ROLLBACK;
```

In production pipelines, avoid deleting straight from **raw** tables unnecessarily: many architectures retain all deliveries for audit/replay and materialize deduplicated canonical records into a separate `UNIQUE`-protected table. On canonical tables, coordinate cleanup and constraint/index deployment so duplicates cannot re-enter mid-migration.

### Why Delete by Primary Key?

`contact_id` identifies each exact row unambiguously in `DELETE`. Joining solely on `(tenant_id, external_key)` risks deleting **the surviving row as well**.

## 47. Adding the Constraint After Cleanup

Conceptually, once data satisfies `NULLS NOT DISTINCT`:

```sql
ALTER TABLE lesson_unique.raw_contacts
ADD CONSTRAINT uq_raw_contacts_tenant_external
UNIQUE NULLS NOT DISTINCT (tenant_id, external_key);
```

**This statement fails if run immediately after Section 46**, because the demo cleanup ended with `ROLLBACK` and duplicates remain. To test success in the **lab**, commit an actual cleanup and re-verify zero duplicates before adding the constraint.

### Cleanup Alone Still Leaves Writers Unchecked

If writers remain active between cleanup and index creation, duplicates can reappear. Decide how to:

- Pause or coordinate ingestion.
- Make writes idempotent before migration.
- Use concurrent unique index builds appropriately.
- Handle errors/retries if a unique build encounters mid-flight conflicts.

“One-time duplicate cleanup” alone never guarantees long-term uniqueness.

## 48. UNIQUE on Canonical Data vs. Raw Data

A clean pipeline architecture:

```text
API / Message Queue Source
         │
         ▼
raw_contacts
  - append-only
  - each delivery gets its own contact_id
  - allows repeated business keys for audit
         │
         │ normalize + deduplicate
         ▼
canonical_contacts
  - UNIQUE (tenant_id, external_key)
  - or UNIQUE NULLS NOT DISTINCT
  - or status-scoped partial unique index
         │
         ▼
Business Apps / Reporting
```

If raw logs intentionally retain redeliveries, slapping a unique constraint onto the raw table destroys audit visibility. Distinguish **“canonical entity unique key”** from **“physical delivery identifier.”**

Queues routinely retry deliveries. Use unique business/idempotency keys on canonical tables to prevent duplicate side effects rather than blindly erasing raw logs.

## 49. An Idempotent UPSERT for Canonical Tables

Example:

```sql
CREATE TABLE lesson_unique.canonical_contacts (
    tenant_id BIGINT NOT NULL,
    external_key TEXT NOT NULL,
    source_version BIGINT NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY (tenant_id, external_key)
);
```

UPSERT pattern:

```sql
INSERT INTO lesson_unique.canonical_contacts AS c (
    tenant_id,
    external_key,
    source_version,
    payload
)
VALUES (
    10,
    'A',
    42,
    '{"name":"An"}'::jsonb
)
ON CONFLICT (tenant_id, external_key)
DO UPDATE SET
    source_version = EXCLUDED.source_version,
    payload = EXCLUDED.payload
WHERE EXCLUDED.source_version > c.source_version;
```

Semantics:

- Missing key → insert.
- Existing key and newer version → update.
- Existing key and older/equal version → skip overwrite.

**Do not compare `received_at` when messages can arrive out of order and you want the latest upstream `source_version`.**

### Concurrency

The unique key protects against concurrent worker races. PostgreSQL serializes conflicting updates properly instead of letting two workers `SELECT` nothing and both insert duplicates.

### NULL external_key

The canonical table above marks `external_key NOT NULL` because it participates in the primary key and represents mandatory identity. Optional business keys require a different model rather than a nullable primary key.

## 50. UNIQUE and Transaction Errors in JDBC

When PostgreSQL returns `23505` inside an explicit transaction, the transaction moves into a failed/aborted state. Issuing further SQL without rolling back returns `25P02`:

```text
INSERT duplicate key → SQLSTATE 23505
Next SELECT          → SQLSTATE 25P02
ROLLBACK             → session returns to valid state
```

### Error Classification Example

```java
try {
    preparedStatement.executeUpdate();
} catch (SQLException e) {
    String state = e.getSQLState();
    if ("23505".equals(state)) {
        // Unique violation: map to an appropriate domain conflict.
    } else if ("23502".equals(state)) {
        // NOT NULL violation.
    } else if ("23514".equals(state)) {
        // CHECK violation.
    }
    throw e;
}
```

This snippet assumes a valid `preparedStatement` and passes exceptions to the transaction owner for rollback.

### JDBC Transaction Pattern

```java
try (Connection conn = dataSource.getConnection()) {
    conn.setAutoCommit(false);

    try {
        String sql = """
            INSERT INTO lesson_unique.accounts(
                tenant_id, email, display_name
            )
            VALUES (?, ?, ?)
            """;

        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setLong(1, 10L);
            ps.setString(2, "an@example.test");
            ps.setString(3, "Display Name");
            ps.executeUpdate();
        }

        conn.commit();
    } catch (SQLException | RuntimeException failure) {
        try {
            conn.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
```

This uses Java text blocks and assumes `DataSource`, imports, and a method throwing `SQLException`. Inside Spring/JPA, let the framework's transaction manager handle rollbacks rather than manipulating framework-managed JDBC connections directly.

### pgJDBC Error Details

With the PostgreSQL driver, exceptions carry structured metadata such as constraint name, schema/table, and detail. When distinguishing a **unique email violation** from a **primary key violation**, inspect structured metadata fields rather than matching English error strings.

**Never return raw database `DETAIL` strings directly to end users** if they expose emails, business keys, or internal system details.

## 51. Spring and Managing UNIQUE Constraints

In Spring Data/JPA applications:

- Unique constraints can be defined via schema migrations or ORM schema metadata.
- Unique violations are commonly translated into Spring persistence exceptions such as `DataIntegrityViolationException`.
- Services should identify which conflicts represent **business validation failures** and respond cleanly.
- If a PostgreSQL transaction has failed, **catching the exception and reusing the same transaction** causes `25P02`; roll back or use UPSERT/savepoints intentionally.
- Once ORM flush fails, the persistence context is generally tainted; rolling back and ending the transaction scope is usually safest.

### Never Rely Solely on @Column(unique = true)

Annotations like `@Column(unique = true)` describe metadata for ORM DDL generation, yet in production you must verify via catalogs that migrations actually created the constraint. Without a server-side constraint, Java annotations cannot stop concurrent services from racing.

### API Idempotency

An order creation endpoint needs an idempotency key for safe retries:

```text
POST /orders
Idempotency-Key: req-123
```

Database uniqueness per merchant/tenant lets retries fail or coordinate cleanly, yet you still must persist request outcome, status, and response replay logic; **a unique constraint alone does not implement a full idempotency protocol**.

## 52. Performance Characteristics of Unique Indexes

A unique index enforces data integrity while also accelerating matching lookups:

```sql
SELECT account_id
FROM lesson_unique.accounts
WHERE tenant_id = 10
  AND email = 'an@example.test';
```

The index backing `uq_accounts_tenant_email` can be used by the optimizer for this lookup.

### Associated Costs

- Every insert checks uniqueness rules against the index.
- Updating key columns checks and maintains the index.
- Indexes consume disk space/buffer cache and produce WAL.
- Tables with more indexes absorb slower writes, especially under heavy `UPDATE`s.
- “Hot” keys contested by concurrent writers can introduce wait contention.

### Unique Indexes Do Not Force Index Usage

On tiny tables, sequential scans can win. When queries lack compatible predicates, the planner skips the index.

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT account_id
FROM lesson_unique.accounts
WHERE tenant_id = 10
  AND email = 'an@example.test';
```

`EXPLAIN ANALYZE` **actually executes the statement**. Safe here on a `SELECT`; for `DELETE`/`UPDATE`, account for side effects and wrap in rollback transactions when testing.

## 53. UNIQUE Does Not Mean “One Row per Tenant”

The constraint:

```sql
UNIQUE (tenant_id, email)
```

places no limit on **account count per tenant**—a tenant may hold millions of distinct emails. If the real rule is **at most one primary owner** per tenant, define a separate invariant.

Example:

```sql
CREATE TABLE lesson_unique.tenant_memberships (
    membership_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    role_name TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE UNIQUE INDEX ux_one_active_owner_per_tenant
ON lesson_unique.tenant_memberships (tenant_id)
WHERE role_name = 'OWNER'
  AND active;
```

This index allows:

- Multiple users and non-owner roles within a tenant.
- At most **one active `OWNER` row** per tenant.
- Inactive owners excluded from the conflict check.

### Predicates Must Match Real Business Rules

If the system permits multiple simultaneous co-owners, the index above is **wrong**. Verify exact domain rules before creating partial unique indexes—the database enforces what you declare, not unstated product assumptions.

## 54. UNIQUE and Time-Based Partitioning

Another scenario: an event table partitioned monthly where `external_event_id` must be unique **across all history**.

When the partition key is the event month and the business key is solely `external_event_id`, PostgreSQL cannot directly enforce cross-partition global uniqueness on the partitioned parent under the declarative partitioning rules noted earlier.

One architectural option:

```text
event_keys
  UNIQUE (tenant_id, external_event_id)
  └── system-wide key registry

events_2026_11
events_2026_12
...
  └── partitioned payload tables
```

However, the registry must update **within the same transactional protocol** so keys cannot exist without events or vice versa. That is an architectural trade-off, not a free index trick.

Sometimes the true invariant only requires uniqueness per **tenant and month**, in which case a unique key containing the partition key models it directly. Confirm the exact uniqueness scope first.

## 55. UNIQUE, Privileges, and Production DDL

Creating constraints and indexes requires appropriate table owner/schema privileges. When running migrations:

1. Use an appropriately privileged migration role.
2. Check active transactions holding conflicting table locks.
3. Distinguish `CREATE INDEX` from `CREATE INDEX CONCURRENTLY`.
4. Verify the created index matches intended predicates, expressions, and null semantics.
5. Ensure applications handle SQLSTATE `23505` and transaction rollbacks.
6. Avoid duplicate indexes created by overlapping migration/ORM DDL tools.
7. Avoid constraint/index naming collisions within the schema.
8. Monitor write latency and lock contention post-deploy.

### DDL Can Block Applications

Running `ALTER TABLE ... ADD CONSTRAINT UNIQUE` directly on large live tables acquires heavy locks and scans the table. For busy tables, consider building a unique index concurrently first and then attaching it—remembering the attach step itself still takes a brief lock.

**Never deploy directly to production merely because syntax ran instantaneously on a few lab rows.**

## 56. Workflow for Designing Unique Rules from Business Requirements

Answer these questions first:

1. **What must be unique?** Email, SKU, external ID, `(tenant, key)` pair?
2. **What is the scope of uniqueness?** Global, per tenant, per organization, per day, active-only?
3. **Are `NULL`s allowed?** If yes, permit multiple `NULL`s or at most one?
4. **Is normalization required before comparison?** Lowercase, trim, Unicode normalization, collation?
5. **Are soft deletes used?** Should deleted rows participate in uniqueness?
6. **Is `ON CONFLICT` needed?** If so, must the arbiter be non-deferrable and inferable?
7. **Do foreign keys reference it?** Does the key qualify as an FK target?
8. **Is the table partitioned?** Does the unique key include all partition key columns?
9. **Is existing data clean?** How many duplicates or expression/null collisions already exist?
10. **Are concurrent writers active during migration?** How is idempotency maintained?

Map answers to solutions:

| Requirement | Typical Solution |
|---|---|
| Mandatory unique key | `NOT NULL` + `UNIQUE` or `PRIMARY KEY`. |
| Optional key, multiple `NULL`s valid | Default `UNIQUE`. |
| Optional key, at most one `NULL` in scope | `UNIQUE NULLS NOT DISTINCT` (PG15+). |
| Unique only while active | Partial unique index. |
| Unique after normalization | Expression unique index, generated canonical column, or matching type/collation. |
| Unique after normalization while active | Partial expression unique index. |
| Temporary swap transitions needed | `DEFERRABLE UNIQUE` when compatible. |
| UPSERT required | Non-deferrable unique index/constraint with matching conflict target. |
| Large active table | Planned migration, evaluating `CREATE UNIQUE INDEX CONCURRENTLY`. |

## 57. Common Mistakes and Misconceptions

### 57.1. “UNIQUE means only one NULL is allowed”

False under PostgreSQL defaults. To allow at most one null, use `NULLS NOT DISTINCT` on PostgreSQL 15+ or an alternative design.

### 57.2. “NULL = NULL evaluates to true”

False. `NULL = NULL` yields unknown (`NULL`). Use `IS NULL` or `IS NOT DISTINCT FROM` as appropriate.

### 57.3. “UNIQUE(tenant_id, email) makes email globally unique”

False. Different tenants can hold matching emails.

### 57.4. “UNIQUE(tenant_id, email, deleted_at) blocks two active rows”

False for `deleted_at IS NULL` under default rules. Use a partial unique index for active rows, or verify whether `NULLS NOT DISTINCT` truly matches all rules.

### 57.5. “NULLS NOT DISTINCT is identical to NOT NULL”

False. `NULLS NOT DISTINCT` allows one null row on a single-column key; `NOT NULL` allows none.

### 57.6. “Adding id to UNIQUE helps prevent duplicate emails”

Writing `UNIQUE(id, email)` when `id` is already unique stops almost no email duplicates. Key columns must reflect **actual collision attributes**, not blindly include primary keys.

### 57.7. “After adding a UNIQUE constraint, I still need an identical unique index”

Usually false. The constraint already maintains its backing unique index; adding another creates redundant write/storage cost.

### 57.8. “A partial unique index is a constraint and works with ON CONSTRAINT”

False. A partial unique index is not a named table constraint usable with `ON CONSTRAINT`.

### 57.9. “INCLUDE(display_name) adds display_name to the unique check”

False. Included payload columns do not participate in uniqueness enforcement.

### 57.10. “DEFERRABLE UNIQUE is better in every case”

False. It carries semantic/runtime overhead and cannot serve as an arbiter for `ON CONFLICT DO UPDATE`.

### 57.11. “UNIQUE only matters on INSERT, not UPDATE”

False. Updating key columns, resetting `deleted_at` to null, or mutating indexed expressions/predicates can trigger `23505`.

### 57.12. “If SELECT finds nothing, INSERT cannot collide”

False under concurrency. Uncommitted concurrent inserts remain invisible to `SELECT` yet synchronize inside unique enforcement.

### 57.13. “ON CONFLICT DO NOTHING RETURNING returns the existing row”

False. When nothing is inserted, `RETURNING` returns no rows.

### 57.14. “ON CONFLICT handles every constraint failure”

False. It catches only conflicts matching its specified arbiter/target; `NOT NULL`, `CHECK`, FK, or other unique index errors still fail.

### 57.15. “CREATE INDEX CONCURRENTLY never waits”

False. It reduces write blocking, yet still coordinates and waits across build phases and consumes resources.

### 57.16. “An INVALID index is guaranteed completely inert”

False across all concurrent failure phases. Inspect `indisvalid`/`indisready` and clean up failed builds cleanly.

### 57.17. “NOT VALID lets you add UNIQUE onto a table with duplicates”

False; unlike `CHECK`/FK constraints, `UNIQUE` requires a valid backing unique index over existing rows.

### 57.18. “Every GROUP BY COUNT > 1 group is blocked by default UNIQUE”

False for nullable keys: `GROUP BY` collapses nulls together, whereas default `UNIQUE` allows multiple nulls.

### 57.19. “Lowercasing alone properly normalizes all emails”

Not necessarily. Account explicitly for locale, Unicode normalization, collation, and email policies.

### 57.20. “A unique index on a partitioned table is automatically cluster-wide unique”

False. Remember partition-key requirements and declarative partitioning constraints.

### 57.21. “With UNIQUE in place, apps no longer need SQLException handling”

False. Constraints guard integrity, while applications must roll back aborted transactions, handle `23505`, and return clean responses.

### 57.22. “Different constraint/index names mean they are unrelated”

Constraints and backing indexes are linked in catalogs and may be renamed or attached during migrations; check `pg_constraint` and `pg_index` instead of relying on naming guesses.

### 57.23. “INCLUDE guarantees Index Only Scan”

False. Planner choices, visibility maps, and workloads decide; `INCLUDE` only provides the coverage prerequisite.

### 57.24. “Unique email guarantees account security”

False. Uniqueness never replaces authentication, email verification, password hashing, authorization, RLS, or security controls.

## 58. Hands-On Exercises

### Exercise 1 — Single-Column UNIQUE

Create a table with `email TEXT UNIQUE`. Insert duplicate emails and note the SQLSTATE. Why is relying solely on `SELECT` before `INSERT` unsafe?

### Exercise 2 — Two-Column UNIQUE

With `UNIQUE (tenant_id, email)`, insert matching emails in tenant 10 and tenant 20; then insert a duplicate email inside tenant 10. Explain the results.

### Exercise 3 — Default NULL Behavior

Insert two rows with `optional_code = NULL` into `codes_default`. Why do both succeed? What does `NULL = NULL` return?

### Exercise 4 — NULLS NOT DISTINCT

On PostgreSQL 15+, insert two null rows into `codes_strict`. Compare with Exercise 3. Why is it not equivalent to `NOT NULL`?

### Exercise 5 — NULLs in Composite Keys

With `UNIQUE NULLS NOT DISTINCT (tenant_id, external_ref)`, test `(10, NULL)` twice and `(20, NULL)` once. Which inserts succeed?

### Exercise 6 — PostgreSQL Version

Use `server_version_num` to check whether your server supports `NULLS NOT DISTINCT`. If not, propose a scoped partial unique index workaround for a nullable column.

### Exercise 7 — PRIMARY KEY and UNIQUE

Create a table with `id BIGINT PRIMARY KEY`, `email TEXT UNIQUE`, and `nickname TEXT`. Explain which columns forbid nulls, which allow multiple nulls, and why.

### Exercise 8 — Broken Soft Delete

Using `members_wrong` with `UNIQUE (tenant_id, email, deleted_at)`, insert two active rows with null `deleted_at`. Predict whether conflict occurs and explain using default null semantics.

### Exercise 9 — Partial Unique Index for Active Rows

Create `UNIQUE (tenant_id, email) WHERE deleted_at IS NULL`. Test one active and one deleted row sharing an email; then test two active rows. State the enforced invariant.

### Exercise 10 — Restoring a Soft-Deleted Record

A tenant already has an active member with email A and a deleted member with email A. What happens if you update the deleted member's `deleted_at` back to `NULL`? Why do partial unique indexes enforce checks on `UPDATE`?

### Exercise 11 — Expression Index

Create a unique index on `(tenant_id, lower(btrim(email)))`. Test `'An@Example.Test'` and `' an@example.test '`. Explain the normalization rule and its caveats.

### Exercise 12 — Expression + Partial

Design a unique index enforcing case-insensitive uniqueness on active members while allowing duplicate emails among deleted records. Write the complete `CREATE UNIQUE INDEX`.

### Exercise 13 — INCLUDE

Create unique index `(tenant_id, email) INCLUDE (display_name)`. Are two rows with identical keys and different `display_name` values allowed? Why or why not?

### Exercise 14 — DEFERRABLE Swap

Create a table with `UNIQUE (position) DEFERRABLE INITIALLY IMMEDIATE`. Inside a transaction, issue `SET CONSTRAINTS ... DEFERRED` and swap two rows' positions. Compare with `NOT DEFERRABLE`.

### Exercise 15 — Deferred Failure at COMMIT

In the lab, leave two rows colliding at the end of a transaction under a deferred unique constraint. When does the error surface, and how must JDBC handle `COMMIT` failures?

### Exercise 16 — ON CONFLICT DO NOTHING

Attempt to insert an existing key using `ON CONFLICT (tenant_id, email) DO NOTHING RETURNING account_id`. Why does `RETURNING` yield no old ID?

### Exercise 17 — ON CONFLICT DO UPDATE

Write an account UPSERT keyed by `(tenant_id, email)` updating only `display_name` on conflict. Explain why this can be unsuitable for user registration endpoints.

### Exercise 18 — Partial Index Inference

Write `ON CONFLICT (tenant_id, email) WHERE deleted_at IS NULL DO NOTHING` against `members`. Contrast the `WHERE` in conflict target inference with the `WHERE` after `DO UPDATE`.

### Exercise 19 — Expression Index Inference

Write the conflict target for `(tenant_id, lower(btrim(email))) WHERE deleted_at IS NULL`. Why cannot you use `ON CONFLICT ON CONSTRAINT <index_name>`?

### Exercise 20 — Auditing Duplicates with NULLs

On `raw_contacts`, run `GROUP BY tenant_id, external_key HAVING COUNT(*) > 1`. Explain why null groups show up yet default `UNIQUE` would still permit them.

### Exercise 21 — Deduplication Keeping Latest Record

Use `ROW_NUMBER() OVER (PARTITION BY tenant_id, external_key ORDER BY received_at DESC, contact_id DESC)` to keep one row per key. If an upstream `source_version` exists, how should ordering change?

### Exercise 22 — Safe Cleanup

Write a preview `SELECT` for `rn > 1`, then describe `DELETE ... USING` keyed by primary key inside a rolled-back lab transaction. Why avoid deleting raw audit logs directly?

### Exercise 23 — Large-Table Migration

Describe building `CREATE UNIQUE INDEX CONCURRENTLY` to minimize write blocking, checking `indisvalid`, and attaching `UNIQUE USING INDEX` when eligible. Why cannot concurrent builds run inside `BEGIN`?

### Exercise 24 — INVALID Index

Suppose a concurrent unique build fails due to duplicates. Which `pg_index` columns should you inspect and what cleanup steps are needed before retrying?

### Exercise 25 — Foreign Keys

Why can FKs reference eligible primary/unique keys yet cannot target arbitrary partial expression unique indexes as entity keys?

### Exercise 26 — Partitioned Tables

Design a table partitioned by `tenant_id`. Why must primary/unique constraints on the parent normally include the partition key? Propose a way to enforce globally unique `event_id` if required.

### Exercise 27 — Concurrent INSERT

Two sessions insert the same uncommitted `business_key`. Why may one block waiting on the other and then receive `23505` even though its earlier `SELECT` saw nothing?

### Exercise 28 — SQLSTATE and JDBC

Write a `SQLException` handler classifying `23505`, `23502`, and `23514`. Inside manual transactions, why must you roll back before reusing the connection?

### Exercise 29 — Catalog Metadata

Query `pg_constraint` and `pg_indexes` to compare a `UNIQUE` constraint, a partial unique index, and an expression unique index. Why does `information_schema.table_constraints` omit standalone indexes?

### Exercise 30 — End-to-End Design

A multi-tenant platform requires: active members have case-insensitive unique emails per tenant; deleted members stay in history; `external_ref` is optional yet at most one null per tenant; create requests must be idempotent. Propose:

1. Table columns with key `NOT NULL`/`CHECK` constraints.
2. Partial expression unique index for active emails.
3. `UNIQUE NULLS NOT DISTINCT` for `external_ref` scoped per tenant (if semantics align).
4. UPSERT/conflict handling that avoids silently clobbering older records.
5. A migration strategy when historical data already contains duplicates.
6. A test plan covering two concurrent identical requests.

## Conclusion

In PostgreSQL, **`UNIQUE` is not simply a “no duplicates” checkbox on one column**, but an invariant enforced across a **key tuple**, governed by specific rules for **`NULL`s**, expressions, predicates, collations, and transactions. A unique constraint is backed by a unique index; directly created unique indexes further express **partial uniqueness** and **expression-based uniqueness** beyond plain table constraints.

The single most important rule is: **default `UNIQUE` permits multiple `NULL`s**. When requirements demand “at most one `NULL`” or “tuples with matching `NULL` positions collide,” use **`NULLS NOT DISTINCT` in PostgreSQL 15+**. When uniqueness applies only to **active** records, use a **partial unique index with a matching business predicate** rather than appending `deleted_at` blindly to the key. When normalizing emails or codes, adopt expression indexes, generated canonical columns, or consistent collations once comparison rules are settled.

In real deployments, distinguish **`PRIMARY KEY`**, **`NOT NULL`**, **`UNIQUE` constraints**, **partial/expression unique indexes**, and **`DEFERRABLE UNIQUE`**; account for constraints on **`ON CONFLICT`**, **foreign keys**, and **partitioned tables**. Before introducing uniqueness to populated tables, detect duplicates under the **exact target null semantics**, preview deletions carefully, and execute migrations/concurrent builds cleanly. Under concurrency, database unique indexes remain the indispensable safety barrier that `SELECT` before `INSERT` can never replace.

Sound design begins by asking **“what precisely counts as the same business entity?”**, and only then selecting key columns, null handling, tenant/active scoping, and write protocols. Expressing those rules cleanly in PostgreSQL alongside proper `23505` handling keeps data integrity rock-solid even under heavy concurrent writes.
