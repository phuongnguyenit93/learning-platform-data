# Hot Partitions, Throttling, Backups, and Recovery in DynamoDB

## Learning Objectives

After this lesson, learners can:

- Explain how **partition keys**, **sort keys**, and **physical partitions** relate to Amazon DynamoDB scalability.
- Distinguish **hot items/hot partitions**, **table-level throttling**, **GSI throttling**, **account-level quotas**, and **administrator-set on-demand limits**; avoid trying to fix every error by simply raising RCUs/WCUs.
- Estimate **RCUs/WCUs**, understand strongly consistent, eventually consistent, and transactional reads/writes, per-physical-partition limits, and adaptive capacity.
- Read **ThrottlingReasons** including the resource ARN and limit type, and correlate them with CloudWatch metrics and Contributor Insights to identify root causes.
- Choose between **on-demand/provisioned capacity**, Auto Scaling, warm throughput, and pre-warming strategies ahead of flash sales or sudden traffic spikes.
- Mitigate hot keys using **partition key cardinality, write sharding, aggregation, caching/DAX, and backpressure**, while understanding trade-offs around query fanout, ordering, and transactions.
- Implement **exponential backoff + jitter** with AWS SDK for Java v2, handle `BatchWriteItem.UnprocessedItems` and `BatchGetItem.UnprocessedKeys`, and avoid infinite retries.
- Distinguish **on-demand backups**, **point-in-time recovery (PITR)**, **AWS Backup**, **Global Tables**, and **PITR restore**, selecting based on RPO/RTO and retention requirements.
- Enable PITR, create backups, restore to **a new DynamoDB table**, validate data, reconfigure missing settings, and perform a safe cutover using the AWS CLI.
- Design IAM, KMS, VPC endpoints, CloudWatch metrics, alarms, recovery drills, and cost controls for systems using DynamoDB.

**Chapter Context:** **DynamoDB** in the **CLOUD_PROVIDERS_AWS** module is part of the AWS learning path covering Regions/AZs, IAM, VPCs, compute, storage, and databases through integration and serverless. This lesson focuses on selecting, designing, and operating DynamoDB **securely, observably, recoverably, and cost-effectively**, especially alongside API Gateway/Lambda/ECS, SQS/EventBridge, CloudWatch, and AWS Backup.

> **Scope & Boundaries:** DynamoDB is a managed service; users **do not directly create or control physical partitions**. Limits, capacity modes, pricing, and restore behavior may vary by Region, account, and time. The CLI commands below use placeholder lab table names and profiles; do not run load tests, restores, or deletes against production tables.

## 1. The Problem: A Table Has Sufficient Capacity Yet Requests Still Get Throttled?

Suppose an e-commerce system has an `Orders` table using `tenantId` as the partition key and `orderId` as the sort key:

~~~text
PK = TENANT#tenant-a | SK = ORDER#1001
PK = TENANT#tenant-a | SK = ORDER#1002
PK = TENANT#tenant-a | SK = ORDER#1003
PK = TENANT#tenant-b | SK = ORDER#2001
...
~~~

During a flash sale, tenant A creates a huge number of orders per second while other tenants generate little traffic. Total table read/write consumption remains below your provisioned capacity, yet tenant A's requests start getting throttled.

~~~mermaid
flowchart LR
    API[API Gateway / Lambda] --> DDB[(DynamoDB Orders)]
    DDB --> Hot[Hot partition/key range: TENANT#A]
    DDB --> Cool1[Low-traffic Range B]
    DDB --> Cool2[Low-traffic Range C]
    DDB --> Cool3[Low-traffic Range D]
    Hot --> Fail[Throttling despite spare table capacity]
    Fail --> Obs[ThrottlingReasons + CloudWatch]
~~~

The root cause is usually **uneven load distribution**, not merely insufficient total table capacity. Simply increasing total WCUs may **not overcome the limit of a single physical partition/key range**.

A second incident: an engineer runs a faulty batch update by mistake, wiping out data. Read replicas or Global Tables can propagate that error to other Regions. To recover, you need **PITR or a point-in-time backup**, restore **to a new table**, validate, and shift traffic under strict control.

The two skills in this lesson are therefore tightly linked: **preventing system collapse from skewed load** and **ensuring data remains recoverable when mistakes happen**.

## 2. How Are DynamoDB Logical Keys Different from Physical Partitions?

A DynamoDB table contains **items**; each item is uniquely identified by its primary key:

- **Simple primary key**: consists only of a **partition key (HASH)**, such as `userId`.
- **Composite primary key**: **partition key + sort key (RANGE)**, such as `PK=ORDER#1001` and `SK=METADATA`.

DynamoDB hashes the partition key to distribute data across service-managed **physical partitions**. The sort key enables sorting and querying within the same logical partition key.

### Logical Partition Key Does Not Equal Physical Partition

- All items sharing the same partition key form an **item collection** (when the table has a sort key).
- One physical partition can hold multiple partition key values.
- DynamoDB can split/rebalance physical partitions based on storage size and throughput load.
- Multiple items sharing a partition key are **not guaranteed to stay on one physical partition forever** under all conditions; adaptive capacity can split item collections by sort key when appropriate.
- Having a **Local Secondary Index (LSI)** changes item collection splitting behavior; do not assume hot keys can always be automatically split.

**Hot key:** A partition key value or single item receiving excessive requests.

**Hot physical partition/key range:** A physical slice receiving excessive RCUs/WCUs, whether from one hot key, multiple keys co-located together, or uneven access patterns.

**Hot GSI:** The base table has a well-distributed partition key, but a GSI uses a poor key, causing writes or reads through the GSI to bottleneck.

### Examples of Good and Poor Keys

| Access pattern | Hot-prone key | Key worth considering |
| --- | --- | --- |
| Events everyone creates today | `PK=DATE#2026-11-20` | `PK=DATE#2026-11-20#SHARD#N` or partitioned by entity |
| Millions of likes on a single post | `PK=POST#hot-post`, every like updates same item | Sharded counters + async aggregation |
| Recording product page views | `PK=PRODUCT#popular-id` | Emit distributed events via Kinesis/SQS then aggregate |
| Multi-tenant orders | `PK=TENANT#large-tenant` | Split by tenant + time bucket/shard if load profile demands |
| GSI by common status | `GSI_PK=STATUS#PENDING` | Distribute by tenant/time bucket/shard if queries allow |

**Do not blindly append random suffixes to every key.** Doing so forces fanout queries on reads, multiplies query count, alters uniqueness semantics, and can destroy desired sort ordering. Only shard when measurements show a key range exceeds capacity and you have designed the read/merge strategy.

## 3. RCUs, WCUs, and Item Size: Calculate Accurately Before Scaling

DynamoDB meters capacity differently based on **read vs. write** and **consistency**.

### 3.1. Reads

For items ≤ **4 KB**:

- **Strongly consistent read:** roughly **1 RCU** per read/second.
- **Eventually consistent read:** roughly **0.5 RCU** per read/second (two reads/second consume 1 RCU).
- **Transactional read:** roughly **2 RCUs** per read/second.

If an item is > 4 KB, calculate in 4 KB blocks rounded up; final RCU count also depends on consistency.

Example of reading a **6 KB** item once:

| Read mode | Equivalent capacity |
| --- | --- |
| Strong | `ceil(6/4)=2 RCU` |
| Eventually consistent | `2 × 0.5 = 1 RCU` |
| Transactional | `2 × 2 = 4 RCU` |

### 3.2. Writes

Each item **≤1 KB** written once consumes roughly **1 WCU**, rounded up to 1 KB increments. Transactional writes typically consume **double** the standard WCUs.

Example of writing a **2.2 KB** item:

- Standard write: `ceil(2.2/1)=3 WCU`.
- Transactional write: `6 WCU` for the same size under unit pricing rules.

### 3.3. Query, Scan, and FilterExpression

A `Query` or `Scan` can read many items and consumes capacity based on the **actual data read**, not just the final count of returned items. **`FilterExpression` is applied after DynamoDB reads the items**, so it does not reduce RCUs for scanned/retrieved items.

**Typical mistake:** Running a full-table `Scan` filtered by `status=NEW` as request rates rise, causing massive cost and throttling. The solution is **designing keys/GSIs around access patterns**, paginating properly, capping concurrency, and avoiding Scans on hot request paths.

**On-demand mode** meters **read request units / write request units (RRU/WRU)** using the same item-size and consistency rules, though pay-per-request pricing differs from provisioned capacity.

## 4. Throughput Limits on a Physical Partition

DynamoDB documentation cites reference benchmarks **per physical partition**:

| Type | Typical limit |
| --- | --- |
| Write | Roughly **1,000 WCU/sec** |
| Strongly consistent reads | Roughly **3,000 RCU/sec** |
| Eventually consistent reads | Roughly **6,000 4 KB reads/sec**, equivalent to 3,000 RCU |

These figures are measured in **capacity units**, meaning not all HTTP requests cost the same; larger items and transactional operations consume more units.

**Key characteristics:**

1. **Reads and writes throttle independently** at the partition level.
2. **On-demand is still subject to partition limits**, even though total table throughput can be huge.
3. **Adaptive capacity** redistributes spare capacity to hot partitions/key ranges but **cannot exceed the physical limit of a single partition**.
4. Automatic split/rebalance helps when traffic patterns allow; a single item hammered with concurrent writes remains a bottleneck that cannot easily be split.
5. GSIs have **their own partitioning and throughput**, so a hot GSI key can cause write failures even when the base table uses a well-distributed key.

### Quick Calculation Example for a Hot Counter

An item `PK=COUNTER#SALE` is updated **1,800 times/sec**, each ≤1 KB. That demands roughly **1,800 WCUs/sec directed at a single item/key**.

Because one partition handles roughly **1,000 WCU/sec**, raising table capacity from 5,000 to 20,000 WCUs **will not magically let a single item sustain 20,000 WCUs**. The solution is **sharded counters**, aggregation, or redesigning the write path.

## 5. Throttling Has More Than One Cause

DynamoDB categorizes **ThrottlingReason** into four main groups, each structured as:

~~~text
<ResourceType><OperationType><LimitType>
Example: TableWriteKeyRangeThroughputExceeded
~~~

- `ResourceType`: `Table` or `Index`.
- `OperationType`: `Read` or `Write`.
- `LimitType`: one of the four causes below.

| LimitType | When does it happen? | First mitigation step |
| --- | --- | --- |
| **`KeyRangeThroughputExceeded`** | A physical partition/key range is too hot | Identify hot keys, partition key/GSI design, adaptive capacity, sharding/caching |
| **`ProvisionedThroughputExceeded`** | Table/GSI exceeds provisioned RCUs/WCUs | Optimize queries, raise provisioned units/Auto Scaling, check GSIs |
| **`AccountLimitExceeded`** | On-demand table/GSI exceeds account/Region throughput quota | Check Service Quotas, request quota increase, warm-up, shed load |
| **`MaxOnDemandThroughputExceeded`** | Exceeds user-configured **maximum on-demand throughput** | Review cost guardrails, raise max if approved, or throttle traffic |

Errors can surface as exceptions like **`ProvisionedThroughputExceededException`**, **`ThrottlingException`**, or **`RequestLimitExceeded`** depending on the context. **The exception name alone is not enough to diagnose a hot partition.**

### Sample Error Payload

~~~json
{
  "code": "ProvisionedThroughputExceededException",
  "ThrottlingReasons": [
    {
      "reason": "IndexWriteKeyRangeThroughputExceeded",
      "resource": "arn:aws:dynamodb:ap-southeast-1:111122223333:table/OrdersLab/index/ByStatus"
    }
  ]
}
~~~

This example points directly to **GSI `ByStatus`**, **write**, and **key range throughput**. Raising base table RCUs would not fix the real bottleneck.

### How to Trace the Error Chain

~~~mermaid
flowchart TD
    Error[DynamoDB throttling response] --> Reason[Read ThrottlingReasons + resource ARN]
    Reason --> Res{Table or Index?}
    Res --> Type{LimitType?}
    Type -->|KeyRange| Key[Hot key / sharding / Contributor Insights]
    Type -->|Provisioned| P[Provisioned RCUs/WCUs and Auto Scaling]
    Type -->|AccountLimit| Q[Service Quotas / account-Region limits]
    Type -->|MaxOnDemand| O[Configured on-demand maximum]
    Key --> Test[Re-measure latency + throttles + cost]
    P --> Test
    Q --> Test
    O --> Test
~~~

**Do not retry indefinitely before identifying the error type.** Short retries help transient spikes, but retries cannot turn a key receiving a steady 3,000 writes/sec into a partition capable of 3,000 WCUs.

## 6. GSI Hot Keys and Write Throttling / Back-Pressure

A base table with PK `ORDER#uuid` distributes evenly, yet it has a GSI:

~~~text
Table PK = orderId (well-distributed UUIDs)
GSI1 PK  = status (only NEW / PAID / FAILED)
GSI1 SK  = createdAt
~~~

During a flash sale, nearly every write sets `status=NEW`. The GSI funnels all traffic into the same **logical partition key**. When GSI writes fall behind, **base table writes get throttled by back-pressure from the GSI**, even though the base table itself still has plenty of capacity.

### Symptoms

- `ThrottlingReason` contains **`IndexWriteKeyRangeThroughputExceeded`** or **`IndexWriteProvisionedThroughputExceeded`**.
- The ARN in the error ends with `/index/ByStatus`.
- GSI `WriteThrottleEvents` or throttling reason metrics spike.
- Base table write API latency and errors rise while many table-level gauges have not hit limits.

### Redesigning the Access Pattern

Instead of `GSI_PK=STATUS#NEW`, consider:

~~~text
GSI_PK = STATUS#NEW#DAY#2026-11-20#SHARD#03
GSI_SK = createdAt#orderId
~~~

Reading all `NEW` orders requires a **fanout Query across N shards**, followed by merge-sorting and paginating via per-shard tokens. If a dashboard only needs counts, use **event-driven materialized counts** rather than querying the entire GSI.

**Trade-off:** Sharding relieves hot writes at the cost of **more read calls, complexity, and expense**. Plan migrations, backfills, and versioning carefully; never alter schemas on a production table without a rollback plan.

## 7. Adaptive Capacity, Split-for-Heat, and Unavoidable Limits

DynamoDB automatically manages **adaptive capacity** to shift unused table throughput toward hot key ranges, reducing throttling during unbalanced traffic.

### What Adaptive Capacity Does

- Monitors hot partitions/keys and redistributes throughput accordingly.
- Can **isolate hot items** or **split partitions** depending on load and key structure.
- Operates automatically with no developer toggle required.
- Helps when one physical partition runs hot while overall table capacity still has unused headroom.

### What Adaptive Capacity Cannot Do

- **Cannot exceed the ~1,000 WCU / 3,000 RCU ceiling of a single physical partition**.
- Cannot guarantee splitting a **single item** receiving all writes.
- With an **LSI**, DynamoDB **cannot automatically split an item collection across multiple physical partitions** in certain layouts, so a partition key with a massive item collection can remain hot.
- With **strictly monotonic sort keys**, split-for-heat can be less effective because writes keep targeting the newest range.
- Cannot rescue a GSI design where every record shares one low-cardinality partition key under extreme write load.

### When to Wait for Adaptation vs. Change the Key

If brief throttling appears right as traffic surges and then disappears while SLOs hold, adaptive capacity/split-for-heat may have resolved it. If **the same key/partition range keeps throttling** while latency and retries climb, move to key distribution, caching, or backpressure.

**Never assume every hot key will automatically split cleanly.** Measure with Contributor Insights and CloudWatch, and account for LSIs, monotonic sort keys, and real workload shapes.

## 8. Provisioned, On-Demand, Warm Throughput, and Flash Sales

### Provisioned Capacity

You specify **RCUs/WCUs** for tables/GSIs and can enable DynamoDB Auto Scaling. Throttling happens when usage exceeds provisioned units or when a hot partition hits its ceiling despite spare table capacity.

**Auto Scaling does not react instantaneously** and is constrained by min/max bounds, target utilization, and CloudWatch metric evaluation intervals. A sudden flash sale spike can throttle before Auto Scaling reacts.

### On-Demand Capacity

On-demand bills per request unit and automatically scales up/down with traffic. However:

- New tables start with AWS-published baseline throughput, such as **up to roughly 4,000 writes/sec and 12,000 strongly consistent reads/sec** for uniform workloads with small items.
- The system can accommodate **double the previous peak** immediately under AWS rules.
- If traffic exceeds double the previous peak within roughly **30 minutes**, throttling can occur while partitions scale out.
- **Account/Region quotas**, **user-configured maximum throughput**, and **physical partition limits** still apply.
- On-demand **is not free**: request pricing, storage, backups/PITR, streams, Global Tables, data transfer, and monitoring are still billed per feature.

### Warm Throughput

AWS provides **warm throughput** for tables/GSIs: the read/write workload level a resource can sustain **immediately** based on history or configuration. You can proactively **pre-warm** ahead of expected spikes subject to limits and pricing.

**Warm throughput is distinct from a single partition's maximum limit.** Pre-warming a table to 50,000 WCUs does not enable 50,000 writes/sec against one physical partition.

| Symptom | Appropriate response |
| --- | --- |
| Provisioned table hits WCU limit with evenly spread keys | Increase provisioned WCUs / Auto Scaling capacity |
| On-demand outpaces previous peak too rapidly | Pre-warm, ramp up gradually, forecast peaks |
| Account-level quota exceeded | Request increase via Service Quotas / AWS Support |
| Hit configured on-demand maximum | Review cost limits, adjust max if approved, or shed load |
| `KeyRangeThroughputExceeded` despite spare table capacity | Fix partition key/GSI, shard/cache/apply backpressure |
| GSI write back-pressure | Raise GSI capacity if under-provisioned; redesign GSI key if key range is hot |

## 9. Diagnosing Hot Keys with CloudWatch and Contributor Insights

### First Steps

1. Capture the **exception + ThrottlingReasons + resource ARN** from SDK/logs.
2. Distinguish `Table` vs. `Index`, `Read` vs. `Write`, and the exact limit type.
3. Open DynamoDB Console → table/index → **Metrics/Monitoring** in the current UI.
4. Compare `ConsumedReadCapacityUnits`/`ConsumedWriteCapacityUnits`, provisioned levels, read/write throttle metrics, latency, and request counts.
5. Verify request patterns: `GetItem`/`Query`/`Scan`/`BatchWrite`, item sizes, consistency, indexes, and concurrency.
6. Check **CloudWatch Contributor Insights for DynamoDB** if enabled and security-approved.
7. Audit key cardinality and top hot keys, especially **GSI partition keys**.
8. Update your hypothesis, pick the mitigation matching the reason type, and validate in a lab/staging environment.

### How Contributor Insights Helps

Contributor Insights surfaces **most accessed** and **most throttled** partition/sort key values, making hot-key detection straightforward. However:

- Primary keys may contain **PII or sensitive identifiers**, so review IAM/retention/encryption policies before enabling.
- Contributor Insights incurs **additional cost**; do not enable it broadly on every table/GSI without clear need.
- Not all request types (e.g., PartiQL per AWS docs) are surfaced identically.
- Hot ranges can come from "rolling hot partitions", Scans, or monotonic keys, so top-key charts alone may not explain everything.

**When logging:** Instead of dumping raw payloads or tokens, log `tableName`, `indexName`, `operation`, `reason`, `requestId`, `itemSizeBucket`, and a **non-sensitive hash or key prefix** per policy.

## 10. Write Sharding: Splitting One Hot Key Across Buckets

Suppose all order events for one tenant currently sit under:

~~~text
PK = TENANT#A
SK = EVENT#timestamp#uuid
~~~

To spread write load, pick `N` logical shards:

~~~text
PK = TENANT#A#SHARD#00
PK = TENANT#A#SHARD#01
...
PK = TENANT#A#SHARD#15
SK = EVENT#timestamp#uuid
~~~

### How Should Shards Be Chosen?

- **Random sharding**: writers pick a bucket randomly. Suitable when you never need to fetch a single entity deterministically from one shard.
- **Calculated sharding**: `shard = hash(eventId) mod N`. Allows deterministic bucket lookup from `eventId`.
- **Time-bucket + shard**: prevents unbounded item collections and supports day/hour-scoped queries.

Pseudocode example:

~~~text
function shardFor(eventId, shardCount):
    return unsignedStableHash(eventId) modulo shardCount

pk = "TENANT#" + tenantId + "#DAY#" + date + "#SHARD#" + shardFor(eventId, 16)
sk = "EVENT#" + timestamp + "#" + eventId
PutItem(pk, sk, otherAttributes)
~~~

**Never change `shardCount` without versioning.** Changing shards from 16 to 32 maps the same `eventId` to a different PK; maintain a key version or migration catalog so both old and new data remain readable.

### Reading Sharded Data

Querying by tenant + day must:

1. Query all required shard keys.
2. Paginate each shard independently (`LastEvaluatedKey` per Query).
3. Merge-sort results by timestamp and build a composite pagination token.
4. Bound concurrency and handle partial failures, timeouts, and cost.

If the workload mainly needs **point lookups for one event**, maintain an `eventId → shard` mapping or use stable calculated sharding. If it needs **tenant-wide key uniqueness**, use a conditional write/transaction pattern or suitable index; sharding makes global uniqueness harder.

**Sharding is a data model change**, not just tuning a throughput knob.

## 11. Hot Reads: Caching, Denormalization, and Strongly Consistent Reads

For a popular hot item—such as shared configuration or a catalog item read thousands of times per second:

- Use an **application cache / ElastiCache** with clear TTL and invalidation rules.
- Evaluate **DynamoDB Accelerator (DAX)** when access patterns, APIs, and consistency requirements fit.
- Use **eventually consistent reads** whenever business logic allows; this roughly halves RCU consumption compared to strong reads for the same item size.
- Denormalize read models or publish snapshots via S3/CloudFront for rarely changing public data.
- Cap duplicate retries and cache misses, shielding the DB with backpressure.

### DAX Is Not a Silver Bullet

- DAX sits in front of DynamoDB for supported access patterns and provides **eventual consistency semantics** for cached reads.
- It does **not fix hot writes**; write traffic still hits DynamoDB.
- It is unsuitable for balance/authorization/inventory decisions requiring transaction-level freshness unless carefully designed.
- It carries separate cluster node costs, availability considerations, and operational overhead.

### Preventing Cache Stampedes

When a hot item's cache TTL expires, thousands of clients can miss simultaneously and query DynamoDB for the same key. Use **single-flight**, TTL jitter, stale-while-revalidate (when safe), rate limiting, and fallback protection instead of merely cranking cache TTL up forever.

## 12. Retrying Correctly: Exponential Backoff + Jitter and Idempotency

Throttling is generally **retryable**, yet unbounded retries cause **retry storms**, driving up latency and bills. AWS SDK for Java v2 includes built-in retry strategies; applications must tune them appropriately for request SLOs and workloads.

### Principles

1. Retry only genuinely **transient/retryable** errors per SDK/service classification.
2. Use **exponential backoff + jitter** so clients do not retry in synchronized waves.
3. Bound both retry attempts and **total deadline**; frontends should not hang for minutes reading one item.
4. Apply rate limiting, circuit breakers, and queues/buffers for spikes; never rely on retries instead of good partition key design.
5. Record `requestId`, `reason`, retry count, latency, and business outcome in metrics.
6. Writes require **idempotency** when callers cannot tell whether an earlier attempt committed; use conditional writes/unique keys or transactions with an idempotency token per API support.

### Java SDK v2: Retry Strategy Example

The application needs `software.amazon.awssdk:dynamodb` and the AWS SDK for Java v2 BOM, obtaining credentials from an IAM role/profile.

~~~java
package com.example.dynamodb;

import java.time.Duration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.core.retry.RetryMode;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

public final class DynamoClientFactory {

    public static DynamoDbClient create() {
        return DynamoDbClient.builder()
            .region(Region.AP_SOUTHEAST_1)
            // STANDARD supports backoff/jitter and retry quota per AWS SDK.
            // Configure max attempts via SDK configuration when needed.
            .overrideConfiguration(c -> c
                .retryStrategy(RetryMode.STANDARD)
                .apiCallTimeout(Duration.ofSeconds(10))
                .apiCallAttemptTimeout(Duration.ofSeconds(3)))
            .build();
    }
}
~~~

**SDK Version Note:** `retryStrategy(RetryMode.STANDARD)` is supported in AWS SDK for Java v2, providing exponential backoff and jitter per AWS documentation. Default `maxAttempts` can differ across SDK versions, so pin dependencies, verify against the Java v2 Developer Guide, and measure real retry behavior. **Do not wrap a manual retry loop around the SDK when SDK retries are already active**, unless enforcing custom total deadlines and idempotency policies.

### Idempotency and Ambiguous Retry Outcomes

A `PutItem` call may commit while its response times out returning to the client. Retrying without `ConditionExpression` can overwrite state or increment a counter twice.

Example guarding unique order creation:

~~~json
{
  "TableName": "OrdersLab",
  "Item": {
    "PK": {"S": "ORDER#501"},
    "SK": {"S": "META"},
    "status": {"S": "CREATED"}
  },
  "ConditionExpression": "attribute_not_exists(PK)"
}
~~~

If a retry throws `ConditionalCheckFailedException`, do not treat it automatically as throttling; verify whether the item was created by your previous attempt or another request using `eventId`/idempotency key before returning a response.
## 13. BatchGetItem/BatchWriteItem: HTTP Success Does Not Mean All Items Succeeded

With batch APIs, DynamoDB can **partially process** a request and return unprocessed items in the response:

- `BatchWriteItem` → `UnprocessedItems`.
- `BatchGetItem` → `UnprocessedKeys`.

**Never treat HTTP 200 as proof that every record succeeded.**

### Batch Write Demo

~~~json
{
  "RequestItems": {
    "OrdersHotLab": [
      {
        "PutRequest": {
          "Item": {
            "PK": {"S": "ORDER#501"},
            "SK": {"S": "META"},
            "status": {"S": "CREATED"}
          }
        }
      },
      {
        "PutRequest": {
          "Item": {
            "PK": {"S": "ORDER#502"},
            "SK": {"S": "META"},
            "status": {"S": "CREATED"}
          }
        }
      }
    ]
  }
}
~~~

If the response contains:

~~~json
{
  "UnprocessedItems": {
    "OrdersHotLab": [
      {
        "PutRequest": {
          "Item": {
            "PK": {"S": "ORDER#502"},
            "SK": {"S": "META"},
            "status": {"S": "CREATED"}
          }
        }
      }
    ]
  }
}
~~~

then the application must **retry only `ORDER#502`**, never blindly resend the entire batch.

### Retry Pattern

~~~text
pending = initialRequests
attempts = 0

while pending != empty and attempts < maxAttempts and beforeDeadline:
    response = BatchWriteItem(pending)
    pending = response.UnprocessedItems
    if pending != empty:
        wait(exponentialBackoffWithFullJitter(attempts))
    attempts += 1

if pending != empty:
    store pending durably to retry queue / DLQ
    alert failure without pretending success
~~~

**Important Notes:**

- `BatchWriteItem` **does not** support per-item conditional writes like `PutItem.ConditionExpression`; never use batch write for operations needing uniqueness or idempotency conditions.
- `BatchWriteItem` is limited to **25 requests/batch** and AWS payload size limits; responses can be partial.
- `BatchGetItem` is limited to **100 items/request** plus data/access limits; `UnprocessedKeys` can be returned due to throughput or size.
- In the **AWS SDK Java v2 Enhanced Client**, `batchGet` may assist with retrying unprocessed keys while `batchWrite` may return unprocessed items for the caller to handle. Always verify exact SDK version contracts.
- Adding more retry threads is not a solution when a hot partition is out of capacity.

### Write Transactions Differ from Batch Writes

`TransactWriteItems` provides atomicity within supported API limits, consumes capacity differently, and can be rejected due to conflicts or throttling. For transactional writes, **use an idempotency token `ClientRequestToken`** per the API contract/window; never substitute `BatchWriteItem` thinking both merely "write multiple items".

## 14. DynamoDB Streams, Lambda, SQS, and Backpressure

DynamoDB often sits behind API Gateway/Lambda/ECS services. If clients hammer **one hot partition key**, scaling Lambda concurrency infinitely only drives more concurrent writes to that same key, worsening throttling.

~~~mermaid
flowchart LR
    Client[Web/Mobile] --> API[API Gateway]
    API --> Lambda[Lambda / ECS]
    Lambda --> Rate[Rate limit / batching]
    Rate --> DB[(DynamoDB)]
    DB --> Stream[DynamoDB Streams]
    Stream --> Processor[Lambda stream processor]
    Processor --> Queue[(SQS DLQ / failure destination)]
~~~

**Load-shedding and smoothing options:**

1. **Cap concurrency** on Lambda/ECS and apply per-tenant/per-resource token buckets.
2. Buffer write-heavy asynchronous jobs through **SQS** to absorb spikes and control consumption rate.
3. Coalesce multiple incremental updates into **periodic aggregate writes** where business logic permits.
4. Shard writes using an appropriate partition key model; avoid a single continuously hammered counter item.
5. Use conditional writes, optimistic locking, and idempotency to prevent duplicates during queue retries.
6. Use DynamoDB Streams for CDC and read-model synchronization within capacity, **never mistaking Streams for a point-in-time recovery backup**.

### Streams Do Not Replace Backups

DynamoDB Streams has its own **retention window and event semantics**, not a full table snapshot. Events that have rolled out of the stream or retention window do not provide complete history to restore an accidentally deleted table. **PITR and on-demand backups** solve an entirely different problem.

### Table Throttling Can Trigger Cascading Failures

A Lambda handler hits `ProvisionedThroughputExceededException` and retries repeatedly, API Gateway times out, the client retries POST, and SQS/Lambda reprocesses events and double-writes. Prevent cascades with:

- End-to-end deadlines and backoff.
- Idempotency on database keys or business events.
- Returning proper 429/503 responses when shedding load instead of faking success.
- CloudWatch alarms on tables, GSIs, Lambda errors, and DLQs.
- Business metrics like `orders_created_unique`, `orders_duplicate_ignored`, and `hot_key_retry_attempts`.

## 15. Observability: CloudWatch, Logs, and Business Metrics

| Signal | Meaning | When to act |
| --- | --- | --- |
| `ConsumedReadCapacityUnits` / `ConsumedWriteCapacityUnits` | Actual consumed capacity | Approaching provisioned limits or unexpected cost growth |
| `ProvisionedReadCapacityUnits` / `ProvisionedWriteCapacityUnits` | Total provisioned capacity | Mis-sizing or Auto Scaling max set too low |
| `ReadThrottleEvents` / `WriteThrottleEvents` | Throttled read/write events | Sustained elevation affecting SLOs |
| `ThrottledRequests` | Requests receiving throttling | Correlate with application errors/retries |
| `SuccessfulRequestLatency` | Service-side latency for successful requests | Slow access or hot paths |
| `SystemErrors` / `UserErrors` | API error classifications | Separate service faults from client issues |
| **ThrottlingReason-specific metrics** | Pinpoint table/index + read/write + limit type | Isolate true root cause |
| Contributor Insights top keys | Most accessed/throttled keys | Hot key schema or GSI key |
| Application p95/p99 latency | Real user-facing latency | SLO degraded even when backend retries eventually pass |
| SDK retry attempts | Retry overhead | Retry storms or hot keys |
| DynamoDB `ReturnedItemCount` / consumed capacity logs | Query/read efficiency | Scans or post-read filtering |
| Lambda Errors/Duration/Throttles | Backend reaction | Cascading failures |
| SQS queue age/DLQ | Jobs backing up due to DynamoDB throttling | Must shed/reduce load before redriving |

**Some CloudWatch metrics are published as aggregates/averages with specific dimensions**; do not expect every metric to support every table/index dimension combination. For short spikes, metrics have delay and granularity limits; combine with SDK `ThrottlingReasons` to pinpoint per-request causes.

### Minimum Dashboard

~~~text
Top:
  requests per second, successful business writes, p95/p99 latency
  throttle count and throttle rate

Capacity:
  table/GSI consumed vs provisioned/on-demand max
  physical partition key-range throttling reasons
  warm throughput and previous peak where available

Workload:
  top hot key shapes (safely hashed)
  BatchWrite UnprocessedItems, SDK retries, Lambda concurrency
  queue backlog, DLQ, downstream API 429/503

Recovery:
  PITR enabled + Earliest/LatestRestorableDateTime
  last on-demand backup status/time
  last restore drill duration and validation result
~~~

**Security:** Throttling logs must never dump raw item bodies, plaintext secrets, tokens, or email/PII partition keys. Contributor Insights can expose primary keys; restrict CloudWatch read permissions and avoid sensitive data in key designs.

## 16. Lab: Creating an On-Demand DynamoDB Table via CLI

> **Prerequisites:** AWS CLI v2, Region `ap-southeast-1`, IAM profile `lab` with appropriate permissions. Every table, backup, and restore incurs charges; use only a lab account and synthetic data, and never generate load large enough to impact account quotas. Clean up resources once no needed data remains.

### 16.1. Verify Identity

~~~bash
aws sts get-caller-identity \
  --profile lab

aws configure get region \
  --profile lab
~~~

### 16.2. Create a Table with a Composite Key

~~~bash
aws dynamodb create-table \
  --table-name OrdersHotLab \
  --attribute-definitions AttributeName=PK,AttributeType=S AttributeName=SK,AttributeType=S \
  --key-schema AttributeName=PK,KeyType=HASH AttributeName=SK,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --region ap-southeast-1 \
  --profile lab
~~~

**Declare only key attributes in `AttributeDefinitions`.** DynamoDB does not require pre-declaring non-key attributes.

Wait until the table is ready:

~~~bash
aws dynamodb wait table-exists \
  --table-name OrdersHotLab \
  --region ap-southeast-1 \
  --profile lab

aws dynamodb describe-table \
  --table-name OrdersHotLab \
  --region ap-southeast-1 \
  --profile lab \
  --query 'Table.{Name:TableName,Status:TableStatus,Billing:BillingModeSummary,Key:KeySchema,Arn:TableArn}'
~~~

### 16.3. Seed Data

~~~bash
aws dynamodb put-item \
  --table-name OrdersHotLab \
  --item '{"PK":{"S":"ORDER#501"},"SK":{"S":"META"},"status":{"S":"CREATED"},"amount":{"N":"120000"}}' \
  --condition-expression 'attribute_not_exists(PK)' \
  --region ap-southeast-1 \
  --profile lab
~~~

> **Shell note:** Single-quoted examples are written for Bash/macOS/Linux; Windows PowerShell has different quoting rules. If you hit JSON quoting issues, create a JSON file in your lab project and pass `--item file://item.json`. This worker **does not** create any extra files inside the module.

### 16.4. Read and Inspect Consumed Capacity

~~~bash
aws dynamodb get-item \
  --table-name OrdersHotLab \
  --key '{"PK":{"S":"ORDER#501"},"SK":{"S":"META"}}' \
  --consistent-read \
  --return-consumed-capacity TOTAL \
  --region ap-southeast-1 \
  --profile lab
~~~

Run it again without `--consistent-read` and compare capacity across request types and consistency modes; never extrapolate peak throughput from a single sample.

## 17. Lab: Demonstrating Hot Keys Without Creating a Load Storm

**Never instruct generating 3,000+ writes/sec against a live account.** You can teach the phenomenon accurately via **access pattern modeling, math analysis, and a small set of safe requests**.

### Comparing Two Designs

**A. Unsharded counter:**

~~~json
{
  "PK": {"S": "COUNTER#PRODUCT-501"},
  "SK": {"S": "TOTAL"},
  "count": {"N": "150"}
}
~~~

If 2,500 purchases/sec all update `count` on that single item, every write funnels into one key. Calculate WCUs by item size and compare against the partition limit. This is a **paper analysis**, not a live load run.

**B. Sharded counter:**

~~~text
COUNTER#PRODUCT-501#SHARD#00
COUNTER#PRODUCT-501#SHARD#01
...
COUNTER#PRODUCT-501#SHARD#15
~~~

Each purchase writes to a deterministic or random shard; total count = sum across shards. Deduplicate repeated purchases using `purchaseId` and writer-side transactions/idempotency, and cache or materialize totals for dashboards if query fanout gets expensive.

### Logic Testing

- Send 10–20 synthetic events with unique `eventId` values to code/staging.
- Verify hash-to-shard distribution is balanced across the sample set.
- Verify duplicate `eventId` does not increment counts twice under your idempotency design.
- Query every shard and compute the sum.
- Test that timeout retries do not double-count.

**A small test does not prove production throughput capacity**, yet it validates key shape, consistency, read fanout, and retry logic before any approved load test.

## 18. Workflow for Investigating a Real Throttling Incident

Suppose an error log shows:

~~~json
{
  "errorCode": "ThrottlingException",
  "reason": "IndexWriteMaxOnDemandThroughputExceeded",
  "resource": "arn:aws:dynamodb:ap-southeast-1:111122223333:table/OrdersHotLab/index/ByStatus",
  "requestId": "req-lab-129"
}
~~~

**Step-by-step analysis:**

1. `Index` → the resource is a **GSI**, not the base table.
2. `Write` → GSI updates triggered by writes are being throttled.
3. `MaxOnDemandThroughputExceeded` → hit the GSI's configured on-demand maximum throughput, not a physical hot partition.
4. Check whether that GSI on-demand limit was set for **budget control**.
5. Compare GSI `ConsumedWriteCapacityUnits`, throttling metrics, application p99, and business request rate.
6. Choose **load shedding / backpressure** or raise the GSI max after change approval/budget review.
7. Check whether `ByStatus` **also** has a hot partition; raising max throughput alone will not cure a separate hot-key bottleneck.
8. Retry with backoff + idempotency; never retry failures endlessly.
9. Re-test and document before/after metrics.

**Another example:** `TableWriteProvisionedThroughputExceeded` in provisioned mode calls for checking table WCUs/Auto Scaling; `TableWriteKeyRangeThroughputExceeded` requires **diagnosing hot keys** first.

### When to Contact AWS Support?

- Persistent throttling despite healthy key distribution and consumption verified in metrics.
- Needing an on-demand service quota increase for an account/Region.
- Warm throughput or partition behavior not matching expectations.
- Suspected issues with internal partition splits or service incidents.

Provide the **Region, table/index ARN, request IDs, UTC timestamps, reason, metrics, and scope**—never send plaintext data or credentials.

## 19. Migrating Key Design When Production Already Has Data

You cannot simply "swap the partition key" on an existing DynamoDB table like renaming a column in RDS. Typically you must **create a new table/GSI/key layout and migrate the data**.

### Safe Migration Plan

~~~mermaid
flowchart TB
    Old[(Old table schema)] --> Export[Export/Scan/Stream migration]
    Export --> New[(New sharded table)]
    App[Application] --> Mode{Migration mode}
    Mode -->|Read old, write old + new| Dual[Dual-write / outbox]
    Mode -->|Compare counts + checksums| Verify[Validate IDs, versions, aggregates]
    Verify --> Cut[Canary cutover reads/writes]
    Cut --> Full[Full cutover]
    Full --> Retire[Old table retention + cleanup approval]
~~~

**Operational steps:**

1. Identify hot-causing patterns, measure `ThrottlingReasons`, and audit key cardinality.
2. Design the new schema with `schemaVersion`, `eventId`, and versioned shard counts.
3. Backfill via rate-limited export/scan so production writes are not overwhelmed or RCUs spiked unexpectedly.
4. Use controlled Streams/outbox/dual-write to keep changes synced during backfill.
5. Ensure updates, deletes, and TTL events propagate too—not just inserts.
6. Validate data by IDs, counts, checksums, business invariants, and sample queries.
7. Canary traffic + **shadow reads**, then cut over via feature flag/config.
8. Watch hot-key throttles, p95 latency, capacity, and cost on the new schema.
9. Maintain a rollback route to the old table **only while data remains in sync**; never treat config rollback as data rollback.
10. After a safety period, retire the old table per retention/backup policy.

### The Hardest Part Is Dual-Write

Two separate DynamoDB tables do not automatically share an atomic transaction across complex workflows. Use **DynamoDB transactions** within supported account/Region scope when appropriate, or **transactional outbox / DynamoDB Streams** for eventual replay. Every consumer/migration writer needs **idempotency**, update ordering, and conflict handling.

**Avoid split-brain:** Never let two app versions update the same business record under two key schemas without a single source of truth and reconciliation.

## 20. Backups and Restore: Choosing the Right Tool for Each Risk

| Mechanism | Purpose | Strengths | Limits to remember |
| --- | --- | --- | --- |
| **DynamoDB on-demand backup** | Logical snapshot of a table at creation time | Independent backup, retained long-term until deleted/managed | Not second-by-second history |
| **DynamoDB PITR** | Restore to any point within **1–35 days** | Continuous backups, one-second granularity, no daily schedule needed | Latest lags ~5 minutes; restores into a **new table** |
| **AWS Backup for DynamoDB** | Backup plans/schedules, retention, cross-account/cross-Region | Centralized governance, policies, and vaults | Depends on configuration, costs, and restore permissions |
| **DynamoDB Global Tables** | Multi-Region reads/writes and regional availability per mode | Regional availability and data replication | **Not a backup**; accidental deletes replicate too |
| **DynamoDB Streams** | CDC/event processing | Powers read models/audit events within retention | Not PITR or full backup |
| **Export to S3** | Archival/analytics/data export | Integrates with data lakes; consumes no RCUs during export | Restoring back to a table requires import/mapping; does not restore all config verbatim |

### RPO/RTO Must Be Explicitly Defined

- **RPO**: maximum tolerable data loss measured in time when restoring to a recovery point.
- **RTO**: acceptable elapsed time until the table/restored application is ready to serve.

**PITR's latest restorable time typically lags ~5 minutes behind the present**, so you cannot promise RPO = 0 for all incidents. Restoring large tables takes time, and cutover/reconciliation often takes longer than the restore API itself. Measure **end-to-end RTO** through real drills.

## 21. PITR: Continuous, Window-Bound, Non-Overwriting

**Point-in-time recovery (PITR)** maintains continuous backups used to restore a table's state to **a specific second** within the configured window.

### Key Fields to Know

| Field | Meaning |
| --- | --- |
| `PointInTimeRecoveryStatus` | `ENABLED` or `DISABLED` |
| `RecoveryPeriodInDays` | **1–35 days**, defaults to 35 if unset |
| `EarliestRestorableDateTime` | Oldest timestamp still restorable |
| `LatestRestorableDateTime` | Most recent restorable timestamp, **typically ~5 minutes behind now** |
| `RestoreDateTime` | User-chosen timestamp inside the valid window |
| `UseLatestRestorableTime` | Selects the most recent point the service can restore |

### Common Misconceptions

1. **PITR restore always creates a new table**; it never overwrites the source table in place.
2. Turning `PITR` on today does not let you restore data from last week when no recovery window existed.
3. If you **disable and re-enable PITR**, the previous recovery window resets per service rules; do not toggle it off for short-term savings without considering restore needs.
4. PITR and backups do not consume provisioned table RCUs/WCUs for snapshots/restores under AWS's model.
5. Selecting a timestamp after `LatestRestorableDateTime` or before `EarliestRestorableDateTime` causes the restore request to be rejected.
6. PITR **reflects table data at the restore timestamp**, not a point-in-time snapshot of all operational/IAM/alarm configurations.
7. With multi-table/multi-service workflows, restoring one table **does not guarantee system-wide causal/transactional consistency**; reconciliation is required.

### Accidental Deletion Timeline

~~~text
09:55:00 UTC  Normal orders
10:00:00 UTC  Faulty script deletes 100,000 records
10:02:00 UTC  Incident detected
10:05:00 UTC  LatestRestorableDateTime may still be before 10:00
                (always verify actual AWS value)
Pick a valid restore timestamp BEFORE the error, e.g. 09:59:50 UTC.
~~~

**Do not guess latest restorable time from a wall clock.** Always query it from the API, select UTC timestamps, and document **why that timestamp was chosen**. Valid writes occurring between the restore point and now must be **replayed/reconciled**, otherwise recent valid data is lost.

## 22. Lab: Enabling, Inspecting, and Alerting on PITR

### 22.1. Enable PITR on the Lab Table

~~~bash
aws dynamodb update-continuous-backups \
  --table-name OrdersHotLab \
  --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true,RecoveryPeriodInDays=35 \
  --region ap-southeast-1 \
  --profile lab
~~~

This command modifies the backup policy and incurs cost; it requires appropriate IAM permissions and an approved lab account.

### 22.2. Read Status + Recovery Window

~~~bash
aws dynamodb describe-continuous-backups \
  --table-name OrdersHotLab \
  --region ap-southeast-1 \
  --profile lab \
  --query 'ContinuousBackupsDescription.{Continuous:ContinuousBackupsStatus,PITR:PointInTimeRecoveryDescription}'
~~~

Sample output:

~~~json
{
  "Continuous": "ENABLED",
  "PITR": {
    "PointInTimeRecoveryStatus": "ENABLED",
    "RecoveryPeriodInDays": 35,
    "EarliestRestorableDateTime": "2026-11-19T03:00:00+00:00",
    "LatestRestorableDateTime": "2026-11-20T03:45:00+00:00"
  }
}
~~~

**Timestamps above are examples only.** Actual AWS timestamps may format slightly differently depending on CLI version; copy values **from the live response** and ensure your chosen restore timestamp lies within the valid window.

### 22.3. Designing Monitoring for Backup Policies

Monitor and audit:

- PITR `ENABLED` across every production table whose data classification requires protection.
- `RecoveryPeriodInDays` matching organizational policy.
- Latest/Earliest restorable windows and unexpected shifts.
- CloudTrail events for `UpdateContinuousBackups` and backup/restore/delete operations.
- AWS Config/CloudWatch/AWS Backup compliance rules per environment.
- Associated KMS keys/grants, especially during key rotation or deletion.
- Most recent restore drill and its pass/fail status; **having backups does not prove restores work**.

## 23. Hands-On PITR Restore: Always Choose a New Table Name

> **Never run a restore in production without change approval.** Restores can incur charges and create new resources. Never use example timestamps if they fall outside the table's real `EarliestRestorableDateTime..LatestRestorableDateTime`.

### 23.1. Restore to Latest Restorable Time

~~~bash
aws dynamodb restore-table-to-point-in-time \
  --source-table-name OrdersHotLab \
  --target-table-name OrdersHotLab-PITR-Restore \
  --use-latest-restorable-time \
  --region ap-southeast-1 \
  --profile lab
~~~

### 23.2. Restore to an Explicit UTC Timestamp

~~~bash
aws dynamodb restore-table-to-point-in-time \
  --source-table-name OrdersHotLab \
  --target-table-name OrdersHotLab-BeforeIncident \
  --restore-date-time "2026-11-20T03:00:00Z" \
  --region ap-southeast-1 \
  --profile lab
~~~

**The timestamp above is illustrative**; substitute an actual timestamp **prior to the incident** within the restorable window. Specify only one of `--restore-date-time` or `--use-latest-restorable-time` as needed.

### 23.3. Wait Until the New Table Is ACTIVE

~~~bash
aws dynamodb wait table-exists \
  --table-name OrdersHotLab-PITR-Restore \
  --region ap-southeast-1 \
  --profile lab

aws dynamodb describe-table \
  --table-name OrdersHotLab-PITR-Restore \
  --region ap-southeast-1 \
  --profile lab \
  --query 'Table.{Name:TableName,Status:TableStatus,Keys:KeySchema,Billing:BillingModeSummary,Indexes:GlobalSecondaryIndexes,Arn:TableArn}'
~~~

**Caution:** `wait table-exists` only confirms the table exists under waiter semantics; during drills, continue polling until **`TableStatus=ACTIVE`** before allowing production traffic. Never compare data or cut over while the table is still `CREATING`.

### 23.4. Data Verification

- Cross-check key business IDs and defined record counts.
- Verify uniqueness/transactional invariants and order/payment relationships.
- Verify GSIs have finished building and query paths succeed.
- Test data access via a **read-only verifier** before opening writes.
- Measure RTO from the restore decision until the API successfully uses the new table.
- Plan replay of valid writes after the restore timestamp; skipping this means the restored table **will lack all recent valid changes**.

## 24. On-Demand Backups: Snapshots and Restore

PITR handles second-granularity recovery over 1–35 days; **on-demand backups** handle key pre-migration snapshots and longer-term retention per policy.

### 24.1. Create a Backup

~~~bash
aws dynamodb create-backup \
  --table-name OrdersHotLab \
  --backup-name OrdersHotLab-before-schema-migration-20261120 \
  --region ap-southeast-1 \
  --profile lab
~~~

Save the `BackupArn` from the response. Backups are created **asynchronously** and become available after processing completes; check status before restoring.

### 24.2. Inspect Backups

~~~bash
aws dynamodb list-backups \
  --table-name OrdersHotLab \
  --region ap-southeast-1 \
  --profile lab

aws dynamodb describe-backup \
  --backup-arn "arn:aws:dynamodb:ap-southeast-1:111122223333:table/OrdersHotLab/backup/01234567890123-example" \
  --region ap-southeast-1 \
  --profile lab
~~~

`describe-backup` requires the **real BackupArn** from `create-backup`/`list-backups`. Never copy a dummy placeholder ARN literally.

### 24.3. Restore Backup to a New Table

~~~bash
aws dynamodb restore-table-from-backup \
  --target-table-name OrdersHotLab-BackupRestore \
  --backup-arn "arn:aws:dynamodb:ap-southeast-1:111122223333:table/OrdersHotLab/backup/01234567890123-example" \
  --region ap-southeast-1 \
  --profile lab
~~~

Wait for `ACTIVE`, validate data, indexes, IAM/KMS/configuration, and cut over just like PITR. **Backups and restores do not alter the source table** during normal restore operations.

### 24.4. Retention and AWS Backup

- DynamoDB on-demand backups do not automatically expire with the PITR window; set up **lifecycle/cleanup** or an AWS Backup plan to avoid lingering storage charges.
- **AWS Backup for DynamoDB** supports scheduled backup plans, retention, vaults, cross-account/cross-Region copies, and compliance controls.
- For **long-term immutable or organizational retention**, evaluate AWS Backup Vault Lock and cross-account policies per data governance.
- Tags, ABAC, KMS encryption, and backup/restore permissions follow specific rules; **never assume table tags or permissions automatically copy to backups or restored tables**.

## 25. Post-Restore: Which Configurations Must Be Rebuilt?

**Restoring creates a new table with data from the chosen point in time and certain restored table settings**, but **it does not carry over the entire operational environment verbatim**.

### Data/Schema Elements to Check

- Primary keys and table items/attributes.
- GSI/LSI/vector indexes where supported; verify **table/index status** and rebuild/restore behavior.
- Index and provisioned capacity settings may reflect **source configurations at an AWS-defined point**, not complete historical settings at the PITR timestamp.
- Billing mode, provisioned capacity, and encryption settings per restore options.
- KMS customer managed key policies/permissions during cross-Region or standard restores.
- DynamoDB item TTL attributes remain present as data, though the **TTL feature configuration** must be re-enabled if needed.

### Settings That Usually Need Manual Rebuilding or Review

| Component | Why post-restore action is needed |
| --- | --- |
| **Auto Scaling policies** | Capacity does not automatically inherit full policies from the old table |
| **IAM/resource-based policies** | New table ARN; consumers/roles may lack permission |
| **CloudWatch alarms & dashboards** | Reference old table dimensions/resources |
| **CloudWatch Contributor Insights** | Must be re-enabled and security-reviewed on the restored table |
| **Tags** | Restores do not automatically preserve tags per documentation |
| **DynamoDB Streams settings** | Do not assume Streams is enabled or keeps the old stream ARN |
| **TTL settings** | Must be reconfigured if the workload relies on automatic expiration |
| **PITR settings** | Restored table must have PITR enabled again per policy |
| **Deletion protection** | Must be verified and enabled per policy |
| **EventBridge Pipes/Lambda mappings** | Stream/table ARNs changed; mappings must be updated and reviewed |
| **VPC endpoints/IAM KMS network paths** | Connectivity and authorization must match the new resource |
| **Application table config** | Hardcoded table names or ARNs do not update themselves |
| **Global Tables replication** | A newly restored table is not automatically part of the existing global table across all scenarios |

**Important:** Do not enable `Streams` expecting it to replay all historical stream events from the old table. After PITR, if downstream read models need backfilling, plan a **scan/export/reconciliation** or replay events from a durable source.

### Keep the Restore Target Isolated Until Verified

A sound runbook holds the restored table in **quarantine / read-only verification** (via IAM permissions and feature flags) before canarying or cutting over. Avoid letting applications write new mutations into the restored table before indexes, mappings, and backups are fully configured.
## 26. Cutting Over to the Restored Table: Avoiding Loss of Valid Writes

**A successful restore does not automatically mean production is recovered.** Because the new table has a new name/ARN and holds data from a past timestamp, flipping app config without a reconciliation workflow risks losing valid updates written after that timestamp.

### Cutover Phases

~~~mermaid
flowchart TB
    Incident[Incident: data deleted / corrupted] --> Contain[Block destructive writes, preserve evidence]
    Contain --> Point[Select PITR timestamp / backup ARN]
    Point --> Restore[(Restore to NEW DynamoDB table)]
    Restore --> Check[Verify keys, items, GSIs, IAM/KMS, TTL, PITR]
    Check --> Reconcile[Replay / reconcile valid writes after restore]
    Reconcile --> Canary[Controlled canary reads / writes]
    Canary --> Decide{Data + SLO + security pass?}
    Decide -->|Yes| Cutover[Cutover application table config]
    Decide -->|No| Hold[Keep new table isolated and investigate]
    Cutover --> Monitor[Monitor consistency, errors, lag, cost]
    Monitor --> Cleanup[Backup/retire old table with approval]
~~~

### The Problem of Writes After the Restore Timestamp

Suppose:

~~~text
09:59:50Z   Chosen PITR restore point
10:00:00Z   Faulty script deletes 100,000 rows
10:01:00Z   Users place 200 valid orders in the source table
10:05:00Z   Incident response locks writes
10:20:00Z   Restored table ACTIVE at 09:59:50Z state
~~~

The restored table **does not contain those 200 valid orders placed after 09:59:50Z**. You cannot simply swap `TABLE_NAME` to the new table and declare recovery done.

Depending on architecture, apply one or more strategies:

- Use a **write-ahead / business event log** or transactional outbox containing enough events to replay valid operations after the restore point.
- Diff the **current source table** against the restored table to selectively keep valid rows while rejecting invalid updates, using version/timestamp/actor keys to distinguish them.
- Replay idempotently and in per-entity order where required.
- Pause writes or buffer them into SQS during the cutover window (with timeouts/DLQ/capacity controls).
- Run **read verification** followed by canary writes with a tested rollback path.
- Flag unverifiable records explicitly for manual investigation.

**Do not blindly "scan source and overwrite restored table"**, as you risk re-introducing accidental deletes or overwriting clean versions with corrupted state.

### Never Roll Back Applications Blindly

If you switch the app to the new table and then roll back to the old table 30 minutes later, the two tables have already diverged. Config rollback **does not roll back data**. Before enabling dual writes or switching back, define a clear source of truth and reconciliation logic.

## 27. Global Tables, Cross-Region Backups, and Disaster Recovery

### 27.1. Global Tables Is for Availability, Not a Substitute for PITR

**DynamoDB Global Tables** distributes data across Regions under supported models, enabling apps to read/write near users and keep running during regional incidents per your DR design.

~~~mermaid
flowchart LR
    Asia[Users Asia] --> RegionA[(DynamoDB Region A)]
    RegionA <-->|Global Tables replication| RegionB[(DynamoDB Region B)]
    Europe[Users Europe] --> RegionB
    RegionA --> BackupA[PITR / AWS Backup Region A]
    RegionB --> BackupB[PITR / AWS Backup Region B]
~~~

**Critical distinctions:**

- Global Tables replication is **application-level data synchronization under service semantics**, not an immutable backup.
- If a user/script accidentally deletes many items, those deletions **replicate to the other Regions**.
- With standard **MREC Global Tables**, cross-Region replication is eventual with model-specific conflict resolution; it does not promise cross-Region strong consistency.
- DynamoDB also offers **multi-Region strong consistency (MRSC)** for supported Regions/topologies/features. Never assume every Global Table is MRSC or design around MRSC without checking account/Region constraints.
- Global table replication and PITR/on-demand backups require **independent recovery strategies**, even with multiple replicas.

### 27.2. Cross-Region / Cross-Account Backups

For compliance/DR needs, evaluate **AWS Backup** to:

- Define scheduled backup plans and retention.
- Copy recovery points across supported accounts and Regions.
- Use backup vaults, resource policies, and appropriate KMS keys.
- Separate backup creation, deletion, copy, and restore permissions from application roles.
- Maintain a tested restore workflow inside the standby account/Region.

**Never assume the DR account has KMS decrypt/restore permissions** just because a backup copy succeeded; verify target-account key policies, resource ARNs, backup vault access, and IAM roles.

### 27.3. Minimum DR Runbook

1. Determine whether the incident is a **Region outage** or **logical corruption**.
2. Region outage with intact data → execute Global Tables failover / traffic routing per strategy.
3. Replicated logical corruption → **do not treat a corrupted global replica as truth**; recover from PITR or a clean backup.
4. Quarantine writes if necessary, preserve CloudTrail/operation logs, and pick the recovery point.
5. Restore/cut over, replay valid writes, and verify RPO/RTO.
6. Update Route 53/API Gateway/Lambda configs/IAM/KMS/VPC endpoints for the recovery Region.
7. Verify idempotency, conflict resolution, and network/client retry behavior.
8. Plan failback, re-establishing replication, and approved cleanup.

**Final RPO/RTO must be measured across end-to-end multi-component drills**, not merely the time until `RestoreTableToPointInTime` returns.

## 28. IAM, KMS, VPC, and Protecting Backups

### 28.1. IAM for Applications vs. Operations

Normal applications should need only data-plane APIs like `GetItem`, `Query`, `PutItem`, `UpdateItem`, and `DeleteItem` scoped to required tables/indexes.

**Never grant application runtimes permissions for**:

- `dynamodb:DeleteTable`
- `dynamodb:RestoreTableToPointInTime`
- `dynamodb:RestoreTableFromBackup`
- `dynamodb:UpdateContinuousBackups`
- `dynamodb:DeleteBackup`

Administrative backup/restore APIs belong exclusively to **operator / backup service roles** protected by MFA, change approval, and auditing as appropriate.

Example policy for a consumer reading the lab table:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOrdersTable",
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:Query",
        "dynamodb:DescribeTable"
      ],
      "Resource": [
        "arn:aws:dynamodb:ap-southeast-1:111122223333:table/OrdersHotLab",
        "arn:aws:dynamodb:ap-southeast-1:111122223333:table/OrdersHotLab/index/*"
      ]
    }
  ]
}
~~~

Separate roles for readers, writers, deployers, and backup admins. **A role with only `GetItem` cannot restore a table**—that is intentional least privilege.

### 28.2. AWS KMS

DynamoDB uses encryption at rest; depending on compliance, choose **AWS owned keys, AWS managed keys, or customer managed KMS keys**. With customer managed keys:

- Separate key administration from key usage.
- Verify the KMS key stays active and available for restores and cross-Region backup plans.
- Ensure backup vault / customer-managed key policies align with target table encryption.
- Avoid disabling or deleting a KMS key while dependent backups, tables, or restores still exist.
- Enable CloudTrail auditing for key operations per configuration.

### 28.3. VPC Endpoints

Lambda/ECS/EC2 workloads inside private VPCs calling the DynamoDB API can use:

- A **Gateway VPC endpoint for DynamoDB** via regional route tables and endpoint policies; or
- Approved network egress per architecture.

**DynamoDB APIs communicate over HTTPS/443.** There is no "database port 5432/3306" to connect directly to DynamoDB like RDS. DynamoDB tables do not live inside your private subnet; the endpoint enables **private resources in a VPC to reach the API** cleanly.

### 28.4. Encryption Does Not Replace Authorization

Encrypted data at rest can still be deleted if a principal holds `DeleteItem`/`DeleteTable` or valid API credentials. Guard against destructive deletions with:

- Least privilege, appropriate conditions/tags, resource-based policies, and SCPs.
- **Deletion protection** enabled on critical tables where supported.
- PITR and AWS Backup / Vault policies.
- CloudTrail/auditing and alarms when PITR is disabled or a table is deleted.
- Dedicated backup administrator roles/accounts and change control processes.

## 29. Cost: Hot Partitions Can Hurt Your Bill Both Ways

Main DynamoDB cost components:

| Component | Cost driver |
| --- | --- |
| **On-demand reads/writes** | RRUs/WRUs consumed by item size and consistency |
| **Provisioned table/GSI capacity** | Configured RCUs/WCUs (and Auto Scaling output) |
| **Storage** | Data size of table + indexes |
| **GSI** | Index storage + write/read throughput |
| **PITR** | Continuous backup billed by protected storage size; configured recovery period does not automatically scale down pricing by day count |
| **On-demand backups** | Backup storage and restore operations |
| **AWS Backup** | Backup vault/copy/cold tiers/restores per feature |
| **Global Tables** | Replicated writes/storage/cross-Region charges by Global Table type |
| **Export/Import to S3** | Data export/import and S3 storage/requests |
| **CloudWatch/Contributor Insights** | Metrics, Contributor Insights rules, logs/alarms |
| **Lambda/ECS/SQS/DAX** | Compute, queues, retries, caching |
| **KMS/network** | KMS API calls/key usage, VPC endpoints/traffic per config |

### How Does Throttling Cost Money?

A hot key can cause:

- Excessive SDK retries, longer Lambda durations, and client timeouts triggering repeated requests.
- Duplicate downstream processing charges when idempotency is missing.
- High provisioned WCU/GSI capacity sitting unused while a single key bottlenecks.
- Cache miss storms driving spikes in read request units.
- Growing SQS backlogs, DLQ redrives, and alerting costs.

**A single key-design fix can be orders of magnitude cheaper than raising total WCUs**, though you must weigh fanout read costs and migration expenses.

### Estimation Model

\[
C_{\text{monthly}} \approx C_{\text{throughput}}
+ C_{\text{table+GSI storage}}
+ C_{\text{PITR/backup}}
+ C_{\text{restore drills}}
+ C_{\text{Global Tables}}
+ C_{\text{compute+monitoring+KMS}}
\]

Never hardcode static USD rates across all Regions. Use the **AWS Pricing Calculator**, **Cost Explorer**, **AWS Budgets**, and tagging; measure cost **per successful business operation** rather than just cost per raw request.

## 30. Troubleshooting: Read the Symptoms Before Changing Capacity

| Symptom | Likely cause | Action |
| --- | --- | --- |
| Spare table capacity yet write throttling occurs | Hot key / physical partition | `TableWriteKeyRangeThroughputExceeded`, key cardinality, Contributor Insights |
| Base table healthy yet PutItem slows/fails | GSI write back-pressure | `IndexWrite...` reason + index ARN + GSI metrics |
| Provisioned table throttles near RCU/WCU ceiling | Insufficient provisioned capacity | Optimize queries, increase provisioned capacity, tune Auto Scaling min/max |
| On-demand workload spikes 10× | Previous peak / warm throughput exceeded | Pre-warm / ramp up, watch throttle metrics |
| On-demand throttles despite well-spread keys | Account limit or configured max | `AccountLimitExceeded` / `MaxOnDemandThroughputExceeded` |
| `BatchWriteItem` HTTP 200 yet records missing | Unprocessed items in `UnprocessedItems` | Retry only unprocessed items with backoff; persist permanent failures |
| SDK retries stall too long | Max attempts/deadline too high | Tune retry strategy, timeouts, queue/backpressure |
| GSI Query burns too many RCUs | Poor key design / Scan / FilterExpression | Use `KeyCondition`, pagination, projection/index redesign |
| Adaptive capacity does not cure hot key | Single ultra-hot item, LSI, or monotonic sort key | Sharding/aggregation, revise data model |
| Backup exists yet restore fails | KMS/IAM/backup status/wrong ARN | Check `DescribeBackup`, key policy, admin role |
| PITR lacks desired timestamp | Outside Earliest/Latest window or PITR just enabled | Check `DescribeContinuousBackups`, recovery period |
| Restore succeeded yet app still reads old table | Hardcoded table name/env/ARN | Config cutover, deployment/feature flag |
| Restored table missing streams/TTL | Settings are not automatically restored | Re-enable Streams/TTL and update mappings |
| GSI unqueryable right after restore | Index still building or missing GSI/config | Check `DescribeTable`/index status, test query |
| IAM `AccessDenied` after restore | New table ARN, missing ABAC tags | Update policies/tags, review IAM |
| PITR enabled yet lacks data from the last seconds | `LatestRestorableDateTime` lags ~5 minutes | Pick valid timestamp, reconcile newer writes |
| Restored table has old data but lacks recent orders | Timestamp predates valid writes | Replay events/outbox, reconcile |
| Global Tables still shows accidental deletions | Logical deletions were replicated | Use PITR/backups; never treat replicas as backups |
| Restore takes longer than SLO | Large table, index builds, cutover/reconciliation | Restore drills, measure RTO, DR runbook, capacity plans |
| PITR unexpectedly disabled | Configuration drift / permission issue | CloudTrail, AWS Config, backup policy guardrails |
| CloudWatch Contributor Insights exposes PII | Primary keys contain sensitive data | Redesign keys / restrict IAM / review before enabling |
| Cost rises even though QPS is flat | Item size / GSI / retries / backups / streams | Cost Explorer, SDK consumed capacity, table size |

### 10-Step Investigation Workflow

~~~text
1. Confirm account, Region, table ARN, and GSIs.
2. Capture DynamoDB exception + ThrottlingReasons + request ID.
3. Classify Table/Index, Read/Write, KeyRange/Provisioned/Account/MaxOnDemand.
4. Read CloudWatch + workload shape (Query/Scan/Batch/size/consistency).
5. If KeyRange, pinpoint hot keys via Contributor Insights or app metrics.
6. If GSI, inspect write back-pressure and index partition key design.
7. Apply backoff/jitter + idempotency + concurrency caps to contain impact.
8. Pick long-term fix: sharding, caching, index redesign, capacity mode.
9. If data corruption: check PITR window/backups, restore to new table,
   reconcile/cut over; never delete source before validation.
10. Re-measure throughput, throttle rate, p99 latency, RPO/RTO, and cost.
~~~

## 31. Practical Architecture: A Flash Sale That Recovers from Mistakes

~~~mermaid
flowchart TB
    Users[Web/Mobile] --> Gateway[API Gateway]
    Gateway --> Lambda[Lambda Order API]
    Lambda --> Limit[Per-tenant rate limiter]
    Limit --> DDB[(DynamoDB Orders with good PK)]
    Lambda --> Queue[(SQS OrderEvents)]
    DDB --> Stream[DynamoDB Streams]
    Stream --> Enrich[EventBridge Pipes / Lambda]
    Enrich --> ReadModel[(Read model / aggregates)]
    DDB --> PITR[PITR 1-35 days]
    DDB --> Backup[AWS Backup / recovery vault]
    PITR --> Restore[(New restored table)]
    Backup --> Restore
    DDB --> CloudWatch[CloudWatch metrics + alarm]
    Lambda --> CloudWatch
    Queue --> CloudWatch
~~~

### Before the Flash Sale

- Audit hot keys on base tables and GSIs; avoid single-value keys like `PK=EVENT#TODAY`.
- Calculate WCUs/RCUs by item size, forecasted traffic bursts, and warm throughput.
- Check on-demand previous peaks or provisioned Auto Scaling min/max and account quotas.
- Run approved load tests with concurrency caps using staging/canary data.
- Enable PITR and verify backup policies, IaC, and alarms.

### During the Flash Sale

- Monitor `ThrottlingReasons`, GSI back-pressure, SDK retries, and p95/p99 latency.
- Prioritize business commands and critical reads.
- Enforce backpressure: API rate limits, SQS buffering, bounded retries.
- Temporarily throttle back expensive analytics Scans/queries if needed.
- Enforce idempotency so client retries never duplicate orders.

### After an Incident

- If throttling only: diagnose hot keys/capacity; no restore needed.
- If data corruption: isolate the fault and choose a PITR/backup before the bad write.
- Restore to a **new table** and verify keys, indexes, tags, and permissions.
- Replay valid writes and cut over via feature flags/canary.
- Record actual RTO/RPO, reconciled data, and root cause.

**Never use restore to "fix" throttling caused by a bad partition key.** Without changing the data schema, the restored table carries the exact same hot-key layout.

## 32. Case Study A — Best-Selling Product Counter

**Facts:**

- Table provisioned at 15,000 WCUs.
- Every purchase updates a single item `PK=PRODUCT#X, SK=COUNTER`.
- 2,000 purchases/sec, item <1 KB.
- `TableWriteKeyRangeThroughputExceeded` climbs while total consumed WCUs stay at just a few thousand.

**Analysis:** The 15,000 provisioned WCUs are not exhausted; one item demanding ~2,000 writes/sec on a single key exceeds one partition's capacity. Adaptive capacity cannot exceed a partition's physical ceiling for one item.

**Solution:**

1. Enforce idempotency via `purchaseId` so one purchase never increments the counter twice.
2. Create **16 shards** for the counter (or an event aggregation architecture) to spread writes.
3. Query and sum shards for near-real-time totals, caching aggregated totals.
4. Audit missed/duplicate purchases via SQS/event logs and reconciliation.
5. Measure write throttles, unique successful purchase counts, read costs, and latency.

**Why not just add a GSI?** Adding a GSI on status or product name does not change how writes hammer that same hot item.

## 33. Case Study B — Accidental Deletion from a Batch Job

**Facts:**

- At 09:00 UTC a batch job uses the wrong filter and deletes 30,000 orders.
- PITR has been enabled since last month with a 35-day window.
- At 09:03 UTC the mistake is spotted; several valid new orders arrived between 09:00 and 09:03.
- The business requires recovering deleted data without losing the new valid orders.

**Suggested Runbook:**

1. Disable the faulty job/credentials, preserve logs/CloudTrail, and snapshot current state.
2. Describe PITR to verify whether `08:59:55Z` falls within the restorable window.
3. Restore to a new table `OrdersBeforeIncident`; do not cut over immediately.
4. Diff IDs/versions between the restored and source tables; classify the 30,000 deleted orders vs. new valid orders.
5. If an event source/outbox exists, replay valid writes after `08:59:55Z` **in order and idempotently**; verify status transitions.
6. Ensure tags/IAM/KMS/TTL/streams/PITR/alarms/indexes are configured on the new table.
7. Canary queries and business flows; execute a reviewed selective repair or full cutover.
8. Document **achieved RPO, actual RTO**, and any transactions unable to recover automatically.
9. Retain evidence and old backups per retention policy; clean up resources after approval.

**Lesson:** PITR restores past data, but it does not know which subsequent operations were valid. **Reconciliation** is what preserves business continuity.

## 34. Practical Exercises and Self-Check

### Exercise 1 — Capacity Units Analysis

A 6 KB item is read using strong vs. eventual vs. transactional reads. Compute the corresponding RCUs and verify `ceil(6/4)`. How many WCUs does a 2.2 KB write consume, and why do transactional writes cost more?

### Exercise 2 — Table Under WCU Limit Still Throttles

A table is provisioned at 20,000 WCUs; one hot partition key receives 1,800 writes/sec for ≤1 KB items. Error reason is `TableWriteKeyRangeThroughputExceeded`.

**Task:** Why won't raising WCUs to 40,000 necessarily fix this? Design 16-bucket write sharding and describe query fanout costs and idempotency.

### Exercise 3 — Hot GSI

The base table PK is an evenly distributed order UUID, while GSI PK=`status` only takes `NEW`/`PAID`/`FAILED`. Logs report `IndexWriteKeyRangeThroughputExceeded`.

**Task:** Point out the `/index/...` ARN suffix and propose a new GSI key using tenant/time/shard; describe query paging and merging.

### Exercise 4 — On-Demand Throttling

An on-demand table experiences a sharp request spike in <30 minutes after running at low load. `ThrottlingReasons` report `TableReadAccountLimitExceeded` and `TableReadMaxOnDemandThroughputExceeded` in two different environments.

**Task:** Distinguish service quotas from user-defined maximums; recommend warm throughput / peak ramp-ups, budget controls, and when to request a quota increase.

### Exercise 5 — Batch Partial Success

`BatchWriteItem` sends 20 PutRequests, and `UnprocessedItems` returns 4 requests.

**Task:** Write pseudocode that retries only those 4 items with backoff+jitter, deadline, DLQ, and metrics; explain why HTTP 200 is insufficient and why `BatchWriteItem` is not where uniqueness constraints belong.

### Exercise 6 — PITR Timestamp

`EarliestRestorableDateTime=2026-11-19T00:00:00Z`, `LatestRestorableDateTime=2026-11-20T03:45:00Z`. A script mistakenly deleted records at `2026-11-20T03:00:00Z`.

Pick a valid timestamp **before the incident**, explain why `2026-11-20T03:50:00Z` is invalid, and write the `restore-table-to-point-in-time` command targeting a new table name.

### Exercise 7 — App Fails After Restore

The restored table has data and GSIs, yet the Lambda API throws `AccessDeniedException`, Streams consumers receive no events, and TTL does not delete items.

**Task:** List the new IAM/resource policies/table ARN, Streams config/ARN/mapping, TTL settings, tags, alarms, and PITR that must be re-established.

### Exercise 8 — DR and Global Tables

An application uses two-Region DynamoDB Global Tables. An operator accidentally deletes all `TENANT#A` items in Region A, and the deletions replicate to B.

**Task:** Why isn't Region B a backup? Select PITR/AWS Backup plus a restore/reconciliation workflow, cross-Region KMS/IAM, traffic failover, and old-data fencing.

### Exercise 9 — Cost Modeling

Post-migration, an application handles 4 million eventual reads/day, 500,000 writes/day, three GSIs, 35-day PITR, weekly AWS Backups, and CloudWatch Contributor Insights.

**Task:** Build a cost model across item size, consistency, GSI write amplification, PITR table size, retention, backups, logs, KMS, and retries. Never assign fixed USD pricing without knowing the Region.

### 15 Quick Questions

1. **What is a hot partition?** A partition/key range receiving too much read/write traffic for its throughput capacity.
2. **Can a partition run hot even when the table has spare capacity?** Yes, due to physical partition limits.
3. **Roughly how many WCUs/RCUs does 1 partition handle?** Typically 1,000 WCU or 3,000 RCU/sec per AWS.
4. **Can a GSI throttle base table writes?** Yes, via GSI write back-pressure.
5. **Is adaptive capacity enabled automatically?** Yes.
6. **Can adaptive capacity exceed one partition's ceiling?** No.
7. **Can on-demand ever throttle?** Yes—hot partitions, rapid peaks, quotas, or configured max throughput.
8. **Is `ThrottlingReasons` more informative than the exception name?** Yes; it identifies the exact resource and limit type.
9. **Does `FilterExpression` save RCUs for read items?** No.
10. **Does `BatchWriteItem` HTTP 200 prove all items were written?** No; inspect `UnprocessedItems`.
11. **Up to how many days does PITR retain data?** 35, configurable from 1–35.
12. **Does PITR overwrite the source table?** No; it always creates a new table.
13. **Is `LatestRestorableDateTime` typically at the current second?** No, it usually lags by ~5 minutes.
14. **Does Global Tables replace backups/PITR?** No; accidental deletions replicate too.
15. **Does a newly restored table automatically keep all TTL/Streams/tags/PITR/alarms?** No; they must be reconfigured and verified.

## 35. Production Readiness Checklist

- [ ] Evaluated access patterns and partition key/cardinality for **the base table and all GSIs**.
- [ ] Team can distinguish hot items, hot key ranges, provisioned throughput, account limits, and configured on-demand max.
- [ ] Logging captures **ThrottlingReasons + resource ARN** without exposing sensitive primary keys or payloads.
- [ ] CloudWatch tracks consumed/provisioned/throttled/latency metrics per table/index against SLOs.
- [ ] Contributor Insights enabled where security/budget allows, monitoring most accessed/throttled keys.
- [ ] RCUs/WCUs calculated by item size and consistency; no misuse of Scan/`FilterExpression`.
- [ ] Reviewed adaptive capacity/split-for-heat, LSI restrictions, and monotonic sort-key limits.
- [ ] Hot write counters or low-cardinality GSIs use appropriate sharding/aggregation.
- [ ] Read sharding enforces fanout/concurrency caps, pagination, merge-sort, and idempotency.
- [ ] Selected on-demand/provisioned matching traffic, warm throughput/previous peak, Auto Scaling, and quotas.
- [ ] Implemented backoff+jitter, bounded attempts/deadlines, API rate limits, and SQS backpressure.
- [ ] Handled `BatchWrite` `UnprocessedItems`, `BatchGet` `UnprocessedKeys`, and business unique keys.
- [ ] PITR is `ENABLED` for protected tables with an approved recovery period window.
- [ ] On-demand backups / AWS Backup configured with schedules, retention, vaults, and cross-account/Region policies as required.
- [ ] Alerts configured for PITR disabled, table deletion, backup/restore failures, or backup permission changes.
- [ ] Verified `EarliestRestorableDateTime`/`LatestRestorableDateTime` and UTC timestamps.
- [ ] Conducted **restore drills to a new table**, verifying data, indexes, `ACTIVE` status, and measured RTO/RPO.
- [ ] Post-restore checklist covers IAM/ABAC/tags, KMS, autoscaling, TTL, Streams, alarms, PITR, and deletion protection.
- [ ] Replay/reconciliation plan exists for valid writes after the PITR timestamp without blindly copying corrupted data.
- [ ] Application cutover uses feature flags/config, canarying, and rollback **alongside a data strategy**.
- [ ] Global Tables / Region DR accounts for replicated deletes, conflicts, and cross-Region network/IAM/KMS.
- [ ] Database runtime least-privilege IAM is separated from backup/restore/deletion permissions.
- [ ] DynamoDB VPC gateway endpoints/routes/policies or HTTPS egress verified.
- [ ] AWS Budgets, Cost Explorer, and tags cover throughput, GSI storage, PITR, backups, logs, and KMS.
- [ ] Rehearsed hot partitions, GSI throttling, batch partial failures, PITR restores, and Region recovery.
- [ ] Runbooks define owners, change approval, key metrics, data validation, and post-incident cleanup.

## 36. Summary

**Hot partitions and throttling** come down to distributing load properly with **partition keys and GSI keys**, paired with capacity sizing and bounded retries. A table with abundant RCUs/WCUs can still throttle if writes pile onto a single item. Always read **`ThrottlingReasons` and the ARN**, distinguish **KeyRange / Provisioned / AccountLimit / MaxOnDemand**, and apply the matching fix: **key redesign, write sharding, caching, warm throughput, scaling, or quota increases**.

**Backups and recovery** solve a separate problem: **1–35 day PITR** restores to a specific second; **on-demand backups** preserve longer-lived snapshots; **AWS Backup** governs schedules, retention, copies, and vaults. **Restores always create a new table**, requiring data validation, rebuilding missing settings, and **replaying/reconciling valid writes** before cutover. **Global Tables does not replace backups** because mistakes and accidental deletions replicate too.

A well-operated DynamoDB system combines **data modeling, idempotency, load shedding, IAM/KMS/VPC controls, CloudWatch/Contributor Insights, PITR, backup drills, and AWS Budgets** to withstand both flash sales and operational mistakes.

### Official AWS Documentation

- [DynamoDB partitions and partition keys](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.Partitions.html)
- [Adaptive capacity and burst capacity](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/burst-adaptive-capacity.html)
- [Key design best practices](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-partition-key-design.html)
- [Write sharding data modeling](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/data-modeling-blocks.html)
- [Troubleshooting DynamoDB throttling](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/TroubleshootingThrottling.html)
- [Throttling reasons diagnostic workflow](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/throttling-diagnosing-workflow.html)
- [Key range throttling mitigation](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/throttling-key-range-limit-exceeded-mitigation.html)
- [GSI write throttling and back pressure](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/gsi-throttling.html)
- [On-demand capacity mode](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/on-demand-capacity-mode.html)
- [Warm throughput](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/warm-throughput.html)
- [CloudWatch Contributor Insights DynamoDB](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/contributorinsights_HowItWorks.html)
- [DynamoDB CloudWatch metrics](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/metrics-dimensions.html)
- [DynamoDB error handling and batch retries](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Programming.Errors.html)
- [AWS SDK Java v2 retry strategies](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/retry-strategy.html)
- [DynamoDB backup and restore overview](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Backup-and-Restore.html)
- [DynamoDB on-demand backups](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/CreateBackup.html)
- [DynamoDB point-in-time recovery](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Point-in-time-recovery.html)
- [Enable PITR](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/PointInTimeRecovery_Howitworks.html)
- [Restore DynamoDB table](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/pointintimerecovery_restores.html)
- [RestoreTableToPointInTime API](https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_RestoreTableToPointInTime.html)
- [DynamoDB with AWS Backup](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GettingStartedBackupsAWS.html)
- [DynamoDB Global Tables](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GlobalTables.html)
- [DynamoDB pricing](https://aws.amazon.com/dynamodb/pricing/)
- [AWS CLI DynamoDB reference](https://docs.aws.amazon.com/cli/latest/reference/dynamodb/)

**Operational Note:** Throughput limits, pricing, on-demand scaling, warm throughput, Global Tables consistency modes, AWS SDK defaults, and restore behaviors can change. Cross-check current AWS documentation for your **engine features, Region, and account**, and test in a lab account before modifying production tables or committing to RPO/RTO targets.



