# Asynchronous Send Mode and Context Propagation by Supported Version

`StreamBridge` enables a component not triggered by a Spring Cloud Stream input binding to send data to an output binding. The data source can be a REST controller, a scheduled task, a callback from an external library, or a traditional Spring MVC business flow. `StreamBridge` feeds data into the same Spring Cloud Stream output pipeline, including data type conversion and partitioning per producer configuration.

By default, sending uses the caller's thread and is blocking. Starting from Spring Cloud Stream 4.1.1, the `StreamBridge.setAsync(true)` API lets you switch sending to an asynchronous execution channel. When work crosses onto another thread, contexts stored in `ThreadLocal` may no longer be present. Micrometer Context Propagation helps propagate registered contexts—especially Observation/Tracing contexts—across this thread boundary.

The two mechanisms must be understood separately: asynchronous sending changes how threads perform message dispatch; context propagation preserves execution-flow metadata when switching threads. Neither by itself guarantees that the broker has durably stored the message or that a consumer has processed it successfully.

## 1. When to use StreamBridge?

The `Supplier`, `Function`, and `Consumer` functional model is the natural choice when data sources and sinks are already expressed as application bindings. Yet some components produce data outside that model. For example:

- A REST endpoint accepting an order creation request and publishing an `OrderCreated` event.
- A periodic task reading data from a legacy system and sending records to the broker.
- A callback from a payment library needing to publish a `PaymentCompleted` event.
- A Spring MVC service needing to send messages to Kafka, RabbitMQ, or Pulsar without declaring a `Supplier` solely to trigger it manually.

In these scenarios, `StreamBridge` provides a way to send to an output binding by binding name:

```java
streamBridge.send("orders-out-0", orderCreated);
```

The first argument is the output binding name. The second argument is the object or `Message<?>` to send. If passing a POJO, Spring Cloud Stream applies output conversion and partitioning according to the binding. If passing a `Message`, the message headers are also included in output processing.

`StreamBridge` does not replace the entire functional model. If the data source is inherently a framework-managed `Supplier`, let the function binding handle publishing. `StreamBridge` is useful when the publishing source lies outside that trigger mechanism or when application code must proactively send at a specific point.

## 2. Synchronous sending is the default

By default, `StreamBridge.send(...)` uses the caller's thread. If a REST controller calls `send`, the request-handling thread performs the send through the output channel. This means the request may have to wait for the send to complete to the extent performed by the channel/binder.

Synchronous sending fits when:

- Traffic is low or moderate and send latency does not noticeably impact requests.
- The caller needs to know immediately whether the send operation was accepted by the channel.
- Current thread context must be preserved throughout the call.
- A simpler execution flow that is easier to observe during debugging is desired.

Example of a synchronous sending endpoint:

```java
@RestController
public class OrderController {
    private final StreamBridge streamBridge;

    public OrderController(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    @PostMapping("/orders")
    public ResponseEntity<Void> create(@RequestBody OrderCreated event) {
        boolean accepted = streamBridge.send("orders-out-0", event);
        return accepted
                ? ResponseEntity.accepted().build()
                : ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build();
    }
}
```

The boolean value indicates the send operation was accepted by the output channel per the channel's contract. It is not proof that the broker durably wrote the message, that the consumer received it, or that business logic finished. With binders supporting asynchronous send confirmations, send results must be handled through the binder's own mechanism.

## 3. Enabling async send per supported version

The `setAsync(boolean)` API was added to `StreamBridge` starting in Spring Cloud Stream 4.1.1. With this version or newer supporting the API, call `setAsync(true)` before sending to enable asynchronous mode:

```java
@Configuration
public class StreamBridgeConfiguration {

    @Bean
    ApplicationRunner enableAsyncStreamBridge(StreamBridge streamBridge) {
        return args -> streamBridge.setAsync(true);
    }
}
```

Configure it once at application startup. `StreamBridge` is a shared bean across the application; do not toggle `setAsync` per request because multiple requests can run concurrently and share the same setting. If two different send policies are needed, design two intentional sending paths and verify your version's capabilities.

When using async send, the `send` call can return before sending through the channel completes. The request thread does not wait for the entire send work as in the default mode. This is useful when an endpoint needs fast ingestion, though it also means errors arising after dispatch may not be thrown directly back onto the calling thread.

Async send does not mean every step inside `StreamBridge.send` runs on a background thread. Binding resolution, message preparation, and some payload conversion may occur before the message is handed off to the output channel. Therefore, still measure actual timings with the binder and version in use; do not treat `setAsync(true)` as a guarantee that the entire call is always non-blocking.

### 3.1. Declaring the output binding

For destinations known in advance, explicitly declare the binding in `application.yml`:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders
          content-type: application/json
```

`destination` is the topic, exchange, or logical target mapped by the binder to the broker. The binding name in the `send` call must match the declared name. With the configuration above, `StreamBridge` can create the output binding on the first send and reuse it for subsequent sends.

If you want the binding created before the application receives requests, also declare `spring.cloud.stream.output-bindings` with the output binding name. Pre-creating channels and how `setAsync(true)` applies to those channels can depend on the binding creation path and specific version; verify with integration tests rather than assuming every pre-created channel turns into an executor channel.

Dynamic binding creation is convenient when the destination is only known at runtime, but you must restrict the destination set and monitor the cache. An application creating an unbounded number of dynamic destinations can increase memory usage and binding creation overhead.

### 3.2. Older versions

If a project uses Spring Cloud Stream earlier than 4.1.1, do not assume `StreamBridge.setAsync(true)` is available. Check the Javadoc of the exact version in your dependencies. If async sending is needed on a version that does not support this API, you can use an application-managed executor to call `send` from a background task, but then the application must manage executor lifecycle, queue bounds, task rejection, background errors, and context propagation itself. Avoid unbounded executors or spawning a new thread per request.

Do not upgrade Spring Cloud Stream alone to an arbitrary version just to get a new API. Pick a Spring Cloud release train compatible with your project's Spring Boot version, then use the corresponding BOM to manage library versions.

## 4. Example REST endpoint sending asynchronously with business metadata

A message can carry `eventId` and `correlationId` so downstream services link the event to the initial request. These business values should be explicitly placed in the payload or headers rather than existing only in `ThreadLocal` or the HTTP thread's MDC.

```java
@RestController
public class OrderIngressController {
    private final StreamBridge streamBridge;

    public OrderIngressController(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    @PostMapping("/orders")
    public ResponseEntity<Void> publish(
            @RequestBody OrderCreated event,
            @RequestHeader(value = "X-Correlation-Id", required = false)
                    String correlationId) {

        MessageBuilder<OrderCreated> builder = MessageBuilder
                .withPayload(event)
                .setHeader("eventId", event.eventId());

        if (correlationId != null && !correlationId.isBlank()) {
            builder.setHeader("correlationId", correlationId);
        }

        boolean accepted = streamBridge.send("orders-out-0", builder.build());
        return accepted
                ? ResponseEntity.accepted().build()
                : ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build();
    }
}
```

In the application, `setAsync(true)` is called once at startup as in the previous section's example. The endpoint simply creates the message and sends it. The `eventId` header holds the business event identifier; `correlationId` links the message to the request or related processing steps. If the system has ID formatting rules, validate them before sending.

HTTP `202 Accepted` in the example only indicates the application accepted the send request based on the result returned by `StreamBridge.send`. It does not confirm the message was saved by the broker or processed by a consumer. If the API needs a stronger commitment, design the response based on actual broker confirmation mechanisms or durably persisted business state.

## 5. Propagating Observability context across thread boundaries

In synchronous mode, sending code runs on the caller's thread. Contexts backed by `ThreadLocal` can be read on the same thread. When switching to async send, the work executes on another thread. The HTTP thread's `ThreadLocal` does not automatically appear on the sending thread.

This can affect:

- Current trace/span and parent-child relationships in distributed traces.
- Observation context used to correlate metrics and traces.
- MDC or thread-bound logging information.
- Custom application contexts kept in `ThreadLocal`.

Spring Cloud Stream supports Micrometer Context Propagation for async send. Add the `io.micrometer:context-propagation` dependency compatible with your project's BOM:

```kotlin
dependencies {
    implementation("io.micrometer:context-propagation")
}
```

If dependencies are managed by the Spring Boot/Spring Cloud BOM, let the BOM select a compatible version instead of pinning an older version in the build file. For projects without a BOM, choose a Micrometer Context Propagation version compatible with the Spring Cloud Stream and Micrometer versions in use.

When the library is present, Spring Cloud Stream versions supporting this mechanism can wrap `StreamBridge`'s executor with a context-aware executor to capture registered contexts on the calling thread and restore them when the task runs. Async send must be enabled and the application's Observability/Tracing properly configured; merely adding the dependency does not enable full tracing if the system has not configured Observation or a tracer.

### 5.1. Context propagation does not replace message headers

Micrometer Context Propagation handles contexts across threads within the same process. Once a message crosses the broker into another process, the producer's `ThreadLocal` does not exist at the consumer. To pass business metadata across the broker, put it in the payload or message headers:

| Information type | Appropriate propagation method |
|---|---|
| Trace/span context | Use Observability/Tracing integration and propagation headers supported by Spring/binder |
| `correlationId`, `tenantId`, `eventId` | Place explicitly in payload or custom headers per application contract |
| Credentials or secrets | Use proper security mechanisms; do not put sensitive tokens in message headers without protective design |
| Temporary variables solely for single-request logging | MDC or local context; do not treat as durable message data |

If the application uses a custom `ThreadLocal`, Micrometer can only propagate its value when a corresponding accessor is registered with Context Propagation. Do not assume every `ThreadLocal`, MDC, or custom `SecurityContext` is automatically copied. Check the accessors provided by integration libraries or register an accessor for your custom context using the Micrometer version's API.

## 6. Distinguishing different types of asynchronicity

In a Spring Cloud Stream application, several distinct async layers may exist. They solve different problems:

| Mechanism | Impact | What it does NOT guarantee by itself |
|---|---|---|
| `StreamBridge.setAsync(true)` | Moves dispatch through the output channel to StreamBridge's async execution mechanism | Does not confirm the broker stored the message |
| Broker producer client async send | Client may send in background and return results via its own callback/future API | Does not automatically propagate the StreamBridge caller thread's context |
| Micrometer Context Propagation | Captures/restores registered contexts when tasks switch threads | Does not serialize contexts into business data across the broker |
| `@Async` or application executor | Runs the send method in an application-managed executor | Does not configure binder, retries, confirmations, or DLQ |
| Reactive API | Expresses processing chains via `Publisher` and operators | Does not turn a blocking binder into reactive or create cross-system back-pressure |

Do not enable multiple async layers merely to make an endpoint respond quickly. Every additional thread boundary increases complexity around context, ordering, errors, and shutdown. Pick one clear responsibility point for dispatch and test the entire path.

## 7. Handling send results and async errors

In async send, errors may surface after the calling thread has already received a result from `send`. Therefore, do not rely solely on the boolean return value to track publishing. Check the following mechanisms per binder and version:

1. **Pre-dispatch errors:** binding creation, payload conversion, or producer configuration errors may surface immediately during the call.
2. **Channel/executor errors:** the task may be rejected or fail during background execution.
3. **Producer client errors:** the broker may reject or fail to confirm the send after the task has been dispatched.
4. **Post-broker errors:** the consumer may fail processing; this is a consumer-side retry/DLQ concern, separate from publish errors.

With binders supporting asynchronous send results, the `errorChannelEnabled` producer property can route send errors to the destination's error channel:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          producer:
            error-channel-enabled: true
```

This property only takes effect when the binder supports asynchronous send results and is configured per the exact version. It is not a generic callback guaranteed to catch every executor exception or every consumer business error. Check the documentation of the binder in use and register appropriate handlers/monitors for the error channel.

At minimum, monitor requested sends, channel rejections, producer errors, send latency, messages routed to the error channel, and messages processed by consumers. Logs should include `eventId`, `correlationId`, binding, and destination to trace a message across components.

## 8. Delivery guarantees and ordering

Async send improves decoupling of the request thread from send work, but does not increase broker delivery guarantees. It does not provide exactly-once delivery, replace transactions, or guarantee messages survive if the process stops while tasks are queued.

For business-critical events, consider these principles:

- Store business changes and outbox records in the same database transaction; a separate publisher reads the outbox and sends via `StreamBridge`.
- Use stable `eventId` values and idempotent consumers to handle redelivered messages.
- If the binder/broker provides producer confirms, acknowledgments, or transactions, configure and test them per that broker.
- Do not respond with HTTP success implying "durably delivered" if the application only knows the channel accepted the send task.
- On shutdown, establish a policy to drain or reprocess incomplete tasks; do not rely on an executor's memory as a durable queue.

Sending from multiple threads can also make completion order differ from request arrival order. If events for the same order must stay ordered, use the business key as the partition key, ensure events with the same key go to the same partition/queue per binder capabilities, and design consumers to process order per broker semantics. Never infer ordering solely from the order of `send` calls across different threads.

## 9. Testing async send and context propagation

Tests should verify both sending and what happens after switching threads. You can use `StreamOperations` in services for easy mocking in unit tests; `StreamBridge` implements this contract.

Test groups to include:

- **Unit tests:** verify the correct binding name, payload, `eventId`, `correlationId`, and content type are passed to `send`.
- **Async behavior tests:** verify callers do not wait for send task completion in async scenarios; use latches or synchronization in tests instead of arbitrary `Thread.sleep`.
- **Context tests:** create an Observation/trace or registered context before calling send, and verify the background task sees the corresponding context.
- **Custom ThreadLocal tests:** verify registered accessors capture and restore values, and also verify values are cleared after task completion to prevent context leakage across tasks.
- **Integration tests:** use a real broker or equivalent test environment to verify messages are received, required headers remain intact, and producer errors are observed.
- **Failure tests:** simulate broker rejection, executor task rejection, application shutdown with pending tasks, and consumer error handling.
- **Ordering tests:** send multiple messages with the same key and verify ordering per actual binder/broker guarantees.

Never test only that `send()` returns `true`. An integration test must prove the message actually arrives at the destination or the consumer receives the payload per contract.

## 10. Common pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| `setAsync` not found at compile time | Spring Cloud Stream older than 4.1.1 or incompatible dependency/BOM | Check actual version and select a compatible release train |
| Broken trace after enabling async | Context not propagated across executor or missing Observability config | Add compatible Micrometer Context Propagation and check tracer/accessors |
| `correlationId` missing at consumer | Value stored only in MDC/ThreadLocal without putting it in the message | Attach header or payload before calling `send` |
| `send()` returns `true` but consumer receives nothing | Boolean does not confirm the entire broker/consumer pipeline | Check producer results, broker metrics, destination, and consumer group |
| Exception does not appear in REST request | Error occurred after the task was dispatched | Monitor binder error channel/logs/metrics and design compensating handling |
| Events for the same order arrive out of order | Multiple threads sending concurrently or inconsistent partition keys | Choose a stable partition key and test ordering on the broker |
| Events lost when application stops | Send tasks still in executor memory with no durable store | Use an outbox or durable storage and replay mechanism |
| Previous request's context leaks into a later task | Accessor failed to reset context or improper thread reuse | Check accessor, scope, and context cleanup after task completion |

## 11. Pre-deployment checklist

- [ ] Use `StreamBridge` for data sources outside the function binding model.
- [ ] Spring Cloud Stream version supports `setAsync(true)`; API available since 4.1.1.
- [ ] Async mode is configured once at startup, not toggled arbitrarily per request.
- [ ] Output bindings and destinations are explicitly declared if known; dynamic destinations are restricted.
- [ ] Channel acceptance is distinguished from broker confirmation and consumer processing.
- [ ] Micrometer Context Propagation and Observability/Tracing are configured compatibly.
- [ ] Custom contexts have accessors; business data crossing the broker is placed in payload/headers.
- [ ] Async send errors have error handling and metrics suited to the binder.
- [ ] Idempotency, outbox, or an equivalent mechanism exists for critical events.
- [ ] Context, send errors, shutdown, and message ordering have been tested in the deployment configuration.

`StreamBridge.setAsync(true)` decouples message dispatch from the calling thread when supported by the Spring Cloud Stream version. Micrometer Context Propagation preserves registered contexts across thread boundaries so traces and logs remain unbroken. Applications still must pass business metadata in messages, monitor post-dispatch errors, and use durable mechanisms such as an outbox when event loss cannot be tolerated.

## References

- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream 4.1.1 release notes — async send for StreamBridge](https://github.com/spring-cloud/spring-cloud-stream/releases/tag/v4.1.1)
