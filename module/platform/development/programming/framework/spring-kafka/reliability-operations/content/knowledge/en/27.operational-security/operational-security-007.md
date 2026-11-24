# ACLs for DLTs in Spring Kafka

A Dead Letter Topic (DLT) stores Kafka records that could not be processed successfully after retries or were classified as non-retryable errors. A DLT preserves data for investigation, quarantine, and replay. When a Kafka cluster has authorization enabled, sending a record to a DLT is a new publish operation and must be explicitly authorized.

A consumer may read the source topic normally yet lack permission to write to the DLT. When that happens, the listener fails, the error handler invokes DeadLetterPublishingRecoverer, KafkaTemplate sends the record, and the broker rejects it due to ACLs. If the application does not handle the send failure properly, the source record could be treated as recovered while the DLT copy was never stored.

**DLT ACLs** must be designed by role: source consumer, DLT publisher, DLT consumer, replay operator, and administrator. Each principal should only be granted permissions on the exact topics, consumer groups, and transactional IDs it requires. Do not grant cluster-wide permissions just to make the DLT work.

This lesson explains Kafka ACL resources and operations, principal mapping, kafka-acls commands, Spring Kafka DeadLetterPublishingRecoverer, retry topics, transactional producers, topic pre-provisioning, authorization failures, and production verification procedures.

## 1. Why Does a DLT Need Its Own ACL?

Suppose the orders service reads topic orders.events. When a record cannot be processed, the recoverer sends it to orders.events.DLT.

~~~text
Kafka topic: orders.events
       |
       v
orders-service consumer
       |
       v
@KafkaListener
       |
       +--> processing succeeds
       |
       +--> exception
                |
                v
          DefaultErrorHandler
                |
                +--> retry
                |
                +--> retries exhausted / non-retryable
                         |
                         v
                DeadLetterPublishingRecoverer
                         |
                         v
                   KafkaTemplate
                         |
                         v
                orders.events.DLT
~~~

There are at least two independent Kafka operations:

1. Consumer reading a record from the source topic.
2. Producer writing a new record to the DLT.

READ permission on orders.events **does not automatically grant WRITE permission on orders.events.DLT**. ACLs are evaluated per principal, resource, and operation on each request.

A listener can process business records normally for days and only fail when the DLT is needed. If ACLs have not been granted, the authorization error surfaces right during recovery. Therefore, DLT permissions must be prepared and tested before production.

## 2. Common Principals and Roles

Do not assume every component should share the same principal. A deployment can separate credentials by responsibility:

| Principal / role | Responsibility | Key Permissions |
|---|---|---|
| orders-source-consumer | Read source topic and process records | READ source topic, READ consumer group |
| orders-dlt-publisher | Send failed records to DLT | WRITE DLT topic |
| orders-dlt-consumer | Read and investigate DLT | READ DLT topic, READ DLT consumer group |
| orders-replay-operator | Read DLT and publish replay records | READ DLT, READ group, WRITE destination topic |
| kafka-admin | Provision topics, ACLs, and configs | Separately controlled admin permissions |

If the source consumer and DLT publisher share the same Kafka principal, that principal needs both source read and DLT write permissions. This is a common simple configuration. Separating publisher credentials shrinks privilege scope and clarifies auditing.

**A principal is the identity authenticated by the broker**, not necessarily a Spring bean name, listener ID, or Kubernetes service account. ACLs must match the principal the broker sees after SASL/mTLS authentication and principal mapping.

## 3. Kafka ACL Resources and Operations

Kafka authorization applies to resource types. Those most relevant to DLTs:

| Resource type | Represents | Example |
|---|---|---|
| Topic | A topic or pattern-matched group of topics | orders.events.DLT |
| Group | Consumer group | orders-dlt-investigation |
| Cluster | Cluster-level resource | IdempotentWrite or cluster operations |
| TransactionalId | Producer transactional ID | orders-dlt-publisher- |
| DelegationToken | Delegation token if used | token identity |

Common operations:

| Operation | General Meaning |
|---|---|
| READ | Read records or use a group depending on resource type |
| WRITE | Write records to a topic or use a transactional ID depending on resource |
| DESCRIBE | Read resource metadata |
| CREATE | Create resource |
| DELETE | Delete resource |
| ALTER | Modify resource |
| DESCRIBE_CONFIGS | Read configurations |
| ALTER_CONFIGS | Modify configurations |
| IDEMPOTENT_WRITE | Permission related to idempotent producers on the cluster |
| CLUSTER_ACTION | Certain internal/cluster operations |
| ALL | All operations applicable to the resource |

Permissions are evaluated per resource type. READ on Topic differs from READ on Group; a topic ACL cannot substitute for consumer group permissions.

Kafka authorizers have operation implication rules, such as certain read/write permissions implying describe capabilities per broker semantics. When deploying, consult the authorization matrix for your exact Kafka version and authorizer rather than granting every operation out of habit.

## 4. Minimum Permissions for a DLT Publisher

If the orders service uses one principal to read the source and publish to the DLT, typical minimum permissions are:

- READ on source topic orders.events.
- READ on consumer group orders-service.
- WRITE on destination topic orders.events.DLT.
- Additional permissions if the producer uses transactions or idempotent authorization per broker policy.

Diagram:

~~~text
Principal: User:orders-service

Topic orders.events
  READ

Group orders-service
  READ

Topic orders.events.DLT
  WRITE
~~~

The publisher does not need DELETE on the DLT to send records. It also does not need ALTER_CONFIGS merely because it uses KafkaTemplate.

If the publisher can write to multiple DLT topics, list the exact set of destinations. Do not grant WRITE across the entire topic namespace if the service only sends to specific DLTs.

## 5. Permissions for a DLT Consumer

A service investigating or quarantining a DLT needs:

- READ on the DLT topic.
- READ on the consumer group it uses.
- Metadata access per broker authorization behavior.

Example:

~~~text
Principal: User:orders-dlt-investigator

Topic orders.events.DLT
  READ

Group orders-dlt-investigation
  READ
~~~

READ on the topic lets the consumer fetch records per ACLs; READ on the group lets the consumer join the group and manage offsets per the consumer group protocol.

If operators use Kafka UI or AdminClient to inspect topic metadata, offsets, or configs, DESCRIBE or corresponding admin permissions may be required. Do not grant ALTER or DELETE to a consumer whose only job is reading and quarantining records.

## 6. Source Consumer, Retry Topics, and DLT Have Distinct Permissions

A flow using retry topics can require more permissions than a simple DLT:

~~~text
orders.events
     |
     +--> source consumer
     |
     +--> retry publish
              |
              v
       orders.events-retry
              |
              +--> retry consumer
                       |
                       +--> success
                       |
                       +--> exhausted
                                |
                                v
                         orders.events.DLT
~~~

With non-blocking retries, the application may both consume source/retry topics and publish to retry/DLT destinations. ACLs must follow the topology:

| Topic/resource | Permissions Typically Needed |
|---|---|
| orders.events | READ |
| orders.events-retry | READ and/or WRITE depending on role |
| orders.events-retry-5000 | READ and/or WRITE depending on topology |
| orders.events.DLT | WRITE from publisher; READ from DLT consumer |
| orders-service group | READ |
| retry consumer group | READ |
| DLT investigation group | READ |

Do not infer permissions solely from topic names. List every listener endpoint, retry publisher, recoverer, group ID, and destination resolver to see which principal genuinely needs which operation.

If the source consumer uses one principal for both source and retry/DLT publishing, permissions can be combined. If using separate producer factories, grant WRITE to the corresponding producer principal.

## 7. Granting ACLs with kafka-acls.sh

Kafka provides kafka-acls.sh to add, list, and remove ACLs. The commands below illustrate a DLT publisher principal.

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-service \
  --operation Write \
  --topic orders.events.DLT
~~~

If READ permission is needed for the source topic:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-service \
  --operation Read \
  --topic orders.events
~~~

Consumer group permission:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-service \
  --operation Read \
  --group orders-service
~~~

In these examples, admin-client.properties holds connection and authentication config for an administrative account permitted to manage ACLs. Do not use administrative credentials in the orders-service application.

## 8. Granting ACLs for a DLT Consumer

Example read-only DLT principal:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-dlt-investigator \
  --operation Read \
  --topic orders.events.DLT
~~~

And separate group:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-dlt-investigator \
  --operation Read \
  --group orders-dlt-investigation
~~~

This principal does not need WRITE on source or DLT just to inspect records. If an investigation tool includes replay functionality, treat replay as a separate role and grant WRITE only on the target topics where operators are allowed to replay.

A useful principle is that **read-only investigator** and **replay operator** have different permissions. Inspecting a record does not mean permission to replay it into a production topic.

## 9. Reviewing Granted ACLs

After adding ACLs, list permissions on a topic:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --list \
  --topic orders.events.DLT
~~~

List permissions on a consumer group:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --list \
  --group orders-dlt-investigation
~~~

Listing ACLs across the entire cluster can return very large results; use it only when performing broad audits with appropriate permissions.

ACL output should be compared against a reviewed desired-state table. Seeing that a principal has WRITE is not enough to know whether it was granted overly broad prefix access or has a conflicting DENY ACL.

## 10. Literal Resource and Prefixed Resource Patterns

Kafka ACLs can apply to a literal resource or a prefix pattern.

**Literal** applies only to the exact resource name:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-service \
  --operation Write \
  --topic orders.events.DLT \
  --resource-pattern-type literal
~~~

**Prefixed** applies to resources whose names begin with the specified prefix:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-service \
  --operation Write \
  --topic orders. \
  --resource-pattern-type prefixed
~~~

For example, prefix orders. covers orders.events, orders.events.DLT, and other topics sharing the prefix. This is convenient with many DLT topics but also widens permission scope.

Using literal for fixed DLTs is usually easiest to audit. Use prefixed ACLs only when naming conventions are governed and all topics under the prefix truly share the same trust boundary.

## 11. DENY ACLs and Allowlists

Kafka ACLs support allow and deny entries. When ACLs overlap, DENY can reject a request even if the principal has another matching ALLOW.

~~~text
ALLOW User:orders-service WRITE Topic:orders.events.DLT
DENY  User:orders-service WRITE Topic:orders.events.DLT
~~~

In a policy containing a matching DENY, operators must not look at an ALLOW line and conclude access works. Inspect all ACLs applying to the principal, host, and resource pattern.

Recommended design:

- Start with least privilege.
- Use separate principals per service/role.
- Limit wildcards/prefixes.
- Add DENY rules only for explicit policies and with clear understanding of precedence.
- Audit both ALLOW and DENY.
- Avoid broad DENY rules that could prevent services from publishing DLTs during an incident.

If a cluster has no matching ACL and the default policy allows or denies, behavior also depends on authorizer configuration. Verify broker config before assuming "no ACL" implies a specific result.

## 12. Pre-Creating DLT Topics Instead of Relying on Auto-Create

A common mistake is granting only WRITE to the publisher and expecting Kafka to auto-create the DLT topic. Topic creation is a separate administrative operation.

In production, pre-provision DLT topics:

- Partition count compatible with the destination resolver.
- Replication factor appropriate for the cluster.
- min.insync.replicas matching durability requirements.
- Retention long enough for investigation/replay.
- Cleanup policy suited to DLT usage.
- Quotas and storage capacity.
- ACLs for publishers and consumers.

If DeadLetterPublishingRecoverer preserves the source partition by default when choosing a destination, the DLT usually needs an equal or greater partition count. If the DLT has fewer partitions than the source, the destination resolver can pick a nonexistent partition. The resolver can be configured to return partition -1 so the Kafka producer chooses a partition automatically when compatible with ordering requirements.

Do not grant cluster-wide CREATE to a business consumer just to work around a missing DLT topic. Let a provisioning pipeline or administrator create topics and ACLs via reviewed changes.

## 13. Destination Resolver Must Match ACLs

DeadLetterPublishingRecoverer can use a destination resolver to choose the destination topic/partition. Example:

~~~java
DeadLetterPublishingRecoverer recoverer =
        new DeadLetterPublishingRecoverer(
                dltKafkaTemplate,
                (record, exception) -> new TopicPartition(
                        record.topic() + ".DLT",
                        -1
                )
        );
~~~

For source topic orders.events, the destination is orders.events.DLT. Publisher ACLs must allow WRITE on that exact destination.

If the resolver routes by exception category:

~~~text
orders.events + validation error
    -> orders.validation.DLT

orders.events + database error
    -> orders.infrastructure.DLT
~~~

then the publisher needs WRITE on both destinations. Do not grant WRITE only to orders.events.DLT and overlook a rarely hit resolver branch.

Some systems route topics based on tenant or payload. Avoid generating arbitrary DLT topics per input record, as topic governance and ACLs become unmanageable. Map into a fixed set of destinations.

## 14. Spring Kafka Configuration for DLT Publishers

Example error handler using KafkaTemplate:

~~~java
@Configuration
public class DltConfiguration {

    @Bean
    DefaultErrorHandler ordersErrorHandler(
            KafkaTemplate<Object, Object> dltKafkaTemplate) {

        DeadLetterPublishingRecoverer recoverer =
                new DeadLetterPublishingRecoverer(
                        dltKafkaTemplate,
                        (record, exception) -> new TopicPartition(
                                record.topic() + ".DLT",
                                -1
                        )
                );

        recoverer.setFailIfSendResultIsError(true);

        return new DefaultErrorHandler(
                recoverer,
                new FixedBackOff(1_000L, 2L)
        );
    }
}
~~~

This example illustrates the Spring Kafka API supporting setFailIfSendResultIsError. Check your application's version to confirm exact API and timeout/send-result behavior.

The key point is that when the Kafka broker rejects a DLT publish, the error must propagate into the recovery path per policy. If send result errors are ignored, the application may treat recovery as complete and advance the source offset while no DLT record exists.

Do not log a "sent to DLT" message immediately upon calling send. Distinguish between request creation, producer send completion, and broker acknowledgment per durability policy.

## 15. Same Principal or Separate DLT Publisher Credentials?

There are two ways to organize this.

**One principal for source consumer and DLT producer**

~~~text
User:orders-service
  READ  Topic:orders.events
  READ  Group:orders-service
  WRITE Topic:orders.events.DLT
~~~

Pros: simpler configuration, fewer producer factories and credentials.

Cons: a single service credential holds both source read and DLT write permissions; if leaked, its action scope is wider.

**Separate principal for the DLT publisher**

~~~text
User:orders-source-consumer
  READ Topic:orders.events
  READ Group:orders-service

User:orders-dlt-publisher
  WRITE Topic:orders.events.DLT
~~~

This separation requires a KafkaTemplate/ProducerFactory with dedicated credentials for the DLT. The error handler uses that exact template. Verify tracing, serializers, transaction settings, and security properties of the dedicated template.

Separating principals helps auditing and least privilege, though it increases the number of configs and secrets to manage. Choose based on your threat model, credential management capability, and DLT criticality.

## 16. SASL_SSL Configuration and ACLs Are Two Different Layers

**Authentication** determines who the client is. **Authorization** determines what that principal is allowed to do.

~~~text
Spring Kafka client
       |
       v
TLS/SASL authentication
       |
       v
Broker identifies principal
       |
       v
Kafka authorizer checks ACL
       |
       +--> ALLOW
       |
       +--> DENY
~~~

Example connection properties:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka-1.example.net:9093
    properties:
      security.protocol: SASL_SSL
      sasl.mechanism: SCRAM-SHA-512
~~~

This is only a partial configuration. JAAS credentials, truststores, and other secrets must be supplied via secret managers/appropriate environment injection; never hard-code passwords in source code or commit config files containing secrets.

TLS/SASL success does not mean ACLs allow DLT WRITE. Conversely, a valid ACL cannot help a client log in if authentication fails.

When broker logs show a different principal than the granted ACL principal, inspect principal mapping, SASL username, mTLS distinguished name, and authorizer configuration.

## 17. Distinguishing Authorization Errors by Resource Type

Common errors:

| Exception/error | Possible Cause | Check |
|---|---|---|
| TopicAuthorizationException | Missing permission on topic | READ/WRITE/Describe on exact topic |
| GroupAuthorizationException | Missing permission on consumer group | READ group on exact group.id |
| ClusterAuthorizationException | Missing cluster-level permission | Cluster operation or admin action |
| TransactionalIdAuthorizationException | Missing transactional ID permission | WRITE on TransactionalId resource |
| AuthenticationException | Failed to authenticate | SASL, TLS, credentials, principal mapping |
| Topic not found/metadata failure | Topic not yet created or invalid metadata | Topic provisioning, resolver, bootstrap metadata |
| Invalid partition | Destination partition does not exist | DLT partition count/resolver |
| SerializationException | Serializer does not support DLT payload | Key/value serializer and raw bytes |

Exact exception names and how they are wrapped can vary by Kafka client/Spring Kafka version. A send error may appear in a CompletableFuture cause chain rather than being thrown immediately at the KafkaTemplate.send call site.

Do not blame every DLT error on "missing WRITE ACL." Distinguish authentication, authorization, metadata, partitions, serialization, and broker availability.

## 18. Producer Idempotence and Transactional DLT Publishers

If the DLT producer uses idempotence or Kafka transactions, additional ACLs may be needed.

With an **idempotent producer**, broker authorization may require the IDEMPOTENT_WRITE operation on the Cluster resource depending on Kafka version and authorizer policy.

With a **transactional producer**, the producer uses a transactional.id. ACLs typically require WRITE on the corresponding TransactionalId resource, in addition to WRITE on target topics. Some flows also require cluster-level idempotent-write authorization.

Example transactional ID prefix:

~~~yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: orders-dlt-publisher-
~~~

Illustrative transactional ID prefix ACL:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-dlt-publisher \
  --operation Write \
  --transactional-id orders-dlt-publisher- \
  --resource-pattern-type prefixed
~~~

If the broker requires cluster-level IDEMPOTENT_WRITE:

~~~bash
kafka-acls.sh \
  --bootstrap-server kafka-1.example.net:9093 \
  --command-config admin-client.properties \
  --add \
  --allow-principal User:orders-dlt-publisher \
  --operation IdempotentWrite \
  --cluster
~~~

Grant these permissions only when the producer configuration and broker authorization actually require them. Do not add a transactional ID ACL for a non-transactional producer simply because DLT is used with Spring Kafka.

**Kafka transactions only span Kafka resources participating in the transaction.** They do not automatically roll back database or HTTP side effects of a listener. Transaction ACLs ensure permission to use transactions, not atomicity with systems outside Kafka.

## 19. Retry Topics Also Need ACLs

With Spring Kafka non-blocking retries, the framework can use retry topics and publish records to them before routing to the DLT.

Example topology:

~~~text
orders.events
    |
    +--> orders.events-retry-1000
    |
    +--> orders.events-retry-5000
    |
    +--> orders.events.DLT
~~~

Depending on configuration, the application may need:

- READ on source topic.
- WRITE on retry topics.
- READ on retry topics.
- WRITE on DLT.
- READ on consumer groups of retry listeners.
- READ on source consumer group.

If retry topics are created by a provisioning/admin process, the application does not need cluster-wide CREATE just to consume/publish to them. Grant ACLs for every topic actually present in the topology.

Retry topic names and routing depend on RetryTopicConfiguration, suffixes, attempts, and Spring Kafka version. Create ACLs based on the verified topology rather than guessing from a sample topic name.

## 20. Auto Topic Creation and CREATE Permission

Some Kafka clusters disable auto topic creation to prevent unplanned topics. If the DLT does not exist yet, the producer can hit metadata or authorization errors depending on broker configuration.

There are two options:

1. **Pre-provision DLT topics:** recommended for production.
2. **Allow the application to create topics:** requires granting CREATE per resource/cluster policy and accepting governance risk.

Pre-provisioning gives control over:

- Partition count.
- Replication factor.
- min.insync.replicas.
- Retention.
- Cleanup policy.
- Quotas.
- ACLs.
- Monitoring and ownership.

A business service generally does not need CREATE or DELETE on the cluster to send to a DLT. Separating provisioning roles from runtime producers is a cleaner least-privilege boundary.

If the DLT topic is created after the service starts, verify metadata refresh and startup ordering to prevent initial failures from being mistaken for listener data errors.

## 21. ACLs for Replay Operators

Replaying records from a DLT back to a source topic is an operation that can re-trigger business side effects. Therefore, replay operators need different permissions than DLT investigators.

A replay role may need:

- READ on the DLT topic.
- READ on the group used to read the DLT if replaying via consumer.
- WRITE on the source/replay destination topic.
- Additional permissions if using transactions.
- Tooling/audit access permissions per internal policy.

~~~text
User:orders-dlt-investigator
  READ Topic:orders.events.DLT
  READ Group:orders-dlt-investigation

User:orders-replay-operator
  READ  Topic:orders.events.DLT
  READ  Group:orders-replay
  WRITE Topic:orders.events
~~~

Do not grant source topic WRITE to everyone who can read the DLT. Replay requires approval/audit procedures, idempotency, and verification of side effects before re-publishing.

If replaying to an intermediate topic, grant WRITE only on that topic. A replay processor can be a separate service with its own principal rather than sharing credentials with the DLT investigation UI.

## 22. Configuring Kafka ACLs on KRaft and Older Clusters

The authorizer mechanism depends on the Kafka deployment:

- KRaft-based Kafka typically uses StandardAuthorizer.
- Older ZooKeeper-based clusters may use a ZooKeeper-based authorizer.
- Managed Kafka services may provide their own authorization layer and admin tooling.
- Principal mapping may transform identities from SASL/mTLS before the authorizer evaluates ACLs.

Example KRaft authorizer configuration within broker administrator scope:

~~~properties
authorizer.class.name=org.apache.kafka.metadata.authorizer.StandardAuthorizer
allow.everyone.if.no.acl.found=false
super.users=User:kafka-admin
~~~

This is an illustrative configuration example; super.users, listener configuration, and default ACL behavior must fit the actual deployment. Changing the broker authorizer affects the entire cluster and is not something a Spring application does on its own.

Do not change the broker authorizer to fix a single DLT WRITE error. Identify the missing principal and ACL first. Superuser privileges should also be tightly restricted, audited, and never used as runtime principals for business services.

## 23. Principal Mapping and Why Matching-Named ACLs Still Get Denied

An ACL might be granted for User:orders-service, yet the broker sees a different principal, such as a username with a prefix/suffix or a distinguished name from a certificate.

Points to check:

- Actual SASL mechanism and username.
- Whether JAAS configuration is loaded from the right environment.
- TLS client certificate subject and principal builder/mapping.
- Which authenticated principal broker logs record.
- Whether the client uses a different ProducerFactory/KafkaTemplate than expected.
- Whether the DLT producer uses the same credentials as the source consumer.
- Whether a matching DENY ACL or host restriction exists.

Do not log passwords, JAAS strings, or private keys to investigate principal mismatches. Logging authenticated principals may itself need protection as security metadata.

A common bug is the source consumer factory using credentials A while the DLT KafkaTemplate is built from producer factory B with different credentials. Source READ succeeds, while DLT WRITE is denied. Inspect the actual configs of both consumer and producer factories.

## 24. Spring Boot Can Use Shared or Separate Security Configurations

If the source consumer and DLT producer share the same principal, Spring Boot can share Kafka properties across consumer/producer. If separating principals, configure a dedicated ProducerFactory for the DLT.

~~~java
@Bean
ProducerFactory<Object, Object> dltProducerFactory(
        KafkaProperties kafkaProperties) {

    Map<String, Object> properties =
            new HashMap<>(kafkaProperties.buildProducerProperties());

    properties.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            "kafka-1.example.net:9093"
    );

    // DLT publisher credentials are injected from secret configuration.
    // Do not hard-code username/password here.

    return new DefaultKafkaProducerFactory<>(properties);
}

@Bean
KafkaTemplate<Object, Object> dltKafkaTemplate(
        ProducerFactory<Object, Object> dltProducerFactory) {

    return new KafkaTemplate<>(dltProducerFactory);
}
~~~

This snippet illustrates a separate factory; exact property extraction depends on the Spring Boot version. In production, construct the properties map from a dedicated security binding for the DLT principal to avoid accidentally inheriting wrong credentials or serializers.

If the DLT publisher uses a different KafkaTemplate, make sure DeadLetterPublishingRecoverer receives that exact bean. Having a bean named dltKafkaTemplate does not mean the recoverer uses it automatically if constructor/wiring selects another template.

Verify key serializer, value serializer/raw bytes serializer, security protocol, SASL mechanism, JAAS credentials, transactional ID prefix if using transactions, and Observation if needed.

## 25. ACLs for DLT Raw Bytes and Deserialization Failures

A record failing deserialization may be exported by the recoverer to the DLT as raw byte[] along with exception headers. The DLT publisher still needs the same WRITE ACL as other DLT records, and the producer serializer must support the actual payload type.

~~~text
orders.events
     |
     v
Deserializer failure
     |
     v
ErrorHandlingDeserializer
     |
     +--> raw bytes + error metadata
     |
     v
DeadLetterPublishingRecoverer
     |
     v
KafkaTemplate
     |
     v
orders.events.DLT
~~~

If KafkaTemplate only serializes OrderCreated while the DLT record value is byte[], sending can fail at serialization before the broker ever evaluates ACLs. Do not conclude every send failure is an authorization error.

A DLT topic may carry both domain objects and raw bytes depending on recovery paths. Configure compatible serializers or multiple templates as needed. A WRITE ACL only resolves broker permissions; it does not fix serializers.

## 26. What Happens When a DLT Publish Hits TopicAuthorizationException?

A failure path:

~~~text
Source record fails
      |
      v
DefaultErrorHandler
      |
      v
DeadLetterPublishingRecoverer
      |
      v
KafkaTemplate.send(DLT)
      |
      v
Broker checks ACL
      |
      +--> WRITE is DENIED
                |
                v
       TopicAuthorizationException
                |
                v
       Recoverer reports send failure
                |
                v
       Error handler/container handles recovery failure
~~~

When the DLT publisher lacks WRITE:

- The source record is not stored in the DLT.
- The recoverer must surface the publish failure.
- The source offset must not be treated as successfully recovered.
- The record may continue to be redelivered per error handling/offset policy.
- Infinite repetition can trigger an incident and consumer stall.
- Immediate alerting is needed because the recovery path is broken.

Check your Spring Kafka version's behavior and send-result policy configuration. On supported versions, enable fail-if-send-result-is-error so send errors are surfaced rather than merely logged. Do not swallow TopicAuthorizationException and return normally from a custom recoverer.

## 27. Avoiding Infinite Retry Loops When DLT ACLs Are Wrong

A poison pill record can fail repeatedly. The error handler tries to send the record to the DLT, but the publisher lacks WRITE permission. If recovery failures loop without alerting, the partition can stay pinned on that record and subsequent records stall per policy.

A runbook should:

1. Classify the original record error.
2. Distinguish the original error from the DLT publish authorization failure.
3. Check the producer's principal.
4. List ACLs on the destination topic.
5. Check DENY rules, host restrictions, and resource patterns.
6. Grant the right WRITE ACL via the admin workflow.
7. Confirm the producer can publish to the DLT.
8. Confirm the source record recovers per policy.
9. Monitor lag and delivery counts.
10. Do not seek/skip the source offset just to unblock the partition without a business decision.

If the original error is validation while recovery fails due to ACLs, preserve both causes in logs/alerts. Do not log only the final exception and lose the original failure reason.

## 28. Auditing, Rotation, and Revoking ACLs

ACLs are part of the security lifecycle, not a one-time setup to forget.

Maintain:

- Owner of each principal.
- Justification for each ACL grant.
- Specific resource/pattern.
- Grant date and review cadence.
- Credential rotation procedure.
- Permission revocation procedure when a service is decommissioned.
- Audit logs of admin changes.
- Desired ACL state in infrastructure-as-code or provisioning repos.
- Drift checks between desired ACLs and actual ACLs.

When a service is decommissioned, remove the old principal's ACLs after confirming no workloads still use them. Do not revoke DLT publisher permissions mid-recovery without a plan, as failed records may not be safely transferred.

If credentials must be rotated:

1. Create new principal/credentials.
2. Grant corresponding least-privilege ACLs.
3. Update service secrets/config.
4. Verify authentication and publish/consume tests.
5. Shift traffic.
6. Revoke old principal after ensuring no clients still use it.

Do not record secrets in audit tickets or structured logs.

## 29. Pre-Deployment ACL Verification

A pre-production procedure can verify operations using real runtime principals:

| Check | Principal | Expected Outcome |
|---|---|---|
| Consume source topic | source consumer | Allowed |
| Join source group | source consumer | Allowed |
| Publish DLT | DLT publisher | Allowed |
| Consume DLT | DLT investigator | Allowed |
| Join DLT group | DLT investigator | Allowed |
| Publish source topic from investigator | DLT investigator | Denied if read-only |
| Delete DLT topic from runtime principal | service principal | Denied |
| Publish to topic outside allowlist | DLT publisher | Denied |
| Publish DLT with raw byte[] | DLT publisher | Allowed if serializer matches |
| DLT send when topic unavailable | DLT publisher | Recovery failure surfaced |

A smoke test publishing a synthetic record to the DLT can verify WRITE permission. Use dedicated test topics/environments and do not inject real production data merely to test ACLs.

Do not test only with an admin principal. Admins can bypass ACLs, yielding false passes while runtime principals remain denied.

## 30. Observability for ACL Failures

Separate logs and metrics should exist for authorization failures:

| Signal | Purpose |
|---|---|
| DLT publish attempts | How many times the recoverer invoked the producer |
| DLT publish success/failure | How many sends succeeded/failed |
| TopicAuthorizationException count | Missing topic permission |
| GroupAuthorizationException count | Missing consumer group permission |
| TransactionalIdAuthorizationException count | Missing transaction permission |
| AuthenticationException count | Authentication errors |
| DLT oldest record age | DLT backlog needing investigation |
| Source consumer lag | Whether source partitions are stuck |
| Recovery failure rate | Error handler unable to complete recovery |
| Principal/resource denied logs | Finding ACL mismatches |

Structured log should record:

~~~json
{
  "level": "ERROR",
  "event": "kafka_dlt_publish_failed",
  "principal": "User:orders-service",
  "source_topic": "orders.events",
  "source_partition": 2,
  "source_offset": 105,
  "destination_topic": "orders.events.DLT",
  "exception_type": "TopicAuthorizationException",
  "recovery_outcome": "failed"
}
~~~

This example contains no credentials or raw payloads. Log the authenticated principal only if logging policy permits. Metric labels should have low cardinality; do not use offsets, eventIds, or arbitrary raw principals as labels.

## 31. ACL Checklists by Flow Type

### Flow where source consumer and DLT publisher share a principal

- READ source topic.
- READ source consumer group.
- WRITE on each DLT destination.
- Transactional ID/cluster permissions if the producer actually uses transactions/idempotent authorization per broker policy.
- No unnecessary DELETE/ALTER permissions.

### Flow with separate DLT publisher principal

- Source consumer has only source READ and group READ.
- DLT publisher has only WRITE on DLT destinations.
- DLT KafkaTemplate uses the right producer credentials.
- Serializer supports required domain objects/raw bytes.
- DLT send failures are surfaced.
- Separate credentials are rotated/audited.

### DLT investigator

- READ DLT.
- READ separate group.
- No WRITE if read-only investigation.
- Quarantine storage has access controls.
- Do not log sensitive raw payloads.

### Replay operator

- READ DLT and appropriate group.
- WRITE to exact replay/source destination.
- Audit and approval in place.
- Idempotency and side effects reviewed before replay.
- No cluster-wide admin permissions granted.

## 32. Common Mistakes

**Granting READ on source topic and assuming the DLT publisher can also write to the DLT**

No. WRITE on the destination topic is a separate permission.

**Granting ALL cluster-wide to fix TopicAuthorizationException**

This over-provisions privileges and hides which principal/resource is wrong. Identify the exact topic and operation.

**Using an admin principal in the application**

Admins can bypass ACLs and defeat least privilege. Runtime must use dedicated principals.

**Forgetting the consumer group ACL**

Consumer has topic READ but cannot join the group. READ is required on the exact Group resource.

**Forgetting retry topics**

Non-blocking retry publishing can fail before records ever reach the DLT. Provision and grant ACLs across the entire retry topology.

**Not pre-creating the DLT topic**

Producers can hit missing-topic or authorization errors if auto-create is disabled. Provision topics via pipeline.

**Resolver picking a destination different from the ACL**

An exception routing branch may send to a topic lacking WRITE permission. Audit all resolver mappings.

**Logging success immediately after KafkaTemplate.send**

Calling send is not broker acknowledgment. Check future/recoverer send-result semantics.

**Swallowing TopicAuthorizationException**

The container may treat recovery as complete even though the record is not in the DLT. Let recovery failures surface and keep source records safe.

**Granting DLT WRITE to every investigator**

Reading the DLT does not mean permission to publish/replay. Separate roles.

**Confusing SASL authentication with ACL authorization**

Valid credentials only establish the principal; the broker can still deny operations.

**Assuming Kafka transactions solve DLT permissions**

Transactions do not bypass ACLs. The producer still needs matching topic and transactional ID permissions.

## 33. Runbook When DLT Publish Is Denied

When alerts indicate TopicAuthorizationException:

1. Extract source topic, partition, offset, and destination topic from structured logs.
2. Identify which KafkaTemplate/ProducerFactory actually sends to the DLT.
3. Identify the principal the broker authenticated for that producer.
4. Use an admin identity to list ACLs on the DLT destination.
5. Check literal/prefixed patterns, host restrictions, and DENY entries.
6. Grant WRITE to the exact principal on the exact DLT topic via the change process.
7. If using transactions, check transactional ID ACLs and cluster idempotent permissions per configuration.
8. Confirm the DLT topic exists and the partition resolver is valid.
9. Run a smoke test using the runtime principal.
10. Monitor DLT send results and source offset recovery.
11. Check source lag, retry counts, and DLT ingress.
12. Confirm records are reprocessed strictly per policy without manual out-of-process seek/skip.
13. Record audit details for the ACL change and incident closure.

If the exception is GroupAuthorizationException, investigate the consumer group of the DLT listener or source listener. If AuthenticationException, fix credentials/TLS/SASL first; adding ACLs does not resolve authentication failures.

## 34. Production Checklist for DLT ACLs

- Identify the actual principal seen by brokers.
- Separate source consumer, DLT publisher, DLT investigator, and replay operator per least privilege.
- Source consumer has READ on exact source topics.
- Consumer group has READ on exact Group resource.
- DLT publisher has WRITE on each exact destination topic.
- DLT consumer has READ on DLT and its group.
- Retry topics have ACLs matching the actual topology.
- DLT topics are pre-provisioned.
- Partition counts match the destination resolver.
- Retention, replication, and min.insync.replicas match durability requirements.
- No CREATE/DELETE/ALTER granted to runtime principals unless needed.
- Never use cluster-wide ALL to fix a single-topic error.
- Use prefixed ACLs only where namespace ownership is clear.
- Check both DENY entries and principal mapping.
- Keep SASL/TLS authentication separate from authorization.
- Grant TransactionalId and IDEMPOTENT_WRITE only when producer configuration requires them.
- DLT KafkaTemplate uses the right principal and serializers.
- Recoverer surfaces send failures per policy.
- Source offsets are not treated as recovered if DLT sends fail.
- Structured logs retain source/destination coordinates and error categories.
- Metrics alert on authorization/recovery failures.
- ACL changes are audited and reviewed periodically.
- Credentials are stored in a secret manager with rotation.
- Smoke tested with runtime principals, not admin principals.
- Replay operators have separate permissions and an idempotency policy.

**Conclusion:** DLT ACLs are part of the recovery path, not an optional afterthought once the listener runs. The source consumer needs READ on source topics and group; the DLT publisher needs WRITE on exact DLT destinations; the DLT consumer needs READ on the DLT and its group. When retry topics or Kafka transactions are involved, ACLs must extend to those exact resources as well. Pre-provision topics, verify the principal authenticated by brokers, uphold least privilege, and ensure DLT send failures surface. A record is considered safely recovered only when **DLT publication has been confirmed per policy**, not merely because the recoverer invoked KafkaTemplate.send.

