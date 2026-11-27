# Page Index, Page Size, and Mapping to from and size

Pagination splits a large result set into smaller chunks so an API or UI loads only the documents needed for display. In Spring Data Elasticsearch, an application typically represents a pagination request using Pageable, such as PageRequest. Elasticsearch receives two corresponding values: from and size. from is the starting position in the sorted result set, and size is the maximum number of hits to return.

Spring Data page indices are zero-based. Thus the first page has page = 0, and the second page has page = 1. With a fixed page size, the mapping formulas are from = pageNumber × pageSize and size = pageSize. For example, page 3 with size 20 corresponds to from = 60, size = 20.

from/size pagination works well for shallow result pages where users navigate back and forth across the first several pages. Elasticsearch caps the default result window at 10,000 documents via index.max_result_window. For large datasets or deep traversal, use search_after—often combined with Point In Time (PIT)—rather than increasing from indefinitely.

## 1. Why Is Pagination Needed?

Suppose a products index has 50,000 documents. If an API returned all results in a single response, the application would have to:

- Read and convert far more documents than the screen requires.
- Consume large amounts of memory on Elasticsearch, the application server, and the client.
- Transmit a huge response over the network.
- Increase response latency.
- Increase load on shards and the coordinating node.

Pagination limits the number of hits in one response:

~~~text
Sorted result set:        [ 1 ... 1000 ... 50000 ]

Page 0, size 20:          [ 1 ............... 20 ]
Page 1, size 20:          [ 21 .............. 40 ]
Page 2, size 20:          [ 41 .............. 60 ]
...
~~~

APIs typically receive page and size from query parameters:

~~~http
GET /products?page=0&size=20
GET /products?page=1&size=20
GET /products?page=2&size=20
~~~

Each request returns only one slice of results. The API can also provide metadata such as page number, page size, total elements, total pages, hasNext, and hasPrevious.

## 2. Distinguishing page number, offset, and size

Three concepts must be kept distinct:

| Concept | Meaning | Example |
|---|---|---:|
| pageNumber | Page index in Spring Data, starting at 0 | 3 |
| pageSize | Maximum number of elements per page | 20 |
| offset | Number of elements skipped before taking the current page | 60 |

For pagination from the start of the result set:

\[
\text{offset} = \text{pageNumber} \times \text{pageSize}
\]

Elasticsearch uses the parameter name from instead of offset:

\[
\text{from} = \text{offset}, \qquad \text{size} = \text{pageSize}
\]

For example:

| Spring Data page | Spring Data size | Elasticsearch from | Elasticsearch size |
|---:|---:|---:|---:|
| 0 | 20 | 0 | 20 |
| 1 | 20 | 20 | 20 |
| 2 | 20 | 40 | 20 |
| 3 | 20 | 60 | 20 |
| 4 | 20 | 80 | 20 |

Page number is not offset. If an API receives page = 3, size = 20, then from is 60, not 3.

## 3. Spring Data Page Indices Are Zero-Based

Spring Data uses zero-based page indices:

- First page: pageNumber = 0.
- Second page: pageNumber = 1.
- Third page: pageNumber = 2.

PageRequest creates a Pageable:

~~~java
Pageable pageable = PageRequest.of(0, 20);
~~~

This is the first page with up to 20 results.

~~~java
Pageable pageable = PageRequest.of(2, 20);
~~~

This is the third page. Offset is computed as 2 × 20 = 40.

If the UI numbers pages starting from 1, convert at the API boundary:

~~~java
int springPage = requestedPage - 1;
Pageable pageable = PageRequest.of(springPage, pageSize);
~~~

Only perform this subtraction when the API contract genuinely accepts 1-based page numbers. Do not mix Spring's zero-based page convention with a UI's one-based pages.

## 4. Page Size and Input Limits

Page size is the maximum number of documents the application wants to receive in one response. Too large a value makes responses heavy and increases Elasticsearch's workload; too small a value forces clients to send many requests.

APIs should enforce bounds:

- page must be non-negative.
- size must be greater than 0.
- size must have an application-defined maximum.
- Reject page/size values exceeding data-type limits or causing overflow when computing offset.

Example validation in a controller:

~~~java
@GetMapping
public Page<Product> findProducts(
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {

    if (page < 0) {
        throw new IllegalArgumentException("page must be zero or greater");
    }

    if (size < 1 || size > 100) {
        throw new IllegalArgumentException("size must be between 1 and 100");
    }

    return productService.findProducts(PageRequest.of(page, size));
}
~~~

The limit of 100 is just an example API policy. Real systems must choose based on document size, target latency, shard count, and cluster load.

### 4.1. Why Not Let Clients Request Arbitrary Sizes?

If a client sends size = 100000, the application can produce a huge response, spike heap usage, and overload the cluster. A buggy client or intentional abuse can generate many resource-intensive requests.

Enforce default and max sizes on the server. Do not rely on the UI to enforce bounds, because the API can be called directly.

### 4.2. Safe Offset Checking

PageRequest stores offset as a long. However, Elasticsearch from/size has practical limits and is constrained by max_result_window. Do not let page × size overflow or generate overly large offsets:

~~~java
long offset = (long) page * size;

if (offset + size > MAX_ALLOWED_WINDOW) {
    throw new IllegalArgumentException(
            "Requested page exceeds the supported result window");
}
~~~

This is application-policy validation. MAX_ALLOWED_WINDOW should align with index settings and pagination strategy; do not merely check numeric bounds and permit arbitrary offsets.

## 5. Mapping Pageable to Elasticsearch from and size

Spring Data Elasticsearch uses Pageable on Query to pass pagination details down to Elasticsearch. From Pageable, the framework derives:

- Offset to set from.
- Page size to set size.
- Sort to build the sort section of the search request.

Direct example with Query:

~~~java
Pageable pageable = PageRequest.of(2, 20);

CriteriaQuery query = new CriteriaQuery(
        Criteria.where("category").is("accessories"));
query.setPageable(pageable);

SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products"));
~~~

With page = 2 and size = 20, the corresponding search request fetches starting at position 40 and up to 20 hits. Spring Data handles converting Pageable into search request parameters.

### 5.1. NativeQuery with Pageable

If using NativeQuery to write Query DSL:

~~~java
Pageable pageable = PageRequest.of(1, 10);

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
                .term(t -> t
                        .field("category")
                        .value("accessories")))
        .withPageable(pageable)
        .build();

SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products"));
~~~

Pageable is attached to the query. There is no need to write from and size manually in raw JSON when using withPageable.

### 5.2. Do Not Set Pageable Twice

Avoid calling query.setPageable(pageable) while also configuring a different from/size in a native query. Two pagination sources can conflict or make it hard for readers to tell which values are actually sent.

Pick one consistent approach: use Spring Data's Pageable, or use a low-level request with from/size when direct control is genuinely required.

## 6. Using Pageable in a Repository

Repository query methods can accept Pageable for pagination:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    Page<Product> findByCategory(String category, Pageable pageable);
}
~~~

Service:

~~~java
public Page<Product> findByCategory(
        String category,
        int page,
        int size) {

    Pageable pageable = PageRequest.of(page, size);
    return repository.findByCategory(category, pageable);
}
~~~

Spring Data derives the query from the method name, attaches pagination from Pageable, and converts results to Page.

### 6.1. Sort Inside Pageable

PageRequest can accept Sort:

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.asc("category"),
                Sort.Order.desc("price")));
~~~

Elasticsearch receives the sort in the declared field order. Page results are determined after sorting is applied, so sorting must remain consistent across page requests.

### 6.2. Services Should Not Build PageRequest from Unvalidated Inputs

If multiple controllers share a service, validate page and size in one consistent place—such as a request DTO, argument resolver, or service boundary. Do not let different endpoints accidentally enforce inconsistent max sizes.

## 7. Using Page, List, and SearchHits

Different return types provide different levels of metadata:

| Return type | Contents | Pagination metadata |
|---|---|---|
| List<T> | Entities on the page | No total/page metadata |
| Page<T> | Content and page metadata | Page number, size, total elements, total pages |
| SearchHits<T> | SearchHits containing content and hit metadata | Has total hits, scores, and search info |
| SearchPage<T> | SearchHits combined with Pageable | Has both search metadata and page metadata |

If the API only needs to return a list, List may suffice. If the UI needs total pages or next/previous buttons based on total elements, Page is more suitable.

If scores, highlights, or per-hit sort values are needed, use SearchHits/SearchPage to retain Elasticsearch metadata.

### 7.1. Page Is More Than a List

Page contains:

- getContent(): current elements.
- getNumber(): zero-based page index.
- getSize(): page size.
- getNumberOfElements(): actual number of elements on the current page.
- getTotalElements(): total number of elements.
- getTotalPages(): total number of pages.
- hasNext(): whether there is a next page.
- hasPrevious(): whether there is a previous page.
- isFirst()/isLast(): page position.

The last page often contains fewer elements than page size. For example, with 43 documents total and size = 20, the pages contain 20, 20, and 3 elements respectively.

### 7.2. Building a Page from SearchHits When Needed

When using ElasticsearchOperations directly, you can fetch SearchHits and build a PageImpl:

~~~java
public Page<Product> search(
        Query query,
        Pageable pageable) {

    SearchHits<Product> searchHits = operations.search(
            query,
            Product.class,
            IndexCoordinates.of("products"));

    List<Product> content = searchHits.getSearchHits().stream()
            .map(SearchHit::getContent)
            .toList();

    return new PageImpl<>(
            content,
            pageable,
            searchHits.getTotalHits());
}
~~~

The query must have Pageable configured before calling operations:

~~~java
query.setPageable(pageable);
~~~

PageImpl takes the total element count from SearchHits. However, total hit accuracy depends on track_total_hits configuration and the Elasticsearch response. Do not assume total hits is always an unlimited exact count.

## 8. Computing Total Pages and the Last Page

If totalElements = 43 and pageSize = 20:

\[
\text{totalPages} =
\left\lceil \frac{\text{totalElements}}{\text{pageSize}} \right\rceil
= 3
\]

Pages:

| Page | From | Size | Results |
|---:|---:|---:|---|
| 0 | 0 | 20 | 20 elements |
| 1 | 20 | 20 | 20 elements |
| 2 | 40 | 20 | 3 elements |

If totalElements = 40 and size = 20, then totalPages = 2, and valid pages are 0 and 1. There is no page 2 with empty content within the current result range.

If totalElements = 0, totalPages = 0. The requested page number can still be 0, with empty content.

### 8.1. General Formula

With totalElements = N and pageSize = S, where S > 0:

\[
\text{totalPages} = \left\lceil \frac{N}{S} \right\rceil
\]

Spring Data Page provides getTotalPages() so you do not need to compute it manually in the service.

### 8.2. The Last Page May Be Partial

Do not assume the number of elements in content always equals pageSize. Only getSize() represents the requested page size; getNumberOfElements() is the actual number of elements in the response.

## 9. Computing Next and Previous

An API can return metadata:

~~~json
{
  "page": 1,
  "size": 20,
  "numberOfElements": 20,
  "totalElements": 43,
  "totalPages": 3,
  "first": false,
  "last": false,
  "hasNext": true,
  "hasPrevious": true
}
~~~

This is an example DTO; the content array can be placed in a separate field.

The UI can use:

- hasPrevious to enable/disable the Previous button.
- hasNext to enable/disable the Next button.
- totalPages to display total pages if the total is exact.
- number to identify the current page.

Do not calculate hasNext manually by comparing page against a hard-coded value. Use Page metadata or an appropriate cursor response.

## 10. Stable Sorting Across Pages

from/size pagination must have a deterministic result order. If sorting on a non-unique field, multiple documents can share the same sort value. Elasticsearch may return tied documents in an unstable order across requests.

For example, sorting only by category:

~~~java
Sort sort = Sort.by(Sort.Order.asc("category"));
~~~

Many products can share the same category. When data changes or shards return results in a different order, documents can appear on two pages or be skipped.

You should add a unique sort field as a tie-breaker:

~~~java
Sort sort = Sort.by(
        Sort.Order.asc("category"),
        Sort.Order.asc("sku"));
~~~

Here sku must be mapped as keyword and guaranteed unique within the result set. Do not default to sorting directly on Elasticsearch _id; the _id field is not designed as a standard sort field. If a tie-breaker is needed, store a suitable keyword field in _source.

### 10.1. Which Fields Can Be Sorted?

Suitable fields typically include:

- keyword.
- numeric such as integer, long, double.
- date.
- boolean.

Text fields are analyzed into tokens and are unsuitable for direct sorting. If both full-text search and sorting are needed, the mapping can use a multi-field:

~~~json
{
  "name": {
    "type": "text",
    "fields": {
      "keyword": {
        "type": "keyword"
      }
    }
  }
}
~~~

Sort by name.keyword instead of the text name field:

~~~java
Sort sort = Sort.by(Sort.Order.asc("name.keyword"));
~~~

Field names must match the actual mapping. The Spring Data field name and Elasticsearch field name can differ if the entity uses @Field(name = "...").

### 10.2. A Tie-Breaker Does Not Eliminate All Pagination Drift

Stable sorting ensures deterministic ordering when data is unchanged. If documents are added, deleted, or have their sort fields updated between two page requests, result positions can still shift. To traverse a stable snapshot on large datasets, use PIT combined with search_after.

## 11. Mapping from and size in Elasticsearch DSL

A search request corresponding to page = 2, size = 10:

~~~http
GET products/_search
{
  "from": 20,
  "size": 10,
  "query": {
    "term": {
      "category": "accessories"
    }
  },
  "sort": [
    {
      "price": "asc"
    },
    {
      "sku": "asc"
    }
  ]
}
~~~

Meaning:

- Elasticsearch skips the first 20 hits in sort order.
- Returns up to the next 10 hits.
- Sort is applied before taking the from/size window.

If sort is omitted, Elasticsearch still returns results, but the order should not be treated as a stable pagination contract.

### 11.1. from Is Not the Number of Documents Loaded from Each Shard

Elasticsearch distributes searches across shards. Each shard may need to find and retain candidates corresponding to from + size before the coordinating node merges results. Thus cost rises as from grows, even if the response only returns size hits.

For example, from = 9000, size = 20 may require processing a window of 9020 hits on each involved shard before the coordinator selects the right slice.

This is why deep offset pagination is more expensive than looking solely at the number of returned hits suggests.

## 12. The max_result_window Limit

Elasticsearch sets index.max_result_window to 10,000 by default. The condition is generally that from + size must not exceed the allowed window.

Example with size = 20:

| Page | From | From + size | Default |
|---:|---:|---:|---|
| 0 | 0 | 20 | Valid |
| 100 | 2000 | 2020 | Valid |
| 400 | 8000 | 8020 | Valid |
| 499 | 9980 | 10000 | At limit |
| 500 | 10000 | 10020 | Exceeds limit |

Requests exceeding the limit typically fail with a result window too large error.

Check the setting:

~~~http
GET products/_settings?filter_path=*.settings.index.max_result_window
~~~

You can increase the setting:

~~~http
PUT products/_settings
{
  "index": {
    "max_result_window": 20000
  }
}
~~~

However, raising the limit does not make deep pagination free. It permits more resource-intensive requests and can increase memory pressure on shards and coordinators. Only increase it after load testing and with proper API limits.

### 12.1. Do Not Solve Deep Pagination Simply by Raising the Setting

If a product requires users to jump to page 50,000, from/size is not the right strategy. Choose:

- search_after for sequential traversal.
- PIT + search_after when a stable snapshot is needed.
- Scroll for batch processing / reading an entire dataset in a background workflow, not typical interactive UI pagination.

## 13. Total Hits and the Accuracy of totalElements

Page normally needs total elements to compute totalPages. Elasticsearch can limit total hit counting to reduce cost. In a search response, total hits can have a relation:

| Relation | Meaning |
|---|---|
| eq | Total hit count was counted accurately |
| gte | Total hit count is at least the returned value |

Example response:

~~~json
{
  "hits": {
    "total": {
      "value": 10000,
      "relation": "gte"
    }
  }
}
~~~

This means there are at least 10,000 results; you cannot conclude the exact total is 10,000.

If an API needs exact totals, Elasticsearch supports track_total_hits to request exact counting. This can increase search cost, particularly with broad queries and large indices.

### 13.1. Page Total May Be an Estimate or Lower Bound

When converting SearchHits to PageImpl, do not automatically assume getTotalHits() is exact if the response has relation gte. The API should distinguish:

- Exact total.
- Minimum total (lower bound).
- No total needed; only whether there is a next page.

If the UI only needs a Next button, you can avoid counting the full total and fetch size + 1 hits or use a suitable Slice/cursor mechanism.

### 13.2. Page and Slice

Page provides totalElements and totalPages. Obtaining an exact total may require extra work or a count query.

Slice focuses on the current content and whether more elements follow, without needing the full total count. If the UI only has Next/Previous, Slice or a cursor response may fit better than Page.

## 14. Pagination with CriteriaQuery and SearchHits

Example service using CriteriaQuery:

~~~java
public SearchHits<Product> search(
        String category,
        Pageable pageable) {

    CriteriaQuery query = new CriteriaQuery(
            Criteria.where("category").is(category));

    query.setPageable(pageable);

    return operations.search(
            query,
            Product.class,
            IndexCoordinates.of("products"));
}
~~~

Caller:

~~~java
Pageable pageable = PageRequest.of(
        1,
        20,
        Sort.by(
                Sort.Order.asc("category"),
                Sort.Order.asc("sku")));

SearchHits<Product> hits = searchService.search(
        "accessories",
        pageable);
~~~

Spring Data translates page/size/sort from Pageable into the search request. SearchHits holds hit metadata so upper layers can map it into a DTO or Page.

## 15. Pagination with NativeQuery

NativeQuery is suitable when combining Query DSL and Pageable:

~~~java
public SearchHits<Product> search(
        String text,
        Pageable pageable) {

    NativeQuery query = NativeQuery.builder()
            .withQuery(q -> q
                    .match(m -> m
                            .field("name")
                            .query(text)))
            .withPageable(pageable)
            .build();

    return operations.search(
            query,
            Product.class,
            IndexCoordinates.of("products"));
}
~~~

If the query already specifies a sort in the NativeQuery builder and Pageable also contains a Sort, choose a single sort source or verify the combination order for your Spring Data version. Avoid letting two sort configurations accidentally override each other.

## 16. API Responses for Pagination

You do not have to expose Spring Data's Page object directly outside the API. You can map it to a DTO to keep the HTTP contract stable:

~~~java
public record PageResponse<T>(
        List<T> content,
        int page,
        int size,
        int numberOfElements,
        long totalElements,
        int totalPages,
        boolean hasNext,
        boolean hasPrevious) {

    public static <T> PageResponse<T> from(Page<T> result) {
        return new PageResponse<>(
                result.getContent(),
                result.getNumber(),
                result.getSize(),
                result.getNumberOfElements(),
                result.getTotalElements(),
                result.getTotalPages(),
                result.hasNext(),
                result.hasPrevious());
    }
}
~~~

Controller:

~~~java
@GetMapping
public PageResponse<Product> find(
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {

    Page<Product> result = service.find(PageRequest.of(page, size));
    return PageResponse.from(result);
}
~~~

A DTO prevents the API from coupling directly to the serialization details of Page implementations. You can add sort metadata or totalRelation if the API needs to represent a lower-bound total hits value.

## 17. Pagination When Data Changes Between Requests

from/size is offset pagination. Each search request is independent and may observe a different index state.

For example:

1. The client loads page 0 with 20 documents.
2. A new document is inserted at the start of the sort order.
3. The client loads page 1 with from = 20.

Because the new document takes the first position, a document from the old page 0 can be pushed into page 1. The client may see duplicate documents or miss documents while browsing pages.

Deleting documents or updating sort fields between two requests can also shift offsets.

This is a property of offset pagination over changing data. Stable sorting makes order deterministic for a given data state, but it does not lock a snapshot across multiple requests.

If the use case needs to browse a consistent result set, use PIT combined with search_after.

## 18. Deep Pagination with search_after

search_after retrieves the next page based on the sort values of the last hit from the previous page, rather than skipping a large offset.

Flow:

~~~text
Search request 1
    size = 100
    sort = [createdAt, sku]
          |
          v
    Hits 1 ... 100
          |
          v
    Read sort values of hit 100
          |
          v
Search request 2
    size = 100
    search_after = sort values of hit 100
          |
          v
    Hits 101 ... 200
          |
          v
    Repeat with last hit sort values
~~~

First request:

~~~http
POST products/_search
{
  "size": 100,
  "query": {
    "term": {
      "active": true
    }
  },
  "sort": [
    {
      "createdAt": "asc"
    },
    {
      "sku": "asc"
    }
  ]
}
~~~

Suppose the last hit has sort values:

~~~json
{
  "sort": [
    "2026-11-13T10:00:00.000Z",
    "SKU-0100"
  ]
}
~~~

The next request passes that exact sort array:

~~~http
POST products/_search
{
  "size": 100,
  "query": {
    "term": {
      "active": true
    }
  },
  "sort": [
    {
      "createdAt": "asc"
    },
    {
      "sku": "asc"
    }
  ],
  "search_after": [
    "2026-11-13T10:00:00.000Z",
    "SKU-0100"
  ]
}
~~~

Elasticsearch starts after the hit with those sort values. No offset is computed and thousands of prior hits do not need to be skipped.

### 18.1. search_after Needs a Stable Sort

Sort values must define a unique order. If sorting only by createdAt and multiple documents share the same timestamp, there may be no unique continuation point.

Add a unique keyword tie-breaker, such as sku or externalId:

~~~json
"sort": [
  {"createdAt": "asc"},
  {"sku": "asc"}
]
~~~

Do not manually construct search_after by passing only the primary field value. You must pass the complete sort values in the exact order Elasticsearch returned in the last hit.

### 18.2. search_after Is Sequential Pagination

search_after is designed for advancing from the current page. It does not support jumping arbitrarily to page 500 by merely passing a page number. The client must retain the cursor/sort values of the last hit from the previous page.

Therefore, UI designs like "jump to page 500" do not fit pure search_after. For such use cases, reconsider the UX, use offset for shallow pages, or build cursor navigation.

## 19. Point In Time (PIT) Combined with search_after

If data changes while a client browses multiple pages, search_after without a fixed snapshot can be affected by inserts, updates, or deletes between requests.

Point In Time creates a stable view of the index for a retained duration. Use PIT with search_after to traverse pages sequentially on the same snapshot.

Open a PIT:

~~~http
POST products/_pit?keep_alive=1m
~~~

Elasticsearch returns a PIT ID. Search with the PIT:

~~~http
POST /_search
{
  "size": 100,
  "pit": {
    "id": "PIT_ID",
    "keep_alive": "1m"
  },
  "query": {
    "term": {
      "active": true
    }
  },
  "sort": [
    {"createdAt": "asc"},
    {"sku": "asc"}
  ]
}
~~~

The next request uses the same PIT context and the search_after values from the last hit:

~~~http
POST /_search
{
  "size": 100,
  "pit": {
    "id": "LATEST_PIT_ID",
    "keep_alive": "1m"
  },
  "query": {
    "term": {
      "active": true
    }
  },
  "sort": [
    {"createdAt": "asc"},
    {"sku": "asc"}
  ],
  "search_after": [
    "2026-11-13T10:00:00.000Z",
    "SKU-0100",
    4294967298
  ]
}
~~~

PIT can return a new ID in the response. If the response provides a new PIT ID, use the latest ID for the next request.

When finished, close the PIT:

~~~http
DELETE /_pit
{
  "id": "LATEST_PIT_ID"
}
~~~

Keeping a PIT open too long retains resources and old segments. Set keep_alive long enough for a traversal pass, renew it when continuing, and close the PIT when finished or when the cursor is canceled.

### 19.1. PIT Provides a Snapshot, Not a Business Transaction

PIT maintains a stable search view for traversal. It does not lock the index and does not create an application transaction. New or modified documents after the PIT is created will not appear in that snapshot.

### 19.2. Tie-Breaker with PIT

When using PIT, Elasticsearch appends _shard_doc as an internal tie-breaker for hit ordering if needed. The application must still use the exact sort values returned in the last hit to construct search_after. Do not drop the last element from the sort array yourself.

If declaring a business tie-breaker such as sku, it must have a sortable mapping and guarantee uniqueness within the result scope. Even with PIT, use the intact sort values from the response.

## 20. When to Use from/size, search_after, or Scroll?

| Mechanism | Suitable for | Limitations |
|---|---|---|
| from/size | Shallow UI pagination, direct page jumping | Deep offsets are expensive and bounded by max_result_window |
| search_after | Sequential traversal of large data | Needs previous page's sort values, no arbitrary jumping |
| PIT + search_after | Stable sequential traversal on a snapshot | Must manage PIT lifecycle and keep_alive |
| Scroll | Session-based batch export/processing | Unsuitable for standard interactive pagination; holds server-side context |

Scroll was designed for reading large volumes of results across batches within a session. For new applications needing deep, stable traversal, Elasticsearch recommends PIT combined with search_after instead of using scroll as a UI pagination mechanism.

## 21. Reactive Pagination

Reactive repositories still use Pageable and PageRequest with zero-based rules:

~~~java
Flux<Product> findByCategory(String category, Pageable pageable);
~~~

For example:

~~~java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.asc("price")));

Flux<Product> products = reactiveRepository.findByCategory(
        "accessories",
        pageable);
~~~

The result is a Flux because reactive repositories emit items as a stream. Pageable only carries page/size/sort; it does not turn a Flux into a Page with total metadata.

If a reactive API needs the total element count, you can combine the content query and a count query:

~~~java
Mono<ReactiveProductPage> findPage(
        String category,
        Pageable pageable) {

    Flux<Product> content = repository.findByCategory(category, pageable);
    Mono<Long> total = repository.countByCategory(category);

    return Mono.zip(content.collectList(), total)
            .map(tuple -> new ReactiveProductPage(
                    tuple.getT1(),
                    pageable.getPageNumber(),
                    pageable.getPageSize(),
                    tuple.getT2()));
}
~~~

This is an illustrative DTO. The two content/count requests may observe data at different points in time if the index is changing. If an exact total is unnecessary, avoid the count query and return appropriate cursor/hasNext metadata.

## 22. Count and Page Can Be Expensive

To build a full Page, the application needs totalElements. In Elasticsearch, accurately counting all hits can take time depending on the query, shard count, and index size.

Ways to reduce cost:

- Constrain queries with selective filters.
- Avoid exact counting if the UI only needs a Next button.
- Use Slice/cursor responses when totalPages is unnecessary.
- Only request exact track_total_hits when business logic requires it.
- Cache totals if data changes infrequently and cache semantics fit.
- Use appropriate aggregation/count APIs if only counts are needed.

Do not execute a separate count query on every request if the UI does not use the total count.

## 23. Handling Pages Beyond the Results

If a client requests a page greater than the last page:

~~~http
GET /products?page=100&size=20
~~~

The API can return an empty Page with the requested page metadata and current totalElements, or return 404/400 per the API contract. Choose one consistent rule.

With Spring Data's Page, content can be empty while totalElements still indicates how many elements exist in the result set. Do not silently rewrite page to the last page without telling the client, as that makes page metadata mismatch the request.

If page number is negative or size is invalid, return a clear validation error before calling Elasticsearch.

## 24. Testing page/size/from Mapping

An integration test should verify:

- page 0 returns the first documents per sort.
- page 1 starts after page 0 by the exact number of elements.
- size limits the number of returned hits.
- The last page can have fewer than size elements.
- totalElements/totalPages reflect expected data.
- Sort is stable across requests.
- Pages outside the window are handled per the API contract.

For example:

~~~java
@Test
void mapsPageNumberAndSizeToExpectedWindow() {
    Pageable firstPage = PageRequest.of(
            0,
            2,
            Sort.by(Sort.Order.asc("sku")));
    Pageable secondPage = PageRequest.of(
            1,
            2,
            Sort.by(Sort.Order.asc("sku")));

    Page<Product> first = repository.findByCategory(
            "accessories",
            firstPage);
    Page<Product> second = repository.findByCategory(
            "accessories",
            secondPage);

    assertThat(first.getContent()).hasSize(2);
    assertThat(second.getContent()).hasSize(2);
    assertThat(first.getContent())
            .doesNotContainAnyElementsOf(second.getContent());
}
~~~

This test needs a fixture with at least four products and a deterministic sort field. If sorting only by a duplicated field, the test may be flaky.

### 24.1. Testing from/size Mapping Directly

When you need to verify that the actual Elasticsearch request contains the expected from and size, you can use a mock client/request capture or an integration test inspecting the search request. Do not only assert that PageRequest was constructed properly; verify that the query/operations received the Pageable.

### 24.2. Testing Deep Pagination

Do not create tens of thousands of documents in every unit test just to test max_result_window. You can:

- Unit test page/size/window validation in the service.
- Write a small integration test verifying a custom low setting and the error when exceeded.
- Write a dedicated test for cursor/search_after with a dataset large enough to span multiple batches.

## 25. Common Pitfalls

### Confusing page number with from

page is the page index, while from is the offset. Compute from = page × size.

### Using 1-based pages for PageRequest

PageRequest is zero-based. If an API accepts 1-based page numbers, convert explicitly at the boundary.

### Failing to cap size

Clients can request overly large responses. Set default and max sizes on the server.

### Forgetting Pageable in Query

Creating a PageRequest without attaching it to a repository method or Query means Elasticsearch will not receive the pagination as intended. Pass Pageable to the repository or call query.setPageable/withPageable.

### Unstable sort

Sort fields with many duplicate values can cause hits to shift positions. Add a unique keyword tie-breaker.

### Sorting on a text field

Text fields are analyzed; use a keyword subfield or a field with a sortable type.

### Sorting directly on _id

Do not assume _id is a standard sort field. Store a suitable unique keyword field as a tie-breaker.

### Exceeding max_result_window

from + size exceeding the default limit of 10,000 will fail. Use search_after/PIT for deep traversal instead of raising the setting indefinitely.

### Assuming total hits is always exact

Elasticsearch can return total relation gte. Check total hits semantics before using it to calculate exact totalPages.

### Using Page when total count is unnecessary

Exact counting can be expensive. If the UI only needs to know whether a next page exists, use Slice or a cursor.

### Data changing between pages

Offset pagination can duplicate or skip hits when the index changes. PIT + search_after is suitable for traversals needing a stable snapshot.

### Using search_after without preserving sort values

You must send the exact sort array of the last hit from the previous page. Do not synthesize a cursor from arbitrary fields.

### Using search_after to jump to an arbitrary page

search_after is a sequential cursor. It does not support direct random access by page number.

### Keeping PIT open too long

PIT retains resources and segments. Set a sufficient keep_alive, renew on continuation, and close when done.

### Using Scroll for UI pagination

Scroll is meant for session-based batch processing/reading large volumes. Use from/size for shallow pages or PIT + search_after for deep traversal.

## 26. Workflow for Designing API Pagination

When adding pagination to a Spring Data Elasticsearch endpoint:

1. Determine whether the UI needs page numbers or cursors.
2. If only early pages are needed, use Pageable/PageRequest.
3. Define zero-based or one-based paging in the API contract.
4. Choose default size and max size on the server.
5. Validate that page is non-negative, size is positive, and offset does not exceed bounds.
6. Construct PageRequest with a stable sort.
7. Pass Pageable to a repository method or attach it to a Query.
8. Choose Page if total metadata is needed; choose List/SearchHits/Slice/cursor if more suitable.
9. Determine whether total hits must be exact or just a lower bound.
10. Ensure sort fields have sortable mappings and a tie-breaker.
11. Keep from/size within max_result_window.
12. Switch to PIT + search_after for deep traversal or stable snapshots.
13. Close PIT and manage cursor lifecycle.
14. Test page 0, subsequent pages, the last page, sorting, and out-of-bounds cases.

## 27. Summary

Spring Data Pageable represents page number, page size, and sort. Page numbers start at 0; offset is computed as pageNumber × pageSize. Spring Data Elasticsearch translates offset into Elasticsearch from and page size into size. Repository query methods can accept Pageable; with Query objects, attach Pageable using setPageable or withPageable depending on the query type.

Page provides content along with totalElements/totalPages, whereas List only holds elements. SearchHits retains hit metadata and total hits from Elasticsearch. Total hits may only be a lower bound if Elasticsearch does not count all matches accurately; only request exact counts when business logic requires them.

from/size works well for shallow pages and supports direct page jumping, but cost grows with from + size. Elasticsearch defaults index.max_result_window to 10,000. Do not raise the limit indefinitely to support deep pagination. For sequential traversal of large data, use search_after; if a stable snapshot is needed while data changes, combine with Point In Time and close the PIT when finished.

Sorting must be stable and use fields with suitable mappings. Add a unique keyword tie-breaker to reduce duplicate or skipped hits across pages. However, offset pagination can still drift when data changes between requests; PIT + search_after better addresses the need to traverse a snapshot.

## References

- [Spring Data Elasticsearch – Repositories](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/repositories.html)
- [Spring Data Elasticsearch – Query API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/query/Query.html)
- [Spring Data Elasticsearch – PageRequest API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/PageRequest.html)
- [Spring Data Elasticsearch – SearchHits API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/SearchHits.html)
- [Elasticsearch – Paginate search results](https://www.elastic.co/guide/en/elasticsearch/reference/current/paginate-search-results.html)
- [Elasticsearch – Search API](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-search.html)
- [Elasticsearch – Point in Time API](https://www.elastic.co/guide/en/elasticsearch/reference/current/point-in-time-api.html)
- [Elasticsearch – Scroll API](https://www.elastic.co/guide/en/elasticsearch/reference/current/scroll-api.html)
