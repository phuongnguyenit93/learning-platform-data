# saveAll and Limitations of All-or-Nothing Guarantees

In Spring Data Elasticsearch, saveAll is a convenient way to persist multiple entities through a repository. However, the method name does not mean the entire list is saved within an atomic transaction. Elasticsearch does not provide multi-document transactions in the style of relational databases; a single bulk request can succeed for some documents and fail for others.

When using saveAll, distinguish three things:

- **API at the repository layer:** accepts a collection of entities and requests that they be saved.
- **Execution at the client layer:** depending on the version and implementation, the framework may send a bulk request or execute write operations via another mechanism.
- **Outcome on the Elasticsearch side:** each document operation can succeed or fail independently. The Bulk API does not roll back items that already succeeded when another item fails.

Therefore, saveAll is helpful for reducing boilerplate and can leverage bulk indexing, but it is not an all-or-nothing guarantee. If business requirements demand knowing exactly which documents were saved, you must design item-level result tracking, error handling, and safe retries.

## 1. What Is saveAll Used For?

With a synchronous repository, you can save multiple entities in a single call:

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String> {
    }

Service:

    @Service
    public class ProductService {

        private final ProductRepository repository;

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        public Iterable<Product> saveProducts(
                List<Product> products) {
            return repository.saveAll(products);
        }
    }

saveAll takes an Iterable of entities and returns the saved entities per the repository contract. Business code does not have to call save inside a loop manually.

If the application saves a list:

    List<Product> products = List.of(
        new Product("p-101", "Keyboard", 45.0),
        new Product("p-102", "Mouse", 20.0),
        new Product("p-103", "Monitor", 220.0)
    );

    Iterable<Product> saved = productRepository.saveAll(products);

then the application asks Spring Data to store three documents. How the framework executes this underneath depends on the Spring Data Elasticsearch version and implementation used.

In implementations that support bulk operations, multiple actions are combined into a single request to reduce round trips between the application and Elasticsearch. This generally benefits throughput when indexing many documents. However, batching requests does not turn those operations into a transaction.

## 2. Bulk API Operates Per Item

The Elasticsearch Bulk API accepts multiple actions within a single HTTP request. Each action describes an operation on a document, such as index, create, update, or delete.

Example bulk request:

    POST _bulk
    { "index": { "_index": "products", "_id": "p-101" } }
    { "name": "Keyboard", "price": 45.0 }
    { "index": { "_index": "products", "_id": "p-102" } }
    { "name": "Mouse", "price": 20.0 }
    { "index": { "_index": "products", "_id": "p-103" } }
    { "name": "Monitor", "price": 220.0 }

Elasticsearch processes each action and returns a result for every item. A response can look like:

    {
      "took": 18,
      "errors": true,
      "items": [
        {
          "index": {
            "_index": "products",
            "_id": "p-101",
            "status": 201,
            "result": "created"
          }
        },
        {
          "index": {
            "_index": "products",
            "_id": "p-102",
            "status": 400,
            "error": {
              "type": "mapper_parsing_exception",
              "reason": "failed to parse field [price]"
            }
          }
        },
        {
          "index": {
            "_index": "products",
            "_id": "p-103",
            "status": 201,
            "result": "created"
          }
        }
      ]
    }

In the example:

- p-101 is created successfully.
- p-102 fails due to a parse/mapping error.
- p-103 can still be created successfully.

The HTTP-level response of the Bulk API can be HTTP 200 while the errors field is true. HTTP 200 here indicates that the bulk request was processed at the protocol level; it does not prove that every item succeeded.

The key takeaway is that each item has its own status and may have its own error. The Bulk API does not undo p-101 and p-103 merely because p-102 failed.

## 3. Why Does saveAll Lack an All-or-Nothing Guarantee?

An all-or-nothing transaction has two broad outcomes:

- All operations succeed and are committed.
- At least one operation fails, and all changes are rolled back.

The Bulk API does not work that way. Each document operation is processed independently by Elasticsearch. If one item fails due to mapping, a version conflict, or invalid data, the other items can still complete.

Even when Spring Data sends a bulk request in a single HTTP call, one HTTP call does not equal one transaction. The request is merely a transport for multiple actions; atomicity is still governed by the server-side semantics of each individual action.

You can picture it as:

    saveAll([A, B, C, D])
              |
              v
        Bulk request
              |
       +------+------+
       |      |      |
       v      v      v
       A      B      C      D
       |      |      |      |
       OK    ERROR   OK     OK
       |      |      |      |
       +------+------+
              |
              v
    A, C, D have been saved
    B needs separate handling

There is no automatic rollback step for A, C, and D.

### What If saveAll Throws an Exception?

Spring Data Elasticsearch may detect errors during writing and throw an exception depending on the implementation, version, and abstraction invoked. Some API layers may expose bulk response details or failed item lists; the repository layer may wrap failures into an exception.

When an exception occurs, do not conclude that no documents were saved. Part of the list may already have succeeded before the error was reported back to the application. Inspect item-level error details or reconcile document states by ID.

Conversely, if saveAll returns normally, that signals the operation completed under the implementation's contract without reporting an error. Still, it does not create a transactional guarantee to roll back other operations if a failure is detected at an outer layer.

## 4. Distinguishing the Repository Contract from Elasticsearch Semantics

CrudRepository.saveAll provides a multi-entity save API across the Spring Data ecosystem. This contract lets applications use consistent method calls across different repository types.

However, the repository contract does not alter the characteristics of the underlying database:

| Layer | What is provided | What must not be inferred |
|---|---|---|
| Repository saveAll | A single call to save multiple entities | Does not automatically guarantee a multi-document transaction |
| Spring Data implementation | How entities are translated into write operations | Does not guarantee every version uses the exact same bulk mechanism |
| Elasticsearch Bulk API | Batches multiple actions into one request | Does not roll back succeeded items |
| Elasticsearch document operation | Individual outcome per document | No ACID transaction spanning the entire bulk request |

Therefore, when upgrading Spring Data Elasticsearch, check the implementation and version-specific documentation if performance, exceptions, or item-level details are critical. Do not rely on assumptions that every version of saveAll produces the exact same bulk request or error structure.

## 5. saveAll Typically Uses Index Semantics

In Spring Data Elasticsearch, save and saveAll generally follow entity-by-ID save behavior. With normal index operations:

- If the document does not exist yet, Elasticsearch creates it.
- If a document with the same ID already exists, the document content can be replaced with the new content according to index operation semantics.

Example:

    Product updated = new Product("p-101", "Keyboard Pro", 59.0);
    productRepository.save(updated);

If p-101 already exists, saving with index semantics can write the new content for that document. This fits a model that stores current state, but must be understood clearly when retrying.

If business logic requires create-only behavior and rejecting existing IDs, use create semantics instead of assuming saveAll behaves as an insert-only command. A bulk create action fails with a conflict if the document ID already exists.

This matters for events or append-only data: retrying a create operation after the first attempt succeeded can return a conflict, whereas retrying an index operation with a stable ID can re-write the same document. The two choices behave differently.

## 6. Handling Item-Level Results

When the application must track per-document success/failure, it needs a stable identifier to correlate items in the response back to source records.

Example import batch:

| ID | Product | Result |
|---|---|---|
| p-101 | Keyboard | Succeeded |
| p-102 | Mouse | Failed due to mapping |
| p-103 | Monitor | Succeeded |

The application should record:

- Document ID.
- Operation type.
- HTTP/item status.
- Error type and error message.
- Retry count.
- Processing timestamp.

If using the Elasticsearch Java Client directly, BulkResponse provides information such as errors() and the list of items(). Each item response has status, id, and error if the operation failed.

Conceptual example:

    BulkResponse response = client.bulk(request);

    if (response.errors()) {
        for (BulkResponseItem item : response.items()) {
            if (item.error() != null) {
                // Record item.id(), item.status(), item.error()
            }
        }
    }

Class names and getters may vary across Java API Client versions; use the API matching your project's dependency. The core idea stays the same: inspect each item's status instead of checking only the HTTP status of the whole request.

If using repository saveAll, the abstraction may not expose complete item-level responses the way your application needs. In that case, you can:

1. Check the specific exception types in your Spring Data Elasticsearch version.
2. Use ElasticsearchOperations or a bulk API that provides more detailed results.
3. Call the Elasticsearch Java Client directly for import flows that require per-item control.
4. Record source IDs so failed items can be reconciled and reprocessed.

Do not pick an abstraction solely for shorter code if business rules need to know exactly whether each individual item succeeded.

## 7. Classifying Errors Before Retrying

Not every error should be retried. Distinguish data/configuration errors from transient errors.

| Error category | Examples | Typically appropriate handling |
|---|---|---|
| Mapping or parsing error | mapper_parsing_exception, wrong value type | Fix the data or mapping before resending |
| Insufficient permissions | HTTP 401/403 | Fix authentication/authorization; do not retry continuously |
| Missing index/resource | HTTP 404 or index error | Check provisioning and index name |
| Version conflict | HTTP 409 | Handle per business rules, check ID/version |
| Temporary overload | HTTP 429, rejected execution | Retry with backoff and concurrency limits |
| Transient service error | Some 502/503/504 errors | Retry with limits if the operation is safe |
| Timeout/connection drop | No response received | State is uncertain; must reconcile or use idempotency |

Mapping errors will generally continue failing if the same document is resent without fixing the data or mapping. Continuous retries only add load and flood error logs.

For overload errors such as 429, you can use exponential backoff with jitter:

    delay = min(maxDelay, baseDelay * 2^attempt) + jitter

Example:

- First attempt waits around 200 ms.
- Second attempt waits around 400 ms.
- Third attempt waits around 800 ms.
- Stop after a maximum number of attempts or when the allowed time budget expires.

Specific values should be tuned based on cluster latency and capacity. Avoid having all workers retry at the exact same instant, as that can cause another load spike.

## 8. Safe Retries and Idempotency

An idempotent operation means that executing the same request repeatedly does not change the final outcome beyond the first execution, according to the application's business definition.

### Using Stable IDs with Index Operations

If the application uses stable IDs and sends the same content with an index operation, retries typically converge the document to the same final state. However, if another flow updated the document between attempts, a retry can overwrite newer data.

Thus, stable IDs reduce duplicate creation risk but do not resolve concurrent update conflicts on their own. If version protection is required, use an appropriate optimistic concurrency/versioning mechanism.

### Using Create Operations

With a create operation, if the first attempt succeeded but the response was lost, retrying with the same ID can return a conflict because the document already exists. The application must distinguish a conflict caused by the earlier write succeeding from a conflict caused by a different document already claiming that ID.

### Using Auto-Generated IDs

If every retry generates a new ID, the same payload can create multiple documents. This is a common hazard when a producer sends events and a timeout leaves it unknown whether the server persisted the previous request.

For event ingestion, you can use a stable event ID from the source system or an idempotency key to prevent duplicates. If uniqueness cannot be guaranteed, accept duplicates and deduplicate downstream.

## 9. Timeouts Do Not Prove a Request Failed

A common failure pattern is:

1. The application sends a bulk request.
2. Elasticsearch receives the request and saves some or all items.
3. The connection drops before the application receives the response.
4. The application sees a timeout and assumes all items failed.
5. The application resends the entire batch.

The true state after step 3 is uncertain. Zero items may have been saved, a subset may have been saved, or all of them may have been saved. A timeout only means the application did not receive a response in time; it does not prove the server never executed the operation.

To handle this:

- Use stable document IDs.
- Track batch IDs and item IDs.
- When possible, reconcile document states before resending.
- Retry only unconfirmed items or use operations with suitable idempotent semantics.
- Persist checkpoints so the import process can resume after an application restart.

Do not blindly retry an entire batch with auto-generated IDs if duplicates are a business issue.

## 10. Split into Batches Instead of Sending All Data at Once

saveAll takes an Iterable, but that does not mean you should pass a list of millions of entities in a single call.

Oversized batches can:

- Create huge request bodies and consume excessive application memory.
- Increase processing time and single-request latency.
- Increase the amount of data needing retry on partial failure.
- Put pressure on Elasticsearch thread pools, networking, and heap.
- Cause large indexing bursts that degrade search workloads.

Split data into appropriately sized batches:

    int batchSize = 500;

    for (int from = 0; from < products.size(); from += batchSize) {
        int to = Math.min(from + batchSize, products.size());
        List<Product> batch = products.subList(from, to);

        productRepository.saveAll(batch);
    }

500 is only an illustrative example, not a universally optimal number for every system. Batch size should be tuned based on request byte size, document size, latency, throughput, and cluster resources. For large documents, fewer items per batch may be better; for small documents, larger batches may be effective.

If processing asynchronously or running multiple batches in parallel, limit concurrency. Sending too many concurrent bulk requests can cause Elasticsearch to return 429 and reduce overall throughput.

### Tracking Batch Progress

A reliable import workflow should persist state:

| Batch | Status | Notes |
|---|---|---|
| 1 | Completed | All items confirmed |
| 2 | Partial failure | Store failed ID list for reprocessing |
| 3 | Pending | Waiting for a worker to pick up |

Checkpoints must be stored durably if imports must resume after a restart. Do not keep failure lists only in process memory.

## 11. Example Batch Processing with Error Recording

With a simple repository, you can catch exceptions per batch:

    for (List<Product> batch : batches) {
        try {
            productRepository.saveAll(batch);
            markBatchCompleted(batch);
        } catch (RuntimeException ex) {
            markBatchFailed(batch, ex);
            // Inspect the exception before deciding what to retry.
        }
    }

This code marks a batch completed only when the call returns normally. If an exception occurs, do not mark the whole batch as unwritten; reconcile actual outcomes or extract item-level errors from the bulk layer.

If exact per-item handling is required, use the Bulk API directly:

    BulkResponse response = client.bulk(request);

    for (BulkResponseItem item : response.items()) {
        if (item.error() == null) {
            markDocumentIndexed(item.id());
        } else {
            recordFailure(
                item.id(),
                item.status(),
                item.error().reason()
            );
        }
    }

This is illustrative code showing how to inspect results. Exact data types and method names must be checked against your project's Elasticsearch Java Client version.

After classifying:

- Succeeded items are recorded as complete.
- Data-error items go to a dead-letter queue or remediation list.
- Transient-error items go to a retry queue.
- Uncertain-outcome items from timeouts are reconciled by ID before resending.

## 12. saveAll and Spring Transactions

Some applications place @Transactional on a service and expect saveAll calls to roll back completely on error:

    @Transactional
    public void importProducts(List<Product> products) {
        productRepository.saveAll(products);
        // More database operations
    }

Do not infer that this annotation makes multiple Elasticsearch documents an atomic transaction. Elasticsearch does not offer multi-document ACID transactions equivalent to relational database transactions.

If the application has a transaction manager for another database, that transaction does not automatically enlist Elasticsearch writes either. When the database commits but Elasticsearch fails, the two systems can drift out of sync.

If business rules require updating critical data in a database and syncing it to Elasticsearch, you can use the Transactional Outbox pattern:

1. Inside the database transaction, update business data and write an outbox event.
2. After commit, a worker reads the outbox.
3. The worker indexes the document into Elasticsearch.
4. Once Elasticsearch acknowledges, the worker marks the event as processed.
5. On transient errors, the worker retries per policy; on data errors, it moves the event to a state needing intervention.

This flow provides recoverability and eventual consistency. It does not turn the database and Elasticsearch into a distributed transaction, but it prevents losing sync events if a process stops mid-flight.

## 13. What If Business Requirements Truly Need All-or-Nothing?

First, determine which data the all-or-nothing rule applies to and within what boundary.

### Transactional Source Data

If a group of changes must succeed or fail together, keep the authoritative data in a database that supports transactions. Treat Elasticsearch as a read model/search projection synchronized from that source.

Example:

    Database transaction
       |
       +-- Update product A
       +-- Update product B
       +-- Insert outbox event
                 |
                 v
             Commit
                 |
                 v
          Outbox processor
                 |
                 v
          Elasticsearch bulk
                 |
        +--------+--------+
        |                 |
        v                 v
     Success            Partial failure
        |                 |
        v                 v
     Mark done        Retry / dead letter

The database enforces transactionality for the business data. Elasticsearch is updated asynchronously and may experience a short lag.

### Replacing an Entire Search Dataset

If the requirement is to publish an index version only after every document is loaded and verified, you can use a versioned index:

1. Create a new index, e.g., products_import_2026_11.
2. Load data into the new index in batches.
3. Collect and resolve all item failures.
4. Verify document count, mapping, and key queries.
5. Only when the entire dataset passes validation, switch the read/write alias to the new index.
6. If loading fails, keep the alias pointing to the old index and fix or delete the staging index per procedure.

This creates publish/rollback behavior at the alias level. It does not make individual bulk requests atomic, but users continue reading the old version until the new index is complete.

### Using Compensating Actions

Some workflows can record succeeded documents and run compensating operations if any item fails. This is a compensation/Saga pattern, not an Elasticsearch transaction rollback.

Compensating actions can also fail and require retries. Therefore, state and logs must be clear enough to know which documents were written, compensated, or remain pending.

## 14. Common Pitfalls

### Assuming saveAll Is a Transaction

saveAll is an API for saving multiple entities. A bulk request can have both succeeded and failed items; Elasticsearch does not roll back succeeded items. Handle results per document when business logic requires it.

### Checking Only HTTP 200 on the Bulk API

The Bulk API can return HTTP 200 with errors set to true. Read each item's result rather than marking the entire batch successful based solely on HTTP status.

### Assuming No Data Was Written When an Exception Occurs

Some items may already have succeeded before an error was raised. Reconcile item responses or check by ID before re-running the entire batch.

### Retrying Every Error

Mapping, authentication, or permission errors generally will not disappear on retry. Classify errors and retry only transient ones.

### Using Auto-Generated IDs and Retrying the Whole Batch

The first request may have already written part of the data. Retrying with fresh IDs can create duplicates. Use stable IDs or deduplication mechanisms.

### Sending Oversized Batches

Huge batches increase memory usage, latency, and retry volume. Split into batches, measure request size, and bound concurrency.

### Using @Transactional Expecting Elasticsearch Rollback

Spring transactions do not create multi-document transactions in Elasticsearch. If consistency between a database and Elasticsearch is required, use an outbox or a resilient sync pattern.

### Not Persisting Import Checkpoints

When a process stops mid-run, the application will not know which batches finished and which items need retry. Persist progress and errors durably.

## Conclusion

saveAll lets you save multiple entities via a repository and can leverage bulk indexing depending on the Spring Data Elasticsearch implementation. However, a multi-entity save call does not mean an all-or-nothing transaction. The Bulk API processes each item independently; some documents may succeed while others fail, and HTTP 200 can still accompany errors: true.

When building import flows, use stable IDs, split batches, inspect item-level results, classify errors, and retry under control. Timeouts must be treated as uncertain outcomes until reconciled. If business rules truly require publishing an entire dataset at once, load into a newly versioned index and switch the alias after verification; if source data needs transactions, keep transactions in an appropriate database and sync to Elasticsearch via an outbox. This approach accurately reflects saveAll's limits and lets systems recover safely when only part of the data is written successfully.
