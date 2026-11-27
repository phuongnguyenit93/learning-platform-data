# Nested-Loop, Hash Join, and Version Changes

## Lesson objectives

After this lesson, you will be able to:

- Describe how Nested-Loop Join (NLJ) feeds rows one by one from the outer table to the inner table.
- Explain why an index on the join column makes NLJ efficient.
- Recognize the limits of nested loop when the inner table must be scanned repeatedly.
- Distinguish historical Block Nested-Loop (BNL), Batched Key Access (BKA), and Hash Join.
- Describe the build and probe phases of hash join, along with join buffer memory limits.
- Read EXPLAIN FORMAT=TREE and EXPLAIN ANALYZE to identify join algorithms.
- Understand key changes from MySQL 8.0.18, 8.0.19, and 8.0.20 through MySQL 8.4.
- Control join algorithms at session scope or via optimizer hints when testing.
- Choose optimizations based on row counts, indexes, join order, memory, and execution metrics.

When JOINing two tables, MySQL needs an algorithm to match rows satisfying the join condition. Two central algorithms in modern MySQL are Nested-Loop Join and Hash Join.

Nested loop reads a row from the outer table and then finds matching rows in the inner table. If the inner table has an index on the join column, each iteration becomes a fast index lookup. Without an index, scanning the inner table again for every outer row causes cost to skyrocket.

Hash join addresses a different set of cases: MySQL reads one input to build a hash table on the join key, then reads the other input and probes the hash table. This algorithm is especially useful when no suitable index exists on the join condition and many rows must be matched. Hash join first appeared in MySQL 8.0.18; starting in 8.0.20, it replaced Block Nested-Loop in the cases where BNL was previously used.

## 1. Join algorithm and join order

A JOIN query involves two related yet distinct decisions:

- Join order: which table is read first, and which is read next.
- Join algorithm: which method MySQL uses to match rows between tables.

Example:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.total_amount
FROM customer AS c
JOIN sales_order AS o
    ON o.customer_id = c.customer_id
WHERE c.region_code = 'NORTH';
~~~

The optimizer can choose customer as the outer input and sales_order as the inner input, or reverse the order if cost estimates indicate another order is cheaper.

Join order affects how many rows pass into the next step. If the WHERE clause narrows customer from one million rows down to 20 rows, reading customer first dramatically reduces lookups on the inner table. If the outer input is huge, NLJ can execute a vast number of loops.

Do not infer the algorithm solely from JOIN syntax. MySQL picks a plan based on statistics, indexes, filter conditions, data sizes, and estimated costs.

## 2. How does Nested-Loop Join work?

Nested-Loop Join (NLJ) matches rows using nested loops. MySQL reads a row from the outer table and uses it to process the inner table. This repeats until the outer table is exhausted.

With two tables, the conceptual model is:

~~~text
for each row in outer_table:
    for each matching row in inner_table:
        output joined row
~~~

With three tables, loops nest deeper:

~~~text
for each row in t1:
    for each matching row in t2:
        for each matching row in t3:
            output joined row
~~~

Each table in an inner loop can be accessed many times. This is why join order and indexes on inner tables are critical.

### 2.1. NLJ combined with index lookup

Suppose customer has primary key customer_id and sales_order has an index on customer_id.

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.total_amount
FROM customer AS c
JOIN sales_order AS o
    ON o.customer_id = c.customer_id
WHERE c.customer_id = 101;
~~~

MySQL can perform:

1. Use PRIMARY KEY to look up customer 101.
2. Use the index on sales_order.customer_id to look up that customer's orders.
3. Return the joined rows.

Because only one customer is selected, the number of lookups on the orders table is tiny. This is the classic efficient NLJ pattern: the outer table is tightly filtered and the inner table has an index supporting the join condition.

### 2.2. NLJ cost grows when the outer input is large

Suppose the outer table emits 50,000 rows and each row must probe the inner table. Even if each probe is an index lookup, MySQL still executes many lookups. If each probe must scan an entire 2-million-row inner table, the workload becomes extraordinarily expensive.

You can approximate the cost mentally:

- With a suitable index: outer loop count multiplied by index lookup cost and matching rows.
- Without an index, scanning the inner table each time: outer rows multiplied by inner rows.

This is only a mental model for reasoning, not MySQL's full cost formula. Buffer pool caching, pages already in memory, filter predicates, row widths, and other optimizations all affect real cost.

### 2.3. Reading NLJ in EXPLAIN TREE

On MySQL versions supporting TREE format:

~~~sql
EXPLAIN FORMAT=TREE
SELECT
    c.customer_id,
    o.order_id
FROM customer AS c
JOIN sales_order AS o
    ON o.customer_id = c.customer_id
WHERE c.customer_id = 101;
~~~

A nested-loop plan may be presented as:

~~~text
-> Nested loop inner join
    -> Single-row index lookup on c using PRIMARY
    -> Index lookup on o using idx_order_customer
       (customer_id = c.customer_id)
~~~

Exact iterator names and details vary by version, statistics, and schema. Recognize the structure: one input is read first, then an inner iterator is invoked for those input rows.

### 2.4. NLJ without an index on the inner table

If the inner table lacks a suitable index, naive NLJ would have to scan the inner table for each row of the outer table. This is a situation requiring investigation.

In older versions, Block Nested-Loop could use a join buffer to batch multiple rows from the outer loop, reducing inner table scans. Since MySQL 8.0.20, BNL has been removed; hash join is used in cases BNL previously handled.

## 3. Block Nested-Loop is a historical algorithm

Block Nested-Loop (BNL) extended nested loop by buffering multiple rows from outer loops in a join buffer. When the buffer filled, MySQL scanned the inner table once and compared each inner row against all outer row combinations held in the buffer.

Simplified model:

~~~text
read a batch of outer rows into join buffer

for each row in inner_table:
    compare it with each outer row in the buffer
    output matching combinations

repeat with the next batch
~~~

If one batch held 100 outer rows, a single scan of the inner table could match against all 100 rows at once. BNL thus reduced inner table scans compared to unindexed naive NLJ.

However, BNL is no longer used as a join algorithm as of MySQL 8.0.20. Understanding BNL remains important for version history and because the names of its control flags were retained.

### 3.1. Why does the name block_nested_loop still exist?

The `block_nested_loop` flag in `optimizer_switch` and the `BNL`/`NO_BNL` hints were retained. Starting in MySQL 8.0.20, they control hash join usage rather than meaning the server still runs the legacy BNL algorithm.

This is a common source of confusion when reading old configurations or documentation. When working with MySQL 8.4, treat `block_nested_loop` as the flag controlling hash join.

## 4. How does Hash Join work?

Hash join generally consists of two phases:

1. Build: read one input and build a hash table keyed on the join columns or expression.
2. Probe: read the remaining input, hash each row's join key, and probe the hash table for matching rows.

Example joining on customer_id:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.total_amount
FROM customer AS c
JOIN sales_order AS o
    ON o.customer_id = c.customer_id;
~~~

If no usable index exists for the join condition, MySQL can select hash join:

- Read one table and build a hash table on customer_id.
- Read the other table.
- For each row, compute the hash of customer_id and find rows with matching keys.
- Verify join predicates and return matching rows.

The optimizer picks build and probe inputs based on plan shape, estimated sizes, and cost. Never assume the left-hand table in the SQL text is always the build table.

### 4.1. Illustrating build and probe

~~~text
Input A                         Input B
customer_id, customer_name      customer_id, order_id
        |                               |
        v                               v
  Build hash table                 Probe hash table
  key = customer_id                key = customer_id
        |                               |
        +------------+------------------+
                     |
                     v
              Matching rows
                     |
                     v
                Join result
~~~

Hash join avoids repeatedly scanning the entire inner table for every outer row like unindexed NLJ. It still must read the inputs and process matches; if many rows share identical keys, output row counts can still be enormous.

### 4.2. When is hash join suitable?

Hash join is typically suitable when:

- The join condition has equality predicates (equi-join).
- No usable index exists for the join condition.
- Both inputs have many rows to match by key.
- Scanning inputs and building a hash table costs less than executing numerous index lookups.

Hash join can also appear when indexes exist only for single-table filter conditions, yet no index supports the join predicate linking the two tables.

If one input filters down to just a few rows and the other table has a matching index on the join column, NLJ with index lookup is usually more competitive.

Starting in MySQL 8.0.20, hash join is also used in cases where BNL previously applied even without equality join conditions, including inner non-equi joins, semijoins, antijoins, and outer joins. Hash join can also be used for Cartesian products when a query has no join condition. Thus hash join's scope in modern versions is broader than the basic equi-join example above.

### 4.3. Hash join does not eliminate data-reading cost

Hash join still must read data from its inputs. If tables are very large and memory cannot hold the hash table, MySQL uses disk files to process the overflow.

Moreover, hash join does not shrink the output row count of a many-to-many relationship. If a customer_id appears 1,000 times in table A and 2,000 times in table B, joining on that key can generate up to 2 million row combinations for that single key.

Check cardinality, join conditions, and output row counts before blaming the join algorithm as the sole cause of a slow query.

## 5. Hash join and join_buffer_size memory

The `join_buffer_size` system variable limits the memory a hash join can use. If a hash join requires more memory than that limit, MySQL handles the excess data using on-disk files.

Check current settings:

~~~sql
SELECT
    @@GLOBAL.join_buffer_size AS global_join_buffer_size,
    @@SESSION.join_buffer_size AS session_join_buffer_size,
    @@GLOBAL.open_files_limit AS open_files_limit;
~~~

Values are in bytes. Do not increase `join_buffer_size` just because you spot a hash join. Verify whether the hash join is spilling to disk, check I/O wait times, and account for concurrent queries before tuning.

### 5.1. Hash join spilling to disk

When memory is insufficient, hash join uses temporary files. This can increase I/O and execution time. The number of files a hash join can open is also bounded by `open_files_limit`.

The MySQL Reference Manual notes two options when a hash join needs more files than allowed:

- Increase `join_buffer_size` to reduce or avoid spilling.
- Increase `open_files_limit` if needed files exceed the limit.

These are server-level configuration changes requiring measurement and resource planning. Never apply them directly to production based on a single query.

### 5.2. Join buffer is allocated incrementally

The hash join buffer is allocated incrementally as needed. This keeps small queries from immediately consuming the entire `join_buffer_size` allocation. However, outer joins can allocate the full buffer.

If you raise the limit too high, many concurrent queries can drive total memory consumption up dramatically. Account for concurrency, the number of joins per query, and server RAM limits.

## 6. BKA: a nested-loop variant with batched keys

Batched Key Access (BKA) is a join algorithm that uses index access on the joined table combined with a join buffer to batch key lookups.

Instead of sending keys one by one to the storage engine, BKA collects a batch of keys and uses Multi-Range Read (MRR) to fetch rows more efficiently. It remains an index-lookup-based strategy, unlike hash join which builds a hash table.

BKA can help when the inner table has a suitable index yet numerous individual lookups cause unfavorable random access patterns. BKA supports inner joins, outer joins, and semijoins where supported by the optimizer.

### 6.1. BKA is off by default

In MySQL 8.4:

- `batched_key_access` defaults to off.
- For BKA to take effect, `mrr` must be enabled.
- Because MRR cost estimation can be overly pessimistic, the documentation requires `mrr_cost_based=off` for BKA to be chosen.

Session test configuration:

The example below uses the two lab tables from section 9. After creating the data and adding index `idx_order_customer` in section 9.3, you can test BKA on that join query:

~~~sql
SET @saved_optimizer_switch = @@SESSION.optimizer_switch;

SET SESSION optimizer_switch =
    'batched_key_access=on,mrr=on,mrr_cost_based=off';

EXPLAIN FORMAT=TREE
SELECT
    c.customer_id,
    o.order_id
FROM customer_demo AS c
JOIN order_demo AS o
    ON o.customer_id = c.customer_id;

SET SESSION optimizer_switch = @saved_optimizer_switch;
~~~

This setting is strictly for session-level experimentation. The optimizer still decides whether to use BKA based on query conditions and cost. Re-check EXPLAIN after enabling it; never assume flipping the flag guarantees BKA appears.

### 6.2. Distinguishing BKA and hash join

| Criterion | BKA | Hash join |
|---|---|---|
| Core mechanism | Nested-loop with batched index lookups | Build hash table then probe |
| Requires index on probed table | Yes | No index required on join condition in typical cases |
| Uses join buffer | Yes | Yes |
| MRR | Used to batch accesses | Not a core requirement |
| Suitable conditions | Index exists and lookups benefit from batching | Many rows, no suitable join index |
| Main configuration | batched_key_access, mrr | block_nested_loop |

Do not treat BKA as a drop-in replacement for hash join in all cases. Choosing the right algorithm depends on indexes and data patterns.

## 7. Algorithm changes across MySQL versions

Version history matters because the exact same SQL statement can produce a different plan after upgrading MySQL.

| Version | Relevant changes |
|---|---|
| Before 8.0.18 | Hash join not supported; MySQL used nested-loop and the BNL variant where applicable |
| 8.0.18 | Hash join introduced for equi-joins lacking usable join indexes; `hash_join` flag and `HASH_JOIN`/`NO_HASH_JOIN` hints existed in this release |
| 8.0.19 | `hash_join` and `HASH_JOIN`/`NO_HASH_JOIN` hints no longer have effect; `block_nested_loop` and `BNL`/`NO_BNL` hints control hash join |
| 8.0.20 | BNL removed; hash join replaced cases formerly using BNL, expanding to additional join types and conditions |
| 8.4 | Hash join used by default where applicable; `block_nested_loop` and `BNL`/`NO_BNL` control hash join; BKA remains a separate option |

### 7.1. 8.0.18: hash join arrives

Starting in MySQL 8.0.18, hash join was used for queries where each join has an equi-join condition and no usable index exists for the join condition.

Example:

~~~sql
SELECT *
FROM t1
JOIN t2
    ON t1.c1 = t2.c1;
~~~

If neither table has a suitable index on c1, hash join may be chosen. You can identify it via EXPLAIN FORMAT=TREE or EXPLAIN ANALYZE.

### 7.2. 8.0.19: control mechanism changes

In 8.0.18, you could use:

~~~sql
SET SESSION optimizer_switch = 'hash_join=off';
~~~

or the HASH_JOIN and NO_HASH_JOIN hints.

Starting in 8.0.19, those options stopped having any effect. Use:

~~~sql
SET SESSION optimizer_switch = 'block_nested_loop=off';
~~~

or the `NO_BNL` hint to disable hash join for the specified scope.

### 7.3. 8.0.20: BNL removed

Starting in MySQL 8.0.20, BNL is no longer used by the server. Hash join is used in scenarios where BNL would previously have been chosen, including inner non-equi joins, semijoins, antijoins, left outer joins, and right outer joins. Hash join can also apply to Cartesian products when no join condition exists.

Therefore, when reading documentation or logs from MySQL 5.7, 8.0.17, and newer releases, never assume the same `Using join buffer` text always means the same algorithm.

### 7.4. MySQL 8.4: block_nested_loop no longer means BNL

In MySQL 8.4, `block_nested_loop` is the flag controlling hash join. Variable and hint names were kept for backward compatibility and historical reasons.

Check:

~~~sql
SELECT
    @@version AS mysql_version,
    @@SESSION.optimizer_switch AS optimizer_switch;
~~~

You may still see `hash_join` listed in some MySQL 8.4 `optimizer_switch` outputs, but that flag has no effect. Use `block_nested_loop` to control hash join.

## 8. Reading join plans with EXPLAIN

### 8.1. EXPLAIN FORMAT=TREE

TREE format shows iterators and parent-child plan relationships. It is the clearest way to distinguish nested loop from hash join.

Hash join example:

~~~sql
EXPLAIN FORMAT=TREE
SELECT *
FROM customer_demo AS c
JOIN order_demo AS o
    ON o.customer_id = c.customer_id;
~~~

The plan might look like:

~~~text
-> Inner hash join (o.customer_id = c.customer_id)
    -> Table scan on o
    -> Hash
        -> Table scan on c
~~~

Nested loop example:

~~~text
-> Nested loop inner join
    -> Index lookup on c using PRIMARY
    -> Index lookup on o using idx_order_customer
       (customer_id = c.customer_id)
~~~

These are illustrative shapes. Iterator names, build/probe order, and costs vary by version and data.

### 8.2. Tabular EXPLAIN

In traditional format, hash join can be recognized in the Extra column:

~~~text
Using where; Using join buffer (hash join)
~~~

Tables participating in a hash join often show `type = ALL` because MySQL scans inputs to build or probe the hash table. That does not automatically mean a bad plan; evaluate total cost and data volume.

### 8.3. EXPLAIN ANALYZE

EXPLAIN ANALYZE executes the SELECT statement and displays actual row counts, loop counts, and iterator timings.

~~~sql
EXPLAIN ANALYZE
SELECT
    c.customer_id,
    o.order_id
FROM customer_demo AS c
JOIN order_demo AS o
    ON o.customer_id = c.customer_id
WHERE c.region_code = 'NORTH';
~~~

When reading results, pay attention to:

- Which iterator builds the hash table.
- Which iterator scans the probe input.
- Actual row counts of each input.
- Loop counts in nested loops.
- Gaps between estimated and actual rows.
- Timing of individual iterators and overall query time.

EXPLAIN ANALYZE actually runs the query. Use datasets and predicates with acceptable execution cost.

## 9. Hands-on lab: comparing hash join and nested loop

This lab uses two standalone tables without foreign keys so we can control join indexes. Initially there is no index on `order_demo.customer_id`, and then we add one to observe the plan change.

### 9.1. Creating tables and loading data

~~~sql
CREATE TABLE customer_demo (
    customer_id BIGINT UNSIGNED NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    region_code VARCHAR(20) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

CREATE TABLE order_demo (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;

INSERT INTO customer_demo (
    customer_id, customer_name, region_code
)
VALUES
    (101, 'Nguyen An', 'NORTH'),
    (102, 'Tran Binh', 'SOUTH'),
    (103, 'Le Chi', 'NORTH'),
    (104, 'Pham Dung', 'CENTRAL');

INSERT INTO order_demo (
    order_id, customer_id, total_amount, created_at
)
VALUES
    (5001, 101, 1250000.00, '2026-02-01 09:15:00'),
    (5002, 101, 2400000.00, '2026-02-03 11:30:00'),
    (5003, 102,  890000.00, '2026-02-08 14:00:00'),
    (5004, 103, 3400000.00, '2026-02-15 16:45:00'),
    (5005, 101,  450000.00, '2026-02-18 10:20:00'),
    (5006, 104, 5100000.00, '2026-03-02 08:10:00'),
    (5007, 102,  760000.00, '2026-03-05 13:25:00'),
    (5008, 103, 1750000.00, '2026-03-10 17:05:00');
~~~

### 9.2. Observing hash join without a join index

~~~sql
EXPLAIN FORMAT=TREE
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.total_amount
FROM customer_demo AS c
JOIN order_demo AS o
    ON o.customer_id = c.customer_id
WHERE c.region_code = 'NORTH';
~~~

Without an index on `order_demo.customer_id`, there is no suitable index lookup for the join condition. On MySQL 8.0.18 and later, hash join may be chosen.

The expected plan shows an Inner hash join with table scans. Because the sample data is tiny, cost estimates and server version can affect the exact plan; read the actual output rather than expecting one fixed output string.

### 9.3. Adding an index to the inner table

~~~sql
CREATE INDEX idx_order_customer
ON order_demo (customer_id);
~~~

Run a query selecting a single customer:

~~~sql
EXPLAIN FORMAT=TREE
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.total_amount
FROM customer_demo AS c
JOIN order_demo AS o
    ON o.customer_id = c.customer_id
WHERE c.customer_id = 101;
~~~

The index on `order_demo.customer_id` enables MySQL to use nested loop with an index lookup on the inner table. Because the filter selects only one customer, the lookup count is small.

### 9.4. Comparing timing and row counts

~~~sql
EXPLAIN ANALYZE
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.total_amount
FROM customer_demo AS c
JOIN order_demo AS o
    ON o.customer_id = c.customer_id
WHERE c.customer_id = 101;
~~~

Compare with the hash join query in section 9.2. The sample dataset is too small to draw general performance conclusions. Scale up rows in a test environment while preserving business results and measure under identical load conditions.

### 9.5. Testing disabling hash join in the session

You can save current settings and disable hash join to observe the fallback plan on small data:

~~~sql
ALTER TABLE order_demo
DROP INDEX idx_order_customer;

SET @saved_optimizer_switch = @@SESSION.optimizer_switch;

SET SESSION optimizer_switch = 'block_nested_loop=off';

EXPLAIN FORMAT=TREE
SELECT
    c.customer_id,
    o.order_id
FROM customer_demo AS c
JOIN order_demo AS o
    ON o.customer_id = c.customer_id;

SET SESSION optimizer_switch = @saved_optimizer_switch;

CREATE INDEX idx_order_customer
ON order_demo (customer_id);
~~~

Disabling hash join does not magically make MySQL invent an index lookup. Without a matching index, the fallback plan may resort to nested loop with repeated inner table scans, which is catastrophic on large data.

Only perform this experiment on small data or an isolated environment. Always restore `optimizer_switch` afterward.

## 10. Choosing algorithms based on workload

| Scenario | Likely suitable algorithm | Reason |
|---|---|---|
| Outer table filtered to few rows, inner table has join index | NLJ with index lookup | Each outer row only needs a selective lookup |
| Both inputs large, no suitable join index, equality condition | Hash join | Scanning inputs and probing hash beats repeated full scans |
| Join index exists yet many key lookups need batching | BKA may be worth testing | Key batching with MRR improves inner table access patterns |
| Join produces massive duplicate key matches | Check cardinality first | Result explosion can bottleneck regardless of join algorithm |
| Hash table exceeds join_buffer_size | Hash join can spill to disk | Extra disk I/O increases execution time |
| Small tables or data cached in memory | Several plans may have similar cost | Measure on representative data |

No single algorithm is best for every query. A join query may fly with NLJ when indexes are selective and stall if the outer input spikes. Hash join can shine when join indexes are absent, yet remains constrained by memory and input read volume.

## 11. Common mistakes when diagnosing joins

| Misconception | Reality | How to handle |
|---|---|---|
| Every JOIN is a nested loop | MySQL can choose hash join or NLJ variants | Use EXPLAIN TREE |
| Hash join is always faster than NLJ | NLJ with index lookups can be far faster for small outer inputs | Check join order, indexes, and row counts |
| Having any index prevents hash join | An index must apply to the join condition; single-table filter indexes may still exist | Verify which index supports the join condition |
| block_nested_loop=on means the server uses BNL | From 8.0.20, this flag controls hash join | Interpret according to MySQL version |
| hash_join=off disables hash join in 8.4 | The `hash_join` flag has no effect in 8.4 | Use `block_nested_loop=off` or `NO_BNL` |
| Using join buffer always means BNL | It can mean hash join in newer versions | Read the exact parenthetical (`hash join`) and TREE plan |
| Increasing join_buffer_size always helps | Hash joins and other join buffers can consume much more RAM | Check spilling, concurrency, and I/O |
| EXPLAIN ANALYZE only estimates | It actually executes the SELECT | Use on queries with acceptable cost |
| Disabling hash join forces an index lookup | Without an index, NLJ falls back to repeated inner table scans | Create or evaluate a suitable index first |
| BKA and hash join are the same | BKA is batched index lookup; hash join uses a hash table | Distinguish `batched_key_access` and `block_nested_loop` |

## 12. Workflow for optimizing a JOIN query

When a JOIN query is slow, follow this sequence:

1. Identify the tables, join predicates, and filter predicates.
2. Check indexes on join columns, especially on inner tables if NLJ is chosen.
3. Run EXPLAIN FORMAT=TREE to see whether NLJ or hash join is used.
4. Read join order and estimated rows at each input.
5. Run EXPLAIN ANALYZE to compare actual rows, loops, and timings.
6. Check whether hash join spills to disk or NLJ executes excessive lookups.
7. Verify whether the join condition causes an unexpected many-to-many explosion.
8. Test adding an index or rewriting the query in a test environment.
9. If needed, test BKA or toggle `block_nested_loop` at session scope.
10. Restore settings after testing and re-measure on representative data.

Reference diagram:

~~~mermaid
flowchart TD
    A[Slow JOIN query] --> B[EXPLAIN FORMAT=TREE]
    B --> C{Algorithm in use?}
    C -->|Nested loop| D[Check outer row count and inner index]
    C -->|Hash join| E[Check size of both inputs and join buffer]
    D --> F{Is lookup selective?}
    F -->|No| G[Evaluate indexes and join order]
    F -->|Yes| H[Measure loops and actual time]
    E --> I{Spilling or huge inputs?}
    I -->|Yes| J[Check I/O, join_buffer_size, and open_files_limit]
    I -->|No| H
    G --> K[Test a change]
    J --> K
    H --> K
    K --> L[EXPLAIN ANALYZE and compare]
~~~

## 13. Practice exercises

### Exercise 1: Sketching nested loop

Use the `customer` and `sales_order` tables. Sketch the outer loop and inner loop for a JOIN on `customer_id`. Identify which table is outer and which is inner in the actual plan.

### Exercise 2: Evaluating an inner table index

Run the JOIN query when `order_demo` has no `customer_id` index. Add the index and run EXPLAIN TREE. Explain the change in iterators.

### Exercise 3: Comparing NLJ and hash join

Run the same query on larger data with and without a join index. Record row counts, loops, and timings using EXPLAIN ANALYZE.

### Exercise 4: Join order

Write a query with filter conditions on both tables. Compare plans when the outer filter is more selective versus when data distributions shift.

### Exercise 5: Hash join memory

Keep the query constant and test different `join_buffer_size` values in an isolated environment. Observe timing and I/O signs when hash join handles large data.

### Exercise 6: Testing spill

Generate data larger than the hash table can hold in test memory. Measure timing when hash join must use disk files. Note the `open_files_limit` setting.

### Exercise 7: BKA

Add an index on the inner table, enable `batched_key_access`, `mrr`, and `mrr_cost_based` as shown. Run EXPLAIN and determine whether the optimizer chooses BKA.

### Exercise 8: Testing disabling hash join

Save `optimizer_switch`, turn off `block_nested_loop` in the session, and run EXPLAIN on a query without a join index. Compare plans and restore original settings.

### Exercise 9: Comparing versions

Read MySQL 8.0.18, 8.0.19, 8.0.20, and 8.4 documentation. Build a table explaining changes across `hash_join`, `block_nested_loop`, BNL, and BKA.

### Exercise 10: Analyzing a slow query

Pick a JOIN query with high runtime. Identify algorithm, join order, indexes, estimated rows, actual rows, loops, and memory footprint. Propose one change and prove it with measurements.

## Conclusion

Nested-Loop Join reads rows from an outer table and finds matching rows in an inner table. When the inner table has an index and the outer input is small, NLJ can be highly efficient. When no suitable join index exists and many rows must be matched, hash join is often the better option because it builds a hash table and probes the remaining input.

In MySQL 8.0.18, hash join was introduced; 8.0.19 changed how it is controlled; 8.0.20 removed BNL and expanded the cases hash join replaces. In MySQL 8.4, `block_nested_loop` and `BNL`/`NO_BNL` control hash join, while BKA remains a separate batched index-lookup strategy.

Use EXPLAIN TREE to identify iterators, EXPLAIN ANALYZE to measure row counts and loops, and evaluate indexes, join order, and memory together. The join algorithm is only part of the cost; cardinality and output row volume still dictate most of the work a query must perform.

## References

- MySQL 8.4 Reference Manual — Nested-Loop Join Algorithms: https://dev.mysql.com/doc/refman/8.4/en/nested-loop-joins.html
- MySQL 8.4 Reference Manual — Hash Join Optimization: https://dev.mysql.com/doc/refman/8.4/en/hash-joins.html
- MySQL 8.4 Reference Manual — Block Nested-Loop and Batched Key Access Joins: https://dev.mysql.com/doc/refman/8.4/en/bnl-bka-optimization.html
- MySQL 8.4 Reference Manual — Switchable Optimizations: https://dev.mysql.com/doc/refman/8.4/en/switchable-optimizations.html
- MySQL 8.4 Reference Manual — Optimizer Hints: https://dev.mysql.com/doc/refman/8.4/en/optimizer-hints.html
- MySQL 8.4 Reference Manual — Server System Variables (join_buffer_size, open_files_limit): https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html
- MySQL 8.0 Reference Manual — What Is New in MySQL 8.0: https://dev.mysql.com/doc/refman/8.0/en/mysql-nutshell.html
