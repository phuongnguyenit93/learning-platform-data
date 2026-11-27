# Query depth limit

In Spring for GraphQL, clients send operations matching the SDL schema and can combine Query, Mutation, and Subscription with nested fields. DataFetchers, annotated controllers, and DataLoaders collaborate to build the response. When a schema models multi-level relationships, a query depth limit is a performance guardrail that keeps operation structure within what the backend can handle.

## Objectives

After this lesson, you will be able to:

- Explain query depth and the relationship between depth and GraphQL execution cost.
- Calculate the depth of operations containing nested fields, fragments, and multiple branches.
- Distinguish deep queries from queries with high fan-out or expensive resolvers.
- Use MaxQueryDepthInstrumentation to enforce depth limits in Spring for GraphQL.
- Choose thresholds based on valid workloads and performance measurements.
- Combine depth limits with pagination, amount limits, query complexity, and DataLoader.
- Test boundaries and benchmark to evaluate the effectiveness of limits.
- Monitor rejected queries without creating high-cardinality metrics.

## 1. What is query depth?

GraphQL allows clients to select nested fields following the schema structure. An operation starts from a root type such as Query or Mutation, then traverses object fields to fetch related data.

Example:

~~~graphql
query BookDetails {
  bookById(id: "b-01") {
    id
    title
    author {
      name
      organization {
        name
      }
    }
  }
}
~~~

Query depth is the number of nested field levels along the deepest path of an operation. According to GraphQL Java's MaxQueryDepthInstrumentation counting rules, root fields start at depth 1 and each child field adds one level.

| Field on deepest path | Depth |
|---|---:|
| Query.bookById | 1 |
| Book.author | 2 |
| Author.organization | 3 |
| Organization.name | 4 |

The maximum depth of the operation above is 4. Other scalar fields such as Book.id and Book.title do not extend the deepest path because they have no child fields.

A depth limit sets a threshold on this nested structure. If an operation exceeds the threshold, the GraphQL runtime rejects the operation before running its DataFetchers.

## 2. Why does query depth affect performance?

GraphQL schemas often model relationships between objects. A Book has an Author, an Author has Books, a Book has Reviews, and a Review has an Author or Replies. Clients can traverse those relationships across many levels.

Example schema:

~~~graphql
type Query {
  bookById(id: ID!): Book
  books(first: Int = 20): [Book!]!
}

type Book {
  id: ID!
  author: Author
  reviews(first: Int = 10): [Review!]!
}

type Author {
  id: ID!
  books(first: Int = 10): [Book!]!
}

type Review {
  id: ID!
  author: Author
  replies(first: Int = 5): [Review!]!
}
~~~

A query can traverse Books, Author, Reviews, and Replies. Each level can trigger additional DataFetchers, service calls, database queries, or serialization.

As depth increases, the following can grow:

- The number of resolver layers to execute.
- The number of hops between services or repositories.
- The number of objects held in memory to build the response.
- The number of fields to serialize.
- The likelihood of queries traversing recursive schema relationships deeply.

A depth limit is a guardrail that caps the maximum nesting depth clients can request. It is useful when schemas contain recursive relationships or data branches that can expand across many levels.

However, depth only measures nested structure. It does not directly measure object count, database round trips, or individual resolver duration. To understand performance, you must also examine fan-out and field cost.

## 3. Depth does not equal query cost

Two queries with the same depth can have vastly different costs.

Query A:

~~~graphql
query {
  bookById(id: "b-01") {
    reviews(first: 50) {
      author {
        name
      }
    }
  }
}
~~~

Query B:

~~~graphql
query {
  books(first: 100) {
    reviews(first: 50) {
      author {
        name
      }
    }
  }
}
~~~

Both have a maximum nested field path of 4 levels from root. Query A only loads reviews for one Book; Query B can produce up to 100 Books and 5,000 Reviews if the server accepts those page sizes. The number of objects and resolver invocations can be much larger.

You can approximate the object count at each level as:

~~~text
N(next) = N(current) * fanOut(current)
~~~

Where N(current) is the number of objects at the current level, fanOut(current) is the average element count of the next list field, and N(next) is the number of objects at the next level.

For Query B:

- Root books(first: 100) produces up to 100 Books.
- Each Book has up to 50 Reviews.
- Total Reviews can reach 100 x 50 = 5,000.
- The author field may be resolved for thousands of Reviews.

Depth remains low, yet high fan-out causes cost to grow rapidly.

This is why a depth limit cannot replace amount limits or query complexity analysis.

## 4. Cost model across depth, fan-out, and resolvers

To analyze a query, you can use a mental model:

~~~text
W ~= sum(N[i] * C[i]), for i = 1..D
~~~

Where:

- D is the maximum depth.
- N[i] is how many times a field level is resolved.
- C[i] is the average resolver cost at that level.

This is an estimation model for comparing workloads, not an internal formula used by GraphQL Java.

A deep query can create many sequential processing layers. A shallow query with large lists can create massive parallel resolution. A single field calling a slow external API can dominate runtime even when the query depth is only 2.

| Query characteristic | Performance risk | Appropriate measure |
|---|---|---|
| Many nested object levels | Too many resolver layers | Depth limit |
| Lists with large page sizes | Too many objects | Amount limit, pagination |
| Many expensive fields | High total resolver cost | Query complexity |
| Related fields calling DB individually | N+1 database calls | DataLoader, @BatchMapping |
| Many aliases on the same field | Many execution branches | Field/alias limits, complexity |
| Slow downstream responses | Long-running requests | Timeout, bulkhead, caching |

When designing a policy, identify the type of cost you need to control before choosing a tool.

## 5. Calculating depth with nested fields

Suppose the schema is:

~~~graphql
type Query {
  order(id: ID!): Order
}

type Order {
  customer: Customer
  items: [OrderItem!]!
}

type Customer {
  profile: CustomerProfile
}

type CustomerProfile {
  address: Address
}

type Address {
  city: String!
}
~~~

Query:

~~~graphql
query {
  order(id: "o-01") {
    customer {
      profile {
        address {
          city
        }
      }
    }
    items {
      id
    }
  }
}
~~~

Deepest path:

| Field | Depth |
|---|---:|
| Query.order | 1 |
| Order.customer | 2 |
| Customer.profile | 3 |
| CustomerProfile.address | 4 |
| Address.city | 5 |

The items.id branch only has depth 3, so it does not determine the maximum depth. Depth limits always care about the deepest path in the operation.

When evaluating a real query, trace each branch from the root to its deepest field. Do not sum field counts across parallel branches into depth.

## 6. Fragments and inline fragments

Fragments let you reuse selection sets. A fragment does not add an extra field level merely due to fragment syntax; fields inside a fragment are counted at the position where the fragment is spread.

~~~graphql
fragment CustomerDetails on Customer {
  profile {
    address {
      city
    }
  }
}

query OrderDetails {
  order(id: "o-01") {
    customer {
      ...CustomerDetails
    }
  }
}
~~~

The deepest path is still:

1. Query.order: depth 1.
2. Order.customer: depth 2.
3. Customer.profile: depth 3.
4. CustomerProfile.address: depth 4.
5. Address.city: depth 5.

Inline fragments also do not add extra field levels:

~~~graphql
query {
  search {
    ... on Book {
      author {
        organization {
          name
        }
      }
    }
  }
}
~~~

Depth is calculated along the fields in the execution branch after applying fragments. Use the GraphQL AST and built-in instrumentation to analyze queries rather than manually counting braces or lines in the document.

## 7. Aliases add branches without increasing depth

Aliases rename a field's response key. An alias does not add a nesting level, so it does not increase depth on its own.

~~~graphql
query {
  first: bookById(id: "b-01") {
    author {
      name
    }
  }
  second: bookById(id: "b-02") {
    author {
      name
    }
  }
}
~~~

Both branches have the same depth. However, the server may have to resolve bookById twice with two different arguments.

A client can create many aliases:

~~~graphql
query {
  a: bookById(id: "b-01") { title }
  b: bookById(id: "b-02") { title }
  c: bookById(id: "b-03") { title }
  d: bookById(id: "b-04") { title }
}
~~~

Low depth does not imply few resolver invocations. If an endpoint accepts arbitrary documents, consider limiting total fields/aliases or query complexity alongside depth limits.

## 8. Recursive relationships in a schema

Some schemas have naturally recursive relationships:

~~~graphql
type Category {
  id: ID!
  name: String!
  parent: Category
  children(first: Int = 20): [Category!]!
}
~~~

The root query needs to expose the category list:

~~~graphql
type Query {
  categories: [Category!]!
}
~~~

Clients can request a deep category tree:

~~~graphql
query {
  categories {
    children {
      children {
        children {
          children {
            name
          }
        }
      }
    }
  }
}
~~~

Without a depth limit, a client can keep repeating the children field across many levels. Each level can expand object count according to the fan-out of the child list.

For recursive relationships, combine:

- Depth limits to cap the number of levels.
- Pagination or amount limits on each children list.
- Optimized resolvers so the database is not queried individually per node.
- DataLoader or batch queries when loading relationships.
- Request-level timeouts and resource limits.

A depth limit caps tree shape, but does not guarantee a tree has few nodes if each node has many children.

## 9. Configuring MaxQueryDepthInstrumentation in Spring for GraphQL

GraphQL Java provides MaxQueryDepthInstrumentation to limit operation depth. Spring Boot automatically integrates Instrumentation beans into the GraphQL runtime.

Example setting maximum depth to 6:

~~~java
import graphql.analysis.MaxQueryDepthInstrumentation;
import graphql.execution.instrumentation.Instrumentation;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class GraphQlPerformanceConfiguration {

    @Bean
    Instrumentation maxQueryDepthInstrumentation() {
        return new MaxQueryDepthInstrumentation(6);
    }
}
~~~

In this example:

- Queries with depth less than 6 pass the depth check.
- Queries with depth equal to 6 are still allowed.
- Queries with depth greater than 6 are rejected.

Spring Boot detects instrumentation beans when building the GraphQL runtime. If the application builds GraphQlSource manually, add the instrumentation to the builder alongside existing instrumentations.

Do not create duplicate instrumentations if Spring Boot auto-configuration already provides one. When the application has tracing or custom instrumentations, make sure they remain chained after adding the depth limit.

The threshold of 6 is only an example. Measure valid operations before choosing a production value.

## 10. Depth check runs before DataFetchers

Depth instrumentation analyzes the GraphQL operation before field resolvers execute. If a query exceeds the limit, GraphQL Java aborts the operation and does not invoke its DataFetchers.

Overall flow:

~~~mermaid
flowchart TD
    A[HTTP GraphQL request] --> B[Parse document]
    B --> C[Validate schema and variables]
    C --> D[Depth instrumentation]
    D -->|Within budget| E[Execute DataFetchers]
    D -->|Over budget| F[Abort execution]
    E --> G[GraphQL response]
    F --> G
~~~

The depth check avoids resolver execution cost for over-budget operations. Still, the server must receive the request, parse the document, and run validation steps before rejecting the operation.

Therefore, depth limits should be paired with request body size limits and rate limits. A huge document containing fields at only a single level may stay within the depth limit while still consuming CPU and memory during parsing and validation.

## 11. Choosing thresholds based on real workloads

No single depth value fits every GraphQL API. The threshold should reflect valid operations clients actually use and your backend's performance budget.

Process for selecting a threshold:

1. Collect operations from clients or a persisted query registry.
2. Compute the depth of each valid operation.
3. Identify the deepest operation with a real business need.
4. Measure duration, resolver counts, object counts, and database calls for those operations.
5. Choose a threshold covering valid operations with an appropriate safety margin.
6. Test operations just below, at, and above the threshold.
7. Monitor rejected query counts after deployment.

For example, if the deepest valid operation has depth 5, you might start testing a threshold of 6 or 7. Avoid picking an arbitrarily large number just to avoid impacting clients without measuring cost.

For APIs serving multiple clients, categorize operations by use case. An admin screen may need deeper queries than a public listing view. If they share the same schema and endpoint, the global depth limit must cover all supported use cases.

When the schema evolves, re-evaluate registered operations. Adding a new object relationship can make an existing operation deeper than expected.

## 12. Enforcing page size limits on every list field

Depth limits do not inspect page size to determine element count. Therefore, every list field that can produce many objects needs an amount cap.

Example resolver:

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

Apply similar limits to nested lists:

~~~graphql
type Book {
  reviews(first: Int = 10): [Review!]!
}
~~~

Do not cap only root lists. A query can fetch 20 Books and request 10,000 Reviews per Book if the resolver fails to validate the argument.

Place limits in the service/repository or a shared layer so every entry point complies. The GraphQL controller can validate input, but the service still needs to enforce data query policies.

For large datasets, prefer cursor pagination instead of returning unbounded lists.

## 13. When is query complexity needed instead of depth?

Depth limits only bound the number of nested field levels. When field costs vary significantly, query complexity analysis is required.

Examples:

- Book.title reads an in-memory property.
- Book.author calls an internal service.
- Book.recommendations calls an external recommendation engine.
- Book.reviews(first: 100) loads many records.

These fields have vastly different costs even at the same depth.

GraphQL Java provides MaxQueryComplexityInstrumentation with per-field complexity calculation. Applications can define a cost model so list fields scale with the `first` argument, or expensive fields carry higher weights.

A simple estimation model:

~~~text
C(field) = baseCost(field) + fanOut * sum(C(children))
~~~

This is an illustrative cost model formula, not GraphQL Java's default formula. Build calculators and weights based on actual workloads.

Use depth limits to block overly deep queries; use complexity to control the total estimated cost of selected fields.

## 14. DataLoader reduces backend calls, not depth

DataLoader and @BatchMapping batch related data loads together. They can reduce N+1 database calls, but they do not alter the structure of the GraphQL operation.

For example, a client queries 20 Books and Authors:

~~~graphql
query {
  books(first: 20) {
    id
    author {
      id
      name
    }
  }
}
~~~

If each Book calls the repository separately for Author, the server can make 20 database calls. Using DataLoader or @BatchMapping can group the author IDs into one batch.

However:

- The query still has the same depth.
- The server still has to build the response for 20 Books and Authors.
- Serialization still has to process every requested field.
- A deep query with many branches still needs a depth limit.
- A shallow query with a huge list still needs an amount limit.

Never treat DataLoader as a replacement for depth limits or pagination. It optimizes how data is loaded, not how much data clients request.

## 15. Testing depth boundaries

When enabling a depth limit, include tests for three cases:

| Case | Expected outcome |
|---|---|
| Depth below threshold | Operation executes |
| Depth equal to threshold | Operation executes |
| Depth above threshold | Operation is aborted |

Example with threshold 3 and a valid query:

The examples in this section assume a schema with Query.bookById, Book.author, Author.organization, and Organization.name.

~~~graphql
query {
  bookById(id: "b-01") {
    author {
      name
    }
  }
}
~~~

Maximum depth is 3, so the query is accepted.

Over-budget query:

~~~graphql
query {
  bookById(id: "b-01") {
    author {
      organization {
        name
      }
    }
  }
}
~~~

Maximum depth is 4, so the query is rejected.

Testing with GraphQlTester:

~~~java
@Test
void shouldRejectQueryBeyondDepthBudget() {
    graphQlTester.document("""
            query {
              bookById(id: "b-01") {
                author {
                  organization {
                    name
                  }
                }
              }
            }
            """)
            .execute()
            .errors()
            .satisfy(errors ->
                    assertThat(errors).isNotEmpty());

    verifyNoInteractions(bookService);
}
~~~

This test assumes bookService is a dependency called by the resolver to load Book. If depth instrumentation aborts before execution, the service is never invoked.

Besides boundary tests, test fragments, inline fragments, aliases, and multiple branches to verify that query depth is calculated accurately for the GraphQL document.

## 16. Benchmarking before and after enabling depth limits

A depth limit incurs AST analysis overhead, but rejects overly deep queries before resolvers run. Measure both instrumentation overhead and the benefit of blocking invalid workloads.

A benchmark can compare:

| Scenario | Depth | Fan-out | Purpose |
|---|---:|---:|---|
| Basic query | 2 | Low | Measure baseline |
| Relationship query | 5 | Low | Measure additional resolver cost |
| Deep query | 9 | Low | Verify depth rejection |
| Large list query | 3 | High | Prove depth does not cap amount |
| Multi-alias query | 2 | Many branches | Check DataFetcher invocation count |
| DataLoader query | 4 | Medium | Compare DB calls before/after batching |

Metrics to measure:

- Latency p50, p95, and p99.
- Throughput and request error rate.
- CPU and heap allocation.
- DataFetcher invocation count.
- Database query count.
- Objects created and response size.
- Parse, validation, and execution durations if tracing supports them.

Run benchmarks with identical datasets, page sizes, and concurrency. Changing multiple factors at once makes it hard to tell whether improvements came from depth limits, DataLoader, or database caching.

A depth limit is not a tool to speed up valid queries. Its primary goal is to block operations whose structure exceeds budget. To speed up valid operations, optimize resolvers, database queries, pagination, and batching.

## 17. Monitoring rejected queries

After deployment, you need to know whether depth limits are blocking valid operations.

Record:

- Count of operations rejected due to depth.
- Depth of rejected operations.
- Operation name or persisted query ID if available.
- Client/application sending the request, per security policy.
- Rejection rate over time.

Do not use full GraphQL documents, variables, or arbitrary field paths as metric tags. Those values can have extremely high cardinality or contain sensitive data.

Metrics should use keys with bounded value sets such as outcome, operation type, and error category. Specific depth values or operation identifiers can be recorded in access-controlled logs/traces.

If rejection rates spike suddenly after a client release, inspect the new operations and schema changes before raising global thresholds.

## 18. Common pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| Deep queries still execute | Instrumentation is not registered in the GraphQL runtime | Check bean and GraphQlSource configuration |
| Valid queries get rejected | Threshold is lower than actual client depth | Collect valid operations and calibrate |
| Shallow queries are still slow | High fan-out or expensive resolvers | Add amount/complexity limits and optimize resolvers |
| Many database calls | Resolvers load relationships individually | Use DataLoader or @BatchMapping |
| Aliases create heavy load at low depth | Depth does not count total branches | Limit aliases/fields and complexity |
| Large documents still burn CPU | Depth limit does not bound AST size | Cap HTTP body size and rate |
| Adding instrumentation breaks tracing | Overwrote existing instrumentations | Chain instrumentations instead of replacing |
| Over-budget test still calls service | Test does not run through instrumented runtime or asserts wrong dependency | Check test configuration and verified service |
| Raising threshold degrades p99 | Deeper queries are allowed to execute | Measure workload and evaluate complexity/fan-out |

## 19. Query depth limit deployment checklist

Before taking depth limits to production:

- [ ] Computed depth of valid operations.
- [ ] Determined threshold from workload rather than arbitrarily.
- [ ] MaxQueryDepthInstrumentation registered in the GraphQL runtime.
- [ ] Other instrumentations such as tracing/metrics still work.
- [ ] Tests cover queries just below, equal to, and above the threshold.
- [ ] Fragments and inline fragments are counted accurately.
- [ ] Queries with aliases and multiple branches are tested.
- [ ] DataFetchers do not execute when operations are aborted.
- [ ] Every list field has an amount limit.
- [ ] Pagination is implemented for large collections.
- [ ] Complexity limits cover fields with varying costs.
- [ ] DataLoader is used for relationships prone to N+1.
- [ ] HTTP request body size and rate are limited.
- [ ] Metrics/logs monitor rejected queries.
- [ ] No raw queries, variables, or arbitrary field paths are placed in metric tags.

## Conclusion

Query depth limits bound the number of nested field levels in a GraphQL operation. They are especially useful for schemas with recursive relationships or multi-level resolvers, rejecting over-budget queries before DataFetchers execute.

In Spring for GraphQL, you can use GraphQL Java's MaxQueryDepthInstrumentation and integrate it into the GraphQL runtime. Choose thresholds from valid operations and real performance measurements. Depth limits only control nesting depth; fan-out, page sizes, aliases, and resolver costs must be controlled with amount limits, pagination, query complexity, DataLoader, and complementary guardrails.

Evaluating effectiveness through boundary tests, benchmarks, and monitoring rejected queries helps sustain performance as schemas and clients evolve.

## References

- [Spring for GraphQL — Request Execution and GraphQlSource](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Boot — GraphQL Auto-configuration](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [GraphQL Java — MaxQueryDepthInstrumentation API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/MaxQueryDepthInstrumentation.html)
- [GraphQL Java — MaxQueryComplexityInstrumentation API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/analysis/MaxQueryComplexityInstrumentation.html)
- [OWASP — GraphQL Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/GraphQL_Cheat_Sheet.html)
