# Handling AuthorizationException

In Spring Kafka producer operations, **AuthorizationException** indicates that Kafka recognized the client's identity but rejected an operation because that principal lacks the required permissions on the corresponding resource. The error typically stems from ACLs or cluster authorization policies—for instance, the producer lacks write permission on the topic, lacks cluster-level permission for an idempotent producer, or lacks permission to use the transactional ID.

This is a security configuration and permissions error. Repeatedly retrying message sends will not grant permissions. The application must recognize the error, preserve information about unsent events, emit alerts with sufficient context, and coordinate with the Kafka administration team to fix the permissions.

## 1. What does AuthorizationException mean?

Kafka protects resources through authentication and authorization. These two steps answer different questions:

- **Authentication** establishes who the client is. For example, the client authenticates via SASL/SCRAM, SASL/OAUTHBEARER, or a TLS client certificate.
- **Authorization** determines what an authenticated principal is permitted to do on which resources. Kafka may allow a principal to read a topic while denying writes to that topic.

When receiving **AuthorizationException**, the client has usually already passed authentication. The broker or authorizer rejected an operation because no matching ALLOW rule was found, an applicable DENY rule exists, or platform security policy forbids that operation.

Examples:

- Principal **User:billing-producer** is allowed to read topic **orders.created** but does not yet have **WRITE** permission.
- The producer enables idempotence, but the principal lacks **IDEMPOTENT_WRITE** permission on the cluster.
- A transactional producer uses a **transactional.id** in a scope where the principal has not been granted **WRITE** permission.
- The application connected to the wrong cluster or used credentials from another environment, causing a mismatch between actual principal and ACLs.

AuthorizationException does not mean the payload is invalid, the topic is full, or brokers are unavailable. Identify the rejected operation and resource before changing configurations.

## 2. Common exceptions

**org.apache.kafka.common.errors.AuthorizationException** is the base class for Kafka authorization errors. When handling it in an application, inspect both the specific exception class and the cause chain because Spring Kafka or the Kafka client may wrap the underlying error in another exception.

| Exception | Common meaning | Where to check |
|---|---|---|
| **TopicAuthorizationException** | Principal is not authorized to perform an operation on one or more topics | Check target topic, principal, **WRITE** ACL, and actual topic name |
| **ClusterAuthorizationException** | Principal was denied a cluster-level operation | Check cluster permissions; for idempotent producers, check **IDEMPOTENT_WRITE** |
| **TransactionalIdAuthorizationException** | Principal is not authorized to use the configured transactional ID | Check transactional ID and **WRITE** ACL on the transactional ID resource |
| **GroupAuthorizationException** | Principal is not authorized to operate on a consumer group | Check group ACLs; usually relates to consumers or apps that both produce and consume |
| **AuthorizationException** | Base class or uncategorized error details | Read cause chain and broker logs to determine resource and operation |

A Spring application that has both producers and consumers may hit a group authorization error even when investigating a producer. Identify which listener, transaction flow, or component raised the exception rather than assuming every authorization error is a topic write permission issue.

### Distinguishing from authentication errors

| Signal | Authentication failure | Authorization failure |
|---|---|---|
| Client identity | Could not authenticate or establish identity | Principal established, but operation was denied |
| Examples | Wrong SASL password, invalid truststore/certificate, mismatched SASL mechanism | Missing **WRITE** on topic or missing permission on transactional ID |
| First place to check | Credentials, certificates, SASL mechanism, TLS, and listener | Actual principal, ACLs, resource, operation, and host restrictions |
| Resolution | Fix authentication config or issue valid credentials | Grant least-privilege permissions or fix resource/policy |

**AuthenticationException**, **SaslAuthenticationException**, and **AuthorizationException** belong to different error categories. Do not respond to authentication failures by adding ACLs; likewise, do not rotate passwords when the broker already authenticated successfully and is denying permissions.

## 3. Which producer operations can fail?

### 3.1 Sending records to a topic

For a standard producer, the primary operation is writing records to a topic. The principal needs **WRITE** permission on the target topic.

If the application sends to **orders.created** while ACLs only permit writing to **orders.updated**, the broker can return **TopicAuthorizationException**. The error can also occur when topic names are built from environment configs, prefixes, or tenants and the actual value differs from what operations granted permissions for.

Capture accurately:

- Bootstrap cluster or environment alias the producer connects to.
- Actual topic after applying configuration and naming rules.
- Principal seen by the broker.
- Rejected operation and corresponding resource.
- Requesting host or workload if ACL policy restricts hosts.

### 3.2 Idempotent producer

An idempotent producer lets Kafka deduplicate records from internal producer retries within Kafka's supported scope. When this feature is enabled, the cluster may require the principal to have **IDEMPOTENT_WRITE** permission on the cluster resource.

This is easy to overlook: an application that already has **WRITE** on the topic can still hit **ClusterAuthorizationException** when initializing or using an idempotent producer if the cluster-level permission has not been granted.

Some Kafka client versions enable idempotence by default. Therefore, check the client version and effective configuration rather than just searching for **enable.idempotence** in YAML files. Do not disable idempotence merely to hide authorization errors; first confirm security requirements and grant permissions per platform policy.

### 3.3 Transactional producer

A transactional producer uses **transactional.id** to identify transactions. The principal needs appropriate permission on the transactional ID resource—usually the **WRITE** operation—as well as write permissions on the participating topics. If the idempotent producer requires cluster-level permission, that must also be checked.

For example, the application configures **transactional.id** with prefix **billing-tx-**, while ACLs only grant access for a different ID. When calling **initTransactions()** or executing transaction operations, the broker can reject with **TransactionalIdAuthorizationException**.

Check:

- Actual **transactional.id** value, including prefixes and suffixes generated by the application.
- ACL resource pattern: **LITERAL** or **PREFIXED**.
- **WRITE** permission on the transactional ID.
- **WRITE** permission on each topic written within the transaction.
- Required cluster permission if the producer uses idempotence.

Do not widen ACLs to allow writing any transactional ID just to avoid errors. Restrict to the prefix or IDs the workload actually uses.

## 4. Where do exceptions appear in Spring Kafka?

Producers send data asynchronously. Therefore, authorization errors can appear via two paths:

1. **Synchronous error at API call**: calling **KafkaTemplate.send(...)** can throw an exception immediately if the error occurs before the record enters the send pipeline.
2. **Asynchronous error**: calling **send(...)** returns a future, which later completes exceptionally when the producer receives a broker response or handles a send failure.

In Spring Kafka 3.x, **KafkaTemplate.send(...)** returns **CompletableFuture<SendResult<K, V>>**. In older Spring Kafka versions, the future API may be **ListenableFuture**; use callbacks matching your running version.

Do not check only the outermost exception class. The Kafka client and Spring Kafka may wrap the root exception. Traverse the cause chain to locate **AuthorizationException** or its subclasses.

### Example handling futures with Spring Kafka 3.x

~~~java
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;
import java.util.concurrent.CompletableFuture;

import org.apache.kafka.common.errors.AuthorizationException;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.support.SendResult;

public class OrderPublisher {

    private final KafkaTemplate<String, OrderCreated> kafkaTemplate;

    public OrderPublisher(
            KafkaTemplate<String, OrderCreated> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreated event) {
        try {
            CompletableFuture<SendResult<String, OrderCreated>> future =
                    kafkaTemplate.send(
                            "orders.created",
                            event.orderId(),
                            event
                    );

            future.whenComplete((result, failure) -> {
                if (failure == null) {
                    // Broker acknowledged the record per producer configuration.
                    return;
                }

                AuthorizationException authorization =
                        findAuthorizationException(failure);

                if (authorization != null) {
                    // Record security configuration error and trigger alert.
                    // Event must be retained via outbox or recovery mechanism.
                    handleAuthorizationFailure(event, authorization);
                    return;
                }

                handleOtherPublishFailure(event, failure);
            });

        } catch (RuntimeException failure) {
            // Cover errors occurring directly during the send() call.
            AuthorizationException authorization =
                    findAuthorizationException(failure);

            if (authorization != null) {
                handleAuthorizationFailure(event, authorization);
            } else {
                handleOtherPublishFailure(event, failure);
            }
        }
    }

    private static AuthorizationException findAuthorizationException(
            Throwable failure) {

        Set<Throwable> visited =
                Collections.newSetFromMap(new IdentityHashMap<>());

        for (Throwable current = failure;
             current != null && visited.add(current);
             current = current.getCause()) {

            if (current instanceof AuthorizationException authorization) {
                return authorization;
            }
        }

        return null;
    }

    private void handleAuthorizationFailure(
            OrderCreated event,
            AuthorizationException failure) {
        // Write structured log, emit alert, and persist failed send status.
        // Do not log credentials or full sensitive payloads.
    }

    private void handleOtherPublishFailure(
            OrderCreated event,
            Throwable failure) {
        // Apply policy for other send failures.
    }
}
~~~

The example illustrates detecting errors on both synchronous and asynchronous paths. The internal handler methods should be implemented according to your system's persistence and monitoring mechanisms. When using transactions, propagate the exception across the transaction boundary so the transaction is aborted or rolled back per configuration; never swallow exceptions and report success.

### Why check both error paths?

If you only attach **whenComplete**, an exception thrown directly by **send()** can escape before the callback is registered. Conversely, if you only use **try/catch**, errors arising after the producer sends the request will live inside the future and will not be caught by the **catch** block.

In both cases, share the same error classification logic to avoid divergent handling between synchronous and asynchronous errors.

## 5. AuthorizationException investigation workflow

### Step 1: Identify the right producer and cluster

Start from the instance or workload raising the error. Determine the environment, bootstrap servers, application name, Kafka client/Spring Kafka version, and error timestamp.

Do not infer the cluster merely from a service name in logs. A deployment may receive settings from environment variables, ConfigMaps, secrets, or profiles differing from files in the repository. Verify the application's effective runtime values without printing credentials to logs.

### Step 2: Find the root exception and rejected resource

Inspect the full cause chain and specific exception class name. For **TopicAuthorizationException**, identify the involved topic list. For **ClusterAuthorizationException**, identify the cluster operation being attempted. For **TransactionalIdAuthorizationException**, obtain the actual transactional ID.

Details needed before requesting permissions:

| Field | Example |
|---|---|
| Workload | **billing-service** |
| Environment | **staging** |
| Cluster alias | **kafka-staging** |
| Principal | **User:billing-producer** |
| Resource type | **Topic** |
| Resource name | **orders.created** |
| Operation | **WRITE** |
| Client host/workload | Pod or host issuing the request |
| Timestamp | Timestamp with timezone |
| Exception | **TopicAuthorizationException** |

The example illustrates the information format; supply real values captured from the client and broker.

### Step 3: Verify the principal seen by the broker

The principal in application configuration does not always match the principal string evaluated by the authorizer. With SASL, the principal depends on authentication mechanism and mapping config. With TLS, the principal may be constructed from the certificate's distinguished name or a principal builder.

Check broker logs to see which principal was actually denied. An authorizer log often contains details like:

~~~text
Principal = User:billing-producer
Operation = WRITE
Resource = Topic:LITERAL:orders.created
Result = DENIED
~~~

This format is illustrative and not a fixed message across every Kafka version or provider. Actual broker logs may phrase it differently.

If the principal does not match expected ACLs, investigate SASL mechanism, certificates, principal mapping, listeners, and workload credentials before modifying ACLs.

### Step 4: Check ACLs and resource patterns

Verify permissions on the right cluster and resource. Check:

- Does the ACL apply to the exact principal?
- Is the resource name spelled accurately with the right prefix and naming rules?
- Is the ACL **LITERAL** or **PREFIXED**?
- Does the operation match the denied operation?
- Does the ACL have host restrictions that exclude the current workload?
- Is there a matching DENY ACL blocking the operation?
- Which cluster and listener are the permissions granted on?

A literal ACL for **orders.*** is not equivalent to a prefixed ACL for **orders.**. Likewise, permission on an identically named topic in staging grants no permission on production.

### Step 5: Check whether producer config enables features needing separate ACLs

If the error is cluster authorization, inspect **enable.idempotence** and the Kafka client version. If the producer uses transactions, inspect **transactional.id** and participating topics.

Never assume topic **WRITE** alone suffices for every producer. Idempotent and transactional producers impose additional authorization requirements.

### Step 6: Fix permissions via governance workflow

Once missing ACLs are confirmed, send the platform team the principal, resource, operation, cluster, environment, and error evidence. The authorized team will grant permissions according to organizational governance.

After permissions are updated, send a controlled test record and confirm broker acknowledgement. Also check broker logs to verify the operation is no longer denied. If ACLs are correct yet errors persist, verify actual principal, cache/policy propagation, and cluster endpoints before making further changes.

## 6. Least-privilege permissions for producers

For Kafka clusters using the standard ACL authorizer, permissions typically needed include:

| Scenario | Resource | Typical operation needed |
|---|---|---|
| Producer sends records to an existing topic | Target topic | **WRITE** |
| Producer uses idempotence | Cluster | **IDEMPOTENT_WRITE** |
| Transactional producer | Transactional ID | **WRITE** |
| Transactional producer writing records | Each target topic | **WRITE** |
| App creates topics via KafkaAdmin/AdminClient | Topic or Cluster depending on creation call | **CREATE** per cluster rules |

The table above guides standard Kafka ACL authorizer setups. Managed Kafka platforms may use IAM, RBAC, or custom policies; follow the provider's authorization model in those cases.

A producer that only writes to existing topics normally does not need cluster admin or topic creation permissions. Provision topics via platform governance workflows. Never grant **ALL** or broad **CREATE** rights to an application merely to resolve publish errors.

### Example inspecting ACLs with kafka-acls

On clusters using the standard Kafka ACL authorizer, administrators can list relevant ACLs using **kafka-acls.sh**:

~~~bash
kafka-acls.sh \
  --bootstrap-server broker.example:9092 \
  --command-config admin.properties \
  --list \
  --topic orders.created \
  --principal User:billing-producer
~~~

To grant write permission on a specific topic:

~~~bash
kafka-acls.sh \
  --bootstrap-server broker.example:9092 \
  --command-config admin.properties \
  --add \
  --allow-principal User:billing-producer \
  --operation Write \
  --topic orders.created
~~~

If the producer requires idempotence and the authorizer requires the corresponding cluster permission, an administrator can grant it on the cluster:

~~~bash
kafka-acls.sh \
  --bootstrap-server broker.example:9092 \
  --command-config admin.properties \
  --add \
  --allow-principal User:billing-producer \
  --operation IdempotentWrite \
  --cluster
~~~

For transactional producers, grant **Write** on the exact transactional ID or prefix used by the workload. Example granting on a specific ID:

~~~bash
kafka-acls.sh \
  --bootstrap-server broker.example:9092 \
  --command-config admin.properties \
  --add \
  --allow-principal User:billing-producer \
  --operation Write \
  --transactional-id billing-tx-01
~~~

If the application generates transactional IDs with per-instance suffixes, the platform team can use a **PREFIXED** resource pattern aligned with naming conventions and the active Kafka version. Confirm prefix scope before applying.

The commands above are examples for administrators with cluster privileges. Replace bootstrap server, principal, topic, and transactional ID with verified values. Never pass passwords directly on the command line or commit admin credentials to a repository. If your organization manages ACLs via GitOps, cloud UI, or IAM/RBAC systems, use that official workflow instead of CLI commands.

After granting permissions, list ACLs again and test from the exact workload/principal. An ACL grant command succeeding does not prove the live producer is actually using that principal.

## 7. Application-layer error handling

### Do not retry infinitely

Producer retries handle recoverable send-layer errors. Authorization failures are generally unrecoverable by resending the same request while ACLs and principal remain unchanged.

Continuous retries will:

- Increase broker requests and log volume.
- Generate duplicate alerts.
- Fill application-side queues or buffers.
- Obscure the underlying configuration root cause.
- Risk losing events if the app only buffers them in memory and the process restarts.

Classify **AuthorizationException** as a configuration/permission error, stop retrying the failing record quickly, and trigger the designed recovery flow. After ACLs are fixed and verified, the application can resend records under a bounded retry policy.

### Preserving unsent events

If events must not be lost, do not simply log the exception and move on. Ways to preserve events include:

- **Transactional outbox**: store events in the database within the same transaction as business changes; a publisher reads unsent events and marks them published after acknowledgement.
- **Durable retry store**: persist the event with status, attempt count, failure time, and routing metadata.
- **Request failure**: if a synchronous API depends on publishing, return an error per API contract and allow callers to retry safely using an idempotency key.

Do not rely on an in-memory list as the sole store for critical events. On service restart, in-memory data can be lost. When using an outbox, ensure status updates and publishing handle the case where publishing succeeded but the process stopped before marking status; the publisher may re-send and consumers still need idempotency.

### Do not swallow exceptions inside transactions

With transactional producers, authorization errors during transaction initialization or commit must propagate to the transaction management boundary so the application handles transaction state properly. Never catch the exception and still return success. Once a transaction fails, never assume records sent inside it were committed.

For Kafka transactions, only records from committed transactions are visible to consumers using **read_committed**. Recovery workflows must follow actual producer/transaction state; never attempt to continue a failed transaction.

### Distinguishing authorization errors from business errors

AuthorizationException is a security operational error. Do not route records to a business DLT merely because the broker rejected the producer sending them: if the producer lacks permission to write to the target topic, it likely lacks permission to write to the DLT as well. DLTs fit consumer flows that read records successfully and then fail business processing, per error handler policy.

If failed records must be saved, use an outbox or a recovery store that the application is authorized to write to and that was designed for this scenario.

## 8. Observability, logging, and alerting

A well-operated system reveals which producer, topic, and principal hit the error without exposing credentials or sensitive data.

### Recommended log fields

| Field | Purpose |
|---|---|
| **service** and **environment** | Identify workload and environment |
| **cluster_alias** | Distinguish target cluster |
| **principal** | Correlate identity with ACLs |
| **topic** | Identify rejected resource |
| **operation** | Know which permission is needed |
| **exception_class** | Classify the error |
| **event_id** or correlation ID | Track events needing recovery |
| **timestamp** | Correlate client and broker logs |
| **attempt** | Know how many send attempts were tried |

Never log passwords, SASL JAAS configs, access tokens, private keys, or full payloads just to diagnose authorization. If events contain personal data or payment info, log only approved IDs/correlation IDs.

### Alerts to monitor

- Count of authorization failures by service, cluster, and exception class.
- Count of rejected topics or transactional IDs.
- Count of events waiting to be published in the outbox/recovery store.
- Age of the oldest unpublished event.
- Time from error detection until ACLs are fixed and publishing recovers.
- Send success rate after remediation.

A good alert should identify principal, resource, operation, and environment so the platform team can act. Avoid sending alerts with only a generic **Kafka send failed** message.

## 9. Production remediation runbook

When an AuthorizationException alert fires, follow this sequence:

1. Identify the failing service, instance, environment, and cluster alias.
2. Collect the specific exception and cause chain from the producer.
3. Extract the rejected topic or transactional ID and operation.
4. Verify the actual principal in broker logs.
5. Check ACLs, resource patterns, host restrictions, and DENY ACLs.
6. If the producer is idempotent, verify **IDEMPOTENT_WRITE** on the cluster.
7. If the producer is transactional, verify **WRITE** on the transactional ID and topics.
8. Request the authorized team to fix ACLs following least privilege.
9. Verify ACLs after the change and send a test record from the actual workload.
10. Replay pending events from the outbox/recovery store according to ordering and application idempotency policies.
11. Monitor publish success, backlog, consumer lag, and new errors after recovery.
12. Document root cause, permissions changed, and how to prevent recurrence.

Never clear the backlog or mark events as published just to silence alerts. Close the incident only after confirming required records were published and recovery states were updated accurately.

## 10. Pre-release testing

Authorization tests should run against an environment with brokers and authorizers equivalent to production. Mock producers can verify exception-handling code branches, but do not prove broker ACLs work properly.

Useful test scenarios:

| Scenario | Expected outcome |
|---|---|
| Principal has **WRITE** on topic | Producer sends successfully and receives acknowledgement |
| Principal lacks **WRITE** on topic | Producer receives **TopicAuthorizationException**; event is retained for recovery |
| Idempotent producer lacks **IDEMPOTENT_WRITE** | Broker rejects cluster operation; alert names principal and cluster |
| Unauthorized transactional ID | Transaction init or corresponding operation fails; app does not report success |
| Principal used in wrong environment | Logs and diagnostics pinpoint actual cluster/principal |
| ACL fixed after incident | Producer resends successfully; backlog drains per policy |
| Broker returns non-authorization error | Error is routed to appropriate retry/recovery branch, not mislabeled as ACL |

Use test principals with limited permissions and verify both client and broker logs. Never test by revoking ACLs on a production workload serving live traffic.

## 11. Common handling mistakes

**Only increasing retries or delivery timeout.** Those settings do not create ACL permissions. Fix the principal or policy before retrying.

**Granting ALL permissions to the application principal.** This may silence errors immediately but overly broadens access. Grant the exact operations on the exact resources.

**Checking only topic ACLs.** Idempotent and transactional producers have extra authorization requirements on the cluster or transactional ID.

**Looking only at the principal name in config.** The actual principal may differ due to SASL, TLS, or principal mapping. Check broker logs.

**Catching exceptions only around callbacks.** Errors can occur synchronously right at `send()`. Cover both paths and share classification logic.

**Logging the exception and dropping the event.** Producer failure can mean Kafka never received the event. If the event is important, use an outbox or durable recovery storage.

**Routing producer errors straight to a DLT.** The producer may lack permission to write to the DLT as well; business DLTs also do not replace durable storage for unpublished events.

**Restarting the service without fixing ACLs.** Restarting does not change a principal's permissions. Only consider recreating producers/clients if needed after policies or credentials are fixed and client state requires it.

## 12. Operations checklist

**Error identification**

- [ ] Distinguish authentication failure from authorization failure.
- [ ] Capture root exception and full cause chain.
- [ ] Identify exact cluster, topic, operation, or transactional ID.
- [ ] Cross-check the principal seen by the broker.

**Permission verification**

- [ ] Producer has **WRITE** on the target topic.
- [ ] Idempotent producer has **IDEMPOTENT_WRITE** if required by the authorizer.
- [ ] Transactional producer has **WRITE** on the transactional ID and involved topics.
- [ ] Resource patterns, host restrictions, and DENY ACLs have been checked.
- [ ] Permissions are granted on the right cluster and environment.

**Application recovery**

- [ ] Both synchronous exceptions and failed futures are handled.
- [ ] Authorization failures are not retried infinitely.
- [ ] Unpublished events are persisted in an outbox or durable recovery mechanism.
- [ ] Exceptions are not swallowed inside transactions.
- [ ] After ACL fixes, events are replayed per idempotency policy.

**Observability and process**

- [ ] Logs include principal, resource, operation, cluster, timestamp, and event/correlation ID.
- [ ] Credentials and sensitive payloads are not logged.
- [ ] Alerts guide the responsible team to inspect ACLs.
- [ ] Runbook identifies who is authorized to change permissions and how to verify changes.
- [ ] Tested in a production-equivalent environment.

## 13. Operational principles

When a Spring Kafka producer encounters AuthorizationException, treat it as a signal that an authenticated identity is attempting an operation beyond its granted permissions. Identify the rejected principal, resource, and operation, then update policy following least privilege.

On the application side, detect errors on both synchronous and asynchronous paths, inspect the cause chain, avoid infinite retries, and preserve unpublished events. On the platform side, verify the actual principal, ACLs, and resource patterns on the right cluster, then grant appropriate permissions for topics, cluster, or transactional IDs. Only after testing from the actual workload and confirming broker acknowledgements should the publish flow be considered recovered.
