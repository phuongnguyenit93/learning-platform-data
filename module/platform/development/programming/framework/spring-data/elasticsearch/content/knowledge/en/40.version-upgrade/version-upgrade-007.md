# Upgrading Reactive Clients, Auditing, and Callbacks

When upgrading Spring Data Elasticsearch, changes extend beyond dependencies or client initialization. An application on a reactive stack must also verify the client type, reactive operations, repository configuration, callback lifecycle, and how the current auditor is resolved. If you only convert query code to reactive while leaving auditing or callbacks synchronous, metadata may not be written, callbacks may never fire, or requests may block unexpectedly.

Perform the upgrade across three layers:

1. **Client and API:** choose the right Spring Data Elasticsearch version, Elasticsearch server/client libraries, and imperative/reactive configuration.
2. **Auditing:** enable the appropriate auditing infrastructure, distinguish new vs. existing entities, and retrieve the principal from the reactive context.
3. **Entity callbacks:** migrate callbacks to reactive interfaces, ensure callbacks return a `Publisher`, preserve ordering, and avoid blocking work.

## 1. Understanding components in the reactive stack

Spring Data Elasticsearch provides abstractions so applications do not have to call HTTP clients directly for every operation.

~~~text
Reactive application
       |
       v
Reactive repository / service
       |
       v
ReactiveElasticsearchOperations
       |
       v
ReactiveElasticsearchClient
       |
       v
Elasticsearch client transport
       |
       v
Elasticsearch cluster
~~~

Each component has a distinct role:

| Component | Role |
| --- | --- |
| `ReactiveElasticsearchClient` | Low-level reactive client used to send requests to Elasticsearch |
| `ReactiveElasticsearchOperations` | High-level template API for save, search, delete, and index operations |
| `ReactiveElasticsearchRepository` | Repository abstraction returning `Mono`/`Flux` |
| `ReactiveElasticsearchAuditing` | Records creation/modification metadata along the reactive lifecycle |
| `ReactiveAuditorAware` | Supplies the current principal as a `Mono` |
| Reactive `EntityCallback` | Reactive hooks before/after entity processing steps |

Applications should usually use `ReactiveElasticsearchOperations` or `ReactiveElasticsearchRepository`. Use the low-level client only when an Elasticsearch API is not exposed by Spring Data abstractions.

### 1.1. Reactive is more than changing return types

A method returning `Mono` or `Flux` does not automatically make the whole pipeline non-blocking. Internal operations must also follow reactive execution:

- Do not call `block()` in services or callbacks.
- Do not use `ThreadLocal` to read a reactive request's security context.
- Do not perform blocking I/O directly inside callbacks.
- Do not create a `Publisher` and discard it, as a `Publisher` typically runs only when subscribed.
- Do not run side effects at assembly time if they must occur per subscription.
- Account for backpressure, concurrency, and timeouts when processing multiple documents.

Example:

~~~java
public Mono<Product> save(Product product) {
    return operations.save(product);
}
~~~

This is a reactive pipeline. The Elasticsearch operation executes only when the `Publisher` is subscribed to by WebFlux, a consumer, or another reactive component.

## 2. Mapping compatibility before upgrading

Before modifying code, determine precisely:

- Spring Boot version.
- Spring Data Elasticsearch version selected by dependency management.
- Spring Data Commons version.
- Elasticsearch server version.
- Elasticsearch Java API Client or `RestClient` version.
- Java runtime.
- Imperative vs. reactive client configuration.
- Legacy packages currently imported.

Do not upgrade an Elasticsearch client dependency independently to the latest version if the Spring Data release train does not yet support it. Spring Boot dependency management generally selects a verified compatible set of versions.

### 2.1. Inspecting the dependency tree

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-elasticsearch
mvn dependency:tree -Dincludes=co.elastic.clients
mvn dependency:tree -Dincludes=org.elasticsearch.client
~~~

Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-data-elasticsearch
./gradlew dependencyInsight --dependency elasticsearch-java
./gradlew dependencyInsight --dependency elasticsearch-rest-client
~~~

The goal is knowing which dependencies actually resolve, not just what is declared in the build file.

### 2.2. Do not mix client generations

During transitions, several clients may exist:

- Legacy `RestHighLevelClient`.
- `RestClient` from the Elasticsearch 7/8 client stack.
- Elasticsearch Java API Client.
- `Rest5Client` in the Elasticsearch 9 client stack.
- `ReactiveElasticsearchClient` provided by Spring Data.

These are not interchangeable merely by renaming beans. Spring Data configuration, transport, request/response classes, and converters must belong to the same client generation.

### 2.3. Common upgrade milestones

| Upgrade | Changes to Watch |
| --- | --- |
| Spring Data Elasticsearch 4.4 to 5.0 | New client based on Elasticsearch Java API Client; packages using `RestHighLevelClient` deprecated; `NativeSearchQuery` replaced by `NativeQuery` |
| 5.x | Reactive stack has `ReactiveElasticsearchConfiguration` and `ReactiveElasticsearchClient`; verify APIs/clients per minor version |
| 5.5 to 6.0 | Uses Elasticsearch 9 libraries and `Rest5Client` as default; legacy `RestClient` moved to legacy package and deprecated |
| 6.x | Uses default `Rest5Client` configuration; retaining legacy `RestClient` requires the supported legacy configuration for that version |

These milestones help locate breaking changes. Use the migration guide matching your exact source and target versions; do not assume a change in 6.0 applies identically across every subsequent minor release.

## 3. Upgrading reactive clients from RestHighLevelClient

Spring Data Elasticsearch 5.0 cleanly separated legacy-client code from Elasticsearch Java API Client code. Classes depending on `RestHighLevelClient` moved into the `erhlc` package and were deprecated. The legacy reactive implementation also moved there because it contained code built on the old Elasticsearch libraries.

If the application still has imports from:

~~~java
org.springframework.data.elasticsearch.client.erhlc
~~~

identify each class in use and replace it with the corresponding new API. Do not rename packages in bulk without checking constructors, request models, and response models.

### 3.1. Reactive configuration with the new client generation

The reactive stack uses its own configuration base class:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ReactiveElasticsearchConfiguration;

@Configuration
public class ReactiveSearchConfiguration
        extends ReactiveElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
            .connectedTo("localhost:9200")
            .build();
    }
}
~~~

With this configuration, Spring Data registers the required reactive beans, including `ReactiveElasticsearchClient` and `ReactiveElasticsearchOperations`. Default bean names and configuration details depend on the version.

Do not use `ElasticsearchConfiguration` for reactive repositories if the application needs `ReactiveElasticsearchOperations`. Imperative and reactive configurations are separate branches.

### 3.2. Configuring TLS, timeouts, and authentication

`ClientConfiguration` supports connection settings such as:

- One or more endpoints.
- SSL/TLS.
- Connect timeout.
- Socket timeout.
- Proxy.
- Path prefix.
- HTTP headers.
- Basic authentication.
- Client configuration callbacks.

Example configuration:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ReactiveElasticsearchConfiguration;

@Configuration
class ReactiveSearchConfiguration
        extends ReactiveElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
            .connectedTo("es.internal.example:9200")
            .usingSsl()
            .withConnectTimeout(Duration.ofSeconds(3))
            .withSocketTimeout(Duration.ofSeconds(10))
            .withBasicAuth(
                System.getenv("ES_USERNAME"),
                System.getenv("ES_PASSWORD")
            )
            .build();
    }
}
~~~

This is a configuration example. Certificate provisioning, trust material, credentials, and endpoints must match your deployment environment. Never hard-code secrets into source code or test fixtures.

### 3.3. Reactive header suppliers must not block

`ClientConfiguration` can accept a supplier that produces HTTP headers per request, useful when tokens rotate over time.

In a reactive setup, this supplier must return without performing blocking I/O. Do not call a synchronous token service or wait on a network response inside the supplier.

If you need to retrieve a token from a reactive security context, design authentication/header propagation according to the capabilities of your current client configuration. Do not read `ThreadLocal` inside the callback and assume it represents the active reactive request.

## 4. Notes when upgrading from Spring Data Elasticsearch 5.x to 6.x

Spring Data Elasticsearch 6.0 moves to Elasticsearch 9 libraries and `Rest5Client` as the default client. Legacy `RestClient` code may remain supported through a legacy configuration within the corresponding version's scope, though those APIs are deprecated.

Areas to review:

| Area | Change |
| --- | --- |
| Default client | `Rest5Client` |
| Legacy client configuration | Moved to legacy package and deprecated |
| Legacy client config callbacks | Moved from `ElasticsearchClients` to corresponding `rest_client` package |
| `UpdateQuery` | `ifSeqNo` and `ifPrimaryTerm` changed from `Integer` to `Long` |
| `ScriptType` | Removed; use `ScriptData` to describe scripts |
| Reactive client | Use `ReactiveElasticsearchConfiguration` aligned with the new client generation |

### 4.1. Checking UpdateQuery

Legacy code may use `Integer` for sequence numbers and primary terms:

~~~java
UpdateQuery.builder(id)
    .withIfSeqNo(seqNo)
    .withIfPrimaryTerm(primaryTerm)
    .build();
~~~

In the new API, corresponding values use `Long` to match the Elasticsearch client types:

~~~java
Long seqNo = response.seqNo();
Long primaryTerm = response.primaryTerm();

UpdateQuery update = UpdateQuery.builder(id)
    .withIfSeqNo(seqNo)
    .withIfPrimaryTerm(primaryTerm)
    .build();
~~~

Verify method names and return types against your active client version. Do not cast down to `Integer`, which risks data truncation or compile errors.

### 4.2. Replacing ScriptType with ScriptData

If legacy code distinguished inline vs. stored scripts via `ScriptType`, migrate to creating `ScriptData` per the new API.

Conceptual example:

~~~java
ScriptData scriptData = ScriptData.builder()
    .withScript("ctx._source.status = params.status")
    .withParams(Map.of("status", "ACTIVE"))
    .build();
~~~

This illustrates the concept; constructors/builder methods vary by version. Read the `ScriptData` Javadoc and migration guide before editing production scripts.

### 4.3. Client configuration callbacks

In 6.0, configuration callbacks for the legacy `RestClient` moved to the `rest_client` package. If the application customizes the low-level `RestClient`, do not retain imports from old packages when switching to `Rest5Client`.

Distinguish:

- Default `Rest5Client` configuration.
- Legacy `RestClient` configuration.
- `ReactiveElasticsearchConfiguration`.
- `ReactiveElasticsearchLegacyRestClientConfiguration` if a legacy client must be kept temporarily.

Do not mix configuration callbacks for legacy `RestClient` with `Rest5Client`.

## 5. Migrating query APIs and related packages

Upgrading clients often brings changes to query classes and imports.

### 5.1. NativeSearchQuery to NativeQuery

On the 4.4 to 5.0 path, legacy `NativeSearchQuery` was replaced by `NativeQuery` using the Elasticsearch Java API Client's `Query` model.

Example:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .match(m -> m
            .field("name")
            .query("wireless keyboard")
        )
    )
    .build();
~~~

If the application has large query factories, migrate each query family and inspect the resulting JSON DSL sent over the wire. Do not just fix imports and assume identical semantics.

### 5.2. Operations interface

Prefer depending on the interface:

~~~java
ReactiveElasticsearchOperations
~~~

rather than depending directly on the concrete template implementation unless specifically required.

This reduces coupling to client generations and lets Spring Data wire the appropriate implementation.

### 5.3. HttpHeaders package

Spring Data Elasticsearch 5.0 introduced its own `HttpHeaders` in package:

~~~java
org.springframework.data.elasticsearch.support.HttpHeaders
~~~

If legacy client configurations used `org.springframework.http.HttpHeaders`, update imports per the migration guide. You may need to copy headers via `addAll` instead of passing the old object directly.

### 5.4. Java records and accessors

Several data types in Spring Data Elasticsearch were converted to Java records. Code calling `getProp()` getters may need to switch to `prop()` accessors.

Do not mechanically rewrite every getter across the codebase. Change only the specific types converted to records in the migration guide for your version.

## 6. Using ReactiveElasticsearchOperations and repositories

`ReactiveElasticsearchOperations` provides APIs returning `Publisher` types like `Mono` and `Flux`. Example:

~~~java
import org.springframework.data.elasticsearch.core.ReactiveElasticsearchOperations;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class ProductService {

    private final ReactiveElasticsearchOperations operations;

    ProductService(ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }

    Mono<Product> save(Product product) {
        return operations.save(product);
    }
}
~~~

Reactive repository:

~~~java
public interface ProductRepository
        extends ReactiveElasticsearchRepository<Product, String> {

    Flux<Product> findByBrandId(String brandId);
}
~~~

Derived query method names must align with entity fields and mappings. Do not invoke a reactive repository by calling `block()` inside a WebFlux controller.

### 6.1. Reactive search

~~~java
Mono<List<SearchHit<Product>>> searchProducts(Query query) {
    return operations.search(query, Product.class)
        .collectList();
}
~~~

The exact return type of `search` methods depends on the overload and Spring Data version. You may receive `Flux<SearchHit<T>>`, `Flux<SearchHits<T>>`, or another API-defined type. Check the dependency's method signatures before applying.

### 6.2. Composing operations

~~~java
Mono<Product> createAndRead(Product product) {
    return operations.save(product)
        .flatMap(saved -> operations.get(saved.getId(), Product.class));
}
~~~

`flatMap` fits when the next step also returns a `Publisher`. `map` is for synchronous transformations that do not produce a new `Publisher`.

### 6.3. Do not subscribe manually in services

Avoid:

~~~java
public void save(Product product) {
    operations.save(product).subscribe();
}
~~~

This detaches the side effect from the request lifecycle, preventing callers from knowing when the write finishes or handling errors.

Return the `Publisher` to the caller instead:

~~~java
public Mono<Product> save(Product product) {
    return operations.save(product);
}
~~~

Callers at the web layer or message consumer decide subscription and acknowledgement.

## 7. Auditing in Spring Data Elasticsearch

Auditing automatically populates who created/updated a document and when it was created/updated.

Common annotations:

| Annotation | Meaning |
| --- | --- |
| `@CreatedDate` | Creation timestamp |
| `@LastModifiedDate` | Most recent update timestamp |
| `@CreatedBy` | Creating principal |
| `@LastModifiedBy` | Most recent updating principal |

Auditing is useful for:

- Tracking modification metadata.
- Displaying creator/editor info.
- Analyzing stale data.
- Supporting basic audit trails.
- Filtering data by timestamp or actor.

Auditing metadata on an entity does not create an immutable audit log. If the domain needs to retain every historical change, use an event log or a separate audit index.

## 8. Preparing an entity with audit fields

Example:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.DateFormat;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    private String name;

    @CreatedDate
    @Field(type = FieldType.Date, format = DateFormat.basic_date_time)
    private Instant createdDate;

    @LastModifiedDate
    @Field(type = FieldType.Date, format = DateFormat.basic_date_time)
    private Instant lastModifiedDate;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String lastModifiedBy;

    // Constructors, getters and setters
}
~~~

You can use date fields alone if the application does not need to store principals. When using `CreatedBy` or `LastModifiedBy`, provide a compatible `AuditorAware` or `ReactiveAuditorAware`.

### 8.1. Time data types

Auditing supports JDK date/time types, `long`/`Long`, and legacy `Date`/`Calendar` types per the Spring Data auditing infrastructure.

`Instant` is usually well suited for absolute points in time:

- Independent of local timezones.
- Easy to exchange across services.
- Serializes cleanly in ISO-8601.
- Suitable for event times and audit times.

Elasticsearch mappings must be declared accordingly. If using a custom format, ensure converters, mappings, and legacy data are consistent.

### 8.2. CreatedDate alone does not prove an entity is new

In Elasticsearch, an entity having an ID does not necessarily mean it already exists. An application can assign IDs before inserting. Therefore, checking only whether the ID is `null` does not always distinguish new vs. existing entities.

Auditing must know whether an entity is new to decide whether to preserve `CreatedDate` or update `LastModifiedDate`.

Spring Data Elasticsearch documentation recommends implementing `Persistable<ID>` to provide `isNew()` when explicit control over new/existing state is required.

Example:

~~~java
@Document(indexName = "products")
public class Product implements Persistable<String> {

    @Id
    private String id;

    @CreatedDate
    private Instant createdDate;

    @CreatedBy
    private String createdBy;

    @Override
    public String getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return id == null || (createdDate == null && createdBy == null);
    }
}
~~~

This is an illustrative strategy. `isNew()` must accurately reflect your application's entity lifecycle. If entities can be imported or lack audit metadata, use an explicit state/version marker instead of inferring from arbitrary fields.

## 9. Enabling auditing for imperative and reactive stacks

The two stacks use separate enablement annotations.

### 9.1. Imperative auditing

~~~java
@Configuration
@EnableElasticsearchAuditing
class ElasticsearchAuditingConfiguration {
}
~~~

### 9.2. Reactive auditing

~~~java
@Configuration
@EnableReactiveElasticsearchAuditing
class ReactiveElasticsearchAuditingConfiguration {
}
~~~

If the application uses reactive repositories, repository scanning must also match:

~~~java
@EnableReactiveElasticsearchRepositories(
    basePackages = "com.example.search.repository"
)
~~~

Do not enable imperative auditing and assume it will handle reactive entity callbacks. The reactive stack uses its own `ReactiveAuditingEntityCallback` and `ReactiveIsNewAwareAuditingHandler`.

### 9.3. Date-only auditing does not require AuditorAware

If entities only have `CreatedDate` and `LastModifiedDate`, auditing does not need a principal. In that case, you can enable reactive auditing without supplying `ReactiveAuditorAware`.

If using `CreatedBy` or `LastModifiedBy`, supply an auditor provider with a generic type compatible with the field.

### 9.4. Selecting the right bean via auditorAwareRef

If the application defines multiple `AuditorAware`/`ReactiveAuditorAware` beans, specify the bean name via `auditorAwareRef` on the auditing annotation.

Example:

~~~java
@Configuration
@EnableReactiveElasticsearchAuditing(
    auditorAwareRef = "reactiveAuditorAware"
)
class ReactiveAuditingConfiguration {
}
~~~

Do not let Spring pick the wrong auditor provider with an incompatible return type or principal source.

## 10. ReactiveAuditorAware and Spring Security

In reactive applications, `SecurityContext` is normally propagated via the Reactor Context. Do not use `ThreadLocal`-based `SecurityContextHolder` inside `ReactiveAuditorAware`, as execution can switch threads mid-request.

Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

@Configuration
class AuditorConfiguration {

    @Bean
    ReactiveAuditorAware<String> reactiveAuditorAware() {
        return () -> ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName);
    }
}
~~~

`ReactiveAuditorAware` returns a `Mono` containing the current auditor or `Mono.empty()` when none is available.

If the `Authentication` principal is a custom `UserDetails`, map it to a stable user ID instead of storing a display name.

### 10.1. Store IDs instead of display names

`createdBy` and `lastModifiedBy` should generally store a stable identifier:

- User ID.
- Service account ID.
- Tenant-scoped principal ID.
- System actor such as `batch-importer`.

Display names can change over time, complicating historical queries.

### 10.2. Background jobs and system actors

A batch job has no user security context. `ReactiveAuditorAware` can return a system actor:

~~~java
return () -> ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .filter(Authentication::isAuthenticated)
    .map(Authentication::getName)
    .switchIfEmpty(Mono.just("system:catalog-import"));
~~~

Use this fallback only when business rules permit it. If an auditor is mandatory, return `Mono.empty()` or emit an error according to policy rather than writing records without an actor.

### 10.3. Do not capture the principal at assembly time

Do not read `SecurityContext` in a constructor or bean initialization and cache it in a field. Principals change per subscription/request.

Always resolve the context inside the `Publisher` returned by `ReactiveAuditorAware`.

## 11. DateTimeProvider and clocks

Auditing uses `CurrentDateTimeProvider` by default to fetch the current timestamp. Replace it with a custom `DateTimeProvider` when you need:

- A uniform clock across components.
- Deterministic time in tests.
- A single system time source.
- Enforced UTC policy.

Example:

~~~java
@Bean
DateTimeProvider dateTimeProvider(Clock clock) {
    return () -> Optional.of(Instant.now(clock));
}

@Bean
Clock auditClock() {
    return Clock.systemUTC();
}
~~~

Then reference the bean:

~~~java
@EnableReactiveElasticsearchAuditing(
    dateTimeProviderRef = "dateTimeProvider"
)
~~~

If the system requires a business-provided timestamp, do not arbitrarily overwrite it with the local clock. Distinguish `occurredAt` from domain events from `auditedAt` updated by the projector/service.

## 12. Entity callbacks in Spring Data Elasticsearch

Entity callbacks are hooks invoked at specific points in the entity processing lifecycle. A callback can return the original entity or a modified instance.

Callbacks fit:

- Normalizing fields before conversion.
- Generating slugs or normalized values.
- Populating technical metadata.
- Stamping status or tenant context.
- Normalizing data after load/convert.
- Triggering post-save actions.

Spring Data recommends the `EntityCallback` API for lifecycle entity modifications. Application events may still be published prior to callbacks, but callbacks provide deterministic ordering.

### 12.1. Imperative and reactive callbacks are different interfaces

The reactive implementation invokes only reactive callbacks; the imperative implementation invokes only synchronous callbacks.

| Imperative | Reactive |
| --- | --- |
| `BeforeConvertCallback` | `ReactiveBeforeConvertCallback` |
| `AfterLoadCallback` | `ReactiveAfterLoadCallback` |
| `AfterConvertCallback` | `ReactiveAfterConvertCallback` |
| `AfterSaveCallback` | `ReactiveAfterSaveCallback` |

Do not implement synchronous `BeforeConvertCallback` and expect `ReactiveElasticsearchOperations` to invoke it. When moving a service to the reactive stack, migrate callback beans to the corresponding reactive interfaces.

### 12.2. Callbacks of Spring Data Elasticsearch

Callbacks invoked by Spring Data Elasticsearch during the entity lifecycle include:

| Callback | Timing | Purpose |
| --- | --- | --- |
| `BeforeConvertCallback` / `ReactiveBeforeConvertCallback` | Before entity is converted to a `Document` | Modify entity before writing |
| `AfterLoadCallback` / `ReactiveAfterLoadCallback` | After `Document` is loaded from Elasticsearch, before entity conversion | Process raw `Document` |
| `AfterConvertCallback` / `ReactiveAfterConvertCallback` | After `Document` is converted to entity | Enrich or normalize loaded entity |
| `AuditingEntityCallback` / `ReactiveAuditingEntityCallback` | Before convert | Populate created/modified metadata |
| `AfterSaveCallback` / `ReactiveAfterSaveCallback` | After saving | Process saved entity |

Verify exact callback lists and method signatures against your Spring Data Elasticsearch version. Do not assume every callback interface in Spring Data Commons is implemented by every store module.

## 13. Writing ReactiveBeforeConvertCallback

Example generating a slug before saving:

~~~java
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.event.ReactiveBeforeConvertCallback;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
class ProductSlugCallback
        implements ReactiveBeforeConvertCallback<Product> {

    @Override
    public Mono<Product> onBeforeConvert(
            Product product,
            IndexCoordinates index) {

        if (product.getSlug() != null && !product.getSlug().isBlank()) {
            return Mono.just(product);
        }

        product.setSlug(toSlug(product.getName()));
        return Mono.just(product);
    }

    private String toSlug(String value) {
        return value.toLowerCase()
            .trim()
            .replaceAll("[^a-z0-9]+", "-");
    }
}
~~~

This example uses a mutable entity. For immutable entities/records, construct and return a new instance instead of mutating the object.

Callbacks execute inside the reactive pipeline. They do not run when the bean is instantiated; logic executes when the operation is subscribed.

### 13.1. Return the modified entity

A callback must return the entity to pass to the next conversion step. If you create a new instance yet return the old entity, changes are lost.

### 13.2. Do not perform blocking I/O

Do not invoke blocking JDBC, synchronous HTTP clients, or `block()` inside a callback. If data from another service is required, compose the `Publisher` and return the resulting `Mono`/`Flux`.

However, callbacks should generally remain local, deterministic, and fast. Keeping multi-source business logic in the service layer prior to `save` makes it easier to observe and test.

## 14. Writing ReactiveAfterSaveCallback

A post-save callback can emit internal events or enrich data for downstream steps:

~~~java
import org.springframework.data.elasticsearch.core.event.ReactiveAfterSaveCallback;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
class ProductAfterSaveCallback
        implements ReactiveAfterSaveCallback<Product> {

    @Override
    public Mono<Product> onAfterSave(
            Product product,
            IndexCoordinates index) {

        return Mono.just(product);
    }
}
~~~

Do not send emails or call external systems directly inside a callback if delivery must be guaranteed. Elasticsearch `save` can succeed while the downstream side effect fails, or the callback may re-run on pipeline retries.

If durable event publishing is needed, use a transactional outbox at the authoritative data store or a workflow with explicit retries/deduplication. Elasticsearch callbacks do not establish distributed transactions.

## 15. Callback ordering and auditing

Spring Data registers auditing using an internal entity callback. In current Spring Data Elasticsearch, `AuditingEntityCallback` and `ReactiveAuditingEntityCallback` have order `100`. Store-specific callbacks such as `BeforeConvertCallback` default to `LOWEST_PRECEDENCE`.

This matters when the application registers additional callbacks:

- Callbacks with lower order values execute before callbacks with higher order values.
- Auditing callbacks may execute before default custom callbacks.
- A custom callback running after auditing could inadvertently overwrite `CreatedDate` or `LastModifiedDate`.
- If multiple callbacks modify the same field, the outcome depends on order.

### 15.1. Specify order intentionally

Use `@Order` or implement `Ordered`:

~~~java
@Component
@Order(200)
class ProductMetadataCallback
        implements ReactiveBeforeConvertCallback<Product> {

    @Override
    public Mono<Product> onBeforeConvert(
            Product product,
            IndexCoordinates index) {
        return Mono.just(product);
    }
}
~~~

Order `200` is an example. Choose values based on which callback must run first without clobbering audit metadata. Never rely on arbitrary ordering among unordered beans.

### 15.2. Prevent CreatedDate from being overwritten

A normalizing callback must not reset `CreatedDate` on every save. `CreatedDate` should only be populated when the entity is recognized as new; `LastModifiedDate` updates on modification.

If a custom callback touches audit fields, define an explicit policy and test both create and update flows.

### 15.3. Callback order must be tested

When multiple callbacks exist, verify:

- Actual execution order according to `@Order`/`Ordered`.
- Whether the callback receives the already-audited entity.
- Whether the callback returns a new instance.
- Which fields are mutated.
- That the reactive pipeline invokes callbacks on subscription.

Do not infer execution order from `@Bean` declaration order in configuration classes.

## 16. Application events and EntityCallback

Spring Data Elasticsearch emits store-specific `ApplicationEvent`s such as `BeforeConvertEvent` or `AfterSaveEvent` in supported versions.

`EntityCallback` is preferred when modifying entities at lifecycle checkpoints because:

- Callbacks return the modified entity.
- Reactive callbacks return a `Publisher`.
- Order is controlled via `Ordered`.
- Callbacks execute within the template lifecycle.
- They avoid ambiguity when `ApplicationEventMulticaster` runs asynchronously.

Application events remain useful for observation or event listeners, but never replace a callback with an async listener if logic must finish before conversion or persistence.

### 16.1. Do not mix synchronous listeners with reactive callbacks

A synchronous listener does not become reactive simply by running in a reactive application. If an entity must be modified before writing, use `ReactiveBeforeConvertCallback`.

### 16.2. Event listeners do not replace an outbox

In-process event listeners may not run if the JVM terminates or crashes right after a write. When side effects must be durable, use durable messaging/outbox patterns.

## 17. Upgrading legacy callbacks

When migrating from older versions, check for:

- Classes extending `AbstractElasticsearchEventListener`.
- Listeners handling `BeforeConvertEvent`/`AfterSaveEvent`.
- Synchronous callbacks implementing `BeforeConvertCallback`.
- Callbacks tied to concrete template implementations.
- Manual audit logic written inside listeners.
- Listeners relying on `ApplicationEventMulticaster`.

Choose the migration path:

| Legacy Logic | Migration Direction |
| --- | --- |
| Modify entity before conversion | `ReactiveBeforeConvertCallback` |
| Process `Document` after load | `ReactiveAfterLoadCallback` |
| Modify entity after conversion | `ReactiveAfterConvertCallback` |
| Post-save processing | `ReactiveAfterSaveCallback` |
| Populate created/modified fields | Reactive Elasticsearch auditing |
| Durable side effects | Outbox/messaging workflow |

Do not convert every listener to a callback mechanically. Some listeners merely observe events and do not need to modify entities.

## 18. Operations that may bypass entity callbacks

Entity callbacks are bound to the lifecycle executed by Spring Data templates/repositories. If the application bypasses the template and calls the Elasticsearch Java API Client directly, do not assume Spring Data auditing or callbacks will fire.

Cases to check separately:

- Direct calls to `ElasticsearchClient`.
- Client-level bulk requests.
- Direct update scripts.
- Delete-by-query.
- Reindex API.
- Ingest pipelines.
- Data sync jobs outside Spring Data.

If an operation bypasses the entity lifecycle, the application must populate audit fields itself or handle them at the ingest/source layer.

Specifically, partial script updates may modify only a few fields without materializing a full entity. Do not assume `@LastModifiedDate` updates automatically when an operation does not trigger auditing callbacks.

## 19. Auditing and immutable entities

For mutable entities, auditing can assign fields via setters or field access.

For immutable objects or Java records, the auditing infrastructure must instantiate a new object via persistent entity metadata and appropriate constructors/property accessors.

When using immutable entities:

- Ensure audit fields are included in the constructor/property model.
- Ensure mapping metadata recognizes the fields.
- Ensure custom callbacks do not return the old instance after auditing created a new one.
- Check constructor parameter names and nullability.
- Test both inserts and updates.

If a custom callback must modify an immutable entity, use a factory/wither or constructor to produce a new instance.

## 20. New vs. existing entity issue with pre-assigned IDs

Elasticsearch allows document IDs to be generated by the application prior to indexing. Thus, an entity with a non-null ID is not necessarily already persisted.

Example:

~~~java
Product product = new Product();
product.setId(UUID.randomUUID().toString());
product.setName("Keyboard");
~~~

If `isNew()` checks only `id == null`, this entity may be treated as already existing despite never having been saved.

Implement `Persistable<ID>` when explicit control is needed:

~~~java
public class Product implements Persistable<String> {

    @Id
    private String id;

    @CreatedDate
    private Instant createdDate;

    @Override
    public String getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return createdDate == null;
    }
}
~~~

This is a minimal example. If data can be imported with `CreatedDate` already set, or the field can be `null` on an existing document, use a more reliable new/persisted state flag.

## 21. Configuring reactive repositories and auditing together

Example configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.repository.config.EnableReactiveElasticsearchRepositories;
import org.springframework.data.elasticsearch.config.EnableReactiveElasticsearchAuditing;

@Configuration
@EnableReactiveElasticsearchRepositories(
    basePackages = "com.example.product.repository"
)
@EnableReactiveElasticsearchAuditing(
    auditorAwareRef = "reactiveAuditorAware"
)
class ReactiveElasticsearchConfiguration {
}
~~~

Reactive client configuration can live in a dedicated configuration class extending Spring Data's `ReactiveElasticsearchConfiguration`. If sharing a similar name, name your class distinctly to avoid confusion between your application configuration and Spring Data's base class.

Example provider:

~~~java
@Bean
ReactiveAuditorAware<String> reactiveAuditorAware() {
    return () -> ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .filter(Authentication::isAuthenticated)
        .map(Authentication::getName);
}
~~~

Do not enable both imperative and reactive repository scanning on the same package without a clear design. Dual repository infrastructures can create duplicate beans or bind unexpected `operations`.

## 22. Phased migration checklist

### Phase A: Dependencies and client

1. Identify Spring Boot, Spring Data Elasticsearch, and Elasticsearch server versions.
2. Inspect the dependency tree for legacy clients.
3. Remove `RestHighLevelClient` once migrated to the new client generation.
4. Update reactive configuration to the appropriate `ReactiveElasticsearchConfiguration`.
5. On Spring Data 6.x, check `Rest5Client` default and legacy `RestClient` usage.
6. Update imports and client configuration callbacks.
7. Migrate `NativeSearchQuery` to `NativeQuery` if on the 4.4 to 5.0 path.
8. Update data types/APIs such as `Long` sequence numbers or `ScriptData` where applicable.
9. Verify TLS, timeouts, authentication, and connection lifecycles.

### Phase B: Reactive operations

1. Use `ReactiveElasticsearchOperations` or `ReactiveElasticsearchRepository`.
2. Remove `block()` from request paths.
3. Return `Mono`/`Flux` to callers.
4. Remove manual `subscribe()` calls inside services.
5. Handle timeouts, retries, and cancellation.
6. Verify bulk/search pagination and backpressure.
7. Verify clients/transports close properly on shutdown.

### Phase C: Auditing

1. Add audit fields to entities.
2. Choose date/time types and mappings.
3. Define `isNew()` for entities with pre-assigned IDs.
4. Enable `@EnableReactiveElasticsearchAuditing`.
5. Provide `ReactiveAuditorAware` if `CreatedBy`/`LastModifiedBy` are used.
6. Read principals from the Reactor/Spring Security reactive context.
7. Configure a system actor fallback if business rules permit.
8. Configure `DateTimeProvider` if a uniform clock is required.

### Phase D: Entity callbacks

1. Inventory existing callbacks and event listeners.
2. Migrate synchronous callbacks to reactive callback interfaces.
3. Return entities or `Publisher`s containing entities.
4. Remove blocking I/O and `ThreadLocal` access.
5. Set explicit callback ordering.
6. Prevent unintended overwrites of audit fields.
7. Move durable side effects to outboxes/workflows.
8. Check whether direct client/bulk/update paths bypass callbacks.

### Phase E: Testing and rollout

1. Boot the Spring context with reactive configuration.
2. Verify reactive repository beans are instantiated properly.
3. Verify `save` populates `CreatedDate`/`CreatedBy`.
4. Verify updates preserve `CreatedDate` and update `LastModifiedDate`.
5. Verify `ReactiveAuditorAware` extracts the proper principal.
6. Verify background jobs use the system actor.
7. Verify callbacks run upon subscription.
8. Verify callback execution order.
9. Verify bulk/direct client paths.
10. Run integration tests against a compatible Elasticsearch version.
11. Monitor mapping errors, timeouts, connection pools, and latency post-deploy.

## 23. Testing reactive auditing

Tests must subscribe to the pipeline for callbacks to run. Use `StepVerifier`:

~~~java
StepVerifier.create(productRepository.save(product))
    .assertNext(saved -> {
        assertThat(saved.getCreatedDate()).isNotNull();
        assertThat(saved.getLastModifiedDate()).isNotNull();
        assertThat(saved.getCreatedBy()).isEqualTo("test-user");
    })
    .verifyComplete();
~~~

To test principals, attach the reactive security context on subscription:

~~~java
Mono<Product> result = productRepository.save(product)
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(authentication)
    );

StepVerifier.create(result)
    .assertNext(saved ->
        assertThat(saved.getCreatedBy()).isEqualTo("test-user")
    )
    .verifyComplete();
~~~

Exact `Authentication` test fixtures and Spring Security dependencies depend on your project.

### 23.1. Testing creates and updates

Scenario:

1. Save the entity for the first time.
2. Record `CreatedDate` and `CreatedBy`.
3. Advance or freeze the clock.
4. Update the entity and save again.
5. Assert `CreatedDate`/`CreatedBy` remain unchanged.
6. Assert `LastModifiedDate`/`LastModifiedBy` are updated.

Do not rely on consecutive wall-clock calls and assert millisecond differences if clock precision is not guaranteed. Inject a fixed `Clock` or advance a test clock.

### 23.2. Testing callbacks

A test callback can stamp a marker field:

~~~java
@Component
class ProductMarkerCallback
        implements ReactiveBeforeConvertCallback<Product> {

    @Override
    public Mono<Product> onBeforeConvert(
            Product product,
            IndexCoordinates index) {
        product.setIndexedByCallback(true);
        return Mono.just(product);
    }
}
~~~

After saving and reading the document back, assert the marker field was persisted. If a test merely invokes the method without subscribing, the callback will not run.

## 24. Common mistakes

**Using imperative client configuration for reactive repositories.** Reactive repositories require `ReactiveElasticsearchOperations` and the corresponding reactive client. Use `ReactiveElasticsearchConfiguration`.

**Keeping RestHighLevelClient after migrating to the new client.** The legacy package is deprecated and may be removed. Migrate to the client/API specified in the migration guide.

**Upgrading the Elasticsearch Java API Client independently of Spring Data.** Dependencies may become incompatible. Let the Spring Boot/Spring Data BOM manage versions when possible.

**Only renaming NativeSearchQuery to NativeQuery while keeping old query builders.** The new query model uses Elasticsearch Java API Client classes. Migrate and test DSL per query.

**Using EnableElasticsearchAuditing for the reactive stack.** Use `EnableReactiveElasticsearchAuditing`.

**Using synchronous AuditorAware to read reactive principals.** Use `ReactiveAuditorAware` and resolve principals from the Reactor Context.

**Reading SecurityContextHolder inside a reactive pipeline.** `ThreadLocal` is not preserved across thread hops. Use `ReactiveSecurityContextHolder`.

**Forgetting isNew() when IDs are pre-assigned.** `CreatedDate`/`LastModifiedDate` may behave incorrectly. Use `Persistable` or an explicit new-entity detection strategy.

**Using synchronous callbacks with the reactive template.** The reactive implementation invokes reactive callback interfaces. Migrate to `ReactiveBeforeConvertCallback` and corresponding interfaces.

**Callback failing to return the modified entity.** Changes are discarded before conversion. Return the modified instance or a `Publisher` emitting the new instance.

**Calling block() inside a callback.** This can block the event loop and degrade throughput. Compose `Publisher`s or move I/O outside callbacks.

**Subscribing manually inside services.** Callers lose error propagation and completion signals. Return the `Publisher` to callers.

**Using ThreadLocal to resolve the auditor.** Reactive execution can switch threads. Resolve principals from the Reactor Context.

**Callback overwriting CreatedDate.** A callback running after auditing may reset metadata. Control ordering and touch only responsible fields.

**Assuming callbacks run on all low-level APIs.** Direct client, script, or bulk paths can bypass the entity lifecycle. Populate audit metadata at the appropriate layer.

**Triggering non-durable side effects inside AfterSaveCallback.** Save success does not guarantee messages/emails were delivered. Use an outbox/workflow for critical side effects.

**Failing to test reactive callbacks because tests never subscribe.** Callbacks only run in the pipeline upon subscription. Use `StepVerifier` or subscribe at the test boundary.

**Using async application events to mutate entities before saving.** The event multicaster can run on a different thread with no ordering guarantees. Use `EntityCallback`.

## 25. Safe upgrade rollout workflow

A practical roadmap:

1. Lock down the version matrix across Spring Boot, Spring Data Elasticsearch, Elasticsearch client, and server.
2. Read the migration guide between source and target versions.
3. Migrate reactive client configuration to the matching class.
4. Migrate query APIs, imports, and client callbacks.
5. Verify `ReactiveElasticsearchOperations` and repository wiring.
6. Add auditing annotations and check entity `isNew` semantics.
7. Enable `EnableReactiveElasticsearchAuditing`.
8. Migrate `AuditorAware` to `ReactiveAuditorAware`.
9. Migrate callback implementations to reactive interfaces.
10. Verify callback ordering and eliminate blocking calls.
11. Audit write paths that bypass the Spring Data entity lifecycle.
12. Write integration tests covering create/update/auditor/callbacks.
13. Deploy via canary and monitor latency, errors, connection pools, and audit fields.
14. Delete legacy client/callback code once all callers have migrated.

## 26. References

- [Spring Data Elasticsearch - Elasticsearch Clients](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/clients.html): imperative/reactive client configuration and `Rest5Client`.
- [Spring Data Elasticsearch - Upgrading 4.4.x to 5.0.x](https://docs.spring.io/spring-data/elasticsearch/reference/migration-guides/migration-guide-4.4-5.0.html): package changes, `NativeQuery`, and client migration.
- [Spring Data Elasticsearch - Upgrading 5.5.x to 6.0.x](https://docs.spring.io/spring-data/elasticsearch/reference/migration-guides/migration-guide-5.5-6.0.html): Elasticsearch 9 libraries, `Rest5Client`, legacy `RestClient`, and API changes.
- [Spring Data Elasticsearch - Auditing](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/auditing.html): entity audit metadata, `Persistable`, `AuditorAware`, and reactive auditing.
- [Spring Data Elasticsearch - Entity Callbacks](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/entity-callbacks.html): synchronous/reactive callback interfaces, lifecycle, and ordering.
- [Spring Data Commons - Auditing](https://docs.spring.io/spring-data/elasticsearch/reference/data-commons/auditing.html): `CreatedBy`, `CreatedDate`, `AuditorAware`, and `ReactiveAuditorAware`.
- [Spring Data Elasticsearch - ReactiveElasticsearchAuditing API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/config/EnableReactiveElasticsearchAuditing.html): reactive auditing configuration.
- [Spring Security - Reactive Security Context](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): security context in reactive applications.

Packages, method signatures, and client generations change across Spring Data Elasticsearch versions. Cross-check Javadoc and migration guides for your exact upgrade versions. The key takeaway is that the reactive client, reactive auditing, and reactive callbacks must all share the reactive lifecycle; verify every write path to ensure audit metadata is populated accurately and not overwritten by custom callbacks.
