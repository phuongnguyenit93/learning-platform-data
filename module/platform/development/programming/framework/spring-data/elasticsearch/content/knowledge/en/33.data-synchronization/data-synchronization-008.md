# Retries, Dead-Letter Queues, and Reconciling Missing Data

Elasticsearch is often used as a search projection for data originating in a database, message broker, or another business system. When the source data changes, the application must synchronize those changes into the index so search reflects the latest state. In practice, synchronization can fail due to network timeouts, cluster overload, unavailable shards, incompatible mappings, malformed data, or a consumer crashing mid-flight.

A reliable synchronization system must solve three problems:

- **Retry:** re-attempting transient failures with bounded attempts and appropriate backoff.
- **Dead Letter Queue (DLQ):** durably storing events that cannot be processed under the retry policy for investigation and replay.
- **Reconciliation:** comparing source data against the search index to detect and repair missing, stale, or drifted documents.

Retries handle temporary errors. The DLQ preserves unprocessable cases. Reconciliation catches discrepancies that retries and event delivery cannot guarantee to have fixed—such as events lost before entering a queue, consumers crashing after partial writes, or prolonged mapping errors.

Do not treat Elasticsearch as the sole business data store if the system requires transactions and reliable change history. A common design keeps a database or business system as the source of truth and synchronizes to Elasticsearch under eventual consistency.

## 1. Why Can Data Synchronization Miss Records?

Suppose a product management service uses a database as its primary source and Elasticsearch for search:

    Database
       |
       v
    Outbox / Change Event
       |
       v
    Message Broker
       |
       v
    Sync Consumer
       |
       v
    Elasticsearch Index

A product updated in the database may fail to appear in search for many reasons:

- The database transaction committed, yet the event was never published.
- The event was published, yet the broker or consumer failed.
- The consumer received the event, yet failed to write the document.
- A bulk request returned success at the HTTP level while an individual item failed.
- The consumer wrote the document successfully, yet died before acknowledging the message.
- Messages were processed repeatedly or out of order, causing newer data to be overwritten by stale data.
- A mapping or ingest pipeline change invalidated older events.
- Retries were exhausted without a DLQ.
- Documents were accidentally deleted, written to the wrong index, or used wrong routing.
- A reindex or alias-switch deployment did not finish cleanly.

Therefore, a sync pipeline relying solely on calling `save` and logging exceptions is not enough. You need processing state tracking, retry capabilities, durable error storage, and independent drift detection.

## 2. Classifying Errors Before Retrying

Not every error should be retried. Retrying an invalid-data error usually just increases load and delays finding the root cause.

Errors can be split into two groups:

- **Transient failure:** an error likely to resolve on its own if retried after a delay.
- **Permanent failure:** an error requiring changes to data, mapping, configuration, or logic before retrying.

Examples:

| Error | Typical classification | Action |
|---|---|---|
| HTTP 429 / rejected execution | Transient | Slow down, back off, retry failed items |
| Connection reset / temporary network failure | Transient | Bounded retry |
| Timeout with unknown outcome | Potentially transient, ambiguous state | Safe idempotent retry or reconcile first |
| Briefly unavailable shard | Transient | Back off, inspect cluster health |
| HTTP 502/503/504 from gateway or cluster | Usually transient | Bounded retry |
| Mapper parsing exception | Usually permanent | Send to DLQ, fix data or mapping |
| Mapping conflict / wrong field type | Permanent until schema fixed | Do not keep retrying |
| Missing pipeline | Configuration error | Stop or DLQ with classification |
| Unauthorized / forbidden | Auth/config error | Stop automatic retries, alert |
| Version conflict 409 | Logic or ordering conflict | Re-read, compare versions, handle per business rules |
| Document missing on update | Depends on use case | Upsert, ignore, or DLQ per contract |

Classification must be based on exception type, HTTP status, Elasticsearch error type, and operation context. Never rely solely on the overall status code of a bulk request.

## 3. Bulk API Has Partial Failures

The Bulk API executes multiple operations in a single request. A bulk request can succeed at the HTTP level while some items inside fail.

Example response:

    {
      "took": 32,
      "errors": true,
      "items": [
        {
          "index": {
            "_id": "p-100",
            "status": 201
          }
        },
        {
          "index": {
            "_id": "p-101",
            "status": 429,
            "error": {
              "type": "es_rejected_execution_exception",
              "reason": "rejected execution"
            }
          }
        },
        {
          "index": {
            "_id": "p-102",
            "status": 400,
            "error": {
              "type": "mapper_parsing_exception",
              "reason": "failed to parse field"
            }
          }
        }
      ]
    }

In this example:

- `p-100` was indexed successfully.
- `p-101` was temporarily rejected and can be retried after backoff.
- `p-102` contains data incompatible with the mapping; fix data or schema before replaying.

If the application checks only the HTTP status, it may falsely conclude the entire batch succeeded. With bulk operations, always check the `errors` field and inspect every item's result.

## 4. Retrying Only the Failed Subset

Suppose a batch of 500 items has 490 successes and 10 items returning 429. Retrying all 500 items wastes resources and risks duplicate writes. Split the 10 failed items into a separate subset for retry.

Processing flow:

    Build batch
       |
       v
    Send Bulk request
       |
       v
    Inspect each item result
       |
       +---- Succeeded --------> Mark complete
       |
       +---- Transient error --> Retry queue / backoff
       |
       +---- Permanent error --> DLQ
       |
       v
    Update checkpoint once fully handled

If the Spring Data API returns per-operation metadata, correlate results back to input items by ID or correlation key. Do not rely on positional order if an application adapter layer may reorder or filter items.

When a bulk request times out at the HTTP level, the application may not know how many items Elasticsearch processed. The state is then ambiguous. If operations are idempotent, you can retry the batch safely; if not idempotent, inspect state or design idempotency keys before retrying.

## 5. Exponential Backoff and Jitter

Immediate continuous retries can worsen an overloaded cluster. When multiple consumers retry simultaneously, they can trigger a retry storm.

Exponential backoff increases wait time across attempts:

    delay = min(maxDelay, baseDelay * 2^attempt)

Jitter adds randomness so workers do not retry at the exact same instant:

    actualDelay = random(0, delay)

Example with a 200 ms base delay and 10-second max delay:

| Retry attempt | Max delay before jitter |
|---:|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1.6 s |
| 5 | 3.2 s |
| 6 onward | Up to 10 s |

These numbers are examples. Tune them based on target latency, event lifetime, broker visibility timeout, and cluster recovery speed.

Principles:

- Cap maximum retry attempts.
- Cap maximum wait duration.
- Use jitter.
- Respect `Retry-After` if supplied by a gateway or service.
- Lower concurrency when seeing frequent 429s.
- Never infinitely retry data or permission errors.
- Record retry attempts and time spent in the system.

## 6. At Which Layer Should Retries Happen?

Retries can happen at several layers:

- HTTP client request retries.
- Elasticsearch client transport error retries.
- Service operation retries.
- Message broker message redeliveries.
- Consumer retry queues.
- Reconciliation jobs replaying missing data.

Stacked retry layers multiply total attempts. For instance, 3 HTTP client retries, 3 service retries, and 5 broker redeliveries can produce far more calls to Elasticsearch than expected.

Designate one primary layer responsible for business retries and enforce strict bounds at lower layers. HTTP client retries should handle only appropriate transport glitches; consumer retries must track which items succeeded, which failed, and when messages are acknowledged.

## 7. Idempotency Is Essential for Safe Retries

At-least-once delivery means an event can be delivered multiple times. Consumers must tolerate receiving the same event again.

Example indexing a document by stable ID:

    PUT products/_doc/p-100
    {
      "id": "p-100",
      "name": "Keyboard K8",
      "price": 120
    }

Resending the same ID and same `_source` typically yields the same final state. This is reasonably idempotent.

Conversely, an increment-style update:

    POST products/_update/p-100
    {
      "script": {
        "source": "ctx._source.viewCount += params.count",
        "params": {
          "count": 1
        }
      }
    }

If processed twice, `viewCount` increases twice. This operation is not idempotent.

Ways to improve safety:

- Derive deterministic document IDs from business keys or events.
- Store source versions or event sequences.
- Ignore events older than the processed version.
- Use conditional updates.
- Track processed event IDs when deduplication is needed.
- Design updates around desired state rather than blind increments.

## 8. Protecting Against Out-of-Order Events

Idempotency alone does not solve event ordering. Suppose a product has two versions:

    Event A: version 10, price = 100
    Event B: version 11, price = 120

If B is processed first and A arrives late, the index can revert to version 10 unless the consumer checks versions.

You can use external versioning or store the source version inside the document to reject stale events. Conceptual example:

    if (event.version <= indexed.version) {
        ignore(event);
    } else {
        index(event);
    }

When using Elasticsearch external versioning, understand `version_type` semantics and how the API client passes versions. Never generate consumer-side incrementing versions when the source has a reliable version.

If multiple events for the same aggregate require ordering, partitioning the broker by aggregate ID helps keep per-partition order. Still, retries and multiple consumers require duplicate/version handling.

## 9. What Is a Dead Letter Queue?

A Dead Letter Queue (DLQ) stores messages or items that cannot be processed successfully under the retry policy. A DLQ preserves failing data for later investigation, correction, and replay.

A DLQ is not an automatic feature of the Elasticsearch Bulk API. The application or messaging infrastructure must provide durable storage, such as:

- A Kafka dead-letter topic.
- A RabbitMQ dead-letter queue.
- A dedicated application error queue.
- A database table storing failed payloads.
- Object storage for large payloads paired with database metadata.

Elasticsearch has ingest pipelines and error responses, but does not automatically provide a full business DLQ for sync events.

A DLQ record should contain enough details to understand and replay:

| Field | Purpose |
|---|---|
| eventId | Unique identifier for deduplication |
| aggregateId/documentId | Related business document |
| eventType | Type of change |
| sourceVersion | Source data version |
| payload or payload reference | Content to reprocess |
| targetIndex | Target index at failure time |
| routing | Routing if applicable |
| errorType/errorReason | Cause of failure |
| firstFailedAt/lastFailedAt | Failure timestamps |
| attempts | Number of attempts made |
| correlationId/traceId | Distributed trace linkage |
| schemaVersion | Payload schema version |
| status | `NEW`, `INVESTIGATING`, `READY_TO_REPLAY`, `RESOLVED`, or equivalent |

Never store secrets, tokens, or unnecessary personal data in a DLQ. Apply proper access controls, encryption, retention periods, and deletion workflows.

## 10. When Should Messages Move to the DLQ?

Do not send every error to the DLQ on the first failure. A common policy:

1. Transient errors: retry with backoff.
2. Retries exhausted: route to DLQ or delayed retry topic.
3. Permanent errors: route straight to DLQ with error classification.
4. Widespread configuration errors: pause consumers and alert instead of flooding millions of messages into the DLQ.

Examples:

| Situation | Action |
|---|---|
| 429s for a few seconds | Retry with backoff |
| Brief cluster disconnect | Bounded retries |
| `price` field has unparseable string | DLQ to fix payload |
| Mapping changed while consumer still sends old schema | Pause/alert or classified DLQ |
| Target index unexpectedly deleted | Stop or pause pipeline and alert |
| Event exceeds supported `schemaVersion` | DLQ or hold in retry topic until consumer is upgraded |

A DLQ must never become an unmonitored dumping ground. Without alerts, an owner, and a replay workflow, data will sit there indefinitely.

## 11. Difference Between a DLQ and a Retry Topic

A retry topic holds messages to be retried after a delay. A DLQ holds messages that have exhausted retries or cannot be processed automatically.

| Component | Goal |
|---|---|
| Main topic/queue | Initial event delivery |
| Retry topic/queue | Delay and retry transient errors |
| DLQ | Store messages requiring investigation or intervention |
| Replay worker | Read fixed/approved items and re-submit |

Some systems use tiered retry topics with increasing delays. Others use schedulers and database retry tables. Pick the mechanism matching your broker, throughput, and operational needs.

Avoid retrying by sleeping a consumer thread for long periods. That occupies consumer slots, lowers throughput, and impacts other partitions.

## 12. Designing a Delayed Retry Queue

A pipeline flow can look like:

    Main topic
        |
        v
    Consumer
        |
        +---- Success ----> Acknowledge
        |
        +---- Transient --> Retry topic (delay)
        |                       |
        |                       v
        |                    Consumer
        |
        +---- Permanent --> DLQ
        |
        +---- Retry limit --> DLQ

Retry messages should retain the original event ID, source version, payload reference, and attempt count. When moving to a retry topic, do not mint a new event ID for the same business event.

With Kafka, you can implement per-attempt retry topics or framework retry/DLT facilities. With RabbitMQ, you can use dead-letter exchanges and TTL/delay patterns depending on broker/plugin support. Exact configurations depend on infrastructure; the general rule is that retries need delays, limits, and observability.

## 13. When to Acknowledge Messages?

With a message broker, when you acknowledge determines whether messages can be lost or duplicated.

A common rule is to acknowledge only after:

- Elasticsearch has written all items to be processed successfully; or
- Failed items have been durably persisted to a retry queue/DLQ per policy.

If you acknowledge before writing to Elasticsearch and the consumer crashes afterward, events can be lost from the queue while the index remains un-updated.

If Elasticsearch writes succeed and the consumer crashes before acknowledging, the broker can redeliver events. Thus, consumers must remain idempotent.

When bulk operations have partial failures, never acknowledge the entire batch message as if all items succeeded. Separate succeeded and failed items, or persist failed items durably before acknowledging the source message.

## 14. Using the Outbox Pattern to Prevent Lost Events

A subtle bug happens when a database transaction commits successfully yet publishing the event fails:

    UPDATE products SET price = 120 WHERE id = 'p-100';
    COMMIT;
    publish(ProductUpdated);  // fails or process stops

The database holds the new price, yet no event exists to update Elasticsearch.

The outbox pattern solves this by writing business changes and the event within the same database transaction:

    BEGIN;
      UPDATE products
      SET price = 120
      WHERE id = 'p-100';

      INSERT INTO outbox(
        event_id,
        aggregate_id,
        event_type,
        payload,
        created_at
      ) VALUES (...);
    COMMIT;

A publisher reads the outbox and sends events to the broker. Once published successfully, the publisher marks the record sent or updates its status accordingly.

Outbox does not eliminate duplicates: the publisher can send an event and die before marking it sent. Consumers still need idempotency.

Outbox guarantees source changes and event emission intent are stored in the same transaction, preventing silent event loss when the database changes.

## 15. Change Data Capture and Synchronization

Beyond outboxes, systems can use Change Data Capture (CDC) to read database transaction logs and emit changes to a broker.

Flow:

    Database transaction log
             |
             v
            CDC
             |
             v
        Message broker
             |
             v
      Elasticsearch consumer

CDC reduces the need to write custom publishers in every business service, yet still requires:

- Handling schema evolution.
- Managing offsets/checkpoints.
- Handling duplicates and ordering.
- Retries/DLQs.
- Reconciliation.
- Monitoring lag between source and index.

CDC does not automatically guarantee Elasticsearch stays synchronized. It merely provides a change stream for consumers to process.

## 16. What Is Reconciliation?

Reconciliation is the process of comparing data in Elasticsearch against the authoritative source of truth to find discrepancies.

Common discrepancy types:

- Documents present at the source but missing in Elasticsearch.
- Documents in Elasticsearch carrying older source state.
- Documents with wrong or missing fields.
- Documents deleted at the source yet still present in the index.
- Documents residing in the wrong index or routing.
- Mapping/transform changes rendering projections outdated.

Retries address known failed operations. Reconciliation uncovers discrepancies the system might not even realize happened.

If the database is the source of truth, reconciliation should compare Elasticsearch against the database or a trusted snapshot/stream. Never treat the index being verified as its own sole authority.

## 17. Reconciling by ID and Version

A simple approach is storing the source version in every Elasticsearch document:

    {
      "id": "p-100",
      "name": "Keyboard K8",
      "price": 120,
      "sourceVersion": 42,
      "updatedAt": "2026-11-13T10:00:00Z"
    }

During reconciliation:

1. Read IDs and versions from the source.
2. Read corresponding documents from Elasticsearch.
3. Compare `sourceVersion`.
4. If missing in the index or carrying a lower version, emit a repair operation.
5. If the index version exceeds the source version, check source data, out-of-order events, or cross-environment write mix-ups.

Do not compare only timestamps if systems can record skewed timestamps, low precision, or out-of-order events. Monotonically increasing per-aggregate versions are much easier to compare.

Versions must be updated inside the business transaction at the source. If versions are generated in the consumer, they cannot tell which source change is newer.

## 18. Reconciling by Checksum or Hash

When comparing only ID and version is insufficient, compute a hash over critical fields:

    sourceHash = hash(canonicalize(sourceProjection))
    indexHash  = hash(canonicalize(indexProjection))

If the hashes differ, the document may be missing fields or hold mismatched data.

Canonicalization must be deterministic:

- Sort object keys before serializing.
- Normalize numeric and date/time representations.
- Exclude volatile fields like ingest timestamps or technical metadata.
- Define null, missing, and default behaviors explicitly.
- Use the same projection logic version.

Hashes do not replace version checks. Hashes detect payload differences, whereas versions establish ordering and update currency.

For large datasets, avoid pulling the entire source and index into the application to compare hashes. Use partitions, batches, group checksums, or store projection hashes at the source.

## 19. Reconciling Missing Documents

A straightforward workflow:

    Read batch of IDs from source
             |
             v
    Multi-get IDs from Elasticsearch
             |
             v
    Compare ID sets
             |
             +---- Present ----> Compare version/hash
             |
             +---- Missing ----> Emit repair event
             |
             v
    Persist repair result/checkpoint

Avoid issuing individual GET calls per ID across thousands of documents. Use multi-get or bulk reads to cut request overhead.

When Elasticsearch reports a document is missing, distinguish:

- The ID is genuinely missing.
- Wrong routing caused the request to hit the wrong shard.
- Wrong index/alias.
- Document is moving between indexes during a reindex.
- Access permissions or filters restricted results.

Repairs should only rewrite documents from the source of truth. Never fabricate source state by guessing from incomplete search data.

## 20. Reconciling Source-Deleted Documents

Deleted documents are harder because when reading current source state, the ID is gone. Without tombstones or change logs, reconciliation cannot tell which IDs must be removed from Elasticsearch.

Strategies:

- Persist tombstones/delete events in an outbox or CDC stream.
- Retain a time-bounded list of deleted IDs.
- Compare complete ID sets per partition when scale permits.
- Use generations/snapshots and rebuild the index from source.

A tombstone can contain:

    {
      "eventId": "evt-900",
      "aggregateId": "p-100",
      "eventType": "ProductDeleted",
      "sourceVersion": 43,
      "deletedAt": "2026-11-13T10:05:00Z"
    }

Consumers use tombstones to delete documents or record deleted state depending on strategy. Retaining the tombstone version prevents late stale updates from recreating deleted documents.

## 21. Checkpointing Reconciliation Jobs

Reconciliation usually processes data in batches. If a job stops partway through, it must know where it left off.

Checkpoints can store:

- Partition or tenant.
- Last read ID.
- Source watermark or sequence.
- Snapshot start time.
- Scanned record count.
- Missing/stale/mismatched document counts.
- Job status.

Avoid storing only page numbers if source data mutates continuously and pagination order shifts. Use keyset cursors on ascending keys or appropriate snapshots/watermarks.

Example:

    {
      "jobId": "reconcile-products-2026-11-13",
      "partition": "tenant-12",
      "lastProcessedId": "p-90000",
      "sourceWatermark": 8839201,
      "status": "RUNNING"
    }

On resume, continue after the committed cursor. Only advance the checkpoint after all repairs for the batch are completed or durably persisted to a repair queue.

## 22. Snapshot vs. Delta Reconciliation

There are two common reconciliation styles:

### Full Reconciliation

Scans the entire source dataset and compares it with the index.

Pros:

- Detects older drift for which events no longer exist.
- Useful after migrations or major incidents.

Cons:

- Resource-intensive.
- Can take a long time.
- Hard to spot extra documents in the index without a complete source ID set.
- Concurrent changes during scanning require snapshot/watermark handling.

### Incremental Reconciliation

Scans only records modified after a watermark or within a time window:

    updated_at > last_successful_watermark

Pros:

- Low resource cost.
- Can run frequently.

Cons:

- Can miss changes if watermarks, timestamps, or CDC offsets are flawed.
- Requires an overlap window to absorb latency and clock skew.
- Cannot detect historical drift if records were not marked modified.

In practice, teams combine frequent incremental reconciliation with periodic or post-incident full audits.

## 23. Watermarks and Overlap Windows

If using `updatedAt` as a watermark, a job can save the last completed time and query:

    updatedAt >= previousWatermark
    AND updatedAt < currentCutoff

An overlap window re-reads a slice of time prior to the watermark:

    updatedAt >= previousWatermark - overlap

This reduces the risk of missing updates due to:

- Low timestamp precision.
- Late-committing transactions.
- Delayed events.
- Clock skew across systems.
- Previous jobs updating checkpoints before every event settled.

Overlaps produce duplicates, so repairs and consumers must be idempotent. Use source versions to ignore older or already-indexed data.

Never treat a standalone timestamp as a strict total order if multiple updates can share the same timestamp. Combine timestamps with IDs or source sequences.

## 24. Reconciling Large Datasets with PIT and `search_after`

When scanning large Elasticsearch indexes, avoid deep pagination via `from`/`size`. PIT combined with `search_after` reads a stable snapshot via cursor.

General flow:

1. Open a PIT on the target index.
2. Run searches with stable sorting and bounded page size.
3. Read the hit stream and extract the last hit's sort values.
4. Request the next page using `search_after` and the latest PIT ID.
5. Repeat until exhausted.
6. Close the PIT in a finally/cleanup path.

Example request:

    POST products/_search
    {
      "size": 500,
      "pit": {
        "id": "PIT_ID",
        "keep_alive": "2m"
      },
      "sort": [
        {
          "_shard_doc": "asc"
        }
      ]
    }

The next page passes the sort values from the last hit:

    POST _search
    {
      "size": 500,
      "pit": {
        "id": "LATEST_PIT_ID",
        "keep_alive": "2m"
      },
      "sort": [
        {
          "_shard_doc": "asc"
        }
      ],
      "search_after": [
        12345
      ]
    }

This is an illustrative example; actual sort values must be taken verbatim from the last hit. The PIT ID can be refreshed in responses, so always use the newest ID.

A PIT snapshot reflects index state only at snapshot creation time. If the source changes during reconciliation, pair it with a source watermark and an incremental pass after the snapshot.

## 25. Reconciling with Composite Aggregations

When you need to paginate buckets by key rather than individual documents, composite aggregations support bucket pagination via `after_key`.

Example grouping by tenant:

    GET products/_search
    {
      "size": 0,
      "aggs": {
        "by_tenant": {
          "composite": {
            "size": 500,
            "sources": [
              {
                "tenant": {
                  "terms": {
                    "field": "tenantId"
                  }
                }
              }
            ]
          }
        }
      }
    }

Responses include `after_key` so subsequent requests continue iterating buckets. Composite aggregations suit bucket-by-key traversal; they do not replace PIT/`search_after` for reading individual documents.

If reconciliation compares individual IDs, choose a document traversal approach. If it aggregates counts or checksums per tenant/category, composite aggregations can be useful.

## 26. Repair Jobs Must Be Idempotent

Reconciliation may detect the same missing document across consecutive runs, or a repair request may time out after Elasticsearch already wrote the document. Hence, repair operations must be idempotent.

Example repairing via stable-ID indexing:

    IndexRequest request = IndexRequest.of(i -> i
        .index("products")
        .id(sourceProduct.id())
        .document(sourceProduct)
    );

Resending the same source version and ID converges to the same final state if no newer events arrived. However, check versions so an older repair snapshot never overwrites newer consumer-indexed data.

A safe approach:

- Read the source version.
- Compare against the version in Elasticsearch.
- Write only if the source version is newer or the document is missing.
- Use external versioning/conditional updates when appropriate.
- Record repair outcomes and checkpoints.

## 27. Spring Data Elasticsearch: Handling Bulk Item Failures

Spring Data Elasticsearch provides `ElasticsearchOperations` for sending bulk operations. Exact APIs and return types vary by version. A common imperative example:

    List<IndexQuery> queries = batch.stream()
        .map(product -> IndexQuery.builder()
            .withId(product.getId())
            .withObject(product)
            .build())
        .toList();

    List<IndexedObjectInformation> indexed =
        operations.bulkIndex(
            queries,
            BulkOptions.builder()
                .withRefreshPolicy(RefreshPolicy.NONE)
                .build(),
            IndexCoordinates.of("products")
        );

The returned result can provide metadata for successfully indexed operations. How Spring Data represents item errors in exceptions or results depends on client integration and version. When granular per-error classification is required, use the Elasticsearch Java API Client directly or a persistence-layer adapter to retain `BulkResponse` item details.

Never assume `bulkIndex` always returns a result list containing both successes and failures. Read your version's method contract and check how exceptions are thrown on partial bulk failures.

### Sending Bulk via the Java API Client

With the Elasticsearch Java API Client, you can obtain `BulkResponse` and iterate over `items`:

    BulkResponse response = client.bulk(request);

    for (BulkResponseItem item : response.items()) {
        if (item.error() == null) {
            markSucceeded(item.id());
        } else {
            classifyFailure(
                item.id(),
                item.status(),
                item.error().type(),
                item.error().reason()
            );
        }
    }

This is a conceptual example. Exact request builders, item types, and source passing depend on the client version. The goal is preserving the mapping between each request item and response item for accurate failure classification.

## 28. Retries in Spring Services

Retries can be implemented in a service with a backoff loop:

    public void indexWithRetry(Product product) {
        int maxAttempts = 5;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                operations.save(product);
                return;
            } catch (TransientDataAccessException ex) {
                if (attempt == maxAttempts) {
                    throw ex;
                }

                sleepWithBackoff(attempt);
            }
        }
    }

This is illustrative code, not a complete exception classifier. Never catch every `RuntimeException` and retry blindly. Map Elasticsearch/client errors specifically into transient vs. permanent categories.

In production applications, avoid sleeping inside request threads whenever possible. For background workers, schedulers, or queues, use delayed retries to free workers while waiting.

## 29. Using Spring Retry or Resilience4j

Spring Retry or Resilience4j can provide retry/backoff/circuit-breaker mechanisms. They are application-level libraries and do not replace inspecting item-level bulk errors.

Illustrative annotation example with Spring Retry:

    @Retryable(
        retryFor = TransientDataAccessException.class,
        maxAttempts = 4,
        backoff = @Backoff(
            delay = 200,
            multiplier = 2,
            maxDelay = 5000,
            random = true
        )
    )
    public Product save(Product product) {
        return operations.save(product);
    }

Exact annotation signatures and `retryFor`/`value` attributes depend on the Spring Retry version. Enable retry configuration according to the library in use.

Notes:

- Retry annotations take effect only when calls pass through the appropriate proxy.
- Self-invocation within the same bean bypasses the proxy.
- Retrying a `save` method does not analyze bulk partial failures automatically.
- Retry only exceptions classified as transient.
- Never retry non-idempotent operations without deduplication.

## 30. Retries in Reactive Pipelines

With Reactor, use `retryWhen` for transient failures:

    Mono<Product> saved =
        reactiveOperations.save(product)
            .retryWhen(
                Retry.backoff(4, Duration.ofMillis(200))
                    .maxBackoff(Duration.ofSeconds(5))
                    .jitter(0.5)
                    .filter(this::isTransientFailure)
            );

`isTransientFailure` must classify errors based on actual exceptions. Never use unbounded `retry()` for all errors.

In reactive bulk calls, if the response contains partial item failures yet the `Mono` succeeds, `retryWhen` will not detect failed items automatically. The application must inspect the response, build a publisher solely for retryable items, and route permanent failures to the DLQ.

Never call `block` in a reactive retry path. Never call a separate `subscribe` inside a retry callback; compose the full publisher chain.

## 31. Application DLQ Records

A DTO can model an error record:

    public record DeadLetterRecord(
        String eventId,
        String aggregateId,
        String eventType,
        long sourceVersion,
        String targetIndex,
        String errorType,
        String errorReason,
        int attempts,
        Instant firstFailedAt,
        Instant lastFailedAt,
        String payloadReference
    ) {}

Large payloads or payloads containing sensitive data can be stored in separate object storage or a database; the DLQ holds only a reference. Ensure the payload reference stays accessible throughout the retention period.

DLQ persistence must be durable before acknowledging the source message. If writing to the DLQ fails, do not mark the message done under an at-least-once policy.

## 32. Safe DLQ Replays

Replaying means feeding messages from the DLQ back into processing once the root cause is fixed.

Workflow:

1. Select a batch of DLQ records by error type, target index, or time range.
2. Identify the root cause and required fix.
3. Verify payload/schema version.
4. Confirm the source version is still valid.
5. Replay to the consumer or repair worker.
6. Record the replay attempt, operator/process, and outcome.
7. Mark `RESOLVED` only after Elasticsearch holds the right state.

Never bulk-replay before fixing the root cause. If the mapping is still broken, replaying will fail repeatedly and create heavy load.

Replays must be idempotent. If an event is older than the current document, never overwrite newer state. Check source versions or re-read the source of truth before indexing.

## 33. Preventing DLQ Replays from Causing Duplicates or Reordering

Suppose the DLQ holds event version 10 while Elasticsearch already has version 12. Replaying version 10 can regress data if the consumer does not check versions.

Before replaying:

- Read the current source of truth or check source versions.
- Skip stale events if the indexed document already holds a newer version.
- To rebuild state, project from the current source rather than replaying every historical event.
- Keep event IDs for deduplication.

For events with side effects such as incrementing counters, sending notifications, or triggering payments, never replay indiscriminately. Distinguish search projection sync from business side effects.

## 34. Reconciling Against the Source of Truth

A reliable reconciliation job knows which source is authoritative. For example:

- Database is authoritative for products.
- Elasticsearch is a search projection.
- Cache is an acceleration layer that can be rebuilt.

When a discrepancy appears:

    Database product version 42
    Elasticsearch product version 40

The job should fetch current data from the database and update Elasticsearch to version 42. It should not read version 40 from Elasticsearch and try to guess which two events were missed.

If the source of truth no longer keeps deleted records, you need tombstones/change logs or ID snapshots to detect leftover documents in the index.

## 35. Reconciliation with Spring Data and Multi-Get

You can read source data in batches, then use `ElasticsearchOperations` or the Java API Client to fetch documents by ID.

Conceptual example:

    List<Product> sourceBatch = sourceRepository
        .findNextBatch(checkpoint, 500);

    List<String> ids = sourceBatch.stream()
        .map(Product::getId)
        .toList();

    // Use multi-get or an IDs query to read projections.
    // Compare versions/hashes and build repair IndexQueries for missing/stale documents.

Do not call `repository.findById` in a loop when batches hold hundreds or thousands of IDs; that creates N+1 requests.

With Spring Data, use `multiGet` or `NativeQuery` with `terms` on IDs depending on version and mapping needs. For large ID lists, split into smaller batches to avoid oversized `terms` queries.

## 36. Repairing Missing Documents via Bulk

After identifying missing or stale documents, create a repair batch:

    List<IndexQuery> repairs = outdatedProducts.stream()
        .map(product -> IndexQuery.builder()
            .withId(product.getId())
            .withObject(product)
            .build())
        .toList();

    operations.bulkIndex(
        repairs,
        BulkOptions.builder()
            .withRefreshPolicy(RefreshPolicy.NONE)
            .build(),
        IndexCoordinates.of("products")
    );

After repairing, inspect each item's result and advance the checkpoint only when the batch is handled or failures are durably persisted to a DLQ/repair queue.

If search visibility is required right after reconciliation, refresh once after the batch/job finishes. Never refresh after every single document.

## 37. Reconciling Deletes Using Tombstones

When the source emits tombstones, the consumer can delete documents in Elasticsearch:

    DeleteQuery delete = DeleteQuery.builder(productId)
        .build();

    operations.delete(delete, IndexCoordinates.of("products"));

Exact builder APIs depend on the Spring Data version. With custom routing, include routing in the delete request.

If delete event version 43 arrives before update event version 42, the consumer must prevent the older event from recreating the document. You can store tombstone versions in a store or use versioning/conditional operations.

If a document is completely deleted, its tombstone version metadata can disappear with the document. For late events, you need a place tracking delete versions or source-of-truth checks so deleted data is not resurrected.

## 38. Measuring Synchronization Health

A sync pipeline should track metrics and alerts:

| Metric | What to detect |
|---|---|
| Consumer lag | Events waiting too long to process |
| Retry count/rate | Rising transient errors |
| DLQ size | Number of unprocessable items |
| Oldest DLQ age | Stale failures sitting unresolved |
| Bulk item failure rate | Mapping, overload, or malformed data |
| 429/rejected count | Cluster under pressure |
| Indexing latency | Slow Elasticsearch writes |
| Source-to-index lag | Search projection lagging behind source |
| Reconciliation mismatch count | Missing/stale/mismatched documents |
| Repair success/failure rate | Ability to remediate drift |
| Last successful checkpoint | Whether reconciliation jobs are making progress |

Do not monitor DLQ count alone. A small DLQ with months-old records is still a problem. Track error record age and assign owners.

## 39. Alerting and Operating a DLQ

Operational procedures must answer:

- Who owns each error category?
- How quickly must new DLQ records be triaged?
- When should consumers be paused?
- When should payloads be fixed and replayed?
- When is a full index rebuild better than replaying individual events?
- Who has access to failed payloads?
- How long are payloads retained?
- How do we verify a replay fixed the right data?

Classify DLQ items by error type and schema version to group failures sharing a root cause. Dashboards should show counts, ages, top error reasons, and replay status.

If a mapping bug affects the entire consumer, pausing or throttling may be better than flooding every event into the DLQ. Implement circuit breakers or health gates for widespread configuration errors.

## 40. Reconciliation Does Not Replace Event-Driven Sync

Running full reconciliation after every single change is expensive. Event-driven sync provides fast updates; reconciliation is the safety net verifying and fixing drift.

A balanced design:

- Outbox/CDC emits changes in near real-time.
- Consumers write to Elasticsearch and retry transient failures.
- DLQs capture unprocessable items.
- Incremental reconciliation runs periodically to verify watermarks/versions.
- Full reconciliation or rebuilds run after incidents, migrations, or major projection changes.

If reconciliation finds excessive mismatches, investigate the sync pipeline rather than merely increasing repair frequency. Mass drift usually signals a bug, mapping drift, or event loss.

## 41. When Should You Rebuild the Whole Index?

Sometimes per-document repair is no longer effective:

- Major mapping or analyzer changes.
- Legacy projection logic wrote widespread bad data.
- Event history is missing and individual changes cannot be recovered.
- Index structure is corrupted or untrustworthy.

Typical rebuild workflow:

1. Create a new index with proper mappings/settings.
2. Read a data snapshot from the source of truth.
3. Bulk index in controlled batches.
4. Sync changes occurring during the snapshot via outbox/CDC or watermarks.
5. Reconcile counts, versions, and sample data.
6. Switch the alias to the new index.
7. Retain the old index during the policy rollback window.

Never delete the old index before verifying the new index and switching the alias successfully.

## 42. Handling Schema Evolution

Older events may have been created under a prior schema version. When a newer consumer receives an older event, fields may be missing or typed differently.

Payloads should carry `schemaVersion` or `eventVersion`. Consumers can:

- Support multiple schema versions.
- Upcast older payloads into the current internal model.
- Route unsupported versions to the DLQ.
- Keep raw payloads for replay once a converter is deployed.

Never modify raw DLQ events without preserving originals or an audit trail. When transforming, log the converter version and replay attempt.

Elasticsearch mappings must also evolve deliberately. Changing field types usually requires a new index and reindexing; simply retrying old events will not alter existing mappings.

## 43. Bulk Retries and Resource Limits

Retries can amplify load if batches are too large or too many workers run concurrently. When the cluster returns 429:

- Reduce concurrency.
- Reduce batch size if payloads are large.
- Increase backoff.
- Pause producers if queues grow rapidly.
- Monitor indexing pressure and write thread pools.

Never raise retry counts just to mask an overloaded cluster. Retries should help the system recover, not prolong overload.

When a batch has item errors, form a smaller retry batch containing only transient failures. This lowers overhead and avoids resending permanent failures.

## 44. Exactly-Once vs. the Reality of Synchronization

Across a database, broker, and Elasticsearch, achieving a single atomic transaction covering every component is very hard. Thus, many architectures choose at-least-once delivery paired with idempotent consumers.

At-least-once delivery may redeliver events, but does not intentionally drop events committed to the outbox/broker. Consumers handle redeliveries safely via event IDs, source versions, and idempotent writes.

Do not claim a pipeline is exactly-once merely because the broker supports transactions within its own boundaries. Broker transactions do not form a shared transaction with databases and Elasticsearch.

A more realistic goal:

- Never lose changes committed at the source.
- Events can be redelivered.
- Consumers handle duplicates safely.
- Failures are durably stored.
- Reconciliation catches residual drift.
- Replays or rebuilds can recover projections.

## 45. Example Complete Synchronization Architecture

    [Application Service]
             |
             v
    [Database Transaction]
       |             |
       |             +--> [Outbox Event]
       |                       |
       v                       v
    [Source Tables]        [Publisher]
                               |
                               v
                         [Message Broker]
                               |
                               v
                         [Sync Consumer]
                               |
                       +-------+-------+
                       |               |
                       v               v
                [Bulk Index]     [Failure Classifier]
                       |               |
                       v          +----+----+
                [Elasticsearch]   |         |
                                  v         v
                             [Retry]      [DLQ]
                                  |
                                  v
                             [Replay]

    [Reconciliation Job]
             |
             +---- Read source snapshot/watermark
             |
             +---- Compare IDs, versions, hashes
             |
             +---- Create repair events
             |
             +---- Update checkpoint

This architecture has multiple parts, each with clear responsibilities:

- Database/outbox preserves source changes and event emission intent.
- Broker transports events.
- Consumer turns events into index operations.
- Retries handle transient errors.
- DLQ captures failures needing investigation.
- Replay recovers fixed items.
- Reconciliation catches remaining drift.

## 46. Common Pitfalls

### Retrying Every Exception

Mapping, permission, or configuration errors never fix themselves. Classify transient vs. permanent before retrying.

### Infinite Retries

Infinite retries build backlogs and retry storms. Enforce max attempts, max delay, jitter, and DLQs.

### Retrying an Entire Bulk Batch When One Item Fails

Causes duplicate writes and extra load. Isolate failed items when responses provide enough detail.

### Not Checking Partial Failures

HTTP 200 does not mean every bulk item succeeded. Inspect `errors` and per-item responses.

### Lacking Idempotency

Messages can be redelivered. Use stable IDs, event IDs, source versions, or conditional updates.

### Out-of-Order Events Overwriting Newer Data

Compare source versions or maintain per-aggregate order. Never let stale events regress projections.

### Acknowledging Before Durably Saving Results

If a consumer dies after acknowledging, events can be lost. Acknowledge only after success or after durably writing failures to retry/DLQ.

### Unmonitored DLQs

A growing DLQ without alerts or replay workflows becomes a data graveyard. Track age, owner, and status.

### Replaying Before Fixing Root Causes

Replays will keep failing and generate load. Fix mappings/configs/payloads first.

### Replaying Events Older Than Current Data

Can regress target state. Check source versions and current state before replaying.

### Missing Tombstones for Deletes

Documents deleted at the source can linger forever in the index. Keep delete events or mechanisms detecting orphaned IDs.

### Reconciliation Without Checkpoints

Interrupted jobs must rescan from scratch or risk missing records. Save cursors/watermarks after batches finish safely.

### Reconciling Solely by Timestamp

Clock skew and duplicate timestamps can miss changes. Use versions/sequences, overlap windows, and idempotent repairs.

### Checking Document Counts Only

Matching totals do not guarantee matching contents. Compare IDs, versions, and hashes across key fields.

### Using Elasticsearch as Its Own Source of Truth

Reconciliation must compare against the source of truth or an independent snapshot. You cannot verify missing data using only the index under audit.

### Logging Sensitive Payloads in the DLQ

DLQs need retention, access control, and data protection. Store references when payloads are large or sensitive.

## 47. Workflow for Designing Retries, DLQs, and Reconciliation

When building a sync pipeline, follow this sequence:

1. Identify the source of truth and the Elasticsearch document projection.
2. Define event ID, aggregate ID, and source version.
3. Use outbox or CDC to prevent losing changes between database and broker.
4. Design idempotent consumers with ordering/version checks.
5. Send bulk batches appropriately sized and inspect every item result.
6. Classify transient vs. permanent errors using status and error type.
7. Retry transient failures with exponential backoff, jitter, and caps.
8. Route permanent or retry-exhausted failures to a DLQ with full metadata.
9. Acknowledge only after success or durable error persistence.
10. Build replays with version checks and idempotency.
11. Run incremental reconciliation using watermarks/overlaps.
12. Run full reconciliation or rebuilds when necessary.
13. Use PIT/`search_after` or stable cursors when scanning large indexes.
14. Persist checkpoints only after batches are handled or repairs are durably queued.
15. Monitor consumer lag, retries, DLQ age, mismatches, and repair rates.

## Conclusion

Retries, DLQs, and reconciliation address three complementary parts of a sync pipeline. Retries handle transient failures via backoff, jitter, and caps; DLQs retain unprocessable items for investigation and replay; reconciliation compares Elasticsearch against the source of truth to catch missing, stale, corrupt, or orphaned deleted documents.

Because the Bulk API has partial failures, inspect every item and retry only the failed subset when details allow. Safe retries demand idempotency and ordering via event IDs/source versions. Outbox or CDC lowers the risk of lost events, yet consumers still must handle duplicates and DLQs require operational procedures. Reconciliation needs checkpoints, watermarks/overlaps, ID/version/hash comparisons, and idempotent repairs. For large datasets, use PIT/`search_after` or composite aggregations matching traversal needs. Designing around at-least-once delivery with drift detection and repair is far more realistic than assuming an exactly-once transaction across database, broker, and Elasticsearch.
