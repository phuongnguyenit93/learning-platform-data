# Integrating Java or Spring Data with Automated Testing on MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chapter:** Integrated Practice  
> **Lesson:** Integrating Java or Spring Data with Automated Testing

## 1. Integrated Problem: Product Management and Inventory Reservation API

A Java store service needs to:

- Create and read products scoped by tenant and SKU code.
- Store monetary prices accurately in the smallest unit using BSON Int64.
- Prevent two products from sharing the same `sku` within the same `tenantId`.
- Reserve a quantity of stock upon receiving an order request.
- Prevent negative inventory counts if two concurrent requests arrive.
- Re-receive the same request when a client times out without reserving inventory twice.
- Return errors distinguishing out-of-stock, invalid requests, duplicate keys, and MongoDB failures.
- Run **automated tests against real MongoDB**, rather than merely mocking repositories.
- Be executable in CI/CD without touching production data.

Sample test interface:

```http
POST /api/demo/tenants/tenant-a/products
Content-Type: application/json

{
  "sku": "BOOK-101",
  "priceCents": 125000,
  "available": 12
}
```

A reservation request:

```http
POST /api/demo/tenants/tenant-a/products/prod_123/reservations
Idempotency-Key: reserve-tenant-a-order-999
Content-Type: application/json

{
  "quantity": 2
}
```

If the first request succeeded but the response was lost, retrying with the same `Idempotency-Key` **must not deduct inventory a second time**. If only 1 item remains, a request to reserve 2 must fail without setting `available = -1`.

The goal is to combine **MongoDB data modeling, indexes/validation, Java integration, atomic updates, transactions, error handling, and automated tests** into a verifiable hands-on exercise.

### 1.1. Request Flow Diagram

```text
      HTTP client / test
              |
              v
      Spring REST controller
      Bean Validation / auth
              |
              v
         StockService
              |
       +------+-------+
       |              |
       v              v
   ProductRepository  ReservationRepository
    / MongoTemplate      / Spring Data
       |              |
       +------+-------+
              |
       MongoTransactionManager
              |
              v
        MongoDB replica set
         /           \
    products       reservations
       |                |
   tenant+sku       requestId
   unique index     unique _id
              ^
              |
       JUnit 5 integration tests
       Testcontainers MongoDB
```

This application is a **testing-oriented demo**. Production tenant authentication, actual payment processing, order management, cross-system idempotency, and production data require additional components.

### 1.2. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish the plain Java Sync Driver, Spring Data MongoDB, and the Reactive driver.
2. Set up a Java 17, Spring Boot, MongoDB Driver, Maven, and JUnit 5 project.
3. Map documents using `@Document`, `@Id`, `@Version`, and BSON types.
4. Write repositories using `MongoRepository` and tenant-scoped queries.
5. Use `MongoTemplate` for atomic conditional updates.
6. Define properly scoped unique indexes and test duplicate-key errors.
7. Write a reservation ledger entry and decrement stock within **a single MongoDB transaction**.
8. Use an idempotency key for controlled HTTP request retries.
9. Write integration tests against an ephemeral MongoDB replica set via Testcontainers.
10. Verify BSON types, null/missing fields, array queries, validators, and transaction rollbacks.
11. Separate unit tests, slice tests, integration tests, and API tests.
12. Design test data isolation, cleanup, CI pipelines, and troubleshooting when Docker/MongoDB is unavailable.
13. Observe errors, write concern, index plans, retry semantics, and security boundaries.
14. Implement step by step without turning test examples into scripts that damage real data.

## 2. Choosing Plain Java Sync Driver vs. Spring Data MongoDB

### 2.1. Plain Java Sync Driver

The MongoDB Java Sync Driver exposes APIs such as:

```java
MongoClient client = MongoClients.create(uri);
MongoDatabase db = client.getDatabase("app");
MongoCollection<Document> products =
        db.getCollection("products");

products.find(Filters.eq("_id", "SKU-1")).first();
```

Advantages:

- Close to MongoDB command semantics.
- Direct access to `Bson`, `Document`, and `BsonDocument`.
- Straightforward control over exact queries, filters, updates, and aggregations.
- Usable outside the Spring Framework.
- Suitable for simple workers, libraries, and standalone utilities.

Parts you must build yourself:

- Dependency injection and lifecycle management.
- Repository abstractions.
- POJO/codec mapping.
- Application validation and transaction boundaries.
- Exception mapping and HTTP endpoints.
- Test setup and configuration wiring.

### 2.2. Spring Data MongoDB

Spring Data MongoDB adds:

- `@Document` and entity mapping.
- `MongoRepository` and query derivation.
- `MongoTemplate` for complex updates and aggregations.
- `@Version` for optimistic locking.
- `MongoTransactionManager` for `@Transactional` integration.
- Spring Boot auto-configuration.
- Spring Test/JUnit integration.
- Spring Data auditing when enabled.

Note: Spring Data does not give MongoDB foreign keys, does not automatically wrap all writes in transactions, does not turn retries into exactly-once delivery, and does not guarantee every repository query uses an index.

### 2.3. Reactive MongoDB

The Reactive driver / Spring WebFlux uses Publisher/Flux/Mono and an asynchronous lifecycle:

- Requires backpressure and subscription handling.
- Transactions use the corresponding reactive context/manager.
- Never mix blocking driver calls on the event-loop thread.
- Tests use `StepVerifier` and reactive testing utilities.

This lesson selects **synchronous Spring Data MongoDB** to focus on consistency and JUnit. Later sections show how to substitute the plain Java Sync Driver.

### 2.4. Quick Selection Table

| Need | Java Sync Driver | Spring Data MongoDB | Reactive |
| --- | --- | --- | --- |
| Direct BSON CRUD | Excellent fit | Via `MongoTemplate` | Via reactive driver/template |
| Repository abstraction | Build yourself | Built-in | Built-in for reactive |
| Spring Boot application | Works, needs wiring | Native | Native with WebFlux |
| Many API Spring services | Considerable boilerplate | Well suited | If full stack is reactive |
| Transactions | `ClientSession` | `MongoTransactionManager` | `ReactiveTransactionManager` |
| Testing real MongoDB | JUnit + Testcontainers | Spring Test + Testcontainers | Reactor + Testcontainers |
| Ease of debugging blocking flow | Convenient | Convenient | Requires understanding async chains |
| High I/O concurrency | Thread-per-blocking-op | Blocking threads | Non-blocking per driver |

Do not use two separate drivers or sessions inside the same business transaction assuming Spring `@Transactional` covers both: always verify they share **the same transaction manager/session context**.

## 3. Environment and Key Prerequisites

### 3.1. Practice Requirements

- JDK 17 or a Java version supported by your Spring Boot release.
- Maven or Gradle.
- Spring Boot and Spring Data MongoDB from **a compatible release train**.
- JUnit Jupiter 5 and Spring Boot Test.
- A MongoDB test replica set, or Testcontainers capable of starting one.
- Docker/container runtime for Testcontainers; CI runners must have container permissions.
- MongoDB Java Sync Driver version managed by the Spring Boot BOM.
- Never use production credentials.

The structural examples below follow common APIs in **Spring Boot 3.x / Spring Data MongoDB 4.x, Java 17, and the corresponding MongoDB Java Sync Driver**. When running locally, pick verified versions of Spring Boot, driver, and Testcontainers for your project. Spring Boot 4.x and Testcontainers 2.x may change dependencies, artifacts, or packages; check version-specific docs.

### 3.2. Why Must Testcontainers Use a MongoDB Replica Set?

Single-node standalone MongoDB suffices for basic CRUD and filters. However, multi-document transactions and change streams require a **replica set or sharded cluster**.

Testcontainers' `MongoDBContainer` can launch a single MongoDB container configured as a replica set for integration tests. Test code uses `getReplicaSetUrl()` rather than a hand-crafted standalone URI.

If production runs a sharded cluster, testing on a single-node replica set is **insufficient** to verify shard-key/unique-index constraints and cross-shard behavior; add tests on a matching staging topology.

### 3.3. No Embedded Fake Replaces Full Server Semantics

Mocking `MongoRepository` can test service branching, but cannot verify:

- MongoDB atomic conditional updates.
- `$jsonSchema` validation.
- BSON type persistence.
- Real unique indexes.
- Transaction rollback.
- `$elemMatch` vs. dot notation.
- Retryable writes and driver error labels.
- Query planner and index usage.

These mechanics require integration tests against a real MongoDB Server.

## 4. Maven Project: Core Dependencies

A skeleton `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>SPRING_BOOT_VERSION_DA_CHOT</version>
    <relativePath/>
  </parent>

  <groupId>vn.demo</groupId>
  <artifactId>mongo-row465</artifactId>
  <version>1.0.0-SNAPSHOT</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-data-mongodb</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>junit-jupiter</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.testcontainers</groupId>
      <artifactId>mongodb</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <!-- If the Spring Boot BOM already manages Testcontainers,
       do not declare a duplicate BOM; otherwise import a
       Testcontainers BOM compatible with the pinned version. -->

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
```

**Important:** `SPRING_BOOT_VERSION_DA_CHOT` is a placeholder that must be replaced with a confirmed actual version; this `pom.xml` will not run until replaced. Newer Testcontainers releases may change group/artifact/module names; follow the corresponding dependency matrix and never blindly mix Testcontainers 1.x code APIs with 2.x artifacts.

If using Gradle, keep the same dependency set:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    implementation("org.springframework.boot:spring-boot-starter-data-mongodb")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:mongodb")
}

tasks.test {
    useJUnitPlatform()
}
```

This Gradle snippet requires the Spring Boot plugin and corresponding dependency-management/BOM configured in the project build. In this STEP 4 **do not execute Maven/Gradle**; the code is provided for learners to apply in their own environment.

## 5. Recommended Project Structure

```text
mongo-row465/
  pom.xml
  src/
    main/
      java/vn/demo/row465/
        MongoRow465Application.java
        MongoTxConfig.java
        Product.java
        Reservation.java
        ProductRepository.java
        ReservationRepository.java
        StockService.java
        ReservationController.java
        ApiErrorHandler.java
      resources/
        application.yml
    test/
      java/vn/demo/row465/
        StockServiceIT.java
        ReservationApiIT.java
        BsonAndSchemaIT.java
        StockServiceUnitTest.java
```

This is a guide layout. In the code snippets, class and package names must match when copied into files. Some integration tests show skeleton code; adding unit tests requires the dependencies/mocking tools for your chosen framework.

## 6. Secure Connection Configuration

### 6.1. Main Application

```java
package vn.demo.row465;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MongoRow465Application {
    public static void main(String[] args) {
        SpringApplication.run(
            MongoRow465Application.class, args
        );
    }
}
```

`application.yml`:

```yaml
spring:
  data:
    mongodb:
      uri: \${MONGODB_URI}
      database: \${MONGODB_DATABASE:row465_app}
      auto-index-creation: false

server:
  port: 8080
```

In the actual file, `\${MONGODB_URI}` represents a Spring placeholder; remove the backslash unless your templating tool requires different escaping. Intended configuration:

```text
spring.data.mongodb.uri = MONGODB_URI environment variable
spring.data.mongodb.database = MONGODB_DATABASE environment variable
```

**Never commit URIs containing passwords.** Production should use secrets/secret managers/TLS, least-privilege roles, and separate database migrations to manage indexes.

### 6.2. About `auto-index-creation`

Spring Data can create indexes from annotations if auto index creation is enabled. The default across many Spring Data releases is **false**, because creating indexes automatically at application startup can:

- Run unexpected DDL against large collections.
- Trigger duplicate-key index build failures.
- Compete for I/O with live traffic.
- Complicate rollout ordering across multiple app versions.
- Bypass change tickets and capacity planning.

In integration tests against an empty MongoDB container, you can enable it to verify annotations. Production requires an explicit index migration process rather than blindly enabling `true` on every service.

### 6.3. Parameters to Understand Before Tuning

- `serverSelectionTimeoutMS`: driver node discovery timeout.
- `connectTimeoutMS`: TCP connection setup timeout.
- `socketTimeoutMS` or `timeoutMS` depending on driver version.
- `retryWrites`: driver-level retry for eligible writes.
- `w`, `j`, `wtimeout`: durability and acknowledgment guarantees.
- Pool size and wait queue depending on driver version.
- Read preference, read concern, and session semantics.

Never set ultra-low timeouts to make tests finish quickly and then carry that config into production. A request timeout never proves MongoDB rolled back the operation.

## 7. Product Data Model

### 7.1. Product Document

```javascript
{
  _id: "prod_e8d59a",
  tenantId: "tenant-a",
  sku: "BOOK-101",
  priceCents: NumberLong("125000"),
  available: NumberInt(12),
  version: NumberLong("0")
}
```

Invariants:

- `tenantId` is non-empty; every query is tenant-scoped.
- `sku` is non-empty and unique per tenant.
- `priceCents` is a non-negative integer within Int64 range.
- `available` is a non-negative integer.
- `version` changes on updates to detect stale writes.
- `_id` must not be regenerated when retrying the same product/business identity.

### 7.2. Spring Data Entity

```java
package vn.demo.row465;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "row465_products")
@CompoundIndex(
    name = "tenant_sku_unique",
    def = "{'tenantId': 1, 'sku': 1}",
    unique = true
)
public class Product {
    @Id
    private String id;
    private String tenantId;
    private String sku;
    private long priceCents;
    private int available;

    @Version
    private Long version;

    public Product() {
        // For the mapping framework.
    }

    public Product(
            String id,
            String tenantId,
            String sku,
            long priceCents,
            int available) {
        this.id = id;
        this.tenantId = tenantId;
        this.sku = sku;
        this.priceCents = priceCents;
        this.available = available;
    }

    public String getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getSku() {
        return sku;
    }

    public long getPriceCents() {
        return priceCents;
    }

    public int getAvailable() {
        return available;
    }

    public Long getVersion() {
        return version;
    }
}
```

`@Id` maps to MongoDB `_id`. This demo uses `prod_...` IDs so they do not accidentally look like 24-character hex ObjectIds; Spring Data may convert valid ObjectId-formatted String IDs depending on mapping/annotations.

`@Version` provides optimistic locking for Spring Data mapped operations, especially `save`; it does not mean every raw driver command automatically increments `version`. Stock reservation uses `MongoTemplate.findAndModify` with the mapped entity; according to Spring Data MongoDB documentation, update operations can auto-increment `@Version` when the version field is not included in the `Update`. Verify exact behavior with integration tests on your framework version.

### 7.3. Why Choose `long` for Price?

`125000` can arrive in HTTP JSON as a number. Stored in a Java `long` field, Spring Data/the driver typically persists it as BSON Int64; tests should assert the stored type after writing.

Do not use `double` for money when exact minor-unit precision is required. For currencies with fractional units or extremely large amounts, use `Decimal128`, `BigDecimal` + converters, or a money value object paired with currency.

### 7.4. Why Not Embed Reservations Inside Product?

Reservations can grow unboundedly over time. Stuffing every reservation into a single product document would cause:

- The document to grow toward the 16 MiB limit.
- Every insert to increase contention on a hot product.
- Audit and retention policies to become hard to separate.
- Customer reservation queries to become awkward.

This demo uses a separate `row465_reservations` collection and a transaction to protect changes across multiple documents.

## 8. Reservation Ledger and Idempotency Key

### 8.1. Document

```javascript
{
  _id: "reserve-tenant-a-order-999",
  tenantId: "tenant-a",
  productId: "prod_e8d59a",
  quantity: NumberInt(2),
  createdAt: ISODate("2026-11-14T04:00:00Z")
}
```

`_id` is the **request identity**, not a fresh random ID generated per retry. If the same request ID arrives a second time with the same payload, the service returns the existing reservation.

If the same ID arrives with a different payload, it must **conflict**, never be treated as a new request.

### 8.2. Entity

```java
package vn.demo.row465;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "row465_reservations")
public class Reservation {
    @Id
    private String requestId;
    private String tenantId;
    private String productId;
    private int quantity;
    private Instant createdAt;

    public Reservation() {}

    public Reservation(
            String requestId,
            String tenantId,
            String productId,
            int quantity,
            Instant createdAt) {
        this.requestId = requestId;
        this.tenantId = tenantId;
        this.productId = productId;
        this.quantity = quantity;
        this.createdAt = createdAt;
    }

    public String getRequestId() {
        return requestId;
    }
    public String getTenantId() {
        return tenantId;
    }
    public String getProductId() {
        return productId;
    }
    public int getQuantity() {
        return quantity;
    }
    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

Production can add `requestHash`, a `PENDING/CONFIRMED/CANCELLED` state machine, expiration/leases, and a business order ID. **Never add an automatic TTL** to an inventory-backing reservation unless release/compensation workflows are designed; expiring the ledger can erase idempotency proof.

## 9. Repository Interfaces

```java
package vn.demo.row465;

import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductRepository
        extends MongoRepository<Product, String> {

    Optional<Product> findByTenantIdAndSku(
        String tenantId, String sku
    );

    Optional<Product> findByIdAndTenantId(
        String id, String tenantId
    );
}
```

```java
package vn.demo.row465;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface ReservationRepository
        extends MongoRepository<Reservation, String> {
}
```

Spring Data derives queries from method names. While convenient, avoid writing long repository method names with complex array or nested predicates without verifying whether they generate `$elemMatch` or dot notation.

### 9.1. Queries Must Be Tenant-Scoped

Insecure:

```java
productRepository.findById(productId);
```

and returning it directly to a user in tenant A; that ID could belong to tenant B.

Better:

```java
productRepository.findByIdAndTenant(
    productId, authorizedTenantId
);
```

In the demo code, the exact method name is `findByIdAndTenantId`. Crucially, `authorizedTenantId` must come from a trusted identity/authorization context, **never blindly trusting a path parameter**.

### 9.2. A Unique Index Cannot Be Replaced by `findBySku` Followed by `save`

Two threads:

```text
Thread A: find sku -> absent
Thread B: find sku -> absent
Thread A: insert sku
Thread B: insert sku
```

Without a unique index, both inserts can succeed. You need a unique compound index `{tenantId:1,sku:1}` and duplicate-key error handling. Unique indexes on sharded collections must also obey shard-key prefix rules.

## 10. MongoDB Transaction Manager

```java
package vn.demo.row465;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTxConfig {
    @Bean
    public MongoTransactionManager transactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
```

Conditions:

- The MongoDB deployment supports multi-document transactions (replica set or supported sharded cluster).
- Repository and template operations participate in the Spring-managed transaction context.
- Never use a separate `MongoClient` or session outside the context and expect it to share the same transaction.
- Keep transactions short; never perform HTTP calls or wait on external input inside one.
- Configure write concern, read concern, and transaction options appropriate to the business logic.
- `@Transactional` on self-invocation may not trigger due to Spring proxy boundaries.
- Running tests against standalone MongoDB will fail when starting a transaction.

### 10.1. Why Not Put `@Transactional` on Every Method?

Transactions add overhead and can trigger write conflicts, especially on hot products. If a workflow updates only a single document, a single atomic conditional update may suffice. Here we require **two consistent changes**: decrementing `available` and writing the reservation ledger, making a transaction appropriate.

## 11. StockService: Atomic Check and Idempotent Reservation

### 11.1. Service Code

```java
package vn.demo.row465;

import java.time.Instant;
import java.util.Objects;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

@Service
public class StockService {
    private final MongoTemplate template;
    private final ReservationRepository reservations;

    public StockService(
            MongoTemplate template,
            ReservationRepository reservations) {
        this.template = template;
        this.reservations = reservations;
    }

    @Transactional
    public Reservation reserve(
            String tenantId,
            String requestId,
            String productId,
            int quantity) {

        if (tenantId == null || tenantId.isBlank()
                || requestId == null || requestId.isBlank()
                || productId == null || productId.isBlank()
                || quantity < 1) {
            throw new IllegalArgumentException(
                    "Invalid reservation input"
            );
        }

        Reservation previous = reservations
                .findById(requestId)
                .orElse(null);

        if (previous != null) {
            boolean sameCommand =
                Objects.equals(previous.getTenantId(), tenantId)
                && Objects.equals(
                    previous.getProductId(), productId
                )
                && previous.getQuantity() == quantity;

            if (!sameCommand) {
                throw new IllegalStateException(
                    "Idempotency key reused with different payload"
                );
            }

            return previous;
        }

        Query filter = Query.query(
            Criteria.where("_id").is(productId)
                .and("tenantId").is(tenantId)
                .and("available").gte(quantity)
        );

        Update change = new Update()
                .inc("available", -quantity);

        Product changed = template.findAndModify(
            filter,
            change,
            FindAndModifyOptions.options().returnNew(true),
            Product.class
        );

        if (changed == null) {
            throw new IllegalStateException(
                    "Product missing or insufficient stock"
            );
        }

        // Same MongoDB transaction as findAndModify.
        return reservations.insert(new Reservation(
            requestId,
            tenantId,
            productId,
            quantity,
            Instant.now()
        ));
    }
}
```

### 11.2. Why Does the Query Include `available >= quantity`?

```javascript
{
  _id: productId,
  tenantId: tenantId,
  available: { $gte: quantity }
}
```

MongoDB evaluates the filter and performs the update on **one document atomically**. If two requests each attempt to reserve 8 units out of 10 in stock, only the first (or whichever sees sufficient stock) succeeds; the other cannot drive stock negative.

Never do:

```text
read available=10
if available >= 8:
    update available = available - 8
```

because two threads can both read 10 and both write. Use an atomic predicate/update or an appropriately guarded transaction.

### 11.3. Why Must the Transaction Enclose the Reservation Insert?

If decrementing `available` succeeds while `reservations.insert` fails, we must not leave "phantom" held stock with no ledger entry.

Inside a MongoDB transaction:

```text
begin transaction
  |
  v
check and decrement product
  |
  v
insert reservation with unique request ID
  |
commit transaction
```

If inserting hits a duplicate key, the transaction can abort and roll back the product decrement together with it. If the transaction commit outcome is unknown, **reconcile against the request ledger** instead of blindly retrying.

### 11.4. Two Concurrent Requests with the Same `requestId`

Reading `reservations.findById` at the start of the service **does not by itself prevent races**. Two transactions can both see no existing record and then contend on the product write or the unique reservation `_id`.

In production:

- Use a stable request ID.
- Enforce unique `_id` on the reservation.
- On write conflict or transient transaction error, retry the **entire transaction** per driver/policy rules.
- On unknown commit outcome, retry **committing the same transaction/session** or reconcile; never dispatch a new business request ID.
- If a duplicate key occurs after rollback, read the existing reservation and compare payloads.
- Cap retries and apply backoff to avoid retry storms.

The example above processes a single transaction attempt; **it omits a full retry loop**. Sequential tests prove baseline idempotency; add dedicated concurrency tests to verify retry and ownership logic.

### 11.5. `@Version` and Update Operators

`Product.version` is managed by Spring Data. Spring Data documentation explains that update operations can automatically increment `version` when the version field is omitted from `Update`. This differs from raw Java driver `updateOne`, which only modifies explicitly specified fields.

Therefore, do not add `.inc("version",1)` manually to this Spring Data snippet without checking auto-increment behavior on your exact framework version—you risk double-incrementing or unexpected behavior. Integration tests should read back `version` after a reservation and assert progression.

### 11.6. Stock Reservation Is Not Payment

The reservation here only decrements `available` and records a ledger entry. Real orders and payments also require:

- TTL/expiration semantics and stock release.
- Cancellation and inventory return.
- Order payment state machines.
- Idempotency across external gateway timeouts.
- An outbox to emit `ReservationCreated`.
- Retry/reconciliation for unknown commit outcomes.

Never attempt to "roll back" an external payment simply by deleting a MongoDB reservation.

## 12. REST Controller and Bean Validation

### 12.1. DTOs Prevent Clients from Setting Arbitrary Fields

```java
package vn.demo.row465;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.PositiveOrZero;

public record CreateProductRequest(
    @NotBlank String sku,
    @PositiveOrZero long priceCents,
    @PositiveOrZero int available
) {}

public record ReserveRequest(
    @Min(1) int quantity
) {}

public record ReservationResponse(
    String requestId,
    String tenantId,
    String productId,
    int quantity
) {
    public static ReservationResponse from(Reservation r) {
        return new ReservationResponse(
            r.getRequestId(),
            r.getTenantId(),
            r.getProductId(),
            r.getQuantity()
        );
    }
}
```

These are three separate Java records; when saving to files, each public record must reside in a file matching its name (or adjust visibility to fit your project layout). Do not place all three public records inside a single `CreateProductRequest.java` file.

### 12.2. Illustrative Controller

```java
package vn.demo.row465;

import java.util.UUID;

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/demo/tenants/{tenantId}/products")
public class ReservationController {
    private final ProductRepository products;
    private final StockService stockService;

    public ReservationController(
            ProductRepository products,
            StockService stockService) {
        this.products = products;
        this.stockService = stockService;
    }

    @PostMapping
    public ResponseEntity<Product> create(
            @PathVariable String tenantId,
            @Valid @RequestBody CreateProductRequest body) {

        Product product = new Product(
            "prod_" + UUID.randomUUID(),
            tenantId,
            body.sku(),
            body.priceCents(),
            body.available()
        );

        return ResponseEntity.ok(products.insert(product));
    }

    @PostMapping("/{productId}/reservations")
    public ResponseEntity<ReservationResponse> reserve(
            @PathVariable String tenantId,
            @PathVariable String productId,
            @RequestHeader("Idempotency-Key")
                String requestId,
            @Valid @RequestBody ReserveRequest body) {

        Reservation saved = stockService.reserve(
            tenantId,
            requestId,
            productId,
            body.quantity()
        );

        return ResponseEntity.ok(
            ReservationResponse.from(saved)
        );
    }
}
```

**Security warning:** this demo route **has no authentication or authorization**. In production, `tenantId` must be authenticated from the security principal/claims with ownership verified. Never trust client-supplied path or header values alone.

### 12.3. Exception Mapping

Throwing a generic `IllegalStateException` above does not let the API distinguish "out of stock" from "same idempotency key, different payload", and may default to HTTP 500. Define domain exceptions:

```java
public class StockUnavailableException
        extends RuntimeException {
    public StockUnavailableException(String message) {
        super(message);
    }
}

public class IdempotencyConflictException
        extends RuntimeException {
    public IdempotencyConflictException(String message) {
        super(message);
    }
}
```

In production `StockService` code, replace `IllegalStateException` with the appropriate domain exception. Map them as follows:

```java
@RestControllerAdvice
public class ApiErrorHandler {
    @ExceptionHandler(StockUnavailableException.class)
    ResponseEntity<?> outOfStock(
            StockUnavailableException e) {
        return ResponseEntity.status(409)
            .body(java.util.Map.of(
                "code", "STOCK_UNAVAILABLE"
            ));
    }

    @ExceptionHandler(IdempotencyConflictException.class)
    ResponseEntity<?> reusedKey(
            IdempotencyConflictException e) {
        return ResponseEntity.status(409)
            .body(java.util.Map.of(
                "code", "IDEMPOTENCY_CONFLICT"
            ));
    }

    @ExceptionHandler(
        org.springframework.dao.DuplicateKeyException.class
    )
    ResponseEntity<?> duplicateKey(Exception e) {
        return ResponseEntity.status(409)
            .body(java.util.Map.of(
                "code", "DUPLICATE_KEY"
            ));
    }
}
```

This snippet is a skeleton—add imports and package declarations when placing into source files. Never return raw exception messages containing sensitive data or DB internals to HTTP clients. Network errors or unknown commit outcomes should not be collapsed into a misleading `409`; log them and apply proper reconciliation protocols.

## 13. Indexes and Schema Validation at the Database Layer

### 13.1. Compound Unique Index

`@CompoundIndex` declares intent. Production should create or migrate indexes through controlled DDL workflows:

```javascript
db.row465_products.createIndex(
  { tenantId: 1, sku: 1 },
  {
    name: "tenant_sku_unique",
    unique: true
  }
);
```

Notes:

- Build unique indexes only after auditing existing collections for duplicates.
- Consider missing/`null` semantics in compound unique keys.
- On sharded collections, unique indexes must obey shard-key prefix rules.
- Indexes alone do not enforce `priceCents >= 0` or exact BSON types.
- Application validation does not stop another script from writing bad data directly unless the DB enforces a validator.

### 13.2. Validator Expressing the Data Contract

Example:

```javascript
const productValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: [
      "tenantId",
      "sku",
      "priceCents",
      "available"
    ],
    properties: {
      tenantId: {
        bsonType: "string",
        minLength: 1
      },
      sku: {
        bsonType: "string",
        minLength: 1
      },
      priceCents: {
        bsonType: "long",
        minimum: 0
      },
      available: {
        bsonType: "int",
        minimum: 0
      }
    }
  }
};
```

Depending on mapping/driver behavior, `version` may be stored as BSON Int64 and is left unconstrained here. To validate `version`, audit actual stored types first before extending the validator.

`required` requires the field to be present; pairing it with `bsonType` rejects `null` as desired. Do not set `additionalProperties:false` at the root without listing `_id` and valid metadata fields.

### 13.3. Applying the Validator on a Test Collection

```javascript
db.runCommand({
  collMod: "row465_products",
  validator: productValidator,
  validationLevel: "strict",
  validationAction: "error"
});
```

Never run `collMod` against a production collection merely to "see if code works". Legacy data might violate the new schema, requiring phased rollout (`warn`/`moderate`/`error`/`strict`) and backfilling.

### 13.4. Both Validators and Unique Indexes Must Be Tested

A passing test caused by Java rejecting `priceCents=-1` **does not prove** the MongoDB validator is active. You need an integration test that uses the MongoDB driver/template to insert an invalid document directly into a test namespace and asserts server-side rejection.

Similarly, unit tests mocking the repository do not prove the unique index exists; you must attempt inserting two documents with the same `tenantId+sku` into real MongoDB.

## 14. Choosing an Appropriate Test Pyramid

### 14.1. Four Layers

```text
               End-to-end API
               HTTP -> Spring -> MongoDB
                      /\
                     /  \
               Integration
           MongoTemplate/Repository/Txn
                   /      \
                  /        \
             Slice tests
      MVC / mapping / configuration
                /          \
               /            \
          Unit tests
     pure rules and branching
```

Test counts do not need to form a rigid pyramid in every project. The goal is for each layer to verify **its own responsibility**, avoiding misplaced mocks.

### 14.2. What Should Unit Tests Verify?

- Validating `quantity > 0`.
- SKU canonicalization rules.
- `requestId` / `payloadHash` comparison.
- Mappers and formatters without DB access.
- Money arithmetic without overflow.
- Business state-machine transitions.

These run with plain JUnit 5 and Mockito without starting a Spring context.

### 14.3. What Should Repository Integration Tests Verify?

- MongoDB BSON mapping.
- Unique indexes.
- Tenant filters.
- `$elemMatch`.
- Null vs. missing fields.
- Query projections, sorting, and pagination.
- Transactions and rollbacks.
- Optimistic locking and `version`.
- Decimal128, ObjectId, and Date serialization.

These require real MongoDB. A mocked repository only returns whatever you programmed into the mock and proves nothing about server semantics.

### 14.4. What Should Controller/API Tests Verify?

- JSON validation: missing and invalid fields.
- HTTP status codes and error contracts.
- Enforcement of `Idempotency-Key`.
- Tenant authorization.
- Responses omitting sensitive fields.
- Proper wiring into service and transaction layers.
- Correct mapping of timeouts and unknown outcomes.

`@WebMvcTest` isolates the controller with a mocked service; `@SpringBootTest + MockMvc` exercises the full stack.

## 15. Testcontainers: Real MongoDB for JUnit 5

### 15.1. Principles

- The test container is an ephemeral resource owned by the test suite.
- The MongoDB image is pinned to a version matching production/staging.
- `MongoDBContainer.getReplicaSetUrl()` provides a topology-accurate connection string.
- Never hardcode `localhost:27017` in tests.
- Never use a production MongoDB URI in CI.
- Tests can run via `mvn test` in the learner's environment; the STEP 4 worker **does not execute them**.
- Docker image `mongo:7.0` is just an example; if targeting MongoDB 8.x/9.x, use an appropriate compatibility matrix.

### 15.2. Integration Test Configuration

```java
package vn.demo.row465;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Assertions;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
class StockServiceIT {
    @Container
    static final MongoDBContainer mongo =
        new MongoDBContainer(
            DockerImageName.parse("mongo:7.0")
        );

    private static final String DB_NAME =
        "row465_it_" +
        UUID.randomUUID().toString().replace("-", "");

    @DynamicPropertySource
    static void mongodbProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.mongodb.uri",
            mongo::getReplicaSetUrl
        );
        registry.add(
            "spring.data.mongodb.database",
            () -> DB_NAME
        );
        registry.add(
            "spring.data.mongodb.auto-index-creation",
            () -> "true"
        );
    }

    @Autowired
    ProductRepository products;

    @Autowired
    ReservationRepository reservations;

    @Autowired
    StockService stockService;

    @Autowired
    MongoTemplate template;

    private String productId;
    private String requestId;

    @BeforeEach
    void setUp() {
        productId = "prod_" + UUID.randomUUID();
        requestId = "req_" + UUID.randomUUID();
    }

    private Product seed(int available) {
        return products.insert(new Product(
            productId,
            "tenant-test",
            "SKU_" + productId,
            125000L,
            available
        ));
    }

    @AfterEach
    void cleanup() {
        if (requestId != null) {
            reservations.deleteById(requestId);
        }
        if (productId != null) {
            products.deleteById(productId);
        }
        // DB_NAME is an ephemeral database exclusive to this suite.
        // Never wipe an entire database in a shared environment.
    }

    @Test
    void reserveReducesAvailableAndSavesLedger() {
        seed(10);

        Reservation result = stockService.reserve(
            "tenant-test",
            requestId,
            productId,
            3
        );

        Assertions.assertEquals(
            requestId, result.getRequestId()
        );
        Assertions.assertEquals(3, result.getQuantity());

        Product after = products.findById(productId).orElseThrow();

        Assertions.assertEquals(7, after.getAvailable());
        Assertions.assertTrue(
            reservations.findById(requestId).isPresent()
        );
    }

    @Test
    void sameRequestIdDoesNotReserveTwice() {
        seed(10);

        Reservation first = stockService.reserve(
            "tenant-test", requestId, productId, 2
        );

        Reservation again = stockService.reserve(
            "tenant-test", requestId, productId, 2
        );

        Assertions.assertEquals(
            first.getRequestId(),
            again.getRequestId()
        );

        Assertions.assertEquals(
            8,
            products.findById(productId)
                .orElseThrow().getAvailable()
        );
        Assertions.assertEquals(
            1,
            reservations.count()
        );
    }

    @Test
    void insufficientStockDoesNotWriteReservation() {
        seed(1);

        Assertions.assertThrows(
            IllegalStateException.class,
            () -> stockService.reserve(
                "tenant-test", requestId, productId, 2
            )
        );

        Assertions.assertEquals(
            1,
            products.findById(productId)
                .orElseThrow().getAvailable()
        );
        Assertions.assertFalse(
            reservations.findById(requestId).isPresent()
        );
    }

    @Test
    void reusedKeyWithDifferentQuantityIsRejected() {
        seed(10);

        stockService.reserve(
            "tenant-test", requestId, productId, 1
        );

        Assertions.assertThrows(
            IllegalStateException.class,
            () -> stockService.reserve(
                "tenant-test", requestId, productId, 2
            )
        );

        Assertions.assertEquals(
            9,
            products.findById(productId)
                .orElseThrow().getAvailable()
        );
    }

    @Test
    void duplicateSkuWithinTenantIsRejected() {
        seed(10);

        String otherId = "prod_" + UUID.randomUUID();

        try {
            Assertions.assertThrows(
                DuplicateKeyException.class,
                () -> products.insert(new Product(
                    otherId,
                    "tenant-test",
                    "SKU_" + productId,
                    125000L,
                    1
                ))
            );
        } finally {
            products.deleteById(otherId);
        }
    }
}
```

### 15.3. Why Is This Test Suite More Reliable Than Mocks?

- `reserveReduces...` hits real MongoDB to decrement stock and insert the ledger entry.
- `sameRequestId...` proves sequential retries do not double-reserve.
- `insufficientStock...` proves the atomic predicate rejects insufficient inventory.
- `duplicateSku...` proves the **index actually exists and enforces uniqueness**, not merely an annotation.
- `MongoDBContainer` runs as a replica set so `@Transactional` works properly.
- The test database uses a per-suite random name; test records use isolated IDs.

**Not yet covered:** transaction error retries, unknown commits, concurrent same-key requests, secondary failover, sharded uniqueness, API authentication, and full performance SLOs. Those scenarios need dedicated tests.

### 15.4. A Note on `reservations.count()`

In this example, each suite uses its own random database and only one reservation is created per test; if running parallel tests sharing a database, `count()` can become flaky due to concurrent reservations from other tests.

When enabling parallel test execution, filter by `requestId`/`runId` with per-test isolation, or disable parallelization on shared state. Tests must be **independent** of execution order.

## 16. Verifying BSON Types After Writes

### 16.1. Why JSON Assertions Are Not Enough

HTTP JSON:

```json
{
  "priceCents": 125000
}
```

cannot prove MongoDB stored BSON `Int64` rather than `Int32` or `Double`.

### 16.2. Reading Raw BSON from the Test Collection

```java
import org.bson.BsonDocument;
import org.bson.BsonType;
import com.mongodb.client.MongoCollection;
import static com.mongodb.client.model.Filters.eq;

// After creating the Product:
MongoCollection<BsonDocument> rawProducts =
    template.getDb().getCollection(
        "row465_products",
        BsonDocument.class
    );

BsonDocument stored = rawProducts.find(
    eq("_id", productId)
).first();

Assertions.assertNotNull(stored);
Assertions.assertEquals(
    BsonType.INT64,
    stored.get("priceCents").getBsonType()
);

Assertions.assertEquals(
    BsonType.INT32,
    stored.get("available").getBsonType()
);
```

Imports and `template`/`productId` come from the integration test class above. Also verify `version` according to your framework's version behavior and contract; never assume all numeric fields share the same BSON type.

### 16.3. Large Numbers and Decimal128

Create a test value:

```java
long large = 9_007_199_254_740_993L;
```

This exceeds JavaScript `Number`'s exact integer range. MongoDB and Java `long` store it accurately, yet a frontend sending it as a raw JS `Number` can silently round it **before Java ever receives it**.

For decimal money:

```java
org.bson.types.Decimal128 dec =
    new org.bson.types.Decimal128(
        new java.math.BigDecimal("125.50")
    );
```

Verify rounding, scale, and units across boundaries. Never use `new BigDecimal(0.1)` expecting an exact decimal `0.1`.

## 17. Null, Missing, and Patch Semantics

### 17.1. Two States That Look Identical via `Document.get()`

```java
org.bson.Document missing =
    new org.bson.Document("_id", "missing");

org.bson.Document explicitNull =
    new org.bson.Document("_id", "null")
        .append("nickname", null);

Assertions.assertNull(missing.get("nickname"));
Assertions.assertNull(explicitNull.get("nickname"));

Assertions.assertFalse(
    missing.containsKey("nickname")
);
Assertions.assertTrue(
    explicitNull.containsKey("nickname")
);
```

`get()==null` does not distinguish missing fields from BSON Null; `containsKey` does.

### 17.2. MongoDB Queries

```javascript
db.profile_cases.find({
  nickname: null
});
```

matches both missing fields and explicit `null`. By contrast:

```javascript
db.profile_cases.find({
  nickname: { $exists: false }
});

db.profile_cases.find({
  nickname: { $type: "null" }
});
```

distinguish them precisely. For array fields, `$type` queries can match array elements, so add explicit fixtures.

### 17.3. Omitted Field vs. Explicit Null in PATCH

```json
{}
```

and:

```json
{"nickname": null}
```

must be modeled differently if your PATCH API defines "missing = leave unchanged, null = clear/set null". A plain Java DTO field `String nickname` loses this distinction during deserialization.

Use JSON Patch, field-presence wrappers, or safe JSON key inspection, then translate to:

- `$set` for a new value.
- `$set:{nickname:null}` if the contract uses explicit null.
- `$unset:{nickname:""}` if the contract removes the field.

Test the full HTTP JSON -> DTO -> MongoDB readback path, not just an isolated update method.

## 18. Arrays: Querying Correctly with `$elemMatch`

### 18.1. Fixture

```javascript
{
  _id: "order-cross",
  lines: [
    { sku: "A", quantity: 1 },
    { sku: "B", quantity: 10 }
  ]
}
```

Query:

```javascript
{
  "lines.sku": "A",
  "lines.quantity": { $gte: 5 }
}
```

can match because each condition is satisfied by a **different array element**.

### 18.2. Query Requiring One Element to Satisfy Both

```javascript
{
  lines: {
    $elemMatch: {
      sku: "A",
      quantity: { $gte: 5 }
    }
  }
}
```

The document above does not match. In Spring Data:

```java
Query q = Query.query(
    Criteria.where("lines").elemMatch(
        Criteria.where("sku").is("A")
            .and("quantity").gte(5)
    )
);
```

An integration test should seed both cross-element and same-element documents and assert counts `0` vs. `1`. Mocking `MongoTemplate.find` cannot catch query-semantics bugs.

### 18.3. Empty/Missing/Null Arrays

Cases to distinguish:

```javascript
{}
{ tags: null }
{ tags: [] }
{ tags: [null] }
{ tags: ["java"] }
{ tags: "java" }
```

`{tags:"java"}` matches both scalar strings and arrays containing the string. If your schema requires `tags` to be an array, enforce `$jsonSchema`/Bean Validation and add BSON readback tests rather than treating membership queries as type checks.

## 19. Schema Validator Integration Test

### 19.1. Use a Test-Specific Namespace

In an integration test, create a fresh randomly named collection with the validator. Never modify the validator of a collection shared by other components.

```java
String name =
    "validation_row465_" +
    java.util.UUID.randomUUID().toString()
        .replace("-", "");

org.bson.Document jsonSchema =
    new org.bson.Document("bsonType", "object")
        .append("required", java.util.List.of(
            "sku", "priceCents"
        ))
        .append("properties",
            new org.bson.Document()
                .append("sku",
                    new org.bson.Document(
                        "bsonType", "string"
                    ))
                .append("priceCents",
                    new org.bson.Document(
                        "bsonType", "long"
                    ).append("minimum", 0))
        );

org.bson.Document validator =
    new org.bson.Document("$jsonSchema", jsonSchema);

template.getDb().createCollection(
    name,
    new com.mongodb.client.model.CreateCollectionOptions()
        .validationOptions(
            new com.mongodb.client.model.ValidationOptions()
                .validator(validator)
                .validationLevel(
                    com.mongodb.client.model.ValidationLevel.STRICT
                )
                .validationAction(
                    com.mongodb.client.model.ValidationAction.ERROR
                )
        )
);
```

Depending on your Java Driver release, import the enum/options classes from `com.mongodb.client.model` as above and check Javadocs.

### 19.2. Test Valid and Invalid Type Inserts

```java
MongoCollection<org.bson.Document> collection =
    template.getDb().getCollection(name);

collection.insertOne(new org.bson.Document()
    .append("_id", "valid")
    .append("sku", "A")
    .append("priceCents", 125000L));

Assertions.assertThrows(
    com.mongodb.MongoWriteException.class,
    () -> collection.insertOne(
        new org.bson.Document()
            .append("_id", "invalid")
            .append("sku", "B")
            .append("priceCents", "125000")
    )
);
```

The second insert must be rejected by the server because `priceCents` is a BSON String rather than Long.

### 19.3. Cleanup

Because this collection was created **exclusively by the test** inside an isolated Testcontainers database, it can be cleaned up afterward:

```java
try {
    // Run test assertions against own collection.
} finally {
    template.getDb().getCollection(name).drop();
}
```

Only call `drop()` on the test-owned collection after verifying its name and ownership. **Never** copy this drop pattern into a shared or production database. For stricter safety, delete by exact `_id` and let the container be destroyed at the end of the CI job.

### 19.4. Validators Do Not Replace Unique Indexes

`$jsonSchema` only checks shape, types, and values within a single document. Two distinct products sharing the same `tenant+sku` both pass JSON Schema, so the unique index is still mandatory; tests must verify both.

## 20. Testing Real Transaction Rollback

### 20.1. What Needs to Be Proven

Annotating a method with `@Transactional` does not prove a transaction is actually opened. You need a test that intentionally throws an exception **after a write** and verifies the write is rolled back.

### 20.2. Using `TransactionTemplate` Against a MongoDB Container

```java
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.data.mongodb.MongoTransactionManager;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.data.mongodb.core.query.Criteria;

TransactionTemplate tx =
    new TransactionTemplate(mongoTransactionManager);

int before = products.findById(productId)
    .orElseThrow().getAvailable();

Assertions.assertThrows(
    IllegalStateException.class,
    () -> tx.execute(status -> {
        template.updateFirst(
            Query.query(
                Criteria.where("_id").is(productId)
            ),
            new Update().inc("available", -1),
            Product.class
        );

        throw new IllegalStateException(
            "Injected error after write"
        );
    })
);

int after = products.findById(productId)
    .orElseThrow().getAvailable();

Assertions.assertEquals(before, after);
```

In the test class, inject:

```java
@Autowired
MongoTransactionManager mongoTransactionManager;
```

This test only runs on transaction-compatible deployments; if accidentally executed against standalone MongoDB or without a transaction manager, fix the environment rather than "removing `@Transactional` to make it pass".

### 20.3. Be Careful About Rollback Assumptions on Unknown Commit

An exception **inside the transaction body** followed by an abort differs from a network timeout **during commit**. With `UnknownTransactionCommitResult`, the transaction may have already committed. The application must never blindly retry stock reservation under a new request ID.

Use stable request IDs and reconciliation:

- Read the reservation ledger by request ID.
- Verify product/ledger consistency under the durability contract.
- Retry committing the same session when appropriate, or invoke recovery workflows.
- Never deduct stock a second time.

## 21. Testing Optimistic Locking with `@Version`

### 21.1. Two Concurrent Entity Snapshots

```text
T0: Thread A reads Product(version=5)
T1: Thread B reads Product(version=5)
T2: A saves updated product -> version=6
T3: B attempts save version=5 -> optimistic lock failure
```

Spring Data MongoDB checks `version` on `save` for `@Version`-annotated entities (per mapping semantics). A test can do:

```java
Product a = products.findById(productId).orElseThrow();
Product b = products.findById(productId).orElseThrow();

// Add an entity update method/setter in the domain model
// if mutating and saving directly.
// After A saves a new version, B saving with the old version
// must be rejected as a stale update.
```

Do not simulate this by saving the same Java reference (`a == b`), because then there are no two separate snapshots.

### 21.2. `@Version` Does Not Guard Raw Updates Automatically

If using the raw driver:

```java
collection.updateOne(
    Filters.eq("_id", productId),
    Updates.set("priceCents", newPrice)
);
```

MongoDB does not check `version` just because a POJO has an annotation. To protect it, include a filter predicate:

```java
Filters.and(
    Filters.eq("_id", productId),
    Filters.eq("version", expectedVersion)
);
```

and increment `version` according to your update protocol. Ensure queries and updates match `version`'s exact BSON type.

### 21.3. Version vs. Business State

Reading a newer `version` does not mean your earlier request succeeded; another writer may have incremented it. Use `requestId` or an operation ledger to distinguish idempotent replay from a conflicting update.

## 22. Concurrency Tests Must Assert Invariants, Not Thread Ordering

### 22.1. Scenario

Inventory has 5 items. Two concurrent requests each try to reserve 4.

Valid outcomes:

- Total reserved quantity ≤ 5.
- `available >= 0`.
- Both reservations cannot succeed with quantity 4 each.
- No ledger entry succeeds without the corresponding stock reduction.
- Transient conflicts are retried or reconciled per policy.

### 22.2. Using a Barrier to Fire Concurrently

A test skeleton:

```java
ExecutorService pool =
    Executors.newFixedThreadPool(2);

CountDownLatch ready = new CountDownLatch(2);
CountDownLatch go = new CountDownLatch(1);

Callable<Reservation> task1 = () -> {
    ready.countDown();
    go.await();
    return stockService.reserve(
        "tenant-test", "req-A", productId, 4
    );
};

Callable<Reservation> task2 = () -> {
    ready.countDown();
    go.await();
    return stockService.reserve(
        "tenant-test", "req-B", productId, 4
    );
};

Future<Reservation> f1 = pool.submit(task1);
Future<Reservation> f2 = pool.submit(task2);

ready.await();
go.countDown();

// Collect both successes and failures; never assume which wins.
// A separate retry policy may be needed for WriteConflict.
pool.shutdown();
```

This is a skeleton; when implementing it, you must:

- Add timeouts on `await()` and `get()` so tests never hang.
- Catch `ExecutionException` and classify root causes.
- Clean up both request IDs in `finally`.
- Ensure the transactional service retries transient write conflicts.
- Assert final MongoDB state and total reserved quantities.
- Avoid shared mutable Java objects between tasks.

### 22.3. Why One Run Does Not Prove Absence of Races

Concurrency bugs do not trigger on every run. Run multiple iterations against test containers, use seeded fault injection, and verify invariants—without causing resource exhaustion on a shared cluster.

Separate **correctness of atomic predicates/transactions** from OS scheduler timing.

## 23. Verifying Tenant Filters in Tests

### 23.1. One User Must Never Read or Modify Another Tenant's Data

Example:

```javascript
{ _id: "prod-A", tenantId: "tenant-A" }
{ _id: "prod-B", tenantId: "tenant-B" }
```

Integration tests:

- `findByIdAndTenantId("prod-A","tenant-A")` returns the product.
- `findByIdAndTenantId("prod-A","tenant-B")` returns empty.
- `reserve("tenant-B", ..., "prod-A", 1)` fails.
- Product A retains its stock.
- No reservation for tenant B references product A.

### 23.2. Controller Tests Also Need Authentication

A route path:

```text
/api/demo/tenants/tenant-A/products/...
```

is not itself proof of tenant identity. When integrating Spring Security, verify the principal/JWT/scope, resolve the authorized tenant, and test that a tenant B client cannot spoof a tenant A path.

**Tenant-filtered queries** are an essential data-layer guardrail, not a replacement for authorization. Never trust raw `tenantId` values from requests unverified.

## 24. Controller Tests with MockMvc

### 24.1. Enabling MockMvc

Use:

```java
@SpringBootTest
@AutoConfigureMockMvc
@Testcontainers
class ReservationApiIT {
    @Autowired MockMvc mvc;
    // @Container + @DynamicPropertySource MongoDB setup
    // similar to StockServiceIT.
}
```

In a real test, declare MongoDB Testcontainers/`DynamicPropertySource` for the Spring context and seed product fixtures in that same test database.

### 24.2. Testing Invalid JSON

```java
mvc.perform(
    post("/api/demo/tenants/tenant-test/products")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
            {
              "sku": "",
              "priceCents": -1,
              "available": 5
            }
            """)
).andExpect(status().isBadRequest());
```

Spring MVC requires the Bean Validation starter, `@Valid`, and a handler returning `400` on validation errors. With a custom `@RestControllerAdvice`, do not accidentally map validation exceptions to `500` or `409`.

### 24.3. Testing Missing Idempotency-Key

```java
mvc.perform(
    post("/api/demo/tenants/tenant-test/products/"
         + productId + "/reservations")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"quantity\":1}")
).andExpect(status().isBadRequest());
```

`@RequestHeader` is required by default, so missing headers normally produce `400` in Spring MVC. If you have custom exception handlers, verify the API contract holds.

### 24.4. Testing Response Data Minimization

Do not return raw MongoDB entities directly from production endpoints if they expose internal metadata or sensitive fields. The demo create endpoint returns `Product` for brevity, whereas production should return response DTOs with authorization and hidden internal fields.

## 25. Plain Java Sync Driver: Variant Without Spring Data

If a project does not use Spring Boot, you can still test MongoDB using the Java Sync Driver + JUnit + Testcontainers.

### 25.1. Initializing the Client

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

try (MongoClient client =
         MongoClients.create(mongodbReplicaSetUri)) {

    MongoDatabase db =
        client.getDatabase("row465_driver_test");

    MongoCollection<Document> products =
        db.getCollection("products");

    // Create data with test-specific IDs and context.
}
```

### 25.2. Atomic Conditional Update

```java
import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

var result = products.updateOne(
    and(
        eq("_id", "prod_123"),
        eq("tenantId", "tenant-test"),
        gte("available", 2)
    ),
    inc("available", -2)
);

if (result.getMatchedCount() == 0) {
    throw new IllegalStateException(
        "Out of stock or missing product"
    );
}
```

The raw driver does not automatically enforce Spring's `@Version`. If optimistic CAS is required, add matching version predicates and increments using the right BSON type.

### 25.3. Transactions with `ClientSession`

```java
import com.mongodb.client.ClientSession;

try (ClientSession session = client.startSession()) {
    session.withTransaction(() -> {
        products.updateOne(
            session,
            and(
                eq("_id", "prod_123"),
                gte("available", 2)
            ),
            inc("available", -2)
        );

        reservations.insertOne(
            session,
            new Document("_id", "request-123")
                .append("productId", "prod_123")
                .append("quantity", 2)
        );

        return null;
    });
}
```

This snippet illustrates the **API** only and is not production-complete: you must verify `matchedCount`, tenant scope, request payload equality, transaction options, duplicate IDs, and unknown-commit reconciliation. Inserting a reservation after `matchedCount == 0` breaks invariants. Real code must throw/abort before inserting if `matchedCount != 1`.

### 25.4. Sharing Test Infrastructure Across Suites

You can share the same Testcontainers MongoDB URI across:

- The Spring repository integration suite.
- The plain Java driver integration suite.

Do not spin up 10 MongoDB containers for 10 test methods when CI resources are limited. Reuse a suite-level container with clean database/data isolation, and never couple tests to execution order.

## 26. Standalone `mongosh` Practice: Inspecting the Data Protected by Tests

### 26.1. Safety Rules

- Run only against an approved MongoDB test database.
- Never touch production data or `admin`/`config`/`local` databases.
- Create isolated collections using a unique `runId`.
- Never run `dropDatabase()` or `deleteMany({})` on shared collections.
- Never alter cluster/replica config or FCV.
- Clean up by exact `_id` + `runId`.
- These commands model **data shapes and assertions** and do not replace a JUnit integration suite.

### 26.2. Create a Test Namespace

```javascript
const lab = db.getSiblingDB("mongo_java_row465_lab");
const runId = "row465_" + new ObjectId().toHexString();
const productCollection = "products_" + runId;
const reservationCollection = "reservations_" + runId;

for (const name of [productCollection, reservationCollection]) {
  if (lab.getCollectionNames().includes(name)) {
    throw new Error("Namespace already exists");
  }
}

lab.createCollection(productCollection);
lab.createCollection(reservationCollection);

const products = lab.getCollection(productCollection);
const reservations = lab.getCollection(reservationCollection);

printjson({
  database: lab.getName(),
  runId,
  productCollection,
  reservationCollection
});
```

### 26.3. Create the Unique Index and Seed Data

```javascript
products.createIndex(
  { tenantId: 1, sku: 1 },
  {
    name: "tenant_sku_unique",
    unique: true
  }
);

const tenantId = "tenant_" + runId;
const productId = "prod_" + runId;

products.insertOne({
  _id: productId,
  runId,
  tenantId,
  sku: "SKU-465",
  priceCents: NumberLong("125000"),
  available: NumberInt(10),
  version: NumberLong("1")
});
```

### 26.4. Verify Raw BSON Types

```javascript
const typed = products.aggregate([
  { $match: { _id: productId, runId } },
  {
    $project: {
      priceType: { $type: "$priceCents" },
      availableType: { $type: "$available" },
      versionType: { $type: "$version" }
    }
  }
]).toArray()[0];

printjson(typed);

if (typed.priceType !== "long" ||
    typed.availableType !== "int" ||
    typed.versionType !== "long") {
  throw new Error("Unexpected BSON types");
}
```

### 26.5. Conditional Stock Decrement and Verification

```javascript
const requestId = "reserve_" + runId;
const qty = 3;

const changed = products.updateOne(
  {
    _id: productId,
    runId,
    tenantId,
    available: { $gte: qty }
  },
  {
    $inc: {
      available: -qty,
      version: NumberLong("1")
    }
  }
);

if (changed.matchedCount !== 1) {
  throw new Error("Insufficient stock or conflict");
}

printjson(products.findOne({
  _id: productId, runId
}));
```

In this snippet, transactions and full idempotency are not implemented; this is only a **single-document** atomic update. Do not mistake it for atomic coordination across both stock and the reservation ledger.

### 26.6. Simulating a Ledger Entry by Request ID

```javascript
reservations.updateOne(
  { _id: requestId, runId },
  {
    $setOnInsert: {
      tenantId,
      productId,
      quantity: NumberInt(qty),
      createdAt: new Date()
    }
  },
  { upsert: true }
);
```

A second upsert with the same `requestId` does not insert a duplicate document. **However**, if your code decremented stock before this step on every retry, stock would still be double-deducted. That is why the real business flow needs a transaction plus an idempotency check **before** decrementing, as in `StockService`.

### 26.7. Ownership-Scoped Cleanup

```javascript
const ownedProducts = products.find(
  { runId }, { _id: 1, runId: 1 }
).toArray();

const ownedReservations = reservations.find(
  { _id: requestId, runId }, { _id: 1, runId: 1 }
).toArray();

printjson({
  ownedProducts: ownedProducts.length,
  ownedReservations: ownedReservations.length,
  runId
});

for (const item of ownedReservations) {
  reservations.deleteOne({
    _id: item._id, runId
  });
}

for (const item of ownedProducts) {
  products.deleteOne({
    _id: item._id, runId
  });
}

printjson({
  productsRemaining: products.countDocuments({ runId }),
  reservationsRemaining:
      reservations.countDocuments({ runId })
});
```

Do not drop the whole database. Any leftover empty test collections/indexes can be managed by prefix, owner, and retention policies after verification.

## 27. Testing Index Plans and Performance

### 27.1. Query Shape

```javascript
db.row465_products.find({
  tenantId: "tenant-test",
  sku: "SKU-A"
});
```

With the compound unique index `{tenantId:1,sku:1}`, the query can use the index, though exact plans depend on dataset statistics and server version.

### 27.2. `explain("executionStats")`

```javascript
db.row465_products.find({
  tenantId: "tenant-test",
  sku: "SKU-A"
}).explain("executionStats");
```

Key metrics to inspect:

- `winningPlan` and index name.
- `totalKeysExamined`.
- `totalDocsExamined`.
- `nReturned`.
- Filter selectivity.
- Whether sort stages are index-supported.
- p95/p99 latency on realistic workloads.

On a test collection with only a few documents, the planner may pick `COLLSCAN` as cheaper; never treat a tiny `explain` as a production benchmark.

### 27.3. Test Dataset Scale

Performance tests need datasets reflecting:

- Realistic cardinality.
- Hot tenants and products.
- Read/write ratios.
- Query filter combinations.
- Document sizes and index density.
- Concurrent reservations.
- Replication topology and network latency.

Small unit/integration tests verify **correctness**; load tests measure **performance**. Do not conflate the two by forcing every JUnit test to meet a 10 ms deadline on a laptop.

## 28. Testing Failure Windows and Retries

### 28.1. A Transaction Can Commit Even When the Response Is Lost

```text
T0: reserve(tenant, requestId=R1)
T1: Product stock decremented
T2: Reservation R1 inserted
T3: Transaction commit succeeds
T4: Commit response lost
T5: Application sees UnknownTransactionCommitResult
```

If the app retries the business command with a **different `requestId`**, it risks deducting stock again. Keeping the same request ID and reconciling against the ledger provides proof that the command already committed.

### 28.2. Distinguishing the Two Error Labels

| MongoDB error label | Meaning | Strategy |
| --- | --- | --- |
| `TransientTransactionError` | Temporary failure in transaction body; safe to retry whole transaction | Retry whole transaction per driver policy |
| `UnknownTransactionCommitResult` | Client does not know whether commit succeeded | Retry **committing the same transaction/session** while valid; otherwise reconcile |

Never catch generic `MongoException` and call `reserve` in an unbounded loop.

### 28.3. Retryable Writes Do Not Replace HTTP Idempotency

`retryWrites=true` lets the driver retry eligible writes within a single logical operation. Two separate HTTP requests from a client create two distinct logical MongoDB operations—hence the API needs `Idempotency-Key`.

### 28.4. Fault Injection Without Breaking the Cluster

You can test application resilience when:

- A mocked repository throws an exception right after a simulated commit.
- An adapter times out even though a record already exists.
- The same request is sent twice with the same key.
- An event/outbox publish succeeds while its ACK is lost.
- A batch insert partially succeeds.
- A worker shuts down between a side effect and its checkpoint.

Never run `rs.stepDown()`, kill the MongoDB primary, or sever networks in production just to test error handling.

### 28.5. When Is a Reconciliation Worker Needed?

If a commit outcome is unknown and the application has closed the session, or an external system leaves state ambiguous:

- Persist a durable `NEEDS_RECONCILIATION` record.
- Look up the command/reservation by request ID.
- Compare tenant, product, quantity, and outcome.
- Verify durability guarantees (write/read concern).
- Never mint a new request ID to "try again".
- Alert if timeout budgets are exceeded or conflicts arise.

## 29. Schema Evolution and Regression Testing

### 29.1. Adding a New Field

Suppose Product v2 adds `currency`:

```javascript
{
  priceCents: NumberLong("125000"),
  currency: "VND"
}
```

If old writers omit `currency` and a new validator immediately requires it, old writes fail.

Rollout process:

1. Readers interpret missing `currency` according to agreed rules.
2. Deploy writers that populate `currency`.
3. Audit and backfill legacy documents.
4. Enable the validator in `warn`/`moderate` mode.
5. Once all writers are compatible and data is clean, switch to `strict`.
6. Add regression tests covering both old and new shapes.
7. Remove reader fallbacks only after the rollback window closes.

### 29.2. Do Not Assign Arbitrary Defaults

A document missing `currency` does not automatically mean `"VND"`. Confirm a valid source of truth or business rule before backfilling.

### 29.3. Testing Backward Compatibility

If old code reads BSON Int32 while new code writes Int64:

- Include both types in test fixtures.
- Test mapping and integer overflow handling.
- Test DTO/JSON serialization conversions.
- If the validator requires Int64, backfill Int32 documents first.
- Verify rolled-back application code can still read newly written documents.

Never assume numbers with the same numeric value share the same BSON type.

## 30. Spring Data Slices vs. Full Context

### 30.1. `@DataMongoTest`

`@DataMongoTest` focuses on MongoDB repositories and mapping components; it fits query, index, and codec tests against a real MongoDB test connection. However:

- It does not load `StockService` or controllers by default.
- `MongoTransactionManager` or custom configs may require explicit imports.
- You still must configure the test container/connection URI.
- Do not assume an embedded MongoDB instance is present.

### 30.2. `@SpringBootTest`

Loads the broader application:

- Controller, service, and repository beans.
- `MongoTransactionManager` and `@Transactional`.
- Bean Validation.
- Integration with real MongoDB.
- Combinable with `@AutoConfigureMockMvc`.

The trade-off is slower startup and higher memory usage. Keep test suites efficient instead of recreating a fresh Spring context for every method.

### 30.3. `@Transactional` on Test Methods Can Be Misleading

Test frameworks use test-managed transactions in some contexts. If a test itself runs inside an uncommitted transaction, another application thread may not see seeded fixtures. With the MongoDB driver, transaction support, topology, and session propagation must be clearly understood.

In this lesson's tests, **do not annotate entire test methods with `@Transactional`** unless specifically testing that behavior. Let the service manage its own transaction boundaries and assert state after it returns.

## 31. Test Data Isolation and Cleanup

### 31.1. Never Share Fixed `_id`s in Parallel Tests

Wrong:

```java
products.insert(new Product(
    "product-1", "test", "SKU-1", 100L, 10
));
```

across parallel tests—it invites `DuplicateKeyException` and state pollution.

Use:

```java
String runId = "row465_" + UUID.randomUUID();
String productId = "prod_" + runId;
```

Also ensure `sku` and `tenantId` respect unique constraints, and track generated IDs for cleanup.

### 31.2. Testcontainers per Suite vs. per Test

| Strategy | Advantages | Drawbacks |
| --- | --- | --- |
| One container per test | Maximum isolation | Very slow and Docker-heavy |
| One container per class | Balanced setup | Needs cleanup/test isolation |
| One container per suite | Faster execution | Shared lifecycle and parallelization care |
| Separate database per test | Independent queries, schemas, indexes | Extra namespace/init overhead |
| Random IDs in shared test DB | Simple | Tests can skew global counts |
| Shared staging DB | Realistic topology | Pollution risk; requires auth/ownership |

In CI, prefer ephemeral containers with randomized namespaces. Test results must never depend on execution order.

### 31.3. Cleanup Should Not Mask the Original Failure

`@AfterEach` should delete exact test IDs even when assertions fail. However, if cleanup throws an exception, it can hide the root assertion failure.

Log cleanup errors separately or rely on the ephemeral Testcontainers database being destroyed with the job. Never run `deleteMany({})` against a potentially shared database.

### 31.4. Do Not Log Sensitive Data on Failure

Test failure logs should record the test case, namespace, `runId`, expected/actual BSON types, and redacted errors. Never dump credentials, full customer records, or payment tokens.

## 32. Running Tests in CI

### 32.1. Representative Pipeline

```text
Checkout
   |
Resolve dependencies with locked versions
   |
Compile Java
   |
Run fast unit tests
   |
Start Testcontainers MongoDB replica set
   |
Run Spring Data integration tests
   |
Run API tests
   |
Collect sanitized reports
   |
Stop/remove ephemeral resources
   |
Package artifact if all gates pass
```

### 32.2. On a Developer Machine

Illustrative commands for learners:

```bash
mvn test
```

Or:

```bash
./gradlew test
```

These commands **must not be executed by the worker in STEP 4**. Only run them in a project environment with valid dependency versions and a working Docker/container runtime.

### 32.3. CI Requirements

- Authorized Docker daemon or container runtime.
- Permission to pull the pinned MongoDB image version.
- Local container networking allowing the test host/driver to connect.
- Sufficient CPU, RAM, and disk space.
- Zero production credentials.
- Tests free of wall-clock or execution-order dependencies.
- Resource cleanup even when jobs are canceled.
- JUnit failure reporting without leaking secrets.
- Appropriate dependency caching.
- A test matrix matching your current MongoDB version and upgrade target.

### 32.4. Container Startup Failure Is an Environment Error

If Testcontainers reports no Docker environment found:

- Verify a supported Docker/Podman provider.
- Verify user permissions on the container runtime socket.
- Check image pulls, proxies, and registry policies.
- Inspect Docker Desktop/WSL/CI runner health.
- Never replace failing integration tests with mocked MongoDB and claim integration passed.

If containers cannot run in CI, provision an isolated MongoDB test cluster with dedicated URIs, scoped permissions, and equivalent test isolation.

## 33. Observing the Java/MongoDB Application

### 33.1. Essential Metrics

- HTTP request rate, latency, and error rate per endpoint.
- MongoDB command latency and errors.
- Connection pool wait times and timeouts.
- Transaction begins, commits, aborts, and retries.
- Duplicate-key error rate.
- Schema validation failure rate.
- Inventory conflicts and out-of-stock responses.
- Idempotency key reuse vs. conflict events.
- Unknown commit outcomes.
- Replica set elections and replication lag.
- Query p95/p99 latency and documents examined.
- JVM heap, GC pauses, and thread pools.

### 33.2. Sample Structured Log

```json
{
  "event": "reservation_attempt",
  "requestId": "req_...",
  "tenantScope": "tenant-demo",
  "productId": "prod_...",
  "quantity": 2,
  "outcome": "CONFIRMED",
  "transactionDurationMs": 24,
  "duplicateRequest": false
}
```

In production, consider hashing request IDs or trimming identifiers per privacy/retention policies. Never log full MongoDB URIs, secrets, or complete customer payloads.

### 33.3. API Health vs. Consumer Health

If adding a change-stream or outbox worker:

- The HTTP API may look healthy while the CDC consumer lags.
- The consumer may be alive while its checkpoint stalls.
- Readiness/liveness probes should reflect each service's role.
- Alert on oplog retention margins and failed reconciliations.
- `"connected=true"` does not prove downstream projections are caught up.

## 34. Common Integration Pitfalls

| Symptom | Common Cause | Investigation Direction |
| --- | --- | --- |
| Transaction test reports standalone | URI points to standalone MongoDB | Use Testcontainers replica set URL |
| `@Transactional` does not roll back | Missing `MongoTransactionManager`, self-call, session mismatch | Inspect bean/proxy, run rollback test |
| Duplicate SKU test passes both inserts | Unique index missing | Check `getIndexes()` / `auto-index-creation` |
| `Product.version` does not increment as expected | Raw update omits version or different mapping | Compare `@Version` vs. raw driver behavior |
| Price stored as Integer/Double | Mapper/JSON conversion | Assert raw BSON types and DTOs |
| JSON validation skipped | Missing `starter-validation` or `@Valid` | Add MockMvc negative test |
| Transaction write conflict | Hot product / concurrent writes | Bounded retries, CAS/version, partition hot keys |
| `DuplicateKey` on request retry | Concurrent same-request race or payload mismatch | Read ledger and compare identity |
| Out of stock yet reservation exists | Missing transaction or faulty error handling | Test atomic stock+ledger rollback |
| Timeout during commit | Unknown outcome | Retry commit or reconcile; never blind-reserve |
| Spring app cannot connect to DB | URI, credentials, TLS, network, server selection | Log sanitized connection metadata |
| Testcontainers fails to start | Docker runtime, image pull, or networking | Inspect CI provider/daemon |
| `@DataMongoTest` lacks service bean | Data slice loads data layer only | Import bean/config or use `@SpringBootTest` |
| Tests depend on previous tests | Shared IDs, global counts, missing cleanup | Random keys and isolated DBs |
| Tests pass locally, fail in CI | Version mismatch, timing, lower capacity | Pin versions and eliminate `sleep` |
| Queries slow on large datasets | Missing index, bad plan, low cardinality | Run `explain`/metrics on realistic data |
| BSON ObjectId vs. String mismatch | ID converter or annotation | Write raw BSON readback test |
| `$elemMatch` replaced by dot filters | Cross-element false positive | Add array regression fixtures |
| Invalid schema insert succeeds | Validator action set to `warn`/off | Check `collectionInfo`/options |
| Null and missing treated identically | DTO loses field presence | Add API-to-BSON round-trip tests |
| Cross-tenant data leak | Missing tenant filter/auth | Add negative security tests |
| Migration breaks older app nodes | Strict validator enabled before all writers updated | Follow expand/migrate/contract |
| Indexes built on prod startup | `auto-index-creation` enabled in prod | Separate DDL migrations |
| Mocks pass while real DB rejects | Unit tests substituting for integration tests | Run Testcontainers suite |

## 35. Deploying to Production with Confidence from Tests

### 35.1. Pre-Deployment Checklist

- Lock compatible MongoDB Server/FCV, driver, and Spring Boot versions.
- Verify all indexes and validators on the target database.
- Audit duplicate `tenant+sku` records and legacy BSON types.
- Verify data retention, backups/PITR, and restore drills.
- Confirm API ownership and auth scopes.
- Review connection pools and write/read concerns.
- Verify driver transaction error and retry handling.
- Enable feature flags, SLOs, and metrics.
- Run automated tests against a matching MongoDB topology.

### 35.2. Phased Rollout

```text
Schema/contract design
      |
      v
Create compatible indexes / data migration
      |
      v
Deploy reader compatible with old/new shape
      |
      v
Deploy writer new shape (canary)
      |
      v
Backfill legacy data
      |
      v
Validator moderate -> strict
      |
      v
Rollout wider traffic with monitoring
      |
      v
Remove compatibility code after rollback window
```

Never force all app instances onto a breaking schema change in one uncontrolled deploy. If a strict DB validator rejects an older writer, rolling back application code can trigger an outage.

### 35.3. Post-Rollout Monitoring

- HTTP 409 rates split by stock conflicts vs. idempotency conflicts.
- Error 121 document validation failures.
- E11000 duplicate-key errors.
- Transaction commit retries and unknown outcomes.
- Replication lag and disk pressure.
- Product `version` progression and anomalies.
- Reservation ledger consistency.
- API p95/p99 latencies.
- Client retry rates.

If an indicator spikes unexpectedly, halt the rollout per runbook; never weaken durability or drop unique constraints to hide errors.

### 35.4. Rollback and Data Recovery

Rolling back the Java service **does not undo** committed documents or created reservations. You may need to:

- Maintain backward schema compatibility.
- Reconcile reservations before releasing stock.
- Preserve ledgers for uncertain commands.
- Restore from backup/PITR per policy if corruption occurs.
- Emit compensating events when downstream systems already consumed an event.
- Retain audit logs for every mutation.

## 36. Ordered Practice Checklist

1. Select compatible Spring Boot, driver, and Testcontainers versions; replace placeholders.
2. Create a Java 17 project with Spring Boot starters for web, data-mongodb, validation, and test.
3. Implement the `Product` and `Reservation` entities.
4. Define the repositories.
5. Configure `MongoTransactionManager`.
6. Implement `StockService` with atomic `available >= quantity` filtering and transactional reservation inserts.
7. Build the controller, DTOs, and error mapping.
8. Set up a Testcontainers MongoDB replica set with `DynamicPropertySource`.
9. Write tests for BSON readback, tenant/unique enforcement, stock reservation, insufficient stock, and idempotent retries.
10. Write transaction rollback tests and error-path assertions.
11. Write invalid-payload API tests and negative tenant/auth tests.
12. Write array, nullability, and schema-validator tests in isolated namespaces.
13. Add concurrency, fault-injection, and reconciliation tests.
14. Inspect `explain` for critical queries.
15. Configure CI to run JUnit and archive sanitized test reports.
16. Benchmark SLOs on representative data before canary deployment.
17. Maintain rollback/recovery runbooks and observability.

This checklist is **for learners building the project**, not a documentation QA pass. STEP 4 only authors the lesson and verifies the saved file.

## 37. Advanced Exercises

### Exercise A — Basic CRUD

Implement `GET /products/{id}` and `PUT /products/{id}` with tenant scoping. Write integration tests covering found products, missing products, cross-tenant denial, and `version` updates.

### Exercise B — Unique Index

Concurrently insert two products with the same `tenant+sku`. Confirm only one document exists for that key and distinguish `E11000` from connection or validation errors.

### Exercise C — Money and BSON

Create a product priced at `9_007_199_254_740_993L` and verify exact Int64 round-trip between Java and MongoDB. What happens if a JavaScript client sends it as a JSON `Number`?

### Exercise D — Bean Validation

Send an API request with `priceCents:-1`, `sku:""`, and `available:-2`. Assert HTTP 400 and confirm no record was written to the database.

### Exercise E — Atomic Reservation

With 5 items in stock, launch two concurrent requests each trying to reserve 4. Assert `available >= 0`, total reservations ≤ 5, and no ledger written without stock decrement.

### Exercise F — Idempotency

Send the same `requestId` and payload twice: stock is deducted once. Send the same `requestId` with a different payload: reject as conflict. After a commit timeout, reconcile using the ledger.

### Exercise G — Optimistic Locking

Have two `version=4` entity snapshots concurrently update price. Verify the stale save does not overwrite the newer version. Contrast this with a raw driver update lacking a version predicate.

### Exercise H — Null vs. Missing

Create a `profiles` collection containing missing, `null`, and empty-string `nickname` values. Test `{nickname:null}`, `$exists`, `$type`, and Java `containsKey`.

### Exercise I — Array `$elemMatch`

Create an order with two lines: A (quantity 1) and B (quantity 10). Write a query matching only when **line A itself** has quantity ≥ 5, and verify why naive dot notation fails.

### Exercise J — Schema Validator

Create a test collection requiring `bsonType:"long"` for price. Insert a valid `Long`, an invalid `String`, and missing/`null`; assert error 121 and verify readback.

### Exercise K — Transaction Rollback

Inject an exception after the product decrement but before inserting the ledger. Assert the entire transaction rolls back and `available` remains unchanged.

### Exercise L — Unknown Commit

Design a fault-injection test where commit succeeds but the response is lost. What should the API return? When do you retry commit on the same session vs. reconcile by `requestId`?

### Exercise M — Performance

An API lists products filtered by tenant and status, sorted by `updatedAt`. Choose a compound index and verify it with `explain` on a sufficiently large dataset.

### Exercise N — API Security

Tenant A attempts to reserve tenant B's product using a guessed `productId`. Verify controller, service, and DB filters alongside authorized tenant resolution.

### Exercise O — Testcontainers CI

Write a CI pipeline running unit tests followed by replica-set integration tests. Document how to handle an unavailable Docker daemon and image pinning.

### Exercise P — Schema Evolution

Make `currency` required on `Product`. Plan reader compatibility, writer rollout, backfill, `warn`/`moderate`/`strict` validator transitions, and negative tests.

### Exercise Q — Change Stream / Outbox

Emit a `ReservationCreated` event after commit and have a worker dispatch messages. Write tests for deduplication, ordering, lost ACKs, restart/resume tokens, and cleanup.

### Exercise R — Bulk Import

Import 100 products containing 3 duplicate SKUs and 2 invalid prices. Compare ordered vs. unordered bulk behavior, partial success, and stable-ID retries.

### Exercise S — Disaster Recovery

MongoDB restores back 15 minutes while another service holds newer reservations. Propose a ledger reconciliation, event replay, and oversell prevention alert strategy.

### Exercise T — ADR

Write an Architecture Decision Record comparing Spring Data MongoDB against the plain Java Sync Driver for the reservation service across team skill, complexity, transaction semantics, testability, and operational cost.

## 38. Official References

### MongoDB and Java

- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — connections, BSON, CRUD, and transactions.
- [MongoDB Java Driver Compatibility](https://www.mongodb.com/docs/drivers/java/sync/current/compatibility/) — driver, Java runtime, and server version matrix.
- [MongoDB CRUD Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/) — insert, find, update, and delete.
- [MongoDB Java Sync Driver Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — sessions, callback/core APIs, and retry labels.
- [BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/) — Int32, Int64, Decimal128, ObjectId, and Date.
- [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — `$jsonSchema`, validation levels, and actions.
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — uniqueness, null handling, and compound rules.
- [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/) — single-document atomicity.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — durability and replication.
- [Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — write retries and limitations.
- [Change Streams](https://www.mongodb.com/docs/manual/changestreams/) — CDC when adding an outbox consumer.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — inspecting query execution plans.

### Spring

- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/) — repositories, `MongoTemplate`, mapping, optimistic locking, and transactions.
- [Spring Boot Data Access / MongoDB](https://docs.spring.io/spring-boot/reference/data/nosql.html) — auto-configuration and properties.
- [Spring Framework Test](https://docs.spring.io/spring-framework/reference/testing/) — integration test context.
- [Spring Boot Testing](https://docs.spring.io/spring-boot/reference/testing/) — `@SpringBootTest`, `MockMvc`, and test slices.
- [Spring Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/) — proxies and transaction lifecycles.

### JUnit and Testcontainers

- [JUnit User Guide](https://junit.org/junit5/docs/current/user-guide/) — Jupiter, parameterized tests, and lifecycles.
- [Testcontainers Java](https://java.testcontainers.org/) — container-based integration testing.
- [Testcontainers MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/) — `MongoDBContainer` and replica set URLs by version.
- [Spring Boot Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html) — Spring Boot integration.

**Version note:** Some URLs may change across documentation versions. MongoDB server features, Spring Boot 3/4, Spring Data major versions, Testcontainers 1/2, and Java Driver releases each have distinct compatibility matrices. Lock dependency versions using official matrices and never mix API imports or configuration styles across major releases.

## 39. Conclusion

A reliable Java application integrated with MongoDB requires far more than calling `repository.save()`.

1. **Choose the right API:** the Java Sync Driver for direct BSON/command control; Spring Data for entity mapping, repositories, `MongoTemplate`, and transaction integration.
2. **Start from invariants:** tenant ownership, unique SKUs, BSON Int64 prices, non-negative `available`, and non-repeating request IDs.
3. **Use atomic conditional updates** when decrementing stock and **short transactions** when multiple MongoDB documents must change together.
4. **Never overlook idempotency:** HTTP timeouts and retries can redeliver the same business request; retrying under a fresh request ID easily creates duplicate side effects.
5. **Enforce constraints in MongoDB:** unique indexes and `$jsonSchema` guard all writers, not just a single controller.
6. **Test against real MongoDB:** JUnit 5 + a Testcontainers replica set actually prove indexes, BSON types, transaction rollbacks, filters, and query semantics.
7. **Maintain test isolation:** randomized namespaces/IDs, scoped cleanup, zero real data, and no order dependencies.
8. **Separate correctness from performance:** integration tests prove business invariants; `explain` and load tests prove indexes and SLOs on representative workloads.
9. **Monitor failure paths too:** duplicate keys, validation errors, transient/unknown transaction outcomes, network timeouts, and reconciliation.
10. **Evolve schemas cleanly:** when changing schemas or indexes, deploy compatible readers/writers, backfill, tighten validation in stages, and preserve a rollback plan.

**Core principle:** turn every critical application invariant into an **automated test running against real MongoDB Server**, backed by database constraints and sound recovery protocols. When these layers work together, Java/Spring Data integration does not just "work on the happy path"—it stays correct across duplicate requests, bad inputs, concurrent threads, transaction rollbacks, and future upgrades.
