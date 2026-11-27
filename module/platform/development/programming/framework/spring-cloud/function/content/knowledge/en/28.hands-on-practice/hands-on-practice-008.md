# Using FunctionFlowBuilder in a Spring Integration Flow

## 1. Practice Problem

In **Spring Cloud Function** (**SPRING_CLOUD_FUNCTION**), we package business logic into **Supplier**, **Function**, and **Consumer** beans so they can be reused across multiple invocation environments. **FunctionCatalog** registers and looks up functional beans, while Spring Integration provides message channels, endpoints, and Enterprise Integration Patterns to connect processing steps into a flow.

In this lesson, we build an order-processing flow:

1. A message enters the **ordersInput** channel.
2. **wireTap** sends a copy of the raw message to an observation channel.
3. **normalizeOrder** normalizes the order ID.
4. **validateOrder** validates the data.
5. **calculateTotal** calculates the total price.
6. **storeOrder** receives the result and records it into an observation queue in the lab.

We will use **FunctionFlowBuilder** to wire functional beans by name in **FunctionCatalog**:

~~~text
Message<OrderCommand>
       |
       v
  ordersInput
       |
       +-----------------------> rawOrdersChannel
       |                           (wireTap)
       v
 normalizeOrder
       |
       v
 validateOrder
       |
       v
 calculateTotal
       |
       v
   storeOrder
       |
       v
 BlockingQueue<PricedOrder>
~~~

**Goal:** understand how Spring Cloud Function and the Spring Integration DSL work together, practice **from**, **fromSupplier**, **apply**, and **accept** operations, and test an `IntegrationFlow` running inside a real Spring context.

After this lesson, you will be able to:

- Explain the roles of **FunctionFlowBuilder** and **FunctionFlowDefinition**.
- Look up `Supplier`, `Function`, and `Consumer` by name from `FunctionCatalog`.
- Build an `IntegrationFlow` starting from a message channel.
- Chain multiple functions with `apply` and composition.
- End a flow with a `Consumer` via `accept`.
- Use `wireTap` to observe messages without altering the main branch payload.
- Distinguish `DirectChannel` from `QueueChannel`.
- Test the flow with Spring Boot Test and `FunctionCatalog`.
- Use `fromSupplier` with a poller when generating messages on a schedule.

## 2. What Is FunctionFlowBuilder?

Spring Integration provides a Java DSL to declare an **IntegrationFlow** using endpoints like `transform`, `filter`, `handle`, `route`, `wireTap`, `log`, and `channel`. Spring Cloud Function adds the **spring-cloud-function-integration** module so this DSL can look up functional beans via **FunctionCatalog**.

Since Spring Cloud Function **4.0.3**, the integration module provides **FunctionFlowBuilder**. Spring auto-configures the builder and wires it to `FunctionCatalog`. You can inject the builder into a `@Bean` method to declare an `IntegrationFlow`.

Core operations:

| API | Role |
| --- | --- |
| **from(channelName)** | Starts the flow from a Spring Integration channel |
| **fromSupplier(supplierName)** | Looks up a `Supplier` in `FunctionCatalog` as the source |
| **apply(functionName)** | Looks up a `Function` and adds it to the flow |
| **accept(consumerName)** | Looks up a `Consumer` and adds it as the terminal handler |
| **wireTap(channelName)** | Sends a copy of the message to a secondary channel |
| **log(level)** | Adds a logging endpoint |

`FunctionFlowBuilder` returns a flow definition that supports the Spring Integration DSL. When you call **apply("normalizeOrder")**, the builder looks up the function with that name in `FunctionCatalog`; you do not have to inject the bean manually or write a service activator by hand.

### 2.1. FunctionFlowBuilder vs. IntegrationFlowBuilder

These two concepts are related but serve different roles:

- **IntegrationFlowBuilder** is Spring Integration's general-purpose DSL for declaring message flows.
- **FunctionFlowBuilder** adds entry points and operators that look up functional beans via `FunctionCatalog`.
- **FunctionFlowDefinition** extends the `IntegrationFlow` DSL, providing `apply` and `accept`.

This allows you to interleave Spring Cloud Function beans with standard Spring Integration endpoints:

~~~java
return functionFlowBuilder
        .from("ordersInput")
        .wireTap("rawOrdersChannel")
        .apply("normalizeOrder")
        .apply("calculateTotal")
        .log(LoggingHandler.Level.INFO)
        .accept("storeOrder");
~~~

This is a single flow. Functions are resolved by name in the catalog, while `wireTap` and `log` are Spring Integration endpoints.

### 2.2. When Should You Use FunctionFlowBuilder?

Use `FunctionFlowBuilder` when:

- The application already declares business logic as functional beans.
- You want to assemble functions by name, including compositions.
- You want to leverage message channels, pollers, `wireTap`, routers, or Enterprise Integration Patterns.
- You want to integrate functions supplied by external libraries or auto-configuration.

If a flow uses only standard Spring Integration endpoints and does not need to look up functions from `FunctionCatalog`, the standard `IntegrationFlow` DSL works well. `FunctionFlowBuilder` is helpful when bridging the two models.

## 3. Preparing the Maven Project

The lab uses **JDK 17**, **Maven 3.9+**, **Spring Boot 3.5.0**, and **Spring Cloud 2025.0.0**. The Spring Cloud BOM manages Spring Cloud Function module versions. For new projects, pick a release train compatible with your Spring Boot version and keep supported patches up to date.

Create the directory:

~~~text
function-flow-builder-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/flowlab/
    │   │   ├── FlowLabApplication.java
    │   │   ├── OrderCommand.java
    │   │   ├── NormalizedOrder.java
    │   │   ├── PricedOrder.java
    │   │   ├── OrderFunctions.java
    │   │   └── OrderIntegrationConfiguration.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/flowlab/
            ├── OrderFunctionsTest.java
            └── OrderIntegrationFlowTest.java
~~~

All Java classes use package **com.example.flowlab**.

### 3.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>function-flow-builder-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>function-flow-builder-lab</name>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>2025.0.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-function-context</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-function-integration</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-integration</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Dependency roles:

| Artifact | Role |
| --- | --- |
| **spring-cloud-function-context** | `FunctionCatalog` and functional beans |
| **spring-cloud-function-integration** | `FunctionFlowBuilder` and integration auto-configuration |
| **spring-boot-starter-integration** | Spring Integration channels, endpoints, and Java DSL |
| **spring-boot-starter-test** | JUnit 5, Spring Boot Test, and assertions |

The **spring-cloud-function-integration** module already pulls in required Spring Integration dependencies transitively. We declare the integration starter explicitly in this example to make clear that the application uses the Spring Integration DSL.

## 4. Creating the Order Models

### 4.1. OrderCommand.java

~~~java
package com.example.flowlab;

public record OrderCommand(
        String orderId,
        int quantity,
        long unitPriceVnd) {
}
~~~

This is the input payload sent by upstream systems into the channel.

### 4.2. NormalizedOrder.java

~~~java
package com.example.flowlab;

public record NormalizedOrder(
        String orderId,
        int quantity,
        long unitPriceVnd) {
}
~~~

Intermediate type after normalizing the order ID.

### 4.3. PricedOrder.java

~~~java
package com.example.flowlab;

public record PricedOrder(
        String orderId,
        int quantity,
        long unitPriceVnd,
        long totalVnd,
        String status) {
}
~~~

Result type received by the final consumer. Defining distinct types for each step lets the functions' generic signatures express the data contract.

## 5. Declaring Functional Beans

Create **OrderFunctions.java**:

~~~java
package com.example.flowlab;

import java.util.Locale;
import java.util.concurrent.BlockingQueue;
import java.util.function.Consumer;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderFunctions {

    @Bean
    public Function<OrderCommand, NormalizedOrder> normalizeOrder() {
        return command -> {
            if (command == null) {
                throw new IllegalArgumentException(
                        "order command is required");
            }
            if (command.orderId() == null
                    || command.orderId().isBlank()) {
                throw new IllegalArgumentException(
                        "orderId is required");
            }

            return new NormalizedOrder(
                    command.orderId().trim().toUpperCase(Locale.ROOT),
                    command.quantity(),
                    command.unitPriceVnd());
        };
    }

    @Bean
    public Function<NormalizedOrder, NormalizedOrder> validateOrder() {
        return order -> {
            if (order.quantity() <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
            if (order.unitPriceVnd() <= 0) {
                throw new IllegalArgumentException(
                        "unitPriceVnd must be positive");
            }
            return order;
        };
    }

    @Bean
    public Function<NormalizedOrder, PricedOrder> calculateTotal() {
        return order -> {
            long total = Math.multiplyExact(
                    order.unitPriceVnd(),
                    order.quantity());

            return new PricedOrder(
                    order.orderId(),
                    order.quantity(),
                    order.unitPriceVnd(),
                    total,
                    "ACCEPTED");
        };
    }

    @Bean
    public Consumer<PricedOrder> storeOrder(
            BlockingQueue<PricedOrder> processedOrders) {
        return processedOrders::add;
    }
}
~~~

The beans:

| Bean | Signature | Responsibility |
| --- | --- | --- |
| **normalizeOrder** | `Function<OrderCommand, NormalizedOrder>` | Normalizes the order ID |
| **validateOrder** | `Function<NormalizedOrder, NormalizedOrder>` | Validates quantity and unit price |
| **calculateTotal** | `Function<NormalizedOrder, PricedOrder>` | Calculates total price and produces the result |
| **storeOrder** | `Consumer<PricedOrder>` | Receives the final result and writes to the observation queue |

### 5.1. Why Is the Consumer at the End of the Flow?

A `Consumer` accepts a payload without returning a new payload. Therefore, **accept("storeOrder")** is the appropriate terminal step for this flow.

If further processing is required after storing, design a function that returns a result or publish a message to another channel. Do not expect a `Consumer` to return `PricedOrder` so you can chain another `apply` step after it.

### 5.2. Overflow Protection

Multiplying quantity and unit price uses **Math.multiplyExact**. If the product exceeds `long` limits, Java throws `ArithmeticException` instead of silently returning an overflowed number.

In real applications, clearly define currency units, quantity caps, and maximum prices. This lab uses integer VND to stay focused on the integration flow.

## 6. Configuring Spring Integration Channels

Create **OrderIntegrationConfiguration.java**:

~~~java
package com.example.flowlab;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;

import org.springframework.cloud.function.context.integration.FunctionFlowBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration(proxyBeanMethods = false)
public class OrderIntegrationConfiguration {

    @Bean
    public DirectChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel rawOrdersChannel() {
        return new QueueChannel();
    }

    @Bean
    public BlockingQueue<PricedOrder> processedOrders() {
        return new LinkedBlockingQueue<>();
    }

    @Bean
    public IntegrationFlow orderProcessingFlow(
            FunctionFlowBuilder functionFlowBuilder) {

        return functionFlowBuilder
                .from("ordersInput")
                .wireTap("rawOrdersChannel")
                .apply("normalizeOrder|validateOrder")
                .apply("calculateTotal")
                .accept("storeOrder");
    }
}
~~~

### 6.1. Analyzing the Flow Configuration

**from("ordersInput")**

Spring Integration begins receiving messages from the channel bean named **ordersInput**. Because it is a `DirectChannel`, messages are dispatched synchronously to the flow's subscriber on the sender's thread.

**wireTap("rawOrdersChannel")**

`wireTap` sends a copy of the message to a secondary channel for observation or auditing. The main branch continues processing the original payload.

**apply("normalizeOrder|validateOrder")**

`FunctionFlowBuilder` looks up the composition in `FunctionCatalog`. The output of `normalizeOrder` is `NormalizedOrder`, matching the input type of `validateOrder`. Both functions are combined into a single step.

**apply("calculateTotal")**

Looks up the pricing function and appends it after the preceding composition.

**accept("storeOrder")**

Looks up the `Consumer` in the catalog and terminates the flow with that consumer.

### 6.2. Why Must Function Names Match Exactly?

The names passed to `apply` and `accept` are the registered functional bean names:

~~~text
normalizeOrder
validateOrder
calculateTotal
storeOrder
~~~

`FunctionFlowBuilder` relies on `FunctionCatalog` for lookup. If a name is wrong, a bean is missing from the catalog, or type signatures are incompatible, the flow will fail to build or start properly.

### 6.3. Why Use Composition Inside apply?

`FunctionCatalog` supports composition by name. The expression:

~~~text
normalizeOrder|validateOrder
~~~

means `normalizeOrder`'s output feeds into `validateOrder`'s input. The pipe character is Spring Cloud Function's composition syntax, not a channel separator.

You can also write two separate `apply` calls:

~~~java
.apply("normalizeOrder")
.apply("validateOrder")
~~~

Both forms express the same business sequence. Composition helps group function steps into a single reusable definition when desired.

## 7. Initializing Spring Boot

Create **FlowLabApplication.java**:

~~~java
package com.example.flowlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FlowLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(FlowLabApplication.class, args);
    }
}
~~~

Create **src/main/resources/application.yml**:

~~~yaml
spring:
  application:
    name: function-flow-builder-lab
  cloud:
    function:
      single-function-fallback-enabled: false
~~~

Because we look up functions explicitly by name inside the flow, we do not need to set **spring.cloud.function.definition** for this lab. That property is typically used when another adapter like Spring Cloud Stream needs to pick which function or composition to bind.

## 8. Unit Testing Functions Independently

Create **OrderFunctionsTest.java**:

~~~java
package com.example.flowlab;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class OrderFunctionsTest {

    private final OrderFunctions functions = new OrderFunctions();

    @Test
    void normalizesOrderId() {
        NormalizedOrder result = functions.normalizeOrder().apply(
                new OrderCommand(" o-801 ", 2, 150_000L));

        assertEquals(
                new NormalizedOrder("O-801", 2, 150_000L),
                result);
    }

    @Test
    void validatesQuantity() {
        NormalizedOrder invalid =
                new NormalizedOrder("O-802", 0, 100L);

        assertThrows(
                IllegalArgumentException.class,
                () -> functions.validateOrder().apply(invalid));
    }

    @Test
    void calculatesTotal() {
        PricedOrder result = functions.calculateTotal().apply(
                new NormalizedOrder("O-803", 3, 250_000L));

        assertEquals(
                new PricedOrder(
                        "O-803", 3, 250_000L, 750_000L, "ACCEPTED"),
                result);
    }

    @Test
    void detectsAmountOverflow() {
        NormalizedOrder tooLarge =
                new NormalizedOrder("O-804", 2, Long.MAX_VALUE);

        assertThrows(
                ArithmeticException.class,
                () -> functions.calculateTotal().apply(tooLarge));
    }

    @Test
    void catalogStyleCompositionHasCompatibleTypes() {
        Function<OrderCommand, NormalizedOrder> normalize =
                functions.normalizeOrder();
        Function<NormalizedOrder, NormalizedOrder> validate =
                functions.validateOrder();

        NormalizedOrder result =
                normalize.andThen(validate).apply(
                        new OrderCommand(" o-805 ", 1, 50_000L));

        assertEquals("O-805", result.orderId());
    }
}
~~~

These unit tests verify each function and type compatibility between the first two steps. They do not test `FunctionCatalog` or `IntegrationFlow`.

## 9. Testing FunctionCatalog and IntegrationFlow

Create **OrderIntegrationFlowTest.java**:

~~~java
package com.example.flowlab;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.concurrent.BlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.function.Function;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.function.context.FunctionCatalog;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@SpringBootTest(classes = FlowLabApplication.class)
class OrderIntegrationFlowTest {

    @Autowired
    private FunctionCatalog functionCatalog;

    @Autowired
    private DirectChannel ordersInput;

    @Autowired
    private QueueChannel rawOrdersChannel;

    @Autowired
    private BlockingQueue<PricedOrder> processedOrders;

    @BeforeEach
    void clearQueues() {
        processedOrders.clear();
        while (rawOrdersChannel.receive(0) != null) {
            // Drain any leftover observation messages from prior tests.
        }
    }

    @Test
    void functionsAreRegisteredInCatalog() {
        Function<OrderCommand, NormalizedOrder> normalize =
                functionCatalog.lookup("normalizeOrder");
        Function<NormalizedOrder, NormalizedOrder> validate =
                functionCatalog.lookup("validateOrder");
        Function<NormalizedOrder, PricedOrder> calculate =
                functionCatalog.lookup("calculateTotal");

        assertNotNull(normalize);
        assertNotNull(validate);
        assertNotNull(calculate);
    }

    @Test
    void catalogCanResolveFunctionComposition() {
        Function<OrderCommand, NormalizedOrder> normalizeAndValidate =
                functionCatalog.lookup("normalizeOrder|validateOrder");

        assertNotNull(normalizeAndValidate);

        NormalizedOrder result = normalizeAndValidate.apply(
                new OrderCommand(" o-901 ", 2, 100_000L));

        assertEquals(
                new NormalizedOrder("O-901", 2, 100_000L),
                result);
    }

    @Test
    void integrationFlowAppliesFunctionsAndAcceptsConsumer()
            throws InterruptedException {

        OrderCommand command =
                new OrderCommand(" o-902 ", 3, 250_000L);

        Message<OrderCommand> message = MessageBuilder
                .withPayload(command)
                .setHeader("correlationId", "corr-902")
                .build();

        assertTrue(ordersInput.send(message));

        PricedOrder result = processedOrders.poll(
                1, TimeUnit.SECONDS);

        assertNotNull(result);
        assertEquals(
                new PricedOrder(
                        "O-902", 3, 250_000L, 750_000L, "ACCEPTED"),
                result);

        Message<?> tapped = rawOrdersChannel.receive(1_000);
        assertNotNull(tapped);
        assertEquals(command, tapped.getPayload());
        assertEquals(
                "corr-902",
                tapped.getHeaders().get("correlationId"));
    }

    @Test
    void invalidOrderDoesNotReachTheConsumer() {
        OrderCommand invalid =
                new OrderCommand("O-903", 0, 250_000L);

        Message<OrderCommand> message =
                MessageBuilder.withPayload(invalid).build();

        assertThrows(
                RuntimeException.class,
                () -> ordersInput.send(message));

        assertTrue(processedOrders.isEmpty());
    }
}
~~~

### 9.1. What Do the Tests Prove?

| Test | What Is Verified |
| --- | --- |
| **functionsAreRegisteredInCatalog** | Functional beans are registered in `FunctionCatalog` |
| **catalogCanResolveFunctionComposition** | Catalog resolves pipe-separated composition |
| **integrationFlowAppliesFunctionsAndAcceptsConsumer** | Message travels from channel through function chain to `Consumer` |
| **invalidOrderDoesNotReachTheConsumer** | Validation failure halts the flow before the final consumer |

The flow test uses **DirectChannel** to send messages synchronously. When `send` returns, synchronous endpoints have already processed the message or thrown an exception. The trailing consumer writes `PricedOrder` into `BlockingQueue` so the test can read the result.

### 9.2. Verifying wireTap

The test retrieves a message from **rawOrdersChannel** and verifies:

- The payload is still the original `OrderCommand`.
- The `correlationId` header is preserved on the observation branch.
- The main branch still proceeds through normalization, validation, and calculation.

`wireTap` does not replace the main branch. If the observation channel fills up or is unconsumed, design capacity and handling policies to fit operational needs.

### 9.3. Why Does the Exception Test Catch RuntimeException?

Spring Integration may wrap exceptions thrown by endpoints in a messaging-layer exception. Accordingly, flow tests can assert `RuntimeException` to confirm message failure, while unit tests on `validateOrder` still assert the exact business `IllegalArgumentException`.

## 10. DirectChannel vs. QueueChannel

Spring Integration uses channels to connect producers and consumers. The two channels in this lab have different semantics:

| Characteristic | DirectChannel | QueueChannel |
| --- | --- | --- |
| Type | `SubscribableChannel` | `PollableChannel` |
| Sending a message | Invokes subscriber on sender thread | Enqueues message into a queue |
| Processing | Usually synchronous | Consumer fetches messages via `receive`/poller |
| Best suited for | Flow entry points needing immediate processing | Buffering, observation, or decoupling producer/consumer pace |
| In this lab | `ordersInput` | `rawOrdersChannel` |

### 10.1. DirectChannel

`DirectChannel` dispatches messages to subscribers on the caller's thread. This is convenient for simple flow tests where you call `send` and immediately inspect results.

In production, synchronous execution ties `send` duration to downstream processing latency. To decouple load or run asynchronously, consider `ExecutorChannel` or a broker adapter with appropriate concurrency tuning.

### 10.2. QueueChannel

`QueueChannel` buffers messages in memory for a consumer to receive later. In this lab, it serves as the `wireTap` branch for inspecting inputs.

`QueueChannel` does not turn into a durable message broker on its own. Messages in an in-memory queue lack durability across process restarts; if durability or cross-instance distribution is required, use a proper broker/adapter.

## 11. Using fromSupplier to Create a Message Source

`FunctionFlowBuilder` also provides **fromSupplier** to look up a `Supplier` from `FunctionCatalog`. Choose this when the flow starts from an application-generated source instead of an inbound message channel.

Example `Supplier` declaration:

~~~java
import java.util.function.Supplier;

@Bean
public Supplier<OrderCommand> demoOrderSupplier() {
    return () -> new OrderCommand(
            "O-DEMO",
            2,
            125_000L);
}
~~~

You can create a poller-driven flow:

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.integration.dsl.Pollers;

@Bean
@Profile("polling-demo")
public IntegrationFlow supplierOrderFlow(
        FunctionFlowBuilder functionFlowBuilder) {

    return functionFlowBuilder
            .fromSupplier(
                    "demoOrderSupplier",
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(5_000)))
            .apply("normalizeOrder|validateOrder")
            .apply("calculateTotal")
            .accept("storeOrder");
}
~~~

This flow invokes the `Supplier` every 5 seconds. It reuses the same functions and consumer as the channel-driven flow. The **polling-demo** profile ensures the periodic flow runs only when explicitly requested:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=polling-demo
~~~

Keep this profile disabled during the main flow tests because the poller will periodically emit sample orders and mutate queue state.

### 11.1. What Does the Poller Mean?

A `Supplier` has no input channel to receive messages on its own. A poller is the mechanism that triggers a `MessageSource`/`Supplier` on a schedule. Depending on the source:

- Use `fixedDelay` to wait a fixed interval after the previous poll completes.
- Use `fixedRate` to run on a fixed periodic cadence.
- Use a custom trigger for complex schedules.

The `Supplier` generates data; the poller decides when to invoke the `Supplier`. Those are two separate responsibilities.

### 11.2. Infinite Suppliers and Finite Sources

An ordinary `Supplier` can return one value per invocation. A reactive supplier such as `Supplier<Flux<T>>` can represent a stream. When a `Supplier` returns a finite stream and needs re-polling, inspect the poller mechanism and framework semantics carefully rather than assuming Spring Cloud Function automatically re-polls every reactive `Supplier`.

## 12. Using IntegrationFlow DSL Beyond apply/accept

`FunctionFlowBuilder` still lets you use standard Spring Integration endpoints.

### 12.1. Adding log

~~~java
import org.springframework.integration.handler.LoggingHandler;

return functionFlowBuilder
        .from("ordersInput")
        .apply("normalizeOrder|validateOrder")
        .log(LoggingHandler.Level.INFO)
        .apply("calculateTotal")
        .accept("storeOrder");
~~~

The logging endpoint helps observe the message flow. In production, log only required metadata and avoid logging full payloads if they contain sensitive data.

### 12.2. Adding transform

If you need auxiliary data transformation outside a functional bean, use `transform`:

~~~java
return functionFlowBuilder
        .from("ordersInput")
        .apply("normalizeOrder|validateOrder")
        .<NormalizedOrder, String>transform(
                order -> order.orderId() + ":" + order.quantity())
        .accept("storeOrderSummary");
~~~

In this example, a `Consumer` named **storeOrderSummary** accepting `String` must exist. The output type of `transform` must match the input type of the final `Consumer`.

### 12.3. Adding filter

You can use `filter` to drop messages that fail a condition:

~~~java
import org.springframework.integration.core.MessageSelector;

return functionFlowBuilder
        .from("ordersInput")
        .filter((MessageSelector) message ->
                message.getHeaders().containsKey("correlationId"))
        .apply("normalizeOrder|validateOrder")
        .apply("calculateTotal")
        .accept("storeOrder");
~~~

`filter` checks the message/headers before entering the functions. Filtered-out messages stop following the main branch; clarify whether you need a discard channel or audit trail for rejected messages.

### 12.4. Composition in accept

`FunctionFlowDefinition.accept` also uses `FunctionCatalog`, so you can pass a composition ending with a `Consumer`:

~~~java
return functionFlowBuilder
        .from("ordersInput")
        .accept("normalizeOrder|validateOrder|calculateTotal|storeOrder");
~~~

`FunctionCatalog` looks up the entire chain as a single definition ending in the `Consumer`. However, in longer flows, separate `apply` calls make intermediate integration points like `wireTap`, `filter`, `log`, or routers clearly visible.

## 13. Controlling Errors in IntegrationFlow

In this lab, validation throws `IllegalArgumentException` when quantity or unit price is invalid. The exception may be wrapped at the Spring Integration messaging layer.

A production flow must decide:

- Should a failing message halt the current flow?
- Should failed messages go to an error channel?
- Should transient failures be retried?
- Should permanently invalid data move to quarantine or a dead-letter destination?
- Should the trailing consumer be skipped when an earlier step fails?

### 13.1. Error Channel

Spring Integration supports error channels to route flow failures to dedicated error-handling endpoints. You can declare an error channel and a subscriber to log or record metadata:

~~~java
@Bean
public QueueChannel orderErrors() {
    return new QueueChannel();
}
~~~

When configuring error handling, wire the flow/endpoint errors to the proper channel using Spring Integration's error-channel mechanisms or the global error channel. Never just create a `QueueChannel` and assume exceptions automatically flow into it.

### 13.2. Do Not Retry Every Error

For example:

| Error | Typical Policy to Consider |
| --- | --- |
| Missing `orderId` | Reject without retry |
| Negative quantity | Reject without retry |
| Temporary database disconnect | Bounded retry |
| Service call timeout | Retry with timeout/backoff |
| Unreadable schema | Quarantine/DLQ, notify producer |
| Duplicate delivery to consumer | Idempotency |

Unbounded retries can trap bad messages in the flow and block valid traffic. Set retry limits, backoff intervals, and dead-letter destinations.

### 13.3. Consumers with Side Effects

The **storeOrder** consumer in this lab only writes to a `BlockingQueue`. If replaced with a database or external API:

- Define clear transaction boundaries.
- Use idempotency keys to guard against duplicate processing.
- Never assume `wireTap` and the main branch share an atomic transaction.
- When a flow triggers multiple side effects, consider outbox or saga patterns.

## 14. FunctionFlowBuilder and FunctionCatalog

`FunctionFlowBuilder` uses `FunctionCatalog` to look up functions by name. Consequently, functional beans must have stable names and compatible input/output types.

### 14.1. Direct Function Lookup

~~~java
Function<NormalizedOrder, PricedOrder> calculate =
        functionCatalog.lookup("calculateTotal");
~~~

### 14.2. Composition Lookup

~~~java
Function<OrderCommand, NormalizedOrder> normalizeAndValidate =
        functionCatalog.lookup("normalizeOrder|validateOrder");
~~~

### 14.3. Consumer Lookup

~~~java
Consumer<PricedOrder> store =
        functionCatalog.lookup("storeOrder");
~~~

The flow DSL performs these lookups on your behalf. Direct catalog tests are useful for confirming bean registration before debugging integration endpoints.

### 14.4. FunctionCatalog Uses Wrappers

`FunctionCatalog` may return functions instrumented by the framework to support type conversion, composition, and other features. Therefore, when invoking functions through the catalog, verify behavior and data types rather than comparing runtime implementation classes against the raw bean.

## 15. Distinguishing FunctionFlowBuilder from Configured Composition

There are two ways to combine functions:

| Approach | Example | When Appropriate |
| --- | --- | --- |
| Composition in `FunctionCatalog` | `normalizeOrder\|validateOrder\|calculateTotal` | When you want a single composite function definition |
| `FunctionFlowBuilder` DSL | `from → wireTap → apply → log → apply → accept` | When mixing functions with channels, endpoints, and EIPs |

Pure composition focuses on connecting function inputs to outputs. `FunctionFlowBuilder` lets you interleave Spring Integration endpoints between steps.

Example:

~~~java
return functionFlowBuilder
        .from("ordersInput")
        .wireTap("rawOrdersChannel")
        .apply("normalizeOrder|validateOrder")
        .log(LoggingHandler.Level.INFO)
        .apply("calculateTotal")
        .accept("storeOrder");
~~~

Here, `wireTap` and `log` are not business functions; they are integration flow endpoints.

## 16. Running and Testing the Project

Inside **function-flow-builder-lab**, run:

~~~bash
java -version
mvn -version
mvn test
~~~

Tests expected to pass:

| Group | Result |
| --- | --- |
| `OrderFunctionsTest` | Normalization, validation, pricing, and overflow detection |
| `FunctionCatalog` test | Function and composition lookup succeeds |
| `IntegrationFlow` test | Message travels from channel to final `Consumer` |
| `WireTap` test | Observation branch receives original payload and headers |
| Negative test | Invalid data does not reach the `Consumer` |

To observe logs when running the application:

~~~bash
mvn spring-boot:run
~~~

In default mode, the application does not generate orders automatically. The flow waits for messages sent to **ordersInput**. To send messages from code or another adapter, use the channel/gateway or add an appropriate inbound adapter.

## 17. Extension Exercises

### Exercise A — Adding an enrichCustomer Function

Create `Function<NormalizedOrder, EnrichedOrder> enrichCustomer` to attach customer tier or customer metadata.

**Requirements:**

- Add the `EnrichedOrder` record.
- Register the function bean.
- Insert `apply("enrichCustomer")` before `calculateTotal`.
- Verify input/output type compatibility across all stages.

### Exercise B — Adding an Audit Consumer

Create `Consumer<PricedOrder> auditOrder` to record order IDs and totals into a separate `BlockingQueue`.

**Requirements:** use `wireTap` or a dedicated channel branch if auditing should remain independent of the main consumer. Analyze what happens if auditing fails.

### Exercise C — Using fromSupplier

Create `Supplier<OrderCommand> demoOrderSupplier` and a flow polling every 10 seconds.

**Requirements:** enable the flow only under a dedicated profile; verify the `Supplier` generates messages and the flow reuses the `normalizeOrder|validateOrder` composition.

### Exercise D — Adding a Header-Based Filter

Allow only messages whose `sourceSystem` header equals `PARTNER-A` to enter the function chain.

**Requirements:** test accepted and dropped messages; define how discarded messages are observed.

### Exercise E — Adding a Router by Order Type

Add a router or separate channels for priority orders and standard orders.

**Requirements:** describe how routing works with Spring Integration routers, channel names, and target consumers. Keep transport routing logic out of the pricing function.

### Exercise F — Moving from QueueChannel to a Broker

Replace the `DirectChannel` source with a RabbitMQ or Kafka inbound adapter.

**Requirements:** keep all functional beans intact; test header mapping, retries, DLQ, and idempotency through the broker.

## 18. Common Errors and Troubleshooting

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| Cannot inject `FunctionFlowBuilder` | Missing `spring-cloud-function-integration` or auto-config disabled | Check dependencies and Spring context |
| `FunctionFlowBuilder` cannot find function | Wrong bean name or bean is not functional | Check `@Bean` and `FunctionCatalog` |
| `apply` composition reports type error | Prior function output incompatible with next input | Check generic signatures for every stage |
| `accept` cannot find consumer | Wrong consumer name or unregistered bean | Check catalog lookup |
| Flow receives no messages | Wrong channel name or channel bean missing | Check `from("ordersInput")` and bean names |
| `QueueChannel` never delivers messages | No poller/consumer reading the queue | Distinguish `QueueChannel` from `DirectChannel` |
| `DirectChannel.send` blocks for long time | Downstream executes synchronously and slowly | Consider `ExecutorChannel` or broker decoupling |
| `wireTap` receives no data | Wrong channel name or channel is not a bean | Check `rawOrdersChannel` |
| Consumer receives wrong payload type | Incompatible generics or missing converter | Check `Function`/`Consumer` signatures |
| Poller emits messages too frequently | Misconfigured `fixedDelay`/`fixedRate` | Adjust poller and concurrency limits |
| Tests polluted by periodic Supplier | Polling flow active in test context | Use `@Profile` or `@ConditionalOnProperty` |
| `FunctionCatalog.lookup` returns null | Function not registered or excluded from catalog | Check bean names and `ineligible-definitions` |
| Exceptions bypass expected error channel | Endpoint/flow error handling not wired | Configure error channel and test separately |
| Audit runs while main flow fails | `wireTap` is a separate branch, not a transaction | Design idempotency and error policies |

### 18.1. Debugging Sequence

1. Verify JDK and Maven.
2. Confirm `spring-cloud-function-integration` is on the classpath.
3. Confirm Spring creates `FunctionFlowBuilder`.
4. Look up each functional bean via `FunctionCatalog`.
5. Look up the composition to verify type compatibility.
6. Verify channel beans and names passed to `from`/`wireTap`.
7. Send a message directly through `DirectChannel`.
8. Inspect outputs in the consumer queue and `wireTap` `QueueChannel`.
9. Only then add pollers, inbound adapters, or brokers.

## 19. Completion Criteria

| Criterion | Evidence |
| --- | --- |
| `FunctionFlowBuilder` available | Spring context injects builder successfully |
| Functional beans | `normalizeOrder`, `validateOrder`, `calculateTotal`, and `storeOrder` |
| `FunctionCatalog` | Looks up functions and compositions by name |
| `IntegrationFlow` | `from` channel, `apply` functions, and `accept` consumer |
| Enterprise Integration Pattern | `wireTap` observes raw messages |
| Channel semantics | Distinguishes `DirectChannel` from `QueueChannel` |
| `Supplier` source | Understands `fromSupplier` and pollers |
| Error handling | Invalid data never reaches the trailing consumer |
| Testing | Unit tests and Spring Boot `IntegrationFlow` tests pass |
| Limitations understood | `QueueChannel` is in-memory, not a durable broker |

**Summary:** `FunctionFlowBuilder` bridges Spring Cloud Function's `FunctionCatalog` with Spring Integration's `IntegrationFlow` DSL. Use `from` or `fromSupplier` to define entry points, `apply` to look up and chain `Function` beans, and `accept` to finish with a `Consumer`. You can interleave `wireTap`, `log`, `filter`, and other Spring Integration endpoints to build a structured message flow while keeping business logic inside reusable functional beans.

## 20. Self-Check Questions

**Question 1.** Which module provides `FunctionFlowBuilder`?

**Answer:** `spring-cloud-function-integration`.

**Question 2.** Where does `FunctionFlowBuilder` obtain `Function` and `Consumer` beans from?

**Answer:** From `FunctionCatalog` using the definition name passed to `apply` or `accept`.

**Question 3.** Where does `from("ordersInput")` start the flow?

**Answer:** From the Spring Integration channel named `ordersInput`.

**Question 4.** How does `fromSupplier` differ from `from`?

**Answer:** `from` starts from a declared channel or message source; `fromSupplier` looks up a `Supplier` in `FunctionCatalog` as the source, usually paired with a poller.

**Question 5.** What does `apply("normalizeOrder|validateOrder")` mean?

**Answer:** Looks up a composition of two functions where `normalizeOrder`'s output feeds into `validateOrder`'s input.

**Question 6.** Does `accept("storeOrder")` forward a payload to subsequent steps in the flow?

**Answer:** No. A `Consumer` accepts a payload and returns no value, so it is normally the terminal step.

**Question 7.** Does `wireTap` alter the main branch's payload?

**Answer:** No. It sends a copy of the message to a secondary channel for observation.

**Question 8.** How does `DirectChannel` differ from `QueueChannel`?

**Answer:** `DirectChannel` invokes subscribers synchronously on the sender's thread; `QueueChannel` buffers messages in a queue for a consumer to receive later.

**Question 9.** Does `QueueChannel` guarantee messages survive an application restart?

**Answer:** No. It is an in-memory queue; a broker or persistence adapter is required for durability.

## References

- [Spring Cloud Function 4.3 — Spring Integration Interaction](https://docs.spring.io/spring-cloud-function/reference/4.3/spring-integration.html)
- [Spring Cloud Function — Programming Model and FunctionCatalog](https://docs.spring.io/spring-cloud-function/reference/4.3/spring-cloud-function/programming-model.html)
- [Spring Integration — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html)
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html)
- [Spring Integration — Wire Tap](https://docs.spring.io/spring-integration/reference/channel/interceptors.html)
- [Spring Integration — Pollers](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Java 17 — Supplier, Function, and Consumer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/package-summary.html)
