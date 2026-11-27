# MERGE and Conditional Data Synchronization in PostgreSQL

In systems that import files, sync product catalogs, update order statuses, or process feeds from external services, a single input batch often combines multiple scenarios simultaneously:

- Rows that already exist in the database and need to be **updated**.
- Rows that do not exist yet and need to be **inserted**.
- Rows that already exist with no newer changes and should be **skipped**.
- Rows that already exist yet the source requests to **delete** or **deactivate**.
- In a full snapshot, target rows that no longer appear in the source.

`MERGE` is the SQL statement designed to perform these conditional actions from a single data source and match condition. It is especially helpful when a workflow must synchronize multiple kinds of changes in one statement rather than issuing several independent commands.

Conceptual example:

~~~sql
MERGE INTO products AS t
USING incoming_products AS s
ON t.sku = s.sku
WHEN MATCHED AND s.version > t.version THEN
    UPDATE SET
        product_name = s.product_name,
        price = s.price,
        version = s.version
WHEN NOT MATCHED THEN
    INSERT (sku, product_name, price, version)
    VALUES (s.sku, s.product_name, s.price, s.version);
~~~

In this lesson of the **Data Modification** chapter of the **Database Engine Relational PostgreSQL** module, we cover how to identify matching rows, choose actions, prevent source duplicates, manage transactions and concurrency, compare with UPSERT, and understand differences across PostgreSQL versions.

One principle to keep front and center: **`MERGE` does not replace key design, constraints, access privileges, or data policies**. A syntactically valid `MERGE` using a flawed source or a wrong `ON` condition can still cause data loss.

## 1. Which PostgreSQL Versions Support MERGE?

`MERGE` was introduced in **PostgreSQL 15**, with subsequent versions adding capabilities.

| Feature | PostgreSQL 15–16 | PostgreSQL 17 | PostgreSQL 18 |
|---|---|---|---|
| `MERGE INTO ... USING ... ON ...` | Yes | Yes | Yes |
| `WHEN MATCHED THEN UPDATE/DELETE/DO NOTHING` | Yes | Yes | Yes |
| `WHEN NOT MATCHED THEN INSERT/DO NOTHING` | Yes | Yes | Yes |
| `WHEN NOT MATCHED BY SOURCE` | No | Yes | Yes |
| Explicit `WHEN NOT MATCHED BY TARGET` | No | Yes | Yes |
| `MERGE ... RETURNING` | No | Yes | Yes |
| `merge_action()` in `RETURNING` | No | Yes | Yes |
| Extended `OLD`/`NEW` references in `MERGE RETURNING` | No | Not as in PG18 | Yes |

Check the **server** version:

~~~sql
SHOW server_version;

SELECT current_setting('server_version_num')::INTEGER
    AS server_version_num;
~~~

Never infer the server version from the user's local `psql`, pgAdmin, or JDBC driver version.

**Lesson conventions:**

- Core examples use syntax available from PostgreSQL 15 onward.
- Examples marked **PostgreSQL 17+** use `BY SOURCE`, `BY TARGET`, or `MERGE RETURNING`.
- Examples marked **PostgreSQL 18+** use `OLD` and `NEW` in `MERGE RETURNING`.

If your system runs an older major version, choose compatible syntax and consult the official documentation for that major version.

## 2. What Are the Components of MERGE?

Basic structure:

~~~sql
MERGE INTO target_table AS t
USING source_table AS s
ON matching_condition
WHEN MATCHED AND condition_1 THEN
    UPDATE SET column_a = expression
WHEN MATCHED AND condition_2 THEN
    DELETE
WHEN MATCHED THEN
    DO NOTHING
WHEN NOT MATCHED AND condition_3 THEN
    INSERT (column_a, column_b)
    VALUES (s.value_a, s.value_b);
~~~

This is only a syntax skeleton, not runnable SQL, because table and column names are placeholders.

| Component | Meaning |
|---|---|
| `MERGE INTO` | Specifies the target table receiving changes |
| `USING` | Supplies the source rows |
| `ON` | Determines whether a source row matches a target row |
| `WHEN MATCHED` | Action branch when a matching target row is found |
| `WHEN NOT MATCHED` | Action branch when a source row has no matching target row |
| `WHEN NOT MATCHED BY SOURCE` | PG17+: branch for target rows absent from the source |
| `AND condition` | Additional predicate selecting an action within that match category |
| `UPDATE SET` | Updates the target row |
| `INSERT ... VALUES` | Inserts a new target row from source data |
| `DELETE` | Deletes the target row |
| `DO NOTHING` | Leaves that candidate unchanged |

Visual model:

~~~text
                Source rows
                     |
                     v
              Match against target
                     |
          +----------+----------+
          |                     |
        MATCHED            NOT MATCHED
          |                (source-only)
          v                     |
    Check WHEN MATCHED          v
     UPDATE/DELETE/       Check WHEN NOT MATCHED
       DO NOTHING             INSERT/DO NOTHING

PG17+: target-only rows also have WHEN NOT MATCHED BY SOURCE
~~~

### 2.1. A Candidate Row Executes at Most One WHEN Branch

PostgreSQL evaluates `WHEN` clauses in order. **The first matching branch** executes. A candidate row does not cascade sequentially through multiple `WHEN` clauses.

Example:

~~~sql
WHEN MATCHED AND s.stock = 0 THEN
    UPDATE SET is_active = FALSE
WHEN MATCHED THEN
    UPDATE SET stock = s.stock
~~~

If `s.stock = 0`, the first branch executes and the second branch **does not execute**.

### 2.2. If No Branch Matches, No Change Occurs

If a matched row satisfies none of the `WHEN MATCHED AND ...` predicates, PostgreSQL simply skips that row. An explicit `DO NOTHING` fallback branch is not mandatory.

## 3. Preparing Schema and Sample Data

We use a product catalog table keyed by `sku` with version numbers from an upstream system. The data below is synthetic.

**Run only in a dedicated practice database.** If the schema already exists, pick a fresh lab database rather than dropping objects used by applications.

~~~sql
CREATE SCHEMA merge_lab;

CREATE TABLE merge_lab.product (
    sku TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0),
    stock INTEGER NOT NULL CHECK (stock >= 0),
    source_version BIGINT NOT NULL CHECK (source_version >= 1),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp()
);

INSERT INTO merge_lab.product
    (sku, product_name, price, stock, source_version, is_active)
VALUES
    ('A100', 'Notebook', 30000.00, 10, 1, TRUE),
    ('B200', 'Fountain Pen', 15000.00, 40, 3, TRUE),
    ('C300', 'Folder', 25000.00, 20, 2, TRUE),
    ('D400', 'Sticker', 12000.00, 8, 1, TRUE);
~~~

Initial state:

| SKU | Name | Price | Stock | Version |
|---|---|---:|---:|---:|
| A100 | Notebook | 30000.00 | 10 | 1 |
| B200 | Fountain Pen | 15000.00 | 40 | 3 |
| C300 | Folder | 25000.00 | 20 | 2 |
| D400 | Sticker | 12000.00 | 8 | 1 |

Constraints preserve invariants:

- `PRIMARY KEY(sku)` guarantees at most one row per SKU.
- Price and stock are non-negative.
- Version is a positive integer.
- `is_active` supports logical deactivation rather than hard deletion.
- `updated_at` defaults on `INSERT`; it **does not auto-update** on `UPDATE` unless SQL or a trigger sets it.

## 4. First MERGE Example: Update or Insert

Suppose the source sends:

| SKU | Source Price | Source Stock | Source Version |
|---|---:|---:|---:|
| A100 | 35000.00 | 12 | 2 |
| B200 | 16000.00 | 38 | 3 |
| E500 | 45000.00 | 5 | 1 |

Rule: matched records update only when the source version is **strictly newer**; missing records are inserted.

~~~sql
MERGE INTO merge_lab.product AS t
USING (
    VALUES
        ('A100'::TEXT, 'New Notebook'::TEXT,
         35000.00::NUMERIC, 12::INTEGER, 2::BIGINT),
        ('B200', 'Fountain Pen', 16000.00::NUMERIC,
         38, 3::BIGINT),
        ('E500', 'Pencil Case', 45000.00::NUMERIC,
         5, 1::BIGINT)
) AS s(sku, product_name, price, stock, source_version)
ON t.sku = s.sku
WHEN MATCHED AND s.source_version > t.source_version THEN
    UPDATE SET
        product_name = s.product_name,
        price = s.price,
        stock = s.stock,
        source_version = s.source_version,
        is_active = TRUE,
        updated_at = statement_timestamp()
WHEN NOT MATCHED THEN
    INSERT (
        sku, product_name, price,
        stock, source_version, is_active
    )
    VALUES (
        s.sku, s.product_name, s.price,
        s.stock, s.source_version, TRUE
    );
~~~

Logical outcome starting from the initial data:

- `A100` exists, source version 2 > target version 1 → **UPDATE**.
- `B200` exists, source version 3 = target version 3 → **unchanged**.
- `E500` does not exist → **INSERT**.
- `C300` and `D400` are absent from source → **untouched**, because the statement has no target-only branch.

~~~sql
SELECT
    sku, product_name, price, stock, source_version, is_active
FROM merge_lab.product
ORDER BY sku;
~~~

Expected:

| SKU | Name | Price | Stock | Version |
|---|---|---:|---:|---:|
| A100 | New Notebook | 35000.00 | 12 | 2 |
| B200 | Fountain Pen | 15000.00 | 40 | 3 |
| C300 | Folder | 25000.00 | 20 | 2 |
| D400 | Sticker | 12000.00 | 8 | 1 |
| E500 | Pencil Case | 45000.00 | 5 | 1 |

**Note on B200:** even though the source has a different price/stock, its version is not greater, so the target stays unchanged. This rule only works if upstream guarantees versions reflect authoritative ordering. If "same version with different content" indicates an upstream bug, reconcile it rather than silently ignoring it forever.

### 4.1. Why Cast Inside VALUES?

Using `::TEXT`, `::NUMERIC`, `::INTEGER`, and `::BIGINT` fixes source column types explicitly. When inputs contain `NULL` or mixed types, automatic type inference can produce unexpected types.

When the source already lives in a typed staging table, explicit casts per literal are usually unnecessary.

## 5. The ON Condition Defines Identity Matching

In our example:

~~~sql
ON t.sku = s.sku
~~~

means source and target represent **the same product** when their SKUs match.

A dangerous mistake:

~~~sql
-- Avoid:
-- ON t.sku = s.sku AND t.is_active = TRUE
~~~

Suppose SKU `A100` exists with `is_active = FALSE`. That condition fails to match the target row, so source `A100` is classified as `NOT MATCHED`. The `INSERT` branch then tries to insert a second `A100`, triggering a unique violation.

If the goal is reactivating inactive products, put the status check inside `WHEN`:

~~~sql
MERGE INTO merge_lab.product AS t
USING (
    VALUES
        ('A100'::TEXT, 'Re-listed Notebook'::TEXT)
) AS s(sku, product_name)
ON t.sku = s.sku
WHEN MATCHED AND NOT t.is_active THEN
    UPDATE SET
        is_active = TRUE,
        product_name = s.product_name,
        updated_at = statement_timestamp()
WHEN NOT MATCHED THEN
    INSERT (
        sku, product_name, price, stock, source_version
    )
    VALUES (
        s.sku, s.product_name, 0, 0, 1
    );
~~~

**Rule:** `ON` defines entity identity; `WHEN ... AND` chooses actions based on state and version.

### 5.1. Why Not Filter Target Rows in ON?

Putting target-state predicates in `ON` changes **candidate classification** (matched vs. not matched). That is especially hazardous if `NOT MATCHED` inserts or PG17+ `BY SOURCE` deletes.

To filter source rows by batch or validity, filter inside `USING (SELECT ... WHERE ...)`. To decide actions based on target state, put predicates inside the appropriate `WHEN` clause.

## 6. WHEN Clauses Are Evaluated in Order

Suppose a batch sends operations to ignore, update, or disable products:

~~~sql
MERGE INTO merge_lab.product AS t
USING (
    VALUES
        ('A100'::TEXT, 0::INTEGER, 'DISABLE'::TEXT),
        ('B200'::TEXT, 32::INTEGER, 'SET'::TEXT),
        ('C300'::TEXT, 99::INTEGER, 'IGNORE'::TEXT)
) AS s(sku, new_stock, operation)
ON t.sku = s.sku
WHEN MATCHED AND s.operation = 'IGNORE' THEN
    DO NOTHING
WHEN MATCHED AND s.operation = 'DISABLE' THEN
    UPDATE SET
        stock = 0,
        is_active = FALSE,
        updated_at = statement_timestamp()
WHEN MATCHED AND s.operation = 'SET' THEN
    UPDATE SET
        stock = s.new_stock,
        updated_at = statement_timestamp();
~~~

Each candidate picks **the first branch whose condition evaluates to true**.

Never write:

~~~sql
-- Flawed logic / unreachable later branch:
-- WHEN MATCHED THEN UPDATE SET stock = s.new_stock
-- WHEN MATCHED AND s.operation = 'DISABLE' THEN DELETE
~~~

The unconditional `MATCHED` branch captures every matched row, so the subsequent `MATCHED` branch can never execute. Place **specific** branches before **general** ones.

### 6.1. Is DO NOTHING Required?

No. If a matched row matches no branch, it remains unchanged. Still, `DO NOTHING` is useful to explicitly document an intention to skip certain cases ahead of broader branches.

`DO NOTHING` in `MERGE` is distinct from `INSERT ... ON CONFLICT DO NOTHING`.

## 7. WHEN MATCHED AND: Only UPDATE When Data Actually Changed

If `MERGE` updates every matched row even when price and stock are identical, PostgreSQL still incurs MVCC write overhead.

Check for differences explicitly:

~~~sql
MERGE INTO merge_lab.product AS t
USING (
    VALUES
        ('A100'::TEXT, 35000.00::NUMERIC, 12::INTEGER),
        ('B200'::TEXT, 15000.00::NUMERIC, 40::INTEGER)
) AS s(sku, new_price, new_stock)
ON t.sku = s.sku
WHEN MATCHED AND (
    t.price IS DISTINCT FROM s.new_price
    OR t.stock IS DISTINCT FROM s.new_stock
) THEN
    UPDATE SET
        price = s.new_price,
        stock = s.new_stock,
        updated_at = statement_timestamp();
~~~

`IS DISTINCT FROM` has clear semantics when either side is `NULL`:

| A | B | `A IS DISTINCT FROM B` |
|---|---|---|
| 10 | 10 | FALSE |
| 10 | 20 | TRUE |
| NULL | NULL | FALSE |
| NULL | 10 | TRUE |

On `NOT NULL` columns `<>` also works, while `IS DISTINCT FROM` handles optional nullable columns safely.

### 7.1. Why Avoid Unnecessary UPDATEs?

An `UPDATE` can:

- Write a new tuple version.
- Generate WAL and dead tuples.
- Increase `VACUUM` work.
- Overwrite `updated_at` even when nothing business-meaningful changed.
- Fire triggers and downstream CDC events.
- Increase lock contention across concurrent writers.

Still, if business rules require recording "source confirmed at this timestamp," a dedicated confirmation record may be better than mutating the main entity row. Decide based on audit requirements.

## 8. NULLs in Join Keys and Comparison Predicates

SQL uses three-valued logic: `NULL = NULL` does not evaluate to `TRUE`. If a match key is nullable:

~~~sql
ON t.external_code = s.external_code
~~~

then source and target rows where `external_code IS NULL` **are not considered matched**.

You could write:

~~~sql
ON t.external_code IS NOT DISTINCT FROM s.external_code
~~~

to treat two `NULL`s as equal, yet that easily causes **many-to-many matches** when multiple records lack a key.

**Prefer** `NOT NULL` identity keys backed by `UNIQUE`/`PRIMARY KEY`. Quarantine upstream records missing keys instead of treating all `NULL`s as the same entity.

### 8.1. Nullable Attributes Differ from Nullable Identity

A nullable `description` column might need:

~~~sql
WHEN MATCHED
    AND t.description IS DISTINCT FROM s.description
THEN UPDATE SET description = s.description
~~~

This checks an **attribute** change, not entity identity, which is completely appropriate.

## 9. USING Accepts VALUES, Tables, SELECT, or CTEs

### 9.1. Small Inline List via VALUES

~~~sql
MERGE INTO merge_lab.product AS t
USING (
    VALUES
        ('A100'::TEXT, 25::INTEGER),
        ('B200'::TEXT, 35::INTEGER)
) AS s(sku, new_stock)
ON t.sku = s.sku
WHEN MATCHED THEN
    UPDATE SET
        stock = s.new_stock,
        updated_at = statement_timestamp();
~~~

Readable and handy for a few controlled source rows.

### 9.2. A Staging Table

In real pipelines, source data arrives in a staging table loaded from files. Filter by batch inside `USING` and enforce unique source keys:

~~~sql
MERGE INTO merge_lab.product AS t
USING (
    SELECT sku, product_name, price, stock, source_version
    FROM merge_lab.product_feed
    WHERE batch_id = 20261114
      AND is_valid = TRUE
) AS s
ON t.sku = s.sku
WHEN MATCHED AND s.source_version > t.source_version THEN
    UPDATE SET
        product_name = s.product_name,
        price = s.price,
        stock = s.stock,
        source_version = s.source_version
WHEN NOT MATCHED THEN
    INSERT (sku, product_name, price, stock, source_version)
    VALUES (
        s.sku, s.product_name,
        s.price, s.stock, s.source_version
    );
~~~

`product_feed` is created in the next section; this shows the query pattern against it.

### 9.3. Using WITH

~~~sql
WITH incoming AS (
    SELECT sku, product_name, price, stock, source_version
    FROM merge_lab.product_feed
    WHERE batch_id = 20261114
)
MERGE INTO merge_lab.product AS t
USING incoming AS s
ON t.sku = s.sku
WHEN MATCHED AND s.source_version > t.source_version THEN
    UPDATE SET
        price = s.price,
        stock = s.stock,
        source_version = s.source_version
WHEN NOT MATCHED THEN
    INSERT (sku, product_name, price, stock, source_version)
    VALUES (
        s.sku, s.product_name,
        s.price, s.stock, s.source_version
    );
~~~

CTEs clarify source preparation without turning `MERGE` into a multi-transaction workflow. All actions still execute under single-statement semantics.

## 10. Designing a Batch Staging Table

In ETL pipelines, a staging table receives raw batches, validates structure, and merges only verified rows.

~~~sql
CREATE TABLE merge_lab.product_feed (
    batch_id BIGINT NOT NULL,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0),
    stock INTEGER NOT NULL CHECK (stock >= 0),
    source_version BIGINT NOT NULL CHECK (source_version >= 1),
    is_valid BOOLEAN NOT NULL DEFAULT TRUE,
    received_at TIMESTAMPTZ NOT NULL DEFAULT statement_timestamp(),
    PRIMARY KEY (batch_id, sku)
);

INSERT INTO merge_lab.product_feed
    (batch_id, sku, product_name, price, stock, source_version)
VALUES
    (20261114, 'A100', 'New Notebook', 35000.00, 12, 2),
    (20261114, 'B200', 'Fountain Pen', 16000.00, 38, 3),
    (20261114, 'E500', 'Pencil Case', 45000.00, 5, 1);
~~~

`PRIMARY KEY(batch_id, sku)` guarantees:

- Within one batch, at most one row exists per SKU.
- Different batches can carry the same SKU.
- Queries filtering by `batch_id` have an index ready for lookup.

If a real import contains duplicates, loading is rejected immediately before `MERGE` touches the target table.

### 10.1. Preflight Checks Before Merging

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE is_valid) AS valid_rows,
    COUNT(*) FILTER (WHERE NOT is_valid) AS invalid_rows
FROM merge_lab.product_feed
WHERE batch_id = 20261114;
~~~

Source-to-target reconciliation:

~~~sql
SELECT
    s.sku,
    s.source_version AS incoming_version,
    t.source_version AS current_version,
    s.price AS incoming_price,
    t.price AS current_price
FROM merge_lab.product_feed AS s
LEFT JOIN merge_lab.product AS t
    ON t.sku = s.sku
WHERE s.batch_id = 20261114
ORDER BY s.sku;
~~~

These read-only queries verify source scope before running `MERGE`.

## 11. WHEN MATCHED THEN DELETE

`MERGE` can delete matched target rows in a branch:

~~~sql
BEGIN;

MERGE INTO merge_lab.product AS t
USING (
    VALUES
        ('C300'::TEXT, 'REMOVE'::TEXT),
        ('B200'::TEXT, 'KEEP'::TEXT)
) AS s(sku, operation)
ON t.sku = s.sku
WHEN MATCHED AND s.operation = 'REMOVE' THEN
    DELETE
WHEN MATCHED AND s.operation = 'KEEP' THEN
    DO NOTHING;

ROLLBACK;
~~~

This uses `ROLLBACK` for safe demonstration in a lab database. If committed without blocking constraints, `C300` is **physically deleted**.

Never write the branch action like a standalone `DELETE` statement:

~~~sql
-- Invalid inside a MERGE branch:
-- WHEN MATCHED THEN DELETE FROM merge_lab.product WHERE sku = s.sku
~~~

Inside `MERGE`, write only `THEN DELETE`; conditions belong in `ON` and `WHEN MATCHED AND ...`.

### 11.1. Soft Delete Differs from DELETE

To take a product off sale while preserving history:

~~~sql
WHEN MATCHED AND s.operation = 'DISABLE' THEN
    UPDATE SET
        is_active = FALSE,
        updated_at = statement_timestamp()
~~~

That is a status `UPDATE`, not physical deletion. Base the choice on order history, foreign keys, retention rules, and business policy.

## 12. PostgreSQL 17+: WHEN NOT MATCHED BY SOURCE

From PostgreSQL 17 onward, you can handle **target rows that have no matching source row**.

Suppose:

~~~text
Target: A100, B200, C300
Full source snapshot: A100, B200, E500
~~~

Classification:

| SKU | Source | Target | Category |
|---|---|---|---|
| A100 | Yes | Yes | MATCHED |
| B200 | Yes | Yes | MATCHED |
| E500 | Yes | No | NOT MATCHED BY TARGET |
| C300 | No | Yes | NOT MATCHED BY SOURCE |

A full snapshot `MERGE`:

~~~sql
-- PostgreSQL 17+.
-- Safe ONLY when the source is a COMPLETE SNAPSHOT of the target scope.
MERGE INTO merge_lab.product AS t
USING (
    VALUES
        ('A100'::TEXT, 'New Notebook'::TEXT,
         35000.00::NUMERIC, 12::INTEGER, 2::BIGINT),
        ('B200', 'Fountain Pen', 15000.00::NUMERIC,
         40, 3::BIGINT),
        ('E500', 'Pencil Case', 45000.00::NUMERIC,
         5, 1::BIGINT)
) AS s(sku, product_name, price, stock, source_version)
ON t.sku = s.sku
WHEN MATCHED AND s.source_version > t.source_version THEN
    UPDATE SET
        product_name = s.product_name,
        price = s.price,
        stock = s.stock,
        source_version = s.source_version,
        is_active = TRUE,
        updated_at = statement_timestamp()
WHEN NOT MATCHED BY TARGET THEN
    INSERT (
        sku, product_name, price, stock,
        source_version, is_active
    )
    VALUES (
        s.sku, s.product_name, s.price, s.stock,
        s.source_version, TRUE
    )
WHEN NOT MATCHED BY SOURCE AND t.is_active THEN
    UPDATE SET
        is_active = FALSE,
        updated_at = statement_timestamp();
~~~

For target-only rows, the `BY SOURCE` branch deactivates them. **It does not restrict itself to SKUs "seen in an earlier batch"**—it evaluates **all target rows absent from the source under the `ON` predicate**.

### 12.1. When Is a Source Insufficient for BY SOURCE?

If the source contains only **SKUs that changed today** rather than the whole catalog, every other SKU is absent from the source. Using `BY SOURCE` `DELETE`/`UPDATE` would accidentally wipe or deactivate valid catalog items.

Distinguish:

- **Delta feed:** only changed records.
- **Complete snapshot:** all records belonging to a defined scope at a valid point in time.

Only use `BY SOURCE` deactivation or deletion when **completeness and scope** are verified.

### 12.2. Tenant or Catalog Scoping

With multiple tenants or catalogs, a source containing only Catalog A must never deactivate Catalog B's products.

Template for a schema with `catalog_id` (do not run on our demo table lacking this column):

~~~sql
MERGE INTO catalog_product AS t
USING (
    SELECT catalog_id, sku, product_name, price
    FROM catalog_snapshot
    WHERE catalog_id = 42
      AND snapshot_id = 1001
) AS s
ON t.catalog_id = s.catalog_id
   AND t.sku = s.sku
WHEN MATCHED AND t.price IS DISTINCT FROM s.price THEN
    UPDATE SET
        price = s.price,
        product_name = s.product_name
WHEN NOT MATCHED BY TARGET THEN
    INSERT (catalog_id, sku, product_name, price)
    VALUES (s.catalog_id, s.sku, s.product_name, s.price)
WHEN NOT MATCHED BY SOURCE AND t.catalog_id = 42 THEN
    UPDATE SET is_active = FALSE;
~~~

Restricting target-only actions with `t.catalog_id = 42` is essential here. In production, also verify catalog authorization and snapshot consistency.

### 12.3. How to Handle PG15/16?

`BY SOURCE` does not exist in PG15/16. Run a separate `UPDATE ... WHERE NOT EXISTS (...)` inside the same transaction after verifying snapshot completeness and target scope.

Never send PG17+ syntax to a PG15/16 server.

## 13. PostgreSQL 17+: BY TARGET vs. BY SOURCE

In PostgreSQL 17+:

- `WHEN NOT MATCHED BY TARGET`: **source row has no target**; typically `INSERT`.
- `WHEN NOT MATCHED BY SOURCE`: **target row has no source**; typically `UPDATE`/`DELETE`/`DO NOTHING`.

Unqualified `WHEN NOT MATCHED` continues to mean source-only (`BY TARGET`).

This distinction trips people up because "not matched" requires specifying **which side is missing**.

When `MERGE` handles both directions, PostgreSQL performs a full-outer-join-like match; `ON` must suit join requirements. Standard equality keys like `t.sku = s.sku` are far cleaner than complex predicates or one-sided filters.

### 13.1. Which Columns Are Accessible in Each Branch?

- `WHEN MATCHED`: both source and target exist; reference either.
- `WHEN NOT MATCHED BY TARGET`: no target row exists; `INSERT` reads source columns.
- `WHEN NOT MATCHED BY SOURCE`: no source row exists; `UPDATE`/`DELETE` reads target columns.

Never reference `s.stock` in a target-only branch expecting a source value to exist.

## 14. BY SOURCE with Hard Delete Requires Strict Controls

Extremely dangerous if the source is incomplete:

~~~sql
-- PostgreSQL 17+, NEVER use with a delta feed:
-- WHEN NOT MATCHED BY SOURCE THEN DELETE
~~~

Potential consequences:

- Deletes valid products missing from a partial batch.
- Cascades or fails on FKs to order lines.
- Generates massive WAL and dead tuples.
- Spikes `VACUUM` and replica load.
- Sends unintended delete events to downstream audits/CDC.
- Triggers complex restore and reconciliation incidents.

`UPDATE SET is_active = FALSE` is usually safer for catalogs needing history. When physical purging is truly required, build a dedicated retention workflow with explicit permissions.

### 14.1. An Empty Snapshot Does Not Always Mean "Delete Everything"

If upstream sends 0 rows due to a network or export failure, that does not prove the entire catalog vanished. Verify snapshot completion markers, expected counts, checksums, or explicit end-of-feed signals before running target-only reconciliation.

## 15. Duplicate Sources and Cardinality Violations

Source rows must satisfy the expected cardinality; specifically, **a single target row must never be modified more than once in the same `MERGE`**.

Error example:

~~~sql
-- Error demonstration only: two source rows share the same SKU.
MERGE INTO merge_lab.product AS t
USING (
    VALUES
        ('A100'::TEXT, 10::INTEGER),
        ('A100'::TEXT, 20::INTEGER)
) AS s(sku, new_stock)
ON t.sku = s.sku
WHEN MATCHED THEN
    UPDATE SET stock = s.new_stock;
~~~

Both source rows match target `A100`. Attempting to update or delete the same target row twice in `MERGE` raises a **cardinality violation**. If two source rows both try to `INSERT` the same new SKU, a **unique violation** occurs.

Never rely on the database "picking the last row" or "dropping one." `MERGE` makes no such promise.

### 15.1. Detect Duplicates in Raw Sources

~~~sql
WITH incoming(sku, stock) AS (
    VALUES
        ('A100'::TEXT, 10),
        ('A100', 20),
        ('B200', 30)
)
SELECT sku, COUNT(*) AS count_per_sku
FROM incoming
GROUP BY sku
HAVING COUNT(*) > 1;
~~~

Result: `A100` has 2 rows.

### 15.2. Deduplicate Using Explicit Business Rules

Suppose the source provides `version` and `received_at`; pick the latest record:

~~~sql
WITH incoming(sku, stock, version, received_at) AS (
    VALUES
        ('A100'::TEXT, 10, 2::BIGINT,
         TIMESTAMPTZ '2026-11-14 08:00:00+00'),
        ('A100', 20, 3::BIGINT,
         TIMESTAMPTZ '2026-11-14 08:05:00+00'),
        ('B200', 30, 1::BIGINT,
         TIMESTAMPTZ '2026-11-14 08:10:00+00')
)
SELECT DISTINCT ON (sku)
    sku, stock, version, received_at
FROM incoming
ORDER BY sku, version DESC, received_at DESC;
~~~

If two rows share the same `version` and timestamp with different payloads, add an explicit tiebreaker or reject the anomalous source. `DISTINCT ON` cannot guess which record is business-valid.

## 16. The Target Table Must Also Have a Unique Key

If the target table allows two rows with `SKU A100` due to a missing unique constraint, one source `A100` matches both and modifies multiple target rows.

While distinct from the "same target row modified twice" error, updating two target rows for a supposedly unique SKU is a business bug.

Enforce `PRIMARY KEY` or `UNIQUE` on the true identity key. In multi-tenant tables:

~~~text
identity = (tenant_id, sku)
~~~

both the unique constraint/index and the `ON` condition must match that pair.

## 17. MERGE vs. UPDATE ... FROM

PostgreSQL supports:

~~~sql
UPDATE merge_lab.product AS t
SET
    stock = s.stock,
    updated_at = statement_timestamp()
FROM (
    VALUES
        ('A100'::TEXT, 12::INTEGER),
        ('B200'::TEXT, 20::INTEGER)
) AS s(sku, stock)
WHERE t.sku = s.sku;
~~~

This updates target rows when matching source rows exist. It **cannot insert** missing SKUs.

`MERGE` combines multiple conditional actions in one command.

| Criterion | `UPDATE ... FROM` | `MERGE` |
|---|---|---|
| Update matched rows | Yes | Yes |
| Insert unmatched rows | Not in the same statement | Yes |
| Delete matched rows conditionally | Not in the same `UPDATE` | Yes |
| Multiple conditional branches | No `WHEN` branching model | Yes |
| Duplicate source matching one target | Nondeterministic source selection | Can raise cardinality violation |
| Simple update-only jobs | Usually concise | Often overkill |
| Multi-action synchronization | Requires multiple statements | Cleaner fit |

When you only need to update existing rows, `UPDATE ... FROM` remains great as long as source keys are unique.

## 18. MERGE vs. INSERT ... ON CONFLICT

Traditional PostgreSQL UPSERT:

~~~sql
INSERT INTO merge_lab.product
    (sku, product_name, price, stock, source_version)
VALUES
    ('A100', 'New Notebook', 35000.00, 12, 2)
ON CONFLICT (sku)
DO UPDATE SET
    product_name = EXCLUDED.product_name,
    price = EXCLUDED.price,
    stock = EXCLUDED.stock,
    source_version = EXCLUDED.source_version;
~~~

`ON CONFLICT` starts from an **`INSERT` hitting a unique conflict**, whereas `MERGE` starts from **source–target matching via `ON`**.

| Criterion | `INSERT ... ON CONFLICT` | `MERGE` |
|---|---|---|
| Starting model | `INSERT` + conflict handling | `JOIN`/matching |
| Unique arbiter | Required for conflict targeting | `ON` defines match; unique constraints still guard target |
| Simple UPSERT | Ideal fit | Supported |
| `DELETE` matched rows | Not via `DO UPDATE` | Yes |
| Target-only rows in snapshot | No | PG17+ |
| Multiple action branches | Limited | Flexible |
| Concurrent `INSERT` on same key | Built-in atomic conflict switching | Does not share identical branch-switching guarantees |

### 18.1. When to Choose ON CONFLICT?

When the requirement is simply:

> Insert a SKU; if it already exists, update it.

and a compatible unique constraint exists, `INSERT ... ON CONFLICT DO UPDATE` is easier to read and handles high-concurrency insert races cleanly.

### 18.2. When to Choose MERGE?

When you simultaneously need to:

- Update when version is newer.
- Skip when version is older.
- Delete when operation is `REMOVE`.
- Insert missing rows.
- (PG17+) deactivate target-only rows in a complete snapshot.

`MERGE` expresses multi-branch rules cleanly in one statement.

**The two statements are not equivalent under concurrency.**

## 19. Concurrency: MERGE Can Still Hit Unique Violations

Suppose two transactions concurrently `MERGE` a new SKU `E500`:

~~~text
Transaction A                 Transaction B
-------------                 -------------
reads: E500 absent            reads: E500 absent
picks INSERT branch           picks INSERT branch
insert succeeds               may hit unique conflict
commits                       retries/rolls back per policy
~~~

The primary key prevents creating two `E500` rows, yet does not guarantee both `MERGE` calls succeed.

Errors you may need to handle:

- Unique violations during concurrent `INSERT` races.
- Lock contention when concurrent transactions update the same rows.
- Deadlocks when locking multiple rows in different orders.
- Serialization failures under stricter isolation levels.

### 19.1. Mitigation Strategies

- Enforce unique constraints on the true business key.
- Prefer `INSERT ... ON CONFLICT` for simple high-concurrency single-key upserts.
- Partition work by tenant or key range to reduce contention.
- Implement bounded retries for transient errors.
- Keep operations idempotent.
- Keep transactions short and monitor lock waits.

### 19.2. Retries Must Handle Aborted Transactions

When a statement fails inside an explicit transaction, PostgreSQL requires `ROLLBACK` or rolling back to a valid savepoint before continuing. Never re-run `MERGE` inside an aborted transaction expecting it to succeed.

Under `SERIALIZABLE`, retry the **entire transaction** on serialization failure after re-reading required preconditions.

## 20. Idempotency: Is Re-Running a Batch Safe?

A batch may be re-sent after a timeout. Compare two update policies:

**Absolute assignment:**

~~~sql
WHEN MATCHED THEN
    UPDATE SET stock = s.absolute_stock
~~~

Re-running the exact same source leaves stock at the same value (though it still writes an `UPDATE` unless gated by a difference check).

**Delta addition:**

~~~sql
WHEN MATCHED THEN
    UPDATE SET stock = t.stock + s.stock_delta
~~~

Re-running the same batch adds the delta twice, corrupting stock.

Example:

~~~text
Initial stock: 10
Delta: +5

Run 1: 15
Retry 2: 20    <-- wrong if from the same event
~~~

For deltas, record the event ID or batch ID in an applied-events ledger **in the same transaction**. `MERGE` itself does not know whether a delta was previously applied.

### 20.1. Proper Versioning

When using `source_version > target_version`, upstream must guarantee monotonic versions within scope. Same-version differing payloads must be flagged and reconciled—never assume version numbers alone guarantee correctness without an upstream contract.

## 21. MERGE Inside Transactions

PostgreSQL executes a single `MERGE` as an atomic statement within its transaction. When a constraint fails, partial modifications from that statement are never committed half-done.

Multi-step workflow skeleton:

~~~sql
BEGIN;

-- 1. Verify batch status.
-- 2. Execute MERGE from verified source.
-- 3. Record completion metadata if all checks pass.

COMMIT;
~~~

This is a skeleton. In production, configure lock timeouts, statement timeouts, rollbacks, auditing, and downstream impact controls.

### 21.1. External Side Effects Do Not Roll Back Automatically

If application code sends an HTTP call to a search engine or publishes a message while the PostgreSQL transaction is still uncommitted, rolling back the DB does not un-send that message.

Use the **transactional outbox** pattern: write target changes and an outbox event in the same DB transaction, then have a worker publish externally after commit with retries and idempotency.

## 22. Target Constraints Still Apply

In our demo table:

~~~sql
price NUMERIC(12,2) NOT NULL CHECK (price >= 0)
stock INTEGER NOT NULL CHECK (stock >= 0)
sku TEXT PRIMARY KEY
~~~

All `MERGE` actions must obey these constraints:

- Inserting negative stock → rejected by `CHECK`.
- Inserting duplicate SKU → rejected by `PRIMARY KEY`.
- Deleting a parent row referenced by child FKs → rejected by `FOREIGN KEY`.
- Assigning incompatible types → cast or constraint error.

Never drop constraints just to let a `MERGE` batch pass. Validate the source, classify bad rows, and handle them per policy.

### 22.1. Foreign Keys and DELETE

Products referenced by historical order lines should usually be kept for auditing. When `order_items` holds an FK to `product`, hard deletion fails. Deactivating with `UPDATE is_active = FALSE` preserves integrity while distinguishing "discontinued from sale" from retention-based purging.

## 23. Triggers When MERGE Modifies Rows

`MERGE` fires triggers corresponding to its executed and declared actions:

- Row-level triggers fire for rows actually processed by the corresponding action (`INSERT`/`UPDATE`/`DELETE`).
- Statement-level triggers can fire for action types declared in the `MERGE` statement, even if zero rows end up executing that branch, per PostgreSQL rules.

Thus a `MERGE` containing both `INSERT` and `UPDATE` branches that only updates rows can still fire a statement-level `INSERT` trigger. Never count statement-level trigger invocations to infer how many rows were inserted.

When triggers exist on the target table:

- Inspect trigger types and `BEFORE`/`AFTER` timing.
- Assess audit and CDC effects.
- Check whether triggers mutate keys or columns used in `ON`.
- Guard against non-transactional external side effects.
- Never assume the `MERGE` SQL on paper represents the entire final state.

## 24. Role Privileges for Running MERGE

PostgreSQL has no standalone `MERGE` privilege replacing individual DML privileges.

The executing role may need:

- `SELECT` on columns read from source and target.
- `INSERT` if `MERGE` contains an `INSERT` branch.
- `UPDATE` on columns assigned in `SET`.
- `DELETE` if `MERGE` contains a `DELETE` branch.
- Schema and sequence/object privileges as configured.

Privileges are checked for all actions **declared in the statement**, not only the branches that happen to trigger on a given batch.

A role with only `UPDATE` privilege cannot run a `MERGE` that declares a `DELETE` branch even if the operator expects zero deletions in that batch.

**Principle:** follow least privilege, separate update-only jobs from hard-delete jobs, and test under the real runtime role before production.

## 25. PostgreSQL 17+: RETURNING and merge_action()

Starting in PostgreSQL 17, `MERGE` can return actually modified rows:

~~~sql
-- PostgreSQL 17+.
MERGE INTO merge_lab.product AS t
USING (
    VALUES
        ('A100'::TEXT, 33::INTEGER),
        ('B200'::TEXT, 44::INTEGER)
) AS s(sku, new_stock)
ON t.sku = s.sku
WHEN MATCHED AND t.stock IS DISTINCT FROM s.new_stock THEN
    UPDATE SET
        stock = s.new_stock,
        updated_at = statement_timestamp()
RETURNING
    merge_action() AS action,
    t.sku,
    t.stock;
~~~

`merge_action()` returns `'INSERT'`, `'UPDATE'`, or `'DELETE'` for each modified row.

**Never call `merge_action()` in a regular `SELECT`**; it is specifically for `MERGE ... RETURNING` in supported versions.

### 25.1. DO NOTHING Does Not Appear as a Modification

Rows skipped because no branch matched or because `DO NOTHING` executed are not `INSERT`/`UPDATE`/`DELETE` actions and do not appear in `RETURNING`.

If you need counts of skipped rows by reason, compute them in preflight reconciliation or a dedicated audit query.

### 25.2. MERGE Command Tag

On success, PostgreSQL returns a command tag formatted as:

~~~text
MERGE total_count
~~~

`total_count` is the total number of modified rows. It is **not the source row count**, and does not break down inserts vs. updates vs. deletes.

## 26. PostgreSQL 18+: OLD and NEW in RETURNING

PostgreSQL 18 adds support for referencing old and new values in `MERGE RETURNING`.

~~~sql
-- PostgreSQL 18+.
MERGE INTO merge_lab.product AS t
USING (
    VALUES ('A100'::TEXT, 25::INTEGER)
) AS s(sku, new_stock)
ON t.sku = s.sku
WHEN MATCHED AND t.stock IS DISTINCT FROM s.new_stock THEN
    UPDATE SET
        stock = s.new_stock,
        updated_at = statement_timestamp()
RETURNING
    merge_action() AS action,
    t.sku,
    old.stock AS previous_stock,
    new.stock AS current_stock;
~~~

On `UPDATE`, you see both pre- and post-update stock. On `INSERT`, there is no `OLD` target row; on `DELETE`, there is no `NEW` row under standard semantics.

Another PG18 extended syntax option:

~~~sql
-- Illustrative RETURNING clause:
-- RETURNING WITH (OLD AS o, NEW AS n)
--     merge_action(), o.stock, n.stock
~~~

Never deploy these clauses to servers running PostgreSQL 15–17.

## 27. Previewing Before Executing MERGE

Before applying an important batch, write a `SELECT` predicting each planned action:

~~~sql
WITH incoming AS (
    SELECT
        sku, price, stock, source_version
    FROM merge_lab.product_feed
    WHERE batch_id = 20261114
      AND is_valid = TRUE
)
SELECT
    s.sku,
    t.source_version AS target_version,
    s.source_version AS source_version,
    CASE
        WHEN t.sku IS NULL THEN 'would_insert'
        WHEN s.source_version > t.source_version
            THEN 'would_update'
        ELSE 'would_skip'
    END AS planned_action
FROM incoming AS s
LEFT JOIN merge_lab.product AS t
    ON t.sku = s.sku
ORDER BY s.sku;
~~~

Count by planned action:

~~~sql
WITH incoming AS (
    SELECT sku, source_version
    FROM merge_lab.product_feed
    WHERE batch_id = 20261114
),
planned AS (
    SELECT
        CASE
            WHEN t.sku IS NULL THEN 'insert'
            WHEN s.source_version > t.source_version THEN 'update'
            ELSE 'skip'
        END AS action
    FROM incoming AS s
    LEFT JOIN merge_lab.product AS t
        ON t.sku = s.sku
)
SELECT action, COUNT(*) AS candidate_count
FROM planned
GROUP BY action
ORDER BY action;
~~~

The preview reflects the **`SELECT`'s snapshot**. If another transaction modifies the target between preview and `MERGE`, actual outcomes can differ.

High-reliability systems pair validation with proper transaction strategies rather than trusting preview counts blindly.

## 28. EXPLAIN and MERGE Execution Plans

To inspect the plan **without modifying data**, use `EXPLAIN`:

~~~sql
EXPLAIN
MERGE INTO merge_lab.product AS t
USING (
    SELECT sku, price, stock, source_version
    FROM merge_lab.product_feed
    WHERE batch_id = 20261114
) AS s
ON t.sku = s.sku
WHEN MATCHED AND s.source_version > t.source_version THEN
    UPDATE SET
        price = s.price,
        stock = s.stock,
        source_version = s.source_version
WHEN NOT MATCHED THEN
    INSERT (
        sku, product_name, price,
        stock, source_version
    )
    VALUES (
        s.sku, 'Unnamed', s.price,
        s.stock, s.source_version
    );
~~~

Things to check:

- Is the target looked up using the match key?
- Is the source filtered to the target batch?
- Did the planner pick Hash Join, Nested Loop, or Merge Join?
- Are source/target row estimates reasonable?
- Are there unexpected large sorts or sequential scans?
- Are staging indexes and table statistics up to date?

### 28.1. Beware of EXPLAIN ANALYZE

`EXPLAIN (ANALYZE, BUFFERS)` **actually executes the DML**. Never run it directly on production just to inspect timings.

In a lab you can wrap it:

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
MERGE INTO merge_lab.product AS t
USING (
    VALUES ('A100'::TEXT, 12::INTEGER)
) AS s(sku, new_stock)
ON t.sku = s.sku
WHEN MATCHED THEN
    UPDATE SET stock = s.new_stock;

ROLLBACK;
~~~

`ROLLBACK` reverts DB row changes, yet cannot undo external side effects. In production, follow dedicated benchmarking and safety procedures.

## 29. Which Indexes Help MERGE?

With `ON t.sku = s.sku`, the target needs fast SKU lookups. Our demo table already has `PRIMARY KEY(sku)`, providing a unique B-tree index.

Do not add a second identical index just for `MERGE`.

In multi-tenant schemas where SKUs are unique per tenant:

~~~text
PRIMARY KEY (tenant_id, sku)

ON t.tenant_id = s.tenant_id
   AND t.sku = s.sku
~~~

Target key, `ON` predicate, and source scope must align.

On staging tables:

~~~text
PRIMARY KEY (batch_id, sku)
~~~

supports batch filtering and prevents intra-batch duplicates.

Still, the planner may prefer a Hash Join or Seq Scan when source or target is large. **Having an index does not force an Index Scan.** Depending on data volume, joining whole tables can beat millions of individual key lookups.

## 30. Large MERGE Batches and Operational Cost

A `MERGE` touching millions of rows can:

- Hold row locks for a long time.
- Generate huge WAL volume.
- Produce heavy dead tuples.
- Strain autovacuum.
- Cause replication lag.
- Consume significant CPU/memory for joins.
- Slow down rollback if an error occurs near the end.

For **delta feeds**, split into non-overlapping batches/key ranges with checkpoints.

For **full snapshots** needing `BY SOURCE`, never run "target absent from source" logic after each partial chunk, since each chunk only holds part of the snapshot. Load and verify the **complete snapshot** before reconciling target-only rows.

### 30.1. A Safer Multi-Batch Pipeline

~~~text
Receive snapshot_id
    |
    v
Load staging chunks 1..N
    |
    v
Verify row count + duplicates + checksum
    |
    v
Mark snapshot COMPLETE
    |
    v
MERGE valid source rows
    |
    v
Only if source is a full snapshot:
  reconcile target-only rows within scope
    |
    v
Audit + verify + checkpoint
~~~

Never treat an empty batch as proof that all upstream records were deleted.

## 31. Deadlocks and Processing Order

Two concurrent transactions can deadlock:

~~~text
T1 locks SKU-A, waits for SKU-B
T2 locks SKU-B, waits for SKU-A
~~~

PostgreSQL detects deadlocks and aborts one transaction.

Mitigations:

- Partition work by tenant or non-overlapping key groups.
- Keep transactions short.
- Consider consistent source ordering.
- Implement bounded retries for deadlock errors.
- Monitor lock waits and overlapping batch schedules.

Sorting `ORDER BY sku` in the source query can help in some cases, yet does not guarantee deadlock freedom across optimizer plans, triggers, or mixed operations. Measure and design for your actual workload.

## 32. Partitioned Tables and MERGE

When the target is a partitioned table:

- `INSERT`s must route to the right partition.
- Partition constraints apply.
- Unique/primary keys on partitioned tables have version-dependent rules involving partition keys.
- Updating partition keys may involve row movement or version limitations.
- Planning and locking can span multiple partitions.
- Triggers, FKs, and rules need verification.

Never move a `MERGE` from an ordinary table to a large partitioned table without testing on the exact PostgreSQL version, partition key type, and constraints.

## 33. Can Views or Foreign Tables Be Targets?

Target support varies across object types and major versions:

- Materialized views are not ordinary `MERGE` targets.
- Foreign tables have restrictions or lack `MERGE` target support per current documentation.
- Views have specific conditions, such as updatable views or `INSTEAD OF` triggers in supported versions.
- Rules, triggers, and partitioning affect eligibility.

Never assume an object you can `SELECT` from supports `MERGE INTO`. Check the documentation for your server version and test in staging.

## 34. Java JDBC: Merging One SKU with PreparedStatement

In Java, never concatenate user input into SQL. Bind values with `PreparedStatement`:

~~~java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class ProductMergeRepository {
    private final DataSource dataSource;

    public ProductMergeRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public int mergeOne(
        String sku,
        String name,
        BigDecimal price,
        int stock,
        long version
    ) throws SQLException {
        String sql = """
            MERGE INTO merge_lab.product AS t
            USING (
                VALUES (
                    CAST(? AS TEXT),
                    CAST(? AS TEXT),
                    CAST(? AS NUMERIC(12,2)),
                    CAST(? AS INTEGER),
                    CAST(? AS BIGINT)
                )
            ) AS s(sku, name, price, stock, version)
            ON t.sku = s.sku
            WHEN MATCHED AND s.version > t.source_version THEN
                UPDATE SET
                    product_name = s.name,
                    price = s.price,
                    stock = s.stock,
                    source_version = s.version,
                    updated_at = statement_timestamp()
            WHEN NOT MATCHED THEN
                INSERT (
                    sku, product_name, price,
                    stock, source_version
                )
                VALUES (
                    s.sku, s.name, s.price,
                    s.stock, s.version
                )
            """;

        try (Connection con = dataSource.getConnection();
             PreparedStatement ps = con.prepareStatement(sql)) {
            ps.setString(1, sku);
            ps.setString(2, name);
            ps.setBigDecimal(3, price);
            ps.setInt(4, stock);
            ps.setLong(5, version);
            return ps.executeUpdate();
        }
    }
}
~~~

This assumes Java 17+ (text blocks), a PostgreSQL JDBC driver, and a configured `DataSource`.

Notes:

- `executeUpdate()` returns the affected row count per JDBC/driver semantics; it does not replace detailed auditing.
- Validate price, stock, version, and privileges.
- Under concurrent writers, handle unique conflicts/deadlocks with an appropriate retry policy.
- For large batches, load staging and `MERGE` from `SELECT` rather than building SQL with hundreds of thousands of placeholders.
- Never interpolate client-supplied table or column names directly into SQL.

## 35. Observing Results and Auditing

A sync job should distinguish:

| Metric | Meaning |
|---|---|
| `source_rows` | Total rows received |
| `valid_rows` | Rows passing validation |
| `duplicate_keys` | Duplicate keys detected in source |
| `would_insert` | Rows predicted to insert at preview time |
| `would_update` | Rows predicted to update |
| `actual_changed` | Rows actually modified |
| `skipped_rows` | Rows untouched due to version/conditions |
| `failed_batches` | Batches rolled back or failed |
| `target_only_rows` | Target-only rows in full snapshot scope |
| `processed_batch_id` | Processed batch identifier |

Never infer from `MERGE 2` that the source contained exactly two rows or that all input rows were applied.

### 35.1. Post-MERGE Reconciliation

~~~sql
SELECT
    s.sku,
    s.source_version,
    t.source_version AS target_version,
    s.price AS source_price,
    t.price AS target_price,
    s.stock AS source_stock,
    t.stock AS target_stock
FROM merge_lab.product_feed AS s
LEFT JOIN merge_lab.product AS t
    ON t.sku = s.sku
WHERE s.batch_id = 20261114
ORDER BY s.sku;
~~~

If target version exceeds source version, price differences are intentional—**preventing stale batches from overwriting newer data**. Reconciliation must understand version policies rather than expecting blind equality everywhere.

### 35.2. Recording Operation History

Audits should record at least batch ID, source system, snapshot flag, version/policy, execution time, changed counts, and errors. Avoid logging sensitive data unnecessarily. On PG17+, `RETURNING` helps capture exact action types, though client-returned rows alone do not form a durable audit log.

## 36. Common Mistakes

### Mistake 1 — Running MERGE on PostgreSQL Older Than 15

Older servers do not support `MERGE`. Check `server_version` first.

### Mistake 2 — Using BY SOURCE/RETURNING on PG15/16

Those features require PostgreSQL 17+; use compatible syntax.

### Mistake 3 — Putting Target State Filters in ON

Existing rows become classified as `NOT MATCHED`, causing duplicate `INSERT`s. Keep identity in `ON` and action conditions in `WHEN`.

### Mistake 4 — Failing to Ensure Unique Source Keys

A target row modified multiple times in one `MERGE` triggers a cardinality violation. Enforce staging constraints and validation.

### Mistake 5 — Target Lacks a Unique Key

One source row can match and alter multiple target rows. Define appropriate `PK`/`UNIQUE` constraints.

### Mistake 6 — Wrong WHEN Branch Order

A broad branch before a specific branch makes the later branch unreachable. Put specific branches first and fallbacks last.

### Mistake 7 — Using BY SOURCE with a Delta Source

Deactivates or deletes valid rows absent from the delta. Use `BY SOURCE` only with verified complete snapshots and tight scope.

### Mistake 8 — Using DELETE Instead of Deactivation

Breaks history, FKs, or retention rules. Choose actions matching business lifecycle rules.

### Mistake 9 — Confusing MERGE with INSERT ON CONFLICT

They differ in matching and concurrency guarantees. For high-concurrency single-row upserts, consider `ON CONFLICT`.

### Mistake 10 — Retrying Deltas Without Idempotency

Applies stock deltas twice. Track event/batch IDs and checkpoints atomically.

### Mistake 11 — Updating Unchanged Rows

Generates needless WAL, dead tuples, triggers, and `updated_at` churn. Guard with difference predicates where appropriate.

### Mistake 12 — Ignoring NULL Semantics

`NULL = NULL` is not `TRUE`; use `NOT NULL` identity keys and `IS DISTINCT FROM` for nullable attributes.

### Mistake 13 — Ignoring CHECK/UNIQUE/FK Constraints

`MERGE` does not bypass constraints; validate sources and keep constraints intact.

### Mistake 14 — Overlooking Triggers

Statement-level triggers can fire even when a declared branch modifies zero rows; inspect side effects.

### Mistake 15 — Running EXPLAIN ANALYZE in Production

`ANALYZE` executes the `MERGE`. Use it only with proper safety controls.

### Mistake 16 — Oversized MERGE Batches

Increases locks, WAL, vacuum load, and replication lag. Batch and monitor workloads.

### Mistake 17 — Not Granting Privileges for All Declared Branches

A role may need `INSERT`/`UPDATE`/`DELETE` privileges depending on declared branches, even if a batch only exercises one branch.

### Mistake 18 — Missing Snapshot Validation/Checksums

A failed empty source could be mistaken for a complete empty snapshot and wipe targets. Require reliable `COMPLETE` signals.

### Mistake 19 — Omitting Audits and Checkpoints

Makes it impossible to tell which batches ran, retried, or rolled back. Persist metadata and reconcile.

### Mistake 20 — Missing Tenant Scope in ON

Matching SKUs across tenants will collide or cross-update. Use composite tenant keys and authorization guards.

## 37. Controlled MERGE Deployment Workflow

**Step 1 — Check PostgreSQL version.** Pick syntax supported by the server.

**Step 2 — Define the goal.** Simple upsert, delta sync, or full snapshot reconciliation?

**Step 3 — Define the match key.** `ON` must bind to a guaranteed `PK`/`UNIQUE` or business key.

**Step 4 — Prepare staging.** Include `batch_id`, `NOT NULL`, `CHECK`, unique constraints, and duplicate rules.

**Step 5 — Validate the source.** Check counts, schema, versions, tenant scope, checksums, and completeness.

**Step 6 — Design WHEN branches.** Specific before general; define skip/update/insert/delete clearly.

**Step 7 — Handle NULLs.** Avoid nullable identities; use `IS DISTINCT FROM` for nullable attributes where needed.

**Step 8 — Preview with SELECT.** Classify `would_insert`/`would_update`/`would_skip` and check counts.

**Step 9 — Verify constraints and privileges.** Ensure least-privilege roles and valid FKs/triggers.

**Step 10 — Inspect EXPLAIN.** Verify index usage, join strategy, and estimated row counts.

**Step 11 — Execute inside a transaction.** Keep short, set timeouts, enforce retry, idempotency, and audit policies.

**Step 12 — Reconcile after commit.** Compare source vs. target by version, verify actual changes, and handle exceptions.

**Step 13 — Extra step for BY SOURCE.** Execute only on verified complete snapshots with strict scope and bulk-delete safeguards.

## 38. Practice Exercises

### Exercise 1 — MATCHED and NOT MATCHED

Target has `A100`, `B200`; source has `B200`, `C300`. Classify `B200`, `C300`, and `A100` from both sides.

**Hint:** `B200` is matched; `C300` is source-only; `A100` is target-only under PG17+ logic.

### Exercise 2 — Basic MERGE

Write a `MERGE` updating `A100`'s stock and inserting SKU `X900` from a `VALUES` source.

**Hint:** `ON` by SKU, `WHEN MATCHED UPDATE`, and `WHEN NOT MATCHED INSERT`.

### Exercise 3 — Version Guard

Target `A100` is at version 10; source is at version 8. Which condition prevents overwriting newer data with stale data?

**Hint:** `s.source_version > t.source_version`.

### Exercise 4 — Flawed ON Condition

Why can `ON t.sku=s.sku AND t.is_active=TRUE` cause a duplicate `INSERT` error?

**Hint:** an inactive row still exists yet fails to match.

### Exercise 5 — WHEN Branch Ordering

To deactivate when `stock = 0` and update normally when `stock > 0`, which branch comes first?

**Hint:** the `stock = 0` branch before the general `MATCHED` branch.

### Exercise 6 — DO NOTHING

Write a `MERGE` that updates only existing SKUs and ignores new SKUs.

**Hint:** omit `NOT MATCHED` or use `DO NOTHING`.

### Exercise 7 — DELETE Matched

Write a branch deleting the target row when source `operation = 'REMOVE'`.

**Hint:** `WHEN MATCHED AND s.operation = 'REMOVE' THEN DELETE`.

### Exercise 8 — Logical Deactivation

Instead of hard deleting, set `is_active = FALSE`.

**Hint:** `WHEN MATCHED ... THEN UPDATE SET is_active = FALSE`.

### Exercise 9 — NULLs

`description` is nullable. Which comparison detects both `NULL` → string and string → `NULL` changes?

**Hint:** `IS DISTINCT FROM`.

### Exercise 10 — Duplicate Source

Two source rows for `A100` with different stock values cause what risk in `MERGE UPDATE`?

**Hint:** cardinality violation from modifying the same target row multiple times.

### Exercise 11 — Deduplicate

Use `DISTINCT ON (sku)` to select the highest source version and explain the risk if multiple records share the same version with different contents.

**Hint:** add a tiebreaker in `ORDER BY`, or reject ambiguous source data.

### Exercise 12 — Target Key

The target allows two rows with the same SKU, while the source has one row. Is `MERGE` guaranteed to touch only one target row?

**Hint:** no; add proper `PK`/`UNIQUE` constraints.

### Exercise 13 — Staging

Why does `PRIMARY KEY(batch_id, sku)` make sense for `product_feed`?

**Hint:** one SKU is unique per batch while still allowing the same SKU across multiple batches.

### Exercise 14 — Delta Source

A batch contains only 10 recently changed SKUs. Is `BY SOURCE DELETE` safe to clean up absent SKUs?

**Hint:** no; a delta is not a complete snapshot.

### Exercise 15 — PostgreSQL 17+

Write a branch deactivating target-only rows once a snapshot is verified complete.

**Hint:** `WHEN NOT MATCHED BY SOURCE AND t.is_active THEN UPDATE SET is_active = FALSE`.

### Exercise 16 — BY TARGET

Distinguish source-only from target-only and give the PG17+ syntax for each.

**Hint:** `BY TARGET` is source-only; `BY SOURCE` is target-only.

### Exercise 17 — RETURNING

On PG17+, how do you tell whether a row was `INSERT`ed or `UPDATE`d?

**Hint:** `RETURNING merge_action(), t.sku`.

### Exercise 18 — PostgreSQL 16

Can you use `MERGE RETURNING`?

**Hint:** no.

### Exercise 19 — OLD/NEW

On PG18+, how do you return stock before and after an `UPDATE` in `MERGE`?

**Hint:** `old.stock` and `new.stock` in `RETURNING`.

### Exercise 20 — UPSERT vs. MERGE

A multi-writer API only needs to insert or update by unique SKU. Which tool should you prefer?

**Hint:** `INSERT ... ON CONFLICT DO UPDATE`.

### Exercise 21 — Concurrent Insert

Two concurrent `MERGE`s both see `E500` absent. Are both guaranteed to succeed?

**Hint:** no; one can hit a unique violation.

### Exercise 22 — Constraints

Source has `stock = -5` while target has `CHECK(stock >= 0)`. Can `MERGE` bypass `CHECK`?

**Hint:** no.

### Exercise 23 — EXPLAIN

Why is `EXPLAIN ANALYZE MERGE` dangerous on production?

**Hint:** it executes the DML.

### Exercise 24 — Indexes

`product` already has `PRIMARY KEY(sku)`. Should you add a duplicate B-tree index on `sku` just for `MERGE`?

**Hint:** usually unnecessary.

### Exercise 25 — Idempotency

Why can `SET stock = t.stock + s.delta` produce wrong results on batch retry?

**Hint:** the delta gets added again.

### Exercise 26 — Failed Transaction

When `MERGE` errors inside an explicit transaction, can you run another statement immediately?

**Hint:** you must `ROLLBACK` or roll back to a valid savepoint.

### Exercise 27 — Privileges

A role only has `UPDATE`, yet `MERGE` declares `INSERT` and `DELETE` branches. Will it run if the batch only hits `UPDATE`?

**Hint:** privileges are checked against all actions declared in the statement.

### Exercise 28 — Triggers

`MERGE` has an `INSERT` branch, yet the batch inserts zero rows. Can a statement-level `INSERT` trigger fire?

**Hint:** yes; unlike row-level `INSERT` triggers.

### Exercise 29 — Preview

Write a `SELECT` with `CASE` classifying source rows as `would_insert`, `would_update`, or `would_skip`.

**Hint:** `LEFT JOIN` target and compare versions.

### Exercise 30 — Multi-Tenant

Two tenants both have SKU `A100`. Why is matching `ON` solely by SKU wrong?

**Hint:** include `tenant_id + sku` and authorization scoping.

### Exercise 31 — Empty Snapshot

An import job fails and outputs a 0-row source. Should `BY SOURCE DELETE` run?

**Hint:** no; require completeness verification.

### Exercise 32 — Command Tag

Does `MERGE 2` mean the source had 2 rows?

**Hint:** no; it is the number of modified rows.

## 39. Summary

- **`MERGE` arrived in PostgreSQL 15**, using `MERGE INTO ... USING ... ON ...` with `WHEN` branches to modify data conditionally by match status.
- `ON` is the **identity match predicate**, not a place for arbitrary status filters; action conditions belong in `WHEN ... AND`.
- `WHEN MATCHED` handles rows present in both source and target; `WHEN NOT MATCHED` handles source-only rows.
- **PostgreSQL 17+** adds `WHEN NOT MATCHED BY SOURCE`, explicit `BY TARGET`, and `MERGE RETURNING` / `merge_action()`.
- **PostgreSQL 18+** adds `OLD`/`NEW` references in `RETURNING`.
- `WHEN` branches are evaluated **in order**, and at most one branch executes per candidate row.
- **Duplicate sources** can trigger cardinality or unique violations; design target and staging keys cleanly.
- **`BY SOURCE` is safe only on verified complete, scoped snapshots.** Never use it to delete targets from a delta feed.
- `MERGE` still obeys `CHECK`, `UNIQUE`, `FOREIGN KEY`, triggers, privileges, and transaction rules.
- `MERGE` **differs from `INSERT ... ON CONFLICT` under concurrency**. Unique constraints, retries, isolation, and idempotency remain essential.
- Previews, staging, indexes, `EXPLAIN`, auditing, and reconciliation are vital steps before processing large datasets.
- For simple updates or upserts, `UPDATE` or `ON CONFLICT` may be clearer; choose `MERGE` when multi-branch matching logic truly calls for it.

The key to `MERGE` is separating two questions: **"Are this source row and target row the same entity under `ON`?"** and **"Given that match state, which policy action is permitted?"** When both questions are answered clearly, PostgreSQL lets you express multi-branch synchronization in one clean, controllable statement.

## Official References

- [PostgreSQL 15 — MERGE](https://www.postgresql.org/docs/15/sql-merge.html): core syntax.
- [PostgreSQL 17 — MERGE](https://www.postgresql.org/docs/17/sql-merge.html): `BY SOURCE`/`BY TARGET`, `RETURNING`.
- [PostgreSQL 18 — MERGE](https://www.postgresql.org/docs/18/sql-merge.html): newer capabilities, `OLD`/`NEW` in `RETURNING`.
- [PostgreSQL 18 — Merge support functions](https://www.postgresql.org/docs/18/functions-merge-support.html): `merge_action()`.
