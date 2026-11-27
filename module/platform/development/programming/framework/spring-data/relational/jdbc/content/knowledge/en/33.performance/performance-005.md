# Reading Execution Plans and Designing Indexes Around Query Predicates

In **Spring Data Relational JDBC**, repository methods and SQL statements inside **@Query** are ultimately executed by the database. Speed does not depend solely on Java or Spring Data; the database must locate matching rows, join tables, sort, and return results. As data grows, a query that once ran quickly can become a bottleneck if the database has to scan too many rows or sort a large dataset.

Two primary tools for improving queries are:

- **Execution plan:** shows the steps the database intends to take, or actually took, to execute a query.
- **Index:** an auxiliary data structure that helps the database locate rows by filter predicates, join keys, or sort order without scanning an entire table.

Index design must start from actual queries: which columns appear in `WHERE`, which predicates are equality vs. range, which tables participate in joins, whether `ORDER BY`/`LIMIT` is present, and which columns the query returns. Then inspect the execution plan and re-measure on representative data.

## 1. What Is an Execution Plan?

An execution plan is the strategy the database intends to use to execute an SQL statement. Depending on the database, a plan can describe:

- How data is read: sequential/table scan, index scan, index seek, or bitmap scan.
- How tables are combined: nested loop, hash join, or merge join.
- How rows are filtered and sorted: filter, sort, aggregate, limit.
- Estimated row counts, cost, memory, and I/O.
- With execution-analysis modes, actual row counts and timing for each node.

For example, the query:

```sql
SELECT id, order_number, status, created_at
FROM purchase_order
WHERE customer_id = 42
  AND status = 'OPEN'
ORDER BY created_at DESC
LIMIT 20;
```

can be executed in two ways:

1. Scan the entire table, filter open orders for customer 42, sort by timestamp, and take the first 20 rows.
2. Use an index leading with `customer_id` and `status`, read in descending `created_at` order, and stop once 20 rows are collected.

For small tables, approach 1 can sometimes be cheaper. For large tables with selective predicates, approach 2 is usually far better. The optimizer chooses a plan based on statistics, estimated costs, and database configuration.

## 2. Using EXPLAIN to Inspect Execution Plans

Each database has its own syntax and plan presentation. Two common engines are PostgreSQL and MySQL.

### 2.1. PostgreSQL: EXPLAIN

`EXPLAIN` displays the plan PostgreSQL intends to use:

```sql
EXPLAIN
SELECT id, order_number, status, created_at
FROM purchase_order
WHERE customer_id = 42
  AND status = 'OPEN'
ORDER BY created_at DESC
LIMIT 20;
```

A basic plan typically contains:

- `cost=startup..total`: the planner's internal estimated cost units, not milliseconds.
- `rows`: the number of rows the planner estimates the node will return.
- `width`: the estimated average row size in bytes.
- Node names: such as `Seq Scan`, `Index Scan`, `Index Only Scan`, `Sort`, and `Limit`.

PostgreSQL cost is a relative unit for comparing alternatives within the same environment and configuration. Do not compare raw cost numbers directly across two different databases or treat cost as actual runtime.

### 2.2. PostgreSQL: EXPLAIN ANALYZE

`EXPLAIN ANALYZE` actually executes the SQL statement and appends runtime measurements:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, order_number, status, created_at
FROM purchase_order
WHERE customer_id = 42
  AND status = 'OPEN'
ORDER BY created_at DESC
LIMIT 20;
```

Key fields to inspect:

| Component | Meaning |
| --- | --- |
| `actual time` | Actual time of the node, usually showing startup and completion averages per loop |
| `actual rows` | Actual number of rows returned by the node per loop |
| `loops` | Number of times the node was executed |
| `Buffers: shared hit` | Number of blocks found in shared buffers |
| `Buffers: shared read` | Number of blocks read into shared buffers |
| `Rows Removed by Filter` | Number of rows discarded by the node's filter |
| `Planning Time` | Time spent planning the query |
| `Execution Time` | Execution time measured by PostgreSQL |

`EXPLAIN ANALYZE` executes the statement for real. For SELECTs, it reads data as usual; for UPDATE/DELETE/INSERT, it modifies data. Only run analysis on write statements in a safe environment, inside an intentional rollback transaction or against test data. Rolling back does not undo every external side effect such as sequence increments or trigger side effects.

### 2.3. MySQL: EXPLAIN and EXPLAIN ANALYZE

MySQL provides `EXPLAIN` to show how the optimizer plans to read tables:

```sql
EXPLAIN
SELECT id, order_number, status, created_at
FROM purchase_order
WHERE customer_id = 42
  AND status = 'OPEN'
ORDER BY created_at DESC
LIMIT 20;
```

Important columns in tabular output:

| Column | Meaning |
| --- | --- |
| `type` | Table access method, e.g., `ALL`, `range`, `ref`, `eq_ref`, `const`, `system` |
| `possible_keys` | Indexes the optimizer can consider |
| `key` | Index actually chosen |
| `key_len` | Length of the index prefix used |
| `rows` | Estimated number of rows to inspect |
| `filtered` | Estimated percentage of rows remaining after filtering |
| `Extra` | Additional info such as `Using filesort` or `Using temporary` |

MySQL 8.0.18 and later support `EXPLAIN ANALYZE` to execute the query and print actual metrics as an iterator plan:

```sql
EXPLAIN ANALYZE
SELECT id, order_number, status, created_at
FROM purchase_order
WHERE customer_id = 42
  AND status = 'OPEN'
ORDER BY created_at DESC
LIMIT 20;
```

`EXPLAIN ANALYZE` also executes the SQL statement. Apply the same safety precautions as in PostgreSQL when analyzing statements with side effects.

## 3. How to Read a Plan in Order

Plans are usually shown as trees. Child nodes feed rows upward into parent nodes. When reading, start at the root node to see the final output, then follow child nodes down to locate where most of the work happens.

Common nodes:

| Node | Meaning | What to check |
| --- | --- | --- |
| Sequential/Table Scan | Reads table rows sequentially | Table size, how many rows the filter discards |
| Index Scan/Seek | Uses an index to locate row positions | Index rows read and number of table fetches |
| Index Only Scan | Can satisfy data from the index without reading heap/table per row | PostgreSQL also depends on the visibility map; having an index does not guarantee index-only |
| Bitmap Index Scan + Bitmap Heap Scan | Finds locations via index then reads matching pages using a bitmap | Useful when many rows match, though less than the whole table |
| Filter | Filters rows after a child node returns them | Rows discarded and whether the predicate can move into an index |
| Sort | Sorts results | Row count to sort, memory, and whether an ordered index can avoid sorting |
| Nested Loop | For each outer row, looks up matching inner rows | Loop count and whether the inner side has an index |
| Hash Join | Builds a hash table from one side and probes with the other | Data size, memory, and disk spill |
| Merge Join | Merges two inputs already sorted on the join key | Sort cost or benefit from pre-ordered indexes |
| Aggregate/GroupAggregate | Groups rows or computes aggregates | Input row count and aggregation method |
| Limit | Stops once enough rows are produced | A matching index can enable early termination |

Do not judge a node by its name alone. A `Seq Scan` is not automatically bad; sequentially scanning a small table can beat an index lookup followed by scattered random table reads. Conversely, an `Index Scan` is not automatically good if it reads too many rows and hits many random pages.

### 3.1. Finding Time-Consuming Nodes

With PostgreSQL `EXPLAIN ANALYZE`:

- Compare `actual time` across nodes.
- Check `loops`; a fast node executed hundreds of thousands of times can still dominate runtime.
- Multiply rows by loops to approximate total work.
- Inspect `Buffers` to see whether the query touches many pages or reads from cache.
- Check whether sort/hash nodes spill to disk.

With MySQL, check actual timing and loop counts in the iterator plan of `EXPLAIN ANALYZE`. Tabular `EXPLAIN` output shows estimates only; do not treat its `rows` column as actual rows read.

### 3.2. Checking Mismatches Between Estimates and Actuals

A critical warning sign is estimated rows diverging widely from actual rows.

```text
Planner estimate: 100 rows
Actual result:    120,000 rows
```

The optimizer might pick a nested loop or index path assuming only 100 rows, while in reality it must process 120,000 rows. Causes can include:

- Stale or under-sampled statistics.
- Data skew, such as one status being far more common than others.
- Correlated columns where default statistics assume independence.
- Predicates using expressions/casts that the planner cannot estimate well.
- Query parameters whose distribution varies across executions.

PostgreSQL may need updated statistics via `ANALYZE` and extended statistics for correlated columns. MySQL has corresponding statistics-update mechanisms. Do not add new indexes before checking whether the planner has accurate statistics.

## 4. Start from Query Predicates, Not Entity Names

Indexes serve a specific workload. Collect frequent queries, slow queries, and business-critical queries. For each query, record:

1. Columns in `WHERE` and predicate types: equality, range, `IN`, `IS NULL`, pattern.
2. Columns used in `JOIN`.
3. Columns and directions in `ORDER BY`.
4. Whether `LIMIT`/pagination is present.
5. Columns returned in `SELECT`.
6. Execution frequency and typical returned row count.
7. Table read/write ratio.

Example query listing a customer's open orders:

```sql
SELECT id, order_number, status, created_at
FROM purchase_order
WHERE customer_id = 42
  AND status = 'OPEN'
  AND created_at >= TIMESTAMP '2026-01-01 00:00:00'
ORDER BY created_at DESC
LIMIT 20;
```

Predicates:

| Column | Role | Predicate type |
| --- | --- | --- |
| `customer_id` | Partition by customer | Equality |
| `status` | Filter status | Equality |
| `created_at` | Time bound and sort order | Range + Order |
| `id`, `order_number` | Columns to return | Projection |

Only from here should you propose an index, and then verify it with an execution plan.

## 5. B-tree Indexes for Equality, Range, and Sort

B-tree is the default index type and is commonly used for equality, range, certain prefix/ordering conditions, `ORDER BY` when index order matches, and key joins.

For example:

```sql
CREATE INDEX idx_purchase_order_customer
    ON purchase_order (customer_id);

CREATE INDEX idx_purchase_order_created
    ON purchase_order (created_at);
```

Single-column indexes fit workloads that filter on each column independently. However, if queries routinely combine multiple predicates, a composite index can be more effective.

## 6. Composite Indexes and the Leftmost Prefix Rule

A composite (multi-column) index stores keys in the declared column order. For a B-tree:

```sql
CREATE INDEX idx_order_customer_status_created
    ON purchase_order (customer_id, status, created_at);
```

This index best fits queries filtering on leading columns:

- `customer_id`.
- `customer_id` and `status`.
- `customer_id`, `status`, and a range predicate on `created_at`.

A query filtering only on `status` without `customer_id` generally cannot utilize the leading portion of the index as effectively as a query with `customer_id`. This is the leftmost prefix rule.

### 6.1. Column Order Matters

Suppose you have two queries:

```sql
-- Query A: always filters by customer and status.
SELECT id, status
FROM purchase_order
WHERE customer_id = 42
  AND status = 'OPEN';

-- Query B: searches orders by status across the entire system.
SELECT id, customer_id
FROM purchase_order
WHERE status = 'OPEN';
```

The index `(customer_id, status)` supports Query A. It is not a good fit for Query B because Query B does not constrain the leading column. Query B may need a separate index starting with `status` if it is sufficiently selective and frequent.

### 6.2. Equality Before Range Is a Useful Starting Rule

For queries with multiple equality predicates and one range predicate, a strong starting heuristic is putting equality columns first and the range column afterward:

```sql
WHERE customer_id = ?
  AND status = ?
  AND created_at >= ?
```

Suggested index:

```sql
CREATE INDEX idx_order_customer_status_created
    ON purchase_order (customer_id, status, created_at);
```

Equality columns narrow down a contiguous slice of the index; the range on the next column bounds the scan within that slice. This is an initial design rule, not a substitute for inspecting plans and workloads.

### 6.3. Do Not Mechanically Apply "Highest Cardinality Column Always Goes First"

The advice "always put the column with the most distinct values first" is not a universal rule for composite indexes. When multiple equality columns are constrained simultaneously, their relative order may matter less for a single query; serving other queries via leftmost prefixes, sort order, and data distribution are often the deciding factors.

Choose column order based on prefixes actually used by the workload, columns appearing independently, equality/range and sort positions, true selectivity, index size, and write cost.

### 6.4. Index Direction and ORDER BY

For the query:

```sql
SELECT id, created_at
FROM purchase_order
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 20;
```

An index:

```sql
CREATE INDEX idx_order_customer_created_desc
    ON purchase_order (customer_id, created_at DESC);
```

can allow the database to locate the customer's rows and read them in descending timestamp order, stopping early once 20 rows are found. B-trees can be scanned backward, but explicit direction becomes important when sorting across multiple columns with mixed directions. Always inspect the actual plan.

## 7. Covering Indexes and Index-Only Scans

A query may need more columns than those used for filtering. If the index includes both filter columns and returned columns, the database can avoid some table lookups.

PostgreSQL supports `INCLUDE` to attach payload columns to an index without making them search keys:

```sql
CREATE INDEX idx_order_customer_status_created_cover
    ON purchase_order (customer_id, status, created_at DESC)
    INCLUDE (id, order_number);
```

This index has key columns `customer_id`, `status`, `created_at` and included columns `id`, `order_number`. For queries selecting only columns present in the index, PostgreSQL can consider an `Index Only Scan`. However, index-only scans still depend on the visibility map and vacuum state; the plan may still fetch heap pages to verify visibility.

In MySQL/InnoDB, a secondary index can act as a covering index if it contains all required columns; InnoDB secondary indexes also store the primary key in leaf records. PostgreSQL's `INCLUDE` syntax is not valid in MySQL.

Covering indexes can make indexes noticeably larger. Only add returned payload columns when reduced table lookups are measurably beneficial; do not turn every index into a near-duplicate of the whole table.

## 8. Partial Indexes and Filtered Workloads

PostgreSQL supports partial indexes, indexing only rows matching a predicate:

```sql
CREATE INDEX idx_open_orders_customer_created
    ON purchase_order (customer_id, created_at DESC)
    WHERE status = 'OPEN';
```

This index is smaller than a full-table index if only a subset of rows have `status = 'OPEN'`. It fits queries that consistently include the matching predicate:

```sql
SELECT id, order_number, created_at
FROM purchase_order
WHERE status = 'OPEN'
  AND customer_id = 42
ORDER BY created_at DESC
LIMIT 20;
```

The planner uses a partial index only when it can prove the query condition implies the index predicate. With prepared statements using parameters rather than literals, that proof can depend on plan type and parameter values; test the query exactly as the application executes it.

MySQL does not have general B-tree partial indexes using PostgreSQL syntax. Generated columns/expression indexes or alternative designs may work depending on the case, but verify capabilities for your MySQL version.

## 9. Expression Indexes and Function Predicates

If a query applies a function to a column:

```sql
SELECT id, email
FROM customer
WHERE LOWER(email) = LOWER('ALICE@example.com');
```

A standard B-tree index on `email` may not directly serve `LOWER(email)`. PostgreSQL supports expression indexes:

```sql
CREATE INDEX idx_customer_lower_email
    ON customer (LOWER(email));
```

Queries must use an expression compatible with the index. Where feasible, normalizing data on the write path or choosing an appropriate type/collation can also be a good option.

Similarly, casts or arithmetic on columns can prevent regular indexes from being used as expected. Inspect plans and bind parameter types; avoid unnecessarily casting columns when you can cast the input parameter instead.

## 10. Indexes for LIKE, Text Search, and JSON

Not all string predicates are handled identically by B-trees.

### 10.1. Prefix Search and Leading Wildcards

A `LIKE 'alice%'` query can use a B-tree under compatible database/collation/operator classes.

A `LIKE '%alice%'` query usually cannot use a standard B-tree for substring matching because the match does not start at the beginning of the string. In PostgreSQL, the `pg_trgm` extension and a GIN/GiST index can suit substring search:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_customer_email_trgm
    ON customer
    USING GIN (email gin_trgm_ops);
```

Evaluate index size and insert/update performance before adopting it.

### 10.2. Full-Text Search

When requirements involve word/language search, stemming, or ranking, full-text search fits better than `LIKE '%word%'` on large tables. PostgreSQL provides `tsvector`/`tsquery` and GIN indexes; other databases have their own full-text mechanisms.

### 10.3. JSONB

PostgreSQL provides GIN indexes for JSONB:

```sql
CREATE INDEX idx_event_payload_gin
    ON event_record
    USING GIN (payload);
```

GIN can support compatible JSONB operators such as containment `@>`:

```sql
SELECT id
FROM event_record
WHERE payload @> '{"eventType":"ORDER_CONFIRMED"}';
```

If queries routinely filter on a specific scalar value via an expression:

```sql
SELECT id
FROM event_record
WHERE payload ->> 'eventType' = 'ORDER_CONFIRMED';
```

you can consider an expression index:

```sql
CREATE INDEX idx_event_type
    ON event_record ((payload ->> 'eventType'));
```

Choose between GIN and an expression B-tree based on actual query operators. A general JSONB index does not automatically optimize every JSON query expression.

## 11. Indexes for JOINs and Foreign Keys

Join queries frequently look up rows in a related table by key:

```sql
SELECT o.id, o.order_number, c.name
FROM purchase_order o
JOIN customer c ON c.id = o.customer_id
WHERE c.region = 'NORTH';
```

The primary key on `customer.id` is normally already indexed. The orders table may need an index on `purchase_order.customer_id` if queries join or filter on that column frequently enough:

```sql
CREATE INDEX idx_order_customer
    ON purchase_order (customer_id);
```

Do not assume every database automatically creates an index on referencing foreign key columns. For example, PostgreSQL automatically indexes declared primary keys and unique constraints, but does not automatically index referencing foreign key columns. InnoDB requires an index on foreign keys and may create one automatically if none exists.

Indexing foreign keys helps joins and can also help the database locate child rows when parent updates/deletes check constraints. Still, create indexes based on actual workloads and database behavior.

## 12. Choosing Index Types by Workload

Not every database offers the same index types or semantics. Common examples:

| Index type | Typical workload fit | Notes |
| --- | --- | --- |
| B-tree | Equality, range, sort, join | Default choice for most relational queries |
| Hash | Equality | PostgreSQL offers hash indexes; narrower use case than B-tree |
| GIN | JSONB, arrays, full-text, and composite data | Strong for membership/containment; write cost and size can be high |
| GiST | Spatial, range, and searches with matching operator classes | Requires selecting the right operator class |
| BRIN | Very large tables correlated with physical order, e.g., time-ordered logs | Tiny index, though many blocks may require rechecking |
| Full-text index | Word/phrase search | Syntax and capabilities vary by database |

MySQL/InnoDB typically uses B-tree for standard indexes; specialized types like `FULLTEXT` or `SPATIAL` have distinct mechanisms. Do not apply PostgreSQL GIN/GiST/BRIN syntax to MySQL or vice versa.

## 13. Selectivity and Cardinality

**Selectivity** describes the fraction of rows remaining after a filter predicate. A predicate selecting 1% of a table is far more selective than one keeping 90%.

Example for a table with one million orders:

| Predicate | Matching rows | Share |
| --- | ---: | ---: |
| `id = 123` | 1 | 0.0001% |
| `customer_id = 42` | 500 | 0.05% |
| `status = 'OPEN'` | 700,000 | 70% |

An index on `id` is very effective for single-row lookups. An index solely on `status` may be of little help if most rows are `'OPEN'`, because the database would read too many scattered rows. Still, `status` can be valuable inside a partial index for a rare status or inside a composite index such as `(customer_id, status)`.

Cardinality is the number of distinct values in a column. High cardinality often gives good discrimination, yet is not enough by itself to design indexes. Consider value distribution, query frequency, returned row counts, and composite column order.

## 14. Why Does the Optimizer Ignore an Existing Index?

Having an index does not mean the database always picks it. Common reasons:

- Table is small; a sequential scan is cheaper.
- Predicate matches a large share of the table.
- Statistics are stale or data distribution is skewed.
- Index does not lead with the columns constrained by the query.
- Query applies functions/casts differing from an expression index.
- Bind parameter data types mismatch column types.
- Leading wildcards or operators unsupported by that index type.
- Sort columns do not match index order.
- Index incurs many random heap fetches, costing more than a scan.
- Query selects too many columns/rows, making covering paths unviable.

Do not force the optimizer to use an index the moment you see a sequential scan. Examine estimates, actual rows, buffers, and the workload. Hints or disabling scan methods should only be used in controlled investigations, not as substitutes for fixing queries, statistics, or index design.

## 15. Spring Data JDBC: From Repository Method to Execution Plan

Spring Data JDBC generates SQL from derived query methods or runs SQL declared with `@Query`. The database only sees the SQL and bound parameters; Java method names do not dictate indexes.

Example derived query:

```java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    List<PurchaseOrder>
    findByCustomerIdAndStatusOrderByCreatedAtDesc(
            Long customerId,
            String status
    );
}
```

Example custom SQL:

```java
@Query("""
    SELECT id, customer_id, order_number, status, created_at
    FROM purchase_order
    WHERE customer_id = :customerId
      AND status = :status
    ORDER BY created_at DESC
    """)
List<PurchaseOrder> findRecentOrders(
        @Param("customerId") Long customerId,
        @Param("status") String status
);
```

Illustrative method names and SQL must match your application's actual properties and tables. Spring Data JDBC does not automatically create indexes from query method names. Indexes must be created in the database schema via migrations and verified via execution plans.

### 15.1. Inspecting Actual SQL

When a plan behaves unexpectedly, inspect the actual SQL sent by Spring Data JDBC:

- Enable appropriate logging for Spring JDBC/repository packages in development.
- Use a datasource proxy or SQL observation tool if you also need bound parameters.
- Check SQL generated by derived methods, especially with sorting, pagination, or projections.
- Run `EXPLAIN` with the same predicates and representative parameter types.

Do not log sensitive values such as access tokens, private emails, or personal data in production without proper data-protection policies.

### 15.2. Pageable and ORDER BY

If a query uses pagination, indexes must align with both filter predicates and sort order. For example:

```sql
SELECT id, order_number, created_at
FROM purchase_order
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 50 OFFSET 50000;
```

An index on `(customer_id, created_at DESC)` helps filter and sort, yet the database still has to walk past/discard rows before a large offset. For very deep pages, consider keyset/seek pagination using the last sort key of the previous page, if API and business requirements permit.

Counting total rows to build a `Page` can also run a separate, costly query. If the UI does not need total page counts, consider returning a `Slice` or bounding results in a way supported by your framework version.

## 16. Example Index Design from a Query

Suppose we have this table:

```sql
CREATE TABLE purchase_order (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_number VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
```

Workload query:

```sql
SELECT id, order_number, status, created_at
FROM purchase_order
WHERE customer_id = 42
  AND status = 'OPEN'
  AND created_at >= TIMESTAMP '2026-01-01 00:00:00'
ORDER BY created_at DESC
LIMIT 20;
```

### 16.1. First Step: Index by Predicates and Order

PostgreSQL:

```sql
CREATE INDEX idx_po_customer_status_created
    ON purchase_order (
        customer_id,
        status,
        created_at DESC
    );
```

The index leads with two equality columns, followed by the range/sort column. It can jump to the index range for the customer and status, then scan in chronological order.

### 16.2. Comparing Plans Before and After

Before creating the index:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, order_number, status, created_at
FROM purchase_order
WHERE customer_id = 42
  AND status = 'OPEN'
  AND created_at >= TIMESTAMP '2026-01-01 00:00:00'
ORDER BY created_at DESC
LIMIT 20;
```

Create the index in a test environment, refresh statistics if needed, and re-run the same query. Compare execution time, planning time, estimated/actual rows, buffers hit/read, sort nodes, how many index/table rows are read to return 20 rows, and added insert/update overhead from the new index.

Do not declare victory merely upon seeing `Index Scan`. If the index scan reads hundreds of thousands of tuples and filters out nearly all of them, the query can still be slow.

### 16.3. Considering a Covering Index

If the query runs very frequently and table lookups are the expensive part, PostgreSQL can test:

```sql
CREATE INDEX idx_po_customer_status_created_cover
    ON purchase_order (
        customer_id,
        status,
        created_at DESC
    )
    INCLUDE (id, order_number);
```

Keep only one of the two indexes if the covering index supersedes the earlier one and workload tests confirm the benefit. Do not keep two nearly identical indexes unless another query requires the distinction.

## 17. Indexes Have Costs: Do Not Over-Index

Every additional index introduces overhead:

- Inserts must add an entry to every relevant index.
- Updates to indexed columns may need to modify index entries.
- Deletes must mark/remove entries per the database's mechanism.
- Consumes disk, buffer cache, and backup/restore time.
- Increases vacuum/maintenance work in MVCC databases.
- Too many similar indexes complicate schema management and inflate write costs.

Redundant indexes can noticeably degrade write throughput. Before adding an index, check whether an existing index already has a matching prefix and order. Afterward, monitor index usage and write workloads.

Do not drop an index merely because it showed no usage over a short window. An index might serve an infrequent yet critical query, a constraint, or seasonal workloads. Confirm with owners and observe across full load cycles before removing it.

## 18. Creating Indexes in Migrations

Indexes are part of the database schema. Manage them with Flyway, Liquibase, or your project's migration tool rather than creating them manually in production and forgetting to record them.

Example SQL migration:

```sql
CREATE INDEX idx_po_customer_status_created
    ON purchase_order (
        customer_id,
        status,
        created_at DESC
    );
```

On large PostgreSQL tables, `CREATE INDEX CONCURRENTLY` can reduce write blocking during index builds, though it has specific restrictions and cannot run inside a transaction block. Check how your migration tool manages transactions before using it.

Before building production indexes, estimate table size and build duration, verify disk space and I/O headroom, assess lock/blocking impact, prepare a deploy/rollback plan, and test the migration on production-like data volumes.

## 19. Repeatable Query Optimization Workflow

A workflow you can apply to each slow query:

1. **Identify the query:** capture actual SQL, parameter shapes, frequency, and latency from logs/metrics.
2. **Establish a baseline:** run `EXPLAIN` and, in a safe environment, `EXPLAIN ANALYZE`.
3. **Read the plan:** look for scans, joins, sorts, estimate/actual mismatches, loops, and buffer I/O.
4. **Check statistics:** ensure statistics are fresh and reflect data distribution.
5. **Propose index/query changes:** base them on predicates, joins, sorts, projections, and selectivity.
6. **Re-measure:** run the same query with the same representative dataset/parameters after changes.
7. **Check write cost:** measure inserts/updates/deletes and index size.
8. **Test on staging:** use production-like DBMS, version, and data.
9. **Deploy migration:** follow your project's release process.
10. **Monitor production:** query latency, database load, pool wait, and index usage.

When comparing runs, execute enough iterations to smooth out cache warm-up and background load. Document whether measurements used a warm or cold cache; never compare two runs under different conditions and conclude an index is better.

## 20. Common Mistakes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Index exists yet planner chooses Seq Scan | Small table, low predicate selectivity, or stats/cost favor scan | Inspect actual rows, buffers, and table size |
| Composite index is not used | Query omits leading column or column order mismatches | Design around leftmost prefixes and workload |
| Filter is fast yet `ORDER BY` still runs a large sort | Index does not match sort order or preceding predicates mismatch | Check if composite index can include sort keys |
| Index scan is still slow | Reading too many index entries/table rows or random I/O | Check selectivity, heap fetches, and buffers |
| Estimated rows diverge wildly from actual | Stale stats, skew, or correlated columns | Update statistics; consider extended statistics |
| `LIKE` does not use B-tree | Leading wildcard or incompatible collation/operator | Use prefix search, trigram, or full-text per requirements |
| `LOWER` prevents regular index usage | Query uses an expression differing from index key | Use an expression index or normalize data |
| JSONB query slow despite GIN index | Operator/expression does not match index type | Choose an appropriate operator class or expression index |
| Insert/update slows after adding indexes | Index write amplification and storage overhead | Measure write workload and prune redundant indexes |
| `EXPLAIN ANALYZE` mutates data | Executed on a write statement | Run only in safe environments with controlled rollback |
| Spring Data query has different plan from manual SQL | Parameters, bind types, sorting, or actual SQL differ | Capture actual SQL and bound parameters from the application |
| Offset pagination grows slower | Database must traverse many rows before offset | Consider keyset pagination |

## 21. Practice Exercises

**Exercise 1 — Reading a basic plan.** Create a `purchase_order` table with at least several hundred thousand rows. Run a query filtering on `customer_id`, inspect `EXPLAIN`, and identify the scan node, estimated row count, and sort.

**Exercise 2 — Comparing estimates and actuals.** Run `EXPLAIN ANALYZE` on PostgreSQL. Record estimated rows, actual rows, loops, and buffers. Explain which node processes the most rows.

**Exercise 3 — Composite indexes.** Create index `(customer_id, status, created_at)`. Compare a query using all three columns against one filtering only on `status`; explain leftmost prefix.

**Exercise 4 — Equality and range.** Write a query with two equality predicates and one range predicate. Test two composite index column orders in a test database and compare plans on the same data.

**Exercise 5 — ORDER BY/LIMIT.** Create an index matching customer filter and descending creation time. Verify whether the plan eliminates sorting and stops early for a small page.

**Exercise 6 — Covering indexes.** On PostgreSQL, try `INCLUDE` for projection columns. Observe `Index Only Scan`, heap fetches, and index size.

**Exercise 7 — Partial and expression indexes.** Create a partial index for `OPEN` orders and an expression index for `LOWER(email)`. Confirm corresponding queries can use them.

**Exercise 8 — JSONB and LIKE.** Compare B-tree with GIN/trigram on two different queries: JSONB containment and substring search. Document which operators each index supports.

**Exercise 9 — Spring Data JDBC.** Write both a derived query and an `@Query` for the same use case. Capture actual SQL, run `EXPLAIN`, and compare plans.

**Exercise 10 — Measuring write overhead.** Measure insert/update latency before and after adding several indexes. Weigh read gains against write costs and storage.

**Exercise 11 — Deep pagination.** Compare `LIMIT/OFFSET` at small and large offsets. Test seek/keyset pagination on a deterministic sort key pair and explain the difference.

**Exercise 12 — Index migrations.** Write a migration creating an index for a chosen query. Run it on a test database, confirm the post-migration plan, and verify the rollback procedure.

### References

- [PostgreSQL — Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): how to read plans, estimated/actual rows, costs, and buffers.
- [PostgreSQL — Indexes](https://www.postgresql.org/docs/current/indexes.html): overview of indexes, index types, and planner usage.
- [PostgreSQL — Multicolumn Indexes](https://www.postgresql.org/docs/current/indexes-multicolumn.html): rules for multi-column indexes.
- [PostgreSQL — Index Types](https://www.postgresql.org/docs/current/indexes-types.html): B-tree, Hash, GiST, SP-GiST, GIN, and BRIN.
- [PostgreSQL — Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html): expression indexes.
- [PostgreSQL — Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html): predicate-based indexes.
- [MySQL — EXPLAIN Output](https://dev.mysql.com/doc/refman/8.4/en/explain-output.html): fields in MySQL plans.
- [MySQL — EXPLAIN ANALYZE](https://dev.mysql.com/doc/refman/8.4/en/explain.html): iterator plan analysis with execution metrics.
- [Spring Data Relational Reference](https://docs.spring.io/spring-data/relational/reference/): repository queries and mapping in Spring Data JDBC.
