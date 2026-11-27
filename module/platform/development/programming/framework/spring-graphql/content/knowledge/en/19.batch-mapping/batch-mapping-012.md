# Measuring N+1 mitigation effectiveness

Batch mapping and DataLoader help reduce data access calls when GraphQL resolves relational fields. However, merely adding `@BatchMapping` is not enough to conclude the N+1 problem has been solved. You must measure batch method call counts, SQL statement counts, keys per batch, and processing time on the exact same operation before and after the change.

The goal of measurement is to confirm three things: query count no longer scales linearly with the number of parent objects, results still match the right objects, and actual latency improves under representative load. This lesson focuses on how to verify this in Spring for GraphQL, particularly with `@BatchMapping`, DataLoader, and JPA.

## How does N+1 manifest?

Suppose the API returns a list of books, and each book has an author:

```graphql
type Query {
  books(first: Int = 20): [Book!]!
}

type Book {
  id: ID!
  title: String!
  author: Author
}

type Author {
  id: ID!
  name: String!
}
```

The client fetches the list along with authors:

```graphql
query BooksWithAuthors {
  books(first: 20) {
    id
    title
    author {
      id
      name
    }
  }
}
```

A regular resolver may call the repository for each book:

```java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorRepository.findById(book.getAuthorId()).orElse(null);
}
```

With 20 books, the system may run one query to fetch books plus 20 queries to fetch authors, totaling 21 SQL statements. When the number of books grows from 20 to 100, the number of relational queries also grows from 20 to 100. This is the classic signature of N+1.

## After switching to `@BatchMapping`

`@BatchMapping` allows Spring for GraphQL to group source objects of the same field into a single batch method invocation. Example:

```java
@Controller
public class BookController {

    private final AuthorService authorService;

    public BookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        List<Long> authorIds = books.stream()
                .map(Book::getAuthorId)
                .distinct()
                .toList();

        Map<Long, Author> authorsById = authorService.findAllByIds(authorIds);

        return books.stream()
                .filter(book -> authorsById.containsKey(book.getAuthorId()))
                .collect(Collectors.toMap(
                        Function.identity(),
                        book -> authorsById.get(book.getAuthorId())));
    }
}
```

The batch method receives the list of `Book`s, extracts unique `authorId`s, loads authors in bulk, and returns a map from each `Book` to its corresponding `Author`. In this example, the map key is the source object and the value is the data for the `author` field.

With 20 books whose author IDs fit within a single batch limit, you expect one query to fetch books and one query to fetch authors—roughly 2 SQL statements instead of 21. If the list is large or split into multiple batches, the number of relational queries can be greater than one.

Do not register both `@SchemaMapping` and `@BatchMapping` for the same field in a real example. When measuring before/after, keep only one mapping active at a time so comparison results stay clear.

## Expected query counts by list size

To observe the trend, run the same GraphQL operation with different numbers of books. Suppose each book has a distinct author and all IDs fit within the batch limit:

| Number of books (N) | Per-book resolver | Single batch for relation |
| ---: | ---: | ---: |
| 1 | 2 SQL | 2 SQL |
| 10 | 11 SQL | 2 SQL |
| 20 | 21 SQL | 2 SQL |
| 50 | 51 SQL | 2 SQL |
| 100 | 101 SQL | 2 SQL if still within one batch |

This is an illustrative model, not a fixed guarantee for SQL counts across every application. Actual results also depend on unique key count, batch size, nested field depth, fetch strategy, caching, and how repositories execute queries.

If batch size is capped at 50 keys, 100 unique author IDs may require two relational loads. Expected total SQL would then be one book query plus two batch queries. What matters is that query count scales with the number of batches rather than with each parent object.

## Which metrics should you measure?

Do not measure response time alone. A fast response on a small dataset can still hide N+1; conversely, fewer SQL statements with an overly heavy batch query can still make responses slow.

| Metric | What it reveals | Where to observe |
| --- | --- | --- |
| Batch method invocation count | Whether batch mapping groups multiple source objects into the same call. | Counter inside `@BatchMapping` or spy in tests. |
| Keys per batch | Size of the data group being loaded. | Distribution summary or histogram. |
| SQL/JDBC statement count | Whether N+1 decreased at the persistence layer. | Hibernate Statistics or datasource instrumentation. |
| Batch service duration | How long querying relational data takes. | Timer around the batch service. |
| Total GraphQL request duration | How long the client actually waits for the operation. | HTTP server metrics, tracing, or test timer. |
| Rows read and returned data size | Whether the batch loads too much data. | Database metrics, query plans, and query logs. |
| p50, p95, p99 latency | How the system behaves at varying load levels. | Load tests and observability. |
| Cache hit/miss and duplicate keys | Whether DataLoader avoids redundant loads within a request. | DataLoader instrumentation or custom metrics. |
| Connection pool wait/active | Whether queries cause database pool saturation. | HikariCP metrics or datasource metrics. |

Counting SQL statements detects N+1; measuring duration, row counts, and pool usage evaluates real cost. Look at these metrics together.

## Counting batch method invocations

With `@BatchMapping`, a simple technique is recording every time the batch method runs and how many source objects were in the batch. Micrometer provides `Counter`, `DistributionSummary`, and `Timer` for this purpose.

Illustrative example with a synchronous batch method:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

@Controller
public class BookController {

    private final AuthorService authorService;
    private final Counter batchCalls;
    private final DistributionSummary batchSize;
    private final Timer batchDuration;

    public BookController(AuthorService authorService, MeterRegistry registry) {
        this.authorService = authorService;
        this.batchCalls = Counter.builder("graphql.batch.invocations")
                .tag("loader", "book-author")
                .register(registry);
        this.batchSize = DistributionSummary.builder("graphql.batch.unique_keys")
                .tag("loader", "book-author")
                .register(registry);
        this.batchDuration = Timer.builder("graphql.batch.duration")
                .tag("loader", "book-author")
                .register(registry);
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(List<Book> books) {
        batchCalls.increment();
        List<Long> authorIds = books.stream()
                .map(Book::getAuthorId)
                .distinct()
                .toList();
        batchSize.record(authorIds.size());

        return batchDuration.record(() -> {
            Map<Long, Author> authorsById = authorService.findAllByIds(authorIds);
            return books.stream()
                    .filter(book -> authorsById.containsKey(book.getAuthorId()))
                    .collect(Collectors.toMap(
                            Function.identity(),
                            book -> authorsById.get(book.getAuthorId())));
        });
    }
}
```

`graphql.batch.invocations` counts how many times the batch method runs; `graphql.batch.unique_keys` records the number of unique author IDs in each batch; `graphql.batch.duration` measures batch service processing time. Metric names and tags in the example are application-defined.

For methods returning `CompletableFuture`, `Mono`, or `Flux`, do not stop the timer immediately when the method returns the publisher/future, as work may not be complete yet. Stop the timer when the future completes or the publisher terminates, and also record error and cancellation cases if appropriate.

Do not attach high-cardinality tags such as `bookId`, `authorId`, email, arbitrary tenant, or full GraphQL queries. Use low-cardinality tags like loader name, GraphQL operation type, or controlled operation name. High cardinality increases memory and metrics system overhead.

**Note:** the number of times field resolution is requested still relates to the number of parent objects. What you want to reduce is the number of batch method calls and data access calls. Do not conclude batching failed just because GraphQL still resolves the `author` field for each `Book`.

## Counting SQL with Hibernate Statistics

For applications using Hibernate/JPA, you can enable statistics in test configuration:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        generate_statistics: true
```

In tests, obtain `Statistics` from `SessionFactory`, clear metrics before the operation, and read the prepared statement count after GraphQL completes:

```java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.Test;

class BookGraphQlIntegrationTests {

    private final GraphQlTester graphQlTester;
    private final Statistics statistics;

    BookGraphQlIntegrationTests(
            GraphQlTester graphQlTester,
            EntityManagerFactory entityManagerFactory) {
        this.graphQlTester = graphQlTester;
        this.statistics = entityManagerFactory
                .unwrap(SessionFactory.class)
                .getStatistics();
    }

    @Test
    void booksAndAuthorsUseBoundedNumberOfStatements() {
        statistics.clear();

        graphQlTester.document("""
            query {
              books(first: 20) {
                id
                title
                author {
                  id
                  name
                }
              }
            }
            """)
            .execute()
            .errors()
            .verify();

        long preparedStatements = statistics.getPrepareStatementCount();
        assertThat(preparedStatements).isLessThanOrEqualTo(2L);
    }
}
```

The threshold `2` only makes sense for a simple fixture and configuration: one query for books, one query for authors, and no secondary queries. In real projects, determine baselines and thresholds based on the SQL actually needed rather than copying this number blindly.

`getPrepareStatementCount()` counts prepared statements prepared by Hibernate within the `SessionFactory` scope; it is useful for comparison but is not a perfect per-request GraphQL counter. Statistics have a broader scope than a single request and can be affected by other tests running concurrently. Isolate tests, avoid parallel execution, or use a datasource proxy/instrumentation to measure statements per request.

In addition to prepared statement counts, Hibernate Statistics provides metrics for entity fetches, collection fetches, and query executions. Pick the right metric for the question being asked; do not treat `queryExecutionCount` as the total count of all SQL statements.

## Measuring SQL at the datasource layer

When you need an exact count of JDBC commands during an operation, use a datasource proxy or equivalent JDBC observability tool. Such tools wrap `DataSource` to record executed statements, execution durations, and errors.

Advantages over reading only Hibernate Statistics:

- Can observe SQL issued by multiple JDBC libraries, not only ORM queries tracked by Hibernate.
- Can collect execution counts and statement durations at the datasource layer.
- Can attach measurement data to a request or test context when configured with appropriate instrumentation.

Do not enable full logging of bind parameters in production if parameters may contain personal or confidential data. In production environments, favor aggregated metrics, controlled tracing, and sampling; keep detailed SQL logs in protected test or debug environments.

## Comparing before and after fairly

For measurements to be meaningful, hold conditions constant between runs:

1. **Same GraphQL operation:** select the exact same fields and arguments. If the post-batching query fetches fewer fields, a drop in SQL count does not prove batching is effective.
2. **Same data:** use the same number of books, unique authors, duplicate ID ratio, and relationship sizes.
3. **Same cache state:** distinguish cold cache from warm cache. JPA persistence contexts, second-level caches, query caches, and application caches can mask N+1.
4. **Same pagination:** keep `first`, filters, and sorting identical to compare the same workload.
5. **Same environment:** use the same database, indexes, connection pool, JVM settings, and network.
6. **Repeat multiple times:** run a warm-up first, then collect multiple samples instead of concluding from a single run.
7. **Separate timings:** distinguish total GraphQL duration, batch service duration, and SQL duration. They cover different parts of the cost.

When measuring cold cache, create a fresh request and make sure the persistence context is not accidentally reused. When measuring warm cache, state explicitly which caches are enabled. Never mix both modes in the same statistic.

## Verifying the scaling trend with N

A practical way to detect N+1 is to vary the number of parent objects in the same kind of operation. Run levels such as 1, 10, 25, 50, and 100 books, then plot SQL count against N.

With a per-book resolver, query count usually follows roughly `1 + N` (one parent query and N child queries). With batching, query count usually follows roughly `1 + batch count`, where batch count depends on unique keys, batch size, and dispatch rounds.

```text
Number of books (N):       1    10    20    50    100
Per-book resolver:         2    11    21    51    101 SQL
Single batch:              2     2     2     2      2 SQL
```

This example only illustrates the case where all keys can be loaded in one batch with no extra queries. When batch size is 50, batching SQL count will grow with the number of key groups rather than staying flat at 2.

Do not look at only a single point like N=10. A resolver might happen to run two queries for N=10 due to caching, only to expose N+1 as N increases or key ratios change. The trend across N is more reliable than any single number.

## Measuring timing and performance under load

Reducing SQL count does not always guarantee faster responses. A single batch SQL query might join too many tables, return too many columns, or scan too many rows. Therefore, after verifying query counts, measure:

- Batch SQL execution time and database query plans.
- Total GraphQL operation duration, including resolvers, serialization, and response transfer.
- p50, p95, p99 latency under low load and concurrent load.
- Throughput, timeout errors, and rejected request count.
- Active connections, connection wait time, and executor queue depth.
- Response size, rows scanned, and memory consumption.

Run load tests with data volumes and distributions resembling production. Increase concurrency stepwise to find where the database or connection pool begins to saturate. Test both the case where many objects share a foreign key and the case where all keys are distinct, since DataLoader caching behaves differently in each.

## Distinguishing batching from other optimizations

N+1 can be addressed with several strategies. `@BatchMapping` and DataLoader are not the only options:

| Strategy | When it fits | What to check |
| --- | --- | --- |
| `@BatchMapping` | Need to load a relational field for a group of source objects. | Batch count, key count, result order/map, and nullability. |
| Explicit DataLoader | Need batching, key caching, or reusable loader logic. | Request scope, cache invalidation, and dispatch. |
| JPA fetch join / EntityGraph | Relationships can be loaded efficiently with the parent query. | Whether joins duplicate rows, pagination behavior, and payload volume. |
| Projection/DTO query | Only a specific set of fields is needed for a use case. | Query structure, flexibility, and reuse. |
| Application cache | Data rarely changes and can be cached safely. | TTL, invalidation, access permissions, and tenant isolation. |

Fetch joins can reduce SQL count, yet joining multiple collections can create Cartesian products, duplicate rows, or break pagination. DataLoader can be used for relationships needing separate loading. Measure query plans and actual responses to pick the right strategy.

## Misleading measurement results

- **Measuring only latency:** warm caches or a fast database can mask N+1. Count SQL statements and vary N to check the trend.
- **Measuring only resolver invocations:** GraphQL still resolves the field on each object; count batch method invocations and SQL statements instead of expecting the field resolver to disappear.
- **Measuring only one small request:** batching benefits may not show at small N. Increase N and use representative data.
- **Sharing caches across tests:** caching makes subsequent queries appear faster or use fewer SQL statements. Isolate requests and document cache state.
- **Ignoring secondary queries:** lazy loading from serializers, logging, or other service code can trigger SQL outside the batch method.
- **Comparing different operations:** differing fields, filters, or pagination make results non-comparable.
- **Ignoring errors and timeouts:** a fast-failing batch can make latency look low even though the operation failed.

## Project verification checklist

- Choose a GraphQL operation with a relationship causing N+1 and save a fixed document/variables pair.
- Create fixtures with known parent object counts and unique foreign key counts.
- Measure baseline SQL count, batch invocations, latency, and connection pool metrics.
- Switch the field resolver to `@BatchMapping` or DataLoader.
- Re-run the exact same operation with the same data.
- Verify the batch method receives multiple source objects per call.
- Verify results match the right source objects, even when the database returns a different order.
- Test missing keys, nullability, batch errors, and duplicate keys.
- Increase N to confirm SQL count scales with batch count rather than parent count.
- Run load tests and inspect p95/p99, DB time, throughput, and pool saturation.
- Confirm no caching or parallel tests skew the measurements.

## Takeaways

Measuring N+1 mitigation effectiveness requires combining batch method invocation counts, keys per batch, SQL/JDBC statement counts, and execution duration. With per-object resolvers, SQL count typically scales near `1 + N`; with batching, relational SQL count scales with the number of batches of unique keys. Exact numbers depend on batch size, dispatch, caching, and query structure.

In Spring for GraphQL, you can instrument `@BatchMapping` with Micrometer, count SQL statements via Hibernate Statistics or a datasource proxy, and use `GraphQlTester` to test the same operation before and after changes. Once query reduction is confirmed, continue measuring latency, query plans, rows scanned, connection pools, and p95/p99 under representative load. A solution is effective only when it reduces redundant queries while preserving accurate data and improving real-world cost.
