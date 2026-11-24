# ConsumerFailedToStartEvent

In a Spring Kafka application, calling `start()` on a listener container or letting Spring Boot auto-start `@KafkaListener` endpoints does not mean all consumer threads have actually started. A listener container may be requested to run while the corresponding consumer still has not started in time—for example, because the executor has no available threads. Without distinguishing "start requested" from "consumer started," an application can easily report healthy when in reality no consumer is reading messages.

`ConsumerFailedToStartEvent` is a Spring Kafka **application event** published when a consumer **fails to start within the wait interval specified by `consumerStartTimeout`**. This event is especially useful for detecting insufficient task executor capacity or slow/stalled startup, enabling alerts and root-cause identification before consumer lag builds up for too long.

It is a **timeout signal during consumer startup**, not a type of Kafka record, not an exception thrown by a business listener, and not definitive proof that the broker is down. This lesson explains the conditions under which the event is published, how to listen for it, how to distinguish it from other events, timeout/executor configuration, production observability, and troubleshooting runbooks.

## 1. Where ConsumerFailedToStartEvent sits in the listener lifecycle

Spring Kafka creates listener containers to manage consumers. With `@KafkaListener`, containers are typically registered in `KafkaListenerEndpointRegistry`. A `ConcurrentMessageListenerContainer` can manage multiple child consumers depending on the `concurrency` setting and partition count.

In a typical startup path:

~~~text
Spring ApplicationContext starts
               |
               v
KafkaListenerEndpointRegistry
               |
               v
Listener container start()
               |
               v
Assign consumer task to task executor
               |
      +--------+---------+
      |                  |
 Consumer thread      Consumer does not start
 starts on time       within consumerStartTimeout
      |                  |
      v                  v
 ConsumerStarting/   ConsumerFailedToStartEvent
 ConsumerStarted     (startup warning)
      |
      v
 Poll Kafka records
      |
      v
 @KafkaListener
~~~

The diagram illustrates functional relationships. Events during startup can be published on different threads and at different times; do not assume an absolute fixed event sequence across every version/container implementation.

### 1.1. What does "fails to start on time" mean?

Spring Kafka has a wait window to observe that the consumer thread has started. If the startup condition is not met within this limit, the container can publish `ConsumerFailedToStartEvent`.

Typical scenarios:

- A shared executor has run out of threads.
- `concurrency` is higher than the number of worker threads allowed to run.
- The task executor queues many tasks and the consumer task has to wait.
- A long-running task is occupying threads meant for Kafka consumers.
- Startup is delayed by lifecycle hooks or resource initialization at an inappropriate time.

The event reflects the **startup process**. It does not directly describe a record-processing error, a deserialization error, a retried record, or a failed offset commit.

### 1.2. The event does not mean the entire application is dead

Operationally, the application may still serve HTTP requests or other listeners may still run when one consumer fails to start on time. Therefore, you must decide the event's impact on:

- Logs and alerts.
- Readiness state.
- Dashboards comparing expected consumers versus started consumers.
- Recovery workflows or deployment rollbacks.

Do not default to calling `System.exit()` on every occurrence of this event; doing so can create a restart loop and mask the underlying thread shortage.

## 2. Why is this application event important?

Without a start-failure event, failures may only surface indirectly:

- Consumer lag increases.
- The topic has data, yet no listener logs appear.
- Downstream requests wait too long for Kafka results.
- Dashboards show the expected number of replicas, yet throughput is zero.
- A pod is marked Ready too early.

`ConsumerFailedToStartEvent` provides a signal closer to the source of the problem: the container did not reach the consumer startup milestone on time.

This helps distinguish three situations:

| Situation | Symptom | Investigation direction |
|---|---|---|
| Consumer failed to start on time | `ConsumerFailedToStartEvent` may be published | Task executor, concurrency, lifecycle, and startup |
| Consumer started but no records arrive | Listener is silent, possibly with zero lag | Topic, partition assignment, offsets, subscription |
| Consumer started but is stuck in poll/processing | Lag or processing time increases | Broker/network, blocked listener, `NonResponsiveConsumerEvent`, and metrics |

When a consumer fails to start, simply increasing `max.poll.records` or tuning batch size usually does not fix the root cause.

## 3. Related application events

Spring Kafka publishes multiple events across the container lifecycle. A runbook should understand how they differ.

| Event | Main timing/meaning | How is it different from ConsumerFailedToStartEvent? |
|---|---|---|
| `ConsumerStartingEvent` | Consumer thread begins the startup process | Has not necessarily completed startup |
| `ConsumerStartedEvent` | Consumer started successfully | Positive signal rather than startup timeout |
| `ConsumerFailedToStartEvent` | Consumer did not start within the wait threshold | Diagnoses slow/non-starting startup |
| `ConsumerStoppedEvent` | Consumer ran and then stopped | Related to shutdown or post-start errors |
| `ContainerStoppedEvent` | Container stopped | Container-level, not necessarily a startup failure |
| `ListenerContainerIdleEvent` | Listener received no records within the configured idle interval | Consumer may still be healthy and polling regularly |
| `NonResponsiveConsumerEvent` | Consumer did not poll on time per monitoring criteria | Can occur while running, different from start timeout |
| `ConsumerPausedEvent` / `ConsumerResumedEvent` | Consumer paused/resumed | Controls delivery, not start/stop |

The goal is to identify the **lifecycle stage** where the failure occurred. A consumer that already received `ConsumerStartedEvent` and later `ConsumerStoppedEvent` is not necessarily a `ConsumerFailedToStartEvent` scenario.

### 3.1. Start timeout differs from poll timeout

Kafka has multiple time thresholds:

- `consumerStartTimeout`: wait window used by the Spring Kafka container to detect consumer startup.
- `pollTimeout`: timeout of a single poll call in the container.
- `max.poll.interval.ms`: upper bound on the interval between polls per the Kafka consumer group protocol.
- `session.timeout.ms`: group membership liveness mechanism.
- `request.timeout.ms`: timeout for Kafka client requests.

They protect different stages. Increasing `session.timeout.ms` is not a direct fix for a consumer task that the executor has not yet run.

## 4. Listening for ConsumerFailedToStartEvent with @EventListener

Spring application events can be received using Spring `@EventListener` in a bean managed by the application context.

Simple example:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerFailedToStartEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaConsumerStartupEvents {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaConsumerStartupEvents.class);

    @EventListener
    public void onConsumerFailedToStart(
            ConsumerFailedToStartEvent event) {

        log.error(
                "Kafka consumer did not start within configured " +
                "timeout; source={}, timestamp={}",
                event.getSource(),
                event.getTimestamp());
    }
}
~~~

In the example:

- Spring automatically routes events of the matching type to the method.
- `event.getSource()` is the event source per Spring `ApplicationEvent`.
- `event.getTimestamp()` is the timestamp when the event was created.
- The handler logs briefly to avoid blocking startup any longer.

You do not manually call the event-handling method from the listener. `ConsumerFailedToStartEvent` is published by Spring Kafka when the container hits the corresponding condition.

### 4.1. Do not infer metadata not present in the event

Do not assume the event contains full Kafka client ID, topic, consumer group, and exception cause like a failed record. Because the consumer may not have started yet, much runtime information is not even available.

When more context is needed, obtain it from:

- Declared listener/container configuration.
- `KafkaListenerEndpointRegistry`.
- Startup-phase logs.
- Task executor metrics and thread dumps.
- Deployment configuration (pod, instance, release version).

Do not attach nonexistent offsets or record keys to a startup timeout report.

## 5. Listening with ApplicationListener

If the project prefers interface-based listeners, you can declare:

~~~java
import org.springframework.context.ApplicationListener;
import org.springframework.kafka.event.ConsumerFailedToStartEvent;
import org.springframework.stereotype.Component;

@Component
public class ConsumerStartFailureListener
        implements ApplicationListener<ConsumerFailedToStartEvent> {

    @Override
    public void onApplicationEvent(
            ConsumerFailedToStartEvent event) {
        startupHealthRecorder.recordFailure(
                "consumer_start_timeout",
                event.getTimestamp());
    }
}
~~~

`startupHealthRecorder` in the example represents an internal service provided by the application. When implementing it as a real class, inject the dependency via constructor injection or provide a corresponding implementation.

Both `@EventListener` and `ApplicationListener` are appropriate. Do not register both just to record the same incident, to avoid duplicate alerts.

## 6. Configuring consumerStartTimeout

`consumerStartTimeout` is a property on `ContainerProperties` used to determine how long the container waits for the consumer to start. The default value is typically documented by Spring Kafka as **30 seconds** in versions that support this feature. For a specific version, check the API and default in the running dependency.

Example configuring via the factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerContainerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(4);

    factory.getContainerProperties()
            .setConsumerStartTimeout(Duration.ofSeconds(45));

    return factory;
}
~~~

The example uses `ContainerProperties.setConsumerStartTimeout(Duration)` in Spring Kafka versions supporting `Duration`. For other versions, consult the exact Javadoc before applying.

### 6.1. Do not increase timeout to mask thread starvation

Increasing 30 seconds to 120 seconds can help if the application has a legitimately slow startup. However, if the executor only has two threads for six long-lived consumer tasks, waiting several extra minutes still will not start the remaining consumers.

Reasonable order of action:

1. Confirm that the consumer start timeout was exceeded.
2. Inspect the executor in use.
3. Determine the number of threads needed for all containers sharing the executor.
4. Check the queue and tasks occupying threads.
5. Fix executor/concurrency configuration before loosening the timeout.

### 6.2. Timeout is not a business retry limit

`consumerStartTimeout` does not govern how many times `@KafkaListener` reprocesses a record and does not control `DefaultErrorHandler`. Do not confuse it with `FixedBackOff`, `@RetryableTopic`, or DLT publish deadlines.

## 7. Typical cause: task executor lacks threads

A Kafka consumer task usually runs long-term to continuously poll records. If a listener container is given an executor with too few worker threads, consumer tasks may sit in the queue and never get a thread to run.

Suppose two listeners share an executor:

~~~text
ordersListener:
  concurrency = 3  -> needs 3 consumer threads

paymentsListener:
  concurrency = 2  -> needs 2 consumer threads

Executor shared:
  maxPoolSize = 3

Consumer tasks needing concurrent execution: 5
Max threads: 3
Remaining wait -> may exceed consumerStartTimeout
~~~

This is only a model of container thread demand; a real deployment also has schedulers, other executors, and auxiliary threads. Do not calculate capacity by multiplying pod count by concurrency and comparing directly against max threads **in one pod**: you must calculate per executor on each JVM.

### 7.1. Why can a large queue be harmful?

With certain `ThreadPoolExecutor` or `ThreadPoolTaskExecutor` configurations, once the core pool is full, tasks may be placed into the queue before the executor grows threads up to max pool size. Because consumer tasks are long-lived, the queue is not drained quickly.

Example:

~~~text
corePoolSize = 1
maxPoolSize  = 10
queueCapacity = 100

Consumer task A occupies the core thread long-term.
Consumer tasks B, C, D enter the queue.
No new threads are created because the queue still has space.

Result: consumers B/C/D fail to start on time.
~~~

If each consumer requires a long-lived thread, size the pool for concurrent consumers and clearly understand how the executor allocates threads.

## 8. Example executor sized for concurrency

Example creating a dedicated executor for a listener with `concurrency = 4`:

~~~java
@Bean("ordersConsumerExecutor")
ThreadPoolTaskExecutor ordersConsumerExecutor() {
    var executor = new ThreadPoolTaskExecutor();

    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(0);
    executor.setThreadNamePrefix("orders-kafka-");

    return executor;
}
~~~

Attach the executor to the listener factory:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerContainerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory,
        @Qualifier("ordersConsumerExecutor")
        ThreadPoolTaskExecutor ordersConsumerExecutor) {

    var factory =
            new ConcurrentKafkaListenerContainerFactory<
                    String, OrderEvent>();

    factory.setConsumerFactory(consumerFactory);
    factory.setConcurrency(4);

    factory.getContainerProperties()
            .setListenerTaskExecutor(ordersConsumerExecutor);
    factory.getContainerProperties()
            .setConsumerStartTimeout(Duration.ofSeconds(45));

    return factory;
}
~~~

Setter methods may differ in older Spring Kafka versions. The example uses `setListenerTaskExecutor(...)` and `setConsumerStartTimeout(...)` in versions providing those APIs. In production, verify that the executor is properly initialized and shut down by Spring according to lifecycle rules.

### 8.1. A bigger thread pool is not always better

Consumer concurrency must match:

- Topic partition count.
- Total Kafka containers on the JVM.
- CPU and memory.
- Database/downstream processing capacity.
- Connection limits of Kafka brokers and downstream systems.

A topic with three partitions will not scale throughput linearly simply by adding ten consumer threads in the same group; many consumers may receive no partition assignment.

Therefore, resolving startup timeouts does not mean increasing `concurrency` without limits. Allocate enough threads **for useful concurrency** while managing CPU/downstream capacity.

### 8.2. Shared executors must account for total demand

If the same executor serves three listener containers with concurrencies of 2, 4, and 3 respectively, total long-term thread demand can reach 9 when all three run. Using a pool with only 4 threads will cause queueing even if each listener factory looks valid in isolation.

In systems with many listeners, dedicate separate executors or establish a clear capacity plan for the shared executor; avoid sharing a small pool that also serves HTTP requests or batch background tasks.

## 9. Distinguishing consumer threads from other thread types

Spring Boot and the application may have multiple thread pools:

| Pool / thread | Typically serves | Related to startup? |
|---|---|---|
| Kafka listener task executor | Runs container consumer loops | Directly |
| Task scheduler | Runs periodic jobs, backpressure coordinator | Indirectly, does not replace consumer loops |
| HTTP server worker | Handles requests | Can cause resource contention if executor is improperly shared |
| Async executor | `@Async` or background jobs | Can cause thread exhaustion if shared |
| Kafka producer network thread | Producer I/O | Not the listener task executor |
| Kafka consumer heartbeat/network internals | Internal Kafka client operations | Does not replace consumer polling threads |

If a listener consumer task has not started, increasing HTTP worker threads usually does not help unless both actually share the same executor or compete for scarce JVM resources.

## 10. Is ConsumerFailedToStartEvent always caused by the executor?

**No.** Executor thread exhaustion is an important cause frequently noted in Spring Kafka documentation. However, the event indicates that the consumer did not start within the wait window—it does not prove the sole cause is the thread pool.

Other cause categories to consider:

- Startup blocked by a custom lifecycle callback.
- An unusually slow dependency or deserializer initialization step.
- Consumer factory configuration error.
- CPU pressure, long GC pauses, memory pressure.
- Deadlock or thread starvation caused by shared application resources.
- Deployment shutdown or lifecycle alteration during startup.

With an unreachable broker error, a consumer may still start and then repeatedly encounter connection errors during poll/metadata fetch. Therefore, **you cannot conclude that an unreachable broker definitely emits `ConsumerFailedToStartEvent`**.

### 10.1. Auth or deserialization errors may produce different events

A consumer that has started and hits an authentication/authorization problem while polling can report errors through the consumer runtime path and other stop/error events. Record deserialization errors inside `poll()` also differ from a startup timeout.

Read the actual exceptions, client logs, and event timeline before blaming a Kafka broker setting.

## 11. Spring application event delivery

Under standard Spring application event mechanics, listeners may be invoked synchronously on the thread publishing the event, unless the application configures an asynchronous event multicaster. This matters because code inside the event listener can affect container responsiveness or lifecycle timing.

### 11.1. Event handlers should be lightweight

Do:

- Write structured logs.
- Increment counters with fixed tags.
- Store last-start-failure timestamp in lightweight thread-safe state.
- Signal a readiness/health aggregator.

Avoid:

- Calling long HTTP APIs inside the event callback.
- Sleeping or retrying directly from the event handler.
- Running heavy database queries to "confirm the error."
- Immediately calling stop/start repeatedly on the very container that published the event.
- Extracting `KafkaConsumer` from the event and invoking consumer operations on another thread.

If you want to create tickets/notifications, forward minimal metadata to a monitoring pipeline with timeouts and a bounded queue.

### 11.2. Do not mutate consumer lifecycle recursively

Example of what not to do:

~~~java
@EventListener
public void onConsumerFailedToStart(
        ConsumerFailedToStartEvent event) {
    // Do not repeatedly start/stop/restart inside this callback
    // before determining the root cause and lifecycle state.
}
~~~

If the cause is an exhausted thread pool, repeated restarts can queue even more tasks or disrupt active consumers. Use an external coordinator outside the event callback with rate limits and clear recovery conditions.

## 12. Recording metrics and alerts from the event

Not every observability system has a built-in metric named "consumer failed to start." You can instrument it yourself:

~~~java
@Component
public class KafkaStartupMetrics {

    private final Counter consumerStartTimeouts;

    public KafkaStartupMetrics(MeterRegistry meterRegistry) {
        this.consumerStartTimeouts = Counter.builder(
                "app.kafka.consumer.start.timeout.total")
                .description(
                        "Number of Kafka consumer start timeouts")
                .register(meterRegistry);
    }

    @EventListener
    public void onStartTimeout(
            ConsumerFailedToStartEvent event) {
        consumerStartTimeouts.increment();
    }
}
~~~

The example uses Micrometer; the project must have the corresponding dependency and imports. The counter name is chosen by the application, not a guarantee that Spring Kafka exports that metric by default.

### 12.1. Metrics to combine

| Metric | Purpose |
|---|---|
| `consumer_start_timeout_total` | Count failures to start on time |
| Expected consumer count | Expected consumers based on configuration |
| Started/running consumer count | Consumers that actually started |
| Executor active threads | Whether the pool has exhausted capacity |
| Executor pool size/max size | Current thread limits |
| Executor queue depth | Whether consumer tasks are queuing |
| Container running state | Whether the container was started |
| Consumer assignment count | Whether consumers have been assigned partitions |
| Consumer lag/oldest record age | Impact on data |
| JVM CPU/GC/heap | Whether resources are slowing startup |

A single event enables fast alerting, but **consumer health** should be verified across start state, partition assignment, and data-processing progress.

### 12.2. Metric tags should not be overly granular

You can attach bounded labels such as `application`, `environment`, `listenerId`, and `instance` when cardinality is controlled. Do not attach raw exception messages, event timestamps, offsets, record keys, or event IDs as metric tags.

Some startup errors have no record context; fabricating fake offsets or message IDs will make dashboards misleading.

## 13. Building readiness state from events and consumer state

An application may have already started its HTTP server while a critical Kafka listener is not ready. If Kafka consumption is mandatory functionality, a readiness policy can enforce:

- Ready only when critical listeners are running.
- Consumer start timeouts must be flagged as failures.
- Appropriate partition assignment or sufficiently reliable connected state exists.
- Allow normal startup time before evaluating failure.
- Distinguish mandatory listeners from optional listeners.

### 13.1. Do not evaluate solely from isRunning()

`container.isRunning()` reflects container-level lifecycle state but does not necessarily prove every child consumer has started and is processing successfully. When `concurrency > 1`, look at startup events and the state of each child consumer.

### 13.2. Do not evaluate solely from consumer lag

Lag = 0 may occur because there are no records or because no partitions are assigned in some state; high lag may be the valid consequence of a planned pause. Use lag alongside events, assignments, processing rate, and container health.

### 13.3. Avoid restart loops caused by confusing readiness with liveness

Kubernetes typically uses readiness to control traffic routing, whereas liveness can trigger pod restarts. Putting startup timeout events into a strict liveness check can cause the pod to restart continuously when the executor lacks threads.

Use readiness to express temporary unavailability, alerts to page operators, and decide to restart only when evidence shows restarting is a useful recovery action. For a Kafka-only worker with no HTTP traffic, design probes according to the application's nature rather than copying a web service's liveness probe.

## 14. Concurrency and partition count

When setting:

~~~java
factory.setConcurrency(6);
~~~

the container may attempt to run up to six child consumers for one listener. This does not mean the topic has six partitions so that every consumer gets an assignment.

Example:

~~~text
Topic orders.events has 3 partitions.

Container concurrency = 6.

Some consumers may not be assigned partitions
because there are more consumers than partitions.

Yet startup must still manage consumer threads according to
the actual concurrency the container creates.
~~~

Do not increase concurrency just to make consumers "start faster." If executor capacity is lacking, raising concurrency can leave even more consumers unstarted.

### 14.1. Calculate capacity across all listener containers

For example, a JVM has:

| Listener | Concurrency | Long-lived thread demand |
|---|---:|---:|
| Orders | 4 | Up to 4 |
| Billing | 3 | Up to 3 |
| Notifications | 2 | Up to 2 |
| Total | 9 | Up to 9 |

If all three listeners share an executor with a maximum of four threads, at least part of the consumer tasks will struggle to start when all containers run simultaneously.

Reserve capacity for consumer tasks and keep appropriate headroom for shutdown/restart/rollout; avoid sharing a small pool with background tasks that can block for a long time.

## 15. Example failure caused by a shared ThreadPoolTaskExecutor

Suppose the application configures:

~~~java
@Bean("sharedExecutor")
ThreadPoolTaskExecutor sharedExecutor() {
    var executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(2);
    executor.setQueueCapacity(100);
    return executor;
}
~~~

Two Kafka listener containers both have concurrency 2 and use this executor:

~~~text
orders listener    -> consumer task 1, 2
billing listener   -> consumer task 3, 4

Pool has 2 threads.
Tasks 1, 2 run long-term.
Tasks 3, 4 sit in the queue.
Billing consumers fail to start in time.
~~~

If `consumerStartTimeout` is shorter than the task wait time, `ConsumerFailedToStartEvent` can be published.

A better solution is to allocate four threads or use dedicated executors per listener. Simply increasing queue capacity from 100 to 1000 will not allow waiting consumer tasks to run.

## 16. Do not confuse ConsumerFailedToStartEvent with broker loss

A consumer can create its client and start its polling thread even when the Kafka broker cannot be reached immediately. The Kafka client then retries metadata, network requests, or reports authentication errors depending on the case. Therefore:

- Startup events are not a direct "broker health check."
- Absence of the event does not guarantee the broker is ready.
- Presence of the event does not prove the broker is broken.

When investigating broker-related symptoms, additionally check:

1. Bootstrap servers and DNS.
2. Network connectivity to broker advertised listeners.
3. SASL/SSL credentials.
4. ACLs for consumer groups and topics.
5. Kafka client logs regarding metadata, authentication, and coordinator.
6. Partition assignments and group rebalances.

Still, start from **executor/lifecycle startup state** because that is the direct context of `ConsumerFailedToStartEvent`.

## 17. Runbook: receiving ConsumerFailedToStartEvent after deploy

An investigation procedure should follow an order:

1. Record the event timestamp and the pod/instance emitting it.
2. Identify the affected listener/container from logs and the registry.
3. Confirm whether `concurrency`, executor config, or number of listeners changed.
4. Inspect the executor thread pool: active count, max size, queue depth.
5. Inspect thread dumps to spot consumer tasks holding threads long-term or waiting tasks.
6. Check pod CPU/heap/GC pauses and resource limits.
7. Check whether other `ConsumerStartedEvent` instances were published in the same startup wave.
8. Cross-check Kafka group membership and partition assignment.
9. Fix capacity or misconfiguration before attempting a restart.
10. After recovery, verify the listener receives records and lag decreases.

Do not see a single `ConsumerFailedToStartEvent` line and restart the entire cluster. If pods share an under-threaded executor config, restarting only repeats the incident.

## 18. Runbook: application is Ready but not consuming Kafka

1. Check whether the listener registry contains a container with the expected ID.
2. Check whether the container has started or is still waiting on lifecycle.
3. Confirm whether `ConsumerFailedToStartEvent` or startup timeout logs exist.
4. Check whether the executor has enough long-lived consumer threads.
5. Confirm `@KafkaListener` uses the right factory and concurrency.
6. Check group assignment and topic partitions.
7. Check whether the listener is paused.
8. Check startup or runtime exceptions.
9. Adjust readiness policy if Ready currently does not reflect critical consumers.

Do not treat a quiet listener as a startup failure if the topic has no new records and lag is 0. You must prove the consumer actually failed to start or is not polling.

## 19. Runbook: only some child consumers start

With concurrency greater than 1, you may observe some consumers running while others fail to start.

1. Inspect the parent container and child consumers.
2. Compare the count of `ConsumerStartedEvent` against expected concurrency.
3. Inspect executor active threads and queue.
4. Check whether other tasks share the executor.
5. Inspect thread names and thread dumps.
6. Verify topic partition count is not being mistaken for actual thread count.
7. After adding capacity, verify all child consumers start and assignments stabilize.

If the executor pool has enough threads yet a consumer still does not start, investigate initialization steps in the consumer factory and lifecycle rather than just growing the pool.

## 20. Runbook: event occurs only during rolling deployment

Rolling deployments can spike CPU/GC load while a new pod starts, or start multiple listener containers simultaneously. Certain issues only surface under these conditions:

- Thread pool initializes too late or batch tasks occupy all threads.
- Concurrency configuration increased in the new release.
- Slow startup dependencies when many pods start at once.
- Network/DNS contention.
- Pod CPU limit too low, slowing thread scheduling.

Actions needed:

1. Compare old and new configs.
2. Inspect thread dumps, CPU throttling, and startup timings of the new pod.
3. Separate consumer executors from long-running startup tasks.
4. Limit the number of concurrently rolling pods if necessary.
5. Monitor events after the next rollout.

Do not simply increase `consumerStartTimeout` to silence dashboard alerts if actual startup time is violating SLOs and consumer lag is rising.

## 21. Recovery: is restarting always the right fix?

**No.** Recovery strategies depend on the root cause:

| Cause | Preferred approach |
|---|---|
| Executor ran out of threads | Add capacity/isolate executor, reduce unnecessary concurrency |
| Consumer task queued behind background tasks | Provision dedicated executor, fix thread pool queue policy |
| Legitimately slow startup | Optimize startup, extend timeout with justification |
| CPU/GC pressure | Adjust resource limits, optimize allocations |
| Misconfigured consumer | Fix configuration, redeploy |
| Container stopped | Evaluate error, start via proper lifecycle procedure |
| Post-start broker/auth error | Fix network/credentials, do not misattribute to startup timeout |

If automated restart is needed, enforce cooldowns, attempt limits, distributed coordination, and a clear recovery condition. Calling `stop()`/`start()` directly inside the event callback itself can cause lifecycle conflicts.

### 21.1. Resume does not fix startup failure

`resume()` only acts on a container that is running but paused. If the consumer never started or the container is stopped, calling resume is not a start command. Distinguish:

- `start()`: opens the container lifecycle.
- `pause()`: requests temporary suspension of record delivery in a running container.
- `resume()`: cancels a pause request.
- `stop()`: stops the container.

Do not use resume as the default reaction when encountering `ConsumerFailedToStartEvent`.

## 22. Interacting with KafkaListenerEndpointRegistry

The registry is useful for managing a listener that declares an `id`:

~~~java
@KafkaListener(
        id = "ordersConsumer",
        topics = "orders.events",
        groupId = "orders-workers",
        containerFactory = "ordersListenerContainerFactory")
public void consume(OrderEvent event) {
    orderService.processIdempotently(event);
}
~~~

In a management service:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("ordersConsumer");

if (container == null) {
    log.error("Listener container not registered");
}
else {
    log.info(
            "Listener container lifecycle running={}",
            container.isRunning());
}
~~~

`isRunning()` is a container-level lifecycle state; it is not proof that every child consumer thread and assignment is ready. When investigating a start failure, combine it with the event timeline and executor metrics.

### 22.1. Event occurring before registry query?

Startup events can be published while the Spring context is still initializing. A listener event callback should not depend on a management component that is not ready yet or expect every container to already have its final assignment. If deep checks are needed, record a lightweight signal and let a health reconciler run after the context is ready.

## 23. Testing ConsumerFailedToStartEvent

A unit test can prove `@EventListener` handles the event, but verifying that the container actually publishes the event on startup timeout requires an integration test with a real listener container and an intentionally configured executor.

### 23.1. Executor starvation scenario

1. Create a Kafka listener container with `concurrency = 2`.
2. Supply an executor with only one worker thread for two long-lived consumer tasks.
3. Configure `consumerStartTimeout` short enough for an integration test.
4. Start the container.
5. Attach an event listener or event collector.
6. Verify that the remaining consumer fails to reach the start milestone within the timeout and the event is published per the version in use.
7. Stop the container/test executor cleanly according to lifecycle after the test.

In production, never intentionally create thread starvation; this scenario is strictly for testing.

### 23.2. Sufficient capacity scenario

1. Provide an executor with enough threads for concurrency.
2. Start the listener container.
3. Observe consumer startup events.
4. Verify no startup timeout event is published under normal conditions.
5. Send a Kafka record and verify the listener processes it.

### 23.3. Metrics-only event handler scenario

1. Send a test event to the Spring `ApplicationContext` or test event publisher.
2. Verify counters/logs/health state are updated.
3. Verify the callback does not call stop/start recursively.
4. Verify there are no duplicate alerts when the application has multiple event subscribers.

### 23.4. Do not confuse with broker-offline testing

Shutting down the broker can trigger many kinds of network/client errors, but it does not guarantee producing `ConsumerFailedToStartEvent`, because the consumer thread can still start on time. To test **this event**, manipulate the actual startup timeout condition rather than simply making the Kafka broker unreachable.

## 24. Testing in multi-listener, multi-pod environments

When production runs multiple Kafka listener containers, test capacity and coordination:

1. Total concurrency per JVM.
2. Thread counts of shared/dedicated executors.
3. Topic partition counts.
4. CPU/memory limits per pod.
5. Number of pods rolling out concurrently.
6. Event collectors and metric tags capable of distinguishing listeners/instances.
7. Readiness not reporting Ready before critical consumers start.

For example, if each pod has 3 listeners with concurrencies 2, 3, and 4, total consumer tasks can reach 9 on that pod. An executor with only 4 threads may work fine when only one listener is enabled yet fail when all three start concurrently.

## 25. Common mistakes

**Treating ConsumerFailedToStartEvent as a record-processing error.** The event belongs to the consumer startup phase and does not contain a failed record to retry/DLT.

**Immediately blaming the Kafka broker.** Start timeouts can be caused by executor thread exhaustion; broker disconnects can occur after a consumer has already started.

**Only increasing consumerStartTimeout.** If tasks sit indefinitely in a queue, waiting longer does not fix the cause.

**Looking only at ThreadPoolTaskExecutor maxPoolSize.** Core size and queue policy can prevent the pool from growing threads up to max size.

**Increasing concurrency to make consumers start faster.** This can worsen thread starvation and will not boost throughput when partition counts are low.

**Sharing a small executor across many long-lived consumers.** Later tasks are queued and never run on time.

**Calling restart immediately inside the event callback.** This can create lifecycle loops and extra load.

**Failing to distinguish container running from consumer ready.** Lifecycle state does not reflect every child consumer.

**Using resume to fix a start failure.** Resume only lifts pause on a running container.

**Lacking an alert/readiness policy.** The application can report Ready even though critical consumers failed to start.

**Using a broker-offline test as proof the event works.** These are two different classes of failure.

**Putting dynamic data into metric tags.** Startup metrics need low cardinality; do not use exception messages or event timestamps as tags.

## 26. Implementation checklist

### Container configuration

- [ ] Clear `id` assigned to critical `@KafkaListener` definitions.
- [ ] `concurrency` aligned with partition counts and processing capacity.
- [ ] Executor has enough threads for all shared long-lived consumer tasks.
- [ ] Core/max pool size and queue capacity clearly understood.
- [ ] `consumerStartTimeout` reflects the real startup budget.
- [ ] Startup timeout is not used to replace Kafka network/poll timeouts.

### Event handling

- [ ] `@EventListener` or `ApplicationListener<ConsumerFailedToStartEvent>` present.
- [ ] Handler logs and updates metrics briefly without long blocking.
- [ ] Does not repeatedly restart directly inside the callback.
- [ ] Includes listener, instance, and release metadata for investigation.
- [ ] Startup failures distinguished from `ConsumerStopped`/`NonResponsive`/`Idle` events.

### Production observability

- [ ] Metrics exist for start timeouts, executor threads/queue, and consumer running counts.
- [ ] Alerts exist when critical consumers fail to start.
- [ ] Readiness reflects critical consumers if required by business logic.
- [ ] Liveness restart loops are not used in place of fixing insufficient executor capacity.
- [ ] Runbooks exist for investigating rolling deploys and thread starvation.

### Testing

- [ ] Integration test intentionally induces executor starvation and observes the event.
- [ ] Test with sufficient threads confirms normal consumer startup.
- [ ] Test with multiple listeners sharing an executor.
- [ ] Test confirms event handler does not trigger a restart loop.
- [ ] Test verifies real recovery by having the listener process records and reduce lag.

## Conclusion

`ConsumerFailedToStartEvent` is Spring Kafka's signal indicating that **a consumer did not start running within the `consumerStartTimeout` wait window**. It typically points to task executor capacity issues or startup delays, not direct proof of a broken Kafka broker, and is unrelated to a record undergoing retry. To handle it properly, observe `ConsumerStartingEvent`/`ConsumerStartedEvent`, container lifecycle, executor active threads, and task queues, then reconcile them against the total `concurrency` of all listeners on each JVM.

A reliable system should log and record metrics immediately when the event occurs, enforce readiness policies for mandatory consumers, and never restart infinitely inside the event callback itself. Provision proper threads, design suitable timeouts, test startup with integration tests, and verify that consumers actually receive records after recovery. That way, a container requested to start without running consumers is caught early before turning into backlog and pipeline SLA breaches.
