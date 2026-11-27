# IntegrationFlows and Java DSL

## 1. Objectives and Scope

In the `SPRING_INTEGRATION_CORE` module, Java DSL is a way to use Java code to describe the path of a message through `MessageChannel`s and endpoints. This lesson belongs to the **Java DSL** chapter and focuses on reading, building, and testing an `IntegrationFlow` from input to result or error.

After this lesson, you will be able to:

- Distinguish the `IntegrationFlows` factory in older documentation from the `IntegrationFlow` interface in the newer API.
- Explain what components are created by a chain `from → transform → filter → route → handle`.
- Choose an input via a channel, a gateway, or a polling source.
- Design payload, header, and reply contracts between steps.
- Compose sub-flows, identify thread boundaries, and handle rejected messages.
- Apply `split`, `aggregate`, and write behavioral tests for a flow.

You should know Java lambdas, Spring `@Configuration`, `@Bean`, and the concept of a message consisting of a payload and headers. The main examples use Java 17 and the Spring Integration 6.5.x API as an illustrative baseline; this is a lesson baseline, not a claim of the latest release. When adopting in a project, use the compatible Spring Boot/Spring Integration version set managed by your project.

## 2. How Do IntegrationFlows and IntegrationFlow Differ?

### 2.1. Reading Older Examples

You may encounter configurations like:

~~~java
// Historical syntax; depends on versions that still provide IntegrationFlows.
return IntegrationFlows.from("orders.input")
        .transform(String.class, String::trim)
        .channel("orders.output")
        .get();
~~~

Here `IntegrationFlows` is a factory class providing methods to start a builder; the final value has type `IntegrationFlow`.

Starting with Spring Integration 6.0, `IntegrationFlows` was deprecated in favor of moving the factory methods directly onto the `IntegrationFlow` interface itself. For new code following the API used in this lesson, write `IntegrationFlow.from(...)`. Simply renaming the factory does not guarantee an older application has been fully migrated; check other changes in the target version. See [changes between 5.5 and 6.0](https://docs.spring.io/spring-integration/reference/changes-5.5-6.0.html) and [IntegrationFlows 6.0.3 Javadoc](https://docs.spring.io/spring-integration/docs/6.0.3/api/org/springframework/integration/dsl/IntegrationFlows.html).

~~~java
// Syntax used in this lesson.
return IntegrationFlow.from("orders.input")
        .transform(String.class, String::trim)
        .channel("orders.output")
        .get();
~~~

Both snippets above illustrate how to declare the flow and do not yet have a consumer for `orders.output`. To actually send and receive results, connect that channel to another endpoint or declare it as a `QueueChannel` so it can be read with `receive(...)`.

| Name | Role |
| --- | --- |
| `IntegrationFlows` | Factory in the older API; check your version before using |
| `IntegrationFlow` | Contract describing a flow; also hosts the static factory methods in the newer API |
| `IntegrationFlowBuilder` | Builder collecting channels, handlers, endpoints, and related configuration |
| Java DSL | Way to express topology using Java, a fluent API, and lambdas |

### 2.2. DSL Describes Topology at Initialization Time

A `@Bean` method builds a flow description when Spring creates the application context. Spring Integration processes this description and registers the actual components into the context. When a message arrives, the channels and endpoints execute the work; the framework does not re-run the entire builder chain for every message. This mechanism is described in the [Java DSL reference](https://docs.spring.io/spring-integration/reference/6.5/dsl.html).

~~~mermaid
flowchart LR
    A["@Bean creates IntegrationFlow"] --> B["Spring registers channels and endpoints"]
    B --> C["Context starts"]
    C --> D["Message arrives at channel"]
    D --> E["Endpoint processes message"]
~~~

Example:

~~~java
@Bean
IntegrationFlow textFlow() {
    System.out.println("Declaring flow");

    return IntegrationFlow.from("text.input")
            .transform(String.class, text -> {
                System.out.println("Processing a payload");
                return text.trim();
            })
            .channel("text.output")
            .get();
}
~~~

The first line runs when the bean is created. The lambda inside `transform` runs when the endpoint receives a message. In this example, `get()` completes the builder to return the flow object; it does not send a message, wait for a reply, or pull an item from a source.

## 3. Reading a DSL Chain by Message Contract

### 3.1. Core Verbs

| DSL | Meaning in the flow | Question to answer when designing |
| --- | --- | --- |
| `from(...)` | Defines where the flow starts | Who creates the message and where is it sent? |
| `channel(...)` | Connects to a channel | Does it switch threads or buffer messages? |
| `transform(...)` | Transforms data | What type is the payload after this step? |
| `filter(...)` | Accepts or rejects a message | Where do rejected messages go? |
| `handle(...)` | Calls a handler or business service | Does it produce a reply? |
| `route(...)` | Selects a path | Are all routing keys handled? |
| `split(...)` | Splits one input into multiple messages | What correlation/sequence info does each part carry? |
| `aggregate(...)` | Groups messages into a result | Which group is collected and when is it released? |
| `bridge(...)` | Forwards between channels | How are two flow segments connected? |
| `get()` | Ends construction by the builder | Is the result registered as a bean? |

The verbs map to Spring Integration endpoints such as transformer, filter, and service activator. See [DSL Basics](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-basics.html).

A flow should have a clear contract for every edge:

~~~text
RawOrder
  -> Normalized Order
  -> Order with amount > 0
  -> Receipt by priority/standard lane
  -> Response String
~~~

A flow name cannot replace this contract. If a step changes the payload from `Order` to `Receipt`, the next step must accept `Receipt`, even if the channel name still contains the word "orders".

### 3.2. Does the Lambda Receive the Payload or the Message?

In many overloads, the lambda's argument is the **payload**:

~~~java
.transform(String.class, text -> text.trim())
.handle(String.class, (payload, headers) -> payload.toUpperCase(Locale.ROOT))
~~~

In the two-argument `handle` form, the second parameter provides the headers. Using the snippet above requires importing `java.util.Locale`.

Do not assume that writing the generic `Message<?>` is enough to ask the framework to pass the entire message:

~~~java
// Avoid: the framework may still pass the payload to the lambda.
.<Message<?>, String>transform(message ->
        message.getPayload().toString())
~~~

If you need the full message, choose an overload with an appropriate class token, such as `transform(Message.class, message -> ...)`, or use a handler whose signature explicitly expresses a message-receiving contract. Overload differences and type erasure notes are explained in [DSL Basics, lambdas and Message section](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-basics.html).

When constructing a new `Message` manually, actively preserve headers required by the flow. In particular, losing `replyChannel` can prevent a gateway from receiving the result; losing correlation/sequence headers can prevent an aggregator from grouping messages properly.

## 4. Preparing Dependencies and Bean Registration

In a Spring Boot application with managed versions, the minimal commonly used dependency is:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-integration</artifactId>
</dependency>
~~~

If you are not using Spring Boot, you need `org.springframework.integration:spring-integration-core` and an appropriate Spring configuration. Java DSL is part of Spring Integration core in this lesson's version baseline; you do not need to add the legacy Java DSL artifact just because you saw it in a historical guide.

The testing example below uses JUnit Jupiter, `spring-test`, and JUnit assertions. In a Boot project, you can use `spring-boot-starter-test` in `test` scope. `spring-integration-test` is an optional dependency when you need utilities like mocking integration endpoints, and is not required for this simple gateway testing example.

The method declaring the flow must be managed by Spring:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableIntegration
public class ExampleConfiguration {

    @Bean
    IntegrationFlow exampleFlow() {
        return IntegrationFlow.from("example.input")
                .transform(String.class, String::trim)
                .channel("example.output")
                .get();
    }
}
~~~

`@EnableIntegration` makes the infrastructure configuration explicit when learning with plain Spring. In a Boot application, understand which parts of the infrastructure are already provided by auto-configuration.

Creating a builder in an ordinary Java variable without feeding it into the flow registration mechanism will not create a Spring-managed pipeline. Similarly, do not manually call `getObject()` on `IntegrationComponentSpec` instances inside `@Bean` methods; let the container manage those specs via the `FactoryBean` lifecycle. When sharing a channel across multiple flows, the clearest approach is to declare the channel as its own bean and inject it.

## 5. Complete Example: Receiving and Classifying Orders

### 5.1. Business Requirements

The application receives a request containing an order ID, a priority flag, and an amount as a string. The flow must:

1. Trim extra whitespace and convert the amount to `BigDecimal`.
2. Reject non-positive amounts.
3. Route the order to the `PRIORITY` or `STANDARD` lane.
4. Create a receipt, format it, and return it to the caller.

This example only classifies and creates a receipt in memory. It does not persist orders to a database, call a shipping carrier, or guarantee idempotency.

~~~mermaid
flowchart LR
    A["OrderGateway.submit"] --> B["RawOrder -> Order"]
    B --> C{"amount > 0?"}
    C -->|No| X["MessageRejectedException"]
    C -->|Yes| D{"priority?"}
    D -->|true| E["Receipt PRIORITY"]
    D -->|false| F["Receipt STANDARD"]
    E --> G["Format String"]
    F --> G
    G --> H["Gateway reply"]
~~~

### 5.2. Configuration and Data Types

Place the following code in `OrderFlowConfiguration.java`, package `example.integration`:

~~~java
package example.integration;

import java.math.BigDecimal;
import java.util.Objects;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.handler.annotation.Header;

@Configuration(proxyBeanMethods = false)
@EnableIntegration
public class OrderFlowConfiguration {

    public record RawOrder(
            String id,
            boolean priority,
            String amount) {
    }

    public record Order(
            String id,
            boolean priority,
            BigDecimal amount) {
    }

    public record Receipt(
            String orderId,
            String lane,
            BigDecimal amount) {
    }

    public interface OrderGateway {
        String submit(
                RawOrder command,
                @Header("correlationKey") String correlationKey);
    }

    @Bean
    IntegrationFlow orderFlow() {
        return IntegrationFlow
                .from(OrderGateway.class, gateway -> gateway
                        .beanName("orderGateway")
                        .replyTimeout(2_000L))
                .transform(
                        RawOrder.class,
                        OrderFlowConfiguration::normalize,
                        endpoint -> endpoint.id("orders.normalize"))
                .channel("orders.normalized")
                .filter(
                        Order.class,
                        order -> order.amount().signum() > 0,
                        filter -> filter
                                .id("orders.positiveAmount")
                                .throwExceptionOnRejection(true))
                .<Order, Boolean>route(
                        Order::priority,
                        router -> router
                                .subFlowMapping(true, branch -> branch
                                        .handle(Order.class, (order, headers) ->
                                                new Receipt(
                                                        order.id(),
                                                        "PRIORITY",
                                                        order.amount())))
                                .subFlowMapping(false, branch -> branch
                                        .handle(Order.class, (order, headers) ->
                                                new Receipt(
                                                        order.id(),
                                                        "STANDARD",
                                                        order.amount()))))
                .transform(
                        Receipt.class,
                        receipt -> receipt.orderId()
                                + "|" + receipt.lane()
                                + "|" + receipt.amount().toPlainString(),
                        endpoint -> endpoint.id("orders.formatReceipt"))
                .get();
    }

    static Order normalize(RawOrder raw) {
        Objects.requireNonNull(raw, "command is required");

        String id = Objects.requireNonNull(
                raw.id(), "id is required").trim();

        if (id.isEmpty()) {
            throw new IllegalArgumentException("id must not be blank");
        }

        BigDecimal amount = new BigDecimal(
                Objects.requireNonNull(
                        raw.amount(), "amount is required").trim());

        return new Order(id, raw.priority(), amount);
    }
}
~~~

The gateway proxy is created by `IntegrationFlow.from(OrderGateway.class, ...)`. Therefore, this example does not need a manual implementation of the interface and does not need to scan the same interface with `@IntegrationComponentScan`. Starting a flow from an interface and naming the proxy are described in [IntegrationFlow as a Gateway](https://docs.spring.io/spring-integration/reference/6.5/dsl/integration-flow-as-gateway.html).

`replyTimeout(2_000L)` configures how long the gateway waits for a reply. It is not a total execution timeout for all operations in the flow: if a synchronous handler holds the caller thread for too long, this timeout does not interrupt the handler. Builder options are in [GatewayProxySpec Javadoc](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/GatewayProxySpec.html).

### 5.3. Invoking the Flow with Plain Java

You can run the configuration above with a separate class:

~~~java
package example.integration;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class OrderFlowDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                OrderFlowConfiguration.class)) {

            var gateway = context.getBean(
                    "orderGateway",
                    OrderFlowConfiguration.OrderGateway.class);

            String result = gateway.submit(
                    new OrderFlowConfiguration.RawOrder(
                            " O-100 ", true, " 125.50 "),
                    "request-100");

            System.out.println(result);
        }
    }
}
~~~

Expected output:

~~~text
O-100|PRIORITY|125.50
~~~

Closing the context with `try-with-resources` cleanly terminates component lifecycles when the demo finishes.

### 5.4. Tracing the Message Through Each Step

| Stage | Payload | Business header to preserve |
| --- | --- | --- |
| Gateway receives | `RawOrder(" O-100 ", true, " 125.50 ")` | `correlationKey=request-100` |
| After normalize | `Order("O-100", true, 125.50)` | `correlationKey` |
| After filter | Still `Order` | `correlationKey` |
| After priority branch | `Receipt("O-100", "PRIORITY", 125.50)` | `correlationKey` |
| After formatter | `"O-100\|PRIORITY\|125.50"` | Headers for gateway reply |

`correlationKey` in the example is an application header to trace a request. It does not automatically replace the `correlationId` used by splitter/aggregator.

The gateway hides the messaging API from calling code and sets up reply information to receive the result. When the final endpoint produces a result and has no explicitly declared output channel, it can use the `replyChannel` from the message. See [Messaging Gateways](https://docs.spring.io/spring-integration/reference/6.5/gateway.html) and [Service Activator](https://docs.spring.io/spring-integration/reference/6.5/service-activator.html).

## 6. Filters, Routers, and Reply Contracts

### 6.1. Filter Rejection Does Not Mean Returning False

In the example, if the predicate returns `true`, the message continues. If it returns `false`, `throwExceptionOnRejection(true)` causes the flow to throw `MessageRejectedException`.

If you omit this option and do not configure a discard destination, the message is dropped from the main processing path; the gateway may wait until timeout because no reply arrives. If business logic expects a "rejected order" result, design a branch that produces a clearly typed reply, such as a router directing to a handler that builds `RejectedOrder`. `discardChannel`/`discardFlow` should be designed for handling discarded messages, not assumed to be an error-return mechanism for the caller. See [Filter](https://docs.spring.io/spring-integration/reference/6.5/filter.html).

With the current example:

| Input | Decision step | Outcome |
| --- | --- | --- |
| `amount="100"` | Filter accepts | Receipt produced |
| `amount="0"` | Filter rejects | Exception |
| `amount="-10"` | Filter rejects | Exception |
| `amount="abc"` | Normalize fails | Transformation error before reaching filter |

Distinguishing parse errors from failed conditions helps set appropriate messages, metrics, and retry rules. Resending the exact same string `"abc"` will usually not make parsing succeed.

### 6.2. Inline Sub-flows Return to the Common Step

The two `subFlowMapping` branches in the example return a `Receipt`, and both then flow into the formatter following `route`.

Do not replace a branch with:

~~~java
.handle(message -> System.out.println(message.getPayload()))
~~~

and still expect a `Receipt` for the formatter to process. Such a one-way handler merely consumes the message.

`channelMapping` directs messages to a target channel; it does not automatically establish the same return contract as an inline sub-flow. When calling a separate flow and needing its result to continue the current flow, you can use `gateway(...)` to express request-reply. If you choose one-way sending, you must design an appropriate termination path. These differences are described in [Sub-flows support](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-subflows.html).

### 6.3. Does handle Return a Result or Only Perform an Action?

~~~java
// Produces a result for the next step to continue.
.handle(Order.class, (order, headers) ->
        new Receipt(order.id(), "STANDARD", order.amount()))

// One-way: suitable when ending an event-recording branch.
.handle(message -> System.out.println(message.getPayload()))
~~~

In a real application, move order persistence or service calls into a business bean, and let the DSL wire the steps. When a handler returns `null` or has a `void` return type, there is no reply to forward; if the endpoint must reply, configure the appropriate reply requirement. See [Service Activator](https://docs.spring.io/spring-integration/reference/6.5/service-activator.html).

## 7. Choosing How to Start a Flow

### 7.1. Starting from a Channel

~~~java
@Bean("text.results")
QueueChannel textResults() {
    return new QueueChannel(20);
}

@Bean
IntegrationFlow textFlow(
        @Qualifier("text.results") QueueChannel results) {

    return IntegrationFlow.from("text.input")
            .transform(String.class, String::trim)
            .channel(results)
            .get();
}
~~~

This is a standalone supplementary configuration snippet and requires the corresponding `Bean`, `Qualifier`, `QueueChannel`, and `IntegrationFlow` imports. `from("text.input")` uses an existing channel with that name, or lets the DSL create one if it does not yet exist.

The sender uses `MessageChannel`, and the result reader uses `QueueChannel`:

~~~java
MessageChannel input = context.getBean("text.input", MessageChannel.class);
QueueChannel results = context.getBean("text.results", QueueChannel.class);

boolean sent = input.send(new GenericMessage<>("  spring integration  "), 1_000);
if (!sent) {
    throw new IllegalStateException("Failed to send message");
}

Message<?> reply = results.receive(1_000);
if (reply == null) {
    throw new IllegalStateException("No result received");
}

System.out.println(reply.getPayload());
~~~

The calling snippet requires additional imports for `org.springframework.messaging.Message`, `MessageChannel`, and `org.springframework.messaging.support.GenericMessage`. The `context` variable is an application context that has loaded the configuration.

One benefit of named channels is that multiple flows can connect to the same contract. However, do not declare two separate inline channel objects and give them the same name expecting them to be a single channel. For shared components, declare the bean once and inject it or reference it by name. See [Message Channels in Java DSL](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-channels.html).

### 7.2. Starting from a Gateway

Use a gateway when business code needs a method with a clear name, parameters, and return type, such as `OrderGateway.submit(...)`.

Two common configuration approaches:

| Approach | Suitable when |
| --- | --- |
| `IntegrationFlow.from(MyGateway.class, ...)` | You want to declare the gateway together with the flow via DSL |
| `@MessagingGateway` + gateway registration + flow from request channel | You want to separate the gateway interface from the flow via an agreed channel |

Choose one registration approach for a given gateway. With `from(MyGateway.class)`, a request channel is created to connect to that flow; do not expect a `requestChannel` placed on the annotation to route to a different flow. See [IntegrationFlow as a Gateway](https://docs.spring.io/spring-integration/reference/6.5/dsl/integration-flow-as-gateway.html).

### 7.3. Starting from a Polled Supplier

An active tick-emitting source can be declared as follows:

~~~java
@Bean
IntegrationFlow heartbeatFlow() {
    return IntegrationFlow
            .fromSupplier(
                    () -> java.time.Instant.now().toString(),
                    source -> source.poller(
                            Pollers.fixedDelay(1_000)
                                    .maxMessagesPerPoll(1)))
            .handle(message ->
                    System.out.println("heartbeat=" + message.getPayload()))
            .get();
}
~~~

The snippet above requires `org.springframework.integration.dsl.Pollers` and enabled integration infrastructure. It runs repeatedly according to the poller while the context is active.

The poller here belongs to the endpoint fetching data from the source. `maxMessagesPerPoll(1)` limits the number of fetches/emissions in a single poll cycle; it does not limit the total number of messages over the application's lifetime.

Not every `from` needs a poller: a flow from `DirectChannel` receives messages via subscription; polling sources and consumers reading a `PollableChannel` are what need polling configuration. See [Pollers](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-pollers.html).

## 8. Channels Determine Execution Behavior

Placing DSL calls on separate lines does not make them run in parallel. The channel type, executor, and endpoint determine execution.

| Channel | How messages are transferred | Consequence to account for |
| --- | --- | --- |
| `DirectChannel` | Invokes subscriber on sending thread | Caller bears synchronous downstream processing time |
| `QueueChannel` | Stores messages for consumer retrieval | Requires consumer/poller; has capacity and waiting |
| `ExecutorChannel` | Dispatches via an executor | Introduces a thread boundary per executor configuration |
| `PublishSubscribeChannel` | Broadcasts to multiple subscribers | Broadcast semantics; check whether an executor is used |

`DirectChannel` has point-to-point semantics. Having multiple consumers on it does not mean every consumer receives every message. `PublishSubscribeChannel` fits broadcast goals. A queue stores messages in memory by default unless backed by another persistence mechanism. See [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html).

### 8.1. Example of a Queue-Reading Consumer

The configuration snippet below is a standalone example; place the methods in a `@Configuration` class with `@EnableIntegration` enabled:

~~~java
@Bean("tasks.input")
QueueChannel tasksInput() {
    return new QueueChannel(100);
}

@Bean
IntegrationFlow queuedTasksFlow(
        @Qualifier("tasks.input") QueueChannel input) {

    return IntegrationFlow.from(input)
            .handle(
                    String.class,
                    (payload, headers) -> {
                        if (payload.isBlank()) {
                            throw new IllegalArgumentException(
                                    "task must not be blank");
                        }

                        System.out.println("processed=" + payload);
                        return null; // One-way contract.
                    },
                    endpoint -> endpoint
                            .id("tasks.worker")
                            .poller(Pollers.fixedDelay(200)
                                    .maxMessagesPerPoll(10)
                                    .errorChannel("tasks.errors")))
            .get();
}

@Bean
IntegrationFlow taskErrorsFlow() {
    return IntegrationFlow.from("tasks.errors")
            .handle(message ->
                    System.err.println("task failed: " + message.getPayload()))
            .get();
}
~~~

Imports beyond the basic configuration:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.Pollers;
~~~

The `tasks.worker` consumer has a poller because its input is a `QueueChannel`. `tasks.errors` is used by the error-handling flow as its input channel. The final endpoint of each flow is one-way and thus does not require the caller to supply a reply channel.

If the sender only calls `send(...)` on `tasks.input` and receives `true`, that confirms sending to the channel succeeded. Whether the worker completes or fails happens later and is not proven by this `true` return value.

### 8.2. Decisions When Adding a Queue

Before replacing a direct channel with a queue, determine:

1. Capacity suited to arrival and processing rates.
2. Send timeout when the queue is full and behavior upon timeout.
3. Who reads the queue and which poller governs the read cadence.
4. How errors and backlog are observed.
5. Durability requirements if the process stops.

A queue does not create a consumer by itself. Nor does a poller create durability by itself. If data must survive restarts, choose a message store or messaging infrastructure that matches the requirement.

An executor/queue boundary also requires reviewing transactions and thread-bound context. Do not assume that the caller's transaction will automatically cover work running on another thread.

## 9. Combining Splitter and Aggregator with Java DSL

### 9.1. Example Processing a List

Suppose a message contains `List.of(1, 2, 3)`. Each number must be multiplied by ten, and the results are then collected back together.

~~~java
@Bean("batch.results")
QueueChannel batchResults() {
    return new QueueChannel(20);
}

@Bean
IntegrationFlow batchFlow(
        @Qualifier("batch.results") QueueChannel results) {

    return IntegrationFlow.from("batch.input")
            .split()
            .transform(Integer.class, value -> value * 10)
            .aggregate()
            .channel(results)
            .get();
}
~~~

Given a non-empty `List<Integer>` input, the default splitter creates a message for each element and populates sequence/correlation metadata. The aggregator can use that metadata to identify the group and when to release it. See [Splitter](https://docs.spring.io/spring-integration/reference/6.5/splitter.html).

~~~mermaid
flowchart LR
    A["List: 1, 2, 3"] --> B["split"]
    B --> C["1 -> 10"]
    B --> D["2 -> 20"]
    B --> E["3 -> 30"]
    C --> F["aggregate by same correlationId"]
    D --> F
    E --> F
    F --> G["Result contains 10, 20, 30"]
~~~

The default processing path in this example is synchronous; the multi-branch diagram illustrates child messages, not a guarantee that they run on multiple threads.

### 9.2. Aggregators Have State and Completion Conditions

Three questions must be answered:

| Question | Related component | In the list example |
| --- | --- | --- |
| Which messages belong to the same group? | Correlation strategy | Correlation header created by splitter |
| When is data complete? | Release strategy | Element count known from sequence |
| What output are they combined into? | Group processor | Collects the group's payloads |

An aggregator holds groups in a message store; it is a stateful endpoint. By default, it relies on `correlationId` to group and `sequenceSize` to decide completion. When a group can never become complete, you need a timeout/expiry policy and handling for partial data; merely configuring a gateway wait timeout does not release group state. See [Aggregator](https://docs.spring.io/spring-integration/reference/6.5/aggregator.html).

Example of a common design mistake:

~~~text
split a 3-element list
  -> filter drops 1 element
  -> aggregator still waits for 3
~~~

If elements need to be excluded, consider filtering the list before splitting, or redesigning the release strategy and per-item result contract. Another option is to keep the full response count while representing invalid items as a clearly typed rejection result.

With an empty list, no child messages are emitted to trigger aggregation as in the non-empty case. Define the outcome for empty input explicitly. With an iterator/stream source of unknown size, you also cannot blindly apply a "received all N elements" condition.

If you add parallel processing, completion order may differ from input order. If result order matters to business logic, design and test for it rather than relying on the line order in the DSL.

## 10. Error Handling Across Execution Boundaries

### 10.1. Synchronous Flows Return Errors to the Caller

In `orderFlow`, direct channels keep the processing path synchronous. If normalization or the filter throws an error, the gateway in the current configuration propagates the error to the caller because no dedicated error channel is configured on the gateway.

The underlying business error may be wrapped in a messaging exception, so tests should inspect both the outer exception and its cause. Do not catch only `NumberFormatException` in calling code assuming every parse error arrives directly as that exact type.

### 10.2. Asynchronous Flows Need a Dedicated Error Path

When a framework task runs via an executor or poller, an exception cannot simply be thrown back up the call stack of the thread that already finished sending. The error-handling mechanism can create an `ErrorMessage` whose payload is the `Throwable` and send it to the appropriate error channel.

A poller's error channel configuration, a message's `errorChannel` header, and a gateway's error channel each have their own scope of effect. Do not infer that merely creating an `errorChannel` bean will automatically catch every exception from every synchronous handler. See [Error Handling](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html).

In the queue example, `.errorChannel("tasks.errors")` placed directly on the poller makes the error destination for that polling work explicit. In a real system, replace `System.err.println` with observable, operable handling such as logging with request IDs, metrics, and storage for errors that need reprocessing.

### 10.3. Distinguishing Timeouts, Retries, and Failed Outcomes

| Situation | Suggested design decision |
| --- | --- |
| Malformed amount | Return an input error; fix data before retrying |
| Filter drops a message in request-reply | Choose between throwing an error or a branch producing a rejection reply |
| Transient downstream HTTP error | Consider timeouts and bounded retries |
| Gateway times out | Check downstream; do not assume work has stopped |
| Missing child message | Check aggregator group and expiry policy |
| Retrying an order-creation operation | Needs deduplication rules based on business keys |

The options in the table are design directions for the application, not automatic behaviors built into the DSL.

If the caller times out while the task keeps creating an order, a retry may create an extra order. Therefore, timeouts must be paired with deduplication contracts and a way to query the final outcome; merely shortening the wait milliseconds does not solve this scenario.

## 11. Testing the Flow at Its Public Boundary

### 11.1. Testing the Main Example's Gateway

Place the following class in `OrderFlowConfigurationTest.java` in the same `example.integration` package. This is test code for learners to run in a project with appropriate test dependencies.

~~~java
package example.integration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.MessageRejectedException;
import org.springframework.messaging.MessagingException;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(OrderFlowConfiguration.class)
class OrderFlowConfigurationTest {

    @Autowired
    @Qualifier("orderGateway")
    private OrderFlowConfiguration.OrderGateway gateway;

    @Test
    void normalizesAndRoutesPriorityOrder() {
        String result = gateway.submit(
                new OrderFlowConfiguration.RawOrder(
                        " O-100 ", true, " 125.50 "),
                "req-priority");

        assertEquals("O-100|PRIORITY|125.50", result);
    }

    @Test
    void routesStandardOrder() {
        String result = gateway.submit(
                new OrderFlowConfiguration.RawOrder(
                        "O-101", false, "20.00"),
                "req-standard");

        assertEquals("O-101|STANDARD|20.00", result);
    }

    @Test
    void rejectsNonPositiveAmount() {
        assertThrows(
                MessageRejectedException.class,
                () -> gateway.submit(
                        new OrderFlowConfiguration.RawOrder(
                                "O-102", false, "0"),
                        "req-rejected"));
    }

    @Test
    void exposesMalformedAmountAsTransformationFailure() {
        MessagingException error = assertThrows(
                MessagingException.class,
                () -> gateway.submit(
                        new OrderFlowConfiguration.RawOrder(
                                "O-103", false, "not-a-number"),
                        "req-malformed"));

        assertInstanceOf(NumberFormatException.class, rootCause(error));
    }

    private static Throwable rootCause(Throwable error) {
        Throwable current = error;
        while (current.getCause() != null
                && current.getCause() != current) {
            current = current.getCause();
        }
        return current;
    }
}
~~~

The tests verify behavior observable by calling code: normalization, both routing branches, and errors. They do not need to know auto-generated channel names or internal builder structure.

When replacing a handler with an external service, you can mock the business bean or use support from `spring-integration-test`. Integration testing utilities are introduced in [Testing support](https://docs.spring.io/spring-integration/reference/6.5/testing.html).

### 11.2. Testing a Flow with a Queue

For a flow ending in a `QueueChannel`:

1. Send a message carrying deterministic data.
2. Receive the result using a bounded `receive(timeout)`.
3. Assert both the presence of the message and the expected content.
4. For error cases, verify the error channel or error-recording mechanism.
5. Ensure queue state and aggregator groups do not leak across test cases.

Do not use `Thread.sleep(...)` as proof that work has finished. Also do not use an unbounded `receive()` in tests, as a misconfiguration can hang the test.

For a three-element batch, what must be proven is that an aggregated result contains the exact three transformed values without mixing data from another batch. Checking only `send(...) == true` does not test the splitter or aggregator.

### 11.3. Choosing the Appropriate Test Level

| Level | What to prove | Example |
| --- | --- | --- |
| Business function | Data rules independent of messaging | Normalizing order ID and amount |
| Flow in context | Endpoints wired properly, right branches, right replies | Invoking gateway and asserting results/errors |
| Infrastructure integration | Protocols and external dependencies work properly | HTTP/JMS/JDBC adapters against a test environment |

A flow wiring individually correct functions can still fail at channels, headers, or reply paths. Conversely, there is no need to bring in full external infrastructure in a test just to check a pure Java parsing rule.

## 12. Naming and Splitting Flows for Maintainability

In the example:

- `orderFlow` is the bean name holding the flow configuration.
- `orderGateway` is the proxy name called by business code.
- `orders.normalized` is the channel carrying normalized `Order` instances.
- `orders.normalize` and `orders.formatReceipt` are explicitly named endpoint IDs.

Assign names at boundaries that need to be observed or controlled. Do not couple tests to auto-generated index-based channel names, because adding an endpoint can shift the indices.

When a large lambda holds multiple business branches, move the computation into a bean with clear methods. When a branch is reused or has an independent lifecycle, consider a separate flow connected via a channel/gateway with concrete input and reply contracts.

For example, if "create priority receipt" later involves calling three services, compensating on errors, and persisting data, stuffing everything into a `subFlowMapping` lambda will make the topology hard to read. The main flow should express steps at the business level; the implementation of each step can be tested separately.

## 13. Common Mistakes When Writing Java DSL

| Symptom | Cause to check | Fix |
| --- | --- | --- |
| Cannot import `IntegrationFlows` | Applying a historical example to a different version | Use the factory matching your version; for this lesson's baseline use `IntegrationFlow` |
| Message enters, but gateway gets no reply | Filter dropped it, one-way handler, or reply header lost | Trace each branch and define an outcome for every path |
| Flow from queue does not read | Missing consumer/poller or consumer not started | Check polling endpoint and lifecycle |
| Sending to direct channel reports no subscribers | No receiving endpoint or flow not started | Check bean registration and target channel |
| Only one of several handlers receives messages | Using a point-to-point channel | Choose broadcast when all subscribers must receive |
| Class-cast error when lambda expects `Message` | Overload is still passing payload | Pick an overload with a class token or explicit message-receiving handler |
| Two flows collide on channel name | Creating multiple inline objects with the same ID | Declare shared channel as a bean once |
| Aggregator waits forever | Missing items, wrong correlation, or release condition | Check sequence, filter, and group policy |
| Only a log line appears and flow stops | Final handler does not return a result | Choose a clear one-way or request-reply contract |
| Retries produce duplicate data | Side effects lack deduplication rules | Apply business keys and idempotency contracts |
| Caller times out while downstream keeps running | Reply timeout does not cancel work | Design deadlines/cancellation and result queries when needed |

Use the table to form hypotheses, then verify with actual messages, endpoint configurations, and logs. A single timeout alone is not enough to determine whether a message was dropped, lost its header, or is still sitting in a queue.

## 14. Self-Implementation Practice Exercises

### Exercise 1: Add a Business Branch

Change the routing condition to split into `PRIORITY`, `STANDARD`, and `MANUAL_REVIEW` for orders exceeding an amount threshold.

Completion requirements:

- Every valid routing key has a target.
- Every branch produces the same reply type before the formatter.
- Tests cover both the exact threshold value and values above the threshold.
- Classification logic lives in an independently testable function/bean.

### Exercise 2: Change the Rejection Contract

Replace throwing an exception on non-positive amounts with a business result having status `REJECTED`.

Before editing the DSL, define the gateway's return type for both accepted and rejected orders. Then use an appropriate router or reply branch, and test that every input produces a result conforming to the contract.

### Exercise 3: Add a Queue and Observe Errors

Offload processing work to a queue with bounded capacity.

Completion requirements:

- The consumer has an explicit poller.
- A valid task reaches an observable destination.
- A failing task reaches the error-recording path.
- Tests use finite timeouts and do not rely on sleep.
- Distinguish successful sending from successful processing.

### Exercise 4: Test an Incomplete Batch

In the `split → transform → aggregate` flow, try adding a filter after split that drops one element. Explain why the group does not complete, then choose a fix appropriate for the business logic.

Do not simply increase the timeout. Provide a clear contract for incomplete groups, empty inputs, and per-item results.

## 15. Key Takeaways

`IntegrationFlow` describes how channels and endpoints connect together; Java DSL lets you express that topology directly in Java configuration. When reading older documentation featuring `IntegrationFlows`, first check the API against your target version.

Designing a flow starts with contracts: who sends messages, what payload each step accepts/returns, which headers must be preserved, what result each branch produces, and where errors go. Then choose channels to determine synchronous execution, polling, or executor dispatching.

A complete flow must account for the success path, the rejection path, and the incomplete path. Gateways, filters, routers, and aggregators only coordinate properly when those contracts are defined and tested.
