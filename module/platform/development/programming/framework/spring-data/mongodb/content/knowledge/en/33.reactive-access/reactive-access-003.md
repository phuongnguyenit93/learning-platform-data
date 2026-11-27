# AbstractReactiveMongoConfiguration and @EnableReactiveMongoRepositories

## 1. Problem: Initializing Reactive MongoDB Access

In the **Reactive access** chapter of **Spring Data MongoDB**, applications can query and write documents using `ReactiveMongoTemplate` or repositories returning `Mono<T>`/`Flux<T>`. These APIs organize execution flow differently from synchronous `MongoTemplate` and `MongoRepository`: instead of blocking the calling thread waiting for results, the reactive driver supplies publishers to process data asynchronously under the Reactive Streams model.

For example, a catalog API needs to:

- Fetch a product by SKU **within an authenticated tenant**;
- List active products in a deterministic order;
- Update inventory with a conditional update;
- Detect empty results and query errors, and close connections properly with the application lifecycle.

For reactive repositories to work, Spring must know the **reactive MongoDB client**, **database**, **mapping/converters**, **`ReactiveMongoTemplate`**, and **where to scan repository interfaces**. The two central building blocks of this lesson are:

1. `AbstractReactiveMongoConfiguration`: Spring Data MongoDB's base configuration class for configuring reactive MongoDB access infrastructure **manually and explicitly**.
2. `@EnableReactiveMongoRepositories`: enables discovery of **reactive repository interfaces** and generates repository proxies, optionally specifying scan packages or the template bean to use.

In a **Spring Boot** project using `spring-boot-starter-data-mongodb-reactive`, many beans and repository scanning **can be auto-configured**. Therefore, not every application needs to extend `AbstractReactiveMongoConfiguration` or add `@EnableReactiveMongoRepositories`. This lesson presents both **alternatives/trade-offs**, and recommends against stacking redundant configurations on top of each other.

### Target Outcomes

1. Understand the role of each bean from the reactive driver to `ReactiveMongoRepository`.
2. Write a configuration extending `AbstractReactiveMongoConfiguration` with `reactiveMongoClient()` and `getDatabaseName()`.
3. Use `@EnableReactiveMongoRepositories(basePackageClasses = ...)` to target the exact repositories to scan.
4. Distinguish manual configuration from Spring Boot auto-configuration.
5. Practice `Mono`, `Flux`, `ReactiveMongoTemplate`, `@Document`/`@Field` mapping, tenant filtering, and empty-result errors.
6. Understand subscription, avoid arbitrary `block()` in WebFlux, and manage backpressure and client lifecycle.
7. Test against a real MongoDB instance with Reactor `StepVerifier`; diagnose startup failures and reactive transaction/context issues.

> Examples target Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x, and a compatible MongoDB version. Specific API signatures or behavior may differ in other versions. Use the coherent version set managed by Spring Boot; do not mix synchronous and reactive MongoDB drivers expecting them to be interchangeable.

## 2. Reactive MongoDB Architecture in Spring

Flow from application to MongoDB:

~~~mermaid
flowchart TD
    A["HTTP request / reactive job"] --> B["Reactive service returning Mono / Flux"]
    B --> C["ReactiveMongoRepository proxy"]
    B --> D["ReactiveMongoTemplate"]
    C --> D
    D --> E["ReactiveMongoDatabaseFactory"]
    E --> F["Reactive Streams MongoClient"]
    F --> G["MongoDB server"]
    H["Mapping context + MongoConverter"] --> D
    I["@EnableReactiveMongoRepositories"] --> C
    J["AbstractReactiveMongoConfiguration or Boot auto-config"] --> E
    J --> H
~~~

| Component | Primary Responsibility |
|---|---|
`com.mongodb.reactivestreams.client.MongoClient` | Connects to MongoDB using the Reactive Streams driver; not the sync `MongoClient` |
`ReactiveMongoDatabaseFactory` | Provides reactive access to the database, supporting compatible context/sessions |
`ReactiveMongoTemplate` | Reactive API for queries, updates, aggregations, indexes, and conversion |
Mapping context/converter | Maps Java classes/records to BSON, `@Id`/`@MongoId`, `@Field`, nested types |
`ReactiveMongoRepository<T, ID>` | Repository abstraction, implemented via a Spring-generated proxy |
`@EnableReactiveMongoRepositories` | Configures repository scanning and template references |
`AbstractReactiveMongoConfiguration` | Base configuration for reactive infrastructure |
Spring Boot auto-configuration | Provides these beans when the starter and conditions match |

A repository does not open connections via `new`. It is a **Spring bean proxy** and requires valid reactive infrastructure in the application context.

### 2.1. Reactive Does Not Mean “MongoDB Handles Infinite Requests”

Asynchronous I/O avoids holding an application thread blocked per database wait. However:

- The MongoDB server still needs CPU, RAM, indexes, connection pools, and disk I/O.
- Slow queries stay slow if filters lack indexes, scan too broadly, or run expensive aggregations.
- Calling blocking code on the event loop can degrade a WebFlux application.
- Collecting millions of rows into a `List` still exhausts memory even if the source is a `Flux`.
- Reactive programming does not automatically provide transactions, tenant security, or safe retries.

## 3. Choosing Between Spring Boot Auto-Configuration and Manual Configuration

Two common initialization paths:

| Scenario | Preferred Approach |
|---|---|
Spring Boot, single MongoDB database, standard schema | Reactive starter and Boot auto-configuration |
Need explicit control over bean factory/template/repository scan | Explicit configuration, optionally using `AbstractReactiveMongoConfiguration` |
Not using Spring Boot | Manual Spring Data configuration |
Multiple MongoDB databases/templates | Named configurations, explicit template references, scoped repository scans |
Migrating from sync to reactive | Verify driver/starter and APIs explicitly; do not just change return types to `Mono` |

**Operational rule:** choose **one primary owner** for creating the client/factory/template and scanning repositories. Letting Boot auto-configure while also declaring competing manual beans with conflicting names can cause bean conflicts, duplicate scans, or connections pointing somewhere unexpected.

### 3.1. Option A: Spring Boot Auto-Configuration

Gradle dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb-reactive'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

`spring-boot-starter-webflux` is only required when building WebFlux HTTP APIs; a reactive batch/job does not strictly need WebFlux. `reactor-test` provides `StepVerifier`.

Configuration example:

~~~yaml
spring:
  data:
    mongodb:
      uri: "${MONGODB_URI:mongodb://localhost:27017/catalogdb}"
~~~

With this approach, Spring Boot can create the reactive client, database factory, template, and reactive repositories **when auto-configuration and repository-scanning conditions match**. A standard app with `@SpringBootApplication` in a parent package above its repositories normally does not need `@EnableReactiveMongoRepositories`.

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Place repositories in `com.example.catalog` or a sub-package. If repositories live outside the scan root, adjust scanning explicitly instead of assuming the framework will search the entire classpath.

### 3.2. Option B: AbstractReactiveMongoConfiguration

When you need explicit control, write a `@Configuration` extending this Spring Data base class. The complete configuration is shown in section 6; the difference is that you explicitly supply the **reactive `MongoClient`** and **database name**, while the base class wires the supporting infrastructure beans.

In Spring Boot, Option B fits when the project explicitly owns infrastructure rather than relying fully on Boot auto-configuration. Avoid enabling both configuration setups inadvertently.

## 4. Dependencies and the Right MongoClient Type

For reactive access, use:

~~~java
import com.mongodb.reactivestreams.client.MongoClient;
import com.mongodb.reactivestreams.client.MongoClients;
~~~

Do not confuse with:

~~~java
// Synchronous driver, NOT the type used in the reactive configuration below:
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
~~~

Both types share the simple name `MongoClient` but reside in different packages. The reactive driver executes publisher-based operations; the sync driver executes blocking calls. `MongoTemplate` and `ReactiveMongoTemplate` are likewise distinct.

### 4.1. Why Should You Avoid Mixing Driver Versions?

Spring Boot manages dependency versions via its BOM. Forcing a newer or older MongoDB Reactive Streams Driver incompatible with Spring Data MongoDB in the same runtime can cause missing class/method errors or subtle runtime differences.

Process:

1. Pick an appropriate Spring Boot release line.
2. Use `spring-boot-starter-data-mongodb-reactive` aligned with the BOM.
3. Only override dependency versions after checking compatibility matrices and testing.
4. If the project also includes the sync starter, check whether Boot creates **both clients/templates** or only one set.

### 4.2. A Client Is a Long-Lived Resource

`MongoClient` holds a connection pool and internal resources. Never create a new client **per request**:

~~~java
// Avoid:
public Mono<?> everyRequest() {
    MongoClient client = MongoClients.create(uri);
    // Repeatedly creating new clients; hard to close or reuse the pool.
    throw new UnsupportedOperationException("Anti-pattern illustration");
}
~~~

This snippet illustrates a design flaw, not runnable service code. In real applications, use a **Spring-managed singleton `MongoClient`** with proper lifecycle and shutdown cleanup.

## 5. Sample Entity: BSON Structure and Java Field Names

We use the `catalog_products` collection:

~~~json
{
  "_id": "p-101",
  "tenantId": "tenant-a",
  "sku": "BOTTLE-500",
  "name": "Insulated water bottle",
  "status": "ACTIVE",
  "stock_qty": 12,
  "createdAt": { "$date": "2026-11-20T08:00:00Z" }
}
~~~

**CatalogProduct.java**

~~~java
package com.example.catalog;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "catalog_products")
public record CatalogProduct(
        @MongoId(FieldType.STRING) String id,
        String tenantId,
        String sku,
        String name,
        String status,
        @Field("stock_qty") long stockQty,
        Instant createdAt) {
}
~~~

Details:

- `@Document` maps the entity to the `catalog_products` collection.
- `@MongoId(FieldType.STRING)` keeps `_id` as a BSON String matching the example schema.
- The Java property `stockQty` is stored as BSON `stock_qty` via `@Field`.
- `createdAt` is used when sorting lists.
- `tenantId` scopes data by tenant and is **not automatically added to every query by Spring**.

Repositories can use **Java property names** in derived queries. When writing raw BSON in the driver or custom aggregation stages, reference the actual **BSON field names**.

### 5.1. Reactive Entity Mapping Does Not Enforce Business Invariants

Java records provide shallow immutability at the component-reference level, ideal for read/write payloads. However, they do not enforce invariants like “non-negative stock,” “one SKU per tenant,” or “only ACTIVE products can be sold.” Those invariants require conditional updates, unique indexes, validation, tenant authorization, and thorough tests.

## 6. Manual Configuration with AbstractReactiveMongoConfiguration

Here is a **self-contained** configuration for reactive access when a project chooses manual control over relying entirely on Boot auto-configuration.

**ReactiveMongoConfig.java**

~~~java
package com.example.catalog;

import com.mongodb.reactivestreams.client.MongoClient;
import com.mongodb.reactivestreams.client.MongoClients;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.config.AbstractReactiveMongoConfiguration;
import org.springframework.data.mongodb.repository.config.EnableReactiveMongoRepositories;

@Configuration
@EnableReactiveMongoRepositories(
        basePackageClasses = CatalogProductRepository.class)
public class ReactiveMongoConfig
        extends AbstractReactiveMongoConfiguration {

    private final String connectionString;
    private final String databaseName;

    public ReactiveMongoConfig(
            @Value("${app.mongodb.uri}") String connectionString,
            @Value("${app.mongodb.database}") String databaseName) {
        this.connectionString = connectionString;
        this.databaseName = databaseName;
    }

    @Override
    protected String getDatabaseName() {
        return databaseName;
    }

    @Bean(destroyMethod = "close")
    @Override
    public MongoClient reactiveMongoClient() {
        return MongoClients.create(connectionString);
    }
}
~~~

Example properties for this configuration:

~~~yaml
app:
  mongodb:
    uri: "${MONGODB_URI:mongodb://localhost:27017}"
    database: "catalogdb"
~~~

These are **custom properties** read by `ReactiveMongoConfig`, not automatic aliases for `spring.data.mongodb.uri`. With manual configuration, explicitly define how config and secrets are injected. In production, never hardcode MongoDB passwords in source files.

**Important:** place `ReactiveMongoConfig`, repositories, and entities inside scanned packages. Here, `basePackageClasses = CatalogProductRepository.class` targets the repository package; services still require component scanning or explicit bean imports.

### 6.1. Role of Each Override

| Component | Role |
|---|---|
`getDatabaseName()` | Specifies the database name used by reactive MongoDB infrastructure |
`reactiveMongoClient()` | Supplies `com.mongodb.reactivestreams.client.MongoClient` |
`@Bean(destroyMethod = "close")` | Places the client lifecycle under Spring; closes it on context shutdown |
`@EnableReactiveMongoRepositories(...)` | Scans and registers repository proxies |
`AbstractReactiveMongoConfiguration` | Provides base beans for mapping, converters, database factory, and template per Spring Data version |

The base class does not solve tenant authentication or query design; it is purely an **infrastructure assembly point**.

### 6.2. Why Declare @Bean When Overriding the Client?

Exposing `MongoClient` as a Spring bean enables connection pool reuse, injection, lifecycle management, and context verification. Some Spring Data API examples override `reactiveMongoClient()` without showing every annotation depending on version; here `@Bean` is declared explicitly to highlight resource lifecycle management.

Do not declare two manual client beans for the same database unless intentionally designed: one template using client A while a repository uses client B can create hard-to-diagnose configuration bugs.

### 6.3. Difference Between getDatabaseName and the URI

`MongoClients.create(connectionString)` configures how the driver connects and authenticates. `getDatabaseName()` selects the database used by Spring Data. When the URI already specifies a default database or authentication bound to an `authSource`, keep them consistent:

- Do not assume the DB name from the URI path if manual configuration returns a different name.
- Avoid accidentally writing test collections into a production DB due to a mismatched `getDatabaseName()`.
- For URIs with credentials, verify `authSource` and user permissions on the actual target database.

## 7. How Does @EnableReactiveMongoRepositories Scan and Create Proxies?

The annotation:

~~~java
@EnableReactiveMongoRepositories(
        basePackageClasses = CatalogProductRepository.class)
~~~

declares where repository interfaces live. Spring Data scans the package of `CatalogProductRepository`, finds eligible reactive repository interfaces, and generates proxies backed by the selected `ReactiveMongoTemplate`.

### 7.1. Precise Meaning of Base Packages

| Declaration Style | When Appropriate |
|---|---|
`@EnableReactiveMongoRepositories` with no args | Scans the configuration class package and sub-packages per framework rules |
`basePackages = "com.example.catalog"` | When specifying package names as strings |
`basePackageClasses = CatalogProductRepository.class` | More refactor-safe than string package names |
`reactiveMongoTemplateRef = "reactiveMongoTemplate"` | When selecting a specific template bean, especially with multiple templates |

Do not scan the company's top-level root package “just to be safe”; overly broad scans can pick up unrelated repositories or cause duplicate definitions. Also do not use `@EnableMongoRepositories` (imperative) expecting it to generate reactive repository proxies.

### 7.2. @EnableReactiveMongoRepositories Does Not Start a Database Server

It does **not** launch `mongod`, create a replica set, or configure networking. Repository proxies can be instantiated in the Spring context, while actual operations will still fail if the URI, credentials, or server are invalid.

### 7.3. Repository Scanning Differs from Entity Mapping

`basePackageClasses` here sets the **repository scan scope**. Entity mapping is normally discovered/registered via the mapping context, metadata, and configuration package rules. If entities live in another package and mapping errors occur, check `getMappingBasePackages`/entity scan settings; do not assume the repository scan package covers all entity mapping packages.

## 8. ReactiveMongoRepository: Declaring Search Methods

**CatalogProductRepository.java**

~~~java
package com.example.catalog;

import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface CatalogProductRepository
        extends ReactiveMongoRepository<CatalogProduct, String> {

    Mono<CatalogProduct> findByTenantIdAndSku(
            String tenantId, String sku);

    Flux<CatalogProduct> findByTenantIdAndStatusOrderByCreatedAtDesc(
            String tenantId, String status);

    Mono<Boolean> existsByTenantIdAndSku(
            String tenantId, String sku);

    Mono<Long> countByTenantIdAndStatus(
            String tenantId, String status);
}
~~~

Following these conventions:

- `findByTenantIdAndSku` matches equality on `tenantId` and `sku`.
- `findByTenantIdAndStatusOrderByCreatedAtDesc` selects the tenant's ACTIVE items sorted newest first.
- `existsBy...` returns `Mono<Boolean>`, not a direct boolean upon invocation.
- `countBy...` returns `Mono<Long>`.

**Derived repository queries use Java property names**, not BSON names, in the method signature. For a field annotated with `@Field("stock_qty")`, a method like `findByStockQtyGreaterThanEqual` still uses `StockQty`, and the converter translates the storage field name.

### 8.1. Mono vs Flux Differences

| Type | Expected Meaning | Example |
|---|---|---|
`Mono<CatalogProduct>` | 0 or 1 document | Find one SKU in a tenant |
`Flux<CatalogProduct>` | 0..N documents | List ACTIVE products |
`Mono<Boolean>` | Single existence check result | `existsByTenantIdAndSku` |
`Mono<Long>` | Single count result | `countByTenantIdAndStatus` |
`Mono<Void>` | Represents completion/error only | `deleteAll` or a command pipeline |

An **empty** `Mono<CatalogProduct>` is not a null document. Reactor never emits `null` as a normal element. When an entity is absent, use `switchIfEmpty`/`defaultIfEmpty`/`hasElement` according to contract.

### 8.2. Derived Queries Do Not Enforce Tenant Checks Automatically

Repositories inherit methods like `findAll()`. In a multi-tenant app, calling `findAll()` from an HTTP endpoint could expose **every tenant's products**, even if other methods use `findByTenantId...`.

Design services and APIs to pull the tenant from a **trusted auth context**; never accept an arbitrary client-supplied tenant ID as authorization. Good indexes do not replace authorization checks.

## 9. Writing Reactive Services Over Repositories: Don't Block, Don't Self-Subscribe

**CatalogQueryService.java**

~~~java
package com.example.catalog;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class CatalogQueryService {
    private final CatalogProductRepository repository;

    public CatalogQueryService(CatalogProductRepository repository) {
        this.repository = repository;
    }

    public Mono<CatalogProduct> findBySku(
            String authenticatedTenantId, String sku) {
        requireTenant(authenticatedTenantId);
        if (sku == null || sku.isBlank()) {
            return Mono.error(new IllegalArgumentException("Empty SKU"));
        }

        return repository.findByTenantIdAndSku(authenticatedTenantId, sku)
                .switchIfEmpty(Mono.error(
                        new CatalogProductNotFoundException(sku)));
    }

    public Flux<CatalogProduct> activeProducts(
            String authenticatedTenantId) {
        requireTenant(authenticatedTenantId);

        return repository
                .findByTenantIdAndStatusOrderByCreatedAtDesc(
                        authenticatedTenantId, "ACTIVE");
    }

    public Mono<Boolean> existsBySku(
            String authenticatedTenantId, String sku) {
        requireTenant(authenticatedTenantId);
        if (sku == null || sku.isBlank()) {
            return Mono.error(new IllegalArgumentException("Empty SKU"));
        }
        return repository.existsByTenantIdAndSku(
                authenticatedTenantId, sku);
    }

    private static void requireTenant(String tenantId) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Invalid tenant");
        }
    }
}
~~~

**CatalogProductNotFoundException.java**

~~~java
package com.example.catalog;

public class CatalogProductNotFoundException
        extends RuntimeException {
    public CatalogProductNotFoundException(String sku) {
        super("Product not found for SKU: " + sku);
    }
}
~~~

`CatalogQueryService` returns Publishers so the caller—the WebFlux HTTP runtime, a batch pipeline, or a test—controls subscription. Never call `subscribe()` inside the service just to “kick off the query”; doing so detaches the query from the caller's result, errors, cancellation, and lifecycle.

### 9.1. Mono.empty Differs from Exceptions

A repository SKU lookup typically returns `Mono.empty()` when no document matches. The service enforces a “missing product is a domain error” contract with:

~~~java
return repository.findByTenantIdAndSku(tenantId, sku)
        .switchIfEmpty(
                Mono.error(new CatalogProductNotFoundException(sku)));
~~~

To map that to HTTP 404, the WebFlux layer can translate the domain exception. If “not found is valid and optional,” keep `Mono.empty()` or return an appropriate response DTO. Never use `null` in place of an empty Publisher.

### 9.2. Tenant Must Come from a Trusted Source

The parameter `authenticatedTenantId` emphasizes that the tenant is resolved by server-side authentication and authorization. Controllers must never pass through a raw query-string `tenantId` bypassing the principal's permissions.

In WebFlux, you can build a component that extracts the tenant from the security context/principal and compose:

~~~java
return authenticatedTenantProvider.currentTenantId()
        .flatMap(tenantId -> catalogQueryService.findBySku(
                tenantId, sku));
~~~

This fragment assumes `currentTenantId()` returns `Mono<String>` containing only an authorized tenant. It shows where security context integrates with the reactive flow, not a complete security provider implementation. **Never treat a client-chosen `tenantId` as trustworthy**.

## 10. Mono, Flux, and Subscription: When Do Commands Execute?

In Reactor, most publishers returned from repositories and templates are **cold**: they merely describe work until subscribed, and the actual query is triggered upon subscription per publisher semantics.

~~~java
Mono<CatalogProduct> pending =
        repository.findByTenantIdAndSku("tenant-a", "BOTTLE-500");

// Nothing blocked, nothing subscribed, and no result yet here.
~~~

In WebFlux, the framework subscribes to the Publisher returned by the handler. In tests, `StepVerifier` subscribes to verify signals. In batch apps, the pipeline connects to an orchestrator with an explicit lifecycle.

### 10.1. Do Not Return Entities via block()

Avoid:

~~~java
public CatalogProduct unsafe(String tenantId, String sku) {
    return repository.findByTenantIdAndSku(tenantId, sku)
            .block();
}
~~~

`block()` converts waiting into blocking behavior, risking event-loop stalls or errors on non-blocking threads. Do not use it as a default adapter to turn reactive APIs into imperative ones.

Better:

~~~java
public Mono<CatalogProduct> correct(String tenantId, String sku) {
    return repository.findByTenantIdAndSku(tenantId, sku);
}
~~~

If your application is purely synchronous, consider imperative `MongoTemplate`/repositories from the start instead of writing reactive code and blocking at every layer.

### 10.2. map and flatMap

`map` is for **synchronous** transformations:

~~~java
Mono<String> name =
        repository.findByTenantIdAndSku("tenant-a", "BOTTLE-500")
                .map(CatalogProduct::name);
~~~

`flatMap` is used when a step returns a **Publisher**:

~~~java
Mono<Boolean> active =
        repository.findByTenantIdAndSku("tenant-a", "BOTTLE-500")
                .flatMap(product ->
                        repository.existsByTenantIdAndSku(
                                product.tenantId(), product.sku()));
~~~

This illustrates composition; checking `exists` here is redundant in real logic because the document was already loaded. The point is that `flatMap` chains another async step **without calling `block()`**.

### 10.3. Calling subscribe() in a Service Is Not Safe Fire-and-Forget

Wrong:

~~~java
public Mono<Void> unsafeWrite(CatalogProduct product) {
    repository.save(product).subscribe();
    return Mono.empty();
}
~~~

The caller receives an immediately completing `Mono.empty()`, while the write runs under an unlinked subscription. Database errors may go unhandled by the caller, and cancellation, transaction context, backpressure, and outcomes are decoupled.

Better:

~~~java
public Mono<Void> saveThenComplete(CatalogProduct product) {
    return repository.save(product).then();
}
~~~

The caller subscribes to a single Publisher representing **the actual outcome of the work**. For standalone batch workers, use a subscriber with explicit lifecycle, logging, retry, and shutdown handling—never an unmonitored `subscribe()`.

### 10.4. Multiple Subscriptions Can Repeat Operations

With a cold Publisher, each subscription can trigger another query or write. Never write:

~~~java
Mono<CatalogProduct> saved = repository.save(product);
saved.subscribe();
saved.subscribe(); // May execute a second write.
~~~

Repeated `save` calls with the same ID can produce unexpected outcomes under multiple subscribers or concurrent requests. With `$inc` or external side effects, the harm is even clearer. Composition must align idempotency, retries, and subscriber ownership.

## 11. ReactiveMongoTemplate for Controlling Queries and Sorting

Repository derived queries are great for simple lookups. When filters, sorting, projections, or limits grow complex, `ReactiveMongoTemplate` expresses queries explicitly.

**CatalogTemplateQueryService.java**

~~~java
package com.example.catalog;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class CatalogTemplateQueryService {
    private final ReactiveMongoTemplate template;

    public CatalogTemplateQueryService(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Flux<CatalogProduct> newestActive(
            String authenticatedTenantId, int limit) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || limit < 1 || limit > 100) {
            return Flux.error(
                    new IllegalArgumentException("Invalid filter/limit"));
        }

        Query query = Query.query(
                Criteria.where("tenantId").is(authenticatedTenantId)
                        .and("status").is("ACTIVE"));

        query.with(Sort.by(
                Sort.Order.desc("createdAt"),
                Sort.Order.asc("id")));
        query.limit(limit);
        return template.find(query, CatalogProduct.class);
    }

    public Mono<CatalogProduct> findByIdInTenant(
            String authenticatedTenantId, String productId) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || productId == null || productId.isBlank()) {
            return Mono.error(
                    new IllegalArgumentException("Invalid input"));
        }

        Query query = Query.query(
                Criteria.where("id").is(productId)
                        .and("tenantId").is(authenticatedTenantId));
        return template.findOne(query, CatalogProduct.class);
    }
}
~~~

These queries use Java property names, so `Sort.Order.asc("id")` maps to BSON `_id`. Likewise, `Criteria.where("stockQty")` maps to `stock_qty` via `@Field`. `findByIdInTenant` intentionally avoids `findById(productId)` followed by an in-memory tenant check: filtering by tenant directly in the database reduces the risk of unauthorized access.

### 11.1. Put Limits Inside the Query for Server-Side Bounds

`Flux.take(20)` stops the client stream after 20 items, but MongoDB may still sort many documents beforehand, so server cost isn't necessarily small. For paged endpoints, apply `query.limit(20)`, sorting, and matching indexes so the server knows the bound upfront.

### 11.2. Add a Tie-Breaker to Sorts

`createdAt DESC` alone does not guarantee a unique order when multiple documents share the same timestamp. Adding `id ASC` keeps ordering stable on static datasets. For keyset paging, the cursor must carry the full `(createdAt, id)` tuple, not only the timestamp.

### 11.3. Never Collect an Entire Flux into a List Recklessly

~~~java
Mono<java.util.List<CatalogProduct>> all =
        template.find(new Query(), CatalogProduct.class)
                .collectList();
~~~

Querying with an unfiltered `new Query()` and calling `collectList()` loads every document across all tenants into memory; this is an **anti-pattern** on large/multi-tenant collections. Filter and limit at the database, stream/paginate, or design bounded batch pipelines.

## 12. Reactive Conditional Updates: Atomicity Remains MongoDB's Responsibility

Reactive APIs do not grant greater atomicity than imperative ones. For inventory, only decrement when status is ACTIVE and stock suffices:

**CatalogStockService.java**

~~~java
package com.example.catalog;

import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class CatalogStockService {
    private final ReactiveMongoTemplate template;

    public CatalogStockService(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Mono<Boolean> reserve(
            String authenticatedTenantId,
            String productId,
            long quantity) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || productId == null || productId.isBlank()
                || quantity <= 0) {
            return Mono.error(
                    new IllegalArgumentException("Invalid request"));
        }

        Query query = Query.query(
                Criteria.where("id").is(productId)
                        .and("tenantId").is(authenticatedTenantId)
                        .and("status").is("ACTIVE")
                        .and("stockQty").gte(quantity));

        Update update = new Update()
                .inc("stockQty", -quantity);

        return template.updateFirst(
                query, update, CatalogProduct.class)
                .map(result -> result.getMatchedCount() == 1);
    }
}
~~~

MongoDB receives an equivalent command:

~~~javascript
db.catalog_products.updateOne(
  {
    _id: "p-101",
    tenantId: "tenant-a",
    status: "ACTIVE",
    stock_qty: { $gte: 3 }
  },
  { $inc: { stock_qty: -3 } }
);
~~~

This is a **single-document conditional update**. Two concurrent requests each subtracting 3 from an initial stock of 5 cannot both match if every writer applies this precondition. `Mono<Boolean>` emits a value only once subscribed and acknowledged.

### 12.1. Do Not Split Read → Check → Write for “Simplicity”

Wrong:

~~~java
return repository.findById(productId)
        .flatMap(product -> {
            if (product.stockQty() < quantity) {
                return Mono.just(false);
            }
            // Saves an entity based on a stale read:
            return repository.save(new CatalogProduct(
                    product.id(), product.tenantId(),
                    product.sku(), product.name(), product.status(),
                    product.stockQty() - quantity,
                    product.createdAt())).thenReturn(true);
        });
~~~

Two streams reading the same initial stock can overwrite each other when the entity lacks a version guard. `flatMap` only handles async composition—it **does not create a transaction** and does not protect invariants when the check precedes the write.

### 12.2. Do Not Retry $inc Blindly

If the client drops its connection after the server decrements stock but before the client receives the response, an application-level retry of `reserve` as a fresh request can decrement stock twice. Reactive `retryWhen(...)` does not make a business command idempotent either.

You need a command ID and an idempotency design suited to the document/workflow scope. This is a **business correctness** concern, not a quirk unique to reactive APIs.

### 12.3. @Version Does Not Protect Every Write Path Automatically

With `@Version` on an entity, repository `save` can enforce optimistic locking via framework mechanics. With raw/custom updates or explicit template updates, check version semantics and verify BSON/`matchedCount`; do not assume every reactive update path enforces CAS versioning automatically.

## 13. ReactiveMongoClient Lifecycle and Resource Cleanup

A MongoDB client should never be created/destroyed per HTTP request. The `@Bean(destroyMethod = "close")` pattern in `ReactiveMongoConfig` ties the client to the Spring context lifecycle.

On shutdown:

1. Spring closes the application context.
2. Beans using the client stop accepting new work, and in-flight publishers need a graceful shutdown strategy.
3. `MongoClient.close()` releases connections and resources.

**Note:** closing the client is not a business transaction rollback mechanism for pending tasks. If an app stops mid-way through a non-transactional multi-step workflow, idempotency and reconciliation are required.

### 13.1. Share and Manage the Connection Pool

Do not open one `MongoClient` per repository or service. Reuse the Spring-managed reactive Mongo client unless you genuinely separate databases/credentials with clear operational justification.

When the pool is too small, requests queue waiting for connections; when too large, the server suffers resource pressure. Options like max pool size, timeouts, TLS, and authentication should be configured and measured for your workload instead of guessed.

### 13.2. The Reactive Driver Is Not an HTTP Client

The reactive MongoDB driver is not responsible for managing HTTP security tokens, tenant contexts, API rate limits, or downstream services. A reactive service must enforce proper authorization, filters, and lifecycles at the application layer.

## 14. Choosing Repository vs Template

| Requirement | Reactive Repository | ReactiveMongoTemplate |
|---|---|---|
Simple CRUD/entity access | Very suitable | Also supported |
Property-based derived queries | `findByTenantIdAndSku` | Build `Query` explicitly |
Dynamic multi-condition queries | May need custom implementation | Flexible with `Criteria`/`Query` |
Aggregation | Supports some annotations/query mechanisms | Usually more flexible |
Atomic conditional updates | Depends on repository/custom update support | Clear with `updateFirst`/`findAndModify` |
Index operations | Usually via other infrastructure | `indexOps(...)` returning reactive publishers |
Single business pipeline needing both | Can cooperate if sharing factory/session | Can cooperate if sharing factory/session |

Never pick `ReactiveMongoTemplate` thinking it is “faster than repositories”: both invoke the same driver/server, where indexes and query shape dominate performance. Repositories express domain access cleanly, while the template excels at custom operations.

### 14.1. Same Database Does Not Mean Same Transaction

Reactive repositories and `ReactiveMongoTemplate` can share the same infrastructure. However, multi-document transactions require registering `ReactiveMongoTransactionManager`/`TransactionalOperator` and keeping the reactive flow within the same Reactor context. Calling two methods in one service does not make them transactional.

## 15. Spring Boot Auto-Config: When Not to Extend Configuration Classes Manually

Typical Spring Boot setup:

~~~text
spring-boot-starter-data-mongodb-reactive
  + spring.data.mongodb.uri
  + @SpringBootApplication package scan
  + interface extends ReactiveMongoRepository

=> Boot can typically provide the reactive MongoClient,
   ReactiveMongoTemplate, and repository proxies.
~~~

In this case, adding a manual `ReactiveMongoConfig extends AbstractReactiveMongoConfiguration` often only adds complexity. Manual config makes more sense when:

- Not using Spring Boot.
- Deep customization of mapping/converters/templates is required.
- Multiple templates or repositories target separate databases.
- Explicit control over base packages and bean references is needed.
- Incrementally migrating from a legacy client to the reactive driver.

### 15.1. Distinguishing Configuration Properties

| Setting | Who Reads It? |
|---|---|
`spring.data.mongodb.uri` | Spring Boot auto-configuration |
`app.mongodb.uri` | `ReactiveMongoConfig` in this lesson, via `@Value` |
`app.mongodb.database` | `getDatabaseName()` in manual configuration |
`@EnableReactiveMongoRepositories` | Spring Data repository infrastructure |
`@Document(collection = "...")` | Spring Data mapping |
`@Field("stock_qty")` | MongoDB mapping converter |

If using **Option B / manual** while only setting `spring.data.mongodb.uri` in YAML without `app.mongodb.uri`, the sample constructor will fail with a missing property error. Do not blame the MongoDB server when the root cause is a **property name mismatch**.

### 15.2. Avoid Duplicate Client/Template Beans

When combining custom configuration with Boot:

1. Check which auto-configuration conditions match or back off.
2. List reactive `MongoClient`, `ReactiveMongoDatabaseFactory`, and `ReactiveMongoTemplate` beans.
3. If beans share names, check bean overriding policies (Boot generally discourages silent overrides).
4. Pick one configuration path and verify repositories receive the right template.
5. Test real queries against the **intended database**, rather than trusting context startup alone.

Do not use `@Primary` as a blanket fix for bean conflicts: it only controls injection preference, not duplicate repository scanning or resources pointing to the wrong database.

### 15.3. Auto Index Creation Does Not Manage Full Index Lifecycle

`@Indexed`/`@CompoundIndex` on an entity do not guarantee indexes exist on MongoDB. In modern Spring Data MongoDB, auto-index-creation is typically disabled by default; applications should use an explicit migration or index-provisioning workflow.

In particular, a reactive repository does not become “fast” simply by being reactive. Queries still need indexes tailored to equality, range, sorting, and tenant filters.

## 16. Multiple Databases, Multiple ReactiveMongoTemplates, and Repository Scanning

In larger systems, you may have:

~~~text
Catalog repositories   -> catalogReactiveMongoTemplate  -> catalogdb
Reporting repositories -> reportReactiveMongoTemplate   -> reportdb
~~~

If both are reactive repositories, configure separate scan packages and template references. `@EnableReactiveMongoRepositories` accepts `reactiveMongoTemplateRef` to select a specific template bean.

Conceptual example for a separate reporting configuration:

~~~java
@Configuration
@EnableReactiveMongoRepositories(
        basePackageClasses = ReportingRepository.class,
        reactiveMongoTemplateRef = "reportReactiveMongoTemplate")
public class ReportRepositoryConfig {
    // Register reportReactiveMongoTemplate along with its corresponding
    // ReactiveMongoDatabaseFactory in dedicated config.
}
~~~

This is an **architectural fragment** requiring `ReportingRepository` and the `reportReactiveMongoTemplate` bean to exist in your project. Do not copy it verbatim expecting it to compile without the reporting domain.

### 16.1. Two Common Mistakes

- Both `@EnableReactiveMongoRepositories` annotations scan the same package → repository beans get duplicated or wired to the wrong template.
- Repository A gets wired to database B's template → queries silently return empty or read from the wrong database while the app starts cleanly.

Keep repositories in stable packages like `com.example.catalog.repository` and `com.example.reporting.repository`, and use `basePackageClasses` for refactor safety.

### 16.2. Do Not Assume Two Databases Share a Reactive Transaction

`ReactiveMongoTransactionManager` manages resources and sessions for the single factory it wraps. Two clients/factories pointing to separate MongoDB deployments do not form a distributed transaction just because Spring manages both.

When a business flow spans multiple databases or services, design explicit transaction boundaries, outbox, saga, or compensating actions; never slap `@Transactional` on the method expecting everything to roll back together.

## 17. ReactiveMongoTransactionManager: Related, Not Automatic

`AbstractReactiveMongoConfiguration` and `@EnableReactiveMongoRepositories` **only configure reactive data access**; they do not turn repository calls into multi-document transactions.

When business logic genuinely needs multi-document transactions, register:

**ReactiveMongoTransactionConfig.java**

~~~java
package com.example.catalog;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;

@Configuration
public class ReactiveMongoTransactionConfig {

    @Bean("reactiveMongoTransactionManager")
    public ReactiveMongoTransactionManager reactiveMongoTransactionManager(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }
}
~~~

MongoDB requires a **replica set or another transaction-capable topology**, matching session/driver/factory setup, compatible server version, and proper privileges. A standalone MongoDB without full multi-document transaction support does not become transaction-capable just by registering this bean.

### 17.1. TransactionalOperator Uses Reactor Context

For reactive flows, Spring uses **Reactor Context** rather than the thread-local context used by imperative transaction managers. Example:

~~~java
import org.springframework.transaction.reactive.TransactionalOperator;

TransactionalOperator tx =
        TransactionalOperator.create(reactiveMongoTransactionManager);

Mono<Void> businessFlow = debitReactive()
        .then(creditReactive())
        .as(tx::transactional);
~~~

In this fragment, `debitReactive()` and `creditReactive()` return Publishers backed by the same reactive MongoDB factory with proper error handling. `reactiveMongoTransactionManager` is an injected bean. This is not a production-ready funds-transfer implementation.

### 17.2. Creating a Mono Without Subscribing Also Does Not Run the Transaction

~~~java
Mono<Void> flow = performReactiveWrites()
        .as(tx::transactional);

// No subscriber yet: no write or commit happens by default.
~~~

In WebFlux, the framework subscribes to the Publisher returned by the handler. In tests, `StepVerifier` subscribes. If code invokes a method returning `Mono<Void>` and discards the result, never assume database writes completed.

### 17.3. Imperative vs Reactive @Transactional

| Access Path | Appropriate Manager | Context |
|---|---|---|
`MongoTemplate` + `MongoRepository` | `MongoTransactionManager` | Imperative / thread-bound |
`ReactiveMongoTemplate` + `ReactiveMongoRepository` | `ReactiveMongoTransactionManager` | Reactive / Reactor Context |

Do not wrap a `Mono` with `MongoTransactionManager` expecting the reactive driver to share an imperative session. If an application uses both stacks, specify the matching manager and test rollback.

## 18. Indexes, Result Limits, and Backpressure

Reactive Streams allows a subscriber to request elements according to **demand**. The reactive MongoDB driver can fetch results in cursor batches on demand rather than eagerly loading everything at once. However, this **does not replace indexes, pagination, or server-side limits**.

### 18.1. Index for Tenant + SKU Queries

If each tenant has unique SKUs:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, sku: 1 },
  {
    name: "uq_product_tenant_sku",
    unique: true
  }
);
~~~

A unique compound index protects the business key under concurrent inserts. Calling `existsByTenantIdAndSku` then `save` **does not replace a unique index**.

### 18.2. Index for Sorting Newest ACTIVE Items

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, status: 1, createdAt: -1, _id: 1 },
  { name: "idx_product_tenant_status_created_id" }
);
~~~

This is a candidate index for tenant/status queries sorted by `createdAt DESC, _id ASC`. Do not index every field blindly; verify with `explain("executionStats")` and metrics against real workloads.

### 18.3. Reactive Index Operations Are Also Publishers

In reactive Spring Data:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.index.Index;
import reactor.core.publisher.Mono;

Index index = new Index()
        .on("tenantId", Sort.Direction.ASC)
        .on("sku", Sort.Direction.ASC)
        .unique()
        .named("uq_product_tenant_sku");

Mono<String> indexCreation =
        template.indexOps(CatalogProduct.class)
                .ensureIndex(index);
~~~

`indexCreation` is a publisher that must be **executed inside an intentional migration or provisioning lifecycle**. Creating the `Mono<String>` without subscribing/awaiting it in an orchestrator **does not ensure the index was created**.

Never block on the event loop to build indexes per request. Index provisioning belongs in managed deployment or test setup with conflict and permission checks.

### 18.4. Backpressure Cannot Rescue an Unindexed Query

If the server must scan the entire collection to find a handful of documents, a reactive consumer requesting 20 items does not eliminate server scan work. And calling `collectList()` over millions of documents can still exhaust memory. Control steps:

1. Include tenant filters and business predicates in the MongoDB query.
2. Provide indexes aligned with filters and sorting.
3. Apply `limit`, paging/cursors, or server-side batching.
4. Project only needed fields.
5. Enforce timeouts, metrics, and workload bounds matching the API contract.

### 18.5. flatMap Concurrency Is Not a Transaction

~~~java
return Flux.fromIterable(commands)
        .flatMap(command -> applyOneCommand(command), 8);
~~~

This fragment bounds operator concurrency, but **does not make the 8 commands atomic**. If commands touch the same document, use CAS/uniqueness/idempotency; if ordering matters, `concatMap` or a queue design may be needed. Never use `parallel()` to “speed up every update” without measuring contention and database capacity.

## 19. Monitoring and Diagnosing Reactive Access

Diagnosing reactive issues typically requires inspecting multiple layers:

| Symptom | What to Check |
|---|---|
Spring context fails to create repository | Package scanning, `@EnableReactiveMongoRepositories`, repository interface |
Cannot inject `ReactiveMongoTemplate` | Client/factory/template beans, auto-config conditions |
Publisher returns empty | Query filters, tenant, collection/database name, BSON mapping |
Publisher errors on subscribe | URI, authentication, network, schema, server timeout |
HTTP request hangs | Missing subscription in custom flow, blocked event loop, DB latency |
CPU spikes | Missing indexes, heavy aggregation, expensive Java processing |
Connection pool exhaustion | Multiple clients created, excessive concurrency, unclosed resources |
Timeouts only on large data | Cursor/batch size, indexes, sorting, memory, read concern |
Duplicate writes after retry | Cold Publisher resubscribed, missing idempotency, driver/app retries |
Reactive transaction fails to roll back | Wrong manager type, mismatched Reactor Context/session, topology |

### 19.1. Inspecting on MongoDB

~~~javascript
db.catalog_products.find({
  tenantId: "tenant-a",
  status: "ACTIVE"
})
.sort({ createdAt: -1, _id: 1 })
.limit(20)
.explain("executionStats");
~~~

Watch `totalKeysExamined`, `totalDocsExamined`, blocking `SORT` stages, `nReturned`, and latency. A reactive Publisher backed by an I/O-heavy `COLLSCAN` query can still bottleneck the system.

### 19.2. Logging Must Respect Privacy

The MongoDB Driver `CommandListener` helps inspect actual commands, but BSON queries may contain tenants, SKUs, coordinates, or sensitive data. Log selectively in integration tests and avoid dumping raw query payloads to production logs by default.

### 19.3. Never Mask Database Errors with Blanket onErrorResume

Wrong:

~~~java
return repository.findByTenantIdAndSku(tenantId, sku)
        .onErrorResume(anyError -> Mono.empty());
~~~

This turns timeouts or auth failures into “product not found.” Callers cannot tell infrastructure outages apart from genuine empty results. Handle **specific exception types**, emit logs/metrics, and preserve API semantics.

## 20. Testing Configuration: Context Must Wire the Right Beans

With manual configuration, write integration tests verifying that:

- The Spring context creates `com.mongodb.reactivestreams.client.MongoClient`.
- `ReactiveMongoTemplate` can be injected.
- `@EnableReactiveMongoRepositories` discovers `CatalogProductRepository`.
- Repository proxies target the right database, collection, and converters.
- Subscribing to a Publisher actually reads and writes.

**Do not just verify that `@Configuration` exists in source.** Having the annotation does not prove the URI is right, the right beans were picked, repositories were scanned, or the MongoDB server works.

### 20.1. Test Environment

Examples require a dedicated test MongoDB instance, such as Testcontainers or an isolated local test MongoDB:

~~~yaml
# Test-only configuration; never point at real data.
app:
  mongodb:
    uri: "mongodb://localhost:27017"
    database: "catalog_reactive_test"
~~~

Do not assume `@SpringJUnitConfig` or `@DataMongoTest` starts `mongod` automatically. This lesson uses `@SpringJUnitConfig` to highlight manual infrastructure with `@TestPropertySource` overrides; the test MongoDB must already be running or managed by Testcontainers.

**Note:** tests wipe collection data in `catalog_reactive_test` to seed fixtures. Never point this URI at a shared or production database.

### 20.2. Testing Context + Reactive Bean Wiring

**ReactiveMongoWiringIntegrationTest.java**

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.reactivestreams.client.MongoClient;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = {
        ReactiveMongoConfig.class,
        CatalogQueryService.class,
        CatalogTemplateQueryService.class,
        CatalogStockService.class
})
@TestPropertySource(properties = {
        "app.mongodb.uri=mongodb://localhost:27017",
        "app.mongodb.database=catalog_reactive_test"
})
class ReactiveMongoWiringIntegrationTest {

    @Autowired MongoClient reactiveClient;
    @Autowired ReactiveMongoTemplate template;
    @Autowired CatalogProductRepository repository;
    @Autowired CatalogQueryService queryService;
    @Autowired CatalogStockService stockService;

    @Test
    void allReactiveBeansAreAvailable() {
        assertThat(reactiveClient).isNotNull();
        assertThat(template).isNotNull();
        assertThat(repository).isNotNull();
        assertThat(queryService).isNotNull();
        assertThat(stockService).isNotNull();
    }
}
~~~

This test proves **Spring bean wiring** only; because it never subscribes to a MongoDB operation, it **does not prove the server can actually be queried**. The next step uses `StepVerifier` against a real test MongoDB.

## 21. Testing Repositories, Templates, and Concurrency with StepVerifier

`StepVerifier` from `reactor-test` subscribes to a Publisher and observes `onNext`, `onComplete`, and `onError`. This lets you test reactive flows without scattering `block()` inside application services.

### 21.1. Integration Test Suite Against Real MongoDB

**CatalogReactiveIntegrationTest.java**

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.reactivestreams.client.MongoClient;
import java.time.Instant;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@SpringJUnitConfig(classes = {
        ReactiveMongoConfig.class,
        CatalogQueryService.class,
        CatalogTemplateQueryService.class,
        CatalogStockService.class
})
@TestPropertySource(properties = {
        "app.mongodb.uri=mongodb://localhost:27017",
        "app.mongodb.database=catalog_reactive_test"
})
class CatalogReactiveIntegrationTest {

    @Autowired CatalogProductRepository repository;
    @Autowired CatalogQueryService queryService;
    @Autowired CatalogTemplateQueryService templateService;
    @Autowired CatalogStockService stockService;
    @Autowired ReactiveMongoTemplate template;
    @Autowired MongoClient reactiveClient;

    private CatalogProduct product(
            String id,
            String tenant,
            String sku,
            String status,
            long stock,
            String createdAt) {
        return new CatalogProduct(
                id,
                tenant,
                sku,
                "Product " + id,
                status,
                stock,
                Instant.parse(createdAt));
    }

    @BeforeEach
    void cleanCollection() {
        // Isolated test database only.
        StepVerifier.create(repository.deleteAll())
                .verifyComplete();
    }

    @Test
    void reactiveRepositoryWasScannedAndCanQuery() {
        CatalogProduct source = product(
                "p-101", "tenant-a", "BOTTLE-500", "ACTIVE", 12,
                "2026-11-20T08:00:00Z");

        StepVerifier.create(
                repository.save(source)
                        .then(queryService.findBySku(
                                "tenant-a", "BOTTLE-500")))
                .assertNext(saved -> {
                    assertThat(saved.id()).isEqualTo("p-101");
                    assertThat(saved.stockQty()).isEqualTo(12L);
                    assertThat(saved.tenantId()).isEqualTo("tenant-a");
                })
                .verifyComplete();
    }

    @Test
    void notFoundIsReportedAsDomainError() {
        StepVerifier.create(
                queryService.findBySku("tenant-a", "MISSING"))
                .expectError(CatalogProductNotFoundException.class)
                .verify();
    }

    @Test
    void querySortAndTenantIsolationAreCorrect() {
        List<CatalogProduct> fixtures = List.of(
                product("p-101", "tenant-a", "SKU-1", "ACTIVE", 12,
                        "2026-11-20T08:00:00Z"),
                product("p-102", "tenant-a", "SKU-2", "ACTIVE", 9,
                        "2026-11-20T09:00:00Z"),
                product("p-103", "tenant-a", "SKU-3", "DRAFT", 1,
                        "2026-11-20T10:00:00Z"),
                product("p-201", "tenant-b", "SKU-4", "ACTIVE", 7,
                        "2026-11-20T11:00:00Z")
        );

        StepVerifier.create(
                repository.saveAll(fixtures)
                        .thenMany(templateService.newestActive(
                                "tenant-a", 10))
                        .map(CatalogProduct::id))
                .expectNext("p-102", "p-101")
                .verifyComplete();
    }

    @Test
    void concurrentConditionalUpdatesDoNotOversell() {
        CatalogProduct source = product(
                "p-101", "tenant-a", "BOTTLE-500", "ACTIVE", 5,
                "2026-11-20T08:00:00Z");

        StepVerifier.create(
                repository.save(source)
                        .then(Mono.zip(
                                stockService.reserve(
                                        "tenant-a", "p-101", 3),
                                stockService.reserve(
                                        "tenant-a", "p-101", 3)))
                        .flatMap(pair -> repository.findById("p-101")
                                .map(saved -> new ReservationOutcome(
                                        pair.getT1(),
                                        pair.getT2(),
                                        saved.stockQty()))))
                .assertNext(result -> {
                    // Do not assume which request wins.
                    assertThat(result.first() ^ result.second()).isTrue();
                    assertThat(result.stock()).isEqualTo(2L);
                })
                .verifyComplete();
    }

    @Test
    void fieldAnnotationIsAppliedToBson() {
        CatalogProduct source = product(
                "p-101", "tenant-a", "BOTTLE-500", "ACTIVE", 12,
                "2026-11-20T08:00:00Z");

        Mono<Document> rawById = Mono.from(
                reactiveClient.getDatabase("catalog_reactive_test")
                        .getCollection("catalog_products")
                        .find(new Document("_id", "p-101"))
                        .first());

        StepVerifier.create(
                repository.save(source).then(rawById))
                .assertNext(raw -> {
                    assertThat(raw.containsKey("stock_qty")).isTrue();
                    assertThat(raw.containsKey("stockQty")).isFalse();
                    assertThat(raw.get("stock_qty"))
                            .isInstanceOf(Number.class);
                    assertThat(((Number) raw.get("stock_qty"))
                            .longValue()).isEqualTo(12L);
                })
                .verifyComplete();
    }

    private record ReservationOutcome(
            boolean first, boolean second, long stock) {
    }
}
~~~

### 21.2. What Do These StepVerifier Tests Prove?

- `repository.save(...)`/`findBy...` actually hit MongoDB when subscribed.
- `@EnableReactiveMongoRepositories` registered the right repository proxy.
- `ReactiveMongoTemplate` applied tenant filtering and sorting accurately.
- Two competing conditional updates on stock=5, each deducting 3: **exactly one matches** and final stock is 2.
- `@Field("stock_qty")` produces the physical BSON key, verified via a raw driver read.
- `Mono.empty` translates into the domain exception per contract.

### 21.3. What Do These Tests Not Yet Prove?

A handful of documents on local MongoDB cannot prove:

- Queries are index-optimized; the server may choose a collection scan on tiny datasets.
- Idempotency guarantees under retries after timeouts.
- Throughput under high load or backpressure/cursor behavior across millions of documents.
- Multi-document reactive transaction rollback; requires a replica set and `ReactiveMongoTransactionManager`.
- HTTP-layer authorization correctness: service tests pass the tenant directly as an argument.

For multi-tenant APIs, add security integration tests verifying that a principal only resolves authorized tenants, never a client-forged tenant.

### 21.4. Do Not Run This Test Against a Shared Database

`repository.deleteAll()` in `@BeforeEach` wipes all documents in the test collection. If parallel test runs share the same database, races and flaky tests occur. Use dedicated databases, isolated collections, or proper isolation; never point tests at production.

### 21.5. Using Testcontainers

With a Testcontainers MongoDB container:

1. Start a MongoDB container of the target version.
2. Read the dynamic connection string provided by the container.
3. Register `app.mongodb.uri` before Spring creates `ReactiveMongoConfig`, e.g., via `@DynamicPropertySource`.
4. Keep the test database isolated.
5. Let Testcontainers manage container lifecycle and cleanup after tests.

Never hardcode `localhost:27017` when the test MongoDB runs on a randomized port. This lesson shows a static URI purely for simplicity with a pre-started local MongoDB.

## 22. Common Configuration and Usage Mistakes

| Mistake / Symptom | Why It Happens | Fix |
|---|---|---|
Extending `AbstractReactiveMongoConfiguration` but returning sync `MongoClient` | Driver type mismatches reactive infrastructure | Import `com.mongodb.reactivestreams.client.MongoClient` |
Adding only `@EnableReactiveMongoRepositories` expecting MongoDB to start | Annotation only enables repository scanning | Configure client/factory/template and MongoDB server |
Repository bean not found | Package outside scan scope | Set `basePackageClasses` to the right package |
Using `@EnableMongoRepositories` for reactive interfaces | Imperative vs reactive repository infrastructure | Use `@EnableReactiveMongoRepositories` |
Service fails injection | Repository scanned, but `@Service` outside component scan | Fix component scan or bean imports |
Missing `ReactiveMongoTemplate` | Missing starter, factory/client, or auto-config backed off | Inspect context and configuration |
Missing `app.mongodb.uri` with manual config | Confusing Boot properties with custom properties | Supply properties matching `@Value` |
Duplicate client/template/repository beans | Combining manual config and Boot scan carelessly | Pick one strategy; check auto-config conditions |
Instantiating `MongoClient` with `new` per request | Multiplies pools and resources | Use a Spring-managed singleton bean |
Calling a `Mono` method and discarding the return value | No subscriber, so operation never runs | Return the Publisher or subscribe at a clear boundary |
Calling `subscribe()` inside a service | Detaches errors/transactions/cancellation from caller | Compose `Mono`/`Flux` and return it |
Calling `block()` in a WebFlux handler | Blocks the event loop, increases latency or throws | Use `flatMap`/`map`/`then` |
Treating `Mono.empty` as null | Error/404 logic fails to trigger as expected | Use `switchIfEmpty` per contract |
`onErrorResume` turning all errors into empty | Masks network/auth errors as “no data” | Classify exceptions and preserve semantics |
Calling inherited `findAll()` in a tenant API | Leaks cross-tenant data | Query only within the authorized tenant |
Using BSON names in typed derived methods | Property resolution fails | Derived methods use Java property names |
Using Java property names in raw BSON | Not auto-mapped in raw aggregation stages | Use real BSON field names; verify commands |
Reading from an unexpected database | Wrong URI, `getDatabaseName()`, or template reference | Assert database/collection in integration tests |
Collecting a whole `Flux` via `collectList()` | Accumulates too many documents in heap | Filter/limit/project/paginate on the server |
Sorting by `createdAt` with no tie-breaker | Unstable pagination | Add `id`, and include all keys in cursors |
Assuming reactive protects concurrent writes automatically | Lost updates or overselling | Use CAS/filters and atomic updates |
Retrying `$inc` without a command ID | Duplicate writes on ambiguous outcomes | Add idempotency and reconciliation |
Confusing `MongoTransactionManager` with reactive manager | Fails to share reactive session context | Use `ReactiveMongoTransactionManager` |
Running reactive transactions on standalone MongoDB | Server lacks multi-document transaction support | Use a test replica set or compatible topology |
Only unit-testing with a mocked Mongo client | Does not verify mapping or server behavior | Write integration tests + `StepVerifier` |
Running `deleteAll()` on a shared database | Wipes other data unexpectedly | Use isolated test databases |
Assuming queries run just because beans instantiate | Publisher unsubscribed or URI invalid | Test subscribing and assert MongoDB state |

### 22.1. Startup Diagnostic Checklist

When the app fails with `NoSuchBeanDefinitionException` or `BeanCreationException` around reactive MongoDB:

1. Is `spring-boot-starter-data-mongodb-reactive` or compatible dependencies present?
2. Does the `MongoClient` import come from the reactive streams package?
3. Is `ReactiveMongoConfig` scanned or imported by Spring?
4. Does `getDatabaseName()` match an existing DB with sufficient permissions?
5. Does `@EnableReactiveMongoRepositories` scan the right repository package?
6. Does the repository interface extend `ReactiveMongoRepository`?
7. If multiple template beans exist, does `reactiveMongoTemplateRef` select the intended one?
8. Is Boot auto-configuration disabled, overridden, or conflicting with custom config?
9. On subscription, is the error a MongoDB network/auth/schema failure or bean wiring?
10. Does an integration test on an isolated DB read and write successfully?

Distinguish **context startup errors** from **runtime subscription errors**. Publishers may assemble cleanly while connection or auth failures only surface when the operation actually subscribes.

## 23. Practice Exercises

**Exercise 1 — Boot Auto-Config.** Create a Spring Boot app with `spring-boot-starter-data-mongodb-reactive`, `spring.data.mongodb.uri`, and `@SpringBootApplication`. Create a `ReactiveMongoRepository` and write a test verifying queries run on subscription. Record which beans auto-configuration created.

**Exercise 2 — Manual Config.** Replace auto-config with `ReactiveMongoConfig extends AbstractReactiveMongoConfiguration` reading URI and database name from properties. Verify `reactiveMongoClient()` uses the reactive driver package.

**Exercise 3 — Repository Scanning.** Move the repository to a different package than the config class. Observe the missing-scan failure, then fix it with `@EnableReactiveMongoRepositories(basePackageClasses = ...)`.

**Exercise 4 — Base Packages vs templateRef.** Create two repository groups (e.g., catalog and reporting) with separate templates targeting two test databases. Set `reactiveMongoTemplateRef` and prove neither queries the wrong database.

**Exercise 5 — Mono and Empty.** Write `findByTenantIdAndSku` returning `Mono<CatalogProduct>`; for missing SKUs, use `switchIfEmpty` to emit a domain exception. Verify with `StepVerifier.expectError`.

**Exercise 6 — Flux and Sorting.** List ACTIVE products for a tenant sorted `createdAt DESC, id ASC`. Use `ReactiveMongoTemplate` with `limit=20` and inspect the candidate index with `explain`.

**Exercise 7 — Java → BSON Mapping.** Put `@Field("stock_qty")` on `stockQty`. Save an entity with the reactive repository, read it back via the native reactive driver, and verify BSON contains only `stock_qty`.

**Exercise 8 — No Blocking.** Refactor a service calling `.block()` into a chain of `map`/`flatMap`/`then`. Explain why subscription belongs to the WebFlux framework or an explicit orchestrator boundary.

**Exercise 9 — No Fire-and-Forget Subscribe.** Write a bad example calling `repository.save(...).subscribe()` in a service and returning `Mono.empty()`. Fix it to return a Publisher the caller can await, cancel, and handle errors on.

**Exercise 10 — Conditional Update.** Seed stock=5 and run two concurrent reactive `reserve(..., 3)` calls. Assert exactly one returns `true` and final stock is 2. Explain why reading stock followed by `flatMap` cannot replace a conditional update.

**Exercise 11 — Error Handling.** Simulate an unreachable MongoDB. Compare `switchIfEmpty` and `onErrorResume`; ensure timeouts or auth failures are never turned into 404s.

**Exercise 12 — Bounded Results.** Seed tens of thousands of products. Compare an indexed query with `Query.limit(20)` against unbounded `collectList()`. Measure memory, latency, and docs examined.

**Exercise 13 — Reactive Transactions.** On a test MongoDB replica set, configure `ReactiveMongoTransactionManager` and wrap two writes with `TransactionalOperator`. Force an error on the second write and verify the first write rolls back.

**Exercise 14 — Tenant Security.** Have a `tenant-a` principal request a SKU owned by `tenant-b`. Verify the service leaks nothing and every query includes the tenant filter from the auth context.

**Exercise 15 — Testcontainers.** Replace local `localhost:27017` in tests with Testcontainers and `@DynamicPropertySource`. Verify client lifecycle and isolated test databases across suites.

**Exercise 16 — Performance.** Write a load test using `Flux.flatMap` with concurrency 1, 8, and 32 for independent queries. Measure throughput, p95, connection usage, and DB CPU; explain why unbounded concurrency can hurt performance.

## 24. Key Takeaways

**`AbstractReactiveMongoConfiguration`** explicitly configures the **MongoDB Reactive Streams client**, database factory, converters, and `ReactiveMongoTemplate` when manual configuration is needed. The two key overrides are `reactiveMongoClient()` and `getDatabaseName()`; the client must come from `com.mongodb.reactivestreams.client`, be a Spring-managed bean with proper lifecycle, and point to the right database.

**`@EnableReactiveMongoRepositories`** activates **repository scanning and proxies** for interfaces extending `ReactiveMongoRepository`. Use `basePackageClasses`/`basePackages` to scope scans accurately, and `reactiveMongoTemplateRef` when using multiple templates. This annotation **does not start MongoDB, enforce tenant permissions, or open transactions**.

In **Spring Boot**, evaluate **auto-configuration** before building manual infrastructure: the starter plus `spring.data.mongodb.uri` may already provide all required beans. Avoid accidentally mixing manual config with Boot auto-config.

Finally, **`Mono`/`Flux` are publishers that require subscription**: return and compose reactive pipelines instead of calling `block()` or `subscribe()` carelessly. Optimize with server-side filters, indexes, and limits, guard concurrent writes with conditional updates/idempotency, use `ReactiveMongoTransactionManager` for reactive transactions, and **verify both bean wiring and real behavior with `StepVerifier` against an isolated test MongoDB**.
