# Choosing a Refresh Policy Based on Read-After-Write Requirements

When an application writes a document to Elasticsearch and immediately searches for that document, search results sometimes do not show the newly written data yet. This is normal behavior because Elasticsearch is a *near real-time* search engine: a write operation may already be acknowledged while the document becomes visible in search results only after the next refresh.

A refresh policy governs whether a write request waits for data to become searchable or proactively triggers an immediate refresh. Choosing the right policy is a trade-off between read-after-write latency and indexing throughput.

Three common options are:

- **NONE / false:** neither requests a refresh nor waits for one. Data appears in search after an automatic refresh or a separately invoked refresh.
- **IMMEDIATE / true:** requests an immediate refresh on the relevant shards before the request completes. Search can observe changes right away, though this carries a cost.
- **WAIT_UNTIL / wait_for:** the request waits until a natural refresh makes the data searchable. It does not proactively force an immediate refresh and is often the right balance when read-after-write visibility is required without sacrificing indexing efficiency.

No single policy is optimal for every operation. Determine whether your application truly needs immediate search visibility, can tolerate a brief delay, or only needs to check the document by ID.

## 1. Why Does Search Miss a Document Right After Writing?

Elasticsearch uses Lucene under the hood to store and search data. When a document is indexed, the change is recorded in internal structures and the translog. However, for a new searcher to see the document, Elasticsearch must perform a refresh.

A refresh opens new segments for searching, making recent changes visible to search queries. This is a core part of the near real-time search model.

Example:

    1. Application sends an index request for document p-101.
    2. Elasticsearch processes the write operation and acknowledges the request.
    3. Application sends a search query immediately afterward.
    4. Current searcher has not refreshed yet, so it does not see p-101.
    5. A refresh occurs.
    6. Next search query sees p-101.

Consequently, a successful write response does not necessarily mean the document already appears in search results at the moment the response arrives.

### Refresh Is Not Flush

Refresh and flush are two separate concepts:

- **Refresh:** makes new data searchable by opening new segments to searchers.
- **Flush:** performs a Lucene commit and rotates the translog according to Elasticsearch's internal lifecycle.

Triggering a refresh does not mean the application just forced an fsync or added a durability guarantee. Conversely, a document not appearing in search yet does not mean the write was unsaved or lost.

Data durability involves translog durability, replication, cluster settings, and write acknowledgements. Refresh policies primarily control when data becomes visible to search.

## 2. Refresh Happens at the Shard Level

An index is divided into primary shards and possibly replica shards. Searches run against eligible shard copies. A refresh makes written changes visible to the shard's searcher.

Therefore, a refresh is not simply updating an application-level cache. It involves Elasticsearch opening new searchers on the affected shards.

If a write request affects multiple shards, refreshing or waiting for refresh applies across those shards. A write to a separate index does not necessarily need to refresh at the same time if the application only queries a distinct index.

## 3. The Three Refresh Policies

### NONE: Do Not Wait for Refresh

NONE corresponds to refresh=false in the REST API and Elasticsearch Java API Client. This is the appropriate default for most regular write flows.

Characteristics:

- Write requests do not proactively trigger a refresh.
- Requests do not wait for search visibility.
- Elasticsearch continues refreshing on its automatic interval or on other triggers.
- Indexing throughput is generally much higher than forcing refreshes per request.

REST API example:

    PUT products/_doc/p-101?refresh=false
    {
      "name": "Keyboard",
      "price": 45.0
    }

After the request returns successfully, a GET by ID can read the new data immediately thanks to realtime GET. However, a search query may not see the document until the next refresh.

NONE is suitable when:

- The application writes many documents continuously.
- Users do not require instantaneous search updates.
- Short near real-time search latency is acceptable.
- Data is processed in batches or via an ingest pipeline.

### IMMEDIATE: Refresh Immediately

IMMEDIATE corresponds to refresh=true. Elasticsearch requests a refresh of the affected shards before completing the request so the written changes become searchable right away.

Example:

    PUT products/_doc/p-101?refresh=true
    {
      "name": "Keyboard",
      "price": 45.0
    }

Once the request completes, searches on the relevant index can observe the change written by that request.

IMMEDIATE is useful when:

- A business step must write data and immediately execute a search to construct subsequent results.
- A low-volume administrative workflow must confirm data appears in search before advancing.
- An integration test needs deterministic search state immediately after a write.

Do not use IMMEDIATE on every write in high-throughput systems. Frequent refreshes create many small segments, increase merge overhead, and degrade indexing and search efficiency. If each document is written in its own request with an immediate refresh, the cost can be vastly higher than batching data and refreshing once.

### WAIT_UNTIL: Wait for Natural Refresh

WAIT_UNTIL corresponds to refresh=wait_for. The write request executes, and the client waits until a refresh makes the changes searchable.

Example:

    PUT products/_doc/p-101?refresh=wait_for
    {
      "name": "Keyboard",
      "price": 45.0
    }

Unlike IMMEDIATE, WAIT_UNTIL does not force Elasticsearch to refresh immediately. It waits for the next scheduled refresh. Under normal refresh intervals, the wait time is roughly the remainder of the current refresh cycle.

WAIT_UNTIL fits when:

- A request must write a document and return with the guarantee that it is already visible in search.
- You want to avoid forcing a dedicated refresh per request.
- Write frequency is moderate and waiting for the refresh cycle is acceptable.
- A business workflow requires read-after-write via search rather than just GET by ID.

If an index disables automatic refresh via refresh_interval = -1, WAIT_UNTIL may block until a manual refresh or another refresh-triggering operation runs. Therefore, avoid WAIT_UNTIL during bulk loads where automatic refresh is disabled without an explicit refresh plan.

## 4. Comparing the Three Options

| Criterion | NONE / false | IMMEDIATE / true | WAIT_UNTIL / wait_for |
|---|---|---|---|
| Proactively refreshes immediately | No | Yes | No |
| Waits for search visibility | No | Yes, via requested refresh | Yes, until the next refresh |
| Response latency | Typically low | Can be higher due to refresh | Depends on timing of next refresh |
| Refresh cost | Follows automatic schedule | Can grow significantly if overused | Leverages natural refreshes |
| Suitableness for high-volume writes | Usually suitable | Usually unsuitable per request | May fit depending on concurrency and requirements |
| Read-after-write via search | Not immediately guaranteed | Available once request finishes | Available once request finishes |

You can remember them by goal:

- Prioritize throughput and accept eventual visibility: NONE.
- Need search to see data immediately after the request: IMMEDIATE or WAIT_UNTIL.
- Need read-after-write without forcing extra refreshes: WAIT_UNTIL is usually the balanced option.

## 5. Refresh Interval and Search Latency

Elasticsearch automatically refreshes indices according to the refresh interval. In typical configurations, the default interval is 1 second, though the actual value can be changed via index settings and deployment configuration.

Example configuration:

    PUT products/_settings
    {
      "index": {
        "refresh_interval": "5s"
      }
    }

With a 5-second interval, a document written right after a refresh might wait nearly 5 seconds before appearing in search if the request uses NONE and no other refresh occurs.

Increasing the refresh interval can improve indexing efficiency in write-heavy workloads, at the expense of higher search visibility latency. Decreasing the interval surfaces new data faster, but causes more frequent refreshes and higher processing overhead.

Do not alter the global refresh interval just to satisfy one endpoint with special read-after-write requirements. You can apply WAIT_UNTIL to that specific request while keeping the interval tuned for general workloads.

### Infrequently Searched Indices

Elasticsearch optimizes refreshes for indices with low search activity. Depending on the version and index state, refreshes may not occur strictly at the cadence an application assumes from a fixed interval setting. Rely on observed behavior and actual configuration rather than treating the interval as a strict SLA for every index.

## 6. Read-After-Write via GET vs. Read-After-Write via Search

This is an essential distinction when choosing a refresh policy.

Elasticsearch's GET API by document ID is realtime by default. It can read a newly written document from internal structures/translog without waiting for a refresh.

Example:

    PUT products/_doc/p-101?refresh=false
    {
      "name": "Keyboard",
      "price": 45.0
    }

    GET products/_doc/p-101

GET by ID can return the newly written document even when search does not see it yet.

Meanwhile, the query:

    GET products/_search
    {
      "query": {
        "term": {
          "_id": "p-101"
        }
      }
    }

might not find the document before the next refresh.

Thus, if a service only needs to confirm a document was saved by ID, a refresh may be unnecessary. If a service must run a search query, aggregation, or field query immediately after writing, the refresh policy becomes critical.

Do not add refreshes merely because GET by ID behavior was misunderstood. Identify which type of read the business flow actually performs.

## 7. Choosing a Policy per Business Flow

### Continuous Log or Event Ingestion

Log ingestion flows prioritize throughput. Systems can typically tolerate dashboards lagging slightly behind event emission time.

Common recommendation: NONE, letting refreshes follow the default interval or lifecycle. If dashboards need fresher updates, tune the interval based on load and observability needs instead of refreshing immediately per event.

### Creating a Product and Displaying It via Search

Suppose a user creates a product and the next screen immediately searches for that product by name or category. If search must see the data before the response returns, WAIT_UNTIL is a reasonable choice.

If the screen can render the object directly from the create command's response without re-querying Elasticsearch, NONE can be used. The application returns the newly created object directly while the search index updates on its normal refresh schedule.

### Updating Data and Running an Aggregation

If a workflow writes multiple documents and then immediately runs an aggregation that must include all changes, you can:

1. Write the documents with NONE.
2. After the entire batch finishes, call refresh once on the index.
3. Run the aggregation after the refresh completes.

Or use WAIT_UNTIL on the bulk request if your API and client version support it. Batching operations avoids refreshing after every single document.

### Large Bulk Imports

When importing hundreds of thousands or millions of documents:

- Avoid IMMEDIATE on individual requests.
- Consider temporarily increasing the refresh interval or disabling automatic refresh during data loading if your operational plan permits.
- Send bulk requests in bounded batch sizes.
- Once finished, call refresh once so the data becomes searchable.
- Restore the original refresh interval if you changed it.

If refresh_interval was set to -1, ensure the final refresh step runs. Skipping it leaves data invisible to search until another refresh is triggered.

### Integration Tests

Tests usually need deterministic search results immediately after writing. You can use WAIT_UNTIL for writes in tests or call refresh explicitly after saving data:

    productRepository.save(product);
    operations.indexOps(Product.class).refresh();
    List<Product> found = productRepository.findByName(product.getName());

Explicit refreshes decouple tests from automatic refresh timing. However, do not copy this pattern into every production request without a matching requirement.

## 8. Using Refresh in the Elasticsearch Java API Client

The Elasticsearch Java API Client lets you configure the refresh option on write requests. The Refresh enum typically provides values corresponding to False, True, and WaitFor.

Example writing a document and waiting for refresh:

    client.index(request -> request
        .index("products")
        .id("p-101")
        .document(product)
        .refresh(Refresh.WaitFor)
    );

If refresh is omitted, the request typically uses the default behavior of not waiting for refresh.

For bulk requests, you can set a refresh policy on the whole request:

    client.bulk(request -> request
        .refresh(Refresh.WaitFor)
        .operations(operation -> operation
            .index(index -> index
                .index("products")
                .id("p-101")
                .document(product)
            )
        )
    );

A bulk request can contain many items. The refresh option applies at the request level; it does not turn the items into a transaction or make failed items succeed.

Exact enum names and builder methods must match your project's Elasticsearch Java API Client version. Older versions may use different packages or type names.

## 9. Using Refresh with Spring Data Elasticsearch

In Spring Data Elasticsearch, most applications interact via repositories or ElasticsearchOperations. Distinguish entity write APIs from index refresh operations.

### Saving Entities via Repository

Example:

    productRepository.save(product);

or:

    productRepository.saveAll(products);

Do not assume these calls refresh the index by default for immediate search visibility. If the application requires read-after-write via search, choose a refresh control mechanism supported by your Spring Data version and API.

### Explicit Refresh via IndexOperations

Spring Data provides IndexOperations to execute index-level operations:

    IndexOperations indexOperations =
        operations.indexOps(Product.class);

    indexOperations.refresh();

Once refresh finishes, searches on the index can observe prior writes within the refreshed index's scope.

If an entity uses an alias or custom index name, construct IndexOperations with the matching IndexCoordinates to refresh the right target:

    IndexOperations indexOperations =
        operations.indexOps(IndexCoordinates.of("products"));

    indexOperations.refresh();

Do not call refresh through IndexCoordinates that do not point to the index/alias actually used by the write operation.

### Request-Level Refresh Policy

Some Spring Data Elasticsearch write APIs allow configuring a refresh policy per operation or query; where that configuration lives depends on the version and API used. When WAIT_UNTIL or IMMEDIATE is required per request, verify your project's exact API rather than assuming repository.save or saveAll always accepts a RefreshPolicy parameter.

If the repository abstraction does not expose the needed control, you can:

- Call IndexOperations.refresh() after a group of write operations.
- Use ElasticsearchOperations or a write API supporting refresh policies in your current version.
- Use the Elasticsearch Java API Client directly for requests needing specific options.

When calling the client directly, ensure mappings, converters, exception handling, and client configuration stay consistent with the rest of the application.

## 10. Refresh and Bulk Indexing

The Bulk API supports a request-level refresh option. For a batch of multiple documents, WAIT_UNTIL lets the caller proceed only after successful changes have been refreshed.

Example flow:

    1. Build document batch.
    2. Send a bulk request with refresh=wait_for.
    3. Read BulkResponse and inspect each item.
    4. After the response returns, run search if needed.

Keep in mind:

- WAIT_UNTIL does not guarantee every item succeeded.
- A bulk response can still contain partial failures.
- You must check errors and per-item responses.
- Only documents written successfully can appear in search.
- If the request times out, item states may be uncertain and need reconciliation before retrying.

Do not use refresh=true on small consecutive bulk requests when you can combine batches or use WAIT_UNTIL. Every forced refresh can increase small segment counts and add work for the cluster.

## 11. Performance Impact of Refresh

Refreshing makes new data searchable, but it is not free. Frequent refreshes can:

- Produce many smaller segments.
- Increase the number of segments search must manage.
- Increase subsequent segment merge costs.
- Raise CPU and I/O usage during indexing workloads.
- Reduce throughput when the application forces refreshes too often.

IMMEDIATE is especially prone to high cost when applied per document. For instance, an API receiving 100 requests per second where each request writes one document and refreshes immediately creates a far higher refresh rate than batching writes.

WAIT_UNTIL typically reduces forced refreshes because multiple concurrent requests can wait together on a single natural refresh. Still, if too many concurrent requests wait on refresh, the application must bound concurrency and monitor latency.

NONE keeps the write path lighter, while search visibility follows the refresh interval. This is usually the right choice for heavy ingestion and workflows that accept eventual consistency.

## 12. Common Misconceptions

### Thinking a Successful Write Response Means Search Sees It Immediately

Write acknowledgement and search visibility happen at different times. If search must see the document immediately, use WAIT_UNTIL, IMMEDIATE, or an explicit refresh.

### Thinking WAIT_UNTIL Forces an Immediate Refresh

WAIT_UNTIL waits for a refresh to make data visible. It does not proactively force an immediate refresh like IMMEDIATE does.

### Using IMMEDIATE for Every Document

Forcing a refresh after every write increases segment counts and merge overhead. Use it only when read-after-write latency genuinely demands it.

### Thinking NONE Means Data Was Not Saved

NONE simply means not waiting for a refresh. Data is still written through Elasticsearch's write path; search will see it after an automatic or explicit refresh.

### Confusing GET by ID with Search

GET by document ID can be realtime even when search does not see the document yet. Before adding a refresh, check whether the read operation is a GET or a search.

### Confusing Refresh with Durability

Refresh makes data visible to search. It does not replace translog durability, replication, or flush. Do not use a refresh policy as a guarantee that data was fsynced in a particular manner.

### Disabling Refresh Interval and Forgetting to Re-Refresh

During bulk loads, disabling refresh can boost throughput. However, skipping the final refresh leaves data invisible to search. Explicitly document the final refresh and setting restoration steps in the runbook.

### Thinking saveAll Is an Atomic Operation with One Refresh

saveAll may use bulk or another mechanism depending on the version. Even if the request carries a single refresh option, it still does not create an all-or-nothing transaction across documents.

## 13. How to Decide on a Policy

You can choose based on business questions:

| Question | Usually appropriate choice |
|---|---|
| Does search need to see the document right after writing? | If no: NONE |
| Needs immediate search visibility without forcing refreshes? | WAIT_UNTIL |
| Special requirement to force refresh before request returns? | IMMEDIATE |
| Only need GET document by ID after writing? | Usually no refresh needed |
| Running a large bulk data import? | NONE while writing, refresh once after completion |
| Integration test needs to search just-written data? | WAIT_UNTIL or explicit refresh |

Before deciding, verify:

1. Is read-after-write a true business requirement or just a convenience in code?
2. Does the read path use GET by ID or search/query/aggregation?
3. Can the newly written object be returned directly to the client?
4. Does the current refresh delay already meet requirements?
5. What are the write rate and concurrent request count?
6. Can you refresh once after a batch instead of per document?

## 14. Example Service Design for Read-After-Write Needs

Suppose a service creates a product and then returns a search list by name. If the API contract requires the list to include the newly created product, there are two design options.

### Approach A: Use WAIT_UNTIL for the Write Operation

The service writes the document with refresh policy WAIT_UNTIL via the appropriate write API and then executes the search. Once the write request returns, the change is visible to search.

Advantages:

- Straightforward for write-then-search flows.
- No manual refresh calls in the service layer.
- Does not force an immediate refresh if an automatic refresh is imminent.

Trade-offs:

- Product creation requests must wait for a refresh.
- Latency depends on the refresh interval and cluster load.
- Must verify that the Spring Data/client API actually applies WAIT_UNTIL to the write operation.

### Approach B: Write with NONE, Then Refresh Once

If a workflow writes multiple products and then runs an aggregate query, you can:

    productRepository.saveAll(products);
    operations.indexOps(Product.class).refresh();
    return productRepository.searchByCategory("keyboard");

Advantages:

- Combines multiple writes before a single refresh.
- Fits batches or workflows with clear boundaries.

Trade-offs:

- Explicit refresh affects the index and incurs cost.
- With multiple concurrent writers, refreshing can also expose other in-flight changes on the same index.
- Must handle partial errors from saveAll before running search.

If the API only needs to return the newly created object, a simpler third option is returning the object directly from the service without re-searching Elasticsearch. No refresh is needed just to build the response.

## Conclusion

A refresh policy governs when newly written documents become visible to search. NONE does not wait for a refresh and fits high-throughput ingestion; IMMEDIATE forces a refresh before the request returns; WAIT_UNTIL waits for a natural refresh and is typically the balanced choice when read-after-write via search is needed.

Before choosing a policy, distinguish GET by ID from search: GET can be realtime without a refresh, while search requires refreshed data. Refresh also differs from flush and durability; it does not provide transactions or rollbacks for saveAll/bulk. With Spring Data Elasticsearch, use explicit refreshes via IndexOperations or version-supported write APIs with refresh policies. Pay the refresh cost only when business rules truly demand immediate search visibility, and prefer batching operations before a single refresh whenever possible.
