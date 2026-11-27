# `@Transformer`, `@Filter`, and `@Router` Methods in Spring Integration

## 1. Position of the Three Methods in a Message Flow

In Spring Integration, a message consists of a **payload** (business data) and **headers** (metadata such as `id`, `replyChannel`, `errorChannel`, and correlation identifiers). A `MessageChannel` moves messages between endpoints; an endpoint takes a message from a channel, invokes a processing component, and decides the next step.

These three annotations belong to the **handler adapter** group: Spring Integration can invoke plain Java methods (POJOs) as message endpoints without forcing business code to implement `MessageHandler` directly. They answer three distinct questions:

| Method Annotation | Question Handled | Return Value | Runtime Result |
| --- | --- | --- | --- |
| `@Transformer` | How should the message's **data/format be transformed**? | New payload or new `Message<?>`, **must not be `null`** | Creates an output message and sends it to the output channel. |
| `@Filter` | Should this message **continue forward**? | `boolean` or `Boolean` | `true`: forwards the original message to the output; `false`: rejects it, optionally discarding or raising an error. |
| `@Router` | Which **channel(s) should the message go to**? | Channel name, `MessageChannel`, or collection of targets | Sends the message to one or more selected channels. |

Order intake pipeline example:

~~~mermaid
flowchart LR
    A["ordersIn"] --> T["@Transformer normalize()"]
    T --> N["normalized"]
    N --> F{"@Filter valid()"}
    F -->|true| R["@Router route()"]
    F -->|false| D["rejected"]
    R -->|priority| P["priority"]
    R -->|standard| S["standard"]
~~~

A crucial pitfall: if a `@Transformer` method returns the string `"priority"`, that string is treated as the **new payload**, not a channel name. Conversely, when a `@Router` method returns `"priority"`, that is the **destination address**. `@Filter` returns `true`/`false` to decide acceptance, not to produce a Boolean payload.

## 2. From Annotation to Executing Endpoint

The process follows these main steps:

1. Spring registers the bean containing annotated methods, typically via `@MessageEndpoint` (a stereotype with `@Component` semantics) and component scanning; Spring Integration infrastructure is enabled via `@EnableIntegration` or appropriate auto-configuration.
2. The annotation processor creates a **consumer endpoint** along with the corresponding **message handler/adapter**; the Java method is called via parameter mapping based on payload, headers, and data types.
3. The endpoint subscribes to `inputChannel`. With subscribable channels (such as `DirectChannel`), the endpoint typically runs event-driven; with `QueueChannel`, a polling consumer and poller are needed to actively pull messages.
4. The handler interprets the return value according to its transformer, filter, or router role and sends the message onward. Channel configuration, advice, transactions, and executors determine how delivery actually occurs.

Thus **annotations describe endpoint behavior**; they do not automatically create background threads, retry logic, transactions, or durable persistence. An `IntegrationFlow` can wire these endpoints with channels, pollers, executors, gateways, error flows, and message stores; the methods themselves remain focused only on their declared logic.

When a method specifies `inputChannel = "normalized"`, that is the endpoint's **input**. `outputChannel = "accepted"` (where supported by the annotation) is where messages are sent next. If an endpoint produces a reply without an explicit output channel, the reply mechanism may look up `replyChannel` in headers. A router, by contrast, chooses destinations via route results and routing attributes rather than having a single output channel.

## 3. Declaring Methods and Parameter Mapping

Methods can receive the full `Message<T>`, only the payload of type `T`, one or more header values via `@Header`, or the header map via `@Headers`:

~~~java
@Transformer(inputChannel = "raw", outputChannel = "clean")
public Customer normalize(CustomerInput input,
                          @Header(value = "tenant", required = false) String tenant) {
    return new Customer(input.id().trim(), tenant);
}

// Alternative form: accept Message to inspect both payload and headers explicitly.
@Filter(inputChannel = "clean", outputChannel = "accepted")
public boolean acceptable(Message<Customer> message) {
    return message.getPayload().id() != null
            && !message.getPayload().id().isBlank();
}

// Alternative form: decide solely from metadata without reading the payload.
@Router(inputChannel = "toRoute")
public String routeByTier(@Header("tier") String tier) {
    return "gold".equals(tier) ? "priority" : "standard";
}
~~~

These are **three independent signature examples**, not a standalone runnable program. Corresponding target channels and consumers must also be declared.

- `@Header("tier")` reads a single header; by default the header is required to be present. Use `required = false` and handle `null` when the header may be absent.
- `@Headers Map<String, Object>` lets you inspect all headers. `@Payload` can explicitly mark the payload parameter in complex signatures.
- Payloads may be converted using converters integrated with the message conversion infrastructure; conversion failures or incompatible methods can surface at message-handling time.
- Avoid overloads with the same name and hard-to-distinguish parameter types unless necessary; clear signatures keep method selection deterministic and easy to diagnose.

### `@Transformer`: Changing Payload Without Dropping the Message

Accepting `OrderRequest` and returning `Order` fits the transformer's role. When a method returns a business object, Spring Integration builds a message with the new payload; eligible headers from the request are forwarded according to reply-building rules. When a method returns `Message<?>`, it can directly construct both the payload and headers of the outgoing message.

**Do not `return null` to discard a message.** A transformer requires a reply; returning `null` raises `MessageTransformationException`. If the goal is to block messages, place a separate `@Filter`. Returning `void` is also invalid for a transformer.

Example when headers need explicit modification:

~~~java
@Transformer(inputChannel = "raw", outputChannel = "clean")
public Message<String> normalize(Message<String> inbound) {
    return MessageBuilder.withPayload(inbound.getPayload().trim())
            .copyHeaders(inbound.getHeaders())
            .setHeader("normalized", true)
            .build();
}
~~~

`MessageBuilder` manages system headers such as ID and timestamp according to message creation rules; do not assume every system header will retain the exact same value as the source message.

### `@Filter`: Accepting or Rejecting Messages

When the method returns `true`, the filter forwards **the message under evaluation**, rather than replacing its payload with a Boolean value. For `false`, there are three main handling modes:

| Configuration | Behavior for Rejected Messages |
| --- | --- |
| No `discardChannel`, default no exception thrown | Drops the message; newer versions may log a warning about the discard. |
| `discardChannel = "rejected"` | Sends the rejected message to the `rejected` channel for logging, inspection, or separate handling. |
| `throwExceptionOnRejection = "true"` | Throws an exception on rejection, appropriate when rejection must be treated as a flow error. |

Explicit configuration example:

~~~java
@Filter(
    inputChannel = "clean",
    outputChannel = "accepted",
    discardChannel = "rejected")
public boolean isValid(Customer customer) {
    return customer.id() != null && !customer.id().isBlank();
}
~~~

You can use the `nullChannel` bean as the discard channel when dropping messages is truly intentional and you want to suppress discard warnings. Do not design a single case as both "normally discarded" and "must fail with exception" without defining the business rule clearly. Methods should return an unambiguous boolean result; never return `null` from a `Boolean` return type.

### `@Router`: Selecting One or More Channels

Common valid signatures:

~~~java
@Router(inputChannel = "toRoute")
public String choose(Order order) {
    return order.urgent() ? "priority" : "standard";
}

// Standalone variant: send the same message to multiple branches.
@Router(inputChannel = "broadcastInput", applySequence = "true")
public List<String> chooseMany(Order order) {
    return List.of("audit", "fulfillment");
}
~~~

A router may return a `String`, a `MessageChannel`, an array, or a collection of elements of those types. For string names, the endpoint must resolve each name to an actual channel. `channelMappings` maps route keys to channel names; `prefix` and `suffix` alter names prior to resolution.

Key options to pay attention to:

| `@Router` Attribute | Meaning |
| --- | --- |
| `defaultOutputChannel` | Fallback destination when no destination can be resolved and resolution mode permits it. |
| `resolutionRequired` (default `true`) | Requires route keys to resolve; otherwise raises an error. `"false"` allows ignoring unresolved destinations, combined with a fallback channel if configured. |
| `channelMappings` | Declares mappings such as `{"VIP=priority", "NORMAL=standard"}`, decoupling business keys from channel bean names. |
| `applySequence` | Adds sequence number/size metadata when distributing to multiple destinations; useful for downstream aggregation flows. |
| `ignoreSendFailures` | Controls how the router handles errors sending to a destination, especially with multiple targets. |

**Sending to multiple destinations does not mean every branch succeeds**: when using synchronous channels, an error on one branch can prevent sending to subsequent branches (unless send failures are ignored). Do not rely on multi-target routing as a guaranteed-delivery event broadcast mechanism.

## 4. Complete Example: Runtime Order Classification

The example below uses Java records (Java 17+) and Spring Boot with Spring Integration. All classes sit in the same component-scanned package. Each input passes through three methods in sequence: normalize -> validate -> route. All channels are `DirectChannel` so synchronous behavior is easy to observe.

~~~java
package demo.integration;

import java.util.Locale;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.annotation.Filter;
import org.springframework.integration.annotation.MessageEndpoint;
import org.springframework.integration.annotation.Router;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.annotation.Transformer;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
@EnableIntegration
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean MessageChannel ordersIn()   { return new DirectChannel(); }
    @Bean MessageChannel normalized() { return new DirectChannel(); }
    @Bean MessageChannel accepted()   { return new DirectChannel(); }
    @Bean MessageChannel priority()   { return new DirectChannel(); }
    @Bean MessageChannel standard()   { return new DirectChannel(); }
    @Bean MessageChannel rejected()   { return new DirectChannel(); }

    @Bean
    ApplicationRunner sample(@Qualifier("ordersIn") MessageChannel in) {
        return args -> {
            in.send(MessageBuilder.withPayload(
                    new OrderRequest("  a-01  ", 1_500_000))
                    .setHeader("traceId", "t-001").build());
            in.send(MessageBuilder.withPayload(
                    new OrderRequest(" b-02 ", 150_000))
                    .setHeader("traceId", "t-002").build());
            in.send(MessageBuilder.withPayload(
                    new OrderRequest("   ", -10))
                    .setHeader("traceId", "t-003").build());
        };
    }
}

record OrderRequest(String id, long amountMinorUnits) {}
record Order(String id, long amountMinorUnits) {}

@MessageEndpoint
class OrderMethods {

    @Transformer(inputChannel = "ordersIn", outputChannel = "normalized")
    public Order normalize(OrderRequest input) {
        return new Order(input.id().trim().toUpperCase(Locale.ROOT),
                         input.amountMinorUnits());
    }

    @Filter(inputChannel = "normalized",
            outputChannel = "accepted",
            discardChannel = "rejected")
    public boolean valid(Order order) {
        return !order.id().isBlank() && order.amountMinorUnits() > 0;
    }

    @Router(inputChannel = "accepted")
    public String route(Order order) {
        return order.amountMinorUnits() >= 1_000_000
                ? "priority" : "standard";
    }

    @ServiceActivator(inputChannel = "priority")
    public void onPriority(Order order) {
        System.out.println("PRIORITY " + order.id());
    }

    @ServiceActivator(inputChannel = "standard")
    public void onStandard(Order order) {
        System.out.println("STANDARD " + order.id());
    }

    @ServiceActivator(inputChannel = "rejected")
    public void onRejected(Order order) {
        System.out.println("REJECTED " + order.id());
    }
}
~~~

To run the example, the project needs Spring Boot, the Spring Integration starter matching your Spring Boot version, and package `demo.integration` within component-scan scope. The example uses `System.out` for visibility; real applications should use structured logging with correlation IDs and omit sensitive data.

| Inbound Message | After `normalize()` | `valid()` | Branch Invoked |
| --- | --- | --- | --- |
| `("  a-01  ", 1_500_000)` | `("A-01", 1_500_000)` | `true` | `priority` |
| `(" b-02 ", 150_000)` | `("B-02", 150_000)` | `true` | `standard` |
| `("   ", -10)` | `("", -10)` | `false` | `rejected`; router is not called |

On the `rejected` branch, the consumer receives the `Order` produced by the transformer, because the filter runs **after** the transformer. The `traceId` header can be accessed in later steps via `@Header("traceId")`. When all channels are `DirectChannel`, `send()` may run the entire handler chain on the calling thread; this matters if any handler blocks on I/O or throws an exception.

## 5. Threading, Pollers, and Transactions

Annotations alone do not decide the thread count. **The channel type at each boundary** is the decisive factor:

| Channel / Consumer | Runtime Behavior | Design Consequence |
| --- | --- | --- |
| `DirectChannel` | Invokes subscriber on the sending thread (synchronous). | Errors typically propagate back to the sender; one slow method slows down upstream callers. |
| `ExecutorChannel` | Hands off processing to a `TaskExecutor`. | Introduces an async boundary; manage queues, worker counts, and error handling appropriately. |
| `QueueChannel` + polling consumer | Buffers messages in a queue; endpoint pulls on a poll schedule. | Requires a poller; handles bursty/paced loads, and requires sizing capacity and backpressure. |
| `PublishSubscribeChannel` | Distributes to subscribers, synchronously or asynchronously depending on executor. | Suited for fan-out; unlike `DirectChannel`, which typically dispatches to one subscriber per message. |

If you change `ordersIn` to a `QueueChannel`, the endpoint reading from it needs a poller, for example (an **alternative configuration** for the `normalize` annotation in the previous example):

~~~java
@Transformer(
    inputChannel = "ordersIn",
    outputChannel = "normalized",
    poller = @Poller(fixedDelay = "1000", maxMessagesPerPoll = "10"))
public Order normalize(OrderRequest request) {
    return new Order(request.id().trim(), request.amountMinorUnits());
}
~~~

This variant requires importing `org.springframework.integration.annotation.Poller`, and the `ordersIn` bean must be a pollable type (`QueueChannel`); do not attach a poller to a `DirectChannel`. On the same endpoint annotation, `poller` and `reactive` are mutually exclusive options in versions supporting reactive endpoints.

Regarding transactions:

- In a synchronous `DirectChannel` chain, the caller thread's transaction can encompass downstream handlers depending on where the transaction begins and which advice/proxies apply.
- Across an `ExecutorChannel` or polling consumer, execution moves to another thread/context; thread-bound transactions **do not automatically cross** that boundary. Define transactions per segment or on the poller and backing store.
- Retries can be configured using handler advice (such as `RequestHandlerRetryAdvice`). Advice on one endpoint does not automatically wrap all downstream branches; with routers and filters, consider idempotency upon re-execution.
- An in-memory `QueueChannel` is not a durability guarantee. If restart recovery is needed, consider a persistent `MessageStore` or a message broker with proper acknowledgments.

Likewise, correlation headers (such as `correlationId`) help link logs and branches together; they do not automatically turn a router into an aggregator or guarantee results converge back to one place. If you route to multiple targets and later combine results, design correlation, release strategy, timeouts, and a message store for the aggregation step.

## 6. Errors, Retries, and Flow Control

Categorizing errors properly makes diagnosis much faster:

| Symptom | Common Cause | How to Check / Resolve |
| --- | --- | --- |
| `@Transformer` throws `MessageTransformationException` | Method returns `null` or fails to produce a valid payload. | Check input data; use `@Filter` when valid messages need to be dropped. |
| Message disappears after filter | Method returns `false`, no discard channel configured or discard channel has no subscriber. | Log rejection conditions; configure `discardChannel` for visibility. |
| Router reports channel resolution failure | Route result does not match a channel bean; `resolutionRequired` requires resolution by default. | Check names, `channelMappings`, prefix/suffix, and channel consumers. |
| `MessageDeliveryException` / `Dispatcher has no subscribers` | Sent to a channel with no active consumer or delivery failed. | Verify endpoint scanning, start/stop state, and channel wiring. |
| Handler never runs with `QueueChannel` | Missing polling consumer/poller, or poller has not started. | Inspect `@Poller`, `autoStartup`, phase, and scheduling configuration. |
| Messages arrive but latency grows | Method blocks on I/O over `DirectChannel`, executor/poller queues build up. | Measure time per endpoint, queue depth, and pool saturation; offload heavy work deliberately. |
| Errors only appear on async flows | Exceptions no longer propagate directly to the sending thread; error handling is unobserved. | Configure and monitor error flows/`ErrorMessage`, and `errorChannel` header where appropriate. |

For synchronous processing, method exceptions typically propagate back to the caller through the chain. In asynchronous or polled flows, errors are typically published as `ErrorMessage` according to the endpoint/error handler configuration; do not assume a `try/catch` around `send()` will catch errors thrown later on another thread.

Pattern for distinguishing business decisions from infrastructure errors:

- `@Filter` returns `false` when data is syntactically valid but fails an **acceptance rule** (for example, an ineligible order).
- Throw an exception when a rule cannot be evaluated due to an infrastructure failure (for example, lookup service unavailable); handle with bounded retries, backoff, and dead-letter/error flows.
- `@Router` picks an **explicitly designed** fallback branch for business cases without a route; do not set `resolutionRequired = "false"` merely to hide a typo in a channel name.

When retrying or replaying messages, methods with side effects must be idempotent by business key—especially if a router already succeeded on the first branch before failing on the second.

## 7. Lifecycle Management and State Observability

Method annotations create Spring-managed endpoints, so options like `autoStartup`, `phase`, `poller`, and `adviceChain` bind to the **generated endpoint** rather than directly modifying the business POJO bean. Endpoints can be controlled through Spring Integration's lifecycle/management mechanisms when enabled. With integration flows registered dynamically via `IntegrationFlowContext`, distinguish starting/stopping/removing a **flow registration** from container-scanned method annotations; they are two separate declaration and management models.

When diagnosing runtime behavior, trace a message across these checkpoints:

1. **Ingress:** which channel received the message, and what `id`/`traceId`/`correlationId` does it carry?
2. **Transformer:** do input and output payloads have expected types, no `null` return, and how long did processing take?
3. **Filter:** what was the `true`/`false` condition, discard rate, and is there a consumer on the discard channel?
4. **Router:** what were the route key and target channel(s), did they resolve, and were there send failures?
5. **Target consumer:** is the endpoint running, which thread is executing it, and do queues/executors still have capacity?

Emit metrics for inbound/outbound counts, discards, and errors per endpoint wherever observable; include correlation IDs in logs to connect steps across thread switches. Avoid writing payloads containing private data to production logs.

## 8. Verification Exercises and Edge Cases

Use the example in section 4 to verify the following behaviors yourself:

1. Send the three sample inputs and verify the results in the table. Log thread names in `normalize`, `valid`, `route`, and `onPriority` to confirm synchronous behavior.
2. Temporarily make `normalize` return `null` in a test environment. Verify it throws an error instead of routing to `rejected`; restore the correct implementation right after testing.
3. Change `route` to return a nonexistent channel name; observe the resolution error. Only afterward test `resolutionRequired = "false"` alongside a `defaultOutputChannel` that has a consumer to understand fallback behavior.
4. Try returning `List.of("priority", "standard")` from `@Router` in a test config, observe both consumers receiving the message, and inspect how `applySequence` affects metadata.
5. Replace the input boundary with a `QueueChannel` and configure an appropriate poller. Measure latency/throughput under multiple messages; observe the thread change and how exceptions are handled.

Common pitfalls to avoid: using a transformer to "filter by returning `null`"; returning a Boolean from a router to pick a branch; forgetting a subscriber on target channels; forgetting a poller for pollable channels; calling slow APIs inside a filter method on `DirectChannel`; assuming retries, transactions, and correlation appear automatically just from adding annotations.

## 9. Official Reference Documentation

- [Spring Integration — Annotation Support](https://docs.spring.io/spring-integration/reference/configuration/annotations.html): method detection, parameter mapping, input/output channels, and endpoint creation.
- [Spring Integration — Transformer](https://docs.spring.io/spring-integration/reference/transformer.html): POJO transformers, headers, and the non-`null` return rule.
- [Spring Integration — Filter](https://docs.spring.io/spring-integration/reference/filter.html): selector semantics, discard channels, and rejection exceptions.
- [Spring Integration — Router annotation](https://docs.spring.io/spring-integration/reference/router/annotation.html): router return types and header-based routing.
- [Javadoc `@Transformer`](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/Transformer.html), [`@Filter`](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/Filter.html), [`@Router`](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/Router.html): configuration attributes and endpoint behavior.
