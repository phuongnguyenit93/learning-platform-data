# Separating Readiness and Liveness

A Spring Boot application can keep running inside the JVM while no longer able to serve new requests. Conversely, an application can temporarily lose connectivity to Kafka or a database while the process remains healthy and capable of self-recovery. Relying on a single generic health check for every decision makes the system react wrongly: repeatedly restarting when an external dependency fails, or continuing to route traffic to an instance that genuinely cannot serve.

**Readiness** and **liveness** answer two distinct questions:

- **Readiness:** is the instance ready to accept new traffic or work under the service contract?
- **Liveness:** is the process alive and able to continue operating, or must it be restarted to recover?

In Spring Boot, these two states are represented by `ApplicationAvailability`, `ReadinessState`, and `LivenessState`, and can be exposed via Actuator health groups for Kubernetes. With Spring Kafka, one more crucial detail applies: **a Kubernetes readiness probe does not automatically control the Kafka consumer group**. If a worker needs to suspend consumption when a dependency is unready, the application must have its own dedicated mechanism to pause or stop the listener container.

## 1. Why must the two states be separated?

Suppose an order-processing service uses Spring Kafka:

~~~text
Kubernetes
   |
   +---- liveness probe
   |         |
   |         v
   |    Is JVM / process still running?
   |
   +---- readiness probe
             |
             v
       Can service accept new work?
             |
             v
       Spring Kafka listener
             |
       +-----+------+
       |            |
       v            v
   PostgreSQL     Kafka
~~~

There are two scenarios:

**Scenario A — process is deadlocked.** The JVM still exists, yet critical threads make no progress. The instance cannot recover by waiting on a dependency; it needs a restart. This is a **liveness** issue.

**Scenario B — Kafka broker is temporarily unavailable.** The JVM can still serve other HTTP endpoints, manage resources, and reconnect once the broker recovers. If liveness depends directly on Kafka, Kubernetes may restart all Pods even though the cause is outside the application. This is typically a **dependency health/readiness** issue, not automatically a liveness failure.

| State | Question | Typical Orchestration Action |
|---|---|---|
| Readiness `UP` | Can the instance accept new work? | Kept in traffic-serving endpoints |
| Readiness `DOWN` | Should the instance temporarily stop receiving new work? | Removed from Service endpoints |
| Liveness `UP` | Is the process still operating? | No probe-triggered restart |
| Liveness `DOWN` | Can the process no longer continue? | Kubernetes may restart the container after the failure threshold |
| Startup incomplete | Is the application still starting up? | Startup probe defers readiness/liveness probes |

Readiness and liveness are not two names for the same ping. Each state must align with a **clear operational contract**.

## 2. Readiness: ability to accept new traffic or work

Readiness answers whether the instance qualifies to accept new work at the time of the check.

An HTTP service can be unready when:

- Required cache or configuration initialization is incomplete.
- Graceful shutdown is in progress.
- A dependency mandatory for all endpoints is unavailable.
- The application is intentionally refusing traffic during maintenance.
- An internal state prevents the instance from fulfilling its service contract.

A Spring Kafka worker may need a different readiness policy:

- A mandatory listener has not started yet.
- A dependency required to process all records is unready.
- The consumer is in an intentional stopped state.
- The worker is draining or performing an orderly shutdown.

However, **readiness does not mean the consumer has been assigned Kafka partitions**. A consumer can start without holding assignments yet, or hold no partitions because consumers outnumber partitions in the group. If the business contract requires assignments, that is a separate condition to track.

Readiness should reflect serving capability for the functions the service provides, not merely the existence of beans in the Spring context.

## 3. Liveness: ability of the process to keep operating

Liveness focuses on internal process health. The question is: if the instance stays running, can it self-recover and make progress?

Cases that may warrant a liveness failure:

- Internal deadlock or unrecoverable blockage of a critical thread pool.
- A severe error preventing the application from continuing properly.
- An internal state that cannot be fixed by retries or reconnects.
- The application detects a broken internal invariant and operational policy requires a restart.

These situations are **not automatically liveness failures**:

- Kafka brokers undergoing maintenance or temporarily disconnected.
- PostgreSQL temporarily refusing connections.
- A downstream HTTP service timing out.
- Consumer group rebalancing.
- A topic having no new records.
- A partition sitting idle.
- Rising consumer lag while the process keeps polling and processing.
- Temporary DLT publish failures.

When an external dependency is unavailable, restarting the JVM rarely fixes the dependency. It discards caches, causes connection churn, triggers consumer group rebalances, and adds load to an already troubled system.

## 4. Spring Boot ApplicationAvailability

Spring Boot provides `ApplicationAvailability` to query the two primary states:

- `LivenessState`: `CORRECT` or `BROKEN`.
- `ReadinessState`: `ACCEPTING_TRAFFIC` or `REFUSING_TRAFFIC`.

Example:

~~~java
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.LivenessState;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.stereotype.Component;

@Component
public class AvailabilityReporter {

    private final ApplicationAvailability availability;

    public AvailabilityReporter(ApplicationAvailability availability) {
        this.availability = availability;
    }

    public void report() {
        LivenessState liveness = availability.getLivenessState();
        ReadinessState readiness = availability.getReadinessState();

        // Send state to logs/diagnostics as needed.
    }
}
~~~

`ApplicationAvailability` is the state source inside the Spring `ApplicationContext`. It does not probe Kafka or databases on every call. State changes via application availability events, typically published by Spring Boot during lifecycle or by the application under its own policy.

| Enum | Meaning |
|---|---|
| `LivenessState.CORRECT` | The application is considered capable of operating |
| `LivenessState.BROKEN` | The application cannot continue operating per internal assessment |
| `ReadinessState.ACCEPTING_TRAFFIC` | Ready to accept traffic/work |
| `ReadinessState.REFUSING_TRAFFIC` | Temporarily refusing new traffic/work |

## 5. Changing readiness and liveness with AvailabilityChangeEvent

Spring Boot allows applications to publish `AvailabilityChangeEvent` to transition states.

Example of a service beginning orderly shutdown and refusing new traffic:

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.stereotype.Component;

@Component
public class MaintenanceCoordinator {

    private final ApplicationContext context;

    public MaintenanceCoordinator(ApplicationContext context) {
        this.context = context;
    }

    public void stopAcceptingNewWork() {
        AvailabilityChangeEvent.publish(
                context,
                ReadinessState.REFUSING_TRAFFIC);
    }

    public void resumeAcceptingWork() {
        AvailabilityChangeEvent.publish(
                context,
                ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

When the application publishes the event, Spring Boot updates the readiness state read by the corresponding health indicator. Other components can also listen for availability events to coordinate actions.

Liveness can be transitioned similarly:

~~~java
AvailabilityChangeEvent.publish(context, LivenessState.BROKEN);
~~~

and when a state can recover under application policy:

~~~java
AvailabilityChangeEvent.publish(context, LivenessState.CORRECT);
~~~

**Be careful with `BROKEN`:** when the liveness probe reflects this state, Kubernetes may restart the container. Do not use it as a generic alert for Kafka outages or database timeouts.

Publishing `REFUSING_TRAFFIC` also does not automatically stop Kafka consumers. It updates Spring Boot's availability state; listener containers must be controlled separately if the service is a consume-only worker.

## 6. Actuator health groups for liveness and readiness

Spring Boot Actuator can expose two health groups:

- `/actuator/health/liveness`
- `/actuator/health/readiness`

Basic configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState
~~~

`livenessState` and `readinessState` are health contributors bound to `ApplicationAvailability`.

Illustrative response:

~~~json
{
  "status": "UP"
}
~~~

When the application transitions to `REFUSING_TRAFFIC`, the readiness group can return an unhealthy status (typically `OUT_OF_SERVICE` under default health mapping). Liveness can remain `UP`.

Exact HTTP status codes depend on health status mapping and endpoint configuration. In Kubernetes, probes primarily evaluate HTTP success/failure from the response code; therefore check the actual HTTP response code rather than looking only at the JSON status string.

### 6.1. Including dependencies in the readiness group

If a service cannot perform its primary function when its database is unavailable, database health can be included in readiness:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db
~~~

Similarly, `kafka` can be added if Kafka connectivity is required for the instance to accept new work under its service contract.

Do not put every dependency into readiness by default. If a dependency only serves an auxiliary endpoint, that dependency failing does not necessarily mean the entire instance must be pulled from traffic.

### 6.2. Separating health groups by capability

For services with multiple functions, expose distinct views:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db
        kafkaConnectivity:
          include: kafka
~~~

`kafkaConnectivity` lets operators inspect Admin connectivity status without forcing the entire service's readiness to depend on Kafka. Group names are examples; verify that actual contributor IDs match your configuration.

Health groups are a way to classify observation results. They do not automatically control listener lifecycles or Kafka consumer groups.

## 7. How does Kubernetes handle startup, readiness, and liveness?

Kubernetes provides three commonly used probe types:

| Probe | Goal | On Failure |
|---|---|---|
| `startupProbe` | Has the application finished its startup phase? | Container is treated as not yet started; other probes are deferred |
| `readinessProbe` | Should the container receive Service traffic? | Pod is marked NotReady and removed from matching endpoints |
| `livenessProbe` | Does the container need a restart to recover? | After the configured failure threshold, kubelet restarts the container |

~~~text
Container starts
      |
      v
Startup probe succeeds?
      |
      +---- No -> keep waiting / restart if threshold exceeded
      |
      v
Startup complete
      |
      +---- Readiness probe -> accept traffic or not
      |
      +---- Liveness probe  -> keep process or restart
~~~

`startupProbe` is useful for slow-starting applications, such as those loading configuration, warming caches, or initializing many Spring beans. Until the startup probe succeeds, Kubernetes does not apply readiness/liveness in the normal way.

### 7.1. Configuring probes in a Deployment

Example:

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: payment-worker
      image: example/payment-worker:latest
      ports:
        - name: http
          containerPort: 8080

      startupProbe:
        httpGet:
          path: /actuator/health/liveness
          port: http
        periodSeconds: 5
        timeoutSeconds: 2
        failureThreshold: 30

      livenessProbe:
        httpGet:
          path: /actuator/health/liveness
          port: http
        periodSeconds: 10
        timeoutSeconds: 2
        failureThreshold: 3

      readinessProbe:
        httpGet:
          path: /actuator/health/readiness
          port: http
        periodSeconds: 5
        timeoutSeconds: 2
        failureThreshold: 2
~~~

Values are illustrative and must match startup times and SLOs. `failureThreshold × periodSeconds` estimates the window before Kubernetes treats a probe as persistently failing, alongside `timeoutSeconds`, `initialDelaySeconds`, and actual probe timing.

Readiness failure does not restart the container. Liveness failure can trigger a restart. Mistakenly placing a Kafka dependency into liveness can cause all replicas to restart while the Kafka cluster is under maintenance.

### 7.2. Additional probe paths on the main port

In supported Spring Boot versions, additional paths can be enabled:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

This can expose `/livez` and `/readyz` on the main application port. That is helpful when the management server runs on a separate port: probes on the management port might still answer even if the main server port is failing.

Verify exact support and paths for your Spring Boot version. Do not assume all versions share identical defaults.

## 8. Kafka connection health is not liveness

A Kafka health indicator typically checks cluster communication via the Kafka Admin API. If brokers are unreachable, the contributor may return `DOWN`.

However, that does not prove the JVM is broken:

~~~text
Kafka cluster outage
      |
      +---- KafkaHealthIndicator = DOWN
      |
      +---- JVM / Spring context continues operating
      |
      +---- Kafka client can retry/reconnect
      |
      +---- Liveness should remain UP
~~~

If Kafka health is placed into liveness, Kubernetes can restart all Pods. When brokers recover, all Pods simultaneously open connections, start consumers, and trigger rebalances, adding pressure to the cluster.

Typically:
- Liveness focuses on the process's ability to self-recover.
- Readiness can consider Kafka if the service truly cannot accept work when Kafka is unavailable.
- Kafka connectivity is observed separately via health components/metrics.
- Consumer progress is evaluated via assignments, lag, processing rate, and error rate.

## 9. HTTP service readiness differs from Kafka worker readiness

This is an essential distinction when running Spring Kafka on Kubernetes.

For an HTTP API, Kubernetes readiness failure removes the Pod from Service endpoints. Load balancers stop sending new requests to that instance.

For a Kafka consumer, brokers **do not use Kubernetes readiness** to assign partitions. The Kafka group coordinator relies on consumer membership, subscriptions, heartbeats, and the rebalance protocol.

~~~text
HTTP workload:
  Readiness DOWN
      |
      v
  Pod removed from Service endpoints

Kafka workload:
  Readiness DOWN
      |
      v
  Kafka broker still sees consumer member
      |
      v
  Consumer can keep polling/processing
~~~

Therefore, if a consumer worker cannot process records because a database dependency is unavailable, merely switching readiness to `REFUSING_TRAFFIC` **does not automatically stop consumption**.

A separate policy is needed to control the listener container if the requirement is to stop taking new work while the dependency is unready.

## 10. Controlling Kafka listeners when a worker is not ready

Spring Kafka provides `KafkaListenerEndpointRegistry` to look up containers created by `@KafkaListener`. From there, the application can control lifecycle or pause/resume per policy.

Example managing pause/resume:

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class ConsumerWorkGate {

    private final KafkaListenerEndpointRegistry registry;

    public ConsumerWorkGate(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pauseOrders() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        if (container != null && container.isRunning()) {
            container.pause();
        }
    }

    public void resumeOrders() {
        MessageListenerContainer container =
                registry.getListenerContainer("orders-listener");

        if (container != null && container.isRunning()) {
            container.resume();
        }
    }
}
~~~

`pause()` requests temporary suspension of record delivery via the container API; the container can still keep polling to maintain consumer group membership. Exact timing of when pause takes effect and callbacks depend on container type and version.

| Action | Purpose | Group Consequence |
|---|---|---|
| `pause()` | Temporarily pause record delivery to listener | Container can keep polling and maintain membership |
| `resume()` | Allow listener to receive records again | Resumes processing on current assignment if still valid |
| `stop()` | End container lifecycle | Consumer closes and leaves group; can trigger rebalance |
| `start()` | Restart container | Consumer joins group and can trigger rebalance |

Never call pause/stop directly inside a health indicator. Health checks should observe and return status; a separate coordinator decides actions after applying thresholds, debouncing, and recovery policies.

### 10.1. Do not pause immediately on a single database error

If a query briefly times out for a few hundred milliseconds, pausing the whole consumer causes unnecessary churn. A realistic policy can:

1. Count consecutive dependency failures.
2. Evaluate failure duration and retryability.
3. Once a threshold is crossed, switch readiness to `REFUSING_TRAFFIC` if appropriate.
4. For consumer workers, pause the listener if continuing to consume risks repeated failures/rollbacks.
5. Keep monitoring the dependency with bounded health checks.
6. Once the dependency recovers steadily, resume the listener and return readiness to `ACCEPTING_TRAFFIC`.

Avoid creating a deadlock loop: pausing stops the consumer from processing, leaving nothing to test whether the dependency recovered so it can resume. The health coordinator must operate independently of the paused listener.

### 10.2. When to stop instead of pause?

Pause fits when you want to suspend delivery while preserving consumer group membership. Stop fits when you need to release the consumer and partition ownership, such as during shutdown or extended maintenance.

Stopping can trigger a rebalance, shifting partitions to other instances. If other instances also cannot process due to the same dependency outage, stopping all at once merely shifts the backlog around.

## 11. Which dependencies belong in readiness?

Not every dependency belongs in the readiness group.

| Dependency | Decision Question |
|---|---|
| PostgreSQL | Can the service answer/accept core requests if the DB is unavailable? |
| Kafka | Must the service publish/consume to fulfill the contract of new requests? |
| Redis/cache | Can cache failures fall back to the primary source? |
| External payment API | Can requests be accepted and queued for later processing? |
| Schema Registry | Can consumers/producers continue with currently cached schemas? |
| DLT topic | Does a DLT publish failure prevent preserving failed records? |

A dependency can be important without making the entire service unready. For instance, an API may accept commands and persist them to a database/outbox even while Kafka is temporarily unavailable; in that case, pulling the Pod from readiness could discard valid request intake that could have been safely persisted via outbox.

Conversely, if an endpoint must synchronously call a payment gateway with no fallback, readiness may reflect serving capability for that endpoint—though health groups are typically instance-wide rather than per-endpoint. Consider degraded modes or splitting capabilities/services.

## 12. Dependency outages and cascading failures

Suppose a Kafka outage affects all worker replicas:

~~~text
Kafka outage
    |
    +---- Kafka readiness check = DOWN on every Pod
    |
    +---- all Pods NotReady
    |
    +---- if liveness also depends on Kafka:
              |
              v
          restart storm
              |
              v
          connection/rebalance churn
              |
              v
          Kafka recovery becomes harder
~~~

Readiness `DOWN` can be useful to keep HTTP traffic away from unserviceable instances. Yet if every replica becomes unready, understand the upstream impact: the load balancer may have zero endpoints left and start returning 503s.

Ways to reduce impact:
- Provide clear degraded modes, such as APIs accepting commands into an outbox.
- Put only mandatory dependencies into readiness.
- Use retries/backoff and circuit breakers per policy.
- Separate HTTP API readiness from consumer worker state when capabilities differ.
- Avoid restarting all Pods on dependency outages.
- Alert on dependency health independently from liveness.

## 13. Graceful shutdown and readiness

When a Pod is terminated, the application should stop accepting new traffic before closing resources.

~~~text
SIGTERM / shutdown signal
          |
          v
Readiness -> REFUSING_TRAFFIC
          |
          v
Kubernetes updates endpoints
          |
          v
Spring lifecycle stops listener containers
          |
          v
In-flight work completes per policy
          |
          v
Close DB / producer / executor / context
          |
          v
Process exit
~~~

Actual ordering and timing depend on Spring lifecycle phases, termination hooks, and application configuration. Kubernetes endpoint propagation does not stop every incoming request instantaneously; include appropriate drain windows/connection draining.

For Kafka listeners:
- Container stop needs enough budget to finish current processing per policy.
- Kafka offsets commit only when ack/transaction semantics allow.
- If the process receives `SIGKILL`, uncommitted records may be redelivered.
- Business side effects must be idempotent.
- Never use readiness events as proof that records were committed.

`terminationGracePeriodSeconds`, Spring lifecycle timeouts, and Kafka container shutdown timeouts must be coordinated.

## 14. Availability state and custom health indicators

Availability state represents the application's intent and state; a `HealthIndicator` checks a component or capability.

Example custom readiness indicator:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("ordersProcessing")
public class OrdersProcessingHealthIndicator implements HealthIndicator {

    private final ProcessingGate gate;

    public OrdersProcessingHealthIndicator(ProcessingGate gate) {
        this.gate = gate;
    }

    @Override
    public Health health() {
        if (gate.isAcceptingWork()) {
            return Health.up()
                    .withDetail("acceptingWork", true)
                    .build();
        }

        return Health.outOfService()
                .withDetail("acceptingWork", false)
                .withDetail("reason", gate.reason())
                .build();
    }
}
~~~

`ProcessingGate` is an application-defined abstraction, not a Spring Kafka API. It can aggregate database dependency status, maintenance mode, or listener coordinator state.

The contributor can be added to the readiness group:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,ordersProcessing
~~~

Avoid running unbounded network calls inside every `health()` invocation. If checking a dependency, enforce finite timeouts and consider caching the latest result with explicit data age.

## 15. Do not confuse Kafka health with Kafka processing readiness

A Kafka health indicator can check Admin connectivity without guaranteeing producer/consumer capability. A service can have:

~~~text
Kafka Admin health: UP
Producer write:      DENIED
Consumer read:       OK
Listener assignment: empty
Database:             UP
~~~

Separate the signals:

| Signal | Purpose |
|---|---|
| Kafka cluster connectivity | Can `AdminClient` talk to the cluster? |
| Producer capability | Can the producer write to mandatory topics? |
| Consumer capability | Can the consumer join groups and fetch data? |
| Listener readiness | Has the container started and reached an appropriate state? |
| Assignment | Which partitions does the consumer own? |
| Processing health | Are records processed within latency/error SLOs? |

For produce/consume canaries, use a dedicated topic, dedicated event IDs, cleanup/retention, and a synthetic monitoring schedule rather than wiring them directly into liveness.

## 16. Readiness in applications with multiple listeners

A service may have:
- `orders-listener`: mandatory for core business logic.
- `analytics-listener`: optional; failure does not impair order processing.
- `audit-listener`: must run, though short backlogs are acceptable.

A single application-level readiness state requires an aggregation policy:

~~~text
orders-listener:    READY
analytics-listener: STOPPED (optional)
audit-listener:     READY
        |
        v
Application readiness: ACCEPTING_TRAFFIC
~~~

If a mandatory listener is not ready, the application can transition to `REFUSING_TRAFFIC`. Yet for worker-only applications, HTTP readiness does not directly affect Kafka assignments. If only one listener needs stopping, use the registry to control that exact listener ID rather than stopping the entire context.

Clearly define which listeners are critical, which are optional, whether one stopped listener makes APIs unready, when to pause/stop, and who is responsible for resuming.

## 17. Health checks should not block or cause side effects

Health endpoints can be called by many probes and monitoring systems. A check waiting indefinitely on a Kafka Admin request can exhaust request threads.

A good health indicator needs:
1. Finite timeouts.
2. No creating new Kafka producers/consumers on every call.
3. No sending business events or committing offsets.
4. No heavy scan queries.
5. No exposing sensitive credentials or topology.
6. Metrics/logs for duration and failures.
7. Never turning telemetry errors into liveness failures.

If health results are cached, expose result age and a policy for stale caches. Caching `UP` too long can hide outages; not caching while probing too often can create load.

## 18. Security of Actuator endpoints

Health endpoints can leak broker hostnames/cluster IDs, topic names, consumer group details, and exception metadata.

Production configuration should restrict exposure and details:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
~~~

If kubelet needs access to probe paths, ensure security allows internal health probes without exposing details to all clients. A separate management port, network policies, and authentication can be used depending on architecture.

Never return SASL JAAS configs, passwords, tokens, or raw client properties in health details.

## 19. Integration tests for readiness and liveness

Tests should verify `ApplicationAvailability`, Actuator groups, and integrated policies.

### 19.1. Checking default states

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class AvailabilityHealthIT {

    @Autowired
    MockMvc mvc;

    @Test
    void applicationStartsReadyAndAlive() throws Exception {
        mvc.perform(get("/actuator/health/liveness"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));

        mvc.perform(get("/actuator/health/readiness"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
    }
}
~~~

Tests must expose Actuator health groups in test configuration. Depending on version and management port, paths and responses may differ.

### 19.2. Readiness switching to REFUSING_TRAFFIC

~~~java
@Autowired
ApplicationContext context;

@Test
void readinessCanRefuseTrafficWhileLivenessRemainsUp() throws Exception {
    AvailabilityChangeEvent.publish(
            context,
            ReadinessState.REFUSING_TRAFFIC);

    mvc.perform(get("/actuator/health/readiness"))
            .andExpect(status().isServiceUnavailable());

    mvc.perform(get("/actuator/health/liveness"))
            .andExpect(status().isOk());
}
~~~

Imports include `AvailabilityChangeEvent` and `ReadinessState`. The test assumes default status mapping and a readiness group containing only readiness state; if custom indicators are added, expected aggregate outcomes must match policy.

### 19.3. Testing consumer worker pause/resume

With Kafka Testcontainers or Embedded Kafka:

1. Start the listener container and wait for assignment.
2. Send a record and confirm the listener receives it.
3. Have the coordinator pause the listener.
4. Send additional records and confirm the listener does not dispatch them while paused.
5. Verify the container retains the expected lifecycle state for its version.
6. Resume the listener and confirm the backlog is processed.
7. Check offset/duplicate semantics.
8. Stop the container and clean up the group/topic.

Do not test only HTTP readiness `DOWN` and assume the Kafka consumer stopped itself. Explicitly verify that the coordinator executed pause/stop.

### 19.4. Testing Kubernetes policy

Integration tests can verify HTTP statuses and paths, while restart/endpoint-removal behavior must be verified in a Kubernetes environment or via manifest validation. Confirm that readiness failures do not restart containers, liveness failures trigger restarts only after thresholds, startup probes defer the other two probes, Kafka outages do not pull liveness `DOWN`, and shutdown has an adequate termination grace period.

## 20. Common mistakes

- **Using one health endpoint for both readiness and liveness:** easily causes restarts when external dependencies fail.
- **Putting Kafka into liveness:** broker outages can trigger restart storms.
- **Assuming readiness DOWN automatically stops Kafka listeners:** Kubernetes does not control Kafka groups via readiness.
- **Using readiness to prove the consumer has assigned partitions:** assignment is a separate state.
- **Using consumer start events as proof of readiness:** a consumer can start without partitions or without being able to process records.
- **Putting every dependency into readiness:** an optional dependency can pull the whole service out of traffic.
- **Not defining critical vs. optional listeners:** one auxiliary listener stopping can unnecessarily make the entire app unready.
- **Pausing listeners without a resume mechanism:** workers remain stuck permanently after dependency recovery.
- **Stopping all consumers on a dependency outage:** causes rebalances and shifts backlog to other replicas that cannot process it either.
- **Making un-timeouted network calls in HealthIndicator:** health endpoints can hang.
- **Using liveness to fix ACL errors:** restarts do not fix credentials/permissions.
- **Not coordinating startupProbe:** slow-starting apps get killed by liveness before becoming ready.
- **Treating HTTP 200 on the management port as main app port health:** the management server can stay alive while the main server is broken.
- **Not testing shutdown/redelivery:** in-flight records may be redelivered after restart.
- **Exposing health details publicly:** leaks cluster topology and exception metadata.

## 21. Production design checklist

Before deploying readiness/liveness for a Spring Kafka service, clarify:

1. What capability does readiness reflect: HTTP traffic, Kafka consume, Kafka produce, or all?
2. Does liveness reflect only process faults that may require a restart?
3. Are Kafka/database outages kept out of liveness?
4. Which dependencies are truly mandatory to serve core workloads?
5. Which listeners are critical, and which are optional?
6. How does readiness failure affect Kubernetes Service endpoints?
7. For worker-only services, what pauses/stops listeners when a dependency is unready?
8. What resumes listeners after dependency recovery?
9. Does pause or stop fit group membership and rebalance requirements?
10. Does `startupProbe` budget enough time for Spring context and Kafka initialization?
11. Do liveness/readiness timeouts and failure thresholds avoid flapping?
12. Do health indicators use finite timeouts and avoid side effects?
13. Are Actuator details protected?
14. Does graceful shutdown coordinate readiness, listener stop, transactions, and termination grace period?
15. Do integration tests prove readiness and liveness are independent?
16. Do Kafka worker tests verify actual pause/resume rather than HTTP status alone?
17. Do consumer lag, assignment, retry/DLT, and processing latency have separate dashboards?

**Separating readiness and liveness** lets Spring Boot and Kubernetes respond accurately to two distinct classes of problems: an instance temporarily unable to accept new work, and a process unable to continue operating. With Spring Kafka, one extra boundary is critical: HTTP readiness does not automatically stop consumers or change partition assignments. Use Actuator availability states to represent application status, Kubernetes probes to orchestrate Pods, and listener container APIs to control consumption under your own policy. Keep dependency outages out of liveness unless there is evidence the process needs a restart, and clearly define capabilities, pause/resume, shutdown, and recovery to avoid restart storms, ping-ponging backlogs, or misprocessed records.

