# requiredGroups and Binder-Specific Applicability Conditions

In an event-processing system, a producer may begin sending messages before a consumer is deployed. If the broker does not yet have a receiving resource dedicated to that group, messages emitted during the waiting interval might not be retained for the new group. Spring Cloud Stream provides the producer property **requiredGroups** to pre-declare the groups that need to receive data. However, its actual effect depends on the broker's storage model and how the binder provisions resources.

This property is particularly useful with RabbitMQ, where each consumer group typically has its own queue bound to an exchange. Kafka and Pulsar use topics with offsets or subscription cursors, so guaranteeing messages for late-starting groups works differently from creating a per-group queue. Do not treat **requiredGroups** as a uniform consumer-group creation command across all binders.

## 1. Distinguishing consumer group from producer requiredGroups

Spring Cloud Stream has two settings related to consuming groups, located on opposite sides:

| Property | Where it resides | Meaning |
|---|---|---|
| **group** | Consumer input binding | Sets the consuming group's identity. Instances in the same group coordinate to share load; different groups receive independent copies of the event stream per broker semantics. |
| **requiredGroups** | Output binding producer properties | Declares the groups for which the producer needs receiving resources prepared before emitting messages. |

Example of an event-consuming application:

~~~yaml
spring:
  cloud:
    function:
      definition: billingConsumer
    stream:
      bindings:
        billingConsumer-in-0:
          destination: orders
          group: billing
~~~

Here **billing** is the input binding's group. Running multiple application replicas with the same group name lets them join the same consuming group. An analytics application can use a different group to receive an independent stream.

A producer can declare the groups to prepare:

~~~yaml
spring:
  cloud:
    function:
      definition: orderPublisher
    stream:
      bindings:
        orderPublisher-out-0:
          destination: orders
          producer:
            required-groups: billing,analytics
~~~

**required-groups** is the kebab-case form of **requiredGroups**. Its value is a comma-separated list of group names. These names must match the exact group names used by the corresponding consumers.

The property belongs under **producer** on an output binding. Placing it on an input binding or under **consumer** does not produce the intended behavior. If multiple output bindings are used, each binding can declare its own list of required groups because each destination has a different set of consumers.

## 2. The problem when consumers start after producers

Consider an order flow with two receiving groups:

~~~mermaid
flowchart TD
    P[Order producer] --> D[Destination orders]
    D --> B[Group billing]
    D --> A[Group analytics]
    B --> B1[Billing consumers]
    A --> A1[Analytics consumers]
~~~

Suppose the producer starts at 09:00, while the billing group is only deployed at 09:10. The system must ensure events emitted during the first 10 minutes can still be processed by billing.

The outcome depends on the broker:

- With RabbitMQ, if the group's queue does not yet exist when the producer sends, the exchange has no corresponding queue to route messages to. **requiredGroups** lets the binder create the queue and binding before the producer starts sending.
- With Kafka, messages are stored in the topic log. A new consumer group can read data still within retention based on its starting offset without needing a per-group queue.
- With Pulsar, subscriptions store cursors and backlogs. If no subscription exists yet when the producer emits, the topic does not retain messages beyond backlog by default; a new subscription also normally starts at the latest position. Subscriptions and retention must be handled according to Pulsar policies.

Therefore, the goal of required groups is to ensure receiving resources fit the broker's model. It does not replace retention, offsets, subscription cursors, acknowledgments, or expiration policies.

## 3. Configuring requiredGroups for RabbitMQ

The RabbitMQ binder maps a destination to an exchange. For each consumer group, the binder creates a dedicated queue and binds that queue to the exchange. The default queue name follows the pattern:

~~~text
<prefix><destination>.<group>
~~~

If the output binding declares **requiredGroups**, the Rabbit binder provisions a queue and binding for each group when the producer binding is created. As a result, the queue already exists before the producer sends its first message, even if the consumer application is not running yet.

Producer example:

~~~yaml
spring:
  cloud:
    function:
      definition: orderPublisher
    stream:
      bindings:
        orderPublisher-out-0:
          destination: orders
          producer:
            required-groups: billing,analytics
~~~

The Rabbit binder can create the queues corresponding to destination **orders** and groups **billing** and **analytics**. The billing consumer uses:

~~~yaml
spring:
  cloud:
    function:
      definition: billingConsumer
    stream:
      bindings:
        billingConsumer-in-0:
          destination: orders
          group: billing
~~~

The analytics consumer uses the same destination with its own group:

~~~yaml
spring:
  cloud:
    function:
      definition: analyticsConsumer
    stream:
      bindings:
        analyticsConsumer-in-0:
          destination: orders
          group: analytics
~~~

Each queue holds a copy of messages for its corresponding group. Multiple instances in the same group compete to consume from the same queue; two different groups receive independent copies.

### Conditions for the queue to retain messages

Pre-creating the queue only solves the routing condition. For data to survive while the consumer is down, verify these additional requirements:

1. The queue is declared durable and the broker has appropriate storage configuration.
2. The producer sends persistent messages. The Rabbit binder uses delivery mode **PERSISTENT** by default, though verify if the application customized this setting.
3. The queue has not been deleted by an auto-delete or expires policy.
4. Messages have not exceeded their TTL and the queue has not exceeded size or count limits.
5. The exchange, queue, and binding have proper permissions; the producer is permitted to publish, and the binder is permitted to declare resources if auto-provisioning.
6. The consumer ACKs only after successful processing according to the application's delivery design.

A durable queue and a persistent message are two separate properties. A durable queue preserves the queue definition across broker restarts; a persistent message instructs the broker to persist the message durably. Both must be evaluated alongside queue type, replication, publisher confirms, and RabbitMQ operational policies.

### Configuring queues and DLQ for required groups

The Rabbit binder provides extended properties for queues created via required groups. For example:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderPublisher-out-0:
          destination: orders
          producer:
            required-groups: billing,analytics
      rabbit:
        bindings:
          orderPublisher-out-0:
            producer:
              auto-bind-dlq: true
              ttl: 3600000
              max-length: 100000
~~~

This illustrates binder options; check the exact namespace and support level in your Rabbit binder version. Properties such as TTL, max length, DLX, and DLQ apply only to queues provisioned for required groups. They are not general retention settings on the exchange.

When using pre-provisioned RabbitMQ infrastructure, automatic queue or exchange declaration may need to be disabled using the appropriate properties, such as **bindQueue: false**. In that case, the operations team must ensure exchanges, queues, and bindings already exist with the exact names and routing keys. **requiredGroups** cannot create resources if the binder is configured not to declare them.

## 4. Conditions under the Kafka binder

Kafka organizes data as topic logs and partitions. Independent consumer groups read the same topic using their own offsets; the broker does not create a physical queue per group. Therefore, Kafka does not need a per-group queue provisioning mechanism like RabbitMQ.

When a producer sends events to the **orders** topic, records are retained according to topic retention. A new consumer group can read existing records if its initial offset points to the right position. With the Kafka binder, the **startOffset** property controls the starting position for a group without committed offsets:

- **earliest**: starts from the earliest record still available in the partition.
- **latest**: starts from the end of the log and receives only new records written after that point.

In the Kafka binder, an input binding with an explicit group defaults to **earliest** for a new group; an anonymous binding defaults to **latest**. You can set it explicitly:

~~~yaml
spring:
  cloud:
    function:
      definition: billingConsumer
    stream:
      bindings:
        billingConsumer-in-0:
          destination: orders
          group: billing
      kafka:
        bindings:
          billingConsumer-in-0:
            consumer:
              start-offset: earliest
~~~

With this configuration, a new **billing** group starts from the earliest records still in the topic. It cannot read data already purged by retention. If the group already has committed offsets, normal resumption uses those offsets; **startOffset** does not automatically rewind an active group.

### Does requiredGroups pre-create Kafka groups?

Do not interpret **requiredGroups** as a request to pre-create consumer group metadata or separate queues on Kafka. A Kafka group is recognized by the broker through consumer activity and offset commits. The producer writes to the topic; groups track their own read progress.

With Kafka, ensure:

- The topic is created and has enough partitions.
- Retention is long enough to cover the window during which consumers may start late or go offline.
- New groups use **startOffset** or appropriate offset configuration.
- ACL permissions allow consumers to read the topic and use the group.
- The broker's offset retention policy does not expire progress within the required window.

Because topic retention applies to the log, every group can only read records that still exist. **requiredGroups** neither extends retention nor creates a separate log copy per group. Verify the behavior of your specific Kafka binder version if the application uses this common property; do not rely on it in place of topic retention or offset configuration.

## 5. Conditions under the Pulsar binder

Apache Pulsar uses topics and subscriptions. A subscription has a name and a cursor storing consumption position; multiple consumers in the same subscription share work according to the subscription type. A durable subscription can resume after consumer disconnection and broker restarts.

An important difference is that a new subscription typically starts at **latest**. If a producer already sent messages before the subscription was created, a new consumer may start after those messages. In addition, by default Pulsar only keeps messages belonging to the backlog of at least one subscription. A topic without a subscription does not normally retain messages for a future subscription to re-read unless the namespace has an appropriate retention policy.

Therefore, with Pulsar:

1. Create durable subscriptions before the producer starts emitting if a group needs to receive all events from the time the producer launches.
2. If a subscription is only created afterward, consider configuring the initial position as **Earliest** and enabling namespace/topic retention so prior records still exist.
3. Check backlog quotas, TTL, retention size/time, and topic deletion policies.
4. Keep subscription names stable across deployments so cursors resume accurately.
5. Choose a subscription type matching concurrency and ordering requirements.

In Spring Boot for Apache Pulsar, the subscription initial position property can be configured through consumer properties. For example:

~~~yaml
spring:
  pulsar:
    consumer:
      subscription:
        initial-position: earliest
        mode: durable
~~~

Exact property names and locations may differ when configured through the Pulsar binder's extended binding properties. Confirm against the documentation for the Spring Cloud Stream and Spring for Apache Pulsar versions you use. The example above illustrates Spring Boot Pulsar-level configuration; it is not **requiredGroups** configuration.

Current Pulsar binder documentation describes the topic provisioner, subscriptions, and client/binder properties, without describing **requiredGroups** as a mechanism for pre-creating per-group subscriptions comparable to the Rabbit binder. Therefore, do not rely on this property to guarantee data delivery for late-starting Pulsar groups. Provision subscriptions via administrative tools or deploy consumers ahead of producers, while configuring retention and initial position according to replay needs.

## 6. Comparing requiredGroups and equivalent mechanisms

| Aspect | RabbitMQ binder | Kafka binder | Pulsar binder |
|---|---|---|---|
| Data storage model | Exchange routes messages to queues. | Topic log stores records per partition. | Topic stores messages; subscription holds cursor and backlog. |
| Group receiving resource | Dedicated queue per group. | Consumer group offsets on the topic. | Named subscription. |
| Explicit role of requiredGroups | Provisions queue/binding before producer sends. | Does not create separate queues or group offsets; topic retention and offsets govern late reads. | No documented binder mechanism equivalent to provisioning subscriptions via requiredGroups. |
| Condition for a late-starting group to read data | Queue already existed before publish. | Records remain within retention and group starts from the right offset. | Subscription already existed, or retention keeps data and new subscription starts from earliest. |
| Where lifecycle is managed | Queue, exchange, binding, TTL, DLQ, and policies. | Topic, partition, retention, group offset, and ACLs. | Topic, subscription, cursor, retention, TTL, and backlog quota. |

One easily misunderstood distinction is the word **durable**. RabbitMQ durable queues, Kafka log retention, and Pulsar durable subscriptions all help recover data in their own ways. They are not the same mechanism and cannot be substituted for one another via a single configuration property.

## 7. Real-world deployment scenario

Suppose a sales system has producer **order-api** and two consumers:

- **billing** generates invoices.
- **analytics** updates reports.

The requirement is that both groups must receive every order from the moment the producer system is deployed, even if a consumer is deployed later.

### If using RabbitMQ

The producer output binding declares:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orderPublisher-out-0:
          destination: orders
          producer:
            required-groups: billing,analytics
~~~

The Rabbit binder creates the exchange and queues/bindings for both groups as configured. Consumers can be deployed later; messages wait in their respective queues within TTL, queue policy, and capacity limits.

### If using Kafka

The producer sends to the **orders** topic. The topic needs sufficiently long retention. Consumers **billing** and **analytics** use separate groups. If the groups start for the first time with **startOffset: earliest**, they read records still present in the topic. There is no need to declare `requiredGroups` to create queues. If retention already purged old records before consumers start, they cannot be recovered from that topic.

### If using Pulsar

Create the two durable subscriptions **billing** and **analytics** before the producer emits events, or configure appropriate retention and initial position **Earliest** for subscriptions created later. If the topic has no subscriptions yet and default retention does not preserve messages outside a backlog, data emitted before the subscription existed may no longer be available to read.

When switching brokers, rewrite the resource setup and test consumer creation timing. Do not simply copy the **required-groups** configuration verbatim from a RabbitMQ environment to Kafka or Pulsar.

## 8. Testing requiredGroups and late-starting consumers

Tests should simulate the actual startup order, because running producers and consumers simultaneously can hide missing receiving-resource bugs.

### General scenario

1. Start the broker and the producer application.
2. Wait for the output binding to be created and verify broker resources.
3. Emit a batch of events with distinct identifiers.
4. Keep the consumer group stopped.
5. Start the consumer after a delay.
6. Verify the group receives the events within the broker's guarantees.
7. Restart the consumer and verify progress resumes without data loss or duplicate processing outside expected policy.

### Per-binder test matrix

| Binder | Before sending | While consumer is not running | When consumer starts late |
|---|---|---|---|
| RabbitMQ | Verify exchange, queue per required group, and bindings are created. | Send messages; verify queues have ready messages. | Consumer in the right group receives backlog and ACKs after processing. |
| Kafka | Verify topic, partitions, and retention. | Send messages to topic; group metadata does not need to exist. | Start new group with appropriate startOffset; verify reading records still within retention. |
| Pulsar | Verify durable subscriptions exist, or retention is enabled if subscriptions are created later. | Send messages and inspect topic backlog/retention. | Consumer attaches to subscription with existing cursor or creates earliest subscription while data is still retained. |

With RabbitMQ, verify queue names derived from destination and group, queue durability, message persistence, TTL, expires, max length, and DLQ. Try restarting the broker in a test environment to verify resources and messages recover as configured.

With Kafka, verify offsets for a new group, startOffset, topic retention, and broker offset retention. An important test is keeping the consumer group absent, sending data, then creating the group with `earliest`; repeat with `latest` to confirm the difference.

With Pulsar, test both cases: subscription created before publishing and subscription created after publishing. For the second case, compare initial position `latest` and `earliest` when retention is enabled. If retention is disabled and no subscription exists when the producer sends, do not expect old data to remain.

### Testing counts and time boundaries

Do not verify only a single message. Send many messages with sequential event IDs, generate enough load to test backlogs, then reconcile:

- Messages successfully sent by the producer.
- Messages stored or routed by the broker per group.
- Messages received and ACKed/committed by the consumer.
- Messages remaining in backlog while the consumer is stopped.
- Messages expired or dropped due to capacity limits.
- Duplicate executions after restarts or redeliveries.

Metrics must be interpreted according to broker semantics. RabbitMQ queue depth, Kafka consumer lag, and Pulsar subscription backlog are not the same unit of measurement.

## 9. Common mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| RabbitMQ loses messages when consumer starts late | Group queue did not exist when producer sent. | Declare requiredGroups on the output binding or pre-provision queues. |
| RabbitMQ has the queue but data is gone after restart | Queue/messages are not durable or storage policy is misconfigured. | Check durable queue, persistent delivery mode, and broker config. |
| RabbitMQ queue expires before consumer deploys | TTL, expires, auto-delete, or policy deleted the queue/messages. | Adjust queue and message lifetimes for the deployment window. |
| New Kafka consumer does not read old data | startOffset is latest, retention purged records, or group already has committed offsets. | Check startOffset, resetOffsets, committed offsets, and retention. |
| requiredGroups does not create a Kafka queue | Kafka does not use separate queues per group. | Manage topic retention and group offsets. |
| New Pulsar subscription misses old messages | Subscription starts at latest or topic does not retain data without subscriptions. | Create subscriptions early or use earliest with appropriate retention. |
| New group re-reads too much data | Offset/cursor started from earliest or group identity changed. | Define replay window and desired starting position clearly. |
| Producer and consumer use different group names | Mismatched group names or environment config overrides. | Standardize group names and inspect resolved configuration. |
| Backlog is purged before processing | TTL, retention, backlog quota, or queue limits. | Size limits based on outage windows and recovery capacity. |

When investigating, first confirm destination and group names. Next inspect actual broker resources: queues and bindings in RabbitMQ, topics and offsets in Kafka, topics/subscriptions/cursors in Pulsar. Finally inspect producer and consumer application configuration; a correctly spelled YAML value does not prove broker resources were created as expected.

## 10. Selection and operational procedure

Before enabling required groups, answer:

1. Which business groups need to receive the same event?
2. From what point in time must those groups receive data?
3. What is the maximum delay before a consumer starts?
4. Does the broker maintain per-group receiving resources or use logs/subscriptions?
5. Under what limits can data expire or be evicted?
6. Who is responsible for provisioning, monitoring, and deleting resources when a group is retired?

Apply by binder:

- **RabbitMQ:** use **requiredGroups** when the producer must pre-create queues/bindings for known groups. Verify durability, persistent delivery, TTL, expires, queue limits, and DLQ.
- **Kafka:** rely on topic logs, retention, and initial offsets. Use stable groups; set **startOffset** explicitly for new groups if reading historical data is required.
- **Pulsar:** manage durable subscriptions, initial position, and namespace retention. Create subscriptions before publishing if an initial backlog must be guaranteed; if created afterward, ensure data stays within retention and select earliest when appropriate.

Do not place every group name into `requiredGroups` out of habit. Only declare groups that require receiving data before consumers run and are managed by operations. An inaccurate or stale group list can create unnecessary resources, increasing storage usage and cleanup overhead.

## 11. Pre-deployment checklist

- [ ] **requiredGroups** is declared on the right output binding if the binder supports the required behavior.
- [ ] The group list is comma-separated and matches the input binding groups verbatim.
- [ ] Whether consumers start before or after producers has been determined.
- [ ] RabbitMQ already has queues/bindings for each required group before publishing.
- [ ] RabbitMQ queues and messages have appropriate durability; TTL, expires, max length, and DLQ have been reviewed.
- [ ] Kafka topic retention is long enough and `startOffset` for new groups is appropriate.
- [ ] Pulsar durable subscriptions are created or retention/initial position is configured for late-starting consumers.
- [ ] Do not assume `requiredGroups` creates the same type of resource across Kafka, RabbitMQ, and Pulsar.
- [ ] Integration tests have run in producer-first, consumer-second order.
- [ ] Backlog/lag/queue depth metrics and alerts are in place when consumers stop processing.
- [ ] A process exists to decommission unused groups and broker resources.

**requiredGroups** is a producer-side property meant to prepare data reception for known groups, yet its operational meaning must be read alongside the binder. RabbitMQ uses queues and bindings, so it can provision resources for each required group. Kafka uses topic logs and offsets, while Pulsar uses subscription cursors and retention; those two binders require configuring resources and starting positions via their own mechanisms. Understanding the exact differences enables the system to handle late-starting consumers without relying on a single delivery assumption across all brokers.

## References

- [Spring Cloud Stream — Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Consumer Groups](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/consumer-groups.html)
- [RabbitMQ Binder — Producer Properties](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/prod-props.html)
- [RabbitMQ Binder — Existing Queues and Exchanges](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview/existing-destinations.html)
- [Kafka Binder — Resetting Offsets](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/reset-offsets.html)
- [Pulsar Binder](https://docs.spring.io/spring-cloud-stream/reference/pulsar/pulsar_binder.html)
- [Apache Pulsar — Message Retention and Expiry](https://pulsar.apache.org/docs/next/cookbooks-retention-expiry/)
- [Apache Pulsar — Messaging and Subscriptions](https://pulsar.apache.org/docs/4.0.x/concepts-messaging/)
