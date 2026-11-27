# Evaluating Partner Binders Such as Azure Event Hubs, Pub/Sub, and Solace

Spring Cloud Stream provides a unified programming model using Supplier, Function, Consumer, and bindings. Binders connect those bindings to specific messaging systems. As a result, most business logic can be preserved when switching middleware, yet you cannot assume every broker shares the same semantics for partitions, consumer groups, checkpoints, acknowledgements, retries, schemas, or replays.

Azure Event Hubs, Google Cloud Pub/Sub, and Solace PubSub+ all have Spring Cloud Stream binders listed as partner-maintained. This means the binder is maintained by the vendor or a partner, with its own release schedule, compatibility matrix, and support channels. During evaluation, examine the messaging service, the binder, the Spring Boot/Spring Cloud versions, and production operations together.

This lesson compares the three binders across data models, binding mappings, delivery semantics, partitioning, errors, and operability. At the end, there is an example of an application using multiple binders simultaneously and a checklist for selecting a solution.

## Learning objectives

After this lesson, you can:

- Explain the role of partner-maintained binders in the Spring Cloud Stream ecosystem.
- Distinguish Event Hubs partitioned logs, Pub/Sub topics/subscriptions, and Solace topics/queues.
- Evaluate consumer groups, checkpoints, acknowledgements, ordering, and partitioning.
- Choose between connecting to Azure Event Hubs via its dedicated binder or its Kafka endpoint.
- Evaluate the Google Pub/Sub binder's limitations regarding partitioning and exactly-once.
- Understand how Solace maps consumer groups to durable queues and how to use partitioned queues.
- Configure multiple binders in a single Spring Cloud Stream application.
- Plan testing and operations before taking a partner binder into production.

## 1. Partner binders in Spring Cloud Stream

Spring Cloud Stream defines the Binder SPI to connect applications to middleware. The application declares functions and bindings; the binder creates producers/consumers, maps destinations, and sends/receives messages via the broker's client.

Spring Cloud Stream lists core binders such as RabbitMQ, Apache Kafka, Kafka Streams, and Apache Pulsar. Azure Event Hubs, Google Pub/Sub, and Solace PubSub+ are listed as partner-maintained. Before choosing a binder, verify:

1. Who maintains the source code and releases the binder.
2. Which versions of Spring Cloud Stream, Spring Boot, and Java the binder supports.
3. Whether key broker features are exposed by the binder.
4. Which properties are common Spring Cloud Stream properties and which exist only in that binder.
5. Upgrade paths, security support, issue trackers, and release schedules.

The partner-maintained label does not mean a binder is unusable. It reminds implementers to verify compatibility matrices and support responsibilities per vendor.

### Integration models of the three binders

| Binder | Main integration component | Broker model | Suitable for |
|---|---|---|---|
| Azure Event Hubs | Spring Integration Event Hubs Channel Adapters | Namespace, event hub, and partitioned log | Telemetry ingestion, event streaming, and data pipelines on Azure |
| Google Cloud Pub/Sub | Spring Integration Pub/Sub Channel Adapters | Topic and subscription | Distributed pub/sub, subscription-based fan-out, and Google Cloud service integration |
| Solace PubSub+ | Solace Java API/JCSMP and Spring Cloud Stream Binder | Topic, durable queue, topic subscription, and message VPN | Event mesh, topic-based routing, and guaranteed delivery via queues |

All three can accept function bindings, but the underlying concepts are not uniform. For instance, Event Hubs consumer groups are tied to checkpoints and partition ownership; Pub/Sub groups map to subscriptions; Solace groups map to durable queues.

## 2. Quick comparison by semantics

| Criterion | Azure Event Hubs | Google Cloud Pub/Sub | Solace PubSub+ |
|---|---|---|---|
| Primary model | Partitioned event log | Topic and subscription | Topic combined with queue |
| Consumer group unit | Consumer group | Subscription | Group's durable queue |
| Consumer progress | Per-partition checkpoint, usually stored in Azure Blob Storage | Ack and ack deadline on subscription | Broker acknowledgement on queue |
| Parallel distribution | Partition ownership and leases | Subscriber clients; ordering key is not a partition | Multiple consumers on queue; broker distributes per access mode |
| Ordering | Within a single partition | By ordering key if enabled and published in the same region | Per queue/partitioned queue semantics and broker config |
| Spring Cloud Stream partition abstraction | Binder supports Event Hubs physical partitions | Binder does not currently support partitioning | Spring Cloud Stream partitioning abstraction is not supported; broker has its own partitioned queues |
| Retry/DLQ | Retries/checkpoints via Event Processor and app; design poison-event handling separately | Redelivery, retry policy, and dead-letter topic | Redelivery, error queue, and Dead Message Queue |
| Exactly-once | Not inferred from checkpoints; check idempotency and separate Kafka transaction paths | Service supports exactly-once for pull subscriptions; binder has acknowledgement API limitations | Has its own broker transaction/ack semantics; not equivalent to end-to-end exactly-once |
| Supporting resources | Azure Storage for checkpoints and leases | Topic, subscription, IAM, and quotas | Message VPN, topic, queue, ACL, and spool |

This table is a conceptual map. Exact configuration must still be verified against the binder version and service tier.

## 3. Azure Event Hubs Binder

Azure Event Hubs is a partitioned event ingestion and retention service. A namespace contains multiple event hubs; an event hub corresponds to a topic from a Kafka perspective. Consumers read from partitions by offset and process data within the retention window.

### How the binder works

The Spring Cloud Azure Event Hubs Binder is built on Spring Integration Event Hubs Channel Adapters. The binder takes the destination from the binding and connects using the Event Hubs SDK. This is a dedicated Event Hubs integration, not the Kafka binder pointed at another broker address.

Key concepts:

- Namespace: the endpoint and capacity boundary of Event Hubs.
- Event hub: a stream containing events.
- Partition: an independent physical log inside an event hub.
- Consumer group: an independent read view of an application.
- Checkpoint: the position a consumer has processed up to within a partition.
- Checkpoint store: storage for checkpoints and lease information to coordinate partition ownership.

Event Hubs does not store consumer offsets inside the broker the same way Kafka does. Event Processor uses a checkpoint store, usually Azure Blob Storage, to save progress per partition. Storage leases are also used to determine which consumer owns each partition.

### Checkpoints and partition ownership

When a new consumer instance joins, Event Processor uses leases in Storage to distribute partitions. An instance can claim partitions from an instance holding more partitions. This differs from assuming a Kafka group coordinator handles all rebalancing and offset management inside the broker.

The binder supports batch consumers. When batch mode is enabled, the function receives a list of events instead of individual events. Checkpointing can be done in two ways:

- BATCH: the binder checkpoints the entire batch automatically after the batch is received.
- MANUAL: the application uses the `Checkpointer` passed via a message header to checkpoint based on business logic.

With MANUAL, checkpoint only after durable processing. If you checkpoint before writing to a database or calling a target system succeeds, the application may skip events after a failure. If processing succeeds but the checkpoint is not saved yet, events may be re-read; consumers must be idempotent.

### Dependencies and configuration

You can use the starter:

~~~xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-stream-eventhubs</artifactId>
</dependency>
~~~

Or use the binder artifact directly if the project manages dependencies separately:

~~~xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-stream-binder-eventhubs</artifactId>
</dependency>
~~~

Example consumer configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: consumeTelemetry
    stream:
      bindings:
        consumeTelemetry-in-0:
          destination: telemetry
          group: telemetry-processor
      azure:
        eventhubs:
          connection-string: AZURE_EVENTHUB_NAMESPACE_CONNECTION
          processor:
            checkpoint-store:
              account-name: CHECKPOINT_STORAGE_ACCOUNT
              container-name: eventhub-checkpoints
~~~

The values above are placeholders illustrating structure. Do not commit connection strings, Storage keys, or secrets to the repository. In production, prefer Microsoft Entra ID and managed identities where supported by infrastructure; grant least-privilege permissions for Event Hubs and the Storage checkpoint container.

The binder has per-binding properties under the prefix:

~~~text
spring.cloud.stream.eventhubs.bindings.<binding-name>.consumer.*
~~~

For example, you can configure checkpoint mode/count/interval, batch size, batch wait time, and load-balancing strategy. Consult the property table for the exact Spring Cloud Azure version in use; do not confuse this prefix with Kafka binder properties.

### Event Hubs via the Kafka endpoint

Event Hubs provides a Kafka-compatible endpoint. A Kafka application can connect via the Kafka protocol by changing bootstrap servers, port, and SASL configuration. This is an alternative to the Event Hubs Binder.

Choose the Kafka binder with the Kafka endpoint when:
- The application already depends heavily on Kafka client APIs.
- You want to reuse compatible Kafka producer/consumer configuration and tooling.
- The Kafka features used by the application fall within what Event Hubs supports.

Choose the Event Hubs Binder when:
- You want direct integration with the Azure Event Hubs SDK.
- You need Event Processor's checkpoint store and partition ownership mechanism.
- You want to use the binder's batch consumer and `Checkpointer`.
- The application needs Azure-specific properties.

Kafka compatibility does not mean Event Hubs is a full Kafka cluster. Event Hubs uses a namespace as the endpoint and does not expose all Kafka broker behaviors. Current Azure documentation marks Kafka Streams and Kafka transactions as public preview on Premium and Dedicated tiers; Kafka compression is also supported only on those two tiers, with gzip noted in the documentation. Verify your tier and feature matrix before enabling them.

### Risks to check

- An unreachable checkpoint store disrupts progress tracking or partition ownership.
- Storage leases and Event Hubs partition assignments must be observed during scaling/restarts.
- Partition count caps useful parallelism for consumers in the same consumer group.
- Batch checkpointing can confirm an entire batch; if part of the batch is not yet durably processed, redesign commit boundaries.
- Event Hubs retention and checkpoints are two different concepts: checkpoints do not keep events beyond retention.
- Kafka API compatibility has tier and feature limits; test the actual APIs your application uses.

## 4. Google Cloud Pub/Sub Binder

Google Cloud Pub/Sub is a managed messaging service built around topics and subscriptions. Publishers send messages to a topic; each subscription has its own backlog and acknowledgement progress. Multiple subscriptions on the same topic create independent fan-out: each subscription receives a logical copy of the message stream.

### How the binder works

Spring Framework on Google Cloud provides the Spring Cloud Stream Binder for Pub/Sub. The binder is built on Spring Integration Channel Adapters.

Common mappings:

- Producer binding destination is a Pub/Sub topic.
- Consumer binding destination is a topic; the binder connects to a subscription.
- Consumer group is used to derive the subscription name from the topic and group.
- Omitting group typically creates an anonymous subscription; this subscription may be cleaned up by the binder when the application stops.
- You can specify a pre-created subscription name.

For example, a group creates a subscription named in the form:

~~~text
<topicName>.<group>
~~~

A subscription is an independent delivery stream. Two applications needing fan-out copies of every message should use two different subscriptions. Instances of the same consumer group share a single subscription to process the backlog together.

### Dependencies and configuration

Binder artifact:

~~~xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-pubsub-stream-binder</artifactId>
</dependency>
~~~

Use the Spring Framework on Google Cloud BOM to manage versions of the binder and client libraries. The BOM's compatibility matrix determines supported Spring Cloud and Spring Boot versions; do not pick an arbitrary newer binder version independently.

Consumer example:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
      gcp:
        pubsub:
          bindings:
            processOrder-in-0:
              consumer:
                auto-create-resources: false
                subscription-name: orders-order-processor
~~~

In production, create topics and subscriptions through reviewed infrastructure workflows and set `auto-create-resources=false`. If allowing the binder to auto-create resources, control IAM and topic/subscription creation permissions for the service account.

Google Cloud authentication typically uses Application Default Credentials (ADC). On Google Cloud, prefer a service account attached to the workload or Workload Identity Federation. Do not store JSON private keys in source control. Grant publisher/subscriber permissions scoped to the exact resources rather than overly broad roles just to make the app start.

### Acknowledgement and delivery

Pub/Sub provides at-least-once delivery by default. Subscribers must ack messages within the ack deadline; if the deadline expires or a message is nacked, it may be redelivered. Ack deadlines can be extended by the client library during long processing.

The binder provides ack modes such as AUTO, AUTO_ACK, and MANUAL. Understand the exact semantics of your binder version before choosing:

- AUTO: the adapter acks on success and nacks on errors not handled completely by an error handler.
- AUTO_ACK: the adapter acks on success; on errors, it neither acks nor nacks, letting the ack deadline drive the next redelivery.
- MANUAL: the application explicitly acknowledges using the callback/header exposed by the binder.

With AUTO, if an error handler catches an error and completes normally, the adapter may treat the flow as successful and ack the message; to trigger default nack, the error must be rethrown through the error flow. AUTO_ACK is often used when letting the ack deadline pace retries after errors. With MANUAL, retrieve `BasicAcknowledgeablePubsubMessage` from the original header to ack/nack after business decisions; idempotency is still required because network errors or redeliveries can cause duplicate processing.

Pub/Sub supports dead-letter topics and retry policies at the subscription level. Delivery attempts, ack deadlines, and dead-letter topics are subscription settings; do not confuse client library RPC retries with message redelivery. RPC retries handle API call failures, whereas redelivery occurs when a message is not acked.

### Ordering and exactly-once

A Pub/Sub ordering key is not a partition. When message ordering is enabled on a subscription, messages with the same ordering key published in the same region are delivered in the order the service received them. Different keys have no global ordering. Hot keys can degrade throughput and build backlogs for that key's message chain.

Pub/Sub supports exactly-once delivery for pull subscriptions within the same region. Push and export subscriptions do not support this feature. However, current Spring Cloud GCP documentation notes that the library does not expose `AckReplyConsumerWithResponse`, the interface needed to use the Java client's exactly-once acknowledgement API. Therefore, do not assume enabling exactly-once on a subscription automatically gives the Spring Cloud Stream binder full exactly-once semantics for functions.

Additionally, the binder explicitly notes that Spring Cloud Stream partitioning is not yet supported. If the application relies on partition keys, partition counts, or binder-managed partitioning, redesign around ordering keys and subscription semantics or choose another middleware. Ordering keys are not equivalent to partitions and do not create a fixed number of partitions.

### Risks to check

- Creating anonymous subscriptions leads to unstable backlogs and identities across restarts.
- Auto-create resources requires IAM permissions; manage resources separately in production.
- Expired ack deadlines trigger message redelivery; verify processing times and flow control.
- Ordering keys increase latency and can create hot keys.
- Service-level exactly-once capability does not mean the binder exposes the corresponding acknowledgement API.
- The binder does not support the Spring Cloud Stream partitioning abstraction.
- Google Cloud quotas, regions, project IDs, and service account scopes must all be verified together.

## 5. Solace PubSub+ Binder

Solace PubSub+ is an event broker supporting topic routing and guaranteed messaging via queues. The binder maps the Spring Cloud Stream model onto Solace's topic/queue model.

### Topics, queues, and consumer groups

Basic mapping:

- Producer bindings always publish to a topic.
- Consumer bindings always receive messages from a queue.
- Consumer groups are mapped to durable queues.
- The group's queue is configured with a topic subscription for the destination topic.
- When no group is declared, the binder creates a temporary queue for an anonymous consumer.
- If the queue has non-exclusive access, the broker distributes messages round-robin among consumer bindings in the group.

Because consumers receive from queues, the Message VPN must have Assured Delivery enabled and the client profile must allow sending/receiving guaranteed messages. Creating only a topic without an appropriate queue/subscription means the consumer group will not receive messages as expected.

### Dependencies and configuration

Starter artifact:

~~~xml
<dependency>
    <groupId>com.solace.spring.cloud</groupId>
    <artifactId>spring-cloud-starter-stream-solace</artifactId>
</dependency>
~~~

Functional binding example:

~~~yaml
spring:
  cloud:
    function:
      definition: uppercase
    stream:
      bindings:
        uppercase-in-0:
          destination: orders
          group: order-processor
          binder: solace-main
        uppercase-out-0:
          destination: processed/orders
          binder: solace-main
      binders:
        solace-main:
          type: solace
          environment:
            solace:
              java:
                host: tcps://broker.example.net:55443
                msgVpn: production
                clientUsername: app-client
                clientPassword: SOLACE_CLIENT_PASSWORD
~~~

In production, use TLS and a proper secret management mechanism. Do not commit passwords or truststore passwords. Verify Message VPN, ACL profiles, queue permissions, spool quotas, and permissions to provision queues/topic subscriptions.

The binder supports dedicated properties under the prefixes:

~~~text
spring.cloud.stream.solace.bindings.<binding-name>.consumer.*
spring.cloud.stream.solace.bindings.<binding-name>.producer.*
~~~

You can configure endpoint types, durable queue provisioning, queue access types, redelivery, error queues, batch mode, transactions, publisher confirmation, header mapping, and dynamic producer destinations.

### Broker version and acknowledgement

With Solace PubSub+ Binder v5.x and later, consumer bindings require PubSub+ Broker 10.2.1 or newer because the binder uses native message NACK introduced in that broker version. Producer bindings in binder v5.x remain compatible with older brokers, but an application that both publishes and consumes must check broker requirements for the consumer.

The binder supports manual message acknowledgement via `AcknowledgmentCallback`. However, manual acknowledgement is not supported when the consumer enables `transacted=true`. Error queue republishing is also not supported with `transacted=true` consumers. This is a constraint to decide before selecting a transaction strategy.

Distinguish two types of error queues:

- Error Queue: the binder can republish messages that were successfully delivered by the broker but failed application processing after internal retries are exhausted.
- Dead Message Queue (DMQ): the broker routes failed messages according to broker mechanisms such as expired TTL or exceeded redelivery count.

Do not treat the Error Queue and DMQ as the same resource. Configuration, publish/consume permissions, and replay procedures may differ.

### Solace partitioning

The PubSub+ broker natively supports partitioned queues. However, the Spring Cloud Stream partitioning abstraction is not supported by the Solace binder. To publish to a partitioned queue, the application passes the partition key via header `SolaceBinderHeaders.PARTITION_KEY` (the header name on the message is `solace_scst_partitionKey`). The broker handles distribution when consumers read from the partitioned queue.

Therefore, you cannot take `partitionCount`/`partitionKeyExpression` settings from another binder and expect the Solace binder to interpret them identically. Configure a partitioned queue in the broker and pass the key using the Solace binder's API/header.

### Redelivery and transactions

When a message is NACKed to requeue, the broker can redeliver that message and subsequent messages already buffered by the client. Redeliveries can create duplicates; consumers still need idempotency. Cap redelivery counts and configure error queues/DMQs to avoid infinite poison-message loops.

Solace supports local transactions for certain consumer flows. Transaction size and broker limits must be checked. Manual ack, error queue republishing, and transactions cannot be combined arbitrarily; test the exact configuration combination before production rollout.

## 6. Configuring multiple binders in the same application

When multiple binder implementations are on the classpath, Spring Cloud Stream needs to know which binder owns each binding. Each binder provides a type name in its binder metadata. A binder configuration has its own name, type, environment, and `defaultCandidate`.

Common properties:

- `spring.cloud.stream.bindings.<binding-name>.binder`: selects the binder for a binding.
- `spring.cloud.stream.binders.<binder-name>.type`: the type name provided by the binder.
- `spring.cloud.stream.binders.<binder-name>.environment`: properties specific to the binder context.
- `spring.cloud.stream.binders.<binder-name>.default-candidate`: determines whether the binder can be selected as a default candidate.

Do not allow multiple binders to act as default choices when the application needs explicit routing. Assign binders to every critical binding so configuration does not depend on classpath order.

### Example: reading from Event Hubs, publishing to Solace and Pub/Sub

Suppose an application has a function receiving orders from Event Hubs and emitting results to Solace. An independent Supplier emits audit events to Pub/Sub.

~~~java
import java.time.Instant;
import java.util.function.Function;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MultiBinderFunctions {

@Bean
Function<OrderCreated, OrderAccepted> azureToSolace() {
    return order -> new OrderAccepted(order.orderId(), "RECEIVED");
}

@Bean
Supplier<OrderAudit> publishAudit() {
    return () -> new OrderAudit("deployment-check", Instant.now());
}

record OrderCreated(String eventId, String orderId) {}
record OrderAccepted(String eventId, String orderId, String status) {}
record OrderAudit(String eventId, Instant createdAt) {}
}
~~~

Illustrative configuration:

~~~yaml
spring:
  cloud:
    function:
      definition: azureToSolace;publishAudit
    gcp:
      project-id: GOOGLE_CLOUD_PROJECT
    stream:
      bindings:
        azureToSolace-in-0:
          binder: eventhubs-main
          destination: incoming-orders
          group: order-bridge
        azureToSolace-out-0:
          binder: solace-main
          destination: enterprise/orders/accepted
        publishAudit-out-0:
          binder: pubsub-main
          destination: order-audit
      binders:
        eventhubs-main:
          type: eventhubs
          environment:
            spring:
              cloud:
                azure:
                  eventhubs:
                    connection-string: AZURE_EVENTHUB_CONNECTION
                    processor:
                      checkpoint-store:
                        account-name: AZURE_STORAGE_ACCOUNT
                        container-name: eventhub-checkpoints
        pubsub-main:
          type: pubsub
        solace-main:
          type: solace
          environment:
            solace:
              java:
                host: tcps://broker.example.net:55443
                msgVpn: production
                clientUsername: app-client
                clientPassword: SOLACE_CLIENT_PASSWORD
~~~

This example uses placeholders to show structure. Replace connection values with secrets or workload identities per environment. The Azure checkpoint store must be granted Storage access permissions.

The Google Pub/Sub binder has an important configuration caveat: GCP connection properties such as project ID and credentials must be placed according to Spring Cloud GCP's single-binder configuration style. Solace integration documentation notes this limitation when the Pub/Sub binder is used alongside other binders; do not assume all GCP properties can be isolated inside a binder `environment` the way Azure or Solace ones can. If multiple Pub/Sub binder instances with separate GCP configurations are needed, verify the capability of the specific binder version before designing.

This example only illustrates that one application can use multiple brokers. It does not create a distributed transaction among Event Hubs, Solace, and Pub/Sub. If the function reads from Event Hubs and publishes to Solace, publishing may succeed before the Event Hubs checkpoint is saved, causing the function to be invoked again and publish a duplicate. Use stable event IDs, idempotent consumers, outbox/inbox, or an appropriate deduplication mechanism.

## 7. Evaluating substitutability and portability

The functional model makes business logic reusable, yet broker characteristics cannot be swapped transparently.

| Component | Reusable? | Requires adapter or custom design? |
|---|---|---|
| Supplier/Function/Consumer | Usually yes | Payload types may need adjustment if a binder has limits |
| Binding name and destination | Common structure | Destination names carry broker-specific semantics |
| Consumer group | Common concept | Queues, subscriptions, and Event Hubs consumer groups behave differently |
| Partition key | Not entirely | Event Hubs partition keys, Pub/Sub ordering keys, and Solace partition keys are distinct concepts |
| Checkpoint/ack | No | Azure checkpoints, Pub/Sub ack deadlines, and Solace broker acks differ |
| Retries and DLQ | No | Separate broker configuration and resources |
| Message headers | Not entirely | Header mappings, reserved headers, and native metadata differ |
| Schema | Not automatic | Schema registries/metadata and serialization must be aligned |
| Exactly-once | No | Each service and binder has its own guarantee scope |

A portable design keeps the business contract in the payload: `eventId`, `eventType`, `aggregateId`, `occurredAt`, `schemaVersion`, and `payload`. Use headers only for correlation IDs, trace IDs, tenant IDs, or regenerable transport metadata. When switching binders, write an adapter to translate vendor-specific metadata into your internal model.

Do not pass vendor-specific objects such as `Checkpointer`, Pub/Sub acknowledgement callbacks, or Solace `AcknowledgmentCallback` into shared business layers. Wrap them in an adapter at the messaging boundary so order processing does not depend directly on vendor APIs.

## 8. Selection criteria by scenario

### Choose Azure Event Hubs when

- The system runs primarily on Azure.
- The primary need is partitioned event ingestion and retention.
- Consumer groups and replay from offsets within retention are needed.
- You can operate an Azure Blob Storage checkpoint store.
- Batch consumers and per-partition checkpointing fit the workload.
- Either the Kafka endpoint covers all Kafka APIs needed by the app, or the dedicated binder fits better.

Do not choose it solely because Event Hubs offers a Kafka endpoint. Check tiers, the Kafka protocol feature matrix, compression, transactions, Kafka Streams preview status, and the APIs your application actually uses.

### Choose Google Cloud Pub/Sub when

- The system needs managed pub/sub and subscription-based fan-out.
- Independent consumers need separate backlogs and progress tracking.
- Ordering keys satisfy per-entity ordering requirements.
- The application accepts subscription-based delivery instead of partition-based processing.
- Workloads do not rely on the Spring Cloud Stream partitioning abstraction.
- IAM, projects, regions, and quotas are managed in Google Cloud.

If exactly-once delivery is required, check both the subscription type and whether the binder exposes the acknowledgement API. If fixed partitions or Kafka-style stream processing are required, the Pub/Sub binder may not be suitable.

### Choose Solace PubSub+ when

- The architecture needs an event mesh and topic routing.
- Consumer groups are modeled via durable queues.
- Queue policies, spooling, selectors, topic subscriptions, and assured delivery are needed.
- The system needs broker features such as redelivery, error queues, DMQs, publisher confirmation, or queue partitioning.
- Operations teams can manage Message VPNs, queues, ACLs, spool, and broker versions.

Check the minimum broker version for the consumer binder, Assured Delivery, transaction/ack compatibility, and the limitations of Spring Cloud Stream's partition abstraction.

## 9. Testing binders before production

Do not stop at function unit tests. Test the binder, the broker, and external resources around the broker.

### General test matrix

| Test | Question to answer |
|---|---|
| Startup | Does the application create bindings and connect to the broker properly? |
| Authentication | Does the workload identity/service principal/service account have the right permissions? |
| Resource provisioning | Are topics, event hubs, subscriptions, and queues created properly? |
| Consumer group | Do multiple instances balance load properly and does fan-out work? |
| Partition/order | Do keys preserve ordering and distribute as intended? |
| Acknowledgement | Do acks/checkpoints occur only after durable processing? |
| Redelivery | Does stopping the process mid-processing trigger expected redelivery? |
| Retry | Do transient errors retry with bounds and backoff? |
| DLQ/error queue | Are permanent errors quarantined and is there a replay procedure? |
| Schema/header | Do payloads and metadata preserve the contract? |
| Restart/rebalance | Do new instances acquire partitions/subscriptions/queues cleanly? |
| Shutdown | Do producer flushes, consumer stops, and checkpoints complete? |
| Observability | Are metrics present for lag, backlogs, checkpoints, redeliveries, and publish errors? |

### Specific tests for Event Hubs

- Revoke Storage checkpoint permissions to verify errors are detected.
- Restart consumers and observe partition leases.
- Send large batches, fail part of a batch, and inspect checkpoints.
- Scale consumer count up/down and verify partition distribution.
- If using the Kafka endpoint, test actual Kafka APIs, authentication, compression, and transactions.

### Specific tests for Pub/Sub

- Create two subscriptions to verify fan-out.
- Run multiple instances in the same group to verify load sharing.
- Let ack deadlines expire and verify redelivery.
- Test ordering keys within the same region and hot-key scenarios.
- Verify dead-letter topics and max delivery attempts.
- Test service-level exactly-once, while verifying whether the binder exposes the required acknowledgement API.
- Run tests with the Pub/Sub emulator for basic logic and against the real service for IAM, quotas, ordering, and delivery semantics.

### Specific tests for Solace

- Verify durable queues and topic subscriptions are provisioned accurately.
- Test Assured Delivery and queue access types.
- Send NACKs and observe broker redelivery.
- Verify error queues differ from DMQs across failure types.
- Test manual ack together with transactions to confirm documented constraints.
- Test partition key headers on partitioned queues.
- Verify publisher confirmations and queue spool/TTL.

## 10. Workflow for taking a partner binder to production

1. Choose the service based on data model and delivery requirements, not just binder name.
2. Lock down versions of Spring Boot, Spring Cloud Stream, BOM, and the binder.
3. Read release notes, migration guides, and compatibility matrices.
4. Assign ownership for upgrading the binder and addressing CVEs/bugs.
5. Declare dependencies using the vendor's starter/BOM.
6. Separate properties by binder and binding; keep secrets out of YAML.
7. Create topics, subscriptions, event hubs, queues, and checkpoint stores via infrastructure pipelines.
8. Use stable consumer group or subscription identities.
9. Finalize payload schemas, event IDs, header contracts, and retry/DLQ policies.
10. Run integration tests against real brokers, covering restarts, rebalances, redeliveries, and replays.
11. Set up metrics/alerts for backlogs, lag, checkpoints, redeliveries, publish failures, and queue quotas.
12. Run a canary rollout and verify no unexpected duplicates or losses occur.
13. Prepare rollback, replay, and migration paths before shifting traffic.

If an application publishes to a second broker, design failure handling for cases where only one side succeeds. Spring Cloud Stream does not provide a shared distributed transaction across Azure, Google Cloud, and Solace. Outbox/inbox and idempotency are typically the required protective boundaries.

## 11. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Binding uses the wrong binder | Missing binder assignment or ambiguous `defaultCandidate` | Specify `binder` on critical bindings |
| Event Hubs consumer repeats data after restart | Checkpoints not saved or Storage lease failure | Check checkpoint store and idempotency |
| Event Hubs consumer does not scale like Kafka | Partition leases/rebalancing have distinct semantics | Check ownership, Storage leases, and partition count |
| Kafka app fails on Event Hubs | Uses Kafka APIs unsupported by Event Hubs or insufficient tier | Check feature matrix and tier |
| Pub/Sub does not preserve order like Kafka partitions | Ordering key is not equivalent to a partition | Design around ordering keys and single region |
| Pub/Sub creates unexpected subscriptions | Auto-create resources enabled with unstable group | Pre-provision resources and disable auto-create |
| Pub/Sub binder does not satisfy partitioning | Binder does not support Spring Cloud Stream partitioning | Change model or select a suitable broker |
| Pub/Sub exactly-once unusable from binder | Binder does not expose `AckReplyConsumerWithResponse` | Verify API and consider a separate client adapter |
| Solace consumer receives no messages | Incorrect queue/subscription or Assured Delivery | Check Message VPN, queues, and ACLs |
| Solace binder v5+ cannot consume | Broker older than 10.2.1 | Upgrade broker or use a compatible binder version |
| Solace partition key has no effect | Using generic Spring Cloud Stream partitioning properties | Use partitioned queues and `SolaceBinderHeaders.PARTITION_KEY` |
| Solace error queue does not work | Missing publish ACL or confusing Error Queue with DMQ | Grant permissions and verify the right queue type |
| Cross-broker duplicates | Publish succeeds before source checkpoint/ack commits | Use event IDs, inbox/outbox, and deduplication |
| Headers lost when switching binders | Header mappings and native metadata differ | Standardize contracts and test header mapping |

## 12. Hands-on exercise: evaluating three binders for an order flow

A system has three requirements:

- Ingest order events from Event Hubs.
- Publish audit events to Google Cloud Pub/Sub so multiple subscriptions receive them independently.
- Publish processed events to Solace for applications in the event mesh to consume via durable queues.

Steps:

1. Write a Function reading `OrderCreated` from Event Hubs and emitting `OrderAccepted` to Solace.
2. Write an independent Supplier emitting `OrderAudit` to Pub/Sub.
3. Configure each binding to use the right binder.
4. Configure the Event Hubs checkpoint store and consumer group.
5. Create a Pub/Sub topic, two subscriptions, and test fan-out.
6. Create a Solace Message VPN, topic, durable queue, and subscription.
7. Normalize `eventId`, `orderId`, `eventType`, and `occurredAt` in the payload.
8. Simulate a failure after Solace publish succeeds but before Event Hubs checkpoints.
9. Verify duplicates are handled idempotently.
10. Simulate a Pub/Sub ack deadline expiring and verify redelivery.
11. Simulate a Solace NACK, redelivery, and Error Queue behavior.
12. Measure backlog/lag, checkpoint duration, redelivery count, and publish latency.
13. Compare operational cost, IAM/ACL requirements, replay capabilities, and binder upgrade complexity.
14. Write an ADR stating the final choice, trade-offs, and rollback plan.

Acceptance table:

| Item | Result to verify |
|---|---|
| Binder selection | Each binding explicitly points to the right binder |
| Version compatibility | BOM, Spring Boot, Spring Cloud, and binders are compatible |
| Event Hubs checkpoint | Checkpoint store/leases work across restarts |
| Pub/Sub subscription | Fan-out and group mapping work properly |
| Pub/Sub ordering | Ordering key enabled for the right region/subscription |
| Solace queue | Durable queue and Assured Delivery work properly |
| Error handling | Retries, redelivery, and DLQ/error queue match semantics |
| Schema contract | Payloads and event IDs are consistent across brokers |
| Idempotency | Cross-broker retries produce no duplicate side effects |
| Security | Workload identity, service accounts, ACLs, and secrets are accurate |
| Observability | Metrics exist for backlog/lag/checkpoint/redelivery |
| Recovery | Replay and rollback runbooks are in place |

## Conclusion

Azure Event Hubs, Google Cloud Pub/Sub, and Solace PubSub+ all have partner-maintained Spring Cloud Stream binders, yet serve different messaging models. Event Hubs is a partitioned event log with checkpoints and leases via Azure Storage. Pub/Sub is a topic/subscription service with acknowledgement deadlines, ordering keys, and fan-out. Solace combines topic routing with durable queues, Assured Delivery, redelivery, and event mesh.

Evaluate semantics before evaluating configuration syntax. The Event Hubs Binder has its own checkpointing and batching; the Pub/Sub binder does not support Spring Cloud Stream partitioning and has API limitations for exactly-once; the Solace binder maps groups to durable queues and uses the broker's own partitioning/ack mechanisms. Multiple binders can run together in one application, yet do not create distributed transactions across brokers. Keep payload contracts stable, apply idempotency, and test realistic failure paths before moving to production.

## References

- [Spring Cloud Stream 5.1.0 – Binder implementations](https://spring.io/projects/spring-cloud-stream/)
- [Spring Cloud Stream – Multiple Binders on the Classpath](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/multiple-binders.html)
- [Spring Cloud Azure – Binder for Azure Event Hubs](https://microsoft.github.io/spring-cloud-azure/current/reference/html/index.html#spring-cloud-stream-binder-for-azure-event-hubs)
- [Microsoft Learn – Spring Cloud Stream support](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/spring-cloud-stream-support)
- [Microsoft Learn – Azure Event Hubs for Apache Kafka](https://learn.microsoft.com/en-us/azure/event-hubs/azure-event-hubs-apache-kafka-overview)
- [Spring Framework on Google Cloud – Spring Cloud Stream Binder for Pub/Sub](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/index.html#spring-cloud-stream)
- [Google Cloud – Using Pub/Sub in Spring applications](https://docs.cloud.google.com/pubsub/docs/spring)
- [Google Cloud – Subscription overview](https://docs.cloud.google.com/pubsub/docs/subscription-overview)
- [Google Cloud – Exactly-once delivery](https://docs.cloud.google.com/pubsub/docs/exactly-once-delivery)
- [Solace – Spring Cloud Stream Binder for PubSub+](https://github.com/SolaceProducts/solace-spring-cloud/tree/master/solace-spring-cloud-starters/solace-spring-cloud-stream-starter)
- [Solace – Spring Cloud Stream tutorial](https://tutorials.solace.dev/spring/spring-cloud-stream/)
