# Query Parameters and Choosing Between CriteriaQuery, StringQuery, and NativeQuery

## 1. Query in Spring Data Elasticsearch

When you need to search for multiple documents, Spring Data Elasticsearch provides `ElasticsearchOperations` and `SearchOperations`. Search methods accept a `Query` object describing what to search for along with execution options such as pagination, sorting, and result limits.

`Query` in Spring Data Elasticsearch is an abstraction in the Spring Data layer. It is distinct from the `Query` type in the Elasticsearch Java API Client. Three common ways to construct a query are:

- **CriteriaQuery:** builds conditions using a fluent Criteria API without writing JSON Query DSL manually.
- **StringQuery:** passes Elasticsearch Query DSL directly as a JSON string.
- **NativeQuery:** builds queries using query types from the Elasticsearch Java API Client.

Basic execution flow:

~~~text
Service
  |
  v
ElasticsearchOperations.search(query, ...)
  |
  v
Spring Data SearchOperations
  |
  v
Convert Query to Elasticsearch request
  |
  v
Elasticsearch cluster
  |
  v
SearchHits<T>
~~~

The same requirement—finding products by name, category, and price—can be expressed with all three implementations. Which one to choose depends on complexity, how much Query DSL control is needed, and how dynamic the search criteria are.

## 2. Passing Query to ElasticsearchOperations

`ElasticsearchOperations` combines document and search operations. For searching, you can call `search` with a query, entity type, and index coordinates:

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.query.Query;

public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<Product> search(Query query) {
        return operations.search(
            query,
            Product.class,
            IndexCoordinates.of("products")
        );
    }
}
~~~

Parameters of the call:

- `query` describes the search conditions and accompanying options.
- `Product.class` is the Java type into which returned documents will be mapped.
- `IndexCoordinates.of("products")` is the index or alias that the request will query.

If the entity has `@Document(indexName = "...")` metadata, some overloads can obtain the index from entity metadata. Passing `IndexCoordinates` explicitly is useful when a service works with aliases or indices selected at runtime.

`Query` represents the search request specification. `ElasticsearchOperations` translates the query into an appropriate client request, sends it, and maps the results into `SearchHits`.

## 3. Common Query Parameters

A Query does not only hold filter conditions. It can also carry options controlling the results and how Elasticsearch executes the search.

| Parameter or Option | Purpose | When to Use |
|---|---|---|
| `Pageable` | Specifies page, page size, and optionally sort | Result list UI |
| `Sort` | Sorts by one or more fields | Price ascending, newest date, name |
| `SourceFilter` | Includes only specific fields from `_source` or excludes fields | Reduce returned payload when entities are large |
| Fields / stored fields | Requests returning specific fields | When specific field values need to be fetched |
| `trackTotalHits` | Asks Elasticsearch to track the exact total hit count | When the UI needs an exact total result count |
| `trackTotalHitsUpTo` | Caps the threshold for tracking total hits | When you only need counts up to a threshold |
| `minScore` | Keeps only hits with a minimum relevance score | Filter out results with very low relevance |
| `timeout` | Limits search execution time on the Elasticsearch side | Queries that require an execution time bound |
| `preference` | Hints preferred shard copies/nodes to handle the request | When shard selection stability or locality is needed |
| `routing` | Routes search to the corresponding shard | When the system uses custom routing |
| `searchAfter` | Continues fetching the next page from the previous page's sort values | Deep pagination |
| `highlight` | Requests text snippets matching the query | Highlighting keywords in results |

Not every option is configured the same way across every version or every `Query` implementation. Current APIs provide methods such as `setPageable`, `addSort`, `addSourceFilter`, `setTrackTotalHits`, `setTrackTotalHitsUpTo`, `setPreference`, `setSearchAfter`, and `setHighlightQuery`. Other options are declared on `BaseQuery` or through `NativeQuery`'s builder.

### Pagination and Sorting

You can set `Pageable` directly on the query:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.asc("price"),
        Sort.Order.desc("name")
    )
);

query.setPageable(pageable);
~~~

Pages are zero-indexed (`0`). The example above fetches up to the first 20 results, sorted by ascending price and then descending name.

If the query already has a `Pageable` containing a sort, do not add the same sort again. You can use `addSort` when you want to append sorting according to your version's API.

### Tracking Total Hits

Elasticsearch may cap total-hit tracking to save resources. If the UI genuinely needs the exact total number of results, you can request it:

~~~java
query.setTrackTotalHits(true);
~~~

If you only need to know counts up to a threshold, use `trackTotalHitsUpTo` according to your version's API. Requesting exact totals can consume extra resources on large datasets; only enable it when business logic requires it.

### Limiting Returned Data

Source filtering allows selecting specific fields from `_source` or excluding unnecessary fields. This is useful when documents carry heavy metadata or large fields while the screen only needs name, price, and category.

Distinguish source filtering from stored fields. Source filtering selects portions of data inside `_source`; stored fields request fields configured to be stored separately in the index. Not every field can be returned via stored fields just by specifying its name.

### Deep Pagination with search_after

`from` and `size` are suited for initial pages. When paging deeply through many results, cost and the result window limit can become issues. `search_after` uses the sort values of the last hit on the previous page to fetch the next page.

Spring Data Query provides `setSearchAfter(...)`. Values passed in must come from `SearchHit.getSortValues()` of the previous result, and the subsequent query must keep the same sort order. For a consistent result set while data changes, consider combining with Point in Time according to your Elasticsearch and Spring Data versions.

## 4. CriteriaQuery: Building Queries with Criteria

`CriteriaQuery` is suitable when search conditions can be expressed using familiar operators such as equals, greater than, less than, in list, contains string, or AND/OR combinations. The author does not have to write JSON Query DSL manually.

Suppose the product entity has these fields:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private Double price;

    @Field(type = FieldType.Boolean)
    private Boolean active;

    // Constructors, getters, and setters
}
~~~

Finding products with an exact price:

~~~java
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Criteria criteria = new Criteria("price").is(42.0);
Query query = new CriteriaQuery(criteria);
~~~

Finding products in category `audio` with a price not exceeding 2,000,000:

~~~java
Criteria criteria = new Criteria("category").is("audio")
    .and("price").lessThanEqual(2_000_000);

Query query = new CriteriaQuery(criteria);
~~~

`and("price")` chains the price condition onto the Criteria chain. Conditions are combined using AND logic.

### Combining AND and OR

By default, when chaining Criteria with `and`, all conditions must be satisfied together. With `or`, any one of the branches can match.

Example finding products in category `audio` with brand `Acme` or `Contoso`:

~~~java
Criteria brandCriteria = new Criteria()
    .or("brand").is("Acme")
    .or("brand").is("Contoso");

Criteria criteria = new Criteria("category").is("audio")
    .subCriteria(brandCriteria);

Query query = new CriteriaQuery(criteria);
~~~

The condition above can be understood as:

~~~text
category = "audio"
AND
(brand = "Acme" OR brand = "Contoso")
~~~

In Elasticsearch Query DSL, AND typically translates to `bool.must`, while OR translates to `bool.should`. When expressions have multiple logical levels, use `subCriteria` to make condition grouping explicit and inspect the generated query if grouping order affects business behavior.

### Common Criteria Operators

| Operator | Example | Meaning |
|---|---|---|
| Equals | `is("audio")` | Value equals the supplied value |
| Not equals | `not().is("audio")` | Negates the condition |
| Greater than | `greaterThan(100)` | Value is greater |
| Greater than or equal | `greaterThanEqual(100)` | Value is at least |
| Less than | `lessThan(100)` | Value is smaller |
| Less than or equal | `lessThanEqual(100)` | Value does not exceed |
| Between | `between(10, 20)` | Within the range |
| In list | `in("audio", "video")` | Matches one of the values in the list |
| Has value | `exists()` | Field has an indexed value |
| Contains string | `contains("wireless")` | Contains-style condition via Criteria API |
| Starts with | `startsWith("pro")` | Prefix condition |
| Ends with | `endsWith("phone")` | Suffix condition |
| Fuzzy | `fuzzy("wirless")` | Approximate match as supported by Criteria |

Not every operator suits every field type. For example, `in` creates a terms query so it is usually appropriate for `keyword` fields and should not be used on text fields transformed by an analyzer. Operations like contains or wildcards can cause expensive queries, especially with leading wildcards. Choose mappings and operators according to real data.

### When is CriteriaQuery Suitable?

CriteriaQuery is a good choice when:

- Conditions are simple business filters.
- You want to construct queries based on which parameters are present or absent.
- You want readable code without writing JSON.
- Criteria operators are sufficient to describe the requirement.
- The query does not need specialized Elasticsearch features.

CriteriaQuery is not intended to replace all of Query DSL. If you need complex queries such as nested queries, scripts, vector search, or an intricate DSL combination, NativeQuery is usually more appropriate.

## 5. StringQuery: Passing Query DSL as JSON

`StringQuery` takes a JSON string containing the Elasticsearch query section. This approach fits when you already have a clear Query DSL or want to keep JSON queries close to Elasticsearch documentation.

Example finding products by name:

~~~java
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.StringQuery;

Query query = new StringQuery("""
{
  "match": {
    "name": {
      "query": "wireless headphones"
    }
  }
}
""");
~~~

Searching by name and filtering by category and price range:

~~~java
Query query = new StringQuery("""
{
  "bool": {
    "must": [
      {
        "match": {
          "name": {
            "query": "wireless headphones"
          }
        }
      }
    ],
    "filter": [
      {
        "term": {
          "category": "audio"
        }
      },
      {
        "range": {
          "price": {
            "lte": 2000000
          }
        }
      }
    ]
  }
}
""");
~~~

In this example:

- `match` performs full-text search on the `name` field.
- `must` holds the query condition that can affect the relevance score.
- `filter` filters by category and price without using those conditions for relevance scoring.
- `term` suits a keyword field.
- `range` filters by price range.

After creating a `StringQuery`, you can still attach pagination or sorting options through the `Query` API:

~~~java
query.setPageable(PageRequest.of(
    0,
    20,
    Sort.by(Sort.Direction.ASC, "price")
));
~~~

### StringQuery Does Not Bind Parameters Automatically Like Repository @Query

Distinguish between two mechanisms:

- `StringQuery` accepts a pre-built JSON Query DSL string.
- The `@Query` annotation on repositories supports placeholders like `?0`, `?1` to substitute method parameters.

Do not assume `StringQuery` automatically substitutes `?0` with Java values. If you need to generate JSON from input data, use a JSON serializer or a safe query-building mechanism. Never concatenate user strings directly into JSON because quotes, escape characters, or untrusted content can break the query or produce unintended queries.

### When is StringQuery Suitable?

- A JSON Query DSL already exists from a trusted source.
- You want to express the query exactly like an Elasticsearch request.
- You need a part of Query DSL that Criteria API cannot express conveniently.
- The query is relatively fixed and the team wants full control over the JSON.

The downside is that JSON is stored as a string, so syntax errors or wrong field names are usually discovered only when the query executes. Long strings are also harder to refactor and type-check compared to NativeQuery.

## 6. NativeQuery: Using Elasticsearch Java API Client Directly

`NativeQuery` is suitable for complex queries or capabilities that cannot be expressed conveniently with Criteria API. It uses query types from the Elasticsearch Java API Client, in package `co.elastic.clients.elasticsearch._types.query_dsl`.

Example finding products whose name matches `wireless headphones` and belonging to category `audio`:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withQuery(q -> q
        .bool(b -> b
            .must(m -> m
                .match(mm -> mm
                    .field("name")
                    .query("wireless headphones")
                )
            )
            .filter(f -> f
                .term(t -> t
                    .field("category")
                    .value(v -> v.stringValue("audio"))
                )
            )
        )
    )
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

In this example:

- `NativeQuery.builder()` creates Spring Data's builder.
- `withQuery(...)` takes a lambda to construct the query via the Elasticsearch Java API Client.
- `bool(...)` builds a bool query.
- `must(...)` contains the full-text match query.
- `filter(...)` contains the term query filtering by category.
- `withPageable(...)` configures result pagination.
- `build()` produces the completed query.

The key difference is that the code uses typed builders from the Java API Client. IDEs can provide autocomplete and the compiler checks types much better than writing long JSON strings in StringQuery.

### Combining Aggregations

NativeQuery is also suitable when aggregations are needed alongside a query:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Query query = NativeQuery.builder()
    .withQuery(q -> q
        .match(m -> m
            .field("name")
            .query("wireless")
        )
    )
    .withAggregation(
        "categories",
        Aggregation.of(a -> a
            .terms(t -> t
                .field("category")
                .size(10)
            )
        )
    )
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

The `categories` aggregation builds buckets by the `category` field. Aggregation results can be read from `SearchHits` via the aggregation metadata provided by Spring Data.

### Capabilities That Often Require NativeQuery

Depending on the Elasticsearch Java API Client and Spring Data Elasticsearch versions, NativeQuery can be used to construct:

- Bool queries with multiple `must`, `filter`, `should`, and `must_not` clauses.
- Nested queries.
- Geo queries.
- Script queries.
- Highlights.
- Aggregations.
- Suggestions.
- Other specialized queries supported by the Java API Client.

Not all Elasticsearch features have identical APIs across versions. Use the documentation for the exact dependency version in your project when constructing queries.

## 7. Comparing CriteriaQuery, StringQuery, and NativeQuery

All three implementations can be passed to `ElasticsearchOperations.search(...)`, but query creation and level of control differ.

| Criterion | CriteriaQuery | StringQuery | NativeQuery |
|---|---|---|---|
| Declaration style | Fluent Criteria API | JSON Query DSL string | Typed builder from Elasticsearch Java API Client |
| Required Query DSL knowledge | Low to medium | High | High |
| Compile-time type checking | Good for Java types and Criteria API | Low for JSON contents | Better thanks to typed builders |
| Readability for simple conditions | Very readable | Can be unnecessarily verbose | Can involve nested lambdas |
| Complex queries | Limited | Expressible in JSON | Expressible via Java API Client |
| Aggregations | Not the main choice | Possible via JSON query portion but requires request control | Directly supported via builder |
| Refactoring | Convenient with properties and Java code | Harder because JSON is a string | More convenient with typed APIs |
| Best suited for | Business filters and basic conditions | Existing JSON queries or fixed queries | Advanced queries, aggregations, and complex DSL |

You can choose using these guidelines:

- Start with CriteriaQuery if conditions are simple and fully supported by Criteria API.
- Use StringQuery when you already have JSON Query DSL and want to keep that structure intact.
- Use NativeQuery when you need advanced capabilities, aggregations, or typed builders from the Elasticsearch Java API Client.

There is no need to mix all three implementations in a single query. Choose the representation that best fits the query structure.

## 8. Executing Queries and Reading SearchHits

After building a query with any implementation, it can be executed with the same API:

~~~java
SearchHits<Product> searchHits = operations.search(
    query,
    Product.class,
    IndexCoordinates.of("products")
);
~~~

`SearchHits<Product>` contains more information than a plain list of entities. Each `SearchHit<Product>` can provide:

- Document ID.
- Relevance score (`score`).
- Sort values.
- Highlight fields.
- Mapped entity content.
- Inner hits if returned by the query.

Example extracting the entity list from results:

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;

List<Product> products = searchHits.getSearchHits()
    .stream()
    .map(SearchHit::getContent)
    .toList();
~~~

If you only extract `List<Product>`, the application may discard scores, sort values, highlights, and other metadata. When building a search page that needs to display highlighted text snippets or relevance scores, keep `SearchHits`/`SearchHit` to use the metadata.

## 9. Building Dynamic Queries from Input Parameters

In real applications, users may choose one or multiple filters. For example:

- Keyword may or may not be present.
- Category may be unselected.
- Maximum price may be empty.
- Active status may be true, false, or unfiltered.

CriteriaQuery is well suited for adding conditions for each present parameter:

~~~java
Criteria criteria = new Criteria();

if (keyword != null && !keyword.isBlank()) {
    criteria = criteria.and("name").matches(keyword);
}

if (category != null && !category.isBlank()) {
    criteria = criteria.and("category").is(category);
}

if (maxPrice != null) {
    criteria = criteria.and("price").lessThanEqual(maxPrice);
}

Query query = new CriteriaQuery(criteria);
query.setPageable(PageRequest.of(
    page,
    size,
    Sort.by(Sort.Direction.ASC, "price")
));
~~~

This example demonstrates assembling conditions. Choose Criteria operators compatible with the mapping: full-text search on `name` requires an appropriate analyzer and semantics; an `is` condition on `category` should target a keyword field.

If dynamic conditions require nested queries, scripts, aggregations, or complex bool branches, you can build a NativeQuery by adding each condition to the builder. This avoids manual JSON concatenation and keeps the query structured.

With StringQuery, if you must build dynamic JSON queries, use a JSON serializer to escape data properly. Never concatenate untrusted input into JSON Query DSL.

## 10. Pagination, Total Hits, and Result Limits

A query can have correct conditions yet still be unsuitable if it returns too many documents. Configure `Pageable`, sorting, and total hits according to UI needs.

Example:

~~~java
Pageable pageable = PageRequest.of(
    0,
    25,
    Sort.by(Sort.Direction.DESC, "createdAt")
);

query.setPageable(pageable);
query.setTrackTotalHits(false);
~~~

If a screen only displays the current page list and a "Load more" button, an exact total hit count is not strictly needed. If it must display "12,483 results found", evaluate the requirement for total-hit tracking.

For very large datasets, avoid deep `from` offsets. Use `search_after` with a stable sort. When using `search_after`, take the sort values from the last hit of the current page and pass them into the next query. Do not fabricate sort values manually because they must match the exact sort used.

## 11. Common Pitfalls When Building Queries

**Using the wrong field type.** `term` on an analyzed text field may not match as expected; `match` on a keyword field does not carry full-text semantics like on text. Check the mapping before choosing an operator.

**Confusing Spring Data's Query with Elasticsearch Java Client's Query.** `org.springframework.data.elasticsearch.core.query.Query` is the abstraction accepted by `ElasticsearchOperations`. `co.elastic.clients.elasticsearch._types.query_dsl.Query` is the query type in the Java API Client, usually constructed inside NativeQuery.

**Assuming StringQuery supports automatic placeholders.** StringQuery accepts a JSON query string. Placeholders like `?0` belong to certain repository declarations such as `@Query`, and do not automatically apply to StringQuery strings.

**Concatenating JSON directly from inputs.** Quotes, escape characters, or untrusted content can break JSON structure. Use Criteria, NativeQuery, or a JSON serializer.

**Using Criteria for queries beyond its capabilities.** When you need nested DSL, aggregations, scripts, or advanced queries, switch to NativeQuery rather than forcing an unreadable Criteria chain.

**Not grouping AND/OR clearly.** Chained Criteria default to AND; OR translates to should. Use subCriteria to group conditions and verify query logic.

**Omitting pagination.** Unbounded queries can load too many documents. Use Pageable or an appropriate deep pagination mechanism.

**Requesting exact total hits unnecessarily.** Tracking exact total hits can increase search cost. Enable it only when the UI or business logic actually requires it.

**Not testing queries against real Elasticsearch.** Code can compile yet the query can still fail due to mapping, analyzer, or data issues. Integration tests must verify actual results.

## 12. Workflow for Selecting and Building Queries

You can follow this sequence:

1. Identify the data to search and the mappings of the fields.
2. Categorize conditions into full-text, exact match, range, nested, or aggregation.
3. Choose CriteriaQuery if conditions are basic and clearly expressible with Criteria.
4. Choose StringQuery if you already have stable JSON Query DSL and want to pass that structure verbatim.
5. Choose NativeQuery if you need advanced Query DSL, aggregations, or typed builders.
6. Add Query options such as Pageable, Sort, source filtering, and total-hit tracking.
7. Call `ElasticsearchOperations.search(...)` with the entity type and index coordinates.
8. Read `SearchHits` if scores, sort values, highlights, or aggregations are needed.
9. Verify with integration tests against an Elasticsearch version compatible with the application.
10. Monitor execution time, result counts, and query cost on production-like data.

## Conclusion

`Query` is the abstraction that lets Spring Data Elasticsearch separate how searches are described from how requests are sent. `CriteriaQuery` provides a readable Criteria API for common conditions; `StringQuery` directly accepts Elasticsearch Query DSL as JSON; `NativeQuery` uses typed builders from the Elasticsearch Java API Client for complex queries and aggregations.

Beyond the query body, the Query object also carries execution parameters such as pagination, sorting, source filtering, total-hit tracking, preference, timeout, and search_after. Choosing the right implementation, configuring parameters properly, and reading `SearchHits` when metadata is needed keeps search code clear, performance controlled, and well aligned with Elasticsearch's capabilities.

## References

- [Spring Data Elasticsearch — Elasticsearch Operations and Queries](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Spring Data Elasticsearch — Query API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/Query.html)
- [Spring Data Elasticsearch — Criteria API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/core/query/Criteria.html)
- [Spring Data Elasticsearch — NativeQuery API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/client/elc/NativeQuery.html)
