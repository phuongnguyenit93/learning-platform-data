# UnicastingDispatcher

In the **SPRING_INTEGRATION_CORE** module, this lesson belongs to the **DirectChannel** chapter and explains how a message is delivered to a subscriber. It serves as the foundation for wiring endpoints, reading Java DSL flows, and understanding errors when multiple handlers share a channel.

**UnicastingDispatcher** is the dispatcher inside DirectChannel. It chooses the order in which handlers are tried and stops when one handler completes the call without throwing an exception. If failover is allowed, earlier handlers may have already been invoked and failed. Therefore, "unicast" does not mean every send always produces exactly one handler invocation. [UnicastingDispatcher Javadoc](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dispatcher/UnicastingDispatcher.html)

## 1. Objectives and Scope of Examples

After this lesson, you can:

- Distinguish channel, dispatcher, endpoint, and handler.
- Predict which handler is tried first when using round-robin or fixed ordering.
- Configure failover and recognize the risk of repeated business execution.
- Create two endpoints receiving from the same DirectChannel using Java DSL.
- Design tests for dispatch, errors, and execution flow.

The examples use **Java 17**, with the **Spring Integration 6.5.0** API as the reproducibility baseline. Specifically, `setFailoverStrategy(Predicate<Exception>)` has been available since **6.3**. This is the lesson's API baseline, not a claim about the latest version. [Failover strategy Javadoc](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dispatcher/UnicastingDispatcher.html#setFailoverStrategy(java.util.function.Predicate))

For standalone Maven, the primary dependency for the examples is:

~~~xml
<dependency>
    <groupId>org.springframework.integration</groupId>
    <artifactId>spring-integration-core</artifactId>
    <version>6.5.0</version>
</dependency>
~~~

If the project uses Spring Boot, let Boot's BOM manage the compatible version. The illustrations below do not require a broker, database, or external service.

## 2. Position in the Message Flow

~~~mermaid
flowchart LR
    P["Producer or gateway"] --> C["DirectChannel"]
    C --> D["UnicastingDispatcher"]
    D --> S["Handler attempt order"]
    S --> A["Handler A"]
    A -->|Succeeds| R["send returns"]
    A -->|Exception and failover allowed| B["Handler B"]
    B -->|Succeeds| R
    B -->|No candidates left or failover stops| E["Exception to caller"]
~~~

| Component | Responsibility |
| --- | --- |
| `Message<?>` | Carries a message's payload and headers. |
| `DirectChannel` | Provides the API for sending and registering subscribers. |
| `UnicastingDispatcher` | Performs message delivery under unicast semantics. |
| `LoadBalancingStrategy` | Determines the order in which handlers are tried. |
| Failover policy | Decides whether to continue to another handler after an exception. |
| Consumer endpoint | Manages connecting the handler to the input channel and endpoint lifecycle. |
| `MessageHandler` | Receives the `handleMessage(message)` call to process. |

At the implementation level, the channel's `subscribe()` and `unsubscribe()` delegate adding or removing handlers to the dispatcher; `doSend()` delegates message delivery to `dispatch()`. [AbstractSubscribableChannel Source](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/channel/AbstractSubscribableChannel.java)

You typically configure **DirectChannel** without creating a separate UnicastingDispatcher bean. `getDispatcher()` on DirectChannel is `protected`; public setters on the channel forward configuration down to the dispatcher. [DirectChannel Source](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/channel/DirectChannel.java)

### Unicast vs. Broadcast

For order `ORDER-701`, two handlers both performing the "record order" business task can be two interchangeable alternatives. DirectChannel fits this structure.

If the same event must go to both accounting and email sending, you need a multi-branch dispatch structure such as PublishSubscribeChannel. Multiple subscribers on DirectChannel do not turn the channel into broadcast. [Message Channel Implementations](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html)

## 3. What Happens During a Single Dispatch?

You can read the mechanism in four steps:

1. Obtain the currently registered handlers and the attempt order.
2. Invoke the first handler in that order.
3. If the call completes normally, finish the dispatch.
4. If an exception occurs, evaluate the failover policy: try the next candidate or finish with an error.

The dispatcher does not automatically wait and retry the same handler. With standard round-robin and a stable subscriber set, the candidate list contains each handler once in a single dispatch pass. [UnicastingDispatcher Source](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/dispatcher/UnicastingDispatcher.java), [RoundRobinLoadBalancingStrategy Source](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/dispatcher/RoundRobinLoadBalancingStrategy.java)

### Where Is "Success" Recognized?

The `MessageHandler.handleMessage()` contract returns `void`. At the dispatcher boundary, normal completion is treated as accepted processing; the dispatcher does not check order status in a database.

For example, a handler that catches an error and only logs it hides the error from the dispatcher:

~~~java
channel.subscribe(message -> {
    try {
        persistOrder(message.getPayload());
    }
    catch (RuntimeException ex) {
        logger.warn("Could not save order", ex);
        // Call completes normally: dispatcher does not fail over.
    }
});
~~~

This is an illustrative snippet: `persistOrder` and `logger` belong to the application. If the contract requires falling back to an alternative, the error must be surfaced past the appropriate processing boundary.

A filter that discards a message without throwing an exception also does not make the dispatcher look for another subscriber. By default, a filter can discard a message without raising an error; rejection behavior must be configured according to business requirements. [Message Filter Documentation](https://docs.spring.io/spring-integration/reference/6.5/filter.html)

Do not put competing filters on a DirectChannel expecting the channel to find whichever branch matches the payload. When business logic requires choosing a branch by order type or header, express that decision using a router. [Router Overview](https://docs.spring.io/spring-integration/reference/6.5/router/overview.html)

## 4. Round-Robin: Rotating the Starting Point

`new DirectChannel()` uses `RoundRobinLoadBalancingStrategy` by default. Failover is also enabled by default. These two options solve two different problems: choosing the attempt order and deciding whether to continue after an error. [DirectChannel Configuration](https://docs.spring.io/spring-integration/reference/6.4/channel/configuration.html)

Suppose A, B, C are registered in order, a single producer sends sequentially, subscribers do not change, and no errors occur:

| Send turn | Candidate order | Completing handler |
| --- | --- | --- |
| M1 | A → B → C | A |
| M2 | B → C → A | B |
| M3 | C → A → B | C |
| M4 | A → B → C | A |

If A fails on M1 and B succeeds, M1 finishes at B. M2's starting point is still B under the above conditions; round-robin rotates per dispatch turn, not based on "most recent successful handler". [How round-robin builds an iterator](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/dispatcher/RoundRobinLoadBalancingStrategy.java)

### Standalone Java Example

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.GenericMessage;

public class RoundRobinDemo {

    public static void main(String[] args) {
        DirectChannel orders = new DirectChannel();
        List<String> events = new ArrayList<>();
        Thread sender = Thread.currentThread();

        orders.subscribe(message -> {
            requireSenderThread(sender);
            events.add("A:" + message.getPayload());
        });

        orders.subscribe(message -> {
            requireSenderThread(sender);
            events.add("B:" + message.getPayload());
        });

        for (int number = 1; number <= 4; number++) {
            Message<String> message =
                    new GenericMessage<>("ORDER-" + number);

            if (!orders.send(message)) {
                throw new IllegalStateException("Could not send message");
            }
        }

        System.out.println(events);
    }

    private static void requireSenderThread(Thread sender) {
        if (Thread.currentThread() != sender) {
            throw new IllegalStateException("Handler switched threads");
        }
    }
}
~~~

Expected output:

~~~text
[A:ORDER-1, B:ORDER-2, A:ORDER-3, B:ORDER-4]
~~~

The example subscribes handlers directly to observe the dispatcher without initializing a Spring context.

### Rotation Does Not Mean Parallel Processing

DirectChannel invokes handlers on the sending thread. While M1 is running a slow handler, a sequential producer cannot yet send M2 through the same call sequence. [DirectChannel Javadoc](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/channel/DirectChannel.html)

Consequently, adding subscribers does not automatically increase thread count. If there are multiple concurrent producers, the same handler can be called by multiple threads; shared handler state still needs protection. Round-robin also does not balance load by processing time or active task count.

## 5. Fixed Order and Failover

When you have a primary option and a backup option, you can disable load balancing:

~~~java
DirectChannel orders = new DirectChannel(null);
orders.setFailover(true);
~~~

`null` in the constructor means no load balancing strategy is used. In that case, handler attempts start according to the subscriber set's ordering. If you want to stop immediately on the first error, use `setFailover(false)`. [DirectChannel Configuration API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/channel/DirectChannel.html)

Complete example:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.support.GenericMessage;

public class FixedOrderFailoverDemo {

    public static void main(String[] args) {
        DirectChannel orders = new DirectChannel(null);
        orders.setFailover(true);

        List<String> attempts = new ArrayList<>();

        orders.subscribe(message -> {
            attempts.add("primary:" + message.getPayload());
            throw new IllegalStateException("Primary warehouse temporarily paused");
        });

        orders.subscribe(message ->
                attempts.add("backup:" + message.getPayload()));

        boolean delivered = orders.send(new GenericMessage<>("ORDER-701"));

        System.out.println("delivered=" + delivered);
        System.out.println(attempts);
    }
}
~~~

Expected output, excluding framework logs:

~~~text
delivered=true
[primary:ORDER-701, backup:ORDER-701]
~~~

The first handler was invoked, threw an exception, and then the second handler completed. A single send produced two processing attempts.

| Configuration | Starting point | If the first handler fails |
| --- | --- | --- |
| `new DirectChannel()` | Rotates | Defaults to trying the next handler |
| Default channel + `setFailover(false)` | Rotates | Stops and raises error |
| `new DirectChannel(null)` | In fixed order | Defaults to trying the next handler |
| Fixed order + `setFailover(false)` | In fixed order | Stops and raises error immediately |

Do not rely on bean declaration order to express the primary option. When using endpoints, set `order` explicitly; lower numeric values take priority first. For direct handlers without order metadata as in the example above, insertion order is preserved. [Dispatcher's ordered handler set](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/dispatcher/OrderedAwareCopyOnWriteArraySet.java)

## 6. Fail Over Only for Suitable Error Types

A transient connection failure and an order with invalid data require different policies. Since Spring Integration 6.3, you can configure a predicate instead of enabling failover for every exception. `setFailover()` and `setFailoverStrategy()` replace each other's policy; do not treat them as two conditions combined together. [Exception-based failover configuration](https://docs.spring.io/spring-integration/reference/channel/configuration.html)

The following example allows forwarding only if the cause chain contains an application-defined transient error:

~~~java
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.support.GenericMessage;

public class SelectiveFailoverDemo {

    static class TemporaryStoreException extends RuntimeException {
        TemporaryStoreException(String message) {
            super(message);
        }
    }

    public static void main(String[] args) {
        DirectChannel orders = new DirectChannel(null);
        orders.setFailoverStrategy(SelectiveFailoverDemo::isTemporaryFailure);

        orders.subscribe(message -> {
            String order = (String) message.getPayload();

            if (order.isBlank()) {
                throw new IllegalArgumentException("Missing order ID");
            }

            throw new TemporaryStoreException("Primary warehouse not ready");
        });

        orders.subscribe(message ->
                System.out.println("Backup received " + message.getPayload()));

        orders.send(new GenericMessage<>("ORDER-701"));
    }

    private static boolean isTemporaryFailure(Exception failure) {
        Throwable current = failure;

        while (current != null) {
            if (current instanceof TemporaryStoreException) {
                return true;
            }
            current = current.getCause();
        }

        return false;
    }
}
~~~

With payload `ORDER-701`, backup is invoked. If replaced with an empty string, the validation error causes the predicate to return `false`; backup is not invoked.

Walking the cause chain helps the example work when business errors sit inside an endpoint's wrapper exception. In an application, the predicate should be brief, deterministic, and not throw errors itself.

**Failover is not retry:** this example tries an alternative option rather than waiting for an interval and calling the primary warehouse again. It also has no memory to exclude the primary warehouse from subsequent sends.

## 7. Which Exceptions Reach the Caller?

Distinguish errors at the dispatcher from errors observed through the channel API.

| Situation | Behavior to understand |
| --- | --- |
| No subscribers | The dispatcher throws `MessageDispatchingException`; through DirectChannel, this is wrapped as `MessageDeliveryException`. |
| Single handler and handler fails | The processing error is propagated via the message-delivery wrapping mechanism. |
| Multiple handlers, failover disabled, first handler fails | Stops after the first attempt. |
| Multiple attempts all fail | When the failure list contains multiple elements, the dispatcher throws `AggregateMessageDeliveryException`. |
| An earlier handler fails but a later handler succeeds | `send()` may return `true`; the earlier error does not become the final exception of the send call. |

Do not read a general Javadoc statement like "all handlers fail" as "always receive `AggregateMessageDeliveryException`". In the 6.5.0 implementation, a single failure is propagated directly; multiple failures are aggregated. [UnicastingDispatcher Error Handling Source](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/dispatcher/UnicastingDispatcher.java)

The channel layer performs the wrapping when there are no subscribers, so check the cause when inspecting this error. [AbstractSubscribableChannel Source](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/channel/AbstractSubscribableChannel.java)

### Optimized Path When There Is One Handler

`AbstractDispatcher` has a direct invocation path for the single-subscriber case. In that case there is no alternative handler; do not rely on the failover predicate being called to record every processing error. [AbstractDispatcher Source](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/dispatcher/AbstractDispatcher.java)

### `errorChannel` Does Not Automatically Receive Every Synchronous Error

When calling `DirectChannel.send()` directly, synchronous processing exceptions are returned to the caller. Merely setting the `errorChannel` header does not turn this call into an automatic `ErrorMessage` publisher. Gateways or asynchronous components have their own error-forwarding mechanisms that must be configured accordingly. [Error Handling Documentation](https://docs.spring.io/spring-integration/reference/6.5/error-handling.html)

For instance, the producer must decide whether to return an error to the API client, record the failure, or route to an error-handling flow. Do not catch and ignore exceptions just to make `send()` appear successful.

## 8. Two Endpoints Sharing a DirectChannel with Java DSL

In a Spring application, endpoints are managed by the container. The following two flows register two handlers onto the same `ordersInput` bean.

The example selects fixed order: the primary endpoint has `order(0)`, and the backup endpoint has `order(1)`. The configuration below is a complete Java class:

~~~java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
@EnableIntegration
public class OrderFlowConfiguration {

    @Bean
    public DirectChannel ordersInput() {
        DirectChannel channel = new DirectChannel(null);
        channel.setFailover(true);
        return channel;
    }

    @Bean
    public IntegrationFlow primaryOrders(DirectChannel ordersInput) {
        return IntegrationFlow.from(ordersInput)
                .handle(String.class, (order, headers) -> {
                    if (Boolean.TRUE.equals(
                            headers.get("simulatePrimaryFailure"))) {
                        throw new IllegalStateException(
                                "Primary path temporarily unable to process");
                    }

                    System.out.println("Primary: " + order);
                    return null;
                }, endpoint -> endpoint
                        .id("primaryOrderEndpoint")
                        .order(0)
                        .requiresReply(false))
                .get();
    }

    @Bean
    public IntegrationFlow backupOrders(DirectChannel ordersInput) {
        return IntegrationFlow.from(ordersInput)
                .handle(String.class, (order, headers) -> {
                    System.out.println("Backup: " + order);
                    return null;
                }, endpoint -> endpoint
                        .id("backupOrderEndpoint")
                        .order(1)
                        .requiresReply(false))
                .get();
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                OrderFlowConfiguration.class)) {

            DirectChannel input =
                    context.getBean("ordersInput", DirectChannel.class);

            input.send(MessageBuilder.withPayload("ORDER-701")
                    .setHeader("simulatePrimaryFailure", true)
                    .build());

            input.send(MessageBuilder.withPayload("ORDER-702")
                    .build());
        }
    }
}
~~~

Excluding framework logs, expected business output:

~~~text
Backup: ORDER-701
Primary: ORDER-702
~~~

`IntegrationFlow` acts as a description of components to register in the context; overloads of `handle()` let you configure the handler alongside its endpoint. [IntegrationFlow API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/IntegrationFlow.html), [handle API in DSL](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/BaseIntegrationFlowDefinition.html)

`order()` sets handler order; `requiresReply(false)` allows completing without generating a reply. In the example, `return null` ends a one-way send task—it does not ask the dispatcher to try backup. [ConsumerEndpointSpec API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/ConsumerEndpointSpec.html)

Points to observe:

- `ORDER-701` enters the primary endpoint first; the exception triggers trying the backup endpoint.
- `ORDER-702` starts at the primary endpoint again. The earlier failover does not automatically shift all future traffic to backup.
- Replacing `new DirectChannel(null)` with `new DirectChannel()` makes the two endpoints compete via round-robin.
- A gateway sending commands into `ordersInput` still passes through this same mechanism. If the gateway awaits a reply, alternative branches must share a compatible reply contract.

The example uses broad failover for easy observation. When applying it to real business logic, replace the policy with a predicate as in section 6 if only certain errors qualify for switching.

### Distinguishing Two Alternative Handlers from Two Sequential Steps

Two flows both starting from one DirectChannel are competing subscribers. To transform an order and then save the order, chain a transformer and a service activator as steps of a single flow.

Similarly, if you need an aggregator to collect multiple results, you must explicitly design message-branching and correlation. Registering additional handlers on DirectChannel does not produce those multiple results automatically.

## 9. Implications for Transactions and Side Effects

DirectChannel keeps the call on the producer's thread, so an existing transaction can span processing on both sides of the channel. The channel does not create a transaction on its own. Participation still depends on the transaction manager and the resources used. [DirectChannel and Transactions](https://docs.spring.io/spring-integration/reference/6.5/channel/implementations.html)

From the failover mechanism, the following scenario can be deduced:

~~~text
1. Primary handler sends a payment command to an external system.
2. External system charges the account, but the response is lost.
3. Primary handler throws a timeout exception.
4. Dispatcher forwards the same request to the backup handler.
5. Backup handler sends another payment command.
~~~

Without a deduplication key, the customer may be charged twice. One handler finishing normally does not prove only one handler caused side effects.

Design for this scenario must define:

- A stable business key, such as `paymentRequestId`, preserved across attempts.
- How the receiving system handles duplicate requests.
- Whether the outcome of an earlier call can be verified before executing an alternative.
- Commit/rollback boundaries and operations outside local transactions.

You also cannot conclude "if backup succeeds, the transaction is guaranteed to commit". If an earlier operation already marked the transaction rollback-only, the commit outcome remains subject to that state.

### An Error at a Later Step Can Trigger Retrying the Whole Branch

Suppose subscriber A starts a synchronous branch:

~~~text
DirectChannel → handler A → another DirectChannel → data-writing handler
~~~

If the data-writing step throws an error and it propagates back to handler A's call, the first dispatcher may treat the entire attempt of branch A as failed and invoke B. This deduction comes from the synchronous call stack: the impact scope to examine is all processing occurring before the subscriber call returns.

Therefore, failover is best suited when subscribers implement alternative approaches with the same business contract and side effects have been accounted for.

## 10. Testing Observable Behavior

The tests below serve as practice material for a project with **JUnit Jupiter**. They use direct handlers to isolate channel behavior without needing a Spring context or external infrastructure.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import org.springframework.integration.MessageDispatchingException;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dispatcher.AggregateMessageDeliveryException;
import org.springframework.messaging.MessageDeliveryException;
import org.springframework.messaging.support.GenericMessage;

import static org.junit.jupiter.api.Assertions.*;

class UnicastingBehaviorTest {

    @Test
    void roundRobinAlternatesAndRunsOnSenderThread() {
        DirectChannel channel = new DirectChannel();
        Thread sender = Thread.currentThread();
        List<String> received = new ArrayList<>();

        channel.subscribe(message -> {
            assertSame(sender, Thread.currentThread());
            received.add("A:" + message.getPayload());
        });

        channel.subscribe(message -> {
            assertSame(sender, Thread.currentThread());
            received.add("B:" + message.getPayload());
        });

        for (int number = 1; number <= 4; number++) {
            assertTrue(channel.send(new GenericMessage<>(number)));
        }

        assertEquals(List.of("A:1", "B:2", "A:3", "B:4"), received);
    }

    @Test
    void failoverCallsBackupAfterPrimaryFails() {
        DirectChannel channel = new DirectChannel(null);
        channel.setFailover(true);
        List<String> attempts = new ArrayList<>();

        channel.subscribe(message -> {
            attempts.add("primary");
            throw new IllegalStateException("Temporary failure");
        });

        channel.subscribe(message -> attempts.add("backup"));

        assertTrue(channel.send(new GenericMessage<>("ORDER-701")));
        assertEquals(List.of("primary", "backup"), attempts);
    }

    @Test
    void disablingFailoverKeepsBackupUntouched() {
        DirectChannel channel = new DirectChannel(null);
        channel.setFailover(false);
        AtomicInteger backupCalls = new AtomicInteger();

        channel.subscribe(message -> {
            throw new IllegalStateException("Primary failed");
        });

        channel.subscribe(message -> {
            backupCalls.incrementAndGet();
        });

        assertThrows(MessageDeliveryException.class,
                () -> channel.send(new GenericMessage<>("ORDER-701")));

        assertEquals(0, backupCalls.get());
    }

    @Test
    void missingSubscriberIsWrappedByChannel() {
        DirectChannel channel = new DirectChannel();

        MessageDeliveryException failure = assertThrows(
                MessageDeliveryException.class,
                () -> channel.send(new GenericMessage<>("ORDER-701")));

        assertInstanceOf(
                MessageDispatchingException.class, failure.getCause());
    }

    @Test
    void twoFailedAttemptsProduceAnAggregateFailure() {
        DirectChannel channel = new DirectChannel(null);
        channel.setFailover(true);

        channel.subscribe(message -> {
            throw new IllegalStateException("Primary failed");
        });

        channel.subscribe(message -> {
            throw new IllegalArgumentException("Backup failed");
        });

        assertThrows(AggregateMessageDeliveryException.class,
                () -> channel.send(new GenericMessage<>("ORDER-701")));
    }
}
~~~

The examples above present expected outcomes; this lesson does not claim they were executed in the current project.

For the Java DSL example, you should add integration-level checks:

| Scenario | What to confirm |
| --- | --- |
| Primary works | Primary is invoked, backup is not invoked. |
| Primary has transient failure | Backup processes the right payload and business key. |
| Primary has validation failure, using predicate | Backup is not invoked and caller receives error. |
| Endpoint is stopped | Subscriber count and message reception reflect lifecycle accurately. |
| Multiple concurrent producers | Shared data is safe; do not infer completion order from round-robin. |
| Primary caused a side effect then failed | Backup does not repeat unintended business work. |

With these synchronous tests, `Thread.sleep()` is unnecessary: when `send()` returns, the synchronous handler portion is finished. When testing an application with asynchronous boundaries, use completion signals suited to those boundaries.

## 11. Configuration Choices and Diagnostics

| Need | Design direction |
| --- | --- |
| One synchronous processing step, one consumer | DirectChannel with one subscriber |
| Multiple equivalent alternative handlers | DirectChannel with round-robin |
| Prioritized primary/backup | Disable load balancing, set explicit order, choose failover policy |
| Choose business flow by payload or header | Router and output channels |
| Every branch receives the event | PublishSubscribeChannel or multi-branch dispatch |
| Decouple sending from processing, buffering needed | Consider QueueChannel or broker-backed channel per requirements |
| Dispatch work via executor | ExecutorChannel; re-verify thread and transaction boundaries |

Channel choices have different semantics; specifically, UnicastingDispatcher is capable of using an executor, but **DirectChannel initializes its dispatcher without an executor**. Do not infer backwards that every UnicastingDispatcher is always synchronous. [UnicastingDispatcher Source](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/dispatcher/UnicastingDispatcher.java), [DirectChannel Source](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/channel/DirectChannel.java)

Some common diagnostic situations:

| Observation | What to check |
| --- | --- |
| Channel exists but send reports no subscribers | Was the endpoint created, started, and pointing to the right channel bean? |
| Only one of two tasks runs | Are both endpoints competing on DirectChannel instead of chained sequentially? |
| Error occurs yet backup does not run | Is failover disabled, did the predicate return false, or was the exception caught inside the handler? |
| Backup runs yet request still fails | Did backup or its downstream continue throwing an exception? |
| Message send succeeds yet no reply arrives | Does the flow produce a reply and does the gateway contract require one? |
| Adding subscribers does not speed things up | Is the producer sending sequentially on one thread? |
| An order is processed multiple times | Have you checked failover, retries at another layer, and deduplication keys? |

`setMaxSubscribers(...)` can limit the number of registered handlers; it is not a limit on concurrent requests or queue length. [DirectChannel API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/channel/DirectChannel.html)

When extending `LoadBalancingStrategy`, the core contract is creating an iterator from a message and the handler collection. Test candidate ordering, concurrency safety when sending simultaneously, and policy when the subscriber list changes. [LoadBalancingStrategy Source](https://github.com/spring-projects/spring-integration/blob/v6.5.0/spring-integration-core/src/main/java/org/springframework/integration/dispatcher/LoadBalancingStrategy.java)

A custom strategy does not automatically add persistence, retries, or an exactly-once processing guarantee. Those requirements must be addressed at the corresponding components and business boundaries.
