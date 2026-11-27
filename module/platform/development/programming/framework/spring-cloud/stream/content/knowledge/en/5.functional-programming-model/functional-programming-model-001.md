# Declaring Supplier, Function, and Consumer with @Bean

Spring Cloud Stream uses a functional programming model to connect business logic with the messaging system. Instead of writing a separate listener container or producer for each broker, the application declares beans using Java's three standard functional interfaces: `Supplier`, `Function`, and `Consumer`. The binder connects those functions to destinations through input bindings and output bindings.

The three functional types represent three fundamental roles in an event stream: producing data to publish, receiving and transforming data, or receiving data to perform an action. Once you understand the function signatures, bean names, and binding naming conventions, you can structure a Spring Cloud Stream application clearly and switch between Kafka, RabbitMQ, or Pulsar with minimal changes to your business logic.

## Learning Objectives

After this lesson, you will be able to:

- Explain the roles of `Supplier<T>`, `Function<I, O>`, and `Consumer<T>` in Spring Cloud Stream.
- Declare each functional type using a `@Bean` method in a Spring configuration class.
- Determine input binding and output binding names from the bean name.
- Activate one or more function beans with `spring.cloud.function.definition`.
- Configure the destination and group for each binding.
- Distinguish between raw payloads, `Message<T>`, and message headers.
- Test function logic independently before testing broker connectivity.

## 1. The Functional Model in Spring Cloud Stream

In the functional model, the application focuses on processing data. Spring Cloud Stream manages the connection between functions and middleware through a binder.

| Function Type | General Signature | Role | Default Binding |
|---|---|---|---|
| Supplier | `Supplier<T>` | Produces data to publish | `<beanName>-out-0` |
| Function | `Function<I, O>` | Receives data, transforms it, and publishes the result | `<beanName>-in-0`, `<beanName>-out-0` |
| Consumer | `Consumer<T>` | Receives data and performs an action | `<beanName>-in-0` |

In this table, `T` is the data type produced or consumed, `I` is the input type, and `O` is the output type. These types can be plain Java classes, records, shared data types, or `Message<T>`.

### Supplier: Data Source

`Supplier<T>` takes no input parameters and returns a value. Spring Cloud Stream invokes the supplier through a poller to retrieve data and send it to the output binding.

~~~java
@Bean
Supplier<String> greetingSource() {
    return () -> "Hello from Spring Cloud Stream";
}
~~~

A bean named `greetingSource` creates the default output binding `greetingSource-out-0`. A Supplier is suitable when the application needs to publish data from a source that can be polled periodically, such as an outbox, an internal queue, or a scheduled data source.

A Supplier is not a function invoked directly by an incoming message from a broker. If data needs to be emitted when a business operation occurs in a service or controller, you can use `StreamBridge` to send data through an output binding. This distinction separates a periodically polled source from proactive event publishing.

### Function: Receiving and Transforming Data

`Function<I, O>` accepts a value of type `I`, processes it, and returns a result of type `O`. Spring Cloud Stream connects the function's input binding and output binding to the broker.

~~~java
@Bean
Function<String, String> uppercase() {
    return value -> value.toUpperCase();
}
~~~

The `uppercase` bean has the input binding `uppercase-in-0` and the output binding `uppercase-out-0`. Each incoming message is converted into an output value according to the function's logic.

A Function is well suited for standalone transformation steps such as data normalization, enrichment, attribute calculation, or converting an event into a format suitable for the next step.

### Consumer: Receiving and Processing Data

`Consumer<T>` accepts a value of type `T` and returns no result. This is typically the end of a processing pipeline: persisting data, updating state, calling a business service, or producing side effects.

~~~java
@Bean
Consumer<String> logMessage() {
    return value -> System.out.println("Received: " + value);
}
~~~

The `logMessage` bean creates the input binding `logMessage-in-0`. Because a Consumer produces no return value, it has no output binding generated from its function signature.

A Consumer should only acknowledge successful processing after the required business work is complete. If the logic throws an exception, error handling, retry, or dead-letter behavior depends on the binder and Spring Cloud Stream configuration.

## 2. Bean Names Determine Binding Names

The name of a method annotated with `@Bean` normally becomes the bean name in the Spring Application Context. Spring Cloud Stream uses the function bean name to derive the binding names.

For a bean named `processOrder`:

- If it is a `Supplier<T>`, the output binding is `processOrder-out-0`.
- If it is a `Function<I, O>`, the input binding is `processOrder-in-0` and the output binding is `processOrder-out-0`.
- If it is a `Consumer<T>`, the input binding is `processOrder-in-0`.

The suffixes `-in-0` and `-out-0` denote the first input port and first output port. Functions with multiple inputs or outputs can have additional corresponding indices; when using complex function types, verify the binding names generated by the framework against your actual configuration.

You can specify an explicit bean name using the `@Bean` attribute:

~~~java
@Bean("orderNormalizer")
Function<OrderCreated, NormalizedOrder> normalize() {
    return event -> new NormalizedOrder(
        event.orderId(),
        event.total().stripTrailingZeros()
    );
}
~~~

In this example, the function bean name is `orderNormalizer`, so the binding names are derived from this name rather than the method name `normalize`. Clear naming keeps binding configuration stable and easy to read.

Avoid renaming beans arbitrarily after deployment. Binding names may be referenced in environment configurations, dashboards, tests, and operational documentation.

## 3. Activating Function Beans with Function Definition

An application can declare multiple beans of different functional types. The `spring.cloud.function.definition` property specifies which functions Spring Cloud Stream activates to create bindings.

For example, an application declares three function beans:

~~~yaml
spring:
  cloud:
    function:
      definition: orderSource;enrichOrder;recordOrder
~~~

The semicolon separates independent functions to activate. It does not mean that the output of the preceding function automatically becomes the input of the next function. Each function still has its own bindings and can connect to different destinations.

If you want to chain functions using function composition, Spring Cloud Function supports the `|` operator in the function definition. In that case, the output of the preceding function is passed directly to the next function in the same processing chain according to composition rules. Only use composition when the function signatures and processing goals align; do not confuse it with multiple independent functions connecting through a broker.

When there is only a single function bean, the framework can automatically detect it in certain configurations. In applications with multiple beans, declare the definition explicitly to avoid activating the wrong function or leaving the intended function unresolved.

## 4. Complete Example: Supplier, Function, and Consumer for Orders

Consider an order processing flow consisting of three steps:

1. The event source retrieves a pending `OrderCreated` event.
2. The Function enriches the information and converts it into an `EnrichedOrder`.
3. The Consumer writes the result to the order ledger.

The example uses the `orders` destination for the first step and `enriched-orders` for the second step. This is how a flow is organized through a broker; each function can be deployed in the same application or split into separate applications depending on operational requirements.

### Declaring Data Types and Supporting Contracts

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record OrderCreated(
    String eventId,
    String orderId,
    BigDecimal total,
    Instant occurredAt
) {}

public record EnrichedOrder(
    String eventId,
    String orderId,
    BigDecimal total,
    BigDecimal tax,
    Instant processedAt
) {}
~~~

The data source and persistence component are represented by business interfaces:

~~~java
public interface OrderEventSource {
    // Return a pending event; return null if no event is currently available.
    OrderCreated pollNextPendingEvent();
}

public interface OrderLedger {
    void append(EnrichedOrder order);
}
~~~

These interfaces are implemented by the application. The example does not depend on a specific storage mechanism, as the goal is to illustrate how Spring Cloud Stream connects function signatures to bindings.

### Declaring Three Function Beans

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctionConfiguration {

    @Bean
    Supplier<OrderCreated> orderSource(OrderEventSource source) {
        return source::pollNextPendingEvent;
    }

    @Bean
    Function<OrderCreated, EnrichedOrder> enrichOrder() {
        return event -> {
            BigDecimal tax = event.total()
                .multiply(new BigDecimal("0.10"));

            return new EnrichedOrder(
                event.eventId(),
                event.orderId(),
                event.total(),
                tax,
                Instant.now()
            );
        };
    }

    @Bean
    Consumer<EnrichedOrder> recordOrder(OrderLedger ledger) {
        return ledger::append;
    }
}
~~~

The three beans serve three distinct roles:

- `orderSource` is a Supplier. Each time the poller invokes it, the source retrieves a pending event and returns it to the output binding.
- `enrichOrder` is a Function. It receives `OrderCreated`, calculates an illustrative tax amount, and emits `EnrichedOrder`.
- `recordOrder` is a Consumer. It receives `EnrichedOrder` and writes it to `OrderLedger`.

In this example, `OrderEventSource` must ensure that an event already fetched from the source is not re-emitted endlessly just because the poller invokes it repeatedly. For database-backed sources, use a marking mechanism or a transactional outbox to coordinate event retrieval and publishing state.

### Configuring Function Definition and Bindings

~~~yaml
spring:
  cloud:
    function:
      definition: orderSource;enrichOrder;recordOrder
    stream:
      poller:
        fixed-delay: 1000
      bindings:
        orderSource-out-0:
          destination: orders

        enrichOrder-in-0:
          destination: orders
        enrichOrder-out-0:
          destination: enriched-orders

        recordOrder-in-0:
          destination: enriched-orders
          group: order-ledger
~~~

This configuration specifies:

| Binding | Direction | Destination | Purpose |
|---|---|---|---|
| `orderSource-out-0` | Output | `orders` | Supplier publishes order events |
| `enrichOrder-in-0` | Input | `orders` | Function receives original events |
| `enrichOrder-out-0` | Output | `enriched-orders` | Function publishes enriched results |
| `recordOrder-in-0` | Input | `enriched-orders` | Consumer receives results |

The poller invokes the Supplier at the configured interval. The one-second interval is only an example for a test environment; adjust it according to the data source rate, system load, and acceptable latency. The poller does not generate a new business message if the source has no data to publish.

The Consumer has the group `order-ledger` to maintain a stable subscription. With Kafka, this group maps to a consumer group; with RabbitMQ, the binder typically creates a corresponding queue for the group; with Pulsar, the group is represented by a subscription name. Exact resource names and details depend on the binder.

## 5. Configuring Destination and Group for Each Function Type

Function beans describe only the logic. The destination and group are configured separately on the bindings so the binder knows where to send or receive data.

Example of a Consumer:

~~~yaml
spring:
  cloud:
    function:
      definition: inventory
    stream:
      bindings:
        inventory-in-0:
          destination: orders
          group: inventory
~~~

Example of a Function:

~~~yaml
spring:
  cloud:
    function:
      definition: normalizeOrder
    stream:
      bindings:
        normalizeOrder-in-0:
          destination: raw-orders
          group: order-normalizer
        normalizeOrder-out-0:
          destination: normalized-orders
~~~

Example of a Supplier:

~~~yaml
spring:
  cloud:
    function:
      definition: orderSource
    stream:
      poller:
        fixed-delay: 2000
      bindings:
        orderSource-out-0:
          destination: orders
~~~

Several principles to keep in mind:

- An input binding can use a group to establish a named subscription and stable consumption progress.
- An output binding generally requires a destination; group is a consumer-side property.
- Multiple independent consumers reading the same destination should have separate groups.
- Multiple instances of the same consumer typically share the same group to distribute load.
- Do not rely on the binding name alone to guess the final resource name on the broker; inspect the binder configuration and broker state.

## 6. Payload and Message<T>

Functions can receive or return a payload directly, such as `OrderCreated`, or work with `Message<T>` when header access is needed.

Use a direct payload when the logic only needs business data:

~~~java
@Bean
Function<OrderCreated, EnrichedOrder> enrichOrder() {
    return event -> enrich(event);
}
~~~

Use `Message<T>` when you need to read metadata such as a correlation ID, partition key, or headers sent by the publisher:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Bean
Function<Message<OrderCreated>, Message<EnrichedOrder>> enrichWithHeaders() {
    return message -> {
        OrderCreated event = message.getPayload();
        EnrichedOrder result = enrich(event);

        return MessageBuilder.withPayload(result)
            .copyHeaders(message.getHeaders())
            .setHeader("processedBy", "order-enricher")
            .build();
    };
}
~~~

`Message<T>` consists of a payload and headers. The payload is the primary content; headers contain metadata for routing, correlation, partitioning, or processing. Do not place large business data in headers, and do not copy all headers indiscriminately if they contain information that should not be forwarded.

Similarly, a Supplier can return `Message<T>` to attach metadata when publishing. A Consumer can accept `Message<T>` to inspect headers before processing. When using a plain payload, Spring Cloud Stream and the binder handle message conversion according to the configured content type and message converters.

## 7. Distinguishing Function Beans and StreamBridge

A function bean is a way to declare a source, transformation step, or consumer that is activated and managed as a functional endpoint. `StreamBridge` is appropriate when publishing logic resides inside an imperative call flow, such as after a service completes a business operation.

Example:

~~~java
import org.springframework.cloud.stream.function.StreamBridge;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {

    private final StreamBridge streamBridge;

    public OrderPublisher(StreamBridge streamBridge) {
        this.streamBridge = streamBridge;
    }

    public boolean publish(OrderCreated event) {
        return streamBridge.send("orders-out-0", event);
    }
}
~~~

The output binding `orders-out-0` must point to the appropriate destination. The boolean value returned by `send` reflects the send result through the binding at that step; it does not confirm that every subscriber has received or finished processing the message.

You can choose based on the scenario:

| Need | Approach |
|---|---|
| Periodically read data from a source | Supplier |
| Receive a message, transform it, and publish the result | Function |
| Receive a message and perform a terminal action | Consumer |
| Publish an event immediately during a business call | StreamBridge |

Both approaches can coexist in the same application. What matters is that the output binding name used in code matches the configuration.

## 8. Testing Function Beans

Function logic can be tested without starting a broker. Because the beans return Java functional interfaces, unit tests can invoke them directly.

Example of testing a Function:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.function.Function;

import org.junit.jupiter.api.Test;

class OrderFunctionTest {

    @Test
    void enrichesOrder() {
        Function<OrderCreated, EnrichedOrder> function =
            event -> new EnrichedOrder(
                event.eventId(),
                event.orderId(),
                event.total(),
                event.total().multiply(new BigDecimal("0.10")),
                Instant.parse("2026-01-01T00:00:00Z")
            );

        OrderCreated input = new OrderCreated(
            "evt-1",
            "order-1",
            new BigDecimal("100.00"),
            Instant.parse("2026-01-01T00:00:00Z")
        );

        EnrichedOrder output = function.apply(input);

        assertEquals("order-1", output.orderId());
        assertEquals(new BigDecimal("10.0000"), output.tax());
    }
}
~~~

In real tests, instantiate the bean from the configuration or extract business logic into a service to avoid rewriting the same algorithm in the test. The example above only illustrates calling a Function using `apply`.

Testing levels should include:

1. **Unit test:** verify Supplier, Function, and Consumer logic; check input/output data and business side effects.
2. **Spring context test:** initialize the Application Context to verify that beans have the right names and are recognized by Spring.
3. **Binding test:** use the test binder to verify that functions are activated, bindings have the right names, and payloads pass through.
4. **Broker integration test:** run the appropriate broker to verify destinations, groups, converters, and actual binder behavior.

When testing a Supplier, control the data source to prevent the poller from continuously emitting unintended messages. For a Consumer, test both successful processing and exception-throwing scenarios.

## 9. Common Errors When Declaring Function Beans

| Symptom | Possible Cause | Resolution |
|---|---|---|
| No binding created | Function bean is not activated or definition is incorrect | Check the bean name and `spring.cloud.function.definition` |
| Binding has a different name than configured | Actual bean name differs from the expected method name | Check the name declared in `@Bean` |
| Supplier does not emit messages | Supplier is not polled, source has no data, or output binding is wrong | Check the poller, source logic, and output binding |
| Function receives data but produces no output | Function errors out, returns null, or output binding is misconfigured | Check logs, return value, and destination |
| Consumer does not receive messages | Function is not activated, destination/group is wrong, or broker is not connected | Check function definition, input binding, and binder logs |
| Consumer receives data of the wrong type | Content type or message converter is incompatible | Check payload type, schema, and content type configuration |
| Multiple functions are skipped | Definition does not list all functions that need to run | Explicitly list the functions in the definition |
| Messages are emitted repeatedly | Supplier re-reads the same data or source does not mark items as fetched | Design an event-fetching mechanism that prevents duplicate emission |
| Consumer performs duplicate actions | Messages may be redelivered after an error or restart | Design an idempotent handler and use an event ID |

When a function does not behave as expected, check in order: whether Spring creates the bean, whether the function is activated, whether the binding is created, whether the binder connects, and finally whether messages pass through the endpoint. Checking layer by layer helps isolate the issue to the exact component.

## 10. Practice Workflow

Create a small application with three function beans to process order events:

1. Declare the `OrderCreated` and `EnrichedOrder` records.
2. Declare a `Supplier<OrderCreated>` named `orderSource` to fetch pending events from a data source.
3. Declare a `Function<OrderCreated, EnrichedOrder>` named `enrichOrder` to enrich the information.
4. Declare a `Consumer<EnrichedOrder>` named `recordOrder` to store the result.
5. Declare `spring.cloud.function.definition` containing all three functions.
6. Configure `orderSource-out-0`, `enrichOrder-in-0`, `enrichOrder-out-0`, and `recordOrder-in-0` with their corresponding destinations.
7. Set a stable group for the Consumer.
8. Run unit tests for each function, then run the application with the test binder.
9. Send a sample event and verify the input data, output data, and Consumer side effect.
10. Try swapping the binder in a test environment and verify whether the function logic needs changes or only connection reconfiguration.

The expected outcome is that you can explain why a Supplier creates an output binding, a Function has both input and output bindings, and a Consumer has only an input binding, while determining binding names based on bean names and configuration.

## Conclusion

The functional model helps Spring Cloud Stream applications express event processing with familiar Java signatures. A Supplier produces data, a Function transforms data, and a Consumer receives data and performs an action. The `@Bean` method provides the function name; Spring Cloud Stream uses that name to create default bindings, and the binder connects bindings to destinations on the broker.

When organizing an application, explicitly declare the function definition, configure the right binding names, destinations, and groups, and choose between raw payloads or `Message<T>` based on metadata needs. By keeping business logic inside independent functions and letting the binder handle connectivity, the application can target Kafka, RabbitMQ, or Pulsar with less coupling to broker-specific details.
