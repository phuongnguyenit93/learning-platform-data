# AuthorizationException

Kafka uses authentication to verify who the client is and authorization to decide what that principal is allowed to do on a topic, consumer group, cluster, or transactional ID. A consumer may pass SASL/TLS authentication yet still be unable to read a topic; a producer may connect to a broker yet be denied WRITE permission. When a broker rejects an operation due to insufficient permissions, the Kafka client may throw **AuthorizationException** or a specific subclass.

In Spring Kafka, it is important to recognize this error type because it typically occurs at the **Kafka client/container layer**, before the listener method is invoked. Therefore, treating it as a business record exception and relying only on DefaultErrorHandler usually will not resolve the root cause. Spring Kafka provides a dedicated mechanism on the listener container via the **authExceptionRetryInterval** property to retry after authentication/authorization failures in supported versions.

This lesson belongs to the **Operational Security** chapter of **Spring Kafka Reliability Operations**. It focuses on principals, ACLs, distinguishing AuthenticationException from AuthorizationException, consumer container behavior, producer failures, retry boundaries, protecting secrets, and production recovery procedures.

## 1. Authentication and Authorization Are Different

Two security questions must be separated:

- **Authentication:** who is the client? The broker verifies identity via SASL, TLS client certificates, or configured security mechanisms.
- **Authorization:** is the authenticated principal allowed to perform the operation on the specific resource? Kafka checks the corresponding ACL/policy.

~~~text
orders-projection connects to Kafka
        |
        v
SASL authentication succeeds
        |
        v
Broker identifies principal: User:orders-projection
        |
        v
Consumer requests READ on topic orders.created
        |
        v
Broker checks ACL
       / \
  allowed denied
     |      |
  consume  AuthorizationException
~~~

If the SASL password is wrong, the client may receive an authentication failure. If the password is correct but the principal lacks READ permission on the topic, that is an authorization failure.

| Scenario | Common Problem Type |
|---|---|
| Wrong SASL username/password | AuthenticationException |
| Unsupported SASL mechanism | Authentication/configuration failure |
| TLS truststore does not trust broker certificate | TLS/SSL handshake failure |
| Client certificate rejected | Authentication failure |
| Valid principal but missing READ on topic | AuthorizationException |
| Consumer has topic READ but lacks group READ permission | Group authorization failure |
| Producer lacks WRITE on topic | Topic authorization failure |
| Transactional producer lacks permission on transactional ID | Transactional ID authorization failure |

TLS, SASL, and authorization errors can appear at different times during connection setup, metadata lookup, poll, send, or commit. Read the exception subtype and broker logs to identify the exact failing layer.

## 2. What Is AuthorizationException?

In the Kafka Java client, AuthorizationException represents an operation rejected by the broker due to missing permissions. Specific subclasses can indicate the resource or operation involved, depending on the Kafka client version.

Common exceptions:

- **TopicAuthorizationException:** principal is not authorized to perform operations on one or more topics.
- **GroupAuthorizationException:** principal lacks necessary permissions on the consumer group.
- **ClusterAuthorizationException:** operation requiring cluster-level permissions was denied.
- **TransactionalIdAuthorizationException:** producer lacks permission on the transactional ID.
- **DelegationTokenAuthorizationException:** delegation token operation was denied in environments using delegation tokens.

These classes belong to the Kafka client package, e.g., org.apache.kafka.common.errors. Preserve the cause chain to determine the subtype; class names and metadata may vary across Kafka versions.

### 2.1 One permission error does not necessarily break the whole cluster

If a consumer is denied READ on one topic, other clients with different principals can still operate. If a service is denied on a consumer group, that service's producer can still write to topics if it has the corresponding WRITE ACL.

Incident scope depends on resource and principal. Do not conclude the entire cluster is disconnected from a single authorization error.

### 2.2 Do not confuse with record errors

AuthorizationException usually arises when the Kafka client calls broker APIs such as metadata, fetch, group coordination, offset commit, or produce. It is not necessarily tied to the payload of a specific record.

A poison message typically causes the listener method to throw an exception while processing a record. AuthorizationException typically indicates the client is not authorized to perform the operation at the Kafka layer. The two errors have different recovery paths.

## 3. Which Permissions Does a Consumer Need?

A typical consumer group needs permissions on both topic and group:

- **READ on the topic** to consume records.
- **READ on the group** to join/manage the consumer group and perform required group operations.
- Corresponding metadata/describe permissions per the broker ACL model and application operations. In Kafka's ACL model, some operations may imply DESCRIBE; verify your broker version's behavior.

Example:

~~~text
Principal: User:orders-projection

Topic resource:
  orders.created
  required operation: READ

Group resource:
  orders-projection-prod
  required operation: READ
~~~

Topic READ and group READ are two separate resources. Granting only topic READ without group READ lets the client fetch metadata, but it cannot join the group as expected. Granting only group READ without topic READ prevents the consumer from fetching records.

### 3.1 ACL granting example

The following commands illustrate using kafka-acls.sh; replace bootstrap server, principal, topic, and group with your environment values. Follow your organization's permission governance process.

~~~bash
kafka-acls.sh --bootstrap-server kafka.example.internal:9092 --add --allow-principal 'User:orders-projection' --operation Read --topic orders.created

kafka-acls.sh --bootstrap-server kafka.example.internal:9092 --add --allow-principal 'User:orders-projection' --operation Read --group orders-projection-prod
~~~

These are the minimum permissions typically needed for a consumer group. If the application uses AdminClient, topic creation, transactions, or other operations, corresponding ACLs are required. Do not grant Cluster ALL just to make an AuthorizationException disappear.

### 3.2 Prefix ACLs and wildcards

Kafka supports resource patterns such as literal, prefixed, and wildcard depending on version. Prefix ACLs are convenient for groups of topics, but they expand permission scope.

Allowing a principal to read all topics with prefix orders- can inadvertently grant access to future topics. Use literal ACLs whenever possible; use prefixes only when naming conventions and ownership are clear.

## 4. Which Permissions Does a Producer Need?

A typical producer needs **WRITE on the destination topic**. Some metadata operations require DESCRIBE or permissions implied by WRITE under Kafka's ACL model.

~~~text
Principal: User:orders-publisher
Topic: orders.created
Operation: WRITE
~~~

Example:

~~~bash
kafka-acls.sh --bootstrap-server kafka.example.internal:9092 --add --allow-principal 'User:orders-publisher' --operation Write --topic orders.created
~~~

If the producer uses idempotence or transactions, additional permissions related to transactional IDs and cluster behavior may be required depending on Kafka version/security policy. For transactional producers, permissions on the transactional ID must be granted for the exact resource and operation; do not grant only WRITE on output topics and assume transactions will work.

### 4.1 Producer authorization is not handled by the listener container

If KafkaTemplate.send() is rejected by the broker, the exception usually appears in the send result/future or during flush/transaction commit. The listener container's authExceptionRetryInterval property does not automatically retry producer sends.

The producer application must handle send failures according to its business contract, retry budget, idempotency, and transaction policy. Do not assume enabling authExceptionRetryInterval on the consumer factory resolves KafkaTemplate WRITE ACL errors.

## 5. How Does Spring Kafka Handle Auth Exceptions?

KafkaConsumer can throw AuthenticationException or AuthorizationException while executing broker operations. These exceptions usually occur inside the consumer loop, such as during poll or group/metadata operations, rather than being thrown from the listener method.

In Spring Kafka:

- By default behavior, when an authentication/authorization exception occurs, the listener container stops.
- In supported versions, **authExceptionRetryInterval** can be configured so the container waits a period and retries.
- This mechanism is meant for authentication/authorization errors in the Kafka consumer/container path.
- It does not replace DefaultErrorHandler for record processing exceptions.
- It does not fix wrong ACLs or credentials by itself.

If permissions were just granted or secrets just fixed, the retry interval can let the container keep retrying without requiring a manual operator restart, provided the version and container setup support it.

## 6. Configuring authExceptionRetryInterval

The property is configured on ContainerProperties:

~~~java
factory.getContainerProperties()
       .setAuthExceptionRetryInterval(Duration.ofSeconds(30));
~~~

Factory example:

~~~java
@Configuration
public class OrdersConsumerConfiguration {

    @Bean
    ConcurrentKafkaListenerContainerFactory<String, OrderCreated>
    ordersListenerFactory(
            ConsumerFactory<String, OrderCreated> consumerFactory) {

        var factory =
            new ConcurrentKafkaListenerContainerFactory<
                String, OrderCreated>();

        factory.setConsumerFactory(consumerFactory);
        factory.setConcurrency(3);

        factory.getContainerProperties()
               .setAuthExceptionRetryInterval(Duration.ofSeconds(30));

        return factory;
    }
}
~~~

Listener:

~~~java
@KafkaListener(
    id = "orders-main",
    topics = "orders.created",
    groupId = "orders-projection-prod",
    containerFactory = "ordersListenerFactory"
)
public void handle(OrderCreated event) {
    orderService.apply(event);
}
~~~

The beans and models in the example are illustrative. ConsumerFactory still needs appropriate SASL/TLS, deserializer, bootstrap servers, group properties, and ACL configuration.

### 6.1 Version requirement

authExceptionRetryInterval was added in Spring Kafka **2.8**. In older versions, the setter may not exist and the default behavior may be stopping the container on auth exceptions.

Before copying code:

1. Confirm your actual Spring Kafka dependency.
2. Check the ContainerProperties API for that exact version.
3. Verify the Duration type and setter signature.
4. Test auth failure in staging.
5. Do not assume a YAML property of the same name is bound in every Spring Boot release.

### 6.2 Consumer requires group.id

The listener container's auth exception retry mechanism requires the consumer to be configured with a **group.id** per Spring Kafka's contract. Ensure the actual group ID is set properly, whether from ConsumerFactory or @KafkaListener.

Without a proper group ID, do not assume the container can continue on the retry interval. Verify API/version documentation and effective consumer configuration.

### 6.3 Retry interval is a wait duration, not a retry count

A Duration of 30 seconds means the container waits between retry attempts under this mechanism. It does not mean retrying 30 times, nor does it automatically add exponential backoff or jitter.

If the broker keeps denying permissions, the container may keep hitting auth exceptions periodically. Alerts are needed so operators know the incident persists.

## 7. Auth Exceptions Differ from Listener Record Exceptions

~~~text
KafkaConsumer.poll()
    |
    +-- AuthorizationException
    |       -> consumer/container error path
    |       -> stop by default, or retry interval if configured
    |
    +-- ConsumerRecord received
            |
            v
        @KafkaListener
            |
            +-- Database exception
            |       -> CommonErrorHandler / DefaultErrorHandler
            |
            +-- Business validation exception
                    -> retry/recovery policy
~~~

**DefaultErrorHandler is not the place to fix ACLs.** If the Kafka broker denies topic READ or group READ during poll/join operations, the listener method may not have been invoked at all, so the record error handler's RetryListener will not receive a corresponding delivery callback either.

Similarly, @RetryableTopic is not a solution for a consumer lacking permission to read the main topic or retry topics. Retry-topic listeners also need their own ACLs.

### 7.1 Avoiding retry storms on permanent permission errors

If ACLs are missing for hours, a short retry interval can produce repetitive requests and logs. Choose an operationally sensible interval, track retry counts, and alert. If fast shutdown is required when credentials/policies are revoked, consider default stop behavior or an appropriate operational policy.

### 7.2 When to use DefaultErrorHandler?

Use DefaultErrorHandler for exceptions thrown during record processing in the listener path, such as database timeouts, business service exceptions, or validation/recovery failures. Do not use it to handle missing ACLs on consumer poll or group coordination.

## 8. Distinguishing TopicAuthorizationException and GroupAuthorizationException

| Exception | Typical Resource | Check |
|---|---|---|
| TopicAuthorizationException | Topic | Does the principal have appropriate READ/WRITE/Describe? |
| GroupAuthorizationException | Consumer group | Does the principal have READ on the group? |
| ClusterAuthorizationException | Cluster-level operation | Are ACLs present for cluster/Admin operations? |
| TransactionalIdAuthorizationException | Transactional ID | Does the principal have corresponding transaction permissions? |

The exception name is only a starting point. Broker logs or exception metadata can reveal the exact denied resource.

### 8.1 TopicAuthorizationException on the consumer

If a consumer subscribes to multiple topics and only one is denied, the exception may point to one or more disallowed topics. Do not immediately grant wildcard permissions for all topics.

Check the resolved topic string after pattern expansion, the principal after mapping, the ACL resource pattern type, the READ operation, the connected cluster, and any retry/DLT topics the consumer also needs to read.

### 8.2 GroupAuthorizationException

If the consumer can read topic metadata but cannot join the group, check the actual group.id, ACL resource type GROUP, the principal recognized by the broker, and whether the group name is overridden by @KafkaListener.id/idIsGroup.

Changing the group ID to bypass an ACL error can create a new consumer group with a different offset namespace, causing replay or starting from different offsets. Do not do this as an arbitrary workaround.

## 9. Principal Mapping: Which Identity Does the Broker See?

The username configured on the client is not necessarily the final principal string the broker uses for ACL evaluation.

~~~text
Client SASL username:
  orders-projection

Broker principal:
  User:orders-projection
~~~

With TLS certificates, the broker can derive a principal from the subject DN and apply principal builder/mapping rules. If the ACL is granted to User:orders-projection while the broker identifies the client as User:CN=orders-worker,OU=Services, the ACL may not match.

To investigate:

1. Identify the broker listener endpoint and security protocol.
2. Check broker authentication/audit logs.
3. Inspect the principal after mapping.
4. Check the denied resource and operation.
5. Compare against actual ACLs.
6. Confirm the right cluster/environment.

Do not just look at the username in application.yml and assume the broker uses the same principal.

### 9.1 Do not log credentials

Do not log sasl.jaas.config, SASL passwords, OAuth access/refresh tokens, private keys, keystore contents, truststore passwords, or authorization headers.

If you need to log security config, log only the mechanism, protocol, and sanitized secret reference/alias. Do not stringify all Kafka properties.

## 10. What Errors Can SASL/TLS Cause?

Example client configuration using SASL_SSL:

~~~yaml
spring:
  kafka:
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-projection" password="INJECTED_SECRET";
~~~

This is a structural example, not a complete production secret configuration. Passwords should come from a secret manager or secure environment injection; do not commit credentials to source control.

Error categories:

- Security protocol mismatch with broker listener.
- Unsupported SASL mechanism.
- Wrong or expired username/password.
- Invalid JAAS syntax.
- TLS truststore does not trust broker certificate.
- Invalid client certificate.
- Principal mapping differs from ACL.
- Authentication succeeds, but ACLs are insufficient.

Not all of these errors are AuthorizationException. Read the root cause and broker logs before choosing remediation.

## 11. Producer AuthorizationException via KafkaTemplate

~~~java
kafkaTemplate.send("orders.created", orderId, event)
    .whenComplete((result, exception) -> {
        if (exception != null) {
            // Classify and handle send failure.
        }
    });
~~~

If the broker rejects WRITE, the future can complete exceptionally with a cause of TopicAuthorizationException or a corresponding wrapper exception.

authExceptionRetryInterval is a listener container/consumer path mechanism. KafkaTemplate send failures must be handled in the producer application or transaction boundary.

Do not retry producer sends infinitely on ACL errors. If the principal lacks WRITE, every retry will continue to be rejected and generate duplicate attempts/logs.

When a send failure outcome is uncertain, examine producer delivery semantics, idempotence, transactions, and business idempotency. AuthorizationException is usually a clear denial; however, wrappers/async completions can obscure the root cause. Unwrap the cause chain before deciding to retry.

## 12. Transactional Producers and Transactional ID Permissions

A transactional Kafka producer uses transactional.id. The broker checks permissions on the transactional ID namespace and required topic operations.

If permissions are missing, transaction begin/commit or producer initialization can fail with TransactionalIdAuthorizationException or a related error class.

Verify:

- Transactional ID prefix configured on ProducerFactory.
- Actual principal of the producer.
- ACL resource type TRANSACTIONAL_ID.
- Required operations per Kafka version.
- WRITE permissions on output topics.
- Corresponding consumer/group permissions if a listener container consumes inside the transaction.
- Whether ProducerFencedException is a separate error being confused with authorization.

### 12.1 Authorization and fencing are different

- AuthorizationException: principal lacks permission.
- ProducerFencedException: producer instance was fenced due to a transaction ownership conflict or another producer using the same transactional identity.

Granting more ACLs does not resolve fencing. Increasing retries does not resolve multiple producer instances improperly sharing a transactional ID. Identify the specific exception.

Do not catch a transaction failure and return normally to reduce logs; the transaction may roll back and offsets will not commit. Let the exception propagate through Spring Kafka transaction handling and investigate producer/consumer security policy.

## 13. Retry Interval and Container Operations

Suppose a consumer hits TopicAuthorizationException at 10:00 and authExceptionRetryInterval is 30 seconds:

~~~text
10:00:00  poll/metadata operation denied
10:00:00  container receives auth exception
10:00:00  container waits for retry interval
10:00:30  container retries
10:01:00  retries again if ACL still missing
...
10:02:10  operator grants proper ACL
10:02:30  next retry may succeed
10:02:30  consumer continues lifecycle if other conditions are valid
~~~

The timeline is illustrative only; network, broker, metadata refresh, and container scheduling can affect exact timing.

### 13.1 Retry interval too short

If the interval is 100 ms while the ACL remains broken for hours, the consumer can repeat requests and flood logs. That does not create permissions.

### 13.2 Retry interval too long

If the ACL was just fixed, a 10-minute interval makes consumer recovery slow even though the broker already allows it. Choose the interval based on desired recovery time, broker capacity, and operational alerting.

### 13.3 Interval is not exponential backoff

authExceptionRetryInterval is an API-configured retry interval. It does not default to jitter or exponential growth. If a different policy is needed, check framework version capabilities and lifecycle management; do not insert manual thread sleeps in consumer callbacks.

## 14. Choosing Stop vs. Retry by Policy

| Scenario | Typical Approach Considered |
|---|---|
| ACL missing due to rollout, will be fixed quickly | Monitored retry interval |
| Secret rotation has brief skew between pods | Retry interval and alert |
| Principal intentionally revoked | Stop/fail fast to prevent continued access |
| Permanent ACL error from deployment config | Stop and alert; fix config/policy |
| Broker security service temporarily out of sync | Monitored retry interval |
| Producer WRITE denied | Handle send failure separately; consumer interval does not apply |

If using a retry interval indefinitely, alert when the container repeatedly hits auth exceptions or makes no record progress. If failing fast is desired, default stop behavior may fit better, provided orchestrator/restart policies and incident response are clear.

## 15. Observability for AuthorizationException

Useful logs should distinguish authentication failure from authorization failure, and record resource type/name, Kafka client role, authenticated principal if available, cluster/environment, listener ID or producer component, retry/stop action, start time, and failure duration.

Suggested metrics:

| Metric | Meaning |
|---|---|
| kafka_authentication_failures_total | Authentication failures |
| kafka_authorization_failures_total | Authorization denials |
| kafka_authorization_retry_total | Container auth retry attempts |
| kafka_container_stopped_total | Container stops due to auth exceptions |
| kafka_consumer_last_successful_poll_timestamp | Timestamp of last successful poll if custom-instrumented |
| kafka_consumer_records_processed_total | Records processed |
| kafka_consumer_lag | Group backlog |
| kafka_producer_send_failures_total | Producer send failures |
| kafka_transaction_failures_total | Transaction outcome failures |

These are suggested metric names for custom instrumentation, not all available out of the box in Spring Kafka. Tags should have low cardinality: service, listener, client role, exception category, environment. Do not use raw principals if principal cardinality is large or sensitive; consider mapping to an approved service identity.

### 15.1 Impact-based alerting

An authorization error might appear once during an ACL rollout and self-heal. Prolonged errors must alert by duration/rate and impact:

~~~text
authorization failure rate > 0
AND consumer has no successful poll/progress
FOR 2 minutes
~~~

Exact conditions depend on available metrics and SLAs. Also alert when producer send failures increase or consumer lag exceeds budget.

Do not treat a RUNNING container as healthy. If an auth retry interval is configured, the container may remain alive without successfully processing records. Health checks must combine successful poll/record progress, assignment, and lag appropriately.

## 16. Reducing Log Noise When Auth Exceptions Repeat

If the retry interval is enabled and the broker keeps denying permissions, exceptions can recur periodically. A pragmatic policy:

- Log ERROR once when the auth failure starts.
- Log WARN summaries at intervals while it persists.
- Increment metrics for each retry attempt.
- Log INFO/WARN when the consumer recovers.
- Log ERROR when the container stops or a producer send/recovery failure impacts data.

Structured summary example:

~~~text
event=kafka_authorization_retry
clientRole=consumer
listenerId=orders-main
exception=TopicAuthorizationException
resource=orders.created
retryIntervalSeconds=30
failureDurationSeconds=180
attempts=6
~~~

This is an application-defined schema. Resource and principal must be sanitized. If the broker exception does not supply a safe resource string to log, record the exception category and reference the broker audit event.

Sampling must not hide an outage. If only the first auth failure is logged, maintain counters and alerts while the error persists. Upon recovery, log a recovery event so operators know the consumer is active again.

## 17. ACLs for Retry Topics and DLT

A listener using @RetryableTopic can subscribe to the main topic, retry topics, and DLT. The consumer principal needs READ on the topics the retry listener actually reads and READ on the corresponding consumer groups. The recoverer/producer principal needs WRITE on destination retry/DLT topics.

If ACLs are granted only for the main topic, the main consumer may run while retry listeners hit TopicAuthorizationException. If the producer can write the main topic but not the DLT, recovery can fail right when a poison record exhausts retries.

Example permission matrix:

| Component | Resource | Operation |
|---|---|---|
| Main consumer | orders.created | READ |
| Main consumer | orders-main group | READ |
| Retry consumer | orders.created-retry-* | READ |
| Retry consumer | retry group(s) | READ |
| DLT consumer | orders.created.DLT | READ |
| Recoverer producer | orders.created.DLT | WRITE |
| Retry publisher | retry topics | WRITE |

Exact group names depend on retry-topic configuration. Do not copy wildcard resource patterns without checking topic/group names generated at runtime.

A DLT recovery failure is not a consumer authorization retry. If the recoverer sends to the DLT without WRITE permission, that is a producer authorization failure. The consumer's authExceptionRetryInterval does not fix that WRITE permission.

## 18. AdminClient and Authorization Errors

An application may use KafkaAdmin/AdminClient to describe topics, create/delete topics, describe consumer groups, alter configs, or inspect cluster metadata. These operations have their own ACLs.

A consumer may read topics normally while a health check using AdminClient hits ClusterAuthorizationException because the principal lacks DescribeCluster or DescribeConfigs permission.

Do not grant broad Admin permissions to a consumer just to make a health check green.

### 18.1 Separating principals by role

A secure architecture typically separates:

- Consumer principal: only READ on required topics and READ on group.
- Producer principal: only WRITE on required topics.
- Admin principal: controlled administrative permissions, used by deployment/operations tooling.
- DLT/recovery principal: only required destinations and operations.

If a service shares one principal across consume, publish, admin, and DLT, the blast radius upon credential compromise is much larger.

## 19. Least Privilege and Prefix Permissions

ACLs should be granted for the minimal resource and operation. Avoid granting Cluster ALL, Topic wildcard, and Group wildcard just to get a listener running.

A cleaner policy:

- READ on specific topics needed for consumption.
- READ on the specific consumer group.
- WRITE only on output/retry/DLT topics the service actually publishes to.
- Transactional ID permissions only for the service's namespace if using transactions.
- Admin permissions separated from runtime principals.

An orders- prefix can be convenient for auto-generated retry topics, but ownership and naming rules must be enforced. If a service has overly broad prefix permissions, future topics could automatically fall under its permissions without review.

### 19.1 ACL rollout and secret rotation

1. Create/verify the new principal.
2. Grant least-privilege ACLs.
3. Test authentication and authorization from the target environment.
4. Roll out credentials with an overlap strategy if supported by the platform.
5. Monitor auth errors and consumer progress.
6. Revoke old credentials after confirming all instances have migrated.
7. Keep an audit trail for ACL changes.

Do not revoke old credentials before all replicas use the new credentials if the system lacks a coordinated rotation mechanism.

## 20. Diagnosing AuthorizationException in Order

When a consumer stops with AuthorizationException:

1. Capture the exception subtype and full cause chain.
2. Identify the failing operation: metadata, fetch, group join, commit, transaction, or produce.
3. Identify the resource: topic, group, cluster, or transactional ID.
4. Identify the principal actually recognized by the broker.
5. Confirm the cluster/environment the client is connecting to.
6. Read broker authorization/audit logs.
7. List existing ACLs for the principal and resource.
8. Compare required operations with granted operations.
9. Check literal/prefix/wildcard resource patterns.
10. Check whether listener group ID is overridden by annotation or idIsGroup.
11. Check retry/DLT topics and groups if applicable.
12. Fix ACLs or principal mapping following least privilege.
13. Verify container retry/restart behavior per policy.
14. Check consumer assignment, successful polls, lag, and record progress.
15. Document the permission change and recovery outcome.

Do not start by granting Cluster ALL or resetting offsets. Those are broad actions that can introduce new issues.

## 21. When the Container Stops Due to AuthorizationException

If default stop behavior is in effect:

- The container may not restart automatically just because ACLs are granted later.
- Determine the lifecycle policy: operator restart, application restart, or container registry start.
- Confirm the permission issue is fixed before restarting.
- Monitor group rebalances and partition reassignments.
- Check committed offsets and lag after the consumer returns.

If authExceptionRetryInterval is configured and supported by the version:

- The container can retry after the interval.
- No restart is needed solely because ACLs were granted late if the retry succeeds.
- If ACLs remain wrong, errors will recur periodically.
- Alerts and summaries are needed to avoid noise.
- Verify successful poll/record progress after recovery.

Do not restart repeatedly while ACLs remain unfixed. A restart loop creates log noise, consumer group churn, and broker authentication load. If the error is a consistent authorization denial, restarting does not add permissions.

## 22. Diagnosing Producer Authorization Failures

When KafkaTemplate.send() fails:

1. Inspect the future/transaction exception and unwrap the cause.
2. Confirm the destination topic is on the right cluster.
3. Identify the producer's actual principal.
4. Check WRITE/Describe ACLs on the topic.
5. If using transactions, check transactional ID permissions.
6. Check idempotence/transaction setup and producer fencing separately.
7. Determine whether the send outcome is definitely failed or unknown.
8. Apply an appropriate retry budget and idempotency.
9. Log final failures with topic and operation, without payload.
10. Alert if the producer cannot publish critical events.

Do not rely on the listener container auth retry interval to retry KafkaTemplate sends.

## 23. Easily Confused Errors

| Exception/Symptom | Possibility | Investigation Direction |
|---|---|---|
| SaslAuthenticationException | Credential/mechanism/principal auth | SASL config and broker auth logs |
| SSLHandshakeException | TLS trust/certificate/protocol | Truststore, certificate chain, listener |
| TopicAuthorizationException | Missing topic permission | Topic ACL and principal |
| GroupAuthorizationException | Missing group permission | Group ACL and actual group.id |
| ClusterAuthorizationException | Missing cluster operation | Admin/cluster ACL |
| TransactionalIdAuthorizationException | Missing transactional ID permission | Transactional ID ACL |
| ProducerFencedException | Producer fenced | Transactional ID uniqueness/lifecycle |
| TimeoutException | Network, broker, queue, or operation timeout | Client metrics and broker health |
| UnknownTopicOrPartitionException | Topic/partition missing or stale metadata | Topic provisioning/metadata |
| RecordDeserializationException | Data cannot be decoded | Deserializer/schema; not ACL |

Exception wrapping can cause logs to display ExecutionException or ListenerExecutionFailedException on the outside. Always inspect the root cause.

## 24. Integration Tests for Auth Behavior

Unit tests invoking listener methods directly do not verify auth behavior, because AuthorizationException typically occurs before the listener is called. Use a test broker environment with real ACLs/security or an equivalent integration environment.

### 24.1 Consumer missing topic READ

1. Create a test principal with valid authentication.
2. Grant only group READ; intentionally omit topic READ.
3. Start the listener container.
4. Verify the exception subtype/behavior per Kafka/Spring Kafka version.
5. Verify the listener is not called for unread records.
6. Grant topic READ.
7. If authExceptionRetryInterval is enabled, wait for the container to retry.
8. Verify the consumer joins/consumes and records progress.

### 24.2 Consumer missing group READ

1. Grant topic READ.
2. Omit group READ.
3. Start the consumer with a specific group.id.
4. Verify group authorization failure.
5. Grant appropriate group permission.
6. Verify retry/restart behavior works properly.
7. Check offsets/assignment after recovery.

### 24.3 Producer missing topic WRITE

1. Create a producer principal with valid auth.
2. Omit WRITE on the destination topic.
3. Call KafkaTemplate.send().
4. Verify future/transaction failure has the expected cause.
5. Grant WRITE.
6. Resend per test policy.
7. Verify the record appears with expected semantics/idempotency.

This test does not use the consumer container's authExceptionRetryInterval.

### 24.4 Testing transactional ID ACL

- Configure a transactional producer with a specific transactional.id/prefix.
- Grant topic permissions but intentionally omit transactional ID permission.
- Verify the transaction operation is rejected.
- Grant proper permission.
- Verify transaction commit/abort and downstream read_committed behavior.

### 24.5 Testing retry interval

- Run a Spring Kafka version supporting authExceptionRetryInterval.
- Set an interval long enough to observe.
- Intentionally trigger an auth failure.
- Verify the container does not treat it as a listener record exception.
- Grant the ACL while the container waits.
- Verify a subsequent retry succeeds.
- Measure successful poll/record progress.
- Do not assert timing down to the millisecond; use reasonable timeouts.

### 24.6 Testing no secret leakage

- Use dummy credentials in tests.
- Capture application/client logs.
- Verify passwords, tokens, and JAAS secrets do not appear.
- Verify principal/resource/error category are sufficient for diagnosis.
- Verify log masking after exceptions are wrapped.

## 25. Operational Security Runbook

**Containment**

1. Identify service, pod, listener/client role, and Kafka cluster.
2. Determine whether it is consumer or producer/admin client.
3. Capture the exception subtype and denied resource.
4. Check start time and scope of affected replicas.
5. Check broker audit/security logs to confirm the principal.

**Remediation**

6. Verify actual group ID/topic/transactional ID.
7. Check ACLs by resource and operation.
8. Check principal mapping, SASL/TLS, and secret rotation.
9. Grant least-privilege permissions or fix identity mapping.
10. If the container stopped, restart per lifecycle policy; if retry interval is active, wait for the next controlled attempt.
11. For producer failures, handle send/transaction outcomes separately.

**Verification**

12. Confirm authentication/authorization failures stop increasing.
13. Confirm consumer assignment and successful polls.
14. Confirm committed offsets/lag progress.
15. Confirm producer sends and transaction commits succeed.
16. Verify retry/DLT consumers also have required permissions.
17. Record the ACL change, principal, resource, and approver.
18. Narrow or revoke temporary permissions after the incident if policy requires.

## 26. Common Misconceptions

**"Authentication succeeding means the consumer can read topics."** False. The broker still checks ACLs on topics and groups.

**"AuthorizationException is a listener record error."** Usually not. It can occur during Kafka client/container operations before listener invocation.

**"DefaultErrorHandler will retry AuthorizationException."** Do not assume so. The container has separate handling for authentication/authorization failures.

**"authExceptionRetryInterval applies to all producer sends."** False. It is a listener container/consumer path mechanism; KafkaTemplate send failures must be handled separately.

**"Enabling the retry interval fixes ACLs automatically."** False. It only retries after a wait; permissions must still be fixed.

**"Group ID and listener ID are always identical."** No. @KafkaListener.id can be used as the group when idIsGroup=true and no explicit groupId is given, but they are two distinct concepts.

**"Granting Cluster ALL is a safe quick fix."** False. It expands the blast radius and violates least privilege.

**"A producer with topic WRITE can definitely run transactions."** No. Transactional ID and related permissions must also be aligned.

**"Use the consumer auth retry interval to fix DLT producer ACLs."** False. The DLT publisher is a producer path.

**"Restarting the consumer fixes ACLs."** False. Restarting does not grant new permissions.

**"Seeing no exceptions means data is being processed."** No. Check successful polls, assignment, offset progress, and business completion.

**"You can log JAAS config to check the username/password."** No. Never log secrets; verify the principal via broker logs and sanitized secret references.

## 27. Implementation Checklist

**Identity and ACLs**

- [ ] Know the actual principal recognized by the broker.
- [ ] Distinguish authentication from authorization.
- [ ] Consumer has required topic READ and group READ.
- [ ] Producer has WRITE on destination topics.
- [ ] Retry/DLT consumers and publishers have corresponding ACLs.
- [ ] Transactional producer has permissions on the appropriate transactional ID.
- [ ] Prefix/wildcard ACLs are governed and restricted.
- [ ] Runtime principals follow least privilege.

**Spring Kafka behavior**

- [ ] Confirm Spring Kafka version.
- [ ] Understand default container stop behavior on auth exceptions.
- [ ] authExceptionRetryInterval is configured when policy requires retry.
- [ ] Actual consumer group ID is verified.
- [ ] Do not confuse auth exceptions with listener record exceptions.
- [ ] Producer send failures are handled separately.
- [ ] Recovery/DLT producer errors have dedicated monitoring.

**Observability and security**

- [ ] Log exception subtype, resource, and operation when available.
- [ ] Never log passwords, tokens, JAAS, or private keys.
- [ ] Metrics exist for auth failures/retries and consumer progress.
- [ ] Alert when auth failures persist.
- [ ] Retry logs are rate-limited/summarized if needed.
- [ ] Audit trail records ACL changes.
- [ ] Do not grant broad permissions just to silence alerts.

**Verification**

- [ ] Test consumer missing topic READ.
- [ ] Test consumer missing group READ.
- [ ] Test producer missing topic WRITE.
- [ ] Test transactional ID ACL if using transactions.
- [ ] Test authExceptionRetryInterval against real broker security.
- [ ] Test ACL recovery without resetting offsets.
- [ ] Test that logs do not expose secrets.
- [ ] Test retry/DLT topics and consumer groups.

## 28. References

- Spring for Apache Kafka — Listener Container Properties: https://docs.spring.io/spring-kafka/reference/kafka/container-props.html
- Spring for Apache Kafka — Message Listener Containers: https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html
- Spring Kafka API — ContainerProperties: https://docs.spring.io/spring-kafka/api/org/springframework/kafka/listener/ContainerProperties.html
- Apache Kafka — Authorization and ACLs: https://kafka.apache.org/documentation/#security_authz
- Apache Kafka — Consumer configuration: https://kafka.apache.org/documentation/#consumerconfigs
- Apache Kafka — Producer configuration: https://kafka.apache.org/documentation/#producerconfigs

API details and ACL implications should be checked against the Kafka broker/client and Spring Kafka versions deployed in the environment.

## 29. Conclusion

**AuthorizationException** indicates the Kafka broker rejected an operation because the principal lacks sufficient permissions on the resource. For consumers, the error can occur during poll, metadata, or group coordination before the listener receives a record; therefore, do not treat it like a normal business exception in DefaultErrorHandler. Starting in Spring Kafka 2.8, **authExceptionRetryInterval** on ContainerProperties allows the container to retry after a wait, provided the consumer has a group ID configured and corresponding version/API conditions are met.

The right way to recover is to identify the exception subtype, actual principal, and denied resource/operation; fix ACLs or identity mapping per least privilege; and verify that the container/producer actually resumes working. The retry interval only helps retry after permissions are fixed—it does not replace security policy. Safe operations require distinguishing consumer paths from producer/DLT paths, tracking auth failures alongside offset/lag progress, and never letting credentials appear in logs.

