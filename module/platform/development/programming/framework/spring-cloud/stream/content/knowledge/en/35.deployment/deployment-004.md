# Liveness, Readiness, and the Impact of Broker Failures

When deploying Spring Cloud Stream applications to Kubernetes, many teams set up a single health check endpoint and use that same endpoint for both liveness and readiness. This practice easily causes incidents: if Kafka, RabbitMQ, or Pulsar temporarily loses connectivity, all Pods may get restarted even though the application is functioning normally and automatically reconnecting. Conversely, an endpoint simply returning HTTP 200 does not prove consumers are receiving messages or producers are writing successfully.

To design probes properly, you must distinguish **process liveness**, **traffic acceptance capability**, **broker communication capability**, and **event flow progress**. Spring Boot Actuator supports liveness/readiness based on `ApplicationAvailability`, while Spring Cloud Stream provides per-binder health indicators. Kubernetes offers startup, liveness, and readiness probes with very different impacts. This article explains how to combine them without creating restart loops, masking messaging failures, or breaking consumer recovery.

## 1. Four Distinct Health Questions

Before writing a probe, identify the question the check needs to answer.

| Question | Appropriate Signal | On Failure |
|---|---|---|
| Is the process still capable of self-recovering? | Liveness | Kubernetes may restart the container |
| Is the instance ready to serve traffic routed to it? | Readiness | Kubernetes removes the Pod from the Service's endpoint set |
| Can the binder connect to and communicate with the broker? | Binder/connection health and telemetry | Alert, investigate; may affect readiness depending on business logic |
| Is the event stream progressing properly? | Lag, throughput, publish errors, acks, retries, DLQ, binding state | Investigate processing capability; not necessarily a restart |

**Liveness** is an internal signal: can the application still make progress or self-heal? **Readiness** is a traffic contract: should this instance accept requests sent by the router? **Broker health** indicates how ready an external dependency is. **Flow health** requires verifying that data is actually moving as expected.

A disconnected broker does not automatically deadlock the JVM. Nor does a broker answering ping mean the pipeline is processing successfully. These signal layers must be managed separately.

## 2. Kubernetes Startup, Liveness, and Readiness Probes

Kubernetes supports three probe types:

- **Startup probe**: Checks whether the application has finished initialization; until the startup probe succeeds, Kubernetes does not run liveness or readiness probes.
- **Liveness probe**: After failing enough consecutive times, kubelet restarts the container according to its restart policy.
- **Readiness probe**: When it fails, the Pod is marked NotReady and excluded from receiving traffic via a Kubernetes Service; kubelet continues probing and does not restart solely due to readiness failure.

The startup probe runs only during initialization. Liveness and readiness are checked periodically throughout the container's lifecycle.

Decision flow example:

~~~mermaid
flowchart TD
    A[Pod running] --> B{Startup complete?}
    B -->|No| C[Continue startup probe within threshold]
    B -->|Yes| D{Liveness succeeds?}
    D -->|No, threshold exceeded| E[Restart container]
    D -->|Yes| F{Readiness succeeds?}
    F -->|Yes| G[Pod can receive Service traffic]
    F -->|No| H[Pod NotReady, stays running and re-probed]
    C --> B
    H --> F
~~~

The operational difference is huge: a failed liveness probe can wipe in-memory process state and trigger consumer group rebalancing; a failed readiness probe mainly affects Kubernetes Service traffic routing. Choose checks based on the action that should happen when they fail.

## 3. Why Not Put the Broker Directly in Liveness?

Suppose a Kafka cluster stops responding for three minutes. All ten Spring Cloud Stream instances use the Kafka Binder and their liveness endpoint checks the broker. The probes fail one by one, and Kubernetes restarts every instance.

Consequences may include:

1. Every instance loses in-memory state and closes connections.
2. Consumer groups rebalance repeatedly as Pods restart.
3. Unacknowledged messages may be redelivered.
4. Pods simultaneously try to connect or declare topics before the broker recovers.
5. When the broker comes back online, multiple Pods create a reconnect storm at once.
6. Downstream services receive duplicates or suffer increased recovery latency.

Restarting the application does not fix a broken broker. Spring Boot officially recommends that **liveness should not depend on external services**, because doing so can trigger cascading failures when a shared dependency across all instances goes down.

Liveness is suited for hard-to-self-recover symptoms such as an unresponsive process, severely corrupted application state, or an internal error leaving workers unable to progress after recovery attempts. You should not put Kafka metadata checks, Rabbit connection checks, Pulsar broker queries, or database queries into every liveness call.

If the JVM is alive while a stream thread dies and cannot self-recover, define a clear handling policy: replace the thread, shut down the process in a controlled manner, or signal liveness failure. That decision must rest on a verified unrecoverable state rather than a transient network glitch.

## 4. Must Readiness Always Depend on the Broker?

No. It depends on the type of traffic the application receives.

**Case A: HTTP API receiving requests and then publishing messages.** If the API only returns success after durably writing to Kafka, losing the broker can prevent the API from fulfilling its contract. Readiness may need to reflect publish capability or outbox health. If the API persists requests into a durable transactional outbox, it can continue accepting traffic even if the broker pauses temporarily.

**Case B: Consumer receiving messages directly from Kafka/RabbitMQ/Pulsar.** The Pod might not have a Kubernetes Service, or the Service is only for metrics. Readiness failure does **not** automatically stop the binder's consumer: the broker can still connect and deliver messages because it does not distribute via Kubernetes Service endpoints. In this case, readiness reflects HTTP/Pod status, while consumption capability should be observed through binder state, lag, subscriptions, and metrics.

**Case C: Bridge application both receiving HTTP and consuming from a broker.** HTTP readiness may need to remain independent of consumer health. Marking the entire Pod NotReady just because a non-essential broker fails can disrupt HTTP features that are still healthy.

Readiness is not a pause switch for Kafka, RabbitMQ, or Pulsar consumers. If you genuinely need to stop receiving messages, use the binding lifecycle API, container configuration, or appropriate broker management mechanisms.

## 5. Spring Boot ApplicationAvailability

Spring Boot publishes application availability state via **ApplicationAvailability**. Two state groups matter:

| Group | State | Meaning |
|---|---|---|
| LivenessState | CORRECT | The application is considered operating normally |
| LivenessState | BROKEN | The application is broken to a degree requiring intervention |
| ReadinessState | ACCEPTING_TRAFFIC | Ready to serve traffic according to contract |
| ReadinessState | REFUSING_TRAFFIC | Not yet ready / should not accept new traffic |

During startup, the application is typically in a state refusing traffic. Once initialization finishes, Spring Boot emits an event transitioning readiness to `ACCEPTING_TRAFFIC`. During shutdown, readiness transitions to `REFUSING_TRAFFIC`.

Spring Boot Actuator provides:

~~~text
GET /actuator/health
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

The liveness and readiness endpoints are **health groups**. They use **LivenessStateHealthIndicator** and **ReadinessStateHealthIndicator**, rather than checking every application dependency by default.

In a Kubernetes environment, Spring Boot can auto-detect and enable probe support. To enable it explicitly, use **management.endpoint.health.probes.enabled=true**. Do not assume the endpoints exist if the application lacks Actuator or a web stack to serve HTTP.

## 6. Enabling Actuator and Endpoints for Deployment

The application needs the Actuator dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

If the application is purely a background consumer without an HTTP server, add a web starter matching your Spring Boot line (Spring MVC or WebFlux) if you want Kubernetes to invoke HTTP probes. Exec probes can be used instead, though HTTP health groups are usually simpler to standardize operationally.

Baseline configuration:

~~~yaml
server:
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      group:
        readiness:
          include: "readinessState"
      show-details: when-authorized
~~~

When **add-additional-paths=true** is enabled, Spring Boot additionally exposes:

~~~text
GET /livez
GET /readyz
~~~

on the **main application server port**. This configuration is useful when Actuator runs on a separate management port: probing only the management port might succeed while the main server cannot accept connections.

If additional paths are unnecessary, you can use **/actuator/health/liveness** and **/actuator/health/readiness** directly on the Actuator port. Make sure the actual path, port, and context path match the Pod specification.

The **show-details: when-authorized** property avoids exposing full health metadata to unauthorized callers. Probes need HTTP status codes, not payloads containing topics, brokers, credentials, or internal details.

## 7. Kubernetes Deployment Example with Three Probes

Here is an example for an application with main HTTP port 8080 and Spring Boot configured with `/livez` and `/readyz`:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-stream
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-stream
  template:
    metadata:
      labels:
        app: order-stream
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: app
          image: registry.example/order-stream:1.0.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 60
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
            successThreshold: 2
~~~

These are illustrative values, not universal thresholds for all workloads:

- The startup probe allows up to roughly 300 seconds for startup (60 × 5 seconds). Measure actual startup and Kafka Streams state-store restoration times.
- Liveness tolerates up to three consecutive failed checks, avoiding restarts over a single random HTTP timeout.
- Readiness uses two consecutive successes to reduce Ready/NotReady flapping while recovering.
- Termination grace period must accommodate in-flight HTTP requests and message handlers, without extending indefinitely.

**A startup probe does not replace readiness.** Startup protects initialization; readiness governs traffic throughout runtime. **Readiness does not replace liveness** because Kubernetes will not restart a Pod merely because readiness fails.

## 8. HTTP Statuses and Response Payloads

Spring Boot Actuator maps standard Health statuses to HTTP statuses:

| Actuator status | Default HTTP status | Meaning for HTTP probes |
|---|---|---|
| UP | 200 | Probe succeeds |
| DOWN | 503 | Probe fails |
| OUT_OF_SERVICE | 503 | Probe fails |
| UNKNOWN | 200 unless custom mapping configured | Should not treat UNKNOWN as proof of broker health |

Example when `readinessState` is `REFUSING_TRAFFIC`:

~~~json
{
  "status": "OUT_OF_SERVICE"
}
~~~

The readiness HTTP probe receives 503 and the Pod becomes NotReady after exceeding `failureThreshold`. When readiness returns to `ACCEPTING_TRAFFIC`, the health group typically reports UP/200 if no other health indicator in the group fails.

Do not parse JSON string contents to decide restarts manually when kubelet already relies on HTTP status codes. If you add custom Health statuses or HTTP mappings, preserve mappings for `DOWN` and `OUT_OF_SERVICE` to avoid unintentionally turning errors into HTTP 200.

## 9. Spring Cloud Stream Binder Health Indicator

Spring Cloud Stream registers a health contributor for binders under the name **binders**. It can be enabled/disabled via **management.health.binders.enabled**; if omitted, behavior depends on health defaults and framework version.

Example configuration to observe binder health via Actuator:

~~~yaml
management:
  health:
    binders:
      enabled: true
  endpoint:
    health:
      show-details: when-authorized
~~~

With proper authorization, **/actuator/health** can return binder status and details. Do not assume that Health status UP means all messages are processed; binder health generally checks connection/metadata or thread states, not business side effects.

Some binders have dedicated health indicators; not every implementation provides the same level of detail. With multiple binders, the composite contributor may report DOWN when one binder fails even while other bindings keep working. Before adding `binders` to readiness, understand which binders the application uses and whether each binder's status is truly essential for incoming traffic.

### Do Not Confuse Global Health with Readiness

Three endpoints can report different statuses at the same time:

~~~text
/actuator/health            -> DOWN (one binder lost connection)
/actuator/health/liveness   -> UP
/actuator/health/readiness  -> UP (if only readinessState is included)
~~~

This can be the intended behavior: the process is still alive, consumers are reconnecting automatically, while the binder has flagged a lost broker connection. If business rules require refusing HTTP traffic when a binder is down, explicitly add the health indicator to the readiness group.

## 10. Kafka Binder Health Indicator

The Kafka Binder checks broker/topic metadata health. Useful properties:

| Property | Effect |
|---|---|
| spring.cloud.stream.kafka.binder.healthTimeout | Maximum wait time to fetch partition info; expiration can report DOWN |
| spring.cloud.stream.kafka.binder.considerDownWhenAnyPartitionHasNoLeader | Treats the binder as DOWN if any partition of relevant topics lacks a leader |
| spring.cloud.stream.kafka.binder.healthIndicatorConsumerGroup | Group ID of the metadata consumer used by the health indicator in supported versions |

Example:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          healthTimeout: 15
          considerDownWhenAnyPartitionHasNoLeader: true

management:
  health:
    binders:
      enabled: true
~~~

**`healthTimeout` is in seconds**, not milliseconds. The 15-second example illustrates a metadata timeout; too large a value can make the HTTP health check slower than Kubernetes probe `timeoutSeconds`. Too small a value can cause false negatives during Kafka leader elections or transient network fluctuations.

The **considerDownWhenAnyPartitionHasNoLeader** property evaluates partition leader availability on topics; it is not a measure of consumer lag or processing latency. A consumer may stay connected to the broker while lag climbs because downstream is slow. Conversely, a brief leader change can temporarily turn health DOWN while the client self-recovers.

Do not turn every Kafka metadata error into a liveness failure. Monitor metadata/leader state alongside request timeouts, consumer lag, commit failures, and retry exhaustion.

## 11. Kafka Streams Binder and Stream Thread States

The Kafka Streams Binder provides a health indicator covering stream threads and tasks. Details can include thread names, thread states, active tasks, standby tasks, and application IDs when multiple topologies exist.

Commonly observed states:

- CREATED: Thread newly created.
- RUNNING: Thread is actively running.
- PARTITIONS_REVOKED and PARTITIONS_ASSIGNED: Partition/task reassignment in progress.
- PENDING_SHUTDOWN: Thread is shutting down.
- DEAD: Thread has stopped.

Kafka Streams Binder documentation notes that the indicator reports UP when registered threads are in the RUNNING state. During startup or rebalancing, threads temporarily pass through other states. Therefore, putting this status directly into readiness can make Pods flap NotReady/Ready during rebalancing; putting it into liveness can cause Kubernetes to restart Pods right when Kafka Streams is redistributing tasks.

Kafka Streams also performs **state restoration**: when a new Pod receives tasks, it may need to restore state stores from changelogs before normal processing. Startup/readiness timeouts should be chosen based on real state-store recovery times. Never set liveness `failureThreshold` too low and trigger continuous restarts before state restoration completes.

For stateful topologies, also monitor restore duration, changelog lag, task rebalance counts, processing errors, commit latency, and throughput. RUNNING threads are necessary but insufficient to prove aggregation results are correct.

## 12. RabbitMQ Binder Health Indicator

The RabbitMQ Binder uses the health indicator supported by Spring Boot via Spring AMQP. There are two common configuration scopes:

~~~yaml
management:
  health:
    binders:
      enabled: true
    rabbit:
      enabled: true
~~~

- **management.health.binders.enabled** controls the health indicator at the binder layer.
- **management.health.rabbit.enabled** controls Spring Boot's Rabbit health indicator.
- In a multi-binder environment, a binder has its own application context and requires the corresponding property if you want to disable that binder's indicator independently.

Rabbit health may report DOWN when unable to connect to or check the broker. However, an active Rabbit connection does not prove producers route to the right queue or consumers acknowledge data. Routing keys, queue bindings, ACLs, DLQs, and publisher confirms require separate telemetry or tests.

When RabbitMQ restarts, listener containers and connection factories typically have reconnection mechanisms. Unacknowledged deliveries may be requeued. Restarting Pods due to broker-coupled liveness increases redelivery risk and creates unnecessary recovery pressure.

If RabbitMQ is the sole input for a background consumer, Kubernetes Service readiness generally does not stop the broker from delivering messages. Measure consumer count, ready/unacked messages, redelivery rate, queue depth, and DLQ depth to assess the processing path.

## 13. Pulsar Binder and Client/Subscription Health

The Pulsar Binder builds on Spring for Apache Pulsar and uses framework-managed producer/consumer clients. Specific health indicator capabilities depend on the selected Spring Boot, Spring Pulsar, and binder versions. Do not assume a contributor named **pulsar** always exists or provides identical semantics to the Kafka Binder.

Key signals for Pulsar:

- The client can connect to the broker via the configured service URL.
- Producers publish and receive acknowledgments successfully.
- Consumer subscriptions are created and receive messages.
- Unacked messages, redelivery counts, and subscription backlog.
- Subscription types such as Shared, Failover, or Key_Shared and takeover behavior.
- Retry-letter topics and dead-letter topics if used by the application.
- Reconnect durations and authentication/TLS failures.

If Pulsar health checks are needed, verify which contributors actually exist at runtime via Actuator, then define readiness policies aligned with application capabilities. For message-only streams, subscription/backlog metrics and automatic reconnection are usually more useful than a broker-dependent liveness check.

## 14. Configuring Readiness Based on Actual Dependencies

By default, Spring Boot does not include every external health indicator in readiness. You can explicitly extend the readiness group:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: "readinessState,binders"
~~~

This configuration is **only appropriate when every binder in the contributor is a mandatory dependency for traffic the Pod accepts**. If a single optional binder fails, the entire Pod may be dropped from the Service even though it can still serve other functions.

In many applications, keep the default readiness containing only `readinessState` and create separate dashboards/alerts for `binders`. If HTTP API readiness must reflect broker availability, add a dedicated indicator with a short timeout, cached results, or asynchronous updates. Never let every HTTP probe synchronously query broker metadata with a long timeout, as the health endpoint itself can become congested.

A simple example of a custom indicator that does not perform network I/O on every kubelet poll:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.boot.health.contributor.Health;
import org.springframework.boot.health.contributor.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("bridgeOutputReady")
public class BridgeOutputReadyHealthIndicator implements HealthIndicator {

    private final AtomicBoolean canAccept = new AtomicBoolean(false);

    public void markUnavailable() {
        canAccept.set(false);
    }

    public void markRecovered() {
        canAccept.set(true);
    }

    @Override
    public Health health() {
        return canAccept.get()
            ? Health.up().build()
            : Health.outOfService().build();
    }
}
~~~

This is an illustrative indicator and **does not monitor the broker automatically**. Initially it returns `OUT_OF_SERVICE`; the application must call `markRecovered` after confirming the write path is genuinely ready and `markUnavailable` when that capability is lost. Calls should come from components observing publish/connection state or a tested state machine. A successful TCP connect does not guarantee publishing works.

The `Health`/`HealthIndicator` imports follow **Spring Boot 4.x**. For **Spring Boot 3.x**, these two classes belong to package `org.springframework.boot.actuate.health`. Choose the exact imports matching your project's actual dependencies.

Enable it for HTTP readiness if bridge output capability is mandatory:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: "readinessState,bridgeOutputReady"
~~~

Do not put `bridgeOutputReady` into liveness. Do not trigger this mechanism on every transient retry failure in a consumer, since the consumer can retry on its own while the Pod needs to retain state and keep processing.

## 15. Updating ReadinessState via Application Events

Spring Boot supports **AvailabilityChangeEvent** to update readiness according to business state. Example:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class TrafficReadinessControl {

    private final ApplicationEventPublisher publisher;

    public TrafficReadinessControl(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void refuseNewTraffic() {
        AvailabilityChangeEvent.publish(
            publisher,
            this,
            ReadinessState.REFUSING_TRAFFIC
        );
    }

    public void acceptNewTraffic() {
        AvailabilityChangeEvent.publish(
            publisher,
            this,
            ReadinessState.ACCEPTING_TRAFFIC
        );
    }
}
~~~

This class only emits events; state transitions when the service calls these methods at meaningful milestones. For instance, an internal API gateway might refuse new traffic while a critical data source is recovering. Avoid calling `refuseNewTraffic` on every transient exception.

`ReadinessState` affects Actuator's readiness group. It does not automatically pause bindings or stop consumer threads. If the application needs to stop consuming, control the binding/container through a dedicated mechanism.

## 16. Binding Lifecycle and Readiness Are Different Concerns

Spring Cloud Stream provides **BindingsLifecycleController** to manage binding lifecycles. Example of a control component invoked by operational workflows:

~~~java
import org.springframework.cloud.stream.binding.BindingsLifecycleController;
import org.springframework.stereotype.Component;

@Component
public class OrderInputLifecycle {
    private final BindingsLifecycleController controller;

    public OrderInputLifecycle(BindingsLifecycleController controller) {
        this.controller = controller;
    }

    public void stopInput() {
        controller.stop("processOrder-in-0");
    }

    public void startInput() {
        controller.start("processOrder-in-0");
    }
}
~~~

Actuator also supports the `bindings` endpoint when enabled and authorized. `STARTED`/`STOPPED` actions control lifecycle. `PAUSED`/`RESUMED` only work on binders/transports that support them; Spring Cloud Stream documentation explicitly notes not all binders support pause/resume.

**Do not use readiness failures as a mechanism to stop consumers.** If a Pod continues processing Kafka consumer messages even while NotReady, that is valid behavior: Kubernetes keeps the Pod running and Kafka continues distributing records within the consumer group.

Be careful when stopping bindings in production: in-flight messages may be redelivered, partition assignments may shift, and downstream producers/consumers may observe duplicates. Design for idempotency and test lifecycle actions in staging.

## 17. Broker Disconnection: What Actually Happens?

| Scenario | Liveness | Recommended Readiness | What to Monitor |
|---|---|---|---|
| Kafka broker temporarily down, consumer can reconnect | Keep UP | Depends on HTTP role; worker-only apps usually omit broker from readiness | Lag, reconnects, failed poll/commit |
| RabbitMQ restarts, unacked messages requeued | Keep UP | Depends on ability to accept new requests | Redeliveries, unacked count, DLQ |
| Pulsar broker disconnected, client reconnecting | Keep UP | Depends on publish capability or outbox persistence | Subscription backlog, errors, retries |
| Kafka Streams tasks rebalancing/restoring | Usually keep UP | May be unready for features serving state queries | Thread/task state, restore duration |
| Unrecoverable application deadlock | DOWN if internal state verified | DOWN | Thread dumps, request timeouts, restart count |
| Extended broker outage, API has durable outbox | UP | Can stay UP if outbox persists and meets request contract | Outbox pending, publish retries |
| Extended broker outage, API requires synchronous publish | UP | Can go DOWN | Publish failures, client timeouts |

When the broker recovers, accumulated backlog may cause consumer lag to spike and then gradually drain. Keeping liveness UP does not mean skipping alerts. Alerts should reflect stream health, latency, and retry counts—not merely Pod Ready status.

When designing recovery, account for client limits such as connection backoff, Kafka poll interval, listener concurrency, Rabbit prefetch, Pulsar subscription types, and DLQs. Restarting all Pods can create duplicates and prolong recovery time.

## 18. Graceful Shutdown During Deployments or Scale-Down

During a rollout of a new version or scale-down, Kubernetes sends a termination signal per the container lifecycle. Spring Boot provides graceful shutdown for the web server: it stops accepting new requests and waits for active requests to finish within the configured timeout. Binders are `SmartLifecycle` components and execute their own stop sequence when the application context closes.

Configuration example:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 45s
~~~

Pair this with **terminationGracePeriodSeconds: 60** on the Pod to give the application time to exit cleanly. Actual values must be measured against batch sizes, handler execution times, and orchestrator constraints.

For message consumers, verify:

1. When the consumer stops accepting new deliveries.
2. Whether in-flight messages complete or get aborted.
3. Whether Kafka offsets or Rabbit/Pulsar acknowledgments are committed.
4. Whether unacknowledged messages are redelivered after the instance stops.
5. Whether idempotency prevents duplicate side effects on redelivery.
6. Whether producers flush outputs or await publisher confirms before exit.

Do not rely on graceful shutdown to achieve exactly-once across Kafka/RabbitMQ/Pulsar and a database. When a process is killed abruptly, messages can be redelivered. Idempotent design and the outbox pattern remain essential whenever side effects are critical.

## 19. Health of Multiple Binders and Unused Binders

In a multi-binder application, a single instance might use the Kafka Binder for input and the Rabbit Binder for output. The **binders** contributor may aggregate the health of both. If Rabbit goes down temporarily, global `/actuator/health` may report DOWN even while the Kafka consumer keeps receiving data. Interpret this according to business boundaries.

Another pitfall: an application may have a binder implementation on its classpath without creating any bindings for it. Spring Cloud Stream documentation warns that an unused binder may report DOWN because no destinations are registered for it. Global health is then impacted even though active bindings are healthy.

Remediation:

- Keep only the binder dependencies actually used on the classpath.
- Verify initialized aliases/named binders.
- Use health indicators appropriate for each binder.
- If implementing custom health checks, place them into the proper functional health group.
- Never disable all binder checks just to hide a real configuration mistake.

If you need to disable health for one binder in a multi-binder environment, set **management.health.binders.enabled=false** inside that binder's environment. Distinguish disabling an indicator from stopping connections or fixing broker errors.

## 20. When to Choose Custom Health Instead of Default Binders?

Binder health alone may not accurately reflect the end-to-end contract. For example:

- Kafka metadata is healthy, yet a consumer handler throws exceptions on every message.
- RabbitMQ connection is UP, yet the exchange routes to no queue.
- Pulsar client connects, yet the subscription receives no messages due to ACLs or schema mismatches.
- Kafka Streams threads are RUNNING, yet a stateful window has massive lag.
- An HTTP request receives 202 because the outbox persisted successfully even though the broker cannot publish yet.

In these scenarios, a business-aligned indicator or metric is more meaningful. Custom readiness should answer a concrete question: "Can this instance accept and process new requests according to its published contract?" It should not turn into a mirror of a broker monitoring dashboard.

If readiness must perform network checks, keep timeouts small, polling frequency reasonable, cache results, and limit new connections. Avoid heavy checks on every kubelet poll.

## 21. Monitoring Beyond Kubernetes Probes

Probes are tools for managing Pod lifecycles and traffic routing. They cannot replace an observability system.

| Signal | Operational Value |
|---|---|
| Kubernetes restarts / CrashLoopBackOff | Detects misconfigured liveness or startup failures |
| Pod Ready ratio | Detects instances removed from Services |
| Broker connect/reconnect attempts | Detects connection drops and recovery |
| Kafka consumer lag / partition assignment | Measures ability to keep up with incoming data |
| Kafka Streams task/thread state, restore duration | Measures stateful topology progress |
| Rabbit ready/unacked/redelivery/DLQ depth | Tracks backlog and duplicates |
| Pulsar subscription backlog/unacked/redelivery | Tracks consumer subscriptions |
| Producer send failures, confirm latency | Measures outbound publishing capability |
| Retry count, retry exhaustion, DLT count | Detects poison messages |
| Handler latency / throughput | Detects business logic bottlenecks |
| Outbox pending age | Detects bridge delays in dispatching events |

A broker incident usually shows up across multiple signals simultaneously: connect failures rise, lag or queue depth climbs, and DLTs may grow, while liveness stays UP. This is the exact goal of separating health concerns: alert on infrastructure issues without triggering a restart storm.

Use metrics and alerts to decide when human intervention or operational automation is needed, rather than turning every high-lag threshold into liveness DOWN.

## 22. Practical Pre-Deployment Testing

Use Testcontainers, a staging environment with real brokers, or controlled chaos testing to verify these behaviors:

1. Start while the broker is ready: liveness/readiness come UP in the right order.
2. Start while the broker is temporarily unavailable: verify whether binder provisioning fails fast or retries; do not assume startup probes fix unrecoverable startup errors.
3. Stop Kafka while a consumer is running: confirm liveness does not go DOWN solely due to the broker, and the consumer reconnects once the broker returns.
4. Stop RabbitMQ while unacked deliveries exist: verify redelivery/idempotency.
5. Disconnect and restore the Pulsar broker: verify subscriptions, reconnection, and redelivery.
6. Induce a long Kafka Streams rebalance/state restore: startup/readiness must not cause mistaken Pod restarts.
7. Verify `/actuator/health`, `/livez`, and `/readyz` return HTTP statuses as configured.
8. If readiness depends on binders, test both broker failure and recovery; evaluate the impact across all Pods.
9. Verify background consumers can still receive messages while the Pod is NotReady if bindings are not stopped.
10. Simulate graceful shutdown and hard kill: verify acks/offsets, message redelivery, and idempotency.
11. Simulate an unused binder on the classpath: check whether global health falsely reports DOWN.
12. Verify health indicator network timeouts do not exceed kubelet `timeoutSeconds`.
13. Ensure Actuator does not expose sensitive information via health details or the `bindings` endpoint.

A test that only asserts `GET /readyz` returns 200 does not prove the application consumes messages successfully. Send real messages, verify side effects, commit/ack state, and advancing metrics.

## 23. Common Symptoms

| Symptom | Common Cause | Resolution Approach |
|---|---|---|
| Broker outage triggers mass Pod restarts | Liveness includes binder/external health | Remove external dependencies from liveness |
| `/actuator/health` DOWN while `/readyz` UP | Readiness group only includes `readinessState` | May be intentional design; check against workload contract |
| Pod NotReady yet Kafka still processes messages | Readiness does not control consumer groups | Use binding lifecycle if you truly need to stop consuming |
| Probe timeouts while app is still working | Binder health query waits too long on broker | Check `healthTimeout`, `timeoutSeconds`, and add caching |
| Stateful processor keeps restarting during rebalance | Liveness tied directly to Kafka Streams thread status | Allow restore/rebalance time; use dedicated metrics |
| Consumer receives no messages after Ready | Binding not created, ACL error, bad schema, or handler failing | Check binding state, error logs, and broker metrics |
| Missing `/livez` or `/readyz` | Probes/additional paths not enabled or no web server | Check Actuator, paths, and main server port |
| Kafka Binder reports DOWN while Kafka Streams runs | Unused Kafka binder dependency on classpath | Remove unused binder or check health configuration |
| One broker fault removes all Service endpoints | Readiness bundles all binders | Identify dependencies truly required for HTTP traffic |
| Broker recovers yet lag keeps growing | Consumer cannot keep up or handler retries endlessly | Investigate throughput, partitions, DLQ, and downstream |
| Shutdown processes a message twice | Ack/commit not recorded before Pod stopped | Ensure idempotency and test shutdown windows |

## 24. Production Checklist

- [ ] Liveness checks only internal states difficult to self-recover.
- [ ] Readiness reflects the traffic-handling contract, not merely whether the broker answers ping.
- [ ] For message-only workers, understand that Pod NotReady does not automatically pause consumers.
- [ ] Startup probe allows enough time for Spring Boot and Kafka Streams state restoration.
- [ ] Actuator, web stack, and exact paths/ports are configured for HTTP probes.
- [ ] If management port differs from main port, consider `/livez` and `/readyz` on the main server port.
- [ ] Do not place all external dependencies into liveness.
- [ ] Verify binder health behavior individually for Kafka, RabbitMQ, and Pulsar for your exact version.
- [ ] Do not include non-essential binders in readiness for all endpoints.
- [ ] Health indicators do not cause network storms or block too long.
- [ ] Graceful shutdown timeout is compatible with `terminationGracePeriodSeconds`.
- [ ] Idempotency exists for broker redeliveries or Pod restarts.
- [ ] Monitor consumer lag, queue depth, subscription backlog, retries, and DLQ.
- [ ] Test broker disconnect/reconnect, restarts, rebalancing, and state restoration.
- [ ] Secure Actuator endpoints and restrict health detail visibility.

## 25. References

- [Spring Boot — Actuator Endpoints and Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html), `ApplicationAvailability`, liveness/readiness health groups, additional paths, and external system check principles.
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/), impact of each probe on containers and Service endpoints.
- [Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/), startup timeouts, `failureThreshold`, `successThreshold`, and HTTP probes.
- [Spring Cloud Stream — Health Indicator](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/health-indicator.html), `binders` health contributor, multiple binders, and implementation differences.
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html), `healthTimeout`, metadata, and partition leaders.
- [Spring Cloud Stream — Kafka Streams Binder Health Indicator](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-streams-binder/health-indicator.html), RUNNING thread state, task metadata, and application ID.
- [Spring Cloud Stream — Rabbit Binder Health Indicator](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/health-indicator.html), Spring Boot Rabbit health and `management.health.binders.enabled`.
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html), Pulsar client, consumer/producer, and subscriptions.
- [Spring Cloud Stream — Binding Visualization and Control](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding_visualization_control.html), managing binding lifecycles via controller and Actuator.
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html), HTTP and lifecycle termination windows on application shutdown.

Liveness, readiness, and binder health answer three different questions. A temporary broker disconnection should generally be handled with reconnection, retries, and lag monitoring rather than restarting every Pod. Readiness should only reflect the ability to accept traffic per contract; Kubernetes NotReady does not automatically stop consumers receiving messages from a broker. By combining Actuator health groups, sensible probe timeouts, graceful shutdown, and real broker fault testing, Spring Cloud Stream applications can recover gracefully without causing cascading failures when messaging infrastructure runs into trouble.
