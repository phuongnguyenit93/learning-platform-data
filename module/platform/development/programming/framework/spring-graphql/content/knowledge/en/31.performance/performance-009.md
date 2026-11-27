# Query size limits

GraphQL allows clients to select many fields and nest many levels within a single operation. This flexibility can lead to huge or resource-intensive requests: long documents, overly deep selection sets, many branches, nested list queries with large page sizes, or variables carrying massive payloads.

In Spring for GraphQL, GraphQL Java performs parsing, validation, and operation execution. Therefore, query size limits should be applied across multiple layers: HTTP request body limits, parser limits, operation depth and complexity limits, along with pagination and rate limits. No single limit controls every kind of load.

This lesson explains how to set these limits, how to configure `ParserOptions` and `Instrumentation` with Spring Boot, how to test over-limit queries, and common pitfalls during implementation.

## 1. Why are query size limits needed?

A query that is small in character count can still request huge amounts of data:

~~~graphql
query {
    customers(first: 100) {
        orders(first: 100) {
            items(first: 100) {
                product {
                    reviews(first: 100) {
                        author {
                            name
                        }
                    }
                }
            }
        }
    }
}
~~~

If each level returns up to 100 items, the number of potential data branches grows rapidly. Just four list levels can create a massive amount of work, even though the document itself is short.

Another query might contain thousands of aliases or fields:

~~~graphql
query {
    a1: customer(id: "1") { id }
    a2: customer(id: "2") { id }
    a3: customer(id: "3") { id }
    a4: customer(id: "4") { id }
}
~~~

These cases can increase request body read and document parse time, memory used to build the AST, validation and query analysis time, DataFetcher invocation counts, response size, and serialization cost.

Query limits are part of protecting server resources and keeping latency predictable when many clients send requests concurrently.

## 2. Four limit layers to distinguish

| Layer | What does it control? | Common mechanism |
| --- | --- | --- |
| HTTP request body | Total payload size over the network, including query, variables, and metadata | Reverse proxy, gateway, HTTP server, or request decoder |
| Parser | Document length, token count, whitespace tokens, and grammar depth | GraphQL Java `ParserOptions` |
| Query shape | Selection set depth, field count, and operation structure | `MaxQueryDepthInstrumentation`, `MaxQueryComplexityInstrumentation` |
| Runtime/data access | Record count, processing time, request rate, and dependency usage | Pagination, timeout, rate limit, DataLoader, and business caps |

These layers complement one another:

- `ParserOptions` bounds the GraphQL document being parsed; it does not bound the total JSON body.
- HTTP body limits protect the incoming payload; they do not know whether the query has a deep or expensive selection set.
- Depth limits prevent overly nested queries; they do not prevent queries with thousands of sibling fields at the same level.
- Complexity limits estimate operation cost; they do not replace actual database record limits.

Combine layers according to your application's risks and capacity.

## 3. Default limits of GraphQL Java ParserOptions

`ParserOptions` configures the GraphQL Java parser. Common defaults in GraphQL Java include:

| Limit | Default value | Purpose |
| --- | ---: | --- |
| `maxCharacters` | 1,048,576 characters | Prevents documents with overly long character strings |
| `maxTokens` | 15,000 tokens | Caps syntax token count |
| `maxWhitespaceTokens` | 200,000 tokens | Caps documents containing excessive whitespace |
| `maxRuleDepth` | 500 levels | Prevents overly deep grammar nesting during parsing |

These are parser limits, not HTTP request byte limits. A JSON body can be huge due to variables even when the GraphQL document is short; conversely, a long document can exceed parser limits even when the body passes the gateway's byte limit.

Default values belong to the GraphQL Java version your application uses. Check the actual dependency version before relying on fixed numbers, especially when Spring Boot manages the GraphQL Java version.

`maxRuleDepth` is grammar depth when the parser reads a document. It does not replace operation selection depth limits; that is enforced by instrumentation during query analysis.

## 4. Customizing parser limits for operations

GraphQL Java lets you build `ParserOptions` with custom limits. For request operations, use `setDefaultOperationParserOptions(...)` to set default parser options before the server receives requests.

Example configuring stricter limits than defaults:

~~~java
import graphql.parser.ParserOptions;

public final class GraphQlParserLimits {

    private GraphQlParserLimits() {
    }

    public static void configure() {
        ParserOptions operationOptions = ParserOptions.newParserOptions()
                .maxCharacters(256 * 1024)
                .maxTokens(8_000)
                .maxWhitespaceTokens(50_000)
                .maxRuleDepth(200)
                .build();

        ParserOptions.setDefaultOperationParserOptions(operationOptions);
    }
}
~~~

Call this configuration once at application startup before processing GraphQL operations:

~~~java
@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        GraphQlParserLimits.configure();
        SpringApplication.run(Application.class, args);
    }
}
~~~

`ParserOptions.setDefaultOperationParserOptions(...)` modifies the default configuration at JVM scope. If multiple GraphQL application contexts run in the same JVM, all of them share this configuration. Choose values suitable for all applications in the process and never mutate the configuration between requests.

Do not raise parser limits arbitrarily. If a legitimate client truly needs large documents, measure size, token count, and parse duration before adjusting.

## 5. HTTP request body limits separate from the parser

An HTTP GraphQL request typically carries a JSON payload like:

~~~json
{
    "query": "query Search($filter: SearchFilter!) { search(filter: $filter) { id } }",
    "operationName": "Search",
    "variables": {
        "filter": {
            "keywords": ["spring", "graphql"],
            "metadata": {
                "source": "web"
            }
        }
    }
}
~~~

The parser only processes the `query` value. The HTTP body also contains `operationName`, `variables`, and possibly `extensions`. Therefore, if you only configure `ParserOptions`, clients can still send huge JSON variables payloads.

Configure body limits at the reverse proxy, API gateway, or HTTP server suited to your deployment infrastructure. The gateway can reject payloads exceeding the byte limit before forwarding to the application.

When choosing a body limit, account for the query document, variables, metadata, actual JSON encoding (typically UTF-8), and other endpoints sharing the same HTTP server or gateway.

Do not confuse body limits with `maxCharacters`: body limits usually count bytes, whereas parser limits count characters in the GraphQL document. The two numbers are not interchangeable.

## 6. Limiting depth with MaxQueryDepthInstrumentation

Query depth is the number of nested levels in a selection set. Example:

~~~graphql
query {
    book {
        author {
            organization {
                address {
                    city
                }
            }
        }
    }
}
~~~

High depth increases the number of field resolution layers and can trigger many nested data accesses.

GraphQL Java provides `MaxQueryDepthInstrumentation`. If an operation's depth exceeds the threshold, the instrumentation refuses to execute the operation.

With Spring Boot, you can register an instrumentation bean:

~~~java
import graphql.execution.instrumentation.Instrumentation;
import graphql.analysis.MaxQueryDepthInstrumentation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GraphQlQueryLimitConfiguration {

    @Bean
    Instrumentation maxQueryDepthInstrumentation() {
        return new MaxQueryDepthInstrumentation(12);
    }
}
~~~

Spring Boot automatically detects `Instrumentation` beans when building `GraphQlSource`. The value `12` is only an example; choose a threshold based on your schema, valid client queries, and observed telemetry.

Depth limits only constrain nesting depth. An operation can have low depth yet hundreds or thousands of fields at the same level, so complexity limits are still needed.

## 7. Limiting complexity with MaxQueryComplexityInstrumentation

Query complexity is an estimated cost score for an operation based on selected fields and their nested sub-structures.

GraphQL Java provides `MaxQueryComplexityInstrumentation`. By default, its calculator sums a field's cost with its child complexity using `1 + childComplexity`.

Example registering a complexity limit:

~~~java
import graphql.analysis.MaxQueryComplexityInstrumentation;
import graphql.execution.instrumentation.Instrumentation;

@Bean
Instrumentation maxQueryComplexityInstrumentation() {
    return new MaxQueryComplexityInstrumentation(500);
}
~~~

If complexity exceeds the threshold, the operation is rejected before DataFetchers run.

Complexity limits can block wide queries with many fields even when the query is shallow. However, the default calculation does not automatically understand the cost difference between a list with `first: 1000` versus `first: 10`. For paginated APIs, define a custom `FieldComplexityCalculator` to factor page size into the calculation.

## 8. Computing complexity from pagination arguments

A query can nest multiple collections:

~~~graphql
query {
    books(first: 50) {
        reviews(first: 20) {
            author {
                name
            }
        }
    }
}
~~~

If the calculator only adds one point per field, two queries with the same structure but vastly different page sizes receive the same complexity score. That does not reflect actual cost.

`FieldComplexityCalculator` receives `FieldComplexityEnvironment` and `childComplexity`. From the environment, you can read the field definition and resolved arguments, including values passed via variables.

Illustrative calculator computing cost for the two collections `books` and `reviews`:

~~~java
import graphql.analysis.FieldComplexityCalculator;
import org.springframework.context.annotation.Bean;

@Bean
FieldComplexityCalculator paginationAwareCalculator() {
    return
        (environment, childComplexity) -> {
            if (environment.getFieldDefinition() == null) {
                return 1 + childComplexity;
            }

            String fieldName =
                    environment.getFieldDefinition().getName();

            if ("books".equals(fieldName) || "reviews".equals(fieldName)) {
                Object first = environment.getArguments().get("first");

                int pageSize = first instanceof Number number
                        ? Math.min(Math.max(number.intValue(), 1), 100)
                        : 20;

                return 1 + pageSize * childComplexity;
            }

            return 1 + childComplexity;
        };
}
~~~

In this example, page size is capped at 100 and defaults to 20 when the client omits `first`. These numbers must match the resolver's actual pagination limits.

This is an illustrative scoring model. In real applications, account for multiple collection fields, arguments such as `last` and `limit`, nested connections, fields calling expensive services, and schema default values.

## 9. Combining depth and complexity instrumentations

An application can use both instrumentations. Spring Boot collects `Instrumentation` beans, and GraphQL Java provides `ChainedInstrumentation` to run multiple instrumentations within the same execution.

Example:

~~~java
import java.util.List;

import graphql.analysis.FieldComplexityCalculator;
import graphql.analysis.MaxQueryComplexityInstrumentation;
import graphql.analysis.MaxQueryDepthInstrumentation;
import graphql.execution.instrumentation.ChainedInstrumentation;
import graphql.execution.instrumentation.Instrumentation;
import org.springframework.context.annotation.Bean;

@Bean
Instrumentation queryLimitsInstrumentation(
        FieldComplexityCalculator paginationAwareCalculator) {
    return new ChainedInstrumentation(List.of(
            new MaxQueryDepthInstrumentation(12),
            new MaxQueryComplexityInstrumentation(
                    10_000,
                    paginationAwareCalculator
            )
    ));
}
~~~

Combining these limits makes sense:

- Parser limits document size and parsing cost.
- Depth instrumentation limits nesting levels.
- Complexity instrumentation limits total estimated cost.
- Pagination limits how many elements resolvers can return.

If the application already uses instrumentations for metrics, tracing, or DataLoader, check how Spring Boot composes `Instrumentation` beans so they all run together. Avoid replacing existing instrumentations accidentally when adding a query limit.

The chained example in this section is an alternative configuration if you want to group depth and complexity into a single bean. When using the chain, remove the separate depth/complexity beans from earlier examples to avoid registering the same limit twice.

## 10. Pagination is a data limit, not just an API convenience

Even when a query passes parser, depth, and complexity checks, resolvers can still load too much data if collections are unbounded.

Example paginated schema:

~~~graphql
type Query {
    books(first: Int = 20, after: String): BookConnection!
}
~~~

The resolver must enforce a server-side maximum:

~~~java
@QueryMapping
public BookConnection books(
        @Argument Integer first,
        @Argument String after) {

    int pageSize = first == null ? 20 : Math.min(Math.max(first, 1), 100);

    return bookService.findBooks(pageSize, after);
}
~~~

Do not rely solely on clients passing small page sizes. A client can send `first: 100000`; the server must clamp or reject it according to the API contract.

For queries with nested collections, each collection needs an appropriate cap. Total potential items can grow as the product of page sizes across multiple levels.

## 11. Aliases, fragments, and repeated fields can widen queries

Queries can use aliases to request the same field multiple times with different arguments:

~~~graphql
query {
    recent: books(first: 20, sort: NEWEST) {
        id
    }
    popular: books(first: 20, sort: POPULAR) {
        id
    }
}
~~~

A single document can contain many such aliases. Each branch can trigger separate resolver work.

Fragments allow selection set reuse:

~~~graphql
fragment BookDetails on Book {
    id
    title
    author {
        name
    }
}

query {
    books(first: 20) {
        ...BookDetails
    }
}
~~~

When evaluating a query, do not just count lines or directly visible fields. Fragment spreads and inline fragments contribute to the operation after expansion.

GraphQL Java's query complexity instrumentation analyzes the operation and selection set, making it far more reliable than manual string counting. If writing a custom analyzer, handle fragments, aliases, directives, and operation variants accurately per GraphQL semantics.

## 12. Controlling introspection and special fields

Introspection lets clients explore the schema via `__schema` and `__type`. Some public APIs require introspection for GraphQL IDEs, code generation, or tooling; some production environments prefer restricting it.

However, disabling introspection does not replace query size limits. Clients can still send massive business queries.

If introspection is enabled, keep in mind that introspection queries can also be large. GraphQL Java includes dedicated protections for good-faith introspection in certain versions, so verify behavior and configuration for the exact version in use.

Special fields such as `__typename` must also be counted properly when evaluating queries. Do not blindly exclude all fields starting with `__` from counters without understanding their semantics.

## 13. Persisted queries and operation allowlists

Persisted queries allow clients to send an identifier or hash of a registered document instead of sending the full query text every time.

Benefits:

- Reduces document size transmitted over the network.
- Reduces parsing and validation cost when parsed documents can be reused.
- Simplifies managing the catalog of operations released by clients.
- Can support a policy permitting only registered operations.

Spring for GraphQL supports configuring `PreparsedDocumentProvider` via `GraphQlSource.Builder#configureGraphQl(...)`. GraphQL Java also provides persisted query support.

Distinguish two mechanisms:

- **Document cache:** caches parse/validation results to avoid redundant work; clients can still submit new query text.
- **Persisted query allowlist:** accepts only pre-registered hashes/documents; unregistered queries are rejected.

Persisted queries do not automatically become an allowlist if the server still allows clients to submit arbitrary documents. Nor do they replace complexity limits, pagination, or runtime timeouts.

## 14. Caching parsing and validation does not replace execution limits

GraphQL Java must parse and validate an operation before execution. `PreparsedDocumentProvider` can cache parsed/validated documents for reuse.

This reduces repeated overhead when the same operation is invoked frequently, but does not reduce data fetching cost for each request.

A cached operation can still query thousands of records if the resolver permits it. Therefore, combine:

- Preparsed document caching for repeated operations.
- Parser limits for incoming documents.
- Depth/complexity instrumentation for operation structure.
- Pagination and data bounds for resolvers.
- Timeouts and rate limits for runtime execution.

Caching is a performance optimization for valid requests, not a complete protective barrier.

## 15. Per-user rate limits and timeouts

Query limits apply per operation, yet a single client can send hundreds of valid operations back-to-back. Thus, the system needs rate limiting at the gateway or application layer.

Policies can be keyed by authenticated user ID or API key, tenant, IP address when no trusted identity exists, operation type, or resource/complexity score consumption.

Server timeouts also release requests that run too long. Spring for GraphQL provides `TimeoutWebGraphQlInterceptor` for web transports. However, timeouts do not replace parser, complexity, or pagination limits: the server can still burn substantial CPU before the timeout fires.

Rate limits, timeouts, and query complexity must work together to govern both single-request cost and request frequency.

## 16. Testing queries exceeding parser limits

After configuring parser options, verify that overly long operations are rejected before resolvers run.

Example building a document exceeding the character limit in a test:

~~~java
@Test
void rejectsDocumentAboveCharacterLimit() {
    String longFieldName = "x".repeat(300_000);
    String document = "query { " + longFieldName + " }";

    graphQlTester.document(document)
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).isNotEmpty());
}
~~~

The example assumes the parser is configured with a limit below 300,000 characters. The test checks that a request-level error occurs; it does not depend on exact parser message text.

You can add separate tests for token limits, whitespace limits, and parser rule depth. These tests confirm each limit is properly enforced.

## 17. Testing depth and complexity instrumentation

For depth limits, create a query with a selection set deeper than the threshold:

~~~java
@Test
void rejectsQueryAboveMaximumDepth() {
    graphQlTester.document("""
            query {
                category {
                    children {
                        children {
                            children {
                                id
                            }
                        }
                    }
                }
            }
            """)
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).isNotEmpty());
}
~~~

For complexity, create a query whose collection arguments exceed the budget:

~~~java
@Test
void rejectsQueryAboveMaximumComplexity() {
    graphQlTester.document("""
            query {
                books(first: 100) {
                    reviews(first: 100) {
                        id
                    }
                }
            }
            """)
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).isNotEmpty());
}
~~~

These tests require a schema with matching fields and the real instrumentation configured in the test context. If a query fails due to schema validation or nonexistent fields, the test will still see `errors`; therefore, make sure the query is schema-valid before using it to test depth or complexity.

Also add tests for queries below the threshold to ensure instrumentation does not block legitimate operations by mistake.

## 18. Common pitfalls with query limits

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Long queries still reach the parser | Only HTTP body limit is set, without `ParserOptions` | Configure parser operation options |
| Huge variables are still accepted | `maxCharacters` only bounds the GraphQL document | Set HTTP body limits and separate input bounds |
| Very deep queries still execute | `MaxQueryDepthInstrumentation` is not registered | Add instrumentation bean and test it |
| Queries with many sibling fields still run | Only depth limit is configured | Add a complexity limit |
| Nested list queries consume heavy resources | Default complexity does not multiply by page size | Use a calculator incorporating pagination arguments |
| Valid queries get rejected | Threshold too low or complexity calculator overestimates | Measure real queries and calibrate thresholds |
| Raised parser limit but requests still fail | Gateway or HTTP server caps body before parser runs | Check body limits at ingress and transport |
| Persisted queries still accept arbitrary documents | Caching enabled without allowlist enforcement | Reject unregistered documents/hashes |
| Requests remain slow despite caching | Parsing is cached but DataFetchers still burn resources | Inspect resolvers, pagination, DataLoader, and database |
| Small query returns massive response | Unbounded page sizes or collection fields | Clamp pagination on the server |
| Limit test passes due to invalid schema query | Query was already invalid before limit check | Verify baseline query is schema-valid before testing limits |

## 19. Workflow for setting up query limits

When introducing limits to a Spring for GraphQL server, follow this sequence:

1. Measure the largest valid documents clients actually need.
2. Set HTTP request body limits at the gateway or server, including variables.
3. Configure operation `ParserOptions`: characters, tokens, whitespace tokens, and rule depth.
4. Register `MaxQueryDepthInstrumentation`.
5. Register `MaxQueryComplexityInstrumentation`.
6. For collection fields, compute complexity based on page sizes and actual query costs.
7. Enforce pagination bounds in resolvers/services, not just on clients.
8. Consider a persisted query allowlist if the API has a stable operation set.
9. Add per-user/tenant rate limits and timeouts.
10. Test queries below limits, queries exceeding each limit, and oversized variables/bodies.
11. Monitor rejected request rates, query complexity, parse/execute durations, and response sizes.
12. Tune thresholds using production data and legitimate client requirements.

Do not apply one universal number to every system. Query limits must reflect your schema, data volume, database capacity, target timeouts, and client types.

## 20. Points to remember

- Query size has multiple dimensions: HTTP body, document characters, token count, parser depth, selection depth, and execution complexity.
- `ParserOptions` bounds documents before GraphQL Java executes the operation.
- `setDefaultOperationParserOptions(...)` configures operation parser options at JVM scope.
- `MaxQueryDepthInstrumentation` limits selection set nesting levels.
- `MaxQueryComplexityInstrumentation` limits an operation's estimated cost score.
- Complexity must factor in collection page sizes to reflect actual data load.
- Pagination must be clamped on the server.
- Persisted query caches reduce parse cost; allowlists restrict permitted operations.
- HTTP body limits must cover variables, not only query text.
- Rate limits and timeouts protect the system against bursts of consecutive valid requests.

Query size limits allow Spring for GraphQL to handle requests more predictably. By combining parser, depth, complexity, request body, and pagination limits, the server can reject oversized operations early while keeping valid queries within healthy resource budgets.

## References

- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — GraphQlSource](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.graphqlsource)
- [GraphQL Java — ParserOptions API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/parser/ParserOptions.html)
- [GraphQL Java — ParserOptions.Builder API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/parser/ParserOptions.Builder.html)
- [GraphQL Java — MaxQueryDepthInstrumentation API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/MaxQueryDepthInstrumentation.html)
- [GraphQL Java — MaxQueryComplexityInstrumentation API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/MaxQueryComplexityInstrumentation.html)
- [GraphQL Java — FieldComplexityCalculator API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/FieldComplexityCalculator.html)
