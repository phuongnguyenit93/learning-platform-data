# Gathering Queries, Filter Conditions, Read Ordering, and Result Limits

## Lesson Objectives

In Apache Cassandra, **the data model begins with the queries that the application needs to execute**. Before choosing a partition key, clustering columns, or writing `CREATE TABLE`, the designer must clarify what data users want to read, under what conditions, in what order, and how many records to retrieve. This is the first step of query-driven design for a distributed wide-column database.

After this lesson, you will be able to:

- Translate a business or API requirement into an implementable and testable **query contract**.
- Distinguish between conditions that identify a partition, conditions that restrict rows within a partition, and filter conditions on regular attributes.
- Precisely document sort order, tie-breaking rules, `LIMIT`, pagination, time ranges, and the cost of multi-partition queries.
- Use a query inventory to guide **partition key**, **clustering column**, and denormalized per-read-path table design; recognize early which requirements do not fit Cassandra's efficient read paths.

## 1. Why Gather Queries Before Creating Tables?

With relational databases, development teams typically normalize entities and then join, filter, and sort as needed. Cassandra is optimized for routing queries to specific partitions via a **partition key**, then reading rows organized by **clustering columns** within each partition. It does not provide arbitrary `JOIN` capabilities or global sorting across all partitions like a traditional relational database management system.

Therefore, asking "what fields does an order have?" is not enough to design the schema. You need to ask specifically:

> "A customer views their 20 most recent orders within a month, newest first, and can load the next page"

This requirement immediately suggests three design dimensions:

1. **Query entry point:** which customer, belonging to which tenant, in which month → components that can form the partition key.
2. **Read order:** order creation time descending → clustering columns and sort direction.
3. **Query bounds:** at most 20 orders per view → `LIMIT` and pagination strategy; if viewing across multiple months is required, rules for reading multiple partitions must be defined.

There is no single "one-size-fits-all" Cassandra table that efficiently serves every arbitrary filter. You may need multiple tables storing intentional copies of the same data, such as `orders_by_customer_month`, `orders_by_id`, and `orders_by_tenant_status_day`. The application must maintain consistency across those representations when data changes.

## 2. Template for Gathering a Query

For each read action, record one row in the **query inventory** and a detailed contract. At a minimum, include the following information:

| Component | Questions to Ask | Example: Order History |
| --- | --- | --- |
| Purpose and caller | Who reads it, and in which feature? | Customer views order history via API |
| Returned data | Which columns are actually needed? | `order_id`, `created_at`, `status`, `total_amount` |
| Mandatory conditions | Which values are always present on the call? | `tenant_id`, `customer_id`, `month_bucket` |
| Optional conditions | Are there filters the user can toggle on/off? | `created_at` range; **no** default `status` filter |
| Operators | Equality, range, list, or prefix comparison? | Equality on partition key, range on `created_at` |
| Ordering | Which column(s) and direction? | `created_at DESC`, tie-broken by `order_id DESC` |
| Limit and pagination | How many per fetch, and how is the next page loaded? | 20 rows, business cap 100; driver paging/cursor |
| Scope | Single partition or multiple partitions? | One customer, one month; spanning months requires multiple reads |
| Load and skew | Average/peak QPS? Which tenants are oversized? | Measure per customer and per tenant |
| Freshness and consistency | Is stale data acceptable? | Specify order status visibility requirements and read/write consistency levels |
| Data lifecycle | How long is it retained, and how do updates/deletes occur? | Retain 24 months; order status can change |

The numbers in the example are **illustrative assumptions**, not Cassandra defaults. Before locking the design, replace them with measured production data or product commitments.

A query contract should use a format that is easy to cross-reference against APIs and CQL:

```text
ID: Q01
Use case: Customer views orders within a single month
Required inputs: tenantId, customerId, month (UTC, YYYY-MM)
Optional inputs: fromInclusive, toExclusive, pageToken
Filter: tenantId = ?, customerId = ?, monthBucket = ?;
        createdAt >= ? and createdAt < ? if a time range is provided
Sort: createdAt DESC, orderId DESC
Output: orderId, createdAt, status, totalAmount
Page: 20 records; business cap 100 records/request
Scope: exactly one customer/month partition
Other: from date A to B across multiple months -> rule to read each month separately
```

The key point is to **separate mandatory filters from optional filters**. An API that allows `status` or `minAmount` to vary freely can produce multiple distinct query shapes, and each shape must be evaluated individually.

## 3. Classifying Filter Conditions in Cassandra

A `WHERE` clause in CQL does not mean Cassandra can use every column to locate data efficiently. When documenting conditions, divide them into three groups.

### 3.1. Partition-Identifying Conditions

The **partition key** determines where data resides in the cluster. With a composite partition key such as `(tenant_id, customer_id, month_bucket)`, queries typically need concrete values for **all** components to target a single partition:

```sql
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
```

If only `tenant_id` is known without `customer_id` or `month_bucket`, a query against this table is no longer a direct single-partition read. Do not assume Cassandra will quickly find all orders for a tenant by scanning the table.

Ask further during requirements gathering:

- Does the caller **always** have all partition key components?
- Are there "all customers" or "all months" queries? If so, do you need a different read path or to fan out into multiple queries?
- Does the partition risk growing very large or becoming a hotspot when a high-traffic customer/tenant is active?

### 3.2. Conditions on Clustering Columns

Within each partition, **clustering columns** determine the logical storage order of rows. For example, `(created_at, order_id)` enables reading by time and uses `order_id` to establish a deterministic position when multiple orders share the same creation timestamp.

Conditions on clustering columns must align with the **column order in the key**: typically equality conditions on a prefix, followed by range conditions on an eligible column. You cannot arbitrarily skip a preceding clustering column and expect the query to remain optimal. Exact rules depend on the CQL operator types and Cassandra version; always verify actual queries against the chosen schema.

An example matching the table defined later:

```sql
AND created_at >= ?
AND created_at < ?
```

A **half-open** range (`[from, to)`) avoids double-counting records when splitting contiguous time windows. A consistent timezone, such as UTC, must be agreed upon for computing `month_bucket` and both boundary timestamps.

### 3.3. Conditions on Regular Columns

Columns such as `status`, `total_amount`, or `customer_name` may be only **regular columns** in a table. Cassandra does not inherently maintain an efficient access path for filtering on them.

For instance, "all `PAID` orders today for a tenant" is **different** from "a customer's 20 most recent orders." If `status` is a mandatory condition of the first query, you may need a table with `status` in the partition key rather than adding `WHERE status = ?` to the customer history table.

`ALLOW FILTERING` may allow some queries to execute, but it **does not turn post-read filtering into an access path with predictable cost**. Use it only after thoroughly understanding read volume, partition sizes, and operational limits; never treat it as a fix for a data model.

Secondary indexes or Storage-Attached Indexes (SAI, if supported by your version/deployment) are also options to evaluate based on query and data characteristics. They do not replace clearly specifying the partition key, selectivity, read order, and latency requirements.

## 4. Capturing Exact Read Ordering

"Most recent orders" is not specific enough. You must ask:

- Is "most recent" based on `created_at`, `updated_at`, or completion time?
- Ascending or descending? Does the direction ever need to be reversed?
- When two rows have the same timestamp, which column breaks the tie? Is a stable, repeatable order across pages required?
- Must sorting occur **within a single partition** or **across multiple partitions**?

In Cassandra, `CLUSTERING ORDER BY` in the table definition sets the default order inside a partition. CQL `ORDER BY` queries are constrained by the partition key and clustering columns; you cannot request arbitrary global sorting by a regular column as in SQL.

For example, a table storing orders by customer/month with clustering `created_at DESC, order_id DESC` naturally serves "newest first." However, it does **not** automatically serve "sort all orders across the entire tenant by `total_amount DESC`"; that requirement must be entered into the query inventory as an independent query.

If a screen displays aggregated results from multiple months or multiple partitions, the application must decide **the merge order across result streams**, the maximum number of partitions to read, and how to resume on the next page. Cassandra does not automatically guarantee a global order when the application merges multiple reads.

## 5. Distinguishing `LIMIT`, Page Size, and Cost Bounds

These three concepts are not interchangeable:

| Concept | Effect | What It Does **Not** Guarantee |
| --- | --- | --- |
| `LIMIT n` in CQL | Limits the number of rows returned by the query | Does not guarantee reading only `n` rows at the storage layer, especially with tombstones/filtering |
| Driver `page size` | Controls the target number of rows per result page fetched on each paging round-trip | Not a business rule meaning "the user can view at most `n` rows" |
| API-level limits | Caps payload size, time-range width, or partition count per request | Does not automatically optimize CQL if the partition key or filters are unsuitable |

Example:

```sql
SELECT order_id, created_at, status, total_amount
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
LIMIT 20;
```

If the application needs to paginate across multiple requests, use the Cassandra driver's paging mechanism and manage the **paging state** safely. Paging state is opaque data tied to the query and its bound parameters; do not modify it, do not reuse it across different queries, and do not assume a sequence of pages represents a consistent snapshot under concurrent writes. Do not design SQL-style `OFFSET` pagination for CQL.

For UI patterns like "view first 20 orders" or "load more," clarify whether `LIMIT 20` is a **total row cap** for the query or whether the product wants **20 rows per page across multiple pages**. If multiple pages are needed, `LIMIT` and paging must be designed together; a query capped with `LIMIT 20` will not arbitrarily yield a second page of 20 different rows from the same result set.

Beyond row counts, you must bound **the number of partitions touched**, **time-window width**, and **record size**. Reading 20 rows past a large accumulation of tombstones, or querying the 20 newest rows across hundreds of partitions, can still consume heavy resources and degrade latency.

## 6. End-to-End Example: Multi-Tenant Order System

Suppose a Java service uses Cassandra to store orders. The following table is the query inventory gathered from product requirements; frequencies and response-time targets must be measured and filled in before production rollout.

| ID | Read Need | Input Conditions | Order and Limits | Design Direction |
| --- | --- | --- | --- | --- |
| Q01 | View one customer's orders in one month | `tenant_id =`, `customer_id =`, `month_bucket =`; optional time range | Newest first, 20 rows/page | `orders_by_customer_month` |
| Q02 | View details of one order | `tenant_id =`, `order_id =` | At most one order | `orders_by_id` |
| Q03 | Staff views orders by status on a given day | `tenant_id =`, `status =`, `day_bucket =` | Newest first, 50 rows/page | `orders_by_tenant_status_day` |
| Q04 | View 50 most recent orders across three months | `tenant_id =`, `customer_id =`, three target months | Screen-wide order, max 50 | Read monthly partitions, merge and limit in application |
| Q05 | Search orders by keyword, arbitrary amount filters, sort by amount across tenant | Arbitrary filters | Global sort and pagination | Separate analytical requirement; may need an additional access model or dedicated search engine |

Do not merge Q01–Q05 into a single `SELECT` with numerous optional filters. What they share is the "order" domain data; their **read paths** are distinct.

### 6.1. Table Design for Q01: History by Customer/Month

```sql
CREATE TABLE orders_by_customer_month (
    tenant_id text,
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_amount decimal,
    PRIMARY KEY ((tenant_id, customer_id, month_bucket), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);
```

Here:

- `(tenant_id, customer_id, month_bucket)` is the **composite partition key**. One customer in one month corresponds to one logical partition.
- `(created_at, order_id)` is the **clustering key**. Rows are organized in descending time order, using ID to break ties when timestamps match.
- `status` and `total_amount` are display columns, **not** flexible filter keys for Q01.

Query Q01 with a time range within the requested month:

```sql
SELECT order_id, created_at, status, total_amount
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
  AND created_at >= ?
  AND created_at < ?
LIMIT 20;
```

The `?` placeholders are bind markers for a Java application **prepared statement**. When running directly in `cqlsh`, replace them with valid CQL literals. If no time-range filter is supplied, use a separate prepared statement without the two `created_at` conditions; do not dynamically concatenate arbitrary conditions into an uncontrolled query.

Decisions to confirm with product:

- Can users query arbitrarily across multiple months? If so, what is the maximum number of months and how are results merged?
- How many orders/month does a very large customer generate? If partitions grow too large, use a finer bucket (such as day) or a measured sharding strategy.
- When an order's status changes, which table representations need the `status` column updated?

### 6.2. Table Design for Q02: Single-Order Lookup

```sql
CREATE TABLE orders_by_id (
    tenant_id text,
    order_id uuid,
    customer_id uuid,
    created_at timestamp,
    status text,
    total_amount decimal,
    PRIMARY KEY ((tenant_id, order_id))
);

SELECT customer_id, created_at, status, total_amount
FROM orders_by_id
WHERE tenant_id = ? AND order_id = ?;
```

The detail query has the full partition key and requires no sorting. It is not a query pattern that should be forced onto the customer history table if the API does not always have `customer_id` and `month_bucket`.

### 6.3. Table Design for Q03: List by Status/Day

```sql
CREATE TABLE orders_by_tenant_status_day (
    tenant_id text,
    status text,
    day_bucket date,
    created_at timestamp,
    order_id uuid,
    customer_id uuid,
    total_amount decimal,
    PRIMARY KEY ((tenant_id, status, day_bucket), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);

SELECT order_id, customer_id, created_at, total_amount
FROM orders_by_tenant_status_day
WHERE tenant_id = ?
  AND status = ?
  AND day_bucket = ?
LIMIT 50;
```

`status` is part of the partition key **in the Q03 table** because it is a mandatory filter for this screen. Conversely, in Q01, `status` is merely a display attribute. That is why the same attribute can play different roles across query-specific tables.

Two operational considerations to note:

1. A tenant with too many orders in the same status/day can create a large or hot partition. Before deployment, estimate row counts and bytes per partition at peak hours; consider smaller buckets or controlled sharding if metrics require it.
2. When an order transitions from `PENDING` to `PAID`, the system must update the lookup-by-ID table, the history table, and **delete the row from the old status partition while writing a row to the new status partition**. Optimizing for easy reads typically trades off multi-table synchronization responsibility on the write path; clearly define error handling, retries, and reconciliation mechanisms.

### 6.4. Q04: Multi-Partition Reads Are Not a Single Globally Ordered Read

Suppose users want the "50 most recent orders across three months." With the Q01 table, you can read the three corresponding `month_bucket` partitions, fetch the already-sorted data from each partition, and merge them by `(created_at DESC, order_id DESC)` in the service. The design must specify the maximum number of months, the strategy for fetching more rows when one month runs out, total row caps, and how per-partition pagination state is tracked.

Do not assume adding `IN` over multiple partition key values plus an `ORDER BY` will cheaply produce a globally ordered list. As fan-out grows, API load and latency increase as well. If cross-month reading is a dominant query, re-evaluate the bucket granularity or introduce a dedicated serving table.

## 7. Questions to Resolve Before Finalizing Keys

### 7.1. Partition Size and Hotness

Suppose a customer places 2,000 orders/day and each row stores an average of roughly 1 KiB of business data. A 30-day bucket corresponds to **approximately 60,000 rows and 59 MiB of raw data** (excluding storage overhead, indexes, tombstones, and actual on-disk layout). This is an initial rough estimate, **not** a universal Cassandra safety threshold.

Ask further: how many orders does the largest customer have? Are there campaign-driven spikes? What are the largest partition size, per-node maximums, and tombstone ratio? Daily buckets make partitions smaller but increase the number of partitions read when querying an entire month. Balance this against real workload profiles and benchmark on the target system.

### 7.2. Frequency, SLA, and Consistency

Not every query has the same priority. Document:

- Average and peak call rates; concurrent callers; the highest-traffic tenants or customers.
- Latency targets (e.g., p95/p99), acceptable error rates, and maximum result payload sizes.
- Appropriate read/write consistency levels (e.g., `LOCAL_QUORUM` in an appropriate datacenter deployment), read-your-writes expectations, and fault-tolerance requirements.
- Update, delete, or TTL patterns: tombstones can make a query returning few rows still incur heavy read work.

Raising the consistency level does not fix a query that reads too many partitions or filters data inefficiently; those are two separate design decisions.

### 7.3. Boundaries of Optional Filters

Every UI toggle can create another query shape. For example:

```text
GET /orders?customerId=...&month=...             -> Q01
GET /orders?customerId=...&month=...&status=PAID -> requires separate evaluation
GET /orders?status=PAID&day=...                  -> Q03
GET /orders?minAmount=...&sort=amount_desc      -> Q05, no suitable read path yet
```

If product wants arbitrary filter combinations, prioritize identifying the subset of queries actually used in practice, expected load, and required user experience. Never promise performance for every filter combination merely because the API can express them.

## 8. Template for Handing Off the Query Inventory to Table Design

A complete inventory enables backend, product, and operations teams to validate assumptions together:

| Handoff Field | Q01 Example | How to Verify |
| --- | --- | --- |
| Query ID / owner | `Q01` / Customer API | Cross-check against endpoint and owning team |
| Always-present inputs | tenant, customer, month | Verify API contract and actual call payloads |
| Read range | at most one month/request | Test month boundaries, UTC, and empty data |
| Filters | equality on partition key; range on timestamp | Write actual CQL, avoiding `ALLOW FILTERING` |
| Sort | timestamp DESC, ID DESC | Test records with identical `created_at` |
| Limit/page | 20 default; 100 max | Test last page, invalid token, and concurrent writes |
| Partition size | projected rows/month/customer | Measure against largest cohort, not just averages |
| SLA/load | metrics populated from real traffic | Load test; measure p95/p99 and partitions read |
| Consistency | finalized after business alignment | Test read-after-write and replica failures |
| Design status | `SUPPORTED` / `NEEDS_DESIGN` | Do not mark supported without a clear read path |

During verification, use `cqlsh` or prepared statements with **representative schemas and datasets**, thoroughly testing start/end range boundaries, empty partitions, large partitions, and status transitions. Use tracing/metrics when diagnosing read counts, latency, and tombstone issues; do not judge a design solely because a CQL query runs successfully on a handful of sample rows.

## 9. Common Pitfalls

| Symptom | Why It Is Dangerous | How to Fix at Gathering Time |
| --- | --- | --- |
| "Just store orders and we can `WHERE` on any field later" | Ignores partition routing and clustering order | List each query pattern, mandatory inputs, and volume separately |
| Writing only "latest orders" | Unclear timestamp column, tie-breaking, and sort scope | Specify `created_at DESC, order_id DESC` and single- vs. multi-partition scope |
| Adding `ALLOW FILTERING` to bypass CQL errors | May read large amounts of data before discarding rows | Decide which filters belong in keys or in a separate serving table |
| Believing `LIMIT 20` guarantees a lightweight query | `LIMIT` does not bound tombstones or partitions scanned | Document bucket limits, partition caps, and pagination strategy |
| Using only `tenant_id` as partition key for unbounded data | Large tenants create hot/oversized partitions | Analyze data distribution, bucketing, and peak traffic |
| Adding every filter to one endpoint without analysis | Each combination may require a distinct access path | Mark supported vs. unsupported query shapes |
| Duplicating data but forgetting updates/deletes | Tables can return inconsistent states | Define update ownership and reconciliation procedures |

## 10. Self-Check Exercise

A product requires a screen showing the **"20 most recent transactions for a device on a given day"**, with mandatory filters on `tenantId`, `deviceId`, and UTC date; newest first by default. Users occasionally want to view an entire week and additionally filter by `severity = HIGH`.

Answer before writing CQL:

1. Which fields must be in the Q01 contract? Which fields are optional filter conditions?
2. For a single-day query, what are reasonable partition key and clustering columns? Which column should break timestamp ties?
3. How does the "entire week" requirement affect partition count, overall sort order, and pagination?
4. Can the `severity = HIGH` filter be applied efficiently on the initial history table, or does it need another read design?

**Reference guidance:** One candidate is partition key `(tenant_id, device_id, day_bucket)` and clustering `(event_time DESC, event_id DESC)`, with `LIMIT 20` for a single-day read. A weekly query must cap fan-out and merge in order within the application, or consider a more suitable table if very common. `severity` should only become a primary filter path after confirming usage volume; simply adding `WHERE severity = 'HIGH'` to the history table is not enough to guarantee efficiency.

## Conclusion

In Cassandra, every query must be treated as a **concrete read contract**: which partition it targets, which rows it narrows down, in what order it reads, how much it limits, how it paginates, and how it behaves under real load. The more precise the query inventory, the less guesswork is needed when choosing partition keys, clustering columns, buckets, and denormalized tables. Conversely, arbitrary filtering, global sorting, or massive multi-partition reads must be caught early and designed as separate read paths with controlled cost.
