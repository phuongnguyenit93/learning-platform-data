# Callback Ordering with Ordered or @Order

Spring Data Elasticsearch provides `EntityCallback` to intervene on an entity at defined points when writing and reading documents. An application can have multiple callbacks processing the same entity: normalizing data, building search fields, assigning metadata, or enriching information after reading.

When multiple callbacks belong to the same phase, execution order directly affects the result. For example, a callback building a search string must run after a callback normalizing the name; a custom callback may need to run before or after the auditing callback to use created and modified date fields.

Spring Data supports two ways to specify order:

- Implementing the `org.springframework.core.Ordered` interface and returning a value from `getOrder()`.
- Annotating the callback class or bean method with `org.springframework.core.annotation.Order`.

The core rule is that **the smaller the order value, the earlier the callback is invoked**. This ordering applies within the same callback chain; it does not alter the fixed order between lifecycle phases.

## 1. EntityCallback in Spring Data Elasticsearch

`EntityCallback` is a typed hook tied to a domain type. Spring Data invokes callbacks at checkpoints while converting an entity to a document, writing a document, reading a document, and converting a document back to an entity.

For example, a product may require these steps before writing:

1. Normalize name and SKU.
2. Build a value for searching.
3. Assign auditing metadata such as creator and modification timestamp.
4. Convert the entity into an Elasticsearch `Document` and write it to the index.

If these steps live in multiple callbacks, the application must declare their order so later steps see the output of earlier steps.

Entity callbacks have several characteristics:

- A callback is bound to an entity type via its generic type, e.g. `BeforeConvertCallback<Product>`.
- A callback can return the same entity or a modified instance.
- Callbacks execute sequentially in sorted order.
- Synchronous and reactive callbacks are separate; synchronous APIs only invoke synchronous callbacks, and reactive APIs only invoke reactive callbacks.
- Callbacks are registered in the Spring `ApplicationContext` so Spring Data implementations can discover them.

`EntityCallback` fits synchronous, strictly ordered entity modifications. It is a better choice than `ApplicationEvent` when logic must complete in a guaranteed order before the save operation proceeds.

## 2. Callbacks in the Elasticsearch Lifecycle

Spring Data Elasticsearch provides callbacks for both the write path and the read path.

### 2.1. Write Path

Conceptual write flow:

~~~text
Entity
  |
  v
BeforeConvertCallback
  |
  v
Entity -> Elasticsearch Document
  |
  v
Write document to Elasticsearch
  |
  v
AfterSaveCallback
  |
  v
Entity returned to caller
~~~

`BeforeConvertCallback<T>` runs before the entity is converted into a `Document`. The callback can return the normalized entity or another instance. The returned entity becomes the input for the subsequent conversion step.

`AfterSaveCallback<T>` runs after the document has been saved. The callback receives the entity and `IndexCoordinates`, and returns the entity to the calling flow. Modifying the entity in this callback does not automatically write the document a second time.

### 2.2. Read Path

Read flow:

~~~text
Elasticsearch returns document
  |
  v
AfterLoadCallback
  |
  v
Document -> Entity
  |
  v
AfterConvertCallback
  |
  v
Entity returned to caller
~~~

`AfterLoadCallback<T>` receives the newly read `Document` and can adjust the document before conversion. `AfterConvertCallback<T>` receives the entity created from the document and can modify the entity before returning it to the caller.

### 2.3. Callback Phases and Ordering Are Different Concepts

| Phase | Timing | Data Received or Returned by Callback |
| --- | --- | --- |
| BeforeConvert | Before converting entity into Document | Entity |
| AfterSave | After saving document | Entity |
| AfterLoad | After reading Document, before converting | Document |
| AfterConvert | After converting Document into entity | Entity |
| AuditingEntityCallback | During the BeforeConvert phase | Entity with auditing fields |

Order only sorts callbacks eligible to participate in the same callback chain. For instance, orders 10 and 20 determine which order two `BeforeConvertCallback` instances run in. Order cannot make an `AfterSaveCallback` run before a `BeforeConvertCallback`; the lifecycle fixes phase order.

### 2.4. Which Callbacks Does Spring Data Elasticsearch Support?

Current Spring Data Elasticsearch documentation lists the store-specific callbacks as:

- `BeforeConvertCallback`
- `AfterLoadCallback`
- `AfterConvertCallback`
- `AfterSaveCallback`
- `AuditingEntityCallback`

Spring Data Commons documentation includes a general example for `BeforeSaveCallback`. Do not infer that every callback in the Commons documentation is supported by every store module. For Spring Data Elasticsearch, check the callback list in your exact dependency version before designing around a specific phase.

Corresponding reactive callbacks carry the `Reactive` prefix, such as `ReactiveBeforeConvertCallback` and `ReactiveAfterSaveCallback`.

## 3. Sorting Rule: Smaller Numbers Run First

Spring uses order values to sort callbacks. A smaller value gives higher execution precedence.

| Order value | Meaning |
| ---: | --- |
| `Ordered.HIGHEST_PRECEDENCE` | Highest precedence, typically the smallest integer |
| -100 | Runs before callback with order 0 |
| 0 | Runs before callback with order 10 |
| 10 | Runs after order 0 |
| 100 | Runs after order 10 |
| `Ordered.LOWEST_PRECEDENCE` | Lowest precedence, typically the largest integer |

Example of three ordered callbacks:

~~~text
NormalizeProductCallback  order = 10
AuditingEntityCallback    order = 100
BuildSearchTextCallback  order = 200
~~~

Result:

~~~text
NormalizeProductCallback
          |
          v
AuditingEntityCallback
          |
          v
BuildSearchTextCallback
          |
          v
Entity converted into Document
~~~

Do not confuse `LOWEST_PRECEDENCE` with highest priority. This name means the callback is placed last among ordered items.

### 3.1. Default Value

A callback without an explicit order is typically treated as `Ordered.LOWEST_PRECEDENCE`, so it runs after callbacks with explicit order values.

Spring Data Elasticsearch documentation also notes that callbacks created via lambda expressions lack typing information for filtering by entity type and are invoked last by default. If you need a callback scoped to one entity type and efficient filtering, use a class or enum with an explicit generic type.

### 3.2. Avoid Using the Same Order Value for Dependent Logic

If two callbacks must run in a deterministic order, assign two distinct values. When two callbacks share the same order, do not rely on bean registration order, class names, or component scan order to decide which runs first.

Example:

~~~java
@Component
@Order(10)
class NormalizeNameCallback implements BeforeConvertCallback<Product> {
    // ...
}

@Component
@Order(20)
class BuildSearchTextCallback implements BeforeConvertCallback<Product> {
    // ...
}
~~~

The search-text callback will run after the name-normalization callback.

## 4. First Approach: Implementing Ordered

`Ordered` is a Spring Core interface. A callback implements this interface and returns an order value from `getOrder()`.

~~~java
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;
import org.springframework.data.elasticsearch.core.event.BeforeConvertCallback;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

@Component
public class NormalizeProductCallback
        implements BeforeConvertCallback<Product>, Ordered {

    @Override
    public Product onBeforeConvert(
            Product entity,
            IndexCoordinates index) {

        entity.setName(entity.getName().trim());
        entity.setSku(entity.getSku().trim().toUpperCase());
        return entity;
    }

    @Override
    public int getOrder() {
        return 10;
    }
}
~~~

In this example:

- The callback applies only to the `Product` entity.
- The callback runs in the `BeforeConvert` phase.
- Name and SKU are normalized before the entity is converted.
- `getOrder()` returns `10` to define its position in the callback chain.

### 4.1. When Should You Use Ordered?

Use `Ordered` when:

- Order is an intrinsic part of the callback implementation.
- You want the order defined directly inside the class.
- The callback is packaged and reused as a standalone component.
- The order value can be computed or read from configuration inside the implementation.

A class only needs to implement `Ordered` if it genuinely needs an explicit order. Callbacks independent of other callbacks can keep the default.

### 4.2. Returning a New Entity for Immutable Types

Not all entities are mutable. For records or immutable classes, the callback should construct a new instance instead of mutating fields.

~~~java
public record Product(
    String id,
    String name,
    String sku
) {}

@Component
public class NormalizeImmutableProductCallback
        implements BeforeConvertCallback<Product>, Ordered {

    @Override
    public Product onBeforeConvert(
            Product entity,
            IndexCoordinates index) {

        return new Product(
            entity.id(),
            entity.name().trim(),
            entity.sku().trim().toUpperCase()
        );
    }

    @Override
    public int getOrder() {
        return 10;
    }
}
~~~

The value returned by the callback is what gets converted and saved. If the callback creates a new instance but returns the old instance, the changes will not be used.

## 5. Second Approach: Using @Order

`Order` is a Spring Core annotation. It can be placed on the callback class or on the `@Bean` factory method creating the callback.

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.data.elasticsearch.core.event.BeforeConvertCallback;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

@Component
@Order(20)
public class BuildSearchTextCallback
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product entity,
            IndexCoordinates index) {

        entity.setSearchText(
            entity.getName() + " " + entity.getSku()
        );
        return entity;
    }
}
~~~

This callback runs at order 20. If the normalization callback has order 10, the search-text callback receives the already-normalized entity.

### 5.1. Placing Order on a Bean Method

If the callback is declared in a configuration class:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.data.elasticsearch.core.event.BeforeConvertCallback;

@Configuration
public class ProductCallbackConfiguration {

    @Bean
    @Order(20)
    BeforeConvertCallback<Product> buildSearchTextCallback() {
        return (entity, index) -> {
            entity.setSearchText(
                entity.getName() + " " + entity.getSku()
            );
            return entity;
        };
    }
}
~~~

Because this is a lambda callback, it lacks runtime generic type information unlike a concrete implementing class. Spring Data documentation recommends using a class or enum when efficient type filtering is needed. In applications with many entity types and callbacks, separate classes are usually easier to read and test.

### 5.2. Order Does Not Control Bean Creation

`Order` determines the usage order of beans in order-aware mechanisms such as an entity callback chain. It does not force Spring to instantiate beans in that order.

Do not use `Order` instead of:

- `DependsOn` when you genuinely need to dictate bean initialization relationships.
- Dependency injection when one bean requires another bean.
- Transactions or synchronization when controlling transactional ordering.
- Separate ordering mechanisms for event listeners or task executors.

In `EntityCallback`, `Order` is used to sort callbacks when Spring Data invokes the callback chain.

## 6. Choosing Ordered vs. Order

Both approaches express the same ordering concept. Choose whichever matches how you manage configuration.

| Criterion | Ordered | Order |
| --- | --- | --- |
| Declaration | Implement interface | Annotation on class or bean method |
| Value location | `getOrder()` | Annotation value |
| Best suited when | Order belongs to the implementation | Order is configuration metadata |
| Can override dynamically | Can return value from method | Static declared value |
| Clarity in class | Immediately visible via interface and method | Immediately visible on annotation |

Example achieving the same goal:

~~~java
class FirstCallback implements BeforeConvertCallback<Product>, Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public Product onBeforeConvert(Product entity, IndexCoordinates index) {
        return entity;
    }
}
~~~

~~~java
@Component
@Order(10)
class SecondCallback implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(Product entity, IndexCoordinates index) {
        return entity;
    }
}
~~~

Do not implement both `Ordered` and `Order` with two different values on the same callback. Pick one source of order to avoid confusing maintainers.

## 7. Ordering of Auditing Callbacks

Spring Data Elasticsearch integrates auditing via `AuditingEntityCallback`. This callback runs in the `BeforeConvert` phase and populates auditing fields before the entity is converted into a document.

Common annotations:

| Annotation | Meaning |
| --- | --- |
| `CreatedDate` | Timestamp when the entity was created |
| `LastModifiedDate` | Timestamp when the entity was last updated |
| `CreatedBy` | Creator of the entity |
| `LastModifiedBy` | Last modifier of the entity |

Entity example:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.elasticsearch.annotations.Document;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    private String name;
    private String sku;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String updatedBy;

    // Constructors, getters, and setters
}
~~~

### 7.1. Enabling Elasticsearch Auditing

~~~java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.elasticsearch.config.EnableElasticsearchAuditing;

@Configuration
@EnableElasticsearchAuditing
public class ElasticsearchAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorProvider() {
        return () -> Optional.of("system");
    }
}
~~~

This example returns a fixed auditor for illustration. In real applications, `AuditorAware` typically reads the current user from the security context or a trusted execution context. For background jobs, it can return an appropriate service account.

If only creation and modification dates are needed, auditing can still update date fields without an `AuditorAware`. To use `CreatedBy` and `LastModifiedBy`, provide an auditor source.

### 7.2. Default Order of AuditingEntityCallback

In current Spring Data Elasticsearch documentation, `AuditingEntityCallback` has an order of `100`. Standard store-specific callbacks such as `BeforeConvertCallback` default to `Ordered.LOWEST_PRECEDENCE`.

That means:

- A callback with order 50 runs before auditing.
- The auditing callback runs at order 100.
- A callback with order 150 runs after auditing.
- A callback without an explicit order usually runs at the end of the callback chain.

Example:

~~~text
NormalizeProductCallback     Order(50)
             |
             v
AuditingEntityCallback       order 100
             |
             v
BuildAuditSearchTextCallback Order(150)
             |
             v
Convert entity -> Document
~~~

If a callback produces data depending on `createdAt`, `updatedAt`, `createdBy`, or `updatedBy`, place its order after auditing. If a callback alters input fields that auditing does not depend on, it can be placed before auditing.

The order value `100` is an implementation detail of the auditing callback in the referenced documentation versions. If your application logic relies on this exact number, verify the Javadoc or source of your Spring Data Elasticsearch version.

### 7.3. Example Callback After Auditing

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.data.elasticsearch.core.event.BeforeConvertCallback;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

@Component
@Order(150)
public class BuildProductAuditTextCallback
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product entity,
            IndexCoordinates index) {

        entity.setAuditText(
            entity.getCreatedBy() + " " +
            entity.getUpdatedBy() + " " +
            entity.getUpdatedAt()
        );
        return entity;
    }
}
~~~

Because order 150 is greater than the auditing callback's order 100, this callback runs after auditing has populated the entity. If it ran before auditing, the auditor fields might not yet be assigned for the current save.

Only construct composite fields from audit metadata if there is an explicit search or display requirement. Do not duplicate these fields mechanically.

## 8. How Does a Callback Chain Pass Results?

Callbacks in the same chain are invoked sequentially. The result of the previous callback is passed as the input to the next callback.

Suppose we have:

- Callback A: trims the name.
- Callback B: lowercases the name.
- Callback C: builds search text.

With orders 10, 20, and 30:

~~~text
Input: "  Mechanical Keyboard  "
                |
                v
       A: trim whitespace
                |
                v
       "Mechanical Keyboard"
                |
                v
       B: lowercase
                |
                v
       "mechanical keyboard"
                |
                v
       C: build search text
                |
                v
       Final entity
                |
                v
       Convert and persist
~~~

Each callback must return the modified instance. If a callback mutates the entity and returns it, the change propagates forward. For immutable objects, return the new instance.

### 8.1. Multiple Callbacks Example

Normalization callback:

~~~java
@Component
@Order(10)
class NormalizeProductName implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(Product entity, IndexCoordinates index) {
        entity.setName(entity.getName().trim());
        return entity;
    }
}
~~~

Slug-building callback:

~~~java
@Component
@Order(20)
class BuildProductSlug implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(Product entity, IndexCoordinates index) {
        entity.setSlug(toSlug(entity.getName()));
        return entity;
    }

    private String toSlug(String value) {
        return value.toLowerCase().replace(" ", "-");
    }
}
~~~

Search-text callback:

~~~java
@Component
@Order(30)
class BuildProductSearchText implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(Product entity, IndexCoordinates index) {
        entity.setSearchText(
            entity.getName() + " " + entity.getSku() + " " + entity.getSlug()
        );
        return entity;
    }
}
~~~

This ordering guarantees the slug is generated from the trimmed name, and the search text uses the already-normalized name and generated slug.

### 8.2. One Class Can Implement Multiple Callback Interfaces

A single component can implement multiple callback interfaces:

~~~java
@Component
@Order(100)
class ProductLifecycleCallbacks
        implements BeforeConvertCallback<Product>,
                   AfterConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(Product entity, IndexCoordinates index) {
        // Prepare data before writing.
        return entity;
    }

    @Override
    public Product onAfterConvert(
            Product entity,
            Document document,
            IndexCoordinates index) {
        // Enrich entity after reading.
        return entity;
    }
}
~~~

The bean's order is used when each corresponding callback is sorted within its phase. `BeforeConvert` and `AfterConvert` ordering remain in two separate chains.

## 9. Callback Types and Domain Types

Generic types tell Spring Data which entity type a callback applies to:

~~~java
BeforeConvertCallback<Product>
BeforeConvertCallback<Order>
AfterConvertCallback<Customer>
~~~

`BeforeConvertCallback<Product>` is designed to handle `Product`. It should not contain logic meant for every entity type.

If a callback needs to handle multiple entity types, you can:

- Create a separate callback per type.
- Use a shared interface for a group of entities sharing the same behavior.
- Create a component implementing multiple callback interfaces with concrete generic types.

Do not use lambdas lacking type information in systems with many callbacks and domain types if doing so forces the framework to evaluate the callback against unrelated entities.

### 9.1. IndexCoordinates in Callbacks

Elasticsearch callbacks receive `IndexCoordinates` to indicate the target index or indices for the operation:

~~~java
@Override
public Product onBeforeConvert(
        Product entity,
        IndexCoordinates index) {

    if (index.getIndexNames().length == 0) {
        return entity;
    }

    // Index-specific rules can be applied if truly needed.
    return entity;
}
~~~

In most cases, callbacks should depend on the domain type rather than index names. Use index coordinates when a single entity is stored in multiple indices or when special rules apply per write target.

## 10. Registering Callbacks in ApplicationContext

Spring Data retrieves `EntityCallback` beans from the `ApplicationContext`. They can be registered via component scanning:

~~~java
@Component
@Order(10)
class NormalizeProductCallback implements BeforeConvertCallback<Product> {
    // ...
}
~~~

Or registered via configuration:

~~~java
@Configuration
class ProductCallbacksConfiguration {

    @Bean
    @Order(10)
    NormalizeProductCallback normalizeProductCallback() {
        return new NormalizeProductCallback();
    }
}
~~~

Do not instantiate a new callback object inside a repository method or service on every save. Callbacks should be Spring-managed beans so the framework can discover and order them.

### 10.1. Templates and Repositories

Spring Data template implementations normally have access to the `ApplicationContext` and receive callback beans. Repositories backed by the corresponding template/operations also pass through the configured mapping and callback mechanism.

If you instantiate `ElasticsearchTemplate` or `ElasticsearchOperations` manually, ensure callback configuration is attached to the template. A callback bean residing in a different context or left unregistered will not run automatically.

### 10.2. Calling the Java API Client Directly

If you call directly:

~~~java
elasticsearchClient.index(request);
~~~

the operation does not pass through Spring Data's entity mapping lifecycle. Therefore, do not expect Spring Data's `BeforeConvertCallback`, `AfterSaveCallback`, or auditing callbacks to run automatically.

If an ingestion flow uses the raw Elasticsearch Java API Client or Bulk REST API, the application must invoke the corresponding normalization/auditing logic in the service/projector layer or use a Spring Data write path that supports callbacks.

This is especially important when one part of an application writes via repositories while another writes via a raw bulk client. If the two flows do not share the same rules, documents may end up with inconsistent audit or search fields.

## 11. Callbacks and ApplicationEvent Are Not the Same

Spring Data can publish store-specific events such as `BeforeSaveEvent`. `EntityCallback` is a distinct mechanism:

| EntityCallback | ApplicationEvent |
| --- | --- |
| Generic type bound to domain type | Event has its own event-specific type |
| Invoked at defined lifecycle checkpoints | Published through `ApplicationEventMulticaster` |
| Supports ordered callback chains | Listeners have their own ordering mechanism |
| Returns modified entity or document | Event listeners do not always have a way to return a new entity into the save flow |
| Has separate synchronous and reactive APIs | Can be processed asynchronously depending on configuration |

If an asynchronous event multicaster is used, listeners may run on another thread and execution order is no longer suitable as a mandatory pre-save normalization step.

`EntityCallback` is designed to process entities at lifecycle checkpoints and guarantee execution order within the corresponding chain. Events fit notifications, integrations, or side effects depending on your architecture.

## 12. Reactive Callbacks Have Their Own Ordering

Spring Data Elasticsearch provides a reactive API with corresponding callback interfaces:

- `ReactiveBeforeConvertCallback<T>`
- `ReactiveAfterLoadCallback<T>`
- `ReactiveAfterConvertCallback<T>`
- `ReactiveAfterSaveCallback<T>`
- `ReactiveAuditingEntityCallback`

Reactive callbacks return a `Publisher` rather than returning the entity directly. Ordering still applies within the reactive callback chain, though reactive APIs only inspect reactive callbacks.

Illustrative example:

~~~java
import org.reactivestreams.Publisher;
import org.springframework.core.Ordered;
import org.springframework.data.elasticsearch.core.event.ReactiveBeforeConvertCallback;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
class ReactiveNormalizeProductCallback
        implements ReactiveBeforeConvertCallback<Product>, Ordered {

    @Override
    public Publisher<Product> onBeforeConvert(
            Product entity,
            IndexCoordinates index) {

        entity.setName(entity.getName().trim());
        return Mono.just(entity);
    }

    @Override
    public int getOrder() {
        return 10;
    }
}
~~~

This example uses `Mono.just`. In a real application, if the callback calls an asynchronous service, return the corresponding publisher and do not block inside the callback.

Do not implement a synchronous callback and expect `ReactiveElasticsearchOperations` to invoke it automatically. The two callback APIs are kept separate to avoid mixing synchronous and reactive semantics.

## 13. Exception Handling in Callbacks

Callbacks are part of the lifecycle operation. If a callback throws an exception, the current processing flow can stop at that phase.

| Phase Where Error Occurs | Common Consequence |
| --- | --- |
| BeforeConvert | Entity has not been converted/written; save operation fails |
| AfterLoad | Document was read but cannot continue normal read pipeline |
| AfterConvert | Document was converted but entity is not returned normally |
| AfterSave | Document may already have been written before the callback threw; caller may still receive an exception |

### 13.1. Do Not Use AfterSave for Pre-Write Checks

If a mandatory condition must be checked before a document is saved, put that logic in `BeforeConvert` or the service layer before calling `save`.

If `AfterSaveCallback` throws an exception, do not assume Elasticsearch rolled back the written document. The caller may see an error even though the document exists in the index.

### 13.2. Do Not Swallow Exceptions Arbitrarily

Do not catch every exception and return the old entity as if the operation succeeded. If a callback builds required search fields, ignoring errors can leave documents missing fields and produce hard-to-detect bugs.

If a callback only performs optional side effects, consider moving the side effect to an event/outbox or a separate retryable flow instead of blocking the primary save operation.

## 14. Testing Callback Order

Callback ordering should be tested at two levels:

1. Unit tests for each callback, verifying it transforms the entity properly.
2. Integration tests with the Spring `ApplicationContext` and Elasticsearch operations, verifying callbacks are registered and run in the expected order.

### 14.1. Unit Test for a Callback

~~~java
@Test
void shouldTrimProductNameBeforeConvert() {
    Product product = new Product();
    product.setName("  Keyboard  ");

    Product result = callback.onBeforeConvert(
        product,
        IndexCoordinates.of("products")
    );

    assertThat(result.getName()).isEqualTo("Keyboard");
}
~~~

### 14.2. Verifying Order with a Trace

In an integration test, each callback can append a marker to a test-only field or record into an injected collector:

~~~text
normalize
auditing
build-search-text
~~~

After saving the entity, assert the markers appear in the expected order. Do not use component scan order as an assertion.

Another approach is asserting the final output: the search text used the normalized name and audit fields were populated prior to conversion.

### 14.3. Testing Auditing

With `EnableElasticsearchAuditing`, verify:

- New inserts have `createdAt` and `createdBy`.
- Updates preserve `createdAt` and `createdBy`.
- Updates modify `updatedAt` and `updatedBy`.
- Callbacks running after auditing can read the expected values.
- Entities not marked auditable are not altered unexpectedly.

If using a custom clock or auditor provider, inject a controllable implementation so tests do not depend on wall-clock time or real users.

## 15. Common Pitfalls with Ordered and Order

**Assuming higher order numbers run first.** Spring sorts in ascending order; smaller numbers run first.

**Confusing LOWEST_PRECEDENCE with highest priority.** This value places the callback at the end of the sorted group.

**Assuming Order controls bean creation.** The annotation orders callbacks when invoked; it does not control when Spring instantiates beans.

**Assigning the same order to two dependent callbacks.** Their relative order should not be treated as a contract. Assign distinct values.

**Placing a search-field builder callback before normalization.** Search fields may capture unnormalized data. Order the pipeline by data dependencies.

**Assuming auditing runs last.** The auditing callback has order 100 in current Spring Data Elasticsearch documentation; callbacks defaulting to `LOWEST_PRECEDENCE` typically run after auditing.

**Forgetting EnableElasticsearchAuditing.** The entity has auditing annotations, but because auditing infrastructure is not enabled, fields are not updated as expected.

**Omitting AuditorAware when CreatedBy/LastModifiedBy are needed.** Actor fields require an auditor provider.

**Using synchronous callbacks for reactive operations.** Reactive APIs only inspect reactive callbacks. Implement the right callback type.

**Calling the raw Java API Client while expecting Spring Data callbacks to run.** The raw client bypasses Spring Data's entity mapping lifecycle. Invoke equivalent logic in the application layer or use appropriate operations.

**Assuming AfterSave can alter the already-saved document.** The callback runs after persistence. Modifying the returned entity does not re-write the document.

**Using callbacks for side effects requiring transactional guarantees.** Callbacks do not turn Elasticsearch and external systems into a distributed transaction. Use an outbox or durable process for side effects.

**Using lambdas for every callback.** Lambdas lack explicit generic type information compared to generic classes and can reduce domain-type filtering efficiency. Use classes when type filtering matters.

**Relying on generic Spring Data Commons callback examples without checking Elasticsearch support.** Each store module supports a specific set of callbacks. Check the list for your exact version.

## 16. Process for Designing Callback Order

When an application has multiple callbacks:

1. Identify the lifecycle phase requiring intervention.
2. Select a callback interface supported by Spring Data Elasticsearch in your project version.
3. Identify which callbacks depend on the output of other callbacks.
4. Map out the data order—for example: normalize, auditing, build search fields.
5. Assign ascending order values matching dependencies.
6. Use `Ordered` or `Order`; do not declare two conflicting values.
7. Register callbacks in the `ApplicationContext`.
8. Verify callback generic types match the target entities.
9. If using auditing, confirm `EnableElasticsearchAuditing` and an auditor provider.
10. If using reactive operations, implement the corresponding reactive callbacks.
11. Check whether write paths go through Spring Data operations or raw clients.
12. Write tests verifying execution order and final output.

Example `Product` write pipeline:

~~~text
BeforeConvert callback chain
    |
    +-- order 10: normalize name and SKU
    |
    +-- order 100: AuditingEntityCallback
    |
    +-- order 150: build search/audit fields
    |
    v
Convert Product to Document
    |
    v
Persist to Elasticsearch
    |
    v
AfterSave callback chain
~~~

There is no need to create callbacks for every operation. Separate callbacks only when each has a clear, reusable responsibility or requires independent ordering control.

## 17. References

- [Spring Data Elasticsearch - Entity Callbacks](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/entity-callbacks.html): callback lifecycle, callback registration, ordering, and auditing callbacks.
- [Spring Data Elasticsearch API - BeforeConvertCallback](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/event/BeforeConvertCallback.html): signature and invocation timing of `BeforeConvertCallback`.
- [Spring Data Elasticsearch - Auditing](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/auditing.html): enabling auditing and configuring auditors.
- [Spring Framework - Ordered](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/Ordered.html): order value rules and precedence constants.
- [Spring Framework - Order](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/annotation/Order.html): annotation specifying priority order.
- [Spring Data Commons - Entity Callbacks](https://docs.spring.io/spring-data/commons/reference/entity-callbacks.html): callback chains, synchronous/reactive callbacks, and bean registration.

Callback signatures, supported callback interfaces, and auditing details can vary across Spring Data Elasticsearch versions. Check the documentation and Javadoc matching your project's dependencies. The sorting rule remains: smaller order values run first; this order only sorts callbacks within the same lifecycle chain and does not change the order between phases.
