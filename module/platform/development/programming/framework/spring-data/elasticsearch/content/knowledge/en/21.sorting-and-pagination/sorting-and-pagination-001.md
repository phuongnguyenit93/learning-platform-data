# Sort, Sort.Order, and Pageable in Spring Data

In a Spring Data Elasticsearch application, search typically requires two capabilities working together: selecting matching documents and determining the display order. The query determines the result set, while the sort determines which document comes first. Pageable combines pagination information with sorting so that a service or repository can retrieve a subset of results in the desired order.

Spring Data provides familiar abstractions:

- Sort represents one or more sorting criteria.
- Sort.Order describes a single sort condition, including the field and ascending/descending direction.
- Pageable describes the current page, page size, offset, and sort.
- PageRequest is the common implementation used to create a Pageable.

These abstractions help keep repository and service code less coupled to Elasticsearch REST API details. However, Elasticsearch only sorts efficiently on fields with an appropriate mapping. In particular, you should not sort directly on an analyzed text field; you typically need to use a keyword sub-field, numeric field, or date field with doc values.

## 1. Why Are Sorting and Pagination Needed?

Suppose a product listing page needs to display 20 products at a time, with the most recently updated items first. If you only run a search without specifying a sort, the result order is not a stable business guarantee. The application should request sorting by update time in descending order.

For example:

    Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("updatedAt"))
    );

    Page<Product> page = productRepository.findAll(pageable);

Here:

- The first page has index 0.
- Each page contains at most 20 products.
- updatedAt is sorted in descending order.
- The repository returns a Page containing the content and pagination metadata.

Pagination limits the number of documents returned in a single request. Sorting ensures the results are ordered appropriately for the user experience. When used together, the sort must be stable enough so users can navigate from one page to another without frequently encountering duplicate or skipped results.

## 2. What Is Sort?

Sort is Spring Data's abstraction for describing sort order. It can contain one or more Sort.Order instances.

Example of sorting by price ascending:

    Sort sort = Sort.by("price").ascending();

Or:

    Sort sort = Sort.by(Sort.Order.asc("price"));

Descending sort:

    Sort sort = Sort.by(Sort.Order.desc("createdAt"));

Sort does not inherently contain only a single field. It is an ordered collection of Orders. When multiple Orders are present, Elasticsearch applies them in priority order: the first field is evaluated first; if two documents are equal on that field, the next field is used to break the tie.

This can be expressed as:

    Sort sort = Sort.by(
        Sort.Order.desc("updatedAt"),
        Sort.Order.asc("name")
    );

Results are sorted by updatedAt descending. If two documents have the same updatedAt, name ascending determines the order between them.

## 3. Sort.Order and Its Properties

Sort.Order describes an individual sorting criterion. Important components include:

| Property | Meaning |
|---|---|
| property | Name of the field or property used for sorting |
| direction | ASC or DESC |
| ascending() | Creates an ascending Order |
| descending() | Creates a descending Order |
| null handling | Hints how to handle null values in the Spring Data abstraction; translation capability depends on the datastore |
| ignoreCase() | Marks the intent to ignore case differences if supported by the datastore |

For example:

    Sort.Order priceAscending =
        Sort.Order.asc("price");

    Sort.Order newestFirst =
        Sort.Order.desc("createdAt");

    Sort.Order nameAscending =
        Sort.Order.asc("name");

You can create an Order from a direction:

    Sort.Order order = new Sort.Order(
        Sort.Direction.DESC,
        "createdAt"
    );

Sort.Order only describes the order. It does not verify whether the field exists in the Elasticsearch mapping, nor does it automatically convert a text field to keyword. Choosing the right field remains the responsibility of mapping and query design.

## 4. Creating Sort with a Single Field

Commonly used patterns:

    Sort byPrice = Sort.by("price");

    Sort priceDescending =
        Sort.by(Sort.Direction.DESC, "price");

    Sort newestFirst =
        Sort.by(Sort.Order.desc("createdAt"));

    Sort alphabetical =
        Sort.by(Sort.Order.asc("name"));

Sort.by("price") defaults to ascending order. To make business code readable, you should explicitly specify the direction when order matters:

    Sort sort = Sort.by(
        Sort.Order.desc("rating")
    );

For numeric values, ASC is typically smallest to largest; DESC is largest to smallest. For dates, DESC typically places the most recent timestamps first. For keyword fields, ASC/DESC is based on term order according to Elasticsearch semantics, not natural language collation order.

## 5. Combining Multiple Sort.Order Instances

Sort can contain multiple criteria:

    Sort sort = Sort.by(
        Sort.Order.desc("rating"),
        Sort.Order.desc("purchaseCount"),
        Sort.Order.asc("name")
    );

Elasticsearch will:

1. Sort by rating descending.
2. If ratings are equal, sort by purchaseCount descending.
3. If both fields are equal, sort by name ascending.

This is multi-criteria sorting. The order of Orders inside Sort is very important. Changing the order of Orders changes the priority order.

Another example for an orders page:

    Sort orderSort = Sort.by(
        Sort.Order.asc("deliveryDate"),
        Sort.Order.desc("priority"),
        Sort.Order.asc("orderNumber")
    );

Orders are sorted by the earliest delivery date first; on the same date, higher-priority orders come first; if still tied, orderNumber ascending.

### Using Sort.and

You can chain Sort instances:

    Sort primary = Sort.by(
        Sort.Order.desc("updatedAt")
    );

    Sort tieBreaker = Sort.by(
        Sort.Order.asc("productId")
    );

    Sort combined = primary.and(tieBreaker);

This approach is useful when a primary sort is reused and each use case adds its own tie-breaker condition.

## 6. Sort.unsorted and Pageable

If no sorting is needed, you can use:

    Sort sort = Sort.unsorted();

With Pageable:

    Pageable pageable = PageRequest.of(0, 20);

A PageRequest without a Sort represents the page and page size without requesting a specific sort order.

You should not rely on arbitrary order or internal shard order if the UI requires a meaningful order. When users paginate, stable sorting is especially important.

## 7. What Is Pageable?

Pageable is an interface describing a pagination request. It contains:

- page number: zero-based page index.
- page size: maximum number of elements in a page.
- offset: starting position in the result set.
- sort: sorting order.

PageRequest is the commonly used implementation:

    Pageable pageable = PageRequest.of(0, 20);

    Pageable secondPage = PageRequest.of(1, 20);

    Pageable thirdPage = PageRequest.of(2, 20);

With a page size of 20:

| Page number | Offset | Result slice |
|---:|---:|---|
| 0 | 0 | Documents 1 to 20 |
| 1 | 20 | Documents 21 to 40 |
| 2 | 40 | Documents 41 to 60 |

Offset is calculated as page number multiplied by page size. Page numbers start at 0, not 1. If an external API accepts 1-based page numbers, the service or controller needs to convert them before creating a PageRequest.

### Creating Pageable with Sort

You can pass Sort directly:

    Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.asc("name")
        )
    );

Or create the Pageable first and then replace the Sort:

    Pageable pageable = PageRequest.of(0, 20)
        .withSort(Sort.by(Sort.Order.desc("createdAt")));

When sort is part of an API, you should construct the Pageable at the request-handling layer and pass it through the service to the repository or ElasticsearchOperations.

### Validating Pagination Parameters

PageRequest requires a non-negative page number and a page size greater than 0. You should not pass client-supplied page/size directly without bounds:

    int page = Math.max(requestedPage, 0);
    int size = Math.min(Math.max(requestedSize, 1), 100);

    Pageable pageable = PageRequest.of(page, size);

The example above caps page size at 100 to prevent requests from returning excessively large payloads. The actual limit should fit the API and document size.

## 8. Using Pageable in ElasticsearchRepository

Spring Data Elasticsearch repositories support methods that accept Pageable.

For example:

    public interface ProductRepository
            extends ElasticsearchRepository<Product, String> {

        Page<Product> findByCategory(
            String category,
            Pageable pageable
        );
    }

Service:

    @Service
    public class ProductService {

        private final ProductRepository repository;

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        public Page<Product> findCategory(
                String category,
                int page,
                int size) {

            Pageable pageable = PageRequest.of(
                page,
                size,
                Sort.by(Sort.Order.desc("createdAt"))
            );

            return repository.findByCategory(category, pageable);
        }
    }

The repository method finds products belonging to the category and applies the passed-in pagination and sort.

Pageable can also be used with findAll:

    Page<Product> products =
        productRepository.findAll(
            PageRequest.of(
                0,
                20,
                Sort.by(Sort.Order.asc("name"))
            )
        );

Derived query methods can also accept Pageable:

    Page<Product> findByStatus(
        ProductStatus status,
        Pageable pageable
    );

Field names in the method and sort must match the entity metadata and actual mapping.

## 9. Reading Page and Pagination Metadata

Page<T> contains the page content along with summary metadata:

    Page<Product> page =
        productRepository.findAll(pageable);

    List<Product> products = page.getContent();
    int currentPage = page.getNumber();
    int pageSize = page.getSize();
    long totalElements = page.getTotalElements();
    int totalPages = page.getTotalPages();
    boolean hasNext = page.hasNext();
    boolean hasPrevious = page.hasPrevious();

Commonly used methods:

| Method | Meaning |
|---|---|
| getContent() | List of elements in the page |
| getNumber() | Current page index |
| getSize() | Requested page size |
| getNumberOfElements() | Actual number of elements in the page |
| getTotalElements() | Total number of elements according to query metadata |
| getTotalPages() | Total number of pages |
| hasNext() | Whether there is a next page |
| hasPrevious() | Whether there is a previous page |
| isFirst() / isLast() | Whether the current page is the first/last page |

Page is suitable when the UI needs to display the total number of results or total pages. However, obtaining exact total hits can consume additional resources depending on the query and Elasticsearch configuration.

If the UI only needs to know whether more data is available to load, consider Slice or a lighter response if supported appropriately by the repository/API in use. Do not compute total pages if the UI does not need them.

## 10. Which Fields Can Be Sorted in Elasticsearch?

Not every field is suitable for sorting. Elasticsearch needs a storage structure that allows reading field values efficiently during sorting.

Commonly used field types:

| Mapping type | Suitable for sorting? | Notes |
|---|---|---|
| keyword | Yes | Commonly used for normalized names, codes, statuses |
| long, integer, double, float | Yes | Suitable for prices, quantities, scores |
| date, date_nanos | Yes | Suitable for timestamps |
| boolean | Yes | Can sort by boolean value |
| text | Usually no | text fields do not have doc values by default; direct sorting is usually rejected |
| geo_point | Yes, via geo-distance sort | Requires appropriate geo sort configuration |

Elasticsearch typically uses doc values to support sorting, aggregations, and per-document field value access. Keyword and common scalar types usually enable doc_values by default. Text fields usually do not enable doc_values because they are optimized for full-text search.

### Do Not Sort Directly on a text Field

Mapping:

    PUT products
    {
      "mappings": {
        "properties": {
          "name": {
            "type": "text"
          },
          "price": {
            "type": "double"
          },
          "createdAt": {
            "type": "date"
          }
        }
      }
    }

If you sort directly on name, Elasticsearch may return an error because text fields do not support sorting in the standard way. Text fields are analyzed into tokens and are unsuitable for whole-string ordering.

You should declare a multi-field:

    PUT products
    {
      "mappings": {
        "properties": {
          "name": {
            "type": "text",
            "fields": {
              "keyword": {
                "type": "keyword"
              }
            }
          }
        }
      }
    }

Then use name.keyword for sorting:

    Sort sort = Sort.by(
        Sort.Order.asc("name.keyword")
    );

With Spring Data entities, property names and actual field names can be mapped via metadata. If using a raw field path in a native sort, specify the exact actual mapping name.

### Keyword Normalizer for Case-Insensitive Sorting

Keyword fields normally preserve the exact string. If case-insensitive ordering is needed, you can declare a normalizer on the keyword field:

    PUT products
    {
      "settings": {
        "analysis": {
          "normalizer": {
            "lowercase_normalizer": {
              "type": "custom",
              "filter": [ "lowercase" ]
            }
          }
        }
      },
      "mappings": {
        "properties": {
          "name": {
            "type": "text",
            "fields": {
              "sort": {
                "type": "keyword",
                "normalizer": "lowercase_normalizer"
              }
            }
          }
        }
      }
    }

Then sort by name.sort. The normalizer is applied when indexing the keyword value and produces a more consistent order for strings that differ in casing.

Do not assume Sort.Order.ignoreCase() automatically replaces mapping design. With Elasticsearch, a normalizer on a keyword field is the explicit way to define sort semantics.

## 11. Sorting by a Field Mapped with @Field

A Java entity can use a property name that differs from the Elasticsearch field name:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        @Field(name = "created_at", type = FieldType.Date)
        private Instant createdAt;

        @Field(type = FieldType.Double)
        private Double price;
    }

In Spring Data code, you should generally use the entity property name in Sort:

    Sort sort = Sort.by(
        Sort.Order.desc("createdAt")
    );

Spring Data's mapping metadata can translate the property name to the corresponding Elasticsearch field name when processing the query. With native sort or requests built directly with the Java API Client, you must use the exact Elasticsearch field name—in this example, created_at.

This distinction should be kept in mind when using:

- Spring Data Sort tied to entity metadata.
- Native sort options of the Elasticsearch Java API Client referencing fields in the Elasticsearch mapping.

If sorting does not behave as expected, inspect the final generated DSL request and the actual mapping rather than only looking at the Java property name.

## 12. Sorting by Search Score

For full-text search, Elasticsearch normally ranks by _score descending when no other sort is specified. If you want to explicitly include relevance in the sort list, you can use the _score field:

    Sort sort = Sort.by(
        Sort.Order.desc("_score")
    );

If you need a tie-breaker when scores are equal:

    Sort sort = Sort.by(
        Sort.Order.desc("_score"),
        Sort.Order.asc("productId")
    );

productId here should be a keyword field with doc values and unique or near-unique values across the dataset.

Sorting by another field such as price or createdAt changes the role of relevance. For example, sorting by price ascending prioritizes lower prices even for documents with lower text scores. Decide clearly what the API needs:

- Relevance first, secondary field used only when scores tie.
- Business field as the primary order.
- Combining score and fields in a specific order.

## 13. Missing Values and Null Values When Sorting

A document may lack the field used for sorting. Elasticsearch allows configuring missing values in sort options, such as placing missing values at the beginning or end of the list.

REST API:

    GET products/_search
    {
      "sort": [
        {
          "price": {
            "order": "asc",
            "missing": "_last"
          }
        }
      ]
    }

With this configuration, products without a price are placed last when sorting ascending.

Spring Data Sort.Order has null-handling metadata, but how it is translated to the backend depends on the implementation and version. If exact missing behavior is required, verify Spring Data Elasticsearch support or use native SortOptions to declare missing explicitly.

Do not treat missing values as 0 if 0 has actual business meaning. For example, a product without a price should not automatically appear first when sorting price ascending just because the application defaults missing prices to 0.

## 14. Sorting on Multi-Valued Fields in a Document

A field can contain multiple values, for example:

    {
      "name": "Keyboard",
      "offers": [ 40.0, 45.0, 50.0 ]
    }

When sorting on a multi-valued field, Elasticsearch needs a rule to pick a representative value. Common modes:

| Mode | Meaning |
|---|---|
| min | Use the smallest value |
| max | Use the largest value |
| sum | Sum the values |
| avg | Take the average |
| median | Take the median |

Example of sorting by the lowest offer price:

    GET products/_search
    {
      "sort": [
        {
          "offers": {
            "order": "asc",
            "mode": "min"
          }
        }
      ]
    }

With descending sort, the default mode typically depends on the sort direction; if a specific business behavior is required, declare mode explicitly.

Sort mode for multi-valued fields is not an arbitrary business aggregation mechanism. If the representative value requires custom semantics, store a precomputed numeric field or use a script sort only when truly necessary.

## 15. Nested Sort

When data uses a nested mapping, sorting on a field inside a nested object requires specifying the nested path and possibly a filter.

Example mapping:

    PUT products
    {
      "mappings": {
        "properties": {
          "offers": {
            "type": "nested",
            "properties": {
              "seller": {
                "type": "keyword"
              },
              "price": {
                "type": "double"
              }
            }
          }
        }
      }
    }

Sorting by the lowest price in offers:

    GET products/_search
    {
      "sort": [
        {
          "offers.price": {
            "order": "asc",
            "mode": "min",
            "nested": {
              "path": "offers"
            }
          }
        }
      ]
    }

If you only want to sort by offers from a specific seller, the nested sort can include a filter to consider only nested documents matching the condition. In that case, the sort clause must declare the exact nested path and filter.

Standard Spring Data Sort cannot fully express all nested sort options. For nested sorts, you typically need NativeQuery and Elasticsearch Java API Client SortOptions or a specialized API provided by your Spring Data version.

## 16. Using Pageable with ElasticsearchOperations

Repositories are not the only place Pageable is used. When a service builds a NativeQuery, you can attach Pageable using withPageable:

    Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.asc("name")
        )
    );

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .match(m -> m
                .field("name")
                .query("keyboard")
            )
        )
        .withPageable(pageable)
        .build();

    SearchHits<Product> hits =
        operations.search(query, Product.class);

withPageable passes the Pageable's offset, size, and sort into the query. ElasticsearchOperations executes the query and returns SearchHits.

SearchHits contains the hits and metadata such as score, id, and total hits. You can extract the content:

    List<Product> products = hits.getSearchHits()
        .stream()
        .map(SearchHit::getContent)
        .toList();

If the Page abstraction is needed, Spring Data provides utilities to convert SearchHits into SearchPage in the appropriate APIs. Use the utilities and result types appropriate to your installed version; SearchHits is not automatically synonymous with Page.

## 17. Sorting in NativeQuery Using Elasticsearch SortOptions

Spring Data Sort is sufficient for most simple sorts. When you need specialized options such as missing, nested path, mode, unmapped_type, or geo distance, you can build native sort options using the Elasticsearch Java API Client.

Example of sorting by price and placing missing fields last:

    import co.elastic.clients.elasticsearch._types.SortOptions;
    import co.elastic.clients.elasticsearch._types.SortOrder;

    SortOptions priceSort = SortOptions.of(s -> s
        .field(f -> f
            .field("price")
            .order(SortOrder.Asc)
            .missing("_last")
        )
    );

Then attach it to NativeQuery using the corresponding sort API:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .match(m -> m
                .field("name")
                .query("keyboard")
            )
        )
        .withSort(priceSort)
        .withPageable(PageRequest.of(0, 20))
        .build();

Builder method names and overloads may vary across Spring Data Elasticsearch / Java API Client versions. Confirm the exact signatures in your project dependencies. When using native SortOptions, field names must match the Elasticsearch mapping; they are not translated from Java property names via entity metadata by default as with Spring Data Sort.

If you set both a sort inside Pageable and a separate native sort, determine the precedence and behavior of the API version you are using. Avoid configuring two different sort lists unless clearly intended.

## 18. Sorting and Deep Pagination Limits

Elasticsearch commonly uses from/size for standard pagination. For example:

    GET products/_search
    {
      "from": 100,
      "size": 20,
      "sort": [
        { "created_at": "desc" }
      ]
    }

from is the number of documents to skip, and size is the number of documents to retrieve. With PageRequest, Spring Data calculates the offset from page number and page size and translates it into from/size.

By default, Elasticsearch limits the total result window accessible via from/size through index.max_result_window, typically 10,000. If users request very deep pages, increasing the page number can hit this limit and incur high memory and CPU costs.

For example:

    PageRequest.of(500, 20)

has an offset of 10,000. This is a common default boundary of the result window.

You should not increase max_result_window indefinitely to solve deep pagination. Elasticsearch must track and process the skipped results on every shard, so cost grows as offset increases.

### search_after for Deep Pagination

search_after uses the sort values of the last hit from the previous page to fetch the next page. Instead of skipping thousands of documents, the next request continues after the known sort position.

Example first request:

    GET products/_search
    {
      "size": 20,
      "sort": [
        { "created_at": "desc" },
        { "product_id": "asc" }
      ],
      "query": {
        "match": {
          "name": "keyboard"
        }
      }
    }

Suppose the last hit has sort values:

    "sort": [
      1794564000000,
      "p-1020"
    ]

The next request passes those exact values:

    GET products/_search
    {
      "size": 20,
      "sort": [
        { "created_at": "desc" },
        { "product_id": "asc" }
      ],
      "search_after": [
        1794564000000,
        "p-1020"
      ],
      "query": {
        "match": {
          "name": "keyboard"
        }
      }
    }

Values in search_after must come from the sort array of the last hit of the previous page and preserve their exact types and order. The sort should have a stable tie-breaker so two documents do not share identical full sort values.

### PIT Combined with search_after

If data changes while a user paginates through multiple pages, subsequent page results can be affected by inserts, updates, or deletes. Point in Time (PIT) preserves a consistent view for a period of time and is commonly combined with search_after for deep pagination.

General flow:

1. Open a PIT on the index or alias.
2. Send the first search with the PIT, query, and stable sort.
3. Save the sort values of the last hit.
4. Send the next request with the same PIT and search_after.
5. Continue until data is exhausted or close the PIT.

PIT holds cluster resources while open, so configure an appropriate keep_alive and close the PIT when finished if required by the API/client.

Standard Pageable primarily describes offset and size. It does not inherently represent the full cursor state of search_after/PIT. For deep pagination, use the appropriate Elasticsearch API or design a dedicated cursor rather than forcing search_after into a page number.

## 19. Stable Ordering and Tie-Breakers

If multiple documents share the same sort value, Elasticsearch may return them in an internal order that is not guaranteed to remain stable across requests. This easily causes:

- A document appearing on two pages.
- A document being skipped when data changes.
- Page order changing between calls.

The solution is to add a tie-breaker field with unique or sufficiently distinct values:

    Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("productId")
    );

productId should have a keyword mapping and doc values for efficient sorting. You should not assume sorting directly on _id is a good choice; the _id field has its own limitations and is not designed for general sorting. You can store a copy of the identifier in a dedicated keyword field for sorting.

With search_after, a tie-breaker is even more important because it pinpoints the exact continuation position.

## 20. Sorting Across Different Data Types

### Price and Quantity

Numeric fields are suitable for numeric ordering:

    Sort priceAscending =
        Sort.by(Sort.Order.asc("price"));

Ensure the mapping is integer, long, float, double, or another appropriate numeric type. If price is stored as keyword, sorting follows lexicographical string order—for example, "100" may come before "20", rather than numeric order.

### Date and Time

Date fields support chronological sorting:

    Sort newestFirst =
        Sort.by(Sort.Order.desc("createdAt"));

Store timestamps as a date type and standardize timezones. If one index uses date and another uses an incompatible type, sorting across an alias or multiple indices may fail.

### Keyword

Keyword is suitable for codes, statuses, or normalized names:

    Sort alphabetical =
        Sort.by(Sort.Order.asc("name.keyword"));

String order is based on the keyword value and normalization rules, not necessarily natural language dictionary order.

### Boolean

Boolean can be used for flags such as featured or active. However, if the business requirement is to group true values first and then sort by another field, verify the boolean ordering explicitly and append subsequent Orders.

## 21. Combining Filter, Query, and Sort

Sort only determines the order of documents already selected by the query. It does not replace filtering.

Example of finding active products in the accessories category, sorted with the most recently updated first:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .bool(b -> b
                .must(m -> m
                    .match(mm -> mm
                        .field("name")
                        .query(keyword)
                    )
                )
                .filter(f -> f
                    .term(t -> t
                        .field("status")
                        .value(FieldValue.of("ACTIVE"))
                    )
                )
                .filter(f -> f
                    .term(t -> t
                        .field("category")
                        .value(FieldValue.of("accessories"))
                    )
                )
            )
        )
        .withPageable(PageRequest.of(
            0,
            20,
            Sort.by(
                Sort.Order.desc("updatedAt"),
                Sort.Order.asc("productId")
            )
        ))
        .build();

In this example:

- must searches against the product name content.
- filter restricts status and category.
- Sort prioritizes the newest updatedAt.
- productId is the tie-breaker.
- Pageable limits to the first 20 results.

If relevance should be the primary criterion, you can sort by _score descending first, followed by updatedAt or productId. If updatedAt comes first, newer documents may appear ahead of documents with higher content relevance scores.

## 22. Pageable in a REST API

A REST API commonly receives page, size, and sort from query parameters:

    GET /api/products?page=0&size=20&sort=createdAt,desc

Spring MVC can automatically bind Pageable if Spring Data web support is appropriately configured. However, with Elasticsearch, the application should still cap page size and whitelist allowed sort fields.

You should not let clients send arbitrary field names for sorting:

    GET /api/products?sort=internal_score,desc

If a field is not meant to be public, letting clients sort on it can leak internal signals or trigger expensive queries. Map public sort choices explicitly:

    switch (sortBy) {
        case "newest" ->
            Sort.by(Sort.Order.desc("createdAt"));
        case "price-low" ->
            Sort.by(Sort.Order.asc("price"));
        case "price-high" ->
            Sort.by(Sort.Order.desc("price"));
        case "name" ->
            Sort.by(Sort.Order.asc("name.keyword"));
        default ->
            Sort.by(Sort.Order.desc("createdAt"));
    }

This example shows how to map business choices to Sort. Field names must correspond to the actual mapping and options must be controlled.

## 23. Sorting and Pagination with Page, Slice, or List

Different return types provide different amounts of metadata:

| Return type | Content | Total metadata |
|---|---|---|
| Page<T> | Current page content | Includes total elements/pages |
| Slice<T> | Content and whether there is a next page | Does not require total pages |
| List<T> | Bounded list of results | No page metadata |
| SearchHits<T> | Hits with scores and Elasticsearch metadata | Includes total hits from response |

Page is useful when the UI needs the total number of pages. Slice fits Next/Load more buttons when counting all results is unnecessary. List fits a bounded subset of data. SearchHits fits when scores, highlights, or specialized metadata are needed.

Support for each return type depends on the repository abstraction and Spring Data Elasticsearch version. Choose method signatures supported by the framework; do not assume every Spring Data JPA return type has identical semantics on Elasticsearch.

## 24. Performance and Limitations of Sorting

Sorting has a cost because Elasticsearch must read field values from candidate documents and sort them. Key principles:

- Sorting on keyword/numeric/date fields with doc values is generally appropriate.
- Avoid sorting on analyzed text fields.
- Limit the number of sort fields.
- Avoid script sorts if the value to sort by can be pre-stored.
- Narrow the candidate set using appropriate queries/filters.
- Use reasonable page sizes.
- Avoid overly deep offsets.
- Use search_after/PIT when traversing large datasets.
- Ensure indices behind an alias have compatible mappings for sort fields.

If a field is only used for sorting, consider an appropriate mapping and doc_values. Do not disable doc_values for fields needed in sorting or aggregations.

### Sorting on a Field Missing in Some Indices

If querying through an alias pointing to multiple indices and the sort field does not exist or has different types across indices, Elasticsearch may return an error or inconsistent results.

When using multiple indices:

- Keep the sort field mapping consistent.
- If needed, configure unmapped_type in native sort to handle indices missing the field.
- Verify field types across all backing indices.
- Avoid sorting on fields with different semantics across index versions.

## 25. Testing Sort and Pageable

A useful test should verify both ordering and pagination, not just that results are returned.

Example dataset:

| ID | Price | CreatedAt |
|---|---:|---|
| p-1 | 100 | 2026-11-01 |
| p-2 | 50 | 2026-11-03 |
| p-3 | 75 | 2026-11-02 |

Ascending price sort must produce the order p-2, p-3, p-1.

With page size 2:

- Page 0 has p-2 and p-3.
- Page 1 has p-1.

Tests should verify:

- ASC/DESC direction.
- Priority order when multiple Orders are present.
- Tie-breaker when sort values are equal.
- Documents missing the sort field.
- Proper text/keyword field mapping.
- Page number and size.
- Total elements/pages if using Page.
- Behavior when page exceeds the last page.

Integration tests against an actual Elasticsearch instance help catch mapping and sort DSL bugs that unit tests mocking the repository cannot detect.

## 26. Common Pitfalls

### Sorting directly on a text field

Text fields are analyzed and typically lack doc values. Use a keyword sub-field such as name.keyword for string sorting.

### Confusing Java property names with mapping fields in native sort

Spring Data Sort can use mapping metadata to translate properties to field names. Native SortOptions reference Elasticsearch field names directly. Check the actual mapping and generated request.

### Forgetting the sort direction

Sort.by("price") defaults to ascending. If business logic requires highest price first, specify DESC explicitly.

### Ordering multiple Order instances incorrectly

The first Order has the highest priority. Arrange criteria in business priority order.

### Omitting a tie-breaker

Multiple documents with the same sort value can change order between requests. Add a unique, stable, sortable field.

### Using _id as a default tie-breaker

_id has specific limitations and is not a general sort field optimized for this use case. Store an additional keyword field with doc values for sorting.

### Using Pageable for deep pagination

PageRequest uses offset/size and can hit max_result_window. Use search_after with PIT for deep traversal requiring consistency.

### Allowing clients to sort arbitrarily

Clients may request sorting on internal or expensive fields. Whitelist the sort options exposed by the public API.

### Assuming Sort replaces filtering

Sort only changes order. Ineligible documents must be excluded via query/filter or authorization.

### Inconsistent mappings across indices

Multi-index aliases require sort fields with compatible types and semantics. If mappings diverge, queries can fail or yield wrong results.

## 27. Workflow for Choosing Sort and Pageable

When designing a search endpoint, you can follow this sequence:

1. Determine which query and filters select the valid document set.
2. Determine the business order: relevance, newest, price, name, or priority.
3. Choose fields whose mappings support sorting.
4. If string sorting is needed, use keyword or a keyword sub-field.
5. Build Sort with one or more Sort.Order instances in the right priority order.
6. Add a stable tie-breaker if users paginate.
7. Create Pageable with bounded page number and page size.
8. Pass Pageable to a repository or NativeQuery.
9. Choose Page, Slice, List, or SearchHits based on the required metadata.
10. For deep offsets, switch to search_after/PIT.
11. Verify the actual request and mapping with integration tests.

## Conclusion

Sort and Sort.Order describe sorting order; Pageable combines page number, page size, offset, and sort. In Spring Data Elasticsearch, you can pass Pageable to repository methods or attach it to NativeQuery using withPageable. Multi-field sorting is applied in the order of Orders, so the first field is the primary criterion.

Elasticsearch requires appropriate field mappings for sorting: keyword for strings, numeric for numbers, and date for timestamps. For text fields, use a keyword sub-field; for nested sorting or special missing-value rules, consider native SortOptions. Add a stable tie-breaker so pagination is less prone to duplicates or skipped items, cap page sizes, and avoid deep offsets exceeding max_result_window. When large datasets must be traversed, search_after combined with PIT is a better fit than standard offset-based Pageable.
