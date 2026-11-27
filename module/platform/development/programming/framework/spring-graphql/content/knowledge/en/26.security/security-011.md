# Limiting query depth

## Objectives

After this lesson, you will be able to:

- Explain query depth and why limiting the depth of GraphQL operations is necessary.
- Count the depth of a query with nested fields.
- Identify schemas with recursive relationships prone to deep queries.
- Configure `MaxQueryDepthInstrumentation` in Spring for GraphQL.
- Register the instrumentation with Spring Boot and understand where it participates in execution.
- Distinguish depth limits from pagination, amount limits, and query complexity.
- Understand the effect of fragments, aliases, and multiple operations on query evaluation.
- Test queries exceeding the threshold and verify that DataFetchers are not executed.
- Combine depth limits with other GraphQL protections.

## 1. What is query depth?

GraphQL lets clients select nested fields following the schema structure. A query can traverse from a root type down to an object type, and continue selecting child fields on that object.

Example:

~~~graphql
query {
  books {
    id
    title
    author {
      name
    }
  }
}
~~~

The deepest path in this query is:

`Query.books → Book.author → Author.name`

Query depth represents the number of nested field levels from the root operation to the deepest field. A common counting convention in GraphQL Java counts the root field at depth 1, with each child field adding one level.

For the query above:

| Field | Depth |
|---|---:|
| `Query.books` | 1 |
| `Book.author` | 2 |
| `Author.name` | 3 |

Sibling fields such as `Book.id` and `Book.title` do not increase the maximum depth of the query. Depth limits focus on the deepest nested path, not the total number of fields appearing in the document.

A shallow query can still be expensive if it requests thousands of records or repeats many fields using aliases. Therefore, depth is an important protective signal, though it does not represent the entire execution cost.

## 2. Why can overly deep queries pose a risk?

GraphQL schemas often describe bidirectional relationships or relationships that can cycle back to the starting type.

Example:

~~~graphql
type Query {
  books(first: Int = 20): [Book!]!
}

type Book {
  id: ID!
  author: Author
  relatedBooks(first: Int = 10): [Book!]!
}

type Author {
  id: ID!
  books(first: Int = 10): [Book!]!
}
~~~

A Book has an Author, and an Author has a list of Books. A Book can also link to other Books. This valid schema allows clients to repeat fields across many levels:

~~~graphql
query {
  books {
    author {
      books {
        author {
          books {
            author {
              id
            }
          }
        }
      }
    }
  }
}
~~~

If each resolver queries a database or calls an external service, a deep query can trigger many data loads, multiply the number of executed resolvers, and make processing time unpredictable.

Risk increases when combined with:

- Recursive or bidirectional relationships in the schema.
- List fields without item count limits.
- Expensive resolvers or calls to external services.
- Multiple levels of nested fields simultaneously triggering DataFetchers.
- Clients sending many aliases or many query branches.
- Missing timeouts, rate limits, and resource bounds.

Depth limits help block operations with excessive nesting before resolvers begin loading data.

## 3. Counting the depth of a GraphQL query

Suppose the schema has these types:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  author: Author
}

type Author {
  id: ID!
  organization: Organization
}

type Organization {
  id: ID!
  address: Address
}

type Address {
  city: String!
}
~~~

Query:

~~~graphql
query {
  book(id: "b-01") {
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

Depth is calculated along the path from the root:

| Field | Depth |
|---|---:|
| `Query.book` | 1 |
| `Book.author` | 2 |
| `Author.organization` | 3 |
| `Organization.address` | 4 |
| `Address.city` | 5 |

Therefore, the maximum depth of this query is 5 according to `MaxQueryDepthInstrumentation`'s counting.

Another query with multiple sibling fields:

~~~graphql
query {
  book(id: "b-01") {
    id
    author {
      id
      name
    }
  }
}
~~~

The maximum depth is 3:

- `Query.book`: depth 1.
- `Book.author`: depth 2.
- `Author.name`: depth 3.

Sibling `id` fields add no extra depth. The instrumentation evaluates the deepest path, rather than summing all fields into one number.

When choosing a threshold, use real client queries as a baseline. If the threshold is too low, legitimate screens with nested fields will be rejected. If too high, it may fail to stop abnormally structured queries.

## 4. MaxQueryDepthInstrumentation in GraphQL Java

GraphQL Java provides `MaxQueryDepthInstrumentation` to limit operation depth.

This class belongs to the package:

~~~java
graphql.analysis.MaxQueryDepthInstrumentation
~~~

The instrumentation analyzes the selected operation and computes field depths. If depth exceeds `maxDepth`, execution is aborted with `AbortExecutionException` before the operation's DataFetchers run.

Example creating the instrumentation with a threshold of 8:

~~~java
Instrumentation instrumentation =
        new MaxQueryDepthInstrumentation(8);
~~~

The constructor takes an integer representing the maximum allowed depth. A query whose depth equals the threshold is still accepted; a query with depth greater than the threshold is rejected.

The rule works as follows:

- Depth 7: allowed if maxDepth is 8.
- Depth 8: allowed.
- Depth 9: rejected.

The threshold in the example is purely illustrative. Applications should determine thresholds by measuring legitimate operations, schema complexity, and backend capacity.

## 5. Registering the instrumentation in Spring Boot

Spring Boot's auto-configuration for Spring for GraphQL detects beans of type `graphql.execution.instrumentation.Instrumentation` and wires them into the GraphQL runtime.

Thus, the simplest approach is declaring a bean:

~~~java
import graphql.analysis.MaxQueryDepthInstrumentation;
import graphql.execution.instrumentation.Instrumentation;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GraphQlSecurityConfiguration {

    @Bean
    Instrumentation maxQueryDepthInstrumentation() {
        return new MaxQueryDepthInstrumentation(8);
    }
}
~~~

When the application starts:

1. Spring Boot detects the `Instrumentation` bean.
2. `GraphQlSource` is configured with that instrumentation.
3. When GraphQL receives an operation, the instrumentation analyzes query depth.
4. If depth exceeds the limit, the operation is aborted before calling resolvers.
5. If depth is within bounds, GraphQL proceeds with normal execution.

There is no need to write a custom HTTP filter to count braces or parse raw query strings. The instrumentation operates on the GraphQL document already parsed by GraphQL Java with schema awareness of field relationships.

### When the application configures GraphQlSource manually

If the application builds `GraphQlSource` directly instead of using Spring Boot auto-configuration, register the instrumentation on the builder:

~~~java
GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
        .schemaResources(schemaResources)
        .configureRuntimeWiring(runtimeWiringConfigurer)
        .instrumentation(new MaxQueryDepthInstrumentation(8))
        .build();
~~~

The example above illustrates the integration point; resources and runtime wiring are supplied according to your application configuration.

If you already have instrumentation for metrics, tracing, or other features, combine them using GraphQL Java's chaining mechanism, such as `ChainedInstrumentation`. Avoid replacing existing instrumentation without checking, as doing so can drop metrics or tracing.

With Spring Boot auto-configuration, prefer declaring `Instrumentation` beans and letting Boot integrate them. If a custom `GraphQlSource` is necessary, take responsibility for combining all active instrumentations.

## 6. At which stage does the instrumentation run?

Query depth must be checked before DataFetchers execute so an operation exceeding the limit cannot trigger data loading.

In broad terms, a GraphQL request goes through these stages:

~~~mermaid
flowchart TD
    A[HTTP GraphQL request] --> B[Parse document]
    B --> C[Validate against schema]
    C --> D[Coerce variables and select operation]
    D --> E[MaxQueryDepthInstrumentation]
    E -->|Within limit| F[Execute fields and DataFetchers]
    E -->|Exceeds limit| G[Abort operation and create errors]
    F --> H[GraphQL response]
    G --> H
~~~

The instrumentation evaluates the document and the selected operation. If depth exceeds the threshold, GraphQL Java aborts the operation before running resolvers.

This matters for security: a query rejected for being too deep should not generate database queries from fields inside that operation.

However, parsing and validation still consume resources. Depth limits do not replace request body size limits, parse/validation timeouts, rate limiting, or HTTP-layer protections.

## 7. Effect of fragments and inline fragments

GraphQL allows reusing selection sets via fragments.

Example:

~~~graphql
fragment AuthorDetails on Author {
  id
  organization {
    id
    address {
      city
    }
  }
}

query {
  book(id: "b-01") {
    author {
      ...AuthorDetails
    }
  }
}
~~~

A fragment is not a field level in the schema. Fields inside the fragment are still counted according to the position where the fragment is spread in the query.

Deepest path:

- `Query.book`: depth 1.
- `Book.author`: depth 2.
- `Author.organization`: depth 3.
- `Organization.address`: depth 4.
- `Address.city`: depth 5.

Inline fragments also do not add an extra field level merely for using fragment syntax:

~~~graphql
query {
  search {
    ... on Book {
      author {
        organization {
          id
        }
      }
    }
  }
}
~~~

Depth is calculated according to the actual field selections along the query branch. Never write a naive string-based counter because it easily miscounts fragments, inline fragments, aliases, and other GraphQL syntax.

## 8. Aliases and multiple query branches

Aliases let clients request the same field multiple times with different arguments:

~~~graphql
query {
  firstBook: book(id: "b-01") {
    author {
      name
    }
  }

  secondBook: book(id: "b-02") {
    author {
      name
    }
  }
}
~~~

Both branches have the same maximum depth. Aliases do not by themselves increase depth because they only change response keys.

However, aliases can increase the number of executed fields. If a client creates hundreds of aliases with different arguments, a pure depth limit may still permit that query.

Example:

~~~graphql
query {
  a: book(id: "b-01") { title }
  b: book(id: "b-02") { title }
  c: book(id: "b-03") { title }
}
~~~

The depth is low, yet there are many root field branches. Therefore, combine depth limits with query complexity, alias/field limits if needed, rate limiting, and data query controls.

## 9. Depth limits do not cap item counts

A shallow query can still request a massive number of items:

~~~graphql
query {
  books(first: 100000) {
    id
    title
  }
}
~~~

This query's depth is low, yet the server might have to load and serialize a huge amount of data if the resolver accepts that argument.

Depth limits do not interpret the business meaning of the `first` argument to cap item counts. Dedicated amount limits or pagination are required.

Example resolver enforcing a limit:

~~~java
@QueryMapping
public List<Book> books(@Argument Integer first) {
    int pageSize = first == null ? 20 : first;

    if (pageSize < 1 || pageSize > 100) {
        throw new IllegalArgumentException(
                "first must be between 1 and 100");
    }

    return bookService.findFirst(pageSize);
}
~~~

Enforce the limit in the service or data access layer as well if the same service is called from multiple entry points. Do not rely solely on validation in the GraphQL controller.

For large lists, prefer cursor pagination or connection types so clients load data page by page.

## 10. Distinguishing depth, complexity, and amount limits

These measures address different kinds of cost:

| Measure | Controls | Example risk |
|---|---|---|
| Query depth limit | Number of nested field levels | Recursive relationships producing very deep queries |
| Query complexity limit | Estimated cost of fields | Many fields or expensive resolvers |
| Amount limit | Number of items loaded per list field | `first: 100000` |
| Alias/field limit | Number of branches or fields in an operation | Hundreds of root field aliases |
| Timeout | Maximum processing time | Slow resolvers or downstream services |
| Rate limit | Number of requests over a time window | A client sending too many operations |

GraphQL Java also provides `MaxQueryComplexityInstrumentation`. It can calculate complexity based on fields and a custom `FieldComplexityCalculator`.

Conceptual example of declaring complexity instrumentation:

~~~java
Instrumentation complexityInstrumentation =
        new MaxQueryComplexityInstrumentation(500);
~~~

Complexity thresholds should be designed around the application's cost model. If a list field has a `first` argument, the calculator should factor in the requested item count; otherwise, a field loading 1 item and a field loading 1,000 items might be scored too similarly.

Do not use a single depth number to replace complexity or amount limits. These measures should work together to control both query structure and actual workload.

## 11. How should the depth threshold be chosen?

There is no single right threshold for every GraphQL API. The appropriate value depends on the schema, how clients use the API, and resolver cost.

Threshold selection process:

1. Collect legitimate operations from clients or a persisted query registry.
2. Measure the maximum depth of real-world operations.
3. Identify which deep operations remain necessary for business needs.
4. Choose a threshold reasonably above legitimate use cases.
5. Test queries just below, at, and above the threshold.
6. Monitor rejected requests and adjust as the schema evolves.

For example, if supported operations have depths from 2 to 6, a threshold of 8 may be a starting point for testing. This is not a fixed recommendation; measure your actual backend and workload.

Use logs or metrics to monitor:

- Number of operations aborted due to depth.
- Depth of rejected operations.
- Operation name or persisted query ID.
- Principal/client that sent the operation, per security logging policy.
- Parse, validation, and execution durations.

Do not log entire query variables if they might contain sensitive data. When recording operations, consider using operation names or persisted query hashes.

## 12. Handling queries that exceed the limit

`MaxQueryDepthInstrumentation` aborts the operation by default when depth exceeds the limit. GraphQL Java generates an execution error from `AbortExecutionException`.

An example default message looks like:

~~~text
maximum query depth exceeded 9 > 8
~~~

The GraphQL response may contain errors without normal execution data, because the operation is stopped before field resolvers run.

Clients should receive a recognizable error so they can adjust their queries. In production, you do not necessarily need to disclose internal details or the full threshold if security policy requires limiting information disclosure.

If you want to customize behavior when the limit is exceeded, `MaxQueryDepthInstrumentation` has a constructor accepting an additional `QueryDepthInfo -> Boolean` function. This function decides whether to throw the abort exception. When a specific response contract is required, test how the exception translates into a GraphQL error in the exact versions of GraphQL Java and Spring for GraphQL in use.

Never return fake data or silently drop deep fields to make the query appear successful. Queries violating policy must be explicitly rejected.

## 13. Testing depth limits in Spring for GraphQL

Test through the GraphQL runtime to confirm the instrumentation is registered and actually prevents resolvers from running.

Example configuration:

~~~java
@Configuration
class GraphQlSecurityConfiguration {

    @Bean
    Instrumentation maxQueryDepthInstrumentation() {
        return new MaxQueryDepthInstrumentation(3);
    }
}
~~~

Suppose the schema is:

~~~graphql
type Query {
  books: [Book!]!
}

type Book {
  author: Author
}

type Author {
  books: [Book!]!
}
~~~

Query exceeding the limit:

~~~graphql
query {
  books {
    author {
      books {
        author {
          books
        }
      }
    }
  }
}
~~~

The deepest path exceeds 3, so the operation must be rejected before resolvers load data.

Example test:

~~~java
@Test
void shouldRejectQueryWhenDepthExceedsLimit() {
    graphQlTester.document("""
            query {
              books {
                author {
                  books {
                    author {
                      books {
                        id
                      }
                    }
                  }
                }
              }
            }
            """)
            .execute()
            .errors()
            .satisfy(errors -> {
                assertThat(errors).isNotEmpty();
                assertThat(errors.get(0).getMessage())
                        .contains("maximum query depth exceeded");
            });

    verifyNoInteractions(bookService);
}
~~~

This test assumes the instrumentation is registered in the test application context and the resolver uses `bookService`. It is important to verify both the GraphQL error and that the service is never called.

Additional tests to include:

1. A query with depth below the threshold executes.
2. A query with depth equal to the threshold is accepted.
3. A query with depth above the threshold is rejected.
4. Queries using fragments still have depth calculated accurately.
5. Queries using inline fragments are not miscounted by level.
6. Queries with aliases do not skew depth calculations.
7. A document with multiple operations evaluates only the selected operation.
8. Resolvers are not called when depth limit aborts.
9. Other instrumentations such as metrics/tracing still work after adding the depth limit.
10. HTTP responses follow an error contract clients can handle.

## 14. Common issues

| Symptom | Possible cause | Solution |
|---|---|---|
| Deep queries still run | Instrumentation is not registered with the GraphQL runtime | Check the `Instrumentation` bean or `GraphQlSource` builder |
| All queries are rejected | Threshold is too low or depth counting was not verified | Write tests for depths 1, threshold, and threshold + 1 |
| Adding instrumentation drops tracing | Replaced existing instrumentation | Combine via `ChainedInstrumentation` or Boot auto-configuration |
| Queries with many aliases still exhaust resources | Depth does not measure total field/branch count | Add complexity and alias/field limits |
| Shallow queries still load too much data | List arguments are uncapped | Add amount limits and pagination |
| Queries with fragments are mis-evaluated | Custom string-based syntax counting | Use `MaxQueryDepthInstrumentation` on the GraphQL document |
| Resolvers still run when query is rejected | Test did not run through a GraphQL runtime with instrumentation or verified the wrong service | Verify the application context and service mocks |
| Clients receive internal messages | Abort exception returned verbatim | Standardize error responses per application policy |

## 15. Implementation checklist

Before enabling query depth limits in production:

- [ ] `MaxQueryDepthInstrumentation` is present in the GraphQL runtime.
- [ ] The threshold is chosen from legitimate operations and real backend capacity.
- [ ] Counting conventions for root fields and nested fields are tested.
- [ ] Fragments and inline fragments are counted accurately.
- [ ] Queries just below, equal to, and above the threshold have tests.
- [ ] Queries exceeding the threshold abort before DataFetchers run.
- [ ] Existing metrics/tracing instrumentations continue working.
- [ ] Amount limits exist for list fields and pagination.
- [ ] Query complexity limits exist for expensive fields.
- [ ] Timeouts and rate limits are configured at appropriate layers.
- [ ] Error responses do not leak internal details.
- [ ] Rejected operations are monitored and thresholds adjusted as the schema changes.

## Conclusion

Query depth is the number of nested field levels along the deepest path of a GraphQL operation. Schemas with recursive relationships can allow clients to craft very deep queries, triggering many resolvers and data sources.

Spring for GraphQL can use GraphQL Java's `MaxQueryDepthInstrumentation` to reject operations exceeding a threshold. In Spring Boot, registering the instrumentation as a bean is a straightforward integration. Depth limits must be combined with complexity limits, amount limits, pagination, timeouts, and rate limiting because a shallow query can still consume substantial resources.

Choose thresholds based on legitimate operations, test fragments/aliases, and verify resolvers do not run when a query is aborted. That turns depth limiting into a measurable safeguard that can be maintained as the schema evolves.

## References

- [Spring for GraphQL — Request Execution and GraphQlSource](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Boot — GraphQL Auto-configuration](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [GraphQL Java — MaxQueryDepthInstrumentation API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/MaxQueryDepthInstrumentation.html)
- [GraphQL Java — Query Complexity Instrumentation](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/MaxQueryComplexityInstrumentation.html)
- [OWASP — GraphQL Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/GraphQL_Cheat_Sheet.html)
