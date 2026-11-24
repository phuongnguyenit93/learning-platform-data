# Readiness When Brokers Are Not Ready

A Spring Kafka application can start the JVM and Spring `ApplicationContext` while **Kafka brokers are not yet ready to accept connections or serve requests**. This commonly happens when Kubernetes starts an application pod before the broker, when brokers are undergoing a rolling restart, when DNS/network is not yet stable, when a cluster has just recovered from an outage, or when Kafka authentication/authorization is not working properly yet.

In production, **a running process does not mean the service is ready to serve**. Readiness must reflect the ability to perform the work assigned to the instance. If a service cannot accept or process messages when Kafka is unavailable, it should not be marked ready simply because the HTTP server opened its port.

However, readiness must also be properly scoped: **broker unavailability is not a reason for the liveness probe to fail and for Kubernetes to repeatedly restart the pod**. The broker is an external dependency; restarting the application will not make the broker healthy. With Spring Kafka, you must distinguish application startup, broker connectivity, listener container running state, consumer group assignment, producer capability, and business dependency health.

This lesson covers how to design readiness when brokers are not ready, use Spring Boot Actuator and Kafka `AdminClient` for time-bounded broker checks, coordinate consumer assignment state, distinguish readiness/liveness/startup probes, manage retry/recovery, avoid probe flapping, and test broker outage scenarios.

## 1. Process started does not mean service ready

A Spring Boot application can go through these stages:

~~~text
JVM started
    |
    v
Spring ApplicationContext initialized
    |
    v
HTTP server started
    |
    v
Kafka listener containers start
    |
    v
Kafka broker reachable
    |
    v
Consumer group assigned required partitions
    |
    v
Business dependencies ready
    |
    v
Application ready
~~~

These milestones are distinct:

- **Started**: the process/JVM is running.
- **Application context ready**: Spring has created beans and completed the corresponding initialization phase.
- **HTTP accepting connections**: the web server can accept requests.
- **Kafka reachable**: the application can reach the broker/cluster according to the selected check.
- **Listener assigned**: the consumer has joined the group and received the required partitions.
- **Business ready**: databases, schemas, credentials, and dependencies needed for message processing are ready.

If Kubernetes only checks an HTTP port or an endpoint that returns 200 as soon as the web server opens, the pod can enter Service endpoints while the Kafka broker is still unavailable.

Readiness must answer a concrete question: **can this instance perform its current role properly without accepting additional work that it cannot process safely?**

## 2. Readiness, liveness, and startup probes differ

Kubernetes provides three probe types with distinct purposes:

| Probe | Question | What does Kubernetes do on failure? |
|---|---|---|
| **Startup** | Has the application finished its startup phase so further checks can run? | Continues checking startup; if the failure threshold is exceeded, the container may be restarted |
| **Readiness** | Should the pod receive new traffic/work? | Marks the pod NotReady and removes it from Service endpoints |
| **Liveness** | Is the process still alive and capable of recovering on its own? | Restarts the container after exceeding the failure threshold |

For a Kafka dependency:

- **Readiness** can fail when brokers are not ready if Kafka is a mandatory dependency for the service's role.
- **Liveness** should generally not depend directly on Kafka brokers.
- **Startup probe** gives the application time to start and wait for dependencies within a bounded window without being restarted prematurely by the liveness probe.

Example scenario:

~~~text
Kafka broker is performing a rolling restart
       |
       v
Spring Boot application continues running normally
       |
       +-- readiness -> DOWN
       |
       +-- liveness  -> UP
       |
       v
Kubernetes keeps the pod running without routing new HTTP traffic to it
       |
       v
Broker recovers
       |
       v
Readiness -> UP
~~~

This avoids a **restart storm** when a shared dependency experiences an outage.

## 3. How does readiness affect Kafka consumers?

An important point: a Kubernetes readiness probe primarily controls whether the pod is included in **Service endpoints**. It **does not automatically stop the Kafka listener container**.

If a consumer application marks itself NotReady while the Kafka broker is still reachable, the listener container can continue consuming records normally. That may be right or wrong depending on business requirements.

~~~text
Pod NotReady in Kubernetes Service
       |
       +-- new HTTP traffic is not routed to the pod
       |
       +-- Kafka listener is still RUNNING
               |
               +-- continues polling and processing records
~~~

Therefore, you must define what readiness is used for:

1. **HTTP readiness**: whether the instance can serve API requests.
2. **Kafka consumer readiness**: whether the listener has broker connectivity, assignments, and required dependencies.
3. **Producer readiness**: whether the application can publish according to business requirements.
4. **Combined application readiness**: all capabilities required for the service role are ready.

If the consumer must stop receiving records when the database is overloaded, merely returning readiness `DOWN` is not enough. You need to coordinate **pausing/resuming the container** or a dedicated consumption-control mechanism, with safe acknowledgment/offset semantics.

## 4. Reasons a broker may not be ready

Not all Kafka connection failures are the same:

| Cause | Observable Symptoms | Action |
|---|---|---|
| Broker process has not started | Connection refused / timeout | Wait with bounded retries and keep readiness `DOWN` |
| DNS cannot resolve | Unknown host / resolution error | Check service discovery and DNS |
| Network policy/firewall | Timeout or connection failure | Check network path |
| Kafka metadata not yet stable | Broker/controller metadata errors | Wait for cluster stabilization and observe |
| TLS handshake failure | SSL handshake exception | Check truststore/certificates |
| SASL authentication failure | Authentication exception | Check mechanism, credentials, JAAS |
| Missing ACL permissions | Topic/group/cluster authorization exception | Grant proper permissions; do not retry infinitely |
| Topic does not exist yet | Unknown topic/partition or metadata timeout | Check provisioning and missing-topic policy |
| Transaction coordinator not ready | Transaction initialization/commit failure | Check coordinator and producer transaction state |
| Broker reachable but business dependency failing | Consumer can poll, but DB/API is unusable | Readiness should reflect the business dependency separately |

A probe that only checks whether a bootstrap broker responds with metadata **does not prove that all Kafka operations will succeed**. For example, `AdminClient` may be able to describe the cluster while the producer lacks permission to write to a topic or the consumer lacks permission to join a group.

## 5. Do not make liveness depend on brokers

A dangerous configuration:

~~~text
Liveness:
  Kafka broker reachable?

Broker DOWN
  -> liveness DOWN
  -> Kubernetes restarts application
  -> application reconnects
  -> broker still DOWN
  -> liveness DOWN
  -> restarts again
~~~

The outcome can be:

- The application restarts continuously even though the code has no bug.
- Consumer group churn and rebalances when the broker recovers.
- Producer/consumer connection storms.
- Spikes in logs and metrics.
- Longer overall recovery time.

**Liveness should check whether the process/application is internally stuck or broken**, such as a dead event loop, a severe deadlock, or an unresponsive internal health mechanism.

A broker outage is normally an external dependency condition that the application should wait to recover from. Putting it into liveness makes Kubernetes act at the wrong layer.

A useful rule of thumb:

~~~text
Broker unavailable:
  readiness = DOWN
  liveness  = UP
~~~

This is a sensible default for services depending on Kafka, though exact readiness depends on the role and degraded modes supported by the application.

## 6. Spring Boot Actuator health probes

Spring Boot Actuator provides health infrastructure and health groups for readiness/liveness in versions that support Kubernetes probes.

Example configuration:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,kafkaBroker
        liveness:
          include: livenessState
  endpoints:
    web:
      exposure:
        include: health,info
~~~

In this example:

- **readinessState** reflects the `ReadinessState` managed by Spring Boot.
- **kafkaBroker** is a custom `HealthIndicator` provided by the application.
- **livenessState** reflects `LivenessState`.

The health contributor name in the `include` list must match the actual bean name/health contributor ID. If the bean is named `kafkaBrokerHealthIndicator`, Spring Boot typically resolves the corresponding contributor ID as **kafkaBroker**.

Properties and probe defaults change across Spring Boot versions. Check your project's dependency version before applying YAML verbatim.

Do not include `kafkaBroker` in the liveness group just to force Kubernetes to restart the application during a Kafka outage.

## 7. Creating a long-lived AdminClient for broker health

One way to check brokers is using Kafka's **AdminClient.describeCluster()**. Do not create and close a new `AdminClient` on every health check; manage a client bean with a clear lifecycle.

Example using configuration already managed by Spring Kafka's **KafkaAdmin**:

~~~java
@Configuration
public class KafkaReadinessConfiguration {

    @Bean(destroyMethod = "close")
    AdminClient readinessAdminClient(KafkaAdmin kafkaAdmin) {
        return AdminClient.create(
                kafkaAdmin.getConfigurationProperties());
    }
}
~~~

Required imports for the example:

~~~java
import org.apache.kafka.clients.admin.AdminClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.core.KafkaAdmin;
~~~

`KafkaAdmin` provides the application's `AdminClient` configuration in Spring Kafka versions that support this API. Verify your exact version and ensure the configuration includes bootstrap servers, TLS/SASL, and required security properties.

The client is closed when the Spring context shuts down thanks to **destroyMethod="close"**. If the application uses multiple Kafka clusters, manage a separate `AdminClient`/health contributor per cluster alias.

Do not use a single `AdminClient` bean for one cluster and treat it as proof that all Kafka clusters in the application are healthy.

## 8. HealthIndicator checking the broker with a timeout

A custom `HealthIndicator`:

~~~java
@Component("kafkaBrokerHealthIndicator")
public class KafkaBrokerHealthIndicator implements HealthIndicator {

    private final AdminClient adminClient;
    private final long timeoutMillis;

    public KafkaBrokerHealthIndicator(AdminClient adminClient) {
        this.adminClient = adminClient;
        this.timeoutMillis = 2_000L;
    }

    @Override
    public Health health() {
        try {
            Collection<Node> nodes = adminClient.describeCluster()
                    .nodes()
                    .get(timeoutMillis, TimeUnit.MILLISECONDS);

            if (nodes == null || nodes.isEmpty()) {
                return Health.down()
                        .withDetail("reason", "no_brokers_discovered")
                        .build();
            }

            return Health.up()
                    .withDetail("brokerCount", nodes.size())
                    .build();
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return Health.down()
                    .withDetail("reason", "probe_interrupted")
                    .build();
        }
        catch (Exception ex) {
            return Health.down()
                    .withDetail("reason", "broker_unavailable")
                    .withDetail("errorType", ex.getClass().getSimpleName())
                    .build();
        }
    }
}
~~~

Key imports:

~~~java
import java.util.Collection;
import java.util.concurrent.TimeUnit;
import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.common.Node;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;
~~~

Key points:

- **The AdminClient is reused**, not created per request.
- **Finite timeout** so the health endpoint does not hang for long when brokers are unavailable.
- When the thread is interrupted, restore the interrupt flag.
- Health details only record generic error categories, avoiding leaking credentials, SASL details, or connection strings.
- Do not write raw exception messages into public health endpoint responses.

A 2-second timeout is only an example. It must be shorter than the probe timeout and fit cluster latency. Kafka `AdminClient` also has its own request and default API timeouts; set them consistently so calls do not hold resources for too long.

## 9. What does the broker probe actually check?

The code above calls **describeCluster().nodes()**. If it returns a list of brokers, the application was able to retrieve cluster metadata using the current `AdminClient` permissions and configuration.

It provides evidence that:

- The DNS/network path to bootstrap brokers works well enough to fetch metadata.
- The Kafka cluster responds to a describe-cluster request.
- Credentials/ACLs for this metadata operation are valid.
- Broker nodes are discovered.

It **does not prove**:

- That the consumer group has been assigned partitions.
- That the consumer has permission to read all required topics.
- That the producer has permission to write to all topics.
- That the transaction coordinator is ready for a transactional producer.
- That a specific topic exists or has the right partition count.
- That database/API dependencies of business handlers are healthy.
- That an actual record can be processed end-to-end.

Therefore, name the health indicator **kafkaBroker** or **kafkaClusterMetadata**, rather than `businessReady` if it only checks broker metadata.

## 10. Timeouts and health probe impact

Health endpoints can be called frequently by Kubernetes. If each request creates a new Kafka `AdminClient` and waits for a long broker timeout, the probes themselves will add load while the broker is already struggling.

~~~text
Kubernetes probes:
  10 pods
  each pod probes every 5 seconds
  each probe creates a new AdminClient
  broker does not respond for 10 seconds

=> many concurrent connections and pending requests
~~~

Mitigations:

1. Use a single long-lived, managed `AdminClient`.
2. Set finite timeouts for each health check.
3. Do not run unbounded overlapping `describeCluster` requests.
4. Consider caching results briefly or updating health state via a background probe.
5. Limit details returned in health responses.
6. Do not run health checks more frequently than the broker's recovery capacity allows.

Health checks must be sensitive enough to detect outages without becoming a source of connection storms.

## 11. Synchronous HealthIndicator or background probe?

There are two ways to organize this:

### Synchronous probe when the health endpoint is called

Each time the Actuator health check calls `health()`, the code executes an `AdminClient` request with a timeout.

Pros:

- Status reflects the latest check result closely.
- Simple structure.
- Little separate state to synchronize.

Cons:

- The probe endpoint can become slow when brokers/networks are slow.
- Many pods probing simultaneously can generate many requests.
- Frequent Kubernetes probes can cause unnecessary load.

### Background probe updating a cached state

A scheduled task checks the broker periodically, stores the result, and the `HealthIndicator` simply reads the updated state.

~~~text
Scheduled probe
     |
     v
AdminClient.describeCluster()
     |
     v
Broker result
     |
     v
Atomic readiness snapshot
     |
     v
Actuator health endpoint reads snapshot
~~~

Pros:

- Health endpoint responds quickly and predictably.
- Broker call frequency can be capped.
- Easy to apply hysteresis and consecutive failure thresholds.

Cons:

- Status lags behind reality slightly.
- Stale results and startup state must be managed.
- The background task needs explicit timeouts and lifecycle management.

For systems with many replicas or short probe intervals, a **background probe with cached state** is usually better suited, provided data age limits and stale-state handling are in place.

## 12. Never-probed state must be NOT READY

Right after startup, the background probe may not have completed its first run. Do not assume the broker is healthy just because no error has occurred yet.

A state model:

~~~text
UNKNOWN
  |
  +-- probe success -> UP
  |
  +-- probe failure -> DOWN

UP
  |
  +-- consecutive failures exceed threshold -> DOWN

DOWN
  |
  +-- consecutive successes reach threshold -> UP
~~~

Where:

- **UNKNOWN**: no reliable result yet.
- **UP**: recent probes succeeded.
- **DOWN**: recent probes failed sufficiently.

Readiness while in `UNKNOWN` state should return **OUT_OF_SERVICE or DOWN**, depending on policy. Never mark `UP` before the first result arrives.

A snapshot can store:

~~~text
status: UNKNOWN | UP | DOWN
lastSuccessAt: timestamp
lastProbeAt: timestamp
consecutiveFailures: integer
consecutiveSuccesses: integer
lastErrorCategory: bounded value
~~~

Do not store exception messages or credentials in the readiness snapshot.

## 13. Hysteresis to prevent readiness flapping

If readiness toggles `UP`/`DOWN` on a single brief timeout, Kubernetes Service endpoints can continuously add and remove the pod.

Example policy:

~~~text
UP:
  1 probe failure -> keep UP
  3 consecutive failures -> DOWN

DOWN:
  1 probe success -> remain DOWN
  2 consecutive successes -> UP
~~~

These thresholds are only examples. Choose them based on:

- Broker outage SLO.
- Probe interval and timeout.
- Consumer reconnect behavior.
- Acceptable degraded-mode handling.
- Impact of pods leaving/rejoining Service endpoints.

**Do not delay `DOWN` for too long** if the instance genuinely cannot process messages safely. Hysteresis filters out brief noise; it must not mask a prolonged outage.

## 14. Kubernetes probe configuration

Example Deployment:

~~~yaml
spec:
  template:
    spec:
      containers:
        - name: orders-service
          image: example/orders-service:1.0
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
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 3
            failureThreshold: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
~~~

This example assumes Actuator health probe paths are enabled and endpoints are properly exposed. `periodSeconds`/`timeoutSeconds`/`failureThreshold` values must be tuned to your SLO and actual startup time.

The startup probe uses the liveness endpoint to confirm the application process has started; it **does not wait for Kafka to be healthy**. After the startup probe succeeds, readiness decides whether the pod receives traffic, while liveness continues checking process health.

If using a Spring Boot version that does not automatically expose these health probe paths, enable probes or configure the appropriate endpoint paths.

## 15. What should the readiness group include?

A service may have multiple dependencies:

~~~text
orders-service
  |
  +-- database
  +-- Kafka cluster
  +-- schema registry
  +-- payment API
  +-- object storage
~~~

Do not include every dependency in readiness just because a `HealthIndicator` exists for it. Identify which dependencies are truly mandatory for the instance to serve its current role.

Example:

~~~yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,kafkaBroker,database
        liveness:
          include: livenessState
~~~

If the application can still serve read-only HTTP GET requests when Kafka is unavailable, but cannot accept order-creation commands, a **global readiness** depending on Kafka might pull the pod from the entire HTTP Service too broadly. You can design per-capability health groups/endpoints or return degraded status at the API layer.

Conversely, if every request in the service must publish a Kafka event to guarantee consistency, Kafka can be a mandatory readiness dependency.

**Readiness is a role-based decision**, not an identical dependency checklist across every service.

## 16. Broker reachable does not mean consumer ready

An `AdminClient` probe can return `UP` while the consumer has not received any partition assignment yet.

~~~text
AdminClient:
  describeCluster() -> success

KafkaListenerContainer:
  isRunning() -> true
  consumer group -> no partitions assigned yet

Business processing:
  cannot process records yet
~~~

Possible causes:

- The consumer group has not joined successfully yet.
- The topic does not exist yet or has no partitions.
- Group/topic ACLs are missing.
- Rebalance has not completed yet.
- The consumer is paused.
- The consumer instance has not been accepted by the broker due to authentication/configuration.

For a service responsible for **consuming** a mandatory topic, readiness may also need to check **assignment readiness**.

Do not use `isRunning()` as proof that the consumer is ready. Running only indicates that the container lifecycle is running; it does not confirm that the group has assigned partitions.

## 17. Tracking assignments with ConsumerAwareRebalanceListener

Spring Kafka provides **ConsumerAwareRebalanceListener** to receive callbacks when partitions are assigned or revoked. These callbacks can be used to update assignment state:

~~~java
@Component
public class OrdersAssignmentTracker
        implements ConsumerAwareRebalanceListener {

    private final AssignedPartitionRegistry registry;

    public OrdersAssignmentTracker(AssignedPartitionRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void onPartitionsAssigned(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        registry.assigned(consumer, partitions);
    }

    @Override
    public void onPartitionsRevokedBeforeCommit(
            Consumer<?, ?> consumer,
            Collection<TopicPartition> partitions) {

        registry.revoked(consumer, partitions);
    }
}
~~~

This is illustrative code: `AssignedPartitionRegistry` is an application component that must be implemented thread-safely. If the Spring Kafka version supports the `onPartitionsLost` callback, the registry must also clear ownership when the consumer loses partitions without a normal revoke.

Registering the listener:

~~~java
factory.getContainerProperties()
        .setConsumerRebalanceListener(ordersAssignmentTracker);
~~~

When using a concurrent container, multiple child consumers can invoke callbacks on different threads. The registry must distinguish consumer/container identity and only add/remove the corresponding partitions.

Do not just keep a single global `AtomicBoolean assigned` set to true when **any** child receives a partition. A parent container may have children that are not ready yet, or partitions may be revoked immediately afterward.

## 18. How to determine assignment readiness?

A simple policy for a consumer group:

~~~text
Required topic:
  orders.commands

Expected partitions:
  6

Observed assigned partitions:
  consumer 0 -> P0, P1
  consumer 1 -> P2, P3
  consumer 2 -> P4, P5

Assigned coverage:
  6 / 6

Consumer group assignment readiness:
  READY
~~~

However, **not all partitions assigned in a group have to reside on one instance**. If a group has multiple replicas, each pod receives only a subset of partitions. Therefore, you cannot require every pod to own the full partition count of the topic.

Possible policies include:

- **At least one partition assigned** for a consumer instance that must actively consume.
- **Expected assignment per child** based on concurrency and group assignment.
- **Group-level coverage** measured via a separate observability system, which cannot be concluded fully from a single pod alone.
- **Listener container running + no fatal startup/auth error + at least one assignment** for pod-level readiness.

Choose a policy based on group architecture and partition distribution capability. For valid instances with zero partitions because replica count exceeds partition count, marking them NotReady can cause scaling/rebalance loops.

## 19. Assignment readiness and rebalances

During a rebalance, a consumer can temporarily lose its assignment before receiving a new one. If readiness flips `DOWN`/`UP` immediately on every callback, pods can flap during deployments or scaling.

~~~text
Assigned
   |
   v
Rebalance begins
   |
   v
Partitions revoked
   |
   v
No assignment temporarily
   |
   v
Partitions assigned again
   |
   v
Ready
~~~

A policy can use a short grace period for expected rebalances, but must enforce a timeout so readiness is not kept `UP` indefinitely when a consumer truly loses ownership.

Do not treat `onPartitionsRevoked` as proof that the broker is unavailable. Rebalancing is normal group lifecycle activity.

With cooperative rebalancing, a consumer may revoke only a subset of partitions while retaining others. The assignment tracker must update only the exact set passed to the callback, without wiping out the entire parent state.

## 20. Producer readiness differs from consumer readiness

An application that only publishes to Kafka may have no listener consumers. For a producer-only service, assignment readiness is meaningless.

Producer readiness may need to verify:

- Broker metadata is reachable.
- The producer factory can instantiate a producer.
- Serializer/configuration is valid.
- ACLs allow writing to required topics.
- If transactional, the transaction coordinator and transactional ID are working.

**AdminClient.describeCluster() does not check produce permissions**. The broker can be `UP` while the producer hits `TopicAuthorizationException` when sending to a topic.

Some systems send a **canary message** to a health topic to test the real publish path. This must be designed carefully:

- Use a dedicated topic, dedicated key/event type, and corresponding confirming consumer.
- Identify the canary so business listeners do not process it like a real order.
- Enforce timeouts and cleanup/retention.
- Do not send canaries on every health probe.
- Evaluate the impact on transactional producers if the publish path uses transactions.

Never send synthetic messages to a business topic to prove readiness; doing so can trigger real side effects.

## 21. Consumer readiness is not producer readiness

A service with both a consumer and a producer:

~~~text
orders-service
  |
  +-- consume orders.commands
  |
  +-- process order
  |
  +-- produce orders.events
~~~

If broker metadata is reachable but consumer ACLs are missing, the producer can still work. If the consumer can read but producer ACLs are missing, the listener still receives records but cannot complete output.

Overall readiness needs to define which capabilities are mandatory:

~~~text
broker metadata reachable
       AND
required consumer assignment ready
       AND
required produce capability ready
       AND
database ready
       |
       v
application ready
~~~

For transactional producers, a single `describeCluster` call is not enough to prove transactions can commit. Separate integration/canary validation or detection via producer transaction health/error metrics may be required.

Do not run a transaction canary on every liveness/readiness probe; doing so creates producer churn, transaction coordinator load, and unwanted data.

## 22. Listener container startup when brokers are not ready

Spring Kafka listener containers can start once the Spring context finishes initializing. If brokers are unavailable, the Kafka consumer can hit connection errors in the poll/reconnect path and retry according to client behavior/configuration.

Things to distinguish:

- The container bean has started.
- The consumer object has been created.
- The consumer has connected and fetched metadata.
- The consumer has joined the group.
- The consumer has received partitions.
- The listener has processed records.

Not every state can be represented by a single `isRunning()` boolean.

During a brief outage, it is usually best to let the application and container keep their lifecycle running so the Kafka client reconnects automatically, while readiness reflects that brokers are not ready. If the container stops due to a fatal error (such as authentication/authorization misconfiguration or a non-retryable initialization error under policy), readiness should reflect that the listener is genuinely inactive and operators need to investigate.

Do not repeatedly restart the listener just because of a broker connection timeout. Restarting does not replace the Kafka client's own reconnect/backoff mechanism.

## 23. Authentication and authorization need separate policies

A reachable broker with invalid credentials is a different situation from a broker that has not started yet.

| Error | Should you wait for self-recovery? |
|---|---|
| Broker connection refused during rollout | Usually yes, with retries and readiness `DOWN` |
| Temporary network timeout | Usually yes, with backoff |
| Temporary DNS failure | Can wait and observe |
| Invalid SASL credentials | Should not retry infinitely like a transient error |
| Incorrect TLS truststore/certificate | Configuration/certificate must be fixed |
| Topic authorization denied | ACLs must be fixed |
| Consumer group authorization denied | ACLs must be fixed |

Spring Kafka has a configuration related to **authExceptionRetryInterval** on the listener container in supported versions. If configured appropriately, certain authentication/authorization exceptions can be retried on an interval instead of stopping the container immediately.

Do not enable infinite retries for invalid credentials without alerting; readiness will stay `DOWN` continuously while operators remain unaware of the root cause.

Health responses should return an error category such as **authentication**, **authorization**, **network**, or **metadata_timeout**, rather than exposing raw exception messages that may contain sensitive data.

## 24. Missing topic does not mean broker unavailable

Brokers can be `UP` while the topic subscribed by the listener does not exist yet.

Spring Kafka provides **missingTopicsFatal** on container properties in supported versions. This property controls behavior when a topic required by a listener does not exist during the corresponding check phase.

~~~java
factory.getContainerProperties()
        .setMissingTopicsFatal(true);
~~~

This is a fail-fast option when the topic is a mandatory dependency and a missing topic is considered a configuration/provisioning error. However, if topics are created after the application starts, the policy must align with the provisioning workflow.

Do not confuse:

- **Broker unavailable**: cannot reach the cluster.
- **Topic missing**: cluster is reachable, but the resource does not exist yet.
- **Topic authorization denied**: resource may exist, but the client lacks permission.
- **No partition assigned**: group/assignment state is not ready yet.

Readiness may be `DOWN` in all four cases, but the error category and remediation differ.

## 25. Do not fail-fast application startup on Kafka if flexible recovery is desired

One option is to force application startup to fail immediately when Kafka is unavailable. This can fit when:

- The application has no useful function without Kafka.
- The deployment/orchestrator has appropriate retry/backoff.
- Kafka availability is mandatory to complete initialization.
- You do not want processes lingering in a degraded state.

However, in many Kubernetes environments, **letting the application start with readiness `DOWN` and waiting for Kafka recovery** can be better:

- Pods are not restarted continuously.
- Logs/metrics remain observable via management endpoints.
- The Spring Kafka client can reconnect per policy.
- When brokers recover, readiness can transition to `UP` without redeploying.

There is no single choice for every application. What matters is that startup policy, retry behavior, and Kubernetes probes are consistent.

## 26. ApplicationAvailability and ReadinessState

Spring Boot provides **ApplicationAvailability** and **AvailabilityChangeEvent** to manage readiness/liveness state.

Readiness states typically include:

- **ACCEPTING_TRAFFIC**: the application is ready to accept traffic.
- **REFUSING_TRAFFIC**: the application is not ready or is shutting down.

State can be changed proactively:

~~~java
@Component
public class KafkaReadinessStatePublisher {

    private final ApplicationContext applicationContext;

    public KafkaReadinessStatePublisher(
            ApplicationContext applicationContext) {
        this.applicationContext = applicationContext;
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
}
~~~

Key imports:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;
~~~

This example illustrates how to publish readiness state. Note that **ReadinessState is an application-wide state**, so one controller must not arbitrarily set `ACCEPTING_TRAFFIC` while another dependency still requires `REFUSING_TRAFFIC`.

When there are multiple readiness reasons, use a coordinator that computes the aggregate state from all conditions instead of letting each `HealthIndicator` emit events and overwrite one another.

## 27. HealthIndicator and AvailabilityChangeEvent differ

Both mechanisms can participate in readiness, but they are not identical:

| Mechanism | Role |
|---|---|
| **HealthIndicator** | Returns `UP`/`DOWN`/`OUT_OF_SERVICE`/`UNKNOWN` for a dependency or component |
| **Health group** | Aggregates multiple health contributors into an endpoint/group |
| **ReadinessState** | Application state indicating whether traffic is accepted |
| **AvailabilityChangeEvent** | Publishes/changes availability state |
| **Kubernetes readiness probe** | Reads the endpoint to decide whether the pod stays in Service endpoints |

If the readiness group includes `readinessState,kafkaBroker`, a `DOWN` broker `HealthIndicator` can mark the readiness group `DOWN` even while `ReadinessState` remains `ACCEPTING_TRAFFIC`. This is a clean compositional model.

If you want to use `AvailabilityChangeEvent` to update readiness state, a coordinator must listen to broker state and publish transitions. Then the group can include `readinessState` along with other components per policy.

You do not need to use both approaches at once. Avoid creating two conflicting sources of truth.

## 28. Example cached broker health state

A background probe can store its result in a bean:

~~~java
public record BrokerHealthSnapshot(
        boolean known,
        boolean available,
        Instant lastProbeAt,
        String errorCategory) {
}
~~~

A component checking periodically:

~~~java
@Component
public class BrokerHealthMonitor {

    private final AdminClient adminClient;
    private final AtomicReference<BrokerHealthSnapshot> snapshot =
            new AtomicReference<>(
                    new BrokerHealthSnapshot(
                            false, false, Instant.EPOCH, "not_probed"));

    public BrokerHealthMonitor(AdminClient adminClient) {
        this.adminClient = adminClient;
    }

    @Scheduled(fixedDelay = 5_000L)
    public void probe() {
        try {
            Collection<Node> nodes = adminClient.describeCluster()
                    .nodes()
                    .get(2, TimeUnit.SECONDS);

            boolean available = nodes != null && !nodes.isEmpty();
            snapshot.set(new BrokerHealthSnapshot(
                    true,
                    available,
                    Instant.now(),
                    available ? "none" : "no_brokers_discovered"));
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            snapshot.set(new BrokerHealthSnapshot(
                    true, false, Instant.now(), "interrupted"));
        }
        catch (Exception ex) {
            snapshot.set(new BrokerHealthSnapshot(
                    true, false, Instant.now(), "broker_unavailable"));
        }
    }

    public BrokerHealthSnapshot current() {
        return snapshot.get();
    }
}
~~~

This is a minimal example illustrating a background probe and thread-safe snapshot. Production requires adding:

- Consecutive failure/success thresholds.
- Stale snapshot timeout.
- Metrics and logs for errors.
- Guarding against overlapping probes if a previous request has not finished.
- Shutdown handling and exception classification.

**Never treat an old snapshot as healthy indefinitely**. If `lastProbeAt` is too old per policy, the health state should become `UNKNOWN`/`DOWN`.

## 29. HealthIndicator reading a cached snapshot

The health endpoint can simply read the snapshot:

~~~java
@Component("kafkaBrokerHealthIndicator")
public class CachedKafkaBrokerHealthIndicator
        implements HealthIndicator {

    private final BrokerHealthMonitor monitor;

    public CachedKafkaBrokerHealthIndicator(
            BrokerHealthMonitor monitor) {
        this.monitor = monitor;
    }

    @Override
    public Health health() {
        BrokerHealthSnapshot state = monitor.current();

        if (!state.known() || !state.available()) {
            return Health.down()
                    .withDetail("errorCategory", state.errorCategory())
                    .withDetail("lastProbeAt", state.lastProbeAt())
                    .build();
        }

        return Health.up()
                .withDetail("lastProbeAt", state.lastProbeAt())
                .build();
    }
}
~~~

This example uses a boolean snapshot for simplicity. If you need to distinguish `UNKNOWN` and `DOWN`, you can return `Health.unknown()` for unprobed or stale states, depending on how the health group and Kubernetes interpret it.

For readiness, an unverified state should generally be treated as **not ready**. For liveness, cached broker health should not be included.

## 30. Hysteresis for broker readiness

A probe may briefly time out due to GC pauses, network jitter, or broker leader elections. Switching readiness `UP`/`DOWN` immediately on every single probe can cause flapping.

Example policy:

~~~text
State = UP
  failure #1 -> keep UP
  failure #2 -> keep UP
  failure #3 -> DOWN

State = DOWN
  success #1 -> keep DOWN
  success #2 -> UP
~~~

Hysteresis must be combined with a **stale timeout**:

- If the background probe thread dies or stops running, the snapshot must not remain `UP` indefinitely.
- If a probe hangs, the timeout must complete the future and record a failure.
- If the broker recovers while `AdminClient` caches stale metadata, the next probe must have enough time to fetch fresh metadata.

These thresholds are only examples. Do not wait for too many failures if an outage immediately impairs message processing; also do not switch `UP` after a single success if the broker cluster is still unstable.

## 31. Readiness policies by service role

Not every service needs the same policy:

| Role | Broker unavailable | Recommended readiness |
|---|---|---|
| Consumer-only worker | Cannot receive/process Kafka records | `DOWN` if Kafka is a mandatory dependency |
| Producer-only API | Cannot publish mandatory request events | `DOWN` for publish-dependent endpoints; can be degraded for other endpoints |
| HTTP query service using Kafka only for auxiliary telemetry | API can still serve queries | Can stay `UP` if degraded mode is acceptable |
| Command service using DB + outbox | Can write business state and outbox events even while broker is temporarily unavailable | Can stay `UP` if outbox backlog is bounded and requirements allow eventual publish |
| Kafka Streams application | Processing topology depends on cluster | `DOWN` when topology cannot fulfill its task per policy |
| Multi-cluster application | One cluster fails, another cluster keeps working | Readiness per capability/service route, not necessarily global `DOWN` |

In particular, with a **transactional outbox**, the database can continue writing business state and event intents while Kafka is temporarily unavailable. If this is an intentional degraded mode and the outbox has a quota/backlog policy, the application may remain ready for certain APIs. However, the relay cannot publish yet and needs clear metrics/alerts.

Readiness should not mirror dependency availability mechanically; it must reflect **the ability to fulfill the service's contract**.

## 32. Broker outages and consumer retry behavior

Kafka consumers have built-in client reconnect/network retry mechanisms. When brokers are unavailable:

~~~text
Spring Kafka container
       |
       v
consumer.poll()
       |
       v
network / metadata failure
       |
       v
Kafka client reconnects/retries per configuration
       |
       +-- broker not ready -> continues failing
       |
       +-- broker recovers -> poll/metadata succeeds
                              |
                              v
                        group join/assignment
~~~

Do not stop and start the listener container every time a health probe returns `DOWN`. Doing so can reset client state and cause extra group membership churn.

If the container remains running and the Kafka client reconnects on its own, the readiness indicator only needs to reflect dependency state. When the broker recovers, the consumer can automatically regain its assignment.

If the container has stopped due to a fatal error, health logic must distinguish a stopped container from unavailable broker metadata; broker reconnection alone will not restart a stopped container.

## 33. Readiness when a topic has not been created yet

A service may connect to brokers successfully while the listener's topic has not been provisioned yet:

~~~text
Broker UP
  |
  v
AdminClient describeCluster -> success
  |
  v
orders.commands does not exist
  |
  v
Listener cannot consume topic yet
~~~

If the topic is a mandatory dependency, readiness should be `DOWN` with category **topic_missing** or **listener_not_assigned**, instead of returning `UP` merely because the broker is reachable.

Topic metadata can be checked using `AdminClient` or based on provisioning/assignment state. Distinguish missing topics from topic authorization denied; some ACL restrictions can prevent metadata lookup from verifying the resource as expected.

Do not auto-create all topics from a health probe. Provisioning is a separate responsibility with controlled partition count, replication factor, retention, and ACLs.

## 34. Readiness when the consumer group has no assignment

A consumer group may have no partition assignment because:

- The consumer just started and is waiting for a rebalance.
- The topic has no partitions yet or is missing.
- The group protocol/coordinator is recovering.
- Replica count exceeds partition count, so some instances receive no partitions.
- Group/topic ACLs are incorrect.
- The consumer container has stopped or is paused.

For a worker that must actively process records, readiness may require **child consumer assignments**. However, the policy must account for legitimate zero-partition cases caused by topology.

Do not mark readiness `DOWN` simply because one pod has no assignment if:

- The service is scaled higher than the partition count.
- Some consumer replicas are allowed to be idle.
- Listener subscriptions span multiple topics with uneven partition distribution.

In such systems, readiness can rely on **group-level coverage** or verifying container lifecycle and broker health, rather than requiring every pod to own at least one partition.

## 35. Pause and readiness

A paused consumer can still maintain group membership and poll. Readiness can be interpreted in two ways:

- **Infrastructure ready**: broker/consumer are alive; pause is only a temporary throttling state.
- **Processing ready**: the listener can accept and process new records right now.

If a backpressure controller intentionally pauses the container, readiness does not necessarily have to go `DOWN`. If paused because a business dependency cannot process work, readiness may go `DOWN` depending on the service contract.

~~~text
Broker UP
Consumer assigned
Database overloaded
Container paused

Infrastructure readiness = UP
Business processing readiness = DOWN
~~~

Do not rely on a single boolean if dashboards and Kubernetes need to distinguish both aspects. However, Kubernetes only uses a single readiness result for that endpoint; decide which state is meaningful for the traffic that the Service routes.

## 36. Health checks should not send business messages

One way people try to test producers is publishing a test record to a business topic on every readiness probe. This is dangerous:

- Business consumers may process the synthetic message.
- Canary records inflate traffic/lag.
- Retry/DLT topics may end up holding canaries.
- Transactional producers can create transaction coordinator load.
- If keys collide, canaries can affect ordering.

If an end-to-end canary is needed:

1. Use a dedicated topic.
2. Use a dedicated message type and confirming consumer.
3. Include a unique canary ID only in logs/traces.
4. Do not use canary IDs as metric tags.
5. Run on a longer interval than readiness probes.
6. Set retention and cleanup.
7. Separate canary health from business traffic.

`AdminClient.describeCluster` is suitable for metadata reachability. Canaries are suitable for testing the **end-to-end publish/consume path**, but must be designed as an active testing system rather than a lightweight zero-impact probe.

## 37. Health endpoints must not expose security details

Do not return:

~~~json
{
  "status": "DOWN",
  "error": "SASL authentication failed using username=...",
  "bootstrapServers": "internal-broker-secret...",
  "jaasConfig": "..."
}
~~~

A safer response:

~~~json
{
  "status": "DOWN",
  "components": {
    "kafkaBroker": {
      "status": "DOWN",
      "details": {
        "errorCategory": "authentication",
        "lastProbeAt": "2026-11-15T10:00:00Z"
      }
    }
  }
}
~~~

This response is an example schema; the actual structure depends on Actuator health groups and `show-details` policy.

Recommendations:

- Do not expose health details to Internet users.
- Configure management endpoint `show-details` according to security policy.
- Do not include JAAS configs, passwords, tokens, internal broker hostnames, or full exception messages in responses.
- Restrict network access to Actuator.
- Use redacted internal logs to investigate detailed root causes.

## 38. Monitoring readiness and Kafka metrics

Readiness only indicates whether a pod is marked ready. Understanding the cause requires additional metrics/logs:

- Broker probe success/failure counts.
- Probe latency and timeout counts.
- Last successful probe age.
- Consumer container running/stopped state.
- Consumer assignment count or partition coverage.
- Consumer lag.
- Rebalance count/duration.
- Authentication/authorization errors.
- Producer send/transaction failures.
- Outbox backlog, if applicable.
- Pause duration and in-flight processing if backpressure is active.

A structured log:

~~~text
event=readiness_changed
service=orders-service
previous=UP
current=DOWN
reason=kafka_metadata_timeout
probe_latency_ms=2000
last_success_age_seconds=45
~~~

Do not log an `ERROR` on every failed probe if Kubernetes calls the probe every few seconds. Log on state transitions, rate-limit repeated failures, and use metrics to track probe counts.

Readiness state transitions help operators see when pods leave Service endpoints and when they recover.

## 39. Alerting when readiness is DOWN

Useful alerts:

| Alert | Meaning |
|---|---|
| Kafka readiness down across multiple replicas | Widespread broker/cluster/network outage |
| Readiness down on a single pod | Local DNS, network, credentials, or instance issue |
| Rising broker probe latency | Cluster/network degradation prior to an outage |
| Consumer assignment fails to recover | Group/ACL/topic/consumer lifecycle issue |
| Consumer lag rising while readiness is `UP` | Slow consumer or overly loose readiness policy |
| Readiness `UP` while producer errors rise | Broker metadata OK, but produce path/ACL/transaction failing |
| Readiness flapping | Overly sensitive threshold/timeout or unstable cluster |
| Rising outbox backlog | Broker unavailable or relay unable to publish |

Do not alert on a single probe timeout alone. Use duration/thresholds and correlate with Kafka broker metrics.

For consumer-only services, readiness `DOWN` may not stop Kafka listeners from consuming. If that matters, alert on and control the container separately.

## 40. Diagnosing a NotReady pod when brokers appear healthy

A procedure:

1. Check the readiness endpoint and which contributor returned `DOWN`.
2. Inspect the error category: network, authentication, authorization, metadata timeout, or topic missing.
3. Verify bootstrap servers and DNS resolution from inside the exact pod.
4. Check TLS/SASL configuration and credential rotation.
5. Confirm `AdminClient` has permission to describe the cluster.
6. Check consumer group/topic ACLs separately; broker health does not prove consumer permissions.
7. Check listener container `isRunning` and stopped event states.
8. Check partition assignment/rebalances.
9. Verify topic existence, partition count, and metadata.
10. If producer-only, check produce ACLs and the transaction coordinator.
11. Compare probe timeout against broker/client request timeouts.
12. Determine whether probe flapping or stale cached state is occurring.

Do not "fix" readiness by hardcoding `UP` when the endpoint reports `DOWN`. Fix the root cause or adjust the policy based on the business contract.

## 41. Diagnosing a Ready pod that is not consuming

If a pod is Ready yet not processing Kafka records:

- The health indicator may only check `AdminClient` metadata.
- The listener container may not have started or may have stopped.
- The consumer group may not have assigned partitions yet.
- Topic subscription may be incorrect.
- The consumer is paused.
- Group offsets are at the end of the log or the topic has no data.
- Deserialization or authorization may be failing on the separate consumer path.
- The listener may be blocked/non-responsive.

This is why **broker readiness does not mean consumer readiness**. A consumer service may need an additional readiness contributor to confirm listener assignment or processing state.

Do not use zero consumer lag as proof of a healthy listener: the topic may have no data, or the consumer may have never received an assignment.

## 42. Readiness during rolling deployments

In a rolling deployment, the new pod must become ready before the old pod is terminated if disruption is to be minimized:

~~~text
Pod A (old) -> Ready, consumes
Pod B (new) -> Starting, broker unavailable

Readiness B = DOWN
Pod A remains active

Kafka recovers
Pod B -> broker reachable
Pod B -> group assigned
Readiness B = UP

Pod A graceful shutdown
Group rebalance
Pod B continues
~~~

If readiness B only checks the HTTP server without considering Kafka, the deployment controller can treat the new pod as ready too early. If readiness requires full group assignment while a valid new pod receives no partitions due to group topology, rollouts can become blocked.

Choose a readiness gate that fits the service role and configure `maxUnavailable`, `maxSurge`, termination grace period, and consumer group behavior coherently.

Do not require every new pod to own all partitions; group assignment is distributed across the group.

## 43. Readiness with transactional producers

With transactional producers, a successful metadata probe is not enough to prove transactions work.

~~~text
AdminClient describeCluster -> UP

KafkaTemplate producer:
  initTransactions -> failure
  or send/commit -> ProducerFencedException

Business event publish:
  not ready
~~~

If transactions are mandatory, readiness must reflect transactional publishing capability according to an appropriate policy.

Do not initialize and commit a Kafka transaction on every probe. Instead:

- Track producer initialization/transaction failures.
- Ensure `transactional.id` does not collide across active instances.
- Handle fencing and container/producer lifecycles properly.
- Use a separate transaction canary if end-to-end verification is needed.
- Only change readiness on sufficiently reliable state, not a single stale error log.

## 44. Readiness when brokers recover before consumers stabilize

Brokers can respond to metadata requests before a consumer group finishes rebalancing or listeners begin receiving partitions:

~~~text
Broker probe -> UP
      |
      v
Consumer reconnect
      |
      v
Group join/rebalance
      |
      v
Partitions assigned
      |
      v
Listener processing resumes
~~~

If the service must consume to perform its primary role, mark it ready only after the appropriate assignment condition is met.

However, if a consumer group has many members and a pod is legitimately assigned 0 partitions, do not force that pod to wait forever. Choose a policy based on instance role or group-level assignment.

A grace period after broker recovery can prevent flapping while the group is still rebalancing, but it must have an upper bound and alert if assignment never completes.

## 45. Readiness and database dependencies

A consumer service may be connected to Kafka while its database is not ready:

~~~text
Kafka broker -> UP
Database -> DOWN
Consumer group -> ASSIGNED
Listener -> cannot write business state
~~~

If the listener continues consuming and the listener method throws exceptions, the error handler can retry. However, infinite retries or long blocking retries can accumulate partition lag and delay other records.

A policy can:

- Mark readiness `DOWN` when the database is a mandatory dependency.
- Pause the consumer when the database is overloaded to avoid pulling more work.
- Maintain consumer group membership during brief outages.
- Resume when the database recovers.
- Use outbox/idempotency for side effects and event publication.

Do not just include `kafkaBroker` in readiness and assume the entire service is healthy. **Readiness must cover the dependencies actually required on the business path.**

## 46. Readiness and the transactional outbox

With a transactional outbox, an API can write business state together with an outbox event in a single DB transaction even when Kafka is temporarily unavailable:

~~~text
HTTP command
    |
    v
DB transaction:
  update orders
  insert outbox event
    |
    v
DB commit
    |
    v
Outbox relay
    |
    +-- Kafka unavailable -> backlog grows
    |
    +-- Kafka recovered -> publish backlog
~~~

In this architecture, a Kafka outage does not necessarily make the entire HTTP API NotReady immediately. If the database has capacity and the outbox backlog is below limits, the API can keep accepting commands under an eventual consistency contract.

Readiness must check:

- Database ready.
- Outbox storage writable.
- Outbox backlog/oldest event age within limits.
- Relay state monitored.
- Disk/database capacity sufficient for the expected outage window.

If the backlog exceeds a hard limit or event age exceeds business SLA, readiness/traffic policies can transition to degraded or `DOWN`.

Do not stay `UP` indefinitely while the outbox backlog grows without bound; eventual consistency still needs a budget.

## 47. Avoiding restart storms and rebalance storms

Poor probe design can trigger this chain:

~~~text
Kafka broker outage
   |
   v
Liveness probe fails
   |
   v
Kubernetes restarts all pods
   |
   v
Consumers leave group
   |
   v
Broker recovers
   |
   v
All pods reconnect simultaneously
   |
   v
Group rebalances and transaction initialization spike
   |
   v
Recovery is slower
~~~

To avoid this:

1. Do not put broker availability into liveness.
2. Use readiness to remove pods from HTTP Services when needed.
3. Let Kafka clients reconnect with backoff.
4. Use a startup probe generous enough for startup time.
5. Avoid restarting/stopping-and-starting listeners on every probe failure.
6. Use proper rollout strategies and graceful shutdown.
7. Monitor consumer group rebalances and connection rates when brokers recover.

If listeners must be paused due to a business dependency, use pause/resume with hysteresis; do not restart pods to shed load.

## 48. Testing broker unavailability

Use a real test Kafka broker such as **Testcontainers Kafka** or an integration environment where brokers can be stopped and started in a controlled way.

### Test 1: broker not ready at application startup

1. Start the Spring Boot application while the broker is not running.
2. Verify the application context/HTTP management endpoints can start per policy.
3. Verify readiness is `DOWN` or `UNKNOWN`.
4. Verify liveness is `UP`.
5. Verify the pod is not instructed to restart solely because of the Kafka outage.
6. Start the broker.
7. Wait for readiness to transition to `UP` per defined thresholds.

### Test 2: broker loses connectivity after service is ready

1. Wait for the application and consumer group to be ready.
2. Stop the broker or block network access.
3. Verify readiness transitions to `DOWN` after the threshold.
4. Verify liveness remains `UP`.
5. Check Kafka client reconnect attempts and container state.
6. Restore the broker.
7. Verify the consumer regains assignment and readiness returns `UP`.

### Test 3: broker reachable but topic missing

1. Start the broker.
2. Do not create the required topic.
3. Verify the broker metadata probe is `UP`.
4. Verify listener readiness is `DOWN` if policy requires topic/assignment.
5. Create the topic with the right configuration.
6. Verify listener readiness recovers.

### Test 4: authentication/authorization failure

1. Misconfigure SASL credentials or ACLs in the test.
2. Verify health state classifies authentication/authorization.
3. Verify liveness is not pulled `DOWN`.
4. Restore valid credentials/ACLs.
5. Verify retry/reconnect and readiness recovery per policy.

### Test 5: metadata UP but consumer unassigned

1. Allow `AdminClient.describeCluster` to succeed.
2. Keep the consumer group in an unassigned state (e.g., via test-appropriate topic/ACL/subscription).
3. Verify broker health is `UP` while consumer assignment readiness is not `UP`.
4. Fix the group/topic condition.
5. Verify the assignment tracker updates properly.

### Test 6: readiness flapping

1. Simulate a single brief probe timeout.
2. Verify the threshold does not transition to `DOWN` if policy requires multiple failures.
3. Simulate multiple consecutive failures.
4. Verify `DOWN`.
5. Simulate a single success.
6. Verify it stays `DOWN` until enough recovery successes occur.

### Test 7: probe timeout

1. Prevent the `AdminClient` request from completing within the timeout.
2. Verify the health endpoint responds within a bounded time.
3. Verify an interrupted thread restores its interrupt flag.
4. Verify a new `AdminClient` is not created on every request.
5. Verify scheduled probes do not overlap unboundedly.

### Test 8: transactional producer not ready

1. Allow the broker metadata probe to succeed.
2. Configure a failing producer transaction (e.g., transactional ID conflict or coordinator issue).
3. Verify broker readiness is not mistaken for transaction readiness.
4. Check transaction error metrics/logs and additional readiness policy if needed.
5. Restore the producer lifecycle.

## 49. Testing with Kubernetes probes

In integration/deployment tests:

1. Deploy the application before Kafka or simulate broker unavailability.
2. Observe startup probe, readiness, and liveness separately.
3. Verify liveness does not repeatedly restart pods when the broker is down.
4. Verify readiness removes the pod from HTTP Service endpoints if required by policy.
5. Check whether consumer listeners continue or pause according to their own policy.
6. Restore the broker and verify the pod returns to Ready.
7. Monitor consumer group rebalances/lag during recovery.

Do not check only the HTTP response status. Inspect the **Kubernetes pod Ready condition**, restart count, and Service endpoints to confirm probes behave as expected.

## 50. Common misconceptions

**ApplicationContext started means Kafka is ready.** False. Spring beans can be created before brokers are reachable or consumer groups are assigned.

**Kafka broker unavailable must fail liveness.** False in most systems; brokers are dependencies outside the process.

**Readiness DOWN automatically stops Kafka listeners.** False. Kubernetes readiness primarily affects Service routing; listener containers can keep consuming.

**AdminClient.describeCluster succeeding proves producer and consumer are ready.** False. It does not prove topic/group ACLs, assignments, or transactional publishing.

**container.isRunning() means the consumer has partitions.** False. Running is lifecycle state; assignment is group state.

**Consumer group assignment must have all partitions on every pod.** False. Partitions are distributed across group members.

**One health check timeout means the broker is definitely DOWN.** Not necessarily. It could be network jitter, request timeout, or thread blocking; thresholds and categories are needed.

**Creating an AdminClient on every health check is simple and safe.** Bad practice. It can cause connection churn and increase load during broker outages.

**Readiness should fail immediately after one timeout.** Depends on SLO. A single failure can be transient; hysteresis is needed without hiding prolonged outages.

**Broker UP means the topic exists.** False. Topic provisioning is a separate condition.

**Broker UP means the consumer group is assigned.** False. Group membership/rebalancing is a separate lifecycle.

**Paused consumer must mean readiness DOWN.** Not necessarily. Pausing can be intentional backpressure; distinguish infrastructure readiness from processing readiness.

**Readiness UP guarantees successful business processing.** False. Dependencies can fail after the probe or side effects can fail.

**When brokers recover, the application must be restarted.** Unnecessary if consumer/producer clients are still active and can reconnect through their lifecycle.

**Transactional outbox must still mark readiness DOWN whenever Kafka is down.** Not necessarily. If the contract permits writing to the outbox and backlog is within bounds, some APIs can continue serving.

## 51. Production rollout procedure

To design readiness when Kafka brokers are not ready:

1. Identify the service role: consumer, producer, combined API, Kafka Streams, or outbox relay.
2. Clearly define what **ready** means in terms of fulfillable business contracts.
3. Separate readiness, liveness, and startup probes.
4. Do not put broker availability into liveness if the process is healthy and can wait for dependencies.
5. Enable Spring Boot Actuator health probes and configure the readiness group intentionally.
6. Use a long-lived managed `AdminClient` to check broker metadata with finite timeouts.
7. Keep state `UNKNOWN`/NOT READY until reliable probe successes occur.
8. Use consecutive failure/success thresholds and stale-result timeouts to avoid flapping.
9. For consumer services, add assignment readiness aligned with group topology if business requires assigned partitions before becoming ready.
10. Do not use `isRunning()` as proof of consumer assignment or transactional producer health.
11. Classify network, authentication, authorization, missing topic, and transaction failures.
12. Do not restart listeners/pods on every readiness failure; let Kafka clients reconnect and restart only when lifecycle genuinely requires it.
13. If record intake must stop due to backpressure, control container pause/resume separately; readiness does not do this automatically.
14. If using an outbox, set backlog/age limits for degraded mode.
15. Never let health endpoints leak credentials, exception messages, or sensitive broker configuration.
16. Monitor readiness transitions, probe latency, assignments, consumer lag, rebalances, and transaction errors.
17. Test broker startup delays, outages, recovery, missing topics, ACL failures, unassigned consumers, and Kubernetes restart behavior.

**Readiness when brokers are not ready** is a question of service capability, not a simple check of whether a process has opened an HTTP port. Spring Boot Actuator and Kafka `AdminClient` help observe broker connectivity, while consumer assignments and producer transactions need dedicated signals when mandatory. When Kafka is unavailable, an application can stay alive and wait to reconnect; **readiness should reflect whether an instance can safely accept work, while liveness continues to reflect the internal health of the process**. This separation helps Kubernetes avoid restart storms, prevents unnecessary consumer group churn, and lets the system recover cleanly when brokers return.
