# Designing Partition Keys, Sort Keys, and DynamoDB Object Mapping

## 1. Objectives and Context

In the **AWS Data Services** chapter of the **Spring Cloud Provider Integration** module, a Spring Boot application works with AWS-managed data services using Spring Cloud AWS or the AWS SDK. With **Amazon DynamoDB**, the most critical decision is usually not which repository class to choose, but **designing keys around the queries the application must serve**.

DynamoDB is a key–value/document NoSQL database. The table name and key/index attributes are declared upfront; non-key attributes can vary flexibly across items. DynamoDB does **not** infer relationships or natively support arbitrary ad-hoc queries like a relational database. Therefore, the key model, secondary indexes, and Java mapping classes must be designed together.

After this lesson, you will be able to:

- Distinguish between **partition key**, **sort key**, simple primary key, and composite primary key.
- Start from access patterns to choose keys that distribute load well, avoiding hot keys and unbalanced partitions.
- Design sort keys for time-based queries, record grouping, and range queries; understand the impact of string comparison order.
- Design **GSI/LSI** when queries differ from the primary key, along with their consistency limits and costs.
- Map tables into Java using `@DynamoDbBean`, `@DynamoDbPartitionKey`, `@DynamoDbSortKey`, and secondary index annotations from **AWS SDK for Java v2 Enhanced Client**.
- Execute CRUD/Query operations from Spring Boot, test with DynamoDB Local, and evaluate how to adapt for AWS deployment.

> **Scope:** This is a data modeling and object mapping lesson for DynamoDB. `@DynamoDbBean` and `DynamoDbEnhancedClient` belong to AWS SDK v2; AWSpring's `DynamoDbTemplate`, if supported by the version in use, can reuse these mapping declarations. Do not confuse these annotations with JPA (`@Entity`, `@Id`).

## 2. How Does DynamoDB Organize Data with Keys?

### 2.1. Simple and Composite Primary Keys

Each item in a table is uniquely identified by its **primary key**:

| Primary key type | Components | When appropriate | Limitations to remember |
| --- | --- | --- | --- |
| **Simple primary key** | One partition key, e.g., `orderId` | Only read/write by ID is needed and IDs have high cardinality/spread | Cannot query all orders for a user using the main key |
| **Composite primary key** | Partition key + sort key, e.g., `customerId` + `createdAt#orderId` | Multiple items needed per group, supporting range or prefix queries | Reading an exact item requires knowing **both** key values |

A table with a composite key can store multiple items under the same partition key, but **each pair** (`partitionKey`, `sortKey`) must be unique. DynamoDB uses the partition key value to distribute data; within a group sharing the same partition key, items are ordered by the sort key.

Attributes participating in a primary key must be **scalar** types: **String**, **Number**, or **Binary**; they cannot be List/Map/Boolean. Key values cannot be null or empty strings. Maximum key value length is **2,048 bytes** for partition keys and **1,024 bytes** for sort keys; units are UTF-8 bytes, not Java character counts. A single item has a maximum size of **400 KB**, including both attribute names and values.

~~~text
Table: reservation_record

tenantId (PK)      sortKey (SK)                              propertyId   state
---------------------------------------------------------------------------------
tenant-a           RES#2026-11-24T08:00:00.000Z#res-1001    house-99     PENDING
tenant-a           RES#2026-11-24T08:45:00.000Z#res-1002    house-99     CONFIRMED
tenant-a           RES#2026-11-25T09:00:00.000Z#res-1003    house-88     CANCELLED
tenant-b           RES#2026-11-24T08:00:00.000Z#res-1001    house-01     CONFIRMED

=> Two tenants can share the same reservationId; the actual key is (tenantId, sortKey).
~~~

### 2.2. How `Query` Differs from `GetItem` and `Scan`

- `GetItem` reads a single item by its full primary key. For a table with a sort key, providing only the partition key is insufficient.
- `Query` **requires an equality (`=`) condition on the partition key** of the table or index. You can add conditions on the sort key such as `=`, `<`, `>`, `BETWEEN`, or `begins_with` (within the limits of the key's data type).
- `Scan` sweeps broadly across the table/index. A `FilterExpression` filters **after reading** the data, so it does not turn an unindexed access pattern into an efficient query.
- Each `Query`/`Scan` page is bounded by read data size; for `Query`, a single call processes up to **1 MB before applying filters/projections**. Pagination must be handled when `LastEvaluatedKey` is returned.

~~~mermaid
flowchart LR
    A["Business access pattern"] --> B{"Which keys are known?"}
    B -->|"Both PK + SK"| C["GetItem"]
    B -->|"PK, optional SK range/prefix"| D["Query table"]
    B -->|"Different lookup key"| E["Query GSI or LSI"]
    B -->|"No matching key/index"| F["Revisit data model<br/>Scan only when truly necessary"]
~~~

## 3. Start from Access Patterns, Not Java Classes

Consider a reservation system involving tenants, properties, and bookings. Before creating the table, describe the main queries and workload characteristics.

| Access pattern | Input data | Expected result | Approach |
| --- | --- | --- | --- |
| View a known reservation | `tenantId` + timestamp/ID recorded in `sortKey` | One item | `GetItem` on the primary key |
| List a tenant's November reservations | `tenantId` + `2026-11` | Multiple items ordered by time | `Query` on PK with `begins_with(sortKey, ...)` |
| List reservations for a property | `tenantId` + `propertyId` | Multiple items ordered by time | GSI with partition key `propertyKey` and sort key `createdAt` |
| Find a reservation knowing only `reservationId` | `tenantId` + `reservationId` | One item | Add a dedicated access pattern: adjust sort key design, maintain a lookup item, or add a suitable GSI |
| Count reservations by state | Tenant + time + state | Aggregated metrics | Maintain aggregates or a specialized index model; evaluate cost |

**Design decisions in this example:**

- The `reservation_record` table has primary key: **`tenantId` (partition key)** and **`sortKey` (sort key)**.
- `sortKey` has the form `RES#<createdAtUtc>#<reservationId>`. Example: `RES#2026-11-24T08:00:00.000Z#res-1001`.
- `createdAt` is stored as an ISO-8601 string in **UTC with fixed millisecond precision**. The `RES#` prefix supports grouping; the timestamp supports range queries; `reservationId` prevents primary key collisions if two bookings occur in the same millisecond.
- GSI `by-property` uses `propertyKey = tenantId#propertyId` as its partition key and `createdAt` as its sort key.

**Intentional trade-off:** this design supports time-based queries, whereas a "find by reservationId" API requires knowing `sortKey` or a secondary ID-to-sortKey mapping. If querying by ID is the most common requirement, an alternative design like `PK=tenantId`, `SK=RES#reservationId` combined with a GSI for time-based queries may fit better. There is no single "one-size-fits-all" key when access patterns differ.

## 4. Choosing a Partition Key for Load Distribution

The partition key is not just a filter field: it governs how reads and writes are distributed across physical partitions. A good key balances **query capability** with **actual traffic dispersion**.

### 4.1. Good Candidates vs. Hot Key Risks

| Partition key candidate | Strengths | Risks |
| --- | --- | --- |
| High-entropy `reservationId` | Spreads ID-based accesses evenly | Hard to list all reservations per tenant without an index |
| `tenantId` | Conveniently queries all records for a tenant | A large tenant with heavy burst reads/writes can become a hot key |
| `tenantId#yyyyMM` | Narrows data scope and can distribute across periods | Querying multiple months requires multiple calls; a massive tenant can still be hot within one month |
| `tenantId#bucket` (sharding) | Distributes load of an ultra-large tenant | Tenant-wide queries must fan out across buckets and merge results |

**Example:** if `tenant-a` creates a few dozen reservations per day, `tenantId` may be completely reasonable. However, if one tenant generates tens of thousands of requests/second on the same key, measure the load and consider bucket sharding; DynamoDB has adaptive capacity, but it does not eliminate all hot item/key limits. Do not introduce sharding merely because "NoSQL must shard"; first check item counts, request rates, item sizes, query patterns, and throttling metrics.

In a multi-tenant design, placing `tenantId` in the key organizes data, **but does not automatically enforce authorization boundaries**. The API layer must authenticate the tenant from the user identity and validate every read/write operation; never trust an arbitrary `tenantId` supplied in a request.

### 4.2. Decisions to Make Early

- **Cardinality:** how many distinct partition key values exist and how is traffic distributed across them?
- **Item collection:** how many items typically live under a single partition key?
- **Cross-group queries:** must data be listed across an entire tenant, by month, by property, or by an individual ID?
- **Size/cost:** long keys increase item size, index size, and storage/read/write costs.
- **Evolution:** if the primary key must change later, you usually must create a new table and migrate data because DynamoDB does not allow modifying an existing table's primary key definition in place.

## 5. Designing Sort Keys for Structure and Ordering

The sort key encodes ordering or hierarchy among items sharing the same partition key.

### 5.1. Composite Sort Keys

~~~text
RES#2026-11-24T08:00:00.000Z#res-1001
|    |                         |
|    |                         +-- ID to prevent key collisions
|    +---------------------------- normalized UTC timestamp
+--------------------------------- item type
~~~

For a given `tenantId`:

- `begins_with(sortKey, "RES#")`: all reservation items.
- `begins_with(sortKey, "RES#2026-11")`: reservations in November 2026.
- `BETWEEN` with two sort key bounds: date/time ranges when the timestamp format is uniform.

**Ordering note:** DynamoDB compares String keys by UTF-8 bytes and does not understand timestamps natively. Strings like `2026-11-24T08:00:00Z` and `2026-11-24T08:00:00.100Z` differ in length and may not sort chronologically as expected. Standardize UTC, timezone, precision, and zero-padding at write time; treat the format as part of your data contract.

If a numeric sort key is needed, DynamoDB's `Number` type sorts numerically; however, `begins_with` cannot be used on Number keys. With hierarchical composite keys like `CUSTOMER#123#ORDER#456`, the delimiter must be standardized/escaped if IDs could contain that character. Never concatenate untrusted user input into keys without validation/escaping.

### 5.2. Should Multiple Entity Types Share One Table?

A single table can store multiple item types:

~~~text
PK=TENANT#alpha, SK=PROFILE
PK=TENANT#alpha, SK=RES#2026-11-24T08:00:00.000Z#res-1001
PK=TENANT#alpha, SK=RES#2026-11-24T08:45:00.000Z#res-1002
~~~

This is **single-table design**, allowing related access patterns to be queried in a single table. However, it requires strict key conventions, handling differing schemas per item type, and more complex application mapping. This hands-on lesson uses **one item type** in the table to clarify partition keys, sort keys, and Java mapping first.

## 6. Secondary Indexes for Remaining Access Patterns

### 6.1. Differences Between GSI and LSI

| Criterion | Global Secondary Index (GSI) | Local Secondary Index (LSI) |
| --- | --- | --- |
| Partition key | Can differ from the table's partition key | Must share the table's partition key |
| Sort key | Can differ from the table's keys | Differs from the table's sort key |
| Creation time | Can be added to an existing table | Must be declared at table creation |
| Strongly consistent reads | No, GSIs only support eventually consistent reads | Supports strongly consistent reads |
| Item collection limit | Not bound by the 10 GB LSI mechanism | Tables with LSIs have a 10 GB item collection limit per partition key |
| Cost | Index storage and dedicated read/write capacity | Account for projection, storage, and table RCU/WCU |

To query **reservations for a property within a tenant**, use a GSI:

~~~text
GSI: by-property
  partition key: propertyKey = "tenant-a#house-99"
  sort key:      createdAt  = "2026-11-24T08:00:00.000Z"
~~~

The `propertyKey` includes the tenant so index queries do not mix data across tenants. If identifiers can contain `#`, define an escaping rule or an unambiguous key structure. Even with the tenant embedded in the key, authorization must still be enforced in the service layer.

**GSIs do not enforce uniqueness**: multiple base-table items can share the same `propertyKey` and `createdAt` in the GSI. Item uniqueness is enforced solely by the base table's primary key. GSIs are updated **asynchronously**, so newly written data may not appear immediately when querying the index. Choosing `ProjectionType=ALL` is convenient for practice but increases storage and write costs; in production, evaluate `KEYS_ONLY` or `INCLUDE` with only the attributes actually required.

### 6.2. Creating the Table and GSI in DynamoDB Local

Start DynamoDB Local for testing:

~~~bash
docker run --rm -p 8000:8000 amazon/dynamodb-local:latest
~~~

Set dummy credentials in your **local terminal**, such as `AWS_ACCESS_KEY_ID=local` and `AWS_SECRET_ACCESS_KEY=local`. Never use dummy keys or local endpoints in production.

~~~bash
# Bash; example for DynamoDB Local, where the endpoint is explicitly provided.
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

Review the details:

- The table name is `reservation_record`.
- The base table uses `tenantId` / `sortKey`; index `by-property` uses `propertyKey` / `createdAt`.
- Only declare attributes in `--attribute-definitions` that participate in table or index keys. `reservationId`, `state`, and other non-key attributes must not be declared there.
- In real AWS environments, create tables/indexes using IaC, use IAM roles, and select the appropriate region; **the starter/mapper does not create schemas automatically**.

Verify that the table and index exist:

~~~bash
aws dynamodb describe-table \
  --endpoint-url http://localhost:8000 \
  --region ap-southeast-1 \
  --table-name reservation_record
~~~

## 7. Object Mapping with AWS SDK for Java v2

### 7.1. Libraries and Configuration Sources

Spring Boot can use the AWSpring DynamoDB starter (if compatible with your application's Spring Boot and AWS SDK versions) to auto-configure `DynamoDbEnhancedClient`, or configure AWS SDK v2 manually.

In Maven, the core Enhanced Client dependencies are:

~~~xml
<!-- Manage versions consistently via the project's AWS SDK v2 BOM. -->
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>dynamodb</artifactId>
</dependency>
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>dynamodb-enhanced</artifactId>
</dependency>
~~~

If using AWSpring, the dependency is typically `io.awspring.cloud:spring-cloud-aws-starter-dynamodb`, managed via an **AWSpring BOM** compatible with Spring Boot. Check the documentation and API of your actual version before assuming `DynamoDbTemplate` exists; AWSpring and AWS SDK v2 are two distinct layers.

### 7.2. Defining a Bean Matching the Schema

In the AWS SDK Enhanced Client, `@DynamoDbBean` maps attributes via JavaBean getters/setters. Key annotations must be placed on **getters**; the class must have a no-arg constructor and accessible getters/setters.

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
}
~~~

Four key annotations:

| Annotation | Meaning | In this example |
| --- | --- | --- |
| `@DynamoDbPartitionKey` | Table partition key attribute | Getter `getTenantId()` |
| `@DynamoDbSortKey` | Table sort key attribute | Getter `getSortKey()` |
| `@DynamoDbSecondaryPartitionKey(indexNames = "...")` | Partition key attribute of the named GSI/LSI | Getter `getPropertyKey()` |
| `@DynamoDbSecondarySortKey(indexNames = "...")` | Sort key attribute of the named index | Getter `getCreatedAt()` |

By default, the stored attribute name is derived from the JavaBean property name. To rename the stored field, add `@DynamoDbAttribute("storageName")` on the getter; the key name in the **actual table/index** must then match that new name. If a getter is only for display/formatting and should not be persisted to DynamoDB, use `@DynamoDbIgnore`.

If immutable objects are needed, the AWS SDK Enhanced Client supports `@DynamoDbImmutable(builder = ...)` with a compliant builder; do not simply mark fields `final` on a `@DynamoDbBean` and expect the mapper to work. Complex types can use nested beans, Maps/Lists, or custom `AttributeConverter`/`@DynamoDbConvertedBy` when default mapping does not fit. Nested data must remain within DynamoDB's item size and document depth limits.

### 7.3. Business Logic Owns Key Values

Annotations declare **which field** acts as a key; they do not automatically construct `sortKey` or `propertyKey` from other fields. The service layer must build keys using a single consistent rule:

~~~java
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;

public final class ReservationKeys {
    private static final DateTimeFormatter UTC_MILLIS =
            DateTimeFormatter
                    .ofPattern("uuuu-MM-dd'T'HH:mm:ss.SSS'Z'")
                    .withZone(ZoneOffset.UTC);

    private ReservationKeys() { }

    public static ReservationItem newItem(
            String tenantId,
            String propertyId,
            String reservationId,
            Instant createdAt) {
        String timestamp = UTC_MILLIS.format(createdAt);

        ReservationItem item = new ReservationItem();
        item.setTenantId(tenantId);
        item.setReservationId(reservationId);
        item.setPropertyId(propertyId);
        item.setPropertyKey(tenantId + "#" + propertyId);
        item.setCreatedAt(timestamp);
        item.setSortKey("RES#" + timestamp + "#" + reservationId);
        item.setState("PENDING");
        return item;
    }
}
~~~

In production code, validate tenant/property/reservation IDs, `#` delimiter conventions, timezone, key length limits, and ID uniqueness. For an existing `reservationId`, do not generate a new timestamp to look up the item; retrieve the stored key or use a dedicated index/lookup. If consistency across multiple lookup records is required, evaluate transactions or conditional writes.

## 8. Using the Enhanced Client in Spring Boot

### 8.1. Client Initialization

If you use a compatible AWSpring starter and a `DynamoDbEnhancedClient` bean is auto-configured, simply inject it. If **not using AWSpring**, declare plain SDK v2 configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbEnhancedClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

@Configuration
public class DynamoDbConfiguration {
    @Bean
    DynamoDbClient dynamoDbClient() {
        return DynamoDbClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                // Uses the SDK's default credentials provider chain.
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

The snippet above connects to real AWS using the default credentials provider chain. To run against DynamoDB Local **when configuring the client manually**, add the corresponding endpoint override—such as `.endpointOverride(URI.create("http://localhost:8000"))`—and dummy credentials only for the local environment. **Do not create duplicate beans** when the starter already provides properly configured clients.

Example AWSpring local configuration (verify property names in your chosen version):

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

### 8.2. Repository Accessing the Table via TableSchema

~~~java
import org.springframework.stereotype.Repository;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbEnhancedClient;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbIndex;
import software.amazon.awssdk.enhanced.dynamodb.DynamoDbTable;
import software.amazon.awssdk.enhanced.dynamodb.Key;
import software.amazon.awssdk.enhanced.dynamodb.TableSchema;
import software.amazon.awssdk.enhanced.dynamodb.model.QueryConditional;

@Repository
public class ReservationRepository {
    private final DynamoDbTable<ReservationItem> table;

    public ReservationRepository(DynamoDbEnhancedClient client) {
        this.table = client.table(
                "reservation_record",
                TableSchema.fromBean(ReservationItem.class));
    }

    public void save(ReservationItem item) {
        table.putItem(item);
    }

    public ReservationItem findOne(String tenantId, String sortKey) {
        Key key = Key.builder()
                .partitionValue(tenantId)
                .sortValue(sortKey)
                .build();
        return table.getItem(key); // null if item does not exist
    }

    public void listReservationsInMonth(String tenantId, String yyyyMM) {
        String prefix = "RES#" + yyyyMM;
        var pages = table.query(request -> request
                .queryConditional(QueryConditional.sortBeginsWith(
                        Key.builder()
                                .partitionValue(tenantId)
                                .sortValue(prefix)
                                .build()))
                .limit(25));

        for (var page : pages) {
            for (ReservationItem item : page.items()) {
                System.out.println(item.getReservationId());
            }
        }
    }

    public void listReservationsForProperty(
            String tenantId, String propertyId) {
        DynamoDbIndex<ReservationItem> index = table.index("by-property");
        var pages = index.query(request -> request
                .queryConditional(QueryConditional.keyEqualTo(
                        Key.builder()
                                .partitionValue(tenantId + "#" + propertyId)
                                .build()))
                .limit(25));

        for (var page : pages) {
            for (ReservationItem item : page.items()) {
                System.out.println(item.getReservationId());
            }
        }
    }
}
~~~

**What to understand about this code:**

1. `TableSchema.fromBean(...)` reads annotations and builds mapping metadata, but **does not create the AWS table**. The table and index must already exist with matching names and key types.
2. `table.getItem(key)` requires both `tenantId` and `sortKey`; it returns `null` if not found.
3. `table.query(...)` uses the primary key, while `table.index("by-property").query(...)` uses the declared GSI keys. You **cannot** query the table directly by `propertyId` because it is only a regular table attribute.
4. `limit(25)` bounds how many items DynamoDB evaluates **per page request**, not the total across the entire loop. The demo API iterates through all pages; a real system should support cursors and enforce limits at the API layer.
5. GSI queries have eventual consistency. Table queries can request consistent reads when required by business logic and supported by the API; **do not enable strongly consistent reads on a GSI**.
6. Do not put `System.out.println` in production repositories; replace it with DTO/page return logic and controlled logging.

### 8.3. Safe Inserts Under Concurrent Requests

`putItem(item)` can overwrite an existing item with the same primary key. If you need **create-only** semantics, add a condition:

~~~java
import software.amazon.awssdk.enhanced.dynamodb.Expression;
import software.amazon.awssdk.enhanced.dynamodb.model.PutItemEnhancedRequest;

var createOnly = PutItemEnhancedRequest
        .builder(ReservationItem.class)
        .item(item)
        .conditionExpression(Expression.builder()
                .expression("attribute_not_exists(tenantId)")
                .build())
        .build();

table.putItem(createOnly);
~~~

The snippet above illustrates logic **inside the repository where `table` and `item` are in scope**. The condition is evaluated atomically on the item with the matching key; the operation throws `ConditionalCheckFailedException` if that primary key already exists. Do not retry unconditionally or treat this conflict as a connection failure. For concurrent updates, consider `@DynamoDbVersionAttribute` and optimistic locking.

### 8.4. If the Project Uses `DynamoDbTemplate`

In Spring Cloud AWS versions that actually provide `DynamoDbTemplate`, the `@DynamoDbBean` entity above remains the mapping foundation, while the template typically exposes operations such as `save`, `load`, and `query`. Verify the API and table name resolver configuration for your **exact version**. The example explicitly specifies table name `reservation_record` via `client.table("reservation_record", ...)`; if you switch to the template and its resolver derives a different name, operations may fail with `ResourceNotFoundException`. Never assume AWSpring, SDK v2 Enhanced Client, and JPA share the same table naming, repository, or transaction mechanics.

## 9. Testing Key Design and Mapping

A unit test with a mocked repository can pass even when the real table uses wrong key names. With a DynamoDB data model, you should run **integration tests on DynamoDB Local or LocalStack** with tables and indexes matching production.

Minimal test scenario:

1. Create the `reservation_record` table and `by-property` GSI as in Section 6, targeting the local endpoint.
2. Save 3 items: two with the same tenant/property but different timestamps, and one belonging to another tenant.
3. Read an exact item using both `tenantId` and `sortKey`; verify another tenant's key does not accidentally read the data.
4. Query with `begins_with(sortKey, "RES#2026-11")` and verify only records within that tenant and time range appear.
5. Query the GSI with `propertyKey = "tenant-a#house-99"` and verify the index returns records for that property. If queried immediately after writing, bounded polling may be needed because GSIs update asynchronously.
6. Execute two create-only writes with the same key to verify the second raises `ConditionalCheckFailedException`.
7. Use isolated test data per test and clean up by primary key to avoid state leakage between tests.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("local")
class ReservationRepositoryIT {

    @Autowired
    ReservationRepository repository;

    @Test
    void compositeKeyMapsAndReadsCorrectItem() {
        String tenant = "it-" + UUID.randomUUID();
        ReservationItem item = ReservationKeys.newItem(
                tenant, "house-99", "res-1",
                Instant.parse("2026-11-24T08:00:00Z"));

        repository.save(item);

        ReservationItem loaded =
                repository.findOne(tenant, item.getSortKey());

        assertNotNull(loaded);
        assertEquals(item.getSortKey(), loaded.getSortKey());
        assertEquals(tenant + "#house-99", loaded.getPropertyKey());
        assertEquals("PENDING", loaded.getState());
    }
}
~~~

Advanced practice should use Testcontainers to launch DynamoDB Local/LocalStack in CI, create tables/indexes in test setup, inject dynamic endpoints, and clean up data automatically. Only when a test **actually runs against a DynamoDB endpoint** are the mapping and schema verified—never treat sample code as proof of a PASSING test.

## 10. Common Mistakes and Consequences

| Symptom | Common cause | How to resolve |
| --- | --- | --- |
| `ValidationException: key element does not match schema` | Bean annotations, data type, or `Key.builder()` do not match actual keys | Inspect `describe-table`, `tenantId`/`sortKey`, and scalar types S/N/B |
| Item read returns null right after write | Wrong tenant, wrong sort key, wrong table/region, eventual read | Log normalized keys and region; consider consistent read on the base table |
| `ResourceNotFoundException` | Wrong table/index name, region, or endpoint | Check IaC and resolver naming, plus table/index status |
| Query by `propertyId` fails | `propertyId` is not a table/index partition key | Use GSI `by-property` with `propertyKey` or revise the access pattern |
| Incorrect chronological order | Timestamps lack consistent UTC/precision, non-standard string key | Normalize formatting and add ordering tests |
| `DynamoDbMappingException` / class mapping error | Missing constructor, setter, getter annotation, or unsupported type | Verify JavaBean conventions, `TableSchema.fromBean`, and converters |
| GSI missing item after write | Asynchronous index update or missing index key attribute | Wait with a bounded retry if needed; verify `propertyKey`/`createdAt` |
| Large tenant throttled | Hot `tenantId` key, oversized items, or constrained GSI capacity | Measure per-key metrics; consider sharding, index adjustments, or capacity changes |
| Duplicate reservation accidentally overwrites | `putItem` used without a condition | Use conditional writes and define an explicit idempotency key |
| Query returns too much data | Missing pagination; misunderstanding per-request `limit` | Return cursors/page sizes and enforce bounds in both service and API layers |

## 11. Operational and Multi-Cloud Decisions

- **Security:** Spring Boot running on ECS/EKS/EC2 should use an appropriate identity/role with least-privilege IAM permissions for `GetItem`, `PutItem`, `Query`, `DeleteItem`, and the **GSI ARN** when querying indexes. Never commit access keys or secret keys to source control. Use AWS Secrets Manager/Parameter Store if the application needs to manage separate secrets.
- **Performance/cost:** select capacity modes based on real traffic, and monitor read/write capacity, throttling, latency, and GSI write amplification. `Scan` on large tables is generally far costlier than key-based `Query`; adding GSIs is not free.
- **Consistency:** single-item writes are atomic; multi-item writes require transactional APIs if all-or-nothing semantics are required. GSIs are eventually consistent and unsuitable for concurrent conditional checks requiring the latest state.
- **TTL and sensitive data:** to expire old records, store the TTL timestamp as **Unix epoch seconds (Number)** in a dedicated attribute and enable TTL on the table. TTL does not guarantee immediate deletion at expiration time; code must still check expiration when business logic requires it.
- **Preserving schemas during deployment:** manage tables/indexes with IaC, test mappers against the real schema, and plan backfills and cutovers when changing keys. Changing a table's primary key is not a simple annotation edit.
- **Comparison with Azure/GCP:** Azure Cosmos DB and Google Cloud Firestore also require careful planning around partitioning, document paths, indexes, and quotas, but their key models, limits, and IAM differ from DynamoDB. Keep data access interfaces in the domain/service layer and implement provider-specific adapters for multi-cloud products.

## 12. Practice Exercises

1. From the four queries—"by reservationId", "by tenant and month", "by property", and "by state"—design two different primary key/GSI schemas and analyze their trade-offs.
2. Insert 100 items for a tenant and query with `begins_with` to filter by month; compare item reads/pages and returned payloads against `Scan`.
3. Replace `propertyKey = tenantId#propertyId` with an encoding rule safe against `#` characters in IDs; write tests proving no two distinct ID pairs produce the same key.
4. Add an `expiresAt` attribute for TTL and a nested `guestContact` field; choose how to map and protect the personal data.
5. Write tests verifying that the same `reservationId` across two different tenants does not overwrite each other, and test create-only behavior under two competing requests.
6. Evaluate the requirement "read a reservation by ID immediately after creation" when the ID does not embed a timestamp: add a lookup item, a GSI, or change the primary key schema? State your decision and its consistency implications.

## References

- [AWS — Core components of DynamoDB](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.CoreComponents.html): tables, items, partition keys, sort keys, and indexes.
- [AWS — Designing partition keys](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-partition-key-design.html): load distribution and hot keys.
- [AWS — Best practices for sort keys](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-sort-keys.html): structured sort keys and hierarchical queries.
- [AWS — Key condition expressions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.KeyConditionExpressions.html): `Query` conditions and pagination.
- [AWS — Using global secondary indexes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GSI.html): GSIs, projections, consistency, and cost.
- [AWS SDK for Java 2.x — Enhanced Client](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/dynamodb-enhanced-client.html): `TableSchema`, `DynamoDbBean`, and access APIs.
- [AWS SDK for Java 2.x — Use secondary indices](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/ddb-en-client-use-secindex.html): mapping GSIs/LSIs with annotations.
- [AWS — DynamoDB constraints](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Constraints.html): limits on keys, items, and expressions.
