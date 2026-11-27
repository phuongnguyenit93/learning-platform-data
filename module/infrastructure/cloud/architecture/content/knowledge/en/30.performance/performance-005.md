# Optimizing Communication: Reducing Call Counts, Batching, and Compression

In cloud architectures, performance does not depend solely on CPU, memory, or database speed. A request can spend most of its time waiting over the network: calling multiple services sequentially, making excessive database round trips, sending tiny individual messages, or transferring repetitive payloads. As network latency grows, call frequency and payload size amplify their impact on latency, throughput, cost, and load resilience.

**Communication optimization** means designing how components exchange data to cut overhead while preserving business semantics. Three common techniques are reducing call counts (request consolidation and chatty-call reduction), batching (grouping multiple operations into a single communication), and compression (shrinking payloads in transit or at rest). They can substantially improve performance, yet they introduce trade-offs: batching adds wait latency while collecting items, larger payloads increase memory usage, compression consumes CPU, and failure visibility shifts.

This lesson belongs to the **Performance** chapter of the **Cloud Architecture** track. The track guides designing cloud applications from business requirements down to networking, compute, data, and deployment models—balancing reliability, security, scalability, cost, and operations. Communication optimizations must therefore rest on end-to-end measurements and realistic workloads, while keeping timeouts, ordering, idempotency, security, and failure handling sound.

After this lesson, you will be able to:

- Identify chatty communication, round-trip overhead, payload bloat, and fan-out.
- Measure latency, throughput, bytes transferred, and request amplification.
- Reduce call counts via well-scoped APIs, projections, pagination, and caching.
- Choose batching strategies based on throughput, latency budgets, payload limits, and failure semantics.
- Design batch flushes using size/time/idle triggers, backpressure, and retries.
- Select compression algorithms and levels based on CPU, payloads, network characteristics, and client capabilities.
- Avoid compressing already-compressed or tiny payloads.
- Apply batching and compression safely across HTTP, RPC, databases, and message brokers.
- Test correctness, tail latency, resource consumption, and cost.

## 1. Why Does Call Count Matter?

A single network call typically involves multiple steps: DNS/connection setup if not reused, TLS, network transit, queueing, serialization/deserialization, server processing, and response transfer. Even if each call takes only a few milliseconds, dozens of sequential round trips can make a request noticeably slow.

For example, a dashboard page needs to display 40 bookings. If the application calls separate APIs per booking to fetch customer, asset, and payment summaries, a single request can trigger dozens or hundreds of downstream calls. This pattern is **chatty communication**.

Conversely, an aggregated API can return all required screen data in a few requests, or a service can expose a pre-built projection.

### 1.1. Latency Model

With N sequential calls, total latency is approximately:

\[
T_{total} \approx \sum_{i=1}^{N}(T_{network,i}+T_{queue,i}+T_{server,i})
\]

If each call averages 20 ms and there are 25 sequential calls, the calls alone consume around 500 ms before counting local processing. This is a simplified example; tail latency and dependency contention can make the outcome worse.

With N parallel calls, latency can approximate the slowest call rather than the sum, yet the call volume still creates fan-out load and raises the probability of hitting at least one slow or failing dependency. Parallelism does not eliminate overhead; it shifts pressure onto concurrency, connections, and downstream capacity.

### 1.2. Request Amplification

A single client HTTP request can trigger many internal calls. The amplification ratio is:

\[
A = \frac{\text{Total downstream calls}}{\text{Inbound requests}}
\]

If each inbound request triggers an average of 18 downstream calls, amplification is 18. When traffic grows from 100 to 1,000 requests/second, downstream systems can receive 18,000 calls/second. Track amplification per endpoint and operation.

~~~mermaid
flowchart TD
    U["One client request"] --> API["API service"]
    API --> A["Customer lookup"]
    API --> B["Asset lookup"]
    API --> C["Payment lookup"]
    API --> D["Policy lookup"]
    API --> E["History lookup"]
    A --> DB1[("Customer DB")]
    B --> DB2[("Asset DB")]
    C --> DB3[("Payment DB")]
    D --> DB4[("Policy DB")]
    E --> DB5[("History DB")]
~~~

## 2. Measure Before Optimizing

Do not assume every network call is a problem. A secondary call may be negligible if it runs in parallel, enjoys a high cache hit rate, and sits off the critical path. Collect a baseline before making changes.

| Metric | Meaning |
| --- | --- |
| Calls per inbound request | Amplification/fan-out level |
| Round trips per transaction | Number of sequential exchanges |
| p50/p95/p99 latency | Latency distribution, especially the tail |
| Payload bytes/request | Transfer size per call |
| Total bytes/sec | Bandwidth consumed |
| Serialization CPU/time | Encode/decode cost |
| Compression ratio | Ratio of compressed bytes to raw bytes |
| Batch size and wait time | Batch item count and collection wait duration |
| Batch flush frequency | How often batches flush |
| Retry/duplicate rate | Re-transmitted communication overhead |
| Connection reuse/pool saturation | Connection utilization efficiency |
| Queue age/backlog | Impact of batching or consumer capacity |

### 2.1. Tracking Tail Latency

Averages can hide slow requests. If p99 climbs sharply, the cause may be a slow dependency, a batch waiting to flush, queueing, or oversized payloads triggering garbage collection. Measure latency by endpoint, dependency, payload size, batch size, and client type to establish correlations.

### 2.2. Critical Path Analysis

Use distributed traces to spot sequential calls, parallel branches, retries, and serialization spans. Identify which calls are required for an immediate response, which can run asynchronously, and which data can be served from a projection or read model.

Effective optimization usually begins by removing unnecessary calls from the critical path rather than just raising timeouts or adding threads.

## 3. Reducing Call Counts: Designing APIs Around Use Cases

One way to cut round trips is designing endpoints that return sufficient data for a specific use case instead of forcing clients to stitch together multiple small APIs.

For example, a booking summary view might need booking details, asset label, and payment status. A composite endpoint can return a projection prepared by the domain service:

~~~http
GET /v1/bookings/booking-1005/summary
Accept: application/json
~~~

Example response:

~~~json
{
  "bookingId": "booking-1005",
  "status": "CONFIRMED",
  "asset": {
    "assetId": "asset-42",
    "displayName": "Camera kit"
  },
  "payment": {
    "status": "AUTHORIZED",
    "currency": "VND"
  }
}
~~~

Projections can live inside the service owning the use case, an API composition layer, or a dedicated read model. Avoid turning a composite endpoint into a distributed monolith that calls dozens of services sequentially.

### 3.1. API Composition and BFF

A Backend for Frontend (BFF) can aggregate data tailored for web or mobile clients. It reduces client requests, but does not automatically reduce downstream calls if the BFF still fans out to every API as before. Inspect the call graph and consider projections, caching, or adjusting data ownership.

### 3.2. GraphQL, REST Aggregation, and RPC

GraphQL lets clients pick required fields and avoid over-fetching, yet poorly designed resolvers can trigger N+1 queries. REST aggregation and RPC can likewise create chatty patterns if endpoints are too fine-grained. The transport technology alone does not solve round trips; you must design query plans, batching resolvers, and depth/complexity limits.

## 4. Eliminating N+1 Calls

A common anti-pattern queries a list of entities and then issues another query per entity to fetch related data.

~~~text
bookings = queryBookings(tenantId)

for booking in bookings:
    customer = getCustomer(booking.customerId)
    asset = getAsset(booking.assetId)
    append(summary(booking, customer, asset))
~~~

With 100 bookings, this code issues 1 list query plus 200 lookups. A better approach collects unique IDs and runs bulk queries:

~~~text
bookings = queryBookings(tenantId)
customerIds = unique(bookings.customerId)
assetIds = unique(bookings.assetId)

customers = getCustomersByIds(customerIds)
assets = getAssetsByIds(assetIds)

return joinInMemory(bookings, customers, assets)
~~~

If the data belongs to the same database/domain, an appropriate join can be even more efficient. If it spans different services, bulk endpoints or read projections cut network round trips.

### 4.1. Bounding Bulk Lookup Sizes

Bulk endpoints must cap ID counts, payload bytes, and execution times. Never let clients send millions of IDs in a single request; use pagination, async exports, or batch jobs for large volumes.

## 5. Pagination, Field Selection, and Payload Minimization

Reducing call counts does not mean dumping all data into one giant response. Oversized payloads increase network transfer, memory usage, serialization, parsing time, and timeout risk.

- Pagination/cursors for long lists.
- Field selection/projection returning only needed fields.
- Summaries instead of full objects when appropriate.
- Avoid repeating identical metadata on every record.
- Use stable enums/codes instead of long descriptive strings when the contract permits.
- Expand only required nested relations.
- Cap payload size and nesting depth.
- Support conditional requests/ETags when beneficial.

### 5.1. Offset vs. Cursor Pagination

Offset pagination fits small pages and slowly changing datasets, though large offsets can be expensive to query and results shift when new rows arrive. Cursor/keyset pagination based on an ordering key provides more stable traversal when the sort key is chosen carefully.

Both have trade-offs. Cursors should be opaque tokens validated so a client cannot reuse another tenant's or resource's cursor.

## 6. Caching to Avoid Repeated Calls

Caching eliminates repeated calls for slowly changing data or data with acceptable freshness policies. Cache keys must include tenant/resource scope; TTLs and invalidation must reflect business semantics.

Caching fits reference data, non-sensitive configuration, catalogs, or summaries. Exercise caution when caching access permissions, payment state, inventory availability, or data requiring strong consistency.

Options include in-process caches, distributed caches, HTTP caches/CDNs, and materialized views/read models. Each introduces its own dependencies and freshness policies. A high cache hit ratio can mask underlying load issues during cold caches or mass invalidation.

## 7. What Is Batching?

**Batching** groups multiple small operations into a larger communication unit to amortize fixed per-operation overhead.

For instance, instead of sending 100 separate messages, a producer groups 100 messages into one batch publish. Instead of inserting one row per database request, a client uses a multi-row insert or prepared statement batch.

Total cost can be approximated as:

\[
C_{total} \approx N \cdot C_{fixed} + C_{payload}
\]

Batching reduces how often fixed overhead is paid, but can raise payload size, wait time, and memory usage. If a batch is too large, a single retry may reprocess lots of data and exceed transport limits.

| Layer | Examples |
| --- | --- |
| HTTP API | Bulk create/update, batch lookup |
| gRPC | Client/server streaming or batch RPC |
| Database | Multi-row insert, prepared statement batch |
| Message broker | Batch produce/fetch/ack per capabilities |
| Object storage | Packing small files, multipart uploads |
| Analytics | Micro-batch events and bulk loads |
| External provider | Batch APIs aligned with rate limits/contracts |

Not every protocol supports batch requests with identical semantics. In streaming, client libraries or brokers may group records and flush automatically; in bulk APIs, a batch is a business operation with an explicit response/partial-failure contract.

## 8. Choosing Batch Sizes

Batch sizing must balance throughput, latency, memory, payload limits, and failure scope.

- Too small: little overhead reduction.
- Too large: long collection wait, higher memory use, and timeout risk.
- Oversized batch payload: exceeds API/broker limits or causes fragmentation.
- Variable-size records: item count alone does not reflect byte size.
- Long-running batches: one bad record can delay the entire batch if the contract lacks per-item error isolation.

Bound **max items**, **max bytes**, and **max wait time** together. Adaptive batching driven by traffic and downstream capacity can be used, provided upper bounds and guardrails are enforced.

### 8.1. Flushing by Size and Time

A batch producer typically flushes when reaching an item count, total byte threshold, max wait timeout, shutdown signal, or a priority message marked for immediate send by policy.

~~~mermaid
flowchart TD
    A["New item arrives"] --> B["Add to pending batch"]
    B --> C{"Item/byte limit reached?"}
    C -- "Yes" --> F["Flush batch"]
    C -- "No" --> D{"Max wait elapsed?"}
    D -- "Yes" --> F
    D -- "No" --> B
    F --> G["Send and record result"]
    G --> H["Start next batch"]
~~~

Misconfigured timers can cause starvation when traffic trickles in; ensure batches always flush when the time window expires. Under low traffic, time-based flushing bounds latency.

## 9. Batching and Latency

Batching generally boosts throughput at the cost of per-item latency, since early items wait for later ones.

\[
T_{item} = T_{wait\_in\_batch} + T_{send} + T_{process}
\]

At low traffic, max wait time dominates total latency. At high traffic, batches fill quickly so wait time drops. The same batch configuration can yield very different latencies between peak and off-peak hours.

If a synchronous API needs immediate responses, do not wait to fill a batch. Batching fits asynchronous write paths, bulk operations, or client SDKs with explicit latency budgets.

### 9.1. Latency SLOs and Throughput Objectives

Select batch sizes by benchmarking across multiple traffic profiles: idle, normal, peak, and burst. Measure p95/p99 per-item latency, batch completion latency, throughput, memory, and retries. Never pick a configuration purely for peak throughput if it breaches latency SLOs.

## 10. Partial Failures in Batches

A batch contains multiple records, yet not all items always succeed or fail together.

- **Atomic batch:** the entire batch succeeds or rolls back if the platform supports transactions.
- **Partial success:** each item receives its own outcome.
- **Best-effort:** valid items are processed and failed items are recorded.
- **At-least-once:** items may be redelivered/reprocessed; consumers must be idempotent.
- **At-most-once:** items may be lost if failures strike at unsafe moments.
- **Exactly-once effect:** requires explicit transaction/idempotency mechanisms across both storage and side effects; never assume it solely from an API/broker name.

Example bulk update returning per-item results:

~~~json
{
  "batchId": "batch-20261118-01",
  "results": [
    {"itemId": "booking-1", "status": "UPDATED"},
    {"itemId": "booking-2", "status": "REJECTED", "code": "VERSION_CONFLICT"},
    {"itemId": "booking-3", "status": "UPDATED"}
  ]
}
~~~

Results must give enough detail for clients to retry only failed items without repeating side effects on succeeded items.

## 11. Idempotency and Retries for Batches

When a batch response is lost, the client may not know whether the server processed all, part, or none of the batch. Retrying the entire batch blindly can create duplicates.

You need idempotency keys per batch or per item; stable message/item IDs across redelivery; unique constraints or deduplication stores; batch processing state and per-item results; retrying only incomplete items; backoff, jitter, and retry budgets; dead-letter/failed-item queues; and reconciliation when outcomes remain unknown.

A single batch-level idempotency key works if the server stores the full batch result. If a batch is split into independent units, per-item keys allow more precise retries. Validation errors, authorization failures, or schema mismatches typically do not succeed on retry; classify transient vs. permanent errors.

## 12. Backpressure and Batch Queues

Batch producers and consumers must bound pending buffers. When producers outpace consumers, queues or memory can grow without limit.

Implement bounded queues/buffers, max in-flight batches, consumer concurrency aligned with downstream capacity, pause/resume or admission control, queue age/backlog alerts, spill-to-disk or durable brokers where suitable, and per-tenant fairness/quotas.

~~~mermaid
flowchart LR
    P["Producers"] --> B["Bounded pending buffer"]
    B -->|Batch flush| Q[("Durable broker")]
    Q --> C["Consumers with concurrency cap"]
    C --> D["Downstream service"]
    D -. "Capacity feedback" .-> C
    C -. "Backpressure" .-> B
~~~

If consumers are slow, enlarging batch size does not necessarily fix the bottleneck; it can increase batch processing duration and memory footprint. First check downstream throughput, queue age, and saturation.

## 13. Message Broker Batching

Brokers can batch at the producer, broker, or consumer fetch level. Understand specific semantics: does batch publishing preserve ordering within a partition/key; at what durability level does the broker ack; do failures affect the whole batch or individual records; where does compression happen (producer/broker/consumer); do retries preserve identity; what are max message/batch byte limits; do consumers ack per message or by offset; and do rebalances trigger redelivery.

Batching by partition/key can preserve ordering within a scope, though multiple partitions lack global ordering by default. Choose partition keys aligned with business consistency boundaries.

## 14. Database Batching

Database batching cuts round trips and parse/execute overhead. Prepared statement batches or multi-row inserts work well for bulk writes.

Pay attention to transaction boundaries/atomicity; parameter/packet limits; lock duration and contention; index maintenance and WAL/log volume; constraint/trigger behavior; batch size/commit frequency; retries on deadlock/serialization conflicts; and driver/database partial-result semantics.

Overly large batches can hold locks too long, generate massive transaction logs, or cause costly rollbacks. Chunking with checkpoints/idempotency usually suits large backfills.

### 14.1. Bulk Reads

Replace multiple point lookups with `WHERE id IN (...)` queries, joins, or table-valued inputs if supported by the database. Cap list sizes and inspect query plans; huge lists can trigger poor plans or exceed parameter limits.

## 15. Data Compression: Goals and Trade-Offs

Compression shrinks bytes transferred or stored, lowering network costs and improving latency when networking is the bottleneck. However, compression/decompression consumes CPU and memory and can add overhead to tiny payloads.

\[
T_{compressed} \approx T_{compress} + \frac{S_{compressed}}{B} + T_{decompress}
\]

Where S is byte size and B is network throughput. Compared to raw transfer time S_raw/B, compression pays off when saved transfer time outweighs encode/decode costs and other overhead.

### 15.1. When Does Compression Pay Off?

Large, repetitive text/JSON/XML payloads; bandwidth-constrained links or significant egress costs; responses slowed by transfer bytes; batches with many records sharing schemas/metadata; text-based log/analytics files.

### 15.2. When Does It Not Pay Off?

Small payloads dominated by round-trip latency; JPEG/PNG/MP4/ZIP or already-compressed payloads; saturated CPUs; constrained clients/mobile devices struggling with decompression; previously encrypted payloads; or contexts where compression introduces side-channel risks by mixing secrets with attacker-controlled data.

Never enable compression globally without measuring payload sizes, CPU, latency, and security context.

## 16. Choosing Compression Algorithms and Levels

| Algorithm | General characteristics | Common use cases |
| --- | --- | --- |
| gzip/DEFLATE | Broad compatibility; balanced CPU and ratio depending on level | HTTP content encoding, text payloads |
| Brotli | Typically strong ratio for text/web; encode cost depends on level | Static web assets, text responses when clients support it |
| Zstandard (zstd) | Fast with wide trade-off levels | Internal services, file/batch/data pipelines where supported |
| LZ4 | Speed-focused, typically lower compression ratio | High-throughput internal paths, storage/log pipelines |
| Snappy | Fast compression, common in data/big data ecosystems | Data files or compatible streaming/broker ecosystems |

Never choose an algorithm solely from a summary table. Benchmark with real payloads and target library versions. Verify support across clients/browsers, proxies, brokers, database drivers, and formats.

Higher compression levels raise CPU and encode latency with diminishing byte savings. For real-time responses, low or medium levels often outperform maximum compression.

## 17. HTTP Compression and Content Negotiation

HTTP lets clients advertise supported algorithms via `Accept-Encoding`, and servers should pick only an encoding the client supports. Responses declare the compressed representation via `Content-Encoding`.

~~~http
GET /v1/bookings?pageSize=100 HTTP/1.1
Host: api.example.com
Accept: application/json
Accept-Encoding: gzip, br
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Encoding: gzip
Vary: Accept-Encoding
~~~

`Vary: Accept-Encoding` lets caches distinguish representations by encoding. Proxies/CDNs must handle headers and cache keys correctly. Never compress already-compressed responses or sensitive payloads in contexts vulnerable to compression side-channels.

### 17.1. Thresholds and Content Types

Compress only when responses exceed a byte threshold and match eligible content types. JSON/text benefits far more than already-compressed JPEGs. Thresholds must be benchmarked because compressing a 1 KB response can spend CPU while saving very few bytes.

### 17.2. Compression Bombs and Size Limits

When accepting compressed payloads from clients or brokers, bound both compressed size and decompressed size. A tiny payload can expand into huge data. Enforce max expansion ratios, decompressed bytes, nesting/decode depth, and decode timeouts; validate before allocating large memory buffers.

## 18. gRPC, RPC, and Serialization

gRPC supports message-level compression depending on runtime/client/server configuration. Compression must be compatible across peers and monitored to prevent CPU saturation.

Ways to optimize RPC communication:

- Reuse channels/HTTP2 connections where appropriate.
- Avoid creating a new channel per request.
- Propagate deadlines and cancellation.
- Choose unary vs. streaming based on semantics.
- Batch multiple items when suitable endpoints/contracts exist.
- Transmit only required fields.
- Compress large payloads when beneficial.
- Cap message sizes and concurrent streams.
- Monitor serialization/deserialization time.

Binary serialization like Protocol Buffers can reduce payload sizes compared to JSON for certain schemas/workloads, though it is not automatically faster in every case; evaluate CPU, compatibility, debuggability, and client support. Serialization format and compression are two separate layers.

## 19. Combining Batching with Compression

Batching often improves compression opportunities because records share repetitive structure. Compressing items individually misses cross-item repetition; compressing a serialized batch can improve ratios.

Conversely, batch compression increases producer/consumer CPU, causes one corrupt item to break decoding of the whole batch, requires buffering the full batch, increases decompression memory, hinders random access, and raises latency while waiting to fill the batch.

Pick compression boundaries matching broker/protocol capabilities. For large streams, chunked compression avoids holding entire payloads in memory. Include version and algorithm metadata for reader compatibility.

## 20. Network Connection Reuse and Multiplexing

Reducing connection setup counts also trims handshakes and setup overhead:

- HTTP keep-alive/connection reuse.
- HTTP/2 multiplexing multiple streams over one connection.
- HTTP/3/QUIC has different transport properties and can reduce certain transport-layer head-of-line blocking effects.
- gRPC channel reuse.
- Database connection pooling.
- Broker connection/session reuse.

Connection pooling requires clear bounds and lifecycles. Pools that are too large exhaust database connections; pools that are too small cause queueing. Multiplexing cuts connection counts, but does not remove concurrency/flow-control limits or server capacity constraints.

## 21. Batching Can Alter Communication Semantics

A batch is not merely items placed in an array. It can alter send timing, item ordering, atomicity, failure scope, retry behavior, transaction boundaries, observability granularity, and cross-tenant fairness.

For instance, packing all tenants into one large batch allows a noisy tenant to delay others. Use per-tenant batch queues or fairness policies when isolation is required.

For payments, bookings, or inventory, never combine operations if executing them as a single shared transaction alters ordering or business invariants.

## 22. Security and Privacy When Optimizing Payloads

Efficient communication must preserve confidentiality, integrity, and authorization.

- Send only fields needed downstream.
- Never put secrets in headers/message payloads unnecessarily.
- Encrypt in transit via TLS/mTLS according to the trust model.
- Compress only after evaluating content classification and side-channel risks.
- Enforce payload size limits before and after decompression.
- Validate schemas and versions.
- Tenant-scope every bulk request and batch item.
- Never let a batch response leak another tenant's records.
- Redact PII in traces and logs.
- Use checksums/signatures when integrity across storage/transfer boundaries is required.

A bulk API must authorize every resource/tenant inside the batch; never authenticate the caller once and skip per-item ownership checks.

## 23. End-to-End Example: Booking Summary and Event Ingestion

A dashboard page fetches 50 bookings, where each booking needs customer name, asset summary, and payment status. The initial version called one booking list API followed by three APIs per booking, generating up to 151 requests.

### 23.1. Reducing Call Counts

Redesign the summary endpoint with cursor pagination and required fields. The booking service exposes a read projection pre-aggregated from domain-owned data or invokes bulk endpoints by ID lists. Client round trips drop to a few bounded calls.

### 23.2. Event Batching

A producer continuously records booking events. Rather than publishing each event as a separate RPC, it batches up to 100 events or 256 KB and flushes every 20 ms. These thresholds are initial benchmark assumptions, not universal optimal values.

Consumers process batches under concurrency limits, record per-message outcomes, and ack according to broker semantics. Permanently failing messages are quarantined; transient failures retry with backoff and idempotency.

### 23.3. Compression

If event JSON carries repetitive fields, the producer serializes the batch and enables broker-supported compression. Benchmarks compare gzip/zstd/LZ4 across CPU, ratio, p99 delivery latency, and consumer memory. For small or pre-compressed payloads, compression is skipped.

~~~mermaid
flowchart LR
    API["Dashboard client"] --> SUM["Booking summary API"]
    SUM --> PROJ["Read projection / bulk lookup"]
    PROJ --> DATA[("Curated read data")]
    EVT["Booking events"] --> BATCH["Bounded batcher"]
    BATCH --> COMP["Serialize + compress"]
    COMP --> MQ[("Message broker")]
    MQ --> CON["Consumers"]
    CON --> STORE[("Downstream stores")]
~~~

### 23.4. Measurement Plan

| Metric | Baseline | Evaluation target |
| --- | --- | --- |
| Client requests per dashboard | Many requests | Marked reduction |
| Downstream calls per summary | High | Reduced call amplification |
| p95/p99 dashboard latency | Measured baseline | No regression; improves toward SLO |
| Batch item latency | N/A | Within latency budget |
| Broker throughput | Baseline | Increases without backlog growth |
| Producer/consumer CPU | Baseline | Remains within capacity |
| Bytes/event | Baseline | Decreases when payloads fit |
| Duplicate/failed item rate | Baseline | Does not rise; safely replayable |

## 24. Common Design Mistakes

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| Making many small sequential API calls | Compounding round trips, high latency | Projections, bulk endpoints, and use-case APIs |
| Turning sequential fan-out into unbounded parallel fan-out | Downstream overload, tail latency spikes | Concurrency caps and deadlines |
| Dumping every field into composite responses | Large payloads and high memory use | Projections/field selection |
| Omitting pagination on bulk reads | Oversized queries and responses | Cursors, max items/bytes |
| Batching without a max wait | First item waits indefinitely | Flush by time and size |
| Capping only item count without byte limits | Batches exceed payload/memory limits | Max item count and byte size |
| Misusing atomic batches | One bad item fails the entire batch | Partial results or smaller batches |
| Blindly retrying whole batches | Duplicate side effects | Idempotency and per-item status |
| Unbounded buffers | Uncontrolled memory growth | Backpressure/admission control |
| Increasing batch size when consumers lag | Slower batches and higher memory | Measure bottlenecks, scale/cap to capacity |
| Compressing every payload | Higher CPU with no gain on tiny payloads | Size thresholds and content-type policies |
| Compressing already-compressed payloads | Wastes CPU for minimal byte savings | Skip compressed media/formats |
| Maximum compression levels everywhere | High encode latency/CPU | Benchmark levels per use case |
| Omitting post-decompression size limits | Compression bombs/DoS | Compressed and decompressed limits |
| Failing to reuse connections | Repeated handshake and setup overhead | Keep-alive, channel/pool reuse |
| Mixing tenants in batches without fairness | Noisy neighbors and tenant starvation | Per-tenant quotas/queues |
| Using request IDs as metric labels | Cardinality explosion | Keep IDs in logs/traces |
| Not measuring tail latency | Good average hides bad p99 | Track p95/p99 and trace critical paths |

## 25. Communication Optimization Workflow

1. **Select user journey:** pinpoint endpoints/workflows with latency, throughput, or cost issues.
2. **Measure baseline:** calls per request, round trips, p95/p99, bytes, CPU, queue age, and retries.
3. **Map dependency graph:** synchronous calls, fan-out, N+1 patterns, and payload transfers.
4. **Eliminate unnecessary calls:** projections, use-case endpoints, bulk lookups, or caches.
5. **Bound payloads:** field selection, pagination, cursors, and size limits.
6. **Design batching:** atomicity, item/byte limits, flush timeouts, and failure semantics.
7. **Design backpressure:** bounded buffers, concurrency, fairness, and admission policies.
8. **Choose compression:** algorithms, levels, thresholds, client compatibility, and security.
9. **Optimize connections:** reuse, pooling, multiplexing, and deadlines/cancellation.
10. **Test correctness:** ordering, idempotency, partial failures, retries, and tenant isolation.
11. **Benchmark:** low/normal/peak/burst traffic; measure latency, throughput, CPU, memory, bytes, and cost.
12. **Roll out:** canary, health gates, rollback, and monitor consumers/downstream.
13. **Review:** confirm SLOs, costs, and live behavior once traffic stabilizes.

## 26. Well-Architected Review

| Perspective | Design questions |
| --- | --- |
| **Reliability** | Do batches have bounded buffers, retry/idempotency, and partial-failure handling? Are compression/decoding bounded? Can retries run without duplicates? |
| **Security** | Is bulk authorization enforced per resource? Do payloads carry PII/secrets? Does compression pose side-channel risks? Are decompression limits enforced? |
| **Performance Efficiency** | Are round trips, p95/p99, bytes, and CPU measured? Do batch sizes/flush intervals fit the latency budget? Are connections reused? |
| **Cost Optimization** | Are egress/requests reduced? Does compression CPU justify saved bytes? Does batching lower operation costs while increasing memory/idle wait? |
| **Operational Excellence** | Are there dashboards for call amplification, batch wait/size, compression ratios, backlogs, retries, and policy owners? |

### Acceptance Checklist

- [ ] Baselines exist for calls/request, round trips, payload bytes, p95/p99, and resource usage.
- [ ] Critical path is identified; unnecessary calls are removed or moved asynchronous.
- [ ] API aggregation does not create a distributed monolith or unbounded fan-out.
- [ ] Bulk lookups enforce max items/bytes, pagination, and per-item authorization.
- [ ] N+1 patterns are audited across API resolvers, services, and databases.
- [ ] Batching enforces max item counts, max bytes, and max wait times.
- [ ] Atomicity/partial success/ordering/retry semantics are explicitly documented.
- [ ] Idempotency prevents duplicates across timeouts, retries, and redeliveries.
- [ ] Bounded buffers, concurrency quotas, and backpressure are tested.
- [ ] Compression is enabled only for eligible payloads/clients with benchmarked gains.
- [ ] Compressed/decompressed size limits and decode timeouts are enforced.
- [ ] Connections/channels/pools are reused with explicit capacity limits.
- [ ] Tenant fairness and isolation are preserved in batch/bulk APIs.
- [ ] Structured logs/traces capture batch ID/item ID and operations without leaking secrets.
- [ ] Metrics avoid high cardinality from unique IDs.
- [ ] Canary/rollback plans and load tests cover low, peak, and burst traffic.

## 27. Practice Exercise

An equipment rental application has a dashboard endpoint returning the 30 most recent bookings. The client calls the bookings API, then calls customer, asset, and payment APIs individually for each booking. A background worker publishes each event as a separate broker request; the JSON messages repeat extensive metadata. During high traffic, p99 latency spikes and egress costs exceed projections. Consumers occasionally reprocess messages after timeouts.

Design the following:

1. What will you measure to separate latency caused by round trips, server processing, queueing, and payload transfer?
2. Which summary/projection or bulk APIs will replace the N+1 API calls?
3. How do pagination and field selection prevent oversized payloads?
4. How will you choose batch size, max bytes, and flush interval for the event producer?
5. How will you handle partial failures and per-item retries without creating duplicates?
6. Which compression algorithms/levels should be benchmarked, and when should compression be skipped?
7. How will you cap decompressed sizes and defend against malicious payloads?
8. How will you design bounded buffers and backpressure when consumers slow down?
9. How will you preserve ordering, tenant authorization, and fairness within batches?
10. Which before/after metrics prove the optimizations improved p99, throughput, and cost without harming correctness?

A well-grounded solution uses summary/read projections to cut client round trips, bounded bulk lookups for auxiliary data, producer batching by item/byte/time thresholds, idempotent consumers with per-item status, and compression only for payloads with strong ratios. Results must be verified via benchmarks tracking p95/p99, bytes/event, CPU, queue age, duplicate rates, and egress costs.

**Core Takeaway:** Reducing call counts curbs round-trip and call-amplification overhead; batching amortizes fixed costs across items while requiring bounds on size, wait time, and failure scope; compression cuts bytes at the expense of CPU and requires size guardrails. Optimize only when end-to-end gains are measurable and ordering, idempotency, security, tenant isolation, and SLOs remain intact.
