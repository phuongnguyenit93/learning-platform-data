# IntegrationFlow

## 1. Objectives and Context

In the **Java DSL** chapter of the **SPRING_INTEGRATION_CORE** module, this lesson presents how to use `IntegrationFlow` to design and declare a message flow. The focus is on the relationship between `Message`, `MessageChannel`, endpoint, and gateway; transformations, filtering, routing, and aggregation are components that can be composed into the flow.

After this lesson, you will be able to:

- Read a flow and identify its input, processing steps, and output.
- Declare a flow as a Spring bean and send messages to the right channel.
- Distinguish DSL configuration from the runtime processing of each message.
- Design the reply path and error path for a request sent through a gateway.
- Test the behavior of a flow using Spring Test and JUnit.

The main example is a quote service: it receives a quantity as a string, normalizes it, parses it into an integer, rejects non-positive quantities, and calculates the total amount. The fixed unit price is for illustration only; this lesson does not model taxes, discounts, or payment logic.

The examples use the `IntegrationFlow.from(...)` syntax from Spring Integration 6 and later. Use a JDK and dependency set compatible with your project's Spring version. Snippets marked as variants are standalone alternatives, not configurations to register simultaneously.

## 2. What Does IntegrationFlow Describe?

`IntegrationFlow` describes how channels and endpoints are wired together into a flow. The builder collects the configuration; `IntegrationFlowBeanPostProcessor` processes that configuration to register the components into the Spring container. At runtime, messages travel through the created channels and handlers. The `@Bean` method does not run again for each request. This mechanism is described in the [Java DSL documentation](https://docs.spring.io/spring-integration/reference/dsl.html).

| Component | Role in the quote example |
| --- | --- |
| `Message` | Carries the quantity or result along with metadata |
| `MessageChannel` | Connects the sender with the next receiving step |
| Handler | Performs work such as parsing a string into a number |
| Endpoint | Attaches the handler to the message-receiving mechanism and manages its execution |
| Gateway | Provides a Java method to invoke the messaging system |
| `IntegrationFlow` | Declares the structure connecting the components above |

A flow can represent many Enterprise Integration Patterns, not necessarily just a linear sequence. In the DSL, commonly used verbs correspond to the following components. See [DSL Basics](https://docs.spring.io/spring-integration/reference/dsl/java-basics.html).

| Method | Component / Purpose |
| --- | --- |
| `transform(...)` | Transformer: changes the data representation |
| `filter(...)` | Filter: lets a message proceed or rejects it |
| `handle(...)` | Service activator: invokes processing |
| `route(...)` | Router: selects the route |
| `split(...)` | Splitter: splits a message |
| `aggregate(...)` | Aggregator: groups messages |
| `bridge(...)` | Bridge: forwards messages between channels |

To learn flow structure, we start with a linear path. When adding a router or aggregator, you also need to define the contract of each branch and the group completion condition.

## 3. Reading the Declarative Structure

A builder declaration looks like this:

~~~java
@Bean
IntegrationFlow sampleFlow() {
    return IntegrationFlow.from("sample.input")
            .<String, String>transform(String::trim)
            .<String>filter(value -> !value.isEmpty())
            .<String>handle((payload, headers) -> "Received: " + payload)
            .get();
}
~~~

This snippet illustrates the structure and is not yet the complete quote configuration.

- `from(...)` defines the entry point.
- The calls in the middle declare endpoints or channels.
- `get()` finishes the builder and returns the object describing the flow.

Here, `get()` does not receive a message, does not wait for a result, and does not trigger a business request. The bean name `sampleFlow` is also not the channel name `sample.input`.

With `from("sample.input")`, the DSL looks up a channel with that name; if none exists yet, the DSL can create a `DirectChannel`. Adjacent endpoints are connected by default with a direct channel. This resolution behavior is described in [Message Channels in Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java-channels.html).

You can declare the channel explicitly and pass the object to `from(...)` to make the input contract clear:

~~~java
@Bean(name = "sample.input")
DirectChannel sampleInput() {
    return new DirectChannel();
}

@Bean
IntegrationFlow sampleFlow(
        @Qualifier("sample.input") DirectChannel input) {

    return IntegrationFlow.from(input)
            .<String, String>transform(String::trim)
            .get();
}
~~~

The two snippets in this section are alternatives. Do not register both `sampleFlow` beans in the same context.

## 4. Complete Example: Quote Flow

### 4.1. Dependencies and Structure

If the project already uses Spring Boot with a matching parent or BOM, you can declare:

~~~xml
<dependencies>
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
~~~

Keep dependency management consistent with the project. For a plain Spring application, `spring-integration-core` is required; the testing section below requires Spring Test and JUnit Jupiter.

The example consists of `QuoteGateway.java`, `QuoteFlowConfiguration.java`, and a runner class, all located in the `example.integration` package.

~~~mermaid
flowchart LR
    A["Caller: quote(rawQuantity)"] --> G["QuoteGateway"]
    G --> C["quote.input"]
    C --> T1["trim: String → String"]
    T1 --> T2["parse: String → Integer"]
    T2 --> F{"quantity > 0?"}
    F -- Yes --> H["Calculate total: Integer → BigDecimal"]
    H --> R["replyChannel"]
    R --> G
    G --> O["Return BigDecimal to caller"]
    F -- No --> E["MessageRejectedException"]
~~~

The diagram only shows the input channel and the reply channel. The intermediate consecutive steps are also connected by channels created by the DSL.

### 4.2. Gateway as the Application Entry Point

File `QuoteGateway.java`:

~~~java
package example.integration;

import java.math.BigDecimal;

import org.springframework.integration.annotation.MessagingGateway;

@MessagingGateway(
        defaultRequestChannel = "quote.input",
        defaultRequestTimeout = "1000",
        defaultReplyTimeout = "1000")
public interface QuoteGateway {

    BigDecimal quote(String rawQuantity);
}
~~~

The application calls `quote(" 3 ")` like a regular Java method. The gateway proxy creates a request message and converts the reply result into a `BigDecimal`.

The example uses `@Import(QuoteGateway.class)` in the configuration below to register the proxy, an approach supported since Spring Integration 6. Another option is `@IntegrationComponentScan` for interfaces annotated with `@MessagingGateway`. See [Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html#gateway-configuration-annotations).

### 4.3. Declaring the Channel and Processing Steps

File `QuoteFlowConfiguration.java`:

~~~java
package example.integration;

import java.math.BigDecimal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration(proxyBeanMethods = false)
@EnableIntegration
@Import(QuoteGateway.class)
public class QuoteFlowConfiguration {

    private static final BigDecimal UNIT_PRICE =
            new BigDecimal("120000");

    @Bean(name = "quote.input")
    public DirectChannel quoteInput() {
        return new DirectChannel();
    }

    @Bean
    public IntegrationFlow quoteFlow() {
        return IntegrationFlow.from("quote.input")
                .<String, String>transform(
                        String::trim,
                        endpoint -> endpoint.id("quote.trim"))
                .<String, Integer>transform(
                        Integer::valueOf,
                        endpoint -> endpoint.id("quote.parse"))
                .<Integer>filter(
                        quantity -> quantity > 0,
                        endpoint -> endpoint
                                .id("quote.positiveQuantity")
                                .throwExceptionOnRejection(true))
                .handle(
                        Integer.class,
                        (quantity, headers) ->
                                UNIT_PRICE.multiply(
                                        BigDecimal.valueOf(quantity)),
                        endpoint -> endpoint
                                .id("quote.calculateTotal")
                                .requiresReply(true))
                .get();
    }
}
~~~

`@EnableIntegration` provides the Spring Integration infrastructure in this Java configuration context. Each `id(...)` names the corresponding endpoint, making it easier to identify the processing stage when observing or testing. The endpoint configuration lambda is also where you configure pollers, lifecycle, and advice when needed. See [DSL and Endpoint Configuration](https://docs.spring.io/spring-integration/reference/dsl/java-endpoints.html).

In the final step, `handle(Integer.class, ...)` receives the payload and headers; `Integer.class` specifies the input type for the lambda. The return value is the processing result forwarded as a reply message. Handler forms and notes on lambda types are described in [Service Activators and the handle() method](https://docs.spring.io/spring-integration/reference/dsl/java-handle.html).

### 4.4. Calling Through a Spring Context

File `QuoteDemo.java`:

~~~java
package example.integration;

import java.math.BigDecimal;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class QuoteDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                QuoteFlowConfiguration.class)) {

            QuoteGateway gateway = context.getBean(QuoteGateway.class);
            BigDecimal total = gateway.quote(" 3 ");

            System.out.println(total); // Expected: 360000
        }
    }
}
~~~

Progression of the request:

| Stage | Payload | Type |
| --- | --- | --- |
| Request message | `" 3 "` | `String` |
| After `quote.trim` | `"3"` | `String` |
| After `quote.parse` | `3` | `Integer` |
| After filter | `3` | `Integer` |
| After `quote.calculateTotal` | `360000` | `BigDecimal` |
| Value returned by gateway | `360000` | `BigDecimal` |

The filter keeps accepted messages unchanged. For inputs `"0"` or `"-2"`, `throwExceptionOnRejection(true)` causes the request to be rejected with an error instead of continuing. If the filter simply drops the message, a caller waiting for a response will not receive a successful result from that branch. See [Filter](https://docs.spring.io/spring-integration/reference/filter.html).

## 5. Data Contracts Along Each Segment of the Flow

Lambda generics help write type-safe code, but the entire `IntegrationFlow` is not an end-to-end compiler-verified generic pipeline. A channel can receive messages from multiple sources. Therefore, every boundary still needs a contract for payload types, required headers, and behavior on invalid data.

In the example:

- The gateway accepts an integer string, possibly with leading or trailing whitespace.
- The transformer normalizes it before parsing.
- `"abc"`, `"1.5"`, or numbers outside the `Integer` range do not pass the parse step.
- Non-positive quantities are rejected by the filter.
- Every valid quantity reaches the handler that produces a `BigDecimal`.

If the business rules require a maximum quantity, that condition must be added explicitly; the current example only checks greater than 0.

A `Message` consists of a payload and headers. The headers structure does not allow direct modification via `put(...)`; the immutability of the message wrapper also does not make an arbitrary payload object immutable. When constructing a replacement message manually, preserve the metadata required for the reply path and tracking. See [Message](https://docs.spring.io/spring-integration/reference/message.html).

Do not use `message.getHeaders().getId()` as a fixed business identifier across transformations. The quote example can use a dedicated `quoteRequestId` header to track the request, while `replyChannel` indicates where to send the reply.

## 6. Ways to Choose the Entry Point

### 6.1. Receiving Messages on an Existing Channel

The main example uses:

~~~java
IntegrationFlow.from("quote.input")
~~~

This approach fits when a gateway, another flow, or an internal producer already knows the target channel to send to. Naming channels after business contracts helps connect parts without depending on flow bean names.

### 6.2. Letting the DSL Create a Gateway from an Interface

A standalone variant can start from an interface:

~~~java
@Bean
IntegrationFlow inlineQuoteFlow() {
    return IntegrationFlow.from(
                    QuoteGateway.class,
                    gateway -> gateway.beanName("inlineQuoteGateway"))
            .<String, String>transform(String::trim)
            .<String, Integer>transform(Integer::valueOf)
            .<Integer>filter(
                    quantity -> quantity > 0,
                    endpoint -> endpoint.throwExceptionOnRejection(true))
            .handle(
                    Integer.class,
                    (quantity, headers) ->
                            new BigDecimal("120000")
                                    .multiply(BigDecimal.valueOf(quantity)))
            .get();
}
~~~

The types used here are `IntegrationFlow`, `BigDecimal`, and `QuoteGateway` already used in the main example. This bean is placed in an alternative configuration with `@EnableIntegration` and without importing the gateway again.

With `from(QuoteGateway.class, ...)`, the DSL creates the gateway and an internal channel wired into the first step. The request channel on the interface annotation is replaced by that internal channel. Do not use this variant together with the gateway registration in section 4. See [IntegrationFlow as a Gateway](https://docs.spring.io/spring-integration/reference/dsl/integration-flow-as-gateway.html).

### 6.3. Creating Messages from a Polling Source

A flow can actively pull data from a `Supplier`:

~~~java
@Bean
IntegrationFlow heartbeatFlow() {
    return IntegrationFlow.fromSupplier(
                    () -> "heartbeat",
                    source -> source.poller(
                            Pollers.fixedDelay(Duration.ofSeconds(5))
                                    .maxMessagesPerPoll(1)))
            .handle(message -> {
                System.out.println(message.getPayload());
            })
            .get();
}
~~~

This snippet requires adding imports for `java.time.Duration` and `org.springframework.integration.dsl.Pollers`, placed in a configuration with `@EnableIntegration`.

The source is polled on a schedule; the supplier's result is wrapped in a message if it is not already one. The final handler only consumes, so this flow uses one-way communication. See [Inbound Channel Adapters](https://docs.spring.io/spring-integration/reference/dsl/java-inbound-adapters.html).

This is a scheduled emitter, which differs from a caller invoking a gateway and waiting for a quote.

## 7. Channels Determine Execution Behavior

Java DSL does not automatically make every step asynchronous. Changing the channel type can change the processing thread, when control returns to the producer, and how errors are received.

| Channel type | Characteristics to consider |
| --- | --- |
| `DirectChannel` | Invokes one subscriber on the message-sending thread |
| `QueueChannel` | Buffers messages for a consumer to retrieve; requires a receiving mechanism |
| `ExecutorChannel` | Hands off dispatching to an executor; behavior also depends on the executor |
| `PublishSubscribeChannel` | Broadcasts to subscribers; can be configured with an executor |

A standard `QueueChannel` uses memory rather than durable storage. Enqueuing and successful processing happen at two different points in time. A bounded queue also introduces the possibility of blocking sends when full. See [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

### 7.1. The Poller Belongs to the Queue Consumer

The standalone example below receives integers via a queue and doubles them:

~~~java
package example.integration;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

@Configuration(proxyBeanMethods = false)
@EnableIntegration
public class QueuedNumberConfiguration {

    @Bean(name = "numbers.input")
    public QueueChannel numbersInput() {
        return new QueueChannel(100);
    }

    @Bean(name = "numbers.output")
    public QueueChannel numbersOutput() {
        return new QueueChannel(100);
    }

    @Bean
    public IntegrationFlow numberFlow(
            @Qualifier("numbers.input") QueueChannel input,
            @Qualifier("numbers.output") QueueChannel output) {

        return IntegrationFlow.from(input)
                .handle(
                        Integer.class,
                        (number, headers) -> number * 2,
                        endpoint -> endpoint
                                .id("numbers.double")
                                .poller(Pollers
                                        .fixedDelay(Duration.ofMillis(100))
                                        .maxMessagesPerPoll(5)))
                .channel(output)
                .get();
    }
}
~~~

The poller is configured on the `numbers.double` endpoint because this endpoint must pull messages from `numbers.input`. The output queue is for a receiver that actively calls `receive(...)`; another polling endpoint is not needed if the caller itself retrieves the result.

`fixedDelay` configures the polling schedule, while `maxMessagesPerPoll` limits how many messages are fetched/processed per poll cycle, not the number of threads. The DSL infrastructure provides `Pollers` to configure metadata for polling endpoints. See [Pollers](https://docs.spring.io/spring-integration/reference/dsl/java-pollers.html).

In a test snippet with a `context` created from `QueuedNumberConfiguration`:

~~~java
QueueChannel input = context.getBean(
        "numbers.input", QueueChannel.class);
QueueChannel output = context.getBean(
        "numbers.output", QueueChannel.class);

boolean accepted = input.send(
        new org.springframework.messaging.support.GenericMessage<>(21),
        1000);

org.springframework.messaging.Message<?> result = output.receive(2000);
// Expected: accepted == true; result is non-null; payload == 42.
~~~

Do not interpret `accepted == true` as a guarantee that the result `42` is already produced. When receiving the result, check for `null` and use an appropriate timeout.

## 8. Ending a Flow, Replies, and Errors

### 8.1. The Endpoint Must Match the Calling Contract

The quote flow ends with a handler that returns a value and specifies no output channel, so the reply can return to the request's `replyChannel`. The gateway sets up the reply path to collect the result.

If you replace the final handler with a consumer that only logs, there will no longer be a `BigDecimal` result for `quote(...)`. Similarly, adding an explicit output channel means the result goes to that channel; you must design a path back to the gateway if you want to keep the request–reply contract.

A handler returning `null` can also cause the reply to be lost. `requiresReply(true)` in the main example helps detect cases where the quote handler fails to produce a reply. It does not force a filter that rejected a message to produce a result.

### 8.2. Timeouts Do Not Interrupt Synchronous Handlers

`requestTimeout` applies when sending to a potentially blocking channel; `replyTimeout` bounds the reply-waiting phase. If all processing runs on the caller thread over direct channels, the reply timeout does not interrupt a slow handler. HTTP or database calls still need timeouts at their respective clients. See [Gateway Behavior When No Response Arrives](https://docs.spring.io/spring-integration/reference/gateway.html#gateway-no-response).

For quotes, explicitly choose the business outcome for each case: return the total amount, return a rejection response according to your data model, or raise an error. Do not use a timeout to represent a rule like "quantity must be greater than 0".

### 8.3. Error Paths Depend on Execution Boundaries

In the synchronous quote configuration, errors can propagate back through the gateway call. When processing moves to an asynchronous task or a scheduled poller, you cannot rely on the sender's call stack.

Spring Integration's error-handling infrastructure can send an `ErrorMessage` to the channel specified by the `errorChannel` header or to the global error channel. Simply declaring a flow listening on `errorChannel` does not mean all synchronous exceptions will automatically route there. See [Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html).

For this example, distinguish the following cases:

| Situation | Origin | Interpretation |
| --- | --- | --- |
| `"abc"` | `quote.parse` | Invalid input format |
| `"0"` | `quote.positiveQuantity` | Quantity rule violation |
| Handler returns no result | `quote.calculateTotal` | Reply contract violation |
| Error in a queue-backed flow | Message-receiving task | Must observe the task's error path |

Endpoint names help correlate errors with processing steps. When adding retries, apply them only to recoverable errors and consider side effects; re-parsing the same string `"abc"` will not make the data valid.

## 9. Testing the Flow Contract

The following tests use a real Spring context with the quote configuration and connect to no external services. They verify the result, data rejection, and preservation of business headers.

Spring Integration supports testing on top of Spring Test; `spring-integration-test` provides additional utilities when you need to mock or control components inside a flow. This small example only needs Spring Test and JUnit Jupiter. See [Testing Support](https://docs.spring.io/spring-integration/reference/testing.html).

File `QuoteFlowTest.java`:

~~~java
package example.integration;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.MessageRejectedException;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringJUnitConfig(QuoteFlowConfiguration.class)
class QuoteFlowTest {

    @Autowired
    private QuoteGateway gateway;

    @Autowired
    @Qualifier("quote.input")
    private MessageChannel input;

    @Test
    void calculatesTotalAfterTrimming() {
        assertEquals(
                new BigDecimal("360000"),
                gateway.quote(" 3 "));
    }

    @Test
    void rejectsNonPositiveQuantity() {
        RuntimeException error = assertThrows(
                RuntimeException.class,
                () -> gateway.quote("0"));

        assertTrue(hasCause(error, MessageRejectedException.class));
    }

    @Test
    void rejectsInvalidNumber() {
        RuntimeException error = assertThrows(
                RuntimeException.class,
                () -> gateway.quote("abc"));

        assertTrue(hasCause(error, NumberFormatException.class));
    }

    @Test
    void repliesToSuppliedChannelAndPreservesBusinessHeader() {
        QueueChannel replies = new QueueChannel(1);

        Message<String> request = MessageBuilder
                .withPayload(" 2 ")
                .setHeader("quoteRequestId", "Q-1001")
                .setReplyChannel(replies)
                .build();

        assertTrue(input.send(request, 1000));

        Message<?> reply = replies.receive(1000);
        assertNotNull(reply);
        assertEquals(new BigDecimal("240000"), reply.getPayload());
        assertEquals("Q-1001", reply.getHeaders().get("quoteRequestId"));
    }

    private static boolean hasCause(
            Throwable error,
            Class<? extends Throwable> expectedType) {

        for (Throwable current = error;
                current != null;
                current = current.getCause()) {
            if (expectedType.isInstance(current)) {
                return true;
            }
        }
        return false;
    }
}
~~~

The two error tests check the cause chain because the wrapper exception may differ between the call site and the handler. They still require the exact cause type, rather than accepting just any error.

The last test sends a message directly to the channel, allowing it to verify metadata as well. The `QueueChannel` used to capture the reply in the test does not need a poller: the test calls `receive(1000)` itself. A finite timeout ensures the test terminates cleanly if the reply path is broken.

This is test code for learners to practice with; the article does not include compilation or execution results from a sample project.

## 10. Organizing and Managing Flows

### 10.1. Separating Wiring Configuration from Business Processing

When the calculation grows into substantial business logic, move it into a dedicated service and inject the service into the `@Bean` method. For example, with a `pricingService` bean that has a `calculate(Integer quantity)` method returning `BigDecimal`:

~~~java
.handle(
        pricingService,
        "calculate",
        endpoint -> endpoint
                .id("quote.calculateTotal")
                .requiresReply(true))
~~~

This snippet replaces the total calculation step in the main flow. The flow expresses the order of normalization, validation, and service invocation; the service contains the pricing rules. This separation lets you test business logic independently and change wiring without packing all processing into a long lambda.

Declare shared channels as separate beans and inject them into the flows that need them. Avoid creating multiple distinct channel objects that are meant to represent a single common junction.

### 10.2. Distinguishing Sequential Wiring from Calling a Sub-flow with Reply

`channel("another.input")` forwards the message to a channel. When you need to call a sub-flow, wait for its result, and continue to the next step, you can use `gateway("another.input")`. This is an operator inside the DSL, distinct from the gateway interface that the application calls. See [Operator gateway()](https://docs.spring.io/spring-integration/reference/dsl/java-gateway.html).

Before reusing a sub-flow, verify whether it always replies. A branch that only logs does not satisfy the caller's contract waiting for a result.

### 10.3. Lifecycle and Dynamic Registration

A flow declared as a `@Bean` is managed by Spring. The associated components support lifecycle operations; starting and stopping the flow is delegated to those components. Do not call the flow creation method again to "send another message". See [DSL Basics](https://docs.spring.io/spring-integration/reference/dsl/java-basics.html).

If the application genuinely needs to create or remove flows at runtime, `IntegrationFlowContext` provides a registration and management mechanism. Dynamic registration requires clear names and releasing the registration when it is no longer used. The fixed quote example does not need this mechanism yet. See [Dynamic and Runtime Integration Flows](https://docs.spring.io/spring-integration/reference/dsl/java-runtime-flows.html).

## 11. Mistakes to Spot When Reading an IntegrationFlow

| Symptom | What to check |
| --- | --- |
| Builder exists, but no messages are received | Has the flow been registered in the context and has integration infrastructure been enabled? |
| Sending to the bean name `quoteFlow` | Producers need to send to the channel `quote.input` |
| Gateway waits and returns no result | Is a filter dropping the message, a handler returning `null`, or a branch not producing a reply? |
| Replaced direct channel with queue and flow stops running | Does the first consumer after the queue have a poller or appropriate receiving mechanism? |
| Send to queue succeeds, but business logic fails | Have you observed the consumer's result and error path? |
| Added a global error-catching flow, but caller still gets exceptions | Is the error occurring synchronously on the caller's thread? |
| Wrong payload type mid-flow | Are the contracts at the input and each transformation clearly defined? |

When expanding the example to real orders, you can add a router to choose processing paths or a splitter–aggregator to compute per line item. Each addition should describe its input, output, rejected branch, and reply condition. That is the foundation for using Java DSL to design integration patterns in the Spring Integration Core module while keeping flows easy to read and test.
