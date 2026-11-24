# Consumer ACLs in Spring Kafka

In Kafka, a consumer must prove **which principal it is** and be authorized by the broker to perform **specific operations**. These are two distinct things: SASL or TLS authenticates identity; Kafka ACLs determine whether that principal is allowed to read topics, join consumer groups, and commit offsets.

For a typical Spring Kafka service using `@KafkaListener`, the minimum permissions to consider usually apply to two resource types:

- **TOPIC**: the principal needs `READ` permission on the topics the consumer reads.
- **GROUP**: the principal needs `READ` permission on the consumer group the application joins.

If you grant topic read permission but forget group permission, the consumer can authenticate successfully and see topic metadata, yet cannot join the group or commit offsets as expected. If you grant only group permission without topic permission, the consumer cannot read data from the topic.

This lesson explains how to design ACLs with least privilege, determine the right principal and group ID in Spring Boot, configure SASL/TLS, grant and revoke ACLs with `kafka-acls.sh`, handle topic subscriptions, troubleshoot authorization errors, and build integration tests.

## 1. Authentication and Authorization Are Two Separate Steps

A consumer connection goes through two questions:

1. **Authentication:** with what identity is the client connecting to Kafka?
2. **Authorization:** does that identity have permission to execute the request on the target resource?

```text
Spring Kafka application
       |
       v
TLS / SASL authentication
       |
       v
Kafka identifies principal
       |
       v
Kafka authorizer checks ACL
       |
       +-- ALLOW --> request is executed
       |
       +-- DENY  --> authorization exception
```

Example:

- Consumer uses SASL/SCRAM with username `billing-consumer`.
- Broker identifies principal as `User:billing-consumer`.
- ACL allows the principal to read topic `orders.created`.
- ACL allows the principal to use group `billing-service`.
- Consumer can read and commit offsets per granted permissions.

A successful SASL login **does not automatically grant topic read permission**. Conversely, an ACL for `User:billing-consumer` does nothing if the client cannot authenticate as that principal.

### 1.1. Concepts to distinguish

| Concept | Example | Meaning |
|---|---|---|
| Username / certificate identity | `billing-consumer` | Credentials used for authentication |
| Kafka principal | `User:billing-consumer` | Identity used by the broker in ACLs |
| Client ID | `billing-consumer-1` | Client identifier for logs/metrics/quotas |
| Consumer group ID | `billing-service` | Group name used for coordination and offset tracking |
| Topic | `orders.created` | Resource containing records |
| ACL | Allow READ for principal on resource | Determines access permissions |

**Client ID is neither consumer group ID nor principal.** Setting `client.id=billing-service` does not grant permissions on group `billing-service`.

### 1.2. Principal may differ from username

With SASL/SCRAM, the principal is typically based on the authenticated username, e.g., `User:billing-consumer`. With TLS client authentication, the principal may be derived from the certificate's distinguished name, e.g., `User:CN=billing-consumer,OU=Services,O=Example`.

Kerberos/GSSAPI may produce principals in the form `User:service/host@REALM`, depending on principal builder and mapping rules.

When granting ACLs, use the **principal the broker actually sees**, not a guess from pod names, Spring beans, or application names. Verify this via broker authentication/authorizer logs and principal mapping configuration.

## 2. Why Does a Consumer Need ACLs on Both Topic and Group?

A consumer group has two separate authorization scopes:

- Reading records from topics.
- Participating/operating in a group, including coordination and managing committed offsets.

Example listener:

```java
@KafkaListener(
    id = "billing-listener",
    topics = "orders.created",
    groupId = "billing-service"
)
public void consume(OrderCreated event) {
    billingService.process(event);
}
```

The Kafka broker needs to check permissions matching:

```text
Principal: User:billing-consumer

TOPIC resource:
  orders.created
  operation: READ

GROUP resource:
  billing-service
  operation: READ
```

In the Kafka ACL model, `READ` on a topic is the primary permission to fetch records. With StandardAuthorizer, `READ` also implies corresponding `DESCRIBE` per operation implication rules. Some standalone metadata/admin operations may require explicit `DESCRIBE` permission.

`READ` on a group allows the consumer to use the group resource for coordination and related offset operations. Do not confuse `READ` on a topic with `READ` on a group: these are two ACLs on two separate resources.

### 2.1. Common minimum permission matrix

| Resource type | Resource name | Operation | Purpose |
|---|---|---|---|
| TOPIC | `orders.created` | READ | Fetch records from topic |
| GROUP | `billing-service` | READ | Join/coordinate consumer group and offset operations |
| TOPIC | `orders.updated` | READ | Only if the listener actually reads this topic |
| GROUP | `billing-replay` | READ | Only if the application uses this group ID |

For group-subscribed consumers, this is a good starting point for least privilege. Additional permissions should only be granted when an API or workflow actually needs them.

### 2.2. Missing topic ACL

If the principal has group permission but lacks topic read permission, the consumer may hit `TopicAuthorizationException` when fetch/metadata access requires authorization. Logs may name the specific denied topic.

Do not grant `READ` across all topics just to fix an error on `orders.created`.

### 2.3. Missing group ACL

If the principal can read the topic but is not allowed to use the group, the consumer may hit `GroupAuthorizationException` during group join, heartbeat/coordination, or offset operations depending on the request.

Symptoms can include the listener receiving no records, group join failing, or offset commits being rejected. Read the exception and broker authorizer logs to see which group resource was denied.

### 2.4. Consumers not using a group

If a consumer uses `assign()` to manually assign partitions instead of `subscribe()`, it does not participate in group coordination in the same way. However, if it still commits offsets under a group ID, offset operations remain tied to the group resource and authorization must be evaluated accordingly.

In Spring Kafka applications using `@KafkaListener` with `groupId` and standard subscription, grant group permissions as shown in the matrix above.

## 3. Kafka ACL Model: Resource, Operation, Principal, and Host

An ACL entry is defined by several components:

- **Principal:** identity being allowed or denied.
- **Host:** client address to which the ACL applies, commonly `*` if not host-restricted.
- **Operation:** READ, WRITE, DESCRIBE, CREATE, DELETE, ALTER...
- **Permission type:** ALLOW or DENY.
- **Resource type/name:** TOPIC, GROUP, CLUSTER, TRANSACTIONAL_ID...
- **Pattern type:** literal, prefixed, or wildcard per ACL model.

Example:

```text
ALLOW User:billing-consumer
  HOST *
  READ
  TOPIC orders.created
  LITERAL
```

This entry allows the principal to read the specific topic from any host matching the host wildcard.

### 3.1. Literal resource pattern

Literal is a good choice when the application only needs a fixed set of topics/groups.

Example:

```text
TOPIC orders.created (literal)
GROUP billing-service (literal)
```

If a service only consumes `orders.created` and uses group `billing-service`, literal ACLs bound the scope clearly.

### 3.2. Prefixed resource pattern

An ACL with pattern `PREFIXED` applies to resource names starting with the specified prefix.

Example:

```text
TOPIC orders. (prefixed)
GROUP billing- (prefixed)
```

This can be useful when a service consumes multiple topics following a naming convention. However, an overly broad prefix such as `orders` could grant read access to topics outside the workload.

For group prefixes, consider whether the application truly needs multiple group IDs or just one fixed group ID. If only one group is needed, literal is easier to audit.

### 3.3. Wildcard resource

Wildcard resource patterns can apply very broadly. Using `--topic '*'` or resource wildcards for an application principal can inadvertently grant read access to data outside its business scope.

Do not use wildcards as a quick fix in production without a data-scope review and security approval.

### 3.4. Host restriction

ACLs can restrict client hosts. In Kubernetes environments, pod IPs can change across rollouts/autoscaling; binding hosts to static pod IPs can suddenly strip consumer permissions after deployment.

If using host `*`, compensate with per-service principals, TLS/SASL, network controls, and narrow resource ACLs. A host wildcard does not mean every user is allowed; the principal must still match.

## 4. Least Privilege for Consumers

A consumer should only be granted permissions necessary for its specific function.

Example:

```text
billing-service:
  principal: User:billing-consumer
  topics:
    - orders.created
    - orders.updated
  groups:
    - billing-service
  operations:
    - READ on those topics
    - READ on that group
```

A consumer does not need the following permissions merely to read topics in a group:

- `WRITE` on source topics.
- `CREATE` or `DELETE` topics.
- `ALTER` topic configuration.
- `CLUSTER_ACTION`.
- `ALTER_CONFIGS` or `DESCRIBE_CONFIGS` for cluster/topic.
- `WRITE` on group.
- `READ` on all groups or all topics.

A consumer may need other permissions if it also publishes output, creates topics, invokes AdminClient, or uses Kafka transactions. In those cases, separate the roles or grant additional permissions on the exact resources.

### 4.1. Separating principals by service

Avoid using one shared principal across all applications:

```text
User:shared-application
  -> orders-service
  -> billing-service
  -> analytics-service
```

If a shared principal has permission to read all topics, one compromised service can access other services' data. Separate principals shrink the blast radius and clarify audit trails.

Example:

```text
User:orders-consumer
User:billing-consumer
User:analytics-consumer
```

Each principal has its own topic/group ACLs.

### 4.2. Read-only consumer

A read-only consumer does not need topic write permissions. If the same service contains both a consumer and a producer, consider separate principals for producer and consumer when the environment requires strict privilege separation.

If sharing a principal, ACLs must include both producer and consumer permissions, increasing the privilege scope of the consumer process.

### 4.3. Do not grant admin permissions to runtime consumers

A runtime service should not run with an admin principal just to avoid ACL errors. Admin credentials typically carry broad privileges, increasing impact if a secret leaks or an application is exploited.

Use a dedicated admin principal for provisioning/ACL changes and a least-privilege principal for runtime.

## 5. Granting ACLs with `kafka-acls.sh`

The `kafka-acls.sh` tool administers ACLs via the Kafka Admin API. The examples below assume the broker has an authorizer enabled and the caller has ACL management permissions.

Create a separate administrative connection config file, e.g., `admin.properties`, with bootstrap servers and appropriate authentication. Do not put real passwords in source control or shell commands saved in history.

### 5.1. Granting READ on a topic

```bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal 'User:billing-consumer' \
  --operation Read \
  --topic orders.created
```

This ACL grants READ to the principal on the literal topic `orders.created`. With StandardAuthorizer, READ implies DESCRIBE per operation implication.

If internal policy requires an explicit DESCRIBE ACL or a separate client/admin operation needs to describe topics, it can be granted separately:

```bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal 'User:billing-consumer' \
  --operation Describe \
  --topic orders.created
```

Do not add DESCRIBE_CONFIGS just because a consumer needs to read records; that permission reads resource configurations and serves a different purpose.

### 5.2. Granting READ on a consumer group

```bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal 'User:billing-consumer' \
  --operation Read \
  --group billing-service
```

The `GROUP` resource here must match the group ID the consumer actually uses. For the listener example:

```java
@KafkaListener(
    topics = "orders.created",
    groupId = "billing-service"
)
public void consume(OrderCreated event) {
    // ...
}
```

the group resource is `billing-service`.

### 5.3. Granting permissions for multiple topics

If the service also reads topic `orders.updated`, grant a separate ACL:

```bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal 'User:billing-consumer' \
  --operation Read \
  --topic orders.updated
```

Do not grant `orders.*` with wildcards if the application only needs two fixed topics.

### 5.4. Listing existing ACLs

```bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --command-config admin.properties \
  --list \
  --topic orders.created
```

List ACLs for a group:

```bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --command-config admin.properties \
  --list \
  --group billing-service
```

You can list all ACLs with `--list`, but in large clusters filter by resource so the output is easy to inspect.

### 5.5. Revoking ACLs

When a service stops using a topic:

```bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --command-config admin.properties \
  --remove \
  --allow-principal 'User:billing-consumer' \
  --operation Read \
  --topic orders.created
```

Revoke the group ACL separately if the group is no longer used:

```bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --command-config admin.properties \
  --remove \
  --allow-principal 'User:billing-consumer' \
  --operation Read \
  --group billing-service
```

The remove operation must match the exact principal, operation, resource pattern, and host of the ACL to delete. Check `--list` output after the change.

## 6. Prefixed ACLs for Topic Subscriptions

A listener may subscribe to multiple topics using a pattern or regex. In that case, understand **which topics are actually subscribed** and whether ACLs cover all of them.

Example listener:

```java
@KafkaListener(
    id = "orders-listener",
    topicPattern = "orders\\.events\\..*",
    groupId = "billing-service"
)
public void consume(String payload) {
    // ...
}
```

If topic names follow the prefix `orders.events.`, a prefixed ACL can be considered:

```bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal 'User:billing-consumer' \
  --operation Read \
  --topic orders.events. \
  --resource-pattern-type prefixed
```

The group still needs a separate ACL:

```bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --command-config admin.properties \
  --add \
  --allow-principal 'User:billing-consumer' \
  --operation Read \
  --group billing-service
```

### 6.1. Overly broad prefixes can expand permissions unexpectedly

For example, prefix `orders.` could cover:

```text
orders.events.created
orders.events.updated
orders.internal.audit
orders.admin.commands
orders.private.customer-data
```

If the service only needs `orders.events.*`, the narrower prefix `orders.events.` is safer. When topic naming conventions are unstable, use literal ACLs for an approved list of topics.

### 6.2. Regex subscriptions do not grant ACLs automatically

`topicPattern` only determines how the client subscribes by pattern. It does not create ACLs and does not make the broker bypass authorization.

When a new topic matching the pattern is created, the consumer principal still needs read permission on that resource. A prefixed ACL lets new topics under that prefix be read without granting per-topic ACLs, provided it is designed intentionally.

### 6.3. Dynamic group IDs

If the group ID varies by environment or instance, a literal group ACL may not match. Do not immediately use a broad group prefix as a quick fix. First determine the actual group ID via config/logs; then decide between literal or prefix.

Normally, replicas of the same logical service should use the **same group ID**, not a group ID containing the pod name, so partitions are shared and load-balanced. If each pod uses its own group ID, each pod may receive the entire stream independently and require separate group ACLs.

## 7. DENY ACLs and Permission Precedence

Kafka ACLs have ALLOW and DENY permission types. When a request matches a DENY ACL, access is rejected per authorizer rules; do not assume a broader ALLOW will override DENY.

Example:

```text
ALLOW User:billing-consumer READ TOPIC orders.
DENY  User:billing-consumer READ TOPIC orders.created
```

If both ACLs match on resource pattern/host/operation, DENY can prevent the consumer from reading `orders.created`.

### 7.1. Check effective ACLs, not just intended ACLs

When a consumer receives an authorization error:

1. List ACLs on the specific topic.
2. List ACLs on the specific group.
3. Check literal/prefixed/wildcard resource patterns.
4. Check the actual principal after authentication/mapping.
5. Check host conditions.
6. Check whether any DENY entries match.
7. Check `super.users` and authorizer policies if applicable.
8. Check broker logs to see which resource/operation was denied.

An existing ALLOW ACL does not prove a request will succeed if a matching DENY exists or principal/host does not match.

### 7.2. Avoid wildcard principals

ACLs for `User:*` or broad principals weaken service isolation. Use dedicated principals and narrow resources. For DENY rules, be especially cautious since a broad entry can disrupt multiple workloads.

## 8. Enabling the Authorizer on Kafka Brokers

ACLs take effect only when brokers use an active authorizer. Configuration depends on Kafka deployment mode and version.

For modern Kafka running KRaft, the standard authorizer is:

```properties
authorizer.class.name=org.apache.kafka.metadata.authorizer.StandardAuthorizer
```

For some ZooKeeper/older deployments, the authorizer may be:

```properties
authorizer.class.name=kafka.security.authorizer.AclAuthorizer
```

This is broker-side configuration, not Spring Boot consumer configuration. Do not copy an authorizer class from one mode/version to another without checking the documentation for your running Kafka version.

### 8.1. Default deny and ACL bootstrap

When the authorizer is enabled, requests requiring authorization are checked. Without a matching ALLOW ACL and absent configured exceptions, the request is denied.

Prepare:

- An administrative principal allowed to create/list/remove ACLs.
- `super.users` if deployment policy requires superuser identities.
- ACLs for runtime services.
- A bootstrap procedure so admins do not lock themselves out.
- An audit trail for ACL changes.

Do not enable the authorizer in production before verifying administrative access paths and ACL bootstrap. Misconfiguration can cause brokers to reject even required administrative operations.

### 8.2. `allow.everyone.if.no.acl.found`

Some authorizers/configurations offer `allow.everyone.if.no.acl.found`. When enabled, resources without ACLs may be handled under a permissive fallback policy.

This is not a substitute for granting proper ACLs. Understand the exact default behavior of your authorizer/version and cluster security policy. In environments requiring least privilege, avoid "allow everyone if no ACL found" unless explicitly approved by a security decision.

### 8.3. KRaft and ZooKeeper differ

Kafka KRaft and ZooKeeper-based clusters differ historically in authorizer/configuration details. KRaft uses the metadata quorum for metadata/ACL storage; older ZooKeeper deployments have their own mechanisms for those versions.

`kafka-acls.sh --bootstrap-server` is the preferred modern management path, though flags, authorizer behavior, and bootstrap requirements still need checking per version/distribution.

## 9. Configuring a Spring Boot Consumer with SASL/SCRAM and TLS

ACLs define permissions, but clients still need to authenticate. Example consumer using SASL_SSL and SCRAM-SHA-512:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.internal:9093,kafka-2.internal:9093
    consumer:
      group-id: billing-service
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.JsonDeserializer
      properties:
        spring.json.trusted.packages: com.example.billing.events
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
      sasl.jaas.config: org.apache.kafka.common.security.scram.ScramLoginModule required username="billing-consumer" password="${KAFKA_CONSUMER_PASSWORD}";
      ssl.endpoint.identification.algorithm: https
~~~

This is an illustrative example. `KAFKA_CONSUMER_PASSWORD` must be injected from a secret manager/environment per deployment policy. Do not commit real passwords to `application.yml`, public Helm values, Docker images, or repositories.

### 9.1. TLS trust

With SASL_SSL, the client authenticates via SASL and secures the connection with TLS. Truststore/CA configuration must allow the client to verify the broker certificate.

If the cluster requires mutual TLS, the client also needs the appropriate keystore/certificate/key. The Kafka principal may be formed from the SASL identity or TLS certificate identity depending on listener/auth config and principal builder.

### 9.2. Distinguishing SASL errors from ACL errors

| Exception / symptom | Typical Error Layer | Investigation Direction |
|---|---|---|
| SaslAuthenticationException | Authentication | Username, password, mechanism, JAAS config |
| SSLHandshakeException | TLS handshake/trust | CA, hostname, certificate, protocol |
| TopicAuthorizationException | Authorization | TOPIC ACL, principal, operation |
| GroupAuthorizationException | Authorization | GROUP ACL, group ID |
| ClusterAuthorizationException | Authorization | Required CLUSTER operation |
| Timeout / disconnect | Connectivity or broker | Network, listener, TLS, broker health |

A successful SASL login with a missing topic ACL yields a different error class than a wrong password. Do not change credentials when broker logs confirm the principal is valid and an operation was denied.

### 9.3. Separating admin and runtime credentials

`admin.properties` used for `kafka-acls.sh` should belong to an administrative principal. Spring Boot consumers use a dedicated runtime principal.

Do not configure a runtime consumer with admin credentials just to test whether a listener runs. Testing with a superuser hides missing ACLs.

## 10. Example SASL_SSL Configuration in Properties

If using Java properties instead of YAML:

~~~properties
spring.kafka.bootstrap-servers=kafka-1.internal:9093,kafka-2.internal:9093
spring.kafka.consumer.group-id=billing-service
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.properties.security.protocol=SASL_SSL
spring.kafka.properties.sasl.mechanism=SCRAM-SHA-512
spring.kafka.properties.sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="billing-consumer" password="${KAFKA_CONSUMER_PASSWORD}";
spring.kafka.properties.ssl.endpoint.identification.algorithm=https
~~~

Spring Boot binds Kafka properties to consumer/producer/admin clients per configuration. If the application builds a custom `ConsumerFactory`, verify it receives Boot properties or maps the corresponding Kafka client properties.

### 10.1. Do not put passwords on the command line

Some shell/process inspection tools expose command-line arguments. Avoid passing secrets directly in `--command-config` arguments or inline JAAS in command history. Use restricted-permission files or platform secret injection.

### 10.2. Credential rotation

When rotating SCRAM passwords or TLS certificates:

1. Prepare new identity/credentials.
2. Update broker-side credentials/certificates per procedure.
3. Update secrets in the runtime deployment.
4. Roll/restart consumers in a controlled manner.
5. Verify authentication and authorization continue succeeding.
6. Revoke old credentials after all clients have transitioned.
7. Monitor reconnects/rebalances and authorization errors.

Credential rotation does not alter ACLs if the principal name stays the same; however, if the principal changes, ACLs must be granted for the new identity.

## 11. Consumer Group ID Must Match the ACL

A common mistake is granting ACLs for group `billing-service`, while runtime uses a different group ID.

Sources of group ID configuration can include:

- `spring.kafka.consumer.group-id`.
- `groupId` on `@KafkaListener`.
- `idIsGroup` behavior of the annotation/container in that version.
- Custom container properties or factories.
- Environment-specific overrides.

Example:

~~~java
@KafkaListener(
    id = "billing-listener",
    groupId = "${app.kafka.billing-group}"
)
public void consume(OrderCreated event) {
    billingService.process(event);
}
~~~

If `app.kafka.billing-group=billing-prod-v2`, the ACL must grant permission for GROUP resource `billing-prod-v2`, not `billing-service`.

### 11.1. Listener ID is not group ID

In the example:

~~~java
@KafkaListener(
    id = "billing-listener",
    groupId = "billing-service",
    topics = "orders.created"
)
~~~

- Listener ID: `billing-listener` — identifies the container in the Spring Kafka registry.
- Group ID: `billing-service` — the Kafka consumer group resource.
- Principal: `User:billing-consumer` — the identity authorized by the broker.

Group ACLs use **group ID**, not listener ID.

### 11.2. Multiple listeners, multiple groups

A service may have two listeners:

~~~java
@KafkaListener(
    id = "orders-listener",
    topics = "orders.created",
    groupId = "billing-orders"
)
public void onOrder(OrderCreated event) { }

@KafkaListener(
    id = "refund-listener",
    topics = "refunds.created",
    groupId = "billing-refunds"
)
public void onRefund(RefundCreated event) { }
~~~

If the same principal serves both listeners, it needs READ on both topics and READ on both groups. If you want to isolate blast radius, use separate principals or separate deployment identities.

## 12. Consumer Pattern Subscriptions and ACLs for New Topics

With topic patterns, read permissions must cover every topic the pattern matches. Two common approaches:

1. Grant literal ACLs for each existing topic and update when new topics are added.
2. Grant prefixed ACLs for a governed naming namespace.

Example naming convention:

~~~text
billing.input.orders.created
billing.input.orders.updated
billing.input.refunds.created
~~~

The prefix `billing.input.` can be more appropriate than `billing.` if the consumer only reads input topics.

### 12.1. Topics created after ACLs are granted

If a literal ACL applies only to `orders.created`, a new topic `orders.updated` will not automatically be allowed merely because code regex matches it.

If using a prefixed ACL, new topics whose names begin with the prefix can match immediately, depending on authorizer/resource pattern semantics. This is operationally convenient, but also expands permission scope when new topics are created.

### 12.2. Metadata discovery and AdminClient

Normal consumer subscriptions require metadata and read access to the topics they consume. If the application also uses `AdminClient` to list topics, describe the cluster, inspect configs, or provision resources, that is a separate set of operations.

Do not grant CLUSTER DESCRIBE, DESCRIBE_CONFIGS, or CREATE just because `@KafkaListener` needs to read records. If the service genuinely requires AdminClient operations, identify the exact APIs and resources and grant separate ACLs.

### 12.3. Regex subscriptions are not an ACL management mechanism

Do not use an overly broad regex like `.*` and grant wildcard topic READ. Subscription and authorization are independent mechanisms. Review naming conventions and ACL patterns together.

## 13. ACLs for Consumers Using Retry Topics and DLTs

A listener may use retry topics or a dead-letter topic. In that case, the service may consume the original topic, consume retry topics, and publish records to retry/DLT destinations.

A consumer that only reads the original topic may need only READ on the source topic and READ on the group. However, a service using `@RetryableTopic` typically needs additional permissions along the retry/DLT paths.

Example:

~~~text
Input topics:
  orders.created

Retry topics:
  orders.created-retry-1000
  orders.created-retry-5000

DLT:
  orders.created.DLT
~~~

Permissions depend on how retry is implemented:

| Activity | Resource | Permissions Typically Needed |
|---|---|---|
| Consume original topic | TOPIC source | READ |
| Join original group | GROUP source group | READ |
| Consume retry topic | TOPIC retry | READ |
| Join retry consumer group | GROUP retry group | READ |
| Publish retry record | TOPIC retry | WRITE |
| Publish DLT record | TOPIC DLT | WRITE |
| Consume DLT in separate listener | TOPIC DLT | READ |
| Join DLT consumer group | GROUP DLT group | READ |

**Do not grant WRITE on the DLT to a consumer that only reads the DLT.** If `DeadLetterPublishingRecoverer` publishes records, the producer role needs WRITE on the destination topic; the consumer role needs READ if there is a separate DLT listener.

### 13.1. Auto-created retry topics

If the framework/deployment creates retry topics automatically, determine who creates them:

- A provisioning/admin pipeline can pre-create topics.
- The runtime application can use AdminClient to create topics if granted permissions.
- Infrastructure operators can manage the topic lifecycle.

Do not grant CREATE/ALTER/DELETE to runtime consumers by default. Pre-provisioning topics and granting runtime ACLs is usually easier to audit.

### 13.2. DLT producer failure is a recovery failure

If the service lacks a WRITE ACL on the DLT, the recoverer cannot finish storing the failed record. Monitor `TopicAuthorizationException`, ensure recovery is not treated as successful, and keep source offsets safe per error handler/transaction policy.

A consumer with READ on source/group but missing WRITE on the DLT can process normal records smoothly until recovery is needed. That is why error paths must be tested, not just the happy path.

## 14. Do Consumers Using Transactional Listeners Need Extra ACLs?

With Kafka transactions, additional permissions depend on whether the consumer publishes records inside the transaction and how producer transaction IDs are configured.

A transactional listener may:

- Consume input topic: READ on TOPIC.
- Join group: READ on GROUP.
- Produce output: WRITE on output TOPIC.
- Use transactional producer ID: appropriate permissions on the TRANSACTIONAL_ID resource per transaction setup/version.
- Perform transaction coordinator operations: Kafka authorization may check related resources.

Do not assume a consumer-only app needs a TRANSACTIONAL_ID ACL. Grant this permission only when the application actually uses a transactional producer/transaction manager and the authorizer requires it for that resource.

### 14.1. Transactional ID resource

If the application uses a transactional producer, inspect `transactional.id` or the prefix Spring Kafka builds from `transactionIdPrefix`. The ACL pattern for `TRANSACTIONAL_ID` must match actual IDs, especially with multiple instances and dynamic suffixes.

Producer fencing/transaction authorization is distinct from group READ permission. Inspect broker exceptions and transaction configuration before adding ACLs.

### 14.2. Separating permissions by role

An architecture might use:

~~~text
billing-consumer principal:
  READ source topics
  READ consumer group

billing-publisher principal:
  WRITE output topics
  TRANSACTIONAL_ID operations if needed

billing-dlt-publisher principal:
  WRITE DLT/retry topics
~~~

Separating principals adds secret/configuration management overhead, but narrows the privileges of each runtime component. Choose based on your system's threat model and operations.

## 15. Verifying Effective ACLs with `kafka-acls.sh`

To list ACLs for a topic:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --command-config admin.properties \
  --list \
  --topic orders.created
~~~

To list group ACLs:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --command-config admin.properties \
  --list \
  --group billing-service
~~~

To list ACLs for a specific principal, depending on Kafka CLI version you can filter with `--principal` during list. Otherwise, list by resource and match principal/pattern/host/operation in the output.

When checking, verify all dimensions:

- Principal spelling/case matches.
- Resource type is TOPIC or GROUP.
- Resource name matches.
- Pattern type is literal/prefixed.
- Operation includes READ.
- Permission type is ALLOW.
- Host condition matches.
- No matching DENY ACL exists.

### 15.1. ACL listing does not prove client authentication

`kafka-acls.sh --list` runs with an admin principal and shows ACL configuration. It does not prove that the runtime consumer logged in successfully as the expected principal.

To confirm identity, use broker logs/authentication metrics or test with runtime credentials. Do not conclude "the ACL is right" just because list output shows an ALLOW entry if the client actually authenticates as a different principal.

### 15.2. Checking principal mapping

If TLS DNs or Kerberos principals are mapped, inspect `principal.builder.class` and related mapping rules. A certificate renewal with a different DN can change the principal and break matching against old ACLs.

When identity mapping changes, test on a staging broker/listener before rolling out cluster-wide.

## 16. Testing the Actual Consumer with Its Runtime Identity

A solid test should use the **same credentials, security protocol, group ID, and topic scope** as the application.

Example using Kafka console consumer:

~~~bash
bin/kafka-console-consumer.sh \
  --bootstrap-server kafka-1.internal:9093 \
  --consumer.config billing-consumer.properties \
  --topic orders.created \
  --group billing-service \
  --from-beginning \
  --max-messages 1
~~~

`billing-consumer.properties` holds protected runtime security properties. The command reads at most one message and can affect group offsets if using the real production group ID.

**In production, do not run a test command with a live running group ID** unless you intend to alter group membership/offset behavior. Use a separate test group and grant an ACL for that test group, or run a controlled smoke test per runbook.

### 16.1. Separate test group

Example:

~~~text
group.id = billing-acl-smoke-test
principal = User:billing-consumer
topic = orders.created
~~~

Grant READ on the topic and test group; run console consumer with the exact properties; then revoke the test group ACL. This confirms the principal can fetch the topic and use a group without interfering with production group offsets.

### 16.2. Testing the actual Spring Kafka application

Console consumer is useful, but does not test serializers, listener factories, group ID overrides, or Spring error handling. Ultimately, run a smoke test using the actual Spring Boot application with the appropriate runtime profile/secrets.

Observe startup logs, assignment, polls, listener invocations, and offset progress.

## 17. Troubleshooting by Exception

### 17.1. `TopicAuthorizationException`

Symptom: consumer is not allowed to perform an operation on the topic.

Check:

1. Exact topic name in the exception.
2. Principal authenticated by the broker.
3. Whether the TOPIC ACL for the principal has ALLOW READ.
4. Whether the resource pattern matches the topic.
5. Whether any DENY ACL matches.
6. Whether broker authorizer logs indicate the denied operation.
7. Whether the listener subscribes to extra topics via regex/pattern.

Do not add wildcard topic READ when only one topic lacks an ACL.

### 17.2. `GroupAuthorizationException`

Symptom: consumer is not allowed to use the group resource.

Check:

1. Runtime group ID from effective configuration.
2. Whether the GROUP ACL has ALLOW READ for the principal.
3. Whether group prefix/literal matches.
4. Whether the principal was mapped to a different name.
5. Whether a group ID override exists on `@KafkaListener` or environment.
6. Whether any DENY ACL matches.

A group ACL granted for `billing-service` does not apply to `billing-service-v2` when using literal patterns.

### 17.3. `ClusterAuthorizationException`

Some clients/APIs may require a CLUSTER-level operation, such as admin operations or cluster description. Do not grant broad CLUSTER permissions to a consumer just to clear the exception without knowing which API issued the request.

If the application uses AdminClient, identify the actual operation and evaluate separating admin tasks from the runtime listener.

### 17.4. `SaslAuthenticationException`

This is an authentication error, not a missing topic/group ACL. Check username/password, mechanism, JAAS module, credential rotation, and broker SASL listener.

### 17.5. `SSLHandshakeException`

Check CA trust, broker hostname/SAN, client certificate if mutual TLS, TLS protocol/ciphers, and certificate expiration. Do not modify ACLs to fix a TLS handshake error.

### 17.6. No clear exception, but listener receives no records

Check:

- Has the consumer authenticated?
- Has the group joined/received partition assignments?
- Does the topic have records and appropriate retention?
- Is the consumer paused?
- Do ACLs allow READ topic and READ group?
- Is the application pointing to the right cluster/bootstrap servers?
- Where are consumer lag/offsets?
- Are logs missing due to log levels or async delivery?

Authorization errors usually appear in client logs and broker authorizer logs; metrics help detect them but do not replace exception/resource details.

## 18. ACLs and Consumer Group Offsets

Kafka stores committed offsets by group and topic-partition. A consumer group needs proper authorization to use the group and commit offsets.

If a consumer can read records but offset commits are denied or it cannot operate with the group, the system may:

- Re-read records after restarts/rebalances.
- Fail to advance committed offsets.
- Build growing lag even though the listener processed some records.
- Cause duplicate business processing if side effects are not idempotent.

### 18.1. Do not grant topic WRITE to commit offsets

Offset commits are not business produces to the source topic. Kafka manages group offsets via the group coordinator and group resource. Granting WRITE on the topic does not replace READ on GROUP.

### 18.2. Manual commit and Spring Kafka AckMode

`AckMode` settings such as RECORD, BATCH, MANUAL, and MANUAL_IMMEDIATE control when the container acknowledges/commits offsets per configuration. They do not alter ACL resource rules: the consumer group still needs appropriate permissions to execute group/offset operations.

If logs show commit errors, distinguish:

- Authorization denied.
- Coordinator/network timeout.
- Invalid generation/member ID due to rebalance.
- Transaction commit/abort.
- Missing application acknowledgement.

Do not add ACLs when the real cause is a rebalance or timeout.

## 19. ACLs Across Multiple Environments

Production, staging, and development should use separate identities if policy requires isolation.

Example:

| Environment | Principal | Group | Topics |
|---|---|---|---|
| Dev | `User:billing-dev` | `billing-dev` | `dev.orders.created` |
| Staging | `User:billing-staging` | `billing-staging` | `staging.orders.created` |
| Production | `User:billing-consumer` | `billing-service` | `orders.created` |

Avoid using the same principal with read access across all environments, especially when production data is sensitive.

### 19.1. ACL-as-code

Manage ACL changes as versioned infrastructure configuration:

- Principal and owner.
- Resource type/name/pattern.
- Operation and permission type.
- Environment/cluster.
- Ticket/change reason.
- Approver.
- Grant date and revocation criteria.

A pipeline can apply ACLs via Admin API/CLI, then list and diff against desired state. Do not store admin credentials in repositories.

### 19.2. Drift detection

Over time, ACLs may be added manually, left unrevoked, or modified outside the pipeline. Periodically compare actual ACLs against approved policy.

Focus on:

- Wildcard principals.
- Wildcard topics/groups.
- ALLOW READ on sensitive topics.
- Broad DENY entries.
- Principals without an active service owner.
- Overly broad prefix patterns.
- Runtime identities holding admin privileges.

## 20. Safe Consumer Permission Provisioning Workflow

A practical workflow:

1. Identify service and business owner.
2. Identify Kafka cluster/environment.
3. Identify authentication mechanism.
4. Verify the actual principal seen by brokers.
5. List topics the listener actually subscribes to.
6. Determine the effective group ID.
7. List retry/DLT topics if used by the service.
8. Determine whether the service only consumes or also publishes/uses AdminClient/transactions.
9. Create minimal literal ACLs for TOPIC READ.
10. Create minimal literal ACLs for GROUP READ.
11. Apply ACLs using an admin identity.
12. List ACLs to verify resource/pattern/operation.
13. Smoke test with runtime credentials and the right group.
14. Confirm listener assignment, processing, and offset progress.
15. Save audit record and ACL owner.
16. Set a review/revocation deadline if permissions are temporary.

Do not grant broad ACLs first and hope to tighten them later. Temporary broad permissions are easily forgotten and become permanent.

## 21. ACL Revocation and Rotation

When a service stops consuming a topic, revoke unused permissions. Before removing:

1. Confirm no active deployments/consumers still use the principal.
2. Check listener groups and topic subscriptions.
3. Check retry/DLT/replay jobs.
4. Verify whether a consumer migration is underway.
5. Revoke specific ACLs.
6. Re-list ACLs to confirm.
7. Monitor authorization errors and consumer group activity.

When changing principals, the safe process is usually granting ACLs to the new principal, deploying/verifying the new client, and revoking the old principal's ACLs after migration completes.

Do not revoke a group ACL while old consumers still need to commit offsets or drain during rollout.

## 22. Observing ACLs and Authorization in Production

Useful signals:

| Signal | Purpose |
|---|---|
| Authentication failure count | Detect faulty credentials/mechanisms |
| Authorization failure count | Detect missing ACLs or DENY rules |
| TopicAuthorizationException count | Isolate topic resources |
| GroupAuthorizationException count | Isolate group resources |
| Principal / client ID | Identify runtime identity |
| Topic/group resource | Identify denied scope |
| Consumer group state | Confirm join/assignment |
| Commit failure count | Track offset progress |
| Rebalance rate | Distinguish authorization from lifecycle/group issues |
| Secret/certificate expiry | Prevent authentication failures |

Exact metric names depend on Kafka version, broker authorizer, logging/metrics exporter, and application instrumentation. Exception counters may need to be created at the application layer or log pipeline.

### 22.1. Logging authorization failures

Broker authorizer logs are often helpful to identify the denied principal, host, operation, and resource. Protect these logs because they contain details about identities, topic naming, and security policies.

Do not log passwords, SASL tokens, or private keys. Log only the principal and resource metadata necessary for auditing/troubleshooting.

### 22.2. Alert on change, not just volume

A newly deployed service can generate many authorization failures within seconds if ACLs were not provisioned. Alerts should include service/cluster/principal/resource context so operators can fix the exact entry.

If a principal repeatedly attempts to read many unauthorized topics, this may indicate misconfiguration or anomalous activity requiring investigation.

## 23. Testing ACLs in an Integration Environment

A Spring Kafka unit test does not prove the broker authorizer enforces ACLs. You need a Kafka environment with authentication and an authorizer enabled for end-to-end testing.

### 23.1. Happy path with least privilege

1. Create principal `billing-consumer`.
2. Create topic `orders.created`.
3. Grant TOPIC READ to the principal.
4. Grant GROUP READ for `billing-service`.
5. Run the consumer with matching SASL/TLS credentials.
6. Send a test record using a producer test identity.
7. Confirm the listener receives the record and offsets advance.
8. Check broker logs for zero authorization denials.

### 23.2. Missing topic ACL

1. Revoke TOPIC READ.
2. Keep GROUP READ.
3. Restart or create a test consumer with that principal.
4. Confirm topic authorization failure is observed.
5. Re-grant READ and confirm the consumer recovers.

This scenario proves group permission does not substitute for topic permission.

### 23.3. Missing group ACL

1. Keep TOPIC READ.
2. Revoke GROUP READ.
3. Use a test group ID.
4. Confirm group authorization failure.
5. Re-grant GROUP READ and confirm the consumer can join/commit.

Do not run this test against a production group processing live data.

### 23.4. Prefixed ACL

1. Grant READ with prefix `orders.events.`.
2. Create two topics within the prefix.
3. Confirm the principal can read both.
4. Create a topic outside the prefix.
5. Confirm the principal cannot read the out-of-scope topic.
6. Verify group ACL remains independent.

### 23.5. DENY ACL

Create a controlled broad ALLOW and then add a DENY for one specific topic. Confirm the denied topic cannot be read while other topics remain readable per policy.

Clean up test ACLs after finishing and re-list resources so no temporary permissions remain.

### 23.6. Authentication failure

Use wrong credentials or a mismatched mechanism in the test environment. Confirm the error is authentication, distinguished from authorization. Do not use real credentials to intentionally trigger login failures in production.

### 23.7. Retry/DLT permissions

If the service has retry/DLT:

- Verify source READ and group READ.
- Verify retry topic READ/WRITE per role.
- Verify DLT producer has WRITE.
- Verify DLT listener has READ and group READ.
- Revoke DLT WRITE to test controlled recovery failure.
- Confirm source records are not falsely acked/committed when DLT publish is denied.

## 24. Common Mistakes

**Granting READ on topic while forgetting group.** Consumer cannot operate fully with the group or commit offsets per policy.

**Granting READ on group while forgetting topic.** Consumer cannot fetch data from the topic.

**Using listener ID instead of group ID in ACLs.** GROUP ACLs must match the actual group resource.

**Using client ID as principal.** Client ID is client metadata, not an authenticated identity.

**Using admin credentials for runtime consumers.** Masks missing ACLs and expands blast radius.

**Granting wildcard TOPIC READ to a service.** Allows reading data beyond business scope.

**Using overly broad prefixes.** New topics can automatically fall into the granted permission zone.

**Confusing authentication with authorization.** A wrong SASL password is not fixed by adding ACLs.

**Confusing topic ACLs with group ACLs.** They are two independent resources.

**Forgetting retry/DLT topics.** Happy path works, but error paths hit authorization failures.

**Granting consumers CREATE/DELETE/ALTER topic permissions by default.** Runtime consumers do not need admin privileges just to read.

**Assuming DESCRIBE_CONFIGS is needed for every consumer.** That is a configuration-reading operation, not a record-fetching permission.

**Not checking principal mapping.** Certificate/Kerberos mapping can make the principal differ from the expected username.

**Granting group prefixes for pod-specific group IDs without evaluation.** Can turn each pod into an independent group and alter consumption semantics.

**Testing with an admin principal.** A passing test does not prove the runtime identity has proper permissions.

**Not checking DENY rules and host constraints.** A single ALLOW entry may not suffice to authorize a request.

**Granting production ACLs manually without auditing.** Temporary permissions easily become long-lived.

**Revoking ACLs before consumers finish draining.** Can cause commit/rebalance failures during rollout.

**Assuming Kafka ACLs protect database or HTTP side effects.** ACLs only protect Kafka resources/operations; external dependencies need separate authorization.

## 25. Runbook When a Consumer Hits Authorization Failures

### Phase A — Identify the failing layer

1. Collect exception classes and broker logs.
2. Distinguish SASL/TLS authentication from Kafka authorization.
3. Record actual principal, host, and client ID.
4. Identify TOPIC, GROUP, or CLUSTER resource.
5. Record topic/group ID and denied operation.

### Phase B — Cross-check policy

1. List ACLs on the relevant topic/group.
2. Check ALLOW/DENY.
3. Check literal/prefixed/wildcard.
4. Check principal mapping.
5. Check host restrictions.
6. Compare against effective Spring Boot group ID and listener topic subscriptions.
7. Check whether the consumer uses retry/DLT/AdminClient/transactional behavior.

### Phase C — Remediate

1. Grant least-privilege permissions for the exact principal/resource/operation.
2. Do not grant wildcards or admin rights as a bypass.
3. Smoke test with runtime credentials.
4. Perform a controlled consumer restart/reconnect if needed.
5. Confirm group join, partition assignment, record processing, and offset progress.
6. Monitor authorization failures after deployment.
7. Audit and record the ACL change.

If authentication succeeded and the broker specifies `READ` was denied on `orders.created`, fix the corresponding TOPIC ACL. If the resource is `billing-service` as a GROUP, fix the GROUP ACL. Do not blindly change both.

## 26. Version-Specific Reference Documentation

When implementing ACLs, consult the official documentation of your running Kafka distribution/version:

- **Apache Kafka Security — Authorization and ACLs**: principals, resources, operations, ALLOW/DENY, and resource patterns.
- **Apache Kafka Security — SASL Authentication**: SCRAM, PLAIN, GSSAPI, and listener configuration.
- **Apache Kafka Security — SSL**: truststore, keystore, client authentication, and principal mapping.
- **Kafka `kafka-acls.sh` documentation**: `--add`, `--remove`, `--list`, `--topic`, `--group`, `--principal`, resource pattern types.
- **Apache Kafka Authorizer documentation**: StandardAuthorizer for KRaft and authorizers for older deployments/versions.
- **Spring for Apache Kafka Reference — Connecting to Kafka / Boot Integration**: consumer factory, container, and security properties.
- **Spring Boot Reference — Kafka Properties**: `spring.kafka.consumer.group-id`, `spring.kafka.properties.*`, and client configuration.
- **Kafka Consumer API**: subscribe/assign, group membership, offset commit, and consumer behavior.
- **Kafka Admin API**: managing ACLs and resource operations.

Authorizer classes, default behavior, CLI flags, and operation implications can vary between Kafka versions/distributions. Verify the Javadoc/help of the exact `kafka-acls.sh` and broker configuration before changing production ACLs.

**Technical conclusion:** a standard Spring Kafka consumer using a consumer group must authenticate as the right principal and be permitted **READ on each source topic** and **READ on the actual group ID**. Grant permissions using controlled literal/prefix patterns, keep runtime principals separate from admin, and test using the application's real credentials. When errors occur, distinguish authentication, topic authorization, and group authorization before modifying ACLs; least privilege must also cover retry/DLT paths if the service uses them.
