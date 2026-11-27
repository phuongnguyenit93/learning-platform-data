# Conditional Writes, Optimistic Locking, and Consistency Choices

## 1. Context and Objectives

In the **AWS Data Services** chapter of the **Spring Cloud Provider Integration** module, Spring Boot connects to managed services using Spring Cloud AWS (AWSpring) and the AWS SDK. When working with Amazon DynamoDB, a `PutItem` or `UpdateItem` operation can succeed technically while still being **wrong from a business perspective** if two users update concurrently, a request is retried, or the application acts on stale reads.

Example: a property rental reservation service has a record:

~~~text
tenantId    = "tenant-a"                                    (partition key)
sortKey     = "RES#2026-11-24T08:00:00.000Z#res-1001"       (sort key)
state       = "PENDING"
version     = 1
propertyKey = "tenant-a#house-99"
createdAt   = "2026-11-24T08:00:00.000Z"
~~~

Two staff members may try to confirm or cancel a reservation at the same time. A worker may also retry a reservation creation request after a timeout. If the application simply reads an item and writes it back unconditionally, data is easily overwritten. This lesson focuses on three related mechanisms that address **three distinct needs**:

- **Conditional write:** DynamoDB only writes, deletes, or updates when a condition on the current item holds—for example, "create only if the key does not exist" or "confirm only if state is still PENDING".
- **Optimistic locking:** an item's `version` attribute is compared on update to detect whether someone else modified it since the previous read.
- **Read consistency:** the application selects *eventually consistent* or *strongly consistent* reads where supported; this choice governs how fresh observed data is, **but does not replace write conditions for concurrency protection**.

After this lesson, you will be able to:

1. Distinguish the semantics of `PutItem`, `UpdateItem`, and conditional writes.
2. Author conditions using `attribute_not_exists`, `attribute_exists`, state checks, and version checks in a single request.
3. Map an entity with `@DynamoDbVersionAttribute` from AWS SDK for Java v2 Enhanced Client and handle concurrent update conflicts.
4. Select read consistency for base tables, LSIs, and GSIs; understand the limits of global tables and multi-page consistency.
5. Integrate this logic into Spring Boot, configure IAM/credentials, test with DynamoDB Local, and determine when DynamoDB transactions are required.
6. Evaluate cost, retries, idempotency, and differences from Azure and Google Cloud managed data services.

> **Scope note:** examples use AWS SDK v2 Enhanced Client with DynamoDB. AWSpring versions may provide `DynamoDbTemplate` and matching auto-configuration, though support for specific operations depends on version. JPA's `@Transactional` does not automatically turn DynamoDB writes into transactions, and DynamoDB annotations are not JPA annotations.

## 2. What Happens When You Write Unconditionally?

### 2.1. Overwrites When Two Requests Read the Same State

Suppose A and B both read the item with `state=PENDING, version=1`:

~~~mermaid
sequenceDiagram
    participant A as Staff A
    participant B as Staff B
    participant DB as DynamoDB
    A->>DB: GetItem → PENDING, version=1
    B->>DB: GetItem → PENDING, version=1
    A->>DB: PutItem/UpdateItem state=CONFIRMED
    DB-->>A: Success
    B->>DB: PutItem/UpdateItem state=CANCELLED
    DB-->>B: Success if no condition is set
    Note over DB: B overwrote A's decision
~~~

DynamoDB executes each single-item write atomically, but atomic **does not mean** the application automatically detects stale decisions made from an earlier read. Without an appropriate condition or transaction, a later write can overwrite an earlier write's outcome.

### 2.2. Three Mechanisms Solving Different Risks

| Problem | Appropriate mechanism | Example condition |
| --- | --- | --- |
| Duplicate item created due to retried request | Conditional Put | `attribute_not_exists(tenantId)` on the item with the same composite key |
| Confirming an already-cancelled reservation | Conditional Update | `#state = :pending` |
| Two staff editing different fields from the same read | Optimistic locking | `#version = :expectedVersion`, then increment version |
| Modifying two items with all-or-nothing guarantee | DynamoDB transaction | `TransactWriteItems` with appropriate conditions |
| Must immediately read newly written data on the table | Strongly consistent read where supported | `ConsistentRead=true` on table/LSI |
| Newly written item not yet visible in GSI | Design for eventual consistency or read from base table | GSIs do not support strong reads |

**Core rule:** combining a "strongly consistent read" with an "unconditional write" **still fails to prevent** two requests from reading the same value and both writing. The final guard must be evaluated inside the **write request** (or within a transaction with appropriate semantics).

## 3. Preparing the Table and Spring Boot Application

### 3.1. Data Model

This example uses the `reservation_record` table:

| Attribute | Type | Role |
| --- | --- | --- |
| `tenantId` | String | Table partition key |
| `sortKey` | String | Table sort key, `RES#<UTC timestamp>#<reservationId>` |
| `reservationId` | String | Business reservation ID |
| `state` | String | `PENDING`, `CONFIRMED`, `CANCELLED` |
| `version` | Number | Version attribute for optimistic locking |
| `propertyKey` | String | Partition key of GSI `by-property` |
| `createdAt` | String | Sort key of GSI `by-property`, UTC string in matching format |

This example intentionally uses a composite key to clarify the creation condition: **one item** is identified by the pair (`tenantId`, `sortKey`), not by `tenantId` alone. Multiple distinct reservations for the same tenant can coexist.

`createdAt` and the timestamp segment inside `sortKey` must be normalized in UTC with fixed precision if you want chronological String-key queries. `version` is a monotonically increasing integer; never use client timestamps as versions because clocks are neither guaranteed unique nor synchronized.

### 3.2. Dependencies and Configuration

With AWSpring, the typical dependency is:

~~~xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-dynamodb</artifactId>
</dependency>
~~~

Use an **AWSpring BOM compatible with your Spring Boot version** to manage the starter and related AWS SDK dependencies. In projects without the starter, declare AWS SDK v2 `dynamodb` and `dynamodb-enhanced` under the AWS SDK BOM:

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

The Java code in this lesson uses `DynamoDbClient` for low-level write expressions and `DynamoDbEnhancedClient` for bean mapping. Compatible AWSpring versions can auto-configure these clients; if you define beans manually, do not duplicate beans already provided by the starter.

Example AWSpring configuration when deploying on AWS:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
      dynamodb:
        enabled: true
~~~

Use an IAM role/workload identity for workloads on ECS, EKS, or EC2 along with the default credential provider chain. Never hardcode AWS access keys, secret access keys, or session tokens into `application.yml`, source code, or Git.

### 3.3. Starting DynamoDB Local for Practice

~~~bash
docker run --rm --name dynamodb-local -p 8000:8000 amazon/dynamodb-local:latest
~~~

In Bash, set **dummy** credentials only in your testing terminal:

~~~bash
export AWS_ACCESS_KEY_ID=local
export AWS_SECRET_ACCESS_KEY=local
export AWS_DEFAULT_REGION=ap-southeast-1
~~~

Local profile configuration for AWSpring versions supporting these properties:

~~~yaml
# application-local.yml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
      dynamodb:
        endpoint: http://localhost:8000
~~~

Create the table and GSI used in subsequent sections:

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

Only attributes participating in table/GSI keys appear in `--attribute-definitions`; `state` and `version` are regular attributes. The table and index must exist before running the code. In production, provision via IaC (CloudFormation, CDK, Terraform), scope IAM permissions by resource, and measure access capacity.

## 4. Conditional Writes with DynamoDB

### 4.1. `ConditionExpression` Is Evaluated at Write Time

DynamoDB supports conditions on `PutItem`, `UpdateItem`, `DeleteItem`, and `ConditionCheck` inside transactions. The condition is evaluated **atomically against the target item as part of the write**: if the condition fails, the write does not apply and the API returns an error such as `ConditionalCheckFailedException`.

Useful condition expressions:

| Expression | Meaning | Use case |
| --- | --- | --- |
| `attribute_not_exists(tenantId)` | The key attribute does not exist on the target item | Create only if an item with the same primary key does not yet exist |
| `attribute_exists(tenantId)` | Target item already has the key attribute | Prevent an update from inadvertently creating a new item |
| `#state = :pending` | Current state is still PENDING | Confirm only reservations not yet processed |
| `#version = :expected` | DB version equals the version read by the request | Guard against writes based on stale reads |
| `#state = :pending AND #version = :expected` | Both business rule and optimistic lock hold | Safe state transition under concurrency |

In condition expressions, `#state` and `:pending` are placeholders mapped via `ExpressionAttributeNames` and `ExpressionAttributeValues`. Using placeholders for attribute names avoids collisions with reserved words and avoids interpolating user-supplied values directly into expressions.

**Composite key note:** when calling `PutItem` for key (`tenant-a`, `RES#...#res-2`), `attribute_not_exists(tenantId)` is checked on **the item identified by that full composite key**. Other items sharing `tenantId` with different sort keys do not cause the condition to fail.

### 4.2. Creating a Reservation Only If the Key Does Not Exist

This example uses the low-level SDK v2 client to show the condition and attributes written to the table explicitly. We **explicitly initialize `version = 1`** for new records; subsequent updates can go through the Enhanced Client with `@DynamoDbVersionAttribute`.

~~~java
import java.util.Map;
import org.springframework.stereotype.Repository;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.PutItemRequest;

@Repository
public class ReservationConditionalWriter {
    private final DynamoDbClient client;

    public ReservationConditionalWriter(DynamoDbClient client) {
        this.client = client;
    }

    public void createOnly(
            String tenantId,
            String sortKey,
            String reservationId,
            String propertyKey,
            String createdAt) {
        client.putItem(PutItemRequest.builder()
                .tableName("reservation_record")
                .item(Map.of(
                        "tenantId", s(tenantId),
                        "sortKey", s(sortKey),
                        "reservationId", s(reservationId),
                        "propertyKey", s(propertyKey),
                        "createdAt", s(createdAt),
                        "state", s("PENDING"),
                        "version", n(1)))
                .conditionExpression("attribute_not_exists(#pk)")
                .expressionAttributeNames(Map.of("#pk", "tenantId"))
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

If the **exact same full key** already exists, DynamoDB throws `ConditionalCheckFailedException`; the application should return a conflict error or handle duplicate submissions via a stable idempotency key. This is **not** a transient connection error to retry blindly.

Never generate a new `sortKey` using the current timestamp on each retry. If the original request succeeded on the server while the response was lost, retrying with a new key creates a second record and defeats duplicate protection. Business logic must retain a fixed ID/idempotency key, or store enough mapping state to reconstruct the exact same full key.

### 4.3. Conditional Update by State and Version

Suppose a client read `state=PENDING, version=1` and needs to transition to `CONFIRMED` only if **both state and version are unchanged**. `UpdateItem` updates specific attributes without resending the entire item.

~~~java
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;
import software.amazon.awssdk.services.dynamodb.model.ReturnValue;
import software.amazon.awssdk.services.dynamodb.model.UpdateItemRequest;
import software.amazon.awssdk.services.dynamodb.model.UpdateItemResponse;

// Method inside a class with field: DynamoDbClient client.
public UpdateItemResponse confirmIfPending(
        String tenantId, String sortKey, long expectedVersion) {

    return client.updateItem(UpdateItemRequest.builder()
            .tableName("reservation_record")
            .key(Map.of(
                    "tenantId", AttributeValue.builder()
                            .s(tenantId).build(),
                    "sortKey", AttributeValue.builder()
                            .s(sortKey).build()))
            .updateExpression(
                    "SET #state = :confirmed, #version = #version + :one")
            .conditionExpression(
                    "attribute_exists(tenantId) "
                    + "AND #state = :pending "
                    + "AND #version = :expected")
            .expressionAttributeNames(Map.of(
                    "#state", "state",
                    "#version", "version"))
            .expressionAttributeValues(Map.of(
                    ":confirmed", AttributeValue.builder()
                            .s("CONFIRMED").build(),
                    ":pending", AttributeValue.builder()
                            .s("PENDING").build(),
                    ":expected", AttributeValue.builder()
                            .n(Long.toString(expectedVersion)).build(),
                    ":one", AttributeValue.builder().n("1").build()))
            .returnValues(ReturnValue.ALL_NEW)
            .build());
}
~~~

Both the condition check and the version increment happen within **the same atomic item write**, leaving no race window between checking and writing. If the item does not exist, was already cancelled, or its version changed, the request fails. `ReturnValue.ALL_NEW` tells DynamoDB to return the updated item so the caller receives the new version without needing an extra `GetItem` right after every write.

For cancellation, use a similar condition with `:next=CANCELLED` and the corresponding expected states. When a transition is invalid, return a clear business error; when the version is stale, prompt the caller to reload and re-evaluate against fresh state.

### 4.4. Conditional Delete and When to Use Soft Delete

Like Update, `DeleteItem` also supports conditions. To require "delete only if version is still 3", specify `#version = :expected`; a modified item will not be deleted. In systems needing an audit trail, setting `CANCELLED` is usually preferable to physical deletion because records remain available for auditing, reconciliation, or customer support.

Choose deletion strategies based on retention periods, personal data policies, backups, and recovery requirements. DynamoDB TTL uses epoch seconds and deletes expired items asynchronously; TTL does **not** replace business expiration checks at request time.

## 5. Optimistic Locking with `@DynamoDbVersionAttribute`

### 5.1. How Does Optimistic Locking Work?

**Optimistic locking** assumes most updates do not conflict. Instead of holding a distributed lock while a user edits a record, each item carries a numeric `version` attribute:

1. A and B both read the item at `version=1`.
2. A sends an update conditioned on `version=1`; DynamoDB allows it and increments version to 2.
3. B sends an update also expecting `version=1`; the condition fails and the request is rejected.
4. B must re-read the item and decide whether to merge, ask the user to reconfirm, or abort.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant DB as DynamoDB
    A->>DB: Read state=PENDING, version=1
    B->>DB: Read state=PENDING, version=1
    A->>DB: Update if version=1
    DB-->>A: OK; new version=2
    B->>DB: Update if version=1
    DB-->>B: ConditionalCheckFailedException
    Note over B: Re-read and apply business logic
~~~

**Benefits:** avoids long-lived database locks; detects lost updates; works well under low contention. **Limitations:** any request working from a stale read must handle conflicts; this mechanism does not automatically pick the "business-correct" edit, does not lock the table, and does not turn multiple writes into a transaction.

### 5.2. Entity Mapping with the Enhanced Client

AWS SDK for Java v2 Enhanced Client supports `@DynamoDbVersionAttribute` via **`VersionedRecordExtension`**. Example entity:

~~~java
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbBean;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbPartitionKey;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbSortKey;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbSecondaryPartitionKey;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbSecondarySortKey;
import software.amazon.awssdk.enhanced.dynamodb.extensions.annotations.DynamoDbVersionAttribute;

@DynamoDbBean
public class ReservationItem {
    private String tenantId;
    private String sortKey;
    private String reservationId;
    private String propertyKey;
    private String createdAt;
    private String state;
    private Long version;

    public ReservationItem() {}

    @DynamoDbPartitionKey
    public String getTenantId() { return tenantId; }
    public void setTenantId(String value) { this.tenantId = value; }

    @DynamoDbSortKey
    public String getSortKey() { return sortKey; }
    public void setSortKey(String value) { this.sortKey = value; }

    public String getReservationId() { return reservationId; }
    public void setReservationId(String value) { this.reservationId = value; }

    @DynamoDbSecondaryPartitionKey(indexNames = "by-property")
    public String getPropertyKey() { return propertyKey; }
    public void setPropertyKey(String value) { this.propertyKey = value; }

    @DynamoDbSecondarySortKey(indexNames = "by-property")
    public String getCreatedAt() { return createdAt; }
    public void setCreatedAt(String value) { this.createdAt = value; }

    public String getState() { return state; }
    public void setState(String value) { this.state = value; }

    @DynamoDbVersionAttribute
    public Long getVersion() { return version; }
    public void setVersion(Long value) { this.version = value; }
}
~~~

**Verify imports:** `@DynamoDbVersionAttribute` resides in `software.amazon.awssdk.enhanced.dynamodb.extensions.annotations`, while key annotations reside in `software.amazon.awssdk.enhanced.dynamodb.mapper.annotations`. Ensure you use the exact SDK v2 package, as some IDEs may auto-import similarly named annotations from other libraries.

In the default Enhanced Client configuration, `VersionedRecordExtension` is typically registered automatically to compare and increment versions on supported writes. If your project calls `DynamoDbEnhancedClient.builder().extensions(...)` to **register custom extensions**, inspect the active extension list and include `VersionedRecordExtension` explicitly; never assume default extensions remain active when overriding the extension list.

### 5.3. Read–Modify–Write with Automatic Version Checking

~~~java
import org.springframework.stereotype.Repository;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbEnhancedClient;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbTable;
import software.amazon.awssdk.enhanced.dynamodb.Key;
import software.amazon.awssdk.enhanced.dynamodb.TableSchema;
import software.amazon.awssdk.enhanced.dynamodb.model.GetItemEnhancedRequest;

@Repository
public class ReservationVersionedRepository {
    private final DynamoDbTable<ReservationItem> table;

    public ReservationVersionedRepository(DynamoDbEnhancedClient client) {
        this.table = client.table(
                "reservation_record",
                TableSchema.fromBean(ReservationItem.class));
    }

    public ReservationItem loadStrong(
            String tenantId, String sortKey) {
        return table.getItem(GetItemEnhancedRequest.builder()
                .key(Key.builder()
                        .partitionValue(tenantId)
                        .sortValue(sortKey)
                        .build())
                .consistentRead(true)
                .build());
    }

    public ReservationItem updateStateOptimistically(
            ReservationItem previouslyLoaded, String nextState) {
        previouslyLoaded.setState(nextState);
        return table.updateItem(previouslyLoaded);
    }
}
~~~

In this example, `previouslyLoaded` is **a complete item previously read** from the table carrying its current `version`. The Enhanced Client enforces the version condition during `updateItem(...)`; if another write already changed the version, DynamoDB throws `ConditionalCheckFailedException`. The code in Section 4.3 provides an **explicit** approach when you need to combine version checking and state-transition rules in one expression.

If you pass a sparsely populated entity to `table.updateItem(...)`, null-mapping behavior may overwrite or delete omitted attributes depending on configuration/update semantics. For partial updates, select an appropriate API/ignore-null mode or use `UpdateItemRequest` with an explicit update expression. Never construct an object holding only key + version + state and assume the update leaves all other fields intact.

### 5.4. When Is Versioning Not Enough?

- **Business rules:** the version may still be fresh, yet business logic forbids `CANCELLED → CONFIRMED`. Enforce `state` checks or evaluate business preconditions atomically in the write condition.
- **Items missing a version:** legacy items lacking a `version` attribute do not follow the same optimistic locking contract. Plan migration/backfill strategies and clear initialization conditions.
- **Other writers bypassing versions:** if another worker issues raw `PutItem` without checking/updating `version`, it can overwrite data and break optimistic locking assumptions. Every writer must follow the same contract.
- **Multiple items changing together:** a version on one item cannot preserve an invariant spanning two items; use transactions or redesign the invariant when multi-item atomicity is required.
- **High contention:** many requests updating the same item continuously cause high failure rates and excessive retries. Consider queueing/serializing updates at the application layer or redesigning keys.

**Distinction:** optimistic locking checks *has anyone modified this item since I read it?*; conditional business writes check *does the current state permit this action?*. Both can be combined in the same write.

## 6. Strongly Consistent vs. Eventually Consistent Reads

### 6.1. Selection Table

By default, DynamoDB uses **eventually consistent reads** for standard read operations. You can request **strongly consistent reads** on the **base table** and **Local Secondary Indexes (LSIs)** where supported by the API. **Global Secondary Indexes (GSIs)** only support eventually consistent reads.

| Data source | Eventually consistent | Strongly consistent | Important notes |
| --- | --- | --- | --- |
| Base table | Yes; default for many read APIs | Yes, via `ConsistentRead=true` | Use when you must observe prior completed writes in the same Region |
| LSI | Yes | Yes | LSIs share the table's partition key and must be created with the table |
| GSI | **Yes** | **No** | GSIs update asynchronously and may lag behind the base table |
| DynamoDB Streams | Changes appear asynchronously | Not a strong-read table API | Designed for events/CDC; do not substitute for `GetItem` needing latest state |
| Multi-Region global tables | Depends on replication/consistency mode | Depends on global table mode | Strong read in one Region does not guarantee seeing writes from another Region |

**Strong consistency** on a table read guarantees observing all previously completed DynamoDB writes in that Region according to DynamoDB semantics; it does not prevent data from changing immediately after the read completes. **Eventual consistency** may return slightly stale data briefly after a write, but consumes less read capacity.

### 6.2. Reading via AWS SDK v2

Strongly consistent item read on the base table:

~~~java
import software.amazon.awssdk.enhanced.dynamodb.Key;
import software.amazon.awssdk.enhanced.dynamodb.model.GetItemEnhancedRequest;

ReservationItem latest = table.getItem(
        GetItemEnhancedRequest.builder()
                .key(Key.builder()
                        .partitionValue("tenant-a")
                        .sortValue(
                                "RES#2026-11-24T08:00:00.000Z#res-1001")
                        .build())
                .consistentRead(true)
                .build());
~~~

Above, `table` is the `DynamoDbTable<ReservationItem>` configured in Section 5.3. If the item does not exist, `latest` is `null`. Strong reads reduce the chance of acting on stale state right after a write; **version conditions on updates are still required**.

Base-table queries can also request strong reads:

~~~java
import software.amazon.awssdk.enhanced.dynamodb.Key;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryConditional;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryEnhancedRequest;

QueryEnhancedRequest tableQuery = QueryEnhancedRequest.builder()
        .queryConditional(QueryConditional.keyEqualTo(
                Key.builder().partitionValue("tenant-a").build()))
        .consistentRead(true)
        .limit(20)
        .build();

var pages = table.query(tableQuery);
~~~

When querying a **GSI**, do not set `consistentRead(true)`:

~~~java
var indexPages = table.index("by-property").query(
        QueryEnhancedRequest.builder()
                .queryConditional(QueryConditional.keyEqualTo(
                        Key.builder()
                                .partitionValue("tenant-a#house-99")
                                .build()))
                .limit(20)
                .build());
// GSI Queries are always eventually consistent.
~~~

If callers need an exact representation right after creating a reservation, return the record directly from the write response or re-read from the **base table** with strong consistency. Never rely on a GSI to verify a critical real-time invariant such as remaining availability.

### 6.3. Cost and Practical Impact

DynamoDB bills read capacity in data units; for equivalent items and conditions, **eventually consistent reads generally consume roughly half the read capacity of strongly consistent reads**. A 4 KB unit is commonly used in standard read capacity calculations; exact costs depend on capacity mode, item size, API type, and request volume.

As a rule of thumb: reading a 4 KB item with strong consistency consumes capacity equivalent to 1 read capacity unit; an eventually consistent read consumes about 0.5 under standard capacity math. Do not treat these units as fixed monetary prices, as pricing varies by Region, on-demand vs. provisioned mode, and other factors.

Conditional writes can consume read capacity when evaluating failing conditions and incur write costs when succeeding. Monitor `ConsumedCapacity`, throttling, latency, and `ConditionalCheckFailedException` rates rather than tracking only successful request counts.

## 7. Why Strong Reads Still Do Not Replace Transactions

### 7.1. The Race Window After a Read

~~~text
T0: A GetItem(ConsistentRead=true) -> state=PENDING
T1: B GetItem(ConsistentRead=true) -> state=PENDING
T2: A unconditional UpdateItem -> CONFIRMED
T3: B unconditional UpdateItem -> CANCELLED
~~~

Both reads can be strongly consistent and still suffer a **lost update**, because the item changed between read and write. Put the condition inside `UpdateItem` so DynamoDB checks state/version **at the exact moment of the write**.

### 7.2. Operations Requiring Multiple Items Atomically

Suppose confirming a reservation must simultaneously:

1. Transition `reservation.state` from PENDING to CONFIRMED.
2. Decrement `propertyInventory.available` by one.
3. Never drive inventory negative or confirm an already-cancelled reservation.

If executed as two separate `UpdateItem` calls, step 1 could succeed and step 2 could fail, leaving data inconsistent. When an invariant requires atomic all-or-nothing execution, use **`TransactWriteItems`** with per-item condition checks. DynamoDB transactions have their own rules, item/size limits, and costs; calling multiple repository methods under JPA's `@Transactional` does not make them a DynamoDB transaction.

~~~mermaid
flowchart LR
    A["Confirm reservation"] --> B{"Invariant spans multiple items?"}
    B -->|"No"| C["Conditional UpdateItem / version check"]
    B -->|"Yes"| D["TransactWriteItems<br/>Update reservation + inventory"]
    C --> E["Success or conflict"]
    D --> E
~~~

If the workflow also involves S3, SQS, or services outside DynamoDB, DynamoDB transactions do **not** span those services. Across multiple systems, use outbox patterns, idempotency keys, sagas/compensations, and bounded retries rather than assuming a cross-service transaction.

### 7.3. Multi-Page Scans/Queries Do Not Create Snapshots

`ConsistentRead=true` on a `Scan` (where supported) guarantees strongly consistent item-level reads, **but does not create a consistent snapshot across the entire Scan**. Similarly, a multi-page `Query` can observe changes occurring between page requests. When reports require an immutable point-in-time snapshot, use exports/backups or dedicated snapshotting rather than treating paginated queries as transactional snapshots.

## 8. Safe Writes Under Retries and Network Failures

### 8.1. Distinguishing Conflicts from Infrastructure Errors

| Error / Signal | Typical meaning | Remediation |
| --- | --- | --- |
| `ConditionalCheckFailedException` | Business/version condition no longer holds or item already exists | Return conflict, re-read, and re-evaluate business logic; never retry blindly forever |
| `TransactionCanceledException` | One operation caused the whole transaction to cancel | Inspect cancellation reasons; separate condition failures from throughput limits |
| `ProvisionedThroughputExceededException`, throttling | Table/GSI/partition hot or exceeding capacity | SDK retries with backoff/jitter and bounds; inspect metrics and capacity |
| `ResourceNotFoundException` | Wrong table/index name, account, endpoint, or Region | Verify IaC, configuration, and `DescribeTable` |
| `AccessDeniedException` | IAM role lacks required action or ARN | Check policy for both table and index |
| Timeout or `SdkClientException` | Uncertain whether the write reached the server | Evaluate idempotency; query/reconcile by deterministic key before retrying |

For create requests: **a client may fail to receive a response even though the server committed the write**. The solution is a deterministic idempotency key and key-based lookup. If retrying the same key raises `ConditionalCheckFailedException`, verify whether it represents the completed request itself or a different business action claiming that key; never blindly treat every conflict as success.

### 8.2. Retry Only with a Strategy

- **Optimistic conflict:** re-read the latest item, verify current state and user intent, and only then decide whether to retry with the new version. Blindly retrying can turn a "cancel" into a "confirm" unintentionally.
- **Throttling/transient errors:** use exponential backoff with jitter, cap retry attempts, elapsed time, and latency, and avoid retry storms.
- **Non-idempotent writes:** operations like incrementing a counter or generating a fresh ID per attempt require deduplication when a prior attempt's outcome is unknown.
- **Transactions:** use the API's client request token to obtain idempotency within DynamoDB's scope and retention window; still maintain durable request IDs if business rules require longer tracking.
- **Deadlines:** never block HTTP requests indefinitely; record pending state for follow-up or return a clear error.

### 8.3. HTTP Error Mapping

A reservation API can standardize responses:

| Scenario | Suggested response |
| --- | --- |
| Create-only with existing reservation ID | `409 Conflict` or idempotent response after verification |
| Update with stale version | `409 Conflict` with reload guidance; or `412 Precondition Failed` if using HTTP preconditions/ETags consistently |
| Item not found | `404 Not Found` |
| Unauthorized tenant access | `403 Forbidden` or conceal existence per API policy |
| Temporary DynamoDB throttling | `429`/`503` per contract, with appropriate retry headers/policy |

Never expose stack traces, sensitive ARNs, or other tenants' keys in responses. Log correlation IDs, request IDs, error codes, and metrics while redacting personal data, credentials, and sensitive payloads.

## 9. IAM and Multi-Tenant Access Boundaries

Minimal policy for an API that creates, updates, reads single items, and queries a GSI:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:Query"
      ],
      "Resource": [
        "arn:aws:dynamodb:ap-southeast-1:123456789012:table/reservation_record",
        "arn:aws:dynamodb:ap-southeast-1:123456789012:table/reservation_record/index/by-property"
      ]
    }
  ]
}
~~~

Replace Region, account ID, and table/index names with actual resources; separate roles by workload/function instead of granting broad permissions everywhere. If using `TransactWriteItems` or other APIs, grant only the exact permissions required per resource under least privilege.

In multi-tenant systems:

- Derive `tenantId` from the authenticated identity or authorization context—**never trust** an arbitrary tenant ID sent in the request body.
- Construct `propertyKey` from the verified tenant and a validated property ID; never let clients select another tenant's partition key.
- When using IAM conditions such as `dynamodb:LeadingKeys`, verify alignment with your key/identity model; IAM conditions do not replace business-layer authorization.
- Isolate dev/staging/prod roles; never let DynamoDB Local dummy credentials enter production.
- Protect personal data across items, logs, events, and backups; DynamoDB encryption at rest does not replace access control.

## 10. Integration Testing Conditional Writes and Optimistic Locking

Unit tests with mocked repositories validate service logic, **but do not prove** that condition expressions, version extensions, or consistency behaviors work against DynamoDB's schema. Test against DynamoDB Local/LocalStack with tables/indexes matching the target environment and with both `DynamoDbClient` and `DynamoDbEnhancedClient` pointing at the test endpoint.

### 10.1. Scenarios to Cover

1. **Create-only:** creating with a new key succeeds; creating again with the same key throws `ConditionalCheckFailedException`; creating an item with the same `tenantId` but a different `sortKey` succeeds.
2. **Transition condition:** confirming from PENDING succeeds, confirming from CANCELLED is rejected, and missing items are not upserted.
3. **Optimistic locking:** two reads see the same version; update A succeeds; update B with the stale version fails without overwriting A.
4. **Read consistency:** strongly consistent read on the base table observes a completed write; do not request strong consistency on a GSI. For GSIs, use bounded polling or assert eventual behavior rather than instant visibility.
5. **No unintended attribute loss:** when calling Enhanced Client `updateItem`, verify unrelated attributes preserve their values.
6. **Idempotent retry:** replaying a create request with the same key after a simulated timeout does not create a duplicate item; distinguish genuine conflicts from retries sharing the same request ID.
7. **Multi-tenant:** items belonging to other tenants are untouched, and the API rejects caller-chosen tenant overrides.
8. **Transaction rollback:** when one condition in `TransactWriteItems` fails, no item in the transaction is partially applied.

### 10.2. JUnit 5 Test for Optimistic Locking

The example below assumes `ReservationVersionedRepository` from Section 5.3 and `ReservationConditionalWriter` from Section 4.2 are registered as beans, and DynamoDB Local is running with table `reservation_record`.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Instant;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import software.amazon.awssdk.services.dynamodb.model.ConditionalCheckFailedException;

@SpringBootTest
@ActiveProfiles("local")
class ReservationOptimisticLockIT {
    @Autowired ReservationConditionalWriter writer;
    @Autowired ReservationVersionedRepository repository;

    @Test
    void staleUpdateMustNotOverwriteNewerState() {
        String tenantId = "it-" + UUID.randomUUID();
        String reservationId = "res-1";
        String createdAt = "2026-11-24T08:00:00.000Z";
        String sortKey = "RES#" + createdAt + "#" + reservationId;

        writer.createOnly(
                tenantId, sortKey, reservationId,
                tenantId + "#house-99", createdAt);

        ReservationItem first = repository.loadStrong(tenantId, sortKey);
        ReservationItem stale = repository.loadStrong(tenantId, sortKey);

        assertEquals(first.getVersion(), stale.getVersion());

        // Enhanced Client enforces the version condition during update.
        repository.updateStateOptimistically(first, "CONFIRMED");

        assertThrows(
                ConditionalCheckFailedException.class,
                () -> repository.updateStateOptimistically(
                        stale, "CANCELLED"));

        assertEquals(
                "CONFIRMED",
                repository.loadStrong(tenantId, sortKey).getState());
    }
}
~~~

This is a **test template to execute**, not proof of an already-run test. `updateStateOptimistically(...)` demonstrates version-based optimistic locking; a production service should also enforce valid state transitions via a condition expression as in Section 4.3 if business rules restrict `nextState`. The key assertion is that **the second request fails due to the stale version** and the item retains the state written by the first request.

For automated CI execution, use Testcontainers to start DynamoDB Local/LocalStack, create the table in setup, and inject endpoint/credentials into the Spring context. Use isolated test data per run, clean up by key, and avoid dependencies on prior test state.

### 10.3. Empirical Consistency Verification

You can structure the verification flow as:

~~~text
Step 1: PutItem to base table, response succeeds
Step 2: GetItem with ConsistentRead=true on base table -> new item is visible
Step 3: Query GSI by-property -> may or may not appear immediately
Step 4: Poll GSI with a deadline; confirm index eventually reflects the item
Step 5: Attempt ConsistentRead=true on GSI -> error/unsupported
~~~

DynamoDB Local may not replicate the exact propagation delays or distributed behavior of production DynamoDB. Therefore, local tests validate APIs, schemas, and exceptions; measuring real consistency/latency behavior requires an AWS test environment with controlled quotas and budgets.

## 11. Common Misconceptions

| Statement | True or false? | Explanation |
| --- | --- | --- |
| "DynamoDB single-item writes are atomic, so lost updates cannot happen." | False | Two atomic writes can still overwrite each other without conditions/versions |
| "A strongly consistent read prevents two users from overwriting each other." | False | Data can change after the read and before the write |
| "`PutItem` inserts only if the item doesn't exist by default." | False | Put can overwrite an existing item with the same primary key |
| "`attribute_not_exists(tenantId)` locks the whole tenant." | False | The condition is evaluated on the **target item** identified by the full primary key |
| "`@DynamoDbVersionAttribute` protects against raw writers ignoring versions." | False | All writers must adhere to the same version/condition contract |
| "GSIs support strong consistency if enabled on the Query request." | False | GSIs only support eventual consistency |
| "A consistent Scan produces a snapshot of the whole table." | False | Item-level strong reads do not create a snapshot across the whole Scan |
| "Always retry `ConditionalCheckFailedException`." | False | It usually indicates a business or optimistic locking conflict |
| "Spring JPA's `@Transactional` spans DynamoDB + S3 + SQS." | False | Coordination/transactions must be designed per system |
| "If a write times out, the DB definitely didn't commit it." | False | The outcome is ambiguous; use idempotency/reconciliation |

## 12. Advanced Practice Exercises

1. Build `POST /reservations` using create-only and a deterministic idempotency key. Submit the same request twice and distinguish duplicate retries from ID collisions across different customers.
2. Build `PATCH /reservations/{id}/state` transitioning PENDING → CONFIRMED only when both version and state match; return `409 Conflict` on stale versions with a reload contract.
3. Run two concurrent threads updating the same item from identical version reads. Compare outcomes with unconditional writes, state-conditioned writes, and Enhanced Client optimistic locking.
4. Read from the base table using eventual vs. strong consistency and query the same item via GSI; document theoretical guarantees alongside actual observations without extrapolating from a single run.
5. Design a transaction that confirms a reservation and decrements property inventory; add a condition preventing negative inventory, test partial condition failure, and verify no partial updates persist.
6. Simulate a timeout after a successful create-only write and replay the same request ID; verify no second reservation is created and the response follows the idempotent contract.
7. Compare version checking and consistency models when porting a workload from DynamoDB to Azure Cosmos DB or Google Cloud Firestore. Identify which business interfaces remain portable and which semantics must be implemented per provider.

**Completion criteria:** learners can explain why atomic writes, optimistic locking, conditional business writes, and strong reads provide distinct guarantees; implement a real concurrency scenario on DynamoDB; verify conflicts via integration tests; and choose appropriately among base-table reads, GSIs, and transactions.

## References

- [Amazon DynamoDB — Condition expressions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Expressions.ConditionExpressions.html): conditional Put, Update, and Delete.
- [Amazon DynamoDB — Read consistency](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadConsistency.html): eventual/strong consistency on tables, indexes, and global tables.
- [Amazon DynamoDB — Working with transactions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transactions.html): transaction APIs, characteristics, and limits.
- [Amazon DynamoDB — Error handling](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Programming.Errors.html): condition failures, throttling, and retries.
- [Amazon DynamoDB — Global tables consistency modes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/V2globaltables_HowItWorks.html): multi-Region replication and mode-specific consistency semantics.
- [AWS SDK for Java 2.x — DynamoDB Enhanced Client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/dynamodb-enhanced-client.html): bean mapping and Enhanced Client operations.
- [AWS SDK for Java 2.x — Use extensions](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/ddb-en-client-extensions.html): `VersionedRecordExtension`, `@DynamoDbVersionAttribute`, and custom extensions.
- [Spring Cloud AWS — Reference documentation](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html): dependencies, AWS identity, and version-specific auto-configuration.
