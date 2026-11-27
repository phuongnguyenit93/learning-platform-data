# Measuring DataLoader Observations

DataLoader batches multiple relationship data loads together, yet looking solely at `load()` calls or GraphQL query counts is not enough to know whether batching is truly effective. You need to measure how many batches are dispatched, processing duration, success/failure outcomes, and the size of loaded data.

Spring for GraphQL integrates Micrometer Observation to observe GraphQL requests, `DataFetcher`s, and `DataLoader`s. Since Spring for GraphQL 1.4.0, instrumentation adds an observation named `graphql.dataloader`. This observation covers `@BatchMapping` invocations as well as manually registered `DataLoader`s. This hands-on practice sets up a Book–Author relationship, sends a query fetching multiple books along with their authors, and inspects metrics and traces to confirm batch loading is working.

## 1. Measurement Goals

Suppose a client fetches 10 books and requests author details for each one. If every `Book.author` field calls the repository individually, the server may execute:

- One query to fetch the book list.
- Ten queries to fetch each author individually.

This is the N+1 select problem. DataLoader defers `load(authorId)` calls within the same GraphQL execution, collects the keys, and invokes the batch loader once or in multiple batches depending on limits.

After this hands-on practice, you should be able to answer:

1. Which DataLoader is being invoked?
2. How many batch observations does each GraphQL request produce?
3. How long does a batch take?
4. Did the batch succeed or fail?
5. How many items did the batch return?
6. In a trace, where does the batch observation sit inside the GraphQL request?
7. Does observation data prove the database only ran one SQL statement?

The final question is critical: the observation measures the execution of the batch loader. If the code inside the batch loader still loops and calls the repository key by key, a trace can still show a single batch observation while the database runs N SQL queries. Always cross-check with SQL logs or database metrics.

## 2. Version Requirements

DataLoader observations were added in Spring for GraphQL `1.4.0`. Therefore, use Spring for GraphQL 1.4 or later. With Spring Boot, pick a compatible dependency management line, such as Spring Boot 3.5+ or Spring Boot 4.x.

In Spring for GraphQL versions prior to 1.4, `graphql.request` and `graphql.datafetcher` may already exist, but the dedicated `graphql.dataloader` observation does not. If this metric does not appear, check library versions before writing custom instrumentation.

Spring Boot auto-configures `ObservationRegistry` and `GraphQlObservationInstrumentation` when observability infrastructure and an `ObservationRegistry` are present on the classpath. The GraphQL Boot starter detects `Instrumentation` beans and registers them with the GraphQL runtime. In a standard Spring Boot application, do not manually create a second instrumentation bean.

## 3. Adding Micrometer and Actuator Dependencies

Use Spring Boot dependency management to select compatible versions:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    runtimeOnly("io.micrometer:micrometer-registry-prometheus")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.graphql:spring-graphql-test")
}
~~~

Role of each dependency:

- `spring-boot-starter-graphql` provides the GraphQL server and integration with GraphQL Java.
- `spring-boot-starter-actuator` provides Micrometer Observation infrastructure and endpoints to inspect metrics.
- `micrometer-registry-prometheus` exports meters in Prometheus format.
- `spring-graphql-test` provides utilities for testing GraphQL execution.

If you only want to inspect metrics in Actuator, you can use whatever meter registry the application already configures. If you want to view traces, add a Micrometer Tracing bridge and exporter matching your observability backend, such as OpenTelemetry with OTLP. Metrics and tracing are two different outputs of the same Observation API.

## 4. Configuring Actuator and Prometheus

Expose the needed endpoints in `application.yml`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus

  endpoint:
    health:
      show-details: never

  metrics:
    distribution:
      percentiles-histogram:
        graphql.dataloader: true
~~~

`metrics` lets you read a specific meter via Actuator. `prometheus` exports meters in Prometheus scrape format. Histograms help Prometheus backends compute percentiles and latency distributions rather than looking only at averages.

Expose only necessary endpoints and secure them according to your deployment environment. Do not leave metrics or Prometheus endpoints publicly accessible if they reveal internal operational information.

## 5. Where Are Observations Created?

Spring for GraphQL has three main observation groups:

| Observation | Scope Measured | When Useful |
| --- | --- | --- |
| `graphql.request` | Entire GraphQL execution | Total request duration and outcome |
| `graphql.datafetcher` | A non-trivial data-fetching operation | Finding slow field resolvers |
| `graphql.dataloader` | A dispatched batch-loading call | Measuring DataLoader effectiveness |

Default property fetchers that simply read a Java property from a source object are considered trivial operations and do not necessarily produce a `graphql.datafetcher` observation.

Starting in Spring for GraphQL 1.4, data-fetching operations that merely delegate loading to a DataLoader no longer emit separate `graphql.datafetcher` observations as before. Instead, batch loading emits a `graphql.dataloader` observation. This makes traces reflect the real work happening in the batch loader and eliminates repetitive per-item spans.

## 6. Keys on graphql.dataloader

The default convention creates the following keys:

| Key | Cardinality | Meaning |
| --- | --- | --- |
| `graphql.loader.name` | Low | Name of the DataLoader being used |
| `graphql.outcome` | Low | Result: `SUCCESS` or `ERROR` |
| `graphql.error.type` | Low | Exception class name if the batch fails |
| `graphql.loader.size` | High | Size of the loaded item list |

Low-cardinality keys have a bounded set of values, making them suitable as metric tags. High-cardinality keys can have many distinct values; they are recorded in traces but are not used as default metric tags.

Consequently, `graphql.loader.size` lets you inspect batch sizes in traces. Do not expect Actuator metrics or Prometheus to maintain separate time series per batch size by default. This separation protects the metrics system from creating excessive time series.

`graphql.loader.size` is the size of the list of values loaded/returned by the DataLoader. For a loader mapping one key to one entity, this number is typically close to the number of unique keys. However, if duplicate keys are cached, entities do not exist, or the batch loader omits results, the item count may differ from the number of `load()` calls.

## 7. Creating the Book–Author Schema

Create the schema in `src/main/resources/graphql/book.graphqls`:

~~~graphql
type Query {
    books(limit: Int = 10): [Book!]!
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
~~~

A `Book` stores `authorId` to reference its author. The `author` field is a relationship field resolved through DataLoader.

Model examples:

~~~java
package com.example.books.domain;

public record Book(Long id, String title, Long authorId) {
}
~~~

~~~java
package com.example.books.domain;

public record Author(Long id, String name) {
}
~~~

Application services expose two operations: finding books and finding multiple authors by a set of IDs.

~~~java
package com.example.books.application;

import com.example.books.domain.Author;
import com.example.books.domain.Book;

import java.util.List;
import java.util.Map;
import java.util.Set;

import reactor.core.publisher.Mono;

public interface BookService {
    List<Book> findBooks(int limit);
}

public interface AuthorService {
    Mono<Map<Long, Author>> findByIds(Set<Long> authorIds);
}
~~~

Each public interface is placed in its own Java file matching the interface name. The example uses `Mono<Map<Long, Author>>` to illustrate a reactive batch loader. If your application uses synchronous JPA/JDBC, you can return `Map<Long, Author>` and register an appropriate imperative batch loader.

## 8. Registering the DataLoader and Using It in SchemaMapping

Register the batch loader via `BatchLoaderRegistry`:

~~~java
package com.example.books.graphql;

import com.example.books.application.AuthorService;
import com.example.books.domain.Author;

import org.springframework.graphql.execution.BatchLoaderRegistry;
import org.springframework.stereotype.Component;

@Component
public class AuthorBatchLoader {

    public AuthorBatchLoader(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(Long.class, Author.class)
            .registerMappedBatchLoader((authorIds, environment) ->
                authorService.findByIds(authorIds)
            );
    }
}
~~~

`BatchLoaderRegistry` registers loaders by key/value types, and Spring creates DataLoaders per GraphQL execution. By default, the registration key uses the fully qualified class name of the value type, so controllers can inject a `DataLoader` with matching generic types without specifying a custom name.

The controller calls `load()` for each book:

~~~java
package com.example.books.graphql;

import com.example.books.application.BookService;
import com.example.books.domain.Author;
import com.example.books.domain.Book;

import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

import java.util.List;
import java.util.concurrent.CompletableFuture;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books(@Argument Integer limit) {
        return bookService.findBooks(limit == null ? 10 : limit);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<Long, Author> authorLoader) {

        return authorLoader.load(book.authorId());
    }
}
~~~

Calls to `authorLoader.load()` are queued within the same execution. When GraphQL Java dispatches the DataLoader, the batch function receives the set of IDs and invokes `AuthorService.findByIds` once for that batch.

If you want to simplify the resolver, you can use `@BatchMapping`. Spring for GraphQL also creates DataLoader observations for `@BatchMapping` calls, so manual DataLoader registration is not required in order to measure them.

Example replacing `@SchemaMapping` and `BatchLoaderRegistry` above:

~~~java
package com.example.books.graphql;

import com.example.books.application.AuthorService;
import com.example.books.domain.Author;
import com.example.books.domain.Book;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class BookBatchController {

    private final AuthorService authorService;

    public BookBatchController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Mono<Map<Book, Author>> author(List<Book> books) {
        Set<Long> authorIds = books.stream()
            .map(Book::authorId)
            .collect(Collectors.toSet());

        return authorService.findByIds(authorIds).map(authorsById -> {
            Map<Book, Author> result = new HashMap<>();
            for (Book book : books) {
                result.put(book, authorsById.get(book.authorId()));
            }
            return result;
        });
    }
}
~~~

The example uses a `Book` record, which already implements `equals` and `hashCode`, making it suitable as a map key in `@BatchMapping`. Choose one of the two approaches for `Book.author` in the same schema; do not register both resolvers at once.

## 9. Sending a Query That Triggers Batching

Send a query fetching multiple books and requesting their authors:

~~~graphql
query MeasureAuthorBatch {
    books(limit: 10) {
        id
        title
        author {
            id
            name
        }
    }
}
~~~

To make results easy to read, set up a fixture with 10 books and 10 distinct `authorId`s. If multiple books share the same author, DataLoader's cache can coalesce duplicate keys; the number of unique keys dispatched will then be lower than the number of books.

With this query, the `Book.author` fields invoke the same DataLoader within one execution. If all keys are queued before dispatch and do not exceed batch size limits, there will typically be one batch observation for the author loader.

A single GraphQL request can generate multiple batch observations if there are multiple DataLoaders, multiple dispatch waves, or a `maxBatchSize` setting that splits the key set. Therefore, do not assume every request always produces exactly one `graphql.dataloader` observation.

You can send the query over HTTP to generate measurement samples:

~~~bash
curl -i -X POST http://localhost:8080/graphql \
  -H "Content-Type: application/json" \
  -d '{"query":"query MeasureAuthorBatch { books(limit: 10) { id title author { id name } } }"}'
~~~

## 10. Reading Metrics with Actuator

After sending the query, list the available meters:

~~~bash
curl -i http://localhost:8080/actuator/metrics
~~~

Find the `graphql.dataloader` meter, then inspect its details:

~~~bash
curl -i http://localhost:8080/actuator/metrics/graphql.dataloader
~~~

Actuator returns measurements such as `COUNT`, `TOTAL_TIME`, and `MAX` along with `availableTags`. `COUNT` is the number of recorded batch observations—meaning the number of measured batch dispatches; it is neither the number of `load()` calls nor the number of keys in a batch. `TOTAL_TIME` is the total duration across all batch observations. `MAX` is the maximum duration among the meter's recorded observations.

To filter by loader, inspect `availableTags` for the actual value of `graphql.loader.name`, then pass that tag:

~~~bash
curl --get "http://localhost:8080/actuator/metrics/graphql.dataloader" ^
  --data-urlencode "tag=graphql.loader.name:<loader-name>"
~~~

Replace `<loader-name>` with the actual value returned by the endpoint. For type-registered DataLoaders, the name may be based on the value type's class name; for `@BatchMapping` or custom registrations, always inspect the tag rather than guessing.

If the meter does not appear:

- Confirm Spring for GraphQL is version 1.4.0 or higher.
- Confirm an `ObservationRegistry` is present.
- Confirm GraphQL observation instrumentation has been added to the GraphQL runtime.
- Confirm the request actually invoked a `DataLoader` or `@BatchMapping`.
- Check that the metric exporter and Actuator endpoint are exposed.

## 11. Reading Prometheus and Calculating Average Duration

When a Prometheus registry is configured, scrape the endpoint:

~~~bash
curl -i http://localhost:8080/actuator/prometheus
~~~

Timers can be exported as series with suffixes such as `_count`, `_sum`, and histogram buckets depending on registry configuration. Metric names and labels are converted according to Prometheus naming conventions.

Illustrative example:

~~~text
graphql_dataloader_seconds_count{graphql_loader_name="com.example.books.domain.Author",graphql_outcome="SUCCESS"} 25
graphql_dataloader_seconds_sum{graphql_loader_name="com.example.books.domain.Author",graphql_outcome="SUCCESS"} 0.425
~~~

In this example:

- `count = 25`: there are 25 batch observations.
- `sum = 0.425`: total batch duration is 0.425 seconds.
- Average duration is approximately `0.425 / 25 = 0.017` seconds, or 17 ms.

These figures are illustrative; actual labels and meter names depend on conventions, registries, and naming strategies. If histograms are enabled, buckets can be used to track latency percentiles and detect slow batches in tail latency.

## 12. Inspecting Batch Size in Traces

Metrics answer aggregated questions over time. Traces let you see which batches a specific GraphQL request produced and how many results each batch contained.

To collect traces, configure Micrometer Tracing with a matching bridge/exporter, such as OpenTelemetry and OTLP, then inspect the trace in your observability backend.

A trace typically has the following high-level structure:

~~~text
HTTP server request
└── graphql.request
    ├── graphql.datafetcher (Query.books)
    └── graphql.dataloader
        ├── graphql.loader.name = Author
        ├── graphql.outcome = SUCCESS
        └── graphql.loader.size = 10
~~~

Exact loader names and displayed attributes depend on conventions. What to observe is that the batch span sits inside the GraphQL request, with a specific outcome and batch size. If a request creates multiple batches, the trace reveals which dispatch wave produced them and how long each took.

`graphql.loader.size` is a high-cardinality key and is therefore placed on traces. Do not turn every exact size value directly into a metric tag, because each distinct batch size would create an additional time series and blow up cardinality.

## 13. Adding a Batch-Size Bucket to Metrics (Advanced)

If you need to view batch size distribution on metrics dashboards, you can add a low-cardinality bucket tag instead of using raw integer batch sizes as tags. Spring Boot prefers a `DataLoaderObservationConvention` bean; the custom convention below extends the default convention:

~~~java
package com.example.books.observability;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.graphql.observation.DataLoaderObservationContext;
import org.springframework.graphql.observation.DefaultDataLoaderObservationConvention;
import org.springframework.stereotype.Component;

@Component
public class BatchSizeBucketConvention
        extends DefaultDataLoaderObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(
            DataLoaderObservationContext context) {

        int size = context.getResult().size();

        String bucket;
        if (size == 0) {
            bucket = "0";
        } else if (size <= 10) {
            bucket = "1-10";
        } else if (size <= 50) {
            bucket = "11-50";
        } else {
            bucket = "51+";
        }

        return super.getLowCardinalityKeyValues(context)
            .and(KeyValue.of("graphql.loader.size.bucket", bucket));
    }
}
~~~

Buckets have a small finite set of values, making them safe as metric tags. Because this class is a `DataLoaderObservationConvention` bean, Spring Boot uses it in place of the default convention when creating GraphQL observation instrumentation.

Only register one custom convention for DataLoader when replacing the default convention. Do not register a second instrumentation bean just to add tags. Keep buckets broad and stable; do not create per-value buckets such as `1`, `2`, `3`, ..., as cardinality would grow with data.

## 14. Comparing Before and After DataLoader

Use the same `MeasureAuthorBatch` query and the same dataset to compare.

| Signal | Without DataLoader | With DataLoader |
| --- | --- | --- |
| Book query | One query | One query |
| Author queries | Potentially N separate queries | One batch query or a few batches per limit |
| `graphql.datafetcher` for `author` field | May appear N times | Operations that merely delegate to DataLoader are represented by DataLoader observations |
| `graphql.dataloader` | No batch observations | One observation per batch dispatch |
| Trace | Many repeated field fetches | Shows batch operation and loader size |
| Database query count | Scales with number of books | Should drop to number of batch queries |

Do not conclude batching succeeded solely because `graphql.dataloader` has one observation. Verify that the batch function truly queries by a set of IDs—such as a single SQL statement `WHERE author_id IN (...)`—and cross-check the SQL query count.

A batch observation might show short duration while the database still runs multiple sequential SQL queries inside it. Conversely, a very large batch size can reduce query count while increasing duration and memory usage. Balance batch size, `maxBatchSize`, per-request caching, and query cost.

## 15. Interpreting Results and Troubleshooting

| Observation | Interpretation | Where to Check |
| --- | --- | --- |
| No `graphql.dataloader` | DataLoader not used, instrumentation disabled, or older version | Check versions, registry, and GraphQL runtime |
| One request has multiple batch observations | Multiple loaders or multiple dispatch waves | Check loader name, query shape, and dispatches |
| Batch size is often 1 | Query only needs one key, keys are dispatched separately, or batches are split | Check execution flow and `maxBatchSize` |
| Batch size is lower than parent count | Duplicate keys cached, missing entities, or incomplete batch result | Check key set and mapping result |
| `graphql.outcome=ERROR` | Batch loader failed | Check `graphql.error.type` and exception logs |
| Batch duration increases | Slow DB query, remote call, or mapping logic | Inspect traces, SQL logs, and dependency metrics |
| Batch duration is low yet request is slow | Bottleneck in root query, another resolver, transport, or many batches | Open the full `graphql.request` trace |
| Metrics lack batch size | Batch size is a high-cardinality key, only in traces by default | Use traces or a bucket convention |

When measuring in production, filter by `graphql.loader.name` and `graphql.outcome`. Never attach user IDs, tenant IDs, raw GraphQL queries, or individual entity keys to low-cardinality metric tags. Those values risk exposing sensitive data and exploding metric cardinality.

To observe the error path in a test environment, you can temporarily have the batch service throw a controlled exception and re-send the query. Verify `graphql.outcome=ERROR`, `graphql.error.type`, and the corresponding exception logs; restore the batch service afterward. Never intentionally break dependencies in production to test metrics.

## 16. Practice Completion Checklist

- Is Spring for GraphQL version 1.4.0 or higher?
- Does the application have an `ObservationRegistry`?
- Is the GraphQL runtime using `GraphQlObservationInstrumentation`?
- Are Actuator metrics endpoints exposed safely?
- Does the practice query load multiple parents with the same relationship field?
- Does the batch loader receive a set of keys and query in batches?
- Does a `graphql.dataloader` observation appear after sending the query?
- Did you inspect `COUNT`, `TOTAL_TIME`, and `MAX` per loader?
- Did you inspect `graphql.loader.size` in a trace?
- Can you distinguish low-cardinality metric tags from high-cardinality trace attributes?
- Did you compare batch observations against SQL query counts?
- Did you verify `outcome` and error type when a batch fails?

Measuring DataLoader observations reveals the cost of batch dispatches inside a GraphQL request. Metrics report frequency, duration, and outcomes per loader; traces reveal batch size and where batches sit within the request. Combining both perspectives with SQL metrics/logs confirms that DataLoader both batches keys properly and reduces database round trips.

## References

- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL — Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers and @BatchMapping](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring Boot — GraphQL Observation Auto-configuration](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/autoconfigure/observation/graphql/GraphQlObservationAutoConfiguration.html)
- [Spring for GraphQL — DataLoaderObservationContext API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/observation/DataLoaderObservationContext.html)
- [Spring for GraphQL 1.4 — DataLoader observations](https://github.com/spring-projects/spring-graphql/wiki/Spring-for-GraphQL-1.4)
