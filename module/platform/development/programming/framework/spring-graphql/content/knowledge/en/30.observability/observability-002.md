# ObservationRegistry

In a Spring for GraphQL application, a request may arrive over HTTP or WebSocket, execute multiple field resolvers, query a database, use a DataLoader, and return partial data along with errors. When an API is slow or failing, looking only at controller logs is often not enough to determine whether the request spent time in transport, GraphQL execution, a DataFetcher, or a batch load.

**ObservationRegistry** is the central component of Micrometer Observation. It holds the configuration and handlers that process the observation lifecycle. Spring for GraphQL uses **GraphQlObservationInstrumentation** to record timing and metadata for GraphQL requests, non-trivial DataFetcher operations, and DataLoaders. These observations can be converted into metrics and distributed traces through their respective handlers.

This article explains the role of ObservationRegistry, the building blocks of Micrometer Observation, how Spring for GraphQL integrates instrumentation, how to enable observability in Spring Boot, how to read default observations, customize conventions, create custom observations, propagate context across synchronous and reactive flows, test, and troubleshoot common issues.

## 1. What Is ObservationRegistry?

**ObservationRegistry** belongs to the io.micrometer.observation package. It is where Observation-related configuration is managed, such as:

- ObservationHandler: receives observation lifecycle events and produces metrics, spans, or logs.
- ObservationPredicate: decides whether to create an observation or replace it with a no-op observation.
- ObservationFilter: adds or modifies context before the observation stops.
- ObservationConvention: defines observation names and metadata to collect.

ObservationRegistry also manages the current observation and its scope. As a result, components can associate ongoing work with a parent observation instead of building a separate tracing mechanism.

You can picture it as:

~~~text
GraphQL request
      |
      v
GraphQlObservationInstrumentation
      |
      v
ObservationRegistry
      |
      +--> ObservationHandler --> MeterRegistry --> Metrics backend
      |
      +--> ObservationHandler --> Tracer --------> Trace backend
      |
      +--> ObservationFilter
      |
      +--> ObservationPredicate
      |
      +--> ObservationConvention
~~~

ObservationRegistry is neither the storage for all metric samples nor the trace backend. It coordinates the observation lifecycle. Handlers connect observations to measurement or tracing systems.

## 2. Distinguishing ObservationRegistry, MeterRegistry, and Tracer

These three components have distinct roles:

| Component | Role |
|---|---|
| ObservationRegistry | Manages Observations, context, handlers, filters, predicates, and conventions |
| MeterRegistry | Stores and exports meters such as Counter, Timer, Gauge |
| Tracer | Creates and manages spans in a distributed trace |

For example, a GraphQL request completes in 120 ms:

- ObservationRegistry coordinates the request observation.
- The meter handler can record the duration into a Timer in MeterRegistry.
- The tracing handler can create a corresponding span in a trace.

The application does not need separate custom code to both record a Timer and create a span for the same operation. Micrometer Observation provides a unified API layer for handlers to process both types of telemetry.

## 3. Components of Micrometer Observation

### Observation

**Observation** represents an operation to measure, such as a GraphQL request or loading data from a repository. An Observation has a name, context, key-value metadata, and a lifecycle.

An observation typically goes through these steps:

1. Create the observation.
2. Start the observation.
3. Open a scope to set the observation as the current activity.
4. Run the work.
5. Record an exception or event if one occurs.
6. Close the scope and stop the observation.

The observe(...) method executes this lifecycle for a synchronous block of code:

~~~java
Observation.createNotStarted("catalog.book.lookup", observationRegistry)
        .lowCardinalityKeyValue("result", "cache")
        .observe(() -> bookService.loadBook(bookId));
~~~

In this example, the execution time of loadBook is measured under the catalog.book.lookup observation. If the lambda throws an exception, the Observation API can record the error before ending.

### Observation.Context

**Observation.Context** is a mutable data container attached to an observation. Instrumentation and handlers use the context to share metadata or state throughout the lifecycle.

The context can hold information about the request, response, exception, field being resolved, or data needed to build key-values.

The context makes it possible to pass state between handlers without placing everything into ThreadLocal.

### ObservationHandler

**ObservationHandler** reacts to events such as start, stop, error, event, and scope lifecycle. A handler only processes contexts accepted by its supportsContext(...) method.

For example, a meter handler creates a Timer from the observation duration; a tracing handler creates a span and attaches attributes to it.

Multiple handlers can receive the same observation. Thus, a single operation can produce both metrics and traces.

### ObservationConvention

**ObservationConvention** separates naming and metadata from the logic of starting/stopping an observation. A convention determines:

- The observation name.
- The contextual name displayed in traces.
- Low-cardinality key-values.
- High-cardinality key-values.

Spring for GraphQL provides default conventions for requests, DataFetchers, and DataLoaders. Applications can provide custom conventions to add appropriate metadata.

### ObservationPredicate and ObservationFilter

ObservationPredicate decides whether to create an observation. A predicate can be used to exclude a group of observations from the system.

ObservationFilter modifies the context before an observation stops. For example, a filter can add normalized metadata or environment details.

Do not use filters to attach private data to every observation. Metadata must have a clear observability purpose and adhere to cardinality rules.

## 4. Low Cardinality and High Cardinality

Micrometer divides key-value metadata into two groups:

**Low cardinality** has a finite or bounded set of values; for example, operation type can be query, mutation, or subscription. These values can be used as tags for metrics and can also appear in traces.

**High cardinality** can have a very large number of distinct values, such as execution IDs, user IDs, or paths containing individual resource IDs. These values should only be included in traces and should not become metric tags.

| Type | Example | Where used |
|---|---|---|
| Low cardinality | operation.type=query | Metrics and traces |
| Low cardinality | outcome=SUCCESS | Metrics and traces |
| High cardinality | execution.id=per-request unique value | Traces |
| High cardinality | field.path=/bookById/author | Traces |
| High cardinality | user.id or resource.id | Only when genuinely needed in traces and privacy-reviewed |

If you put a nearly unique per-request value into a metric tag, the number of time series can grow rapidly. As a result, the metrics backend consumes excessive memory, queries slow down, and storage costs increase.

Do not put raw GraphQL documents, variable values, emails, tokens, or personal information into metric tags. High cardinality does not mean sensitive data becomes safe; traces can still be stored and accessed by many people.

## 5. ObservationRegistry in Spring for GraphQL

Spring for GraphQL integrates Micrometer Observation via **GraphQlObservationInstrumentation** in the org.springframework.graphql.observation package.

This instrumentation creates observations while GraphQL Java executes a request. It can measure:

- Execution time of a GraphQL server request.
- Duration of non-trivial DataFetchers.
- Duration of DataLoaders, including batch loaders registered via @BatchMapping or manual DataLoaders.

Observations are only published when the instrumentation uses an ObservationRegistry configured with the appropriate handlers. Simply adding annotations to resolvers or adding a Micrometer dependency does not guarantee metrics and traces are exported.

## 6. Three Default GraphQL Observation Groups

Spring for GraphQL provides three observation groups with default names:

| Observation name | Measurement scope | When created |
|---|---|---|
| graphql.request | Entire server GraphQL operation | Every GraphQL request |
| graphql.datafetcher | A field data-fetching operation | For non-trivial DataFetchers |
| graphql.dataloader | A batch load invocation | With @BatchMapping and manually registered DataLoaders; supported since Spring GraphQL 1.4 |

A single request can create one graphql.request observation and multiple graphql.datafetcher observations. If resolvers use DataLoaders, batch loads can also create graphql.dataloader observations.

~~~mermaid
flowchart TD
    A[HTTP request observation] --> B[graphql.request]
    B --> C[graphql.datafetcher: Query.books]
    B --> D[graphql.datafetcher: Book.author]
    D --> E[graphql.dataloader: authorLoader]
    B --> F[GraphQL response]
~~~

### 6.1. GraphQL Request Observation

The observation named **graphql.request** measures the execution duration of a GraphQL request. It works with both Servlet and Reactive applications, along with supported transports.

The default convention is **DefaultExecutionRequestObservationConvention**, based on **ExecutionRequestObservationContext**.

Default low-cardinality keys:

| Key | Meaning |
|---|---|
| graphql.operation.type | Operation type: query, mutation, subscription, or operation if the document cannot be parsed |
| graphql.outcome | Request processing outcome |

Default high-cardinality keys:

| Key | Meaning |
|---|---|
| graphql.execution.id | ExecutionId of the GraphQL request |
| graphql.operation.name | Operation name provided by the client |

Values of graphql.outcome:

| Outcome | When it occurs |
|---|---|
| SUCCESS | A valid GraphQL response is sent with no errors |
| REQUEST_ERROR | The request cannot be parsed or the response has errors, but no INTERNAL_ERROR error |
| INTERNAL_ERROR | A valid GraphQL response cannot be produced or the response contains at least one INTERNAL_ERROR error |

Spring for GraphQL also records GraphQL errors as Observation Events. These events are typically represented by tracing handlers as span events or annotations. The event name reflects the GraphQL error type; the contextual name may contain the full error message.

### 6.2. DataFetcher Observation

The observation named **graphql.datafetcher** measures the runtime of a data-fetching operation during GraphQL execution. Spring for GraphQL does not create observations for every simple property fetcher. Reading a property directly from a Java object is considered a trivial operation and typically does not need a dedicated span.

The default convention is **DefaultDataFetcherObservationConvention**, based on **DataFetcherObservationContext**.

Default low-cardinality keys:

| Key | Meaning |
|---|---|
| graphql.error.type | Class name of the error when the DataFetcher fails |
| graphql.field.name | Name of the field being resolved |
| graphql.outcome | SUCCESS or ERROR |

Default high-cardinality key:

| Key | Meaning |
|---|---|
| graphql.field.path | Path of the field in the GraphQL response, e.g. /bookById/author |

DataFetcher observations are useful for identifying which field consumes the most time. For example, if the total query time is 100 ms but the Book.author field takes 80 ms, you may need to inspect the repository or remote service called by that resolver.

### 6.3. DataLoader Observation

Since Spring for GraphQL 1.4, the **graphql.dataloader** observation measures DataLoader activity, including batch methods generated from @BatchMapping and manually registered DataLoaders.

The default convention is **DefaultDataLoaderObservationConvention**, based on **DataLoaderObservationContext**.

Default low-cardinality keys:

| Key | Meaning |
|---|---|
| graphql.error.type | Class name of the error when the batch load fails |
| graphql.loader.name | Name of the DataLoader being used |
| graphql.outcome | SUCCESS or ERROR |

Default high-cardinality key:

| Key | Meaning |
|---|---|
| graphql.loader.size | Number of elements in the loaded list |

This observation helps check whether a batch load groups multiple keys together. If a loader frequently receives a batch size of 1, review how the field is resolved, when the DataLoader dispatches, or how the client constructs its selection set.

## 7. Enabling GraphQL Observations in Spring Boot

With Spring Boot, you should use auto-configuration to create the ObservationRegistry, handlers, and GraphQL instrumentation. Typical dependencies:

~~~gradle
implementation("org.springframework.boot:spring-boot-starter-graphql")
implementation("org.springframework.boot:spring-boot-starter-actuator")
runtimeOnly("io.micrometer:micrometer-registry-prometheus")
~~~

The Actuator starter provides observability infrastructure and metrics management. The Prometheus registry is one exporter option; it can be replaced with the registry suited to your monitoring system.

Example management endpoint configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
~~~

With Spring Boot 3 and above, GraphQL observation auto-configuration can register GraphQlObservationInstrumentation when GraphQL infrastructure and ObservationRegistry are present. Do not register the instrumentation manually again if auto-configuration already handles it.

Verification steps:

1. The application has Spring Boot Actuator and the appropriate GraphQL dependencies.
2. The application context contains an ObservationRegistry.
3. GraphQL instrumentation is registered with GraphQlSource.
4. An appropriate meter handler or tracing handler is present.
5. An exporter or endpoint is available to read the results.

You can inspect the list of metrics via `/actuator/metrics` and scrape Prometheus via `/actuator/prometheus` if the endpoints are properly exposed and secured.

To obtain distributed traces, you must additionally configure a Micrometer Tracing bridge and a corresponding exporter, such as an OpenTelemetry- or Brave-based system. Enabling only a metrics registry does not automatically set up a trace backend.

## 8. Manual Configuration Without Spring Boot

If a Spring Framework application configures GraphQlSource manually, you can add GraphQlObservationInstrumentation to GraphQlSource.Builder:

~~~java
GraphQlObservationInstrumentation instrumentation =
        new GraphQlObservationInstrumentation(observationRegistry);

GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
        .schemaResources(schemaResource)
        .instrumentation(List.of(instrumentation))
        .build();
~~~

GraphQlObservationInstrumentation accepts an ObservationRegistry and uses the default conventions if no custom conventions are passed.

In a non-Boot application, you need to configure ObservationHandler manually. For example, if you want to record Timers, register DefaultMeterObservationHandler with a MeterRegistry; if you want to create spans, register the corresponding tracing handler.

~~~java
ObservationRegistry observationRegistry = ObservationRegistry.create();
observationRegistry.observationConfig()
        .observationHandler(
                new DefaultMeterObservationHandler(meterRegistry));
~~~

Key imports for this example:

~~~java
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.ObservationRegistry;
~~~

The snippet above only registers the meter handler. Exporting distributed traces requires a separately configured tracing handler and tracer.

If GraphQlSource already has other instrumentations, preserve the existing instrumentations when adding GraphQlObservationInstrumentation. Do not overwrite the entire list with a single new instrumentation if doing so would drop instrumentations for tracing, security, or other features.

## 9. Customizing ObservationConvention

Default conventions provide general metadata for all applications. When you need to add information with a bounded set of values, you can provide a custom convention.

With Spring Boot, the preferred approach is to declare a bean implementing the corresponding convention interface. GraphQL observation auto-configuration will use that bean instead of the default convention.

Example adding a fixed label to distinguish an API group:

~~~java
@Configuration(proxyBeanMethods = false)
public class GraphQlObservationConfiguration {

    @Bean
    ExecutionRequestObservationConvention executionRequestConvention() {
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

Key imports:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.observation.DefaultExecutionRequestObservationConvention;
import org.springframework.graphql.observation.ExecutionRequestObservationContext;
import org.springframework.graphql.observation.ExecutionRequestObservationConvention;
~~~

Here, graphql.api always has the value catalog. This is a suitable low-cardinality key for metrics because the number of values is bounded per API group.

You can customize the other convention groups:

- ExecutionRequestObservationConvention: metadata for the entire request.
- DataFetcherObservationConvention: metadata for a field resolver.
- DataLoaderObservationConvention: metadata for a batch load, available since Spring GraphQL 1.4.

When creating a custom convention, retain the mandatory keys from the default convention. The simplest approach is to extend the default convention and append to KeyValues, rather than rewriting all key-value logic from scratch.

### Without Spring Boot

You can pass conventions directly into GraphQlObservationInstrumentation. Since Spring GraphQL 1.4, the full constructor accepts the registry and all three conventions:

~~~java
GraphQlObservationInstrumentation instrumentation =
        new GraphQlObservationInstrumentation(
                observationRegistry,
                requestConvention,
                dataFetcherConvention,
                dataLoaderConvention);
~~~

The older constructor taking only the request and DataFetcher conventions was deprecated in 1.4 in favor of the constructor that includes the DataLoader convention. Use the API appropriate for the version of Spring for GraphQL in your project.

## 10. Creating Custom Observations in a Resolver or Service

GraphQL instrumentation measures the overall duration of requests and DataFetcher operations. However, a resolver may invoke multiple internal steps, such as reading from a cache, calling a search service, and loading data from a repository.

You can create a separate observation for a business step you want to track:

~~~java
@Service
public class BookEnrichmentService {

    private final ObservationRegistry observationRegistry;

    public BookEnrichmentService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public BookDetails enrich(Book book, boolean cacheHit) {
        return Observation.createNotStarted(
                        "catalog.book.enrichment",
                        this.observationRegistry)
                .lowCardinalityKeyValue(
                        "cache.result",
                        cacheHit ? "hit" : "miss")
                .observe(() -> loadDetails(book));
    }

    private BookDetails loadDetails(Book book) {
        // Load supplementary data for the book.
        return new BookDetails(book.getId(), book.getTitle());
    }
}
~~~

The catalog.book.enrichment observation can appear inside the GraphQL request observation. As a result, traces help distinguish the duration of the entire operation, the resolver duration, and the duration of the enrichment step itself.

Only add metadata with a small set of values to low-cardinality keys. For instance, cache.result has two values: hit and miss. Do not put book IDs or user IDs into metric tags.

The observe(...) method in the example is suited for synchronous work. If a service returns a Mono or Flux, do not wrap Publisher creation inside observe(...) and assume the entire asynchronous work has been measured; the synchronous lambda can finish as soon as the Publisher is created. For reactive pipelines, use a Reactor-compatible observation/context propagation mechanism or let framework instrumentation manage the lifecycle.

## 11. Linking GraphQL Observations with HTTP Traces

The GraphQL engine runs on top of a transport. When a client sends an HTTP request, Spring Framework can create an HTTP server observation and trace context for that request. Spring for GraphQL creates the graphql.request observation for GraphQL execution.

When context is propagated properly, the GraphQL request observation can become a child span of the HTTP server span. DataFetcher and DataLoader observations continue to reside within the GraphQL request trace.

~~~mermaid
flowchart TD
    A[HTTP client span] --> B[HTTP server observation]
    B --> C[graphql.request]
    C --> D[graphql.datafetcher]
    D --> E[graphql.dataloader]
    D --> F[Database client observation]
    D --> G[Remote service client observation]
~~~

Spring for GraphQL uses the conventional context key **micrometer.observation** in the GraphQL context to determine the current parent observation. Instrumentation at the transport layer is responsible for propagating trace context across network boundaries. For HTTP, Spring Framework has its own instrumentation to handle trace propagation.

GraphQlObservationInstrumentation does not replace HTTP instrumentation. If you only register GraphQL instrumentation while the transport does not propagate the parent context, traces may lack the expected parent-child relationship.

### Context Propagation with WebFlux and Asynchronous Tasks

With Spring MVC, context usually stays with the request thread. With WebFlux, a single request may hop across multiple threads in a Reactor pipeline, so you cannot assume ThreadLocal is present in every operator.

Micrometer Context Propagation helps transfer context information between execution mechanisms. In Spring Boot, automatic Reactor context propagation can be enabled with:

~~~yaml
spring:
  reactor:
    context-propagation: auto
~~~

With an AsyncTaskExecutor auto-configured by Spring Boot, context propagation for @Async tasks can be enabled with:

~~~yaml
spring:
  task:
    execution:
      propagate-context: true
~~~

If configuring an executor manually, you can use ContextPropagatingTaskDecorator:

~~~java
@Configuration(proxyBeanMethods = false)
public class AsyncConfiguration {

    @Bean
    ContextPropagatingTaskDecorator contextPropagatingTaskDecorator() {
        return new ContextPropagatingTaskDecorator();
    }
}
~~~

Context propagation must be configured according to your Spring Boot version and how executors are created in the application. When context is lost, traces can split into disconnected traces or custom observations will no longer be children of the request.

ContextPropagatingTaskDecorator is available in Spring Framework 6.1 and later. Context propagation properties also depend on the Spring Boot version; check the configuration metadata for your project's version before enabling them.

## 12. Customizing ObservationRegistry

Spring Boot can automatically register beans of type:

- ObservationHandler.
- ObservationPredicate.
- ObservationFilter.
- GlobalObservationConvention.

These beans are registered with the auto-configured ObservationRegistry. You can use ObservationRegistryCustomizer if you need to configure the registry directly.

### ObservationPredicate

A predicate allows ignoring a group of observations by name or context. For example, if an application has an internal observation that does not need to be published, you can return false for that observation.

Do not disable all of graphql.request solely to reduce metrics overhead if operations teams still need to know which requests are slow or failing.

### ObservationFilter

A filter runs before an observation stops and can add metadata to the context. Only add key-values with stable meaning that do not contain sensitive data.

### ObservationHandler

A handler receives lifecycle callbacks. Spring Boot typically auto-configures handlers for metrics and tracing based on dependencies on the classpath. When configuring a handler manually, ensure it supports the right Observation.Context type.

If a handler does not support the GraphQL context, it will not process GraphQL observations even if the handler is registered on the registry.

## 13. Testing ObservationRegistry

Micrometer provides **TestObservationRegistry** in the micrometer-observation-test artifact. This registry records observations created during tests so you can inspect names, key-values, errors, and events.

Test dependency:

~~~gradle
testImplementation("io.micrometer:micrometer-observation-test")
~~~

Example testing a custom observation:

~~~java
class BookEnrichmentServiceTest {

    private final TestObservationRegistry observationRegistry =
            TestObservationRegistry.create();

    @Test
    void shouldRecordBookEnrichmentObservation() {
        Observation.createNotStarted(
                        "catalog.book.enrichment",
                        observationRegistry)
                .lowCardinalityKeyValue("cache.result", "hit")
                .observe(() -> {
                    // Execute the operation under test.
                });

        assertThat(observationRegistry)
                .hasAnObservation(context -> {
                    context.hasNameEqualTo("catalog.book.enrichment");
                    context.hasLowCardinalityKeyValue(
                            "cache.result", "hit");
                });
    }
}
~~~

In Spring Boot integration tests, you can provide TestObservationRegistry as a bean so GraphQL observation auto-configuration uses that registry. After sending a GraphQL request with GraphQlTester, verify that the registry contains a graphql.request observation. With Spring GraphQL 1.4 or later, you can also assert graphql.dataloader when an operation goes through a DataLoader.

Things to verify:

1. A GraphQL request creates a graphql.request observation.
2. A successful request has outcome SUCCESS.
3. A request with GraphQL errors has the corresponding outcome REQUEST_ERROR or INTERNAL_ERROR.
4. Non-trivial DataFetchers create graphql.datafetcher.
5. Simple property fetchers do not create excessive unnecessary observations.
6. DataLoader observations appear when using @BatchMapping or manual DataLoaders, if supported by the version.
7. Observations include all mandatory low-cardinality keys.
8. Errors are attached to the appropriate observation or span.
9. The observation scope is closed after the request completes.
10. Parent context is propagated properly across the transport and reactive pipeline.

TestObservationRegistry is well-suited for verifying instrumentation at the application level. To test actual exporters, run integration tests with an appropriate MeterRegistry or trace exporter.

## 14. Checking Metrics and Traces at Runtime

After configuring Actuator and exporters, you can inspect metrics at runtime.

Examples:

- /actuator/metrics/graphql.request: inspect the count and timing of GraphQL requests.
- /actuator/metrics/graphql.datafetcher: inspect DataFetcher activity if the corresponding meter exists.
- /actuator/metrics/graphql.dataloader: inspect DataLoader activity if supported by the version and batch loads occur.
- /actuator/prometheus: read metrics in Prometheus format if the registry and endpoint are configured.

Actual displayed metric names may be normalized by MeterRegistry. With Prometheus, metric names may differ from the original observation name due to naming and unit conversion rules.

In the trace backend, locate the graphql.request span and inspect child spans such as graphql.datafetcher, graphql.dataloader, or database client spans. If you only see the HTTP server span without GraphQL spans, check GraphQlObservationInstrumentation and ObservationRegistry. If GraphQL spans exist but lack the parent HTTP span, check transport instrumentation and context propagation.

### Questions to Answer When Investigating Slow Requests

| Question | Signals to inspect |
|---|---|
| Is the request slow inside GraphQL or before entering GraphQL? | Compare HTTP server observation and graphql.request |
| Which field consumes the most time? | graphql.datafetcher by field name/path |
| Is the batch loader grouping multiple keys? | graphql.dataloader and loader size |
| At which layer did the request fail? | graphql.outcome, error type, and span events |
| Is there a slow external service call? | Child spans of HTTP/database clients |
| Is trace context being lost? | Parent-child relationship and trace ID |

## 15. Protecting Metadata and Avoiding Cardinality Explosion

GraphQL requests can contain sensitive data in documents, variables, and error messages. Do not put the entire request into observation metadata.

Guidelines:

- Do not add raw GraphQL documents to metric tags.
- Do not add variable values such as emails, tokens, passwords, or personal information.
- Do not use user IDs, order IDs, or book IDs as low-cardinality keys.
- Only use operation type, outcome, loader name, or field name when the number of values is bounded.
- Keep operation name, execution ID, and field path in high-cardinality metadata per default convention.
- Check trace backend access permissions because high-cardinality values can still contain identifying data.
- Only record full errors in traces when logging and security policies permit.

If you need to track a group of customers or tenants, consider using a stable classification label instead of individual customer IDs as a metric dimension.

## 16. Common Errors with ObservationRegistry

| Symptom | Possible cause | Resolution |
|---|---|---|
| No graphql.request | GraphQlObservationInstrumentation is not registered | Check Spring Boot auto-configuration or GraphQlSource |
| Registry exists but no metrics appear | Missing meter handler or MeterRegistry exporter | Check Actuator, registry, and handler |
| Metrics exist but no traces | Micrometer Tracing bridge or exporter not configured | Configure tracing handler and backend |
| HTTP span exists but no GraphQL span | GraphQL instrumentation is inactive | Check ObservationRegistry and GraphQlObservationInstrumentation |
| GraphQL span has no HTTP parent | Transport did not propagate parent observation | Check HTTP instrumentation and context propagation |
| No graphql.datafetcher for every field | Trivial property fetchers are not instrumented | This is expected behavior; only non-trivial operations have observations |
| No graphql.dataloader | Using Spring GraphQL before 1.4 or operation does not invoke DataLoader | Check version and batch loader |
| Metrics backend has too many time series | Using IDs or continuously changing values as metric tags | Move that data to traces or remove from metadata |
| Custom convention is not used | Bean has wrong interface or auto-configuration cannot pick up bean | Check exact convention type and GraphQL auto-configuration |
| Trace splits during async execution | Context not propagated across executor or Reactor | Configure appropriate Context Propagation |
| Custom observation duration is too short | Wrapping reactive Publisher in synchronous observe | Use reactive-aware instrumentation or lifecycle |
| Observation appears twice | Both auto-configured and manually registered instrumentation | Keep only one instrumentation configuration for GraphQL |

## 17. Workflow for Implementing ObservationRegistry in GraphQL

When enabling observability for Spring for GraphQL:

1. Determine whether you need metrics, traces, or both.
2. Add Spring Boot Actuator and the corresponding registry/exporter.
3. Verify that ObservationRegistry is created in the application context.
4. Verify that GraphQlObservationInstrumentation is registered.
5. Send a representative query, mutation, and subscription.
6. Check graphql.request and its outcome.
7. Check graphql.datafetcher on resolvers that access services or databases.
8. If using DataLoader, check graphql.dataloader and batch size; requires Spring GraphQL 1.4 or later.
9. Add custom conventions only when new metadata is needed.
10. Review low-cardinality and high-cardinality keys before sending to the backend.
11. Verify context propagation across HTTP, GraphQL, Reactor, and executors.
12. Write integration tests verifying observations and error paths.
13. Check dashboards or the trace backend to confirm data is exported properly.

ObservationRegistry is the connection point between Spring for GraphQL instrumentation and Micrometer's metrics/tracing infrastructure. GraphQlObservationInstrumentation creates observations for the whole request, non-trivial DataFetchers, and DataLoaders; ObservationHandlers turn that lifecycle into Timers or spans. Configure the registry and handlers, keep low-cardinality metadata stable, propagate trace context properly across transports and reactive pipelines, and test both successful and error requests. With all three layers—request, field, and loader observations—operations teams can clearly pinpoint which GraphQL operation, resolver, or batch load is slow.

## References

- Spring for GraphQL — Observability: https://docs.spring.io/spring-graphql/reference/observability.html
- Spring for GraphQL — GraphQlObservationInstrumentation API: https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/observation/GraphQlObservationInstrumentation.html
- Spring Boot — Observability: https://docs.spring.io/spring-boot/reference/actuator/observability.html
- Micrometer — Observation introduction: https://docs.micrometer.io/micrometer/reference/observation/introduction.html
- Micrometer — Observation components: https://docs.micrometer.io/micrometer/reference/observation/components.html
