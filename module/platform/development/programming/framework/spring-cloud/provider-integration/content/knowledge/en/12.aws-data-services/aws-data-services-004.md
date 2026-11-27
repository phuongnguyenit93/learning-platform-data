# Distinguishing Query and Scan in Access Pattern Design

## 1. Context and Objectives

In the **Spring Cloud Provider Integration** module, Spring Boot connects to managed services on AWS, Azure, and Google Cloud via their respective SDKs and Spring Cloud libraries. In the **AWS Data Services** chapter, Amazon DynamoDB is the AWS-managed NoSQL database. Choosing the right read operation directly impacts **latency, service call counts, read costs, scalability, and tenant data isolation**.

Two operations commonly confused are **`Query`** and **`Scan`**:

- `Query` reads a set of items using the **partition key** of a table or secondary index; optional conditions can be added on the **sort key**.
- `Scan` sweeps through items in a table or index without a key condition; any filter, if supplied, is applied **after the data has been read**.

After this lesson, you will be able to:

1. Choose `GetItem`, `Query`, or `Scan` from a concrete access pattern.
2. Design partition keys, sort keys, and GSIs to avoid Scans in high-frequency business APIs.
3. Explain `KeyConditionExpression`, `FilterExpression`, `ProjectionExpression`, `Limit`, `Count`, and `ScannedCount` accurately.
4. Estimate the cost/latency impact of Query vs. Scan, even when a filter returns only a few items.
5. Implement Query/Scan with AWS SDK for Java v2, integrate into a Spring Boot repository, and understand the version-dependent role of Spring Cloud AWS.
6. Paginate using `LastEvaluatedKey` / `ExclusiveStartKey`, govern legitimate Scans, and test using DynamoDB Local.

> **Scope:** These principles are specific to DynamoDB and do not apply verbatim to queries in Azure Cosmos DB or Google Cloud Firestore. When designing multi-cloud systems, keep business interfaces stable while implementing adapters tailored to each provider's partitioning and indexing model.

## 2. Starting from Access Patterns

DynamoDB is built to look up data by keys and predictable queries. Therefore, data modeling should start with **what callers need to retrieve, which values they know at request time, how large results can grow, and how often queries run**.

Suppose a service manages reservations for multiple companies:

| Attribute | Example | Role |
| --- | --- | --- |
| `tenantId` | `tenant-a` | Partition key of table `reservation_record` |
| `sortKey` | `RES#2026-11-24T08:00:00.000Z#res-1001` | Table sort key; supports chronological listing |
| `reservationId` | `res-1001` | Business reservation identifier |
| `propertyId` | `house-99` | Associated property |
| `propertyKey` | `tenant-a#house-99` | Partition key of GSI `by-property` |
| `createdAt` | `2026-11-24T08:00:00.000Z` | Sort key of GSI `by-property` |
| `state` | `CONFIRMED` | Reservation status |

The table has a **composite primary key** `(tenantId, sortKey)`. GSI `by-property` has key `(propertyKey, createdAt)`. All timestamps in String keys are normalized to **UTC with millisecond precision** so lexicographical order matches chronological order.

Four business questions lead to different choices:

| Requirement | Known caller keys | Appropriate mechanism | Why |
| --- | --- | --- | --- |
| Fetch a specific known reservation | `tenantId` and full `sortKey` | `GetItem` | Uniquely pinpoints a single item |
| Fetch a tenant's November reservations | `tenantId`, prefix `RES#2026-11` | Table `Query` | Exact partition key match + sort key prefix |
| Fetch reservations for a property | `tenantId`, `propertyId` | GSI `by-property` `Query` | Index has partition key `tenantId#propertyId` |
| Periodically audit the entire table for invalid data | No specific key known | Bounded, batched `Scan` | Intentional administrative task requiring broad traversal |

A query knowing only `reservationId` without the timestamp **cannot invoke `GetItem` directly under this model**. You can redesign the key, add a lookup item, or add a dedicated GSI. Never solve it by issuing a Scan on every request.

~~~mermaid
flowchart TD
    A["Access requirement"] --> B{"Know both PK and SK?"}
    B -->|"Yes, 1 item"| C["GetItem"]
    B -->|"No"| D{"Know table or index PK?"}
    D -->|"Yes"| E["Query by key<br/>+ sort key condition if needed"]
    D -->|"No"| F{"Can create index/lookup?"}
    F -->|"Yes"| G["Design index/lookup<br/>then Query"]
    F -->|"No, intentional full traversal"| H["Bounded, monitored Scan"]
~~~

## 3. How Does `Query` Actually Work?

### 3.1. Key Conditions Locate the Data

A `Query` against a table or index requires **an equality (`=`) condition on the exact partition key of the target being queried**. If a sort key exists, you may add one condition:

- `=`, `<`, `<=`, `>`, `>=`;
- `BETWEEN :from AND :to` (inclusive on both ends);
- `begins_with(sortKey, :prefix)` for **String or Binary sort keys**, not applicable to Number.

Table Query example:

~~~sql
tenantId = :tenant AND begins_with(sortKey, :monthPrefix)
-- :tenant      = "tenant-a"
-- :monthPrefix = "RES#2026-11"
~~~

This condition means "read items for `tenant-a` whose sort key starts with `RES#2026-11`". To query GSI `by-property`, switch to **the index's** keys:

~~~sql
propertyKey = :property AND begins_with(createdAt, :monthPrefix)
-- :property    = "tenant-a#house-99"
-- :monthPrefix = "2026-11"
~~~

You cannot put `propertyId = :id` in `KeyConditionExpression` if `propertyId` is only a regular attribute. Likewise, you cannot execute `Query` without a partition key condition.

### 3.2. Result Ordering and Size

`Query` returns results ordered by the **sort key of the table/index**. Number sort keys sort numerically; String sort keys sort by UTF-8 bytes. `ScanIndexForward=true` returns ascending order (default), while `false` reverses it. This ordering applies strictly **within the queried partition key**.

A single `Query` call processes up to **1 MB of data before filtering/projection**, or stops earlier if `Limit` is reached. If more data remains, the response includes `LastEvaluatedKey` to continue reading. Thus, a `Query` on a tenant with millions of items **can still be very expensive** if the application iterates through every page.

**Remember:** `Query` is generally much more efficient than `Scan` for a given access pattern, but actual efficiency depends on key condition selectivity, item size, page count, and traffic concentration on the partition key.

## 4. How Does `Scan` Actually Work?

### 4.1. Scan Reads Broadly

`Scan` examines items across the **entire table or entire secondary index** page by page. DynamoDB does not use a `KeyConditionExpression` to narrow a Scan to a single partition key.

Example request:

~~~sql
-- This is a Scan filter, NOT a KeyConditionExpression:
state = :expected
-- :expected = "CONFIRMED"
~~~

DynamoDB must **read the items in the scanned slice first and then apply the filter**. If a table has 500,000 items and only 200 are `CONFIRMED`, the filter does not let DynamoDB jump straight to those 200 items.

A single Scan reads up to **1 MB before filtering** or the number of items evaluated per `Limit`; reading the entire table requires multiple requests until `LastEvaluatedKey` is absent. `Scan` does not guarantee global ascending key order across the table like querying a single partition key does.

### 4.2. `Count` and `ScannedCount`

In a Scan response:

- `ScannedCount`: number of items DynamoDB **evaluated** in the request, before filtering.
- `Count`: number of items **remaining after filtering** in the request.
- `Items`: the items returned after filter/projection.
- `LastEvaluatedKey`: marker to continue, if more data remains to be scanned.

Suppose a page reads 100 items, of which only 3 satisfy the condition:

~~~text
ScannedCount = 100
Count        = 3
LastEvaluatedKey = { ... }    # More data may remain
~~~

Filter selectivity on this page is `3 / 100 = 3%`. When Scans run frequently, this is a strong signal to revisit your access pattern design. `Count` and `ScannedCount` reflect only **the current page**; sum across pages to measure a full scan.

### 4.3. When Does Scan Make Sense?

Scan can be reasonable for:

- One-off operational tasks: backfills, data audits, migrations, schema reconciliation.
- Periodic jobs that cannot be modeled via keys/indexes and run during off-peak hours.
- Small datasets with very low query volume where cost/latency have been measured.
- Administrative/investigative tools with strict quotas, permissions, and rate limits.

Do not make Scan the default path for high-frequency list views or high-scale self-serve APIs. If you must Scan a large table, favor asynchronous jobs with checkpoints, rate limiting, backoff retries, and metrics; never scan the entire table inside a single HTTP request and hold the connection open.

## 5. Comparing Query and Scan as Engineering Decisions

| Criterion | `Query` | `Scan` |
| --- | --- | --- |
| Required condition | `partitionKey = value` | No key required |
| Sort key | Supports range, prefix, or comparison | No key condition narrowing |
| Read scope | Items matching key condition on table/index | Traverses full table/index across pages unless stopped |
| `FilterExpression` | Applied after items matching key condition are read | Applied after items in the Scan page are read |
| `ProjectionExpression` | Selects returned attributes; does not cut table read RCU | Selects returned attributes; does not cut table read RCU |
| Ordering | Ordered by sort key within queried partition key | No useful global table ordering |
| Pagination | `LastEvaluatedKey` → `ExclusiveStartKey` | Same mechanism; typically many more pages |
| `Limit` | Max items evaluated before filtering per request | Max items evaluated before filtering per request |
| 1 MB/request | Yes | Yes |
| Consistency | Strong on table/LSI if requested; GSI eventual | Strong on table/LSI if supported, **does not form a full-Scan snapshot**; GSI eventual |
| Parallel read | Can issue multiple key Queries from app layer | Supports **parallel Scan** via `Segment`/`TotalSegments` |
| When to use | Business APIs with designed keys/indexes | Backfills, audits, intentional bulk data sweeps |

**Common misconceptions:** "a filtered Scan only consumes capacity for the few returned items" and "Query is always cheap". Both are false. Read cost depends on **data processed by DynamoDB**, consistency mode, item/index sizes, and request frequency. Filters only shrink the payload sent back to the client; an unselective Query can also read many megabytes across multiple pages.

## 6. `KeyCondition`, `FilterExpression`, and `ProjectionExpression`

### 6.1. Three Clauses with Distinct Roles

~~~mermaid
flowchart LR
    A["Table / Index"] --> B["Narrow scope by key<br/>Query: PK=... and SK...<br/>Scan: sweep"]
    B --> C["Read data page<br/>up to 1 MB / Limit"]
    C --> D["Apply FilterExpression"]
    D --> E["Return only Projected attributes"]
    E --> F["Items + LastEvaluatedKey"]
~~~

- **Key condition:** applies only to `Query`, using the partition key and optionally the sort key. This is what **reduces how much data must be read**.
- **Filter expression:** usable with Query or Scan; filters after items have already been read. A Query filter **cannot reference primary key attributes of the queried table/index**; key conditions belong in key condition expressions.
- **Projection expression:** asks DynamoDB to return specific fields. This reduces network bytes and client memory; it **does not automatically lower read capacity** on table queries because DynamoDB has already read the items.
- **GSI projection:** a GSI stores only projected attributes (along with required keys); a GSI Query reads based on the index item size, which can save capacity when the index is smaller than the base table. A GSI does not automatically fetch unprojected attributes from the base table. Choose projections carefully when designing the index.

### 6.2. "Filter Matches Only 2%" Is an Access Pattern Problem

Suppose `GET /reservations?state=CONFIRMED` is called hundreds of times per second on a table with millions of items, and `state` is not part of any table/index key. Two approaches:

**Option A — Scan + filter:**

~~~text
Scan reservation_record
FilterExpression: state = "CONFIRMED"
~~~

Each API call may traverse many pages and burn substantial read capacity. Response latency degrades as data grows and can starve other workloads.

**Option B — Design for the access pattern:**

~~~text
GSI by-tenant-state-time
  partition key: tenantStateKey = tenantId + "#STATE#" + state
  sort key:      createdAt
Query index with tenantStateKey = "tenant-a#STATE#CONFIRMED"
~~~

The new Query reads only items matching the index key and returns them sorted by time. The trade-off is additional index storage, extra index writes when state changes, and GSI eventual consistency. Proper design also requires evaluating cardinality, hot keys, and tenant authorization.

**No single design fits every system.** If a status report runs once nightly over a small dataset, a quota-limited Scan may be simpler than maintaining an extra index. If the query is a core product feature, an index, aggregate, or materialized view is usually worth it.

## 7. Estimating Cost and Latency Rigorously

### 7.1. Returned Item Count Does Not Reflect Total Read Work

Consider a hypothetical scenario:

- The table holds about **200,000 reservations**, each ~1 KB.
- Tenant `tenant-a` has 500 reservations in November.
- The UI shows the **20 most recent reservations** for a tenant and month.
- Some items have `state=CONFIRMED`, though `state` is not in any key or index.

| Approach | Data DynamoDB must examine | What the user receives |
| --- | --- | --- |
| `Query` PK=tenant-a + sort key prefix, reversed, first page | Items strictly in that tenant/month key range | Up to one page of matching items |
| `Query` then filter state | Same key condition range; filter applied after read | May be under 20 items; next page needed if key remains |
| Full-table `Scan` then filter tenant/month/state | Potentially many pages across a huge volume of data | Might also return 20 items after reading thousands |

Exact RCU cannot be deduced from these numbers without knowing actual item sizes, consistency mode, page count, and query execution details. As a foundational rule: DynamoDB measures read capacity in **4 KB** blocks and by consistency type; for an equivalent payload, eventual consistency typically consumes about **half** the read capacity of strong consistency. Scanning 1 MB can consume substantial read capacity in a single request. Measure against sample data instead of guessing bills from returned item counts.

### 7.2. Metrics to Measure

For each request type, record:

- **End-to-end latency** and DynamoDB request latency.
- **Consumed capacity** (`ReturnConsumedCapacity=TOTAL` or `INDEXES` where supported), broken down by table and index.
- **Evaluated items** `ScannedCount` vs. **returned items** `Count`; inspect per page and sum across the whole operation.
- **Page count**, total response bytes, and total completion time.
- **Throttling**, retries, timeouts, and failed request counts.
- Key dispersion and traffic concentration on hot partitions/indexes.

A Query with `ScannedCount=10` and `Count=10` shows no items discarded by filters, whereas a Scan with `ScannedCount=10000` and `Count=12` signals a design issue. Always interpret these metrics in the context of access patterns, dataset size, and request rate.

## 8. Spring Boot Example: Entity Mapping and Enhanced Client

### 8.1. Dependencies and Auto-Configuration

In Spring Boot, you can choose **Spring Cloud AWS (AWSpring)** with its DynamoDB starter or configure **AWS SDK for Java v2** directly.

~~~xml
<!-- When using AWSpring: choose a BOM compatible with your Spring Boot version -->
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-dynamodb</artifactId>
</dependency>
~~~

With plain SDK v2, add the dependencies managed by the AWS SDK BOM:

~~~xml
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>dynamodb</artifactId>
</dependency>
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>dynamodb-enhanced</artifactId>
</dependency>
~~~

`DynamoDbTemplate` is an abstraction provided in Spring Cloud AWS versions that support it. Its API is not identical to the Enhanced Client, nor is it a Spring Data JPA repository. Here we use the Enhanced Client directly to keep Query/Scan, expressions, indexes, and page boundaries transparent. If the starter provides a `DynamoDbEnhancedClient` bean, inject it; with plain SDK, configure the client manually using the credential provider chain.

### 8.2. Entity Matching the Table and GSI

~~~java
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbBean;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbPartitionKey;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbSortKey;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbSecondaryPartitionKey;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbSecondarySortKey;

@DynamoDbBean
public class ReservationItem {
    private String tenantId;
    private String sortKey;
    private String reservationId;
    private String propertyKey;
    private String createdAt;
    private String state;

    public ReservationItem() {}

    @DynamoDbPartitionKey
    public String getTenantId() { return tenantId; }
    public void setTenantId(String value) { tenantId = value; }

    @DynamoDbSortKey
    public String getSortKey() { return sortKey; }
    public void setSortKey(String value) { sortKey = value; }

    public String getReservationId() { return reservationId; }
    public void setReservationId(String value) { reservationId = value; }

    @DynamoDbSecondaryPartitionKey(indexNames = "by-property")
    public String getPropertyKey() { return propertyKey; }
    public void setPropertyKey(String value) { propertyKey = value; }

    @DynamoDbSecondarySortKey(indexNames = "by-property")
    public String getCreatedAt() { return createdAt; }
    public void setCreatedAt(String value) { createdAt = value; }

    public String getState() { return state; }
    public void setState(String value) { state = value; }
}
~~~

Annotated getters belong to **Enhanced Client**; public getters/setters and a no-arg constructor are required. Annotations declare mapping metadata and **do not create tables or indexes**. `sortKey` and `propertyKey` must be populated consistently by the service when writing items.

### 8.3. Repository for Table Query, GSI Query, and Scan

~~~java
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Repository;

import software.amazon.awssdk.enhanced.dynamodb.DynamoDbEnhancedClient;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbTable;
import software.amazon.awssdk.enhanced.dynamodb.Key;
import software.amazon.awssdk.enhanced.dynamodb.TableSchema;
import software.amazon.awssdk.enhanced.dynamodb.model.Page;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryConditional;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryEnhancedRequest;
import software.amazon.awssdk.enhanced.dynamodb.model.ScanEnhancedRequest;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;

@Repository
public class ReservationReadRepository {
    private final DynamoDbTable<ReservationItem> table;

    public ReservationReadRepository(DynamoDbEnhancedClient client) {
        this.table = client.table(
                "reservation_record",
                TableSchema.fromBean(ReservationItem.class));
    }

    public record ReadPage(
            List<ReservationItem> items,
            Map<String, AttributeValue> nextKey) {}

    // Query exact tenant and month prefix on the base table.
    public ReadPage queryMonth(String tenantId, String yyyyMM,
            Map<String, AttributeValue> startKey) {
        QueryEnhancedRequest.Builder request =
                QueryEnhancedRequest.builder()
                        .queryConditional(QueryConditional.sortBeginsWith(
                                Key.builder()
                                        .partitionValue(tenantId)
                                        .sortValue("RES#" + yyyyMM)
                                        .build()))
                        .scanIndexForward(false)
                        .limit(20);
        if (startKey != null && !startKey.isEmpty()) {
            request.exclusiveStartKey(startKey);
        }
        Iterator<Page<ReservationItem>> pages =
                table.query(request.build()).iterator();
        return pages.hasNext()
                ? toPage(pages.next())
                : new ReadPage(List.of(), null);
    }

    // Query the GSI using the INDEX key, not the base table key.
    public ReadPage queryProperty(String propertyKey,
            Map<String, AttributeValue> startKey) {
        QueryEnhancedRequest.Builder request =
                QueryEnhancedRequest.builder()
                        .queryConditional(QueryConditional.keyEqualTo(
                                Key.builder()
                                        .partitionValue(propertyKey)
                                        .build()))
                        .limit(20);
        if (startKey != null && !startKey.isEmpty()) {
            request.exclusiveStartKey(startKey);
        }
        Iterator<Page<ReservationItem>> pages = table
                .index("by-property")
                .query(request.build())
                .iterator();
        return pages.hasNext()
                ? toPage(pages.next())
                : new ReadPage(List.of(), null);
    }

    // Intended strictly for controlled admin/batch jobs.
    public ReadPage scanOnePage(
            Map<String, AttributeValue> startKey) {
        ScanEnhancedRequest.Builder request =
                ScanEnhancedRequest.builder().limit(20);
        if (startKey != null && !startKey.isEmpty()) {
            request.exclusiveStartKey(startKey);
        }
        Iterator<Page<ReservationItem>> pages =
                table.scan(request.build()).iterator();
        return pages.hasNext()
                ? toPage(pages.next())
                : new ReadPage(List.of(), null);
    }

    private static ReadPage toPage(Page<ReservationItem> page) {
        return new ReadPage(
                List.copyOf(page.items()),
                page.lastEvaluatedKey());
    }
}
~~~

**Purpose of single-page methods:** the iterable returned by `query(...)` or `scan(...)` lazy-loads subsequent pages. Calling `pages.next()` exactly once ensures the repository returns **one DynamoDB page**, avoiding accidental full-dataset traversal inside an HTTP request. `limit(20)` only caps the number of items **evaluated in a single request**; it does not guarantee every page returns 20 items (especially with filters) or represent the total result size.

Before calling `queryMonth`, validate `yyyyMM` at the API layer (e.g., `YearMonth.parse(value)`); otherwise the prefix may be malformed or overly broad. Before calling `queryProperty`, construct `propertyKey` from the authenticated tenant and a validated property ID—never accept it raw from the client.

**`scanOnePage` in this repository illustrates single-page scanning only**, not a recommendation to expose a public `GET /all` endpoint. If you need to scan the whole table, build a controlled worker/job rather than looping through all pages inside a controller.

### 8.4. When You Need to Inspect `ScannedCount` and Consumed Capacity

The low-level AWS SDK v2 client exposes these fields directly. Here is a controlled example comparing Filter vs. Scan:

~~~java
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.ReturnConsumedCapacity;
import software.amazon.awssdk.services.dynamodb.model.ScanRequest;
import software.amazon.awssdk.services.dynamodb.model.ScanResponse;

public class ScanDiagnostics {
    private final DynamoDbClient client;

    public ScanDiagnostics(DynamoDbClient client) {
        this.client = client;
    }

    public void inspectOnePage() {
        ScanRequest request = ScanRequest.builder()
                .tableName("reservation_record")
                .filterExpression("#status = :state")
                .expressionAttributeNames(Map.of("#status", "state"))
                .expressionAttributeValues(Map.of(
                        ":state", AttributeValue.builder()
                                .s("CONFIRMED").build()))
                .limit(50)
                .returnConsumedCapacity(ReturnConsumedCapacity.TOTAL)
                .build();

        ScanResponse response = client.scan(request);
        System.out.println("ScannedCount = " + response.scannedCount());
        System.out.println("Count = " + response.count());
        System.out.println("ConsumedCapacity = "
                + response.consumedCapacity());
        System.out.println("HasMore = "
                + !response.lastEvaluatedKey().isEmpty());
    }
}
~~~

This is **diagnostic code for a single page**; if only 2 items are `CONFIRMED` among 50 evaluated items, `ScannedCount` is still 50. Never leave `System.out.println` or customer data in production logs; use metrics and logging with sensitive fields redacted.

## 9. Pagination: `Limit` Does Not Mean "Read Only N Matching Results"

### 9.1. Both Operations Share the Same Flow

Both Query and Scan can return `LastEvaluatedKey`. The next request keeps the exact same query context/conditions and sets `ExclusiveStartKey` to the returned key map.

~~~mermaid
sequenceDiagram
    participant UI as Client
    participant API as Spring Boot
    participant DB as DynamoDB
    UI->>API: GET /reservations?tenant=...&pageSize=20
    API->>DB: Query key condition + Limit=20
    DB-->>API: Items + LastEvaluatedKey
    API-->>UI: Items + nextCursor
    UI->>API: GET /reservations?cursor=...
    API->>DB: Query same condition + ExclusiveStartKey
    DB-->>API: Items + LastEvaluatedKey or empty
    API-->>UI: Items + nextCursor or null
~~~

If the response **has no `LastEvaluatedKey`** (or the map is empty), the read has reached the end at that moment. If the key is present, more data may remain. A page returning **0 items** can still include a next key when filters are active; never treat `items.isEmpty()` or `items.size() < limit` as end-of-results.

DynamoDB does not provide a consistent snapshot across paginated requests. If items are inserted, deleted, or re-keyed while the client advances pages, results can diverge from page 1's point in time. Even a Scan with `ConsistentRead=true` does not turn multi-page traversal into a transactional snapshot.

### 9.2. Designing Public Cursors

`ReadPage.nextKey` is an internal AWS SDK map. Public APIs should return an opaque `nextCursor` and validate:

- The cursor belongs to the **authenticated tenant**, table/index, key condition, filter, sort direction, and page size.
- The token includes a version, expiration, and **HMAC signature** or authenticated encryption; Base64 is only an encoding and **does not prevent tampering**.
- For GSI queries, preserve the **complete returned key map**; do not reconstruct a cursor with only the partition key and drop base-table/index keys.
- Reject unknown, expired, or parameter-mismatched cursors, bound token size, and avoid leaking sensitive values in logs.
- Return a clear error instructing the client to restart when a token is no longer valid.

Example API payload (the token is just a placeholder):

~~~json
{
  "items": [
    {"reservationId":"res-1001","state":"CONFIRMED"}
  ],
  "nextCursor": "opaque-signed-token-from-server"
}
~~~

If business rules require returning **a full 20 items after filtering**, you may need to fetch and aggregate multiple DynamoDB pages. Bound **request count, read budget, and elapsed time**; never loop indefinitely just to fill a page. A better solution for common queries is **designing a selective GSI** to reduce the number of items read.

## 10. Parallel Scan: When Needed and What to Avoid

DynamoDB supports splitting a Scan into segments using `Segment` and `TotalSegments`, allowing multiple workers to process distinct segments concurrently. Parallel Scan is useful in high-volume batch jobs, however:

- It can **accelerate read capacity consumption** without reducing total data read.
- It can cause contention or throttling for business traffic sharing the same table or GSI.
- Each segment must maintain its **own** `LastEvaluatedKey` checkpoint; `ExclusiveStartKey` applies only within that exact segment.
- Do not use it to power arbitrary user-facing pagination APIs or to globally sort table results.
- Changing `TotalSegments` mid-run requires a clean restart/re-sharding strategy; never mix cursors across segment configurations.
- Concurrency caps, backoff with jitter, queue/batch windows, metrics, and crash recovery checkpoints are typically needed.

Low-level SDK v2 example for **one segment page**:

~~~java
import software.amazon.awssdk.services.dynamodb.model.ScanRequest;
import software.amazon.awssdk.services.dynamodb.model.ScanResponse;

int totalSegments = 4;
int segmentNumber = 0; // Each worker handles one value in 0..3.

ScanResponse page = client.scan(ScanRequest.builder()
        .tableName("reservation_record")
        .totalSegments(totalSegments)
        .segment(segmentNumber)
        .limit(100)
        .build());

// Only the worker for segmentNumber may reuse page.lastEvaluatedKey().
~~~

`client` above is `DynamoDbClient`; this snippet illustrates segment configuration only and does not implement the full job, checkpointing, or retry loop. Only adopt parallel Scan after measuring and confirming that a full table/index sweep is genuinely required.

## 11. IAM, Tenant Security, and Deployment Environments

### 11.1. Grant Only Required Permissions

For a repository using Query on the table and GSI:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["dynamodb:Query", "dynamodb:GetItem"],
      "Resource": [
        "arn:aws:dynamodb:ap-southeast-1:123456789012:table/reservation_record",
        "arn:aws:dynamodb:ap-southeast-1:123456789012:table/reservation_record/index/by-property"
      ]
    }
  ]
}
~~~

Substitute region, account, table, and index for your real environment. For Scan jobs, add `dynamodb:Scan` **only on the required resources**, ideally under a dedicated role. Never grant Scan permissions to user-facing APIs just for convenience.

The application must verify tenant IDs from authenticated tokens/identities; never trust a `tenantId` or `propertyKey` supplied freely by the client. You can evaluate IAM conditions like `dynamodb:LeadingKeys` when your identity/partitioning model permits, while still enforcing business-level authorization. Never log credentials, sensitive data, raw cursors, or full customer items.

### 11.2. Region, Credentials, and Local Endpoint Configuration

In AWS, attach an IAM role to the workload (ECS task, EC2 instance, EKS pod identity/IRSA as appropriate); the AWS SDK and AWSpring use the credentials provider chain. Example AWSpring configuration in supported versions:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
~~~

Test locally with DynamoDB Local:

~~~bash
docker run --rm -p 8000:8000 amazon/dynamodb-local:latest
~~~

~~~yaml
# application-local.yml (for AWSpring versions supporting this property)
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
      dynamodb:
        endpoint: http://localhost:8000
~~~

Set dummy credentials (e.g., `AWS_ACCESS_KEY_ID=local`, `AWS_SECRET_ACCESS_KEY=local`) in your local terminal to sign requests; never use dummy credentials on real AWS. If configuring `DynamoDbClient` manually with the plain SDK, configure `endpointOverride(URI.create("http://localhost:8000"))` directly, because AWSpring properties do not apply automatically to manually built clients.

## 12. Hands-On Comparison of Query and Scan on DynamoDB Local

### 12.1. Creating the Table and Sample Data

Create the table with a composite primary key and GSI:

~~~bash
aws dynamodb create-table \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name reservation_record \
  --attribute-definitions \
    AttributeName=tenantId,AttributeType=S \
    AttributeName=sortKey,AttributeType=S \
    AttributeName=propertyKey,AttributeType=S \
    AttributeName=createdAt,AttributeType=S \
  --key-schema \
    AttributeName=tenantId,KeyType=HASH \
    AttributeName=sortKey,KeyType=RANGE \
  --global-secondary-indexes \
    '[{"IndexName":"by-property","KeySchema":[{"AttributeName":"propertyKey","KeyType":"HASH"},{"AttributeName":"createdAt","KeyType":"RANGE"}],"Projection":{"ProjectionType":"ALL"}}]' \
  --billing-mode PAY_PER_REQUEST
~~~

Insert a reservation:

~~~bash
aws dynamodb put-item \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name reservation_record \
  --item '{
    "tenantId":{"S":"tenant-a"},
    "sortKey":{"S":"RES#2026-11-24T08:00:00.000Z#res-1001"},
    "reservationId":{"S":"res-1001"},
    "propertyKey":{"S":"tenant-a#house-99"},
    "createdAt":{"S":"2026-11-24T08:00:00.000Z"},
    "state":{"S":"CONFIRMED"}
  }'
~~~

Add several more items across different tenants, months, `state` values, and `propertyKey` values so you can observe Query hitting only matching keys while Scan reads broadly. With only one record, comparisons will not reflect cost differences.

### 12.2. Querying with the CLI

**Query by table key:**

~~~bash
aws dynamodb query \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name reservation_record \
  --key-condition-expression 'tenantId = :t AND begins_with(sortKey, :p)' \
  --expression-attribute-values '{
    ":t":{"S":"tenant-a"},
    ":p":{"S":"RES#2026-11"}
  }' \
  --limit 20 \
  --return-consumed-capacity TOTAL \
  --no-paginate
~~~

**Query GSI by property:**

~~~bash
aws dynamodb query \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name reservation_record \
  --index-name by-property \
  --key-condition-expression 'propertyKey = :p' \
  --expression-attribute-values '{
    ":p":{"S":"tenant-a#house-99"}
  }' \
  --limit 20 \
  --return-consumed-capacity TOTAL \
  --no-paginate
~~~

**Scan with filter:**

~~~bash
aws dynamodb scan \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name reservation_record \
  --filter-expression '#s = :s' \
  --expression-attribute-names '{"#s":"state"}' \
  --expression-attribute-values '{":s":{"S":"CONFIRMED"}}' \
  --limit 20 \
  --return-consumed-capacity TOTAL \
  --no-paginate
~~~

Inspect `Count`, `ScannedCount`, `ConsumedCapacity`, and `LastEvaluatedKey`. Depending on item count and limit, you may not see a next key yet; add more items and use a smaller limit to practice pagination. The AWS CLI has **its own auto-pagination mechanism**; `--no-paginate` is used here so you can inspect the single-call service response clearly. Do not confuse the CLI's `--starting-token` with DynamoDB's `ExclusiveStartKey` map.

### 12.3. Spring Boot Integration Test Scenarios

A thorough test suite should verify:

1. **Correct key:** Querying `tenant-a` with the November prefix returns only items for that tenant/month, never `tenant-b`.
2. **Correct index:** Querying `by-property` returns only items with the matching `propertyKey`. Immediately after a write, GSI queries may require bounded polling due to eventual consistency.
3. **Post-read filtering:** Scanning with a filter returns few items; verify `ScannedCount >= Count` and reflects the difference.
4. **Pagination:** fetch a page with a small limit, capture `LastEvaluatedKey`, and pass it as `ExclusiveStartKey` with identical parameters; verify no missed or duplicate items on a static test set.
5. **Empty page:** use a non-matching filter on enough items to produce a next key; confirm the API does not terminate simply because a page is empty.
6. **Tenant isolation:** the API rejects another tenant's token/cursor; verify tenant scope is enforced before Query/Scan runs.
7. **Throttling/capacity:** as dataset size increases, measure page count, RCU, retries, and latency; never run unbounded load tests against production tables.

Tests use JUnit 5/Spring Boot Test and DynamoDB Local or LocalStack via Testcontainers and must actually execute against tables/indexes matching production. Code snippets in this lesson are practice guides, **not evidence that tests have been run**.

## 13. Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Query throws `ValidationException` | Missing `partitionKey = value` or non-key attribute placed in key condition | Use the target table/index PK; put non-key predicates in a filter or design an index |
| Query returns no items | Wrong tenant, sort prefix, region, endpoint, or item absent from GSI | Verify schema and data, especially GSI key attributes |
| Scan returns few items but reads many | Low filter selectivity | Evaluate GSI/lookup/aggregate and monitor `ScannedCount` |
| Scan degrades latency of other APIs | Broad reads spike read capacity/throttling | Move to an offline job, throttle rate, or segment carefully |
| Newly written item missing from GSI query | Asynchronous GSI propagation | Redesign read-after-write flows; never assume strong consistency on GSIs |
| Page 1 returns fewer items than limit | Filter or 1 MB page cap applied | Check `LastEvaluatedKey` before assuming end of data |
| Next page cursor fails or returns wrong data | Index, key condition, or sort changed between pages | Bind cursor tokens to the full query context |
| `for (page : query)` makes API slow | SDK lazy-fetches all pages unless stopped | Fetch only one page or enforce explicit read budgets |
| `ResourceNotFoundException` | Table or GSI missing in active account/region/endpoint | Check IaC, table/index names, and `describe-table` |
| `AccessDeniedException` | Role lacks `Query`/`Scan` on the target ARN | Verify least-privilege IAM policy, index ARN, and active role |
| Key data type changed | Schema mapping mismatches table/index | Align Java mapping with AWS schema and run a planned migration |

## 14. Practice Questions and Completion Criteria

1. A table stores 1 million orders, and a UI screen displays the 20 most recent orders for a customer. Choose the partition key/sort key, write `KeyConditionExpression`, and explain why Scan + filter is unsuitable.
2. A service must filter by `state` 500 times/second, yet `state` is not in the key. Compare Scan + Filter against a GSI on tenant-state-time, covering index write cost, latency, and consistency.
3. Populate 100 items and measure individual pages of `Query` and `Scan` using `Count`, `ScannedCount`, and `ConsumedCapacity`. Record observed measurements rather than guessing from displayed item counts.
4. Build a REST endpoint returning `items` + signed `nextCursor`, capped at 20 items per request; ensure a cursor from tenant A cannot be used by tenant B.
5. Implement a Scan job to audit legacy records with rate limiting (requests/sec), per-segment checkpoints, backoff retries, and a summary count of scanned items on completion.
6. Compare implementing "filter by property ID and timestamp" on DynamoDB GSI, Azure Cosmos DB, and Google Cloud Firestore. Identify which business interfaces can be shared and which parts remain provider-specific.

**Self-assessment criteria:** learners can explain why Query is key-based, why Filters do not reduce data read, why Scan requires deliberate intent and quotas, why `Limit` is not the final post-filter item count, and why pagination must follow the exact `LastEvaluatedKey` of the matching query.

## References

- [AWS — Key condition expressions for Query](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.KeyConditionExpressions.html): partition/sort key rules.
- [AWS — Filter expressions for Query](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.FilterExpression.html): post-read filtering and read capacity impact.
- [AWS — Scanning tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Scan.html): Scan, Count, ScannedCount, pagination, and parallel Scan.
- [AWS — Best practices for querying and scanning](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-query-scan.html): performance, RCU, and rate limiting.
- [AWS — Paginating table query results](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.Pagination.html): `LastEvaluatedKey` and `ExclusiveStartKey`.
- [AWS — Global secondary indexes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GSI.html): queries, index projections, and consistency.
- [AWS SDK for Java v2 — DynamoDB Enhanced Client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/dynamodb-enhanced-client.html): repositories, Query/Scan, and mapping.
- [Spring Cloud AWS — Reference documentation](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html): starter and version-specific client configuration.
