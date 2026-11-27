# Building Queries with Builders and Lambda Expressions

In Spring Data Elasticsearch, NativeQuery lets you build queries using the Elasticsearch Java API Client. Instead of concatenating JSON query strings, the application uses strongly typed builders and lambda expressions to describe each part of the Query DSL.

A typical call looks like this:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .match(m -> m
                .field("name")
                .query("keyboard")
            )
        )
        .build();

Here, NativeQuery.builder() creates the Spring Data builder. withQuery takes a lambda to build an Elasticsearch Java API Client Query object. The lambda inside match configures a MatchQuery, and build() completes the NativeQuery object.

Builders and lambdas keep queries clearly structured, provide compile-time type checking, and make it straightforward to combine clauses such as bool, must, filter, range, sort, pagination, and aggregation.

## 1. Where Does NativeQuery Fit in Spring Data Elasticsearch?

Spring Data Elasticsearch offers multiple ways to express queries. Repository methods fit simple operations with clear naming patterns. CriteriaQuery provides a criteria-style API for common conditions. NativeQuery fits cases where you need direct control over the Elasticsearch Query DSL.

NativeQuery belongs to the package:

    import org.springframework.data.elasticsearch.client.elc.NativeQuery;

It is an implementation of the Query abstraction in Spring Data Elasticsearch, integrated with the Elasticsearch Java API Client. It allows passing query objects built by the Java client along with options like pagination, sort, aggregations, highlighting, and other query components supported by the Spring Data version.

You can distinguish the approaches as follows:

| Construction Approach | Purpose | When Appropriate |
|---|---|---|
| Repository derived query | Generate queries from method names | Simple conditions easily expressed by method name |
| CriteriaQuery | Build queries via criteria | Common conditions needing a Spring Data API |
| NativeQuery | Build Elasticsearch Query DSL with Java API Client | Complex queries or needing specific DSL features |
| Manual JSON query | Pass JSON content in suitable APIs | Special integrations or needing to preserve raw JSON queries |

The examples below use NativeQuery and the Elasticsearch Java API Client from modern Spring Data Elasticsearch releases. Older versions may use NativeSearchQuery, QueryBuilders, or the High Level REST Client. Avoid mixing APIs from both client generations in the same project.

## 2. How Do Builders and Lambdas Work Together?

A builder is an object that helps construct another object step by step. Each method configures a part of the object and typically returns the builder so calls can be chained.

A lambda is an expression passed into a method. In the Java API Client, builder methods typically accept a lambda whose parameter is the builder for the corresponding query type. The lambda configures that builder and returns it so the library can finalize the object.

Example:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .match(m -> m
                .field("name")
                .query("keyboard")
            )
        )
        .build();

You can read it from the outside in:

1. NativeQuery.builder() begins constructing a Spring Data NativeQuery.
2. withQuery(...) configures the main query section.
3. q is the Elasticsearch Query builder.
4. q.match(...) selects the match query variant.
5. m is the MatchQuery builder.
6. field("name") selects the search field.
7. query("keyboard") sets the keyword.
8. build() creates the completed NativeQuery.

Each lambda has its own scope. Variable names like q, m, and b are simply parameter names chosen by the developer; they are not special Elasticsearch keywords.

### Lambdas Do Not Execute the Query Immediately

The lambdas inside builders are used to configure the query object. When the NativeQuery creation code runs, it constructs the query structure in memory. Elasticsearch only receives and executes the query when the application calls operations.search(...), elasticsearchClient.search(...), or an equivalent execution API.

Therefore, distinguish between:

- **Building the query:** creating the Java structure describing the conditions.
- **Executing the query:** sending the request to Elasticsearch.
- **Reading results:** receiving the response and mapping documents into entities or result types.

Separating these three steps allows you to build a query in one method, pass it to another layer, unit-test its structure, or compose/reuse query parts before execution.

## 3. Basic match Query

Example searching products by name:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .match(m -> m
                .field("name")
                .query("mechanical keyboard")
            )
        )
        .build();

This query corresponds to the Elasticsearch DSL:

    {
      "query": {
        "match": {
          "name": "mechanical keyboard"
        }
      }
    }

match is suitable for text fields because Elasticsearch analyzes the search string using the field's analyzer. The keyword is broken into tokens and used to find matching documents.

If the field is keyword and exact matching is required, term is usually used instead of match. Query selection should be based on the mapping and search objective.

## 4. Distinguishing NativeQuery and Elasticsearch Java Client Query

There are two Query types that can easily cause confusion:

- org.springframework.data.elasticsearch.core.query.Query: Spring Data's query abstraction.
- co.elastic.clients.elasticsearch._types.query_dsl.Query: the query type provided by the Elasticsearch Java API Client.

NativeQuery is a Spring Data query type, while the lambda inside withQuery builds the Elasticsearch Java API Client query type.

Common imports:

    import co.elastic.clients.elasticsearch._types.FieldValue;
    import co.elastic.clients.elasticsearch._types.query_dsl.Query;
    import org.springframework.data.elasticsearch.client.elc.NativeQuery;
    import org.springframework.data.elasticsearch.core.SearchHits;
    import org.springframework.data.elasticsearch.core.ElasticsearchOperations;

In real code, you do not need to declare a Query variable if you only use an inline lambda inside withQuery. However, when extracting a query into a separate method, you can explicitly declare co.elastic.clients.elasticsearch._types.query_dsl.Query to avoid confusion with Spring Data's Query interface.

Example of creating a Java Client query first:

    co.elastic.clients.elasticsearch._types.query_dsl.Query nameQuery =
        co.elastic.clients.elasticsearch._types.query_dsl.Query.of(q -> q
            .match(m -> m
                .field("name")
                .query("keyboard")
            )
        );

    NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(nameQuery)
        .build();

Query.of(...) is a factory method on the Java Client query type. It creates a concrete query from a builder lambda. That object is then passed into NativeQuery.

## 5. Building a bool Query with Nested Lambdas

Real queries often combine multiple conditions. For example, searching for products whose name relates to keyboard, restricted to active products in the accessories category:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .bool(b -> b
                .must(m -> m
                    .match(mm -> mm
                        .field("name")
                        .query("keyboard")
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
        .build();

Equivalent query:

    {
      "query": {
        "bool": {
          "must": [
            {
              "match": {
                "name": "keyboard"
              }
            }
          ],
          "filter": [
            {
              "term": {
                "status": "ACTIVE"
              }
            },
            {
              "term": {
                "category": "accessories"
              }
            }
          ]
        }
      }
    }

In this example:

- bool combines multiple clauses.
- must requires documents to match the search content and contributes to relevance scoring.
- filter restricts status and category without calculating relevance scores.
- FieldValue.of(...) creates a term value in the data type required by the Java API Client.

Nested lambdas mirror the Query DSL structure. Each level provides a corresponding builder: Query.Builder, BoolQuery.Builder, MatchQuery.Builder, or TermQuery.Builder.

### Using should to Boost Scores

If you want to prioritize products with matching names and boost the score further when the description also matches:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .bool(b -> b
                .must(m -> m
                    .match(mm -> mm
                        .field("name")
                        .query("mechanical keyboard")
                    )
                )
                .should(s -> s
                    .match(m -> m
                        .field("description")
                        .query("mechanical keyboard")
                    )
                )
                .minimumShouldMatch("0")
            )
        )
        .build();

Here, must determines the primary search condition. should can contribute to the score if the description matches. Because bool already has must, should is optional by default; declaring minimumShouldMatch("0") makes this intent explicit.

If at least one condition in should is required to match, set minimumShouldMatch("1") and organize the clauses accordingly. The value of minimum_should_match can be a more flexible expression than a single integer, depending on Elasticsearch syntax support.

## 6. Building term Queries and Typed Values

term is used to match an exact indexed value. It is typically suited for keyword fields, identifiers, statuses, or enum values.

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .term(t -> t
                .field("status")
                .value(FieldValue.of("ACTIVE"))
            )
        )
        .build();

The Java API Client uses FieldValue to represent different value types such as string, long, double, boolean, or null. Example:

    FieldValue stringValue = FieldValue.of("ACTIVE");
    FieldValue numberValue = FieldValue.of(100L);
    FieldValue decimalValue = FieldValue.of(19.95);
    FieldValue booleanValue = FieldValue.of(true);

Do not pass every value as a string. The value's data type must match the field's mapping. For example, numeric fields should use numeric values; keyword fields should use strings.

## 7. Building range Queries

A range query filters by numeric, date, or other range-capable types. For example, finding products priced between 100 and 500:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .range(r -> r
                .number(n -> n
                    .field("price")
                    .gte(100.0)
                    .lte(500.0)
                )
            )
        )
        .build();

In the modern Elasticsearch Java API Client, range queries have typed variants. For numeric fields, the number builder represents a numeric range. For date fields, you can use the date range variant with date values in a format supported by the mapping.

Example filtering creation date within a range:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .range(r -> r
                .date(d -> d
                    .field("createdAt")
                    .gte("2026-01-01T00:00:00Z")
                    .lt("2027-01-01T00:00:00Z")
                )
            )
        )
        .build();

Range query builder variants may change across Java API Client versions. Use the type matching your declared dependency; do not mix older range syntax using JsonData with the newer typed range API in the same example.

## 8. Building multi_match Queries

multi_match searches content across multiple fields. You can boost important fields using boost syntax:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .multiMatch(m -> m
                .query("spring data")
                .fields("name^3", "description", "brand")
            )
        )
        .build();

In this example, the name field has a boost of 3, while description and brand use the default weight. Documents matching the product name can be ranked higher than documents matching only the description or brand.

Multi-match supports several execution modes, such as best_fields, most_fields, cross_fields, or phrase. If business requirements call for a specific mode, configure type(...) with the corresponding enum from the Java API Client.

Do not add many fields to multi-match without considering each field's mapping, analyzer, and importance. Having too many participating fields can affect query cost and result ordering.

## 9. Extracting Queries into Small Helper Methods

A large query can become hard to read if every condition is placed inside a deeply nested lambda expression. You can extract parts into methods that return Query.

    private Query nameMatch(String keyword) {
        return Query.of(q -> q
            .match(m -> m
                .field("name")
                .query(keyword)
            )
        );
    }

    private Query activeFilter() {
        return Query.of(q -> q
            .term(t -> t
                .field("status")
                .value(FieldValue.of("ACTIVE"))
            )
        );
    }

    private Query categoryFilter(String category) {
        return Query.of(q -> q
            .term(t -> t
                .field("category")
                .value(FieldValue.of(category))
            )
        );
    }

Then combine them:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .bool(b -> b
                .must(nameMatch(keyword))
                .filter(activeFilter())
                .filter(categoryFilter(category))
            )
        )
        .build();

Benefits:

- Each method describes a meaningful condition.
- Filters or queries can be reused across multiple searches.
- Individual components are easy to test in isolation.
- Reduces lambda nesting depth in the overall query.

Do not extract every single line into a tiny method. Only extract conditions that have distinct business meaning or reuse potential to avoid fragmenting the code excessively.

## 10. Combining Optional Conditions

A search screen may allow users to enter a keyword, pick a category, or specify a price limit. Some parameters may be left blank. In that case, add the corresponding clause only if the user provided a value.

You can build a list of queries first and pass it into the bool query:

    List<Query> filters = new ArrayList<>();

    filters.add(Query.of(q -> q
        .term(t -> t
            .field("status")
            .value(FieldValue.of("ACTIVE"))
        )
    ));

    if (category != null && !category.isBlank()) {
        filters.add(Query.of(q -> q
            .term(t -> t
                .field("category")
                .value(FieldValue.of(category))
            )
        ));
    }

    if (minimumPrice != null || maximumPrice != null) {
        filters.add(Query.of(q -> q
            .range(r -> r
                .number(n -> {
                    n.field("price");
                    if (minimumPrice != null) {
                        n.gte(minimumPrice);
                    }
                    if (maximumPrice != null) {
                        n.lte(maximumPrice);
                    }
                    return n;
                })
            )
        ));
    }

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .bool(b -> b
                .filter(filters)
            )
        )
        .build();

Here, the filters list is assembled based on input parameters. A block lambda allows calling multiple methods on the same builder before returning the builder at the end. This approach is helpful when queries have optional conditions.

If your project uses a Java API Client version with a different range builder API, adjust the numeric range part to match that version's types. The composition idea remains the same: create a clause only when the parameter has a value, then pass the list into filter.

When there are many optional conditions, check for the empty list case. A bool query with only an empty filter can behave like match-all according to Elasticsearch semantics; if business rules require at least one condition, validate inputs in the service before building the query.

## 11. Adding Pagination and Sorting

NativeQuery can be combined with Spring Data's Pageable. For example, fetching the first page of 20 products sorted by price descending:

    Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(Sort.Order.desc("price"))
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

PageRequest uses a 0-based page index. Sort references Elasticsearch mapping field names, so you must use the exact indexed field name.

If you need to sort by multiple fields:

    Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.asc("name")
        )
    );

With large datasets and deep pagination, from/size has limits and can consume significant resources. When paginating deeply through many results, consider search_after with a stable sort or a mechanism appropriate for your Elasticsearch version.

## 12. Adding Aggregations

NativeQuery can also contain aggregations. For example, counting products by category:

    import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .term(t -> t
                .field("status")
                .value(FieldValue.of("ACTIVE"))
            )
        )
        .withAggregation(
            "products_by_category",
            Aggregation.of(a -> a
                .terms(t -> t
                    .field("category")
                )
            )
        )
        .build();

The query narrows down the set of active products, while the aggregation groups matching documents by category. Fields used for terms aggregations are typically keyword or fields with suitable doc values; avoid using analyzed text fields by default.

When reading aggregation results, the response can be retrieved from SearchHits or the corresponding Spring Data response API, depending on the aggregation type and version. Keep the aggregation name (`products_by_category`) consistent so you read the right bucket from the results.

## 13. Executing NativeQuery with ElasticsearchOperations

After building the query, you can execute it via ElasticsearchOperations:

    @Service
    public class ProductSearchService {

        private final ElasticsearchOperations operations;

        public ProductSearchService(
                ElasticsearchOperations operations) {
            this.operations = operations;
        }

        public SearchHits<Product> search(
                String keyword,
                String category,
                Pageable pageable) {

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
                                .value(FieldValue.of(category))
                            )
                        )
                    )
                )
                .withPageable(pageable)
                .build();

            return operations.search(query, Product.class);
        }
    }

operations.search(query, Product.class) executes the query against the index determined by the entity's metadata, usually `@Document(indexName = "products")`. Spring Data uses its converter to map JSON documents into Product instances.

If you need to specify a particular index or alias, pass IndexCoordinates to the corresponding overload:

    SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
    );

This is useful when an entity can be read from multiple indices or when the application uses a stable alias.

## 14. Reading SearchHits and Result Metadata

SearchHits<T> contains the search hits along with metadata such as total hit count, scores, and related information. You can iterate over it:

    SearchHits<Product> hits =
        operations.search(query, Product.class);

    for (SearchHit<Product> hit : hits) {
        Product product = hit.getContent();
        float score = hit.getScore();
        String id = hit.getId();
    }

If you only need the entities, you can extract the contents:

    List<Product> products = hits.getSearchHits()
        .stream()
        .map(SearchHit::getContent)
        .toList();

Do not discard metadata if the UI needs to display scores, highlights, or total hit counts. The return type should reflect the exact information needed by the caller layer.

## 15. Adding Highlighting to Search Results

For full-text search, the application may need the text snippets matching the keyword for display. NativeQuery can configure highlighting using the APIs supported by Spring Data and the Java Client.

Highlighting is declared in the query options, specifying the fields to generate fragments for and limits such as the number of fragments. The exact builder structure depends on the Spring Data Elasticsearch and Java API Client versions; check the corresponding highlight signatures in your actual dependencies before implementing.

Highlighting only assists in presenting matching text. It does not replace the analyzer or determine whether a query matches.

## 16. Separating Query Construction from Execution

For large queries, you can create a separate method that returns a NativeQuery:

    private NativeQuery buildProductQuery(
            String keyword,
            String category,
            Pageable pageable) {

        return NativeQuery.builder()
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
                            .value(FieldValue.of(category))
                        )
                    )
                )
            )
            .withPageable(pageable)
            .build();
    }

    public SearchHits<Product> search(
            String keyword,
            String category,
            Pageable pageable) {
        NativeQuery query =
            buildProductQuery(keyword, category, pageable);

        return operations.search(query, Product.class);
    }

This organization establishes a clear boundary:

- buildProductQuery is responsible for describing the conditions.
- search is responsible for sending the query and returning results.

If there are many query variants, split builders by use case or condition group. Avoid creating one massive generic query builder with dozens of boolean flags that make it hard to tell which conditions are actually added.

## 17. When to Use Query.of vs. Direct Lambdas?

Both approaches are valid.

Direct lambda inside NativeQuery:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .match(m -> m
                .field("name")
                .query(keyword)
            )
        )
        .build();

Creating a Query beforehand with Query.of:

    Query esQuery = Query.of(q -> q
        .match(m -> m
            .field("name")
            .query(keyword)
        )
    );

    NativeQuery query = NativeQuery.builder()
        .withQuery(esQuery)
        .build();

Use a direct lambda when the query is short and used in only one place. Use Query.of when you want to place a query in its own method, reuse it, assemble a list of clauses, or test the query structure independently of NativeQuery.

## 18. Notes on Builders and Lambda Expressions

### Use Accurate Field Names

Builders accept field names as strings. The Java compiler cannot verify whether a field name exists in the mapping. A wrong field name can cause the query to return no results or trigger errors during sorting/aggregations.

Verify against the actual mapping and consider constants for frequently used fields:

    private static final String FIELD_NAME = "name";
    private static final String FIELD_CATEGORY = "category";

Constants reduce typos in Java code, though they do not replace checking the mapping.

### Use the Right Value Types

The Java API Client typically requires FieldValue for term values. Range queries use value types suited for their numeric/date variants. Do not convert everything into a String if the field is mapped as a number or date.

### Distinguish must and filter

The builder lets you call both must(...) and filter(...), but their query semantics differ:

- must uses query context and can contribute to the score.
- filter only evaluates true/false matching and does not contribute to the score.

Use filter for status, category, price range, or mandatory conditions that do not require ranking; use must/should for content conditions that should influence relevance scores.

### Do Not Reuse a Built Builder

Builders are mutable objects during configuration. After calling build(), use the created query object. If you need a different query variant, create a new builder or a new query object instead of sharing a mutable builder across threads.

### Avoid Deeply Nested Lambdas

Nested lambdas reflect the Query DSL structure, but too many levels can make code hard to read. Extract clauses into methods returning Query when they carry distinct meaning or are reused.

### Check API Compatibility by Version

The builder types generated by the Elasticsearch Java API Client depend on the client version. Some range, highlight, aggregation, or enum types may change across releases. Use Spring Boot/Spring Data dependency management to keep libraries compatible and check the corresponding Javadoc.

## 19. Common Mistakes

### Confusing NativeQuery with Query Builder

NativeQuery is a Spring Data query type; the withQuery lambda builds the Elasticsearch Java API Client Query type. Distinguishing these two abstractions helps avoid importing the wrong Query class.

### Passing a String Directly into a Term Value

The Java API Client generally requires FieldValue for term values. Use FieldValue.of(...) to represent values with the right type.

### Using term on a text Field

Text fields are split into tokens by an analyzer. For full-text search, use match or another suitable query. term is typically meant for exact values on keyword fields or compatible data types.

### Using match on a keyword Field Without Understanding the Mapping

A match query analyzes the input string using the search analyzer. For keyword fields, if exact matching is intended, a term query is usually clearer in intent.

### Putting Every Condition Inside must

Filtering conditions like status, category, or price range do not necessarily need to participate in scoring. Putting them in filter expresses the right semantics and avoids unnecessary score computation.

### Not Handling Optional Parameters

If an empty parameter is still added to a query, results may be wrong or the query invalid. Only add a clause when the input has a value, and explicitly define behavior when no conditions are provided.

### Forgetting Pagination or Result Limits

Search queries can return a limited default number of results. Configure Pageable or an appropriate result size for your API.

### Assuming build() Sends the Request

build() only constructs the query object. The request is only sent when calling operations or an execution client.

### Using Builder Examples That Do Not Match Your Version

Java Client builders can differ between versions. If the IDE reports missing methods like number(...), date(...), or a specific overload, check your dependency version and use the signature matching the API you have.

## 20. Workflow for Building a Maintainable NativeQuery

When implementing a new query, follow these steps:

1. Check the mapping of the fields to be used in the query.
2. Identify which conditions require scoring and which only filter.
3. Start with a small query, typically match, term, or range.
4. Combine conditions with bool and the corresponding lambdas.
5. Extract clauses into methods returning Query if the query gets too deep or needs reuse.
6. Add Pageable, sort, aggregations, or highlighting as required by business needs.
7. Build the NativeQuery via build().
8. Execute via ElasticsearchOperations.search(...).
9. Read SearchHits and process scores/metadata if needed.
10. Test the query against real data and mappings on Elasticsearch.

Complete example:

    @Service
    public class ProductSearchService {

        private final ElasticsearchOperations operations;

        public ProductSearchService(
                ElasticsearchOperations operations) {
            this.operations = operations;
        }

        public SearchHits<Product> search(
                String keyword,
                String category,
                Double minPrice,
                Double maxPrice,
                int page,
                int size) {

            NativeQuery query = NativeQuery.builder()
                .withQuery(q -> q
                    .bool(b -> {
                        b.must(m -> m
                            .match(mm -> mm
                                .field("name")
                                .query(keyword)
                            )
                        );

                        b.filter(f -> f
                            .term(t -> t
                                .field("status")
                                .value(FieldValue.of("ACTIVE"))
                            )
                        );

                        if (category != null && !category.isBlank()) {
                            b.filter(f -> f
                                .term(t -> t
                                    .field("category")
                                    .value(FieldValue.of(category))
                                )
                            );
                        }

                        if (minPrice != null || maxPrice != null) {
                            b.filter(f -> f
                                .range(r -> r
                                    .number(n -> {
                                        n.field("price");
                                        if (minPrice != null) {
                                            n.gte(minPrice);
                                        }
                                        if (maxPrice != null) {
                                            n.lte(maxPrice);
                                        }
                                        return n;
                                    })
                                )
                            );
                        }

                        return b;
                    })
                )
                .withPageable(PageRequest.of(
                    page,
                    size,
                    Sort.by(Sort.Order.desc("createdAt"))
                ))
                .build();

            return operations.search(query, Product.class);
        }
    }

In this query:

- Product name is searched with match inside must.
- ACTIVE status is always a mandatory filter.
- Category is added only when the user selects a category.
- Price range is added only when at least one price bound is provided.
- Pageable limits the number of results and sorts by creation date.
- operations.search executes the query and maps results into Product.

A block lambda for the bool builder lets you configure clauses conditionally in Java and return the builder at the end. Verify the range builder type and overload signatures against the Java API Client version in your project to ensure compatibility.

## Conclusion

NativeQuery provides a flexible way to build queries in Spring Data Elasticsearch when you need to use the Elasticsearch Query DSL directly. NativeQuery.builder() configures the Spring Data query; withQuery takes a lambda to construct a Query from the Elasticsearch Java API Client. Nested lambdas sequentially configure builders for bool, match, term, range, and other query types.

To keep queries readable and semantically accurate, use must/should for search conditions that affect relevance scoring, use filter for restricting conditions, pick proper value types like FieldValue, add pagination and sorting when needed, and execute via ElasticsearchOperations. When a query grows large, extract clauses into small methods returning Query. Always cross-check your project's mapping and Java API Client version because builders are generated per library version.
