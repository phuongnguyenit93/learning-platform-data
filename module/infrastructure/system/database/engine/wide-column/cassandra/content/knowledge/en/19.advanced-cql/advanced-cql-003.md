# Aggregate Functions, GROUP BY, and Query Semantic Limitations

## 1. Objectives and the Right Mindset for Cassandra

In relational databases, a query like `SELECT status, SUM(amount) FROM orders GROUP BY status` is routine. In **Apache Cassandra**, CQL also provides aggregate functions such as `COUNT`, `MIN`, `MAX`, `SUM`, `AVG` and a `GROUP BY` clause, yet **it does not offer the same arbitrary grouping capabilities as SQL in a relational DBMS**.

Cassandra is a **distributed wide-column** database designed for efficient reads and writes by **partition key**, storing rows sorted by **clustering key**. Consequently, aggregation capabilities must be understood alongside:

- **Partition key:** determines where data partitions live across replicas.
- **Clustering columns:** determine the order of rows within a partition and form the basis for grouping along a primary key prefix.
- **Replication and consistency level:** affect how the coordinator reads from replicas and the confirmation level of the result.
- **Data scanning cost:** Cassandra does not automatically maintain arbitrary counts and sums for every possible query.

After this lesson, you will be able to use CQL aggregate functions, write valid `GROUP BY` queries over primary keys, recognize the limitations of `WHERE`, `HAVING`, and `ORDER BY`, evaluate multi-row scan costs, and design query-driven tables when a Java application needs frequent statistics.

## 2. What Do CQL Aggregate Functions Do?

An **aggregate function** takes values from multiple rows in a result set and produces a single summary value. Common built-in functions include:

| Function | Meaning | CQL Example | Notes |
| --- | --- | --- | --- |
| `COUNT(*)` | Counts the rows visible to the query. | `COUNT(*)` | Must scan the relevant data; not a precomputed count stored in table metadata. |
| `COUNT(column)` | Counts non-`null` values of the column. | `COUNT(total_amount)` | May differ from `COUNT(*)` if a regular column is missing/unset. |
| `MIN(column)` | Smallest value in the set of valid values. | `MIN(total_amount)` | Does not mean picking "the row with the earliest date" if applied to another column. |
| `MAX(column)` | Largest value in the set of valid values. | `MAX(total_amount)` | Does not automatically return the rest of the row holding the maximum value. |
| `SUM(column)` | Sum of numeric values. | `SUM(total_amount)` | Depends on data type and the set of scanned rows. |
| `AVG(column)` | Average of numeric values. | `AVG(total_amount)` | Data type/precision affects the displayed result. |

These aggregates normally skip `null` input column values (except `COUNT(*)`, which counts rows). `COUNT(*)` counts **logical rows currently visible at read time**, not every physical record in SSTables: expired TTL data, tombstones, and replica-reconciled data can cause the count to differ from historical entries on disk.

Without `GROUP BY`, an aggregate query returns **a single summary result for the matching rows**:

~~~sql
SELECT COUNT(*) AS order_count,
       SUM(total_amount) AS gross_amount,
       MIN(total_amount) AS smallest_order,
       MAX(total_amount) AS largest_order,
       AVG(total_amount) AS average_order
FROM orders_lab.orders_by_store_day
WHERE store_id = 'store-A';
~~~

The query above will be run after creating the table and loading data in section 3. Aliases like `AS order_count` and `AS gross_amount` let the Java driver read results by meaningful names.

> **Remember:** CQL aggregates are computed over data the query must read. Do not assume `COUNT(*)` is an instant `O(1)` count, especially when scanning a large partition or the entire table.

## 3. Hands-On Dataset: Grouping Orders by Day for a Store

Suppose an e-commerce system needs to answer: **"Each day, how many orders did store A receive and what is the total amount?"**.

For this example, create a keyspace using `NetworkTopologyStrategy`. Replace `dc1` with your **actual data center name**, and ensure the lab has enough replicas to satisfy RF = 3 if using `LOCAL_QUORUM`.

~~~sql
CREATE KEYSPACE IF NOT EXISTS orders_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

CREATE TABLE IF NOT EXISTS orders_lab.orders_by_store_day (
  store_id text,
  order_day date,
  order_id uuid,
  order_status text,
  total_amount decimal,
  PRIMARY KEY ((store_id), order_day, order_id)
) WITH CLUSTERING ORDER BY (order_day DESC, order_id ASC);
~~~

Meaning of the primary key:

- **`store_id` is the partition key:** all orders for the same store in this example reside in one partition.
- **`order_day` is the first clustering column:** rows in the partition are ordered by day, making daily grouping convenient.
- **`order_id` is the second clustering column:** distinguishes orders on the same day.
- **`order_status` and `total_amount` are regular columns:** `total_amount` can be used in `SUM`, but `order_status` does not automatically become a grouping key.

This is a **small practice table** to illustrate syntax; production usually requires **bucketing** (e.g., `(store_id, month_bucket)`) to prevent a partition from growing unboundedly over years.

Load five orders, including a `CANCELLED` order on the 20th:

~~~sql
INSERT INTO orders_lab.orders_by_store_day
  (store_id, order_day, order_id, order_status, total_amount)
VALUES ('store-A', '2026-11-20',
        00000000-0000-4000-8000-000000000001, 'PAID', 100.50);

INSERT INTO orders_lab.orders_by_store_day
  (store_id, order_day, order_id, order_status, total_amount)
VALUES ('store-A', '2026-11-20',
        00000000-0000-4000-8000-000000000002, 'PAID', 50.00);

INSERT INTO orders_lab.orders_by_store_day
  (store_id, order_day, order_id, order_status, total_amount)
VALUES ('store-A', '2026-11-20',
        00000000-0000-4000-8000-000000000003, 'CANCELLED', 75.00);

INSERT INTO orders_lab.orders_by_store_day
  (store_id, order_day, order_id, order_status, total_amount)
VALUES ('store-A', '2026-11-21',
        00000000-0000-4000-8000-000000000004, 'PAID', 200.00);

INSERT INTO orders_lab.orders_by_store_day
  (store_id, order_day, order_id, order_status, total_amount)
VALUES ('store-A', '2026-11-21',
        00000000-0000-4000-8000-000000000005, 'PAID', 25.00);
~~~

In a lab with no concurrent writes or TTLs, the expected calculations are:

| Day | Order Count | Total `total_amount` | Notes |
| --- | ---: | ---: | --- |
| `2026-11-20` | 3 | 225.50 | Includes one `CANCELLED` order. |
| `2026-11-21` | 2 | 225.00 | Two `PAID` orders. |
| **Entire partition** | **5** | **450.50** | Belongs only to `store-A`. |

These numbers reflect **all orders**; they **do not automatically mean "paid revenue"** just because the column is named `total_amount`. If you need to filter by status, you must design an appropriate query path.

## 4. Using `GROUP BY` Properly: Grouping by Primary Key Prefix

Query aggregating orders by day:

~~~sql
SELECT store_id,
       order_day,
       COUNT(*) AS order_count,
       SUM(total_amount) AS gross_amount,
       MIN(total_amount) AS min_amount,
       MAX(total_amount) AS max_amount
FROM orders_lab.orders_by_store_day
WHERE store_id = 'store-A'
GROUP BY store_id, order_day;
~~~

With the dataset above, there are **two groups**: `(store-A, 2026-11-20)` and `(store-A, 2026-11-21)`. Because `store_id` is bound by equality `=`, Cassandra can group by `order_day` within the targeted partition. The example query lists the grouping columns in exact primary key order for readability.

### Why Key Order Matters

Suppose the primary key is:

~~~text
PRIMARY KEY ((store_id), order_day, order_id)
             partition    clustering  clustering
~~~

Valid grouping keys must be **primary key columns in declaration order**, subject to rules allowing columns already equality-bound in `WHERE` to be omitted. For example:

| Query Pattern | Interpretation |
| --- | --- |
| `WHERE store_id = 'store-A' GROUP BY store_id` | Aggregates into one group for the store's partition. |
| `WHERE store_id = 'store-A' GROUP BY store_id, order_day` | Aggregates by day within the partition. |
| `WHERE store_id = 'store-A' GROUP BY store_id, order_day, order_id` | Each order has its own key, typically leaving one row per group. |
| `GROUP BY order_status` | **Invalid:** `order_status` is not part of the primary key. |
| `GROUP BY order_day, store_id` | **Invalid key order:** reverses the order of the key columns. |

This is where Cassandra differs from SQL: Cassandra cannot automatically gather `order_status` values across all partitions into arbitrary groups and sort them by largest sum like a general-purpose analytical database.

### Diagram of a Grouped Query Path

~~~mermaid
flowchart TD
    Q["SELECT ... WHERE store_id = 'store-A'"] --> P["Partition key locates partition and replicas"]
    P --> C["Coordinator reads rows in clustering key order"]
    C --> G["GROUP BY store_id, order_day"]
    G --> A1["2026-11-20: COUNT=3, SUM=225.50"]
    G --> A2["2026-11-21: COUNT=2, SUM=225.00"]
    A1 --> R["Returns aggregated rows"]
    A2 --> R
~~~

**No index or permanent summary table is automatically created** by `GROUP BY`. The next time the query runs, the system still has to read the underlying data. The diagram shows the logical flow; how many replica nodes participate in the read depends on the consistency level.

## 5. Semantic Limits: How Cassandra's `GROUP BY` Differs from SQL

### 5.1. Cannot Group Arbitrarily by a Regular Column

A query SQL users often reach for:

~~~sql
-- INVALID on the example table in Cassandra:
SELECT order_status, COUNT(*)
FROM orders_lab.orders_by_store_day
GROUP BY order_status;
~~~

`order_status` is just a regular column and **cannot be used as a grouping key**. Adding `ALLOW FILTERING` does not turn a regular column into a clustering key and does not relax `GROUP BY` rules.

If the business frequently asks "count orders by status for a store," you need **another table whose primary key directly serves that query**, or a separate pre-aggregated summary table. For instance, you could place `order_status` before `order_day` in the clustering prefix if the read pattern truly requires grouping by status.

### 5.2. `WHERE` Must Align with Partition/Clustering Keys

The query:

~~~sql
-- Not an efficient query path on the current schema:
SELECT COUNT(*)
FROM orders_lab.orders_by_store_day
WHERE order_status = 'PAID';
~~~

has no partition key predicate, and `order_status` is not a key capable of routing the query under the schema above. Cassandra normally rejects queries requiring unsupported filtering or requires a dedicated index/query path; **do not add `ALLOW FILTERING` just to force a table into acting as a cluster-wide statistics engine**.

Even with an index, you must separately evaluate cardinality, selectivity, data distribution, and `GROUP BY` constraints. An index does not turn every `GROUP BY` query into arbitrary SQL-style grouping.

### 5.3. No SQL-Style `HAVING` or Arbitrary Sorting by Aggregates

CQL does not provide `HAVING SUM(total_amount) > ...` to filter groups like SQL, nor does it support `ORDER BY SUM(total_amount) DESC` as free sorting on aggregate results:

~~~sql
-- SQL concept, NOT valid CQL:
SELECT order_day, SUM(total_amount) AS gross
FROM orders_lab.orders_by_store_day
WHERE store_id = 'store-A'
GROUP BY store_id, order_day
HAVING SUM(total_amount) > 200
ORDER BY gross DESC;
~~~

For small result sets, the application can filter and sort **after retrieving the groups**. For large datasets and high-traffic dashboards, store a **pre-aggregated table** keyed for that view, or use an appropriate analytical engine.

CQL's `ORDER BY`, when used, is constrained by **clustering columns** and partition key predicates; it is not SQL's arbitrary-column or arbitrary-aggregate `ORDER BY`.

### 5.4. Be Careful Selecting Columns Outside the Grouping Key

Cassandra allows certain `SELECT` queries to return additional columns that are neither grouped nor aggregated. In that case, the unaggregated value comes from **one representative row in the group** per how the query processes rows, **not a property of the whole group**.

For example, `SELECT order_day, order_status, COUNT(*) ... GROUP BY store_id, order_day` could display `order_status = 'PAID'` alongside a group containing both `PAID` and `CANCELLED` orders. Interpreting that status label as "every order in the group is PAID" would be wrong. Therefore, only `SELECT` **grouping key columns** and **aggregate expressions** when reporting meaningful group summaries.

If you need "the most common status," "which customer placed the largest order," or "fields from the row with `MAX`," design another query or table; `MAX` returns the maximum value, not the entire row containing it.

### 5.5. `LIMIT` Does Not Make a Large Aggregation Cheap

With `GROUP BY`, `LIMIT` caps the number of **grouped result rows** returned. It **does not create pre-maintained statistics**, nor does it guarantee constant-cost computation behind each group. `PER PARTITION LIMIT` has per-partition/group limiting semantics depending on query structure.

Example:

~~~sql
SELECT order_day, COUNT(*) AS order_count
FROM orders_lab.orders_by_store_day
WHERE store_id = 'store-A'
GROUP BY store_id, order_day
LIMIT 7;
~~~

The query only requests up to seven day groups, yet if each day contains millions of orders, **the rows within those groups still have to be processed** to count accurately.

### 5.6. Do Not Treat Aggregates as a Global Transactional Snapshot

Cassandra reads through coordinator/replicas according to the consistency level. `LOCAL_QUORUM` increases the required local replica responses, but **does not turn multiple partitions into a consistent transactional snapshot like an MVCC SQL engine**. While the query executes, concurrent writes, TTLs, timestamps, tombstones, lagging replicas, or unrepaired data can affect what is observed.

Therefore, numbers from `COUNT(*)` or `SUM` should be understood as **CQL read results at a specific consistency level**, not automatically as a transactionally locked financial ledger.

## 6. Distributed Cost and Consistency Level Choices

With `WHERE store_id = 'store-A'`, the partition key lets Cassandra pinpoint the replica set holding that partition. The node handling the request acts as **coordinator**, follows a read path matching the consistency level, fetches data, and computes/returns the aggregate result. Reading across many partitions widens the work and can involve many replica sets.

| Query | Data Scope to Process | Assessment |
| --- | --- | --- |
| `COUNT(*) WHERE store_id = ?` | Relevant rows in one store's partition | Acceptable for small partitions, but not inherently instant. |
| `GROUP BY store_id, order_day WHERE store_id = ?` | Rows in the partition grouped by clustering key | Good for illustration and controlled use when partitions are moderate. |
| `COUNT(*)` without `WHERE` | May have to scan data across many partitions/nodes | High risk of latency spikes, timeouts, and cluster load. |
| Group all stores by a regular column | Unsupported as ad-hoc SQL on this table | Needs a query-driven/pre-aggregated table or analytics engine. |

If a partition holds too many rows, an aggregate scan puts pressure on disk, CPU, network, memory, coordinator, and request timeouts. It also incurs read costs from SSTables, tombstones, and replica reconciliation. **Compaction** manages local SSTables; **repair** synchronizes data across replicas. Neither mechanism **turns `COUNT(*)` into a precomputed metric**.

With `LOCAL_QUORUM` and RF = 3 in the local DC, a read requires **two appropriate replica responses**; `LOCAL_ONE` requires only one response and may observe older data. Aggregate queries are subject to these exact same consistency trade-offs as any other read query.

## 7. Designing for Real Analytical Queries

### 7.1. Keep Groups Small Using Partition Keys and Buckets

If daily reporting per store is needed, avoid storing a store's entire multi-year history in one unbounded partition. One option is bucketing by **month**:

~~~sql
CREATE TABLE IF NOT EXISTS orders_lab.orders_by_store_month (
  store_id text,
  month_bucket text,
  order_day date,
  order_id uuid,
  order_status text,
  total_amount decimal,
  PRIMARY KEY ((store_id, month_bucket), order_day, order_id)
) WITH CLUSTERING ORDER BY (order_day DESC, order_id ASC);
~~~

A monthly query targets only the `(store_id, month_bucket)` partition:

~~~sql
SELECT store_id, month_bucket, order_day,
       COUNT(*) AS order_count,
       SUM(total_amount) AS gross_amount
FROM orders_lab.orders_by_store_month
WHERE store_id = 'store-A'
  AND month_bucket = '2026-11'
GROUP BY store_id, month_bucket, order_day;
~~~

Here, both partition key columns are equality-bound with `=`; `order_day` is the next clustering prefix. For full-year stats, the application can query each monthly bucket and combine results rather than relying on a single query scanning every partition like general-purpose SQL.

If the application only cares about `PAID` orders, you can maintain a separate table containing only paid orders or a table with `order_status` placed in the key to match the query. Changing the primary key is a **data modeling decision**, because it affects writes, distribution, partition sizing, and valid queries.

### 7.2. Pre-Aggregation for High-Traffic Dashboards

If a dashboard frequently displays daily "paid order count" and "paid revenue" at high volume, a precomputed summary table is usually a better fit:

~~~sql
CREATE TABLE IF NOT EXISTS orders_lab.paid_revenue_by_store_day (
  store_id text,
  order_day date,
  paid_order_count bigint,
  paid_amount decimal,
  calculated_at timestamp,
  PRIMARY KEY ((store_id), order_day)
) WITH CLUSTERING ORDER BY (order_day DESC);

SELECT order_day, paid_order_count, paid_amount
FROM orders_lab.paid_revenue_by_store_day
WHERE store_id = 'store-A';
~~~

This table is updated by **the application, periodic jobs, or event-processing pipelines** with computed figures; `SELECT` reads the daily metrics directly without rescanning every order. In return, you must design update workflows for newly created orders, cancellations, refunds, status transitions, and event replays.

Never use an unguarded "read current total -> add amount -> overwrite" sequence under concurrent workers: that causes **lost updates**. Cassandra offers the `counter` type for certain counting scenarios, yet counter increments have specific retry/idempotency properties and do not solve `decimal` sums or financial reconciliation. For strict accuracy, design deduplication, event sourcing, checkpoint/reconciliation, and an appropriate consistency strategy.

### 7.3. When to Use a Dedicated Analytics Engine

Questions like "Top 100 stores by revenue across all regions," "GROUP BY `order_status` with `HAVING`," "JOIN orders with customers," multi-dimensional time analysis, or very long-range reporting should generally be offloaded to an analytics/OLAP pipeline. Cassandra serves as **the operational store for key-based transactional queries**, while the pipeline aggregates data for ad-hoc reporting.

## 8. Connecting from Java and Reading Aggregate Values

With **Apache Cassandra Java Driver 4.x**, the application can prepare a query scoped by partition key and set the consistency level on the statement. The example below uses the table created in section 3:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.math.BigDecimal;
import java.net.InetSocketAddress;
import java.time.LocalDate;

public class DailyOrderSummary {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement prepared = session.prepare(
                    "SELECT order_day, COUNT(*) AS order_count, " +
                    "SUM(total_amount) AS gross_amount " +
                    "FROM orders_lab.orders_by_store_day " +
                    "WHERE store_id = ? " +
                    "GROUP BY store_id, order_day");

            BoundStatement statement = prepared.bind("store-A")
                    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

            ResultSet result = session.execute(statement);
            for (Row row : result) {
                LocalDate day = row.getLocalDate("order_day");
                long count = row.getLong("order_count");
                BigDecimal gross = row.getBigDecimal("gross_amount");
                System.out.printf("%s: %d orders, gross %s%n",
                        day, count, gross);
            }
        }
    }
}
~~~

Key takeaways:

1. `WHERE store_id = ?` lets the driver and coordinator route by **partition key**; binding via a prepared statement safely passes values and reuses the CQL execution plan.
2. `LOCAL_QUORUM` enforces quorum reads across replicas in the local data center, **without creating a cluster-wide transactional snapshot**.
3. Aliases `AS order_count` and `AS gross_amount` become the result column names used by `Row`; `SUM(decimal)` is retrieved as `BigDecimal`.
4. `127.0.0.1` and `dc1` are for lab testing only; real applications must configure contact points, local DC, TLS/authentication, and timeouts matching the actual topology.
5. This example reads a small dataset. If a query must scan millions of orders, switch to a pre-aggregated table or an analytics workflow instead of merely raising timeouts.

## 9. Common Reasoning Mistakes

| Claim | Assessment | Correct Understanding |
| --- | --- | --- |
| "Cassandra has `GROUP BY`, so it can group by any column." | **False** | Grouping columns are constrained by the primary key and key order, accounting for equality-bound columns. |
| "`COUNT(*)` reads from metadata, so huge tables still count instantaneously." | **False** | It must read the matching rows; very expensive over large scans. |
| "`MIN(amount)` returns the entire smallest order row." | **False** | It only returns the minimum aggregated value, not the other columns of that row automatically. |
| "`LIMIT 10` guarantees aggregation only reads 10 source rows." | **False** | With `GROUP BY`, the number of returned groups is capped, yet work inside each group can still be large. |
| "`LOCAL_QUORUM` makes `SUM` a globally exact transactional report at all times." | **False** | CL governs replica responses; it does not provide a global snapshot. |
| "You can use `HAVING` to keep revenue groups above a threshold." | **False** | CQL does not support SQL-style `HAVING`; filter elsewhere or use a query-specific table. |
| "Pre-aggregated tables need their own maintenance mechanism." | **True** | You must handle inserts, updates, cancellations, event replays, and reconciliation. |

## 10. Self-Check Exercises

**Exercise 1.** On `orders_by_store_day`, write a query to count total orders for `store-A` without breaking down by day.

~~~sql
SELECT COUNT(*) AS total_orders
FROM orders_lab.orders_by_store_day
WHERE store_id = 'store-A';
~~~

If the data matches section 3 with no changes, the result is `5`.

**Exercise 2.** Why is `GROUP BY order_status` invalid even though the table has an `order_status` column?

**Answer:** `order_status` is a regular column, not part of the primary key. Cassandra does not support arbitrary grouping on regular columns like SQL. You need a query-driven table or a pre-aggregated summary table.

**Exercise 3.** A `GROUP BY store_id, order_day` query returns a row showing `order_status = 'PAID'` for the 20th. Can you conclude all orders on the 20th are `PAID`?

**Answer:** **No.** The ungrouped/unaggregated `order_status` value simply comes from one representative row; the 20th group also contains a `CANCELLED` order.

**Exercise 4.** A company wants daily order counts across 3,000 stores, each having millions of orders. Is running `COUNT(*) GROUP BY order_day` directly across the whole table every time a dashboard opens appropriate?

**Answer:** Unsuitable in most cases. The query would scan massive amounts of data and easily cause overload/timeouts. Design proper partitions and buckets, maintain pre-aggregated summary tables keyed by query, or offload to an analytics engine.

**Exercise 5.** A system has RF = 3 in `dc1`. If you use `LOCAL_ONE` instead of `LOCAL_QUORUM` for a `SUM` query, will the results always be identical?

**Answer:** There is no such guarantee when replicas experience update lag or repair is in progress. `LOCAL_ONE` contacts one replica; `LOCAL_QUORUM` requires two responses. Different read consistency levels can observe different results while data has not converged.

## 11. Decision Flow Before Writing an Aggregate Query

~~~mermaid
flowchart TD
    A["Need COUNT / SUM / AVG / MIN / MAX?"] --> B{"Does the query specify the partition key?"}
    B -->|Yes| C{"Does GROUP BY only use a primary key prefix?"}
    B -->|No| D["Revisit the data model or analytics pipeline"]
    C -->|Yes| E{"Is the scanned row count small and bounded?"}
    C -->|No| F["Design a query-specific or pre-aggregated table"]
    E -->|Yes| G["Can use CQL aggregate and measure real latency"]
    E -->|No| F
    D --> H["Do not use periodic full scans for large dashboards"]
    F --> I["Maintain results and reconcile when data changes"]
~~~

**Takeaway:** `COUNT`, `SUM`, `AVG`, `MIN`, and `MAX` are valid CQL aggregates; `GROUP BY` only groups along a **primary key** structure that Cassandra can traverse. Query-driven table design and bounded partition sizes determine real-world performance. Whenever SQL-style filtering, sorting, or multi-dimensional grouping is required, choose a pre-aggregated table or an analytics system built for that purpose.
