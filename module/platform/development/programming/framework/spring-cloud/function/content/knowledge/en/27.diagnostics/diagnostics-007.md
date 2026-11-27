# Routing Headers Have No Effect on Reactive Streams

## 1. Symptom: Routing Header Is Present, Yet the Target Never Changes

A **Spring Cloud Function** application defines two handlers:

~~~java
@Bean
public Function<Flux<OrderEvent>, Flux<OrderResult>> processOrders() {
    return events -> events.map(this::processOrder);
}

@Bean
public Function<Flux<InvoiceEvent>, Flux<InvoiceResult>> processInvoices() {
    return events -> events.map(this::processInvoice);
}
~~~

A producer wants to pick the function per message using a header:

~~~text
spring.cloud.function.definition=processOrders
~~~

Or using an expression:

~~~text
spring.cloud.function.routing-expression=headers['eventType'] == 'ORDER'
    ? 'processOrders'
    : 'processInvoices'
~~~

However, when the input is `Flux<?>` or `Publisher<?>`, per-message header routing does not work as expected. Events carrying different headers still enter the same reactive function, or `RoutingFunction` fails to choose targets based on each element's header.

Usually this is not a header typo. The root cause lies in the **unit of work** of a reactive function:

- For an imperative function such as `Function<Message<OrderEvent>,OrderResult>`, the framework invokes the function once per message. The router receives a concrete `Message` to inspect headers and pick a target.
- For a reactive function such as `Function<Flux<Message<OrderEvent>>,Flux<OrderResult>>`, the framework invokes the function once to pass in the publisher. Elements are processed later inside the Reactor pipeline.
- `RoutingFunction` is not re-invoked for each element inside the publisher just to inspect headers and switch functions.
- For reactive inputs, Spring Cloud Function requires routing instructions to be supplied via **application properties**; that instruction selects the target for the entire stream.

This lesson belongs to the **Diagnostics** chapter, titled **"Routing Headers Have No Effect on Reactive Streams"**, in the **SPRING_CLOUD_FUNCTION** module. The module teaches building reusable business logic with `Supplier`, `Function`, and `Consumer`, looking up via `FunctionCatalog`, converting messages, and deploying over HTTP, events, or serverless.

**Central diagnostic question:** is the function invoked once per message, or once for the entire publisher?

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish per-message routing from whole-stream reactive routing.
2. Explain why `spring.cloud.function.definition` or `spring.cloud.function.routing-expression` headers do not route individual items inside a `Flux`.
3. Understand the role and limits of `MessageRoutingCallback`.
4. Configure routing via application properties for reactive functions.
5. Distinguish function routing from Spring Cloud Stream output destination routing.
6. Choose between imperative routing and explicit branching inside a Reactor pipeline.
7. Verify routing across HTTP, Spring Cloud Stream, `FunctionCatalog`, and serverless adapters.
8. Write tests confirming each event takes the right branch without being dropped.
9. Protect routing targets using allowlists, authorization, and SpEL controls.

## 2. Imperative and Reactive Functions Have Different Units of Work

### 2.1. Imperative: One Invocation Equals One Message

~~~java
@Bean
Function<Message<OrderEvent>, OrderResult> processOrder() {
    return message -> process(message.getPayload());
}
~~~

If the adapter receives three messages, the function is called three times:

~~~text
Message A → processOrder(message A)
Message B → processOrder(message B)
Message C → processOrder(message C)
~~~

Each invocation receives a concrete `Message<?>`. `RoutingFunction` can inspect that message's headers to select a target.

### 2.2. Reactive: One Invocation Receives the Entire Publisher

~~~java
@Bean
Function<Flux<Message<OrderEvent>>, Flux<OrderResult>> processOrders() {
    return messages -> messages.map(message ->
        process(message.getPayload())
    );
}
~~~

The adapter passes a single `Flux`:

~~~text
processOrders(publisher)
    ├─ Message A
    ├─ Message B
    └─ Message C
~~~

`processOrders` is invoked once to accept the publisher. Reactor processes elements when the pipeline is subscribed to. Having multiple `Message<?>` items inside `Flux` does not turn the function into multiple imperative invocations.

### 2.3. Comparison Diagram

~~~mermaid
flowchart TB
    subgraph IMP["Imperative function"]
      A["Message A + header A"] --> R["RoutingFunction"]
      B["Message B + header B"] --> R
      C["Message C + header C"] --> R
      R -->|A| FA["Function A"]
      R -->|B| FB["Function B"]
      R -->|C| FC["Function C"]
    end
    subgraph REACT["Reactive function"]
      P["Publisher / Flux"] --> RR["Single routing decision"]
      RR --> T["One reactive target"]
      T --> PIPE["Reactor pipeline"]
      PIPE --> X["Message A"]
      PIPE --> Y["Message B"]
      PIPE --> Z["Message C"]
    end
~~~

The difference is not whether the header exists. The difference is whether `RoutingFunction` receives a single `Message` or a `Publisher` at target-selection time.

## 3. Headers Still Exist on Each Element, Yet the Built-In Router Does Not Route Per Item

A reactive function can accept:

~~~java
Function<Flux<Message<OrderEvent>>, Flux<OrderResult>>
~~~

Each `Message<OrderEvent>` still carries payload and headers. Inside the business pipeline, you can read headers:

~~~java
messages.map(message ->
    message.getHeaders().get("eventType", String.class)
);
~~~

However, that does not mean `RoutingFunction` inspected those headers before selecting the function. The router treats the publisher as a single unit of work; per-element headers are only seen once the Reactor pipeline processes them.

| Question | Reactive function |
| --- | --- |
| Can you read per-item headers inside `Flux<Message<T>>`? | **Yes**, inside the pipeline |
| Does built-in `RoutingFunction` pick a different function per item in the same publisher? | **No** under SCF reactive per-message routing rules |
| Do application properties pick the function for the entire stream? | **Yes** |
| Can you branch per item using `flatMap`/`concatMap`? | **Yes** |
| Does `MessageRoutingCallback` decide per item in a reactive publisher? | **No** under imperative routing callback semantics |

For example, a producer might construct messages with different headers:

~~~java
Message<OrderEvent> orderMessage =
    MessageBuilder.withPayload(orderEvent)
        .setHeader("spring.cloud.function.definition", "processOrders")
        .build();

Message<InvoiceEvent> invoiceMessage =
    MessageBuilder.withPayload(invoiceEvent)
        .setHeader("spring.cloud.function.definition", "processInvoices")
        .build();
~~~

If the adapter feeds them into one publisher passed to a reactive function, the headers may still sit on each item. SCF does not re-invoke `RoutingFunction` for each item to switch targets.

## 4. Two Primary Routing Headers

Spring Cloud Function supports two routing instructions:

~~~text
spring.cloud.function.definition
spring.cloud.function.routing-expression
~~~

### 4.1. Definition Header

The `spring.cloud.function.definition` header specifies a function name or composition:

~~~text
spring.cloud.function.definition=processOrders
~~~

It can also contain a composition:

~~~text
spring.cloud.function.definition=normalizeOrder|processOrders
~~~

### 4.2. Routing-Expression Header

The `spring.cloud.function.routing-expression` header holds a SpEL expression that must evaluate to a function name or definition:

~~~text
spring.cloud.function.routing-expression=headers['eventType'] == 'ORDER'
    ? 'processOrders'
    : 'processInvoices'
~~~

In imperative routing, the expression's root object is the incoming message, so the expression can read both payload and headers.

### 4.3. Headers Differ from Application Properties

| Where instruction is placed | Example | Scope |
| --- | --- | --- |
| Message header | `spring.cloud.function.definition` | One imperative message |
| Message header | `spring.cloud.function.routing-expression` | Expression on one imperative message |
| Application property | `spring.cloud.function.definition` | Application-level target selection |
| Application property | `spring.cloud.function.routing-expression` | Application-level routing expression |

For reactive inputs, use application properties to pick the target for the whole stream. Do not turn per-message headers into shared properties expecting each item to get its own target.

## 5. Why Does Reactive Routing Only Use Application Properties?

Spring Cloud Function documentation explains this via the unit of work:

- An imperative function's unit of work is a single `Message`.
- A reactive function's unit of work is the entire `Publisher`/stream.
- A reactive function is invoked once to accept the publisher; Reactor processes items afterward.
- The router cannot inspect each item's routing instruction to re-select a function prior to each invocation.
- For reactive functions, routing instructions must come from application properties and apply to the entire stream.

~~~mermaid
sequenceDiagram
    participant A as Adapter
    participant R as RoutingFunction
    participant F as Reactive Function
    participant P as Reactor pipeline
    A->>R: Publisher (Flux<Message>)
    R->>R: Read application properties
    R->>F: Select one target for the stream
    F->>P: Pass Publisher into pipeline
    loop As each item is consumed
        P->>P: Process item's Message and headers
    end
~~~

If application properties select `processOrders`, the entire publisher goes to that function. An element's `eventType` header will not make the router switch targets to `processInvoices` on the next element.

## 6. Proper Configuration When Choosing One Target for the Whole Stream

Suppose an application has a reactive function processing orders:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderResult>> processOrders() {
    return events -> events.map(this::processOrder);
}
~~~

Explicit configuration:

~~~properties
spring.cloud.function.definition=processOrders
~~~

Or YAML:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrders
~~~

Another deployment can pick a different function:

~~~properties
spring.cloud.function.definition=processInvoices
~~~

### 6.1. Profile-Based Configuration

~~~yaml
spring:
  config:
    activate:
      on-profile: orders
  cloud:
    function:
      definition: processOrders
---
spring:
  config:
    activate:
      on-profile: invoices
  cloud:
    function:
      definition: processInvoices
~~~

Activating a profile:

~~~bash
java -jar app.jar --spring.profiles.active=orders
~~~

Profiles select targets at the application level. This fits when each instance or consumer group is dedicated to one stream type.

### 6.2. Profiles Are Not Per-Message Routing

If a publisher carries both orders and invoices, the `orders` profile routes the entire publisher to `processOrders`. It does not split invoice events off to another function. If one instance must handle multiple event types within the same stream, branch inside the reactive pipeline or split ingress/bindings into separate streams.

## 7. MessageRoutingCallback Applies Only to Imperative Routing

`MessageRoutingCallback` is a strategy determining the target function from a `Message<?>`:

~~~java
public interface MessageRoutingCallback {
    String routingResult(Message<?> message);
}
~~~

Example:

~~~java
@Bean
MessageRoutingCallback routeByEventType() {
    return new MessageRoutingCallback() {
        @Override
        public String routingResult(Message<?> message) {
            String type =
                message.getHeaders().get("eventType", String.class);

            return switch (type == null ? "" : type) {
                case "ORDER" -> "processOrder";
                case "INVOICE" -> "processInvoice";
                default -> throw new IllegalArgumentException(
                    "Unsupported eventType: " + type
                );
            };
        };
    };
}
~~~

The callback is invoked by the router with a concrete message to choose the target. When the target is a reactive function, SCF invokes the function to hand over the publisher; the callback is not re-invoked for each element in the publisher.

### 7.1. Callbacks Can Override Headers in Imperative Routing

Precedence according to current documentation:

1. `MessageRoutingCallback`.
2. Message headers if no callback is registered.
3. Application properties.

If a callback is registered, the `spring.cloud.function.definition` header can be ignored because the callback takes higher precedence. That is another reason headers appear to have no effect even in imperative applications.

This precedence order does not turn callbacks into per-message routing for reactive publishers. Reactive routing still relies on application properties.

## 8. Definition Header and Routing-Expression

Static header:

~~~java
Message<OrderEvent> message =
    MessageBuilder.withPayload(order)
        .setHeader(
            "spring.cloud.function.definition",
            "processOrder"
        )
        .build();
~~~

Expression header:

~~~java
Message<OrderEvent> message =
    MessageBuilder.withPayload(order)
        .setHeader(
            "spring.cloud.function.routing-expression",
            "headers['eventType'] == 'ORDER' ? 'processOrder' : 'processInvoice'"
        )
        .build();
~~~

Both can route per message when inputs are imperative `Message` instances and the adapter sends messages through `RoutingFunction`.

Headers like `eventType`, `tenantId`, `correlationId`, `traceId`, or `contentType` are merely application/transport metadata unless routing logic is configured to read them. Sending `eventType=ORDER` does not automatically select bean `processOrder`.

Do not confuse this with `spring.cloud.stream.sendto.destination`. That header routes **output messages to a destination** in Spring Cloud Stream; it does not choose which function processes input.

## 9. Routing Each Event in a Reactive Stream by Branching Inside Flux

If a stream carries multiple event types and each event needs a distinct branch, implement branching logic inside the reactive function.

~~~java
@Bean
Function<Flux<Message<InboundEvent>>, Flux<RoutedResult>> dispatchEvents(
        OrderHandler orderHandler,
        InvoiceHandler invoiceHandler) {

    return messages -> messages.concatMap(message -> {
        InboundEvent event = message.getPayload();
        String type =
            message.getHeaders().get("eventType", String.class);

        return switch (type == null ? "" : type) {
            case "ORDER" -> orderHandler.handle(event);
            case "INVOICE" -> invoiceHandler.handle(event);
            default -> Mono.error(
                new IllegalArgumentException(
                    "Unsupported eventType: " + type
                )
            );
        };
    });
}
~~~

Services:

~~~java
public interface OrderHandler {
    Mono<RoutedResult> handle(InboundEvent event);
}

public interface InvoiceHandler {
    Mono<RoutedResult> handle(InboundEvent event);
}
~~~

DTOs:

~~~java
public record InboundEvent(
    String eventId,
    String payload
) {}

public record RoutedResult(
    String eventId,
    String handler,
    String status
) {}
~~~

This is business-level dispatch inside the stream:

- The reactive function is invoked once with the publisher.
- Each `Message` is inspected inside `concatMap`.
- The application selects the handler based on each item's header.
- Results are emitted onto the output publisher.
- `FunctionCatalog` does not re-route each event.

### 9.1. Choosing Operators Based on Ordering and Concurrency

- `concatMap` processes sequentially and preserves input ordering in outputs.
- `flatMap` allows inner publishers to run concurrently; outputs may not keep source order.
- `flatMapSequential` runs concurrently while preserving emission order at the cost of buffering.

If events mutate the same aggregate or must preserve transaction order, do not switch to `flatMap` just for concurrency without ordering guarantees.

### 9.2. Target Allowlist

The example switches over fixed values. This acts as a simple allowlist. Never take an arbitrary class or function name from headers and use unrestricted reflection or SpEL to invoke any bean in the context.

## 10. Routing by Payload Instead of Headers

If the event type already resides in the payload, separate routing metadata may not be needed:

~~~java
public record DomainEvent(
    String eventType,
    String eventId,
    String body
) {}
~~~

~~~java
@Bean
Function<Flux<DomainEvent>, Flux<RoutedResult>> dispatchByPayload(
        OrderHandler orderHandler,
        InvoiceHandler invoiceHandler) {

    return events -> events.concatMap(event ->
        switch (event.eventType()) {
            case "ORDER" -> orderHandler.handle(
                new InboundEvent(event.eventId(), event.body())
            );
            case "INVOICE" -> invoiceHandler.handle(
                new InboundEvent(event.eventId(), event.body())
            );
            default -> Mono.error(
                new IllegalArgumentException(
                    "Unsupported event type: " + event.eventType()
                )
            );
        }
    );
}
~~~

Advantages:

- Routing data is part of the event schema.
- It can be serialized, validated, and versioned alongside the payload.
- It does not depend on whether adapters propagate custom headers.
- Tests are simpler with pure event objects.

Drawbacks: payloads may duplicate metadata already present in envelope/message headers. Pick one clear contract to prevent headers and payloads from contradicting each other.

## 11. Splitting Streams into Reactive Branches

You can use `filter`, `groupBy`, or other Reactor operators to split streams.

~~~java
@Bean
Function<Flux<DomainEvent>, Flux<RoutedResult>> dispatchByType(
        OrderHandler orderHandler,
        InvoiceHandler invoiceHandler) {

    return events -> events
        .groupBy(DomainEvent::eventType)
        .flatMap(group ->
            switch (group.key()) {
                case "ORDER" ->
                    group.concatMap(event -> orderHandler.handle(
                        new InboundEvent(event.eventId(), event.body())
                    ));
                case "INVOICE" ->
                    group.concatMap(event -> invoiceHandler.handle(
                        new InboundEvent(event.eventId(), event.body())
                    ));
                default ->
                    group.flatMap(event ->
                        Mono.error(new IllegalArgumentException(
                            "Unsupported event type: " + group.key()
                        ))
                    );
            }
        );
}
~~~

`groupBy` can keep multiple active groups alive simultaneously; pay attention to lifecycle, backpressure, and consuming every group. With unbounded key cardinality, never create infinite groups without a management strategy.

### 11.1. Be Careful When Filtering the Same Publisher Multiple Times

The following pattern may look simple:

~~~java
Flux<RoutedResult> orders =
    events.filter(e -> "ORDER".equals(e.eventType()))
        .concatMap(orderHandler::handle);

Flux<RoutedResult> invoices =
    events.filter(e -> "INVOICE".equals(e.eventType()))
        .concatMap(invoiceHandler::handle);

return Flux.merge(orders, invoices);
~~~

However, a `Flux` is often a cold source; two branches may subscribe to upstream twice. Use a proper multicast/`share` design or a single branching operator. Do not copy that snippet verbatim if the source has side effects or can only be read once.

### 11.2. When Separate Output Bindings Are Needed

Spring Cloud Function supports reactive function arity with multiple inputs/outputs via supported tuple types. If the requirement is splitting orders and invoices onto two separate output bindings, consider function arity instead of trying to route individual items to function beans by header.

Choose by goal: calling internal services, emitting two output publishers, or sending to different broker destinations are three distinct requirements.

## 12. Spring Cloud Stream: Enabling RoutingFunction Properly

Spring Cloud Stream supports event routing via `RoutingFunction`. To enable input routing through the function router:

~~~properties
spring.cloud.stream.function.routing.enabled=true
~~~

When enabled, the router's input binding is named:

~~~text
functionRouter-in-0
~~~

Producers send messages to the destination bound to `functionRouter-in-0`. The router can use `spring.cloud.function.definition` or `spring.cloud.function.routing-expression` in message headers or application properties according to the execution model.

### 12.1. Imperative Targets: Per-Message Headers Work

~~~java
@Bean
Consumer<Integer> evenHandler() {
    return value -> log.info("EVEN: {}", value);
}

@Bean
Consumer<Integer> oddHandler() {
    return value -> log.info("ODD: {}", value);
}
~~~

A message arriving at `functionRouter-in-0` can carry the header:

~~~text
spring.cloud.function.routing-expression:
    payload % 2 == 0 ? 'evenHandler' : 'oddHandler'
~~~

Because imperative consumers process one message at a time, the router can select `evenHandler` or `oddHandler` per event.

### 12.2. Reactive Targets: Do Not Use Headers to Switch Targets Between Items

If the target is a reactive function accepting `Flux<T>`, the function is invoked once to accept the publisher. Routing instructions via application properties pick the stream's target. Do not expect per-item headers inside the publisher to make `RoutingFunction` switch targets on every event.

### 12.3. Distinguish the Properties

| Property | Effect |
| --- | --- |
| `spring.cloud.stream.function.routing.enabled=true` | Enables event routing through Stream's `RoutingFunction` |
| `spring.cloud.function.definition` | Specifies the function or composition |
| `spring.cloud.function.routing-expression` | SpEL evaluating to the function definition to route to |

`routing.enabled` activates Stream's router mechanism; it does not turn reactive routing into per-message routing.

## 13. Spring Cloud Stream: Routing TO vs. Routing FROM

Spring Cloud Stream's Event Routing documentation distinguishes:

- **Routing TO Consumer:** choosing which consumer/function processes incoming messages.
- **Routing FROM Consumer:** choosing which destination receives outgoing messages.

### 13.1. Routing TO

Uses `RoutingFunction`, `spring.cloud.function.definition` or `spring.cloud.function.routing-expression` headers, or application properties.

### 13.2. Routing FROM

A function can return a `Message` containing the header:

~~~text
spring.cloud.stream.sendto.destination
~~~

Example:

~~~java
@Bean
Function<String, Message<String>> routeOutput() {
    return value -> MessageBuilder.withPayload(value)
        .setHeader(
            "spring.cloud.stream.sendto.destination",
            value.startsWith("order-") ? "orders-out" : "other-out"
        )
        .build();
}
~~~

This header instructs the framework to route **the output message to a destination**. It does not ask `FunctionCatalog` to select an input-processing function.

A reactive application may not route each incoming event to a different function via `spring.cloud.function.definition`, yet it might still need to send each output message to a different destination. Those are two separate problems.

## 14. HTTP Adapter: One Request Differs from One Publisher

The Spring Cloud Function web adapter can copy HTTP headers into message headers when creating a message for a function. With imperative functions, header routing can select the target.

Yet if the entry function takes a reactive publisher, an HTTP header:

~~~http
spring.cloud.function.definition: processOrders
~~~

does not cause the router to inspect a fresh header per element inside the body stream. Application properties remain the routing instruction source for reactive functions.

### 14.1. One HTTP Request Containing Multiple Events

For example, a request sends a JSON array:

~~~json
[
  {"eventType":"ORDER","eventId":"E-1","body":"..."},
  {"eventType":"INVOICE","eventId":"E-2","body":"..."}
]
~~~

The adapter may turn the request into a publisher or a collection payload depending on mapping and signature. Do not assume each array element becomes an independent invocation of `RoutingFunction`.

If per-item routing is required, verify whether request binding produces `Flux<Message<DomainEvent>>` or `Flux<DomainEvent>`, then branch inside the function.

### 14.2. Multiple Independent Requests vs. Multiple Events in One Publisher

If each HTTP request triggers a separate imperative invocation, each request's headers can choose a different target. If a single request streams a reactive body, the routing decision applies to that stream.

Always distinguish **multiple independent requests** from **multiple events inside one publisher**.

## 15. Serverless: Event Batches Do Not Automatically Become Per-Message Routing

Serverless adapters may receive a single event or a batch. A batch can be represented as an envelope or collection depending on the adapter/platform.

Questions to verify:

1. Does the handler receive one event or a batch?
2. Does the adapter invoke an imperative function once per record or a reactive function once with a publisher?
3. Are routing instructions in the event envelope, message headers, or application properties?
4. Does the business function receive each record as `Message<T>`?
5. Do retries apply to the whole batch or individual records?
6. If one record fails, do the remaining records continue?

Do not infer from the word "serverless" that routing is always per event. The unit of work is determined by the adapter and function signature.

If the adapter hands the batch over as `Flux<Message<DomainEvent>>`, use a reactive dispatcher as in section 9. If the adapter invokes an imperative function per record, `MessageRoutingCallback` or routing headers can be used. Verify your exact adapter/version before choosing.

## 16. Why Can Routing Headers Be Lost Even Before the Router?

Beyond reactive limitations, headers may fail to reach the boundary at all:

- The producer never sent the header.
- The broker/binder configuration does not propagate custom headers.
- The HTTP adapter does not copy the header due to mapping or allowlist rules.
- The header was renamed, coerced, or stripped.
- An earlier function built a new `Message` without copying required headers.
- A custom converter returned only a payload and dropped metadata.
- The router is not actually the entry function being invoked.

### 16.1. Headers Are Not Always Propagated by Default

If a function receives `Message<T>` and returns `Message<R>`, it can selectively copy headers:

~~~java
@Bean
Function<Message<OrderEvent>, Message<NormalizedOrder>> normalize() {
    return message -> MessageBuilder
        .withPayload(normalizeOrder(message.getPayload()))
        .setHeader(
            "correlationId",
            message.getHeaders().get("correlationId")
        )
        .setHeader(
            "eventType",
            message.getHeaders().get("eventType")
        )
        .build();
}
~~~

When returning `Message`, the framework handles payload conversion per contract without guaranteeing all input headers survive to output. Forward only headers that are necessary and valid for the next step.

### 16.2. Do Not Copy Unnecessary Routing Headers

Once a message has passed through the router, leaving `spring.cloud.function.definition` attached can mislead downstream steps or another adapter into re-routing by the old instruction. Propagate routing headers only if a downstream contract genuinely requires them.

### 16.3. Inspect Runtime Headers

~~~java
messages.doOnNext(message ->
    log.debug(
        "eventId={}, eventType={}, routeHeader={}",
        message.getHeaders().get("eventId"),
        message.getHeaders().get("eventType"),
        message.getHeaders().get("spring.cloud.function.definition")
    )
);
~~~

Never log full payloads or headers containing tokens or PII. Log approved IDs, relevant diagnostic header names, and payload types.

## 17. Routing Expressions and Security

`spring.cloud.function.routing-expression` uses SpEL to compute a function definition. Since routing expressions can alter which function executes, control their input sources carefully.

### 17.1. External Headers Are Untrusted Data

If an HTTP client or external producer can set:

~~~text
spring.cloud.function.definition
spring.cloud.function.routing-expression
~~~

callers may try selecting functions outside intended business scope. Never let external callers freely invoke administrative or internal functions.

### 17.2. SimpleEvaluationContext vs. Application Properties

Current SCF documentation distinguishes:

- Expressions from `Message` headers are evaluated with `SimpleEvaluationContext`, restricting capabilities compared to a full SpEL context.
- Expressions from application properties / system environment are evaluated with `StandardEvaluationContext`.

Context restrictions do not replace authorization. Enforce function target allowlists, secure Actuator/config endpoints, and restrict which callers may supply routing headers.

### 17.3. Safe Mapping

~~~java
@Bean
MessageRoutingCallback safeRouter() {
    Set<String> allowed = Set.of("processOrder", "processInvoice");

    return new MessageRoutingCallback() {
        @Override
        public String routingResult(Message<?> message) {
            String requested =
                message.getHeaders().get("target", String.class);

            if (!allowed.contains(requested)) {
                throw new IllegalArgumentException(
                    "Unsupported routing target: " + requested
                );
            }

            return requested;
        }
    };
}
~~~

This illustrates a function-name allowlist. In real systems, authenticate the caller/capability before permitting a target rather than letting headers grant access.

For reactive dispatch inside `Flux`, use a switch/allowlist as in section 9, and check tenant/event permissions if business rules require it.

## 18. Unroutable Messages: Target Missing from the Catalog

If the router computes a definition absent from `FunctionCatalog`, the framework may throw an exception for the unroutable message.

Spring Cloud Function provides the `DefaultMessageRoutingHandler` strategy to handle unroutable messages. Documentation notes its default behavior logs and lets the flow continue, effectively dropping unroutable messages; applications can register a custom implementation.

~~~java
@Bean
DefaultMessageRoutingHandler routingFailureHandler() {
    return new DefaultMessageRoutingHandler() {
        @Override
        public void accept(Message<?> message) {
            log.warn(
                "Unroutable message eventId={}",
                message.getHeaders().get("eventId")
            );
            deadLetterPublisher.publish(message);
        }
    };
}
~~~

This is a directional example; verify exact APIs/constructors/imports against your SCF version. Never use a handler to silently discard critical business events.

Distinguish three cases:

- **Unroutable:** the router received a routing instruction, yet the target does not exist or cannot resolve.
- **Reactive header has no effect:** the router does not use per-item headers as per-message routing instructions for a publisher.
- **Header lost:** an adapter/binder/function failed to propagate the header to the boundary.

## 19. Step-by-Step Diagnostic Workflow

~~~mermaid
flowchart TD
    START["Routing header does not change target"] --> SIG{"Is function input Message or Publisher?"}
    SIG -->|Message<T>| IMP["Imperative: inspect RoutingFunction"]
    SIG -->|Flux/Publisher<T>| REACT["Reactive: headers do not route per item"]
    IMP --> ENABLE{"Is router/adapter enabled and invoked?"}
    ENABLE -->|No| ROUTER["Enable routing or invoke functionRouter"]
    ENABLE -->|Yes| HEADER{"Did header reach the router?"}
    HEADER -->|No| PROP["Check producer, binder, adapter, header propagation"]
    HEADER -->|Yes| PRIORITY{"Is MessageRoutingCallback present?"}
    PRIORITY -->|Yes| CALLBACK["Callback takes priority over header"]
    PRIORITY -->|No| TARGET["Check definition, expression, target name"]
    REACT --> APP["Use application property for whole stream"]
    REACT --> BRANCH["If per-item needed: branch inside Flux"]
    APP --> VERIFY["Test actual target"]
    BRANCH --> VERIFY
    ROUTER --> VERIFY
    PROP --> VERIFY
    CALLBACK --> VERIFY
    TARGET --> VERIFY
~~~

### 19.1. Investigation Checklist

1. Inspect the actual function signature: `Function<T,R>` or `Function<Flux<T>,Flux<R>>`?
2. Determine whether the adapter calls the function once or once per event.
3. Confirm requests/messages actually enter `functionRouter`.
4. If imperative, verify exact header names and value types.
5. Check whether a `MessageRoutingCallback` is registered.
6. Check whether the callback takes priority and overrides headers.
7. Verify the header reaches the router instead of being dropped by broker/adapter.
8. If reactive, inspect effective application properties.
9. If per-item routing is required, add branching logic inside the reactive function.
10. Verify target functions exist in the catalog.
11. Verify SpEL expressions evaluate to valid definitions.
12. Check security/allowlists and unroutable-message handling.
13. Test one imperative message, then test a multi-event publisher.
14. Verify outputs, errors, ordering, backpressure, and side effects.

## 20. Observing Effective Routing Configuration

Settings in `application.yml` can be overridden by profiles, environment variables, or command-line arguments.

~~~java
@Component
class RoutingConfigurationInspector implements ApplicationRunner {

    private final Environment environment;
    private final FunctionCatalog catalog;

    RoutingConfigurationInspector(
            Environment environment,
            FunctionCatalog catalog) {
        this.environment = environment;
        this.catalog = catalog;
    }

    @Override
    public void run(ApplicationArguments args) {
        log.info("function.definition={}",
            environment.getProperty(
                "spring.cloud.function.definition", "<unset>"
            ));

        log.info("function.routing-expression={}",
            environment.getProperty(
                "spring.cloud.function.routing-expression", "<unset>"
            ));

        log.info("catalog.names={}", catalog.getNames(null));
    }
}
~~~

Enable the inspector only during diagnostics or at an appropriate log level. Do not dump the entire environment because it may contain secrets.

### 20.1. In Stream, Check Routing Enabled and Bindings

~~~properties
spring.cloud.stream.function.routing.enabled=true
~~~

And verify the input binding:

~~~text
functionRouter-in-0
~~~

If the app is binding `processOrders-in-0` directly, messages go straight to the reactive function and bypass `RoutingFunction`.

## 21. Testing Imperative Routing: Header Picks Target per Message

~~~java
@Bean
MessageRoutingCallback routeByType() {
    return new MessageRoutingCallback() {
        @Override
        public String routingResult(Message<?> message) {
            String type =
                message.getHeaders().get("eventType", String.class);

            return switch (type == null ? "" : type) {
                case "ORDER" -> "orderHandler";
                case "INVOICE" -> "invoiceHandler";
                default -> throw new IllegalArgumentException(
                    "Unsupported eventType: " + type
                );
            };
        }
    };
}

@Bean
Consumer<OrderEvent> orderHandler() {
    return event -> orderService.process(event);
}

@Bean
Consumer<InvoiceEvent> invoiceHandler() {
    return event -> invoiceService.process(event);
}
~~~

This is an imperative routing example. To test thoroughly, invoke `functionRouter` with individual `Message<?>` inputs and assert each matching handler runs. Because callbacks outrank headers/application properties, callback tests should confirm that precedence too.

Test two independent messages:

- Message A with `eventType=ORDER`.
- Message B with `eventType=INVOICE`.
- Invoke the router separately for each message.
- Verify A goes to `orderHandler`, and B goes to `invoiceHandler`.

Do not merge A and B into one `Flux` and use that test to claim per-message reactive routing works.

## 22. Testing Reactive Dispatch: Each Item Takes the Right Branch Inside Flux

~~~java
class ReactiveDispatchTest {

    @Autowired
    @Qualifier("dispatchEvents")
    Function<Flux<Message<InboundEvent>>, Flux<RoutedResult>> dispatchEvents;

    @Test
    void routesEachMessageInsideTheStream() {
        InboundEvent order =
            new InboundEvent("E-1", "order body");

        InboundEvent invoice =
            new InboundEvent("E-2", "invoice body");

        Message<InboundEvent> orderMessage =
            MessageBuilder.withPayload(order)
                .setHeader("eventType", "ORDER")
                .build();

        Message<InboundEvent> invoiceMessage =
            MessageBuilder.withPayload(invoice)
                .setHeader("eventType", "INVOICE")
                .build();

        StepVerifier.create(
                dispatchEvents.apply(
                    Flux.just(orderMessage, invoiceMessage)
                )
            )
            .expectNextMatches(result ->
                result.eventId().equals("E-1")
                    && result.handler().equals("ORDER")
            )
            .expectNextMatches(result ->
                result.eventId().equals("E-2")
                    && result.handler().equals("INVOICE")
            )
            .verifyComplete();
    }
}
~~~

This test proves **dispatch logic inside `Flux`** based on per-item headers. It does not test built-in `RoutingFunction` and does not prove headers can change reactive function targets per message.

### 22.1. Testing Unsupported Events

~~~java
StepVerifier.create(
        dispatchEvents.apply(Flux.just(unsupportedMessage))
    )
    .expectErrorMatches(error ->
        error instanceof IllegalArgumentException
    )
    .verify();
~~~

In real systems, you may choose a dead-letter/discard policy instead of terminating the whole stream. Design the policy explicitly, since one item error can terminate the publisher.

## 23. Testing Whole-Stream Routing with Application Properties

To test SCF reactive routing, configure the application property before context startup:

~~~properties
spring.cloud.function.definition=processOrders
~~~

Then feed a multi-event publisher into the selected reactive function. All events in the publisher are expected to go to `processOrders`.

If you change the property to:

~~~properties
spring.cloud.function.definition=processInvoices
~~~

the entire publisher goes to `processInvoices`.

This is **per-stream** routing, not routing by individual message header.

Do not mutate properties between items. Application properties configure the application context/runtime, not per-item metadata. Mutating system properties per event creates shared mutable state and race conditions. If multiple targets must run concurrently, branch inside the pipeline or separate streams/bindings.

## 24. Testing Spring Cloud Stream Event Routing

With Spring Cloud Stream, tests should verify three things:

1. `spring.cloud.stream.function.routing.enabled=true` is enabled when using `functionRouter`.
2. Input messages arrive on binding `functionRouter-in-0`.
3. Routing instructions are provided properly for the target kind.

### 24.1. Imperative Event Routing

Send individual messages with appropriate routing headers and assert the corresponding consumer receives each event.

### 24.2. Reactive Functions

When the target is a reactive function, configure application properties to choose the stream target. Do not send varying headers on items expecting `RoutingFunction` to re-pick targets per event.

### 24.3. Routing FROM

If the goal is sending each event's output to a different broker destination, test `spring.cloud.stream.sendto.destination` and output binding semantics. That is routing FROM, not choosing a reactive function by input header.

## 25. Testing the HTTP Adapter: One Request Differs from One Publisher

When the HTTP adapter turns headers into message headers, an imperative endpoint test can send:

~~~http
POST /functionRouter
Content-Type: application/json
spring.cloud.function.definition: processOrder
~~~

The actual path depends on web adapter config and function exports. Do not assume `/functionRouter` is always exposed; verify your application's routes.

For a reactive endpoint receiving a streamed body:

- The routing target is selected at stream level via application properties.
- Per-record headers in the body do not cause SCF to select a new target for that record.
- If per-record dispatch is needed, handle it inside `Flux` as shown in section 9.

## 26. Testing Serverless Adapters

In serverless, tests must reproduce the runtime's actual input shape:

- One invocation containing one event.
- One invocation containing a batch of records.
- One invocation creating a reactive publisher.
- An event envelope containing a nested `body`.
- Whether routing headers are mapped by the adapter into Spring `Message` headers.

Do not infer per-message routing from a test with one invocation / one event. If the runtime sends batches, confirm whether the adapter calls an imperative function per record or passes a single publisher to a reactive function.

## 27. Common Errors and How to Interpret Them

| Symptom | Possible cause | Evidence to inspect |
| --- | --- | --- |
| Definition header appears in logs, target unchanged | Reactive function receives a publisher | `Flux`/`Publisher` signature |
| `routing-expression` header ignored | Reactive routing does not use per-message headers | Unit of work |
| Callback does not run per event | Function is reactive | `MessageRoutingCallback` applies to imperative routing |
| Every item in `Flux` hits the same function | Routing property selects whole stream | Effective application properties |
| Header absent from `Message` | Adapter/binder did not propagate | Log headers at ingress |
| Router never invoked | Input bound directly to business function | Binding name/destination |
| Target does not exist | Definition typo or unregistered bean | `catalog.getNames(null)` |
| Routing header overridden | Callback has higher priority on imperative path | Callback bean |
| SpEL route fails to pick target | Bad expression or wrong header value | Expression output/logs |
| Messages dropped | Unroutable handler / default behavior | Routing handler and logs |
| Output lands on wrong topic | Confused route TO vs. route FROM | `sendto.destination` vs. function routing |
| HTTP request does not route | Header unmapped by web adapter or wrong route path | Web adapter config |
| Serverless batch hits only one target | Adapter turns entire batch into one publisher | Handler signature / event shape |

## 28. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "Adding `spring.cloud.function.definition` header always routes per event." | True only for imperative message routing; reactive routes the whole stream via application properties. |
| "`Flux<Message<T>>` has no headers." | Individual items can be `Message`; the built-in router simply does not route per item inside a reactive stream. |
| "`MessageRoutingCallback` runs once per item in `Flux`." | Callbacks belong to imperative routing. |
| "Setting `spring.cloud.stream.function.routing.enabled` fixes reactive per-message routing." | It enables `RoutingFunction`; it does not change the reactive unit of work. |
| "`definition` header and property work identically." | Headers attach to a message; properties configure the application. |
| "Switching from `definition` to `routing-expression` makes per-item routing work." | Neither provides per-message routing for reactive functions. |
| "You can mutate a system property per item." | Shared mutable state causes race conditions; not a per-event routing design. |
| "Putting the header inside the JSON payload lets the router read it." | The router still receives a publisher; the business function must inspect payloads inside the stream. |
| "`spring.cloud.stream.sendto.destination` picks the target function." | It routes output messages to a destination. |
| "Routing and composition are the same." | Composition chains steps sequentially; routing picks a target. |
| "Every HTTP request is a single reactive item." | One request can build a publisher with multiple items. |
| "Serverless always invokes the function once per record." | Depends on handler/adapter and event batching. |
| "Failure to route means a misspelled header name." | Could be reactive unit of work, callback precedence, adapter, or uninvoked router. |
| "Header expressions evaluate just like application properties." | Header expressions use a more restricted evaluation context. |
| "If the target is missing, messages are always rejected." | `DefaultMessageRoutingHandler` can handle unroutable messages, including dropping them. |

## 29. Architecture Selection Checklist

### 29.1. If Per-Message Routing Is Needed

- [ ] Imperative `Function`/`Consumer` receives one `Message<T>` per call.
- [ ] Messages flow through `functionRouter`.
- [ ] `spring.cloud.stream.function.routing.enabled` is enabled if using Stream Event Routing.
- [ ] Routing headers have the right names and values.
- [ ] No `MessageRoutingCallback` unintentionally overrides headers.
- [ ] Targets exist in `FunctionCatalog`.
- [ ] Routing targets enforce allowlists and authorization.

### 29.2. If Whole-Stream Reactive Routing Is Needed

- [ ] Function signature accepts `Flux<T>`/`Publisher<T>`.
- [ ] `spring.cloud.function.definition` or `routing-expression` is configured at application level.
- [ ] Instance profiles/environments select the expected target.
- [ ] Integration tests verify the whole publisher enters the selected target.
- [ ] Do not expect per-item headers to switch targets.

### 29.3. If Each Event in Flux Needs Its Own Branch

- [ ] Reactive function accepts `Flux<Message<T>>` when headers are needed, or a payload DTO with event type.
- [ ] Branching logic sits inside `map`, `flatMap`, `concatMap`, or a suitable operator.
- [ ] Handlers/services have clear input/output types.
- [ ] Ordering/concurrency rules are defined.
- [ ] Invalid events follow a dead-letter/reject policy.
- [ ] Tests use `StepVerifier` with multiple event types in one publisher.
- [ ] Real adapter tests confirm headers/payloads arrive intact.

## 30. Self-Assessment Questions

1. What is the unit of work of an imperative function?
2. What is the unit of work of a reactive function?
3. Why is `Function<Flux<Message<T>>,Flux<R>>` not routed per item by built-in routing headers?
4. Where can headers still be read inside a reactive function?
5. What are Spring Cloud Function's two primary routing headers?
6. How does the `spring.cloud.function.definition` header differ from the application property of the same name?
7. What role does `spring.cloud.function.routing-expression` play?
8. Why is `MessageRoutingCallback` suited to imperative routing?
9. What is the precedence among callbacks, message headers, and application properties in imperative routing?
10. For reactive functions, which routing instruction source is used?
11. Does setting `spring.cloud.stream.function.routing.enabled=true` change reactive limitations?
12. What is the input binding name of `RoutingFunction` in Spring Cloud Stream?
13. How do you route individual items inside a `Flux` based on an `eventType` header?
14. How do `concatMap` and `flatMap` differ in ordering and concurrency?
15. Why should you never change a system property between items to switch targets?
16. Is `spring.cloud.stream.sendto.destination` route TO or route FROM?
17. How does an HTTP request carrying a JSON array differ from multiple independent imperative requests?
18. How can a serverless adapter alter the unit of work?
19. Why can a header be lost before reaching `RoutingFunction`?
20. What case does `DefaultMessageRoutingHandler` handle?
21. Why do SpEL header expressions still require allowlisting and authorization?
22. What test would you write to prove per-item dispatch inside a `Flux`?
23. What would you test to prove application properties route an entire stream?
24. How do you distinguish routing not switching due to reactive semantics from the router never being invoked?

## 31. References

- [Spring Cloud Function — Programming Model, Function Routing](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — imperative vs. reactive unit of work, routing via `Message` headers, `MessageRoutingCallback`, application properties, and precedence.
- [Spring Cloud Stream — Event Routing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/event-routing.html) — enabling `spring.cloud.stream.function.routing.enabled`, `functionRouter-in-0` binding, routing TO Consumer, callbacks, and routing FROM Consumer.
- [Spring Cloud Function — Function Catalog](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html) — how functional beans are registered and wrapped by `FunctionCatalog`.
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/) — publisher lifecycles, operators, subscriptions, backpressure, and stream processing.
- [Project Reactor — Testing](https://projectreactor.io/docs/test/release/reference/) — `StepVerifier` for verifying reactive routing logic.
- [Spring Cloud Stream — Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html) — input/output binding names for functions and the router.

Examples use Java 17+, Spring Cloud Function 5.1.0, and current Spring Cloud Stream 5.1.0 reference docs. Specific APIs/adapters may vary by BOM, binder, and deployed version; verify function signatures and actual ingress paths before drawing conclusions.

**Takeaway:** Routing headers do not route individual events inside a reactive publisher because reactive functions are invoked once with **the entire stream**. Headers can still live on each `Message` and be read inside the Reactor pipeline, yet built-in `RoutingFunction` does not re-select targets per item. Use application properties to pick **one target for the whole stream**; if individual events need separate branches, branch inside `Flux` with strongly typed logic, or use an imperative function so every message is its own routing unit. Distinguish routing TO from `sendto.destination` routing FROM, verify adapters/bindings, and test multiple events inside a single publisher with `StepVerifier`.
