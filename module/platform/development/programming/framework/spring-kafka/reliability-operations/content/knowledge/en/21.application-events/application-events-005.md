# ConsumerRetryAuthSuccessfulEvent

`ConsumerRetryAuthSuccessfulEvent` is a **Spring Kafka application event** published when a Kafka consumer **has successfully called `poll()` again after having to retry due to an authentication or authorization error**. This is a useful signal for recording that the process of retrying Kafka read operations after a security error has passed a recovery milestone.

This event is especially important in long-running systems: tokens can expire and then be refreshed, ACLs can be fixed, or brokers/authentication services can be temporarily unavailable. If the listener container is configured to retry authentication/authorization errors rather than stop immediately, the application needs to know **when a retry poll has succeeded** in order to close alerts, evaluate consumer health, and continue tracking backlog.

However, `ConsumerRetryAuthSuccessfulEvent` **is not a signal that a business record has been processed successfully**. A `poll()` call may return zero records; offsets may not have advanced yet; the consumer group may have just rebalanced; and an authorization issue on a producer, DLT, or external service may still exist. The event must be placed within the full Kafka consumer cycle rather than interpreted as certification that the application is completely healthy.

## 1. Context: consumer poll encounters an authentication or authorization error

A Kafka consumer must connect to the broker, authenticate its identity, and be granted permissions on the resources it uses. When a security step related to reading fails, the Kafka client can throw exceptions such as:

- `AuthenticationException`: authentication failure, potentially involving SASL, tokens, or security mechanisms.
- `AuthorizationException`: authorization failure, such as lacking permission to read a topic or join a consumer group according to ACLs.
- Specific subtypes emitted by the Kafka client/broker depending on version and protocol.

If the listener container has no retry mechanism configured for these exceptions, the consumer can stop and publish the corresponding lifecycle event, such as `ConsumerStoppedEvent` with an `AUTH`-related reason in supported versions.

Spring Kafka provides the container property `authExceptionRetryInterval`. When configured in supported versions, the listener container can **wait and try `poll()` again** after encountering `AuthenticationException` or `AuthorizationException`.

During that process, two events are easily confused with each other:

| Event | Timing | Meaning |
|---|---|---|
| `ConsumerRetryAuthEvent` | Container is preparing to retry after an authentication/authorization error | Consumer is still in the error/waiting-to-retry phase. |
| **`ConsumerRetryAuthSuccessfulEvent`** | **A `poll()` call after the retry phase succeeds** | **Consumer has cleared a poll attempt previously blocked by an auth error.** |
| `ConsumerStoppedEvent` | Consumer stops, possibly due to auth or another error | A consumer lifecycle has ended; not a recovery event. |
| `ConsumerStartedEvent` | Consumer begins a lifecycle | Does not guarantee subsequent polls will succeed or return data. |

Not every auth error leads to `ConsumerRetryAuthSuccessfulEvent`. If retry is not enabled, the consumer stopped, the error is unrecoverable, or the application shuts down before a poll succeeds, the recovery event will not appear.

## 2. Auth retry flow and when the success event is published

Suppose a service reads the topic `payments.events`. While the consumer is running steadily, the broker rejects a poll because credentials temporarily become invalid. The container is configured to retry auth with a set wait interval.

~~~mermaid
sequenceDiagram
    participant L as Spring Kafka Listener Container
    participant C as Kafka Consumer
    participant B as Kafka Broker / Security
    participant E as Application Event Observer
    L->>C: poll()
    C->>B: Fetch / group operation
    B-->>C: Authentication/Authorization error
    C-->>L: AuthenticationException / AuthorizationException
    L->>E: ConsumerRetryAuthEvent
    Note over L: Wait authExceptionRetryInterval
    L->>C: retry poll()
    C->>B: Fetch / group operation
    alt Access permission still failing
        B-->>C: Authentication/Authorization error
        C-->>L: Exception
        L->>E: ConsumerRetryAuthEvent
        Note over L: Continue backoff/retry per lifecycle
    else Poll succeeds
        B-->>C: Poll succeeds, possibly with no records
        C-->>L: ConsumerRecords
        L->>E: ConsumerRetryAuthSuccessfulEvent
        L->>L: Continue listener processing loop
    end
~~~

Key points to remember:

1. `ConsumerRetryAuthEvent` represents **the retry moment**, not recovery.
2. `ConsumerRetryAuthSuccessfulEvent` marks **a successful poll after auth retry**.
3. The recovery event does not mean a record was just deserialized, processed, or committed successfully.
4. After success, the Kafka consumer may still have to handle assignment/rebalance or resume from the appropriate committed offset.
5. If the auth error recurs later, a new retry cycle can begin.

Recovery can occur when poll returns **0 records**. Therefore, if a dashboard wants to show that the business flow is operating again, it must combine this with metrics for record consumption, listener success, commits, and lag.

## 3. Exact scope of ConsumerRetryAuthSuccessfulEvent

This event relates to **a Kafka consumer poll failing due to authentication/authorization and then retrying successfully**. It is not a generic callback for all retry types in Spring Kafka.

Cases that **should not be inferred** from the event:

- The listener hit a business exception and `DefaultErrorHandler` retried successfully.
- `@RetryableTopic` routed records between retry topics.
- `DeadLetterPublishingRecoverer` sent a failing record to the DLT.
- The Kafka producer retried a failed `send()`.
- `KafkaTemplate` completed a Kafka transaction.
- The database reconnected successfully.
- An HTTP client refreshed a token used for an external service.
- Another consumer in the same group recovered.

The mechanisms above have their own logging/metrics or events. Do not increment a "business retry recovered" counter solely because a `ConsumerRetryAuthSuccessfulEvent` appeared.

### Poll success differs from processing success

This can be illustrated across stages:

~~~text
Consumer has permission to connect/poll:
  poll() succeeds
          |
          v
Consumer is assigned partitions:
  has assignment, may currently be empty
          |
          v
Consumer fetches records:
  receives ConsumerRecords
          |
          v
Listener processes business logic:
  may succeed or throw an exception
          |
          v
Offset commit/recovery:
  depends on AckMode, transaction, error handler
~~~

`ConsumerRetryAuthSuccessfulEvent` only provides a signal at **the poll recovery step**. Remaining steps must be verified independently.

## 4. Conditions for Spring Kafka to retry auth

The `authExceptionRetryInterval` property resides on **listener container properties**; it is not a Kafka broker parameter and is not in the same category as Kafka producer `retries`.

In principle:

- When an appropriate retry interval is configured, Spring Kafka can retry `AuthenticationException`/`AuthorizationException` raised on the consumer's poll path.
- Each preparation for a retry can emit `ConsumerRetryAuthEvent` for application observation.
- After a successful poll in this sequence, the container publishes `ConsumerRetryAuthSuccessfulEvent`.
- If the application requests stop or the error cannot continue, the lifecycle flow may terminate instead of publishing the success event.

Do not set the retry interval too small, causing the consumer to send thousands of futile requests while broker ACLs/credentials have not yet been fixed. Conversely, retrying for too long or blocking the poll loop inappropriately can cause consumer group membership issues.

### Configuring via ConcurrentKafkaListenerContainerFactory

A Spring Kafka example using a dedicated container factory:

~~~java
@Configuration
public class KafkaListenerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, PaymentEvent>
    paymentKafkaListenerContainerFactory(
            ConsumerFactory<String, PaymentEvent> consumerFactory) {

        ConcurrentKafkaListenerContainerFactory<String, PaymentEvent> factory =
                new ConcurrentKafkaListenerContainerFactory<>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties().setAuthExceptionRetryInterval(
                Duration.ofSeconds(15));

        return factory;
    }
}
~~~

This example demonstrates setting a 15-second retry interval on container properties. `PaymentEvent` is an application-defined data type. Imports such as `Duration`, `ConcurrentKafkaListenerContainerFactory`, and `ConsumerFactory` should be added according to your project.

Listener using the factory:

~~~java
@KafkaListener(
        topics = "payments.events",
        groupId = "payment-service",
        containerFactory = "paymentKafkaListenerContainerFactory")
public void onPayment(PaymentEvent event) {
    paymentService.processIdempotently(event);
}
~~~

The 15-second value is illustrative only. In production, choose the retry interval according to authentication service characteristics, SLAs, and consumer group timing allowances. Setter APIs and behavior can vary by Spring Kafka version; verify `authExceptionRetryInterval` exists and accepts `Duration` in the version in use.

### Do not misconfigure on the Kafka client

The following **is not** a standard Kafka consumer property:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        authExceptionRetryInterval: 15000
~~~

Declaring an arbitrary property name inside the Kafka consumer properties map does not guarantee the Spring Kafka container will use it. Configure container properties via a mechanism supported by your project's Spring Kafka/Spring Boot version, such as factory customization.

Properties such as `security.protocol`, `sasl.mechanism`, JAAS, TLS, OAuth, and topic/group ACLs must still be configured properly. `authExceptionRetryInterval` only controls **retrying**; it does not replace security policies.

## 5. Registering @EventListener for the recovery event

Because `ConsumerRetryAuthSuccessfulEvent` is a Spring application event, the application can listen for it using `@EventListener`:

~~~java
@Component
public class KafkaAuthRecoveryObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaAuthRecoveryObserver.class);

    @EventListener
    public void onAuthRetrySuccess(
            ConsumerRetryAuthSuccessfulEvent event) {

        log.info(
                "Kafka consumer auth retry recovered; sourceType={}",
                event.getSource().getClass().getSimpleName());
    }
}
~~~

Key imports include:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerRetryAuthSuccessfulEvent;
import org.springframework.stereotype.Component;
~~~

This handler is straightforward: receive the event and log it to prove a recovery poll occurred. When multiple instances/child consumers run concurrently, logs should include application instance, listener ID, client ID, or container ID if provided by the current API and context.

### Combining retry and recovery events

An observer can register two methods:

~~~java
@Component
public class KafkaAuthEventObserver {

    private static final Logger log =
            LoggerFactory.getLogger(KafkaAuthEventObserver.class);

    @EventListener
    public void onAuthRetry(ConsumerRetryAuthEvent event) {
        log.warn("Kafka consumer is retrying after auth-related failure");
    }

    @EventListener
    public void onAuthRecovered(
            ConsumerRetryAuthSuccessfulEvent event) {
        log.info("Kafka consumer poll succeeded after auth retry");
    }
}
~~~

The snippet avoids relying on fields not supported across all versions. In versions that provide a reason on `ConsumerRetryAuthEvent`, the authentication/authorization classification can enrich logs and metrics. Do not assume `ConsumerRetryAuthSuccessfulEvent` contains the full root exception or a `getReason()` like the retry event.

### Meaning of the event source

`getSource()` is the source per Spring's `ApplicationEvent` mechanism. It is useful for associating the observer with the container that published the event, but you should not store the entire source object into a long-lived monitoring queue. Doing so can retain references to container/consumer lifecycles, increase memory usage, and complicate serialization.

Instead, **extract the necessary metadata** into a simple record if it needs to be forwarded to logging, metrics, or a notification service.

## 6. Is the event published synchronously or asynchronously?

Spring application events are normally published synchronously via `ApplicationEventMulticaster` by default. Within Spring Kafka's lifecycle, the observer may run on a consumer/container-related thread.

This leads to an operational requirement: **the handler must be lightweight and must not block the poll loop**.

Do not:

- Call `Thread.sleep` for several seconds waiting for other components.
- Make database/network I/O calls without timeouts.
- Synchronously reload all secrets/certificates inside the callback.
- Execute a slow HTTP notification directly on the consumer thread.
- Call `KafkaConsumer.poll()` or `commitSync()` from the event listener.
- Arbitrarily `start()`, `stop()`, or `seek()` the container without checking lifecycle state.

If you need to notify an external system, pass a small DTO to an appropriate executor/queue; do not pass the consumer reference to a background thread. `KafkaConsumer` is generally not thread-safe.

If the application configures an asynchronous multicaster, the event observer may run on a different thread. In that case, do not assume callback ordering or thread-local context matches synchronous publication. Use explicit timestamps and correlation metadata when building incident timelines.

## 7. One recovery event does not mean authentication is "permanently cured"

A single successful poll only proves the state at **that point in time**. The following situations can still occur:

- An OAuth token was refreshed but expires again in the next cycle.
- An ACL was just granted but is revoked shortly afterward.
- Another broker in the cluster still has skewed config or an unstable authentication service.
- The consumer polled successfully, yet the producer sending to the DLT lacks permissions.
- The source topic has read permission, yet another topic used by the same application lacks permission.
- The consumer can poll, yet the listener fails to process records due to schema or database errors.
- The consumer group is rebalancing so record processing does not resume immediately.

Therefore, do not use `ConsumerRetryAuthSuccessfulEvent` as proof that the entire service is unconditionally "healthy." Treat it as a **per-consumer recovery signal**, combined with other readiness/health conditions.

### Readiness and liveness

- **Liveness:** whether the process is still alive and capable of continuing service/recovery as designed.
- **Readiness:** whether the instance is currently ready to receive and process workload as expected.
- **Auth retry success:** a consumer that hit an auth error has now succeeded in one poll.

These three are not completely equivalent. When tuning Kubernetes probes, avoid configuring liveness to repeatedly kill pods solely due to a temporary authentication outage that the container is already designed to retry. At the same time, readiness should not be marked healthy solely from one event if the listener remains paused, lacks assignments, or backlog continues growing.

## 8. ConsumerRetryAuthEvent and distinguishing authentication/authorization

`ConsumerRetryAuthEvent` is the signal emitted when the consumer is retrying due to one of the two security error groups. Authentication and authorization have different causes.

| Group | Possible symptoms | Investigation |
|---|---|---|
| Authentication | Broker rejects identity; invalid SASL/OAuth/TLS handshake or token | Secrets, certificates, token refresh, clock skew, JAAS, SASL mechanism. |
| Authorization | Client authenticates but lacks permission to use topic/group | Kafka ACLs, principal mapping, READ/DESCRIBE permissions, and group access. |
| Transient broker/security service issue | Auth fails once and succeeds after external system recovers | Broker logs, identity provider availability, retry timing. |
| Client configuration change | Every poll keeps failing after deployment | Effective config, environment, and secret mounts. |

Depending on version, `ConsumerRetryAuthEvent` can provide a reason classification to separate the two groups above. For `ConsumerRetryAuthSuccessfulEvent`, correlate the success event with preceding failure events on the same consumer/container to know **which failure group it recovered from**.

### When is retry useful?

Retry is generally useful when:

- A token can be refreshed automatically.
- ACLs are being updated as part of an approved change.
- The Kafka broker or authentication system is experiencing a transient glitch.
- Secret rotation has a proper reload/reconnect mechanism.
- Access permissions are granted after the service starts.

Retry may **not** be sufficient when:

- A password is permanently wrong in configuration.
- The client lacks a role/ACL and no process is restoring permissions.
- A certificate expired and the client cannot reload it.
- The topic/group is blocked by long-term policy.
- Producer or DLT permissions differ from consumer permissions, while the event only reflects a consumer poll.

Do not increase retry frequency to "fix" an unchanging configuration cause.

## 9. authExceptionRetryInterval and max.poll.interval.ms

A Kafka consumer needs to call `poll()` often enough to maintain group progress. `max.poll.interval.ms` sets the maximum time allowed between polls under consumer group mechanics; `session.timeout.ms` and heartbeats relate to detecting inactive members.

When designing auth retry, control:

- The `authExceptionRetryInterval` wait between retries.
- The duration of one failing `poll()`/network request.
- Listener/callback processing time before the poll loop returns.
- Consumer group limits such as `max.poll.interval.ms`.
- Session timeout, static membership, and rebalances if the outage drags on.
- Shutdown responsiveness: the consumer must be able to stop when the application is asked to stop.

A retry interval shorter than `max.poll.interval.ms` is usually a necessary condition to avoid holding the consumer thread too long; it is **not sufficient** if each poll or other work already consumes nearly the entire time budget.

### Timing example

~~~text
max.poll.interval.ms = 300000  (5 minutes)
authExceptionRetryInterval = 15000  (15 seconds)

T0: poll -> AuthorizationException
T1: publish ConsumerRetryAuthEvent
T2: wait retry interval
T3: next poll -> AuthorizationException
T4: retry again
T5: ACL fixed
T6: poll succeeds -> ConsumerRetryAuthSuccessfulEvent
~~~

If an outage lasts 20 minutes, the coordinator may already consider the consumer to have lost membership or trigger a rebalance depending on group protocol and client lifecycle. A subsequent success event does not guarantee the consumer still holds its old assignment or that no records were redelivered.

### Retry interval is not a recovery SLA

If retry is configured every 15 seconds, actual recovery time is not guaranteed to be exactly 15 seconds. Other factors include network, DNS, broker availability, authentication mechanism, metadata refresh, scheduling, group join, and application readiness to process records.

Set SLAs based on actual measurements, not just the interval value.

## 10. Relationship with consumer groups, rebalances, and offsets

Authentication/authorization errors can affect group joining, record fetching, and related client operations. By the time a consumer retries successfully, partition ownership may have changed.

Example:

~~~text
Before incident:
  Consumer A -> Partition 0, 1
  Consumer B -> Partition 2, 3

During auth outage:
  A fails to poll successfully for a long period
  Group may rebalance

After poll succeeds:
  A may receive a different assignment
  Committed offset determines the corresponding read point
~~~

Do not use `ConsumerRetryAuthSuccessfulEvent` to manually commit a new offset or seek to the end of the topic. The event contains no business proof that all preceding records have been processed.

### When records are redelivered

Suppose a consumer updated the database without committing the offset before hitting an auth outage:

1. The database update succeeded.
2. The consumer did not commit the source offset.
3. Group membership changed or the consumer restarted.
4. A valid member reads the record again from the previous committed offset.
5. The same business event may execute a second time.

Idempotency is needed, such as a stable event ID and a unique constraint/inbox in the database transaction. The auth recovery event cannot eliminate this duplicate window.

### Offset commit after recovery

After a successful poll, the listener container continues processing according to `AckMode` or Kafka transactions. Only when records are processed/recovered per policy is the offset allowed to advance.

Do not call `Acknowledgment.acknowledge()` or `commitSync()` from an auth recovery observer. The observer does not own the record-processing lifecycle and may run on a different thread than the consumer.

## 11. Relationship with Listener error handler, retry topic, and DLT

An authentication error during poll and a business error while processing a record sit at **two different layers**:

~~~mermaid
flowchart TD
    A[Listener container] --> B[Consumer poll]
    B --> C{Poll hit auth exception?}
    C -->|Yes| D[authExceptionRetryInterval]
    D --> E[ConsumerRetryAuthEvent]
    E --> B
    C -->|No| F[ConsumerRetryAuthSuccessfulEvent if just retried auth]
    F --> G[Records / listener]
    G --> H{Business processing succeeded?}
    H -->|Yes| I[Commit per policy]
    H -->|No| J[DefaultErrorHandler or rollback/retry]
    J --> K[Retry record / recovery / DLT]
~~~

In the diagram, if there has never been an auth retry, a normal successful poll **does not necessarily emit** `ConsumerRetryAuthSuccessfulEvent`.

- `DefaultErrorHandler` handles listener/record errors in non-transactional containers according to the configured policy.
- `@RetryableTopic` routes records to retry topics for later business-processing attempts.
- `DeadLetterPublishingRecoverer` sends unprocessable records to the DLT.
- `authExceptionRetryInterval` handles **poll auth failure** situations.

Therefore, do not use `ConsumerRetryAuthSuccessfulEvent` as a trigger to clear the DLT or close all listener processing failure tickets. Auth may have recovered while the DLT producer still lacks `WRITE` permission.

## 12. Relationship with ContainerStoppedEvent and ConsumerStoppedEvent

When not retrying or unable to continue after an auth exception, the consumer may stop. In versions supporting this classification, `ConsumerStoppedEvent` with reason `AUTH` represents a different lifecycle path from a successful retry poll.

| Progression | Important event | Implication |
|---|---|---|
| Consumer starts running normally | `ConsumerStartedEvent` | Consumer started its lifecycle; does not prove auth recovery. |
| Poll hits auth error, container will retry | `ConsumerRetryAuthEvent` | Error is being retried; consumer has not recovered yet. |
| Poll succeeds after auth retry | **`ConsumerRetryAuthSuccessfulEvent`** | Consumer just cleared a poll after an auth failure. |
| Consumer stops due to auth issue | `ConsumerStoppedEvent` / `AUTH`-related reason | Consumer stopped; investigate or restart per policy. |
| Entire listener container stops | `ContainerStoppedEvent` | Container-level state, not a single poll. |

If the application restarts the container after an auth failure without using in-place retry, the new startup may publish `ConsumerStartedEvent` without publishing `ConsumerRetryAuthSuccessfulEvent`. Do not define "recovered" solely by a single event type across all failure paths.

## 13. Concurrency: multiple consumers can recover independently

With `ConcurrentMessageListenerContainer` and `concurrency=4`, Spring Kafka typically manages four child consumers. Each consumer has its own poll loop and can publish its own auth retry/success events.

Example:

~~~text
Parent listener: paymentsListener
  Child 0: auth retry -> recovered
  Child 1: auth retry -> still failing
  Child 2: no auth error encountered
  Child 3: auth retry -> recovered

2 ConsumerRetryAuthSuccessfulEvent occurrences
Does not mean all 4 children are healthy.
~~~

If an authentication outage affects the entire Kafka cluster, multiple consumers may publish events around the same time when access is restored. Do not use a single success event to mark **the entire consumer group** as recovered.

Monitor:

- Number of actually running consumers versus configured concurrency and replica count.
- Whether each child listener/container still has an open retry/auth issue.
- Actual consumer group membership and assignments.
- Lag, record processing, and committed offsets after recovery.
- Downstream saturation when many consumers come back at once.

### Preventing duplicate alerts

If multiple child consumers recover simultaneously, send one aggregated notification for the incident instead of dozens of "Kafka is fine" messages. Use meaningful grouping keys: environment, Kafka cluster, service, consumer group, and outage window.

## 14. Recording recovery with Micrometer

A simple counter setup:

~~~java
@Component
public class KafkaAuthRecoveryMetrics {

    private final MeterRegistry meterRegistry;

    public KafkaAuthRecoveryMetrics(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @EventListener
    public void onRetry(ConsumerRetryAuthEvent event) {
        meterRegistry.counter(
                "kafka.consumer.auth.retry.events").increment();
    }

    @EventListener
    public void onRecovered(ConsumerRetryAuthSuccessfulEvent event) {
        meterRegistry.counter(
                "kafka.consumer.auth.retry.success.events").increment();
    }
}
~~~

These two counters count **events**, not retried records or business-processing success probability. One consumer may publish many retry events before one recovery event; different consumers experience different retry cycle counts.

If you need to measure outage duration, use a state tracker keyed by a stably identified consumer/container, storing the timestamp on the first auth retry and closing that state when the matching recovery event arrives. If the container stops without recovering, the state must be closed as **failed/stopped**, not counted as recovered.

### Tracking time from retry to successful poll

~~~text
auth_retry_started_at = timestamp of first auth retry for consumer
auth_poll_recovered_at = timestamp of ConsumerRetryAuthSuccessfulEvent
duration = recovered_at - started_at
~~~

This measures **how long polling was disrupted by auth**, not necessarily how long business processing was unavailable. Cross-check with consumer lag, processing rate, and consumer group status to understand real impact.

If the app restarts between the two timestamps, an in-memory state tracker loses its history. A centralized monitoring system can use structured logs/traces to reconstruct the incident.

## 15. Avoiding confusion between recovery signals and health signals

An incident can be divided into multiple phases:

| Phase | Signal | How to verify |
|---|---|---|
| Auth issue starts | `ConsumerRetryAuthEvent` or Kafka authentication error | Exception logs and retry state. |
| Auth issue persists | Repeated retry events, no successful poll | Backoff attempts, broker logs, and group membership. |
| Poll recovered | `ConsumerRetryAuthSuccessfulEvent` | Application event and timestamp. |
| Consumer receives valid assignment | Group assignment/consumer metrics | Consumer joined the group or holds proper assignment. |
| Listener resumes processing | Record consumption, listener success | Processing metrics and logs. |
| Backlog cleared | Partition lag drops, offsets advance | End offset, committed offset, and throughput. |
| Incident closed | Multiple signals verified stable over a period | SLO restored and no further auth failures. |

If you close an incident immediately based solely on the success event, you may miss a consumer alternating between one successful poll and failing on the next poll. Use a **stability window**: require stable polling/processing/assignments for long enough per SLA before marking fully recovered.

## 16. Auth retry may not fix permanently wrong credentials

Suppose an application starts with a wrong password in config and has no reload mechanism. The consumer will keep failing even if `authExceptionRetryInterval` is set to 15 seconds. The Kafka broker does not change the password inside the client process.

Distinguish:

- **Credentials rotated and client can refresh:** retry may succeed after refresh.
- **ACL not yet granted but operator will grant it:** retry may succeed after the broker change.
- **Credentials permanently wrong, no reload:** fix configuration/secret and possibly restart per procedure.
- **Certificate expired:** may need to replace TLS files/config and reinitialize the client.
- **Broker or identity provider temporarily disrupted:** retry with backoff can bridge the blip.

Tuning the retry interval does not replace fixing the root cause. If credentials may have been exposed, rotate them following security procedures; do not log secrets to "debug" auth.

## 17. Producer and DLT errors do not self-heal from a consumer event

A service can both consume and produce:

~~~text
payments.events  --consumer-->  PaymentService
                                    |
                                    +--> payments.results
                                    |
                                    +--> payments.events.DLT
~~~

If the consumer's `READ` permission is fixed and poll succeeds, `ConsumerRetryAuthSuccessfulEvent` can appear. However, the producer sending to `payments.results` or the DLT may still be rejected due to lacking `WRITE` on the destination topic.

To verify end-to-end:

1. Check consumer poll/assignment.
2. Check listener business-event processing.
3. Check producer send results/transaction commits.
4. Check DLT recovery if failing records exist.
5. Check input committed offsets and output visibility.
6. Check external databases/APIs if part of the workflow.

A consumer auth recovery event has no authority to confirm all of these steps.

## 18. When Kafka transactions and fencing appear together

In transactional consume–transform–produce, the consumer is permitted to read input, while the transactional producer must have permission to initialize and complete transactions with the Kafka coordinator. Authentication/authorization errors can appear at multiple steps: group join, fetch, producer init, publish, or transaction commit.

`ConsumerRetryAuthSuccessfulEvent` only indicates **poll auth retry succeeded**; it does not resolve producer fencing or transactional ID collisions.

If occurring concurrently:

- `ConsumerRetryAuthSuccessfulEvent` from the consumer,
- `ProducerFencedException` on the producer,
- transaction aborts and rising consumer lag,

then separately investigate producer identity (`transactionIdPrefix`, `transactional.id`, epoch) and consumer group membership. Do not mark transactions healthy simply because the consumer can poll again.

In a Kafka transactional listener, input offsets and Kafka outputs can be committed in the same transaction when wired properly. However, databases/HTTP still require idempotency. When an auth outage or rebalance causes records to be redelivered, an external side effect may be executed a second time.

## 19. Data security when logging auth retries

Auth errors can carry sensitive details in client configs or exception messages. An event handler should never write raw credentials, tokens, JAAS configs, or certificate private keys into logs.

Logs should include:

- Service, environment, Kafka cluster/alias.
- Listener/container ID and group ID if available.
- Timestamps when retry started and when recovery occurred.
- Authentication/authorization error category.
- Retry count or elapsed duration per policy.
- Consumer group state after recovery.
- Correlation/incident ID generated by operations tooling.

Do not log Kafka payloads just to prove the consumer polled successfully. A consumer can poll successfully with zero records, and recovery events do not need payloads.

## 20. Testing ConsumerRetryAuthSuccessfulEvent

You can test the observer at the Spring application event level and test retry integration with a test Kafka broker configured with security.

### Unit/application test for the observer

An event recorder can collect events to test listening:

~~~java
@Component
public class AuthEventRecorder {

    private final BlockingQueue<String> events =
            new LinkedBlockingQueue<>();

    @EventListener
    public void onRetry(ConsumerRetryAuthEvent event) {
        events.offer("RETRY");
    }

    @EventListener
    public void onRecovered(
            ConsumerRetryAuthSuccessfulEvent event) {
        events.offer("RECOVERED");
    }

    public String await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return events.poll(timeout, unit);
    }
}
~~~

The example focuses on the observer technique; imports such as `BlockingQueue`, `LinkedBlockingQueue`, and `TimeUnit` need to be added. In production, do not store unbounded event objects in a queue. If constructing events manually in unit tests, use the constructor matching the actual Spring Kafka version rather than guessing signatures.

### Integration test for auth recovery

1. Start a test Kafka broker with SASL/ACL or the corresponding authentication mechanism.
2. Create a topic, group, and a principal whose permissions can be adjusted in the test.
3. Configure the consumer container with a finite `authExceptionRetryInterval`.
4. Intentionally cause consumer polls to hit `AuthenticationException`/`AuthorizationException`.
5. Verify `ConsumerRetryAuthEvent` appears.
6. Restore permissions/credentials in a way the Kafka client can pick up.
7. Wait for a successful poll and verify `ConsumerRetryAuthSuccessfulEvent`.
8. Then publish a test record and verify listener processing and offset/lag behavior per policy.
9. Test a non-recovering scenario to verify the appropriate stop/alert policy.
10. Stop test containers and verify the observer does not prolong shutdown.

A Kafka test broker without security/ACL enabled is usually **insufficient** to prove the auth retry flow. Simulate real failures or use an appropriate integration environment. Do not intentionally revoke ACLs or rotate credentials on a production cluster serving live business traffic.

### Concurrency test scenario

With `concurrency=3`, let multiple child consumers encounter auth failures. Verify that the recorder and metrics do not mistake one child's success for recovery of all three. Also test shutdown mid-retry to ensure controllers do not restart a container being intentionally stopped.

## 21. Monitoring dashboards and alerting

| Signal | Scope | Meaning |
|---|---|---|
| Auth retry event count | Consumer/container | Frequency of poll errors requiring retry. |
| Auth retry success event count | Consumer/container | Number of observed poll recovery cycles. |
| Duration from first retry to success | Consumer/container | How long the consumer could not poll successfully due to auth. |
| Last successful poll time | Consumer/client | Whether the consumer continues polling after recovery. |
| Group member count and assignment | Consumer group | Whether members hold valid partition assignments. |
| Lag per partition | Topic/group | Whether backlog grew during outage and drops after recovery. |
| Listener record processing rate | Listener | Whether business processing has resumed. |
| Commit latency / committed offsets | Consumer group | Whether offsets advance per policy. |
| Authentication/authorization failures | Kafka client/broker | Whether the root cause is recurring or widespread. |
| Producer/DLT errors | Producer/recoverer | Avoid missing errors outside the consumer poll branch. |

Base alerts on trends rather than a single number:

- Continuous auth retries with no successful poll exceeding SLA duration.
- Retry success appears, followed shortly by recurring poll errors.
- Consumer is polling again yet member assignments remain incomplete.
- Lag keeps rising despite success events.
- Multiple services simultaneously experience auth failures after rotation/ACL deployment.
- Spike in recovery event counts, suggesting an unstable broker/security subsystem.

For high availability, alert on the ratio of affected consumers rather than a single error. During a widespread broker/security provider outage, group alerts by cluster/incident so on-call channels are not flooded.

## 22. Runbook: Prolonged auth retry with no success event

1. Identify the application, listener ID, group ID, instance, and time of first retry.
2. Find the root exception: authentication, authorization, or another error type.
3. Check whether `authExceptionRetryInterval` is properly configured on the container factory used by the listener.
4. Check the credentials/token/certificate actually used by the client.
5. Inspect Kafka ACLs for the topic and group; verify principal mapping.
6. Check broker logs, identity provider, and network connectivity.
7. Determine whether secrets or ACLs were fixed yet the client failed to reload/reconnect properly.
8. Monitor retry events, stop events, and container state.
9. After recovery, verify poll success, assignment, record consumption, and lag.
10. If the error does not change, perform a controlled stop/restart after fixing config; do not hot-retry infinitely.

Do not use another consumer's successful retry count in the group as proof that the failing instance has recovered.

## 23. Runbook: Success event appears but consumer does not process records

1. Confirm which consumer/container the event belongs to, avoiding confusion with another instance.
2. Check topic subscription, group ID, assignment, and partition count.
3. Check whether `poll()` returned records or was just an empty poll.
4. Check whether the container is paused, rebalancing, or waiting on state restoration.
5. Compare committed offset with end offset to determine whether backlog exists.
6. Check listener exceptions, retry/DLT, and downstream latency.
7. Check producer/DLT access permissions if the pipeline needs to publish output.
8. Do not reset offsets or seek to beginning/end just because the success event did not immediately lead to processing.

A consumer polling successfully when the topic has no data can be a normal state.

## 24. Runbook: Auth recovers yet errors recur repeatedly

1. Build a timeline of `ConsumerRetryAuthEvent` and `ConsumerRetryAuthSuccessfulEvent` per instance.
2. Measure recovery duration and stable intervals between outages.
3. Check token refresh/expiry and credential rotation schedules.
4. Check whether brokers or the security provider have intermittent outages.
5. Check for ACL/config drift across brokers or clusters if errors show uneven distribution.
6. Inspect DNS/TLS/SASL client logs at a safe logging level.
7. Tune retry interval/backoff per SLA, avoiding creating an auth request storm.
8. Enforce a stability window before closing the incident.
9. After fixing, verify group stability, lag, and processing throughput.

Do not increase `authExceptionRetryInterval` indefinitely; it only lengthens the wait without addressing the root cause.

## 25. Runbook: Recovery event appears during rolling deployment

1. Identify whether the pod is starting up or about to shut down.
2. Check whether the consumer retry happened before or after credential/ACL changes.
3. Check whether the instance still has `isRunning()` true and holds assignments.
4. Verify whether the success event belongs to a container about to stop to avoid falsely marking a pod ready.
5. Check that no restart controller triggers inversely during shutdown.
6. Compare member counts and lag before/after rollout.
7. If transactions are used, inspect producer identity and commit/abort independently.
8. Close the incident when workload processing is genuinely stable, not just on one success event.

## 26. Runbook: Auth retry succeeds yet DLT publish still fails

1. Confirm consumer polling recovered; capture source topic/partition/offset of the failing record.
2. Inspect the exception when `DeadLetterPublishingRecoverer` publishes to the DLT.
3. Confirm the producer has `WRITE` permission on the DLT and required transactional ACLs if using transactions.
4. Check serializer, destination partition count/topic, and broker availability.
5. Ensure the recoverer does not treat a failed DLT publish as success and commit the source offset.
6. Restore producer permissions, then retry/recover per policy.
7. Reconcile DLT messages, source offsets, and audit/replay logs.

Consumer authentication success does not equate to producer authorization success.

## 27. ConsumerRetryAuthSuccessfulEvent verification table

| Checkpoint | Question to answer | Evidence |
|---|---|---|
| Retry enabled | Does the listener container have a valid `authExceptionRetryInterval`? | Container factory config and runtime logs. |
| Event semantics | Did the success event arrive after a successful auth retry poll? | Retry/recovered timeline. |
| Observer wiring | Does `@EventListener` receive the right events? | Spring context and structured logs. |
| Consumer identity | Can the recovering child consumer/instance be identified? | Listener/container ID, group, and instance. |
| Root cause | Was the prior failure authentication or authorization? | `ConsumerRetryAuthEvent` and exception/broker logs. |
| Poll budget | Does the retry interval fit `max.poll.interval.ms` and group lifecycle? | Effective properties, poll/rebalance metrics. |
| Group health | Does the consumer hold assignments and sufficient members? | Group membership and assignment. |
| Business progress | Have records been processed and offsets advanced? | Listener metrics, committed offsets, lag. |
| Producer/DLT | Were producer, DLT, and transaction permissions checked independently? | Send results, recovery, and transaction metrics. |
| Restart policy | Did auth retry trigger a restart loop or double-controller? | Stop/start events and orchestration state. |
| Security | Do logs avoid exposing credentials/tokens/payloads? | Logging policy and access review. |
| Incident closure | Is a stability window enforced instead of closing immediately on the event? | Alert lifecycle, processing rate, and recovery duration. |

**Conclusion:** `ConsumerRetryAuthSuccessfulEvent` marks a **successful Kafka consumer poll following an authentication or authorization retry phase** managed by the Spring Kafka container. It is an important observability signal indicating that a temporary security error has been overcome at the Kafka read layer. For reliable operations, configure `authExceptionRetryInterval` properly, listen for both retry and success events, distinguish consumer-level recovery from business-level success, measure group/lag/offset status after recovery, and govern restart and credential policies. Never treat the event as proof that all records, transactions, or external effects beyond Kafka have completed.
