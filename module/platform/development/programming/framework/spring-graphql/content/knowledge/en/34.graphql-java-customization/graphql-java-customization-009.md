# ExecutionStrategy in Spring for GraphQL

GraphQL Java uses **ExecutionStrategy** to determine how fields are fetched and completed within an operation. The strategy coordinates invoking DataFetchers, awaiting asynchronous results, handling errors, and assembling results into the GraphQL structure.

The three default strategies serve distinct roles:

- **AsyncExecutionStrategy** for Queries: allows sibling fields to execute asynchronously and potentially concurrently.
- **AsyncSerialExecutionStrategy** for Mutations: executes mutation root fields sequentially in the order they appear in the document.
- **SubscriptionExecutionStrategy** for Subscriptions: handles Reactive Streams publishers and produces one GraphQL response per emitted event.

Spring for GraphQL delegates to GraphQL Java's strategies. When customization is needed, applications can configure them through `GraphQlSource` or `GraphQlSourceBuilderCustomizer`. Replacing a strategy must preserve the semantics of each operation type and continue using Spring's configured `DataFetcherExceptionHandler` so exception resolvers function as expected.

## 1. What Is ExecutionStrategy?

`ExecutionStrategy` is the GraphQL Java component responsible for orchestrating selection set execution. A selection set is the group of fields requested by a client on an object.

Example:

~~~graphql
query Dashboard {
    dashboard {
        profile {
            displayName
        }
        notifications {
            id
            message
        }
        recommendations {
            id
            title
        }
    }
}
~~~

GraphQL Java must resolve the `dashboard` field first to obtain the parent object. Once the `dashboard` object is available, the `profile`, `notifications`, and `recommendations` fields can be processed according to the active strategy. When a field returns an object or a list of objects, the engine continues completing the selected child fields.

`ExecutionStrategy` coordinates two primary phases:

1. **Fetch**: invoke the field's `DataFetcher` to retrieve a Java value.
2. **Complete**: convert that value into the appropriate GraphQL form—such as a scalar, enum, list, or object; for objects, the engine recursively resolves child fields.

High-level diagram:

~~~mermaid
flowchart TD
    A[GraphQL operation] --> B[ExecutionStrategy.execute]
    B --> C[Collect selection set]
    C --> D[Fetch field via DataFetcher]
    D --> E[Complete field value]
    E --> F{Result type}
    F -->|Scalar / Enum| G[Coerce value]
    F -->|List| H[Complete each element]
    F -->|Object| I[Resolve child selection set]
    H --> J[Build ExecutionResult]
    G --> J
    I --> J
~~~

`ExecutionStrategy` does not contain database access or service-invocation logic. Those belong in DataFetchers, controllers, or application services. The strategy governs how the engine coordinates DataFetchers and their outputs.

## 2. The Three Default Strategies

GraphQL Java applies a different strategy for each operation type:

| Operation | Default Strategy | Behavior |
| --- | --- | --- |
| Query | `AsyncExecutionStrategy` | Sibling fields can be dispatched asynchronously; results are assembled in document field order. |
| Mutation | `AsyncSerialExecutionStrategy` | Root fields run sequentially; the next field is dispatched only after the previous one completes. |
| Subscription | `SubscriptionExecutionStrategy` | The subscription DataFetcher creates a publisher; each event is turned into a GraphQL response. |

They can be configured directly on `GraphQL.Builder`:

~~~java
import graphql.GraphQL;
import graphql.execution.AsyncExecutionStrategy;
import graphql.execution.AsyncSerialExecutionStrategy;
import graphql.execution.SubscriptionExecutionStrategy;

GraphQL graphQL = GraphQL.newGraphQL(schema)
        .queryExecutionStrategy(new AsyncExecutionStrategy())
        .mutationExecutionStrategy(new AsyncSerialExecutionStrategy())
        .subscriptionExecutionStrategy(new SubscriptionExecutionStrategy())
        .build();
~~~

These are GraphQL Java's standard strategies and correspond to the typical defaults. In a Spring for GraphQL application, you usually do not construct the `GraphQL` instance manually; configure strategies via `GraphQlSource`.

## 3. Query: AsyncExecutionStrategy

Queries are read operations. According to the GraphQL specification, fields within a Query selection set may execute in any order, typically in parallel, because Query field resolution should not produce side effects that mutate business state.

Consider the query:

~~~graphql
query {
    dashboard {
        profile {
            displayName
        }
        notifications {
            id
        }
        recommendations {
            id
        }
    }
}
~~~

The `dashboard` field must return its object first. Afterward, child fields `profile`, `notifications`, and `recommendations` can be dispatched without waiting on one another. If each DataFetcher returns a `CompletionStage`, GraphQL Java composes the futures to complete the response.

~~~mermaid
flowchart TD
    A[Fetch dashboard] --> B[Dashboard object available]
    B --> C[Fetch profile]
    B --> D[Fetch notifications]
    B --> E[Fetch recommendations]
    C --> F[Wait for all results]
    D --> F
    E --> F
    F --> G[Assemble response in document field order]
~~~

A common misconception: **fetch order does not necessarily match JSON field order**. DataFetchers may finish in arbitrary order, yet GraphQL Java still assembles the response object following the document's field order.

### Query does not mean every field runs on its own thread

`AsyncExecutionStrategy` enables the engine to coordinate asynchronous results. It does not automatically turn a blocking DataFetcher into a non-blocking one, nor does it mean every field always runs on a separate thread.

If a DataFetcher makes a synchronous blocking JDBC call before returning, that call still holds the current thread. To achieve asynchronous I/O, use non-blocking APIs or return a `CompletionStage`/`Publisher` suited to your application stack.

Never rely on Query concurrency to perform write operations. Query fields must be designed as read-only, side-effect-free, and idempotent.

## 4. Mutation: AsyncSerialExecutionStrategy

The GraphQL specification mandates that root fields of a Mutation operation execute sequentially in the order they appear in the document.

Example:

~~~graphql
mutation Checkout {
    reserveInventory(orderId: "order-10") {
        reservationId
    }
    chargePayment(orderId: "order-10") {
        paymentId
    }
    confirmOrder(orderId: "order-10") {
        id
        status
    }
}
~~~

GraphQL Java must finish `reserveInventory` before dispatching `chargePayment`, and finish `chargePayment` before dispatching `confirmOrder`.

~~~mermaid
flowchart TD
    A[Mutation operation] --> B[reserveInventory]
    B --> C[Wait for field completion]
    C --> D[chargePayment]
    D --> E[Wait for field completion]
    E --> F[confirmOrder]
    F --> G[Build mutation response]
~~~

`AsyncSerialExecutionStrategy` still supports asynchronous results. The `Async` prefix does not mean root mutation fields run concurrently; it means the strategy can await a `CompletionStage` without blocking a thread while waiting, while still dispatching the next root field sequentially.

### Scope of sequential execution for Mutations

The sequential rule applies to root fields within the same Mutation operation. It does NOT mean:

- Every nested child field on every returned object runs sequentially.
- All mutation requests across the entire system are serialized under a global lock.
- Requests from two different clients are serialized.
- Root fields inside one operation automatically share the same database transaction.
- A multi-field mutation operation automatically forms an atomic business use case.

If a client sends two concurrent HTTP mutation requests, the server can still process them in parallel. To protect data against competing requests, use transactions, locking, optimistic versioning, or appropriate synchronization at the business layer.

### Sequential does not mean atomic

Consider an operation with two root fields:

~~~graphql
mutation {
    createOrder(input: { customerId: "c-1" }) {
        id
    }
    reserveInventory(orderId: "order-10") {
        reservationId
    }
}
~~~

The strategy guarantees `createOrder` runs before `reserveInventory`. However, GraphQL does not automatically open a shared database transaction spanning both fields. If `createOrder` commits and `reserveInventory` then fails, the created order data may remain persisted.

If two steps must succeed or roll back together, design a single mutation invoking an application service that runs the entire use case within one transaction.

## 5. Subscription: SubscriptionExecutionStrategy

Subscriptions differ from Queries and Mutations in that the root subscription DataFetcher typically returns a `Publisher` rather than a single value.

Example schema:

~~~graphql
type Subscription {
    orderUpdated(orderId: ID!): OrderEvent!
}

type OrderEvent {
    orderId: ID!
    status: String!
    occurredAt: String!
}
~~~

Spring for GraphQL controller:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class OrderSubscriptionController {

    private final OrderEventService eventService;

    public OrderSubscriptionController(OrderEventService eventService) {
        this.eventService = eventService;
    }

    @SubscriptionMapping
    public Flux<OrderEvent> orderUpdated(@Argument String orderId) {
        return eventService.events(orderId);
    }
}
~~~

`SubscriptionExecutionStrategy` sets up the subscription source and processes emitted events. Each event object is completed against the subscription's selection set to produce a GraphQL response.

~~~mermaid
flowchart TD
    A[Client subscribes] --> B[Execute subscription root field]
    B --> C[DataFetcher returns Publisher]
    C --> D[Transport subscribes]
    D --> E[Publisher emits event]
    E --> F[Resolve selected fields for event]
    F --> G[Send GraphQL event response]
    G --> E
    E -->|Publisher complete| H[End stream]
    E -->|Publisher error| I[Terminal subscription error]
~~~

Do not replace `SubscriptionExecutionStrategy` with `AsyncExecutionStrategy` merely for configuration uniformity. The subscription strategy must preserve Reactive Streams behavior and how GraphQL Java turns events into responses. If customizing the subscription strategy, extend or preserve the semantics of `SubscriptionExecutionStrategy`.

A field error inside an individual event and a terminal error on the `Publisher` are two distinct situations. `DataFetcherExceptionResolver` handles errors during field resolution; `SubscriptionExceptionResolver` handles errors when the subscription publisher emits an `onError` signal after the stream is established.

## 6. How Do DataFetcher and ExecutionStrategy Collaborate?

`DataFetcher` is responsible for retrieving data for a field. `ExecutionStrategy` invokes the DataFetcher, receives its return value, and completes that value according to the GraphQL type.

A DataFetcher can return:

- A synchronous value, such as `Book` or `List<Book>`.
- A `CompletionStage`, such as `CompletableFuture<Book>`.
- A `DataFetcherResult` to return data alongside GraphQL errors or local context.
- In Spring for GraphQL, controllers can return supported reactive types such as `Mono` or `Flux` depending on the mapping type.

Example DataFetcher returning a `CompletionStage`:

~~~java
DataFetcher<Book> bookFetcher = environment -> {
    String id = environment.getArgument("id");

    return bookService.findByIdAsync(id);
};
~~~

If the service returns `CompletionStage<Book>`, `AsyncExecutionStrategy` coordinates that result with other fields. There is no need to call `join()` or `get()` manually to await future completion.

Example using a bounded executor when wrapping a blocking API:

~~~java
DataFetcher<Book> bookFetcher = environment -> {
    String id = environment.getArgument("id");

    return CompletableFuture.supplyAsync(
            () -> legacyBookService.findById(id),
            bookLookupExecutor);
};
~~~

The `bookLookupExecutor` must be sized with thread counts and queue capacities appropriate for system load. Never use an unbounded executor or overload `ForkJoinPool.commonPool` for arbitrary blocking tasks.

In WebFlux applications, prefer non-blocking APIs like `WebClient` and reactive repositories instead of offloading every blocking call into `CompletableFuture`.

## 7. AsyncExecutionStrategy Does Not Provide Free Concurrency

Three layers must be distinguished:

| Component | Responsibility |
| --- | --- |
| `ExecutionStrategy` | Decides how fields are dispatched, coordinated, and completed. |
| `DataFetcher` | Retrieves data for a field; can be synchronous or asynchronous. |
| Executor / reactive runtime | Executes async work on concrete thread/event-loop resources. |

`AsyncExecutionStrategy` allows independent fields to progress without waiting sequentially for prior fields. However, if all DataFetchers execute blocking JDBC calls on the same thread, I/O wait time still ties up that thread.

To gain real concurrency benefits:

- Return `CompletionStage` or reactive types when data sources support them.
- Use a bounded executor when calling blocking APIs is unavoidable.
- Configure timeouts on service and database calls.
- Bound concurrency so connection pools or downstream services are not overwhelmed.
- Never call `block()`, `join()`, or `get()` on an event-loop thread.
- Monitor per-operation and per-field latency to find actual bottlenecks.

## 8. DataLoader and Batching Under Different Strategies

`DataLoader` batches multiple reads of the same kind into a single batch call. `ExecutionStrategy` coordinates when DataLoaders are dispatched during field resolution.

Example query fetching multiple orders and their customers:

~~~graphql
query {
    orders {
        id
        customer {
            id
            name
        }
    }
}
~~~

If every `customer` field hits the database individually, the application can generate N+1 queries. `DataLoader` collects customer IDs and loads them in a batch.

`ExecutionStrategy` does not replace `DataLoader`. The strategy orchestrates field execution; `DataLoader` batches loads sharing the same loader key within an execution context. When customizing a strategy, re-test dispatch behavior to verify batching still works.

In particular, switching Queries from async to serial can alter when fields are dispatched and shrink batch sizes. Never change strategies solely to control order without measuring the impact on `DataLoader` and latency.

## 9. Exception Handling Tied to ExecutionStrategy

`ExecutionStrategy` requires a `DataFetcherExceptionHandler` to handle exceptions thrown by DataFetchers.

GraphQL Java defaults to `SimpleDataFetcherExceptionHandler`. This handler converts exceptions into GraphQL errors, attaches path/location, and includes them in the response. GraphQL permits partial data alongside errors; one failing field does not necessarily fail the entire operation.

Spring for GraphQL provides `DataFetcherExceptionResolver` and `@GraphQlExceptionHandler` to map exceptions according to application rules. Spring constructs a `DataFetcherExceptionHandler` from the resolver list and registers it on `GraphQL.Builder`.

When instantiating a custom `ExecutionStrategy`, pass the handler built from Spring's resolver list. Using the strategy's no-arg constructor can fall back to GraphQL Java's `SimpleDataFetcherExceptionHandler` and bypass Spring's configured error mappings.

## 10. Customizing ExecutionStrategy in Spring Boot

Spring for GraphQL provides `GraphQlSourceBuilderCustomizer` to customize `GraphQL.Builder` while preserving Boot auto-configuration.

The following example creates a custom strategy for Queries while keeping Mutations sequential and sharing Spring's exception handler:

~~~java
import graphql.ExecutionResult;
import graphql.execution.AsyncExecutionStrategy;
import graphql.execution.AsyncSerialExecutionStrategy;
import graphql.execution.DataFetcherExceptionHandler;
import graphql.execution.ExecutionContext;
import graphql.execution.ExecutionStrategyParameters;
import graphql.execution.NonNullableFieldWasNullException;

import java.util.concurrent.CompletableFuture;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.DataFetcherExceptionResolver;
// Spring Boot 3.x; for Spring Boot 4.x, use package org.springframework.boot.graphql.autoconfigure.
import org.springframework.boot.autoconfigure.graphql.GraphQlSourceBuilderCustomizer;

@Configuration(proxyBeanMethods = false)
public class GraphQlExecutionStrategyConfiguration {

    @Bean
    GraphQlSourceBuilderCustomizer executionStrategyCustomizer(
            ObjectProvider<DataFetcherExceptionResolver> resolvers) {

        DataFetcherExceptionHandler exceptionHandler =
                DataFetcherExceptionResolver.createExceptionHandler(
                        resolvers.orderedStream().toList());

        AsyncExecutionStrategy queryStrategy =
                new TimedQueryExecutionStrategy(exceptionHandler);

        AsyncSerialExecutionStrategy mutationStrategy =
                new AsyncSerialExecutionStrategy(exceptionHandler);

        return builder -> builder.configureGraphQl(graphQLBuilder ->
                graphQLBuilder
                        .queryExecutionStrategy(queryStrategy)
                        .mutationExecutionStrategy(mutationStrategy));
    }

    static class TimedQueryExecutionStrategy extends AsyncExecutionStrategy {

        private static final Logger log =
                LoggerFactory.getLogger(TimedQueryExecutionStrategy.class);

        TimedQueryExecutionStrategy(DataFetcherExceptionHandler exceptionHandler) {
            super(exceptionHandler);
        }

        @Override
        public CompletableFuture<ExecutionResult> execute(
                ExecutionContext executionContext,
                ExecutionStrategyParameters parameters)
                throws NonNullableFieldWasNullException {

            long startedAt = System.nanoTime();

            return super.execute(executionContext, parameters)
                    .whenComplete((result, error) ->
                            log.debug("Query execution completed in {} ms, failed={}",
                                    (System.nanoTime() - startedAt) / 1_000_000,
                                    error != null
                                            || (result != null && !result.getErrors().isEmpty())));
        }
    }
}
~~~

This example illustrates the key integration points:

- `ObjectProvider` retrieves all registered `DataFetcherExceptionResolver` beans.
- `createExceptionHandler` constructs a handler backed by Spring's resolver list.
- Queries use a custom strategy extending `AsyncExecutionStrategy`.
- Mutations continue using `AsyncSerialExecutionStrategy`.
- Both strategies receive the same handler so application exception mappings remain intact.

The package of `GraphQlSourceBuilderCustomizer` depends on the Spring Boot major version. In Spring Boot 3.x, the interface lives in `org.springframework.boot.autoconfigure.graphql`. In Spring Boot 4.x, the package is `org.springframework.boot.graphql.autoconfigure`. Use the package matching your dependency version.

This snippet only illustrates timing inside a Query strategy. If your sole goal is metrics/tracing, consider Micrometer Observation or `GraphQlObservationInstrumentation` before writing a custom strategy.

## 11. Why Keep Mutations Sequential When Customizing?

A custom strategy can extend either `AsyncExecutionStrategy` or `AsyncSerialExecutionStrategy`. Choosing the wrong superclass can alter operation semantics.

Example unsuitable for Mutations:

~~~java
AsyncExecutionStrategy strategy = new CustomAsyncExecutionStrategy(handler);

builder.configureGraphQl(graphQLBuilder ->
        graphQLBuilder
                .queryExecutionStrategy(strategy)
                .mutationExecutionStrategy(strategy));
~~~

If `CustomAsyncExecutionStrategy` executes root fields concurrently, assigning it to Mutations violates the sequential order mandated by the GraphQL specification.

A safer approach is separating strategies:

~~~java
builder.configureGraphQl(graphQLBuilder ->
        graphQLBuilder
                .queryExecutionStrategy(customQueryStrategy)
                .mutationExecutionStrategy(
                        new AsyncSerialExecutionStrategy(exceptionHandler)));
~~~

If you need custom behavior specific to Mutations, extend `AsyncSerialExecutionStrategy` and preserve sequential execution. Never choose a strategy based solely on the word `Async` or a desire for speed.

## 12. Configuring GraphQlSource Directly Without Boot

If the application builds `GraphQlSource` manually, you can configure `GraphQL.Builder` via `configureGraphQl`:

~~~java
GraphQlSource graphQlSource = GraphQlSource.schemaResourceBuilder()
        .schemaResources(new ClassPathResource("graphql/schema.graphqls"))
        .configureGraphQl(graphQLBuilder -> graphQLBuilder
                .queryExecutionStrategy(queryStrategy)
                .mutationExecutionStrategy(mutationStrategy))
        .build();
~~~

In a real application, the builder also needs schema resources, `RuntimeWiringConfigurer`, exception resolvers, and other settings. When constructing `GraphQlSource` manually, ensure exception handlers and all required extension points are wired in.

When using Spring Boot auto-configuration, prefer `GraphQlSourceBuilderCustomizer` to add configuration. Once you declare your own `GraphQlSource` bean, the application assumes responsibility for wiring components Boot previously auto-detected.

## 13. Customizing the Subscription Strategy

Subscriptions use `SubscriptionExecutionStrategy` to work with Reactive Streams. Never replace it with `AsyncExecutionStrategy` or `AsyncSerialExecutionStrategy`, as those two strategies do not implement subscription semantics.

If you genuinely need a custom `SubscriptionExecutionStrategy`, you can pass `DataFetcherExceptionHandler` similarly:

~~~java
import graphql.execution.SubscriptionExecutionStrategy;

SubscriptionExecutionStrategy subscriptionStrategy =
        new SubscriptionExecutionStrategy(exceptionHandler);
~~~

In Spring for GraphQL, terminal publisher errors are handled by `SubscriptionExceptionResolver`. `DataFetcherExceptionResolver` handles exceptions thrown while invoking a DataFetcher or resolving a field, not publisher `onError` signals after the transport has subscribed.

Do not use `ExecutionStrategy` to alter transport protocols, WebSocket lifecycles, or client reconnect policies. Those concerns belong to transport handlers, interceptors, and clients.

## 14. Errors, Partial Data, and Null Propagation

`ExecutionStrategy` coordinates the exception handler and GraphQL's value completion rules. When a DataFetcher throws an exception, GraphQL Java can resolve that field to null and add a GraphQL error to the response.

Example:

~~~json
{
  "data": {
    "book": {
      "id": "book-10",
      "title": "Spring GraphQL",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Author service unavailable",
      "path": ["book", "author"]
    }
  ]
}
~~~

If the `author` field is nullable, the error may turn only `author` into null. If the field or its parent is declared Non-Null, null propagation can null out a larger portion of `data` according to the schema.

`ExecutionStrategy` does not make business decisions about which errors to ignore. `DataFetcherExceptionHandler`/Spring exception resolvers map errors; schema nullability governs how nulls propagate through the response.

## 15. How Do ExecutionStrategy and Instrumentation Differ?

`Instrumentation` is an extension point for observing or adjusting GraphQL Java's lifecycle. `ExecutionStrategy` governs how fields are executed and results are coordinated.

| Need | Suitable Extension Point |
| --- | --- |
| Measuring overall request or field duration | `Instrumentation` / Micrometer Observation |
| Changing parallel vs. sequential field dispatch | `ExecutionStrategy` |
| Logging transport metadata or HTTP headers | `WebGraphQlInterceptor` |
| Mapping exceptions to GraphQL errors | `DataFetcherExceptionResolver` |
| Fetching data from databases/services | `DataFetcher`, controller, or application service |
| Batching multiple loads | `DataLoader` / `@BatchMapping` |
| Limiting query depth/complexity | `Instrumentation` or appropriate validation mechanism |

Do not create a custom `ExecutionStrategy` just to log or count fields. Those tasks fit `Instrumentation` far better and do not require altering execution semantics.

## 16. When Should You Write a Custom ExecutionStrategy?

Write a custom strategy only when the application needs to alter how GraphQL Java schedules fields in ways built-in strategies cannot satisfy.

Cases to consider:

- Requiring a custom scheduling policy for a category of queries.
- Enforcing domain-specific field concurrency caps.
- Coordinating a group of fields under an explicit dependency mechanism.
- Integrating execution with a specialized runtime.
- Extending an existing strategy while preserving operation semantics.

Before writing a custom strategy, verify whether simpler options solve the problem:

- Use `CompletionStage` or reactive return types in DataFetchers.
- Use `DataLoader` to batch I/O.
- Use a bounded executor to constrain blocking work.
- Use query depth/complexity limits to bound resource consumption.
- Use `Instrumentation` to observe execution.
- Scope transactions at the application service layer instead of across the entire GraphQL execution.

A custom strategy must handle nested objects, list completion, nullability, DataLoader dispatch, instrumentation callbacks, exception handling, and cancellation properly. It is a low-level extension point—avoid reimplementing it from scratch when you only need minor behavioral tweaks.

## 17. Performance and Concurrency Limits

`AsyncExecutionStrategy` can improve latency when multiple independent fields query different data sources. However, excessive concurrency can overwhelm database pools, HTTP connection pools, or downstream services.

Practical guidelines:

1. Never perform blocking I/O directly in a DataFetcher running on an event loop.
2. Use a bounded executor when wrapping blocking APIs is necessary.
3. Configure timeouts for databases and external services.
4. Bound concurrency at the client or service layer when downstream capacity is constrained.
5. Use `DataLoader` to cut query counts rather than adding more threads.
6. Measure p95/p99 latency and error rates before changing strategies.
7. Test with queries containing many sibling fields and large lists.
8. Monitor connection pool saturation and queue depth.

Switching Queries to `AsyncSerialExecutionStrategy` can increase latency because independent fields must wait for each other. Conversely, using a parallel strategy for Mutation root fields violates mandatory GraphQL semantics.

## 18. Testing ExecutionStrategy

Test both operation behavior and Spring configuration.

### Testing Mutation ordering

You can use `GraphQlTester` and Mockito `InOrder` to verify mutation root fields are invoked in order:

Schema used in the test:

~~~graphql
input CreateOrderInput {
    customerId: ID!
}

type Order {
    id: ID!
}

type Mutation {
    createOrder(input: CreateOrderInput!): Order!
    cancelOrder(orderId: ID!): Order!
}
~~~

The types below are the DTO and service contract used by the controller in the example:

~~~java
public record CreateOrderInput(String customerId) {
}

public record Order(String id) {
}

public interface OrderService {
    Order create(CreateOrderInput input);
    Order cancel(String orderId);
}
~~~

~~~java
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.mockito.InOrder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.graphql.test.autoconfigure.GraphQlTest;
import org.springframework.graphql.test.tester.GraphQlTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@GraphQlTest(OrderMutationController.class)
class MutationExecutionOrderTests {

    @Autowired
    GraphQlTester graphQlTester;

    @MockitoBean
    OrderService orderService;

    @Test
    void mutationRootFieldsAreExecutedInDocumentOrder() {
        when(orderService.create(any(CreateOrderInput.class)))
                .thenReturn(new Order("order-11"));
        when(orderService.cancel("order-10"))
                .thenReturn(new Order("order-10"));

        graphQlTester.document("""
                mutation {
                    createOrder(input: { customerId: "c-1" }) {
                        id
                    }
                    cancelOrder(orderId: "order-10") {
                        id
                    }
                }
                """)
                .execute()
                .errors()
                .verify();

        InOrder order = inOrder(orderService);
        order.verify(orderService).create(any());
        order.verify(orderService).cancel("order-10");
    }
}
~~~

The example assumes `OrderMutationController` maps the two root fields to `OrderService.create` and `OrderService.cancel`; the schema declares both fields and both return a non-null `Order`. `@GraphQlTest` auto-configures `GraphQlTester` for execution tests without an HTTP transport. In Spring Boot 3.x, import `GraphQlTest` from `org.springframework.boot.test.autoconfigure.graphql`; the Boot 4.x package is `org.springframework.boot.graphql.test.autoconfigure`. If using a Spring Boot version older than Spring Framework 6.2, replace `@MockitoBean` with `@MockBean` and import the annotation from Boot's test package.

### Testing asynchronous Query execution

Create two DataFetchers returning `CompletableFuture`s controlled by the test fixture. Confirm both sibling fetches are dispatched before completing either future, then complete them in reverse order and assert the response still preserves document field order.

Never use `Thread.sleep` to prove concurrency. Use `CountDownLatch`, `CompletableFuture` gates, or a controlled test executor to avoid flaky tests.

### Testing custom strategies and exception mapping

When using a custom strategy in Spring:

- Send a request whose DataFetcher throws a domain exception.
- Verify `DataFetcherExceptionResolver` is still invoked.
- Check that the GraphQL error carries the message/code defined by the resolver.
- Verify partial data and null propagation do not change unexpectedly.
- Confirm the custom strategy does not execute twice due to duplicate configuration.

### Testing Subscriptions

For subscriptions, verify:

- The root DataFetcher returns a `Publisher`.
- Each event produces one GraphQL response.
- Field errors inside an event appear in that event's response.
- Publisher terminal errors are routed through `SubscriptionExceptionResolver`.
- Client cancellation propagates to the publisher/upstream.

## 19. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Query fields run sequentially unexpectedly | Blocking DataFetchers or strategy changed to serial | Use non-blocking return types and check the query strategy. |
| Mutation root fields run concurrently | `AsyncExecutionStrategy` assigned to Mutation | Use `AsyncSerialExecutionStrategy` or a custom strategy preserving serial semantics. |
| JSON result does not match completion order | Field fetches finish in a different order than the document | Expected behavior; GraphQL Java assembles results in document field order. |
| Mutations are sequential yet data races across requests | Serial strategy applies only within a single operation | Use transactions, locking, or optimistic concurrency in services/databases. |
| Second mutation runs after first fails at business level | DataFetcher returned an error result as a GraphQL error so execution continued | Design an atomic use case in a single mutation/service if later steps depend on earlier ones. |
| Custom strategy breaks `@GraphQlExceptionHandler` | Strategy uses default `SimpleDataFetcherExceptionHandler` | Build the handler from Spring's `DataFetcherExceptionResolver` list and pass it to the constructor. |
| Subscription emits no events | `SubscriptionExecutionStrategy` replaced with a regular strategy | Keep `SubscriptionExecutionStrategy`. |
| Async Query still holds threads for long durations | DataFetcher performs blocking I/O before returning the future | Use non-blocking clients or a bounded executor. |
| Database overloaded after enabling parallel queries | Sibling field concurrency exceeds pool capacity | Bound concurrency and optimize `DataLoader`/queries. |
| DataLoader batches are small or ineffective | Dispatch timing shifted due to strategy or fetch pattern | Test batch dispatch and adjust strategy/loader accordingly. |
| GraphQL mutation fails to roll back all fields | Confusing serial execution with a transaction | Place the transaction inside an application service spanning the full use case. |
| Duplicate metrics | Custom strategy used solely for timing alongside Observation | Prefer Instrumentation/Micrometer and avoid double-counting. |

## 20. Checklist for Choosing and Configuring ExecutionStrategy

1. Use `AsyncExecutionStrategy` for standard Queries.
2. Use `AsyncSerialExecutionStrategy` for Mutations to preserve root field order.
3. Use `SubscriptionExecutionStrategy` for Subscriptions and Reactive Streams.
4. Remember Query fields can execute asynchronously while responses stay in document order.
5. Never assume `AsyncExecutionStrategy` turns blocking DataFetchers into non-blocking ones.
6. Use `CompletionStage`/reactive types or a bounded executor for appropriate I/O.
7. Never confuse Mutation serial execution with an atomic transaction or global lock.
8. When customizing a strategy, prefer extending an appropriate built-in strategy rather than implementing from scratch.
9. When configuring in Spring, keep the `DataFetcherExceptionHandler` created from `DataFetcherExceptionResolver`s.
10. Never assign a parallel strategy to Mutations.
11. Never replace `SubscriptionExecutionStrategy` with a Query/Mutation strategy.
12. Use Instrumentation/Micrometer for metrics and tracing when scheduling itself does not need to change.
13. Test mutation ordering, query concurrency, exception mapping, partial data, and subscriptions.
14. Measure latency, throughput, queues, and connection pools before and after changing strategies.

`ExecutionStrategy` is GraphQL Java's mechanism for coordinating field resolution. `AsyncExecutionStrategy` fits Queries with independent fields; `AsyncSerialExecutionStrategy` enforces the mandatory order for Mutation root fields; `SubscriptionExecutionStrategy` handles event streams. In Spring for GraphQL, customizing strategies via `GraphQlSourceBuilderCustomizer` while retaining Spring's `DataFetcherExceptionHandler` lets applications adjust execution behavior without breaking error mapping. Replace a strategy only when you genuinely need a different scheduling policy; metrics, batching, transactions, and transport concerns belong in their respective extension points.

References:
- [GraphQL Java — Execution Strategies](https://graphql-java.com/documentation/execution/)
- [GraphQL Java — ExecutionStrategy API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/ExecutionStrategy.html)
- [GraphQL Java — AsyncExecutionStrategy API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/AsyncExecutionStrategy.html)
- [GraphQL Java — AsyncSerialExecutionStrategy API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/AsyncSerialExecutionStrategy.html)
- [GraphQL Java — SubscriptionExecutionStrategy API](https://javadoc.io/doc/com.graphql-java/graphql-java/latest/graphql/execution/SubscriptionExecutionStrategy.html)
- [Spring for GraphQL — Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — DataFetcherExceptionResolver API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/execution/DataFetcherExceptionResolver.html)
- [GraphQL Specification — Normal and Serial Execution](https://spec.graphql.org/October2021/#sec-Normal-and-Serial-Execution)
