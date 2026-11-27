# Why Search Might Not Yet See a Newly Written Document

A common situation when working with Elasticsearch is that an application successfully writes a document, receives an ID or a success response, and immediately runs a search only to find the document is not there yet. This does not necessarily mean the write operation was lost or that Elasticsearch encountered an error. Elasticsearch is a near-real-time (NRT) search engine: a written document may not appear in search results until the shard is refreshed.

The important point is to distinguish three things:

- **Write acknowledgement:** Elasticsearch processed the write operation according to the request's conditions and returned a response.
- **Durability:** data is protected via the translog and the configured storage/replication mechanism.
- **Search visibility:** whether the document has appeared in the Lucene searcher that search requests use.

A write operation can already be acknowledged and readable via GET by ID, yet not be found by match, term, or other search queries. The usual cause is that a refresh has not happened yet.

In Spring Data Elasticsearch, you need to choose a refresh policy that fits your application's requirements. You can accept waiting for periodic refreshes, require the request to wait until the next refresh, or force a refresh immediately when truly necessary. Forcing a refresh after every write can reduce throughput and increase segment/merge overhead.

## 1. The phenomenon of writing and immediately searching without seeing the document

Suppose a service saves a product:

    Product product = new Product();
    product.setId("p-100");
    product.setName("Mechanical Keyboard");

    productRepository.save(product);

Immediately afterward, the service searches by name:

    List<Product> results =
        productRepository.findByName("Mechanical Keyboard");

The application might not yet see p-100 in the search results, even though save returned normally.

This happens because indexing and search visibility are two separate steps. Elasticsearch may have received the write operation, updated its internal state, and written the information to the translog, while the current searcher has not yet been refreshed to see the new segment.

With a typical configuration, refreshes run periodically. Therefore, a document usually becomes searchable after a short interval, but there is no guarantee that a search request sent immediately after a write will always see it unless the application explicitly requests read-after-write visibility.

## 2. Elasticsearch is a near-real-time search engine

Elasticsearch is built on Apache Lucene. Documents are indexed into internal structures and then organized into segments. Search requests read data through a searcher bound to segments that have been opened for searching.

Refresh is the process of making recent indexing changes visible to search by opening a new searcher over the newly created segments.

General flow:

    Application sends index request
             |
             v
    Elasticsearch receives write operation
             |
             v
    Updates indexing buffer and translog
             |
             v
    Write operation is acknowledged
             |
             |  Search may still use old searcher
             v
    Refresh creates/opens new searcher
             |
             v
    Document can be found via search

Because a refresh does not occur synchronously after every write operation, Elasticsearch is called near-real-time rather than real-time search.

Near-real-time means data generally becomes searchable after a short delay; it does not mean every search sees every write immediately.

## 3. What is a refresh?

A refresh makes recent indexing changes available for search. At a high level, Elasticsearch creates or opens the necessary segments and updates the searcher so queries can read them.

Refresh is not the same as rewriting the entire index to disk or creating a durable Lucene commit. It primarily changes data visibility for search.

A few points to remember:

- Refresh affects search visibility.
- Refresh is not a per-document write operation.
- Refresh is not synonymous with flush.
- Refresh incurs CPU, I/O, and segment management costs.
- A search request only sees data that has been refreshed on the shard copy it reads from.

When an index has search activity, Elasticsearch typically refreshes automatically on a schedule. A common default in self-managed Elasticsearch is around one second, though the configuration can vary by index, version, and deployment environment. Some managed or serverless environments may use different defaults.

Do not write application logic based on a hard assumption that a refresh always happens after exactly one second. If a business requirement needs immediate visibility, use an intentional refresh policy or refresh API.

## 4. Write acknowledgement does not mean search visibility

When Elasticsearch returns a successful response for an index request, that indicates the write operation was processed according to the request semantics and relevant cluster conditions.

A successful response does not automatically mean:

- A refresh has occurred.
- A new searcher has been opened on every shard.
- Every replica has refreshed so search sees the document immediately.
- A query on any arbitrary field is guaranteed to return the document.

For example:

    PUT products/_doc/p-100
    {
      "name": "Mechanical Keyboard",
      "price": 120
    }

The response may report that indexing succeeded. However, immediately afterward:

    GET products/_search
    {
      "query": {
        "term": {
          "name.keyword": "Mechanical Keyboard"
        }
      }
    }

may not return p-100 yet if the shard has not refreshed.

Besides refresh, the query also needs the right field, analyzer, filter, index/alias, and routing. If a document still does not appear after a refresh, check these causes instead of continuing to force refreshes.

## 5. How do translog, refresh, and flush differ?

These three concepts are often confused:

| Concept | Primary role | Direct effect |
|---|---|---|
| Translog | Records operations to support durability and recovery | Protects changes according to the translog policy |
| Refresh | Makes recent changes searchable | Search can see the document |
| Flush | Creates a Lucene commit and starts a new translog generation | Supports translog management and recovery |

### Translog

The translog records write operations so Elasticsearch can recover changes not yet included in a Lucene commit after a failure. The translog durability policy determines when the translog is synced to storage.

The default typically uses request durability, meaning the translog is synced according to request semantics before the operation is acknowledged. Configuration can change, so check index settings when durability requirements are especially critical.

### Refresh

Refresh makes indexed documents appear in a new searcher. It is not a flush command and does not mean all data has been committed into a durable Lucene commit.

### Flush

Flush creates a Lucene commit and switches to a new translog generation. Elasticsearch manages flushes automatically based on internal conditions; typical search applications do not need to call flush after every write.

If the goal is for search to see the document, think of refresh. If the goal is durability/recovery, understand translog and flush. Do not use flush as a substitute for refresh.

## 6. GET by ID can see a document before search does

Elasticsearch supports real-time GET by document ID. A real-time GET can read the latest state from internal structures, including the translog, without waiting for a search refresh.

For example:

    PUT products/_doc/p-100
    {
      "name": "Mechanical Keyboard"
    }

    GET products/_doc/p-100

GET by ID can return the document immediately after the write, whereas:

    GET products/_search
    {
      "query": {
        "term": {
          "name.keyword": "Mechanical Keyboard"
        }
      }
    }

still does not see the document until a refresh occurs.

The difference:

| API | How it reads | Depends on refresh to see new writes? |
|---|---|---|
| GET document by ID | Real-time document lookup | Normally no |
| Search API | Reads via Lucene searcher | Yes |
| Aggregation | Computed over the document set selected by search | Yes |

GET by ID does not replace search. If the application needs to query by name, status, category, or other query criteria, it must ensure search visibility.

## 7. Default refresh interval and configuration

The `refresh_interval` index setting specifies the automatic refresh cycle:

    PUT products/_settings
    {
      "index": {
        "refresh_interval": "1s"
      }
    }

A value of 1s is a common configuration in self-managed Elasticsearch, but it can be changed. If increased to 5s or 30s, documents can take longer before appearing in search.

If set to:

    PUT products/_settings
    {
      "index": {
        "refresh_interval": "-1"
      }
    }

automatic refresh is disabled. In that case, documents will not automatically become searchable on a schedule; the application or an operational job must explicitly refresh when appropriate.

Disabling refresh can be helpful during large bulk imports to reduce overhead, but a refresh step after the import is needed if search should see the data.

### When to adjust refresh_interval?

- Continuously written index that tolerates slower search visibility: you can increase the interval.
- Large data import: you can temporarily disable automatic refresh in a controlled workflow, then refresh after the import.
- Data needs to appear quickly in the UI: keep an appropriate interval or use WAIT_UNTIL for writes that need read-after-write.
- Index serving both heavy ingest and interactive search: balance visibility latency with throughput.

Do not reduce `refresh_interval` to a very small value just to work around a race condition in the application. Refreshing too frequently can increase segment count and merge overhead.

## 8. Refresh policies in the Bulk API and Spring Data

Elasticsearch provides refresh handling options commonly represented by three policies:

| Policy | REST API | Meaning |
|---|---|---|
| NONE | false or omit refresh | Do not request a separate refresh for the request |
| IMMEDIATE | true | Immediately refresh affected shards after the operation |
| WAIT_UNTIL | wait_for | Wait for the next refresh to make changes visible |

In Spring Data Elasticsearch, the enum is usually called RefreshPolicy with values NONE, IMMEDIATE, and WAIT_UNTIL. The exact package and API for passing the policy depend on the Spring Data version.

### NONE

NONE does not ask Elasticsearch to refresh immediately after the request. The document will become searchable when the next automatic refresh occurs or when another refresh affects the index.

Suitable for:

- Large bulk imports.
- Continuous ingest where throughput is the priority.
- Writes that do not require immediate search visibility.
- Systems that accept eventual search visibility.

### IMMEDIATE

IMMEDIATE requests an immediate refresh after the operation. When the request completes, changes can be found via search on the affected shards.

Suitable for:

- A rare administrative operation that needs to appear immediately.
- Small workflows with strict immediate visibility requirements.
- Tests or use cases that need immediate search results and accept the cost.

Do not use IMMEDIATE for every operation in high-throughput systems.

### WAIT_UNTIL

WAIT_UNTIL asks the request to wait until a refresh makes the change visible to search. It does not actively force an immediate refresh; instead, the request is held until the next appropriate refresh.

Suitable for:

- A user creates a product and immediately navigates to a page that searches for that product.
- APIs that must guarantee read-after-write via search.
- Business operations that require searchable results before returning a response.

WAIT_UNTIL generally balances visibility and cost better than forcing IMMEDIATE on every write, though the request may have to wait until the next refresh cycle.

## 9. Choosing a refresh policy based on business requirements

Not every write needs the same level of visibility.

| Scenario | Typically suitable policy | Reason |
|---|---|---|
| Importing millions of documents | NONE | Optimize throughput, refresh after import |
| Scheduled background data updates | NONE | Tolerates delay until automatic refresh |
| User creates a product and immediately searches for it | WAIT_UNTIL | Wait for data to become searchable before returning |
| Rare admin operation needing immediate visibility | IMMEDIATE or WAIT_UNTIL | Choose based on requirement and cost |
| Writing many batches in one job | NONE, then refresh once | Avoid refreshing after every batch |
| Integration test needing search right after save | Explicit refresh or WAIT_UNTIL | Make tests deterministic, independent of timers |

Determine precisely what the API needs to guarantee. If the user only needs to view the details of the newly created document and already has the ID, a real-time GET may be sufficient; there is no need to force a refresh on the entire index.

## 10. Using RefreshPolicy in the @Document annotation

Spring Data Elasticsearch may allow declaring a refresh policy in entity metadata in supported versions:

    @Document(
        indexName = "products",
        refreshPolicy = RefreshPolicy.WAIT_UNTIL
    )
    public class Product {

        @Id
        private String id;

        private String name;
    }

When the entity is written via Spring Data operations that honor this metadata, the corresponding refresh policy can be applied to the write request.

Check the annotation package and attributes in your project's version. Not all Spring Data Elasticsearch versions have the same metadata or apply the policy uniformly across all write APIs.

Do not set IMMEDIATE at the entity level just to fix one endpoint that needs immediate visibility if that entity is written very frequently by many other flows. A broad policy can impact the entire write path.

If only a few use cases need read-after-write, consider configuring it on the specific request or service so the scope of impact is clear.

## 11. Using BulkOptions to configure the refresh policy

For bulk operations, you can pass a refresh policy via BulkOptions in supported versions:

    BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.WAIT_UNTIL)
        .build();

    operations.bulkIndex(
        indexQueries,
        options,
        IndexCoordinates.of("products")
    );

For large imports:

    BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.NONE)
        .build();

    for (List<IndexQuery> batch : batches) {
        operations.bulkIndex(
            batch,
            options,
            IndexCoordinates.of("products")
        );
    }

    operations.indexOps(IndexCoordinates.of("products"))
        .refresh();

The snippet illustrates common API usage. Packages, builder methods, and IndexCoordinates types depend on the Spring Data Elasticsearch version. Verify against your actual dependencies before applying.

If every batch uses WAIT_UNTIL, each request may have to wait for a refresh. With hundreds of batches, total import time can increase significantly. If reading between batches is not required, NONE followed by a single refresh is usually more appropriate.

## 12. Explicit refresh with IndexOperations

When the application needs to actively make data searchable, it can call refresh:

    IndexOperations indexOperations =
        operations.indexOps(IndexCoordinates.of("products"));

    indexOperations.refresh();

Or using the corresponding entity metadata:

    operations.indexOps(Product.class).refresh();

The exact API depends on the Spring Data version. An explicit refresh affects the specified index and can make prior writes searchable.

Do not call refresh after every document:

    for (Product product : products) {
        operations.save(product);
        operations.indexOps(Product.class).refresh();
    }

This approach can create a large number of refreshes and tiny segments. If you need to process many documents, batch them, write them, and then refresh once when actually needed.

## 13. Direct Elasticsearch Refresh API

REST API:

    POST products/_refresh

Multiple indices can be refreshed:

    POST products,orders/_refresh

The Refresh API is commonly used in:

- Import workflows after completion.
- Integration tests.
- Controlled operational tasks.

Refresh does not take a document ID. It establishes search visibility for writes already applied on the relevant index/shards.

If the application uses an alias, identify which indices the alias points to and refresh the proper target. Refreshing an alias can apply to the backing indices according to API semantics, but verify the alias and write index in your deployment workflow.

## 14. How does WAIT_UNTIL work?

WAIT_UNTIL uses a refresh listener waiting mechanism. Instead of requesting an immediate refresh, Elasticsearch holds the request until the next refresh makes the request's changes visible.

Flow:

    Application sends write with refresh=wait_for
                 |
                 v
    Elasticsearch processes write operation
                 |
                 v
    Registers to wait for refresh
                 |
                 v
    Automatic or explicit refresh occurs
                 |
                 v
    Request completes
                 |
                 v
    Application receives response

WAIT_UNTIL can reduce forced refreshes compared to IMMEDIATE when multiple requests wait on the same refresh cycle.

However, it is not free:

- The request holds a connection or waiting resources.
- If the refresh interval is long, the write response can also be slow.
- If automatic refresh is disabled, the request can wait until an explicit refresh or timeout.
- There is a limit on the number of refresh listeners; too many waiting requests can cause errors.

Do not issue thousands of concurrent WAIT_UNTIL requests without bounding concurrency.

## 15. Disabling automatic refresh and the risk with WAIT_UNTIL

If an index has:

    index.refresh_interval = -1

then automatic refresh is disabled. In that case, WAIT_UNTIL cannot rely on an automatic refresh cycle to complete. Requests may keep waiting until an explicit refresh occurs or a timeout takes effect under the relevant mechanism.

In a bulk import with refresh disabled:

1. Send bulk requests with NONE.
2. Complete all batches.
3. Call explicit refresh once.
4. Only then run searches that need to see the new data.

Do not combine long-term disabled refresh with WAIT_UNTIL without a clear refresh plan.

## 16. Why does IMMEDIATE degrade performance?

Refresh makes a new searcher able to read new segments. When refreshes happen continuously:

- Many small segments are created and opened.
- Search has to manage more segments.
- Segment merging can increase.
- CPU and I/O spent on refresh/merge rise.
- Indexing throughput can drop.
- Search latency can fluctuate due to resource pressure.

If every document forces a refresh, the system loses the benefit of batching multiple operations before a refresh.

For example:

    save A -> refresh
    save B -> refresh
    save C -> refresh
    save D -> refresh

Compared to:

    save A
    save B
    save C
    save D
    -> one periodic refresh or one intentional refresh

The second approach is generally far more efficient for write-heavy workloads.

## 17. Read-after-write via GET and via search

Choose the read API based on what the user needs.

### Reading by ID

If a write returns an ID and the UI only needs to open the details page of the newly created document, GET by ID can be used. Real-time GET typically sees new writes without waiting for a refresh.

### Searching by attributes

If the UI needs to find the document by name, category, status, or full-text query, it must rely on search visibility. Use WAIT_UNTIL or an explicit refresh if the endpoint must guarantee read-after-write.

### Reading from another system

If another service performs a search right after the writing service returns a response, the writing service needs a clear visibility contract. Options include:

- Returning the response after WAIT_UNTIL.
- Emitting an event only after the data is searchable as required.
- Having the reading service fetch by ID if the use case fits.
- Accepting eventual consistency and designing retry/polling in the consumer.

Do not let another service guess by sleeping for one second and searching again.

## 18. Reasons search might not find a document besides refresh

If you have waited for a refresh and the document still does not appear, check other causes:

| Cause | Symptom | How to check |
|---|---|---|
| Searching wrong index or alias | GET by ID on a different index succeeds | Check index/alias and write index |
| Query does not match | GET finds the document but term/match returns nothing | Check mapping, analyzer, and query DSL |
| Filter excludes the document | Basic search finds it but business query does not | Check status, tenant, permission, and range filters |
| Incorrect routing | GET/search with different routing returns different results | Check routing at index time and search time |
| Write not yet finished | Search runs before async write completes | Await completion of Future/Mono/job |
| Bulk item failed | Bulk response has item errors | Inspect errors and each item |
| Document overwritten or deleted | ID has unexpected version/source | Check sequence, version, and other write paths |
| Mapping parse error | Item returns mapper_parsing_exception | Check data types and source |

Refresh only resolves search visibility for writes that succeeded. It does not fix wrong queries, wrong mappings, or failed write operations.

## 19. Bulk response succeeds but items can fail

The Bulk API can return a successful HTTP response while some items inside fail. Before investigating refresh, inspect item-level results.

Example response:

    {
      "errors": true,
      "items": [
        {
          "index": {
            "_id": "p-1",
            "status": 201
          }
        },
        {
          "index": {
            "_id": "p-2",
            "status": 400,
            "error": {
              "type": "mapper_parsing_exception"
            }
          }
        }
      ]
    }

p-1 was written; p-2 was not written successfully. Refresh cannot make p-2 appear because that operation failed.

In Spring Data, how item errors are represented depends on the API and version. Read the corresponding response/exception, log the ID and reason, and classify for retry.

## 20. Search on replicas and visibility

Elasticsearch distributes shards into primaries and replicas. Search can be executed across shard copies based on routing and adaptive replica selection.

Refresh is a shard-copy operation. In an environment with replicas, understand that write visibility involves refreshing the shard copies that search may read. Elasticsearch coordinates refresh and replication according to request semantics; do not assume manually refreshing a single node always resolves cluster-wide visibility.

When per-request visibility is needed, using the write request's refresh policy is clearer than manually targeting a node and calling the refresh API directly without proper scope.

If search still returns inconsistent results after WAIT_UNTIL or explicit refresh, check cluster health, shard allocation, routing, and index aliases. Do not attribute every difference between replicas to a refresh interval bug.

## 21. Asynchronous writes and execution order in the application

Another common cause is a service launching an asynchronous write without waiting for it to finish before searching:

    executor.submit(() -> productRepository.save(product));

    return productRepository.findByName(product.getName());

The search may run before the save operation even starts or finishes. This is an application race condition, different from refresh.

With CompletableFuture, wait or compose the steps:

    CompletableFuture<Product> saved =
        CompletableFuture.supplyAsync(
            () -> productRepository.save(product),
            executor
        );

    return saved.thenApply(result ->
        productRepository.findByName(result.getName())
    );

This example still needs an appropriate refresh policy if the read step is a search. Waiting for the write to complete only guarantees the write request returned a response; it does not by itself guarantee a refresh has occurred.

With reactive Spring Data:

    Mono<Product> saved = reactiveOperations.save(product);

    Mono<List<Product>> results = saved.flatMap(entity ->
        reactiveOperations.search(
            queryFor(entity.getName()),
            Product.class
        ).collectList()
    );

Composition ensures search starts after the save Mono completes. Still, for search to see the document immediately, WAIT_UNTIL or a refresh appropriate for the API/version in use is still required.

Do not call subscribe and then immediately search on the next line without completion coordination. subscribe triggers the reactive stream; it does not mean the operation completed synchronously.

## 22. Integration testing: do not use Thread.sleep

A fragile test looks like this:

    repository.save(product);
    Thread.sleep(1000);
    assertThat(repository.findByName(product.getName()))
        .isNotEmpty();

This test depends on refresh timing, machine load, and index configuration. It can be slow or flaky.

Instead, refresh explicitly:

    repository.save(product);

    operations.indexOps(Product.class).refresh();

    List<Product> results =
        repository.findByName(product.getName());

Or configure the write to use WAIT_UNTIL for the test:

    @Document(
        indexName = "products_test",
        refreshPolicy = RefreshPolicy.WAIT_UNTIL
    )
    public class Product {
        @Id
        private String id;
        private String name;
    }

Annotations and policies apply according to the Spring Data version. Explicit refresh in tests is often easier to see and control.

After tests, clean up data/indices according to your test workflow. If multiple tests run in parallel against the same index, refresh does not resolve data collisions between tests; use separate IDs or test indices.

## 23. Verifying with the REST API

You can reproduce the behavior:

    PUT products/_doc/p-100?refresh=false
    {
      "name": "Mechanical Keyboard"
    }

    GET products/_doc/p-100

GET by ID can return the document immediately.

Search:

    GET products/_search
    {
      "query": {
        "term": {
          "name.keyword": "Mechanical Keyboard"
        }
      }
    }

May not see the document before refresh.

Call refresh:

    POST products/_refresh

Search again:

    GET products/_search
    {
      "query": {
        "term": {
          "name.keyword": "Mechanical Keyboard"
        }
      }
    }

After refresh, the successfully written document and matching query can find it.

Another option is using `refresh=wait_for`:

    PUT products/_doc/p-101?refresh=wait_for
    {
      "name": "Wireless Mouse"
    }

When the write response returns, the request has waited for an appropriate refresh so the data is searchable.

## 24. Refresh and optimistic concurrency

Refresh policy does not replace concurrency control mechanisms.

If two requests update the same document concurrently, Elasticsearch can use sequence number and primary term or version to protect operations according to the appropriate semantics. Refresh only determines when changes become visible to search.

For example:

- Request A updates price.
- Request B updates stock.
- Unrefreshed search might not yet see one or both changes.
- GET by ID can see the latest state.
- If there is a write conflict, handle version/conflict separately.

Do not use IMMEDIATE to fix lost updates or version conflicts. Those issues require optimistic concurrency control, update scripts, retries, or proper write design.

## 25. Refresh and large bulk imports

When ingesting many documents, refreshing every batch can degrade throughput.

A common workflow:

1. Create the index with prepared mapping/settings.
2. If appropriate, temporarily increase `refresh_interval` or disable automatic refresh.
3. Send bulk requests with refresh NONE.
4. Monitor item failures and retry transient errors.
5. Complete all batches.
6. Restore `refresh_interval` if it was changed.
7. Call refresh once when search needs to see the data immediately.
8. Run verification queries after refresh.

For example:

    PUT products/_settings
    {
      "index": {
        "refresh_interval": "-1"
      }
    }

After import:

    POST products/_refresh

Then restore:

    PUT products/_settings
    {
      "index": {
        "refresh_interval": "1s"
      }
    }

This is an operational example; only disable refresh when the job has control over the index and a procedure to restore settings even if the job fails. Do not leave production indices with refresh unexpectedly disabled.

## 26. WAIT_UNTIL and refresh listener limits

WAIT_UNTIL uses listeners to wait for refreshes. Elasticsearch limits the number of refresh listeners per shard via a related setting, commonly called `index.max_refresh_listeners`.

If there are too many concurrent WAIT_UNTIL requests and a refresh has not occurred, new requests may be rejected once the listener limit is reached.

To avoid this:

- Do not use WAIT_UNTIL for every write on high-throughput workloads.
- Limit the number of concurrent waiting requests.
- Keep an appropriate refresh interval.
- Do not disable automatic refresh if requests depend on WAIT_UNTIL.
- Use bulk to group multiple writes that need the same visibility.
- Monitor write request errors and latency.

If the application needs to write many documents and then read the whole group, a single bulk request with WAIT_UNTIL can be more suitable than thousands of individual requests waiting for refresh, depending on workload.

## 27. Refresh and search consistency across multiple requests

Suppose a user performs:

1. Create product p-100.
2. Receive a success response.
3. Open the product list.

If the write uses NONE, the list might not show p-100 immediately. A subsequent search request can see the document once a refresh occurs.

This is eventual consistency in search visibility. The application should decide the user experience:

- Display details based on the ID immediately after the write.
- Display an updating message indicating the list will sync shortly.
- Wait with WAIT_UNTIL before returning the response if immediate searchability is required.
- Update the local UI from the write response and synchronize search afterward.

Do not default every create/update endpoint to forcing a refresh. That turns a UI visibility requirement into overhead across the entire write workload.

## 28. Common mistakes

### Assuming save returning means search sees it immediately

A save response indicates the write was processed, but search visibility requires a refresh. Use WAIT_UNTIL or explicit refresh if needed.

### Confusing real-time GET with search

GET by ID can read new writes from the translog, whereas search relies on refreshed searchers. The two APIs have different semantics.

### Calling flush to make data searchable

Flush and refresh serve different purposes. Search visibility requires refresh; do not use flush as a substitute.

### Calling refresh after every document

Refreshing too frequently increases segment count and merge costs. Batch writes or use WAIT_UNTIL/NONE appropriately.

### Using WAIT_UNTIL when automatic refresh is disabled

Requests can wait for a long time or until timeout if no refresh happens. Include an explicit refresh in the workflow.

### Using Thread.sleep in tests

Sleep makes tests timing-dependent. Call explicit refresh or use an appropriate policy to make tests deterministic.

### Only checking the HTTP status of bulk

Bulk can have item-level failures. Check per-item results before concluding a document was written.

### Not waiting for async writes to complete

Search can run before the write request is sent or finished. Compose Future/Mono or await completion properly.

### Searching the wrong index, alias, or routing

Refresh cannot fix the wrong target. Check index/alias, routing, mapping, analyzer, and filters.

### Lowering refresh_interval too far to fix a race condition

Frequent refreshes increase overhead. Choose a policy based on read-after-write requirements rather than lowering the index-wide interval without justification.

### Using IMMEDIATE system-wide

Some use cases need immediate visibility, but forcing a refresh on every write can reduce throughput. Narrow the scope.

## 29. Troubleshooting process when a write succeeds but search misses it

When encountering this issue, check in order:

1. Confirm the write request completed and the response reported success.
2. If using bulk, check errors and each item.
3. Try GET document by ID to verify the current source.
4. Verify the index, alias, write index, and routing.
5. Check mapping, analyzer, and query DSL.
6. Call explicit refresh in an investigation environment.
7. Run the search query again.
8. If still missing, check filters, tenant, permissions, and other update/delete operations.
9. Check `refresh_interval` and shard status.
10. If the write is asynchronous, verify the Future/Mono/job completed.

If an explicit refresh makes the document appear, the cause is likely search visibility. If it still does not appear, investigate the query or write path rather than continuing to call refresh.

## 30. Process for choosing a refresh strategy

You can select a policy using these steps:

1. Determine whether the user needs to read by ID or search by fields.
2. If reading by ID suffices, use real-time GET when appropriate.
3. If search can lag by the refresh interval, use NONE and accept eventual visibility.
4. If the write request must wait until searchable before returning a response, use WAIT_UNTIL.
5. If there is a small operation that needs immediate refresh, consider IMMEDIATE.
6. For large bulk imports, use NONE and then refresh once after completion.
7. Avoid WAIT_UNTIL when automatic refresh is disabled unless an explicit refresh is present.
8. Monitor waiting requests and refresh listener limits.
9. Use explicit refresh in integration tests instead of Thread.sleep.
10. Measure write latency, ingest throughput, and search visibility before changing `refresh_interval`.

## Conclusion

A newly written document might not appear in search results because Elasticsearch is a near-real-time search engine. Write acknowledgement, durability, and search visibility are three distinct concepts. The translog supports durability and recovery; refresh makes changes searchable; flush creates a Lucene commit and manages translog generations. Real-time GET by ID can see a document before search sees it.

In Spring Data Elasticsearch, NONE fits writes that do not need immediate visibility, IMMEDIATE forces a refresh and can reduce throughput, and WAIT_UNTIL waits for the next refresh to guarantee read-after-write via search. For bulk imports, it is usually best to write with NONE and refresh once at the end. For tests, refresh explicitly instead of using Thread.sleep. If the document still cannot be found after a refresh, check item-level bulk errors, index/alias, routing, mapping, analyzer, filters, and asynchronous execution order. Choosing a refresh policy based on business requirements helps balance search visibility with ingest performance.
