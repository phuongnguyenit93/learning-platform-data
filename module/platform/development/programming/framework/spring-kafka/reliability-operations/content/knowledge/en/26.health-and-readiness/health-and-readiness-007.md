# Authorization Failure

A Spring Kafka application can connect successfully to a Kafka broker, complete the TLS/SASL handshake, and still not be allowed to read a topic, join a consumer group, or write records to a Dead Letter Topic (DLT). This is an **authorization failure**: the broker has identified the client's principal, yet the ACL/authorizer policy does not allow that principal to perform the operation on the corresponding resource.

In operations, this error often appears after deploying a new service, changing `group.id`, adding a topic or DLT, changing principals across environments, or modifying service account permissions. An application can still start and its health endpoint can still return `UP` while the listener cannot consume. Therefore, you must distinguish **authentication** (who is the client?) from **authorization** (what is the client allowed to do?), identify the exact denied resource/operation, and reflect that state accurately in readiness.

## 1. How do authentication and authorization differ?

Kafka protects connections across multiple layers. TLS can encrypt traffic and authenticate certificates; SASL can authenticate principals; the authorizer checks permissions on cluster resources.

| Concept | Question | Example Error |
|---|---|---|
| TLS / transport security | Can a secure channel be established and the certificate trusted? | Certificate expired, wrong truststore, hostname verification failed |
| Authentication | How does the client prove its principal identity? | Wrong SASL password, mechanism mismatch, invalid certificate |
| Authorization | Does the authenticated principal have permission to perform the operation on the resource? | `TopicAuthorizationException`, `GroupAuthorizationException` |

Example:

```text
Spring Kafka application
       |
       | TLS + SASL handshake
       v
Kafka broker authenticates principal:
       User:orders-service
       |
       v
Authorizer checks ACLs
       |
       +--> READ topic orders?  ALLOW
       +--> READ group orders-worker? DENY
       |
       v
GroupAuthorizationException
```

In this example, the password and SASL mechanism can be completely correct. The failure lies in the permission on the `Group` resource, not in the secret. Changing the password or restarting the pod will not automatically grant `READ` permission on the consumer group.

## 2. Common authorization exceptions

The Kafka client provides specific exceptions by resource type or operation. Common ones in Spring Kafka applications include:

| Exception | Typical Meaning | Where to Check |
|---|---|---|
| `TopicAuthorizationException` | Principal is not allowed to perform an operation on one or more topics | ACLs of source topic, output topic, retry topic, or DLT |
| `GroupAuthorizationException` | Principal is not allowed to use the consumer group | `READ` ACL on the corresponding group |
| `ClusterAuthorizationException` | Principal is not allowed to perform a cluster-level operation | ACL/permissions for cluster-level operations or admin requests |
| `TransactionalIdAuthorizationException` | Producer is not allowed to use the transactional ID | `WRITE` ACL on the `TransactionalId` resource |
| `DelegationTokenAuthorizationException` | Missing permissions for the corresponding delegation token operation | Delegation token policy and principal |

Exact exception names and operations depend on the rejected Kafka request. Sometimes the framework wraps an exception inside another exception; find the **root cause** rather than reading only the outermost exception layer.

Do not confuse these exceptions with connectivity errors such as `TimeoutException`, DNS failures, `SaslAuthenticationException`, or SSL errors. A timeout can hide the fact that the client is retrying a rejected request, but it is not enough on its own to conclude an ACL is missing.

## 3. Kafka ACLs bind to resources and operations

The Kafka authorizer decides permissions based on principal, resource, operation, host, and policy. For consumption flows, key resources are usually **Topic** and **Group**:

| Flow | Resource | Typically Required Operations |
|---|---|---|
| Reading records from a source topic | `Topic: orders` | `READ`; may also need `DESCRIBE` depending on operation/config |
| Joining a group and committing offsets | `Group: orders-worker` | `READ` |
| Writing results to another topic | `Topic: order-results` | `WRITE`; may also need `DESCRIBE` |
| Writing records to a DLT | `Topic: orders.DLT` | `WRITE`; may also need `DESCRIBE` |
| Writing a Kafka transaction | `TransactionalId: orders-tx-*` | `WRITE`; some operations/versions may require extra permissions |
| Creating topics or changing configs | Topic/Cluster | `CREATE`, `ALTER`, `ALTER_CONFIGS` per policy |

Operations and inheritance relationships among ACLs depend on the Kafka authorizer/version. For example, some operations implicitly imply `DESCRIBE`. Never grant `ALL` just to make an error disappear; identify the specific rejected request and grant the minimum required permission.

A consumer principal that only has `READ` on the topic while lacking `READ` on the group still cannot join the consumer group. Conversely, having group permission without topic permission still prevents fetching data. Both sides must be checked.

## 4. Where in the lifecycle can authorization errors occur?

Not every authorization error appears immediately at application context startup. Some requests are only sent when the listener subscribes, fetches metadata, joins the group, commits offsets, or when the producer executes a send.

```text
Application start
       |
       v
ConsumerFactory creates KafkaConsumer
       |
       v
subscribe / metadata / join group
       |
       +--> GroupAuthorizationException
       |
       v
poll / fetch records
       |
       +--> TopicAuthorizationException
       |
       v
Listener processes record
       |
       v
Producer sends output or DLT
       |
       +--> TopicAuthorizationException
       +--> TransactionalIdAuthorizationException
```

Therefore, a successfully created `KafkaTemplate` bean does not prove the principal can write to every topic. An initialized `KafkaConsumer` also does not prove topic/group permissions have been fully checked. Only an actual attempt using the exact principal, resource, and operation confirms the required permission.

## 5. Identifying the exact principal seen by Kafka

Before modifying ACLs, you need to know which principal the broker sees for the request. In environments with multiple clusters or multiple listener factories, consumer and producer principals can even differ.

Check:

1. Actual `security.protocol` (`SASL_SSL`, `SSL`, or corresponding configuration).
2. `sasl.mechanism` and JAAS/client login config used by consumer/producer.
3. Certificate subject or SASL principal mapping if using TLS/SASL.
4. `client.id`, consumer group, and transactional ID to correlate broker/client logs.
5. Secret version, workload identity, or service account attached to that deployment.

Never print passwords, JAAS configs containing secrets, private keys, tokens, or entire environments into logs. To verify a principal, use broker audit logs or protected observability mechanisms; log only controlled principal names containing no credentials.

A common mistake is when the consumer uses principal `User:orders-service`, while the DLT producer uses another principal `User:orders-publisher`. If permissions are granted only to the consumer principal, reading the source topic succeeds while recovery publishing still fails.

## 6. Granting least-privilege permissions for consumers

A consumer group needs permission to read the source topic and permission to use the group. The example below illustrates ACL commands using `kafka-acls.sh` with a hypothetical principal `User:orders-service`:

```bash
# Permission to read the source topic
kafka-acls.sh --bootstrap-server kafka.example:9093 \
  --add --allow-principal User:orders-service \
  --operation Read --topic orders

# Permission to join the consumer group
kafka-acls.sh --bootstrap-server kafka.example:9093 \
  --add --allow-principal User:orders-service \
  --operation Read --group orders-worker
```

These are illustrative administrative commands; use your environment's bootstrap endpoint and administrative authentication mechanism, which may require `--command-config` pointing to a protected client config file. Never place passwords directly on the command line or in source control. `DESCRIBE` permission may be required depending on the request, Kafka version, and authorizer policy.

If topics are managed by a platform team, applications should not hold `CREATE`/`ALTER` permissions just so consumers can start. Topics should be provisioned beforehand through infrastructure workflows, with retention, partitions, replication, and ACLs reviewed.

## 7. Producers and DLTs need separate permissions

A consumer can read a source topic normally, yet hit an authorization failure when a record fails and `DeadLetterPublishingRecoverer` sends to the DLT. At that point, the issue is not the source consumer's `READ` permission; it is the producer principal's publish permission on the DLT.

| Flow | Possible Principal | Permissions to Check |
|---|---|---|
| Consume `orders` | Consumer principal | `READ` topic `orders`, `READ` group `orders-worker` |
| Publish `order-results` | Producer principal | `WRITE` topic `order-results` |
| Publish `orders.DLT` | DLT producer principal | `WRITE` topic `orders.DLT` |
| Publish `orders-retry` | Retry publisher principal | `WRITE` topic `orders-retry` |
| Kafka transaction | Transactional producer principal | `WRITE` transactional ID and permissions on related topics |

Even if `KafkaTemplate` and the consumer share a principal, permissions must still be granted on each resource. If two different security configs are used, confirm the principal for **the exact producer factory** used by the DLT template.

When DLT publishing fails, recovery is not necessarily complete. If the recoverer is configured to wait for the send result and fail on send error, the error handler can retry recovery per policy; the source offset must not be treated as recovered merely because a destination was selected. Log source coordinates, DLT destination, principal, and root exception, then verify committed offsets and actual DLT records.

## 8. Authorization with Kafka transactions

A transactional producer adds a `TransactionalId` resource. An application may have `WRITE` permission on the output topic yet lack permission to use the transactional ID, leading to `TransactionalIdAuthorizationException` when initializing or executing a transaction.

Example consume-transform-produce flow:

```text
Consumer principal
  READ source topic
  READ consumer group
          |
          v
Listener + Kafka transaction manager
          |
          v
Transactional producer principal
  WRITE transactional ID
  WRITE output topic
          |
          v
Commit output + input offset in Kafka transaction
```

With Spring Kafka, `transactionIdPrefix` generates transactional IDs for producer instances. The prefix must be designed not to collide across concurrent instances; however, **setting a unique prefix does not replace ACLs**. The authorizer must grant the principal permission to use the corresponding range of transactional IDs. If the prefix changes after a deployment, ACL resource patterns may stop matching.

During transaction commit/abort, topic and transactional ID permissions must match the design. Never grant cluster-wide `ALL` just to fix a transactional ID error; use a narrow resource pattern and check permissions for the real principal/ID.

## 9. Spring Boot security configuration

A SASL/SSL consumer configuration can be supplied via Spring Boot properties. Illustrative example using environment variables for secrets:

```yaml
spring:
  kafka:
    bootstrap-servers: kafka.example:9093
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: >-
        org.apache.kafka.common.security.scram.ScramLoginModule required
        username="${KAFKA_USERNAME}"
        password="${KAFKA_PASSWORD}";
    consumer:
      group-id: orders-worker
      enable-auto-commit: false
```

This example only illustrates the configuration mechanism; the SCRAM mechanism, JAAS module, truststore, and property binding must match your cluster. In production, inject secrets from a secret manager/Kubernetes Secret or workload identity per organizational standards. Never write real values into YAML in Git.

If the producer uses a separate security configuration, configure `spring.kafka.producer.properties` or the corresponding producer factory. A custom `KafkaTemplate`/`ProducerFactory` might not inherit the configuration used by the consumer. Inspect bean wiring instead of assuming a single security block applies to every client.

## 10. `authExceptionRetryInterval` in Spring Kafka

When a container encounters an authorization exception, the default behavior in supported Spring Kafka versions is to stop the consumer/container unless an appropriate retry mechanism is configured. Since Spring Kafka 2.8, `ContainerProperties` has the **`authExceptionRetryInterval`** property so the container can retry after an interval upon encountering supported authorization errors.

Example:

```java
ContainerProperties properties = factory.getContainerProperties();
properties.setAuthExceptionRetryInterval(Duration.ofSeconds(30));
```

The retry interval should be chosen deliberately and according to the documentation of your exact version. Specifically, do not assume this property fixes all authentication errors such as a wrong SASL password or failed TLS handshake. An **authorization failure** can be resolved by changing ACLs at runtime; an **authentication failure** typically requires fixing credentials/certificates/configs and may have different stop semantics.

A retry interval does not grant permissions, does not make the broker bypass ACLs, and does not guarantee the listener is ready. It only allows the container to retry in framework-supported cases. If ACLs are not fixed, the application can emit repeated error logs on each cycle; alerting, sensible backoff, and log-storm prevention are required.

## 11. Is retrying authorization suitable for every listener?

Choose behavior based on how your organization grants permissions and your SLOs:

| Situation | Approach |
|---|---|
| ACLs may be granted within a few minutes after deploy | `authExceptionRetryInterval` can let the container retry while readiness reflects unready |
| Permanently wrong principal/secret | Fix identity/secret; do not rely on continuous retries |
| Deleted or misspelled topic/group | Fix config/resource; retrying auth does not resolve resource mismatches |
| DLT producer missing permissions | Fix the producer principal's publish permissions; ensure recovery does not miscommit offsets |
| ACLs revoked while the app is running | Monitor exceptions, container state, and readiness; prepare to restore permissions |
| Prolonged authorization failure | Alert and keep the instance out of readiness if the consumer is mandatory |

Retries should have a cadence aligned with the platform team's response time. Looping every few milliseconds only inflates logs and broker requests. Conversely, an overly long retry interval delays recovery after ACLs are fixed. Pick a value based on SLOs, consumer count, and how the cluster propagates ACLs.

## 12. Readiness and liveness must reflect the failure accurately

For a consumer service, the process can stay alive while the listener cannot read the topic due to an authorization failure. This is a crucial difference between **liveness** and **readiness**:

| Probe | Question | When Kafka authorization fails |
|---|---|---|
| Liveness | Is the JVM/process still running and able to continue on its own? | Usually remains `UP`; do not restart solely for missing ACLs |
| Readiness | Can the instance perform its required function right now? | Can be `DOWN` if the listener is a mandatory dependency |
| Startup | Has the application finished initial startup? | Depends on startup policy; do not turn temporary ACL issues into an infinite restart loop |

If the liveness probe fails on authorization, Kubernetes can repeatedly restart the pod even though the cause is a broker ACL. Restarting does not grant new permissions and can create extra group churn. Readiness is more appropriate for taking the instance out of traffic when an essential consumer cannot operate.

However, an HTTP API and a Kafka consumer in the same process can have different readiness requirements. If the instance still serves an independent API and the consumer is only an auxiliary workload, marking the entire application `DOWN` may be unnecessary. Define readiness based on **the listener's role in the instance's functionality**.

## 13. Broker connectivity does not prove consumer authorization

A health check that merely opens a socket or calls `describeCluster` does not necessarily test the consumer principal's permission to read topics and groups. Health checks can use `KafkaAdmin` with a different client configuration, or check only cluster metadata.

Example:

```text
Health check principal: User:platform-monitor
  DESCRIBE cluster -> ALLOW

Listener principal: User:orders-service
  READ orders -> ALLOW
  READ orders-worker group -> DENY

Generic broker health = UP
Actual consumer readiness = DOWN
```

Therefore, do not take a generic broker connectivity health indicator as proof that every listener is fully authorized. Readiness should consider the state of required containers/listeners and recent authorization errors on the right principal.

Do not publish synthetic records to production topics every few seconds just to probe permissions; doing so causes side effects and unnecessary load. A separate authorized probe topic/group can be used, but it only proves the probe principal has permissions on probe resources, not on `orders` or `orders-worker`. Best practice is verifying ACLs via the platform control plane and confirming the real listener has successfully joined/fetched.

## 14. Designing readiness state for critical listeners

For critical listeners, readiness state can be maintained at the application layer using lifecycle events, assignment/health state, and authorization errors. The example below illustrates the concept rather than relying on a specific lifecycle API across all Spring Kafka versions:

```java
public enum ConsumerReadiness {
    STARTING,
    READY,
    AUTHORIZATION_FAILED,
    STOPPED
}

@Component
public class ConsumerReadinessState {

    private final AtomicReference<ConsumerReadiness> state =
            new AtomicReference<>(ConsumerReadiness.STARTING);

    public void markReady() {
        state.set(ConsumerReadiness.READY);
    }

    public void markAuthorizationFailed() {
        state.set(ConsumerReadiness.AUTHORIZATION_FAILED);
    }

    public void markStopped() {
        state.set(ConsumerReadiness.STOPPED);
    }

    public ConsumerReadiness current() {
        return state.get();
    }
}
```

A `HealthIndicator` can reflect the state:

```java
@Component
public class OrdersConsumerHealthIndicator implements HealthIndicator {

    private final ConsumerReadinessState readiness;

    public OrdersConsumerHealthIndicator(ConsumerReadinessState readiness) {
        this.readiness = readiness;
    }

    @Override
    public Health health() {
        return switch (readiness.current()) {
            case READY -> Health.up().build();
            case AUTHORIZATION_FAILED -> Health.down()
                    .withDetail("reason", "Kafka authorization failed")
                    .build();
            case STARTING -> Health.outOfService()
                    .withDetail("reason", "Kafka listener is starting")
                    .build();
            case STOPPED -> Health.down()
                    .withDetail("reason", "Kafka listener is stopped")
                    .build();
        };
    }
}
```

`HealthIndicator`, `Health`, and `Status` belong to Spring Boot Actuator. This code is a simple state model; a production implementation must update state from accurate lifecycle/error observations, handle multiple child consumers, and avoid calling `markReady()` too early. A container returning `isRunning()` does not always prove it has been assigned partitions or can fetch records. Better readiness is marked after the listener satisfies the service's required operating conditions and reset whenever an authorization failure occurs.

Never let one healthy child consumer overwrite the state to `READY` while another child of a critical listener is still hitting authorization failures. With higher concurrency, aggregate readiness must reflect **all mandatory consumers** or defined quorum/partition-ownership rules.

## 15. Observing authorization failures

Useful signals for dashboards and alerts:

| Signal | What it is used for |
|---|---|
| Count by exception class | Distinguish `TopicAuthorizationException`, `GroupAuthorizationException`, transactional ID failures |
| Principal and client ID in audit logs | Identify the denied identity, when logging is permitted |
| Resource and operation | Know whether the ACL fix belongs on topic, group, cluster, or transactional ID |
| Listener/container state | Determine whether the listener is still running, stopped, or retrying authorization |
| Readiness state | Indicate whether the instance can accept required workloads |
| DLT send failure count | Detect producer principals lacking permission to publish to DLT |
| Transaction failures | Detect transactional ID ACL or producer authorization issues |
| Consumer lag / oldest record age | Assess business impact while listeners cannot consume |

Logs should include service, environment, `client.id`, group, topic, operation, exception class, and timestamp if known. Never log SASL passwords, tokens, raw JAAS strings, private keys, or full config objects.

Metric labels need low cardinality. Use exception class or a standardized error category; never use raw exception messages, offsets, event IDs, or credentials as labels. Principal can be a tag if the number of principals is finite and reviewed, though detailed logs/audits are usually safer.

## 16. Troubleshooting by exception

When encountering an authorization failure, trace by resource instead of trying broad permissions:

| Exception / Symptom | Check First | Action |
|---|---|---|
| `GroupAuthorizationException` | Actual principal, `group.id`, Group ACL | Grant `READ` on the exact group to the consumer principal |
| `TopicAuthorizationException` on consume | Topic subscription, metadata/fetch, Topic ACL | Verify `READ` and required describe permissions on the source topic |
| `TopicAuthorizationException` on publish | Producer principal, output/DLT/retry topic | Grant `WRITE` on the exact topic to the producer principal |
| `TransactionalIdAuthorizationException` | Actual `transactional.id` and prefix | Grant permissions on the `TransactionalId` resource using the proper pattern |
| `ClusterAuthorizationException` | Which cluster-level request was denied | Determine if cluster permissions are truly needed; avoid granting `ALL` |
| `SaslAuthenticationException` | Credentials, mechanism, principal mapping | Fix secret/identity; ACLs cannot fix authentication failures |
| SSL handshake failure | Certificates, truststore, hostname, TLS version | Fix transport trust/identity; do not change ACLs to fix TLS |

If the exception does not name the resource clearly, selectively enable Kafka client/broker logging during investigation and inspect audit logs. Do not leave full Kafka client `TRACE` logging enabled long-term in production because logs can grow huge and expose sensitive configuration details.

## 17. Checking current ACLs

For Kafka clusters using an ACL authorizer and corresponding admin tools, you can list a principal's permissions:

```bash
kafka-acls.sh --bootstrap-server kafka.example:9093 \
  --command-config admin-client.properties \
  --list --principal User:orders-service
```

`admin-client.properties` must reside in a protected location and contain appropriate connection/admin settings; never dump file contents into logs or Git. List output must be read alongside resource patterns, hosts, operations, and permission types (ALLOW/DENY). Wildcard/prefix ACLs can affect more resources than a single specific entry.

If the cluster uses an authorizer or policy engine other than traditional Kafka ACLs, use the platform's official control-plane tools. Some managed Kafka services manage permissions via roles/permission sets rather than permitting direct `kafka-acls.sh` usage.

When verifying, check **the running principal**, not the admin principal. An admin may see all ACLs while the application still lacks permission due to a different principal, mismatched resource pattern, or host restriction.

## 18. Common configuration mistakes

| Symptom | Likely Cause | Remediation |
|---|---|---|
| App connects to broker, but listener does not join group | Missing `READ` on Group | Verify actual `group.id` and Group ACL |
| Consumer joins group, but does not fetch topic | Missing Topic permission or wrong subscription name | Check topic ACL and subscription pattern |
| Main publish succeeds, but DLT send fails | Producer principal lacks `WRITE` on DLT | Grant separate permissions for the DLT topic |
| Normal output send works, but transactions fail | Missing ACL on transactional ID | Check actual prefix/ID and `TransactionalId` permissions |
| Works locally, fails in production | Different principal, cluster ACLs, or topic naming | Compare identity/resources per environment; do not copy broad ACLs |
| Health endpoint `UP`, yet consumer processes nothing | Health check only checks broker connectivity | Add readiness reflecting listener state/authorization |
| Pod restarts repeatedly | Liveness is tied to ACL failures | Keep liveness for process health; reflect capability via readiness |
| Authorization retries cause log storm | Retry interval too short or ACL still unfixed | Choose interval, alert, and coordinate with platform team |
| Only works after adding `ALL` permission | Missing specific permission not yet identified | Narrow ACLs down to minimum principal/resource/operation |

## 19. Testing authorization and readiness scenarios

Testing must verify both that **the failure is detected** and that **the application reacts properly**. You can use a Kafka test cluster supporting ACLs or a dedicated integration environment with the authorizer enabled.

Cases to include:

1. **Consumer with full permissions:** principal can read the topic and group; listener receives records.
2. **Missing Topic READ:** confirm root cause is topic authorization and readiness reflects that the listener cannot process.
3. **Missing Group READ:** consumer cannot join the group; distinguish from missing topic permission.
4. **Producer missing DLT WRITE:** failing record is processed, DLT publish fails, recovery is not treated as complete.
5. **Missing transactional ID WRITE:** producer transaction fails with the appropriate resource error.
6. **ACL granted while app is running:** if using `authExceptionRetryInterval`, verify the container retries on schedule and returns to ready once permissions take effect.
7. **Wrong authentication:** confirm `SaslAuthenticationException` is not confused with authorization and does not retry infinitely under an inappropriate policy.
8. **Readiness and liveness:** ACL failure drops readiness when a critical listener fails, without causing a liveness restart loop.
9. **Multiple child consumers:** one failing child does not have aggregate state wrongly overwritten by another child.
10. **Secret rotation:** new client uses new credentials without logging secrets; verify behavior when consumers restart.
11. **Least privilege:** granted permissions suffice for required operations without accidentally allowing `CREATE`/`ALTER`/`DELETE` on out-of-scope resources.
12. **Post-outage recovery:** after ACLs are fixed, lag drops, records are processed properly, and no duplicates/lost offsets occur.

Do not merely mock an `AuthorizationException` in a unit test and conclude production ACLs are correct. At least one integration test with a real principal and authorizer is needed to verify actual resources and operations.

## 20. Runbook when a consumer hits an authorization failure

1. **Identify the workload:** service, instance, listener ID, consumer group, topic, and client ID.
2. **Extract the root exception:** distinguish authorization, authentication, TLS, and timeouts.
3. **Identify the principal:** confirm which principal the broker sees from the exact consumer or producer client.
4. **Identify resource/operation:** Topic `READ`/`WRITE`, Group `READ`, `TransactionalId` `WRITE`, or cluster-level operation.
5. **Inspect current ACLs/policies:** resource pattern, host, ALLOW/DENY, and environment.
6. **Check readiness:** is the critical listener actually operating? Keep process liveness independent of Kafka permissions.
7. **Grant least privilege via platform control plane:** never grant `ALL` as a quick fix without approval/analysis.
8. **Let the container retry or restart cleanly:** use `authExceptionRetryInterval` if appropriate for your version and exception type; avoid restart storms.
9. **Verify recovery:** listener joined/fetched, DLT/producer sends succeed if applicable, committed offsets advance, and lag decreases.
10. **Record root cause:** missing ACL/resource, wrong principal/config, detection time, data impact, and preventive measures.

If a record was already processed into the DB while the offset remained uncommitted as the consumer stopped on an authorization failure, redelivery can occur after permissions are restored. Ensure side effects are idempotent or backed by an inbox to prevent duplicate processing. If DLT publishing failed, inspect source offsets and recovery state before replaying or resetting offsets.

## 21. Production principles

1. Distinguish **authentication** from **authorization** before rotating secrets or changing ACLs.
2. Identify the actual principal of every consumer, producer, DLT publisher, and transactional producer.
3. Grant least-privilege permissions by resource/operation: Topic, Group, `TransactionalId`, or Cluster only when genuinely needed.
4. Check both the source topic and the consumer group; a consumer can lack permissions on either side.
5. DLT/retry/output topics require `WRITE` permission for the exact producer principal.
6. Kafka transactions require ACLs on the transactional ID; a unique prefix does not replace authorizer permissions.
7. Use `authExceptionRetryInterval` when supported by your version/exception type and when permissions can be fixed at runtime; do not treat it as a way to grant permissions.
8. Keep liveness tied to process health; use readiness to signal when a critical listener cannot handle workload.
9. Never treat broker connectivity or generic admin health as proof of successful consumer authorization.
10. Never log credentials; metric tags must be low-cardinality and free of raw exception messages/secrets.
11. Test missing Topic/Group/DLT/TransactionalId ACLs, readiness, retries, and recovery before deployment.
12. After granting permissions, verify listener assignment, record processing, DLT sends, committed offsets, and consumer lag.

**Conclusion:** An authorization failure is a permission error on a specific resource, not a generic "Kafka down" state. In Spring Kafka, identifying the exact principal, operation, and resource lets you apply least-privilege ACL fixes; `authExceptionRetryInterval` can aid recovery in framework-supported cases. Readiness must reflect the listener's actual ability to process, while liveness stays focused on process health. When logs, metrics, ACLs, and recovery are properly aligned, operations can resolve permission errors without triggering restart storms, skipping records, or hiding DLT publish failures.
