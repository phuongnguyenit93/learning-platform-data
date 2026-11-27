# Distinguishing Direct Dual Write, Outbox, and CDC

An application often stores business data in a relational database while also sending data to Elasticsearch for search. The key question is: how do you ensure both places stay consistently updated when the network fails, a process stops mid-flight, or a message is redelivered?

There are three common approaches:

- **Direct dual write**: the service calls writes to the database and Elasticsearch in the same execution flow.
- **Transactional outbox**: the service writes business data and an event record in the same database transaction; another process forwards the event to Elasticsearch.
- **Change Data Capture (CDC)**: a system reads the database transaction log to detect changes and turns them into events or index records.

These three approaches differ in complexity, latency, and consistency guarantees. Spring Data Elasticsearch is typically the layer that writes projections into Elasticsearch; it does not automatically create a distributed transaction between Elasticsearch and the business database.

## 1. Why Synchronize the Database with Elasticsearch?

Suppose an application manages products. The relational database stores the official state, while Elasticsearch serves search by name, description, category, and filters.

A record in the database:

~~~json
{
  "id": 1001,
  "name": "Wireless Keyboard",
  "price": 1299000,
  "status": "PUBLISHED",
  "version": 42
}
~~~

The Elasticsearch document can be designed for querying:

~~~json
{
  "productId": "1001",
  "name": "Wireless Keyboard",
  "price": 1299000,
  "status": "PUBLISHED",
  "category": "ACCESSORIES",
  "aggregateVersion": 42
}
~~~

The two structures do not need to match:

- The database is optimized for transactions and business data constraints.
- Elasticsearch is optimized for full-text search, filtering, sorting, and aggregations.
- An Elasticsearch document can combine data from multiple tables.
- Elasticsearch mappings and analyzers can differ from the database structure.

Therefore, Elasticsearch typically acts as a **read model or search projection** built from source data. When the database changes, the projection must be updated accordingly.

## 2. The Atomicity Problem When Writing to Two Places

Suppose a service executes:

~~~java
@Transactional
public void publishProduct(Product product) {
    productRepository.save(product);
    elasticsearchOperations.save(toDocument(product));
}
~~~

At first glance, both calls are inside a `@Transactional` method. However, a Spring Data JPA transaction does not automatically wrap an Elasticsearch write into a distributed transaction capable of atomically committing or rolling back alongside the database.

Several situations can occur:

| Sequence | Failure | Possible resulting state |
|---|---|---|
| Database writes first | Elasticsearch fails | Database committed, search index not updated |
| Elasticsearch writes first | Database rolls back | Search index contains data not accepted by the database |
| Both writes succeed | Response to client is lost | Client may retry and resend the operation |
| Process stops between the two calls | Second call never ran | The two stores diverge |
| Elasticsearch times out | Unclear whether server wrote it | Retry may write duplicates or overwrite newer data |

This is the **atomicity gap**: the two systems have independent storage and commit mechanisms. Putting a transaction annotation on the service does not automatically turn them into a single transaction.

Distributed transactions can be used in certain architectures, but Elasticsearch and relational databases do not inherently participate in the same transaction manager the way JPA transactions typically work. For search projections, outbox or CDC is usually easier to operate.

## 3. Direct Dual Write

Direct dual write is when the service actively writes to the database and Elasticsearch within the same processing flow.

For example:

~~~java
@Service
public class ProductService {

    private final ProductRepository productRepository;
    private final ElasticsearchOperations elasticsearchOperations;

    public ProductService(
            ProductRepository productRepository,
            ElasticsearchOperations elasticsearchOperations
    ) {
        this.productRepository = productRepository;
        this.elasticsearchOperations = elasticsearchOperations;
    }

    @Transactional
    public Product publish(Product product) {
        product.setStatus("PUBLISHED");

        Product saved = productRepository.save(product);

        ProductDocument document = toDocument(saved);
        elasticsearchOperations.save(document);

        return saved;
    }
}
~~~

The service can return the result after both operations finish. This approach is easy to understand and can fit small systems where low latency matters and the application has clear divergence-handling mechanisms.

However, if Elasticsearch fails after the database has committed, the database transaction does not automatically roll back that commit. If Elasticsearch succeeds before the database commits and then the database rolls back, the search index can hold unaccepted state.

### Advantages

- Few infrastructure components.
- Easy-to-follow code flow.
- Can respond to the user after attempting to update both stores.
- Suitable for small systems or cases where Elasticsearch is a reproducible projection.

### Limitations

- No atomic commit across both systems.
- Business requests depend on Elasticsearch availability if waiting for synchronous writes.
- Retries and timeouts can create duplicates or overwrite newer data.
- Recovery logic tends to scatter across services.
- When multiple services write concurrently, preserving update ordering is harder.

Never treat dual write as consistent simply because two statements are written next to each other in the same method.

## 4. Dual Write Variants

### Write Database Then Write Elasticsearch

~~~text
Client
  |
  v
Application
  |
  +----> Database commit
  |
  +----> Elasticsearch index
  |
  v
Response
~~~

If the database commit succeeds but Elasticsearch fails, the application must record the pending sync state and retry later. Without retries or reconciliation, the document can drift indefinitely.

### Write Elasticsearch Then Write Database

~~~text
Client
  |
  v
Application
  |
  +----> Elasticsearch index
  |
  +----> Database commit
  |
  v
Response
~~~

If Elasticsearch succeeds but the database rolls back, the search projection may display data that does not exist in the authoritative source.

### Parallel Writes

~~~java
Mono.zip(
        saveDatabaseReactive(product),
        saveElasticsearchReactive(toDocument(product))
);
~~~

Parallel writes reduce sequential waiting time, but do not solve atomicity. One publisher can succeed while the other fails. When `zip` emits an error, side effects already completed in the other branch are not automatically rolled back.

Do not choose parallel writes solely to lower latency without a policy for handling partial success.

## 5. When Is Dual Write Acceptable?

Dual write can be a reasonable choice if:

- Elasticsearch data can be regenerated from the primary source.
- Short-term inconsistency is acceptable.
- A retry queue or reconciliation mechanism exists.
- Load and writer count are still small.
- It is acceptable for the business request to fail or report a pending sync status.

If the search index must be updated before returning a response, the service can write to the database first, then write to Elasticsearch and return an error or pending status when sync fails. Keep in mind, however, that the database has already committed and returning an error may cause the client to retry. Stable IDs and idempotency remain necessary.

Do not use dual write for data with strict consistency requirements without a recovery mechanism, such as balances or payment status. Elasticsearch should generally not be the place deciding financial transactions when the business database is the source of truth.

## 6. What Is the Transactional Outbox?

Transactional outbox solves the problem where an application needs to update a database and emit an event, but cannot commit two independent systems in one transaction.

Instead of having the service write directly to the database and then call Elasticsearch, the service performs two operations within the **same database transaction**:

1. Update the business table.
2. Insert a record into the outbox table describing the change to publish.

If the transaction commits, both the business change and the outbox record are persisted together. If it rolls back, both roll back.

A relay process reads the outbox and forwards events to a message broker or directly to Elasticsearch.

~~~mermaid
flowchart LR
    A["Application service"] --> B["Database transaction"]
    B --> C["Business table"]
    B --> D["Outbox table"]
    D --> E["Outbox relay / CDC"]
    E --> F["Message broker"]
    F --> G["Elasticsearch consumer"]
    G --> H["Search projection"]
~~~

The key point is that the database only needs to guarantee atomicity between two writes inside the database itself. Publishing the event externally happens asynchronously and can be retried.

## 7. Designing the Outbox Table

An outbox table can contain:

~~~sql
CREATE TABLE outbox_event (
    event_id          VARCHAR(100) PRIMARY KEY,
    aggregate_type    VARCHAR(100) NOT NULL,
    aggregate_id      VARCHAR(150) NOT NULL,
    aggregate_version BIGINT,
    event_type        VARCHAR(150) NOT NULL,
    schema_version    INTEGER NOT NULL,
    payload           TEXT NOT NULL,
    occurred_at       TIMESTAMP NOT NULL,
    published_at      TIMESTAMP NULL
);
~~~

Meaning:

| Field | Purpose |
|---|---|
| `event_id` | Unique identifier of the event, used for deduplication |
| `aggregate_type` | Entity type, e.g. Product |
| `aggregate_id` | Business entity ID |
| `aggregate_version` | Change version of the aggregate |
| `event_type` | Event name, e.g. ProductPublished |
| `schema_version` | Payload structure version |
| `payload` | Event content or data needed to build the projection |
| `occurred_at` | Time when the business event occurred |
| `published_at` | Time when the relay confirmed publication, if polling is used |

Some implementations also include `headers`, `tenant_id`, `trace_id`, `correlation_id`, attempt count, and processing status.

Not every outbox needs the exact same schema. What matters is having a stable event ID, aggregate identity, event type, payload, and version/schema matching how consumers process them.

## 8. Writing Business Data and Outbox in the Same Transaction

Example outbox entity using JPA:

~~~java
@Entity
@Table(name = "outbox_event")
public class OutboxEventEntity {

    @Id
    private String eventId;

    private String aggregateType;
    private String aggregateId;
    private Long aggregateVersion;
    private String eventType;
    private Integer schemaVersion;

    @Lob
    private String payload;

    private Instant occurredAt;

    // Constructors, getters and setters
}
~~~

Service:

~~~java
@Service
public class ProductApplicationService {

    private final ProductRepository productRepository;
    private final OutboxEventRepository outboxRepository;
    private final ObjectMapper objectMapper;
    private final Clock clock;

    public ProductApplicationService(
            ProductRepository productRepository,
            OutboxEventRepository outboxRepository,
            ObjectMapper objectMapper,
            Clock clock
    ) {
        this.productRepository = productRepository;
        this.outboxRepository = outboxRepository;
        this.objectMapper = objectMapper;
        this.clock = clock;
    }

    @Transactional
    public Product publish(long productId) {
        Product product = productRepository.findById(productId)
                .orElseThrow();

        product.publish();
        product.increaseVersion();

        Product saved = productRepository.save(product);

        ProductPublished event = new ProductPublished(
                saved.getId(),
                saved.getVersion(),
                saved.getName(),
                saved.getPrice(),
                clock.instant()
        );

        outboxRepository.save(
                OutboxEventEntity.from(
                        event.eventId(),
                        "Product",
                        String.valueOf(saved.getId()),
                        saved.getVersion(),
                        "ProductPublished",
                        1,
                        serialize(event),
                        clock.instant()
                )
        );

        return saved;
    }

    private String serialize(Object event) {
        try {
            return objectMapper.writeValueAsString(event);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                    "Cannot serialize outbox event",
                    ex
            );
        }
    }
}
~~~

This is an illustrative example. `ProductRepository` and `OutboxEventRepository` must share the same transaction manager and database. If the two repositories use two separate datasources or two independent transaction managers, atomicity is no longer guaranteed by `@Transactional` alone.

If event serialization fails, the transaction must roll back so business state is not saved without its corresponding outbox event.

## 9. Outbox Relay via Polling

One way to implement a relay is to periodically read unpublished events:

~~~sql
SELECT *
FROM outbox_event
WHERE published_at IS NULL
ORDER BY occurred_at
LIMIT 100;
~~~

The relay sends events to Kafka or another message broker, then marks `published_at`.

Flow:

~~~text
Outbox table
    |
    v
Poll unpublished events
    |
    v
Publish to broker
    |
    v
Mark published
~~~

In a multi-instance relay setup, a claim/lock mechanism is needed so two workers do not redundantly process the same batch. You can use row locking, leases, or a processing status column depending on the database.

Avoid holding a long database transaction while waiting on network broker calls whenever possible. A common design claims a short batch in one transaction, publishes outside the transaction, and marks completion in another transaction. This pattern must handle expired leases and redelivered events.

### The Gap Between Publishing and Marking

An important scenario:

1. The relay publishes the event successfully.
2. The process crashes before updating `published_at`.
3. The relay restarts.
4. The event is still seen as unpublished and gets published again.

Therefore, polling outbox typically provides at-least-once delivery. Consumers must tolerate duplicates and process idempotently.

If you mark published before publishing, the process could crash after marking and before sending, causing the event to be lost. Therefore, prioritize not losing events and design consumers to handle duplicates.

## 10. Outbox Combined with CDC

An outbox does not have to use polling. You can use CDC to read the transaction log and emit newly inserted outbox rows.

For example, with Debezium:

~~~text
Application transaction
       |
       v
Business table + Outbox table
       |
       v
Database transaction log
       |
       v
Debezium connector
       |
       v
Outbox event router
       |
       v
Kafka topic
       |
       v
Elasticsearch projection consumer
~~~

Here:

- The application still writes to the business table and outbox table in the same transaction.
- The database writes the transaction log upon commit.
- Debezium reads the log and emits outbox changes.
- The Outbox Event Router can transform outbox rows into messages with appropriate keys, topics, and payloads.
- The consumer receives the message and updates Elasticsearch.

CDC does not replace the purpose of the outbox. The outbox defines **which business events to emit**; CDC is a way to **transport those events out of the database**.

This pattern is commonly used when high reliability and high throughput are required without continuous polling.

## 11. What Is CDC?

Change Data Capture is a technique for capturing data changes from a database. With log-based CDC, a connector reads the database transaction log instead of repeatedly running SELECT queries to compare state.

Log sources vary by database:

- PostgreSQL: Write-Ahead Log (WAL).
- MySQL: binary log (binlog).
- SQL Server: transaction log or appropriate CDC mechanism.
- Oracle: redo log via a supported connector.

CDC can emit operations:

- Insert.
- Update.
- Delete.
- Initial snapshot.
- Metadata about transactions, timestamps, log positions, or source offsets depending on the connector.

CDC typically turns row changes into events in Kafka or another streaming system. A sink connector or consumer then writes those events into Elasticsearch.

## 12. How Does CDC Directly from Business Tables Differ from Outbox?

There are two common ways to use CDC:

1. **Raw table CDC**: reads changes directly from business tables.
2. **Outbox CDC**: reads events written by the application into an outbox table.

| Criterion | Raw table CDC | Outbox CDC |
|---|---|---|
| Emitted data | Row-level changes | Application-defined domain events |
| Semantics | Reflects table structure changes | Reflects business events |
| Joining multiple tables | Consumer must reconstruct state | Events can contain aggregated data |
| DB schema coupling | Higher | Lower on the consumer side |
| Best suited for | Replica sync, data pipelines | Service integration and business projections |
| Event emission logic | Inferred from row changes | Application explicitly decides event types |

For example, raw CDC might emit that the `status` column in the product table changed from DRAFT to PUBLISHED. However, it does not inherently know that this corresponds to `ProductPublished`, whether notifications are needed, or which other tables must be joined.

Outbox can emit an event:

~~~json
{
  "eventId": "evt-184",
  "eventType": "ProductPublished",
  "aggregateId": "1001",
  "aggregateVersion": 42,
  "occurredAt": "2026-11-13T10:00:00Z",
  "payload": {
    "name": "Wireless Keyboard",
    "price": 1299000,
    "status": "PUBLISHED"
  }
}
~~~

This event carries clearer business semantics. Consumers do not have to guess event types from table names and changed columns.

## 13. When to Use Raw CDC?

Raw CDC fits well when the goal is table-level data synchronization or building data pipelines:

- Replicating changes to a data warehouse.
- Syncing select tables to a search system.
- Building read replicas or cache projections.
- Collecting row change history.
- Integrating with streaming platforms.

If using raw CDC to update Elasticsearch, design the consumer to:

1. Understand each table's schema.
2. Handle inserts/updates/deletes.
3. Join data from multiple tables when a document needs multiple sources.
4. Handle change ordering.
5. Handle initial snapshots and transition to streaming.
6. Track schema evolution.
7. Generate stable document IDs.

A single row change may not carry enough information to build a complete document. For instance, a product may also need its category name, inventory summary, and brand data. The consumer may need to query additional tables or maintain its own state.

## 14. When to Use Outbox Instead of Raw CDC?

Outbox fits well when the application wants to emit events with business semantics and control the event contract.

Examples:

- `ProductCreated`.
- `ProductPriceChanged`.
- `ProductPublished`.
- `ProductDeleted`.

The application knows exactly when a business action occurs and can write the event in the same transaction as the primary data.

Outbox is especially useful when:

- One change needs to notify multiple consumers.
- Payloads need normalized data or snapshots.
- Database schemas may evolve while event contracts need to remain stable.
- Multiple services consume the same event.
- Auditing and replaying by event identity are required.

Avoid creating a generic event like `ProductRowUpdated` for every change if consumers need specific business semantics. Conversely, avoid creating too many granular events if consumers only need a projection snapshot.

## 15. Consumer Updating Elasticsearch with Spring Data

After receiving an event from the broker, the consumer transforms it into a document and writes it using Spring Data Elasticsearch.

Example:

~~~java
@Component
public class ProductProjectionConsumer {

    private final ElasticsearchOperations operations;

    public ProductProjectionConsumer(
            ElasticsearchOperations operations
    ) {
        this.operations = operations;
    }

    public void handle(ProductPublished event) {
        ProductDocument document = new ProductDocument();

        document.setId(String.valueOf(event.productId()));
        document.setProductId(String.valueOf(event.productId()));
        document.setName(event.name());
        document.setPrice(event.price());
        document.setStatus("PUBLISHED");
        document.setAggregateVersion(event.aggregateVersion());

        operations.save(
                document,
                IndexCoordinates.of("products")
        );
    }
}
~~~

`operations.save(...)` writes the document by ID. When the same event is redelivered and the payload represents the same snapshot, rewriting under the same ID generally leaves the document in the same state.

However, if an older event arrives after a newer event, `save` can overwrite the newer projection with stale data. Stable IDs prevent creating multiple documents for the same product; they do not guarantee event ordering by themselves.

The consumer needs a version guard or an appropriate ordering strategy.

## 16. Idempotency and Event Ordering in Projections

Suppose two events exist for the same product:

~~~text
Event version 42: price = 1,299,000
Event version 43: price = 1,499,000
~~~

If version 43 is processed first and version 42 arrives late, a simple `save` call can revert the price back to the old value.

You can store `aggregateVersion` in the document and apply an event only if its version is greater:

~~~painless
if (ctx._source.aggregateVersion == null
        || params.aggregateVersion > ctx._source.aggregateVersion) {
    ctx._source.name = params.name;
    ctx._source.price = params.price;
    ctx._source.status = params.status;
    ctx._source.aggregateVersion = params.aggregateVersion;
} else {
    ctx.op = 'noop';
}
~~~

The script is invoked with params from the event. It turns stale events into no-ops if the projection already holds a newer version.

Other options include:

- Partitioning messages by aggregate ID to preserve ordering within the same aggregate.
- Using external versioning when writing documents if the API and version model fit.
- Using sequence numbers issued by the business source.
- Using consumer state/checkpoints if complex ordering control is required.

Never use message receipt timestamps as versions. Producer and consumer clocks can skew, and receipt time does not necessarily reflect business order.

## 17. Handling Delete Events

Synchronization is not only about creates and updates. When a product is deleted in the database, the Elasticsearch projection must also be deleted or marked with a tombstone.

Event:

~~~json
{
  "eventId": "evt-delete-1001",
  "eventType": "ProductDeleted",
  "aggregateId": "1001",
  "aggregateVersion": 44
}
~~~

The consumer can call:

~~~java
public void handle(ProductDeleted event) {
    operations.delete(
            event.productId().toString(),
            ProductDocument.class,
            IndexCoordinates.of("products")
    );
}
~~~

If old events might arrive after a delete, physical deletion may be insufficient because once the document disappears, its version guard disappears too. You can store a separate tombstone/version, use a soft-delete field, or maintain the event sequence elsewhere.

A tombstone can look like:

~~~json
{
  "productId": "1001",
  "aggregateVersion": 44,
  "deleted": true
}
~~~

Search queries filter `deleted = false`. This retains the version so late-arriving stale events do not recreate deleted documents. A retention and cleanup policy is needed to purge tombstones once old events can no longer arrive.

## 18. Acknowledging Messages After Elasticsearch Writes Succeed

For message consumers, do not acknowledge an event before Elasticsearch has confirmed the write if the goal is to avoid losing projection updates.

Common flow:

~~~text
Broker delivers event
        |
        v
Consumer maps event
        |
        v
Elasticsearch write
        |
        +---- failure -> retry / DLQ
        |
        v
Acknowledge message
~~~

Conceptual example with Spring Kafka:

~~~java
@KafkaListener(topics = "product-events")
public void onProductPublished(
        ProductPublished event,
        Acknowledgment acknowledgment
) {
    productProjectionConsumer.handle(event);

    // Only acknowledge after the ES write operation succeeds.
    acknowledgment.acknowledge();
}
~~~

This is an example for a listener using manual acknowledgment. The acknowledgment mode, transactions, and error handler configuration must match the application.

If Elasticsearch succeeds but the process crashes before acknowledgment, the broker may redeliver the event. The consumer must be idempotent.

If you acknowledge before writing to Elasticsearch and the process crashes afterward, the broker may not redeliver the event; the projection will miss that update.

## 19. Handling Bulk Operations and Partial Failures in Consumers

Consumers can batch multiple events into a single bulk request to increase throughput. The Bulk API can partially succeed, so never acknowledge an entire batch solely because the overall request returned a response.

Classify each item individually:

| Result | Handling |
|---|---|
| Index/create succeeded | Mark item as processed |
| Version conflict due to stale event | Determine whether it is a valid no-op or an error to handle |
| Mapping error | Send to DLQ or fix schema/payload |
| 429 or transient error | Retry with backoff |
| Timeout with unknown outcome | Retry with the same ID/version under an idempotent policy |
| Document missing on update | Determine whether upsert is needed or events arrived out of order |

If the broker offset spans multiple events in a batch, only commit the offset when all events up to that offset have been handled per policy. For partial failures, retry failed items, split the batch, or move permanently failing items to a DLQ before advancing the offset.

Do not blindly retry an entire batch if some scripts or update operations are non-idempotent.

## 20. Comparing the Three Approaches

| Criterion | Direct dual write | Transactional outbox | Raw CDC |
|---|---|---|---|
| Source of changes | Service writes to two places | Service writes business + outbox | Database transaction log |
| Atomicity | None across the two systems | Business row and outbox row share a DB transaction | CDC observes commits written to the DB |
| Event semantics | Orchestrated by the service | Clear domain events | Row-level changes |
| Complexity | Initially low | Medium | Medium to high |
| Latency | Can be immediate | Usually asynchronous | Usually asynchronous |
| Retries | Custom-built in the service | Relay and consumer retries | Connector/consumer retries |
| Duplicates | Possible on client retries | Possible on republication | Possible on offset/replay |
| Replay | Usually difficult unless events are stored | Can replay outbox/event log | Can snapshot/replay from log within retention |
| DB schema coupling | Low in write code, high in mapping logic | Lower on the consumer side | Higher |
| Best suited for | Small systems, simple requirements | Reliable business synchronization | Data pipelines and data-level change sync |

Outbox + CDC is a popular combination: the outbox defines domain events, while CDC transports outbox rows to the broker.

## 21. Initial CDC Snapshot and Streaming

When a new CDC connector is deployed, Elasticsearch may initially have zero documents. Simply reading new changes from the transaction log will not automatically populate historical data.

A CDC workflow typically needs to:

1. Take an initial snapshot of the monitored tables or outbox.
2. Record the corresponding log position.
3. Emit the snapshot records.
4. Continue reading new changes from the transaction log.
5. Maintain offsets/checkpoints to resume after restarts.

How the transition from snapshot to streaming works depends on the connector and database. Check the snapshot mode, offset behavior, and semantics of the connector in use.

When using outbox CDC, snapshotting the entire historical outbox may be unnecessary or undesirable. The initial projection can be built from a snapshot of business data, with CDC emitting only new events starting from a consistent log position. Design the starting point carefully so no changes are missed between snapshot and streaming.

## 22. Schema Evolution and Event Versioning

Database schemas and event schemas evolve over time. Consumers must handle older events still residing in the broker or DLQ.

Example event version 1:

~~~json
{
  "eventType": "ProductPublished",
  "schemaVersion": 1,
  "payload": {
    "productId": "1001",
    "name": "Keyboard"
  }
}
~~~

Event version 2 adds category:

~~~json
{
  "eventType": "ProductPublished",
  "schemaVersion": 2,
  "payload": {
    "productId": "1001",
    "name": "Keyboard",
    "category": "ACCESSORIES"
  }
}
~~~

Consumers should:

- Include an explicit schema version.
- Add fields in a backward-compatible way when possible.
- Supply defaults for new fields if business rules allow.
- Never change the meaning of an existing field without changing the version.
- Retain the ability to process older events throughout the retention/replay window.
- Version mappings and indexes when Elasticsearch field types need to change.

Avoid coupling consumers directly to internal table structures if the contract needs to last long-term.

## 23. Managing Lag and Sync Observability

Asynchronous synchronization introduces delay between the database and Elasticsearch. The application must measure and expose that state.

Useful metrics:

| Metric | Meaning |
|---|---|
| Outbox backlog | Number of unpublished events |
| Oldest unpublished age | Age of the oldest unpublished event |
| CDC source lag | Delay in reading the transaction log |
| Consumer lag | Number of unprocessed messages |
| Projection latency | Time from event to completed ES write |
| Retry count | Number of retries |
| DLQ count | Number of events that could not be processed automatically |
| Bulk item failures | Number of failed items per bulk request |
| Version no-op/conflict | Number of events skipped due to stale versions |

You can include `occurredAt` in the event and record `indexedAt` in the projection to measure latency.

Do not rely on error logs alone. Alert when backlogs grow continuously, the oldest event becomes too old, or mass schema/mapping errors appear in the DLQ.

## 24. Reconciliation and Projection Rebuildability

Outbox or CDC reduces the risk of lost events, but does not eliminate all operational failures. Consumers can have bugs, mappings can be wrong, events can land in a DLQ, or an index can be accidentally deleted.

You should have a reconciliation process:

1. Read IDs/versions from the primary source.
2. Compare against the Elasticsearch projection.
3. Detect missing, extra, or stale-version documents.
4. Recreate projections from the primary source or event log.
5. Record repair counts and outcomes.

If Elasticsearch is purely a read model, you can delete the old index, create a new index, and rebuild from the database or event history. Once rebuilt, switch the alias to the new index.

A safe reindex process typically requires:

- A source data snapshot at a consistent point.
- Continuing to capture changes occurring during the rebuild.
- Applying changes by version so older events do not overwrite newer snapshots.
- Verifying counts and sample data.
- Switching the alias once the new index is ready.

Do not use Elasticsearch as the sole source of truth if the business architecture defines the database or event store as authoritative.

## 25. Choosing Direct Dual Write, Outbox, or CDC?

You can decide based on these questions:

### Need simple code and reproducible search data?

Dual write with retries/reconciliation may suffice for a small system. However, you must account for cases where the DB succeeds and ES fails, and have a way to repair projections.

### Need to ensure business changes are not lost if a process crashes?

Transactional outbox fits well because business updates and event records commit together in the database. The relay can resume after a restart.

### Need to sync multiple tables or build row-level data pipelines?

Raw CDC fits well if consumers understand the schema and have the logic to assemble projections.

### Need reliable domain events over a streaming platform?

Outbox + CDC is often a strong choice: the service writes domain events to the outbox, the connector publishes events to the broker, and consumers build Elasticsearch projections.

### Is Elasticsearch itself the primary data source?

If there is no other source database to sync from, you can write directly to Elasticsearch. In that case, the dual-write problem does not apply in the same sense; focus instead on Elasticsearch durability, replication, backups, versioning, and recovery.

## 26. A Reference Architecture with Spring Boot, Outbox, and Elasticsearch

~~~mermaid
flowchart TD
    A["REST / Command"] --> B["Spring Application Service"]
    B --> C["@Transactional"]
    C --> D["JPA ProductRepository"]
    C --> E["JPA OutboxRepository"]
    E --> F["Outbox CDC / Debezium"]
    F --> G["Kafka: product-events"]
    G --> H["Spring Kafka Consumer"]
    H --> I["Projection Mapper"]
    I --> J["ElasticsearchOperations"]
    J --> K["products-v2 index"]
    K --> L["products alias"]
    L --> M["Search API"]
~~~

Role of each component:

- Application service coordinates business logic.
- JPA transaction writes data and outbox events.
- CDC connector reads outbox inserts.
- Kafka holds events and distributes them to consumers.
- Consumer checks versions and maps events into documents.
- Spring Data Elasticsearch writes projections.
- Search API reads only from the appropriate alias/index.

This architecture decouples business write flows from search update flows. When Elasticsearch is temporarily unavailable, events can wait in the broker and be reprocessed by consumers once the cluster recovers, within retention and retry policy limits.

## 27. Common Pitfalls

### Assuming `@Transactional` Covers Both Database and Elasticsearch

JPA transactions do not automatically roll back Elasticsearch operations. The two systems need separate coordination mechanisms.

### Committing the Database and Ignoring Elasticsearch Errors

Projections can drift permanently without retries, pending state tracking, or reconciliation.

### Publishing Events Before Database Commit

Consumers might read an event and query the database before the source transaction commits or if it later rolls back. Write to the outbox in the same transaction and publish after commit.

### Marking Outbox Rows Published Before Sending

If the process crashes before publishing, the event is lost. Prefer publish-then-mark, tolerate duplicates, and make consumers idempotent.

### Treating Raw CDC as Automatic Domain Events

Raw CDC emits row changes. If you want meaningful domain events, use an outbox or intentional transformations.

### Acknowledging Messages Before Writing to Elasticsearch

The process could crash after ack and before the ES write, losing the projection update. Ack after successful processing per policy.

### Using Random Document IDs in Consumers

A redelivered event can create a new document. Use stable IDs derived from the aggregate or event depending on the projection type.

### Stale Events Overwriting Newer Projections

Use aggregate versions, key-based ordering, or version guards during updates/indexing.

### Treating Bulk as a Transaction

Bulk operations have partial success. Inspect each item and retry selectively.

### Failing to Handle Deletes

The projection retains documents deleted at the source, or old events recreate deleted documents. Design tombstones/versioning or delete semantics.

### Skipping Initial Snapshots for CDC

A connector reading only new logs may not populate historical data in Elasticsearch. Plan an initial snapshot and transition to streaming.

### Having No Reconciliation

Outbox/CDC can still suffer from consumer bugs, schema issues, or administrative mistakes. Maintain comparison and rebuild capabilities.

## 28. Synchronization Implementation Workflow

When designing a database-to-Elasticsearch sync pipeline:

1. Identify the primary data source and the role of Elasticsearch.
2. Determine consistency requirements: immediate sync, eventual consistency, or snapshots.
3. If using dual write, explicitly handle partial success and add retries/reconciliation.
4. If reliable event emission is needed, create an outbox table within the same database transaction.
5. Define event ID, aggregate ID, aggregate version, event type, and schema version.
6. Choose a polling relay or CDC connector.
7. If using raw CDC, design logic to transform row changes into projection documents.
8. Choose topic/partition keys by aggregate to preserve ordering where needed.
9. Build idempotent consumers and acknowledge only after Elasticsearch writes succeed.
10. Use stable document IDs and version guards to prevent duplicate/out-of-order events.
11. Handle deletes, mapping errors, bulk partial failures, retries, and DLQs.
12. Monitor outbox backlog, CDC lag, consumer lag, and projection latency.
13. Build reconciliation and index rebuild procedures.
14. Test process crashes at every boundary: before commit, after commit, after publish, after ES write, and before ack.
15. Test replays, duplicate events, stale events, and older schema versions.

## References

- [Spring Data Elasticsearch — Reference Documentation](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch.html)
- [Spring Framework — Declarative transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Debezium — Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html)
- [Debezium — Architecture](https://debezium.io/documentation/reference/stable/architecture.html)
- [Debezium — PostgreSQL connector](https://debezium.io/documentation/reference/stable/connectors/postgresql.html)
- [Debezium — MySQL connector](https://debezium.io/documentation/reference/stable/connectors/mysql.html)
- [Kafka — Delivery semantics](https://kafka.apache.org/documentation/#semantics)
- [Elasticsearch — Index API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-index_.html)
- [Elasticsearch — Bulk API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html)

## Conclusion

Direct dual write is simple but lacks atomic commits between the database and Elasticsearch. Transactional outbox writes business data and events in the same database transaction, after which a relay or CDC forwards events externally. Raw CDC reads the transaction log and suits row-level pipelines, whereas outbox CDC preserves application-defined domain event semantics. With Spring Data Elasticsearch, consumers transform events into projections and write them using `ElasticsearchOperations`; this requires stable IDs, version guards, duplicate handling, post-write acknowledgments, retries/DLQs, and reconciliation. Choose the architecture based on consistency needs, recoverability, and the operational complexity your system can support.
