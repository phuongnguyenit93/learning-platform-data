# shutdownTimeout

In Spring Kafka, `shutdownTimeout` is the duration the listener container waits for consumers to stop when the container is shut down. This property directly impacts orderly application shutdown: the consumer must exit the poll loop, finish in-flight processing to the extent the application permits, and close Kafka resources.

The default value of `ContainerProperties.shutdownTimeout` is 10 seconds. It can be changed with `setShutdownTimeout(long)`; the unit is milliseconds. The value must be sufficient for the consumer to terminate under normal operating conditions, while being set alongside listener processing times, dependency timeouts, and the deployment platform's shutdown limits.

`shutdownTimeout` is a wait limit during container shutdown. It is not a per-record timeout, does not cap business processing duration, and does not replace `max.poll.interval.ms`, `session.timeout.ms`, or transaction timeouts.

## 1. Why does a listener container need shutdown time?

A listener container manages consumer threads, poll loops, listener invocations, and closing the Kafka consumer. When the application stops, the container needs to bring consumers out of the processing loop in a controlled way. If the process stops immediately while a listener is executing business logic, the application may abandon work partway through or fail to finish required steps.

For example, a listener receives a payment request and calls an internal service. When the application receives a shutdown signal, the listener may be in the middle of that call:

```text
Application receives shutdown signal
          |
          v
Listener container tells consumer to stop
          |
          v
Consumer stops taking new work
          |
          v
In-flight listener finishes if possible
          |
          v
Consumer closes and container terminates
```

The container needs time to carry out this sequence. `shutdownTimeout` configures the wait budget for stopping the consumer. If in-flight work finishes within that window, closing the container completes cleanly. If the wait time expires before the consumer stops, the application must anticipate that shutdown did not complete within the desired time.

## 2. Default value and unit

`ContainerProperties` has a `shutdownTimeout` property. The standard default is 10,000 milliseconds, equivalent to 10 seconds. The setter API takes a `long` in milliseconds:

```java
factory.getContainerProperties().setShutdownTimeout(30_000L);
```

The snippet above sets the shutdown wait time to 30 seconds for listener containers created from that factory. Make the unit explicit when configuring to avoid confusing milliseconds and seconds.

Do not pick a huge value just to mask hung listeners. `shutdownTimeout` should reflect a reasonable system stop time. If listeners routinely take several minutes to complete, revisit processing times, dependency calls, and work decomposition instead of merely extending wait time.

## 3. Configuring via listener container factory

For applications using `ConcurrentKafkaListenerContainerFactory`, set `shutdownTimeout` on the factory's `ContainerProperties`:

```java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, Order> orderListenerFactory(
            ConsumerFactory<String, Order> consumerFactory) {

        var factory =
                new ConcurrentKafkaListenerContainerFactory<String, Order>();
        factory.setConsumerFactory(consumerFactory);
        factory.getContainerProperties().setShutdownTimeout(30_000L);
        return factory;
    }
}
```

Listeners using this factory inherit the corresponding container configuration:

```java
@KafkaListener(
        topics = "${app.topics.orders-in}",
        containerFactory = "orderListenerFactory")
public void onOrder(Order order) {
    orderService.process(order);
}
```

If an application has multiple factories, set wait durations suited to the workload of each listener group. A listener handling lightweight events can stop quickly; a listener calling slow dependencies may need a larger shutdown budget. Avoid raising the timeout for every container if only one listener group has long processing times.

You can configure a container directly after creation rather than on the factory. This is useful when a single listener needs a distinct policy:

```java
MessageListenerContainer container =
        kafkaListenerEndpointRegistry.getListenerContainer("orders-listener");

if (container != null) {
    container.getContainerProperties().setShutdownTimeout(45_000L);
}
```

In real applications, apply configuration before the container starts running. Do not change the property mid-shutdown expecting the current stop operation to pick up the new budget automatically.

## 4. How does shutdownTimeout participate in stopping?

When the container is asked to stop, Spring Kafka tells the consumer to exit normal operation. The consumer may be waiting in `poll()` or executing the listener. Depending on state, the container needs to wake up the poll loop, wait for current processing to finish, and close the consumer.

A typical sequence of events:

1. Spring context or application asks the listener container to stop.
2. The container tells consumer threads to stop and wakes up consumers if waiting in poll.
3. Consumers stop picking up new work once the stop sequence is processed.
4. In-flight listeners get a chance to finish; the container waits for consumers to finish stopping within the shutdown timeout.
5. Consumers are closed and the container completes the stop process.

`shutdownTimeout` is the wait budget during the consumer-stopping phase. It does not interrupt a hung HTTP call, does not cancel a thread running business logic, and cannot force a database transaction to finish. If a listener blocks indefinitely on a dependency, raising `shutdownTimeout` only makes the application wait longer; the dependency itself still needs its own timeout.

## 5. Distinguishing from other Kafka timeouts

Timeouts in Kafka consumers and Spring Kafka solve different problems. Mixing them up can lead to unexpected shutdown behavior.

| Property | Scope | Question it answers |
|---|---|---|
| `shutdownTimeout` | Spring Kafka listener container during stop | How long does the container wait for consumers to stop? |
| `max.poll.interval.ms` | Kafka consumer | How long may the consumer go between `poll()` calls before being considered stalled? |
| `session.timeout.ms` | Kafka consumer group membership | How long does the broker wait without a valid heartbeat before considering the consumer dead? |
| `request.timeout.ms` | Kafka client requests | How long does the client wait for a response to a broker request? |
| `transaction.timeout.ms` | Kafka transactions | How long may a transaction stay open before the coordinator can time it out? |
| HTTP/database timeout | Dependency client or driver | How long is an external call allowed to wait? |

For instance, increasing `shutdownTimeout` does not increase `max.poll.interval.ms`. If a listener takes too long processing a record, the consumer can still exceed the poll interval and be removed from the group by the group coordinator before application shutdown even begins.

Similarly, `shutdownTimeout` does not extend transaction timeout. If a listener is inside a Kafka transaction and the transaction exceeds the broker limit, the transaction can fail even though the container still has shutdown wait time left.

## 6. Choosing a timeout from observed processing times

Base the value on observed processing durations rather than picking an arbitrary number. Consider:

- How long the listener takes to finish a record or batch under normal load.
- Maximum wait times of HTTP clients, database drivers, and dependent services.
- Time needed for producer flush or completing a Kafka transaction if the listener sends output.
- Number of consumer threads and active listeners in the same application.
- Shutdown budget granted by Spring Boot, process supervisor, container runtime, or orchestrator.

A practical estimation method is measuring the time from when the application requests stop until the listener container actually stops under representative load scenarios. Then set `shutdownTimeout` large enough for the stop-time percentile the system must support, while keeping total shutdown within platform budgets.

For example, if a listener normally finishes in a few seconds but some dependency calls can take up to 20 seconds, a 30-second timeout can be a starting point for testing. Final numbers must rest on production telemetry and the graceful shutdown window allowed by the deployment environment.

Do not mechanically add every timeout into one number. Operations may run sequentially or in parallel, and shutdown also includes other beans' lifecycles. Measuring overall application stop time gives a more accurate budget.

## 7. Combining with Spring Boot graceful shutdown

In Spring Boot applications, listener containers are usually managed by the Spring context and `KafkaListenerEndpointRegistry`. When the context closes, container lifecycles are invoked to stop listeners. `shutdownTimeout` participates in stopping container consumers.

Several aspects need coordination:

- Spring Boot graceful shutdown should be enabled if the application needs to stop accepting new requests while finishing in-flight HTTP requests.
- Kafka listener containers have their own lifecycle; HTTP graceful shutdown does not replace stopping consumers.
- Dependent beans needed by listeners must stay alive while listeners finish. If database connection pools or HTTP clients close too early, listeners can fail during shutdown.
- Process supervisor or container runtime timeouts must allow enough time for the Spring context to complete shutdown.

For a Spring Boot application, graceful shutdown for the web server can be configured as follows:

```yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 45s
```

This is Spring Boot's overall lifecycle configuration. It is not a replacement for `ContainerProperties.shutdownTimeout`. Coordinate the lifecycle budget with listener container and other component timeouts. If the phase timeout is shorter than the time needed for containers to stop, the Spring context may exhaust its budget before listeners finish.

## 8. Kubernetes and termination grace period

In Kubernetes, when a Pod is deleted or rolled out, kubelet sends a `SIGTERM` signal to the container and waits for `terminationGracePeriodSeconds`. If the process has not exited when the grace period expires, kubelet may send `SIGKILL`.

Therefore, the application's shutdown budget must fit inside Kubernetes's allowance. If a listener container needs 30 seconds to stop, yet the Pod only has a 20-second termination grace period, the process may be terminated before the listener finishes. In that case `shutdownTimeout` cannot protect the application from `SIGKILL`.

Illustrative configuration example:

```yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: order-worker
      image: example/order-worker:latest
```

60 seconds is only an example. Set the grace period large enough for Spring context shutdown, listener container consumer waits, other lifecycle tasks, and a buffer. Also check any `preStop` hooks if the deployment uses them, as hook execution time consumes the grace period as well.

During rollouts, readiness and liveness probes serve distinct roles. Readiness governs whether the Pod receives traffic or is considered ready; it does not replace signaling listener containers to stop. For Kafka consumers, design rollouts so consumers leave the group cleanly and remaining instances can take over processing.

## 9. Long-running listeners and impact on shutdown

If a listener performs lengthy work, `shutdownTimeout` must be evaluated alongside the timeouts of that work itself. For instance, a listener calls an HTTP service with no timeout, so when that service stops responding, the consumer thread can be held for a very long time.

Set finite timeouts on dependencies:

```java
@Bean
RestClient paymentRestClient(RestClient.Builder builder) {
    var requestFactory = new SimpleClientHttpRequestFactory();
    requestFactory.setConnectTimeout(Duration.ofSeconds(3));
    requestFactory.setReadTimeout(Duration.ofSeconds(10));

    return builder
            .requestFactory(requestFactory)
            .build();
}
```

Exact APIs for configuring HTTP timeouts depend on the client and Spring Framework version in use; the example above illustrates setting finite connect/read timeouts. Database queries, lock waits, and producer sends also need appropriate timeouts.

For batch listeners, processing times can be longer than record listeners because one invocation contains multiple records. Measure full batch duration and determine how to handle shutdown arriving mid-batch. Do not acknowledge the entire batch before required steps complete.

If processing is lengthy and cannot finish within the shutdown budget, consider breaking work into smaller steps, persisting durable progress, or moving heavy processing to a separate idempotent worker mechanism. Do not rely on extending shutdown indefinitely.

## 10. Shutdown with manual acknowledgment

With `AckMode.MANUAL` or `MANUAL_IMMEDIATE`, the listener decides when to call `Acknowledgment.acknowledge()`. If shutdown happens before the listener acknowledges and offsets have not been committed, records may be redelivered after restart or rebalance.

This is usually safe at-least-once behavior: records may be processed twice rather than skipped simply because the listener had not acknowledged yet. To tolerate redelivery, business logic must be idempotent or have deduplication.

Do not call `acknowledge` just to make shutdown finish quickly if business processing has not succeeded. Doing so can commit the offset for an incompletely processed record. `shutdownTimeout` is not a reason to bypass proper acknowledgment.

If the listener runs inside a Kafka transaction, outputs and offsets can be committed together. When a transaction is incomplete at shutdown, the outcome depends on transaction state and how the container stops; transaction timeout remains enforced independently. Test shutdown while a transaction is open to confirm outputs and offsets have expected semantics.

## 11. Observing and diagnosing slow shutdowns

When a container takes too long to stop or fails to stop within the expected timeout, gather evidence on what consumer threads and listeners are doing.

Monitor these signals:

- Time from receiving `SIGTERM` or a stop command until the container stops completely.
- Which listener is processing and the duration of the current record/batch.
- Timeouts or errors from HTTP clients, databases, producers, and transaction managers.
- Spring Kafka logs for stop, consumer close, commit, and rebalance.
- Shutdown time of the whole Spring context compared to `timeout-per-shutdown-phase`.
- Number of times Pods are terminated via `SIGKILL` or rollouts exceed grace period.

Business logs should include topic, partition, offset, or event ID to correlate in-flight records with shutdown logs. Avoid logging sensitive payloads. If investigating a hung thread, a thread dump taken during shutdown can reveal whether the consumer thread is waiting in an HTTP client, JDBC driver, lock, or application code.

If shutdown timeouts expire frequently, find the root cause before raising the value. Raising the timeout may reduce alerts short-term while lengthening rollout times and delaying replacement of unhealthy instances.

## 12. Testing shutdownTimeout

Integration tests help verify whether containers stop within the configured budget and in-flight records behave as expected. You can use Embedded Kafka or Kafka Testcontainers with real listener containers.

Scenarios to test:

1. Fast listener processing; request stop and verify the container stops normally.
2. Listener processing a record for a controlled duration; request stop and observe container termination time.
3. Listener blocked by a dependency; verify dependency timeout releases the listener before the shutdown budget runs out.
4. Listener has not acknowledged yet; stop and restart the application and verify the record can be redelivered.
5. Listener has already acknowledged; verify the consumer group resumes from the committed offset.
6. With Kafka transactions, request shutdown while a transaction is open and verify outputs/offsets match actual commit or abort state.
7. Run the application in a container with a grace period matching deployment and verify the process exits before time runs out.

Do not use fixed sleeps to conclude a container has stopped. Wait on stop callbacks, container state, or specific lifecycle signals with finite timeouts. Clean up topics, consumer groups, and executors after tests so lingering threads do not affect other tests.

## 13. Common configuration mistakes

- **Confusing `shutdownTimeout` with record processing timeout:** this property serves container shutdown, not business execution limits.
- **Only raising `shutdownTimeout` when listeners hang:** dependencies can still wait indefinitely without their own timeouts.
- **Setting timeout longer than termination grace period:** Kubernetes may send `SIGKILL` before the application finishes shutting down.
- **Closing dependencies too early:** listeners are finishing while the database or HTTP client is already closed.
- **Acknowledging before processing finishes to avoid redelivery:** offsets may commit even though business logic failed.
- **Ignoring transaction timeout:** Kafka transactions can time out even while the container is still waiting on shutdown.
- **Not measuring actual shutdown time:** configured values may not reflect full application stop duration.
- **Using one timeout for every listener type:** listener groups have different processing durations and shutdown needs.

## 14. How to choose shutdownTimeout for production

In production, determine the maximum acceptable processing time, set timeouts on dependencies, measure consumer stop time, and coordinate budgets with Spring lifecycle and the orchestrator. Start from the 10-second default if workloads stop quickly, then adjust using observed telemetry.

A consistent configuration should answer:

- How is the container asked to stop and who manages its lifecycle?
- How long can a listener be processing a record or batch?
- Do HTTP, database, and producer calls have finite timeouts?
- If the listener has not acknowledged when the process stops, how will records be redelivered and handled idempotently?
- Does Spring lifecycle give listener containers enough time to stop?
- Does the container runtime or Kubernetes give the process enough time before sending `SIGKILL`?

`shutdownTimeout` works best as part of a complete graceful shutdown plan. It gives listener containers time to stop consumers cleanly; shutdown quality also depends on whether listeners can terminate, whether dependencies have timeouts, when offsets are acknowledged, and whether the platform grants the application enough time to exit.
