# Using Pre-Created Topics and Managing Resource Permissions

In production environments, Kafka topics are usually created and managed in advance by a platform team or Kafka administrators. The Spring Cloud Stream application simply connects to existing topics, reading or writing data according to granted permissions. This deployment model helps control partition count, replication factor, retention, cleanup policy, and access rights according to organizational operational procedures.

The Kafka binder can automatically create topics or add partitions in some configurations. When you want to use existing topics, disable the corresponding provisioning features in the binder, confirm the topic already has enough partitions, and then grant proper ACLs to the application's runtime principal. Permissions to create topics, alter configurations, and manage ACLs should belong to a dedicated administrative principal; the application's runtime principal should only have read or write permissions on the exact resources it needs.

## 1. Topics Are Pre-Governed Resources

The Spring Cloud Stream Kafka binder maps each destination to a Kafka topic. A binding's consumer group maps to a Kafka consumer group; binder partitioning maps directly to topic partitions.

Example:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
        processOrder-out-0:
          destination: orders.accepted
~~~

In this example:

- **orders.submitted** is the existing topic read by the input binding.
- **order-service** is the consumer group storing the application's read offsets.
- **orders.accepted** is the existing topic written to by the output binding.
- **processOrder-in-0** and **processOrder-out-0** are logical binding names inside the application.

The destination must match the exact topic name created on the cluster. Setting a group does not create a new topic; it defines the consumer group identity. If `group` is omitted, the binding uses an anonymous consumer group; instances may receive independent streams rather than sharing load within a named group. Set an explicit group when replicas of a service must share processing and offset positions.

## 2. Disabling Kafka Binder Topic Provisioning

The Kafka binder has two important properties:

| Property | When Enabled | When Disabled |
|---|---|---|
| `autoCreateTopics` | Binder creates topics when needed | Binder requires topics to already exist; if missing, binding initialization fails |
| `autoAddPartitions` | Binder can add partitions when the current count is below the required level | Binder requires existing topics to have enough partitions; if insufficient, binding initialization fails |

To use only pre-provisioned topics:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          brokers: ${KAFKA_BOOTSTRAP_SERVERS}
          autoCreateTopics: false
          autoAddPartitions: false
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
        processOrder-out-0:
          destination: orders.accepted
~~~

Both properties are set at the Kafka binder level, not under an individual binding. When `autoCreateTopics` is `false`, a missing topic causes the binder to fail binding initialization. When `autoAddPartitions` is `false`, the binder does not automatically increase partitions if the topic has fewer than requested by producer or partitioning settings.

The default values in current binder documentation are `autoCreateTopics=true` and `autoAddPartitions=false`. Explicitly declare both in environments requiring centralized topic governance so deployment intent does not depend on version defaults.

### 2.1. Distinguishing Binder Configuration from Broker Configuration

Spring Cloud Stream binder's `autoCreateTopics` is independent of Kafka broker's `auto.create.topics.enable`. Disabling auto-create on the binder does not automatically turn off the broker's ability to auto-create a topic when a client sends a metadata request for a non-existent topic name.

If operational requirements dictate that topics may only be created via an administrative process, administrators should inspect broker configuration and consider disabling:

~~~properties
auto.create.topics.enable=false
~~~

These two layers serve different purposes:

- `spring.cloud.stream.kafka.binder.autoCreateTopics=false` prevents the binder from proactively creating topics via its provisioning mechanism.
- `auto.create.topics.enable=false` prevents the broker from auto-creating topics upon client metadata requests.

In a shared cluster, do not assume an application is blocked from creating topics just because the binder sets `autoCreateTopics=false`. Check broker policies and the runtime principal's ACLs.

## 3. Preparing Topics Before Application Deployment

Administrators must agree on the topic name, partition count, replication factor, and data retention configuration before granting permissions to the application. These values directly affect ordering, throughput, durability, and storage capacity.

| Topic Property | Questions to Decide |
|---|---|
| Topic name | Does it follow domain, environment, and ownership conventions? |
| Partition count | How much parallelism is needed, and is it enough for consumer concurrency? |
| Replication factor | How many copies are needed, and does the cluster have enough brokers? |
| `min.insync.replicas` | When producers use `acks=all`, what is the minimum number of in-sync replicas required? |
| `retention.ms` / `retention.bytes` | How long or how much data should be retained? |
| `cleanup.policy` | Should `delete`, `compact`, or both be used based on the data's purpose? |
| `max.message.bytes` | Does the maximum message size fit actual payloads? |

Example of an order-events topic with six partitions, replication factor three, and seven-day data retention:

~~~bash
kafka-topics.sh --bootstrap-server kafka-1:9092,kafka-2:9092 \
  --command-config /etc/kafka/admin-client.properties \
  --create --if-not-exists \
  --topic orders.submitted \
  --partitions 6 \
  --replication-factor 3 \
  --config retention.ms=604800000 \
  --config min.insync.replicas=2
~~~

This is an example administrative command. The `admin-client.properties` path should point to a security configuration file for an administrative principal and be protected according to organizational policy. Never put real passwords on the command line or store credential files in a repository.

Existing topics do not need to be re-created. For existing topics, inspect current configuration and only make changes through the cluster's change management process. Do not run topic creation or modification commands from an application deployment pipeline if that pipeline only has runtime permissions.

## 4. Verifying Existing Topic Partitions and Configuration

Before starting the application, use Kafka tools to verify the topic exists:

~~~bash
kafka-topics.sh --bootstrap-server kafka-1:9092 \
  --command-config /etc/kafka/admin-client.properties \
  --describe --topic orders.submitted
~~~

The topic description reports partition count, leader, replicas, and ISR (in-sync replicas). Verify that every partition has a leader and that the replication assignment satisfies cluster policy.

Read topic configuration:

~~~bash
kafka-configs.sh --bootstrap-server kafka-1:9092 \
  --command-config /etc/kafka/admin-client.properties \
  --describe --entity-type topics --entity-name orders.submitted
~~~

Check existing ACLs:

~~~bash
kafka-acls.sh --bootstrap-server kafka-1:9092 \
  --command-config /etc/kafka/admin-client.properties \
  --list --topic orders.submitted
~~~

After the application is running, inspect the group and offsets:

~~~bash
kafka-consumer-groups.sh --bootstrap-server kafka-1:9092 \
  --command-config /etc/kafka/admin-client.properties \
  --describe --group order-service
~~~

The commands above require appropriate describe permissions. If the principal is not allowed to view configs, ACLs, or consumer groups, the tools may return an authorization error even though the topic exists and the application can read or write data.

## 5. Ensuring Partition Count Compatibility with Bindings

When a producer uses partitioning, the binder needs to know the target partition count. Example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-out-0:
          destination: orders.accepted
          producer:
            partition-key-expression: payload.customerId
            partition-count: 6
~~~

For an existing topic, the actual partition count must satisfy the producer configuration. If `partition-count` requests six while the topic only has four partitions and `autoAddPartitions=false`, the binder may refuse to initialize the binding instead of modifying the topic.

`minPartitionCount` only takes effect when `autoCreateTopics` or `autoAddPartitions` is enabled. When both are disabled, do not expect `minPartitionCount` to adjust an existing topic.

For producers not using explicit partitioning, check other settings that can raise the expected partition count, such as `instanceCount * concurrency` in the case of a partitioned producer. Application configuration and topic configuration must be aligned before deployment.

Do not reduce a topic's partition count as a routine adjustment. Kafka does not support reducing partition count safely the way it supports increasing partitions; increasing partitions can also alter how hashed keys map to partitions and affect relative ordering for the same key. Decide partition counts intentionally from the outset.

## 6. Separating Administrative and Runtime Permissions

Separate principals should be used for distinct duties:

| Principal | Responsibility | Typical Permissions |
|---|---|---|
| `kafka-platform-admin` | Create topics, modify partitions/configs, manage ACLs | Create/Alter/Describe on managed resources; ACL permissions per cluster policy |
| `order-producer` | Publish events to output topics | Write and Describe on output topics |
| `order-consumer` | Read input topics and commit offsets | Read and Describe on input topics; Read on the corresponding consumer group |
| `order-observer` | Read operational telemetry | Describe or DescribeConfigs on permitted resources |

Runtime principals should not have cluster-wide `Create`, topic `Delete`, or `AlterConfigs` permissions unless the application has administrative duties. Separating permissions limits blast radius if application credentials are compromised and simplifies auditing.

If an application only reads `orders.submitted` and writes `orders.accepted`, the principal can be granted:

- `Read`/`Describe` on `orders.submitted`.
- `Read` on group `order-service`.
- `Write`/`Describe` on `orders.accepted`.

Do not grant read access to all topics or write access to all topics just to avoid authorization errors during deployment.

## 7. Commonly Used Kafka ACLs

Kafka ACLs apply to different resource types. Common resources when using the binder include:

| Resource | Example | Purpose |
|---|---|---|
| `Topic` | `orders.submitted` | Read or write records and query metadata |
| `Group` | `order-service` | Join a consumer group and manage offsets |
| `Cluster` | Current cluster | Certain administrative operations or idempotent producers |
| `TransactionalId` | Producer transaction prefix | Send and commit Kafka transactions |

Common operations:

| Operation | Meaning |
|---|---|
| `Read` | Read topic, join group, or read offsets depending on resource |
| `Write` | Write records or perform transaction operations depending on resource |
| `Create` | Create a resource |
| `Alter` | Modify a resource or ACL depending on context |
| `Describe` | Read basic metadata |
| `DescribeConfigs` | Read resource configurations |
| `AlterConfigs` | Modify resource configurations |
| `IdempotentWrite` | Allow idempotent producers at the cluster level |

For a standard producer, producing requires `Write` on the topic; metadata lookup requires `Describe` on the topic. For a consumer group, consumers need appropriate permissions on the topic and group to read records, join the group, and commit/fetch offsets.

When idempotence is enabled, Kafka may require `IdempotentWrite` on the cluster. When using a transactional producer, `Write` permission is also needed on the corresponding `TransactionalId` resource; transaction operations may require permissions on related topics and groups. Base ACL grants on the actual Kafka APIs used by the application and the broker version's authorization matrix.

## 8. Granting ACLs for Producers and Consumers

Example granting minimal producer permissions on a topic:

~~~bash
kafka-acls.sh --bootstrap-server kafka-1:9092 \
  --command-config /etc/kafka/admin-client.properties \
  --add --allow-principal User:order-producer \
  --operation Write --operation Describe \
  --topic orders.accepted
~~~

Example granting consumer permissions on an input topic:

~~~bash
kafka-acls.sh --bootstrap-server kafka-1:9092 \
  --command-config /etc/kafka/admin-client.properties \
  --add --allow-principal User:order-consumer \
  --operation Read --operation Describe \
  --topic orders.submitted
~~~

Granting permissions for the consumer group:

~~~bash
kafka-acls.sh --bootstrap-server kafka-1:9092 \
  --command-config /etc/kafka/admin-client.properties \
  --add --allow-principal User:order-consumer \
  --operation Read \
  --group order-service
~~~

If the application or operational tools need to call APIs that describe the consumer group, `Describe` on the group resource may also be needed:

~~~bash
kafka-acls.sh --bootstrap-server kafka-1:9092 \
  --command-config /etc/kafka/admin-client.properties \
  --add --allow-principal User:order-consumer \
  --operation Describe \
  --group order-service
~~~

These examples use literal ACLs on individual resources. Prefix resource patterns can be used when many topics follow a naming convention, but prefixes should remain narrowly scoped. Inspect existing ACLs before adding new ones to avoid allow/deny conflicts or overly broad permissions.

The Kafka CLI includes convenience flags `--producer` and `--consumer` to generate common ACL sets. These flags may grant extra permissions such as `Create` or `Describe` depending on the role and Kafka version. When enforcing least privilege, explicit `--operation` flags make each granted permission clear.

## 9. Topic and Partition Administrative Permissions

If an application is allowed to auto-create topics, the principal needs `Create` permission on the cluster or topic according to how the broker authorizer checks permissions. If the binder is allowed to add partitions, the principal needs appropriate `Alter` permission on the topic and related metadata permissions.

If an application needs to read topic configurations, the principal may need `DescribeConfigs`. If an application needs to modify retention or cleanup policy, that operation requires configuration-altering permissions such as `AlterConfigs`. Managing ACLs is also a separate administrative action; do not grant `Alter` on the cluster to a runtime application just so it can read/write records.

With pre-created topics, the recommended workflow is:

1. Administrators create topics and configure partitions/replication/configs.
2. Administrators grant ACLs to producer and consumer principals.
3. The application uses its runtime principal to connect to existing topics.
4. The binder verifies topics and metadata without creating topics or adding partitions.
5. If partitions or configs need changes, execute them through the administrative and change-review process.

Kafka documentation describes `Create`, `Alter`, `DescribeConfigs`, and `AlterConfigs` operations on separate resources. Exact permissions may vary by broker version, authorizer, and the APIs invoked by the client; inspect actual authorization errors and the cluster's permission matrix.

## 10. Configuring Authentication and Encrypted Connections

ACLs determine which operations a principal can perform after authentication. To authenticate clients, Kafka typically uses SASL or TLS client certificates; to encrypt traffic in transit, it uses SSL/TLS.

Example binder configuration with SASL/SCRAM over TLS:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          brokers: ${KAFKA_BOOTSTRAP_SERVERS}
          autoCreateTopics: false
          autoAddPartitions: false
          configuration:
            security.protocol: SASL_SSL
            sasl.mechanism: SCRAM-SHA-512
            sasl.jaas.config: ${KAFKA_SASL_JAAS_CONFIG}
            ssl.truststore.location: ${KAFKA_TRUSTSTORE_LOCATION}
            ssl.truststore.password: ${KAFKA_TRUSTSTORE_PASSWORD}
~~~

Environment variables must be supplied by a secret manager or deployment system. Never write real usernames/passwords into `application.yml`, source code, logs, or container images. Truststore files and secrets must have restricted read permissions.

`spring.cloud.stream.kafka.binder.configuration` applies shared Kafka client properties to producers and consumers created by the binder. If `AdminClient` needs separate customization, the binder provides `AdminClientConfigCustomizer`; `AdminClient` configuration must align with the cluster's authentication mechanism. Do not assume producer/consumer settings automatically satisfy all authentication or administrative permission requirements.

In multi-cluster environments, each binder may need its own broker list and JAAS/SASL configuration. Use multi-binder configuration and assign a binder to each binding instead of sharing credentials or pointing to the wrong cluster's bootstrap servers.

## 11. Verifying Permissions and Authorization Errors

An application can authenticate successfully yet still be denied access to a topic or group. Distinguish authentication failures from authorization failures:

| Error or Symptom | Possible Cause | Where to Check |
|---|---|---|
| Authentication failed | Wrong username/password, SASL mechanism, or TLS certificate | Secrets, JAAS config, truststore, and broker logs |
| `TOPIC_AUTHORIZATION_FAILED` | Missing `Read`, `Write`, `Describe`, or corresponding topic permission | Topic ACLs |
| `GROUP_AUTHORIZATION_FAILED` | Missing `Read`/`Describe` permission on consumer group | Group ACLs |
| `CLUSTER_AUTHORIZATION_FAILED` | Missing cluster permission for the required operation | Cluster ACLs and API being called |
| Topic does not exist | Topic not provisioned or wrong destination name | `kafka-topics --describe` |
| Binder fails to start due to partitions | Topic has fewer partitions than required by configuration | `partition-count`, `instanceCount`, `concurrency`, and actual partitions |
| Metadata request creates unintended topic | Broker has auto topic creation enabled | `auto.create.topics.enable` and broker policy |

When troubleshooting errors, check the actual principal received by the broker, not just the secret name in a config file. With SASL, principals are often mapped from authenticated identities; ACLs must be granted to that exact principal.

Do not grant `All` on the cluster just to make the application start. Identify which API was denied, which resource was checked, and add only the minimal operation required.

## 12. Deploying Across Environments

Development, staging, and production environments typically have different topics and permissions. You can use the same configuration structure while sourcing brokers, topic names, and groups from environment variables:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: ${ORDERS_INPUT_TOPIC}
          group: ${ORDERS_CONSUMER_GROUP}
        processOrder-out-0:
          destination: ${ORDERS_OUTPUT_TOPIC}
      kafka:
        binder:
          brokers: ${KAFKA_BOOTSTRAP_SERVERS}
          autoCreateTopics: false
          autoAddPartitions: false
~~~

Topic and group names should be declared explicitly per environment. Never share the same consumer group across two environments if they require independent offsets. If two environments share a cluster and use the same group, they can split partitions between them and cause unexpected behavior.

Deployment pipelines should verify:

- Topics already exist in the right cluster.
- Partition counts match producer/consumer configuration.
- Replication factor and ISR policy suit the environment.
- ACLs are granted to the application's principal.
- The runtime principal does not hold unnecessary administrative permissions.
- The binder disables auto-create and auto-add-partitions per policy.
- Broker auto topic creation is configured according to cluster policy.

## 13. Troubleshooting When a Topic Exists but the Binding Fails to Start

Check in order:

1. Confirm `destination` matches the exact topic name.
2. Run `kafka-topics --describe` to confirm the topic exists and has leaders.
3. Compare actual partition count against `partition-count`, `minPartitionCount`, and partitioning requirements.
4. Confirm `autoCreateTopics=false` and `autoAddPartitions=false` if the application only uses pre-existing resources.
5. Confirm the broker does not auto-create topics outside policy if prohibited.
6. Check `security.protocol`, SASL mechanism, JAAS, and TLS truststore.
7. Identify the actual principal in broker logs or admin tools.
8. Inspect ACLs on the topic and group using `kafka-acls --list`.
9. If the error involves `AdminClient`, check `Describe` permissions and separate `AdminClient` configuration.
10. Restart the binding after an administrator fixes the topic or ACLs, then verify consumer group/producer activity.

Do not re-enable auto-create or grant broad admin permissions as a first troubleshooting step. Those actions can mask the real root cause and create non-compliant resources.

## 14. Production Handover Checklist

- [ ] Input/output topics are pre-created through the administrative process.
- [ ] Destination names match actual topic names.
- [ ] Partition counts meet producer and consumer requirements.
- [ ] Replication factor, `min.insync.replicas`, and retention are agreed upon.
- [ ] `autoCreateTopics=false` and `autoAddPartitions=false` are explicitly declared.
- [ ] Broker auto topic creation is reviewed against cluster policy.
- [ ] Runtime principal is separated from administrative principals.
- [ ] Producers only have `Write`/`Describe` on required output topics.
- [ ] Consumers have `Read`/`Describe` on input topics and appropriate group permissions.
- [ ] `TransactionalId`/`IdempotentWrite` ACLs are granted if the application actually uses transactions/idempotence.
- [ ] Connections use appropriate SASL/TLS and secrets are kept out of source control.
- [ ] `AdminClient` has the permissions needed for metadata/provisioning operations performed by the binder.
- [ ] Topics, ACLs, groups, offsets, and logs are verified after deployment.

## Official References

- [Spring Cloud Stream - Kafka Binder Overview](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/overview.html): mapping destinations, consumer groups, and partitions to Kafka.
- [Spring Cloud Stream - Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html): `autoCreateTopics`, `autoAddPartitions`, `minPartitionCount`, `replicationFactor`, and client settings.
- [Spring Cloud Stream - Kafka Binder Security Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/security-config.html): SASL, TLS, JAAS, and recommendations for topic/ACL governance in secure environments.
- [Spring Cloud Stream - Customizing AdminClient Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/admin-client-config-cust.html): customizing the `AdminClient` configuration used by the binder.
- [Apache Kafka - Authorization and ACLs](https://kafka.apache.org/40/security/authorization-and-acls/): resources, operations, and ACLs for producers, consumers, groups, clusters, and transactional IDs.
