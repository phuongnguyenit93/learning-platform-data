# Broker Health in Spring Boot

In the **Health and readiness** chapter of the **SPRING_BOOT_OBSERVABILITY** module, broker health is the health status of the message broker that an application depends on to send or receive messages. For Spring Boot using JMS, the broker may be ActiveMQ Artemis, IBM MQ, or another JMS-compatible provider. Checking broker health helps detect disconnections, authentication failures, or an unresponsive broker early before producers/consumers encounter widespread errors.

Broker health is more than "is the socket open?" A broker can be reachable while credentials are invalid, a destination does not exist, publish/consume permissions are missing, or queue backlog grows beyond SLAs. You must select health signals matching the application's role while avoiding having health probes create extra load or letting a flaky dependency trigger continuous restarts across the entire service.

In **SPRING_BOOT_OBSERVABILITY**, broker health should be read alongside metrics, logs, and distributed tracing. The health endpoint returns an overall state for orchestration/monitoring decisions; broker metrics and traces help investigate root causes. This lesson focuses on Spring Boot Actuator `HealthIndicator`, broker connectivity, readiness/liveness, queue signals, timeouts/caching, and practical testing.

## 1. What aspects does broker health cover?

A message broker provides multiple capabilities: accepting connections, authenticating clients, managing destinations, storing messages, delivering messages to consumers, and acknowledging processing. Each capability can fail independently.

| Aspect | Example signal | Operational question |
| --- | --- | --- |
| Connectivity | TCP/JMS connection can be established | Can the application reach the broker? |
| Authentication | JMS connection/session created successfully | Are credentials still valid? |
| Authorization | Producer/consumer permitted to access destination | Are publish/consume permissions correct? |
| Destination availability | Queue/topic exists and is accessible | Is the application sending/receiving on the right destination? |
| Broker capacity | Disk, memory, connection limits | Does the broker have sufficient resources? |
| Queue backlog | Queue depth, oldest message age | Are consumers keeping up with producers? |
| Consumer availability | Consumer count, delivery rate | Are active consumers present? |
| Processing reliability | Redelivery, DLQ rate | Are messages repeatedly failing? |

Not all signals should be checked synchronously inside every HTTP health request. A probe should be short, time-bounded, and check only the conditions necessary for the service to accept traffic or perform its duty.

## 2. Distinguishing broker health from application health

A broker can be healthy while the application fails to process messages due to code bugs, schema mismatches, or a downstream database. Conversely, a broker may lose connectivity briefly while the service still serves other HTTP requests and can retry publishing later.

Distinguish the perspectives:

- **Broker health:** state of the broker/provider and broker resources.
- **Application dependency health:** whether the application can currently perform needed operations with the broker.
- **Messaging flow health:** producer rate, consumer processing rate, backlog, redelivery, and DLQ.
- **Business health:** whether the business workflow completes within SLA.

An Actuator `HealthIndicator` usually reflects dependency health from the application's perspective. Queue depth, oldest message age, and broker disk usage typically require broker management metrics/exporters. Do not infer a healthy broker solely from an UP status caused by an initialized connection factory.

## 3. Spring Boot Actuator and HealthIndicator

Spring Boot Actuator provides the health endpoint and a mechanism to contribute status via `HealthIndicator` or a reactive health contributor. A custom indicator can verify the dependency the application requires.

Example simple indicator for a JMS `ConnectionFactory`:

```java
import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("jmsBroker")
class JmsBrokerHealthIndicator implements HealthIndicator {
    private final ConnectionFactory connectionFactory;

    JmsBrokerHealthIndicator(ConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }

    @Override
    public Health health() {
        try (Connection connection = connectionFactory.createConnection()) {
            connection.start();
            return Health.up()
                    .withDetail("broker", "connection-established")
                    .build();
        } catch (Exception ex) {
            return Health.down(ex)
                    .withDetail("broker", "connection-failed")
                    .build();
        }
    }
}
```

This is an illustrative example of the classic JMS API. With Jakarta JMS, the `jakarta.jms` package fits newer Spring Boot generations; older projects may use `javax.jms`. Creating a connection on every probe can consume resources or add load to the broker, so do not copy this pattern directly into production without designing timeouts, caching, and check frequency.

If the connection factory uses a pooling/caching layer, creating a connection may simply borrow an existing pooled connection and fail to prove the broker responds to a new operation. Understand the semantics of the provider and wrapper before treating a probe as proof of connectivity.

## 4. What should a HealthIndicator check?

| Check | What it confirms | Limitations |
| --- | --- | --- |
| ConnectionFactory bean exists | Spring configured the bean | Does not prove the broker is reachable |
| Create JMS connection | Basic network and provider handshake | May not verify destination permissions |
| Create session | Connection can open a session | Does not prove publish/consume works |
| Publish probe message | Producer can send to test destination | Has side effects and requires cleanup/consumer |
| Consume probe message | Consumer can receive test message | Needs dedicated destination and test protocol |
| Broker management API | Can read broker state/capacity | Requires separate admin credentials/permissions |
| Queue depth/oldest age | Backlog and message age | Usually sourced from broker metrics, not a connection probe |

Do not publish dummy messages to business queues just for health checks. If an end-to-end probe is required, use a dedicated destination, a per-run correlation ID, a short TTL, and a dedicated test consumer; ensure probes are never processed as business events.

## 5. Readiness and liveness are not the same

Kubernetes and orchestration platforms typically distinguish two questions:

- **Liveness:** is the process alive and able to continue running? If it fails repeatedly, the orchestrator may restart the container.
- **Readiness:** should the instance currently accept new traffic/work? If it fails, the instance may be removed from service endpoints without restarting.

A disconnected broker dependency does not necessarily mean the JVM process is hung. Putting broker health into liveness can cause a broker incident to restart every replica at once, creating a reconnect storm and making broker recovery harder.

If the application cannot fulfill its primary role when the broker is unavailable, broker dependency can be placed in readiness. If the service still serves HTTP and only buffers/retries messages temporarily, the readiness decision should rely on actual capabilities and SLAs. There is no single rule for every architecture.

Example health groups configuration:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,jmsBroker
        liveness:
          include: livenessState
```

Group properties and health contributor naming depend on the Spring Boot version. Inspect actual readiness/liveness endpoint output. If the broker is not a mandatory dependency for accepting traffic, do not add it to readiness mechanically.

## 6. When should the broker affect readiness?

Put the broker in readiness when the instance cannot perform its primary work if the broker is unavailable. For example:

- A consumer service whose sole responsibility is receiving and processing messages; without a broker connection, it cannot fulfill its duty.
- A producer API that commits to synchronous publishing without an outbox/buffer fallback; an unavailable broker prevents requests from meeting contract.
- A service requiring an active consumer subscription to complete a mandatory workflow before receiving traffic.

It is not necessarily appropriate to put the broker in readiness if:

- The HTTP API still serves independent features.
- The producer uses a transactional outbox and can persist events to the database for later publishing.
- Clients have bounded retries/buffering and the system tolerates temporary message delay.
- The broker is an optional dependency for a subset of features rather than the whole service.

If a dependency only affects one feature, it can be exposed as a separate health component while overall readiness depends on traffic-serving requirements. Avoid turning every dependency warning into a service-wide DOWN state.

## 7. Queue depth and backlog are not connection health

A broker can accept connections normally while queue backlog keeps growing. For instance, producers send 1,000 messages/minute while consumers only process 700 messages/minute. Connection health may be UP, yet the messaging flow is failing to meet throughput.

Broker signals to monitor:

- Queue depth or pending message count.
- Oldest message age.
- Enqueue/dequeue rate.
- Active consumer count.
- Redelivery count/rate.
- Dead-letter queue depth/rate.
- Broker memory/disk usage and connection count.

A `HealthIndicator` should not query heavy management APIs on every HTTP request. Collect these signals with a broker exporter/management integration, then use metrics dashboards and alerts to observe trends. If backlog breaches SLAs, it can reflect a degraded/readiness state under an explicit policy.

## 8. Timeouts, caching, and health check frequency

Health probes are called frequently by orchestrators and monitoring systems. If every call opens a new connection, the system can generate many simultaneous connection attempts when the broker is slow.

Probe design needs:

1. **Finite timeout:** connection checks must not hang longer than the health endpoint budget.
2. **Bounded concurrency:** prevent bursts of concurrent probes from loading the broker.
3. **Short-term caching:** recent check results can be reused to avoid continuous reconnects, depending on freshness requirements.
4. **Clear failure semantics:** distinguish timeout, authentication, authorization, and destination errors in logs/metrics.
5. **No sensitive details:** never return broker URLs, usernames, passwords, or stack traces to unauthorized callers.

Caching has trade-offs: a recently cached UP result may not reflect a broker that just disconnected; a DOWN result cached too long can delay readiness recovery. Choose TTL according to probe interval, broker recovery time, and operational requirements. A background checker can update the latest status instead of checking the broker synchronously on every health request.

## 9. Preventing health probes from causing a reconnect storm

Suppose 30 replicas lose their broker connection at the same time. If every replica has a readiness/liveness probe every second and each probe creates a new JMS connection, dozens of reconnects per second may occur. Just as the broker recovers, health checks compete for connections with real producers and consumers.

Mitigations:

- Reuse connections or use low-cost provider-native health checks when semantics fit.
- Apply timeouts and backoff to connection attempts.
- Cache probe results with a short TTL and jitter when using a background checker.
- Limit concurrency and frequency of management API calls.
- Separate liveness from dependency checks to avoid restart loops.
- Track health probe duration/error rate as a dedicated signal.

The health endpoint should reflect state, not become a new workload that degrades the dependency.

## 10. Graceful degradation and recovery

When the broker is unavailable, application behavior depends on its role:

**Producer:** may return an error to callers, write events to an outbox, or buffer boundedly in memory/disk per contract. Never hold request threads indefinitely waiting for the broker. When using an outbox, database commits and the publishing worker must be observed separately.

**Consumer:** may pause listeners, reconnect with backoff, let the broker retain messages, or continue independent functions. Avoid continuous error polling that creates log noise.

**Recovery:** after the broker recovers, verify consumer count, queue drain rate, oldest message age, redeliveries, and DLQ. Broker connection UP does not mean the backlog has been cleared.

If queue backlog breaches SLAs, the service may still be healthy at the process level yet degraded at the business flow level. Dashboards should present both states instead of forcing every issue into a single UP/DOWN boolean.

## 11. Logs and metrics for broker health

| Signal | Example | Purpose |
| --- | --- | --- |
| Health check status | UP/DOWN/UNKNOWN | Overall dependency status |
| Probe duration | p95 health check duration | Detect slow checks |
| Connection failures | Count by finite error type | Distinguish network/auth/provider |
| Reconnect attempts | Rate and retry count | Observe recovery behavior |
| Queue depth | Pending messages | Detect backlog |
| Oldest message age | Seconds | Track processing latency SLA |
| Consumer count | Active consumers | Detect inactive listeners |
| Redelivery/DLQ | Rate/count | Detect poison/failing messages |

Do not use full broker URLs, message IDs, per-request dynamic queue names, or exception messages as metric tags. Queue/destination names should be stable and belong to a managed set.

Log events should include service, normalized broker alias, check type, outcome, and error class. Do not log credentials, connection strings with secrets, or raw message payloads.

## 12. Configuration and operation by environment

An application can expose only health and Prometheus while restricting health details:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,prometheus
  endpoint:
    health:
      show-details: when-authorized
      probes:
        enabled: true
```

If using a dedicated readiness group, include the broker component according to the service's role and verify the group endpoint. Do not expose full health component details to public networks.

In test environments, an embedded/test broker or an appropriate Testcontainers provider can verify connection failures, credentials, and listener behavior. Production readiness must be tested with the actual broker provider, network path, and security identity used by the application.

## 13. Testing broker health

| Scenario | Result to verify |
| --- | --- |
| Broker reachable, valid credentials | Indicator UP per chosen semantics |
| Broker unreachable | Indicator DOWN/OUT_OF_SERVICE per policy, finite timeout |
| Wrong credentials | Failure classified, no secrets leaked |
| User lacks destination permissions | Authorization failure distinguished from connectivity |
| Slow broker | Probe duration bounded, does not hang health endpoint |
| Large queue backlog | Queue metrics/alerts reflect degraded flow; not confused with TCP health |
| Consumer count equals 0 | Consumer availability detected if required by role |
| Broker restart | Recovery/reconnect uses backoff, no storm |
| Management API unavailable | Broker health check not confused with management exporter failure |
| Anonymous health caller | Sensitive details hidden |

Tests should not rely on production hostnames or a shared team broker. Use isolated test brokers and controlled states for repeatable results.

## 14. Case study

A system runs 20 replicas of `payment-consumer`. The broker restarts for 45 seconds. The liveness probe currently invokes a custom `HealthIndicator`, and that indicator creates a new JMS connection each time. After the broker recovers, connection attempts surge; several pods restart repeatedly. Queue depth continues climbing because consumers have not caught up with producers.

**Questions:**

1. Why can putting broker connectivity in liveness worsen the incident?
2. How should liveness and readiness be separated for a consumer-only service?
3. Why does a broker connection UP status not prove messaging flow has recovered?
4. Which metrics should be watched during the recovery phase?
5. How should the `HealthIndicator` be redesigned to reduce load?

**Analysis hints:**

- Liveness failures can restart all pods simultaneously, creating a reconnect storm and forcing the recovering broker to handle extra connection attempts.
- Liveness should focus on the process; readiness can depend on the broker if the consumer cannot perform its job when the broker is unavailable.
- A connection only proves partial connectivity/authentication; queue backlog and consumer throughput may still fall short of SLA.
- Watch consumer count, processing rate, queue depth, oldest message age, redeliveries, DLQ, reconnect attempts, and health probe duration.
- Use finite timeouts, bounded concurrency, backoff, and appropriate caching/background status checking; do not create a new connection on every probe tick.

### Completion checklist

| Topic | Can explain/verify |
| --- | --- |
| Broker health dimensions | Connectivity, auth, authorization, destination, and capacity |
| HealthIndicator | Create custom dependency check with timeout |
| Readiness/liveness | Do not use dependency outages as arbitrary restart triggers |
| Queue signals | Distinguish connectivity from backlog/throughput |
| Timeout/cache | Limit health check frequency and load |
| Recovery | Use backoff, avoid reconnect storms, and monitor backlog drain |
| Metrics/logs | Observe probes, reconnects, queue age, redeliveries, and DLQ |
| Security | Never return credentials or sensitive broker details |
| Testing | Verify broker down, auth failure, slow broker, and recovery |

**Key takeaways:** Broker health must reflect the application's ability to use the broker according to its actual role while distinguishing connectivity from queue backlog and consumer processing. Use an Actuator `HealthIndicator` with a finite timeout, protect health details, and weigh carefully whether to include the broker in readiness; avoid placing flaky dependencies in liveness where they cause restart/reconnect storms. Monitor queue depth, oldest message age, consumer count, redeliveries, and DLQ via broker metrics; combine with logs/traces to investigate. When the broker recovers, connection UP is only the first step—verify that consumer throughput and backlog return within SLA.
