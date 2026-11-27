# BulkOptions, Batch Size, and Version-Specific Limits

When importing or updating many documents in Elasticsearch, sending each document in a separate request typically creates substantial network and processing overhead. The Bulk API lets you send multiple index, create, update, or delete operations in a single request. Spring Data Elasticsearch provides bulk APIs and the `BulkOptions` class to configure several properties of a bulk request.

There are three distinct concepts to separate:

- **BulkOptions:** configures how Elasticsearch processes a single bulk request, such as refresh policy, timeout, active shard copies required, and ingest pipeline if supported by the version.
- **Batch size:** the number of operations or total data volume the application groups into a single bulk request.
- **Version and cluster limits:** limits on HTTP request size, Spring Data APIs, the Elasticsearch Java API Client, operation count, and cluster resources.

`BulkOptions` does not automatically split a large list into multiple batches. The application must determine batch size, chunk the data, and send each bulk request. The appropriate size depends on document size, mapping, shard count, ingest rate, network, and cluster configuration.

## 1. Why Use the Bulk API?

Suppose you need to import 50,000 products into the `products` index. Calling `save` or `index` individually for each product requires sending many requests:

    for (Product product : products) {
        operations.save(product);
    }

Each individual request incurs connection, serialization, scheduling, and Elasticsearch processing overhead. When the document count is large, this cost can degrade throughput.

The Bulk API groups multiple operations into a single request:

    POST products/_bulk
    {"index":{"_id":"p-1"}}
    {"name":"Keyboard K8","price":120}
    {"index":{"_id":"p-2"}}
    {"name":"Mouse M3","price":45}
    {"delete":{"_id":"p-3"}}

A bulk request can contain multiple operation types. Each operation normally has a metadata line and, for index/create/update, a corresponding payload line. Delete only needs the metadata line.

Key benefits:

- Fewer HTTP requests.
- Higher throughput during large data imports.
- Ability to mix index, create, update, and delete in the same bulk request.
- Easy tuning of batch size and worker count.
- Request-level settings can be applied via `BulkOptions`.

Bulk is not a transaction. A request can succeed for some items and fail for others. The application must inspect per-item results.

## 2. Bulk API and BulkOptions Solve Two Different Problems

The Bulk API defines the list of operations to perform. `BulkOptions` configures how that request is sent and handled at the request level.

Examples of responsibilities:

| Component | Question to Answer |
|---|---|
| List of `IndexQuery`/`UpdateQuery` | Which documents or operations need to be executed? |
| `BulkOptions` | Which refresh policy, timeout, routing, or pipeline should the request use? |
| Application batching/chunking | How many operations or bytes go into a single request? |
| Concurrency | How many bulk requests run concurrently? |
| Retry policy | When an item fails transiently, which items are retried and after what delay? |
| Mapping and cluster settings | Are documents, requests, and workload within limits? |

Do not confuse `BulkOptions` with an automatic batch controller. Passing one million `IndexQuery` items into a single `bulkIndex` call does not cause `BulkOptions` to automatically split that list into smaller requests.

## 3. `BulkOptions` in Spring Data Elasticsearch

Spring Data Elasticsearch provides `BulkOptions` as an abstraction for several Bulk API parameters. Common options across modern versions include:

| Option | Meaning |
|---|---|
| `refreshPolicy` | Controls when changes become visible to search |
| `timeout` | Wait timeout for processing conditions supported by the Bulk API |
| `waitForActiveShards` | Number of shard copies required to be active before the operation proceeds |
| `pipeline` | Default ingest pipeline applied to documents in the request |
| `routing` | Default request-level routing when supported by the API and operation |
| `includeSourceOnError` | Whether to include source in error details, if supported by the version |

Exact method names and available options depend on the Spring Data Elasticsearch version. Not every version has the same builder methods or parameter types for timeout, refresh, and `waitForActiveShards`.

Illustrative construction example:

    BulkOptions bulkOptions = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.NONE)
        .withTimeout("2m")
        .withWaitForActiveShards("1")
        .build();

This is an example following the common builder style in modern Spring Data Elasticsearch. Before using it verbatim, verify packages, methods, and overloads in your project's dependency version. If the IDE does not recognize a method, do not substitute an API from another client generation without checking compatibility.

`BulkOptions` does not replace per-`IndexQuery` or per-`UpdateQuery` data. For example, an item's ID, source, version, individual routing, or update script belongs on the operation itself.

## 4. Refresh Policy During Bulk Imports

Refresh determines when newly written documents can be found via search. Indexing and search visibility do not necessarily occur at the same time.

Common choices:

| Refresh Policy | Behavior | When Appropriate |
|---|---|---|
| `NONE` | Do not request an explicit refresh for the request; Elasticsearch refreshes per normal schedule and conditions | Large bulk imports where immediate search visibility is not required |
| `IMMEDIATE` | Request an immediate refresh after the operation | Only when documents must be visible immediately and the cost is acceptable |
| `WAIT_UNTIL` | Wait until a refresh makes changes visible to search | Read-after-write visibility is needed without forcing an immediate refresh |

Enum names and parameter types depend on the Spring Data version. In the REST Bulk API, the corresponding values are typically `false`, `true`, and `wait_for`.

### Why Can `IMMEDIATE` Reduce Throughput?

Refreshing creates a new segment so documents become searchable. If every small batch triggers an immediate refresh, Elasticsearch may produce many small segments, increasing merge and I/O overhead.

For a large import:

1. Send multiple bulk requests with refresh policy `NONE`.
2. Wait for all batches to complete.
3. If search must see the data immediately, trigger a single explicit refresh after the import.

Do not set `IMMEDIATE` by default on every bulk request just to inspect data immediately after each write. Choose visibility requirements based on the use case.

`WAIT_UNTIL` differs from `IMMEDIATE`: it waits for the next refresh to make data visible rather than actively forcing an immediate refresh. If the cluster is under load or refresh is delayed, the request may have to wait.

## 5. Timeout and `wait_for_active_shards`

Timeout and `waitForActiveShards` relate to cluster-side request processing, but they are not the same as the overall HTTP client timeout.

### Timeout

The Bulk API can wait for shard conditions or related operations up to a given duration. The request timeout does not guarantee that every indexing, ingest pipeline, and replication step finishes within that exact time.

The application still needs HTTP client timeouts, job timeouts, and worker deadlines. If the HTTP client times out while the cluster is still processing, the application may not know how far the request progressed. In that case, reconcile state and design safe retries.

### Wait for Active Shards

`wait_for_active_shards` specifies how many shard copies must be active before the request executes. For example, `1` typically means the primary shard must be active; `all` requires the designated shard copies to be active per Elasticsearch semantics.

This option does not mean all replicas have acknowledged every operation after the bulk finishes. It is a precondition on shard availability before execution.

Choosing a higher value can cause requests to wait when a replica is not ready. Choosing a lower value lets writes proceed while the primary is available, though you must understand your system's durability and cluster health requirements.

## 6. Ingest Pipelines in `BulkOptions`

An Elasticsearch ingest pipeline can transform documents before indexing, for example:

- Normalizing fields.
- Creating derived fields.
- Parsing data from an input field.
- Attaching metadata.
- Transforming content using configured processors.

The Bulk API can specify a pipeline at the request level. If your version's `BulkOptions` supports `pipeline`, the application can configure a default pipeline for the operations in the request.

REST example:

    PUT _ingest/pipeline/product-normalize
    {
      "processors": [
        {
          "lowercase": {
            "field": "brand"
          }
        },
        {
          "set": {
            "field": "ingested",
            "value": true
          }
        }
      ]
    }

Bulk request:

    POST products/_bulk?pipeline=product-normalize
    {"index":{"_id":"p-1"}}
    {"name":"Keyboard K8","brand":"KEYCHRON"}

Pipelines add processing time per document. For large imports, benchmark with the pipeline enabled and disabled to understand actual throughput.

If individual operations need different pipelines or need to skip the default pipeline, check override capabilities in your Bulk API and client version. Do not assume `BulkOptions` can express every per-item configuration.

## 7. Default Routing and Per-Document Routing

Routing determines which shard receives a document. With custom routing, documents with the same routing value are placed on the same shard.

`BulkOptions` in some versions can configure request-level routing. This is suitable when all operations in the batch share the same routing value, such as importing data for a single tenant.

If each document has a different routing value, routing must be placed on each respective index/update operation. Do not use a single default routing value if it routes documents to the wrong shard.

Example:

    IndexQuery query = IndexQuery.builder()
        .withId(product.getId())
        .withObject(product)
        .withRouting(product.getTenantId())
        .build();

The builder method name for routing depends on the Spring Data version. Confirm that routing is sent in the metadata of each bulk item.

Incorrect routing can cause:

- Documents to reside on a different shard than the one routing-based queries search.
- Updates/deletes to miss the document.
- Parent-child relations to fail because parent and child are not on the same shard.
- One shard to overload if routing funnels most data into a single value.

## 8. Batch Size: Count Documents or Measure Bytes?

A batch of 1,000 small documents can be lighter than a batch of 100 large documents. Therefore, limiting only by document count is insufficient to control request size.

Monitor all of:

- Number of operations in a batch.
- Total bytes of the NDJSON payload.
- Average and high-percentile document sizes.
- Completion time per bulk request.
- Error counts and rejected items.

A common starting approach is testing batch payloads from a few MB up to around 10 MB, then benchmarking to find a good throughput region. A range of 5–15 MB is often used as an experimental starting point, not a mandatory limit or optimal setting for every cluster.

Do not create huge requests just to reduce API calls. Large requests consume memory in the application, across the network, and on coordinating/data nodes; when failures occur, retries are also costlier.

### Estimating Batch Size

Suppose the average JSON document size is about 4 KB. With 1,000 documents per batch, the raw payload is approximately:

    4 KB × 1,000 = 4 MB

The actual size also includes bulk metadata lines, newlines, field escaping, and variance across documents. Measure serialized bytes if you need strict request size limits.

A starting configuration might look like:

    int maxDocumentsPerBatch = 1000;
    long maxPayloadBytes = 8L * 1024 * 1024;

    // Add operations until either limit is reached.
    // Send the batch and continue with the remaining data.

These are baseline values for benchmarking. A good batch size must be determined from real data and cluster capacity.

## 9. Elasticsearch Request Size Limits

Elasticsearch enforces an HTTP request size limit via the `http.max_content_length` setting. A common default is 100 MB, though this can be changed and may vary by version or deployment environment.

Do not size bulk requests right up to the maximum limit:

- Requests may be rejected before bulk actions are processed.
- Buffering and serialization can create memory pressure.
- Proxies, gateways, or load balancers may enforce lower limits than Elasticsearch.
- A huge request is harder to retry and takes longer when failures happen.

Check your actual cluster configuration and network infrastructure. Reverse proxies or ingress controllers can also have lower limits than `http.max_content_length`.

The Bulk API uses NDJSON. Each action and source must be properly formatted, each line must end with a newline, and the request must end with a final newline. A standard JSON array is not a valid bulk request format.

## 10. No Fixed Maximum Document Count for Every Bulk Request

The Bulk API does not define a single universal maximum document count suitable for every system. Practical limits depend on:

- Source document size.
- Number of operations and metadata.
- Number of receiving shards.
- Ingest pipelines and mappings.
- Disk and CPU speed.
- Heap, indexing buffer, and indexing pressure.
- Number of concurrent bulk requests.
- Thread pool queues and backpressure.

A batch of 10,000 tiny documents may run smoothly in one environment yet cause rejections or high latency in another. Benchmark with payloads matching production size and distribution.

## 11. Bulk API in Spring Data Elasticsearch

Spring Data Elasticsearch provides `ElasticsearchOperations` for bulk execution. Depending on the version, common methods include `bulkIndex` for `IndexQuery`, `bulkUpdate` for `UpdateQuery`, and `bulkDelete` for delete operations.

Example building `IndexQuery` items:

    List<IndexQuery> queries = products.stream()
        .map(product -> IndexQuery.builder()
            .withId(product.getId())
            .withObject(product)
            .build())
        .toList();

    BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.NONE)
        .build();

    List<IndexedObjectInformation> result =
        operations.bulkIndex(
            queries,
            options,
            IndexCoordinates.of("products")
        );

Common types:

    import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
    import org.springframework.data.elasticsearch.core.IndexedObjectInformation;
    import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
    import org.springframework.data.elasticsearch.core.query.BulkOptions;
    import org.springframework.data.elasticsearch.core.query.IndexQuery;

Packages or signatures of some classes can differ between major versions. Inspect your actual dependency and import from the exact Spring Data Elasticsearch version in use.

The example above builds one `IndexQuery` list and sends it in a single bulk request. If `products` contains too many elements, split the list into batches before calling `bulkIndex`. `BulkOptions` does not chunk that list automatically.

## 12. Splitting a List into Multiple Batches

A simple approach is chunking by document count:

    int batchSize = 1000;

    for (int start = 0; start < products.size(); start += batchSize) {
        int end = Math.min(start + batchSize, products.size());
        List<Product> batch = products.subList(start, end);

        List<IndexQuery> indexQueries = batch.stream()
            .map(product -> IndexQuery.builder()
                .withId(product.getId())
                .withObject(product)
                .build())
            .toList();

        operations.bulkIndex(
            indexQueries,
            bulkOptions,
            IndexCoordinates.of("products")
        );
    }

This is easy to read when document sizes are relatively uniform. When document sizes vary significantly, split by estimated total bytes or serialized bytes to avoid abnormally large batches.

### Avoid Materializing All `IndexQuery` Objects in Memory

If the data source has millions of documents, do not load everything into a `List` before chunking. Read data by page or stream:

    while (source.hasNext()) {
        List<Product> batch = source.readNextBatch(1000);
        bulkIndex(batch);
    }

This pseudocode illustrates sequential reading and sending. The source can be a database cursor, file reader, message queue, or paginated API.

Streaming bounds application memory and enables backpressure. Establish checkpoints so the job can resume or rerun after failures.

## 13. Bulk Update and Delete

Bulk is not limited to new indexing. Applications can batch `UpdateQuery` items or IDs to delete.

Example creating an update query:

    UpdateQuery update = UpdateQuery.builder(product.getId())
        .withDocument(Document.from(
            Map.of("price", product.getPrice())
        ))
        .build();

Then send multiple updates:

    operations.bulkUpdate(
        updateQueries,
        bulkOptions,
        IndexCoordinates.of("products")
    );

`UpdateQuery` builder details and `Document` types vary by version. For updates, clarify:

- Partial document vs. scripted update.
- Whether upsert is used.
- Behavior when the document does not exist yet.
- Version or optimistic concurrency control.
- Retry on conflict if supported by the operation API.

Bulk delete can group multiple IDs or queries depending on the Spring Data overload. Verify method signatures and ensure routing is provided if documents use custom routing.

## 14. Repository `saveAll` and `BulkOptions`

Spring Data repositories provide `saveAll` to save multiple entities:

    productRepository.saveAll(products);

This is a convenient API when fine-grained request configuration is unnecessary. Spring Data Elasticsearch implementations can optimize multi-entity saves using bulk under the hood, but internal behavior and the ability to pass `BulkOptions` depend on the version.

If you need control over refresh policy, timeout, `waitForActiveShards`, or pipeline, `ElasticsearchOperations` with bulk methods and `BulkOptions` generally gives more explicit control.

Do not assume `saveAll` always uses your desired batch size or automatically splits any huge list into smaller requests at a fixed threshold. Check the implementation of your version and chunk data manually when control matters.

## 15. Bulk Responses and Partial Failures

The Bulk API can return a successful HTTP response while some items inside fail. The response contains an `errors` field and an `items` list corresponding to each operation.

Example:

    {
      "took": 25,
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
              "type": "mapper_parsing_exception",
              "reason": "failed to parse field"
            }
          }
        },
        {
          "index": {
            "_id": "p-3",
            "status": 429,
            "error": {
              "type": "es_rejected_execution_exception",
              "reason": "rejected execution"
            }
          }
        }
      ]
    }

In this example:

- `p-1` was indexed successfully.
- `p-2` failed because the data did not match the mapping.
- `p-3` was temporarily rejected due to processing pressure.

Do not check only the HTTP status or assume the entire bulk request succeeded simply because the method did not throw an exception. Inspect item-level results or the exception/result object returned by Spring Data.

### Error Classification

| Error Type | Example | Typical Action |
|---|---|---|
| Invalid data | Mapping parse error, wrong field type | Route to dead-letter/error report, fix the data |
| Conflict | Version conflict | Re-read state or apply controlled retry |
| Temporary overload | HTTP 429, rejected execution | Backoff then retry failed items |
| Temporary shard/cluster issue | Unavailable shard, timeout | Retry with limits after checking status |
| Configuration error | Missing index, invalid pipeline | Stop batch/job and fix configuration |

Retrying the entire bulk request when only a few items failed can repeat operations that already succeeded. For `index` with a stable ID, resending the same document may be idempotent in final state, but incrementing updates or non-idempotent scripts could be applied twice.

## 16. Retry and Backoff

When Elasticsearch returns 429 or temporary overload errors, do not retry continuously without pause. A common approach is exponential backoff with jitter:

    delay = min(maxDelay, baseDelay * 2^attempt)
    delay = random(0, delay)

For example, wait intervals can grow across 100 ms, 200 ms, 400 ms, 800 ms and cap at a maximum threshold. Jitter prevents multiple workers from retrying at the exact same instant.

Principles:

- Only retry errors that are potentially transient.
- Cap the maximum number of attempts.
- Retry failed items when possible rather than blindly resending the whole batch.
- Keep the same ID and payload so operations remain safely repeatable where appropriate.
- Do not retry mapping or data errors that cannot resolve on their own.
- Record failed items for reconciliation.
- Stop increasing concurrency if the cluster is overloaded.

Some clients or frameworks have built-in retries for specific errors. Check the behavior of the version in use to avoid stacking multiple retry layers and amplifying load.

## 17. Idempotency of Bulk Operations

Safe retries depend on the operation type:

| Operation | Typical Repeatability |
|---|---|
| `index` with same ID and same source | Usually yields the same final state |
| `create` with same ID | Subsequent attempt may conflict because the document already exists |
| `delete` with same ID | Usually repeatable, though status/result can differ |
| `update` setting fixed values | Can be idempotent with the same payload and semantics |
| `update` incrementing a counter | Not idempotent if applied multiple times |
| Script adding a value | Not idempotent if retried after the first attempt succeeded |

If the client times out and receives no response, the application cannot assume Elasticsearch did not execute the request. The state may be ambiguous. Design repeatable operations, re-check the document, or use an idempotency key/marker.

For snapshot imports, indexing by stable ID is usually easier to retry than increment-style updates. For event streams, persist an event ID or version to avoid applying the same event multiple times.

## 18. Tuning Batch Size for Throughput

There is no fixed optimal batch size. The best approach is step-by-step benchmarking:

1. Start with a small batch size and low worker count.
2. Measure payload bytes, latency, throughput, and errors.
3. Increase batch size incrementally.
4. Observe whether throughput keeps rising or has saturated.
5. When latency, memory, or rejections spike, reduce batch size or concurrency.
6. Re-test with large documents, pipelines enabled, and realistic mappings.

Metrics to monitor:

- Documents per second.
- Bytes per second.
- Bulk request latency p50/p95/p99.
- Failed item counts by status/error type.
- HTTP 429 and rejected execution counts.
- Application JVM heap, GC pauses, and allocation rate.
- Cluster CPU, disk I/O, and indexing pressure.
- Write/bulk thread pool queue and rejected counts per version.
- Segment count, merge time, and refresh activity.

If throughput stops increasing as batch size grows, the bottleneck may be disk, ingest pipeline, mapping, shard distribution, or concurrency rather than documents per request.

## 19. Tuning Concurrency and Backpressure

Batch size and concurrent request count are two separate variables. A large batch with one worker can yield very different throughput from smaller batches with multiple workers.

Setting concurrency too high can:

- Fill the write/bulk thread pool queue.
- Increase indexing pressure.
- Increase memory and network buffering.
- Accumulate many pending HTTP requests.
- Drive up 429 errors and retries.
- Increase latency of other search and indexing workloads.

A safe strategy:

- Start with few workers.
- Increase concurrency only while the cluster has headroom.
- Cap the number of queued batches.
- On repeated 429s, reduce concurrency or increase backoff.
- Do not let the producer read faster than Elasticsearch can write over extended periods.

This is backpressure: when Elasticsearch slows down, the data source must throttle down rather than accumulating an unbounded in-memory queue.

## 20. Mapping and Document Limits

The Bulk API does not bypass per-document limits. A bulk operation must still respect:

- Mapping field types.
- Document and request size limits.
- Field count limits or mapping explosion.
- Nested object limits if documents contain nested data.
- Ingest pipeline and script constraints.
- Versioning and concurrency controls.

If bulk fails with `mapper_parsing_exception`, increasing batch size or changing timeouts will not fix the data error. Inspect the source and mapping.

### Mapping Explosion

If importing data with uncontrolled dynamic field names, the number of fields in the mapping can grow rapidly. This consumes cluster memory and slows queries or hits the total fields limit.

Standardize the schema, use `flattened` or appropriate objects for dynamic key-value data where the use case permits, and constrain dynamic mapping.

## 21. Spring Data Elasticsearch Version Limits

Spring Data Elasticsearch has changed its client integration across major versions. Differences that commonly affect bulk code:

- Package and type of `BulkOptions`.
- Builder methods and parameter types for timeout, refresh, and `waitForActiveShards`.
- Signatures of `bulkIndex`, `bulkUpdate`, and `bulkDelete`.
- Return types and how item errors are represented.
- Underlying client: older generations used High Level REST Client; modern generations use Elasticsearch Java API Client.
- How ingest pipeline, routing, and extra options are configured.

Do not take a code snippet from documentation of another major version and assume it compiles in your current project.

### Identifying the Version in Use

Check the resolved Spring Data Elasticsearch dependency in the build:

    ./gradlew dependencies

Or use `dependencyInsight` with the appropriate configuration:

    ./gradlew dependencyInsight \
        --dependency spring-data-elasticsearch \
        --configuration runtimeClasspath

On Windows PowerShell, you can run the corresponding Gradle wrapper command:

    .\gradlew.bat dependencyInsight --dependency spring-data-elasticsearch --configuration runtimeClasspath

Also check the transitive Elasticsearch Java API Client version. Do not upgrade the client independently if Spring Data manages a compatible version.

### Checking the Actual `BulkOptions` API

In your IDE or the resolved dependency's Javadoc, verify:

- Package of `BulkOptions`.
- Methods available on the builder.
- Parameter types expected for timeout and refresh policy.
- Overloads of `bulkIndex`/`bulkUpdate`/`bulkDelete`.
- Return types and how item-level errors are read.

If you need behavior not exposed by your version's `BulkOptions` abstraction, consider using the underlying client API or upgrading Spring Data according to the compatibility matrix. Do not mix request classes from legacy and modern clients in the same implementation.

## 22. Elasticsearch Server Version Limits

Elasticsearch server also introduces changes to the Bulk API, mappings, ingest pipelines, and cluster settings across versions. When the application and cluster differ in major/minor version, check:

- Whether API endpoints and fields are supported by the server version.
- Whether the client sends a compatible request format.
- Whether new bulk actions and options are accepted by the server.
- Whether mapping types or field types remain valid.
- Values of cluster settings like `http.max_content_length` and indexing pressure.
- Whether thread pool, queue, and request size limits differ from other environments.

Do not rely on defaults from a different cluster. Inspect the running cluster and documentation for the exact version.

### Do Not Confuse Client Limits with Server Limits

A request can be constrained at multiple layers:

    Application builds payload
          |
          v
    Spring Data / Java API Client
          |
          v
    HTTP client and connection pool
          |
          v
    Proxy / gateway / ingress
          |
          v
    Elasticsearch HTTP layer
          |
          v
    Coordinating node and data node

Limits at a lower layer can cause a request to be rejected before Elasticsearch processes it. When investigating request-too-large or timeout errors, identify which layer actually returned the error.

## 23. Safe Bulk and Alias Usage During Reindex/Import

When importing into an index managed behind an alias, ensure bulk operations write to the intended target index. For an alias pointing to multiple indices, writes require a proper write index.

Some versions of `BulkOptions` or the Bulk API support `require_alias` to enforce that the target must be an alias. Where supported, this option helps prevent accidentally writing directly to a physical index.

Do not assume every Spring Data `BulkOptions` version provides the corresponding method. If this requirement is critical, verify the client API and actual request generated by your version.

A safe import workflow typically includes:

1. Create the new index with defined mappings and settings.
2. Bulk import in bounded batches.
3. Verify document counts, item errors, and sample queries.
4. Refresh when needed to verify data via search.
5. Switch the alias using an appropriate operation.
6. Keep a rollback plan according to operational procedures.

Do not switch the alias before import and verification complete if users need continuous data availability.

## 24. Bulk with Ingest Pipeline and Refresh in an Import Job

A large import job might use configurations such as:

    BulkOptions options = BulkOptions.builder()
        .withRefreshPolicy(RefreshPolicy.NONE)
        .withTimeout("2m")
        .withWaitForActiveShards("1")
        .withPipeline("product-normalize")
        .build();

    for (List<Product> batch : batches) {
        List<IndexQuery> queries = toIndexQueries(batch);
        operations.bulkIndex(
            queries,
            options,
            IndexCoordinates.of("products")
        );
    }

After all batches finish, if immediate search verification is needed:

    operations.indexOps(IndexCoordinates.of("products"))
        .refresh();

This example follows common builder APIs; check the `pipeline` option and `RefreshPolicy` types in your actual version. Post-import refresh should be performed intentionally and is unnecessary if the application accepts visibility on the normal refresh schedule.

If a batch has failed items, the job must record the failed items and decide whether to continue or halt. Do not mark the import complete simply because the loop finished sending requests.

## 25. Tracking and Handling Errors in Spring Data

Spring Data APIs can return metadata for successful operations and can throw exceptions when a bulk request fails at the request level. Depending on the version, some item failures may be represented in an exception or response object.

Do not assume every item failure surfaces as the exact same exception. Check the method return type and documentation for your version.

A handling flow should:

1. Send the batch.
2. Receive the result or exception.
3. Distinguish request-level errors from item-level errors.
4. Record ID, operation type, status, and reason for failed items.
5. Retry transient errors with backoff.
6. Route non-retryable data errors to an error file or dead-letter queue.
7. Update the checkpoint after finishing batch processing per policy.

Do not log entire sensitive sources on failure. If payloads must be stored for investigation, apply data protection policies and retention limits.

## 26. Byte-Based Batch Sizing

For data with varying sizes, you can build a byte-based chunker:

    List<IndexQuery> currentBatch = new ArrayList<>();
    long currentBytes = 0;

    for (Product product : source) {
        IndexQuery query = toIndexQuery(product);
        long estimatedBytes = estimateBulkBytes(query);

        boolean countLimitReached =
            currentBatch.size() >= maxDocuments;
        boolean byteLimitReached =
            currentBytes + estimatedBytes > maxPayloadBytes;

        if (!currentBatch.isEmpty()
                && (countLimitReached || byteLimitReached)) {
            sendBulk(currentBatch);
            currentBatch.clear();
            currentBytes = 0;
        }

        currentBatch.add(query);
        currentBytes += estimatedBytes;
    }

    if (!currentBatch.isEmpty()) {
        sendBulk(currentBatch);
    }

This is illustrative code. `estimateBulkBytes` must account for both metadata and source serialization in bulk format. If using a different JSON serializer than Spring Data's serializer, byte estimates can drift. A more accurate approach is using the same serializer or measuring actual payload bytes before sending.

For extremely large documents, handle them separately so a single document does not exceed request limits. You cannot split one document's JSON source across multiple bulk items to bypass size limits while keeping the document intact.

## 27. Common Mistakes

### Thinking `BulkOptions` Automatically Splits Batches

`BulkOptions` configures the request, not a chunker. The application must split lists into multiple requests for large datasets.

### Limiting Only by Document Count

Document sizes vary. Track both operation count and total payload bytes.

### Setting Batches Right Near the Max Request Limit

Proxies, gateways, or Elasticsearch can reject requests. Leave headroom and benchmark with real payloads.

### Using `IMMEDIATE` for Every Batch

Frequent refreshes increase segment counts and reduce throughput. Use `NONE` for large imports if immediate search visibility is not required.

### Assuming `WAIT_UNTIL` Is the Same as `IMMEDIATE`

`WAIT_UNTIL` waits for the next refresh to make data visible; `IMMEDIATE` requests an immediate refresh. They have different behaviors and costs.

### Checking Only HTTP Status

Bulk can succeed at the request level while having failed items. Inspect `errors` and per-item results.

### Retrying the Whole Batch When One Item Fails

This can re-apply operations that already succeeded. Classify errors and retry only failed items where appropriate.

### Retrying Mapping Errors Infinitely

Data errors do not resolve on retry. Route items to error handling to fix the data or mapping.

### Increasing Concurrency When the Cluster Is Already Rejecting

More workers can worsen overload. Apply backpressure and throttle down when receiving 429s.

### Using One Routing Value for a Multi-Tenant Batch

Request-level routing only fits when all operations share the same routing. With varying routing keys, configure per item.

### Assuming `saveAll` Has a Fixed Batch Size

Internal behavior depends on version. When batch size control is needed, chunk manually and use the appropriate bulk API.

### Copying `BulkOptions` Code from Another Major Version

Builder methods and packages change across Spring Data/client versions. Verify actual dependencies before applying.

### Confusing Request Timeout with Total Job Duration

Bulk API timeout, HTTP client timeout, and job timeout are separate layers. Design deadlines, retries, and state reconciliation separately.

## 28. Bulk Import Design Workflow

A practical workflow can follow this order:

1. Identify the operations to execute: `index`, `create`, `update`, or `delete`.
2. Verify mappings and ingest pipelines before importing large data.
3. Choose stable IDs and proper routing per document.
4. Pick an initial batch size based on document count and total bytes.
5. Start with a low worker count and scale up via benchmarks.
6. Use `BulkOptions` to set appropriate refresh, timeout, active shards, and pipeline options.
7. Send each batch via `ElasticsearchOperations` or the corresponding API.
8. Inspect per-item results and classify errors.
9. Retry transient errors using bounded backoff.
10. Write dead-letter/error reports for data or configuration errors.
11. Monitor throughput, latency, 429s, heap, disk, and indexing pressure.
12. Tune batch size/concurrency based on metrics.
13. Refresh once post-import if immediate visibility is required.
14. Mark the job complete only once every item has been processed per policy.

## Conclusion

`BulkOptions` configures bulk request properties such as refresh policy, timeout, `waitForActiveShards`, pipeline, or routing depending on the version. Batch size is a separate application decision: split data into multiple requests and control both operation count and total payload bytes. The Bulk API is not a transaction; a request can contain both successful and failed items, so you must inspect per-item results, classify errors, and retry with limits.

In Spring Data Elasticsearch, `ElasticsearchOperations` provides bulk methods for sending `IndexQuery`, `UpdateQuery`, or delete operations along with `BulkOptions`. Repository `saveAll` is convenient for simple use cases, but do not assume it exposes every request option or controls batch size. Check the exact versions of Spring Data Elasticsearch and Elasticsearch Java API Client resolved in your build, as packages, builder methods, and option types can change across major versions. Benchmark with realistic payloads, shard counts, concurrency, and workloads; choose refresh and backpressure strategies appropriately to achieve high throughput without overloading the cluster.
