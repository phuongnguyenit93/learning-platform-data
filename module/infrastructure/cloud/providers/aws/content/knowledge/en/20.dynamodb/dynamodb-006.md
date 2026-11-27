# Read Consistency and Performance Trade-Offs in Amazon DynamoDB

A Java/Spring Boot application updates an order status via `UpdateItem`, receives a successful response, and then calls `GetItem`. Why does it sometimes still return the old status? If we turn on `ConsistentRead=true` for every read, will the application be accurate in every situation? What about reading from a **Global Secondary Index (GSI)** or **Global Tables**? These questions cannot be solved just by adding more read capacity.

**Read consistency** defines the freshness an application can expect when reading an item. It is distinct from **transaction isolation**, **write contention**, **index propagation**, **cache freshness**, **network latency**, and **RCU/RRU cost**. A correct system must understand its business invariants and select the right consistency level per access pattern.

This lesson belongs to the **DynamoDB** chapter of the **CLOUD_PROVIDERS_AWS** module, connecting to Regions/AZs, IAM, VPC, Lambda/ECS, DynamoDB Global Tables, DAX, CloudWatch, recovery, and cost control. Examples use AWS SDK for Java 2.x and Region `ap-southeast-1`. All tables and IDs are illustrative only.

> **Principle:** A **strongly consistent read** on a **base table/LSI** reflects previously succeeded writes, **but does not lock the item**, does not create a table-wide snapshot, does not make a **GSI** strong, and never replaces **`ConditionExpression`** on updates.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Distinguish **eventual**, **strong**, and **transactional** reads.
2. Explain why DynamoDB defaults to eventual reads, and when to choose strong reads.
3. Know which consistency levels are supported by base tables, **LSIs**, **GSIs**, **Streams**, DAX, and Global Tables.
4. Use `ConsistentRead` in `GetItem`, `Query`, `Scan`, and `BatchGetItem`.
5. Explain `TransactGetItems` and the limits of atomic multi-item reads.
6. Calculate **RCU/RRU read capacity per 4 KiB block** for eventual, strong, and transactional reads.
7. Understand the impact of `FilterExpression`, `ProjectionExpression`, `Limit`, pagination, and hot partitions.
8. Distinguish Global Tables **MREC** and **MRSC** in current AWS offerings.
9. Design read-after-write flows, cache/consistency strategies, optimistic concurrency, and transactional updates.
10. Write Java SDK v2 code, read-only AWS CLI checks, and measure CloudWatch metrics.
11. Balance correctness, latency, throughput, availability, and total cost.
12. Separate stale reads, throttling, index lag, and application bugs during troubleshooting.

## 2. Why Can a Read Return Stale Data After DynamoDB Confirmed a Write?

A `PutItem`/`UpdateItem`/`DeleteItem` returning success means DynamoDB has **durably committed** the change. However, default reads can hit a replica that has not yet finished syncing. DynamoDB provides **read-committed isolation**: a read never returns data from a write that never committed. Read-committed **does not** prevent an item from being modified right after your read.

~~~mermaid
sequenceDiagram
    participant API as Order API
    participant DB as DynamoDB table
    participant E as Eventual read
    participant S as Strong read
    API->>DB: UpdateItem status=PAID
    DB-->>API: Success
    API->>E: GetItem default
    E-->>API: May temporarily see PENDING
    API->>S: GetItem ConsistentRead=true
    S-->>API: PAID (unless a newer write occurred)
~~~

If the client **receives no write response** due to a timeout, that is an **unknown outcome**—not proof the write failed. Use a business request ID, conditional writes, and state queries to prevent double updates.

| Term | Meaning |
|---|---|
| **Durability** | Committed writes are persisted durably |
| **Eventually consistent** | Reads may see an older version briefly before converging |
| **Strongly consistent** | Reads reflect all writes that succeeded before the read within supported scope |
| **Read committed** | Never reads state from an uncommitted or rolled-back write |
| **Transactional/serializable** | Reads multiple items under transaction semantics |
| **Read-after-write** | Guaranteeing subsequent reads reflect a write that just succeeded |
| **Optimistic concurrency** | Updating only if version/state still matches expectation |

There is no fixed SLA such as "GSIs sync in exactly 100 ms" for all cases; never turn average replication lag into a business guarantee.

## 3. Eventually Consistent Reads: Default and Benefits

`GetItem`, `Query`, and `Scan` default to eventual reads, which may return stale data right after a successful write.

~~~text
t0  Order.status = PENDING
t1  UpdateItem(status = PAID) → success
t2  GetItem (eventual)         → may still return PENDING
t3  Read after convergence     → PAID
~~~

This does not mean DynamoDB loses data or that every eventual read is stale. An eventual read **often** returns the latest version immediately; it simply does not **guarantee** the latest version.

When is it suitable? Product catalogs, search listings, near-real-time analytics, homepages, dashboards tolerating brief staleness, and read-heavy traffic needing lower cost.

**Capacity advantage:** For items up to 4 KiB, an eventual read consumes roughly **0.5 read units**, versus **1** for strong. All else equal, you can serve roughly twice as many reads on the same capacity budget.

**Never rely on eventual reads alone** to guard inventory depletion, single-use coupons, unique ticket issuance, or balance deductions. Those workflows require **conditional writes**, optimistic locking, or transactions.

## 4. Strongly Consistent Reads: Freshness, Not Locking

On a **base table** and **Local Secondary Index (LSI)**, set:

~~~text
ConsistentRead = true
~~~

on `GetItem`/`Query`/`Scan` (where supported by the API/target). Strong reads reflect all previously completed writes. They consume roughly **twice the read units** of eventual reads for the same item size and can exhibit different latency.

### 4.1. Strong Reads Do Not Prevent Lost Updates

~~~text
1. Worker A GetItem(strong) → stock=1
2. Worker B GetItem(strong) → stock=1
3. A UpdateItem(stock=0)
4. B UpdateItem(stock=0)
~~~

Both workers read the freshest value **at read time**, yet reading does not lock the item. If both workers issue a ticket from `stock=1`, business correctness is broken.

The fix is an atomic conditional update:

~~~text
UpdateItem:
  UpdateExpression: SET stock = stock - :q, version = version + :one
  ConditionExpression: stock >= :q AND version = :expected
~~~

Or a multi-item transaction when needed. Strong reads aid UX/verification, **but never replace `ConditionExpression`**.

### 4.2. Strong Scan Does Not Provide Snapshot Isolation

A `Scan` with `ConsistentRead=true` ensures freshness **for each individual item at the moment it is read**, not a point-in-time snapshot across the entire table. If writes happen while a multi-page scan runs, early pages and later pages can reflect different points in time.

If accounting reports demand "table state at exactly 12:00:00," design a snapshot/export/event watermark mechanism; turning strong reads on for Scan **is not enough**.

## 5. Consistency Matrix: Table, LSI, GSI, Streams, DAX

| Source | Eventual | Strong | Transactional read |
|---|---|---|---|
| **Base table** | Yes | Yes | Yes via `TransactGetItems` |
| **LSI** | Yes | Yes in `Query/Scan` | Not a direct target of `TransactGetItems` |
| **GSI** | **Yes** | **No** | No |
| **DynamoDB Streams** | **Yes** | **No** | No |
| **DAX cache** | Cached eventual | Strong passes straight through to DynamoDB, **not cached** | `TransactGetItems` pass-through |
| **Global Tables MREC replica** | Yes | Only guarantees latest **present in the read Region** | Single-Region only, not atomic across Regions |
| **Global Tables MRSC replica** | Yes | **Yes across Regions with strong read** | **Does not support transaction APIs** |

### 5.1. Local Secondary Index (LSI)

An LSI **shares the partition key** with the base table while changing the sort key/projection. It is defined at table creation time and supports strongly consistent `Query`. Tables with LSIs impose a **10 GiB item collection limit per partition-key value**; reading attributes not projected into the LSI fetches them from the base table.

### 5.2. Global Secondary Index (GSI)

A GSI can use a **different partition key** to serve new access patterns. GSI data updates **asynchronously** from the base table, so:

- **Eventual reads only**—no strong GSI Queries.
- Passing `ConsistentRead=true` with `IndexName=GSI1` throws **`ValidationException`**.
- An item just written to the table **may not appear yet** in a GSI Query; updated attributes may lag.
- `ProjectionType` and index entry size affect read units, not consistency.

Never try to "fix" stale GSIs by granting admin IAM permissions, cranking up SDK read timeouts, or tight-loop retrying.

### 5.3. DynamoDB Streams

Streams is a change feed for CDC/Lambda, not an API for querying latest item values. Stream records propagate asynchronously and do not support strongly consistent reads. Consumers must handle event delivery, ordering, duplicates, and retries per Streams/Lambda semantics.

## 6. Read APIs and Consistency Levels

### 6.1. `GetItem`

Requires the **complete primary key** and supports `ConsistentRead=true`:

~~~json
{
  "TableName": "Orders",
  "Key": {
    "PK": {"S": "ORDER#101"},
    "SK": {"S": "META"}
  },
  "ConsistentRead": true,
  "ReturnConsumedCapacity": "TOTAL"
}
~~~

`ReturnConsumedCapacity` reports consumed capacity. A response without `Item` means the item was not found, **but missing items still consume read units**.

### 6.2. `Query`

Requires partition-key equality and an optional sort-key condition. Queries on **base tables/LSIs** can be strong; **GSIs** are eventual only.

~~~json
{
  "TableName": "Orders",
  "KeyConditionExpression": "#pk = :pk",
  "ExpressionAttributeNames": {
    "#pk": "PK"
  },
  "ExpressionAttributeValues": {
    ":pk": {"S": "CUSTOMER#7"}
  },
  "ConsistentRead": true,
  "ReturnConsumedCapacity": "INDEXES"
}
~~~

`Query` can return `LastEvaluatedKey`; if present, retrieve the next page via `ExclusiveStartKey`.

### 6.3. `Scan`

Scan reads across items in a table or index and can burn large capacity. `ConsistentRead=true` works only on supported targets. **Parallel Scan** speeds up migrations at higher capacity pressure, without providing snapshot isolation.

### 6.4. `BatchGetItem`

Reads multiple keys and allows `ConsistentRead=true` per table request. **Output order is not guaranteed to match input order.** `UnprocessedKeys` can be returned under throttling or size limits and must be retried with exponential backoff. Even when every table read uses strong consistency, `BatchGetItem` is **not an atomic multi-item snapshot**.

### 6.5. `TransactGetItems`

Atomically reads multiple items from tables within **the same account and Region**, up to **100 Get actions** and **4 MiB** total item data. Cannot target GSIs/LSIs directly. Provides **serializable isolation** per transaction semantics, though it can conflict and fail.

For items up to 4 KiB, transactional reads consume **2 read units** (double strong, quadruple eventual). MREC transactions are atomic only within the local Region; **MRSC global tables do not support `TransactGetItems` or `TransactWriteItems`**.

## 7. Calculating RCU/RRU by 4 KiB Chunks

- **Provisioned mode:** `1 RCU` covers **1 strong read/second** or **2 eventual reads/second** for an item up to `4 KiB`.
- **On-demand mode:** `1 RRU` equals one strong read up to 4 KiB; eventual consumes **0.5 RRU**, transactional **2 RRUs**.
- `4 KiB = 4096 bytes`. Larger items round up to the next 4 KiB multiple.

For an item of size `s` bytes:

\[
b=\left\lceil\frac{s}{4096}\right\rceil,\qquad
U_{\mathrm{strong}}=b,\qquad
U_{\mathrm{eventual}}=\frac{b}{2},\qquad
U_{\mathrm{transactional}}=2b
\]

This is the baseline item-read formula; empty `Query`/`Scan` results still incur **minimum read charges**, and specific APIs have additional rules. Cost is never determined merely by bytes **returned after filtering**.

| Item size | 4 KiB chunks | Strong | Eventual | Transactional |
|---|---:|---:|---:|---:|
| 1 KiB | 1 | 1 | 0.5 | 2 |
| 4 KiB | 1 | 1 | 0.5 | 2 |
| 4 KiB + 1 byte | 2 | 2 | 1 | 4 |
| 8 KiB | 2 | 2 | 1 | 4 |
| 20 KiB | 5 | 5 | 2.5 | 10 |

### 7.1. Example: 100 Reads/Second

For 3 KiB items at 100 `GetItem` calls/second:

~~~text
100 eventual reads × 0.5 unit =  50 read units/second
100 strong reads   × 1   unit = 100 read units/second
100 transactional  × 2   unit = 200 read units/second
~~~

If item size grows to 5 KiB, each item spans 2 chunks:

~~~text
100 eventual reads × 1 unit = 100 units/second
100 strong reads   × 2 unit = 200 units/second
100 transactional  × 4 unit = 400 units/second
~~~

This is capacity math, **not USD pricing**: rates, data transfer, storage, global replication, and backups depend on Region and table settings.

### 7.2. Saving Capacity by Using Strong Reads Only Where Needed

~~~text
1000 reads/s, item <= 4 KiB
950 catalog/profile eventual → 950 × 0.5 = 475 units/s
 50 checkout strong         →  50 × 1   =  50 units/s
Total                                     525 units/s

If all reads were strong                 1000 units/s
~~~

This is an idealized calculation. If 5% of traffic hammers a single hot key while 95% spreads evenly, throttling/hot partitions and latency still need separate analysis.

## 8. Consistency Is Neither Latency Nor Throughput

| Goal | Choice | Risk / trade-off |
|---|---|---|
| Low-latency catalog | Eventual / cache | Can be stale |
| Read-after-write on one item | Strong `GetItem` | Double read capacity |
| Atomic multi-item read | `TransactGetItems` | Transaction conflicts and 2× strong cost |
| Query by secondary attribute | Eventual GSI | Index propagation lag |
| Multi-Region with fast writes | MREC | Cross-Region staleness, last-writer-wins |
| Multi-Region strict freshness | MRSC strong | Cross-Region coordination and feature limits |
| Heavy repeated reads | DAX | Cache invalidation and cluster costs |

Strong reads consume twice the read units of eventual reads for the same item size; **there is no fixed rule that latency is exactly 2×**. Measure client P50/P95/P99 and AWS `SuccessfulRequestLatency`, checking SDK retries and network paths.

### 8.1. Hot Partitions Still Exist

Read consistency cannot rescue a scorching-hot partition key. If 90% of reads target `PK=GLOBAL`, throttling can happen even with plenty of table-wide headroom. Redesign keys, cache, distribute reads, and shard purposefully. Under throttling, SDK backoff/jitter drives up latency—distinguish that from eventual staleness.

## 9. Choosing Consistency by Business Case

| Scenario | Recommendation |
|---|---|
| Product catalog, recommendations | Eventual / GSI / cache |
| User just updated profile and reloads immediately | Strong base-table `GetItem` or echo write response |
| Near-real-time dashboard | Eventual, documenting staleness tolerance |
| Checkout inventory check | Conditional write; strong read only supports UI |
| Single-use coupon | Conditional write / transaction |
| Filtering orders by status via GSI | Eventual with UX handling index lag |
| Payment ledger | Idempotency + conditional write/transaction where supported |
| Point-in-time snapshot report | Export / backup / event watermark; never strong Scan |
| Cross-Region read right after write | MRSC strong or route reads to the write Region |

### 9.1. Read-Your-Write UX Does Not Always Require Another Read

`UpdateItem` supports `ReturnValues=ALL_NEW` to return the updated item directly. The UI can render from that response, eliminating a follow-up read call. If the client does call `GetItem` afterward, enable strong reads on the base table when needed. When querying via a GSI, index lag still applies; the UI can hold newly written items in local state until the GSI converges.

### 9.2. Session-Level Monotonic Reads

An application can track `lastSeenVersion` in the session; if an eventual read returns a lower version than already shown, ignore the stale regression. You can perform a bounded retry or fall back to a strong base-table read. This is an application-level session guarantee, not a built-in DynamoDB consistency flag.

## 10. GSIs, LSIs, and Access Pattern Design

A table might store:

~~~text
PK = ORDER#101
SK = META
status = PAID
customerId = CUSTOMER#7
updatedAt = 2026-11-20T09:30:00Z
~~~

A GSI serves customer queries:

~~~text
GSI1PK = CUSTOMER#7
GSI1SK = UPDATED#2026-11-20T09:30:00Z#ORDER#101
~~~

Right after a base-table write, the GSI entry may lag. **Never** enable strong reads on a GSI. To provide read-your-write per customer, use these strategies:

1. If `ORDER#101` is known, read the base table with `GetItem ConsistentRead=true`.
2. Return the written item in the API response and merge it into the UI's temporary list.
3. Make the base table `PK=CUSTOMER#7`, `SK=ORDER#101` for strong Queries if that access pattern dominates.
4. Consider an LSI if the partition key fits and the item collection stays under 10 GiB.
5. When multiple projections need atomic updates, consider denormalized records + `TransactWriteItems` within one Region (not MRSC).
6. Accept eventual consistency with a "syncing" UI state and bounded retries when brief lag is fine.

### 10.1. `FilterExpression` and `ProjectionExpression` Do Not Cut Capacity as Assumed

`Query` reads items matching `KeyConditionExpression` **first**, then applies `FilterExpression`. Whether the filter keeps 5 or 500 items, read units are charged for all data **read**, not just the output. `ProjectionExpression` shrinks network payload, but does not shrink the item size DynamoDB reads from the base table.

For example, reading 200 KiB of items and filtering down to 4 KiB still charges read units for **200 KiB read**, not 4 KiB. GSI projections shrink the stored index entry, which is a different **index item size**—not a filter reducing capacity.

### 10.2. Pagination and State Snapshots

- One Query/Scan request reads at most **1 MiB of data before filtering**; paginate whenever `LastEvaluatedKey` is present.
- `Limit=10` means evaluating at most 10 items before filtering, not guaranteeing 10 returned items after filtering.
- A page can return **0 items and a `LastEvaluatedKey`** when the filter rejects every item on that page.
- Strong Query/Scan does not provide a **consistent snapshot** across multiple pages while writes are occurring.

Never mistake `Count=0` from a GSI Query for proof an item does not exist; it could be propagation lag, a key expression mismatch, a filter, or unpaginated pages.

## 11. Global Tables: MREC and MRSC in Current AWS

**DynamoDB Global Tables** replicate data across AWS Regions. Today there are **two consistency modes**: **Multi-Region Eventual Consistency (MREC)** (default) and **Multi-Region Strong Consistency (MRSC)**. AWS introduced MRSC in 2025; it is no longer accurate to claim "all Global Tables are strictly eventual across Regions."

### 11.1. MREC: Asynchronous Replication

~~~mermaid
sequenceDiagram
    participant API as Client Region A
    participant A as Replica Region A
    participant B as Replica Region B
    participant USER as Client Region B
    API->>A: UpdateItem status=PAID
    A-->>API: Success
    USER->>B: GetItem ConsistentRead=true
    B-->>USER: May still see PENDING
    A-->>B: Async replication
    USER->>B: GetItem ConsistentRead=true
    B-->>USER: PAID after replication arrives
~~~

With MREC, `ConsistentRead=true` in Region B reads only the latest state **already replicated to B**. It does not wait for writes committed in A **before replication reaches B**. If two Regions concurrently update the same item, MREC resolves via **last-writer-wins**, risking lost updates. Design **single-writer per aggregate**, Regional ownership, or explicit conflict handling.

`TransactWriteItems` in Region A is atomic in A; replica B may temporarily see some items replicated before others. **MREC has no cross-Region atomic transactions.**

### 11.2. MRSC: Strong Consistency Across Regions

MRSC synchronously replicates updates to **at least one other Region before returning write success**; a strong read in **any replica Region** reflects the latest successful write of that item, supporting **RPO=0** under the service model.

MRSC requires **exactly three Regions**: either three full replicas, or two replicas + one **witness**. A witness stores metadata for quorum/replication, **without allowing applications to read/write items**. AWS publishes the list of MRSC-supported Regions (including Asia Pacific (Singapore) at the time of writing); never assume every Region supports it.

| Criterion | MREC (default) | MRSC |
|---|---|---|
| Replication | Asynchronous | Synchronous to at least one other Region |
| Cross-Region strong read | No, if write has not arrived at replica | Yes, via `ConsistentRead` on any replica |
| Concurrent writes | Last-writer-wins | Can raise `ReplicatedWriteConflictException` |
| Write / strong-read latency | Generally lower | Cross-Region coordination/RTT, generally higher |
| Transactions | Atomic within Region only | **Does not support transaction APIs** |
| LSI | Supported per table design | **Not supported** |
| GSI | Eventual | **Still eventual** |
| TTL | Supported | **Not supported** |
| `ReplicationLatency` metric | Emitted | **Not emitted** |
| Topology | Can add/remove replicas per rules | Fixed 3 Regions, restricted edits |
| Switching mode after creation | Direct toggle not supported | Direct toggle not supported |

### 11.3. MRSC Trade-Offs That Are Hard to Ignore

- GSIs remain **eventual**, even though base replicas support global strong reads.
- MRSC **does not support `TransactGetItems` or `TransactWriteItems`**.
- MRSC **has no TTL or LSI**.
- Writes and strongly consistent reads incur cross-Region latency → affecting P99 latency.
- Mode and topology must be chosen at creation. You cannot flip a Global Table from MREC to MRSC with a flag; migrating an existing populated table to MRSC is constrained and needs a migration strategy.
- DynamoDB has no single global auto-routing endpoint; clients call **regional endpoints**. Application/API failover and dependencies must be designed explicitly.

If your business operates in one Region or tolerates cross-Region staleness, MREC is simpler and cheaper. Choose MRSC only when cross-Region strong item reads and zero RPO justify its latency and feature limits.

## 12. DAX and Read Consistency: Caching Does Not Make Reads Strong

**DynamoDB Accelerator (DAX)** is a managed in-memory cache for repeated read workloads, reducing latency and DynamoDB read units on eventual cache hits.

~~~mermaid
flowchart LR
    APP["Java application"] --> DAX["DAX cluster: item/query cache"]
    DAX -->|"Eventual cache hit"| APP
    DAX -->|"Cache miss / strong pass-through"| DB["DynamoDB"]
    WRITER["Direct DynamoDB writer"] --> DB
~~~

### 12.1. DAX Item Cache and Query Cache

- Eventual `GetItem`: DAX checks the item cache; on hit, returns cached data; on miss, reads eventually from DynamoDB and caches it.
- DAX cluster nodes sync cache asynchronously, allowing brief skew across nodes.
- Writes routed through DAX pass through to DynamoDB (write-through), refreshing the item cache per DAX behavior.
- Direct writes to DynamoDB **bypassing DAX** leave cached items stale until TTL/eviction.
- `Query`/`Scan` uses the **query cache**, which can remain stale even after item cache updates; updating an item **does not automatically invalidate the query cache**.

### 12.2. Strong and Transactional Requests Through DAX

With `ConsistentRead=true`, DAX **passes through** `GetItem`/`BatchGetItem`/`Query`/`Scan` directly to DynamoDB and **does not cache strong results**. `TransactGetItems` also passes through. If most workloads require strong reads, DAX yields minimal cache-hit savings while still incurring cluster costs.

### 12.3. When Is DAX Worth It?

Ideal for read-heavy hot keys with high repeated eventual reads, tolerance for cache TTL staleness, and high cache-hit ratios. Never deploy DAX just to mask a hot partition, wrong-Region SDK traffic, or throttled read APIs. Measure actual cache-hit ratios, memory, latency, and DynamoDB read consumption.

## 13. Java AWS SDK for Java 2.x: One Key, Two Read Levels

Java 21 example using `software.amazon.awssdk:dynamodb` with the AWS SDK BOM. Use the default credentials provider chain (Lambda/ECS/EC2 IAM role or local profile)—never hardcode credentials.

~~~java
import java.util.Map;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.GetItemRequest;
import software.amazon.awssdk.services.dynamodb.model.GetItemResponse;
import software.amazon.awssdk.services.dynamodb.model.ReturnConsumedCapacity;

public final class ReadConsistencyExample {
    public static void main(String[] args) {
        Map<String, AttributeValue> key = Map.of(
            "PK", AttributeValue.fromS("ORDER#101"),
            "SK", AttributeValue.fromS("META")
        );

        try (DynamoDbClient db = DynamoDbClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {
            GetItemResponse eventual = db.getItem(GetItemRequest.builder()
                    .tableName("Orders")
                    .key(key)
                    .consistentRead(false)
                    .returnConsumedCapacity(ReturnConsumedCapacity.TOTAL)
                    .build());

            GetItemResponse strong = db.getItem(GetItemRequest.builder()
                    .tableName("Orders")
                    .key(key)
                    .consistentRead(true)
                    .returnConsumedCapacity(ReturnConsumedCapacity.TOTAL)
                    .build());

            // Never log full items containing PII in production.
            System.out.println("Eventual hasItem=" + eventual.hasItem());
            System.out.println("Strong hasItem=" + strong.hasItem());
            System.out.println("Eventual units=" +
                    eventual.consumedCapacity().capacityUnits());
            System.out.println("Strong units=" +
                    strong.consumedCapacity().capacityUnits());
        }
    }
}
~~~

This code is **read-only** on DynamoDB (consumes capacity and requires `dynamodb:GetItem`). `Orders` and the keys must exist. The two reads run at **different points in time**; with concurrent writers, comparing one pair of responses never proves one mode is universally "faster" or "more correct." Benchmarks require repeated runs and tracking business versions.

`ReturnConsumedCapacity.TOTAL` reports capacity units used by the call. For `Query` against indexes, `ReturnConsumedCapacity.INDEXES` gives the breakdown; never log raw requests/responses containing sensitive data.

## 14. Java Query: Base Table Strong, GSI Eventual, and Pagination

### 14.1. Strong Query on Base Table

~~~java
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.QueryRequest;
import software.amazon.awssdk.services.dynamodb.model.QueryResponse;
import software.amazon.awssdk.services.dynamodb.model.ReturnConsumedCapacity;

public final class StrongQueryPager {
    public static void readPages(DynamoDbClient db, String partitionValue) {
        Map<String, AttributeValue> cursor = null;
        int pageCount = 0;

        do {
            QueryRequest.Builder request = QueryRequest.builder()
                    .tableName("Orders")
                    .keyConditionExpression("#pk = :pk")
                    .expressionAttributeNames(Map.of("#pk", "PK"))
                    .expressionAttributeValues(Map.of(
                            ":pk", AttributeValue.fromS(partitionValue)))
                    .consistentRead(true)
                    .returnConsumedCapacity(ReturnConsumedCapacity.TOTAL)
                    .limit(100);

            if (cursor != null && !cursor.isEmpty()) {
                request.exclusiveStartKey(cursor);
            }

            QueryResponse page = db.query(request.build());
            System.out.println("Page " + (++pageCount)
                    + ": count=" + page.count()
                    + " scanned=" + page.scannedCount());

            // Process page.items() per business schema; never log PII.
            cursor = page.lastEvaluatedKey();
        } while (cursor != null && !cursor.isEmpty());
    }
}
~~~

`Limit=100` is the **number of items evaluated per page before `FilterExpression`**, not a guarantee of 100 returned items. `LastEvaluatedKey` indicates remaining data. While paginating, concurrent writes may occur, and strong consistency does not freeze a snapshot across pages.

### 14.2. Eventual Query on GSI

~~~java
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.QueryRequest;
import software.amazon.awssdk.services.dynamodb.model.QueryResponse;

public final class CustomerOrdersGsi {
    public static QueryResponse query(DynamoDbClient db) {
        return db.query(QueryRequest.builder()
                .tableName("Orders")
                .indexName("GSI1")
                .keyConditionExpression("#g = :v")
                .expressionAttributeNames(Map.of("#g", "GSI1PK"))
                .expressionAttributeValues(Map.of(
                        ":v", AttributeValue.fromS("CUSTOMER#7")))
                // GSIs do not support strong reads.
                .consistentRead(false)
                .build());
    }
}
~~~

**Never change this to `.consistentRead(true)`:** DynamoDB rejects it because GSIs do not support strong reads. If an index query misses a fresh write, fall back to a base-table read by known key or a session UX strategy—never spin an unbounded busy-loop on the GSI.

## 15. Guaranteeing Correctness Under Concurrent Writes

A strong `GetItem` before `UpdateItem` still leaves a race window. Use an **atomic conditional write** directly when updating inventory counts.

~~~java
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.ConditionalCheckFailedException;
import software.amazon.awssdk.services.dynamodb.model.UpdateItemRequest;

public final class InventoryUpdater {
    public static boolean reserveOne(DynamoDbClient db) {
        try {
            db.updateItem(UpdateItemRequest.builder()
                    .tableName("Inventory")
                    .key(Map.of(
                            "PK", AttributeValue.fromS("SKU#7"),
                            "SK", AttributeValue.fromS("STOCK")))
                    .updateExpression("SET available = available - :one")
                    .conditionExpression("available >= :one")
                    .expressionAttributeValues(Map.of(
                            ":one", AttributeValue.fromN("1")))
                    .build());
            return true;
        } catch (ConditionalCheckFailedException insufficient) {
            return false;
        }
    }
}
~~~

**This write mutates data** when executed with valid IAM/table permissions, modifying inventory and incurring costs. Never run it on production for practice. The condition guards `available >= 1` against concurrent writes, yet another gap remains: the same client retrying after a lost ACK could subtract a second unit if stock remains sufficient. Add a **per-order idempotency key** and operation record/transaction where business rules require it.

### 15.1. Optimistic Locking

An application maintains a `version` attribute. Updates succeed only when `version` matches expectation:

~~~text
ConditionExpression: #v = :expected
UpdateExpression: SET #status = :newStatus, #v = :next
~~~

If workers A and B both read version 7, only one succeeds updating to version 8 conditioned on version 7. The other receives `ConditionalCheckFailedException` and must resolve the conflict—never retry infinitely with stale state.

### 15.2. CAS vs. Strong Read

| Goal | Tool |
|---|---|
| Display newly written record | Strong `GetItem` or write response |
| Prevent issuing two coupons for the same key | Conditional `PutItem` with `attribute_not_exists(PK)` |
| Prevent overselling stock | `UpdateItem` condition on stock/version |
| Update two items atomically together | `TransactWriteItems` within supported scope |
| Read multiple items in one transactional snapshot | `TransactGetItems` on supported tables |
| Cross-Region strong single-item read | MRSC strong; never transaction APIs |

Choose based on invariants, not a vague label like "data is important."

## 16. TransactGetItems and Transaction Isolation

### 16.1. API Request JSON

A page verifying an order and its payment across two items:

~~~json
{
  "TransactItems": [
    {
      "Get": {
        "TableName": "Orders",
        "Key": {
          "PK": {"S": "ORDER#101"},
          "SK": {"S": "META"}
        }
      }
    },
    {
      "Get": {
        "TableName": "Orders",
        "Key": {
          "PK": {"S": "ORDER#101"},
          "SK": {"S": "PAYMENT"}
        }
      }
    }
  ],
  "ReturnConsumedCapacity": "TOTAL"
}
~~~

`TransactGetItems` atomically reads up to 100 items / 4 MiB total within the same account and Region, **and cannot read indexes directly**. It is a **read operation** consuming roughly **two RCUs/RRUs per 4 KiB item**, and can fail due to concurrent transaction conflicts or capacity.

### 16.2. Isolation Scope

DynamoDB transactions provide serializable isolation across transactional operations and documented item-level reads/writes. However, a `Query`, `Scan`, or `BatchGetItem` as a whole **does not** become a serializable snapshot simply because the table supports transactions.

With Global Tables MREC, transactions are atomic within the calling Region, not across Regions after replication. With **MRSC**, transaction APIs **are unsupported**. If your design demands cross-Region multi-item ACID, rethink the architecture and data ownership.

### 16.3. ClientRequestToken and Idempotency

`TransactWriteItems` accepts `ClientRequestToken` to deduplicate retries within DynamoDB's supported window, yet business operation IDs must be retained longer for delayed retries, SQS redeliveries, or manual recovery. If a request times out after committing, the outcome is unknown—never increment the operation key on the next retry.

## 17. Other Sources of Stale Data: TTL, Streams, and Caches

### 17.1. TTL Does Not Delete to the Exact Second

DynamoDB TTL cleanup runs **asynchronously**. An item whose `expiresAt` has passed can still remain until the background TTL process deletes it. **Strong `GetItem` can return an expired item not yet deleted.** Business logic must verify `expiresAt <= now` at decision time, paired with conditions if needed. **Global Tables MRSC does not support TTL.**

### 17.2. Streams and Downstream Projections

A Lambda reading DynamoDB Streams to update Elasticsearch/OpenSearch, S3, or caches is an **event-driven asynchronous process**. Base-table strong reads do not make those downstream projections immediately fresh. Build idempotent consumers, retries/DLQs, `IteratorAge` monitoring, and business correlation IDs.

### 17.3. Multiple Independent Staleness Layers

~~~text
Write to base DynamoDB table (success)
  ├─ Base table eventual read: brief staleness possible
  ├─ GSI replication: eventual with its own lag
  ├─ DAX item cache: TTL/eviction, especially on direct writes
  ├─ DAX query cache: not invalidated immediately on writes
  ├─ DynamoDB Streams → Lambda projection: async processing
  └─ Global Tables MREC: async cross-Region propagation
~~~

A single `ConsistentRead=true` flag cannot fix all of these. Pinpoint the exact **read path** and staleness source before altering the architecture.

## 18. IAM, VPC Endpoints, and the Right Region

### 18.1. Least-Privilege IAM

Example policy for an application reading a table and index:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOrders",
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:Query",
        "dynamodb:BatchGetItem"
      ],
      "Resource": [
        "arn:aws:dynamodb:ap-southeast-1:111122223333:table/Orders",
        "arn:aws:dynamodb:ap-southeast-1:111122223333:table/Orders/index/GSI1"
      ]
    }
  ]
}
~~~

ARNs are placeholders. Grant `dynamodb:Scan` or transaction permissions only where truly needed; restrict actions and table/index resources, never `dynamodb:*`. You can use IAM conditions like `dynamodb:LeadingKeys`/`dynamodb:Attributes` for tenant isolation when business policy aligns. **IAM does not control eventual vs. strong consistency**; that is governed by the read request/API/data source.

### 18.2. Gateway Endpoints in a VPC

ECS/Lambda workers inside private subnets can reach same-Region DynamoDB through a **Gateway VPC Endpoint**:

~~~text
com.amazonaws.ap-southeast-1.dynamodb
~~~

A Gateway endpoint attaches to private subnet route tables with an endpoint policy; standard Gateway endpoints incur **no hourly/data-processing endpoint charges**, though DynamoDB read units, storage, and related data transfer still apply.

**DynamoDB also supports Interface VPC Endpoints (AWS PrivateLink)** for on-premises clients, VPC peering, Transit Gateway, or architectures needing private endpoint IPs. Interface endpoints use Security Groups, Private DNS, and **incur endpoint-hour/data-processing charges**, unlike free-to-add Gateway endpoints for intra-VPC/same-Region access. Neither endpoint type **changes DynamoDB's read consistency semantics**.

For `AccessDenied`, check the execution role, table/KMS policies, and endpoint policies. For `TimeoutException`, inspect VPC route tables, DNS, SDK Region, and SGs/NACLs. If the response returns a stale value, that is **consistency semantics**, not necessarily a network bug.

### 18.3. Wrong Region Can Look Like a Stale Read

`DynamoDbClient` calls a **regional endpoint**. If an app in `ap-southeast-1` accidentally points to `us-east-1`, it may hit a **different table with the same name** or an un-synced MREC replica, while inflating latency. Log metadata such as account, region, table ARN/index name, `requestId`, and item business version—**never log credentials or PII**.

## 19. Benchmarking Eventual vs. Strong and MRSC Meaningfully

A rigorous benchmark must hold constant:

1. Same table, keys, item size, and partition key distribution.
2. Same Region, VPC, and SDK HTTP settings; reuse clients/connections.
3. Warm-up phase and sufficient sample size rather than comparing **a single** `GetItem`.
4. Measure **client end-to-end P50/P95/P99 latency**, AWS service latency, retries, and throttle events.
5. Record `ReturnConsumedCapacity`, item size, read mode, index, and table billing mode.
6. For consistency tests, track `version`/commit timestamps to measure stale rate—never rely on "feels fast."
7. With DAX, separate cache-hit vs. cache-miss latency, TTL, query cache, and direct writes.
8. With MREC, measure `ReplicationLatency` and business lag across Regions.
9. With MRSC, measure writes/strong reads across Regions and cross-Region failover.
10. Test in a sandbox with capped request rates and budgets; never throttle production hot keys.

### 19.1. Results Recording Template

| Metric | Table eventual | Table strong | GSI eventual | DAX eventual | MRSC strong |
|---|---:|---:|---:|---:|---:|
| P50/P95/P99 latency | Measure | Measure | Measure | Measure | Measure |
| Capacity units/request | Measure | Measure | Measure index | Separate cache hit | Measure |
| Stale reads / version lag | Measure | Expect no stale in scope | Measure | Measure | Expect no stale for successful writes |
| SDK retries/throttles | Measure | Measure | Measure | Measure | Measure |
| Infra/mode/Region | Document | Document | Document | DAX node/cache | Global topology |

Never fabricate latency figures or USD prices without an empirical workload. Base conclusions strictly on metrics observed in your test environment.

## 20. CloudWatch Observability and Operational Control

| Source | Metric / signal | Interpretation |
|---|---|---|
| DynamoDB | `ConsumedReadCapacityUnits` | Total read units consumed |
| DynamoDB | `ProvisionedReadCapacityUnits` | Provisioned read capacity |
| DynamoDB | `ReadThrottleEvents` / `ThrottledRequests` | Throttled requests, which inflate latency |
| DynamoDB | `SuccessfulRequestLatency` | Service-side latency per operation |
| DynamoDB | `SystemErrors` / `UserErrors` | Distinguish service vs. client errors |
| DynamoDB | `TransactionConflict` | Transaction contention |
| Global Tables MREC | `ReplicationLatency` | Cross-Region replication delay |
| Global Tables MRSC | No MREC-style `ReplicationLatency` | Track relevant latency/conflict/service metrics |
| DAX | Cache hits/misses, evictions, CPU | Real cache effectiveness |
| Application | P99/stale-read-rate/version lag, retry attempts | UX and business consistency |
| Event processor | Lambda `IteratorAge`, DLQ count | Downstream projection staleness |

### 20.1. Separating Incidents

- **Stale read without exception:** inspect `ConsistentRead`, base table vs. GSI, DAX cache, Global Tables mode/Region.
- **`ValidationException` on strong GSI:** remove `ConsistentRead=true` and redesign the access pattern.
- **Throttling:** check CloudWatch, SDK retries, hot partitions, and capacity/burst.
- **Conflict / `ConditionalCheckFailed`:** business concurrency or version mismatch—not replication lag.
- **`TransactionCanceledException`:** inspect cancellation reasons, optimistic locks, and capacity.
- **`ResourceNotFoundException`:** wrong Region, table, or index ARN, or table not yet ACTIVE.
- **Network timeout / `AccessDenied`:** VPC endpoint, IAM, or endpoint policy—unrelated to read consistency.

## 21. Read-Only AWS CLI: Checking Tables, Indexes, and Consistency

Commands in this section use AWS CLI v2, profile `dev`, Region `ap-southeast-1`, and an illustrative `Orders` table. They **do not mutate items**, though `GetItem`/`Query`/`TransactGetItems` still **consume read capacity and incur costs**; run only in an authorized account with bounded requests.

### 21.1. Identity, Region, and Table Metadata

~~~bash
aws sts get-caller-identity \
  --profile dev \
  --query '{Account:Account,Arn:Arn}' \
  --output json

aws dynamodb list-tables \
  --profile dev \
  --region ap-southeast-1 \
  --output json

aws dynamodb describe-table \
  --table-name Orders \
  --profile dev \
  --region ap-southeast-1 \
  --query 'Table.{Name:TableName,Status:TableStatus,KeySchema:KeySchema,Mode:BillingModeSummary.BillingMode,GlobalConsistency:MultiRegionConsistency,GSIs:GlobalSecondaryIndexes[].IndexName,LSIs:LocalSecondaryIndexes[].IndexName}' \
  --output json
~~~

`MultiRegionConsistency` may show `EVENTUAL` (MREC) or `STRONG` (MRSC) on a Global Table; single-Region tables may omit the field. `GlobalSecondaryIndexes` and `LocalSecondaryIndexes` show which Query paths support strong vs. eventual reads.

**Never guess MRSC mode just from seeing `Replicas`:** inspect the consistency mode metadata and topology. On a newly created table, `DescribeTable` metadata may lag briefly; wait for the table to become `ACTIVE` instead of acting blindly.

### 21.2. Eventual GetItem (Default)

~~~bash
aws dynamodb get-item \
  --table-name Orders \
  --key '{"PK":{"S":"ORDER#101"},"SK":{"S":"META"}}' \
  --return-consumed-capacity TOTAL \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

This command uses default **eventual consistency**. It will not fix missing data if an item has not yet appeared.

### 21.3. Strong GetItem on Base Table

~~~bash
aws dynamodb get-item \
  --table-name Orders \
  --key '{"PK":{"S":"ORDER#101"},"SK":{"S":"META"}}' \
  --consistent-read \
  --return-consumed-capacity TOTAL \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

The `--consistent-read` flag applies to the table. JSON quoting uses **Bash** rules; PowerShell requires different escaping/quoting, or you can use `file://key.json` on Windows. Never store credentials or business PII in sample files.

### 21.4. Strong Query on Base Table

~~~bash
aws dynamodb query \
  --table-name Orders \
  --key-condition-expression '#pk = :pk' \
  --expression-attribute-names '{"#pk":"PK"}' \
  --expression-attribute-values '{":pk":{"S":"CUSTOMER#7"}}' \
  --consistent-read \
  --return-consumed-capacity TOTAL \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Requires a matching access pattern and key. If the table's PK is `ORDER#id` instead of `CUSTOMER#id`, Query will not return orders grouped by customer—**that is data modeling**, not a read consistency bug. The CLI auto-paginates when `LastEvaluatedKey` appears, whereas SDK code must paginate explicitly.

### 21.5. GSI Query: Strong Reads Not Allowed

~~~bash
aws dynamodb query \
  --table-name Orders \
  --index-name GSI1 \
  --key-condition-expression '#g = :v' \
  --expression-attribute-names '{"#g":"GSI1PK"}' \
  --expression-attribute-values '{":v":{"S":"CUSTOMER#7"}}' \
  --return-consumed-capacity INDEXES \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

**Never add `--consistent-read`** to a GSI query. DynamoDB does not support strong GSI reads and raises `ValidationException`. When you need the freshest item and know its base key, read the base table with `get-item --consistent-read`.

### 21.6. Transactional Read: Higher Capacity Cost

~~~bash
# READ-ONLY, but consumes transactional read capacity; DO NOT use on MRSC tables.
aws dynamodb transact-get-items \
  --transact-items '[{"Get":{"TableName":"Orders","Key":{"PK":{"S":"ORDER#101"},"SK":{"S":"META"}}}},{"Get":{"TableName":"Orders","Key":{"PK":{"S":"ORDER#101"},"SK":{"S":"PAYMENT"}}}}]' \
  --return-consumed-capacity TOTAL \
  --profile dev \
  --region ap-southeast-1 \
  --output json
~~~

Table `Orders` must exist and support transactions; MRSC Global Tables **do not support this API**. Transactions can conflict and fail with `TransactionCanceledException`. Never use a transaction just to check a single item "because it sounds stronger."

### 21.7. Measuring Capacity Without Scanning Production

Use per-request `ConsumedCapacity`, CloudWatch `ReadThrottleEvents`/`ConsumedReadCapacityUnits`, and redacted SDK logs to compare read modes. **Never run `Scan --consistent-read` on a large table just to explore**: it can burn huge capacity and trigger production throttling.

## 22. Write APIs and Read-After-Write Testing (Mutating)

To verify consistency in a sandbox, a team can create an item at version 1, update it to version 2, and immediately read using both modes. **These commands mutate real data**—never run them in production without approval.

~~~bash
# SANDBOX ONLY - writes/overwrites an item in a DynamoDB table.
aws dynamodb put-item \
  --table-name OrdersLab \
  --item '{"PK":{"S":"ORDER#LAB101"},"SK":{"S":"META"},"status":{"S":"PENDING"},"version":{"N":"1"}}' \
  --condition-expression 'attribute_not_exists(PK)' \
  --profile dev \
  --region ap-southeast-1

# SANDBOX ONLY - updates an item currently at version 1.
aws dynamodb update-item \
  --table-name OrdersLab \
  --key '{"PK":{"S":"ORDER#LAB101"},"SK":{"S":"META"}}' \
  --update-expression 'SET #s = :paid, #v = :v2' \
  --condition-expression '#v = :v1' \
  --expression-attribute-names '{"#s":"status","#v":"version"}' \
  --expression-attribute-values '{":paid":{"S":"PAID"},":v1":{"N":"1"},":v2":{"N":"2"}}' \
  --return-values ALL_NEW \
  --profile dev \
  --region ap-southeast-1
~~~

Use an `OrdersLab` table in a lab account with `PutItem`/`UpdateItem` IAM permissions and sufficient capacity. Conditional writes protect versions from races; `ReturnValues=ALL_NEW` returns the latest state without an extra read.

**Never try to "force a GSI to be strong" by tweaking CloudFormation or IAM**: index consistency is service-level behavior.

## 23. Decision Tree: Choosing Consistency Without Waste

~~~mermaid
flowchart TD
    A["App needs to read data"] --> B{"Must reflect committed write immediately?"}
    B -->|"No"| EV["Eventual: table/GSI/cache"]
    B -->|"Yes"| C{"Can we query base key or LSI?"}
    C -->|"Yes"| D{"Read-only or deciding an update?"}
    D -->|"Read-only"| STR["Strong GetItem/Query"]
    D -->|"Update correctness"| CAS["Conditional write / transaction"]
    C -->|"GSI only"| F["Redesign base-key access; fallback/versioned UX"]
    A --> G{"Cross-Region writes/reads?"}
    G -->|"Yes"| H{"Need global strong single-item reads/RPO=0?"}
    H -->|"No"| MREC["MREC + conflict policy"]
    H -->|"Yes"| MRSC["MRSC + latency/feature trade-offs"]
~~~

### 23.1. Architecture Review Checklist

1. What is the **actual read path**: base table, LSI, GSI, DAX, Streams projection, or replica?
2. How much staleness can the business tolerate? Is there an explicit SLA/requirement?
3. Is the access pattern a point read, partition query, index query, scan, or multi-item transaction?
4. Can we use the **write response** or a strong `GetItem` by known key instead of a GSI Query?
5. Are invariants enforced via **conditional writes** rather than `SELECT then UPDATE`?
6. Are Global Tables used? MREC or MRSC, and in which Regions?
7. If MRSC, does the app depend on unsupported **LSI/TTL/transaction APIs**?
8. What are the item sizes, projected attributes, RCU/RRU budgets, hot partitions, and retry behaviors?
9. Do DAX hit ratios and invalidation patterns actually reduce read units?
10. Are IAM, VPC endpoints, cross-Region networking, and CloudWatch ready for operations?

## 24. Read-Only Lab and Analysis Scenarios

### 24.1. Lab 1 — Inspecting Metadata and Consistency Settings

Use the **read-only** `describe-table` and `get-item`/`query` CLI commands from Section 21 on an authorized table with bounded read requests. If no AWS account is available, use this illustrative table:

| Item | Sample value |
|---|---|
| Table name | `Orders` |
| Base PK | `PK`, SK `SK` |
| GSI1 PK | `GSI1PK` |
| Table Region | `ap-southeast-1` |
| Global mode | No (single-Region) |
| Read pattern A | `GetItem(PK=ORDER#101, SK=META)` |
| Read pattern B | `Query GSI1PK=CUSTOMER#7` |

**Question:** Which read pattern can enable strong consistency? **A**, because it is a base-table `GetItem`; **B** cannot, because it targets a GSI. If the UI just created an order and B does not show it yet, fall back to `GetItem` by `orderId` or render from the write response.

### 24.2. Lab 2 — Calculating Read Units

1. Reading 200 items/s, 3 KiB each, eventual: `200 × 0.5 = 100 units/s`.
2. Same workload strong: `200 × 1 = 200 units/s`.
3. Each item grows to 4 KiB + 1 byte: strong `200 × 2 = 400 units/s`.
4. Transactional reads at 20 items/s, 6 KiB each: `20 × (2 blocks × 2) = 80 units/s`.

Why is there a step jump once an item exceeds 4 KiB? Because DynamoDB rounds up in 4 KiB blocks for capacity accounting. Explain why `FilterExpression` does not shrink the items/bytes read from the base table.

### 24.3. Lab 3 — Race Condition

Two workers both want to decrement `stock=1`. Both run strong `GetItem` and see `1`. Does that prevent overselling? **No.** Write an `UpdateItem` with `ConditionExpression=available >= 1` and design an `operationId` to guard against retries after lost ACKs. Contrast **stale reads** with **concurrent updates**.

### 24.4. Lab 4 — GSI Lag

The application creates Order#101 with `GSI1PK=CUSTOMER#7`. Right after the successful write, a GSI Query misses the item. Why? Asynchronous GSI propagation. Should you set `ConsistentRead=true` on the GSI? **Unsupported.** Propose a base `GetItem` fallback and a UI sync-state indicator.

### 24.5. Lab 5 — Global Tables MREC

A client in Region A updates Order#101 `status=PAID`, and a client in Region B immediately calls strong `GetItem`. Is seeing `PAID` guaranteed? **No** under MREC, because B may not have received the replicated write yet. Options include routing reads to A, waiting for propagation with version checks, or evaluating MRSC if global strong reads are required.

### 24.6. Lab 6 — Global Tables MRSC

A team wants MRSC for a ledger system while also using `TransactWriteItems`, TTL, and LSIs. Is that compatible? **No**—MRSC does not support those features. They must redesign the data model or pick another architecture. MRSC provides global strongly consistent single-item reads, not a cross-Region multi-item ACID engine.

### 24.7. Lab 7 — DAX

DAX item cache holds `status=PENDING`. Another service runs a direct DynamoDB `UpdateItem` to `PAID`. A user reading via DAX receives `PENDING`. Why? Stale cache from a DAX-bypassing write. Does a strong `GetItem` through DAX hit the cache? **No**—the request passes through to DynamoDB and returns without caching the strong result.

### 24.8. Lab Summary

Build a review matrix:

| Access pattern | Data source | Consistency | Estimated units | Risk | Mitigation |
|---|---|---|---|---|---|
| Order detail after write | Base table | Strong | Per 4 KiB item | Concurrent overwrite | Conditional version |
| Customer orders listing | GSI | Eventual | Per GSI entry | GSI lag | Session fallback |
| Daily dashboard | Table/GSI | Eventual | Per bytes read | Acceptable staleness | Latency label |
| Inventory reserve | Atomic `UpdateItem` | Write condition | Per write units | Duplicate retries | Operation ID |
| Multi-item regional snapshot | Table transaction | `TransactGet` | 2× strong | Conflict/cost | Bounded retries |
| Immediate global read | MRSC replica | Strong | Measure Region/cost | Cross-Region latency | Failover testing |

## 25. Self-Assessment Questions

1. Can an eventual read return an item before a write commits successfully?
2. Why might a successful write not appear immediately on an eventual read?
3. What is the default value of `ConsistentRead`?
4. How do base tables, LSIs, GSIs, and Streams differ on strong reads?
5. Does `GetItem ConsistentRead=true` stop another writer from modifying the item right after the read?
6. Does a strong `Scan` provide table-wide snapshot isolation?
7. Does `BatchGetItem` with per-table strong consistency provide an atomic multi-item snapshot?
8. When should you choose `TransactGetItems`?
9. How many read units does a transactional read of a 4 KiB item consume?
10. How many strong/eventual units does a 4 KiB + 1 byte item consume?
11. At 100 item reads/s of 3 KiB items, how much capacity does eventual save compared to strong?
12. Does `FilterExpression` reduce RCUs on a base-table `Query`?
13. Does `ProjectionExpression` shrink the item size used to compute RCUs?
14. Does `Limit=10` guarantee DynamoDB returns 10 items after filtering?
15. What does `LastEvaluatedKey` signify?
16. Can strong Queries be enabled on a GSI via CLI/SDK?
17. Why might a freshly written item be absent from a GSI Query?
18. Does DAX cache strongly consistent reads?
19. Does the DAX query cache auto-invalidate when an item updates?
20. Does an MREC global table guarantee Region B immediately reads a write committed in A?
21. How does MREC resolve concurrent cross-Region writes?
22. How does MRSC differ from MREC in replication and write latency?
23. Does MRSC support GSI strong reads, TTL, LSIs, and transactions?
24. How many Regions does MRSC require, and what is the witness for?
25. Are `TransactWriteItems` calls in MREC atomic across Regions?
26. When decrementing inventory, why is a conditional write more critical than just a strong read?
27. Does DynamoDB TTL delete items at the exact `expiresAt` timestamp?
28. How do you distinguish stale reads, throttling, and wrong-Region calls?
29. Which CloudWatch metric tracks MREC replication lag?
30. When should an application use strong reads for every access pattern?

### Answer Key Outline

- **Eventual:** default, may be briefly stale; reads committed values only, consuming ~**0.5 unit/4 KiB**.
- **Strong:** base table/LSI, **1 unit/4 KiB**, does not lock items or create a full-Scan snapshot.
- **Transactional:** `TransactGetItems` costs **2 units/4 KiB**, capped at 100 items/4 MiB, same account/Region, unsupported on MRSC.
- **GSI/Streams:** eventual-only; `FilterExpression`/`ProjectionExpression` do not cut base-table bytes read.
- **Global Tables:** MREC is cross-Region eventual; MRSC is strong across Regions with latency and feature trade-offs.
- **Correctness:** use `ConditionExpression`, optimistic versioning, and idempotency for concurrent updates—never substitute a strong read before writing.

## 26. Official AWS Documentation

1. [DynamoDB read consistency](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadConsistency.html) — Default eventual, strong table/LSI, GSI/Streams eventual, global modes.
2. [DynamoDB read and write operations](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/read-write-operations.html) — Capacity units by item size and consistency.
3. [DynamoDB provisioned capacity](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/provisioned-capacity-mode.html) — RCUs/WCUs and capacity planning.
4. [On-demand capacity mode](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/on-demand-capacity-mode.html) — RRUs and traffic scaling behavior.
5. [DynamoDB Query API](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_Query.html) — `ConsistentRead`, pagination, consumed capacity.
6. [Query and FilterExpression](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.FilterExpression.html) — Filtering after reading items.
7. [Other Query considerations](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.Other.html) — RCUs, limits, index consistency.
8. [DynamoDB Scan API](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_Scan.html) — Strong Scan has no snapshot isolation.
9. [GetItem API](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_GetItem.html) — Point reads.
10. [BatchGetItem API](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_BatchGetItem.html) — Batch strong flag, `UnprocessedKeys`.
11. [TransactGetItems API](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_TransactGetItems.html) — Atomic multi-item reads and limits.
12. [DynamoDB transactions: how they work](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html) — Isolation, conflicts, consumed units.
13. [Global tables architecture and consistency modes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/V2globaltables_HowItWorks.html) — MREC/MRSC, replication, limits, supported Regions.
14. [Best practices for Global Tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-global-table-design.html) — Topology and consistency/availability trade-offs.
15. [DescribeTable API](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_DescribeTable.html) — `MultiRegionConsistency` table metadata.
16. [Global secondary indexes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GSI.html) — GSI replication and access patterns.
17. [Local secondary indexes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/LSI.html) — LSI constraints and strong consistency.
18. [DAX consistency models](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DAX.consistency.html) — Item/query caches, strong pass-through.
19. [DAX how it works](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DAX.concepts.html) — Read caching behavior.
20. [Conditional writes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Expressions.ConditionExpressions.html) — Protecting invariants.
21. [DynamoDB Java SDK 2.x examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_dynamodb_code_examples.html) — `GetItem`, `Query`, and SDK design.
22. [DynamoDB CloudWatch metrics](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/metrics-dimensions.html) — Capacity, throttles, latency.
23. [DynamoDB VPC endpoints](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/privatelink-interface-endpoints.html) — Private access options.
24. [DynamoDB pricing](https://aws.amazon.com/dynamodb/pricing/) — On-demand/provisioned reads, storage, global replication.
25. [AWS DynamoDB Service Quotas](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/ServiceQuotas.html) — Item sizes, limits, and capacity.

> **Final takeaway:** **Eventual reads** are ideal when brief staleness is acceptable, while **strong table/LSI reads** serve read-after-write needs within supported scope. **GSIs and Streams are eventual-only**, **DAX passes strong reads through**, **MREC lacks global strong reads**, and **MRSC** provides them at the cost of latency and without transactions, TTL, or LSIs. For any concurrent update race, rely on **conditional writes, idempotency, and appropriate transactions**. Always measure capacity units, P99 latency, replication/index lag, and total cost before deciding.
