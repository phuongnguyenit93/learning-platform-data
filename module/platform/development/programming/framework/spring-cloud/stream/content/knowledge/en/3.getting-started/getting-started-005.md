# Building Your First Application to Emit, Transform, and Consume Messages

Spring Cloud Stream enables applications to exchange events through a broker using a functional programming model. Instead of manually managing a Kafka, RabbitMQ, or Pulsar client in each component, you declare a message-emitting function, a transformation function, and a message-consuming function. Bindings connect the functions to destinations; the binder handles communication with the specific broker.

In this lesson, you will build a simple order-processing pipeline:

1. Supplier creates an `OrderCreated` event and emits it to the `orders.created` destination.
2. Function receives the event, validates the data, produces an `OrderValidated` event, and emits it to `orders.validated`.
3. Consumer receives `OrderValidated` and records the result.

The example uses the Kafka binder to demonstrate running it. The function and binding structure remains the foundation when switching to RabbitMQ or a compatible Pulsar binder.

## 1. Preparing the Project

Spring Cloud Stream runs on Spring Boot. Before adding dependencies, select a compatible Spring Boot version and Spring Cloud release train from the Spring Cloud compatibility table. Use the Spring Cloud BOM to manage Spring Cloud library versions and avoid manually pairing incompatible versions.

Example dependencies section in `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
    id 'io.spring.dependency-management' version '<dependency-management-version>'
}

ext {
    set('springCloudVersion', '<compatible-spring-cloud-release-train>')
}

dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}"
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.cloud:spring-cloud-starter-stream-kafka'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.cloud:spring-cloud-stream-test-binder'
}
~~~

The version values in the example are placeholders to fill in with the versions chosen for your project. Do not copy an old release train onto a new Spring Boot version without checking compatibility.

If using Maven, declare `spring-cloud-dependencies` inside `dependencyManagement`, then add `spring-cloud-starter-stream-kafka` and the corresponding test dependencies. For RabbitMQ, replace the Kafka starter with `spring-cloud-starter-stream-rabbit`. For Pulsar, choose a Pulsar binder whose version is published as compatible with the Spring Cloud Stream version in use; check that binder's exact artifact and connection properties rather than assuming all binders share the same broker properties.

The application needs a Spring Boot startup class:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StreamGettingStartedApplication {

    public static void main(String[] args) {
        SpringApplication.run(StreamGettingStartedApplication.class, args);
    }
}
~~~

## 2. Declaring Event Data

A message needs a clear contract so producer and consumer understand the same data. For the order example, we use two Java records:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

record OrderCreated(
        String orderId,
        String customerId,
        BigDecimal total) {
}

record OrderValidated(
        String orderId,
        String customerId,
        BigDecimal total,
        String status,
        Instant validatedAt) {
}
~~~

`OrderCreated` describes an order-created event. `OrderValidated` is the result after the validation step. These two data types illustrate the message schema; when services have independent deployment lifecycles, manage contracts using schemas or event API documentation with compatibility rules rather than relying on sharing a Java class.

Place the records in the same package as the configuration and test classes. You can keep them in one file as non-public top-level records as shown, or split them into two separate files and declare each record `public`.

## 3. Writing Supplier, Function, and Consumer

Spring Cloud Stream recognizes function beans by standard Java types in `java.util.function`:

- `Supplier<T>` takes no input and produces data to emit.
- `Function<T, R>` takes a value of type `T`, processes it, and returns a result of type `R`.
- `Consumer<T>` takes data of type `T` and performs an action without emitting output.

Declare the three beans in a configuration class:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderFunctions {

    private final AtomicLong sequence = new AtomicLong();

    @Bean
    public Supplier<OrderCreated> orderSource() {
        return () -> {
            long number = sequence.incrementAndGet();
            return new OrderCreated(
                    "ORD-%04d".formatted(number),
                    "CUSTOMER-01",
                    new BigDecimal("125.50"));
        };
    }

    @Bean
    public Function<OrderCreated, OrderValidated> validateOrder() {
        return order -> {
            if (order.orderId() == null || order.orderId().isBlank()) {
                throw new IllegalArgumentException("orderId is required");
            }
            if (order.total() == null || order.total().signum() <= 0) {
                throw new IllegalArgumentException("total must be positive");
            }
            return new OrderValidated(
                    order.orderId(),
                    order.customerId(),
                    order.total(),
                    "VALIDATED",
                    Instant.now());
        };
    }

    @Bean
    public Consumer<OrderValidated> auditOrder() {
        return order -> System.out.printf(
                "Validated order %s for %s: %s%n",
                order.orderId(),
                order.customerId(),
                order.status());
    }
}
~~~

`orderSource` is an illustrative data source. Spring Cloud Stream invokes the `Supplier` via a poller and emits the returned value to the output binding. The default poller typically invokes the supplier every one second; you can adjust the polling interval with the appropriate Spring Integration configuration. In a real application, a supplier can pull data from an existing source or emit events after business logic completes. Do not use an in-memory counter as an order identifier in a multi-instance system; each instance would have its own counter. Use a unique identifier generated by the business system.

`validateOrder` receives the event and returns the result. When the function throws an exception, the binding and binder error-handling mechanism decides whether to retry or route the error according to configuration. This example only illustrates synchronous validation; do not place slow operations or non-idempotent side effects inside a function without designing a delivery policy.

`auditOrder` receives the validated result. In a real application, the consumer can write data to a database or call another service. If a message is redelivered, the operation needs to be safe when executed multiple times.

## 4. Connecting Functions to Destinations

Spring Cloud Stream generates default binding names based on the bean name and data direction:

| Bean | Binding | Direction |
|---|---|---|
| orderSource | orderSource-out-0 | Supplier output |
| validateOrder | validateOrder-in-0 | Function input |
| validateOrder | validateOrder-out-0 | Function output |
| auditOrder | auditOrder-in-0 | Consumer input |

Create `src/main/resources/application.yml`:

~~~yaml
spring:
  cloud:
    function:
      definition: orderSource;validateOrder;auditOrder
    stream:
      bindings:
        orderSource-out-0:
          destination: orders.created
          content-type: application/json

        validateOrder-in-0:
          destination: orders.created
          group: order-validator
          content-type: application/json

        validateOrder-out-0:
          destination: orders.validated
          content-type: application/json

        auditOrder-in-0:
          destination: orders.validated
          group: order-audit
          content-type: application/json

      kafka:
        binder:
          brokers: localhost:9092
~~~

The `spring.cloud.function.definition` property lists the function beans to activate. Semicolons separate independent functions; they are not composed into a single function. Each function has its own bindings and is connected to the broker through destinations:

- `orderSource-out-0` emits messages to `orders.created`.
- `validateOrder-in-0` reads from `orders.created`; the function processes them and sends results through `validateOrder-out-0` to `orders.validated`.
- `auditOrder-in-0` reads from `orders.validated`.

`content-type: application/json` declares the payload format. Spring Cloud Stream uses message converters to convert between messages and the Java types declared by the function. Producer and consumer must agree on the schema and data representation; setting the content type alone does not guarantee two application versions are compatible.

`group` specifies the consumer group name for an input binding. Multiple instances running with `order-validator` share the load of processing the `orders.created` stream; another group can independently read the same destination. `order-audit` is a separate group on `orders.validated`. Setting a stable group allows the broker to track progress via its native mechanism and supports multi-instance deployment.

## 5. Starting and Observing the First Flow

Before running the application, start Kafka and make sure the broker is reachable at `localhost:9092`. If the broker does not auto-create topics, pre-create `orders.created` and `orders.validated` with an appropriate partition count. In development, you can use a local broker or container; deployment environments need broker addresses, authentication credentials, and connection encryption configured per infrastructure policy.

Run the application with Gradle:

~~~bash
./gradlew bootRun
~~~

On Windows, you can run `gradlew.bat bootRun`. Once the application starts successfully, the supplier begins emitting events periodically. The function reads `orders.created`, validates the payload, and emits the result to `orders.validated`. The consumer reads the result and prints logs similar to:

~~~text
Validated order ORD-0001 for CUSTOMER-01: VALIDATED
Validated order ORD-0002 for CUSTOMER-01: VALIDATED
~~~

The order names and sequence numbers in the log are illustrative data only. If no logs appear, check in this order:

1. Is the broker running and can the application connect to the configured address?
2. Do the `orders.created` and `orders.validated` topics exist or is auto-creation allowed?
3. Does `spring.cloud.function.definition` match the names of all three beans?
4. Do binding names match the bean names and `-in-0` / `-out-0` suffixes exactly?
5. Are producer and consumer using the same destination, content type, and schema?
6. Do the logs show payload conversion, authorization, connection, or message processing errors?

If the application connects to the broker from inside a container, `localhost` usually points to that container itself. In that case, use the internal network hostname or a broker address reachable from the container.

## 6. Choosing a Binder for the Broker

The `Supplier`, `Function`, `Consumer` logic and binding configuration above describe how the application processes messages. The binder translates those bindings into broker-specific resources and operations.

| Broker | Typical mapping | What to check |
|---|---|---|
| Kafka | Destination is a topic; group is a consumer group | Partitions, offsets, number of consumers in the group, and commit policy |
| RabbitMQ | Destination usually maps to an exchange; group maps to the group's queue | Exchange type, routing key, queue, acknowledgement, and dead-lettering |
| Pulsar | Destination is a topic; group maps to a subscription | Subscription type, subscription name, key-based distribution, and cursor |

When switching to RabbitMQ, add the compatible Rabbit binder starter and configure RabbitMQ connectivity for your environment. Keep the binding names and logical destinations if desired; verify that the exchanges and queues created by the binder match the expected routing. For Pulsar, add a compatible binder and configure the service URL, authentication, and subscription according to that binder version's guide.

Do not assume that the same destination name means the same physical structure on every broker. Kafka uses topics and partitions; RabbitMQ typically routes through exchanges to queues; Pulsar manages topics and subscriptions. Inspecting actual broker resources is a required step during deployment.

## 7. Testing Functions and Bindings

Test function logic first, then test messages flowing through bindings. Spring Cloud Stream provides the test binder to test bindings without starting a real broker. Add the `spring-cloud-stream-test-binder` dependency to your project's test configuration.

Example testing `validateOrder` alone using `InputDestination` and `OutputDestination`:

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.stream.binder.test.InputDestination;
import org.springframework.cloud.stream.binder.test.OutputDestination;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest(properties = {
        "spring.cloud.function.definition=validateOrder",
        "spring.cloud.stream.bindings.validateOrder-in-0.destination=orders.in",
        "spring.cloud.stream.bindings.validateOrder-out-0.destination=orders.out"
})
class ValidateOrderBindingTest {

    @Autowired
    InputDestination input;

    @Autowired
    OutputDestination output;

    @Test
    void validatesAnIncomingOrder() {
        OrderCreated event = new OrderCreated(
                "ORD-TEST-1",
                "CUSTOMER-TEST",
                new java.math.BigDecimal("125.50"));

        input.send(
                MessageBuilder.withPayload(event).build(),
                "validateOrder-in-0");

        Message<byte[]> result =
                output.receive(1000, "validateOrder-out-0");

        assertNotNull(result);
        String json = new String(result.getPayload(), StandardCharsets.UTF_8);
        assertTrue(json.contains("ORD-TEST-1"));
        assertTrue(json.contains("VALIDATED"));
    }
}
~~~

This test confirms that a message enters the right binding, is processed by the function, and appears on the output binding. It does not replace integration testing against Kafka, RabbitMQ, or Pulsar. With a real broker, you also need to verify destination creation, consumer groups/subscriptions, distribution across multiple instances, acknowledgements, retries, and dead-lettering.

## 8. Principles to Keep When Moving the Example to Production

The example above clearly shows the flow of emitting, transforming, and consuming messages. When evolving this into a business system, additional decisions are needed:

- **Event identification:** every event needs a stable `eventId` to detect duplicate messages and aid tracing. Do not use an in-memory counter as a global identifier.
- **Schema:** agree on field names, data types, units, required fields, and compatibility rules across producer/consumer versions.
- **Consumer group:** use the same group when instances share the workload of one job; use separate groups when each service needs to receive an independent stream.
- **Partitioning and ordering:** if per-order ordering is needed, use a stable key like `orderId` and verify how the broker distributes messages across partitions or subscriptions.
- **Retry and DLQ:** cap retry attempts for transient errors, route unprocessable messages to quarantine, and establish an investigation/replay workflow.
- **Idempotency:** design consumers to tolerate redelivery. One successful broker delivery does not guarantee that side effects in a database or external API happen only once.
- **Operational observability:** log with `eventId`, destination, and group; monitor latency, backlog depth, processing errors, and DLQ message counts.

`Supplier`, `Function`, and `Consumer` establish three clear roles in a pipeline. Bindings connect those roles to destinations, and the binder connects the application to the chosen broker. Once you understand and test each layer, you can start with a small message flow, scale out to multiple consumer groups, and swap brokers while keeping most business logic intact.
