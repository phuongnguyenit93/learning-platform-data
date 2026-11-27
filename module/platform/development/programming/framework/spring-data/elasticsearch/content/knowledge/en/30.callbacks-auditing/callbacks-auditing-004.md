# AfterSaveCallback and Post-Save Metadata

In Spring Data Elasticsearch, a save operation often involves more than simply sending a document to Elasticsearch. An application may need to perform extra work after the write operation completes: logging, timing measurements, updating processing status, emitting a signal to another component, or reading metadata received by the persistence layer. Spring Data provides entity callbacks to place logic at defined checkpoints in the entity save lifecycle.

`AfterSaveCallback` is the callback invoked after an entity has been saved via a persistence flow that supports callbacks. It receives the entity and `IndexCoordinates`, then returns the entity. This callback is useful when you need to observe the outcome at the application layer after a save operation.

What must be understood clearly is that `AfterSaveCallback` is not a hook for altering the source that was already saved. When the callback runs, the write operation has already occurred. If the callback modifies a regular field on the entity and returns that entity, the in-memory change is not automatically written back to Elasticsearch. To prepare data before writing, use `BeforeConvertCallback` or `BeforeSaveCallback`. To automatically populate creation/update timestamps, use auditing.

## 1. Entity Callbacks in Spring Data Elasticsearch

An entity callback is an extension point called by Spring Data during a phase of the persistence lifecycle. Instead of having services manually invoke auxiliary functions before or after every operation, the application can register callbacks and let Spring Data invoke them at the right moment.

In Spring Data Elasticsearch, common callbacks include:

| Callback | Timing | Common Purpose |
|---|---|---|
| BeforeConvertCallback | Before the entity is converted into a Document | Prepare or normalize the entity before conversion |
| AfterConvertCallback | After the Document is converted into an entity | Add post-read and post-conversion processing |
| BeforeSaveCallback | Before the Document is sent to be saved | Adjust the entity or Document before writing |
| AfterSaveCallback | After the save operation completes | Observe the entity after save, log, or run post-save tasks |

Verify exact names and signatures against the Spring Data Elasticsearch version in use. In modern versions, imperative callbacks typically parameterize the entity type and receive `IndexCoordinates`.

Callbacks help separate lifecycle logic from business services. However, you should not move all auxiliary tasks into callbacks. Callbacks still reside on the persistence execution path and can affect both execution time and the result returned to the caller.

## 2. What Does AfterSaveCallback Do?

`AfterSaveCallback` represents an action after an entity is saved. Its typical signature in Spring Data Elasticsearch is:

    public interface AfterSaveCallback<T> extends EntityCallback<T> {
        T onAfterSave(T entity, IndexCoordinates index);
    }

The callback receives:

- `entity`: the entity that was just saved.
- `index`: `IndexCoordinates` representing the target index used in the operation.

The callback returns the entity. Spring Data uses a callback chain to pass results between callbacks of the same type and returns the persistence result according to the corresponding API.

A simple implementation:

    @Component
    public class ProductAfterSaveCallback
            implements AfterSaveCallback<Product> {

        private static final Logger log =
            LoggerFactory.getLogger(ProductAfterSaveCallback.class);

        @Override
        public Product onAfterSave(
                Product entity,
                IndexCoordinates index) {

            log.info(
                "Saved product id={} to index={}",
                entity.getId(),
                index.getIndexName()
            );

            return entity;
        }
    }

This callback records the ID and index after saving. It does not need to be invoked manually from `ProductService` if Spring Data recognizes the callback in the application context and the save operation passes through a template/repository supporting entity callbacks.

## 3. Entity Save Lifecycle and the Position of AfterSaveCallback

A typical save flow can be visualized as follows:

    Service calls repository.save(entity)
                  |
                  v
    Spring Data receives entity
                  |
                  v
    BeforeConvertCallback
                  |
                  v
    Convert entity to Document
                  |
                  v
    BeforeSaveCallback
                  |
                  v
    Send index/update request to Elasticsearch
                  |
                  v
    Receive write operation response
                  |
                  v
    Update persistence metadata supported by mapping
                  |
                  v
    AfterSaveCallback
                  |
                  v
    Return entity/result to caller

This is a high-level lifecycle model. Exact ordering between updating ID, version, or other metadata and invoking the callback can depend on the Spring Data version, operation type, and API used. If callback logic relies on specific metadata, verify with an integration test on your actual version.

The core point remains unchanged: `AfterSaveCallback` runs after the save stage. It is suited for observing the outcome of the save operation and running lightweight post-save tasks.

## 4. Registering AfterSaveCallback

In a Spring Boot application, the callback is usually declared as a bean so Spring Data can discover it:

    @Component
    public class ProductAfterSaveCallback
            implements AfterSaveCallback<Product> {

        @Override
        public Product onAfterSave(
                Product entity,
                IndexCoordinates index) {

            // Process after save succeeds.
            return entity;
        }
    }

If using Java configuration:

    @Configuration
    public class ElasticsearchCallbackConfiguration {

        @Bean
        ProductAfterSaveCallback productAfterSaveCallback() {
            return new ProductAfterSaveCallback();
        }
    }

Normally there is no need to invoke the callback manually from a repository or service. Spring Data manages callback execution via its entity callback infrastructure.

If the application constructs `ElasticsearchOperations` or templates manually instead of relying on standard Spring Boot auto-configuration, verify that the template is wired with the appropriate `EntityCallbacks`. A callback bean existing in the context does not guarantee every manually created template will use it.

Do not register the same callback multiple times in the same callback chain. If the same logic is registered in multiple places, a single save can produce duplicate side effects.

## 5. AfterSaveCallback with Entities Having IDs

An entity can have an application-assigned ID or let Elasticsearch generate one on index. Example:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        private String name;
        private Double price;
    }

If the application assigns the ID:

    Product product = new Product();
    product.setId("p-100");
    product.setName("Keyboard K8");

    Product saved = productRepository.save(product);

The callback can log the entity's ID after saving:

    @Override
    public Product onAfterSave(
            Product entity,
            IndexCoordinates index) {

        log.info("Saved id={}", entity.getId());
        return entity;
    }

If the ID is generated by Elasticsearch, Spring Data can populate the returned ID into the `@Id` property and return the entity with its ID according to the `save` API semantics. The exact moment the ID is populated relative to the callback must be confirmed on your version if the callback depends on an auto-generated ID.

Do not generate a new ID inside `AfterSaveCallback` and expect the document to have been written under that ID. If you need an application-controlled ID, generate it before saving. If you need an Elasticsearch-generated ID, use the ID from the entity/save result after persistence completes.

## 6. What Does Post-Save Metadata Include?

Metadata describes the persistence operation or storage state, rather than necessarily being a business field inside the source document.

Common items of interest:

| Metadata | Meaning |
|---|---|
| ID | Document identifier in the index |
| Version | Version used for optimistic locking/versioning if supported by entity and API |
| Sequence number | Write operation sequence number on the shard, usable in concurrency control |
| Primary term | Epoch/term of the primary shard, paired with sequence number in optimistic concurrency |
| IndexCoordinates | Target index used by the operation at the Spring Data layer |
| Result | Operation outcome such as created or updated in Elasticsearch-level responses |
| Shard information | Information about shard copies that handled the operation |
| Refresh information | Refresh-related information if provided by the response/API |

`AfterSaveCallback` only receives the entity and `IndexCoordinates` in its standard callback signature. It does not directly receive the full `IndexResponse` or `BulkResponse`. Therefore, only metadata already mapped by Spring Data onto the entity or available via callback parameters can be read directly here.

If you need low-level response fields such as result, shard details, forced refresh, or sequence number/primary term not exposed by the callback, use an appropriate persistence/client API or a dedicated adapter that retains the response.

## 7. ID and Metadata Are Not the Same as Fields in _source

The ID is normally stored in document metadata (`_id`), not as a regular source field. Spring Data maps the ID to the property annotated with `@Id`.

Example:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        private String name;
    }

The document source might contain only `name`, while the ID is stored in Elasticsearch's metadata.

This matters when writing callbacks:

- `entity.getId()` retrieves the ID mapped by Spring Data.
- `IndexCoordinates` indicates the target index at the Spring Data layer.
- Do not assume the ID also appears inside JSON `_source`.
- Do not write response metadata into `_source` unless it is intentional business data.

If you need to store a business code in `_source` for queries or aggregations, declare a separate field such as `productCode`. Do not use `@Id` as a substitute for every business identifier field.

## 8. @Version and Optimistic Locking

Spring Data Elasticsearch supports version metadata via `@Version` in applicable versions. The version can be used to detect an update based on an outdated document state.

Example:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        @Version
        private Long version;

        private String name;
        private Double price;
    }

When the entity is saved, Spring Data/Elasticsearch can manage the version according to the configured mechanism. The new version can be reflected in the returned entity.

`AfterSaveCallback` can observe the version if the version has already been updated on the entity before the callback is invoked:

    @Override
    public Product onAfterSave(
            Product entity,
            IndexCoordinates index) {

        log.info(
            "Saved id={} version={}",
            entity.getId(),
            entity.getVersion()
        );

        return entity;
    }

Do not manually increment the version inside `AfterSaveCallback`. Version is metadata managed by the persistence engine. Changing the version manually can cause state divergence between the in-memory entity and Elasticsearch.

### Version Is Not Refresh

Versioning and refresh solve two different problems:

- Versioning controls conflicts when multiple writers update the same document.
- Refresh determines when changes become visible to searches.

A document with a new version may still not appear in search results if the shard has not refreshed. Conversely, a searchable document does not mean subsequent updates cannot encounter a version conflict.

## 9. Sequence Number and Primary Term

Elasticsearch uses sequence numbers and primary terms for optimistic concurrency control. When a write succeeds, the shard can return this metadata so the client can use it on the next operation with concurrency conditions.

Concepts:

- Sequence number identifies the operation order on a shard.
- Primary term changes when a primary shard is replaced during failover/election scenarios.
- The pair of sequence number and primary term lets Elasticsearch check whether an update operation is based on the shard state version the client expects.

A low-level response can provide `seq_no` and `primary_term`. However, do not assume `AfterSaveCallback` can always read these two values directly from the entity. Mapping support and annotations depend on the Spring Data Elasticsearch version.

If the application needs to use concurrency tokens:

1. Check whether your Spring Data version supports mapping the corresponding metadata.
2. Identify which metadata the save operation returns.
3. Verify whether the callback runs after metadata has been populated.
4. If detailed responses are needed, use the Elasticsearch Java API Client directly or an adapter returning both the entity and response metadata.
5. Do not infer sequence numbers from version or ID.

Do not confuse `@Version` with `seq_no`/`primary_term`. These are distinct metadata mechanisms, and exact semantics depend on the API being used.

## 10. AfterSaveCallback Does Not Receive IndexResponse

An important characteristic of the callback is that its signature typically contains only the entity and `IndexCoordinates`:

    Product onAfterSave(Product entity, IndexCoordinates index)

It has no `IndexResponse` parameter. Therefore, the callback cannot directly read every field in the Elasticsearch response unless Spring Data populates them onto the entity.

For example, if you need to know whether Elasticsearch reported the operation as `created` or `updated`, a standard callback has no `response.result()` to call.

If a use case requires response details:

- Use the Elasticsearch Java API Client to invoke the index API and receive `IndexResponse`.
- Create a service adapter returning a dedicated result type containing the entity, ID, version, and needed response metadata.
- Keep the response in the persistence layer and publish an application event with selected data.

Do not use reflection or access internal template state to grab responses not exposed by public APIs. That approach depends on internal implementation details and breaks easily on upgrades.

## 11. Example Callback Logging Post-Save Metadata

A callback can log the ID, index, and version:

    @Component
    public class ProductSavedLogCallback
            implements AfterSaveCallback<Product> {

        private static final Logger log =
            LoggerFactory.getLogger(ProductSavedLogCallback.class);

        @Override
        public Product onAfterSave(
                Product entity,
                IndexCoordinates index) {

            log.info(
                "Product persisted: id={}, version={}, index={}",
                entity.getId(),
                entity.getVersion(),
                index.getIndexName()
            );

            return entity;
        }
    }

This callback suits lightweight technical logging. Do not log the entire entity if `_source` contains sensitive information or large payloads.

If logs must serve business auditing, distinguish technical logs of an Elasticsearch operation from an audit trail requiring durability, actor traceability, and transactional guarantees. A simple logging callback does not create a reliable audit system on its own.

## 12. Recording Metrics After Saving

`AfterSaveCallback` can be a place to record metrics for save operations:

    @Component
    public class ProductSaveMetricsCallback
            implements AfterSaveCallback<Product> {

        private final MeterRegistry meterRegistry;

        public ProductSaveMetricsCallback(
                MeterRegistry meterRegistry) {
            this.meterRegistry = meterRegistry;
        }

        @Override
        public Product onAfterSave(
                Product entity,
                IndexCoordinates index) {

            meterRegistry.counter(
                "search.document.saved",
                "entity",
                "product",
                "index",
                index.getIndexName()
            ).increment();

            return entity;
        }
    }

Metrics can help observe save counts by entity type or index. Avoid using document IDs or high-cardinality values as metric tags, as doing so can create too many time series.

If you need to measure the latency of the entire persistence operation, `AfterSaveCallback` only marks a point near the end of the lifecycle. You must also capture the start time before `save` begins in the service or via client instrumentation to obtain the full duration.

## 13. Publishing Events After Saving

Some applications want to publish an event once a document has been saved:

    public record ProductSavedEvent(
        String productId,
        String indexName
    ) {}

Callback:

    @Component
    public class ProductSavedEventCallback
            implements AfterSaveCallback<Product> {

        private final ApplicationEventPublisher publisher;

        public ProductSavedEventCallback(
                ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        @Override
        public Product onAfterSave(
                Product entity,
                IndexCoordinates index) {

            publisher.publishEvent(
                new ProductSavedEvent(
                    entity.getId(),
                    index.getIndexName()
                )
            );

            return entity;
        }
    }

The event in this example is an internal application event. Publishing an event does not guarantee consumers have finished processing it, nor does it establish a distributed transaction between Elasticsearch and a message broker.

If you need to guarantee an event is not lost if the process stops right after a write, design an outbox or durable delivery mechanism at the transactional data source. `AfterSaveCallback` is not a durable message queue.

## 14. Failing Side Effects After the Document Has Been Written

The callback runs after the save operation. If the callback executes a side effect and then throws an exception, the following sequence can happen:

1. Elasticsearch has already saved the document successfully.
2. `AfterSaveCallback` begins.
3. Calling an external system fails.
4. The exception propagates back to the caller.
5. The caller receives an error and may assume the entire save failed.

This is a significant risk. A callback error does not roll back an already-completed Elasticsearch operation.

Example:

    @Override
    public Product onAfterSave(
            Product entity,
            IndexCoordinates index) {

        remoteAuditService.send(entity);
        return entity;
    }

If `remoteAuditService` fails, the caller may receive an exception even though the document exists. If the caller retries the entire save, the operation may run again and side effects may be duplicated.

To reduce risk:

- Keep callbacks short and low-risk.
- Avoid calling high-latency external systems unless truly necessary.
- Design side effects to be idempotent.
- Log errors clearly.
- If side effects must not be lost, use an outbox or durable job/event delivery.
- Explicitly define whether API callers may receive exceptions after a write has already succeeded.

Do not assume a post-save callback can roll back an Elasticsearch write like a relational database transaction.

## 15. Do Not Use AfterSaveCallback to Modify Data That Needs Saving

Suppose you want to generate a slug after saving:

    @Override
    public Product onAfterSave(
            Product entity,
            IndexCoordinates index) {

        entity.setSlug(toSlug(entity.getName()));
        return entity;
    }

The slug changes on the in-memory object, but the index operation already finished before the callback. There is no automatic second write to save the slug.

If the slug must be inside the document, compute it before conversion:

    @Component
    public class ProductBeforeConvertCallback
            implements BeforeConvertCallback<Product> {

        @Override
        public Product onBeforeConvert(
                Product entity,
                IndexCoordinates index) {

            entity.setSlug(toSlug(entity.getName()));
            return entity;
        }
    }

Or use `BeforeSaveCallback` if you need to adjust the `Document` after the entity has been converted.

Distinguish between:

- `BeforeConvertCallback`: modify the entity before conversion.
- `BeforeSaveCallback`: modify the entity or `Document` before writing, depending on version signature.
- `AfterSaveCallback`: process after the write completes.

If `AfterSaveCallback` returns a modified entity, the caller may receive an object that differs from the saved source. That easily causes confusion and should be avoided unless intentional.

## 16. AfterSaveCallback and Auditing

Spring Data Auditing uses annotations such as:

- `@CreatedDate`
- `@LastModifiedDate`
- `@CreatedBy`
- `@LastModifiedBy`

Auditing typically runs before the entity is converted into a document so audit values are written into `_source` during the same save.

Example:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        private String name;

        @CreatedDate
        private Instant createdAt;

        @LastModifiedDate
        private Instant updatedAt;
    }

Enabling auditing in configuration:

    @Configuration
    @EnableElasticsearchAuditing
    public class ElasticsearchAuditingConfiguration {
    }

If the current actor is needed for `CreatedBy` or `LastModifiedBy`, the application can configure `AuditorAware` via Spring Data Auditing.

Auditing and `AfterSaveCallback` have distinct roles:

| Need | Appropriate Mechanism |
|---|---|
| Assign `createdAt` before saving | Auditing / `BeforeConvertCallback` |
| Update `updatedAt` before saving | Auditing / `BeforeConvertCallback` |
| Assign creator or modifier | Auditing with `AuditorAware` |
| Log after save operation | `AfterSaveCallback` |
| Count save operations | `AfterSaveCallback` |
| Publish event after save | `AfterSaveCallback`, with an appropriate delivery policy |
| Add field to `_source` before writing | `BeforeConvertCallback` or `BeforeSaveCallback` |

Do not use `AfterSaveCallback` to assign `@CreatedDate` or `@LastModifiedDate` if you want those values in the newly saved document. By the time the callback runs, `_source` has already been sent.

## 17. Callback Ordering

An application can have multiple callbacks of the same type. Spring Data supports callback ordering via Spring's ordering mechanisms, such as `@Order` or `Ordered`, depending on the callback infrastructure and version.

Example:

    @Component
    @Order(100)
    public class FirstProductAfterSaveCallback
            implements AfterSaveCallback<Product> {

        @Override
        public Product onAfterSave(
                Product entity,
                IndexCoordinates index) {
            return entity;
        }
    }

    @Component
    @Order(200)
    public class SecondProductAfterSaveCallback
            implements AfterSaveCallback<Product> {

        @Override
        public Product onAfterSave(
                Product entity,
                IndexCoordinates index) {
            return entity;
        }
    }

Lower order values usually execute first according to Spring's ordering rules. Verify callback chain semantics in your project's version and do not rely on arbitrary bean discovery order.

If the second callback depends on in-memory data modified by the first callback, the order must be configured explicitly. However, avoid using callback chains to construct complex business pipelines. If steps require tight coordination, service orchestration is usually easier to understand and test.

## 18. Which Operations Does the Callback Apply To?

`AfterSaveCallback` attaches to the save lifecycle executed through Spring Data components integrated with entity callbacks. Do not assume it runs for every operation capable of writing to Elasticsearch.

Distinguish between:

- `repository.save(entity)`
- `ElasticsearchOperations.save(entity)`
- `saveAll`
- `bulkIndex` with a list of `IndexQuery`
- `bulkUpdate`
- `bulkDelete`
- calling the Elasticsearch Java API Client directly
- calling the REST API from another HTTP client

These APIs may take different execution paths. Bulk methods work with query/request objects and might not run the same callback chain as single-entity saves. Direct Java API Client calls do not go through Spring Data's entity callback infrastructure automatically.

If a callback is a mandatory part of your logic, verify each actual write API with integration tests. Do not rely on method names or assume all index operations call `AfterSaveCallback`.

If logic must apply to both single saves and bulk operations, place the shared logic in a service or dedicated component and invoke it explicitly from each write path, or design a unified persistence adapter layer.

## 19. AfterSaveCallback and Delete Operations

`AfterSaveCallback` is for save operations. It is not a post-delete callback.

If post-delete logic is needed, check the corresponding lifecycle callback in your Spring Data Elasticsearch version, such as an after-delete callback if provided by the API in use. If business logic is required upon deletion, the service layer can coordinate explicitly:

    productRepository.deleteById(id);
    eventPublisher.publishEvent(
        new ProductDeletedEvent(id)
    );

This code must be designed with the same considerations for side effects and durability. If delete succeeds but publishing the event fails, the data is already deleted and the event may be lost.

Do not use `AfterSaveCallback` to handle deletions just because the callback name sounds like a general callback for all persistence operations.

## 20. Imperative and Reactive Callbacks

Spring Data Elasticsearch has both imperative and reactive APIs. Do not assume a callback used in an imperative flow can be used as-is in a reactive template.

In the reactive stack, Spring Data provides a corresponding reactive entity callback mechanism in supported versions. The callback can return a `Publisher`/`Mono` rather than a synchronous entity value, and must be composed into the reactive chain.

Conceptual example:

    @Component
    public class ReactiveProductAfterSaveCallback
            implements ReactiveAfterSaveCallback<Product> {

        @Override
        public Publisher<Product> onAfterSave(
                Product entity,
                IndexCoordinates index) {

            return Mono.just(entity);
        }
    }

Verify the exact reactive interface name, package, and signature against your actual Spring Data Elasticsearch version. The example above depicts the reactive callback shape; do not mix `ReactiveAfterSaveCallback` with the imperative `AfterSaveCallback`.

In reactive callbacks:

- Do not call `block()` to wait on an I/O task.
- Do not perform long synchronous side effects on the event loop.
- Return a `Publisher`/`Mono` and compose errors per reactive semantics.
- Keep callbacks stateless and thread-safe.
- Do not subscribe independently inside the callback if the side effect must belong to the same lifecycle.

If the callback calls a reactive service, compose that publisher and return the entity after the side effect completes as required. If only recording a fast metric, a very lightweight synchronous operation may be acceptable depending on the thread model.

## 21. Handling Metadata with a Service Adapter

When more detailed metadata is needed than the callback provides, build an adapter returning a custom persistence result:

    public record ProductSaveResult(
        Product product,
        String id,
        Long version,
        String indexName
    ) {}

Service:

    public ProductSaveResult save(Product product) {
        Product saved = operations.save(product);

        return new ProductSaveResult(
            saved,
            saved.getId(),
            saved.getVersion(),
            IndexCoordinates.of("products").getIndexName()
        );
    }

This example only returns metadata the entity and service already have. If low-level response fields like `result`, shard info, sequence number, or primary term are needed, the adapter must call an API that returns those fields and map them explicitly.

Do not force `AfterSaveCallback` to play the role of a response adapter. Callbacks serve lifecycle purposes; adapters define the result contract for callers.

## 22. Storing Metadata in the Document vs. Keeping It Outside

Not all metadata belongs in `_source`.

Example:

| Information | Usually Stored Where? | Reason |
|---|---|---|
| Business `productId` | Source field if queries/aggregations need it; may also be `_id` | It is domain data |
| `createdAt` | Source field | Business metadata needed for searching or display |
| `updatedAt` | Source field | Business/audit data |
| Elasticsearch version | Persistence metadata/entity mapping | Used for concurrency |
| Sequence number/primary term | Persistence metadata or response adapter | Used for concurrency control |
| Shard response details | Response/logs/metrics | Usually not business data |
| `IndexCoordinates` | Operation context | Not necessarily a source field |
| Request latency | Metrics/observability | Should not be stored back in the newly indexed document |

If you want to store a field such as `indexedAt` in `_source`, determine the timestamp before sending the request and use a pre-save callback or service. You cannot write the exact server-side completion timestamp into the same document via `AfterSaveCallback` without performing an additional write.

## 23. Do Not Automatically Re-Save Inside AfterSaveCallback

An anti-pattern is calling `repository.save` again from inside the callback:

    @Override
    public Product onAfterSave(
            Product entity,
            IndexCoordinates index) {

        entity.setProcessed(true);
        return repository.save(entity);
    }

This can create a loop:

    save
      -> AfterSaveCallback
          -> repository.save
              -> AfterSaveCallback
                  -> repository.save
                      ...

Even if recursion is avoided with flags or conditions, nested saves can generate extra requests, race conditions, and unpredictable states.

If you need to write a different document after saving, coordinate it at the service layer or publish an event with a separate consumer. If you need to alter the document itself before saving, use a pre-save callback.

## 24. Exception Handling and Observability

Callbacks should have a clear error policy:

- Non-critical logging/metric errors can be handled so they do not break the write path, depending on requirements.
- Business errors that must be reported to the caller should be thrown intentionally, while understanding the document may already have been written.
- Event publishing errors should have their own retry/delivery strategy if events are important.
- Do not catch all exceptions and ignore them without recording anything.

An example logging errors only for an auxiliary metric:

    @Override
    public Product onAfterSave(
            Product entity,
            IndexCoordinates index) {

        try {
            metrics.recordSaved(index.getIndexName());
        } catch (RuntimeException ex) {
            log.warn(
                "Could not record save metric for id={}",
                entity.getId(),
                ex
            );
        }

        return entity;
    }

This is only appropriate if the metric is an auxiliary side effect and losing a metric point is not considered a persistence failure. If the metric is a mandatory business requirement, design explicit delivery and retries rather than swallowing exceptions.

Logs should include correlation IDs or job IDs when traceability is needed. Avoid putting full `_source` or sensitive metadata in logs.

## 25. Testing AfterSaveCallback

Verify the callback through a real persistence flow in integration tests whenever logic depends on metadata or lifecycle ordering.

Simple test example:

    @SpringBootTest
    class ProductAfterSaveCallbackTest {

        @Autowired
        ProductRepository repository;

        @Autowired
        ElasticsearchOperations operations;

        @Test
        void callbackRunsAfterSave() {
            Product product = new Product();
            product.setId("p-callback-1");
            product.setName("Keyboard");

            Product saved = repository.save(product);

            assertThat(saved.getId()).isEqualTo("p-callback-1");
        }
    }

If search visibility needs to be verified, the test must refresh or use an appropriate refresh policy. The callback running after `save` does not mean the document is already searchable if the write did not request a refresh.

If the callback records metrics or publishes events, inject a mock or spy for that dependency and verify the callback was invoked once via the persistence path under test.

Scenarios to verify:

- Entity with an application-assigned ID.
- Entity using an auto-generated ID if supported by the use case.
- Entity with `@Version`.
- Callback receives the correct `IndexCoordinates`.
- Multiple callbacks execute in the expected order.
- How callback exceptions affect the caller.
- Whether `save`, `saveAll`, and bulk APIs invoke the callback in your project's version.
- Imperative and reactive callbacks are registered with the right infrastructure.

Do not use a unit test calling `onAfterSave` directly as proof that Spring Data automatically registers and invokes the callback in the repository flow. Unit tests only verify logic inside the callback; integration tests verify lifecycle wiring.

## 26. Checking Your Spring Data Elasticsearch Version

Callback APIs have evolved alongside Spring Data and Elasticsearch client integrations. Before implementing, check:

- The package of `AfterSaveCallback`.
- The `onAfterSave` signature and `IndexCoordinates` type.
- How callbacks are registered in the application context.
- How templates receive `EntityCallbacks` if constructed manually.
- Which callbacks are invoked in `repository.save` and `ElasticsearchOperations.save`.
- Whether `saveAll` and bulk operations traverse the callback chain.
- Which metadata has already been populated on the entity at callback time.
- The reactive callback contract if using reactive templates.

Do not mix examples from older major versions of Spring Data Elasticsearch with the modern Elasticsearch Java API Client. Packages, builders, and callback registration may differ.

If a callback depends on specific metadata, write a small integration test against your resolved dependency version rather than relying on assumptions from a different version.

## 27. Common Pitfalls

### Using AfterSaveCallback to Modify Source

The callback runs after the document has been written. Modifying the entity inside the callback does not automatically re-index it. Use `BeforeConvertCallback` or `BeforeSaveCallback` if a field must be included in `_source`.

### Expecting Callback to Receive IndexResponse

The standard `AfterSaveCallback` signature receives the entity and `IndexCoordinates`. If you need result, shard info, or unmapped response metadata, use a separate API/client adapter.

### Assuming Callback Always Has Complete Metadata

ID, version, or concurrency metadata can only be read if the template populated them on the entity and the mapping/version supports them. Verify the lifecycle per version.

### Confusing @Version with Refresh

Version supports optimistic locking. Refresh controls search visibility. The two mechanisms are independent.

### Using Callback to Populate Audit Fields

`createdAt`/`updatedAt` must be populated before conversion to enter `_source`. Use Spring Data Auditing or a pre-save callback.

### Calling External Services Synchronously in Callback

Slow side effects can lengthen the save request. Side effect failures can cause callers to receive exceptions even though the write succeeded. Use idempotency and an appropriate delivery strategy.

### Calling Save Again from Callback

This can trigger recursion or multiple writes. Coordinate in a service or separate event handler.

### Assuming Bulk Always Invokes Callbacks

Bulk APIs may follow a different execution path than single-entity saves. Verify each API on your actual version.

### Not Managing Callback Ordering

Multiple callbacks of the same type need explicit ordering if dependencies exist. Use `@Order`/`Ordered` when needed and avoid overly complex chains.

### Swallowing Exceptions Without Logging

Side effect failures vanish without a trace and become hard to investigate. Decide which errors can be ignored, which must propagate, and log thoroughly.

### Treating Callback as a Transaction Hook

`AfterSaveCallback` does not create a transaction rollback for Elasticsearch. If durable cross-system delivery is needed, use an outbox or a separate synchronization process.

## 28. Process for Using AfterSaveCallback

When considering an after-save callback, follow these steps:

1. Identify logic that genuinely needs to run after the save operation.
2. If the logic only prepares source fields, move it to `BeforeConvertCallback` or `BeforeSaveCallback`.
3. If the logic assigns created/updated metadata, use auditing.
4. If the logic needs to observe ID/version/index after saving, verify which metadata is exposed on the entity and callback signature.
5. If detailed `IndexResponse` is needed, use an adapter or the Java API Client.
6. Register the callback as a Spring bean and verify the template uses the callback infrastructure.
7. Keep the callback lightweight, stateless, and thread-safe.
8. Design side effects to be idempotent and recognize that the write may have succeeded before the callback fails.
9. Verify callback ordering if multiple callbacks exist.
10. Test `save`, `saveAll`, bulk, and reactive paths separately if the application uses them.
11. Do not use the callback to re-save the same entity or replace transactions/outbox.
12. Measure the callback's impact on write-path latency.

## Conclusion

`AfterSaveCallback` is an entity callback that runs after the save operation in Spring Data Elasticsearch. The imperative callback typically receives the entity along with `IndexCoordinates` and returns the entity to the callback chain. It is suited for logging, metrics, or triggering lightweight post-save work. The entity may already have an updated ID or version depending on lifecycle and version, though the callback does not directly receive the full `IndexResponse`; if result, shard information, or unmapped concurrency metadata is needed, use a dedicated response API or adapter.

Distinguish persistence metadata from fields in `_source`. `@Version` and concurrency metadata serve update control; `@CreatedDate` and `@LastModifiedDate` must be populated before the document is sent, usually via Spring Data Auditing or a pre-save callback. `AfterSaveCallback` does not automatically save entity mutations it makes, cannot roll back a completed write, and is not a transaction/outbox hook. Keep callbacks short, idempotent, properly registered with the template, and verified on your actual Spring Data Elasticsearch version to avoid duplicate side effects or callers receiving errors after a document has already been written.
