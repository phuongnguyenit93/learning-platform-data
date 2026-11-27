# Stream or Flux Results and Closing Cursors

## 1. The problem: an aggregation report with very large results

An e-commerce system needs to export a revenue report by product SKU for a store. If the store has tens of thousands of SKUs, the output of a **$group** pipeline can be huge. Having the repository return the entire report as a **List** forces the application to materialize many objects before starting to process them, increasing memory pressure and delaying export file generation.

Spring Data MongoDB offers two incremental consumption models:

- **Java Stream<T>** in **synchronous** repositories/`MongoTemplate`. A Stream is typically backed by a MongoDB cursor; **you must close the Stream** after use to release resources.
- **Reactor Flux<T>** in **reactive** repositories/`ReactiveMongoTemplate`. A Flux emits items upon subscription, supporting backpressure and cancellation; resource lifecycle is coordinated through the reactive driver and subscription.

Key point: **returning Stream or Flux does not make every aggregation stage capable of processing record-by-record without memory**. Stages such as $group and $sort may need to process large amounts of data on the server before emitting the very first item. Streaming primarily prevents the application from **having to hold the entire output in RAM**, while still requiring proper cursor management.

This lesson **Stream or Flux Results and Closing Cursors** belongs to the **Aggregation repository** chapter of the **SPRING_DATA_MONGODB** module. The module uses Spring Data MongoDB to connect, map documents, and operate via `MongoTemplate` or repositories, while practicing queries, aggregation, indexes, transactions, reactive access, testing, and performance diagnostics.

After this lesson, you will be able to:

1. Choose among **List**, **Stream**, **Slice**, and **Flux** based on requirements.
2. Define repository **@Aggregation** methods returning **Stream<DTO>** or **Flux<DTO>**.
3. Use **try-with-resources** to close synchronous cursors, including during early termination or exceptions.
4. Understand subscription, cancellation, doFinally, and backpressure in reactive pipelines.
5. Use **MongoTemplate.aggregateStream** and **ReactiveMongoTemplate.aggregate** when dynamic pipelines are needed.
6. Bound data scope/volume, pick indexes, and diagnose blocking stages.
7. Test output correctness, tenant isolation, resource closing, and client disconnect scenarios.

## 2. Asking the right question: where is result data held?

Suppose a pipeline aggregates 5 million payment events into 70,000 SKU rows. There are three resource layers to distinguish:

| Component | Role | Risk |
| --- | --- | --- |
| MongoDB Server | Executes $match, $group, $sort; maintains cursor | CPU, temp RAM/disk, index scan, long-lived cursor |
| MongoDB Driver | Reads batches from cursor and decodes data | Connections, buffer memory, round trips |
| Java Application | Maps DTOs, computes/exports further | Heap, GC, backpressure, aborted response |

**List** usually requires reading and holding all results before the caller iterates the List. **Stream/Flux** lets the caller consume incrementally, yet does not change the entire server-side execution strategy in MongoDB.

~~~mermaid
flowchart LR
    A["Collection sale_events"] --> B["MongoDB $match / $group / $sort"]
    B --> C["Server cursor"]
    C --> D["Driver receives batches"]
    D --> E["Stream or Flux"]
    E --> F["Export / Web response / processing"]
~~~

### 2.1. List, Stream, and Flux are not equivalent

| Characteristic | List<T> | Stream<T> | Flux<T> |
| --- | --- | --- | --- |
| Programming model | Synchronous | Synchronous, Java Stream | Reactive, Reactor |
| When items are processed | After fetching all results | As iterator/terminal operation reads | When subscribed with demand |
| Application memory | Grows with result count | Can stay bounded if not collected all at once | Can stay bounded unless downstream collects/buffers unboundedly |
| Must caller close explicitly? | Usually does not keep cursor open after returning List | **Yes**, close Stream/try-with-resources | Resources normally managed by driver/framework on terminal/cancel |
| Can stop early? | Results already fetched before iterating | Yes, yet **still must close** | Yes, via cancel/take/timeout |
| Reactive Streams backpressure | No | No | Yes |
| Automatically provides snapshot? | No | No | No |

**Note:** Flux does not automatically make queries faster. It is a non-blocking data transfer and consumption model when used with the reactive driver—it does not turn an expensive $group stage into a free read.

## 3. Sample domain: payment events by SKU

Suppose collection **sale_events** stores payment events:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenantId: "shop-a",
  status: "PAID",
  sku: "BOOK-101",
  amountMinor: NumberLong("159000"),
  paidAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

Another event:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  tenantId: "shop-a",
  status: "PAID",
  sku: "PEN-002",
  amountMinor: NumberLong("12000"),
  paidAt: ISODate("2025-06-02T09:00:00Z")
}
~~~

In Java:

~~~java
package com.example.sales;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "sale_events")
public record SaleEventDocument(
    @Id ObjectId id,
    String tenantId,
    String status,
    String sku,
    long amountMinor,
    Instant paidAt
) {}
~~~

The entity stores one payment event. **tenantId** is a mandatory authorization predicate in queries; status = PAID filters out unpaid events. **amountMinor** is an integer value in the smallest currency unit. If multiple currencies exist, include currency and group separately by currency; never sum different currencies into a single combined figure.

### 3.1. Aggregation result DTO

~~~java
package com.example.sales;

public record SkuRevenueRow(
    String sku,
    long orderCount,
    long revenueMinor
) {}
~~~

Each row holds one SKU, event count, and total amountMinor. In this lesson **orderCount** is an illustrative metric name; it equals order count only if the business model genuinely has exactly one sale event per order/SKU. If an order can have multiple events for the same SKU, name the metric **eventCount** or group distinct orderIds instead of calling it orderCount.

**Do not map $group results into SaleEventDocument** once the structure has changed. Use a result DTO to avoid misinterpreting missing entity fields and prevent passing partial objects to save.

## 4. Baseline pipeline: grouping revenue by SKU

In mongosh:

~~~javascript
db.sale_events.aggregate([
  {
    $match: {
      tenantId: "shop-a",
      status: "PAID"
    }
  },
  {
    $group: {
      _id: "$sku",
      orderCount: { $sum: 1 },
      revenueMinor: { $sum: "$amountMinor" }
    }
  },
  {
    $project: {
      _id: 0,
      sku: "$_id",
      orderCount: 1,
      revenueMinor: 1
    }
  },
  { $sort: { sku: 1 } }
]);
~~~

Stages:

1. **$match** restricts tenant and status before aggregating.
2. **$group** creates one group per SKU and computes accumulators.
3. **$project** turns group key _id into DTO field sku.
4. **$sort** sets output order for deterministic report exports.

Illustrative output:

~~~javascript
[
  { sku: "BOOK-101", orderCount: 2, revenueMinor: NumberLong("350000") },
  { sku: "PEN-002", orderCount: 1, revenueMinor: NumberLong("12000") }
]
~~~

In real reports, if SKU counts are very large, a List<SkuRevenueRow> can consume heavy application memory. That is why streaming aggregation results is worth considering.

### 4.1. Streaming results differs from streaming source data

**$group** must aggregate events before producing the corresponding groups, potentially using server memory or disk spill depending on configuration. Once groups are formed, the cursor delivers result documents to the driver.

Consequently, even when the client uses Stream/Flux, the pipeline can still have high latency before the first element arrives. When diagnosing, inspect the **aggregation plan, indexes, number of input documents, and blocking stages**, not just the count of emitted elements.

## 5. @Aggregation in a synchronous repository returning Stream

Spring Data MongoDB supports repository methods annotated with **@Aggregation** returning **Stream<DTO>** to read via a cursor.

~~~java
package com.example.sales;

import java.util.stream.Stream;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface SaleEventRepository
        extends MongoRepository<SaleEventDocument, ObjectId> {

    @Aggregation(pipeline = {
        "{ '$match': { 'tenantId': ?0, 'status': 'PAID' } }",
        "{ '$group': { '_id': '$sku', "
            + "'orderCount': { '$sum': 1 }, "
            + "'revenueMinor': { '$sum': '$amountMinor' } } }",
        "{ '$project': { '_id': 0, 'sku': '$_id', "
            + "'orderCount': 1, 'revenueMinor': 1 } }",
        "{ '$sort': { 'sku': 1 } }"
    })
    Stream<SkuRevenueRow> streamPaidRevenueByTenant(
        String tenantId
    );
}
~~~

**?0** is the first method parameter (tenantId). The framework binds the value via Spring Data mechanics rather than concatenating JSON strings from input. The tenant predicate must come from a trusted authentication context, never solely from a client-supplied query parameter.

The method above **does not return a List**. The caller receives a Stream that may hold a MongoDB cursor and must ensure it is closed.

### 5.1. Repository @Aggregation is not an ordinary @Query

**@Query** defines a find/fields query; **@Aggregation** defines pipeline stages. A repository pipeline can return a DTO/projection different from the source entity type.

Do not confuse Stream<SkuRevenueRow> with Stream<SaleEventDocument>: result documents have already been **$group**ed and **$project**ed, so only report fields remain.

### 5.2. Sort and Pageable in @Aggregation

Per Spring Data MongoDB documentation, @Aggregation methods can accept Sort/Pageable to append sort/pagination stages after the pipeline, and can return **Slice**. However, **Page** is not supported as an automatic return type for @Aggregation repository methods.

If the pipeline already ends with **$sort**, verify whether adding a method `Sort` parameter alters the final order. In the example, SKU sorting is declared right inside the pipeline to preserve a fixed ordering contract.

**Do not use Pageable just to pretend the cursor is closed.** Pagination and cursor lifecycle are two separate concerns.

## 6. Closing Stream with try-with-resources

Proper usage:

~~~java
import java.util.function.Consumer;
import java.util.stream.Stream;

public class RevenueExportService {

    private final SaleEventRepository repository;

    public RevenueExportService(SaleEventRepository repository) {
        this.repository = repository;
    }

    public void export(
            String authenticatedTenantId,
            Consumer<SkuRevenueRow> sink) {

        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()) {
            throw new IllegalArgumentException("Tenant required");
        }

        try (Stream<SkuRevenueRow> rows =
                repository.streamPaidRevenueByTenant(
                    authenticatedTenantId)) {

            rows.forEach(sink);
        }
    }
}
~~~

Upon exiting the **try** block:

- The Stream is closed after full iteration.
- The Stream is closed when **sink.accept** throws a RuntimeException.
- The Stream is closed when code **return**s early from inside the block.

For cursor-backed Java Streams, **close() is real resource management**, not merely a ceremonial method.

### 6.1. Place try-with-resources at the point of consumption

Do not do this:

~~~java
public Stream<SkuRevenueRow> loadReport(String tenantId) {
    try (Stream<SkuRevenueRow> rows =
            repository.streamPaidRevenueByTenant(tenantId)) {
        return rows;
    }
}
~~~

Here the Stream is closed before the caller even begins iterating, so the method returns a resource that can no longer be used properly.

A better service design is to **consume the Stream within the same resource-owning scope**, or accept a callback/consumer invoked inside the try block.

### 6.2. Stopping early still requires closing

~~~java
try (Stream<SkuRevenueRow> rows =
        repository.streamPaidRevenueByTenant(tenantId)) {

    rows.limit(10).forEach(this::writePreviewRow);
}
~~~

**limit(10)** here caps how many elements Java consumes, yet **does not guarantee MongoDB only computed 10 groups**. Specifically, $group/$sort may already have processed lots of data. Even when previewing only 10 rows, close the cursor after the terminal operation finishes.

To have the server return only N results, consider **$limit inside the pipeline** with the right stage order for business semantics. $limit after $group limits to **N groups**, not N input events.

### 6.3. Stream.findFirst does not automatically close the cursor for the caller

~~~java
try (Stream<SkuRevenueRow> rows =
        repository.streamPaidRevenueByTenant(tenantId)) {

    var first = rows.findFirst();
}
~~~

**findFirst()** is a terminal operation that can stop before exhausting the cursor. Never rely on a terminal operation always releasing every resource. try-with-resources keeps resource ownership explicit.

## 7. Stream patterns prone to resource leaks

### 7.1. Returning a Stream straight from a controller

~~~java
// Avoid when you do not control who closes the stream.
public Stream<SkuRevenueRow> controllerAction() {
    return repository.streamPaidRevenueByTenant(tenantId);
}
~~~

Returning a Stream to the serialization layer does not guarantee the serializer closes the cursor across every success/cancel/error path. Controllers should use a response streaming mechanism with controlled lifecycle or a service that consumes the Stream and closes it in finally.

### 7.2. Storing a Stream in a singleton field

~~~java
// Avoid: a cursor-backed Stream is not a data cache.
private Stream<SkuRevenueRow> cachedRows;
~~~

A cursor-backed Stream cannot be reused across requests, is unsuitable as a singleton field, and must never act as a cache.

### 7.3. Using parallel() on a cursor-backed Stream

~~~java
// Avoid assuming a cursor can be split safely for effective parallelism.
rows.parallel().forEach(this::writeRow);
~~~

A driver cursor and mapper are not an in-memory immutable dataset already partitioned. Parallel streams do not create independent cursors or replace batch job design. For file-export I/O workloads, ordering and write coordination are separate concerns as well.

### 7.4. Closing only on exception

~~~java
// Wrong: happy path skips close; early return easily misses it.
Stream<SkuRevenueRow> rows =
    repository.streamPaidRevenueByTenant(tenantId);
rows.forEach(this::writeRow);
~~~

Make **try-with-resources** the default choice, even when you expect the entire Stream to be consumed.

## 8. MongoTemplate.aggregateStream for flexible pipelines

When time filters, grouping, or projections are built dynamically, MongoTemplate offers **aggregateStream(...)** returning a Java Stream:

~~~java
import java.util.stream.Stream;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.query.Criteria;

Aggregation aggregation = Aggregation.newAggregation(
    Aggregation.match(
        Criteria.where("tenantId").is(tenantId)
            .and("status").is("PAID")
    ),
    Aggregation.group("sku")
        .count().as("orderCount")
        .sum("amountMinor").as("revenueMinor"),
    Aggregation.project("orderCount", "revenueMinor")
        .and("_id").as("sku")
        .andExclude("_id"),
    Aggregation.sort(Sort.Direction.ASC, "sku")
);

try (Stream<SkuRevenueRow> rows =
        mongoTemplate.aggregateStream(
            aggregation,
            "sale_events",
            SkuRevenueRow.class)) {

    rows.forEach(this::writeRow);
}
~~~

**aggregateStream** uses a MongoDB aggregation cursor instead of returning AggregationResults holding a materialized list. This gives explicit control over the pipeline in a service or custom repository fragment.

### 8.1. stream(Query) and aggregateStream are different

~~~java
try (Stream<SaleEventDocument> events =
        mongoTemplate.stream(
            Query.query(Criteria.where("tenantId").is(tenantId)),
            SaleEventDocument.class)) {

    events.forEach(this::handleEvent);
}
~~~

**MongoTemplate.stream(Query, ...)** streams **find** results; **aggregateStream(Aggregation, ...)** streams **aggregation pipeline** results. Both APIs have cursor resource lifecycles requiring close, yet their query semantics differ.

### 8.2. AggregateStream and explain

The MongoOperations documentation states explicitly that **streaming aggregation does not support explain mode**; enabling explain on an aggregation passed to aggregateStream can throw IllegalArgumentException.

To inspect an execution plan, run **explain on the equivalent pipeline** separately via mongosh/driver or the appropriate explain API. Do not try to enable explain on a production export Stream.

## 9. List vs. Stream: choosing from application goals

| Requirement | Suitable approach |
| --- | --- |
| Report with only 5–20 fixed groups | List, or Page/Slice if applicable |
| Export tens of thousands of groups in order | Stream + try-with-resources |
| Fetch a preview subset with an explicit limit | $limit / Slice with proper sort |
| Need another global metric across all groups | Put the aggregation in MongoDB instead of materializing a List |
| API returning a small bounded list | Simple List, easy to serialize |
| WebFlux needing continuous streaming | Flux via reactive repository/template |
| Synchronous background job writing row by row | Stream with explicit lifecycle management |

**Do not pick Stream just for the buzzword "fast."** For small result sets, List is simpler and avoids forcing callers to manage open cursors.

### 9.1. Stream does not mean results are cached

A standard Java Stream can only be traversed once. To read again, call the repository again or persist the data separately. Do not call two terminal operations on the same Stream as if it were a Collection.

### 9.2. Building a List from a Stream forfeits heap benefits

~~~java
try (Stream<SkuRevenueRow> rows =
        repository.streamPaidRevenueByTenant(tenantId)) {

    List<SkuRevenueRow> all = rows.toList();
}
~~~

This closes the cursor properly yet still holds every result in a List. That is acceptable with tight limits, **unsuitable for exporting massive reports under tight RAM constraints**.

## 10. Reactive repositories returning Flux from @Aggregation

Spring Data MongoDB supports reactive repositories via ReactiveMongoRepository. With @Aggregation, results can be expressed as **Flux<DTO>**:

~~~java
package com.example.sales;

import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;

public interface ReactiveSaleEventRepository
        extends ReactiveMongoRepository<SaleEventDocument, ObjectId> {

    @Aggregation(pipeline = {
        "{ '$match': { 'tenantId': ?0, 'status': 'PAID' } }",
        "{ '$group': { '_id': '$sku', "
            + "'orderCount': { '$sum': 1 }, "
            + "'revenueMinor': { '$sum': '$amountMinor' } } }",
        "{ '$project': { '_id': 0, 'sku': '$_id', "
            + "'orderCount': 1, 'revenueMinor': 1 } }",
        "{ '$sort': { 'sku': 1 } }"
    })
    Flux<SkuRevenueRow> streamPaidRevenueByTenant(
        String tenantId
    );
}
~~~

In a service:

~~~java
import reactor.core.publisher.Flux;

public Flux<SkuRevenueRow> getRows(
        String authenticatedTenantId) {

    return reactiveRepository
        .streamPaidRevenueByTenant(authenticatedTenantId)
        .map(this::normalizeRow);
}
~~~

**normalizeRow** is an illustrative business function transforming each DTO. Avoid performing blocking I/O inside normalizeRow on the event loop.

### 10.1. Flux is a publisher, not an immediately iterating cursor

~~~java
Flux<SkuRevenueRow> result =
    reactiveRepository.streamPaidRevenueByTenant(tenantId);
~~~

Merely constructing a Flux does not mean MongoDB has executed the aggregation yet. Once a subscriber attaches, the driver starts the query and emits items according to demand.

### 10.2. Do not turn an unbounded Flux into a List

~~~java
// Dangerous if group counts are very large.
Mono<List<SkuRevenueRow>> allRows =
    reactiveRepository.streamPaidRevenueByTenant(tenantId)
        .collectList();
~~~

**collectList** accumulates all data in memory. If the group set is tightly bounded in MongoDB, collectList may be reasonable; for large reports it forfeits one of Flux's primary benefits.

## 11. Subscription, cancellation, and reactive cursor lifecycle

With the reactive driver, the cursor is managed along the publisher/subscription lifecycle. When the publisher completes normally, errors out, or the subscriber **cancels**, the driver/framework initiates the corresponding resource release. Applications typically **do not call MongoCursor.close manually** on a Flux produced by Spring Data.

~~~mermaid
flowchart TD
    A["Create Flux from repository"] --> B["Subscriber subscribes"]
    B --> C["Driver opens aggregation cursor"]
    C --> D["Emits batches per demand"]
    D --> E{"Terminal signal?"}
    E -->|Complete| F["Release cursor"]
    E -->|Error| F
    E -->|Cancel| F
~~~

**Note:** cleanup on cancel is a coordinated driver/network process, not a guarantee that the server cursor disappears instantaneously under every network failure. Measure with metrics and integration tests if strict resource cleanup is an operational requirement.

### 11.1. take(n) cancels upstream after N items

~~~java
Flux<SkuRevenueRow> preview =
    reactiveRepository.streamPaidRevenueByTenant(tenantId)
        .take(10);
~~~

Once take receives 10 elements, it cancels upstream, stopping further cursor reads. Yet like Stream.limit, it **does not guarantee MongoDB's $group/$sort only processed 10 events**.

If the goal is limiting group count on the server, add **$limit** into the aggregation after the proper $group/$sort rather than relying solely on take(10) in Java.

### 11.2. timeout and cancel

~~~java
import java.time.Duration;

Flux<SkuRevenueRow> guarded =
    reactiveRepository.streamPaidRevenueByTenant(tenantId)
        .timeout(Duration.ofSeconds(30));
~~~

On timeout, Reactor cancels the upstream subscription and emits a timeout error downstream. That alone does not confirm the MongoDB Server terminated all work within exactly 30 seconds, especially if a server stage is busy or the network drops.

For strict SLAs, consider **maxTimeMS**/query metadata, time-range bounds, and timeouts at both database and application layers.

### 11.3. Do not subscribe yourself and then return the Flux

~~~java
// Wrong: can trigger two subscriptions/queries.
Flux<SkuRevenueRow> rows =
    reactiveRepository.streamPaidRevenueByTenant(tenantId);

rows.subscribe(this::logRow);
return rows;
~~~

When the controller/framework subscribes again, the pipeline can execute a second time. Running two aggregations creates extra load, holds cursors longer, and may see different data if the database mutates between runs.

Always **return one pipeline** and let the caller control subscription.

## 12. doFinally, onCancel, and reactive error handling

Reactor provides hooks to observe lifecycle events:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;

Flux<SkuRevenueRow> rows =
    reactiveRepository.streamPaidRevenueByTenant(tenantId)
        .doOnSubscribe(subscription ->
            log.info("Revenue export subscribed"))
        .doOnNext(row ->
            metrics.incrementRowsEmitted())
        .doOnCancel(() ->
            metrics.incrementExportsCancelled())
        .doOnError(error ->
            log.error("Revenue aggregation failed", error))
        .doFinally(signal ->
            log.info("Revenue stream finished: {}", signal));
~~~

This example uses hypothetical **log** and **metrics** dependencies. **doFinally** runs when the downstream pipeline completes, errors, or cancels, receiving the corresponding SignalType. It is useful for measuring duration, row counts, and cancellations.

**Never call close() manually on a MongoCursor inside doFinally** when the cursor is managed by the reactive driver. Hooks should only record telemetry or release resources **owned by the application itself**.

### 12.1. doOnComplete and doFinally differ

| Hook | When is it invoked? |
| --- | --- |
| doOnComplete | Upstream completes normally |
| doOnError | Upstream emits an error |
| doOnCancel | Downstream cancels subscription |
| doFinally | When pipeline terminates by complete/error/cancel |

Using **doOnComplete** to "always close a writer" can leak the writer when a client disconnects or an exception occurs. For application-managed resources, close in **finally/doFinally**, or use **using/usingWhen** with explicit resource lifecycle management.

### 12.2. Mid-stream errors do not retract already emitted data

A Flux may have emitted 2,000 rows before the database/driver throws an error on the next batch. If the client already wrote those rows to a file or HTTP response, they **do not automatically roll back**.

For critical export workflows, a practical strategy is:

1. Write to a temporary/unpublished export file.
2. Verify the stream **completes** successfully.
3. Publish/rename the output file upon completion.
4. On cancel/error, delete or mark the export as incomplete.

If an HTTP response has already streamed partial chunks, it usually cannot switch cleanly into a standard JSON error body at the end; design a streaming protocol that defines partial output handling and end-of-stream detection.

## 13. Backpressure: helpful, not infinite memory

Reactive Streams allows downstream consumers to request items (*demand*), preventing upstream from flooding a slow consumer without bound. The reactive MongoDB driver coordinates cursor delivery via batches and demand under its own mechanics.

~~~java
Flux<SkuRevenueRow> throttled =
    reactiveRepository.streamPaidRevenueByTenant(tenantId)
        .limitRate(64);
~~~

**limitRate** tunes how many items Reactor requests from upstream; it is not syntax that directly sets **batchSize=64 on the MongoDB cursor**. The driver may prefetch, maintain internal batches, and issue getMore as appropriate.

### 13.1. Operators that can defeat streaming benefits

~~~java
// Can accumulate the entire result set in memory.
Flux<SkuRevenueRow> sortedInJava =
    rows.sort((a, b) -> a.sku().compareTo(b.sku()));
~~~

**Flux.sort(...)** collects items to sort them—it is not a streaming sort on MongoDB. For huge lists, prefer **$sort inside the aggregation** when ordering is part of the data contract.

~~~java
// Similarly: collectList gathers all results.
Mono<List<SkuRevenueRow>> list = rows.collectList();
~~~

**buffer**, **groupBy**, **collectMap**, **reduce**, and similar operators can also retain state in memory. Evaluate every operator against item counts and consumption patterns rather than assuming a chain is bounded just because it starts with Flux.

### 13.2. onBackpressureBuffer does not fix a slow consumer by default

~~~java
// Avoid creating an unbounded buffer just to avoid stalling.
Flux<SkuRevenueRow> unsafe =
    rows.onBackpressureBuffer();
~~~

An unbounded buffer can spike heap usage drastically. If buffering is needed, configure **explicit bounds** and an appropriate overflow policy, and measure latency and resource impact.

### 13.3. Do not confuse batchSize with limit

| Parameter/concept | Effect |
| --- | --- |
| cursor batchSize | Documents exchanged per driver/server batch under cursor protocol |
| $limit in pipeline | Caps output documents at that pipeline stage |
| Pageable / $skip | Skips results in the appropriate order |
| Reactor limitRate | Tunes demand inside the reactive pipeline |
| take(n) | Stops consuming after n items and can cancel upstream |

**Batch size is not the total number of documents a query can return.** A cursor with a small batchSize can still return millions of documents across many getMore calls.

## 14. ReactiveMongoTemplate.aggregate: when dynamic pipelines are needed

Repository @Aggregation is concise for static pipelines. When time windows, tenants, statuses, or grouping units vary dynamically, use **ReactiveMongoTemplate**:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.query.Criteria;
import reactor.core.publisher.Flux;

public Flux<SkuRevenueRow> aggregateReactive(
        ReactiveMongoTemplate template, String tenantId) {

    Aggregation pipeline = Aggregation.newAggregation(
        Aggregation.match(
            Criteria.where("tenantId").is(tenantId)
                .and("status").is("PAID")
        ),
        Aggregation.group("sku")
            .count().as("orderCount")
            .sum("amountMinor").as("revenueMinor"),
        Aggregation.project("orderCount", "revenueMinor")
            .and("_id").as("sku")
            .andExclude("_id"),
        Aggregation.sort(Sort.Direction.ASC, "sku")
    );

    return template.aggregate(
        pipeline, "sale_events", SkuRevenueRow.class
    );
}
~~~

Unlike synchronous **MongoTemplate.aggregate(...)** which returns **AggregationResults**, **ReactiveMongoTemplate.aggregate(...)** returns a Flux of aggregation results. The reactive driver/framework coordinates cursor cleanup with subscription lifecycle.

### 14.1. DTO mapping

Pipeline output has:

~~~javascript
{
  sku: "BOOK-101",
  orderCount: 2,
  revenueMinor: NumberLong("350000")
}
~~~

Record SkuRevenueRow has matching properties, so Spring Data maps the data. With projections renaming fields or accumulators yielding different numeric types, verify DTO constructor/property mapping and actual BSON types in integration tests.

### 14.2. Dynamic queries do not mean concatenating JSON from HTTP input

Never concatenate an arbitrary JSON string to inject a stage:

~~~java
// Avoid: fields/operators arbitrarily controlled by the client.
String pipeline = "{ '$match': " + clientJson + " }";
~~~

Use **Criteria**, **AggregationOperation**, validation, and allowlisted fields/operators. The **tenantId** filter must be enforced by the service, preventing clients from crafting an $or that bypasses authorization filters.

## 15. Stream/Flux in Web APIs

### 15.1. WebFlux with NDJSON

For an API emitting each result row as its own JSON object line, **NDJSON** is an option:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class RevenueStreamController {

    private final ReactiveSaleEventRepository repository;

    public RevenueStreamController(
            ReactiveSaleEventRepository repository) {
        this.repository = repository;
    }

    @GetMapping(
        path = "/reports/revenue/stream",
        produces = MediaType.APPLICATION_NDJSON_VALUE
    )
    public Flux<SkuRevenueRow> exportRevenue() {

        String tenantId = authenticatedTenantId();

        return repository.streamPaidRevenueByTenant(tenantId);
    }

    private String authenticatedTenantId() {
        // Illustrative: obtain from a trusted authorization mechanism.
        throw new UnsupportedOperationException("Wire security context");
    }
}
~~~

`authenticatedTenantId` is the **hook into your real security layer**. Do not invoke this illustrative controller without integrating principal/tenant resolution. In production, resolve tenantId via the reactive security mechanism rather than carelessly reading a synchronous ThreadLocal in WebFlux.

NDJSON lets clients read each JSON line without waiting for an entire JSON array to close. However, incremental flushing and buffering across the HTTP server, proxies, and clients are operational behaviors that must be tested.

### 15.2. Client response cancellation

When a client disconnects, WebFlux triggers subscription cancellation per runtime behavior. The driver/framework then handles cursor cleanup. The application should still:

- Cap query execution time.
- Monitor open stream counts and lifetimes.
- Track cancellations and timeouts.
- Avoid catching errors and continuing unneeded background queries.

**Do not conclude a server cursor was released instantaneously** simply because a browser tab closed; inspect metrics and real behavior under network failures.

### 15.3. Synchronous streaming over HTTP

In Spring MVC, an export can use StreamingResponseBody or an appropriate response streaming mechanism. Put **try-with-resources around the entire export loop** inside the callback that actually writes the response, rather than opening a Stream in the controller and handing it off to another thread.

Never pass a MongoDB cursor-backed Java Stream across boundaries without a clear owner and closing point.

## 16. Cursors: from firstBatch to getMore and close

An aggregation does not necessarily return all results in a single MongoDB response. MongoDB can open a **cursor** holding state to deliver batches incrementally.

~~~mermaid
sequenceDiagram
    participant C as Application
    participant D as MongoDB Driver
    participant M as MongoDB Server
    C->>D: Run @Aggregation / aggregateStream
    D->>M: aggregate with cursor
    M-->>D: firstBatch and cursorId (if more remain)
    D-->>C: Result elements
    C->>D: Continue consuming
    D->>M: getMore as needed
    M-->>D: next batch
    C->>D: close Stream or cancel Flux
    D->>M: Release/killCursors flow when appropriate
~~~

**Server cursor** and **Java Stream/Flux publisher** live at different layers. The Stream is merely Java's handle to read results, while the cursor holds driver/server resources. That is why try-with-resources must close the Stream even when Java loops stop early.

### 16.1. Cursors can exhaust naturally

Once a query is consumed to completion, server and driver typically clean up the cursor through normal lifecycle completion. In synchronous code, however, **`close()` remains the caller's responsibility** because iteration can stop early or fail mid-loop.

### 16.2. Long-lived cursors

An opened Stream that is never iterated or never closed can hold connections and server cursors/resources longer than needed. Under load, leaked cursors can cause:

- Increased connection pressure and server cursor count.
- Longer resource retention per request.
- Difficulty diagnosing why a job never finishes.
- Risk of cursor timeout/invalidation while idle.

Never rely on garbage collection or server idle timeouts for timely resource cleanup. **Resource ownership must be explicit in code.**

## 17. $group and $sort can still be blocking stages

Streaming avoids holding the entire **output** in Java, yet MongoDB Server may still process vast amounts of data before emitting results.

### 17.1. $group

~~~javascript
{
  $group: {
    _id: "$sku",
    revenueMinor: { $sum: "$amountMinor" }
  }
}
~~~

$group usually has to accumulate state per key during processing. If group counts or input volumes are huge, memory usage rises. Depending on server version and settings, aggregation may need disk for eligible stages.

### 17.2. $sort

~~~javascript
{ $sort: { revenueMinor: -1 } }
~~~

When sorting on a field **created after $group**, an index on source collection fields does not automatically make sorting free. MongoDB may have to sort all aggregated groups.

### 17.3. $match and indexes

A candidate index for this workload:

~~~javascript
db.sale_events.createIndex({
  tenantId: 1,
  status: 1,
  paidAt: 1
});
~~~

For reports filtering by tenant/status and a **paidAt range**, this index helps $match reduce events processed. If the pipeline has no paidAt filter, re-evaluate index design against actual query patterns.

**Never move $limit before $group to cut load without changing requirements**, because that turns total revenue across all events into revenue over only a tiny subset.

## 18. @Meta and resource limits for aggregations

Spring Data MongoDB supports **@Meta** on repository aggregations to set options such as allowDiskUse, maxExecutionTimeMs, and comment.

~~~java
import java.util.stream.Stream;
import org.springframework.data.mongodb.repository.Aggregation;
import org.springframework.data.mongodb.repository.Meta;

public interface SaleEventReportRepository
        extends MongoRepository<SaleEventDocument, ObjectId> {

    @Meta(allowDiskUse = "true", maxExecutionTimeMs = 30000)
    @Aggregation(pipeline = {
        "{ '$match': { 'tenantId': ?0, 'status': 'PAID' } }",
        "{ '$group': { '_id': '$sku', "
            + "'orderCount': { '$sum': 1 }, "
            + "'revenueMinor': { '$sum': '$amountMinor' } } }",
        "{ '$project': { '_id': 0, 'sku': '$_id', "
            + "'orderCount': 1, 'revenueMinor': 1 } }",
        "{ '$sort': { 'sku': 1 } }"
    })
    Stream<SkuRevenueRow> streamByTenantWithOptions(String tenantId);
}
~~~

**allowDiskUse does not guarantee the query spills to disk**, nor does it guarantee less time or fewer resources. It permits eligible stages to use disk when needed under MongoDB Server/version semantics.

**maxExecutionTimeMs** sets an execution time limit at the database layer per MongoDB semantics; it does not replace network/HTTP timeouts, does not guarantee instant termination on client cancel for every task, and does not automatically close Java-owned resources.

### 18.1. Why does @Meta not replace close?

Even with a 30-second limit, synchronous Streams **still require try-with-resources**:

~~~java
try (Stream<SkuRevenueRow> stream =
        repository.streamByTenantWithOptions(tenantId)) {
    stream.forEach(this::handleRow);
}
~~~

Server options and client-side closing are two separate layers of protection.

## 19. Transactions, sessions, and Stream lifetime

Streaming queries may tie into Spring-managed sessions/transactions. **Never return an unconsumed Stream outside a transaction boundary expecting the cursor/session to remain valid.**

Risky example:

~~~java
// Avoid returning a Stream out of a transactional method.
@Transactional(readOnly = true)
public Stream<SkuRevenueRow> openInTransaction(String tenantId) {
    return repository.streamPaidRevenueByTenant(tenantId);
}
~~~

When the method returns, the transaction interceptor may end the transaction before the caller iterates the Stream, causing a lifecycle mismatch.

### 19.1. Consume inside the owning scope

~~~java
@Transactional(readOnly = true)
public void exportWithinTransaction(
        String tenantId,
        Consumer<SkuRevenueRow> sink) {

    try (Stream<SkuRevenueRow> rows =
            repository.streamPaidRevenueByTenant(tenantId)) {
        rows.forEach(sink);
    }
}
~~~

This snippet only illustrates **keeping the Stream lifecycle inside the method**. Real MongoDB transactions require `MongoTransactionManager` and a supported deployment topology; `@Transactional` alone does not guarantee all operations participate in a transaction.

**Never open a transaction just to be able to call aggregateStream.** A long transaction holding a cursor open across a huge export consumes resources and faces transaction time limits. Only use transactions when business consistency/atomicity requires it and costs have been evaluated.

### 19.2. Report consistency

If the collection receives inserts/updates/deletes while the aggregation runs, results depend on read concern, snapshots, and execution mechanics. **Stream/Flux does not create a consistent snapshot just by changing return types.**

When accounting reports require frozen figures, consider:

- Appropriately scoped snapshots/transactions where supported.
- Data versions or cutoff timestamps.
- Materializing the report at a reconciliation checkpoint.
- Adjustment rules for late-arriving events and refunds.

Business accuracy must be designed independently of cursor consumption style.

## 20. When to batch instead of holding a very long cursor?

A massive export running for hours may face network drops, retries, and checkpointing needs. One long Stream is simple yet hard to resume accurately mid-way after a disconnect.

### 20.1. Batching strategy

1. Choose a `paidAt` window, tenant, and deterministic sort key.
2. Process a bounded set of IDs or data slice.
3. Persist a checkpoint for the completed batch.
4. On failure, reconcile and resume from the checkpoint.
5. Add idempotency when exporting to external systems.

For raw data with suitable monotonically increasing/unique keys, **keyset pagination** can beat deep skips. For aggregations already grouped by SKU, checkpointing by **group key** requires careful design; never assume partial output can resume seamlessly without skewed totals if source events continue changing.

### 20.2. When to pre-materialize

If a report must match a fixed data version, generate a materialized report/batch result keyed by **reportId** and timestamp. Then Stream/Flux consumes the finalized report rows. This separates **computing a consistent result** from **incrementally streaming results to clients**.

### 20.3. Do not confuse MongoDB cursors with Change Streams

The **aggregation cursor** in this lesson returns results of a query pipeline. **MongoDB Change Streams** use a special pipeline to watch continuous changes with different lifecycle and semantics. Do not treat an ordinary aggregation cursor as an endless event stream.

## 21. Direct streaming does not replace bounding data

Some APIs need a 10-row preview, others export 50,000 rows. Separate those contracts explicitly:

~~~text
GET /reports/revenue/preview?limit=10
GET /reports/revenue/exports/{jobId}
GET /reports/revenue/stream
~~~

For previews, place **$sort/$limit in the pipeline** at the right spot. For exports, enforce tenant scope, time windows, authorization, duration/resource budgets, and handling when clients cancel mid-way.

### 21.1. Where are limit semantics applied?

| Pipeline | Meaning |
| --- | --- |
| $match → $limit(10) → $group | Aggregates from the first 10 events; usually wrong for full revenue reports |
| $match → $group → $sort → $limit(10) | Gets the top 10 groups by sort order |
| $match → $group → $limit(10) → $sort | Sorts only 10 previously chosen groups; can miss true top 10 |
| $match → $group → $sort → Stream | Streams all groups incrementally after server executes pipeline |

**Stage order is part of business correctness**, not merely an optimization detail.

### 21.2. Top-N and sorting on repositories

If you add Sort/Pageable to an @Aggregation signature, extra stages may be appended after the declared pipeline. For top-N, verify the final $sort/$limit position and field mapping against the **return DTO**; do not assume sorting by source entity properties once $group changes the structure.

## 22. Integration testing Stream from @Aggregation

Unit tests that merely mock the repository do not prove the framework uses a MongoDB cursor or that the pipeline groups accurately. Write integration tests with a dedicated MongoDB test instance, such as Testcontainers or a test MongoDB environment.

### 22.1. Test data and expected output

Suppose:

| Tenant | Status | SKU | amountMinor |
| --- | --- | --- | --- |
| test-a | PAID | BOOK-101 | 10000 |
| test-a | PAID | BOOK-101 | 25000 |
| test-a | PAID | PEN-002 | 5000 |
| test-a | PENDING | BOOK-101 | 90000 |
| test-b | PAID | BOOK-101 | 70000 |

Expected for tenant=test-a:

~~~javascript
[
  { sku: "BOOK-101", orderCount: 2, revenueMinor: 35000 },
  { sku: "PEN-002", orderCount: 1, revenueMinor: 5000 }
]
~~~

### 22.2. JUnit example

~~~java
package com.example.sales;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.stream.Stream;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class SaleEventAggregationStreamTest {

    @Autowired SaleEventRepository repository;
    @Autowired MongoTemplate template;

    private SaleEventDocument event(
            String tenant, String status, String sku, long amount) {
        return new SaleEventDocument(
            new ObjectId(),
            tenant,
            status,
            sku,
            amount,
            Instant.parse("2025-06-01T09:00:00Z")
        );
    }

    @Test
    void streamsGroupedRevenueAndClosesStream() {
        String tenant = "TEST-" + UUID.randomUUID();
        String otherTenant = "OTHER-" + UUID.randomUUID();

        List<SaleEventDocument> inserted = repository.saveAll(List.of(
            event(tenant, "PAID", "BOOK-101", 10_000),
            event(tenant, "PAID", "BOOK-101", 25_000),
            event(tenant, "PAID", "PEN-002", 5_000),
            event(tenant, "PENDING", "BOOK-101", 90_000),
            event(otherTenant, "PAID", "BOOK-101", 70_000)
        ));

        try {
            List<SkuRevenueRow> rows;

            try (Stream<SkuRevenueRow> stream =
                    repository.streamPaidRevenueByTenant(tenant)) {
                rows = stream.toList();
            }

            assertThat(rows).hasSize(2);
            assertThat(rows.get(0).sku()).isEqualTo("BOOK-101");
            assertThat(rows.get(0).orderCount()).isEqualTo(2L);
            assertThat(rows.get(0).revenueMinor()).isEqualTo(35_000L);
            assertThat(rows.get(1).sku()).isEqualTo("PEN-002");
            assertThat(rows.get(1).revenueMinor()).isEqualTo(5_000L);
        } finally {
            repository.deleteAllById(
                inserted.stream().map(SaleEventDocument::id).toList()
            );
        }
    }
}
~~~

This test **reads and closes the Stream properly** and verifies filtering, grouping, sorting, and DTO mapping. However, using try-with-resources **does not by itself prove the server cursor actually received killCursors** on early termination. To test cursor closing in detail, instrument MongoDB command monitoring/driver metrics or check cursor lifecycle in your test environment.

**Never run tests against a production collection.** To avoid colliding with other data, fixtures use a unique tenant ID and delete only the IDs created by the test.

### 22.3. Testing that exceptions still close the Stream

With a mock stream resource having a close hook, you can unit-test that a service using try-with-resources invokes close when the Consumer throws. A corresponding integration test can deliberately throw an exception on the first item in the loop and inspect cursor/command metrics as the driver closes.

Do not merely assert a RuntimeException was thrown and conclude **every network resource was released immediately** without instrumentation.

## 23. Testing Flux and cancellation

For reactive repositories, use **StepVerifier** to verify data:

~~~java
import reactor.test.StepVerifier;

StepVerifier.create(
    reactiveRepository.streamPaidRevenueByTenant(tenantId)
        .map(SkuRevenueRow::sku)
)
.expectNext("BOOK-101")
.expectNext("PEN-002")
.verifyComplete();
~~~

This snippet assumes **reactiveRepository** is injected and test data matches section 22. The test suite requires the **reactor-test** dependency.

### 23.1. Early cancellation

~~~java
StepVerifier.create(
    reactiveRepository.streamPaidRevenueByTenant(tenantId)
        .take(1)
)
.expectNextCount(1)
.verifyComplete();
~~~

**take(1)** completes downstream after one item and cancels upstream while more data remains. This tests flow at the Reactor level, yet **is not enough to prove the server cursor closed**. Where resource control is critical, add metrics/command monitoring, track open cursor counts, and simulate network faults.

### 23.2. Error and cancel signals

A test can add:

~~~java
import java.util.concurrent.atomic.AtomicReference;
import reactor.core.publisher.SignalType;

AtomicReference<SignalType> terminal =
    new AtomicReference<>();

StepVerifier.create(
    reactiveRepository.streamPaidRevenueByTenant(tenantId)
        .doFinally(terminal::set)
        .take(1)
)
.expectNextCount(1)
.verifyComplete();
~~~

**Do not assert on the exact instant doFinally fires if the test has an asynchronous race.** When proving signals, use proper test synchronization or place hooks at a controlled scheduling point.

### 23.3. Multi-tenant testing

Seed at least one event with the same SKU belonging to another tenant and verify it contributes neither to counts nor to revenue. Tenant isolation is a higher-priority security requirement than small streaming performance tweaks.

## 24. Troubleshooting and cursor leaks

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| RAM spikes during export | Using List/collectList or unbounded buffer | Stream/Flux and process row-by-row; cap output |
| Long-lived cursors | Stream not closed, overly slow consumer | try-with-resources, timeouts, metrics |
| Controller returns Stream then errors later | Resource outlives owning scope | Consume inside callback with clear lifecycle |
| Cursor remains after findFirst/limit(10) | Terminal op does not replace closing responsibility | try-with-resources |
| No reactive results emitted | Missing subscription | Return Flux to WebFlux/appropriate caller |
| Aggregation runs twice | Subscribed twice or retry/repeat | Ensure one subscription per request |
| Client disconnects yet server keeps working | Async cancel/cleanup or blocking server stage | Monitor metrics, maxTimeMS, filter early |
| Very slow first row | $group/$sort computing over massive data | Inspect pipeline and indexes |
| Stream already closed before iteration | Stream returned out of try or transaction | Consume within owning scope |
| Error at row 1000 leaves partial file | Streaming does not roll back output | Write temp file, publish on complete |
| Reactive stream grows heap | collectList/sort/buffer/groupBy retain items | Audit every operator, enforce bounds |
| Slow query despite trailing $limit | $group still processes large input | Early $match and proper indexes |
| Cursor timeout/invalid | Stream held too long, session/transaction ended | Shorten cursor hold time, batch work |
| Wrong DTO mapping | $project field names/numeric types mismatch | Inspect raw BSON and constructors |
| Wrong sort after @Aggregation | Sort parameter appended after pipeline | Inspect actual stage order |
| Aggregation lacks Page support | @Aggregation repository doesn't auto-return Page | Use Slice/build separate count |
| Error on aggregateStream + explain | Streaming aggregation rejects explain mode | Run explain separately |
| Export leaks other tenant's data | Tenant missing from $match | Enforce tenant auth + cross-tenant tests |

### 24.1. Investigation workflow

1. Identify whether **List**, **Stream**, or **Flux** is used.
2. Verify the pipeline filters tenant, status, and time window properly.
3. Check which stages can block emissions: $group, $sort, $lookup.
4. Read execution plans/metrics to spot COLLSCAN or disk spill.
5. Measure actual result counts and open cursor counts.
6. For Stream, verify caller uses try-with-resources on **every code path**.
7. For Flux, audit subscriptions, cancellation, timeouts, and memory-retaining operators.
8. Check that transactions/sessions do not end before data consumption finishes.
9. Reproduce with tests for early stop, mid-stream error, and client disconnect.
10. Only then optimize batch sizes, indexes, pipeline stages, and export mechanics.

## 25. Practice exercises

### Exercise 1: Stream or List?

A report has 200,000 SKU rows and the service needs to write each row sequentially to a file without keeping all of them in RAM. Which type should you consider?

**Answer:** **Stream<SkuRevenueRow>** with try-with-resources in a synchronous stack, or **Flux<SkuRevenueRow>** in a reactive stack. Both still require appropriate pipelines and indexes.

### Exercise 2: closing the cursor

Write Java code to iterate a repository Stream and close it on all paths:

~~~java
try (Stream<SkuRevenueRow> rows =
        repository.streamPaidRevenueByTenant(tenantId)) {
    rows.forEach(this::writeRow);
}
~~~

**Explanation:** try-with-resources closes the Stream even if writeRow throws an exception.

### Exercise 3: bug when returning a Stream

Is a method returning a Stream from inside try-with-resources safe?

**Answer:** No. The Stream is closed upon exiting the try block, before the caller consumes it. Either transfer ownership with an explicit contract or consume within the same scope.

### Exercise 4: findFirst

A method calls **stream.findFirst()** and returns the result. Does the Stream still need to be closed?

**Answer:** Yes. A terminal operation can stop before the cursor finishes and does not replace resource closing responsibility.

### Exercise 5: Flux and subscribe

Create a Flux from a reactive repository without subscribing. Has MongoDB definitely executed the aggregation yet?

**Answer:** No. Publishers are lazy and typically only execute upon subscription.

### Exercise 6: take(10)

Why does **Flux.take(10)** not mean MongoDB only processed 10 sale events?

**Answer:** $group/$sort may need to process many inputs to form results; take(10) only limits items consumed downstream and cancels upstream afterward.

### Exercise 7: collectList

How can a Flux from MongoDB cause heap overflow even though the driver supports backpressure?

**Answer:** Downstream calls collectList, sort, unbounded buffer, or retains every row; backpressure cannot help if the application deliberately accumulates all data.

### Exercise 8: mid-export error

After writing 1,000 rows to a file, the driver throws an error. Does that file automatically roll back to empty?

**Answer:** No. Write to a temporary file and publish only after onComplete or a successful read loop; mark output incomplete on error.

### Exercise 9: cursor and transaction

You return a Stream from a @Transactional method and let the caller iterate it later. What is the risk?

**Answer:** The transaction/session may have already ended before the Stream is consumed, causing errors or lifecycle mismatches. Iterate and close within the owning scope.

### Exercise 10: @Aggregation and Page

Is a repository @Aggregation returning Page<DTO> to auto-count totals a supported contract?

**Answer:** No. Spring Data MongoDB documentation does not support Page return types for @Aggregation repositories; use Slice with Pageable or design a separate count when total is needed.

### Exercise 11: where does $limit go?

To get the top 10 SKUs by revenue, should $limit go before or after $group/$sort?

**Answer:** $match → $group → $sort by revenueMinor DESC → $limit(10). Placing limit before grouping only sums a small slice of events.

### Exercise 12: Mono or Flux?

A pipeline returns multiple SKUs using ReactiveMongoRepository. Should it return Mono<SkuRevenueRow> or Flux<SkuRevenueRow>?

**Answer:** Flux<SkuRevenueRow>. Mono fits at most one value, such as a single total revenue figure.

### Exercise 13: batch size

If a cursor has batchSize=100, does MongoDB return at most 100 total results for the entire query?

**Answer:** No. Batch size controls chunked delivery; total results can be much larger and arrive across multiple batches/getMore calls.

### Exercise 14: onComplete callback

Is using only doOnComplete to close a file writer safe if the client cancels?

**Answer:** No. doOnComplete does not run on error or cancel. Use explicit resource management such as usingWhen or finally/doFinally.

### Exercise 15: performance

A Flux emits its first item after 45 seconds even though the client is fast. What are possible causes?

**Answer:** $group/$sort, missing index on $match, scanning many events, or server disk spill. Inspect explain/profiler and optimize the pipeline rather than just tweaking Reactor backpressure.

## 26. Pre-deployment checklist

- **Output size:** is the report large enough to need Stream/Flux?
- **API style:** does the synchronous repository use Stream and the reactive one use Flux?
- **Cursor owner:** is try-with-resources present for every synchronous Stream?
- **Scope:** are Streams never returned closed or past transaction/session boundaries?
- **Cancellation:** are client cancellations/timeouts observed?
- **Errors:** is there a plan for partially written data/files/HTTP responses?
- **Backpressure:** do any operators collect/buffer/sort all items in Java?
- **Batches:** is the distinction among batchSize, $limit, and limitRate clear?
- **Filters:** does $match include tenant and mandatory authorization predicates?
- **Sorting:** are group ordering and $sort/$limit positions business-accurate?
- **Indexes:** have keys/docs examined and query plans been measured?
- **Blocking stages:** has the cost of $group/$sort/$lookup been evaluated?
- **Disk/time:** are allowDiskUse and maxTimeMS appropriate for the workload?
- **Responses:** is there a streaming format and a protocol to detect partial output?
- **Transactions:** are long transactions avoided solely for exports?
- **Consistency:** has snapshot/cutoff design been addressed if required by the report?
- **Testing:** have sufficient data, multi-tenancy, errors, cancellations, and closes been tested?
- **Metrics:** are duration, emitted rows, cancellations, and cursor lifetimes measured?

## 27. Summary

1. **Repository @Aggregation can return Stream or Flux**, not always List.
2. **Synchronous Stream<T> typically wraps a MongoDB cursor**. Callers must close it, best done with try-with-resources.
3. **Reactive Flux<T> executes on subscription/demand**; complete/error/cancel coordinate cursor release via driver/framework.
4. **Closing Streams is still mandatory on findFirst, limit, exceptions, or early returns**, not only when fully iterated.
5. **Reactive backpressure does not mean every operator streams**; collectList/sort/buffer can accumulate huge state.
6. **$group/$sort can still maintain heavy server state**, so returning Flux does not make heavy pipelines free.
7. **MongoTemplate.aggregateStream** serves synchronous aggregations and **ReactiveMongoTemplate.aggregate** serves reactive pipelines.
8. **$match, indexes, properly placed $limit, maxTimeMS, and resource observability** cut load more than return type choice alone.
9. **@Aggregation does not auto-return Page with totals**, requiring Slice or custom count logic.
10. **Transaction/session scope and cursor scope must align**; never let a Stream outlive its context.
11. **Streaming output can end mid-way on error/cancel**, requiring publish/rollback handling in file exports or application protocols.
12. **Testing against a real MongoDB and monitoring cursor metrics** verifies both correctness and resource lifecycles.

Mastering **Stream or Flux results and closing cursors** enables **SPRING_DATA_MONGODB** services to build scalable aggregation reports, avoid holding entire result sets in memory, manage synchronous resources cleanly, and leverage reactive cancellation and backpressure properly.

### References

- [Spring Data MongoDB — MongoDB-specific Query Methods / Aggregation Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html) — @Aggregation, return types Stream, Slice, @Meta, and Page limitations.
- [Spring Data — Defining Query Methods / Streaming Query Results](https://docs.spring.io/spring-data/mongodb/reference/repositories/query-methods-details.html) — Stream closing rules, List vs. Stream/Flux.
- [Spring Data MongoDB — MongoOperations API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoOperations.html) — aggregateStream, lifecycle, and limitations with aggregation explain.
- [Spring Data MongoDB — Aggregation Framework Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html) — Aggregation, group, project, sort, and aggregation execution.
