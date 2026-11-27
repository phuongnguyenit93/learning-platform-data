# Query execution cost

## Objectives

After this lesson, you will be able to:

- Describe the stages of processing a GraphQL request on the server.
- Identify sources of CPU, I/O, memory, and bandwidth consumption during query execution.
- Estimate cost from the number of fields, depth, breadth, and size of nested collections.
- Explain why a shallow query can still be very expensive and a deep query is not necessarily expensive.
- Analyze N+1 issues and use DataLoader or @BatchMapping to reduce backend calls.
- Limit page size, query depth, query complexity, and execution time.
- Use GraphQL Java Instrumentation and Micrometer to measure performance.
- Distinguish document caching from data caching and choose the appropriate optimization.

## Cost of a GraphQL request

GraphQL allows clients to choose which fields appear in the response. This flexibility requires the server to handle many different query shapes, including queries with deeply nested fields or large collections.

A single request can consume resources in multiple places:

| Cost source | Example | Affected resources |
| --- | --- | --- |
| Parsing and validation | Parsing the document, checking fields, arguments, fragments, and variables | CPU, memory |
| Data fetching | Reading from a database, calling a REST API, or querying a message broker | I/O, connection pool, latency |
| Nested field resolution | Resolving author, reviews, and permissions for each object | CPU, number of backend calls |
| Collection completion | Iterating through and completing many elements of a list | CPU, memory |
| Scalar serialization | Converting data into response maps and JSON | CPU, memory |
| Response transfer | Returning a large payload over HTTP or WebSocket | Bandwidth, network time |
| Concurrent requests | Many queries loading large datasets simultaneously | Threads, connection pool, heap, and downstream capacity |

A query with only a few fields can still be expensive if one field calls a slow external service or loads tens of thousands of records. Conversely, a query with many scalar fields read from an already loaded object can be very cheap.

Therefore, field count is a signal for estimating cost, not a measure of execution time. You must combine query structure with how resolvers fetch data and the size of the returned data.

## Query processing stages

A GraphQL request goes through the following main steps:

~~~mermaid
flowchart TD
    A[GraphQL request] --> B[Parse document]
    B --> C[Validate against schema]
    C --> D[Coerce variables and select operation]
    D --> E[Execute root fields]
    E --> F[Resolve nested fields]
    F --> G[Complete lists and scalar values]
    G --> H[Build and serialize response]
    H --> I[Return response]
~~~

**Parsing and validation** converts the document into an AST structure and verifies the operation against the schema. If clients send the same document repeatedly, repeated parsing and validation can become a noticeable cost.

**Variable coercion and operation selection** checks variable values, applies default values, and determines which query or mutation to execute.

**Data fetching and field completion** is typically the part that takes the most time. GraphQL invokes data fetchers for the selected fields, then continues resolving nested fields and completing lists, objects, and scalars.

**Response serialization** builds the result according to the selection set and converts it to the transport format. Queries returning many objects and fields require more memory, even if the backend loaded the data quickly.

Spring for GraphQL uses ExecutionGraphQlService as the request execution abstraction. Transports such as HTTP forward requests to this service; GraphQlSource provides the configured GraphQL Java engine for execution. [Spring for GraphQL – Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)

## Query depth and query breadth

Depth is the number of nested field levels from the root to the deepest field. Breadth is the number of fields or items requested at the same level.

Deep query:

~~~graphql
query {
  me {
    manager {
      manager {
        manager {
          name
        }
      }
    }
  }
}
~~~

Wide query:

~~~graphql
query {
  books(first: 100) {
    id
    title
    publishedAt
    author {
      id
      name
    }
    publisher {
      id
      name
    }
    category {
      id
      name
    }
  }
}
~~~

The first query has many levels, but each level might only read a single object. The second query has fewer levels, yet can load 100 books along with multiple relationships.

A query can be both deep and wide when nested fields return lists:

~~~graphql
query {
  books(first: 50) {
    reviews(first: 20) {
      reviewer {
        friends(first: 10) {
          name
        }
      }
    }
  }
}
~~~

The potential number of objects at the final level can reach:

\[
50 \times 20 \times 10 = 10\,000
\]

This is only the number of elements at the friends level, not counting Book, Review, Reviewer, and other fields. A depth limit alone cannot prevent wide queries with large collections.

## Estimating cost from the selection set

A simple model can assign each field a base cost and multiply child costs by the number of elements a collection field can return.

Let:

- \(C(f)\) be the estimated cost of field f.
- \(B(f)\) be the base cost to process the field.
- \(M(f)\) be the expected maximum number of items if the field returns a collection.
- \(Children(f)\) be the selected child fields.

For a single field:

\[
C(f) = B(f) + \sum C(child)
\]

For a field returning a list:

\[
C(f) = B(f) + M(f) \times \max(1, \sum C(child))
\]

This is an illustrative model to understand how collections multiply cost. Production setups need adjustments based on resolvers, backend type, page size, and actual data. Complexity points should not be treated as milliseconds.

Example schema:

~~~graphql
type Query {
  books(first: Int = 20): [Book!]!
}

type Book {
  title: String!
  author: Author
  reviews(first: Int = 10): [Review!]!
}

type Author {
  name: String!
}

type Review {
  rating: Int!
  reviewer: User
}

type User {
  displayName: String!
}
~~~

Query:

~~~graphql
query {
  books(first: 50) {
    title
    author {
      name
    }
    reviews(first: 10) {
      rating
      reviewer {
        displayName
      }
    }
  }
}
~~~

In this example, the server may have to complete 50 Books, up to 500 Reviews, and up to 500 reviewer Users. Even though each field appears only once in the document, nested fields of a list are executed for each corresponding element.

When estimating cost, look at pagination arguments such as first and last, fields likely to return lists, and fields that call backends. A field calling a paid service or a complex search query may need a higher weight than a field reading a simple property.

### How do aliases and fragments affect cost?

Fragments help reuse selection sets:

~~~graphql
fragment BookCard on Book {
  id
  title
  author {
    name
  }
}

query {
  books(first: 20) {
    ...BookCard
  }
}
~~~

A fragment is not an independent fetch. GraphQL expands fragments into the selection set to determine which fields need to be executed.

Aliases create different response keys and can cause the same field to be executed multiple times:

~~~graphql
query {
  firstBook: book(id: "book-1") {
    title
  }
  secondBook: book(id: "book-1") {
    title
  }
}
~~~

Two aliases produce two separate response fields. Without appropriate caching in the resolver, the backend may be called twice even when accessing the same ID.

The @skip and @include directives affect which fields are executed based on variables. A complexity calculator needs to account for directive conditions if you want a more accurate estimate; do not assume every branch is always executed or always skipped.

## N+1 increases backend cost

A query may return 50 books, each with one author. If the resolver loads the author separately for each book, the number of database queries can be:

- One query to load the list of books.
- Fifty queries to load the authors.

Fifty-one queries in total. This is the N+1 problem.

Non-batching resolver:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorRepository.findById(book.authorId())
            .orElse(null);
}
~~~

When the author field is selected for 50 Books, the method can be invoked 50 times. The cost lies not only in method calls, but also in network round trips, connection pool usage, transactions, and database wait time.

### Using @BatchMapping

For a one-to-one relationship from Book to Author, you can load in a batch:

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        List<String> authorIds = books.stream()
                .map(Book::authorId)
                .distinct()
                .toList();

        Map<String, Author> authors =
                authorService.findAllByIds(authorIds);

        Map<Book, Author> result = new HashMap<>();
        books.forEach(book ->
                result.put(book, authors.get(book.authorId())));
        return result;
    }
}
~~~

In this example, the service can load all Authors by a list of IDs instead of running a query for each Book. HashMap allows null values if an Author is not found; the author field in the schema is also declared nullable. @BatchMapping creates a corresponding batch loader and data fetcher for the field. Keys in the Map must match the source objects; if using a Map with entities as keys, equality and hashCode must be stable.

### Using DataLoader and BatchLoaderRegistry

When you need more control, register a batch loader through BatchLoaderRegistry:

In this example, AuthorService.findAllByIds takes a set of author IDs and returns Mono<Map<String, Author>>.

~~~java
@Configuration
public class GraphQlBatchConfiguration {

    private final AuthorService authorService;

    public GraphQlBatchConfiguration(
            BatchLoaderRegistry registry,
            AuthorService authorService) {
        this.authorService = authorService;
        registry.forTypePair(String.class, Author.class)
                .registerMappedBatchLoader((authorIds, environment) ->
                        authorService.findAllByIds(authorIds));
    }
}
~~~

Then the resolver uses DataLoader:

~~~java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(
        Book book,
        DataLoader<String, Author> authorLoader) {

    return authorLoader.load(book.authorId());
}
~~~

DataLoader batches load() calls within the same request for batch dispatch and caches results by key within request scope. BatchLoaderRegistry registers loaders per request and supports sharing GraphQLContext with the batch loading function.

@BatchMapping works well for simple cases. BatchLoaderRegistry is more flexible when you need custom keys, context, or multiple loading strategies. [Spring for GraphQL – Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html)

Batching reduces backend round trips, but it does not eliminate the cost of completing each object or the response size. A query requesting 10,000 objects still requires the server to build and serialize 10,000 objects, even when loaded in a single batch.

## Limiting page size and collections

Do not let clients request arbitrary page sizes. The schema can declare pagination arguments:

~~~graphql
type Query {
  books(first: Int = 20, after: String): [Book!]!
}
~~~

The resolver must enforce server-side limits:

~~~java
@QueryMapping
public List<Book> books(@Argument Integer first) {
    int requested = first != null ? first : 20;
    int pageSize = Math.min(Math.max(requested, 1), 100);
    return bookService.findFirstPage(pageSize);
}
~~~

Do not enforce limits only in the UI or client SDK. Any client can send a direct request with first: 1000000.

For large collections, use cursor pagination or keyset pagination when appropriate. Cursors should be tied to a stable sort order; if sorting is unstable, clients may receive duplicates or miss items between pages. Spring for GraphQL supports Connection/Edge/PageInfo and adapters for Spring Data Window or Slice.

Cap page size at the resolver or service/repository layer, and also feed that limit into the query complexity calculator so the estimated score reflects the actual number of items the server can load.

## Limiting query depth and query complexity

GraphQL Java provides two useful instrumentations:

- MaxQueryDepthInstrumentation rejects queries exceeding the allowed number of levels.
- MaxQueryComplexityInstrumentation rejects queries exceeding the allowed complexity score.

Depth protects against excessively nested selection sets. Complexity helps control field counts and child costs; with a custom calculator, you can multiply costs by pagination arguments.

Example Spring Boot configuration using Instrumentation beans:

~~~java
import graphql.analysis.FieldComplexityCalculator;
import graphql.analysis.MaxQueryComplexityInstrumentation;
import graphql.analysis.MaxQueryDepthInstrumentation;
import graphql.execution.instrumentation.Instrumentation;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GraphQlQueryCostConfiguration {

    @Bean
    Instrumentation maxQueryDepthInstrumentation() {
        return new MaxQueryDepthInstrumentation(8);
    }

    @Bean
    Instrumentation maxQueryComplexityInstrumentation() {
        FieldComplexityCalculator calculator =
                (environment, childComplexity) -> {
                    if (environment.getFieldDefinition() == null) {
                        return 1 + childComplexity;
                    }

                    boolean paginated = environment.getFieldDefinition()
                            .getArguments().stream()
                            .anyMatch(argument ->
                                    argument.getName().equals("first")
                                    || argument.getName().equals("last"));

                    if (!paginated) {
                        return 1 + childComplexity;
                    }

                    Object rawSize = environment.getArguments().get("first");
                    if (!(rawSize instanceof Number)) {
                        rawSize = environment.getArguments().get("last");
                    }

                    int pageSize = rawSize instanceof Number number
                            ? number.intValue()
                            : 20; // Must match the resolver's default page size.

                    return 1 + Math.max(1, pageSize)
                            * Math.max(1, childComplexity);
                };

        return new MaxQueryComplexityInstrumentation(1500, calculator);
    }
}
~~~

The Spring Boot GraphQL starter detects Instrumentation beans to register them into the GraphQL engine. If you construct GraphQlSource manually, register instrumentations on GraphQlSource.Builder or GraphQL.Builder. When the application already has instrumentations for metrics/tracing, combine them using ChainedInstrumentation rather than accidentally overwriting existing instrumentations.

In this example:

- Maximum query depth is 8 levels.
- Each field has a base cost of 1 plus its child complexity.
- Fields with first or last multiply child complexity by page size.
- If no page size is provided, the calculator uses 20, which must stay synchronized with the resolver's default.
- Maximum complexity is 1500 points.

These numbers are only illustrative values. Calibrate them based on benchmarks and real traffic. If resolvers use other arguments like limit, count, or pageSize, the calculator must account for those arguments as well. If a field is expensive due to calling an external service, assign a custom weight to that field.

GraphQL Java's default complexity calculator adds one unit for the field and child complexity (1 + childComplexity). It does not automatically infer how many items a resolver will return. Therefore, queries books(first: 1000) and books(first: 1) can produce the same score with the default calculator. A custom FieldComplexityCalculator lets you include page size in the estimate.

Depth and complexity are pre-execution guards; they do not replace business validation, page size caps, authorization, or per-user rate limiting.

## Caching parsing and validation

GraphQL Java must parse and validate a document before execution. If a stable operation is called repeatedly, you can cache parse/validation results using PreparsedDocumentProvider.

Spring for GraphQL allows registering a PreparsedDocumentProvider via GraphQlSource.Builder#configureGraphQl. Options include:

- Caching parsed and validated documents by query text.
- Using persisted queries so clients reference registered operations.
- Using an operation allowlist for APIs with a controlled set of queries.

Document caching reduces parsing/validation CPU when the same operation is sent repeatedly. It does not cache database data, does not bypass authorization, and does not make resolvers run faster.

When implementing caching:

- Set a maximum size limit and eviction policy.
- Avoid unbounded caching of unique query texts generated dynamically by clients.
- Consider invalidation when the schema changes.
- With persisted queries, verify that the operation ID maps to the expected document.
- Do not use document caching as a data protection mechanism.

If you need response caching, that is a separate layer. Response caching must consider variables, principal, tenant, permissions, and data freshness; never share cached responses containing private data across users.

## Query timeout and cancellation

A request can consume resources for too long due to a slow database, downstream timeout, or a non-completing publisher. Spring for GraphQL provides TimeoutWebGraphQlInterceptor for web transports:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.TimeoutWebGraphQlInterceptor;

@Configuration(proxyBeanMethods = false)
public class GraphQlTimeoutConfiguration {

    @Bean
    TimeoutWebGraphQlInterceptor graphQlTimeoutWebInterceptor() {
        return new TimeoutWebGraphQlInterceptor(Duration.ofSeconds(5));
    }
}
~~~

When a request exceeds the timeout, the interceptor sends a cancellation signal up the processing chain. Reactive data fetchers can receive cancellation and stop ongoing work. This is a time limit for requests going through the web handler; downstream clients and databases should still have their own timeouts.

Not every blocking operation can be stopped immediately when a GraphQL request times out. If a resolver is blocking inside JDBC or a library that does not support interruption/cancellation, you need timeouts at the driver/client level or execute on an appropriate executor.

## Execution model and concurrency

GraphQL Java uses AsyncExecutionStrategy for queries by default. Sibling fields can be launched concurrently if data fetchers return CompletionStage or reactive types supported by Spring for GraphQL adapters.

This reduces wait time when a query needs multiple independent data sources. However, it also means multiple resolvers may run at the same time:

- Do not share non-thread-safe mutable state across requests or fields.
- Do not spawn excessive new threads inside each resolver.
- Monitor database and HTTP client connection pool limits.
- Use batch loading to reduce downstream work instead of merely increasing concurrency.
- Do not call blocking repositories on the WebFlux event loop.

With Spring WebFlux, data fetchers should return Mono, Flux, or CompletionStage appropriate to the data source. A blocking call placed inside Mono.just(blockingCall()) still runs blocking before the Mono is even created. Choose reactive drivers or an appropriate executor for blocking work.

Mutation root fields are executed sequentially per GraphQL semantics. Do not assume mutations can run in parallel like queries; order may matter because each field can mutate state.

Spring for GraphQL supports reactive data fetchers, CompletionStage, Kotlin coroutines, and Callable for @SchemaMapping/@BatchMapping when an appropriate executor is configured. [Spring for GraphQL – Thread Model](https://docs.spring.io/spring-graphql/reference/request-execution.html)

## Measuring and observing query execution

Do not optimize based on guesswork or total duration alone. Measure requests and key data fetchers.

Spring for GraphQL integrates with Micrometer Observation:

| Observation | Meaning | Useful data |
| --- | --- | --- |
| graphql.request | Entire GraphQL request | Operation type, outcome, operation name, execution ID |
| graphql.datafetcher | Non-trivial data fetcher | Field name, field path, duration, and outcome |
| graphql.dataloader | Batch loader and @BatchMapping | Loader name, number of loaded items, outcome |

To emit observations, the application needs an ObservationRegistry and GraphQlObservationInstrumentation configured. Spring Boot provides auto-configuration for GraphQL observation when the appropriate observability infrastructure is enabled.

Data fetcher observations are only created for non-trivial fetch operations. Simple property reads from Java objects typically do not generate separate observations. DataLoader observations track @BatchMapping and registered DataLoaders.

When inspecting dashboards or traces, look for:

- Operations with abnormally high p95/p99 latency.
- Field paths with high processing time.
- DataLoaders with small batch sizes or abnormally high dispatch counts.
- Increases in request errors or timeouts after schema/resolver changes.
- Discrepancies between GraphQL request duration and database/downstream duration.

Do not put raw queries, emails, user IDs, or high-cardinality argument values into metric tags. Use operation name, field name, outcome, and execution ID for tracing; keep sensitive information in access-controlled logs/traces.

## How to benchmark a query

A repeatable measurement workflow:

1. Prepare a dataset whose volume and relationship distribution resemble production.
2. Send operations with fixed page sizes and selection sets.
3. Warm up the application and connection pool before recording metrics.
4. Measure p50, p95, p99, throughput, and error rate.
5. Record database query counts, downstream call counts, batch sizes, and response bytes.
6. Increase concurrency to observe when the connection pool or CPU saturates.
7. Change one factor at a time: pagination, batching, selection set, caching, or resolver.
8. Compare under the same conditions before and after the change.

For slow databases, use query plans or EXPLAIN ANALYZE at the database layer to identify whether the bottleneck is an index, join, sort, or rows scanned. A GraphQL field may appear fast in the resolver while the underlying SQL query still scans too much data.

Do not measure only once locally. Network latency, connection pools, warm/cold caches, and concurrent load can make production results very different.

## Common pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Query has few fields but is still slow | A resolver calls a slow downstream service or runs a poor database query | Measure data fetcher and query plan |
| Low query depth but loads too much data | Large collections or nested lists with high page sizes | Cap page size and use complexity with multipliers |
| High query depth but server is not overloaded | Many fields only read already-loaded properties | Combine depth with complexity and actual metrics |
| A list query generates dozens of SQL queries | N+1 in nested resolver | Use @BatchMapping or DataLoader |
| Batching reduces SQL but response is still slow | Large payload or too many objects to serialize | Reduce selection set, page size, and returned data |
| Complexity limit fails to block large page sizes | Using default calculator without checking arguments | Write FieldComplexityCalculator based on first/last/limit |
| Valid query runs for too long | Missing request/downstream timeout | Configure TimeoutWebGraphQlInterceptor and separate timeouts |
| High CPU on repeated documents | Repeated parsing and validation | Consider PreparsedDocumentProvider or persisted queries |
| Document cache continuously grows heap | Caching every query text without bounds | Set maximum size, eviction, and monitor hit/miss |
| WebFlux stalls even though resolver returns Mono | Blocking call runs before Mono is created or runs on event loop | Use reactive drivers or an executor for blocking work |
| Observation does not show simple fields | PropertyDataFetcher is treated as trivial | Monitor request observations and measure key resolvers |
| Increasing concurrency makes database slower | Connection pool or downstream is already saturated | Limit concurrency and reduce I/O count via batching |

## Hands-on practice

Build a cost policy for a library API:

1. Declare Query.books(first: Int = 20) and Book.reviews(first: Int = 10).
2. Create a query fetching 50 Books, each with an Author and 10 Reviews.
3. Calculate the maximum number of objects that can be requested and explain why depth alone does not reflect cost.
4. Write the nested field resolver using the N+1 pattern and measure repository call counts.
5. Replace the resolver with @BatchMapping or DataLoader; compare database query counts.
6. Cap maximum page size in the service/resolver.
7. Register MaxQueryDepthInstrumentation and MaxQueryComplexityInstrumentation.
8. Write a FieldComplexityCalculator using first or last to multiply child cost.
9. Test queries below and above the complexity threshold.
10. Configure PreparsedDocumentProvider if the same document is sent repeatedly.
11. Enable Micrometer GraphQL observations and inspect request, data fetcher, and DataLoader metrics.
12. Configure TimeoutWebGraphQlInterceptor and verify reactive publishers receive cancellation.
13. Benchmark before/after with the same dataset, concurrency, and selection set.

After completing this, explain why DataLoader does not reduce response size, why depth limits do not replace complexity limits, and why caching parsed documents is not response caching.

## Key takeaways

GraphQL request cost comes from parsing/validation, data fetching, nested field completion, collection size, serialization, and network transfer. Depth only measures levels; breadth and page size determine how many objects can be loaded. N+1 increases backend round trips; DataLoader and @BatchMapping batch loads but do not reduce the number of objects the client requests. Cap page size, estimate queries using MaxQueryComplexityInstrumentation with FieldComplexityCalculator, and combine depth limits with timeouts. PreparsedDocumentProvider reduces parsing/validation cost but does not cache data. Use Micrometer observations, query plans, and p95/p99 benchmarks to identify bottlenecks before optimizing.

## References

- [Spring for GraphQL – Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL – Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL – Annotated Controllers and @BatchMapping](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [GraphQL Java – Instrumentation](https://graphql-java.com/documentation/instrumentation/)
- [GraphQL Java – Limits](https://graphql-java.com/documentation/limits/)
- [GraphQL Java – Batching](https://graphql-java.com/documentation/batching/)
