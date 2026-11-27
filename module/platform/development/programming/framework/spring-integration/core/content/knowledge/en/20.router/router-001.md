# What is a message router

A message router is the component that **chooses the next path for a message**. It receives a `Message<?>` from an input channel, applies a routing rule, and forwards the message to one or more target channels. The rule can be based on the payload, headers, or payload type. This is an enterprise integration pattern that separates the "where to go next" decision from the place where the message originates. [Spring Integration: Router Overview](https://docs.spring.io/spring-integration/reference/router/overview.html)

In the **SPRING_INTEGRATION_CORE** module, the router connects knowledge about `Message`, `MessageChannel`, and endpoints into a branching flow. This lesson focuses on what a router means, how to express it with Java DSL, the policy when no target is selected, and how to verify that a message took the right branch.

After this lesson, you will be able to:

- Recognize situations that call for a router and distinguish a router from neighboring components.
- Explain the relationship between input data, routing keys, and target channels.
- Build an order routing flow with two business branches and one fallback branch.
- Verify the selected branch, payload, and headers without connecting to external systems.

## 1. Problem statement: orders need to be sent to the right processing flow

Suppose a system receives orders from multiple sources. Express delivery orders and standard delivery orders must go through two different workflows; unsupported methods must go to manual review.

| Business data | Normalized key | Target channel | Meaning |
| --- | --- | --- | --- |
| `deliveryType = "EXPRESS"` | `EXPRESS` | `expressOrders` | Express delivery flow |
| `deliveryType = "STANDARD"` | `STANDARD` | `standardOrders` | Standard delivery flow |
| `deliveryType = "DRONE"` | `DRONE` | `manualReview` | No mapping yet, needs review |
| `deliveryType = null` | `UNKNOWN` | `manualReview` | Missing routing information |

Desired flow:

~~~mermaid
flowchart LR
    P["Order intake"] --> I["ordersInput"]
    I --> R{"Router: deliveryType"}
    R -->|"EXPRESS"| E["expressOrders"]
    R -->|"STANDARD"| S["standardOrders"]
    R -->|"No mapping"| M["manualReview"]
    E --> EF["Express delivery workflow"]
    S --> SF["Standard delivery workflow"]
    M --> MF["Manual review"]
~~~

The intake component only sends messages to `ordersInput`. It does not have to call each delivery service directly. When a new delivery method is added, the main point of change is the routing rule and the corresponding processing branch.

An `if/else` statement could still express this rule. The value of a router is bringing branch selection into the messaging architecture: each branch connects via a channel and can continue with a transformer, filter, service activator, or another integration flow.

The router here operates inside a Spring Integration flow. It is neither a network router nor Spring MVC's URL mapping mechanism.

## 2. Operating model: read message, choose target, forward

### 2.1. Where does the router sit inside an endpoint?

You can picture the structure as follows:

~~~text
Input MessageChannel
        |
        v
Message-receiving endpoint
        |
        v
Router handler
        |
        +--> Target MessageChannel A
        |
        +--> Target MessageChannel B
~~~

In configuration terms, this whole processing point is often called a "router endpoint". The router handler itself decides the target; the endpoint mechanism connects the handler to the input channel. With a `DirectChannel`, the handler is invoked when a message is sent. If a polling input channel is used, the endpoint needs a poller mechanism to pull messages out. [Spring Integration: Common Router Parameters](https://docs.spring.io/spring-integration/reference/router/common-parameters.html)

Because of this, you need to determine two things separately: **how the message is received** and **where it is forwarded**.

### 2.2. Distinguishing three easily confused concepts

| Concept | Example | Role |
| --- | --- | --- |
| Data used for the decision | `order.deliveryType()` | Information read from the message |
| Routing key | `"EXPRESS"` | Result of the branch-selection function |
| Target channel | Bean `expressOrders` | Destination receiving the forwarded message |

In this example:

~~~text
payload.deliveryType() = " express "
             |
             v
normalize key to "EXPRESS"
             |
             v
map "EXPRESS" -> "expressOrders"
             |
             v
send Message<Order> to the expressOrders channel
~~~

`EXPRESS` is a business concept; `expressOrders` is a channel name in the configuration. Separating the two values makes the business rule less coupled to bean names.

The fact that the routing function returns `"EXPRESS"` does not mean the payload is replaced by that string. The string is used to select the target, while the forwarded data remains the order message. Java DSL supports `channelMapping(key, channelName)` pairs to express this relationship. [Spring Integration: Message Routers in Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java-routers.html)

### 2.3. A router forwards data; it does not transform data by default

Conceptually:

~~~text
routing decision: Message -> set of target channels
forwarding:       Message -> send to selected targets
~~~

In the illustrative flow, the router does not modify the payload or the `traceId` header. Normalization only creates a temporary key to look up the mapping; it does not mutate the `deliveryType` field of the order.

You should not overgeneralize this into "every router always preserves every header in every configuration". For example, a configuration intended for aggregating results across multiple branches may require adding sequence information. If business content needs to be transformed, express that with a dedicated transformer so the purpose of each step stays clear.

## 3. How does a router differ from familiar components?

| Component | Main question | Order example |
| --- | --- | --- |
| `MessageChannel` | Which transport path does the message travel through? | `ordersInput` receives messages from the sender |
| Router | Which branch should the message go to? | Express delivery or standard delivery |
| Transformer | What shape should the data be converted into? | Convert JSON into `Order` |
| Filter | Should the message continue past this step? | Drop orders that do not meet a condition |
| Splitter | Which parts should one message be split into? | Split an order into individual line items |
| Aggregator | Which messages should be combined back together? | Combine processing results of line items |
| Gateway | Through which interface does caller code interact with the message flow? | Call `submitOrder(...)` on a Java interface |

If you need to accept or discard a message based on a condition, a filter usually expresses that more directly. If you need to route multiple message types to separate destinations, a router is a better fit.

It is also important to distinguish **selecting a channel** from **broadcasting to a channel's subscribers**. `PublishSubscribeChannel` distributes a message to all of its subscribers. A router can select that channel as a target; the two mechanisms can appear together. A `DirectChannel` with multiple subscribers, on the other hand, does not mean broadcasting copies to all subscribers. [Spring Integration: Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)

A router can also select multiple channels for the same message. For example, an order event might need to go to both a reporting update branch and a notification branch at the same time. Therefore, "a router always picks exactly one branch" is too narrow a view. The example in this lesson, specifically, is designed so that each order goes to only one of the three channels.

## 4. What information should routing be based on?

The rule should reflect available data and the purpose of the flow.

| Decision source | Example | What needs to be agreed upon |
| --- | --- | --- |
| Field in payload | `Order.deliveryType` | Business data contract |
| Header | `tenantId`, `region`, `documentType` | Which step sets the header, and whether its value is trustworthy |
| Payload type | `OrderCreated` or `OrderCancelled` | Event model and deserialization behavior |
| Prior classification result | `riskLevel = HIGH` | The classification step must run before the router |

Spring Integration provides specialized routers such as `HeaderValueRouter`, `PayloadTypeRouter`, and `RecipientListRouter`; you can also use a Java function or expression to decide targets. [Spring Integration: Router Overview](https://docs.spring.io/spring-integration/reference/router/overview.html)

For the order problem, `deliveryType` is chosen because it directly represents the type of workflow to run. The key-selection function only normalizes the string and reads data, so it can be tested independently.

A maintainable routing rule usually has the following characteristics:

- The same input data yields the same decision, unless the business logic intentionally depends on external state.
- Do not simultaneously charge payment, update the order, or call a delivery service inside the key-selection function.
- Have a clear policy for unknown values, missing data, and configuration errors.
- If a lookup from another system is needed, represent that lookup step explicitly in the flow before branch selection.

Missing data and invalid data do not necessarily share the same policy. This lesson sends `deliveryType = null` to manual review so it is easy to observe. A system that requires this field can use a validation step before the router to reject it early.

## 5. Java DSL example: order routing

### 5.1. Prerequisites to run the example

The example uses Java 17 or later and the `IntegrationFlow.from(...)` declaration style of Spring Integration 6.x. The project needs the `org.springframework.integration:spring-integration-core` dependency along with compatible Spring dependencies. If using Spring Boot, let Boot's dependency management pick a compatible version set.

The two classes below are placed in the same package `example.router`. No HTTP server, Kafka, or RabbitMQ is needed to observe the behavior.

The output channels use `QueueChannel` to hold messages so the program can read and inspect them. In a real application, behind each channel there would be a consumer or a downstream processing flow. `QueueChannel` in this example is an in-memory queue, not a durable messaging guarantee.

### 5.2. Declaring data, channels, and router

Class `OrderRoutingConfig.java`:

~~~java
package example.router;

import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
@EnableIntegration
public class OrderRoutingConfig {

    public record Order(String orderId, String deliveryType) {
    }

    @Bean
    public DirectChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel expressOrders() {
        return new QueueChannel(10);
    }

    @Bean
    public QueueChannel standardOrders() {
        return new QueueChannel(10);
    }

    @Bean
    public QueueChannel manualReview() {
        return new QueueChannel(10);
    }

    static String routingKey(Order order) {
        String deliveryType = order.deliveryType();
        return deliveryType == null
                ? "UNKNOWN"
                : deliveryType.trim().toUpperCase(Locale.ROOT);
    }

    @Bean
    public IntegrationFlow orderRoutingFlow() {
        return IntegrationFlow.from(ordersInput())
                .route(Order.class, OrderRoutingConfig::routingKey,
                        router -> router
                                .channelMapping("EXPRESS", "expressOrders")
                                .channelMapping("STANDARD", "standardOrders")
                                .defaultOutputChannel("manualReview")
                                .channelKeyFallback(false)
                                .resolutionRequired(true)
                                .sendTimeout(1_000))
                .get();
    }
}
~~~

Reading the configuration step by step:

1. `ordersInput` is the entry point of the flow.
2. `Order.class` specifies the payload type handled by the routing function.
3. `routingKey` produces a business key, such as `EXPRESS`.
4. `channelMapping` links that key to a channel bean name.
5. `manualReview` receives messages when no target matches from the mapping.
6. The remaining options govern how channel names are resolved and how messages are sent.

`Locale.ROOT` ensures uppercasing does not depend on the machine's default locale. Given `" express "` as input, the router selects `expressOrders`, while the payload still holds the original value `" express "`.

The three queues have a capacity of 10 so the example has an explicit bound. `sendTimeout(1_000)` sets the wait timeout for sending to a target channel to 1,000 ms when sending has to wait, such as when a queue is full. It does not bound the execution time of the entire business process downstream of the router.

The `channelMapping`, `channelKeyFallback`, `resolutionRequired`, and `sendTimeout` APIs belong to router configuration in Java DSL. [Spring Integration: RouterSpec API](https://docs.spring.io/spring-integration/api/org/springframework/integration/dsl/RouterSpec.html)

### 5.3. Sending messages and reading each branch

Class `RouterDemo.java`:

~~~java
package example.router;

import java.util.List;

import example.router.OrderRoutingConfig.Order;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

public class RouterDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(OrderRoutingConfig.class)) {

            MessageChannel input =
                    context.getBean("ordersInput", MessageChannel.class);

            List<Order> orders = List.of(
                    new Order("ORD-1", "EXPRESS"),
                    new Order("ORD-2", "STANDARD"),
                    new Order("ORD-3", "DRONE"));

            for (Order order : orders) {
                Message<Order> message = MessageBuilder.withPayload(order)
                        .setHeader("traceId", "trace-" + order.orderId())
                        .build();

                if (!input.send(message)) {
                    throw new IllegalStateException("Failed to send order");
                }
            }

            for (String channelName :
                    List.of("expressOrders", "standardOrders", "manualReview")) {
                QueueChannel channel =
                        context.getBean(channelName, QueueChannel.class);
                Message<?> received = channel.receive(0);
                System.out.println(channelName + " -> "
                        + (received == null ? "EMPTY" : received.getPayload()));
            }
        }
    }
}
~~~

Expected output:

~~~text
expressOrders -> Order[orderId=ORD-1, deliveryType=EXPRESS]
standardOrders -> Order[orderId=ORD-2, deliveryType=STANDARD]
manualReview -> Order[orderId=ORD-3, deliveryType=DRONE]
~~~

Here, `receive(0)` reads immediately and returns `null` if the queue is empty. The program does not need a poller for the three output queues because the demo code itself calls `receive`. If you want to declare an endpoint that continuously pulls data from a queue to process it, you need to configure an appropriate poller. The send and receive behavior of `QueueChannel` is described in the [Spring Integration channel documentation](https://docs.spring.io/spring-integration/reference/channel/implementations.html).

When `send` returns successfully, the message in the example has been placed into the target queue. That does not mean the delivery workflow has finished.

## 6. No matching branch and routing errors are two distinct situations

### 6.1. Unsupported key

`DRONE` does not appear in the mapping table. The configuration has `channelKeyFallback(false)`, so the router does not try to use the string `DRONE` as a channel name. Because there is no target from the mapping, it uses `manualReview`.

When channel-key fallback is enabled, an unmapped key can be used as a channel name for further resolution. Disabling this mechanism keeps the example's target set strictly tied to the declared mappings. Since Spring Integration 6.0, setting a default output channel also switches channel-key fallback to `false`; the example still specifies the option explicitly so readers see the intent. [Spring Integration: AbstractMappingMessageRouter API](https://docs.spring.io/spring-integration/api/org/springframework/integration/router/AbstractMappingMessageRouter.html)

### 6.2. Mapping exists, but the channel name is wrong

Suppose someone accidentally edits:

~~~java
.channelMapping("EXPRESS", "expressOrderTypo")
~~~

If there is no channel named `expressOrderTypo`, that is a configuration error. With `resolutionRequired(true)`, the router requires the channel name to resolve successfully and raises an error when it cannot. You should not treat `manualReview` as a mechanism to mask every routing error. [Spring Integration: Common Router Parameters](https://docs.spring.io/spring-integration/reference/router/common-parameters.html)

You can predict the behavior of this lesson's configuration as follows:

| Situation | Expected behavior |
| --- | --- |
| Key `EXPRESS`, valid mapping and channel | Sent to `expressOrders` |
| Key `DRONE`, no mapping | Sent to `manualReview` |
| `deliveryType = null` | Produces key `UNKNOWN`, sent to `manualReview` |
| Key `EXPRESS`, mapping points to nonexistent channel name | Raises resolution error |
| Target channel exists but fails to receive message | Handled as a send failure, does not automatically fall back to default branch |
| Routing function throws an exception | Handled as a function execution error, does not automatically fall back to default branch |
| Payload has a type incompatible with a function expecting `Order` | Input handling error, not an unsupported-key case |

If you omit the default output channel, you must actively decide what happens when there is no target. By default, a router does not silently drop a message just because no branch was found. Choosing to drop a message must be designed explicitly; in this lesson's order flow, keeping it in `manualReview` helps surface unsupported delivery types. [Spring Integration: Router Overview](https://docs.spring.io/spring-integration/reference/router/overview.html)

## 7. Recognizing the same idea with the `@Router` annotation

Java DSL is the primary representation in this lesson. When reading other codebases, you may also encounter a method annotated with `@Router`.

A router method can return a channel name, a `MessageChannel` object, or a collection of corresponding values to select multiple targets. The method can also receive the payload or header data. [Spring Integration: Configuring a Router with Annotations](https://docs.spring.io/spring-integration/reference/router/annotation.html)

Alternative example:

~~~java
package example.router;

import example.router.OrderRoutingConfig.Order;
import org.springframework.integration.annotation.Router;

public class OrderRouter {

    @Router(inputChannel = "ordersInput")
    public String selectChannel(Order order) {
        return switch (OrderRoutingConfig.routingKey(order)) {
            case "EXPRESS" -> "expressOrders";
            case "STANDARD" -> "standardOrders";
            default -> "manualReview";
        };
    }
}
~~~

To use this alternative with the already declared channels, remove the `orderRoutingFlow` flow bean and register the router as a bean in the configuration class that has `@EnableIntegration`:

~~~java
@Bean
public OrderRouter orderRouter() {
    return new OrderRouter();
}
~~~

In this annotation approach, the method returns the **channel name directly**. In the earlier DSL approach, the `routingKey` method returned the **business key**, and the mapping then selected the channel name.

Keep only one approach on `ordersInput` for the exercise. If you register both at the same time, you create two endpoints subscribed to the same `DirectChannel`; that is a different flow structure from the single router being observed.

## 8. A router does not itself decide synchronous vs. asynchronous flow

The path and the execution mode are two different decisions.

In the example, `ordersInput` is a `DirectChannel`, so the routing decision runs on the thread calling `input.send(...)`. The router then puts the message into a `QueueChannel`; downstream business processing only happens when a consumer takes the message.

With a synchronous path through `DirectChannel`, exceptions can propagate back to the sender. With asynchronous processing via an executor or polling endpoint, errors cannot return to a call stack that has already finished; the error-handling mechanism of the corresponding component typically turns the failure into an `ErrorMessage` sent to an error channel. You should not assume every error automatically appears on the global `errorChannel`, especially when calling `MessageChannel.send` directly. [Spring Integration: Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)

When designing error branches, clearly determine:

- Which component raises the error and which thread it runs on.
- Who is responsible for catching the error or publishing the `ErrorMessage`.
- Whether to retry, keep the message for reprocessing, or move it to another business workflow.

The `manualReview` example represents a business decision for an unsupported delivery type. It does not replace exception handling.

If a router sends to multiple targets, you also should not assume by default that those sends form an "all-or-nothing" transaction. One branch may have already received the message before another branch fails. If the business logic needs stronger guarantees, you must design transactions, persistence, or idempotent/retry handling appropriate to the actual resources.

## 9. Testing routing behavior

A useful test needs to verify both **the right target received the message** and **the other targets did not receive it**. Looking only at logs from one handler can miss the case where a message was also sent to another branch.

With the Java DSL configuration, the cases to observe include:

| Input | Exclusive recipient | Additional assertion |
| --- | --- | --- |
| `EXPRESS` | `expressOrders` | The other two queues are empty |
| `STANDARD` | `standardOrders` | The other two queues are empty |
| `" express "` | `expressOrders` | Payload keeps its original value |
| `DRONE` | `manualReview` | Does not land in either delivery branch |
| `null` | `manualReview` | Missing data does not cause an error under the example's policy |

The JUnit Jupiter snippet below sits in the same package and reuses the original `OrderRoutingConfig`. The project needs the `org.junit.jupiter:junit-jupiter` test dependency and an appropriate JUnit runner setup.

~~~java
package example.router;

import java.util.List;

import example.router.OrderRoutingConfig.Order;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class OrderRoutingTest {

    @Test
    void routesEachOrderToExactlyOneDestination() {
        try (var context =
                     new AnnotationConfigApplicationContext(OrderRoutingConfig.class)) {
            assertRouted(context, new Order("ORD-1", "EXPRESS"), "expressOrders");
            assertRouted(context, new Order("ORD-2", "STANDARD"), "standardOrders");
            assertRouted(context, new Order("ORD-3", " express "), "expressOrders");
            assertRouted(context, new Order("ORD-4", "DRONE"), "manualReview");
            assertRouted(context, new Order("ORD-5", null), "manualReview");
        }
    }

    private static void assertRouted(
            AnnotationConfigApplicationContext context,
            Order order,
            String expectedChannel) {

        String traceId = "trace-" + order.orderId();
        Message<Order> sent = MessageBuilder.withPayload(order)
                .setHeader("traceId", traceId)
                .build();

        MessageChannel input =
                context.getBean("ordersInput", MessageChannel.class);
        assertTrue(input.send(sent));

        for (String channelName :
                List.of("expressOrders", "standardOrders", "manualReview")) {
            Message<?> received = context.getBean(channelName, QueueChannel.class)
                    .receive(0);

            if (channelName.equals(expectedChannel)) {
                assertNotNull(received, "Missing message in " + channelName);
                assertEquals(order, received.getPayload());
                assertEquals(traceId, received.getHeaders().get("traceId"));
                assertNull(context.getBean(channelName, QueueChannel.class).receive(0),
                        "Extra message in " + channelName);
            } else {
                assertNull(received, "Message routed unexpectedly to " + channelName);
            }
        }
    }
}
~~~

This test observes the real flow through the Spring context: selecting the right target, not sending extra messages, and preserving the order data and tracing header. It does not test any delivery service or external system.

No `Thread.sleep` is needed here because routing to the queue completes before `send` returns. If you switch to a segment executed by an executor, the way you wait for results needs to change, such as receiving with a bounded timeout.

Besides the normal path, you should test configuration errors and exceptions when you add the corresponding error-handling mechanisms. In particular, a test for "an unsupported value goes to manual review" is not a substitute for testing "a channel name in the mapping is misspelled".

## 10. Common design mistakes

### 10.1. Returning a business key but forgetting to declare the mapping

A function returning `"EXPRESS"` is not enough to refer to the `expressOrders` channel. Without a mapping, behavior depends on how channel resolution is configured.

Check the full chain: input data → key → mapping → channel bean.

### 10.2. Putting all business processing inside the target-selection function

If the routing function calls a risk-scoring API, writes to a database, and sends an email all at once, changing or retrying the routing decision can cause unintended side effects.

Place data-gathering steps and business-processing steps in separate endpoints. The router uses the already available result to choose the path.

### 10.3. Using default output as a place to swallow all exceptions

The default branch handles the situation where there is no target according to the routing policy. It does not automatically catch exceptions from the key-selection function, send errors, or errors from downstream handlers.

Keep the policy for "unknown which branch to choose" separate from the policy for "processing failed".

### 10.4. Letting multiple branches mutate the same mutable payload

Sending a message to multiple targets does not mean creating an independent deep copy of the payload for each branch. If branches mutate a shared object concurrently, results easily become dependent on ordering or timing.

Prefer immutable data; if each branch needs its own representation, create the corresponding data through an explicit transformation step. The record in the example contains only `String` fields, which fits the goal of demonstrating data that is not mutated across branches.

### 10.5. Expecting a gateway to reply even though a branch only stores into a queue

If a caller invokes a gateway in request-reply style, you need to design the path that produces and returns the result. Having the router put the message into `manualReview` does not automatically create a business reply for the caller.

You must agree on whether the calling interface is one-way send or awaits a reply, and then design the branches accordingly. The router is only one step in that contract.

## 11. Extended practice

Use the DSL configuration as a starting point and carry out the following in order:

1. Send an order with `deliveryType = " standard "`; verify it arrives at `standardOrders` and the payload retains its original value.
2. Add a `pickupOrders` channel and a mapping for key `PICKUP`; verify this change does not reroute existing order types.
3. Send `"expressOrders"` as a `deliveryType` value; under the current rule it is not the `EXPRESS` key, so it must go to `manualReview`.
4. In a separate practice configuration, intentionally point the `EXPRESS` mapping to a nonexistent channel name; observe the difference between a configuration error and an unsupported key.
5. Sketch an added transformer before the router and a handler after each branch; note clearly which data is transformed and which step only selects the path.

When reading any router, identify in order: where it receives from, what data it reads, what key it produces, which channels it selects, and what it does when there is no target. Being able to answer those points means you have grasped the core role of a message router in a Spring Integration flow.