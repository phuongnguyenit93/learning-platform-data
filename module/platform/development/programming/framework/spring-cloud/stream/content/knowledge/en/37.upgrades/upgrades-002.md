# Identifying Legacy Code Using @EnableBinding, @StreamListener, Source, Processor, and Sink

In Spring Cloud Stream applications written in the first generation, developers typically defined **message channels** using `Source`, `Sink`, `Processor`, or custom interfaces, enabled them with `@EnableBinding`, and handled events inside methods annotated with `@StreamListener`. When reviewing such a service to upgrade Spring Boot/Spring Cloud Stream, you must accurately identify this **legacy annotation- and channel-based programming model** before changing dependencies or editing configuration. If you only bump versions, imports may no longer exist, and legacy `input`/`output` bindings will not automatically become `functionName-in-0`/`functionName-out-0` bindings.

This lesson belongs to the **Upgrades** chapter of the `SPRING_CLOUD_STREAM` module — the foundation for writing event-driven applications with `Supplier`, `Function`, and `Consumer` across Kafka, RabbitMQ, or Pulsar binders. The goal is first to **detect and understand legacy code traces**, map out message flows, and spot configuration and tests tied to the old model, and then know the right path to migrate to the modern functional model without silently altering destination names, consumer groups, partitions, retry/DLQ, or delivery semantics.

## 1. Two programming generations in Spring Cloud Stream

| Criterion | Legacy channel/annotation model | Recommended functional model |
|---|---|---|
| Defining entry/exit points | `@Input`, `@Output`, `Source`, `Sink`, `Processor` | Parameters and return types of `Supplier`/`Function`/`Consumer` |
| Enabling bindings | `@EnableBinding(...)` | Auto-configuration discovers function beans; `spring.cloud.function.definition` when needed |
| Processing messages | `@StreamListener` | `@Bean` returning `Consumer`, `Function`, or `Supplier` |
| Sending output from listener | `@SendTo` or `MessageChannel.send(...)` | Return value of `Function`/`Supplier`; or `StreamBridge` for imperative sends |
| Common binding names | `input`, `output`, names in `@Input/@Output` | `beanName-in-0`, `beanName-out-0` |
| Binding destination | `spring.cloud.stream.bindings.input.destination` | `spring.cloud.stream.bindings.processOrder-in-0.destination` |
| Typical tests in legacy projects | `TestSupportBinder`, `MessageCollector` | `spring-cloud-stream-test-binder`, `InputDestination`, `OutputDestination` |

The channel/annotation model was the primary API in older Spring Cloud Stream lines. These APIs were deprecated during the transition to the functional model and are no longer supported as an application model in modern Spring Cloud Stream lines, especially from 4.x onward. Verify versions via the **project's build/dependency management when performing an actual migration**; this lesson itself does not require opening any build files. Do not conclude solely from the Spring Boot version that all legacy APIs still exist.

## 2. Diagram for identifying legacy message flows

```text
                  @EnableBinding(Processor.class)
                              |
                 Processor.INPUT / OUTPUT
                              |
Kafka / RabbitMQ / Pulsar --> input MessageChannel
                              |
                              v
                  @StreamListener(Processor.INPUT)
                    handle(...) + @SendTo(...)
                              |
                              v
                       output MessageChannel
                              |
                              v
                      Kafka / RabbitMQ / Pulsar
```

In the new architecture, no separately created channel interface is needed for a standard processing flow:

```text
Broker --> functionName-in-0 --> @Bean Function<T,R> --> functionName-out-0 --> Broker
Broker --> consumerName-in-0 --> @Bean Consumer<T>
            @Bean Supplier<T> --> supplierName-out-0 --> Broker
```

When auditing a legacy repository, diagram each flow: **who emits the message**, **which input receives it**, **which handler processes it**, **which output is sent**, and **what the actual destination and group are**. This diagram matters more than renaming annotations because binder settings and delivery guarantees are tied to the message path.

## 3. Quick identification signals in source code

Strong indicators of the legacy model:

```java
import org.springframework.cloud.stream.annotation.EnableBinding;
import org.springframework.cloud.stream.annotation.StreamListener;
import org.springframework.cloud.stream.annotation.Input;
import org.springframework.cloud.stream.annotation.Output;
import org.springframework.cloud.stream.messaging.Source;
import org.springframework.cloud.stream.messaging.Sink;
import org.springframework.cloud.stream.messaging.Processor;
```

These are **import patterns for spotting historical code**, not instructions to copy into a new project. Some projects use static imports or fully qualified class names, so searching only for the string `@EnableBinding` can still miss part of the codebase.

| Trace | Likely doing what? | Look alongside for |
|---|---|---|
| `@EnableBinding(Source.class)` | Declares default output channel | Who calls `source.output().send(...)`? |
| `@EnableBinding(Sink.class)` | Declares default input channel | Method `@StreamListener(Sink.INPUT)`? |
| `@EnableBinding(Processor.class)` | Declares both input and output | `@StreamListener`, `@SendTo`, converters |
| `@EnableBinding(OrderChannels.class)` | Custom binding interface | Names in `@Input/@Output` and config |
| `@StreamListener("input")` | Processes messages from channel named `input` | Ack, error handling, `@SendTo` |
| `@SendTo("output")` | Routes return value to output channel | Return format/type and downstream target |
| `Source.OUTPUT`, `Sink.INPUT` | References legacy channel constants | `output`/`input` bindings in YAML |
| `SubscribableChannel`, `MessageChannel` | Spring Messaging channel layer | Is it linked to `@Input/@Output`? |

Having `MessageChannel` or `@Bean Consumer<T>` does not automatically mean legacy code: Spring Integration and Spring Messaging are still used in many modern contexts. Inspect **how the channel is registered with Spring Cloud Stream** before classifying it.

## 4. `@EnableBinding`: the most important starting point

This is the legacy annotation telling the framework to create bindings and infrastructure based on declared channel interfaces. For example:

```java
import org.springframework.cloud.stream.annotation.EnableBinding;
import org.springframework.cloud.stream.messaging.Sink;

@EnableBinding(Sink.class)
public class LegacyOrderApplication {
}
```

The older framework interprets this as the application needing the input channel described by `Sink`. `@EnableBinding` is not a direct connection to every topic; the actual destination is defined by binder and binding properties. In some codebases, the annotation sits on `@SpringBootApplication` or a `@Configuration` class rather than the same class as the listener.

Variants to recognize:

```java
@EnableBinding(Source.class)
// Or:
@EnableBinding(Processor.class)
// Or custom interfaces:
@EnableBinding({OrderChannels.class, AuditChannels.class})
```

`@EnableBinding` is **not equivalent** to `@EnableTestBinder`. `@EnableTestBinder` belongs to the **modern testing infrastructure** of `spring-cloud-stream-test-binder`; it is not a way to restore old channel APIs for production applications.

## 5. `Source`: indicator of a legacy producer

`Source` is an interface with **one default output channel** named `output`. In older versions, a service publishes messages by injecting `Source`, calling `output()`, and then `send()`:

```java
import org.springframework.cloud.stream.annotation.EnableBinding;
import org.springframework.cloud.stream.messaging.Source;
import org.springframework.messaging.support.MessageBuilder;

@EnableBinding(Source.class)
class LegacyOrderPublisher {

    private final Source source;

    LegacyOrderPublisher(Source source) {
        this.source = source;
    }

    boolean publishOrder(String orderId) {
        return source.output().send(
            MessageBuilder.withPayload(orderId).build()
        );
    }
}
```

Details to record during inventory:

1. `Source.OUTPUT`/`output()` maps to the **`output` binding**, not necessarily a topic named `output`.
2. Messages are sent **imperatively when the method is called** (for example, from a REST handler), not necessarily on a schedule.
3. `send` returns the status of sending to the message channel in that model; it does not automatically mean the broker persisted it durably or a consumer processed it.
4. A service may call `source.output().send()` in multiple places; locate **every call site** before replacing it with `Supplier` or `StreamBridge`.

Legacy configuration example:

```yaml
spring:
  cloud:
    stream:
      bindings:
        output:
          destination: orders.created
```

If rewritten under the functional model without preserving this destination, messages could be sent to a different topic named after the new binding. For a publisher that emits on requests/commands, the usual approach is **`StreamBridge`**; a polling `Supplier` is only appropriate when the nature of the flow is to actively supply values periodically.

## 6. `Sink`: indicator of a legacy consumer

`Sink` defines **one default input channel** named `input`. A common signature is `@EnableBinding(Sink.class)` paired with `@StreamListener(Sink.INPUT)`:

```java
import org.springframework.cloud.stream.annotation.EnableBinding;
import org.springframework.cloud.stream.annotation.StreamListener;
import org.springframework.cloud.stream.messaging.Sink;

@EnableBinding(Sink.class)
class LegacyOrderConsumer {

    @StreamListener(Sink.INPUT)
    public void consume(String payload) {
        System.out.println("Received: " + payload);
    }
}
```

`Sink.INPUT` has the logical value `input`. If `consume` returns no data, it usually corresponds to a `Consumer<T>` role in the functional model. However, check whether the method updates a database, makes HTTP calls, publishes additional events, handles exceptions, or manually acks: those side effects dictate how to rewrite it, not just the `void` return type.

Legacy YAML example:

```yaml
spring:
  cloud:
    stream:
      bindings:
        input:
          destination: orders.created
          group: order-projection
          content-type: application/json
```

`input` is the **binding name**; `orders.created` is the **destination**; `order-projection` is the **consumer group**. Do not change the group during migration if you want the new consumer to continue processing under the same logical identity and expected offset/subscription policy. Different binders handle groups and offsets differently, so keeping the group still requires testing with the actual middleware.

## 7. `Processor`: has one input and one output

`Processor` combines the roles of `Sink` and `Source`, providing `Processor.INPUT` (value `input`) and `Processor.OUTPUT` (value `output`). This is the most common pattern when an application **receives, transforms, and forwards** events:

```java
import org.springframework.cloud.stream.annotation.EnableBinding;
import org.springframework.cloud.stream.annotation.StreamListener;
import org.springframework.cloud.stream.messaging.Processor;
import org.springframework.messaging.handler.annotation.SendTo;

@EnableBinding(Processor.class)
class LegacyOrderProcessor {

    @StreamListener(Processor.INPUT)
    @SendTo(Processor.OUTPUT)
    public String normalize(String orderId) {
        return orderId.trim().toUpperCase();
    }
}
```

In legacy code, `@StreamListener(Processor.INPUT)` specifies the input channel, while `@SendTo(Processor.OUTPUT)` sends the **return value** to the output channel. If you drop `@SendTo` during refactoring without another publish path, the output may disappear. If `Message<T>` is used, preserve important business headers during transformation.

```yaml
spring:
  cloud:
    stream:
      bindings:
        input:
          destination: orders.raw
          group: order-normalizer
        output:
          destination: orders.normalized
```

After migrating to a function bean named `normalize`, the default bindings become `normalize-in-0` and `normalize-out-0`. **The broker destination names can stay the same**, but you must update or alias the binding properties.

## 8. `@StreamListener`: event-handling method invoked by the framework

`@StreamListener` in historical code marks a method that processes records from an input channel. Common form:

```java
@StreamListener("input")
public void onMessage(String body) {
    // Legacy event processing
}
```

Or with a constant name:

```java
@StreamListener(Sink.INPUT)
public void onMessage(Message<String> message) {
    // Read payload and headers
}
```

Variants to document:

- Parameter is a POJO, `String`, `byte[]`, or `Message<T>`.
- Method returns `void` (usually consume-only) or has a return type (may emit output).
- With or without `@SendTo`.
- Conditional `@StreamListener(value = ..., condition = ...)`.
- Multiple `@StreamListener` methods on the same input or across multiple channels.
- Header parameters, such as `@Header(...)`.
- Binder-specific exception handling, retries, or acknowledgments.

`@StreamListener` is not a function bean name discovered by Spring Cloud Function via `definition`. Setting `spring.cloud.function.definition` to the old method name while keeping `@StreamListener` will **not** automatically create a new functional binding; you must convert the method into a properly typed function bean.

## 9. `@SendTo`: the listener's output path

In legacy code, `@SendTo` from Spring Messaging is a key sign that a return value is being routed. For example:

```java
@StreamListener(Processor.INPUT)
@SendTo(Processor.OUTPUT)
public String trim(String body) {
    return body.trim();
}
```

If a method returns `void`, there is normally no output from the return value; if it calls `MessageChannel.send()` internally, it still has a message-publishing side effect. When mapping flows, check **both `@SendTo` and manual send calls**.

Do not merge all `@StreamListener` methods with `@SendTo` into a single `Function<T,R>` if there is multi-branch routing, multiple outputs, delays, acks, or conditions. A single `Function` fits simple one-to-one processing, whereas complex flows require explicitly designing output bindings and routing rules.

## 10. Custom interfaces with `@Input` and `@Output`

Not all legacy code imports `Source`, `Sink`, or `Processor`. Some applications define custom interfaces:

```java
import org.springframework.cloud.stream.annotation.Input;
import org.springframework.cloud.stream.annotation.Output;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.SubscribableChannel;

interface OrderChannels {
    String ORDERS_IN = "ordersIn";
    String ORDERS_OUT = "ordersOut";

    @Input(ORDERS_IN)
    SubscribableChannel ordersIn();

    @Output(ORDERS_OUT)
    MessageChannel ordersOut();
}
```

Consuming class:

```java
@EnableBinding(OrderChannels.class)
class LegacyCustomChannels {

    @StreamListener(OrderChannels.ORDERS_IN)
    @SendTo(OrderChannels.ORDERS_OUT)
    public String process(String body) {
        return body.toUpperCase();
    }
}
```

The binding names are **`ordersIn` and `ordersOut`**, not `input`/`output`. Trace constants, string literals, `@Input`, `@Output`, and configuration; do not search only for `Processor.INPUT`.

```yaml
spring:
  cloud:
    stream:
      bindings:
        ordersIn:
          destination: orders.raw
          group: order-projection
        ordersOut:
          destination: orders.normalized
```

An interface can contain multiple `@Input`/`@Output` declarations. Each channel creates a message path that must be inventoried independently. In the new functional model, these paths may become multiple functions, one multi-output function, or `StreamBridge`, depending on semantics rather than annotation count.

## 11. Identifying direct sends via `MessageChannel`

Not every legacy application has `@StreamListener` methods; some only have REST endpoints, schedulers, or domain services using `MessageChannel` to send messages. For example:

```java
@EnableBinding(Source.class)
class LegacyEventGateway {

    private final MessageChannel output;

    LegacyEventGateway(Source source) {
        this.output = source.output();
    }

    void fire(String event) {
        output.send(MessageBuilder.withPayload(event).build());
    }
}
```

To detect this pattern, search for `MessageChannel.send(`, `.output().send(`, `@Autowired Source`, and injections of `@Output` interfaces. Check whether the call site is triggered by a request, domain transaction, scheduler, or message handler. A publisher firing on **business events** cannot be blindly replaced with a `Supplier` polling every second without changing behavior.

`MessageChannel` is also widely used in Spring Integration; only classify it as a **Spring Cloud Stream legacy channel** if it is tied to `@EnableBinding`/`@Output`/corresponding binding configuration.

## 12. Legacy binding names are not identical to topic/queue names

Legacy configuration:

```yaml
spring:
  cloud:
    stream:
      bindings:
        input:
          destination: orders.events
          group: order-processor
        output:
          destination: orders.validated
```

Here `input` and `output` are **logical names inside the application**; the binder translates them into consumers/producers for the corresponding broker destination. The Kafka Binder typically points to a topic, the RabbitMQ Binder can create exchanges/queues named according to destination/group, and the Pulsar Binder points to a topic and subscription per binder configuration.

After converting to the functional model, a bean named `validateOrder` generates by default:

```text
validateOrder-in-0  -> orders.events
validateOrder-out-0 -> orders.validated
```

You must migrate the destination, consumer group, and **extended binder properties** attached to `input`/`output`; if you only change Java code, the old properties may no longer apply to the new bindings.

## 13. Checking binder-specific settings tied to legacy names

Besides `spring.cloud.stream.bindings.*`, applications often have properties under the Kafka, RabbitMQ, or Pulsar binder namespaces. Example legacy Kafka Binder trace:

```yaml
spring:
  cloud:
    stream:
      bindings:
        input:
          destination: orders.events
          group: order-processor
          consumer:
            concurrency: 3
            maxAttempts: 3
      kafka:
        bindings:
          input:
            consumer:
              enableDlq: true
              dlqName: orders.events.dlq
```

This is illustrative syntax for the **legacy Kafka Binder configuration model**; availability, property names, and behavior when enabling retry/DLQ depend on the version. When renaming `input` to `processOrder-in-0`, `kafka.bindings.input.consumer...` must also be checked/renamed unless compatibility aliases are used.

Property groups to inventory:

| Group | Example | Risk if missed |
|---|---|---|
| Destination | `bindings.input.destination` | Reads from/writes to unintended topic/queue |
| Group/subscription | `bindings.input.group` | Changes offset/subscription, risking replay/duplicates |
| Concurrency | `bindings.input.consumer.concurrency` | Changes throughput/ordering |
| Retry | `maxAttempts`, backoff | Different error handling and blocking duration |
| Kafka DLQ | `kafka.bindings.input.consumer.enableDlq` | Failed messages do not reach the right DLQ |
| RabbitMQ topology | exchange, queue, routing, DLX | Creates different queues/exchanges or changes routing |
| Pulsar subscription | subscription type/name and producer/consumer properties | May replay, misdistribute load, or lose key ordering |
| Serialization | `content-type`, native encoding/Serde | Alters actual payload/schema |
| Partitioning | key expression, partition count | Alters key-to-partition mapping and ordering |
| Error/ack | error channel, ack mode/handler | Premature commit, infinite retry, or message loss |

Modern property names can change, not just the binding prefix. In an actual migration, verify exact names against the Spring Cloud Stream/binder documentation for the **target release train** and test with the broker instead of copying old YAML and assuming it is enough.

## 14. Conditional `@StreamListener` methods

Some legacy code handles multiple message types on the same channel via `condition`, for example:

```java
@StreamListener(value = Sink.INPUT,
                condition = "headers['eventType']=='ORDER_CREATED'")
public void onCreated(String payload) {
    // Handle order created event
}

@StreamListener(value = Sink.INPUT,
                condition = "headers['eventType']=='ORDER_PAID'")
public void onPaid(String payload) {
    // Handle order paid event
}
```

This is a **legacy syntax recognition example** and should not be carried over verbatim to the new model. In the functional model, two independent `Consumer` beans subscribing to the same destination are not automatically equivalent to the old conditional routing mechanism; the broker may load-balance messages rather than broadcasting depending on group/binder.

Conversion options must be designed explicitly: a single `Consumer<Message<T>>` reading the header and dispatching by `eventType`, a properly configured function router, or separate destinations/consumer groups with matching publishing rules. Changing from conditions on a single input to two independent groups can significantly change delivery behavior, throughput, and duplication.

## 15. Methods with multiple parameters, headers, and error handling

Do not stop at annotation names; inspect the **method signature and surrounding logic**:

```java
@StreamListener(Sink.INPUT)
public void handle(
        String body,
        @Header("correlationId") String correlationId) {
    // Use payload together with header
}
```

Items to record in the inventory:

- Does the signature use `Message<T>`, `@Payload`, `@Header`, or raw `byte[]`?
- Are headers used for keys, partitioning, routing, or correlation IDs?
- Is there `try/catch`, manual retry, an error channel, or programmatic DLQ forwarding?
- Does the method return early while work still runs asynchronously?
- Do transactions/acks/commits depend on when the method returns?
- Does it write to a database, call other services, publish new messages, or participate in a saga?

In the functional model, `Consumer<Message<T>>` or `Function<Message<T>, Message<R>>` is typically used when handling headers. `Function<T,R>` has a simpler payload signature, but not all business headers are preserved the same way when message types change. You must test message converters, header mapping, and binder-specific delivery semantics.

## 16. Legacy code signs in tests

Historical tests may use `spring-cloud-stream-test-support`, `TestSupportBinder`, or `MessageCollector`. A common pattern sends a message to an input channel or polls emitted messages via the collector:

```java
// Legacy generation test API signature:
@Autowired
private MessageCollector messageCollector;

@Autowired
private Processor processor;

// Inside a legacy project test method:
processor.input().send(MessageBuilder.withPayload("abc").build());
Message<?> out = messageCollector
    .forChannel(processor.output())
    .poll();
```

The snippet above intentionally omits imports and assertions: it is an **identification pattern**, not a complete test meant to run on modern versions. Also look for `org.springframework.cloud.stream.test.binder` and older test-support imports. Do not assume production code is successfully upgraded just because old tests no longer compile: test infrastructure must be migrated as well.

For modern Spring Cloud Stream, the Test Binder provides the `spring-cloud-stream-test-binder` dependency and `InputDestination`, `OutputDestination`, and `@EnableTestBinder` APIs. Do **not** replace `@EnableBinding` with `@EnableTestBinder` in production: the new annotation is solely for test contexts.

## 17. Identifying dependencies and versions behind legacy APIs

When authorized to migrate an actual repository, inspect the BOM, Spring Boot/Spring Cloud release train, and binder artifacts. Dependencies commonly found in legacy projects:

```text
org.springframework.cloud:spring-cloud-stream
org.springframework.cloud:spring-cloud-stream-binder-kafka
org.springframework.cloud:spring-cloud-stream-binder-rabbit
org.springframework.cloud:spring-cloud-stream-test-support
```

The presence of the Kafka or Rabbit binder **does not prove** the application still uses the annotation model: the same binders also power the functional model. Stronger evidence is importing `org.springframework.cloud.stream.annotation.EnableBinding` or `org.springframework.cloud.stream.messaging.Source` in Java code alongside `input`/`output` configuration.

Some modules use Spring Kafka (`@KafkaListener`), Spring AMQP (`@RabbitListener`), or native Pulsar listeners instead of Spring Cloud Stream. Those annotations belong to **different** APIs; do not classify them as legacy `@StreamListener` and do not blindly convert them to `Consumer<T>` unless a technology change is requested.

## 18. Searching for legacy code systematically

In a project where you have permission to inspect the entire repository, you can use the following **reference** search commands. This lesson does not require running them in the current workspace.

```bash
# Find legacy channel annotations or interfaces in Java:
rg -n '@EnableBinding|@StreamListener|@Input\(|@Output\(|@SendTo' src
rg -n 'cloud\.stream\.messaging\.(Source|Sink|Processor)' src
rg -n 'Source\.OUTPUT|Sink\.INPUT|Processor\.(INPUT|OUTPUT)' src

# Find channel-based sending and receiving:
rg -n 'MessageChannel|SubscribableChannel|\.output\(\)\.send|\.send\(' src

# Find legacy binding config and test APIs:
rg -n 'spring-cloud-stream-test-support|MessageCollector|TestSupportBinder' .
rg -n 'spring\.cloud\.stream|bindings:|destination:|group:' src/main/resources
```

`rg` is the ripgrep tool; IDE Find in Files can be used instead. Searching for `send(` is very broad, so its matches are **candidates to read**, not final proof. If the project uses static imports, searching `@EnableBinding` and `@StreamListener` still catches annotations even when import lines are omitted. If code is generated by annotation processing or comes from library classes, verify the actual call paths.

Do not perform bulk text find-and-replace because multiple `Processor.INPUT` references may map to different destinations depending on profiles and binder environments.

## 19. Sample inventory table for the upgrade process

Before editing code, create one row per **message path**, not just one row per Java class:

| Inventory field | Example | Why it matters |
|---|---|---|
| Java owner | `LegacyOrderProcessor.normalize` | Locates the handler |
| Legacy API | `@EnableBinding(Processor.class)`, `@StreamListener` | Identifies declaration mechanism |
| Input binding | `input` | Matches old config key |
| Output binding | `output` | Matches publish path |
| Input destination | `orders.raw` | Preserves data source |
| Output destination | `orders.normalized` | Preserves target topic/queue |
| Consumer group | `order-normalizer` | Protects offsets/subscriptions |
| Payload and schema | `OrderEvent` + JSON/Avro | Prevents converter/Serde errors |
| Headers | `correlationId`, Kafka key | Preserves tracking/routing |
| Retry/DLQ | `maxAttempts=3`, Kafka DLQ | Preserves error policy |
| Partition/concurrency | 12 partitions, 3 threads | Avoids altering ordering/throughput |
| Side effects | DB update + outbound message | Evaluates transactions/idempotency |
| Existing tests | `MessageCollector` or integration tests | Shows what must be rewritten |

If the system has multiple profiles (`local`, `staging`, `prod`) or distinct binder instances, actual destination/group values may vary. The inventory must capture environment-specific critical settings, not only defaults from a single YAML file.

## 20. Distinguishing `Source` from a functional `Supplier`

The name `Source` leads many to think it can be mechanically replaced with `Supplier<T>`, but you must inspect the **publish trigger condition**:

| Legacy code | Semantics | Usually appropriate new approach |
|---|---|---|
| REST controller calls `source.output().send(event)` | Emits on incoming request | `StreamBridge.send(bindingName, event)` |
| Domain transaction calls `output.send(...)` | Emits after business state change | `StreamBridge` paired with appropriate outbox/transaction boundary |
| Scheduler every minute calls `send` | Emits on schedule | `Supplier` with suitable poller or scheduler + `StreamBridge` |
| Infinite generator/streaming events | Continuous emission | Reactive `Supplier<Flux<T>>` if semantics and lifecycle fit |

A Spring Cloud Function `Supplier` can be polled on a schedule by the framework. If a publisher previously emitted only when a payment command arrived, switching it to a `Supplier` that returns the same value on every poll could emit **duplicate events**. Choose the migration target based on actual runtime behavior rather than the legacy interface name.

## 21. `Sink` usually migrates to `Consumer<T>`

For a listener that only processes one input and produces no output, the fitting functional model is:

```java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class OrderConsumerConfiguration {

    @Bean
    Consumer<String> consumeOrder() {
        return payload -> System.out.println("Received: " + payload);
    }
}
```

The new default binding is `consumeOrder-in-0`. To keep the destination/group from the legacy `Sink` example:

```yaml
spring:
  cloud:
    function:
      definition: consumeOrder
    stream:
      bindings:
        consumeOrder-in-0:
          destination: orders.created
          group: order-projection
          content-type: application/json
```

This is a **model comparison example**, not proof that business tests pass. If the old listener accepted `Message<String>` or read partition/key headers, update the signature and assertions accordingly. If the old listener used custom transactions/acks, test against the real container and binder, not just a unit test of `Consumer.accept`.

## 22. `Processor` usually migrates to `Function<T,R>`

Example converting a legacy handler with `@SendTo`:

```java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class OrderTransformConfiguration {

    @Bean
    Function<String, String> normalizeOrder() {
        return orderId -> orderId.trim().toUpperCase();
    }
}
```

Configuration mapping:

```yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.raw
          group: order-normalizer
        normalizeOrder-out-0:
          destination: orders.normalized
```

`Function<T,R>` fits when an input value produces one output value along the same pipeline. If the old handler had multiple side effects or distinct output routes, analyze those separately. Do not assume every POJO-returning `@StreamListener` had `@SendTo` and a single explicit output.

## 23. Legacy on-demand publishers: `StreamBridge`

To replace imperative sending via `Source.output().send(...)`, the modern API is typically `StreamBridge`:

```java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
class OrderEventPublisher {

    private final StreamBridge streamBridge;

    OrderEventPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    boolean publish(String orderId) {
        return streamBridge.send(
            "orders-out-0",
            MessageBuilder.withPayload(orderId).build()
        );
    }
}
```

Bind the output binding name `orders-out-0` to the old destination:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
```

`StreamBridge.send(...)` creates/uses an output binding based on the supplied name and configuration; it is not the exact same API as `MessageChannel.send(...)`. Test payload types, headers, binder routing, failure handling, and binder send-confirmation semantics. Do not interpret the boolean return of `send` as a guarantee of end-to-end delivery or consumer processing.

## 24. Renaming bindings explicitly or using aliases

The functional model generates implicit binding names from function bean names. There are two strategies to preserve legacy configuration:

**Approach A — Rename configuration keys to the new names**, clearer in the long run:

```yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.raw
          group: order-normalizer
        normalizeOrder-out-0:
          destination: orders.normalized
```

**Approach B — Alias implicit bindings to the old names**, useful when many properties already reference `input`/`output`:

```yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      function:
        bindings:
          normalizeOrder-in-0: input
          normalizeOrder-out-0: output
      bindings:
        input:
          destination: orders.raw
          group: order-normalizer
        output:
          destination: orders.normalized
```

The `spring.cloud.stream.function.bindings` property maps an **implicit function binding name** to an explicit binding name. When using aliases, be consistent: destination and extended binder properties must attach to the mapped binding name. Aliasing does not restore removed `@StreamListener` or `@EnableBinding` APIs; it only names bindings for **modern function beans**.

Use aliases only when there is a real migration benefit; avoid adding extra naming layers that cause confusion when the project has no compatibility constraints.

## 25. Check `spring.cloud.function.definition` when an app has multiple functions

In the old model, `@EnableBinding` listed channel interfaces, and `@StreamListener` methods declared which inputs to consume. In the functional model, an application with multiple `Consumer`, `Function`, and `Supplier` beans must select which functions are bound to the broker via configuration.

```java
@Bean
Consumer<String> auditOrder() {
    return value -> System.out.println("Audit: " + value);
}

@Bean
Function<String, String> normalizeOrder() {
    return value -> value.trim().toUpperCase();
}
```

Example selecting two independent functions:

```yaml
spring:
  cloud:
    function:
      definition: auditOrder;normalizeOrder
```

In the functional model, `;` separates multiple independent function definitions, while `|` is Spring Cloud Function's composition syntax. These two cannot be swapped arbitrarily: composition changes the input/output flow, data types, and binding names. If an app has multiple function beans and `definition` is not explicitly set, auto-detection may fail to initialize bindings as the upgrader expects.

When auditing a legacy app with multiple listeners, document which listeners are independent flows, which share the same channel, and which form sequential stages. Only then decide on `definition`, composition, or an orchestrating function.

## 26. Be careful with reactive `@StreamListener` methods

Legacy code sometimes accepts/returns `Flux` or uses `@StreamListener` with Kafka Streams `KStream`/`KTable` instead of individual POJOs. Signature recognition example (illustrative):

```java
@StreamListener("input")
@SendTo("output")
public Flux<String> transform(Flux<String> input) {
    return input.map(String::toUpperCase);
}
```

Do not convert this directly into `Function<String,String>` if the previous behavior was a continuous reactive stream with different backpressure, batching, windowing, or concurrency. You must understand subscription boundaries, completion, error signals, and the framework version in use. The functional model supports reactive types like `Function<Flux<T>, Flux<R>>` in appropriate contexts, but their semantics differ from per-message functions and require checking binder support.

In particular, the Kafka Streams Binder supports processing tied to `KStream`/`KTable`; when upgrading, the target may be `Function<KStream<K,V>, KStream<K2,V2>>` or `Consumer<KStream<K,V>>`, not a regular `Function<OrderEvent,OrderEvent>`. You must preserve the application ID, Serdes, task topology, repartitioning, changelog/state stores, and compatibility with existing Kafka data. Looking solely at `@StreamListener` without checking **parameter types** will misclassify the application type.

## 27. Java patterns that do not mean legacy Spring Cloud Stream APIs

When searching across a repository, many matches have similar names but different semantics:

| Signal | Which system? | Is it a legacy Stream indicator? |
|---|---|---|
| `@EnableBinding` from `org.springframework.cloud.stream.annotation` | Spring Cloud Stream annotation model | Yes |
| `@StreamListener` from `org.springframework.cloud.stream.annotation` | Spring Cloud Stream annotation model | Yes |
| `@EnableTestBinder` | Spring Cloud Stream Test Binder | No; this is a test API |
| `@KafkaListener` | Spring Kafka | Not directly |
| `@RabbitListener` | Spring AMQP | Not directly |
| `@Bean Consumer<OrderEvent>` | Spring Cloud Function/Java functional bean | Usually the new model |
| `MessageChannel` without `@Output` | Spring Messaging/Integration or custom code | Not sufficient evidence |
| `Function<T,R>` used only in Java algorithms | Java standard library | Not necessarily bound to a broker |

When reporting "how many places need migration," count only entry points and output paths that **truly belong to the annotation-based Spring Cloud Stream model**. If a class uses both `@KafkaListener` and `@StreamListener`, map the two data paths separately and do not mistakenly replace the Spring Kafka listener method.

## 28. Risks of changing APIs without preserving semantics

| Rushed upgrade action | Potential consequence | Check before deploying |
|---|---|---|
| Removing `@EnableBinding` while keeping `@StreamListener` | New function bindings are not created | Are real `Consumer/Function/Supplier` beans present? |
| Changing `Processor` to `Function` while keeping YAML `input`/`output` | New bindings use unexpected default destinations | Verify runtime binding names and destinations |
| Renaming consumer group per Pod/release | Offsets/subscriptions split, replaying or duplicating messages | Keep the old group or plan an offset migration |
| Converting an imperative publisher to a polling Supplier | Sends duplicate messages or emits at the wrong times | Record the publisher's actual trigger source |
| Dropping `@SendTo` with no replacement output | Downstream events stop being published | Test output payload and destination |
| Dropping `@Header` to keep only a POJO | Loses correlation/routing/partition keys | Assert headers in integration tests |
| Replacing `condition` with two uncoordinated Consumers on one destination | Consumers may see/split messages differently than before | Verify group/binder semantics |
| Changing `Message<T>` to `T` without checking converters | Payload/schema or headers change | Test content type, schema, and Serdes |
| Upgrading binder without checking retry/DLQ | Errors are retried or dead-lettered differently than before | Integration test transient errors and poison messages |
| Increasing concurrency after migration | Per-key/partition ordering impacted by app logic | Test ordering, acks, and database versioning |
| Upgrading Kafka Streams topology without checking state | Unexpected restore/repartition/changelog behavior | Test state compatibility and recovery |

The core takeaway is that **legacy annotations do not capture the entire operational contract**. The contract resides in the combination of Java methods, binding names, binder properties, broker topology, schemas, producer/consumer groups, and error handling.

## 29. Deduplication and delivery models during migration

A legacy consumer may receive messages with at-least-once delivery: if the database write succeeds but the app crashes before ack/offset commit, the message may be redelivered. After migration, you must still protect:

```text
Broker -> Consumer -> check eventId/version
                     -> transaction updating data
                     -> ack/commit once safe
```

If the new handler returns immediately after offloading work to a thread pool, the binder may receive a success signal before the database update happens; that is not equivalent to a synchronous legacy handler. Kafka transactions/exactly-once semantics do not automatically create distributed transactions with external databases outside Kafka; idempotency, transactional outbox, or proper coordination design is required.

During inventory, document *when the method returns*, *when side effects become durable*, *when ack/commit happens*, *how retries work*, and *how DLQ replay works*. These migration test criteria matter more than whether Java classes compile cleanly.

## 30. Separating identification from upgrade decisions

The implementation process can be split into two clear parts:

**Part A — Identify without changing behavior**

1. List legacy channel annotations and interfaces.
2. Link them to `bindings`, `kafka.bindings`, `rabbit.bindings`, or Pulsar binder configuration depending on version.
3. Diagram every input → handler → output path, including side effects.
4. Record destinations, groups/subscriptions, partitioning, serializers, and retry/DLQ.
5. Read existing tests to identify the real contract and coverage gaps.
6. Classify handlers: consume-only, transform, publish-on-demand, multi-input, multi-output, reactive/stateful.

**Part B — Controlled conversion**

1. Select the appropriate functional bean type or `StreamBridge`.
2. Explicitly set `spring.cloud.function.definition` and binding names.
3. Map destinations/groups and binder-specific properties.
4. Write unit tests for business logic and Test Binder tests for functional wiring.
5. Write integration tests against the actual Kafka/RabbitMQ/Pulsar and broker policies.
6. Perform a controlled canary/rolling update, comparing message flows and metrics.
7. Remove legacy code only after the new message paths and rollback strategy are verified.

**Do not accidentally run two consumer paths from two versions in parallel** on the same topic. If they use different groups, each group may process the same events; if they share a group while handling different schemas/protocols, results can become inconsistent. For zero-downtime upgrades, design version compatibility, ownership, and rollback explicitly.

## 31. Practical example: inventorying a legacy service

Suppose internal documentation for a legacy service shows:

```java
@EnableBinding(Processor.class)
class PaymentNormalizer {

    @StreamListener(Processor.INPUT)
    @SendTo(Processor.OUTPUT)
    public String normalize(String reference) {
        return reference.trim().toUpperCase();
    }
}
```

And configuration:

```yaml
spring:
  cloud:
    stream:
      bindings:
        input:
          destination: payments.raw
          group: payment-normalizer
          content-type: text/plain
        output:
          destination: payments.normalized
          content-type: text/plain
```

The inventory should record:

| Item | Inventory finding |
|---|---|
| Legacy API | `@EnableBinding`, `Processor`, `@StreamListener`, `@SendTo` |
| Processing pattern | Single input → single output, synchronous transform |
| Logical input binding | `input` |
| Input destination | `payments.raw` |
| Consumer group | `payment-normalizer` |
| Logical output binding | `output` |
| Output destination | `payments.normalized` |
| Payload | `String`, trim + uppercase, `text/plain` |
| Unknowns | Retry/DLQ, binder type, serializer, ack, idempotency, deployment replicas |

After identification, you can write `Function<String,String> normalizePayment` and migrate binding names to `normalizePayment-in-0`/`normalizePayment-out-0`, but you **must not** declare migration complete until the "unknowns" are answered and tested. Good practice records missing information as well; never fill in assumptions as if they were verified.

## 32. Regression testing for API upgrades

A useful test suite should include:

| Scenario | Goal | Suitable tool |
|---|---|---|
| Valid string/JSON input | Transformation logic matches previous behavior | Unit test + Test Binder |
| Missing fields/invalid schema input | Converters and error handling work properly | Test Binder + broker integration |
| Correct output destination | Does not publish to unintended new topics/queues | Configuration integration test |
| Preserved consumer group | Does not unexpectedly change offsets/subscriptions | Broker integration |
| Retry and DLQ | Failed messages follow expected error policy | Real Kafka/RabbitMQ/Pulsar or test environment |
| Kafka partition key | Same key still routes to the designed partition | Kafka integration |
| Rabbit exchange/queue/routing | Provisioning/routing remains unchanged | RabbitMQ integration |
| Pulsar subscription/schema | Consumer reads the right backlog/encoding | Pulsar integration |
| Crash after side effect | Redelivery does not duplicate side effects | Fault-injection integration |
| Multi-function routing | Messages reach the right conditional handler | Functional integration test |
| Kafka Streams state restore | State remains compatible after deployment | Topology/stateful integration |

Modern Test Binder verifies wiring and message transformations, but does not replace broker-level tests for partitions, ACLs, DLQs, consumer group rebalancing, and delivery guarantees. When upgrading an app that relied on `MessageCollector`, migrate the test infrastructure alongside production code to maintain reliable regression coverage.

## 33. Diagnosing common errors when reading or upgrading legacy code

| Symptom | Possible cause | Diagnostic direction |
|---|---|---|
| IDE cannot find `@EnableBinding` | Newer Spring Cloud Stream no longer provides legacy APIs | Identify the release train and migrate to the functional model |
| `@StreamListener` no longer runs | Annotation model is unsupported/unregistered | Create function beans and new bindings |
| App starts but receives no events | New binding points to a different default destination | Check `function.definition`, bindings/destinations |
| Replays old messages or duplicates appear | Group/subscription changed | Compare old and new consumer groups, offsets/subscriptions |
| Output does not appear | Old method had `@SendTo`, new function returns no output | Check `Function` return type, output binding, and destination |
| Function exists but is not bound | Multiple beans exist and `definition` is missing/wrong | Specify the right function bean or composition |
| Kafka DLQ stops working | Binder-specific config still references old `input` key | Rename/alias extended binding properties |
| Schema mapping fails | Message converter/content type/native serde differs | Compare payloads and headers on the broker |
| `MessageCollector` test fails to compile | Old test-support is incompatible | Use version-matched `spring-cloud-stream-test-binder` |
| Changing publisher to Supplier causes duplicates | Poller triggers repeatedly | Use `StreamBridge` for event-triggered sends |
| Kafka Streams fails to restore state | Topology/Serde/application ID changed | Verify compatibility and state recovery |

## 34. Identification checklist before changing a single line of code

- [ ] Located `@EnableBinding`, `@StreamListener`, `@Input`, `@Output`, and `@SendTo`.
- [ ] Located imports of `Source`, `Sink`, `Processor`, and custom channel interfaces.
- [ ] Identified all call sites of `MessageChannel.send()` and `source.output().send()`.
- [ ] Distinguished channel binding names from broker destinations.
- [ ] Mapped input → handler → output for every event flow.
- [ ] Recorded exact consumer groups/subscriptions rather than inferring them from service names.
- [ ] Checked whether Kafka/RabbitMQ/Pulsar binder-specific properties reference legacy binding names.
- [ ] Identified conditional listeners, multi-input/multi-output, reactive, and Kafka Streams handlers.
- [ ] Documented payload types, content types, schemas, and business headers.
- [ ] Identified retry, DLQ, ack/offset, transaction, and side-effect behavior.
- [ ] Located legacy test-support usage and planned test infrastructure migration.
- [ ] Chosen among `Consumer`, `Function`, `Supplier`, and `StreamBridge` based on actual behavior.
- [ ] Decided between renaming binding keys or using `spring.cloud.stream.function.bindings` aliases.
- [ ] Prepared regression test suites using real brokers for critical delivery guarantees.

## 35. Self-check questions

1. Which channels do `Source`, `Sink`, and `Processor` provide, and what are their default names?
2. How do `@EnableBinding(Processor.class)` and `@StreamListener(Processor.INPUT)` differ in responsibility?
3. Why is `@SendTo(Processor.OUTPUT)` a trace that must be inspected separately during an upgrade?
4. How do you find the exact binding name when an application uses an interface with `@Input("ordersIn")`?
5. Does `bindings.input.destination=orders.raw` mean the topic must be named `input`?
6. Why can changing `input` to `normalize-in-0` while leaving Kafka DLQ properties unchanged cause errors?
7. When a legacy publisher sends inside a REST handler, is a polling `Supplier` always equivalent to `Source.output().send()`?
8. Should `@EnableBinding` be replaced with `@EnableTestBinder` in a production application? Why or why not?
9. What additional analysis is needed for a `@StreamListener` accepting `Flux` or `KStream`?
10. Why is preserving consumer groups, ack/commit, and idempotency critical when changing APIs even if transformation logic stays unchanged?

## Conclusion

Identifying legacy Spring Cloud Stream code is the process of finding **traces of the channel/annotation model**, not merely scanning for a few class names. `@EnableBinding` creates bindings for `Source`/`Sink`/`Processor` or `@Input`/`@Output` interfaces; `@StreamListener` processes inputs; `@SendTo` and `MessageChannel.send` are outbound paths to trace. Configuration under `bindings.input`/`bindings.output`, consumer groups, destinations, binder extensions, retry/DLQ, serialization, and legacy test-support are all part of the same event-processing contract. Only after completing a full inventory should you choose `Supplier`, `Function`, `Consumer`, or `StreamBridge`, migrate binding names deliberately, and verify with regression/integration tests before upgrading production.

## References

- Spring Cloud Stream Reference — Functional Binding Names: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html
- Spring Cloud Stream Reference — Producing and Consuming Messages: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html
- Spring Cloud Stream Reference — Binding Properties: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html
- Spring Cloud Stream Reference — StreamBridge: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html#streambridge-and-dynamic-destinations
- Spring Cloud Stream Reference — Test Binder: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/spring_integration_test_binder.html
- Spring Cloud Function Reference — Function Definition and Composition: https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html
- Spring Cloud Stream 3.x Documentation — Historical annotation programming model (consult the version matching your legacy project): https://docs.spring.io/spring-cloud-stream/docs/3.2.x/reference/html/
