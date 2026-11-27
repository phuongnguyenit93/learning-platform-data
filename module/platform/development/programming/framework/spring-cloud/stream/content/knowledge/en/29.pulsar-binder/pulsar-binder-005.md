# Automatic Topic Provisioning and Partition Count Configuration

The Spring Cloud Stream Pulsar Binder includes a **topic provisioner** to prepare topics when the application creates bindings. If a topic does not yet exist, Pulsar can automatically create a basic non-partitioned topic upon client access. When a topic with multiple partitions is required, the binder uses `PulsarAdministration` to call the Pulsar Admin API and create a partitioned topic with the configured partition count.

Two key properties are `spring.cloud.stream.pulsar.binder.partition-count` and `spring.cloud.stream.pulsar.bindings.<binding-name>.producer|consumer.partition-count`. The binder-level property sets the default partition count for topics created by the application; the binding-level property allows each data stream to have its own partition count. To provision partitioned topics, the application must be able to connect to both the Pulsar broker and the Pulsar administration endpoint.

This lesson belongs to the **Pulsar Binder** chapter of the `SPRING_CLOUD_STREAM` module. It focuses on the `Supplier`/`Function`/`Consumer` function model, destinations, automatic topic provisioning, tenant/namespace, partitioned topics, two-level partition count configuration, the Pulsar Admin API, key-based routing, consumer scaling, changing partition counts, and operational testing.

## 1. Topics in Apache Pulsar

A topic is the channel for storing and transmitting messages between producers and consumers. A full topic name has the structure:

```text
{persistent|non-persistent}://tenant/namespace/topic
```

Example:

```text
persistent://acme/orders/orders.created
```

| Component | Meaning | Example |
|---|---|---|
| `persistent` | Topic type; messages are stored durably via Pulsar's storage mechanism | `persistent` |
| `tenant` | Multi-tenancy boundary and top-level administrative authority | `acme` |
| `namespace` | Group of topics for applying policies, quotas, and permissions | `orders` |
| `topic` | Specific message stream name within the namespace | `orders.created` |

If the topic type is omitted, Pulsar typically defaults to `persistent`. Non-persistent topics do not store messages durably in BookKeeper like persistent topics do. For business events requiring durability and recovery, choose persistent topics unless there is a clear reason to use non-persistent ones.

Tenants and namespaces are administrative units. In production environments, tenants and namespaces are typically pre-created by the platform team to assign permissions, retention, replication, backlog quotas, and policies. Do not assume automatic topic creation will also create missing tenants and namespaces.

## 2. Spring Cloud Stream Destinations Map to Topics

Spring Cloud Stream uses `destination` to indicate the topic a binding reads from or writes to. Function and binding names are logical names at the application layer; `destination` is the topic name on Pulsar.

Example producer function:

```java
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

record OrderCreated(String eventId, String orderId, long total) {}

@Configuration
class OrderPublisherConfiguration {

    @Bean
    Supplier<OrderCreated> publishOrder() {
        return () -> new OrderCreated(
            "evt-1001",
            "order-1001",
            250000L
        );
    }
}
```

The default binding of the supplier is `publishOrder-out-0`. Configuring the destination:

```yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: persistent://acme/orders/orders.created
```

The binder connects the output binding to the topic `persistent://acme/orders/orders.created`. If no destination is specified, Spring Cloud Stream may use the binding name as the default destination. In production, specify topic names explicitly for easier management and to avoid creating unintended topics.

For a function with both input and output, each binding can point to a separate destination:

```yaml
spring:
  cloud:
    function:
      definition: enrichOrder
    stream:
      bindings:
        enrichOrder-in-0:
          destination: persistent://acme/orders/orders.created
        enrichOrder-out-0:
          destination: persistent://acme/orders/orders.enriched
```

## 3. Pulsar Binder Topic Provisioner

The Pulsar Binder integrates a topic provisioner to prepare the resources required by bindings. When the application starts and a binding references a non-existent topic, the provisioner can create the topic according to configuration.

Distinguish two cases:

1. **Non-partitioned topic:** Pulsar can auto-create a basic topic when a producer/consumer accesses a non-existent topic name, if allowed by broker/namespace policy.
2. **Partitioned topic:** requires metadata specifying the number of partitions. The Pulsar Binder uses the topic provisioner and Pulsar Admin API to create a partitioned topic according to `partition-count`.

If you rely solely on client access to a non-existent topic, the auto-created topic may be non-partitioned. To obtain a topic with multiple partitions, configure the partition count so the provisioner creates the right topic type from the start.

```text
Spring Cloud Stream binding
          |
          v
Pulsar Binder / Topic Provisioner
          |
          +---- topic does not exist, no partitions requested
          |          |
          |          v
          |     basic topic
          |
          +---- partition-count configured
                     |
                     v
               PulsarAdministration
                     |
                     v
               Pulsar Admin API
                     |
                     v
               partitioned topic
```

Provisioning requires topic administrative permissions. An application might have publish/consume permissions without permission to create topics. In that case, have the infrastructure pipeline pre-create topics and grant the application appropriate runtime permissions.

## 4. Client URL and Admin URL Are Two Different Endpoints

The Pulsar client uses the Pulsar protocol to send/receive messages. The Pulsar Admin client uses HTTP/HTTPS to perform administrative operations such as creating topics and partition metadata.

| Connection | Spring Boot property | Example |
|---|---|---|
| Pulsar broker/client | `spring.pulsar.client.service-url` | `pulsar://pulsar-broker:6650` |
| Pulsar Administration | `spring.pulsar.administration.service-url` in some Spring for Apache Pulsar versions; `spring.pulsar.admin.service-url` in newer Spring Boot/Spring Pulsar versions | `http://pulsar-admin:8080` |

Configuration example:

```yaml
spring:
  pulsar:
    client:
      service-url: pulsar://pulsar-broker:6650
    administration:
      service-url: http://pulsar-admin:8080
```

The Pulsar Binder uses `PulsarAdministration` to provision partitioned topics. If the client URL is right but the Admin URL is wrong or unreachable, the application can connect to the broker yet fail when creating topics/partitions. Verify DNS, ports, TLS, authentication, and permissions separately on both endpoints.

Spring for Apache Pulsar property names may vary across bundled Spring Boot/Spring Pulsar versions. Some Pulsar Binder documentation versions use `spring.pulsar.administration.service-url`; newer Spring Boot property catalogs use `spring.pulsar.admin.service-url`. If your project uses the newer namespace, the corresponding configuration is:

```yaml
spring:
  pulsar:
    admin:
      service-url: http://pulsar-admin:8080
```

Cross-check the property metadata of your project's release train before deploying; do not declare both names with different values or blindly copy an Admin URL configuration from another version.

## 5. Configuring Partition Count at the Binder Level

The property:

```text
spring.cloud.stream.pulsar.binder.partition-count
```

sets the default partition count for topics created by the application through the Pulsar Binder. Example:

```yaml
spring:
  cloud:
    stream:
      pulsar:
        binder:
          partition-count: 6
```

With this configuration, topics provisioned by the application inherit a partition count of six unless a specific binding configures its own partition count. Binder-level configuration is useful when streams in the application share similar throughput and concurrency requirements.

Do not mistake binder-level `partition-count` for the number of consumers, subscriptions, or application replicas. It is the number of partitions of the provisioned topic.

## 6. Configuring Partition Count per Binding

When topics carry different loads, you can configure partition counts individually per binding. Property pattern:

```text
spring.cloud.stream.pulsar.bindings.<binding-name>.producer.partition-count
spring.cloud.stream.pulsar.bindings.<binding-name>.consumer.partition-count
```

Example:

```yaml
spring:
  cloud:
    function:
      definition: publishOrder;publishAudit
    stream:
      bindings:
        publishOrder-out-0:
          destination: persistent://acme/orders/orders.created
        publishAudit-out-0:
          destination: persistent://acme/audit/audit.events
      pulsar:
        bindings:
          publishOrder-out-0:
            producer:
              partition-count: 12
          publishAudit-out-0:
            producer:
              partition-count: 3
```

In this example, the orders topic is provisioned with 12 partitions, while the audit topic is provisioned with 3 partitions. The differing counts reflect each stream's distinct load and scaling needs.

You can set the corresponding property on a consumer binding when that binding provisions the topic. Example:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processPayment-in-0:
          destination: persistent://acme/payments/payment.events
      pulsar:
        bindings:
          processPayment-in-0:
            consumer:
              partition-count: 8
```

If both a producer and a consumer reference the same topic, align the partition count between both sides. Avoid having two bindings provision the same destination while declaring conflicting partition counts.

## 7. Configuration Precedence Order

The Pulsar Binder applies configuration in descending order of precedence:

1. Extended binding properties: `spring.cloud.stream.pulsar.bindings.<binding-name>...`
2. Binder-level properties: `spring.cloud.stream.pulsar.binder...`
3. Spring Boot Pulsar properties: `spring.pulsar...`

Example where the binder sets a default of six partitions while binding `publishOrder-out-0` specifically sets 12 partitions:

```yaml
spring:
  cloud:
    stream:
      pulsar:
        binder:
          partition-count: 6
        bindings:
          publishOrder-out-0:
            producer:
              partition-count: 12
```

Binding `publishOrder-out-0` uses the specific value of 12; other topics created by the binder inherit the binder-level value of six. This precedence rule allows one application to manage multiple functions with different partition requirements.

## 8. Complete Configuration for Producer and Consumer

Example of an application that both emits order events and processes them:

```yaml
spring:
  pulsar:
    client:
      service-url: pulsar://pulsar-broker:6650
    administration:
      service-url: http://pulsar-admin:8080
  cloud:
    function:
      definition: publishOrder;processOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: persistent://acme/orders/orders.created
        processOrder-in-0:
          destination: persistent://acme/orders/orders.created
          group: order-processing
      pulsar:
        binder:
          partition-count: 6
```

In this configuration:

- `publishOrder-out-0` is the supplier's output binding.
- `processOrder-in-0` is the consumer's input binding.
- Both reference the same destination.
- The Pulsar client URL connects to the broker for publishing/consuming.
- The Admin URL allows the topic provisioner to perform administrative actions.
- The binder-level partition count sets six partitions for created topics.

`group` in Spring Cloud Stream configuration is the logical consumer group name. With Pulsar, verify how the binder maps `group` to subscription name for your binder version. Do not treat `group` as a tenant, namespace, or partition name.

## 9. Creating a Partitioned Topic with the Pulsar Admin CLI

If your organization manages topics outside the application, you can pre-create partitioned topics using the Pulsar Admin CLI:

```bash
pulsar-admin topics create-partitioned-topic \
  persistent://acme/orders/orders.created \
  --partitions 6
```

Before doing so, the tenant and namespace must exist:

```bash
pulsar-admin tenants list
pulsar-admin namespaces list acme
```

If namespace `acme/orders` does not exist yet and your account has admin permissions, create the namespace according to your infrastructure process:

```bash
pulsar-admin namespaces create acme/orders
```

Check partition count metadata:

```bash
pulsar-admin topics get-partitioned-topic-metadata \
  persistent://acme/orders/orders.created
```

The output should show the declared number of partitions. CLI commands require appropriate admin permissions and must be run with connection/authentication settings targeting the right cluster.

## 10. How Partitioned Topics Are Implemented

A partitioned topic is a logical topic backed by multiple internal partitions. If topic `orders.created` has six partitions, Pulsar manages the individual partitions and distributes them across appropriate brokers.

```text
Logical topic:
persistent://acme/orders/orders.created
                 |
                 +---- partition 0
                 +---- partition 1
                 +---- partition 2
                 +---- partition 3
                 +---- partition 4
                 +---- partition 5
```

Producers and consumers normally interact with the logical topic name. The Pulsar client looks up metadata and connects to the corresponding partitions. The application does not need to manually create six separate business topic names.

Partitions enable a topic to distribute load across multiple brokers and increase parallel processing capacity. Partition count also affects the number of producer/consumer connections, metadata, ledgers, and administrative overhead.

## 11. Partition Count and Scalability

Partition count sets an upper bound on parallelism achievable at the topic level, but it does not by itself determine the number of consumers. The actual number of active consumers also depends on the subscription type, the number of registered consumers, and how Pulsar distributes partitions.

Examples:

| Topic structure | Consumer instances | Notes |
|---:|---:|---|
| Non-partitioned topic | 1 | No internal partitions for topic-level parallel scaling |
| 6 | 1 | One consumer can read multiple partitions |
| 6 | 3 | An appropriate subscription can distribute partitions across multiple consumers |
| 6 | 10 | Does not mean all 10 consumers get their own partition; some may get none depending on subscription type |
| 12 | 3 | More partitions available to distribute, though load and broker capacity still need measurement |

These are illustrative examples, not fixed partition assignment rules for every subscription. With `Exclusive`, `Shared`, `Failover`, and `Key_Shared`, message and partition distribution work differently.

## 12. Partition Count Does Not Replace Routing Keys

Partition count determines how many partitions a topic has. Routing mode and message key determine which partition a message is sent to.

Pulsar provides common routing modes:

| Routing mode | Without key | With key |
|---|---|---|
| `RoundRobinPartition` | Distributes round-robin across partitions by batch/routing interval | Hashes key to pick the corresponding partition |
| `SinglePartition` | Selects one partition for the producer and sends keyless messages there | Hashes key to pick the corresponding partition |
| `CustomPartition` | Uses a custom message router | Router logic decides the partition |

`RoundRobinPartition` is typically the default for Pulsar producers. When messages of the same aggregate must stay on the same partition, send a stable key such as `orderId` or `accountId` and use a routing mode supporting key routing.

If messages have no key, round-robin may optimize load distribution but provides no per-aggregate ordering guarantee. If all messages share a single hot key, they may concentrate onto one partition and reduce scaling effectiveness.

Note: the Pulsar Binder's `partition-count` configures provisioning of the partition count. Choosing keys/routing modes is a producer-layer message-sending configuration. The two settings are related, not a single property.

## 13. Partitioning and Subscription Types

Pulsar separates the producer's decision of which partition receives a message from the subscription's decision of which consumer receives a message.

| Subscription type | Consumption model |
|---|---|
| `Exclusive` | Only one consumer attaches to the subscription |
| `Shared` | Multiple consumers on the same subscription share messages; global ordering is not guaranteed |
| `Failover` | Multiple consumers can register, but the broker selects an active consumer per topic/partition and fails over when needed |
| `Key_Shared` | Distributes messages by key so messages with the same key go to the corresponding consumer per subscription semantics |

Partitioned topics can be combined with any of these subscription types. If throughput is the goal, evaluate partition count and `Shared`/`Key_Shared`. If active/standby is needed, evaluate `Failover`. If per-key ordering is needed, design compatible message keys, routing mode, subscription type, and batching.

Do not increase partition count just to add more consumers if the subscription in use does not distribute load the way you expect. Check subscription semantics first.

## 14. Choosing an Initial Partition Count

There is no single right partition count for every topic. Base your choice on target throughput, message size, key distribution, consumer count, broker capacity, and operational overhead.

An estimation process:

1. Measure or estimate messages/second and payload size.
2. Benchmark steady throughput of a single partition using production-like messages and producer/consumer settings.
3. Estimate the number of partitions needed to achieve target throughput, plus a reasonable safety margin.
4. Verify broker count, namespace bundles, storage, and network capacity can support it.
5. Evaluate the expected consumer count and subscription type.
6. Inspect key distribution to avoid hot partitions.
7. Run load and failover tests before finalizing for production.

Illustrative example: if one partition steadily handles around 2,000 messages/second under realistic workload conditions and the topic needs 10,000 messages/second, six partitions can be a starting point for benchmarking. This is purely a load-sizing assumption; do not substitute illustrative numbers for benchmarks on a real cluster.

Increasing partition count increases internal partitions, metadata, producer/consumer connections, and management overhead. Choosing too many partitions upfront adds overhead without extra throughput if producers, consumers, or brokers are the real bottleneck elsewhere.

## 15. Impact of Increasing Partition Count

Apache Pulsar supports increasing the partition count of a partitioned topic. You can update it with:

```bash
pulsar-admin topics update-partitioned-topic \
  persistent://acme/orders/orders.created \
  --partitions 12
```

Pulsar supports increasing the partition count; it does not support decreasing the partition count via a standard update operation. To reduce partitions or make major structural changes, create a new topic and perform a migration.

When increasing partition count, producers and consumers can discover new partitions through metadata. However, evaluate:

- How new load is distributed across partitions.
- Keys may hash to different partitions when the modulus changes.
- Per-key ordering during the transition period.
- Whether consumers/subscriptions require rebalancing or reconnection.
- Whether brokers, storage, and network have sufficient capacity.
- Whether downstream systems assume a fixed partition count.

If strict business ordering per key is required, test behavior before and after increasing partitions. Messages with the same key published before and after the change may no longer land in the same partition if the partition calculation changes.

## 16. Do Not Assume Regular Topics Auto-Convert to Partitioned Topics

If a topic was already created as non-partitioned, do not assume simply adding `partition-count` in YAML will make the binder automatically convert the existing topic into a partitioned topic. The provisioner cannot arbitrarily change the resource type of an existing topic.

For existing topics, inspect metadata before deploying. If you must switch to a partitioned topic, the safe approach is usually:

1. Create a new topic with a new name and the desired partition count.
2. Update producers to publish to the new topic or perform controlled dual-publishing.
3. Run new consumers and verify the data.
4. Backfill/replay historical data if required by business needs.
5. Switch downstream consumers to the new topic.
6. Stop writing to the old topic after verifying the migration.
7. Delete the old topic only according to retention and audit policies.

Do not delete an existing topic to force the binder to recreate it while unprocessed messages or active subscriptions still exist on it.

## 17. Automatic Provisioning vs. Infrastructure-Managed Provisioning

There are two ways to organize provisioning:

| Approach | Best suited when | Responsibilities |
|---|---|---|
| Binder auto-provisioning | Development, test, or environments where applications are allowed to create topics | Application needs Admin URL and permissions to create topics/partitions |
| Infrastructure pre-provisioning | Production with centralized topic governance, ACLs, and policies | Platform team creates tenant/namespace/topic; application uses runtime permissions |

In production, topics often require policies for retention, backlog quota, message TTL, replication, schemas, and access control. If the binder creates a topic automatically without those policies applied properly, the topic may run with unsuitable defaults.

You can use the binder provisioner during development and switch to infrastructure-managed provisioning before production. In that case, ensure destination names and partition counts in the application match the pre-provisioned resources.

## 18. Permissions Required for Automatic Topic Provisioning

The Pulsar client and Pulsar Admin API may use different permissions. When the binder auto-provisions a partitioned topic, the principal needs appropriate administrative permissions on the tenant/namespace or topic per cluster policy.

Check that:

- The tenant already exists.
- The namespace already exists.
- The Admin endpoint is reachable from the application.
- The admin principal is allowed to create topics and partitions in the namespace.
- The client principal has publish/consume permissions once the topic exists.
- Authentication and TLS are configured for both client and admin.
- Namespace policies do not block auto topic creation or partitioned topic creation.

Do not grant cluster-wide admin privileges to an application just to create one topic. If your organization prohibits applications from creating resources themselves, provision via infrastructure pipelines and grant minimal runtime permissions.

## 19. Common Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Topic created without partitions | Only basic auto topic creation occurred; partition count not configured | Configure `spring.cloud.stream.pulsar.binder.partition-count` or per-binding partition count |
| Application connects to broker but partition provisioning fails | Admin URL is wrong or unreachable | Check Pulsar Administration endpoint separately from client URL |
| Topic creation fails | Tenant/namespace does not exist or lacks permissions | Provision tenant/namespace and grant appropriate permissions |
| All topics unexpectedly have the same partition count | Binder-level partition count applied to every topic | Switch to per-binding configuration for topics with differing loads |
| One topic has an unexpected partition count | Per-binding config overrode binder-level config | Check precedence order and binding name |
| Producer/consumer do not use the same topic | Different destinations or inconsistent short vs. FQ names | Standardize full destination names |
| Partition count increased but per-key ordering changed | Keys hash to different partitions after count change | Plan migration and test ordering |
| Consumer throughput does not increase | Unsuitable subscription type or consumer count | Check `Shared`/`Key_Shared`/`Failover` and consumer assignment |
| Existing topic does not become partitioned | Existing topic is non-partitioned | Create a new topic and migrate in a controlled manner |
| Auto provisioning fails in production | Runtime principal lacks Admin API permissions | Pre-provision via infrastructure or grant least-privilege permissions |

## 20. Verifying Topics and Partitions After Provisioning

After the application starts, inspect topic metadata with the Pulsar Admin CLI:

```bash
pulsar-admin topics get-partitioned-topic-metadata \
  persistent://acme/orders/orders.created
```

List topics in the namespace:

```bash
pulsar-admin topics list acme/orders
```

View topic statistics:

```bash
pulsar-admin topics stats \
  persistent://acme/orders/orders.created
```

Check actual partition count, connected producers/consumers, backlog, and message rate. Do not rely solely on Spring Boot starting cleanly to conclude the topic has the intended partition count.

## 21. Testing Auto-Provisioning and Partition Count

An integration test suite should verify both binder configuration and metadata on a real Pulsar instance or compatible test environment:

| Scenario | How to test | Expected verification |
|---|---|---|
| Non-existent topic | Start binding with a new destination | Topic is created according to provisioner/policy |
| Non-partitioned topic | Omit partition count | Verify basic topic is created per environment config |
| Binder-level count | Set `binder.partition-count: 6` | Topics created by the application inherit six partitions |
| Binding-level count | Set producer partition count to 12 | Specific binding creates topic with 12 partitions |
| Two different bindings | One 12-partition topic, one 3-partition topic | Each topic gets its own configured count |
| Binding override | Binder count 6, binding count 12 | Binding uses the specific value per precedence |
| Wrong Admin URL | Configure invalid admin endpoint | Provisioning error is clearly surfaced |
| Missing Admin permissions | Revoke topic creation permissions | Provisioning fails and is observed |
| Non-existent namespace | Use destination in an unprovisioned namespace | Verify namespace error and namespace creation workflow |
| Existing non-partitioned topic | Add partition count to config | Verify binder does not silently convert topic type |
| Increase partitions | Increase from 6 to 12 via Admin API | Metadata reflects new partition count; producers/consumers discover properly |
| Key-based routing | Send multiple messages with the same key | Messages with the same key go to the same partition under proper routing mode |
| Consumer scaling | Run multiple consumers with selected subscription type | Verify partition/message distribution and throughput |

Binder unit tests can verify functions and bindings at the Spring layer, but they do not replace integration tests for the Pulsar Admin API, topic metadata, partition routing, and subscription behavior.

## 22. Monitoring in Production

Metrics to monitor:

- Number of provisioned topics per tenant/namespace.
- Actual partition count of each topic.
- Publish and consume rates per partition.
- Message/key distribution across partitions.
- Producer latency, send failures, and pending messages.
- Consumer backlog, redeliveries, and subscription state.
- Broker ownership, storage usage, and network throughput.
- Admin API errors, authentication/authorization errors, and provisioning errors.
- Partition metadata changes after each deployment.

Set alerts when a topic lacks the expected partitions, a single partition carries disproportionate load, backlog grows persistently, or the binder cannot reach the Admin API. Logs should include binding name, full destination, expected partition count, and provisioning errors; never log credentials or tokens.

## 23. Topic and Partition Configuration Workflow

When deploying the Pulsar Binder:

1. Select a pre-provisioned tenant and namespace.
2. Specify the full destination as `persistent://tenant/namespace/topic` or the appropriate topic type.
3. Decide whether topics will be auto-created by the binder or pre-provisioned by infrastructure.
4. Configure the Pulsar client service URL.
5. If the binder must create partitioned topics, configure the Admin service URL and corresponding admin permissions.
6. Choose a default partition count at the binder level if topics share similar requirements.
7. Use binding-level partition counts for topics with distinct throughput requirements.
8. Choose routing mode and message keys to match load distribution and ordering requirements.
9. Choose subscription type and consumer count according to the processing model.
10. Inspect topic metadata after provisioning.
11. Test publishing, consuming, key-based routing, partition increases, and failover.
12. Monitor partition-level throughput, backlog, Admin API health, and broker capacity.

## 24. Self-Check

- [ ] Can explain that a topic name consists of topic type, tenant, namespace, and topic name.
- [ ] Can distinguish basic auto topic creation from partitioned topic provisioning.
- [ ] Can explain the role of the Pulsar Topic Provisioner and `PulsarAdministration`.
- [ ] Can distinguish the Pulsar client service URL from the Admin service URL.
- [ ] Can configure `spring.cloud.stream.pulsar.binder.partition-count`.
- [ ] Can configure separate partition counts per producer/consumer binding.
- [ ] Can explain precedence order among extended binding, binder, and Spring Boot properties.
- [ ] Can create a partitioned topic using the Pulsar Admin CLI.
- [ ] Can distinguish partition count from consumer count and subscription type.
- [ ] Can explain routing modes and the role of message keys.
- [ ] Knows that partition count can be increased, not decreased via standard update operations.
- [ ] Can plan a migration when a regular topic needs to become a partitioned topic.
- [ ] Can inspect topic metadata, provisioning permissions, and partition-level metrics.

## Conclusion

The Pulsar Binder provides a topic provisioner to create topics required by bindings. Basic topics can be auto-created on access, whereas partitioned topics require the provisioner to call the Pulsar Admin API with the specified partition count. Use `spring.cloud.stream.pulsar.binder.partition-count` for application-wide defaults and `spring.cloud.stream.pulsar.bindings.<binding-name>.producer|consumer.partition-count` to tune individual bindings. Provisioning partitioned topics requires the Admin URL, tenant/namespace, and appropriate admin permissions. Partition count defines the topic's parallel structure; routing mode/message keys and subscription type determine how messages are distributed. Inspect metadata after creation, benchmark partition counts, and plan migrations carefully before altering production topics.

## References

- Spring Cloud Stream Pulsar Binder: https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html
- Apache Pulsar, managing topics and partitioned topics: https://pulsar.apache.org/docs/4.2.x/admin-api-topics/
- Apache Pulsar, topics, partitions, routing modes, and subscriptions: https://pulsar.apache.org/docs/4.2.x/concepts-messaging/
- Spring Boot, connecting Pulsar client and administration: https://docs.spring.io/spring-boot/4.0/reference/messaging/pulsar.html
