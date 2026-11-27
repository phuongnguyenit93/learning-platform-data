# @Transformer

## 1. Objectives and Context

In the **Annotations and XML** chapter of the **SPRING_INTEGRATION_CORE** module, `@Transformer` turns a Java method into a data transformation step in a message flow. After this lesson, you can configure the endpoint with annotations, understand the input/output contract, preserve necessary headers, and represent the same step using XML or Java DSL.

Suppose the system receives orders as strings:

```text
"  od-42 | 3 | 125000.00  "
```

Downstream business steps need an `OrderCommand` with a normalized order ID, an `int` quantity, and a `BigDecimal` unit price. Instead of forcing the sender to know the internal structure, we place a transformer between the two sides:

```mermaid
flowchart LR
    A[Partner system] --> B[rawOrders: DirectChannel]
    B --> C[Transformer: String to OrderCommand]
    C --> D[canonicalOrders: QueueChannel]
    D --> E[Order processing step]
```

A transformer focuses on **data representation**. Choosing the next channel belongs to a router; deciding whether to accept a message belongs to a filter; combining messages belongs to an aggregator. In a real flow, these endpoints collaborate, but each step should have a clear responsibility.

## 2. What Does `@Transformer` Create?

The annotation to use is:

```java
import org.springframework.integration.annotation.Transformer;
```

When Spring Integration infrastructure processes a Spring bean with a method like the following, it creates an endpoint that receives messages from `rawOrders`, invokes the method with the appropriate payload, and sends the result to `canonicalOrders`:

```java
@Transformer(inputChannel = "rawOrders", outputChannel = "canonicalOrders")
public OrderCommand normalize(String line) {
    return parser.parse(line);
}
```

The call flow has three distinct layers:

1. **Channel** transports the message and determines how it is delivered to the consumer.
2. **Endpoint/handler** orchestrates invoking the method and sending the result.
3. **Transformation method** executes the data conversion rules.

`@Transformer` does not automatically turn an object instantiated with `new` outside Spring into a consumer. The object containing the method must be registered as a bean, and the application must have integration infrastructure enabled. Examples in this lesson use `@Configuration`, `@EnableIntegration`, and `@Bean` to make registration explicit; no component scanning is needed. See [Annotation Support](https://docs.spring.io/spring-integration/reference/6.5/configuration/annotations.html).

A direct Java call such as `endpoint.normalize(line)` only executes the method body. It does not go through the input channel, output channel, or endpoint orchestration mechanism. Therefore, testing the method directly and testing the messaging flow serve different purposes.

### Common Attributes

| Attribute | Practical Meaning |
| --- | --- |
| `inputChannel` | Name of the channel from which the endpoint receives messages. |
| `outputChannel` | Name of the channel receiving the transformed result. |
| `poller` | Polling configuration when the input is a `PollableChannel`. |
| `adviceChain` | Attaches advice around the handler, such as a defined retry policy. |
| `autoStartup` | Controls automatic endpoint startup. |
| `sendTimeout` | Wait timeout when sending the result if a bounded output channel causes the send operation to wait. |

`sendTimeout` is not an execution time limit for the transformation method. A method blocked on a remote service call is not automatically interrupted when this value expires. The meaning of each attribute is described in [Javadoc for `@Transformer`](https://docs.spring.io/spring-integration/api/org/springframework/integration/annotation/Transformer.html).

## 3. Input and Output Contracts

### 3.1. Receive the Payload or the Entire Message?

Choose the smallest signature sufficient for the job:

| Example Signature | When Appropriate |
| --- | --- |
| `OrderCommand convert(String payload)` | The rule only depends on data inside the payload. |
| `OrderCommand convert(String payload, @Header("sourceSystem") String source)` | A specific header is needed to interpret the data. |
| `OrderCommand convert(String payload, @Headers Map<String, Object> headers)` | Multiple metadata entries are needed and read by name. |
| `Message<OrderCommand> convert(Message<String> message)` | You need to explicitly construct both the output payload and headers. |

`@Header` and `@Headers` belong to the `org.springframework.messaging.handler.annotation` package. A parameter receiving the payload does not need to be typed as `Message<?>` just because it is processed in Spring Integration.

Avoid declaring multiple unannotated parameters that could all be interpreted as the payload. With `String line, String sourceSystem`, the framework cannot infer which string you intend as metadata; explicitly annotate the second parameter with `@Header`.

Do not rely on implicit type conversion to parse a business format. If the input is a line of text, accept `String`, parse it yourself, and state the validation rules clearly. Using `Object` and casting internally makes the contract harder to see.

### 3.2. How Returning a Payload Differs from Returning a `Message`

If the method returns `OrderCommand`, the framework creates an output message carrying that payload and forwards input headers according to the default header propagation mechanism.

If the method returns `Message<OrderCommand>`, the transformer treats it as the complete message. Application code is responsible for the headers of the returned message; there is no step that automatically fills in missing input headers. Configurations that restrict propagation can also change the header set when returning only a payload. This is an important distinction for transformers, explained in [Message — Header Propagation](https://docs.spring.io/spring-integration/reference/6.5/message.html#message-header-propagation).

Therefore, decide explicitly:

- Only transforming data: returning the payload is usually simpler.
- Need to modify metadata along with data: return `Message` and construct headers deliberately.
- Only adding or removing headers: consider a header enricher or header filter to express the intent accurately.

### 3.3. The Result Must Not Be `null`

A transformer must produce a valid result for every successful execution. Returning `null` is treated as an error, not a way to silently discard a message. `void` is also unsuitable for this contract. To drop data that fails a condition, use a filter; to invoke an operation that may not return a reply, consider a service activator. This contract is stated in [Transformer](https://docs.spring.io/spring-integration/reference/6.5/transformer.html).

Returning `List<OrderCommand>` produces a single list-typed payload. It does not automatically turn one message into multiple independent messages. If each element needs to go through the flow separately, use a splitter.

## 4. Complete Example: Normalizing an Order Line

### 4.1. Environment and Data Contract

The example uses Java 17 or higher, Spring Integration 6.x, and JUnit Jupiter for testing. The demonstrated APIs follow the 6.5 documentation. The project requires the `org.springframework.integration:spring-integration-core` dependency; Spring Integration and Spring library versions must be managed consistently via a BOM or your project's dependency management.

If the project uses Spring Boot with a matching BOM, the corresponding starters are:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

These declarations assume the project already has a Spring Boot parent or BOM; this is not a standalone `pom.xml`. The example needs no broker, database, or network connection when processing messages.

Data conventions for this lesson:

| Component | Rule |
| --- | --- |
| Input line | Exactly three fields, separated by the `\|` character. |
| Order ID | Trim whitespace on both ends, convert to uppercase using `Locale.ROOT`, non-empty. |
| Quantity | Positive integer within the `int` range. |
| Unit price | Positive decimal number, using dot notation, represented accurately with scale 2. |
| `traceId` header | Preserved to track the same request across steps. |

This parser serves a small text protocol, not a general-purpose CSV reader: it does not support delimiters inside fields, escaping, or quoted fields.

### 4.2. Target Data Type

Sample file `OrderCommand.java`:

```java
package example.integration;

import java.math.BigDecimal;

public record OrderCommand(
        String orderId,
        int quantity,
        BigDecimal unitPrice) {
}
```

A record fits the example because fields are not reassigned after creation. Using `BigDecimal` avoids introducing `double` precision errors into the unit price right from the parsing step.

### 4.3. Separating the Parser from Endpoint Declarations

Sample file `OrderLineParser.java`:

```java
package example.integration;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;

public class OrderLineParser {

    public OrderCommand parse(String line) {
        if (line == null || line.isBlank()) {
            throw new IllegalArgumentException("Order line must not be blank");
        }

        String[] fields = line.split("\\|", -1);
        if (fields.length != 3) {
            throw new IllegalArgumentException(
                    "Expected format: orderId|quantity|unitPrice");
        }

        String orderId = fields[0].strip().toUpperCase(Locale.ROOT);
        if (orderId.isEmpty()) {
            throw new IllegalArgumentException("orderId must not be blank");
        }

        int quantity = Integer.parseInt(fields[1].strip());
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        BigDecimal unitPrice = new BigDecimal(fields[2].strip());
        if (unitPrice.signum() <= 0) {
            throw new IllegalArgumentException("unitPrice must be positive");
        }
        unitPrice = unitPrice.setScale(2, RoundingMode.UNNECESSARY);

        return new OrderCommand(orderId, quantity, unitPrice);
    }
}
```

The `-1` parameter to `split` preserves trailing empty fields. For example, `OD-42|3|` still has three fields, then gets rejected because unitPrice is empty. `RoundingMode.UNNECESSARY` causes values like `125000.001` to throw an error instead of rounding automatically; values with extra trailing zeros can still be converted cleanly to scale 2.

The parser does not access channels or the application context. It can be invoked from annotations, XML, DSL, and unit tests with the exact same rules.

### 4.4. Configuring Channels and the Endpoint with Annotations

Sample file `OrderFlowConfiguration.java`:

```java
package example.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Transformer;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration(proxyBeanMethods = false)
@EnableIntegration
public class OrderFlowConfiguration {

    @Bean
    public MessageChannel rawOrders() {
        return new DirectChannel();
    }

    @Bean
    public PollableChannel canonicalOrders() {
        return new QueueChannel(20);
    }

    @Bean
    public OrderLineParser orderLineParser() {
        return new OrderLineParser();
    }

    @Bean
    public OrderTransformerEndpoint orderTransformerEndpoint(
            OrderLineParser parser) {
        return new OrderTransformerEndpoint(parser);
    }

    public static class OrderTransformerEndpoint {

        private final OrderLineParser parser;

        public OrderTransformerEndpoint(OrderLineParser parser) {
            this.parser = parser;
        }

        @Transformer(
                inputChannel = "rawOrders",
                outputChannel = "canonicalOrders")
        public OrderCommand normalize(String line) {
            return parser.parse(line);
        }
    }
}
```

Here, `@Bean` registers the object containing the method; `@Transformer` on `normalize` describes the message processing step. The two annotations solve two different concerns.

`rawOrders` is a `DirectChannel`, so invoking the transformer happens on the thread sending the message. `canonicalOrders` is the output queue, only buffering results for the downstream reader. Having a queue at the output does not automatically move the parser onto a background thread.

There is no poller in this configuration because **the transformer's input** is a `DirectChannel`. A queue used as the result receiver in this example can be read directly via `receive`.

### 4.5. Sending and Reading the Result

Sample file `OrderFlowDemo.java`:

```java
package example.integration;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;

public class OrderFlowDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                OrderFlowConfiguration.class)) {

            MessageChannel input = context.getBean(
                    "rawOrders", MessageChannel.class);
            PollableChannel output = context.getBean(
                    "canonicalOrders", PollableChannel.class);

            Message<String> request = MessageBuilder
                    .withPayload("  od-42 | 3 | 125000.00  ")
                    .setHeader("traceId", "trace-order-42")
                    .build();

            if (!input.send(request)) {
                throw new IllegalStateException("Input channel rejected message");
            }

            Message<?> result = output.receive(1000);
            if (result == null) {
                throw new IllegalStateException("No transformed message received");
            }

            System.out.println(result.getPayload());
            System.out.println(result.getHeaders().get("traceId"));
        }
    }
}
```

Expected output:

```text
OrderCommand[orderId=OD-42, quantity=3, unitPrice=125000.00]
trace-order-42
```

Returning `true` from `send` does not mean the order has been written to a database or finished business processing. With this specific configuration, the transformer ran synchronously and placed the result onto the queue; steps after the queue remain separate work.

## 5. When Transformation Rules Depend on a Header

Suppose the format above only applies to the `partner-a` source. You can replace the `normalize` method in the endpoint with:

```java
import org.springframework.messaging.handler.annotation.Header;

@Transformer(inputChannel = "rawOrders", outputChannel = "canonicalOrders")
public OrderCommand normalize(
        String line,
        @Header("sourceSystem") String sourceSystem) {

    if (!"partner-a".equals(sourceSystem)) {
        throw new IllegalArgumentException("Unsupported sourceSystem");
    }
    return parser.parse(line);
}
```

When sending, add `.setHeader("sourceSystem", "partner-a")` to `MessageBuilder`. `@Header` requires the header to exist by default; a missing header causes parameter resolution to fail before the method body runs.

If the metadata is allowed to be missing, declare `@Header(value = "sourceSystem", required = false)` and use a nullable type, then define the default value explicitly in code. Do not mark mandatory metadata as optional just to hide configuration mistakes. How header parameters are bound is described in [Annotation Support — Parameter Annotations](https://docs.spring.io/spring-integration/reference/6.5/configuration/annotations.html).

If there are multiple sources with different formats, a more readable design is a router by `sourceSystem`, where each branch has its own parser, and all converge on `OrderCommand`. That way the transformer does not hold a long conditional chain for every partner.

## 6. Explicitly Building a Message and Preserving Metadata

Sometimes a transformation step both changes the payload and needs to tag a schema. In that case, you can replace the original `normalize` method with the following `Message`-returning version:

```java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Transformer(inputChannel = "rawOrders", outputChannel = "canonicalOrders")
public Message<OrderCommand> normalize(Message<String> input) {
    OrderCommand command = parser.parse(input.getPayload());

    return MessageBuilder
            .withPayload(command)
            .copyHeaders(input.getHeaders())
            .setHeader("payloadSchema", "order-command-v1")
            .build();
}
```

This is a **replacement** for the old method, not adding a second consumer to the same input channel. The builder call order shows that input headers are copied first, and then `payloadSchema` is set according to the new data type.

Do not modify `input.getHeaders().put(...)` directly: the `MessageHeaders` structure is read-only. When building a new message via the builder, system `id` and `timestamp` are managed separately; do not use them in place of a business tracking ID. A dedicated `traceId` or request ID is more suitable for linking processing steps. See [Message — Headers and Message ID Generation](https://docs.spring.io/spring-integration/reference/6.5/message.html).

In real applications, consider each metadata group:

| Header Group | Considerations |
| --- | --- |
| Business trace IDs | Usually need to be preserved to track requests across multiple steps. |
| `replyChannel`, `errorChannel` | Meaningful for reply and error reporting mechanisms inside the application. |
| Payload-describing metadata | Update if the format or schema has changed. |
| Correlation and sequence | Check if an aggregator/resequencer sits downstream. |
| Transport headers | Select based on adapter boundaries and outbound mapping policies. |

`copyHeaders` in the example is a choice for an internal step. When building a new message with `MessageBuilder.withPayload(command).build()` without copying headers, the transformer can lose `traceId` or information needed by a gateway/aggregator.

## 7. `DirectChannel`, `QueueChannel`, and Pollers

The **input channel** type determines how the endpoint is triggered:

| Input Channel | How the Transformer Runs | Poller |
| --- | --- | --- |
| `DirectChannel` | Consumer is invoked on the sender's thread. | Do not configure a poller. |
| `QueueChannel` | Consumer actively pulls messages on a schedule. | Requires a poller on the endpoint or a default poller. |
| `ExecutorChannel` | Dispatches work through a configured executor. | Do not configure a poller to read a queue. |

For example, switching the input to a queue requires changing both the input bean and the method configuration:

```java
// Replace the original rawOrders bean.
@Bean
public PollableChannel rawOrders() {
    return new QueueChannel(100);
}

// Replace the annotation on normalize; keep the method body unchanged.
@Transformer(
        inputChannel = "rawOrders",
        outputChannel = "canonicalOrders",
        poller = @Poller(fixedDelay = "100", maxMessagesPerPoll = "10"))
public OrderCommand normalize(String line) {
    return parser.parse(line);
}
```

You need to import `org.springframework.integration.annotation.Poller`. `fixedDelay` in the example is a string representing milliseconds; `maxMessagesPerPoll` limits the number of messages processed in a single poll. This mechanism is presented in [Annotation Support — Using the `@Poller` Annotation](https://docs.spring.io/spring-integration/reference/6.5/configuration/annotations.html#using-the-poller-annotation).

After this change, `send` only puts the message into the queue. The sender cannot infer that the parser succeeded right after calling send. Tests must wait for a result or error with a finite timeout.

A queue with capacity makes buffer limits visible, but it does not automatically turn the flow into durable storage. The example uses an in-memory `QueueChannel`; meeting recovery requirements after process shutdown requires a dedicated persistence design.

## 8. Equivalent XML Configuration

XML is another way to declare endpoints. You can keep `OrderCommand` and `OrderLineParser` unchanged, and use the following configuration instead of `OrderFlowConfiguration`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:int="http://www.springframework.org/schema/integration"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd
         http://www.springframework.org/schema/integration
         https://www.springframework.org/schema/integration/spring-integration.xsd">

    <int:channel id="rawOrders"/>

    <int:channel id="canonicalOrders">
        <int:queue capacity="20"/>
    </int:channel>

    <bean id="orderLineParser"
          class="example.integration.OrderLineParser"/>

    <int:transformer id="normalizeOrder"
                     input-channel="rawOrders"
                     output-channel="canonicalOrders"
                     ref="orderLineParser"
                     method="parse"/>
</beans>
```

If saved on the classpath as `order-flow.xml`, you can open the context with:

```java
try (var context = new org.springframework.context.support
        .ClassPathXmlApplicationContext("order-flow.xml")) {
    // Retrieve rawOrders and canonicalOrders, send/receive as in the previous example.
}
```

`ref` points to the bean, and `method` identifies the processing method. The parser here does not need `@Transformer`: the XML element itself creates the endpoint. How a bean and method are wired is described in [Transformer — Configuring a Transformer with XML](https://docs.spring.io/spring-integration/reference/6.5/transformer.html#transformer-namespace).

| Annotation | XML |
| --- | --- |
| `@Transformer(...)` | `<int:transformer .../>` |
| `inputChannel` | `input-channel` |
| `outputChannel` | `output-channel` |
| Annotated method | `ref` combined with `method` |
| `poller = @Poller(...)` | Child element `<int:poller .../>` |

Do not simultaneously load both the XML configuration and the annotation configuration for the same step into one context. Two endpoints subscribing to the same `DirectChannel` will compete to receive messages according to the dispatcher's rules; they are not two notations for a single endpoint. To migrate from annotations to XML, transfer endpoint creation ownership to XML as well.

## 9. Writing the Same Step in Java DSL

Java DSL makes step order easier to see as flows grow longer. With the plain Java parser above, the complete alternative configuration is:

```java
package example.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;

@Configuration(proxyBeanMethods = false)
@EnableIntegration
public class OrderDslConfiguration {

    @Bean
    public MessageChannel rawOrders() {
        return new DirectChannel();
    }

    @Bean
    public PollableChannel canonicalOrders() {
        return new QueueChannel(20);
    }

    @Bean
    public OrderLineParser orderLineParser() {
        return new OrderLineParser();
    }

    @Bean
    public IntegrationFlow orderFlow(OrderLineParser parser) {
        return IntegrationFlow.from("rawOrders")
                .transform(parser, "parse")
                .channel("canonicalOrders")
                .get();
    }
}
```

Here `.transform(...)` creates the transformation step; the `parse` method does not need `@Transformer`. The DSL directly uses Spring Integration components and registers them via an `IntegrationFlow` bean, as described in [Java DSL](https://docs.spring.io/spring-integration/reference/6.5/dsl.html).

Load only one of the three configurations—annotation, XML, or DSL—for the same example flow. They can coexist in a larger application when each configuration owns distinct endpoints.

## 10. Distinguishing Two Places Where the Annotation Is Used

### Annotation on a Processing Method

In the main example, `normalize(String line)` is a method invoked **for each message**. The object containing it is created by a separate `@Bean` method.

### Annotation on a Transformer Bean Factory Method

Spring Integration also supports placing messaging annotations on a `@Bean` method that returns a prebuilt transformer. The following example assumes two channels `rawNotes` and `textNotes` are already registered:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.Transformer;
import org.springframework.integration.transformer.ObjectToStringTransformer;

@Bean
@Transformer(inputChannel = "rawNotes", outputChannel = "textNotes")
public ObjectToStringTransformer noteToText() {
    return new ObjectToStringTransformer();
}
```

`noteToText()` is a factory method executed when creating the bean; it is not a method that receives individual payloads. The endpoint will use the returned transformer object. Pay attention to the difference between the annotation `org.springframework.integration.annotation.Transformer` and the interface `org.springframework.integration.transformer.Transformer` when reading code or choosing imports.

Do not place `@Bean` on `OrderCommand normalize(String line)` expecting Spring to pass payloads into factory parameters. That mixes bean creation time with message processing time.

If the factory returns a `MessageHandler` instead of a transformer strategy, handler options must be set on the handler itself according to the corresponding rules; do not assume every annotation attribute applies the same way as on a POJO method. See [Messaging Meta-Annotations — Annotations on `@Bean` Methods](https://docs.spring.io/spring-integration/reference/6.5/configuration/meta-annotations.html#annotations_on_bean_methods).

## 11. Handling Errors at the Right Boundary

With `rawOrders` as a `DirectChannel`, data like `OD-42|abc|125000.00` causes the parser to throw an error on the sending thread. Spring Integration may wrap the cause in a messaging exception; callers should inspect the `cause` chain and the failed message information instead of relying solely on the outermost error message.

If you switch the input to a `QueueChannel` and use a poller, the sender has already completed the enqueue operation before the parser runs. Processing errors must be observed through the polling task's error mechanism, typically as an `ErrorMessage`. The default error handler checks the message's `errorChannel` header and then the global `errorChannel`; a poller can also have its own configured error channel. Setting this header alone does not turn a synchronous error from a direct `DirectChannel.send` call into asynchronous error handling. See [Error Handling](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html).

| Error | Appropriate Handling in the Example |
| --- | --- |
| Wrong field count, missing ID, negative quantity | Report invalid data; fix or route to an invalid-data handling flow. |
| Required header missing | Check the contract between producer and endpoint. |
| Transformer returns `null` | Fix the return contract or use a filter for discarding. |
| Unit price has fractional digits needing rounding | Define the business policy; the current example intentionally rejects it. |
| Output queue is full | Review consumer throughput, capacity, and send timeout. |

Retrying the same malformed string will not make the data valid. For a pure, deterministic transformer like this parser, prioritize diagnosing input data. If there is an I/O operation that needs retry, separate it into its own step so the contract and error policy stay clear.

## 12. Testing from Parsing Rules to Message Routing

The test snippets below are sample code to include in a project. Parser tests answer whether the data rules are correct; flow tests verify that beans, annotations, channels, headers, and error paths are wired properly.

### 12.1. Testing the Parser Without Spring

Sample file `OrderLineParserTest.java`:

```java
package example.integration;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class OrderLineParserTest {

    private final OrderLineParser parser = new OrderLineParser();

    @Test
    void normalizesOrderFields() {
        OrderCommand actual = parser.parse(" od-42 | 3 | 125000.00 ");

        assertEquals(new OrderCommand(
                "OD-42", 3, new BigDecimal("125000.00")), actual);
    }

    @Test
    void rejectsZeroQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> parser.parse("OD-42|0|125000.00"));
    }

    @Test
    void doesNotRoundUnexpectedPrecision() {
        assertThrows(ArithmeticException.class,
                () -> parser.parse("OD-42|3|125000.001"));
    }
}
```

### 12.2. Testing the Annotation Endpoint

Sample file `OrderFlowTest.java`:

```java
package example.integration;

import java.math.BigDecimal;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import static org.junit.jupiter.api.Assertions.*;

class OrderFlowTest {

    private AnnotationConfigApplicationContext context;
    private MessageChannel input;
    private PollableChannel output;

    @BeforeEach
    void openContext() {
        context = new AnnotationConfigApplicationContext(
                OrderFlowConfiguration.class);
        input = context.getBean("rawOrders", MessageChannel.class);
        output = context.getBean("canonicalOrders", PollableChannel.class);
    }

    @AfterEach
    void closeContext() {
        context.close();
    }

    @Test
    void transformsPayloadAndPreservesTraceId() {
        Message<String> request = MessageBuilder
                .withPayload(" od-42 | 3 | 125000.00 ")
                .setHeader("traceId", "trace-order-42")
                .build();

        assertTrue(input.send(request));
        Message<?> result = output.receive(1000);

        assertNotNull(result);
        assertInstanceOf(OrderCommand.class, result.getPayload());
        assertEquals(new OrderCommand(
                "OD-42", 3, new BigDecimal("125000.00")),
                result.getPayload());
        assertEquals("trace-order-42", result.getHeaders().get("traceId"));
        assertNotEquals(request.getHeaders().getId(),
                result.getHeaders().getId());
        assertNull(output.receive(0));
    }

    @Test
    void reportsInvalidDataToDirectChannelSender() {
        Message<String> request = MessageBuilder
                .withPayload("OD-42|abc|125000.00")
                .build();

        MessagingException error = assertThrows(MessagingException.class,
                () -> input.send(request));

        assertInstanceOf(NumberFormatException.class, rootCause(error));
        assertNotNull(error.getFailedMessage());
        assertEquals(request.getPayload(),
                error.getFailedMessage().getPayload());
        assertNull(output.receive(0));
    }

    private static Throwable rootCause(Throwable error) {
        Throwable current = error;
        while (current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }
}
```

A fresh context per test keeps the queue clean and closes resources afterward. `receive(1000)` has a finite wait timeout; `receive(0)` reads immediately to detect stray messages or confirm the queue has no result yet.

Checking for a different `id` applies to this specific case: the input carries a `String`, and the output is a new message carrying an `OrderCommand`. Do not conclude that every endpoint always changes `id`.

If switching to the header-dependent option in section 5, add tests for missing `sourceSystem`, unsupported source, and valid source. If switching the input to a queue, replace the test catching an error from `send` with a test receiving an `ErrorMessage` on the configured error channel. Do not use the same error assumption for both execution models.

## 13. Common Misconceptions

| Misconception | Consequence | Adjustment |
| --- | --- | --- |
| Instantiating endpoint with `new` without registering a bean | Annotation does not create a consumer. | Register the bean and enable integration infrastructure. |
| Calling the method directly to test the whole flow | Fails to test wiring and header propagation. | Send messages through the input channel in flow tests. |
| Returning `null` to discard invalid orders | Treated as a transformation error. | Use a filter for accept/discard decisions. |
| Returning a new message without keeping headers | Loses tracing or routing metadata. | Build the message and choose headers deliberately. |
| Adding a poller because the output is a queue | Confuses which side triggers the endpoint. | Check the transformer's input channel type. |
| Treating `sendTimeout` as a parser timeout | The method can still run for a long time. | Enforce timeouts on the actual operation being bounded. |
| Registering the same step via both annotation and DSL | Creates an extra endpoint or bean conflict. | Each step should have one owner declaring its endpoint. |
| Treating a returned list as multiple messages | Downstream step receives the entire list. | Use a splitter when each element needs separate processing. |
| Calling payments or updating a database inside a parser | Mixes transformation with side effects, hard to retry. | Separate business operations into their own endpoint. |

To design a new transformer, be able to describe its input, output, error conditions, metadata to preserve, and execution style determined by the channel. If any of these parts are not answered clearly, adding an annotation alone is not enough to complete the step's contract.

## 14. Extended Practice

1. Add a rule accepting only order IDs starting with `OD-`, with valid and invalid data. Decide whether that is a parser data-structure error or a filter acceptance policy, and explain your choice.
2. Replace the payload-returning method with the `Message`-returning version in section 6. Verify that `traceId` stays intact and `payloadSchema` is set properly.
3. Switch the input to a `QueueChannel`, add a poller, and configure a dedicated error channel. Send invalid data, then observe the error via a message instead of expecting `send` to throw a parse exception.
4. Replace the annotation configuration with XML, then with DSL. For each approach, use the same test data to compare output and header contracts.
5. Extend the flow to `gateway → transformer → router → service activator`. Identify where the gateway accepts application calls, what data the transformer normalizes, and which property of `OrderCommand` the router inspects.

The target outcome is a transformation step with a clear contract, reusable data rules, and observable behavior when integrated into an enterprise integration flow.
