# Why `@Transactional` Does Not Create a Shared Transaction Between JPA and Elasticsearch

A Spring method can both save data using Spring Data JPA and write a document using Spring Data Elasticsearch. Even when both calls reside inside the same `@Transactional` method, they do not automatically become an atomic transaction.

The reason lies in transaction manager boundaries. `@Transactional` instructs the transaction manager configured for the method to manage its resources. `JpaTransactionManager` manages JPA transactions and can coordinate with JDBC connections belonging to the same `DataSource`; it does not automatically enroll Elasticsearch HTTP requests into that transaction. The Elasticsearch client sends independent requests to the cluster, and Elasticsearch does not participate in XA transactions with relational databases.

Therefore, if an operation must update both the database and Elasticsearch, the application must design how to handle a state where one side succeeds and the other fails. For systems that treat the database as the primary data source, the transactional outbox is usually the right choice: persist the business change and the sync event in the same JPA transaction, then have a separate process forward events to Elasticsearch using recoverable retries.

## 1. What Does `@Transactional` Actually Manage?

In Spring, `@Transactional` is metadata instructing the transaction infrastructure to open, commit, or roll back a transaction through a transaction manager.

For imperative applications, common transaction managers include:

- `JpaTransactionManager`: manages JPA `EntityManagerFactory` transactions and can coordinate with JDBC access on the same `DataSource`.
- `DataSourceTransactionManager`: manages JDBC transactions for a `DataSource`.
- `JtaTransactionManager`: integrates with a JTA transaction coordinator if participating resources support that protocol.
- Other specialized transaction managers: manage their own resources and semantics.

When a method is invoked through a Spring proxy, the transaction interceptor resolves the transaction manager to use, starts or joins a transaction, invokes the method, and then commits or rolls back according to the outcome and rollback rules.

Example:

~~~java
@Service
public class ProductService {

    private final ProductRepository productRepository;

    public ProductService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @Transactional
    public Product create(CreateProductCommand command) {
        Product product = new Product(
                command.name(),
                command.price()
        );

        return productRepository.save(product);
    }
}
~~~

In this example, if the repository uses JPA and the method is called via a Spring proxy, the JPA transaction manager manages database writes. If the method throws a runtime exception before committing, the transaction rolls back by default.

Crucially, a transaction manager does not automatically discover every resource used inside a method and enlist them into a shared transaction. It only manages the resources it is designed and configured to manage.

## 2. Why Are JPA and Elasticsearch Independent Resources?

JPA typically communicates with the database through JDBC connections and an `EntityManager` persistence context. The database supports ACID transactions for operations within that transaction.

Spring Data Elasticsearch communicates with Elasticsearch via the Elasticsearch Java API Client and HTTP transport. An index/update request is sent to the cluster and processed by Elasticsearch according to the corresponding API semantics.

Diagram of the two write paths:

~~~text
                  Spring service
                       |
                 @Transactional
                       |
             JpaTransactionManager
                       |
                 EntityManager
                       |
                    JDBC
                       |
                Relational DB

                  Spring service
                       |
             ElasticsearchOperations
                       |
             Elasticsearch Java Client
                       |
                      HTTP
                       |
               Elasticsearch cluster
~~~

The two branches do not automatically share a transaction context. `JpaTransactionManager` cannot roll back an Elasticsearch request already accepted by the cluster. Conversely, Elasticsearch cannot roll back a database commit.

Even if both clients are Spring beans, injected into the same service, and invoked within the same method, that does not make them the same transactional resource.

### 2.1. Same Method Does Not Mean Same Transaction

Example:

~~~java
@Transactional("jpaTransactionManager")
public Product create(CreateProductCommand command) {
    Product product = productRepository.save(
            new Product(command.name(), command.price())
    );

    elasticsearchOperations.save(
            ProductDocument.from(product)
    );

    return product;
}
~~~

The method has a transaction boundary chosen by `jpaTransactionManager`. The call `productRepository.save(...)` joins the JPA transaction. The call `elasticsearchOperations.save(...)` sends a separate request to Elasticsearch.

If both calls return normally, the database still only commits when the transaction interceptor finishes the method and executes commit. Elasticsearch may have already finished processing the request before that moment.

### 2.2. Specifying a Transaction Manager Does Not Expand Resource Scope

If an application has multiple transaction managers, you can specify one explicitly:

~~~java
@Transactional(transactionManager = "jpaTransactionManager")
public void updateProduct(...) {
    // JPA operations participate in this transaction manager.
}
~~~

The bean name `jpaTransactionManager` is an example; use the actual bean name in your application.

Specifying the manager clarifies which transaction applies to the method. It does not register the Elasticsearch client as a participant in the JPA transaction.

If an application configures multiple transaction managers without specifying one, Spring must select a manager by configuration/qualifier or may fail when ambiguous. Regardless of which manager is chosen, calls to Elasticsearch still require a separate synchronization mechanism.

## 3. Two Failure Orders When Writing Both Database and Elasticsearch

A dual-write operation usually has two steps: write to the database and write to Elasticsearch. Regardless of the order, a window exists where one side succeeds while the other has not completed.

### 3.1. Elasticsearch Write Succeeds, Database Commit Fails

Suppose the method writes to the database first, then Elasticsearch:

~~~text
1. Open JPA transaction
2. JPA save Product (uncommitted)
3. Elasticsearch index ProductDocument -> succeeds
4. JPA commit -> fails
5. JPA rolls back
~~~

Result:

| Resource | State |
| --- | --- |
| Database | No committed changes. |
| Elasticsearch | Document was written. |

Search may return a product that does not exist in the database. This is orphaned data in the read model.

Note: JPA `save()` may not send SQL immediately. SQL may be flushed at the end of the transaction. Calling `EntityManager.flush()` only pushes SQL to the database within the current transaction; it does not commit and does not make Elasticsearch wait for that transaction.

### 3.2. Database Committed, Elasticsearch Write Fails

Another variant is when the application commits the database first and then calls Elasticsearch, or catches an Elasticsearch error without rolling back the database transaction:

~~~text
1. JPA transaction commit -> succeeds
2. Send index request to Elasticsearch
3. Elasticsearch times out or rejects the request
4. Database has the data, Elasticsearch is not updated
~~~

Result:

| Resource | State |
| --- | --- |
| Database | Business data is committed. |
| Elasticsearch | Projection/search document is not updated. |

If the service returns an error to the caller, the caller may retry the entire request. Without idempotency, the business operation could be executed twice.

### 3.3. Summary Table

| Failure timing | Database | Elasticsearch | Issue |
| --- | --- | --- | --- |
| DB commit fails after ES write | Rolled back | Written | Orphaned document in ES. |
| ES fails after DB commit | Committed | Not written | Search index lags or misses document. |
| ES request times out, outcome unknown | Possibly committed | Possibly written or not | Retries risk repeating operations. |
| Bulk has partial item failures | Possibly committed | Some documents written | Must handle per item. |
| Process dies between the two steps | One side may have completed | Out-of-sync state | No shared transaction to recover automatically. |

This is not a bug in the annotation. It is a consequence of writing to two systems with different transaction boundaries.

## 4. Why Does a JPA Rollback Not Delete an Elasticsearch Document?

A rollback only reverses changes within the transaction managed by the transaction manager.

Example:

~~~java
@Transactional("jpaTransactionManager")
public void createProduct() {
    productRepository.save(new Product("Keyboard", 49.99));

    elasticsearchOperations.save(
            new ProductDocument("P-100", "Keyboard", 49.99)
    );

    throw new IllegalStateException("Simulated failure");
}
~~~

A runtime exception causes the JPA transaction to roll back by default if it escapes the method and is handled by the transaction interceptor. However, the `save()` request already sent to Elasticsearch is outside the JPA transaction. The document is not automatically deleted.

To undo the Elasticsearch operation, the application must explicitly send another request, such as deleting the document. That is a compensating action, not a rollback of the original transaction. A compensating action can also fail or execute after another consumer has already read the document.

### 4.1. Rollback Rules Must Also Be Understood Correctly

By default in Spring, runtime exceptions and errors trigger rollback; checked exceptions do not automatically roll back a transaction unless an appropriate rollback rule is declared.

Example:

~~~java
@Transactional(
        transactionManager = "jpaTransactionManager",
        rollbackFor = IOException.class
)
public void update(...) throws IOException {
    // ...
}
~~~

`rollbackFor` only changes the commit/rollback decision of the JPA transaction. It still does not make Elasticsearch participate in the transaction.

If an exception from Elasticsearch is caught and not rethrown, the JPA method may return normally and the transaction will commit. Therefore, catch blocks must clearly express business policy and never accidentally turn a sync failure into a false success.

## 5. Elasticsearch Does Not Provide Shared ACID Transactions with Databases

Elasticsearch supports document write operations and certain document-scoped atomic semantics. For example, a document update is applied as a single write operation on that document; optimistic concurrency can prevent writes based on stale versions.

However, those capabilities are not equivalent to an ACID transaction spanning:

- One Elasticsearch document.
- Multiple Elasticsearch documents.
- A relational database.
- A message broker.
- Another HTTP service.

The Bulk API is also not a transaction. Each item has its own outcome; some items can succeed while others fail.

Elasticsearch does not participate in XA transactions like an XA-capable relational database resource. You cannot simply enable JTA and assume HTTP requests to Elasticsearch will be enlisted, prepared, and rolled back alongside the database.

### 5.1. Refresh Is Not a Shared Commit

Refresh makes indexed documents visible to search. It does not:

- Wait for a JPA transaction to commit.
- Check whether the database has committed.
- Roll back documents when the database rolls back.
- Create a transaction across two systems.

`refresh=wait_for` or `refresh=true` only affects when search sees Elasticsearch changes. It does not fix dual-write issues.

## 6. Why Is `@TransactionalEventListener(AFTER_COMMIT)` Still Not Enough?

A common pattern is publishing an application event after the database commits:

~~~java
@Transactional
public Product create(CreateProductCommand command) {
    Product product = productRepository.save(
            new Product(command.name(), command.price())
    );

    eventPublisher.publishEvent(
            new ProductCreatedEvent(product.getId())
    );

    return product;
}
~~~

Listener:

~~~java
@Component
public class ProductCreatedListener {

    private final ElasticsearchOperations operations;

    public ProductCreatedListener(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onProductCreated(ProductCreatedEvent event) {
        // Read product from database and index document.
    }
}
~~~

`AFTER_COMMIT` ensures the listener is invoked after the transaction commits successfully. This avoids indexing data before database commit.

However, events in the application context typically exist only in process memory. There is still a gap:

~~~text
1. Database commit succeeds
2. Process stops abruptly
3. Listener has not run or has not sent the Elasticsearch request
4. No durable event remains to replay
~~~

The database has committed, yet there is no Elasticsearch document and no durable message to retry.

If the listener runs asynchronously, failures inside the listener cannot roll back an already committed database transaction either. `@Async` changes the execution thread; it does not make an event durable data.

### 6.1. When Is `AFTER_COMMIT` Useful?

`@TransactionalEventListener(AFTER_COMMIT)` remains useful for:

- Triggering a task after data has committed.
- Sending a wake-up signal to an outbox poller.
- Best-effort cache updates.
- Running work that does not require durable delivery guarantees.

If losing events is unacceptable, do not rely on in-memory events as the sole mechanism. Persist the event in the same database transaction, and optionally use the listener as an optimization signal to reduce processing lag.

## 7. How Does the Transactional Outbox Solve the Dual-Write Gap?

Transactional outbox persists the business change and a record describing the required sync inside the same database transaction.

When the transaction commits:

- The business record exists.
- The outbox record also exists.
- Both commit together or roll back together because they belong to the same database transaction.

A relay process later reads the outbox and sends events to Elasticsearch or a message broker.

~~~text
                 JPA service
                      |
              JPA transaction
                      |
            +---------+---------+
            |                   |
            v                   v
       Product table       Outbox table
            |                   |
            +------ COMMIT -----+
                                |
                                v
                         Outbox relay
                                |
                     retry / delivery tracking
                                |
                                v
                        Elasticsearch index
~~~

If the process dies after committing but before the relay runs, the outbox record remains in the database. The relay can resume after the service restarts.

Outbox does not create a shared transaction between the DB and Elasticsearch. It guarantees the sync intent is durably stored alongside the database change, enabling eventual-consistency delivery.

## 8. Designing the Outbox Table

An outbox table typically stores:

| Column | Meaning |
| --- | --- |
| id | Unique event ID, used for deduplication and auditing. |
| aggregate_type | Aggregate type, e.g., Product. |
| aggregate_id | Business entity ID. |
| aggregate_version | Incrementing version of the aggregate. |
| event_type | Event type, e.g., ProductCreated or ProductUpdated. |
| payload | Content to be projected. |
| created_at | Event creation timestamp. |
| published_at | Timestamp when the relay confirmed successful delivery. |
| attempts | Number of attempts. |
| next_attempt_at | Next allowed retry timestamp. |
| last_error | Sanitized error details. |
| lock_owner / locked_until | Lease info so multiple relays do not process duplicates concurrently. |

Illustrative SQL schema:

~~~sql
CREATE TABLE outbox_event (
    id                UUID PRIMARY KEY,
    aggregate_type    VARCHAR(100) NOT NULL,
    aggregate_id      VARCHAR(200) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type        VARCHAR(150) NOT NULL,
    payload           TEXT NOT NULL,
    created_at        TIMESTAMP WITH TIME ZONE NOT NULL,
    published_at      TIMESTAMP WITH TIME ZONE NULL,
    attempts          INTEGER NOT NULL DEFAULT 0,
    next_attempt_at   TIMESTAMP WITH TIME ZONE NULL,
    last_error        TEXT NULL,
    lock_owner        VARCHAR(100) NULL,
    locked_until      TIMESTAMP WITH TIME ZONE NULL
);
~~~

UUID types, timestamps, and SQL syntax must be adjusted for your database. You can add indexes on columns used to query pending events, such as `published_at`, `next_attempt_at`, and `created_at`.

Do not store arbitrary payloads containing secrets or unnecessary data. The outbox should hold snapshot/event data sufficient to update the projection, with schema versioning and compatibility rules.

## 9. Writing Domain Data and Outbox in the Same JPA Transaction

Simple entity example:

~~~java
@Entity
@Table(name = "outbox_event")
public class OutboxEvent {

    @Id
    private UUID id;

    private String aggregateType;
    private String aggregateId;
    private long aggregateVersion;
    private String eventType;

    @Lob
    private String payload;

    private Instant createdAt;
    private Instant publishedAt;

    protected OutboxEvent() {
    }

    public static OutboxEvent pending(
            String aggregateId,
            long version,
            String eventType,
            String payload) {

        OutboxEvent event = new OutboxEvent();
        event.id = UUID.randomUUID();
        event.aggregateType = "Product";
        event.aggregateId = aggregateId;
        event.aggregateVersion = version;
        event.eventType = eventType;
        event.payload = payload;
        event.createdAt = Instant.now();
        return event;
    }
}
~~~

Service:

~~~java
@Service
public class ProductService {

    private final ProductRepository productRepository;
    private final OutboxEventRepository outboxRepository;
    private final ObjectMapper objectMapper;

    public ProductService(
            ProductRepository productRepository,
            OutboxEventRepository outboxRepository,
            ObjectMapper objectMapper) {
        this.productRepository = productRepository;
        this.outboxRepository = outboxRepository;
        this.objectMapper = objectMapper;
    }

    @Transactional(transactionManager = "jpaTransactionManager")
    public Product create(CreateProductCommand command) {
        Product product = productRepository.save(
                new Product(command.name(), command.price())
        );

        String payload = serialize(
                ProductProjection.from(product)
        );

        outboxRepository.save(
                OutboxEvent.pending(
                        product.getId(),
                        product.getVersion(),
                        "ProductProjectionChanged",
                        payload
                )
        );

        return product;
    }

    private String serialize(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                    "Cannot serialize outbox event", ex
            );
        }
    }
}
~~~

The transaction manager bean name and version type are illustrative; entity/version strategies must be defined in the application. The critical requirement is that `ProductRepository` and `OutboxEventRepository` use the same database and the same transaction manager.

If payload serialization fails before commit, a runtime exception rolls back the transaction. If the commit succeeds, both the product and the outbox row are durable.

Do not call Elasticsearch directly in this method. The method only writes two types of data belonging to the same database transaction.

### 9.1. Snapshot Payload or Thin Event?

There are two ways to design payloads:

- **Snapshot/projection payload:** contains enough data for the relay to write the Elasticsearch document directly.
- **Thin domain event:** contains the aggregate ID and event metadata; the consumer reads the latest state from the database.

Snapshots avoid requiring the relay to re-query the database and preserve the exact state at the time the event was created. Thin events reduce outbox size, but may require re-reading the entity and handling cases where the entity changed further.

If the relay reads the latest state from the database, an older event might generate a projection for a newer version. That may be acceptable when the goal is an eventual current-state projection, but unsuitable when reconstructing exact historical events.

## 10. Outbox Relay: Sending Events and Marking Processed

The relay can run via a scheduler, dedicated worker, or CDC platform. For a polling relay, the general flow is:

1. Fetch a batch of unpublished events whose `next_attempt_at` has arrived.
2. Claim events using a lease/lock so multiple workers do not process them simultaneously.
3. Commit the short claim state.
4. Send payloads to Elasticsearch.
5. On success, mark `published_at`.
6. On transient error, increment attempts and schedule a retry.
7. On non-recoverable error, move to a manual-intervention status or dead-letter workflow.

Avoid keeping a database transaction/row lock open for the entire duration of network calls to Elasticsearch. A slow request can hold locks for a long time and stall the relay or business transactions.

Pseudocode:

~~~java
public void processBatch() {
    List<ClaimedOutboxEvent> events = claimPendingBatch();

    for (ClaimedOutboxEvent event : events) {
        try {
            elasticsearchProjectionWriter.apply(event);
            markPublished(event.id());
        } catch (TransientElasticsearchException ex) {
            scheduleRetry(event.id(), ex);
        } catch (PermanentProjectionException ex) {
            markForManualReview(event.id(), ex);
        }
    }
}
~~~

The `claim`, `markPublished`, and `scheduleRetry` methods require separate database transactions. `claimPendingBatch()` needs database-appropriate locking or leasing so multiple relay instances do not grab the same events.

### 10.1. Crash After Elasticsearch Write

There is another window:

~~~text
1. Relay sends event to Elasticsearch
2. Elasticsearch write succeeds
3. Relay process dies before updating published_at
4. Relay restarts and resends the event
~~~

This is at-least-once delivery behavior. The outbox ensures events are not silently lost, but they can be delivered multiple times. Consumers must be idempotent or have deduplication/version guards.

There is no way to make marking a DB row and writing to Elasticsearch atomic simply by placing the two calls side by side.

## 11. Idempotency When Writing Projections to Elasticsearch

An idempotent consumer can process the same event multiple times without producing unintended business effects.

For projections reflecting an entity's current state, a common approach is using a stable document ID:

~~~http
PUT /products/_doc/P-100
Content-Type: application/json

{
  "id": "P-100",
  "name": "Keyboard",
  "price": 49.99,
  "sourceVersion": 12
}
~~~

If the same snapshot is resent, indexing under a deterministic ID replaces the same document with the same content. This generally suits current-state projections.

However, deterministic IDs do not solve out-of-order events. For example, version 13 may already be indexed when a delayed version 12 event arrives and overwrites newer data.

### 11.1. Preserving Order with Aggregate Version

Increment the aggregate version within the same database transaction and include it in the outbox payload.

When writing to Elasticsearch, you can use external versioning:

~~~http
PUT /products/_doc/P-100?version=13&version_type=external
Content-Type: application/json

{
  "id": "P-100",
  "name": "Keyboard",
  "price": 52.00,
  "sourceVersion": 13
}
~~~

With `version_type=external`, Elasticsearch only accepts a new version strictly greater than the existing version. Late older events are rejected with a version conflict, preventing overwrites of newer projections.

Consumers must distinguish conflicts caused by stale/duplicate events from conflicts caused by another writer. You can read the current version or use known metadata to decide whether the event was already applied or requires investigation.

Do not use external versioning if source versions are not monotonic or if multiple aggregates write to a single document without an aggregation rule.

### 11.2. Event ID and Deduplication

In addition to aggregate version, store a unique event ID for auditing and deduplication support. You can keep a processed-event table on the consumer side if business rules require tracking processed events.

For current-state projections, deterministic document IDs combined with external versions are sufficient in most cases. For operations with side effects or increments/decrements, use idempotency keys or an event processing ledger.

## 12. CDC and Debezium

Instead of polling the outbox table, you can use Change Data Capture (CDC) to read the database transaction log.

A common pattern:

~~~text
JPA transaction
      |
      v
Domain table + Outbox table
      |
      v
Database transaction log
      |
      v
CDC connector (e.g., Debezium)
      |
      v
Message broker
      |
      v
Projection consumer
      |
      v
Elasticsearch
~~~

The CDC connector reads committed outbox rows from the transaction log and emits them to the broker. The consumer updates Elasticsearch.

Advantages:

- No continuous polling of the outbox table.
- Can leverage log positions and connector offsets.
- Decouples the relay from the business application.
- Easy to scale to multiple consumers/projections.

In return, operating CDC and a broker adds complexity: connector health, schema registry, offsets, topic retention, partition ordering, dead-letter handling, and replay must all be managed.

CDC is still typically at-least-once across delivery boundaries. Elasticsearch consumers still need idempotency and version ordering. CDC does not create an XA transaction between the database and Elasticsearch.

## 13. Sagas and Compensating Actions

Transactional outbox fits one-way synchronization from a database to a search projection. If a workflow requires multiple business steps across multiple systems, a Saga can be used.

A Saga models a workflow as stateful steps with compensating actions:

~~~text
Create order in DB
       |
       v
Reserve inventory
       |
       v
Update search/projection
       |
       v
Complete workflow

If a later step fails:
       |
       v
Run compensating action
       |
       v
Restore business state where possible
~~~

A compensating action is a new business operation intended to bring the system back to an acceptable state. It does not erase history and does not guarantee absolute success.

For example, if a document has already been indexed but the order is canceled, the workflow can emit an event to update the status or delete the projection. If the consumer temporarily fails, the compensating action must also be retried.

Do not use a Saga solely to synchronize a simple search document when an outbox suffices. Sagas are useful when there are multiple steps and explicit compensation rules.

## 14. Why Not Rely on `ChainedTransactionManager` or JTA to Solve This?

Some legacy systems used chained transaction managers or configured transaction coordinators to try coordinating multiple resources.

Distinguish clearly:

- A transaction manager can manage multiple resources if they are supported and properly enlisted via the protocol.
- Sequentially calling two transaction managers does not automatically produce an atomic commit.
- A JTA transaction coordinator can only coordinate resources participating in that protocol.
- An Elasticsearch HTTP client does not become an XA resource just by being invoked inside a `@Transactional` method.

Chained commit mechanisms can still encounter scenarios where the first manager commits while the next manager fails. The system is then left in a partial commit state requiring compensation/recovery.

Do not treat wrapping multiple managers in an annotation as proof of a shared ACID transaction. For DB + Elasticsearch, design around outbox/eventual consistency or a workflow with compensation.

## 15. `@Transactional(propagation = ...)` Does Not Solve Cross-Resource Atomicity

Propagation determines how a method participates in an existing transaction or creates a new transaction within the scope of the chosen transaction manager.

Examples:

- `REQUIRED`: joins the current transaction or creates a new one.
- `REQUIRES_NEW`: suspends the current transaction and opens a new one.
- `NESTED`: nested transaction if the manager/resource supports savepoints.
- `NOT_SUPPORTED`: executes without a transaction within the scope of that manager.

Propagation modes do not automatically add Elasticsearch to a JPA transaction.

Example:

~~~java
@Transactional(
        transactionManager = "jpaTransactionManager",
        propagation = Propagation.REQUIRES_NEW
)
public void saveAuditRecord(...) {
    // A new database transaction.
}
~~~

`REQUIRES_NEW` can be useful for writing audit records to the database in a separate transaction, but it does not make Elasticsearch requests part of that transaction.

## 16. Handling Elasticsearch as Only a Read Model

A common architecture keeps the relational database as the source of truth while Elasticsearch serves as a read model for search, filtering, and aggregations.

In this architecture:

- The JPA transaction ensures business changes and outbox events commit together.
- The outbox relay/consumer updates Elasticsearch post-commit.
- Search may lag behind the database by some interval.
- If Elasticsearch goes down temporarily, the database can still accept changes and the outbox queues events.
- When Elasticsearch recovers, consumers process the backlog so projections converge.

This is eventual consistency. The application must define acceptable latency and behavior when a user updates data and immediately searches.

For instance, the API can return the entity from the database immediately after commit while optionally reporting projection sync status if the UI needs to know whether the search index has caught up.

Never use Elasticsearch results as the sole proof that a database transaction has committed.

## 17. Read-After-Write and User Experience Alignment

If a user creates a product and immediately searches for it, the outbox may cause the search index to be not yet updated at query time.

Ways to handle this:

1. Return newly created data from the database response instead of re-querying Elasticsearch.
2. Display a "syncing search index" indicator if business requirements call for it.
3. Allow search queries once the relay confirms the event has been indexed.
4. For certain critical flows, await consumer acknowledgment with a timeout, without holding the JPA transaction open while waiting.
5. Use a direct database read endpoint for operations requiring read-your-writes.

Refresh `wait_for` only ensures a document written to Elasticsearch becomes search-visible after refresh. It does not ensure the event was created, the relay ran, or the database and Elasticsearch committed together.

## 18. Retries, Dead-Letter Queues, and Reconciliation

An outbox workflow needs a clear error policy.

### 18.1. Error Classification

| Error | Handling |
| --- | --- |
| Timeout or network interruption | Retry with backoff; previous outcome may be unknown so idempotency is required. |
| Elasticsearch 429 | Back off, reduce concurrency, and retry. |
| Mapping/parsing error | Do not retry as-is; fix payload or mapping. |
| 401/403 | Fix credentials/privileges; place event in an error state for intervention. |
| Version conflict from stale event | Mark stale/already superseded after verifying the current version is newer. |
| Index does not exist | Check provisioning/aliases; retry once the condition is resolved. |

### 18.2. Dead-Letter or Manual Review

After a bounded number of retries, permanently failing events should move to an observable state:

- Record error type and diagnostic details.
- Retain payload or a safe reference for replay.
- Alert on event age and failure count.
- Provide controlled replay tooling.
- Do not delete rows simply because retry limits were exceeded.

### 18.3. Reconciliation

The outbox handles undelivered events, yet the system still needs to verify whether projections have drifted. A reconciliation job can compare:

- Entity counts by partition or time window.
- Aggregate versions in DB vs. projection.
- Recently updated IDs.
- Missing or stale documents.
- Outbox events stuck for too long.

Reconciliation catches operational errors, consumer bugs, or data modified outside the event flow.

## 19. Testing Transaction Boundaries

Do not test only the happy path. Simulate points where the process can fail.

### 19.1. Testing JPA Rollback

1. Start a JPA transaction.
2. Write a Product.
3. Force the method to throw a runtime exception.
4. Verify the Product is not committed in the database.

If the same method also wrote directly to Elasticsearch, check whether the document still exists. This demonstrates that a JPA rollback does not reverse Elasticsearch requests.

### 19.2. Testing Outbox Atomicity

1. Write Product and OutboxEvent in the same transaction.
2. Force the transaction to roll back.
3. Verify neither row exists.
4. Execute a successful transaction.
5. Verify both Product and OutboxEvent exist.

### 19.3. Testing Relay Crash

1. Create an outbox event.
2. Relay sends it successfully to Elasticsearch.
3. Simulate process death before marking published.
4. Run the relay again.
5. Verify the event is redelivered without duplicating projections or regressing versions.

### 19.4. Testing Out-of-Order Events

1. Send event version 12.
2. Send event version 13.
3. Resend event version 12.
4. Verify the projection remains at version 13.

### 19.5. Testing Elasticsearch Failures

- Pause the cluster or block network access.
- Return 429 to verify backoff.
- Send a malformed payload against mapping to verify dead-lettering.
- Restart the relay and verify pending events are processed.
- Verify alerts when outbox backlog grows.

## 20. Anti-Patterns to Avoid

| Anti-pattern | Risk | Remedy |
| --- | --- | --- |
| Assuming `@Transactional` on a method commits DB and ES together | One side can succeed while the other fails. | Define each resource's transaction boundary. |
| Writing ES before JPA commit | ES may contain documents absent from the DB. | Write outbox in the DB transaction and process post-commit. |
| Using an `AFTER_COMMIT` listener as a durable queue | Process crashes can lose events. | Persist outbox rows or use CDC. |
| Catching ES errors and returning success without saving state | Projections drift with no way to retry. | Persist events durably and track state. |
| Retrying the entire business operation | Can create duplicates or run business logic twice. | Separate commands from projection events; use idempotency keys. |
| Retrying events without a version guard | Old events can overwrite newer projections. | Aggregate versions/external versioning. |
| Keeping JPA transactions open during slow ES calls | Holds connections/locks long, increasing contention. | Have the outbox relay call ES outside domain transactions. |
| Using `REQUIRES_NEW` thinking it creates a distributed transaction | Only creates a new transaction in the chosen manager. | Use outbox or Saga as required. |
| Treating the Bulk API as a transaction | Items can succeed/fail independently. | Process each item response individually. |
| Enabling immediate refresh to fix dual write | Only changes search visibility, not atomicity. | Separate freshness from transaction consistency. |
| Deleting outbox events immediately after sending without audit | Hard to replay and investigate bugs. | Retain/archive per policy. |

## 21. Solution Selection Workflow

When a use case needs to write to both JPA and Elasticsearch, determine:

1. Which system is the source of truth?
2. Is Elasticsearch a read model or the primary business data store?
3. Is eventual consistency lag acceptable?
4. What happens if the DB commits but Elasticsearch does not update?
5. What happens if Elasticsearch writes successfully but the DB rolls back?
6. Can events be stored inside the same DB transaction?
7. Can consumers write idempotently by document ID?
8. Is an aggregate version needed to prevent stale events from overwriting?
9. How are retries, dead-letter handling, and reconciliation operated?
10. What level of read-after-write do users require?

For most systems using JPA as the primary data source and Elasticsearch for search, the practical choice is:

- Write the entity and outbox event under the same `JpaTransactionManager`.
- Commit the database.
- Have a relay/CDC deliver events at-least-once.
- Have consumers index documents using stable IDs and version guards.
- Retry transient failures and isolate permanent failures.
- Run reconciliation to detect projection drift.

If business logic requires multiple systems to complete a multi-step process, model workflow state and compensating actions with a Saga. Never try to turn a Java method into a distributed transaction with an annotation alone.

## 22. References

- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
- [Spring Data Elasticsearch — Elasticsearch Clients and Operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/clients.html)
- [Elasticsearch — Bulk API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html)
- [Elasticsearch — Optimistic concurrency control](https://www.elastic.co/guide/en/elasticsearch/reference/current/optimistic-concurrency-control.html)
- [Debezium — Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html)

`@Transactional` defines transaction boundaries for resources managed by the selected transaction manager. `JpaTransactionManager` protects the database transaction, whereas the Elasticsearch client sends independent HTTP requests and is not rolled back with JPA. `@TransactionalEventListener(AFTER_COMMIT)` ensures post-commit ordering but does not durably persist events. When reliable synchronization is required, write an outbox row alongside the entity in a single JPA transaction, then relay events with at-least-once delivery using idempotency, version ordering, retries, and reconciliation.
