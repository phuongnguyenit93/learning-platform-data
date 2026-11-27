# Syncing Database Changes via Outbox

When an application saves business data to a database while also updating Elasticsearch for search, those two writes create a consistency problem. The database may commit successfully while Elasticsearch is temporarily unavailable; or the application may crash after the database commits but before sending the change to the search index. Simply executing two sequential writes inside the same service method still risks leaving the two stores out of sync.

**Transactional outbox** closes this gap by persisting both the business change and an event to be synced inside the same database transaction. A relay process reads committed events and forwards them to Elasticsearch. If the relay fails, the event remains in the outbox for retry or recovery. This pattern typically provides at-least-once delivery; therefore, consumers must be idempotent and enforce version-ordering protection.

In a Spring Data Elasticsearch architecture, the database is the source of truth and Elasticsearch serves as the read model/projection. This lesson covers outbox architecture, transaction boundaries, event schemas, polling relays, CDC, Bulk API handling, idempotency, ordering, deletes, retry/DLQ, index rebuilding, and end-to-end testing.

## 1. Why Writing Directly to the Database and Elasticsearch Can Fail

A naive service might do the following:

~~~java
@Transactional
public Product updateProduct(UpdateProductRequest request) {
    Product product = productRepository.findById(request.id())
            .orElseThrow();

    product.setName(request.name());
    productRepository.save(product);

    elasticsearchOperations.save(toDocument(product));

    return product;
}
~~~

At first glance, the method carries a database transaction annotation, making it look like both changes are protected together. However, that transaction typically manages only the database connection. Elasticsearch does not automatically participate in a JPA/JDBC transaction.

Failure modes:

1. Database commits successfully, Elasticsearch times out.
2. Elasticsearch write succeeds, database transaction rolls back.
3. Process is killed after database commit but before the Elasticsearch call.
4. Process is killed after the Elasticsearch write but before returning a response.
5. Elasticsearch returns HTTP success while an individual bulk item failed.
6. Network timeout leaves the application uncertain whether the server applied the write.

This is the dual-write problem. Without an explicitly configured distributed transaction, you cannot assume two separate systems commit or roll back atomically.

For search projection architectures, an outbox is usually simpler and easier to operate: the business transaction commits solely in the source database, while projections update asynchronously and remain rebuildable.

## 2. Transactional Outbox Architecture

The outbox stores events in the same database as business data. When the transaction commits, both the business mutation and the event exist together.

~~~text
HTTP request
     |
     v
Application service
     |
     | one database transaction
     v
+-----------------------------+
| Relational database         |
|                             |
|  business table             |
|  outbox_event table         |
+-----------------------------+
               |
               | committed rows
               v
        Outbox relay
               |
               | retry / backoff
               v
        Elasticsearch
               |
               v
         Search API
~~~

Components:

- **Business table:** stores canonical business state.
- **Outbox table:** stores events awaiting forwarding.
- **Application service:** writes business data and outbox events in one transaction.
- **Relay/consumer:** reads committed events.
- **Projector:** transforms events into Elasticsearch documents.
- **Elasticsearch:** stores projections for search, filtering, and aggregations.

An outbox does not turn the database and Elasticsearch into one single transaction. Instead, it guarantees that whenever the business transaction commits, the intent to sync is durably recorded in the same transaction.

## 3. Processing Flow When Updating a Product

Suppose a user renames a product:

~~~text
1. Request UpdateProduct
          |
          v
2. Begin DB transaction
          |
          v
3. Update products row
          |
          v
4. Insert ProductUpdated event into outbox
          |
          v
5. Commit DB transaction
          |
          v
6. Outbox relay reads committed event
          |
          v
7. Build ProductDocument
          |
          v
8. Index document into Elasticsearch
          |
          v
9. Mark outbox event delivered
~~~

If step 5 rolls back, neither the product update nor the outbox event exists. If step 7 or 8 fails, the outbox event remains available for retry. If step 8 succeeds but the relay crashes before step 9, the event can be redelivered; the projector must handle it idempotently.

This is the key insight: an outbox eliminates the risk of losing synchronization intent between two writes, but it does not automatically deliver exactly-once between the database and Elasticsearch.

## 4. Designing the Outbox Table

A baseline schema using PostgreSQL:

~~~sql
CREATE TABLE outbox_event (
    event_id           UUID PRIMARY KEY,
    aggregate_type     VARCHAR(100) NOT NULL,
    aggregate_id       VARCHAR(200) NOT NULL,
    aggregate_version  BIGINT NOT NULL,
    event_type         VARCHAR(150) NOT NULL,
    schema_version     INTEGER NOT NULL,
    payload            JSONB NOT NULL,
    occurred_at        TIMESTAMPTZ NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    status             VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempts           INTEGER NOT NULL DEFAULT 0,
    next_attempt_at    TIMESTAMPTZ,
    locked_by          VARCHAR(150),
    lease_until        TIMESTAMPTZ,
    delivered_at       TIMESTAMPTZ,
    last_error         TEXT
);

CREATE INDEX idx_outbox_pending
    ON outbox_event (status, next_attempt_at, created_at);

CREATE INDEX idx_outbox_aggregate
    ON outbox_event (aggregate_type, aggregate_id, aggregate_version);
~~~

Fields:

- event_id: stable event identifier.
- aggregate_type: entity/domain aggregate type.
- aggregate_id: business ID.
- aggregate_version: monotonically increasing version per aggregate.
- event_type: event name.
- schema_version: payload schema version.
- payload: data for the projector to process.
- occurred_at: timestamp when the business event occurred.
- status: delivery state.
- attempts: attempt counter.
- next_attempt_at: earliest eligible retry timestamp.
- locked_by and lease_until: claim/lease metadata for the relay.
- delivered_at: completion timestamp.
- last_error: sanitized latest error.

The actual schema should be tailored to your database engine, event volume, retention, and concurrency model. You can separate delivery state into a separate table to keep events immutable; at high throughput, time-based partitioning or archival policies may be needed.

## 5. What Should an Event Contain?

An event should carry enough information for consumers to identify the change type and construct the projection. Example:

~~~json
{
  "eventId": "6d76f9d0-6f2d-4e56-ae58-1e1f2e3a1001",
  "eventType": "ProductUpdated",
  "schemaVersion": 1,
  "aggregateType": "Product",
  "aggregateId": "p-1001",
  "aggregateVersion": 42,
  "occurredAt": "2026-11-13T10:15:30Z",
  "tenantId": "tenant-a",
  "payload": {
    "name": "Mechanical Keyboard",
    "description": "Compact wireless keyboard",
    "category": "keyboard",
    "status": "ACTIVE"
  }
}
~~~

The envelope should include a unique event ID stable across retries, aggregate ID, aggregate version or sequence, event type, schema version, source timestamp, tenant/partition key if applicable, and either the payload or reference data to load latest state.

Never put access tokens, secrets, or unnecessary personal data into events. Outboxes often grant broad read access within pipelines and may be retained long-term for replays, so protect them like core business data.

## 6. Event Payload vs. Reloading Latest State

Two common strategies exist.

**Event carries the required snapshot:** the payload includes all fields needed to build the document at the moment the event occurred. Consumers do not need to query the database again. This facilitates historical replay, though payloads are larger and schema evolution must be managed.

**Event carries only ID/version:** the consumer reloads the current aggregate from the database and builds the latest document. This keeps payloads small, though when an old event is processed late, the consumer may read newer state than the event represents. That can be desirable if projections only care about current state, but unsuitable if every historical transition must be replayed.

A system can also emit compact domain events with metadata and project directly from them, or emit notification events signaling that an aggregate needs refreshing.

Decide semantics upfront:

- If the goal is reflecting latest state, reloading from the source can be simpler.
- If the goal is applying each change in order, events need full data and versions.
- If auditing/history is needed, keep events immutable and do not overwrite payloads with latest state.

## 7. Writing Business Data and Outbox in the Same Spring Transaction

Example using Spring Data JPA for the database and an outbox repository:

~~~java
@Service
public class ProductCommandService {

    private final ProductJpaRepository products;
    private final OutboxEventRepository outbox;
    private final ObjectMapper objectMapper;

    public ProductCommandService(
            ProductJpaRepository products,
            OutboxEventRepository outbox,
            ObjectMapper objectMapper) {
        this.products = products;
        this.outbox = outbox;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public Product update(UpdateProductRequest request) {
        Product product = products.findById(request.id())
                .orElseThrow(ProductNotFoundException::new);

        product.setName(request.name());
        product.setDescription(request.description());
        product.setVersion(product.getVersion() + 1);

        Product saved = products.save(product);

        ProductUpdatedPayload payload =
                new ProductUpdatedPayload(
                        saved.getId(),
                        saved.getName(),
                        saved.getDescription(),
                        saved.getVersion()
                );

        OutboxEvent event = OutboxEvent.create(
                UUID.randomUUID(),
                "Product",
                saved.getId(),
                saved.getVersion(),
                "ProductUpdated",
                1,
                objectMapper.writeValueAsString(payload),
                Instant.now()
        );

        outbox.save(event);
        return saved;
    }
}
~~~

This assumes ProductJpaRepository and OutboxEventRepository share the same transaction manager and database. Constructors, exceptions, and JSON serialization should be adapted to your application.

The essential rule is never calling Elasticsearch inside this transactional method. When the transaction commits, the business row and outbox row either commit together or roll back together.

If writing the outbox via a different data source or transaction manager, atomicity is no longer guaranteed automatically. In that case, use an explicitly vetted design rather than adding a repository and assuming shared transactions.

## 8. Outbox Entity and Repository

A minimal JPA entity:

~~~java
@Entity
@Table(name = "outbox_event")
public class OutboxEvent {

    @Id
    private UUID eventId;

    private String aggregateType;
    private String aggregateId;
    private long aggregateVersion;
    private String eventType;
    private int schemaVersion;

    @Column(columnDefinition = "jsonb")
    private String payload;

    private Instant occurredAt;
    private String status;
    private int attempts;
    private Instant nextAttemptAt;
    private String lockedBy;
    private Instant leaseUntil;
    private Instant deliveredAt;

    @Column(length = 4000)
    private String lastError;

    protected OutboxEvent() {
    }

    // Constructor/factory and accessors omitted for clarity.
}
~~~

Repository:

~~~java
public interface OutboxEventRepository
        extends JpaRepository<OutboxEvent, UUID> {
}
~~~

Using JSONB depends on PostgreSQL and Hibernate mapping strategies. Use an appropriate converter or JSON type for your ORM version. Do not assume columnDefinition alone converts Java objects to JSONB if no converter is configured.

In production, consider separating immutable event content from delivery state. Event payloads should not be mutated on every retry; only delivery-status fields should change.

## 9. Why the Relay Should Not Hold a Database Transaction While Calling Elasticsearch

A naive approach opens a transaction, reads an outbox row, calls Elasticsearch, and marks it delivered before committing. Holding database locks and transactions across network requests causes serious problems:

- Slow Elasticsearch calls prolong database transactions.
- Long-held locks block other relays.
- Connection pool slots remain pinned while waiting on network I/O.
- If the transaction rolls back after Elasticsearch already wrote, the event is redelivered.
- If the cluster times out, the database transaction can cascade into another timeout.

The standard pattern is **claiming events in a short transaction**, committing the lease, and calling Elasticsearch outside the transaction. Once done, open another short transaction to update status.

~~~text
Transaction A:
  claim rows + set lease + commit
             |
             v
Outside DB transaction:
  project and write to Elasticsearch
             |
             v
Transaction B:
  mark delivered / schedule retry + commit
~~~

Crashing after claiming leaves the event leased until the lease expires, allowing another worker to reclaim it. Crashing after Elasticsearch succeeds but before marking delivered causes redelivery; idempotency handles this safely.

## 10. Polling Relay with FOR UPDATE SKIP LOCKED

PostgreSQL supports SELECT ... FOR UPDATE SKIP LOCKED so multiple workers claim distinct rows without blocking one another.

Example batch-claim transaction:

~~~sql
WITH candidates AS (
    SELECT event_id
    FROM outbox_event
    WHERE status = 'PENDING'
      AND (next_attempt_at IS NULL OR next_attempt_at <= now())
      AND (lease_until IS NULL OR lease_until < now())
    ORDER BY created_at, event_id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE outbox_event e
SET status = 'IN_PROGRESS',
    locked_by = :worker_id,
    lease_until = now() + interval '60 seconds',
    attempts = attempts + 1
FROM candidates c
WHERE e.event_id = c.event_id
RETURNING e.*;
~~~

Run the query inside a short transaction. Once claimed rows return, commit before calling Elasticsearch.

Interval syntax, RETURNING, and locking clauses vary by database. MySQL, SQL Server, or Oracle require their own dialect equivalents. Do not copy PostgreSQL SQL verbatim to other databases.

## 11. Leases and Handling Worker Crashes

A lease grants temporary, time-bounded ownership. If a worker dies, the lease expires so another worker can reclaim the event.

Requirements to define:

- Lease duration must exceed normal batch processing time.
- If processing runs long, workers can renew the lease.
- Only the worker currently holding the lease may update delivery state.
- When a lease expires, the old worker may still be running, so duplicates can still happen.
- State updates must check locked_by and lease expiration so an old worker cannot overwrite state after another worker reclaimed the event.

Example conditional update:

~~~sql
UPDATE outbox_event
SET status = 'DELIVERED',
    delivered_at = now(),
    locked_by = NULL,
    lease_until = NULL
WHERE event_id = :event_id
  AND status = 'IN_PROGRESS'
  AND locked_by = :worker_id
  AND lease_until > now();
~~~

If the update affects zero rows, this worker no longer owns the lease. Never mark delivered blindly with an unconditional update.

## 12. Do Not Let Claiming Break Aggregate Ordering

Multiple workers can process in parallel. This raises throughput, but can allow event version 43 to reach Elasticsearch before version 42.

~~~text
Product p-1001:
  E41 -> worker A (slow)
  E42 -> worker B (fast)

Elasticsearch receives E42 before E41
Then E41 overwrites the newer projection
~~~

Options:

- Partition by aggregate ID and preserve order within each partition.
- Claim only the next eligible event per aggregate.
- Use source versions and external versioning to reject stale events.
- Run a sequential event consumer per partition.
- When projecting by reloading latest state, verify version before indexing.

You rarely need global sequential processing. You can parallelize across aggregates while preserving order per aggregate key.

## 13. Polling Relay in Spring

A scheduled component can invoke the batch-claim service:

~~~java
@Component
public class OutboxPollingJob {

    private final OutboxRelayService relayService;

    public OutboxPollingJob(OutboxRelayService relayService) {
        this.relayService = relayService;
    }

    @Scheduled(fixedDelay = 500L)
    public void poll() {
        relayService.processNextBatch();
    }
}
~~~

Orchestration service:

~~~java
public void processNextBatch() {
    List<ClaimedOutboxEvent> events = claimService.claim(batchSize);

    if (events.isEmpty()) {
        return;
    }

    processOutsideTransaction(events);
}
~~~

The claim method should live in a separate transactional bean/service so the transaction closes before calling Elasticsearch. Avoid self-invocation inside the same bean expecting @Transactional to open a new transaction; Spring proxies generally do not intercept self-invocation that way.

When multiple application instances run schedulers, coordinate claims via database locks/leases or a broker. Never rely on an in-memory boolean flag to guarantee single-worker exclusivity cluster-wide.

## 14. Separating Transaction Boundaries in Spring

A clean structure:

~~~java
@Service
public class OutboxClaimService {

    @Transactional
    public List<ClaimedOutboxEvent> claim(int limit) {
        // Select eligible rows with lock/lease.
        // Mark them IN_PROGRESS and return immutable event data.
    }
}

@Service
public class OutboxDeliveryService {

    @Transactional
    public void markDelivered(UUID eventId, String workerId) {
        // Update only if this worker still owns the lease.
    }

    @Transactional
    public void scheduleRetry(
            UUID eventId,
            String workerId,
            Instant nextAttempt,
            String safeError) {
        // Persist retry state.
    }
}
~~~

The relay calls both services through proxy beans:

~~~java
public void processNextBatch() {
    List<ClaimedOutboxEvent> events = claimService.claim(100);

    for (ClaimedOutboxEvent event : events) {
        try {
            projector.project(event);
            deliveryService.markDelivered(
                    event.eventId(),
                    workerId
            );
        } catch (RetryableProjectionException ex) {
            deliveryService.scheduleRetry(
                    event.eventId(),
                    workerId,
                    retryPolicy.nextAttempt(event.attempts()),
                    sanitize(ex)
            );
        } catch (PermanentProjectionException ex) {
            deliveryService.moveToDeadLetter(
                    event.eventId(),
                    workerId,
                    sanitize(ex)
            );
        }
    }
}
~~~

This is illustrative; design appropriate claim DTOs, exceptions, and retry policies. Never keep the claim transaction open across the loop calling Elasticsearch.

## 15. Writing Documents to Elasticsearch with Spring Data

Create a dedicated document class for the search projection:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    private String name;
    private String description;
    private String category;
    private String status;
    private String tenantId;
    private long sourceVersion;
}
~~~

The projector transforms events into documents:

~~~java
@Component
public class ProductProjector {

    private final ElasticsearchOperations operations;
    private final ObjectMapper objectMapper;

    public ProductProjector(
            ElasticsearchOperations operations,
            ObjectMapper objectMapper) {
        this.operations = operations;
        this.objectMapper = objectMapper;
    }

    public void project(OutboxEvent event) {
        ProductUpdatedPayload payload =
                readPayload(event.getPayload());

        ProductDocument document = new ProductDocument();
        document.setId(event.getAggregateId());
        document.setName(payload.name());
        document.setDescription(payload.description());
        document.setCategory(payload.category());
        document.setStatus(payload.status());
        document.setTenantId(payload.tenantId());
        document.setSourceVersion(event.getAggregateVersion());

        operations.save(
                document,
                IndexCoordinates.of("products")
        );
    }
}
~~~

This demonstrates saving through Spring Data Elasticsearch. In production, load the index name from configuration/alias, enforce tenant scope in queries, and guard version semantics in Elasticsearch or the projector.

Using a dedicated projection document decouples database entities from search mappings. You can add analyzers, multi-fields, denormalized fields, or search-only fields without altering the operational database schema.

## 16. Idempotency When the Relay Redelivers Events

The relay can redeliver an event if Elasticsearch succeeds but the worker crashes before marking the outbox event delivered. Lease expiration can also cause another worker to reclaim it.

Therefore, the projector must handle duplicates safely:

- Use a stable document ID derived from the aggregate ID.
- Never generate a new random ID on retry.
- Avoid non-idempotent side effects inside the projector.
- Store sourceVersion.
- Reject events older than the already-applied version.
- Ensure replaying the same event yields the exact same final state.

For full-document index operations using the same ID, resending the same payload yields the same document state. However, if a projection accumulates counters or appends to arrays, design explicit idempotency.

Idempotency is not just using the same ID. If an older event overwrites a newer event, the document regresses. You also need version ordering.

## 17. Protecting Versions with External Versioning

Elasticsearch supports version control on index operations. When sources have monotonically increasing aggregate versions, external versioning lets Elasticsearch accept only newer versions according to the chosen semantics.

~~~text
Database aggregate version 41 -> Elasticsearch document version 41
Database aggregate version 42 -> Elasticsearch document version 42

If event version 41 arrives after version 42:
    Elasticsearch rejects stale write
~~~

At the REST layer, an index request specifies version and version_type. With Spring Data abstractions, external versioning support varies by API and version; if exact control is required, use the Elasticsearch Java API Client inside an adapter.

Distinguish external versioning from optimistic concurrency via sequence number and primary term. They address related but different problems.

When receiving a version conflict:

- If the event is older than the current document, mark it stale/superseded.
- If it has the same version and same event, the duplicate was already applied.
- If it has the same version with a different payload, investigate.
- If a newer version conflicted due to a race, inspect state/version and handle per policy.

Never retry conflicts infinitely.

## 18. Handling Delete Events

Deletes must be synced just like ordinary mutations. If you only handle creates and updates, products deleted from the database remain visible in search results.

Example event:

~~~json
{
  "eventId": "evt-delete-1001",
  "eventType": "ProductDeleted",
  "aggregateId": "p-1001",
  "aggregateVersion": 43,
  "occurredAt": "2026-11-13T11:00:00Z",
  "payload": {
    "reason": "REMOVED"
  }
}
~~~

The projector can delete the document by ID. However, watch out for stale update events arriving late and re-creating the deleted document.

Protections:

- External versioning on deletes when semantics align.
- Retaining a tombstone with version inside the projection.
- Storing deleted versions in a separate lookup store.
- Serializing events per aggregate.
- When projecting from latest source state, verifying the aggregate still exists rather than already deleted.

If the Elasticsearch document is purged completely with no version or tombstone left behind, an older event can resurrect it. Tests must include a version-43 delete arriving before a version-42 update and confirm the document does not reappear.

## 19. Bulk Indexing from the Outbox

When backlogs grow, sending one document per request creates excessive HTTP overhead. Batch events into bulk requests.

~~~text
Claim batch of outbox events
          |
          v
Transform to IndexQuery items
          |
          v
Bulk index request
          |
          v
Inspect every item response
       /      |       \
      v       v        v
  Success   Retry    Permanent
      |       |        |
      v       v        v
 Delivered  Pending    DLQ
~~~

Spring Data Elasticsearch exposes the Bulk API through ElasticsearchOperations. Conceptual example:

~~~java
List<IndexQuery> queries = events.stream()
        .map(this::toIndexQuery)
        .toList();

List<IndexedObjectInformation> results =
        operations.bulkIndex(
                queries,
                BulkOptions.defaultOptions(),
                IndexCoordinates.of("products")
        );
~~~

Class names, overloads, and response metadata vary by Spring Data version. Use your project's actual dependency APIs and establish how each result correlates back to its source event. If the API throws a composite exception, determine whether the server partially processed the request; never assume every item failed or every item succeeded.

## 20. Bulk HTTP Success Does Not Mean Every Item Succeeded

A bulk response can report item-level errors even when the HTTP call succeeded. Workers must inspect every action result:

- Success: mark event delivered.
- Transient error such as 429: retry with backoff.
- Mapping/parsing error: move to DLQ or await remediation.
- Stale version conflict: mark superseded per policy.
- Authentication/authorization error: alert on configuration and usually pause the pipeline rather than retrying items endlessly.

Never mark an entire batch delivered simply because the bulk call threw no exception. Never retry an entire batch when only a subset failed and resending succeeded items could cause side effects or version overwrites.

Every bulk item must retain correlation to its eventId. If list ordering is the only correlation mechanism, ensure transforms never reorder items and the response API preserves action order. Tracking explicit correlation IDs in worker state simplifies troubleshooting.

## 21. Retrying with Backoff and Jitter

Transient errors require bounded retries. Exponential backoff:

\[
delay_n = min(maxDelay,\ baseDelay \times 2^n)
\]

You can add jitter:

\[
actualDelay = random(0,\ delay_n)
\]

For example, attempt 1 up to 250 ms, attempt 2 up to 500 ms, attempt 3 up to 1 second, attempt 4 up to 2 seconds, capped at 30 seconds; once attempts are exhausted, move to DLQ or parked status.

These numbers are examples only. Tune them based on throughput, latency, cluster capacity, and freshness requirements.

When 429s spike, reduce batch size or concurrency instead of merely increasing retries. If the cluster is overloaded, a retry storm worsens backlogs and latency.

## 22. Classifying Retryable vs. Permanent Errors

| Error | Typical handling |
|---|---|
| 429 / rejected execution | Backoff, reduce batch size/concurrency |
| Network timeout/reset | Idempotent retry; check that writes may already have landed |
| 502/503/504 | Bounded retry |
| Cluster unavailable | Retain backlog, back off |
| 400 mapping/parsing | DLQ, fix payload/mapping |
| 401/403 | Alert on credentials/roles, stop or pause |
| Index/alias not found | Check provisioning, do not retry forever |
| Version conflict from stale event | Mark superseded per policy |
| Unexplained version conflict | Read current version and investigate |
| Payload too large | Split batches or handle individually |

Never classify solely on broad exception classes. Inspect HTTP status, error type, and per-item context. Error messages persisted into outbox/DLQ columns must be sanitized and length-bounded.

## 23. Dead Letter Queue for Unprocessable Events

The DLQ retains events that exhausted retries or need manual intervention.

DLQ records should capture event ID, aggregate ID/version, event type and schema version, original payload or safe reference, target index/alias, attempts and last attempt timestamp, sanitized error type/message, worker/build version, remediation/replay status, and the operator or job performing replay for auditing.

Never treat the DLQ as a place to forget events. Maintain dashboards, ownership, alerts, retention policies, and replay procedures. A widespread mapping bug can fill a DLQ rapidly without surfacing any user-facing API exception.

## 24. Replaying Events from the DLQ

Once the underlying bug is fixed:

1. Select events by error type or time window.
2. Check event schema and aggregate version.
3. Verify whether the event still applies or was superseded by a newer version.
4. Rebuild the projection.
5. Send to the target index.
6. Verify item-level results.
7. Mark replay successful only after confirmation.
8. Record an audit trail.

There are two approaches: replay the original payload to re-apply the event, or read current state from the database and rebuild the aggregate's projection.

If search only needs current state, rebuilding from latest source avoids applying outdated historical events. If audit logs or event-sourced projections require it, replay in order by version.

Never replay the entire DLQ at once immediately after an outage. Start with small batches, monitor latency and 429s, and scale up gradually.

## 25. Outbox Retention and Data Cleanup

The outbox table grows continuously unless delivered events are archived or purged according to retention policies. Decide:

- How long to retain delivered events.
- Whether to archive to object storage or a data warehouse.
- How DLQ retention differs from delivered retention.
- Whether events must be kept to rebuild indices.
- Whether audit or historical investigation requires them.
- How to partition and vacuum/clean up the database.

Do not delete events the instant Elasticsearch acknowledges them if your organization needs replay after discovering a projector bug. A common policy retains delivered events for a window, then archives and deletes them in batches.

Cleanup must never lock the entire table or create giant transactions. Delete by partition, time range, or small batches.

## 26. CDC Instead of a Polling Relay

Instead of polling the outbox table, you can use Change Data Capture (CDC) reading the database transaction log.

~~~text
Application transaction
      |
      v
Business tables + outbox_event
      |
      v
Database transaction log
      |
      v
Debezium connector
      |
      v
Kafka topic
      |
      v
Outbox event consumer
      |
      v
Elasticsearch projector
~~~

The Debezium Outbox Event Router transforms outbox rows into Kafka messages by convention/configuration. Kafka retains events and consumer offsets, aiding consumer scaling and retention-based replay.

CDC removes polling queries from the database and provides near-real-time event streams. However, it adds operational infrastructure: connectors, optional schema registry, Kafka, partitioning, offset management, retention, and monitoring.

Choose polling for moderate throughput and fewer moving parts. Choose CDC when you need higher scale, large throughput, multiple consumers, or already operate an event streaming platform.

## 27. Polling and CDC Share the Same Delivery Principles

Whether the relay reads via polling or CDC, you must still handle:

- At-least-once delivery.
- Duplicate events.
- Event ordering.
- Schema evolution.
- Retries and DLQs.
- Idempotent projections.
- Source versions.
- Deletes.
- Rebuilds and replays.
- Lag monitoring.

CDC does not automatically guarantee exactly-once indexing into Elasticsearch. A consumer can index a document and crash before committing its Kafka offset, causing redelivery.

Consequently, the exact same idempotent projector can serve both a polling relay and a CDC consumer. Only the event source, ack, and checkpoint layer differ.

## 28. Schema Evolution of Outbox Events

Events can outlive individual application releases. A newer worker may read events serialized under an older payload schema.

Maintain schema_version and compatibility rules:

- Add optional fields with sensible defaults.
- Never redefine existing fields without bumping versions.
- Never remove fields still read by active/older consumers.
- Handle newly introduced enum values gracefully.
- Provide adapters or upgraders for older event schemas.
- Keep test fixtures for every supported schema version.

Consumers can dispatch to deserializers/mappers per schema version. Never let a single legacy event crash workers repeatedly without routing to the DLQ.

## 29. Rebuilding the Elasticsearch Index from Database and Outbox

A major advantage of treating Elasticsearch as a projection is being able to rebuild fresh indices cleanly.

~~~text
1. Capture consistent source/log position L0
2. Create products-v2 with target mapping
3. Read source snapshot
4. Bulk index snapshot into products-v2
5. Replay outbox/CDC events after L0
6. Catch up to a current watermark
7. Reconcile source and target
8. Switch read/write alias
9. Keep old index for rollback window
~~~

Crucially, the snapshot must align with a consistent log position. Reading a snapshot and guessing a replay start time risks missing mutations made in between.

Use version guards so older replayed events never overwrite newer documents in the new index. After catching up, reconcile by tenant/partition and verify search behavior before switching aliases.

## 30. Post-Sync Reconciliation

A relay may report every event delivered while the projection still drifts due to transform bugs, missing events, dropped deletes, or write paths that bypassed the outbox.

Reconciliation compares the source of truth against Elasticsearch:

- Document counts per tenant, type, and status.
- IDs present in source but missing in the index.
- Documents present in the index that no longer exist in source.
- Source version vs. projection version.
- Critical field values.
- Normalized hashes/checksums across key fields.
- Delete/tombstone consistency.

Never compare only whole-index totals. Two tenants can drift in opposite directions while summing to the same total.

For large datasets, shard reconciliation by tenant, ID range, or time window. When mismatches appear, enqueue scoped repair tasks that read latest source state and reindex with a version guard.

## 31. Monitoring the Outbox and Sync Lag

Essential metrics:

- Pending outbox event count.
- Oldest pending event age.
- Events created per second.
- Events claimed/processed per second.
- Events delivered per second.
- Bulk request count and item count.
- Bulk item successes vs. failures.
- Retry counts and retry delays.
- DLQ depth and oldest DLQ item age.
- Lease expirations and reclaim counts.
- Elasticsearch latency, 429s, 5xx errors, and timeouts.
- Source-to-index lag.
- Searchable lag if read-after-write guarantees apply.

Measure lag from the source occurrence timestamp, not merely from when a worker picked up the event. If an event sits pending for 10 minutes and processes in 100 ms, processing latency looks low while end-to-end lag is 10 minutes.

Track p50, p95, p99, and oldest pending age. Averages hide stuck individual events.

## 32. Micrometer Metrics in Spring Boot

You can record counters and timers with Micrometer:

~~~java
@Component
public class OutboxMetrics {

    private final MeterRegistry registry;

    public OutboxMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void delivered(String eventType) {
        registry.counter(
                "outbox.events",
                "result", "delivered",
                "event_type", eventType
        ).increment();
    }

    public void failed(String failureType) {
        registry.counter(
                "outbox.events",
                "result", "failed",
                "failure_type", failureType
        ).increment();
    }

    public void recordEndToEndLag(Duration lag) {
        registry.timer("outbox.end_to_end_lag")
                .record(lag);
    }

    public void recordProcessingTime(Duration duration) {
        registry.timer("outbox.processing_time")
                .record(duration);
    }
}
~~~

This is a minimal example. You can add gauges for pending counts and oldest age, while avoiding heavy database queries on every metrics scrape.

Never put high-cardinality values like eventId, aggregateId, documentId, or tenant ID into metric tags. Use masked structured logs and traces for per-event investigation.

## 33. Defining SLOs and Alerts

Candidate SLIs:

- p95 source-to-index lag.
- p99 source-to-searchable lag.
- Oldest pending event age.
- Percentage of events delivered within target window.
- Bulk item failure rate.
- DLQ growth rate.
- Reconciliation mismatch count.
- Consumer/checkpoint progress.

Illustrative targets:

| Indicator | Example target |
|---|---|
| p95 source-to-index lag | under 30 seconds |
| p99 source-to-searchable lag | under 2 minutes |
| Oldest pending age | under 5 minutes |
| Event delivery success | 99.9% per daily window |
| Unresolved DLQ | Not growing continuously |

Select numbers based on product requirements, refresh intervals, throughput, and cluster capacity.

Alert when backlogs climb steadily, lease expirations spike, 429s rise, bulk mapping errors appear, or DLQs sit unhandled. Every alert needs an owner and a runbook.

## 34. Securing Outbox Data

The outbox can contain snapshots of business data. Therefore:

- Grant table read privileges only to relays that need them.
- Never write tokens or secrets into payloads.
- Encrypt sensitive fields per policy.
- Restrict retention and archive access.
- Sanitize error messages before persisting.
- Avoid logging full payloads unnecessarily.
- Protect DLQs and replay tools with dedicated roles.
- Audit who replays events or modifies event state.
- Ensure tenant IDs come from trusted business data, never unauthenticated client fields.

When events hold sensitive data, review backups, snapshots, CDC topics, and logs too, since they can retain payload copies longer than primary business tables.

## 35. Testing Atomicity of Business Changes and Outbox

An integration test should prove both writes commit together or roll back together.

Commit scenario:

1. Invoke the product update service.
2. Read back the business row.
3. Read the outbox row.
4. Assert both exist with matching aggregate versions.

Rollback scenario:

1. Invoke the service inside a transaction and deliberately throw an exception before commit.
2. Assert the business row is unchanged.
3. Assert no outbox event was created.

Run these tests against a real database or Testcontainers to verify transaction semantics. Mocked repositories do not prove two tables share the same transaction manager.

## 36. Testing Crashes After Elasticsearch Writes

This is an essential test for at-least-once delivery:

~~~text
1. Claim event E42
2. Project E42 to Elasticsearch successfully
3. Simulate worker crash before markDelivered
4. Lease expires
5. Another worker claims E42
6. Project E42 again
7. Mark delivered
~~~

Verify:

- Document ID is not duplicated.
- Projection remains accurate.
- Source version does not regress.
- Outbox event is eventually marked delivered.
- Redelivery produces no unintended side effects.

If the projector triggers side effects outside Elasticsearch, those side effects must also be idempotent or isolated separately.

## 37. Testing Ordering and Stale Events

Create two events for the same aggregate:

- Version 41: old name.
- Version 42: new name.

Intentionally process version 42 before version 41. Verify the final document still holds version 42 and the new name.

Delete test:

- Version 43 is ProductDeleted.
- Version 42 update arrives late.
- Verify the document is not resurrected.

If using external versioning, integration tests must confirm conflict semantics for your server/client version. If using application-side version checks, test race conditions when two workers update the same aggregate.

## 38. Testing Bulk Partial Failures and Retries

Construct a batch with valid items, mapping-error items, 429 items in a controlled test setup, and version-conflict items.

Verify:

- Successes are marked delivered.
- Retryable failures get next_attempt_at.
- Permanent failures move to DLQ.
- Stale events are marked superseded if policy permits.
- Checkpoints/claims never skip events without durable status updates.
- Replay after fixing bugs does not regress versions.

Do not mock only a single blanket exception. Test classification per item response and include at least one integration test against real Elasticsearch.

## 39. Testing Multi-Instance Relays

With multiple workers:

1. Start two relay instances.
2. Seed a batch of outbox events.
3. Let both claim concurrently.
4. Assert no single event has an active valid lease held by both workers simultaneously.
5. Stop one worker mid-claim.
6. Wait for lease expiration.
7. Verify the surviving worker reclaims the event.
8. Verify duplicate handling and final state.

Duplicates may occur upon lease expiry or network delays, but no event may ever be lost. Verify that the claim query enforces proper locking/leasing on your production database engine.

## 40. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Database updated but Elasticsearch stale | Dual write or relay backlog | Durable outbox, monitor lag |
| Outbox event missing despite business commit | Different transaction manager or database | Share transaction resource |
| Bulk succeeds yet documents missing | Ignored item-level errors | Inspect every item |
| Events processed multiple times | Crash before ack or lease expiration | Idempotent projector |
| Document reverts to older data | Old event arrived after new event | Aggregate/external versioning |
| Deleted document reappears | Late stale update | Tombstone / version ordering |
| Workers hold DB locks too long | Calling Elasticsearch inside claim transaction | Short claims, network calls outside transactions |
| Two workers process same event | Non-atomic claim or lease race | SKIP LOCKED / lease tokens |
| Checkpoints skip failed events | Acking highest position instead of contiguous progress | Track gaps and durable state |
| Retry storm | Immediate synchronized retries | Backoff, jitter, reduce concurrency |
| DLQ grows unboundedly | Missing owner or replay process | Dashboards, alerts, runbook |
| Rebuilt index misses mutations | Snapshot not aligned with CDC position | Consistent snapshot + log position |
| Mapping errors loop forever | Permanent errors not classified | DLQ and schema repair |

## 41. Transactional Outbox Implementation Checklist

**Transactions and Schema**

- Business mutation and outbox event share one database transaction.
- Event ID is stable.
- Aggregate ID/version and schema version are recorded.
- Payload includes source timestamp.
- Events are immutable once committed.
- Retention/archival policy is defined.

**Relay**

- Claim batches in short transactions.
- Leases include expiration and ownership tokens.
- Never hold DB transactions open while calling Elasticsearch.
- Multiple workers never hold simultaneous valid leases on the same event.
- Crashes and reclaims never lose events.
- Checkpoints never skip over gaps.

**Projector**

- Document IDs are deterministic.
- Duplicate handling is idempotent.
- Version guards prevent stale writes.
- Deletes/tombstones are handled properly.
- Bulk item responses are inspected individually.
- Mapping/schema errors are classified properly.

**Retry and Recovery**

- Backoff and jitter enabled.
- Retries bounded.
- DLQ has clear owner and replay workflow.
- Index rebuild procedure uses source snapshot + change stream.
- Reconciliation runs by tenant/partition/version.
- Runbooks and recovery drills exist.

**Observability and Security**

- Monitor end-to-end lag, backlog, and throughput.
- Monitor 429s, timeouts, item errors, and DLQ.
- SLOs and alerts configured.
- Protect outbox tables, CDC topics, and DLQs.
- Never log sensitive payloads.
- Audit replays and manual repairs.

Transactional outbox creates a durable bridge between databases and Elasticsearch: business changes and events commit together, while relays safely retry downstream failures. Because delivery can repeat, projectors must be idempotent and enforce versions to prevent older events from overwriting newer state. Relays should claim in short transactions, perform network I/O outside transactions, inspect every bulk item, and park unprocessable events in retry/DLQ queues. Pairing outbox with lag monitoring, replay, reconciliation, and index rebuild workflows lets Elasticsearch catch up cleanly after outages or bad deployments without silently losing business mutations.
