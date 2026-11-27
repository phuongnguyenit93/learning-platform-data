# Version Conflicts, Missing Documents, and Failed Updates

When working with Elasticsearch, a read or update operation can fail because the document has been modified, the document does not exist, the index has not been created yet, or the request does not satisfy write preconditions. These situations can all appear as HTTP 404, 409, or a failed item inside a bulk response, yet their causes and recovery strategies are completely different.

Spring Data Elasticsearch provides abstractions such as **ElasticsearchOperations** and **ReactiveElasticsearchOperations**. These abstractions help applications work with entities, but they do not eliminate Elasticsearch server concurrency rules and outcome semantics. Applications still need to understand document versions, optimistic concurrency control, updates/upserts, partial bulk failures, and exception classification.

This lesson explains how to identify version conflicts, distinguish document missing from index missing, choose behavior when updating a non-existent document, diagnose causes of failed updates, and design recovery without losing newer data.

## 1. Distinguishing outcomes of document operations

### 1.1. Common statuses

| Situation | Common outcome | Meaning |
|---|---|---|
| Document exists and is readable | 200 or result returned | Document was found |
| Document missing on direct GET | 404 | No document exists with that ID |
| Search finds no documents | 200, hits.total equals 0 | Query is valid but has no hits |
| Index or alias does not exist | 404, index_not_found_exception | Target resource does not exist |
| Updating a missing document | 404, document_missing_exception | Update API has no document to modify |
| Writing with a stale version condition | 409, version conflict | Document changed since it was read |
| Creating a document with an existing ID | 409, version conflict | ID is already in use |
| Request violates mapping or data rules | Usually 400 | Payload incompatible with mapping/API |
| Insufficient permissions | 401 or 403 | Authentication or authorization failed |
| Cluster rejects due to overload | Possibly 429 | Request needs throttling and retry policy handling |

Do not look only at the status code. Read the error type, index, document ID, operation type, and response body to pinpoint the exact cause.

### 1.2. GET 404 differs from search with zero hits

GET by ID asks Elasticsearch whether a specific document exists:

~~~http
GET /products/_doc/P1001
~~~

If the ID does not exist, the endpoint can return HTTP 404 with found false.

A search query with no matches usually returns HTTP 200 with an empty hits list:

~~~http
GET /products/_search
Content-Type: application/json

{
  "query": {
    "term": {
      "sku": "UNKNOWN-SKU"
    }
  }
}
~~~

These two outcomes do not equate to infrastructure errors. A missing document can be a normal business state.

### 1.3. Document missing differs from index missing

Examples:

- **document_missing_exception**: the index exists, but the document ID to update does not exist.
- **index_not_found_exception**: the index or resource referenced by the request does not exist.

Their handling also differs:

- Document missing: check the ID, processing order, retention, or creation policy.
- Index missing: check provisioning, aliases, templates, environment, and deployment order.

Do not automatically create a new index on every 404 error. Doing so can create an index with the wrong mapping or mask configuration bugs.

### 1.4. Not every delete of a missing document is an error

The Delete API can return not_found when the document no longer exists. In many use cases, deleting by ID is treated as idempotent: the end goal is that the document does not exist.

This differs from updating a missing document. Updates generally require an existing document, unless the request is explicitly configured to upsert.

Applications should clearly define whether deleting a non-existent ID counts as success, a warning, or a business error.

## 2. What is a version conflict?

### 2.1. Two clients editing the same document simultaneously

Suppose a product document currently has price 100:

1. Client A reads the document.
2. Client B reads the same document.
3. Client A changes the price to 110 and saves.
4. Client B changes the product name on the stale snapshot and saves the entire document.

Without concurrency control, B's operation can overwrite price 110 with the old price 100. This is a lost update.

A version conflict is the mechanism that detects data changed since the client read it or obtained its version token.

### 2.2. Optimistic concurrency control

Optimistic concurrency control (OCC) assumes conflicts do not happen frequently. A client reads state, processes data, and only writes if the document is still at the version the client read.

If the document has changed, the server rejects the operation so the client can decide how to resolve it.

OCC is appropriate when:

- Multiple requests can update the same document.
- You do not want to hold locks throughout processing.
- Each update must be based on the latest state.
- Lost updates are unacceptable.

### 2.3. Elasticsearch sequence number and primary term

Elasticsearch provides two values used for optimistic concurrency control:

- **_seq_no**: the sequence number of the operation that last modified the document.
- **_primary_term**: the term of the primary shard that processed that operation.

When reading a document, the response can include both values. The client passes them back on update/index/delete to require the operation to succeed only if the document remains in the exact state that was read.

Example:

~~~http
GET /products/_doc/P1001
~~~

The response may contain:

~~~json
{
  "_index": "products",
  "_id": "P1001",
  "_seq_no": 12,
  "_primary_term": 3,
  "_source": {
    "name": "Keyboard",
    "price": 100
  }
}
~~~

If the client uses these two tokens to update, Elasticsearch checks them against the current state. If the document has changed, the request is rejected with a version conflict instead of silently overwriting newer data.

### 2.4. Sending if_seq_no and if_primary_term conditions

Example updating only if the document has not changed:

~~~http
POST /products/_update/P1001?if_seq_no=12&if_primary_term=3
Content-Type: application/json

{
  "doc": {
    "price": 110
  }
}
~~~

If another client updated the document after the read, the old token pair is no longer valid and Elasticsearch returns 409.

The same concurrency condition can be used for index or delete APIs when operations must be guarded against a read snapshot.

### 2.5. Do not confuse _version with _seq_no/_primary_term

Elasticsearch also has a **_version** field for documents. This is a different versioning mechanism from the sequence number/primary term pair used for OCC.

In documentation or logs, state clearly whether you are referring to:

- Internal document version (**_version**).
- Sequence number (**_seq_no**).
- Primary term (**_primary_term**).
- The version property mapped by Spring Data via **@Version**.

Do not arbitrarily substitute one token type for another. Use the exact request parameters/APIs supported by your client and Spring Data version.

## 3. Using @Version in Spring Data Elasticsearch

### 3.1. Marking the version property

Spring Data Elasticsearch supports the **@Version** annotation to track an entity's version:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Version
    private Long version;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Double)
    private Double price;

    // Constructors, getters and setters.
}
~~~

When Spring Data reads and saves a versioned entity, the version property participates in detecting concurrent updates according to the contract of the Spring Data Elasticsearch version in use.

### 3.2. Versioned save flow

A typical flow:

1. Read the entity from Elasticsearch.
2. Spring Data maps the version into the property.
3. The application modifies the entity.
4. Call save.
5. Spring Data uses the version information to check the update.
6. If the version is no longer valid, the operation fails with an optimistic locking error.

Example:

~~~java
ProductDocument product =
    repository.findById("P1001").orElseThrow();

product.setPrice(110.0);

ProductDocument saved = repository.save(product);
~~~

If another transaction/request saved a newer version after the read, save can throw **OptimisticLockingFailureException** (or the corresponding translated exception in the version in use).

### 3.3. Catching optimistic locking exceptions

Can be handled at the service layer:

~~~java
try {
    return repository.save(product);
} catch (OptimisticLockingFailureException conflict) {
    throw new ProductUpdateConflictException(
        product.getId(),
        conflict
    );
}
~~~

In a web API, the application can translate conflicts into HTTP 409 so the caller knows the data changed and must reload or resolve the conflict.

Do not turn conflicts into a generic HTTP 500 if concurrency conflicts are an anticipated scenario in the design.

### 3.4. Version properties must be managed consistently

Do not arbitrarily reset the version property to an old value or strip it from the entity before saving. Doing so can break stale update detection.

When creating a new document, let Spring Data initialize the version per the mapping contract. When reading a document, preserve the returned version. When using DTOs, ensure the necessary version information is passed through the update use case if the application relies on it.

### 3.5. Do not equate @Version with every OCC API

**@Version** is a Spring Data-level abstraction. If an application calls the Elasticsearch Java API Client directly, it can use **if_seq_no** and **if_primary_term** explicitly.

Do not assume every Spring Data version maps @Version to the exact same internal mechanism as raw OCC tokens. Check the documentation for your release train and API before mixing both models on the same entity.

## 4. Full document updates vs. partial updates

### 4.1. save typically writes the entity representation

Repository **save(entity)** is suitable when the application intends to persist the mapped entity. If the entity has an existing ID, the index operation typically replaces the document's source according to index operation semantics.

For example, if the entity contains only:

~~~json
{
  "id": "P1001",
  "name": "Keyboard"
}
~~~

If the document in Elasticsearch previously also had price, category, and tags, writing the entire new entity can cause fields absent from the source to be lost.

Therefore, do not treat save as if it were always a partial update.

### 4.2. Update API for partial documents

The Update API allows sending a subset of fields:

~~~http
POST /products/_update/P1001
Content-Type: application/json

{
  "doc": {
    "price": 110
  }
}
~~~

Only fields sent in doc are updated according to Update API merge semantics. Other fields in _source are preserved.

Partial updates fit when a service owns only specific fields and does not want to overwrite the entire document.

### 4.3. Updates do not automatically create missing documents

By default, the Update API requires the document to exist. If the document is absent, Elasticsearch returns **document_missing_exception**.

This behavior is intentional: applications do not accidentally create new documents simply because an update command targeted the wrong ID.

If you want to create the document when absent, configure upsert explicitly.

### 4.4. Do not use save to mask update errors

A dangerous pattern is immediately calling save with an entity containing only a few fields whenever an update returns 404. That can create an incomplete document or overwrite a document concurrently created by another service.

Before falling back to create, determine:

- Is document missing a valid state?
- Which data source owns the document?
- Is there enough data to construct a complete document?
- Could another writer have just created the document?
- Is a create-only condition or idempotency key needed?

## 5. Upsert when a document does not exist

### 5.1. What is upsert?

Upsert combines update and insert:

- If the document exists, apply the update part.
- If the document does not exist, create the document from the upsert payload.

Upsert is useful for counters, aggregated states, or data where creation and update can be expressed in the same request.

Do not enable upsert by default for every update. If document missing indicates a logic bug or wrong ID, upsert can hide that bug.

### 5.2. Using the upsert field

Example:

~~~http
POST /products/_update/P1001
Content-Type: application/json

{
  "doc": {
    "price": 110
  },
  "upsert": {
    "name": "Keyboard",
    "sku": "SKU-1001",
    "price": 110,
    "active": true
  }
}
~~~

If P1001 exists, the doc part is applied. If it does not exist yet, Elasticsearch creates the document from upsert.

The upsert payload must include all required fields for a valid new document.

### 5.3. Using doc_as_upsert

If the doc payload is also the exact document to create when missing, you can use:

~~~http
POST /products/_update/P1001
Content-Type: application/json

{
  "doc": {
    "name": "Keyboard",
    "price": 110
  },
  "doc_as_upsert": true
}
~~~

When the document does not exist yet, the doc content is used as the initial source.

### 5.4. Scripted upsert

If an update uses a script and that script must also run when the document does not exist yet, consider **scripted_upsert** together with an **upsert** payload.

Conceptual example:

~~~http
POST /products/_update/P1001
Content-Type: application/json

{
  "scripted_upsert": true,
  "script": {
    "source": "ctx._source.count = (ctx._source.count ?: 0) + params.amount",
    "params": {
      "amount": 1
    }
  },
  "upsert": {
    "count": 0
  }
}
~~~

Scripted upsert can apply the script even when the document does not exist yet. Verify the exact request and script semantics in your Elasticsearch version.

### 5.5. Upsert does not solve every race condition

Two clients can send an upsert for the same ID simultaneously. Elasticsearch processes requests according to shard update and concurrency semantics, but business logic must still define how data merges.

If the upsert is a counter increment, the script must run on the latest state without external side effects. If two clients provide different values for the same field, precedence rules or a source version are needed.

## 6. retry_on_conflict and optimistic concurrency

### 6.1. retry_on_conflict for the Update API

The Update API supports **retry_on_conflict** so Elasticsearch retries an update when an internal version conflict occurs during the update.

Example:

~~~http
POST /products/_update/P1001?retry_on_conflict=3
Content-Type: application/json

{
  "doc": {
    "lastViewedAt": "2026-11-13T10:00:00Z"
  }
}
~~~

A value of 3 permits a limited number of internal retries per API semantics. It is not a retry for other error types such as mapping errors, authorization, or missing indices.

### 6.2. When is retry_on_conflict appropriate?

It can fit when:

- The update is a server-side atomic operation.
- The payload/script can be reapplied onto newer source state.
- Short-lived conflicts occur due to concurrent updates.
- The application does not need to reload the full entity to recompute changes.

With an increment script, Elasticsearch can re-run the script against the latest source. This differs from a client resubmitting a stale document built from an old read.

### 6.3. Scripts must be safe to re-execute

Do not place external side effects outside Elasticsearch in update scripts. Scripts can be re-executed during conflict retries.

Scripts should only modify _source through deterministic transformations on current state. Avoid time-dependent or random logic unless intentional.

### 6.4. retry_on_conflict does not replace if_seq_no/if_primary_term

The two conflict-handling approaches have different goals:

- **retry_on_conflict**: the server retries the update operation against newer state.
- **if_seq_no** and **if_primary_term**: the client requires writing only if the document still matches the read snapshot.

If business rules require the caller to know data changed and re-decide, OCC tokens fit better. If an atomic update can be reapplied safely, retry_on_conflict can be appropriate.

## 7. Strategies for resolving version conflicts

### 7.1. Fail fast and ask the caller to reload

For user-edited data, the simplest and safest approach is returning HTTP 409:

1. Client sends update with the version it read.
2. Server detects version conflict.
3. API returns conflict.
4. Client reloads fresh data.
5. User or application logic merges changes.
6. Client sends a new update based on the new version.

This avoids silently overwriting someone else's changes.

### 7.2. Bounded read-modify-write

A service can resolve conflicts itself by reloading the document, recalculating the change, and retrying:

~~~text
read current document and version
calculate desired state
attempt conditional write

if version conflict:
    reload current document
    recalculate change
    retry within a small bounded budget

if budget exhausted:
    return conflict or send to reconciliation
~~~

The key point is recalculating the change from the fresh data. Do not resend the exact payload constructed from the stale document.

### 7.3. Merging by field ownership

If two services own different fields, partial updates can reduce contention and overwrite risks.

Example:

- Catalog service owns name, description, category.
- Pricing service owns price, currency.
- Inventory service owns availableQuantity.

Each service only updates the fields it owns. If both update the same field, clear business rules are required.

### 7.4. Last-write-wins

Last-write-wins fits when business rules accept newer arrivals overwriting earlier values, such as certain rebuildable caches or projections.

Do not use untrusted client timestamps to determine ordering. If ordering is required, use source-system versions or controlled timestamps.

### 7.5. External versioning

If the source system has monotonically increasing versions, Elasticsearch supports external versioning to accept a document only when the source version satisfies the condition.

Conceptual example:

~~~http
PUT /products/_doc/P1001?version=42&version_type=external
Content-Type: application/json

{
  "name": "Keyboard",
  "price": 110
}
~~~

With **external**, the request is accepted only if the new version is strictly greater than the stored version. **external_gte** allows equal versions; weigh carefully because duplicate events with the same version can overwrite.

External versioning is useful for event ingestion or synchronizing from a database with its own versions. Do not use arbitrary versions without consistent ordering.

## 8. Missing documents: designing business behavior

### 8.1. Missing can be a normal state

A missing ID can mean several things:

- A user requested a product that was deleted.
- An update event arrived before the create event.
- The document expired under retention.
- A consumer received a delayed message.
- Wrong ID or inconsistent source data.
- The index has not been provisioned yet.

The application must distinguish these cases instead of handling all missing outcomes identically.

### 8.2. Distinguishing not found from system errors

At the service layer, repository results can be mapped to domain outcomes:

~~~java
public ProductDocument getProduct(String id) {
    return repository.findById(id)
        .orElseThrow(() -> new ProductNotFoundException(id));
}
~~~

Do not convert every exception into ProductNotFoundException. Connection failures, timeouts, and authorization errors are not missing documents.

### 8.3. Handling updates arriving before creates

In event-driven ingestion, an update event may arrive before a create event due to broker ordering or retries.

Options include:

- Hold the event in a retry queue waiting for create.
- Store the event in a pending store.
- Use upsert if the payload is sufficient to build a valid state.
- Read the canonical data source to rebuild the document.
- Discard old events if explicit version ordering exists.

Do not create incomplete documents lacking required fields just to avoid 404 errors.

### 8.4. Deletes and tombstones

If a document is deleted but an old event arrives late, the system could accidentally recreate the document if updates are configured to upsert.

For data synchronized from event streams, you may need tombstones or delete-event versions to prevent stale events from resurrecting deleted data.

### 8.5. Missing indices must be fixed at provisioning

If the index does not exist yet, check:

- Did deployment run migration/provisioning?
- Was the alias created properly?
- Is the index name per environment right?
- Did the template apply to the new index?
- Does the runtime principal have privileges to call required APIs?

Do not grant manage privileges to every runtime service just so they can auto-create indices upon hitting 404.

## 9. Updates failing due to mapping and data

### 9.1. Mapping conflicts

If a field is mapped as long yet the application sends an unconvertible string, the update can fail with mapper_parsing_exception.

Example mapping:

~~~json
{
  "properties": {
    "price": {
      "type": "double"
    }
  }
}
~~~

Invalid payload:

~~~json
{
  "doc": {
    "price": "free"
  }
}
~~~

This is a data/mapping error, not a version conflict. Retrying the same payload will continue to fail.

### 9.2. Defined field types cannot be changed arbitrarily

Elasticsearch does not allow changing a field directly from text to date on the same mapping as a normal update.

If a schema change is incompatible, you usually need to create a new index with the right mapping, reindex data, and switch aliases through a migration workflow.

Do not handle mapping errors by adding retries or recreating an index that holds production data.

### 9.3. Script errors

Update scripts can fail because:

- A field assumed by the script does not exist.
- Data type is wrong.
- Null access occurs.
- Script syntax is invalid.
- Script exceeds limits or violates policy.
- Runtime parameters are invalid.

Inspect both the script and input payload. You can add guards inside the script to handle missing fields, while ensuring business logic remains accurate.

### 9.4. Read-only index or cluster block

Updates can be rejected because the index has a read-only block, such as when the cluster applies the flood-stage disk watermark.

This is a cluster/storage state issue. Repeated retries will not fix it until the root cause is resolved and the block is cleared per operational procedures.

Check cluster health, disk usage, index settings, and block reasons before altering settings.

## 10. Updates failing due to security or infrastructure

### 10.1. Authentication and authorization

- 401: wrong credentials, expired, revoked, or malformed header.
- 403: authenticated principal lacks privileges or is blocked by policy.

Do not infinitely retry 401/403. Inspect API keys, roles, index patterns, and TLS.

### 10.2. Rejections and overload

429 or es_rejected_execution_exception can indicate the cluster is overloaded.

Handling direction:

- Backoff with jitter.
- Reduce concurrency.
- Reduce bulk size if appropriate.
- Bounded retries.
- Monitor write thread pools and node resources.
- Use bounded queues and backpressure.

Do not increase retry rates when the cluster is already rejecting requests.

### 10.3. Timeouts and indeterminate outcomes

If the client times out, the server may have already processed the update while the response did not return. Do not assume the request was never executed.

For write operations:

- Use stable IDs.
- Use OCC/versions or operation IDs.
- Re-read state if verification is needed.
- Retry only when the operation is safe to repeat.
- Do not generate new IDs on every attempt.

### 10.4. Connection resets or node failures

Some transport errors can happen while a request is being processed. Classify by exception and idempotency rather than relying solely on the closed connection.

If an update uses an incrementing counter script, retrying after a connection reset can increment twice if the first request succeeded. Appropriate deduplication or operation semantics must be designed.

## 11. Analyzing Bulk API update failures

### 11.1. HTTP 200 does not mean all items succeeded

The Bulk API processes multiple operations in one request. Elasticsearch can return HTTP 200 while the errors field is true because one or more items failed.

Example:

~~~json
{
  "errors": true,
  "items": [
    {
      "update": {
        "_id": "P1001",
        "status": 200,
        "result": "updated"
      }
    },
    {
      "update": {
        "_id": "P1002",
        "status": 409,
        "error": {
          "type": "version_conflict_engine_exception",
          "reason": "version conflict"
        }
      }
    },
    {
      "update": {
        "_id": "P1003",
        "status": 404,
        "error": {
          "type": "document_missing_exception",
          "reason": "document missing"
        }
      }
    }
  ]
}
~~~

In the example:

- P1001 was updated.
- P1002 hit a version conflict.
- P1003 does not exist.

The application must inspect each item response to decide recovery.

### 11.2. Retrying only failed items

Do not resend the entire bulk request when some items succeeded. Build a retry batch containing only recoverable items:

- Version conflict: reload/recalculate or apply an appropriate retry policy.
- Document missing: upsert, wait for create, or dead-letter per business rules.
- Mapping error: do not retry blindly.
- 429: backoff and shed load.
- 401/403: fix credentials/roles.

### 11.3. Bulk updates with retry_on_conflict

Update actions inside a bulk request can declare retry_on_conflict in each item's metadata, if supported by the API/version.

NDJSON example:

~~~http
POST /_bulk
Content-Type: application/x-ndjson

{"update":{"_index":"products","_id":"P1001","retry_on_conflict":3}}
{"doc":{"price":110}}
~~~

This configuration only handles conflicts according to update action semantics. It does not automatically resolve document missing, mapping errors, or security failures.

### 11.4. Keeping the mapping between request and response items

Bulk response items are returned in the order of operations in the request. When filtering failed items, preserve the ID, operation type, and original payload so you can identify the exact operation to retry or dead-letter.

Do not rely only on array index positions if batches may be split, merged, or reordered in other layers.

## 12. Using the Elasticsearch Java API Client for OCC

### 12.1. Reading a document and obtaining concurrency tokens

The Java API Client can return response metadata including sequence number and primary term depending on the API called.

Conceptual pattern:

~~~java
GetResponse<ProductDocument> response =
    client.get(
        request -> request
            .index("products")
            .id("P1001"),
        ProductDocument.class
    );

if (!response.found()) {
    throw new ProductNotFoundException("P1001");
}

long seqNo = response.seqNo();
long primaryTerm = response.primaryTerm();
ProductDocument current = response.source();
~~~

Accessor names and response types must match the Elasticsearch Java API Client version in the project.

### 12.2. Conditional update

Example sending an update with the two tokens just read:

~~~java
UpdateResponse<ProductDocument> response =
    client.update(
        request -> request
            .index("products")
            .id("P1001")
            .ifSeqNo(seqNo)
            .ifPrimaryTerm(primaryTerm)
            .doc(Map.of("price", 110.0)),
        ProductDocument.class
    );
~~~

If the tokens are stale, the server returns a version conflict. The client can reload and make a business decision.

This uses the low-level Java API Client. If the same application uses Spring Data repositories, standardize which layer owns concurrency to avoid two unsynchronized version mechanisms.

### 12.3. Reloading and recalculating changes

Handling pattern:

~~~java
public ProductDocument updatePrice(
        String id,
        double requestedPrice) {

    for (int attempt = 1; attempt <= 3; attempt++) {
        ProductSnapshot current = loadWithConcurrencyToken(id);

        ProductDocument updated =
            applyPriceChange(current.document(), requestedPrice);

        try {
            return conditionalUpdate(
                id,
                updated,
                current.seqNo(),
                current.primaryTerm()
            );
        } catch (VersionConflictException conflict) {
            if (attempt == 3) {
                throw new ProductUpdateConflictException(id, conflict);
            }
        }
    }

    throw new IllegalStateException("Unreachable");
}
~~~

This snippet is pseudo-code illustrating read-modify-write. In a real application, define how applyPriceChange resolves concurrent changes and how client exceptions are classified.

Do not use an infinite loop. Every conflict retry must be bounded, optionally with a small backoff if contention is high.

## 13. Error handling in Spring Data Elasticsearch

### 13.1. Exception translation

Spring Data can translate client errors into exceptions within the Spring Data/DAO ecosystem. Exact names and hierarchies depend on the version and API path.

Groups to recognize:

- OptimisticLockingFailureException: conflict when updating by version.
- DataAccessResourceFailureException or corresponding transport exception: connectivity/infrastructure.
- DataIntegrityViolationException or mapping-related exception: data invalid per contract.
- NoSuchIndexException or corresponding exception: index/resource missing if translated by the abstraction.
- Exceptions from the Elasticsearch Java API Client: may require reading status and error type from the response.

Do not catch Exception and treat every error as retryable.

### 13.2. Repository findById

With imperative repositories:

~~~java
Optional<ProductDocument> product =
    repository.findById(id);
~~~

Missing documents are typically represented by Optional.empty().

With reactive repositories:

~~~java
Mono<ProductDocument> product =
    reactiveRepository.findById(id);
~~~

Missing documents are typically represented by Mono.empty().

This is an empty-result state, not an error signal. If business rules require the document to exist, translate empty into a domain exception at the service layer.

### 13.3. ElasticsearchOperations get/find

get, search, or multiGet methods have different contracts. Some APIs may return null, an empty collection, or results with missing entries depending on the operation.

Read the Javadoc for your exact version before assuming how missing results are represented. Do not turn null into an infrastructure error.

### 13.4. UpdateQuery and UpdateResponse

Spring Data Elasticsearch provides update abstractions to send partial updates. How UpdateQuery and Document are constructed and how UpdateResponse is read depend on the version.

When using this abstraction, determine:

- Is the update configured for upsert?
- Does the response expose updated, created, or noop results?
- Does it expose enough per-item status/error detail for recovery?
- Which API passes OCC/version tokens?
- Are exceptions translated by Spring or kept as client exceptions?

If you need item-level metadata or OCC parameters not exposed by the abstraction, you can use the Elasticsearch Java API Client inside an isolated component.

### 13.5. Do not let abstractions hide error details

A repository/service layer should translate technical errors into meaningful domain results, while preserving causes and important metadata such as status, error type, index, document ID, and operation.

This information helps logging, retry policies, and observability distinguish conflicts from missing documents or mapping errors.

## 14. Designing safe retries for updates

### 14.1. Retrying the same stale payload usually fails

If OCC rejects because the document changed, resending the same payload with the same version token will continue to conflict.

You must reload the state and recalculate the update, or return a conflict so the caller decides.

### 14.2. Limiting retries

Prolonged contention can cause multiple clients to repeatedly read and rewrite the same document. Unbounded retries increase load and prolong requests.

Configure:

- Maximum retry attempts.
- Backoff and jitter when multiple writers contend.
- Overall deadline.
- Conflict rate metrics.
- Mechanism to return 409 or enqueue operations once the budget is exhausted.

### 14.3. Retries must not hide business conflicts

Some conflicts cannot be resolved automatically:

- Two people editing the shipping address simultaneously.
- Two transactions changing order status in incompatible directions.
- Two data sources owning the same field.
- New and old events arriving out of order.

These cases require business rules: reject, merge, source precedence, version ordering, or reconciliation.

### 14.4. Atomic scripts can reduce read-modify-write

If a transformation can be expressed as a server-side atomic script, the client does not need to read the document and overwrite the entire source.

Example incrementing a counter:

~~~http
POST /products/_update/P1001
Content-Type: application/json

{
  "script": {
    "source": "ctx._source.viewCount = (ctx._source.viewCount ?: 0) + params.increment",
    "params": {
      "increment": 1
    }
  }
}
~~~

The script runs against the document's current state, reducing lost-update risk compared to read-modify-save of the entire source. However, if a client retries the same command after a timeout, the counter can still increment twice if the first attempt succeeded. Preventing duplicates requires operation IDs or deduplication logic.

## 15. Observing and diagnosing update failures

### 15.1. Structured logging

When an update fails, log the following fields:

- Index or alias.
- Document ID.
- Operation type: index/update/delete.
- Status code.
- Elasticsearch error type.
- Version or OCC token if permitted.
- Retry attempt.
- Correlation/batch ID.
- Request duration.
- Outcome after recovery.

Do not log the entire source if it contains sensitive data.

### 15.2. Metrics to monitor

Track:

- Successful updates count.
- Noop updates count.
- Document missing count.
- Index missing count.
- Version conflict count.
- 400 mapping/script error count.
- 401/403 count.
- 429/rejection count.
- Retry count and retry exhaustion.
- Bulk item failures by error type.
- Update latency p50/p95/p99.

Do not use document ID as a metric label because cardinality can grow very large. Use logs/traces for specific identifiers.

### 15.3. Using conflict rate to locate contention

If conflicts spike, check:

- Are multiple workers processing the same key?
- Are batches being duplicated?
- Are consumers parallelizing more than needed?
- Has an aggregate document become a hot spot?
- Can the document be split or updates shifted to event aggregation?

Do not merely increase retry_on_conflict. More retries may reduce visible errors while masking poor contention design.

### 15.4. Tracking missing documents by source

Increasing missing documents can indicate:

- Wrong event ordering.
- Producers emitting update events before create events.
- Retention deleting documents too early.
- Wrong index/alias per environment.
- Consumers using inconsistent IDs.
- Ongoing reindexing or alias switches.

Group by operation and event source to locate the root cause.

## 16. Testing version conflicts and missing documents

### 16.1. Testing document missing

Create a non-existent ID and verify:

- Repository findById returns empty.
- Non-upsert update returns a document-missing error per the API.
- Upsert update creates the document if that is required behavior.
- Missing delete is handled per the application's contract.

### 16.2. Testing optimistic concurrency

An integration test should:

1. Create a document.
2. Read the document and retain its version/OCC tokens.
3. Update the document via a second client.
4. Send an update using the stale tokens.
5. Verify 409 or the corresponding optimistic locking exception.
6. Re-read the document and verify the second writer's newer data remains intact.

This test proves the system detects stale updates rather than merely checking annotations.

### 16.3. Testing retries with recalculation

Simulate or create a real conflict:

- First writer reads version A.
- Another writer saves version B.
- First writer receives conflict.
- First writer reloads B.
- Recalculates the update based on B.
- Successfully writes the new version.

Verify no fields updated by the second writer are lost.

### 16.4. Testing bulk partial failures

Send a bulk request containing:

- One valid item.
- One conflicting item.
- One missing document item.
- One mapping error item.

Verify the response is classified per item, only appropriate items are retried, and successful items are not resent.

### 16.5. Testing concurrent writers

Use multiple threads or workers concurrently updating the same document. Check:

- No lost updates when OCC is enabled.
- Retry budget is respected.
- Conflicts are returned clearly when retries are exhausted.
- Conflict metrics increment properly.
- No retry storms are created.

## 17. Common errors

| Symptom | Possible cause | Handling direction |
|---|---|---|
| 409 when saving entity | Stale version or document changed | Reload, merge, or return conflict |
| Newer updates lost | Overwriting full source from stale entity | Use OCC or partial updates |
| 404 on update | Document ID does not exist | Determine whether missing is valid; choose upsert or business handling |
| 404 on all operations to same index | Index/alias does not exist | Check provisioning and aliases |
| Search returns 200 with no hits | Query does not match documents | Check query, refresh, and data |
| Delete returns not_found | Document already absent | Handle per idempotent contract |
| 400 mapper_parsing_exception | Incompatible field type/payload | Fix data or migrate mapping |
| Script exception | Invalid script or missing field | Inspect script and input |
| 403 on update | Missing write privileges | Check role and index pattern |
| 429 on update | Cluster overloaded | Backoff, jitter, and reduce concurrency |
| Update creates unintended documents | Upsert enabled too broadly | Enable upsert only when business rules permit |
| Conflict retries keep failing | Resending stale payload or tokens | Reload and recalculate state |
| Counter incremented multiple times | Retrying update script after timeout | Use event ID/deduplication |
| Bulk HTTP 200 yet missing data | Item errors ignored | Classify each bulk item |
| Runtime auto-creates wrong mapping index | Provisioning privileges granted to runtime | Separate migration/provisioning from writers |

## 18. Procedure for handling a failed update

When an update operation fails:

1. Record index/alias, document ID, operation, and status.
2. Read error type/reason to distinguish missing, conflict, mapping, security, and overload.
3. If document missing, verify the index exists and determine create/upsert policy.
4. If version conflict, identify which fields another writer modified.
5. Choose fail-fast, merge, read-modify-write, or atomic scripts per business rules.
6. If retrying, bound attempts and recalculate from fresh state.
7. Do not retry mapping, authorization, or fixed configuration errors.
8. For bulk, retry only appropriate failed items.
9. Retain operation ID/version to prevent duplicates on timeouts or redeliveries.
10. Record metrics, logs, and alerts by error type.
11. Test race conditions and negative cases against real Elasticsearch.
12. Review document/field ownership if conflicts recur.

## 19. Key takeaways

- Version conflicts typically indicate data changed since it was read; they protect the application from lost updates.
- Elasticsearch OCC uses **_seq_no** and **_primary_term**; do not confuse them with **_version**.
- Spring Data Elasticsearch supports **@Version** to detect concurrent updates according to the version contract.
- Document missing differs from index/alias missing; both return 404 but require different handling.
- Repository findById typically represents missing with **Optional.empty()** or **Mono.empty()**.
- save writes the entity representation; use the Update API when you only want to modify part of a document.
- Updates do not automatically create missing documents; use upsert, doc_as_upsert, or scripted_upsert when business rules permit.
- retry_on_conflict is a conflict retry for the Update API, not a generic retry for all errors.
- With stale OCC tokens, do not resend the same payload; reload and recalculate or return HTTP 409.
- Update scripts can be re-executed; do not put external side effects inside scripts.
- Timeouts do not prove a write did not happen; design stable IDs and deduplication.
- Bulk responses can be HTTP 200 while some items fail; handle each item individually.
- Mapping, script, security, and overload errors require distinct recovery paths.
- Separate provisioning privileges from runtime services to avoid applications auto-creating misconfigured indices.
- Track conflict rates, missing rates, update failures by error type, and retry exhaustion.

Version conflicts, missing documents, and failed updates are three distinct signals about data state or environment state. By classifying root causes accurately, using OCC to protect concurrent updates, upserting only intentionally, and retrying from fresh state, Spring Data Elasticsearch applications can recover from errors without losing valid changes or creating unintended data.
