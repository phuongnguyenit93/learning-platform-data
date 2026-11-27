# BeforeConvertCallback for Pre-Conversion Normalization

In Spring Data Elasticsearch, a Java entity is typically converted into a `Document` before being sent to Elasticsearch. Certain normalization rules need to run at this exact moment: trimming excess whitespace, standardizing SKU codes, converting empty strings to `null` by convention, populating derived fields, or ensuring a value conforms to a consistent format before the mapping converter writes the document.

`BeforeConvertCallback` is the extension point for that step. The callback receives the entity and `IndexCoordinates`, and returns the entity after processing. Spring Data invokes the callback before converting the entity into a `Document`, so changes are reflected in the written data.

A callback should contain small, deterministic, and repeatable transformations. It is not the place to handle full business logic, authorize access, call external services, or coordinate transactions. This article explains the lifecycle, how to implement and register the callback, execution order, impact on mutable/immutable entities, limitations with other write paths, and how to test it in Spring Data Elasticsearch.

## 1. Position of BeforeConvertCallback in the Write Flow

Saving an entity through Spring Data typically goes through these high-level steps:

~~~text
Java Entity
    |
    v
BeforeConvertCallback
    |
    v
Mapping converter
    |
    v
Document / JSON source
    |
    v
Index request
    |
    v
Elasticsearch
~~~

For example, a `Product` entity has name `"  Wireless Mouse  "` and SKU `" sku-1001 "`. The callback can trim the name and uppercase the SKU before the converter builds the document.

Only after the callback does the converter process mapping metadata such as `@Id`, `@Field`, data types, nested objects, and custom conversions. Therefore, the callback can normalize entity values before those values are serialized.

`BeforeConvertCallback` is not a post-save callback after Elasticsearch has persisted data, nor does it process search results. If you need to observe or transform data at other checkpoints, Spring Data Elasticsearch provides other callbacks in the lifecycle.

## 2. Callback Contract

In Spring Data Elasticsearch, the synchronous callback typically has this form:

~~~java
public interface BeforeConvertCallback<T> extends EntityCallback<T> {

    T onBeforeConvert(T entity, IndexCoordinates index);
}
~~~

Key types:

- `T`: entity type handled by the callback.
- `entity`: object about to be converted.
- `IndexCoordinates`: index or index coordinates targeted by the write operation.
- Return value: entity used for the subsequent conversion step.

Verify the exact package and signature against the Spring Data Elasticsearch version in your project. In modern versions, callbacks belong to the mapping event/entity callback infrastructure of Spring Data Elasticsearch.

The callback must return an entity. If the callback creates a new object, return that object; modifying an object while returning the old object or `null` can lead to incorrect data or failures in later steps.

### 2.1. Callback Is Part of Entity Conversion

The key point is that the callback is tied to Spring Data's entity-to-document conversion flow. It allows intervention before the converter runs.

It does not automatically intercept every request to Elasticsearch. For instance, an application might write via:

- A Spring Data repository.
- `ElasticsearchOperations`.
- The low-level `ElasticsearchClient`.
- A REST API or another service.
- A bulk request containing raw JSON.

Only write paths that go through Spring Data's entity callback mechanism can trigger the corresponding callback. For bulk APIs, query objects, or low-level clients, inspect the specific call path of the version in use rather than assuming the callback always runs.

## 3. Entity Example and Normalization Rules

Suppose we have the `Product` entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Long)
    private Long priceInCents;

    public Product() {
    }

    // getters and setters
}
~~~

Some normalization rules that can be applied before conversion:

- Trim SKU and name.
- Uppercase SKU using `Locale.ROOT`.
- Normalize `category` according to agreed catalog values.
- Convert empty strings to `null` if the schema allows it.
- Standardize region or country codes into an agreed format.

Do not put pricing rules like "maximum 30% discount" into a callback just because the callback can modify fields. That is a business invariant that belongs in a domain/application service, where sufficient context is available and clear errors can be returned.

## 4. Implementing BeforeConvertCallback

A callback that normalizes SKU and name can be written as follows:

~~~java
import java.util.Locale;

import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class ProductNormalizationCallback
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product product,
            IndexCoordinates index) {

        if (product.getSku() != null) {
            product.setSku(
                product.getSku().trim().toUpperCase(Locale.ROOT)
            );
        }

        if (product.getName() != null) {
            product.setName(product.getName().trim());
        }

        if (product.getCategory() != null) {
            product.setCategory(product.getCategory().trim());
        }

        return product;
    }
}
~~~

When Spring manages the callback bean, the callback can be discovered and invoked by the entity callback infrastructure.

Save example:

~~~java
Product product = new Product();
product.setId("P-1001");
product.setSku(" sku-1001 ");
product.setName("  Wireless Mouse  ");
product.setCategory(" accessories ");

productRepository.save(product);
~~~

The entity is normalized before conversion. The document written to Elasticsearch will contain the SKU and name according to the callback's rules.

The callback above mutates the input object directly. This approach fits simple mutable entities, but consider carefully if the entity is shared across multiple threads or reused after saving.

## 5. Mutable Entities and Immutable Entities

Not every entity has setters. With immutable objects, the callback should create and return a new instance.

Record example:

~~~java
public record Product(
    String id,
    String sku,
    String name,
    String category,
    Long priceInCents
) {
}
~~~

Callback:

~~~java
import java.util.Locale;

import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.mapping.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class ImmutableProductNormalizationCallback
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product product,
            IndexCoordinates index) {

        String normalizedSku = product.sku() == null
            ? null
            : product.sku().trim().toUpperCase(Locale.ROOT);

        String normalizedName = product.name() == null
            ? null
            : product.name().trim();

        String normalizedCategory = product.category() == null
            ? null
            : product.category().trim();

        return new Product(
            product.id(),
            normalizedSku,
            normalizedName,
            normalizedCategory,
            product.priceInCents()
        );
    }
}
~~~

Here, the callback does not mutate the original record; it returns a new record.

When using immutable entities, verify that the mapping converter can instantiate the object from its constructor/record in the Spring Data version you are using. Callbacks do not solve constructor binding issues or mismatched property names.

### 5.1. Should You Always Create a Copy?

There is no mandatory rule to create a new object. The choice depends on the model:

- Mutable entity used within a single operation: mutating directly can be simpler.
- Immutable entity: create a new object.
- Shared or cached object: avoid mutation that could alter state held elsewhere by reference.
- Object reused across multiple indices or multiple requests: prefer side-effect-free transformations.

What matters is that the callback returns a valid entity and does not introduce unpredictable behavior for the caller.

## 6. Safe String Normalization

### 6.1. Use Locale.ROOT for Technical Codes

When normalizing identifiers such as SKUs, country codes, or system codes, use `Locale.ROOT`:

~~~java
String normalized = value.trim().toUpperCase(Locale.ROOT);
~~~

Do not use the machine's default locale for technical codes. Some languages have different case-conversion rules; results could differ across developer machines, containers, and production environments.

For natural display names, do not arbitrarily uppercase or lowercase the entire string unless required by business rules. Normalizing technical codes and normalizing display text are two different tasks.

### 6.2. Empty Strings and Null

A helper can normalize empty strings:

~~~java
private String trimToNull(String value) {
    if (value == null) {
        return null;
    }

    String trimmed = value.trim();
    return trimmed.isEmpty() ? null : trimmed;
}
~~~

The callback can use the helper:

~~~java
product.setName(trimToNull(product.getName()));
~~~

Do this only if the schema and business logic treat empty strings as equivalent to `null`. Some fields need to distinguish "no data provided" from "the user explicitly submitted an empty string".

For `keyword` fields, `null` usually does not produce a regular indexed term. If the mapping defines `null_value`, a substitute value may be indexed for querying while `_source` preserves `null` semantics. Design the mapping and callback together.

### 6.3. Do Not Use Callbacks to Hide Invalid Input

Trimming a string is a mechanical normalization. A malformed SKU, invalid email syntax, or negative price is data that requires validation.

A callback should not silently turn `"abc ???"` into an assumed valid code. If data is invalid, the application service should return an appropriate error before writing.

## 7. Using IndexCoordinates

The callback receives `IndexCoordinates`, so it can know which index the operation targets.

Example:

~~~java
@Override
public Product onBeforeConvert(
        Product product,
        IndexCoordinates index) {

    if (Arrays.asList(index.getIndexNames()).contains("products")) {
        // Apply normalization intended for this index.
    }

    return product;
}
~~~

This example uses `getIndexNames()` to inspect the indices in `IndexCoordinates`; verify the method and `java.util.Arrays` import against your project's API version.

Index information can be used when a single domain type is written to different indices and deliberately needs different handling. However, do not let the callback become an unmanageable matrix of index-name conditionals.

If each index represents a distinct schema, consider separating document models, mappers, or services more cleanly.

## 8. Registering the Callback in Spring

The simplest approach is registering the callback as a Spring bean:

~~~java
@Component
public class ProductNormalizationCallback
        implements BeforeConvertCallback<Product> {
    // implementation
}
~~~

Or via configuration:

~~~java
@Configuration
public class ElasticsearchCallbackConfiguration {

    @Bean
    ProductNormalizationCallback productNormalizationCallback() {
        return new ProductNormalizationCallback();
    }
}
~~~

Do not invoke the callback manually in a service if Spring Data already manages the entity callback infrastructure. Manual invocation can cause double normalization or create inconsistent behavior between repository and Operations flows.

If the callback is not invoked:

- Check whether the class is within component scan scope.
- Check whether the bean is created in the `ApplicationContext`.
- Check whether the callback's generic type matches the exact domain type.
- Check whether the write operation goes through Spring Data entity conversion.
- Check the callback infrastructure of your Spring Data Elasticsearch version.
- Check whether the application customizes or replaces the `EntityCallbacks` bean.

## 9. Multiple Callbacks and Execution Order

An application can have multiple callbacks for the same entity. For example:

- Callback A trims the name.
- Callback B normalizes the SKU.
- Callback C generates `normalizedSearchName`.

If callbacks depend on one another's results, execution order must be explicit. Spring Data's entity callback infrastructure supports ordering via Spring's ordering mechanisms, such as `@Order` or `Ordered`, depending on API and version.

Example:

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class ProductNameTrimCallback
        implements BeforeConvertCallback<Product> {
    // ...
}
~~~

Another callback:

~~~java
@Component
@Order(20)
public class ProductSearchNameCallback
        implements BeforeConvertCallback<Product> {
    // ...
}
~~~

In this example, the callback generating the search name is designed to run after the name-trimming callback.

Do not rely on accidental bean discovery order. If multiple callbacks modify the same field, define the order explicitly and test the final result. When possible, consolidate tightly coupled steps into a single callback with a clear name and responsibility.

Default ordering, callback sorting, and interaction with auditing callbacks can depend on the Spring Data version. Confirm with the API in use and integration tests.

## 10. Callbacks and Other Entity Lifecycle Points

`BeforeConvertCallback` is just one point in the entity lifecycle. Spring Data Elasticsearch has other callbacks for different checkpoints. Exact names and signatures should be checked against your version, but their purposes can be distinguished as follows:

| Lifecycle Point | Purpose |
|---|---|
| BeforeConvert | Modify the entity before the converter creates a Document |
| Pre-save callback (if provided by version) | Intervene close to save time, after conversion |
| AfterSave | Process after the save operation completes |
| AfterLoad | Intervene on the Document after reading from Elasticsearch |
| AfterConvert | Process the entity after the Document is converted into an object |

Examples:

- Normalize SKU before writing: `BeforeConvert`.
- Inspect the generated `Document` representation: pre-save callback checkpoint if supported by the API.
- Log after saving: `AfterSave`.
- Adjust the document after reading: `AfterLoad`.
- Populate transient state on the object after conversion: `AfterConvert` if appropriate.

Do not choose a callback solely by a similar-sounding name. Identify whether data is currently an entity or a `Document`, whether the operation has already happened, and whether the return value will be used further.

## 11. Callbacks and Auditing

Auditing tracks information such as creation time, modification time, and creator/modifier. This is a separate requirement from data normalization.

Spring Data Elasticsearch supports auditing via annotations such as:

~~~java
@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant lastModifiedAt;

@CreatedBy
private String createdBy;

@LastModifiedBy
private String lastModifiedBy;
~~~

Auditing can be enabled through the appropriate Spring configuration, typically `@EnableElasticsearchAuditing`, along with an `AuditorAware` if tracking the actor is needed.

Conceptual configuration example:

~~~java
@Configuration
@EnableElasticsearchAuditing
public class ElasticsearchAuditingConfiguration {
}
~~~

The auditing callback automatically populates auditing fields according to the lifecycle. Do not write a custom `BeforeConvertCallback` just to replace auditing when the framework already provides the mechanism.

If both auditing and a custom callback modify the entity, check their order. For example, a custom callback might normalize a field while auditing updates timestamps. Avoid having a custom callback unintentionally overwrite `createdAt` or `lastModifiedAt`.

Auditing does not replace business audit events. If you need to know who approved an order, what price changed from what to what, or why a change happened, record audit events in your domain/application architecture.

## 12. Callbacks and Validation

A callback can check minimal technical conditions before conversion, but it should not be used as the primary API validation layer.

| Task | Appropriate Place |
|---|---|
| Trim SKU code | BeforeConvertCallback or mapper |
| Uppercase identifiers | BeforeConvertCallback |
| Validate non-negative price per business rules | Application/domain validation |
| Check whether user has permission to edit product | Security/application service |
| Check SKU uniqueness across the system | Domain/application service with appropriate concurrency control |
| Call external tax verification service | Integration/application service |
| Populate createdAt/lastModifiedAt | Auditing |
| Convert source data types | Converter or mapping configuration |

If a callback detects unconvertible data, it can throw an exception to fail the write operation. However, that exception will not automatically turn into a user-friendly validation response for HTTP clients. The application service needs to catch and map errors according to the API contract.

## 13. Things Not to Do in BeforeConvertCallback

Callbacks are typically invoked on the write path and can run very frequently. Avoid:

- Calling external HTTP services or databases per entity.
- Sending emails, webhooks, or messages with side effects.
- Executing multi-step business transactions.
- Checking user permissions without a clear security context.
- Generating random values on every callback execution when idempotency is required.
- Relying on current wall-clock time for business fields without defined rules.
- Mutating an object shared across multiple requests.
- Logging entire entities containing sensitive data.
- Executing nested Elasticsearch queries inside the callback per entity.

I/O operations inside callbacks make the write flow unpredictable, easily cause N+1 requests, and slow down bulk indexing. A callback should be a lightweight, synchronous, and deterministic transformation.

If enrichment from external services is needed, perform it in the application/integration layer before calling Elasticsearch, or use Elasticsearch's enrich index mechanism if reference data and freshness requirements match.

## 14. Do Callbacks Run When Using Repositories and ElasticsearchOperations?

Spring Data's entity-oriented operations such as repository `save` typically go through mapping infrastructure, making them the right paths to check for `BeforeConvertCallback`.

Example:

~~~java
productRepository.save(product);
~~~

Or:

~~~java
operations.save(product);
~~~

However, do not generalize this behavior to every API simply because a method name contains `index` or `bulk`.

| Write Path | Callback Considerations |
|---|---|
| Repository `save(entity)` | Typically goes through Spring Data entity conversion |
| `ElasticsearchOperations.save(entity)` | Entity-oriented path using callbacks |
| `saveAll(entities)` | Check implementation/version and test the actual bulk path |
| `IndexQuery` with object | Verify whether callbacks are invoked in that operation path |
| `UpdateQuery` with `Document` | Do not assume entity callbacks run; this is a partial document update |
| Direct Elasticsearch Java API Client | Bypasses Spring Data callback infrastructure |
| Raw JSON REST/Bulk API | Bypasses Spring Data callback infrastructure |
| Ingest pipeline | Runs on the Elasticsearch side, independent of Java callbacks |

A practical rule: callbacks are not a global interceptor for the cluster. They only apply to operations orchestrated by Spring Data through its callback infrastructure.

If an application uses both repository `save` and a low-level client for bulk import, putting normalization only in a callback can produce two different data outcomes. In that case, move shared transformations into a common mapper, use an ingest pipeline, or ensure all producers enforce the same contract.

## 15. Bulk and Callbacks

Bulk indexing sends multiple documents in one request. There are multiple ways to construct a bulk operation:

- Calling `saveAll(entities)` on a repository.
- Using `ElasticsearchOperations` with entity-oriented operations.
- Building `IndexQuery`/`UpdateQuery`.
- Using the Elasticsearch Java API Client with raw operations.

Callback coverage depends on the specific implementation path. You cannot deduce solely from the fact that the underlying request uses the Bulk API that `BeforeConvertCallback` will definitely be called for every entity.

When a callback is a mandatory part of data integrity, write an integration test against the exact bulk method used in production. You can use a marker field in the test or a spy callback to verify invocation count, then read the indexed document back to verify the data was actually normalized.

For high-volume imports, if normalization must apply consistently across multiple producers, consider a shared mapper or ingest pipeline. Avoid relying on callbacks without testing the import path.

## 16. Reactive Applications and Reactive Callbacks

Spring Data Elasticsearch offers both imperative and reactive APIs. The synchronous `BeforeConvertCallback<T>` should not be treated as an automatic substitute for a reactive callback.

In the reactive stack, Spring Data provides a corresponding reactive callback in supported versions, typically returning `Publisher<T>` instead of returning the entity directly. Interface names, packages, and registration depend on the version.

Some guidelines:

- Use the callback matching the template/repository type in use.
- Do not block reactive threads with synchronous HTTP or database calls.
- If a transformation is pure CPU and lightweight, keep it brief.
- If I/O is needed, perform it in the reactive service chain with explicit timeouts and error handling.
- Write tests using reactive testing tools to verify the callback executes in the proper flow.

Do not register an imperative callback and assume reactive operations will invoke it automatically. Check the documentation and type signatures of `ReactiveElasticsearchOperations` in your actual dependencies.

## 17. Differences Between Callbacks, Converters, and Ingest Pipelines

All three mechanisms can affect data before indexing, but they live in different layers:

| Mechanism | Where It Runs | Suitable For |
|---|---|---|
| BeforeConvertCallback | Spring Data application, before entity conversion | Normalizing Java entities before conversion |
| Mapping converter/custom conversions | Spring Data mapping layer | Mapping between Java types and Document |
| Ingest pipeline | Elasticsearch, when the document is ingested | Shared normalization across multiple producers after requests reach the cluster |

Examples:

- Callback trims SKU in the `Product` entity.
- Converter maps `Money` to an integer number of cents.
- Ingest pipeline normalizes fields from Java services, Logstash, and bulk importers alike.

If the same transformation is implemented in multiple layers, ensure identical semantics. For example, uppercasing SKU in a callback while lowercasing SKU in a pipeline creates unpredictable results across producers.

Choose one canonical source of truth for each rule. Rules tied purely to the Java domain model usually fit mappers/callbacks. Ingest rules shared across multiple producers often fit pipelines.

## 18. Callbacks and Custom Conversions

Custom conversions are used when a Java type needs to be written to or read from a different Elasticsearch representation.

For example, a `Money` type might be stored as cents or a structured object. That is the responsibility of converters/custom conversions, not callbacks.

Callbacks fit when the entity already holds Java types and simply needs value normalization before the converter processes it.

| Need | Mechanism |
|---|---|
| Trim strings before writing | BeforeConvertCallback |
| Convert `Money` to `Long` | Custom writing converter |
| Convert `Long` to `Money` when reading | Custom reading converter |
| Transform document structure shared across multiple producers | Ingest pipeline or schema migration |
| Calculate tax-inclusive price per business policy | Domain/application service |

Do not use a callback to manually serialize JSON or build a `Document` by hand if the mapping converter already handles it properly.

## 19. Impact When Reindexing and Rewriting Data

A callback can run again every time an entity is saved via the Spring Data callback path. Therefore, normalization should be idempotent.

An idempotent transformation satisfies:

~~~text
normalize(normalize(value)) = normalize(value)
~~~

For example, trimming and uppercasing are idempotent:

- `" sku-1001 "` → `"SKU-1001"`
- Running again → still `"SKU-1001"`

By contrast, prepending `"prefix-" + value` is not idempotent if the callback runs multiple times:

- Run 1: `prefix-SKU-1001`
- Run 2: `prefix-prefix-SKU-1001`

If you need a derived field, compute it from the original source field or check state before assigning.

Reindexing via Elasticsearch's Reindex API does not run Java's `BeforeConvertCallback` because data moves directly between indices inside Elasticsearch. If you need to normalize historical data during a reindex, use a destination ingest pipeline or an application job that reads entities and re-saves them via the Spring Data callback path.

## 20. Testing Callbacks

You should have unit tests for the transformation and integration tests verifying that Spring Data actually invokes the callback.

### 20.1. Direct Unit Test

~~~java
@Test
void shouldNormalizeSkuAndName() {
    Product product = new Product();
    product.setSku(" sku-1001 ");
    product.setName("  Wireless Mouse  ");

    ProductNormalizationCallback callback =
        new ProductNormalizationCallback();

    Product result = callback.onBeforeConvert(
        product,
        IndexCoordinates.of("products")
    );

    assertThat(result.getSku()).isEqualTo("SKU-1001");
    assertThat(result.getName()).isEqualTo("Wireless Mouse");
}
~~~

A unit test verifies callback logic. It does not prove that Spring registered the callback or that repository `save` routes through the callback infrastructure.

### 20.2. Integration Test with Spring Context

You can use `@SpringBootTest` with an Elasticsearch test instance or Testcontainers. Save the entity through the exact repository/Operations path used by the application, then read the document back.

Verify:

- The callback bean is created.
- The callback is invoked when saving an entity.
- Values in `_source` are normalized.
- Unrelated fields remain intact.
- Immutable entities return a normalized instance.
- `IndexCoordinates` receives the right index when using dynamic indices.
- Callback order is correct if multiple callbacks exist.

Example assertion after saving and reading back:

~~~java
productRepository.save(product);

Product saved = productRepository.findById("P-1001")
    .orElseThrow();

assertThat(saved.getSku()).isEqualTo("SKU-1001");
assertThat(saved.getName()).isEqualTo("Wireless Mouse");
~~~

If you need to confirm the callback ran before the converter, inspect raw `_source` or use a converter/test spy depending on your test infrastructure. Checking only the original object after `save` may not suffice, especially when the callback creates a new immutable instance that the caller never captures.

### 20.3. Testing the Bulk Path

If production uses `saveAll`, bulk operations, or `IndexQuery`, write separate tests for that exact API. Do not use a single `repository.save` test result to infer callback coverage for all bulk paths.

Tests should verify both the number of times the callback is invoked and the actual `_source` written. If the callback only runs on one write path, provide another shared transformation for the remaining paths.

### 20.4. Testing Idempotency and Nulls

Add tests for:

- Calling the callback twice does not alter the first result.
- Null fields remain null.
- Empty strings are preserved or converted to null according to chosen rules.
- Unicode and technical codes are normalized properly.
- The JVM locale does not affect identifier normalization results.
- Fields outside the callback's scope are untouched.

## 21. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Callback does not run | Bean is not scanned or write path does not use entity callbacks | Check `ApplicationContext` and operation path |
| Callback does not receive expected entity | Incorrect generic type | Declare callback with exact domain type |
| Changes do not appear in document | Callback modified object but returned a different object or wrong instance | Return the normalized entity |
| Immutable entity is not updated | Callback created a new instance but returned the old object | Return the new instance |
| Callback runs twice | Called manually outside Spring or multiple save paths | Remove manual call and inspect lifecycle |
| Value gets duplicated prefix | Non-idempotent transformation | Recompute from source or check before assigning |
| Bulk import is not normalized | Bulk path does not invoke callback | Test exact bulk API; use shared mapper or pipeline |
| Low-level client skips callback | Does not go through Spring Data infrastructure | Normalize before request or use ingest pipeline |
| Two callbacks overwrite each other | Unclear order or modifying the same field | Use ordering and assign one owner per field |
| Callback calling service slows down save | I/O or N+1 inside callback | Move I/O to application service |
| Callback modifies wrong data by index | Logic based on `IndexCoordinates` is too broad | Separate mappers/schemas and test specific indices |
| Auditing fields get overwritten | Custom callback and auditing both modify timestamps | Use auditing for metadata and define order |
| Reactive callback is not called | Used imperative callback for reactive path | Use reactive callback appropriate for version |

## 22. Process for Implementing BeforeConvertCallback

When adding a callback to an application:

1. Identify the domain type and fields needing normalization.
2. Ensure the transformation is technical, deterministic, and idempotent.
3. Keep business validation in the application/domain layer.
4. Write a callback implementing `BeforeConvertCallback<T>`.
5. Choose whether to mutate the entity or return a new instance based on the model.
6. Register the callback as a Spring bean.
7. Define order if multiple callbacks of the same type exist.
8. Verify whether the callback matches the imperative or reactive stack.
9. Test actual write paths: repository, Operations, bulk, and low-level client.
10. Write unit tests and integration tests that read the document back.
11. Check interactions with converters, auditing, and ingest pipelines.
12. Monitor throughput impact if the callback runs for large volumes of entities.

Callbacks should be small, testable, and free of external side effects. If a transformation needs broad context or can fail under business rules, perform it in the application service before calling persistence.

## 23. Quick Reference Table

| Need | Approach |
|---|---|
| Normalize entity before conversion | `BeforeConvertCallback<T>` |
| Trim/uppercase identifiers | Callback or shared mapper |
| Mutable entity | Modify entity then return entity |
| Immutable entity / record | Create and return new instance |
| Know target index | Use `IndexCoordinates` |
| Multiple callbacks on same entity | Use ordering and test execution order |
| Populate created/modified metadata | Spring Data auditing |
| Convert Java type to Document | Mapping converter/custom conversions |
| Normalize for multiple producers | Ingest pipeline or shared mapping service |
| Partial update with raw Document | Check Update API; do not assume callback runs |
| Bulk import | Test exact bulk path |
| Reactive write | Corresponding reactive callback if supported by version |
| Reindex within Elasticsearch | Destination ingest pipeline if normalization needed |
| Call external API or check permissions | Application/integration/security layer |
| Test callback | Unit test and integration test with Spring context |

`BeforeConvertCallback` is the right extension point to normalize an entity immediately before Spring Data Elasticsearch converts it into a `Document`. Keep the callback lightweight, deterministic, and idempotent; return the processed entity properly, use a new instance for immutable entities, and check ordering if multiple callbacks exist. Callbacks only run on write paths going through the entity callback infrastructure, so test the repository, Operations, and bulk paths your application actually uses separately. Auditing, custom conversions, ingest pipelines, and business validation each have distinct responsibilities; choosing the right layer keeps data consistent without turning callbacks into a dumping ground for all application logic.
