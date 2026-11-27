# Evaluating Schemas by Queries, Constraints, and Data Growth in PostgreSQL

A PostgreSQL schema can be syntactically valid, have all tables created cleanly, and run fine with a few hundred rows, yet still **not be fit for long-term production**. A year later, the orders table may grow to tens of millions of rows; the "20 most recent orders" query slows to a crawl; excessive indexes drag down write throughput; or corrupted data slips in because business rules were only checked in application code.

Evaluating a schema should not stop at **"are the tables normalized?"** You must evaluate three dimensions together:

1. **Queries and data access patterns:** what the system reads, which columns it filters on, which tables it joins, how it sorts and paginates, plus target frequencies and latencies.
2. **Constraints and consistency:** which states are valid, whether primary/foreign keys protect relationships, and whether updates and deletes remain safe.
3. **Data growth and lifecycle:** row counts, table/index size, write/delete ratios, historical records, retention, vacuuming, backups, and scaling needs.

This lesson uses modern PostgreSQL (such as PostgreSQL 16) to build a small orders schema, then walks through the exact evaluation questions asked before launching a real system. Examples include DDL, application queries, `EXPLAIN`, catalog statistics, and improvement workflows. Capacity and traffic figures are explicitly **illustrative assumptions for calculation**, not real benchmarks.

## 1. A Good Schema Must Serve a Specific Workload

A **workload** is the actual set of operations the system performs: reads, inserts, updates, deletes, aggregations, exports, and feature queries.

Two applications using the exact same `orders` table may require different designs:

- **Transactional application:** creates many orders per second, fetches one order by ID, lists a customer's 20 latest orders, and updates payment status.
- **Analytical system:** scans huge historical datasets to aggregate revenue by day, product, or region.

For the transactional app, B-tree indexes aligned with filters and `ORDER BY` matter most. For scanning massive histories, time-based organization, pre-aggregations, or a separate analytics warehouse may make far more sense.

### Three Criteria to Balance

~~~text
                     QUERIES
             filters, JOIN, ORDER BY
                     /      \
                    /        \
                   /          \
        CONSTRAINTS ---------- GROWTH
        valid data,            storage, write speed,
        keys, relations        vacuum, retention
~~~

For example, adding more indexes speeds up reads while making `INSERT` and `UPDATE` costlier to maintain. Splitting tables guards relationships and avoids duplication while adding `JOIN`s. Storing an order total speeds up listing screens while requiring synchronization with order lines.

**No single schema is optimal for every workload.** The goal is a design that meets critical requirements, makes trade-offs explicit, and still scales cleanly as data grows.

## 2. Start with a Business Query Inventory

Before creating indexes or choosing partitioning, document the key query patterns.

Example e-commerce workload:

| ID | Need | Filter and Ordering | Assumed Frequency | Priority |
| --- | --- | --- | --- | --- |
| Q1 | Open one order's details | `WHERE order_id = ?` | Very frequent | High |
| Q2 | View a customer's latest orders | `WHERE customer_id = ? ORDER BY created_at DESC LIMIT 20` | Frequent | High |
| Q3 | View latest paid orders | `WHERE status = 'paid' ORDER BY created_at DESC LIMIT 50` | Frequent | Medium |
| Q4 | Read an order's product lines | `WHERE order_id = ?` on `order_items` | Very frequent | High |
| Q5 | Aggregate monthly revenue | Filter `created_at`, group/sum across many orders | Scheduled | Medium |
| Q6 | Inspect an order's event history | `WHERE order_id = ? ORDER BY event_at DESC` | On investigation | Medium |

These frequencies are **purely illustrative assumptions**. On a live system, pull real numbers from query logs, APM tools, or `pg_stat_statements` if enabled.

For every critical query, also capture:

- Target p95/p99 latency, not just averages.
- Input rows scanned and expected rows returned.
- Peak-hour read-to-write ratio.
- `WHERE` predicate selectivity, skewed value distributions, and outliers.
- Presence of `JOIN`, `ORDER BY`, `GROUP BY`, deep pagination, or large batches.
- Whether access targets recent data or routinely spans multi-year history.

Every justified schema choice should name **which query, constraint, or growth trend it improves or protects**.

## 3. Building a Practice Orders Schema

Run these statements only in a **practice database** where you hold schema-creation privileges. Never run in production.

~~~sql
CREATE SCHEMA review_lab;

CREATE TABLE review_lab.customers (
    customer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL,
    display_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_customers_email UNIQUE (email),
    CONSTRAINT ck_customers_display_name
        CHECK (length(btrim(display_name)) > 0)
);

CREATE TABLE review_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    created_at timestamptz NOT NULL DEFAULT now(),
    paid_at timestamptz,
    total_amount numeric(14, 2) NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES review_lab.customers (customer_id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_orders_status
        CHECK (status IN ('pending', 'paid', 'cancelled')),
    CONSTRAINT ck_orders_amount
        CHECK (total_amount >= 0),
    CONSTRAINT ck_orders_paid_time
        CHECK (paid_at IS NULL OR paid_at >= created_at)
);

CREATE TABLE review_lab.order_items (
    order_item_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL,
    sku text NOT NULL,
    quantity integer NOT NULL,
    unit_price numeric(14, 2) NOT NULL,
    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id)
        REFERENCES review_lab.orders (order_id)
        ON DELETE RESTRICT,
    CONSTRAINT uq_item_order_sku UNIQUE (order_id, sku),
    CONSTRAINT ck_item_quantity CHECK (quantity > 0),
    CONSTRAINT ck_item_unit_price CHECK (unit_price >= 0)
);

CREATE TABLE review_lab.order_events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL,
    event_type text NOT NULL,
    event_at timestamptz NOT NULL DEFAULT now(),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT fk_events_order
        FOREIGN KEY (order_id)
        REFERENCES review_lab.orders (order_id)
        ON DELETE RESTRICT
);
~~~

This schema contains three relationships:

~~~text
customers (1)
    │
    │ fk_orders_customer
    ▼
orders (N)
    │              │
    │              └──────────► order_events (N)
    │                           stores event history
    │
    └─────────────────────────► order_items (N)
                                stores product line items
~~~

### Explaining Key Choices

| Choice | Rationale | Follow-up Evaluation Point |
| --- | --- | --- |
| `bigint ... IDENTITY` | Auto-incrementing ID, avoids hitting `integer` limits early on large tables | Do external consumers need unpredictable or distributed IDs? |
| `timestamptz` | Stores instant with timezone semantics, suited for events | How does the app convert and format time zones? |
| `numeric(14,2)` | Exact decimal storage for money at chosen precision | Currency codes, rounding rules, maximum value bounds |
| `PRIMARY KEY` | Ensures unique row identity and creates a backing unique B-tree index | Key type and how other tables reference it |
| `FOREIGN KEY` | Prevents orphaned relationships between orders and customers/details | Deletion behavior and write/check overhead |
| `CHECK` and `NOT NULL` | Enforces value domains right at the database | Rules spanning multiple tables or transactions |
| `jsonb` on `payload` | Suits event metadata with varying structure | Never carelessly replace stable relational columns with JSONB |

This is a **baseline schema for review**, not a finished design for every business. For instance, storing `total_amount` on `orders` alongside `quantity × unit_price` in `order_items` demands explicit rules keeping both sources consistent.

## 4. Inserting Sample Data Independent of Generated IDs

~~~sql
INSERT INTO review_lab.customers (email, display_name)
VALUES
    ('lan@example.test', 'Lan'),
    ('minh@example.test', 'Minh'),
    ('an@example.test', 'An');

INSERT INTO review_lab.orders
    (customer_id, status, created_at, paid_at, total_amount)
SELECT
    c.customer_id,
    x.status,
    x.created_at,
    x.paid_at,
    x.total_amount
FROM (
    VALUES
        (
            'lan@example.test',
            'paid',
            '2026-10-01 09:00:00+07'::timestamptz,
            '2026-10-01 09:03:00+07'::timestamptz,
            120000.00::numeric
        ),
        (
            'lan@example.test',
            'pending',
            '2026-10-04 14:30:00+07'::timestamptz,
            NULL::timestamptz,
            300000.00::numeric
        ),
        (
            'minh@example.test',
            'paid',
            '2026-10-02 11:00:00+07'::timestamptz,
            '2026-10-02 11:15:00+07'::timestamptz,
            80000.00::numeric
        ),
        (
            'an@example.test',
            'cancelled',
            '2026-10-05 08:20:00+07'::timestamptz,
            NULL::timestamptz,
            70000.00::numeric
        )
) AS x(email, status, created_at, paid_at, total_amount)
JOIN review_lab.customers AS c
    ON c.email = x.email;
~~~

Insert line items and events by looking up the order ID via email and timestamp instead of assuming sequences always start at 1:

~~~sql
INSERT INTO review_lab.order_items
    (order_id, sku, quantity, unit_price)
SELECT o.order_id, 'COFFEE-001', 2, 60000.00
FROM review_lab.orders AS o
JOIN review_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE c.email = 'lan@example.test'
  AND o.created_at = '2026-10-01 09:00:00+07'::timestamptz;

INSERT INTO review_lab.order_events
    (order_id, event_type, event_at, payload)
SELECT
    o.order_id,
    'payment_confirmed',
    '2026-10-01 09:03:00+07'::timestamptz,
    '{"gateway":"sandbox","result":"ok"}'::jsonb
FROM review_lab.orders AS o
JOIN review_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE c.email = 'lan@example.test'
  AND o.created_at = '2026-10-01 09:00:00+07'::timestamptz;
~~~

Quick check:

~~~sql
SELECT c.email, o.order_id, o.status, o.created_at, o.total_amount
FROM review_lab.orders AS o
JOIN review_lab.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.created_at, o.order_id;
~~~

With just a handful of rows, PostgreSQL will likely choose a **sequential scan** over an index scan because scanning a tiny table is cheaper. That does not mean indexes fail to help on multi-million-row tables.

## 5. Evaluating the Schema by Queries: Keys, Filters, JOINs, Sorting

Start from the workload queries, then identify structures and indexes that serve them.

### 5.1. Q1: Looking Up an Order by Primary Key

~~~sql
SELECT order_id, customer_id, status, total_amount
FROM review_lab.orders
WHERE order_id = 12345;
~~~

Because `orders.order_id` is `PRIMARY KEY`, PostgreSQL maintains a unique B-tree index supporting this lookup. Usually **you do not need another standalone index on `order_id`**.

Similarly, `UNIQUE (email)` on `customers` creates a unique index enforcing uniqueness. Adding a second identical index "to make it faster" is redundant.

### 5.2. Q2: Listing a Customer's Most Recent Orders

~~~sql
SELECT order_id, status, created_at, total_amount
FROM review_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

This query has:

- An equality predicate on `customer_id`.
- Descending order by `created_at` and `order_id`.
- A `LIMIT 20` cap.

An index to consider:

~~~sql
CREATE INDEX idx_orders_customer_created
ON review_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
);
~~~

This column order lets PostgreSQL jump straight to one customer's slice and read newest-first. `order_id` acts as a tie-breaker so pagination stays deterministic when two orders share the exact same timestamp.

This design follows the **query pattern**, rather than mechanically putting the highest-cardinality column first. If the app mainly filters by `created_at` across **all customers**, an index starting with `customer_id` will not serve that other query well.

### 5.3. Q3: Most Recent Paid Orders

~~~sql
SELECT order_id, customer_id, created_at
FROM review_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Because `status = 'paid'` is a fixed constant predicate, consider a **partial index**:

~~~sql
CREATE INDEX idx_orders_paid_created
ON review_lab.orders (created_at DESC, order_id DESC)
WHERE status = 'paid';
~~~

This index includes only rows matching `status = 'paid'` sorted by time, saving space over a full-table index under skewed distributions.

**Never assume a partial index is always smaller and faster.** If 95% of all orders are `'paid'`, the index remains huge. Moreover, the optimizer must prove the query predicate implies the index predicate.

Specifically, with a **parameterized prepared statement**:

~~~sql
WHERE status = $1
~~~

PostgreSQL may pick a generic plan without knowing whether `$1` equals `'paid'`. In that case, the partial index may not be chosen the way a literal `status = 'paid'` query would use it. Always check the **actual plan produced by the application**, not only `EXPLAIN` on a hardcoded test query.

### 5.4. Q4: Fetching Line Items of an Order

~~~sql
SELECT sku, quantity, unit_price
FROM review_lab.order_items
WHERE order_id = 12345;
~~~

`order_items` already carries:

~~~sql
UNIQUE (order_id, sku)
~~~

That constraint creates a unique index leading with `order_id`, which **already supports `WHERE order_id = ?`**. Do not rush to add a redundant `INDEX (order_id)` if the leading-prefix index already serves the workload cleanly.

At the same time, declaring `FOREIGN KEY (order_id)` **does not automatically create a standalone index on the child table's referencing column**. Here the unique index happens to cover `order_id`; without that unique index, evaluate adding a dedicated child index for lookups and parent deletes/updates.

### 5.5. Q6: Event History for an Order

~~~sql
SELECT event_id, event_type, event_at, payload
FROM review_lab.order_events
WHERE order_id = 12345
ORDER BY event_at DESC, event_id DESC
LIMIT 100;
~~~

Suggested index:

~~~sql
CREATE INDEX idx_events_order_time
ON review_lab.order_events (
    order_id,
    event_at DESC,
    event_id DESC
);
~~~

This B-tree index handles single-order event histories cleanly. Conversely, if the system mainly searches events **by time range across all orders**, evaluate an index leading with `event_at` or a storage strategy aligned with growth and retention.

### 5.6. Do Not Create an Index for Every Random WHERE Clause

Indexes accelerate **reads** at a real cost:

- Consume disk and buffer cache.
- Every `INSERT` must update every index.
- `UPDATE`s must update affected indexes; indexing frequently mutated columns can block **HOT updates** when otherwise eligible.
- `DELETE` and `VACUUM` must process index entries.
- Add build, maintenance, and schema-migration time.

A strong schema is not the one with the most indexes, but the one whose **indexes solve critical queries at a reasonable combined read–write cost**.

## 6. Reading Execution Plans with EXPLAIN

PostgreSQL relies on its planner to pick data access paths. Verify how the planner handles real queries instead of guessing from index names alone.

~~~sql
EXPLAIN
SELECT order_id, created_at, total_amount
FROM review_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Key plan nodes to interpret:

| Plan Node | Interpretation |
| --- | --- |
| `Seq Scan` | Sequential table scan; often optimal for small tables or low selectivity |
| `Index Scan` | Traverses index and fetches matching heap rows as needed |
| `Index Only Scan` | Satisfies query from index alone when visibility map allows |
| `Bitmap Index Scan` + `Bitmap Heap Scan` | Collects matching row pointers via index, then reads heap pages in order |
| `Sort` | Performs an explicit sort rather than receiving pre-sorted rows from an index |
| `Hash Join` / `Nested Loop` / `Merge Join` | Distinct join algorithms chosen by planner cost |
| `rows` / `cost` | Planner estimates, not actual runtime measurements |

### Using EXPLAIN ANALYZE Properly

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total_amount
FROM review_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

`ANALYZE` **actually executes the statement** to measure timings, actual row counts, and plan steps. Here we run it safely on `SELECT`. For `UPDATE`, `DELETE`, or other mutating statements, isolate tests and wrap in controlled transactions—never run `EXPLAIN ANALYZE` carelessly on production thinking it "only previews the plan".

`BUFFERS` adds buffer/block hit and read counts; note "shared hit" does not translate naively into raw disk I/O counts. Inspect numbers across repeated runs with up-to-date statistics in context of cache size, data volume, and concurrency.

### Tiny Sample Datasets Cannot Prove Production Performance

With four `orders` rows, the planner picks `Seq Scan`. That is completely normal. To evaluate a schema for a million orders, test against realistic data matching:

- Row counts and average row widths.
- Distributions across `status`, `customer_id`, and time.
- Skewed heavy customers with thousands of orders vs. one-order customers.
- Concurrent write rates.
- Normal vs. peak-hour query mixes.

After significant data changes, PostgreSQL needs fresh planner statistics:

~~~sql
ANALYZE review_lab.orders;
ANALYZE review_lab.order_events;
~~~

`ANALYZE` refreshes planner statistics; it does not create indexes or guarantee every query switches to an ideal plan automatically.

## 7. Evaluating Constraints: What Data Is Permitted to Exist?

Performance is half the story; **data correctness** is what makes a system trustworthy. If the database permits negative order amounts, zero-quantity lines, or references to non-existent customers, even "fast" queries return wrong business results.

### 7.1. PRIMARY KEY

~~~sql
order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY
~~~

`PRIMARY KEY` guarantees uniqueness and non-nullability backed by a unique B-tree index. Pick primary keys for stability and clean referencing.

A business code like `order_code` may warrant its own `UNIQUE` constraint even when the table uses a surrogate `order_id`. Never choose a frequently mutable column as primary key without strong justification.

### 7.2. FOREIGN KEY

~~~sql
CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id)
    REFERENCES review_lab.customers (customer_id)
    ON DELETE RESTRICT
~~~

This blocks orders referencing non-existent customers. `ON DELETE RESTRICT` rejects deleting a parent row while referencing child rows remain.

Common options:

| Action | Behavior on Parent Delete/Update | When to Consider |
| --- | --- | --- |
| `RESTRICT` | Blocks deleting referenced parent | Preserving order history |
| `NO ACTION` | Checks constraint per timing rules; can be deferrable if configured | Multi-step relation updates inside transactions |
| `CASCADE` | Deletes/updates child rows alongside parent per FK rules | Child data truly shares the exact parent lifecycle |
| `SET NULL` | Sets child FK to null on parent delete | Only valid if column and business allow null |

For financial orders, `ON DELETE CASCADE` from customers to orders is usually a severe mistake because deleting a customer erases order history. Typically keep orders and use account deactivation or dedicated archival workflows.

**Never confuse** `ON DELETE CASCADE` (deleting related **rows** via FK) with `DROP TABLE ... CASCADE` (dropping dependent **schema objects**).

### 7.3. NOT NULL and CHECK

~~~sql
status text NOT NULL,
CONSTRAINT ck_orders_status
    CHECK (status IN ('pending', 'paid', 'cancelled')),
CONSTRAINT ck_orders_amount
    CHECK (total_amount >= 0)
~~~

`CHECK` guards value domains. Yet in PostgreSQL, a `CHECK` expression passes whenever it evaluates to **true or null**; therefore `CHECK (total_amount >= 0)` **does not replace** `NOT NULL`. Combine both whenever a value is mandatory.

For temporal ordering:

~~~sql
CHECK (paid_at IS NULL OR paid_at >= created_at)
~~~

this ensures payment time is never earlier than creation time when `paid_at` is present. However, it **does not force** every `'paid'` order to have a non-null `paid_at`. If that rule is required, enforce it via a matching constraint or controlled status transitions.

### 7.4. UNIQUE and NULL Semantics

~~~sql
CONSTRAINT uq_customers_email UNIQUE (email)
~~~

For `email NOT NULL`, this enforces uniqueness under the column's collation/comparison rules. Still, clarify business rules:

- Should `Lan@Example.test` conflict with `lan@example.test`?
- Can an email from a soft-deleted account be reused?
- Is uniqueness per tenant or system-wide?

A unique expression index can enforce case-insensitive checks per expression:

~~~sql
-- Illustrates an ALTERNATIVE option when required by design.
CREATE UNIQUE INDEX uq_customers_email_lower
ON review_lab.customers (lower(email));
~~~

Adding this index **does not automatically drop** the old unique constraint; keep design consistent and clean duplicates first. Also, real email handling involves more than calling `lower()`—align normalization policies with the application.

PostgreSQL 15+ also supports `UNIQUE NULLS NOT DISTINCT` to treat `NULL`s as indistinct when checking uniqueness. Helpful in specific designs, though not a substitute for clarifying nullability and business rules.

### 7.5. Rules Spanning Beyond One Row

Suppose `orders.total_amount` is stored for fast list reads while `order_items` holds line details:

~~~text
orders.total_amount
    must stay consistent with
SUM(order_items.quantity × order_items.unit_price)
~~~

A `CHECK` constraint on `orders` **cannot directly query rows in `order_items`** like a single-row check. Pick an explicit consistency strategy:

- Skip storing the total and compute dynamically on read if cost is acceptable.
- Store the total and update it inside the **same transaction** as line-item edits.
- Use thoroughly tested triggers or controlled write procedures when appropriate.
- Run periodic reconciliation checks for financial or high-integrity data.

Avoid **relying solely on promises from individual services** that they will keep totals synced: systems often acquire extra write paths like imports, batch jobs, or ops scripts.

## 8. Constraints Also Carry Operational Costs

Strong constraints do not mean ignoring performance:

- Foreign keys check referenced rows on inserts and updates.
- When deleting parent rows, PostgreSQL scans child rows; lacking an index on the child FK column makes this slow.
- Unique indexes verify uniqueness on write and add index maintenance overhead.
- Complex constraints or triggers slow down write transactions.

Even so, **never drop constraints just to boost a short-lived benchmark**. Systems require correctness; if a constraint becomes a real bottleneck, revisit data modeling, supporting indexes, and batched transaction patterns.

### Adding Constraints to Huge Tables with Historical Data

In PostgreSQL, certain constraints like `FOREIGN KEY` and `CHECK` support a two-step rollout:

~~~sql
ALTER TABLE review_lab.orders
ADD CONSTRAINT ck_orders_reasonable_amount
CHECK (total_amount <= 999999999999.99)
NOT VALID;

ALTER TABLE review_lab.orders
VALIDATE CONSTRAINT ck_orders_reasonable_amount;
~~~

Run this only when the bound matches business rules. `NOT VALID` skips scanning **existing** rows while enforcing the constraint on new/updated rows immediately. `VALIDATE CONSTRAINT` scans historical rows afterward to mark the constraint validated.

This is **not zero-lock**: DDL statements still acquire locks per PostgreSQL rules. Test on production-sized tables and plan migrations carefully.

For `NOT NULL` or `UNIQUE` on huge tables, workflows and locking differ—never assume every constraint supports `NOT VALID` identically.

## 9. Evaluating Growth: Forecast Beyond Raw Row Counts

Suppose a system ingests **200,000 order events per day**. Each event has fixed columns, timestamps, IDs, and a `jsonb payload`, averaging **700 bytes** of logical data before storage overhead.

~~~text
New rows/day = 200,000
Assumed logical data/row = 700 bytes

New logical data/day
    = 200,000 × 700
    = 140,000,000 bytes
    ≈ 140 MB/day (decimal)

Over 365 days:
    = 140 MB × 365
    = 51,100 MB
    ≈ 51.1 GB logical data
~~~

**51.1 GB is not PostgreSQL's actual disk footprint.** You must also factor in:

- Per-row tuple headers, alignment padding, page headers, and free space.
- B-tree and secondary indexes on queried columns.
- TOAST storage for out-of-line or compressed large values.
- Dead tuple versions from MVCC updates/deletes awaiting vacuum.
- WAL, temporary files, replication slots, and WAL retention windows.
- Disk space for backups, restores, index rebuilds, and maintenance.

Even the "700 bytes/row" estimate grows as `payload` schemas evolve. A design built for year three looks at **growth rate, data age, and historical access patterns**, not simply multiplying a tiny sample by years.

### Measuring Size Over Time

In PostgreSQL:

~~~sql
SELECT
    pg_size_pretty(
        pg_relation_size('review_lab.orders'::regclass)
    ) AS main_relation_size,
    pg_size_pretty(
        pg_indexes_size('review_lab.orders'::regclass)
    ) AS index_size,
    pg_size_pretty(
        pg_total_relation_size('review_lab.orders'::regclass)
    ) AS total_relation_size;
~~~

Size functions compared:

| Function | Typical Meaning |
| --- | --- |
| `pg_relation_size` | Size of the specified relation/fork alone, excluding indexes/TOAST |
| `pg_table_size` | Table size including associated storage such as TOAST |
| `pg_indexes_size` | Combined size of all indexes attached to the table |
| `pg_total_relation_size` | Total footprint including table, indexes, and dependent storage |
| `pg_size_pretty` | Formats byte counts into human-readable units |

Inspect the largest tables in the practice schema:

~~~sql
SELECT
    c.relname AS table_name,
    pg_size_pretty(pg_table_size(c.oid)) AS table_size,
    pg_size_pretty(pg_indexes_size(c.oid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'review_lab'
  AND c.relkind = 'r'
ORDER BY pg_total_relation_size(c.oid) DESC;
~~~

`relkind = 'r'` selects standard heap tables. When using partitioned tables later, the parent table holds no data itself; measure leaf partitions and aggregate totals deliberately.

**Measure at least across two points in time** (e.g., daily) to see growth rate. A single 100 GB snapshot does not tell you whether the database is flat or growing by 10 GB/day.

## 10. How MVCC, UPDATE, DELETE, and Autovacuum Affect Footprint

PostgreSQL uses **Multi-Version Concurrency Control (MVCC)**. Updating a row normally writes a new tuple version rather than overwriting bytes in place. Old versions must be reclaimed once no active transaction needs them.

Direct schema implications:

- Heavily `UPDATE`d tables accumulate dead tuples rapidly.
- Indexing frequently mutated columns increases write amplification.
- Long-running transactions pin old tuple versions and delay cleanup.
- Autovacuum needs headroom to reclaim dead tuples and refresh statistics.
- Update/delete-heavy tables can grow in disk size even when logical row count stays flat.

### Checking Table Statistics

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    last_autovacuum,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'review_lab'
ORDER BY relname;
~~~

`n_live_tup` and `n_dead_tup` are **statistical estimates**, not exact point-in-time counts. Write counters accumulate since stats reset and can reset across restarts or system actions.

**Never declare a table "severely bloated" solely from one high `n_dead_tup` reading.** Examine update rates, autovacuum runs, transaction ages, disk growth, and proper bloat diagnostics.

### VACUUM vs. VACUUM FULL

- Standard `VACUUM` reclaims dead tuples for internal reuse inside the relation without shrinking OS files aggressively.
- `VACUUM (ANALYZE)` vacuums and updates planner statistics together when needed.
- `VACUUM FULL` rewrites the entire table to shrink disk size, yet requires heavy locks, extra temporary disk space, and high I/O—**never schedule it as routine online maintenance**.

A 10-million-row table under heavy constant updates can pose bigger operational challenges than a 50-million-row append-only table. Thus **update/delete churn** is a first-class design variable.

### HOT Updates and Index Choices

PostgreSQL can perform **Heap-Only Tuple (HOT) updates** when conditions allow—notably when no indexed columns change and sufficient free space exists on the heap page—avoiding inserting new index entries.

Adding indexes onto frequently updated columns like `status` or `updated_at` reduces HOT update eligibility and raises write cost. That **does not mean never index `status`**: weigh query gains against real update costs.

## 11. When Should You Consider Partitioning?

**Partitioning** splits one logical table into physical child tables by a rule, such as monthly ranges on `event_at`.

For a fast-growing event table:

~~~text
order_events (logical table)
│
├── order_events_2026_10   [2026-10-01, 2026-11-01)
├── order_events_2026_11   [2026-11-01, 2026-12-01)
├── order_events_2026_12   [2026-12-01, 2027-01-01)
└── ...
~~~

Partitioning is worth evaluating when:

1. Data is very large and queries consistently filter by the **partition key**.
2. Old data is purged or archived on time-window schedules.
3. Maintenance, backups, or data operations benefit from per-partition management.
4. Partition count and impact on planning, constraints, and ops stay reasonable.

### Time-Based RANGE Partitioning Example

Create a standalone table for illustration (without replacing `review_lab.order_events`):

~~~sql
CREATE TABLE review_lab.events_partitioned (
    event_id bigint NOT NULL,
    occurred_at timestamptz NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (event_id, occurred_at)
) PARTITION BY RANGE (occurred_at);

CREATE TABLE review_lab.events_2026_10
PARTITION OF review_lab.events_partitioned
FOR VALUES FROM ('2026-10-01 00:00:00+00')
             TO ('2026-11-01 00:00:00+00');

CREATE TABLE review_lab.events_2026_11
PARTITION OF review_lab.events_partitioned
FOR VALUES FROM ('2026-11-01 00:00:00+00')
             TO ('2026-12-01 00:00:00+00');
~~~

Queries matching the partition key benefit from **partition pruning**, skipping irrelevant partitions:

~~~sql
SELECT event_id, event_type
FROM review_lab.events_partitioned
WHERE occurred_at >= '2026-11-01 00:00:00+00'
  AND occurred_at <  '2026-12-01 00:00:00+00';
~~~

### Unique Key Constraints Under Partitioning

In PostgreSQL, a `PRIMARY KEY` or `UNIQUE` constraint on a partitioned table is constrained by the partition key. Here the primary key must include **`occurred_at`**, the partition key, so PostgreSQL can enforce uniqueness per partition.

That is a major trade-off if the legacy table used `event_id` alone as PK with other tables referencing it. You cannot casually convert an existing table to monthly partitioning without redesigning keys, foreign keys, and migration strategy.

### Partitioning Does Not Guarantee Fast Queries

If a query filters by:

~~~sql
WHERE event_id = 123456
~~~

on a table partitioned by `occurred_at`, PostgreSQL cannot prune partitions from `event_id` alone and may scan every partition. Too many partitions also complicate admin work, stats, planning, and index maintenance.

**Do not partition simply because "we're about to hit a million rows".** First verify which part of the workload actually benefits from pruning, retention drops, or lifecycle management. A well-indexed table with tens of millions of rows often runs great without partitioning.

## 12. Retention and Long-Term Growth

Different tables have different lifecycles:

| Data Type | Read Frequency | Lifecycle to Consider |
| --- | --- | --- |
| Customers | Frequent lookups | Long-term retention per business & compliance |
| Paid orders | May need multi-year reconciliation | Keep per business/accounting policies |
| Detailed technical events | Read during incident debugging | Often shorter retention |
| Verbose debug logs | Rarely read after a short window | Offload externally or purge on schedule |

If an event table grows by 200,000 rows/day with a 90-day retention window, steady-state sits around **the most recent 18 million rows** before accounting for bursts, backlogs, and storage overhead. Design cleanup around throughput and legal/business rules.

On time-partitioned tables, detaching/dropping expired partitions per an approved runbook can be far cleaner than running giant `DELETE`s on a monolithic table—though references, archival needs, and DDL lock windows still require evaluation.

**Never auto-delete rows solely by creation date** without verifying retention, audit, backup, permission, and historical query requirements.

## 13. Using PostgreSQL Statistics to Spot Fixes Needed

Beyond table size, inspect how indexes are actually used:

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    indexrelname AS index_name,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'review_lab'
ORDER BY relname, indexrelname;
~~~

Meaning:

- `idx_scan`: number of index scans initiated.
- `idx_tup_read`: number of index entries returned by scans.
- `idx_tup_fetch`: number of live table rows fetched by index scans.

These counters depend on time elapsed since the last stats reset. Seeing `idx_scan = 0` **is not enough proof to drop an index**, especially if it backs a `PRIMARY KEY`/`UNIQUE` constraint, serves a rare yet critical monthly job, or stats haven't spanned a representative cycle.

### pg_stat_statements When Configured

When `pg_stat_statements` is installed and configured, inspect the costliest SQL statements:

~~~sql
SELECT
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

This query **will not run out of the box on every PostgreSQL instance**: the extension may not be enabled, requires `shared_preload_libraries` configuration and privileges, and column names can vary slightly across versions.

Its biggest value is surfacing **real application workload**, preventing you from tuning a synthetic test query while the real bottleneck sits in a completely different endpoint.

### Combining Multiple Data Sources

| Question | Reference Source |
| --- | --- |
| Which queries consume the most total time? | `pg_stat_statements` or APM / slow logs |
| Does the planner use the index? | `EXPLAIN`, `EXPLAIN (ANALYZE, BUFFERS)` |
| How much disk do tables/indexes use? | `pg_total_relation_size`, `pg_indexes_size` |
| Is the table write/delete-heavy? | `pg_stat_user_tables` |
| Is an index used across full load cycles? | `pg_stat_user_indexes` |
| Are dead tuples piling up or autovacuum lagging? | `pg_stat_user_tables` and vacuum monitoring |
| How much physical disk remains? | OS / managed service metrics |
| How does peak load fluctuate? | Time-series metrics, APM, workload logs |

## 14. Normalization, Denormalization, and JSONB: Evidence-Based Choices

### 14.1. Normalize to Protect Relationships

Designing:

~~~text
customers(customer_id, email, display_name)
orders(order_id, customer_id, ...)
order_items(order_item_id, order_id, sku, quantity, unit_price)
~~~

avoids copying customer name and email onto **every order line** and having to mass-update them on profile edits, while giving customer identity a single source of truth and clean foreign keys.

Still, order history often needs **snapshots at placement time** (such as recipient name or agreed sale price) for reconciliation. Keeping those snapshots is valid business modeling, not "bad normalization".

### 14.2. Denormalization Carries Sync Costs

For example, storing `total_amount` on `orders`:

**Benefit:** order list screens skip summing `order_items` every load.

**Cost:** must stay synced across line inserts/edits/deletes, promotions, taxes, and refunds. Define the **source of truth** and atomic update workflow explicitly.

Every stored derived value should have:

1. A concrete measured performance reason.
2. Consistent same-transaction update logic.
3. Reconciliation checks or tests proving zero drift.
4. A repair procedure if drift is ever detected.

### 14.3. JSONB: Flexible, Yet Never Discard Crucial Constraints

`order_events.payload jsonb` fits heterogeneous metadata across event types. Yet fields that are always required, used in `JOIN`s, or need foreign keys/uniqueness normally belong in **typed relational columns**.

Example:

~~~sql
SELECT event_id, event_at
FROM review_lab.order_events
WHERE payload @> '{"gateway":"sandbox"}'::jsonb;
~~~

If this JSONB containment query runs heavily over large datasets, consider an operator-compatible **GIN index**. Still, GIN indexes consume disk and write bandwidth; never index every JSONB column blindly.

Pick JSONB for **genuine schema flexibility**, not to avoid modeling stable business fields and relationships properly.

## 15. Multi-Tenant Keys and Data Boundaries

In **multi-tenant** systems, verify whether every tenant-owned table includes `tenant_id` and whether foreign keys enforce tenant boundaries.

Example model:

~~~sql
CREATE TABLE review_lab.tenant_warehouses (
    tenant_id bigint NOT NULL,
    warehouse_id bigint NOT NULL,
    name text NOT NULL,
    PRIMARY KEY (tenant_id, warehouse_id)
);

CREATE TABLE review_lab.tenant_inventory (
    tenant_id bigint NOT NULL,
    warehouse_id bigint NOT NULL,
    sku text NOT NULL,
    quantity integer NOT NULL CHECK (quantity >= 0),
    PRIMARY KEY (tenant_id, warehouse_id, sku),
    FOREIGN KEY (tenant_id, warehouse_id)
        REFERENCES review_lab.tenant_warehouses
            (tenant_id, warehouse_id)
);
~~~

The composite foreign key blocks an inventory row in tenant A from mistakenly referencing a warehouse in tenant B. Using a bare `warehouse_id` FK without tenant context leaves cross-tenant validation entirely up to application code.

In production, pair this with **Row-Level Security (RLS)** or equivalent access control if tenants require strict read/write isolation. Composite foreign keys protect data links, yet **do not replace authorization**.

Multi-tenancy also shapes index design: when nearly all queries filter by `WHERE tenant_id = ?`, indexes often need `tenant_id` as their leading column.

## 16. Decision Flowchart for Schema Evaluation

~~~text
               Concrete queries & business rules known?
                                  |
                         +--------+--------+
                         |                 |
                        No                Yes
                         |                 |
                Gather workload      Identify WHERE, JOIN,
                & data requirements  ORDER BY, returned columns
                                           |
                                           v
                                 Do PK/FK/CHECK/UNIQUE
                                 protect all valid states?
                                           |
                                +----------+----------+
                                |                     |
                               No                    Yes
                                |                     |
                         Add appropriate        Inspect EXPLAIN
                         constraints            on realistic data
                                |                     |
                                +----------+----------+
                                           |
                                           v
                              Measure BOTH read & write costs
                                           |
                                           v
                               How fast will data grow?
                                           |
                              +------------+-------------+
                              |                          |
                        Moderate growth            Rapid growth / retention
                              |                          |
                      Indexes + vacuum           Consider partitioning,
                      + stats sufficient?        history tables, archiving
                              |                          |
                              +------------+-------------+
                                           |
                                           v
                                Test, benchmark, and
                                deploy with rollback
~~~

Never start with "let's make monthly partitions" before knowing if queries filter by time, and never "index every column" before understanding write ratios.

## 17. Pre-Launch Schema Evaluation Table

| Category | Question to Answer | Expected Evidence |
| --- | --- | --- |
| Queries | What are the critical query patterns? | Query inventory, frequencies, p95/p99 targets |
| Filters & JOINs | Do indexes support key predicates? | `EXPLAIN` and real execution plans |
| Sorting & Pagination | Does `ORDER BY LIMIT` trigger expensive sorts? | Plan and latency on representative data |
| Keys | Are PKs stable and business unique keys enforced? | DDL and duplicate-data tests |
| Relationships | Do FKs exist with proper delete/update actions? | DDL, orphan tests, parent-delete tests |
| Domains | Are nullability, ranges, and non-negatives checked? | `NOT NULL`, `CHECK`, and invalid-data tests |
| Consistency | Are derived fields synced cleanly? | Transaction/trigger/reconciliation design |
| Writes | Do indexes/triggers slow inserts/updates excessively? | Write benchmarks and tuple/index stats |
| Growth | How fast do tables, indexes, and TOAST grow? | Multi-point size measurements |
| MVCC | How are dead tuples, autovacuum, and long transactions behaving? | Vacuum stats and alerts |
| Retention | What must be kept, deleted, or archived? | Data policies and enforcement jobs |
| Partitioning | Are pruning/retention gains worth the complexity? | Benchmarks with realistic partition counts |
| Operations | Have backups, restores, migrations, and rollbacks been tested? | Drill results and checklists |

Not every item is an SQL query. Several answers require alignment with product, security, and operations teams.

## 18. Process for Improving a Live Schema

Suppose `review_lab.orders` now holds millions of rows and Q2 has slowed down. A disciplined workflow:

### Step 1. Pick an Evidence-Backed Problem

Confirm Q2 consumes major total time or exceeds p95 targets during peak hours. Never optimize just because a `SELECT` "looks complicated".

### Step 2. Inspect Plan and Data Distribution

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status, created_at, total_amount
FROM review_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Check which index the planner chose, whether a `Sort` ran, estimated vs. actual rows, and buffer I/O.

### Step 3. Propose a Small, Measurable Change

If workload warrants it, propose:

~~~sql
CREATE INDEX idx_orders_customer_created
ON review_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
);
~~~

This is the lab index statement. On large production tables, consider `CREATE INDEX CONCURRENTLY` to minimize write blocking; note it has prerequisites and extra cost, **cannot run inside a transaction block**, and can leave an `INVALID` index behind on failure that must be cleaned up.

Never add an index if an equivalent one exists or measurements show write overhead outweighs read gains.

### Step 4. Assess Impact on Constraints and Existing Data

When changes go beyond adding an index—touching keys, data types, or partitioning—verify:

- Whether existing data violates new constraints.
- Which foreign keys and views depend on old structures.
- Whether older app instances stay live during rolling deployments.
- Whether migrations acquire heavy locks, rewrite tables, or need extra disk space.

Prefer **expand–migrate–contract** for breaking changes: add new structures, backfill/migrate data, transition apps, verify, and drop old structures last.

### Step 5. Measure Both Benefits and Costs

After deploying, compare under equivalent load:

- p95/p99 and total execution time of Q2.
- Rows scanned and sort operations eliminated.
- `INSERT/UPDATE` throughput, commit latency, and index overhead.
- Table/index sizes and autovacuum health.

**Never declare victory just because `EXPLAIN` switched to `Index Scan`.** The true goal is correctness and overall workload efficiency as data scales.

## 19. Common Mistakes

### Mistake 1: Designing Only for Tiny Sample Data

With a few hundred rows, every query looks fast. Failing to anticipate data growth and customer/status skew leads to broken indexes and keys a year later.

### Mistake 2: Equating Normalization with Optimal Performance

Normalization prevents anomalies, yet hot queries still need proper indexes and sometimes derived summaries—with strict sync rules and tests.

### Mistake 3: Assuming Foreign Keys Automatically Index Child Columns

PostgreSQL indexes the **referenced** side via PK/`UNIQUE`, yet **does not automatically index child FK columns**. Evaluate child indexes for queries and parent modifications.

### Mistake 4: Using `CHECK` While Forgetting `NOT NULL`

`CHECK (quantity > 0)` does not reject `NULL`. When quantity is mandatory, pair `NOT NULL` with the domain check.

### Mistake 5: Thinking More Indexes Are Always Better

Redundant indexes waste disk, slow writes, and hurt HOT updates. Tailor indexes to real queries and measure write costs.

### Mistake 6: Treating `n_live_tup` as an Exact `COUNT`

`pg_stat_user_tables.n_live_tup` is an estimate. Use proper queries when exact accounting counts are required, and use stats for growth trends.

### Mistake 7: Partitioning to "Make Every Query Fast"

Partitioning helps pruning and retention, yet complicates PK/`UNIQUE`/FK rules, indexes, and operations. Queries without partition-key predicates can still touch many partitions.

### Mistake 8: Ignoring MVCC, Vacuum, and WAL

Logical row count alone hides disk footprint. Update/delete churn, TOAST, indexes, WAL, and temp files heavily impact disk usage and recovery time.

### Mistake 9: Using JSONB for Every Field

JSONB shines for flexible metadata, while entity IDs, relational keys, and constrained business fields belong in typed columns with real constraints.

### Mistake 10: Optimizing Read Latency While Dropping Correctness

An optimization that drops constraints and allows orphaned rows creates long-term maintenance nightmares. Consistency is a non-negotiable baseline for tuning.

## 20. Practice Exercises

### Exercise 1. Workload Analysis

An application frequently runs:

~~~sql
SELECT order_id, created_at, status
FROM review_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Propose an index and explain the order of each column. With only a few sample rows, why might the planner still choose `Seq Scan`?

### Exercise 2. Foreign Keys and Indexes

`order_events` has an FK `order_id` referencing `orders.order_id`. Without an index on `order_events.order_id`, does PostgreSQL automatically create a dedicated B-tree index on the child column? Which queries would justify adding one?

### Exercise 3. CHECK and NULL

Given:

~~~sql
quantity integer CHECK (quantity > 0)
~~~

Can this column accept `NULL`? If business requires at least one unit, how should it be declared?

### Exercise 4. UNIQUE and Email

`UNIQUE (email)` can treat `Lan@Example.test` and `lan@example.test` as distinct under default comparison rules. If the business requires case-insensitive uniqueness, what else must you design?

### Exercise 5. Order Totals

Why can storing `orders.total_amount` alongside `order_items.quantity × unit_price` cause data drift? Name two ways to maintain consistency if you still want fast total reads.

### Exercise 6. Growth Forecasting

An event table grows by **100,000 rows/day** with **500 bytes/row** of logical data. Estimate 30-day logical growth in decimal MB; why will `pg_total_relation_size` differ from that number?

### Exercise 7. Evaluating Partitioning

A 50-million-row events table is queried primarily via `WHERE event_id = ?`, yet someone proposes partitioning by `occurred_at`. Is this guaranteed to improve performance? What conditions and measurements should you check?

### Exercise 8. Reading Growth Metrics

Write SQL to inspect:

1. Total size of `review_lab.order_events`.
2. `n_live_tup`, `n_dead_tup`, and `last_autovacuum` for that table.
3. Existing indexes and scan counts via `pg_stat_user_indexes`.

### Exercise 9. Constraints on Large Tables

A 100-million-row table needs a new `CHECK` constraint. Explain the benefit of `NOT VALID` followed by `VALIDATE CONSTRAINT`, and why you must still evaluate locking and data compliance.

### Exercise 10. Deciding on JSONB

In `order_events`, `event_type` is filtered frequently while `payload` holds varying metadata per event type. Should you drop `event_type` and put everything into one JSONB column? Explain trade-offs around constraints, queries, and indexes.

### Suggested Answers

| Exercise | Direction |
| --- | --- |
| 1 | `(customer_id, created_at DESC, order_id DESC)`; on tiny tables a sequential scan is cheaper than index overhead |
| 2 | No. Evaluate `order_id` event-history lookups and FK checks on parent deletes/updates |
| 3 | Yes, it accepts `NULL`; combine `NOT NULL` with `CHECK (quantity > 0)` |
| 4 | Consider a unique expression index on `lower(email)` or an explicit normalization/type/collation policy after cleaning duplicates |
| 5 | Both sources can be updated at different times or via different paths. Compute dynamically on read or sync totals in the same transaction + reconcile |
| 6 | `100,000 × 500 × 30 = 1,500,000,000 bytes = 1,500 MB`; actual size differs due to indexes, tuple/page headers, TOAST, MVCC dead tuples, and storage overhead |
| 7 | Not guaranteed. Event ID queries cannot prune time partitions; verify partition-key filtering and retention benefits |
| 8 | Combine `pg_total_relation_size`, `pg_stat_user_tables`, and `pg_stat_user_indexes` |
| 9 | `NOT VALID` defers scanning existing rows, `VALIDATE` checks them afterward; DDL still acquires locks and data must conform |
| 10 | Not recommended by default. Stable, frequently filtered/constrained fields belong in columns; JSONB suits flexible metadata |

Example solution for Exercise 8:

~~~sql
SELECT pg_size_pretty(
    pg_total_relation_size('review_lab.order_events'::regclass)
) AS total_size;

SELECT
    relname, n_live_tup, n_dead_tup, last_autovacuum
FROM pg_stat_user_tables
WHERE schemaname = 'review_lab'
  AND relname = 'order_events';

SELECT
    indexrelname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'review_lab'
  AND relname = 'order_events'
ORDER BY indexrelname;
~~~

## 21. Quick Reference Table for Schema Reviews

| Goal | Tool or Check |
| --- | --- |
| Inspect table DDL and constraints | `\d+ review_lab.orders` in `psql` |
| Estimated row counts | `pg_stat_user_tables` or `pg_class.reltuples` |
| Measure table + index footprint | `pg_total_relation_size()` |
| Measure index footprint | `pg_indexes_size()` |
| List existing indexes | `pg_indexes`, `\di`, or `pg_stat_user_indexes` |
| View estimated plan | `EXPLAIN SELECT ...` |
| Measure actual execution plan | `EXPLAIN (ANALYZE, BUFFERS) SELECT ...` |
| Spot expensive queries | `pg_stat_statements` when enabled |
| Monitor vacuum / dead tuples | `pg_stat_user_tables` |
| Protect relationships | `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE` |
| Protect value domains | `NOT NULL`, `CHECK` |
| Handle time-growing tables | Measure growth rate, retention, indexes, and partitioning when justified |
| Evolve schemas safely | Staging tests, migrations, dependency audits, backups/rollbacks |

## 22. Conclusion

Every PostgreSQL schema should be evaluated through **three recurring questions**:

**First: how does the system read and write data?** Collect real queries and inspect `WHERE`, `JOIN`, `ORDER BY`, returned row counts, latency, and actual plans before picking indexes or table layouts.

**Second: where is valid data protected?** Use primary keys, foreign keys, `UNIQUE`, `NOT NULL`, and `CHECK` constraints to block bad data even when application code or ops scripts fail. For derived or denormalized values, enforce explicit synchronization rules.

**Third: how will this design behave at 10× or 100× scale?** Track table/index sizes, write/delete churn, MVCC/vacuum health, retention policies, and migration safety. Adopt partitioning or major structural changes only when real evidence shows benefits outweigh costs.

A strong schema is **accurate for the data, tailored to the workload, and safely evolvable as scale changes**. Schema review should be an ongoing practice guided by live metrics—not something that ends the day your first `CREATE TABLE` runs cleanly.
