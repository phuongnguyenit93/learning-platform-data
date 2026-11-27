# Migrating the Legacy Annotation Model to Supplier, Function, and Consumer

## 1. Why did Spring Cloud Stream move to the functional model?

Earlier versions of Spring Cloud Stream typically declared channel interfaces and attached `@EnableBinding`, `@Input`, `@Output`, `@StreamListener`, and `@SendTo` annotations to classes or methods. That model coupled business code closely to channels and message transport structures.

The modern model uses standard Java functional beans:

- `Supplier<T>`: produces events to emit to an output binding.
- `Function<I, O>`: receives an input message, transforms it, and emits output.
- `Consumer<T>`: receives events and performs processing, with no default output binding.

Spring Cloud Function discovers these beans; Spring Cloud Stream creates bindings connecting them to Kafka, RabbitMQ, or Pulsar. As a result, business logic becomes pure or easily testable functions, while topics, groups, serialization, and retries are configured outside code.

~~~mermaid
flowchart LR
    L[Legacy annotations] --> M[Migration]
    M --> S[Supplier output only]
    M --> F[Function input and output]
    M --> C[Consumer input only]
    S --> B[Spring Cloud Stream bindings]
    F --> B
    C --> B
    B --> K[(Kafka / RabbitMQ / Pulsar)]
~~~

This is not merely renaming annotations. A proper upgrade must preserve the running system's event contract, groups/subscriptions, ordering, error handling, and delivery semantics.

## 2. Mapping legacy annotations to the new structure

| In the legacy application | Purpose | Equivalent in the functional model |
|---|---|---|
| `@EnableBinding(Sink.class)` | Register input channel | `Consumer<T>` or `Function<T,R>` bean and input binding |
| `@EnableBinding(Source.class)` | Register output channel | `Supplier<T>` bean or `StreamBridge` |
| `@EnableBinding(Processor.class)` | Has both input and output | `Function<I,O>` bean |
| `@StreamListener(Sink.INPUT)` | Process incoming messages | `Consumer<T>` bean |
| `@StreamListener` with `@SendTo` | Receive and return output messages | `Function<I,O>` bean |
| `@Input` / `@Output` interface methods | Declare named channels | Bindings derived from functional bean names or aliases |
| Inject `MessageChannel` then `send` | Imperatively emit messages | `StreamBridge.send` via output binding |
| `@InboundChannelAdapter` + poller | Emit events on a polling schedule | `Supplier<T>` with configured poller |
| Condition on `@StreamListener` | Conditional routing | Router function, filter, or clearly designed multiple functions |

Not every Spring Integration annotation was removed. This lesson covers the **legacy Spring Cloud Stream binding and listener model**, and does not recommend deleting integration adapters still needed by other components.

## 3. Defining scope and creating an inventory before editing code

Before converting, list within the running application:

1. Channel interfaces annotated with `@Input`, `@Output`, and `@EnableBinding`.
2. `@StreamListener` methods: inputs, outputs, payload types, and headers.
3. Places directly calling `MessageChannel.send`.
4. Configuration for `destination`, `group`, `contentType`, partitioning, and concurrency.
5. Kafka/Rabbit/Pulsar binders, topics/queues, retry/DLQ, error channels, and acknowledgements.
6. Suppliers/pollers, event emission schedules, and trigger conditions.
7. Message shapes using `Message<T>`, custom headers, or native serialization.
8. Asynchronous processing points, transactions, idempotency, and side effects.

Create a before/after mapping table for each flow; do not accidentally change topic or group names when renaming Java beans.

Example:

| Property | Legacy | Must preserve after upgrade |
|---|---|---|
| Input channel | `input` | `acceptOrder-in-0` |
| Input destination | `orders.events` | `orders.events` |
| Consumer group | `order-processor` | `order-processor` |
| Output channel | `output` | `acceptOrder-out-0` |
| Output destination | `orders.accepted` | `orders.accepted` |
| Input payload format | JSON schema v2 | JSON schema v2 compatible |
| Failure semantics | Broker-specific retry, DLT, ack | Proven equivalent by tests |

## 4. Before conversion example: Processor and StreamListener

The legacy model might look like this:

~~~java
import org.springframework.cloud.stream.annotation.EnableBinding;
import org.springframework.cloud.stream.annotation.StreamListener;
import org.springframework.cloud.stream.messaging.Processor;
import org.springframework.messaging.handler.annotation.SendTo;

record OrderCreated(String orderId, long totalCents) {}
record OrderAccepted(String orderId, String status) {}

@EnableBinding(Processor.class)
class LegacyOrderProcessor {

    @StreamListener(Processor.INPUT)
    @SendTo(Processor.OUTPUT)
    public OrderAccepted acceptOrder(OrderCreated event) {
        return new OrderAccepted(event.orderId(), "ACCEPTED");
    }
}
~~~

The channel names `input` and `output` come from the `Processor` interface. Legacy configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        input:
          destination: orders.events
          group: order-processor
          contentType: application/json
        output:
          destination: orders.accepted
          contentType: application/json
~~~

This snippet is a **legacy pattern to recognize in old source code**, not an option for new Spring Cloud Stream applications. When upgrading the framework version, remove legacy imports/APIs according to the migration guide of the target release train.

## 5. After conversion: Function receiving and returning results

Extract the business logic into a `Function<OrderCreated, OrderAccepted>` bean:

~~~java
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderFunctions {

    @Bean
    Function<OrderCreated, OrderAccepted> acceptOrder() {
        return event -> new OrderAccepted(event.orderId(), "ACCEPTED");
    }
}
~~~

Spring Cloud Stream infers:

- Input binding: `acceptOrder-in-0`.
- Output binding: `acceptOrder-out-0`.

Explicitly declare the old destinations and old group:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.events
          group: order-processor
          content-type: application/json
        acceptOrder-out-0:
          destination: orders.accepted
          content-type: application/json
~~~

Keep `orders.events` and `order-processor` unchanged so the new consumer joins the same logical workload instead of accidentally creating a new subscription/group. **Do not run the old and new versions simultaneously in the same group without accounting for them splitting messages and differing in processing behavior.**

## 6. From void StreamListener to Consumer

A legacy method handling only side effects:

~~~java
import org.springframework.cloud.stream.annotation.EnableBinding;
import org.springframework.cloud.stream.annotation.StreamListener;
import org.springframework.cloud.stream.messaging.Sink;

@EnableBinding(Sink.class)
class LegacyPaymentListener {

    @StreamListener(Sink.INPUT)
    public void applyPayment(PaymentReceived payment) {
        paymentService.apply(payment);
    }
}
~~~

Functional version:

~~~java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class PaymentFunctions {

    @Bean
    Consumer<PaymentReceived> applyPayment(PaymentService paymentService) {
        return payment -> paymentService.apply(payment);
    }
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: applyPayment
    stream:
      bindings:
        applyPayment-in-0:
          destination: payments.received
          group: payment-ledger
~~~

`Consumer<T>` does not automatically create an output binding. If the legacy code both wrote to a database and sent an event, consider converting it to a `Function` returning output, or using `StreamBridge` in a controlled manner; do not lose the publish step when converting to a Consumer.

## 7. From Source/InboundChannelAdapter to Supplier

An old source emitting events via a poller:

~~~java
import org.springframework.cloud.stream.annotation.EnableBinding;
import org.springframework.cloud.stream.messaging.Source;
import org.springframework.integration.annotation.InboundChannelAdapter;
import org.springframework.integration.annotation.Poller;

@EnableBinding(Source.class)
class LegacyHeartbeatSource {

    @InboundChannelAdapter(
        value = Source.OUTPUT,
        poller = @Poller(fixedDelay = "5000")
    )
    public Heartbeat nextHeartbeat() {
        return new Heartbeat("service-a", System.currentTimeMillis());
    }
}
~~~

Migrated to a Supplier bean:

~~~java
import java.util.function.Supplier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record Heartbeat(String source, long timestampMs) {}

@Configuration
class HeartbeatFunctions {

    @Bean
    Supplier<Heartbeat> heartbeat() {
        return () -> new Heartbeat("service-a", System.currentTimeMillis());
    }
}
~~~

A Supplier does not consume messages from a broker; the framework invokes the Supplier via the appropriate polling mechanism. Configure the output destination:

~~~yaml
spring:
  cloud:
    function:
      definition: heartbeat
    stream:
      bindings:
        heartbeat-out-0:
          destination: service.heartbeat
  integration:
    poller:
      fixed-delay: 5000
~~~

Poller properties and how Suppliers are invoked must be verified against the Spring Cloud Stream/Spring Integration version. Avoid using a Supplier to re-emit a business event on every poll: if events are fetched by reading "unsent" records, you need publish state, a transaction/outbox, or a confirmation mechanism to prevent duplicates.

## 8. From injecting Output MessageChannel to StreamBridge

Legacy code may inject an output channel and call `send` inside a REST endpoint or job:

~~~java
@EnableBinding(Source.class)
class LegacyOrderPublisher {
    private final MessageChannel output;

    LegacyOrderPublisher(@Qualifier(Source.OUTPUT) MessageChannel output) {
        this.output = output;
    }

    void publish(OrderCreated event) {
        output.send(MessageBuilder.withPayload(event).build());
    }
}
~~~

In the new model, use `StreamBridge` when publishing messages **not originating from an input binding**:

~~~java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

@Service
class OrderPublisher {

    private final StreamBridge streamBridge;

    OrderPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    void publish(OrderCreated event) {
        boolean accepted = streamBridge.send("orderEvents", event);
        if (!accepted) {
            throw new IllegalStateException("Output binding rejected event");
        }
    }
}
~~~

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: orderEvents
      bindings:
        orderEvents:
          destination: orders.events
          content-type: application/json
~~~

`StreamBridge.send` confirms sending through the API/binding according to binder semantics; it **does not prove the target consumer has processed the business logic**. If reliable publishing after a database commit is required, design an outbox or explicit transactional mechanism. Do not replace every Function with StreamBridge, as doing so forfeits composition benefits, declarative output bindings, and standard error management.

## 9. Binding naming rules in the functional model

For a bean named `processOrder`, default binding names follow the pattern:

~~~text
<functionName>-in-<inputIndex>
<functionName>-out-<outputIndex>
~~~

| Functional bean | Input binding | Output binding |
|---|---|---|
| `Consumer<Order> processOrder` | `processOrder-in-0` | None by default |
| `Function<Order,Result> acceptOrder` | `acceptOrder-in-0` | `acceptOrder-out-0` |
| `Supplier<Heartbeat> heartbeat` | None by default | `heartbeat-out-0` |

Binding names are used under `spring.cloud.stream.bindings`, whereas `destination` is the actual logical topic/exchange/topic name. Renaming a bean from `processOrder` to `handleOrders` without updating YAML prevents old configuration from applying to the new binding.

For function composition and multiple inputs/outputs, binding names can be more complex. Verify the runtime-generated names or use explicit aliases rather than guessing.

## 10. Using binding aliases when you want to keep configuration names

Large applications may already have many properties tied to the names `input` and `output`. Spring Cloud Stream supports binding aliases:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      function:
        bindings:
          acceptOrder-in-0: input
          acceptOrder-out-0: output
      bindings:
        input:
          destination: orders.events
          group: order-processor
        output:
          destination: orders.accepted
~~~

Aliases allow switching to a Function without having to rename every configuration key in a single step. However, this adds an extra mapping layer that must be documented. For new projects or when configuration can be updated together, using the functional bean binding names directly is usually clearer.

An alias does not change the actual destination, synchronize data between two brokers, or replace groups/subscriptions.

## 11. Enabling multiple independent functions

An application can declare multiple beans:

~~~java
@Configuration
class MultipleFunctions {

    @Bean
    Function<String, String> normalize() {
        return String::trim;
    }

    @Bean
    Consumer<String> audit(AuditService auditService) {
        return auditService::record;
    }
}
~~~

If you want two independent processing pipelines, use a semicolon:

~~~yaml
spring:
  cloud:
    function:
      definition: normalize;audit
    stream:
      bindings:
        normalize-in-0:
          destination: names.raw
          group: normalizer
        normalize-out-0:
          destination: names.normalized
        audit-in-0:
          destination: events.audit
          group: audit-service
~~~

A `;` declares multiple independent functions; a `|` composes functions sequentially. Do not confuse the two: `normalize;audit` does not automatically pipe the output of normalize into audit.

When multiple Function/Supplier/Consumer beans exist and none is explicitly selected, configure `spring.cloud.function.definition` to avoid ambiguity.

## 12. Composition is not the same as manually wired channels

Legacy setups might use two applications or two channels:

~~~text
orders.raw -> normalize -> orders.normalized -> validate -> orders.validated
~~~

If both steps are simply in-process data transformations within the same application and need no broker boundary in between, you can use function composition:

~~~java
@Bean
Function<String, String> normalize() {
    return String::trim;
}

@Bean
Function<String, String> validate() {
    return text -> {
        if (text.isBlank()) {
            throw new IllegalArgumentException("Blank value");
        }
        return text;
    };
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: normalize|validate
~~~

Composition combines logic into a single pipeline and **does not create an intermediate destination** like the old broker flow. Therefore it can alter retry boundaries, independent replayability, and per-step observability. If the intermediate topic is a contract for other applications or a durable storage boundary, keep it as real output/input bindings instead of composing the two functions.

## 13. Preserving content type and payload conversion

In the legacy annotation model, `@StreamListener` could receive POJOs because the framework converted bytes into Java objects based on content type. Functional beans also use message conversion, though framework versions, codecs, and configuration may change.

Example payload:

~~~json
{
  "orderId": "ord-42",
  "totalCents": 150000
}
~~~

Bean:

~~~java
record OrderCreated(String orderId, long totalCents) {}

@Bean
Function<OrderCreated, OrderAccepted> acceptOrder() {
    return order -> new OrderAccepted(order.orderId(), "ACCEPTED");
}
~~~

Binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.events
          group: order-processor
          content-type: application/json
        acceptOrder-out-0:
          destination: orders.accepted
          content-type: application/json
~~~

Test both old and new schema versions, missing fields, unrecognized enums, timestamps, large numbers, and malformed payloads. If `useNativeDecoding`/`useNativeEncoding` is enabled on the binder, the broker client handles serialization/deserialization, so do not assume default JSON conversion still applies.

## 14. Preserving headers and the Message wrapper

Legacy code may read `Message<T>` to extract correlation IDs, tenant IDs, or trace headers. You can keep that style in the new function:

~~~java
import java.util.function.Function;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Bean
Function<Message<OrderCreated>, Message<OrderAccepted>> acceptOrder() {
    return incoming -> {
        OrderCreated order = incoming.getPayload();
        OrderAccepted accepted = new OrderAccepted(
            order.orderId(), "ACCEPTED"
        );
        Object correlationId = incoming.getHeaders().get("correlationId");
        return MessageBuilder.withPayload(accepted)
            .setHeader("correlationId", correlationId)
            .build();
    };
}
~~~

Do not blindly copy every broker-specific header from input to output: some headers are tied to consumer offsets, source partitions, acknowledgements, or internal transport and are unsuitable for forwarding. Select the business/trace headers to retain and verify they map properly across the target binder.

If the application bridges Kafka to RabbitMQ or Pulsar, check header mapping compatibility and header value types, especially for binary values and size limits.

## 15. Preserving the consumer group when upgrading

Before conversion:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        input:
          destination: orders.events
          group: order-processor
~~~

After conversion:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.events
          group: order-processor
~~~

Renaming the binding does not force you to change the topic or consumer group. Changing the group to `order-processor-v2` causes Kafka to use a different offset group, Rabbit binder to potentially create a different queue, and Pulsar to use a different subscription; the application can easily replay historical data or skip backlog depending on start-offset and provisioning policies.

When rolling out two versions in the same group, messages are split between both versions during the overlap window. This rolling upgrade strategy is risky if the two versions have different semantics. Verify backward compatibility and idempotency before running them concurrently.

## 16. Partitioning, routing, and ordering must be re-verified

If the old source used `partitionKeyExpression`, producer key headers, or partition count configuration, confirm that the new functional binding emits the corresponding Kafka record key/partition.

Common discrepancies:

- `customerId` field is inside JSON but not set as the message key.
- Changed key serialization causes partition hashing to change.
- Changed partition count routes future keys to different partitions.
- Increased concurrency makes **completion order** differ from arrival order.
- Changed Rabbit consumer or Pulsar subscription mode alters load distribution.

For Kafka Streams KStream/KTable, migration logic must use dedicated Kafka Streams function signatures rather than replacing stateful topologies with `Function<POJO, POJO>` and expecting state stores and changelogs to appear automatically.

## 17. Retries and error handling must not be migrated mechanically

A `@StreamListener` method may rely on retry annotations, binder retries, error channels, or DLQs. When migrating to Function/Consumer, verify **where errors are thrown** and which binder receives them.

Consumer example:

~~~java
@Bean
Consumer<OrderCreated> processOrder(OrderService service) {
    return event -> {
        service.handle(event); // throw on a real failure
    };
}
~~~

If the handler catches an exception and only logs it without rethrowing, the binder usually treats processing as complete; depending on the mode, the message may be acked/committed even though business processing failed. If retries are desired, do not swallow errors unintentionally.

A common retry configuration:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
          consumer:
            maxAttempts: 3
            backOffInitialInterval: 1000
            backOffMultiplier: 2.0
~~~

Verify error handling per binder and mode: Kafka, RabbitMQ, Pulsar, transactional processing, native decoding, and reactive functions do not necessarily share the exact same retry mechanism. Accept a migration only after testing transient errors, non-retryable errors, and DLQ behavior.

## 18. Kafka binder: DLQ and offsets must not change unintentionally

When keeping the Kafka binder, you may need to configure DLQ settings specifically for the new input binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
          consumer:
            maxAttempts: 3
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enableDlq: true
              dlqName: orders.events.dlt
~~~

Because the binding name changed from `input` to `processOrder-in-0`, all properties under `spring.cloud.stream.kafka.bindings.input` in the old app must also be remapped. Missing `enableDlq`, `startOffset`, `ackMode`, or other consumer properties may let the app run while recovery and failure handling behave differently.

Do not conflate Kafka offset state with external side effects outside Kafka as "exactly-once" without proper transactions or idempotency. A crash after a DB commit but before offset commit can still cause redelivery.

## 19. RabbitMQ binder: queues, DLQ, and acknowledgements

With RabbitMQ, `destination` usually maps to an exchange; `group` helps determine the consumer queue. During upgrade, keep the exact destination/group and review Rabbit binder-specific settings for the new binding name.

Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.events
          group: order-processor
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              autoBindDlq: true
              prefetch: 20
~~~

Preserve queue/consumer naming, durability, routing keys, prefetch, and dead-letter semantics. If production resources are pre-provisioned by an admin account, verify runtime permissions and auto-declare options instead of granting admin credentials to the binder.

A message received by a consumer whose process dies before acknowledgement can be redelivered by RabbitMQ. The migrated version still needs safe duplicate handling.

## 20. Pulsar binder: subscription and ack semantics

For Pulsar, preserve the logical subscription/group and corresponding subscription type. `Exclusive`, `Failover`, `Shared`, and `Key_Shared` have different load-sharing, failover, and ordering behaviors.

Items to verify during migration:

- Does the new binding actually connect to the old topic in the right tenant/namespace?
- Does the subscription name remain durable across restarts?
- Was the subscription type altered by new configuration?
- Have consumer ack timeout, negative ack, redelivery, and DLQ changed?
- Do producer keys/batching still satisfy key affinity when using Key_Shared?

Do not switch to Shared just to raise throughput if the flow requires per-key ordering. Migrating from annotations to functional beans does not require changing subscription types; treat them as two separate decisions.

## 21. Differences between synchronous and reactive Functions

A synchronous Function uses:

~~~java
@Bean
Function<OrderCreated, OrderAccepted> acceptOrder() {
    return order -> transform(order);
}
~~~

A reactive application might declare:

~~~java
import reactor.core.publisher.Flux;
import java.util.function.Function;

@Bean
Function<Flux<OrderCreated>, Flux<OrderAccepted>> acceptOrders() {
    return orders -> orders.map(order ->
        new OrderAccepted(order.orderId(), "ACCEPTED")
    );
}
~~~

Do not switch from a synchronous function to Flux merely because the new API supports it. Reactive functions run according to publisher lifecycles and framework subscription mechanics; backpressure, in-stream errors, and processing consistency can differ from per-record execution.

With `Consumer<Flux<T>>`, be very careful about who subscribes and who is responsible for error handling; do not assume it is equivalent to `Consumer<T>`. For workflows with Kafka stateful joins/windowing, use dedicated Kafka Streams functional bindings.

## 22. Conditional StreamListeners require redesign

Some legacy code used `@StreamListener` with `condition` so multiple handlers received records by header/type. When removing the annotation, multiple Consumers will not automatically receive and filter messages under the old rules.

Alternative options:

1. A single Consumer receiving all messages and dispatching to services by event type, with an explicit unknown branch.
2. A Spring Cloud Function router with routing expressions/headers configured and tested accordingly.
3. Splitting input destinations/topics by event type when independent broker boundaries are needed.

Simple dispatch example, avoiding guesswork around router configuration:

~~~java
@Bean
Consumer<Message<String>> dispatch(
        OrderEventHandler orderHandler,
        AuditEventHandler auditHandler) {
    return message -> {
        String type = (String) message.getHeaders().get("eventType");
        if ("ORDER".equals(type)) {
            orderHandler.handle(message.getPayload());
        } else if ("AUDIT".equals(type)) {
            auditHandler.handle(message.getPayload());
        } else {
            throw new IllegalArgumentException("Unsupported eventType: " + type);
        }
    };
}
~~~

Define the behavior when a header is missing or a type is unsupported: reject, DLQ, or ignore. Never allow a malformed message to spin endlessly in a retry loop.

## 23. Multiple inputs/outputs: do not assume one-to-one mapping

Legacy annotation code could accept two input channels in one handler or emit multiple outputs. The functional model supports certain multi-input/output signatures, but not every old method shape maps directly to `BiFunction<POJO,POJO,R>`.

For two reactive streams, you can use a `BiFunction<Flux<A>, Flux<B>, Flux<C>>` supported by the functional model:

~~~java
import java.util.function.BiFunction;
import reactor.core.publisher.Flux;

record CustomerProfile(String customerId, String tier) {}
record EnrichedOrder(String orderId, String tier) {}

@Bean
BiFunction<Flux<OrderCreated>, Flux<CustomerProfile>, Flux<EnrichedOrder>>
enrich() {
    return (orders, customers) -> orders.zipWith(
        customers,
        (order, customer) -> new EnrichedOrder(
            order.orderId(), customer.tier()
        )
    );
}
~~~

`zipWith` pairs elements by **arrival order**, not by joining on customerId or event time. If data arrives independently from two topics, use proper state/correlation mechanisms or a Kafka Streams join. For multiple outputs, examine tuple outputs or StreamBridge depending on desired semantics; write integration tests ensuring each output is published to the right destination.

## 24. Kafka Streams binder must preserve topology and state stores

If the legacy app used the Kafka Streams binder with KStream/KTable rather than message channel annotations, do not mechanically apply the "StreamListener → POJO Function" formula. Kafka Streams has its own topologies, partitions, state stores, and changelogs.

Functional Kafka Streams beans typically have signatures like:

~~~java
import java.util.function.Function;
import org.apache.kafka.streams.kstream.KStream;
import org.springframework.context.annotation.Bean;

@Bean
Function<KStream<String, OrderCreated>, KStream<String, OrderAccepted>>
acceptOrders() {
    return stream -> stream.mapValues(order ->
        new OrderAccepted(order.orderId(), "ACCEPTED")
    );
}
~~~

Stateful systems must accurately compare application IDs, input/output topics, Serdes, partitioning, state store names, and changelog topics. Changing the application ID can cause Kafka Streams to re-read data and rebuild fresh state. If you intend to change the application ID or topology, prepare a dedicated state/offset migration strategy.

## 25. Keeping binder configuration and multiple clusters consistent

An application spanning multiple Kafka clusters or RabbitMQ virtual hosts often assigns each binding to a named binder. When renaming bindings, also carry over the `binder` property:

~~~yaml
spring:
  cloud:
    function:
      definition: relayOrder
    stream:
      bindings:
        relayOrder-in-0:
          destination: orders.events
          group: order-relay
          binder: kafka-primary
        relayOrder-out-0:
          destination: audit.orders
          binder: kafka-audit
~~~

Preserve binder selection, endpoints, credentials, TLS, ACLs, and serialization for every destination. There is no default distributed transaction across two Kafka clusters or between Kafka and RabbitMQ; pipelines require idempotency/compensation or an outbox depending on business needs.

## 26. Testing function logic before testing the broker

Moving logic into a Java Function makes unit testing straightforward:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;

class OrderFunctionsTest {

    @Test
    void transformsOrderWithoutBroker() {
        OrderFunctions configuration = new OrderFunctions();
        OrderAccepted result = configuration.acceptOrder()
            .apply(new OrderCreated("ORD-101", 49_000));

        assertThat(result.orderId()).isEqualTo("ORD-101");
        assertThat(result.status()).isEqualTo("ACCEPTED");
    }
}
~~~

Unit tests verify business transformation but do not verify content-type conversion, routing, or acknowledgement. Therefore you need a second test layer using the Spring Cloud Stream Test Binder and an integration test layer with a real broker.

## 27. Test Binder: verifying destinations before/after migration

With the test binder, send inputs and receive outputs using the configured **effective destination** names:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.cloud.stream.binder.test.TestChannelBinderConfiguration;
import org.springframework.context.annotation.Import;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

@SpringBootTest(properties = {
    "spring.cloud.function.definition=acceptOrder",
    "spring.cloud.stream.bindings.acceptOrder-in-0.destination=orders.events",
    "spring.cloud.stream.bindings.acceptOrder-out-0.destination=orders.accepted"
})
@Import(TestChannelBinderConfiguration.class)
class OrderBindingTest {

    @Autowired InputDestination input;
    @Autowired OutputDestination output;

    @Test
    void keepsTheDestinationContract() {
        byte[] json = "{\"orderId\":\"ORD-101\",\"totalCents\":49000}"
            .getBytes(StandardCharsets.UTF_8);

        input.send(MessageBuilder.withPayload(json)
            .setHeader(MessageHeaders.CONTENT_TYPE, MimeTypeUtils.APPLICATION_JSON)
            .build(), "orders.events");

        Message<byte[]> result = output.receive(2_000, "orders.accepted");
        assertThat(result).isNotNull();
        assertThat(new String(result.getPayload(), StandardCharsets.UTF_8))
            .contains("ORD-101", "ACCEPTED");
    }
}
~~~

This test checks function bindings and conversion within the application context. It does not replace tests for real Kafka partitions/offsets, Rabbit queues/acks, or Pulsar subscriptions. When multiple functions run together, always specify the destination when sending/receiving so you do not read from the wrong channel.

## 28. Integration testing and verifying critical behaviors

Migration tests against a real broker or compatible container environment should cover:

| Item | Scenario | What to verify |
|---|---|---|
| Happy path | Valid event flows through input/output | Payload, headers, and destinations match old contract |
| Consumer group | Restart multiple instances | Still uses the expected group/subscription |
| Retained backlog | Stop consumer then publish messages | No lost events due to changed group/queue name |
| Legacy payload | Send supported schema versions | Conversion remains compatible |
| Poison message | Send invalid JSON | Retry/DLQ or reject matches policy |
| Transient error | Downstream returns timeout/503 | Bounded retry, backoff, and recovery |
| Crash window | Kill after side effect, before ack | Duplicates do not corrupt business state |
| Header routing | Send correlationId/eventType | Headers propagated and handled accurately |
| Partitioning | Same key, multiple messages | Per-key/partition ordering meets requirements |
| Multi-binder | Input/output on different brokers | Correct binders, ACLs, topics/exchanges |

Measure consumer lag, retry counts, DLQ size, duplicate outcomes, throughput, and p95/p99 before and after migration. A test that only asserts the output of a single message is insufficient to prove an upgrade is safe.

## 29. Step-by-step migration roadmap

Recommended workflow:

1. **Inventory** all legacy annotations, channel interfaces, bean names, bindings, and binder-specific properties.
2. **Freeze the contract** for topics/queues, groups, schemas, keys, headers, retry/DLQ, and delivery semantics.
3. **Extract logic** into services or Java functions independent of Spring Cloud Stream annotations.
4. **Choose the function type**: Supplier for producers, Function for transforms, Consumer for sinks, StreamBridge for imperative publishing.
5. **Assign stable bean names** and explicitly configure `spring.cloud.function.definition`.
6. **Remap bindings** from `input`/`output` to functional names, or use controlled aliases.
7. **Migrate binder properties** for Kafka/Rabbit/Pulsar to the new binding names.
8. **Run unit and Test Binder tests** to prove business logic and message wiring.
9. **Run integration tests** covering brokers, queues, partitions, retries, DLQ, and replay.
10. **Execute an appropriate canary/rolling deployment** after accounting for offsets and dual versions sharing a group.
11. **Monitor** lag, throughput, duplicates, conversion errors, and target backlogs.
12. **Remove legacy APIs/dependencies** only after nothing calls them and a rollback plan is ready.

Commit configuration remapping alongside the corresponding code changes; avoid deploying new code with old YAML that causes the app to bind to unintended destinations.

## 30. Canary, rollback, and avoiding duplicates when two versions run together

With Kafka, two consumers in the same group split partitions; they do not both receive the same messages during normal operation. If legacy and functional versions run in the same group, partitions are distributed between both versions. When semantics differ, results can become inconsistent across partitions.

If a new group is used for the canary, the canary reads an independent stream of events and can produce **duplicate side effects** if both write to production systems. A safer approach is shadow mode: the canary reads messages but records only metrics or isolated outputs without performing critical side effects.

A rollback plan must clarify:

- Will groups/offsets stay intact when reverting?
- Are there new schemas the old version cannot read?
- Are there messages processed by new logic that cannot be reprocessed by old logic?
- Must producers be paused or traffic shifted during rollback?
- Are there unprocessed DLT/retry messages that need reconciliation?

Rollback is not as simple as redeploying the old image if the message contract, state store, or schema has changed.

## 31. Common migration pitfalls

| Symptom | Possible cause | Fix |
|---|---|---|
| Function bean exists but is not bound | `spring.cloud.function.definition` omits the function | Declare definition and check startup logs |
| No messages received | Old `input` used, but new binding is `acceptOrder-in-0` | Remap or use binding alias |
| Replays historical events | Accidentally changed group or subscription | Keep old group; review offset policy |
| Output goes to a different topic | Output destination not remapped | Configure `acceptOrder-out-0.destination` |
| Retry/DLQ behaves differently | Binder property still tied to old binding name | Migrate all Kafka/Rabbit/Pulsar binding config |
| Consumer produces no output | Wrongly converted Function to Consumer | Use Function or StreamBridge per semantics |
| Supplier sends uncontrolled duplicates | Poller invokes repeatedly without state | Design event generation/outbox and control schedule |
| Message parsing fails | Content type, Serde, or native decoding changed | Compare payloads/headers/codecs |
| Headers disappear | Returning only POJO when logic needs correlationId | Use `Message<T>` and retain needed headers |
| Multiple listeners stop routing right | Conditional StreamListener does not map automatically | Implement explicit router/dispatcher and test |
| Kafka Streams rebuilds entire state | Changed application ID or state store semantics | Plan topology/state migration carefully |
| Errors swallowed, message still acked | Handler catches exception without rethrowing | Classify errors and align error handling |

## 32. Upgrade completion checklist

- [ ] No legacy `@EnableBinding`, `@Input`, `@Output`, or `@StreamListener` remains in migrated flows.
- [ ] Supplier/Function/Consumer beans have stable names and are selected in `definition`.
- [ ] All input/output bindings, aliases, and destinations are explicitly documented.
- [ ] Consumer groups/subscriptions and restart durability are preserved or changed intentionally.
- [ ] Keys, partitioning, headers, content-types, and schemas are compatible.
- [ ] Supplier pollers have the right emission cadence and do not generate unintended duplicates.
- [ ] StreamBridge is used appropriately wherever imperative publishing is required.
- [ ] Kafka/Rabbit/Pulsar binder-specific properties are migrated to the new binding names.
- [ ] Retries, acknowledgements, DLT/DLQ, and poison messages have been tested.
- [ ] Idempotency is in place for crashes, rebalances, and redeliveries.
- [ ] Kafka Streams topology/state/application ID is preserved where applicable.
- [ ] Both Test Binder and broker integration tests pass.
- [ ] Canary, rollback, and monitoring for outcomes/lag/duplicates are defined.
- [ ] Broker data or offsets are not deleted or altered merely to work around misconfiguration.

## 33. Summary

Migrating from the annotation-based model to the functional model makes Spring Cloud Stream business code clearer and easier to test: **Supplier** produces messages, **Function** processes and emits results, **Consumer** receives messages to perform actions, and **StreamBridge** supports emitting outputs from outside an input binding.

The most error-prone part is not Java syntax but the **operational contract**: binding names change from `input`/`output` to `function-in-0`/`function-out-0`; destinations, groups, serializers, partitions, retry/DLQ, and acknowledgements must all be mapped accurately. For stateful Kafka Streams, multiple binders, header routing, or conditional listeners, plan dedicated migration designs rather than mechanically swapping annotations.

A migration is only safe when business logic, message flows, error handling, and behavior during restarts/rebalances are all verified by appropriate tests.

## References

- [Spring Cloud Stream — Programming Model](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Stream — StreamBridge](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html#streambridge-and-dynamic-destinations)
- [Spring Cloud Stream — Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html)
- [Spring Cloud Stream — Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/overview.html)
- [Spring Cloud Stream — Rabbit Binder](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
