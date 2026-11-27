# Query complexity limit in Spring for GraphQL

## Objectives

After this lesson, you will be able to:

- Explain why GraphQL requires limits on query depth and query complexity.
- Distinguish query depth from query complexity.
- Identify deep queries, wide queries, aliases, and nested lists that risk exhausting resources.
- Configure `MaxQueryDepthInstrumentation` and `MaxQueryComplexityInstrumentation`.
- Wire GraphQL Java instrumentations into Spring Boot's `GraphQlSource`.
- Design field costs based on paginated item counts and resolver cost.
- Combine complexity limits with pagination, DataLoader, timeouts, and rate limiting.
- Test that rejected queries are stopped before DataFetchers execute.
- Select appropriate thresholds based on workloads and actual measurements.

## 1. Why do we need a query complexity limit?

GraphQL lets clients choose the fields and data shape to be returned. A small HTTP request can ask the server to load deeply nested relationships, invoke many DataFetchers, or produce a massive amount of data.

Example of a seemingly valid query:

~~~graphql
query {
    books(first: 100) {
        edges {
            node {
                id
                title
                author {
                    name
                    books(first: 100) {
                        edges {
                            node {
                                title
                            }
                        }
                    }
                }
            }
        }
    }
}
~~~

If each `author` loads a list of books again, the number of requested objects can grow rapidly at each nesting level. The query stays tiny in bytes, yet its execution cost can be huge.

Protections such as request body limits, authentication, or rate limiting remain necessary, but they do not directly measure the amount of work a GraphQL selection demands.

A query complexity limit sets an operational budget on the query structure before the server runs its DataFetchers. It rejects overly deep or expensive queries before they put heavy load on databases and downstream services.

## 2. How do query depth and query complexity differ?

The two limits address two different query patterns:

| Limit | Measures | Detects well |
| --- | --- | --- |
| Query depth | Number of nested field levels | Queries with overly deep nested relations |
| Query complexity | Total estimated cost of fields | Wide queries or queries with many expensive fields/lists |

Query depth is the number of nested selection levels according to the instrumentation's rules. Query complexity is the total cost computed from each field and its child fields.

Example of a wide but shallow query:

~~~graphql
query {
    books { id }
    authors { id }
    publishers { id }
    categories { id }
    reviews { id }
}
~~~

This query has low depth but multiple root fields. A depth limit may fail to catch the combined load across many fields.

Conversely, a deep query:

~~~graphql
query {
    author(id: "author-1") {
        books {
            reviews {
                author {
                    books {
                        reviews {
                            id
                        }
                    }
                }
            }
        }
    }
}
~~~

This query can exceed a depth limit even though each level selects only a single field.

In practice, combine depth and complexity limits. Depth bounds nesting shape; complexity bounds the total field budget.

## 3. Query complexity is not execution time

Complexity is an estimate derived from the GraphQL document, arguments, and configured cost rules. It is not an exact measure of milliseconds or SQL query counts.

Two fields can have drastically different real costs:

- A field reading a property already present on the parent object.
- A field calling a downstream service.
- A field running full-text search.
- A field loading a large list.
- A field performing calculations or aggregation queries.

If every field carries the same cost, instrumentation cannot tell which fields are more expensive in business logic. Therefore, the application must define a cost model tailored to its schema and workload.

A complexity limit is a defensive guardrail. It does not replace profiling, query plans, timeouts, or data access controls.

## 4. GraphQL Java instrumentation

Spring for GraphQL uses GraphQL Java to parse, validate, and execute GraphQL operations. GraphQL Java provides instrumentations to inspect queries before and during execution.

Two common instrumentations for query limits:

- `MaxQueryDepthInstrumentation`: rejects operations whose depth exceeds a threshold.
- `MaxQueryComplexityInstrumentation`: rejects operations whose complexity exceeds a threshold.

Both classes live in package `graphql.analysis`.

Depth instrumentation accepts a maximum depth limit. Complexity instrumentation accepts a maximum complexity limit and can also accept a field complexity calculator to define per-field costs.

These limits must be configured on the GraphQL runtime. Simply setting an arbitrary property in `application.yml` will not automatically activate instrumentation if the version of Spring Boot/Spring for GraphQL in use does not provide a corresponding property.

## 5. Configuring the query depth limit

Example creating an instrumentation with a maximum depth of 8:

~~~java
import graphql.analysis.MaxQueryDepthInstrumentation;

MaxQueryDepthInstrumentation depthLimit =
        new MaxQueryDepthInstrumentation(8);
~~~

The threshold `8` is only an example. The right value depends on your schema, valid nested relationships, and how the application uses fragments.

When a query exceeds the limit, GraphQL Java rejects the operation and returns a GraphQL error. DataFetchers of the rejected operation should not execute.

Depth limits are helpful for schemas with many nested relationships, such as:

- Organization → teams → members → projects → tasks.
- Book → author → books → reviews → author.
- Category → children → products → variants.

Do not set the threshold too low and prevent clients from executing valid use cases. Measure the depth of real operations and leave a safe margin for legitimate queries.

## 6. Configuring the query complexity limit

Example using complexity instrumentation with a maximum budget of 200:

~~~java
import graphql.analysis.MaxQueryComplexityInstrumentation;

MaxQueryComplexityInstrumentation complexityLimit =
        new MaxQueryComplexityInstrumentation(200);
~~~

With the default configuration, GraphQL Java uses its default field complexity calculator to sum a field's cost and its child fields' cost. Exact calculation details should be checked against the GraphQL Java version your application uses.

A threshold of `200` is not a universal default for every system. A small schema may need a lower budget; an API with many simple fields may need a higher threshold.

Complexity limits are particularly useful for wide queries, many aliases, or many selection branches. However, if list fields can return hundreds or thousands of items, include list size in the cost model rather than counting every field as one unit.

## 7. Registering instrumentation in Spring Boot

With Spring Boot GraphQL auto-configuration, you can register GraphQL Java `Instrumentation` instances as Spring beans. Boot collects these beans in order and wires them into `GraphQlSource`:

~~~java
import graphql.execution.instrumentation.Instrumentation;
import graphql.analysis.MaxQueryComplexityInstrumentation;
import graphql.analysis.MaxQueryDepthInstrumentation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class GraphQlQueryLimitConfiguration {

    @Bean
    Instrumentation maxQueryDepthInstrumentation() {
        return new MaxQueryDepthInstrumentation(8);
    }

    @Bean
    Instrumentation maxQueryComplexityInstrumentation() {
        return new MaxQueryComplexityInstrumentation(200);
    }
}
~~~

Each bean contributes an instrumentation to the GraphQL runtime. This registration approach lets Boot combine application-supplied instrumentations with others configured in the context, such as observation. If a specific order is needed, declare `@Order` or implement `Ordered` and verify that order in an integration test.

For applications without Spring Boot, you can configure the instrumentation list directly on `GraphQlSource.Builder` or GraphQL Java's `GraphQL.Builder`. When assembling the list manually, combine depth/complexity limits with existing instrumentations rather than accidentally replacing them.

After starting the application, test an over-limit query against the GraphQL endpoint to confirm the instrumentation is actually active in the runtime.

## 8. Customizing field cost

A query complexity calculator can assign different costs to individual fields. GraphQL Java supports `FieldComplexityCalculator` to compute cost from the field environment and child complexity.

Illustrative example: a normal field has a base cost of 1; if the field accepts a `first` argument, child field complexity is multiplied by the requested item count:

~~~java
import graphql.analysis.MaxQueryComplexityInstrumentation;

MaxQueryComplexityInstrumentation complexityLimit =
        new MaxQueryComplexityInstrumentation(
                500,
                (environment, childComplexity) -> {
                    int multiplier = 1;

                    Object first = environment.getArguments().get("first");
                    if (first instanceof Number number) {
                        multiplier = Math.max(1, Math.min(number.intValue(), 100));
                    }

                    if (environment.getArguments().containsKey("first")) {
                        return 1 + multiplier * (1 + childComplexity);
                    }

                    return 1 + childComplexity;
                }
        );
~~~

Illustrative formula:

\[
C(field) = 1 + multiplier \times C(children)
\]

For a field with a `first` argument, if the client requests 100 items, the cost of each item and its child fields is multiplied up to 100 times. Fields without a `first` argument continue using the basic `1 + childComplexity` formula.

This is a simple cost model. For real schemas, distinguish list fields from scalar fields and apply multipliers accurately to paginated fields. Do not multiply every field's cost merely because it happens to have an argument named `first`.

The example above assumes fields with a `first` argument are paginated fields with no other default page size to apply. If the SDL declares a default such as `first: Int = 20`, ensure the calculator accounts for the default value when the client omits the argument. In production systems, identify paginated fields by parent type and field name, then apply each field's corresponding default and maximum page size.

## 9. Incorporating pagination into the cost model

A list field typically scales in cost with the number of returned elements. Thus `first`, `limit`, or `pageSize` are critical arguments in complexity calculation.

Example SDL:

~~~graphql
type Query {
    books(first: Int = 20): [Book!]!
}

type Book {
    id: ID!
    title: String!
    reviews(first: Int = 10): [Review!]!
}
~~~

A query:

~~~graphql
query {
    books(first: 50) {
        id
        reviews(first: 20) {
            id
        }
    }
}
~~~

If each book loads up to 20 reviews and the client requests 50 books, total reviews can reach 1,000. A complexity model without multipliers can severely underestimate this cost.

If the client omits `first`, the calculator must still use the schema-declared default or service-enforced default. Otherwise, an operation could omit the argument to receive a large default page while being scored as a single item.

Best practices:

- Set small, explicit default page sizes.
- Cap maximum page sizes in the resolver/service or input validation.
- Include list multipliers in the complexity calculator.
- Account for nested lists at every level.
- Use conservative cost models for fields calling downstream services or running aggregations.

A complexity calculator is only one layer of defense. Resolvers must still reject out-of-bounds page sizes so clients cannot invoke fields along paths missed by the calculator.

## 10. Assigning costs by field category

Not all fields have equal cost. You can design a cost model by field coordinates or schema metadata:

| Field category | Example | Suggested cost |
| --- | --- | --- |
| Scalar on parent | `Book.title` | Low |
| One-to-one relation | `Book.author` | Medium |
| List relation | `Author.books(first: ...)` | Based on page size |
| Search | `searchBooks(query: ...)` | Higher than ID lookup |
| Aggregate/report | `salesSummary(range: ...)` | High |
| External lookup | `shippingEstimate` | Based on downstream cost |

The table above is only a classification scheme for cost design, not default numbers from GraphQL Java.

For expensive fields, assign a higher fixed cost or compute cost from arguments. Avoid turning query content, user IDs, or arbitrary client values into metric dimensions solely to support the cost model.

A good cost model is easy to explain, has an upper bound, and is tested against operations representing real workloads.

## 11. Fragments, aliases, and query breadth

GraphQL allows selection reuse with fragments:

~~~graphql
fragment BookSummary on Book {
    id
    title
    author {
        name
    }
}

query {
    first: books(first: 20) {
        ...BookSummary
    }
    second: books(first: 20) {
        ...BookSummary
    }
}
~~~

Aliases allow clients to invoke the same field multiple times with different arguments. This can multiply the number of branches to execute even when the document looks concise thanks to fragments.

Depth limits primarily constrain nesting. Complexity limits must reflect the actual field selections after document analysis, including fragments and aliases as calculated by the GraphQL Java version in use.

Add tests for:

- A fragment spread in multiple places.
- The same field invoked through multiple aliases.
- Multiple root fields in one operation.
- Nested lists combined with fragments.
- `@skip` and `@include` directives if they affect workloads the application must bound.

Never assume that declaring a fragment once means its cost is counted only once. What matters is how many times the selection can execute in the operation.

## 12. Complexity limits do not replace DataLoader

A query complexity limit estimates work from the GraphQL selection. It does not automatically solve N+1 database queries.

For example, a query fetches 100 books and loads the author for each. If the resolver calls the repository once per book, the server can still trigger N+1 queries even when complexity is below the threshold.

DataLoader or `@BatchMapping` batches related loads together. The two mechanisms serve different goals:

- Complexity limits bound how much work a client may request.
- DataLoader reduces backend calls when multiple fields need related data.

A healthy system needs both. Do not raise complexity limits merely because DataLoader was added; a batch can still retrieve and serialize huge amounts of data.

## 13. Combining with other defense layers

Query complexity is only one piece of defense in depth:

| Defense layer | Problem controlled |
| --- | --- |
| HTTP request body limit | Overly large request documents or variables |
| Authentication/authorization | Who is permitted to call operations and fields |
| Query depth limit | Overly deep nested selections |
| Query complexity limit | Overly high total estimated cost |
| Pagination max size | Lists returning too many elements |
| DataLoader/batching | Repeated backend calls |
| Timeout | Operations or downstream calls running too long |
| Rate limiting | A single client sending too many requests |
| Concurrency limit | Too many simultaneous operations |
| Persisted query/allowlist | Restricting which documents are allowed to run |

These layers complement one another. A low-complexity query can still hit a hanging downstream field; timeouts remain necessary. A valid query can still abuse resources if sent hundreds of times; rate limiting remains necessary.

## 14. Handling rejected queries

When instrumentation rejects a query for exceeding depth or complexity, GraphQL execution returns an error via GraphQL Java's error mechanism. Clients should receive an error clear enough to know the operation was not accepted.

Do not expose stack traces or internal details of the schema and instrumentation to clients. You can standardize error codes in the error handling layer if the API requires a stable contract.

Distinguish between:

- Queries rejected by depth/complexity limits.
- Valid queries where a resolver throws a business error.
- Resolvers or infrastructure encountering an internal error.
- HTTP requests rejected before GraphQL execution due to body size, authentication, or rate limits.

Exact HTTP status codes depend on GraphQL-over-HTTP handling, media type, and server configuration. Clients should inspect GraphQL `errors` rather than assuming every complexity violation returns the same HTTP status.

## 15. Testing depth limits

Test both a valid query below the threshold and a query exceeding the threshold.

Example test logic using GraphQlTester:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

@Test
void shouldRejectQueryThatExceedsDepthLimit() {
    GraphQlTester.Response response = graphQlTester.document("""
            query {
                author(id: "author-1") {
                    books {
                        author {
                            books {
                                id
                            }
                        }
                    }
                }
            }
            """)
            .execute();

    response.errors().satisfy(errors ->
            assertThat(errors).isNotEmpty()
    );
}
~~~

The test requires a schema with matching relations and the depth limit configured in the GraphQL runtime. To verify the query is blocked before DataFetchers run, you can use a spy or counter in the service:

~~~java
assertThat(bookServiceInvocationCount.get()).isZero();
~~~

This assertion must run after the request completes, and the test fixture must ensure no invocations came from setup or other tests.

Do not assert only that errors exist; a business error could also pass that assertion. If your instrumentation version exposes a stable message or error classification, assert the error code/message defined by your application's contract.

## 16. Testing complexity limits and field costs

Create low-cost and high-cost operations to verify the threshold works.

Cases to include:

- A small query under the threshold.
- A wide query with many root fields.
- A query with nested lists and large page sizes.
- A query calling a field with a high fixed cost.
- A query repeating fields via aliases.
- A query spreading fragments in multiple positions.
- Missing, null, or out-of-bounds pagination arguments.
- Queries passing page size via variables instead of inline literals.

If the calculator uses the `first` argument, test both default values and runtime values passed in `variables`. This verifies the calculator receives GraphQL-processed arguments matching your library version's contract.

Tests must prove that over-budget operations do not invoke expensive services. At the same time, valid queries must succeed so limits do not accidentally block legitimate use cases.

Example assertion for an operation with an over-budget page size:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.springframework.graphql.test.tester.GraphQlTester;

GraphQlTester.Response response = graphQlTester.document("""
        query Books($first: Int!) {
            books(first: $first) {
                id
                title
            }
        }
        """)
        .variable("first", 100)
        .execute();

response.errors().satisfy(errors ->
        assertThat(errors).anySatisfy(error ->
                assertThat(error.getMessage())
                        .contains("maximum query complexity exceeded")
        )
);
assertThat(bookServiceInvocationCount.get()).isZero();
~~~

The example uses GraphQL Java's default error message for illustration. If your application customizes error messages or upgrades GraphQL Java, assert a stable error code/classification published by your API.

## 17. Choosing thresholds from real workloads

Do not pick depth or complexity limits solely from a popular number found online.

Threshold selection workflow:

1. Collect valid operations from clients and test environments.
2. Measure depth and complexity of representative operations.
3. Identify the highest-cost queries that remain legitimate use cases.
4. Set thresholds above valid workloads with a safety margin.
5. Try extreme queries and verify they are rejected before resolvers run.
6. Monitor limit-related error rates after deployment.
7. Adjust thresholds as the schema or client operations evolve.

You can start with a relatively permissive threshold in staging, gather data, and tighten gradually. Do not use high-cardinality values like raw query text as metric tags. When you need to know which operation exceeded the threshold, record the operation name in controlled traces or logs.

## 18. Common pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Deep queries still run | Depth instrumentation is not wired into the GraphQL runtime | Check GraphQlSource customizers and instrumentation chain |
| Complexity limit has no effect | Instantiated instrumentation object without registering it | Register instrumentation on the GraphQL builder |
| Metrics/tracing disappear after adding limits | Existing instrumentations were replaced instead of composed | Chain instrumentations together and verify Observation |
| Wide queries bypass depth limit | Depth does not count sibling fields | Add a complexity limit |
| Huge list queries still score low | Cost model does not multiply by page size | Customize field complexity calculator |
| Page size exceeds limits | Relying solely on query complexity | Validate max page size in resolver/service |
| Fragments or aliases spike load | Tests do not cover reused selections | Add operations with fragments and aliases |
| Query rejected but test passes falsely | Only asserted presence of errors, which may be a business error | Check error code/message and verify DataFetchers were not called |
| Query limit blocks valid operations | Threshold too low or cost model overly conservative | Measure valid workloads and calibrate |
| DataLoader added yet server still overloads | Batching reduces round trips but does not cap object counts | Keep complexity, pagination, and timeouts |
| Long-lived subscriptions cause load | Complexity does not limit connection lifetime or event rate | Add connection quotas, rate limits, and publisher bounds |

## 19. Workflow for implementing query complexity limits

When protecting a GraphQL API with query limits, follow this sequence:

1. **Measure workload.** Collect valid operations and identify expensive queries.
2. **Choose depth limit.** Bound nested selection levels to match the schema.
3. **Choose complexity limit.** Set a budget for total field cost.
4. **Register instrumentation.** Configure `MaxQueryDepthInstrumentation` and `MaxQueryComplexityInstrumentation` in the GraphQL runtime.
5. **Design cost model.** Account for pagination, nested lists, and fields calling downstream services.
6. **Guard page sizes.** Validate list bounds at the service/resolver layer.
7. **Compose instrumentations.** Preserve existing observation and tracing instrumentations.
8. **Test negative cases.** Include deep queries, wide queries, aliases, fragments, and nested lists.
9. **Verify pre-resolver rejection.** Confirm rejected operations never invoke expensive services.
10. **Monitor and calibrate.** Track rejected queries and workload shifts over time.

## 20. Summary

Query complexity limits help Spring for GraphQL protect servers from operations that are overly deep or demand excessive work. `MaxQueryDepthInstrumentation` caps nested selection depth; `MaxQueryComplexityInstrumentation` enforces a field cost budget. The two mechanisms complement each other and should be registered with the GraphQL Java runtime via `GraphQlSource` configuration.

The default cost model is only a rough estimate. For list fields, incorporate pagination multipliers and enforce maximum page sizes in services. Complexity limits do not replace DataLoader, timeouts, authentication, rate limiting, or concurrency controls. Test both valid and rejected queries, verify DataFetchers do not execute when operations exceed thresholds, and calibrate limits based on real workloads.

## References

- [Spring for GraphQL – Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Boot – GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [GraphQL Java – Instrumentation](https://graphql-java.com/documentation/instrumentation/)
- [GraphQL Java – MaxQueryDepthInstrumentation API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/MaxQueryDepthInstrumentation.html)
- [GraphQL Java – MaxQueryComplexityInstrumentation API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/MaxQueryComplexityInstrumentation.html)
