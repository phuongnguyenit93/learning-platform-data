# Health Indicator for Kafka Connection

A Spring Kafka application can start successfully, its web server can still return HTTP 200, and the listener container can still exist in the Spring context, yet the connection to the Kafka broker has been lost or the Kafka cluster can no longer serve requests. If the system only checks the JVM/process or an HTTP endpoint, a failing Kafka dependency might not be detected in time.

A **health indicator for Kafka connection** is the mechanism that checks and represents Kafka connectivity status in Spring Boot Actuator. It helps answer the question: can the application communicate with the Kafka cluster using its active configuration and credentials? This signal can be exposed in health endpoints, dashboards, and an appropriate readiness policy.

Be clear about the scope: **Kafka connection health does not mean the entire Kafka workflow is healthy**. An `AdminClient` can query cluster metadata successfully while a consumer has no assigned partitions, a producer lacks write permissions on a topic, a listener is processing slowly, or the database is failing. A health indicator is a scoped check, not an end-to-end proof that every record is processed successfully.

## 1. Where does the health indicator live in Spring Boot?

Spring Boot Actuator provides the health contributor model. A health contributor can be:

- `HealthIndicator`: performs a synchronous check and returns `Health`.
- `ReactiveHealthIndicator`: performs checks using a reactive API.
- `CompositeHealthContributor`: groups multiple contributors.
- Health groups: collections of contributors serving a specific purpose such as readiness or liveness.

Spring Boot can auto-configure health indicators for common dependencies when the required dependency and beans are present. For applications with Spring Kafka and Actuator, supported Spring Boot versions can provide a **Kafka health indicator** backed by `KafkaAdmin`.

Conceptual flow:

~~~text
Kubernetes / Load balancer / Operator
                 |
                 v
          /actuator/health
                 |
                 v
       Spring Boot HealthEndpoint
                 |
                 v
          HealthContributor
                 |
          +------+------+
          |             |
          v             v
     Kafka health    DB health
      indicator      indicator
          |             |
          v             v
     KafkaAdmin      DataSource
          |
          v
     Kafka cluster
~~~

The health endpoint aggregates results from contributors according to status and the status aggregator. Depending on configuration, a contributor can be shown in the response or included in a specific health group.

## 2. What does the Kafka health indicator check?

Spring Boot's built-in Kafka health indicator typically uses **KafkaAdmin/AdminClient** to communicate with the Kafka cluster and query cluster information. Returned information may include the cluster ID and broker nodes, depending on the Spring Boot version.

An `UP` result usually indicates that the health check completed the Kafka Admin operation requested by the indicator within its time limit. This is useful evidence that the connection configuration and Admin communication path to the cluster are working.

It does not by itself prove that:

- The consumer group has been created or has active members.
- The listener has received partition assignments.
- The consumer has permission to read every topic the application needs.
- The producer has permission to write to every output topic.
- Kafka transactions can commit.
- DLT/retry topics have been created with the right partitions and ACLs.
- Database side effects have committed.
- Consumer lag is within SLO.
- Business events have been processed exactly once.

| Check | Can a general Kafka health indicator prove it? |
|---|---|
| Admin connection to the cluster and retrieving cluster metadata | **Yes**, for the specific operation of the indicator |
| Consumer group has the expected assignment | No |
| Records can be read from a specific topic | Not necessarily |
| Records can be written to a specific topic | No |
| Transactional producer commits successfully | No |
| Listener processes records successfully | No |
| Consumer lag is low | No |
| Database and Kafka are consistent | No |

Therefore, naming a dashboard panel **Kafka cluster connectivity** is more accurate than a generic label like "Kafka application fully healthy" if the indicator only checks Admin connectivity.

## 3. Enabling Actuator and the Kafka health indicator

The application needs Spring Boot Actuator and Spring Kafka. With Maven, common dependencies are:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.kafka</groupId>
    <artifactId>spring-kafka</artifactId>
</dependency>
~~~

Spring Boot can provide the Kafka health contributor when `KafkaAdmin` and the appropriate auto-configuration are present. A basic configuration:

~~~yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: when-authorized
  health:
    kafka:
      enabled: true
~~~

`management.health.kafka.enabled` is the property that enables/disables the contributor under Spring Boot's health indicator mechanism in supported versions. If the response does not contain the `kafka` component, check:

1. Is the Actuator dependency on the runtime classpath?
2. Is there a `KafkaAdmin` bean?
3. Is Kafka health auto-configuration excluded?
4. Is `management.health.kafka.enabled` set to `false` in another profile/environment?
5. Does the Spring Boot version provide the Kafka health contributor in the expected way?
6. Does the health endpoint expose component details for the current authorization level?

Do not conclude the indicator is not running just because the default response does not show all details. `show-details` and `show-components` have their own visibility policies.

## 4. Configuring KafkaAdmin and connection properties

The Kafka health indicator can only check using the exact Kafka configuration that `AdminClient` uses. If the broker requires SASL/SSL, credentials and truststore settings must be correct.

Illustrative example of secure connection configuration:

~~~yaml
spring:
  kafka:
    bootstrap-servers:
      - kafka-1.example.internal:9093
      - kafka-2.example.internal:9093
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: >
        org.apache.kafka.common.security.scram.ScramLoginModule required
        username="\${KAFKA_USERNAME}"
        password="\${KAFKA_PASSWORD}";
      ssl.truststore.location: \${KAFKA_TRUSTSTORE_PATH}
      ssl.truststore.password: \${KAFKA_TRUSTSTORE_PASSWORD}
~~~

These values are placeholders; do not commit credentials to source control. In real environments, use a secret manager/Kubernetes Secret and an appropriate rotation policy.

Spring Boot can apply `spring.kafka.properties` as common properties for Kafka clients; separate configuration for Admin, producer, and consumer can be placed under their respective namespaces such as `spring.kafka.admin.properties`, `spring.kafka.producer.properties`, and `spring.kafka.consumer.properties`.

Key point: if the listener uses different credentials or client properties than `AdminClient`, **the Kafka health indicator can be UP while the consumer/producer still fails**. Verify the actual configuration of each client.

### 4.1. Bootstrap servers are not the entire broker topology

A client uses bootstrap servers to initiate a connection and fetch metadata. Afterwards, it can connect to the brokers returned by that metadata. A reachable bootstrap endpoint does not prove every broker, leader, or partition replica is healthy.

A successful metadata fetch in a health check is a cluster reachability signal; it does not replace broker metrics, ISR monitoring, or partition-level diagnostics.

## 5. Reading the health response

An illustrative response:

~~~json
{
  "status": "UP",
  "components": {
    "kafka": {
      "status": "UP",
      "details": {
        "clusterId": "cluster-abc",
        "nodes": 3
      }
    },
    "db": {
      "status": "UP"
    },
    "diskSpace": {
      "status": "UP"
    }
  }
}
~~~

The exact details structure depends on the Spring Boot version and contributor. Do not rely on an unguaranteed field as a stable API if the application needs to parse the health response programmatically.

When Kafka is unreachable, the component can transition to `DOWN` or another status depending on the exception and implementation. The aggregated health endpoint can change the overall status according to `StatusAggregator`.

Common statuses:

| Status | General Meaning |
|---|---|
| `UP` | The component is passing the health check |
| `DOWN` | The component check failed |
| `OUT_OF_SERVICE` | The component should not be used at this time |
| `UNKNOWN` | Status could not be determined |

The overall health status can be affected by other contributors and status aggregator ordering. Do not infer everything from a single component when reading the root `/actuator/health` response.

## 6. Timeouts: health checks must not hang indefinitely

A health indicator calling the Kafka Admin API can become slow because of:

- Unresolvable DNS or bootstrap endpoints.
- TCP connection timeouts.
- Slow or failing TLS handshake or SASL authentication.
- Unresponsive brokers.
- Metadata/describe-cluster requests not completing.
- Network partitions or firewalls dropping packets.

If each probe waits too long, the health endpoint can tie up threads, block other health checks, and cause orchestrators to misjudge application health.

Kafka clients have timeouts such as `request.timeout.ms` and `default.api.timeout.ms`. Suitable bounds can be configured for `AdminClient`:

~~~yaml
spring:
  kafka:
    admin:
      properties:
        request.timeout.ms: 3000
        default.api.timeout.ms: 5000
~~~

These illustrative values need to be tuned for network latency, broker topology, and SLAs. They are not a single timeout covering the entire Spring health endpoint. The health indicator implementation and client API determine which operation is bounded by which timeout.

In addition, Spring Boot can log slow health indicators via slow-indicator logging configuration in supported versions. This logs a warning about check duration; it does not automatically cancel a blocked health check.

**Do not set timeouts too short just to make probes return fast.** If the timeout is lower than normal cluster latency, health will flap.

## 7. Distinguishing connection health from readiness

Readiness answers the question: **is this instance ready to accept the type of work the system assigns to it?**

Kafka connection health is a potentially useful input, but it is not complete readiness.

Examples:

- An HTTP service that only uses Kafka to emit asynchronous events: Kafka unavailability may break the contract of some APIs, while other read-only endpoints continue working.
- A consumer worker that needs Kafka to receive work: losing Kafka can prevent the worker from continuing work.
- A service connected to the cluster that has not yet been assigned partitions: Admin health can still be `UP`, while the consumer is not actually processing records yet.
- A service with a running listener whose database is down: Kafka health is `UP`, yet business readiness may still be `DOWN`.

Readiness should be based on the **business capability** the instance commits to providing, not just a network connection.

## 8. Distinguishing readiness and liveness

Spring Boot Actuator supports health groups for Kubernetes probes in modern versions.

~~~text
Kubernetes
    |
    +---- liveness probe
    |        |
    |        v
    |    /actuator/health/liveness
    |
    +---- readiness probe
             |
             v
         /actuator/health/readiness
~~~

- **Liveness:** is the process alive and capable of continuing to operate?
- **Readiness:** should the instance receive traffic/new work under the application contract?

An external Kafka broker failure should usually **not automatically mark liveness DOWN**. If failing liveness causes Kubernetes to restart all Pods during a Kafka cluster outage, restarts will not fix the broker and can trigger a connection storm/rebalance.

Readiness may include Kafka if the service truly cannot serve work when Kafka is unavailable. However, for a consumer-only worker, HTTP readiness does not directly stop the Kafka consumer or revoke partitions; you need to understand how the orchestrator and listener lifecycle control each other.

### 8.1. Configuring health probes

Example enabling probe groups:

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
          include: readinessState,kafka
~~~

The configuration above illustrates including the Kafka indicator in the readiness group. Use this only if the service policy requires the instance to be unready when the Kafka connection fails.

Do not add `kafka` to the liveness group just because Kafka is an important dependency. A broker outage is not evidence that the JVM is deadlocked or the process needs a restart.

If the application has multiple capabilities, you can create separate custom groups such as `kafkaConnectivity` or `messagingReadiness` so operators can inspect dependency health without forcing all traffic readiness to depend on it.

### 8.2. Worker readiness is not the same as HTTP API readiness

For a Kafka-consuming service, the HTTP readiness endpoint may only serve Kubernetes rollout/monitoring; Kafka brokers do not use this endpoint to assign partitions. If you want to pause consuming when a dependency is unready, you need a separate mechanism to control the listener container (pause/stop/start) and a recovery policy.

Do not assume `readiness=DOWN` automatically calls `KafkaListenerEndpointRegistry.stop()`. The two mechanisms are not linked unless the application configures orchestration.

## 9. Built-in health indicator vs. custom health indicators

The built-in health indicator is usually sufficient to answer **whether the Kafka cluster is reachable via the Admin API**. Some applications need deeper checks:

- Do required topics exist?
- Does the consumer group have assignments?
- Does the producer have permission to write to the output topic?
- Do DLT and retry topics have valid metadata?
- Can a canary event be published and consumed?

Do not turn all of those checks into a single health check running every few seconds. Each deep check can generate traffic, require different ACLs, cause side effects, or over-couple the health endpoint to external systems.

### 9.1. When is a custom HealthIndicator needed?

Use a custom indicator when there is a **specific business capability** that the built-in check does not verify. For example, a service that must read metadata for the `payments.authorized` topic or requires producer/consumer credentials different from `AdminClient`.

A custom check should:

1. Use the exact credentials/client configuration of the capability being verified.
2. Have a finite timeout.
3. Not send synthetic business events to real topics on every probe.
4. Not commit offsets or mutate business state.
5. Not create a new producer/consumer on every health call if resources can be safely reused.
6. Emit metrics/logs for the health check itself.
7. Distinguish `DOWN` for transient failures from `UNKNOWN` when the result is indeterminate.

### 9.2. Example custom AdminClient health check

You can create a shared `AdminClient` using `KafkaAdmin`'s configuration and close it on Spring context shutdown. The following example illustrates checking cluster metadata with a finite timeout:

~~~java
import java.util.Collection;
import java.util.concurrent.TimeUnit;

import org.apache.kafka.clients.admin.AdminClient;
import org.apache.kafka.clients.admin.DescribeClusterResult;
import org.apache.kafka.common.Node;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.kafka.core.KafkaAdmin;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;

@Configuration
class KafkaHealthAdminConfiguration {

    @Bean(destroyMethod = "close")
    AdminClient healthAdminClient(KafkaAdmin kafkaAdmin) {
        return AdminClient.create(kafkaAdmin.getConfigurationProperties());
    }
}

@Component("kafkaConnection")
class KafkaConnectionHealthIndicator implements HealthIndicator {

    private final AdminClient adminClient;

    KafkaConnectionHealthIndicator(AdminClient adminClient) {
        this.adminClient = adminClient;
    }

    @Override
    public Health health() {
        try {
            DescribeClusterResult result = adminClient.describeCluster();

            String clusterId =
                    result.clusterId().get(3, TimeUnit.SECONDS);

            Collection<Node> nodes =
                    result.nodes().get(3, TimeUnit.SECONDS);

            return Health.up()
                    .withDetail("clusterId", clusterId)
                    .withDetail("brokerCount", nodes.size())
                    .build();
        } catch (Exception exception) {
            return Health.down(exception).build();
        }
    }
}
~~~

Verify this example against the exact Spring Kafka/Kafka client API version of your application; if your version does not expose the configuration retrieval method shown above, create `AdminClient` from the same property set managed by the application's configuration. Do not hard-code a new bootstrap server and inadvertently omit SASL/SSL credentials.

This is a **custom indicator** with ID `kafkaConnection`; if the built-in Kafka indicator is already registered, the two checks may overlap in functionality. Keep both only when they serve distinct purposes and operators understand the difference.

This health indicator only checks Admin API/cluster metadata. It still does not prove that the producer has `WRITE` permission or the consumer has `READ` permission on business topics.

### 9.3. A topic metadata check is not a produce/consume canary

A custom check using `AdminClient.describeTopics` can confirm that a topic exists and metadata is accessible. However, that does not prove the application can publish records to the topic if `WRITE` ACLs are denied.

A real produce/consume test requires a canary topic, key, consumer group, cleanup/retention, and a process that produces no business side effects. It should run **periodically as synthetic monitoring** with its own timeout, not on every Kubernetes readiness probe.

## 10. Health checks and security

The health endpoint can expose:

- Broker hostnames and cluster topology.
- Topic names and consumer groups.
- Exception messages containing hostnames, credential paths, or sensitive content.
- Network/security configuration details.

In production, do not expose `show-details=always` to all callers. A cautious configuration:

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
~~~

Actuator endpoints can be restricted using network policies, authentication, and a separate management port depending on architecture. If the health endpoint is used by Kubernetes probes, ensure kubelet can reach it without exposing details to external users.

Health indicators should never return passwords, JAAS configs, tokens, SASL payloads, or full client properties inside `details`.

## 11. Kafka health is UP, yet the listener still processes no records

This is a commonly misunderstood scenario.

~~~text
/actuator/health:
  kafka = UP

Kafka consumer:
  container = RUNNING
  assignment = empty
  records processed = 0
  lag = increasing
~~~

Possible causes:

- The consumer group has not finished rebalancing.
- Wrong topic subscription, or the topic lacks appropriate partitions.
- More consumers than partitions, leaving some consumers unassigned.
- The consumer uses separate authentication/authorization from `AdminClient`.
- The container is paused.
- Deserialization or listener errors.
- The listener is taking too long to process a record.
- `max.poll.interval.ms` was exceeded.
- Offset commit or transaction failures.

An Admin connection health indicator succeeding does not check any of the states above. Diagnosis requires consumer group metrics, listener container state, rebalance events, lag, logs, and traces.

## 12. Producer health differs from Admin connection health

An application can use:

- `AdminClient` to describe the cluster and create topics.
- Producer to send events.
- Consumer to read events.

The three clients may share bootstrap servers while having separate credentials, ACLs, and properties.

For example, Admin health is `UP` while the producer encounters:

- `TopicAuthorizationException` due to missing WRITE permission.
- `RecordTooLargeException` because the payload exceeds limits.
- Serializer exceptions.
- `ProducerFencedException` because the transactional ID was fenced.
- Timeouts or broker errors on send requests.

Similarly, the consumer can hit `TopicAuthorizationException` when reading or deserialization failures even while `AdminClient` can still query the cluster.

If a business capability requires publishing, use producer-specific telemetry or a controlled synthetic canary. Do not infer publish health from Admin health.

## 13. Health indicators and consumer group assignment

Consumer group assignment is dynamic state. A service can connect to brokers successfully without owning any partitions yet.

If readiness depends on the consumer holding assignments, build a dedicated signal based on the listener/container and rebalance callbacks, for example:

- The container has started.
- The consumer has joined the group.
- Partition assignment matches the topology.
- The listener can poll and make progress.
- Consumer lag does not exceed a defined threshold.

Do not mechanically apply `assignmentCount > 0` to every service. If a group has 2 partitions and 5 consumers, three idle consumers can still be normal; if a service handles a low-traffic topic, assignment and record traffic are also separate concepts.

With concurrent containers, track parent/child containers and partition ownership at the proper scope. Do not use the count of `ConsumerStartedEvent` as the number of assigned partitions.

## 14. Do not arbitrarily add external dependencies to liveness

Suppose the Kafka cluster loses connectivity for 90 seconds:

~~~text
Kafka broker outage
      |
      +---- Kafka health = DOWN
      |
      +---- liveness = UP
      |
      +---- readiness may be DOWN per policy
      |
      +---- Kubernetes does not restart all Pods just for a dependency outage
      |
      +---- application waits for the broker to recover and continues
~~~

If Kafka is included in liveness, Kubernetes can restart every instance during a broker outage. Repeated restarts create connection churn, consumer group rebalances, and increased startup load, without fixing Kafka.

Liveness should detect unrecoverable process states such as severe deadlocks or an application no longer making progress under its contract. A temporarily unavailable external dependency is normally a reason to alert or adjust readiness, not automatically kill the JVM.

## 15. Timeouts, flapping, and hysteresis

Health indicators are invoked periodically. If the Kafka network is unstable, status can oscillate:

~~~text
UP -> DOWN -> UP -> DOWN -> UP
~~~

Flapping status can cause alerts to continuously open/close, readiness to toggle repeatedly, or rollouts to be disrupted.

Ways to reduce noise:

- Set request/connect timeouts aligned with real-world latency.
- Alert on sustained duration rather than a single failed sample.
- Distinguish transient failures from permanent authentication/authorization failures.
- Use bounded retry/backoff at the health operation layer where appropriate, without creating a request storm.
- Separate connectivity signals from business readiness.
- Track duration and consecutive failure/recovery counts.

Do not cache `UP` so long that it hides an outage. If hysteresis is used, explicitly document maximum detection latency and trade-offs.

## 16. Health indicators should not create heavy load or side effects

The health endpoint can be called repeatedly by Kubernetes, load balancers, monitoring systems, and operators. If every call creates a new producer/consumer, sends a canary record, creates a topic, or reads large amounts of data, health checks themselves can overload the cluster.

Best practices:

1. Prefer the built-in Admin connectivity check when the goal is simply reachability.
2. Use clients with managed lifecycles and proper closing.
3. Keep request counts and timeouts small and finite.
4. Do not generate business records on every probe.
5. Do not perform expensive topic scans or describe every consumer group unnecessarily.
6. Move synthetic produce/consume tests to a separate schedule.
7. Ensure failed health checks do not alter offsets or business state.

## 17. Custom health status by capability

An application can define multiple health groups instead of overloading a single `kafka` component with every meaning.

Examples:

~~~text
/actuator/health
/actuator/health/liveness
/actuator/health/readiness
/actuator/health/kafkaConnectivity
/actuator/health/messagingReadiness
~~~

- `kafkaConnectivity`: the Admin API can connect to the cluster.
- `messagingReadiness`: the capabilities the service needs to consume/publish per policy.
- `readiness`: the instance can receive traffic/work per the service contract.
- `liveness`: the process can continue running.

Health groups let operators view distinct perspectives. Do not wire custom groups into liveness/readiness automatically without understanding how the orchestrator reacts.

## 18. Kubernetes probes with Spring Boot

Example configuring probe groups and additional paths in supported Spring Boot versions:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,kafka
~~~

Additional paths are typically `/livez` and `/readyz` on the main server port when enabled. If Actuator is exposed only on a separate management port, verify that kubelet can reach the right port/path.

A readiness probe failure typically removes the Pod from traffic-serving endpoints; a liveness probe failure can cause the container to restart. Do not let a broker outage cause a restart storm.

### 18.1. Example Kubernetes deployment

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
        failureThreshold: 30
        periodSeconds: 5
      livenessProbe:
        httpGet:
          path: /actuator/health/liveness
          port: http
        periodSeconds: 10
      readinessProbe:
        httpGet:
          path: /actuator/health/readiness
          port: http
        periodSeconds: 5
~~~

This is an example deployment; adjust ports, paths, and startup budget to match the application. `startupProbe` protects slow startup phases; it does not replace Kafka readiness checks. For a worker-only service, evaluate whether HTTP readiness is truly the required orchestration signal or whether custom status/metrics for the consumer lifecycle should be used.

## 19. Logging and metrics for health checks

The health endpoint is a point-in-time snapshot; historical visibility requires separate metrics/logs.

Suggested metrics instrumented by the application/monitoring:

| Metric | Meaning |
|---|---|
| `app.kafka.health.checks` | Number of health checks executed |
| `app.kafka.health.failures` | Number of failed health checks |
| `app.kafka.health.duration` | Duration of the health operation |
| `app.kafka.health.status` | Latest status if represented as a gauge/state |
| `app.kafka.admin.request.errors` | Admin API request errors by type |

Do not put exception messages or constantly changing broker node IDs into metric labels. Use structured logs for error details:

~~~text
event=dependency_health_check
dependency=kafka
indicator=kafka
status=DOWN
operation=describe_cluster
error_category=timeout
duration_ms=5000
instance=payment-worker-2
~~~

These fields are application-emitted metadata, not Actuator's default response. Do not log credentials, SASL configs, or secrets.

### 19.1. Distinguishing health failures from business failures

A Kafka connection health check can be `UP` while DLT publishing fails because of a missing ACL on the DLT topic. Do not merge the two metrics:

- `kafka_cluster_connectivity`: Admin API reachability.
- `dlt_publish_failures`: recovery publishing outcomes.
- `consumer_processing_failures`: business listener outcomes.
- `consumer_lag`: backlog.
- `kafka_transaction_commit_failures`: transaction outcomes.

Each metric represents a different capability. Dashboards should display them side by side instead of a single health badge.

## 20. Integration tests for the Kafka health indicator

A meaningful test must run the health endpoint against a real Kafka broker, such as Kafka Testcontainers or Embedded Kafka.

Basic test cases:

1. **Broker available:** the Kafka health component returns `UP`.
2. **Broker unavailable:** the health check returns a failure status per implementation.
3. **Broker restart:** health recovers after the client reconnects.
4. **Invalid authentication:** Admin health reflects credential errors.
5. **Timeout:** the health operation finishes within a finite budget.
6. **Custom topic check:** valid vs. missing topic metadata is distinguished.
7. **Different ACLs:** Admin health can be `UP` while producer/consumer capabilities are denied.
8. **Readiness policy:** Kafka `DOWN` changes readiness per configuration while liveness stays `UP`.
9. **Multiple clusters:** the indicator distinguishes clusters/aliases if the service connects to multiple Kafka clusters.
10. **Health endpoint security:** details are visible only to authorized principals.

Example health endpoint test:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class KafkaHealthIndicatorIT {

    @Autowired
    MockMvc mvc;

    @Test
    void kafkaComponentIsUpWhenBrokerIsAvailable() throws Exception {
        mvc.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.components.kafka.status")
                        .value("UP"));
    }
}
~~~

Imports and Testcontainers setup are omitted; a real broker must be wired into the application context. If health details are hidden or the endpoint returns a different structure depending on Spring Boot version, the test should use appropriate credentials or call the exposed health group/component according to its contract.

### 20.1. Do not test outages solely by mocking the indicator

Mocking `KafkaHealthIndicator.health()` to return `DOWN` only proves the endpoint aggregates statuses. It does not prove `AdminClient` timeouts, broker reconnects, SSL/SASL, or health contributor auto-configuration work properly.

Use unit tests for status aggregation; use integration tests with a broker/container/proxy to verify network and Kafka client behavior.

### 20.2. Verify there are no side effects

A health check must not produce business records or commit offsets. In integration tests, verify that repeated health polling does not alter topic offsets, business tables, or consumer group state beyond expected metadata operations.

## 21. Common diagnostic scenarios

| Observation | Possible Interpretation | Investigation Direction |
|---|---|---|
| Kafka health `DOWN`, listener container still `RUNNING` | Container object is still running, but Admin connectivity is failing | Broker/network/auth, client logs, reconnect |
| Kafka health `UP`, consumer has no assignment | Admin API works; group/consumer state has an issue or hasn't rebalanced yet | Group state, subscription, partitions, ACLs |
| Kafka health `UP`, producer send fails | Admin and producer capabilities differ | Producer ACLs, serializer, transactions, record size |
| Kafka health `UP`, consumer fetch fails | Consumer credentials/permissions differ from Admin | READ ACL, group ACL, deserializer, poll |
| Kafka health `UP`, lag increasing | Slow consumer, paused container, or upstream traffic spike | Processing timer, lag per partition, pause, DB |
| Kafka health `DOWN` flapping | Network/timeout or overly sensitive probe threshold | Request latency, timeouts, broker events |
| Readiness `DOWN`, liveness `UP` | Dependency/service capability unready, but process is alive | Readiness policy and dependency recovery |
| All Pods restarting on liveness during Kafka outage | Kafka was mistakenly added to liveness or health aggregation | Decouple liveness from dependency health |

Do not use a `DOWN` status to automatically restart the application before knowing whether the failure is in the process or the dependency. A restart can help with certain internal faults, but it will not fix incorrect ACLs or a broker outage.

## 22. Common mistakes

- **Treating Kafka health `UP` as consumer processing healthy:** the indicator may only check Admin connectivity.
- **Treating Kafka health `DOWN` as requiring a JVM restart:** an external dependency may be temporarily unavailable.
- **Putting Kafka into liveness by default:** easily triggers a restart storm during cluster failures.
- **Putting Kafka into readiness without defining the business contract:** may pull all Pods from traffic even when some functions still work.
- **Assuming readiness `DOWN` automatically stops Kafka listeners:** health groups and container lifecycle are two separate mechanisms.
- **Checking only the bootstrap endpoint:** returned metadata may route clients to another unreachable broker.
- **Using an `AdminClient` check to conclude the producer has WRITE permission:** ACLs can differ per operation/topic.
- **Creating a new `AdminClient` on every probe:** increases connection churn and leaks resources if not closed.
- **Omitting finite timeouts:** the health endpoint can hang and affect other probes.
- **Setting timeouts too short:** health flaps even while the cluster operates normally.
- **Exposing health details publicly:** leaks broker topology or exception metadata.
- **Checking the health endpoint only once at startup:** misses outages that happen later.
- **Using health checks to continuously send business canaries:** creates side effects and unnecessary load.
- **Not testing different ACLs across Admin/Producer/Consumer:** `UP` health masks capability failures.
- **Using health indicators instead of consumer lag and DLT metrics:** misses processing progress and business reliability.

## 23. Production checklist

Before using a Kafka health indicator to drive deployment or traffic, verify:

1. Is the Kafka health contributor actually auto-configured in this Spring Boot version?
2. Does it check Admin cluster metadata or another capability?
3. Does `AdminClient` use the right bootstrap servers, SASL/SSL credentials, and timeouts?
4. Do producers and consumers use different credentials/ACLs than `AdminClient`?
5. Should the Kafka indicator be included in the readiness group?
6. Is it strictly necessary for liveness, and why?
7. For a consumer-only worker, how does HTTP readiness affect rollouts/traffic?
8. Does the health endpoint have finite timeouts and avoid blocking threads for too long?
9. Are `UP`, `DOWN`, `OUT_OF_SERVICE`, and `UNKNOWN` appropriately distinguished?
10. Are health details protected from unauthorized callers?
11. Are there historical metrics/logs for health transitions and probe latency?
12. Are there separate consumer lag, assignment, producer error, transaction failure, and DLT metrics?
13. Are custom health indicators added only when a specific capability needs verification?
14. Do synthetic produce/consume checks use a canary topic on a schedule rather than on every probe?
15. Have broker outage, restart, auth failure, timeout, ACL, and recovery been tested with a real broker?
16. When Kafka is unavailable, can the process stay alive and recover without a restart storm?

A **health indicator for Kafka connection** provides an important signal about an application's ability to communicate with the Kafka cluster, typically via `KafkaAdmin`/`AdminClient`. It helps detect dependency outages and integrates with Actuator/Kubernetes health groups, but it only proves the operations the indicator actually executes. To assess whether a service can consume, produce, and handle business logic properly, complement it with consumer assignment, lag, producer/transaction metrics, DLT status, business readiness, and integration tests. Separating connectivity, readiness, and liveness enables the system to respond properly to Kafka incidents without turning a broker outage into an application-wide restart loop.

