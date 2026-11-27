# NativeQuery and Elasticsearch Java Client Query Type

Spring Data Elasticsearch provides several ways to build queries. For simple queries, `CriteriaQuery` can be used. When you need to express the full Elasticsearch query DSL, Spring Data provides `NativeQuery`, which allows using the `Query` type from the Elasticsearch Java API Client directly.

A common source of confusion is that two types share the name `Query`:

- **Spring Data Query**: the Spring Data Elasticsearch abstraction, accepted by methods such as `ElasticsearchOperations.search(...)`.
- **Elasticsearch Java Client Query**: the structured query DSL type, located in the `co.elastic.clients.elasticsearch._types.query_dsl` package.

`NativeQuery` bridges these two layers: it is a Spring Data query that holds a query DSL built with the Elasticsearch Java Client.

## 1. Two Query Types with Different Roles

Spring Data Elasticsearch defines the interface:

~~~java
org.springframework.data.elasticsearch.core.query.Query
~~~

This is the common abstraction for queries that Spring Data can execute. Some familiar implementations include:

- `CriteriaQuery`: a query built using the Criteria API.
- `StringQuery`: a query described as a JSON DSL string.
- `NativeQuery`: a query using the data types of the Elasticsearch Java API Client.

Meanwhile, the Elasticsearch Java API Client has the type:

~~~java
co.elastic.clients.elasticsearch._types.query_dsl.Query
~~~

This type represents query DSL clauses such as `match`, `term`, `bool`, `range`, `multi_match`, and many other query types.

| Type | Package | Role |
|---|---|---|
| Spring Data `Query` | `org.springframework.data.elasticsearch.core.query.Query` | Input abstraction for Spring Data operations |
| `CriteriaQuery` | `org.springframework.data.elasticsearch.core.query.CriteriaQuery` | Builds queries using Criteria |
| `StringQuery` | `org.springframework.data.elasticsearch.core.query.StringQuery` | Builds queries from a JSON DSL string |
| `NativeQuery` | `org.springframework.data.elasticsearch.client.elc.NativeQuery` | Wraps Java Client query DSL and search options |
| Elasticsearch Java Client `Query` | `co.elastic.clients.elasticsearch._types.query_dsl.Query` | Typed representation of the query DSL |

Because both packages have a type named `Query`, pay close attention to imports. In code that uses `NativeQuery`, you can name the variable `elasticsearchQuery` and import only the Java Client's `Query` type to avoid confusion.

## 2. What Is NativeQuery?

`NativeQuery` is an implementation of the Spring Data Query abstraction. It allows passing a query DSL built with the Elasticsearch Java API Client into Spring Data Elasticsearch.

Processing flow:

~~~mermaid
flowchart TD
    A["Elasticsearch Java Client Query"] --> B["NativeQuery.Builder"]
    B --> C["NativeQuery"]
    C --> D["Spring Data Query abstraction"]
    D --> E["ElasticsearchOperations.search"]
    E --> F["Elasticsearch Java Client"]
    F --> G["Elasticsearch cluster"]
    G --> H["Search response"]
    H --> I["SearchHits<Entity>"]
~~~

`NativeQuery` can carry various search request settings, such as:

- The main query DSL.
- Filter query.
- Pageable and sort.
- Aggregations.
- Highlighting.
- Track total hits.
- Other search options supported by Spring Data.

The query DSL inside `NativeQuery` is an Elasticsearch Java Client type. `NativeQuery` enables Spring Data to use that query alongside entity mapping metadata and conversion.

## 3. Creating a Query with the Elasticsearch Java API Client

The Elasticsearch Java API Client provides typed builders for creating queries. Instead of concatenating JSON strings manually, you create a `Query` object using `Query.of(...)`.

Example of a `match` query:

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

Query elasticsearchQuery = Query.of(q -> q
        .match(m -> m
                .field("name")
                .query("wireless keyboard")
        )
);
~~~

In this example:

- `Query.of(...)` creates a query object.
- `match(...)` selects the full-text query type.
- `field("name")` specifies the field to search.
- `query("wireless keyboard")` is the text entered by the user.

The result is an immutable `Query` object describing the DSL structure. The builder provides compile-time type checking, helping reduce errors caused by invalid JSON structure or misspelled property names.

### Term Query

For keyword fields such as status, use `term`:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

Query statusQuery = Query.of(q -> q
        .term(t -> t
                .field("status")
                .value(FieldValue.of("PUBLISHED"))
        )
);
~~~

`FieldValue` is the value type used in the Elasticsearch Java API Client for term queries. Here, the string value is represented using `FieldValue.of(...)`.

`term` matches indexed terms as-is. For `text` fields processed by an analyzer, you need to be aware of the actual indexed tokens; `keyword` fields are usually more suitable for statuses and codes requiring exact matching.

## 4. Combining Multiple Conditions with a bool Query

A real-world search form often needs to combine full-text search with exact filters.

Example: search for products by keyword in the name while only returning products with status `PUBLISHED`:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

Query elasticsearchQuery = Query.of(q -> q
        .bool(b -> b
                .must(m -> m
                        .match(mm -> mm
                                .field("name")
                                .query("wireless keyboard")
                        )
                )
                .filter(f -> f
                        .term(t -> t
                                .field("status")
                                .value(FieldValue.of("PUBLISHED"))
                        )
                )
        )
);
~~~

Meaning:

- `bool` combines multiple conditions.
- `must` contains search conditions that can affect the relevance score.
- `filter` contains filtering conditions that do not need relevance scoring.
- `match` analyzes the query text using the search analyzer.
- `term` matches the status value.

Common clauses used in a bool query:

| Clause | Meaning |
|---|---|
| `must` | Condition must match and can contribute to scoring |
| `filter` | Condition must match without calculating relevance score |
| `should` | Optional or OR condition, depending on minimum_should_match and bool structure |
| `must_not` | Exclusion condition |

### Combining OR Conditions with should

For example, to retrieve products with status `FEATURED` or label `PROMOTED`:

~~~java
Query elasticsearchQuery = Query.of(q -> q
        .bool(b -> b
                .should(s -> s
                        .term(t -> t
                                .field("status")
                                .value(FieldValue.of("FEATURED"))
                        )
                )
                .should(s -> s
                        .term(t -> t
                                .field("label")
                                .value(FieldValue.of("PROMOTED"))
                        )
                )
                .minimumShouldMatch("1")
        )
);
~~~

`minimumShouldMatch("1")` requires at least one `should` branch to match. When combining `must` or `filter` with `should`, explicitly set `minimum_should_match` if business logic requires a mandatory OR. Otherwise, `should` clauses may only act as score boosters according to the default bool query rules.

## 5. Wrapping an Elasticsearch Query in NativeQuery

After creating the query DSL, pass it into `NativeQuery.builder().withQuery(...)`.

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Query elasticsearchQuery = Query.of(q -> q
        .match(m -> m
                .field("name")
                .query("wireless keyboard")
        )
);

NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .build();
~~~

`nativeQuery` is now a Spring Data Query. You can pass it into `ElasticsearchOperations.search(...)`.

~~~java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<ProductDocument> hits =
        operations.search(nativeQuery, ProductDocument.class);
~~~

Spring Data uses `ProductDocument.class` to know how to convert each search hit into an entity. The query DSL determines the search conditions; the entity class determines the returned Java data type and related mapping metadata.

## 6. Adding Pagination and Sorting

`NativeQuery` supports Spring Data search options, including pageable.

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withPageable(
                PageRequest.of(
                        0,
                        20,
                        Sort.by(Sort.Direction.DESC, "createdAt")
                )
        )
        .build();
~~~

In this example:

- The first page has index `0`.
- Each page contains at most `20` results.
- Results are sorted by `createdAt` descending.

The field used for sorting must have a mapping that supports sorting, typically keyword, numeric, or date. Do not sort directly on a regular text field if that field does not have doc values.

For deep pagination, consider `search_after` and a stable sort instead of increasing `from/size` to very large values.

## 7. Distinguishing query and filter in NativeQuery

Search conditions and filter conditions can be expressed inside a single bool query as in the previous example. `NativeQuery` also provides a separate builder method for filters in supported versions.

Example:

~~~java
NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(nameQuery)
        .withFilter(statusFilter)
        .build();
~~~

Here, both `nameQuery` and `statusFilter` are Elasticsearch Java Client `Query` objects.

Separating query and filter serves a clear purpose:

- The main query handles matching and scoring.
- The filter adds mandatory conditions without requiring relevance scoring.
- The query structure clearly communicates business intent.

You can use a bool query instead of separating `withFilter`; both approaches can express the conditions. Choose a consistent structure so queries remain readable and maintainable. Check the API of the Spring Data Elasticsearch version you are using if you rely on advanced builder methods.

## 8. Integrating NativeQuery with ElasticsearchOperations

A service can accept query parameters from input, build a Java Client Query, wrap it in a NativeQuery, and execute it:

~~~java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<ProductDocument> search(
            String keyword,
            String status
    ) {
        Query elasticsearchQuery = Query.of(q -> q
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
                                        .value(FieldValue.of(status))
                                )
                        )
                )
        );

        NativeQuery nativeQuery = NativeQuery.builder()
                .withQuery(elasticsearchQuery)
                .build();

        return operations.search(
                nativeQuery,
                ProductDocument.class
        );
    }
}
~~~

`ElasticsearchOperations` is a Spring Data abstraction. The service does not need to build HTTP requests manually or parse JSON responses itself. Spring Data executes the query through the configured client and converts the results into `SearchHits<ProductDocument>`.

In a real application, you need to validate `keyword` and `status`, handle cases where conditions are absent, limit result counts, and add access/tenant filters from the security context.

## 9. Reading SearchHits Results

`operations.search(...)` typically returns `SearchHits<T>`, not just a plain list of entities.

~~~java
SearchHits<ProductDocument> hits =
        operations.search(nativeQuery, ProductDocument.class);

for (var hit : hits) {
    ProductDocument product = hit.getContent();
    float score = hit.getScore();

    System.out.println(product.getName());
    System.out.println(score);
}
~~~

Each `SearchHit<T>` can contain:

- Entity content.
- Relevance score.
- Document ID.
- The index containing the document.
- Sort values and other metadata depending on the response.

If you only need the list of entities, you can transform `hits.getSearchHits()` into a list of contents. If the UI needs relevance scores or ID/index metadata, keep the `SearchHit` structure.

## 10. How Do NativeQuery and CriteriaQuery Differ?

Both can be passed into Spring Data operations methods because they both implement the `org.springframework.data.elasticsearch.core.query.Query` abstraction.

| Criterion | CriteriaQuery | NativeQuery |
|---|---|---|
| Construction method | Spring Data Criteria API | Elasticsearch Java Client Query DSL |
| Abstraction level | Higher, simpler API | Closer to Elasticsearch DSL |
| Complex queries | Suitable for common conditions | Suitable for advanced query DSL |
| Nested bool queries | Expressible, though sometimes harder to read | Expressed directly with typed DSL |
| New Elasticsearch features | Depends on Criteria support level | Accesses query types supported by Java Client |
| Readability & maintainability | Easy for simple filters | Clear when fine-grained DSL control is needed |

CriteriaQuery example:

~~~java
Criteria criteria = new Criteria("status").is("PUBLISHED")
        .and("price").greaterThanEqual(100000);

CriteriaQuery criteriaQuery = new CriteriaQuery(criteria);
~~~

NativeQuery example:

~~~java
import co.elastic.clients.json.JsonData;
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Query elasticsearchQuery = Query.of(q -> q
        .bool(b -> b
                .filter(f -> f
                        .term(t -> t
                                .field("status")
                                .value(FieldValue.of("PUBLISHED"))
                        )
                )
                .filter(f -> f
                        .range(r -> r
                                .field("price")
                                .gte(JsonData.of(100000.0))
                        )
                )
        )
);

NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .build();
~~~

NativeQuery lets you express a query DSL structure close to the Elasticsearch JSON request, though it requires understanding the Java Client's data types and builder API.

You do not need to use NativeQuery for every query. For simple filters, CriteriaQuery is often easier to read. Choose NativeQuery when you need fine-grained DSL control or features not conveniently expressed by the Criteria API.

## 11. How Do NativeQuery and StringQuery Differ?

`StringQuery` accepts the query DSL as a JSON string:

~~~java
import org.springframework.data.elasticsearch.core.query.StringQuery;

StringQuery query = new StringQuery("""
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
        """);
~~~

Meanwhile, NativeQuery accepts a strongly typed query object:

~~~java
Query elasticsearchQuery = Query.of(q -> q
        .match(m -> m
                .field("name")
                .query("wireless keyboard")
        )
);

NativeQuery query = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .build();
~~~

| Criterion | StringQuery | NativeQuery |
|---|---|---|
| Input | JSON DSL as a string | Java Client Query object |
| Compile-time type checking | Limited | Better via typed builder |
| Ease of copying from Dev Tools | High | Requires translating DSL to builder |
| Refactoring with Java API | Harder | More convenient |
| Best suited for | Pre-existing JSON queries or small structures | Queries built dynamically in Java code needing type safety |

If the JSON query is managed externally or copied from Kibana Dev Tools, StringQuery can be convenient. If the query is built dynamically in code, NativeQuery helps reduce structural and type errors.

## 12. Distinguishing from the Legacy RestHighLevelClient API

Older Spring Data Elasticsearch examples often use `NativeSearchQuery` and `QueryBuilders` from the Elasticsearch Rest High Level Client.

Legacy-style example:

~~~java
// Legacy API, shown for recognition
QueryBuilder queryBuilder =
        QueryBuilders.matchQuery("name", "wireless keyboard");
~~~

In Spring Data Elasticsearch 5.x, the default client integration is based on the Elasticsearch Java API Client. In that case, the query type is:

~~~java
co.elastic.clients.elasticsearch._types.query_dsl.Query
~~~

and the Spring Data wrapper is:

~~~java
org.springframework.data.elasticsearch.client.elc.NativeQuery
~~~

Do not mix `QueryBuilder` from RestHighLevelClient with `NativeQuery` from the Java API Client. These are two different API generations with different packages, data types, and instantiation patterns.

When upgrading a project, check the managed versions of Spring Data Elasticsearch and the Elasticsearch client in your dependencies. In a Spring Boot application, prefer Boot's compatible dependency management rather than manually upgrading a client version on its own.

## 13. Common Mistakes

### Importing the Wrong Query

Both Query types share the same simple name. If you accidentally import `org.springframework.data.elasticsearch.core.query.Query` and then call `Query.of(...)`, the code will not compile because Spring Data's `Query` does not have that builder method.

Import:

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
~~~

and use `NativeQuery` to wrap it.

### Passing the Wrong Type into NativeQuery

`NativeQuery.builder().withQuery(...)` expects a Java Client query DSL object. Do not pass a `Criteria` object or another Spring Data `Query` implementation here.

### Using term on a text Field

`term` does not analyze input like `match` does. If a `text` field has been lowercased or stemmed, the raw query value might not match the tokens in the index.

### Misusing FieldValue

Certain term queries in the Java Client require `FieldValue`. Use `FieldValue.of(...)` with the appropriate data type instead of passing an incompatible object.

### Confusing filter with must

`must` can participate in scoring; `filter` does not calculate a score. Use `filter` for conditions like status, tenant, or category when relevance scoring is not needed.

### Querying a Field Missing from Mapping

The Java Client builder checks the query structure's types, but it cannot automatically know whether every field in the index has the right mapping. If a queried field does not exist or has the wrong type, results may be empty or the request may fail depending on the query type. Check the actual mapping.

### Using Query DSL from a Different Client Version

Builder APIs can change across Elasticsearch Java API Client versions. Ensure your imports and dependencies are compatible with the version of Spring Data Elasticsearch in use.

## 14. Workflow for Building a NativeQuery

When you need to create a query using the Elasticsearch Java Client and execute it via Spring Data:

1. Identify the fields, mapping types, and search goal.
2. Choose the appropriate query DSL such as `match`, `term`, `bool`, `range`, or `multi_match`.
3. Create a `co.elastic.clients.elasticsearch._types.query_dsl.Query` object using `Query.of(...)`.
4. Combine conditions using a bool query; use `filter` for conditions that do not need scoring.
5. Wrap the query in `NativeQuery.builder().withQuery(...)`.
6. Add pageable, sort, aggregations, or search options if needed.
7. Call `ElasticsearchOperations.search(...)` with the appropriate entity class and index coordinates.
8. Read results via `SearchHits<T>` or map them to DTOs.
9. Test the query against the actual mapping and data.
10. Ensure query fields, sort fields, and access control filters are properly controlled.

## Conclusion

`NativeQuery` acts as the bridge between the Spring Data Elasticsearch Query abstraction and the Elasticsearch Java API Client query DSL. The `co.elastic.clients.elasticsearch._types.query_dsl.Query` type describes search conditions via a strongly typed builder; `NativeQuery` wraps it along with search options to pass into `ElasticsearchOperations`. Use `CriteriaQuery` for common queries, `NativeQuery` when detailed DSL control is needed, and always clearly distinguish between the two types named `Query` to avoid import mistakes.
