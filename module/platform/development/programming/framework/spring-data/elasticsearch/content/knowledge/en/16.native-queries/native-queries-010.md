# Distinguishing `NativeQuery` from Legacy Query APIs

Spring Data Elasticsearch offers multiple ways to build queries. When reading legacy codebases or upgrading versions, it is easy to confuse modern `NativeQuery` with `NativeSearchQuery` and `NativeSearchQueryBuilder` from earlier releases. Their names look similar, yet they rely on two different Elasticsearch Java clients and do not share query builder types.

Starting with Spring Data Elasticsearch 5.x, native queries are built on the new **Elasticsearch Java API Client**, using `co.elastic.clients.elasticsearch._types.query_dsl.Query`. Spring Data Elasticsearch 4.x projects typically use the legacy **Rest High Level Client (HLRC)** with `org.elasticsearch.index.query.QueryBuilder`, `QueryBuilders`, `NativeSearchQuery`, and `NativeSearchQueryBuilder`.

Key point during upgrades: `NativeQuery` is not a simple class rename of `NativeSearchQuery`. You must migrate Query DSL construction from legacy builder APIs to the new Java API Client query types, while also reviewing sort, aggregation, highlighting, paging, and mapping options.

```text
Spring Data Elasticsearch 4.x (legacy)
--------------------------------------
QueryBuilders / BoolQueryBuilder
              |
              v
       NativeSearchQuery
              |
              v
      Rest High Level Client

Spring Data Elasticsearch 5.x+
------------------------------
Elasticsearch Java API Client Query
              |
              v
          NativeQuery
              |
              v
      ElasticsearchOperations
              |
              v
       Elasticsearch cluster
```

## 1. Main Query APIs in Spring Data Elasticsearch

Spring Data Elasticsearch provides several abstractions because queries vary in complexity:

| API | How It Is Built | When Appropriate |
|---|---|---|
| `CriteriaQuery` | Uses `Criteria` and Spring Data comparison/logic operations. | Common filter conditions, easy to assemble dynamically in Java. |
| `StringQuery` | Passes Query DSL as a JSON string. | Pre-existing JSON Query DSL or short, readable static queries. |
| `NativeQuery` | Uses query types from the new Elasticsearch Java API Client. | Complex Elasticsearch queries needing full Query DSL capabilities. |
| `NativeSearchQuery` (legacy) | Uses `QueryBuilder` from Rest High Level Client. | Legacy codebases based on Spring Data Elasticsearch 4.x / HLRC. |

The first three APIs are the options in the modern Spring Data Elasticsearch generation. `NativeSearchQuery` belongs to the older generation and should not be viewed as a drop-in companion to `NativeQuery` in 5.x projects.

## 2. `NativeSearchQuery` and `NativeSearchQueryBuilder` in the Legacy Generation

In Spring Data Elasticsearch 4.x, native queries were typically created using `NativeSearchQueryBuilder`. Query conditions used HLRC classes such as `BoolQueryBuilder`, `QueryBuilders`, and `SortBuilders`.

Legacy code example:

```java
import org.elasticsearch.index.query.BoolQueryBuilder;
import org.elasticsearch.index.query.QueryBuilders;
import org.elasticsearch.search.sort.SortBuilders;
import org.elasticsearch.search.sort.SortOrder;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.core.query.NativeSearchQuery;
import org.springframework.data.elasticsearch.core.query.NativeSearchQueryBuilder;

BoolQueryBuilder boolQuery = QueryBuilders.boolQuery()
        .must(QueryBuilders.matchQuery("title", "spring data"))
        .filter(QueryBuilders.termQuery("status", "PUBLISHED"));

NativeSearchQuery query = new NativeSearchQueryBuilder()
        .withQuery(boolQuery)
        .withPageable(PageRequest.of(0, 20))
        .withSort(SortBuilders.fieldSort("published_at").order(SortOrder.DESC))
        .build();
```

Here:

- `QueryBuilders` creates query builders like `matchQuery`, `termQuery`, and `boolQuery`.
- `BoolQueryBuilder` groups `must`, `filter`, `should`, and `mustNot` clauses.
- `NativeSearchQueryBuilder` combines the query, pageable, sort, and search options.
- `build()` creates `NativeSearchQuery`, which Spring Data converts into a request sent via HLRC.

This code depends on classes under the `org.elasticsearch.*` namespace of the Rest High Level Client. Once a project moves to Spring Data Elasticsearch 5.x, those legacy `QueryBuilder` types are no longer what the new Java API Client uses.

### Execution in Legacy Code

At the service layer, queries were typically executed via `ElasticsearchOperations`:

```java
SearchHits<ArticleDocument> hits =
        operations.search(query, ArticleDocument.class);
```

The pattern of using `operations` carries over to the new generation. What changes primarily is the query object type and how Query DSL is constructed.

## 3. `NativeQuery` in Spring Data Elasticsearch 5.x+

Spring Data Elasticsearch 5.x uses the Elasticsearch Java API Client. Query DSL is represented by type-safe Java classes in `co.elastic.clients.elasticsearch._types.query_dsl`.

`NativeQuery` resides in the package:

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
```

Elasticsearch Java API Client query objects:

```java
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
```

Equivalent example to the legacy query above:

```java
Query esQuery = Query.of(q -> q
        .bool(b -> b
                .must(m -> m
                        .match(mm -> mm
                                .field("title")
                                .query("spring data")
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

NativeQuery query = NativeQuery.builder()
        .withQuery(esQuery)
        .withPageable(PageRequest.of(0, 20))
        .build();
```

And you still invoke Spring Data operations:

```java
SearchHits<ArticleDocument> hits =
        operations.search(query, ArticleDocument.class);
```

The core difference lies in the query type:

- Legacy: `org.elasticsearch.index.query.QueryBuilder`.
- Modern: `co.elastic.clients.elasticsearch._types.query_dsl.Query`.

You cannot pass a legacy `BoolQueryBuilder` into `NativeQuery.withQuery(...)`, because the two clients use different request models and data types.

### Using Lambda DSL Directly

The Elasticsearch Java API Client allows passing builder lambdas directly to `NativeQuery` in supported overloads. Example:

```java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
                .bool(b -> b
                        .must(m -> m.match(mm -> mm
                                .field("title")
                                .query("spring data")
                        ))
                        .filter(f -> f.term(t -> t
                                .field("status")
                                .value(FieldValue.of("PUBLISHED"))
                        ))
                )
        )
        .withPageable(PageRequest.of(0, 20))
        .build();
```

This reduces intermediate variables, though extracting a separate `Query esQuery` is often easier to read and reuse when queries are built from multiple conditional branches.

## 4. Differences Between the Two API Generations

| Aspect | Legacy: Spring Data ES 4.x | Modern: Spring Data ES 5.x+ |
|---|---|---|
| Elasticsearch client | Rest High Level Client (HLRC). | Elasticsearch Java API Client. |
| Native query class | `NativeSearchQuery`. | `NativeQuery`. |
| Builder | `NativeSearchQueryBuilder`. | `NativeQuery.builder()`. |
| Query condition | `QueryBuilder`, `BoolQueryBuilder`, `QueryBuilders`. | `co.elastic.clients.elasticsearch._types.query_dsl.Query`. |
| Sort DSL | Legacy builders such as `SortBuilders`. | Java API Client sort types or Spring Data `Sort` via query abstraction. |
| Query package | `org.elasticsearch.index.query.*`. | `co.elastic.clients.elasticsearch._types.query_dsl.*`. |
| Serialization/request model | HLRC request model. | Java API Client request model. |
| Query object reuse | Per HLRC and matching version. | Per Java API Client and matching version. |

Spring Data Elasticsearch 5.x does not merely wrap HLRC. It represents a change in client and request model, requiring updates to imports, dependencies, client configuration, and query-building code.

## 5. How Does `NativeQuery` Differ from `CriteriaQuery`?

Both `CriteriaQuery` and `NativeQuery` implement Spring Data's `Query` abstraction, yet they express conditions differently.

### CriteriaQuery: Spring Data Model Queries

Example:

```java
Criteria criteria = new Criteria("status").is("PUBLISHED")
        .and("publishedAt").greaterThanEqual(startDate);

CriteriaQuery query = new CriteriaQuery(criteria);
```

The Criteria API suits structured filter conditions easily generated from search forms or service parameters. It keeps application code from interacting directly with every Elasticsearch Query DSL type.

### NativeQuery: Elasticsearch Java API Client Queries

Example:

```java
Query esQuery = Query.of(q -> q
        .bool(b -> b
                .must(m -> m.match(mm -> mm
                        .field("body")
                        .query("distributed search")
                ))
                .should(s -> s.term(t -> t
                        .field("category")
                        .value(FieldValue.of("ENGINEERING"))
                ))
        )
);

NativeQuery query = NativeQuery.builder()
        .withQuery(esQuery)
        .build();
```

NativeQuery is appropriate when you need access to specific Query DSL capabilities such as nested queries, function score, script score, rank features, kNN, or complex bool structures. Available features also depend on your Elasticsearch server and Java API Client versions.

### Which API Should You Choose?

| Need | Recommended Option |
|---|---|
| Filtering by several fields and standard comparisons | `CriteriaQuery`. |
| Pre-existing static JSON query | `StringQuery`. |
| Bool/nested/function score/kNN or deep Query DSL | `NativeQuery`. |
| Legacy code using `NativeSearchQuery` on Spring Data ES 4.x | Keep within the older version scope or plan a structured migration to `NativeQuery` during upgrade. |

Do not use `NativeQuery` for every query. `CriteriaQuery` can be more maintainable for routine business conditions; reserve `NativeQuery` for when direct Query DSL control is needed.

## 6. `StringQuery` Is Not `NativeQuery`

Another misconception is treating `StringQuery` as the new native query. `StringQuery` takes Query DSL as a JSON string:

```java
StringQuery query = new StringQuery(
        """
        {
          "match": {
            "title": "spring data"
          }
        }
        """
);
```

`StringQuery` fits cases where JSON queries are already prepared or stored in resources/config. However:

- Because JSON is a plain string, syntax errors are usually caught only when parsed or executed.
- There is no compile-time type safety for field names or query structure.
- Dynamic queries require careful string assembly; never concatenate raw, unsanitized input.
- Refactoring large queries is harder than with typed builders.

`NativeQuery` uses the Java API Client DSL with type-safe builders, giving IDE autocomplete support and catching structural/type errors at compile time.

## 7. Migrating a Legacy Query to NativeQuery

Suppose legacy code searches for articles whose title contains `spring data`, status is `PUBLISHED`, sorted by newest publication date, returning the top 20 results.

### Legacy Code

```java
BoolQueryBuilder boolQuery = QueryBuilders.boolQuery()
        .must(QueryBuilders.matchQuery("title", "spring data"))
        .filter(QueryBuilders.termQuery("status", "PUBLISHED"));

NativeSearchQuery oldQuery = new NativeSearchQueryBuilder()
        .withQuery(boolQuery)
        .withSort(SortBuilders.fieldSort("published_at").order(SortOrder.DESC))
        .withPageable(PageRequest.of(0, 20))
        .build();
```

### Modern Code

```java
Query boolQuery = Query.of(q -> q
        .bool(b -> b
                .must(m -> m.match(mm -> mm
                        .field("title")
                        .query("spring data")
                ))
                .filter(f -> f.term(t -> t
                        .field("status")
                        .value(FieldValue.of("PUBLISHED"))
                ))
        )
);

NativeQuery newQuery = NativeQuery.builder()
        .withQuery(boolQuery)
        .withPageable(PageRequest.of(
                0,
                20,
                Sort.by(Sort.Order.desc("publishedAt"))
        ))
        .build();
```

In the modern example, the query DSL passes Elasticsearch field names directly into `field(...)`, such as `title` and `status`. `Pageable` is a Spring Data abstraction; sorting can reference the Java property `publishedAt` so mapping metadata resolves it to `published_at` if the entity declares `@Field(name = "published_at")`.

When migrating, do not merely swap class names. Compare old and new requests to verify that:

1. `must`, `filter`, `should`, and `must_not` clauses are preserved accurately.
2. Term and range value types match the mapping.
3. Sort, pageable, source filters, and routing are not lost.
4. Aggregations, highlights, suggestions, or advanced options are migrated completely if present.
5. Queries return the same document set and ordering required by business rules.

## 8. Sort, Pageable, and Query Options with NativeQuery

`NativeQuery` still works with familiar Spring Data abstractions such as `Pageable` and `Sort`:

```java
Pageable pageable = PageRequest.of(
        0,
        25,
        Sort.by(
                Sort.Order.desc("publishedAt"),
                Sort.Order.asc("slug")
        )
);

NativeQuery query = NativeQuery.builder()
        .withQuery(esQuery)
        .withPageable(pageable)
        .build();
```

This saves the application from manually setting `from` and `size` for ordinary pages. For deep queries, consider `search_after` and Point in Time rather than increasing offsets indefinitely.

`NativeQuery` also supports additional options via Spring Data's builder and Java API Client request types, depending on version. You may configure aggregations, highlighting, source filtering, track total hits, runtime fields, or specialized query components. Check the builder API in your project's exact dependencies before using a new method.

## 9. NativeQuery and ElasticsearchOperations

`NativeQuery` is a query object; it does not send requests to the cluster by itself. Execute it via `ElasticsearchOperations`:

```java
@Service
public class ArticleSearchService {

    private final ElasticsearchOperations operations;

    public ArticleSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public SearchHits<ArticleDocument> search(String text) {
        Query esQuery = Query.of(q -> q
                .match(m -> m
                        .field("title")
                        .query(text)
                )
        );

        NativeQuery query = NativeQuery.builder()
                .withQuery(esQuery)
                .withPageable(PageRequest.of(0, 20))
                .build();

        return operations.search(query, ArticleDocument.class);
    }
}
```

`ElasticsearchOperations` remains Spring Data's abstraction for executing queries and converting results into domain objects. `SearchHits<T>` provides hits along with metadata such as scores and total hit counts per tracking settings.

If you need to invoke an Elasticsearch API for which Spring Data lacks a suitable abstraction, you can inject `ElasticsearchClient` and call the Java API Client directly. However, in that case the application handles mapping/serialization and responses directly using that API. Never instantiate a new client per request; reuse the Spring-managed client.

## 10. Key Changes When Upgrading from 4.x to 5.x

Upgrading from Spring Data Elasticsearch 4.x to 5.x impacts more than query builders:

### Dependencies and Client

- Spring Data Elasticsearch 4.x typically uses the Rest High Level Client.
- Spring Data Elasticsearch 5.x switches to the Elasticsearch Java API Client.
- Inspect the dependency tree to avoid accidentally pulling both legacy and modern clients simultaneously.
- Prefer Spring Boot dependency management / BOM to keep Spring Data and Elasticsearch client versions compatible.

### Imports and Data Types

Imports from `org.elasticsearch.index.query.*` and `org.elasticsearch.search.sort.*` of HLRC are no longer the query/sort types used in the new Java API Client. Replace them with types under `co.elastic.clients.elasticsearch.*` or Spring Data `Sort` as appropriate.

### Client Configuration

Connection, authentication, TLS, and transport configurations also change with the new client. Do not update only query classes while leaving the entire legacy HLRC configuration untouched without reviewing Spring Boot auto-configuration.

### Features and Responses

Request and response models can differ. If code reads aggregations, highlights, suggestions, profiles, or metadata from legacy responses, update access logic accordingly. Write integration tests for critical flows instead of assuming the new response structure mirrors HLRC identically.

### Version Compatibility Checks

Spring Boot, Spring Data Elasticsearch, Elasticsearch Java API Client, and Elasticsearch server must stay within the compatibility matrix. Do not upgrade a single client dependency outside the BOM without verifying compatibility.

## 11. Common Mistakes When Migrating from NativeSearchQuery to NativeQuery

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Cannot import `NativeSearchQueryBuilder` | Project has upgraded to Spring Data Elasticsearch 5.x. | Switch to `NativeQuery.builder()`. |
| `withQuery` rejects `BoolQueryBuilder` | `BoolQueryBuilder` belongs to HLRC, while `NativeQuery` expects Java API Client query types. | Build `co.elastic.clients.elasticsearch._types.query_dsl.Query`. |
| `QueryBuilders` not found | Still using legacy imports from `org.elasticsearch.index.query`. | Use typed builders from the Elasticsearch Java API Client. |
| Sort field stops working after migration | Confused Java property name with Elasticsearch field name, or mapping changed. | Check `@Field`, live mapping, and the Query DSL sent. |
| Results differ from legacy code | Bool clauses, analyzers, sort, or value types changed. | Compare legacy vs. modern requests and run regression tests. |
| Aggregations or highlights missing | Migrated only the main query while dropping other `NativeSearchQuery` options. | Inventory all legacy options and migrate each part. |
| Runtime class/version errors | Incompatible HLRC, Java API Client, or Spring Data dependencies. | Inspect dependency tree and apply the right BOM. |
| Old and new code share `QueryBuilder` types | The two clients have separate request models. | Isolate adapters by version or migrate query builders completely. |

## 12. Practical Migration Strategy

When upgrading a large application, migrate queries group by group rather than rewriting everything at once without verification.

1. **Inventory legacy queries:** locate usages of `NativeSearchQuery`, `NativeSearchQueryBuilder`, `QueryBuilders`, `BoolQueryBuilder`, `SortBuilders`, and HLRC classes.
2. **Categorize queries:** simple queries can move to `CriteriaQuery`; static JSON queries can use `StringQuery`; complex Query DSL should move to `NativeQuery`.
3. **Migrate query by query:** rebuild conditions with Java API Client DSL while preserving semantics.
4. **Verify mappings:** confirm field names, types, analyzers, and nested paths.
5. **Compare results:** run identical datasets and queries in a test environment, comparing IDs, ordering, scores, and aggregations where needed.
6. **Check performance:** measure latency and cluster load with the migrated queries.
7. **Remove legacy dependencies:** remove HLRC only after no code depends on it and all other components have been migrated.

For queries with multiple logical branches, extract a dedicated `Query` factory method for easy unit testing:

```java
private Query buildArticleQuery(String text, String status) {
    return Query.of(q -> q
            .bool(b -> b
                    .must(m -> m.match(mm -> mm
                            .field("title")
                            .query(text)
                    ))
                    .filter(f -> f.term(t -> t
                            .field("status")
                            .value(FieldValue.of(status))
                    ))
            )
    );
}
```

The service remains responsible for preparing parameters, attaching pageable/sort, and executing the query. This keeps service methods from growing overly long when conditions change.

## 13. When Should You Avoid `NativeQuery`?

`NativeQuery` is powerful and flexible, yet it couples code more closely to Elasticsearch's Query DSL. Do not use it if requirements can be expressed clearly with `CriteriaQuery` or repository query methods.

Consider these guidelines:

- Use derived query methods for simple, stable queries with clear method names.
- Use `CriteriaQuery` when dynamically assembling conditions from multiple parameters.
- Use `StringQuery` when JSON DSL is managed as a resource and rarely changes.
- Use `NativeQuery` when you need Query DSL capabilities that higher-level abstractions do not express cleanly.
- Use the Java API Client directly when you need cluster APIs or low-level request/response features not covered by Spring Data abstractions.

Choosing an abstraction that is just sufficient keeps code less coupled to Elasticsearch internals and easier to evolve. Still, for specialized search features, `NativeQuery` is the natural choice in modern Spring Data Elasticsearch.

## 14. Key Points to Remember

- `NativeSearchQuery` and `NativeSearchQueryBuilder` belong to the legacy Spring Data Elasticsearch generation built on Rest High Level Client.
- `NativeQuery` in Spring Data Elasticsearch 5.x+ is built on the new Elasticsearch Java API Client.
- Legacy queries use `org.elasticsearch.index.query.QueryBuilder`; modern queries use `co.elastic.clients.elasticsearch._types.query_dsl.Query`.
- The two query types are not directly compatible; legacy `BoolQueryBuilder` cannot be passed into `NativeQuery`.
- `NativeQuery.builder()` combines modern Query DSL with `Pageable`, `Sort`, and Spring Data options supported by your version.
- `CriteriaQuery` fits structured conditions; `StringQuery` accepts JSON DSL strings; `NativeQuery` uses typed Java API Client DSL.
- `ElasticsearchOperations.search(...)` remains the standard way to execute queries in the Spring Data layer.
- During migration, inventory queries, sorting, aggregations, highlighting, client configuration, and response handling.
- Use proper dependency management and integration tests to verify that migrated queries preserve results, ordering, and performance.

Understanding the distinction between `NativeQuery` and legacy query APIs helps prevent type errors when upgrading Spring Data Elasticsearch. Treat this as a shift from HLRC to the Elasticsearch Java API Client, select the right abstraction for each query, and verify real behavior before removing legacy code.
