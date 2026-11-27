# PreparsedDocumentProvider

## Objectives

After completing this lesson, you will be able to:

- Explain why GraphQL Java must parse and validate documents before execution.
- Describe the roles of `PreparsedDocumentProvider` and `PreparsedDocumentEntry`.
- Distinguish a document cache from a response cache and a DataLoader cache.
- Configure `PreparsedDocumentProvider` in Spring for GraphQL via `GraphQlSourceBuilderCustomizer`.
- Build a bounded cache using Caffeine and the current `getDocumentAsync` API.
- Understand why GraphQL variables improve the cache hit ratio.
- Distinguish query caching, Automatic Persisted Queries (APQ), and an operation allowlist.
- Manage the cache when the schema, validation rules, or GraphQL Java version changes.
- Test cache hits, cache misses, invalid documents, and per-request execution behavior.
- Avoid unbounded caches, bypassed validation instrumentation, or leaking access rules across contexts.

## Why Does GraphQL Need to Parse and Validate?

When the server receives a GraphQL request, the query text is a plain character string. GraphQL Java must turn that string into a syntax structure and verify that the structure conforms to the schema before invoking any data fetcher.

Example:

~~~graphql
query BookDetails($id: ID!) {
  book(id: $id) {
    id
    title
    author {
      name
    }
  }
}
~~~

Before executing, the engine must:

1. Parse the document into an Abstract Syntax Tree (AST).
2. Verify that the `book` field exists on `Query`.
3. Verify that the `id` argument and `ID!` type are valid.
4. Verify nested fields such as `title`, `author`, and `name`.
5. Verify that variable `$id` is declared and used with the proper type.
6. Only once the document is valid does the engine proceed to operation selection, variable coercion, and field execution.

Parsing and validation become repetitive work when clients send the same document repeatedly. For APIs with stable operations and high request rates, this CPU overhead can be significant even when resolvers and databases are very fast.

## What Is PreparsedDocumentProvider?

GraphQL Java provides the `PreparsedDocumentProvider` interface so applications can intercept the retrieval of parsed and validated documents. A provider can:

- Return a `PreparsedDocumentEntry` already stored in cache.
- Invoke the parse/validate callback on a cache miss.
- Reject operations not present in an allowlist.
- Integrate a persisted query mechanism by ID or hash.

If an application does not configure a custom cache or persisted query provider, GraphQL Java uses a non-caching provider and must re-parse and re-validate documents on every subsequent request.

GraphQL Java invokes the provider prior to operation execution. The provider receives two parameters:

- `ExecutionInput`: the current request, including query text, operation name, variables, and extensions.
- `parseAndValidateFunction`: callback for GraphQL Java to parse and validate the request if the provider has no matching entry.

In the current GraphQL Java API, the method signature is:

~~~java
CompletableFuture<PreparsedDocumentEntry> getDocumentAsync(
        ExecutionInput executionInput,
        Function<ExecutionInput, PreparsedDocumentEntry> parseAndValidateFunction);
~~~

`PreparsedDocumentEntry` represents the outcome of the parse and validation phase. An entry can contain:

- A parsed document with zero validation errors.
- A parsed document with validation errors.
- A list of parse or validation errors when no document could be produced.

When a valid document is found in cache, GraphQL Java can reuse the AST and skip re-parsing/re-validating. When no entry exists, the provider must invoke the callback so the engine runs the proper parse and validation pipeline.

Important note: this callback does more than parse and validate. It also executes parse/validation-related instrumentation. If on a cache miss a provider constructs a `Document` manually or returns a synthetic entry, the corresponding checks and instrumentations may be skipped. [GraphQL Java – PreparsedDocumentProvider API](https://www.javadoc.io/static/com.graphql-java/graphql-java/22.4/graphql/execution/preparsed/PreparsedDocumentProvider.html)

## A Document Cache Is Not a Response Cache

`PreparsedDocumentProvider` only reuses parse/validation results. Every request still executes data fetchers and builds a fresh response.

| Mechanism | What Is Stored | Typical Scope |
| --- | --- | --- |
| `PreparsedDocumentProvider` | AST and parse/validation results | Reused across requests sharing the same document |
| DataLoader cache | Entity load results by key | Typically scoped to a single GraphQL request |
| Application/data cache | Domain data such as Product or Author | Governed by application caching policy |
| HTTP/response cache | Complete serialized responses | Depends on URL, variables, identity, headers, and cache policy |

For example, suppose the same `book(id: $id)` query is sent 1,000 times with different `$id` values:

- `PreparsedDocumentProvider` can reuse the same AST.
- The `book` data fetcher still runs for every request.
- The repository is still called according to application logic, unless a separate data cache exists.
- Each user's response is still produced individually.

Never assume from a document cache hit that data has already been loaded or authorization has already been checked. Resolvers, services, and security policies must still execute per request.

## Query Text, Operation Name, and Variables

A document cache typically keys on the query text. That means two documents differing only in literal values can produce two distinct cache entries:

~~~graphql
query {
  book(id: "book-101") {
    title
  }
}
~~~

~~~graphql
query {
  book(id: "book-202") {
    title
  }
}
~~~

The two queries above share nearly identical structure yet have different query text. Caching by raw query text treats them as two separate keys.

Move varying values into variables:

~~~graphql
query BookTitle($id: ID!) {
  book(id: $id) {
    title
  }
}
~~~

First request:

~~~json
{
  "query": "query BookTitle($id: ID!) { book(id: $id) { title } }",
  "variables": {
    "id": "book-101"
  }
}
~~~

Second request using the same query text with different variables:

~~~json
{
  "query": "query BookTitle($id: ID!) { book(id: $id) { title } }",
  "variables": {
    "id": "book-202"
  }
}
~~~

The document can be reused while the variable values are still coerced and applied per execution.

Operation names and variables do not need to be part of a standard document cache key because they do not alter the parsed document structure. When a document defines multiple operations, GraphQL Java still selects the operation by `operationName` during execution.

Whitespace, comments, aliases, fragments, and literal arguments are all part of the query text. If a cache keys on raw query text, semantically identical queries written differently can create multiple entries. Avoid canonicalizing queries via naive string manipulation; any normalization must preserve GraphQL document semantics.

## Configuration in Spring for GraphQL

Spring for GraphQL lets you register `PreparsedDocumentProvider` via `GraphQlSource.Builder#configureGraphQl`. In Spring Boot, the standard approach is declaring a `GraphQlSourceBuilderCustomizer` bean.

The example below uses Spring Boot 4.x:

~~~java
import graphql.execution.preparsed.PreparsedDocumentProvider;
import org.springframework.boot.graphql.autoconfigure.GraphQlSourceBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GraphQlDocumentCacheConfiguration {

    @Bean
    GraphQlSourceBuilderCustomizer preparsedDocumentCustomizer(
            PreparsedDocumentProvider provider) {

        return builder -> builder.configureGraphQl(graphQLBuilder ->
                graphQLBuilder.preparsedDocumentProvider(provider));
    }
}
~~~

Spring Boot 3.x uses the package `org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer`. The customization API works the same way: receive the builder and invoke `configureGraphQl`.

The Boot starter creates the `GraphQlSource` builder, loads schema resources, and detects customizer beans. You do not need to construct a separate `GraphQL` instance just to register a provider. If the application builds `GraphQlSource` manually, call `configureGraphQl` on that builder before building.

## Building a Document Cache with Caffeine

GraphQL Java does not mandate a specific caching library. You can use Caffeine, an internal cache, or an implementation suited to your runtime environment.

Add the Caffeine dependency:

~~~groovy
dependencies {
    implementation 'com.github.ben-manes.caffeine:caffeine'
}
~~~

Example provider using Caffeine:

~~~java
import java.time.Duration;
import java.util.concurrent.CompletableFuture;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import graphql.ExecutionInput;
import graphql.execution.preparsed.PreparsedDocumentEntry;
import graphql.execution.preparsed.PreparsedDocumentProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PreparsedDocumentCacheConfiguration {

    @Bean
    PreparsedDocumentProvider preparsedDocumentProvider() {
        Cache<String, PreparsedDocumentEntry> cache = Caffeine.newBuilder()
                .maximumSize(10_000)
                .expireAfterAccess(Duration.ofMinutes(30))
                .recordStats()
                .build();

        return (executionInput, parseAndValidateFunction) -> {
            String query = executionInput.getQuery();

            if (query == null || query.isBlank()) {
                PreparsedDocumentEntry entry =
                        parseAndValidateFunction.apply(executionInput);
                return CompletableFuture.completedFuture(entry);
            }

            PreparsedDocumentEntry entry = cache.get(
                    query,
                    key -> parseAndValidateFunction.apply(executionInput));

            // Do not retain erroneous documents sent by clients with invalid queries.
            if (entry.hasErrors()) {
                cache.invalidate(query);
            }

            return CompletableFuture.completedFuture(entry);
        };
    }
}
~~~

In this example:

- The cache key is the query text.
- `maximumSize(10_000)` bounds the entry count to avoid unbounded memory growth.
- `expireAfterAccess` (30 minutes) evicts entries not accessed for a period.
- `recordStats()` enables observing hits, misses, evictions, and cache statistics.
- The cache retains only entries with zero parse/validation errors.
- On a cache miss, it invokes `parseAndValidateFunction` so GraphQL Java runs the standard pipeline.

The cache is created once and shared across requests. Caffeine supports concurrent access; never create a new cache inside each `getDocumentAsync` call.

The numbers 10,000 and 30 minutes are merely examples. Tune them based on actual operation counts, AST sizes, heap budget, and the ratio of distinct query texts. A huge cache does not automatically improve speed if most requests appear only once.

### Why Must the Cache Be Bounded?

If a server caches every query text without bounds, clients can continuously send slightly different documents. Each document occupies a cache entry even if it is never reused. This is a cardinality explosion risk that can unnecessarily inflate heap memory.

Safeguards to consider:

- Configure a maximum size and expiration policy.
- Monitor hit ratio, miss rate, and evictions.
- Limit query text size at the transport/request layer.
- Use persisted queries or an allowlist if clients are only permitted to run pre-approved operations.
- Avoid caching parse/validation errors from arbitrary client queries for long periods.
- Track the number of unique documents over time.

Do not blindly increase cache size just because miss counts look high. First check whether query texts are stable or varying unnecessarily due to literal values, whitespace, or dynamically generated client operations.

## How the Provider Behaves Across Cache Misses and Cache Hits

~~~mermaid
flowchart TD
    A[GraphQL request] --> B[PreparsedDocumentProvider]
    B --> C{Query text in cache?}
    C -->|Yes| D[Reuse PreparsedDocumentEntry]
    C -->|No| E[parseAndValidateFunction]
    E --> F[Parse AST and validate schema]
    F --> G[Create PreparsedDocumentEntry]
    G --> H{Has errors?}
    H -->|Yes| I[Return errors, do not retain]
    H -->|No| J[Store entry in bounded cache]
    J --> D
    D --> K[Select operation and coerce variables]
    I --> L[Return request errors]
    K --> M[Execute data fetchers]
    M --> N[Build response]
~~~

**Cache miss:** the provider invokes the callback. GraphQL Java parses the document, validates against the schema, and returns a `PreparsedDocumentEntry`. The provider stores valid entries and returns the future to the engine.

**Cache hit:** the provider returns the cached entry. The engine can skip parsing and validation, then continue processing `operationName`, `variables`, and data fetchers for the current request.

**Invalid document:** for example, a query referencing a non-existent field or containing syntax errors. The provider returns the errors so GraphQL Java produces a request error; the Caffeine example above invalidates erroneous entries so clients cannot fill the cache with varying invalid queries.

## Persisted Queries and APQ

A document cache uses query text as its key. Persisted queries allow clients to reference a document by ID or hash instead of sending the full query text on every request.

GraphQL Java includes implementations in package `graphql.execution.preparsed.persisted`:

- `PersistedQuerySupport`: foundation for persisted queries.
- `ApolloPersistedQuerySupport`: supports Apollo's Automatic Persisted Queries format.
- `PersistedQueryCache`: abstraction for caching registered queries.
- `InMemoryPersistedQueryCache`: in-memory cache for persisted queries.

Spring for GraphQL illustrates configuring APQ as follows:

~~~java
import graphql.execution.preparsed.PreparsedDocumentProvider;
import graphql.execution.preparsed.persisted.ApolloPersistedQuerySupport;
import graphql.execution.preparsed.persisted.InMemoryPersistedQueryCache;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.Collections;

@Configuration(proxyBeanMethods = false)
public class ApolloPersistedQueryConfiguration {

    @Bean
    PreparsedDocumentProvider preparsedDocumentProvider() {
        return new ApolloPersistedQuerySupport(
                new InMemoryPersistedQueryCache(Collections.emptyMap()));
    }
}
~~~

This is an alternative configuration to the Caffeine document cache above. Do not declare two beans of type `PreparsedDocumentProvider` without an explicit composition strategy.

With APQ, the client sends a query hash inside `extensions`. When the server already recognizes the hash, it retrieves the document from the persisted query cache. In the automatic persistence flow, the client can send the query text together with the hash on a cache miss so the server parses, validates, and stores the document; subsequent requests need only send the hash.

### APQ Does Not Equal an Allowlist

These two concepts are often confused:

| Mechanism | How It Works | Purpose |
| --- | --- | --- |
| Document cache | Client sends query text; server caches parse/validation results by query text | Reduce repeated parsing/validation |
| APQ | Client sends a hash; server looks it up or accepts query text to register on a miss | Shrink request payload size and reuse documents |
| Operation allowlist | Server accepts only pre-registered IDs/documents | Restrict the set of operations clients are permitted to execute |

Automatic APQ still accepts new query text when a client resends it on a cache miss. Therefore, APQ alone is not a policy enforcing that only pre-approved operations can run.

If the API requires a strict allowlist, pre-load only reviewed operations and reject unknown IDs. Disable arbitrary client query registration paths. Validate both hashes and document contents against application policy.

In multi-instance deployments, `InMemoryPersistedQueryCache` is local to each process. Use a shared cache or deploy the exact same persisted operation catalog to every instance to avoid inconsistent state across nodes. [GraphQL Java – Persisted Query Support](https://www.javadoc.io/static/com.graphql-java/graphql-java/22.4/graphql/execution/preparsed/persisted/ApolloPersistedQuerySupport.html)

## Cache Keys and Schema Boundaries

A cache entry is valid only within the schema and validation policy context under which it was created.

For a `GraphQlSource` using a static schema, a cache bound to that `GraphQL` instance's provider is usually sufficient. When the schema changes and `GraphQlSource` is rebuilt, create a fresh provider/cache or namespace entries by schema version.

Do not share a single cache entry solely by query text when validation outcomes depend on:

- Schemas that vary by tenant or API version.
- Field visibility that changes per principal.
- Validation rules that vary by client, tenant, or role.
- Custom instrumentations making validation decisions based on `GraphQLContext` or request state.

In those scenarios, include the dimensions affecting validation in the cache key, or avoid caching across differing contexts. Another option is caching only the parsed AST separately while still running request-specific validation if your architecture supports it.

Data authorization must still be enforced inside resolvers/services on every request. `PreparsedDocumentProvider` is not a cache for deciding whether a user is allowed to read a Product or invoke a field.

## Parse/Validation Instrumentation and Custom Validation

GraphQL Java supplies `parseAndValidateFunction` so the provider runs the proper parse and validation steps. On a cache miss, always call the callback instead of parsing the AST manually and constructing an entry by hand.

On a cache hit, the engine may skip re-running parse/validation. Consequently:

- Instrumentations measuring parse/validation timing alone will primarily reflect cache misses.
- Instrumentations measuring execution and data fetchers must still be configured to observe execution behavior.
- Dynamic custom validations must be reviewed before enabling a shared cache.
- When schemas or validation rules change, invalidate entries or introduce a new cache namespace.

If a custom validation rule checks permissions based on request context, do not store user A's validation result and serve it to user B merely because the query text matches. Either include the validation-relevant context in the cache key or let validation re-run per request.

## Testing PreparsedDocumentProvider

Test the provider at two levels:

**Unit tests for the cache provider**

- Sending the same query text twice invokes the parse/validation callback only once while the valid entry remains cached.
- Different query texts produce separate entries.
- Invalid queries are not retained long-term in the cache.
- Entries are evicted after exceeding maximum size or expiration.
- Empty/null queries take the uncached branch.

**Integration tests through GraphQL**

Add the test dependency if the module does not already include it:

~~~groovy
dependencies {
    testImplementation 'org.springframework.graphql:spring-graphql-test'
}
~~~

- Send the same document with two different sets of variables; responses must reflect each request's variables.
- Data fetchers still run on every request, proving a document cache is not a response cache.
- Querying a non-existent field still returns a validation error.
- When the schema changes, a new provider/cache validates against the new schema.
- When using persisted queries, test registered hashes, unknown hashes, and cache misses accompanied by query text.

Example verifying variable behavior:

~~~java
@Test
void reusesDocumentButExecutesWithCurrentVariables() {
    graphQlTester.document("""
            query BookTitle($id: ID!) {
                book(id: $id) {
                    title
                }
            }
            """)
            .variable("id", "book-101")
            .execute()
            .path("book.title")
            .entity(String.class)
            .isEqualTo("GraphQL Basics");

    graphQlTester.document("""
            query BookTitle($id: ID!) {
                book(id: $id) {
                    title
                }
            }
            """)
            .variable("id", "book-202")
            .execute()
            .path("book.title")
            .entity(String.class)
            .isEqualTo("Spring for GraphQL");
}
~~~

This test assumes `graphQlTester` is configured and test fixtures contain both books. To verify the callback runs only once, wrap `PreparsedDocumentProvider` or the callback with a counter in a unit test and assert the parse/validation invocation count. Do not rely on response latency alone as proof because JIT compilation, connection pools, and other caches also affect timings.

## Observing Cache Effectiveness

Do not enable a cache and assume performance improved. Measure before and after:

- Hit ratio: how many requests reuse an existing entry.
- Miss rate: how many documents require parsing/validation.
- Evictions: entries removed due to size limits or expiration.
- Cache size and heap usage.
- Parse/validation duration on misses.
- Total GraphQL request time and data fetcher duration.

A low hit ratio may indicate clients are sending constantly changing query text, inlining literal arguments inside documents, or generating operations dynamically. Moving varying values into variables and standardizing client operations typically improves results.

If most latency comes from the database or downstream services, a document cache may yield only modest gains. Treat it as an optimization for the parse/validation phase, not a cure for N+1 queries or slow resolvers.

## Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Low cache hit rate for the same business operation | Clients generate varying query text or inline literal values | Use variables and reuse operation documents |
| Heap grows over time | Cache has no maximum size or expiration | Use a bounded cache and monitor evictions |
| Syntax-invalid queries stay cached | Caching `PreparsedDocumentEntry` instances that have errors | Never store or give very short TTL to erroneous entries |
| Validation instrumentation stops running on cache hits | Document is reused so parse/validation is skipped | Understand instrumentation scope and measure execution separately |
| Cache serves documents validated against an old schema | Cache outlives `GraphQlSource`/schema | Create a new cache or namespace by schema version |
| Low-privilege user accesses fields validated for another user | Validation depends on principal while cache key is query text only | Do not share cache by query text alone or include context in the key |
| APQ treated as an allowlist | Server still allows registering new query text on cache miss | Use a pre-loaded operation list and reject unknown IDs |
| Two nodes have different persisted query states | Using per-process in-memory caches | Use a shared cache or deploy an identical allowlist |
| Cache hit still hits the database | Document cache does not store responses or domain data | Use a data cache/`DataLoader` where appropriate |
| Parse/validation instrumentation disappears on cache misses | Provider skips calling `parseAndValidateFunction` | Always invoke the callback supplied by GraphQL Java |
| Query text is missing in `ExecutionInput` | Request uses persisted queries or payload omits query | Use a persisted-query-aware provider rather than a plain text cache |

## Comprehensive Hands-On Exercise

Integrate document caching for a library API:

1. Create the GraphQL operation `BookTitle($id: ID!)` using a variable for the argument.
2. Add the Caffeine dependency managed by Spring Boot's dependency management.
3. Implement a `PreparsedDocumentProvider` backed by a cache with maximum size and expiration.
4. On a cache miss, invoke `parseAndValidateFunction` and return the `PreparsedDocumentEntry`.
5. Do not retain entries with parse/validation errors long-term in the cache.
6. Register the provider via `GraphQlSourceBuilderCustomizer` and `configureGraphQl`.
7. Send the same document with two different sets of variables and verify distinct responses.
8. Use a counter in a unit test to verify the parse/validation callback runs only on misses.
9. Send an invalid document and verify GraphQL still returns a request error.
10. Measure hit ratio, misses, evictions, and parse/validation time.
11. Try `ApolloPersistedQuerySupport` to accept operations by hash.
12. If an allowlist is needed, pre-register only approved operations and verify unknown IDs are rejected.
13. Introduce a new schema version and verify the old cache is not reused across incompatible contexts.

After finishing, explain why variables increase cache hits, why `PreparsedDocumentProvider` does not reduce resolver invocations, and why APQ is not an allowlist by default.

## Key Takeaways

`PreparsedDocumentProvider` lets GraphQL Java reuse parsed and validated documents. It reduces parse/validation CPU cost without caching responses or resolver data. With the current API, implement `getDocumentAsync` and always invoke `parseAndValidateFunction` on cache misses to preserve the validation pipeline and instrumentations. In Spring Boot, register the provider via `GraphQlSourceBuilderCustomizer` and `GraphQlSource.Builder#configureGraphQl`. Use variables instead of literal values so identical query text can be reused. Caches must bound size/expiration, handle erroneous entries properly, and align with schema/validation boundaries. APQ lets clients send operation hashes; an allowlist requires an explicit policy rejecting unregistered operations. Test cache hits/misses, variables, validation errors, schema changes, and per-request resolver execution.

## References

- [Spring for GraphQL – Request Execution, Operation Caching](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [GraphQL Java v25 – Execution and Query Caching](https://graphql-java.com/documentation/execution/)
- [GraphQL Java – PreparsedDocumentProvider API](https://www.javadoc.io/static/com.graphql-java/graphql-java/22.4/graphql/execution/preparsed/PreparsedDocumentProvider.html)
- [GraphQL Java – PreparsedDocumentEntry API](https://www.javadoc.io/static/com.graphql-java/graphql-java/0.0.0-2026-03-04T15-19-42-5b63591/graphql/execution/preparsed/PreparsedDocumentEntry.html)
- [GraphQL Java – ApolloPersistedQuerySupport API](https://www.javadoc.io/static/com.graphql-java/graphql-java/0.0.0-2026-03-04T15-19-42-5b63591/graphql/execution/preparsed/persisted/ApolloPersistedQuerySupport.html)
- [Spring Boot 4 – GraphQlSourceBuilderCustomizer API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/graphql/autoconfigure/GraphQlSourceBuilderCustomizer.html)
