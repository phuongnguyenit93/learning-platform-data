# Preserving Essential Metadata When Designing Search Responses

A well-designed search response must preserve enough information for the UI to interpret results, display relevance, paginate accurately, and continue querying subsequent pages. In Spring Data Elasticsearch, this data does not reside solely inside entity objects. Each search result also carries its own metadata such as ID, score, sort values, highlights, and supplementary information from Elasticsearch. The overall response also includes shared metadata such as total hits, total-hits relation, aggregations, and suggest results.

If a service converts `SearchHits<T>` into `List<T>` too early, substantial metadata can be lost. The API is then left with only fields from `_source` and cannot support features the UI needs. Conversely, returning the entire raw Elasticsearch response to clients can expose internal details, couple the API contract to library internals, and transmit unnecessary data.

Good design means deciding which metadata serves a specific use case, retaining that metadata in the service layer, and intentionally mapping it into a stable response DTO.

## 1. Distinguishing Document Content and Search Metadata

### 1.1. Document Content Comes from `_source`

An Elasticsearch document typically has content stored in `_source`. Example:

~~~json
{
  "id": "P1001",
  "name": "Wireless Keyboard",
  "category": "ACCESSORY",
  "price": 49.90,
  "available": true
}
~~~

Spring Data Elasticsearch maps this source section into a Java entity:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    @Field(type = FieldType.Boolean)
    private boolean available;
}
~~~

Properties such as `name`, `category`, `price`, and `available` are business data. They describe the product and can be used across many screens, not only search results.

### 1.2. Search Metadata Describes How a Document Appears in Results

When Elasticsearch returns a hit, the response can contain information outside source:

~~~json
{
  "_index": "products",
  "_id": "P1001",
  "_score": 2.73,
  "_source": {
    "id": "P1001",
    "name": "Wireless Keyboard",
    "category": "ACCESSORY",
    "price": 49.90,
    "available": true
  },
  "sort": [2.73, "P1001"],
  "highlight": {
    "name": [
      "Wireless <em>Keyboard</em>"
    ]
  }
}
~~~

In the example:

- `_index` indicates the index returning the hit.
- `_id` is the document's ID in Elasticsearch.
- `_score` is the score produced by the query.
- `_source` is the document content.
- `sort` contains sort values used for ordering and usable as a cursor.
- `highlight` contains snippets highlighted according to the query.

Not every response contains all of these fields. Score, sort values, highlights, explanation, or inner hits appear only when the query/request and mapping support or request them.

### 1.3. Per-Hit Metadata and Response-Wide Metadata

There are two levels of information:

| Level | Examples | Used for |
|---|---|---|
| Single hit | ID, score, highlights, sort values, inner hits | Displaying and processing each individual result |
| Entire search | Total hits, total-hit relation, aggregations, suggest, execution metadata | Pagination, analytics, and UI controls |

Keep levels distinct when designing DTOs. For instance, score belongs to each individual product, whereas the total result count belongs to the search page as a whole.

## 2. SearchHit and SearchHits in Spring Data Elasticsearch

### 2.1. SearchHit<T> Represents a Single Result

Spring Data Elasticsearch uses `SearchHit<T>` to wrap entity content and metadata for a single hit.

Example iterating results:

~~~java
SearchHits<ProductDocument> searchHits =
    operations.search(query, ProductDocument.class);

for (SearchHit<ProductDocument> hit : searchHits) {
    ProductDocument product = hit.getContent();

    System.out.println("ID: " + hit.getId());
    System.out.println("Score: " + hit.getScore());
    System.out.println("Name: " + product.getName());
}
~~~

`getContent()` returns the entity mapped from source. Other getters expose metadata returned by Elasticsearch and retained by Spring Data.

Common information to consider:

- Hit ID and index.
- Score.
- Sort values.
- Highlight fields.
- Explanation if requested.
- Matched query names if the query names its clauses.
- Inner hits if `nested` or parent/child queries request them.
- Routing or supplementary info if provided by the API/version.

Exact getter names and support levels depend on the Spring Data Elasticsearch version. Inspect the API of your active dependency rather than assuming every version exposes the exact same set of metadata.

### 2.2. SearchHits<T> Represents the Entire Response

`SearchHits<T>` wraps the hit list and overall metadata:

~~~java
long totalHits = searchHits.getTotalHits();
float maxScore = searchHits.getMaxScore();

List<SearchHit<ProductDocument>> hits =
    searchHits.getSearchHits();
~~~

Commonly meaningful information:

- `getSearchHits()` returns the hit list of the current response.
- `getTotalHits()` returns the total hit count reported per query and total-hit tracking configuration.
- `getMaxScore()` returns the highest score among returned hits when scoring applies.
- Aggregations and suggestions can be held on the response if requested by the query.
- Some versions also expose total-hit relation, execution duration, or PIT metadata.

The hit list is the data for the current page. Total hits is the reported matching result count; these two numbers are not necessarily equal.

### 2.3. Do Not Convert to List<T> Too Early

The following snippet is simple, yet drops per-hit metadata:

~~~java
List<ProductDocument> products = searchHits.getSearchHits()
    .stream()
    .map(SearchHit::getContent)
    .toList();
~~~

After this conversion, the list retains only entity content. The service no longer has scores, highlights, or sort values unless kept in another structure.

If an API only displays product data and needs no search metadata, converting into an entity list can be completely appropriate. However, if the UI needs keyword highlighting, relevance explanations, or a next-page cursor, keep `SearchHit` until response construction is complete.

### 2.4. SearchPage Combines Hits with Pagination Information

Spring Data provides `SearchPage<T>` to combine `SearchHit` content with pagination metadata:

~~~java
SearchPage<ProductDocument> searchPage =
    SearchHitSupport.searchPageFor(searchHits, pageable);
~~~

Depending on usage, `SearchPage` provides access to page metadata such as page number, size, and total elements while keeping content as `SearchHit` items. This is a useful option when the application wants to preserve hit metadata while offering a familiar pagination structure.

If only a page of entities is needed, you can transform content after deciding which metadata to keep. Do not let conversion steps discard data required for the response.

## 3. Selecting Metadata by UI Feature

Not every API needs all metadata. Before designing DTOs, start from user behavior.

| Feature | Metadata to consider |
|---|---|
| Simple result list | ID, content, page/size |
| Relevance ordering | Score or ranked hit order |
| Displaying keyword-matched excerpts | Highlight fragments |
| Offset pagination | Page number, size, total hits if needed |
| Deep scrolling results | Sort values and cursor |
| Explaining why a result ranked high | Explanation in debug mode |
| Results from nested documents | Inner hits |
| Grouped filter facets | Aggregations |
| Search suggestions | Suggest response |
| Monitoring query diagnostics | Execution duration and timeout status if exposed |

Needed metadata depends on the API contract. For example, regular UIs do not need raw explanations or internal index names. A search admin tool might need those details on a dedicated, permission-controlled endpoint.

## 4. Score and Relevance Ordering

### 4.1. Score Is a Ranking Signal

`_score` is the value Elasticsearch uses to express how well a document matches the query. For full-text search, score depends on query, analyzer, term statistics, and other scoring factors.

A hit with a score of 4.2 does not mean it is 84% accurate or has a probability of 4.2. Score has relative meaning only within the context of the active query and ranking strategy.

If the UI needs to show “relevance,” it is usually better to rely on result ordering or a normalized business label rather than displaying raw scores to end users.

### 4.2. Retaining Score in DTOs When Genuinely Needed

DTO example:

~~~java
public record ProductSearchItem(
    String id,
    String name,
    BigDecimal price,
    Float score
) {
}
~~~

Mapping from `SearchHit`:

~~~java
ProductSearchItem toItem(SearchHit<ProductDocument> hit) {
    ProductDocument product = hit.getContent();

    return new ProductSearchItem(
        hit.getId(),
        product.getName(),
        product.getPrice(),
        hit.getScore()
    );
}
~~~

Use a nullable type like `Float` if score might not be provided or is meaningless for a specific query. If the API guarantees every query involves scoring, choose the corresponding type and enforce that condition in the service.

### 4.3. When Sorting by a Field, Do Not Assume Score Is the Primary Signal

If a request sorts by price, date, or name, hit ordering may be determined by the sort field rather than relevance. In this case, scores might not be tracked or might not reflect primary ranking order.

If the UI displays scores, verify whether the query requests score tracking and which sort is active. Do not use scores to re-sort results when Elasticsearch already sorted them by another field.

### 4.4. Max Score Belongs to the Overall Response

`getMaxScore()` is response-wide metadata. It is not the score of a specific hit. Per-document scores reside on individual `SearchHit` objects.

Typically, end-user APIs do not need to return max score. It is more useful for diagnostics, ranking observability, or internal tooling.

## 5. Total Hits and the Total Count Relation

### 5.1. Total Hits Is Not the Current Item Count

For example, a query matches 430 documents, while the page size is 20:

- The current hit list contains at most 20 results.
- Total hits can be 430.
- The next page retrieves the subsequent slice under the same criteria and order.

DTOs should distinguish clearly:

~~~java
public record SearchPageResponse<T>(
    List<T> items,
    long totalHits,
    int page,
    int size
) {
}
~~~

Do not compute total using `items.size()`, as that value is only the number of items returned on the page.

### 5.2. Total Hits Can Be Exact or a Lower Bound

Elasticsearch can cap total-hit counting to save cost. When total-hit tracking is capped, the response can express an `eq` relation (exact count) or `gte` (the reported count is a lower bound).

Example:

- `eq` with 430 means the total is confirmed to be exactly 430.
- `gte` with 10,000 means there are at least 10,000 hits; the true total may be higher.

Spring Data Elasticsearch can expose this relation via the `SearchHits` API depending on version. When a business API displays a total, keep both the value and relation if available. Returning only a raw number without relation risks clients misinterpreting a lower bound as an exact total.

### 5.3. track_total_hits and Cost

Search requests can be configured to track exact total hits or cap the count. Exact counting over large datasets can increase cost.

Choose according to UI needs:

- If exact page numbers are needed, full total-hit tracking may be necessary.
- If only displaying one page and a “load more” button, an exact total may be unnecessary.
- If only checking whether more results exist, fetching one extra hit or using an appropriate pagination pattern can suffice.
- If only a count for a specific condition is needed, use the Count API.

Do not make a separate count request when `SearchHits` already provides an exact total meeting requirements. Conversely, do not use a capped total to calculate an exact total page count.

### 5.4. DTO Representing the Relation

You can design:

~~~java
public enum TotalRelation {
    EXACT,
    LOWER_BOUND,
    UNKNOWN
}

public record SearchTotal(
    long value,
    TotalRelation relation
) {
}
~~~

The service maps Spring Data's enum/metadata to the application's API enum. If the version does not expose the relation, assign an appropriate state or avoid claiming the count is exact. Do not infer relation merely because total equals page size or a familiar threshold.

## 6. Sort Values and Next-Page Cursors

### 6.1. Sort Values Are Hit Metadata

When a query includes sorting, each hit can carry a list of sort values. These values reflect the exact sort fields evaluated for that hit.

Example request sorting by timestamp then ID:

~~~json
{
  "sort": [
    { "createdAt": "asc" },
    { "productId": "asc" }
  ]
}
~~~

A hit might return:

~~~json
{
  "sort": [
    "2026-01-15T10:00:00Z",
    "P1001"
  ]
}
~~~

Sort values must be preserved in exact order and data types for use in `search_after` on the next request.

### 6.2. Do Not Build Cursors from Content Yourself

If sorting by date and ID, do not construct a cursor by reading entity fields and re-serializing them in a new format. Take the sort values returned by Elasticsearch, as they correspond to the actual sort execution.

Example reading sort values:

~~~java
List<Object> sortValues = hit.getSortValues();
~~~

Element data types and representations can depend on mapping, client, and version. Preserve the information as provided by the Spring Data API, then serialize it into an opaque cursor according to your application's contract.

### 6.3. Cursors Should Be Opaque Tokens

Instead of requiring clients to send individual sort values, the API can package them into a cursor:

~~~java
public record SearchCursor(
    String token
) {
}
~~~

A cursor can contain or reference:

- Sort values of the last hit on the page.
- Query/filter fingerprint.
- Sort definition/version.
- PIT ID if using point-in-time.
- Expiration timestamp or cursor format version.

Sign or protect tokens so clients cannot tamper with a cursor into another query. If a cursor contains a PIT ID or internal data, avoid exposing raw values unnecessarily; use an encrypted/signed token or store cursor state server-side.

### 6.4. Cursors Must Bind to the Same Query and Sort

The next page must use the exact same query conditions and sort order as the previous page. If a client changes keywords, filters, or sorting mid-pagination, the old cursor becomes invalid.

You can store a fingerprint of query/filter/sort inside the cursor and verify it on the next request. If it mismatches, require the client to start a new search session.

### 6.5. Tie-Breaker and PIT

Sorting requires a stable tie-breaker, usually a unique field with doc values. If multiple documents share the same timestamp or price, their relative order can shift.

When data changes while users scroll pages, use PIT combined with `search_after` if a consistent view is required. The cursor then needs to carry or reference the PIT ID with a lifetime. Close the PIT when finished or when the search session expires.

## 7. Highlight Fragments

### 7.1. Highlights Are Presentation Data from the Query

Highlights help the UI show which parts matched keywords. Elasticsearch returns fragments per requested field, for example:

~~~json
{
  "highlight": {
    "description": [
      "Compact wireless <mark>keyboard</mark> for travel"
    ]
  }
}
~~~

In Spring Data, `SearchHit` can expose highlight fields by field name:

~~~java
List<String> fragments =
    hit.getHighlightField("description");
~~~

A field can return multiple fragments. DTOs should use a list rather than assuming only a single snippet.

### 7.2. Do Not Confuse Highlights with Source

Highlight fragments are generated per query and highlighter configuration. They do not replace original values in the entity. Keep both if the UI needs to render full content alongside excerpts.

DTO example:

~~~java
public record HighlightedText(
    String field,
    List<String> fragments
) {
}
~~~

Mapping:

~~~java
HighlightedText descriptionHighlight =
    new HighlightedText(
        "description",
        hit.getHighlightField("description")
    );
~~~

If a field has no highlights, the list may be empty. Design clients to handle missing fragments gracefully.

### 7.3. Safe HTML Handling

Some highlighters return fragments with markup tags. If inserting fragments directly into HTML, document content may contain untrusted markup or characters.

Choose a clear strategy:

- Configure simple, controlled, dedicated pre/post tags.
- Escape content before rendering and allow only predefined highlight tags.
- Use safe text-rendering components instead of arbitrary HTML rendering.
- Do not treat document fragments as trusted HTML.

Do not strip all tags with naive string replacement if doing so could corrupt text or let unexpected markup slip through. Use a sanitizer/renderer suited to your UI platform.

### 7.4. Highlighting Has a Cost

Highlighting can increase search request work, especially on long fields or many fragments. Request highlights only for fields the UI actually displays, and cap fragment counts and sizes as needed.

Do not enable highlighting on every field in every search endpoint if only one screen uses the feature.

## 8. Explanation, Matched Queries, and Inner Hits

### 8.1. Explanation for Score Diagnostics

Explanation describes the components contributing to a hit's score. It is helpful when debugging why a document ranked high or low.

It can be very verbose and add overhead. Enable it only on admin endpoints or controlled debug modes. Do not return explanations by default to all users.

### 8.2. Matched Query Names

You can name specific query clauses and identify which clauses matched a hit when requests use named queries. This helps when the UI needs to display reason badges such as “name match,” “brand match,” or “secondary keyword match.”

Matched query names should be defined in server code. Do not use them as authorization data and do not let clients supply names to drive access logic.

### 8.3. Inner Hits for Nested Documents

When nested or parent/child queries request inner hits, the response can include matching child documents inside parent documents.

For example, a product has multiple offers, and a query looks for offers from a specific seller. Inner hits tell the UI which offers matched rather than only showing that the parent product matched.

Inner hits can inflate response size. Cap inner hit counts, fetch only needed fields, and map them to dedicated DTOs. Do not assume every hit has inner hits.

## 9. Aggregations and Suggest Are Not Per-Hit Metadata

### 9.1. Aggregations Belong to the Entire Response

Aggregations return summary figures such as product counts by category, price histograms, or brand statistics. They belong to the entire search response, not to an individual document.

For instance, a response might include 20 hits and an aggregation counting products in each category. DTOs should separate:

- Hit list.
- Pagination metadata.
- Aggregation buckets/statistics.

Do not attach aggregations onto every item solely to flatten JSON when that data actually describes the whole query.

### 9.2. Suggest Is a Separate Result Group

Suggest responses can provide keyword suggestions or completion options. Their structure differs from standard `SearchHit` objects.

If an API returns both search results and suggestions, represent them as two distinct sections in the response DTO. Do not treat suggestions as a type of highlight or document list.

## 10. Designing Response DTOs

### 10.1. Do Not Return Framework Objects Directly

Do not let controllers return `SearchHits` or `SearchHit` directly as a long-term API contract. These types belong to the Spring Data library and can evolve across versions.

Application-owned DTOs help:

- Keep the API contract stable across Spring Data upgrades.
- Expose only intentionally chosen metadata.
- Name fields using business terminology.
- Control nullability and data types.
- Avoid leaking index names, raw explanations, or internal details.
- Simplify writing contract tests and API documentation.

### 10.2. Example Response for Product Search

~~~java
public record ProductSearchItem(
    String id,
    String name,
    BigDecimal price,
    Float score,
    List<String> nameHighlights
) {
}

public record SearchPageMetadata(
    long totalHits,
    String totalRelation,
    int page,
    int size,
    boolean hasNext
) {
}

public record ProductSearchResponse(
    List<ProductSearchItem> items,
    SearchPageMetadata page
) {
}
~~~

This is an illustrative contract. If the API does not provide a total relation, omit that field or represent an unknown state explicitly. Do not assign `exact` without verification.

### 10.3. Converting from SearchHits

~~~java
ProductSearchResponse toResponse(
        SearchHits<ProductDocument> hits,
        Pageable pageable,
        boolean hasNext) {

    List<ProductSearchItem> items = hits.getSearchHits()
        .stream()
        .map(hit -> {
            ProductDocument product = hit.getContent();

            return new ProductSearchItem(
                hit.getId(),
                product.getName(),
                product.getPrice(),
                hit.getScore(),
                hit.getHighlightField("name")
            );
        })
        .toList();

    SearchPageMetadata page = new SearchPageMetadata(
        hits.getTotalHits(),
        "UNKNOWN",
        pageable.getPageNumber(),
        pageable.getPageSize(),
        hasNext
    );

    return new ProductSearchResponse(items, page);
}
~~~

In production code, replace `"UNKNOWN"` with the relation mapped from the Spring Data/Elasticsearch API of your project's version. If total relation is not needed, remove the property instead of returning a placeholder value.

`hasNext` should be derived from pagination metadata or an appropriate cursor strategy. Do not infer it solely from total if total might be a lower bound.

### 10.4. Response for Cursor Pagination

A cursor-based response can look like:

~~~java
public record CursorSearchResponse<T>(
    List<T> items,
    String nextCursor,
    boolean hasMore
) {
}
~~~

The cursor is built from the sort values of the last hit, along with a query fingerprint and PIT metadata if present. When no further results exist, `nextCursor` can be `null`.

Do not have clients assemble sort values or PIT IDs from separate fields. An opaque token lets the server control cursor format and validity.

### 10.5. Response for a Page with Aggregations

If the screen needs both a list and facet filters:

~~~java
public record ProductFacet(
    String category,
    long count
) {
}

public record ProductSearchWithFacetsResponse(
    List<ProductSearchItem> items,
    SearchPageMetadata page,
    List<ProductFacet> categories
) {
}
~~~

Aggregation buckets are mapped separately. This makes clear that category counts describe the query's result set rather than per-product metadata.
## 11. Source Filtering and the Risk of Incomplete Entities

### 11.1. Fetching Only Needed Fields

Elasticsearch supports source filtering to return only fields needed by a screen. This can reduce response size and data transfer cost.

For example, a suggestion screen needs only ID and name. However, if Spring Data still maps the response into `ProductDocument`, omitted fields will hold `null` or default values.

### 11.2. Do Not Treat Partial Entities as Complete Sources

If a query fetches only `name` and `price`, do not pass that entity into business services as a complete `ProductDocument`. Another method might misinterpret `available == false` as a real value when the field simply was not loaded.

You can:

- Use a dedicated projection/DTO for the screen.
- Keep source projection semantics explicit in the return type.
- Invoke only operations requiring the selected fields.
- Avoid saving partial entities back with `save`, as writing an object missing fields can overwrite existing data.

### 11.3. Distinguishing Missing Fields from Excluded Fields

A `null` value can mean several things:

- The document genuinely lacks the field.
- The field exists in source with a `null` value.
- Query source filtering excluded the field.
- The mapping converter failed to map the field due to a name or type mismatch.

APIs should avoid ambiguity among these cases if business logic needs to differentiate them. DTOs can use explicit states or projections containing only guaranteed-fetched fields.

## 12. Security and Privacy of Metadata

### 12.1. Expose Only Useful Metadata

Some metadata is useful for debugging yet should not be exposed publicly:

- Physical index names.
- Routing or shard-related details.
- Full explanations.
- Raw queries or internal matched query names.
- Script details and diagnostic information.
- Unprotected PIT IDs or cursor tokens.

Admin endpoints may need some of that information, but must be protected by appropriate authorization.

### 12.2. Metadata Does Not Replace Authorization

Search queries must apply authorization filters on the server. Do not return results and hope the client hides unauthorized items.

For instance, tenant filters and access scopes must be enforced in the query or corresponding authorization layer. Highlights, inner hits, and aggregations can also leak data; apply the same access scope across the entire response.

### 12.3. Cursors Must Be Protected

If a cursor contains sort values, query state, or a PIT ID, clients can tamper with the token if it is just base64 JSON. Base64 is neither encryption nor signing.

Use HMAC-signed tokens, authenticated encryption, or store cursor state server-side. Verify signatures, expiration, and query fingerprints when receiving a cursor.

### 12.4. Avoid Returning Raw Score as Business Data

Scores shift when queries, analyzers, index statistics, or ranking functions change. If clients persist score as a durable product attribute, data becomes misleading.

Treat score as metadata of a single search execution. If the business requires a stable quality score, store a separate field with a clear definition and lifecycle.

## 13. Performance and Metadata Selection

### 13.1. Request Only What Is Actually Used

Metadata carries cost. Key guidelines:

- Do not enable explanations on end-user requests.
- Request highlights only for fields that are displayed.
- Limit fragment count and fragment length.
- Limit inner hits.
- Choose total-hit tracking according to needs.
- Do not return sort values if the API does not need cursors or diagnostics.
- Use source filtering/projections when response sources are large.
- Avoid heavy aggregations if the screen does not use them.

### 13.2. Total-Hit Tracking

If the UI only needs a “load more” button, counting every result accurately may be unnecessary. Choose an appropriate tracking mode or fetch one extra hit to detect a next page.

If the UI shows “1–20 of 430 results” or the last page number, use total tracking matching exactness requirements. Understand the total relation before committing to an API contract.

### 13.3. Highlight and Inner Hits

Highlighting across many fields or very long text can raise CPU usage and response size. Inner hits with many nested children can bloat responses.

Choose quantities suited to the UI. If a screen needs to inspect detailed nested items, consider loading them on a detail endpoint instead of returning all of them in search listings.

### 13.4. Sort Values and Cursors

Sort values are small compared to large sources, though cursors can grow larger when holding PIT and query state. Limit token lengths, enforce TTLs, and do not keep PIT contexts open indefinitely.

## 14. Testing Metadata and Response Contracts

### 14.1. Unit Tests for Mappers

Mappers from `SearchHit` to DTOs can be tested independently:

- IDs are mapped properly.
- Content fields are selected accurately.
- Scores are preserved when present.
- Empty highlight lists are handled.
- Metadata not meant for exposure does not appear in DTOs.
- Nullability and total relations are represented properly.

You can mock `SearchHit` or build fixtures per your version's API. These tests verify mapping logic, not that Elasticsearch returns metadata.

### 14.2. Integration Tests for SearchHits

Run against a compatible Elasticsearch instance to verify:

1. Scoring queries return expected scores.
2. Sorted queries return sort values.
3. Highlight requests return snippets on the expected fields.
4. Total-hit tracking returns appropriate relations.
5. Inner hits contain data when requested by nested queries.
6. Aggregations are preserved on the response when present.
7. Source filtering does not produce misused partial entities.
8. Cursors use actual sort values to fetch subsequent pages.

Do not mock `ElasticsearchOperations` alone and conclude metadata mapping works properly.

### 14.3. Contract Tests for APIs

Verify controller JSON responses:

- Field names are stable.
- Nullable fields follow conventions.
- Total relation is not dropped when needed.
- Cursors do not leak internal data.
- Score semantics are documented accurately.
- Highlights are handled safely.
- No internal metadata outside the contract appears.

When upgrading Spring Data Elasticsearch, contract tests catch mapper changes before affecting clients.

### 14.4. Testing Edge Cases

Include test data covering:

- Zero results.
- Single result.
- Multiple results with tied scores.
- Missing fields.
- Highlights with no fragments.
- Documents with nested children.
- Capped total hits.
- Sort values with dates, numbers, and keywords.
- Expired PIT.
- Timed-out queries or partial response states.

## 15. Common Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| API keeps only entity fields | Service mapped `SearchHits` to content list too early | Keep `SearchHit` until building DTO |
| Score missing or unhelpful | Non-scoring query or request sorts by field | Determine whether score is needed and check sorting |
| Total hits equals current item count | Used `items.size` instead of total metadata | Use total hits and preserve total relation |
| Client miscalculates page count | Total hits is a lower bound but treated as exact | Return relation or choose appropriate total tracking |
| Highlights missing | Query did not request highlights or field is unsuitable | Check highlight request and mapping |
| Highlights break HTML | Fragments rendered as trusted HTML | Escape/sanitize and allow only markup tags |
| Next-page cursor returns duplicates | Cursor built from content or sort lacks tie-breaker | Use hit sort values and stable sorting |
| Cursor fails after filter changes | Cursor is not bound to query fingerprint | Validate query/sort state in cursor |
| Entity has null fields after source filtering | Fields were omitted from source | Use projection DTO and avoid treating entity as complete |
| Inner hits or aggregations missing | Query did not request them or API dropped that response part | Check DSL and API version |
| Response too large | Returning explanations, many highlights, or unbounded inner hits | Request only needed metadata and enforce limits |
| Upgrading Spring Data breaks mapper | Relied on unstable metadata getters or types | Check version API and contract tests |

## 16. Workflow for Designing Search Responses

When building a search endpoint, follow this sequence:

1. Determine which business data must be returned in each item.
2. Determine which hit metadata supports the UI: score, highlights, sort values, or inner hits.
3. Determine response-wide metadata: total hits, relation, page, aggregations, or suggest.
4. Select query options to request the right metadata.
5. Keep `SearchHits`/`SearchHit` in the service layer until mapping completes.
6. Build application-owned DTOs rather than returning framework objects directly.
7. Protect cursors and strip internal metadata not meant for exposure.
8. Audit source filtering to avoid treating partial entities as full entities.
9. Write unit tests for mappers and contract tests for responses.
10. Integration-test against Elasticsearch to verify metadata is actually present with proper semantics.
11. Measure response size and cost of highlights, total tracking, inner hits, or explanations.
12. Keep the API contract stable when upgrading Spring Data Elasticsearch versions.

## 17. Key Takeaways

- Entity content comes from `_source`; search metadata describes hits and the overall response.
- `SearchHit<T>` holds content along with metadata of one document; `SearchHits<T>` holds the hit list and shared metadata.
- Do not convert to `List<T>` before extracting required metadata.
- Score is a relative ranking signal, not a probability.
- Total hits can be exact or a lower bound; do not assume every total count is exact.
- Sort values must be preserved intact to build cursors for `search_after`.
- Highlight fragments are presentation data requiring safe HTML handling.
- Explanation, matched queries, and inner hits should be enabled only when needed by the use case.
- Aggregations and suggest belong to the overall response, not per-hit metadata.
- Dedicated DTOs control the API contract, nullability, and exposed information.
- Source filtering can produce partial entities; do not treat them as complete data or save them back via `save`.
- Cursors should bind to query/sort, carry expiration, and be protected.
- Test both mappers and real responses against compatible Elasticsearch instances.

By identifying which metadata serves each feature, a service can preserve the right data throughout processing and return only what clients need. Search results then provide sufficient information for display, pagination, and explanation while maintaining a clean and maintainable API contract.
