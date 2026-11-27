# Transaction Limits, Capacity, and Throttling Handling

## 1. Context and Objectives

In the **AWS Data Services** chapter of the **Spring Cloud Provider Integration** module, a Spring Boot application integrates AWS managed services via **Spring Cloud AWS (AWSpring)** or **AWS SDK for Java v2**. Amazon DynamoDB removes database infrastructure management, but that does not mean an application can write arbitrary numbers of items, store arbitrarily large items, or fire unlimited requests without rejection.

Three groups of constraints must be learned together:

- **Data limits:** single-item size, batch request size, Query/Scan page size, and index limits shape entity design and access paths.
- **Transaction limits:** DynamoDB transactions are bounded in size, scoped to a single account and Region, and can fail due to business conditions, concurrent conflicts, or insufficient capacity.
- **Throttling:** DynamoDB may throttle requests when read/write capacity consumption exceeds table/index/partition limits or quotas. Retries require backoff, idempotency, time bounds, and root-cause monitoring.

This lesson uses a running example: a property booking service. When confirming a booking, the system must **create a reservation record** and **decrement the property's remaining availability** as a single business unit: if no slots remain, no confirmed reservation may be created. Meanwhile, a flash sale can trigger write bursts leading to throttling.

After this lesson, you will be able to:

1. State and apply DynamoDB's core limits: **400 KB/item**, **100 actions and 4 MB/transaction**, batch sizes, and **1 MB/Query or Scan page**.
2. Distinguish atomic item operations, batch operations, and DynamoDB transactions; choose transactions when invariants span multiple items.
3. Construct conditional `TransactWriteItems` requests to create reservations and decrement availability without partial updates.
4. Interpret RCU/WCU and decide among on-demand, provisioned, indexes, and access patterns.
5. Handle throttling using exponential backoff + jitter retries, concurrency limits, and duplicate-reservation prevention.
6. Configure Spring Boot, IAM/roles, and DynamoDB Local endpoints, and test both business logic and overload scenarios.

> **Scope:** DynamoDB, RCU/WCU, transactions, and throttling are presented according to AWS semantics. Azure Cosmos DB and Google Cloud Firestore also enforce quotas, transactions, and retries, but their limits and indexing mechanics differ. When building multi-cloud applications, avoid applying DynamoDB limits directly to adapters for other providers.

## 2. Distinguishing Item Operations, Batches, and Transactions

From an application's viewpoint, **a successful write** and **a multi-write business action succeeding completely** are not the same thing.

| Mechanism | Purpose | Key guarantees | What not to assume |
| --- | --- | --- | --- |
| `PutItem`, `UpdateItem`, `DeleteItem` | Write/delete a single item by key | Single item operation is atomic; supports `ConditionExpression` | Multiple separate calls automatically form a transaction |
| `BatchWriteItem` | Send multiple Puts/Deletes efficiently | Up to 25 Put/Delete actions per request | Does not make the batch atomic; may return `UnprocessedItems` |
| `BatchGetItem` | Read multiple items by key | Up to 100 items per request; may return `UnprocessedKeys` | Not a transactional read snapshot; not an ad-hoc Query |
| `TransactWriteItems` | Put/Update/Delete/ConditionCheck multiple items atomically | Either all valid actions apply or none apply | Cannot exceed transaction limits; does not cover S3/SQS |
| `TransactGetItems` | Read a set of items transactionally | Consistent transactional read across supported scope | Not an ad-hoc filter/GSI query mechanism |

A transaction is only necessary when there is a **multi-item invariant**: for example, "creating a confirmed reservation must decrement remaining slots by exactly one". For independent log ingestion or bulk imports that can retry per item, batches are usually a better fit as long as the application handles partial success.

~~~mermaid
flowchart TD
    A["Business write operation"] --> B{"Single item only?"}
    B -->|"Yes"| C["Put/Update/Delete<br/>+ ConditionExpression if needed"]
    B -->|"No"| D{"Must all items succeed together?"}
    D -->|"Yes"| E["TransactWriteItems<br/>+ business conditions"]
    D -->|"No"| F["BatchWriteItem / queue worker<br/>+ handle UnprocessedItems"]
    E --> G["Check 100-action,<br/>4 MB, and contention limits"]
    F --> H["Retry with backoff,<br/>checkpointing, and idempotency"]
~~~

## 3. Data Limits to Remember Before Designing Schemas

### 3.1. Practical Limits Table

| Item | Limit / Constraint to remember | Design implication |
| --- | --- | --- |
| **Single item** size | Max **400 KB**, including attribute names and values as calculated by DynamoDB | Do not embed unbounded images, files, or huge JSON inside items; store blobs in S3 |
| Partition key value | Max **2,048 bytes** | Validate key size; measured in UTF-8 bytes |
| Sort key value | Max **1,024 bytes** | Avoid overly long composite keys or unchecked user input |
| `Query` / `Scan` | Each call processes up to **1 MB** before filter/projection, or stops at `Limit` | Use `LastEvaluatedKey` for pagination |
| `BatchWriteItem` | Max **25** Put/Delete requests and **16 MB** per call; each item still max 400 KB | Chunk batches and handle `UnprocessedItems` |
| `BatchGetItem` | Max **100 items** or **16 MB** per call; some keys may be unprocessed | Chunk keys and handle `UnprocessedKeys` |
| `TransactWriteItems` | Max **100 actions** on **distinct items**; total item payload max **4 MB** | Never bundle large bulk imports into one transaction |
| `TransactGetItems` | Max **100 items**; total read payload max **4 MB** | Use only for bounded key sets |
| Tables with **LSIs** | Item collection per partition key limited to **10 GB** | Watch out when one partition key accumulates massive item counts |
| GSIs | **Eventually consistent** reads only; indexes add storage/write cost | Never use a GSI as the source of truth for real-time slot allocation checks |

These figures represent core API/data-model constraints. **Account quotas, table/index counts, throughput, transaction sizes, on-demand/provisioned capacities, and Region-specific limits** may be updated by AWS. Check the latest quota documentation and **your account's Service Quotas** before setting operational thresholds; never hardcode a universal throughput limit across all tables and Regions.

### 3.2. Large Items Cause Cascading Effects

Suppose a reservation item contains:

~~~json
{
  "tenantId": "tenant-a",
  "reservationId": "res-1001",
  "state": "CONFIRMED",
  "guestCount": 4,
  "contractPdfBase64": "..."
}
~~~

Embedding an entire PDF contract or Base64 photo causes:

- Items easily approaching or exceeding the 400 KB ceiling.
- Every read/write consuming extra read/write capacity; wide-projection indexes duplicating even more data.
- Fewer items fitting inside the 4 MB transaction limit, raising latency and rejection risk.
- Heavy API responses that are difficult to paginate.

**Better design:** store files/contracts in **Amazon S3** with appropriate access controls, and keep only `s3Key`, `contentType`, `checksum`, `fileSize`, and needed metadata in DynamoDB. Because these are two separate services, a DynamoDB transaction cannot atomically commit an S3 object alongside an item; workflows need idempotency, upload status tracking, or cleanup of orphaned objects on failure.

### 3.3. Item Collection Limits with LSIs

If a table has a **Local Secondary Index**, total item collection size for a single partition key is capped at 10 GB under DynamoDB rules. A massive `tenantId` acting as the shared partition key for millions of records may hit scaling barriers even though a plain table without LSIs has no small fixed partition-collection cap. Revisit access patterns, indexes, and key partitioning if a tenant can grow huge. Never pick a hot key expecting extra GSIs to erase all limits automatically.

### 3.4. Keys and Byte Sizes

In Java, `String.length()` counts UTF-16 code units, not UTF-8 bytes. A partition key containing accented Vietnamese characters or emojis can consume multiple bytes per visible character. Validate using `value.getBytes(StandardCharsets.UTF_8).length` if keys derive from variable input; business IDs should use short, standardized formats.

## 4. Transaction Limits and Properties

### 4.1. What Do DynamoDB Transactions Guarantee?

`TransactWriteItems` executes a batch of `Put`, `Update`, `Delete`, or `ConditionCheck` actions with **all-or-nothing** semantics. DynamoDB evaluates all conditions and commits only when the entire transaction is valid. `TransactGetItems` reads multiple items by key under transactional read semantics.

Important boundaries:

1. A single transaction allows at most **100 actions** and **4 MB of total item data** per API rules.
2. All items must belong to **the same AWS account and Region**; they may span multiple tables within that boundary.
3. **Never target the same item twice inside one `TransactWriteItems` call**, such as issuing both a `ConditionCheck` and an `Update` on the same item. Put the condition in `ConditionExpression` inside the `Update` instead.
4. Transactions do not directly modify S3, SQS, RDS, Azure, or Google Cloud; atomicity applies strictly within DynamoDB's supported scope.
5. Transactions can fail due to failed conditions, validation errors, item size limits, insufficient capacity, throttling, or **transaction conflicts** from competing writes on the same item.
6. **GSIs and Streams update asynchronously** relative to base-table writes. A committed transaction does not mean an immediate subsequent GSI query reflects every change.

For multi-table/multi-item transactions, **every item's primary key must be known explicitly**; never run a `Scan` or GSI Query to pick arbitrary items assuming an unbounded transaction can lock that whole set.

### 4.2. Transactions and Batches Do Not Replace Each Other

Suppose you import 2,000 independent log items: creating 20 transactions of 100 items increases cost and unnecessary contention risk. Instead, send batches of 25 items, handle `UnprocessedItems`, checkpoint by message ID, and retry. Conversely, if you must decrement inventory **and** create a reservation simultaneously, two separate Put/Update calls or `BatchWriteItem` cannot enforce the invariant; a transaction is the right choice.

| Scenario | Appropriate mechanism | Why |
| --- | --- | --- |
| Ingesting 5,000 independent events | Batch/worker | Supports partial progress and per-item retries |
| Creating a new reservation without duplicate keys | `PutItem` with `attribute_not_exists` | Single item; atomic with a condition |
| Creating a reservation and decrementing slots | `TransactWriteItems` | Invariant spans two items |
| Checking and allocating inventory across warehouses | Transaction if within limits, or alternative domain design | Prevents negative inventory |
| Updating across DynamoDB + S3 + SQS | Outbox/saga/idempotency | DynamoDB transactions do not span external systems |

### 4.3. Transaction Costs and Contention

Transactional reads/writes generally consume **more capacity** than non-transactional operations for the same data size: the transactional protocol performs prepare and commit phases billed accordingly in capacity units. Therefore, do not wrap every CRUD operation in transactions "just to be safer". Reserve transactions for multi-item invariants, and use conditional writes for single-item operations.

Concurrent transactions modifying the same `inventoryKey` item will contend with each other. When a conflict occurs, one transaction can be canceled; retrying the entire transaction is only appropriate if **business conditions still hold**, keys/tokens remain deterministic, and retries are time-bounded. When heavy traffic converges on one hot item, aggressive retries only worsen contention.

## 5. Hands-On Problem: Atomically Creating a Reservation and Decrementing Inventory

### 5.1. Designing Two Tables

This example uses two tables in the same AWS account and Region:

**`reservation_record`**

~~~text
tenantId (PK, String)  | sortKey (SK, String)                  | state      | reservationId
tenant-a               | RES#2026-11-24T08:00:00.000Z#res-1   | CONFIRMED  | res-1
~~~

**`property_inventory`**

~~~text
inventoryKey (PK, String)            | available (Number)
tenant-a#house-99#2026-11-24         | 3
~~~

We model inventory per **property and single date**, assuming each slot represents one valid single-day booking. In real products, multi-night stays require tracking availability per night/range, touching multiple inventory items in a transaction, and validating against the 100-action and 4 MB limits. Never apply a single-day model to multi-night bookings while ignoring overlapping nights.

### 5.2. Creating Tables in DynamoDB Local

Use DynamoDB Local for practice without writing to an AWS account:

~~~bash
docker run --rm --name dynamodb-local -p 8000:8000 amazon/dynamodb-local:latest
~~~

In your development terminal, set **dummy** credentials and Region:

~~~bash
export AWS_ACCESS_KEY_ID=local
export AWS_SECRET_ACCESS_KEY=local
export AWS_DEFAULT_REGION=ap-southeast-1
~~~

Create the reservation table:

~~~bash
aws dynamodb create-table \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name reservation_record \
  --attribute-definitions \
    AttributeName=tenantId,AttributeType=S \
    AttributeName=sortKey,AttributeType=S \
  --key-schema \
    AttributeName=tenantId,KeyType=HASH \
    AttributeName=sortKey,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST
~~~

Create the inventory table:

~~~bash
aws dynamodb create-table \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name property_inventory \
  --attribute-definitions AttributeName=inventoryKey,AttributeType=S \
  --key-schema AttributeName=inventoryKey,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
~~~

Seed inventory:

~~~bash
aws dynamodb put-item \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name property_inventory \
  --item '{
    "inventoryKey":{"S":"tenant-a#house-99#2026-11-24"},
    "available":{"N":"3"}
  }' \
  --condition-expression 'attribute_not_exists(inventoryKey)'
~~~

Run the seed command once; if the item already exists, the condition rejects it instead of overwriting leftover counts from a previous test. In CI, use unique keys per test or provision isolated tables via Testcontainers and clean up afterward.

### 5.3. Transaction Using AWS SDK v2

In Spring Boot, you can inject a `DynamoDbClient` auto-configured by a compatible AWSpring starter or create an AWS SDK v2 bean yourself. The example below uses the low-level API to express **the exact write conditions**:

~~~java
import java.util.Map;
import org.springframework.stereotype.Service;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.Put;
import software.amazon.awssdk.services.dynamodb.model.ReturnConsumedCapacity;
import software.amazon.awssdk.services.dynamodb.model.TransactWriteItem;
import software.amazon.awssdk.services.dynamodb.model.TransactWriteItemsRequest;
import software.amazon.awssdk.services.dynamodb.model.Update;

@Service
public class ReservationBookingService {
    private final DynamoDbClient client;

    public ReservationBookingService(DynamoDbClient client) {
        this.client = client;
    }

    public void bookOneSlot(
            String tenantId,
            String propertyId,
            String stayDate,
            String sortKey,
            String reservationId,
            String idempotencyToken) {

        String inventoryKey =
                tenantId + "#" + propertyId + "#" + stayDate;

        // 1. Create the item only if the full primary key does not exist yet.
        TransactWriteItem createReservation =
                TransactWriteItem.builder()
                        .put(Put.builder()
                                .tableName("reservation_record")
                                .item(Map.of(
                                        "tenantId", s(tenantId),
                                        "sortKey", s(sortKey),
                                        "reservationId", s(reservationId),
                                        "state", s("CONFIRMED")))
                                .conditionExpression(
                                        "attribute_not_exists(#pk)")
                                .expressionAttributeNames(
                                        Map.of("#pk", "tenantId"))
                                .build())
                        .build();

        // 2. Decrement inventory only if the item exists and has slots left.
        TransactWriteItem decrementInventory =
                TransactWriteItem.builder()
                        .update(Update.builder()
                                .tableName("property_inventory")
                                .key(Map.of(
                                        "inventoryKey", s(inventoryKey)))
                                .updateExpression(
                                        "SET #available = #available - :one")
                                .conditionExpression(
                                        "attribute_exists(inventoryKey) "
                                        + "AND #available >= :one")
                                .expressionAttributeNames(
                                        Map.of("#available", "available"))
                                .expressionAttributeValues(
                                        Map.of(":one", n(1)))
                                .build())
                        .build();

        client.transactWriteItems(
                TransactWriteItemsRequest.builder()
                        .transactItems(
                                createReservation, decrementInventory)
                        .clientRequestToken(idempotencyToken)
                        .returnConsumedCapacity(
                                ReturnConsumedCapacity.TOTAL)
                        .build());
    }

    private static AttributeValue s(String value) {
        return AttributeValue.builder().s(value).build();
    }

    private static AttributeValue n(long value) {
        return AttributeValue.builder()
                .n(Long.toString(value)).build();
    }
}
~~~

**How the transaction protects data:**

- If `reservation_record` already holds an item with **the exact `tenantId + sortKey`**, the creation condition fails: **no reservation is created and inventory is not decremented**.
- If `available = 0`, the inventory condition fails: **no reservation is created and inventory is untouched**.
- If both conditions hold, the reservation is created and inventory decrements by one inside the transaction.
- If the transaction is canceled due to conflict or capacity, inspect the cancellation reason; never treat every transaction failure as "sold out".
- `sortKey` and `idempotencyToken` must stay constant for **the same booking intent**; never generate a fresh timestamp on retries.

**Important detail:** `idempotencyToken` maps to AWS's transaction `ClientRequestToken`, not an arbitrary unbounded string. It must satisfy API length/character rules. DynamoDB provides idempotency for identical requests/tokens within a **10-minute window** after the original request completes. Submitting the same token with changed parameters inside that window triggers `IdempotentParameterMismatchException`. Beyond that window, do not treat the token as permanent deduplication; maintain a deterministic `reservationId`/full key and an idempotency record according to business needs.

### 5.4. Spring Boot Configuration and Identity

For Spring Cloud AWS versions providing the DynamoDB starter and properties below:

~~~yaml
# application.yml - AWS environment
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
      dynamodb:
        enabled: true
~~~

~~~yaml
# application-local.yml - testing environment
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
      dynamodb:
        endpoint: http://localhost:8000
~~~

Use an **AWSpring BOM compatible with Spring Boot** if integrating via `io.awspring.cloud:spring-cloud-aws-starter-dynamodb`. When configuring plain SDK v2, use `software.amazon.awssdk:dynamodb` and build `DynamoDbClient` manually with region, credential provider chain, and `endpointOverride` for local runs; AWSpring properties do not automatically affect manually constructed clients.

Never put real access keys or secret keys in YAML. On ECS/EKS/EC2, prefer IAM roles/workload identities and grant DynamoDB permissions scoped to the exact tables and transaction actions. Likewise, never store passwords, tokens, or configuration secrets in reservation tables; use Secrets Manager, Parameter Store, or an appropriate secret manager.

### 5.5. Multi-Night Transactions and Exceeding Limits

For a 120-night reservation, updating **per-night** inventory items plus one reservation item exceeds the **100-action** transaction ceiling. You cannot raise this limit per request. Options to analyze:

- Narrow the invariant scope: partition calendars into appropriate buckets/ledgers and verify correctness.
- Use a `PENDING` / `CONFIRMING` hold workflow coordinating smaller transactions with compensations and idempotency.
- Change inventory representation so a single transaction touches fewer items.
- When full atomic booking is infeasible under current constraints, surface eventual/in-progress states explicitly in the business layer instead of confirming prematurely.

Splitting a 120-item transaction into two sequential 60-item transactions **does not equal one 120-item transaction**: after the first commits, the second may fail and leave partial state behind.

## 6. Capacity, RCU/WCU, and Why Throttling Still Happens

### 6.1. Visualizing Read/Write Capacity Units

DynamoDB uses capacity units to measure request work:

- **Read Capacity Unit (RCU):** under standard capacity accounting, one strong read of an item up to 4 KB equals 1 RCU; an eventual read of the same size consumes ~0.5 RCU; a transactional read equals ~2 RCU.
- **Write Capacity Unit (WCU):** one standard write of an item up to 1 KB equals 1 WCU, rounded up to the next 1 KB. Transactional writes generally consume twice the standard write capacity for the same item size.
- **GSIs:** writing items projected into GSIs consumes storage and write capacity on each index; projection choices and key updates affect total cost.
- **On-demand:** billed per consumed request unit under current pricing, requiring no manual throughput provisioning, yet still subject to quotas and partition distribution limits.
- **Provisioned:** configurable read/write capacity with optional auto scaling; exceeding provisioned limits triggers throttling.

Illustrative capacity for **a single 5 KB item** (excluding indexes/network/other overhead):

| Operation on a 5 KB item | Equivalent capacity in standard accounting |
| --- | --- |
| Standard write | `ceil(5 / 1) = 5` WCU |
| Transactional write | ~`10` WCU |
| Strong read | `ceil(5 / 4) = 2` RCU |
| Eventual read | ~`1` RCU |
| Transactional read | ~`4` RCU |

These numbers illustrate scaling behavior, **not an exact AWS bill**. Actual pricing varies by Region, table class, capacity mode, indexes, backups, data transfer, and service options. For multi-item transactions, account for each item plus affected indexes—never rely solely on JSON response sizes.

### 6.2. Where Can Throttling Come From?

~~~mermaid
flowchart TD
    A["Traffic spike"] --> B{"Limiting factor?"}
    B --> C["Table or GSI<br/>lacks capacity / quota"]
    B --> D["Hot partition key<br/>concentrated traffic"]
    B --> E["Transaction conflict<br/>on same inventory item"]
    B --> F["Account/Region quota<br/>or transient issue"]
    C --> G["Inspect metrics and capacity"]
    D --> H["Adjust keys / workload"]
    E --> I["Conditions, contention control"]
    F --> J["Verify quotas / retry"]
~~~

Common causes:

1. **Provisioned capacity:** provisioned read/write throughput is lower than demand, or auto scaling lags behind a sudden spike.
2. **On-demand or account quotas:** DynamoDB manages capacity automatically, yet request rates are not infinite; table/account quotas or abrupt traffic surges can still throttle.
3. **Hot partition/hot item:** heavy traffic hits a single partition key or inventory item. Local limits can trigger even when overall table capacity appears underutilized.
4. **GSI throttling:** an index has a hot key or insufficient capacity; base-table writes trigger index updates and can back-pressure when the index throttles.
5. **Transaction conflicts:** multiple transactions concurrently modify the same inventory item, causing contention; this is a concurrency issue requiring different handling than pure capacity throttling.

**Principle:** increasing provisioned throughput helps with table-wide capacity deficits, but does not automatically fix hot items or transaction conflicts. Always inspect **exact exception details, throttling reasons when exposed by the SDK/API, and CloudWatch metrics** before redesigning.

### 6.3. Keys, Indexes, and Load Splitting

Suppose every booking for a property updates:

~~~text
inventoryKey = "tenant-a#house-99#2026-11-24"
~~~

During a flash sale, every transaction contends on this single item. Options depend on business needs:

- Limit concurrency via per-property/date queues/workers, confirming in business order.
- Use reservation holds/tickets or inventory shards/buckets with safeguards ensuring total sales never exceed stock.
- Enforce idempotency and non-negative conditions; rapid blind retries amplify contention.
- Measure per-item/per-key throughput and traffic distribution; never shard prematurely on low traffic or when immediate exact consistency is mandatory.
- For read-only APIs, use key/index Queries and appropriate caching; avoid full-table Scans on high-traffic endpoints.

## 7. Controlled Throttling Handling

### 7.1. Classify Errors Before Retrying

| Error / Outcome | Typical meaning | Response |
| --- | --- | --- |
| `ProvisionedThroughputExceededException` | Exceeded provisioned throughput or related resource limits | Backoff/jitter; adjust capacity/load after measuring |
| `ThrottlingException` or `RequestLimitExceeded` | Request- or account-level throttling/quota limit | Bounded retries; inspect quotas and throttling reasons |
| `TransactionCanceledException` | A transaction member failed a condition, throttled, or conflicted | Inspect cancellation reasons; **never** blindly retry business conflicts |
| `TransactionConflictException` or conflict cancellation reason | Concurrent transaction contention on an item | Backoff, serialize/reduce contention, re-verify invariants |
| `ConditionalCheckFailedException` | Single-item condition failed | Handle as business conflict; never retry infinitely |
| `ValidationException` | Invalid key, payload, quota, or request shape | Fix request or design; retrying verbatim will not help |
| `ResourceNotFoundException` | Wrong table/index, Region, endpoint, or missing resource | Fix configuration; do not treat as throttling |
| Timeout / `SdkClientException` | Unclear whether server received/committed the write | Rely on idempotency and key lookup; do not assume failure |

Not all 4xx errors are non-retryable: throttling is typically retryable, whereas validation or failed conditions usually are not. Conversely, not every timeout proves a write never ran. **A sound retry policy aligns with operation semantics and outcome observability**, not exception names alone.

### 7.2. Exponential Backoff and Jitter

When requests are throttled, immediate retries from many clients worsen congestion. Use exponential backoff with jitter and bounded attempts.

With base delay `b` and attempt `k`, one *full jitter* formula is:

\[
d_k \sim U\left(0,\;\min(d_{\max},\,b\cdot 2^k)\right)
\]

For example, set `b = 100 ms`, `d_max = 5 s`, and up to 4 additional attempts. The actual wait is sampled uniformly within the computed bound; these values are illustrative and should be tuned to your SLOs and traffic profile.

~~~text
Initial call ────────────────────────────────┐
Throttled                                    │
Wait random in [0, 100 ms] ──────────────────┤ retry attempt 1
Throttled                                    │
Wait random in [0, 200 ms] ──────────────────┤ retry attempt 2
Throttled                                    │
Wait random in [0, 400 ms] ──────────────────┤ retry attempt 3
... up to configured max attempts/delay ...  │
                                             └── succeed or fail
~~~

AWS SDK for Java v2 already includes a **retry strategy**. Client-level configuration should be the default for retryable errors; avoid layering an extra service-level retry loop carelessly on top of SDK retries. Stacked retry layers multiply request volume during overload.

### 7.3. Example Retry Configuration in AWS SDK v2

This example uses `StandardRetryStrategy`, available in AWS SDK v2 versions supporting the newer retry API. On older SDK versions, check the `RetryPolicy` API rather than copying incompatible code.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.retries.StandardRetryStrategy;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

@Configuration
class DynamoDbClientConfiguration {
    @Bean
    DynamoDbClient dynamoDbClient() {
        return DynamoDbClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .overrideConfiguration(config -> config
                        .retryStrategy(StandardRetryStrategy.builder()
                                .maxAttempts(4)
                                .build()))
                .build();
    }
}
~~~

**API/version note:** `retryStrategy` and `StandardRetryStrategy` belong to the newer AWS SDK v2 retry API; on older releases, compare against `RetryPolicy` and plan upgrades carefully. `maxAttempts(4)` includes **the initial call**, allowing up to three retries. Standard retry strategy already applies backoff and jitter for retryable errors. When using an AWSpring starter that builds the client automatically, prefer the configuration/customizer hooks supported by your AWSpring version instead of defining a duplicate `DynamoDbClient` bean solely to tweak retries.

When finer backoff control is needed, configure `StandardRetryStrategy` or `AdaptiveRetryStrategy` as supported by your SDK version and measure the impact. **Adaptive retry** adds client-side rate limiting in response to throttling and works best when clients are isolated per throttling scope; avoid sharing a single adaptive client across unrelated tables with independent quotas.

### 7.4. Shedding Upstream Load Alongside Retries

Retries handle only **transient** spikes; when arrival rates exceed sustainable capacity, control load at the source:

- Bound **in-flight requests** via semaphores or appropriately sized thread pools.
- Offload ingestion/sync workloads to **SQS** with concurrency-bounded workers, visibility timeouts, DLQs, and idempotency.
- Tune batch sizes and polling cadence, inspect `UnprocessedItems`/`UnprocessedKeys`, and retry only unprocessed entries.
- Apply API **backpressure** (HTTP `429`/`503` and `Retry-After` where contracts permit).
- Monitor queue lag and latency; scaling workers blindly can worsen downstream bottlenecks.
- Separate interactive user requests requiring immediate responses from batch jobs that can wait.

Never block open controller connections with arbitrary long sleeps; favor bounded SDK retries and asynchronous processing where appropriate.

## 8. Idempotency and Ambiguous Transaction Outcomes

### 8.1. Timeouts Do Not Confirm Write Failure

~~~mermaid
sequenceDiagram
    participant API as Spring Boot
    participant DB as DynamoDB
    API->>DB: TransactWriteItems(token=K)
    DB->>DB: Commit succeeds
    Note over API,DB: Response lost / API timeout
    API->>DB: Retry same token K, same request
    DB-->>API: Idempotent result within API window
~~~

If a response is lost after commit, the client cannot tell whether inventory was decremented. Issuing **another transaction with a new reservation key or token** risks decrementing stock twice. Therefore:

1. Assign a deterministic `reservationId` and `sortKey` per **business intent**.
2. Derive `ClientRequestToken` deterministically from the request (within API length/charset limits), not per network attempt.
3. Include a conditional Put for the reservation inside the same transaction to guard against duplicates.
4. If retries outlive the idempotency window or hit a conflict, read the reservation back by its **full primary key** to reconcile state rather than decrementing inventory again.
5. Design API states distinguishing "completed", "in progress", "conflict", and "outcome pending" when needed.

`ClientRequestToken` is helpful, **but does not replace a durable business idempotency ledger** when duplicate prevention must span hours or days.

### 8.2. Avoiding Non-Idempotent Retry Bugs

Consider a raw `UpdateItem` running `SET available = available - :one` without a business condition or key guard. If the first attempt succeeded and its response dropped, replaying it decrements stock **twice**.

A transaction pairing a conditional Put on a deterministic reservation key provides protection: once the reservation exists, a second transaction with the same key fails the Put condition and cancels without decrementing inventory again. Always verify that the existing reservation matches **the same** business intent before returning an idempotent response; never blindly treat every `TransactionCanceledException` as success.

### 8.3. Retries and Concurrent Contention

Two guests competing for the last slot:

~~~text
Inventory available = 1
Request A: transaction Put(res-A) + Update inventory if available >= 1
Request B: transaction Put(res-B) + Update inventory if available >= 1

Acceptable business outcomes:
  - A succeeds, B is rejected; available = 0; only res-A exists
  - or B succeeds, A is rejected; available = 0; only res-B exists

Disallowed outcomes:
  - Both A and B are CONFIRMED when initial available was 1
  - available becomes negative, or a reservation exists without decrementing inventory
~~~

At the transaction level, one request may hit a **transaction conflict** before conditions are re-evaluated. When retrying after backoff, reuse the exact same reservation key/token and keep the `available >= 1` condition. Once availability reaches zero, report sold out rather than retrying endlessly until "winning".

## 9. Observability: Knowing Why Throttling Occurs

### 9.1. Metrics to Monitor

CloudWatch metrics and dashboards to track per table/index and business flow:

| Category | Example observations | Question answered |
| --- | --- | --- |
| Read/write capacity | `ConsumedReadCapacityUnits`, `ConsumedWriteCapacityUnits` | Where is real demand growing? |
| Throttling | `ReadThrottleEvents`, `WriteThrottleEvents`, `ThrottledRequests` where available/supported | Is the table or GSI throttling requests? |
| Latency | `SuccessfulRequestLatency` and service end-to-end latency | Is slowness from DB, retries, or app code? |
| Errors | `SystemErrors`, `UserErrors`, exception types | Infrastructure failure or request/business error? |
| Business | `booking_conflict`, `inventory_empty`, `transaction_cancelled` | Are last-slot collisions increasing? |
| Queues | Queue depth, age of oldest message, DLQ count | Are retries/backlogs building up during spikes? |

Analyze throughput, retry counts, transaction conflicts, latency, consumed capacity, and success rates **together**. Brief throttling spikes may recover cleanly with SDK retries; sustained throttling warrants investigating capacity, access patterns, or workload spikes.

### 9.2. Avoid Confusing Symptoms with Root Causes

- Transaction canceled due to `ConditionalCheckFailed`: typically a **business conflict**, not fixed by adding WCU.
- Transaction canceled due to throughput exhaustion: requires **capacity/backoff** and inspecting indexes/hot keys.
- Many clients updating a single `inventoryKey` item: indicates **contention**, requiring serialization or inventory redesign.
- GSI write throttling: can slow base-table writes even when base-table provisioned capacity looks healthy.
- Layered application retries: inflate total request volume far beyond user traffic; monitor retry amplification.
- Full-table Scans during peak hours: burn capacity and throttle online workloads even when filters return few items.

### 9.3. Safe Logging

Log operation names, correlation/request IDs, table/index names (as permitted), latency, retry counts, error categories, throttling reasons, and business statuses. Avoid logging AWS credentials, session tokens, full DynamoDB items containing personal data, or cursors exposing tenant keys. Multi-tenant systems must still enforce tenant checks in the service layer; a DynamoDB partition key **does not enforce tenant authorization automatically**.

## 10. IAM, Security, and Multi-Environment Operations

### 10.1. Least Privilege for Transactions

Spring Boot's IAM role should hold only the exact DynamoDB permissions needed on:

- `reservation_record` for `PutItem`/`GetItem` and required transaction actions.
- `property_inventory` for `UpdateItem`/`GetItem`, scoped to the appropriate account/resource conditions.
- If querying a GSI, include **the index ARN** and the corresponding `Query` action.
- Omit `DeleteTable`, `UpdateTable`, `Scan`, or policy-modification permissions when the service does not need them.
- Separate roles across online APIs, migrations/batch jobs, and dev/staging/production.

Verify exact IAM action names in DynamoDB's **IAM Service Authorization Reference** and check real resource/action dependencies. A transaction combining Put, Update, and ConditionCheck requires the corresponding underlying permissions; never assume a single "transaction" action covers everything.

### 10.2. Secrets and Identity

Prefer IAM roles/workload identities on ECS, EKS, and EC2; minimize long-lived static credentials. Secrets for services outside DynamoDB should live in Secrets Manager, Parameter Store, or an equivalent secret store. DynamoDB encrypts data at rest, yet TLS in transit, IAM permissions, service-layer tenant checks, and backup/restore procedures remain essential.

### 10.3. Backups and Recovery

When booking data is business-critical, evaluate Point-in-Time Recovery (PITR), backups, restore drills, storage/cost alarms, and data-corruption recovery plans. Backups do not replace transactions for preventing negative inventory at runtime.

## 11. Integration Testing, Failure Injection, and Load Testing

### 11.1. Functional Testing on DynamoDB Local

DynamoDB Local verifies schemas, transaction requests, conditions, and basic exceptions. Suggested scenarios:

1. **Successful transaction:** seed inventory `available=3`; call `bookOneSlot` with a new key; verify reservation exists and `available=2`.
2. **Sold out:** seed inventory `available=0`; invoke the transaction; verify no reservation is created and inventory stays 0.
3. **Create-only:** pre-create a reservation with the full key; invoke a duplicate transaction; verify inventory does not decrement again.
4. **Idempotency:** resend the same token and **same request** inside the supported window; verify it does not execute twice. Resend the same token with altered parameters; verify rejection.
5. **Concurrent last slot:** with `available=1`, run two concurrent requests with distinct reservations; only one may confirm, and inventory must never go negative.
6. **Transaction boundaries:** submit test requests exceeding 100 actions, >400 KB items, or >4 MB total payload in a test environment; verify validation errors are not retried.
7. **Permissions and endpoints:** test wrong AWS profile, wrong account/Region, missing table, or invalid credentials; verify clean error mapping.
8. **Cleanup:** use unique keys per test and delete test data afterward so runs do not interfere.

Example service-level assertion (requires configured beans, test starter, fixtures, and physical tables in CI):

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.GetItemRequest;
import software.amazon.awssdk.services.dynamodb.model.PutItemRequest;
import software.amazon.awssdk.services.dynamodb.model.TransactionCanceledException;

@SpringBootTest
@ActiveProfiles("local")
class ReservationBookingIT {
    @Autowired ReservationBookingService bookingService;
    @Autowired DynamoDbClient client;

    @Test
    void cannotBookWhenInventoryIsEmpty() {
        // Tables must exist in the DynamoDB Local endpoint.
        String tenant = "it-" + UUID.randomUUID();
        String property = "it-property";
        String date = "2026-11-24";
        String reservationId = "res-empty";
        String sortKey = "RES#2026-11-24T08:00:00.000Z#res-empty";
        String inventoryKey = tenant + "#" + property + "#" + date;
        client.putItem(PutItemRequest.builder()
                .tableName("property_inventory")
                .item(Map.of(
                        "inventoryKey", AttributeValue.builder()
                                .s(inventoryKey).build(),
                        "available", AttributeValue.builder()
                                .n("0").build()))
                .build());

        assertThrows(TransactionCanceledException.class, () ->
                bookingService.bookOneSlot(
                        tenant, property, date, sortKey, reservationId,
                        UUID.randomUUID().toString()));

        var inventory = client.getItem(GetItemRequest.builder()
                .tableName("property_inventory")
                .key(Map.of("inventoryKey", AttributeValue.builder()
                        .s(inventoryKey).build()))
                .consistentRead(true)
                .build());
        assertEquals("0", inventory.item().get("available").n());

        var reservation = client.getItem(GetItemRequest.builder()
                .tableName("reservation_record")
                .key(Map.of(
                        "tenantId", AttributeValue.builder()
                                .s(tenant).build(),
                        "sortKey", AttributeValue.builder()
                                .s(sortKey).build()))
                .consistentRead(true)
                .build());
        assertTrue(reservation.item().isEmpty());
    }
}
~~~

The example seeds inventory under a test-specific key, then reads back **both tables** to verify no partial update occurred. Both tables must exist on the DynamoDB Local endpoint with Spring Boot and test dependencies present. Use Testcontainers to provision tables in setup so CI stays machine-independent. This is sample test code to execute, **not a PASS report from a real test run**.

### 11.2. Throttling Is Not Faithfully Simulated Locally

DynamoDB Local generally **does not replicate real AWS partition distribution, adaptive capacity, quotas, or production throttling**. Therefore:

- Test retry/backoff code via unit/contract tests using stubs returning retryable vs. non-retryable exceptions, verifying permitted attempt counts.
- To validate real load limits, run **budgeted, quota-capped load tests** in a staging AWS account—never against production tables.
- Record CloudWatch metrics, latency, retries, conflicts, consumed capacity, key dispersion, and GSI behavior.
- Ramp load incrementally with strict guardrails on request rate, duration, and cost, plus an abort switch if throttling persists.

### 11.3. Analysis Exercise

Given two workloads:

- Workload A: ingesting 20,000 independent events per minute, small items, eventual processing acceptable.
- Workload B: 2,000 users competing for the last slot on a single `inventoryKey`.

Design each separately:

| Criterion | A – Event ingestion | B – Contending for one slot |
| --- | --- | --- |
| Write mechanism | Batch/queue + per-item retries | Transaction or atomic conditional write |
| Goal | High throughput without losing events | No overselling, consistent state |
| Main risks | UnprocessedItems, capacity, queue backlog | Hot item, transaction conflicts |
| Idempotency | Unique event ID, checkpointing | Fixed reservation ID/token, stock condition |
| Optimization | Batch size, worker concurrency, partition key | Serialization per inventory key, bounded retries |
| Testing | Burst load, retries/lag/DLQ | Concurrency, single winner, non-negative stock |

From this comparison, explain why—even when both look like "the system is slow"—adding more workers can help A while making B worse.

## 12. Production Readiness Checklist

1. **Schema:** every item under 400 KB; keys within byte limits; no oversized payloads; tables/GSIs/LSIs managed via IaC.
2. **Access patterns:** `GetItem`/`Query` on designed keys/indexes; no online full-table Scans.
3. **Transactions:** action count, item size, and 4 MB total checked; never touch the same item twice in one request; invariants encoded as conditions.
4. **Idempotency:** deterministic business IDs and transaction tokens; reconciliation plan for timeouts or expired token windows.
5. **Retries:** errors classified; SDK retries use jitter and limits; never retry business conflicts endlessly; backpressure/queues in place where needed.
6. **Capacity:** monitor RCU/WCU, GSIs, hot partitions, throttling, and transaction conflicts; verify real account/Region quotas.
7. **IAM:** least-privilege workload roles, APIs separated from batch jobs, no credentials in source code.
8. **Testing:** integration tests against real/emulated endpoints, concurrency tests, and cost-controlled AWS load tests.
9. **Operations:** metrics, alarms, redacted logging, DLQs, PITR/backups, and recovery runbooks.
10. **Multi-cloud:** isolate DynamoDB adapters behind business interfaces; document transaction/consistency/retry contracts per provider.

## 13. Self-Practice Questions

1. A reservation embeds a 600 KB Base64 contract image. Why cannot it be written to a single DynamoDB item? How should you redesign the object and file-storage workflow?
2. 80 reservation items must be updated and 30 inventory items decremented atomically. Why cannot all of them fit in one transaction? How does splitting into two transactions affect the invariant?
3. Why is `BatchWriteItem` unsuitable for simultaneously creating a reservation and decrementing inventory? How must `UnprocessedItems` be handled?
4. Choose between on-demand and provisioned capacity for a system experiencing daily traffic spikes. Which metrics should you measure before deciding?
5. A `TransactWriteItems` call times out even though DynamoDB committed it. Explain how `ClientRequestToken` and reservation keys prevent double-decrementing inventory.
6. When 500 guests concurrently update one inventory item, CloudWatch shows heavy transaction conflicts. Why might increasing WCU not be enough? Propose contention-reduction techniques.
7. A nightly Scan job consumes heavy read capacity and throttles online APIs. Redesign its schedule, concurrency cap, checkpointing, and alerting.
8. When migrating from DynamoDB to Azure Cosmos DB or Google Cloud Firestore, which transaction limits and operations must be re-verified instead of carrying over AWS assumptions?

## References

- [AWS DynamoDB — Quotas and constraints](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/ServiceQuotas.html): table, transaction, key, and item limits.
- [AWS DynamoDB — Transactions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transactions.html): `TransactWriteItems`, atomicity, idempotency, and cancellation scenarios.
- [AWS DynamoDB — Transaction conflicts](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html): contention behavior when accessing items.
- [AWS DynamoDB — Batch operations](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-batch-operation.html): batches, request sizes, and unprocessed items.
- [AWS DynamoDB — Read/write capacity mode](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadWriteCapacityMode.html): on-demand, provisioned, and evaluation guidance.
- [AWS DynamoDB — Read/write capacity unit consumption](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/read-write-operations.html): item sizes and RCU/WCU math.
- [AWS DynamoDB — Throttling diagnostics](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/throttling-diagnosing-workflow.html): causes, throttling reasons, and metrics.
- [AWS DynamoDB — Error handling](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Programming.Errors.html): errors, retries, and backoff.
- [AWS SDK for Java 2.x — Retry strategy](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/retry-strategy.html): retry modes, jitter, and SDK configuration.
- [AWS SDK for Java 2.x — DynamoDB Enhanced Client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/dynamodb-enhanced-client.html): data mapping and high-level APIs.
- [Spring Cloud AWS — Reference documentation](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html): DynamoDB starter, AWS identity configuration, region, and endpoint.
