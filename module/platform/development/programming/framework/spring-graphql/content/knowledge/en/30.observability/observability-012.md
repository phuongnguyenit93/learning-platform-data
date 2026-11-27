# Tracing Requests and Resolvers

A GraphQL request can call many resolvers to build a single response. When an API is slow, looking only at total HTTP duration is rarely enough to tell which part is consuming time: the root query, a nested field, a DataLoader, or a call to an external service. Distributed tracing connects these activities into a single trace, from the moment the HTTP request enters the application until GraphQL finishes resolving all fields.

Spring for GraphQL integrates Micrometer Observation to record the duration and metadata of GraphQL requests, data fetchers, and DataLoaders. When combined with Micrometer Tracing in Spring Boot, observations can become spans in a tracing system such as OpenTelemetry, Zipkin, or an OTLP-compatible backend.

**Tracing requests and resolvers** means monitoring a GraphQL operation across multiple levels:

- The request observation shows how long the entire GraphQL execution took, what kind of operation ran, and its outcome.
- DataFetcher observations show how long each non-trivial resolver took, which field was handled, and whether an error occurred.
- DataLoader observations show how batch loading ran, which loader executed, and how many elements were loaded.

As a result, you can trace a query's execution path and identify the specific resolver or batch loader introducing latency.

## Observations, Spans, and Traces

Micrometer Observation is a unified API for recording an operation in an application. Depending on configuration, an observation can produce a metric, a trace span, or both. If the registry only has a metrics handler, observations produce timers/metrics; when Micrometer Tracing is configured, a tracing-aware handler also creates spans.

Concepts:

| Concept | Meaning |
| --- | --- |
| Observation | A measured activity, such as handling a GraphQL request or calling a resolver |
| ObservationRegistry | Registry that receives observations and dispatches them to handlers |
| Span | A unit of work with start time, end time, metadata, and parent/child relationships in a trace |
| Trace | A collection of spans belonging to the same processing flow |
| KeyValue | Metadata attached to an observation/span, such as operation type or outcome |
| ObservationConvention | Rules generating default names and metadata for an observation type |

Low-cardinality keys have a finite, stable set of values. They are suitable for both metrics and traces. High-cardinality keys can have a very large number of distinct values; they should only go into traces to avoid creating too many time series in metrics systems.

Examples:

- operation type can only be query, mutation, or subscription, so it is low cardinality.
- client-supplied operation name can vary widely, so it is high cardinality.
- field name is bounded by the schema, so it is low cardinality.
- field path varies with query structure and aliases, so it is high cardinality.

Distinguishing these two key types is essential when observing GraphQL in production.

## Which Observations Does a GraphQL Request Create?

Spring for GraphQL provides three main observations:

| Observation name | Measurement scope | When created |
| --- | --- | --- |
| graphql.request | Entire GraphQL execution request | For Query, Mutation, and Subscription across supported transports |
| graphql.datafetcher | A field resolution operation | Only for non-trivial data fetching operations |
| graphql.dataloader | A batch loading invocation | For @BatchMapping and manually registered DataLoaders |

Observations are created by GraphQlObservationInstrumentation. This class has existed since Spring for GraphQL 1.1.0. DataLoader observations were added in the 1.4.0 line.

Not every field creates a data fetcher span. If GraphQL Java simply reads an existing property on a Java object, that is a trivial operation and has no graphql.datafetcher observation. Fields resolved by resolvers performing real work—such as querying a repository, calling a service, or computing values—typically create observations.

## Relationship Between HTTP Request, GraphQL Request, and Resolvers

When GraphQL runs over HTTP, Spring Framework creates an observation for the HTTP server request. Spring for GraphQL creates the graphql.request observation inside the HTTP span. Resolvers and DataLoaders then create child observations inside that GraphQL request.

An illustrative trace:

~~~mermaid
flowchart TD
    A["HTTP server request"] --> B["graphql.request"]
    B --> C["graphql.datafetcher: Query.book"]
    B --> D["graphql.datafetcher: Book.author"]
    B --> E["graphql.dataloader: Book.reviews"]
    D --> F["HTTP client request to Author service"]
    E --> G["Database batch query"]
~~~

Traces help answer three questions:

1. Which HTTP request contains the slow GraphQL operation?
2. Within GraphQL execution, which resolver or DataLoader consumes the time?
3. If a resolver calls another service, which downstream span holds that time?

The GraphQL engine can execute independent fields concurrently. Therefore, child spans can overlap in time; do not simply sum all resolver durations to deduce total request duration.

## Configuring Tracing with Spring Boot

Spring Boot automatically configures ObservationRegistry when suitable observability infrastructure is present. For Spring for GraphQL, GraphQlObservationAutoConfiguration automatically registers GraphQlObservationInstrumentation when ObservationRegistry and the required GraphQL classes are on the classpath.

Therefore, a typical Spring Boot application does not need to manually instantiate GraphQlObservationInstrumentation. Manually registering a second identical instrumentation can create duplicate observations.

Example dependencies for Spring Boot 4.2 and OpenTelemetry with OTLP:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("org.springframework.boot:spring-boot-starter-opentelemetry")
}
~~~

Exporter/tracer dependencies depend on your Spring Boot version and backend. With Spring Boot 3.x, use the corresponding Micrometer Tracing and OpenTelemetry exporter dependencies for that Boot line; let Spring Boot dependency management manage versions.

Configure the OTLP endpoint and sampling in application.yml:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: http://localhost:4318/v1/traces
    resource-attributes:
      service.name: spring-graphql-catalog
~~~

In this example, the collector receives traces over OTLP HTTP at localhost:4318. Replace the endpoint with your deployment environment's collector address. service.name helps distinguish services in the trace backend UI.

By default, Spring Boot samples roughly 10% of traces to limit the volume of data sent to the backend. Setting sampling probability to 1.0 captures all traces in development or controlled diagnostics. In production, choose a rate suited to traffic volume and storage cost.

If using Zipkin, choose Spring Boot's Zipkin starter and configure the Zipkin endpoint instead of the OTLP exporter. Do not enable multiple redundant exporters unless you intentionally need to send traces to multiple backends.

## Verifying Instrumentation Is Enabled

In a Spring Boot application, GraphQlObservationAutoConfiguration creates GraphQlObservationInstrumentation when:

- An ObservationRegistry exists.
- GraphQL Java and Spring GraphQL are on the classpath.
- The application has not provided another GraphQlObservationInstrumentation bean.

Spring Boot 3.5 places GraphQlObservationAutoConfiguration in package org.springframework.boot.actuate.autoconfigure.observation.graphql. Spring Boot 4.x moved the package to org.springframework.boot.graphql.autoconfigure.observation.

If the application builds a custom GraphQlSource, verify that the custom GraphQlSource receives the required instrumentation. Replacing GraphQlSource manually can prevent parts of auto-configuration from being applied.

For applications not using Spring Boot, manually configure GraphQlObservationInstrumentation on GraphQlSource:

~~~java
import java.util.List;

import io.micrometer.observation.ObservationRegistry;
import org.springframework.graphql.execution.GraphQlSource;
import org.springframework.graphql.observation.GraphQlObservationInstrumentation;

GraphQlSource graphQlSource =
        GraphQlSource.schemaResourceBuilder()
                .schemaResources(schemaResource)
                .instrumentation(List.of(
                        new GraphQlObservationInstrumentation(
                                observationRegistry)))
                .build();
~~~

The snippet above demonstrates configuring GraphQlSource directly. In a Spring Boot application with auto-configuration enabled, do not add the instrumentation a second time without a clear customization reason.

For the GraphQL request span to become a child span of the HTTP server span, the transport must still pass the parent observation into GraphQLContext under the key micrometer.observation. Spring Framework has HTTP server instrumentation to do this. Adding GraphQlObservationInstrumentation to GraphQlSource alone is not enough to automatically establish trace propagation across transports.

## Request Observation: graphql.request

The graphql.request observation measures the total GraphQL execution time. It is created for both Servlet and Reactive applications, independent of a specific transport.

By default, the request observation has low-cardinality keys:

| Key | Meaning | Example values |
| --- | --- | --- |
| graphql.operation.type | Operation type | query, mutation, subscription |
| graphql.outcome | GraphQL request outcome | SUCCESS, REQUEST_ERROR, INTERNAL_ERROR |

If the GraphQL document cannot be parsed, operation type may be operation instead of query, mutation, or subscription.

Default high-cardinality keys:

| Key | Meaning |
| --- | --- |
| graphql.execution.id | ExecutionId of the GraphQL request |
| graphql.operation.name | Operation name sent by the client |

Operation name helps find a specific type of query in traces. Execution ID helps distinguish individual executions.

### Outcome Classification

graphql.outcome has three primary values:

- SUCCESS: a valid GraphQL response was sent and contained no errors.
- REQUEST_ERROR: the request could not be parsed or the response contained errors not belonging to INTERNAL_ERROR.
- INTERNAL_ERROR: a valid GraphQL response could not be created or the response contained at least one INTERNAL_ERROR.

Therefore, REQUEST_ERROR does not necessarily mean the HTTP transport failed. For instance, a resolver may return a business error in the GraphQL response, resulting in outcome REQUEST_ERROR while the HTTP request completes normally.

Spring for GraphQL also records GraphQL errors as Observation Events. These events typically appear as span events or annotations in the trace backend. An event can carry the error type and error message, helping pinpoint causes without looking only at the high-level outcome.

Because events can contain error messages, do not put tokens, passwords, personal information, or sensitive content into exception messages. Keep error messages helpful enough for diagnostics without exposing business data.

## DataFetcher Observation: graphql.datafetcher

The graphql.datafetcher observation measures the duration of a non-trivial data fetching operation. This is the most important part when you need to identify which resolver slows down a GraphQL request.

By default, it has low-cardinality keys:

| Key | Meaning | Example |
| --- | --- | --- |
| graphql.error.type | Class name of the data fetching error | IllegalStateException |
| graphql.field.name | Name of the field being resolved | author |
| graphql.outcome | Data fetching outcome | SUCCESS or ERROR |

High-cardinality key:

| Key | Meaning | Example |
| --- | --- | --- |
| graphql.field.path | Path to the field in the response | /book/author |

Field path is useful when the same resolver is invoked from multiple locations or across many list items. Do not put field path into metrics because a single query can generate many different paths.

## Example Tracing Resolvers in a GraphQL Query

Suppose a schema has Book, Author, and Review:

~~~graphql
type Query {
  book(id: ID!): Book
}

type Book {
  id: ID!
  title: String!
  author: Author
  reviews: [Review!]!
}

type Author {
  id: ID!
  name: String!
}

type Review {
  id: ID!
  rating: Int!
}
~~~

Controller:

~~~java
import java.util.List;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookController {

    private final BookService bookService;
    private final AuthorService authorService;
    private final ReviewService reviewService;

    public BookController(
            BookService bookService,
            AuthorService authorService,
            ReviewService reviewService) {
        this.bookService = bookService;
        this.authorService = authorService;
        this.reviewService = reviewService;
    }

    @QueryMapping
    public Book book(@Argument String id) {
        return bookService.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public Author author(Book book) {
        return authorService.findById(book.authorId());
    }

    @SchemaMapping(typeName = "Book", field = "reviews")
    public List<Review> reviews(Book book) {
        return reviewService.findByBookId(book.id());
    }
}
~~~

Client sends:

~~~graphql
query BookDetails($id: ID!) {
  book(id: $id) {
    id
    title
    author {
      name
    }
    reviews {
      rating
    }
  }
}
~~~

A trace may show:

1. HTTP server span for POST /graphql.
2. graphql.request for operation BookDetails.
3. graphql.datafetcher for Query.book.
4. graphql.datafetcher for Book.author.
5. graphql.datafetcher for Book.reviews.
6. Downstream spans if services call an instrumented database or HTTP service.

If title is read directly from a Book property, you may not see a separate datafetcher span for title. This is normal behavior because property fetching is a trivial operation.

The example above only illustrates trace structure. The display order of resolvers can differ because GraphQL may resolve fields concurrently.

## DataLoader Observation: graphql.dataloader

When using @BatchMapping or manually registered DataLoaders, Spring for GraphQL creates a graphql.dataloader observation for the batch loading operation.

By default, it has low-cardinality keys:

| Key | Meaning |
| --- | --- |
| graphql.error.type | Class name of the batch loading error |
| graphql.loader.name | Name of the DataLoader being used |
| graphql.outcome | SUCCESS or ERROR |

High-cardinality key:

| Key | Meaning |
| --- | --- |
| graphql.loader.size | Number of elements loaded in the batch |

Example:

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.graphql.data.method.annotation.BatchMapping;

@BatchMapping(typeName = "Book", field = "reviews")
public Map<Book, List<Review>> reviews(List<Book> books) {
    Set<String> bookIds = books.stream()
            .map(Book::id)
            .collect(Collectors.toSet());

    Map<String, List<Review>> reviewsByBook =
            reviewService.findByBookIds(bookIds);

    Map<Book, List<Review>> result = new HashMap<>();
    for (Book book : books) {
        result.put(
                book,
                reviewsByBook.getOrDefault(book.id(), List.of()));
    }
    return result;
}
~~~

When the batch loader runs, the trace can show graphql.dataloader with the loader name and number of loaded elements. This is how you verify batching behaves as expected.

If a GraphQL request has 20 Books and the loader loads reviews once for all 20 book IDs, the trace reveals the single batch operation instead of repeated queries. If the loader runs many small batches, check maxBatchSize, how DataLoader is dispatched, and where the resolver calls load.

DataLoader calls are not represented as regular datafetcher observations for the same batch work. Look for graphql.dataloader to analyze batch loading time.

## Analyzing Traces in a Tracing System

When opening a trace, read in order from parent spans to child spans:

1. Find the HTTP server span to see where the request came from and its total duration.
2. Open graphql.request to view GraphQL operation name, operation type, outcome, and error events.
3. Compare durations of graphql.datafetcher spans to locate high-duration fields.
4. Inspect graphql.dataloader if that field uses batch loading.
5. Expand HTTP client, database, or messaging spans beneath the resolver to see which system took the time.

Illustrative analysis table:

| Span | Illustrative duration | Interpretation |
| --- | ---: | --- |
| HTTP server request | 820 ms | Total HTTP endpoint handling time |
| graphql.request | 790 ms | Total GraphQL execution time |
| graphql.datafetcher: Query.book | 55 ms | Loading root Book |
| graphql.datafetcher: Book.author | 420 ms | Author resolver has high latency |
| graphql.dataloader: Book.reviews | 90 ms | Batch loading reviews |
| HTTP client request: author-service | 360 ms | Most of author time is in the external service |

In this example, investigate author-service first. Optimizing the GraphQL schema or the reviews DataLoader will not solve the primary bottleneck.

Child spans can execute concurrently, so the sum of their durations can exceed the duration of graphql.request. Inspect timing overlaps and parent-child relationships rather than mechanically summing durations.

## Connecting Traces Between Resolvers and External Services

If a resolver calls a service over HTTP, Spring Boot can create an HTTP client observation and propagate trace context to the downstream service.

With WebClient, use the WebClient.Builder auto-configured by Spring Boot:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ClientConfiguration {

    @Bean
    WebClient authorWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("http://author-service")
                .build();
    }
}
~~~

With RestClient, use the RestClient.Builder injected by Spring Boot. Auto-configured builders add the trace propagation interceptor.

Do not create WebClient with WebClient.create() or RestClient via a manual constructor if you want automatic trace propagation. Manually created clients may lack instrumentation and break traces between services.

When the downstream service also uses tracing and accepts W3C traceparent or B3 headers accordingly, the trace backend can display that service's spans within the same trace.

## Context Propagation in Spring MVC and WebFlux

GraphQL Java may execute data fetchers on a different thread from the thread that received the HTTP request. With WebFlux, work can also switch across multiple reactive operators. If context is not propagated properly, resolver spans may lose their parent or logs may lose trace IDs.

Spring for GraphQL uses Micrometer Context Propagation to transfer context:

- Spring MVC: ThreadLocal context from the Servlet request thread is propagated to the thread GraphQL Java uses to invoke data fetchers.
- Spring WebFlux: Reactor Context from the WebFlux request pipeline is passed to reactive data fetchers.

For custom executors or asynchronous code managed by the application, ensure context is propagated forward. For an AsyncTaskExecutor auto-configured by Spring Boot, you can enable propagate-context. When creating an executor manually, use ContextPropagatingTaskDecorator:

~~~yaml
spring:
  reactor:
    context-propagation: auto
  task:
    execution:
      propagate-context: true
~~~

When configuring AsyncTaskExecutor manually, you can use ContextPropagatingTaskDecorator:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;

@Configuration
public class AsyncConfiguration {

    @Bean
    ContextPropagatingTaskDecorator contextPropagatingTaskDecorator() {
        return new ContextPropagatingTaskDecorator();
    }
}
~~~

If using a custom executor without propagating context, observations may become new root spans or lose their link to the original trace. Verify both ThreadLocal and Reactor Context according to your web stack.

## Log Correlation with traceId and spanId

Spring Boot integrates with Micrometer Tracing to add traceId and spanId to the logging MDC. When viewing logs and traces together, you can locate logs belonging to the exact request or resolver under investigation.

Example correlation pattern:

~~~yaml
logging:
  pattern:
    correlation: "[%X{traceId:-},%X{spanId:-}] "
~~~

With default configuration, Spring Boot already adds correlation IDs based on traceId and spanId to logs. Customize the pattern only if you want a custom format or already use a customized logging configuration.

In resolver logs, there is no need to log the entire GraphQL document or variables. Trace ID and span ID are sufficient to link logs to traces; request payloads can contain tokens, personal information, or sensitive business data.

## Customizing GraphQL Observation Metadata

Spring for GraphQL uses ObservationConvention to generate metadata for requests, data fetchers, and DataLoaders. With Spring Boot, the preferred approach is providing a convention bean; GraphQlObservationAutoConfiguration will pick up the corresponding bean.

Example adding a fixed low-cardinality key for GraphQL requests:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.observation.DefaultExecutionRequestObservationConvention;
import org.springframework.graphql.observation.ExecutionRequestObservationContext;
import org.springframework.graphql.observation.ExecutionRequestObservationConvention;

@Configuration
public class GraphQlObservationConfiguration {

    @Bean
    ExecutionRequestObservationConvention executionRequestObservationConvention() {
        return new DefaultExecutionRequestObservationConvention() {

            @Override
            public KeyValues getLowCardinalityKeyValues(
                    ExecutionRequestObservationContext context) {
                return super.getLowCardinalityKeyValues(context)
                        .and(KeyValue.of("graphql.api", "catalog"));
            }
        };
    }
}
~~~

The graphql.api key always has the value catalog, so cardinality stays low. You can use custom conventions to normalize metadata by domain or API group.

Do not add per-request varying values such as user ID, order ID, email, raw query, or field path into low-cardinality keys. If you genuinely need to locate a specific request, use high-cardinality attributes in traces and ensure values contain no sensitive data.

When customizing DataFetcherObservationConvention or DataLoaderObservationConvention, retain the required default keys so existing dashboards and alert rules continue working.

## Distinguishing Metrics and Traces

Metrics reveal overall trends and rates. Traces let you inspect a specific request in depth.

| Question | Where to look |
| --- | --- |
| Did GraphQL request p95 rise over the last 15 minutes? | Metric from graphql.request |
| Which resolver fails frequently? | Metric graphql.datafetcher by field name and outcome |
| In which resolver was a specific request slow? | Trace with graphql.request and graphql.datafetcher |
| Did the batch loader group multiple keys? | graphql.dataloader trace and loader size |
| Did a GraphQL request have parse or validation errors? | graphql.request outcome and error events |
| Which downstream service made a resolver slow? | HTTP client span and that service's trace |

Low-cardinality keys go into both metrics and traces. High-cardinality keys go only into traces. This allows metrics to aggregate by operation type, field name, and outcome without spawning millions of time series.

## Sampling and Limiting Trace Data

Do not always sample 100% of requests in high-traffic production environments. 100% sampling is useful in development or when investigating a reproducible bug, but it can raise storage costs and collector load.

Principles:

- Choose sampling probability based on traffic volume and investigation goals.
- Keep parent-based sampling so child spans follow the parent trace's sampling decision when using the corresponding OpenTelemetry sampler.
- Limit attribute and event counts if traces have many fields.
- Never write raw queries, variables, access tokens, or personal information into spans.
- Use stable operation naming conventions to find query types in traces.
- Include only necessary metadata in custom conventions.

With OpenTelemetry, Spring Boot supports limiting attribute counts, event counts, link counts, and attribute value lengths via management.opentelemetry.tracing.limits.*.

## Common Mistakes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Only HTTP span appears, no graphql.request | GraphQL observation instrumentation not registered or missing ObservationRegistry | Check Actuator, ObservationRegistry, and GraphQlObservationAutoConfiguration |
| graphql.request exists but no resolver spans | Field uses trivial property access, field not selected, or resolver not called | Check query selection set and how the field is resolved |
| Resolver span has no parent | Context propagation broken across thread or executor switches | Check Micrometer Context Propagation and executors |
| DataLoader span missing | Loader runs through uninstrumented custom path or instrumentation not attached to GraphQL source | Check BatchLoaderRegistry and GraphQlObservationInstrumentation |
| Duplicate GraphQL spans appear | Instrumentation registered twice | Check custom GraphQlSource and auto-configuration |
| Traces created but not arriving at backend | Exporter not configured, collector unavailable, or sampling dropped traces | Check OTLP endpoint, exporter, sampling, and collector |
| Resolver calls WebClient but trace breaks | WebClient created manually instead of using auto-configured builder | Inject WebClient.Builder from Spring Boot |
| Metrics generate too many time series | Operation name, execution ID, or field path placed in low-cardinality key | Move dynamic data to high-cardinality trace keys |
| Trace has error yet metric only shows request error | GraphQL errors are classified in graphql.outcome and error events | Open span events to inspect error type and message |
| Logs lack traceId/spanId | Incorrect logging pattern or broken context propagation | Check Micrometer Tracing, MDC, and logging pattern |

## Principles for Reading Request and Resolver Traces

When investigating a slow GraphQL request:

1. Find the HTTP server span to identify the request and total duration.
2. Open graphql.request to inspect operation type, operation name, outcome, and error events.
3. Compare graphql.datafetcher spans to identify slow fields.
4. Check graphql.dataloader if the field uses batch loading.
5. Expand downstream spans to separate resolver time from service or database time.
6. Check context propagation if child spans detach from the parent trace.
7. Use low-cardinality keys for metrics and high-cardinality keys for traces.
8. Keep trace metadata safe by avoiding query variables and sensitive data.
9. Use sampling suited to production traffic.
10. Verify instrumentation is registered only once.

Tracing requests and resolvers provides visibility into a GraphQL operation from the transport layer down to individual data fetchers and batch loaders. Spring for GraphQL creates graphql.request, graphql.datafetcher, and graphql.dataloader observations with Micrometer. When Spring Boot configures ObservationRegistry and Micrometer Tracing, those observations become spans viewable in a trace backend. Combining request outcome, field path, loader name, context propagation, and log correlation helps pinpoint slow resolvers, downstream errors, or ineffective batching without logging full GraphQL request payloads.

## References

- [Spring for GraphQL - Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL - GraphQlObservationInstrumentation API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/observation/GraphQlObservationInstrumentation.html)
- [Spring Boot - Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot - Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot 3.5 - GraphQlObservationAutoConfiguration API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/autoconfigure/observation/graphql/GraphQlObservationAutoConfiguration.html)
- [Spring Boot 4.x - GraphQL Auto-configuration classes](https://docs.spring.io/spring-boot/appendix/auto-configuration-classes/spring-boot-graphql.html)
- [Spring Guide - Observing GraphQL in action](https://spring.io/guides/topicals/observing-graphql-in-action/)
