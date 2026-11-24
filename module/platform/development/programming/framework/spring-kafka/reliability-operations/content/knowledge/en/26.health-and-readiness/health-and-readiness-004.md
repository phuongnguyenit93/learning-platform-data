# Listener Container State

In Spring Kafka, the **listener container** manages the Kafka consumer lifecycle, `poll()` calls, record delivery to listeners, acknowledgments, offset commits, and shutdown. In operations, the question "is the container running?" is often the starting point for determining whether a service can still read from Kafka.

However, container state is only **one part** of system health. A container can report running while the consumer has not joined a group, has not been assigned partitions, is paused, is repeatedly retrying a failing record, or is failing to commit offsets. Conversely, a container intentionally paused during downstream maintenance can be a valid state. Therefore, health/readiness must combine **lifecycle state**, **consumer group assignment**, **poll/processing progress**, **lag**, **recent errors**, and **operational intent**.

This lesson covers how to observe and control listener container state, use `KafkaListenerEndpointRegistry`, distinguish container state from consumer/group health, integrate Spring Boot Actuator and Kubernetes readiness, manage startup/shutdown, test, and build runbooks.

## 1. What is a listener container?

With `@KafkaListener`, Spring Kafka creates endpoints and listener containers to manage one or more Kafka consumers. The container handles the technical work around the listener method:

- Creating the Kafka consumer from `ConsumerFactory`.
- Subscribing to topics or assigning partitions as configured.
- Joining the consumer group and handling rebalances.
- Calling `poll()` to fetch records.
- Dispatching records to the listener.
- Managing acknowledgments and offset commits according to `AckMode`.
- Applying error handlers, retries, recovery, and transactions if configured.
- Stopping the consumer and releasing resources when lifecycle ends.

Two common container types:

| Type | Role |
|---|---|
| `KafkaMessageListenerContainer` | Manages a single consumer and its processing lifecycle. |
| `ConcurrentMessageListenerContainer` | Parent container managing multiple child containers/consumer threads based on `concurrency`. |

When using `@KafkaListener`, applications do not usually create and manage each `KafkaConsumer` directly. `KafkaListenerEndpointRegistry` manages the listener containers registered by the annotation infrastructure, allowing the application to look up containers by listener ID.

### A listener container is not a consumer group

A consumer group is a Kafka broker/coordinator concept; a listener container is a Spring application-side management object. One container can create multiple consumer members. Multiple containers can share the same `group.id`, and a group can also contain consumers from different pods/application instances.

Therefore, local container state alone cannot prove the entire group is healthy.

## 2. States that must be distinguished

In operations, you should not rely on just two labels, "UP/DOWN." At minimum, separate these concepts:

| State | Meaning | What to verify |
|---|---|---|
| Started/running | Container has started per Spring lifecycle | Is the consumer thread actually running and polling? |
| Stopped | Container is no longer running | Was the stop intentional or caused by an error? |
| Starting | Initializing consumer/container | Has it joined the group and received assignments? |
| Paused | Container or partitions requested to pause record intake | Is the pause intentional? Is downstream ready to resume? |
| Assigned | Consumer is assigned one or more partitions | Does the current assignment fit the workload? |
| Idle | Container/partitions received no records over an interval | Does the topic have no traffic, or can the consumer not fetch? |
| Non-responsive | Consumer is not polling at the expected cadence | Is the listener blocked, hitting GC, deadlocked, or seeing slow I/O? |
| Processing stalled | Records are received, but offsets/processing do not advance | Poison pill, retry loop, downstream issue, or commit issue? |
| Degraded | Container runs, but some functionality/partitions fail SLA | Can it keep accepting traffic, or should readiness refuse? |

`isRunning()` only answers a question about Spring container lifecycle. It does not replace the remaining states.

## 3. Observing containers with KafkaListenerEndpointRegistry

Spring Kafka provides `KafkaListenerEndpointRegistry` to access listener containers registered via `@KafkaListener`.

Example listener with a stable ID:

~~~java
@Component
public class OrdersListener {

    @KafkaListener(
            id = "ordersListener",
            topics = "orders.events",
            groupId = "orders-service")
    public void onMessage(OrderEvent event) {
        // Business processing.
    }
}
~~~

Looking up the container from the registry:

~~~java
@Component
public class ListenerContainerInspector {

    private final KafkaListenerEndpointRegistry registry;

    public ListenerContainerInspector(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public boolean isOrdersListenerRunning() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        return container != null && container.isRunning();
    }
}
~~~

Key imports include `KafkaListenerEndpointRegistry`, `MessageListenerContainer`, `KafkaListener`, and Spring component annotations. `OrderEvent` is an application-defined data type.

### Listener IDs must be stable

Using an explicit ID lets health indicators, management endpoints, logs, and runbooks refer to the exact same container. Avoid building health logic that grabs the first container from the registry, because an application can have multiple listeners.

`registry.getListenerContainer(id)` can return `null` if the ID does not exist or the container is not registered yet. Distinguish "listener not configured" from "listener configured but stopped"; the two cases have different operational meanings.

### Listing containers

You can retrieve IDs and containers from the registry to display status:

~~~java
for (String id : registry.getListenerContainerIds()) {
    MessageListenerContainer container =
            registry.getListenerContainer(id);

    if (container != null) {
        log.info(
                "Kafka listener id={} running={}",
                id,
                container.isRunning());
    }
}
~~~

This snippet is for local inspection. Do not log repeatedly on every high-frequency health check; use metrics or management endpoints at an appropriate rate.

## 4. Running does not mean ready to process records

A container may have started yet still be:

- Creating the consumer and connecting to brokers.
- Joining the consumer group.
- Waiting for the coordinator to complete a rebalance.
- Unassigned any partitions because the group has other members or too few partitions.
- Paused for backpressure.
- Retrying auth/authorization.
- Receiving no records because the topic has no traffic.
- Experiencing processing errors while the error handler keeps the container alive.

A simple decision diagram:

~~~mermaid
flowchart TD
    A[Container isRunning?] -->|No| B[Stopped / startup incomplete]
    A -->|Yes| C[Is consumer polling on cadence?]
    C -->|No| D[Non-responsive / thread blocked]
    C -->|Yes| E[Is partition assignment valid?]
    E -->|No| F[Join group / rebalance / group config]
    E -->|Yes| G[Intentionally paused?]
    G -->|Yes| H[Paused per policy]
    G -->|No| I[Are processing and offsets advancing?]
    I -->|Yes| J[Healthy per policy]
    I -->|No| K[Retry / lag / commit / downstream]
~~~

Not every listener must have partition assignments immediately at startup. If concurrency exceeds partition count, some child consumers may receive no partitions. For a topic with no traffic, the container can still poll normally without processing records. Health policies must understand the group's design.

## 5. Concurrent containers and child consumer state

With `concurrency=3`, `ConcurrentMessageListenerContainer` can manage three consumer threads. The parent container reporting running does not mean every child consumer has partitions or throughput.

~~~text
ordersListener (parent)
  child-0: running, assigned P0/P1
  child-1: running, assigned P2
  child-2: running, no assignment (can be normal)
~~~

If a topic only has three partitions and the group has more than three consumers, some consumers may have no assignment. That is not automatically an error. If one child stops unexpectedly while other children keep running, parent state alone may not adequately reflect degraded capacity.

To evaluate accurately:

- Know the listener ID and configured concurrency.
- Know the partition count and expected group membership.
- Track rebalance/assignment events.
- Observe consumer polls and per-partition lag.
- Distinguish a legitimately unassigned child from a child unable to join the group.
- Do not assume "expected active children = concurrency" across every topology.

If per-child state is needed, use lifecycle/metrics APIs appropriate for your Spring Kafka version. Avoid reaching into container internals or threads to infer state when public APIs provide the required signals.

## 6. Pause and resume are not stop and start

Spring Kafka supports pausing/resuming listener containers and, in appropriate versions, pausing/resuming specific partitions. Pausing is commonly used for backpressure or temporary maintenance.

| Action | Meaning |
|---|---|
| `start()` | Starts the container lifecycle. |
| `stop()` | Stops the container and consumer per lifecycle. |
| `pause()` | Pauses record delivery per container mechanism; the consumer may still need to poll to maintain membership. |
| `resume()` | Resumes record delivery after pause. |
| Pause a partition | Reduces/suspends fetching from selected partitions, depending on API/version. |

Pause can be an **expected** state. If a downstream database is overloaded and the application intentionally pauses, readiness can stay `ACCEPTING_TRAFFIC` if the service can still handle other requests; or it can move to `REFUSING_TRAFFIC` if Kafka processing is a mandatory function of the instance. This is an SLA decision, not a universal rule.

### Checking pause state

Spring Kafka versions provide pause-state APIs on listener containers, such as `isPauseRequested()` and `isContainerPaused()`. Check your version's API; whether a pause is requested and whether the container is actually paused can differ.

Do not use pause state in place of group membership. A consumer can hold assigned partitions while paused; an unassigned consumer can still poll and remain running.

### Do not resume blindly

Before resuming:
1. Identify who requested the pause and why.
2. Verify downstream has recovered.
3. Confirm the container is running and its lifecycle is not stopping.
4. Use appropriate container APIs instead of calling `KafkaConsumer` from a background thread.
5. Monitor lag/processing after resuming.

Resuming too early can send traffic straight back into an overloaded dependency.

## 7. Container state and consumer group assignment

The Kafka group coordinator decides which member owns which partitions. A local container cannot know the entire group topology from `isRunning()` alone.

Example:

~~~text
Group: orders-service

Pod A:
  ordersListener running
  P0, P1 assigned

Pod B:
  ordersListener running
  P2, P3 assigned

Pod C:
  ordersListener running
  no assignment (concurrency > partitions)
~~~

All three containers are running. Pod C processes no records because it has no partitions; that can be completely valid. If Pod A loses its assignment after a rebalance, it can still be running while partitions moved to Pod B.

When group-level health is needed, combine:
- Consumer group member count.
- Partition assignment.
- Rebalance count/duration.
- Committed offsets and lag.
- Container lifecycle.
- Poll/processing progress.

You can use Kafka `AdminClient` or a dedicated metrics system to observe the group from an independent health/monitoring component. Never create a new `KafkaConsumer` and subscribe it to the same group just to "check health," because it will join the group and trigger a rebalance.

## 8. Startup readiness: do not mark ready too early

When Spring Boot starts, the application context may have refreshed and the web server may be listening while Kafka listener containers are still initializing. If readiness transitions to `ACCEPTING_TRAFFIC` too early, a load balancer can send traffic to an instance whose Kafka processing is not ready yet.

A startup policy must decide:
- Which listeners are mandatory for the instance to serve its function properly?
- Should it wait for container running or wait for group assignment?
- Is the instance allowed to become ready when the topic has no traffic?
- If concurrency exceeds partition count, are unassigned children acceptable?
- Does a temporary Kafka outage keep the pod unready, or can APIs still serve?
- How long is the startup timeout before transitioning to degraded/failed?

**Do not wait for a first business record before marking ready** if a topic may have no traffic. Readiness should rely on evidence that the consumer initialized/joined the group/met topology conditions, not the random arrival of a message.

## 9. Spring Boot Availability and readiness state

Spring Boot provides application availability states, typically using `ReadinessState.ACCEPTING_TRAFFIC` and `ReadinessState.REFUSING_TRAFFIC`. `AvailabilityChangeEvent` can be used to switch application state when a mandatory Kafka listener is inactive.

Illustrative example of a component managing readiness:

~~~java
@Component
public class KafkaReadinessCoordinator {

    private final ApplicationContext applicationContext;
    private final KafkaListenerEndpointRegistry registry;

    public KafkaReadinessCoordinator(
            ApplicationContext applicationContext,
            KafkaListenerEndpointRegistry registry) {
        this.applicationContext = applicationContext;
        this.registry = registry;
    }

    public void refuseTraffic() {
        AvailabilityChangeEvent.publish(
                applicationContext,
                ReadinessState.REFUSING_TRAFFIC);
    }

    public void acceptTraffic() {
        AvailabilityChangeEvent.publish(
                applicationContext,
                ReadinessState.ACCEPTING_TRAFFIC);
    }

    public boolean isRequiredListenerRunning(String listenerId) {
        MessageListenerContainer container =
                registry.getListenerContainer(listenerId);

        return container != null && container.isRunning();
    }
}
~~~

This example uses Spring Boot Availability APIs and Spring Kafka's registry. Key imports include `ApplicationContext`, `AvailabilityChangeEvent`, `ReadinessState`, `KafkaListenerEndpointRegistry`, and `MessageListenerContainer`.

This code only illustrates readiness control; it does not yet register listener events, check group assignment, or decide when `acceptTraffic()` may be called. In production, use a state coordinator that prevents races across startup, stop, retry, and shutdown.

### Readiness is the state of the application instance

One container can stop while the application continues serving other endpoints. If Kafka is the core function of the service, readiness can switch to `REFUSING_TRAFFIC`. If the Kafka listener is only a background feature that does not affect API serving capability, marking the entire pod unready may be undesirable.

Set policy based on **the listener's role** and SLA, rather than flipping readiness indiscriminately on every listener event.

## 10. Liveness is not readiness

Spring Boot/Kubernetes commonly separates:

- **Liveness:** is the process alive and able to keep going on its own; failure can make the orchestrator restart the pod.
- **Readiness:** should the instance currently receive new traffic; failure removes the pod from service endpoints without necessarily restarting it.
- **Startup probe:** gives the application time to start before liveness/readiness take effect per configuration.

Do not treat a brief Kafka outage as a liveness failure if the container can retry on its own and the process is still healthy. If the liveness probe restarts pods whenever brokers disconnect, the system can trigger a restart storm, increasing rebalances and slowing recovery.

Readiness can report `REFUSING_TRAFFIC` when a critical listener is inactive, though you must decide whether the pod can still process or self-recover without receiving HTTP traffic.

### Illustrative health groups configuration

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,kafkaListener
        liveness:
          include: livenessState
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Property names and health group behavior depend on Spring Boot version and Actuator configuration. `kafkaListener` in the example is the name of a custom health contributor registered by the application, not a default contributor created automatically merely because Spring Kafka is present.

Do not include Kafka broker connectivity in liveness by default. If the readiness group includes a custom contributor, define timeouts, caching, and how retries/paused state/expected assignments are reflected.

## 11. Creating a HealthIndicator for a listener container

A custom `HealthIndicator` can reflect the state of a mandatory listener:

~~~java
@Component("kafkaListener")
public class KafkaListenerHealthIndicator implements HealthIndicator {

    private final KafkaListenerEndpointRegistry registry;

    public KafkaListenerHealthIndicator(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    @Override
    public Health health() {
        MessageListenerContainer container =
                registry.getListenerContainer("ordersListener");

        if (container == null) {
            return Health.down()
                    .withDetail("listener", "ordersListener")
                    .withDetail("reason", "not_registered")
                    .build();
        }

        if (!container.isRunning()) {
            return Health.outOfService()
                    .withDetail("listener", "ordersListener")
                    .withDetail("reason", "container_stopped")
                    .build();
        }

        return Health.up()
                .withDetail("listener", "ordersListener")
                .withDetail("running", true)
                .build();
    }
}
~~~

This example uses Spring Boot Actuator's `HealthIndicator` and `Health`. Statuses `DOWN`, `OUT_OF_SERVICE`, and `UP` must be mapped to readiness/liveness according to the application's health groups. Not every deployment wants one stopped listener to make the entire actuator health return `DOWN`.

### Limitations of a simple health indicator

The indicator above only checks:
- Whether the listener ID is registered.
- Whether the container reports running.

It does not verify:
- That the consumer has joined the group.
- That valid partition assignments exist.
- That polling is progressing.
- That the consumer is not paused.
- That the listener processes records successfully.
- That offset commits are advancing.
- That lag is within SLA.

Do not name this result "Kafka processing healthy" if it only checks `isRunning()`. A more accurate name is "listener container lifecycle running."

## 12. Multi-condition health policies

A policy for a critical listener can combine signals:

~~~text
READY when:
  container is registered
  AND container is running
  AND no unexpected stop occurred
  AND consumer polling has not exceeded non-responsive threshold
  AND pause state matches policy
  AND assignment satisfies design condition (if needed)
  AND lag does not exceed SLA (if required by policy)
~~~

Not every condition is needed in every service. For example:
- A listener with no traffic can still be ready.
- A consumer without partitions because concurrency exceeds partition count can be normal.
- A listener intentionally paused for maintenance may be unready per policy.
- Rising lag during a traffic burst does not necessarily require marking the pod unready if the instance can still catch up within SLA.

### Do not query Kafka brokers on every health probe

The health endpoint can be called multiple times per second by the orchestrator. If every probe makes multiple `AdminClient` requests, health checks can increase broker load and trigger additional failures when the broker is already overloaded.

Best practices:
- Use existing lifecycle/metrics state.
- Collect group/lag state with an independent monitor at a reasonable cadence.
- Cache results outside the health request path.
- Enforce finite timeouts and never block consumer threads.
- Return health with a timestamp/freshness indicator to distinguish stale observations.

A health indicator should read aggregated state, not kick off a heavy verification workflow on every HTTP GET.

## 13. Listener container lifecycle and SmartLifecycle

Spring Kafka listener containers participate in the Spring lifecycle. Related properties can include:
- `autoStartup`: whether the container starts automatically with the application context.
- `phase`: relative start/stop ordering in the lifecycle.
- `shutdownTimeout`: shutdown wait duration in container properties in supported versions.
- `missingTopicsFatal`: policy when configured topics do not exist yet in certain configurations/versions.
- `stop()` callback: allows coordinating asynchronous shutdown completion per the lifecycle API.

Verify exact property names and configuration locations against your Spring Kafka/Boot version.

### autoStartup=false

A listener can be configured not to start automatically:

~~~java
@KafkaListener(
        id = "manualOrdersListener",
        topics = "orders.events",
        autoStartup = "false")
public void handle(OrderEvent event) {
    // Handle.
}
~~~

In this case the container is registered but does not start automatically with the context. A health indicator that only checks "registered" would misreport. If a manual-start listener is intentional by design, the health policy must know when it needs to run and who is responsible for starting it.

### Conditional startup

The registry can be used to start a listener once an application condition is ready:

~~~java
MessageListenerContainer container =
        registry.getListenerContainer("manualOrdersListener");

if (container != null && !container.isRunning()) {
    container.start();
}
~~~

Invoke this only from an appropriate lifecycle coordinator. Do not restart inside every health request or event callback. If multiple components control the same container, use a single state machine to prevent races.

## 14. Controlled shutdown

When the application receives a stop signal, containers must terminate via lifecycle so consumers close cleanly. A typical sequence:

1. Mark the instance as shutting down.
2. Transition readiness to `REFUSING_TRAFFIC` if the service should no longer accept workloads.
3. Request listener containers to stop per lifecycle.
4. Let in-flight records finish within the allowed time or roll back per policy.
5. Commit/abort Kafka transactions as configured.
6. Stop auxiliary workers and wait for in-flight work up to a cap.
7. Confirm containers have stopped.
8. Close the application context.

Do not treat `isRunning()` immediately after calling `stop()` as proof that all consumer threads have finished cleanup if the stop API is asynchronous/callback-based. Use stop callbacks/lifecycle signals or version-appropriate terminal states.

### Shutdown timeout

If the timeout is too short, in-flight records may be interrupted and redelivered after restart. If the timeout is too long, the pod can exceed the orchestrator's termination grace period. Measure listener p99, retry/backoff, and downstream shutdown behavior to choose a sensible bound.

Never keep a container stopping indefinitely waiting for an external call without a timeout. All I/O inside a listener needs a finite timeout and a recovery policy.

## 15. Interaction with consumer rebalances

When a container stops, the consumer leaves the group or loses heartbeats; the coordinator can rebalance partitions to remaining members. When a container merely pauses, it can still maintain membership/polling per client mechanics. When a container is running yet non-responsive, the group can treat the member as stalled and reassign partitions.

Related events/callbacks:
- `ConsumerStartedEvent` / `ConsumerStoppedEvent`: consumer lifecycle.
- `ContainerStoppedEvent`: container lifecycle.
- `onPartitionsAssigned`: new partitions assigned.
- `onPartitionsRevoked`: partitions about to be revoked.
- `onPartitionsLost`: consumer lost ownership.
- `NonResponsiveConsumerEvent`: polling unresponsive beyond expectation.

Do not infer assignments solely from start/stop events. When readiness depends on partition ownership, use an appropriate group/assignment state source.

### Rebalance is not always a container restart

A consumer can have partitions revoked and new partitions assigned while the container stays running. If every rebalance flips readiness `DOWN` then `UP`, the system can cause readiness flapping. Use a grace window or evaluate assignment state after rebalancing finishes.

## 16. Non-responsive state while the container is running

A container can have `isRunning()=true` while the consumer thread is blocked for a long time inside a listener or downstream call. In that scenario, liveness/readiness based on `isRunning` can report `UP` while message processing has stalled.

Spring Kafka provides non-responsive consumer monitoring, typically involving `monitorInterval` and `noPollThreshold` on container properties. `NonResponsiveConsumerEvent` can help detect consumers not polling at the expected cadence.

~~~java
factory.getContainerProperties().setMonitorInterval(10);
factory.getContainerProperties().setNoPollThreshold(3.0);
~~~

Verify the setters and units in your Spring Kafka version. `monitorInterval` is typically the monitor interval in seconds; `noPollThreshold` is a multiplier compared against the expected poll window in the framework mechanism. Do not copy values without checking API/version.

### Investigating non-responsive consumers

- Listener calling HTTP/DB without timeouts.
- `Thread.sleep` or blocking retries on the consumer thread.
- Deadlocks/lock contention.
- Stop-the-world GC or CPU starvation.
- Batch too large or single record taking too long.
- Long-running transactions, producer sends waiting too long.
- Error handler backoff holding the poll thread.
- Hanging network/broker operations.

When a consumer becomes non-responsive, increasing the readiness grace period can prevent short-lived false positives, but it does not fix why the listener is blocking.

## 17. Health and lag: read them together

A running container can fall behind the producer. Lag is the distance between the log position and consumer group progress, according to the offset type used in measurement.

Example:

~~~text
orders.events partition 0:
  end offset       = 50,000
  committed offset = 49,900
  lag              = 100

partition 1:
  end offset       = 80,000
  committed offset = 20,000
  lag              = 60,000
~~~

The container can be running and processing P0 normally while P1 is stuck. A health indicator checking only the parent container misses this issue.

When evaluating lag:
- Monitor per partition, not only totals.
- Watch lag trends (rising/falling), not just a single snapshot.
- Distinguish producer traffic bursts from processing stalls.
- Inspect retry/DLT and committed offsets.
- Do not automatically mark a pod unready during temporary lag spikes if the instance can still catch up within SLA.

If the service requires every partition to be processed within a deadline, use workload-specific lag/record-age thresholds.

## 18. Health when a topic has no traffic

A topic may receive no records for long periods while the consumer works properly. `ListenerContainerIdleEvent` and `ListenerContainerPartitionIdleEvent` can fire to observe idleness; that is not automatically a container fault.

Do not use "no records in 60 seconds" as a liveness failure if continuous traffic is not guaranteed. Readiness should rely on:
- Container lifecycle and consumer poll health.
- Required group membership/assignment.
- Pause state and expected maintenance.
- Auth/ACL errors and non-responsive signals.
- Lag or business freshness when input data exists.

If a topic has a heartbeat contract or freshness SLA, alert on missing data per business rules; that is **source/data freshness health**, not necessarily listener container health.

## 19. Building a readiness policy with a state machine

To avoid health flapping, use a state machine or coordinator to manage state:

~~~mermaid
stateDiagram-v2
    [*] --> STARTING
    STARTING --> READY: Container started and startup checks pass
    STARTING --> DEGRADED: Startup deadline exceeded
    READY --> DEGRADED: Listener error/non-responsive/lag exceeds SLA
    DEGRADED --> READY: Poll/processing stable over recovery window
    READY --> REFUSING: Intentional shutdown or required listener stopped
    DEGRADED --> REFUSING: Cannot accept workload safely
    REFUSING --> STOPPED: Container lifecycle ended
    STOPPED --> STARTING: New start command issued
~~~

This is a recommended operational model, not a built-in Spring Kafka state enum.

A sound policy needs:
- **Startup grace period:** avoids reporting unhealthy while listeners join the group.
- **Failure threshold:** avoids transitioning to degraded on a single transient fault.
- **Recovery window:** requires stability for an interval before accepting traffic again.
- **Intent flag:** distinguishes intentional stops from unexpected stops.
- **Expected assignment:** accounts for partition counts/concurrency/topology.
- **Pause policy:** pause can mean degraded or expected maintenance.
- **Stale data detection:** never use stale metrics to conclude healthy.
- **Single owner:** only one coordinator updates readiness.

## 20. Testing container state

Test lifecycle states, group/assignment behavior, and readiness mapping separately. Example scenarios:

| Scenario | Container expectation | Readiness expectation |
|---|---|---|
| Application just started | May not be running/joined yet | `STARTING`/`REFUSING` during grace period |
| Listener started, group stable | Running | `READY` if listener is mandatory |
| Topic has no records | Running, polling normally | `READY` |
| Intentional consumer pause | Running but paused | Per pause policy |
| Listener stopped unexpectedly | Stopped | `DEGRADED` or `REFUSING` |
| Consumer non-responsive | May still report running | `DEGRADED`/`REFUSING` after threshold |
| Brief rebalance | Container remains running | Stay `READY` or grace window |
| Rolling shutdown | Intentional stop | `REFUSING` |
| Manual-start listener not yet started | Registered but stopped | Per startup policy, usually not `READY` if mandatory |

### Testing the registry and HealthIndicator

Unit tests with mocked registry/containers can verify:
- Non-existent listener ID returns appropriate status.
- Stopped container is not marked `UP`.
- Running container is evaluated per policy.
- Intentional pause is not misclassified.
- An optional listener does not make the entire application unready.

For integration tests, use a compatible test Kafka broker/Embedded Kafka:
1. Start the Spring context.
2. Wait for the container to start.
3. Verify the registry returns the right listener ID.
4. Wait for group assignment per test topology.
5. Publish records and confirm the listener processes them.
6. Stop the container and verify readiness changes per policy.
7. Restart it and verify readiness recovers only after required conditions are met.
8. Test concurrency and rebalances to avoid assuming every child always holds assignments.

Do not require sending records to verify readiness if topics can be idle; assignment/poll health is usually a better signal.

## 21. Actuator endpoints and information protection

Actuator health can expose aggregated status. In production:
- Expose only needed endpoints.
- Enforce access control and network restrictions.
- Do not let health details expose broker hostnames, group topology, or detailed security errors on public endpoints.
- Use separate health groups for liveness/readiness.
- Avoid heavy synchronous network checks on every probe.
- Set timeouts for custom health checks.
- Prevent exceptions from health contributors from hanging actuator endpoints.

If health details are needed by operations, restrict details to authorized/internal views while Kubernetes probes use only HTTP status and concise state.

## 22. Monitoring and metrics for listener state

An operational metric set can include:

| Logical Metric | Meaning |
|---|---|
| `listener_container_running` | Current lifecycle state of the listener. |
| `listener_container_paused` | Whether the container is paused. |
| `listener_start_total` / `listener_stop_total` | Count of recorded start/stop events. |
| `listener_nonresponsive_total` | Count of non-responsive consumer poll events. |
| `listener_assignment_partitions` | Number of partitions currently assigned per listener/member. |
| `consumer_lag` | Backlog by group/topic/partition. |
| `listener_processing_rate` | Rate of records processed by the listener. |
| `listener_processing_duration` | Listener latency. |
| `listener_rebalance_total` | Number of observed rebalances. |
| `listener_last_success_timestamp` | Most recent successful processing timestamp, when traffic exists. |

These names are logical metrics; exact exported names depend on Micrometer, Spring Kafka, and the registry. Avoid attaching event IDs, offsets, or customer IDs as metric labels. Use topic/group/listener/environment and partition where cardinality is appropriate.

### Last successful processing does not replace poll health

If a topic has no traffic, the last successful processing timestamp can grow old while the consumer polls normally. Therefore distinguish:
- Last successful poll (if a measurement source exists).
- Last record received.
- Last listener success.
- Last committed offset advancement.
- Last business event applied.

Each milestone answers a different question.

## 23. Runbook: Container stopped unexpectedly

1. Identify listener ID, application instance, group ID, and stop timestamp.
2. Inspect `ConsumerStoppedEvent` reason and root exception.
3. Confirm whether the stop was from a deployment/manual action.
4. Check Kafka broker connectivity, authentication/authorization, and consumer group.
5. Check transaction/producer fencing if the listener uses Kafka transactions.
6. Identify which member received the reassigned partitions.
7. Check committed offsets and potential redelivered records.
8. Fix the root cause before restarting; use backoff if the error is recoverable.
9. Confirm container started, consumer polling, assignments, and lag recovery.

Never reset offsets just because a container stopped.

## 24. Runbook: isRunning=true but listener processes no records

1. Check whether the consumer has non-responsive events or abnormal poll intervals.
2. Check group assignment; the container may be running without any assigned partitions.
3. Check pause state at container/partition level.
4. Compare broker end offsets and committed offsets.
5. Check whether the listener is retrying a poison pill or blocked on downstream.
6. Check deserialization errors, error handlers, and DLT recovery.
7. Check transaction aborts/fencing and commit failures.
8. Measure listener duration, GC, CPU, and thread state.
9. Mark healthy only when processing/poll progress satisfies policy.

## 25. Runbook: Readiness flapping during rebalances

1. Build a timeline of container lifecycle, rebalance callbacks, and readiness changes.
2. Check whether readiness depends directly on a transient assignment callback.
3. Check the group protocol and cooperative/eager rebalancing.
4. Add startup/rebalance grace windows aligned with SLA.
5. Distinguish container running from temporary partition ownership.
6. Do not transition to `REFUSING_TRAFFIC` on a single partition revocation.
7. Check whether lag/processing actually stalled.
8. Verify readiness stability in rolling deploy/scale tests.

## 26. Runbook: Container paused but health reports UP

1. Determine whether the pause is intentional or caused by backpressure/stuck recovery.
2. Check pause scope: entire container or specific partitions.
3. Read owner/reason and pause duration.
4. Check whether downstream has recovered and can accept traffic.
5. Check policy: should intentional pause be `READY` or `REFUSING`?
6. Resume via container API once conditions are met.
7. Monitor lag and listener processing after resuming.
8. Update the health indicator to reflect pause per policy rather than only `isRunning()`.

## 27. Runbook: Container running but group has no assignment

1. Confirm the listener subscribed to the right topic/group.
2. Check topic existence and partition count.
3. Check group members, static member IDs, and rebalance state.
4. Check whether concurrency exceeds partition count; unassigned children can be normal.
5. Check join-group/read-topic ACLs and broker logs.
6. Check whether partitions are already assigned to other members.
7. Do not spin up a probe consumer joining the same group to test.
8. If the listener requires assignments, define the health condition per topology; otherwise check poll/lifecycle only.

## 28. Runbook: Shutdown takes too long or records are redelivered

1. Check the orchestrator's termination grace period.
2. Compare listener processing p99, retry backoff, and downstream timeouts.
3. Check container shutdown timeout/phase and stop callbacks.
4. Identify in-flight records when the container receives stop.
5. Check Kafka transaction commits/aborts and committed offsets.
6. If records are redelivered, verify business idempotency.
7. Set finite timeouts for external I/O and worker pools.
8. Test rolling shutdown in staging with records in flight.
9. Verify the pod terminates within limits without losing business outcomes.

## 29. Runbook: Health endpoint is slow or increases Kafka load

1. Check whether the health indicator calls `AdminClient` or makes broker network requests on every probe.
2. Measure endpoint latency and probe frequency.
3. Decouple metrics/group sampling from the HTTP request path.
4. Cache group/lag results with timestamps and finite timeouts.
5. Use container lifecycle state for lightweight checks.
6. Set a stale-data policy so stale caches do not report `UP`.
7. Limit details and log volume.
8. Verify readiness/liveness do not jointly trigger a restart loop during broker outages.

## 30. Listener container state checklist

| Checkpoint | Question to answer | Evidence |
|---|---|---|
| Registry | Is the listener ID properly registered? | `KafkaListenerEndpointRegistry` and endpoint IDs. |
| Lifecycle | Is the container running/stopped as expected? | `isRunning()`, start/stop events. |
| Concurrency | Are parent/child consumers properly understood? | Concurrency config, child metrics. |
| Assignment | Does the consumer hold appropriate partition ownership? | Rebalance events/group assignments. |
| Pause | Is the container/partition paused per policy? | Pause state, owner, and reason. |
| Poll health | Does the consumer continue polling on cadence? | Non-responsive events, poll metrics. |
| Processing | What are listener success/failure attempts and latency? | Micrometer metrics/logs. |
| Offset | Are committed offsets and lag advancing within SLA? | Group offsets, lag per partition. |
| Readiness | Which listeners are truly mandatory for the instance to accept traffic? | Readiness policy and health groups. |
| Liveness | Can a Kafka outage trigger a restart storm? | Probe config and incident history. |
| Startup | Is there a grace period for listener/group setup? | Startup/readiness state transitions. |
| Shutdown | How are in-flight work and transactions handled? | Stop callbacks, timeouts, commits/aborts. |
| Recovery | Do restarts have backoff and clear ownership? | Lifecycle coordinator and retry budget. |
| Observability | Do health/metrics distinguish idle, paused, non-responsive, and stopped? | Dashboards, alerts, and runbooks. |

**Conclusion:** Listener container state is the foundation for Spring Kafka health and readiness, but **running does not mean processing healthy**. Use `KafkaListenerEndpointRegistry` to locate the exact container, and distinguish parent/child concurrency, pause state, assignments, poll health, processing progress, and committed offsets. Readiness should reflect the listener's role for the service and include grace/recovery windows; liveness should not restart pods merely because Kafka briefly disconnects. When health indicators read lightweight lifecycle state, combined with independently collected group/lag metrics and runbooks for stops/rebalances/shutdowns, the system avoids false positives, readiness flapping, and restart storms.
