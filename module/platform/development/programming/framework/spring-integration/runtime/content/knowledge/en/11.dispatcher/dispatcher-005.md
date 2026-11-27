# FailoverLoadBalancingStrategy in Spring Integration

## Objectives

In Spring Integration, a point-to-point channel can have multiple `MessageHandler` instances subscribed to receive messages. The dispatcher needs to answer two questions:

1. **Load balancing:** which handler is tried first for the current message?
2. **Failover:** if that handler throws an exception, should the dispatcher try the next handler or stop?

These two decisions combine to produce the behavior commonly called *failover with load balancing*. In the Spring Integration API, they are two separate configurations: `LoadBalancingStrategy` determines the handler trial order; the `failover` property or `Predicate<Exception> failoverStrategy` decides whether to continue after a failure.

> **Note on naming:** do not assume that Spring Integration Core provides a built-in class named `FailoverLoadBalancingStrategy` to instantiate directly. The standard API describes `LoadBalancingStrategy` and a separate failover mechanism on the dispatcher. If your project has a class with that name, check whether it is a custom project implementation.

After this article, you will be able to configure round-robin or primary/backup ordering, classify exceptions to decide failover, and recognize limitations related to transactions, executors, and side effects.

## 1. What Problem Does the Dispatcher Solve?

`DirectChannel` is a point-to-point channel: each message is processed successfully by one subscriber. However, multiple subscribers can subscribe to the channel. `DirectChannel` delegates subscriber selection to `UnicastingDispatcher`.

`UnicastingDispatcher` tries handlers in the order determined by the load-balancing strategy. When a handler processes the message without throwing an exception, the dispatcher considers dispatch successful and stops; the remaining handlers do not receive that message. If a handler fails and failover is permitted, the dispatcher can try the next handler. Thus, a single message may go through multiple attempts within one dispatch, yet once one handler succeeds, the process ends.

If no handlers are registered, the dispatcher throws `MessageDispatchingException`. If all tried handlers throw exceptions, the dispatcher throws `AggregateMessageDeliveryException`.

## 2. Separating Load Balancing and Failover

| Mechanism | Question It Answers | Common Configuration |
|---|---|---|
| Load balancing | Which handler to start with and in what order? | `round-robin`, `none`, or a bean implementing `LoadBalancingStrategy` |
| Failover | When the current handler throws an exception, should the next handler be tried? | `failover=true/false` or `failoverStrategy` |
| Retry | Should the same processing step be retried according to attempt count, delay, and backoff? | Retry advice / dedicated retry mechanism |
| Error flow | When processing fails, how is the error message routed and handled? | `errorChannel`, error handler, router |

Load balancing does not imply failover on its own. Conversely, failover does not determine priority ordering. Both mechanisms are applied together on a unicast dispatcher.

With the default `DirectChannel`:

- Load balancing uses round-robin.
- Failover is enabled.
- Both only take effect when the channel has multiple subscribers.

`ExecutorChannel` supports the same dispatcher configuration. Details about its execution flow and transaction behavior differ from `DirectChannel` and are covered later.

## 3. Dispatch and Failover Flow

~~~mermaid
flowchart TD
    A[Application sends Message to channel] --> B[UnicastingDispatcher]
    B --> C[LoadBalancingStrategy determines trial order]
    C --> D[Dispatcher invokes MessageHandler]
    D -->|Handler succeeds| E[Stop dispatch]
    D -->|Handler throws Exception| F{Is failover permitted?}
    F -->|Yes| G[Try next handler]
    G --> D
    F -->|No| H[Return error to caller]
    G -->|No more handlers| I[AggregateMessageDeliveryException]
~~~

You can read this flow step by step:

1. An endpoint sends a `Message` into the channel.
2. The dispatcher retrieves the current list of subscribers and determines the trial order.
3. The dispatcher invokes the first handler in that order.
4. If the handler completes normally, the dispatcher ends the dispatch.
5. If the handler throws an exception, the dispatcher evaluates the failover policy.
6. If permitted, the dispatcher tries the next handler. If not, the error is propagated according to the execution context.
7. If all handlers fail, the dispatcher raises an aggregate error.

A handler is considered successful when its invocation returns normally. If the handler catches an exception itself and returns normally, the dispatcher does not know that internal business logic failed and will not move to another handler.

## 4. Handler Selection Modes

### 4.1. Round-Robin

Round-robin rotates the starting point among subscribers. This is useful when multiple workers have equivalent capacity and can all process the same message type.

The default `DirectChannel` configuration already uses round-robin with failover enabled:

~~~java
@Bean
public DirectChannel workChannel() {
    return new DirectChannel();
}
~~~

You can declare this explicitly in XML:

~~~xml
<int:channel id="workChannel">
    <int:dispatcher load-balancer="round-robin" failover="true"/>
</int:channel>
~~~

When a handler throws an exception, failover can cause the dispatcher to try subsequent handlers in dispatch order. Do not rely on a fixed handler sequence while using round-robin; if you need explicit primary, secondary, and tertiary roles, configure fixed ordering.

### 4.2. Fixed Order: Primary Then Backup

When one handler is primary and others are backups, disable load balancing with `none` so the dispatcher always starts at the first handler in subscriber order. Failover can remain enabled.

~~~xml
<int:channel id="orderWorkChannel">
    <int:dispatcher load-balancer="none" failover="true"/>
</int:channel>

<int:service-activator
        input-channel="orderWorkChannel"
        ref="primaryOrderHandler"
        method="handle"
        order="1"/>

<int:service-activator
        input-channel="orderWorkChannel"
        ref="backupOrderHandler"
        method="handle"
        order="2"/>
~~~

Both endpoints reference `orderWorkChannel`, so they register as subscribers on the same channel. With `load-balancer="none"`, the dispatcher starts at the handler with the higher-priority order. If the primary handler throws an exception and failover is permitted, the backup handler is tried next.

In the XML namespace, the endpoint's `order` attribute determines ordering. If order is not explicitly declared, subscriber registration order can determine processing order; do not depend on implicit ordering in a critical primary/backup setup.

Java configuration can create a channel with no load balancing using the constructor that accepts `null`:

~~~java
@Bean
public DirectChannel orderWorkChannel() {
    DirectChannel channel = new DirectChannel(null);
    channel.setFailover(true);
    return channel;
}
~~~

### 4.3. Disabling Failover to Fail Fast on Error

When you do not want another handler to continue processing after an error, set `failover=false`:

~~~java
@Bean
public DirectChannel failFastChannel() {
    DirectChannel channel = new DirectChannel();
    channel.setFailover(false);
    return channel;
}
~~~

With this configuration, the dispatcher only tries the initially selected handler for that dispatch. The exception is propagated according to the channel's execution context. This can be used when subscribers are not equivalent alternatives, or when errors must be handled by the caller, a retry layer, or an error flow.

## 5. Conditional Failover by Exception

Since Spring Integration 6.3, channels based on `UnicastingDispatcher` support `Predicate<Exception>` via `setFailoverStrategy`. The predicate decides whether to move to the next handler based on the exception that occurred.

Example: fail over only on transient data access errors:

~~~java
import org.springframework.dao.TransientDataAccessException;
import org.springframework.integration.channel.DirectChannel;

@Bean
public DirectChannel conditionalFailoverChannel() {
    DirectChannel channel = new DirectChannel();

    channel.setFailoverStrategy(exception ->
            exception instanceof TransientDataAccessException);

    return channel;
}
~~~

Meaning of the predicate:

- Returns `true`: permits the dispatcher to try the next handler.
- Returns `false`: stops failover at the current exception.

This classification prevents forwarding an unrecoverable data or business error to an unrelated backup handler. For example, a temporary connection error may warrant failover; a malformed payload error typically needs to stop and report the error.

`setFailoverStrategy` replaces the boolean `setFailover` option; choose the mechanism appropriate for your Spring Integration version. For versions prior to 6.3, use `failover=true/false`. If complex error analysis is needed, the Spring Integration documentation recommends considering `ErrorMessageExceptionTypeRouter` rather than cramming all routing logic into the predicate.

## 6. Customizing LoadBalancingStrategy

Beyond the built-in `round-robin` and `none` values, an application can provide a bean implementing `LoadBalancingStrategy` and reference it with `load-balancer-ref`.

~~~xml
<int:channel id="customBalancedChannel">
    <int:dispatcher load-balancer-ref="customLoadBalancer"
                    failover="true"/>
</int:channel>

<bean id="customLoadBalancer"
      class="com.example.integration.PriorityLoadBalancingStrategy"/>
~~~

`load-balancer` and `load-balancer-ref` are mutually exclusive; do not declare both simultaneously. A custom implementation is responsible for determining the handler order in accordance with the `LoadBalancingStrategy` contract. If the strategy maintains shared state, such as a counter or rotation index, ensure it is thread-safe when multiple threads send messages concurrently.

The load balancer only operates on subscribers visible to the channel's dispatcher. It does not perform service discovery across instances, check the health of remote nodes, or replace broker-level or infrastructure load balancing.

## 7. Limitations to Understand Before Enabling Failover

### 7.1. Failover Is Not Retry

Failover switches to another handler within the same dispatch after the current handler throws an exception. By default, it does not re-invoke the failed handler, does not add backoff, does not persist messages for later processing, and does not provide durable delivery guarantees.

If you need to retry the same processing step with attempt counts and intervals, use an appropriate retry mechanism. If you need to retain messages across application shutdown or restart, use a channel/store or broker with persistent storage and configure delivery accordingly.

### 7.2. Side Effects Can Be Repeated

Suppose the primary handler calls a payment service. The service receives the request and processes the payment, but the connection times out before the handler receives the response. The handler throws an exception; the dispatcher sends the message to the backup handler. The backup handler may resend the payment request and create a second transaction.

Therefore, failover does not guarantee exactly-once execution. Backup handlers must be semantically equivalent in business terms and should use idempotency keys or stable transaction IDs to prevent duplicate processing. Only enable failover when handing the same message to another handler is safe.

### 7.3. Handlers Must Let Errors Reach the Dispatcher

The dispatcher only evaluates exceptions thrown out of the handler invocation. If a handler swallows the exception:

~~~java
public void handle(Order order) {
    try {
        process(order);
    }
    catch (RuntimeException exception) {
        log.error("Order processing failed", exception);
        // Do not rethrow exception
    }
}
~~~

then the dispatcher considers the call to have completed normally and does not trigger failover. If you want the dispatcher to decide, allow an appropriate exception to propagate or forward the error to a dedicated error flow.

### 7.4. Failover Only Works with Multiple Subscribers

If only one endpoint is subscribed to the channel, there is no next handler to try. Verify that endpoints actually share the same `input-channel`. Two endpoints on two different channels do not form a failover group.

### 7.5. DirectChannel and ExecutorChannel Have Different Threading Semantics

| Characteristic | DirectChannel | ExecutorChannel |
|---|---|---|
| Handler execution | On the thread calling `send()` | Typically delegated to a `TaskExecutor` |
| When `send()` returns | After the handler finishes | Usually after the task is submitted |
| Transaction between sender and handler | Can share the same thread and transaction context | Does not support transactions spanning sender and handler |
| Exception visibility | Can propagate synchronously to the caller | Errors can occur after the caller has received the send result |

`ExecutorChannel` supports the same dispatcher load-balancing and failover configuration, but asynchronous execution changes how errors are observed. Do not assume the sender will receive exceptions from the handler. Inspect the executor configuration, error handling, and processing thread logs.

Even with `DirectChannel`, successful failover does not automatically prove a transaction committed. A transaction interceptor may mark the transaction rollback-only after an exception; non-transactional side effects are also not automatically rolled back. Design transaction propagation and handler idempotency according to business requirements.

## 8. Diagnosing When Failover Does Not Happen as Expected

When a message does not reach a backup handler, check in order:

1. **Subscriber count:** does the channel have at least two registered handlers?
2. **Shared channel:** do the endpoints reference the same `DirectChannel` or `ExecutorChannel`?
3. **Starting order:** is `round-robin` or `none` in use? Is `order` declared if primary/backup is needed?
4. **Failover policy:** is `failover` set to `false`? Does the predicate return `true` for the actual exception?
5. **Exception escaping the handler:** did the handler catch and swallow the exception?
6. **Threading model:** does the channel use an executor so errors happen after `send()` returns?
7. **Side effects:** could the first handler have performed partial business work before throwing?

Since Spring Integration 5.2, when failover is enabled, the current handler's error along with the failed message is logged at DEBUG or INFO level depending on logging configuration. In production investigations, correlate logs using message ID or correlation ID, business ID, channel, tried handler, and exception type. Add dedicated metrics for failover counts, handler successes, final failures, and processing latency.

## 9. Testing Failover Behavior

A test suite should verify observable behavior, not just configuration values:

- **Primary succeeds:** primary handler is invoked; backup handler is not invoked.
- **Primary fails, backup succeeds:** both handlers are invoked in the expected order; dispatch completes successfully.
- **Predicate rejects exception:** backup handler is not invoked; the current error propagates.
- **All handlers fail:** dispatch terminates with an aggregate error.
- **Fixed order:** with `load-balancer="none"`, every message starts at the higher-priority subscriber.
- **Round-robin:** multiple messages distribute starting points across subscribers according to the selected strategy.
- **Idempotency:** if the primary handler creates a side effect before throwing an exception, the backup receiving the same message does not duplicate business impact.

In tests, use spies or mocks to count invocations and record invocation order. With `ExecutorChannel`, wait for asynchronous results or observe the error flow rather than asserting immediately after `send()`.

## 10. Quick Selection Rules

| Requirement | Recommended Configuration |
|---|---|
| Multiple equivalent workers, rotating distribution | `round-robin`, `failover` enabled if workers are interchangeable |
| Explicit primary/secondary ordering | `none`, `failover` enabled, explicit `order` |
| Fail immediately on error | `failover=false` |
| Switch handlers only for specific exception types | `failoverStrategy` (Spring Integration 6.3+) |
| Retry the same handler with backoff | Retry advice / dedicated retry mechanism |
| Broadcast to all subscribers | `PublishSubscribeChannel` |
| Buffer messages and poll later | `QueueChannel` or an appropriate broker |

## Conclusion

Failover and load balancing are two independent decisions in a unicast dispatcher. Choose load balancing based on how work should be distributed, choose failover based on which errors can be recovered by another handler, and then verify idempotency, transactions, and threading models. A fallback setup is only reliable when handlers are truly interchangeable and repeated processing does not corrupt business state.

## References

- [Spring Integration — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration 6.5 — UnicastingDispatcher API](https://www.springframework.org/spring-integration/docs/6.5.0/api/org/springframework/integration/dispatcher/UnicastingDispatcher.html)
