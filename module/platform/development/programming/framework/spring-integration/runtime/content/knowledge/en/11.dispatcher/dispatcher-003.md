# BroadcastingDispatcher Delivers to Multiple Handlers

In Spring Integration, a single message may need to be processed by multiple independent components: writing an audit log, updating metrics, sending a notification, syncing a cache, or triggering a secondary process. For this fan-out pattern, `PublishSubscribeChannel` allows multiple handlers to subscribe to the same channel. The dispatcher backing the channel broadcasts the message to registered subscribers.

`BroadcastingDispatcher` is the component responsible for delivering messages to multiple handlers in `PublishSubscribeChannel`. Importantly, it has different semantics from `UnicastingDispatcher`: broadcasting targets all eligible subscribers, whereas unicasting selects one handler per dispatch. Understanding how delivery works, how errors are handled, and whether an executor is used helps you design fan-out flows without confusing successful send, completed processing, and guaranteed success across all branches.

## 1. Where Does BroadcastingDispatcher Fit?

`PublishSubscribeChannel` is a `SubscribableChannel`. Endpoints or handlers register as subscribers. When a producer sends a message to the channel, `BroadcastingDispatcher` iterates over the subscribers and dispatches the message to each handler.

```text
                         +--> AuditHandler
                         |
Producer --> PublishSubscribeChannel --> NotificationHandler
                         |
                         +--> MetricsHandler
                         |
                         +--> CacheUpdateHandler
```

Subscribers receive the same input event to perform different tasks. The producer only needs to send one message; the channel is responsible for distributing the message to registered handlers.

A simple configuration:

```java
@Bean
public PublishSubscribeChannel orderEvents() {
    return new PublishSubscribeChannel();
}

@Component
public class OrderEventHandlers {

    @ServiceActivator(inputChannel = "orderEvents")
    public void writeAudit(OrderCreated event) {
        // Write audit trail.
    }

    @ServiceActivator(inputChannel = "orderEvents")
    public void updateMetrics(OrderCreated event) {
        // Update order metrics.
    }

    @ServiceActivator(inputChannel = "orderEvents")
    public void notifyCustomer(OrderCreated event) {
        // Send customer notification.
    }
}
```

When `orderEvents` receives a message, all service activators subscribed to the channel are dispatch targets. Each handler is responsible for one branch of work.

## 2. Broadcasting vs. Unicasting

The two dispatchers solve two different distribution models:

| Characteristic | BroadcastingDispatcher | UnicastingDispatcher |
|---|---|---|
| Typical channel | `PublishSubscribeChannel` | `DirectChannel` |
| Number of handlers invoked | All subscribers selected for dispatch | One handler per dispatch |
| Purpose | Fan-out an event to multiple branches | Select one consumer to process the message |
| Related configuration | `applySequence`, `ignoreFailures`, `minSubscribers` | Load balancing, failover |
| Business outcome | Multiple branches can produce separate side effects | One branch is selected to do the work |

For example, when an order is created:

- If audit, notification, and metrics all need to receive the event, use publish-subscribe.
- If multiple workers process orders and each order only needs one worker to receive it, use unicast with an appropriate channel.

Do not use `PublishSubscribeChannel` as a substitute for load balancing. Under broadcast, every subscriber is invoked; if five workers are subscribed, a single message can trigger all five workers. This is different from distributing five messages across five workers in a competing-consumers pattern.

## 3. How Are Subscribers Registered and Unregistered?

Subscribers are typically registered when endpoints are initialized in the `ApplicationContext`. For instance, `@ServiceActivator(inputChannel = "orderEvents")` creates an endpoint that registers a handler on the channel. With the Java DSL, a flow starting from a `PublishSubscribeChannel` also registers an endpoint as a subscriber.

```java
@Bean
public IntegrationFlow auditFlow(PublishSubscribeChannel orderEvents,
                                 AuditService auditService) {
    return IntegrationFlow.from(orderEvents)
        .handle(auditService, "record")
        .get();
}

@Bean
public IntegrationFlow notificationFlow(PublishSubscribeChannel orderEvents,
                                         NotificationService notifications) {
    return IntegrationFlow.from(orderEvents)
        .handle(notifications, "send")
        .get();
}
```

Both flows subscribe to the same channel, so each message is dispatched to both branches. When an endpoint stops or a flow is removed from the context, its corresponding subscriber is unregistered according to the endpoint lifecycle.

With dynamic flows managed through `IntegrationFlowContext`, registering and removing flows alters the subscriber list at runtime. If a subscriber is added or removed while the system is under load, subsequent messages are dispatched according to the subscriber list at the time of dispatch. Do not assume that a removed subscriber still receives new messages, or that a newly added subscriber receives messages sent previously.

## 4. Synchronous Dispatch Without an Executor

`PublishSubscribeChannel` can operate without an executor. In that case, the dispatcher invokes handlers synchronously on the message-sending thread.

```java
@Bean
public PublishSubscribeChannel synchronousEvents() {
    PublishSubscribeChannel channel = new PublishSubscribeChannel();
    channel.setApplySequence(true);
    return channel;
}
```

With synchronous dispatch:

1. The producer calls `send()`.
2. The channel invokes subscribers one by one.
3. Each handler runs on the thread calling `send()`.
4. The send call completes only after synchronous dispatch finishes or raises an error.

Example of a producer calling the channel from a service:

```java
Message<OrderCreated> message = MessageBuilder
    .withPayload(new OrderCreated("ORD-1001"))
    .build();

boolean accepted = synchronousEvents.send(message);
```

If one handler takes a long time, the producer must wait as well. This can be a good choice when you want to keep the flow simple and learn about synchronous errors directly within the send call. However, a fan-out with multiple blocking branches can increase producer latency.

Handler invocation order depends on the subscriber order managed by the dispatcher and endpoint ordering metadata. You can use `@Order` or an appropriate ordering mechanism when ordering synchronous subscribers, but do not use invocation order as a business orchestration mechanism. If one branch must run after the result of another branch, model that dependency as sequential steps in the flow.

## 5. Asynchronous Dispatch Using an Executor

You can pass an `Executor` into `PublishSubscribeChannel` so the dispatcher delegates subscriber invocations to the executor:

```java
@Bean("fanoutExecutor")
public ThreadPoolTaskExecutor fanoutExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(12);
    executor.setQueueCapacity(300);
    executor.setThreadNamePrefix("fanout-worker-");
    return executor;
}

@Bean
public PublishSubscribeChannel asynchronousEvents(
        @Qualifier("fanoutExecutor") TaskExecutor executor) {
    return new PublishSubscribeChannel(executor);
}
```

In this configuration, the channel submits handler dispatch tasks to the executor. The producer typically waits only for the dispatch tasks to be submitted as accepted by the executor, not for all handlers to finish. Each handler can run on a different worker thread.

Important consequences:

- `send()` returning does not mean all subscribers have finished processing.
- Completion times across branches can differ.
- Exceptions in worker threads cannot propagate back to the original caller by default.
- The executor queue can grow if messages arrive faster than they are processed.
- Error handling and monitoring must be configured for asynchronous tasks.

An executor decouples producer latency from subscriber processing time, but increases complexity around concurrency, failures, and shutdown. Use bounded queues, I/O timeouts, and a dedicated thread prefix for easier tracing.

## 6. Ordering Configuration and Sequence Headers

When broadcasting a message to multiple branches and then combining results with an `Aggregator`, branches need group identification and message ordering metadata. `PublishSubscribeChannel` supports `applySequence` to add sequence headers to broadcast messages.

```java
@Bean
public PublishSubscribeChannel orderEventsForAggregation() {
    PublishSubscribeChannel channel = new PublishSubscribeChannel();
    channel.setApplySequence(true);
    return channel;
}
```

When `applySequence` is enabled, messages sent to subscribers are enriched with sequence metadata, including:

- `correlationId`: links messages belonging to the same group.
- `sequenceNumber`: the message's position within the group.
- `sequenceSize`: the expected number of messages in the broadcast group.

These headers are useful when branches transform or produce replies and forward their results to an aggregator. The `Aggregator` can use a correlation strategy to group messages and a release strategy to decide when the group is complete.

Conceptual flow example:

```text
OrderCreated
     |
     v
PublishSubscribeChannel (applySequence=true)
     |                         |
     v                         v
Validate branch            Price branch
     |                         |
     +------------+------------+
                  |
                  v
              Aggregator
                  |
                  v
             OrderSummary
```

Do not enable `applySequence` if subscribers only perform independent side effects and results do not need to be aggregated. If a branch may fail to produce a reply or throw an error, the aggregator needs an appropriate timeout or release strategy so it does not wait indefinitely.

## 7. minSubscribers and requireSubscribers

Broadcasting may require a minimum number of subscribers for a message dispatch to be considered valid. `PublishSubscribeChannel` provides `minSubscribers` and `requireSubscribers` for this purpose.

- `minSubscribers` sets the minimum number of subscribers required for a dispatch to be accepted. If the subscriber count is below the required threshold, dispatch can fail with `MessageDispatchingException`.
- `requireSubscribers` requires at least one subscriber to be present. This helps detect cases where a message is sent to a channel with no receiving endpoints.

Example requiring at least two subscribers:

```java
@Bean
public PublishSubscribeChannel criticalEvents() {
    PublishSubscribeChannel channel = new PublishSubscribeChannel();
    channel.setMinSubscribers(2);
    channel.setRequireSubscribers(true);
    return channel;
}
```

These options check the subscriber count at dispatch time. They do not prove that handlers succeeded or that side effects committed. If a specific branch must always be present, check the topology and health of that endpoint by its business name/identifier rather than relying solely on the total subscriber count.

## 8. ignoreFailures and Failure of One Subscriber

In synchronous dispatch, a handler may throw an exception. `BroadcastingDispatcher` supports an `ignoreFailures` policy to decide whether the dispatcher continues invoking remaining subscribers when one subscriber fails.

```java
@Bean
public PublishSubscribeChannel tolerantEvents() {
    PublishSubscribeChannel channel = new PublishSubscribeChannel();
    channel.setIgnoreFailures(true);
    return channel;
}
```

When `ignoreFailures` is enabled, a subscriber's error is ignored for the purpose of continuing the broadcast, and the dispatcher continues processing remaining subscribers. This fits when branches are independent and a failure in one branch should not prevent other branches from receiving the event.

When `ignoreFailures` is disabled, an exception from a subscriber can cause the synchronous dispatch to fail and prevent subsequent subscribers from being invoked. The producer can observe the exception through the send call. Therefore, if you want all branches to be attempted even when one fails, consider `ignoreFailures` alongside per-branch logging and metrics.

Do not enable `ignoreFailures` and then neglect error observability. If errors are ignored without logs, metrics, or an error flow, a branch can silently stop working for a long time without anyone noticing.

### ignoreFailures Does Not Create a Shared Rollback

Broadcast is not a distributed transaction spanning all subscribers. If the audit branch has already written data and the notification branch fails, dispatch failure does not automatically roll back the audit record. Likewise, `ignoreFailures=true` only lets other branches continue; it does not turn branch outcomes into an atomic transaction.

If business requirements demand that all side effects succeed together or roll back together, design an orchestration flow with appropriate transactions, outbox, or saga patterns. Do not treat an in-memory `PublishSubscribeChannel` as an atomic fan-out guarantee.

## 9. Exceptions When Using an Executor

When a channel uses an executor, handlers can execute after the `send()` call has returned. Consequently, exceptions from handlers do not normally propagate to the sending thread. You must identify the error handler configured for the asynchronous execution mechanism and the error channel to which error messages are routed.

In Spring Integration, errors associated with a message can be published as an `ErrorMessage` to the appropriate error channel, such as the error channel in the `MessageHeaders.ERROR_CHANNEL` header or the global `errorChannel`, depending on configuration and execution path. When investigating, inspect the worker exception, the executor's error handler, and the error flow.

Do not rely on `ignoreFailures` as a substitute for asynchronous error handling. It neither ensures the producer receives worker processing outcomes nor replaces per-branch error monitoring.

An asynchronous handler should at minimum record the branch name, message ID, correlation ID, exception type, and root cause. If retries are needed, configure retry on the appropriate endpoint or handler. If message replay is needed, persist the necessary data before the error-handling path completes.

## 10. One Message, Multiple Subscribers, and Mutable Payloads

A Spring `Message` has an immutable envelope, but the payload is not immutable by default. During broadcast, multiple handlers can see the exact same payload object. If the payload is a mutable object and one handler modifies it while another handler reads it, results can depend on timing and cause race conditions.

Risk example:

```java
public void addFlag(OrderEvent event) {
    event.getAttributes().put("processed", true);
}

public void publishAudit(OrderEvent event) {
    // May or may not see the change depending on ordering/thread.
}
```

With synchronous dispatch, mutations may be visible to handlers that run later. With an executor, handlers can access the same object concurrently. Safe design approaches:

- Use immutable payloads, such as records or read-only objects.
- If each branch needs to transform data, create a separate copy within that branch.
- Do not use the payload as shared state to exchange results among subscribers.
- Emit each branch's result as a separate reply message and aggregate them with an aggregator if needed.

## 11. Ordering, Concurrency, and Performance

When dispatching synchronously, subscribers are invoked sequentially in the order managed by the dispatcher. One slow subscriber can prolong the overall send duration. When dispatching via an executor, tasks are handed off to the executor and start/finish times across branches are not guaranteed to match submission order.

| Configuration | Behavior | Impact |
|---|---|---|
| No executor | Invokes subscribers synchronously | Easy to observe errors, but total latency depends on all branches. |
| Small executor | Branches share a worker pool | Limits concurrency, but one slow branch can starve workers from other branches. |
| Adequately sized executor with bounded queue | Multiple branches can run in parallel | Increases throughput, but requires resource and ordering control. |
| Large or unbounded queue | Accepts many pending tasks | Can increase latency and memory usage when consumers are slow. |

You do not necessarily need a separate executor for every subscriber. However, if one branch performs slow I/O or has a different SLA, consider isolating its pool or routing that branch through its own queue so it does not consume workers needed by critical branches.

When measuring performance, track `send()` duration, completion time per handler, active task count, queue depth, rejections, and per-branch error rates. With asynchronous dispatch, measure producer latency and subscriber processing latency separately; a low `send()` time does not mean the fan-out completed quickly.

## 12. Broadcasting Is Not Durable Delivery

`PublishSubscribeChannel` is an in-memory channel within the application. It delivers messages to currently registered subscribers, but it does not provide persistence, replay, or guarantees that messages are processed after process shutdown.

If the application sends a message to the channel and the process stops before the executor finishes processing, pending tasks can be lost with the process. If one subscriber fails after other branches succeed, there is no automatic mechanism to re-run only the failed subscriber unless the application configures it.

When high reliability is required:

- Persist business events durably using a transactional outbox or equivalent mechanism.
- Use a broker or durable queue for subscribers requiring replay/redelivery.
- Design idempotent consumers to tolerate duplicate messages.
- Record per-branch completion status if you need to know which subscribers finished processing.
- Build bounded, auditable retry/redrive mechanisms.

In-memory fan-out fits internal branches that need to receive the same message within the same process. For subscribers with independent lifecycles or delivery guarantees, consider a messaging broker and durable topology.

## 13. Diagnosing When a Handler Does Not Receive Messages

When a branch is not invoked, check in order:

1. **Is the channel actually a `PublishSubscribeChannel`?** If using a `DirectChannel`, each message is dispatched to only one subscriber.
2. **Has the handler subscribed?** Verify that the endpoint was created, started, and has not been stopped or removed.
3. **Is it the exact same channel instance?** Flows must reference the same channel bean, not separate instances with similar names.
4. **Are there subscriber constraints?** Check `minSubscribers` and `requireSubscribers`.
5. **Did a preceding subscriber throw an exception?** With synchronous dispatch and `ignoreFailures=false`, an error can prevent later branches from being called.
6. **Is the executor accepting tasks?** Check queue, workers, rejection policy, and `RejectedExecutionException`.
7. **Where are async errors sent?** Check the error channel header, global `errorChannel`, and error handler.
8. **Did the handler run without producing side effects?** Check logs, transactions, dependencies, and business conditions inside the handler.
9. **Is a mutable payload being shared?** Check for race conditions if multiple branches run concurrently.

Log the channel, endpoint/subscriber, message ID, correlation ID, thread name, and receive timestamp. Avoid logging full payloads if they contain sensitive data.

## 14. Testing BroadcastingDispatcher

You can test fan-out with a `PublishSubscribeChannel` and two simple subscribers:

```java
PublishSubscribeChannel channel = new PublishSubscribeChannel();
AtomicInteger firstCount = new AtomicInteger();
AtomicInteger secondCount = new AtomicInteger();

channel.subscribe(message -> firstCount.incrementAndGet());
channel.subscribe(message -> secondCount.incrementAndGet());

channel.send(MessageBuilder.withPayload("event").build());

assertEquals(1, firstCount.get());
assertEquals(1, secondCount.get());
```

This test verifies that both subscribers are invoked during synchronous dispatch. You can extend tests to cover:

- No subscribers with `requireSubscribers` configured.
- Subscriber count below `minSubscribers`.
- One subscriber throwing an exception with `ignoreFailures=false` and `true`.
- `applySequence=true` generating appropriate sequence headers for branches.
- An executor causing handlers to run on worker threads and `send()` not waiting for handlers to finish.
- Executor rejecting tasks when the queue is full.
- Subscriber unregistration when an endpoint or dynamic flow stops.
- Handlers not mutating shared mutable payloads.

For asynchronous tests, use `CountDownLatch` or `CompletableFuture` to wait with a bounded timeout. Do not use `Thread.sleep()` to guess that all branches have finished.

## 15. Common Design Mistakes

- **Confusing broadcast with load balancing.** Broadcast invokes multiple subscribers; unicast selects one handler.
- **Assuming `send()` returning means all handlers finished.** This is untrue when using an executor.
- **Using `ignoreFailures=true` without recording errors.** Broken branches can be hidden.
- **Relying on subscriber order for business orchestration.** An executor can cause branches to complete out of order.
- **Assuming broadcast shares a single transaction.** Side effects committed in one branch do not automatically roll back when another branch fails.
- **Sharing mutable payloads across multiple handlers.** Branches can overwrite data or trigger race conditions.
- **Treating PublishSubscribeChannel as a durable queue.** In-memory messages have no replay after process shutdown.
- **Not verifying subscribers when deploying dynamic flows.** Messages can be sent before handlers exist or after handlers are removed.
- **Using one shared unbounded pool for all branches.** One slow subscriber can build up a backlog affecting other branches.

## 16. Design Checklist

Before using broadcast, determine:

- Should the message reach all subscribers or only one consumer?
- Which handlers must be registered for a dispatch to be valid?
- Are branches independent, or do they have ordering or result dependencies?
- Does synchronous or asynchronous dispatch fit latency and error semantics?
- Is `applySequence` needed so an aggregator can combine results?
- When one handler fails, should the remaining handlers continue?
- Where are subscriber errors logged, published, or retried?
- Is the payload immutable or safely copied per branch?
- Are durable delivery, replay, and per-branch completion tracking needed?
- Does the executor have a bounded queue, metrics, and an appropriate shutdown policy?

`BroadcastingDispatcher` lets a single message trigger multiple processing branches within the same message flow. When you choose the right synchronous or asynchronous dispatch mode, configure errors and concurrency clearly, and define durability requirements, fan-out becomes straightforward to operate without creating false expectations that every branch always succeeds together.
