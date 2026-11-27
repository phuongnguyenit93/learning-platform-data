# Optimistic Concurrency with Sequence Number and Primary Term

When multiple applications concurrently read and update an Elasticsearch document, one write can accidentally overwrite changes from another write. Optimistic concurrency control (OCC) detects this situation by requiring a write to succeed only if the document is still at the exact version the client read.

Elasticsearch provides two values to implement this mechanism:

- **Sequence number (_seq_no):** the sequence number of the most recent write operation applied on the shard containing the document.
- **Primary term (_primary_term):** the generation of the primary shard that assigned that sequence number.

The client reads the document, retains both values, and sends them in the next index, update, or delete request via the **if_seq_no** and **if_primary_term** conditions. Elasticsearch accepts the operation only if the token pair still matches the current state. If the document has changed or the primary shard has been replaced, the operation is rejected with a version conflict error instead of silently overwriting newer data.

## 1. Why is optimistic concurrency needed?

Suppose the inventory of product P-100 is currently 10. Two requests read this same value:

~~~text
Time            Request A                  Request B
----------------------------------------------------------------
t1              Read stock = 10
t2                                         Read stock = 10
t3              Compute stock = 8
t4                                         Compute stock = 7
t5              Write stock = 8
t6                                         Write stock = 7
~~~

The final result is 7. Request A's change is overwritten by B, even though both requests were based on the same initial value. This is a lost update.

If the two operations were actually two independent inventory decrements, the expected result might be 5. If B changes stock according to a different rule, the application also needs to know the underlying data changed before deciding to write.

OCC solves this by attaching a version condition to the write:

1. The client reads the document and receives a version token.
2. The client computes the new value from the document it read.
3. The client sends the new value along with the token.
4. Elasticsearch compares the token against the current version.
5. If the token is still valid, the write succeeds; if it is stale, a conflict is returned.

OCC is suitable when conflicts happen infrequently and the application can handle them when detected. This mechanism does not lock the document while the client is thinking or computing.

## 2. What is a sequence number?

Every write operation applied by Elasticsearch on a shard is assigned a sequence number. Sequence numbers increase in the order of write operations on that shard.

A document hit can return metadata:

~~~json
{
  "_index": "products",
  "_id": "P-100",
  "_seq_no": 17,
  "_primary_term": 3,
  "_source": {
    "name": "Keyboard",
    "stock": 10
  }
}
~~~

In this example:

- **_seq_no = 17** is the sequence number of the most recent operation that produced this document version.
- **_primary_term = 3** is the primary term of the primary shard that assigned that sequence number.
- **_source** is the document content that was read.

Sequence numbers are scoped per shard, not a cluster-wide counter. Two documents on two different shards can have the same sequence number. Therefore, do not use sequence numbers alone as global IDs or to compare change ordering across shards.

When a document is successfully written again, the sequence number of the new version changes. Clients can use that value to detect that another write occurred since their read.

## 3. What is a primary term?

Primary term identifies the generation of the primary shard. When Elasticsearch elects a new primary shard, the primary term is incremented. This distinguishes operations issued by an old primary from those issued by a new primary.

Sequence number and primary term must be used together:

| Token | Indicates | Role |
| --- | --- | --- |
| _seq_no | Operation order on the shard. | Detects that the document has had a newer write operation. |
| _primary_term | Primary shard generation. | Distinguishes operations belonging to old vs. new primary terms. |
| Pair of both values | Exact version the client read. | Optimistic concurrency condition for the next write. |

Checking only the sequence number might fail to distinguish operations belonging to different primary generations. The primary term adds the context needed to protect operations during failover or primary changes.

Do not increment or compute these two values in your application. Elasticsearch assigns and manages them.

## 4. Retrieving sequence number and primary term on read

### 4.1. Get API

With the Get API, add the parameter `seq_no_primary_term=true`:

~~~http
GET /products/_doc/P-100?seq_no_primary_term=true
~~~

The response may contain:

~~~json
{
  "_index": "products",
  "_id": "P-100",
  "_version": 8,
  "_seq_no": 17,
  "_primary_term": 3,
  "found": true,
  "_source": {
    "name": "Keyboard",
    "stock": 10
  }
}
~~~

The application stores both `_seq_no` and `_primary_term` alongside the data it just read.

### 4.2. Search API

When fetching documents via search, request sequence number and primary term metadata:

~~~http
GET /products/_search
Content-Type: application/json

{
  "seq_no_primary_term": true,
  "query": {
    "term": {
      "_id": "P-100"
    }
  }
}
~~~

Each matching hit can include `_seq_no` and `_primary_term` alongside `_index`, `_id`, `_score`, and `_source`.

If the client needs to update the exact document it found, it must retain:

- The actual index of the hit.
- The document ID.
- The routing value if the document was indexed with custom routing.
- The sequence number.
- The primary term.
- The content or business data used to compute the change.

Sequence number and primary term are meaningful only within the scope of the document/shard from which they were read. Do not take one document's token to write a different document.

### 4.3. Do not confuse tokens with update timestamps

Sequence number is not a timestamp. Do not use it to display update date/time or compare time across shards. If business logic needs update timestamps, store a dedicated timestamp field such as `updatedAt`.

## 5. Conditional writes with if_seq_no and if_primary_term

When indexing an existing document, send both conditions in the request:

~~~http
PUT /products/_doc/P-100?if_seq_no=17&if_primary_term=3
Content-Type: application/json

{
  "name": "Keyboard",
  "stock": 8
}
~~~

Elasticsearch writes only if the current version of P-100 still has `_seq_no` equal to 17 and `_primary_term` equal to 3.

If the operation succeeds, the response returns the metadata of the new version, for example:

~~~json
{
  "_index": "products",
  "_id": "P-100",
  "_version": 9,
  "result": "updated",
  "_seq_no": 21,
  "_primary_term": 3
}
~~~

The new sequence number is the token that must be used for the next write. Do not keep reusing the old token after a successful write.

### 5.1. Both conditions must go together

Sequence-number-based OCC requires both `if_seq_no` and `if_primary_term`. They form a paired condition.

Do not send only one of the two parameters to simulate OCC. Use the exact token pair returned by Elasticsearch from the prior read.

### 5.2. Writing new documents and existence conditions

If the goal is to create a new document without overwriting an existing document with the same ID, use create semantics or `op_type=create`. That is conflict control for an already-existing ID, which differs from OCC based on the token of a previously read document.

Example:

~~~http
PUT /products/_create/P-200
Content-Type: application/json

{
  "name": "Mouse",
  "stock": 25
}
~~~

Create-only ensures an existing document with the same ID is not replaced. OCC using sequence number/primary term ensures an update applies only to the version that was read.

## 6. Update API with optimistic concurrency

The Update API also supports the condition pair:

~~~http
POST /products/_update/P-100?if_seq_no=17&if_primary_term=3
Content-Type: application/json

{
  "doc": {
    "stock": 8
  }
}
~~~

If the document is still at the version that was read, Elasticsearch applies the partial document. If the version has changed, the operation returns a conflict.

You can use a scripted update with the same conditions:

~~~http
POST /products/_update/P-100?if_seq_no=17&if_primary_term=3
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock = params.stock",
    "params": {
      "stock": 8
    }
  }
}
~~~

The OCC conditions still apply to the document version. The script does not run as a way to bypass the token; it executes only if the write condition is satisfied.

### 6.1. Partial update and full replacement

The two write styles behave differently:

- The Index API replaces the document's content with the sent source.
- The Update API applies a partial document or script to the current source.

Both can use `if_seq_no` and `if_primary_term`. Choose the API based on how you want to modify the data, then attach the corresponding token pair.

### 6.2. Update without OCC

If an application reads a document, computes a new value on the client, and calls update without conditions, another request can still write between those two steps. The second update can then overwrite the earlier result.

Using a partial update does not automatically prevent lost updates if the updated fields were derived from a stale snapshot. OCC is still required whenever the business decision depends on the version that was read.

## 7. The Delete API also supports OCC

If a document should only be deleted if it has not changed since being read, pass the token in the Delete API:

~~~http
DELETE /products/_doc/P-100?if_seq_no=17&if_primary_term=3
~~~

If the token still matches, the document is deleted. If the document was updated or the primary term changed, Elasticsearch rejects the operation with a version conflict.

This is useful when a UI displays a record and the user confirms deletion after some time. If the record changed while the user was viewing it, the application can prompt them to reload before confirming.

## 8. What happens when the token is stale?

Suppose two clients read the version with token (17, 3):

~~~text
Client A                              Client B
---------------------------------------------------------------
GET document -> (17, 3)
                                      GET document -> (17, 3)
PUT if_seq_no=17
    if_primary_term=3
-> succeeds, document becomes
   new version (21, 3)
                                      PUT if_seq_no=17
                                          if_primary_term=3
                                      -> 409 version conflict
~~~

Client B's request is not applied because the current document is no longer at version (17, 3).

The error response typically has HTTP status 409 Conflict with error type `version_conflict_engine_exception`. Abbreviated example:

~~~json
{
  "error": {
    "type": "version_conflict_engine_exception",
    "reason": "[P-100]: version conflict, required seqNo [17], primary term [3]. current document has a different version"
  },
  "status": 409
}
~~~

The actual `reason` message may vary by API, version, and document state. Applications should rely on the HTTP status and error type rather than parsing a fixed message string.

A conflict signals that a decision based on stale data can no longer be guaranteed. It is not necessarily a system error or an error that should be retried unconditionally.

## 9. Conflict-handling workflow in the application

Upon receiving a 409, the application can choose one of the following strategies depending on business logic:

### 9.1. Reload and prompt the user for confirmation

Suitable when two users are editing the same form or configuration.

1. Notify that the data was changed by someone else.
2. Reload the document and its new token.
3. Display the current changes.
4. Ask the user to reapply or merge their changes.

This is the clearest approach when the system cannot automatically decide which value takes precedence.

### 9.2. Reload and recompute the change

Suitable when the operation can be re-evaluated against new data.

1. Read the latest document.
2. Re-check business rules.
3. Recompute the new value from the fresh snapshot.
4. Send the write with the new token pair.
5. If conflicts persist, retry within bounded limits.

For example: setting a limit as a percentage of the current value. When the base value changes, the application must recompute against the new value instead of resending a result calculated from the stale snapshot.

### 9.3. Merge independent fields

If two clients update independent fields, the service can reload the document and reapply changes to its own fields. However, you must clearly identify which fields can be merged and which have coupled invariants.

Do not automatically merge two sources if fields have business relationships. For example, quantity, total amount, and order status may need to be updated as a single logical unit.

### 9.4. Limit retry attempts

Do not retry indefinitely. When many clients continuously write to the same document, unbounded retries can trigger high-load loops.

A practical policy may:

- Retry at most a small number of times.
- Include short backoff and jitter if the workload has many writers.
- Reload the token after each conflict.
- Recompute logic on the new data.
- Record metrics for conflict and retry counts.
- Return a meaningful error if the threshold is exceeded.

Retries only help if the application can reload and make a fresh decision. Resending the exact same request with the old token will continue to conflict.

## 10. Distinguishing explicit OCC from retry_on_conflict

The Update API has a `retry_on_conflict` option. It lets Elasticsearch internally retry an update when a version conflict occurs during the update.

The two mechanisms serve different purposes:

| Mechanism | Who decides to retry? | Data used for retry | Best suited when |
| --- | --- | --- | --- |
| if_seq_no + if_primary_term | Client/service | Client controls snapshot and fresh decision. | Must reject operations based on a stale version. |
| retry_on_conflict | Elasticsearch | Update operation is re-read and re-executed per Update API mechanics. | Update script/partial operation can safely re-run on the new source. |

Example incrementing stock with a server-side script:

~~~http
POST /products/_update/P-100?retry_on_conflict=3
Content-Type: application/json

{
  "script": {
    "lang": "painless",
    "source": "ctx._source.stock += params.amount",
    "params": {
      "amount": 1
    }
  }
}
~~~

The Update API can reload the source and re-run the script on conflict up to the retry limit. Because the script adds to the current value, re-running can align with the intent of incrementing by one unit.

Conversely, a script assigning a value precomputed from a stale snapshot may be unsafe to re-run if business logic depends on the data the client had read.

Do not treat `retry_on_conflict` as a replacement for the OCC token pair. When the caller needs to guarantee "write only if the document is still the exact version I read," send `if_seq_no` and `if_primary_term` and handle conflicts at the application layer. Do not assume all retry forms can be combined with OCC conditions without checking API and Elasticsearch version behavior.

## 11. Sequence numbers in the Bulk API

The Bulk API allows sending multiple operations in a single request. Each action can carry its own OCC conditions.

Example updating two documents:

~~~http
POST /_bulk
Content-Type: application/x-ndjson

{"update":{"_index":"products","_id":"P-100","if_seq_no":17,"if_primary_term":3}}
{"doc":{"stock":8}}
{"delete":{"_index":"products","_id":"P-200","if_seq_no":9,"if_primary_term":2}}
~~~

Each action is checked independently. One item can succeed while another returns a conflict. The Bulk response contains an `errors` flag and an `items` list; the application must inspect individual item results rather than checking only the overall HTTP status.

Handling example:

- If updating P-100 succeeds, save the new token from the item response if further writes are needed.
- If deleting P-200 returns 409, reload the document and decide whether deletion is still warranted.
- Do not blindly retry the entire bulk request because items that already succeeded could be executed again.

Bulk reduces round trips, but does not turn the whole request into an atomic transaction.

## 12. Distinguishing sequence number/primary term from _version

Elasticsearch also returns `_version`. This is an internal versioning mechanism separate from the sequence number and primary term pair.

| Mechanism | Conditional data | Purpose |
| --- | --- | --- |
| Internal versioning | _version | Tracks document version and controls version-based writes in supported APIs. |
| External versioning | version with version_type | Lets external systems supply versions following external versioning rules. |
| Modern OCC | if_seq_no and if_primary_term | Writes only when the document still matches the version read from Elasticsearch. |

Do not take `_version` and pass it into `if_seq_no`; the two values do not mean the same thing and are not interchangeable.

Spring Data Elasticsearch has the `@Version` annotation for entity versioning. Do not assume an `@Version` field is the `_seq_no` and `_primary_term` pair. If a use case needs OCC based on Elasticsearch tokens, obtain sequence number and primary term from search/get metadata and pass them to the write request.

## 13. Spring Data Elasticsearch integration

Spring Data Elasticsearch can work with search hit metadata and provide conditional write APIs depending on the version. You must retain the token from the read result and forward it to the index/update request.

### 13.1. Reading metadata from SearchHit

When using `ElasticsearchOperations.search`, each `SearchHit<T>` provides the ID, index, content, and hit metadata. Modern Spring Data Elasticsearch versions expose getters for sequence number and primary term:

~~~java
SearchHits<ProductDocument> searchHits =
        operations.search(query, ProductDocument.class);

for (SearchHit<ProductDocument> hit : searchHits) {
    ProductDocument product = hit.getContent();

    String id = hit.getId();
    String index = hit.getIndex();
    long seqNo = hit.getSeqNo();
    long primaryTerm = hit.getPrimaryTerm();

    // Keep product along with seqNo and primaryTerm
    // for the next conditional write.
}
~~~

If using the Get API or another API, inspect the corresponding response metadata. Do not save only the entity while discarding the token; the entity source normally does not contain `_seq_no` or `_primary_term`.

### 13.2. Writing with IndexQuery

Spring Data Elasticsearch provides `IndexQuery` and its builder to pass sequence number and primary term in supported versions:

~~~java
import org.springframework.data.elasticsearch.core.IndexQuery;
import org.springframework.data.elasticsearch.core.IndexQueryBuilder;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

IndexQuery indexQuery = new IndexQueryBuilder()
        .withId(product.getId())
        .withObject(product)
        .withSeqNo(seqNo)
        .withPrimaryTerm(primaryTerm)
        .build();

operations.index(
        indexQuery,
        IndexCoordinates.of("products")
);
~~~

The index operation carries the token conditions down to Elasticsearch. If the document has changed, the operation can raise a version conflict instead of overwriting the newer version.

Builder method names and nullable types for sequence number/primary term depend on the Spring Data Elasticsearch version. Check your project's dependency API and verify the actual outgoing request contains both parameters.

### 13.3. UpdateQuery

For partial updates, some Spring Data Elasticsearch versions provide conditional sequence number and primary term properties on the `UpdateQuery` builder. Common API pattern:

~~~java
import java.util.Map;
import org.springframework.data.elasticsearch.core.document.Document;
import org.springframework.data.elasticsearch.core.query.UpdateQuery;

UpdateQuery updateQuery = UpdateQuery.builder(id)
        .withDocument(Document.from(Map.of("stock", 8)))
        .withIfSeqNo(seqNo)
        .withIfPrimaryTerm(primaryTerm)
        .build();

operations.update(
        updateQuery,
        IndexCoordinates.of("products")
);
~~~

If your version lacks these builder methods, you can use the Elasticsearch Java API Client directly. Do not drop OCC conditions just to make code compile; use the appropriate API or plan an upgrade.

### 13.4. Direct Elasticsearch Java API Client

With the Elasticsearch Java API Client, `UpdateRequest` supports sequence number and primary term conditions:

~~~java
import co.elastic.clients.elasticsearch.ElasticsearchClient;
import co.elastic.clients.elasticsearch.core.UpdateRequest;
import java.util.Map;

UpdateRequest<ProductDocument, Map<String, Object>> request =
        UpdateRequest.of(u -> u
                .index(index)
                .id(id)
                .ifSeqNo(seqNo)
                .ifPrimaryTerm(primaryTerm)
                .doc(Map.of("stock", 8)));

var response = client.update(request, ProductDocument.class);
~~~

`IndexRequest` and `DeleteRequest` also have corresponding conditions in the Java API Client. Generic types, overloads, and obtaining the client from Spring Data depend on the version; use the client managed by your dependencies.

### 13.5. Catching version conflicts

Spring Data can wrap Elasticsearch errors into client/operations-layer exceptions. Exact exception names depend on the version and API invoked.

At the service layer, identify conflicts from the corresponding status/error type, then:

- Reload the document and fresh metadata.
- Re-check business conditions.
- Recompute the change if possible.
- Send a new request with the freshly read token.
- Stop and return a business error if the retry limit is exceeded.

Do not catch every exception and retry. Mapping, validation, authentication, or script compilation errors are not optimistic conflicts and must be handled separately.

## 14. Routing and token validity scope

Sequence number and primary term belong to the shard storing the document. If a document was indexed with custom routing, the write request must use the same routing to reach the same shard.

For example, a document stored with routing `tenant-42`:

~~~http
GET /products/_doc/P-100?routing=tenant-42&seq_no_primary_term=true
~~~

The conditional write also needs the same routing:

~~~http
PUT /products/_doc/P-100?routing=tenant-42&if_seq_no=17&if_primary_term=3
Content-Type: application/json

{
  "stock": 8
}
~~~

With incorrect routing, the request may fail to find the document or operate on a different shard. Do not use a token pair detached from the index, document ID, and routing context it belongs to.

## 15. Aliases, data streams, and index rollover

A search through an alias can return hits from a concrete index. The sequence number/primary term pair belongs to the document in that specific index/shard.

If the alias switches to a new index between the read and write, a write through the alias may target a different index. A token from the old index cannot serve as a token for a document in the new index.

When OCC is needed through an alias:

- Retain the actual `_index` from the hit.
- Define the policy for writing to the concrete index versus the alias.
- Ensure the write request targets the exact index and routing from the read.
- If the system rolls over indices, handle cases where the document moved or was created in another index as a distinct business scenario.

Do not assume an OCC token is valid across an entire alias or data stream.

## 16. Concurrency testing scenarios

You can test OCC using two independent clients:

1. Create document P-100.
2. Client A reads and receives token A.
3. Client B reads the same document and receives token B.
4. Client A writes successfully with token A.
5. Client B writes with token B.
6. Verify B receives HTTP 409 and A's content is not overwritten.

Expected example:

| Step | Client | Outcome |
| --- | --- | --- |
| Initial read | A | Receives (17, 3). |
| Initial read | B | Receives (17, 3). |
| First write | A | Succeeds; new token (21, 3). |
| First write | B | 409 because token (17, 3) is stale. |
| Reload | B | Receives fresh data and new token. |
| Recompute, rewrite | B | Succeeds if new conditions still hold. |

Also test:

- Document deleted between read and write.
- Primary shard failover.
- Document with custom routing.
- Client sending only one of the two tokens.
- Bulk request where some items conflict.
- Exceeding retry limits.
- Alias rollover between read and write.
- Two requests concurrently modifying coupled business fields.

## 17. Common errors

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| Write returns 409 | Document changed since read. | Reload, check logic, and retry with a bound. |
| Always conflicts even when nobody seems to edit | Token came from another index/shard/routing or is stale. | Check `_index`, ID, routing, and token pair. |
| Passing only `if_seq_no` or `if_primary_term` | Half of the OCC condition is missing. | Send both values from the same read. |
| Using `_version` as `if_seq_no` | Confused two versioning mechanisms. | Fetch proper `_seq_no` and `_primary_term`. |
| Retrying with old token still fails | Token was not refreshed after conflict. | Reload the document and get the new token pair. |
| Update script increments value twice | Business retry or duplicate request lacks idempotency. | Design idempotent operations or use operation IDs/business conditions. |
| Bulk request returns HTTP success but items fail | Bulk processes each item independently. | Check `errors` and per-item results. |
| Spring Data does not pass OCC to request | Unsupported API/version or unconfigured builder. | Verify version-appropriate API and actual outgoing request. |
| Token unusable after rollover | Token belongs to old concrete index. | Write to the right index or handle index rollover per business rules. |
| Request cannot find document with routing | Read/write use different routing. | Keep routing value alongside document metadata. |

## 18. Design principles

When introducing optimistic concurrency into a Spring Data Elasticsearch service:

1. Obtain sequence number and primary term from the same read.
2. Keep index, ID, and routing together with the token.
3. Pass both `if_seq_no` and `if_primary_term` on writes.
4. Handle 409 as an expected data conflict.
5. Reload and re-evaluate business logic before retrying.
6. Bound retries and monitor conflict rates.
7. Do not confuse OCC with `_version`, `@Version`, or `retry_on_conflict`.
8. Do not apply a token across different documents, indices, or shards.
9. For updates that can execute atomically server-side, consider the Update API and an appropriate script.
10. Inspect each item in the Bulk API.
11. Test failover, routing, and alias rollover.
12. Clearly define when user confirmation of changes is required.

OCC is a mechanism for detecting writes based on stale snapshots. It does not automatically resolve business conflicts, merge data, or turn multiple requests into a transaction. Applications still need explicit rules to decide when to retry, merge, or reject operations.

## 19. References

- [Elasticsearch — Optimistic concurrency control](https://www.elastic.co/guide/en/elasticsearch/reference/current/optimistic-concurrency-control.html)
- [Elasticsearch — Get API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-get.html)
- [Elasticsearch — Index API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-index_.html)
- [Elasticsearch — Update API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-update.html)
- [Elasticsearch — Delete API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-delete.html)
- [Elasticsearch — Bulk API](https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html)
- [Spring Data Elasticsearch — Search result types and operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — Version annotation](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/annotations/Version.html)

Sequence number and primary term form a document version token on a shard. Clients fetch both when reading and send them back via `if_seq_no` and `if_primary_term` when indexing, updating, or deleting. If the document has changed, Elasticsearch returns 409 so the application can reload and decide how to proceed. Spring Data can carry metadata from `SearchHit` to conditional write APIs; use the API appropriate for your version and keep the document's index, ID, and routing intact.
