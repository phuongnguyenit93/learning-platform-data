# ReactiveSearchHits and Reading Metadata Alongside the Result Stream

In reactive Spring Data Elasticsearch, a search query can return more than a list of entities. The response also contains query-wide metadata such as total hits, max score, aggregations, execution duration, or Point in Time information if supported by the API and version. Each hit also has its own metadata such as document ID, index, score, sort values, highlights, and inner hits.

When using the imperative API, the application typically receives a SearchHits object and reads the hit list and metadata via synchronous getters. In the reactive stack, results and metadata are represented via Reactive Streams: Flux for the sequence of hits and Mono for a single asynchronous value. ReactiveSearchHits is the abstraction that holds both parts within a single response.

It is important to distinguish:

- **Response-level metadata:** information describing the entire search request, such as total hits, max score, and aggregations.
- **Hit-level metadata:** information about a specific document, such as ID, score, sort values, and highlights.
- **Entity content:** the Java object mapped from the document's source.

If you convert ReactiveSearchHits into Flux<Product> too early, the application may lose metadata needed for pagination, relevance display, or result analysis. When metadata is needed alongside hits, keep ReactiveSearchHits in the reactive chain and combine Mono/Flux properly.

## 1. A Search Response Is More Than a List of Entities

A search request can return:

    {
      "hits": {
        "total": {
          "value": 125,
          "relation": "eq"
        },
        "max_score": 4.82,
        "hits": [
          {
            "_index": "products",
            "_id": "p-100",
            "_score": 4.82,
            "_source": {
              "name": "Mechanical Keyboard"
            },
            "sort": [
              4.82,
              "p-100"
            ]
          }
        ]
      }
    }

The application may need:

- Content to display the product.
- ID to build detail links or process further.
- Score to explain relevance ranking.
- Sort values to continue with search_after.
- Total hits to display result counts or pagination.
- Aggregations to display analytics/facets.
- Highlights to mark matching keywords.
- Inner hits to show matching nested objects.

If you only extract hit.getContent(), most hit-level metadata is discarded. If you only use Flux<Product>, response-level metadata such as total hits and aggregations is also absent from the types received downstream.

## 2. What Is ReactiveSearchHits?

ReactiveSearchHits is Spring Data Elasticsearch's abstraction for representing search results in the reactive API. It holds the stream of SearchHit elements together with the metadata returned from the search response.

In modern versions, usage typically looks like:

    Mono<ReactiveSearchHits<Product>> result =
        operations.search(query, Product.class);

    result.flatMapMany(ReactiveSearchHits::getSearchHits);

Each component plays a distinct role:

- Mono<ReactiveSearchHits<Product>> represents the asynchronously produced search response.
- ReactiveSearchHits<Product> holds response metadata and the hit stream.
- Flux<SearchHit<Product>> emits each hit according to subscriber demand.
- SearchHit<Product> holds the content and metadata of a single hit.

Method names, return types, and available metadata can vary across Spring Data Elasticsearch versions. Check the API of your resolved dependency. In particular, do not confuse ReactiveSearchHits with imperative SearchHits or with Flux<Product>.

## 3. How Does ReactiveSearchHits Differ from an Entity Flux?

Different result types expose different levels of information:

| Result type | Primary payload | Accessible metadata |
|---|---|---|
| Flux<Product> | Entity content per document | Does not preserve full hit/response metadata |
| Flux<SearchHit<Product>> | Content and metadata per hit | ID, score, sort values, highlights, and API-exposed hit metadata |
| Mono<ReactiveSearchHits<Product>> | Reactive search response | Hit stream alongside response-level metadata |
| SearchHits<Product> | Imperative search response | Synchronous hit list and metadata |

If an endpoint only needs a simple list of entities, Flux<Product> may suffice. If you need score, ID, highlights, or sort values, use SearchHit. If you need total hits, max score, aggregations, or other response metadata, keep ReactiveSearchHits.

Avoid converting to Flux<Product> prematurely and then trying to recover discarded metadata.

## 4. ReactiveElasticsearchOperations.search

ReactiveElasticsearchOperations provides search APIs for reactive applications. One common signature:

    Mono<ReactiveSearchHits<Product>> search(
        Query query,
        Class<Product> clazz
    );

You can pass IndexCoordinates if you need to specify the index explicitly:

    Mono<ReactiveSearchHits<Product>> result =
        operations.search(
            query,
            Product.class,
            IndexCoordinates.of("products")
        );

Then extract the hit stream:

    Flux<SearchHit<Product>> hits =
        result.flatMapMany(ReactiveSearchHits::getSearchHits);

This is the reactive flow:

    Mono<ReactiveSearchHits<Product>>
                 |
                 v
        ReactiveSearchHits
          /           \
         v             v
    Flux<SearchHit>  Mono metadata
         |
         v
    SearchHit<Product>
         |
         v
    Product content

The response Mono is the entry point for query-wide metadata. The hit Flux is the multi-element stream. Do not block to transition from Mono to Flux; use flatMapMany or corresponding reactive operators.

## 5. Response-Level Metadata

ReactiveSearchHits can expose search response metadata via publishers. In modern APIs, common methods include:

| Metadata | Meaning | Typical reactive type |
|---|---|---|
| Total hits | Count of documents matching the query per request semantics | Mono<Long> |
| Max score | Highest score among results | Mono<Float> |
| Aggregations | Aggregation results for the request | Mono<AggregationsContainer<?>> |
| Point in Time ID | PIT ID if the search uses PIT and the API exposes it | Mono<String> |
| Execution duration | Execution duration provided by the response/API | Mono<Duration> |

Exact methods and types depend on the Spring Data Elasticsearch version. Some metadata may not exist or may be represented differently in older versions. Check the ReactiveSearchHits interface in your dependency.

Metadata publishers do not represent individual hits. For example, total hits is a single value for the entire search response, not a field repeated inside each SearchHit.

## 6. Hit-Level Metadata in SearchHit

Each SearchHit<T> represents one document in the results. Typically accessible details include:

- getContent(): entity mapped from source.
- getId(): document ID.
- getIndex(): index containing the document.
- getScore(): relevance score if the query computes scores.
- getSortValues(): sort values for the hit.
- getHighlightFields(): highlighted snippets by field.
- getInnerHits(): nested/inner hit metadata if requested by the query.
- getRouting(): routing metadata if provided by the response.
- Explanation or other metadata if supported by the request/API.

Example:

    Flux<ProductSearchRow> rows =
        searchHits.getSearchHits()
            .map(hit -> new ProductSearchRow(
                hit.getId(),
                hit.getIndex(),
                hit.getScore(),
                hit.getContent(),
                hit.getSortValues(),
                hit.getHighlightFields()
            ));

DTO:

    public record ProductSearchRow(
        String id,
        String index,
        Float score,
        Product product,
        List<Object> sortValues,
        Map<String, List<String>> highlights
    ) {}

The types of sort values and highlight fields depend on the client API and Spring Data version. If the DTO is serialized to an HTTP response, convert client-specific values into clear application types rather than exposing internal Elasticsearch objects directly.

## 7. Reading Entity Content and Metadata for Each Hit

A common pattern is mapping SearchHit to a DTO:

    public record ProductHit(
        String id,
        Float score,
        Product content
    ) {}

    Flux<ProductHit> productHits =
        searchHits.getSearchHits()
            .map(hit -> new ProductHit(
                hit.getId(),
                hit.getScore(),
                hit.getContent()
            ));

This preserves ID and score while exposing only the fields required by the business API.

If you only do:

    Flux<Product> products =
        searchHits.getSearchHits()
            .map(SearchHit::getContent);

then ID, score, sort values, highlights, and inner hits are no longer available in the downstream stream. You may get the ID from the entity if the entity has @Id, but score and other search metadata are not domain fields.

## 8. Combining Total Hits and the Hit Stream

An endpoint may need to return both the result list and total hit count. With ReactiveSearchHits, you can combine the metadata Mono and the hit Flux within the same reactive chain.

Example:

    public record ProductSearchResult(
        List<ProductHit> hits,
        Long totalHits,
        Float maxScore
    ) {}

    Mono<ProductSearchResult> searchProducts(Query query) {
        return operations.search(query, Product.class)
            .flatMap(searchHits ->
                Mono.zip(
                    searchHits.getTotalHits(),
                    searchHits.getMaxScore().defaultIfEmpty(0.0f),
                    searchHits.getSearchHits()
                        .map(hit -> new ProductHit(
                            hit.getId(),
                            hit.getScore(),
                            hit.getContent()
                        ))
                        .collectList()
                ).map(tuple -> new ProductSearchResult(
                    tuple.getT3(),
                    tuple.getT1(),
                    tuple.getT2()
                ))
            );
    }

In this example:

- operations.search emits a ReactiveSearchHits.
- getTotalHits supplies total hit metadata.
- getMaxScore supplies max score; defaultIfEmpty is only a fallback when the publisher emits no value.
- getSearchHits emits each hit.
- collectList gathers the hits into a List to build a response DTO.
- Mono.zip waits for the required parts to complete and constructs ProductSearchResult.

collectList() keeps all hits in memory. Only use this pattern when page size is bounded and the result list is small enough. For large result sets, stream hits instead of collecting everything into a List.

In production, if totalHits or maxScore may be omitted, keep them optional rather than silently turning missing values into 0. A value of 0 can mean zero hits, whereas omitted metadata is a distinct case.

## 9. Preserving Optional Metadata Instead of Defaulting Values

A safer representation uses Optional in the DTO:

    public record ProductSearchResult(
        List<ProductHit> hits,
        Optional<Long> totalHits,
        Optional<Float> maxScore
    ) {}

    Mono<ProductSearchResult> searchProducts(Query query) {
        return operations.search(query, Product.class)
            .flatMap(searchHits ->
                Mono.zip(
                    searchHits.getTotalHits()
                        .map(Optional::of)
                        .defaultIfEmpty(Optional.empty()),
                    searchHits.getMaxScore()
                        .map(Optional::of)
                        .defaultIfEmpty(Optional.empty()),
                    searchHits.getSearchHits()
                        .map(hit -> new ProductHit(
                            hit.getId(),
                            hit.getScore(),
                            hit.getContent()
                        ))
                        .collectList()
                ).map(tuple -> new ProductSearchResult(
                    tuple.getT3(),
                    tuple.getT1(),
                    tuple.getT2()
                ))
            );
    }

The metadata publishers are mapped into Monos that always emit an Optional, so Mono.zip does not terminate early simply because a metadata publisher has no value.

If your API version always emits total hits and max score, Optional may not be necessary. Use types matching the actual contract of your version and endpoint.

## 10. Avoiding Multiple Subscriptions to the Same Search Request

Reactive publishers are typically lazy. A search request may only execute when subscribed to. If the same Mono is subscribed to independently multiple times, the application can issue multiple search requests:

    Mono<ReactiveSearchHits<Product>> result =
        operations.search(query, Product.class);

    result.flatMap(ReactiveSearchHits::getTotalHits)
        .subscribe();

    result.flatMapMany(ReactiveSearchHits::getSearchHits)
        .subscribe();

This code may execute the search twice because there are two independent subscriptions. This wastes resources and can return two different snapshots if data changes in between.

Compose metadata and the hit stream under a single subscription:

    Mono<ProductSearchResult> result =
        operations.search(query, Product.class)
            .flatMap(searchHits ->
                Mono.zip(
                    searchHits.getTotalHits(),
                    searchHits.getSearchHits().collectList()
                ).map(tuple -> new ProductSearchResult(
                    mapHits(tuple.getT2()),
                    tuple.getT1()
                ))
            );

Do not call subscribe inside a service to run the request manually and return a separate result to the caller. In WebFlux, controllers normally return Mono or Flux so the framework manages subscription.

## 11. Do Not Use block on a Reactive Path

This approach is inappropriate:

    ReactiveSearchHits<Product> searchHits =
        operations.search(query, Product.class).block();

    Long total = searchHits.getTotalHits().block();

    List<SearchHit<Product>> hits =
        searchHits.getSearchHits().collectList().block();

block() turns an asynchronous flow into synchronous execution, can tie up threads waiting for I/O, and reduces the benefits of the reactive stack. On an event-loop thread, blocking can also throw errors or prevent the system from serving other requests.

Use flatMap, flatMapMany, map, zip, collectList, or other suitable operators:

    Mono<SearchSummary> summary =
        operations.search(query, Product.class)
            .flatMap(searchHits ->
                searchHits.getTotalHits()
                    .map(total -> new SearchSummary(total))
            );

Do not use block just to grab a small piece of metadata. Metadata can be composed into a Mono just like the rest of the response.

## 12. Reading Aggregation Metadata

A search request can include both hits and aggregations. In the reactive API, aggregation metadata is typically provided through a publisher such as Mono<AggregationsContainer<?>>.

General example:

    Mono<AggregationReport> report =
        operations.search(query, Product.class)
            .flatMap(searchHits ->
                searchHits.getAggregations()
                    .map(aggregations ->
                        toAggregationReport(aggregations)
                    )
            );

AggregationsContainer is a Spring Data abstraction. How you fetch aggregations by name and unwrap Elasticsearch-specific types depends on the client integration and Spring Data version.

When using the Elasticsearch Java API Client, the aggregation response may be wrapped in a corresponding container implementation. Do not cast to a specific implementation without verifying the exact version and runtime type.

When both hits and aggregations are needed:

    Mono<ProductSearchResponse> response =
        operations.search(query, Product.class)
            .flatMap(searchHits ->
                Mono.zip(
                    searchHits.getSearchHits().collectList(),
                    searchHits.getAggregations()
                ).map(tuple -> new ProductSearchResponse(
                    mapHits(tuple.getT1()),
                    mapAggregations(tuple.getT2())
                ))
            );

If aggregations were not requested in the query or the metadata publisher can be empty, handle the empty case with Optional or a default object fitting your API contract.

## 13. Reading Point in Time ID and Pagination Metadata

When a search uses Point in Time, the response may include a new PIT ID. Some versions of ReactiveSearchHits expose the PIT ID via a metadata publisher. Always use the latest ID returned by the response when continuing searches against the same snapshot.

General example:

    Mono<PitSearchState> state =
        operations.search(query, Product.class)
            .flatMap(searchHits ->
                searchHits.getPointInTimeId()
                    .map(pitId -> new PitSearchState(pitId))
            );

API methods and PIT metadata types depend on the version. If your project's ReactiveSearchHits does not expose the PIT ID, use the client API or corresponding abstraction to retain response metadata.

PIT ID and hit sort values are two distinct pieces:

- The PIT ID identifies the search snapshot.
- Sort values identify the continuation position.

With search_after, extract the full sort values of the last hit:

    Mono<List<Object>> cursor =
        searchHits.getSearchHits()
            .last()
            .map(SearchHit::getSortValues);

last() requires at least one hit. If there are no results, the publisher may complete empty; handle that case before building a cursor.

When streaming, you can track the cursor while processing each hit up to the last one rather than collecting the entire list. Ensure both the latest PIT ID and the cursor are updated consistently for each pagination session.

## 14. Sort Values and search_after in Reactive Flows

For deep pagination, queries often combine PIT with search_after. The search response returns sort values for each hit. The application uses the last hit's sort values to construct the next request.

Overall flow:

    Open PIT
       |
       v
    Search first page
       |
       v
    ReactiveSearchHits
       |
       +----> response metadata / PIT ID
       |
       v
    Flux<SearchHit<T>>
       |
       v
    Process hits
       |
       v
    Save sort values of the last hit
       |
       v
    Next search request with search_after

Do not derive the cursor from entity fields if SearchHit already provides sort values. Sort values may include tie-breakers or Elasticsearch-normalized types.

If a stream processes multiple hits in parallel, ensure the cursor is selected according to the result's sort order, not the arbitrary completion order of asynchronous tasks.

## 15. Streaming Hits Without Collecting Everything in Memory

If an endpoint or job processes many hits, use Flux to process sequentially or with controlled concurrency:

    Flux<ProductHit> stream =
        operations.search(query, Product.class)
            .flatMapMany(ReactiveSearchHits::getSearchHits)
            .map(hit -> new ProductHit(
                hit.getId(),
                hit.getScore(),
                hit.getContent()
            ));

Consumers can write each item or forward directly to a WebFlux response:

    @GetMapping(value = "/products/stream",
                produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ProductHit> streamProducts() {
        return service.searchProductHits();
    }

Flux emits data according to subscriber demand. This enables backpressure rather than always loading all results into a List.

However, using Flux does not guarantee a query can return unlimited documents or bypass page size limits. The Elasticsearch Search API still caps hits per request and dictates pagination behavior. For large datasets, use scroll or PIT/search_after with an appropriate strategy.

## 16. Backpressure and Asynchronous Per-Hit Processing

Backpressure lets downstream inform upstream of its consumption rate. If a consumer processes slowly, the reactive pipeline can throttle requested data.

Example processing each hit:

    Flux<Void> writes =
        searchHits.getSearchHits()
            .concatMap(hit ->
                archiveService.store(hit.getContent())
            );

concatMap processes each hit one by one, preserving order and moving to the next item according to the operator's sequential semantics.

If concurrency is needed:

    Flux<Void> writes =
        searchHits.getSearchHits()
            .flatMap(
                hit -> archiveService.store(hit.getContent()),
                8
            );

Concurrency 8 caps the number of active inner publishers in this example. Choose the number based on downstream capacity and ordering requirements. flatMap can complete out of the original order.

If a cursor or checkpoint depends on hit ordering, use concatMap or design a coordinator that updates the cursor in sort order.

## 17. Metadata and Streaming: Two Different Response Styles

An HTTP API can emit metadata at the beginning of a response and then stream hits, or wait until processing completes to return a single JSON object containing both metadata and the result list.

### Aggregated JSON Response

    Mono<ProductSearchResult> result =
        operations.search(query, Product.class)
            .flatMap(searchHits ->
                Mono.zip(
                    searchHits.getTotalHits(),
                    searchHits.getSearchHits().collectList()
                ).map(tuple -> new ProductSearchResult(
                    mapHits(tuple.getT2()),
                    tuple.getT1()
                ))
            );

Simple for small page sizes, but keeps all hits in memory.

### Stream Each Hit

    Flux<ProductHit> result =
        operations.search(query, Product.class)
            .flatMapMany(ReactiveSearchHits::getSearchHits)
            .map(this::toProductHit);

Suitable for streaming endpoints or large data processing, though a raw item stream does not naturally wrap everything in a complete JSON metadata envelope.

### Event Stream with Metadata

If using Server-Sent Events or a custom event stream, you can emit a metadata event first and then emit each hit:

    Flux<SearchEvent> events =
        operations.search(query, Product.class)
            .flatMapMany(searchHits ->
                searchHits.getTotalHits()
                    .map(total -> SearchEvent.metadata(total))
                    .flux()
                    .concatWith(
                        searchHits.getSearchHits()
                            .map(this::toSearchEvent)
                    )
            );

SearchEvent is an application-defined DTO. This lets the consumer receive total hits ahead of document events. If max score or aggregations are also needed, combine those metadata publishers before starting the hit stream.

HTTP headers cannot be modified after the response body stream begins. If metadata belongs in HTTP headers, retrieve it before committing the response; if metadata belongs in the body, use an envelope or event stream.

## 18. Total Hits and track_total_hits

Total hits is response metadata reporting how many documents match the query. Elasticsearch can cap exact counting to reduce cost, depending on the request and track_total_hits settings.

The total hits response can have a relation:

- eq: the count is exact per request semantics.
- gte: the value is a lower bound because Elasticsearch stopped counting after reaching a threshold.

ReactiveSearchHits may expose only the numeric value via getTotalHits in some versions, without necessarily exposing the relation. If the API needs to distinguish exact totals from lower bounds, check the abstraction/response metadata provided by your version or use the Elasticsearch Java API Client to read the relation.

Do not always display total hits as an exact count if the query capped track_total_hits. For UIs that only need page navigation, you can use hasNext or the current page's hit count when an exact total is unnecessary.

## 19. Max Score and Per-Hit Score

Max score is the highest score across the entire response. Each SearchHit's score is that specific document's relevance score.

The two values serve different purposes:

- Max score can be used to display or analyze overall response quality.
- Hit score helps explain why a document ranked at a given position.

If the query does not compute scores or sorts by a field, scores may have no meaningful value. Never assume score is always non-null or positive.

When mapping SearchHit to a DTO, keep score nullable/Optional if the API may omit it:

    public record ProductHit(
        String id,
        Float score,
        Product content
    ) {}

If the UI only needs a product list, omit score from the public API. Keeping internal metadata private avoids coupling external contracts to Elasticsearch's relevance scoring algorithm.

## 20. Highlights and Inner Hits

SearchHit can include highlight fields when the query requests highlights:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .match(m -> m
                .field("description")
                .query("mechanical keyboard")
            )
        )
        .withHighlightQuery(/* highlight configuration per version */)
        .build();

Builder names and highlight declarations depend on the Spring Data/Java Client version. When the response contains highlights, each SearchHit can provide highlight metadata for the service to populate DTOs.

Nested queries can use inner_hits to return matching nested objects. Inner hits are also scoped to each parent hit, rather than response-level metadata.

If an API only returns entity content, highlights and inner hits will not be included in the DTO. Map them explicitly when the UI needs matched text snippets or nested objects.

## 21. Aggregation Metadata Is Not a Hit Stream

Aggregations are computed over the set of documents selected by the query, yet the aggregation response is a separate branch of the search response. It is not emitted as a SearchHit per document.

Example:

    Mono<ReactiveSearchHits<Product>> result =
        operations.search(queryWithAggregations, Product.class);

    Mono<AggregationSummary> aggregationSummary =
        result.flatMap(searchHits ->
            searchHits.getAggregations()
                .map(this::toAggregationSummary)
        );

If an endpoint needs both aggregations and hits, combine them under one flatMap as shown earlier. Do not execute the search a second time just to fetch aggregations after consuming the hit stream.

For queries needing only aggregations and no hits, set size to 0 using the appropriate query API. This avoids returning unnecessary documents.

## 22. Execution Duration Metadata

Some versions of ReactiveSearchHits expose the search response's execution duration. This is useful metadata for observability, though it does not necessarily equal the endpoint's total duration.

Endpoint duration also includes:

- Time waiting for a connection.
- Query serialization time.
- Network latency.
- Entity mapping time.
- Downstream processing time.
- Response writing or transmission time.

To measure end-to-end latency, use Micrometer or service/controller instrumentation. Do not treat Elasticsearch's execution duration as the total time the user waited.

## 23. Combining Metadata with Logging and Tracing

You can record total hits, duration, and index to monitor searches:

    Mono<SearchMetrics> metrics =
        operations.search(query, Product.class)
            .flatMap(searchHits ->
                Mono.zip(
                    searchHits.getTotalHits(),
                    searchHits.getExecutionDuration()
                ).map(tuple -> new SearchMetrics(
                    tuple.getT1(),
                    tuple.getT2()
                ))
            );

SearchMetrics is an application-defined DTO. Depending on the version, execution duration may be absent or use a different type.

Avoid logging full query sources if queries contain sensitive data. Avoid using search terms, user IDs, or document IDs as high-cardinality metric tags unless your observability system controls series explosion.

To trace a request across services, use correlation IDs or tracing context rather than passing search metadata into every log line manually.

## 24. ReactiveSearchHits and Standard Pagination

For small pagination, you can use Pageable:

    Pageable pageable = PageRequest.of(0, 20);

    Query query = NativeQuery.builder()
        .withPageable(pageable)
        .build();

    Mono<ReactiveSearchHits<Product>> result =
        operations.search(query, Product.class);

Applications can combine total hits and the hit list to build a response containing page number, page size, and total. However, deep pagination with from/size is limited and grows costlier with depth.

ReactiveSearchHits does not automatically convert the response into a synchronous Spring Data Page. Services should construct an appropriate DTO or page abstraction from metadata and the hit stream.

If using collectList() to build a Page response, cap page size. For deep pagination or large datasets, consider PIT + search_after.

## 25. ReactiveSearchHits and scroll/search_after

For multi-page read tasks:

- Use ReactiveSearchHits when both response metadata and the hit stream are needed.
- Use PIT to hold a consistent snapshot while the context remains alive.
- Use search_after with the last hit's sort values to fetch the next page.
- Update to the latest PIT ID if the response returns a new one.
- Close the PIT upon completion or cancellation.

For scroll:

- Use the scroll/reactive stream API matching your version.
- Update to the latest scroll ID from the response.
- Close/clear the scroll when finished.

Do not treat a Flux<SearchHit<T>> as a durable cursor. Flux is just how current results are consumed; continuing pagination requires a separate PIT/scroll ID and cursor.

## 26. Error Handling in Metadata Publishers and Hit Streams

Reactive pipelines can fail at several stages:

- The search request fails before producing ReactiveSearchHits.
- A metadata publisher fails when subscribed to.
- The hit stream fails mid-emission.
- Entity mapping fails.
- Downstream processing fails.
- The consumer cancels the subscription.

A failure inside Mono.zip can cause the entire combined publisher to fail. If secondary metadata is optional, handle the fallback specifically for that case:

    Mono<Optional<Float>> maxScore =
        searchHits.getMaxScore()
            .map(Optional::of)
            .defaultIfEmpty(Optional.empty());

Do not apply onErrorReturn(0L) to all total hits errors, as it turns network or server failures into a valid-looking 0-hit result. Only use a fallback when metadata may legitimately be absent and the contract allows it.

If the hit stream has emitted some hits before failing, the consumer may have already processed those hits. For write jobs, ensure idempotency or checkpoints so retries do not create duplicates.

## 27. Cancellation and Cleanup

Reactive Streams allows subscribers to cancel. When a user closes an HTTP connection or a job is stopped, the subscription may be canceled before all hits are consumed.

If a search uses a PIT or scroll context, cancellation must be paired with cleanup via the appropriate API and version. Never assume canceling a Flux immediately closes every server-side context.

You can use doFinally to observe complete/error/cancel signals:

    Flux<SearchHit<Product>> hits =
        searchHits.getSearchHits()
            .doFinally(signalType ->
                log.debug("Search hit stream ended: {}", signalType)
            );

doFinally suits metrics/logging or triggering lightweight cleanup. For asynchronous cleanup that must be awaited, use a proper reactive resource management pattern such as usingWhen when the resource lifecycle is well defined.

Never call block inside doFinally and never ignore critical cleanup failures. Retain the PIT/scroll ID in the search session state so the right context is closed.

## 28. Choosing search vs. searchForStream

ReactiveElasticsearchOperations can offer multiple search APIs:

- APIs returning ReactiveSearchHits when response metadata is needed alongside the hit stream.
- APIs returning Flux<SearchHit<T>> or Flux<T> when only the hit/content stream is needed.
- Specialized streaming APIs depending on version and query type.

Method names and signatures can vary. Check the ReactiveElasticsearchOperations interface in your actual dependency.

Choose based on requirements:

| Requirement | API to consider |
|---|---|
| Need total hits, max score, and aggregations | API returning ReactiveSearchHits |
| Only need entity content | Flux<T> |
| Need ID/score/sort/highlights per hit | Flux<SearchHit<T>> |
| Processing a small page and returning a JSON envelope | ReactiveSearchHits + bounded collectList |
| Processing large datasets with backpressure | Flux stream with appropriate pagination/scroll/PIT |

If using a stream API that does not return ReactiveSearchHits, verify which response metadata is omitted and whether the use case requires it.

## 29. Spring WebFlux Controller Returning Metadata with Results

A controller can return a Mono DTO:

    @RestController
    @RequestMapping("/products")
    public class ProductSearchController {

        private final ProductSearchService service;

        public ProductSearchController(ProductSearchService service) {
            this.service = service;
        }

        @GetMapping("/search")
        public Mono<ProductSearchResult> search(
                @RequestParam String q) {
            return service.search(q);
        }
    }

The service executes the query and builds the response:

    public Mono<ProductSearchResult> search(String text) {
        Query query = buildQuery(text);

        return operations.search(query, Product.class)
            .flatMap(searchHits ->
                Mono.zip(
                    searchHits.getTotalHits(),
                    searchHits.getSearchHits()
                        .map(this::toProductHit)
                        .collectList()
                ).map(tuple -> new ProductSearchResult(
                    tuple.getT2(),
                    tuple.getT1()
                ))
            );
    }

This is a general example; DTOs and getters must match your API version. The controller returns Mono so WebFlux manages the subscription and writes the response upon completion.

With large page sizes, collectList can create memory pressure. If streaming hits is desired, choose a response format capable of representing metadata and items over a streaming protocol.

## 30. Reactive Metadata and Serialization

Do not return ReactiveSearchHits or SearchHit directly from a controller without an explicit serialization contract. These types belong to the persistence layer and may contain client-specific objects or metadata unsuitable for public APIs.

Create DTOs instead:

    public record ProductSearchResponse(
        List<ProductHitResponse> items,
        Optional<Long> totalHits,
        Optional<Float> maxScore
    ) {}

    public record ProductHitResponse(
        String id,
        Float score,
        String name,
        List<Object> sortValues
    ) {}

Mapping to DTOs helps:

- Stabilize the API across Spring Data/Elasticsearch client upgrades.
- Select exactly which metadata is exposed.
- Avoid leaking internal fields or overly large response objects.
- Standardize null/optional semantics.
- Simplify service testing without depending on client serialization.

Sort values may contain opaque cursor data. If exposed to clients, protect the cursor according to your API design and never let clients tamper with values trusted by the server.

## 31. ReactiveSearchHits in Tests

When testing a service, use StepVerifier to verify Mono/Flux:

    StepVerifier.create(service.search("keyboard"))
        .assertNext(result -> {
            assertThat(result.totalHits()).isPositive();
            assertThat(result.hits()).isNotEmpty();
        })
        .verifyComplete();

With a hit stream:

    StepVerifier.create(service.searchHitStream("keyboard"))
        .expectNextMatches(hit ->
            hit.id() != null && hit.content() != null
        )
        .thenCancel()
        .verify();

Integration tests with real Elasticsearch must set up indices/mappings and test data. When tests need newly written documents to be searchable, use a refresh policy or explicit refresh instead of Thread.sleep.

Do not verify callbacks or metadata by calling block in production code just for testing. StepVerifier subscribes and verifies signals reactively.

### Verifying Subscription Count

If you need to confirm a search executes only once, mock operations and verify the invocation count of search, or use a test publisher with a side effect counting subscriptions. This catches accidental dual subscriptions for metadata and hits.

## 32. Common Pitfalls

### Converting ReactiveSearchHits to an Entity Flux Too Early

Mapping directly with SearchHit::getContent discards ID, score, sort values, and other metadata. Keep SearchHit or map to a DTO holding the needed metadata.

### Assuming Total Hits Lives Inside Each SearchHit

Total hits is response-level metadata. Read it from ReactiveSearchHits, not from the hit stream.

### Subscribing Separately for Metadata and Hits

A search Mono can re-execute on each subscription. Combine the publishers within a single reactive chain to avoid sending two search requests.

### Using block in WebFlux

block breaks asynchronicity and can stall the event loop. Use flatMap, flatMapMany, zip, and reactive operators.

### Collecting Thousands of Hits with collectList

collectList holds all results in memory. Cap page sizes or stream hits with backpressure.

### Treating Max Score as Always Present

Queries without scoring or responses without scores can leave metadata empty. Represent it as optional/nullable appropriately.

### Assuming Total Hits Is Always Exact

track_total_hits can cap counting. If distinguishing exact totals from lower bounds matters, inspect the relation in the response/API version.

### Confusing Response Metadata with Hit Metadata

Aggregations, total hits, and PIT ID describe the response; ID, score, highlights, and sort values belong to each hit. Place them in the right DTOs.

### Using a Streaming API Yet Expecting All Metadata

Some stream APIs only return hits/content. If total hits or aggregations are needed, use an API returning ReactiveSearchHits or fetch metadata via the matching response mechanism.

### Updating the Cursor from the Last-Completed Hit

flatMap with concurrency can complete out of sort order. The cursor must come from the last hit in result sort order, not the last async task to finish.

### Ignoring Cancellation and PIT Cleanup

Subscriber cancellation should not leave PIT/scroll contexts lingering unintentionally. Manage resource lifecycles and cleanup with the corresponding API.

### Returning Persistence Types Directly on Public APIs

ReactiveSearchHits and SearchHit can vary across versions. Convert to application DTOs before returning HTTP responses.

## 33. Workflow for Reading ReactiveSearchHits

When building a reactive search service, you can follow this sequence:

1. Determine whether the endpoint needs entity content, hit metadata, or response metadata.
2. Use an API returning ReactiveSearchHits if both response metadata and the hit stream are needed.
3. Keep Mono<ReactiveSearchHits<T>> within the same reactive chain.
4. Read total hits, max score, aggregations, or PIT metadata via their respective publishers.
5. Read each SearchHit via Flux to extract content and needed metadata.
6. Combine Mono and Flux with flatMap, flatMapMany, or zip.
7. Only use collectList when results are bounded and small.
8. Never subscribe independently multiple times and never block.
9. Apply backpressure/concurrency limits matching downstream capacity.
10. Keep the latest sort values and PIT ID when using deep pagination.
11. Handle optional metadata and publisher errors explicitly.
12. Clean up PIT/scroll on complete, error, or cancel.
13. Map to application DTOs before returning via WebFlux.
14. Verify actual API signatures and metadata against your Spring Data Elasticsearch version.

## Conclusion

ReactiveSearchHits lets Spring Data Elasticsearch preserve both the hit stream and metadata of a search response in the reactive model. Response-level metadata such as total hits, max score, aggregations, or PIT details are provided via publishers depending on the version; each SearchHit holds individual metadata such as ID, score, sort values, highlights, and inner hits. Entity content is only one part of SearchHit.

Keep ReactiveSearchHits inside the reactive chain when metadata is required, combine metadata Monos with the hit Flux using flatMap/zip, and avoid separate subscriptions or blocking. collectList fits small result pages, whereas Flux streaming processes large datasets with backpressure. When using PIT/search_after, preserve the latest PIT ID along with all sort values from the last hit, and manage cleanup on cancellation. In Spring WebFlux, map results into application DTOs to keep contracts stable and expose only the metadata an endpoint genuinely needs. Always check the interfaces and signatures of your resolved Spring Data Elasticsearch version, as reactive search APIs and exposed metadata can differ between releases.
