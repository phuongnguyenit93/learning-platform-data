# Authorization failure

## 1. What is authorization in Kafka?

Kafka protects resources through identity authentication and access control checks. After a client connects to a broker, Kafka must identify which principal the client is and what operations that principal is allowed to perform on which resources.

**Authentication** verifies who the client is. **Authorization** determines whether an authenticated client is permitted to execute the requested action.

For example, a Spring Boot service may log in to Kafka successfully using SASL/SCRAM yet still be rejected when writing to the `orders.created` topic. In that case, the credentials were accepted, but the service's principal lacks `WRITE` permission on the topic.

Authorization failures commonly occur when:

- A producer sends records to a topic on which the principal lacks write permission.
- A consumer reads a topic on which the principal lacks read permission.
- A consumer joins a group or commits offsets without permission on the group.
- A producer uses Kafka transactions without permission on the transactional ID.
- The application calls AdminClient to create, describe, or alter resources the principal is not allowed to manage.
- An error handler sends records to a dead-letter topic (DLT), but the producer used for publishing to the DLT lacks write permission on the destination topic.

In Spring Kafka, these errors can appear when initializing a producer/consumer, fetching metadata, polling, committing offsets, or sending records. The listener is not necessarily invoked before the error occurs.

## 2. Distinguishing authentication failure from authorization failure

The two error types have different remediation approaches:

| Error type | Question | Examples |
|---|---|---|
| Authentication failure | Can the client prove its identity? | Wrong SASL username/password, mismatched SASL mechanism, invalid TLS certificate |
| Authorization failure | Does the authenticated principal have permission to operate on the resource? | Missing READ permission on topic or READ permission on consumer group |

Some indicators in logs:

- `SaslAuthenticationException`: SASL authentication failed.
- `AuthenticationException`: authentication error at the Kafka client layer.
- `TopicAuthorizationException`: the principal is not authorized to perform the required operation on the topic.
- `GroupAuthorizationException`: the principal lacks required permissions on the consumer group.
- `ClusterAuthorizationException`: an operation requiring cluster-level permission was denied.
- `TransactionalIdAuthorizationException`: the producer lacks required permissions on the transactional ID.
- `AuthorizationException`: general authorization error class in the Kafka client.

Exception names and details depend on the Kafka client version, broker, and API being invoked. Inspect the root exception and broker logs to determine the rejected principal, resource, and operation.

### 2.1. Example: authentication succeeds but topic write fails

Suppose a service logs in with principal `User:orders-service`. The broker accepts SASL authentication. Next, the producer sends a record to `orders.created`, but ACLs do not grant `WRITE` to this principal.

Processing flow:

~~~text
Spring Boot application
       |
       | SASL authentication
       v
Kafka broker
       |
       | Principal = User:orders-service
       | Authentication: SUCCESS
       v
Producer sends to orders.created
       |
       | Authorization check: WRITE
       v
ACL evaluation
       |
       | No matching allow permission
       v
AuthorizationException
       |
       v
Send fails
~~~

Changing the password in this scenario will not solve the problem. You must grant the proper permission to the principal on the corresponding resource after verifying which principal the service is using.

## 3. Principal, resource, operation, and ACL

A Kafka ACL (Access Control List) describes which principal is allowed or denied performing an operation on a resource.

An authorization decision typically depends on:

- **Principal:** client identity, usually formatted as `User:...`.
- **Resource type:** type of resource, such as Topic, Group, Cluster, or TransactionalId.
- **Resource name:** topic name, group ID, transactional ID, or corresponding resource.
- **Operation:** action such as READ, WRITE, CREATE, DESCRIBE, or ALTER.
- **Permission type:** ALLOW or DENY.
- **Host:** client address scope if the ACL restricts hosts.
- **Resource pattern:** ACL applied to a specific resource name, prefix, or supported pattern.

Example of an ACL:

~~~text
Principal: User:orders-service
Resource: Topic:orders.created
Operation: WRITE
Permission: ALLOW
Host: *
~~~

The permission above allows principal `User:orders-service` to write to topic `orders.created` from hosts permitted by the ACL.

### 3.1. Common resource types

| Resource | Used for |
|---|---|
| Topic | Reading, writing, describing, or altering topics |
| Group | Joining consumer groups and managing offsets |
| Cluster | Cluster-level operations, such as idempotent write permission or administrative operations |
| TransactionalId | Producer transactions and fencing by transactional ID |
| DelegationToken | Operations related to delegation tokens |

A principal name is not always the SASL username. With TLS client authentication, the principal may be derived from the certificate's distinguished name (DN). Brokers may apply principal mapping rules to normalize names. Therefore, ACLs must match the principal actually seen by the broker.

### 3.2. Common operations

| Operation | Typical meaning |
|---|---|
| READ | Read topic data or join/read group state depending on resource type |
| WRITE | Write data to a topic or use a transactional ID depending on context |
| CREATE | Create a resource |
| DELETE | Delete a resource |
| ALTER | Modify a resource |
| DESCRIBE | Read resource metadata |
| DESCRIBE_CONFIGS | Read resource configuration |
| ALTER_CONFIGS | Modify resource configuration |
| IDEMPOTENT_WRITE | Use the idempotent producer mechanism at cluster scope |
| CLUSTER_ACTION | Certain internal or administrative cluster-level operations |

Some operations imply others in Kafka's ACL model. For example, READ or WRITE on a topic usually implies the DESCRIBE permission required for the corresponding operation. Do not grant all operations just to resolve a single error; grant least-privilege permissions per actual resource and API.

## 4. Required permissions for producers

A standard producer needs write permission on the target topic:

~~~text
Principal: User:orders-service
Resource: Topic:orders.created
Operation: WRITE
Permission: ALLOW
~~~

If the producer needs to describe topic metadata, the corresponding permission is typically implied by WRITE on the topic in the standard Kafka ACL model. If the application performs additional AdminClient operations, check the specific operations required for those APIs.

### 4.1. Idempotent producer

For producers with `enable.idempotence=true`, some Kafka versions/configurations require `IDEMPOTENT_WRITE` permission on the Cluster resource. This is distinct from `WRITE` on the topic.

This is especially important to check when upgrading Kafka clients or explicitly enabling idempotence. Modern Kafka clients may enable idempotence by default, so a service that previously only needed topic write permission may start requiring cluster-level permission in strict ACL environments. Exact behavior depends on broker/client versions and authorizer configuration; verify actual broker errors before granting.

### 4.2. Producer publishing to a DLT

If Spring Kafka uses `DeadLetterPublishingRecoverer` to send failed records to a topic like `orders.created.DLT`, the recoverer's producer needs WRITE permission on the DLT topic. WRITE permission on the source topic does not automatically grant write access to the DLT.

Example flow:

~~~text
Consumer reads orders.created
       |
       v
Listener processing fails
       |
       v
Error handler retries
       |
       v
Recovery publishes to orders.created.DLT
       |
       v
Kafka checks WRITE on orders.created.DLT
~~~

If DLT publishing fails due to authorization, the original error and the DLT send error must be distinguished in logs. Check the principal used by KafkaTemplate/recoverer, the actual DLT topic, and that topic's ACLs.

## 5. Required permissions for consumers

A consumer needs READ permission on the topic and READ permission on the consumer group to join the group and manage offsets.

Example:

~~~text
Principal: User:orders-fulfillment
Resource: Topic:orders.created
Operation: READ
Permission: ALLOW

Principal: User:orders-fulfillment
Resource: Group:order-fulfillment
Operation: READ
Permission: ALLOW
~~~

These two permissions protect two different resource types:

- READ on the topic allows the consumer to read records.
- READ on the group allows the consumer to perform required consumer group operations, including joining the group and committing offsets in the corresponding flow.

Having topic read permission while lacking group permission can prevent the consumer from starting group membership or committing offsets as expected. Conversely, having group permission without READ on the topic still prevents reading data.

### 5.1. Consumers reading multiple topics

If a listener subscribes to multiple topics, the principal needs appropriate permissions on every topic it reads. With pattern subscriptions, an appropriate ACL resource pattern can be used, but ensure the prefix does not cover beyond the necessary scope.

For example, if a service reads:

- `orders.created`
- `orders.updated`
- `orders.cancelled`

then READ permission must apply to all three topics or to a dedicated prefix such as `orders.`, if security policy permits.

### 5.2. Retry topics and DLT consumers

If the application uses retry topics or DLT topics, consumers reading these topics also need READ on the corresponding resources. Do not grant permissions only on the source topic while overlooking topics created by retry/DLT mechanisms.

## 6. Permissions for transactional producers

Kafka transactions use a transactional ID to identify producer transactions. The producer needs appropriate permission on the transactional ID, in addition to write permissions on output topics.

Example permission:

~~~text
Principal: User:orders-transactional-producer
Resource: TransactionalId:orders-tx-
Operation: WRITE
Permission: ALLOW
Pattern: PREFIXED
~~~

The prefix name must match the transactional ID prefix used by Spring Kafka. Spring Kafka can generate distinct transactional IDs for producer instances based on the prefix and internal suffixes. If an ACL only grants an exact literal name while producers use suffixed IDs, transactions can be rejected.

In Spring Boot, the transaction ID prefix can be configured as follows:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-tx-
~~~

Transactional producers also need write permission on output topics. When using consume-transform-produce, the consumer also needs READ on input topics and READ on the group to handle offsets. When encountering `TransactionalIdAuthorizationException`, check the actual transactional ID in broker logs rather than guessing from bean or listener IDs.

## 7. Security configuration in Spring Boot

Spring Boot passes common security properties to auto-configured Kafka clients. The example below illustrates SASL/SCRAM over TLS:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.example.net:9093,kafka-2.example.net:9093
    properties:
      "[security.protocol]": SASL_SSL
      "[sasl.mechanism]": SCRAM-SHA-512
      "[sasl.jaas.config]": 'org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-service" password="<inject-from-secret>";'
~~~

In real environments, passwords must be retrieved from a secret manager or the deployment platform's secret injection. Never commit passwords, tokens, or private keys to source control, shared config files, or logs.

If using a custom TLS truststore, configure additionally:

~~~yaml
spring:
  kafka:
    properties:
      "[ssl.truststore.location]": /run/secrets/kafka/truststore.p12
      "[ssl.truststore.type]": PKCS12
      "[ssl.truststore.password]": "<inject-from-secret>"
~~~

With mutual TLS, the client also needs an appropriate keystore and private key. When using SASL_SSL, TLS protects the connection while SASL authenticates the principal; the two layers serve different roles.

### 7.1. Separate producer and consumer configurations

If producer and consumer share the same principal, common security properties can be used. If each component needs its own principal, configure separate producer/consumer properties or create distinct factories with corresponding authentication settings.

Example configuring consumer properties:

~~~yaml
spring:
  kafka:
    consumer:
      properties:
        "[security.protocol]": SASL_SSL
        "[sasl.mechanism]": SCRAM-SHA-512
        "[sasl.jaas.config]": 'org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-reader" password="<inject-from-secret>";'
~~~

The producer can use a different principal with WRITE permission, while the consumer uses a read-only principal. This separation supports least privilege, though you must check which factory/principal is used by AdminClient, KafkaTemplate, retry publishers, and DLT recoverers.

### 7.2. Security properties do not grant ACLs

Declaring `security.protocol`, `sasl.mechanism`, username, and password only configures how the client connects and authenticates. These properties do not automatically create ACLs on the broker.

Access permissions are managed by the broker authorizer. To grant permissions, ACLs must be updated via the appropriate Kafka administration process; editing application.yml cannot grant permissions on the cluster.

## 8. Enabling and managing ACLs on the broker

Kafka requires an appropriate authorizer to enforce ACLs. For Kafka running KRaft, configuration commonly uses StandardAuthorizer:

~~~properties
authorizer.class.name=org.apache.kafka.metadata.authorizer.StandardAuthorizer
super.users=User:admin
allow.everyone.if.no.acl.found=false
~~~

For clusters using ZooKeeper or older versions, authorizer classes and ACL management may differ. Follow documentation for the current Kafka version and deployment mode.

`super.users` is a list of principals with special administrative privileges. Only place controlled administrative principals in this list. Do not add application services to super.users to bypass authorization errors.

`allow.everyone.if.no.acl.found` changes behavior when a resource has no ACLs yet. In environments requiring access control, do not enable universal access just to make errors disappear. Grant explicit ACLs for the required principals and resources.

## 9. Checking and granting ACLs with kafka-acls

Kafka provides the `kafka-acls.sh` tool to list, add, and remove ACLs. Use an administrative account with sufficient privileges and a secure command config file.

For example, an `admin.properties` file holding the administrative principal's secure connection settings. Do not put secrets on the command line or share this file.

### 9.1. Listing current ACLs

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin.properties \
  --list \
  --topic orders.created
~~~

To inspect a group:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin.properties \
  --list \
  --group order-fulfillment
~~~

Inspect the output to confirm whether principal, operation, resource pattern, and host match the denied request.

### 9.2. Granting topic write permission to a producer

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-service \
  --operation Write \
  --topic orders.created
~~~

If the producer requires idempotent writes and the broker/client version requires cluster-level permission:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-service \
  --operation IdempotentWrite \
  --cluster
~~~

Only grant cluster-level permissions when confirmed by errors and required by the deployed version. This permission is broader than writing to a single topic, so it should be approved under least-privilege policy.

### 9.3. Granting topic and group read permissions

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-fulfillment \
  --operation Read \
  --topic orders.created
~~~

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-fulfillment \
  --operation Read \
  --group order-fulfillment
~~~

### 9.4. Granting permissions for a DLT

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-service \
  --operation Write \
  --topic orders.created.DLT
~~~

If a consumer needs to read the DLT for investigation or replay, grant READ on the DLT and READ on the corresponding group to that consumer principal.

### 9.5. Granting transactional ID permission by prefix

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal User:orders-transactional-producer \
  --operation Write \
  --transactional-id orders-tx- \
  --resource-pattern-type prefixed
~~~

Option syntax can vary slightly across Kafka CLI versions. Always check `kafka-acls.sh --help` and the tool version shipped with your cluster before running administrative commands.

### 9.6. Verifying after granting

After modifying ACLs:

1. List the resource's ACLs again.
2. Confirm the principal matches what the broker sees.
3. Verify the resource name and pattern type.
4. Verify the granted operations.
5. Retry a small operation using the service's actual credentials.
6. Confirm the producer sends successfully or the consumer joins the group, reads, and commits offsets.
7. Monitor broker logs to ensure no authorization denials remain for that resource.

Do not test using an administrative principal in place of the application principal. Testing with the service's real credentials is what verifies the service's permissions.

## 10. Common authorization failures in Spring Kafka

| Exception or log | Typically involved resource/operation | How to check |
|---|---|---|
| `TopicAuthorizationException` | Topic READ, WRITE, DESCRIBE, or other topic operations | Confirm topic and principal; inspect ACL for the right operation |
| `GroupAuthorizationException` | Group READ or group operations | Check actual group ID and ACL on Group |
| `ClusterAuthorizationException` | Cluster-level operations such as idempotent write or Admin API | Inspect denied operation and Cluster permissions |
| `TransactionalIdAuthorizationException` | TransactionalId WRITE | Inspect actual transactional ID and literal/prefixed ACLs |
| `AuthorizationException` | Disallowed operation, possibly not described by a specific subclass | Read broker logs for principal, resource, and operation |
| `SaslAuthenticationException` | Authentication, not ACL authorization | Check SASL mechanism, credentials, and JAAS config |

Errors can surface in producer futures, consumer polls, offset commits, or AdminClient calls. Thus, locate the exact component issuing the request. One application may use multiple principals or multiple factories.

## 11. Diagnosing by Spring Kafka flow

### 11.1. Producer fails to send records

Symptoms:

- `KafkaTemplate.send()` completes its future with an exception.
- Logs show `TopicAuthorizationException`.
- The broker reports the principal lacks WRITE permission on the topic.

How to investigate:

1. Identify the actual topic passed to `send()`, including dynamically chosen topics.
2. Identify the producer factory/KafkaTemplate in use.
3. Check the principal after authentication and mapping.
4. Inspect WRITE ACLs on the topic.
5. If idempotence is enabled, also check for missing IDEMPOTENT_WRITE on Cluster depending on Kafka version.
6. Retry sending with the real credentials after updating ACLs.

Example callback to record errors:

~~~java
kafkaTemplate.send("orders.created", orderId, event)
    .whenComplete((result, exception) -> {
        if (exception != null) {
            log.error(
                "Kafka publish failed, topic={}, orderId={}",
                "orders.created",
                orderId,
                exception
            );
            return;
        }

        log.info(
            "Kafka publish acknowledged, topic={}, partition={}, offset={}",
            result.getRecordMetadata().topic(),
            result.getRecordMetadata().partition(),
            result.getRecordMetadata().offset()
        );
    });
~~~

Callbacks provide visibility into asynchronous errors. Never log passwords, JAAS strings, or secrets when logging failures.

### 11.2. Consumer fails to read topic

Symptoms:

- The consumer cannot fetch records.
- Logs show `TopicAuthorizationException`.
- The consumer may fail immediately when fetching metadata or calling poll.

Check:

1. Is the topic subscription name exact?
2. Does the consumer principal have READ on every topic?
3. If subscribing by pattern, do ACLs cover matched topics?
4. Is the consumer using the right credentials and ConsumerFactory?
5. Do broker logs record the specific denied operation/topic?

If a consumer reads multiple topics, granting permission on only one topic can still leave the listener failing when touching remaining topics.

### 11.3. Consumer fails to join group or commit offsets

Symptoms:

- Logs show `GroupAuthorizationException`.
- The consumer is unstable in the group or offset commits fail.
- The consumer can read topic metadata, but group operations are denied.

Check READ on the actual group ID. The group ID may be configured in `spring.kafka.consumer.group-id`, on `@KafkaListener(groupId=...)`, or in custom container properties. ACLs must match the listener's effective value.

### 11.4. Transaction or DLT publish fails

For transactional producers, check:

- The transactional ID prefix configured in Spring Boot.
- The actual transactional ID used by the producer instance.
- WRITE on the transactional ID.
- WRITE on output topics.
- IDEMPOTENT_WRITE on Cluster if required by version/config.

For DLTs, inspect the producer used by the recoverer, the destination topic, and WRITE permissions. If the error handler uses a separate KafkaTemplate, its principal may differ from the business producer.

## 12. Authorization failures inside error handlers

Authorization failures are usually permission or identity configuration errors, not business record processing errors solvable by ordinary retries.

For instance, a listener fails and the error handler tries to send the record to a DLT. If the DLT producer is denied, repeatedly retrying DLT publishing will not create WRITE permission. Likewise, a consumer lacking READ on a group cannot fix itself by calling poll repeatedly.

Appropriate handling:

- Record the root exception and the denied resource.
- Do not mask the error by catching the exception and treating the record as processed.
- Fix ACLs or principal mapping via security procedures.
- Restore listeners/producers according to the running Spring Kafka version's lifecycle and retry policy.
- Verify records were not lost or erroneously committed during recovery.

Do not configure long-term retries for authorization errors when permissions remain unfixed. Non-retryable errors must be surfaced and routed to appropriate operational workflows.

## 13. Principal mapping and deployment environments

A common cause is granting ACLs to the principal developers think the app uses, while the broker receives a different principal.

For example, SASL username `orders-service` may map to principal `User:orders-service`. With TLS client authentication, the principal may be constructed from the certificate's subject DN, such as `User:CN=orders-service,OU=Apps,O=Example`.

Factors to verify:

- Actual SASL mechanism and username.
- TLS client certificate subject if using mTLS.
- Principal builder or mapping rules on the broker.
- Secret version currently mounted by the pod.
- Whether custom producer/consumer factories override security properties.
- Whether old and new pods are using different credentials.

When rotating secrets, ensure new credentials receive corresponding ACLs before rolling out the service. If the username changes, the principal may also change and old ACLs will no longer match.

## 14. Authorization and AdminClient

Spring Kafka or the application may use AdminClient to check topics, create topics, describe metadata, or manage configurations. These APIs require different permissions than reading/writing records.

Examples:

| Task | Resource/operation to check |
|---|---|
| Describe topic | DESCRIBE on Topic |
| Create topic | CREATE at scope matching policy |
| Delete topic | DELETE on Topic |
| Alter partitions/config | ALTER or ALTER_CONFIGS accordingly |
| Read topic config | DESCRIBE_CONFIGS |
| List/inspect groups | Group/cluster operations matching API and version |

Do not grant broad administrative permissions to a runtime service merely because startup code runs a topic check. Separate topic creation into a provisioning job or administrative principal, leaving the runtime service with only the READ/WRITE permissions it needs.

If startup fails when AdminClient checks or creates topics, inspect the exact API in broker logs. This error can occur before listeners begin processing records.

## 15. Least privilege and safe ACL management

A sound ACL policy grants only the exact principal, resource, and operations needed:

- Separate producer and consumer principals when workloads need different permissions.
- Grant WRITE only on topics the producer actually writes to.
- Grant READ only on topics the consumer actually reads from.
- Grant READ only on the group ID the consumer uses.
- Grant DLT/retry topic permissions specifically to principals that publish or consume them.
- Scope transactional IDs by service-specific prefixes.
- Avoid using super users for application runtimes.
- Avoid broad wildcard resources when only a small set of topics is needed.
- Document owner, reason, expiration, and revocation procedure for ACLs.

DENY ACLs can affect outcomes even when ALLOW ACLs exist, depending on authorizer mechanics and configuration. When a permission appears granted yet requests are still denied, inspect deny rules, host constraints, resource patterns, and principal mappings.

Never resolve errors by enabling access for everyone, disabling the authorizer, or granting full cluster permissions. That hides the root cause and expands access far beyond the service's needs.

## 16. Authorization failure handling procedure

When encountering an authorization error in production, follow this sequence:

1. **Identify the requesting component:** producer, consumer, listener container, DLT recoverer, or AdminClient.
2. **Read the root exception:** capture exception class, operation, and resource if present.
3. **Cross-check broker logs:** confirm the principal, resource type/name, operation, and host seen by the broker.
4. **Verify authentication:** ensure the client logs in using the expected credentials.
5. **Inspect ACLs:** list ACLs for the principal and resource; check allow, deny, pattern, and host.
6. **Determine least-privilege permissions:** topic READ/WRITE, group READ, transactional ID WRITE, cluster IDEMPOTENT_WRITE, or Admin API permissions depending on the operation.
7. **Update ACLs via admin workflow:** use an administrative principal and record the change.
8. **Retry with service credentials:** confirm the specific operation succeeds.
9. **Recover container/producer:** if the client stopped or entered an error state, perform restart/recovery per application lifecycle and library version.
10. **Monitor after recovery:** check consumer lag, publish errors, DLT backlog, commit failures, and replayed records.
11. **Document root cause:** update runbooks and the service's permission matrix.

Do not rely solely on generic "Not authorized" messages. Broker logs are usually the most authoritative source for pinpointing the exact principal and operation.

## 17. End-to-end example: Order Service

Suppose there are two components:

- Order API producer using principal `User:orders-api`.
- Fulfillment consumer using principal `User:orders-fulfillment`.

The producer writes to `orders.created`; the consumer reads that topic with group `order-fulfillment`. On error, the service's DLT producer sends to `orders.created.DLT`.

The permission matrix might look like:

| Principal | Resource | Operation |
|---|---|---|
| `User:orders-api` | Topic `orders.created` | WRITE |
| `User:orders-api` | Cluster | IDEMPOTENT_WRITE if required by version/config |
| `User:orders-fulfillment` | Topic `orders.created` | READ |
| `User:orders-fulfillment` | Group `order-fulfillment` | READ |
| `User:orders-fulfillment` | Topic `orders.created.DLT` | WRITE if this principal sends to DLT |
| `User:orders-fulfillment` | Corresponding retry topics | READ/WRITE per retry topic role |

If Order API sends a record and receives `TopicAuthorizationException`, check WRITE permission for `User:orders-api` on `orders.created`. If the consumer cannot join the group and receives `GroupAuthorizationException`, check READ on group `order-fulfillment`. If DLT publishing fails, check WRITE permission on `orders.created.DLT` for the principal actually used by KafkaTemplate/recoverer.

Separating principals clarifies which service needs which permissions. If one service is compromised or credentials leak, that principal's blast radius remains confined to its role.

## 18. Operational checklist

- [ ] Distinguished authentication failure from authorization failure.
- [ ] Identified the principal actually seen by the broker.
- [ ] Recorded the denied resource type, resource name, and operation.
- [ ] Producer has WRITE on target topics.
- [ ] Consumer has READ on every required topic.
- [ ] Consumer has READ on the effective group ID.
- [ ] Idempotent producer has IDEMPOTENT_WRITE if required by version/config.
- [ ] Transactional producer has WRITE on transactional ID and output topics.
- [ ] Retry/DLT producer has WRITE on target topics; consumer has READ on topics it consumes.
- [ ] AdminClient holds only necessary administrative permissions.
- [ ] ACLs are not blocked by deny rules, host constraints, or resource patterns.
- [ ] Secrets and principal mappings match deployment configuration.
- [ ] Retried using the service's real credentials.
- [ ] Consumer lag, commits, publishes, and DLT backlog are stable after recovery.

Authorization failures in Kafka are resolved properly by identifying the exact principal, resource, and denied operation, then granting least-privilege permissions. In Spring Kafka, inspect producers, consumer groups, listeners, transactional producers, AdminClient, and DLT publishers separately because each component can perform different operations and use different principals.


