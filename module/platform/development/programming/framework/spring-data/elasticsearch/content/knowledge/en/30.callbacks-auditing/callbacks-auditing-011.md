# Limitations of Callbacks and Auditing When Using Scripts, Bulk, or Direct Clients

## 1. Why Might Callbacks and Auditing Not Run for Every Write Operation?

Spring Data Elasticsearch provides entity callbacks and auditing to populate data or transform entities at defined points in the persistence lifecycle. For instance, before saving an order, an application can automatically populate:

- Creation timestamp: `createdAt`.
- Creator: `createdBy`.
- Last modified timestamp: `lastModifiedAt`.
- Last modifier: `lastModifiedBy`.

When an application writes an entity through Spring Data, the framework converts the entity into a document, runs callbacks, applies auditing, and sends the payload to Elasticsearch.

However, not every write operation traverses that entity lifecycle. An application may write using scripts in the Update API, `_update_by_query`, the Bulk API with `UpdateQuery` or JSON actions, `ElasticsearchClient` directly, a REST client, or another service writing to the same index.

Those operations typically work directly with documents or `_source`. They do not necessarily involve a Java object converted by Spring Data. Consequently, Spring Data callbacks and auditing do not run automatically.

This is a critical limitation when designing systems with multiple write paths. Relying solely on `@CreatedDate` and `@LastModifiedDate` can produce complete data when saving through repositories while leaving audit metadata missing when documents are updated by scripts or direct clients.

This lesson explains where callbacks run, which write paths may bypass callbacks, and how to maintain consistent audit metadata when using scripts, bulk operations, or low-level clients.

## 2. Where Do Entity Callbacks Operate?

An entity callback is a hook invoked by Spring Data at a defined checkpoint while processing an entity. A callback receives the entity and returns either the same entity or a modified instance.

Spring Data Elasticsearch uses the `EntityCallback` API for these main checkpoints:

| Callback | Timing | Purpose |
|---|---|---|
| `BeforeConvertCallback` | Before the entity is converted into a `Document` | Normalize data, assign defaults, update fields |
| `AfterSaveCallback` | After the entity is saved successfully via an entity save path | Perform post-save work |
| `AfterLoadCallback` | After reading results from Elasticsearch into a `Document` and before converting | Alter the document before mapping |
| `AfterConvertCallback` | After the document is converted into an entity | Enrich the entity after reading |
| `AuditingEntityCallback` | Before converting the entity | Populate auditing fields such as created date, modified date, and actor |

Callbacks are registered as Spring beans in the `ApplicationContext`. The template retrieves those beans and invokes them at the corresponding checkpoints.

Example pre-convert callback:

~~~java
import org.springframework.data.elasticsearch.core.event.BeforeConvertCallback;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Component;

@Component
public class OrderDefaultsCallback implements BeforeConvertCallback<Order> {

    @Override
    public Order onBeforeConvert(Order order, IndexCoordinates index) {
        if (order.getStatus() == null) {
            order.setStatus("NEW");
        }

        return order;
    }
}
~~~

When an entity save traverses the callback chain, Spring Data calls `onBeforeConvert` before converting the entity into a document. The return value becomes the entity carried forward in processing.

For immutable entities, the callback can return a new instance instead of mutating the original object:

~~~java
@Component
public class OrderDefaultsCallback implements BeforeConvertCallback<Order> {

    @Override
    public Order onBeforeConvert(Order order, IndexCoordinates index) {
        if (order.status() != null) {
            return order;
        }

        return new Order(
            order.id(),
            order.customerId(),
            "NEW",
            order.createdAt(),
            order.lastModifiedAt()
        );
    }
}
~~~

Do not assume callbacks always mutate the input object in place. Always pass forward the entity returned by the callback.

## 3. Callbacks Supported by Elasticsearch

Spring Data Elasticsearch maintains a module-specific list of callbacks tied to its lifecycle. Common callbacks include:

| Interface | Method | Purpose |
|---|---|---|
| `BeforeConvertCallback<T>` | `onBeforeConvert(T, IndexCoordinates)` | Modify entity before conversion |
| `AfterSaveCallback<T>` | `onAfterSave(T, IndexCoordinates)` | Process entity after saving |
| `AfterLoadCallback<T>` | `onAfterLoad(Document, Class<T>, IndexCoordinates)` | Modify document after loading |
| `AfterConvertCallback<T>` | `onAfterConvert(T, Document, IndexCoordinates)` | Process entity after conversion |
| `AuditingEntityCallback` | `onBeforeConvert(Object, IndexCoordinates)` | Populate audit metadata |

`AuditingEntityCallback` is an internal callback registered by the auditing infrastructure. It is invoked during the pre-conversion step.

Do not mechanically assume callback names from Spring Data JPA or Spring Data MongoDB exist in Elasticsearch. Each store has its own lifecycle and callback set. Check the API of the Spring Data Elasticsearch version you are using.

### Registering Callbacks

Callbacks can be registered with `@Component`:

~~~java
@Component
public class ProductCallback implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product product,
            IndexCoordinates index) {

        product.setNormalizedName(
            product.getName().trim().toLowerCase()
        );

        return product;
    }
}
~~~

Or registered with `@Bean`:

~~~java
@Configuration
public class ElasticsearchCallbackConfiguration {

    @Bean
    BeforeConvertCallback<Product> productCallback() {
        return (product, index) -> {
            product.setStatus(
                product.getStatus() == null ? "ACTIVE" : product.getStatus()
            );
            return product;
        };
    }
}
~~~

Spring Data templates integrate with `ApplicationContext` to discover callback beans. If constructing a template manually or replacing `EntityCallbacks`, ensure the default auditing callback remains configured in the chain.

### Execution Order

Callbacks can implement `Ordered` or use `@Order` to specify execution order. Lower order values run first.

`AuditingEntityCallback` has order `100`. Custom callbacks can be ordered before or after it depending on requirements.

Example callback normalizing data before auditing runs:

~~~java
@Component
@Order(50)
public class NormalizeOrderCallback implements BeforeConvertCallback<Order> {

    @Override
    public Order onBeforeConvert(Order order, IndexCoordinates index) {
        order.setCode(order.getCode().trim().toUpperCase());
        return order;
    }
}
~~~

If a subsequent callback alters an audit field, it can overwrite what auditing just set. Therefore, avoid having multiple callbacks manage the same field without explicit ordering rules.

## 4. Auditing in Spring Data Elasticsearch

Auditing automatically records who created or updated an entity and when the action occurred.

Common annotations:

| Annotation | Meaning |
|---|---|
| `@CreatedDate` | Creation timestamp of the entity |
| `@CreatedBy` | Creator of the entity |
| `@LastModifiedDate` | Latest update timestamp |
| `@LastModifiedBy` | Latest modifier |

Entity example:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "orders")
public class Order {

    @Id
    private String id;

    private String customerId;

    private String status;

    @CreatedDate
    @Field(type = FieldType.Date)
    private Instant createdAt;

    @CreatedBy
    @Field(type = FieldType.Keyword)
    private String createdBy;

    @LastModifiedDate
    @Field(type = FieldType.Date)
    private Instant lastModifiedAt;

    @LastModifiedBy
    @Field(type = FieldType.Keyword)
    private String lastModifiedBy;

    // Constructors, getters, and setters
}
~~~

These fields live as metadata inside the document. When auditing runs, Spring Data updates their values before the entity is converted and sent.

### Enabling Auditing

Auditing must be enabled with a configuration annotation:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.config.EnableElasticsearchAuditing;

@Configuration
@EnableElasticsearchAuditing
public class ElasticsearchAuditingConfiguration {
}
~~~

If the entity uses `@CreatedBy` or `@LastModifiedBy`, the application must provide an `AuditorAware` so Spring Data knows who is executing the operation.

Example:

~~~java
import java.util.Optional;

import org.springframework.data.domain.AuditorAware;
import org.springframework.stereotype.Component;

@Component("auditorAware")
public class SecurityAuditorAware implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        return Optional.of("system");
    }
}
~~~

In a real application, the value should come from `SecurityContext` or the request's user context. The example above uses a fixed string to demonstrate the interface structure.

You can reference the bean explicitly:

~~~java
@Configuration
@EnableElasticsearchAuditing(auditorAwareRef = "auditorAware")
public class ElasticsearchAuditingConfiguration {
}
~~~

If only created/updated dates are used, `AuditorAware` is unnecessary. If multiple `AuditorAware` beans with different data types exist, configure `auditorAwareRef` to select the right bean.

### Choosing Time

By default, auditing uses the current time via `CurrentDateTimeProvider`. To synchronize clocks or run deterministic tests, provide a custom `DateTimeProvider`.

This is especially useful when multiple services write to the same index. If services use different clocks, timestamps can drift. A UTC convention and unified clock source keep data reconcilable.

## 5. Distinguishing Creation vs. Update Timestamps

Auditing must know whether an entity is new or existing to handle `createdAt` and `lastModifiedAt` appropriately.

In Elasticsearch, the presence of an ID is not enough to identify a new entity. A new entity may have an application-assigned ID before saving. Accordingly, Spring Data Elasticsearch documentation recommends implementing `Persistable<ID>` to supply `isNew()` logic.

Example:

~~~java
import org.springframework.data.domain.Persistable;

@Document(indexName = "orders")
public class Order implements Persistable<String> {

    @Id
    private String id;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant lastModifiedAt;

    @Override
    public String getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return id == null || createdAt == null;
    }
}
~~~

This is merely an illustrative rule. In real systems, choose an `isNew()` condition matching your entity lifecycle and legacy data. For instance, if an older document lacks `createdAt` due to a migration, the condition above could classify it as new upon re-saving.

Do not use ID as the sole condition if the application permits client-side or pre-assigned ID generation.

## 6. Callbacks and Auditing When Using save(entity)

The regular entity save path via `ElasticsearchOperations.save(entity)` is the clearest path for callbacks and auditing to run.

High-level flow:

~~~text
ElasticsearchOperations.save(entity)
              |
              v
      BeforeConvertCallback
              |
              v
      AuditingEntityCallback
              |
              v
       Mapping / Conversion
              |
              v
        Index API request
              |
              v
         AfterSaveCallback
~~~

Execution order among `BeforeConvertCallback` beans depends on their order values. The auditing callback runs at order `100`.

Example:

~~~java
@Service
public class OrderService {

    private final ElasticsearchOperations operations;

    public OrderService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Order create(Order order) {
        return operations.save(order);
    }
}
~~~

When auditing is enabled, the entity has proper metadata, and the callback chain is registered, audit fields are updated before the document is saved.

The repository save path uses the same Spring Data infrastructure:

~~~java
public interface OrderRepository
        extends ElasticsearchRepository<Order, String> {
}
~~~

~~~java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public Order create(Order order) {
        return repository.save(order);
    }
}
~~~

Repositories do not implement a separate auditing mechanism; they use the template-backed Spring Data persistence path.

## 7. Do Callbacks Run When Using saveAll or Bulk Index?

Do not assume every bulk operation skips callbacks. You must distinguish the type of bulk operation and how requests are constructed.

### saveAll(entities)

Repository `saveAll(entities)` and `ElasticsearchOperations.save(Iterable)` are entity save paths. Spring Data constructs `IndexQuery` instances from entities and performs bulk indexing.

In the current template implementation:

- `save(entity)` invokes `BeforeConvertCallback` before building the index request.
- `save(Iterable)` creates `IndexQuery` instances from the entities.
- The bulk operation calls a helper processing callbacks for each `IndexQuery` holding an entity object.
- After the bulk request completes, `AfterSaveCallback` is invoked for the corresponding entities.

Therefore, when using the entity save path via `saveAll` or `save(Iterable)`, callbacks and auditing can execute for each entity before the bulk request is sent.

Example:

~~~java
List<Order> orders = List.of(order1, order2, order3);

Iterable<Order> saved = orderRepository.saveAll(orders);
~~~

This remains a Spring Data entity save path. There is no need to manually populate audit fields merely because the underlying transport uses the Bulk API.

### bulkIndex with IndexQuery Containing an Entity Object

Spring Data provides `IndexQuery` to describe an index operation. If `IndexQuery` wraps an entity object, the template can invoke callbacks for that object.

Example:

~~~java
IndexQuery indexQuery = new IndexQueryBuilder()
    .withId(order.getId())
    .withObject(order)
    .build();

operations.bulkIndex(
    List.of(indexQuery),
    IndexCoordinates.of("orders")
);
~~~

On this path, `withObject(order)` tells the template which entity to process. `BeforeConvertCallback` and `AfterSaveCallback` can be invoked through the bulk helper.

### bulkIndex with Pre-Built Document or JSON

If `IndexQuery` contains only a pre-built document and no entity object, Spring Data has no entity to pass to callbacks.

Example:

~~~java
IndexQuery indexQuery = new IndexQueryBuilder()
    .withId("order-100")
    .withSource("""
        {
          "status": "NEW",
          "createdAt": "2026-11-13T10:00:00Z"
        }
        """)
    .build();
~~~

In this case, the template sends the prepared document directly. There is no Java entity for `AuditingEntityCallback` to populate metadata on.

If full audit metadata is needed, add the fields before building the JSON/`Document` or switch to the entity save path.

### bulkUpdate with UpdateQuery

`bulkUpdate(List<UpdateQuery>)` is a document update path. `UpdateQuery` describes an update payload or script, not an entity undergoing conversion.

The template's callback helper handles entity objects inside `IndexQuery`; it does not automatically run auditing for an `UpdateQuery` containing a partial document or script.

Therefore, do not assume:

~~~java
operations.bulkUpdate(updateQueries, Order.class);
~~~

automatically updates `lastModifiedAt` and `lastModifiedBy` for each order. Include audit fields inside the update payload or script.

### Bulk Summary Table

| Write Path | Entity Callbacks / Auditing | Notes |
|---|---|---|
| `repository.saveAll(entities)` | Yes, via entity save path | Entities processed before bulk indexing |
| `operations.save(Iterable)` | Yes, via entity save path | Creates `IndexQuery` from entities |
| `bulkIndex(IndexQuery with object)` | Possibly yes | Callback helper requires an entity object |
| `bulkIndex(IndexQuery with Document/JSON only)` | No entity for callbacks | Prepare audit fields manually |
| `bulkUpdate(List<UpdateQuery>)` | Does not automatically run auditing for update payloads/scripts | Include audit fields in the update |
| Direct Bulk API | No | Handle metadata in each action manually |

The key takeaway is that seeing the word `bulk` is insufficient to tell whether callbacks run. Check whether the bulk operation goes through the entity save path or sends pre-built documents/update actions.

## 8. update(entity) Is Not the Same as save(entity)

An easily overlooked detail is that `ElasticsearchOperations.update(entity)` does not necessarily traverse the same callback chain as `save(entity)`.

In the template implementation, updating an entity converts it into an `UpdateQuery` holding a partial document. This path does not run the same `BeforeConvertCallback` and `AfterSaveCallback` helper as entity saves.

Example:

~~~java
operations.update(order);
~~~

Do not assume this call automatically updates:

- `lastModifiedAt`.
- `lastModifiedBy`.
- Normalized values added by `BeforeConvertCallback`.
- Business fields computed by callbacks.

If auditing is needed for updates, you can:

1. Use `save(entity)` if business rules allow overwriting the full entity.
2. Update audit fields manually before building `UpdateQuery`.
3. Use a script and pass timestamp and actor via params.
4. Create a shared update service so every update flow applies consistent rules.

Choosing an update strategy must account for the risk of overwriting fields the request did not intend to change. Do not replace a partial update with a full save if the in-memory entity could be stale compared to the indexed document.

## 9. Scripts in the Update API Bypass Auditing Callbacks

Elasticsearch's Update API lets Painless scripts run directly on documents.

Example incrementing view count:

~~~http
POST /products/_update/p-100
{
  "script": {
    "lang": "painless",
    "source": "ctx._source.viewCount += params.increment",
    "params": {
      "increment": 1
    }
  }
}
~~~

Elasticsearch executes the script against the current `_source` and re-indexes the result. This request does not send a Java entity through a Spring Data converter. Therefore:

- `BeforeConvertCallback` is not called automatically.
- `AuditingEntityCallback` is not called automatically.
- `AfterSaveCallback` is not called automatically.
- `@LastModifiedDate` and `@LastModifiedBy` annotations do not apply automatically.

If a script must maintain audit metadata, update those fields inside the same script.

Example:

~~~http
POST /orders/_update/order-100
{
  "script": {
    "lang": "painless",
    "source": """
      ctx._source.status = params.status;
      ctx._source.lastModifiedAt = params.updatedAt;
      ctx._source.lastModifiedBy = params.actor;
    """,
    "params": {
      "status": "APPROVED",
      "updatedAt": "2026-11-13T10:15:30Z",
      "actor": "user-42"
    }
  }
}
~~~

The timestamp and actor are supplied from the application via params. This is a clean way to audit a scripted update.

Do not hard-code users or timestamps inside script source. Passing values via params keeps the script source stable and maximizes compiled script reuse.

## 10. Scripts in _update_by_query

`_update_by_query` updates multiple documents matching a query. The script operates directly on each document's `ctx._source`.

Example updating status and audit metadata for pending orders:

~~~http
POST /orders/_update_by_query?conflicts=proceed
{
  "query": {
    "term": {
      "status": "PENDING"
    }
  },
  "script": {
    "lang": "painless",
    "source": """
      ctx._source.status = params.newStatus;
      ctx._source.lastModifiedAt = params.updatedAt;
      ctx._source.lastModifiedBy = params.actor;
    """,
    "params": {
      "newStatus": "EXPIRED",
      "updatedAt": "2026-11-13T10:15:30Z",
      "actor": "scheduler"
    }
  }
}
~~~

This request does not instantiate Java entities for each document. Spring Data auditing callbacks are not invoked per updated document.

If the script must preserve `createdAt` and `createdBy`, do not reassign those fields inside the update script. Only update metadata for the current modification.

Example script setting `createdAt` when missing while always updating `lastModifiedAt`:

~~~json
{
  "script": {
    "lang": "painless",
    "source": """
      if (ctx._source.createdAt == null) {
        ctx._source.createdAt = params.updatedAt;
        ctx._source.createdBy = params.actor;
      }

      ctx._source.lastModifiedAt = params.updatedAt;
      ctx._source.lastModifiedBy = params.actor;
    """,
    "params": {
      "updatedAt": "2026-11-13T10:15:30Z",
      "actor": "migration-job"
    }
  }
}
~~~

This is an example for a migration with specific rules. With production data, check legacy documents, missing fields, and audit policies before running across the whole index.

### Variables in Update Scripts

Update scripts can use:

| Variable | Meaning |
|---|---|
| `ctx._source` | Content of the document being updated |
| `ctx._id` | Document ID |
| `ctx._index` | Index name |
| `ctx._version` | Current version |
| `ctx._routing` | Document routing |
| `params` | Parameters passed by the request |
| `ctx.op` | Selects action: `index`, `noop`, or `delete` |

Update-by-query has its own Painless context. Do not assume every variable from the Update API exists in the update-by-query context. When timestamp or actor is needed, passing them via `params` from the application is clearest.

`_update_by_query` requires `_source` to be enabled so scripts can modify document contents. It can encounter version conflicts if documents change mid-request; specify `conflicts=proceed` only when business rules allow skipping conflicting documents and you have a plan to handle them.

## 11. Scripts in the Bulk API

The Bulk API can contain `index`, `create`, `update`, or `delete` actions. For update actions, a script can be supplied:

~~~http
POST /orders/_bulk
{"update":{"_id":"order-101"}}
{"script":{"source":"ctx._source.lastModifiedAt = params.updatedAt; ctx._source.lastModifiedBy = params.actor","params":{"updatedAt":"2026-11-13T10:15:30Z","actor":"user-42"}}}
{"update":{"_id":"order-102"}}
{"script":{"source":"ctx._source.lastModifiedAt = params.updatedAt; ctx._source.lastModifiedBy = params.actor","params":{"updatedAt":"2026-11-13T10:15:30Z","actor":"user-42"}}}
~~~

These actions are processed directly by Elasticsearch. Spring Data has no entity object on which to run auditing callbacks.

If a bulk request uses `index` actions with pre-built sources, audit fields must be present in the source before sending. If a bulk request uses `update` actions with scripts, the script must update audit fields.

When a batch spans multiple actors, do not apply one shared actor across the entire batch. Each action must carry the actor matching its operation, or the application should partition batches by actor.

## 12. Direct Client Access via ElasticsearchClient

Spring Data Elasticsearch 6.x uses the Elasticsearch Java API Client. The template exposes `execute(ClientCallback)` to perform operations directly on the client while retaining exception translation.

Example:

~~~java
import co.elastic.clients.elasticsearch.core.IndexResponse;

IndexResponse response = elasticsearchTemplate.execute(client ->
    client.index(i -> i
        .index("orders")
        .id(order.getId())
        .document(order)
    )
);
~~~

This path invokes the client directly. It does not traverse `ElasticsearchOperations.save(entity)`, so it does not automatically execute:

- `BeforeConvertCallback`.
- `AuditingEntityCallback`.
- `AfterSaveCallback`.

Using the template merely to supply the client does not route raw client calls back into the entity lifecycle.

Similarly, if an application injects `ElasticsearchClient` and calls `client.index(...)`, `client.update(...)`, or `client.bulk(...)` directly, Spring Data callbacks do not run automatically.

### Can Direct Clients Still Use Converters?

Applications can inject `ElasticsearchConverter` to convert an entity into a `Document` or `Map` before sending via the direct client. That lets you reuse Spring Data's mapping annotations and conversion rules.

However, a converter is not the entity callback chain. Converting an entity alone does not execute auditing callbacks.

If you must use the direct client while still preserving audit metadata, the application must:

1. Call a service or helper responsible for applying audit metadata.
2. Convert the entity with the converter if needed.
3. Send the document using `ElasticsearchClient`.
4. Inspect the response and handle write errors.

Do not assume using the same converter means auditing has executed.

## 13. Write Paths and Callback Limitations

The following table helps choose the right write path when auditing is active:

| Write Path | Spring Data Mapping/Conversion | Entity Callbacks | Automatic Auditing |
|---|---|---|---|
| `repository.save(entity)` | Yes | Yes | Yes, if enabled |
| `operations.save(entity)` | Yes | Yes | Yes, if enabled |
| `repository.saveAll(entities)` | Yes | Yes via entity save path | Yes, if enabled |
| `operations.save(Iterable)` | Yes | Yes via `IndexQuery` with object | Yes, if enabled |
| `operations.bulkIndex(IndexQuery with object)` | Yes for object | Possibly yes | Possibly yes |
| `operations.bulkIndex(Document/JSON)` | Uses pre-built data | No entity for callbacks | Not automatic |
| `operations.update(entity)` | Converts to `UpdateQuery` | Bypasses save callback chain | Not automatic |
| `operations.bulkUpdate(UpdateQuery)` | Uses update payload/query | Not automatic | Not automatic |
| `_update` with script | Elasticsearch processes `_source` | No | No |
| `_update_by_query` with script | Elasticsearch processes each document | No | No |
| Direct Bulk API | Client handles request | No | No |
| Direct `ElasticsearchClient` | Client handles request | No | No |
| REST client or external service | Outside Spring Data | No | No |

This table reflects typical execution paths in Spring Data Elasticsearch. An application can invoke callbacks manually or add audit metadata itself, but that requires explicit application code.

## 14. Maintaining Audit Metadata in Scripts

A simple rule for update scripts:

- `createdAt` and `createdBy` are populated only when the document is first created or when a migration backfills missing data.
- `lastModifiedAt` and `lastModifiedBy` are updated on every business modification.
- Actors must come from an authenticated identity or an explicit system identity.
- Timestamps must come from a unified clock, typically UTC.
- Never let clients supply arbitrary actors if identity spoofing is possible.

Example script updating status:

~~~java
String script = """
    ctx._source.status = params.status;
    ctx._source.lastModifiedAt = params.updatedAt;
    ctx._source.lastModifiedBy = params.actor;
    """;

Map<String, Object> params = Map.of(
    "status", "APPROVED",
    "updatedAt", Instant.now().toString(),
    "actor", currentUserId
);
~~~

The application passes the script and params to the Update API or Bulk Update action.

Even when calling a stored script saved in Elasticsearch, still pass actor and timestamp via params. Stored scripts have no automatic visibility into the application's current user.

### Do Not Overwrite createdAt on Update

Inappropriate example:

~~~painless
ctx._source.createdAt = params.now;
ctx._source.lastModifiedAt = params.now;
~~~

The script above alters creation time as well, destroying audit meaning.

Better approach:

~~~painless
ctx._source.lastModifiedAt = params.now;
ctx._source.lastModifiedBy = params.actor;
~~~

Only set `createdAt` and `createdBy` during document creation or an intentional backfill procedure.

## 15. Building a Shared Audit Helper

If the system has multiple write paths, centralize audit rules into a shared service or helper so different places do not diverge.

Example:

~~~java
import java.time.Clock;
import java.time.Instant;

import org.springframework.stereotype.Component;

@Component
public class AuditMetadataFactory {

    private final Clock clock;
    private final CurrentActorProvider actorProvider;

    public AuditMetadataFactory(
            Clock clock,
            CurrentActorProvider actorProvider) {
        this.clock = clock;
        this.actorProvider = actorProvider;
    }

    public AuditMetadata forUpdate() {
        return new AuditMetadata(
            Instant.now(clock),
            actorProvider.currentActor()
        );
    }
}
~~~

Audit DTO:

~~~java
import java.time.Instant;

public record AuditMetadata(
    Instant modifiedAt,
    String modifiedBy
) {
}
~~~

Such a helper can be used by:

- Custom callbacks.
- Services building `UpdateQuery`.
- Services constructing bulk actions.
- Scripted updates.
- Direct client write flows.

Example when building `UpdateQuery`:

~~~java
AuditMetadata audit = auditMetadataFactory.forUpdate();

Map<String, Object> update = new HashMap<>();
update.put("status", "APPROVED");
update.put("lastModifiedAt", audit.modifiedAt());
update.put("lastModifiedBy", audit.modifiedBy());

UpdateQuery updateQuery = UpdateQuery.builder(orderId)
    .withDocument(Document.from(update))
    .build();
~~~

This example illustrates injecting audit metadata into a partial update. The exact `Document` factory method may differ depending on your Spring Data Elasticsearch API version.

Crucially, all write paths share one actor source and clock, preventing individual controllers from generating ad-hoc timestamps or guessing users.

## 16. Using Ingest Pipelines for Shared Metadata

Elasticsearch ingest pipelines can populate or normalize certain fields before a document is indexed.

Example pipeline adding an ingest timestamp:

~~~http
PUT /_ingest/pipeline/add-ingest-time
{
  "processors": [
    {
      "set": {
        "field": "ingestedAt",
        "value": "{{{_ingest.timestamp}}}"
      }
    }
  ]
}
~~~

Pipelines can be invoked from Index or Bulk APIs via the `pipeline` parameter.

Ingest pipelines are useful for shared metadata such as ingestion timestamps, string normalization, source tagging, field conversions, and normalizing document shapes.

However, `ingestedAt` is not necessarily the same as `lastModifiedAt`. Ingest time is when Elasticsearch processes the document through the pipeline; modified time is when business data changed.

Pipelines also have no built-in knowledge of the application's current user. If `createdBy` or `lastModifiedBy` is needed, the application must pass the actor in the document or request through a trusted mechanism.

You can combine pipelines with scripts or audit helpers, provided you clearly define which source is authoritative for each field.

## 17. Differences Between Synchronous and Reactive Callbacks

Spring Data separates synchronous and reactive callbacks.

- Synchronous APIs use `BeforeConvertCallback`, `AfterSaveCallback`, and corresponding synchronous callbacks.
- Reactive APIs use `ReactiveBeforeConvertCallback`, `ReactiveAfterSaveCallback`, and corresponding reactive callbacks.

A synchronous callback does not run automatically inside a reactive template. Conversely, a reactive callback does not replace a synchronous callback.

Reactive callback example:

~~~java
import org.reactivestreams.Publisher;
import org.springframework.data.elasticsearch.core.event.ReactiveBeforeConvertCallback;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class ReactiveOrderCallback
        implements ReactiveBeforeConvertCallback<Order> {

    @Override
    public Publisher<Order> onBeforeConvert(
            Order order,
            IndexCoordinates index) {

        order.setStatus(
            order.getStatus() == null ? "NEW" : order.getStatus()
        );

        return Mono.just(order);
    }
}
~~~

Reactive auditing must be enabled with `@EnableReactiveElasticsearchAuditing` and use `ReactiveAuditorAware` when auditor fields are present.

Configuration example:

~~~java
@Configuration
@EnableReactiveElasticsearchAuditing
public class ReactiveAuditingConfiguration {
}
~~~

Do not register a synchronous callback expecting it to run in `ReactiveElasticsearchTemplate`. Implement the exact callback type matching your API.

## 18. Callbacks and ApplicationEvent Are Not the Same

Spring Data Elasticsearch supports entity callbacks as well as certain store-specific application events.

Entity callbacks are designed to run sequentially at defined checkpoints in the processing chain. Callbacks can return a modified entity.

`ApplicationEvent` flows through `ApplicationEventMulticaster`. If the application configures an asynchronous event multicaster, event handling can occur on a different thread and no longer guarantee ordering relative to synchronous persistence.

Therefore, for logic that must modify an entity before conversion or before writing, use `EntityCallback` rather than relying on an asynchronous event listener.

Example:

~~~java
@Component
public class NormalizeProductCallback
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product product,
            IndexCoordinates index) {

        product.setName(product.getName().trim());
        return product;
    }
}
~~~

Do not use an event listener to assign audit fields and assume the document is guaranteed to be updated before the template serializes the entity if the event multicaster might execute asynchronously.

## 19. Callbacks Are Not Transactions or Immutable Audit Mechanisms

Entity callbacks help enforce logic along a Spring Data processing path. They do not establish a distributed transaction between the application and Elasticsearch, nor do they provide an immutable audit log.

Key limitations:

- Callbacks only run when the execution path actually traverses the callback chain.
- Scripts or direct clients can bypass callbacks.
- Another service can write documents without enforcing the current application's audit rules.
- `AfterSaveCallback` does not turn a write request into a transaction spanning external systems.
- Audit fields stored inside documents can be overwritten if another writer breaks the rules.
- Callbacks do not replace event sourcing or an append-only audit log system when business rules demand tamper-proof history.

If you need to know every change made to a document over time, keeping only `lastModifiedAt` and `lastModifiedBy` is insufficient. Those two fields reflect only the latest update. Consider storing separate events or audit records to retain full history.

## 20. Testing Callbacks and Auditing

Test write paths with and without callbacks separately.

### Testing Save via Repository

~~~java
@Test
void shouldPopulateAuditFieldsWhenSavingEntity() {
    Order order = new Order();
    order.setStatus("NEW");

    Order saved = repository.save(order);

    assertThat(saved.getCreatedAt()).isNotNull();
    assertThat(saved.getLastModifiedAt()).isNotNull();
    assertThat(saved.getCreatedBy()).isEqualTo("test-user");
    assertThat(saved.getLastModifiedBy()).isEqualTo("test-user");
}
~~~

Tests must configure an auditor and auditing infrastructure. In Elasticsearch integration tests, if searching immediately after writing, use an appropriate refresh policy or wait for searchability intentionally.

### Testing Scripted Updates

After running a scripted update, verify both business fields and audit metadata:

~~~java
@Test
void shouldUpdateAuditMetadataInScriptedUpdate() {
    // Index an order with existing createdAt and createdBy.

    // Run update script with updatedAt and actor in params.

    // Read document back by ID and assert:
    // - status changed
    // - createdAt remained unchanged
    // - createdBy remained unchanged
    // - lastModifiedAt updated
    // - lastModifiedBy matches actor
}
~~~

This test verifies the script maintains metadata itself rather than expecting callbacks.

### Testing Bulk

Write dedicated tests for:

- `saveAll(entities)`.
- `bulkIndex(IndexQuery with object)`.
- `bulkIndex(Document/JSON)`.
- `bulkUpdate(UpdateQuery)`.
- Direct Bulk API.

Expected outcomes must reflect each write path. For example, `saveAll` using the entity lifecycle can be audited automatically; bulk updates using scripts must write audit fields explicitly.

### Testing Direct Clients

If a service calls `ElasticsearchClient` directly, tests should verify audit metadata was added before the request was sent. Never stop at checking that the callback bean exists in the `ApplicationContext`.

## 21. Common Pitfalls

**Assuming every write operation runs callbacks.** Callbacks only run when the call path traverses Spring Data's entity lifecycle. Scripts and raw clients do not trigger callbacks automatically.

**Assuming saveAll skips callbacks because it uses the Bulk API.** `saveAll` is a Spring Data entity save path and can invoke callbacks per entity. Distinguish it from bulk updates or raw bulk requests.

**Assuming bulkUpdate automatically updates LastModifiedDate.** `UpdateQuery` is not an entity lifecycle save. Send audit fields inside the partial document or script.

**Assuming update(entity) equals save(entity).** Update builds an `UpdateQuery` and does not necessarily run `BeforeConvert`/auditing callbacks. Check the specific API before expecting auditing.

**Assuming converters run auditing automatically.** Converters only translate data per mappings. Entity callbacks are a separate step in the template.

**Assuming execute(ClientCallback) still triggers callbacks.** `execute` exposes the raw client. Operations directly on the client bypass entity callbacks.

**Using @LastModifiedDate without enabling auditing.** Annotations only declare metadata. Enable `@EnableElasticsearchAuditing` to register auditing infrastructure.

**Using @CreatedBy without an AuditorAware.** Spring Data cannot resolve the current actor unless the application provides an auditor source.

**Not detecting new entities accurately.** IDs may already be assigned before saving. Consider `Persistable.isNew()` and existing audit fields.

**Letting custom callbacks overwrite audit fields.** Check callback ordering and avoid multiple components managing the same field.

**Using a synchronous callback for reactive APIs.** The reactive stack has separate callbacks and separate auditing configuration.

**Treating ingestedAt as lastModifiedAt.** Ingestion time and business modification time have distinct meanings.

**Overwriting createdAt inside update scripts.** Update only last-modified fields during regular updates. Preserve creation metadata.

**Taking the actor from the request body.** Actors must come from authenticated identities or trusted sources so users cannot spoof modifiers.

**Assuming callbacks create an immutable audit log.** Document fields can be overwritten later. When tamper-proof history is required, use separate audit records or event logs.

## 22. Designing Consistency Across Multiple Write Paths

When an index has multiple write paths, design audit rules before implementation:

1. Identify audit fields to store: created time, created actor, modified time, modified actor.
2. Identify trusted actor sources for user requests, jobs, and internal services.
3. Choose a clock source and timestamp convention, typically UTC.
4. Enable Spring Data auditing for entity save paths.
5. Define `AuditorAware` or `ReactiveAuditorAware` if actors are needed.
6. Verify `isNew()` logic when entities have pre-assigned IDs.
7. Use callbacks for transformations needed before converting entities.
8. For `saveAll`, check whether the call is an entity save path or raw bulk.
9. For `UpdateQuery`, scripted updates, and update-by-query, pass audit metadata explicitly.
10. For direct `ElasticsearchClient` or REST clients, apply an audit helper before sending requests.
11. Preserve creation metadata on updates.
12. Test every write path individually; never infer bulk/script behavior from single-entity save tests.
13. When multiple systems write to the index, standardize the audit contract or route through an authoritative ingest/service layer.
14. If full change history is required, emit separate audit events instead of relying solely on last-modified fields.

Implementation diagram:

~~~text
                 +---------------------+
                 |    Audit policy     |
                 | Actor + Clock + Rule|
                 +----------+----------+
                            |
             +--------------+---------------+
             |              |               |
             v              v               v
       Spring Data       Script / Bulk    Direct Client
       save / saveAll    UpdateQuery      ElasticsearchClient
             |              |               |
             v              v               v
       EntityCallback   Params + Script   Audit helper
       AuditingCallback
             |              |               |
             +--------------+---------------+
                            |
                            v
                    Elasticsearch index
~~~

The goal is for every write path to obey the same audit rules, regardless of execution mechanism.

## Conclusion

Spring Data Elasticsearch entity callbacks and auditing operate within the entity processing lifecycle. `BeforeConvertCallback` and `AuditingEntityCallback` can enrich data before an entity is converted into a document; `AfterSaveCallback`, `AfterLoadCallback`, and `AfterConvertCallback` serve their respective checkpoints.

`save(entity)`, `saveAll(entities)`, and bulk index paths carrying entity objects can pass through the callback chain. However, `UpdateQuery`, scripts in the Update API, `_update_by_query`, manually built bulk actions, and direct `ElasticsearchClient` operations do not automatically execute auditing callbacks. Using `ElasticsearchConverter` alone also does not mean auditing was executed.

When using scripts, bulk updates, or direct clients, pass timestamps and actors explicitly via params or an audit helper, preserve creation metadata, and update last-modified metadata. If multiple writers exist, standardize actor sources, clocks, and audit rules so data stays consistent across every write path. When an immutable change history is needed, store dedicated audit events separately rather than relying only on document fields.

## References

- [Spring Data Elasticsearch — Entity Callbacks](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/entity-callbacks.html)
- [Spring Data Elasticsearch — Auditing](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/auditing.html)
- [Spring Data Commons — Auditing](https://docs.spring.io/spring-data/elasticsearch/reference/data-commons/auditing.html)
- [Spring Data Elasticsearch — Elasticsearch Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — AuditingEntityCallback API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/event/AuditingEntityCallback.html)
- [Spring Data Elasticsearch — EnableElasticsearchAuditing API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/config/EnableElasticsearchAuditing.html)
- [Spring Data Elasticsearch — ElasticsearchTemplate API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/client/elc/ElasticsearchTemplate.html)
- [Elasticsearch — Update API](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/update-document)
- [Elasticsearch — Update by query API](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/update-by-query-api)
- [Elasticsearch — Update by query Painless context](https://www.elastic.co/docs/reference/scripting-languages/painless/painless-update-by-query-context)
- [Elasticsearch — Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk)
