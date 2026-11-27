# Type-based routing

In the **SPRING_INTEGRATION_CORE** module, type-based routing lets you split a message flow into branches based on the **Java type of the payload**. For example, an order-created event goes to the order branch, a payment event goes to the payment branch, and unsupported types go to a separate queue.

This lesson belongs to the **Router** chapter and focuses on `PayloadTypeRouter`, wiring the router to channels using Java DSL, selecting branches by class/interface, and handling cases that cannot be routed. Examples use Java 17+ and Spring Integration 6.5.x APIs; Spring Boot is not required.

## 1. Objectives and use cases

After this lesson, you will be able to:

- Distinguish the type of `Message`, the declared variable type, and the actual runtime type of the payload.
- Map a class or interface to a `MessageChannel`.
- Explain the difference between `PayloadTypeRouter` and a router using the `Object::getClass` lambda.
- Choose policies for unknown payloads, misconfigured channels, and message send failures.
- Test for the right branch, no extra deliveries to other branches, and preserved tracing metadata.

Suppose an application receives events that have already been converted into Java objects:

| Payload | Meaning | Desired channel |
| --- | --- | --- |
| `OrderPlaced` | An order has been placed | `orderEvents` |
| `PaymentCaptured` | Payment has been captured | `paymentEvents` |
| `RefundRequested` | Business event without its own dedicated branch yet | `otherBusinessEvents` |
| A `String` outside the event model | Unsupported input | `unsupportedEvents` |

Here, the Java class itself expresses the event type. If every payload were an `Order` and the decision depended on `order.status()`, a business-attribute router would be a better fit.

## 2. Which type does the router look at?

A Spring message consists of a payload and headers. For a type-based router, the data used to pick a branch is the runtime type of the **payload**, not the class of the `Message` object itself.

The following snippet uses `BusinessEvent` and `OrderPlaced` declared in the configuration in section 5:

~~~java
BusinessEvent event = new OrderPlaced("ORD-1001");
Message<BusinessEvent> message = new GenericMessage<>(event);

// The runtime type of the payload is still OrderPlaced.
Class<?> actualType = message.getPayload().getClass();
~~~

The message classes in the example belong to the `org.springframework.messaging` and `org.springframework.messaging.support` packages.

| Component | Role in the routing decision |
| --- | --- |
| `GenericMessage` | Message wrapper class |
| `Message<BusinessEvent>` | Declared type in source code |
| `BusinessEvent` | Payload interface; can be mapped |
| `OrderPlaced` | Actual class of the payload; can have a dedicated branch |
| Header `eventType=PAYMENT` if present | Does not automatically participate in `PayloadTypeRouter`'s decision |

Spring defines `PayloadTypeRouter` as a router that resolves channels based on payload type. Therefore, verify what type the data has been decoded into before placing the router in the flow. See [PayloadTypeRouter API](https://docs.spring.io/spring-integration/api/org/springframework/integration/router/PayloadTypeRouter.html).

The router chooses where to send the message. A transformer placed before the router can change the type the router observes; the router itself does not turn an order event into a payment event.

## 3. From payload type to target channel

The decision can be broken down into three steps:

1. Find a matching type among the configured types.
2. Retrieve the channel name associated with the selected type.
3. Resolve that name to a `MessageChannel` bean, then send the message.

~~~mermaid
flowchart LR
    A["eventInput: Message with payload"] --> R["PayloadTypeRouter"]
    R -->|"OrderPlaced"| O["orderEvents"]
    R -->|"PaymentCaptured"| P["paymentEvents"]
    R -->|"Matching BusinessEvent"| B["otherBusinessEvents"]
    R -->|"No matching type"| U["unsupportedEvents"]
~~~

A Java mapping looks like:

~~~java
router.setChannelMapping(
        OrderPlaced.class.getName(),
        "orderEvents");
~~~

The two arguments carry different meanings:

- `OrderPlaced.class.getName()` is the type key, consisting of the fully qualified class name.
- `"orderEvents"` is the channel bean name in the Spring context.

Obtain the key via `Class.getName()` instead of typing the class name by hand. This avoids bugs when renaming packages and handles nested class names containing `$` correctly. The target channel still must be declared; a string name in the mapping does not automatically create the bean.

Configuring a router instance and passing it into `.route(router)` is directly supported by Spring Integration. See [Router Implementations](https://docs.spring.io/spring-integration/reference/6.5/router/implementations.html).

## 4. Choosing concrete types, superclasses, and interfaces

### 4.1. Exact mapping takes precedence

Suppose `OrderPlaced` implements `BusinessEvent`, and both types have mappings:

~~~text
OrderPlaced   -> orderEvents
BusinessEvent -> otherBusinessEvents
~~~

A message containing `OrderPlaced` goes to `orderEvents`; it is not additionally sent to `otherBusinessEvents`.

A general branch can absorb new events implementing `BusinessEvent`, while specific classes have dedicated branches. The general branch must be able to handle the event types it may receive.

### 4.2. Superclasses or interfaces can be mapped

| Configured mapping | Payload | Result |
| --- | --- | --- |
| Only `Number -> numericEvents` | `Integer.valueOf(10)` | `numericEvents` |
| `Number -> numericEvents` and `Integer -> integerEvents` | `Integer.valueOf(10)` | `integerEvents` |
| Only `BusinessEvent -> otherBusinessEvents` | `RefundRequested` implementing `BusinessEvent` | `otherBusinessEvents` |

Do not interpret this as "whichever mapping was declared first wins". The router evaluates type fitness. With complex type hierarchies, you also cannot assume every superclass always outranks every interface: the 6.5.x implementation computes weights based on type relationships, where a direct interface can take precedence over a superclass. See [PayloadTypeRouter 6.5.x source](https://github.com/spring-projects/spring-integration/blob/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/router/PayloadTypeRouter.java).

### 4.3. Multiple equally matching types can cause an error

Consider a payload implementing two independent interfaces:

~~~java
interface Auditable {
}

interface Retriable {
}

record MaintenanceRequested(String requestId)
        implements Auditable, Retriable {
}
~~~

If the only mappings are:

~~~text
Auditable -> auditEvents
Retriable -> retryEvents
~~~

Both direct interfaces have the same fitness level. The router does not treat this as a request to send to both channels; ambiguous cases are rejected. In 6.5.x, the type-selection algorithm throws `IllegalStateException`; when flowing through message-handling machinery, the error may be wrapped in a messaging exception.

You can add an exact mapping for `MaintenanceRequested`, or reorganize the payload types so the rule produces a single result. If business logic requires broadcasting to multiple recipients, choose a recipient list or publish-subscribe pattern.

Cases involving superclasses, interfaces, and ambiguous mappings are illustrated in [PayloadTypeRouter tests](https://github.com/spring-projects/spring-integration/blob/6.5.x/spring-integration-core/src/test/java/org/springframework/integration/router/PayloadTypeRouterTests.java).

## 5. Complete example: routing events

The example uses one input `DirectChannel` and four output `QueueChannel` beans for easy observation and testing. These channels live in application memory.

Place the configuration in `TypeRoutingConfig.java`:

~~~java
package example.integration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.router.PayloadTypeRouter;

@Configuration
@EnableIntegration
public class TypeRoutingConfig {

    public interface BusinessEvent {
    }

    public record OrderPlaced(String orderId) implements BusinessEvent {
    }

    public record PaymentCaptured(String paymentId, String orderId)
            implements BusinessEvent {
    }

    public record RefundRequested(String orderId) implements BusinessEvent {
    }

    @Bean
    public DirectChannel eventInput() {
        return new DirectChannel();
    }

    @Bean
    public QueueChannel orderEvents() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel paymentEvents() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel otherBusinessEvents() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel unsupportedEvents() {
        return new QueueChannel(100);
    }

    @Bean
    public PayloadTypeRouter eventTypeRouter() {
        PayloadTypeRouter router = new PayloadTypeRouter();

        router.setChannelMapping(
                OrderPlaced.class.getName(), "orderEvents");
        router.setChannelMapping(
                PaymentCaptured.class.getName(), "paymentEvents");
        router.setChannelMapping(
                BusinessEvent.class.getName(), "otherBusinessEvents");

        router.setChannelKeyFallback(false);
        router.setDefaultOutputChannelName("unsupportedEvents");
        router.setResolutionRequired(true);
        router.setSendTimeout(1_000);

        return router;
    }

    @Bean
    public IntegrationFlow eventRoutingFlow(
            PayloadTypeRouter eventTypeRouter) {

        return IntegrationFlow.from("eventInput")
                .route(eventTypeRouter)
                .get();
    }
}
~~~

Core roles in the flow:

- `Message` carries the event and headers.
- `eventInput` is the receiving channel.
- `PayloadTypeRouter` is the handler selecting the target.
- Java DSL builds the flow and endpoint wiring the handler to the input channel.
- The queues hold messages for receivers to pull and process.

`setChannelKeyFallback(false)` expresses the policy to use only declared mappings. `setResolutionRequired(true)` catches a mapped channel name that does not exist. The `unsupportedEvents` branch is for payloads with no matching type, not a substitute for configuration error reporting.

Each queue has a capacity of 100 messages; the router waits up to 1,000 ms on send if the channel requires waiting. In a real application, arrange consumers and choose appropriate capacities. `QueueChannel` instances created this way do not persist data across application restarts.

### 5.1. Sending a test message

The following snippet can go in a runner method of a class in the same package:

~~~java
try (var context =
        new org.springframework.context.annotation.AnnotationConfigApplicationContext(
                TypeRoutingConfig.class)) {

    var input = context.getBean(
            "eventInput",
            org.springframework.messaging.MessageChannel.class);

    var message = org.springframework.messaging.support.MessageBuilder
            .withPayload(new TypeRoutingConfig.OrderPlaced("ORD-1001"))
            .setHeader("traceId", "trace-01")
            .build();

    boolean sent = input.send(message);
    if (!sent) {
        throw new IllegalStateException("Failed to send message");
    }

    var orders = context.getBean(
            "orderEvents",
            org.springframework.integration.channel.QueueChannel.class);

    var routed = orders.receive(1_000);
    if (routed == null) {
        throw new IllegalStateException("Order event not received");
    }

    System.out.println(routed.getPayload());
    System.out.println(routed.getHeaders().get("traceId"));
}
~~~

When the queue is not full, `send()` completes once the router delivers to the queue. That does not mean business work like sending emails or updating a database has finished. The example currently stops at routing and receiving the message.

To process business work from the queue, you can create a consumer with a poller. If the output uses a `DirectChannel`, the downstream handler runs synchronously on the sending thread under normal configuration.

### 5.2. Endpoint option with annotation

Another way to wire it is adding the following annotation to the existing `@Bean eventTypeRouter()` method:

~~~java
@org.springframework.integration.annotation.ServiceActivator(
        inputChannel = "eventInput")
~~~

When using this option, keep the router configuration method body and remove the corresponding `eventRoutingFlow` bean. Keep only one router endpoint at the connection point under test; keeping both creates two subscribers on `DirectChannel` and changes message distribution.

## 6. Does Java DSL with Object::getClass behave the same way?

Java DSL allows a function that returns a routing key. You can replace the flow bean in the main example with the following method placed in the same configuration class:

~~~java
@Bean
public IntegrationFlow eventRoutingFlow() {
    return IntegrationFlow.from("eventInput")
            .<Object, Class<?>>route(
                    Object::getClass,
                    routes -> routes
                            .channelMapping(
                                    OrderPlaced.class, "orderEvents")
                            .channelMapping(
                                    PaymentCaptured.class, "paymentEvents")
                            .channelKeyFallback(false)
                            .defaultOutputChannel("unsupportedEvents"))
            .get();
}
~~~

The lambda returns the exact runtime class. A router using this function maps keys by the returned value; it does not perform `PayloadTypeRouter`'s superclass/interface lookup algorithm.

| Payload | `PayloadTypeRouter` in section 5 | Lambda in section 6 |
| --- | --- | --- |
| `OrderPlaced` | `orderEvents` | `orderEvents` |
| `PaymentCaptured` | `paymentEvents` | `paymentEvents` |
| `RefundRequested` | `otherBusinessEvents` via interface | `unsupportedEvents` |
| `String` | `unsupportedEvents` | `unsupportedEvents` |

Even if you add `.channelMapping(BusinessEvent.class, "otherBusinessEvents")` to the lambda configuration, `Object::getClass` still returns `RefundRequested.class`, not `BusinessEvent.class`.

If you want to group types manually inside a lambda, you must express the rules using logic such as `instanceof` and return an appropriate business key. To take advantage of existing inheritance relationships, using `PayloadTypeRouter` directly usually communicates intent more clearly. Configuring `route()` with a router object, expression, or lambda is covered in [Message Routers with Java DSL](https://docs.spring.io/spring-integration/reference/6.5/dsl/java-routers.html).

## 7. Type mismatch and routing errors

### 7.1. Four situations to distinguish

With the configuration in section 5:

| Situation | Example | Expected behavior |
| --- | --- | --- |
| No matching type | `String` payload | Sent to `unsupportedEvents` |
| Matching type, but channel does not exist | `OrderPlaced` mapped to `orderEvnts` | Channel resolution error because `resolutionRequired=true` |
| Ambiguous type match | Two direct interfaces both mapped | Error during type selection; default does not resolve ambiguity |
| Channel exists, but send/processing fails | Queue full past timeout or synchronous handler throws | Send/processing error; does not automatically fall back to default |

`defaultOutputChannel` is for when the router has no suitable target. It is not a `catch` block wrapping every flow error.

By default, `ignoreSendFailures=false`. With `DirectChannel`, errors deeper in a synchronous branch can propagate back to the router's send operation. See [Common Router Parameters](https://docs.spring.io/spring-integration/reference/6.5/router/common-parameters.html).

### 7.2. resolutionRequired does not replace the default branch

`resolutionRequired` controls **channel name resolution** errors:

- `true`: an unresolvable target name raises an error.
- `false`: allows skipping unresolvable targets; when no targets remain, the router can use the configured default.

If there is no target channel and no default either, the router can still throw `MessageDeliveryException`. Simply setting `resolutionRequired=false` does not mean the message goes to `errorChannel` or is intentionally discarded.

Since Spring Integration 6.0, setting a default output channel also sets `channelKeyFallback=false` unless explicitly configured otherwise. The main example declares it explicitly so readers see the policy. If you re-enable key fallback manually, examine its interaction with `resolutionRequired`: combining a default channel with `channelKeyFallback=true` and `resolutionRequired=true` is rejected at initialization. See [rules in AbstractMappingMessageRouter](https://github.com/spring-projects/spring-integration/blob/6.5.x/spring-integration-core/src/main/java/org/springframework/integration/router/AbstractMappingMessageRouter.java).

### 7.3. Policies for unknown payloads and execution errors

You can keep unknown payloads in `unsupportedEvents` together with `traceId` to inspect the sender or decoding step. This branch needs a consumption process; letting messages pile up indefinitely will fill the buffer.

If the input contract permits only a fixed set of types and violations must be caught immediately, omit the default so missing targets raise an error. If you intentionally want to discard messages, Spring Integration provides `nullChannel`; that choice must align with business requirements.

Execution errors need their own policy at flow boundaries. With direct calls into `DirectChannel`, exceptions typically propagate back to the `send()` caller; merely adding an `errorChannel` header does not turn that call into asynchronous error publishing. When a poller, executor, or gateway handles errors, configure according to that component's mechanism.

Do not infinitely retry missing-mapping or misspelled channel-bean errors. Replaying the same message without changing the configuration will not create a valid target.

## 8. Testing routing decisions

The code below uses JUnit Jupiter, a Spring context, and the configuration from section 5. It requires `spring-integration-core` and compatible Spring dependencies; your project can manage versions via an existing BOM.

Each test creates a fresh context. The helper verifies that exactly one queue receives the same payload and tracing header, while the remaining queues stay empty. No `Thread.sleep()` is used.

Place the code in `TypeRoutingConfigTest.java`, in the same package as the configuration:

~~~java
package example.integration;

import java.util.List;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;

import static org.junit.jupiter.api.Assertions.*;

class TypeRoutingConfigTest {

    private AnnotationConfigApplicationContext context;
    private MessageChannel input;

    @BeforeEach
    void setUp() {
        context = new AnnotationConfigApplicationContext(
                TypeRoutingConfig.class);
        input = context.getBean("eventInput", MessageChannel.class);
    }

    @AfterEach
    void tearDown() {
        context.close();
    }

    @Test
    void concreteOrderTypeWinsOverBusinessEventInterface() {
        assertOnlyRoute(
                new TypeRoutingConfig.OrderPlaced("ORD-1001"),
                "orderEvents");
    }

    @Test
    void paymentTypeUsesItsDedicatedQueue() {
        assertOnlyRoute(
                new TypeRoutingConfig.PaymentCaptured("PAY-1", "ORD-1001"),
                "paymentEvents");
    }

    @Test
    void eventWithoutDedicatedMappingUsesBusinessEventInterface() {
        assertOnlyRoute(
                new TypeRoutingConfig.RefundRequested("ORD-1001"),
                "otherBusinessEvents");
    }

    @Test
    void unrelatedPayloadUsesDefaultQueue() {
        assertOnlyRoute("unrecognized payload", "unsupportedEvents");
    }

    private void assertOnlyRoute(Object payload, String expectedChannel) {
        Message<?> source = MessageBuilder.withPayload(payload)
                .setHeader("traceId", "trace-test")
                .build();

        assertTrue(input.send(source));

        for (String name : List.of(
                "orderEvents",
                "paymentEvents",
                "otherBusinessEvents",
                "unsupportedEvents")) {

            QueueChannel queue = context.getBean(name, QueueChannel.class);

            if (name.equals(expectedChannel)) {
                Message<?> result = queue.receive(1_000);
                assertNotNull(result, "Missing message in " + name);
                assertSame(payload, result.getPayload());
                assertEquals(
                        "trace-test",
                        result.getHeaders().get("traceId"));
                assertNull(queue.receive(0), "Extra message in " + name);
            }
            else {
                assertNull(queue.receive(0), "Misrouted to " + name);
            }
        }
    }
}
~~~

`assertSame(payload, result.getPayload())` verifies that the in-memory routing example does not replace the payload. This is not a promise of object identity preservation across a broker, serialization, or a transformer.

When modifying the configuration, add the following scenarios to your application's test suite:

| Variant | What to verify |
| --- | --- |
| Remove default, send unmapped type | Sender receives an error instead of silently losing the message |
| Misspell channel name in mapping | Target error is not treated as an unknown event |
| Map two direct interfaces of the same payload | Ambiguity error; check the root cause too if the exception is wrapped |
| Replace router with `Object::getClass` lambda | Events matching only an interface follow the new policy |
| Queue reaches full capacity | Send timeout behavior and how the caller handles it |

## 9. Limitations that easily cause misrouting

### 9.1. JSON has not become a business type yet

The following data is still just a `String` if the receiving step has not deserialized it:

~~~json
{
  "eventType": "ORDER_PLACED",
  "orderId": "ORD-1001"
}
~~~

The `eventType` field does not make the payload an `OrderPlaced`. Deserializing everything into a `Map` can also give multiple event types the same runtime class.

You can design in one of two directions:

~~~text
External data -> deserialize into business type
              -> PayloadTypeRouter -> Java-type branch
~~~

~~~text
External data -> read classification field or normalized header
              -> value-based router -> business branch
~~~

The first direction fits when the type model is the application's internal contract. The second fits when messages share one envelope and the event type sits inside the data.

### 9.2. Generic collections do not carry enough routing information

`List<OrderPlaced>` and `List<PaymentCaptured>` can both be `ArrayList` at runtime. `PayloadTypeRouter` does not rely on source-code generic type parameters to tell individual lists apart.

If each event must be processed individually, place a splitter before the router. If the list must travel as a whole batch, use dedicated wrapper types such as `OrderBatch` and `PaymentBatch`, or route based on explicit batch-type metadata.

### 9.3. Overly broad mappings hide unsupported data

Mapping `BusinessEvent` is an intentional decision: new events implementing this interface are accepted into the general branch.

If you add an overly broad mapping like `Object` for ordinary object payloads, lots of unexpected data will also count as having a branch. The default channel then ceases to be a useful indicator for those inputs.

Draw a clear line between "a valid event without a dedicated branch yet" and "unsupported input". The two cases may need different monitoring and handling.

### 9.4. Renaming classes affects mappings

Within the same application, using `SomeEvent.class.getName()` keeps mappings in sync with refactoring. If fully qualified class names are stored in external configuration, update that configuration whenever packages or classes are renamed.

For cross-system contracts, stable event codes like `ORDER_PLACED` are more independent of Java package structure. You can convert that code into a business object at the intake boundary, then use type routing inside the application.

## 10. Applying to flow design

Use `PayloadTypeRouter` when payload types reflect processing branches and you want to leverage class/interface relationships. Use exact mappings for specialized branches; add supertype mappings only when the general branch can handle every payload it might receive.

When reading or modifying a flow, verify in order: the runtime type at the router input, the selected mapping, the target channel, and the policy when there is no target. Tests should prove both that the right branch receives the message and that unselected branches do not. These checks keep the impact under control when adding a new event type.