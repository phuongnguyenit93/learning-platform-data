# Setting Up spring-cloud-stream-test-binder and @EnableTestBinder

Spring Cloud Stream provides the **Test Binder** to test functions and bindings in the JVM without running Kafka, RabbitMQ, or Pulsar. The Test Binder is built on Spring Integration, providing an in-memory message broker environment so tests can send messages to input bindings and receive messages from output bindings.

To use it, add the `spring-cloud-stream-test-binder` dependency with `test` scope, then enable the testing infrastructure using the `@EnableTestBinder` annotation on the Spring configuration used in tests. Spring provides `InputDestination` and `OutputDestination` to send and receive messages. This approach is well-suited for testing processing logic, function and destination mappings, payloads, headers, and basic message flows of the `SPRING_CLOUD_STREAM` module.

The Test Binder is an in-process emulated broker. It helps test the application and Spring Cloud Stream bindings, but it does not replace integration testing with a real broker when you need to verify protocols, authentication, partitions, consumer groups, transactions, retries, or DLQs specific to Kafka, RabbitMQ, or Pulsar.

## 1. Where Does the Test Binder Fit in the Spring Cloud Stream Model?

A Spring Cloud Stream application implements business processing with `Supplier`, `Function`, or `Consumer`. The binder connects input/output bindings to a messaging system. In production, the corresponding binder might connect to Kafka, RabbitMQ, or Pulsar. In tests, the Test Binder replaces the external broker with in-JVM message channels.

```text
Production:

Kafka / RabbitMQ / Pulsar
          |
          v
     Real Binder
          |
          v
Input binding -> Function/Consumer -> Output binding

Test:

InputDestination
      |
      v
Spring Integration Test Binder (in-JVM)
      |
      v
Input binding -> Function/Consumer -> Output binding
                                      |
                                      v
                               OutputDestination
```

The Test Binder preserves how the application declares functions and bindings. A test can send a message to an input, let the function process it, and receive the message at the output. No broker installation or open network ports are needed to run these tests.

## 2. Adding the `spring-cloud-stream-test-binder` Dependency

The dependency must be placed in a test-specific configuration so it is not packaged into the application's runtime artifact.

### Maven

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
</dependency>
```

### Gradle Kotlin DSL

```kotlin
dependencies {
    testImplementation("org.springframework.cloud:spring-cloud-stream-test-binder")
}
```

### Gradle Groovy DSL

```groovy
dependencies {
    testImplementation 'org.springframework.cloud:spring-cloud-stream-test-binder'
}
```

Do not manually specify a version on the dependency if the project already uses the Spring Cloud BOM or corresponding dependency management. The BOM manages the Spring Cloud Stream version consistently with Spring Boot and the Spring Cloud release train. If not using a BOM, select a test binder version compatible with the `spring-cloud-stream` version in your project.

Tests also require test frameworks such as JUnit Jupiter and Spring Boot Test. In a Spring Boot project, the typical dependencies are:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-stream-test-binder'
}
```

`spring-boot-starter-test` provides Spring/JUnit/AssertJ/Mockito testing components managed by your project's dependency management. There is no need to add a Kafka broker, RabbitMQ broker, or Pulsar broker just to run a test using the Test Binder.

## 3. Role of `@EnableTestBinder`

`@EnableTestBinder` enables Test Binder configuration in the Spring ApplicationContext. When this configuration is loaded, Spring Cloud Stream can create bindings using the Test Binder and provide testing beans such as:

- `InputDestination`: sends messages to an input binding.
- `OutputDestination`: receives messages emitted from an output binding.

The annotation is typically placed on the application configuration used in tests. It can be placed on a test configuration or an application configuration loaded by `@SpringBootTest`.

Example:

```java
import java.util.function.Function;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.stream.binder.test.EnableTestBinder;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTestBinder
class StreamTestApplication {

    @Bean
    Function<String, String> uppercase() {
        return value -> value.toUpperCase();
    }
}
```

In this example, `@EnableTestBinder` activates the Test Binder for the context, and the `uppercase` function is registered as a normal bean. When the test sends a message to the input binding, the function is invoked and the result is held by the Test Binder at the output destination.

Do not place the annotation on a class that is not loaded into the ApplicationContext and expect the Test Binder to work automatically. Confirm that the annotated configuration is actually part of the context initialized by the test.

## 4. Initializing Tests with `@SpringBootTest`

`@SpringBootTest` creates an ApplicationContext close to how the Spring Boot application starts up. Explicitly specifying the configuration class ensures the test uses the right function and Test Binder.

Complete example:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.EnableTestBinder;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;

import java.util.function.Function;

@SpringBootTest(classes = StreamTestApplication.class)
class StreamBinderTests {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void transformsInputMessage() {
        input.send("hello".getBytes(StandardCharsets.UTF_8));

        Message<byte[]> result = output.receive(1_000L);

        assertThat(result).isNotNull();
        assertThat(new String(result.getPayload(), StandardCharsets.UTF_8))
            .isEqualTo("HELLO");
    }

    @SpringBootApplication
    @EnableTestBinder
    static class StreamTestApplication {

        @Bean
        Function<String, String> uppercase() {
            return value -> value.toUpperCase();
        }
    }
}
```

Steps that occur:

1. `@SpringBootTest` initializes the context using `StreamTestApplication`.
2. `@EnableTestBinder` enables the Test Binder in that context.
3. Spring Cloud Stream discovers the `uppercase` function bean and creates the corresponding input/output bindings.
4. The test sends bytes to `InputDestination`.
5. The Test Binder delivers the message to the function.
6. The function converts the string to uppercase.
7. The Test Binder retains the output message for `OutputDestination` to receive.
8. The test verifies the received payload.

The example uses `receive(1_000L)` to wait up to about one second. If no message arrives within that duration, the result may be `null`; therefore, assert `isNotNull()` before reading the payload to produce clearer test failure messages.

## 5. Default Binding Names of the Functional Model

Spring Cloud Stream generates binding names from the function bean name and input/output index:

| Function bean | Binding | Role |
|---|---|---|
| `uppercase` | `uppercase-in-0` | First input |
| `uppercase` | `uppercase-out-0` | First output |
| `enrichOrder` | `enrichOrder-in-0` | First parameter |
| `enrichOrder` | `enrichOrder-in-1` | Second parameter |
| `publishOrder` | `publishOrder-out-0` | Output of Supplier |
| `consumeOrder` | `consumeOrder-in-0` | Input of Consumer |

The Test Binder uses these bindings to route messages. If the application has one input and one output, you can call `input.send(message)` and `output.receive()` without specifying a name. When there are multiple functions or multiple bindings, specify the destination explicitly to avoid sending to the wrong stream.

## 6. Selecting Functions with `spring.cloud.function.definition`

If the application has multiple `Supplier`, `Function`, or `Consumer` beans, declare the function(s) under test using `spring.cloud.function.definition`.

Example:

```java
@SpringBootApplication
@EnableTestBinder
class MultiFunctionTestApplication {

    @Bean
    Function<String, String> uppercase() {
        return value -> value.toUpperCase();
    }

    @Bean
    Function<String, String> reverse() {
        return value -> new StringBuilder(value).reverse().toString();
    }
}
```

Test context:

```java
@SpringBootTest(
    classes = MultiFunctionTestApplication.class,
    properties = "spring.cloud.function.definition=uppercase;reverse"
)
class MultiFunctionBinderTests {
    // inject InputDestination and OutputDestination
}
```

When selecting multiple functions, Spring Cloud Function lets you declare a list of functions using definition syntax. If defining a composition, check the binding name generated for that pipeline and use the right destination in your test.

## 7. Sending Messages with `InputDestination`

`InputDestination` is the entry point for messages in tests. Common ways to send messages:

```java
input.send("hello".getBytes(StandardCharsets.UTF_8));
```

Send a Spring `Message` with payload and headers:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

Message<byte[]> message = MessageBuilder
    .withPayload("hello".getBytes(StandardCharsets.UTF_8))
    .setHeader("correlationId", "corr-1001")
    .build();

input.send(message);
```

Send to a specific destination:

```java
input.send(message, "orders.input");
```

The name passed in must match the destination that the binding uses. If `destination` is not declared, the binding name such as `processOrder-in-0` is typically used. If configured as:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.input
```

then the test sends to `orders.input`:

```java
input.send(message, "orders.input");
```

Do not assume the binding name and destination are always the same. When custom mappings exist, use the configured destination name.

## 8. Receiving Messages with `OutputDestination`

`OutputDestination` holds messages emitted from output bindings so tests can verify them.

Receive a message from the default output:

```java
Message<byte[]> result = output.receive(1_000L);
```

Receive from a specific output:

```java
Message<byte[]> result = output.receive(1_000L, "orders.output");
```

If the binding has a destination:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-out-0:
          destination: orders.output
```

then use `orders.output` when receiving messages. With multiple outputs, specify the destination to avoid pulling messages from another output.

The returned payload is typically read as `byte[]`. Convert bytes to the target data type using an explicit charset:

```java
String body = new String(result.getPayload(), StandardCharsets.UTF_8);
assertThat(body).isEqualTo("ORDER-1001");
```

Avoid relying on the machine's default charset, as results can differ across test environments.

## 9. Configuring Custom Destinations in Tests

A function can read from and write to explicitly named topics/destinations:

```yaml
spring:
  cloud:
    function:
      definition: uppercase
    stream:
      bindings:
        uppercase-in-0:
          destination: text.in
        uppercase-out-0:
          destination: text.out
```

Test:

```java
@Test
void usesConfiguredDestinations() {
    Message<byte[]> message = MessageBuilder
        .withPayload("hello".getBytes(StandardCharsets.UTF_8))
        .build();

    input.send(message, "text.in");

    Message<byte[]> result = output.receive(1_000L, "text.out");

    assertThat(result).isNotNull();
    assertThat(new String(result.getPayload(), StandardCharsets.UTF_8))
        .isEqualTo("HELLO");
}
```

This technique is useful when production destination names do not match default binding names or when testing multiple functions in the same context.

## 10. Testing Multiple Functions in the Same Test Suite

When testing multiple functions, each function has its own input and output. Send and receive using the corresponding destinations.

```java
@Test
void testsTwoFunctions() {
    Message<byte[]> message = MessageBuilder
        .withPayload("Hello".getBytes(StandardCharsets.UTF_8))
        .build();

    input.send(message, "uppercase-in-0");
    input.send(message, "reverse-in-0");

    Message<byte[]> upper = output.receive(1_000L, "uppercase-out-0");
    Message<byte[]> reversed = output.receive(1_000L, "reverse-out-0");

    assertThat(new String(upper.getPayload(), StandardCharsets.UTF_8))
        .isEqualTo("HELLO");
    assertThat(new String(reversed.getPayload(), StandardCharsets.UTF_8))
        .isEqualTo("olleH");
}
```

If functions are mapped to custom destinations, replace the binding names with the configured destinations. Do not rely on message ordering in a shared output if the real application has multiple independent streams.

## 11. Checking Payloads and Headers

The Test Binder lets you verify both message payloads and headers. This is helpful for correlation IDs, event types, content types, or business metadata.

Example of a function receiving `Message<String>` and preserving a correlation header:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Bean
Function<Message<String>, Message<String>> annotateOrder() {
    return message -> MessageBuilder
        .withPayload(message.getPayload().toUpperCase())
        .copyHeaders(message.getHeaders())
        .setHeader("processed", true)
        .build();
}
```

Test:

```java
Message<String> inputMessage = MessageBuilder
    .withPayload("order-created")
    .setHeader("correlationId", "corr-2001")
    .build();

input.send(inputMessage);

Message<byte[]> result = output.receive(1_000L);

assertThat(result).isNotNull();
assertThat(result.getHeaders().get("correlationId"))
    .isEqualTo("corr-2001");
assertThat(result.getHeaders().get("processed"))
    .isEqualTo(true);
```

When testing headers with specific types or contents, verify the actual headers after message conversion. Do not assume all framework-internal headers are preserved identically across every binder.

## 12. Testing a Consumer Without Output

`Consumer<T>` receives messages without returning an output binding. Tests can verify business side effects through a collaborator bean or test state.

Example:

```java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.Consumer;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.stream.binder.test.EnableTestBinder;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTestBinder
class OrderConsumerTestApplication {

    @Bean
    OrderRecorder orderRecorder() {
        return new OrderRecorder();
    }

    @Bean
    Consumer<String> recordOrder(OrderRecorder recorder) {
        return recorder::record;
    }
}

class OrderRecorder {
    private final List<String> orders = new CopyOnWriteArrayList<>();

    void record(String orderId) {
        orders.add(orderId);
    }

    List<String> orders() {
        return List.copyOf(orders);
    }
}
```

The test sends a message to `recordOrder-in-0`, then verifies that `OrderRecorder` recorded the data. For asynchronous processing, use a timeout-based waiting mechanism rather than calling `Thread.sleep` with a fixed duration.

Since a Consumer has no output, `OutputDestination` is not the place to verify business outcomes. Check collaborators, mock repositories, downstream emitted events, or updated state instead.

## 13. Testing a Message-Emitting Supplier

`Supplier<T>` generates data and sends it to an output binding. You can use `OutputDestination` to receive messages emitted by the supplier.

Example supplier:

```java
@Bean
Supplier<String> publishHeartbeat() {
    return () -> "heartbeat";
}
```

Suppliers are typically triggered via the framework's polling mechanism. In tests, control when messages are emitted or configure the poller so the test remains stable. Do not assume a message is already available right as the ApplicationContext finishes starting.

For tests verifying supplier output, wait with a timeout:

```java
Message<byte[]> result = output.receive(2_000L, "publishHeartbeat-out-0");
assertThat(result).isNotNull();
```

If the supplier generates time-dependent data or has side effects, extract the data-generation logic into a collaborator controllable in tests. This prevents tests from depending on poller schedules or wall-clock time.

## 14. Test Binder and `StreamBridge`

Applications can send messages dynamically via `StreamBridge` instead of relying solely on a function bean's output. When the Test Binder is enabled, output destinations can still receive messages sent through a binding name or configured destination.

Example:

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.cloud.stream.function.StreamBridge;

@Bean
ApplicationRunner publishEvent(StreamBridge streamBridge) {
    return args -> streamBridge.send("orders-out-0", "order-created");
}
```

In the test, receive the message from the corresponding destination:

```java
Message<byte[]> result = output.receive(1_000L, "orders-out-0");
assertThat(result).isNotNull();
```

If using `StreamBridge.send` with a binding name mapped to a destination, use the mapped destination when receiving. For dynamic sending code, check both the return value of `send` and the received message contents.

## 15. `@EnableTestBinder` and Manual Context Creation

Most Spring Boot tests only need `@SpringBootTest` with `@EnableTestBinder`. When you need to create multiple independent contexts or pass different properties per test, you can start the context manually using `SpringApplicationBuilder` and the Test Binder configuration.

Example function configuration:

```java
@EnableAutoConfiguration
class UppercaseTestConfiguration {

    @Bean
    Function<String, String> uppercase() {
        return value -> value.toUpperCase();
    }
}
```

Initialize the context with the complete Test Binder configuration:

```java
try (ConfigurableApplicationContext context = new SpringApplicationBuilder(
        TestChannelBinderConfiguration.getCompleteConfiguration(
            UppercaseTestConfiguration.class))
        .run("--spring.cloud.function.definition=uppercase")) {

    InputDestination input = context.getBean(InputDestination.class);
    OutputDestination output = context.getBean(OutputDestination.class);

    input.send("hello".getBytes(StandardCharsets.UTF_8));
    Message<byte[]> result = output.receive(1_000L);

    assertThat(result).isNotNull();
}
```

This is a lower-level way to control the context. When using `@EnableTestBinder` in standard Spring Boot tests, do not call `TestChannelBinderConfiguration.getCompleteConfiguration` again manually. Choose one context initialization approach to avoid registering duplicate test binder configurations.

## 16. Distinguishing the Current Test Binder from Legacy Test Support

Older versions of Spring Cloud Stream provided `spring-cloud-stream-test-support` and `TestSupportBinder`, often tested with `MessageCollector` and legacy channel types. The current Test Binder uses the dependency:

```text
org.springframework.cloud:spring-cloud-stream-test-binder
```

and the APIs `@EnableTestBinder`, `InputDestination`, and `OutputDestination`.

| Component | Current Test Binder | Legacy Test Support |
|---|---|---|
| Dependency | `spring-cloud-stream-test-binder` | `spring-cloud-stream-test-support` |
| Activation | `@EnableTestBinder` or corresponding version's Test Binder configuration | TestSupportBinder auto-configuration |
| Common testing APIs | `InputDestination`, `OutputDestination` | `MessageCollector`, legacy channel bindings |
| Purpose | Testing the functional model and bindings via in-JVM Test Binder | Supporting tests for the legacy channel/binding model |

Do not mix guidance from both generations in the same test. If the project uses an older Spring Cloud Stream version, consult the documentation for that exact release train before changing dependencies or annotations. When upgrading, migrate tests deliberately to the new API and remove the old dependency once unused.

## 17. Test Binder When Kafka/RabbitMQ/Pulsar Binders Are on the Classpath

A production application may declare a real binder such as Kafka, RabbitMQ, or Pulsar. The Test Binder is added with `test` scope for use in test contexts. Ensure tests initialize the Test Binder per the chosen configuration and do not accidentally connect to a production broker.

When the Test Binder is on a module's test classpath, Spring Cloud Stream prioritizes the Test Binder for bindings in test contexts using that configuration. You cannot expect some tests in the same module to switch automatically to a real binder just by changing profiles while the Test Binder remains on the test classpath. If you need to run integration tests against real Kafka/RabbitMQ/Pulsar, organize them in a separate module or separate build configuration that excludes the Test Binder from that test group's classpath.

If the application has multiple binders on the classpath, understand the binder selection mechanism of your Spring Cloud Stream version. For standard tests, enable `@EnableTestBinder` on the test context and verify in logs/context that the Test Binder is active. If multi-binder setups are complex, split test contexts to avoid ambiguous default configurations.

## 18. The Test Binder Does Not Replace Broker Integration Tests

The Test Binder is very useful for testing message processing in the application, but it does not implement full real-broker behavior.

| Subject | Test Binder | Real Broker Needed to Verify? |
|---|---|---|
| Function receives and transforms payload | Yes | Not required |
| Function/Consumer activated via input binding | Yes | Not required |
| Output binding emits expected payload/headers at framework level | Yes | Not required |
| Basic destination mapping | Yes | Not required |
| Kafka partition assignment and consumer group rebalancing | Does not simulate full Kafka semantics | Yes |
| RabbitMQ exchanges, queues, routing keys, and DLQ | Does not simulate real RabbitMQ topology | Yes |
| Pulsar tenants, namespaces, subscriptions, and partitions | Does not simulate Pulsar administration/broker | Yes |
| TLS, SASL, tokens, ACLs, and network failures | No | Yes, compatible environment |
| Broker-specific transactions and delivery guarantees | Cannot verify fully | Yes |
| Broker retries, redelivery, dead-letter policies | Cannot replace the broker | Yes |

A sound testing strategy combines logic/function tests with the Test Binder and a set of integration tests with the target binder/broker to be deployed. Do not treat passing Test Binder tests as proof that Kafka, RabbitMQ, or Pulsar is configured properly.

## 19. Testing Content Types and Message Conversion

Spring Cloud Stream can convert payloads based on content type and message converter configuration. The Test Binder allows testing conversion behavior at the Spring Cloud Stream layer.

Example JSON configuration:

```yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders.input
          content-type: application/json
        normalizeOrder-out-0:
          destination: orders.output
          content-type: application/json
```

Tests can send JSON bytes and check JSON output. For JSON payloads, verify UTF-8 encoding, field structure, and data types. When you need to test Kafka Streams Serdes or a schema registry, the standard Test Binder does not replace integration tests for the real binder/Serde.

Do not confuse Spring Cloud Stream message conversion with Kafka-layer serializers/deserializers or Pulsar schema encoding. The Test Binder tests the framework layer it runs on, not every serializer used by a production broker.

## 20. Testing Timeouts and Test Stability

Message processing can be synchronous or asynchronous depending on the function, executor, reactive pipeline, and configuration. To keep tests stable:

- Use `receive(timeout)` with a finite timeout.
- Check that the message is not `null` before accessing its payload.
- Avoid waiting indefinitely.
- Do not use long `Thread.sleep` calls to guess when messages appear.
- If a function emits multiple messages, receive the exact expected count and destinations.
- Do not share an ApplicationContext with leftover message state between tests without proper control.
- Specify destination names explicitly when multiple bindings exist.

If output does not appear, inspect the function definition, binding name, destination, whether the Test Binder is enabled in the context, and whether the function was actually activated.

## 21. Common Configuration Errors

| Error | Symptom | Resolution |
|---|---|---|
| Missing test binder dependency | No Test Binder or destination beans cannot be created | Add `spring-cloud-stream-test-binder` with `test` scope |
| Using legacy dependency | Cannot find `@EnableTestBinder` or new destination APIs | Use the dependency matching your Spring Cloud Stream generation |
| Forgot `@EnableTestBinder` | Test context does not activate Test Binder as intended | Place annotation on a configuration actually loaded |
| Test configuration not imported | Function bean missing from context | Specify `classes` properly or import the configuration |
| Function not selected | Bindings not created or function does not run | Set `spring.cloud.function.definition` explicitly |
| Sent to wrong binding/destination | No output or receives messages from another flow | Cross-check binding names and destination mappings |
| Used binding name when destination is mapped | `InputDestination` fails to deliver to intended input | Send using the configured destination name |
| Read from wrong output destination | `receive` returns `null` | Use the output binding's actual destination |
| Missing timeout | Test hangs or fails obscurely | Use `receive(timeout)` with a finite timeout |
| Unintended test execution against real broker | Test tries to connect to Kafka/RabbitMQ/Pulsar | Check test scope and Test Binder activation/context |
| Expecting Test Binder to verify partitions/DLQ | Tests pass yet production broker may still be misconfigured | Write integration tests against a real broker |
| Mixing legacy `TestSupportBinder` and new Test Binder | Incompatible dependencies/APIs or confusing configuration | Pick one test API generation and remove unused dependencies |

## 22. Test Binder Setup Checklist

Before writing tests:

1. Identify compatible Spring Cloud Stream and Spring Boot versions.
2. Ensure dependency management/BOM keeps versions consistent.
3. Add `spring-cloud-stream-test-binder` with `test` scope.
4. Add Spring Boot Test/JUnit if the project does not already include them.
5. Create a test application/configuration containing the function beans to test.
6. Place `@EnableTestBinder` on a configuration loaded into the test context.
7. Use `@SpringBootTest(classes = ...)` or an appropriate manual context creation approach.
8. Select functions via `spring.cloud.function.definition` when multiple functions exist.
9. Inject `InputDestination` and `OutputDestination`.
10. Send messages to the proper input binding/destination.
11. Receive output with a timeout and the proper output destination.
12. Verify payloads, headers, and business outcomes.
13. Keep tests independent of external brokers.
14. Add separate integration tests when verifying Kafka, RabbitMQ, or Pulsar semantics.

## 23. Complete Example: Testing Order Event Processing

The application receives `OrderCreated`, normalizes the order ID, and emits `OrderAccepted`.

```java
import java.util.function.Function;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.stream.binder.test.EnableTestBinder;
import org.springframework.context.annotation.Bean;

record OrderCreated(String eventId, String orderId) {}

record OrderAccepted(String eventId, String orderId, String status) {}

@SpringBootApplication
@EnableTestBinder
class OrderStreamTestApplication {

    @Bean
    Function<OrderCreated, OrderAccepted> acceptOrder() {
        return event -> new OrderAccepted(
            event.eventId(),
            event.orderId().trim().toUpperCase(),
            "ACCEPTED"
        );
    }
}
```

Binding configuration:

```yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.created
          content-type: application/json
        acceptOrder-out-0:
          destination: orders.accepted
          content-type: application/json
```

Test sending a JSON message to `orders.created`, then reading output from `orders.accepted`:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest(classes = OrderStreamTestApplication.class)
class OrderStreamBinderTests {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void acceptsOrderAndPublishesEvent() {
        byte[] json = """
            {"eventId":"evt-1","orderId":" order-100 "}
            """.getBytes(StandardCharsets.UTF_8);

        input.send(MessageBuilder.withPayload(json).build(), "orders.created");

        Message<byte[]> result = output.receive(1_000L, "orders.accepted");

        assertThat(result).isNotNull();
        String body = new String(result.getPayload(), StandardCharsets.UTF_8);
        assertThat(body).contains("ORDER-100");
        assertThat(body).contains("ACCEPTED");
    }
}
```

This example demonstrates combining the dependency, annotation, function bean, destination mapping, and two test destinations. In real projects, confirm that the Jackson/content-type converter is configured accordingly and use your application's DTOs/schemas. If you want to verify JSON structurally, deserialize the result back into a DTO or use JSON assertions instead of substring matching alone.

## 24. Self-Check

- [ ] Can add `spring-cloud-stream-test-binder` with `test` scope.
- [ ] Can explain why compatible dependency management/BOM is needed.
- [ ] Know to place `@EnableTestBinder` on a configuration loaded in the test context.
- [ ] Can explain the roles of `InputDestination` and `OutputDestination`.
- [ ] Can initialize tests using `@SpringBootTest`.
- [ ] Can select functions with `spring.cloud.function.definition`.
- [ ] Can send messages to default bindings and explicitly configured destinations.
- [ ] Can receive messages from outputs using timeouts and proper destinations.
- [ ] Can verify payloads and headers.
- [ ] Know how to test multiple functions and consumers without outputs.
- [ ] Can distinguish the current Test Binder from legacy `spring-cloud-stream-test-support`.
- [ ] Can explain which broker behaviors the Test Binder does not emulate.
- [ ] Can build separate integration tests for Kafka, RabbitMQ, or Pulsar when needed.

## Conclusion

To set up the Spring Cloud Stream Test Binder, add `spring-cloud-stream-test-binder` in `test` scope and enable `@EnableTestBinder` on a configuration loaded by the test context. `InputDestination` sends messages to input bindings; `OutputDestination` receives messages from output bindings. Combining `@SpringBootTest`, `spring.cloud.function.definition`, and destination mapping allows testing functions along the application's actual data flow without an external broker. The Test Binder verifies processing and bindings inside the JVM; broker characteristics such as partitions, consumer groups, exchanges/queues, subscriptions, retries/DLQs, and production delivery guarantees should be additionally tested with real Kafka, RabbitMQ, or Pulsar instances.

## References

- Spring Cloud Stream 5.1 — Testing / Spring Integration Test Binder: https://docs.spring.io/spring-cloud-stream/reference/5.1/spring-cloud-stream/spring_integration_test_binder.html
- Spring Cloud Stream 5.0 — Testing: https://docs.spring.io/spring-cloud-stream/reference/5.0/spring-cloud-stream/spring_integration_test_binder.html
- Spring Cloud Stream — Reference Documentation: https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream.html
