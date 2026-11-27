# SeqNoPrimaryTerm and Carrying Metadata During Updates

Elasticsearch supports optimistic concurrency control using the `_seq_no` and `_primary_term` metadata pair. When reading a document, an application can retain these two values and send them along with an update or delete request. Elasticsearch performs the operation only if the document is still in the exact state the application read. If another process has modified the document, the stale request receives a version conflict error rather than silently overwriting newer data.

In Spring Data Elasticsearch, this metadata must be carried from the read result to the subsequent write operation. You can retrieve sequence number and primary term from `SearchHit`, wrap them in a DTO or an application-defined `SeqNoPrimaryTerm` type, and pass them into `IndexQuery`, `UpdateQuery`, or the Elasticsearch Java API Client matching your version.

Crucially, do not treat `_seq_no` and `_primary_term` as two business fields of the document. They are metadata managed by Elasticsearch to identify operation versions on a shard. The application retains them as a concurrency token and sends them back for conditional updates.

## 1. The lost update problem

Suppose two users simultaneously read a product whose inventory is 10. Both receive the data at nearly the same time:

```text
Initial document: stock = 10

User A reads stock = 10
User B reads stock = 10

A computes new stock = 9 and writes successfully
B computes new stock = 8 based on stale stock = 10

If B overwrites without control:
  stock = 8

A's change can be lost.
```

This is a lost update: an update based on stale data overwrites a newer update. For critical data, silent overwrites can corrupt inventory counts, order statuses, or account information.

Optimistic concurrency control lets both processes read normally, but on write Elasticsearch verifies the metadata each process read. Only one request can update the document from that exact version; the other request is rejected and must reload the latest data before deciding.

## 2. What is `_seq_no`?

`_seq_no` (sequence number) is an operation sequence number assigned by Elasticsearch within the scope of a single shard. Every data-modifying operation is recorded with its sequence number, allowing Elasticsearch to track operation ordering on the shard.

Key characteristics:

- Sequence numbers are managed at the shard level, not as a cluster-wide counter.
- Every index, update, or delete operation is recorded with a sequence number.
- Values increase along the shard's operation history.
- Two documents on different shards can share the same `_seq_no`.
- Do not use `_seq_no` as a business ID or global version number.

Example GET response:

```json
{
  "_index": "products",
  "_id": "p-100",
  "_version": 7,
  "_seq_no": 42,
  "_primary_term": 3,
  "found": true,
  "_source": {
    "name": "Wireless Mouse",
    "stock": 10
  }
}
```

In this example, the last operation on the document had sequence number 42 in the shard's history and primary term 3.

## 3. What is `_primary_term`?

`_primary_term` is the generation number of the primary shard. When a primary shard is promoted after a failure or shard allocation change, Elasticsearch increments the primary term to distinguish the operation histories of the old and new primaries.

Primary term prevents a stale request based on a previous primary's history from being mistakenly applied after the shard has moved to a different primary.

Points to remember:

- Primary term is managed at the shard level.
- Its value changes when a new primary is elected/promoted.
- It is not the number of times a document has been updated.
- Many documents on the same shard can share the same primary term.
- Do not increment primary term in the application, and do not store it inside `_source`.

## 4. Why are both values needed?

`_seq_no` identifies the operation's position in shard history; `_primary_term` identifies the primary generation that produced it. Together, the pair forms the concurrency token for a read.

```text
Concurrency token = (_seq_no, _primary_term)

Example:
  _seq_no       = 42
  _primary_term = 3
```

When sending an update with both values, Elasticsearch checks whether the new operation is still based on the current state the application read. If the metadata no longer matches, the request is rejected with a conflict.

Do not send only `_seq_no` or only `_primary_term` as a substitute for the condition pair. Optimistic concurrency control in the corresponding APIs uses both `if_seq_no` and `if_primary_term`.

## 5. Reading metadata with the GET API

GET by ID returns `_seq_no` and `_primary_term` metadata in the response:

```http
GET /products/_doc/p-100
```

Abbreviated response:

```json
{
  "_index": "products",
  "_id": "p-100",
  "_version": 7,
  "_seq_no": 42,
  "_primary_term": 3,
  "found": true,
  "_source": {
    "name": "Wireless Mouse",
    "stock": 10
  }
}
```

Default real-time GET can return the latest document by ID even if changes have not yet been refreshed for search. This is useful when the application needs to read a document and obtain its concurrency token before updating.

### Metadata does not live inside `_source`

`_seq_no`, `_primary_term`, and `_version` are hit/document metadata returned by Elasticsearch. They do not automatically become properties inside `_source`. If the application needs to carry them across multiple layers, extract them from response metadata and store them separately in a DTO or state-management object.

## 6. Reading metadata in the Search API

`_search` results can ask Elasticsearch to return each hit's sequence number and primary term using the `seq_no_primary_term` option:

```http
POST /products/_search
Content-Type: application/json

{
  "seq_no_primary_term": true,
  "query": {
    "term": {
      "status": "PUBLISHED"
    }
  }
}
```

A hit may contain:

```json
{
  "_index": "products",
  "_id": "p-100",
  "_score": 1.0,
  "_seq_no": 42,
  "_primary_term": 3,
  "_source": {
    "name": "Wireless Mouse",
    "stock": 10,
    "status": "PUBLISHED"
  }
}
```

This option is useful when fetching a list via search and then conditionally updating individual hits. Without requesting metadata, search responses may omit these two values; do not derive them from `_version` or compute them yourself.

## 7. Sending conditional updates with the Index API

The Index API supports `if_seq_no` and `if_primary_term`. Suppose the application read the document with `_seq_no = 42` and `_primary_term = 3`:

```http
PUT /products/_doc/p-100?if_seq_no=42&if_primary_term=3
Content-Type: application/json

{
  "name": "Wireless Mouse",
  "stock": 9,
  "status": "PUBLISHED"
}
```

Elasticsearch indexes the document only if the current sequence number and primary term match the condition pair. If another process updated or deleted the document after the read, the request can return HTTP `409 Conflict`.

### Note on the Index API

The Index API replaces the document's `_source` with the request body. If you only want to change a few fields, you must send the full new document or use the Update API. Do not send a partial source to the Index API expecting omitted fields to be preserved.

## 8. Sending partial updates with the Update API

The Update API also supports optimistic concurrency conditions:

```http
POST /products/_update/p-100?if_seq_no=42&if_primary_term=3
Content-Type: application/json

{
  "doc": {
    "stock": 9
  }
}
```

The request updates only the `stock` field while keeping other fields intact per update semantics. If the document changed since the application read its metadata, Elasticsearch returns a conflict.

This is the right choice when the application only modifies part of a document and wants to protect the operation from lost updates.

## 9. Conditional deletes with the Delete API

The Delete API can also use the same condition pair:

```http
DELETE /products/_doc/p-100?if_seq_no=42&if_primary_term=3
```

If the document was updated after the read, the stale delete is not allowed to remove the newer version. This is important when a process reads state before deciding to delete a document.

## 10. What happens when metadata is stale?

Suppose two requests both read token pair `(42, 3)`:

```text
Initial state:
  seq_no = 42
  primary_term = 3

Request A sends if_seq_no=42, if_primary_term=3
  -> succeeds
  -> new state seq_no = 43, primary_term = 3

Request B still sends if_seq_no=42, if_primary_term=3
  -> 409 version conflict
```

Elasticsearch does not automatically merge A's and B's changes. The application must decide how to resolve the conflict based on business logic.

### Conflict response

The response usually looks like:

```json
{
  "error": {
    "type": "version_conflict_engine_exception",
    "reason": "required seqNo [42], primary term [3]. current document has seqNo [43] and primary term [3]",
    "index": "products",
    "shard": "1",
    "index_uuid": "..."
  },
  "status": 409
}
```

The `reason` text can vary by version and scenario. Handle conflicts by HTTP status/error type rather than parsing the literal reason string.

## 11. Proper conflict-handling workflow

Upon receiving `409 Conflict`, do not immediately resend the old request with the same metadata because the token pair is still stale. A common workflow:

1. Reload the latest document via GET or an appropriate query.
2. Obtain the new `_seq_no` and `_primary_term`.
3. Evaluate whether the new change affects business logic.
4. Recompute the update payload based on the new state.
5. Send the request with the new metadata pair.
6. If conflicts persist, retry with bounded attempts and backoff, or return an error for user resolution.

Inventory example:

- Users A and B both read stock = 10.
- A subtracts 1 and writes stock = 9 successfully.
- B gets a conflict when trying to write stock = 8.
- B reloads stock = 9, checks conditions, and recomputes stock = 8.
- B retries the update with the new token.

This preserves both stock deductions if business rules permit. If B simply resent the old value 8 without recomputing, the result would still be wrong from a business perspective even though the new request succeeded.

### Retrying is not always right

If the update sets a specific state, such as "transition order to CANCELLED," inspect the latest state before retrying. If another process already moved the order to SHIPPED, do not blindly overwrite it to CANCELLED just to resolve a conflict.

## 12. Distinguishing `_seq_no`/`_primary_term` from `_version`

Elasticsearch has `_version` metadata and the `_seq_no`/`_primary_term` pair, but they are not the same mechanism.

| Metadata | Meaning | Scope |
|---|---|---|
| `_version` | Document version under Elasticsearch's versioning mechanism | Tied to document and versioning APIs |
| `_seq_no` | Operation sequence number on the shard | Shard level |
| `_primary_term` | Primary shard generation | Shard level |
| `(_seq_no, _primary_term)` | Token verifying an operation is based on the read state | Combines shard history and primary generation |

Do not take `_version` and assign it to `if_seq_no`. The two values are not interchangeable. Likewise, Spring Data's `@Version` is a separate versioning mechanism mapped to version metadata; if using seq_no/primary_term, pass the corresponding metadata pair explicitly.

## 13. Carrying metadata through DTOs in the application

A clean approach is separating business fields from concurrency metadata in API response DTOs:

```java
public record SeqNoPrimaryTerm(
        long seqNo,
        long primaryTerm) {
}

public record ProductView(
        String id,
        String name,
        int stock,
        SeqNoPrimaryTerm concurrency) {
}
```

When reading a `SearchHit`, extract the hit's metadata and package it with the data:

```java
import org.springframework.data.elasticsearch.core.SearchHit;

ProductView toView(SearchHit<ProductDocument> hit) {
    ProductDocument product = hit.getContent();

    SeqNoPrimaryTerm token = new SeqNoPrimaryTerm(
        hit.getSeqNo(),
        hit.getPrimaryTerm()
    );

    return new ProductView(
        hit.getId(),
        product.getName(),
        product.getStock(),
        token
    );
}
```

`SearchHit` metadata accessors may be exposed directly as `getSeqNo()`/`getPrimaryTerm()` or via a paired accessor across different Spring Data versions. Use the API matching your project's version; the principle is extracting them from hit metadata rather than reading them from `_source`.

If the application uses the GET API instead of search, extract metadata from the corresponding response as well. You can wrap it in a dedicated record as shown above so service/controller layers do not depend on Elasticsearch response types.

## 14. Returning concurrency tokens via REST API

Example JSON returned to a client:

```json
{
  "id": "p-100",
  "name": "Wireless Mouse",
  "stock": 10,
  "concurrency": {
    "seqNo": 42,
    "primaryTerm": 3
  }
}
```

When the client sends an update command:

```json
{
  "stock": 9,
  "concurrency": {
    "seqNo": 42,
    "primaryTerm": 3
  }
}
```

The server uses this token in the update request. If the document has changed, Elasticsearch returns a conflict and the server can translate it to HTTP `409 Conflict` for the client.

### Do not treat tokens as trusted data

Clients can send arbitrary values in JSON. A token only checks concurrency; it does not replace authentication, authorization, tenant checks, or business validation. The server must still verify the user has permission to modify that document ID and only apply the token to the appropriate index/routing.

Do not let clients pass raw index names, routing, or arbitrary queries alongside the concurrency token unless the API explicitly requires it. Keep those values under server control.

## 15. Using `IndexQuery` in Spring Data Elasticsearch

When indexing documents via `ElasticsearchOperations`, some Spring Data Elasticsearch versions allow carrying sequence number and primary term in `IndexQuery`.

Conceptual example:

```java
import org.springframework.data.elasticsearch.core.query.IndexQuery;
import org.springframework.data.elasticsearch.core.query.IndexQueryBuilder;

IndexQuery indexQuery = new IndexQueryBuilder()
    .withId(product.getId())
    .withObject(product)
    .withSeqNo(token.seqNo())
    .withPrimaryTerm(token.primaryTerm())
    .build();

operations.index(indexQuery, IndexCoordinates.of("products"));
```

`withSeqNo(...)` and `withPrimaryTerm(...)` represent how Spring Data APIs expose these two properties when supported. Builder names or overloads can vary by version. Check your dependency's Javadoc; if your version does not provide those setters, use the Elasticsearch Java API Client to send `ifSeqNo` and `ifPrimaryTerm` directly.

Note that `IndexQuery` replaces the document source. If the goal is to update just one field, consider `UpdateQuery` or the Update API to avoid overwriting fields omitted from the object.

## 16. Partial updates with `UpdateQuery`

Some Spring Data Elasticsearch versions support sequence number and primary term conditions on `UpdateQuery`. Logical usage pattern:

```java
import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;

Document partialDocument = Document.create();
partialDocument.put("stock", 9);

UpdateQuery updateQuery = UpdateQuery.builder("p-100")
    .withDocument(partialDocument)
    .withIfSeqNo(token.seqNo())
    .withIfPrimaryTerm(token.primaryTerm())
    .build();

operations.update(updateQuery, IndexCoordinates.of("products"));
```

Specific builder methods can vary across versions. If your version lacks `withIfSeqNo`/`withIfPrimaryTerm`, do not drop the conditions and assume the operation remains safe; use the client API directly or upgrade to an API that supports concurrency tokens.

When handling the update response, still catch and classify version conflicts. Passing tokens does not eliminate conflicts; it detects them properly.

## 17. Using the Elasticsearch Java API Client directly

The Elasticsearch Java API Client provides `ifSeqNo` and `ifPrimaryTerm` properties on the appropriate requests.

Update API example:

```java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.core.UpdateResponse;
import co.elastic.clients.json.JsonData;

UpdateResponse<ProductDocument> response = client.update(u -> u
    .index("products")
    .id("p-100")
    .ifSeqNo(token.seqNo())
    .ifPrimaryTerm(token.primaryTerm())
    .doc(JsonData.of(Map.of("stock", 9))),
    ProductDocument.class
);
```

Generic type parameters, `doc(...)` types, and response overloads depend on the Elasticsearch Java API Client version. The two key conditions are `.ifSeqNo(...)` and `.ifPrimaryTerm(...)`, which map to `if_seq_no` and `if_primary_term` in the REST API.

Index API example:

```java
client.index(i -> i
    .index("products")
    .id("p-100")
    .ifSeqNo(token.seqNo())
    .ifPrimaryTerm(token.primaryTerm())
    .document(updatedProduct)
);
```

Delete API example:

```java
client.delete(d -> d
    .index("products")
    .id("p-100")
    .ifSeqNo(token.seqNo())
    .ifPrimaryTerm(token.primaryTerm())
);
```

If an application uses `ElasticsearchOperations` for most queries but needs a request with concurrency conditions not yet exposed by the abstraction, it can use the client configured in the Spring context. Ensure it uses the same cluster, credentials, TLS, timeouts, and connection lifecycle management.

## 18. Bulk API and per-action metadata

The Bulk API supports sequence number and primary term conditions in each action's metadata.

Example:

```http
POST /_bulk
Content-Type: application/x-ndjson

{ "update": { "_index": "products", "_id": "p-100", "if_seq_no": 42, "if_primary_term": 3 } }
{ "doc": { "stock": 9 } }
{ "delete": { "_index": "products", "_id": "p-200", "if_seq_no": 17, "if_primary_term": 2 } }
```

Each action carries its own document's token. Do not share one sequence number/primary term pair across all documents in a batch.

### Bulk responses can partially succeed

The Bulk API can return HTTP 200 while some items receive 409 conflicts:

```json
{
  "errors": true,
  "items": [
    {
      "update": {
        "_id": "p-100",
        "status": 200,
        "result": "updated"
      }
    },
    {
      "delete": {
        "_id": "p-200",
        "status": 409,
        "error": {
          "type": "version_conflict_engine_exception",
          "reason": "..."
        }
      }
    }
  ]
}
```

The application must inspect `errors` and each item. Retry only conflicted items after reloading metadata and recomputing actions. Do not blindly resubmit the entire bulk request if other items already succeeded.

## 19. Sequence number and primary term after writing

After a successful index/update, the response can return new metadata such as `_seq_no`, `_primary_term`, and `_version`. If the application needs to perform another update based on the new result, use the fresh metadata pair from the response just received.

Do not continue reusing the token from the initial read across multiple consecutive writes. After every successful write, the document has a new sequence number. The old token will no longer match for the next operation.

Example:

```text
Read:      seq_no=42, primary_term=3
Update A succeeds
Response:  seq_no=43, primary_term=3
Update B based on state after A
Condition: if_seq_no=43, if_primary_term=3
```

If a write operation does not return the needed metadata or the application did not retain the response, perform a fresh GET on the document to obtain the new token before the next update.

## 20. Routing and concurrency tokens

Sequence number and primary term belong to the shard holding the document. If an index uses custom routing, GET/search/update/index/delete requests must use the exact routing to reach the right shard.

Example:

```http
GET /tenant-products/_doc/p-100?routing=tenant-42
```

After obtaining the token from the document, the update request must also preserve the corresponding routing:

```http
POST /tenant-products/_update/p-100?routing=tenant-42&if_seq_no=42&if_primary_term=3
Content-Type: application/json

{
  "doc": {
    "stock": 9
  }
}
```

If a request goes to a different shard due to wrong routing, the document may not be found or the metadata will not apply to the intended document. A token does not substitute for routing.

## 21. Combining concurrency control with business logic

Optimistic concurrency control only detects that a document has changed. It does not automatically decide whether that change is valid according to business rules.

Order state transition example:

```text
Read order: status = PAID
            seq_no = 20
            primary_term = 2

Application intends to transition to CANCELLED.

Meanwhile, another worker moves order to SHIPPED.

Update with old token -> 409 conflict.

Application reloads:
  status = SHIPPED

Business rule decides transition to CANCELLED is disallowed.
```

Without a concurrency token, the cancel command could overwrite the SHIPPED state. With the token, the application gets a chance to re-evaluate the latest state.

### Counter increment/decrement case

If the business logic increments/decrements a counter, you can use a server-side Elasticsearch update script to perform an atomic transformation on the document, or use concurrency control with bounded retries. Choose the option that fits the nature of the operation and control requirements.

Do not read the current number and compute an absolute value on the client if an appropriate atomic update can be used. However, scripts also need business guards and do not solve every distributed systems problem on their own.

## 22. Retry limits and backoff

If multiple writers update a hot document concurrently, immediate retries can cause continuous conflict loops. You should:

- Limit retry attempts.
- Use exponential backoff with jitter.
- Reload the document and new token before recomputing.
- Monitor 409 rates by index and use case.
- Consider splitting documents or reducing concurrent writers contending for the same document.
- Return a conflict to the client if automatic resolution is unsafe.

Illustrative retry policy:

| Attempt | Base wait |
|---:|---:|
| 1 | 20 ms |
| 2 | 40 ms |
| 3 | 80 ms |
| 4 | Stop and return conflict |

Actual timings should include jitter and be tuned to system latency. Do not retry indefinitely.

## 23. When to use `@Version` instead of SeqNoPrimaryTerm?

Spring Data Elasticsearch supports `@Version` to map Elasticsearch version metadata into an entity property. This is version-based optimistic locking.

Example:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.elasticsearch.annotations.Document;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Version
    private Long version;

    private String name;
    private int stock;

    // Constructors, getters and setters
}
```

`@Version` can fit well when the application works through entity mapping and wants Spring Data to manage a version property. The sequence number/primary term pair fits when the application wants to use Elasticsearch's concurrency tokens directly or needs to carry metadata from a search hit into a separate update request.

Do not mix both mechanisms in the same request. Choose one consistent control mechanism matching your API and Spring Data version. In particular, do not pass `_version` into `if_seq_no` or treat `@Version` as an alias for `SeqNoPrimaryTerm`.

## 24. Do not store concurrency tokens inside `_source` without good reason

You might consider adding `seqNo` and `primaryTerm` fields into the document source for clients to read back. This is usually unnecessary and error-prone:

- Elasticsearch already manages the real metadata outside `_source`.
- Values stored inside `_source` become stale right after the next update.
- Updating a source token field alongside the document creates a hard-to-manage dependency cycle.
- Clients may confuse business fields in source with engine metadata.

Extract metadata from responses and carry it via DTOs or HTTP headers/bodies according to your API contract. Store tokens in application state only if required by a specific workflow; never treat a copy as the source of truth.

## 25. Testing optimistic concurrency

Integration tests should run against a compatible Elasticsearch instance to verify the server actually enforces tokens.

Two-client concurrent read scenario:

1. Index document `p-100` with stock = 10.
2. GET the document and obtain token A.
3. GET the document again and obtain token B; both initial tokens are identical.
4. Send update A with token A, changing stock = 9; expect success.
5. Send update B with token B, changing stock = 8; expect HTTP 409.
6. GET the document; verify stock is still 9.
7. Read the new token and execute a business retry if applicable.

Example REST flow:

```http
GET /products/_doc/p-100
```

Suppose you receive `_seq_no = 42`, `_primary_term = 3`.

```http
POST /products/_update/p-100?if_seq_no=42&if_primary_term=3
Content-Type: application/json

{
  "doc": { "stock": 9 }
}
```

Sending another request with the exact old token must produce a conflict once the first succeeds.

### Additional cases to test

- Update with current token succeeds.
- Update with stale token gets 409.
- Delete with stale token does not delete an updated document.
- Bulk request with one conflicting item and other items succeeding.
- Token from a different shard/document cannot be misapplied.
- Correct routing with custom-routed indices.
- Retry reloads the new token and recomputes the business value.
- Primary shard failover does not cause the application to fabricate tokens.

## 26. Common error diagnosis

| Symptom | Possible cause | How to handle |
|---|---|---|
| HTTP 409 on update | Document changed after read | Fresh GET, evaluate, and recompute update |
| GET returns metadata but search hits do not | `seq_no_primary_term` not enabled in search request or API does not map metadata | Enable the option and check `SearchHit` accessors |
| Updates always conflict | Application reuses stale token after a successful write | Use new metadata from response or perform fresh GET |
| Document not found when using routing | Wrong or missing routing | Use the document's exact routing |
| Bulk HTTP 200 but contains errors | Some items had 409 or other errors | Inspect `errors` and each item's status |
| Confused `_version` with `_seq_no` | Mixed two metadata mechanisms | Use the proper `if_seq_no`/`if_primary_term` pair |
| Retries keep conflicting | Many writers updating a hot document | Backoff, bound retries, or change write model |

During investigation, record the index, document ID, routing, sent token, HTTP status, and error type. Avoid logging the entire `_source` if it contains sensitive data.

## 27. Process for carrying metadata from read to update

A controlled update flow can follow these steps:

```text
GET or SEARCH document
          |
          v
Read _seq_no and _primary_term
          |
          v
Wrap into SeqNoPrimaryTerm
          |
          v
Return DTO/token to service layer or client
          |
          v
Receive update request with token
          |
          v
Check permissions and business validation
          |
          v
Send update with if_seq_no + if_primary_term
          |
      +---+---+
      |       |
      v       v
   Success   409 conflict
      |       |
      v       v
Get new token  Reload and evaluate
      |       |
      v       v
Return result  Bounded retry or return conflict
```

Key principles:

1. Extract the token from the metadata of the exact document and shard.
2. Keep the `_seq_no`/`_primary_term` pair with the required ID and routing.
3. Pass both conditions in the write request.
4. After a successful write, use the new token for any further updates.
5. On conflict, reload and recompute business logic rather than resending the stale token.
6. Bound retries and record conflict metrics.

## 28. Conclusion

`_seq_no` and `_primary_term` are Elasticsearch metadata used to control concurrent updates. Sequence number marks operation ordering on a shard; primary term marks the primary shard generation. Combining the two into a concurrency token, an application can send `if_seq_no` and `if_primary_term` in Index, Update, or Delete APIs to ensure operations apply only if the document remains in the state that was read.

In Spring Data Elasticsearch, extract metadata from `SearchHit` or GET responses, wrap it into `SeqNoPrimaryTerm`/DTOs, and carry it to write operations. `IndexQuery`, `UpdateQuery`, and the Elasticsearch Java API Client provide ways to pass these conditions depending on the version. When a token is stale, Elasticsearch returns 409; the application must reload, verify business rules, recompute changes, and retry within bounds. Do not confuse this pair with `_version` or `@Version`, do not store engine metadata in `_source` as business data, and do not reuse old tokens after a successful write.

## References

- [Elasticsearch – Optimistic concurrency control](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/optimistic-concurrency-control)
- [Elasticsearch – Get API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-get)
- [Elasticsearch – Search API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-search)
- [Elasticsearch – Index API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-index)
- [Elasticsearch – Update API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-update)
- [Elasticsearch – Delete API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-delete)
- [Elasticsearch – Bulk API](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-bulk)
- [Spring Data Elasticsearch – Object mapping and versioning](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch – Search operations and SearchHit](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
