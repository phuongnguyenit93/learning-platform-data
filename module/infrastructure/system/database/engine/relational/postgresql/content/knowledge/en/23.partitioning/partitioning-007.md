# Foreign Keys, Constraints, and Version Support in PostgreSQL Partitioning

*Table partitioning* allows a very large logical table to be stored across multiple smaller physical tables. PostgreSQL routes rows to matching partitions, skips irrelevant partitions during queries (*partition pruning*), and enables managing data by month, tenant, or value range.

Yet partitioning raises a question more important than speed: **do data constraints still protect the entire logical table, or only individual partitions?**

Consider an invoice system partitioned by month:

```text
                   invoice (partitioned parent)
                          PARTITION BY RANGE (issued_on)
                               │
              ┌────────────────┼─────────────────┐
              ▼                ▼                 ▼
       invoice_2026_10   invoice_2026_11   invoice_default
           October          November         other data

invoice_id = 42 can appear across multiple months.
```

If the primary key is solely `invoice_id`, can PostgreSQL enforce global uniqueness? Can an `invoice_line` table define a `FOREIGN KEY` referencing the parent `invoice`? How do `CHECK` and `NOT NULL` propagate to partitions? And how did support evolve from PostgreSQL 10, 11, and 12 through 17 and 18?

**Lesson focus:**

- Distinguish the **partition key** from **primary keys** and **foreign keys**.
- Understand why `PRIMARY KEY`/`UNIQUE` on a partitioned table must include all partition key columns and why that is **not a global unique index**.
- Design FKs from a partitioned table to a regular table, from a regular table to a partitioned table, and between two partitioned tables.
- Understand how `CHECK`, `NOT NULL`, partition bounds, default partitions, and constraint validation interact.
- Learn historical support milestones: **PostgreSQL 10 → 11 → 12 → 17 → 18**.
- Practice DDL, DML, catalog queries, intentional error cases, and migration planning.

This lesson belongs to the **Partitioning** chapter of the *Database Engine Relational PostgreSQL* module. Main examples target **PostgreSQL 18**, while clearly noting steps unsupported on older releases. As of writing in November 2026, PostgreSQL **19 is still in release candidate stage**, so do not treat pre-release features as guaranteed production behavior.

> Exact constraint capabilities on a **partitioned parent table** depend on PostgreSQL version, partition key structure, index access method, and constraint type. Never infer from a constraint succeeding on **one leaf partition** that it protects every other leaf.

---

## 1. Declarative Partitioning: One Logical Table, Many Physical Tables

In **declarative partitioning**, create the parent with `PARTITION BY`:

```sql
CREATE TABLE invoice (
    invoice_id BIGINT NOT NULL,
    issued_on DATE NOT NULL,
    amount NUMERIC(14, 2) NOT NULL
) PARTITION BY RANGE (issued_on);
```

Create partitions:

```sql
CREATE TABLE invoice_2026_10
PARTITION OF invoice
FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');

CREATE TABLE invoice_2026_11
PARTITION OF invoice
FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
```

Query:

```sql
SELECT *
FROM invoice
WHERE issued_on >= DATE '2026-11-01'
  AND issued_on < DATE '2026-12-01';
```

The parent is a logical object holding no heap tuples of its own; real rows live in leaf partitions. PostgreSQL routes an `INSERT INTO invoice` to the right partition and can prune irrelevant partitions when queries filter on the partition key.

### 1.1. Range Bounds Follow Half-Open Rules

With:

```sql
FOR VALUES FROM ('2026-10-01') TO ('2026-11-01')
```

the lower bound is **inclusive** and the upper bound is **exclusive**:

```text
2026-10-01 ≤ issued_on < 2026-11-01
```

Hence `2026-11-01` belongs to the November partition, not October.

### 1.2. PARTITION BY Does Not Imply PRIMARY KEY

```sql
PARTITION BY RANGE (issued_on)
```

only specifies which column **selects the partition**—it does not create `PRIMARY KEY (issued_on)`, create a unique constraint on that column, or restrict a date to appearing once.

### 1.3. Partitioning Types

| Type | Example | Rule |
|---|---|---|
| `RANGE` | `PARTITION BY RANGE (issued_on)` | Each partition holds a value interval |
| `LIST` | `PARTITION BY LIST (tenant_id)` | Each partition holds enumerated values |
| `HASH` | `PARTITION BY HASH (tenant_id)` | Picks partition by hash, modulus/remainder |

**`PARTITION BY HASH` is not `CREATE INDEX ... USING hash`.** One distributes rows across partitions; the other is an index access method.

## 2. Data Constraints You Must Distinguish

| Type | Purpose | Partitioning Question |
|---|---|---|
| `NOT NULL` | Forbids SQL `NULL` in column | Propagates to every partition? |
| `CHECK` | Validates per-row condition | Inherited? Same as partition bounds? |
| `PRIMARY KEY` | Identifies rows, non-null and unique | Must include the partition key? |
| `UNIQUE` | Forbids duplicate keys per `NULL` rules | Per-partition only, or entire logical table? |
| `FOREIGN KEY` | Enforces cross-table references | Which side can be referencing/referenced? |
| `EXCLUDE` | Forbids pairs of rows violating an operator check | Supported on parent, and since which version? |
| Partition bound | Governs which partition holds a row | What happens on missing partition or row move? |

To design cleanly, first identify **the exact scope where a business constraint holds**: system-wide, per tenant, per month, or per status group.

### 2.1. Scope Is Fundamental

Suppose `invoice_id=42` appears in both October and November:

- If business rules allow repeating IDs across months, `(issued_on, invoice_id)` can fit.
- If IDs must be unique **system-wide regardless of month**, partitioning by `issued_on` creates tension because parent-level uniqueness on `invoice_id` alone is unsupported under local-index mechanics.

Never paper over a business conflict by silently adding a month column to the PK if APIs and child tables still treat `invoice_id` as globally unique.

## 3. Why Must Parent UNIQUE/PRIMARY KEY Include the Partition Key?

PostgreSQL creates a **partitioned index** as metadata on the parent, plus matching physical indexes on each partition.

```text
                 UNIQUE on parent (metadata)
                                │
                   ┌────────────┴───────────┐
                   ▼                        ▼
         unique index partition 10  unique index partition 11
             sees October rows only     sees November rows only
```

A unique index on October cannot see values already stored in November.

Therefore, a parent `UNIQUE`/`PK` constraint can guarantee table-wide uniqueness only when **partition routing guarantees rows with the same unique key land in the exact same leaf partition**.

In declarative partitioning, PostgreSQL requires:

1. **All partition key columns must appear in the parent's `UNIQUE`/`PRIMARY KEY`.**
2. **The partition key must not contain expressions or function calls** when declaring such parent-level constraints.
3. Under **multi-level partitioning**, the constraint may need partition key columns from every level in the hierarchy per server rules.

Valid example:

```sql
CREATE TABLE invoice (
    invoice_id BIGINT NOT NULL,
    issued_on DATE NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    CONSTRAINT pk_invoice PRIMARY KEY (issued_on, invoice_id)
) PARTITION BY RANGE (issued_on);
```

Invalid example:

```sql
-- INTENTIONALLY INVALID: partition key issued_on
-- is missing from PRIMARY KEY.
CREATE TABLE invoice_bad (
    invoice_id BIGINT PRIMARY KEY,
    issued_on DATE NOT NULL
) PARTITION BY RANGE (issued_on);
```

This error is not caused by forgetting a manual index; the PK definition **violates partitioned-table rules**.

## 4. What Does a PRIMARY KEY Containing the Partition Key Guarantee?

With:

```sql
PRIMARY KEY (issued_on, invoice_id)
```

these two rows **cannot coexist**:

```text
(issued_on=2026-11-05, invoice_id=42)
(issued_on=2026-11-05, invoice_id=42)
```

Yet these two rows **are allowed**, because their composite keys differ:

```text
(issued_on=2026-10-05, invoice_id=42)
(issued_on=2026-11-05, invoice_id=42)
```

The constraint states only that the combination `(issued_on, invoice_id)` is unique. It **does not guarantee `invoice_id` alone is globally unique**.

### 4.1. The Composite Key Propagates Through the Data Model

If a line item references an invoice, `invoice_line` typically must store both `issued_on` and `invoice_id` to declare an FK targeting that PK.

Changing a PK from `invoice_id` to `(issued_on, invoice_id)` is a **data-contract change** impacting:

- Child tables.
- ORM entity ID / composite-key mappings.
- API URLs and public identifiers.
- `ON CONFLICT` clauses.
- Cache keys and message payloads.
- Deduplication / idempotency logic.
- `JOIN`s and index design.

Never treat adding the partition key to a PK as a harmless DDL tweak.

### 4.2. Does a Sequence-Generated ID Become Globally Unique Automatically?

`GENERATED ... AS IDENTITY` or a sequence issues incrementing numbers across partitions, yet **a generator is not a global `UNIQUE` constraint**:

- Explicit values can still be inserted where permitted.
- Data imports or restores from external sources can collide.
- Sequences can be reset or bypassed by multiple ID generators.
- Privileges or migrations can invalidate "never duplicates" assumptions.

If strict uniqueness is required, enforce an actual constraint within a supported scope rather than trusting an ID generator alone.

## 5. Leaf UNIQUE Differs from Parent UNIQUE

Suppose no parent `UNIQUE` exists and you create:

```sql
CREATE UNIQUE INDEX ux_invoice_2026_10_id
ON invoice_2026_10 (invoice_id);
```

This index protects October data only. An identical `invoice_id` can still live in November.

### 5.1. Physical Indexes per Partition

```text
invoice_2026_10: invoice_id=42   (allowed)
invoice_2026_11: invoice_id=42   (allowed)

Two separate leaf unique indexes cannot see each other.
```

To enforce a contract across the whole logical table:

```sql
ALTER TABLE invoice
ADD CONSTRAINT uq_invoice_date_id
UNIQUE (issued_on, invoice_id);
```

However, if the PK already covers those exact two columns, adding a redundant `UNIQUE` wastes index overhead.

### 5.2. No Standard Global Unique Index on Partitioned Tables

As of PostgreSQL 18, do not assume a unified unique B-tree exists storing **every `invoice_id` across all partitions**. A parent partitioned index is metadata over leaf indexes; partition-key restrictions still apply.

## 6. Expression Partition Keys Alter PK/UNIQUE Eligibility

PostgreSQL allows certain expression partition keys depending on expression properties and operator classes.

Conceptual example:

```sql
CREATE TABLE sample_by_mod (
    record_id BIGINT NOT NULL,
    payload TEXT
) PARTITION BY LIST ((record_id % 4));
```

Yet:

```sql
-- INTENTIONALLY INVALID:
ALTER TABLE sample_by_mod
ADD CONSTRAINT pk_sample_by_mod PRIMARY KEY (record_id);
```

You cannot assume that because `record_id` determines `record_id % 4`, a parent `UNIQUE`/`PK` will be accepted. When the partition key **uses an expression**, PostgreSQL restricts parent-level unique/primary key declarations.

### 6.1. Alternatives May Require Schema Changes

If a global business key must be `UNIQUE`, consider:

- Partitioning by that business key itself (if compatible with queries and retention).
- Maintaining an **unpartitioned** registry table holding the global unique key.
- Keeping an identity lookup table alongside a partitioned fact table.
- Separating logical identity from storage key with an explicit contract.
- Using a composite key if that genuinely reflects business uniqueness.

Each option trades off index size, retention simplicity, FK cost, and complexity.

## 7. Designing Global IDs with a Registry Table

A pattern when `external_id` must never duplicate regardless of month:

```sql
CREATE TABLE invoice_identity (
    external_id TEXT PRIMARY KEY,
    issued_on DATE NOT NULL,
    invoice_id BIGINT NOT NULL
);
```

The registry holds a unique B-tree on `external_id`. Transactions creating an invoice coordinate:

1. Insert an entry into the registry.
2. Insert the invoice into the matching partition.
3. Keep mappings aligned and roll back everything on failure.
4. Define deletion/retention policies so no dangling mappings accumulate.

This is a **design pattern**, not a complete production SQL snippet handling all write contention.

### 7.1. Trade-Offs

- The registry can grow very large even though `invoice` is time-partitioned.
- Keeping or cleaning mappings after dropping partitions requires clear retention rules.
- Any FK from registry to `invoice` must reference a valid key like `(issued_on, invoice_id)` on a supported version.
- Triggers or application writes must handle atomicity and retries cleanly.

**A registry backed by a real unique index** is far more reliable under concurrency than "`SELECT` to check existence then `INSERT`."

## 8. Two Roles of FOREIGN KEY: Referencing and Referenced

Distinguish the FK direction:

```text
    child table (referencing)
      FOREIGN KEY (...)
              │
              ▼
    parent table (referenced)
      PRIMARY KEY / UNIQUE (...)
```

The **referencing table** holds the FK columns. The **referenced table** holds the target key protected by an eligible unique/primary key or non-partial unique index.

With partitioning, four combinations arise:

| Referencing Table | Referenced Table | Meaning |
|---|---|---|
| Regular | Regular | Traditional FK |
| Partitioned | Regular | Leaf rows across partitions reference a regular parent |
| Regular | Partitioned | Regular table references a logical partitioned table's key |
| Partitioned | Partitioned | Both child and referenced tables are partitioned |

Support for these combinations did not arrive simultaneously across PostgreSQL 10/11/12.

## 9. Major Version Support History

This table covers core PostgreSQL **declarative partitioning**, not legacy inheritance partitioning or third-party extensions.

| Version | Key Milestone |
|---|---|
| **PostgreSQL 10** (2017) | Initial declarative RANGE/LIST partitioning; no parent-level `PK`/`UNIQUE` spanning the partition tree, and no FKs in either direction involving partitioned tables |
| **PostgreSQL 11** (2018) | Added parent `PK`/`UNIQUE` when including all partition key columns; added **FKs from a partitioned table to a regular table**; added HASH partitioning, default partitions, and cross-partition `UPDATE` row movement |
| **PostgreSQL 12** (2019) | Added **FKs referencing a partitioned table**; covered regular or partitioned tables referencing a partitioned parent under eligible rules |
| **PostgreSQL 13–16** | Continued refinements to FK/PK/UNIQUE; parent unique key restrictions stayed; parent-level `EXCLUDE` remained unsupported through 16 |
| **PostgreSQL 17** (2024) | Added **parent-level `EXCLUDE` constraints** requiring all partition keys with equality comparisons |
| **PostgreSQL 18** (2025) | Added **`NOT VALID` FKs on partitioned tables**, `NOT ENFORCED` for `CHECK`/FK, and enhancements to `NOT NULL`/temporal constraints; distinguish validation from enforcement states |
| **PostgreSQL 19** (as of 2026-11-14) | Currently at **RC2**; do not treat RC docs as a stable GA production baseline |

Minor releases and bug fixes still matter; always check exact `server_version` and release notes for your target deployment.

### 9.1. Checking the Version Directly on the Database

```sql
SELECT version();

SHOW server_version;
SHOW server_version_num;
```

Example gate check inside a migration script:

```sql
SELECT current_setting('server_version_num')::integer >= 120000
    AS supports_fks_referencing_partitioned_parent;
```

This is a **major feature gate check**, not a substitute for testing actual DDL statements, minor fixes, or environment differences.

### 9.2. Do Not Rely on psql Client Version Alone

`psql --version` shows your client binary version, not necessarily the target PostgreSQL server version. Always inspect `SHOW server_version_num` over the live connection when deciding DDL.

## 10. Main Lab: Monthly Invoice Schema

The following examples require **PostgreSQL 12+** for bidirectional FKs and work best on PostgreSQL 18. Use a fresh lab database or verify this schema holds no data you need to keep.

```sql
CREATE SCHEMA IF NOT EXISTS demo_part_fk;

CREATE TABLE demo_part_fk.customer (
    customer_id BIGINT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO demo_part_fk.customer (customer_id, customer_name)
VALUES
    (1, 'Customer A'),
    (2, 'Customer B'),
    (3, 'Customer C');
```

`customer` is unpartitioned with a table-wide PK.

### 10.1. Create the Partitioned Invoice Table

```sql
CREATE TABLE demo_part_fk.invoice (
    issued_on DATE NOT NULL,
    invoice_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'NEW',

    CONSTRAINT pk_demo_invoice
        PRIMARY KEY (issued_on, invoice_id),

    CONSTRAINT fk_demo_invoice_customer
        FOREIGN KEY (customer_id)
        REFERENCES demo_part_fk.customer(customer_id),

    CONSTRAINT ck_demo_invoice_amount
        CHECK (amount >= 0),

    CONSTRAINT ck_demo_invoice_status
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
)
PARTITION BY RANGE (issued_on);
```

Key details:

- `issued_on` is the partition key and part of the PK.
- `invoice_id` alone has **no global uniqueness guarantee**.
- FK `invoice.customer_id → customer.customer_id` is an **FK from a partitioned table to a regular table**, supported since PostgreSQL 11.
- `CHECK` and `NOT NULL` on the parent apply across partitions.
- `status` has a `DEFAULT`, which supplies a default value rather than constraining allowed values: `CHECK` enforces the allowed set.

### 10.2. Create Leaf Partitions

```sql
CREATE TABLE demo_part_fk.invoice_2026_10
PARTITION OF demo_part_fk.invoice
FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');

CREATE TABLE demo_part_fk.invoice_2026_11
PARTITION OF demo_part_fk.invoice
FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');

CREATE TABLE demo_part_fk.invoice_default
PARTITION OF demo_part_fk.invoice DEFAULT;
```

Parent constraints propagate down to partitions according to constraint type and server rules. Most physical indexes live on leaves, while a parent partitioned index holds no global heap TID tree across leaves.

### 10.3. Insert Valid Data

```sql
INSERT INTO demo_part_fk.invoice
    (issued_on, invoice_id, customer_id, amount, status)
VALUES
    (DATE '2026-10-10', 1001, 1, 450.00, 'NEW'),
    (DATE '2026-11-10', 1001, 2, 990.00, 'PAID'),
    (DATE '2026-11-12', 1002, 1, 120.00, 'NEW');
```

Notice `invoice_id=1001` appears in **two months** validly because the PK includes `issued_on`.

### 10.4. Inspect Partition Placement

```sql
SELECT
    tableoid::regclass AS physical_partition,
    issued_on,
    invoice_id,
    customer_id,
    amount,
    status
FROM demo_part_fk.invoice
ORDER BY issued_on, invoice_id;
```

`tableoid` reveals the physical relation holding each row. Never treat `tableoid` as a business identifier or assume partition names never change.

## 11. UNIQUE/PK Errors on Composite Key Collisions

On the lab data above:

```sql
-- INTENTIONAL ERROR: PK combination already exists.
INSERT INTO demo_part_fk.invoice
    (issued_on, invoice_id, customer_id, amount)
VALUES
    (DATE '2026-11-10', 1001, 3, 600.00);
```

SQLSTATE is `23505` — `unique_violation`, because `(2026-11-10,1001)` already exists.

Yet:

```sql
-- VALID under the composite PK, because the date differs:
INSERT INTO demo_part_fk.invoice
    (issued_on, invoice_id, customer_id, amount)
VALUES
    (DATE '2026-11-15', 1001, 3, 600.00);
```

`invoice_id` repeating within the same month on a **different day** is still permitted. If the business rule says "`invoice_id` is unique within a calendar month," `PK(issued_on,invoice_id)` fails to express that rule.

### 11.1. Align the Partition Key with the Real Uniqueness Scope

If the rule is "one invoice number per tenant per month," you may need an immutable `invoice_month` column as the partition key plus `UNIQUE (tenant_id, invoice_month, invoice_number)`. If an ID must be globally unique forever, never inject date/month into the business identity merely to satisfy PK syntax.

**Storage partitioning and business uniqueness must be designed together.**

## 12. FK from Partitioned Parent to Regular Table

The FK on `demo_part_fk.invoice`:

```sql
CONSTRAINT fk_demo_invoice_customer
FOREIGN KEY (customer_id)
REFERENCES demo_part_fk.customer(customer_id)
```

ensures every invoice has a valid `customer_id` in `customer`.

Test:

```sql
-- INTENTIONAL ERROR: customer_id=999 does not exist.
INSERT INTO demo_part_fk.invoice
    (issued_on, invoice_id, customer_id, amount)
VALUES
    (DATE '2026-11-16', 2001, 999, 50.00);
```

Raises `23503` — `foreign_key_violation`.

### 12.1. How Is the FK Enforced Across Leaves?

Declaring the constraint on the **partitioned parent** establishes the logical contract for every row in the hierarchy. PostgreSQL manages corresponding constraints/triggers across leaf partitions to reject invalid references.

You do not need custom per-month application triggers just because `invoice` is partitioned. Still, migrations and catalogs will show cloned/child constraints rather than a single entry as on a regular table.

### 12.2. FKs Do Not Auto-Create Referencing Indexes

`customer.customer_id` is a PK and has an index for referenced-key lookups.

However, `invoice.customer_id` on the referencing side **does not automatically get an index** from the FK. If querying invoices by customer or deleting/updating customers, consider:

```sql
CREATE INDEX idx_demo_invoice_customer
ON demo_part_fk.invoice (customer_id);
```

On a partitioned parent, this creates a parent partitioned index and matching child indexes. Weigh index cost across all partitions, not just one table.

## 13. FK from a Regular Table Referencing a Partitioned Parent

Since **PostgreSQL 12**, a regular table can reference an eligible PK/UNIQUE on a partitioned parent table.

Example:

```sql
CREATE TABLE demo_part_fk.invoice_receipt (
    receipt_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    invoice_issued_on DATE NOT NULL,
    invoice_id BIGINT NOT NULL,
    received_amount NUMERIC(14, 2) NOT NULL CHECK (received_amount >= 0),

    CONSTRAINT fk_receipt_invoice
        FOREIGN KEY (invoice_issued_on, invoice_id)
        REFERENCES demo_part_fk.invoice(issued_on, invoice_id)
);
```

Insert:

```sql
INSERT INTO demo_part_fk.invoice_receipt
    (invoice_issued_on, invoice_id, received_amount)
VALUES
    (DATE '2026-10-10', 1001, 150.00),
    (DATE '2026-11-10', 1001, 200.00);
```

These two receipts reference **two distinct invoices** because their issue dates differ.

### 13.1. Why Must the FK Include the Date?

```sql
-- INTENTIONALLY INVALID: no UNIQUE/PK
-- on invoice_id alone at the parent table.
CREATE TABLE demo_part_fk.receipt_wrong (
    receipt_id BIGINT PRIMARY KEY,
    invoice_id BIGINT NOT NULL
        REFERENCES demo_part_fk.invoice(invoice_id)
);
```

PostgreSQL cannot use non-unique `invoice_id` as an FK target. The issue isn't missing partition syntax; it is that the parent guarantees no uniqueness on `invoice_id` alone.

### 13.2. Referencing a Partitioned Parent Does Not Randomly Scan the Whole Tree

Because the referenced key includes `issued_on`, PostgreSQL can leverage partitioning and indexing when checking references. Still, actual cost depends on runtime triggers, version, partition count, indexes, cache, and workload. Inspect `EXPLAIN`/stats on a representative environment if FK checks become a bottleneck.

## 14. FK Between Two Partitioned Tables

We can partition `invoice_line` by the same `issued_on` key:

```sql
CREATE TABLE demo_part_fk.invoice_line (
    issued_on DATE NOT NULL,
    invoice_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    sku TEXT NOT NULL,
    qty INTEGER NOT NULL CHECK (qty > 0),
    unit_price NUMERIC(14, 2) NOT NULL CHECK (unit_price >= 0),

    CONSTRAINT pk_demo_invoice_line
        PRIMARY KEY (issued_on, invoice_id, line_no),

    CONSTRAINT fk_demo_line_invoice
        FOREIGN KEY (issued_on, invoice_id)
        REFERENCES demo_part_fk.invoice(issued_on, invoice_id)
        ON DELETE CASCADE
)
PARTITION BY RANGE (issued_on);
```

Create partitions:

```sql
CREATE TABLE demo_part_fk.invoice_line_2026_10
PARTITION OF demo_part_fk.invoice_line
FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');

CREATE TABLE demo_part_fk.invoice_line_2026_11
PARTITION OF demo_part_fk.invoice_line
FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');

CREATE TABLE demo_part_fk.invoice_line_default
PARTITION OF demo_part_fk.invoice_line DEFAULT;
```

Insert valid rows:

```sql
INSERT INTO demo_part_fk.invoice_line
    (issued_on, invoice_id, line_no, sku, qty, unit_price)
VALUES
    (DATE '2026-10-10', 1001, 1, 'PEN', 2, 20.00),
    (DATE '2026-10-10', 1001, 2, 'BOOK', 1, 35.00),
    (DATE '2026-11-10', 1001, 1, 'BAG', 1, 100.00);
```

Now both referencing and referenced tables are partitioned—fully supported on PostgreSQL **12+**.

### 14.1. A Wrong Date Fails the FK Even When invoice_id Exists

```sql
-- INTENTIONAL ERROR:
INSERT INTO demo_part_fk.invoice_line
    (issued_on, invoice_id, line_no, sku, qty, unit_price)
VALUES
    (DATE '2026-11-11', 1001, 1, 'MISMATCH', 1, 1.00);
```

Invoice `1001` exists on another date, yet **`(2026-11-11,1001)` does not exist**. The FK never hunts for "a nearby invoice with that ID"—it requires an exact referenced key match.

### 14.2. Co-Partitioning Does Not Eliminate All FK Cost

Sharing the same range key aids pruning and lifecycle management, yet FKs must still enforce integrity under concurrent `INSERT`/`UPDATE`/`DELETE`. Never assume "same month means FKs are free."

### 14.3. Watch Out for ON DELETE CASCADE

Deleting a valid invoice:

```sql
-- Run only after backing up lab data:
DELETE FROM demo_part_fk.invoice
WHERE issued_on = DATE '2026-10-10'
  AND invoice_id = 1001;
```

The `ON DELETE CASCADE` FK deletes matching lines. Yet if `invoice_receipt` still references that invoice with default `NO ACTION`, the `DELETE` is **blocked** rather than partially cascading and leaving the database inconsistent.

Test safely inside a rolled-back transaction to keep lab data intact:

```sql
BEGIN;
DELETE FROM demo_part_fk.invoice
WHERE issued_on = DATE '2026-10-10'
  AND invoice_id = 1001;
ROLLBACK;
```

If the `DELETE` errors, the transaction is aborted; `ROLLBACK` remains the right cleanup.

## 15. Composite FKs and NULL Rules

A composite foreign key:

```sql
FOREIGN KEY (issued_on, invoice_id)
REFERENCES demo_part_fk.invoice(issued_on, invoice_id)
```

defaults to `MATCH SIMPLE`: if **any** referencing column is `NULL`, the row skips checking for a referenced tuple.

Therefore, if business logic forbids "half-null references," declare `NOT NULL` on every referencing column, as done in `invoice_line` and `invoice_receipt`.

### 15.1. MATCH FULL

`MATCH FULL` requires either all referencing columns to be `NULL` or all to be non-null; mixing `NULL` and non-null is rejected. If a reference is always mandatory, `NOT NULL` is still required.

```sql
-- Syntax fragment:
FOREIGN KEY (issued_on, invoice_id)
REFERENCES demo_part_fk.invoice(issued_on, invoice_id)
MATCH FULL
```

This is a constraint definition snippet, not a standalone SQL statement.

## 16. FK Actions: NO ACTION, RESTRICT, CASCADE, SET NULL, SET DEFAULT

FK actions keep their standard data semantics when one or both tables are partitioned:

| Action | Meaning |
|---|---|
| `NO ACTION` | Checks constraint and rejects violation at check time |
| `RESTRICT` | Blocks changes to referenced keys when dependent rows exist under `RESTRICT` semantics |
| `CASCADE` | Propagates `DELETE`/`UPDATE` on key to referencing rows |
| `SET NULL` | Sets referencing columns to `NULL` per syntax/rules |
| `SET DEFAULT` | Sets default values, which must still satisfy FK/constraints |

### 16.1. Caution When the FK Includes the Partition Key

If `issued_on` is part of the FK and `invoice_line.issued_on` is `NOT NULL`, `ON DELETE SET NULL` trying to null out that column will fail `NOT NULL`. Make sure FK actions stay compatible with column constraints and partition routing.

### 16.2. ON UPDATE CASCADE Can Trigger Row Movement

When the referenced key includes issue date and an `UPDATE` shifts an invoice's date across partitions, `ON UPDATE CASCADE` must update referencing child rows as well—potentially moving them across partitions too. This is expensive and carries lock/serialization risks.

Best practice: **keep partition keys and identity keys immutable** wherever business rules allow. Never treat changing an invoice's issue date as a harmless update.

## 17. Parent CHECK and NOT NULL Are Inherited

In `demo_part_fk.invoice`:

```sql
amount NUMERIC(14, 2) NOT NULL,
CONSTRAINT ck_demo_invoice_amount CHECK (amount >= 0)
```

This applies to rows routed into `invoice_2026_10`, `invoice_2026_11`, and `invoice_default`.

### 17.1. Testing CHECK

```sql
-- INTENTIONAL ERROR (SQLSTATE 23514):
INSERT INTO demo_part_fk.invoice
    (issued_on, invoice_id, customer_id, amount)
VALUES
    (DATE '2026-11-20', 2500, 1, -1.00);
```

### 17.2. Testing NOT NULL

```sql
-- INTENTIONAL ERROR (SQLSTATE 23502):
INSERT INTO demo_part_fk.invoice
    (issued_on, invoice_id, customer_id, amount)
VALUES
    (DATE '2026-11-20', 2501, 1, NULL);
```

### 17.3. CHECK Passes UNKNOWN When a Column Is Nullable

If `amount` allows `NULL`, `CHECK (amount >= 0)` **does not reject `NULL`** because the expression evaluates to `UNKNOWN`. Declare `NOT NULL` explicitly to forbid `NULL`.

### 17.4. Do Not Arbitrarily Drop Inherited Constraints on a Leaf

You cannot drop an inherited parent `NOT NULL`/`CHECK` on a leaf as if it were independent. In declarative partitioning, parent-level `CHECK`/`NOT NULL` apply across the entire tree per version rules.

## 18. CHECK on an Individual Partition

Occasionally one partition needs stricter rules:

```sql
ALTER TABLE demo_part_fk.invoice_2026_11
ADD CONSTRAINT ck_november_positive_amount
CHECK (amount > 0);
```

Now:

- The parent requires only `amount >= 0`.
- The November partition additionally requires `amount > 0`.
- October rows are unaffected by November's extra constraint.

This is a **local** constraint, not a parent-wide rule. An API inserting `amount=0` into November is rejected while October still accepts it.

### 18.1. Avoid Accidental Inconsistency

Valid local constraints can help during migrations, yet make table behavior vary by month. Document the rationale, rollout plan, and when the shared rule moves up to the parent.

## 19. Partition Bounds vs. Custom CHECK Constraints

A partition:

```sql
CREATE TABLE demo_part_fk.invoice_2026_12
PARTITION OF demo_part_fk.invoice
FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');
```

already gives the engine its **range constraint** for routing and pruning. You do not need to add:

```sql
CHECK (issued_on >= DATE '2026-12-01'
       AND issued_on < DATE '2027-01-01')
```

for the partition to have valid bounds.

However, when **attaching a pre-populated table**, a matching validated `CHECK` helps PostgreSQL prove the rows lie within bounds without scanning the entire table.

### 19.1. Pruning Is Not FK Validation

- **Partition pruning:** planner/executor reduces which partitions to read based on query predicates.
- **Constraint exclusion:** technique using `CHECK`s to eliminate relations when provably disjoint.
- **FK validation:** ensures referencing rows point to valid referenced keys.
- **Unique enforcement:** prevents key collisions within constraint scope.

All four relate to queries and integrity, yet **none replaces another**.

## 20. DEFAULT Partition: Prevents Routing Errors, Does Not Bypass Constraints

We already created:

```sql
CREATE TABLE demo_part_fk.invoice_default
PARTITION OF demo_part_fk.invoice DEFAULT;
```

Inserting a date outside the two declared months:

```sql
INSERT INTO demo_part_fk.invoice
    (issued_on, invoice_id, customer_id, amount)
VALUES
    (DATE '2027-02-01', 3001, 1, 5.00);
```

routes to the default partition, **and still enforces PK/FK/CHECK/NOT NULL**.

### 20.1. What Without DEFAULT?

When no partition matches, `INSERT INTO partitioned_parent` raises a routing error. PostgreSQL does not auto-create next month's partition unless external orchestration or extensions do so.

### 20.2. DEFAULT Is Not an "Unchecked Trash Bin"

Rows inside `DEFAULT` are still part of the logical parent, affecting uniqueness, FKs, and parent `SELECT`s. Having `DEFAULT` helps smooth ingestion, yet requires monitoring row counts and a workflow to split rows out into properly bounded partitions.

### 20.3. Adding a New Partition When DEFAULT Holds Rows

If you add February 2027 while `invoice_default` already holds February 2027 rows, PostgreSQL must ensure no rows conflict with the new partition's bounds; the operation requires scanning/locking or pre-migrating those rows first.

Never treat `CREATE TABLE ... PARTITION OF` or `ATTACH PARTITION` as an unconditional O(1) operation when a default partition exists.

## 21. ATTACH PARTITION: Checking Old Data and Constraints

One workflow loads a standalone table, builds constraints/indexes, and attaches it to the parent.

Example **for an isolated lab only** to avoid colliding with existing Oct/Nov partitions:

```sql
CREATE TABLE demo_part_fk.invoice_stage_2027_01
    (LIKE demo_part_fk.invoice INCLUDING DEFAULTS INCLUDING CONSTRAINTS);

ALTER TABLE demo_part_fk.invoice_stage_2027_01
ADD CONSTRAINT ck_invoice_stage_jan_bound
CHECK (
    issued_on >= DATE '2027-01-01'
    AND issued_on < DATE '2027-02-01'
);
```

`LIKE` on a partitioned table copies the requested columns/attributes—it does not magically clone the whole tree or all constraints/indexes/FKs. Inspect the staging table's schema explicitly.

### 21.1. Load Valid Staging Data

```sql
INSERT INTO demo_part_fk.invoice_stage_2027_01
    (issued_on, invoice_id, customer_id, amount, status)
VALUES
    (DATE '2027-01-05', 8001, 1, 100.00, 'NEW');
```

An independent staging table may lack parent FKs/PKs unless declared; validate staging data before attaching rather than assuming a successful `INSERT` guarantees parent compliance.

### 21.2. Attach to the Parent

```sql
ALTER TABLE demo_part_fk.invoice
ATTACH PARTITION demo_part_fk.invoice_stage_2027_01
FOR VALUES FROM ('2027-01-01') TO ('2027-02-01');
```

PostgreSQL verifies schema, bound constraints, and matching indexes/constraints, and may scan data without sufficient constraint proof. When a parent has `DEFAULT`, it checks `DEFAULT` as well.

**Important:** `ATTACH PARTITION` never bypasses PK/FK/CHECK. It is a DDL command that can hold locks and validate data depending on state.

### 21.3. A Prevalidated CHECK Can Reduce Scans

A valid `CHECK` matching the target bounds lets the server skip scanning the staging table to prove rows fit the new partition. Yet it does not guarantee zero scans/locks on all related tables—especially if `DEFAULT` or other constraints are involved.

### 21.4. Never Use CHECK NOT VALID as Proof of Clean Data

A `CHECK` marked `NOT VALID` does not prove existing rows comply, so it cannot substitute for a validated constraint in attach optimizations.

## 22. DETACH PARTITION and FK/Retention Risks

Logical example:

```sql
ALTER TABLE demo_part_fk.invoice
DETACH PARTITION demo_part_fk.invoice_2026_10;
```

After detaching, October becomes a standalone relation outside the logical parent. This affects:

- Rows visible when querying the parent.
- Data protected by FKs/unique constraints in the partition hierarchy.
- Referential-action paths when other tables reference the parent.
- Retention and audit consistency.
- Dependent objects, constraints, and indexes on the partition.

**Never assume `DETACH` is always allowed or leaves FKs unaffected.** PostgreSQL can reject it if dependencies or referential constraints disallow it, with exact behavior varying by version and structure.

### 22.1. Retention Must Protect Referential Integrity

If `invoice_receipt` references October invoices, dropping or detaching October is not just deleting an old file. Plan how to handle receipts, lines, legal holds, orphan states, and concurrent transactions.

Some designs partition **both facts and dependent tables by the same retention key**, while others retain key registries or archives longer than invoice payloads.

### 22.2. DETACH CONCURRENTLY Is a Separate Topic

Some versions support `DETACH PARTITION CONCURRENTLY` with restrictions on transactions, default partitions, and constraints/dependencies. Never put it into a migration without confirming compatibility with the table, FKs, default partition, and runtime window.

## 23. ON CONFLICT on Partitioned Tables

PostgreSQL supports `INSERT ... ON CONFLICT` against valid unique constraints/indexes.

With parent `PK (issued_on, invoice_id)`:

```sql
INSERT INTO demo_part_fk.invoice
    (issued_on, invoice_id, customer_id, amount, status)
VALUES
    (DATE '2026-11-10', 1001, 2, 990.00, 'PAID')
ON CONFLICT (issued_on, invoice_id)
DO NOTHING;
```

This conflict target matches the parent's unique key. It **does not** catch "same `invoice_id` on a different date," because those rows do not conflict on the unique key.

### 23.1. No Parent UNIQUE(invoice_id)

```sql
-- INTENTIONAL ERROR: no unique arbiter
-- on invoice_id alone at the parent.
INSERT INTO demo_part_fk.invoice
    (issued_on, invoice_id, customer_id, amount)
VALUES (DATE '2026-11-13', 1001, 1, 100.00)
ON CONFLICT (invoice_id)
DO UPDATE SET amount = EXCLUDED.amount;
```

PostgreSQL cannot infer uniqueness per `invoice_id` across dates. Change the conflict target or the schema design.

### 23.2. Do Not Shift the Partition Key via DO UPDATE Without Checking Limits

`ON CONFLICT DO UPDATE` on a partitioned parent has restrictions when the update would **move the conflicting row to a different partition**. Do not treat it as identical to a standard `UPDATE` with row movement.

If business logic must modify issue dates, verify version behavior, triggers, and FK dependents—and prefer immutable partition keys.

## 24. FKs and Constraint Locking on DELETE/UPDATE of Referenced Rows

When deleting or updating a referenced key, PostgreSQL must verify no referencing rows violate `ON DELETE`/`ON UPDATE` rules.

With:

```sql
DELETE FROM demo_part_fk.customer
WHERE customer_id = 1;
```

`invoice` holds an FK to `customer`. Because referencing invoices exist and the default action is `NO ACTION`, `DELETE` is rejected.

### 24.1. Referencing Column Indexes Are Usually Crucial

PostgreSQL auto-creates indexes for referenced PK/UNIQUE keys. On the referencing side, evaluate adding an index:

```sql
CREATE INDEX idx_demo_invoice_customer
ON demo_part_fk.invoice (customer_id);
```

If this index was already created in an earlier step, do not recreate the same name. In production, weigh FK check cost, parent `DELETE`/`UPDATE` frequency, and query patterns.

### 24.2. One Parent FK Can Touch Many Partitions

Deleting or updating a referenced row may check references across many leaf partitions—especially when the referencing partition key is absent from the lookup condition. Excessive partition counts inflate catalog, trigger, and planning overhead.

Never choose partitioning purely by table size while ignoring FK maintenance frequency and partition counts.

## 25. DEFERRABLE FKs vs. DEFERRABLE Transactions

`DEFERRABLE` on a foreign key defers constraint checking per constraint rules:

```sql
CREATE TABLE demo_part_fk.review_link (
    review_id BIGINT PRIMARY KEY,
    issued_on DATE NOT NULL,
    invoice_id BIGINT NOT NULL,
    CONSTRAINT fk_review_invoice
        FOREIGN KEY (issued_on, invoice_id)
        REFERENCES demo_part_fk.invoice(issued_on, invoice_id)
        DEFERRABLE INITIALLY IMMEDIATE
);
```

Inside a transaction:

```sql
BEGIN;

SET CONSTRAINTS fk_review_invoice DEFERRED;

-- Perform changes ensuring the constraint holds by commit.
-- Example only; use when data ordering and rollback are understood.

ROLLBACK;
```

`SET CONSTRAINTS` affects eligible deferrable FKs. It **does not** allow an invalid FK state to commit.

### 25.1. NO ACTION vs. RESTRICT on Deferrability

`NO ACTION` can be deferred when the constraint is declared `DEFERRABLE` and conditions permit. `RESTRICT` enforces stricter immediate semantics and cannot be deferred the same way as `NO ACTION`.

### 25.2. Do Not Confuse with SERIALIZABLE READ ONLY DEFERRABLE

`BEGIN ISOLATION LEVEL SERIALIZABLE READ ONLY DEFERRABLE` is a **transaction attribute for obtaining a safe snapshot**. It is completely unrelated to `FOREIGN KEY ... DEFERRABLE` check timing.

## 26. NOT VALID and VALIDATE CONSTRAINT: Crucial for Migrations

When adding an FK to a table with millions of rows, validating all existing rows inside `ADD CONSTRAINT` causes heavy waits and locks.

PostgreSQL supports:

```sql
ALTER TABLE some_table
ADD CONSTRAINT fk_something
FOREIGN KEY (...)
REFERENCES other_table (...)
NOT VALID;
```

Followed by:

```sql
ALTER TABLE some_table
VALIDATE CONSTRAINT fk_something;
```

With `NOT VALID`, PostgreSQL **skips scanning old rows during `ADD`** while still **enforcing the constraint on new `INSERT`/`UPDATE`s**. `VALIDATE` checks existing rows later and marks the constraint validated if clean.

### 26.1. Key Version Milestone

For **foreign keys on partitioned tables**, parent-level `NOT VALID` support was added in **PostgreSQL 18**. On PostgreSQL 12–17, do not assume the exact same workflow works on a partitioned parent even though regular FKs are supported.

### 26.2. PG18+ Example

```sql
-- Run only on PostgreSQL 18+ in an appropriate lab schema.
ALTER TABLE demo_part_fk.invoice_line
ADD CONSTRAINT fk_line_sku_catalog
FOREIGN KEY (sku)
REFERENCES demo_part_fk.sku_catalog(sku)
NOT VALID;
```

This assumes `sku_catalog` **already exists**. To run it completely:

```sql
CREATE TABLE demo_part_fk.sku_catalog (
    sku TEXT PRIMARY KEY
);

INSERT INTO demo_part_fk.sku_catalog (sku)
VALUES ('PEN'), ('BOOK'), ('BAG');
```

Create the catalog **before** `ALTER TABLE ... ADD CONSTRAINT`. If `invoice_line` already contains other SKUs in lab data, clean them up before validation can succeed.

Then:

```sql
ALTER TABLE demo_part_fk.invoice_line
VALIDATE CONSTRAINT fk_line_sku_catalog;
```

### 26.3. NOT VALID Does Not Work for UNIQUE the Same Way as FK

There is no general workaround like:

```sql
-- INTENTIONALLY INVALID:
ALTER TABLE demo_part_fk.invoice
ADD CONSTRAINT uq_invoice_id UNIQUE (invoice_id) NOT VALID;
```

Two issues: `UNIQUE(invoice_id)` lacks the partition key, and `NOT VALID` cannot defer uniqueness checks the way it does for FK/CHECK.

## 27. NOT ENFORCED (PostgreSQL 18) Differs from NOT VALID

This is a critical distinction:

| Attribute | Core Meaning |
|---|---|
| `NOT VALID` | Enforced on new/modified rows; **existing rows not yet fully validated** |
| `VALIDATE CONSTRAINT` | Scans existing rows and marks validated if clean |
| `NOT ENFORCED` (PG18+) | Declares the constraint metadata **without asking PostgreSQL to check violations** for supported types |
| `ENFORCED` | Constraint is actively enforced per its semantics |

PostgreSQL 18 supports `NOT ENFORCED` for **CHECK and FOREIGN KEY**. It does **not** mean "validate later" like `NOT VALID`.

### 27.1. Syntax Pattern

```sql
-- PostgreSQL 18+; syntax illustration only, do not run casually:
CREATE TABLE demo_part_fk.external_import (
    row_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_import_customer
        FOREIGN KEY (customer_id)
        REFERENCES demo_part_fk.customer(customer_id)
        NOT ENFORCED
);
```

A `NOT ENFORCED` constraint **does not protect data like an enforced FK**. Never cite it as proof of strict referential integrity.

### 27.2. Why Does NOT ENFORCED Exist?

Some workflows need metadata documentation/compatibility or multi-step schema transitions before turning enforcement on. Using it requires an explicit validation and migration plan.

If business logic must prevent orphan rows, use an enforced constraint; never leave `NOT ENFORCED` around merely because DDL "succeeded."

## 28. SQLSTATEs and Errors to Distinguish

| SQLSTATE | Name | Scenario |
|---|---|---|
| `23505` | `unique_violation` | Duplicate valid PK/UNIQUE |
| `23503` | `foreign_key_violation` | Referenced key missing, or `DELETE`/`UPDATE` violates FK |
| `23514` | `check_violation` | `CHECK` failed; certain partition check failures |
| `23502` | `not_null_violation` | `NOT NULL` column received `NULL` |
| `42P16` | `invalid_table_definition` | Invalid table/partition/PK definition |
| `0A000` | `feature_not_supported` | Unsupported DDL/feature combination for version |
| `23001` | `restrict_violation` | PostgreSQL 18 changed certain `RESTRICT` FK violations to this SQLSTATE |

Never build application error handlers purely on English error text that can change. PostgreSQL JDBC exposes `SQLException#getSQLState()` for reliable classification.

### 28.1. One Statement Error Aborts the Transaction

```sql
BEGIN;

-- Intentional error statement:
INSERT INTO demo_part_fk.invoice
    (issued_on, invoice_id, customer_id, amount)
VALUES (DATE '2026-11-10', 1001, 1, 1.00);

-- Transaction stays aborted until ROLLBACK
-- or rolling back to a valid savepoint.

ROLLBACK;
```

When testing multiple error cases, use separate transactions or savepoints so secondary `25P02` errors don't mask the original cause.

## 29. EXCLUDE Constraints on Partitioned Parents: PostgreSQL 17+

**`EXCLUDE`** forbids any pair of rows for which all specified operator comparisons evaluate true simultaneously.

A room-booking application might require:

> Within the same tenant and room, no two booking intervals may overlap.

Starting in PostgreSQL **17**, `EXCLUDE` can be declared on a partitioned parent **if**:

1. It includes **all partition key columns**.
2. Partition key columns use **equality (`=`)**, never overlap `&&` on the partition key itself.
3. Remaining columns use compatible operators/index methods.

### 29.1. Tenant-Partitioned Example

```sql
-- Run only on PostgreSQL 17+ in a lab database.
-- btree_gist provides GiST equality support for common scalar types.
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE demo_part_fk.room_booking (
    tenant_id INTEGER NOT NULL,
    booking_id BIGINT NOT NULL,
    room_id INTEGER NOT NULL,
    during TSTZRANGE NOT NULL,

    CONSTRAINT pk_room_booking
        PRIMARY KEY (tenant_id, booking_id),

    CONSTRAINT ex_room_booking_no_overlap
        EXCLUDE USING gist (
            tenant_id WITH =,
            room_id WITH =,
            during WITH &&
        )
)
PARTITION BY LIST (tenant_id);

CREATE TABLE demo_part_fk.room_booking_t1
PARTITION OF demo_part_fk.room_booking FOR VALUES IN (1);

CREATE TABLE demo_part_fk.room_booking_t2
PARTITION OF demo_part_fk.room_booking FOR VALUES IN (2);
```

Here `tenant_id` appears in `EXCLUDE` with `=`. Two overlapping bookings for the same tenant and room are blocked; different tenants live in separate partitions, matching the equality boundary.

### 29.2. Invalid Case: Partitioned by Start Date While Forbidding Cross-Month Overlap

Suppose bookings are partitioned by `booking_start` month, while policy forbids **any overlapping intervals regardless of start date**. Leaf-level `EXCLUDE` checks can miss intervals spanning across two months.

Adding the partition key with `=` would only forbid overlaps sharing **the exact same `booking_start`**, not all overlaps. Never assume parent `EXCLUDE` automatically solves time overlaps crossing partition boundaries.

### 29.3. Version-Specific Feature

Prior to PostgreSQL 17, parent-level `EXCLUDE` spanning a partitioned table was unsupported in this way; leaf-level `EXCLUDE` only guarded each leaf individually. On 17+, the partition-key equality requirements remain mandatory.

## 30. Temporal Constraints in PostgreSQL 18: Do Not Confuse with Regular PKs

PostgreSQL 18 adds syntax for **temporal primary/unique keys** and **temporal foreign keys**, such as `WITHOUT OVERLAPS` and `PERIOD`.

Points to keep in mind for partitioning:

- Temporal constraints carry **specific rules** for range/multirange types and overlap operators.
- They **do not eliminate partition-key restrictions** on parent-level constraints.
- Never replace ordinary PK/FKs with temporal constraints without verifying exact business semantics.
- When deploying on PG18, check exact minor-version docs, partition key types, and tree propagation behavior.

### 30.1. Unchanged Core Semantics

A temporal PK expresses "valid-time ranges for the same identity must not overlap," unlike a scalar `PK(issued_on, invoice_id)` which only prevents exact value-pair duplicates.

If business logic simply needs an invoice with a date and ID, stick with a standard scalar composite PK rather than adding temporal syntax just because the server supports it.

## 31. Deferrable UNIQUE and ON CONFLICT

PostgreSQL supports deferrable unique constraints, yet **`ON CONFLICT DO UPDATE`** requires a compatible arbiter index/constraint and does not treat every deferred uniqueness constraint like an immediate unique index.

On partitioned tables:

- Constraints must satisfy partition-key rules.
- The arbiter must match the conflict target.
- Never extrapolate from a leaf unique index to a parent unique arbiter.
- Modifying the partition key inside `DO UPDATE` still hits row-movement limits.

When idempotent upserts are required, prefer a **simple, immediately enforced unique key** aligned with the partition key, or an unpartitioned registry guarding global business IDs.

## 32. Multi-Level Partitioning: Every Level Matters

Conceptual hierarchy:

```text
invoice
PARTITION BY RANGE (issued_on)
    │
    └── invoice_2026_11
        PARTITION BY HASH (tenant_id)
            │
            ├── remainder 0
            └── remainder 1
```

Declaring a parent-level PK must account for **all partition key columns across the entire involved hierarchy**, not only the root key.

A design may require:

```sql
PRIMARY KEY (issued_on, tenant_id, invoice_id)
```

when two levels partition by `issued_on` and `tenant_id`. Omitting `tenant_id` fails to protect uniqueness across hash leaves within the same month.

### 32.1. Watch Out for Expression Subpartition Keys

If any level uses an expression partition key, it can restrict parent-level `PK`/`UNIQUE` declarations. Never design a multi-level tree and leave PKs until the end without testing DDL feasibility up front.

## 33. Inspecting Constraint Metadata on Parent and Leaves

PostgreSQL stores relation, partition, and constraint details in system catalogs.

### 33.1. View the Partition Tree

```sql
SELECT *
FROM pg_partition_tree('demo_part_fk.invoice'::regclass);
```

`pg_partition_tree` is available in modern PostgreSQL (12+); it will not run on PG10/11.

Output shows relations in the tree, immediate parents, hierarchy depth, and leaf flags.

### 33.2. View Partition Bounds

```sql
SELECT
    c.oid::regclass AS relation_name,
    c.relkind,
    pg_get_expr(c.relpartbound, c.oid) AS partition_bound
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = 'demo_part_fk'
  AND c.relispartition
ORDER BY c.relname;
```

`relkind='p'` marks a partitioned table; `relkind='r'` is a regular table. An intermediate subpartitioned child also has `relkind='p'`.

### 33.3. View Constraints and convalidated

```sql
SELECT
    con.conrelid::regclass AS on_table,
    con.conname,
    con.contype,
    con.convalidated,
    con.condeferrable,
    con.condeferred,
    CASE
        WHEN con.confrelid <> 0
        THEN con.confrelid::regclass::text
        ELSE NULL
    END AS referenced_table,
    pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint AS con
JOIN pg_namespace AS ns ON ns.oid = con.connamespace
WHERE ns.nspname = 'demo_part_fk'
ORDER BY on_table, conname;
```

`contype` codes:

| Value | Constraint |
|---|---|
| `p` | `PRIMARY KEY` |
| `u` | `UNIQUE` |
| `f` | `FOREIGN KEY` |
| `c` | `CHECK` |
| `x` | `EXCLUDE` |
| `n` | `NOT NULL` in PostgreSQL 18+ new catalog representation |

On older versions, `NOT NULL` does not appear this way in `pg_constraint`. Never query newer catalog columns on older servers without checking version first.

### 33.4. How Are Cloned Child Constraints Linked?

In modern PostgreSQL, `pg_constraint.conparentid` shows child constraints inherited/cloned from a parent constraint. Never assume "N FK rows in the catalog means the app declared N distinct foreign keys" without understanding the partition hierarchy.

```sql
SELECT
    con.oid,
    con.conrelid::regclass AS on_table,
    con.conname,
    con.conparentid,
    con.convalidated
FROM pg_constraint AS con
WHERE con.connamespace = 'demo_part_fk'::regnamespace
ORDER BY con.conrelid::regclass::text, con.conname;
```

Check catalog schemas and privileges for your version; avoid migration logic tied rigidly to auto-generated constraint names that can change across upgrades.

## 34. PostgreSQL 18: Reading conenforced

PostgreSQL 18 adds `pg_constraint.conenforced` reflecting constraint enforcement status.

```sql
-- PostgreSQL 18+ only:
SELECT
    conrelid::regclass AS on_table,
    conname,
    contype,
    convalidated,
    conenforced,
    pg_get_constraintdef(oid)
FROM pg_constraint
WHERE connamespace = 'demo_part_fk'::regnamespace
ORDER BY on_table, conname;
```

Inspection and migration tools must distinguish **validated** from **enforced**. Do not query `conenforced` on PG17 and think the catalog is broken.

## 35. Foreign Key Indexes: Often Underestimated Cost

One parent FK across hundreds of partitions creates many underlying constraint/trigger structures. Operations such as:

- Adding an FK to an existing partition tree.
- Adding a new leaf partition.
- Deleting a referenced row with many children.
- Updating a referenced key.
- Detaching/dropping old partitions.
- Schema/dump restores.

should all be benchmarked and planned relative to partition count and referencing row volume.

### 35.1. Indexing Multi-Column FKs

For:

```sql
FOREIGN KEY (issued_on, invoice_id)
REFERENCES invoice(issued_on, invoice_id)
```

a matching referencing index is often:

```sql
CREATE INDEX idx_line_invoice_fk
ON demo_part_fk.invoice_line (issued_on, invoice_id);
```

Yet because `invoice_line` already has `PK(issued_on, invoice_id, line_no)`, **the PK B-tree already leads with those two columns** and serves most FK lookups without needing a redundant index. Check actual query patterns before adding extra indexes.

### 35.2. FKs Do Not Have to Share the Same Partition Strategy

A referenced parent can be time-partitioned while a referencing table is tenant-partitioned, provided the FK is valid and version-supported. Still, lookup/scan cost may rise if FK parameters cannot prune partitions.

Align partition keys when lifecycle and query access benefit—**never assume matching partition strategies is a mandatory FK rule**.

## 36. Updating the Partition Key and Atomicity

Since PostgreSQL 11, `UPDATE` can move a row from an old partition to a new partition under eligible conditions.

Lab example:

```sql
BEGIN;

UPDATE demo_part_fk.invoice
SET issued_on = DATE '2026-11-25'
WHERE issued_on = DATE '2026-11-12'
  AND invoice_id = 1002;

ROLLBACK;
```

Because `issued_on` is part of the PK, changing it **mutates the FK-referenced identity**. If referencing rows exist, `NO ACTION` blocks the `UPDATE` or `ON UPDATE CASCADE` must update dependents.

### 36.1. Row Movement Does Not Bypass FK Semantics

PostgreSQL never skips constraints simply because the destination is a different partition. The destination must match valid bounds, satisfy constraints, and maintain referential integrity.

### 36.2. Concurrency

Row movement can race with concurrent `DELETE`/`UPDATE`s in other sessions and trigger serialization errors. Applications need clean transaction boundaries, retry logic, and idempotency rather than assuming an `UPDATE` never conflicts.

## 37. Adding a Constraint on the Parent: Impact on Every Leaf

To add a status rule:

```sql
ALTER TABLE demo_part_fk.invoice
ADD CONSTRAINT ck_invoice_status_strict
CHECK (status IN ('NEW', 'PAID', 'CANCELLED'));
```

The lab parent already has an equivalent `CHECK`, so this example is **redundant by design** and does not need to be run. What matters is that parent DDL can:

- Scan existing data across many partitions.
- Hold locks throughout schema changes.
- Propagate constraints down to all leaves.
- Impact concurrent writers.
- Apply automatically to future partitions.

### 37.1. CHECK NOT VALID Can Aid Migrations

```sql
ALTER TABLE demo_part_fk.invoice
ADD CONSTRAINT ck_invoice_amount_ceiling
CHECK (amount <= 100000000)
NOT VALID;
```

New `INSERT`/`UPDATE`s must obey the enforced `CHECK`, while existing rows avoid being scanned during `ADD`. Once legacy data is clean:

```sql
ALTER TABLE demo_part_fk.invoice
VALIDATE CONSTRAINT ck_invoice_amount_ceiling;
```

Exact locking and propagation behavior depends on version; test on staging with realistic partition counts before production.

## 38. Migrating from a Regular Table to a Partitioned Table

An existing regular table may have:

```sql
PRIMARY KEY (invoice_id)
```

and numerous FKs referencing `invoice_id`. If partitioning by date:

```sql
PARTITION BY RANGE (issued_on)
```

you cannot keep `PK(invoice_id)` alone on the parent under current rules.

### 38.1. Questions to Resolve Before Migrating

1. **Must the ID be globally unique?**
2. **Should the partition key be issue date or creation timestamp?**
3. **Do child tables already carry the corresponding date?**
4. **Can all FKs migrate to composite keys?**
5. **Do APIs and ORMs handle composite identities cleanly?**
6. **Are single-column `invoice_id` lookups still required?**
7. **Does a registry or lookup table serve as source of truth?**
8. **Could retention purge referenced rows before referencing rows?**
9. **Does the target version support full FKs and `NOT VALID` migrations?**
10. **Can dual-write, backfill, and validation run safely?**

### 38.2. Migration Workflow

```text
Audit schema + FK graph
           │
           ▼
Choose partition key & business identity
           │
           ▼
Design valid parent PK/UNIQUE
           │
           ▼
Create parent + partitions + constraints
           │
           ▼
Backfill data & verify uniqueness
           │
           ▼
Create/migrate FKs per version support
           │
           ▼
Validate data & concurrency tests
           │
           ▼
Controlled application cutover
           │
           ▼
Monitor FK errors, latency, DDL/locks
```

There is no single `ALTER TABLE original PARTITION BY ...` command that automatically converts a regular table into an equivalent partitioned parent in modern PostgreSQL. Migrations require creating new structures or alternative architectures while preserving integrity across cutover.

## 39. Pitfalls of Replacing Constraints with Triggers

When hitting parent-level `UNIQUE(invoice_id)` limits, people sometimes propose a trigger:

```text
BEFORE INSERT:
  SELECT 1 FROM invoice WHERE invoice_id = NEW.invoice_id;
  If absent: allow INSERT.
```

This is **insufficient** to enforce uniqueness under two concurrent transactions:

1. Transaction A checks and sees no matching ID.
2. Transaction B checks and also sees no matching ID.
3. Both insert into different partitions.
4. No global unique constraint forces either transaction to fail.

### 39.1. When a Global Invariant Is Truly Required

Use reliable concurrency control—such as a unique registry table, proven advisory/explicit locking protocols, or a different partition strategy.

**A trigger never turns an existence `SELECT` into serializable uniqueness enforcement.**

## 40. Partitioning by tenant_id: A Natural Fit for Per-Tenant Uniqueness

If the business key is "`order_code` unique within a tenant," partitioning by tenant aligns cleanly with `PK`/`UNIQUE`:

```sql
CREATE TABLE demo_part_fk.tenant_order (
    tenant_id INTEGER NOT NULL,
    order_code TEXT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL CHECK (amount >= 0),
    CONSTRAINT pk_tenant_order PRIMARY KEY (tenant_id, order_code)
)
PARTITION BY HASH (tenant_id);
```

Create hash partitions:

```sql
CREATE TABLE demo_part_fk.tenant_order_p0
PARTITION OF demo_part_fk.tenant_order
FOR VALUES WITH (MODULUS 4, REMAINDER 0);

CREATE TABLE demo_part_fk.tenant_order_p1
PARTITION OF demo_part_fk.tenant_order
FOR VALUES WITH (MODULUS 4, REMAINDER 1);

CREATE TABLE demo_part_fk.tenant_order_p2
PARTITION OF demo_part_fk.tenant_order
FOR VALUES WITH (MODULUS 4, REMAINDER 2);

CREATE TABLE demo_part_fk.tenant_order_p3
PARTITION OF demo_part_fk.tenant_order
FOR VALUES WITH (MODULUS 4, REMAINDER 3);
```

This example targets **PostgreSQL 11+**, where hash partitioning and parent PKs were introduced.

### 40.1. Two Tenants Can Reuse the Same Order Code

```sql
INSERT INTO demo_part_fk.tenant_order (tenant_id, order_code, amount)
VALUES
    (1, 'A001', 100),
    (2, 'A001', 200);
```

Valid because the composite keys differ.

### 40.2. Within the Same Tenant, Order Codes Cannot Repeat

```sql
-- INTENTIONAL ERROR:
INSERT INTO demo_part_fk.tenant_order (tenant_id, order_code, amount)
VALUES (1, 'A001', 300);
```

The parent PK protects `(tenant_id,order_code)` uniqueness across the entire tree because rows for the same tenant always route to the same hash partition.

## 41. FOREIGN KEY to a HASH-Partitioned Table

From PG12+, you can write:

```sql
CREATE TABLE demo_part_fk.tenant_order_note (
    note_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    order_code TEXT NOT NULL,
    note_text TEXT NOT NULL,

    CONSTRAINT fk_note_tenant_order
        FOREIGN KEY (tenant_id, order_code)
        REFERENCES demo_part_fk.tenant_order(tenant_id, order_code)
);
```

Valid insert:

```sql
INSERT INTO demo_part_fk.tenant_order_note
    (tenant_id, order_code, note_text)
VALUES
    (1, 'A001', 'Fast delivery');
```

Wrong tenant:

```sql
-- INTENTIONAL ERROR (no order 3/A001):
INSERT INTO demo_part_fk.tenant_order_note
    (tenant_id, order_code, note_text)
VALUES
    (3, 'A001', 'Wrong tenant key');
```

Crucially, the FK **carries `tenant_id`**, preventing accidental cross-tenant references when order codes collide.

## 42. LIST Partitioning and Key Scope

With LIST:

```sql
CREATE TABLE demo_part_fk.tenant_setting (
    tenant_id INTEGER NOT NULL,
    setting_name TEXT NOT NULL,
    setting_value TEXT NOT NULL,
    CONSTRAINT uq_setting_per_tenant
        UNIQUE (tenant_id, setting_name)
)
PARTITION BY LIST (tenant_id);

CREATE TABLE demo_part_fk.tenant_setting_t1
PARTITION OF demo_part_fk.tenant_setting FOR VALUES IN (1);

CREATE TABLE demo_part_fk.tenant_setting_t2
PARTITION OF demo_part_fk.tenant_setting FOR VALUES IN (2);

CREATE TABLE demo_part_fk.tenant_setting_default
PARTITION OF demo_part_fk.tenant_setting DEFAULT;
```

`UNIQUE (tenant_id, setting_name)` is enforceable on the parent because `tenant_id` is the partition key. `UNIQUE (setting_name)` alone is rejected for omitting `tenant_id`.

### 42.1. A DEFAULT Partition Can Hold Multiple Tenants

The unique index inside `DEFAULT` still protects `(tenant_id, setting_name)` combinations, not `setting_name` alone. When moving a tenant out into a dedicated partition, ensure data/bounds stay disjoint and constraints remain valid.

## 43. Partition Bounds, NULL, and Routing

Rules vary by strategy:

- `RANGE` does not accept `NULL` keys in `FROM`/`TO` bounds and needs `DEFAULT` to route `NULL`.
- `LIST` can explicitly enumerate `NULL` per list-partitioning rules.
- `HASH` routes by key hash using server `NULL` handling rules.
- Enforce `NOT NULL` on the partition key whenever `NULL` is invalid in business logic.

For example, `invoice.issued_on NOT NULL` ensures no invoice lacks a date regardless of whether a default partition catches other out-of-range values.

### 43.1. A Default Partition Does Not Make NULL Valid

Because `issued_on` is `NOT NULL`, `INSERT ... issued_on=NULL` fails the constraint rather than silently landing in `DEFAULT` as an "unknown month."

## 44. FOREIGN TABLEs as Partitions: Where Are Constraints Checked?

PostgreSQL allows **foreign tables** as partitions in certain setups. However, a foreign table stores data managed by an FDW/remote system, and local `CHECK`/`NOT NULL` declarations **may not be enforced by PostgreSQL core against remote data**.

Crucial warning:

> **Never trust remote data solely because a local foreign table declares a valid-looking CHECK.**

If the remote source allows rows violating partition bounds or constraints, planner optimizations relying on those assumptions can break and produce wrong results.

### 44.1. FK/Unique Limits on Foreign Partitions

Never assume parent FK, unique, index, or constraint mechanics from local partitions apply unchanged to foreign-table partitions. Consult `CREATE FOREIGN TABLE` and your specific FDW docs, and verify remote constraints during migrations.

## 45. RLS, Privileges, and Constraints

Row-Level Security (RLS) restricts which rows a user can see or modify, without altering `PK`/`UNIQUE`/`FK`.

For example, an FK must still protect referential integrity even when the referencing user cannot see the referenced row under RLS; PostgreSQL enforces integrity internally to prevent corruption.

### 45.1. Never Use FKs Instead of Authorization

A row with `tenant_id=2` and a valid FK to a tenant-2 order never implies a tenant-1 user may access it. Authorization still needs application scoping, `GRANT`/`RLS`, and role policies.

### 45.2. Unique Errors Can Leak Existence

A duplicate-key `INSERT` error can reveal to a client that a business ID exists even when `SELECT` is blocked by RLS. Never leak raw database error details containing sensitive keys to public APIs; sanitize errors and rate-limit appropriately.

## 46. Partition Pruning and FKs Are Not Independent Design Choices

When an FK targets a PK containing the partition key, composite-key queries naturally enable pruning:

```sql
SELECT *
FROM demo_part_fk.invoice
WHERE issued_on = DATE '2026-11-10'
  AND invoice_id = 1001;
```

Whereas an API knowing only `invoice_id` may probe many partitions:

```sql
SELECT *
FROM demo_part_fk.invoice
WHERE invoice_id = 1001;
```

and may even return **multiple invoices** if `invoice_id` repeats across dates.

**Partition key, business identity, FKs, and query patterns must align**—they are not four isolated decisions.

### 46.1. Pruning Never Skips FK Checks

Even when a query reads a single partition, FKs enforce full referential integrity on `INSERT`/`UPDATE`/`DELETE`. Pruning is a read optimization, not an "integrity check bypass."

## 47. Parent Indexes Are Virtual; Leaf Indexes Are Physical

Example:

```sql
CREATE INDEX idx_invoice_status
ON demo_part_fk.invoice (status);
```

PostgreSQL creates a partitioned index on the parent and physical indexes on leaf partitions. When new partitions are added, matching indexes propagate per rules.

### 47.1. CONCURRENTLY and Parent Partitioned Indexes

Across many PostgreSQL versions, `CREATE INDEX CONCURRENTLY` is not supported directly on a **partitioned parent** the way it is on regular tables. Standard migration workflow:

1. Create the parent index with `ON ONLY` (initially invalid/incomplete).
2. Build each leaf index with `CREATE INDEX CONCURRENTLY` where supported.
3. Run `ALTER INDEX ... ATTACH PARTITION` to attach each child index.
4. Once all children are attached, the parent index becomes valid.

For **`UNIQUE`/`PRIMARY KEY`**, exercise even greater caution regarding constraints and validity. Never blindly copy a non-unique index script for PKs without checking version and dependencies.

### 47.2. Creating an Index Does Not Expand Business Uniqueness Scope

`CREATE INDEX (invoice_id)` on a partitioned parent speeds up lookups—it **never** makes `invoice_id` globally unique.

## 48. Lock Duration for ALTER TABLE Across a Partition Tree

Operations acquire locks of varying strength:

- `ADD CONSTRAINT`.
- `VALIDATE CONSTRAINT`.
- `ATTACH PARTITION`.
- `DETACH PARTITION`.
- `CREATE INDEX` / `ATTACH INDEX PARTITION`.
- `DROP CONSTRAINT`.
- `UPDATE` causing row movement.

There is no rule claiming "since the parent stores no rows, parent DDL is O(1) and locks no leaves." Parent DDL coordinates metadata across leaf objects, and validation can scan full datasets.

### 48.1. Monitoring

```sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    left(query, 180) AS sql_excerpt
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
```

If DDL blocks, inspect lock modes and blocking transactions per DBA runbooks. Never blindly kill other transactions just because a migration is waiting.

## 49. SQLSTATE Changes Across Versions: Application Warning

PostgreSQL 18 changed the SQLSTATE reported for certain **`RESTRICT` FK violations** from `23503` to `23001`.

If Java code checks:

```java
if ("23503".equals(e.getSQLState())) {
    // Foreign key violation
}
```

upgrading to PG18 can cause `RESTRICT` violations to miss that branch if only one code is hardcoded.

Handle this by matching **constraint action types and version-verified SQLSTATEs**, backed by integration tests for:

- Inserting a child without a parent.
- Deleting a referenced parent with surviving children under `NO ACTION`.
- Deleting a referenced parent with surviving children under `RESTRICT`.
- `CASCADE` / `SET NULL` / `SET DEFAULT`.
- Deferred/validated constraints.

Never catch all class `23` errors identically; uniqueness, FK, `CHECK`, and `NOT NULL` carry different business meanings.

## 50. JDBC: Binding Full Composite FKs

In Java:

```java
String sql = """
    INSERT INTO demo_part_fk.invoice_line
      (issued_on, invoice_id, line_no, sku, qty, unit_price)
    VALUES (?, ?, ?, ?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setObject(1, java.time.LocalDate.of(2026, 11, 10));
    ps.setLong(2, 1001L);
    ps.setInt(3, 1);
    ps.setString(4, "SKU-01");
    ps.setInt(5, 2);
    ps.setBigDecimal(6, new java.math.BigDecimal("10.00"));

    ps.executeUpdate();
}
```

If `issued_on` in the referencing row is wrong, the FK rejects it even if `invoice_id` exists on a different date.

### 50.1. Avoid Arbitrary Date String Concatenation

Bind proper JDBC/PostgreSQL `DATE` types instead of mixing local timezones and timestamps casually in partition keys.

When partitioning by `TIMESTAMPTZ` in UTC, align query ranges and timezones consistently. Never form monthly buckets in local application time while defining bounds in UTC without proving equivalence.

### 50.2. Composite Keys in ORMs

If an ORM maps `@Id` solely onto `invoice_id` when the real PK is `(issued_on,invoice_id)`, entity identity caches collide and updates/deletes hit the wrong rows.

Model the full composite ID in entities and pass the partition key in repository methods. Never sacrifice correctness just because an ORM defaults to scalar IDs.

## 51. Essential Migration Tests

An integration test suite for a partitioned schema should cover:

1. Inserts into each bounded partition.
2. Out-of-bounds inserts without `DEFAULT`.
3. Out-of-bounds inserts with `DEFAULT`.
4. Duplicate PK **within the same** partition.
5. Same `invoice_id` with a **different** partition key.
6. Valid FK inserts from a partitioned referencing parent.
7. Invalid FK inserts against a regular referenced table.
8. Valid FK inserts referencing a partitioned parent.
9. FK mismatch on one column of a composite key.
10. Deleting a referenced row with existing children.
11. `ON DELETE CASCADE` when declared.
12. `ON UPDATE` modifying the partition key.
13. Inherited `CHECK`/`NOT NULL` and local `CHECK`s.
14. Attaching a partition with valid historical data.
15. Attaching a partition with out-of-bounds data.
16. `DEFAULT` holding data overlapping a new partition.
17. `NOT VALID` FK validation on PG18+.
18. `NOT ENFORCED` only where version/contract allows.
19. Concurrent inserts of the same business key across two partitions.
20. Restore/migration onto the target major version.

Run these on staging/test databases with representative schemas and data—never in production.

## 52. Exercise 1: Is This PK Valid?

Table:

```sql
CREATE TABLE event_store (
    event_id BIGINT,
    event_day DATE NOT NULL,
    PRIMARY KEY (event_id)
) PARTITION BY RANGE (event_day);
```

**Question:** Does this succeed on PostgreSQL 18?

**Answer:** No. `event_day` is the partition key and is missing from the PK. A structurally valid definition is `PRIMARY KEY (event_day,event_id)`, noting that it does not guarantee global uniqueness of `event_id`.

## 53. Exercise 2: Per-Partition Uniqueness Only

Two partitions for October and November each have:

```sql
CREATE UNIQUE INDEX ... ON leaf (external_id);
```

**Question:** Can `external_id='A001'` appear in both months?

**Answer:** Yes, because two separate indexes guard two separate row sets. Global uniqueness requires a different design or a valid parent `UNIQUE` whose partition key aligns with the business scope.

## 54. Exercise 3: Date as Part of Identity

A parent has:

```sql
PRIMARY KEY (issued_on, invoice_id)
```

Two rows have `invoice_id=42` on `2026-10-01` and `2026-10-02`.

**Answer:** Valid under the PK. If the business requires one unique ID per month, redesign the key/partition key and uniqueness contract rather than assuming the current PK suffices.

## 55. Exercise 4: Distinguishing Both FK Directions

A. Partitioned `invoice` has an FK to regular `customer`.

B. Regular `receipt` has an FK to partitioned `invoice`.

**Question:** Which major versions added support for each?

**Answer:** A since PostgreSQL 11; B since PostgreSQL 12. PostgreSQL 10 declarative partitioning supported neither FK direction.

## 56. Exercise 5: FKs Must Target a Unique Key

```sql
FOREIGN KEY (invoice_id)
REFERENCES demo_part_fk.invoice(invoice_id)
```

**Question:** Why is this rejected?

**Answer:** The parent has no `UNIQUE`/`PK` on `invoice_id` alone; its valid constraint is `(issued_on,invoice_id)`. Targeting `invoice_id` alone is ambiguous across dates/partitions.

## 57. Exercise 6: Composite Key Mismatch Error

`invoice` has `(issued_on=2026-11-10,invoice_id=1001)`. `invoice_line` inserts `(issued_on=2026-11-11,invoice_id=1001)`.

**Answer:** FK fails even though `invoice_id` matches. The FK checks both columns and never snaps dates to nearby records.

## 58. Exercise 7: CHECK Alone Is Not Enough

```sql
amount NUMERIC,
CHECK (amount >= 0)
```

**Question:** Is `NULL` blocked?

**Answer:** No. `CHECK` passes `UNKNOWN` when `NULL` is evaluated. Add `NOT NULL` if `amount` is mandatory.

## 59. Exercise 8: Inherited NOT NULL

Parent has `issued_on DATE NOT NULL`. A leaf tries to drop `NOT NULL` on that column.

**Answer:** You cannot weaken an inherited parent constraint on a leaf in declarative partitioning. Parent constraints govern the entire tree.

## 60. Exercise 9: Default Partition

A row has `issued_on='2027-03-01'`, matching neither Oct nor Nov; the parent has `DEFAULT`.

**Answer:** The row goes to `DEFAULT` if all other constraints pass. `DEFAULT` never bypasses FK/PK/CHECK.

## 61. Exercise 10: Attaching Out-of-Bounds Data

A staging table for `01/2027` holds a row dated `2027-02-10`.

**Question:** Is attaching it to `FROM 2027-01-01 TO 2027-02-01` valid?

**Answer:** No—that row violates the bounds. PostgreSQL validates bounds (or relies on a matching validated `CHECK`) and rejects out-of-bounds rows.

## 62. Exercise 11: ON DELETE CASCADE Alongside Other FKs

`invoice` has `invoice_line` with `ON DELETE CASCADE`, while `invoice_receipt` uses `NO ACTION`.

**Question:** Is deleting an invoice guaranteed to succeed and cascade to lines?

**Answer:** No. The receipt FK blocks `DELETE` if referencing receipts exist. The transaction must satisfy **all constraints**, not just the cascading FK.

## 63. Exercise 12: NOT VALID vs. NOT ENFORCED

**Question:** When adding a `NOT VALID` FK, can new `INSERT`s violate it? What about `NOT ENFORCED`?

**Answer:** An enforced `NOT VALID` FK still validates new data changes; `NOT VALID` only means existing rows haven't been scanned/verified yet. `NOT ENFORCED` (PG18+) skips integrity enforcement altogether.

## 64. Exercise 13: PostgreSQL 18 Milestone

**Question:** Why does a migration running `ALTER TABLE partitioned_parent ADD FOREIGN KEY ... NOT VALID` work on PostgreSQL 18 yet not identically on 16?

**Answer:** PG18 added support for `NOT VALID` foreign keys on partitioned tables. FKs on partitioned parents existed earlier, yet **not every FK option arrived in the same release**.

## 65. Exercise 14: Parent EXCLUDE by Version

**Question:** Is parent-level `EXCLUDE USING gist` supported from PG17, and can you write `partition_key WITH &&`?

**Answer:** PG17 allows parent `EXCLUDE` under specific conditions; all partition key columns must use **equality (`=`)**. Using overlap `&&` directly on the partition key violates that restriction.

## 66. Exercise 15: Same Tenant, Non-Overlapping Rooms

A booking table partitioned by `LIST(tenant_id)` has:

```sql
EXCLUDE USING gist (
    tenant_id WITH =,
    room_id WITH =,
    during WITH &&
)
```

**Question:** What does this constraint prevent?

**Answer:** Two bookings for the same tenant and room cannot have overlapping `during` intervals. Tenant equality aligns with the partition boundaries. Requires matching GiST operator classes and PostgreSQL 17+ for parent-level `EXCLUDE`.

## 67. Exercise 16: Global IDs from a Sequence

A developer claims: "Every `invoice_id` comes from one sequence, so duplicates are impossible; no unique constraint is needed."

**Answer:** A sequence is a value generator, not an integrity guarantee across manual inserts, imports, restores, and explicit writes. If global uniqueness is needed, enforce an actual constraint in the right scope (e.g., registry PK) or pick an aligned partition key.

## 68. Exercise 17: Referencing FK Index

`invoice_line` has `PK(issued_on,invoice_id,line_no)`. Do you need an extra `INDEX(issued_on,invoice_id)` just for FK lookups?

**Answer:** Not necessarily; the PK B-tree already has that exact two-column prefix. Measure workload and plans to avoid redundant indexes.

## 69. Exercise 18: Expression Partition Key

A parent is partitioned by `(id % 4)`. A developer wants `PRIMARY KEY(id)` on the parent.

**Answer:** Declarative partitioning restricts parent `PK`/`UNIQUE` when the partition key contains an expression. Even though the expression is a function of `id`, PostgreSQL does not treat it as an eligible plain column partition key for constraint verification.

## 70. Exercise 19: Subpartitioning

A parent partitions by date, and each month subpartitions by tenant. The root unique constraint covers only `(issued_on,invoice_id)`.

**Question:** What else must be checked?

**Answer:** Multi-level partitioning requires including partition keys from descendant partitioned tables—for instance adding `tenant_id`; a PK covering only the root key may be rejected or insufficient for the tree.

## 71. Exercise 20: Detached Partitions and Receipts

The system plans to detach October while receipts still reference October invoices via a parent FK.

**Guidance answer:** Never treat `DETACH` as harmless cleanup. Analyze dependencies, FK enforcement, retention, and version-specific behavior, test on staging, and handle dependent rows before detaching/dropping.

## 72. Exercise 21: Legacy Inheritance Partitioning

An older system uses `CREATE TABLE child (...) INHERITS(parent)` with triggers routing `INSERT`s.

**Question:** Does the declarative-partitioning FK/PK timeline apply identically?

**Answer:** No. Legacy inheritance has different semantics for indexes, uniqueness, FKs, and automatic routing. Distinguish the two models before migrating.

## 73. Exercise 22: Partition Pruning and CHECK

**Question:** Does adding `CHECK (issued_on BETWEEN ...)` automatically create monthly partitions and replace `PARTITION BY`?

**Answer:** No. `CHECK` is a data constraint; partition keys/bounds define routing and partitioning structure. `CHECK`-based constraint exclusion is a separate optimizer feature, not declarative partitioning.

## 74. Exercise 23: Migrations on Older Versions

A system runs PG11 and a regular table needs an FK referencing a partitioned parent.

**Answer:** PG11 does not support FKs **referencing** a partitioned table. Plan an upgrade to PG12+ or redesign the referenced key/registry; never fake FKs with simple triggers and claim equivalent integrity.

## 75. Exercise 24: Enforcement Status Catalog

A PostgreSQL 17 server runs:

```sql
SELECT conenforced FROM pg_constraint;
```

**Answer:** This fails because `conenforced` was added in PostgreSQL 18. Gate queries on server version before relying on new catalog columns.

## 76. Exercise 25: RESTRICT SQLSTATE After Upgrade

An app catches only `23503`. After upgrading to PG18, `ON DELETE RESTRICT` reports `23001`.

**Answer:** Update error classification to handle version-specific SQLSTATEs with integration tests; never swallow all class `23` errors indiscriminately since different constraint violations have distinct meanings.

## 77. Key Design Decision Matrix

| Business Need | Partitioning Candidate | Key / Constraint to Evaluate |
|---|---|---|
| ID unique per tenant | `HASH/LIST(tenant_id)` | `PRIMARY KEY(tenant_id,id)` |
| ID unique per day | `RANGE(event_date)` | `PRIMARY KEY(event_date,id)` |
| ID unique per month | `RANGE(event_month)` with explicit month column | `UNIQUE(event_month,id)` |
| Globally unique ID, partitioned by date | `RANGE(event_date)` | Unique registry or alternative key/identity model |
| Child rows tied to an invoice's date | Same day/month partitioning or independent | Composite FK `(issued_on,invoice_id)` |
| FK from partitioned table to regular parent | PG11+ | Standard FK, child indexes per workload |
| FK referencing a partitioned parent | PG12+ | Valid referenced PK/UNIQUE |
| Non-overlapping `EXCLUDE` per tenant | `LIST/HASH(tenant_id)` | PG17+ parent `EXCLUDE` with partition-key equality |
| Bulk import, add FK then validate later | Partitioned parent eligible | PG18+ `NOT VALID` FK on partitioned tables |
| Non-enforced constraint metadata | Domain-specific | PG18+ `NOT ENFORCED` (does not protect integrity) |

This is a **design guide**, not an automated formula. Cardinality, query pruning, partition count, retention, and locking also shape the final schema.

## 78. Pre-Deployment Checklist for Constraints on Partitioned Tables

1. Confirmed this uses **declarative partitioning**, not legacy inheritance?
2. What is `SHOW server_version_num` on the **actual target server**?
3. Are partition keys plain **columns or expressions**?
4. Are there **subpartition levels**?
5. Do parent `PK`/`UNIQUE` constraints include **all involved partition key columns**?
6. Does the constraint actually enforce uniqueness across the **intended business scope**?
7. Is anyone mistakenly assuming a leaf `UNIQUE` protects other leaves?
8. Does any business ID need global uniqueness despite time-based partitioning?
9. Is an ID registry table needed to protect global IDs?
10. Do referencing FKs carry the full composite key to target a valid PK/UNIQUE?
11. Does the target major version support FKs referencing a partitioned parent?
12. Could nullable columns cause `MATCH SIMPLE` to skip composite FK checks?
13. Are `ON DELETE`/`ON UPDATE` actions compatible with the partition key?
14. Could cascades delete or move rows across many partitions?
15. Are suitable indexes present on the referencing side?
16. Does a PK/UNIQUE index already share a prefix, making a separate index redundant?
17. Do parent `CHECK`/`NOT NULL` constraints propagate to leaves as intended?
18. Are there leaf-local `CHECK`s making behavior differ across partitions?
19. Do partition bounds cover all real data?
20. Is there a `DEFAULT` partition, and are many rows landing in it?
21. Will `ATTACH` scan historical rows?
22. Are prevalidated `CHECK` bounds present to skip unnecessary scans?
23. How do `DETACH`/`DROP` affect FK references and retention?
24. Are there external/foreign partitions where core DB does not enforce `CHECK` remotely?
25. Is `NOT VALID` accidentally used on a partitioned FK before PG18?
26. Is `NOT ENFORCED` mistaken for an actively enforced integrity constraint?
27. Is parent `EXCLUDE` supported (PG17+) and using equality on all partition keys?
28. Are PG18 temporal constraints verified for exact syntax/semantics?
29. Are `ON CONFLICT`/upserts designed around composite keys containing the partition key?
30. Do ORMs and APIs model composite keys accurately?
31. Has cross-partition row movement on partition-key `UPDATE`s been tested?
32. Do excessive partition counts add constraint/DDL overhead?
33. Does the migration have lock timeouts, throttling, and rollback procedures?
34. Are integration tests covering FK errors, `UNIQUE`, `CHECK`, and `NOT NULL`?
35. Are SQLSTATE differences across major versions checked?
36. Are `pg_constraint`/`pg_partition_tree` verification queries run post-deploy?
37. Have referenced-parent `DELETE`s with many child rows been benchmarked?
38. Is automated partition creation scheduled ahead of upcoming periods?
39. Is there a policy for `DEFAULT` drainage and orphaned references on retention?
40. Have release notes for the target server's exact minor version been reviewed?

## 79. Versioned Documentation References

To cross-check schemas and features **by version**, consult official PostgreSQL documentation:

- [PostgreSQL 10 — Partitioning](https://www.postgresql.org/docs/10/ddl-partitioning.html)
- [PostgreSQL 11 — Partitioning](https://www.postgresql.org/docs/11/ddl-partitioning.html)
- [PostgreSQL 12 — Partitioning](https://www.postgresql.org/docs/12/ddl-partitioning.html)
- [PostgreSQL 16 — Partitioning](https://www.postgresql.org/docs/16/ddl-partitioning.html)
- [PostgreSQL 17 — Partitioning](https://www.postgresql.org/docs/17/ddl-partitioning.html)
- [PostgreSQL 18 — Partitioning](https://www.postgresql.org/docs/18/ddl-partitioning.html)
- [PostgreSQL 18 — CREATE TABLE](https://www.postgresql.org/docs/18/sql-createtable.html)
- [PostgreSQL 18 — ALTER TABLE](https://www.postgresql.org/docs/18/sql-altertable.html)
- [PostgreSQL 18 — Release notes](https://www.postgresql.org/docs/18/release-18.html)
- [PostgreSQL 17 — Release notes](https://www.postgresql.org/docs/17/release-17.html)

**Read documentation matching your running server.** A valid PG18 example will not run identically on PG11, and features in PG19 RC are not production contracts before GA.

## 80. Summary

**Partitioning does not automatically abolish data constraints, yet it changes the scope over which PostgreSQL can prove uniqueness and enforce references.**

Key principles to remember:

1. **Parent `PK`/`UNIQUE` must include all partition key columns and cannot use expression partition keys under current restrictions.** That allows PostgreSQL to rely on routing plus local indexes to enforce uniqueness.
2. **`PK (issued_on,invoice_id)` protects the pair only—not `invoice_id` globally.** If IDs must be unique regardless of date, a different design is required.
3. **FK support by version:** PG10 lacked declarative-tree FKs; PG11 added FKs **from** a partitioned table to a regular table; PG12 added FKs **to** a partitioned table, enabling bidirectional FKs with partitioned parents.
4. **Parent `CHECK`/`NOT NULL` are inherited.** Bounds govern routing; `CHECK` adds row validation and never replaces partition keys.
5. **PG17 added parent `EXCLUDE` with partition-key equality; PG18 added `NOT VALID` FKs on partitioned tables and `NOT ENFORCED` `CHECK`/FK.** `NOT VALID` and `NOT ENFORCED` mean completely different things.
6. **Partition administration must align with constraints.** `ATTACH`, `DETACH`, `DEFAULT` partitions, leaf indexes, row movement, and retention all require data, lock, and dependency checks.
7. **Design FKs and business identity before partitioning.** Composite keys reshape applications, ORMs, APIs, `JOIN`s, and `ON CONFLICT`—not merely database DDL.

The decisive architectural question is: **"Which value must be unique across the entire dataset, and will rows sharing that value always route to the exact same partition?"** Next ask: **"Do referencing tables carry enough partition-key information to define a PostgreSQL-enforced FK on the target version?"** Answering both prevents systems that look valid per partition while silently failing logical-table integrity.
