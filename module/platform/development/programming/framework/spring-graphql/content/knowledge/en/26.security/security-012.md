# Limiting query complexity

## 1. Why limit query complexity?

GraphQL lets clients freely select fields, nested relationships, and the volume of data to fetch in a single operation. This flexibility reduces the number of client requests, yet also allows a single operation to demand a massive amount of work from the server.

For example, a client can request hundreds of books, each with many reviews, where each review loads a user and their activity history. Even though the client sends only one HTTP request, the server may have to run numerous database queries, call multiple services, and build a huge response.

Query complexity is a score estimating the cost of an operation based on the fields selected by the client. The server calculates the score before invoking DataFetchers. If the score exceeds the limit, the server rejects the operation and does not begin executing resolvers.

Limiting complexity protects CPU, memory, databases, downstream services, and response times. It serves as a demand-control layer for GraphQL APIs, especially useful when the API permits external clients to author arbitrary queries.

## 2. Distinguishing query complexity, query depth, and query breadth

These three concepts measure different characteristics of an operation:

| Concept | Measures | Example risk |
| --- | --- | --- |
| Query depth | Maximum nesting depth of the selection set | `user { friends { friends { friends { ... } } } }` |
| Query breadth | Number of fields at the same level or number of aliases in an operation | A shallow query with hundreds of aliases calling the same expensive field |
| Query complexity | Total estimated cost of fields, optionally weighted and scaled by list size | A field returning thousands of items, each loading multiple relationships |

Example of a shallow query with many fields:

```graphql
query Dashboard {
    me {
        id
        name
        email
        orders { id }
        invoices { id }
        notifications { id }
        recommendations { id }
    }
}
```

The query's depth is not large, yet each field may invoke a different service or query different data. A depth limit alone cannot capture this cost.

Conversely, a query with few fields nested across many levels can also cause heavy load. Therefore, combine complexity with depth, pagination, alias/breadth limits, and rate limiting.

## 3. How is query complexity calculated?

The GraphQL specification does not mandate a fixed complexity formula. The score is a server-chosen policy based on the schema structure and the actual cost of fields.

GraphQL Java provides `FieldComplexityCalculator` to compute the cost of each field. The default formula of `MaxQueryComplexityInstrumentation` is:

\[
C(field) = 1 + \sum C(child)
\]

Each field has a base cost of 1, plus the sum of its child fields' costs.

Example:

```graphql
query {
    book {
        id
        title
        author {
            name
        }
    }
}
```

Calculated from the deepest field:

| Field | Calculation | Complexity |
| --- | --- | ---: |
| `name` | `1` | 1 |
| `author` | `1 + name` | 2 |
| `id` | `1` | 1 |
| `title` | `1` | 1 |
| `book` | `1 + id + title + author` | 5 |

The total complexity of the operation is 5 under this default formula. The score is not runtime measured in milliseconds; it is a relative unit used to compare operations and enforce limits.

## 4. Why is the default formula insufficient for List fields?

A field returning a single object and a field returning a list of 1,000 objects do not carry the same cost, even though both count as a single field under the default formula.

Example:

```graphql
type Query {
    books(first: Int! = 20): [Book!]!
}

type Book {
    id: ID!
    title: String!
    author: Author
    reviews(first: Int! = 10): [Review!]!
}
```

Query:

```graphql
query {
    books(first: 100) {
        id
        title
        reviews(first: 20) {
            id
            rating
        }
    }
}
```

If the server only counts fields, it might rate this query fairly cheap. In reality, the server may have to process up to 100 books and up to 2,000 reviews. Item counts and child fields cause cost to scale with list size.

A realistic cost model should consider:

- The maximum item count permitted by pagination arguments.
- The base cost of each field.
- The cost of child fields per item.
- Fields that call external systems or perform heavy queries.
- Fields that can produce nested lists.

For lists, you can use an estimation formula:

\[
C(list) = 1 + pageSize \times (1 + C(children))
\]

This is an example formula for an application, not a mandatory GraphQL rule. When lists are nested, multiplication applies at each level so the score reflects the growth in item count.

## 5. Using `MaxQueryComplexityInstrumentation`

GraphQL Java provides `MaxQueryComplexityInstrumentation` in the `graphql.analysis` package. This instrumentation analyzes the operation and aborts execution if complexity exceeds the limit.

Example configuring directly in GraphQL Java:

```java
import graphql.analysis.MaxQueryComplexityInstrumentation;
import graphql.GraphQL;

GraphQL graphQL = GraphQL.newGraphQL(schema)
    .instrumentation(new MaxQueryComplexityInstrumentation(500))
    .build();
```

In the example, an operation with complexity greater than 500 is rejected. An operation scoring 500 remains within the limit.

When complexity exceeds the threshold, GraphQL Java raises an execution-aborted error. The response may contain an error similar to:

```json
{
  "errors": [
    {
      "message": "maximum query complexity exceeded 620 > 500",
      "extensions": {
        "classification": "ExecutionAborted"
      }
    }
  ]
}
```

The exact message may vary depending on the GraphQL Java version or how the application customizes the instrumentation. What matters is that the operation stops before resolvers begin accessing data.

## 6. Integrating the instrumentation in Spring Boot

Spring Boot auto-configures `GraphQlSource` and detects beans implementing `graphql.execution.instrumentation.Instrumentation`. Therefore, in a Spring for GraphQL application using Boot, you can declare `MaxQueryComplexityInstrumentation` as a bean.

```java
import graphql.analysis.MaxQueryComplexityInstrumentation;
import graphql.execution.instrumentation.Instrumentation;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GraphQlSecurityConfig {

    @Bean
    Instrumentation maxQueryComplexityInstrumentation() {
        return new MaxQueryComplexityInstrumentation(500);
    }
}
```

Spring Boot registers the instrumentation bean with `GraphQlSource` during auto-configuration. You do not need to manually construct `GraphQL` or replace `ExecutionGraphQlService` just to enable complexity limits.

If the application does not use Spring Boot auto-configuration, configure instrumentation via `GraphQlSource.Builder.instrumentation(...)` when building `GraphQlSource`.

Version note: Spring Boot 3.x and 4.x may change the package of certain `GraphQlSource` customization APIs. Registering an `Instrumentation` bean avoids coupling directly to `GraphQlSourceBuilderCustomizer` package names in basic setups.

## 7. Limiting query depth as well

`MaxQueryComplexityInstrumentation` and `MaxQueryDepthInstrumentation` solve two different problems. Both can be registered to block operations that are either too deep or too expensive.

```java
import graphql.analysis.MaxQueryDepthInstrumentation;
import graphql.analysis.MaxQueryComplexityInstrumentation;
import graphql.execution.instrumentation.Instrumentation;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class QueryGuardConfig {

    @Bean
    Instrumentation maxQueryDepthInstrumentation() {
        return new MaxQueryDepthInstrumentation(8);
    }

    @Bean
    Instrumentation maxQueryComplexityInstrumentation() {
        return new MaxQueryComplexityInstrumentation(500);
    }
}
```

Spring Boot detects the instrumentation beans and combines them during GraphQL execution. If an operation has depth greater than 8 or complexity greater than 500, the corresponding instrumentation can reject the operation.

Do not set the depth limit so low that it blocks legitimate schema relationships. Measure typical depths from real operations, then pick a threshold with safety headroom for valid use cases.

## 8. Customizing costs with `FieldComplexityCalculator`

In many applications, the default formula is insufficient because some fields are far more expensive than others. GraphQL Java lets you pass a `FieldComplexityCalculator` to the `MaxQueryComplexityInstrumentation` constructor.

The calculator receives two arguments:

- `FieldComplexityEnvironment`: details about the current field, parent type, field definition, and arguments.
- `childComplexity`: total complexity score of child fields.

For example, a `recommendations` field calls multiple services and is assigned a higher base cost than ordinary fields:

```java
import graphql.analysis.FieldComplexityCalculator;
import graphql.analysis.MaxQueryComplexityInstrumentation;
import graphql.execution.instrumentation.Instrumentation;

FieldComplexityCalculator calculator = (environment, childComplexity) -> {
    String fieldName = environment.getFieldDefinition().getName();

    if ("recommendations".equals(fieldName)) {
        return 25 + childComplexity;
    }

    return 1 + childComplexity;
};

Instrumentation instrumentation =
    new MaxQueryComplexityInstrumentation(500, calculator);
```

In this example, each selection of `recommendations` has a base cost of 25. If the field has child fields, their cost is added on top.

Determine weights from actual resolver costs: number of database calls, external service latency, data volume returned, and CPU usage. Calibrate weights against telemetry and production load rather than picking arbitrary numbers.

## 9. Calculating complexity from pagination arguments

To reflect data scale, the calculator can read pagination arguments from `FieldComplexityEnvironment.getArguments()`.

Example schema:

```graphql
type Query {
    books(first: Int! = 20): [Book!]!
}
```

Calculator:

Replace the basic complexity bean from the previous section with this custom calculator; do not declare two beans with the same name.

```java
import graphql.analysis.FieldComplexityCalculator;
import graphql.analysis.MaxQueryComplexityInstrumentation;
import graphql.execution.instrumentation.Instrumentation;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GraphQlComplexityConfig {

    private static final int DEFAULT_PAGE_SIZE = 20;
    private static final int MAX_PAGE_SIZE = 100;

    @Bean
    Instrumentation queryComplexityInstrumentation() {
        FieldComplexityCalculator calculator = (environment, childComplexity) -> {
            String parentType = environment.getParentType().getName();
            String fieldName = environment.getFieldDefinition().getName();

            if ("Query".equals(parentType) && "books".equals(fieldName)) {
                Object rawFirst = environment.getArguments().get("first");
                int requested = rawFirst instanceof Number number
                    ? number.intValue()
                    : DEFAULT_PAGE_SIZE;

                int pageSize = Math.max(0, Math.min(requested, MAX_PAGE_SIZE));
                return 1 + pageSize * (1 + childComplexity);
            }

            return 1 + childComplexity;
        };

        return new MaxQueryComplexityInstrumentation(500, calculator);
    }
}
```

For the `books` field, cost is calculated from the requested item count and the sum of child field costs. Other fields continue using the default formula.

`MAX_PAGE_SIZE` in the calculator must match the actual limit enforced in the resolver or service. If the calculator caps the score while the resolver still allows fetching 10,000 items, the model will underestimate true cost. Validate the `first` argument or enforce the limit in the service before querying the database.

When there are multiple list fields such as `books`, `reviews`, and `comments`, apply the cost model to each field. With nested lists, multiplying by page size at each level makes the score grow rapidly when clients request multiple layers of data.

## 10. Handling very expensive fields

Some fields can be very costly even when returning a single object. For example:

- `recommendations`: runs ranking algorithms or calls a recommendation model.
- `financialReport`: aggregates data across many tables and accounting periods.
- `search`: runs full-text search or queries a search cluster.
- `analytics`: computes statistics over large datasets.
- `externalProfile`: calls a high-latency external service.

You can assign dedicated base costs to such fields:

```java
private static int baseCost(String parentType, String fieldName) {
    if ("Query".equals(parentType) && "financialReport".equals(fieldName)) {
        return 80;
    }

    if ("Query".equals(parentType) && "recommendations".equals(fieldName)) {
        return 30;
    }

    if ("Query".equals(parentType) && "search".equals(fieldName)) {
        return 15;
    }

    return 1;
}
```

The calculator can call `baseCost(...)` and add `childComplexity`. Distinguishing by parent type avoids applying the same weight to fields that share a name but serve different business purposes.

If cost also depends on arguments, inspect those arguments as well. For instance, `analytics(period: YEAR)` may be costlier than `analytics(period: DAY)`. Avoid feeding sensitive data or authorization state into the cost model unnecessarily.

## 11. How aliases and fragments affect complexity

GraphQL lets clients invoke the same field multiple times using aliases:

```graphql
query Compare {
    small: books(first: 10) {
        id
    }

    large: books(first: 100) {
        id
        reviews(first: 20) {
            rating
        }
    }
}
```

The two aliases `small` and `large` are two separate field selections in the operation. They can trigger two resolver invocations with different arguments. The cost model must count both rather than inspecting the field name `books` only once.

Fragments allow reusing selection sets:

```graphql
fragment BookDetails on Book {
    id
    title
    author {
        name
    }
}

query {
    books(first: 50) {
        ...BookDetails
    }
}
```

A fragment is not a new resolver. Fields inside the fragment remain part of the operation's selection set and must be counted in complexity. When testing the cost model, include cases with aliases, named fragments, and inline fragments to ensure analysis covers all query structures clients use.

## 12. Complexity limits do not replace pagination and other guardrails

Never enable `MaxQueryComplexityInstrumentation` and then let every list return unbounded items. A cost model is an estimate; pagination and validation enforce actual data bounds.

Protective layers to combine:

| Measure | Purpose |
| --- | --- |
| Mandatory pagination for large lists | Limits how many items a single field can return |
| `MaxQueryComplexityInstrumentation` | Caps the total estimated cost of an operation |
| `MaxQueryDepthInstrumentation` | Blocks overly deeply nested queries |
| Alias/breadth limits | Prevents too many fields or aliases at the same level |
| Operation count limit in HTTP batches | Prevents sending many operations in a single batch request |
| Rate limiting | Limits request rate or query budget per user/API key |
| Persisted/trusted documents | Permits only pre-approved operations |
| Timeouts and resource limits | Bounds runtime and resource consumption |

GraphQL Java provides instrumentations for complexity and depth. Breadth, alias, or batch operation count policies may require custom instrumentation, custom validation, or limits at the transport/gateway. Do not assume the two built-in instrumentations handle all of these cases.

## 13. DataLoader reduces N+1 but does not make queries free

DataLoader and `@BatchMapping` reduce backend calls by batching many data requests together. They solve the N+1 problem, but do not necessarily reduce the total number of objects the server must load and return.

For example, a query requests 1,000 books with 20 reviews each. DataLoader may collapse thousands of individual queries into a few batch queries, yet the server still has to process and serialize up to 20,000 reviews.

Therefore:

- DataLoader reduces backend round trips.
- Pagination caps item counts.
- Complexity estimates total operation work.
- Depth limits nesting levels.
- Timeouts and rate limits protect resources over time.

These measures complement one another. Do not reduce a list field's cost merely because its resolver uses DataLoader.

## 14. How to choose the complexity threshold?

There is no single threshold suitable for every GraphQL API. The threshold depends on the schema, how resolvers access data, hardware, database capacity, usage patterns, and target latency.

Setup process:

1. Collect legitimate operations currently used by clients.
2. Measure latency, database query counts, returned item counts, and external service call durations.
3. Design base weights for fields and list fields.
4. Compute complexity scores for common legitimate operations.
5. Choose a threshold sufficient for valid operations while blocking overly expensive queries.
6. Trial in staging or observe-only mode before enabling blocking in production.
7. Monitor rejected requests and adjust the cost model as the schema changes.

Consider different client groups. Internal clients may use persisted documents and dedicated budgets; public clients may need lower thresholds, stricter pagination, and per-API-key rate limits.

With only a single global threshold, some legitimate yet unusually heavy operations might be rejected. You can use persisted operations, custom policies, or per-user/per-role cost budgets to manage those cases.

## 15. Testing query complexity with `ExecutionGraphQlServiceTester`

`ExecutionGraphQlServiceTester` is a variant of `GraphQlTester` that submits operations directly to `ExecutionGraphQlService` without setting up an HTTP client. This is well suited to verifying that the instrumentation blocks operations before resolvers run.

Example using the pagination configuration above, where the complexity limit is 500 and `first` is capped at 100 items:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.ExecutionGraphQlService;
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;

@SpringBootTest
class QueryComplexityTests {

    @Autowired
    ExecutionGraphQlService executionGraphQlService;

    @Test
    void rejectsOperationAboveComplexityLimit() {
        ExecutionGraphQlServiceTester tester =
            ExecutionGraphQlServiceTester.create(executionGraphQlService);

        tester.document("""
            query {
                books(first: 100) {
                    id
                    title
                    author {
                        name
                    }
                }
            }
            """)
            .execute()
            .errors()
            .satisfy(errors -> assertThat(errors).anySatisfy(error ->
                assertThat(error.getMessage())
                    .contains("maximum query complexity exceeded")
            ));
    }
}
```

With the calculator in the pagination section, the operation above has an estimated cost of 501 and exceeds the limit of 500. In real projects, check a stable error classification or extension code if the application standardizes errors; do not rely solely on default message text.

Beyond the response, verify that resolvers/services are never invoked when an operation is aborted. You can use a spy or counter on services in the test context to check this.

Test cases to include:

- Operations with complexity below the threshold execute.
- Operations with complexity equal to the threshold are accepted.
- Operations with complexity above the threshold are rejected.
- Deep queries exceeding the depth limit are rejected.
- List fields with small vs. large pagination yield different scores.
- Aliases calling the same field multiple times are counted separately.
- Fragments and inline fragments are analyzed accurately.
- Expensive fields push operations past the threshold.
- Pagination arguments exceeding the maximum are rejected by validation/service.
- Services do not run when instrumentation aborts the operation.

## 16. Monitoring and operating complexity limits

When rolling limits out to production, observe both accepted and rejected requests.

Record:

- Operation name or persisted document ID.
- Estimated complexity and the enforced limit.
- Query depth and field/alias count if measurable.
- Client/API key or permission group according to security policy.
- Count of aborted requests.
- Latency, database query counts, and response sizes of valid operations.

Do not log full queries or variables if they might contain sensitive information. In production, prefer operation names, hashes/persisted IDs, and sanitized metadata.

When the schema changes, update the cost model as well. A new field calling an external service or a new list field can significantly increase cost even when query depth stays unchanged.

Review frequently rejected operations to distinguish two situations: clients sending abnormal queries, or a complexity threshold set too low for legitimate use cases. Never raise the threshold just to clear a test or a single client error without checking actual cost.

## 17. Common issues when limiting query complexity

| Symptom | Possible cause | Solution |
| --- | --- | --- |
| Instrumentation does not work | `Instrumentation` bean not registered or custom `GraphQlSource` ignores beans | Check Boot auto-configuration and `GraphQlSource` |
| Large queries still execute | Threshold too high or cost model only counts basic fields | Tune weights and factor in pagination arguments |
| A 1,000-item list scores nearly the same as a 10-item list | Page size not included in calculator | Use `FieldComplexityCalculator` to scale by item count |
| Shallow query causes heavy load | Only depth limit enabled | Enable complexity, breadth/alias limits, and pagination |
| Deeply nested query still runs | Only complexity enabled with low field costs | Add `MaxQueryDepthInstrumentation` |
| Legitimate query is rejected | Threshold ignores valid use cases or field cost is inflated | Measure real operations and adjust the cost model |
| Resolver still loads too much data | Calculator caps score but service does not cap page size | Enforce page size in validation and service |
| DataLoader causes cost to be underestimated | Lowered cost due to fewer round trips | Score by item count and data volume, not only query count |
| Aliases call an expensive field repeatedly unblocked | Cost model or guardrails ignore aliases/breadth | Test aliases and add appropriate limits |
| Errors leak too many internal details | Default exception exposed to clients | Standardize GraphQL errors and log details on the server |

## 18. Query complexity limit implementation checklist

- [ ] Identify high-cost fields and list fields capable of returning large datasets.
- [ ] Design a complexity formula suited to the schema.
- [ ] Register `MaxQueryComplexityInstrumentation` in GraphQL execution.
- [ ] Use `FieldComplexityCalculator` when custom weights or pagination scaling are needed.
- [ ] Register `MaxQueryDepthInstrumentation` to limit deeply nested queries.
- [ ] Require pagination on list fields that can grow large.
- [ ] Enforce page size in validation or services, not only in the cost calculator.
- [ ] Test aliases, fragments, and high-cost fields.
- [ ] Add breadth, batch-operation, and rate limits where appropriate.
- [ ] Do not treat DataLoader as a replacement for complexity limits.
- [ ] Test operations below, at, and above the threshold.
- [ ] Verify resolvers do not run when an operation is aborted.
- [ ] Monitor complexity and rejected requests in production.
- [ ] Adjust thresholds as the schema or workload evolves.

## Conclusion

Query complexity limits help Spring for GraphQL control the amount of work clients can demand in a single operation. GraphQL Java provides `MaxQueryComplexityInstrumentation` to reject queries exceeding a threshold and `FieldComplexityCalculator` to assign costs by field, arguments, and item count. Spring Boot automatically detects `Instrumentation` beans and wires them into `GraphQlSource`.

An effective policy combines complexity with query depth, pagination, alias/breadth limits, rate limiting, and persisted documents. Scale list costs by page size, assign higher weights to fields calling expensive services, enforce data bounds in services, and test to confirm resolvers never run when queries are aborted. Monitor real workloads to keep the cost model and thresholds calibrated as the schema grows.

## References

- [Spring for GraphQL — Request Execution and GraphQlSource](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Boot — Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [GraphQL Java — Instrumentation](https://graphql-java.com/documentation/instrumentation/)
- [GraphQL Java — MaxQueryComplexityInstrumentation API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/MaxQueryComplexityInstrumentation.html)
- [GraphQL Java — MaxQueryDepthInstrumentation API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/MaxQueryDepthInstrumentation.html)
- [GraphQL Java — FieldComplexityCalculator API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/FieldComplexityCalculator.html)
- [GraphQL — Security and Demand Control](https://graphql.org/learn/security/)
- [Spring for GraphQL — Testing with GraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)
