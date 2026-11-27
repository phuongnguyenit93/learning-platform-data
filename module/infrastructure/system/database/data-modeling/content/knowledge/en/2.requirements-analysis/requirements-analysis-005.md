# Listing Read, Write, Search, Aggregation Operations, and Execution Frequency

## 1. Why Survey the Workload?

When translating business requirements into a data model, identifying entities and relationships only answers what data consists of. Design must also answer how data is accessed, by whom, when, at what scale, and with what response requirements.

The set of operations a system executes against data is called the **workload**. A workload encompasses reads, writes, searches, aggregations, background jobs, and batch processing runs. It directly shapes data organization, keys, indexes, transaction boundaries, storage strategies, and scaling approaches.

For example, a sales system may store customers, products, orders, and inventory. Yet merely knowing these entities is insufficient for design. You need to know whether the system looks up orders primarily by order code or by customer, searches products by name or multiple filters, updates inventory concurrently, and computes revenue reports in real time or on a schedule.

The goal of this survey step is to produce a verifiable catalog of operations. Each operation must be tied to a business purpose, data access pattern, frequency, data size, latency requirement, and consistency requirement.

## 2. Distinguishing Business Operations and Database Operations

A single business action can generate multiple database operations. For instance, the business action of creating an order may include:

1. Reading customer details and checking account status.
2. Reading the price and sellable status of each product.
3. Checking and reserving inventory quantity.
4. Writing the order and its line items.
5. Writing status history or an event for downstream processing.

Therefore, do not treat one API call or one user button click as a single data operation. When estimating load, record both the business execution count and the number of read/write operations each business action generates. This perspective prevents underestimating load when a single business request triggers multiple queries or multiple updates.

It is also necessary to separate synchronous operations from background tasks. Sending notifications, syncing data to external systems, generating scheduled reports, and purging expired data may not appear in the primary UI flow, yet still place substantial load on the data system.

## 3. Categorizing Data Access Operations

### 3.1. Read Operations

Read operations retrieve stored data without changing business state. Classify them by how records are identified and the shape of the result.

| Read Pattern | Business Example | Characteristics to Record |
|---|---|---|
| Single-record lookup | Fetch order by order code | Lookup key, returned record count, whether related data must be loaded |
| Alternate-key lookup | Find customer by email or phone number | Uniqueness, mutability of the lookup value |
| Conditional listing | View a customer's orders | Filters, time range, result count |
| Range read | Fetch transactions within a date range | Range bounds, sort order, page size |
| Relational read | Fetch line items of an order | Number of relationships to traverse, child record count |
| Aggregated detail read | View order detail page with customer and products | Number of data sources, join/merge method, required consistency level |

For each read operation, identify filter conditions, sort fields, pagination, and related data to return. Two queries reading the same orders table can have very different characteristics: lookup by order code usually retrieves one record, whereas listing orders by customer and time may scan a large dataset.

For example, a customer's recent order list might use the query:

```sql
SELECT id, status, created_at, total_amount
FROM orders
WHERE customer_id = :customer_id
  AND created_at >= :from_time
  AND created_at < :to_time
ORDER BY created_at DESC
LIMIT :page_size;
```

The access pattern here consists of an equality condition on `customer_id`, a range condition on `created_at`, descending sort by timestamp, and a limit on result count. This is valuable information when evaluating keys and indexes later.

### 3.2. Write Operations

Write operations mutate state or append new information. Common forms include:

- **Insert:** Creating a customer, order, line item, or history record.
- **Update:** Changing an address, order status, price, or inventory quantity.
- **Delete:** Removing data per business request or retention policy.
- **Upsert:** Creating a new record if absent or updating if already present.
- **Batch write:** Importing data, syncing multiple records, or processing a batch of transactions.
- **Append-only:** Recording events, logs, or change history without modifying old records.

Beyond counting write frequency, determine how many records each write affects and how many entities must change together. An order creation transaction may have to write the order, line items, and inventory reservation within a single consistency boundary.

Important questions include:

- Is a record created once or updated repeatedly?
- Does a single write modify one row or many rows?
- Which changes must succeed or fail together?
- Can multiple users or processes update the same data concurrently?
- Is deduplication required when a request is retried?
- Is data hard-deleted, soft-deleted, or moved to another storage tier?

These answers help identify transaction requirements, write-contention controls, idempotency, and history retention policies.

### 3.3. Search Operations

Search typically combines multiple conditions and may require ranking by relevance. Clearly distinguish search from single-record lookup or basic list filtering.

| Search Type | Example | Characteristics to Investigate |
|---|---|---|
| Exact match | Find product by SKU | Is the value unique? Is case normalized? |
| Prefix match | Find names starting with a string | Is autocomplete/typeahead needed while typing? |
| Full-text search | Search products by description | Language, tokenization, diacritics (e.g., Vietnamese accents), relevance |
| Multi-filter search | Filter products by category, price, and status | Filter count, common combinations, selectivity |
| Sorted search | Search products and sort by price or popularity | Sort fields, pagination, stable ordering |
| Spatial / range search | Find locations within a radius or region | Spatial data, units of measure, precision |

Document which fields users commonly search on, whether multiple filters are combined, how results must be ranked, and how quickly new data must appear in search results. If full-text search has specific requirements for relevance or suggestions, it may need a different data organization and indexing mechanism than standard relational queries.

### 3.4. Aggregation Operations

Aggregations condense multiple records into metrics or grouped results. Common aggregations include counts, sums, averages, min/max values, grouping by attributes, and time-window calculations.

For example, a daily revenue report may be computed from paid orders:

```sql
SELECT DATE_TRUNC('day', created_at) AS day,
       COUNT(*) AS order_count,
       SUM(total_amount) AS revenue
FROM orders
WHERE status = 'PAID'
  AND created_at >= :from_time
  AND created_at < :to_time
GROUP BY DATE_TRUNC('day', created_at)
ORDER BY day;
```

When surveying an aggregation query, determine:

- Scope of data to read: full history, a time window, or a subset of entities.
- Grouping dimensions: day, month, store, customer, product, or status.
- Refresh frequency: on-demand per request, every few minutes, hourly, or daily.
- Acceptable data freshness: must numbers update immediately, or can they lag by some interval?
- Usage pattern: interactive dashboard, scheduled report, file export, or ad-hoc analysis.

Aggregation queries over large datasets can compete for resources with online transactions. Freshness requirements help decide whether to aggregate on read, precompute results, or offload part of processing to a separate analytical pipeline.

## 4. Building a Workload Catalog

After classification, record each operation as a row in a catalog. Each row should describe an access pattern concrete enough to estimate and verify.

| Information Field | Content to Record |
|---|---|
| Operation ID | Short identifier for discussion and traceability, e.g., `R-01` or `W-02` |
| Actor and purpose | Who executes it, to accomplish which business task |
| Operation type | Read, write, search, aggregation, or background task |
| Access pattern | Lookup keys, filters, relationships to read, sort fields |
| Result size | Single record, one page, thousands of records, or full dataset |
| Frequency | Per second, per minute, per hour, per day, or batches per period |
| Peak load | Frequency during the busiest hour or event |
| Target latency | Desired response time, expressible via p95 or p99 |
| Consistency and freshness | Must newly written data be read immediately; how stale can aggregated data be |
| Criticality | Consequences if the operation is slow, fails, or returns stale data |

The illustrative example below uses a hypothetical sales system. The numbers only illustrate documentation format, not default figures for every system.

| ID | Business Action & Operation Type | Average Frequency | Peak | Key Requirement |
|---|---|---:|---:|---|
| R-01 | Look up order by code, read | 30 req/s | 120 req/s | Return one order and latest status |
| R-02 | List orders by customer, read | 8 req/s | 32 req/s | Sort by time, paginate |
| S-01 | Search products by keyword and filters | 5 req/s | 25 req/s | Relevant results, fast response |
| W-01 | Create order and reserve stock, transactional write | 3 tx/s | 15 tx/s | Related changes must be consistent |
| W-02 | Update delivery status, write | 2 req/s | 10 req/s | Enforce valid state transitions |
| A-01 | Compute daily revenue, aggregation | 1 run / 5 min | Spikes when opening report | Maximum data staleness per requirement |

The catalog must be detailed enough for the design team to visualize data access paths without guessing from feature names. If one feature executes multiple distinct access paths, split it into separate rows. For example, an orders screen might run one query to count total orders and another to fetch a page of orders; these two queries can have different costs and optimization strategies.

## 5. Quantifying Frequency and Load

### 5.1. Using Appropriate Units

Choose units that reflect the true nature of the operation:

- **QPS (queries per second):** Queries per second, suited for reads or searches.
- **TPS (transactions per second):** Transactions per second, suited when a business operation bundles multiple data operations that must complete together.
- **Per minute, per hour, or per day:** Suited for periodic tasks or low-frequency operations.
- **Records per batch:** Suited for imports, syncs, and batch processing.

Do not add different units together directly. Convert them to a common time window when comparing total load, while retaining batch size and operation count per transaction.

### 5.2. Distinguishing Average and Peak

Average frequency indicates everyday usage, yet fails to describe load capacity needed when many users act at once. Survey at least:

- Daily average or average over a representative period.
- Peaks by hour, day of week, season, or campaign.
- Short-term spikes triggered by events, notifications, or bulk imports.
- Expected growth in users, data, and operation volume.

If a query averages 30 req/s and peaks at 120 req/s, the peak-to-average factor is:

```text
Peak factor = Peak frequency / Average frequency
            = 120 / 30
            = 4
```

This factor highlights the gap between normal load and load to prepare for. When real logs exist, measure across short time windows suited to system behavior; a daily average can mask traffic spikes lasting several minutes.

### 5.3. Estimating from User Count and Behavior

When no live system exists to measure, build an initial estimate from behavior:

```text
Operations per period
  = Active users
  × Business actions per user
  × Data operations per business action

Average frequency
  = Operations per period / Seconds in period
```

For example, with 2,000 active users in one hour, each opening the order list 6 times on average, and each open triggering 2 data queries, the estimated query total is:

```text
2,000 × 6 × 2 = 24,000 queries/hour
24,000 / 3,600 ≈ 6.67 queries/second
```

This is only an estimate. Actual numbers can differ due to caching, prefetching, retries, pagination, background tasks, and behavioral differences across user segments. Clearly record every assumption used so it can be adjusted once measurements arrive.

### 5.4. Measuring Latency and Concurrency

Frequency must be paired with latency. A query running 10 times/second that reads millions of records each time can exert far greater pressure than a query running 100 times/second returning one tiny record.

Do not rely solely on average duration. Percentiles such as **p95** and **p99** show the time within which 95% or 99% of requests complete, exposing slow tail requests.

Concurrent requests in flight can be estimated using Little's Law:

```text
Concurrent requests in flight ≈ Request arrival rate × Average processing time
```

For instance, at 120 requests/second and an average processing time of 0.2 seconds, requests in flight at a given moment are roughly 24. This estimates request concurrency; actual database connections and concurrency also depend on connection pools, caches, queues, and how the application executes queries.

### 5.5. Recording Data Size and Selectivity

Beyond frequency, each access pattern needs data volume details:

- Current total record count and expected growth per day, month, or year.
- Number of records read, returned, or updated in a single operation.
- Ratio of records matching the filter relative to the dataset examined.
- Average size of a record and of the returned payload.
- Retention duration, mutation rate, and need to query historical data.

A filter returning 5 records out of 10 million has very different characteristics from a filter returning 500,000 records. Filter selectivity and result size help evaluate query efficiency and indexing needs in the next design step.

## 6. Collecting Survey Data

When a system is already running, prioritize observed metrics from application logs, query statistics, database monitoring tools, and distributed tracing. Collect business operation names, query patterns, execution times, call counts, records read/written, and errors or retries.

When a system has no production data yet, combine:

1. **Interviewing users and business owners:** Identify frequent operations, peak times, critical reports, and consequences of slow data.
2. **Walking through each workflow:** Trace from business initiation to completion, logging every data read and write.
3. **Inspecting input and output samples:** Verify filters, sort fields, pagination, and result sizes actually needed by features.
4. **Estimating by user segment:** Separate regular users, administrators, operations staff, and automated processes.
5. **Cross-checking against measurements:** Once prototypes or live systems exist, compare estimates with metrics to refine assumptions.

In the survey documentation, tag every number's source as **measured**, **estimated**, or **target requirement**. Never present a guessed figure as observed production data. For estimates, state assumptions and uncertainty ranges where applicable.

## 7. Using Workload to Guide the Data Model

The workload catalog is an input to modeling decisions, yet does not automatically dictate a single database engine or structure.

- If the system frequently reads by a stable key, define the lookup key and its uniqueness.
- If the system frequently lists by an entity with time filters, describe ordering, range, and pagination method.
- If multiple writes must uphold the same business rule, identify the entities and changes belonging to the same transaction.
- If search combines full-text, multiple filters, and ranking, separately evaluate search requirements and index freshness.
- If reports scan large data volumes, define acceptable freshness to choose between live computation, precomputation, or analytical offloading.
- If certain frequent reads require data across many relationships, weigh join costs against the cost of maintaining derived data.

For instance, an order detail screen may need data from orders, customers, and line items. Meanwhile, a revenue report needs to scan many orders across a time range and group results. Both use order data, yet have different purposes and load profiles. Good design considers workload, consistency rules, evolvability, and data maintenance costs simultaneously.

## 8. Common Mistakes

- Listing CRUD only without describing filter conditions, sorting, pagination, and relationships to read.
- Counting user action frequency while ignoring the multiple queries generated inside one business operation.
- Estimating only average load while overlooking peaks, seasonality, and batch jobs.
- Forgetting background tasks, retries, syncs, reports, and administrative workflows.
- Lumping short transactional queries and long analytical queries into the same bucket.
- Recording frequency without recording data size, returned record count, and target latency.
- Using estimated numbers without documenting sources or assumptions.
- Optimizing the model for a rare query while significantly increasing the cost of frequent operations.

## 9. Survey Completion Checklist

Before moving to detailed design, verify:

- [ ] Primary read, write, search, and aggregation operations have been listed.
- [ ] Every operation has a specific business purpose, actor, and access pattern.
- [ ] Lookup keys, filters, sorting, pagination, and relationships to read are described.
- [ ] Business execution counts are distinguished from generated data operations.
- [ ] Average frequency, peak frequency, and schedule cycles for periodic tasks are included.
- [ ] Data scale, result sizes, and growth rates are estimated.
- [ ] Latency targets, concurrency levels, and consistency or freshness requirements are stated.
- [ ] Figures clearly distinguish measured actuals, estimates, and targets.
- [ ] Uncertain assumptions are logged for verification.

A clear workload catalog helps the design team translate business needs into concrete data access patterns. From there, choices of keys, relationships, indexes, transaction boundaries, and storage structures rest on solid evidence, while providing criteria to verify as the system evolves.
