# Infrequent Secondary Queries and the Need for Search/Analytics Stores

## Lesson Objectives

Apache Cassandra is designed to excel at access paths where **the partition key and intra-partition read order are known in advance**. Consequently, query-driven design commonly creates dedicated tables for critical APIs. Yet not every requirement deserves its own table: many arise only during incident investigations, periodic reporting, ad-hoc searches, or rare administrative tasks.

Within the **Query-Driven Design** chapter of the `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` module, this lesson addresses the decision: **when do you accept a bounded secondary query, when do you add a query-serving table, and when do you offload the need to a dedicated search or analytics system?** The decision must rest on read paths, data volume, latency, freshness, replication/consistency, duplicated write cost, and failure recovery. Illustrative examples use CQL and Java application connectivity.

After this lesson, you will be able to:

- Classify **primary queries**, **infrequent secondary queries**, and **exploratory/analytical queries** by inputs, scope, SLAs, and frequency.
- Explain why a syntactically valid `SELECT` or a `LIMIT` clause does not automatically mean a cheap Cassandra query.
- Compare four options: **bounded fan-out**, **dedicated query-driven table**, **suitable indexing**, and **external search/analytics store**.
- Identify requirements that demand full-text search, multi-attribute filtering, facets, or historical aggregations.
- Sketch a pipeline from source data to search/analytics, handling sync lag, updates/deletes, replays, backfills, and reconciliation.
- Propose API contracts, load tests, and how Java routes queries to the right system.

## 1. Infrequent Secondary Queries Are Not Necessarily Cheap Queries

Suppose a multi-tenant e-commerce application uses Cassandra to store orders. Most users perform only two actions:

1. View the details of one order by `order_id`.
2. View a customer's 50 most recent orders in a month.

Meanwhile, support staff occasionally need to "find orders containing `damaged packaging` in the note, with status `RETURNED`, and total amount between 500,000 and 2,000,000 VND." The analytics team wants to "calculate total revenue by province and product category per week over two years."

Both of the latter requests may be called infrequently, yet **the data scope they examine is huge** and **access keys are missing**. Low call frequency does not make them safe on a Cassandra cluster serving live transactional traffic.

| Characteristic | Primary Query | Bounded Secondary Query | Search / Exploratory / Analytical |
| --- | --- | --- | --- |
| Inputs | Primary key known upfront | A few known partitions/buckets | Keywords, arbitrary multi-filters, wide ranges |
| Access pattern | Stable, frequent | Infrequent, specific scope | Unpredictable, varies by user |
| Scope | One partition or small fixed set | Maximum partition count capped | Many tenants/days/attributes, potentially entire dataset |
| Sorting | By clustering key | May merge results across a few partitions | Multi-column sort, relevance, aggregations |
| Expectations | Low latency, often needs fresh data | May tolerate higher latency | Prioritizes flexibility or data aggregation |
| Design direction | Query-driven Cassandra table | Bounded fan-out or supplementary table | Search index / OLAP / data lake as needed |

**Infrequent secondary queries** should be evaluated by **worst-case cost per request**, not just total daily request count. A single report can overload the cluster if it forces scanning millions of partitions or traversing massive tombstones.

## 2. Classifying by Query Contract

Before writing `CREATE TABLE` or indexes, build a catalog of query shapes. For example:

| ID | Business Requirement | What Does the Caller Know? | Sort / Aggregation | Expected Latency | Preliminary Direction |
| --- | --- | --- | --- | --- | --- |
| Q01 | Fetch order details | Tenant, order ID | Single result | Low | Cassandra lookup |
| Q02 | Fetch customer's 50 newest orders in UTC month | Tenant, customer ID, month | `created_at DESC` | Low | Cassandra time-ordered table |
| Q03 | Fetch one customer's orders across up to 3 months | Tenant, customer ID, start/end months | Newest first | Medium | Bounded fan-out across buckets |
| Q04 | Filter `FAILED` within one known customer/month partition | Tenant, customer ID, month, status | Same chronological order | Relaxed | Bounded filter or evaluate index |
| Q05 | Search keywords in notes across tenant, plus status/price | Tenant, text, and optional filters | Relevance or newest date | Low–medium | Search engine |
| Q06 | Aggregate revenue by province/week over 2 years | Tenant, year range, grouping dimensions | `GROUP BY` and `SUM` | Can be async | Analytics/OLAP store |
| Q07 | Serve tenant/day `PENDING` queue under high load | Tenant, status, day | Newest first | Low | Cassandra projection table if load permits |

In practice, also ask about **peak QPS**, data growth rate, entity size, largest tenant, required result freshness, retention, and access permissions. A Q05 called 10 times/day needing under 200 ms is completely different from a Q05 allowed to run as a multi-minute batch job.

### 2.1. Input Classification Matrix

For each query, record:

- **Mandatory fields:** are all components of an existing partition key present?
- **Maximum scope:** how many partitions, time ranges, rows, and bytes can be read?
- **Predicates:** filtering on clustering columns or regular columns? Are there full-text terms, multi-column ranges, negations, or complex `OR`s?
- **Results:** `LIMIT`, pagination, exact counts, facets, aggregations, relevance ranking?
- **Freshness:** read-your-writes, seconds, minutes, or end-of-day reports?
- **Interaction mode:** synchronous request, asynchronous export, or internal admin query?

Never group two queries together merely because both read the `orders` table. **Routing path and data transformations** are the deciding factors.

## 3. A Cassandra Schema Serving Primary Queries

Example of two tables serving Q01 and Q02:

```sql
CREATE TABLE orders_by_id (
    tenant_id text,
    order_id uuid,
    customer_id uuid,
    created_at timestamp,
    status text,
    total_amount decimal,
    note text,
    revision bigint,
    PRIMARY KEY ((tenant_id, order_id))
);

CREATE TABLE orders_by_customer_month (
    tenant_id text,
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_amount decimal,
    note text,
    revision bigint,
    PRIMARY KEY ((tenant_id, customer_id, month_bucket),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);
```

`month_bucket` is a `YYYY-MM` string computed from `created_at` in UTC. `order_id` acts as a tie-breaker when multiple orders share the same creation millisecond. In the ID table, `order_id` belongs to the partition key; in the customer/month table, it is a clustering column. Both tables must be updated properly when creating or editing orders, because Cassandra **does not automatically synchronize business projections**.

Q01:

```sql
SELECT customer_id, created_at, status, total_amount, note, revision
FROM orders_by_id
WHERE tenant_id = ? AND order_id = ?;
```

Q02:

```sql
SELECT created_at, order_id, status, total_amount
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
LIMIT 50;
```

These queries supply the full partition key. Cassandra reads one partition and uses the customer/month table's clustering order to serve newest-first lists.

Conversely, the following idea is **not** an efficient tenant-wide search solution:

```sql
-- DO NOT use as a general tenant-wide search pattern.
-- This query lacks customer_id and month_bucket of the composite partition key.
SELECT order_id, created_at, total_amount
FROM orders_by_customer_month
WHERE tenant_id = 'tenant-A'
  AND status = 'FAILED';
```

This is not something solved by adding `ORDER BY` or `LIMIT 50`. The schema routes by `(tenant_id, customer_id, month_bucket)`, whereas the query knows only tenant and status. Reclassify Q05/Q07 by access pattern.

## 4. Four Options for Secondary Queries

### 4.1. Option A: Small, Bounded Fan-Out

Q03 asks for a customer's history across **three known UTC months**. The application can compute the three `month_bucket` values, read each partition using Q02, and merge results by `(created_at DESC, order_id DESC)`.

```text
Request: customer=C, from=2026-09, to=2026-11
   |-- partition (tenant, C, 2026-09)
   |-- partition (tenant, C, 2026-10)
   |-- partition (tenant, C, 2026-11)
   +-- merge by created_at DESC, order_id DESC
       return max 50 orders + next-page state
```

**Conditions for this approach to be acceptable:**

1. Know **all** partition key components for every branch upfront.
2. Maximum fan-out is small and **enforced by the API contract**, e.g., at most three calendar months per request.
3. Sort/merge in bounded memory; never load the entire history first before applying `LIMIT`.
4. Manage per-partition paging and how continuation tokens are built during merging.
5. Benchmark p95/p99 against the heaviest customer, including tombstone and empty-bucket cases.

**Time trap:** a three-month sliding window measured in days does not necessarily touch just three calendar-month buckets. The API must align on "three calendar months" vs. half-open `[from, to)`, then count the actual buckets touched.

Bounded fan-out is often preferable to adding another table when the request is genuinely rare, partition counts are tiny, and SLAs still hold.

### 4.2. Option B: Projection Table When a Secondary Query Becomes Critical

If Q07—the tenant/day `PENDING` queue—becomes a frequent, low-latency read path where callers always have tenant, status, and day, you can create:

```sql
CREATE TABLE orders_by_status_day (
    tenant_id text,
    status text,
    day_bucket date,
    created_at timestamp,
    order_id uuid,
    customer_id uuid,
    total_amount decimal,
    PRIMARY KEY ((tenant_id, status, day_bucket),
                 created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id DESC);

SELECT created_at, order_id, customer_id, total_amount
FROM orders_by_status_day
WHERE tenant_id = ?
  AND status = 'PENDING'
  AND day_bucket = ?
LIMIT 50;
```

Here `day_bucket` is the **UTC date of `created_at`**. The query means "orders created on day X that are currently PENDING"—not "orders that transitioned to PENDING on day X."

The new table cuts read fan-out, yet:

- Each order creation adds another mutation.
- Transitioning `PENDING → PAID` requires a `DELETE` in the old status partition and an `INSERT` in the new partition, generating tombstones.
- If projection updates lag or fail, the list can temporarily be stale.
- A very large tenant can create a **hot partition** at `(tenant, PENDING, day)`; measure size/throughput and consider sharding with bounded multi-partition reads.

**Never create a new table simply because Q05 has an ad-hoc filter combination requested once.** A projection is worthwhile when its query shape is stable, delivers clear business value, and has acceptable write and recovery costs.

### 4.3. Option C: Suitable Indexing for Scoped Filters

On certain Cassandra versions/deployments, **Storage-Attached Indexes (SAI)** can support filters on non-primary-key columns. Illustrative example when SAI is supported:

```sql
-- Use only after confirming your Cassandra version/deployment supports SAI.
CREATE CUSTOM INDEX IF NOT EXISTS orders_customer_month_status_sai
ON orders_by_customer_month (status)
USING 'StorageAttachedIndex';

-- Case where the exact customer/month partition is already known.
SELECT created_at, order_id, status, total_amount
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
  AND status = 'FAILED';
```

In Q04, the caller **already knows the partition** and only filters further on status; if the partition has very few rows, the application may accept reading a small set and filtering instead of creating an index. If partitions are large, compare unindexed reads, indexed reads, and a dedicated table under realistic workloads.

**Important limitations:**

- SAI syntax/capability support depends on **Cassandra version and deployment environment**. Never assume it exists on every cluster.
- SAI does not turn a regular column into a clustering column and **does not automatically enable arbitrary global `ORDER BY`**.
- Indexes carry creation, storage, update, and resource costs. Low-selectivity predicates over wide scopes remain expensive.
- Indexes do not magically turn multi-filter, text-relevance, faceted, arbitrarily sorted queries into a dedicated search-engine experience.

Different secondary index types carry different features and limits by version. Never treat `ALLOW FILTERING` as an index: it merely tells Cassandra to allow certain filtering queries whose actual work can be unpredictable. That a statement executes **does not prove** the query shape is safe for large tenants.

### 4.4. Option D: Dedicated Search Store or Analytics Store

When requirements exceed pre-computable access paths, separate the **transactional data store** from the **search/analytics model**:

| Need | System Worth Evaluating | Primary Advantage |
| --- | --- | --- |
| Full-text keywords, relevance, combined filters, facets | Search engine such as OpenSearch/Elasticsearch or suitable search service | Inverted indexes and flexible querying |
| Multi-dimensional metrics, aggregations over billions of rows, historical trends | Analytics/OLAP store such as ClickHouse, BigQuery, or equivalent | Columnar scans, aggregations, and history |
| Raw data exploration, batch ETL, long ad-hoc queries | Data lake/warehouse and SQL engines like Spark/Trino per architecture | Isolates reporting load from transactional queries |
| Online work queues with stable keys/sorting | Query-driven Cassandra projection | Routes to known partitions with low latency |

Technology names here are examples of **system categories**, not mandatory prescriptions. Final choices depend on volume, operating cost, freshness, security, existing integrations, and SLAs.

A search engine typically fits Q05; an analytics store typically fits Q06. Never force transactional Cassandra to shoulder broad analytical aggregations when that workload can run on replicated analytics-ready data.

## 5. When Do You Need a Search Store?

A search store is worth evaluating when an API simultaneously demands several of these traits:

- **Full-text search** over titles, notes, and descriptions, with tokenizers/analyzers, language rules, and ranking.
- Arbitrary combinations of filters on status, product category, amount ranges, geography, or optional attributes.
- Sorting by **relevance**, price, creation date, or multiple keys not covered by one Cassandra table's clustering.
- Returning facets: counts by status, category, price bucket, or indexed fields.
- Deep pagination over broad search results with well-defined limits and stability semantics.

Example API:

```text
GET /tenants/tenant-A/orders/search
    ?q=damaged-packaging
    &status=RETURNED
    &minAmount=500000
    &maxAmount=2000000
    &sort=createdAtDesc
    &pageSize=30
```

A **search document** might look like:

```json
{
  "document_id": "tenant-A:order-123",
  "tenant_id": "tenant-A",
  "order_id": "order-123",
  "customer_id": "customer-45",
  "created_at": "2026-11-21T09:30:00Z",
  "status": "RETURNED",
  "total_amount": 1250000,
  "title": "Box dented on delivery",
  "note": "Customer reported damaged packaging",
  "revision": 17
}
```

This is an **illustrative document**, not a Cassandra key format. `document_id` should be unique within the index namespace; when multiple tenants share an index, composite tenant/order IDs are typically needed to avoid collisions. Depending on security rules, you may not need to copy sensitive personal data into search.

A conceptual query DSL for an engine supporting OpenSearch-style syntax:

```json
{
  "size": 30,
  "query": {
    "bool": {
      "must": [
        {"multi_match": {"query": "damaged packaging", "fields": ["title", "note"]}}
      ],
      "filter": [
        {"term": {"tenant_id": "tenant-A"}},
        {"term": {"status": "RETURNED"}},
        {"range": {"total_amount": {"gte": 500000, "lte": 2000000}}}
      ]
    }
  },
  "sort": [
    {"created_at": {"order": "desc"}},
    {"document_id": {"order": "desc"}}
  ]
}
```

**Note:** this structure is illustrative; validity depends on mappings (e.g., `keyword` for tenant/status/document ID, `date` for `created_at`, numeric types for amount) and the actual search engine's API/version. Any field used for sorting needs a sortable type and mapping. Deep pagination usually needs an appropriate mechanism such as `search_after`, optionally paired with point-in-time, rather than arbitrarily increasing offsets. Results can shift as the index updates.

**Tenant authorization must be enforced on the server.** Never trust a client-supplied `tenant_id` alone; the service must verify the user belongs to the tenant and apply that filter to every query, including facets and exports. When search returns only IDs, you can query Cassandra's `orders_by_id` to verify current state and access rights before displaying details.

## 6. When Do You Need an Analytics Store?

An analytics store answers questions like:

- Revenue by province, product category, and week over two years?
- Late-delivery rate by carrier and customer cohort?
- Hourly failed-order counts compared across multiple months?
- Long-term trend analysis combining data from orders, payments, and shipping?

These are **broad scans and aggregations**, typically requiring multi-dimensional `GROUP BY`s and `JOIN`s across multiple sources. CQL is not a general-purpose analytical SQL language, and `COUNT(*)` over a wide range does not become cheap just because the statement is short.

A fact table in an analytics system might contain:

| Column | Analytical Role |
| --- | --- |
| `tenant_id` | Enforces tenant scope |
| `order_id` | Reconciliation / deduplication key |
| `created_at`, `created_date` | Time axis and analytical data partitioning |
| `region`, `product_category` | Grouping dimensions |
| `status` | Current status or status at event time; must be clearly defined |
| `total_amount` | Metric to aggregate |
| `revision`, `ingested_at` | Tracks revisions and data freshness |

Illustrative SQL **for an OLAP system**, not CQL:

```sql
SELECT tenant_id,
       DATE_TRUNC('week', created_at) AS week_start,
       region,
       product_category,
       SUM(total_amount) AS revenue
FROM order_facts
WHERE tenant_id = ?
  AND created_at >= ?
  AND created_at < ?
  AND status = 'PAID'
GROUP BY tenant_id, DATE_TRUNC('week', created_at),
         region, product_category;
```

Details of `DATE_TRUNC` syntax, placeholders, and temporal types vary by SQL engine. More important than syntax is **metric definition**: total value of orders created in the week or paid in the week? Are refunds subtracted? When an order changes status, is the fact updated in place or appended as an event? The analytics store must specify these rules clearly so numbers do not diverge from Cassandra due to mismatched definitions.

Long-running reports can execute as **asynchronous jobs** with resource caps, saving output and returning a download link via the application rather than holding HTTP connections open for minutes. Never force the transactional Cassandra cluster to absorb heavy reporting batch scans when a better architecture exists.

## 7. Architecture Separating Transactional Reads from Exploratory Queries

A high-level design:

```text
                          +--> Cassandra: orders_by_id
API / Order Service ------+--> Cassandra: orders_by_customer_month
             |            +--> Cassandra: projections for stable query shapes
             |
             +--> durable change source (event log / operational CDC)
                           |
                           +--> Search consumer -> Search index
                           |
                           +--> ETL/streaming -> Analytics / OLAP store
                           |
                           +--> Dedupe / retry / reconciliation / lag monitoring

Read API:
  lookup by ID / customer-month -> Cassandra
  keyword/filter/facet search   -> Search index
  historical aggregations       -> OLAP / reporting jobs
```

**Never mistake this diagram for an automatic guarantee against data loss.** If the application writes to Cassandra and emits an event in two uncoordinated steps without durability guarantees, a crash in between can leave search/OLAP **permanently missing changes**. Choose an event-source architecture with concrete guarantees: a durable event log, an outbox suited to the source technology, operational CDC connectors, or verified replay/backfill processes.

### 7.1. Ways to Propagate Changes to Search/OLAP

| Approach | Advantage | Risks / Questions to Answer |
| --- | --- | --- |
| App writes to Cassandra and search in parallel | Conceptually simple path | Dual-write gap: source succeeds while search fails or vice versa |
| Emit accepted business events | Decoupled consumers; supports retries/replays | Must guarantee **durable event emission** and preserve ordering/IDs |
| CDC from Cassandra | Captures changes written at source | Requires connectors, log/offset management, initial snapshots, schema evolution |
| Periodic backfill | Easy batch rebuild when full source exists | High latency; must handle updates, deletes, duplicates, and scan cost |

Cassandra CDC and connector support depend on version and deployment. Never assume flipping a CDC flag alone yields **exactly-once** delivery plus full historical snapshots. Nor does CDC automatically understand business transition rules; consumers must select valid events/revisions and handle deletes or TTLs per contract.

### 7.2. Search Data Is an Eventually Consistent Copy

Suppose an order just transitioned `PENDING → PAID`:

```text
10:00:00.000  Write PAID status to transactional source.
10:00:00.200  Lookup-by-ID API already sees PAID.
10:00:02.000  Consumer updates search document to PAID.
```

In the interval between, searching for `status=PENDING` can still return that order. This is **projection/search lag**, distinct from consistency among Cassandra replicas.

Clarify:

- May search lag by a few seconds or minutes?
- Must results re-verify state/ACL against Cassandra before taking action?
- Are users informed that search results are not instantaneous?
- If the consumer fails for an extended period, does the API serve stale results, pause search, or switch modes?

A **consistency level** like `LOCAL_QUORUM` supports Cassandra read/write consistency requirements in a suitable topology; it **does not** cause the search index to receive unprocessed mutations.

### 7.3. Duplicate Events and Out-of-Order Arrivals

If the search consumer receives revision 18 before revision 17, revision 17 must never overwrite the newer state. The design needs:

1. Stable `document_id`, e.g., `tenant_id + order_id`.
2. `event_id` to identify applied events; monotonically increasing `revision` or per-entity version.
3. Rules applying only valid newer mutations; use **external versioning/conditional updates** if the search engine supports the right semantics, or serialize per entity key in the consumer.
4. Idempotent retries; never generate a new document ID when replaying the same event.
5. Explicit tombstone/delete events, processing deletes only after version-order checks.

Never assume "at-least-once" delivery means final data is always right. If an older event replays after a newer event and the consumer skips version checks, search can regress backward.

## 8. Backfill, Reconciliation, and Cutover

Standing up search/analytics for existing data is a distinct engineering problem—not just turning on a consumer today.

### 8.1. Initial Load and Ongoing Changes

A general workflow:

1. Pick a **complete, enumerable source** for existing orders: snapshot/export, designed manifest/ETL path, or an event log holding full history. **Never** scan all of Cassandra on ordinary request paths.
2. Establish the change-stream checkpoint/watermark before or during the backfill using proper synchronization.
3. Load historical data in bounded batches with stable `document_id`s, tracking per-entity revision.
4. Apply ongoing changes from logs/CDC, handling duplicate or out-of-order events.
5. Reconcile counts and meaningful samples across tenants, statuses, time ranges, record IDs, and revisions.
6. Run canary/shadow reads on the API, verifying freshness, security, and latency before cutting over traffic.

Key rule: during backfill, if revision 20 of an order already reached search while the backfill job is still processing revision 17, the older version must not overwrite the newer one. Versioning/checkpointing must protect both **live sync** and **historical load**.

### 8.2. Reconciliation Is More Than Comparing `COUNT(*)`

Comparing total document counts is only a coarse check. A system can match totals while simultaneously **missing** one order and **duplicating** another.

| Invariant After Convergence | How to Verify |
| --- | --- |
| Every active order has a matching search document | Compare IDs via manifest/batch; verify keys and revisions |
| Status/amount/tenant in search match verified source | Compare synchronized fields; never use search to overwrite Cassandra |
| Documents deleted/hidden per policy no longer appear in search | Replay deletes/tombstones; audit retention and ACLs |
| Analytics data is not double-counted on replays | Dedupe by event ID/revision; check fact keys |
| Aggregations match agreed metric definitions | Cross-check against golden dataset and formulas |
| Sync lag stays within SLO | Measure time from accepted → indexed/queryable |

**Cassandra repair** synchronizes replicas via database mechanisms; it does not locate and fix missing documents in search/OLAP. That requires **business-pipeline reconciliation**.

### 8.3. Deletes, TTLs, and Data Protection

When an order is deleted, hidden, or reaches retention expiration:

- The source of truth must propagate delete/hide rules to search and analytics per policy.
- A Cassandra TTL **does not automatically delete** a document already copied to an external system.
- Tables, indexes, and backups may have differing lifecycles. Data-deletion requirements must be designed end-to-end across the pipeline, including caches/exports if policy mandates.
- Search must enforce tenant permissions and may need to re-check permissions before displaying details, because access rights can change faster than index updates.

Never copy sensitive data into analytics tools solely because the source Cassandra table stores it. Data in search/warehouses is an extra copy requiring proper authorization, encryption, auditing, and retention.

## 9. Java: Routing Each Query Type Properly

The example below uses **DataStax Java Driver 4.x** for Q01/Q02, while Q05 search is abstracted behind a dedicated gateway. This pattern separates responsibilities rather than building one dynamic CQL string for every filter.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.YearMonth;
import java.util.UUID;

public final class OrderReadService {
    private final CqlSession session;
    private final PreparedStatement byId;
    private final PreparedStatement byCustomerMonth;
    private final OrderSearchGateway searchGateway;

    public OrderReadService(CqlSession session, OrderSearchGateway searchGateway) {
        this.session = session;
        this.searchGateway = searchGateway;
        this.byId = session.prepare(
            "SELECT customer_id, created_at, status, total_amount, note, revision " +
            "FROM orders_by_id WHERE tenant_id = ? AND order_id = ?"
        );
        this.byCustomerMonth = session.prepare(
            "SELECT created_at, order_id, status, total_amount " +
            "FROM orders_by_customer_month " +
            "WHERE tenant_id = ? AND customer_id = ? AND month_bucket = ? " +
            "LIMIT 50"
        );
    }

    public Row getById(String authorizedTenantId, UUID orderId) {
        return session.execute(
            byId.bind(authorizedTenantId, orderId)
        ).one();
    }

    public ResultSet latestForCustomer(
        String authorizedTenantId, UUID customerId, YearMonth utcMonth
    ) {
        return session.execute(
            byCustomerMonth.bind(
                authorizedTenantId, customerId, utcMonth.toString()
            )
        );
    }

    public SearchPage search(String authorizedTenantId, SearchCriteria criteria) {
        return searchGateway.search(authorizedTenantId, criteria);
    }

    // Interfaces below are implemented by the project's specific search adapter.
    // They illustrate responsibility boundaries and do not replace authentication/authorization.
    public interface OrderSearchGateway {
        SearchPage search(String authorizedTenantId, SearchCriteria criteria);
    }

    public interface SearchCriteria {}
    public interface SearchPage {}
}
```

This example intentionally **does not** couple to a specific OpenSearch/Elasticsearch client library. The real adapter must enforce query DSL safety, mandatory tenant filters, paging tokens, timeouts, result caps, allowed search modes, and search-unavailable handling.

In production APIs:

1. `authorizedTenantId` must come from authenticated context, **never blindly trusted from a query-string tenant ID**.
2. `YearMonth` has no timezone; if derived from `Instant created_at`, convert to UTC before computing the bucket.
3. Synchronous `ResultSet` iteration can fetch additional pages automatically. `LIMIT 50` here caps **total rows of the preview query**, not multi-page pagination.
4. For search, cap `pageSize` and filter counts. When the index is mutating, define pagination semantics; never promise an immutable snapshot without an appropriate mechanism.
5. Never automatically fall back from failed search to a **Cassandra full scan**; such fallback can bring down the transactional cluster during a search outage.

### 9.1. Answering When Search Results Need Fresh State

A search API can:

- Return indexed documents alongside update timestamps/freshness indicators aligned with product expectations.
- Fetch `order_id` lists from search, then perform **bounded reads** on `orders_by_id` to verify final state and permissions before returning results or acting.
- If verification finds stale documents, filter out invalid matches and let sync catch up; never promise exactly 30 items if stale entries are filtered without refill logic.

Re-verification adds N lookup costs and still requires clear rules on ordering, paging, and source state. Apply it only to small, bounded result sets—never turn search into a list of millions of IDs to look up in Cassandra.

## 10. Total Cost: Look Beyond the Latency of One SELECT

When weighing another table or auxiliary store, estimate at least four cost categories:

| Cost Category | Questions |
| --- | --- |
| **Read amplification** | How many partitions touched, bytes/tombstones read, and streams merged per request? |
| **Write amplification** | How many mutations/projections/index updates per source change, replicated to how many replicas? |
| **Storage/retention** | How many logical and physical copies, indexes, tombstones, backups, and retained data? |
| **Operational correctness** | How hard are sync lag, partial failures, replays, backfills, deletes, and reconciliation? |

Hypothetical example:

```text
System has 10 million orders
Q05 called 20 times/day
Q07 (PENDING queue) called 2,000 times/minute

If Q05 must scan a large fraction of 10 million orders:
  - even rare calls can consume heavy CPU/I/O each run
  - evaluate search or analytical jobs instead of scanning the transactional source

If Q07 always knows tenant, status, day:
  - a Cassandra projection with a clear read path may be worthwhile
  - measure mutation cost per status change and partition hotspots
```

This example **compares workload structures**; it is not a benchmark or universal threshold. Final decisions require representative testing on the target cluster.

### 10.1. Fan-Out, Tombstones, and `LIMIT`

`LIMIT 50` caps **rows returned** by a CQL query; it does not make a query missing a partition key read only 50 physical rows. Even within a single partition, TTLs, deletes, and updates leave tombstones that force Cassandra to read past non-visible data.

With multi-bucket fan-out, `LIMIT 50` per branch can still produce far more than 50 rows read overall. The API must bound **partition count, intermediate rows/bytes, and duration** before issuing queries, rather than merely trimming results at the end.

### 10.2. Replication/Consistency, Compaction, and Repair

Replication factor determines Cassandra replica count per keyspace configuration. Consistency level governs replica acknowledgments per operation; it neither creates a tenant-wide filter path nor delivers new events to a search index. Compaction affects how SSTables and tombstones are managed; repair maintains consistency across Cassandra replicas, **not** logical consistency between Cassandra and a warehouse.

Adding a new projection table incurs create/delete churn when key columns like status change, compaction overhead, and hot-partition risk. Adding search/analytics shifts cost into indexing, storage, connectors, pipeline failures, security, reconciliation, and freshness SLAs. There is no "free" option.

## 11. Checklist for Choosing Where to Execute a Query

| Decision Question | If the Answer Is... | Direction |
| --- | --- | --- |
| Does the caller know the full partition key? | Yes | Prefer existing Cassandra table |
| Only 2–3 known buckets needed? | Yes, strictly bounded | Bounded fan-out read and merge |
| Stable query shape with high frequency/SLA? | Yes | Consider dedicated projection table |
| Filtering a regular column within a small scope? | Yes | Compare bounded filter / index / dedicated table |
| Need text relevance, facets, and arbitrary filters? | Yes | Dedicated search engine |
| Need multi-dimensional aggregations over long history? | Yes | OLAP/warehouse or analytical job |
| Need read-your-writes immediately after write? | Yes | Identify source path, freshness, and verification |
| Sensitive or multi-tenant data involved? | Yes | Design authorization, isolation, and retention across copies |
| Is there a durable change source for sync? | Not yet | Do not promise eventual consistency; design events/CDC/backfill |
| Can results be measured and reconciled? | Yes | Set lag SLOs, fault tests, and monitored rollout |

## 12. Mistakes to Avoid

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Allowing large Cassandra scans because the query is rare | One request can spike cluster-wide latency | Cap scope or offload to search/analytics |
| Using `ALLOW FILTERING` to replace a partition key | Unpredictable read load; may be rejected by CQL | Reclassify query shape and benchmark access |
| Creating a Cassandra table for every UI filter | Exploding write amplification and sync complexity | Keep projections for stable patterns; move flexible filters to search |
| Assuming SAI supports every `ORDER BY` | Syntax or performance fails requirements | Verify version, exact queries, and workload |
| Believing `LIMIT 50` makes broad queries safe | Many partitions/tombstones still scanned | Bound fan-out, bytes, time range, and measure |
| Dual-writing Cassandra and search and saying "it'll converge" | Dual-write gaps create permanent drift | Durable events/CDC, retries, and reconciliation |
| Letting old backfill records overwrite newer live revisions | Search/warehouse regresses to stale states | Enforce versioning/sequence and proper checkpoints |
| Using `LOCAL_QUORUM` to "sync" external search | Search still lags behind consumer/index | Measure lag and read source when freshness requires |
| Updating Cassandra while forgetting search deletes | Deleted/unauthorized data stays visible in search | Propagate deletes, retention, and reconcile |
| Falling back to Cassandra scans when search is down | Secondary outage overloads source database | Degrade gracefully; return errors or queue reports |
| Mixing creation-date and payment-date revenue logic | Reports disagree despite healthy pipelines | Lock fact and metric definitions before ETL |

## 13. Practice Exercise

A Java support-ticket management application stores:

```text
tenant_id, ticket_id, requester_id, created_at,
status, priority, title, description, assigned_team, revision
```

APIs needed:

1. **R1:** View one ticket by ID — frequent query, needs fresh data.
2. **R2:** View 30 tickets for a requester in a UTC month, newest first.
3. **R3:** A few times a day, team leads view a requester's tickets across up to two months.
4. **R4:** Search keywords in title/description, filter by multiple statuses/priorities/teams, and sort by relevance.
5. **R5:** Report average resolution time by team and month over three years.
6. **R6:** Continuously open queue of 50 `OPEN` tickets for a tenant/day with low latency SLA.

**Tasks:**

1. Propose Cassandra tables and partition/clustering keys for R1/R2.
2. Explain why R3 can use bounded fan-out without immediately needing a new table; specify bucket limits and pagination handling.
3. Compare R4 vs. R6: which fits a search engine and which merits evaluating a Cassandra projection? State load/hot-partition caveats.
4. For R5, choose an OLAP/warehouse approach and clearly define which start and end milestones measure "resolution time."
5. Sketch a pipeline keeping Cassandra as transactional source while feeding search and warehouse, including out-of-order/duplicate revisions, deletes, and backfill steps.
6. A ticket's `priority` is updated in Cassandra at 10:00 but search receives it at 10:00:05. Explain what kind of consistency this is and why raising `LOCAL_QUORUM` on Cassandra reads does not eliminate that 5-second delay.
7. Describe at least three reconciliation checks before declaring the new search store ready: ID/revision, tenant ACL, deletes, and filter/aggregation accuracy.

**Reference guidance:** R1 uses partition key `(tenant_id, ticket_id)`; R2 uses `(tenant_id, requester_id, month_bucket)` and clustering `(created_at DESC, ticket_id DESC)`. R3 can read up to two known monthly buckets and merge with result caps. R4 needs full-text search plus flexible filters; R6 may need `(tenant_id, status, day_bucket)`, provided the largest tenant is sized and key transitions on status changes are handled. R5 fits an analytics store with precisely defined events/facts; SQL alone does not make metrics accurate. Delayed search updates represent **projection lag**, not replica lag within one Cassandra partition; implement freshness SLOs, retries, versioning, and reconciliation.

## Conclusion

Infrequent secondary queries should neither automatically trigger a new Cassandra table nor be allowed unbounded scans merely because few users invoke them. Choose execution homes based on **partition-routing inputs, fan-out limits, filter/sort/aggregation needs, SLAs, and freshness**. Cassandra excels at well-keyed access paths; small bounded fan-out handles many secondary queries; search indexes power flexible discovery; analytics stores power historical aggregations. When copying data to external systems, the architecture is complete only when **durable change sources, versioning, retries, backfills, reconciliation, security, and deletion policies** are proven against realistic data and load.
