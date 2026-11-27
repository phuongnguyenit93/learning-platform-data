# Signature Constraints and Per-Adapter Support

## 1. Why might a valid signature not run in every environment?

In **Spring Cloud Function** (module `SPRING_CLOUD_FUNCTION`), business logic is packaged as `Supplier`, `Function`, and `Consumer` beans so it can be reused without being tightly coupled to HTTP, a message broker, or a serverless provider. `FunctionCatalog` enables lookup, normalization, composition, and message conversion based on declared data types. However, **what a Java function can express differs from what an adapter can connect**.

For example, both signatures below define a `Function`:

~~~java
Function<String, String> normalize;

Function<Flux<String>, Tuple2<Flux<String>, Flux<String>>> split;
~~~

The `normalize` function has **one input value, one output value**, so it maps relatively directly to an HTTP request/response, an input/output message, or a serverless invocation. The `split` function, on the other hand, has **one input stream, two output streams**. That makes natural sense when an adapter supports **two independent output bindings**, but it does not mean a single HTTP request will produce two HTTP responses or a single Lambda invocation will automatically publish to two topics.

In the **Multiple Inputs/Outputs** chapter, distinguish three layers:

1. **Java signature and logic:** Which types are declared in `Supplier`, `Function`, and `Consumer`?
2. **Spring Cloud Function:** Can `FunctionCatalog` recognize, normalize, and convert types for that signature?
3. **Adapter/binder:** Can the runtime environment create the corresponding number of sources/targets, manage subscriptions, convert data, guarantee delivery, and handle errors?

> **Design principle:** A signature that is valid in Java, or resolvable via `FunctionCatalog`, **does not automatically guarantee** that every adapter supports the same number of inputs, outputs, and operational semantics.

## 2. Foundational signatures and their inherent constraints

Spring Cloud Function uses Java's three standard functional interfaces while also supporting Project Reactor reactive types:

| Signature | Logical contract | Things to watch out for |
| --- | --- | --- |
| `Supplier<O>` | 0 in → 1 out | No input to trigger it; the adapter decides when to call `get()` |
| `Function<I, O>` | 1 in → 1 out | Relatively straightforward for request/response and per-message processing |
| `Consumer<I>` | 1 in → 0 out | `accept` returns `void`; business effect is primarily a side effect |
| `Supplier<Flux<O>>` | 0 in → 1 output stream | Reactive source can be long-lived or unbounded; lifecycle and emission depend on adapter |
| `Function<Flux<I>, Flux<O>>` | 1 input stream → 1 output stream | Can transform multiple events within one reactive pipeline |
| `Function<Flux<I>, Mono<Void>>` | 1 input stream → emits no result payload | Reactive processing pattern with a completion signal, often preferable to `Consumer<Flux<I>>` in messaging |
| `Consumer<Flux<I>>` | Takes a publisher, returns `void` | Framework receives no returned publisher to subscribe to; implementation must manage subscription |

### 2.1. Imperative and reactive function invocations differ

In Spring Cloud Stream, an imperative `Function<I, O>` is typically invoked **per message**. By contrast, a reactive `Function<Flux<I>, Flux<O>>` is invoked to **wire up the pipeline**; afterward, items flow through the stream without invoking `apply` again for each record.

~~~text
Imperative
message A ─> apply(A) ─> result A
message B ─> apply(B) ─> result B
message C ─> apply(C) ─> result C

Reactive
Source Flux ─> apply(Source Flux) ─> Result Flux
                  (sets up pipeline)
Subsequent messages flow through the already-wired pipeline.
~~~

This difference affects retries, error handlers, and per-message routing. In Spring Cloud Stream, per-invocation retry/error-handler mechanisms for **imperative message handlers** cannot automatically apply in the same way to individual items inside a `Flux`. With reactive code, errors must be handled with Reactor operators and evaluated against the binder's capabilities.

### 2.2. BiFunction is not arbitrary support for two input sources

Spring Cloud Function also recognizes `BiFunction<T, Map, R>` and `BiConsumer<T, Map>`, where the second argument is a **Map of headers** extracted from **the same `Message`** as payload `T`. For example:

~~~java
import java.util.Map;
import java.util.function.BiFunction;

BiFunction<String, Map, String> describeEvent =
        (payload, headers) ->
                payload + ":" + headers.getOrDefault("source", "unknown");
~~~

This signature has **two Java parameters**, yet it does not describe two independent topics. It is a way to read **payload + metadata of a single message**. Do not assume `BiFunction<Order, Payment, Result>` will automatically create `-in-0` and `-in-1` bindings.

If you want to handle metadata more explicitly, use `Function<Message<I>, O>` or `Function<Message<I>, Message<O>>`, depending on whether headers need to be preserved.

## 3. Limits of multi-input/output function arity

Under Spring Cloud Function's **Function Arity** model, multi-port representation is built for **reactive functions** using Reactor's `Flux` and `TupleN`:

~~~java
// One input stream, two output streams.
Function<Flux<I>, Tuple2<Flux<A>, Flux<B>>>

// Two input streams, one output stream.
Function<Tuple2<Flux<A>, Flux<B>>, Flux<R>>

// Two input streams, two output streams.
Function<
    Tuple2<Flux<A>, Flux<B>>,
    Tuple2<Flux<C>, Flux<D>>>
~~~

`TupleN` specifies **the number of ports** and **each port's type**; Spring Cloud Stream uses this information to create the corresponding bindings:

| Tuple position | Reactor accessor | Input/output binding index |
| --- | --- | --- |
| First element | `getT1()` | `-in-0` / `-out-0` |
| Second element | `getT2()` | `-in-1` / `-out-1` |
| Third element | `getT3()` | `-in-2` / `-out-2` |

**Not equivalent to multi-output bindings:**

~~~java
Function<Order, Tuple2<Accepted, Rejected>> // Single returned object.
Function<Order, List<Result>>              // Single returned Collection.
Function<Flux<Order>, Flux<Tuple2<A, B>>>  // One stream emitting pairs.
~~~

These three signatures **do not automatically create** separate output bindings. With `Flux<Tuple2<A, B>>`, each item on **one** stream is a tuple of values. With `Tuple2<Flux<A>, Flux<B>>`, there are **two** independent publishers.

This distinction also applies to `Flux<List<T>>`, `List<Message<T>>`, and the number of messages emitted to a destination: **item count or message count is not port count**. Some adapters have special rules for Collections, so you must verify how an adapter serializes or emits individual elements.

## 4. Capability matrix by adapter

The table below describes **natural, documented usage patterns**, not a guarantee that every version, binder, or trigger supports every declaration style:

| Function type | Spring Cloud Function + FunctionCatalog | Web adapter (HTTP) | Spring Cloud Stream (messaging) | AWS/Azure/GCP serverless adapter |
| --- | --- | --- | --- | --- |
| `Function<I, O>` | Lookup/invocation and type conversion | Request → response | Input binding → output binding | Fits event/request → result when adapter supports the types |
| `Supplier<O>` | Zero-argument function | Accessible via HTTP GET | Output binding; polling/triggering managed by framework | Depends on trigger and adapter |
| `Consumer<I>` | Accepts input, returns no payload | HTTP request invokes consumer | Input binding, processes message | Fits certain event triggers |
| `Function<Flux<I>, Flux<O>>` | Supports reactive API | Supports multi-value/SSE responses in appropriate setups | Supports reactive pipeline; actual features depend on binder | Must check how adapter maps publishers and invocation lifecycle |
| `Function<Flux<I>, Tuple2<Flux<A>, Flux<B>>>` | Reactive arity model | **Does not automatically create two HTTP responses/endpoints** | Can create **two output bindings** | **Does not automatically create two destinations/triggers** |
| `Function<Tuple2<Flux<A>, Flux<B>>, Flux<R>>` | Reactive arity model | **Does not automatically create two request sources** | Can create **two input bindings** | **Does not automatically create two event sources** |
| `Function<I, List<O>>` | Single Collection value | Can return a JSON array | How Collection is emitted depends on adapter/binder mechanism | Can serialize a Collection payload; adapter-dependent |

The cells marked **"does not automatically"** are crucial: you can write **additional integration code** to pull events from multiple sources and invoke the function, or send results to multiple services yourself. That, however, is integration code responsibility, not behavior automatically derived from a `TupleN` signature.

## 5. HTTP adapter: one invocation tied to one response

The `spring-cloud-function-web` module can expose functional beans as HTTP endpoints in a Spring Boot web application. Example:

~~~java
import java.util.Locale;
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TextFunctions {

    @Bean
    public Function<String, String> normalizeCode() {
        return code -> code.trim().toUpperCase(Locale.ROOT);
    }
}
~~~

With the web adapter enabled, you can send a request to the function's path:

~~~http
POST /normalizeCode HTTP/1.1
Content-Type: text/plain
Accept: text/plain

 ord-42
~~~

The function returns `ORD-42`, which the adapter turns into an HTTP response. The web adapter supports basic mappings for `Supplier` (such as GET), `Function`, and `Consumer` (such as POST). For multi-valued results, clients can request **server-sent events** via `Accept: text/event-stream` when the signature and environment allow it.

However:

- A normal HTTP request has **one response channel**. Returning `List<Result>` can produce a JSON array, and returning `Flux<Result>` can produce a response stream; both remain **one endpoint/response**.
- Returning `Tuple2<Flux<A>, Flux<B>>` **does not automatically turn into** two endpoints or two independent responses with separate HTTP status codes.
- HTTP has no concept of multiple **input bindings** named `-in-0`, `-in-1` like Spring Cloud Stream. If a request carries multiple fields, the adapter parses them according to the request contract.
- If a complex API is needed (multiple routes, authentication, REST-style error handling, advanced streaming), consider building the API with Spring MVC/WebFlux and **invoking the business bean**.

The web adapter helps expose functions over HTTP, but **does not replace the full capabilities** of Spring MVC or WebFlux.

## 6. Spring Cloud Stream: where function arity becomes multiple bindings

For messaging, Spring Cloud Stream turns logical inputs/outputs into **input/output bindings**; each binding can attach to a destination on a binder such as Kafka or RabbitMQ.

Example classifying payments into two streams:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Flux;
import reactor.util.function.Tuple2;
import reactor.util.function.Tuples;

@Configuration
public class PaymentRoutingFunctions {

    public record Payment(String id, long amountVnd) {}

    @Bean
    public Function<Flux<Payment>,
            Tuple2<Flux<Payment>, Flux<Payment>>> splitPayments() {

        return input -> {
            // Only connect upstream when both outputs have subscribers.
            Flux<Payment> shared = input.publish().autoConnect(2);

            Flux<Payment> large = shared
                    .filter(p -> p.amountVnd() >= 1_000_000L);
            Flux<Payment> regular = shared
                    .filter(p -> p.amountVnd() < 1_000_000L);

            return Tuples.of(large, regular);
        };
    }
}
~~~

The function has **1 input binding, 2 output bindings**:

~~~text
payments.received  --> splitPayments-in-0
                           |
                      splitPayments
                      /            \
             -out-0                 -out-1
                 |                      |
       payments.large         payments.regular
~~~

Example `application.yml` (assuming the project has Spring Cloud Stream and a suitable binder):

~~~yaml
spring:
  cloud:
    function:
      definition: splitPayments
    stream:
      bindings:
        splitPayments-in-0:
          destination: payments.received
          content-type: application/json
        splitPayments-out-0:
          destination: payments.large
          content-type: application/json
        splitPayments-out-1:
          destination: payments.regular
          content-type: application/json
~~~

`getT1()` is output stream 0; `getT2()` is output stream 1. The adapter must subscribe to the output streams for data to flow. The `publish().autoConnect(2)` pattern in the example **assumes both branches are subscribed to**; if one branch lacks a subscriber, the source never connects. Source sharing must be verified alongside subscription lifecycle and backpressure.

### 6.1. Can every reactive feature be used with every binder?

**No.** Using `Flux` in a signature does not mean the system has **end-to-end backpressure**. With non-reactive binders (such as standard Kafka/Rabbit binders), Reactor code still provides stream transformation operators, but rate limiting from broker to application and broker-side throttling differ from a fully reactive system. Spring Cloud Stream documentation clearly distinguishes between the **reactive API** and binders that natively support reactive mechanisms.

When choosing a binder, verify:

- Binder type and level of reactive/backpressure support.
- How the adapter connects and subscribes to publishers.
- Per-port serialization, `content-type`, and schema configuration.
- Impact when one output is slow or a destination is unavailable.
- Error/retry/DLQ policies, especially for reactive functions.

### 6.2. Retries for reactive functions differ from imperative functions

With imperative message handlers, Spring Cloud Stream can apply retry/error handling around **each message invocation**, depending on the binder. With reactive functions, the framework typically invokes the function once when setting up the pipeline and does not directly wrap each individual item in that pipeline. Therefore, imperative retry/error-handler configurations do not automatically work identically with reactive functions.

Example of **expressing per-item error policy** directly inside the stream:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Flux;

// Convert valid numbers; invalid data is recorded in an extra handler.
Function<Flux<String>, Flux<Long>> parseNumbers = input ->
        input.flatMap(text -> {
            try {
                return Flux.just(Long.parseLong(text));
            } catch (NumberFormatException invalidNumber) {
                // Example illustrating a policy of skipping invalid records.
                // Production: log error / dead-letter as required.
                return Flux.<Long>empty();
            }
        });
~~~

This snippet **intentionally drops** invalid items to illustrate error-handling scope and does not yet satisfy error recording or durable delivery requirements of a production system. For higher reliability, design an error/observability branch, bounded retries, and binder delivery guarantees.

### 6.3. Reactive Consumer is a special case

A `Consumer<Flux<T>>` bean returns `void`, so the adapter has no result publisher to subscribe to. According to Spring Cloud Stream guidance, if this signature is needed, **the consumer's code must explicitly subscribe**; however, manual subscriptions can make lifecycle and error handling harder to manage.

For processing a stream to completion, consider `Function<Flux<T>, Mono<Void>>` using `then()` to represent completion. Verify subscription behavior and support on the actual adapter/binder version, especially when the stream never completes.

## 7. Serverless adapters: one invocation per platform contract

Spring Cloud Function provides adapters for platforms such as **AWS Lambda**, **Azure Functions**, and **Google Cloud Functions**. In all of them, the adapter translates a platform-specific request/event into a call to a function in `FunctionCatalog` and translates the result back to the platform.

Example of a shared business bean:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ClassificationFunctions {

    public record Order(String id, long totalVnd) {}
    public record Decision(String id, String category) {}

    @Bean
    public Function<Order, Decision> classifyOrder() {
        return order -> new Decision(
                order.id(),
                order.totalVnd() >= 1_000_000L ? "PRIORITY" : "STANDARD");
    }
}
~~~

This is a **`Function<I, O>`** signature that ports relatively easily across adapters: one `Order` goes in, one `Decision` comes out. **The classification code** does not need to know who invokes it. Deployment configuration differs by platform:

| Adapter | Typical trigger type | What to configure and check |
| --- | --- | --- |
| AWS Lambda | API Gateway, SQS, S3, or other triggers | `spring-cloud-function-adapter-aws`; `FunctionInvoker` handler; event type and response contract |
| Azure Functions | HTTP trigger, queue/event trigger, etc. | Azure adapter and Azure Function entry point/trigger binding; runtime and data types |
| Google Cloud Functions | HTTP or background event | GCP adapter, entry point, event format, and trigger constraints |

**One serverless invocation is not automatically equivalent to a Spring Cloud Stream input/output binding.** For example, a Lambda triggered by SQS normally receives an event under Lambda's contract; it **does not automatically attach** `getT1()`/`getT2()` to two queues just because a bean returns `Tuple2<Flux<A>, Flux<B>>`. To consume from multiple sources or emit to multiple targets, design integration according to platform capabilities, such as event source mappings, message publishers, or dedicated stream processors.

### 7.1. Example selecting a function on AWS Lambda

With the official AWS adapter, the recommended integration handler is:

~~~text
org.springframework.cloud.function.adapter.aws.FunctionInvoker::handleRequest
~~~

If the project has multiple functional beans, provide configuration to select the function, such as an environment variable following AWS/SCF rules:

~~~text
spring_cloud_function_definition=classifyOrder
~~~

When receiving an event compatible with `Order`, the adapter attempts to convert the input to `Order` and serialize the `Decision` result according to platform rules. If the trigger delivers specialized objects such as SQS or S3 events, the signature may need to use **AWS event types** or a dedicated translation layer. Do not assume every event carries JSON shaped like `Order`.

### 7.2. Lifecycle, execution time, and results

Serverless platforms impose specific constraints: per-invocation timeouts, memory limits, payload size limits, retry counts, and failed-event handling. An unbounded `Flux` may suit a continuously running messaging system, but is **not automatically suitable** for a finite serverless invocation. Whether an adapter supports reactive publishers, streaming responses, or batch processing must be verified against the specific platform's documentation and runtime.

If an HTTP response differs from an event trigger outcome, check the trigger contract: a `Consumer<I>` returns no Java payload, yet the platform may still expect a status code/acknowledgment or a specific result shape.

## 8. Composition and routing: limits you cannot infer from external types

Spring Cloud Function supports composition via `spring.cloud.function.definition`:

~~~properties
spring.cloud.function.definition=normalize|validate
~~~

Composing two compatible `Function` beans produces a single externally visible function; composing a `Supplier` with a `Function` remains a source requiring no input; composing a `Function` with a `Consumer` yields a consumer that returns no payload.

However:

- You **cannot arbitrarily compose** a `Consumer` returning `void` and expect a payload for a subsequent `Function`.
- Composition `a|b` means **data flows from a to b**, and does not automatically create extra input/output bindings like a fan-out.
- With a reactive pipeline, verify type compatibility and how the adapter subscribes; mixing reactive functions with imperative consumers can run into subscription constraints.
- Binding names for a composition must be determined from the **composed function bound by the adapter**, not guessed from individual bean names.

### 8.1. Per-message routing vs. stream-level routing

In Spring Cloud Function, routing can be based on headers, configuration, or callbacks. An **imperative function** can choose a route **per message** using message metadata. For a reactive function, however, the unit of processing is **the entire stream**, so per-message routing instructions via headers are not applied in the same way; the documentation recommends **application-level configuration** when routing reactive streams.

~~~text
Imperative:
Message A + header route=alpha ──> alpha
Message B + header route=beta  ──> beta

Reactive:
Flux of messages ──> a single pipeline selected by configuration
~~~

If the requirement is to route individual messages to multiple topics in a reactive pipeline, build explicit data branches (such as `Tuple2<Flux<A>, Flux<B>>`) or use dynamic destination mechanisms supported by Spring Cloud Stream; do not expect imperative header routing to handle every item inside a `Flux`.

## 9. Decision table: choosing a signature based on the target environment

| Requirement | Signature/architecture to consider | Additional checks |
| --- | --- | --- |
| One request receives one return value | `Function<I, O>` | HTTP serialization, timeout, validation |
| Read data without input | `Supplier<O>` | GET on web or poller/trigger in messaging |
| Process events with side effects only | `Consumer<I>` | Ack, retry, idempotency, recoverability |
| One input topic, one output topic | `Function<I, O>` or `Function<Flux<I>, Flux<O>>` | Binder, retries, and backpressure |
| Two input topics need synchronization | `Function<Tuple2<Flux<A>, Flux<B>>, Flux<R>>` | Reactive multi-binding, join/window, state, late events |
| One topic needs two output topics | `Function<Flux<I>, Tuple2<Flux<A>, Flux<B>>>` | Both outputs subscribed, destinations, and tuple ordering |
| One HTTP endpoint returns a list | `Function<I, List<O>>` or suitable response stream | Single response, content negotiation, payload limits |
| One AWS/GCP/Azure invocation handles one event | `Function<Event, Result>` or `Consumer<Event>` | Trigger type, event type, timeout, return rules |
| Need multiple response ports on HTTP/serverless | Custom integration/adapter or contract redesign | Do not infer multiple ports from `TupleN` automatically |

### 9.1. Pre-migration checklist across adapters

Before moving a function from one environment to another:

1. **Define the contract:** bean name, `I/O` generics, port count, value vs. publisher.
2. **Check invocation trigger:** what request, poller, event trigger, or subscription runs the function?
3. **Check output rules:** response, message, collection, stream, or multiple bindings?
4. **Verify conversions:** are payload, headers, `content-type`, and Java types compatible?
5. **Compare lifecycles:** is the function called per message or once to set up a `Flux`?
6. **Compare failure modes:** exceptions, retries, DLQ, cancellation, timeouts, and idempotency.
7. **Validate on the target adapter/binder:** logic unit tests alone are not enough to prove external integration succeeds.

## 10. Testing portability and per-adapter behavior

### 10.1. Transport-independent unit test

Example testing the `classifyOrder` bean directly without starting an HTTP server or broker:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class ClassificationFunctionsTest {

    @Test
    void assignsPriorityWithoutDependingOnTransport() {
        var function = new ClassificationFunctions().classifyOrder();

        var result = function.apply(
                new ClassificationFunctions.Order("O-101", 1_000_000L));

        assertEquals(
                new ClassificationFunctions.Decision("O-101", "PRIORITY"),
                result);
    }
}
~~~

This test proves the business rule is correct at the Java level. It **does not verify** HTTP JSON, topic bindings, Lambda event contracts, or retries.

### 10.2. Unit test for a two-output function

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.List;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class PaymentRoutingFunctionsTest {

    @Test
    void separatesLargePaymentsFromRegularPayments() {
        var large = new PaymentRoutingFunctions.Payment(
                "P-101", 1_500_000L);
        var regular = new PaymentRoutingFunctions.Payment(
                "P-102", 250_000L);

        var outputs = new PaymentRoutingFunctions()
                .splitPayments()
                .apply(Flux.just(large, regular));

        // Subscribe to both publishers to satisfy autoConnect(2).
        StepVerifier.create(Mono.zip(
                        outputs.getT1().collectList(),
                        outputs.getT2().collectList()))
                .assertNext(both -> {
                    assertEquals(List.of(large), both.getT1());
                    assertEquals(List.of(regular), both.getT2());
                })
                .verifyComplete();
    }
}
~~~

Here `Mono.zip` ensures **both branches are subscribed to**, matching the function's `autoConnect(2)`. `collectList()` is only for **finite** test sources. To prove both destinations work properly, integration tests with the **Spring Cloud Stream Test Binder** or a real broker/binder are still required.

### 10.3. Minimum integration test suite per adapter

| Environment | Minimum checks |
| --- | --- |
| HTTP | Send real requests; verify status, content type, response structure, error cases |
| Spring Cloud Stream | Send messages to each input binding; read each output binding; verify payload, headers, port ordering |
| AWS Lambda | Invoke handler/invocation with sample events matching the trigger; verify serialization and output |
| Azure/GCP | Run through the official entry point/trigger, real payloads, and return mechanism |

Especially with reactive multi-output functions, test scenarios where one branch is not consumed, one destination fails, or the two outputs run at different speeds. Backpressure and retry behavior cannot be proven with `Flux.just(...)` unit tests alone.

## 11. Common misconceptions

| Misconception | Reality |
| --- | --- |
| "Since it is a Java `Function`, every adapter supports it identically." | Adapters have distinct event/request contracts, data types, and lifecycles |
| "`Tuple2<OutputA, OutputB>` creates two output bindings." | No; Spring Cloud Function's multi-port support uses reactive arity with tuples of `Flux` |
| "`Flux` means the broker definitely provides backpressure." | The binder and underlying infrastructure must also support it |
| "HTTP can return two responses because the function returns `Tuple2`." | HTTP normally has one response channel; define a suitable payload/stream instead |
| "`BiFunction<A, B, R>` always consumes from two topics." | The special case recognized by Spring Cloud Function is payload and `Map` of headers from one message |
| "Imperative function retry automatically handles each reactive item." | Reactive pipelines must define their own appropriate error-handling policies |
| "`Consumer<Flux<T>>` needs no subscription because it is a Consumer." | A `void` signature provides no result publisher for the framework to subscribe to |
| "One Lambda invocation automatically wires two `Tuple2` inputs to two triggers." | Event sources and integration layers must be designed per platform capabilities |

## 12. Self-check questions

**Question 1.** A function returning `Tuple2<Flux<Accepted>, Flux<Rejected>>` is bound by Spring Cloud Stream into two outputs. If you move the exact same bean to the HTTP web adapter, will it automatically create two endpoints `/accepted` and `/rejected`?

**Answer:** **No.** Two output bindings are a messaging adapter concept. To expose two HTTP APIs, design appropriate routing/responses in the web layer.

**Question 2.** Is `BiFunction<Order, Map, Decision>` two input bindings because it has two parameters?

**Answer:** **No.** Under the recognized special signature, the second parameter is the **headers of the same message**.

**Question 3.** Why might `Function<Flux<I>, Flux<O>>` need a different retry strategy from `Function<I, O>` in Spring Cloud Stream?

**Answer:** A reactive function is invoked to set up the pipeline; the framework does not invoke `apply` again per message to wrap each invocation in an imperative retry/error handler.

**Question 4.** If an application uses a regular Kafka binder while the function returns `Flux<O>`, can you claim end-to-end backpressure from consumer to Kafka broker?

**Answer:** **No.** The Reactor API does not automatically create reactive capabilities in the broker/binder; check the actual support level of the messaging stack.

**Question 5.** An order classification business rule needs to be invoked over HTTP and also emit events to two topics. Which design is easiest to reuse?

**Answer:** Put the **pure classification rule** in `Function<Order, Decision>` (or a transport-independent service). The web adapter invokes that logic and returns one response. The messaging application uses the same rule inside a branching reactive function `Tuple2<Flux<...>, Flux<...>>`; only the messaging adapter creates the two output bindings.

## References

- [Spring Cloud Function — Programming Model, FunctionCatalog, Function Arity, routing and type conversion](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Function — Standalone Web Applications](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/standalone-web-applications.html)
- [Spring Cloud Stream — Producing and Consuming Messages, Reactive Functions](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html)
- [Spring Cloud Function — AWS Lambda adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/aws-intro.html)
- [Spring Cloud Function — Microsoft Azure Functions adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/azure-intro.html)
- [Spring Cloud Function — Google Cloud Functions adapter](https://docs.spring.io/spring-cloud-function/reference/adapters/gcp-intro.html)
