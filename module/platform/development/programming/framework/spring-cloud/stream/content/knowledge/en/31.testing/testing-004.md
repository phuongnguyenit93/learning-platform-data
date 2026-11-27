# Reading and Verifying Results with OutputDestination

When testing a Spring Cloud Stream application, we often need to send a message into an input binding, let a function process it, and verify the message emitted at the output binding. **OutputDestination** is the Spring Cloud Stream test binder API for reading those output messages in tests.

The test binder runs in the JVM and emulates destinations using Spring Integration channels. It lets you test function and binding flows without starting Kafka, RabbitMQ, or Pulsar. A test typically combines three parts:

- **InputDestination:** sends messages into an input destination to trigger a consumer or function.
- **Spring Cloud Stream application:** receives the message, invokes the Supplier/Function/Consumer, and emits output if applicable.
- **OutputDestination:** retrieves messages from an output destination to inspect payloads and headers.

OutputDestination is especially useful when testing functions with outputs, multiple output bindings, or messages sent via StreamBridge. It tests results at the binding boundary rather than just invoking a plain Java method directly.

## 1. The Test Binder and Where OutputDestination Fits

In a real application, the binder connects bindings to Kafka topics, RabbitMQ exchanges/queues, or Pulsar topics. When using the test binder, those connections are replaced by an in-memory broker backed by Spring Integration.

~~~text
                  In-JVM Test
+----------------------------------------------------+
| InputDestination                                   |
|       |                                            |
|       v                                            |
| input binding                                      |
|       |                                            |
|       v                                            |
| Function / Consumer                                |
|       |                                            |
|       v                                            |
| output binding                                     |
|       |                                            |
|       v                                            |
| OutputDestination ---> Message for assertions      |
+----------------------------------------------------+

No connection to Kafka / RabbitMQ / Pulsar required
~~~

OutputDestination receives messages sent by the application through output bindings. Tests can verify:

- Whether a message was emitted.
- Whether the payload has the expected content and data type.
- Whether the message went to the right output destination.
- Whether business headers were created or preserved.
- Whether multiple messages were emitted in the expected count and order within the test's scope.

The test binder does not run a real broker. It does not verify Kafka partitions, RabbitMQ routing, Pulsar subscriptions, broker acknowledgements, binder-specific serialization, or broker retry/DLQ configurations. Those behaviors require separate integration tests with the corresponding binder and broker.

## 2. Adding the Test Binder Dependency

With modern Spring Cloud Stream, use the `spring-cloud-stream-test-binder` dependency in `test` scope.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-test-binder</artifactId>
    <scope>test</scope>
</dependency>
~~~

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    testImplementation("org.springframework.cloud:spring-cloud-stream-test-binder")
}
~~~

Let Spring Cloud BOM dependency management manage the version; avoid pinning a test binder version that differs from the application's Spring Cloud Stream version.

The test binder replaces the middleware binder when loaded in the test context. Therefore, do not put the test binder dependency on the runtime or production classpath. If a test needs to connect to a real broker, configure a separate test setup using the real binder and a test broker.

The examples below use JUnit Jupiter, AssertJ, and Spring Boot Test.

## 3. Enabling the Test Binder with @EnableTestBinder

The test class needs to initialize a Spring application context with the test binder. The common pattern is `@SpringBootTest` combined with `@EnableTestBinder`.

Example application with a function that converts strings to uppercase:

~~~java
import java.util.function.Function;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class TextApplication {

    @Bean
    Function<String, String> uppercase() {
        return value -> value.toUpperCase();
    }
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.EnableTestBinder;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;

@SpringBootTest(classes = TextApplication.class)
@EnableTestBinder
class TextApplicationTests {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void convertsInputAndReadsOutput() {
        input.send(new GenericMessage<>(
            "hello".getBytes(StandardCharsets.UTF_8)
        ));

        Message<byte[]> result = output.receive();

        assertThat(result).isNotNull();
        assertThat(new String(
            result.getPayload(),
            StandardCharsets.UTF_8
        )).isEqualTo("HELLO");
    }
}
~~~

Test flow:

1. Spring starts the application context and discovers the `uppercase` function bean.
2. The test binder creates input/output bindings for the function.
3. InputDestination sends the `hello` payload to the input.
4. Spring Cloud Stream converts the payload to match the function's input type.
5. The function returns `HELLO`.
6. The test binder puts the output message into the output destination queue.
7. OutputDestination retrieves the message for test assertions.

In this example, output is read as `Message<byte[]>`. Decode bytes using an explicit charset like UTF-8 when comparing strings. Do not rely on the test runner's default charset, as results can vary across environments.

## 4. Binding Name vs. Destination Name

A very common source of bugs is confusing binding names with destination names.

For a function named `uppercase`, Spring Cloud Stream creates default bindings:

| Binding | Default Name |
|---|---|
| Input | `uppercase-in-0` |
| Output | `uppercase-out-0` |

If no custom destination is declared, the destination name usually matches the binding name. In that case you can call:

~~~java
input.send(message, "uppercase-in-0");
Message<byte[]> result =
    output.receive(1000, "uppercase-out-0");
~~~

If custom destinations are configured:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase

    stream:
      bindings:
        uppercase-in-0:
          destination: orders-to-normalize

        uppercase-out-0:
          destination: orders-normalized
~~~

Then the test sends and receives using the mapped destination names:

~~~java
input.send(message, "orders-to-normalize");

Message<byte[]> result =
    output.receive(1000, "orders-normalized");
~~~

Here `orders-to-normalize` and `orders-normalized` are destinations; `uppercase-in-0` and `uppercase-out-0` are binding names. Once custom destinations are configured, pass destination names into the named overloads of InputDestination and OutputDestination.

Quick rule of thumb:

- No custom destination configured: use the default binding name.
- Custom destination configured: use the configured destination name.
- Multiple outputs: always specify which output destination to read from.

## 5. Reading Output with receive()

OutputDestination provides these ways to read messages:

~~~java
Message<byte[]> result = output.receive();
~~~

Reads a message from the default output. This is convenient when the application only has one output binding.

~~~java
Message<byte[]> result =
    output.receive(1000, "orders-normalized");
~~~

Reads from the specified destination and waits up to the given timeout. The timeout unit is milliseconds. If no message arrives within the wait window, the result is `null`.

Always check the result before reading the payload:

~~~java
Message<byte[]> result =
    output.receive(1000, "orders-normalized");

assertThat(result)
    .as("application should publish a message to orders-normalized")
    .isNotNull();

assertThat(result.getPayload())
    .isNotEmpty();
~~~

Do not call `result.getPayload()` without first verifying that result is non-null. If the function emitted no output or the test read the wrong destination, a null result causes a NullPointerException and obscures the root cause.

Each receive consumes one message from the test binder's destination. If the function emits multiple messages, call receive for each expected message. Do not read a second time expecting to receive the same message again.

## 6. Verifying Payload and Data Types

OutputDestination returns a Message, so assertions should verify both message presence and payload contents.

For String payloads:

~~~java
Message<byte[]> result =
    output.receive(1000, "uppercase-out-0");

assertThat(result).isNotNull();

String body = new String(
    result.getPayload(),
    StandardCharsets.UTF_8
);

assertThat(body).isEqualTo("HELLO");
~~~

For JSON payloads, you can use Jackson ObjectMapper to deserialize bytes into a DTO:

~~~java
public record OrderSummary(
    String orderId,
    String status,
    long total
) {}
~~~

~~~java
Message<byte[]> result =
    output.receive(1000, "order-summary-out-0");

assertThat(result).isNotNull();

OrderSummary summary = objectMapper.readValue(
    result.getPayload(),
    OrderSummary.class
);

assertThat(summary.orderId()).isEqualTo("order-1001");
assertThat(summary.status()).isEqualTo("ACCEPTED");
assertThat(summary.total()).isEqualTo(250_000L);
~~~

The JSON snippet assumes the application's output converter serialized the DTO to JSON. If using native encoding or custom Serdes, the payload representation may differ. Inspect the exact format emitted by the function/binding.

Do not merely assert that the message is non-null. A meaningful test checks important business values: IDs, statuses, totals, event types, or required fields.

## 7. Inspecting Output Message Headers

A Message in Spring Cloud Stream consists of a payload and headers. When business logic sets a correlation ID, event type, or processing trace, you can assert them on the received Message.

Example of a function that receives a message, normalizes the payload, and adds a header:

~~~java
import java.util.function.Function;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootApplication
public class OrderConfiguration {

    @Bean
    Function<Message<String>, Message<String>> normalizeOrder() {
        return input -> MessageBuilder
            .fromMessage(input)
            .setPayload(input.getPayload().trim().toUpperCase())
            .setHeader("processedBy", "order-normalizer")
            .build();
    }
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.EnableTestBinder;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;

@SpringBootTest(
    classes = OrderConfiguration.class,
    properties = {
        "spring.cloud.function.definition=normalizeOrder"
    }
)
@EnableTestBinder
class OrderHeaderTests {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void preservesCorrelationAndAddsProcessingHeader() {
        Message<byte[]> incoming = MessageBuilder
            .withPayload("  paid  ".getBytes(StandardCharsets.UTF_8))
            .setHeader(
                MessageHeaders.CONTENT_TYPE,
                MimeTypeUtils.TEXT_PLAIN
            )
            .setHeader("correlationId", "corr-1001")
            .build();

        input.send(incoming, "normalizeOrder-in-0");

        Message<byte[]> result =
            output.receive(1000, "normalizeOrder-out-0");

        assertThat(result).isNotNull();
        assertThat(new String(
            result.getPayload(),
            StandardCharsets.UTF_8
        )).isEqualTo("PAID");

        assertThat(result.getHeaders().get("correlationId"))
            .isEqualTo("corr-1001");

        assertThat(result.getHeaders().get("processedBy"))
            .isEqualTo("order-normalizer");
    }
}
~~~

The `contentType` header helps the framework select the right conversion mechanism. The `correlationId` header is added to the input message to test context propagation. The `processedBy` header is created by the function.

Because the test binder runs in the JVM, it is well-suited for verifying the application's message-handling behavior. When using real Kafka, RabbitMQ, or Pulsar binders, header propagation across the broker also depends on header mappers and binder configuration. Test separately if headers are part of a cross-service contract.

## 8. Multiple Output Bindings: Selecting the Right Destination When Reading

An application can activate multiple functions in the same context. Each function has its own inputs and outputs.

~~~java
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TextFunctions {

    @Bean
    Function<String, String> uppercase() {
        return value -> value.toUpperCase();
    }

    @Bean
    Function<String, String> reverse() {
        return value -> new StringBuilder(value).reverse().toString();
    }
}
~~~

Configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase;reverse
~~~

Test:

~~~java
@Test
void readsTheExpectedOutputForEachFunction() {
    Message<byte[]> inputMessage = new GenericMessage<>(
        "Hello".getBytes(StandardCharsets.UTF_8)
    );

    input.send(inputMessage, "uppercase-in-0");
    input.send(inputMessage, "reverse-in-0");

    Message<byte[]> uppercaseResult =
        output.receive(1000, "uppercase-out-0");

    Message<byte[]> reverseResult =
        output.receive(1000, "reverse-out-0");

    assertThat(uppercaseResult).isNotNull();
    assertThat(reverseResult).isNotNull();

    assertThat(new String(
        uppercaseResult.getPayload(),
        StandardCharsets.UTF_8
    )).isEqualTo("HELLO");

    assertThat(new String(
        reverseResult.getPayload(),
        StandardCharsets.UTF_8
    )).isEqualTo("olleH");
}
~~~

If you only call `output.receive()` in a multi-output test, the test may read from the default destination rather than the output you intend to verify. Calling receive with an explicit destination name prevents tests from depending on binding creation order.

If custom destinations are configured for the function:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        uppercase-in-0:
          destination: text-input
        uppercase-out-0:
          destination: uppercase-result
~~~

Then call:

~~~java
input.send(inputMessage, "text-input");

Message<byte[]> result =
    output.receive(1000, "uppercase-result");
~~~

The name passed to receive must be the actual destination whenever a binding is mapped to a custom destination.

## 9. Multiple Inputs for a Single Function

A function with multiple inputs, such as a BiFunction, creates multiple input bindings:

~~~java
import java.util.function.BiFunction;

@Bean
BiFunction<String, String, String> combine() {
    return (left, right) -> left + ":" + right;
}
~~~

Default bindings:

- `combine-in-0`: first input.
- `combine-in-1`: second input.
- `combine-out-0`: output.

The test sends each input to its corresponding destination:

~~~java
input.send(
    new GenericMessage<>("order-1001".getBytes(StandardCharsets.UTF_8)),
    "combine-in-0"
);

input.send(
    new GenericMessage<>("PAID".getBytes(StandardCharsets.UTF_8)),
    "combine-in-1"
);

Message<byte[]> result =
    output.receive(1000, "combine-out-0");

assertThat(result).isNotNull();

assertThat(new String(
    result.getPayload(),
    StandardCharsets.UTF_8
)).isEqualTo("order-1001:PAID");
~~~

Multi-input functions can depend on message arrival timing and data-joining mechanisms. The example above illustrates a simple case. For flows requiring synchronization by key or time, verify the join/aggregation semantics of the specific function or binder.

## 10. Verifying Multiple Messages on the Same Output

A function can emit multiple output messages for a single input, such as a Function returning a Flux or Publisher. OutputDestination buffers each message for the test to read sequentially.

~~~java
import java.util.function.Function;

import reactor.core.publisher.Flux;

@Bean
Function<String, Flux<String>> splitWords() {
    return value -> Flux.fromArray(value.split(" "));
}
~~~

Test:

~~~java
input.send(new GenericMessage<>(
    "spring cloud stream".getBytes(StandardCharsets.UTF_8)
));

Message<byte[]> first =
    output.receive(1000, "splitWords-out-0");

Message<byte[]> second =
    output.receive(1000, "splitWords-out-0");

Message<byte[]> third =
    output.receive(1000, "splitWords-out-0");

assertThat(first).isNotNull();
assertThat(second).isNotNull();
assertThat(third).isNotNull();

assertThat(new String(first.getPayload(), StandardCharsets.UTF_8))
    .isEqualTo("spring");

assertThat(new String(second.getPayload(), StandardCharsets.UTF_8))
    .isEqualTo("cloud");

assertThat(new String(third.getPayload(), StandardCharsets.UTF_8))
    .isEqualTo("stream");
~~~

If message order is a business requirement, assert the exact order. If the binder or topology allows parallel processing and order is not guaranteed, assert the collection of results rather than assuming a fixed order.

With reactive functions, pay attention to subscription and emission timing. OutputDestination's finite timeout lets the test wait for messages over a defined window instead of reading before asynchronous processing completes.

## 11. How to Test a Consumer Without Output?

A Consumer has a void return type:

~~~java
@Bean
Consumer<OrderCreated> recordOrder(OrderService orderService) {
    return order -> orderService.record(order);
}
~~~

A Consumer creates no output binding. Therefore, OutputDestination will not have a message to read simply because the Consumer ran.

For a Consumer, verify side effects using a mock or fake dependency:

~~~java
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.verify;

import org.springframework.test.context.bean.override.mockito.MockitoBean;

@MockitoBean
OrderService orderService;

@Test
void invokesOrderService() {
    input.send(orderMessage, "recordOrder-in-0");

    verify(orderService).record(
        argThat(order -> order.orderId().equals("order-1001"))
    );
}
~~~

The example assumes `OrderService`, `OrderCreated`, and `orderMessage` are declared in the test fixture. `@MockitoBean` is available in Spring Framework 6.2 and later; on older stacks, use Spring Boot's `@MockBean` if still supported by your project version.

If the Consumer calls StreamBridge to emit a message to another output destination, OutputDestination can still check the message sent to that output. In that case, declare or route the proper output binding and read from the corresponding destination.

## 12. Reading Output Sent by StreamBridge

StreamBridge is used when incoming data originates outside a function binding or when the application needs to send messages dynamically to an output binding.

Example:

~~~java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

@Service
public class NotificationPublisher {

    private final StreamBridge streamBridge;

    public NotificationPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(String notification) {
        return streamBridge.send("notification-out-0", notification);
    }
}
~~~

Output destination configuration:

~~~yaml
spring:
  cloud:
    stream:
      output-bindings: notification-out-0

      bindings:
        notification-out-0:
          destination: notifications
~~~

The test calls the service or sends a message via StreamBridge, then reads the output:

~~~java
@Test
void readsStreamBridgeOutput() {
    boolean sent = notificationPublisher.publish("order paid");

    assertThat(sent).isTrue();

    Message<byte[]> result =
        output.receive(1000, "notifications");

    assertThat(result).isNotNull();

    assertThat(new String(
        result.getPayload(),
        StandardCharsets.UTF_8
    )).isEqualTo("order paid");
}
~~~

The boolean returned by StreamBridge indicates whether sending the message to the output channel succeeded. It does not replace assertions on the actual message. Verify both the send result and the received content.

If using dynamic destinations, the test must know the exact destination name created by StreamBridge or configured. Do not read from an output name different from the one the code sends to.

## 13. Testing the Case Where No Output Is Expected

There are valid processing paths that emit no messages, such as a function filtering out events that do not satisfy a condition.

~~~java
import java.util.function.Function;

import reactor.core.publisher.Flux;

@Bean
Function<String, Flux<String>> acceptPaidOrder() {
    return status -> "PAID".equals(status)
        ? Flux.just(status)
        : Flux.empty();
}
~~~

With reactive outputs, `Flux.empty()` indicates no message is emitted. The test can verify that the destination receives no output:

~~~java
input.send(new GenericMessage<>(
    "CANCELLED".getBytes(StandardCharsets.UTF_8)
));

Message<byte[]> result =
    output.receive(100, "acceptPaidOrder-out-0");

assertThat(result).isNull();
~~~

Use a short timeout for no-message assertions. Avoid unnecessarily long timeouts that slow down the test suite. Nor should you treat a timeout as the sole proof of logic: add separate assertions proving the input was sent and the filtering condition behaved properly.

If a function throws an exception, the outcome depends on error handling, retries, and binder configuration. Do not conflate exception cases with cases where a function intentionally emits no output.

## 14. Checking Output Under Asynchronous Processing

Some applications process messages on an executor or reactive pipeline. In those cases, input.send may complete before the output is emitted.

Use a finite timeout on OutputDestination:

~~~java
Message<byte[]> result =
    output.receive(5000, "orders-out");

assertThat(result)
    .as("output should appear within 5 seconds")
    .isNotNull();
~~~

The timeout should be long enough for the test pipeline, yet not so long that it masks failures. If tests frequently wait until the full timeout expires, check:

- Whether the function is activated in `spring.cloud.function.definition`.
- Whether the input was sent to the right destination.
- Whether the output is being read from the right destination.
- Whether an exception occurred inside the function.
- Whether any executor or scheduler has not been started.
- Whether the reactive pipeline is subscribed.
- Whether any asynchronous dependency needs mocking or synchronization.

Do not use `Thread.sleep` as the default synchronization mechanism. Waiting for output with a timeout-based API is usually clearer and more reliable. If you need to wait on multiple distinct side effects, use Awaitility or explicit condition synchronization.

## 15. Testing Content Types and Message Conversion

Spring Cloud Stream can convert payloads based on content type. A message sent as byte[] can be received by a function as a String or DTO depending on headers and converters.

Example sending text/plain:

~~~java
Message<byte[]> message = MessageBuilder
    .withPayload("hello".getBytes(StandardCharsets.UTF_8))
    .setHeader(
        MessageHeaders.CONTENT_TYPE,
        MimeTypeUtils.TEXT_PLAIN
    )
    .build();

input.send(message, "text-input");
~~~

If the function accepts a JSON DTO, send a message with content type application/json and a JSON payload:

~~~java
String json = """
    {
      "orderId": "order-1001",
      "status": "PAID"
    }
    """;

Message<byte[]> message = MessageBuilder
    .withPayload(json.getBytes(StandardCharsets.UTF_8))
    .setHeader(
        MessageHeaders.CONTENT_TYPE,
        MimeTypeUtils.APPLICATION_JSON
    )
    .build();

input.send(message, "orders-in");
~~~

Then read the output bytes and deserialize according to the content type/DTO produced by the output function.

When debugging conversion failures, inspect three factors separately:

1. The Java type declared by the function.
2. The actual payload sent into InputDestination.
3. The contentType header of the message.

If any of these three mismatch, errors may occur before the function is invoked. That differs from logic errors inside the function.

## 16. Test Isolation and Handling Leftover Messages

OutputDestination is a bean bound to the test application context. Messages remain in the destination queue until a test reads them or the context shuts down.

To keep tests stable:

- Each test should send its inputs and consume all outputs it produces.
- Do not share output destinations across tests without controlling leftover messages.
- Read from the exact destination when multiple functions exist.
- Never let tests depend on test method execution order.
- Use separate application contexts when binding configurations differ significantly between tests.
- If a test emits multiple messages, read the exact expected count or assert the expected quantity.

Do not use reflection to access internal channels of InputDestination/OutputDestination. The public API already supports send/receive by destination name. Accessing internal fields couples tests to implementation details and breaks easily on upgrades.

## 17. Test Binder vs. Integration Tests with a Real Broker

The test binder verifies application flow in the JVM. It does not replace integration testing with a real broker.

| Aspect | Test binder + OutputDestination | Broker Integration Test |
|---|---|---|
| Function transformation | Yes | Yes |
| Input/output binding wiring at test binder level | Yes | Yes |
| Payloads and headers in in-JVM flow | Yes | Yes |
| Kafka partitions and consumer groups | No | Yes |
| Rabbit exchanges, queues, and routing keys | No | Yes |
| Pulsar subscription types and backlogs | No | Yes |
| Broker serialization and native header mapping | Incomplete | Yes |
| Binder-specific retry/DLQ | Not fully verified | Yes |
| Network, authentication, and broker permissions | No | Yes |

When you need to verify broker behavior, create separate tests using Kafka Testcontainers/Embedded Kafka, RabbitMQ Testcontainers, or Pulsar Testcontainers. Use the real binder in that test context and send/receive messages through the real broker.

The Spring Cloud Stream documentation notes that the test binder operates as an in-JVM broker. When the test binder is on the test classpath, it is used for testing in place of the middleware binder. Therefore, do not expect a single test to both use in-memory OutputDestination and verify that messages passed through real Kafka/RabbitMQ/Pulsar.

A sound testing strategy:

1. Unit test function logic directly with Java inputs/outputs.
2. Test binder tests for binding flows using InputDestination and OutputDestination.
3. Real-broker integration tests to verify binder config, serialization, partitions/subscriptions, retries, and acknowledgements.
4. End-to-end tests for multi-service business flows if needed.

## 18. Common Errors When Using OutputDestination

| Symptom | Cause | Resolution |
|---|---|---|
| OutputDestination is null | Test binder not configured or dependency missing | Add test binder and enable @EnableTestBinder |
| InputDestination has no channel | Wrong destination name or function not bound | Check function definition and input destination |
| Output receives null | Function emitted no output, read too early, or wrong destination | Inspect function and use receive with timeout |
| Wrong message read | Multiple outputs exist yet default receive() was used | Specify destination name explicitly |
| Payload is byte[] | Output binder returns message bytes | Decode UTF-8 or deserialize according to content type |
| JSON fails to parse | Wrong payload or content type | Check bytes, contentType, and converter |
| Header is missing | Function did not set header or header mapping differs | Check MessageBuilder and test binder; re-verify with real broker |
| Test passes yet Kafka has no messages | Test binder only runs in the JVM | Write integration tests with the real Kafka binder |
| Each test receives previous test's message | Unread messages remained in output within shared context | Drain all output and isolate contexts |
| Test waits until timeout expires | Function not activated or pipeline emitted no output | Check function definition, input/output names, and exceptions |
| Multi-replica tests yield unpredictable results | Test binder does not fully emulate broker concurrency | Use a real test broker for concurrency and partition semantics |

## 19. Hands-On Exercise: Testing an Order Flow

Create an order normalization function:

~~~java
public record Order(
    String orderId,
    String status,
    long total
) {}

@Bean
Function<Order, Order> normalizeOrder() {
    return order -> new Order(
        order.orderId().trim(),
        order.status().toUpperCase(),
        order.total()
    );
}
~~~

Configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder

    stream:
      bindings:
        normalizeOrder-in-0:
          destination: orders-raw

        normalizeOrder-out-0:
          destination: orders-normalized
~~~

Write the test following these steps:

1. Initialize the Spring Boot test context with `@EnableTestBinder`.
2. Inject InputDestination and OutputDestination.
3. Construct a JSON message with whitespace in orderId and lowercase status.
4. Set the content type to application/json.
5. Send the message to destination `orders-raw`.
6. Read output from `orders-normalized` with a finite timeout.
7. Assert that the message is not null.
8. Deserialize the payload into Order.
9. Verify that orderId is trimmed.
10. Verify that status is converted to uppercase.
11. Verify that total remains unchanged.
12. Send an additional invalid input and verify the function behaves according to your designed policy.
13. Add another output binding if the function needs to emit an audit event; verify each output using its own destination.
14. Write real-broker integration tests if you need to verify routing, partitions, or acknowledgements.

Consider the exercise complete when you can explain the roles of InputDestination and OutputDestination; distinguish binding names from destination names; send inputs to the right place; read outputs from the right place; verify payloads, headers, and multiple messages; handle timeouts; and distinguish the test binder from integration tests using a real broker.

## 20. Official References

- [Spring Cloud Stream 5.0 — Testing](https://docs.spring.io/spring-cloud-stream/reference/5.0/spring-cloud-stream/spring_integration_test_binder.html) — test binder, @EnableTestBinder, InputDestination, OutputDestination, and multiple destinations.
- [Spring Cloud Stream 5.0 — Reference Documentation](https://docs.spring.io/spring-cloud-stream/reference/5.0/spring-cloud-stream.html) — application model, functions, binders, and core testing.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — functional beans, binding names, and StreamBridge.
- [Spring Cloud Stream 5.0 — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/5.0/spring-cloud-stream/binding-properties.html) — destinations, content types, and input/output binding configuration.
