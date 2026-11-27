# Observing Broker Resources Created and Cross-Checking Results

When a Spring Cloud Stream application starts, its bindings are connected by the binder to corresponding resources on the broker. Depending on the messaging technology, those resources may be topics, consumer groups, exchanges, queues, bindings, or subscriptions. Inspecting the broker directly confirms that the application configuration was mapped properly, that publisher and subscriber use the same destination, and catches discrepancies in groups, partitions, and resource creation permissions early.

This lesson walks through observing resources before and after running the application, emitting a test message, tracking consumption status, and cross-checking results on Kafka, RabbitMQ, or Pulsar. The illustrative commands use each broker's standard CLI; actual resource names may vary depending on binder version, naming configuration, and deployment environment.

## Learning Objectives

After this lesson, you will be able to:

- Identify the broker resources required by an input or output binding.
- Predict the resources created from a destination and consumer group.
- Use Kafka, RabbitMQ, and Pulsar administration tools to list, describe, and inspect resources.
- Cross-check Spring Cloud Stream configuration against observed topics, exchanges, queues, partitions, or subscriptions.
- Distinguish between resource state, consumer connection state, and processed message state.
- Narrow down the root cause when a resource does not appear or has an unexpected state.

## 1. From Bindings to Broker Resources

Spring Cloud Stream provides a unified binding model on the application side. The binder translates bindings into constructs understood by a specific broker. Consequently, the same destination and group configuration can create different kinds of resources.

A consuming binding typically has two key properties:

- `destination` specifies the message stream the application subscribes to.
- `group` specifies the consumer group with its own independent consumption progress.

For example, an application has a consumer function named `inventory`:

~~~java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class InventoryConfiguration {

    @Bean
    Consumer<OrderCreated> inventory() {
        return event -> {
            System.out.println("Received order: " + event.orderId());
        };
    }
}
~~~

The bean name `inventory` creates the default input binding `inventory-in-0`. The following configuration connects that binding to destination `orders` and group `inventory`:

~~~yaml
spring:
  cloud:
    function:
      definition: inventory
    stream:
      bindings:
        inventory-in-0:
          destination: orders
          group: inventory
~~~

If the application publishes events via `StreamBridge`, an output binding can be configured as follows:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders
~~~

The publisher sends using the configured binding name:

~~~java
streamBridge.send("orders-out-0", event);
~~~

In this example, both publisher and consumer use destination `orders`. Consumer group `inventory` defines the subscriber's subscription. An output binding does not need a group declared.

### Expected Resources by Broker

| Broker | Destination usually maps to | Group usually maps to | What to observe |
|---|---|---|---|
| Kafka | Topic | Consumer group and the group's offsets | Topic name, partition count, replication factor, consumer group, offsets, and lag |
| RabbitMQ | Exchange | Queue bound to the exchange | Exchange, queue, binding, routing key, consumers, and message counts |
| Pulsar | Topic | Subscription | Full topic name, subscription, consumers, backlog, and subscription type |

The mappings above are a conceptual model. RabbitMQ queue names, Pulsar namespaces, resource prefixes, and how subscriptions are created can be influenced by binder configuration. When inspecting, use the actual names from application configuration and startup logs, then confirm with the broker's admin tools.

**Do not conflate destination with group.** Two applications can read from the same `orders` destination while using different groups. In Kafka, they have separate consumer groups and offsets; in RabbitMQ, they usually have separate queues each bound to the exchange; in Pulsar, they have separate subscriptions on the same topic. If two instances of the same service share a group, they participate in load sharing within that same subscription.

## 2. Preparing a Comparable Run

Before starting the application, record the effective configuration and initial broker state. Capturing the initial state helps distinguish resources left over from previous runs from resources provisioned during the current run.

Use a consistent example:

| Property | Value |
|---|---|
| Consumer function | `inventory` |
| Input binding | `inventory-in-0` |
| Destination | `orders` |
| Consumer group | `inventory` |
| Test event | `OrderCreated` |
| Goal | Confirm the consumer connects to the right destination and the broker retains consumption state properly |

Check the following points in the loaded configuration:

1. The function bean exists and is activated by `spring.cloud.function.definition`.
2. The input binding name is derived properly from the function name.
3. Producer and consumer destinations match if they need to exchange the same stream.
4. The group has a stable name if the consumer needs to preserve progress across restarts.
5. The application uses the right binder and broker address for the environment being tested.
6. Profiles, environment variables, or deployment configurations do not override destination and group with different values.

Do not just read the YAML file in source code. Compare against the effective configuration of the running process, because profiles and environment variables can change the final values.

## 3. Observing Kafka

With the Kafka binder, destination `orders` is typically the topic `orders`. Consumer group `inventory` stores reading progress via per-partition offsets. A topic can exist before the consumer group appears; the broker usually records the group only after a consumer joins, and offsets only appear after progress is committed.

### Listing and Describing Topics

With the Kafka CLI, run:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 --list
~~~

After the application starts, describe the topic:

~~~bash
kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic orders
~~~

Read and cross-check the output:

- `Topic`: must match the expected destination.
- `PartitionCount`: the actual partition count must align with the concurrency design.
- `ReplicationFactor`: number of replicas for each partition.
- `Leader`, `Replicas`, `Isr`: indicate replica distribution and synchronization status.
- If the topic does not exist, check whether the binder is permitted to create topics or whether resources must be pre-created by an administrator.

For example, if a topic has three partitions, a single consumer group can distribute those three partitions across at most three active consumers in that group at a time. Adding consumers beyond the partition count does not automatically increase the partition count.

### Checking Consumer Groups and Offsets

List groups:

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --list
~~~

Describe the group:

~~~bash
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group inventory
~~~

Columns commonly checked:

| Field | Meaning |
|---|---|
| `GROUP` | Consumer group name |
| `TOPIC` | Topic the group is reading |
| `PARTITION` | Partition being tracked |
| `CURRENT-OFFSET` | Committed offset |
| `LOG-END-OFFSET` | Latest offset currently on the partition |
| `LAG` | Number of records the group is behind the end of the log |
| `CONSUMER-ID` / `HOST` | Consumer and host currently participating in the group |

If the group has not appeared yet, check whether the consumer was activated and connected successfully. If the group exists but has no offsets, the consumer may not have processed and committed any records yet. If lag rises continuously, publishing rate is outpacing consumption or the consumer is hitting errors.

### Cross-Checking Partitions

Partition count is not just a display number. Cross-check it against:

- The expected number of consumer instances running concurrently in one group.
- Binding or binder partition configuration.
- Application scalability requirements.
- Partition keys used to preserve ordering for events sharing an entity.

If configuration requests more partitions but the broker keeps the old count, check administrative permissions and the Kafka binder's auto-add-partitions option. Do not increase partitions on a shared environment without evaluating the impact on ordering and key distribution.

## 4. Observing RabbitMQ

With the RabbitMQ binder, a destination is typically mapped to an exchange. When a consumer group is present, the binder normally provisions a queue for the group and binds that queue to the exchange. Multiple independent groups can have separate queues so each group receives a copy of messages. Actual queue names are usually constructed from the destination and group, though they can vary by prefix or binder configuration.

### Listing Exchanges

Run on the RabbitMQ server or inside the broker container:

~~~bash
rabbitmqctl list_exchanges name type durable auto_delete
~~~

Locate the exchange corresponding to destination `orders`. Check the exchange type, durable flag, and auto-delete flag against the application design.

### Listing Queues and Message State

~~~bash
rabbitmqctl list_queues name durable auto_delete consumers messages_ready messages_unacknowledged
~~~

Cross-check the fields:

- `name`: the queue created for the group.
- `durable`: whether the queue survives broker restarts as configured.
- `auto_delete`: whether the queue can be deleted once the last consumer stops.
- `consumers`: number of currently subscribed consumers.
- `messages_ready`: number of messages waiting to be delivered to consumers.
- `messages_unacknowledged`: number of messages delivered but not yet acknowledged.

A queue with `messages_ready=0` does not necessarily mean the publisher has not sent messages. The consumer may have already received and processed them quickly. Also inspect `messages_unacknowledged`, publish/deliver/ack counters in the Management UI, and application processing logs.

### Checking Bindings Between Exchange and Queue

~~~bash
rabbitmqctl list_bindings source_name source_kind destination_name destination_kind routing_key
~~~

For group `inventory`, verify that the group's queue is bound to the corresponding exchange. If the exchange exists but no queue is bound, messages may not reach subscribers. Check routing keys and binding arguments when the application uses key-based or partitioned routing.

In the RabbitMQ Management UI, commonly used sections are:

- **Exchanges**: view exchanges, exchange types, durability, and binding counts.
- **Queues and Streams**: view queues, consumers, ready messages, and unacknowledged messages.
- **Bindings**: view source, destination, and routing key of each binding.

A queue with a group typically persists longer than an anonymous queue. When no group is configured, the binder may use a temporary or randomly named queue; that queue may disappear when the consumer stops. Therefore, specify a group before concluding a queue is missing.

## 5. Observing Apache Pulsar

With the Pulsar binder, a destination maps to a topic. A consumer group is represented by a subscription name. The full topic name has the form:

~~~text
persistent://<tenant>/<namespace>/<topic>
~~~

In a typical local environment, topics may live under the `public/default` namespace, for example `persistent://public/default/orders`. Other environments may use dedicated tenants or namespaces; always take the value from actual configuration.

### Listing Topics

~~~bash
pulsar-admin topics list public/default
~~~

Find the `orders` topic. If it is missing, check the namespace, topic type (persistent or non-persistent), access permissions, and the broker's auto-topic-creation policy.

### Viewing Subscriptions and Topic Statistics

~~~bash
pulsar-admin topics subscriptions persistent://public/default/orders
~~~

Retrieve statistics:

~~~bash
pulsar-admin topics stats persistent://public/default/orders
~~~

If the topic is partitioned, use the stats command for partitioned topics:

~~~bash
pulsar-admin topics partitioned-stats persistent://public/default/orders
~~~

In the statistics, focus on:

- The list of subscriptions and the subscription name matching the group.
- Connected consumers and subscription type.
- The subscription's backlog.
- Message in/out rates and stored message count.
- Per-partition status if the topic is partitioned.

A subscription may only be created when a consumer connects for the first time. Thus, a topic existing without the subscription appearing can indicate that the consumer has not started successfully, the group was not applied, or the application is connecting to a different namespace.

Pulsar supports subscription types such as Exclusive, Shared, Failover, and Key_Shared. The subscription type determines how multiple consumers in the same subscription receive messages. When cross-checking against your load-sharing design, inspect the actual subscription type rather than relying solely on the group name.

## 6. Emitting an Event and Confirming the Path

Seeing resources appear only confirms the provisioning step. To prove the flow works, emit an event with an easily searchable identifier, for example:

~~~json
{
  "eventId": "evt-1001",
  "orderId": "order-1001",
  "occurredAt": "2026-11-24T09:00:00Z",
  "schemaVersion": 1
}
~~~

Follow this sequence:

1. Start the broker and wait until it reports ready.
2. Start the Spring Cloud Stream consumer and wait for logs indicating bindings have connected.
3. Inspect broker resources and record the topics/exchanges/queues/subscriptions that appeared.
4. Send an event through the publisher, for instance via `StreamBridge` with an output binding pointing to `orders`.
5. Search for `eventId=evt-1001` in consumer logs or an appropriate message inspection tool.
6. Re-check offsets, queue counters, or subscription backlog.
7. Cross-check application results against broker metrics.

With Kafka, you can use the console consumer to read a sample using a dedicated inspection group:

~~~bash
kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic orders --from-beginning --max-messages 5 --group inspect-orders-unique
~~~

Use a unique inspection group name—do not use the application's `inventory` group. If you use the application's group to read via CLI tools, consumption progress can be altered and skew verification results.

With RabbitMQ, observe message counters on the group's queue in the Management UI or use an admin tool suitable for your running version. Do not acknowledge or consume messages in a way that alters queue state before recording the metrics to cross-check.

With Pulsar, inspect subscriptions and backlogs with `pulsar-admin topics stats`. If using `pulsar-client consume` to read a sample, create a dedicated inspection subscription and remember that doing so creates a new subscription on the broker.

**Expected outcome:** the publisher sends to the right destination; the broker receives the message; the corresponding consumer group/subscription appears; the subscriber receives the expected payload; and offset, queue, or backlog state changes consistently with processing.

## 7. Observing Consumer Stop and Restart

A useful verification is watching messages while the consumer is temporarily stopped:

1. Record the initial metrics of the topic, queue, or subscription.
2. Stop the consumer application gracefully.
3. Emit a few new events from the publisher.
4. Observe messages being retained or backlog increasing according to broker policy.
5. Restart the consumer with the same destination and group.
6. Verify the consumer resumes processing and the backlog decreases.

Expected behavior differs across brokers:

| Broker | While consumer is stopped | When consumer restarts |
|---|---|---|
| Kafka | Records remain stored per retention; group lag can increase once the group already has offsets | Consumer resumes from committed offsets according to reset config and group state |
| RabbitMQ | Messages can accumulate in durable queues; temporary queues may be deleted depending on configuration | Consumer reconnects to the surviving queue and processes queued messages |
| Pulsar | Subscription backlog can grow according to retention and subscription policies | Consumer resumes reading from the subscription cursor |

Do not use stopping the consumer to conclude that messages are guaranteed to be kept indefinitely. Kafka retention, RabbitMQ queue durability/TTL/overflow policies, and Pulsar retention/expiry policies can all cause messages to be deleted or expire.

When the application restarts, check whether resources retain their exact names and states. If every restart creates a new queue or subscription, check whether the group is stable, whether profiles override configuration, and whether the binder is creating an anonymous subscription.

## 8. Cross-Checking Results and Finding Discrepancies

Record results using a consistent template to compare configuration against the broker:

| Item | Expected config | Observed result | Assessment |
|---|---|---|---|
| Binder | Kafka / RabbitMQ / Pulsar | Actual binder | Match / mismatch |
| Destination | `orders` | Topic / exchange / full topic | Match / mismatch |
| Group | `inventory` | Consumer group / queue / subscription | Match / mismatch |
| Partitions | Expected count | Actual count | Match / mismatch |
| Consumer connection | One or more instances | Active consumers | Match / mismatch |
| Message | Test event sent | Offset / ready / backlog / log | Received / pending / not seen |

Some common scenarios:

| Symptom | Causes to check |
|---|---|
| No resources visible | Function not activated; wrong binding name; application failed to start; wrong broker/namespace; binder does not auto-provision or lacks creation permissions |
| Kafka has topic but no group | Consumer has not joined the group; function not running; group name differs from config; consumer has not committed offsets yet |
| Kafka has group but lag grows | Consumer processing slowly, failing repeatedly, missing instances, or partitions not distributed as expected |
| RabbitMQ has exchange but no queue | Consumer group not created; temporary queue deleted; queue provisioning failed |
| RabbitMQ has queue but no binding | Queue not bound to the exchange or routing key mismatch |
| Pulsar has topic but no subscription | Consumer not connected; group not applied; wrong tenant/namespace; or subscription only created when consumer starts |
| Resource appears with a different name | Prefix, group name, namespace, profile, or binder configuration changed the actual name |
| Resource exists but has no messages | Publisher has not sent yet; producer and consumer destinations differ; messages already processed quickly; wrong routing/partition/subscription |
| New queue or subscription appears after each run | Consumer uses an anonymous group or group name changes between deployments |

When discrepancies are found, inspect in this order:

1. **Effective configuration:** destination, group, function definition, binder, and active profile.
2. **Startup logs:** whether bindings were created, broker connection succeeded, or provisioning errors occurred.
3. **Broker resources:** name, type, partitions, queue bindings, or subscriptions.
4. **Access permissions:** whether the application account has permission to connect, declare, write, and read the required resources.
5. **Message flow:** whether the publisher sends to the right destination, whether the subscriber receives it, and how consumption state changes.

Do not rush to manually create a new resource when resource names do not match. First identify the effective configuration and the binder's naming rules; creating an extra misnamed topic, queue, or subscription can split the system into fragmented streams that are hard to trace.

## 9. Provisioning Permissions and Operational Responsibilities

A binder can auto-declare or request the broker to create resources, but this capability depends on the binder, version, configuration, and credentials' permissions. In production environments, organizations often pre-create topics, exchanges, queues, namespaces, or subscriptions before deploying applications.

Permissions to review include:

- **Kafka:** permission to describe topics, create topics if permitted, produce records, and join/read consumer groups.
- **RabbitMQ:** `configure` permission to declare exchanges/queues/bindings, `write` to publish, and `read` to consume.
- **Pulsar:** namespace/topic access permissions and producer/consumer roles aligned with security policy.

If the application only has read and write permissions without resource declaration permissions, the broker may reject the provisioning step. In that case, logs usually contain authorization or access-denied errors. Coordinate with the broker administrator to pre-create resources and grant least-privilege permissions.

Do not leave debug logging enabled long-term in production. When diagnosing, you can briefly raise log levels for Spring Cloud Stream and binder packages, collect the needed details, and restore normal operational log levels. Logs may contain sensitive payloads or metadata, so follow the system's logging policy.

## 10. Hands-On Exercise: Cross-Checking One Destination Across Three Brokers

Use the same consumer application with destination `orders` and group `inventory`. Run each broker in a separate test environment to avoid confusing resources across environments.

**Step 1 — Predict**

Before running, write down the resources you expect:

- Kafka: topic `orders`; consumer group `inventory` after the consumer joins.
- RabbitMQ: exchange for destination `orders`; queue for group `inventory`; binding linking the queue to the exchange.
- Pulsar: topic `orders` in the configured tenant/namespace; subscription `inventory` after the consumer connects.

**Step 2 — Snapshot Before Running**

Use the resource listing commands from the sections above. Note which resources already existed beforehand.

**Step 3 — Start the Application**

Run the consumer, wait for readiness, and save the binding logs. Re-snapshot the resource list to identify newly created resources.

**Step 4 — Emit and Process an Event**

Send an `OrderCreated` event with a distinct `eventId`. Verify consumer logs and message state on the broker.

**Step 5 — Check Lifecycle Behavior**

Stop the consumer, emit additional events, observe backlog or lag, then restart with the same group. Record whether resources are reused and whether the consumer resumes from the appropriate state.

**Step 6 — Compare**

Complete the following table with actual results:

| Aspect | Kafka | RabbitMQ | Pulsar |
|---|---|---|---|
| Destination resource | Topic | Exchange | Topic |
| Group resource | Consumer group/offsets | Queue and binding | Subscription |
| Partitioning info | Partition | Not equivalent to Kafka partitions in all setups | Partitioned topic if configured |
| Backlog indicator | Consumer lag | Ready / unacknowledged | Subscription backlog |
| State after restart | Offset/group | Queue and messages | Subscription cursor |
| Observed discrepancies | Record results | Record results | Record results |

Upon completion, you should be able to explain which resources are created by the binder, which are created by the broker under its own policies, how groups are represented in each broker, and which metrics prove the subscriber received or still has pending messages.

## Conclusion

Observing the broker is an essential verification step after configuring bindings in Spring Cloud Stream. Destination indicates the data stream, group defines independent consumption scope, and the binder determines how those concepts map to concrete resources.

Kafka should be inspected via topics, partitions, consumer groups, and offsets; RabbitMQ via exchanges, queues, bindings, and message counters; Pulsar via topics, subscriptions, consumers, and backlogs. When cross-checking configuration against broker state, verify both message lifecycle and restart behavior to confirm the application uses the intended resources and continues processing as designed.
