# Limiting Query Depth and Complexity

GraphQL allows clients to pick fields, nest objects, and request multiple collections in a single operation. This flexibility also introduces risk: a query can be very deep, very wide, or request thousands of records across multiple levels. If the server only limits HTTP request size, a small document can still trigger massive work in resolvers, databases, and downstream services.

With Spring for GraphQL, GraphQL Java provides two important mechanisms to control operation structure and cost: `MaxQueryDepthInstrumentation` and `MaxQueryComplexityInstrumentation`. Depth limits the nesting depth of the selection tree; complexity estimates the total cost of fields, optionally incorporating multipliers for pagination and expensive fields.

This lesson shows how to understand both limits, configure them in Spring Boot, design a complexity formula tailored to your schema, test rejected queries, and combine them with other safeguards to prevent resource abuse.

## 1. Why Limit Queries?

A GraphQL endpoint typically receives many kinds of operations:

- Simple queries fetching a single object.
- Queries nesting multiple relationships such as Author → Books → Reviews → User.
- Queries fetching multiple collections in one operation.
- Queries using aliases to invoke the same field multiple times with different arguments.
- Queries using fragments to reuse selection sets.
- Queries with large pagination or nested collections.

For example, a client might send:

~~~graphql
query DeepBook {
    book(id: "book-42") {
        author {
            books(first: 100) {
                reviews(first: 100) {
                    author {
                        books(first: 100) {
                            title
                        }
                    }
                }
            }
        }
    }
}
~~~

The document is not particularly long, yet each level can fan out into many objects. If resolvers query the database or call services per object, the amount of work can grow rapidly.

A syntactically valid request can still consume excessive CPU, memory, database connections, or downstream quota. Therefore, the server must evaluate queries before running resolvers and reject operations exceeding the configured budget.

## 2. What Is Query Depth?

Query depth is the deepest level of nested fields in an operation's selection tree. Each time a query steps from an object field to a child field of that object, depth increases.

For example:

~~~graphql
query {
    book {
        id
        author {
            name
        }
    }
}
~~~

The deepest branch is:

~~~text
book
  └── author
        └── name
~~~

The `id` and `name` fields are leaf fields. Query depth focuses on the deepest path; it does not sum all sibling fields into a single number.

Another query might only be two levels deep yet select a huge number of fields:

~~~graphql
query {
    book {
        id
        title
        isbn
        summary
        description
        author { id name email }
        publisher { id name website }
        reviews { id rating body createdAt }
    }
}
~~~

This query is not very deep, yet it can still generate significant work. That is why depth must be combined with complexity.

## 3. What Is Query Complexity?

Query complexity is an estimated cost score for the entire selection set. Each field contributes a portion of the cost; parent fields can also accumulate the cost of their child fields.

GraphQL Java provides `MaxQueryComplexityInstrumentation`. Its simple constructor uses the default formula:

~~~java
new MaxQueryComplexityInstrumentation(500)
~~~

The default formula calculates field cost as `1 + childComplexity`, where `childComplexity` is the sum of its child fields' costs. As a result, queries with many fields or many nested levels receive higher scores.

Consider a selection tree:

~~~graphql
query {
    book {
        id
        title
        author {
            id
            name
        }
    }
}
~~~

If each field has a base cost of 1, the default score can be visualized as:

| Field | Child complexity | Field complexity |
| --- | ---: | ---: |
| `id` | 0 | 1 |
| `title` | 0 | 1 |
| `author` | 2 | 3 |
| `book` | 5 | 6 |

This model illustrates how `1 + childComplexity` accumulates. Actual scores are computed by GraphQL Java against the parsed operation and corresponding schema.

Complexity is not execution time in milliseconds. It is an estimated budget that must be designed and calibrated based on actual resolver costs.

## 4. Distinguishing Depth, Complexity, and Other Limits

| Limit | Measures | Catches Which Cases? | Does Not Replace |
| --- | --- | --- | --- |
| Query depth | Deepest field nesting path | Deeply nested object relationships | Complexity, pagination |
| Query complexity | Total field cost score | Wide queries, many fields, or expensive fields | Body limits, parser limits |
| Parser limits | Document size and syntactic complexity | Oversized documents or too many parser tokens | Resolver cost |
| HTTP body limit | Request body byte count | Oversized JSON payloads | Small queries returning huge data |
| Pagination limit | Maximum items per collection | Collections returning too many records | Queries with many collection branches |
| Rate/concurrency limit | Concurrent requests or executions | Clients flooding many operations continuously | A single overly expensive operation |

No single limit suffices to protect an entire GraphQL server. Depth and complexity handle operation structure; other layers handle request size, data volume, request rate, and runtime resources.

## 5. Why Limiting Depth Alone Is Not Enough

A query with shallow depth can still request many fields or repeat a field using aliases:

~~~graphql
query WideSearch {
    first: searchBooks(text: "java") {
        id
        title
        author { name }
    }

    second: searchBooks(text: "graphql") {
        id
        title
        author { name }
    }

    third: searchBooks(text: "database") {
        id
        title
        author { name }
    }
}
~~~

Each branch is shallow, yet the same search resolver is invoked multiple times in one operation.

Another query has few fields yet requests a huge list:

~~~graphql
query LargePage {
    books(first: 5000) {
        id
        title
    }
}
~~~

Depth does not reflect how many items the server must load and serialize. Default complexity also counts fields purely by structure; without accounting for pagination, the query above can score far below its real cost.

Therefore, use depth to block deep nesting and custom complexity to account for factors that drive actual work.

## 6. MaxQueryDepthInstrumentation in GraphQL Java

`MaxQueryDepthInstrumentation` belongs to the `graphql.analysis` package. This instrumentation traverses the selection tree and rejects execution when depth exceeds the threshold.

Example:

~~~java
import graphql.analysis.MaxQueryDepthInstrumentation;

MaxQueryDepthInstrumentation depthLimit =
        new MaxQueryDepthInstrumentation(8);
~~~

In the example, operations with depth greater than 8 are aborted. A threshold of 8 is purely illustrative; measure your real schema and operations to pick an appropriate limit.

When the limit is exceeded, GraphQL Java throws `AbortExecutionException`. The GraphQL result contains an error with classification `ExecutionAborted`; `DataFetcher`s of the rejected operation do not continue executing.

This limit is evaluated at the GraphQL execution step, after the document has been parsed. It is not a grammar parser limit and does not protect against the cost of reading a massive HTTP body prior to parsing.

## 7. MaxQueryComplexityInstrumentation in GraphQL Java

`MaxQueryComplexityInstrumentation` also belongs to the `graphql.analysis` package. It calculates an operation's complexity score and aborts if the total score exceeds the threshold.

~~~java
import graphql.analysis.MaxQueryComplexityInstrumentation;

MaxQueryComplexityInstrumentation complexityLimit =
        new MaxQueryComplexityInstrumentation(500);
~~~

The single-argument constructor uses the default `1 + childComplexity` calculator. This works well for catching queries with many fields, but does not fully reflect the cost of large collections or particularly expensive resolvers.

GraphQL Java also provides a constructor accepting a `FieldComplexityCalculator` so applications can define per-field costs themselves. Consider this approach whenever your schema includes pagination, search, reports, analytics, or fields making costly downstream calls.

## 8. Configuring Depth and Complexity in Spring Boot

The Spring Boot GraphQL starter automatically detects beans implementing `graphql.execution.instrumentation.Instrumentation` and registers them when building `GraphQlSource`. Therefore, you can declare both instrumentation beans in configuration:

~~~java
import graphql.analysis.MaxQueryComplexityInstrumentation;
import graphql.analysis.MaxQueryDepthInstrumentation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GraphQlQueryLimitsConfiguration {

    @Bean
    MaxQueryDepthInstrumentation maxQueryDepthInstrumentation() {
        return new MaxQueryDepthInstrumentation(8);
    }

    @Bean
    MaxQueryComplexityInstrumentation maxQueryComplexityInstrumentation() {
        return new MaxQueryComplexityInstrumentation(500);
    }
}
~~~

When the application starts, Spring Boot adds these instrumentations to the GraphQL Java execution pipeline. Operations are checked before resolvers perform any work.

The two thresholds in the example are not universal defaults for every application. Start conservatively in staging, run representative operations, and tune according to latency, resolver counts, response sizes, and database resources.

If your application constructs `GraphQL` or `GraphQlSource` manually without Boot's auto-configuration, register instrumentations directly. When you already have instrumentations for metrics, tracing, or logging, combine them with `ChainedInstrumentation` instead of overwriting existing configuration.

## 9. Calculating Complexity with Pagination

For collections, cost typically depends on the number of items returned. For instance, `books(first: 100)` may need to load 100 objects and resolve child fields for each one.

A more accurate formula is:

\[
C(field) = baseCost + pageSize \times childComplexity
\]

For fields returning scalar lists or having no child fields, cost must still scale with item count:

\[
C(field) = baseCost + pageSize \times \max(1, childComplexity)
\]

For example:

- `books(first: 50)` with 3 child fields may cost approximately `1 + 50 × 3 = 151`.
- If each book has `reviews(first: 10)`, review costs are multiplied by 10 as well.
- When two collections are nested, cost can grow by the product of item counts at each level.

This remains an estimation model. You must still account for child field costs and resolvers with special work.

## 10. Writing a Custom FieldComplexityCalculator

Suppose a schema has paginated collections:

~~~graphql
type Query {
    books(first: Int = 20): [Book!]!
    searchBooks(text: String!, first: Int = 20): [Book!]!
}

type Book {
    id: ID!
    title: String!
    reviews(first: Int = 10): [Review!]!
}

type Review {
    body: String!
}
~~~

We want:

- Regular fields to have a base cost of 1.
- `searchBooks` to have a higher base cost because it performs search.
- `books`, `searchBooks`, and `reviews` to multiply child field cost by item count.
- Pagination to be capped at a maximum of 100 items in both the resolver and the calculator.

Example:

~~~java
import graphql.analysis.FieldComplexityCalculator;
import graphql.analysis.MaxQueryComplexityInstrumentation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class GraphQlComplexityConfiguration {

    private static final int DEFAULT_BOOK_PAGE_SIZE = 20;
    private static final int DEFAULT_REVIEW_PAGE_SIZE = 10;
    private static final int MAX_PAGE_SIZE = 100;

    @Bean
    MaxQueryComplexityInstrumentation queryComplexityInstrumentation() {
        FieldComplexityCalculator calculator =
                (environment, childComplexity) -> {
                    String fieldName = environment.getField().getName();

                    int baseCost = "searchBooks".equals(fieldName) ? 10 : 1;

                    if ("books".equals(fieldName)
                            || "searchBooks".equals(fieldName)
                            || "reviews".equals(fieldName)) {

                        Object rawFirst =
                                environment.getArguments().get("first");

                        int defaultPageSize = "reviews".equals(fieldName)
                                ? DEFAULT_REVIEW_PAGE_SIZE
                                : DEFAULT_BOOK_PAGE_SIZE;

                        int requested = rawFirst instanceof Number
                                ? ((Number) rawFirst).intValue()
                                : defaultPageSize;

                        int pageSize = Math.max(
                                1,
                                Math.min(requested, MAX_PAGE_SIZE)
                        );

                        return baseCost
                                + pageSize * Math.max(1, childComplexity);
                    }

                    return baseCost + childComplexity;
                };

        return new MaxQueryComplexityInstrumentation(500, calculator);
    }
}
~~~

This example switches by field name to illustrate cost calculation. In a real application, build a cost lookup table keyed by schema coordinates such as `Query.searchBooks`, `Query.books`, and `Book.reviews` to avoid applying the same rule to fields with different semantics across types.

If you use this custom calculator, replace the simple complexity bean in the Spring Boot configuration section with this bean; do not register two `MaxQueryComplexityInstrumentation` beans for the same policy.

Important point: resolvers must enforce the same maximum pagination limit of 100. If the calculator caps cost at 100 while the resolver still allows returning 5,000 items, the complexity score will underestimate real cost.

If the server uses a default page size other than 20 or 10, the calculator must use that exact same default. Cost calculation rules and pagination enforcement rules must stay aligned.

## 11. Pricing Expensive Fields

Not all fields carry equal cost. A field returning a property from an object can be virtually free, whereas another field calls a search engine, aggregates reports, or invokes a downstream API.

You can assign weights per field:

| Field | Illustrative Base Cost | Reason |
| --- | ---: | --- |
| `id`, `title` | 1 | Simple property read |
| `author` | 2 | May require querying related data |
| `searchBooks` | 10 | Queries search engine |
| `exportReport` | 50 | Aggregates multiple data sources |
| `reviews(first:)` | Scales with page size | Cost grows with item count |

Example calculator:

~~~java
FieldComplexityCalculator calculator = (environment, childComplexity) -> {
    String fieldName = environment.getField().getName();

    int baseCost = switch (fieldName) {
        case "searchBooks" -> 10;
        case "exportReport" -> 50;
        case "author" -> 2;
        default -> 1;
    };

    return baseCost + childComplexity;
};
~~~

This illustrates basic field weights. If pagination must also be factored in, combine this base cost with the `pageSize` multiplier from the previous section instead of replacing the pagination formula.

Weights should be derived from profiling, query plans, and downstream call counts. Do not pick arbitrary numbers and treat them as exact measurements of CPU or database work.

## 12. Nested Pagination and Multiplicative Cost Across Levels

Consider the query:

~~~graphql
query BookReviews {
    books(first: 50) {
        id
        title
        reviews(first: 10) {
            body
        }
    }
}
~~~

If each book has up to 10 reviews, the server may have to process up to 500 reviews alongside 50 books.

With a calculator multiplying `pageSize × childComplexity`, the cost of `reviews` is calculated first, and then that cost is multiplied by the page size of `books`.

If a collection nests one more level—for example, reviews have reactions—the cost continues to scale by the reactions page size. This allows complexity to better reflect the potential number of returned objects.

Ensure every collection capable of returning multiple items applies a multiplier. If you only apply a multiplier to `books` and ignore `reviews`, clients can craft expensive queries through the nested field.

## 13. Aliases, Fragments, and Multiple Operations

GraphQL supports aliases and fragments to help clients structure operations. These features do not automatically make queries safer.

Aliases can invoke the same field multiple times:

~~~graphql
query {
    javaBooks: searchBooks(text: "java") {
        id
    }

    graphqlBooks: searchBooks(text: "graphql") {
        id
    }
}
~~~

Each branch can trigger a separate resolver call. Complexity must account for every occurrence in the operation, not just unique field names.

Fragments enable reusing selection sets:

~~~graphql
fragment BookSummary on Book {
    id
    title
    author {
        name
    }
}

query {
    books(first: 20) {
        ...BookSummary
    }
}
~~~

Depth and complexity must be evaluated on the operation after resolving fragments and type conditions. Do not write naive string-counting logic to replace the GraphQL parser/traverser.

If a document contains multiple operations, clients usually send `operationName` to select one. Test how your instrumentation handles both selected and unselected operations on the exact GraphQL Java version your application uses.

## 14. Parser Limits and Introspection Limits

GraphQL Java also enforces limits at the parser level. These handle oversized or syntactically overly complex documents before depth/complexity instrumentation runs.

The GraphQL Java v25 documentation currently lists the following defaults:

| Parser/introspection limit | Value stated in v25 docs | Purpose |
| --- | ---: | --- |
| Maximum query characters | 1 MB | Restricts overly long documents |
| Maximum query tokens | 15,000 | Limits tokenization work |
| Maximum whitespace tokens | 200,000 | Restricts abnormal whitespace |
| Maximum grammar rule depth | 500 | Limits parser stack depth |
| Good-faith introspection fields | 500 | Limits introspection size |
| Good-faith introspection depth | 20 | Limits introspection depth |

These values are from the GraphQL Java v25 documentation and should not be assumed immutable across every version. Check the GraphQL Java dependency managed by Spring Boot before relying on them.

Parser rule depth differs from query depth:

- Parser rule depth protects syntactic parsing.
- Query depth instrumentation limits field nesting paths in valid operations.
- Complexity instrumentation estimates total field cost after the document is parsed.

These three mechanisms address different stages and risks.

## 15. Pagination Limits Remain Mandatory

A complexity calculator does not replace input validation and pagination limits in resolvers.

Schema:

~~~graphql
type Query {
    books(first: Int = 20): [Book!]!
}
~~~

The schema above accepts the `first` argument but does not automatically enforce a maximum of 100. You must enforce the limit at the input/service layer:

~~~java
private static final int MAX_PAGE_SIZE = 100;

public List<Book> findBooks(int first) {
    if (first < 1 || first > MAX_PAGE_SIZE) {
        throw new IllegalArgumentException(
                "first must be between 1 and " + MAX_PAGE_SIZE
        );
    }

    return bookRepository.findFirstPage(first);
}
~~~

You can use a custom scalar, Bean Validation, or validation logic in the service depending on your architecture. Whichever approach you choose, the maximum must actually be enforced before querying data.

If the resolver clamps values automatically, use the same clamping rule inside the complexity calculator. Never let the calculator assume a page size of 100 while the resolver actually returns more.

## 16. DataLoader Does Not Replace Complexity Limits

DataLoader batches data fetches by key to mitigate N+1. However, DataLoader does not limit how many items a query requests.

For instance, a query loading 2,000 books with 100 reviews each can still produce a massive response, even when lookups are batched into fewer queries.

Combine:

- DataLoader or `@BatchMapping` to reduce data round trips.
- Pagination to bound item counts.
- Query depth to bound nesting.
- Query complexity to bound total estimated work.
- Rate/concurrency limits to bound concurrent operations.

Resolver optimization makes queries execute more efficiently; complexity limits reject over-budget queries.

## 17. Testing Depth-Exceeding Queries with GraphQlTester

Write integration tests verifying that over-limit operations are rejected. The example below uses an HTTP tester against a server running on a random port:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.graphql.test.tester.HttpGraphQlTester;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class QueryDepthLimitTests {

    @LocalServerPort
    private int port;

    private GraphQlTester graphQlTester;

    @BeforeEach
    void setUp() {
        WebTestClient client = WebTestClient.bindToServer()
                .baseUrl("http://localhost:" + port + "/graphql")
                .build();

        graphQlTester = HttpGraphQlTester.create(client);
    }

    @Test
    void rejectsQueryThatExceedsDepthLimit() {
        graphQlTester.document("""
                query TooDeep {
                    book(id: "book-42") {
                        author {
                            books(first: 10) {
                                reviews(first: 10) {
                                    author {
                                        books(first: 10) {
                                            reviews(first: 10) {
                                                author {
                                                    books(first: 10) {
                                                        title
                                                    }
                                                }
                                            }
                                        }
                                    }
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
}
~~~

The example assumes the schema has the corresponding fields and the depth limit is lower than the operation depth. In real tests, also verify that resolvers/services are not invoked when an operation is aborted, confirming the limit is enforced prior to field execution.

## 18. Testing Complexity and Pagination

Another test should send an operation whose complexity exceeds the budget:

~~~java
@Test
void rejectsQueryThatExceedsComplexityLimit() {
    graphQlTester.document("""
            query ExpensiveBooks {
                books(first: 100) {
                    id
                    title
                    reviews(first: 100) {
                        body
                    }
                }
            }
            """)
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).isNotEmpty());
}
~~~

The test must exercise the calculator and threshold configured in the application. If the query still executes, check:

- Whether the instrumentation bean was detected by Spring Boot.
- Whether a custom `GraphQlSource` overrides instrumentation.
- Whether the operation selects the expected collection fields.
- Whether the calculator reads the bound argument properly.
- Whether default page sizes match the schema and resolver.
- Whether the complexity threshold is low enough for the test to exceed it.

In addition to rejection tests, test valid queries just below the limit to avoid overly strict settings breaking normal clients.

Place this test method inside the same test class that initialized `GraphQlTester` in the previous section.

## 19. How to Choose Depth and Complexity Thresholds

There is no single threshold suitable for every GraphQL API. Thresholds depend on schema shape, resolver types, pagination, database performance, and SLAs.

A practical process:

1. Collect representative operations from logs or a persisted query registry.
2. Run operations against production-like data.
3. Record depth, complexity score, resolver count, database call count, and response size.
4. Measure p50/p95/p99 latency along with CPU/memory usage.
5. Set thresholds comfortably above normal valid traffic yet below overload territory.
6. Test the largest supported operation.
7. Adjust over time as traffic and schemas evolve.

For initial experiments, you might start with depth 8 and complexity 500, but always measure before deploying to production. Do not treat illustrative numbers in documentation as production defaults.

If you have distinct groups of operations, consider a persisted query allowlist, per-client quotas, or a separate policy for vetted operations.

## 20. Monitoring When Limits Block Queries

When instrumentation rejects an operation, emit sufficient telemetry to see which limit triggered and whether legitimate clients are impacted.

Record:

- Operation name or persisted operation ID.
- Execution ID/correlation ID.
- Query depth or complexity score.
- Configured maximum.
- Authenticated client identity.
- Timestamp and outcome.
- High-cost field groups or schema coordinates if safe to capture.

Do not log full query variables if they may contain personal data or tokens. Avoid putting raw queries and high-cardinality IDs into metric labels.

You can track metrics such as rejected requests by limit type, complexity score distribution, error rate, and latency prior to abort. Use logs/traces to investigate individual operations and keep metric labels low-cardinality.

## 21. Subscriptions and Long-Running Operations

Subscriptions have a different lifecycle from regular queries. Depth and complexity can evaluate the selection set when the client subscribes, but they do not limit how many events the server emits afterward.

Additional policies are needed for subscriptions:

- Concurrent subscriptions per connection/client.
- Event emission rate and buffer limits.
- Timeouts or maximum lifetimes where appropriate.
- Backpressure and cancellation.
- Per-event resolver cost.
- Authorization throughout the subscription's lifetime.

Never assume a subscription with low complexity has low long-term cost. A lightweight subscription emitting thousands of events per second can still impose heavy load.

## 22. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Deep queries still run | Instrumentation is not registered | Check Spring Boot `Instrumentation` beans |
| Wide queries with many fields pass | Only depth was configured | Add complexity instrumentation |
| Queries with huge page sizes pass | Using default complexity calculator | Add pagination multipliers |
| Calculator underestimates cost | Resolver does not share the same max page size/default | Align calculator and resolver |
| Normal queries get rejected | Threshold set too low | Measure real operations and adjust |
| Parser consumes resources before depth check | Confusing query depth with parser rule depth | Configure parser/request limits |
| DataLoader is present yet queries stay heavy | Confusing batching with data bounding | Combine pagination and complexity |
| Aliased repeated fields are undercounted | Calculator only counts unique field names | Evaluate every field occurrence in the operation |
| Subscriptions cause sustained load | Complexity checked only at subscribe time | Add event rate, concurrency, and backpressure controls |
| Metrics cannot explain blocked requests | Missing score and execution ID logs | Log safe limit metadata |

## 23. Hands-On Practice: Securing the Book Library API

Suppose the application has the schema:

~~~graphql
type Query {
    book(id: ID!): Book
    books(first: Int = 20): [Book!]!
    searchBooks(text: String!, first: Int = 20): [Book!]!
}

type Book {
    id: ID!
    title: String!
    author: Author!
    reviews(first: Int = 10): [Review!]!
}

type Author {
    id: ID!
    name: String!
    books(first: Int = 20): [Book!]!
}

type Review {
    id: ID!
    body: String!
    author: Author!
}
~~~

Follow these steps:

1. Create `MaxQueryDepthInstrumentation` with an initial limit of 8.
2. Create `MaxQueryComplexityInstrumentation` with an initial limit of 500.
3. Add a calculator that multiplies cost by `first` for `books`, `searchBooks`, and `reviews`.
4. Ensure resolvers/services enforce the same default and maximum page size.
5. Write a shallow query with few fields and confirm it is accepted.
6. Write a deeply nested query and confirm depth instrumentation rejects it.
7. Write a query with multiple large collections and confirm complexity instrumentation rejects it.
8. Write a query just below the threshold and confirm it still succeeds.
9. Verify that services/repositories are not called when a query is aborted.
10. Record metrics for blocked queries and tune thresholds based on benchmarks.

Once finished, answer:

- Why can a shallow-depth query still cause overload?
- Why doesn't default complexity accurately reflect the cost of `books(first: 1000)`?
- What happens if the calculator caps page size at 100 while the resolver returns 1,000 items?
- What does DataLoader improve and what does it not solve?
- Why do subscriptions need limits beyond depth and complexity?

## 24. Key Takeaways

- Query depth measures the deepest field nesting path in the selection tree.
- Query complexity estimates total field cost across the operation.
- `MaxQueryDepthInstrumentation` and `MaxQueryComplexityInstrumentation` are built-in instrumentations in GraphQL Java.
- The Spring Boot GraphQL starter automatically detects `Instrumentation` beans.
- `FieldComplexityCalculator` lets you compute cost based on fields, pagination, and specialized resolvers.
- The calculator must share the exact same pagination defaults and limits as the resolvers.
- Parser limits, body limits, pagination, and rate limits address different risks.
- DataLoader mitigates N+1 but does not replace item-count or complexity limits.
- Subscriptions require additional event rate, concurrency, and backpressure limits.
- Choose thresholds from real operations and benchmarks rather than copying example numbers mechanically.

Limiting query depth and complexity enables Spring for GraphQL to control operations before resolvers perform costly work. Combining nesting limits, pagination-aware cost, parser safeguards, data limits, and telemetry lets the server protect resources effectively while still serving legitimate client queries.

## References

- [GraphQL Java — Limits](https://graphql-java.com/documentation/limits/)
- [GraphQL Java — Instrumentation](https://graphql-java.com/documentation/instrumentation/)
- [GraphQL Java — MaxQueryDepthInstrumentation API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/MaxQueryDepthInstrumentation.html)
- [GraphQL Java — MaxQueryComplexityInstrumentation API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/MaxQueryComplexityInstrumentation.html)
- [GraphQL Java — FieldComplexityCalculator API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/FieldComplexityCalculator.html)
- [Spring for GraphQL — Request Execution and GraphQlSource](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
