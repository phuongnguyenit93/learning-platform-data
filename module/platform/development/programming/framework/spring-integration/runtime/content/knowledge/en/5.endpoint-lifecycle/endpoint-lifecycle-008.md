# Restarting Endpoints After Errors or Maintenance

In Spring Integration, endpoints are typically managed through Spring's lifecycle. An endpoint can be started when the ApplicationContext starts, stopped when the application shuts down, or controlled at runtime to recover from an incident or perform maintenance. However, calling `start()` after `stop()` only restores the endpoint's ability to receive and process messages. It does not fix failing dependencies on its own, does not guarantee failed messages are replayed, and does not drain running tasks by itself.

To restart safely, first determine what state the endpoint is actually in, where the error occurred, and whether messages are sitting in a channel, executor, or broker. Then coordinate producers, consumers, running work, and dependencies in the right order.

## 1. Endpoints have their own lifecycle

Spring Integration endpoints are usually built on `AbstractEndpoint`, a base class integrated with Spring's lifecycle. Endpoints support `start()`, `stop()`, and `isRunning()` through `Lifecycle`; many endpoints also implement `SmartLifecycle` to participate in ApplicationContext startup and shutdown ordering.

| API | Meaning |
|---|---|
| `start()` | Begins endpoint operation |
| `stop()` | Stops endpoint operation |
| `isRunning()` | Indicates whether the endpoint is currently marked as running |
| `isAutoStartup()` | Indicates whether the endpoint auto-starts with the context lifecycle |
| `getPhase()` | Indicates the phase used for lifecycle ordering during context start/stop |
| `stop(Runnable callback)` | For `SmartLifecycle`, signals completion of the stop process via callback |

`isRunning()` is a lifecycle state, not a complete health check. An endpoint can remain running while handlers repeatedly throw exceptions, dependencies are unreachable, or messages are diverted into an error flow. Conversely, a stopped endpoint may be the result of intentional maintenance rather than a failure.

`autoStartup` is also not an immediate runtime toggle switch. It determines whether the endpoint auto-starts during ApplicationContext initialization. Once the context is running, use `start()` and `stop()` to change its current state.

### Endpoints differ from IntegrationFlow

A single `IntegrationFlow` can create multiple endpoints, channels, and adapters. Stopping one endpoint only affects that endpoint's lifecycle. It does not automatically stop the entire flow, channels, shared executors, or neighboring endpoints. If you need to stop an entire dynamically registered flow, control its corresponding registration in `IntegrationFlowContext`; if you only need to pause one consumer, controlling the specific endpoint has a narrower scope.

## 2. An exception does not mean the endpoint has stopped

When message processing fails, do not rush to restart the endpoint. First verify whether the error actually stopped the endpoint or merely failed that single execution.

Behavior depends on the endpoint type, channel, poller, executor, and configured error handling:

- With `DirectChannel`, the handler usually runs on the message-sending thread. Exceptions may propagate back to the producer or be handled at the corresponding error-handling boundary.
- With `ExecutorChannel`, processing runs on a worker thread. The producer may have finished before the worker reports an error; check the error flow and logs by message ID or Correlation ID.
- With a polling endpoint, a single poll may fail while the scheduler and endpoint keep running depending on the error handler, retry advice, and poller configuration.
- With a broker-connected inbound adapter, whether messages are redelivered, requeued, or acknowledged depends on the broker, acknowledgment mode, and transactions.

Therefore, a single exception does not prove the endpoint stopped running. Check `isRunning()`, lifecycle logs, received message counts, error counts, and consumer status. If the endpoint is still running but failing on messages, fix the root cause or retry policy before considering a restart.

### Classify before acting

| Observation | Investigation Direction |
|---|---|
| Endpoint running, single message failed | Check payload, handler, validation, errorChannel, and retries |
| Endpoint running, repeated errors across many messages | Check dependencies, connection pools, timeouts, configuration, and backoff |
| Endpoint stopped unexpectedly | Check stop logs, lifecycle owner, runtime management, and startup errors |
| Endpoint running, receiving no messages | Check channel subscriptions, poller, inbound source, routing, and backlog |
| Endpoint just restarted then immediately stopped or errored | Check unhealthy dependencies, invalid configuration, or errors in `doStart`/on first message |

Restarting only makes sense when the endpoint stopped unexpectedly, needs reactivation after maintenance, or the component must be stopped and started to apply changes supported by its lifecycle. If the fault lies in a message or dependency, simply restarting usually just causes the error to reappear.

## 3. Controlling endpoints via Lifecycle

In internal management code, you can inject an endpoint bean as `Lifecycle` or `SmartLifecycle` and invoke lifecycle operations. The bean name in the example must be the actual endpoint name in the ApplicationContext; DSL-created endpoints may have framework-generated names.

~~~java
@Component
public class EndpointLifecycleController {

    private final Lifecycle ordersEndpoint;

    public EndpointLifecycleController(
            @Qualifier("ordersEndpoint") Lifecycle ordersEndpoint) {
        this.ordersEndpoint = ordersEndpoint;
    }

    public synchronized void restart() {
        if (ordersEndpoint.isRunning()) {
            ordersEndpoint.stop();
        }

        verifyDependenciesAreReady();

        ordersEndpoint.start();
    }

    private void verifyDependenciesAreReady() {
        // Check database, remote service, connections, or related configuration.
    }
}
~~~

This code illustrates the lifecycle operation; in a real application, `verifyDependenciesAreReady()` should return an explicit result or throw an exception if not ready. Do not start the endpoint while dependencies are still failing. Also log state before and after the operation, and ensure only one management thread restarts the same endpoint at a time.

If you need to wait for an asynchronous stop to finish, use the `SmartLifecycle.stop(Runnable callback)` contract and start again only after the callback. Do not call `start()` immediately after an asynchronous stop command if the endpoint or running tasks have not completed stopping yet.

## 4. Controlling via Control Bus

The Spring Integration Control Bus allows sending control expressions to beans in the ApplicationContext. It is a convenient way to operate on endpoints at runtime without writing a separate service for every command.

~~~java
@Bean
IntegrationFlow controlBusFlow() {
    return IntegrationFlow.from("controlBus.input")
            .controlBus()
            .get();
}
~~~

Once the Control Bus is configured, expression commands can be sent to its input channel:

~~~java
controlBusInput.send(new GenericMessage<>("@ordersEndpoint.stop()"));
controlBusInput.send(new GenericMessage<>("@ordersEndpoint.start()"));
~~~

Here `ordersEndpoint` is the actual bean name of the endpoint permitted to be controlled. Other expressions can be used to read state or invoke exposed management methods. Restrict the Control Bus channel to a trusted administrative scope, enforce authorization on who can send commands, and audit who performed start/stop. Do not expose a Control Bus capable of invoking arbitrary beans to a public network.

Control Bus is only a command-dispatch mechanism. It does not verify that dependencies are healthy, messages have drained, or the endpoint is processing successfully after starting. Those steps still require dedicated operational procedures and observability.

## 5. Restart procedure after an error

When an endpoint stops unexpectedly, proceed in order:

1. **Identify the exact endpoint.** Record bean name, component name, input channel, endpoint type, and enclosing flow.
2. **Verify state.** Read `isRunning()` and lifecycle logs to distinguish a stopped endpoint from a running endpoint with failing messages.
3. **Find the root cause.** Inspect exceptions, failed message metadata, `errorChannel`, retries, transactions, timeouts, connections, and dependency state.
4. **Prevent repeated failure.** If a dependency is failing, wait for or recover the dependency; if a message is poisoned or invalid data, route it to appropriate error handling.
5. **Handle pending messages.** Identify messages remaining in queues/brokers, tasks submitted to executors, or already-acknowledged messages. Drain, retain backlog, retry, or dead-letter per policy.
6. **Start the endpoint.** Only start once prerequisites are ready.
7. **Verify recovery.** Confirm the endpoint is running, consumers receive messages, backlog shrinks, error rate returns to normal, and errors do not recur.

If the endpoint stops itself due to an error during start, examine the exception from that specific start attempt. Repeatedly calling `start()` without changing the error condition creates noisy logs and makes diagnosis harder.

## 6. Restart procedure for maintenance

Maintenance is usually planned, so ordering can be coordinated to prevent messages arriving when consumers are unready.

~~~mermaid
flowchart TD
    A[Maintenance notice] --> B[Stop or block new producers]
    B --> C[Drain or retain backlog per policy]
    C --> D[Stop endpoint needing maintenance]
    D --> E[Update dependencies / configuration]
    E --> F[Verify dependencies healthy]
    F --> G[Start consumer endpoint]
    G --> H[Test receive and processing]
    H --> I[Re-enable producers]
    I --> J[Monitor backlog and error rate]
~~~

Exact ordering depends on topology. If the endpoint consumes from a queue, you can stop producers first, wait for the queue to drain or accept holding a backlog, then stop the consumer. If maintenance only affects the handler and you want to buffer pending messages, you can stop the consumer while producers keep writing to the queue, provided queue capacity and backpressure are adequate.

When restarting, usually start consumers first and then open producers. When an inbound adapter is the message source, that adapter may be the last endpoint to start once downstream endpoints are ready.

### Draining and in-flight work

`stop()` is not a universal drain command for the entire topology. Depending on the endpoint:

- A polling endpoint can stop future polls while the currently executing poll needs time to complete.
- An event-driven consumer can stop receiving new messages from the channel after unsubscribing; handler invocations already started may still be running.
- An executor may still hold tasks submitted but not yet started. Stopping an endpoint does not necessarily stop or drain a shared executor.
- A broker consumer may hold unacknowledged messages; outcome on stop depends on the broker and acknowledgment mode.

If you need to guarantee no processing remains running, have a dedicated quiesce-and-wait mechanism: block new sources, track in-flight counts, wait for executors to finish, or use appropriate lifecycle callbacks. Do not shut down a shared `TaskExecutor` just because one endpoint is under maintenance; the executor may be serving other flows.

## 7. Channels determine where waiting messages sit

When an endpoint stops, message behavior depends on the channel and sender.

| Channel/Source | When Consumer Stops | What to Check |
|---|---|---|
| `DirectChannel` | No built-in buffer; sending with no subscriber may fail | Stop producer or route to a buffer/error path before stopping consumer |
| `QueueChannel` | Messages may continue being enqueued and wait for consumer | Capacity, send timeout, backlog, and backing `MessageStore` type |
| `ExecutorChannel` | Tasks already accepted by the executor may keep running even if the endpoint stops | Executor queue, in-flight tasks, rejections, and context propagation |
| `PublishSubscribeChannel` | Remaining active subscribers may still receive messages; the stopped branch will not process | Check per-subscriber semantics and whether durable fan-out is needed |
| Broker inbound adapter | Broker retains or redelivers messages per consumer/acknowledgment configuration | Ack mode, transactions, prefetch, requeue, and dead-letter policy |

An in-memory `QueueChannel` does not become durable just because an endpoint is restarted. If the JVM process exits, messages in an in-memory queue can be lost. To preserve messages across process restarts, choose a persistent store or broker and configure durability properly.

With brokers, do not assume every in-flight message is redelivered upon stop. If a message was already acknowledged or its transaction committed, the broker may not resend it. If unacknowledged, the broker may requeue according to configuration. Verify the exact semantics of your adapter and broker before planning maintenance.

## 8. Retries, Error Channel, and Transactions after restart

Restarting an endpoint and retrying a message are two different operations.

Retry advice can retry a message during processing or according to a backoff policy. An error flow can receive an `ErrorMessage` when processing fails. Some message sources support redelivery; some applications send failed messages to a dead-letter channel or persist separate error state. Restarting an endpoint does not re-trigger these mechanisms and does not automatically put failed messages back onto the input channel.

When transactions are configured on a poller or broker, an exception can roll back the transaction and the message source may redeliver the message. However, this only happens when the transaction manager, resource, and acknowledgment mode actually participate in the same transaction per configuration. Do not infer redelivery solely from the fact that an endpoint threw an exception.

Before replaying manually, check whether side effects already happened. If a handler wrote to a database or called an external service before failing, replaying can create duplicate data. Use idempotency keys, unique constraints, or appropriate deduplication mechanisms. Retries need bounded attempt counts, backoff, and separation between transient and non-recoverable errors.

A dedicated checklist for failed messages:

- Identify message ID, Correlation ID, and failed message metadata.
- Check whether the message is still in the channel/broker, already acknowledged, or moved to an error/dead-letter flow.
- Check how many retry attempts ran and whether more attempts are allowed.
- Check transaction commit/rollback status and executed side effects.
- Replay only once the root cause is resolved and the operation is idempotent or protected against duplicate processing.

## 9. Configuration change or just restart?

Restarting fits when keeping the endpoint structure intact and simply stopping and starting again, such as after a dependency recovers or maintenance completes. If changing flow structure, channels, handler beans, or components that must be recreated, stopping/starting the existing endpoint may not be enough.

| Change | Usually Appropriate Approach |
|---|---|
| Dependency temporarily lost connection, endpoint stopped | Recover dependency, verify health, then start endpoint |
| Need to temporarily pause consumer during maintenance | Stop endpoint, manage producers/backlog, then start again |
| Runtime property change supported by setters | Apply change per component contract, verify, and restart if the component requires it |
| Changing topology or swapping handler bean | Update/re-register flow or manage bean again via appropriate lifecycle |
| Tenant dynamic flow no longer used | Stop and remove the corresponding registration, handle backlog per policy |
| Want to change `autoStartup` for future startups | Update bean configuration; do not treat it as a current runtime start/stop command |

Do not use restart to mask configuration errors. If an endpoint restarts while its handler still points to an old dependency, old bean, or unrefreshed configuration, the error will recur. Identify which components must be recreated and use their proper lifecycle.

## 10. Observing before, during, and after restart

Emit structured logs for every administrative operation with endpoint name, component type, action, initiator (user or system), reason, timestamp, and outcome. On message failures, include message ID, Correlation ID, and exception type; avoid logging full payloads or credentials.

Monitor these signals:

| Signal | Before Restart | After Restart |
|---|---|---|
| Endpoint lifecycle | `isRunning`, stop timestamp, and cause | `isRunning` and successful start timestamp |
| Message throughput | Receive/process rate before maintenance | New messages being processed steadily |
| Queue/broker backlog | Messages waiting or unacknowledged | Backlog shrinking or within expected bounds |
| Executor | Active threads, queue size, rejected tasks | Tasks being processed, no rising rejections |
| Error flow | Error count, retry count, dead-letter count | No recurring errors or clearly declining trend |
| Dependency | Health, connection, latency | Healthy with latency within limits |

Do not check `isRunning()` alone and conclude recovery is complete. An endpoint can be running without a valid consumer, unable to poll, or failing every message. Send a safe test message if possible, confirm it traverses the right endpoint, and verify post-processing metrics and logs.

## 11. Endpoint restart checklist

- [ ] Identify the exact endpoint bean and its enclosing flow.
- [ ] Read `isRunning()` and logs to know whether the endpoint is truly stopped or merely failing messages.
- [ ] Find the root cause and verify dependencies are healthy.
- [ ] Block producers or establish backpressure before stopping consumers if the channel has no buffer.
- [ ] Determine how to drain, retain backlogs, and handle in-flight tasks.
- [ ] Check retry, transaction, acknowledgment, and dead-letter policies.
- [ ] Stop the right endpoint; avoid accidentally stopping shared executors or flows.
- [ ] Start consumers after dependencies are ready and before re-opening producers.
- [ ] Confirm the endpoint is running, messages are processed, and backlog and error rates stabilize.
- [ ] Record maintenance/restart outcomes and any messages requiring separate replay.

Restarting an endpoint is a lifecycle operation with a specific scope. Complete recovery also requires healthy dependencies, messages preserved per channel or broker semantics, running tasks handled properly, and evidence that new messages are flowing through successfully. Clearly separating endpoint state from message state prevents repeated restarts that fail to address the root cause.

## References

- [Spring Framework Reference: Lifecycle and SmartLifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Integration Reference: Endpoint Lifecycle](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration Reference: Control Bus](https://docs.spring.io/spring-integration/reference/control-bus.html)
- [Spring Integration Reference: Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
