# Migrating Legacy input and output Names to Functional Binding Names

When upgrading a Spring Cloud Stream application from the legacy annotation model to the functional model (`Supplier`, `Function`, `Consumer`), an easily overlooked change is the **binding name**. Previously, interfaces like `Source`, `Sink`, and `Processor` usually had binding names `output` or `input`. In the functional model, default names are generated from the **function bean name**, data direction, and port index.

Renaming a logical binding **does not mean you must rename Kafka topics, RabbitMQ exchanges/queues, or Pulsar topics**. If you only update Java code and forget the configuration keys, the application may connect to an unintended destination or fail to apply the previously used consumer group, retry, DLQ, partitioning, and binder settings. This lesson explains how to migrate in a controlled way, preserve message paths, and verify with tests before deployment.

## 1. Distinguishing three types of names

| Name type | Example | Meaning |
|---|---|---|
| **Function bean name** | `uppercase` | `Function`, `Consumer`, or `Supplier` bean managed by Spring |
| **Binding name** | `uppercase-in-0`, `uppercase-out-0` | Logical key used by Spring Cloud Stream to select destination, group, binder, and properties |
| **Destination name** | `orders.raw`, `orders.normalized` | Broker address: topic, exchange, queue, or corresponding destination |

A function named `uppercase` can have binding `uppercase-in-0` pointing to topic `orders.raw`, and binding `uppercase-out-0` pointing to topic `orders.normalized`. There is no requirement for the binding name to match the broker destination name.

When configuring:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        uppercase-in-0:
          destination: orders.raw
          group: order-normalizer
        uppercase-out-0:
          destination: orders.normalized
~~~

`uppercase-in-0` and `uppercase-out-0` are binding keys; `orders.raw` and `orders.normalized` are destinations. Keep this distinction clear throughout migration.

## 2. Functional binding naming rules

Spring Cloud Stream uses the default rule:

~~~text
Input  = <functionBeanName>-in-<index>
Output = <functionBeanName>-out-<index>
~~~

Index `0` corresponds to the first input/output. For a typical function with one input and one output, the index is 0 on both ends.

| Function bean type | Bean example | Input binding | Output binding |
|---|---|---|---|
| `Supplier<T>` | `publishOrder` | None | `publishOrder-out-0` |
| `Function<T,R>` | `normalizeOrder` | `normalizeOrder-in-0` | `normalizeOrder-out-0` |
| `Consumer<T>` | `storeOrder` | `storeOrder-in-0` | None |
| `BiFunction<...>` with Kafka Streams | `joinOrders` | `joinOrders-in-0`, `joinOrders-in-1` | `joinOrders-out-0` |

The name used to construct the binding is the **registered bean name**. If the Java method is `transformOrder` but declared as `@Bean("normalizeOrder")`, the binding will be based on `normalizeOrder`. Do not guess from class names, topics, or arbitrary method names.

## 3. How the legacy annotation model uses input/output

In legacy apps, `Processor` represents one input channel and one output channel. The following example uses legacy model annotations; read it only to recognize it during upgrades, **do not use it as new code**:

~~~java
// Legacy Spring Cloud Stream annotation-based programming model.
@EnableBinding(Processor.class)
public class LegacyOrderApplication {

    @StreamListener(Processor.INPUT)
    @SendTo(Processor.OUTPUT)
    public String uppercase(String order) {
        return order.toUpperCase(Locale.ROOT);
    }
}
~~~

Because `Processor.INPUT` and `Processor.OUTPUT` are named `input` and `output` respectively, legacy configuration might look like:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        input:
          destination: orders.raw
          group: order-normalizer
          content-type: text/plain
        output:
          destination: orders.normalized
          content-type: text/plain
~~~

The `@EnableBinding`/`@StreamListener` model has been recommended for replacement with functional programming since Spring Cloud Stream 3.x. When upgrading, clarify the active version and avoid leaving legacy annotation code alongside new functions as two unintended independent consumers.

## 4. Direct migration to functional binding names (recommended)

Replace legacy processing with a `Function` bean:

~~~java
import java.util.Locale;
import java.util.function.Function;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class OrderFunctions {

    @Bean
    Function<String, String> uppercase() {
        return order -> order.toUpperCase(Locale.ROOT);
    }
}
~~~

Explicitly declare the function definition and rename keys `input`/`output` to `uppercase-in-0`/`uppercase-out-0`:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase
    stream:
      bindings:
        uppercase-in-0:
          destination: orders.raw
          group: order-normalizer
          content-type: text/plain
        uppercase-out-0:
          destination: orders.normalized
          content-type: text/plain
~~~

**Result:** the binding names change, while destinations `orders.raw`, `orders.normalized` and consumer group `order-normalizer` remain intact. The broker continues using the configured topics/queues/exchanges as long as other binder settings are not unintentionally altered.

In the functional model, if an application has only a single discovered `Supplier`/`Function`/`Consumer` bean, `spring.cloud.function.definition` may not be strictly required. However, declare it explicitly during upgrades, especially in case more functions are added later.

## 5. Step-by-step migration: keeping input/output names via aliases

If you have many environment-specific config files, dashboards, or scripts referencing `bindings.input` and `bindings.output`, you can keep those names during the transition phase by mapping **implicit binding name → explicit binding name**:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase
    stream:
      function:
        bindings:
          uppercase-in-0: input
          uppercase-out-0: output
      bindings:
        input:
          destination: orders.raw
          group: order-normalizer
          content-type: text/plain
        output:
          destination: orders.normalized
          content-type: text/plain
~~~

The property used is:

~~~text
spring.cloud.stream.function.bindings.<implicitBindingName>=<explicitBindingName>
~~~

In this example, `uppercase-in-0` is effectively renamed to `input`; `uppercase-out-0` is effectively renamed to `output`. **After aliasing, all binding properties must reference the effective names** `input`/`output`. Do not configure `spring.cloud.stream.bindings.uppercase-in-0.destination` while also expecting the framework to merge it with `spring.cloud.stream.bindings.input.destination`.

This migration path is supported by Spring Cloud Stream documentation, though it adds an extra mapping layer to maintain. For new applications or once stabilized, using default function-based binding names is usually easier to trace and less error-prone.

## 6. Two migration options: pros and cons

| Criterion | Rename directly to functional names | Alias to keep legacy names |
|---|---|---|
| Primary config key | `bindings.uppercase-in-0` | `bindings.input` |
| Requires `function.bindings`? | No | Yes |
| Reading logs and Actuator | Easy to correlate with function | Must look up alias mapping |
| Changes to existing config files | More | Fewer |
| Best suited for | Sustainable upgrade target | Transition phase, systems with many dependent configs |
| Main risk | Missing an old property key | Mixing up implicit names and alias names |

Do not mix both strategies for **the same binding**. Pick one approach, build a mapping table, and verify at runtime. If aliasing is only temporary, document the planned date to remove the alias and migrate all configuration to functional names.

## 7. Conversion table for Source, Sink, Processor

Legacy interfaces have different port counts; not all types have both `input` and `output`.

| Legacy interface | Legacy name | Replacement functional bean | Example new binding name |
|---|---|---|---|
| `Source` | `output` | `Supplier<OrderEvent> publishOrder` | `publishOrder-out-0` |
| `Sink` | `input` | `Consumer<OrderEvent> saveOrder` | `saveOrder-in-0` |
| `Processor` | `input`, `output` | `Function<OrderEvent,OrderEvent> normalizeOrder` | `normalizeOrder-in-0`, `normalizeOrder-out-0` |
| Custom `@Input("ordersIn")` | `ordersIn` | `Consumer<OrderEvent> processOrder` | `processOrder-in-0` |
| Custom `@Output("alertsOut")` | `alertsOut` | `Supplier<Alert> publishAlert` | `publishAlert-out-0` |

For `Supplier`, check how polling/scheduling of the producer is structured in the new version; the output name is derived by the `-out-0` rule. For `Consumer`, there is only an input binding—do not create `-out-0` just to keep unused legacy configuration around.

If legacy code used custom interfaces with arbitrary names, alias mappings can point to those names as well:

~~~yaml
spring:
  cloud:
    stream:
      function:
        bindings:
          processOrder-in-0: ordersIn
          publishAlert-out-0: alertsOut
~~~

Only configure `bindings.ordersIn` and `bindings.alertsOut` if you chose the alias strategy.

## 8. Migrating all configuration, not just destination

Configuration fields to inspect when renaming include:

| Config group | Before migration | After migration (direct) |
|---|---|---|
| Destination | `bindings.input.destination` | `bindings.uppercase-in-0.destination` |
| Group | `bindings.input.group` | `bindings.uppercase-in-0.group` |
| Content type | `bindings.output.content-type` | `bindings.uppercase-out-0.content-type` |
| Consumer concurrency | `bindings.input.consumer.concurrency` | `bindings.uppercase-in-0.consumer.concurrency` |
| Retry | `bindings.input.consumer.max-attempts` | `bindings.uppercase-in-0.consumer.max-attempts` |
| Partition key | `bindings.output.producer.partition-key-expression` | `bindings.uppercase-out-0.producer.partition-key-expression` |
| Binder instance | `bindings.input.binder` | `bindings.uppercase-in-0.binder` |
| Kafka consumer extension | `kafka.bindings.input.consumer.*` | `kafka.bindings.uppercase-in-0.consumer.*` |
| Rabbit producer extension | `rabbit.bindings.output.producer.*` | `rabbit.bindings.uppercase-out-0.producer.*` |

The prefixes in the table live under `spring.cloud.stream`. When using aliases, the "After migration" column continues to use the alias names `input`/`output`, **even for binder-specific extended properties**.

Example migrating some Kafka binding-specific properties:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase
    stream:
      bindings:
        uppercase-in-0:
          destination: orders.raw
          group: order-normalizer
          binder: kafka
          consumer:
            concurrency: 3
            max-attempts: 4
        uppercase-out-0:
          destination: orders.normalized
          binder: kafka
      kafka:
        bindings:
          uppercase-in-0:
            consumer:
              enable-dlq: true
          uppercase-out-0:
            producer:
              sync: false
~~~

`destination`, `group`, `binder`, and extended properties must preserve their business values unless the upgrade intentionally changes semantics. Verify that each property is supported in the target binder version; upgrading library versions may introduce changes beyond renaming.

## 9. Multi-environment example: alias vs. direct

Suppose the same application deploys to staging and production using configuration merged from multiple sources. A common mistake is updating common configuration to the new names while the production file still overrides the old name:

~~~yaml
# application.yml, migrated to new names
spring:
  cloud:
    stream:
      bindings:
        uppercase-in-0:
          destination: orders.raw
          group: order-normalizer
~~~

~~~yaml
# application-prod.yml, still using legacy key; NOT automatically applied to uppercase-in-0
spring:
  cloud:
    stream:
      bindings:
        input:
          destination: orders.raw.prod
~~~

Without an alias, `bindings.input.destination` does not configure `uppercase-in-0`. As a result, runtime may read the wrong topic, create a different destination, or ignore the expected production value.

Roadmap:

1. List all `application*.yml` files, environment variables, Helm charts, Config Server entries, and command-line arguments containing `bindings.input` or `bindings.output`.
2. Choose one approach: convert everything to `uppercase-...` or alias everything to the legacy names.
3. Inspect the configuration after Spring Boot merges profiles and property sources, especially in production.
4. Run broker connectivity tests and verify actual topics/groups before cutover.

The example above only illustrates a configuration mismatch; do not use two conflicting snippets in a single deployment.

## 10. Multiple functions in one application

When two function beans exist, explicitly select which functions must be bound. Using `;` in `spring.cloud.function.definition` declares multiple independent functions:

~~~java
@Bean
Function<String, String> uppercase() {
    return String::toUpperCase;
}

@Bean
Function<String, String> reverse() {
    return value -> new StringBuilder(value).reverse().toString();
}
~~~

~~~yaml
spring:
  cloud:
    function:
      definition: "uppercase;reverse"
    stream:
      bindings:
        uppercase-in-0:
          destination: uppercase.request
        uppercase-out-0:
          destination: uppercase.response
        reverse-in-0:
          destination: reverse.request
        reverse-out-0:
          destination: reverse.response
~~~

These are **two independent pipelines**. Do not map both functions to the same `input`/`output` aliases if they need distinct broker destinations. Each binding needs a unique effective name, or separate traceable aliases.

If you only declare `spring.cloud.function.definition: uppercase`, the `reverse` function will not automatically create its own binding pair under this configuration. Do not treat the mere existence of a Java bean as meaning it is selected for binding.

## 11. Function composition also affects binding names

If you want two functions to run sequentially as one pipeline, use `|` instead of `;`:

~~~yaml
spring:
  cloud:
    function:
      definition: "uppercase|reverse"
~~~

`uppercase;reverse` creates two independent flows, whereas `uppercase|reverse` creates a composed function whose output from `uppercase` passes into `reverse`.

The binding name is derived from the composed function name. With the **Kafka Streams Binder**, documentation gives the example `foo|bar` having default binding names `foobar-in-0` and `foobar-out-0`. Older Spring Cloud Function examples may show different composed names depending on version and declaration style. Therefore, when switching to composition, check the actual binding names in logs/Actuator before migrating all configuration.

Do not assume `uppercase-in-0` and `reverse-out-0` will be the outermost binding names after composition. If you need a stable name, alias the binding of the **actual composed function** or wrap the composition in a clearly named bean, depending on the binder and topology requirements.

## 12. Multiple inputs/outputs in Kafka Streams

With the Kafka Streams Binder, a function can have multiple inputs and/or outputs. Example:

~~~java
@Bean
BiFunction<KStream<String, OrderEvent>,
           KTable<String, Customer>,
           KStream<String, EnrichedOrder>> joinOrders() {
    return (orders, customers) ->
        orders.leftJoin(customers,
            (order, customer) -> new EnrichedOrder(order, customer));
}
~~~

Indexed binding configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: joinOrders
    stream:
      bindings:
        joinOrders-in-0:
          destination: orders.events
        joinOrders-in-1:
          destination: customers.table
        joinOrders-out-0:
          destination: orders.enriched
~~~

If the legacy interface had `ordersInput` and `customersInput`, verify accurately which input corresponds to `-in-0` and `-in-1`. Swapping the order makes the processor read the wrong stream/table, potentially causing deserialization errors or broken joins.

Aliases can be used when readable names are desired:

~~~yaml
spring:
  cloud:
    stream:
      function:
        bindings:
          joinOrders-in-0: ordersInput
          joinOrders-in-1: customersInput
          joinOrders-out-0: enrichedOutput
      bindings:
        ordersInput:
          destination: orders.events
        customersInput:
          destination: customers.table
        enrichedOutput:
          destination: orders.enriched
~~~

Clearly document the mapping between function parameters, binding indices, and destinations, especially in Kafka Streams where KTable and KStream have different semantics.

## 13. `StreamBridge` output is not necessarily a function output

Some legacy code called `MessageChannel` or `Source.OUTPUT` directly to publish messages from an HTTP endpoint, scheduler, or service with no input stream. In the current model, `StreamBridge` can be used:

~~~java
@RestController
class OrderPublisher {
    private final StreamBridge streamBridge;

    OrderPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    @PostMapping("/orders")
    void publish(@RequestBody OrderEvent event) {
        streamBridge.send("ordersOutput", event);
    }
}
~~~

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: ordersOutput
      bindings:
        ordersOutput:
          destination: orders.events
~~~

`spring.cloud.stream.output-bindings` proactively creates an output binding not attached to a `Supplier`/`Function`, commonly used with `StreamBridge`. It is **different** from `spring.cloud.stream.function.bindings`: the former creates explicit bindings, while the latter renames implicit bindings of a function. Do not mechanically rename every `output` to `<someFunction>-out-0` if the publish path is no longer driven by a function.

## 14. Standardizing binder configuration during upgrades

A `SPRING_CLOUD_STREAM` project may use Kafka, RabbitMQ, or Pulsar, or even multiple binders simultaneously. Binding names are derived from functions, but **binder-specific properties still reside under their respective binder branches**:

~~~text
spring.cloud.stream.bindings.<bindingName>...
spring.cloud.stream.kafka.bindings.<bindingName>...
spring.cloud.stream.rabbit.bindings.<bindingName>...
spring.cloud.stream.pulsar.bindings.<bindingName>...
~~~

When switching from `input` to `normalizeOrder-in-0`, also locate all extended configuration branches. For instance, a Kafka DLQ setting still under `kafka.bindings.input.consumer.enable-dlq` will not automatically apply to `normalizeOrder-in-0` under the direct-rename strategy.

For multi-binder applications, keep intact:

- `bindings.<name>.binder`: selected named binder instance.
- `bindings.<name>.destination`: existing broker destination.
- `bindings.<name>.group`: group used by the application.
- Partition, retry, DLQ, schema, and content-type properties for each binding.
- Kafka Streams `application.id`, state store/changelog configuration, and related topology parameters if upgrading Kafka Streams.

Unintentionally changing the consumer group or Kafka Streams application ID can create a new reader group with different offsets or a fresh set of states. That is a semantic change requiring its own replay/migration plan, not an inevitable consequence of renaming bindings.

## 15. Does migration change topics or consumer offsets?

**Changing only the logical binding name** while keeping `destination`, `group`, binder configuration, serializers/deserializers, and processing properties **does not inherently create new topics or reset consumer offsets**.

Conversely, if the new configuration omits `destination`, Spring Cloud Stream may use the binding name as the default destination. For the `uppercase` function, `uppercase-in-0` will not automatically read from `orders.raw` if the old destination value was not carried over. The broker/binder may provision a new destination according to provisioning policies, causing the app to run without receiving messages from the old topic.

If `group` is changed, consumer group and offset semantics can change. In RabbitMQ, changing the group usually changes the created/managed queue name. In Kafka, a new group has its own offsets; where reading starts depends on auto-offset-reset settings and topic state.

Do not declare migration successful just because the application starts. Verify topics, queues, groups, and actual message flow.

## 16. Step-by-step safe migration plan

1. **Inventory:** tabulate every legacy binding, direction, destination, group, binder, content type, consumer/producer options, and target environment.
2. **Choose functional beans:** convert `@StreamListener` or channel handler logic into the corresponding `Supplier`/`Function`/`Consumer`.
3. **Decide naming:** use implicit function-based names or aliases for a transition phase; record a 1:1 mapping.
4. **Migrate configuration:** move all `bindings.*` and binder-specific `kafka/rabbit/pulsar.bindings.*`; preserve destinations and groups.
5. **Select function definitions:** use `spring.cloud.function.definition` to control which functions are bound.
6. **Check startup:** confirm actual bindings via logs and, if available, the Actuator `/actuator/bindings` endpoint.
7. **Test message flow:** send events to the old destination, verify the new function processes them, and check output arrives at the old destination.
8. **Test failure paths:** retry, DLQ, error channels, acknowledgements, partition keys, consumer lag, and offsets across restarts.
9. **Cutover:** deploy using an appropriate rolling/blue-green strategy, avoiding running two pipelines concurrently writing non-idempotent results.
10. **Clean up legacy code:** once verified, remove old annotations/interfaces/channels and unused keys; document the migration mapping.

Sample inventory template:

| Legacy binding | New functional binding | Preserved destination | Preserved group | Binder |
|---|---|---|---|---|
| `input` | `uppercase-in-0` | `orders.raw` | `order-normalizer` | Kafka |
| `output` | `uppercase-out-0` | `orders.normalized` | Not applicable | Kafka |
| `ordersIn` | `processOrders-in-0` | `orders.pending` | `fulfillment` | RabbitMQ |
| `alertsOut` | `publishAlert-out-0` | `alerts.events` | Not applicable | Pulsar |

## 17. Quick testing with Spring Cloud Stream Test Binder

Test Binder lets you test application functions and bindings inside the JVM without a real broker. Example using `InputDestination` and `OutputDestination` with the **direct-rename** configuration:

~~~java
@SpringBootTest(
    classes = UppercaseBindingMigrationTest.TestApplication.class,
    properties = {
    "spring.cloud.function.definition=uppercase",
    "spring.cloud.stream.bindings.uppercase-in-0.destination=orders.raw",
    "spring.cloud.stream.bindings.uppercase-out-0.destination=orders.normalized"
})
@EnableTestBinder
class UppercaseBindingMigrationTest {

    @Autowired InputDestination input;
    @Autowired OutputDestination output;

    @Test
    void stillUsesOriginalDestinations() {
        input.send(
            new GenericMessage<>("abC".getBytes(StandardCharsets.UTF_8)),
            "orders.raw"
        );

        Message<byte[]> actual =
            output.receive(1_000, "orders.normalized");

        assertThat(actual).isNotNull();
        assertThat(new String(actual.getPayload(), StandardCharsets.UTF_8))
            .isEqualTo("ABC");
    }

    @SpringBootApplication
    static class TestApplication {
        @Bean
        Function<String, String> uppercase() {
            return value -> value.toUpperCase(Locale.ROOT);
        }
    }
}
~~~

This is a focused test example; it requires `spring-cloud-stream-test-binder`, Spring Boot Test, JUnit, and AssertJ dependencies matching the project version. In multi-function tests, specify the destination on every `send` and `receive` call to avoid reading the wrong output.

Test Binder verifies wiring and logic in the JVM; it **does not prove** that consumer groups, Kafka offsets/partitions, Rabbit queue bindings, Pulsar subscriptions, retry/DLQ, or broker metadata are preserved properly. Those require integration tests with real Kafka/RabbitMQ/Pulsar.

## 18. Verification with Actuator and broker

If Spring Boot Actuator is present and the `bindings` endpoint is exposed according to governance policy:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: bindings
~~~

List bindings:

~~~bash
curl http://localhost:8080/actuator/bindings
~~~

In the direct-rename approach, check for bindings named `uppercase-in-0` and `uppercase-out-0`. In the alias approach, the effective names used in configuration are `input` and `output`; match the response format to your running version.

Then inspect the broker:

- Kafka: are topic names right, is group ID right, and are partition assignments, offsets, and consumer lag normal?
- RabbitMQ: are exchanges/queues/routing keys right, was any unintended group queue created, and are ready/unacked counts growing abnormally?
- Pulsar: are topics, subscription names/types, and schemas preserved as before?
- Multi-binder: is each input/output connected to the right named binder instance and broker environment?

Management endpoints should not be exposed publicly; protect them with authentication/authorization and internal networking.

## 19. Common migration errors

| Symptom | Possible cause | How to check/fix |
|---|---|---|
| App runs but consumes no messages | Did not migrate `bindings.input.destination` to `uppercase-in-0.destination` | Inspect effective binding destination and topic/queue |
| New topic or queue appears | Missing destination; binder falls back to binding name | Set `destination` explicitly, check auto-provisioning |
| Group/offset changes after deploy | Omitted `group` or changed application ID | Keep existing group/app ID to preserve progress |
| Retry/DLQ stops working | Extended properties still under `kafka.bindings.input` | Move all binder-specific config to effective names |
| Output goes to wrong broker | Forgot `binder` or named binder configuration | Cross-check binder name and broker endpoint |
| Only one of several functions is bound | Missing name in `spring.cloud.function.definition` | Declare `"foo;bar"` for independent functions |
| Two functions share alias `input` | Duplicate alias, ambiguous configuration | Assign distinct aliases or switch to implicit names |
| Composition reads wrong destination | Changed `foo;bar` to `foo|bar` while keeping old binding config | Re-check outermost binding names of composed function |
| Schema errors after upgrade | Function signature or conversion changed | Check content-type, serde/schema registry, and headers |
| Test Binder passes but production fails | Test Binder lacks broker metadata, groups, offsets, DLQ | Add integration tests against a real broker |
| `StreamBridge` sends to wrong topic | Called `send` with wrong binding name/destination | Use explicit output bindings and clear mapping |
| Environment configs behave differently | Profiles/Config Server still use `input/output` keys | Audit all property sources, inspect runtime merged config |

## 20. Migration practice exercise

Given a legacy application using:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        input:
          destination: payments.created
          group: payment-audit
          consumer:
            max-attempts: 3
        output:
          destination: payments.checked
~~~

Requirement: move business logic to the bean:

~~~java
@Bean
Function<PaymentCreated, PaymentChecked> verifyPayment() {
    return event -> new PaymentChecked(
        event.paymentId(),
        event.amount() > 0
    );
}
~~~

Implement two configuration variants:

1. **Variant A:** no aliases; replace `input` with `verifyPayment-in-0` and `output` with `verifyPayment-out-0`. Preserve destination, group, and retry.
2. **Variant B:** set `function.bindings.verifyPayment-in-0=input` and `function.bindings.verifyPayment-out-0=output`, keeping the old binding configuration.
3. Check at startup that only one functional binding pair and the two expected destinations appear.
4. Send a valid message; verify output arrives at `payments.checked`.
5. Send an invalid message; verify retry/error semantics still match previous requirements.
6. Check that the Kafka consumer group or Rabbit queue for the group remains unchanged when using those respective binders.

An exercise passes when **broker behavior is unchanged aside from intentional changes**, bindings carry names matching the chosen strategy, and every critical property is applied at runtime.

## 21. Pre-release checklist

- [ ] Inventoried all legacy `input`, `output`, and custom `@Input`/`@Output`.
- [ ] Confirmed exact function beans and `-in-N`/`-out-N` names.
- [ ] Clearly chose either direct renaming or aliasing; never mixed names for the same binding.
- [ ] Configured `spring.cloud.function.definition` matching the number of functions and composition.
- [ ] Preserved destinations, groups, named binders, and connection environments.
- [ ] Migrated both `bindings.*` and `kafka/rabbit/pulsar.bindings.*` branches.
- [ ] Verified content types, serializers/deserializers, schemas, headers, and partition keys.
- [ ] Verified retry, DLQ, ack, and idempotency across application restarts.
- [ ] If using Kafka Streams, re-verified input/output indices and preserved application ID/state semantics.
- [ ] Audited configuration across all profiles, environment variables, and Helm/Config Server.
- [ ] Tested functions with Test Binder and ran integration tests against a real broker.
- [ ] Verified runtime bindings and destinations via Actuator/logs/broker.
- [ ] Prepared a cutover/rollback plan and prevented non-idempotent duplicate processing.
- [ ] Removed unused legacy annotations/interfaces/config once verified.

**Closing principle:** `input` and `output` are logical binding names from the legacy model; in the functional model, Spring Cloud Stream derives default names from beans such as `verifyPayment-in-0`/`verifyPayment-out-0`. Migrating all configuration keys to the new names is the most maintainable destination. When minimizing changes during an upgrade phase, `spring.cloud.stream.function.bindings` can preserve legacy aliases. Either way, verify that **destination, group, binder, and delivery semantics** remain intact before deploying to production.

## References

- [Spring Cloud Stream — Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Stream — Binding and Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-names.html)
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Explicit Binding Creation](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/explicit-binding-creation.html)
- [Spring Cloud Stream — Kafka Binder Tips: Override Default Binding Names](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka_tips.html)
- [Spring Cloud Stream — Kafka Streams Binder Programming Model](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/programming-model.html)
