# Producer ACLs

In Kafka, **producer ACLs** determine which principal is allowed to write data to a topic and use required producer features. A Spring Kafka application can connect to a broker and pass SASL/TLS authentication yet still not be allowed to publish. After authentication, the broker performs authorization based on the principal, resource, operation, and active ACLs.

Proper ACL design restricts a service to writing only to the topics it owns. For producers using idempotence or Kafka transactions, required permissions also involve the **Cluster resource** and **TransactionalId resource**, in addition to topic write permissions. This lesson covers the ACL model, least privilege, admin commands, Spring Boot configuration, transaction IDs, retry/DLT, testing, and operational runbooks.

## 1. Authentication and Authorization Are Two Separate Steps

- **Authentication:** the broker identifies who the client is. For example, principal `User:orders-producer` is authenticated via SASL/SCRAM, SASL/OAUTHBEARER, or TLS client certificate.
- **Authorization:** the broker checks whether the principal is allowed to perform an operation on a resource. For example, `User:orders-producer` has `WRITE` permission on topic `orders.events`.

~~~mermaid
sequenceDiagram
    participant P as Spring Kafka Producer
    participant B as Kafka Broker
    participant A as Kafka Authorizer
    P->>B: Connect + SASL/TLS authentication
    B-->>P: Authenticated principal
    P->>B: Produce record to orders.events
    B->>A: Check WRITE ACL on topic
    alt Matching ACL exists
        A-->>B: Allow
        B-->>P: Produce result
    else Lacks permission
        A-->>B: Deny
        B-->>P: TopicAuthorizationException
    end
~~~

A client can connect to the broker successfully yet be denied writing to a topic; write to topic A yet not topic B; write to a regular topic yet be unable to initialize a transaction; or authenticate as an unexpected principal due to misconfigured SASL/TLS.

**ACLs do not replace authentication.** A valid username/password does not automatically grant permission to write to a topic.

## 2. How Kafka ACLs Model Resources and Operations

| Resource | Example | Role |
|---|---|---|
| `TOPIC` | `orders.events` | Permission to write/read topic data. |
| `CLUSTER` | Kafka cluster | Cluster-scoped permissions, such as idempotent writes. |
| `TRANSACTIONAL_ID` | `orders-tx-...` | Permission to use a transactional producer identity. |
| `GROUP` | `orders-service` | Primarily related to consumer groups, not regular topic writes. |

Commonly relevant operations:

| Operation | Meaning |
|---|---|
| `WRITE` | Write records to a topic or use a transactional ID depending on resource type. |
| `DESCRIBE` | View metadata of a resource. |
| `CREATE` | Create a resource within the granted scope. |
| `ALTER` | Modify configuration/state of a resource per supported APIs. |
| `DELETE` | Delete a resource. |
| `IDEMPOTENT_WRITE` | Allow a producer to use idempotent writes on the cluster resource. |
| `ALL` | All operations; usually too broad for runtime producers. |

Kafka has implication rules between operations. For example, `WRITE` on a topic typically implies `DESCRIBE` according to ACL semantics. However, do not assume every other API is implied; verify which operations the broker checks for your Kafka version.

An ACL entry includes a principal, host, operation, permission type (`ALLOW` or `DENY`), resource type/name, and pattern type such as `LITERAL` or `PREFIXED`.

## 3. Minimum Permissions for a Topic-Writing Producer

For a producer not using Kafka transactions, the core permissions are:

- `WRITE` on the destination topic.
- Required metadata permissions per ACL semantics/version; `WRITE` on a topic typically implies `DESCRIBE`.
- If the producer uses idempotence, grant `IDEMPOTENT_WRITE` on the cluster resource per Kafka's authorization model.
- If the application creates topics itself, `CREATE` permission must be granted separately within resource scope; topics should normally be provisioned by a dedicated admin principal.

Example for a service publishing only to `orders.events`:

~~~text
Principal:
  User:orders-producer

Allowed:
  TOPIC orders.events -> WRITE
  CLUSTER kafka-cluster -> IDEMPOTENT_WRITE (if using idempotence)

Not needed for a typical runtime producer:
  TOPIC payments.events -> WRITE
  TOPIC orders.events -> DELETE
  CLUSTER kafka-cluster -> ALTER
  CLUSTER kafka-cluster -> CREATE
~~~

A producer does not need permission to read a topic simply because it writes data to that topic. If the application also has consumers, AdminClient, Schema Registry, or DLT publishing, analyze each function and grant permissions separately.

### WRITE Is Not CREATE

`WRITE` allows publishing to an existing topic. `CREATE` relates to creating new topics. Do not grant `CREATE` to runtime producers when topics are provisioned through a separate infrastructure process.

If the broker enables `auto.create.topics.enable`, a producer sending to a nonexistent topic may trigger topic creation depending on cluster config and ACL policy. Exact behavior depends on Kafka version and authorizer. Production should provision topics beforehand to prevent typos in topic names from creating unintended topics.

## 4. Which Cluster Permission Does an Idempotent Producer Need?

Kafka producer idempotence helps prevent duplicates caused by producer retries within protocol scope. With Kafka ACL authorization, an idempotent producer needs the `IDEMPOTENT_WRITE` operation on the `CLUSTER` resource.

Distinguish:

- `TOPIC / WRITE`: allowed to write to the target topic.
- `CLUSTER / IDEMPOTENT_WRITE`: allowed to use the idempotent write mechanism.
- `TRANSACTIONAL_ID / WRITE`: allowed to use a transactional identity if the producer uses transactions.

If a producer writes to a topic successfully when idempotence is disabled but hits `ClusterAuthorizationException` after enabling idempotence, the principal may be missing `IDEMPOTENT_WRITE` on the cluster.

In modern Kafka clients, idempotence is often enabled by default when configuration is compatible. Do not assume a producer has idempotence disabled just because the application does not declare the property; inspect the effective producer config and Kafka client version.

**Idempotence does not equal transactions.** Idempotence protects send retries at the producer protocol level; it does not create consume-transform-produce transactions and does not span databases/HTTP.

## 5. Which Permissions Does a Transactional Producer Need?

Kafka transactions allow a producer to write multiple records and, in consume-transform-produce, coordinate output records with input offsets in the same transaction when the container/transaction manager is configured properly.

A transactional producer typically needs:

1. `WRITE` on each topic the producer writes to.
2. `WRITE` on the `TRANSACTIONAL_ID` resource matching the actual transactional ID.
3. `IDEMPOTENT_WRITE` on the cluster resource per Kafka's authorization requirements.
4. Additional permissions if the application also performs admin/consumer operations; do not infer them from transaction permissions.

Example:

~~~text
Principal:
  User:orders-transactional-producer

Resources:
  TOPIC orders.events.out -> WRITE
  TRANSACTIONAL_ID orders-tx-orders-service-* -> WRITE
  CLUSTER kafka-cluster -> IDEMPOTENT_WRITE
~~~

`TRANSACTIONAL_ID` is a separate resource. A `WRITE` ACL on a topic does not grant permission to use a transactional ID; transactional ID permission also does not allow writing to arbitrary topics.

If the producer uses a specific transactional ID `orders-tx-pod-a-0`, the ACL must match that ID. If Spring Kafka generates IDs using a prefix and suffix, the pattern must match all generated IDs. Do not grant overly broad prefixes like `*` across all applications' transactional IDs: one producer could interfere with another producer's lifecycle via fencing.

## 6. Granting ACLs with `kafka-acls.sh`

Kafka provides the `kafka-acls.sh` CLI to manage ACLs. Examples use `--bootstrap-server` and a client config file with ACL admin privileges. Protect config files and do not commit secrets to source control.

### Allowing a producer to write to a topic

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-producer \
  --operation Write \
  --topic orders.events
~~~

This command grants `WRITE` on topic `orders.events`. Avoid using the `--producer` shortcut when least-privilege policy and clear operation auditing are required; shortcuts may grant extra convenience operations depending on CLI version.

### Allowing idempotent write

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-producer \
  --operation IdempotentWrite \
  --cluster
~~~

The CLI operation name is typically `IdempotentWrite`; confirm the help output of your deployed Kafka version. This permission applies to the cluster resource, not a topic resource.

### Allowing a transactional producer

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-producer \
  --operation Write \
  --transactional-id orders-tx-orders-service- \
  --resource-pattern-type prefixed
~~~

This example uses a prefix pattern to match transactional IDs starting with `orders-tx-orders-service-`. The prefix must be distinct across services/environments/instances. If the producer uses a single fixed ID, a literal ACL can be granted for that ID.

### Host restriction

ACLs can be restricted by host if the infrastructure has stable source addresses and the authorizer supports it. In Kubernetes, pod IPs frequently change; restricting to static pod IPs can break producer permissions during rollouts. Consider network policies and service identities before adding host restrictions.

## 7. Inspecting Granted ACLs

List policies for a topic:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --list \
  --topic orders.events
~~~

List ACLs by principal:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --list \
  --principal User:orders-producer
~~~

Check transactional IDs:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --list \
  --transactional-id orders-tx-orders-service-
~~~

CLI options and resource pattern filters can vary slightly across Kafka versions. Use `kafka-acls.sh --help` for your distribution and verify results against the target cluster.

When inspecting, cross-check the actual principal, resource name, resource pattern type, operation, host restriction, matching DENY ACLs, authorizer configuration, and target cluster. An ALLOW ACL with the right topic name but wrong principal or wrong pattern type will still deny the producer.

## 8. Literal and Prefixed Resource Patterns

Kafka ACLs can apply to literal or prefixed resources.

| Pattern | Resource | Principal | Scope |
|---|---|---|---|
| Literal | `orders.events` | `User:orders-producer` | Only this topic. |
| Prefixed | `orders.` | `User:orders-producer` | Topics starting with `orders.`. |
| Literal | `orders-tx-a-0` | `User:orders-producer` | A single transactional ID. |
| Prefixed | `orders-tx-prod-` | `User:orders-producer` | Transactional IDs with that prefix. |

Literal is the safe default when a service only needs to write to one topic. Prefixed is convenient when a service owns a managed set of topics/transactional IDs, provided the prefix is narrow and follows naming conventions.

Do not grant prefix `orders` if topics such as `orders-admin`, `orders-audit`, or `orders-sensitive` have different owners/permissions. Broad prefixes can inadvertently open access to resources created in the future.

## 9. DENY ACLs and Broader Permissions

Kafka ACLs support allow and deny rules. When a deny ACL matches principal/host/resource/operation, it can block another allow ACL matching the same request according to authorizer semantics. Therefore, adding a new ALLOW rule does not always fix an authorization error.

~~~text
ALLOW User:orders-producer WRITE TOPIC orders.events
DENY  User:*               WRITE TOPIC orders.events
~~~

This illustrates a policy conflict. Read matching ACLs and broker logs before making changes; do not remove a broad deny ACL if it is an intentional security policy.

Superuser principals can bypass authorization per authorizer configuration. Do not use superuser credentials for routine producer applications.

## 10. Removing ACLs When Revoking Permissions

When a service stops using a topic or a principal is retired, remove the exact ACL granted:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --remove \
  --allow-principal User:orders-producer \
  --operation Write \
  --topic orders.events \
  --force
~~~

`--force`/confirmation syntax depends on Kafka CLI version. Before removing, verify the principal and resource, check whether another instance still uses the ACL, record an audit/change ticket, and define a rollback plan in case of accidental removal.

Do not delete all ACLs for a principal if the goal is only to revoke one topic.

## 11. Separate Principals per Producer Service

A key principle is **each workload has its own identity**:

~~~text
User:orders-producer-prod
  WRITE -> orders.events
  IDEMPOTENT_WRITE -> cluster (if needed)

User:payments-producer-prod
  WRITE -> payments.events
  IDEMPOTENT_WRITE -> cluster (if needed)

User:shipping-producer-prod
  WRITE -> shipping.events
  IDEMPOTENT_WRITE -> cluster (if needed)
~~~

If all services share `User:application`, ACLs cannot limit the blast radius per service. When one credential leaks, an attacker gains every permission of the shared principal.

Separate principals by service/application, environment, producer/consumer role, runtime/admin identity, and tenant when strong isolation is required. Do not use Kafka administrative credentials in Spring Boot runtime just so a producer can auto-create topics.

## 12. Spring Boot Configuration for SASL/SCRAM and Producer

Example producer configuration using SASL_SSL/SCRAM-SHA-512:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.example.net:9093
    properties:
      "[security.protocol]": SASL_SSL
      "[sasl.mechanism]": SCRAM-SHA-512
      "[sasl.jaas.config]": org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-producer" password="injected-secret";
    producer:
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.springframework.kafka.support.serializer.JsonSerializer
      properties:
        "[enable.idempotence]": true
~~~

This is an illustrative example; adjust serializers, broker endpoints, and authentication mechanisms for your environment. Secrets should be injected from a secret manager/environment, not committed to YAML or printed to logs. Inspect effective configuration in the application, especially JAAS strings containing semicolons.

`acks=all` is a durability/producer acknowledgment choice, not an ACL. `enable.idempotence=true` is a producer behavior, which does not automatically grant `IDEMPOTENT_WRITE` to the principal. Both configuration layers must align.

### SASL Authentication Does Not Grant WRITE

When Spring Boot constructs the producer, the broker authenticates the principal via SASL. ACLs then check `WRITE`. If SASL succeeds but the ACL is missing, the application still receives an authorization exception.

Do not try to resolve `TopicAuthorizationException` by rotating the password if authentication already succeeded with the right principal. Inspect broker logs and ACLs before rotating credentials.

## 13. Spring Kafka Transactional Producers and Transaction ID Prefix

Spring Kafka can configure Kafka transactions via a transaction ID prefix. With Spring Boot:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-tx-prod-
~~~

Spring Kafka uses the prefix to generate transactional IDs for producer instances. Final IDs are built from the prefix and suffix per the producer factory mechanism. Ensure the prefix **does not conflict across independent applications/instances that may run concurrently**.

Grant the prefix ACL:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-producer-prod \
  --operation Write \
  --transactional-id orders-tx-prod- \
  --resource-pattern-type prefixed
~~~

If multiple environments share a cluster, the prefix should include environment and service identity, such as `orders-tx-prod-` and `orders-tx-staging-`. Do not grant a shared prefix like `orders-tx-` if the principal does not need to use transaction IDs across all environments.

### Producer Fencing Is Different from ACLs

If two producers use the same transactional ID, Kafka can fence the older producer when the newer producer initializes. Distinguish:

- `TransactionalIdAuthorizationException`: principal is not authorized to use the transactional ID.
- `ProducerFencedException`: producer lost ownership of the transactional ID/epoch.
- `TopicAuthorizationException`: principal is not authorized to write to the topic.
- `ClusterAuthorizationException`: missing cluster operation permission such as idempotent write or another operation.

Fixing ACLs does not resolve transactional ID collisions; increasing retries also does not fix identity design.

## 14. Does a Producer Need Topic CREATE Permission?

Usually **no** if topics are pre-provisioned. A runtime producer only needs to write to topics already created and granted appropriate ACLs.

If the application uses `KafkaAdmin` or `NewTopic` beans to create topics at startup, AdminClient may need permissions to create/describe/configure topics per API and cluster policy. That is an administrative permission, so consider separating:

~~~text
Provisioning identity:
  CREATE/ALTER/DESCRIBE_CONFIGS per governance process

Runtime producer identity:
  WRITE on designated topics
  IDEMPOTENT_WRITE on cluster if needed
  WRITE on transactional ID if transactional
~~~

Separating provisioning identity from runtime identity reduces application privileges. If startup topic creation is mandatory, use a narrowly scoped admin principal with separate auditing; do not grant CREATE/ALTER/DELETE to every producer.

## 15. Schema Registry Is a Separate Authorization Layer

Many systems use Avro, Protobuf, or JSON Schema. Producers may need to register/fetch schemas from Schema Registry before serializing. **Kafka broker ACLs do not grant Schema Registry permissions.**

Kafka ACLs may permit `WRITE` on topic `orders.events` while Schema Registry still denies registering a schema under the corresponding subject. The producer will fail at serialization/registry before successfully sending the record to the broker.

When a producer cannot publish, determine whether the failure is in Kafka broker authentication, Kafka ACLs, Schema Registry authorization, serialization/compatibility, or broker/network/producer send. Do not grant additional Kafka topic `WRITE` permissions to fix Schema Registry errors.

## 16. Producers Writing to Multiple Topics Need Separate ACLs

A service may publish to multiple destinations:

~~~text
orders-service
  orders.events
  orders.audit
  orders.events.DLT
  orders.events-retry-2000
~~~

List all actual destinations: business output topics, retry topics, DLT, and audit/outbox topics. Spring Kafka retry infrastructure can create or use retry/DLT topics. The publishing principal of the retry infrastructure needs appropriate permissions on those actual destinations. Do not grant `WRITE` only on the original topic and assume retry/DLT topics are covered.

If using retry-topic auto creation, topic creation is a separate provisioning responsibility. Check Spring Kafka Admin setup and required ACLs; do not grant broad `CREATE`/`ALTER` to runtime producers just to make startup "stop failing."

DLT can use the same principal if one workload owns both business output and DLT, or a separate principal if the organization separates operational/audit permissions. Either way, DLT permissions need a clear owner.

## 17. Common Authorization Exceptions

| Exception | Possible Cause | ACL to Check |
|---|---|---|
| `TopicAuthorizationException` | Lacks permission to write to the topic or one of the target topics | `TOPIC / WRITE` for principal/topic. |
| `ClusterAuthorizationException` | Lacks permission for a cluster-level operation | `CLUSTER / IDEMPOTENT_WRITE` if producer is idempotent; check operation in broker logs. |
| `TransactionalIdAuthorizationException` | Lacks permission to use the transactional ID | `TRANSACTIONAL_ID / WRITE` for actual ID/prefix. |
| `AuthenticationException` | Principal not authenticated | SASL/TLS credentials/mechanism, certificate, token. |
| `SerializationException` | Payload/schema/serializer error | Serializer/schema contract; not a Kafka topic ACL by default. |

Kafka clients and Spring Kafka versions may wrap exceptions differently. Read the **root cause** and broker authorization logs, not just the wrapper exception from the listener container.

Many authorization exceptions are policy errors and will not self-heal without ACL changes. Continuous retries can cause a log storm. Once permissions are granted, the producer may need to retry according to client lifecycle; if authz state does not recover automatically, coordinate producer/container restarts through a verified procedure.

## 18. Least-Privilege ACL Provisioning Process

1. **Identify workload:** service, environment, principal, owner.
2. **List operations:** topic WRITE, idempotent write, transactional ID write, and genuinely needed auxiliary permissions.
3. **List resources:** literal/prefixed topics, cluster, transactional ID.
4. **Verify effective principal:** confirm SASL/TLS produces the expected principal.
5. **Inspect existing ACLs:** list by principal and resource.
6. **Create change:** grant the minimal required ACLs with a ticket/audit record.
7. **Verify policy:** confirm no DENY rules, host restrictions, or pattern mismatches interfere.
8. **Test producer:** send a controlled test record to the right topic.
9. **Verify outcome:** producer ack, broker logs, and consumer/offsets if needed.
10. **Record evidence:** principal, resource, operation, pattern, and timestamp.
11. **Monitor:** authorization errors and producer send rates after the change.
12. **Revoke:** remove permissions when the workload/topic is retired.

Do not use an admin principal to test runtime applications; doing so hides missing ACLs on the service principal.

## 19. Example ACLs for a Standard Producer

Requirement: service `orders-producer-prod` only publishes to `orders.events`, uses idempotence, and does not use transactions.

~~~bash
# Topic write
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-producer-prod \
  --operation Write \
  --topic orders.events

# Idempotent write permission
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-producer-prod \
  --operation IdempotentWrite \
  --cluster
~~~

Producer config:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.example.net:9093
    properties:
      "[security.protocol]": SASL_SSL
      "[sasl.mechanism]": SCRAM-SHA-512
      "[sasl.jaas.config]": org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-producer-prod" password="injected-secret";
    producer:
      acks: all
      properties:
        "[enable.idempotence]": true
~~~

Verify the broker receives principal `User:orders-producer-prod`, the topic ACL matches `orders.events`, the cluster ACL matches the cluster, producer sends are acknowledged per policy, and the producer is denied `WRITE` on out-of-scope topics. `ALL` on the cluster or `CREATE` is unnecessary when the topic is already provisioned.

## 20. End-to-End Transactional Producer Example

Requirement: service publishes `orders.events.out` using Spring Kafka transactions with prefix `orders-tx-prod-`.

Topic ACL:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-producer-prod \
  --operation Write \
  --topic orders.events.out
~~~

Transactional ID ACL:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-producer-prod \
  --operation Write \
  --transactional-id orders-tx-prod- \
  --resource-pattern-type prefixed
~~~

Cluster idempotent ACL:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-producer-prod \
  --operation IdempotentWrite \
  --cluster
~~~

Spring Boot:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-tx-prod-
      acks: all
      properties:
        "[enable.idempotence]": true
~~~

In production, the prefix must be unique across producer applications/instances based on how Spring Kafka generates transactional IDs. The ACL prefixed pattern must match the actual IDs. A wrong prefix or overly broad ACL prefix can cause authorization errors or producer fencing.

## 21. Distinguishing Runtime Permissions from AdminClient Permissions

Spring Boot can auto-configure KafkaAdmin/AdminClient for administrative operations, such as creating topics from `NewTopic` beans. If the producer and AdminClient share common configuration, they may authenticate with the same principal. That easily leads to granting overly broad permissions to the runtime service.

~~~text
Deployment / provisioning pipeline
  -> Admin principal
  -> Create/alter topics, partitions, configs

Application runtime
  -> Producer principal
  -> Write only to approved topics
  -> IdempotentWrite if required
  -> TransactionalId Write if required
~~~

If the app must create topics at startup, evaluate whether runtime auto-creation is truly necessary, whether external topic provisioning is better, whether Admin credentials can be separated, and whether CREATE/ALTER permissions can be restricted to a specific prefix.

Do not grant `CLUSTER / ALL` just to make KafkaAdmin work when only creating a few topics. Identify the exact operations/resources required by the Admin API for your Kafka version.

## 22. Secret Rotation and Principal Lifecycle

When credentials are rotated:

1. Provision/update credentials in the identity provider/broker per procedure.
2. Verify principal mapping remains accurate.
3. Update the secret store and applications via a rolling strategy.
4. Confirm new producers authenticate properly.
5. Confirm the new principal's ACLs match the approved scope.
6. Monitor producer sends and authorization failures.
7. Revoke old credentials after old instances have stopped.

If rotation also changes username/principal, the old principal's ACLs do not automatically transfer to the new principal. The producer may authenticate successfully with the new principal yet fail with `TopicAuthorizationException` because ACLs are not yet in place.

Do not log JAAS configs, passwords, OAuth bearer tokens, or private keys while investigating. Use the principal name and exception category as safer metadata.

## 23. ACL Drift Across Environments

A service running in dev might publish normally while production denies it due to differing ACLs. Do not infer from config code that cluster permissions are identical.

Manage policies as infrastructure-as-code or via an audited change process:
- Principal mapping per environment.
- Topic/transactional ID resource patterns.
- Allowed operations and deny rules.
- Authorizer/superuser config.
- ACL verification output.
- Change owner and rollback plan.

Do not necessarily use the same principal in dev and production. Separating identities reduces the risk of lower-environment credentials accessing production data.

## 24. Testing Producer ACLs in an Integration Environment

A realistic test should run against a broker with authentication and ACLs enabled, not just a default open-access test broker.

1. Create test principal `User:orders-producer-test`.
2. Grant `WRITE` on `orders.events.test`.
3. Grant `IDEMPOTENT_WRITE` if the producer enables idempotence.
4. Start the Spring Boot producer with the matching SASL principal.
5. Send a record to the allowed topic and verify the send result.
6. Attempt sending to unauthorized `payments.events.test`; confirm authorization failure.
7. If testing transactions, grant the transactional ID prefix and verify `initTransactions`/send/commit succeed.
8. Revoke the transactional ID ACL and verify the producer receives the expected authorization error.
9. Revoke topic WRITE and verify the producer can no longer publish.
10. Clean up test topics/principals/ACLs per procedure.

Do not use production credentials or topics to intentionally trigger denials in tests. Tests should confirm **least privilege**: the producer can write where permitted and is denied where forbidden. A test verifying only sends to an allowed topic cannot detect overpermission.

## 25. Observability for Producer Authorization

Metrics/logs should distinguish authentication, authorization, serialization, network, and broker availability.

| Signal | Meaning |
|---|---|
| `TopicAuthorizationException` count | Principal denied writing to topic. |
| `ClusterAuthorizationException` count | Cluster-level operation denied. |
| `TransactionalIdAuthorizationException` count | Transactional ID ACL mismatch. |
| `AuthenticationException` count | SASL/TLS/OAuth authentication failure. |
| Producer send error rate | All send errors, requiring root-cause breakdown. |
| Producer request latency | Slow broker/network/send path. |
| Record send success rate | Successful send operations per instrumentation. |
| Transaction abort/fencing | Transaction lifecycle issues. |
| DLT/retry send failures | Possible missing publish permissions on secondary destinations. |

Do not place full exception messages or arbitrary principals/tenants into metric labels if it causes high cardinality. Record principal/resource in structured logs with appropriate access controls.

Example observing a KafkaTemplate send:

~~~java
kafkaTemplate.send("orders.events", orderId, event)
        .whenComplete((result, exception) -> {
            if (exception != null) {
                log.error(
                        "Kafka publish failed: topic={}, errorType={}",
                        "orders.events",
                        exception.getClass().getSimpleName());
            }
            else {
                log.debug(
                        "Kafka publish acknowledged: topic={}, partition={}, offset={}",
                        result.getRecordMetadata().topic(),
                        result.getRecordMetadata().partition(),
                        result.getRecordMetadata().offset());
            }
        });
~~~

This example uses the `CompletableFuture` API in modern Spring Kafka versions; older versions return `ListenableFuture`. Do not log payloads or keys if keys contain PII. This callback measures the send operation; with transactional producers, a completed send future does not guarantee the transaction has committed.

## 26. Producer ACL Errors and Retry Policy

Authorization failures are usually policy errors, not transient network glitches. If a producer retries continuously, log volume grows, buffers may hold records, source listeners may block waiting for transactional sends, and retry/DLT forwarding may keep failing.

Do not configure infinite retries to wait for ACLs. When an authorization exception is detected:
1. Record the principal, resource, and denied operation.
2. Stop futile retries or apply appropriate backoff.
3. Alert the Kafka ACL owner.
4. Grant proper permissions via the change process.
5. Check whether the producer/client continues working or requires recreation.
6. Verify send results and transaction outcomes after the ACL update.

For DLTs, if the producer lacks permission to write to the DLT, the original failed record cannot be safely recovered. Do not allow source offsets to advance as if recovery succeeded if the DLT send is unconfirmed per policy.

## 27. Runbook: `TopicAuthorizationException` When Publishing

1. Record the exception class, destination topic, application instance, and timestamp.
2. Verify the actual principal received by the broker from SASL/TLS.
3. List ACLs for that exact principal and topic using `kafka-acls.sh --list`.
4. Check the `WRITE` operation, resource pattern type, host, and DENY ACLs.
5. Check whether the producer sent to a different topic due to a typo or routing bug.
6. If using retry/DLT, check those destination topics as well.
7. Grant the exact `WRITE` ACL through the change process.
8. Send a test record and verify broker ack.
9. Monitor error rates and backlog after recovery.

Do not grant `ALL` to the principal just to clear the error. Do not change the SASL password if authentication already succeeded and the exception is authorization.

## 28. Runbook: `ClusterAuthorizationException` with an Idempotent Producer

1. Verify whether the effective producer config enables idempotence.
2. Check Kafka client version and broker authorization requirements.
3. Read broker logs to identify the denied cluster operation.
4. List ACLs on the cluster resource for the principal.
5. Verify `IDEMPOTENT_WRITE` is granted to the exact principal and cluster.
6. Do not randomly alter `acks`/idempotence to dodge the error.
7. Grant the least-privilege ACL per policy.
8. Restart/recreate the producer only if client state requires it.
9. Verify send results and retry/transaction behavior.

Disabling idempotence alters delivery guarantees and duplicate risk; do not treat it as the default fix for an ACL error.

## 29. Runbook: `TransactionalIdAuthorizationException`

1. Extract the actual transactional ID from producer/broker logs.
2. Identify the prefix configured in Spring Kafka and the generated suffix.
3. List ACLs for the `TRANSACTIONAL_ID` resource with the matching pattern.
4. Confirm the principal has `WRITE` on the exact ID/prefix.
5. Check whether the ACL has host restrictions or a matching DENY rule.
6. Distinguish authorization failure from producer fencing.
7. Grant a narrow prefixed `WRITE` transactional ID ACL.
8. Verify producer `initTransactions`, send, and transaction commit.
9. Monitor transaction aborts and consumer offsets.

Do not grant `WRITE` across all transactional IDs when the service only needs one prefix.

## 30. Runbook: Authentication Succeeds but ACLs Do Not Match

1. Check broker logs for the authenticated principal.
2. Compare that principal with `--allow-principal` in ACLs.
3. Check mapping of SASL users, TLS DNs, or OAuth principals.
4. Verify the environment/cluster endpoint is correct.
5. Check ACL resource name and pattern.
6. Check host restrictions and DENY rules.
7. Grant or fix the ACL for the right principal; do not use an admin principal as a workaround.
8. Send a test record and save evidence.

The username in JAAS is not necessarily mapped the way you assume; broker principal builders/mappings can transform the principal string.

## 31. Runbook: Producer Writes Main Topic but DLT/Retry Publish Fails

1. Identify the actual destination retry/DLT topic.
2. Retrieve the principal of the publishing producer template/recoverer.
3. Check `WRITE` ACLs for each destination.
4. If using idempotence, check cluster `IDEMPOTENT_WRITE`.
5. If transactional, check `TRANSACTIONAL_ID / WRITE`.
6. Verify the template serializer supports failed records (which may be raw bytes).
7. Verify send results/acks and recovery callbacks.
8. Do not let source offsets commit if the DLT handoff has not succeeded per policy.
9. After fixing, replay/test a representative record and verify no data loss or duplication.

## 32. Runbook: New Producer Denied After Secret Rotation

1. Identify the username/principal before and after rotation.
2. Check whether the current client reloaded the secret or still uses old credentials.
3. Verify the new principal was created and mapped properly.
4. Check the new principal's ACLs on topics/cluster/transactional IDs.
5. Grant equivalent least-privilege permissions per change approval.
6. Perform a safe rolling restart/recreate of producers if the client does not reload automatically.
7. Verify broker auth logs, send acks, and transaction commits.
8. Revoke the old principal only after all instances have transitioned.

Do not copy broad `ALL` permissions from an old principal to a new principal; re-validate the required scope.

## 33. Runbook: Producer Fenced After Granting ACLs

1. Read the root exception: `ProducerFencedException` differs from `TransactionalIdAuthorizationException`.
2. Inspect actual transactional IDs across instances.
3. Look for overlapping prefixes across pods, services, or environments.
4. Check rollout overlap and unstopped old processes.
5. Ensure each producer instance has an identity matching the design.
6. Fix the prefix/instance ID and corresponding ACL pattern.
7. Initialize new producers after fixing the identity.
8. Check transaction aborts/commits and input offsets.
9. Monitor for fencing after deployment.

Correct ACLs do not eliminate the risk of two producers contending for the same transactional ID.

## 34. Producer ACL Control Matrix

| Control Point | Question to Answer | Evidence |
|---|---|---|
| Identity | Which principal does the broker authenticate the producer as? | Broker auth logs, SASL/TLS/OAuth mapping. |
| Topic scope | Can the producer WRITE only to the right topics? | ACL list by principal/resource. |
| Idempotence | Does the producer enable idempotence and which cluster ACL is needed? | Effective producer config, `IDEMPOTENT_WRITE`. |
| Transactions | Does the actual transactional ID/prefix match the ACL? | Producer logs and `TRANSACTIONAL_ID / WRITE`. |
| Topic provisioning | Does the runtime producer genuinely need CREATE? | `NewTopic`/KafkaAdmin config and provisioning workflow. |
| Retry/DLT | Do all destination topics have appropriate WRITE permissions? | Retry/DLT topology and ACL list. |
| Pattern | Is the literal/prefixed pattern overly broad? | ACL resource pattern and topic inventory. |
| Deny/host | Is a DENY rule or host restriction blocking access? | Effective ACL evaluation and broker logs. |
| Secret | Are credentials securely managed/rotated? | Secret manager, deployment history. |
| Schema Registry | Does the producer have separate registry permissions if needed? | Registry ACL/auth logs. |
| Observability | Are authorization failures clearly classified? | Exception metrics, structured logs. |
| Testing | Do both positive and negative ACL tests pass? | Integration tests with an ACL-enabled broker. |
| Recovery | Do retry/DLT send failures keep offsets safe? | Producer ack, recovery result, committed offset. |
| Audit | Do ACL changes have an owner, approval, and rollback? | Change ticket, ACL snapshot. |

**Conclusion:** Producer ACLs must be granted for specific **principals, resources, and operations**. A standard topic-writing producer needs `WRITE` on the topic; an idempotent producer additionally needs `IDEMPOTENT_WRITE` on the cluster resource; a transactional producer needs `WRITE` on the transactional ID and target topics. Use separate principals per service/environment, narrow literal or prefix patterns, separate runtime producers from admin provisioning, and verify both positive and negative permissions. When encountering authorization exceptions, inspect the broker's actual principal, topic/transactional ID, ACL pattern, DENY rules, and rejected operation before rotating credentials or restarting. Least-privilege ACLs contain the blast radius and keep producers, retry/DLT, and Kafka transactions operating strictly within their approved boundaries.
