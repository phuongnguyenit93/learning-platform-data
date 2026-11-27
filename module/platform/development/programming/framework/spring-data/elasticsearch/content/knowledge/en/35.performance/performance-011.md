# Heap, Off-Heap Memory, Disk, and the Cost of Large Indexes

As an Elasticsearch index grows, performance does not depend solely on JVM heap size. Elasticsearch runs on Lucene, simultaneously using heap, native/off-heap memory, the filesystem page cache, and disk. Each layer serves a distinct role: heap holds many runtime structures and transient data; the page cache accelerates reading segments; off-heap holds certain buffers and native structures; and disk stores segments, translogs, and shard copies.

A node can have plenty of free heap and still have slow searches because the page cache is starved, disk latency is high, or shards are oversized. Conversely, a node with a relatively modest heap and a healthy filesystem cache can serve searches smoothly. Looking at heap usage alone is insufficient to conclude a node has spare capacity.

With Spring Data Elasticsearch, costs also arise on the application side: entity mapping, JSON serialization, bulk request buffers, connection pools, and collecting too many results into collections. For large indexes, you must measure both Elasticsearch nodes and the Spring application JVM.

This lesson explains how memory and storage layers work together, why large indexes raise costs, how to monitor them, and how to design mappings, shards, bulks, refreshes, and workloads to maintain stable performance.

## 1. Resource map of an Elasticsearch node

An Elasticsearch architecture can be visualized across these layers:

    Spring Boot application
      - Entity objects
      - Query and bulk request buffers
      - HTTP client connections
      - JSON serialization
                 |
                 v
          Network / HTTP
                 |
                 v
    Elasticsearch JVM process
      - Java heap
      - Thread stacks
      - Direct/native buffers
      - JVM metadata and runtime
      - Elasticsearch data structures
                 |
                 v
          Lucene / filesystem
      - Inverted index
      - Stored fields and _source
      - Doc values
      - Segment files
      - Translog
                 |
                 v
       Operating system page cache
                 |
                 v
              Disk

These layers are not completely independent. Lucene reads segments from the filesystem; the OS can keep recently read blocks in the page cache. Elasticsearch manages metadata and several runtime structures on the heap. The JVM uses native memory for runtime, thread stacks, and direct buffers. The Spring application creates its own objects and buffers before sending requests.

When investigating performance, identify where the bottleneck sits:

- Heap or garbage collection.
- Native memory or direct buffers.
- Filesystem page cache.
- Disk throughput, IOPS, or latency.
- CPU and thread pools.
- Network or connection pools.
- Application-side mapping/serialization costs.

## 2. What is the JVM heap?

Heap is the JVM memory region used to allocate Java objects. Elasticsearch uses heap for many runtime structures, such as:

- Cluster state and index/shard metadata.
- Certain Lucene and segment reader metadata.
- Query execution structures.
- Aggregation state and bucket structures.
- Fielddata.
- Filter/query cache metadata.
- Indexing buffers and ingest-related structures.
- Request state, coordination, and temporary objects.

Heap is managed by the garbage collector. Unreferenced objects can be reclaimed, though GC consumes CPU and can introduce pauses. Under high heap pressure, request latency rises, allocations can fail, or nodes can suffer memory errors.

Heap usage must be observed over time. A single snapshot showing low heap right after GC does not reflect peak workload usage. Inspect:

- Heap used.
- Heap committed and maximum.
- Old generation occupancy.
- GC count and GC pause duration.
- Allocation rate.
- Back-to-back GC cycles.

## 3. Not all index data lives on the heap

A common misconception is that a large index needs a heap sized to the entire index volume. Lucene stores most index data as segment files on the filesystem. Elasticsearch and Lucene rely on the operating system's page cache to accelerate access to those files.

For example, a node holding hundreds of gigabytes of index data does not need hundreds of gigabytes of JVM heap. Heap stores metadata, caches, and active runtime structures; segment files sit on disk and are cached in RAM by the OS.

This explains why assigning all system RAM to the heap is usually counterproductive. Nodes need RAM left over for the filesystem cache so Lucene can efficiently read postings, doc values, and stored fields.

When heap is oversized:

- Less RAM remains for the page cache.
- GC cycles can take longer.
- Larger object graphs raise management overhead.
- Depending on JVM/platform, exceeding compressed OOPs thresholds makes object references larger.
- Searches hit disk more often when data no longer fits in OS cache.

Do not size heap solely from total index size. Base it on real heap pressure, query mix, shard count, aggregations, indexing rate, and RAM needed for OS caching.

## 4. Off-heap and native memory

Beyond the heap, a JVM process consumes native memory. These regions are not fully reflected in `heap used` metrics.

Examples:

- Thread stacks per thread.
- Direct ByteBuffers.
- Native libraries and runtime allocations.
- JIT compiler code cache.
- Metaspace holding class metadata.
- TLS/network buffers.
- Memory-mapped file mappings.
- Native structures of libraries and the OS.

As a result, total process RSS can vastly exceed `heap used`.

A node reporting 55% heap usage while process RSS approaches the container memory limit can still be OOM-killed. Never rely solely on heap charts to judge remaining node RAM.

### Heap vs. off-heap/native

| Characteristic | Heap | Off-heap/native |
|---|---|---|
| Management | JVM garbage collector | JVM/native libraries/OS |
| Measurement | Heap metrics | Process RSS, native memory, OS metrics |
| Lifecycle | By reachability and GC | By API/library/OS lifecycle |
| Pressure | GC, allocation, heap exhaustion | Native memory exhaustion, direct buffer pressure |
| Examples | Java objects, aggregation state | Direct buffers, thread stacks, mmap |

Not every memory-mapped file represents pinned resident RAM. Mappings occupy virtual address space; which pages actually stay resident is managed by the OS page cache and memory manager.

## 5. Filesystem page cache

The filesystem page cache is RAM used by the OS to cache file contents. Lucene segments reside on disk, and previously read blocks can stay in the page cache so subsequent reads are far faster.

The page cache is especially critical for search because queries frequently read:

- Inverted index postings.
- Term dictionaries.
- Norms.
- Doc values.
- Stored fields and `_source`.
- Segment metadata.

If hot data fits in the page cache, many reads are served from RAM. When the cache is insufficient or workloads scan scattered data, the OS must read from disk more often.

This means:

- Free heap does not guarantee fast searches.
- Fast disks still do not replace the page cache.
- An index larger than RAM is not automatically a problem if the working set is small and stable.
- Random queries over a huge working set can trigger heavy cache misses.

When benchmarking, record both process memory and node memory/page cache metrics. Never inspect JVM heap alone.

## 6. Disk stores segments and translogs

Elasticsearch uses Lucene to store indexes. Segment files form the foundational storage of an index. Common data components:

- Inverted index for looking up terms in text/keyword fields.
- Doc values for sorting, aggregations, and per-document field access.
- Stored fields and `_source` for returning document contents.
- Norms and metadata for scoring.
- Segment metadata and reader structures.
- Translog to protect acknowledged writes before segments flush/commit per Elasticsearch's durability mechanism.

Disk must also hold:

- Primary shard data.
- Replica shard data.
- Translogs.
- Temporary files during merges and recoveries.
- Snapshot caches or related files depending on infrastructure.
- Other indexes on the same node.
- Logs and system files if sharing the same filesystem.

The index size shown by a single API does not necessarily capture temporary costs or node-level files. When sizing disks, include store size, translogs, replicas, merge headroom, recovery, and growth.

## 7. Inverted index and storage cost

For `text` fields, Elasticsearch tokenizes content and builds an inverted index. This structure enables fast term lookups, with storage size depending on:

- Document count.
- Tokens per document.
- Term cardinality.
- Token length.
- Analyzers and normalizers.
- Number of `text` fields.
- Term frequencies and positions if stored.

A long description with an analyzer storing positions can consume far more storage than a simple `keyword` field. If the same content is indexed into multiple fields or subfields, cost multiplies.

Do not turn every field into `text`. Fields used for filtering, sorting, or aggregations normally fit `keyword`/numeric/`date` and doc values. Mappings should reflect actual query requirements.

## 8. Doc values: disk space traded for per-document access

Doc values are column-oriented structures stored on disk and used for sorting, aggregations, scripting, or per-document field lookups. For most eligible fields, doc values are enabled by default.

Doc values are not a heap cache. Lucene reads them via the filesystem and page cache. An aggregation query can still allocate state on the heap even though the underlying field values live in doc values on disk.

Example:

    "properties": {
      "category": {
        "type": "keyword"
      },
      "price": {
        "type": "double"
      },
      "createdAt": {
        "type": "date"
      }
    }

These fields typically suit filtering, sorting, and aggregations. When designing mappings, consider:

- Which fields need text search?
- Which fields need exact matching?
- Which fields need sorting/aggregations?
- Which fields only need display from `_source`?
- Which fields do not need indexing at all?

Disabling doc values can save some storage while disabling or limiting sorting/aggregations and certain lookups. Do not disable them just to save disk if workloads rely on those operations.

## 9. Stored fields and _source

`_source` usually retains the original JSON document in compressed form. When returning search hits, Elasticsearch may have to read and decompress `_source` for each hit.

If an API only needs ID, name, and status, returning a large full `_source` increases:

- Disk reads.
- Decompression CPU.
- Network bytes.
- Heap allocation in Elasticsearch and the application.
- JSON mapping/serialization cost.

Source filtering reduces how much `_source` is returned, without removing stored data or acting as authorization. Stored fields are a separate mechanism applying only to fields configured with `store`.

In Spring Data, if an endpoint needs only a subset of fields, consider source filtering and DTO projections. However, never pass a partially loaded entity back to save the entire document, as omitted fields may be overwritten or lost.

## 10. What are segments?

A Lucene index is organized into immutable segments. On refresh, recent writes become new segments visible to search. Once written, a segment is never modified in place the way a relational database updates a row.

Document updates are handled logically by marking the old version deleted and indexing a new version. Deletes similarly mark documents as deleted; physical space is reclaimed only when segments merge.

Consequently, an index with heavy updates/deletes can contain:

- Many segments.
- Deleted documents awaiting merge cleanup.
- Old files lingering until merges complete.
- Numerous structures to open and manage.

Segment counts and fragmentation affect searches, memory, file descriptors, and merge work.

## 11. Refreshes create new segments and affect workloads

Refresh makes recent writes searchable. Refresh is distinct from flush and is not a database transaction commit.

When refreshes run too frequently:

- Many small segments are created.
- Each search may need to inspect more segments.
- Segment metadata and reader overhead increase.
- Merges must process many tiny segments.

When refreshes run too infrequently:

- Search visibility lags.
- Users may not see recently written documents.

For heavy indexing workloads, consider longer refresh intervals or `RefreshPolicy.NONE` during bulk imports, refreshing afterward when needed. Align the choice with search freshness requirements.

In Spring Data Elasticsearch, `RefreshPolicy` can be set on certain operations. Avoid using `IMMEDIATE` on every document unless immediate read-after-write is required.

## 12. Segment merges and disk cost

Lucene merges multiple small segments into larger segments to optimize index layout and purge deleted documents.

Merges require:

- Reading input segments.
- Writing new output segments.
- CPU to process postings, doc values, and stored fields.
- Disk bandwidth and IOPS.
- Temporary disk space while old and new segments coexist.

During merges, disk usage can spike temporarily. Disk sizing based purely on steady-state index size will lack headroom for merges, recoveries, and reindexing.

Merges can be throttled under heavy disk or indexing load. While throttling protects the cluster, it can also grow the merge backlog.

Monitor merge time, merge throttling, segment counts, and disk utilization. Do not run force merge frequently on actively written indexes, as it is resource-intensive and increases write amplification.

## 13. Updates and deletes increase write amplification

Elasticsearch does not update a field in place inside a segment file like a database row update. An update creates a new document version and marks the old one deleted. Only later merges physically reclaim the old data.

If the same document is updated repeatedly:

- Segments holding old versions occupy disk until merged.
- Translog and indexing work rise.
- Merges must process many deleted documents.
- Disk write amplification increases.

For very large documents where only a small field updates frequently, reindexing the whole source can be costly. Consider document modeling and separating fast-changing fields from large static payloads if the use case allows.

## 14. Translog and durability

The translog records operations so Elasticsearch can recover acknowledged writes according to durability semantics. The translog is managed separately from Lucene segment files.

Distinguish these steps:

- Index request is processed.
- Translog is written and persisted per durability settings.
- Refresh makes documents searchable.
- Flush performs a Lucene commit and clears the translog accordingly.

The translog can occupy extra disk space. Under high write rates or delayed flushes, translog size can grow.

Do not confuse refresh with durability. Nor should you arbitrarily disable translog durability just to inflate benchmark numbers without understanding data-loss risks on node/process crashes.

## 15. Cost of replicas

Each primary shard can have one or more replica shards. Replicas provide fault tolerance and search capacity, while requiring storage and indexing resources.

If primary store size is P and there are R replicas, steady-state shard-copy data size is approximately:

    total shard copies ~= P * (1 + R)

This estimates shard data only, excluding translogs, merge headroom, recovery, filesystem overhead, and other indexes.

Replicas also increase:

- Disk usage.
- Network replication traffic.
- CPU and disk writes.
- Recovery duration when a node leaves the cluster.

Replicas can boost search throughput since queries distribute across shard copies. However, adding replicas is not free speed; benchmark both reads and writes.

## 16. Shards have memory and metadata costs

Each shard is a standalone Lucene index. A shard maintains segments, readers, file handles, metadata, and background tasks.

Too many small shards introduce overhead:

- Larger cluster state.
- More shard allocation and recovery tasks.
- More segment readers.
- More file descriptors.
- Higher request fan-out.
- Higher heap and native resource usage.
- Merge and refresh overhead spread across many shards.

Too few or oversized shards also carry trade-offs:

- A single shard can become a hotspot.
- Recovering a huge shard takes longer.
- Harder to balance load evenly.
- Parallelism is constrained.

Choose shard count based on data size, write rate, query fan-out, recovery objectives, and target shard size. Never create one shard per tenant if there are many small tenants.

## 17. Large index cost is more than store size

A large index imposes costs across multiple layers:

| Component | Primary cost |
|---|---|
| Inverted index | Disk, page cache, query CPU |
| Doc values | Disk, page cache, aggregations/sorting |
| _source/stored fields | Disk, decompression, network, and mapping |
| Segment metadata | Heap/native memory, file descriptors |
| Deleted docs | Storage and merge work before cleanup |
| Translog | Disk and recovery work |
| Replicas | Disk, network, and indexing CPU |
| Shard metadata | Heap, cluster state, and coordination |
| Aggregation state | Heap and CPU |
| Fielddata | Can grow heap sharply |
| Caches | Heap/native or page cache depending on type |

A smaller index running high-cardinality aggregations can exert far higher heap pressure than a huge index queried with simple filters.

## 18. Fielddata can create heap pressure

Fielddata is an on-heap structure used to access per-document field values for certain field types, notably `text` when sorting or aggregating.

Aggregating on a `text` field can force Elasticsearch to build fielddata. With high cardinality, fielddata can consume huge amounts of heap.

Unsuitable mapping example:

    "customerName": {
      "type": "text",
      "fielddata": true
    }

If exact matching, sorting, or terms aggregations are needed, usually add a `keyword` subfield:

    "customerName": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword"
        }
      }
    }

Then aggregate on `customerName.keyword` instead of enabling `fielddata` on `text`.

Fielddata can stay cached on the heap and cause memory pressure. Enable it only when genuinely required and cardinality is understood.

## 19. Doc values do not eliminate all aggregation costs

`keyword`/numeric/`date` fields typically use on-disk doc values. This avoids loading entire field values onto the heap like `text` fielddata.

However, aggregations still allocate runtime structures:

- Bucket maps.
- Counts and metrics.
- Parent/child aggregation state.
- Pipeline aggregation data.
- Response serialization.

High-cardinality terms aggregations can still create vast bucket structures and consume heap even when backed by doc values. Cap `size`, use `composite` aggregations when paging through many buckets, and avoid requesting unneeded buckets.

## 20. Query cache and request cache

Elasticsearch provides caches with distinct semantics. The query cache can retain shard-level filter bitsets for eligible queries. The shard request cache can cache results of certain requests, often useful for aggregations on slowly changing data.

Caches cut CPU and disk work, yet consume memory and depend on workload:

- Repeated queries can hit caches.
- Constantly changing queries see low hit rates.
- Segment changes affect cache entries.
- The request cache does not cache every search response by default.

Do not increase cache sizes simply because free heap exists. Monitor hits/misses, evictions, and memory. An ill-suited cache can occupy heap while barely reducing latency.

## 21. Aggregations can consume large amounts of heap

Aggregations maintain state while queries execute. Cost depends on:

- Number of documents evaluated.
- Field cardinality.
- Bucket count.
- Depth of nested aggregations.
- Nested/parent-child structures.
- Pipeline aggregations.
- Number of shards involved.

For example, a terms aggregation on `productId` across millions of distinct values can allocate huge bucket counts:

    {
      "size": 0,
      "aggs": {
        "by_product": {
          "terms": {
            "field": "productId",
            "size": 100000
          }
        }
      }
    }

Do not request giant bucket counts if the UI only displays the top 10. When iterating all buckets, consider `composite` aggregations and bucket pagination.

Circuit breakers can reject requests projected to exceed memory limits. This protects the node rather than being an error to work around by raising limits endlessly.

## 22. Circuit breakers

Elasticsearch uses circuit breakers to stop operations at risk of consuming excessive memory. Breakers exist for requests, fielddata, in-flight requests, and other areas depending on version.

When a breaker trips:

- The request can be rejected.
- The client receives an exception.
- Searches or aggregations fail even with valid query syntax.

Investigate:

- Which breaker tripped?
- Which query or aggregation produced the high memory estimate?
- What are the cardinality and bucket counts?
- Are many heavy requests executing concurrently?
- What is the current heap and GC state?

Do not blindly raise breaker limits. If a request truly needs more memory than available heap, raising limits can turn a controlled rejection into a node OOM.

## 23. Indexing buffer

Elasticsearch uses an indexing buffer to accumulate documents during indexing before flushing them into segments. The buffer is managed per node and shared across active writing shards.

Under high write rates:

- The buffer fills quickly.
- New segments are created more often.
- Merge load increases.
- CPU and disk throughput climb.

Increasing the indexing buffer does not automatically improve throughput if the bottleneck is disk, CPU, merges, or network. Monitor indexing pressure, refreshes, merges, and disk utilization.

For bulk indexing, client batch size and concurrency must match node ingest capacity. Sending too many concurrent requests grows queues and indexing pressure.

## 24. Indexing pressure

Elasticsearch tracks indexing pressure to bound memory consumed by active indexing requests across coordinating, primary, and replica stages. Exact mechanisms and metrics vary by version.

When indexing pressure is high:

- Bulk requests may be rejected.
- 429s can spike.
- Client queues and retries grow.
- Heap/native memory pressure increases.

Client adjustments:

- Lower concurrency.
- Pick moderate bulk sizes.
- Apply backoff and jitter when retrying 429s.
- Separate failed items from successful batches when the API permits.
- Monitor queue time and indexing latency.

Do not respond to overload by spinning up endless workers. The system needs backpressure so send rates match cluster processing capacity.

## 25. Disk watermarks and cluster allocation

Elasticsearch monitors disk usage and enforces watermarks to keep nodes from running out of disk. When nodes cross thresholds, the cluster can restrict allocation or relocate shards depending on configuration/version.

Consequences of disk pressure:

- Shards cannot be allocated.
- Replicas become unassigned.
- Cluster health turns yellow or red.
- Merges/recoveries can run out of space.
- Writes may be blocked when crossing the flood-stage watermark.

Exact watermarks and enforcement depend on Elasticsearch version/configuration. Never raise watermarks too high just to silence alerts; nodes need free space to merge, recover, and keep ingesting.

Monitor free disk per node, not just cluster-wide totals. One node can fill up while the cluster shows spare capacity due to skewed shard distribution.

## 26. Estimating disk capacity

A rough estimation model:

    primary data size
      = document count * average primary bytes per document

    steady shard-copy storage
      ~= primary data size * (1 + replica count)

    required disk
      = steady shard-copy storage
        + translog allowance
        + merge/recovery headroom
        + growth allowance
        + other index/system overhead

This is a planning model, not an exact sizing formula. Average document bytes must be measured after indexing with the real mapping and analyzers, not copied straight from raw JSON payload size.

When planning capacity:

- Measure store size after ingestion and steady-state merges.
- Account for replicas.
- Reserve space for segment merges.
- Reserve space for shard relocations/recoveries.
- Project growth.
- Maintain free disk respecting watermarks and operational policy.
- Verify every node has enough space under actual shard allocation.

## 27. Reindexing and merges require headroom

Reindexing from an old index to a new index temporarily requires space for both indexes simultaneously:

    old index
    + new index under construction
    + replicas
    + translog
    + merge headroom
    + recovery headroom

If disk only fits the final index, reindexing can fail midway while both old and new indexes coexist.

When rolling out a new index version:

1. Estimate target index size.
2. Check free space on each node.
3. Account for replicas and merge headroom.
4. Create the new index.
5. Reindex in controlled batches.
6. Monitor disk, merges, and indexing pressure.
7. Reconcile document counts/data.
8. Switch aliases.
9. Delete the old index only after deliberate verification.

## 28. Shard size and shard count

Overly small shards raise management overhead. Oversized shards slow recoveries, complicate load balancing, and risk hotspots.

No single shard size fits every workload. Appropriate sizing depends on:

- Document count.
- Mapping and field count.
- Write rate.
- Query fan-out.
- Recovery time objectives.
- Disk type.
- Node count and RAM.
- Segment count and update/delete frequency.

Measure actual shard sizes via `_cat/shards` or index stats. Monitor distribution across nodes and shards per node.

Do not pick shard counts using a rigid blog formula without benchmarking your workload and recovery.

## 29. Data streams, rollover, and index lifecycle

For append-only time-series data, data streams and rollover split data into backing indexes by size or age.

Benefits:

- Time-based retention management.
- Bounded size per backing index.
- Separating hot from older data.
- Easy deletion of expired indexes via lifecycle policies.

Costs:

- Many backing indexes/shards if rolling over too often.
- Alias/data stream metadata.
- Reindex or force merge overhead on policy changes.
- Queries may fan out across many backing indexes.

Pick rollover thresholds matching size and age appropriately. Rolling over too early creates tiny indexes; too late creates huge shards and slow recoveries.

## 30. Index lifecycle and tiered storage

Data can be tiered by access temperature:

- Hot: recent data, frequent searches/writes, fast storage.
- Warm: less mutable data, still searched.
- Cold/frozen: rarely accessed data, storage-cost optimized.

Tiered architectures can cut overall cost while increasing operational complexity:

- Allocation and data migration.
- Snapshot/cache behavior.
- Differing search latency across tiers.
- Replica and recovery policies.
- Query fan-out across tiers.

Do not judge the entire index solely by hot-tier latency if production also queries cold data. Benchmarks should simulate age-weighted access ratios.

## 31. Heap sizing and keeping RAM for the page cache

Heap must suffice for cluster metadata, query/aggregation state, fielddata, caches, and indexing load, yet should not consume all node RAM.

A common operational rule is reserving a substantial portion of RAM for the filesystem cache. Elasticsearch often auto-sizes heap in supported deployments; if set manually, follow version-specific guidance.

Do not copy a fixed heap size blindly across differing nodes. Appropriate heap depends on:

- Node RAM.
- Shard count and segment count.
- Aggregation workload.
- Fielddata.
- Indexing rate.
- Cluster state size.
- Query concurrency.
- JVM version and compressed pointers behavior.

Avoid raising heap simply because process RSS is high. RSS can include page cache or native memory. Identify which region is growing before tuning.

## 32. Large heaps can make GC more expensive

A large heap is not automatically bad, yet larger object graphs require GC to manage more memory. Some collectors handle large heaps well, though pauses, concurrent CPU, and allocation pressure still require monitoring.

Warning signs:

- Old generation frequently near full.
- Long GC pauses.
- High allocation rate.
- Latency spikes coinciding with GC events.
- Circuit breakers or memory pressure alerts.

Do not shrink heap immediately if the workload truly needs it. First inspect allocation-heavy queries/aggregations, fielddata, caches, shard counts, and applications sending excessive concurrent requests.

## 33. Native memory and container limits

In containers, memory limits apply to the process/container via cgroups. Maximum heap does not represent total memory usage.

Total memory can include:

    JVM heap
    + metaspace
    + code cache
    + thread stacks
    + direct buffers
    + native libraries
    + memory mappings / resident pages
    + other process memory

If the container limit sits too close to max heap, the process can be OOM-killed before heap hits max.

When running Elasticsearch or Spring Boot in Kubernetes:

- Set memory requests/limits with native headroom.
- Verify JVM container awareness.
- Monitor RSS and cgroup memory.
- Monitor CPU throttling.
- Cap thread counts and concurrency reasonably.
- Avoid setting heap equal to the full container limit.

Do not inspect only Kubernetes pod restart counts; check `OOMKilled` reasons and memory graphs prior to termination.

## 34. Spring Data Elasticsearch also consumes memory

The application side can generate heavy memory pressure when reading or writing large volumes:

- Every document is converted into Java objects.
- Serializers allocate byte buffers.
- Bulk requests retain many `IndexQuery` objects or request items.
- Search result mapping creates entities and nested collections.
- `collectList` buffers all hits until stream completion.
- DTO mapping allocates new objects.
- Web layers serialize response JSON.

Dangerous example:

    List<Product> all =
        repository.findAll();

    List<ProductResponse> responses =
        all.stream()
            .map(ProductResponse::from)
            .toList();

With millions of documents, both the entity list and response list coexist on the heap. This causes massive allocations and can trigger `OutOfMemoryError` in the Spring application even while Elasticsearch nodes remain healthy.

Use pagination, streaming, or bounded batch processing. Never collect an entire index into an in-memory list just to export it.

## 35. Bulk requests in Spring Data

Bulk indexing lowers network overhead, though oversized batches hold many objects and serialized bytes in memory.

Batch example:

    List<IndexQuery> batch = products.stream()
        .map(product -> IndexQuery.builder()
            .withId(product.getId())
            .withObject(product)
            .build())
        .toList();

    operations.bulkIndex(
        batch,
        BulkOptions.builder()
            .withRefreshPolicy(RefreshPolicy.NONE)
            .build(),
        IndexCoordinates.of("products")
    );

After each bulk completes, drop references to the batch before loading the next one. In long pipelines, avoid retaining all batches inside one big list.

Balance batch size by document count and total bytes. 1,000 tiny documents differ hugely from 1,000 documents whose sources are hundreds of KB each.

Monitor:

- Application heap.
- Bulk request bytes.
- Bulk latency.
- 429s and partial failures.
- Elasticsearch indexing pressure.
- Merges and disk throughput.

## 36. Reactive does not mean infinite memory

Reactive Streams and backpressure regulate downstream demand. Yet if an application calls `collectList`, uses unbounded buffers, or runs `flatMap` at excessive concurrency, memory can still spike.

Example:

    Flux<SearchHit<Product>> hits = ...;

    Mono<List<Product>> products =
        hits.map(SearchHit::getContent)
            .collectList();

`collectList` retains every `Product` until the stream terminates. With hundreds of thousands of hits, application heap can swell rapidly.

For large datasets:

- Process in bounded batches.
- Cap `flatMap` concurrency.
- Use backpressure.
- Stream results out incrementally.
- Use PIT/`search_after` or scroll per appropriate APIs.
- Avoid keeping entities and DTOs for the whole index simultaneously.

Client-side backpressure does not shrink Elasticsearch server heap if server-side aggregations already build huge bucket structures.

## 37. Source filtering cuts transfer and mapping costs

When an endpoint needs only a few fields, source filtering cuts bytes transferred from Elasticsearch to the application and reduces fields converted.

Example:

    Query query = NativeQuery.builder()
        .withQuery(q -> q.matchAll(m -> m))
        .withSourceFilter(
            new FetchSourceFilter(
                new String[] {"name", "price", "category"},
                null
            )
        )
        .build();

However, source filtering does not remove fields from the index and is not authorization. Nor does it reduce query-engine costs if the query still reads other fields for filtering, sorting, or aggregating.

If source filtering produces a partial entity, never save that entity back to overwrite the whole document without restoring omitted fields. Map to a read-only DTO instead.

## 38. Query response size and heap

A search returning many hits increases:

- Elasticsearch fetch phase.
- Source decompression.
- Network bytes.
- Client JSON parsing.
- Entity mapping.
- Application heap.
- HTTP response serialization.

Shrinking page size, projecting needed source fields, and returning lean DTOs cut costs. Still, do not reduce `size` arbitrarily if the API needs clear pagination semantics.

For large exports, stream page by page with checkpoints instead of returning a single JSON response containing millions of documents.

## 39. Overly wide mappings inflate indexes

Dynamic mapping can create vast field counts when documents hold dynamic objects or data-driven keys. Wide mappings increase:

- Cluster state metadata.
- Field lookup overhead.
- Mapping serialization and propagation.
- Segment metadata and query planning complexity.
- Risk of hitting field-count limits.

For example, a document containing a map keyed by user-generated values can spawn thousands of mapped fields under dynamic mapping.

Use `flattened` fields, structured object models, or disable dynamic mapping for subtrees that do not need per-key querying, depending on use case and version.

Do not index every property just because it exists in `_source`. Choose indexed fields from actual search/filter/sort/aggregation requirements.

## 40. Multi-fields increase index size

A text field with multiple subfields:

    "name": {
      "type": "text",
      "fields": {
        "keyword": {
          "type": "keyword"
        },
        "english": {
          "type": "text",
          "analyzer": "english"
        }
      }
    }

Each subfield creates additional index structures and storage. Multi-fields are useful when one value needs multiple query patterns, yet unused analyzers/subfields should not be added blindly.

Audit mappings and query usage before adding fields. Unqueried fields merely bloat indexes and burn indexing CPU.

## 41. Nested data increases Lucene document counts

Nested objects are stored as separate internal Lucene documents linked to their parent. A single source document with many nested children produces many more Lucene documents than source documents.

If each product averages 20 offers, Lucene document counts are vastly higher than product record counts.

This impacts:

- Index size.
- Indexing throughput.
- Query cost.
- Nested aggregations.
- Segment counts and merges.

Benchmarks for nested mappings must reflect production child-count distributions, especially p95/p99 nested object counts per parent.

## 42. Routing and shard distribution

Custom routing can cut shard fan-out for tenant-scoped queries, yet can also pack data onto fewer shards.

For example, if the largest tenant owns 40% of data and shares one routing key, its shard can run much hotter than all others.

Monitor:

- Store size per shard.
- Document count per shard.
- Per-shard indexing rate where exposed.
- Search request distribution.
- CPU/disk per node.

Do not look solely at total cluster resources. A single hot node or shard can throttle an entire workload even while other nodes sit underutilized.

## 43. Snapshots are not live shard copies

Snapshots store backups in an external repository. They must not be counted as live replica shards serving searches, and snapshot sizes may benefit from sharing/deduplication depending on repository and snapshot history.

When planning capacity, track:

- Active index disk.
- Replicas.
- Merge/recovery headroom.
- Snapshot repository capacity.
- Snapshot retention.
- Snapshot/restore throughput.

Do not place snapshot repositories on the same disk path as node data if doing so causes I/O contention or exhausts disk space.

## 44. Recovery and relocation also consume resources

When a node leaves the cluster or shards relocate, Elasticsearch copies shard data and rebuilds state.

Recovery uses:

- Disk reads/writes.
- Network bandwidth.
- CPU.
- Heap/native buffers.
- File descriptors.

During recovery, search and indexing latency can climb. A cluster benchmarked solely in steady state will not reveal recovery behavior under node failures.

If availability and recovery times matter, test recovery separately in a safe environment. Never induce arbitrary node failures in production.

## 45. Monitoring heap and the JVM

Inspect JVM stats via Node Stats:

    GET _nodes/stats/jvm

Fields of interest:

- Heap used/committed/max.
- Memory pools.
- GC collectors.
- GC collection counts/time.
- JVM uptime.

Track per node over time. A node with noticeably higher heap pressure than peers may host a hot shard, large fielddata, or uneven queries.

Do not conclude from one point-in-time snapshot. Observe trends, peaks, and correlations with request latency.

## 46. Monitoring process and native memory

Node Stats `process` provides process memory and CPU metrics:

    GET _nodes/stats/process

Combine with OS/container metrics:

- RSS.
- Virtual memory.
- Cgroup memory usage.
- OOM events.
- Thread count.
- CPU utilization.
- CPU throttling.

If heap is flat while RSS climbs steadily, investigate direct buffers, native allocations, thread counts, memory mappings, and OS cache. Distinguish process RSS from node-wide page cache according to how your OS/container reports them.

## 47. Monitoring filesystem and disk

Node stats filesystem:

    GET _nodes/stats/fs

Index stats:

    GET products/_stats/store,segments,translog,merge,refresh,flush

Useful Cat APIs for inspection:

    GET _cat/indices?v&h=index,pri,rep,docs.count,store.size,pri.store.size

    GET _cat/shards/products?v

Monitor:

- Free disk per node.
- Primary and total store size.
- Translog size.
- Segment count.
- Current/total/time for merges.
- Merge throttling.
- IOPS and disk latency.
- Read/write throughput.
- Shard allocation and recovery.

Store size is not the total disk space required. Always compare against filesystem free space and growth/merge/recovery plans.

## 48. Monitoring indexing, search, and breakers

Index stats expose counters for indexing/search/merge/refresh:

    GET products/_stats/indexing,search,merge,refresh,flush,fielddata,query_cache,request_cache

Node stats inspect breakers and thread pools:

    GET _nodes/stats/breaker,thread_pool,indices

Monitor:

- Indexing total/current time.
- Search query/fetch counts and time.
- Rejected requests.
- Fielddata memory.
- Query/request cache hits/misses.
- Breaker estimated/limit/tripped counts.
- Thread pool queues and rejected counts.
- Indexing pressure if exposed by version.

Counters are typically cumulative since node startup. Compute rates via time deltas while handling node restarts/resets.

## 49. Monitoring cluster and shard allocation

APIs:

    GET _cluster/health

    GET _cluster/stats

    GET _cat/nodes?v

    GET _cat/allocation?v

These help observe:

- Cluster health.
- Node count.
- Shard count.
- Unassigned shards.
- Disk allocation.
- Index/store totals.
- Node roles.

A `green` cluster does not mean nodes are balanced or workloads have good latency. A cluster can be green while suffering a hot shard, high heap, or high disk latency.

## 50. Spring Boot Actuator and Micrometer

On the application side, Spring Boot Actuator and Micrometer can collect:

- JVM memory and GC.
- Process CPU.
- HTTP server request durations.
- Connection pool metrics when exposed by client integration.
- Thread pool and executor metrics.
- Custom timers around `ElasticsearchOperations`.
- Bulk failure and retry counters.

Example timing an imperative search operation:

    @Service
    public class ProductSearchService {

        private final ElasticsearchOperations operations;
        private final MeterRegistry registry;

        public ProductSearchService(
                ElasticsearchOperations operations,
                MeterRegistry registry) {
            this.operations = operations;
            this.registry = registry;
        }

        public SearchHits<Product> search(Query query) {
            Timer timer = registry.timer(
                "product.search.duration",
                "operation",
                "search"
            );

            return timer.record(() ->
                operations.search(query, Product.class)
            );
        }
    }

This timer measures the service call duration, not just search engine query time. It includes network, conversion, and client-path steps.

Do not attach high-cardinality raw query text, document IDs, or tenant IDs to metric tags. Use bounded query family and operation names.

## 51. Measuring reactive operations properly

Reactive publishers are lazy. Measuring only `Mono` creation time does not measure request execution time.

Example:

    Mono<ReactiveSearchHits<Product>> result =
        reactiveOperations.search(query, Product.class);

Timing must span subscription through terminal signals, or use configured Micrometer Observation/Reactor instrumentation.

Never call `block()` just to wrap with `Timer.record`. Use `Mono.defer` to start the timer upon subscription and stop it in `doFinally`, or use dedicated instrumentation.

For long reactive streams, distinguish:

- Time to receive response metadata.
- Time to emit the first hit.
- Time to emit the last hit.
- Time for downstream processing to finish.

A `Flux` can hold resources and subscriptions open for a long time; a single total duration may not pinpoint the bottleneck.

## 52. Heap pressure in Spring applications

Spring applications can grow heap due to:

- Oversized search page sizes.
- `collectList` on large `Flux` streams.
- Bulk batches retaining many objects.
- DTO mapping allocating new objects.
- JSON serialization buffers.
- In-memory retry queues.
- Unbounded application caches.
- Large async executor queues.

Example:

    Flux<SearchHit<Product>> hits = ...;

    Mono<List<Product>> products =
        hits.map(SearchHit::getContent)
            .collectList();

`collectList` retains all `Product` instances until the stream ends. With hundreds of thousands of hits, application heap can spike sharply.

Use batch processing, bounded concurrency, and streaming responses. Enforce strict caps on page sizes and queues.

## 53. Distinguishing Spring Boot heap from Elasticsearch heap

The Spring Boot application and Elasticsearch are typically separate processes. Each has its own JVM heap, GC, native memory, and container limits.

A dashboard showing only Elasticsearch heap will not tell you whether the Spring application hit `OutOfMemoryError` while mapping responses.

Monitor separately:

| Component | What to measure |
|---|---|
| Spring Boot JVM | Heap, GC, RSS, allocation, thread pools |
| Elasticsearch JVM | Heap, GC, breakers, indexing/search state |
| OS/node | Page cache, free memory, disk I/O, CPU |
| Network | Bytes, latency, retransmissions, connections |
| Storage | Free space, IOPS, latency, throughput |

If both processes share one host, they compete for RAM, CPU, and disk. Budget combined memory limits and ensure neither starves the other's page cache or native memory.

## 54. Optimizing mappings to shrink index footprint

Good mappings reduce storage and indexing work:

- Use `keyword` for exact matching instead of `text` if full-text is unneeded.
- Avoid creating multi-fields without a query use case.
- Pick matching numeric/date types.
- Disable `index` on fields returned solely from `_source` and never queried.
- Evaluate `doc_values` based on sort/aggregation needs.
- Constrain dynamic fields.
- Use `nested` only when nested semantics are required.
- Never index secrets or unqueried data.
- Avoid duplicating the same payload into multiple fields.

Every mapping change must consider both query semantics and reindexing effort. Saving storage by disabling capabilities the application uses breaks functionality.

## 55. Reducing fielddata and aggregation pressure

If fielddata grows:

1. Identify which fields hold fielddata.
2. Inspect queries/aggregations using those fields.
3. If a `text` field needs exact buckets, add a `keyword` subfield in a new index.
4. Switch aggregations to the `keyword` field.
5. Reindex data if mapping changes require it.
6. Monitor heap and breakers afterward.

Do not repeatedly clear the fielddata cache as a long-term fix. The cache will rebuild, adding CPU and latency spikes.

## 56. Reducing segment and merge pressure

To keep segments under control:

- Choose `refresh_interval` based on freshness needs.
- Avoid `IMMEDIATE` refresh on every document.
- Use bulk indexing instead of repeated tiny requests.
- Never force merge actively written indexes.
- Monitor merge backlogs and throttling.
- Choose an appropriate shard count.
- Limit unnecessary updates and deletes.

For nearly immutable indexes, force merge can be useful inside controlled lifecycle workflows. For continuously updated indexes, force merge causes write amplification and I/O contention.

## 57. Reducing _source and fetch costs

When searches only need a handful of fields:

- Use source filtering.
- Reduce page size.
- Use DTOs instead of returning full entities.
- Avoid requesting highlights/`inner_hits` unless needed.
- Avoid returning huge nested payloads.

If source filtering yields partial entities, never use them to overwrite whole documents. Separate read models from write models.

Source filtering shrinks response payloads, does not delete fields from the index, and is not a security control. For field-level authorization, enforce appropriate security policies.

## 58. Optimizing bulks and refreshes in Spring Data

A bulk job can use bounded batches:

    for (List<Product> batch : batches) {
        List<IndexQuery> queries = batch.stream()
            .map(product -> IndexQuery.builder()
                .withId(product.getId())
                .withObject(product)
                .build())
            .toList();

        operations.bulkIndex(
            queries,
            BulkOptions.builder()
                .withRefreshPolicy(RefreshPolicy.NONE)
                .build(),
            IndexCoordinates.of("products")
        );
    }

This is an imperative example. Size batches by bytes and cluster capacity. After import, trigger a single refresh if immediate search visibility is required.

Avoid keeping the entire source list, entire `IndexQuery` list, and response list in memory simultaneously for large datasets. Stream source batches, write each batch, release references, and continue.

## 59. Optimizing query concurrency

Many heavy queries running together can exhaust node heap and CPU. A high-cardinality aggregation might run fine solo yet trip breakers when 50 arrive at once.

In the application:

- Bound concurrency per endpoint.
- Apply rate limits to heavy queries.
- Set sensible timeouts.
- Enforce pagination and bucket limits.
- Prevent retry storms.
- Add application-level circuit breakers where appropriate.

In Elasticsearch:

- Monitor thread pools and breakers.
- Monitor search queues/rejections.
- Inspect shard fan-out.
- Optimize queries and mappings.

Do not arbitrarily inflate thread pools or queues; higher concurrency can worsen heap pressure.

## 60. When should you add nodes or scale resources?

Before scaling, identify which resource is actually saturated:

- Sustained high CPU.
- High heap pressure/GC.
- Page cache too small for the working set.
- Disk latency or throughput hitting limits.
- Network saturation.
- Shard hotspots.
- Excessive query fan-out.
- Indexing pressure or merge backlogs.

Scaling up (faster CPU/RAM/disks) and scaling out (adding nodes) solve different problems. Adding nodes will not redistribute shards immediately if allocation/routing blocks it. Adding RAM and dumping all of it into heap shrinks the page cache.

After changing resources, rerun the same workload to measure real gains and costs.

## 61. Capacity planning with growth

Planning needs projections for:

- New documents per day.
- Source size growth.
- Field count and mapping evolution.
- Update/delete rates.
- Replica count.
- Retention period.
- Rollover frequency.
- Snapshot retention.
- Reindex windows.
- Growth headroom.

Example model:

    daily_primary_growth = new_docs_per_day
                          * measured_primary_bytes_per_doc

    retained_primary_size = daily_primary_growth
                            * retention_days

    steady_shard_data = retained_primary_size
                        * (1 + replicas)

Then add translogs, merge/recovery headroom, index overhead, and other indexes. Calibrate the model with actual measured store size after ingest.

Never use raw JSON input size as primary bytes per document, because analyzers, postings, doc values, source compression, and mappings alter storage substantially.

## 62. Large indexes and reindexing strategy

When mappings or analyzers change, you may need a new index and reindex. On large indexes, this consumes:

- Disk for both old and new indexes.
- CPU and disk reads/writes.
- Inter-node network bandwidth.
- Heap/native buffers.
- Merge resources.
- Time to catch up on ongoing changes.

Design versioned aliases:

    products-v1
    products-v2
          |
          v
      products alias

Reindex into `v2`, reconcile data, and atomically switch the alias. Keep `v1` long enough for rollback per policy.

Never start reindexing without sufficient disk headroom. Never delete the old index before confirming the alias and new data work properly.

## 63. Testing memory and disk under load

A test plan should cover:

- Bulk indexing up to projected scale.
- Search-only on a steady index.
- Mixed search/write.
- High-cardinality aggregations.
- Update/delete workloads.
- Reindexing.
- Node restarts/recovery.
- Long soak tests to observe merges and cache behavior.

Collect:

- Peak heap and GC pauses.
- RSS and cgroup memory.
- Page cache/available memory.
- Free disk and disk latency.
- Store size/translog.
- Segment counts and merges.
- Indexing pressure.
- Breaker trips.
- Search p95/p99.
- Bulk throughput and failures.

Short tests can miss merge backlogs or memory leaks. Run long enough for workloads to reach steady state.

## 64. Common mistakes

### Thinking a large index needs heap equal to index size

Most Lucene segments live on disk and rely on the filesystem cache. Heap holds runtime structures, caches, and query state.

### Allocating all RAM to heap

The page cache shrinks and GC can grow more expensive. Leave RAM for the OS and native memory.

### Looking only at heap used

RSS, direct buffers, thread stacks, page cache, and cgroup limits matter just as much.

### Thinking doc values use no memory

Doc values reside on disk yet are accessed via the page cache; aggregations still allocate runtime state.

### Enabling fielddata on text for aggregations

This can create heavy heap pressure. Use `keyword` subfields when semantics match.

### Unbounded high-cardinality aggregations

Bucket state can exhaust heap and trip breakers. Cap `size` or use composite pagination.

### Refreshing too frequently

Creates many tiny segments and raises merge overhead. Choose an appropriate freshness policy.

### Force merging frequently

Expensive on disk/CPU and unsuitable for actively written indexes.

### Creating too many small shards

Raises cluster state, reader, file handle, and coordination overhead.

### Counting only primary store when sizing disk

Misses replicas, translogs, merge headroom, recovery, and growth.

### Oversized bulk batches

Both application and cluster hold excessive memory, latency climbs, and retries cost more. Bound by bytes and concurrency.

### Using collectList on large indexes

Retains all entities in application heap. Stream or batch instead.

### Raising concurrency when 429s already appear

Worsens overload. Slow down, back off, and tune batches.

### Ignoring page cache/disk metrics

Heap charts can look fine while search is disk-I/O bound.

### Reindexing without disk headroom

Coexisting old and new indexes, merges, and recoveries can run nodes out of disk.

### Scaling nodes without checking shard distribution

Hot shards can still bottleneck throughput. Check allocation and routing.

## 65. Process for investigating slow nodes or oversized indexes

When search/indexing degrades:

1. Identify which nodes and shards carry heavy load.
2. Check cluster health, allocation, and free disk.
3. Inspect heap, GC, and breakers.
4. Inspect RSS, native memory, and container limits.
5. Inspect page cache, disk latency, and throughput.
6. Check segment counts, merges, and translog.
7. Check indexing pressure and thread pool queues/rejections.
8. Inspect fielddata, query cache, and request cache.
9. Review query mix, aggregation cardinality, and shard fan-out.
10. Check application heap, bulk batching, and response sizes.
11. Use slow logs/Profile API to inspect specific queries.
12. Change one factor, rerun the workload, and compare p95/p99 alongside resources.

Do not start by bumping heap or node count before finding the bottleneck. A wrong resource change can worsen the situation or merely mask the root cause.

## 66. Large index design checklist

- Mappings index only fields needed by queries.
- `text` fields have `keyword` subfields when exact match/aggregation is needed.
- `fielddata` is not enabled carelessly.
- Aggregation cardinality is controlled.
- `_source` payloads contain no unnecessary bloat.
- Dynamic mapping is constrained.
- Nested object counts stay within reasonable bounds.
- Shard counts match data size and workload.
- Replicas are factored into disk and write capacity.
- `refresh_interval` matches freshness needs.
- Bulk batches and concurrency are bounded.
- Disk has merge/recovery headroom.
- Heap leaves ample room for page cache and native memory.
- JVM heap/GC are monitored over time.
- RSS and cgroup limits are monitored.
- Snapshot and reindex capacity are budgeted separately.
- Spring Data never pulls entire datasets into memory.
- Query response sizes and source filtering are evaluated.
- Monitoring alerts on breakers, 429s, disk watermarks, and merge backlogs.

## Conclusion

Large-index performance depends on balancing JVM heap, native/off-heap memory, the filesystem page cache, and disk. Heap retains metadata, caches, and query/aggregation state; Lucene segments, inverted indexes, doc values, stored fields, and translogs reside primarily on disk, while the page cache accelerates file reads. Oversized heaps starve the page cache, whereas undersized heaps or heavy aggregations/fielddata cause GC pressure and circuit-breaker trips. Process RSS can also exceed heap due to native memory, thread stacks, and memory mappings.

Large indexes raise segment, merge, update/delete, replica, shard metadata, recovery, and reindex costs. When sizing disk, account for primary data, replicas, translogs, merge/recovery headroom, and growth; when sizing shards, balance shard size against fan-out, allocation, and recovery times. In Spring Data Elasticsearch, bulk batches, entity mapping, response sizes, and `collectList` can create independent heap pressure inside the application. Monitor JVM, process RSS, page cache, disk I/O, segments/merges, indexing pressure, breakers, and thread pools together. Tune mappings, refreshes, bulk concurrency, and shard layouts from measured workloads rather than a single heap chart or storage figure.
