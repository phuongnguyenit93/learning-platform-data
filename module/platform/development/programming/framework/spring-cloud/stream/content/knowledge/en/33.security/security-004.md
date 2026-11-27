# Least-Privilege Authorization for Producing, Consuming, and Provisioning Resources

A Spring Cloud Stream application typically performs three distinct groups of operations against a broker:

1. **Producing messages:** writing events to a topic, exchange, or destination.
2. **Consuming messages:** reading events from a topic, queue, or subscription and acknowledging processing.
3. **Provisioning resources:** creating topics, partitions, exchanges, queues, subscriptions, bindings, schemas, or modifying broker configurations.

These three groups of operations do not require the same privilege level. Business runtime applications typically only need produce or consume permissions on specific destinations. Creating, deleting, altering partitions, configuring retention, or granting permissions to other roles belong to infrastructure administration tasks.

**Least privilege** means granting each identity only the exact operations and resources needed to accomplish its task, in the right environment and for the required duration. When a credential is compromised, the blast radius is thereby limited.

This lesson applies that principle to the Kafka, RabbitMQ, and Pulsar binders of Spring Cloud Stream. It covers separating producer, consumer, and provisioner identities, concrete ACLs, authentication setup in Spring Boot, permission auditing, and secure credential operations.

## 1. Authentication and Authorization Are Two Separate Things

**Authentication** answers the question: who is the client? The broker verifies identity via username/password, SASL, certificates, tokens, or configured mechanisms.

**Authorization** answers the question: what is that identity allowed to do on which resources? The broker checks permissions when the client publishes, consumes, creates a topic, declares a queue, or performs administrative operations.

~~~text
Spring Cloud Stream application
       |
       | 1. Authentication
       |    "I am orders-projection-prod"
       v
Broker verifies identity
       |
       | 2. Authorization
       |    "Does this role have READ on orders.created
       |     and READ on group order-projection-v1?"
       v
Allow or deny operation
~~~

Having valid credentials does not mean having permission to read or write every topic. Conversely, declaring an ACL for a principal does not allow a client to connect if authentication fails.

A configuration that enables authentication without enabling authorization can still grant authenticated principals broader access than intended. For example, Kafka documentation notes that without an authorizer configured, authenticated principals may have full access. Pulsar also warns that enabling authentication alone may allow authenticated roles to access all resources if authorization is not enabled.

Therefore, when designing security, check both layers: whether the broker properly identifies the service account and whether the authorizer restricts operations on resources.

## 2. Separating Identities by Role

Do not use a shared administrative account for all applications. Every service, environment, and task should have its own identity.

Example order-processing system:

| Identity | Responsibility | Required Permissions |
|---|---|---|
| `orders-api-prod` | Produce `orders.created` | Publish to the output topic/exchange |
| `orders-projection-prod` | Consume `orders.created` | Consume the topic/queue and use its own consumer group/subscription |
| `billing-prod` | Consume events for billing | Consume the same destination via its own group/subscription |
| `stream-provisioner-prod` | Create topics, queues, exchanges, and policies | Administrative permissions on the exact namespaces/vhosts/resources to provision |
| `stream-monitor-prod` | Read metadata and operational metrics | Necessary observability permissions; no default payload read access |
| `schema-publisher-prod` | Register schemas if using a schema registry | Schema write permissions for assigned subjects/packages |

If a service both consumes and produces messages, it may need both consume permission on inputs and publish permission on outputs. Even then, the combined permissions apply only to the specified resources.

Separating identities by environment:

~~~text
orders-api-dev       != orders-api-staging
                    != orders-api-prod

orders-projection    != billing
                    != stream-provisioner
~~~

Do not include hostnames, pod names, or instance IDs in the identity of individual replicas if the replicas must perform the same task together. Use a stable service identity for the workload and let the broker/binder coordinate the consumer group or subscription.

## 3. Operation-Based Permission Matrix

Before creating ACLs, list the exact operations that bindings need to perform.

| Operation | Producer | Consumer | Provisioner |
|---|---:|---:|---:|
| Connect and authenticate | Yes | Yes | Yes |
| Publish to destination | Yes | Only if also producing events | Only if needed for testing |
| Read/consume destination | No | Yes | No |
| Join consumer group or subscription | No | Yes | No |
| Create topic/partition | No | No | Yes |
| Create exchange/queue/binding | No | No | Yes |
| Create namespace or tenant | No | No | Yes |
| Modify retention, quota, or policy | No | No | Yes when delegated |
| Grant/revoke permissions for other roles | No | No | Designated admins only |
| Delete resources | No | No | Approved administrative workflows only |

This table is a separation-of-duties model, not an identical ACL list across every broker. Each broker expresses permissions differently; subsequent sections map these operations to Kafka, RabbitMQ, and Pulsar.

A consume-only application should not have permission to publish to its input topic. A producer does not need permission to join a consumer group. Neither needs permission to create tenants, delete queues, or modify broker settings.

## 4. Distinguishing Runtime Role and Provisioning Role

The binder can auto-create resources when the application starts. That is convenient in development, but can unintentionally force the runtime service account to require administrative permissions.

Production architectures should separate:

~~~text
Pipeline / Platform administrator
          |
          | Provisioning identity
          v
Create topics, exchanges, queues,
partitions, subscriptions and policies
          |
          v
Broker resources already exist
          |
          +------------------------------+
          |                              |
          v                              v
Producer runtime identity        Consumer runtime identity
WRITE only on output             READ only on input
          |                              |
          v                              v
Publish event                    Consume and acknowledge
~~~

Deployment workflow:

1. The platform or pipeline creates resources before deploying the service.
2. Administrators grant ACLs to producer/consumer roles.
3. The application retrieves runtime credentials from a secret store.
4. The binder connects to existing resources and performs only the business operations.
5. When topology changes, the administrative pipeline updates resources and ACLs in a versioned manner.

Do not grant `CREATE`, `ALTER`, `DELETE`, `configure`, or tenant-admin permissions merely because the binder tries to declare resources on startup. Inspect what the binder is provisioning and move that step to an administrative workflow if possible.

## 5. Resource Naming and Permission Scoping

Resource names should reflect domain, environment, and function so ACLs can scope precisely.

Examples:

| Resource | Suggested Name |
|---|---|
| Kafka topic | `orders.created.v1` |
| Kafka consumer group | `orders-projection-prod-v1` |
| RabbitMQ vhost | `orders-prod` |
| Rabbit exchange | `orders.created` |
| Rabbit queue | `orders.created.orders-projection` |
| Pulsar namespace | `acme/orders-prod` |
| Pulsar topic | `persistent://acme/orders-prod/orders-created-v1` |
| Pulsar subscription | `orders-projection-prod-v1` |

Avoid wildcard permissions like `*`, `.*`, or `All` across the entire cluster/vhost/tenant for runtime services. Wildcards may make sense for a controlled platform administrator, but never as a default for business applications.

Also scope:

- Environment: dev, staging, production.
- Domain: orders, billing, inventory.
- Data direction: input and output.
- Consumer group/subscription: exact workload identity.
- Auxiliary resources: retry topics, DLT, DLQ, changelog, or repartition topics if the application actually uses them.

## 6. Kafka: Resources and ACLs

Kafka ACLs apply to resource types such as:

- **Topic:** where producers write and consumers read.
- **Group:** consumer group used for coordination and offset storage.
- **Cluster:** cluster-wide operations.
- **TransactionalId:** producer transaction identifier.
- **User/DelegationToken:** certain credential management operations.

Common operations:

| Operation | Meaning |
|---|---|
| `Read` | Read a topic or join a consumer group per the corresponding protocol |
| `Write` | Write to a topic or transaction resource |
| `Create` | Create a topic/resource |
| `Delete` | Delete a resource |
| `Alter` | Modify a resource or partitions |
| `Describe` | Read metadata |
| `DescribeConfigs` | Read configuration |
| `AlterConfigs` | Modify configuration |
| `IdempotentWrite` | Use producer idempotence at the cluster scope |

A Kafka ACL is a combination of principal, host, operation, resource pattern, and allow/deny permission. If the authorizer is configured in default-deny mode, operations without a matching ACL are rejected.

## 7. Kafka: Least-Privilege Permissions for Producers

A typical producer needs:

- `Write` on the destination topic.
- `Describe` on the topic to fetch metadata.
- Additional permissions if using idempotence, transactions, or auto-creating topics.

Example granting permissions to principal `orders-api-prod` to publish only to topic `orders.created.v1`:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka.example:9093 \
  --add \
  --allow-principal User:orders-api-prod \
  --operation Write \
  --topic orders.created.v1

bin/kafka-acls.sh \
  --bootstrap-server kafka.example:9093 \
  --add \
  --allow-principal User:orders-api-prod \
  --operation Describe \
  --topic orders.created.v1
~~~

These two ACLs express permission to write and inspect metadata for a specific topic. They do not grant permission to read the topic, join a group, create topics, or delete topics.

If the producer uses idempotence, Kafka may require the `IdempotentWrite` operation on the Cluster resource depending on client/broker versions and configuration. If the producer uses `transactional.id`, it needs `Write` permission on the `TransactionalId` resource; transactions with offsets may also require permissions on related groups and topics. Add these permissions only when those features are enabled and verified against the actual broker version.

Do not use the `--producer` convenience option without inspecting the permissions it generates. Current Kafka documentation states that this convenience option creates `WRITE`, `DESCRIBE`, and `CREATE` ACLs on the topic. If the topic is pre-provisioned, a runtime producer usually does not need `CREATE`.

## 8. Kafka: Least-Privilege Permissions for Consumers

A typical consumer needs:

- `Read` on the input topic.
- `Describe` on the topic to fetch metadata.
- `Read` on the exact consumer group to join/heartbeat and commit offsets.
- `Describe` on the group if the client/protocol needs to fetch or inspect committed offsets.
- Additional permissions if using transactions or specialized Kafka features.

Example where principal `orders-projection-prod` reads topic `orders.created.v1` with group `orders-projection-prod-v1`:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka.example:9093 \
  --add \
  --allow-principal User:orders-projection-prod \
  --operation Read \
  --topic orders.created.v1

bin/kafka-acls.sh \
  --bootstrap-server kafka.example:9093 \
  --add \
  --allow-principal User:orders-projection-prod \
  --operation Describe \
  --topic orders.created.v1

bin/kafka-acls.sh \
  --bootstrap-server kafka.example:9093 \
  --add \
  --allow-principal User:orders-projection-prod \
  --operation Read \
  --group orders-projection-prod-v1

bin/kafka-acls.sh \
  --bootstrap-server kafka.example:9093 \
  --add \
  --allow-principal User:orders-projection-prod \
  --operation Describe \
  --group orders-projection-prod-v1
~~~

The group ACL must match the consumer group used by the binding. The Kafka protocol has requests requiring `Read` on the group (join/heartbeat/commit) and offset fetch/describe requests requiring `Describe` on the group; exact required permissions depend on the API/client version and operations used. If the `group` configuration in Spring Cloud Stream changes, the ACL must also be updated.

Do not grant permission to read all groups or all topics to a single consumer. If an application has multiple input bindings, list every required topic and group explicitly.

## 9. Kafka: Permissions for Provisioners

A provisioner may need very different permissions from producers/consumers:

| Provisioning Task | Typical Kafka Permissions Needed |
|---|---|
| Create topic | `Create` on topic or cluster per policy |
| Increase partitions | `Alter` on topic |
| Read metadata | `Describe` on topic |
| Read topic configs | `DescribeConfigs` on topic |
| Modify topic configs | `AlterConfigs` on topic |
| Delete topic | `Delete` on topic |
| Manage ACLs | `Alter` on Cluster resource |

Exact permissions depend on the Kafka version, authorizer, and Admin API operations executed by the provisioning tool. Grant per specific resource, never `All` on Cluster for every application.

The Spring Cloud Stream Kafka binder has provisioning flags:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          auto-create-topics: false
          auto-add-partitions: false
~~~

- `auto-create-topics=false`: the binder relies on pre-created topics; if a topic does not exist, the application fails to start the binding successfully.
- `auto-add-partitions=false`: the binder does not automatically add partitions if the topic has fewer than requested.

This is a useful configuration when the platform manages topics and ACLs. Note that the broker may still auto-create topics when `auto.create.topics.enable` is turned on; the binder flag does not replace broker-side auto-create configuration.

## 10. Kafka: TLS and SASL Authentication in Spring Cloud Stream

The Kafka binder accepts Kafka security properties via `spring.cloud.stream.kafka.binder.configuration`.

Example using SASL/SCRAM over TLS:

~~~yaml
spring:
  cloud:
    stream:
      kafka:
        binder:
          configuration:
            "security.protocol": SASL_SSL
            "sasl.mechanism": SCRAM-SHA-512
            "sasl.jaas.config": ${KAFKA_SASL_JAAS_CONFIG}
~~~

`KAFKA_SASL_JAAS_CONFIG` is supplied from a secret store or deployment environment. Never put real usernames/passwords in committed configuration files.

Kafka also supports SSL client certificates, SASL/PLAIN, Kerberos, and other mechanisms depending on the broker. Configuration must match the cluster's listener and authentication mechanism.

If the application connects to multiple Kafka clusters with different credentials, configure a separate binder for each cluster. Do not use a single principal with permissions across all clusters just to reduce configuration lines.

## 11. Kafka: Separating Permissions for Retry, DLT, and Kafka Streams

A consumer with retry/DLT no longer only reads the input topic. If the binder or error handler publishes failed records to a DLT, the error-handling identity needs permission to write to that DLT.

Example:

| Resource | Basic Consumer | Consumer with DLT |
|---|---:|---:|
| `orders.created.v1` | Read | Read |
| `orders.created.dlt` | No | Write |
| `orders-projection-prod-v1` group | Read | Read |

If using retry topics, add read/write permissions for the retry topics according to the actual configuration. Do not grant topic wildcards just because you do not yet know which internal names the binder creates; determine exact resource names from configuration and broker metadata.

Kafka Streams may need additional permissions for:
- Source topics: Read/Describe.
- Sink topics: Write/Describe.
- Internal changelog/repartition topics: required read/write and create permissions per topology.
- Streams application group: corresponding group permissions.
- Transactional IDs if exactly-once processing is enabled.

Internal topics usually carry a prefix based on the application ID. You can use a prefixed resource pattern to scope a topic family, but choose a sufficiently narrow prefix and verify it does not cover other workloads.

## 12. RabbitMQ: Vhosts, Resource Permissions, and Topic Permissions

RabbitMQ divides permissions into three layers:

1. **Virtual host:** boundary containing exchanges, queues, and bindings.
2. **Resource permissions:** `configure`, `write`, `read` permissions applied to exchange/queue names within a vhost.
3. **Topic permissions:** can restrict routing keys on topic exchanges.

Meaning:

| Permission | Operations |
|---|---|
| `configure` | Create, delete, or modify exchanges/queues |
| `write` | Publish to an exchange or perform bind/unbind operations on destination resources |
| `read` | Consume/get messages from a queue or perform bind operations on source resources |

Each user can only operate inside the virtual hosts to which it is granted permissions. Queues with the same name in two vhosts are two distinct resources.

Do not use the default `guest` user for production services. Create dedicated service accounts, separate credentials, and dedicated vhosts by domain or environment.

## 13. RabbitMQ: Least-Privilege Permissions for Publishers

In AMQP 0-9-1, `basic.publish` requires `write` on the target exchange. If the exchange is pre-created and the client does not need to declare resources, the publisher does not need `configure` permission.

Example allowing `orders-publisher` to write only to exchange `orders.created` in vhost `orders-prod`:

~~~bash
rabbitmqctl set_permissions \
  -p orders-prod \
  orders-publisher \
  '^$' \
  '^orders\.created$' \
  '^$'
~~~

The order of the three expressions is:

1. configure.
2. write.
3. read.

`^$` matches only the empty string, meaning no permissions are granted on normally named resources. `^orders\.created$` restricts write access to that exact exchange.

If the publisher needs to declare the exchange at startup, it will need the corresponding configure permission. In production, the provisioner can create the exchange while keeping the publisher write-only.

## 14. RabbitMQ: Least-Privilege Permissions for Consumers

In AMQP 0-9-1, `basic.consume` requires `read` on the queue. If the queue and binding already exist, the consumer does not need permission to publish to the exchange.

Example allowing the consumer to read only queue `orders.created.orders-projection`:

~~~bash
rabbitmqctl set_permissions \
  -p orders-prod \
  orders-projection \
  '^$' \
  '^$' \
  '^orders\.created\.orders-projection$'
~~~

The queue and exchange must be pre-provisioned. If the binder still declares exchanges, queues, or bindings at startup, it may require additional configure/write/read permissions matching the exact AMQP operations executed.

RabbitMQ 4.3.1 and later allow passive declarations when the user has at least one of the three permissions on the resource; however, non-passive declarations still require configure. Check the broker version if the binder uses passive declaration to verify resources.

## 15. RabbitMQ: Provisioning and Queue Binding Permissions

When the binder automatically creates exchanges, queues, and bindings, the provisioner needs broader permissions than runtime consumers/publishers.

Example binding queue `orders.created.orders-projection` to exchange `orders.created`:

- Creating the exchange requires configure on the exchange.
- Creating the queue requires configure on the queue.
- Binding the queue to the exchange requires write on the destination queue and read on the source exchange.

Example provisioner permissions for those exact two resources:

~~~bash
rabbitmqctl set_permissions \
  -p orders-prod \
  orders-provisioner \
  '^(orders\.created|orders\.created\.orders-projection)$' \
  '^orders\.created\.orders-projection$' \
  '^orders\.created$'
~~~

If there is a dead-letter exchange/queue, retry queue, or alternate exchange, add those exact resource names to the expressions. Do not open `.*` across the entire vhost just to avoid provisioning errors.

With the Rabbit binder, by default the binder can auto-create topic exchanges, queues, and bindings. When using pre-created administrative resources, binder documentation allows disabling provisioning on a consumer binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: orders-projection

      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              bind-queue: false
              declare-exchange: false
~~~

With destination `orders.created` and group `orders-projection`, the default queue name is `orders.created.orders-projection`; hence the config does not enable `queue-name-group-only`. The example assumes the exchange/queue already exist and the queue is already bound properly. For output bindings, disable exchange declaration via `spring.cloud.stream.rabbit.bindings.<binding-name>.producer.declare-exchange=false` when the exchange is pre-provisioned.

Output binding example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.created

      rabbit:
        bindings:
          publishOrder-out-0:
            producer:
              declare-exchange: false
~~~

## 16. RabbitMQ: Restricting Routing Keys

For topic exchanges, resource `write` permission allows publishing to the exchange. RabbitMQ also supports topic authorization to restrict routing keys for protocols/flows where applicable.

Example allowing a publisher to send only routing keys starting with `orders.created.`:

~~~bash
rabbitmqctl set_topic_permissions \
  -p orders-prod \
  orders-publisher \
  orders.created \
  '^orders\.created\..*$' \
  '^$'
~~~

Topic permissions are an additional layer; they do not replace write permission on the exchange. In AMQP 0-9-1, consumers normally consume from queues, while routing keys are checked in certain topic exchange binding operations.

Choose resource permissions and topic permissions according to the actual protocol. Do not assume MQTT/STOMP routing-key ACLs have the same semantics as AMQP 0-9-1 queue consumers.

## 17. Pulsar: Roles, Tenants, and Namespaces

Pulsar uses roles to represent authenticated clients. Authorization can grant permissions at the namespace or topic scope.

Commonly used actions:

- `produce`: publish messages.
- `consume`: subscribe/consume messages.

Topic example:

~~~text
persistent://acme/orders-prod/orders-created-v1
~~~

Where:

- `acme` is the tenant.
- `orders-prod` is the namespace.
- `orders-created-v1` is the topic.

A namespace is an administrative scope suitable for grouping related topics. If a role only needs a single topic, prefer topic-level permissions when policy and deployment version support them; if a role needs many topics in one namespace, namespace permissions can be simpler though broader in scope.

Pulsar separates authentication and authorization. If authentication is enabled without authorization, authenticated roles may gain broad access per broker defaults. A superuser can create/delete tenants and holds extensive permissions over resources. Never use a superuser role for runtime producers or consumers.

## 18. Pulsar: Least-Privilege Permissions for Producers and Consumers

Grant produce permission to the producer role:

~~~bash
pulsar-admin namespaces grant-permission acme/orders-prod \
  --role orders-publisher \
  --actions produce
~~~

Grant consume permission to the consumer role:

~~~bash
pulsar-admin namespaces grant-permission acme/orders-prod \
  --role orders-projection \
  --actions consume
~~~

The two roles have different permissions in the same namespace. The producer does not need consume; the consumer does not need produce if it does not emit output events.

If an application consumes from one namespace and publishes to another, grant each action separately on each namespace. Do not grant `produce,consume` across all namespaces just to share one credential.

Subscription management, topic deletion, backlog clearing, or policy changes may require higher admin roles depending on the operation and authorization configuration. Do not grant those permissions to a runtime consumer simply because the application uses a subscription.

## 19. Pulsar: Provisioning Is a Separate Administrative Permission

Creating tenants, namespaces, partitioned topics, modifying policies, or granting/revoking roles are administrative tasks.

Pulsar can grant namespace permissions to roles and provides APIs to manage topic-level permissions. A tenant admin can manage namespaces and grant/revoke permissions. A superuser holds even broader privileges.

The Spring Cloud Stream Pulsar binder includes a topic provisioner. Binder documentation describes the provisioner as using `PulsarAdministration` (PulsarAdmin) to create topics when needed; thus it may require admin connection details and appropriate administrative permissions.

This is a key point when implementing least privilege:

- Runtime `PulsarClient` is used for publish/consume.
- `PulsarAdmin` is used for provisioning and administrative tasks.
- Do not put a superuser token inside workloads just so topics get created at startup.
- Pre-create tenants, namespaces, and topics using a pipeline/platform role before deployment.
- Check the provisioner behavior of your exact binder version; if the binder still calls the admin API, design a provisioning step or configure a separate admin identity per deployment environment rather than silently granting superuser to runtime.

Do not assume that if a topic already exists, the provisioner definitely needs no admin permissions. Verify via integration tests with the exact runtime role and real binder configuration.

## 20. Pulsar: Client Authentication in Spring Boot

The Pulsar binder uses Spring for Apache Pulsar components, so Spring Boot's client properties can be used in binder applications.

Token authentication example:

~~~yaml
spring:
  pulsar:
    client:
      service-url: pulsar+ssl://pulsar.example:6651
      authentication:
        plugin-class-name: org.apache.pulsar.client.impl.auth.AuthenticationToken
        param:
          token: ${PULSAR_RUNTIME_TOKEN}
~~~

Plugin names and parameters must match the cluster's authentication provider. Never store real tokens in source control. TLS must be configured appropriately for your Spring Pulsar and Spring Boot versions; in versions where auto-configuration lacks full TLS properties, use `PulsarClientBuilderCustomizer` per official documentation.

If using OAuth2, tokens, or mTLS, use an identity bound to the runtime service. Certificates/private keys must be protected like secrets and have a rotation plan.

If the application uses PulsarAdmin for provisioning, admin authentication configuration must be managed separately from the runtime client. Do not use the same superuser token for both merely for configuration convenience.

## 21. Configuring RabbitMQ Connections in Spring Boot

The Rabbit binder normally uses Spring AMQP/Rabbit connection factories. Example configuring a connection to a dedicated vhost:

~~~yaml
spring:
  rabbitmq:
    host: rabbitmq.example
    port: 5671
    username: ${RABBITMQ_USERNAME}
    password: ${RABBITMQ_PASSWORD}
    virtual-host: orders-prod
    ssl:
      enabled: true
~~~

The account here must be a runtime user granted permissions on vhost `orders-prod`. Do not use a management administrator account to run producers/consumers.

In RabbitMQ, vhost permissions and exchange/queue permissions are two separate conditions. The client needs vhost access plus the right resource permissions for AMQP operations.

If using OAuth2 or certificate-based authentication, configure the auth backend and TLS according to broker policy. Do not just change username/password in the application while neglecting resource permissions on RabbitMQ.

## 22. Configuring Kafka Bindings with a Runtime Identity

Example of a service that only reads a topic and uses its own consumer group:

~~~yaml
spring:
  cloud:
    function:
      definition: projectOrder

    stream:
      bindings:
        projectOrder-in-0:
          destination: orders.created.v1
          group: orders-projection-prod-v1

      kafka:
        binder:
          auto-create-topics: false
          auto-add-partitions: false
          configuration:
            "security.protocol": SASL_SSL
            "sasl.mechanism": SCRAM-SHA-512
            "sasl.jaas.config": ${KAFKA_SASL_JAAS_CONFIG}
~~~

Kafka credentials map to a principal that already has Read/Describe ACLs on the topic and Read on the group; add Describe on the group if the client needs to fetch/inspect committed offsets. Do not add Create topic permission for this consumer if the topic already exists.

If the application has multiple bindings with multiple destinations, ACLs must cover each exact destination and group. Do not use a broader prefix than necessary.

## 23. Configuring Multiple Bindings with Different Permissions

An application may both consume and publish. Example function receiving orders, processing them, and emitting a standardized event:

~~~java
@Bean
Function<OrderCreated, OrderAccepted> acceptOrder() {
    return order -> new OrderAccepted(
        order.orderId(),
        "ACCEPTED"
    );
}
~~~

Binding:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptOrder

    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders.created.v1
          group: order-acceptance-prod-v1

        acceptOrder-out-0:
          destination: orders.accepted.v1
~~~

The runtime identity needs:

- Read/Describe on `orders.created.v1`.
- Read on group `order-acceptance-prod-v1`.
- Write/Describe on `orders.accepted.v1`.

It does not need permission to read `orders.accepted.v1`, create topics, or delete resources. If the function uses retry/DLT, add publish permission to the corresponding error resource and only that resource.

If the producer and consumer belong to independent services, use separate credentials for each service. If one JVM has multiple binders/clusters, configure separate identities per binder so cluster A's permissions are not mixed with cluster B's.

## 24. Credentials, Secrets, and Rotation

Broker credentials are operational secrets. Never store secrets directly in:

- Git repositories.
- Docker images or build artifacts.
- Application logs.
- Exception messages or Actuator responses.
- Shared test files.
- Command line history or public scripts.

Retrieve secrets from Vault, a cloud secret manager, Kubernetes Secrets, or the platform's secret store mechanism. Using environment variables is only an example of passing values; in production systems, the secret store and secret read permissions must be strictly controlled.

Rotation procedure:

1. Create a new credential for the same service identity or a replacement identity.
2. Grant equivalent ACLs while keeping the exact resource scope restricted.
3. Update the secret store.
4. Restart/refresh workloads via the supported mechanism.
5. Verify producers/consumers operate with the new credential.
6. Revoke the old credential.
7. Check broker logs to ensure no clients are still using the old credential.

Do not rotate credentials by temporarily granting admin permissions and forgetting to revoke them. Credential rotation must preserve the exact required permission scope.

## 25. TLS and Transport Protection

ACLs do not encrypt messages in transit. You must combine authentication, authorization, and TLS.

- Kafka: use SASL_SSL or SSL/mTLS depending on the cluster.
- RabbitMQ: use AMQPS/TLS and certificate authentication if configured.
- Pulsar: use `pulsar+ssl://`, TLS trust material, and an authentication plugin.
- Verify hostname verification and the trust chain.
- Do not disable certificate validation as a "quick fix" for connection errors.
- Keep private keys in a secret store or mounted files with minimal read permissions.

TLS protects transport and verifies endpoints; it does not replace ACLs. A client with valid TLS must still be rejected if its principal lacks publish/consume permissions.

## 26. Auxiliary Permissions for Schemas, Retry, and Dead-Letter

Real-world processing flows may touch additional resources beyond the primary input/output topics.

| Component | Potentially Required Permissions |
|---|---|
| Schema Registry | Read schemas or register schemas per subject |
| Kafka retry topic | Read/Write on retry topics and related groups |
| Kafka DLT | Write on DLT if the application publishes failed records |
| Rabbit DLX/DLQ | Provisioner creates exchange/queue/binding; consumer needs matching permissions if self-declaring |
| Pulsar DLQ | Produce to the dead-letter topic if client publishes directly |
| Pulsar schema | Lookup/produce permissions per schema operations and authorization provider |
| Kafka Streams internal topics | Permissions on changelog/repartition topics and group |
| Monitoring | Read metadata/metrics; no default message payload read access |

Do not grant permissions across the entire retry/DLT namespace if only one binding needs it. Record the exact resource names generated by the binder, then grant permissions to the exact prefix or exact name.

When enabling DLQ in the Kafka binder, the consumer may both read the input and write to the DLT. Check ACLs in both directions. With the Rabbit binder, if autoBindDlq creates exchanges/queues/bindings, the declaring identity needs corresponding configure/write/read permissions; you can pre-provision resources so runtime does not hold administrative privileges.

## 27. Auditing ACLs and Effective Permissions

Do not rely solely on Spring Boot configuration files. Verify policies directly on the broker.

### Kafka

List ACLs for a principal:

~~~bash
bin/kafka-acls.sh \
  --bootstrap-server kafka.example:9093 \
  --list \
  --principal User:orders-projection-prod
~~~

Verify:
- Input topic has Read/Describe.
- Group has Read and Describe according to the API/client in use.
- Output/DLT has Write only where needed.
- There are no out-of-scope wildcard ACLs.
- The provisioner role is not used inside runtime pods.

### RabbitMQ

List permissions by vhost:

~~~bash
rabbitmqctl list_permissions -p orders-prod
rabbitmqctl list_user_permissions orders-projection
~~~

Verify that configure/write/read regexes accurately restrict queues/exchanges. If permissions were just changed and a client is still denied, check connections/channels because RabbitMQ may cache permission check results; the client may need to reconnect.

### Pulsar

Check namespace permissions:

~~~bash
pulsar-admin namespaces permissions acme/orders-prod
~~~

Verify the producer role has only produce and the consumer has only consume. If topic-level permissions exist, check topic permissions as well. Confirm authorization is enabled on the broker; if it is not enabled, role inspection results cannot prove runtime is restricted as expected.

## 28. Positive and Negative Authorization Testing

An authorization test suite must prove both allowed operations and denied operations.

| Identity | Operation | Expected Outcome |
|---|---|---|
| Producer | Publish to the target output topic | Succeeds |
| Producer | Consume from the input topic | Denied |
| Producer | Create a new topic | Denied |
| Consumer | Read the target input topic/group | Succeeds |
| Consumer | Publish to the input topic | Denied |
| Consumer | Read another topic | Denied |
| Consumer | Create or delete a queue/topic | Denied |
| Provisioner | Create assigned resources | Succeeds |
| Provisioner | Delete out-of-scope resources | Denied |
| Monitoring | Read granted metadata/metrics | Succeeds |
| Monitoring | Publish or consume payloads | Denied unless required |

Negative testing is critical. If you only test that a producer can send messages, you do not yet know whether the producer was accidentally granted permission to read or delete other resources.

You can write integration tests with Kafka Testcontainers, RabbitMQ Testcontainers, or Pulsar Testcontainers. Tests must use the exact ACL-scoped credentials/roles, never administrator credentials for running assertions.

## 29. Common Mistakes When Configuring Least Privilege

| Symptom | Common Cause | Resolution |
|---|---|---|
| Kafka producer fails with TopicAuthorizationFailed | Missing Write or Describe on topic | Grant permissions on the exact topic |
| Kafka consumer fails with GroupAuthorizationFailed | Missing Read on consumer group | Grant Read on the exact group |
| Kafka producer fails to start | Binder tries to create topic but principal lacks Create | Pre-provision topic and disable autoCreateTopics |
| Kafka Streams internal topic error | Missing permissions on changelog/repartition topics | Grant permissions matching the application's internal topic prefix |
| Rabbit publisher gets ACCESS_REFUSED | Missing write on exchange or wrong vhost | Check vhost and resource regex |
| Rabbit consumer fails to bind queue | Binder is auto-declaring/binding but role lacks configure/write/read | Pre-provision and disable provisioning or grant proper permissions |
| Rabbit consumer cannot read | Missing read on queue | Check queue name and permission regex |
| Pulsar client authenticates but publish is denied | Authentication enabled but role lacks produce | Enable authorization and grant produce |
| Pulsar consumer fails to subscribe | Missing consume or wrong namespace/subscription policy | Check role and subscription |
| Pulsar binder fails to create topic | Provisioner lacks admin permissions or admin service URL | Separate provisioning role and verify PulsarAdministration |
| Works locally but fails in production | Local broker uses broader permissions | Test with production-like service accounts |
| Still denied after rotation | Client still connected with old credentials | Reconnect/restart and verify broker principal |
| Retry/DLT stops working | Consumer lacks write permission on DLT or retry topic | Add permissions for the exact auxiliary resource |
| Permission changes have not taken effect | Old connection/channel caches permissions | Open a new connection and re-verify |

## 30. Pre-Deployment Checklist

| Item | Question |
|---|---|
| Identity | Does every service and environment have its own service account? |
| Producer | Does it only have permission to publish to the required output topics/exchanges? |
| Consumer | Does it only have permission to read inputs and corresponding groups/subscriptions? |
| Provisioner | Is there a separate administrative identity for creating resources? |
| Binder | Is it auto-creating topics/queues/exchanges on startup? |
| Kafka | Do autoCreateTopics/autoAddPartitions align with ACLs? |
| RabbitMQ | Are vhost and configure/write/read regexes properly restricted? |
| Pulsar | Is authorization enabled and do roles have exact produce/consume actions? |
| DLQ/retry | Are auxiliary resources accounted for in ACLs? |
| Schema | Are schema registry/Pulsar schema permissions separated? |
| Secret | Are credentials fetched from a secret store and absent from Git/logs? |
| TLS | Are connections encrypted and certificates verified? |
| Rotation | Is there a process to issue, verify, and revoke old credentials? |
| Negative test | Are producers/consumers properly denied unauthorized operations? |
| Audit | Can you trace which principal published, consumed, or provisioned? |

## 31. Hands-On Exercise: Separating Publisher, Consumer, and Provisioner

Build an order flow with destination `orders.created.v1`.

### Step 1: Identify Identities

Create three separate identities:

- `orders-api-prod`: producer.
- `orders-projection-prod`: consumer.
- `orders-provisioner-prod`: provisioner.

### Step 2: Identify Resources

- Kafka: topic `orders.created.v1`, group `orders-projection-prod-v1`.
- RabbitMQ: vhost `orders-prod`, exchange `orders.created`, queue `orders.created.orders-projection`.
- Pulsar: namespace `acme/orders-prod`, topic `orders-created-v1`, subscription `orders-projection-prod-v1`.

### Step 3: Grant Permissions

- Producer only publishes to the output destination.
- Consumer only consumes the input destination and its own group/subscription.
- Provisioner creates resources and grants/revokes permissions; never use this credential in business workloads.

### Step 4: Configure the Binder

- Configure Kafka SASL_SSL, RabbitMQ TLS, or Pulsar token/mTLS.
- Specify binding destination and group explicitly.
- Disable or avoid auto-provisioning in runtime if the platform pre-manages resources.
- Place credentials in a secret store.

### Step 5: Test

- Producer publishes successfully.
- Consumer reads messages.
- Producer cannot consume.
- Consumer cannot publish to the input topic.
- Runtime roles cannot create or delete resources.
- Provisioner only modifies assigned resources.
- Test credential rotation and confirm old credentials no longer work.

Complete the exercise when you can explain how authentication differs from authorization; separate producer, consumer, and provisioner identities; grant specific ACLs for Kafka, RabbitMQ, and Pulsar; configure the binder without unintended administrative privileges; and prove unauthorized operations are rejected by the broker.

## 32. Official References

- [Spring Cloud Stream — Kafka Binder Security Configuration](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/security-config.html) — SASL, JAAS, SSL, and security properties for the Kafka binder.
- [Spring Cloud Stream — Kafka Binder Configuration Options](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/config-options.html) — autoCreateTopics, autoAddPartitions, and provisioning configurations.
- [Apache Kafka — Authorization and ACLs](https://kafka.apache.org/44/security/authorization-and-acls/) — principals, resources, operations, group/topic/transactional IDs, and ACLs.
- [RabbitMQ — Authentication, Authorisation, Access Control](https://www.rabbitmq.com/docs/access-control) — vhosts, configure/write/read, topic permissions, and user management.
- [Spring Cloud Stream — Using Existing Queues/Exchanges](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/existing-destinations.html) — disabling exchange/queue provisioning when using pre-created resources.
- [Spring Cloud Stream — Rabbit Producer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/prod-props.html) — `declareExchange`, DLQ, and producer properties.
- [Spring Boot — AMQP Configuration](https://docs.spring.io/spring-boot/reference/messaging/amqp.html) — username, password, virtual host, and SSL for RabbitMQ.
- [Apache Pulsar — Authentication and Authorization](https://pulsar.apache.org/docs/5.0.x/security-authorization/) — roles, superusers, tenants, namespaces, and authorization.
- [Apache Pulsar — Namespace Admin API](https://pulsar.apache.org/api/admin/5.0.x/org/apache/pulsar/client/admin/Namespaces.html) — granting/revoking produce and consume permissions.
- [Spring Cloud Stream — Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html) — Spring Pulsar client properties, extended binding properties, and topic provisioner.
- [Spring Boot — Apache Pulsar Support](https://docs.spring.io/spring-boot/reference/messaging/pulsar.html) — client authentication and TLS.
