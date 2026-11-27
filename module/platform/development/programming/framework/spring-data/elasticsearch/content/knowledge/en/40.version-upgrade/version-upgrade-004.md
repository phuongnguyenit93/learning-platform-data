# Replacing Legacy APIs Like ElasticsearchRestTemplate and NativeSearchQuery by Version Line

Spring Data Elasticsearch changed its underlying client between the 4.x and 5.x lines. In 4.x, applications typically used the Elasticsearch Rest High Level Client (HLRC), `ElasticsearchRestTemplate`, and `NativeSearchQuery`. Starting in 5.x, Spring Data moved to the Elasticsearch Java API Client; the corresponding imperative template is `ElasticsearchTemplate`, and native queries use `NativeQuery`.

This is a shift in client architecture and Query DSL, not merely a class rename. Types such as HLRC's `org.elasticsearch.index.query.QueryBuilder` cannot be passed directly to the Java API Client. When upgrading, align Spring Boot, Spring Data Elasticsearch, the Elasticsearch server, and client dependencies; then migrate configuration, query builders, aggregations, sorting, bulk operations, and direct client integration points.

This guide explains how to identify APIs by version line, replace `ElasticsearchRestTemplate` and `NativeSearchQuery`, migrate legacy Query DSL to the Java API Client DSL, handle dependencies/configuration, keep abstractions stable, and test the migration step by step.

## 1. Start by identifying the version line

Class names alone are not enough to determine which API is in use. Check the dependency tree, source imports, and Spring Boot BOM version.

The two main lines compare as follows:

| Component | Spring Data Elasticsearch 4.x | Spring Data Elasticsearch 5.x |
|---|---|---|
| Primary client | Elasticsearch Rest High Level Client (HLRC) | Elasticsearch Java API Client |
| Typical client type | `RestHighLevelClient` | `ElasticsearchClient` |
| Imperative template | `ElasticsearchRestTemplate` | `ElasticsearchTemplate` |
| Native query | `NativeSearchQuery` / `NativeSearchQueryBuilder` | `NativeQuery` |
| Query builder | `org.elasticsearch.index.query.QueryBuilders` | Java API Client generated DSL |
| Aggregation builder | `org.elasticsearch.search.aggregations.AggregationBuilders` | Java API Client Aggregation builders |
| HTTP transport | `RestClient` beneath HLRC | `RestClient` + `ElasticsearchTransport` beneath Java API Client |
| Framework baseline | Spring Framework 5 / Boot 2.x line | Spring Framework 6 / Boot 3.x line |
| Java baseline | Depends on 4.x release; later releases support Java 8+ | Java 17+ |

This table outlines the common migration direction and does not replace the official compatibility table for an exact release. Minor/patch releases may change supported Elasticsearch server/client versions. Check the release train and dependency management before choosing a version pair.

### 1.1. Check actual dependencies

With Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-data-elasticsearch --configuration runtimeClasspath
./gradlew dependencyInsight --dependency elasticsearch-rest-high-level-client --configuration runtimeClasspath
./gradlew dependencyInsight --dependency elasticsearch-java --configuration runtimeClasspath
~~~

With Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-elasticsearch
mvn dependency:tree -Dincludes=org.elasticsearch.client:elasticsearch-rest-high-level-client
mvn dependency:tree -Dincludes=co.elastic.clients:elasticsearch-java
~~~

Check the versions managed by the Spring Boot BOM as well. Do not upgrade `spring-data-elasticsearch` or `elasticsearch-java` independently to an arbitrary version when Boot manages those dependencies.

### 1.2. Distinguish the three client layers

During migration, names containing "Rest" can be misleading:

- `RestHighLevelClient`: legacy high-level Java client used in Spring Data Elasticsearch 4.x.
- `RestClient`: low-level HTTP client, which may still sit beneath the new transport.
- `ElasticsearchClient`: new Java API Client providing type-safe/generated DSL APIs.

The fact that Spring Data 5.x uses `RestClient` at the HTTP layer does not mean the application still uses `ElasticsearchRestTemplate` or `RestHighLevelClient`. Do not rename classes by intuition; identify the proper abstraction at each layer.

## 2. 4.x line: the legacy model with ElasticsearchRestTemplate

In Spring Data Elasticsearch 4.x, common configurations are built around `RestHighLevelClient`. `ElasticsearchRestTemplate` implements `ElasticsearchOperations` and executes operations through that client.

Common import examples:

~~~java
import org.elasticsearch.client.RestHighLevelClient;
import org.springframework.data.elasticsearch.core.ElasticsearchRestTemplate;
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.data.elasticsearch.core.query.NativeSearchQuery;
import org.springframework.data.elasticsearch.core.query.NativeSearchQueryBuilder;
~~~

Some applications instantiate the template directly:

~~~java
@Bean
public ElasticsearchOperations elasticsearchOperations(
        RestHighLevelClient client) {
    return new ElasticsearchRestTemplate(client);
}
~~~

Detailed configuration may use `AbstractElasticsearchConfiguration`, `ClientConfiguration`, and `RestClients` depending on the minor version. Keep client creation centralized in configuration rather than creating new `RestHighLevelClient` instances inside services.

### 2.1. Use interfaces instead of depending on concrete templates

Even on 4.x, services should inject `ElasticsearchOperations` when they only need Spring Data operations:

~~~java
@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }
}
~~~

`ElasticsearchRestTemplate` is a concrete implementation. `ElasticsearchOperations` is a better abstraction for typical repository/template operations.

When upgrading, having services already depend on `ElasticsearchOperations` reduces the number of files that need changes. If code injects `ElasticsearchRestTemplate` directly, switch to the interface before or during migration to avoid tying services to the old implementation.

## 3. 5.x line: Java API Client and ElasticsearchTemplate

Starting with Spring Data Elasticsearch 5.x, the primary client shifts to the Elasticsearch Java API Client. Spring Data configuration typically extends `ElasticsearchConfiguration` and provides a `ClientConfiguration`.

Example configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;

@Configuration
public class ElasticsearchConfig extends ElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
            .connectedTo("localhost:9200")
            .build();
    }
}
~~~

With this configuration, Spring Data creates the corresponding client and operations beans. Class/package names must match the release in use; in 5.x, the new imperative implementation is typically `ElasticsearchTemplate` in the `client.elc` package.

If a service only needs operations, continue injecting `ElasticsearchOperations`:

~~~java
@Service
public class ProductSearchService {

    private final ElasticsearchOperations operations;

    public ProductSearchService(ElasticsearchOperations operations) {
        this.operations = operations;
    }
}
~~~

If you truly need to call the Elasticsearch Java API Client directly, inject `ElasticsearchClient` instead of the legacy `RestHighLevelClient`.

### 3.1. TLS and authentication configuration

`ClientConfiguration` remains the central place to configure hosts, SSL, and authentication in 5.x:

~~~java
@Override
public ClientConfiguration clientConfiguration() {
    return ClientConfiguration.builder()
        .connectedTo("es.internal.example:9200")
        .usingSsl()
        .withBasicAuth(
            System.getenv("ES_USERNAME"),
            System.getenv("ES_PASSWORD")
        )
        .build();
}
~~~

The example above uses the runtime's default SSL trust configuration. If the cluster uses an internal CA, configure a truststore/`SSLContext` using the API for the exact release. Never use a trust-all configuration just to bypass certificate errors during migration.

### 3.2. Do not manually create a second client unnecessarily

If Spring Data already creates `ElasticsearchClient`/`ElasticsearchTemplate`, avoid creating a second `RestClient` or `ElasticsearchClient` for the same endpoint without a clear reason.

Multiple clients can lead to:

- Duplicate connection pools.
- Inconsistent TLS/authentication settings.
- Hard-to-manage lifecycles and shutdowns.
- Divergent metrics and timeouts.
- Repositories using one client while another service uses a different client.

Only create a custom client when distinct transport or behavior is required, and manage its bean/lifecycle explicitly.

## 4. How is ElasticsearchRestTemplate replaced?

In a migration from 4.x to 5.x, the standard replacement is:

~~~text
ElasticsearchRestTemplate
        |
        v
ElasticsearchTemplate
~~~

However, a better choice in business services is usually:

~~~text
ElasticsearchRestTemplate (concrete dependency)
        |
        v
ElasticsearchOperations (stable abstraction)
~~~

Services invoke Spring Data operations such as `save`, `search`, `get`, `delete`, and `bulkIndex` through the interface. Spring Data 5.x provides the new implementation in `client.elc`.

### 4.1. Before: injecting the old concrete class

~~~java
@Service
public class ProductService {

    private final ElasticsearchRestTemplate template;

    public ProductService(ElasticsearchRestTemplate template) {
        this.template = template;
    }

    public void save(Product product) {
        template.save(product);
    }
}
~~~

### 4.2. After: injecting the operations abstraction

~~~java
@Service
public class ProductService {

    private final ElasticsearchOperations operations;

    public ProductService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void save(Product product) {
        operations.save(product);
    }
}
~~~

This avoids coupling to concrete implementation names. If Java API Client-specific APIs are required, create a dedicated component depending on `ElasticsearchClient` and keep its scope narrow.

### 4.3. Template APIs to review

Do not assume every overload of `ElasticsearchRestTemplate` shares the exact same signature in `ElasticsearchTemplate`. Review call sites for:

- `search` and `searchForPage`.
- `get` and `multiGet`.
- `save` and `index`.
- `delete`.
- `bulkIndex`, `bulkUpdate`, `bulkDelete`.
- `indexOps` and `IndexOperations`.
- `refresh` and refresh policies.
- Custom callbacks or request options.
- `NativeQuery`/`CriteriaQuery`/`StringQuery`.
- Methods returning `SearchHits`, `SearchPage`, or `SearchScrollHits`.

Core abstractions may remain, yet parameter types, response types, or client configuration may change. Use the compiler to find breakage and consult the Javadoc of the target version.

## 5. NativeSearchQuery is replaced by NativeQuery

This is a key change when migrating query code.

The 4.x line typically uses:

- `NativeSearchQuery`.
- `NativeSearchQueryBuilder`.
- `QueryBuilders` from Elasticsearch HLRC.
- `SortBuilders` and `AggregationBuilders` from HLRC.

The 5.x line uses `NativeQuery` and the Java API Client DSL. Queries are expressed using types in `co.elastic.clients.elasticsearch._types.query_dsl`.

### 5.1. Legacy query: NativeSearchQueryBuilder

Example query searching `title` and filtering by `status`:

~~~java
import org.elasticsearch.index.query.QueryBuilders;
import org.springframework.data.elasticsearch.core.query.NativeSearchQuery;
import org.springframework.data.elasticsearch.core.query.NativeSearchQueryBuilder;
import org.springframework.data.domain.PageRequest;

NativeSearchQuery query = new NativeSearchQueryBuilder()
    .withQuery(
        QueryBuilders.boolQuery()
            .must(
                QueryBuilders.matchQuery("title", "spring data")
            )
            .filter(
                QueryBuilders.termQuery("status.keyword", "published")
            )
    )
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

### 5.2. New query: NativeQuery

In the 5.x line, the equivalent query can be built with the Java API Client DSL:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.domain.PageRequest;

NativeQuery query = NativeQuery.builder()
    .withQuery(q -> q
        .bool(b -> b
            .must(m -> m
                .match(match -> match
                    .field("title")
                    .query("spring data")
                )
            )
            .filter(f -> f
                .term(term -> term
                    .field("status.keyword")
                    .value("published")
                )
            )
        )
    )
    .withPageable(PageRequest.of(0, 20))
    .build();
~~~

Execute via `operations`:

~~~java
SearchHits<Article> hits =
    operations.search(query, Article.class);
~~~

Key differences:

- Do not use `org.elasticsearch.index.query.QueryBuilders`.
- Do not pass an HLRC `QueryBuilder` into `NativeQuery`.
- The new DSL uses builders/lambdas from the Elasticsearch Java API Client.
- Field paths, query semantics, and analyzers must still match the actual mapping.

### 5.3. Using Query.of when building an object beforehand

You can build a Java API Client `Query` and pass it into `NativeQuery`:

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

Query queryDsl = Query.of(q -> q
    .match(m -> m
        .field("title")
        .query("spring data")
    )
);

NativeQuery query = NativeQuery.builder()
    .withQuery(queryDsl)
    .build();
~~~

This is helpful when the Query DSL is constructed in a helper or reused across queries.

## 6. Migrating individual legacy query builders to the new DSL

There is no mechanical rename for every `QueryBuilders` method. Translate according to query semantics.

| HLRC 4.x | Java API Client DSL in 5.x |
|---|---|
| `QueryBuilders.matchQuery` | `q.match(...)` |
| `QueryBuilders.termQuery` | `q.term(...)` |
| `QueryBuilders.termsQuery` | `q.terms(...)` |
| `QueryBuilders.rangeQuery` | `q.range(...)` |
| `QueryBuilders.boolQuery` | `q.bool(...)` |
| `QueryBuilders.existsQuery` | `q.exists(...)` |
| `QueryBuilders.prefixQuery` | `q.prefix(...)` |
| `QueryBuilders.wildcardQuery` | `q.wildcard(...)` |
| `QueryBuilders.nestedQuery` | `q.nested(...)` |
| `QueryBuilders.matchAllQuery` | `q.matchAll(...)` |
| `QueryBuilders.queryStringQuery` | `q.queryString(...)` |
| `QueryBuilders.multiMatchQuery` | `q.multiMatch(...)` |

These lambdas illustrate the generated Java API Client DSL. Enum names, value types, and overloads must be confirmed against the client version managed by Spring Data.

### 6.1. Match query

Old:

~~~java
QueryBuilders.matchQuery("description", "wireless mouse");
~~~

New:

~~~java
q -> q.match(m -> m
    .field("description")
    .query("wireless mouse")
)
~~~

### 6.2. Term query

Old:

~~~java
QueryBuilders.termQuery("status.keyword", "published");
~~~

New:

~~~java
q -> q.term(t -> t
    .field("status.keyword")
    .value("published")
)
~~~

Term queries do not analyze the input string like match queries. Use a `keyword` field or a field type with matching semantics.

### 6.3. Range query

Old:

~~~java
QueryBuilders.rangeQuery("price")
    .gte(100)
    .lte(500);
~~~

New:

~~~java
q -> q.range(r -> r
    .number(n -> n
        .field("price")
        .gte(100.0)
        .lte(500.0)
    )
)
~~~

The Java API Client features typed range variants in newer releases. The example above shows a numeric range. Date ranges have corresponding value representations; do not pass numbers to a date field or vice versa without checking the mapping.

### 6.4. Bool query

Old:

~~~java
QueryBuilders.boolQuery()
    .must(QueryBuilders.matchQuery("title", "elasticsearch"))
    .filter(QueryBuilders.termQuery("active", true))
    .mustNot(QueryBuilders.termQuery("deleted", true));
~~~

New:

~~~java
q -> q.bool(b -> b
    .must(m -> m.match(mm -> mm
        .field("title")
        .query("elasticsearch")
    ))
    .filter(f -> f.term(t -> t
        .field("active")
        .value(true)
    ))
    .mustNot(n -> n.term(t -> t
        .field("deleted")
        .value(true)
    ))
)
~~~

Preserve `must`, `should`, `filter`, and `must_not` accurately. Do not convert every clause into `must`; doing so alters scoring and results.

### 6.5. Prefix and wildcard

Old:

~~~java
QueryBuilders.prefixQuery("username.keyword", "admin");
QueryBuilders.wildcardQuery("path.keyword", "*timeout");
~~~

New:

~~~java
q -> q.prefix(p -> p
    .field("username.keyword")
    .value("admin")
)
~~~

~~~java
q -> q.wildcard(w -> w
    .field("path.keyword")
    .value("*timeout")
)
~~~

Migration is not the time to blindly keep every wildcard if that query is causing load. Review semantics, leading wildcards, mappings, and expensive-query policies before porting verbatim.

## 7. Migrating sorting

The 4.x line may use `SortBuilders` or Spring Data `Sort`:

~~~java
.withSort(
    SortBuilders.fieldSort("createdAt")
        .order(SortOrder.DESC)
)
~~~

In Spring Data 5.x, for ordinary field sorting, you can use Spring Data `Sort`:

~~~java
NativeQuery query = NativeQuery.builder()
    .withSort(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("productId")
    ))
    .build();
~~~

If you need all options of the Elasticsearch Java API Client, build `SortOptions`:

~~~java
import co.elastic.clients.elasticsearch._types.SortOptions;
import co.elastic.clients.elasticsearch._types.SortOrder;

SortOptions sort = SortOptions.of(s -> s
    .field(f -> f
        .field("createdAt")
        .order(SortOrder.Desc)
    )
);
~~~

Then pass it into `NativeQuery` using the `withSort` overload provided by your version.

Check:

- Whether the sort field has doc values.
- Whether a `text` field uses a `keyword` sub-field.
- Missing value policy.
- Multi-valued sort mode.
- Nested sort if the field resides inside a nested object.
- Stable tie-breakers for pagination.
- That sort order was not inverted when switching enums.

## 8. Migrating aggregations

The 4.x line typically uses `AggregationBuilders`:

~~~java
AggregationBuilder aggregation =
    AggregationBuilders.terms("by_status")
        .field("status.keyword")
        .size(20);
~~~

In the Java API Client, an aggregation is of type `Aggregation`:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;

Aggregation aggregation = Aggregation.of(a -> a
    .terms(t -> t
        .field("status.keyword")
        .size(20)
    )
);
~~~

Attach it to the query:

~~~java
NativeQuery query = NativeQuery.builder()
    .withAggregation("by_status", aggregation)
    .withMaxResults(0)
    .build();
~~~

Method names and how aggregation results are retrieved depend on the Spring Data/Java API Client release. In 5.x, responses are typically represented via the Java API Client's `Aggregate` type; do not assume legacy `InternalTerms`/`Terms` classes still exist.

After migration, check:

- Aggregation name.
- Field path.
- Bucket `size` and `shard_size`.
- Sub-aggregations.
- Key type.
- Doc values and fielddata requirements.
- How buckets/results are read from the new response.

## 9. Migrating query responses and SearchHits

Spring Data provides the `SearchHits` and `SearchHit` abstractions so applications do not have to depend directly on client response objects in many scenarios.

Example:

~~~java
SearchHits<Product> hits =
    operations.search(query, Product.class);

for (SearchHit<Product> hit : hits) {
    Product product = hit.getContent();
    float score = hit.getScore();
}
~~~

Check whether legacy code directly reads:

- HLRC `SearchResponse`.
- Legacy `SearchHits`/`SearchHit`.
- `Aggregations` or `InternalAggregations`.
- `TotalHits` relation.
- Highlight fields.
- Suggest responses.
- Explain/profile data.
- Scroll/PIT metadata.

If so, determine which parts can move to `SearchHits` or Spring Data result abstractions, and which parts require Java API Client response types.

Do not convert an old raw response type to a new raw response type by casting. Data types and access patterns differ.

## 10. CriteriaQuery and StringQuery can reduce migration scope

Not every query needs to be rewritten as a `NativeQuery`.

### 10.1. CriteriaQuery

`CriteriaQuery` suits simple conditions such as equality, ranges, and criteria combinations supported by Spring Data.

Example:

~~~java
Criteria criteria = new Criteria("status").is("published")
    .and("price").greaterThan(100);

CriteriaQuery query = new CriteriaQuery(criteria);
~~~

`CriteriaQuery` is a Spring Data abstraction that reduces coupling to generated client DSL for basic queries. However, not every Elasticsearch feature can be expressed through the Criteria API.

### 10.2. StringQuery

For JSON queries already stored in annotations or configuration, `StringQuery` can keep the JSON DSL intact as long as the syntax remains supported by the Elasticsearch server:

~~~java
StringQuery query = new StringQuery(
    "{\"match\":{\"title\":\"spring data\"}}"
);
~~~

This avoids using legacy `QueryBuilder`, though the JSON must still be valid for the target Elasticsearch version. Parts like kNN, runtime fields, aggregations, or newer options may still need updates.

### 10.3. Repository @Query

Repository methods using `@Query` with JSON may require fewer changes than Java query builders:

~~~java
@Query("{\"match\":{\"title\":\"?0\"}}")
List<Article> findByTitleText(String text);
~~~

Check parameter binding and JSON escaping in your exact version. Never concatenate user input directly into a JSON query string.

## 11. Migrating dependencies and avoiding mixing old/new clients

A common migration step is removing direct dependencies on HLRC once the application no longer uses it, and letting Spring Boot/Spring Data manage the Elasticsearch Java API Client.

Example Gradle dependency with the Spring Boot plugin/BOM:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-elasticsearch")
}
~~~

Usually you do not need to specify versions manually for `spring-data-elasticsearch` or `elasticsearch-java` when the Boot BOM already manages them. If not using Spring Boot, use the appropriate Spring Data BOM/release train.

Review legacy dependencies:

~~~gradle
// Remove when no longer required by application code:
implementation("org.elasticsearch.client:elasticsearch-rest-high-level-client")
~~~

Do not delete this dependency just because you spot it in the build file. First search for all direct imports and other libraries that still depend on HLRC.

Inspect the dependency tree after changes to detect:

- Two versions of `elasticsearch-java`.
- Remaining HLRC artifacts.
- Incompatible Elasticsearch server/client versions.
- Apache HTTP client version conflicts.
- `spring-data-elasticsearch` overridden away from the Boot BOM.
- Internal libraries still exposing `RestHighLevelClient` or legacy `QueryBuilder` types.

## 12. Common old and new imports

| Capability | 4.x Import | 5.x Import |
|---|---|---|
| High-level client | `org.elasticsearch.client.RestHighLevelClient` | `co.elastic.clients.elasticsearch.ElasticsearchClient` |
| Imperative template | `org.springframework.data.elasticsearch.core.ElasticsearchRestTemplate` | `org.springframework.data.elasticsearch.client.elc.ElasticsearchTemplate` |
| Native query | `org.springframework.data.elasticsearch.core.query.NativeSearchQuery` | `org.springframework.data.elasticsearch.client.elc.NativeQuery` |
| Query builder | `org.elasticsearch.index.query.QueryBuilders` | `co.elastic.clients.elasticsearch._types.query_dsl.Query` |
| Aggregation builder | `org.elasticsearch.search.aggregations.AggregationBuilders` | `co.elastic.clients.elasticsearch._types.aggregations.Aggregation` |
| Sort options | `org.elasticsearch.search.sort.SortBuilders` | `co.elastic.clients.elasticsearch._types.SortOptions` |
| Configuration | `AbstractElasticsearchConfiguration` (HLRC) | `ElasticsearchConfiguration` (ELC) |

Some Spring Data abstractions reside in shared packages and continue to be used. Do not swap imports in bulk by name alone; use your IDE/compiler and verify the target dependency's packages.

## 13. Repository configuration by version line

Repository interfaces can usually stay unchanged if they only use CRUD and query derivation:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategory(String category);
}
~~~

However, verify:

- Repository factories are configured by the proper configuration class.
- Client beans match the Spring Data line.
- Custom repository implementations do not use `RestHighLevelClient` or old `QueryBuilder`s.
- `@Query` JSON remains valid.
- Derived methods produce equivalent query semantics.
- Index creation/mapping lifecycles are not altered unintentionally.

Do not declare two repository configurations scanning the same package unintentionally; that can create duplicate beans or bind repositories to the wrong template.

## 14. Reactive APIs during an upgrade

Reactive applications must be migrated separately. You cannot take the imperative `ElasticsearchClient` and substitute it for the reactive client.

Areas to review:

- `ReactiveElasticsearchOperations`.
- `ReactiveElasticsearchTemplate` implementation.
- `ReactiveElasticsearchConfiguration`.
- Reactive repository factory.
- Reactive query/response types.
- Client transport and connection lifecycle.
- Retry/backpressure behavior.

Concrete class names and client configuration depend on the release line. Keep services depending on `ReactiveElasticsearchOperations` when possible; touch the concrete reactive client only at configuration/integration boundaries.

Do not use `block()` to force reactive code to call the imperative `ElasticsearchClient` on the request path. That defeats non-blocking execution and can stall the event loop.

## 15. Other APIs that may be affected

When removing HLRC, search the entire repository for old `org.elasticsearch.*` types. More than just templates and query builders can be affected.

Areas to check:

- `RestHighLevelClient` and `RequestOptions`.
- `SearchRequest`/`SearchResponse`.
- `IndexRequest`, `UpdateRequest`, `DeleteRequest`.
- `BulkRequest`/`BulkResponse`.
- `QueryBuilder` and `QueryBuilders`.
- `SortBuilder`/`SortBuilders`.
- `AggregationBuilder`/`AggregationBuilders`.
- `Script` and `ScriptType`.
- `HighlightBuilder`.
- `SearchSourceBuilder`.
- Scroll and clear scroll.
- Index settings/mapping requests.
- Low-level `RestClient` callbacks.
- Exception types and error parsing.

The Java API Client has its own request/response model. Certain REST endpoints can remain on the low-level `RestClient`, but isolate raw HTTP in a dedicated adapter rather than scattering it across domain services.

## 16. Bulk operations after migration

If code uses Spring Data `ElasticsearchOperations.bulkIndex`, `bulkUpdate`, or `bulkDelete`, verify signatures and failure semantics in the target version.

If code calls HLRC `BulkRequest` directly, migrate to Java API Client `BulkRequest` and `BulkResponse`:

~~~java
BulkResponse response = elasticsearchClient.bulk(request);

if (response.errors()) {
    for (BulkResponseItem item : response.items()) {
        if (item.error() != null) {
            // classify this item failure
        }
    }
}
~~~

This is the new API conceptually. Request operation builders, response item types, and metadata must match the client version. Bulk is not transactional; item-level failures, partial retries, and idempotency still require handling.

Do not simply make the code compile and consider the migration done. Test partial success and ambiguous timeout errors.

## 17. Exceptions and error handling

Exceptions can change packages and types across HLRC, the Java API Client, and Spring Data. Do not catch a legacy exception or cast a new one blindly.

Design error handling by layer:

1. Connection/transport errors.
2. Request serialization or validation errors.
3. HTTP/API errors from Elasticsearch.
4. Item-level failures in bulk operations.
5. Spring Data mapping/conversion errors.
6. Business errors such as not found or version conflict.

Preserve status, error type, index, document ID, and correlation ID in logs when possible. Never log credentials or full sensitive document sources.

## 18. Safe migration workflow

A roadmap can be split into phases:

### Phase 1: Inventory

- Identify Spring Boot, Spring Data Elasticsearch, and Elasticsearch server versions.
- Save the dependency tree.
- Find all imports of `RestHighLevelClient`, `ElasticsearchRestTemplate`, `NativeSearchQuery`, and `QueryBuilders`.
- Find custom repositories/templates, bulk calls, and low-level client usage.
- Record critical queries and response semantics.

### Phase 2: Upgrade framework and client

- Select a compatible Spring Boot/Spring Data release train.
- Upgrade the Java runtime to the new line's baseline.
- Use dependency management/BOM.
- Remove unnecessary client version overrides.
- Update configuration classes and transports.
- Verify TLS/authentication/timeouts.

### Phase 3: Reduce implementation coupling

- Inject `ElasticsearchOperations` instead of `ElasticsearchRestTemplate`.
- Inject `ReactiveElasticsearchOperations` for reactive services.
- Isolate raw client usage in dedicated adapters.
- Separate business query specifications from client builders in large codebases.

### Phase 4: Migrate queries

- Migrate `NativeSearchQuery` to `NativeQuery`.
- Migrate `QueryBuilders` to the Java API Client DSL.
- Migrate sorting and aggregations.
- Verify highlighting, suggestions, scripts, kNN, runtime fields, and query options.
- Keep `CriteriaQuery`/`StringQuery` where they meet requirements.

### Phase 5: Migrate remaining APIs

- Bulk operations.
- Index/mapping/settings.
- Scroll/PIT.
- Exception handling.
- Custom repositories.
- Reactive stack.
- Monitoring and low-level HTTP.

### Phase 6: Test and deploy

- Run unit/integration tests.
- Verify mappings and index lifecycles.
- Compare query results against the old version.
- Measure latency/throughput.
- Test partial bulk failures and retries.
- Test authentication, TLS, and timeouts.
- Roll out via canary/rolling deployment as operationally supported.
- Have a rollback plan and monitor errors post-deploy.

## 19. Testing query equivalence before and after migration

A query that compiles does not prove its semantics match the old version. For each critical query, build document fixtures and verify:

- Returned document IDs.
- Total hits and relation.
- Sort order.
- Filter behavior.
- Scoring if the application relies on scores.
- Aggregation buckets/keys/counts.
- Highlight fields.
- Missing field behavior.
- Date/timezone handling.
- Nested query semantics.
- Pagination and tie-breakers.

For example, given a dataset:

~~~text
Product A: title="Spring Data", status=published
Product B: title="Spring Boot", status=draft
Product C: title="Elasticsearch", status=published
~~~

A query matching title `Spring Data` and filtering status `published` must return the same document before and after migration. Do not merely assert the response is non-null.

### 19.1. Inspect actual query JSON

During migration, you can log request DSL in test environments or use Elasticsearch profiling/slow logs to verify the new query being sent. Never enable logging of sensitive payloads in production.

Compare semantics rather than requiring the JSON builder output to have identical field ordering; two DSLs can differ syntactically while behaving equivalently.

### 19.2. Test compatibility with a real cluster

Use Elasticsearch Testcontainers or a test cluster matching the target major/minor version. A mocked Java client will not catch issues with mappings, query rewrites, aggregation responses, or server compatibility.

## 20. Common errors during upgrade

| Error | Cause | Resolution |
|---|---|---|
| `ElasticsearchRestTemplate` not found | Moved to 5.x line | Use `ElasticsearchTemplate`/`ElasticsearchOperations` |
| `NativeSearchQuery` not found | Old native query API is no longer the new default | Use `NativeQuery` |
| `QueryBuilder` incompatible | `QueryBuilder` belongs to HLRC | Rewrite using Java API Client DSL |
| `QueryBuilders` not found | Old imports lack dependency | Use generated Query DSL |
| `RestHighLevelClient` cannot be injected | New configuration/client stack | Use `ElasticsearchClient` or `operations` |
| Two `operations` beans exist | Both old and new configs registered | Keep one explicit configuration |
| `ClassNotFound`/`NoSuchMethod` | Client/Spring Data version conflict | Use BOM and `dependencyInsight` |
| Query returns different results | Incorrect `must`/`filter`/`should` or field path conversion | Test semantics on fixtures |
| Aggregation results unreadable | New response types differ from HLRC | Use new `Aggregate` types or Spring Data abstraction |
| Sort fails with fielddata error | Pre-existing mapping/query mismatch | Use `keyword`/doc values |
| TLS fails after upgrade | Client transport/trust config changed | Configure `SSLContext`/truststore properly |
| Repository uses wrong client | Multiple configuration/template beans | Check repository factory and bean wiring |
| Reactive request blocks | Imperative client called in reactive flow | Use reactive operations/client |
| Bulk treats whole batch as success | Ignored `response.errors`/`items` | Inspect each item |

## 21. Risk-reduction strategies for large codebases

In large applications, avoid changing every query builder and template call in a single hard-to-review patch.

You can split the work:

- One commit upgrading dependencies/configuration.
- One commit switching injections to the `operations` interface.
- Commits migrating query groups incrementally.
- One commit migrating aggregations/bulk/raw client calls.
- One commit removing remaining HLRC dependencies and imports.
- A testing/benchmarking pass before release.

You can introduce internal adapters for heavily used queries:

~~~java
public interface ProductSearchQueries {
    NativeQuery findPublishedProducts(String text, int page, int size);
}
~~~

The new implementation uses the Java API Client DSL. Business services do not need to know which builder constructed the query. Do not create overly generic abstractions just to wrap every Elasticsearch feature; adapters should reflect specific use cases.

## 22. Pre-completion migration checklist

| Item | What to Verify |
|---|---|
| Version matrix | Boot, Spring Data, Java, and Elasticsearch server are compatible |
| Dependency BOM | Client version is not arbitrarily overridden |
| Old HLRC imports | No remaining code dependencies outside intentional adapters |
| Template | Services use `ElasticsearchOperations` where appropriate |
| Native query | `NativeSearchQuery` migrated to `NativeQuery` |
| Query DSL | No old `QueryBuilder` in new code paths |
| Sort/aggregation | Field paths and result parsing are accurate |
| Repository | Repository factory binds to the right `operations` bean |
| Reactive | No imperative client calls/`block` on reactive paths |
| TLS/auth | Truststore, hostname verification, and credentials are correct |
| Bulk | Item-level errors and retries are handled |
| Index mapping | Actual mappings align with entities/queries |
| Tests | Query results, sorting, aggregations, and pagination are equivalent |
| Observability | Metrics/logging are preserved after migration |
| Rollback | Plan exists to revert to compatible version/index |

## 23. Quick reference table

| Legacy API | Replacement Direction |
|---|---|
| `ElasticsearchRestTemplate` | `ElasticsearchTemplate` in 5.x; prefer injecting `ElasticsearchOperations` |
| `RestHighLevelClient` | `ElasticsearchClient` |
| `NativeSearchQuery` | `NativeQuery` |
| `NativeSearchQueryBuilder` | `NativeQuery.builder()` |
| `QueryBuilders` | Java API Client Query DSL |
| `AggregationBuilders` | Java API Client `Aggregation` |
| `SortBuilders` | Spring Data `Sort` or Java API Client `SortOptions` |
| HLRC `SearchResponse` | `SearchHits` abstraction or Java API Client response |
| HLRC abstract config | `ElasticsearchConfiguration` (ELC) |
| Raw HLRC `BulkRequest` | Java API Client `BulkRequest` or Spring Data bulk operations |
| Reactive concrete template | `ReactiveElasticsearchOperations` and version-appropriate implementation |

When replacing legacy Spring Data Elasticsearch APIs, identify the exact release train first. The 4.x line is centered on `RestHighLevelClient`, `ElasticsearchRestTemplate`, and `NativeSearchQuery`; the 5.x line shifts to the Elasticsearch Java API Client, `ElasticsearchTemplate`, and `NativeQuery`. `ElasticsearchOperations` should be preferred in services to reduce coupling to concrete templates. HLRC `QueryBuilder`, aggregations, and sorting are not directly compatible with the Java API Client DSL; translate them semantically and verify results. Align the Spring Boot BOM, Java runtime, client, and Elasticsearch server, then review bulk, reactive, mapping, TLS, exceptions, and raw client usage. Migration is complete only when query behavior, mappings, security, and operations are verified on the right server version—not merely when the source code compiles.
