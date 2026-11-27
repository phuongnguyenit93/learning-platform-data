# Instrumentation Chain in Spring for GraphQL

GraphQL Java provides **Instrumentation** as an extension point to observe and customize the GraphQL operation lifecycle. An instrumentation can measure request duration, record errors, monitor DataFetcher invocations, validate queries prior to execution, or attach metadata to results.

In real-world applications, multiple concerns often coexist: metrics, tracing, auditing, query complexity limits, and custom validation rules. An **Instrumentation chain** lets you combine multiple instrumentations in a deterministic order instead of packing everything into one monolithic class.

Spring for GraphQL integrates this mechanism via **GraphQlSource.Builder**. With the Spring Boot GraphQL starter, you can declare each instrumentation as a bean; Boot automatically collects the beans according to Spring ordering and registers them when building `GraphQlSource`.

## 1. Where Does Instrumentation Sit in the GraphQL Lifecycle?

A request goes through the transport layer before reaching GraphQL Java:

~~~mermaid
flowchart TD
    A[HTTP / WebSocket / RSocket request] --> B[Transport handler]
    B --> C[WebGraphQlInterceptor chain]
    C --> D[ExecutionGraphQlService]
    D --> E[GraphQL Java]
    E --> F[Parse document]
    F --> G[Validate document]
    G --> H[Execute operation]
    H --> I[Resolve fields / DataFetcher]
    I --> J[Build ExecutionResult]
    J --> K[Transport response]
~~~

**WebGraphQlInterceptor** operates at the Spring transport layer, where it can read headers, populate `GraphQLContext`, or manipulate requests/responses before they are sent over the transport.

**Instrumentation** operates inside GraphQL Java. It can observe parsing, validation, execution, field fetching, and execution results. Therefore, instrumentation is suited for needs tied directly to the GraphQL engine, such as timing resolvers, limiting query depth, or adding execution metadata.

Other extension points have their own distinct scopes:

| Extension Point | Scope | When to Use |
| --- | --- | --- |
| `WebGraphQlInterceptor` | Request/response at the Spring transport layer | Authentication context, HTTP headers, correlation ID, web-layer response transformation. |
| `Instrumentation` | GraphQL Java execution lifecycle | Metrics, tracing, query validation, observing field fetches, modifying execution results. |
| `RuntimeWiringConfigurer` | Schema and runtime wiring initialization | Registering scalars, directives, DataFetchers, or wiring factories. |
| `DataFetcherExceptionResolver` | Exceptions originating in DataFetchers | Mapping exceptions to GraphQL errors. |
| `GraphQlSourceBuilderCustomizer` | Customizing the `GraphQlSource` builder in Spring Boot | Configuring advanced GraphQL Java builder or schema builder options. |

Do not use instrumentation as a replacement for authentication or authorization in services. Instrumentation can observe or wrap DataFetchers, but resource access checks should still be enforced in the security layer, services, or resolvers that own the business logic.

## 2. Which Steps Can Instrumentation Observe?

GraphQL Java defines numerous hooks in the **Instrumentation** interface. An instrumentation only needs to override the hooks relevant to its goal; the remaining hooks have default implementations.

| Hook | Timing | Example Purpose |
| --- | --- | --- |
| `createState` | Start of an execution | Create per-request state. |
| `beginExecution` | Start of execution | Measure total GraphQL execution duration. |
| `beginParse` | Before parsing the document | Track parse duration or parse failures. |
| `beginValidation` | Before validating the document | Track validation or apply extra checks. |
| `instrumentDocumentAndVariables` | Before the document and variables are used | Adjust the document/variables when there is a clear reason. |
| `beginExecutionStrategy` | Each time an execution strategy is invoked | Observe field-processing branches. |
| `beginFieldExecution` | Before a field is executed | Measure field execution duration. |
| `beginFieldFetching` | Before a DataFetcher retrieves a value | Observe data fetching. |
| `instrumentDataFetcher` | Before a DataFetcher is used | Wrap the DataFetcher to add observation or modification logic. |
| `instrumentExecutionResult` | Once `ExecutionResult` is available | Augment or transform result metadata. |

A single request can trigger hooks multiple times. For instance, `beginExecutionStrategy` is called as GraphQL Java traverses execution strategies; `beginFieldFetching` can run across many fields and many list elements.

Instrumentation should perform only the work necessary. A field-level hook may run tens or hundreds of times in a large request.

## 3. Three Core Components of Instrumentation

### Instrumentation

**Instrumentation** is the primary contract that GraphQL Java calls during an operation's lifecycle. You can implement this interface directly, though you should usually extend **SimplePerformantInstrumentation** to override only the hooks you need.

`SimplePerformantInstrumentation` provides lightweight default implementations for unused hooks. In modern codebases, prefer this class over `SimpleInstrumentation`, which is deprecated in recent GraphQL Java versions.

### InstrumentationContext

Hooks starting with `begin` typically return an **InstrumentationContext**. GraphQL Java invokes the context's callbacks when the corresponding step finishes.

Two key callbacks:

- `onDispatched`: the asynchronous step has been dispatched.
- `onCompleted`: the step has completed, carrying either the result or a `Throwable` if an error occurred.

This enables timing measurements without holding the request-processing thread. Completion callbacks may execute on a different thread than the one that started the step.

### InstrumentationState

**InstrumentationState** holds data belonging exclusively to one GraphQL execution. For example, it can store the start timestamp, field fetch counts, or request statistics.

Do not store request state in static fields or instance fields shared across all requests. GraphQL Java can execute fields concurrently, so per-request state must be managed per execution and be safe for multi-threaded access.

## 4. Writing an Execution Timing Instrumentation

The example below measures the time from when GraphQL execution starts until it finishes. It records whether the request had errors without logging queries or variables:

~~~java
import graphql.ExecutionResult;
import graphql.execution.instrumentation.InstrumentationContext;
import graphql.execution.instrumentation.InstrumentationState;
import graphql.execution.instrumentation.SimpleInstrumentationContext;
import graphql.execution.instrumentation.SimplePerformantInstrumentation;
import graphql.execution.instrumentation.parameters.InstrumentationExecutionParameters;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class RequestTimingInstrumentation extends SimplePerformantInstrumentation {

    private static final Logger log =
            LoggerFactory.getLogger(RequestTimingInstrumentation.class);

    @Override
    public InstrumentationContext<ExecutionResult> beginExecution(
            InstrumentationExecutionParameters parameters,
            InstrumentationState state) {

        long startedAt = System.nanoTime();

        return new SimpleInstrumentationContext<>() {
            @Override
            public void onCompleted(ExecutionResult result, Throwable throwable) {
                long elapsedNanos = System.nanoTime() - startedAt;

                boolean failed = throwable != null
                        || (result != null && !result.getErrors().isEmpty());

                log.debug(
                        "GraphQL execution completed in {} ns, failed={}",
                        elapsedNanos,
                        failed);
            }
        };
    }
}
~~~

In this example:

- `beginExecution` is called when GraphQL execution starts.
- `System.nanoTime` measures elapsed duration; do not use `currentTimeMillis` for durations.
- `SimpleInstrumentationContext` receives a callback when execution completes.
- `Throwable` indicates an execution-step failure; `ExecutionResult` can contain GraphQL errors even without a `Throwable`.
- Neither queries, variables, authorization headers, nor business data are written to the logs.

This is a request-wide instrumentation. If you need to identify which specific field is slow, you can override hooks at the field-fetch level, while weighing the overhead since callback volume scales with resolved fields.

## 5. Composing Multiple Instrumentations with ChainedInstrumentation

GraphQL Java provides **ChainedInstrumentation** to combine multiple implementations. Its constructor accepts a `List` or varargs and invokes the instrumentations in the supplied order.

Example of building a chain directly with GraphQL Java:

~~~java
import graphql.GraphQL;
import graphql.execution.instrumentation.ChainedInstrumentation;
import graphql.execution.instrumentation.Instrumentation;

import java.util.List;

Instrumentation chain = new ChainedInstrumentation(List.of(
        new RequestTimingInstrumentation(),
        new QueryAuditInstrumentation(),
        new QueryLimitInstrumentation()
));

GraphQL graphQL = GraphQL.newGraphQL(schema)
        .instrumentation(chain)
        .build();
~~~

The example assumes `QueryAuditInstrumentation` and `QueryLimitInstrumentation` are implementations provided by the application.

The order in the list is guaranteed. When a hook is invoked, the instrumentations in the chain are called in that order. The state created by each instrumentation is passed back to that same instrumentation; each component still manages its own state.

You can visualize it as follows:

~~~mermaid
flowchart TD
    A[GraphQL execution] --> B[RequestTimingInstrumentation]
    B --> C[QueryAuditInstrumentation]
    C --> D[QueryLimitInstrumentation]
    D --> E[GraphQL engine continues]
    E --> F[InstrumentationContext callbacks]
~~~

Do not assume completion callback order always matches start order across every hook. Rely on each hook's callback contract and test the chain if one instrumentation depends on outcomes produced by another.

## 6. Registering Instrumentation in Spring Boot

With the Spring Boot GraphQL starter, you can declare each instrumentation as a bean:

~~~java
import graphql.execution.instrumentation.Instrumentation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

@Configuration(proxyBeanMethods = false)
public class GraphQlInstrumentationConfiguration {

    @Bean
    @Order(10)
    Instrumentation requestTimingInstrumentation() {
        return new RequestTimingInstrumentation();
    }

    @Bean
    @Order(20)
    Instrumentation queryAuditInstrumentation() {
        return new QueryAuditInstrumentation();
    }

    @Bean
    @Order(30)
    Instrumentation queryLimitInstrumentation() {
        return new QueryLimitInstrumentation();
    }
}
~~~

The Spring Boot GraphQL starter automatically detects beans of type **Instrumentation** and registers them with **GraphQlSource.Builder**. Beans are collected in Spring order, so you can use `@Order` or `Ordered` to control ordering.

With this approach:

- You do not need to construct a `GraphQL` instance manually.
- You do not need to declare a `ChainedInstrumentation` bean wrapping the instrumentation components.
- Each instrumentation is an independent bean, easy to test and swap.
- Spring Boot integrates these instrumentations when constructing `GraphQlSource`.

If the application already declares its own `GraphQlSource` bean, default auto-configuration may no longer create `GraphQlSource`. In that case, the application must register the instrumentations on its own builder.

## 7. Registering via GraphQlSource.Builder Without Boot Auto-Configuration

Spring for GraphQL provides the **instrumentation(List<Instrumentation>)** method on `GraphQlSource.Builder`.

Example of building `GraphQlSource` manually:

~~~java
import graphql.execution.instrumentation.Instrumentation;
import org.springframework.core.io.ClassPathResource;
import org.springframework.graphql.execution.GraphQlSource;

import java.util.List;

GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
        .schemaResources(new ClassPathResource("graphql/schema.graphqls"))
        .instrumentation(List.of(
                new RequestTimingInstrumentation(),
                new QueryAuditInstrumentation(),
                new QueryLimitInstrumentation()))
        .build();
~~~

This snippet illustrates the instrumentation configuration; a real application also needs `RuntimeWiringConfigurer`, exception resolvers, and any other schema configurations.

If you want to work directly with the GraphQL Java builder, you can use `configureGraphQl`:

~~~java
builder.configureGraphQl(graphQLBuilder ->
        graphQLBuilder.instrumentation(
                new ChainedInstrumentation(List.of(
                        new RequestTimingInstrumentation(),
                        new QueryAuditInstrumentation()))));
~~~

Choose a single registration approach that matches how your application builds `GraphQlSource`. Do not add the same instrumentation both through `GraphQlSource.Builder`'s instrumentation list and through a custom `ChainedInstrumentation` if doing so causes the component to run twice.

## 8. What Does Chain Ordering Affect?

Ordering matters when multiple instrumentations observe or modify the same execution.

Example:

| Order | Instrumentation | Goal |
| --- | --- | --- |
| 1 | `RequestTimingInstrumentation` | Start timing the total request duration. |
| 2 | `QueryAuditInstrumentation` | Record safe operation metadata. |
| 3 | `QueryLimitInstrumentation` | Enforce query limits before resolvers execute. |
| 4 | GraphQL engine | Continue execution if the request is accepted. |

Guidelines for ordering:

- Place checks that can reject requests before expensive work begins.
- Place timing instrumentations so they enclose the full scope to be measured.
- If an instrumentation modifies the GraphQL document or variables, understand that downstream components will see the modified data.
- Do not rely on implicit bean discovery order; declare `@Order` whenever order matters.
- Do not introduce circular dependencies between instrumentations via shared mutable state.

An instrumentation chain is not a message-broker pipeline. Components are invoked through GraphQL Java hooks; each hook has its own lifecycle and may be invoked multiple times.

## 9. Using Built-in Instrumentations to Limit Queries

GraphQL Java provides several useful instrumentations for validation and resource limits:

| Instrumentation | Purpose |
| --- | --- |
| `FieldValidationInstrumentation` | Validate fields and arguments before the query executes. |
| `MaxQueryDepthInstrumentation` | Reject queries exceeding a maximum depth. |
| `MaxQueryComplexityInstrumentation` | Reject queries exceeding a calculated complexity limit. |

GraphQL Java example:

~~~java
import graphql.analysis.MaxQueryComplexityInstrumentation;
import graphql.analysis.MaxQueryDepthInstrumentation;
import graphql.execution.instrumentation.ChainedInstrumentation;
import graphql.execution.instrumentation.Instrumentation;

import java.util.List;

Instrumentation queryProtection = new ChainedInstrumentation(List.of(
        new MaxQueryDepthInstrumentation(8),
        new MaxQueryComplexityInstrumentation(200)));
~~~

Depth and complexity limits should be tuned based on the schema and the actual cost of DataFetchers. A shallow query field can still be very expensive; conversely, a deep query that only reads lightweight data may consume minimal resources.

If the application uses a custom complexity calculator, assign appropriate weights to fields that query databases, call external services, or return large lists. Query limits do not replace pagination, rate limiting, timeouts, or authorization.

## 10. Micrometer Observation Integration

Spring for GraphQL provides **GraphQlObservationInstrumentation** to emit observations for requests and tracked DataFetcher/DataLoader activity.

Common observations:

| Observation | Scope |
| --- | --- |
| `graphql.request` | The entire GraphQL request. |
| `graphql.datafetcher` | Non-trivial DataFetcher activity. |
| `graphql.dataloader` | DataLoader activity, including `@BatchMapping` and manually registered DataLoaders. |

Observations are only emitted when the application has an appropriate `ObservationRegistry`. Metadata can be customized through the corresponding observation conventions.

If the system already uses `GraphQlObservationInstrumentation`, check existing metrics/traces before writing a custom instrumentation measuring the same scope. Custom instrumentations should fill in missing signals rather than duplicating metrics.

Watch out for cardinality:

- Operation type and outcome are typically low-cardinality tags.
- Operation name, field path, or query text can have high cardinality.
- Do not put variables, tokens, emails, user IDs, or raw queries into metric tags.
- Record only classified and approved metadata.

## 11. Differences Between Instrumentation and WebGraphQlInterceptor

These two extension points are frequently confused because both run around a GraphQL request.

| Requirement | Recommended Choice |
| --- | --- |
| Reading an HTTP Authorization header | `WebGraphQlInterceptor` or Spring Security. |
| Putting a tenant ID into `GraphQLContext` from transport | `WebGraphQlInterceptor`. |
| Timing GraphQL execution | `Instrumentation`. |
| Timing a field DataFetcher | `Instrumentation`. |
| Checking query depth/complexity before execution | Appropriate `Instrumentation`. |
| Translating resolver exceptions into GraphQL errors | `DataFetcherExceptionResolver`. |
| Registering scalars or directives | `RuntimeWiringConfigurer`. |
| Modifying HTTP response headers | Transport handler/interceptor. |
| Adding metadata to `ExecutionResult` | `Instrumentation` or appropriate GraphQL result mechanism. |

`WebGraphQlInterceptor` can process both requests and responses at the Spring layer. `Instrumentation` focuses on GraphQL Java execution, so it is not the right place to read or modify HTTP response headers.

## 12. Using InstrumentationState Safely with Concurrency

GraphQL Java commonly uses `AsyncExecutionStrategy` so nested fields can be resolved concurrently. Consequently, instrumentation must never assume all callbacks run on the same thread.

If you need to count field fetches within a request, the state can use `AtomicInteger`:

~~~java
import graphql.execution.instrumentation.InstrumentationState;

import java.util.concurrent.atomic.AtomicInteger;

public class RequestInstrumentationState implements InstrumentationState {

    private final AtomicInteger fieldFetchCount = new AtomicInteger();

    public void recordFieldFetch() {
        fieldFetchCount.incrementAndGet();
    }

    public int getFieldFetchCount() {
        return fieldFetchCount.get();
    }
}
~~~

This state must be created per execution, not as a singleton shared across requests. When hooks are invoked from multiple threads, use thread-safe structures or proper synchronization.

Avoid:

- Storing request-specific state in static mutable fields.
- Using an unsynchronized `HashMap` written concurrently by multiple field resolvers.
- Relying on `ThreadLocal` without handling thread switching.
- Blocking threads to wait for a `CompletableFuture` or `Publisher` to finish.
- Retaining references to `DataFetchingEnvironment` or request objects beyond their needed lifetime.

## 13. Being Careful When Wrapping DataFetchers

The **instrumentDataFetcher** hook lets you return a different DataFetcher in place of the original one. This is a powerful capability, but it requires care.

A wrapper must preserve the behavior of the original DataFetcher:

- Return the exact result or `CompletionStage` produced by the resolver.
- Never block waiting for a future to complete.
- Preserve exception semantics so `DataFetcherExceptionHandler` handles them properly.
- Avoid losing required metadata or context.
- Avoid running side effects multiple times if the wrapper is created or invoked repeatedly.

For example, a wrapper that only records when a DataFetcher is invoked may have to handle synchronous return values, `CompletionStage`s, and exceptions. For straightforward metrics goals, the `beginFieldFetching` hook is often easier to manage than writing a custom wrapper.

## 14. Instrumentation and GraphQLContext

Instrumentation can read or add data to `GraphQLContext` through the execution parameters. Spring for GraphQL also supports propagating context from the transport through GraphQL Java down to DataFetchers.

Example of Spring for GraphQL using a custom instrumentation to enable ordered subscription events:

~~~java
import graphql.ExecutionResult;
import graphql.execution.SubscriptionExecutionStrategy;
import graphql.execution.instrumentation.InstrumentationContext;
import graphql.execution.instrumentation.InstrumentationState;
import graphql.execution.instrumentation.SimpleInstrumentationContext;
import graphql.execution.instrumentation.SimplePerformantInstrumentation;
import graphql.execution.instrumentation.parameters.InstrumentationExecutionParameters;

public class SubscriptionOrderInstrumentation extends SimplePerformantInstrumentation {

    @Override
    public InstrumentationContext<ExecutionResult> beginExecution(
            InstrumentationExecutionParameters parameters,
            InstrumentationState state) {

        parameters.getGraphQLContext().put(
                SubscriptionExecutionStrategy.KEEP_SUBSCRIPTION_EVENTS_ORDERED,
                true);

        return SimpleInstrumentationContext.noOp();
    }
}
~~~

This configures execution behavior in GraphQL Java. It does not by itself guarantee message ordering across every transport or across multiple instances; it controls how GraphQL Java processes subscription events within the execution scope.

## 15. Instrumentation Is Not Ideal for Holding Long Transactions Across Every Request

You can use instrumentation to open a transaction before the first DataFetcher runs and close it after execution finishes. However, this is an advanced technique with significant constraints.

With synchronous transaction management, Spring typically uses `ThreadLocal` to bind a transaction to a thread. Meanwhile, GraphQL Java usually resolves fields concurrently via `AsyncExecutionStrategy` and may hop across multiple threads.

If you want to hold a single synchronous transaction across an entire GraphQL execution, you must ensure DataFetchers execute sequentially on the same thread—for instance, using `AsyncSerialExecutionStrategy`. This sacrifices parallel execution benefits and can severely impact throughput.

Therefore:

- Prefer transactions in application services or mutation methods.
- Use transactional instrumentation only when a request-wide transaction scope is genuinely required.
- If using reactive transactions, follow Reactor Context and `ReactiveTransactionManager`; do not rely on `ThreadLocal`.
- Ensure commit/rollback and transaction cleanup when execution finishes, including on exceptions or cancellation.
- Test nested field failures, subscriptions, timeouts, and async DataFetchers.

## 16. Testing the Instrumentation Chain

You should test each instrumentation individually as well as the composed chain.

### Testing a Single Instrumentation

For `RequestTimingInstrumentation`, you can verify:

- `beginExecution` is called when GraphQL execution starts.
- The `onCompleted` callback is invoked when execution finishes.
- Requests with GraphQL errors record the appropriate outcome.
- A `Throwable` is handled when execution ends abnormally.
- The instrumentation does not alter response data or errors.

### Testing Chain Ordering

Create two test instrumentations that record their hook names into a thread-safe `List`, run a GraphQL operation, and assert that the invocation order matches the chain list.

When testing asynchronous callbacks or multiple fields, do not share an `ArrayList` across threads; use a synchronized collection or a thread-safe queue.

### Spring GraphQL Integration Testing

You can use `GraphQlTester` to send operations through `ExecutionGraphQlService` or a transport test:

~~~java
graphQlTester.document("""
        query {
            bookById(id: "book-10") {
                id
                title
            }
        }
        """)
        .execute()
        .path("bookById.id")
        .entity(String.class)
        .isEqualTo("book-10");
~~~

Beyond verifying the data is correct, tests should confirm that the instrumentation was registered in `GraphQlSource`. With Spring Boot, you can inject a test recorder or mock dependency used by the instrumentation to confirm hooks ran.

Scenarios to cover:

1. Valid request flowing through the entire chain.
2. Request failing parse/validation.
3. DataFetcher throwing an exception.
4. Query exceeding depth or complexity limits.
5. Multiple instrumentations invoked in configured order.
6. Concurrent requests without shared state leakage.
7. Subscription emitting multiple events.
8. Instrumentation not dropping `GraphQLContext` or unexpectedly altering responses.

## 17. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Instrumentation does not run | Not registered with `GraphQlSource` or `GraphQL.Builder` | Check bean discovery and `GraphQlSource.Builder.instrumentation`. |
| Instrumentation runs twice | Component registered through multiple paths | Register only once in the active `GraphQlSource`. |
| Hook order does not match expectations | Missing `@Order` or wrong chain list order | Use `@Order`/`Ordered` or an explicit list. |
| Metrics are double-counted | Using `GraphQlObservationInstrumentation` alongside a custom metric for the same scope | Inspect existing observations and add only missing metrics. |
| State leaks across requests | Using shared instance fields or static fields | Create state scoped to each execution. |
| Race condition counting fields | Multiple DataFetchers running concurrently | Use `AtomicInteger` or thread-safe data structures. |
| Requests slow down after adding chain | Hook performs I/O or blocking work | Keep instrumentation lightweight, non-blocking, and limit logging. |
| DataFetcher returns different errors than before | Wrapper changed exception/future behavior | Preserve return types and exception semantics. |
| Logs contain queries or secrets | Logging raw document/variables in instrumentation | Log only allowlisted metadata; avoid payloads and credentials. |
| Transaction hangs or runs on wrong thread | Using synchronous transactions across async execution | Prefer per-service transactions or controlled sequential execution strategy. |
| Subscription events arrive out of order | Event fields are resolved asynchronously | Configure `KEEP_SUBSCRIPTION_EVENTS_ORDERED` if ordering is required in GraphQL Java. |

## 18. Instrumentation Chain Design Checklist

1. Identify the required hooks: request, parse, validation, field fetch, or execution result.
2. Use `SimplePerformantInstrumentation` for standard custom implementations.
3. Use `InstrumentationContext` to handle asynchronous completion callbacks.
4. Use `InstrumentationState` for per-execution data.
5. Compose components with `ChainedInstrumentation` when configuring GraphQL Java directly.
6. Use `Instrumentation` beans and `@Order` when integrating with Spring Boot.
7. If creating `GraphQlSource` manually, register the list via `GraphQlSource.Builder.instrumentation(...)`.
8. Avoid registering the same component twice through multiple paths.
9. Use built-in instrumentations for field validation, query depth, and query complexity where appropriate.
10. Consider `GraphQlObservationInstrumentation` before writing custom metrics/tracing.
11. Never use instrumentation as a substitute for authentication, authorization, or `DataFetcherExceptionResolver`.
12. Ensure thread safety and avoid blocking in callbacks.
13. Do not log raw queries, variables, headers, or sensitive data.
14. Test chain order, errors, concurrency, subscriptions, and state isolation.
15. Use request-wide transactional instrumentation only when you fully understand the execution strategy and transaction context.

An instrumentation chain breaks GraphQL Java cross-cutting concerns into independent components. GraphQL Java provides `ChainedInstrumentation` to compose them in order; Spring Boot registers each component through `Instrumentation` beans and `GraphQlSource.Builder`. By choosing the right hooks, scoping state per request, keeping callbacks lightweight, and testing ordering/concurrency, instrumentation adds observability and execution control without cluttering business resolvers.

References:
- [GraphQL Java — Instrumentation](https://graphql-java.com/documentation/instrumentation/)
- [GraphQL Java — ChainedInstrumentation API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/instrumentation/ChainedInstrumentation.html)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — GraphQlSource.Builder API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/GraphQlSource.Builder.html)
- [Spring for GraphQL — Observability](https://docs.spring.io/spring-graphql/reference/observability.html)
- [Spring for GraphQL — Data Integration and Transactional Instrumentation](https://docs.spring.io/spring-graphql/reference/data.html)
