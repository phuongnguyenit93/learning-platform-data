# Indexes, Keys, and Execution Plans at a Readable Level

## Lesson Objectives

When a Spring application reads orders using JDBC, JPA, or Spring Data, the final query still has to be executed by the database management system. A concise `findByCustomerId(...)` call in Java can run very fast or very slowly depending on table structure, indexes, record count, filter predicates, and the execution plan.

After this lesson, you should be able to:

1. Distinguish an **index** from a **primary key**, a **foreign key**, and a **UNIQUE** constraint.
2. Understand why having an index can sometimes make queries faster, and why **having an index does not mean the database will use it**.
3. Look at `WHERE`, `JOIN`, `ORDER BY`, and `LIMIT` in a query to spot when an index may help.
4. Read essential parts of an `EXPLAIN` plan: scan type, index-applied conditions, remaining filters, join algorithms, sorting, estimates, and actual measurements.
5. Follow a minimal investigation workflow for a slow query in a Spring app's data-access layer instead of adding indexes by guesswork.

The hands-on statements use **PostgreSQL** for concrete syntax and plan reading. General principles are similar across relational DBMSs, while operator names, `EXPLAIN` formatting, and optimizer details vary across PostgreSQL, MySQL, SQL Server, Oracle, and others. This is knowledge geared toward application developers, not a deep database administration/tuning manual.

## 1. Three Concepts to Keep Separate

Suppose an application has `customers` and `orders` tables. One customer has many orders.

- A **key / constraint** answers questions about **data correctness**: which row is unique, and is a referential link valid?
- An **index** is a **data-access structure** that helps the database find, filter, or read in a given order more efficiently for certain queries.
- An **execution plan** is the **strategy chosen by the database for a specific SQL statement**: how to scan each table, which algorithm joins tables, whether sorting is needed, and how many rows are processed.

For example, a foreign key constraint ensures `orders.customer_id` points to a real customer; an index on `orders.customer_id` can speed up finding orders by customer; and the execution plan shows whether the database **actually chose** that index when running the query.

Avoid confusing two meanings of "key" vs. "lock": **primary/foreign keys** are identifying/referential keys in the data model; **row locks/table locks** are concurrency locks when transactions access data. Most of this lesson covers *keys*, not *locking*; section 8 briefly distinguishes them.

## 2. Primary Keys, Unique Keys, and Foreign Keys

### 2.1. Primary Key (PK): Identifying a Row

A **primary key** uniquely identifies each row in a table. Values of the PK column or column tuple must be **unique and non-NULL**; a table has at most **one PRIMARY KEY constraint** (which may span multiple columns).

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL
);
```

In this table, `id` is the PK. Two customers cannot share the same `id`, and `id` cannot be NULL. A PK can be a natural key such as a country code or a surrogate key such as an auto-incrementing integer or UUID. Choose a stable key that rarely changes; do not default to using email or phone number as the PK since those values can change under business rules.

In **PostgreSQL**, declaring a PK also creates a **unique B-tree index** to enforce uniqueness; however, **a PK is a constraint carrying data semantics, not merely an index**. Many DBMSs create supporting indexes for constraints similarly, though details differ.

### 2.2. UNIQUE: Preventing Duplicates per Business Rule

`UNIQUE` constrains the uniqueness of a column or combination of columns. For instance, `customers.email UNIQUE` prevents two rows from sharing an email. It does not turn email into the PK and does not require `NOT NULL` by default.

```sql
CREATE TABLE order_lines (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, line_no)
);
```

This is a **composite primary key** example: `order_id` can repeat across rows and `line_no` can repeat across different orders, yet the **pair** `(order_id, line_no)` must be unique. You can add `UNIQUE(order_id, product_id)` if business rules require each product to appear at most once per order; that is a separate business decision from the PK.

**NULL note:** in PostgreSQL, `UNIQUE` by default allows multiple rows with NULL in the unique column, because NULLs are treated as distinct during uniqueness checks. PostgreSQL supports `NULLS NOT DISTINCT` when NULLs should be treated as duplicates. Do not apply this rule mechanically to every DBMS.

### 2.3. Foreign Key (FK): Preserving Referential Relationships

```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    created_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
);
```

`orders.customer_id` is an **FK** referencing `customers.id`. It prevents an order from storing a `customer_id` absent from `customers`. `NOT NULL` here also prevents orders unattached to a customer. Omitting `NOT NULL` allows NULL FKs under SQL rules.

When deleting or updating a referenced row's PK, the database checks FK constraints. Policies such as `ON DELETE RESTRICT`, `NO ACTION`, `CASCADE`, and `SET NULL` must reflect business rules. For example, `CASCADE` may suit deleting line items when deleting an order, yet risks unintended data loss if used on a "customer — order" relationship.

**Common pitfall:** in PostgreSQL, declaring an FK **does not automatically create an index on the referencing column** (`orders.customer_id`). The referenced customer side already has an index from its PK/unique constraint; the orders side may need its own index for customer lookups and to assist FK checks when deleting/updating customers. Do not blindly create a single-column index on every FK: consider query patterns, table size, existing composite indexes, and write overhead.

| Construct | Primary Purpose | Guarantees Unique Rows? | Can Speed Up Queries? |
| --- | --- | --- | --- |
| `PRIMARY KEY` | Unique, non-NULL row identifier | Yes | Yes, via backing index in PostgreSQL |
| `UNIQUE` | Enforces no-duplicate rule | Yes, per DBMS NULL rules | Yes, via backing unique index |
| `FOREIGN KEY` | Ensures valid references | No | Depends on index on referencing column, not auto-created in PostgreSQL |
| Plain `CREATE INDEX` | Supports search, filter, join, sort | No | Possibly, when the optimizer finds it beneficial |

**Data integrity and performance are two separate decisions.** Never drop an FK to make queries "faster" if referential integrity remains a requirement; likewise, do not add extra indexes solely because a column is an FK.

## 3. How Do Indexes Work?

Imagine looking up a name in a very thick directory:

- Flipping page by page from front to back is like a **sequential scan**.
- Opening the sorted lookup section and jumping straight to the target name group uses the idea behind a **B-tree index**.

A B-tree index stores keys in organized order along with pointers to locate data rows. For conditions like `id = 42`, `created_at >= ?`, or matching sort orders, the database can use the tree to narrow the search range rather than reading every row. That is the mental model; actual execution involves data pages, buffer caches, row visibility, and physical access paths.

**Not every index is a B-tree.** PostgreSQL also offers Hash, GIN, GiST, BRIN, and others serving different operators and data types; this lesson focuses only on B-tree because it is the most common for comparisons, range searches, and sorting. Do not guess syntax or behavior of other index types without reading your DBMS documentation.

### 3.1. A Query That Can Benefit from an Index

```sql
SELECT id, created_at, status
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 20;
```

With millions of orders when only the 20 most recent orders of one customer are needed, this index is a sensible candidate:

```sql
CREATE INDEX orders_customer_created_at_idx
    ON orders (customer_id, created_at DESC);
```

In the composite B-tree `(customer_id, created_at DESC)`, entries sharing `customer_id` are grouped in order; the database *can* jump to that customer's group and read 20 results in timestamp order, avoiding scanning or sorting the whole table. `LIMIT` is especially effective when paired with an access path matching `ORDER BY`.

**However**, the optimizer may pick another plan when the table is tiny, the query returns a large fraction of rows, statistics differ, or estimated costs favor a sequential scan. **An index existing does not guarantee an `Index Scan`.**

### 3.2. Column Order in a Composite Index Matters Greatly

Compare:

```sql
CREATE INDEX idx_a ON orders (customer_id, created_at);
CREATE INDEX idx_b ON orders (created_at, customer_id);
```

These two indexes are **not equivalent** for `WHERE customer_id = 42 AND created_at >= ...`. In a PostgreSQL B-tree, an equality condition on the **leading column** and a range condition on the **next column** typically narrow the scanned portion of the index effectively. `idx_a` usually fits this query pattern better.

Practical guidelines:

- Start from real filter predicates, especially equality columns in `WHERE` or `JOIN`; then consider ranges, `ORDER BY`, and returned row counts.
- With `(customer_id, created_at)`, queries filtering by `customer_id` alone can leverage the index prefix; queries filtering only by `created_at` are generally less efficient than an index starting with `created_at`.
- PostgreSQL B-trees can sometimes use conditions on non-leading columns or additional strategies, so do not interpret the leading-column guideline as "strictly never usable."
- `ORDER BY created_at DESC` paired with `WHERE customer_id = ?` aligns well with a composite index leading with `customer_id` and matching time order; forward/backward scans and NULL ordering still depend on the index definition.
- One composite index may remove the need for some single-column indexes, though not automatically all of them; evaluate actual queries.

### 3.3. Selectivity, Cost, and Cases Where Indexes Help Little

**Selectivity** describes how tightly a condition distinguishes records. `WHERE id = 42` on a unique column normally selects one row; `WHERE status = 'NEW'` might match a huge fraction of the table. When a query must return most rows, a sequential scan can be cheaper than traversing an index and fetching numerous table pages.

An index also carries **costs**:

- Consumes disk space and buffer-cache memory.
- Adds maintenance work to `INSERT`, `UPDATE` (especially on indexed columns), and `DELETE`.
- As index count grows, write latency and operational overhead can increase.
- May not help if a query applies functions or casts to a column in a way a plain index does not support, such as `WHERE DATE(created_at) = DATE '2025-01-15'`.

Time-range queries can often be written as a **half-open interval** to leverage an ordinary B-tree index:

```sql
-- Instead of transforming created_at on every row:
SELECT id
FROM orders
WHERE created_at >= TIMESTAMPTZ '2025-01-15 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2025-01-16 00:00:00+00';
```

This example filters by a UTC day, not assuming the user's local time zone. When working with timestamps, verify the time zone and calendar boundaries required by the domain.

## 4. Execution Plan: What Does the Database Actually Intend to Do?

SQL is a **result-declarative** language: you describe what data to retrieve, not which B-tree or join algorithm to use. The **query planner/optimizer** analyzes SQL and table statistics to select an **operator tree** estimated to have low cost.

For instance, the same query might have candidate plans:

```text
Plan A: Seq Scan full orders → Filter by customer → Sort by timestamp → Limit 20
Plan B: Index Scan on (customer_id, created_at DESC) → Limit 20
```

If the query joins `orders` with `customers`, the plan also includes `Nested Loop`, `Hash Join`, or `Merge Join`. Lower branches fetch rows from tables or indexes; upper nodes combine, filter, group, sort, or limit results.

### 4.1. Enough Plan Nodes to Read and Understand

| PostgreSQL Node | Application-Level Reading |
| --- | --- |
| `Seq Scan` | Reads table sequentially; often sensible for small tables or queries returning most rows. Do not jump to calling this a bug. |
| `Index Scan` | Uses an index to find locations; typically still reads rows from the table heap. |
| `Index Only Scan` | Reads data stored in the index, though PostgreSQL may still check heap visibility; not always "zero table reads." |
| `Bitmap Index Scan` + `Bitmap Heap Scan` | Collects row locations from an index and reads table pages efficiently for moderate result counts. |
| `Filter` | Condition applied after fetching rows from a node; inspect `Rows Removed by Filter` when present. |
| `Index Cond` | Condition pushed down into the index scan itself, narrowing the search range. |
| `Sort` | Sorts results; may consume memory or spill to disk. |
| `Limit` | Fetches only the requested number of rows; can stop underlying nodes early. |
| `Nested Loop` | For each outer row, probes the inner branch; often good when the outer set is small and the inner branch has an efficient lookup. |
| `Hash Join` | Builds a hash table from one side and probes from the other; often helpful for equality joins on sizable sets. |
| `Merge Join` | Combines two inputs already sorted on the join key or paired with explicit sort steps. |
| `Aggregate` / `HashAggregate` | Performs sums, counts, and grouping via an appropriate strategy. |

**Node names are not good/bad grades.** `Nested Loop` is not inherently slow; `Seq Scan` is not inherently wrong; `Index Scan` is not inherently fast. Judge them in context of row counts, table sizes, predicates, and I/O cost.

### 4.2. Reading the Key Numbers

A PostgreSQL node can look like this (these numbers **only explain how to read**, not output from the exercise):

```text
Index Scan using orders_customer_created_at_idx on orders
  (cost=0.42..42.10 rows=20 width=36)
  (actual time=0.030..0.080 rows=20 loops=1)
```

- `cost=0.42..42.10`: **startup cost** and **estimated total cost** in planner cost units, **not milliseconds**.
- `rows=20` in the estimate section: **predicted output rows** from the node, not necessarily rows inspected.
- `width=36`: estimated average size of one output row, in bytes.
- `actual time=0.030..0.080`: actual elapsed milliseconds for the node when run with `ANALYZE`.
- `actual ... rows=20 loops=1`: average output rows per execution of the node and number of times the node executed. If `loops=100`, account for multiplication; for instance, an inner scan inside a nested loop can execute many times.
- `Buffers` (when requested): shows accessed/read data pages by type, helping spot I/O; measurements are affected by caches and repeat runs.

Never compare `cost=42.10` directly with `actual time=0.080` because they are **two different units**. Instead, compare `estimated rows` against `actual rows` (watching `loops`), look for where most work occurs, spot expensive sorts or heavy page reads, and inspect filter predicates.

### 4.3. `EXPLAIN` vs. `EXPLAIN ANALYZE`

```sql
EXPLAIN
SELECT id FROM orders WHERE customer_id = 42;

EXPLAIN (ANALYZE, BUFFERS)
SELECT id FROM orders WHERE customer_id = 42;
```

- `EXPLAIN` without `ANALYZE`: shows the **plan and estimates** without running the `SELECT` query to measure real timing/rows.
- `EXPLAIN (ANALYZE, BUFFERS)`: **actually executes** the query and records timing, row counts, and buffer stats. Normal query rows are suppressed, yet the SQL work still runs.
- **Do not run `EXPLAIN ANALYZE` casually on `INSERT`, `UPDATE`, `DELETE`, or `MERGE` in production:** the statement executes and modifies data. When analyzing write statements, use an appropriate test environment; a transaction with `ROLLBACK` can undo DB changes in many situations, though it cannot undo external side effects like emitting events.
- For large read queries, `ANALYZE` still imposes real load; pick an appropriate time and environment.

Execution plans depend on **database version, data, statistics, query parameters, existing indexes, and configuration**. Never memorize one plan shape as a single "canonical" output across all environments.

## 5. Hands-On: Before and After Creating an Index

This example uses **PostgreSQL 17+**, executed within **a single connection session** via `psql` or a SQL runner. The tables are `TEMP` and vanish when the session ends. You can save the script to `index_plan_demo.sql` and run `psql -d test_database_name -f index_plan_demo.sql`; a PostgreSQL database and temp-table privileges are required. **Run once per session**, because temp table names will collide if repeated in the same session.

```sql
-- 1. Create tables and integrity constraints.
CREATE TEMP TABLE demo_customers (
    id BIGINT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE
);

CREATE TEMP TABLE demo_orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES demo_customers(id),
    created_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('NEW', 'PAID'))
);

-- 2. Generate sample data (100 customers, 30,000 orders).
INSERT INTO demo_customers (id, email)
SELECT n, 'user' || n || '@example.test'
FROM generate_series(1, 100) AS g(n);

INSERT INTO demo_orders (customer_id, created_at, status)
SELECT ((n - 1) % 100) + 1,
       TIMESTAMPTZ '2025-01-01 00:00:00+00'
           + n * INTERVAL '1 minute',
       CASE WHEN n % 7 = 0 THEN 'PAID' ELSE 'NEW' END
FROM generate_series(1, 30000) AS g(n);

-- 3. Collect statistics so the planner has estimation data.
ANALYZE demo_customers;
ANALYZE demo_orders;

-- 4. Execution plan BEFORE having a dedicated index for this query.
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, customer_id, created_at, status
FROM demo_orders
WHERE customer_id = 42
  AND created_at >= TIMESTAMPTZ '2025-01-10 00:00:00+00'
ORDER BY created_at DESC
LIMIT 20;

-- 5. Create composite index matching filter + sort order.
CREATE INDEX demo_orders_customer_created_at_idx
    ON demo_orders (customer_id, created_at DESC);

ANALYZE demo_orders;

-- 6. Re-run the EXACT same query to compare plans.
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, customer_id, created_at, status
FROM demo_orders
WHERE customer_id = 42
  AND created_at >= TIMESTAMPTZ '2025-01-10 00:00:00+00'
ORDER BY created_at DESC
LIMIT 20;

-- 7. Check the number of created rows.
SELECT (SELECT COUNT(*) FROM demo_customers) AS customer_count,
       (SELECT COUNT(*) FROM demo_orders) AS order_count;
```

The row counts are deterministic: `customer_count = 100` and `order_count = 30000`. **There is no single fixed `EXPLAIN` stdout**: plans, timings, and buffer counts vary across runs, machines, and versions; in particular, consecutive runs can be affected by cached data.

What to observe:

1. Before creating the composite index, check whether `Seq Scan` and `Sort` appear, and read `Filter` and returned row counts. The PK index on `id` does not necessarily help a query filtering by `customer_id`.
2. After creating `(customer_id, created_at DESC)`, observe whether the planner chooses `Index Scan` with `Index Cond` and eliminates `Sort`. One plausible **schematic** plan (not a mandatory output):

   ```text
   Limit
     -> Index Scan using demo_orders_customer_created_at_idx on demo_orders
          Index Cond: (customer_id = 42 AND created_at >= ...)
   ```

3. Read `actual rows` and `Buffers` on notable nodes; see whether the DB had to process excessive rows before yielding 20 rows.
4. If `Seq Scan` still appears, **do not force an index immediately**. Check table size, statistics, filtered row ratio, access cost, and whether total work actually drops.
5. If you add `AND status = 'PAID'` without `status` in the index, the plan may use `Index Cond` for customer/time and an additional `Filter` for status; this is not automatically wrong. Consider another index only when real queries and call frequencies prove it necessary.

**Why use TEMP?** Sample data leaves existing domain tables untouched; PK/FK/UNIQUE constraints still work; and PostgreSQL plans queries on temp tables much like regular tables. `ANALYZE` is important here because temp tables are not automatically analyzed by another session's autovacuum worker like regular tables.

### 5.1. Testing Key Semantics on the Sample Data

The standalone snippet below demonstrates the rules—**do not merge these intentionally failing INSERTs into the practice script above**:

```sql
-- Rejected: customer 999 does not exist (FK violation).
INSERT INTO demo_orders (customer_id, created_at, status)
VALUES (999, NOW(), 'NEW');

-- Rejected: email already exists (UNIQUE violation).
INSERT INTO demo_customers (id, email)
VALUES (101, 'user1@example.test');
```

Both statements raise constraint errors when run in the session holding the temp tables, as expected; inside a transaction, you may need to handle or roll back after an error before running further statements. These errors concern **data integrity**, not whether the current read query uses an index well.

## 6. Reading Plans in Practice: A Six-Question Workflow

When a Spring endpoint responds slowly and time is traced to SQL, ask in order:

**1. What is the actual SQL, and what do parameters represent?** In JPA, the ORM can generate SQL different from what you picture from `findBy...` or JPQL. Check which joins appear, how many queries fire, what `WHERE` predicates actually run, and which parameter types are bound. Never log personal data or secrets carelessly.

**2. How many rows does the query need to return?** A 20-row paginated query is completely different from a report reading millions of rows. Without `LIMIT` or pagination, an index alone may not solve excessive result volume.

**3. How does the database read the data?** Inspect `Seq Scan`, `Index Scan`, and `Bitmap Heap Scan`; identify which tables are scanned and whether indexes support the key predicates.

**4. Where are predicates applied?** Distinguish `Index Cond` from `Filter`; read `Rows Removed by Filter` when present. An expensive filter discarding many rows after reading them suggests rethinking query structure or index design.

**5. Are estimates close to reality?** When `estimated rows` is low while `actual rows` is orders of magnitude higher, the planner may choose an unsuitable join or scan algorithm due to stale statistics or correlated columns. Inspect statistics, parameters, and correlated predicates rather than blindly adding indexes.

**6. Where does total cost come from?** Look at `loops` on nested loops, `BUFFERS` I/O, `Sort` / sort spills, query execution count from the app, network round trips, and object mapping volume in Java. One fast query called 1,000 times still makes an endpoint slow.

Measure on representative data under matching conditions, remembering differences across local, staging, and production environments. Single-run timings fluctuate easily with cache state, CPU load, concurrent workloads, and statistics.

## 7. Connecting to JDBC, JPA, and Spring Data

In Spring, `JdbcTemplate`, JPA `EntityManager`, or Spring Data Repositories determine **how Java sends requests**, while the DBMS still chooses the SQL execution plan for its data.

A repository reading the 20 most recent orders with Spring JDBC can be written as follows. This is **an illustrative class in an app configured with `JdbcTemplate` and a real `orders` table**, not a standalone Java program; the `orders` table here is not the practice `demo_orders` temp table.

```java
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderReadRepository {
    private final JdbcTemplate jdbc;

    public OrderReadRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<OrderView> latestForCustomer(long customerId, Instant since) {
        return jdbc.query(
                """
                SELECT id, created_at, status
                FROM orders
                WHERE customer_id = ?
                  AND created_at >= ?
                ORDER BY created_at DESC
                LIMIT 20
                """,
                (rs, rowNum) -> new OrderView(
                        rs.getLong("id"),
                        rs.getTimestamp("created_at").toInstant(),
                        rs.getString("status")
                ),
                customerId,
                Timestamp.from(since)
        );
    }

    public record OrderView(long id, Instant createdAt, String status) {}
}
```

This code uses parameter binding for both query **values**; `?` avoids concatenating input into SQL. In an appropriate PostgreSQL environment, an index `(customer_id, created_at DESC)` is a candidate to evaluate with `EXPLAIN`. No `@Repository`, `@Transactional`, or method name **forces** the database to pick an `Index Scan`.

With **Spring Data JPA**, a method like `findTop20ByCustomerIdOrderByCreatedAtDesc(...)` can generate the query, yet:

- Inspect the actual SQL and parameters, because mappings, fetches, pagination, and entity relationships affect the generated SQL.
- Never assume "the entity has a PK, so every FK query is fast." The PK on `orders.id` is a different access path from `orders.customer_id`.
- Watch for **N+1 queries** at the ORM layer: a fast SQL query invoked repeatedly while lazy-loading associations can add up to high total latency. Fetch joins, projections, or batch fetching sometimes fit better than a new index.
- When adding indexes, manage DDL via migrations (Flyway/Liquibase or your schema process); do not rely on Hibernate auto-DDL in production to create indexes arbitrarily.
- When running `EXPLAIN`, use SQL **equivalent** to what the application sends along with representative parameters; note that generic vs. custom prepared-statement plans in the DB can influence plan choice.

In architectural responsibilities: repositories/DAOs own queries; services own business rules and transaction coordination; and the database enforces PK/FK/UNIQUE constraints and chooses execution plans. **Do not replace database constraints with simple existence checks in Java**, since concurrent requests can pass application checks before writes land.

## 8. "Key" Is Not "Lock": A Brief Distinction

Similar words, different mechanisms:

- **Primary key / foreign key:** data identification and relationship rules stored in the schema and enforced by the database.
- **Row lock / table lock:** mechanisms coordinating concurrent read/write transactions, depending on statements, DBMS, and isolation levels.
- **Index:** a structure accelerating certain access paths; an index never replaces transactions or locking.

For example, `SELECT ... FOR UPDATE` in PostgreSQL can lock selected rows within a transaction to coordinate competing updates. Finding those rows via an index may locate them faster, yet **indexes and row locks are two separate concepts**. Do not assume indexes eliminate blocking, deadlocks, or write contention. Locking and isolation deserve dedicated study under transactions and concurrency.

## 9. Common Mental Traps

| Misconception | Correct Reading / Application |
| --- | --- |
| "Having a `PRIMARY KEY` makes every `WHERE` fast." | A PK supports lookups on the PK column(s); queries on other columns depend on their own indexes and plans. |
| "Having a `FOREIGN KEY` means the FK column is indexed." | In PostgreSQL, FKs do not auto-create an index on the referencing side; verify directly. |
| "More indexes are always better." | Each index consumes storage and slows writes with extra updates; avoid duplicate or unused indexes. |
| "Seeing `Seq Scan` means the query is broken." | A full table scan can be optimal for small tables or low-selectivity queries. |
| "Seeing `Index Scan` means the query is guaranteed fast." | It may still read many rows/buffers, repeat joins often, or send too much data to Java. |
| "`cost` is in milliseconds." | `cost` is an internal planner estimate unit; `actual time` is the measured time under `ANALYZE`. |
| "`EXPLAIN ANALYZE` only simulates." | It actually executes the SQL, including data writes if the statement modifies data. |
| "Just add an index on every column in `WHERE`." | Composite index column order, selectivity, operator types, and query patterns determine benefit. |
| "Query speed on H2/local proves production will be fast." | Engines, data volumes, statistics, caches, versions, locks, and real workloads differ. |

## 10. Self-Check Questions

1. Why can `PRIMARY KEY`, `UNIQUE`, and `FOREIGN KEY` not be replaced by an ordinary index?
2. If a query filters by `customer_id` and fetches the 20 newest rows by `created_at`, why can `(customer_id, created_at DESC)` be better suited than `(created_at, customer_id)`?
3. When a plan shows `Seq Scan`, what extra information do you need before concluding an index is missing?
4. In `EXPLAIN ANALYZE`, what does a discrepancy between estimated `rows=100` and `actual rows=10000 loops=5` indicate?
5. If JPA issues 100 small queries due to N+1, will a new index completely solve the problem? What should you check?
6. Why should you never run `EXPLAIN ANALYZE DELETE ...` casually on live data?

**Takeaway:** *Keys* protect data rules, *indexes* support access paths, and *execution plans* show how the database chooses to execute. In a Spring application, start from actual SQL and data, read `EXPLAIN`, inspect row counts and work performed, and only then decide whether to change the query or add an index.

### Further Reading

- PostgreSQL 17 — [Indexes](https://www.postgresql.org/docs/17/indexes.html), especially [Multicolumn Indexes](https://www.postgresql.org/docs/17/indexes-multicolumn.html).
- PostgreSQL 17 — [Constraints](https://www.postgresql.org/docs/17/ddl-constraints.html).
- PostgreSQL 17 — [Using EXPLAIN](https://www.postgresql.org/docs/17/using-explain.html).
- PostgreSQL 17 — [ANALYZE](https://www.postgresql.org/docs/17/sql-analyze.html).

