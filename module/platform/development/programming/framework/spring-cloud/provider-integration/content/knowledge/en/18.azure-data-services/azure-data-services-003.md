# Querying, Pagination, and Controlling Request Units

A Cosmos DB query may return only a few items in a single call, even when the container holds thousands of matching items. The service can split results across multiple pages due to execution time limits, response size limits, or currently available Request Units (RU). With Spring Data Cosmos, repositories and `Pageable` provide a familiar querying experience, yet pagination is still backed by Cosmos DB **continuation tokens**. To control cost and latency, the application must understand which partitions a query routes to, how many RUs each page consumes, how the SDK retries, and whether indexes serve the predicates effectively.

This lesson belongs to the **Azure Data Services** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module covers practical integration of Spring Boot with managed services across AWS, Azure, and Google Cloud via their respective Spring Cloud libraries, including identity/permission configuration, storage, messaging, data, secret protection, integration testing, and evaluating differences between cloud providers. This lesson focuses on Azure Cosmos DB for NoSQL: writing queries with Spring Data Cosmos, iterating results via continuation, measuring RUs, and optimizing queries under realistic load.

## 1. Learning Outcomes

After this lesson, you will be able to:

- Distinguish point reads, single-partition queries, and cross-partition queries.
- Write derived queries and custom Cosmos SQL with `@Query`, bound parameters, and partition key predicates.
- Use `CosmosPageRequest`, `Pageable`, and `Slice` to iterate continuation tokens properly.
- Explain why a page may contain fewer items than requested, why page counts vary, or why empty pages can occur at the SDK layer.
- Estimate and measure RUs per request/page; distinguish RU charge from RU/s throughput.
- Read query metrics/index metrics, and tune indexing policies and parallelism.
- Handle 429/throttling, bound concurrency, and design stable cursor APIs.
- Build query tests and workload tests with representative data.

## 2. From Repository Method to Query Execution

With Spring Data Cosmos, a repository method typically executes through `CosmosTemplate` or `ReactiveCosmosTemplate`, down to the Azure Cosmos DB Java SDK. The SDK sends the request to the account; the service plans the query, routes to partitions, executes, and returns data along with request metadata.

~~~mermaid
flowchart LR
    A[Application service] --> R[CosmosRepository]
    R --> T[CosmosTemplate]
    T --> S[Cosmos DB Java SDK]
    S --> Q[Query planner]
    Q --> P1[Partition range A]
    Q --> P2[Partition range B]
    Q --> P3[Partition range C]
    P1 --> M[Merge results / continuation]
    P2 --> M
    P3 --> M
    M --> S
    S --> T
    T --> R
    R --> A
~~~

If the query filters by a partition key value, the SDK can generally route to the corresponding partition. Without an appropriate partition predicate, the query may execute across multiple partitions, with the SDK merging results. For cross-partition `ORDER BY`, results from multiple partitions must be merged into a global order.

A query can be split into multiple executions; each execution returns a portion of results and its own request charge. Thus, "calling a repository method once" does not mean "the service only received one request." One query may trigger multiple round trips due to item counts, page sizes, available RUs, or execution limits.

## 3. Choose the Read Path Before Optimizing Queries

For a known item, prefer a **point read** using container, item ID, and partition key. When multiple items are needed, querying within a single partition key is the next step; queries lacking a partition predicate typically have a broader scope.

| Access Pattern | Required Info | Characteristics |
| --- | --- | --- |
| **Point read** | Item ID + partition key value | Usually lowest RUs and latency for a single known item |
| **Single logical partition query** | Predicate with partition key equality | Avoids fan-out to unrelated partitions |
| **Filtered query without partition key** | Predicates on other fields | May need to probe many partitions; cost depends on indexes and data |
| **Cross-partition query** | Query not scoped to one partition key value | SDK coordinates multiple partitions and merges results |
| **Scan or unindexed query** | Unsuitable query shape/index | Can read far more items than the final result count |

For example, with a container using partition key path `/tenantId`, querying a tenant's orders should include `tenantId = @tenantId`. If a reporting screen needs all paid orders across the entire system, a cross-partition query may be a valid requirement; measure RUs, bound the time range, and consider a dedicated read model for reporting.

## 4. Writing Parameterized Queries in Spring Data Cosmos

### 4.1. Derived Queries

Suppose `OrderDocument` has fields `tenantId`, `status`, and `createdAt`. The repository can declare:

~~~java
import com.azure.spring.data.cosmos.repository.CosmosRepository;
import java.time.Instant;
import java.util.List;

public interface OrderRepository
        extends CosmosRepository<OrderDocument, String> {

    List<OrderDocument> findByTenantIdAndStatus(
        String tenantId, String status);

    List<OrderDocument> findByTenantIdAndCreatedAtAfter(
        String tenantId, Instant from);
}
~~~

Spring Data Cosmos parses method names to generate queries. Property names in the method name must match entity mappings. Derived queries are convenient for simple conditions, but verify the generated query and partition routing; do not assume all Spring Data JPA keywords have identical semantics or are supported in Cosmos.

### 4.2. Custom Queries with `@Query`

When you need control over predicates, projections, or ordering, declare a Cosmos SQL query:

~~~java
import com.azure.spring.data.cosmos.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

public interface OrderRepository
        extends CosmosRepository<OrderDocument, String> {

    @Query("""
        SELECT * FROM c
        WHERE c.tenantId = @tenantId
          AND c.status = @status
        ORDER BY c.createdAt DESC, c.id ASC
        """)
    Slice<OrderDocument> findRecentOrders(
        @Param("tenantId") String tenantId,
        @Param("status") String status,
        Pageable pageable);
}
~~~

This uses the **Cosmos DB for NoSQL** query language, not JPQL. `@Param` binds values into the query; never concatenate user-supplied strings directly into SQL text. The predicate `tenantId = @tenantId` scopes the query by partition key. Multi-property `ORDER BY` clauses may require a corresponding **composite index**; if a required index is missing, the service may return an error requesting the index or the query may consume more resources than expected.

### 4.3. Projections: Reading Only Needed Data

If a list page only displays ID, status, total amount, and creation date, there is no need to load full items with large nested objects. You can use projections/queries supported by your version of Spring Data Cosmos.

Example field-selecting query:

~~~sql
SELECT c.id, c.tenantId, c.status, c.total, c.createdAt
FROM c
WHERE c.tenantId = @tenantId
  AND c.status = @status
ORDER BY c.createdAt DESC, c.id ASC
~~~

The result type must be mapped appropriately (a projection interface/DTO or dedicated model depending on library support). Do not return persistence entities containing internal fields directly from public APIs. Reducing payload size can cut network and document processing overhead, though actual RUs must still be measured against the query plan, indexes, and data.

## 5. Pagination in Cosmos DB Is Based on Continuation Tokens

### 5.1. Page Size Is a Maximum Limit, Not a Guaranteed Count

Cosmos DB may split query results across multiple pages because:

- Not enough RUs remain at execution time to return more items.
- The response hits the size limit.
- A single execution reaches the time limit.
- The query engine chooses to split execution for efficiency.

Page size/`MaxItemCount` only specifies the **maximum number of items** for a single execution. The service may return fewer. The same query and page size can yield a different number of pages across runs—for example, when throughput is throttled or response sizes vary. At the SDK layer, you can occasionally receive an empty page that still carries a continuation token; stop only when no next page exists.

Therefore, do not write logic like:

~~~java
if (page.getContent().size() < requestedPageSize) {
    // Wrong: you cannot conclude there is no more data from item count alone.
}
~~~

Use `Slice.hasNext()`, continuation tokens, or SDK iterator state according to the abstraction in use.

### 5.2. `CosmosPageRequest` Carries the Continuation Token

Spring Data Cosmos supports `Pageable`, `Slice`, and `Sort`. For Cosmos pagination, use `CosmosPageRequest` to pass page size and continuation token:

~~~java
import com.azure.spring.data.cosmos.core.query.CosmosPageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

int pageSize = 50;
Pageable request = new CosmosPageRequest(0, pageSize, null);

Slice<OrderDocument> slice =
    repository.findRecentOrders("tenant-42", "PAID", request);

while (true) {
    process(slice.getContent());

    if (!slice.hasNext()) {
        break;
    }

    Pageable nextRequest = slice.nextPageable();
    slice = repository.findRecentOrders(
        "tenant-42", "PAID", nextRequest);
}
~~~

The first page uses a `null` continuation token. When calling `nextPageable()`, Spring Data Cosmos builds the next request containing the token needed to continue the query. **Use the pageable returned from the previous slice**; do not manually compute `PageRequest.of(pageNumber, pageSize)` and assume Cosmos will jump to that offset.

The example above processes one page at a time and releases data afterward instead of accumulating all results into a large `List`. If returning data from an API, convert each page into a response DTO and retain only the cursor for the next call.

### 5.3. Slice or Page?

Spring Data Cosmos supports both `Page` and `Slice` for pageable queries. Choose based on UI/API needs:

| Type | Best When | Notes |
| --- | --- | --- |
| **Slice<T>** | You only need to know whether a next page exists | Fits cursor/infinite-scroll APIs; does not require total item count for display |
| **Page<T>** | The UI genuinely needs Spring Data's page abstraction metadata | Returned item count per call can still be less than requested size; do not infer total items from page index × size |
| **SDK Iterator/Feed API** | You need low-level control over continuation, request options, or diagnostics | Adapter must manage iteration loop, cancellation, and response lifecycle |

Spring Data Cosmos documentation notes that returned item counts can be smaller than requested sizes depending on available RUs; thus, do not rely on full page sizes to infer completion. If the UI requires an **exact total count**, design a separate count query and budget its RUs/latency; do not assume counts are free or automatically included with list queries.

### 5.4. Continuation Tokens Are Opaque Cursors

A continuation token is a bookmark generated by Cosmos DB/SDK to resume a query. Applications should not parse or modify token contents. With the Java SDK, tokens can be stored and reused to resume queries; service docs note that tokens can be reused when resuming with the same SDK version.

If a public API returns a cursor:

1. Bundle the token with query/filter/sort version and the authenticated tenant scope.
2. Sign or protect the cursor so callers cannot tamper with the token/context.
3. Verify the cursor belongs to the right tenant and the current query.
4. Never let callers supply arbitrary partition keys or query text alongside a token.
5. Handle invalid or incompatible cursors with a clear cursor error instructing the client to restart.

A cursor is not a business ID, not a data access credential, and does not guarantee an immutable snapshot if items change while the client pages through results. If data changes continuously, define list semantics (best-effort, point-in-time, or revision-based) and use stable sorting with a unique tie-breaker when appropriate.

### 5.5. Avoid Deep Offsets Like Relational Pagination

`OFFSET LIMIT` can be useful for certain queries, but deep offset pagination forces the query to process and discard items before the target position. For long lists or cross-partition queries, cost and latency increase. Using continuation tokens to step sequentially through results is usually more appropriate.

Not all query shapes support continuation identically. `GROUP BY` and `DISTINCT` queries have continuation limitations; Cosmos DB permits `DISTINCT` combined with `ORDER BY` per service guidance. For aggregates, grouping, or complex reporting, verify paging behavior for the specific query before designing a public cursor.

## 6. RUs Measure Per-Request Cost, Not Page Size

A **Request Unit (RU)** normalizes processing resources such as CPU, I/O, and memory used by a Cosmos DB operation. RU is the cost of a request; **RU/s** is throughput available/provisioned over time. You cannot infer RUs solely from the number of returned items.

Query cost depends on:

- Source data size and number of items read.
- Size and number of items returned.
- Number of predicates, predicate types, and index usability.
- Index lookups/scans, document loading, and parsing.
- Projections, user-defined functions, and sorting/aggregation.
- Page size, number of pages/round trips, and whether the query fans out across partitions.
- Consistency level, number of regions, and concurrent account/container load.

A query returning 20 items can cost more RUs than another returning 100 items if the first scans more data, uses less selective predicates, or touches multiple partitions. Conversely, a smaller page size does not necessarily reduce total RUs; it can add round trips while keeping total cost similar or higher.

### 6.1. Summing RUs Across Pages

Each query execution returns a request charge for that execution. If a query spans 4 pages, the total RU cost for that traversal is:

[
RU_{total} = RU_1 + RU_2 + RU_3 + RU_4
]

Illustrative example:

| Page | Items Returned | RU Charge |
| --- | ---: | ---: |
| 1 | 50 | 8.2 |
| 2 | 38 | 7.1 |
| 3 | 50 | 8.4 |
| 4 | 12 | 3.5 |
| **Total** | **150** | **27.2 RU** |

These numbers are purely illustrative to show summation. When measuring for real, capture the request charge from SDK response/diagnostics or the appropriate Spring Data integration. Never use `pageSize × fixed RU` as an estimation formula.

### 6.2. What Does Page Size Affect?

| Smaller Page Size | Larger Page Size |
| --- | --- |
| Smaller responses and fewer items held in memory per call | Can reduce round trips when throughput and response limits allow |
| Can increase page count, request count, and total latency from extra round trips | Larger responses, higher memory/buffering, and longer per-page processing time |
| Useful for interactive APIs needing quick partial results | Useful for batch/worker processing when concurrency is bounded |
| Does not guarantee lower total RUs | Does not guarantee a single request or full page sizes |

Choose page size based on target latency, item size, concurrency, memory, and available RUs. Benchmark several page sizes with a representative workload rather than picking the largest value.

## 7. Indexing and Query Shape

By default, Cosmos DB for NoSQL applies an automatic indexing policy across many properties. Indexes help queries filter and sort efficiently, but every indexed property can increase write/update RUs and index storage size.

### 7.1. Predicates That Can Use Indexes

Example query:

~~~sql
SELECT c.id, c.status, c.createdAt
FROM c
WHERE c.tenantId = @tenantId
  AND c.status = @status
  AND c.createdAt >= @from
ORDER BY c.createdAt DESC
~~~

Check:

- Is `tenantId` the partition key and does it have an equality predicate?
- Are filtered/sorted fields covered by an appropriate indexing policy?
- Can the projection be narrowed instead of `SELECT *`?
- Does the query invoke UDFs or expressions that reduce index utilization?
- Is the sort order deterministic and backed by the required indexes?

### 7.2. Composite Indexes for Multi-Field `ORDER BY`

A query with `ORDER BY c.createdAt DESC, c.id ASC` may require a composite index matching the exact property order and sort directions. If the index is missing, Cosmos DB may return an error requiring creation of the composite index. Add the index via container-managing IaC/deployments and wait for index transformation to finish before relying on the new query.

### 7.3. Reducing Write Costs with Intentional Indexing

If a container is write-heavy and has many fields that are never filtered or sorted, consider excluding those paths from the indexing policy. In exchange, queries relying on excluded paths may need to scan or may fail if scans are disallowed. Never drop indexes based on guesswork; build an actual query matrix before modifying policies.

## 8. Reading Query Metrics and Index Metrics

When a query is slow or consumes high RUs, enable metrics to separate time spent in the query engine, document loading, index lookups, and network transfer. Azure Spring Data Cosmos supports configuring **query metrics**, **index metrics**, response diagnostics, degree of parallelism, and buffered item counts via `CosmosConfig` in supported versions.

Example configuration snippet in a class extending `AbstractCosmosConfiguration` when the application **owns Cosmos configuration directly**:

~~~java
import com.azure.spring.data.cosmos.config.CosmosConfig;

@Override
public CosmosConfig cosmosConfig() {
    return CosmosConfig.builder()
        .enableQueryMetrics(true)
        .enableIndexMetrics(true)
        .maxDegreeOfParallelism(-1)
        .maxBufferedItemCount(-1)
        .build();
}
~~~

This snippet configures a custom `AbstractCosmosConfiguration`, not YAML properties automatically applied across all Spring Cloud Azure starter versions. If the starter is auto-configuring clients/templates, use the properties documented for your **exact version** or an intentional custom bean/config; avoid creating two competing client/template sets.

### 8.1. What to Read in Query Metrics

Query execution metrics may include:

| Metric | Interpretation |
| --- | --- |
| **TotalTime** | Total query processing time across measured phases |
| **QueryPreparationTime** | Query compilation/preparation time |
| **IndexLookupTime** | Time spent in the index layer |
| **DocumentLoadTime** | Time spent loading documents |
| **RuntimeExecutionTime / VMExecutionTime** | Time spent executing the query runtime |
| **RetrievedDocumentCount** | Number of documents retrieved for processing |
| **OutputDocumentCount** | Number of documents finally returned |
| **RetrievedDocumentSize / OutputDocumentSize** | Data volume read vs. returned |
| **IndexHitRatio** | Index hit ratio reported by SDK metrics |

If **RetrievedDocumentCount** is much larger than **OutputDocumentCount**, the query may be reading far more items than necessary; inspect predicates, indexes, and partition scope. If network time is high while server query time is low, optimizing the query engine alone won't solve latency; inspect region placement, connectivity, and round-trip counts.

### 8.2. Index Metrics

Index metrics show how current indexes are utilized and which paths might benefit from additional indexes. Enable them during investigation because collecting metrics adds overhead; do not necessarily leave them enabled continuously for all production requests. Use findings to propose index updates, then re-measure both query RUs and write costs after changing the indexing policy.

### 8.3. Response Diagnostics

Spring Data Cosmos supports `ResponseDiagnosticsProcessor` to process diagnostics from responses. You can use this callback to log safe metadata such as operation, duration, request charge, activity ID, and retry context. Never log full items or sensitive data. Logging detailed diagnostics on every single request can substantially inflate log volume and observability costs.

## 9. Parallel Queries and Client Resource Limits

For cross-partition queries, the SDK can execute in parallel across multiple partitions. Spring Data Cosmos allows configuring:

- **maxDegreeOfParallelism:** number of concurrent operations during a query; a negative value such as `-1` lets the SDK decide an appropriate level.
- **maxBufferedItemCount:** maximum items buffered client-side during parallel queries; a negative value lets the SDK decide.
- **responseContinuationTokenLimitInKb:** continuation token size limit in supported configurations; smaller limits may cause extra round trips/RUs.

Increasing parallelism can reduce wall-clock latency for fan-out queries, but does not automatically lower total RUs. It can raise concurrent request counts, memory buffering, and throughput pressure. Setting buffers too large risks heap pressure; excessive parallelism can throttle other workloads.

Choose based on workload:

| Workload | Starting Approach |
| --- | --- |
| Point-read API or single-partition query | Keep default parallelism; optimize the query first |
| Background cross-partition report | Try bounded parallelism and measure throughput/latency |
| Many concurrent user requests | Bound concurrency at the application/service layer; avoid launching large fan-outs per request |
| Large batch export | Page through continuation tokens, stream results to file/sink, bound buffers |

Never call `findAll()` on a large container inside an HTTP request just to export all data. Use a background job, checkpoints, and throughput/concurrency limits.

## 10. 429s and Controlling Request Rate

Cosmos DB returns **429 Too Many Requests** when requests exceed available throughput or a partition/range is overloaded. The Java SDK includes retry/backoff honoring service retry-after for eligible throttling errors; therefore, some 429s may appear in Azure Monitor without being surfaced directly to the application when retries succeed.

A small rate of 429s can indicate efficient throughput utilization if end-to-end latency still meets SLAs and load is evenly distributed. However, a low overall rate does not rule out a hot partition: inspect metrics by partition key range and actual latency.

When encountering 429s:

1. Check total requests, 429 rates, and normalized RU consumption in Azure Monitor.
2. Break down by database, container, operation type, region, and partition key range.
3. Identify which queries/operations consume the most RUs, rather than looking only at aggregate RU/s.
4. Reduce fan-out, optimize predicates/indexes/projections, and bound concurrency.
5. Adjust provisioned throughput/autoscale when the workload genuinely needs more capacity.
6. Check retries across the SDK, application, and message workers to prevent stacked retries.

**Do not retry infinitely in repositories/services** or ignore retry-after. If the SDK already retries, adding a heavy outer retry layer multiplies request volume and extends latency. Permission/configuration errors are never fixed by adding RUs.

## 11. Bringing RUs and Cursors into the Application API

Application services should not expose `CosmosPageRequest` or SDK responses directly to controllers. Create an application-level response model instead:

~~~java
import java.util.List;

public record CursorPage<T>(
    List<T> items,
    String nextCursor
) {}
~~~

At the adapter/persistence boundary:

1. Receive a cursor whose signature and tenant context have been verified by the application.
2. Decode the continuation token and construct a `CosmosPageRequest`.
3. Execute the repository query with matching filters, sort order, and partition scope.
4. If `Slice.hasNext()`, extract `nextPageable()` and the continuation token to build the next cursor.
5. Map entities to DTOs and return `CursorPage` to the application/controller.

Public cursors should be application-managed opaque tokens. You can package the query version, filter/sort hash, tenant scope, and continuation token, then HMAC-sign or encrypt them. Never allow callers to alter the tenant/filter while reusing a continuation token from a prior query. Do not log continuation tokens in public logs.

### 11.1. When Is a Total Item Count Needed?

Some UIs want to show "1–50 of 2,000." Cosmos DB can run count queries, but counting across many partitions can consume significant RUs and latency. If an exact total is not strictly required, use a cursor/`Slice` with a "Load more" button or infinite scroll.

If a total count is required:

- Run a count query with explicit filter/partition scope.
- Measure the count query's RUs separately and include them in the budget.
- Cache or maintain an aggregate/counter if business logic tolerates eventual consistency.
- Avoid re-running the count on every page load if a previously computed value suffices.

## 12. Query and RU Testing Strategy

### 12.1. Unit Tests

Mock repositories to verify that the application service passes the correct tenant, filters, sorting, and page/cursor. Unit tests do not measure real RUs and do not prove queries route properly in Cosmos DB.

### 12.2. Integration Tests with the Emulator

The Cosmos DB Emulator is useful for verifying mapping, query syntax, repository methods, basic continuation flows, and result accuracy. Test datasets should span multiple partition key values, statuses, timestamps, and item sizes.

The emulator is not a production capacity benchmark environment. RUs, throttling, multi-region behavior, account throughput, and partition distribution differ from real cloud behavior; never use emulator RU numbers to finalize production budgets.

### 12.3. Cloud Performance Tests

Run workloads against an Azure test account with:

- A dataset whose item count, item sizes, and skew resemble production.
- Realistic ratios of point reads/queries/writes and concurrency.
- Queries with and without partition predicates.
- Small, medium, and large page sizes with corresponding page counts.
- An indexing policy representative of deployment.
- Target provisioned throughput/autoscale/serverless settings.

Measure:

| Metric | Purpose |
| --- | --- |
| RU/query and RU/page | Per-operation cost |
| Total RUs for a full traversal | Use-case budget |
| p50/p95/p99 latency | User experience |
| Actual page count and items/page | Pagination behavior |
| 429 count/ratio and retry count | Throughput saturation |
| Normalized RUs by partition range | Hot partition detection |
| Retrieved vs. output document count | Over-reading query detection |
| Heap/buffers and concurrent requests | Client resource limits |

After every query or index change, rerun the same workload and compare before/after. A query that lowers latency while spiking RUs or memory may not be a good production trade-off.

## 13. Workflow for Optimizing a Slow Query

~~~mermaid
flowchart TD
    A[Pick slow / high-RU query] --> B[Measure RUs, latency, and page count]
    B --> C{Can a point read replace the query?}
    C -->|Yes| D[Switch to ID + partition key]
    C -->|No| E[Check partition predicate]
    E --> F{Unnecessary fan-out?}
    F -->|Yes| G[Narrow partition scope / read model]
    F -->|No| H[Inspect index metrics and query metrics]
    G --> H
    H --> I[Narrow projection, tune filter/order/index]
    I --> J[Tune page size and concurrency]
    J --> K[Load test and compare RU/p95/429]
    K --> L{Meets budget and SLA?}
    L -->|No| H
    L -->|Yes| M[Record baseline and alerts]
~~~

This investigation order avoids raising throughput before knowing what the query is actually reading. If a query scans many items due to a missing index, adding RUs may make it finish faster while still incurring high costs. Only consider increasing throughput or autoscale after the query itself is optimized and traffic genuinely exceeds provisioned capacity.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Stopping when a page has fewer items than page size | Drops remaining data behind the next continuation | Rely on `Slice.hasNext()` or the continuation token |
| Using `PageRequest.of(pageNumber, size)` to jump deep | No matching continuation; offset semantics differ from relational DBs | Use `CosmosPageRequest` and the pageable returned from the prior page |
| Querying without a partition predicate | Fan-out, higher RUs and latency | Include the partition value in filters when access patterns allow |
| Using `SELECT *` for screens needing a few fields | Larger payloads/document processing | Use appropriate projections |
| Raising page size to lower RUs | Can inflate responses, memory, and latency without lowering total RUs | Measure multiple page sizes and total RUs |
| Raising parallelism without bounds | Increases buffering/concurrency, triggers throttling | Set bounds and measure under load |
| Running a count query on every page load | Extra RUs and latency | Use `Slice`/cursor; count separately only when truly needed |
| Indexing every field unchecked | Higher write RUs and index storage | Index according to query patterns |
| Disabling indexes to save writes without testing queries | Queries scan or fail to execute as expected | Use index metrics and workload tests |
| Retrying 429s across multiple layers | Multiplies request volume and latency | Honor retry-after and enforce a retry budget |
| Using emulator RUs to size production budgets | Inaccurate estimates across different environments | Run cloud performance tests with representative data |

## 15. Practice Exercises

**Exercise 1 — Comparing query shapes.** Container `orders` uses partition key `/tenantId`. Compare expected RUs/latency for a point read by ID + tenant, a query by tenant/status, and a query by status only. Explain why the third query can fan out.

**Exercise 2 — Writing a repository query.** Write a `Slice<OrderDocument>` method with `@Query`, tenant/status filters, and `ORDER BY createdAt DESC, id ASC`. Identify the composite index to verify and how to bind parameters safely.

**Exercise 3 — Iterating continuations.** Write a loop with `CosmosPageRequest` starting with a null token, processing each `Slice`, and calling `nextPageable()`. Explain why you cannot stop just because the current page returned 17 items when the requested size was 50.

**Exercise 4 — Designing a cursor API.** Create a `CursorPage<T>` response and an opaque cursor containing continuation token, tenant, query version, and sort order. Propose how to sign/protect the cursor and validate the tenant on subsequent requests.

**Exercise 5 — RU budget.** A screen requires 5 pages costing 7, 8, 6, 9, and 4 RUs respectively. Calculate the total RUs for one traversal; at 1,000 traversals/hour, estimate RU/hour before adding other operations. Explain why page size cannot serve as a formula for RUs.

**Exercise 6 — Diagnosing a slow query.** A query returns 30 items, yet metrics show `RetrievedDocumentCount` is 12,000, `IndexHitRatio` is low, and p95 climbs. Inspect predicates, indexes, cross-partition scope, projections, and real data; propose the order of fixes.

**Exercise 7 — 429s and parallelism.** A cross-partition reporting query hits 429s when running in parallel. Design an experiment varying `maxDegreeOfParallelism` and `maxBufferedItemCount`; measure total RUs, p95, heap, 429 ratio, and normalized RUs per partition range.

**Exercise 8 — Count and pagination.** A product owner requests exact total order counts on every page. Analyze count query costs, data freshness, and alternatives using `Slice`/cursor or aggregate projections.

## 16. Key Takeaways

- **Queries with a partition predicate** generally reduce fan-out; point reads using ID + partition key are the preferred choice when a single item is known.
- `CosmosPageRequest` uses **continuation tokens**. Always use `nextPageable()` from the previous result; do not treat page numbers/offsets as arbitrary page jumps.
- Page size is the **maximum item count**, not a guaranteed count. The service can return fewer items or split across more pages; continue until no continuation remains.
- **RUs are charged per request/page and query execution**, not strictly by returned item count. Total RUs for a traversal equal the sum of charges across pages.
- Query metrics and index metrics help separate scans, index lookups, document loads, network time, and result serialization. Enable metrics selectively and protect diagnostics.
- Page size, parallelism, and buffering control latency/concurrency/memory; increasing them does not automatically lower total RUs.
- The SDK automatically retries eligible 429s per retry-after; monitor throttling rates, normalized RUs per partition, and end-to-end latency, and avoid stacked retry layers.
- Test queries with the Emulator for correctness; use an Azure test account with representative data/load to measure RUs, quotas, 429s, and p95 before finalizing production settings.

## 17. References

- [Azure Spring Data Cosmos — repository, Pageable, Slice, CosmosPageRequest, and query metrics](https://learn.microsoft.com/en-us/java/api/overview/azure/spring-data-cosmos-readme?view=azure-java-stable)
- [CosmosPageRequest API](https://learn.microsoft.com/en-us/java/api/com.azure.spring.data.cosmos.core.query.cosmospagerequest?view=azure-java-stable)
- [Pagination in Azure Cosmos DB](https://learn.microsoft.com/en-us/cosmos-db/query/pagination)
- [Tuning query performance and reading query metrics](https://learn.microsoft.com/en-us/azure/cosmos-db/query-metrics)
- [Request Units as a throughput and performance currency](https://learn.microsoft.com/en-us/azure/cosmos-db/request-units)
- [Understanding Request Units Consumption](https://learn.microsoft.com/en-us/azure/cosmos-db/understand-request-unit-consumption)
- [Troubleshoot request rate too large (429)](https://learn.microsoft.com/en-us/azure/cosmos-db/troubleshoot-request-rate-too-large)
- [Monitor request unit usage](https://learn.microsoft.com/en-us/azure/cosmos-db/monitor-request-unit-usage)
