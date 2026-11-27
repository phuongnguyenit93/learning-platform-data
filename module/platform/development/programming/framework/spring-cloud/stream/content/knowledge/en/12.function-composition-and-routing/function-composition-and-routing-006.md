# Per-Message Routing Limitations with the Reactive Model

Spring Cloud Function can route a message to an appropriate function based on headers or SpEL expressions. This mechanism works per message with imperative functions such as `Function<OrderEvent, Result>`. However, when using a reactive function such as `Function<Flux<OrderEvent>, Flux<Result>>`, the unit of processing of the function is the entire Publisher. The framework invokes the function once to pass the `Flux` in; Reactor processes the elements afterward. Therefore, headers on individual elements cannot ask Spring Cloud Function to select a different function bean for each individual element.

This limitation does not mean a reactive stream cannot branch per element. An application can still use `filter`, `flatMap`, `groupBy`, or a handler lookup table to route individual events inside the Reactor pipeline. What must be distinguished is **function routing at the FunctionCatalog level** versus **data routing inside the reactive pipeline**. Choosing the right layer prevents flawed designs while preserving backpressure, error handling, and message ordering as required.

## 1. Two different units of processing

With an imperative function, the framework invokes the function once per message. Therefore, each message can carry a header specifying the target function:

```java
@Bean
Function<OrderEvent, ProcessingResult> processOrder() {
    return event -> orderService.process(event);
}
```

With a reactive function, the framework invokes the function to supply a Publisher. Reactor operators then process each element upon subscription:

```java
@Bean
Function<Flux<OrderEvent>, Flux<ProcessingResult>> processOrders() {
    return events -> events.map(orderService::process);
}
```

| Characteristic | Imperative function | Reactive function |
|---|---|---|
| Example signature | `Function<OrderEvent, Result>` | `Function<Flux<OrderEvent>, Flux<Result>>` |
| Framework invocation count | Once per message | Once to pass the Publisher |
| Unit of work | One message | Entire stream/Publisher |
| Per-message header routing | Possible | Cannot be used to choose a function bean per element |
| Per-element branching | Inside function logic | Inside the Reactor pipeline |
| Route config via application properties | Yes | Yes; route applies to the entire stream |

This is the core point of the lesson. Reactive is not imperative called faster; the lifecycle and invocation boundaries differ. You cannot assume the router will be invoked again for each `Message` inside a `Flux`.

## 2. Per-message routing with imperative functions

Spring Cloud Function registers `RoutingFunction` in `FunctionCatalog` under the name `functionRouter`. When using routing, you can select the target function through one of the following mechanisms:

- `spring.cloud.function.definition` header: name of a function or a composition, such as `validateOrder|processOrder`.
- `spring.cloud.function.routing-expression` header: a SpEL expression returning the name of the function/composition to invoke.
- `MessageRoutingCallback`: a strategy bean that determines the function definition from the message.
- Application properties: `spring.cloud.function.definition` or `spring.cloud.function.routing-expression`, applied to the function selected at the application level.

Example configuration enabling the router:

```yaml
spring:
  cloud:
    function:
      definition: functionRouter
```

Producer sending a message with a function definition:

```java
Message<OrderCreated> message = MessageBuilder
    .withPayload(event)
    .setHeader("spring.cloud.function.definition", "validateOrder|acceptOrder")
    .build();

streamBridge.send("orders-out-0", message);
```

In this example, the producer sends through the `orders-out-0` output binding; the consumer receives the message from the corresponding input binding, and the router can select the `validateOrder|acceptOrder` composition for that message. Bindings and send/receive paths must be configured to match your application architecture; this example focuses only on routing metadata. Function names must exist in `FunctionCatalog` and signatures must compose cleanly.

For dynamic expressions, the `spring.cloud.function.routing-expression` header can reference the message payload and headers:

```java
Message<OrderEvent> message = MessageBuilder
    .withPayload(event)
    .setHeader(
        "spring.cloud.function.routing-expression",
        "headers['eventType'] == 'ORDER_CREATED' ? 'createOrder' : 'cancelOrder'")
    .build();
```

For imperative functions, the expression is evaluated per message, so it can select different functions based on `eventType`. Never place an arbitrary expression string from an external user into a header. Validate route values against an allowlist and expose only functions permitted to be invoked.

## 3. Precedence of routing instructions

When multiple mechanisms provide a route simultaneously, Spring Cloud Function applies the following precedence order for imperative functions:

1. `MessageRoutingCallback` has highest priority.
2. Message headers are used if no callback decides the route.
3. Application properties are the next configuration source and are also the mechanism usable with reactive functions.

If a route points to a function not present in `FunctionCatalog`, the message becomes unroutable. Spring Cloud Function provides `DefaultMessageRoutingHandler` to customize behavior; the default implementation logs a message and lets the flow continue, effectively dropping the unroutable message. If business data must be preserved, register a custom handler to record it, route to an error/DLQ flow, or reject in a controlled way. Do not rely on default logging as a message-retention mechanism.

## 4. Routing header limitations with reactive functions

Suppose an input binding receives a `Flux<Message<OrderEvent>>`. Each message has a `spring.cloud.function.definition` header:

```text
Message 1: spring.cloud.function.definition = createOrder
Message 2: spring.cloud.function.definition = cancelOrder
Message 3: spring.cloud.function.definition = createOrder
```

With an imperative function, the router can select `createOrder`, `cancelOrder`, and then `createOrder` in order for each message. But with a reactive function, Spring Cloud Function invokes the function once to pass the Publisher in. Headers carried on individual elements of the Publisher are not used to switch the target function bean per element.

If you provide `spring.cloud.function.definition` or `spring.cloud.function.routing-expression` as application properties, that route applies at the function/stream level. Example:

```yaml
spring:
  cloud:
    function:
      definition: processOrders
```

`processOrders` is selected for the entire stream. You cannot expect one message inside the `Flux` to change the route for remaining messages by setting its own routing header. This is a direct consequence of the unit of work: the entire Publisher is the input of a single invocation.

If the business requirement is that each event in the same stream must be processed by a different handler, place the branching logic inside the reactive function rather than relying on `RoutingFunction` to switch function beans per element.

## 5. Routing individual elements inside a Flux

A common approach is using `flatMap` to look up a handler by event type. The function is still invoked once with the Publisher, but the operator processes and selects a handler for each message:

```java
public interface OrderEventHandler {
    Mono<ProcessingResult> handle(OrderEvent event);
}

@Bean
Function<Flux<Message<OrderEvent>>, Flux<Message<ProcessingResult>>> routeOrders(
        Map<String, OrderEventHandler> handlers) {

    return messages -> messages.flatMap(message -> {
        String eventType = message.getHeaders().get("eventType", String.class);
        OrderEventHandler handler = handlers.get(eventType);

        if (handler == null) {
            return Mono.error(new UnsupportedEventTypeException(eventType));
        }

        return handler.handle(message.getPayload())
            .map(result -> MessageBuilder.withPayload(result)
                .setHeader("correlationId", message.getHeaders().get("correlationId"))
                .setHeader("sourceEventId", message.getHeaders().get("eventId"))
                .build());
    });
}
```

In this example:

- `routeOrders` receives the entire `Flux` in a single invocation.
- `flatMap` applies logic to each `Message<OrderEvent>` as elements flow through the pipeline.
- `eventType` selects a handler from a map registered in the application.
- The handler returns `Mono<ProcessingResult>` to integrate asynchronous processing.
- The result is wrapped into a new message while retaining only necessary metadata.

This is data-layer routing inside Reactor, not Spring Cloud Function routing by bean name. The handler map should be built from approved beans; never use arbitrary class or bean names from a message to instantiate objects or invoke arbitrary beans in the application context.

If handlers perform synchronous work, avoid running blocking operations directly on the Reactor event-loop. Use non-blocking APIs or isolate blocking work on an appropriate scheduler. If strict per-message ordering is required, consider `concatMap`; if parallelism is needed while preserving emission order, consider `flatMapSequential`.

## 6. Choosing operators for routing requirements

| Operator | Behavior | When appropriate |
|---|---|---|
| `filter` | Keeps or drops elements by condition | Passing only qualifying events forward |
| `map` | Synchronously transforms each element | Classification or lightweight normalization |
| `flatMap` | Turns each element into a Publisher and merges results, possibly concurrently | Calling async handlers when output order may vary |
| `concatMap` | Processes each Publisher sequentially | Preserving input processing order |
| `flatMapSequential` | Processes concurrently while emitting results in input order | Needing throughput alongside stable output order |
| `groupBy` | Splits the stream into groups by key | Processing by event type, tenant, or aggregate key |

Example filtering `ORDER_CREATED` events before transformation:

```java
@Bean
Function<Flux<Message<OrderEvent>>, Flux<OrderCreated>> onlyCreatedOrders() {
    return messages -> messages
        .filter(message -> "ORDER_CREATED".equals(
            message.getHeaders().get("eventType")))
        .map(Message::getPayload)
        .cast(OrderCreated.class);
}
```

`filter` removes non-matching elements from this branch. If dropped events need preservation or auditing, route them to another branch or record the rejection reason; do not treat `filter` as an automatic DLQ.

## 7. Splitting into multiple output streams from one reactive function

If the goal is classifying events into multiple output bindings, Spring Cloud Function supports function arity for reactive functions. For example, a function can return a tuple containing two `Flux` streams:

```java
@Bean
Function<Flux<IncomingEvent>, Tuple2<Flux<OrderEvent>, Flux<InvoiceEvent>>> splitEvents() {
    return events -> {
        // Create two output Publishers using a fan-out mechanism suited to the stream source.
        Flux<OrderEvent> orders = orderStreamFrom(events);
        Flux<InvoiceEvent> invoices = invoiceStreamFrom(events);
        return Tuples.of(orders, invoices);
    };
}
```

Function arity for reactive functions lets the framework infer the number of input/output bindings from the tuple. In the example above, the output bindings are `splitEvents-out-0` and `splitEvents-out-1`. Configure their destinations accordingly:

```yaml
spring:
  cloud:
    function:
      definition: splitEvents
    stream:
      bindings:
        splitEvents-out-0:
          destination: orders.events
        splitEvents-out-1:
          destination: invoices.events
```

This is a skeleton illustrating a function arity signature; `orderStreamFrom` and `invoiceStreamFrom` represent the application's branching logic. When creating two outputs from the same Publisher, design fan-out and subscriptions carefully so you do not accidentally subscribe twice to a non-replayable source or lose elements if output subscribers start at slightly different times. Spring Cloud Function arity focuses on reactive functions and multi-input/output stream use cases; it does not turn per-element routing headers into function bean selection commands.

If each event must go to exactly one output, ensure the classification logic is mutually exclusive. If both branches receive an event, that is intentional fan-out and may produce two side effects. Test message counts on each output and behavior when one branch fails.

## 8. Backpressure, concurrency, and ordering

Per-element routing in a reactive stream must preserve flow-rate control. `flatMap` can execute multiple handlers concurrently; if downstream is slow, bound concurrency and prefetch to match system capacity. Never spawn an unbounded number of tasks per message.

Choose operators based on business semantics:

- Use `concatMap` when events for the same aggregate must execute strictly in order and not concurrently.
- Use `flatMapSequential` when parallel execution is safe but output must preserve input order.
- Use `flatMap` when output order does not matter and higher throughput is needed; configure bounded concurrency.
- Use `groupBy` when grouping events by key, while managing group lifecycle and group count to avoid holding excessive resources.

With Kafka, order within a partition is meaningful; arbitrary parallelization in a consumer can cause business operations to finish out of read order. With RabbitMQ and Pulsar, ordering also depends on queues/subscriptions and binder dispatch. Reactor operators alone cannot create ordering guarantees across multiple partitions or queues.

## 9. Handling unroutable events and single-branch errors

In a reactive pipeline, clearly define behavior when:

- The `eventType` header is missing or invalid.
- No matching handler is found.
- A handler returns an error or times out.
- An event does not belong to any handled type.
- One output branch fails after another branch already emitted a message.

Example isolating per-element errors so other events can continue:

```java
return messages.flatMap(message -> routeOne(message)
    .onErrorResume(error -> {
        log.warn("Cannot route eventId={}",
            message.getHeaders().get("eventId"), error);
        return publishToErrorFlow(message, error).then(Mono.empty());
    }));
```

Placing `onErrorResume` inside each element's inner publisher isolates errors per event. If an exception escapes to the outer pipeline, the reactive sequence can terminate and cancel remaining elements. Choose the appropriate policy: bounded retries for transient errors, routing to a DLQ for unprocessable errors, or stopping the stream if consistency requires fail-fast.

Do not merely log and drop events if the business requires delivery guarantees. Error flows should capture event ID, event type, correlation ID, source binding, and cause, while avoiding logging sensitive payloads.

## 10. Securing the routing mechanism

Routing headers are input data. Any producer or client with publish permissions can send arbitrary header values. Therefore:

- Maintain an allowlist of permitted routes/functions.
- Do not let external clients directly choose arbitrary bean names in the application.
- Authenticate producers and enforce publish permissions on the broker.
- Do not use routing to bypass business authorization.
- Validate `eventType` and schema before dispatching.
- Restrict destinations and output bindings a function may send to.
- Protect management endpoints that can modify application properties or function definitions.

Spring Cloud Function evaluates SpEL obtained from message headers in a `SimpleEvaluationContext` with more restricted capabilities than expressions configured in application properties. Even so, treat route values as untrusted data and restrict target functions. Expressions in application properties have broader expressive power; protect configuration sources and administrative endpoints that can modify them.

## 11. Testing routing with imperative and reactive models

Write tests that distinguish the two models:

1. For an imperative function, send two messages with different `spring.cloud.function.definition` values and confirm each reaches the right function.
2. For imperative routing expressions, test valid headers, missing headers, and headers outside the allowlist.
3. For a reactive function, configure the function route in application properties and confirm the entire stream enters the selected function.
4. Send a `Flux` containing different `eventType` values and confirm the internal router picks the right handler for each element.
5. Test concurrency, output ordering, and backpressure when handlers have varying execution times.
6. Force one handler to fail and verify the retry/DLQ policy or per-event error isolation.
7. Send an unsupported event type and confirm it is observed rather than silently ignored.
8. Test with a real binder/broker to verify header mapping, redelivery, and acknowledgments under deployment settings.

The Test Binder is useful for testing functions and bindings at the application scope. It does not replace integration tests with Kafka, RabbitMQ, or Pulsar when verifying partition ordering, redelivery, DLQ, and real consumer behavior.

## 12. Choosing a routing model

| Requirement | Approach |
|---|---|
| Each imperative message selects a function bean | `functionRouter` with `spring.cloud.function.definition` header or routing-expression header |
| Imperative route selection via Java logic | `MessageRoutingCallback` |
| Entire reactive stream uses one function | `spring.cloud.function.definition` or routing instruction in application properties |
| Each reactive element selects a different handler | `Flux` operators and handler registry inside the reactive function |
| Splitting one stream into multiple output bindings | Reactive function arity with a `Tuple` of Publishers |
| Dropping unsuitable messages | `filter` or discard branch with explicit metrics/logs/error policy |

When designing routing for Spring Cloud Stream, first determine whether the unit of work is a single message or an entire Publisher. Use header routing when an imperative function needs per-message function selection. With reactive functions, let application properties select the function for the entire stream and branch per event using Reactor operators or a handler registry. This split respects Spring Cloud Function's invocation model while keeping explicit control over concurrency, ordering, errors, and backpressure. Property names and integration details may change across release trains; verify against the documentation for the exact Spring Cloud Function/Spring Cloud Stream version managed in your project.

## References

- [Spring Cloud Function — Programming model, Function Routing and Filtering](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Function — Function Arity and reactive functions](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html#function-arity)
