# Composite Keys, Key Width, and Impact on References or Indexes

## 1. Why View Keys from Both the Logical and Physical Perspectives?

In the `DATABASE_DATA_MODELING` module, learners translate business requirements into verifiable data models: identifying entities, relationships, constraints, normalization, keys, indexes, and the physical schema, while comparing representations across relational, document, graph, and analytical systems. In the **Physical Modeling** step, choosing a key does not stop at "which values identify a record?"—it also asks "how many columns does the key have, how many bytes wide is it, how many child tables does it flow through, and which indexes does it generate?"

For example, a sales platform serving multiple sellers (*tenants*) may have product code `SKU-001` in both tenant A and tenant B. `sku` alone is not unique; the pair (`tenant_id`, `sku`) is what identifies a product **across the entire platform**. If you use this pair as the primary key, every table referencing a product must carry enough columns to point to the right tenant and SKU. If you use `product_id` as the primary key, you must still protect the no-duplicate-SKU rule with `UNIQUE(tenant_id, sku)`.

Three decisions to distinguish:

1. **Logical identity:** which set of attributes distinguishes two entities by business rules, and within what scope?
2. **Physical key:** which columns declare `PRIMARY KEY`/`UNIQUE`, with what types and widths, and how do foreign keys reference them?
3. **Access path:** does the column order of a composite key help actual queries and joins, or are additional indexes needed?

Good design preserves uniqueness and integrity as data grows, as business codes change, and as the application adds new write paths.

## 2. What Is a Composite Key? Do Not Confuse It with String-Concatenated Keys

A **composite key** is a key consisting of **two or more columns** evaluated together by the DBMS. If `tenant_id` and `sku` form the primary key, each individual component may repeat, but the pair as a whole cannot duplicate:

| `tenant_id` | `sku` | Valid when primary key is (`tenant_id`, `sku`)? |
|---:|---|---|
| 10 | `SP-001` | Valid |
| 10 | `SP-002` | Valid |
| 20 | `SP-001` | Valid, different tenant |
| 10 | `SP-001` | Invalid, entire pair duplicates |

PostgreSQL 16 example:

```sql
CREATE TABLE product (
    tenant_id BIGINT NOT NULL,
    sku       VARCHAR(64) NOT NULL,
    name      TEXT NOT NULL,
    CONSTRAINT pk_product PRIMARY KEY (tenant_id, sku)
);
```

`PRIMARY KEY (tenant_id, sku)` requires **both columns to be non-`NULL`** and the value pair to be unique. There is no need to add another `UNIQUE (tenant_id, sku)` with the exact same columns and semantics.

**Do not simulate a composite key** with a string like `tenant_id || '-' || sku` or by hashing a concatenated string as proof of uniqueness. String concatenation requires delimiter rules, escaping, encoding, and normalization, and can still collide—such as (`'A-B'`, `'C'`) vs. (`'A'`, `'B-C'`). Hash functions can also collide. The DBMS already provides native multi-column constraints: use them directly when enforcing uniqueness of a combination.

### 2.1. Composite Keys, Candidate Keys, and Surrogate Keys

| Concept | Role | Example |
|---|---|---|
| Candidate key | Minimal set of columns sufficient to distinguish each row | (`tenant_id`, `sku`) |
| Primary key | A candidate key chosen as the official row identifier, non-`NULL` | `PRIMARY KEY (tenant_id, sku)` |
| Alternate key | Another candidate key protected with `UNIQUE` | `UNIQUE (tenant_id, external_ref)` if immutable |
| Surrogate key | Separately generated ID carrying no business meaning | `product_id BIGINT` or `UUID` |
| Composite foreign key | Group of columns in a child table jointly referencing a valid unique key in a parent table | (`tenant_id`, `sku`) in `order_line` |

A table has only one `PRIMARY KEY` but may have multiple `UNIQUE` constraints. A composite key does not have to be the primary key: `UNIQUE (tenant_id, sku)` also enforces per-tenant uniqueness when `product_id` is chosen as the primary key.

"Minimality" in a candidate key belongs to logical semantics. If `product_id` is already globally unique, (`tenant_id`, `product_id`) is still **unique**, though not a theoretically minimal candidate key; adding `UNIQUE` on that pair can still be justified to support same-tenant composite foreign keys.

## 3. When Is a Composite Key the Right Design?

Composite keys arise naturally in:

- **Order lines:** (`order_id`, `line_no`), when line numbers are unique only within each order and lines need no standalone identifier.
- **Many-to-many junction tables:** (`student_id`, `course_id`), when a student has at most one enrollment in a course within the model's scope; if multiple terms exist, `term_id` or an enrollment entity may be needed.
- **Per-tenant codes:** (`tenant_id`, `sku`) or (`tenant_id`, `invoice_no`), when the same code can appear in different tenants.
- **Per-integration-source codes:** (`source_system`, `source_record_id`), since multiple external systems can issue identical local IDs.
- **Explicitly identified versions:** (`document_id`, `version_no`), when each version is a row and version numbers only have meaning within one document.

```mermaid
flowchart LR
    A["Requirement: SKU is unique only within a tenant"] --> B["Logical key: tenant_id + sku"]
    B --> C{"Can SKU change?"}
    C -- "No, stably governed" --> D["Can choose composite PK"]
    C -- "Yes, frequently changes" --> E["Consider surrogate PK"]
    D --> F["Child tables reference both columns accurately"]
    E --> G["Keep UNIQUE(tenant_id, sku)"]
    F --> H["Measure size, joins, and query plans"]
    G --> H
```

**A composite key is not automatically a good key:** adding `created_at` to make rows "accidentally unique" can mask a failure to understand business identity. Nor is (`order_id`, `product_id`) the right key if the same product can appear on multiple lines of an order at different prices or promotions. Confirm the business rule before attaching `PRIMARY KEY`.

## 4. Composite Primary Keys and Composite Foreign Keys: Relational Integrity

A composite foreign key requires **a column group in the child table** to reference a matching unique/primary key in the parent table. It cannot be replaced by separate single-column foreign keys while preserving the same semantics.

Modeling anti-pattern: table `order_line` has `tenant_id` referencing `tenant` and `sku` referencing a global SKU list, yet two separate foreign keys **do not guarantee the SKU belongs to the order line's tenant**. A composite foreign key `FOREIGN KEY (tenant_id, sku) REFERENCES product(tenant_id, sku)` enforces the actual invariant.

### 4.1. Complete Example on PostgreSQL 16: Per-Tenant Composite Keys

Assumptions: each tenant manages its own SKUs and order numbers; each order has multiple lines; each line belongs to the exact tenant of both the order and the product; line numbers start at 1. Business codes in this example are assumed stable while transactions reference them.

```sql
CREATE TABLE tenant (
    tenant_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_code VARCHAR(40) NOT NULL UNIQUE
);

CREATE TABLE product (
    tenant_id    BIGINT NOT NULL,
    sku          VARCHAR(64) NOT NULL,
    display_name TEXT NOT NULL,
    CONSTRAINT pk_product PRIMARY KEY (tenant_id, sku),
    CONSTRAINT fk_product_tenant
        FOREIGN KEY (tenant_id) REFERENCES tenant(tenant_id),
    CONSTRAINT ck_product_sku_nonblank
        CHECK (char_length(btrim(sku)) > 0)
);

CREATE TABLE sales_order (
    tenant_id  BIGINT NOT NULL,
    order_no   VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_sales_order PRIMARY KEY (tenant_id, order_no),
    CONSTRAINT fk_order_tenant
        FOREIGN KEY (tenant_id) REFERENCES tenant(tenant_id)
);

CREATE TABLE sales_order_line (
    tenant_id  BIGINT NOT NULL,
    order_no   VARCHAR(40) NOT NULL,
    line_no    INTEGER NOT NULL,
    sku        VARCHAR(64) NOT NULL,
    quantity   INTEGER NOT NULL,
    unit_price NUMERIC(14, 2) NOT NULL,

    CONSTRAINT pk_sales_order_line
        PRIMARY KEY (tenant_id, order_no, line_no),
    CONSTRAINT fk_line_order
        FOREIGN KEY (tenant_id, order_no)
        REFERENCES sales_order (tenant_id, order_no)
        ON DELETE RESTRICT,
    CONSTRAINT fk_line_product
        FOREIGN KEY (tenant_id, sku)
        REFERENCES product (tenant_id, sku)
        ON DELETE RESTRICT,
    CONSTRAINT ck_line_no_positive CHECK (line_no > 0),
    CONSTRAINT ck_line_quantity_positive CHECK (quantity > 0),
    CONSTRAINT ck_line_unit_price_nonnegative CHECK (unit_price >= 0)
);

-- Primary key already supports looking up lines by (tenant_id, order_no).
-- Add a per-tenant product lookup path when queries require it.
CREATE INDEX idx_line_tenant_sku
    ON sales_order_line (tenant_id, sku);
```

Explanation:

1. Two `product` rows with `sku = 'P-01'` in different tenants are valid; two rows with the same (`tenant_id`, `sku`) are rejected.
2. `PRIMARY KEY (tenant_id, order_no, line_no)` lets `line_no = 1` appear in multiple orders, but never twice in one order of the same tenant.
3. The `tenant_id` column in `sales_order_line` is **reused** across both composite foreign keys. Consequently, a line cannot belong to an order from tenant A while selecting a product from tenant B.
4. PostgreSQL creates unique indexes for `PRIMARY KEY`s on parent tables. However, PostgreSQL **does not automatically create indexes on the child side** merely because of a `FOREIGN KEY`. `idx_line_tenant_sku` supports finding lines by product and can reduce check overhead when updating/deleting products.
5. On the order-line table, the three-column primary key already provides access paths for (`tenant_id`, `order_no`) and all three columns. Adding another B-tree index on the exact same three columns without a separate reason creates redundant write and storage overhead.

### 4.2. Column Ordering and Compatibility in Foreign Keys

In PostgreSQL, each corresponding column pair of a foreign key must have compatible data types and comparison operators; a composite foreign key must reference a column set with an eligible unique constraint, primary key, or unique index on the parent table. The column order in `FOREIGN KEY (tenant_id, sku) REFERENCES product(tenant_id, sku)` **defines which columns pair with which**, not merely readable naming.

For example, if `tenant_id` is `BIGINT`, do not arbitrarily define its copy in a child table as `VARCHAR` and rely on implicit casting. For strings, charset/collation and comparison rules can also affect compatibility and uniqueness depending on the DBMS.

### 4.3. `NULL` and Default Behavior of Composite Foreign Keys

This is a major pitfall. In PostgreSQL, composite foreign keys default to `MATCH SIMPLE`: **if any referencing column is `NULL`, the referential check can be skipped for that row**. For a required relationship, declare `NOT NULL` on every column as shown above.

If a composite reference **is optional**, specify clearly whether "both columns must be absent together" or "one column present, one missing" is allowed. PostgreSQL supports `MATCH FULL` to prevent partial `NULL`s while allowing the entire tuple to be `NULL`:

```sql
-- Separate illustration for an optional reference.
CREATE TABLE external_reference (
    tenant_id BIGINT,
    sku       VARCHAR(64),
    note      TEXT,
    CONSTRAINT fk_external_reference_product
        FOREIGN KEY (tenant_id, sku)
        REFERENCES product (tenant_id, sku)
        MATCH FULL
);
```

In `external_reference`, (`NULL`, `NULL`) represents no reference and is allowed; (`10`, `NULL`) or (`NULL`, `'P-01'`) is rejected; (`10`, `'P-01'`) must exist in `product`. Do not assume every DBMS interprets or supports `MATCH FULL` syntax like PostgreSQL.

## 5. Key Width: Cost Propagating Through Indexes and References

Suppose you compare an 8-byte `BIGINT` primary key against a composite key (`tenant_id BIGINT`, `order_no VARCHAR(40)`). The composite key includes at least an 8-byte integer plus a variable-length string, which can consume multiple bytes per character under Unicode. The cost does not stay on the parent table:

- **Unique/primary indexes:** every index entry stores all key components plus index structural metadata.
- **Child tables:** every referencing row must store the foreign key columns. In a one-to-many relationship with tens of millions of child rows, repeating a wide key can incur substantial cost.
- **Indexes on FKs:** often store the same key components again to support joins and parent-table change checks.
- **Joins, sorts, hashes, data transfer:** wide keys affect value sizes, comparisons, caches, and payload transfer across tiers.
- **Key updates:** if a business key component changes, updates ripple across foreign keys, indexes, and replicated copies.

An **illustrative comparison**—not an exact storage measurement:

| Order Line Identification Option | Key Components | Typed Key Data Width |
|---|---|---|
| Surrogate ID | `line_id BIGINT` | 8 bytes numeric value |
| Numeric composite key | `tenant_id BIGINT`, `order_id BIGINT`, `line_no INTEGER` | 8 + 8 + 4 = 20 bytes numeric values, **excluding overhead** |
| Composite key with string | `tenant_id BIGINT`, `order_no VARCHAR(40)`, `line_no INTEGER` | 8 bytes + string bytes + 4 bytes, **excluding overhead** |
| Surrogate UUID | `line_id UUID` | 16 bytes UUID value |

Do not treat table sums as exact B-tree entry or row sizes: DBMSs also store tuple/index headers, null bitmaps, alignment padding, metadata, compression, and sometimes out-of-line values. `VARCHAR(40)` is a limit on **character count per DBMS rules**, not fixed at 40 bytes; actual bytes depend on encoding and content.

Suppose 20 million child rows each carry an average of 32 extra bytes of key data compared to a narrower option; the theoretical difference in row payload alone is 640 million bytes (roughly 610 MiB), **excluding indexes, overhead, or compression**. This is a back-of-the-envelope estimate to raise scale questions; design conclusions should measure actual sizes on the target DBMS.

Key width affects more than disk space. Larger keys fit fewer index entries per page, potentially increasing page reads and reducing cache efficiency. Yet a shorter key does not automatically win every query: if the app constantly looks up records by (`tenant_id`, `sku`), using `product_id` as the PK still requires a unique index on the business pair and may add an extra lookup step for some queries.

## 6. Column Order in Composite Keys and the Prefix Principle

Two B-tree indexes `(tenant_id, order_no, line_no)` and `(order_no, tenant_id, line_no)` can enforce the exact same uniqueness when used as keys, yet serve **different query paths**. With PostgreSQL B-trees, predicates on the **leading** columns of a key are usually most effective at narrowing the index scan range; trailing columns continue filtering/sorting within that range.

Example primary key:

```sql
PRIMARY KEY (tenant_id, order_no, line_no)
```

| Query | Usability of the B-tree Key Above |
|---|---|
| `WHERE tenant_id = ?` | Has leading prefix; can scan orders/lines for that tenant |
| `WHERE tenant_id = ? AND order_no = ?` | Has first two columns; well-suited for fetching an order's lines |
| `WHERE tenant_id = ? AND order_no = ? ORDER BY line_no` | Typically satisfies both filtering and `line_no` ordering |
| `WHERE tenant_id = ? AND line_no = ?` | Can use the `tenant_id` prefix, but lacks `order_no` to narrow contiguously |
| `WHERE order_no = ?` | Missing leading column; usually less effective than an index leading with `order_no` |
| `WHERE sku = ?` | `sku` is not in this key; needs another access path if this query matters |

Do not turn the prefix rule into an absolute claim that the DBMS "never" uses an index when the leading column is absent. Optimizers also consider statistics, full index scans, specialized scan types, or version-specific optimizations. What matters is **selectivity and pages read**, not merely whether a plan mentions the words "Index Scan".

### 6.1. Choosing Column Order by Access Path

In multi-tenant systems, many queries filter by `tenant_id` plus a business code. Placing `tenant_id` first often aids per-tenant queries, scopes data boundaries, and sorts by the next column. However:

- If most queries include **equality predicates on multiple columns**, order matters less for point lookups; weigh `ORDER BY` needs, prefix queries, and read frequency.
- If lookups almost always target a globally unique `order_id`, a single `BIGINT` key may serve that path better while keeping per-tenant uniqueness for the business rule.
- There is no immutable rule "always put the highest-cardinality column first". Column order must reflect filters, sorts, limits, references, and query plans on real data.

Example query well-served by `sales_order_line`'s primary key:

```sql
EXPLAIN
SELECT line_no, sku, quantity, unit_price
FROM sales_order_line
WHERE tenant_id = 42 AND order_no = 'SO-2027-0009'
ORDER BY line_no;
```

For product lookups, the child-table index `(tenant_id, sku)` aligns with:

```sql
EXPLAIN
SELECT order_no, line_no, quantity
FROM sales_order_line
WHERE tenant_id = 42 AND sku = 'P-01';
```

`EXPLAIN` shows the **estimated** plan without runtime metrics. When measuring, `EXPLAIN (ANALYZE, BUFFERS)` actually executes the query, so use it only in environments and situations where its execution cost is acceptable.

### 6.2. Column Order of `UNIQUE` and Uniqueness Semantics

`UNIQUE (tenant_id, sku)` and `UNIQUE (sku, tenant_id)` forbid the same duplicate pairs when columns are non-`NULL`. However, the underlying B-tree index is organized in the declared order. Do not swap columns merely for a secondary search if doing so breaks the access path needed by primary tenant queries. When using composite FKs, ensure child-to-parent column mapping matches order and satisfies constraints accepted by the DBMS.

## 7. When a Shorter Surrogate Key Is the Better Choice

If `sku` or `order_no` is prone to changing, placing strings in the PK ties many FKs and secondary indexes to mutable business values. An alternative is creating a `BIGINT` `product_id`/`order_id` as PK while keeping `UNIQUE(tenant_id, sku)` and `UNIQUE(tenant_id, order_no)` so business constraints remain intact.

Example **standalone Option B** alongside the tables in Section 4; table names carry an `_id` suffix for comparison:

```sql
CREATE TABLE product_id (
    product_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    BIGINT NOT NULL REFERENCES tenant(tenant_id),
    sku          VARCHAR(64) NOT NULL,
    display_name TEXT NOT NULL,
    CONSTRAINT uq_product_id_tenant_sku UNIQUE (tenant_id, sku),
    CONSTRAINT uq_product_id_tenant_product
        UNIQUE (tenant_id, product_id)
);

CREATE TABLE sales_order_id (
    order_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   BIGINT NOT NULL REFERENCES tenant(tenant_id),
    order_no    VARCHAR(40) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_order_id_tenant_no UNIQUE (tenant_id, order_no),
    CONSTRAINT uq_order_id_tenant_order
        UNIQUE (tenant_id, order_id)
);

CREATE TABLE sales_order_line_id (
    line_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id  BIGINT NOT NULL,
    order_id   BIGINT NOT NULL,
    line_no    INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity   INTEGER NOT NULL,
    CONSTRAINT uq_line_id_order_position
        UNIQUE (tenant_id, order_id, line_no),
    CONSTRAINT fk_line_id_order_same_tenant
        FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales_order_id (tenant_id, order_id),
    CONSTRAINT fk_line_id_product_same_tenant
        FOREIGN KEY (tenant_id, product_id)
        REFERENCES product_id (tenant_id, product_id),
    CONSTRAINT ck_line_id_number CHECK (line_no > 0),
    CONSTRAINT ck_line_id_quantity CHECK (quantity > 0)
);

CREATE INDEX idx_line_id_tenant_product
    ON sales_order_line_id (tenant_id, product_id);
```

**The trade-off:** the primary key of `product_id`/`sales_order_id` is only an 8-byte integer, so a single-column reference is compact. Yet to let the DBMS prevent **linking one tenant's order line to another tenant's product or order**, the example still declares composite FKs (`tenant_id`, `product_id`) and (`tenant_id`, `order_id`).

Because PostgreSQL requires the referenced column pair to have a matching unique/primary constraint, the example adds `UNIQUE(tenant_id, product_id)` and `UNIQUE(tenant_id, order_id)`. These two constraints are **mathematically redundant for uniqueness** since the IDs are already globally unique, yet they serve as composite FK targets and create **real additional indexes**. Do not overlook that cost when comparing against a pure composite-key approach.

Another option is a purely numeric composite primary key (`tenant_id`, `product_id`), or an FK referencing only `product_id` paired with another verified mechanism enforcing same-tenant consistency. Each option carries different application complexity and index overhead; evaluate integrity guarantees, query patterns, and operational requirements together.

**Note:** composite keys are not exclusive to natural business keys. Even with surrogate IDs, composite keys are still often needed to guard tenant scope, line ordering, versioning, or per-source uniqueness.

## 8. Comparing PostgreSQL, MySQL/InnoDB, and SQL Server

Physical storage characteristics of a key can vary substantially across DBMSs. The table below is a guide for PostgreSQL 16, MySQL 8.0/InnoDB, and SQL Server 2022; verify exact version, charset/collation settings, engine, and index types before applying:

| Aspect | PostgreSQL 16 | MySQL 8.0 / InnoDB | SQL Server 2022 |
|---|---|---|---|
| Primary key | Creates a unique B-tree index by default, separate from heap row order | Primary key is typically the **clustered index** organizing table rows by key | PK is a unique constraint, backed by a clustered or nonclustered index by design |
| Secondary indexes | Typically store keys and row pointers; do not automatically embed the full PK like InnoDB | Secondary index entries store PK values to locate rows, so a wide PK bloats all secondary indexes | Cost depends on clustered key choice; the clustered key can contribute to nonclustered row locators |
| Composite foreign keys | Supported; FKs do not auto-create child-side indexes | Supported on InnoDB, with specific index/column-type requirements; may auto-create a child index if missing | Supported; consider child-side indexes per access paths |
| Unique with `NULL` | By default, multiple `NULL`s are not considered duplicates; options exist in applicable versions | Multiple-`NULL` semantics depend on key/DBMS; must verify | Unique semantics and `NULL` handling differ from PostgreSQL; test directly |
| Index key limits | Depends on page size, index type, and data; overly long string keys can be rejected | Key length limits measured in bytes, varying by config/engine | Byte limits on index keys depend on index type; `INCLUDE` and clustered/nonclustered rules vary |
| Strings and collations | `VARCHAR(n)`, `TEXT`, and DB/column collations | `VARCHAR(n)` with charsets like `utf8mb4`; collation affects comparisons | `VARCHAR`/`NVARCHAR` with corresponding collations and storage rules |

**Practical consequence:** a composite PK containing a long string may be relatively tolerable in PostgreSQL for certain workloads, yet expensive in InnoDB because every secondary index carries the PK; conversely, wide composite keys in PostgreSQL are not free either. In SQL Server, specify the clustered key deliberately because it impacts locators across nonclustered indexes.

Avoid stating rules like "every key has a maximum of N bytes" as if universal across versions. Limits can depend on page size, charset, index type, `INCLUDE` columns, prefixes, and server settings. Creating an index successfully on short sample data does not prove strings at the business-limit length will not fail during future inserts.

## 9. Designing Width and Stability of Key Components

When a composite key includes strings, clarify:

1. **Value domain:** what is the max SKU length? Are character sets restricted? Is leading/trailing whitespace permitted?
2. **Comparison rules:** does `abc` collide with `ABC`? Is Unicode normalized to a canonical form before storage? Is collation accent-sensitive?
3. **Immutability:** does changing an SKU mean renaming **the same product** or creating a new product identity? This decision drives FK and history design.
4. **Reference fan-out:** how many child tables, rows, and external events carry copies of the key?
5. **Growth trajectory:** will adding a component to the key today force every FK/API/export to change if uniqueness scope expands later?
6. **DBMS limits:** can the type be indexed at maximum length? Do you need a short stable code separate from a long description field?

For instance, putting a multi-thousand-character `TEXT` column inside a PK just because partner codes "could be any length" is questionable. Store full `external_ref` as an attribute, pair it with `source_system` to define scope, use a stable surrogate ID for internal links, and enforce an appropriate unique constraint if index limits permit. If a hash representation is used to shorten lookups, account for **collisions and verification against the original value**; a hash index alone does not prove two distinct codes cannot hash identically.

Avoid putting mutable or sensitive data—like emails, phone numbers, or national IDs—into keys replicated across the schema. Security exposure and update costs usually outweigh saving a single surrogate ID column.

## 10. Measure Cost Instead of Only Calculating on Paper

To evaluate a composite key against a surrogate key, deploy both schema variants in a test environment and load realistically distributed data. Under identical volume and read/write ratios, measure:

- Row storage and total index size, especially on large child tables.
- `INSERT`, `UPDATE`, and parent-row delete latency with many references.
- Latency for point lookups by ID, by business key, fetching an order's lines, and joining to products.
- Query plans and buffer reads for core queries; memory and sort overhead.
- Sensitivity to extra indexes, realistic string lengths, tenant skew, and code update frequency.

With PostgreSQL:

```sql
-- Table size including heap, TOAST, and all indexes.
SELECT
    pg_size_pretty(pg_total_relation_size('public.sales_order_line')) AS total_size,
    pg_size_pretty(pg_indexes_size('public.sales_order_line')) AS indexes_size;

-- Inspect declared indexes and column ordering.
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'sales_order_line'
ORDER BY indexname;

-- Observe a representative query plan.
EXPLAIN (ANALYZE, BUFFERS)
SELECT line_no, sku, quantity
FROM sales_order_line
WHERE tenant_id = 42 AND order_no = 'SO-2027-0009'
ORDER BY line_no;
```

`pg_total_relation_size` aggregates multiple storage forks; `pg_indexes_size` sums index sizes. Do not deduce average key width from those two numbers alone if loaded datasets differ, statistics are stale, or indexes are not yet exercised by queries. `EXPLAIN (ANALYZE, BUFFERS)` **executes the actual query**: run it only on read queries or in controlled test environments where side effects are acceptable.

### Distinguishing Three Optimization Goals

| Goal | Key Selection Priority |
|---|---|
| Business integrity | `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY` with accurate scope and `NULL` rules |
| Access performance | Width, column order, query paths, index count, and DBMS storage layout |
| Evolvability | Key stability, replication across tables/systems, and migration cost |

Never sacrifice correctness to save a few bytes if doing so permits cross-tenant leaks or duplicate order lines. Conversely, an unnecessarily wide string composite key can create heavy overhead when a surrogate ID plus a narrower `UNIQUE` still satisfies all logical rules.

## 11. Migrating Keys and References

Suppose a system initially used `product(tenant_id, sku)` as PK, but partners later need to rename SKUs after tens of millions of order lines already store the composite key. Replacing the PK directly with `product_id` and dropping the old columns on child tables would sever links. A reconcilable rollout is required:

1. **Inventory:** list every child table, FK, unique constraint, index, API, cache, event payload, and data export containing (`tenant_id`, `sku`).
2. **Expand schema:** add `product_id` (initially nullable if needed), populate it for existing rows, and create unique constraints for `product_id` and (`tenant_id`, `sku`).
3. **Backfill references:** add `product_id` to child tables and populate via joins matching tenant and SKU. Use small resumable batches with checkpoints on large tables.
4. **Controlled dual-writing:** update applications or transition jobs so all new records maintain both old and new references consistently; guard against race conditions during migration.
5. **Reconcile:** verify zero missing product IDs, zero cross-tenant mismatches, zero orphaned child rows, and no duplicate business codes per tenant.
6. **Tighten constraints and switch reads:** apply new FKs and `NOT NULL` once data is clean, migrate queries/APIs in stages, and drop old FKs/columns only after all consumers have switched.
7. **Contingency and rollback:** test rollback capability at each stage, table lock durations, and extra write load from new indexes.

Example **verification-only** query after backfilling, assuming the migrated tables hold `product_id` alongside `tenant_id` and `sku`:

```sql
-- Find rows missing the new ID or pointing to the wrong product.
SELECT l.tenant_id, l.order_no, l.line_no, l.sku, l.product_id
FROM sales_order_line AS l
LEFT JOIN product_id AS p
       ON p.tenant_id = l.tenant_id
      AND p.product_id = l.product_id
      AND p.sku = l.sku
WHERE l.product_id IS NULL
   OR p.product_id IS NULL;
```

This query illustrates an **in-flight migration state**: `sales_order_line.product_id` does not exist in the initial DDL and must be added during the schema-expansion step first. An empty result verifies only that single reference relationship; check all other child tables, reconcile row counts, and verify tenant rules before finalizing.

Even upgrading `INTEGER` to `BIGINT` ripples through FKs and APIs. Reordering columns in a composite PK may require rebuilding indexes or constraints, so weigh query benefits against migration cost. Never rely on `ON UPDATE CASCADE` as a default fix for frequently changing business keys: cascading triggers large write fan-out and still fails to fix data already emitted outside the DB.

## 12. Common Pitfalls and Verification

| Pitfall | Impact | Remedy |
|---|---|---|
| Putting `UNIQUE(sku)` alone in a multi-tenant system | Two tenants cannot validly use the same code | Fix scope and use `UNIQUE(tenant_id, sku)` |
| Creating separate FKs for `tenant_id` and `sku` assuming same-tenant safety | Allows referencing another tenant's product | Use a composite FK to the matching composite key |
| Leaving part of a composite FK `NULL` assuming full FK check | `MATCH SIMPLE` skips parent lookup | Use `NOT NULL` or `MATCH FULL` per policy |
| Choosing a composite key just "to avoid an ID column" | Wide key values get duplicated across many FKs/indexes | Estimate and measure cost; consider surrogate + unique |
| Having PK `(tenant_id, order_no, line_no)` and adding an identical index | Duplicate index increasing storage and write cost | Inspect indexes created by PK before adding more |
| Assuming a composite index serves predicates on any column equally | Queries missing leading prefix may scan many pages | Use query stats and `EXPLAIN` to design indexes |
| Treating concatenated strings or hashes as absolute uniqueness | Delimiter/encoding clashes or hash collisions | Use native composite keys; if hashing for speed, verify raw values |
| Changing a business key without updating all FKs and consumers | Broken historical links and orphaned rows | Phased migration, reconciliation, and rollback testing |
| Assuming `VARCHAR(n)` takes `n` bytes | Misjudges storage/index limits under Unicode | Check charset, collation, real data, and DBMS limits |
| Assuming PK enforces tenant access control | Cross-tenant reads/writes still possible via API | Enforce authorization independently; use tenant constraints for consistency |

## 13. Practice Exercise: Choosing and Justifying Keys

**Context:** a multi-organization course management platform. Each organization uses a `student_code`; a student can enroll in the same course across multiple terms. Each enrollment stores status, enrollment timestamp, and final grade. The platform expects tens of millions of enrollment records, queried primarily by organization, student, course, and term.

Business requirements:

- Two organizations may reuse the same `student_code`; within one organization, a student code belongs to only one active student per published identity policy.
- Within a single term, a student has at most one enrollment per course; re-enrollment is allowed in subsequent terms.
- Student codes may be updated during legacy data cleanup, but enrollment history must remain linked.
- The system frequently retrieves a course's student roster by organization and term, and occasionally retrieves a student's history.

Tasks:

1. Identify the business keys of `student` and `enrollment`. Evaluate whether to use `student_id BIGINT` as PK; explain how to keep `UNIQUE(tenant_id, student_code)`.
2. Propose at least two designs for `enrollment`: a composite key (`tenant_id`, `student_id`, `course_id`, `term_id`) and a surrogate `enrollment_id` key with a corresponding `UNIQUE` constraint. State the conditions under which that combination truly suffices to distinguish enrollments.
3. Write the necessary FKs to prevent an enrollment from linking a student or course from another tenant. Explain why separate FKs to `student_id` and `course_id` do not automatically enforce same-tenant consistency if the child record also stores `tenant_id`.
4. Choose column ordering for an index serving "roster of students in a course for a term" and another for "a student's history". Identify which indexes are already created by `PRIMARY KEY`/`UNIQUE` to avoid duplicates.
5. Estimate the impact on foreign key and index size if a 64-character `student_code` were used instead of `student_id BIGINT`, and outline the measurements you would run on PostgreSQL/InnoDB.
6. Design test cases for same-tenant duplicates, cross-tenant code reuse, student code updates, FKs containing `NULL`, and migration scenarios.

### Physical Model Handoff Checklist

Before finalizing the schema, the designer must state clearly:

- **Identity:** which keys are minimal, uniqueness scope, and which columns can change or be `NULL`.
- **Relationships:** each FK references the right parent key tuple, and `MATCH SIMPLE`/`MATCH FULL` or equivalent rules are explicitly understood.
- **Width:** data types, lengths, charset/collation, child row counts, and index overhead are estimated and then measured on the real DBMS.
- **Queries:** column order aligns with critical filter prefixes and sort orders; no duplicate indexes mirror existing constraints.
- **Operations:** key update strategy, migration, rollback, and tests for cross-tenant corruption or orphaned foreign keys are ready.

Composite keys are a powerful tool for expressing **contextual uniqueness** and protecting relationships; key width and component ordering drive much of the physical cost. When you define identity scope clearly, measure costs across references and indexes, and protect business keys even when choosing surrogate keys, your schema stays both accurate and evolvable.
