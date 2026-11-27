# Reading and Writing Data, Querying Indexes, and Pagination

## 1. Context and Objectives

In the **AWS Data Services** chapter of the **Spring Cloud Provider Integration** module, a Spring Boot application needs to access AWS-managed data services securely and scalably. With **Amazon DynamoDB**, reading and writing is not just basic CRUD: developers must also choose the right keys, understand indexes, control the capacity consumed per read, and handle pagination properly.

The running example is a reservation service in a multi-tenant application:

- Table `reservation_record` stores reservations.
- **Partition key** `tenantId` identifies the organization owning the record.
- **Sort key** `sortKey` has the format `RES#2026-11-24T08:30:00.000Z#res-1001`.
- **Global secondary index (GSI)** `by-property` retrieves reservations for a property over time: partition key `propertyKey` and sort key `createdAt`.
- Core flows: create a reservation, read one reservation, update status, delete, list by month, list by property, and return paginated results.

After this lesson, you will be able to:

1. Distinguish `GetItem`, `PutItem`, `UpdateItem`, `DeleteItem`, `Query`, and `Scan` by their actual behavior.
2. Perform **conditional** writes to prevent duplicates or unintended overwrites.
3. Query tables and GSIs by partition key + sort key conditions, while understanding eventual vs. strong consistency.
4. Implement controlled pagination using `LastEvaluatedKey` and `ExclusiveStartKey` without loading the entire result set into memory.
5. Structure a Spring Boot repository using **AWS SDK for Java v2 Enhanced Client** and understand when to use **Spring Cloud AWS (AWSpring)**'s `DynamoDbTemplate`.
6. Test with DynamoDB Local, configure IAM/region/endpoint, and evaluate cost, quotas, retries, and cursors for production.

> This lesson focuses on AWS's DynamoDB model. Azure Cosmos DB and Google Cloud Firestore have their own partitioning, query/index, permission, and continuation token mechanisms. The business layer should expose clear interfaces when multi-cloud integration is required, without assuming SDKs share the same APIs or guarantees.

## 2. How Do Reads and Writes in DynamoDB Differ from SQL?

### 2.1. Operation Decision Table

| Operation | Purpose | Key inputs | Things to note |
| --- | --- | --- | --- |
| `GetItem` | Read **one** item | Full primary key (PK, and SK if present) | Cannot look up directly by non-key attributes |
| `PutItem` | Write an entire item under a key | Item with complete primary key | Can **replace an existing item with the same key** if no condition is specified |
| `UpdateItem` | Modify an item/attributes | Primary key, changes, optional condition | Enhanced Client null-handling/update semantics must be checked |
| `DeleteItem` | Delete an item by key | Full primary key; optional condition | Can delete data unintentionally if permissions are not controlled |
| `Query` | Read items by table/index key | Partition key equal to a specific value; optional sort key condition | Paginated; ordered by sort key within a partition key |
| `Scan` | Sweep across a table/index | Optional filter and projection | Easily consumes large RCU; never use as the default for large views |
| `BatchGetItem`/`BatchWriteItem` | Execute multiple reads or writes/deletes | Multiple keys/items | Must handle `UnprocessedKeys`/`UnprocessedItems`; not atomic as a whole |
| `TransactWriteItems`/`TransactGetItems` | Group operations with transactional guarantees | List of operations within DynamoDB limits | API and cost differ from batch; cannot be replaced by JPA annotations |

DynamoDB allows items to have flexible attributes, but **the primary key and secondary index keys must match the names and types** defined when the table/index was created. For a table keyed by `tenantId` and `sortKey`, `GetItem` cannot take only `reservationId` and look it up automatically; the application must know the full key or have a dedicated access pattern, index, or lookup item.

### 2.2. Choosing Operations by Access Pattern

~~~mermaid
flowchart TD
    A["Application needs data"] --> B{"Know full PK + SK?"}
    B -->|"Yes, exact 1 item"| C["GetItem"]
    B -->|"No, know partition key"| D["Query table or index"]
    B -->|"No, only non-key attribute"| E{"Matching index exists?"}
    E -->|"Yes"| F["Query index"]
    E -->|"No"| G["Design access pattern / index<br/>Scan only with clear justification"]
    D --> H["Control pagination"]
    F --> H
~~~

Distinguish between **filtering results** and **locating data**. `KeyConditionExpression` narrows the key range DynamoDB accesses; `FilterExpression` discards items **after DynamoDB has already read them**. Consequently, filtering `state = "CONFIRMED"` across millions of items via `Scan` can consume massive read capacity even if the final response is tiny.

## 3. Preparing the Table, Index, and Libraries

### 3.1. Illustrative Data Model

| Attribute | DynamoDB Type | Role |
| --- | --- | --- |
| `tenantId` | String | Table partition key |
| `sortKey` | String | Table sort key: `RES#<UTC time>#<reservationId>` |
| `reservationId` | String | Business identifier |
| `propertyId` | String | Property identifier |
| `propertyKey` | String | Partition key of GSI `by-property`: `tenantId#propertyId` |
| `createdAt` | String | GSI sort key, uniformly formatted UTC string |
| `state` | String | `PENDING`, `CONFIRMED`, `CANCELLED` |
| `guestCount` | Number | Guest count |

Example:

~~~text
Primary key (table):         tenantId    + sortKey
GSI by-property:             propertyKey + createdAt

tenantId | sortKey                              | propertyKey      | createdAt                 | state
---------+--------------------------------------+------------------+---------------------------+----------
tenant-a | RES#2026-11-24T08:30:00.000Z#res-1   | tenant-a#house-1 | 2026-11-24T08:30:00.000Z  | PENDING
tenant-a | RES#2026-11-24T09:00:00.000Z#res-2   | tenant-a#house-2 | 2026-11-24T09:00:00.000Z  | CONFIRMED
tenant-b | RES#2026-11-24T08:30:00.000Z#res-1   | tenant-b#house-1 | 2026-11-24T08:30:00.000Z  | CONFIRMED
~~~

**Design trade-off:** querying "all November reservations for a tenant" using a `sortKey` prefix is very convenient. However, an API to "find by reservationId without knowing the timestamp" cannot use `GetItem` with this key. If that is a primary query, consider changing the sort key to `RES#reservationId` and creating a GSI for time-based queries, or maintaining a separate lookup item. Never use `Scan` to compensate for an unmodeled access pattern.

Timestamps stored inside String keys should be in **UTC, with consistent precision (milliseconds) and full zero-padding**; otherwise, string order may diverge from chronological order. Key-generation code must follow one consistent rule and control delimiters so two different ID pairs cannot produce the same string.

### 3.2. Maven with AWSpring or Plain SDK v2

In a Spring Boot application using Spring Cloud AWS, you can declare the starter (managing the version via a BOM compatible with Spring Boot):

~~~xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-dynamodb</artifactId>
</dependency>
~~~

The DynamoDB Enhanced Client uses these AWS SDK v2 dependencies:

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

When using the starter, inspect the dependency tree and BOM: you do not necessarily need to re-declare artifacts already pulled in by the starter. **Do not arbitrarily mix AWSpring/Spring Boot/AWS SDK versions**; do not assume `DynamoDbTemplate` exists in every release. The main Java examples in this lesson use the Enhanced Client so index operations and page boundaries remain explicit.

### 3.3. Configuring Identity, Region, and Endpoint

For AWSpring versions that support the properties below:

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

Production applications should obtain credentials via an **IAM role/workload identity** and the credentials provider chain—never store static access keys or secret keys in YAML or source code.

Local profile example:

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

With a **manually constructed AWS SDK v2 client** (without AWSpring auto-configuration), you must configure the region and `endpointOverride` yourself; `spring.cloud.aws.dynamodb.endpoint` has no effect on a manually created client bean that does not read that property.

Run DynamoDB Local:

~~~bash
docker run --rm --name dynamodb-local -p 8000:8000 amazon/dynamodb-local:latest
~~~

In your local terminal, set **dummy** AWS credentials (`AWS_ACCESS_KEY_ID=local` and `AWS_SECRET_ACCESS_KEY=local`) so the AWS SDK/CLI has credentials to sign requests. Only use dummy values against the local endpoint; when deploying to real AWS, use an IAM role and the default endpoint.

### 3.4. Creating the Table and GSI

Bash / AWS CLI against DynamoDB Local:

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

The `--attribute-definitions` parameter lists only attributes participating in table/index keys, not every data field. `ProjectionType=ALL` is convenient for learning, though it increases storage and write costs; production systems should evaluate `KEYS_ONLY` or `INCLUDE`.

Verify:

~~~bash
aws dynamodb describe-table \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name reservation_record
~~~

In real AWS environments, create tables and indexes via **Infrastructure as Code**. The Spring starter, `@DynamoDbBean`, and `TableSchema.fromBean` **do not create tables automatically**.

## 4. Defining the Entity and Spring Boot Repository

### 4.1. Mapping with `@DynamoDbBean`

~~~java
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbBean;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbPartitionKey;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbSecondaryPartitionKey;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbSecondarySortKey;
import software.amazon.awssdk.enhanced.dynamodb.mapper.annotations.DynamoDbSortKey;

@DynamoDbBean
public class ReservationItem {
    private String tenantId;
    private String sortKey;
    private String reservationId;
    private String propertyId;
    private String propertyKey;
    private String createdAt;
    private String state;
    private Integer guestCount;

    public ReservationItem() { }

    @DynamoDbPartitionKey
    public String getTenantId() { return tenantId; }
    public void setTenantId(String value) { this.tenantId = value; }

    @DynamoDbSortKey
    public String getSortKey() { return sortKey; }
    public void setSortKey(String value) { this.sortKey = value; }

    public String getReservationId() { return reservationId; }
    public void setReservationId(String value) { this.reservationId = value; }

    public String getPropertyId() { return propertyId; }
    public void setPropertyId(String value) { this.propertyId = value; }

    @DynamoDbSecondaryPartitionKey(indexNames = "by-property")
    public String getPropertyKey() { return propertyKey; }
    public void setPropertyKey(String value) { this.propertyKey = value; }

    @DynamoDbSecondarySortKey(indexNames = "by-property")
    public String getCreatedAt() { return createdAt; }
    public void setCreatedAt(String value) { this.createdAt = value; }

    public String getState() { return state; }
    public void setState(String value) { this.state = value; }

    public Integer getGuestCount() { return guestCount; }
    public void setGuestCount(Integer value) { this.guestCount = value; }
}
~~~

`@DynamoDbBean`, `@DynamoDbPartitionKey`, and secondary key annotations belong to AWS SDK v2 Enhanced Client, **not JPA**. Key annotations are placed on getters; the class has a no-arg constructor and public getters/setters. By default, attribute names match JavaBean property names—for example, `getCreatedAt()` maps to `createdAt`. If renamed via `@DynamoDbAttribute`, both the table/index schema and query code must use the declared name.

The service creates `sortKey`, `propertyKey`, and `createdAt`; annotations **do not automatically assemble keys**. Example:

~~~java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;

public final class ReservationFactory {
    private static final DateTimeFormatter UTC_MILLIS =
            DateTimeFormatter
                    .ofPattern("uuuu-MM-dd'T'HH:mm:ss.SSS'Z'")
                    .withZone(ZoneOffset.UTC);

    private ReservationFactory() { }

    public static ReservationItem create(
            String tenantId,
            String propertyId,
            String reservationId,
            Instant when,
            int guestCount) {
        String timestamp = UTC_MILLIS.format(when);

        ReservationItem item = new ReservationItem();
        item.setTenantId(tenantId);
        item.setPropertyId(propertyId);
        item.setReservationId(reservationId);
        item.setCreatedAt(timestamp);
        item.setSortKey("RES#" + timestamp + "#" + reservationId);
        item.setPropertyKey(tenantId + "#" + propertyId);
        item.setState("PENDING");
        item.setGuestCount(guestCount);
        return item;
    }
}
~~~

In production, validate IDs, prevent ambiguous delimiters, and never allow users to arbitrarily pick a `tenantId` outside their authorized scope. If multiple bookings can share the same timestamp, `reservationId` must be sufficiently unique.

### 4.2. Connecting the Enhanced Client

If the starter auto-configures `DynamoDbEnhancedClient`, the repository simply injects it. With plain SDK v2, the beans can be configured as follows:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbEnhancedClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

@Configuration
class DynamoDbClientConfig {
    @Bean
    DynamoDbClient dynamoDbClient() {
        return DynamoDbClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build();
    }

    @Bean
    DynamoDbEnhancedClient dynamoDbEnhancedClient(DynamoDbClient client) {
        return DynamoDbEnhancedClient.builder()
                .dynamoDbClient(client)
                .build();
    }
}
~~~

This is a **real AWS** configuration using the default credentials provider chain. When running locally with a manually configured SDK client, add `endpointOverride(URI.create("http://localhost:8000"))` and local credentials. **Do not define duplicate client beans** when AWSpring already supplies the appropriate configuration.

The repository binds the table name and schema:

~~~java
import org.springframework.stereotype.Repository;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbEnhancedClient;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbTable;
import software.amazon.awssdk.enhanced.dynamodb.TableSchema;

@Repository
public class ReservationRepository {
    private final DynamoDbTable<ReservationItem> table;

    public ReservationRepository(DynamoDbEnhancedClient client) {
        this.table = client.table(
                "reservation_record",
                TableSchema.fromBean(ReservationItem.class));
    }

    // Read/write and pagination methods in the following sections
}
~~~

The following examples use the `table` field from this repository unless noted otherwise.

## 5. Writing, Reading, Updating, and Deleting

### 5.1. Writing an Item: `putItem` and Duplicate-Prevention Conditions

~~~java
import software.amazon.awssdk.enhanced.dynamodb.Expression;
import software.amazon.awssdk.enhanced.dynamodb.model.PutItemEnhancedRequest;

public void createNew(ReservationItem item) {
    var condition = Expression.builder()
            .expression("attribute_not_exists(tenantId)")
            .build();

    table.putItem(PutItemEnhancedRequest
            .builder(ReservationItem.class)
            .item(item)
            .conditionExpression(condition)
            .build());
}
~~~

Without a condition, `table.putItem(item)` can **replace the entire item** if an item with the same primary key already exists. The condition `attribute_not_exists(tenantId)` is evaluated atomically by DynamoDB on the **target item**; even if thousands of other items share the same `tenantId` with different `sortKey` values, creating a new item still succeeds. If an item with the same (`tenantId`, `sortKey`) pair already exists, the SDK throws `ConditionalCheckFailedException`: this is typically a business conflict, not a transient network error to retry endlessly.

To prevent duplicate writes from retried events or requests, use an **idempotency key** and deterministic key rules. Generating a fresh timestamp on every retry could accidentally create a second item for the same business action.

### 5.2. Reading an Item with `getItem`

~~~java
import java.util.Optional;
import software.amazon.awssdk.enhanced.dynamodb.Key;
import software.amazon.awssdk.enhanced.dynamodb.model.GetItemEnhancedRequest;

public Optional<ReservationItem> findOne(
        String tenantId, String sortKey, boolean strongRead) {
    Key key = Key.builder()
            .partitionValue(tenantId)
            .sortValue(sortKey)
            .build();

    GetItemEnhancedRequest request = GetItemEnhancedRequest
            .builder()
            .key(key)
            .consistentRead(strongRead)
            .build();

    return Optional.ofNullable(table.getItem(request));
}
~~~

If the key does not exist, the result is `null`; `Optional` in the repository helps the service handle the "not found" case cleanly. `consistentRead(true)` can be used on the **table** when you need strong consistency for newly written data, at the cost of different read capacity/latency characteristics. Strong consistency cannot be used on a GSI.

**Warning:** `sortKey` is `RES#timestamp#reservationId`, so `reservationId` alone is **not enough** to call `getItem`. Do not synthesize a new timestamp and expect to find an older item.

### 5.3. Updating an Item

The Enhanced Client supports:

~~~java
// Run once the existing item data has been loaded:
ReservationItem item = table.getItem(
        Key.builder()
                .partitionValue(tenantId)
                .sortValue(sortKey)
                .build());

if (item == null) {
    throw new IllegalArgumentException("Reservation not found");
}

item.setState("CONFIRMED");
table.updateItem(item);
~~~

**Do not treat the example above as unconditionally safe under concurrent updates.** Two requests reading and then modifying the same item can overwrite each other's changes. Additionally, `updateItem` and null-handling settings can overwrite or remove attributes omitted from the bean; do not construct a partial bean containing "only key + state" and call `updateItem` without knowing your SDK version's semantics.

In real systems, consider:

- Conditional updates—for instance, transitioning `PENDING → CONFIRMED` only when the current state is still `PENDING`.
- Optimistic locking via a version attribute and Enhanced Client's `@DynamoDbVersionAttribute`, with the entity and extension properly configured.
- `UpdateItemEnhancedRequest` with ignore-null configured appropriately for your SDK version when performing intentional partial updates.
- The transaction API when multiple items must change state atomically.

When modifying `propertyKey` or `createdAt`, remember that the GSI will also be updated and reads through the index may observe propagation lag.

### 5.4. Deleting an Item

~~~java
import software.amazon.awssdk.enhanced.dynamodb.Key;

public void deleteOne(String tenantId, String sortKey) {
    table.deleteItem(Key.builder()
            .partitionValue(tenantId)
            .sortValue(sortKey)
            .build());
}
~~~

Deleting by key generally does not fail merely because the item is already absent. If deletion must proceed only when state/version satisfies a condition, use a conditional delete. For workflows requiring audit trails, consider a **soft delete** (`state = CANCELLED`) or emitting an audit event instead of physical deletion.

### 5.5. Batches and Transactions: Commonly Misunderstood Limits

- `BatchGetItem` can read up to **100 items** per request; DynamoDB may return `UnprocessedKeys` when throttled. Retry unprocessed keys with backoff.
- `BatchWriteItem` accepts up to **25 Put/Delete requests** per batch and does not support Updates or per-item conditions as a transaction. Check and retry `UnprocessedItems`.
- Batches do not guarantee all-or-nothing success or rollback. For all-or-nothing changes, use `TransactWriteItems`/`TransactGetItems` within their quotas and cost model.
- While the Enhanced Client exposes high-level batch/transaction APIs, **do not assume Spring Data JPA's `@Transactional` automatically turns DynamoDB writes into transactions**.

## 6. Querying the Table by Partition Key and Sort Key

For `reservation_record`, retrieve a tenant's reservations for a month using the sort key prefix:

~~~java
import software.amazon.awssdk.enhanced.dynamodb.Key;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryConditional;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryEnhancedRequest;

QueryEnhancedRequest request = QueryEnhancedRequest.builder()
        .queryConditional(QueryConditional.sortBeginsWith(
                Key.builder()
                        .partitionValue("tenant-a")
                        .sortValue("RES#2026-11")
                        .build()))
        .scanIndexForward(false)
        .limit(25)
        .build();

for (var page : table.query(request)) {
    for (ReservationItem item : page.items()) {
        System.out.println(item.getReservationId());
    }
}
~~~

Explanation:

1. `QueryConditional.sortBeginsWith` applies a condition on the partition key **and** sort key. DynamoDB does not allow `begins_with` on the partition key; the partition key must use an exact equality match.
2. `scanIndexForward(false)` reverses the sort key order (newest first when timestamp keys are normalized); the default is `true`, which is ascending.
3. `limit(25)` caps the number of items **evaluated by DynamoDB per call/page**, not the total printed across all pages in the loop. To return 25 items overall, control page and item counts in the application.
4. `Query` has a **1 MB processed data limit per request** (before filtering), so even with a high limit, multiple pages can still occur.
5. If no items match, a page can be empty. When a filter is present, an empty page **can still include a `LastEvaluatedKey`** indicating more data remains to be scanned.
6. String sort key queries follow UTF-8 byte order without interpreting timezones. Every timestamp embedded in the key must follow a single fixed format so ordering remains accurate.

### 6.1. `Query` with Range Conditions

When the tenant and two sort key bounds are known, you can use:

~~~java
QueryConditional range = QueryConditional.sortBetween(
        Key.builder()
                .partitionValue("tenant-a")
                .sortValue("RES#2026-11-01")
                .build(),
        Key.builder()
                .partitionValue("tenant-a")
                .sortValue("RES#2026-11-30T23:59:59.999Z#~")
                .build());
~~~

`BETWEEN` is **inclusive of both endpoints**. The snippet above illustrates a range query when the sort key format is standardized; in production, derive range bounds from the actual format and test boundary/ID cases. To fetch all November reservations, `begins_with(sortKey, "RES#2026-11")` is usually clearer and avoids assumptions about the highest trailing character.

### 6.2. Why `FilterExpression` Cannot Replace an Index

Suppose you want to "fetch only `CONFIRMED` reservations for a tenant", but `state` is not in the key. You can attach a filter expression, yet DynamoDB still reads every item matching `KeyConditionExpression` before discarding items where `state != CONFIRMED`. **Read capacity is billed on data read**, not solely on the final items returned.

If querying by state is a high-volume path, consider designing an additional GSI (`tenantStateKey + createdAt`) or adjusting the access pattern. Each added GSI incurs index maintenance on writes, increasing write capacity consumption and cost.

### 6.3. `ProjectionExpression` and Read Limits

Projections request only a subset of attributes. This reduces network payload size and client deserialization overhead; however, for `Query` on a base table or LSI, projections **do not reduce read capacity consumed per item read**. For a GSI, queries can only access attributes projected into that index; you cannot request attributes omitted from the index projection as you can on the base table. Choose projections carefully when designing the index.

## 7. Querying a Global Secondary Index (GSI)

The `by-property` GSI has keys:

~~~text
IndexName = by-property
PK        = propertyKey  ("tenant-a#house-99")
SK        = createdAt    ("2026-11-24T08:30:00.000Z")
~~~

Example querying reservations for a property within a month:

~~~java
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbIndex;
import software.amazon.awssdk.enhanced.dynamodb.Key;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryConditional;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryEnhancedRequest;

DynamoDbIndex<ReservationItem> index = table.index("by-property");

QueryEnhancedRequest request = QueryEnhancedRequest.builder()
        .queryConditional(QueryConditional.sortBeginsWith(
                Key.builder()
                        .partitionValue("tenant-a#house-99")
                        .sortValue("2026-11")
                        .build()))
        .limit(20)
        .build();

for (var page : index.query(request)) {
    for (ReservationItem item : page.items()) {
        System.out.println(item.getReservationId());
    }
}
~~~

When querying `table`, conditions target `tenantId + sortKey`; when querying `index`, conditions target **`propertyKey + createdAt`**. The index must exist on the physical table and be mapped in the entity. `table.index("by-property")` references an existing index—it does not turn an ordinary attribute into an index.

Key points to remember:

- A GSI can have a different partition key from the table; an LSI must use the same partition key as the table and must be created at table creation time.
- GSIs are maintained **asynchronously** and only support **eventually consistent reads**; never set `consistentRead(true)` on a GSI query.
- An item may not appear in the GSI immediately after `PutItem` succeeds on the base table. If a GSI key attribute is absent on an item, that item is not indexed (sparse index).
- GSIs have separate write/read capacity and storage costs; if an index is throttled, it can back-pressure writes to the base table.
- GSIs do not enforce uniqueness on index keys. DynamoDB enforces uniqueness only on the **base table's** primary key.

**When newly created data must always be visible immediately:** if business logic requires strict read-after-write consistency, favor `GetItem`/`Query` on the base table with strongly consistent reads where supported, or design a synchronous workflow. Never build strong consistency guarantees on top of an eventually consistent GSI.

## 8. Proper Pagination with `LastEvaluatedKey` and `ExclusiveStartKey`

### 8.1. DynamoDB Pagination Mechanics

A `Query` can return a partial result set along with `LastEvaluatedKey`:

~~~mermaid
sequenceDiagram
    participant UI as Client
    participant API as Spring Boot API
    participant DB as DynamoDB
    UI->>API: GET /reservations?month=2026-11&pageSize=20
    API->>DB: Query(KeyCondition, Limit=20)
    DB-->>API: Items + LastEvaluatedKey
    API-->>UI: Items + nextCursor
    UI->>API: GET /reservations?month=2026-11&cursor=...
    API->>DB: Query(same condition, ExclusiveStartKey)
    DB-->>API: Items + LastEvaluatedKey or null
    API-->>UI: Items + nextCursor or null
~~~

Key concepts:

- `Limit`: maximum number of items **evaluated** by DynamoDB in a single request; when a filter is applied, the number of items **returned** may be smaller than the limit, or even 0.
- **1 MB cap:** DynamoDB terminates a page once the processed data size reaches 1 MB, even if the item count has not reached `Limit`.
- `LastEvaluatedKey`: the marker indicating where evaluation stopped. When absent (or empty), you have reached the end for the current access pattern.
- `ExclusiveStartKey`: set to the previous response's `LastEvaluatedKey` to continue reading; scanning resumes **after** that item.
- A GSI pagination key may contain both the base table's key attributes and the index's key attributes. Never assume `propertyKey`/`createdAt` alone is sufficient; preserve the **entire key map** returned by the SDK.

DynamoDB does not provide efficient SQL-style `OFFSET 100000` pagination. Never read 100,000 items and discard 99,900 just to reach "page 1000". Use a **cursor/continuation token** with a consistent query order.

### 8.2. Repository Returning Exactly **One Page**

Define a paginated result type in the repository layer:

~~~java
import java.util.List;
import java.util.Map;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;

public record ReservationPage(
        List<ReservationItem> items,
        Map<String, AttributeValue> nextKey) {
}
~~~

In `ReservationRepository`, add a method querying one page by month:

~~~java
import java.time.YearMonth;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

import software.amazon.awssdk.enhanced.dynamodb.Key;
import software.amazon.awssdk.enhanced.dynamodb.model.Page;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryConditional;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryEnhancedRequest;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;

public ReservationPage monthPage(
        String tenantId,
        String yyyyMM,
        int pageSize,
        Map<String, AttributeValue> startKey) {

    // Parsing rejects invalid month strings.
    YearMonth month = YearMonth.parse(yyyyMM);
    if (pageSize < 1 || pageSize > 100) {
        throw new IllegalArgumentException("pageSize must be between 1 and 100");
    }

    QueryEnhancedRequest.Builder request = QueryEnhancedRequest.builder()
            .queryConditional(QueryConditional.sortBeginsWith(
                    Key.builder()
                            .partitionValue(tenantId)
                            .sortValue("RES#" + month)
                            .build()))
            .scanIndexForward(false)
            .limit(pageSize);

    if (startKey != null && !startKey.isEmpty()) {
        request.exclusiveStartKey(startKey);
    }

    Iterator<Page<ReservationItem>> iterator =
            table.query(request.build()).iterator();

    if (!iterator.hasNext()) {
        return new ReservationPage(List.of(), null);
    }

    Page<ReservationItem> page = iterator.next();
    return new ReservationPage(
            List.copyOf(page.items()),
            page.lastEvaluatedKey());
}
~~~

Why this code calls **`iterator().next()` once**: the Enhanced Client returns a multi-page iterable. If you loop `for (var page : ...)` or iterate through the convenience `.items()` stream, the client keeps issuing DynamoDB calls until all data is exhausted, defeating the API's single-page boundary.

Because `Limit` bounds items evaluated, a filtered request can return fewer than `pageSize` items while still returning a `nextKey`. The API must not declare "no more data" simply because `items.size() < pageSize`.

### 8.3. GSI Pagination: Preserving Context

An example method querying the `by-property` GSI:

~~~java
import java.util.Iterator;
import java.util.List;
import java.util.Map;

import software.amazon.awssdk.enhanced.dynamodb.model.Page;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryConditional;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryEnhancedRequest;
import software.amazon.awssdk.enhanced.dynamodb.Key;
import software.amazon.awssdk.services.dynamodb.model.AttributeValue;

public ReservationPage propertyPage(
        String tenantId,
        String propertyId,
        int pageSize,
        Map<String, AttributeValue> startKey) {

    if (pageSize < 1 || pageSize > 100) {
        throw new IllegalArgumentException("pageSize must be between 1 and 100");
    }

    QueryEnhancedRequest.Builder request = QueryEnhancedRequest.builder()
            .queryConditional(QueryConditional.keyEqualTo(
                    Key.builder()
                            .partitionValue(tenantId + "#" + propertyId)
                            .build()))
            .scanIndexForward(false)
            .limit(pageSize);

    if (startKey != null && !startKey.isEmpty()) {
        request.exclusiveStartKey(startKey);
    }

    Iterator<Page<ReservationItem>> iterator =
            table.index("by-property")
                    .query(request.build())
                    .iterator();

    if (!iterator.hasNext()) {
        return new ReservationPage(List.of(), null);
    }

    Page<ReservationItem> page = iterator.next();
    return new ReservationPage(
            List.copyOf(page.items()),
            page.lastEvaluatedKey());
}
~~~

`startKey` must originate from **a query using the exact same index, partition key, sort direction, and filter conditions**. Never take a `LastEvaluatedKey` from a table query and pass it to an index query, or mix cursors across tenants or properties.

### 8.4. Public Cursors Require Security Boundaries

`Map<String, AttributeValue>` is a **repository-internal** representation; never expose raw AWS SDK objects over a public REST API and blindly trust what the client sends back.

Production APIs should issue an opaque `nextCursor` token:

1. When a response includes `LastEvaluatedKey`, serialize **the exact AttributeValue key types** (String/Number/Binary per schema) along with query context: index name, tenant, filters, sort order, page size/version, and expiration.
2. Sign the token with **HMAC** or protect it using authenticated encryption. URL-safe Base64 is merely **encoding**, not tamper protection or confidentiality.
3. Upon receiving a cursor, verify signature, expiration, version, authenticated account/tenant, index, and query parameters. Reject mismatched tokens; never accept arbitrary table/index names or tenants from a token.
4. Decode back into `Map<String, AttributeValue>` for `exclusiveStartKey`; for GSI cursors, preserve every key attribute returned by DynamoDB.
5. If key values or identifiers must remain hidden, use authenticated encryption or server-side cursor state. Enforce maximum token length and request size limits against abuse.

**Example HTTP contract:**

~~~json
{
  "items": [
    {
      "reservationId": "res-1001",
      "propertyId": "house-99",
      "state": "PENDING",
      "createdAt": "2026-11-24T08:30:00.000Z"
    }
  ],
  "nextCursor": "opaque-signed-token-generated-by-server"
}
~~~

The token in this sample only illustrates the contract—**it is not a real token**. Do not roll ad-hoc JSON/Base64 cursors in production without authenticating their contents. Use SDK serialization or a type-safe codec, and test tokens with Number/Binary types if your schema uses them. In this lesson's example, all keys are Strings, but serializing `AttributeValue` to JSON still requires explicit handling.

### 8.5. Limitations of Cursor-Based Pagination

- Multi-page queries **do not provide a consistent snapshot** of the entire table. While a client moves from page 1 to page 2, items can be added, deleted, or moved in sort/index keys; applications must tolerate this or build dedicated snapshot mechanisms.
- Cursors can become invalid or inconsistent if the query changes index, filter, sort direction, or key structure between requests.
- The presence of `LastEvaluatedKey` means **more data may exist**. The next request can still return an empty page, particularly when filters are active or data changes concurrently.
- Do not infer whether more pages remain from `items.size()`; check `nextKey`.
- If an endpoint requires **exactly N items after filtering**, iterate through a bounded number of DynamoDB pages until N items are gathered or data ends; enforce a read/latency budget and return the latest cursor to prevent unbounded loops.

## 9. IAM Permissions, Real-World Errors, and Cost Controls

### 9.1. IAM for Read/Write and Index Operations

Example policy scoped to the table and index above; replace account ID and region for your environment:

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
        "dynamodb:DeleteItem",
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

Do not grant `Scan`, `BatchWriteItem`, or transaction actions unless the service needs them. In multi-tenant systems, authorization is also required in the service layer: scope `tenantId` from the authenticated user identity and check permissions on the target property/reservation. A single workload IAM role does not isolate end-users by tenant automatically.

### 9.2. Error Handling

| Error/Symptom | Interpretation | Remediation |
| --- | --- | --- |
| `ResourceNotFoundException` | Table/index does not exist in the active account, region, or endpoint | Run `describe-table` and verify IaC/configuration |
| `ValidationException` | Missing/mistyped key, invalid key expression, or invalid cursor | Cross-check PK/SK/index schema, key formatting, and request fields |
| `ConditionalCheckFailedException` | Conditional create/update/delete condition no longer holds | Return a business conflict error; do not blindly retry |
| `AccessDeniedException` | IAM role lacks permission on the table/index | Verify actions and ARNs of the real resource |
| `ProvisionedThroughputExceededException` / throttling | Read/write exceeds capacity or hot key/index exists | Backoff with jitter, measure consumed capacity, adjust keys/capacity |
| `SdkClientException` or timeout | DNS, network, credentials, endpoint, or connection interruption | Check config, log safely via SDK, retry idempotent operations |
| Query returns empty despite data in table | Wrong index/key/tenant queried, sparse GSI, or eventual consistency | Review access pattern, schema, and item key values |
| Page has fewer items than limit | Filter, 1 MB cap, or `LastEvaluatedKey` still present | Continue paginating with the token within budget |
| Write succeeded but GSI does not show item yet | GSIs are eventually consistent | Design workflows to tolerate propagation delay |

### 9.3. Optimizing Queries and Cost

- Query using appropriate keys/indexes rather than broad Scans.
- Measure `ConsumedCapacity` (requests support `returnConsumedCapacity` at the appropriate SDK level), request counts, item sizes, read/write latency, and throttling.
- Projections reduce network transfer, **but do not guarantee lower RCU** when only limiting returned attributes on a base-table query.
- GSIs incur storage/write costs and can throttle base-table writes if an index key becomes hot; evaluate sparse indexes and projections.
- DynamoDB limits item size; store large documents/images in S3 and keep only keys and metadata in the table.
- The SDK provides default retries for certain errors; tune bounded retry/backoff and ensure reservation creation can recover cleanly after timeouts. Never loop endlessly when a client supplies an invalid cursor.

## 10. Integration Testing and Hands-On Practice

A unit test with a mocked repository does not prove that mappings, indexes, or continuation keys are correct. To verify real behavior, run Spring Boot against DynamoDB Local/LocalStack with tables and indexes matching production.

### 10.1. Manual Testing with the AWS CLI

After creating the table and configuring dummy credentials, write an item:

~~~bash
aws dynamodb put-item \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name reservation_record \
  --item '{
    "tenantId":{"S":"tenant-a"},
    "sortKey":{"S":"RES#2026-11-24T08:30:00.000Z#res-1001"},
    "reservationId":{"S":"res-1001"},
    "propertyId":{"S":"house-99"},
    "propertyKey":{"S":"tenant-a#house-99"},
    "createdAt":{"S":"2026-11-24T08:30:00.000Z"},
    "state":{"S":"PENDING"},
    "guestCount":{"N":"2"}
  }'
~~~

Read the item by its full primary key:

~~~bash
aws dynamodb get-item \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name reservation_record \
  --key '{
    "tenantId":{"S":"tenant-a"},
    "sortKey":{"S":"RES#2026-11-24T08:30:00.000Z#res-1001"}
  }'
~~~

Query the GSI:

~~~bash
aws dynamodb query \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name reservation_record \
  --index-name by-property \
  --key-condition-expression 'propertyKey = :pk' \
  --expression-attribute-values '{":pk":{"S":"tenant-a#house-99"}}' \
  --limit 10
~~~

Remember that the AWS CLI may auto-paginate by default. When studying the difference between `Limit`, `LastEvaluatedKey`, and `ExclusiveStartKey`, inspect the raw service response or use the SDK operations in Section 8. When using CLI flags like `--no-paginate`/`--max-items`/`--starting-token`, understand that they are **CLI** pagination mechanisms and may behave differently from passing DynamoDB's `ExclusiveStartKey` directly.

### 10.2. Testing the Paginated Repository

Scenarios to run against a real test endpoint:

1. Create multiple items for the same tenant with timestamps across different days/months; verify `monthPage(...)` returns only items matching the requested sort key prefix.
2. Call `monthPage(tenant, month, 2, null)`, take `nextKey`, and issue the next call with the **same parameters**; verify no items are skipped or duplicated on an unchanged dataset.
3. Create items for another tenant and verify tenant A requests never return tenant B items.
4. Query `by-property` by `propertyKey` and verify only the target property appears; if queried right after writing, use bounded polling due to GSI eventual consistency.
5. Attempt two create-only writes with the same composite key; the second call must throw `ConditionalCheckFailedException`.
6. Submit a mismatched `LastEvaluatedKey` or expired cursor at the API layer; verify the API rejects it cleanly without querying another tenant.
7. When filtering by state, verify a page may contain fewer items than `limit` while still returning `nextKey`; do not stop merely because `items.size() < pageSize`.
8. Cap per-request size, and monitor response time, read capacity, number of DynamoDB pages fetched, and cost as data grows.

Tests can use JUnit 5, Spring Boot Test, and Testcontainers to launch DynamoDB Local/LocalStack, configure dynamic endpoints, and provision tables before running. Never treat example code in a lesson as evidence of executed tests; **report PASS only after actually running tests against the corresponding endpoint and schema**.

## 11. Summary as Technical Decisions

| Design question | Recommended direction |
| --- | --- |
| Need one item by PK + SK? | `GetItem`; consider consistent read if required |
| Need multiple items by tenant and time? | `Query` the table with `partitionValue` + `sortBeginsWith`/range |
| Need multiple items by property? | `Query` the `by-property` GSI |
| Know only a non-key attribute, no index? | Revisit access pattern and design a GSI or lookup item |
| Prevent duplicates? | `PutItem` with `conditionExpression` and deterministic keys/idempotency |
| Update without losing concurrent changes? | Conditional update or optimistic locking |
| Build a paginated API? | `LastEvaluatedKey` → signed cursor → `ExclusiveStartKey` |
| Does a page smaller than `limit` mean end of data? | No; inspect `LastEvaluatedKey` |
| Must read immediately after write via GSI? | GSIs are eventual; prefer reading from the base table |
| Must write multiple items atomically? | DynamoDB transaction API; do not assume JPA `@Transactional` |

### Advanced Exercises

- Add a GSI for querying by `state` and timestamp, and analyze index maintenance costs when states transition frequently.
- Build `GET /reservations` returning `items` + `nextCursor` with HMAC-signed cursors; test tampered tokens, cross-tenant tokens, and expired tokens.
- Implement optimistic locking for status transitions; simulate two concurrent workers transitioning `PENDING` to different target states.
- Add request/page budgets in the service layer plus consumed capacity metrics; compare the impact of filter expressions versus indexed queries.
- Test base-table reads with `consistentRead(true)` versus GSI queries immediately after writes; explain the differing guarantees.
- Compare DynamoDB cursors with Azure Cosmos DB continuation tokens and Google Cloud Firestore query cursors/snapshots, focusing on authentication and tenant boundaries.

## References

- [AWS DynamoDB — Read and write operations](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.ReadWrite.html).
- [AWS DynamoDB — Query: Key condition expressions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.KeyConditionExpressions.html).
- [AWS DynamoDB — Query: Filter expressions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.FilterExpression.html).
- [AWS DynamoDB — Paginating query results](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.Pagination.html).
- [AWS DynamoDB — Global Secondary Indexes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GSI.html).
- [AWS DynamoDB — Condition expressions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Expressions.ConditionExpressions.html).
- [AWS DynamoDB — Batch operations and error handling](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-query-scan.html).
- [AWS SDK for Java v2 — DynamoDB Enhanced Client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/dynamodb-enhanced-client.html).
- [AWS SDK for Java v2 — Secondary indexes with Enhanced Client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/ddb-en-client-use-secindex.html).
- [Spring Cloud AWS — Reference documentation](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html).
