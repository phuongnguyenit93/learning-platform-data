# ConsumerRetryAuthEvent

## 1. What is ConsumerRetryAuthEvent?

**ConsumerRetryAuthEvent** is a **Spring Kafka application event** published when a Kafka consumer encounters an authentication or authorization error and the listener container is **retrying** according to configuration rather than stopping immediately.

This event belongs to the consumer operations layer, not a business event stored in a Kafka topic. It does not carry an OrderCreated or PaymentProcessed payload, nor does it directly perform retries, update ACLs, or rotate credentials. It is a signal that lets the application observe a retry path already decided by the container.

For example: Order Fulfillment reads the orders.created topic. An ACL change causes the consumer's principal to temporarily lose permission to read the topic. When the container is configured to retry auth, it can publish ConsumerRetryAuthEvent, wait the configured interval, and then attempt to poll again. After the ACL is restored and a retry succeeds, the container can publish **ConsumerRetryAuthSuccessfulEvent**.

~~~text
Spring Kafka listener container
          |
          v
     KafkaConsumer.poll()
          |
     +----+--------------------+
     |                         |
  Success               Auth/authz exception
     |                         |
     v                         v
  Listener              Retry enabled?
     |                    /          \
     v                   No          Yes
  Process record         |            |
                         v            v
                      Container  ConsumerRetryAuthEvent
                      may stop   reason=AUTHENTICATION
                                 or AUTHORIZATION
                                      |
                                      v
                                Wait retry interval
                                      |
                                      v
                                KafkaConsumer.poll()
                                      |
                               +------+------+
                               |             |
                          Still failing   Success
                               |             |
                               v             v
                          Retry again    ConsumerRetryAuth
                                         SuccessfulEvent
~~~

**Key point:** the event reflects **retrying after a security error**; it does not prove the error has been fixed or that records have been processed.

## 2. Position of the event in the Spring Kafka system

Spring Kafka publishes multiple application events for the listener container lifecycle:

| Event | Main meaning |
|---|---|
| ConsumerStartingEvent | Consumer starts initializing |
| ConsumerStartedEvent | Consumer has started per the corresponding lifecycle |
| ConsumerPartitionAssignedEvent | Consumer receives partitions |
| ConsumerPartitionRevokedEvent | Partitions are revoked |
| ConsumerPartitionLostEvent | Consumer loses partition ownership |
| **ConsumerRetryAuthEvent** | Authentication/authorization failed and is retrying |
| **ConsumerRetryAuthSuccessfulEvent** | Auth retry succeeded after a previous auth retry |
| ConsumerStoppedEvent | Consumer stopped; may include a reason |
| ContainerStoppedEvent | Container stopped |
| NonResponsiveConsumerEvent | Container detected signs of an unresponsive consumer poll |

ConsumerRetryAuthEvent does not replace ConsumerStoppedEvent. One event indicates **an active retry path**, while the other indicates **the consumer has stopped**.

### 2.1. Not every auth error produces a retry event

If authExceptionRetryInterval is not configured, the container's auth retry path is disabled. When KafkaConsumer throws AuthenticationException or AuthorizationException, the container may stop instead of publishing ConsumerRetryAuthEvent.

Therefore, the absence of ConsumerRetryAuthEvent does not guarantee that no auth error occurred. You must check interval configuration, logs, and ConsumerStoppedEvent as well.

## 3. How does authentication differ from authorization?

**Authentication** verifies identity:

- Wrong SASL/SCRAM username or password.
- SASL mechanism incompatible with the broker.
- Invalid or expired TLS client certificate.
- Improper Kerberos/JAAS configuration.
- Incorrect principal mapping or identity configuration.

**Authorization** verifies the permissions of an identity already recognized by the broker:

- Missing READ permission on topic orders.created.
- Missing READ permission on consumer group order-fulfillment.
- ACL DENY or host restriction blocking the request.
- Topic or group ID differs from the granted resource.

| Aspect | Authentication | Authorization |
|---|---|---|
| Question | Who is the client? | What permissions does the principal have? |
| Typical Kafka exceptions | AuthenticationException, SaslAuthenticationException | AuthorizationException, TopicAuthorizationException, GroupAuthorizationException |
| Event reason | AUTHENTICATION | AUTHORIZATION |
| Remediation | Credentials, TLS/SASL, principal mapping | ACL, resource name, operation, principal |
| Can retry fix it automatically? | No if credentials remain wrong | No if ACLs remain missing |

Changing a password does not grant READ permission. Granting READ permission does not make an invalid password valid. Distinguishing the reason helps the operations team fix the right error layer.

## 4. API of ConsumerRetryAuthEvent

The class resides in package:

~~~java
org.springframework.kafka.event.ConsumerRetryAuthEvent
~~~

In applicable Spring Kafka 3.x and 4.x versions, the event extends KafkaEvent and provides:

| Member | API | Meaning |
|---|---|---|
| Reason | event.getReason() | Retry reason: AUTHENTICATION or AUTHORIZATION |
| Source | event.getSource() | Listener container publishing the event |
| Container | event.getContainer() | Associated container; may be parent if source is a child |
| Timestamp | event.getTimestamp() | Time when the event was created |

Nested enum:

~~~java
ConsumerRetryAuthEvent.Reason.AUTHENTICATION
ConsumerRetryAuthEvent.Reason.AUTHORIZATION
~~~

A simple observer:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.kafka.event.ConsumerRetryAuthEvent;
import org.springframework.stereotype.Component;

@Component
public class KafkaAuthRetryObserver {

    @EventListener
    public void onRetry(ConsumerRetryAuthEvent event) {
        log.warn(
            "Consumer auth retry: reason={}, source={}, container={}",
            event.getReason(),
            event.getSource(),
            event.getContainer()
        );
    }
}
~~~

The event provides the reason, but it is not a full snapshot of principal, resource, operation, and stack trace. When you need to know which ACL is missing, inspect broker/client logs.

### 4.1. Do not invoke the consumer arbitrarily from callbacks

KafkaConsumer is not thread-safe. Spring's default event multicaster normally runs listeners on the event-publishing thread, but an application can switch to an async executor. Do not hold onto a consumer reference or call poll/commit/seek from an event observer running on another thread.

Observers are best kept lightweight: logs, metrics, and thread-safe monitoring state updates.

## 5. ConsumerRetryAuthSuccessfulEvent

Related class:

~~~java
org.springframework.kafka.event.ConsumerRetryAuthSuccessfulEvent
~~~

This event is published when an authentication/authorization retry attempt **succeeds after a previous ConsumerRetryAuthEvent**. It helps mark the end of an auth/authz outage at the consumer's retry layer.

~~~text
10:00 ConsumerRetryAuthEvent(AUTHORIZATION)
10:30 ConsumerRetryAuthEvent(AUTHORIZATION)
11:00 ACL updated
11:01 Next auth retry succeeds
11:01 ConsumerRetryAuthSuccessfulEvent
11:02 Consumer resumes polling/receiving assignment depending on group state
~~~

The timeline is illustrative only. Do not assume an event occurs every exact 30 seconds and do not treat the event count as an exact count of auth requests.

### 5.1. Example capturing both events

~~~java
@Component
public class KafkaAuthEvents {

    @EventListener
    public void retrying(ConsumerRetryAuthEvent event) {
        log.warn(
            "Kafka consumer retrying auth, reason={}",
            event.getReason()
        );
    }

    @EventListener
    public void recovered(ConsumerRetryAuthSuccessfulEvent event) {
        log.info(
            "Kafka consumer auth retry succeeded, source={}",
            event.getSource()
        );
    }
}
~~~

**ConsumerRetryAuthSuccessfulEvent does not guarantee that consumer lag has decreased or that records have been committed.** It only indicates that the auth/authz error in the retry path was overcome.

If the group is still rebalancing, the listener is paused, or the downstream DB is failing, data may still remain unprocessed.

## 6. Configuring authExceptionRetryInterval

Spring Kafka supports **authExceptionRetryInterval** on container properties. This property specifies the wait interval between retries when KafkaConsumer throws AuthenticationException or AuthorizationException.

Example:

~~~java
factory.getContainerProperties()
    .setAuthExceptionRetryInterval(Duration.ofSeconds(30));
~~~

For API versions supporting this feature, leaving the property null disables container auth retry and the container may stop when receiving the corresponding exception.

### 6.1. Constraint with max.poll.interval.ms

The auth retry interval **must be smaller than max.poll.interval.ms**.

~~~text
Kafka consumer:
  max.poll.interval.ms           = 300000 ms
  authExceptionRetryInterval     = 30000 ms
~~~

A 30-second value is smaller than 5 minutes. However, the application also needs to account for record processing time, batches, GC pauses, and downstream latency; do not configure the interval right up against the poll limit.

### 6.2. Waiting does not fix permissions

The retry interval gives the consumer **an opportunity** to recover when ACLs, credentials, or broker conditions are fixed externally. It does not automatically create ACLs or update hardcoded passwords.

If an application uses a secret loaded only at JVM startup, retrying in the same process may keep using the old secret. In that case, design configuration refresh or controlled process restarts.

## 7. Configuring ConcurrentKafkaListenerContainerFactory

Example creating a dedicated factory to apply auth retry:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.kafka.config.ConcurrentKafkaListenerContainerFactory;
import org.springframework.kafka.core.ConsumerFactory;

@Configuration
public class KafkaListenerConfiguration {

    @Bean
    public ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
            authRetryKafkaListenerContainerFactory(
                    ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties()
            .setAuthExceptionRetryInterval(Duration.ofSeconds(30));

        return factory;
    }
}
~~~

Attach the factory to an endpoint:

~~~java
@KafkaListener(
    id = "orders-consumer",
    topics = "orders.created",
    groupId = "order-fulfillment",
    containerFactory = "authRetryKafkaListenerContainerFactory"
)
public void consume(OrderCreated event) {
    fulfillmentService.processIdempotently(event);
}
~~~

The example assumes ConsumerFactory, deserializers, and security are already configured compatibly.

**Note on multiple factories:** configuring the interval on one factory does not automatically apply to listeners using other factories. When debugging, confirm which factory `@KafkaListener` uses.

### 7.1. Spring Boot auto-configuration

YAML property names mapping directly to authExceptionRetryInterval may differ or be absent in a specific Spring Boot line. Using the Java setter as shown avoids guessing property names.

If you want to set it via configuration properties, check the metadata/version of the deployed Spring Boot release or use the official factory customizer supported by that version.

## 8. SASL/SCRAM consumer example

A secure connection configuration:

~~~yaml
spring:
  kafka:
    bootstrap-servers:
      - kafka-a.example.net:9093
      - kafka-b.example.net:9093

    consumer:
      group-id: order-fulfillment
      enable-auto-commit: false
      properties:
        "[security.protocol]": SASL_SSL
        "[sasl.mechanism]": SCRAM-SHA-512
        "[sasl.jaas.config]": 'org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-reader" password="<injected-secret>";'

    listener:
      ack-mode: batch
~~~

The password string is only a placeholder. In production, retrieve secrets from a secret manager or an injection mechanism managed by the deployment platform. Do not commit passwords, private keys, or tokens into source control.

Setting SASL_SSL establishes a connection with TLS and SASL, but does not automatically grant ACLs.

### 8.1. Least-privilege permissions for the consumer

Example principal:

~~~text
Principal: User:orders-reader

Topic orders.created:
    operation READ

Group order-fulfillment:
    operation READ
~~~

Verify the actual resource/principal from broker logs. If the listener subscribes to additional topics or uses a different group ID via annotation overrides, ACLs must match accurately.

## 9. AUTHENTICATION event: password rotation example

Suppose the Kafka cluster rotates the SCRAM password for principal orders-reader while an older pod still uses the previous password.

~~~text
Consumer starts
      |
      v
SASL handshake rejected
      |
      v
AuthenticationException
      |
      v
ConsumerRetryAuthEvent(AUTHENTICATION)
      |
      v
Wait retry interval
      |
      v
Retry with current client credentials
~~~

Checks needed:

1. Was the new secret issued properly?
2. Has the pod/app received the new secret yet?
3. Which credentials is the ConsumerFactory's JAAS config currently using?
4. Can the Kafka client reload credentials without restarting?
5. Is it necessary to recreate the KafkaConsumer or restart the pod?
6. Do broker logs confirm the principal and actual error?

If the password remains wrong, retries will keep failing. Simply increasing retry counts or reducing the interval does not solve the root cause.

### 9.1. Distinguishing from network errors

TLS connection errors, DNS failures, or broker disconnects may follow a different exception path depending on the Kafka client version. Absence of ConsumerRetryAuthEvent does not mean connectivity/security is healthy.

You must read the original exception and cross-check broker logs.

## 10. AUTHORIZATION event: missing group ACL example

The consumer succeeds in SASL authentication as principal User:orders-reader, but the broker denies joining group order-fulfillment.

~~~text
SASL auth: SUCCESS
       |
       v
Group operation
       |
       v
Broker ACL check: DENIED
       |
       v
GroupAuthorizationException
       |
       v
ConsumerRetryAuthEvent(AUTHORIZATION)
       |
       v
Admin fixes READ permission on group
       |
       v
Consumer retry succeeds
       |
       v
ConsumerRetryAuthSuccessfulEvent
~~~

Operational steps:

- Identify the principal seen by the broker.
- Confirm the listener's actual group ID.
- Check READ permission on the group.
- Check READ permission on every topic the consumer reads.
- Check DENY rules, host restrictions, and ACL resource patterns.
- Grant only the minimum required permissions following governance procedures.
- Observe the retry successful event and consumer group assignment.

Do not grant superuser privileges to runtime services just to avoid authz errors.

## 11. Event reason and original exception

ConsumerRetryAuthEvent.getReason() only classifies **AUTHENTICATION** or **AUTHORIZATION**. It is not an API returning the raw Kafka exception with all nested causes.

To debug, combine:

| Information source | Useful details |
|---|---|
| ConsumerRetryAuthEvent | Auth/authz error category and container source |
| Kafka consumer logs | AuthenticationException, AuthorizationException, and causes |
| Broker security logs | Principal, operation, resource, host |
| Spring Kafka container logs | Poll retries, container lifecycle, stop |
| Deployment/config history | Secret rotation, ACL changes, rollouts |
| Consumer group metrics | Lag, assignment, rebalance, commits |

Do not infer a missing topic ACL solely from reason AUTHORIZATION, because the error may be on **Group**, **Topic**, or another resource involved in the request.

### 11.1. Observing the real principal

With SASL/SCRAM, the broker typically derives the principal from the username. With mTLS, the principal may be derived from the certificate subject and mapping rules.

ACLs must match the **principal on the broker**, not necessarily the bean name, Spring application name, or internal service account name.

## 12. When retry interval is not configured

If authExceptionRetryInterval is left null, the Spring Kafka container may stop on auth/authz errors:

~~~text
KafkaConsumer.poll()
        |
        v
AuthenticationException / AuthorizationException
        |
        v
authExceptionRetryInterval = null
        |
        v
Container stops
        |
        v
ConsumerStoppedEvent(reason=AUTH)
~~~

In supported Spring Kafka versions, **ConsumerStoppedEvent** carries reason **AUTH** when a consumer stops due to an authentication/authorization exception without a configured retry interval.

A fail-fast policy can be useful if the security team wants permission failures surfaced immediately for operator intervention.

### 12.1. Auth retry and restart are two different choices

| Situation | Reasonable direction |
|---|---|
| ACL expected to be restored quickly | Can retry with authExceptionRetryInterval |
| Permanently wrong credentials | Fix the secret; retrying is not enough |
| Consumer stopped due to AUTH | Fix the root cause then perform a controlled restart |
| Secret lives in env and is loaded only at JVM start | May require process/pod restart |
| Broker temporarily disconnected while client is reconnecting | Not necessarily a reason to restart container |
| Runtime policy requires fail-fast | Do not enable prolonged unintended retries |

Do not restart infinitely, because the same error can keep recurring and trigger continuous consumer group rebalances.

## 13. ConsumerRetryAuthEvent vs. ConsumerStoppedEvent

| Attribute | ConsumerRetryAuthEvent | ConsumerStoppedEvent |
|---|---|---|
| When published | Auth/authz error and retry is taking place | Consumer has stopped |
| State | Container is attempting recovery | Consumer is no longer running |
| Reason | AUTHENTICATION, AUTHORIZATION | NORMAL, AUTH, FENCED, ERROR, and other values by version |
| Purpose | Logs, metrics, alerts, recovery observation | Classify stops and manage lifecycle |
| Proves records are being processed? | No | No |
| Should start be called immediately in handler? | No | No unless stop-complete and restart policy are ensured |

If no retry event appears while ConsumerStoppedEvent with reason AUTH does appear, inspect the retry interval configuration first.

## 14. Concurrency and child containers

With `@KafkaListener` concurrency=3:

~~~text
Parent ConcurrentMessageListenerContainer
      |
      +-- child #0 -> KafkaConsumer #0
      +-- child #1 -> KafkaConsumer #1
      +-- child #2 -> KafkaConsumer #2
~~~

One child can publish ConsumerRetryAuthEvent while another child has not yet encountered the same error or is still polling.

Spring Kafka events provide:

- **getSource()**: container that published the event.
- **getContainer()**: associated container, which may be the parent in a child model.

Do not use an application-wide boolean such as authFailed=true to describe all consumers if the application has multiple listeners or high concurrency.

A state map keyed by consumer/container identity is better, combined with listener ID and group ID when appropriate metadata is available.

### 14.1. The event is not a Kafka record

ConsumerRetryAuthEvent is published through the Spring application event infrastructure. It does not appear on a Kafka topic unless the application intentionally builds a separate audit pipeline to publish telemetry.

Do not invoke KafkaTemplate.send from the observer on every retry event without considering that the current auth/broker failure itself may cause telemetry publishing to fail and create noise.

## 15. Thread safety and ApplicationEventMulticaster

Spring application event listeners usually run synchronously on the event-publishing thread unless an async multicaster is configured. When switched to an async executor, event callbacks may run on a different thread.

**KafkaConsumer is not thread-safe.** Therefore, do not:

- Call poll, seek, commit, or subscribe from an `@EventListener` running asynchronously.
- Hold a KafkaConsumer reference for later use.
- Perform long blocking I/O inside the observer.
- Call listener container restart immediately upon receiving a retry event.
- Modify ACLs or credentials from the consumer event thread.
- Let metrics/backend exceptions kill the poll thread.

Observers should write brief logs or update metrics/thread-safe data structures.

### 15.1. Metrics example with Micrometer

~~~java
@Component
public class AuthRetryMetrics {

    private final MeterRegistry meterRegistry;

    public AuthRetryMetrics(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    @EventListener
    public void onRetry(ConsumerRetryAuthEvent event) {
        meterRegistry.counter(
            "kafka.consumer.auth.retry.events",
            "reason",
            event.getReason().name()
        ).increment();
    }

    @EventListener
    public void onSuccess(ConsumerRetryAuthSuccessfulEvent event) {
        meterRegistry.counter(
            "kafka.consumer.auth.retry.success.events"
        ).increment();
    }
}
~~~

The snippet assumes the Micrometer dependency is already present. This metric counts **events** emitted by the framework, not guaranteed to equal the exact number of authentication handshakes performed by the broker.

Do not put passwords, tokens, sensitive principals, or dynamic IDs into metric labels.

## 16. State across the auth retry lifecycle

You can build a monitoring state machine, though it is not an official Spring Kafka state machine:

~~~text
HEALTHY
   |
   | ConsumerRetryAuthEvent
   v
AUTH_RETRYING
   |
   +-- Subsequent retry event -> AUTH_RETRYING
   |
   +-- ConsumerRetryAuthSuccessfulEvent
   |            |
   |            v
   |       AUTH_RECOVERED
   |            |
   |            v
   |       Poll/assignment/
   |       processing OK
   |            |
   |            v
   |         HEALTHY
   |
   +-- ConsumerStoppedEvent
                |
                v
              STOPPED
~~~

Store per consumer or listener container:

- First auth retry timestamp.
- Last auth retry timestamp.
- Last reason.
- Successful retry timestamp.
- Container stopped state.
- Last assignment and poll/processing progress.
- Consumer lag.

If the event multicaster runs asynchronously, callbacks may be processed out of publication order. Do not use telemetry event ordering as a business correctness mechanism.

## 17. Alerting based on error duration

Do not open a new incident for every ConsumerRetryAuthEvent; a prolonged outage can emit many events.

Alerts can be based on:

- Auth retry lasting longer than an SLO threshold.
- Consumer lag rising during retry.
- Multiple consumers in the same group hitting AUTHENTICATION after secret rotation.
- AUTHORIZATION occurring right after an ACL deployment.
- Container stopping with reason AUTH.
- Absence of ConsumerRetryAuthSuccessfulEvent within the expected deadline.
- No record processing despite topic backlog.

Structured log example:

~~~text
event=consumer_retry_auth
service=order-fulfillment
listener=orders-consumer
groupId=order-fulfillment
reason=AUTHORIZATION
action=retrying
~~~

After recovery:

~~~text
event=consumer_retry_auth_successful
service=order-fulfillment
listener=orders-consumer
groupId=order-fulfillment
action=auth_recovered
~~~

Remember that the success event does not prove the data pipeline is completely healthy. Only close the incident once processing, assignment, and lag have returned to target criteria.

## 18. Impact on consumer lag and offsets

While authentication/authorization is failing, the consumer may be unable to fetch new records. Producers keep writing to the topic, so backlog can grow.

~~~text
P0 committed offset: 150
P0 log end offset:   250

Consumer encounters auth error
      |
      v
ConsumerRetryAuthEvent
      |
      v
Cannot make progress
      |
      v
More records arrive
      |
      v
Lag increases
      |
      v
Auth retry succeeds
      |
      v
Consumer resumes from appropriate offset
~~~

**The event does not commit offsets.** Commits remain managed by the consumer/container and AckMode or Kafka transactions.

If a record already produced a DB side effect but its offset was not committed before the consumer lost group membership or stopped, that record may be redelivered upon recovery. Therefore, business side effects require idempotency.

### 18.1. Rebalances may occur

If the consumer fails to poll or maintain membership per Kafka requirements, the group may rebalance and partition assignments may change. However, not every ConsumerRetryAuthEvent necessarily leads to a rebalance.

Monitor in parallel:

- ConsumerPartitionAssignedEvent.
- ConsumerPartitionRevokedEvent.
- ConsumerPartitionLostEvent.
- Group rebalance count.
- max.poll.interval.ms.
- Poll latency, commit failures, and lag.

## 19. Distinguishing auth retry from record retry

There are two very different retry layers.

**Auth retry:** KafkaConsumer encounters AuthenticationException/AuthorizationException. The listener may not have received any record; the container retries polling after the wait interval.

**Record retry:** KafkaConsumer has already received the record and `@KafkaListener` encounters a business exception. DefaultErrorHandler can retry or recover to a DLT.

~~~text
KafkaConsumer.poll()
         |
      AUTH error
         |
         v
ConsumerRetryAuthEvent
         |
         v
Auth retry at container

KafkaConsumer.poll() succeeds
         |
         v
@KafkaListener
         |
     Business exception
         |
         v
DefaultErrorHandler
         |
    +----+------+
    |           |
  Retry        DLT
~~~

Do not use authExceptionRetryInterval to resolve malformed JSON or DB timeouts in the listener. Nor should you send a record to a DLT just because the consumer lacked READ permission, since the listener may never have received that record.

## 20. Restart container or wait for retry?

When the container **is retrying**, stopping/starting it on every received event is usually harmful:

- Adds SASL/TLS handshakes.
- Triggers extra rebalances.
- Can disrupt healthy child containers.
- Does not change ACLs or fix an invalid password.
- Makes outage timestamps harder to correlate.

A restart may be needed when:

1. The container has stopped completely.
2. New credentials are only loaded when creating KafkaConsumer or starting the JVM.
3. ConsumerFactory/configuration was fixed, yet the current consumer has not picked it up.
4. Operators confirm the root cause is resolved and want to reinitialize the lifecycle.

When restarting, use KafkaListenerEndpointRegistry or a managed container reference, wait for stop to complete before starting, and avoid performing operations directly inside the ConsumerRetryAuthEvent observer.

### 20.1. Restarting just the listener does not always reload secrets

If a secret is loaded via an environment variable at JVM startup, stopping/starting the Kafka listener container in the same JVM does not automatically refresh environment variables. You may need to restart the pod or use an explicitly designed dynamic refresh mechanism.

Conversely, when a broker ACL is fixed for the current principal, the consumer can recover automatically on the next retry without restarting the process.

## 21. Security and least privilege

An AUTHORIZATION event should never trigger logic that self-grants ACLs using a superuser account. Granting permissions at runtime based on an arbitrary event creates privilege-escalation risk.

Safe procedure:

- Identify the authenticated principal.
- Identify the denied resource type, resource name, and operation.
- Cross-check ALLOW/DENY ACLs, hosts, and patterns.
- Grant only the permissions needed by the service.
- Record the approver and security change.
- Observe the retry successful event.
- Verify the topic/group operates again.

Do not log full JAAS configs, passwords, tokens, or TLS private keys. Security error logs must also follow proper access controls and retention.

## 22. Integration test for Authorization retry

A useful integration test should use a real Kafka broker with an authorizer and real ACLs, not just mock the listener method.

Scenario:

1. Create topic orders.created and group order-fulfillment.
2. Create a consumer principal with valid credentials.
3. Temporarily withhold READ on the topic or group.
4. Configure an appropriate authExceptionRetryInterval.
5. Start `@KafkaListener` and collect ConsumerRetryAuthEvent.
6. Verify reason AUTHORIZATION.
7. Grant minimum READ ACL.
8. Wait for ConsumerRetryAuthSuccessfulEvent.
9. Verify the consumer joins the group and receives partitions.
10. Publish a valid event and verify the listener processes it.
11. Verify offsets advance and lag recovers.
12. Clean up test ACLs and topics per test procedures.

Use await with a timeout instead of fixed sleep, because broker ACL propagation and rebalance timings can vary.

### 22.1. Test collector for application events

~~~java
@Component
public class TestAuthEventCollector {

    private final BlockingQueue<ConsumerRetryAuthEvent> retryEvents =
        new LinkedBlockingQueue<>();

    private final BlockingQueue<ConsumerRetryAuthSuccessfulEvent> successEvents =
        new LinkedBlockingQueue<>();

    @EventListener
    public void onRetry(ConsumerRetryAuthEvent event) {
        retryEvents.offer(event);
    }

    @EventListener
    public void onSuccess(ConsumerRetryAuthSuccessfulEvent event) {
        successEvents.offer(event);
    }

    public ConsumerRetryAuthEvent awaitRetry(Duration timeout)
            throws InterruptedException {

        return retryEvents.poll(
            timeout.toMillis(),
            TimeUnit.MILLISECONDS
        );
    }

    public ConsumerRetryAuthSuccessfulEvent awaitSuccess(Duration timeout)
            throws InterruptedException {

        return successEvents.poll(
            timeout.toMillis(),
            TimeUnit.MILLISECONDS
        );
    }
}
~~~

The example assumes imports for BlockingQueue, LinkedBlockingQueue, Duration, and TimeUnit. With multiple listener factories, filter by source/container so the test does not confuse events from another endpoint.

## 23. Integration test for Authentication retry

Authentication retry requires a real SASL or TLS environment.

Scenario:

1. Create a Kafka test cluster requiring SASL/SCRAM or client certificates.
2. Start the consumer with authExceptionRetryInterval.
3. Intentionally trigger an authentication error.
4. Observe ConsumerRetryAuthEvent with reason AUTHENTICATION.
5. Update credentials or broker settings per the test mechanism.
6. If the client supports reload/re-authentication, observe the successful event.
7. If credentials are only loaded at process startup, verify the appropriate restart path.
8. Verify that the consumer reads records and offsets advance after recovery.
9. Ensure test logs contain no secrets.

Do not assume every form of secret rotation recovers automatically within the same JVM. How credentials are loaded and the Kafka client version determine that.

### 23.1. Fail-fast test without interval

An additional test:

- Do not set authExceptionRetryInterval.
- Trigger AuthenticationException or AuthorizationException.
- Observe container stop per the specific version's behavior.
- Verify ConsumerStoppedEvent reason AUTH when supported by the version.
- Fix the root cause, perform a controlled restart, and verify continued processing.

This test proves the **retry** path differs from the **container stopped** path.

## 24. Production runbook

When receiving ConsumerRetryAuthEvent:

1. Record the timestamp, service, listener/container source, and reason.
2. Distinguish AUTHENTICATION from AUTHORIZATION.
3. Read client and broker logs to identify the root exception.
4. For AUTHENTICATION: check SASL mechanism, TLS certificate, password/secret version, principal.
5. For AUTHORIZATION: check topic/group READ, principal, resource pattern, host, and deny rules.
6. Confirm authExceptionRetryInterval and max.poll.interval.ms.
7. Check whether the container is still retrying or has stopped.
8. Do not mass-restart consumers just because of a retry event.
9. Fix credentials or ACLs according to governance procedures.
10. When needed, perform a controlled reload/restart of the container or pod.
11. Observe ConsumerRetryAuthSuccessfulEvent after the retry succeeds.
12. Check consumer group assignment and rebalances.
13. Verify the listener processes valid records and commits offsets.
14. Observe whether consumer lag drops back to SLO targets.
15. Check side-effect idempotency if uncommitted records are redelivered.
16. Update the incident report and alerts/runbooks for future occurrences.

If the successful event does not appear even after fixing ACLs, inspect the actual principal, group ID, topic, container state, and client security configuration. Do not just increase the retry interval and conclude it is fixed.

## 25. Synthesis example: Order Fulfillment loses ACL

Suppose Order Fulfillment runs three child consumers in the same group order-fulfillment. Topic orders.created continues receiving events steadily.

A security change accidentally revokes READ permission on the consumer group. The consumer receives GroupAuthorizationException. The container is configured with a 30-second retry, so it publishes ConsumerRetryAuthEvent reason AUTHORIZATION.

~~~text
09:00  Group processing normally
09:05  Group READ ACL revoked
09:05  AuthorizationException
09:05  ConsumerRetryAuthEvent(AUTHORIZATION)
09:06  Monitoring detects lag increasing
09:07  Admin restores READ for the group
09:07+ ConsumerRetryAuthSuccessfulEvent
09:08  Group assignment and processing verified
~~~

These are illustrative milestones; actual timing depends on the interval and group lifecycle.

The operations team does not restart pods immediately upon seeing the event. They check the denied principal/resource, fix the ACL, observe the successful retry, and wait for the consumer to catch up.

If a record already created a DB side effect without committing its offset before the consumer stopped or rebalanced, that record can be redelivered. An inbox/idempotent consumer prevents duplicate fulfillment creation.

Scenario takeaway: **fixing the ACL properly is what drives recovery**, while ConsumerRetryAuthEvent supplies the monitoring signal for the failure and retry process.

## 26. Common mistakes

**ConsumerRetryAuthEvent means auth succeeded.** False; it reports an error currently being retried. Success has its own event.

**Reason AUTHORIZATION means wrong password.** False; authorization is permission to access resources.

**Not seeing a retry event means no auth error occurred.** False; the container may have stopped when retry interval was not configured.

**Successful event proves the listener committed records.** False; processing and offsets must be verified separately.

**Every retry event is a new incident.** Not recommended; multiple events may belong to one prolonged outage.

**Retry interval creates ACLs automatically.** Incorrect; permissions must be updated on the broker.

**Retry interval always reloads secrets automatically.** Incorrect; it depends on how the client loads credentials.

**Receiving a retry event means restart the container immediately.** Not recommended; this can cause a rebalance storm.

**An event listener is allowed to call KafkaConsumer on any thread.** False; KafkaConsumer is not thread-safe.

**One child's auth retry proves the entire parent stopped.** False; inspect each child/container individually.

**Auth retry handles malformed JSON.** False; deserialization errors require ErrorHandlingDeserializer/error handler.

**Having a success event means consumer lag is 0.** False; backlog may still be large.

**Logging the entire JAAS config helps debug safely.** False; JAAS configs can contain secrets.

## 27. Implementation checklist

- [ ] Set authExceptionRetryInterval when you want the container to retry AuthenticationException/AuthorizationException.
- [ ] Interval is smaller than max.poll.interval.ms.
- [ ] Verify `@KafkaListener` uses the right container factory.
- [ ] Listen for ConsumerRetryAuthEvent.
- [ ] Listen for ConsumerRetryAuthSuccessfulEvent.
- [ ] Distinguish AUTHENTICATION and AUTHORIZATION.
- [ ] Have fallback monitoring on ConsumerStoppedEvent reason AUTH.
- [ ] Keep observers lightweight and thread-safe.
- [ ] Do not log passwords, tokens, JAAS secrets, or private keys.
- [ ] Maintain runbooks for restoring ACLs and credentials.
- [ ] Have a reload/restart mechanism when secrets do not refresh automatically.
- [ ] Monitor group assignment, consumer lag, and offset commits.
- [ ] Avoid incident/restart storms during prolonged retries.
- [ ] Keep business side effects idempotent if records are redelivered.
- [ ] Test auth failure, authz failure, retry success, and the fail-fast path.

## 28. References

- Spring Kafka Reference — Application Events: https://docs.spring.io/spring-kafka/reference/kafka/events.html
- Spring Kafka JavaDoc — ConsumerRetryAuthEvent: https://docs.spring.io/spring-kafka/docs/3.3.2/api/org/springframework/kafka/event/ConsumerRetryAuthEvent.html
- Spring Kafka JavaDoc — ConsumerProperties: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/ConsumerProperties.html

Consult the JavaDoc matching your deployed Spring Kafka version because container APIs, lifecycle reasons, and Spring Boot integrations can vary across release lines.

## 29. Key takeaways

**ConsumerRetryAuthEvent** is Spring Kafka's signal indicating that a consumer hit an **authentication** or **authorization** error and the container **is retrying** per authExceptionRetryInterval. Reason **AUTHENTICATION** points to credentials/TLS/SASL; reason **AUTHORIZATION** points to ACLs, principals, resources, and operations.

**ConsumerRetryAuthSuccessfulEvent** signals that the auth retry path has recovered after an earlier failure. It does not replace proof that the consumer holds partition assignments, that listeners processed records, or that offsets were committed. When no retry interval is configured, the consumer can stop and publish ConsumerStoppedEvent with reason AUTH.

Reliable operations require combining a retry interval smaller than max.poll.interval.ms, lightweight thread-safe observers, least-privilege ACLs, secret management, thresholded alerting, and lag/processing monitoring. Once permissions or credentials are restored, still confirm that the consumer group processes data normally and protect side effects against potential redelivery.
