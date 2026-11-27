# Entity Callbacks and Data Processing Checkpoints

Spring Data Elasticsearch provides **entity callbacks** so applications can intervene on an entity at defined points in the data read and write lifecycle. For example, an application can normalize a SKU before converting an entity to JSON, add a field to a document before sending it to Elasticsearch, or enrich an entity after reading the result.

Callbacks attach to specific processing checkpoints: before converting the entity, before saving the document, after saving, and after converting the document back into an entity. Understanding this order helps place logic in the right spot, avoiding modifying data too late or duplicating the same work across multiple layers.

In the same feature group, Spring Data Elasticsearch also provides **mapping events** and **auditing**. Mapping events notify listeners of events during the read/write process; auditing automatically manages fields such as created date, modified date, and actor. They are related, but they do not replace one another.

This article uses the **Product** entity and the **products** index to illustrate checkpoints, callbacks, event listeners, and auditing. Examples focus on modern Spring Data Elasticsearch APIs; detailed signatures can differ between library versions, so verify the dependency version you are using before applying them.

## 1. Entity Lifecycle When Writing to Elasticsearch

When saving an entity through Spring Data Elasticsearch, the application does not send the raw Java object directly. Spring Data converts the entity into a document structure, then sends the document to Elasticsearch.

Basic write flow:

~~~text
Product entity
      |
      v
BeforeConvertCallback
      |
      v
MappingElasticsearchConverter
      |
      v
Document (JSON-like structure)
      |
      v
BeforeSaveCallback
      |
      v
Elasticsearch request
      |
      v
Elasticsearch index
      |
      v
AfterSaveCallback
      |
      v
Result returned to caller
~~~

Each checkpoint has a distinct purpose:

1. **BeforeConvert:** the Java entity is still an object. This is the appropriate time to normalize or populate values on the entity before the converter reads its properties.
2. **Convert:** `MappingElasticsearchConverter` maps the entity into a `Document` based on metadata, annotations, and custom conversions.
3. **BeforeSave:** the document has been created. The callback can inspect or modify the data that will be sent to Elasticsearch.
4. **Save:** Spring Data sends the request to the target index.
5. **AfterSave:** the save operation has completed. The callback can process the entity after writing, such as reflecting updated metadata in the result.

A callback is not a transaction spanning Elasticsearch and other systems. If an error occurs in the after-save callback, the write operation in Elasticsearch may already have succeeded. You should not assume an exception in `AfterSaveCallback` automatically rolls back the newly written document.

## 2. Lifecycle When Reading Data

When reading a document, Spring Data retrieves the data from Elasticsearch and then converts `_source` into a Java entity.

High-level read flow:

~~~text
Elasticsearch response
      |
      v
Document (_source)
      |
      v
AfterLoadEvent (mapping event)
      |
      v
MappingElasticsearchConverter
      |
      v
Product entity
      |
      v
AfterConvertCallback
      |
      v
Entity returned to caller
~~~

At this stage:

- `AfterLoadEvent` notifies that the document has been loaded.
- `MappingElasticsearchConverter` converts fields in the document into Java properties.
- `AfterConvertCallback` receives the newly created entity along with the source document and index coordinates.
- The caller receives the entity after mapping completes.

`AfterConvertCallback` is suitable when you need to populate transient in-memory state or enrich an object after reading. If a value needs to be persisted in Elasticsearch, handle it in the pre-write stage; modifying the entity after conversion does not automatically update the stored document.

A search operation can convert many documents, so the after-convert callback may be invoked for each mapped entity. Avoid placing additional queries or heavy I/O operations inside the callback without evaluating the cost.

## 3. Four Commonly Used Entity Callbacks

Spring Data Elasticsearch provides the following main callbacks:

| Callback | Timing | Key Inputs | Purpose |
|---|---|---|---|
| BeforeConvertCallback<T> | Before the entity is converted to a Document | Entity, IndexCoordinates | Normalize and populate data on the entity |
| BeforeSaveCallback<T> | After conversion, before sending the document | Entity, Document, IndexCoordinates | Inspect or adjust the document about to be saved |
| AfterSaveCallback<T> | After the save operation completes | Entity, IndexCoordinates | Post-write processing |
| AfterConvertCallback<T> | After the document is converted into an entity | Entity, Document, IndexCoordinates | Enrich the entity after reading |

Callbacks are parameterized by entity type. For example, `BeforeConvertCallback<Product>` only handles `Product`; callbacks can be registered separately for each document type.

Callback methods return an entity. Return the modified object, or a new object if using an immutable model. Do not forget to return the entity; a callback is not a listener that merely runs a side effect and discards the result.

## 4. BeforeConvertCallback: Processing the Entity Before Conversion

`BeforeConvertCallback` runs while the data is still a Java object and before Spring Data converts it into a `Document`.

Example normalizing SKU and product name:

~~~java
import java.util.Locale;

import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class ProductBeforeConvertCallback
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product entity,
            IndexCoordinates index) {

        if (entity.getSku() != null) {
            entity.setSku(
                    entity.getSku().trim().toUpperCase(Locale.ROOT)
            );
        }

        if (entity.getName() != null) {
            entity.setName(entity.getName().trim());
        }

        return entity;
    }
}
~~~

In this example:

- The SKU has leading/trailing whitespace trimmed.
- The SKU is uppercased using `Locale.ROOT`, avoiding dependence on the server's locale.
- The product name has excess leading and trailing whitespace removed.
- The entity is returned for the converter to use.

This callback is appropriate for changes belonging to the entity model that need to be reflected in the written document.

### When Should You Not Normalize in BeforeConvert?

Not every value should be modified automatically. For example:

- A display name may need to preserve the casing entered by the user.
- A SKU may be case-sensitive according to source system rules.
- Content may need to be stored verbatim for auditing or reconciliation.
- A value already normalized at the service or domain layer may not need to be normalized again.

Normalization rules should be defined in a single place with clear ownership. If the same field is modified across the controller, service, callback, and converter, it becomes very difficult to know where the final value came from.

## 5. BeforeSaveCallback: Processing the Document Before Writing

`BeforeSaveCallback` runs after the entity has been converted into a `Document`, but before the document is sent to Elasticsearch. The callback receives both the entity and the document, so it can inspect or modify the data structure being written.

Example adding a `normalizedName` field to the document:

~~~java
import java.text.Normalizer;
import java.util.Locale;

import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.event.BeforeSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class ProductBeforeSaveCallback
        implements BeforeSaveCallback<Product> {

    @Override
    public Product onBeforeSave(
            Product entity,
            Document document,
            IndexCoordinates index) {

        if (entity.getName() != null) {
            String normalized = Normalizer
                    .normalize(entity.getName(), Normalizer.Form.NFD)
                    .replaceAll("\\p{M}+", "")
                    .toLowerCase(Locale.ROOT);

            document.put("normalizedName", normalized);
        }

        return entity;
    }
}
~~~

The `normalizedName` field is added to the outgoing document. In this example, the entity is not modified; only the `Document` structure is augmented.

This can be useful when:

- A derived field needs to be written.
- Metadata that does not belong to the domain entity needs to be added.
- The representation needs to be adjusted before sending.
- The document needs to be inspected after the converter has mapped annotations and custom conversions.

If the new field needs to be queried or sorted, the index mapping must declare an appropriate type. Adding a field to `Document` does not automatically guarantee the mapping is configured properly.

### Do Not Use BeforeSave to Replace Domain Logic

If `normalizedName` is an important piece of business data used by multiple systems, consider placing it in the domain model or service so it can be tested independently. `BeforeSaveCallback` fits persistence-related logic; it should not become a container for all `Product` business rules.

Additionally, modifying `Document` in a callback does not necessarily change the entity returned to the caller. If the caller needs to see that derived field, update the model or use an appropriate DTO.

## 6. AfterSaveCallback: Processing After Saving

`AfterSaveCallback` is called after the save operation completes. The callback receives the entity and index coordinates.

Example:

~~~java
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.event.AfterSaveCallback;
import org.springframework.stereotype.Component;

@Component
public class ProductAfterSaveCallback
        implements AfterSaveCallback<Product> {

    @Override
    public Product onAfterSave(
            Product entity,
            IndexCoordinates index) {

        // Perform only lightweight, synchronous, and idempotent processing.
        return entity;
    }
}
~~~

Some use cases to consider:

- Populating transient information on the returned object.
- Recording local metrics.
- Preparing data for the next calling layer.
- Inspecting post-save metadata if supported by the API and entity.

Do not use this callback to send emails, call payment systems, or execute side effects that are not safe to repeat. If Elasticsearch has already saved successfully but the callback fails, the caller may receive an exception even though the document exists.

For side effects requiring high reliability, use an event/outbox or an event publishing mechanism that can retry independently. Do not rely on `AfterSaveCallback` as a transaction coordinator between Elasticsearch and other systems.

## 7. AfterConvertCallback: Enriching the Entity After Reading

`AfterConvertCallback` runs after Spring Data has created the entity from the `Document`. The callback can use both the entity and the source document.

Example adding a temporary display label to `Product`:

~~~java
import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.event.AfterConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class ProductAfterConvertCallback
        implements AfterConvertCallback<Product> {

    @Override
    public Product onAfterConvert(
            Product entity,
            Document document,
            IndexCoordinates index) {

        if (entity.getName() != null
                && entity.getName().isBlank()) {
            entity.setName("Unnamed product");
        }

        return entity;
    }
}
~~~

This example only illustrates the ability to modify an entity after conversion. In practice, if a missing name indicates a schema error, detect and handle it explicitly rather than silently substituting a dummy value.

This callback does not write changes back to Elasticsearch. If you want to fix the stored source, perform a separate update operation. Also avoid querying Elasticsearch inside the callback, because a search returning many hits could trigger many extra requests, causing N+1 queries.

## 8. Registering Callbacks in the Spring Application Context

Callbacks are registered as Spring beans. You can use `@Component` as in the examples above or declare them with `@Bean` in a configuration class.

Example bean declaration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ProductCallbackConfiguration {

    @Bean
    ProductBeforeConvertCallback productBeforeConvertCallback() {
        return new ProductBeforeConvertCallback();
    }
}
~~~

In this example, the callback class needs an appropriate constructor and dependencies if instantiated manually. Do not register the same callback with both `@Component` and `@Bean`, otherwise two beans may be created processing the same entity.

Spring Data uses the application context to find and invoke matching entity callbacks. The callback must be component-scanned or configured as a bean in the context used by the repository/template.

If a callback has dependencies such as `Clock`, a normalization service, or configuration, inject them via the constructor. Avoid instantiating dependencies directly inside the callback, as that makes testing and configuration changes difficult.

## 9. Callback Ordering and @Order

An application can have multiple callbacks of the same type for an entity. For example, one callback normalizes the SKU and another populates a classification field. When order affects the outcome, declare the order explicitly.

~~~java
import org.springframework.core.annotation.Order;

@Component
@Order(10)
public class ProductSkuNormalizationCallback
        implements BeforeConvertCallback<Product> {
    // ...
}

@Component
@Order(20)
public class ProductNameNormalizationCallback
        implements BeforeConvertCallback<Product> {
    // ...
}
~~~

Lower order values have higher precedence in Spring's ordering mechanism. You can use `Ordered` if you want to determine the order programmatically.

Do not rely on accidental bean discovery order. If the second callback assumes the first callback has already run, express that relationship with ordering or combine the logic if they are truly one process.

Avoid splitting a simple change into too many small callbacks. Each callback is a separate persistence step; too many steps make the write flow hard to follow and increase the risk of unintended interactions.

## 10. How Do Mapping Events Differ from Entity Callbacks?

Spring Data Elasticsearch also publishes **mapping events** during data conversion and persistence. Events are usually listened to using `@EventListener` or Spring's listener mechanism.

Common events:

| Event | Processing Checkpoint |
|---|---|
| BeforeConvertEvent | Before the entity is converted into a Document |
| BeforeSaveEvent | Before the Document is sent to Elasticsearch |
| AfterSaveEvent | After the save operation completes |
| AfterLoadEvent | After the Document is loaded from Elasticsearch |
| AfterConvertEvent | After the Document is converted into an entity |

High-level differences:

| Entity callback | Mapping event |
|---|---|
| API parameterized with generic entity type | Application event published in the Spring context |
| Usually returns the processed entity | Listener receives the event and handles side effects |
| Suitable for modifying entity/document in the lifecycle | Suitable for observing, logging, or reacting to checkpoints |
| Invoked directly in the corresponding persistence flow | Can be handled by synchronous or asynchronous listeners |
| Supports callback ordering via @Order/Ordered | Listeners use Spring's own ordering mechanism |

Do not use an event listener to replace a callback if you need to guarantee an entity modification is applied before the converter or request uses the data. Asynchronous event listeners are even less suitable for modifying data needed immediately in the current request.

## 11. Listening to BeforeSaveEvent

Example listener receiving an event before the document is saved:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.data.elasticsearch.core.event.BeforeSaveEvent;
import org.springframework.stereotype.Component;

@Component
public class ProductMappingEventListener {

    @EventListener
    public void onBeforeSave(BeforeSaveEvent<Product> event) {
        Product product = event.getSource();

        // Observe the entity and document about to be written.
        // Use for lightweight logging/metrics; avoid modifying data
        // if logic requires guaranteed ordering with the converter.
    }
}
~~~

`BeforeSaveEvent` provides the source entity, document, and index coordinates according to the Spring Data Elasticsearch API. Depending on the version, you can retrieve the document from the event's corresponding getter.

A listener can record logs, metrics, or observability signals. If you need to modify the entity before conversion, use `BeforeConvertCallback`; if you need to modify the `Document` before sending, use `BeforeSaveCallback`.

Avoid performing synchronous Elasticsearch queries inside a pre-save listener. It can increase latency and cause loops if the listener triggers another persistence operation.

## 12. Event Listeners and Asynchronous Processing

By default, Spring application events are usually processed synchronously in the publishing thread unless the listener is configured as asynchronous. If `@Async` is used, the listener may run after the persistence operation continues or completes.

This affects where logic should be placed:

- Validation that must succeed before writing: use validation/service logic or a synchronous callback.
- Data normalization before conversion: use `BeforeConvertCallback`.
- Adjusting the document before sending: use `BeforeSaveCallback`.
- Recording metrics or observability information: an event listener can be appropriate.
- Sending notifications after saving: use an event/outbox with independent retry handling.

An asynchronous listener cannot guarantee that data modifications will be reflected in the document just sent. Do not place `createdAt` assignment, SKU normalization, or required field population inside an `@Async` listener.

If a listener executes side effects, design it to be idempotent and log failures. In-process published events do not guarantee durable delivery after an application crash.

## 13. What Is Auditing?

**Auditing** automatically records who created or modified an entity and when those actions occurred. Spring Data supports these annotations:

- `@CreatedDate`: creation timestamp.
- `@LastModifiedDate`: last modification timestamp.
- `@CreatedBy`: creator.
- `@LastModifiedBy`: last modifier.

Auditing is typically integrated with Spring Data's internal lifecycle callbacks. As a result, audit fields are updated at the checkpoint before the entity is converted and saved.

Product example:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    private String sku;
    private String name;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant lastModifiedAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String lastModifiedBy;

    // Constructors, getters, and setters.
}
~~~

Use `Instant` to store an absolute point in time, which is usually convenient for system data and cross-server exchange. If the application uses another temporal type, ensure converters and mappings are compatible.

Auditing does not automatically create a history table of all changes. It typically maintains only the current audit fields on the entity. If full history is required, design a separate event log or audit index.

## 14. Enabling Elasticsearch Auditing

You can enable auditing with `@EnableElasticsearchAuditing` in configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.config.EnableElasticsearchAuditing;

@Configuration
@EnableElasticsearchAuditing
public class ElasticsearchAuditingConfiguration {
}
~~~

When you need to record the creator/modifier, provide an `AuditorAware<T>` bean:

~~~java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;

@Configuration
@EnableElasticsearchAuditing
public class ElasticsearchAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorProvider() {
        return () -> Optional.of("system");
    }
}
~~~

Returning `system` is only appropriate for tasks running under a system identity. In a real application, retrieve the current user from the security context or background task context.

If no suitable auditor is available, return `Optional.empty()`. The `createdBy` and `lastModifiedBy` fields may then be left unassigned by auditing.

Do not hard-code a single generic user for all requests if user-level traceability is needed. Also do not read a username from an unauthenticated arbitrary header; the auditor must come from a trusted identity source.

## 15. AuditorAware Retrieving the Current User

A simple example with Spring Security:

~~~java
import java.util.Optional;

import org.springframework.data.domain.AuditorAware;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

@Component
public class SecurityAuditorAware implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || "anonymousUser".equals(authentication.getPrincipal())) {
            return Optional.empty();
        }

        return Optional.of(authentication.getName());
    }
}
~~~

This bean allows auditing to obtain the authenticated principal's name. Check how the application manages anonymous authentication and principal types; in real systems, the principal may be a custom object rather than a `String`.

For scheduled jobs or message consumers, there is no HTTP security context. Set an explicit system identity in the job's execution context or use an auditor provider suited to the task type.

If running a reactive application, do not assume a `ThreadLocal`-based `SecurityContextHolder` will hold the right context across all threads. Use context propagation mechanisms appropriate for the reactive stack and the auditing API of the version in use.

## 16. How Do CreatedDate and LastModifiedDate Work?

Auditing distinguishes creation time from modification time:

- `@CreatedDate` is assigned when the entity is first created and is usually preserved on subsequent updates.
- `@LastModifiedDate` is updated when the entity is saved/modified.
- `@CreatedBy` records the creator.
- `@LastModifiedBy` records the last modifier.

Example when saving `Product` for the first time:

~~~json
{
  "sku": "KB-1001",
  "name": "Mechanical Keyboard",
  "createdAt": "2026-11-13T08:00:00Z",
  "lastModifiedAt": "2026-11-13T08:00:00Z",
  "createdBy": "alice",
  "lastModifiedBy": "alice"
}
~~~

After Alice or another user updates the price:

~~~json
{
  "sku": "KB-1001",
  "name": "Mechanical Keyboard",
  "price": 94.5,
  "createdAt": "2026-11-13T08:00:00Z",
  "lastModifiedAt": "2026-11-13T09:30:00Z",
  "createdBy": "alice",
  "lastModifiedBy": "bob"
}
~~~

`createdAt` and `createdBy` still reflect the initial creation; `lastModifiedAt` and `lastModifiedBy` reflect the latest modification.

Exact behavior also depends on entity metadata and how the application writes data. If a service manually reassigns `createdAt` before every save, auditing cannot repair business semantics already altered by application code.

## 17. Customizing the Time Source

By default, auditing obtains the current time from Spring Data's date/time provider mechanism. When deterministic testing or synchronized time from a shared source is needed, you can provide a suitable `DateTimeProvider`.

Example using `Clock`:

~~~java
import java.time.Clock;
import java.time.temporal.TemporalAccessor;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;

@Configuration
public class AuditTimeConfiguration {

    @Bean
    Clock auditClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider dateTimeProvider(Clock auditClock) {
        return () -> Optional.<TemporalAccessor>of(
                auditClock.instant()
        );
    }
}
~~~

To make auditing use the custom provider, reference the bean via the `dateTimeProviderRef` attribute of `@EnableElasticsearchAuditing` if supported by your version:

~~~java
@EnableElasticsearchAuditing(
        dateTimeProviderRef = "dateTimeProvider"
)
~~~

This approach allows tests to use `Clock.fixed(...)` to verify exact creation/modification times. In production, `Clock.systemUTC()` avoids dependence on the server's local timezone.

Check attribute names and APIs in your specific Spring Data Elasticsearch version. There is no need to customize `DateTimeProvider` if the application has no special time-source or testability requirements.

## 18. Callbacks, Auditing, and Validation Have Different Roles

These mechanisms can participate in the same write flow, but they should maintain proper separation of responsibilities:

| Mechanism | Appropriate Responsibility |
|---|---|
| Domain/service validation | Verify business rules before persistence |
| BeforeConvertCallback | Normalize or populate the entity before conversion |
| BeforeSaveCallback | Adjust the Document before sending |
| Auditing | Populate created/modified dates and actors |
| Mapping event listener | Observe checkpoints or emit signals |
| AfterSaveCallback | Synchronous processing after writing |
| AfterConvertCallback | Enrich the entity after reading |

Examples:

- Empty SKU: validation should reject before writing.
- SKU must be uppercase per storage conventions: `BeforeConvertCallback` can normalize it.
- `createdAt` must be populated automatically: auditing fits.
- Document needs a `schemaVersion` field: `BeforeSaveCallback` can fit if it is persistence metadata.
- Recording metrics after saving: event listener or post-save callback depending on requirements.
- Display name needs locale-specific DTO formatting: usually handled in the service/presentation layer, not necessarily in `AfterConvertCallback`.

Do not turn callbacks into a replacement for the entire service layer. Callbacks should handle rules tied to the persistence lifecycle and apply consistently across read/write paths using Spring Data.

## 19. Which APIs Trigger Callbacks?

Normally, when using Spring Data repositories or the mapping methods of `ElasticsearchOperations`, entity lifecycle callbacks are integrated into the template's processing flow.

Example:

~~~java
productRepository.save(product);
~~~

Or:

~~~java
operations.save(product, IndexCoordinates.of("products"));
~~~

These operations go through the Spring Data mapping layer, where the entity is converted and persistence is orchestrated.

However, do not assume every API named `save`, `bulk`, or `update` invokes the same set of callbacks:

- Repository and `ElasticsearchOperations.save` are the standard entity write paths.
- `UpdateQuery` can send a partial document or script without a full entity to run the entire lifecycle like `save`.
- Bulk APIs can use `IndexQuery`, `UpdateQuery`, or entity objects; callback behavior depends on the overload and version.
- Calling `ElasticsearchClient.index(...)`, `bulk(...)`, or the REST API directly bypasses Spring Data's entity callbacks.
- Calling the converter directly does not automatically mean the full callback lifecycle is executed.

If callbacks or auditing are mandatory requirements, test the actual write paths used by the application, especially bulk imports and the Update API.

## 20. Callbacks Do Not Run Automatically When Using Elasticsearch Java API Client Directly

Example calling the client directly:

~~~java
elasticsearchClient.index(
        request -> request
                .index("products")
                .id(product.getId())
                .document(product),
        Product.class
);
~~~

This is a Java API Client call. It does not go through Spring Data's repository/template lifecycle, so do not expect `BeforeConvertCallback`, `BeforeSaveCallback`, or auditing callbacks to run automatically.

If the application has both write paths:

- Repository/Operations for regular entity operations.
- Direct `ElasticsearchClient` for bulk or low-level features.

then rules that must be applied consistently should be placed in a shared layer or invoked explicitly before sending the request. For example, you can call a shared normalization/validation service, or construct a prepared document before sending via the client.

Do not duplicate callback logic across multiple producers. When rules change, copies can drift and produce inconsistent data.

## 21. Callbacks in Bulk Operations

Bulk ingestion typically processes many entities in a single request to reduce round-trips. This is an area requiring special attention regarding callbacks and auditing.

Depending on the version and API called, a bulk operation may process entities through the converter or send pre-built queries/documents. Therefore, do not assume every callback is invoked once per entity across every bulk path.

Before relying on callbacks to populate audit fields or normalize data in bulk:

1. Identify the exact bulk method being used.
2. Check the implementation/API of your Spring Data Elasticsearch version.
3. Write an integration test with an observable callback.
4. Verify how many times the callback executes and check the values in the actual document.
5. Verify that a bulk item failure does not cause the application to mark the entire batch as succeeded.

If a bulk path does not invoke callbacks as desired, normalize entities before building `IndexQuery` or use a shared ingest pipeline. Do not let auditing depend on unverified behavior.

## 22. Callbacks and UpdateQuery Operations

`UpdateQuery` usually represents a partial document or script, not a complete entity. Example:

~~~java
Document partial = Document.parse("""
{
  "price": 94.5
}
""");

UpdateQuery update = UpdateQuery.builder("p-1001")
        .withDocument(partial)
        .build();

operations.update(
        update,
        IndexCoordinates.of("products")
);
~~~

Here Spring Data sends a partial update. There is no complete `Product` from which to derive `LastModifiedDate` or `LastModifiedBy` values unless the application includes them in the payload.

If auditing is needed when using `UpdateQuery`, add the audit fields to the partial document or script according to defined rules. Example:

~~~json
{
  "doc": {
    "price": 94.5,
    "lastModifiedAt": "2026-11-13T09:30:00Z",
    "lastModifiedBy": "bob"
  }
}
~~~

This is an illustrative payload; the timestamp and user must come from a trusted source in the application. Do not assume entity auditing automatically handles every partial update just because the request is sent through `ElasticsearchOperations`.

If there are multiple write paths, create a unified service or helper to assign audit metadata before building `UpdateQuery`, bulk updates, or Java API Client requests.

## 23. Processing Order and Side Effects

When designing callbacks, identify what data exists at each checkpoint:

| Checkpoint | Entity exists? | Document exists? | Written to Elasticsearch? |
|---|---:|---:|---:|
| BeforeConvert | Yes | Not yet | Not yet |
| After convert | Yes | Yes | Not yet |
| BeforeSave | Yes | Yes | Not yet |
| AfterSave | Yes | Depends on API | Yes, if request succeeded |
| AfterLoadEvent | Source document | Yes | Read from Elasticsearch |
| AfterConvert | Yes | Yes | Read and converted |

A few guidelines:

- Do not read `Document` in `BeforeConvertCallback` because the document has not been created yet.
- Do not assume `BeforeSaveCallback` can modify the entity and automatically change the already-converted `Document`; modify the `Document` if the goal is the outgoing payload.
- Do not assume `AfterSaveCallback` can roll back the write operation.
- Do not write back to Elasticsearch from `AfterConvertCallback` without a loop-prevention mechanism.
- Do not run expensive side effects per hit when reading large lists.

Callbacks should be short, predictable, and testable. If you need to call external services or run long work, move it to an appropriate processing layer.

## 24. Callbacks with Immutable Entities

Entities do not have to use setters. If using an immutable object, the callback can return a new instance containing the normalized values.

Example:

~~~java
public record Product(
        String id,
        String sku,
        String name,
        Instant createdAt,
        Instant lastModifiedAt
) {
    Product withSku(String normalizedSku) {
        return new Product(
                id,
                normalizedSku,
                name,
                createdAt,
                lastModifiedAt
        );
    }
}
~~~

Callback:

~~~java
@Component
public class ProductBeforeConvertCallback
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product entity,
            IndexCoordinates index) {

        if (entity.sku() == null) {
            return entity;
        }

        String normalized = entity.sku()
                .trim()
                .toUpperCase(Locale.ROOT);

        return entity.withSku(normalized);
    }
}
~~~

This example illustrates the idea of returning a new instance. For Spring Data to instantiate an immutable entity when reading, configure constructor/property mapping matching the entity metadata, such as a recognized constructor or `@PersistenceCreator` when multiple constructors exist.

If a callback returns a new object, ensure the ID and required fields are preserved. Do not return an object containing only a subset of properties if the converter or subsequent operations need the remaining fields.

## 25. Avoid Putting Heavy Logic in Callbacks

Callbacks can be invoked frequently:

- Every time an entity is saved.
- Every entity converted in search results.
- In bulk flows depending on the API.
- In synchronization or import jobs running at high volume.

If a callback calls an HTTP service or performs another Elasticsearch query for every entity, latency and system load can grow rapidly.

Example of what not to do:

~~~java
@Override
public Product onBeforeConvert(
        Product entity,
        IndexCoordinates index) {

    PricingInfo info = pricingClient.fetch(entity.getSku());
    entity.setPrice(info.price());

    return entity;
}
~~~

This callback makes a network call on every save. When importing 10,000 products, the application could make 10,000 extra requests and make the write flow unpredictable.

Instead:

- Fetch auxiliary data in the service before calling the repository.
- Batch-load required data.
- Pass computed values into the entity.
- Keep callbacks for lightweight mapping/persistence logic.
- If external synchronization is needed after writing, use events/outbox.

## 26. Testing Callbacks

Callbacks can be tested directly with unit tests without Elasticsearch:

~~~java
@Test
void normalizesSkuBeforeConvert() {
    Product product = new Product();
    product.setSku("  kb-1001 ");

    ProductBeforeConvertCallback callback =
            new ProductBeforeConvertCallback();

    Product result = callback.onBeforeConvert(
            product,
            IndexCoordinates.of("products")
    );

    assertEquals("KB-1001", result.getSku());
}
~~~

For a callback that modifies `Document`:

~~~java
@Test
void addsNormalizedNameToDocument() {
    Product product = new Product();
    product.setName("Mechanical Keyboard");

    Document document = Document.create();

    ProductBeforeSaveCallback callback =
            new ProductBeforeSaveCallback();

    callback.onBeforeSave(
            product,
            document,
            IndexCoordinates.of("products")
    );

    assertNotNull(document.get("normalizedName"));
}
~~~

Unit tests verify isolated callback logic. They do not verify that Spring auto-discovers the callback or invokes it in the right order within the repository/template.

### Integration Tests for the Lifecycle

Use a compatible Elasticsearch instance and a real application context configuration to verify:

1. Saving `Product` via the repository.
2. Confirming `BeforeConvert` normalized the SKU.
3. Confirming `BeforeSave` added the field to `_source`.
4. Reading `Product` via the repository.
5. Confirming `AfterConvert` was called.
6. Confirming auditing populated `createdAt`/`lastModifiedAt`.
7. Updating `Product` and confirming `createdAt` is not unintentionally overwritten.
8. Calling the actual bulk or `UpdateQuery` path and checking whether callbacks/auditing run as required.

You can use a test callback that records execution order into a list or a test spy to observe invocations. Do not inspect only the returned object; read `_source` from Elasticsearch when you need to confirm the final document.

## 27. Common Pitfalls When Using Entity Callbacks and Auditing

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Callback is not invoked | Bean is not in the application context or write path bypasses template | Check component scan and the API being used |
| Callback runs twice | Duplicate bean registration or nested save calls | Check configuration and side effects |
| SKU is normalized but source is unchanged | Callback returned a different object ignored by caller, or handled at wrong checkpoint | Return the entity and verify converter flow |
| Document has new field but returned entity does not | BeforeSave only modifies Document | Update model/DTO if caller needs the field |
| Auditing dates are always null | Auditing not enabled or entity metadata missing annotations | Check `@EnableElasticsearchAuditing` and mapping |
| `createdBy`/`lastModifiedBy` are empty | No `AuditorAware` or context has no user | Configure an appropriate `AuditorAware` |
| Audit user is always `system` | Auditor is hard-coded | Retrieve real principal or job context |
| `UpdateQuery` does not update `lastModifiedDate` | Partial update bypasses auditing entity callback | Add audit fields in `UpdateQuery`/script |
| Bulk does not update audit as expected | Bulk path has different callback semantics | Test actual overload and normalize before bulk |
| `AfterSave` throws an error but document still exists | Exception occurred after writing | Treat post-save callback as a separate step with retry/idempotency |
| Search slows down after adding `AfterConvert` | Callback performs I/O per hit | Remove N+1 calls and keep callback lightweight |
| Event listener modifies data too late | Async listener or wrong lifecycle phase | Use a synchronous callback at the appropriate checkpoint |

## 28. Process for Choosing the Right Checkpoint

When adding logic to the entity lifecycle, determine which data needs to change and when it must take effect:

1. **Need to modify the object before converting to JSON?** Use `BeforeConvertCallback`.
2. **Need to adjust the `Document` structure after the converter?** Use `BeforeSaveCallback`.
3. **Need to process after the write request succeeds?** Use `AfterSaveCallback` or an event depending on requirements.
4. **Need to modify an object just read?** Use `AfterConvertCallback`.
5. **Need to observe read/write events or emit signals?** Use a mapping event listener.
6. **Need to record created/modified dates and users?** Enable auditing.
7. **Need business validation?** Place it in the domain/service layer before persistence.
8. **Need durable post-write side effect handling?** Use an outbox or retryable event mechanism.
9. **Using `UpdateQuery`, bulk, or Java API Client?** Verify that specific API's lifecycle; do not assume callbacks/auditing run automatically.
10. **Need to order multiple callbacks?** Use `@Order` or `Ordered`.

A callback placed at the right checkpoint keeps persistence logic consistent. Placing it at the wrong checkpoint can result in data not being saved, changes missing from the returned object, or side effects occurring after the document has already been stored.

## 29. Design Principles for Callbacks and Auditing

- Use `BeforeConvertCallback` to normalize the entity before the converter runs.
- Use `BeforeSaveCallback` when you need to adjust the generated `Document`.
- Use `AfterSaveCallback` for lightweight post-write processing.
- Use `AfterConvertCallback` to enrich the entity after reading.
- Use mapping events to observe lifecycle checkpoints and emit signals.
- Enable auditing when you need created/modified dates or users.
- Provide `AuditorAware` from a trusted identity source.
- Keep callbacks short, deterministic, and free of per-entity network I/O.
- Declare order with `@Order` when multiple callbacks depend on one another.
- Do not assume callbacks are invoked via direct Java API Client calls.
- Test repository, Operations, bulk, and `UpdateQuery` paths separately.
- Do not treat an `AfterSave` exception as a rollback of the written operation.
- Use an outbox or durable delivery mechanism for critical side effects.
- Keep domain validation in the business layer rather than stuffing all rules into callbacks.

Entity callbacks provide clear extension points in the Spring Data Elasticsearch persistence lifecycle. `BeforeConvertCallback` operates on the entity before conversion; `BeforeSaveCallback` operates on the `Document` before writing; `AfterSaveCallback` runs after saving; `AfterConvertCallback` runs after reading and mapping. Mapping events are suited for observing processing checkpoints, while auditing manages created date, modified date, and actor fields. By placing the right logic in the right stage and verifying each write path individually—such as repository, bulk, `UpdateQuery`, or Java API Client—an application keeps its data consistent and avoids hard-to-control side effects.
