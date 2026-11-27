# Competing Consumers Pattern in Spring Integration Adapters

> **Chapter:** Design patterns  
> **Topic:** Competing consumers pattern  
> **Scope:** SPRING_INTEGRATION_ADAPTERS module — connecting external systems via inbound/outbound adapters, gateways, pollers, and MessageChannels. This lesson places the multi-worker competing consumption model into File, SFTP, HTTP, JMS, AMQP, Kafka, and database flows; specifically emphasizing message contracts, redelivery, errors, ordering, load scaling, and connection lifecycles.

## 1. Objectives and Opening Question

Suppose an application receives 50,000 order messages per hour. A single consumer finishes only 5,000 messages per hour. The queue keeps growing even though the producer works normally. We want to increase processing workers **without turning one job into three duplicate business executions**.

**Competing Consumers** is a pattern where multiple consumers **compete to receive work messages from a shared distribution source**. Typically, a message is delivered to **one consumer at a time**, while other messages are distributed to other workers. The goal is increasing processing capacity, availability, and load leveling—not broadcasting a copy of every message to everyone.

After this lesson, learners can:

1. Interpret Competing Consumers in Enterprise Integration Patterns (EIP) and distinguish it from Publish–Subscribe, Event-driven Consumer, and Polling Consumer.
2. Identify the **unit of work**, **queue boundaries**, **consumer groups/partitions**, and **point of confirmed processing success**.
3. Design multi-worker queues in Spring Integration via a **PollableChannel** or message-driven inbound adapters for JMS/AMQP/Kafka.
4. Explain why **a DirectChannel with multiple subscribers**, **a QueueChannel with multiple polling consumers**, and **a broker with competing consumers** do not share the same durability and ack semantics.
5. Evaluate **acks, retries, redelivery, idempotency, dead-lettering, ordering, concurrency, prefetch, and backpressure**.
6. Calculate and measure throughput, backlog, wait times, autoscaling needs, and sink limits.
7. Handle single-worker failures, rolling deploys, broker disconnects, partition rebalances, and repeatedly failing poison messages.
8. Write Java flows, simulate work distribution, test duplicates/failures, and hand over a runbook.

**Guiding question:** *How do you distribute work across multiple consumers—where any worker can fail or shut down abruptly—while keeping business outcomes accurate and recoverable?*

## 2. Core Concept: Competing to Receive Work

A **work queue** receives jobs from one or more producers. Multiple consumers register to consume from the same queue/destination or corresponding consumer group. When a message is available, the distribution mechanism picks an available consumer; that consumer runs the business logic and acknowledges per the transport contract.

~~~mermaid
flowchart LR
    P1["Producer A"] --> Q["Work Queue / Shared Subscription"]
    P2["Producer B"] --> Q
    Q --> C1["Consumer 1"]
    Q --> C2["Consumer 2"]
    Q --> C3["Consumer 3"]
    C1 --> DB["Business Store"]
    C2 --> DB
    C3 --> DB
~~~

The diagram illustrates **work distribution**, not every message in the queue being sent simultaneously to all three consumers. For example, if the queue has W1, W2, W3, W4, one valid distribution is:

~~~text
W1 → consumer-1
W2 → consumer-2
W3 → consumer-3
W4 → consumer-2
~~~

**Even 1:1:1 distribution is never guaranteed.** A faster worker, one with higher prefetch, or a newly reconnected one may receive more messages. Dispatch algorithms depend on the broker, channel, listener container, and actual load.

### 2.1. A message can be redelivered

“Each message goes to one consumer” applies to **an active delivery attempt**, not “once forever.” If consumer-1 receives W1 and crashes before the broker records completion, W1 may be redelivered to consumer-2. Therefore:

- Never infer from *consumerId* that a job only ran once.
- Consumers must handle **duplicates** and the committed-but-unacked state.
- Start order, completion order, and redelivery order can differ.
- **Success of the message-receive API** does not prove the business transaction succeeded.

### 2.2. Three main benefits

| Benefit | Mechanism | What to verify |
| --- | --- | --- |
| **Scale-out** | Multiple workers process distinct work items | Throughput scales until hitting broker/DB/API limits |
| **Availability** | One worker dies; remaining workers still take work | Redelivery/failover actually happens per transport |
| **Load leveling** | Queue absorbs short traffic spikes | Queue capacity, backlog age, and retention limits |

**Not a promise:** multiple consumers do not automatically yield exactly-once, global ordering, even CPU distribution, or infinite downstream capacity.

## 3. Distinguishing from Related Patterns

| Pattern | Who receives a message? | Purpose | Example |
| --- | --- | --- | --- |
| **Competing Consumers** | One consumer in the competing group per delivery | Share work and increase throughput | Multiple workers reading from a RabbitMQ queue |
| **Publish–Subscribe** | Each subscriber/subscription can receive a copy | Multiple domains interested in the same event | Billing and Analytics both receive OrderCreated |
| **Event-driven Consumer** | Handler invoked when message is dispatched | Event-based reception style | JMS/Kafka listener invoking handler |
| **Polling Consumer** | Consumer proactively calls receive on schedule | Pull-based reception from source/channel | PollingConsumer reading QueueChannel |
| **Message Router** | Picks channel/target based on content or policy | Branching messages | Route by order type |
| **Aggregator** | Combines multiple related messages into one result | Consolidation | Merging responses from three APIs |
| **Request–Reply Gateway** | Sends request and awaits correlated reply | Request-response interaction | HTTP/JMS gateway |

Competing Consumers describes **work distribution**, whereas Event-driven/Polling describe **how reception is triggered**. Thus a RabbitMQ listener can simultaneously be an **event-driven consumer** and a member of **competing consumers**; a Spring **PollingConsumer** pulling work from a **QueueChannel** can also compete with another PollingConsumer.

### 3.1. Distinguishing fan-out from competing groups

~~~mermaid
flowchart TB
    EVENT["OrderCreated"] --> BROKER["Broker Topic / Exchange"]
    BROKER --> QUEUE_A["Billing Queue"]
    BROKER --> QUEUE_B["Analytics Queue"]
    QUEUE_A --> BA1["Billing worker 1"]
    QUEUE_A --> BA2["Billing worker 2"]
    QUEUE_B --> AN1["Analytics worker 1"]
    QUEUE_B --> AN2["Analytics worker 2"]
~~~

Billing and Analytics receive **logical copies of the same event** through two separate subscriptions/queues. Inside Billing, two workers **compete with each other**; inside Analytics, two workers also compete. Using one shared queue for both Billing and Analytics would give each message to only one side, dropping the other domain's requirement.

### 3.2. Kafka consumer groups do not give every worker the whole topic

In Kafka, records are stored in **partitions**. Consumers sharing a **group.id** divide partitions; under normal assignment, a partition is assigned to one consumer member in the same group at a time. If two independent domains must both see every event, they use **two separate consumer groups** or an equivalent mechanism—not merely two instances in the same group.

### 3.3. When it is appropriate

Consider competing consumers when:

- Work can be split into **independent units** or partitioned by key.
- A queue/broker/claim mechanism mediates between workers.
- Downstream systems can tolerate the desired concurrency level.
- Learners or ops teams have defined ack, retry, idempotency, and error policies.
- A single worker cannot keep up with arrival rates, or worker redundancy is needed.

Do not blindly add workers when messages require **strict global sequential processing**, contend on a single exclusive lock, hit very low downstream API rate limits, or lack duplicate-prevention for business side effects.

## 4. Spring Integration Architecture for Competing Consumers

Spring Integration provides **MessageChannels**, **MessageHandlers**, **service activators**, **inbound/outbound adapters**, **gateways**, **pollers**, and adapters for external systems. Competing consumers can be structured at **two distinct levels**:

1. **In-JVM:** multiple consumers pulling from one **PollableChannel**, or dispatching among subscribers of a DirectChannel.
2. **External infrastructure outside the JVM:** multiple listener containers/instances consuming from a **JMS/AMQP queue** or a **Kafka consumer group**.

~~~mermaid
flowchart LR
    P["Application Producer"] --> Q["QueueChannel in JVM"]
    Q --> PC1["PollingConsumer A"]
    Q --> PC2["PollingConsumer B"]
    PC1 --> BIZ["Business Service"]
    PC2 --> BIZ
    EXT["Broker work queue / topic partitions"] --> IA1["Adapter instance A"]
    EXT --> IA2["Adapter instance B"]
    IA1 --> CH1["Local MessageChannel"]
    IA2 --> CH2["Local MessageChannel"]
    CH1 --> BIZ
    CH2 --> BIZ
~~~

### 4.1. Consequences of each channel

| Channel | Message distribution | Durability/ack to understand |
| --- | --- | --- |
| **QueueChannel** | Multiple polling consumers can pull different messages | Typically in-memory; `receive` removes the message from the queue, unlike durable broker acks |
| **DirectChannel** | Selects one subscriber handler per message | Synchronous handler call; not a durable work queue |
| **ExecutorChannel** | Dispatches messages to an executor and handlers | Executor queue is not durable by default; capacity must be bounded |
| **PublishSubscribeChannel** | Broadcasts one message to multiple subscribers | **Not competing consumers** if every subscriber must process |
| **Broker adapter → DirectChannel** | Broker distributes at the listener level; channel dispatches in-JVM | Broker ack and business logic must coordinate; do not infer completion from `send()` |

**Do not confuse:** attaching three handlers to a **DirectChannel** means only one handler is chosen per message by the dispatcher. Yet that **never replaces a broker queue** when persistence, post-crash redelivery, and multi-server load sharing are required.

### 4.2. Message-driven vs. polling

- With **JMS/AMQP inbound adapters**, the listener container receives messages from the broker per container mechanics and passes them to a channel—typically event-driven at the Spring Integration layer.
- With **QueueChannel**, a **PollingConsumer** calls `receive()` via a poller to pull messages.
- With **File/SFTP/JDBC inbound sources**, a **SourcePollingChannelAdapter** fetches data on schedule and creates messages. If multiple instances read the same source, shared locks/claims/metadata are needed; adding replicas alone does not create a safe competing queue.
- With **Kafka**, the underlying client runs a poll loop, while at the Spring Integration layer the message-driven inbound adapter usually relies on a listener container; work distribution depends on **consumer groups and partition assignments**, not a single QueueChannel.

## 5. Defining the Work Item and Message Contract

Before configuring concurrency, define **what a completable unit of work is**: an order, a file, a DB row, a command, or a batch? Otherwise, metrics and redelivery become ambiguous.

### 5.1. Illustrative envelope

~~~json
{
  "eventId": "WORK-LAB-0041",
  "eventType": "GenerateInvoice",
  "schemaVersion": 1,
  "tenantId": "TENANT-LAB-01",
  "businessKey": "ORDER-LAB-0088",
  "businessVersion": 2,
  "requestedAt": "2026-11-23T14:00:00+07:00",
  "data": {
    "orderId": "ORDER-LAB-0088",
    "invoiceType": "STANDARD"
  }
}
~~~

This is a **simulated** business schema, not the default payload of JMS, AMQP, or Kafka. Spring **Message<T>** also carries headers for routing and tracing; never assume every external header is trustworthy.

### 5.2. Message contract checklist

- [ ] **eventId or workId** remains stable across retries/redeliveries, not just a newly generated technical message ID.
- [ ] Includes a **businessKey** suitable for idempotency and partitioning/ordering.
- [ ] Clarifies whether one message is one work item or a batch of items.
- [ ] Defines schema/version, format, encoding, size limits, and required fields.
- [ ] Verifies tenant, source, and command authorization before side effects.
- [ ] Distinguishes **RECEIVED, CLAIMED, PROCESSING, COMMITTED, ACKNOWLEDGED**.
- [ ] Includes a business validity window/deadline if work can arrive late.
- [ ] Never stores passwords, raw tokens, private keys, or unnecessary PII in payloads/headers/logs.
- [ ] Has a policy for duplicate events or stale versions arriving after newer versions.
- [ ] Provides a quarantine/DLQ path and safe replay for unprocessable messages.

### 5.3. Correlation does not replace idempotency

**Correlation IDs** link workflow or request/reply steps; **business idempotency keys** protect an effect from being applied twice. Both purposes may share a value by design, yet they are not inherently equivalent. A redelivered broker message may have a different technical message ID while keeping the same business workId.

## 6. Java DSL: Two PollingConsumers Competing on QueueChannel

We start in **one JVM** to observe work pulling before adding a broker. Two integration flows consume from the same bounded **QueueChannel**. Both polling endpoints actively call `receive()`; each message goes to one endpoint, not broadcast.

### 6.1. Java 17 and Spring Integration 6.x example

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
public class LocalCompetingConsumersConfig {

    @Bean
    public QueueChannel invoiceWorkQueue() {
        // Bounded to avoid producers pushing unbounded work into heap.
        return new QueueChannel(100);
    }

    @Bean
    public IntegrationFlow invoiceWorkerA(QueueChannel invoiceWorkQueue) {
        return IntegrationFlow
                .from(invoiceWorkQueue, endpoint -> endpoint.poller(
                        Pollers.fixedDelay(Duration.ofMillis(300))
                               .maxMessagesPerPoll(2)
                ))
                .handle((MessageHandler) message -> {
                    String workId = String.valueOf(message.getPayload());
                    System.out.println("worker-A handles " + workId);
                })
                .get();
    }

    @Bean
    public IntegrationFlow invoiceWorkerB(QueueChannel invoiceWorkQueue) {
        return IntegrationFlow
                .from(invoiceWorkQueue, endpoint -> endpoint.poller(
                        Pollers.fixedDelay(Duration.ofMillis(300))
                               .maxMessagesPerPoll(2)
                ))
                .handle((MessageHandler) message -> {
                    String workId = String.valueOf(message.getPayload());
                    System.out.println("worker-B handles " + workId);
                })
                .get();
    }
}
~~~

This is a **lab configuration** illustrating multiple consuming endpoints, not a production setup with durable transactions/retries. When running in Spring Boot, ensure Spring Integration core/DSL and component scanning match your project version.

### 6.2. Producer sending work items

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class InvoiceWorkPublisher {
    private final MessageChannel channel;

    public InvoiceWorkPublisher(
            @Qualifier("invoiceWorkQueue") MessageChannel channel) {
        this.channel = channel;
    }

    public void enqueue(String workId) {
        boolean accepted = channel.send(
                MessageBuilder.withPayload(workId)
                              .setHeader("workId", workId)
                              .build(),
                1000L
        );
        if (!accepted) {
            throw new IllegalStateException("Work queue is full");
        }
    }
}
~~~

Send distinct IDs, such as **W01–W10**, and observe the output. **Do not expect worker A to process exactly 5 messages and worker B to process 5**: speed, scheduling, and load determine distribution. What matters is proving **no broadcast occurs** and each receive claims one available message.

### 6.3. Critical limitation of QueueChannel

**An in-memory QueueChannel is no substitute for a durable broker queue.** Once a polling consumer dequeues a message, it is gone from the QueueChannel's initial queue. If the handler throws an exception after dequeuing, do not assume **broker redelivery** will run automatically. If the JVM dies, queued in-memory messages can be lost.

Moving toward production, choose one of these paths depending on risk:

1. Use **JMS/AMQP/Kafka** with verified persistence, ack, and recovery mechanics.
2. Use a **persistent message store** or supported transaction mechanism in Spring Integration; test the exact scope.
3. If still using in-memory queues for regenerable work, persist the source of truth/work state durably with reconciliation/replay.

### 6.4. maxMessagesPerPoll and consumer count

Two workers with **maxMessagesPerPoll(2)** mean each poll cycle of each endpoint can pull up to two messages—**not** that the system always processes exactly four messages in parallel. Threading and concurrency depend on TaskScheduler/executors, handler duration, and poller settings. If all handlers are slow while the scheduler has few threads, adding endpoints may fail to yield expected speedups.

## 7. Competing Consumers with JMS

In JMS, a **Queue** typically represents point-to-point work distribution. Multiple **MessageListeners** consuming the same queue is a classic competing-consumers implementation. The broker distributes messages per JMS semantics and provider/container configuration.

~~~mermaid
flowchart LR
    PRODUCER["Order Service"] --> Q["JMS Queue: invoice.jobs"]
    Q --> A["JMS Listener instance A"]
    Q --> B["JMS Listener instance B"]
    Q --> C["JMS Listener instance C"]
    A --> H["Idempotent invoice handler"]
    B --> H
    C --> H
~~~

### 7.1. Spring Integration message-driven inbound adapter

Minimal Java DSL example with the Spring Integration JMS dependency and an application-supplied ConnectionFactory:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jms.dsl.Jms;
import org.springframework.messaging.MessageHandler;

@Configuration
@EnableIntegration
public class JmsInvoiceConsumerFlow {

    @Bean
    public IntegrationFlow invoiceJobs(ConnectionFactory connectionFactory) {
        return IntegrationFlow
                .from(Jms.messageDrivenChannelAdapter(connectionFactory)
                         .destination("invoice.jobs"))
                .handle((MessageHandler) message -> {
                    String body = String.valueOf(message.getPayload());
                    System.out.println("Received invoice work: " + body);
                })
                .get();
    }
}
~~~

Deploying multiple instances pointing to the same **invoice.jobs queue** lets listeners compete for work. The configuration above **does not yet** define durability, transaction managers, delivery modes, redelivery policies, or a DLQ. Configure those explicitly based on your JMS provider, Spring listener container, and business requirements.

### 7.2. Choosing concurrency and acknowledgment

| Concern | Practical question |
| --- | --- |
| **Listener concurrency** | How many consumers per JVM, and are there connection/session limits? |
| **Transaction/ack mode** | When does the broker consider a message finished? |
| **DB updates** | Do the handler and JMS session truly share a transaction? |
| **Redelivery** | When a listener fails or crashes, is the message redelivered? |
| **Poison messages** | After retries exhaust, does it move to DLQ or block the queue? |
| **Ordering** | With multiple consumers, are there ordering constraints or message groups? |

**Async handoff warning:** if a JMS listener receives W1, pushes W1 to an **ExecutorChannel**, and returns, the broker may mark completion **before** the async worker writes to the DB. A JVM crash in that gap can lose work. Define ack/transaction and durable handoff per explicit design—not just because `send()` succeeded.

### 7.3. JMS Topic vs. JMS Queue

Each subscription on a Topic can receive a copy per contract; whether multiple consumers share work or each gets a copy depends on **durable/shared subscriptions and provider setup**. Never claim “JMS has three listeners so it's competing consumers” without verifying **whether the destination is a Queue or Topic and how it is subscribed**.

## 8. Competing Consumers with AMQP/RabbitMQ

In RabbitMQ, producers typically publish to an **exchange**, messages route to a **queue**, and **multiple consumers on the same queue** compete for messages. For both Billing and Analytics to receive every event, you need **two queues bound** via appropriate exchange/routing keys, where each queue can have its own pool of competing consumers.

~~~mermaid
flowchart TB
    P["Order Service"] --> EX["orders.events exchange"]
    EX --> BQ["billing.queue"]
    EX --> AQ["analytics.queue"]
    BQ --> B1["billing-worker-1"]
    BQ --> B2["billing-worker-2"]
    AQ --> A1["analytics-worker-1"]
    AQ --> A2["analytics-worker-2"]
~~~

### 8.1. Listener container settings to understand

| Setting | Meaning | Risk if misconfigured |
| --- | --- | --- |
| **Concurrent consumers** | Number of listeners processing in parallel | Overwhelms target DB/HTTP capacity |
| **Max concurrent consumers** | Local scaling ceiling if supported by container | Unexpected spikes in threads/connections |
| **Prefetch** | Unacked messages delivered ahead of time | Slow worker hoards work, uneven distribution |
| **Ack mode** | When consumers ack/nack/reject | Early ack causes data loss; infinite requeue causes loops |
| **Requeue policy** | Whether failures redeliver or route to DLQ | Poison messages stall queues |
| **Queue durability** | Whether queues survive restarts per setup | Lost topology or messages if misconfigured |
| **Publisher confirms** | Broker receipt confirmation for producers | Does not mean consumers completed business logic |

### 8.2. Designing the Spring Integration AMQP flow

At the structural level:

~~~text
RabbitMQ exchange
  → invoice.jobs.queue (durable as needed)
  → Spring AMQP listener container (bounded concurrency)
  → Spring Integration AMQP message-driven inbound adapter
  → DirectChannel
  → Service Activator: validate + idempotent DB transaction
  → Ack per listener/adapter contract
~~~

In real integration, Spring Integration AMQP wires an **AMQP message listener container** to a **MessageChannel**. Factory method names/overloads vary across Spring Integration/Spring AMQP versions; pick from compatible APIs rather than treating the pseudocode above as copy-paste commands.

### 8.3. Prefetch is not processed message count

With prefetch=50 and a slow consumer, the broker may deliver many unacked messages to it. Other fast workers **cannot necessarily** steal unacked messages from the slow worker until an error/disconnect/timeout occurs per broker rules. Excessively high prefetch raises tail latency and skews distribution; overly low prefetch limits throughput across high round-trip networks.

### 8.4. Redelivery and ordering

Consumer A receives W1 and W2, commits only W2, then disconnects. The broker may redeliver W1 while consumer B has already processed W3. **Business commit order differing from publish order** must be tested. Never use a multi-consumer queue for logic requiring strict global ordering without additional constraints.

## 9. Competing Consumers in a Kafka Consumer Group

Kafka does not use queues in the RabbitMQ sense. Kafka stores records in **topic partitions**, consumer groups perform **partition assignment**, and offsets track the group's reading progress.

### 9.1. Partitions are the unit of work distribution

Suppose topic **invoice.jobs** has three partitions and group **billing-workers** has two consumers:

~~~mermaid
flowchart LR
    TOPIC["Kafka topic: invoice.jobs"] --> P0["Partition 0"]
    TOPIC --> P1["Partition 1"]
    TOPIC --> P2["Partition 2"]
    P0 --> C1["billing worker A"]
    P1 --> C1
    P2 --> C2["billing worker B"]
~~~

Other assignments may also be valid depending on the assignor and group state. Scaling to **four consumers with only three partitions** means at most three consumers in the group hold partitions at any time; the extra consumer cannot boost throughput by grabbing an already-assigned partition.

### 9.2. Ordering conditions

Kafka preserves **record order within the same partition** under producer/broker/reader conditions. To keep changes for the same order sequential, **orderId** is often chosen as the record key so events for that order land in the same partition; however, dispatching downstream across a multi-threaded ExecutorChannel can still scramble **business commit order**.

### 9.3. Spring Integration Kafka inbound adapter

In Spring Integration, the **message-driven** Kafka adapter usually consumes from a **Kafka listener container**, sending records/batches to a MessageChannel. The Kafka client still runs a poll loop underneath, but do not mistake that for a **PollingConsumer** endpoint reading a QueueChannel.

~~~text
Kafka invoice.jobs topic partitions
  → Kafka listener container (group.id = billing-workers)
  → Spring Integration Kafka message-driven inbound adapter
  → MessageChannel
  → idempotent business handler
  → offset commit / ack per container policy
~~~

**Configure per version** of Spring Kafka and Spring Integration Kafka: listener containers offer diverse record/batch, ack, error-handler, and transaction modes. Never assume default auto-commit is suitable.

### 9.4. Rebalancing and consumer failover

When consumer A dies or B joins the group, Kafka may **rebalance**: partition ownership changes. If A wrote record R to the DB before committing the offset, B may reprocess R. This is why **idempotent consumers** keyed by business eventId or business version are essential.

### 9.5. Scaling limits

- **Partition count** caps active partition-holding consumers in one group.
- Increasing partitions alters key hashing and can affect ordering requirements; plan carefully.
- Adding consumers yields zero throughput gain if the DB/sink is saturated.
- A *hot partition* drives up lag even while other partitions drain quickly.
- Never share the same group ID between two business domains that both need every event.

## 10. Files, SFTP, HTTP, and Databases: How to Compete Without a Broker

Not every data source has a broker queue coordinating delivery. Often you must **build a work-claim mechanism** before letting multiple instances process concurrently.

### 10.1. File/SFTP: do not let two pollers read the same file

Two Spring Integration instances scanning an SFTP folder:

~~~text
Replica A: list remote → orders-001.csv
Replica B: list remote → orders-001.csv
A: local memory filter = unseen
B: local memory filter = unseen
A and B: both download and process the file
~~~

This is **not** safe competing consumption. Options include:

- **Single active poller** via leader election/failover.
- **Shared persistent metadata store** for adapter-compatible filters/claims.
- Remote rename/claim or lock registry **when safely supported by the source**, with crash recovery.
- Partition directories per partner/source so each worker owns a deterministic subset.
- Stage each file as a **durable work message in a broker** for multiple consumers to process.

**Never mark a file processed before business commit** unless proper recovery exists. Persisting “seen” metadata only deduplicates one step; it does not create end-to-end exactly-once.

### 10.2. Database: claiming READY rows transactionally

If work sits in a task table, use an explicit state and ownership workflow:

~~~text
READY
  → CLAIMED(workerId, leaseUntil, attempt)
  → PROCESSING
  → COMPLETED
or
  → RETRYABLE / DEAD_LETTER
~~~

Two consumers must never run **SELECT READY** and process independently without conditional locking/claiming. Depending on the DB, use row locking, conditional updates, claim transactions, or leases. Syntax like **FOR UPDATE SKIP LOCKED** applies only on supporting DBs inside proper transactions; plain SELECT never prevents duplicate processing.

### 10.3. HTTP: load balancing is not a competing queue

Multiple HTTP server instances behind a load balancer **distribute independent requests**, yet HTTP provides no **durable work queue, redelivery, or per-message ack**. If a client retries after a timeout, it may hit a different instance; idempotency state must be shared if side effects exist.

When fast HTTP ingestion plus background processing is needed:

~~~mermaid
flowchart LR
    CLIENT["HTTP Client"] --> API["HTTP Inbound Gateway"]
    API --> STORE["Validate + persist job/outbox"]
    STORE --> ACCEPT["202 Accepted + jobId"]
    STORE --> BROKER["Durable work queue"]
    BROKER --> W1["Worker A"]
    BROKER --> W2["Worker B"]
    W1 --> DB["Business result"]
    W2 --> DB
~~~

When calling external APIs inside a handler, an **HTTP outbound gateway** has its own request/reply semantics; never treat a reply timeout as proof the API caused no side effect.

### 10.4. JDBC Outbox: the boundary between DB and broker

A transactional outbox lets one DB transaction write both business changes and outbox records. A relay reads the outbox via polling/CDC and publishes to a broker; on the broker side, competing consumers process the events. The relay may double-publish if ACKs are lost, so downstream still needs idempotency.

### 10.5. Choosing the work-distribution layer

| Initial source | Logical work-sharing layer | Hard parts |
| --- | --- | --- |
| JMS Queue | Broker queue/listeners | Ack/transaction/redelivery |
| RabbitMQ Queue | Broker queue/consumers | Prefetch, nack/requeue, DLQ |
| Kafka Topic | Partitions/consumer group | Offsets, rebalances, ordering |
| HTTP Request | Load balancer or durable job enqueue | Client retry idempotency, job state |
| SFTP/File | Shared claim or broker staging | File completion, metadata, duplicates |
| JDBC READY tasks | Transactional claim/lease | Concurrency, lease expiry, rollbacks |
| In-JVM QueueChannel | Local PollingConsumers | In-memory durability, handler failures |

## 11. Delivery Semantics: A Message Can Be Processed Multiple Times

Broker-backed systems commonly provide **at-least-once delivery**: if a consumer fails to confirm completion per contract, the message may be redelivered. This supports recovery but demands idempotent business logic.

### 11.1. Classic failure window

~~~mermaid
sequenceDiagram
    participant Q as Broker Queue
    participant A as Consumer A
    participant DB as Database
    participant B as Consumer B
    Q->>A: Deliver W1
    A->>DB: Commit invoice(W1)
    DB-->>A: COMMITTED
    Note over A: JVM crash before broker ack
    Q->>B: Redeliver W1
    B->>DB: Repeat invoice(W1)?
    DB-->>B: Must detect duplicate
    B-->>Q: Ack after verification
~~~

If the handler creates a new invoice every time without a unique business key, **duplicate invoices are created**. If the handler writes a dedupe record post-commit in a separate store and crashes first, dedupe fails to save it.

### 11.2. Three common target levels

| Target | Practical meaning | Risks/conditions |
| --- | --- | --- |
| **At-most-once** | No redelivery once considered received | Work can be lost if failures happen after ack |
| **At-least-once** | Work may be re-received until success/exhaustion | Needs idempotency and poison-message handling |
| **Effectively-once** | Final business side effects match single execution | Unique business key + transactions + reconciliation |

Some platforms offer **exactly-once processing** within narrow bounds, such as a supported stream/transaction pipeline, yet that **never automatically covers** files, REST APIs, emails, external databases, and out-of-transaction side effects. Avoid claiming a durable queue equals business exactly-once.

### 11.3. Ack is not business commit

Milestones to separate:

~~~text
PUBLISHED    → broker receives message
DELIVERED    → listener receives message
HANDLING     → handler starts
COMMITTED    → business transaction succeeds
ACKNOWLEDGED → broker records progress per contract
~~~

The relative order of **COMMITTED** and **ACKNOWLEDGED** dictates data-loss vs. duplicate risk. For outbound HTTP calls to other services, there is no broker ack for those side effects; dedicated status/idempotency mechanisms are required.

### 11.4. Consumer crashes mid-processing

| Crash timing | What can happen | Risk-mitigating design |
| --- | --- | --- |
| Before receiving message | Broker/queue keeps work | Availability of other consumers |
| After delivery, before business commit | Message may redeliver | Transaction rollback/claim timeout |
| After business commit, before ack | Message may redeliver and re-run | Business-store idempotency |
| After ack, before async side effect | Work may be lost if async isn't durable | Ack after durable handoff or proper completion |
| During HTTP reply | Target may have committed despite timeout | Idempotency keys, status queries/reconciliation |

**Acceptance question:** After killing a consumer at the worst possible moment, can the system state accurately **which work is unfinished** and safely reprocess it?

## 12. Idempotent Consumer: Business Keys Are the Foundation

In competing consumers, idempotency cannot live solely in the producer or queue. Two workers can receive the same work via redelivery, and application retries can also invoke side effects repeatedly.

### 12.1. Choosing an idempotency key

For GenerateInvoice, you might use:

~~~text
consumerName  = invoice-generation
businessKey   = TENANT-LAB-01 / ORDER-LAB-0088 / INVOICE-STANDARD
version       = 2 (if version is part of business semantics)
~~~

Never rely solely on **message timestamps** or **MessageHeaders.ID** as keys since messages may be recreated on retry. For **two distinct logical consumers** (Billing and Analytics), idempotency keys must separate consumers/domains so one finishing does not make the other skip valid events.

### 12.2. Idempotency table in the database

~~~sql
CREATE TABLE processed_work (
    consumer_name VARCHAR(100) NOT NULL,
    work_key VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    result_reference VARCHAR(200),
    PRIMARY KEY (consumer_name, work_key)
);
~~~

In labs, a DB unique constraint can arbitrate two racing workers. In real applications, insert `processed_work` **within the same DB transaction** as the business mutation when sharing one DB.

### 12.3. Transactional processing pseudocode

~~~text
consume(work):
  validateSourceSchemaAndAuthorization(work)
  key = deriveStableBusinessKey(work)

  beginDbTransaction()
    if processedWork.existsForUpdate(consumerName, key):
        return ALREADY_COMPLETED

    current = loadInvoiceState(work.businessKey)
    if work.version < current.version:
        recordIgnoredStaleWork(consumerName, key)
        commit
        return STALE

    writeInvoiceIdempotently(work)
    processedWork.insert(consumerName, key, invoiceId)
  commitDbTransaction()

  acknowledgeBrokerAccordingToContract()
~~~

**Important:** Pseudocode does not fully resolve races between check and insert. Real implementations must rely on **unique constraints, proper locking/isolation, and duplicate-key conflict handling**. If an out-of-transaction HTTP side effect exists, separate target-side idempotency/reconciliation is still mandatory.

### 12.4. Key reuse with a different payload

If the same workKey arrives with different data, never silently ignore it as a valid duplicate. Store a **hash of significant business fields** to detect contract-violating payload changes, routing them to quarantine or handling version updates per policy. Compute hashes over canonicalized structures without letting hashes leak sensitive data.

### 12.5. Inbox/Outbox

- **Inbox:** records messages/work processed by a consumer to prevent duplicates.
- **Outbox:** persists outbound events in the same transaction as business mutations, later published by a relay.
- **Relay:** may double-publish if broker acks are lost; downstream needs inbox/idempotency.
- **Reconciliation:** detects cases where business state committed while events or readbacks never reached targets.

Even systems using both inbox and outbox must account for external transactions and brokers. Never assume these two tables form an atomic cross-system transaction on their own.

## 13. Ordering: Adding Consumers Can Break Business Order

### 13.1. Three distinct orderings

| Type | Meaning | Why can it differ? |
| --- | --- | --- |
| **Publish order** | Producer emits W1 before W2 | Source clocks or producer concurrency |
| **Delivery/start order** | Consumer starts W1 before W2 | Broker dispatch, prefetch, scheduling |
| **Commit order** | Business logic for W1 commits before W2 | DB latency, retries, thread pools, side effects |

Multiple competing consumers boost throughput for **independent** work, yet jobs touching the same resource require explicit constraints.

### 13.2. Simulated Mover/Leaver example illustrating stale state

~~~text
Event A: AccountRoleChanged(user=U7, version=10, role=EDITOR)
Event B: AccountDisabled(user=U7, version=11)

Worker A receives event A, processes slowly.
Worker B receives event B, commits DISABLED.
Worker A commits EDITOR afterwards.
~~~

If handlers simply perform last-write-wins by **commit time**, a disabled user could wrongly regain permissions. Use **version checks**, conditional updates, per-userId/aggregateId serialization, or equivalent coordination.

### 13.3. Strategies when ordering is needed

1. **One consumer/partition per aggregate:** events for the same orderId/userId stay on the same partition/serial queue where supported by transport.
2. **Versioned writes:** apply events only if the version is newer; detect gaps.
3. **Per-key serial executor:** per-key locks or queues in handlers, avoiding global serialization when unnecessary.
4. **Optimistic locking:** conditional updates on state version with retry/reload on conflicts.
5. **Reconciliation:** compare source–target state to catch drift from missing or out-of-order events.

**Kafka ordering caveat:** identical keys typically land in the same partition under standard partitioners, yet dispatching records into a multi-threaded ExecutorChannel strips away partition-level **business commit ordering**. For multi-consumer JMS/RabbitMQ queues, never assume global ordering is preserved.

## 14. Retries, Redelivery, and Poison Messages

A **poison message** is a message that consistently fails handler execution, such as unsupported schemas or invalid business data. If the broker repeatedly redelivers it to the same queue, throughput drops and logs flood.

### 14.1. Error classification

| Error | Example | Handling direction |
| --- | --- | --- |
| **Transient network** | DB timeout, HTTP 503, broker reconnect | Bounded retry/backoff |
| **Rate limit** | HTTP 429 | Respect Retry-After, lower concurrency |
| **Schema invalid** | Missing required field | Quarantine/DLQ; no infinite retries |
| **Business rejection** | Order canceled per policy | Record business outcome; no default retry |
| **Unknown duplicate** | Same key, differing payload | Check version/source; never silently drop |
| **Stale version** | Event v10 arrives after v11 | Audited skip/reconcile per contract |
| **Unauthorized producer** | Event from invalid source | Reject and alert |
| **Connector misconfiguration** | Bad credentials, missing queue | Escalate; avoid tight retry loops |

### 14.2. Error workflow

~~~mermaid
flowchart TD
    RECEIVE["Receive work"] --> VALID{"Validate source + schema"}
    VALID -->|Invalid| QUAR["Quarantine / Dead Letter"]
    VALID -->|Valid| EXEC["Idempotent handler"]
    EXEC --> OK{"Commit succeeded?"}
    OK -->|Yes| ACK["Appropriate Ack / Offset commit"]
    OK -->|Transient error| BUDGET{"Retry budget left?"}
    BUDGET -->|Yes| DELAY["Backoff + redelivery"]
    DELAY --> EXEC
    BUDGET -->|No| QUAR
    OK -->|Permanent failure| QUAR
    QUAR --> OPS["Owner review + controlled replay"]
~~~

Set **retry budgets** by error category, risk, and SLA. Retrying inside the handler plus retrying at the broker multiplies execution attempts; document which layer owns retries to avoid **retry storms**.

### 14.3. Dead-letter queues do not fix errors on their own

A DLQ/DLT needs:

- Enough metadata to trace source, workKey, error class, and attempt count.
- View permissions, retention limits, and redaction of sensitive info.
- Owners and triage workflows to fix root causes and replay.
- Safeguards preventing schema-error messages from replaying into the same old binary in an infinite loop.
- Metrics tracking DLQ message age and unprocessed counts.

### 14.4. How one failure affects the entire queue

When workers compete on a queue, a failing message can redeliver repeatedly, bounce across workers, and consume slots/prefetch, slowing down healthy messages. Bounding retries and isolating poison messages lets the main flow continue; however, if messages require per-aggregate order, skipping one may violate business rules and requires a **gap policy**.

### 14.5. Error channels in Spring Integration

Spring Integration provides **ErrorMessage**, `errorChannel`, advice, and error handlers; exact paths depend on sync/async boundaries. On DirectChannel, exceptions can unwind back to listeners; on ExecutorChannel, exceptions can occur after the sender returned. When configuring JMS/AMQP/Kafka inbound adapters, verify **how rethrowing, swallowing, or routing to an error flow** impacts acks and redelivery.

Never assume **adding an errorChannel** automatically ensures broker redelivery. Run integration tests against actual listener containers, transactions, and failure handling in your library version.

## 15. Backpressure, Prefetch, and Choosing Concurrency

Competing Consumers scale capacity by worker count, bounded by networks, DB connection pools, rate limits, and compute resources.

### 15.1. Basic capacity model

Let:

- **λ** = arrival rate of new work (items/second).
- **μ** = sustainable average processing rate of **one worker** (items/second).
- **N** = number of actively running workers, not necessarily deployed instances.
- **C** = maximum capacity of the target system (items/second).

Actual throughput is roughly bounded by:

~~~text
throughput <= min(N × μ, C, broker/source capacity)
~~~

For example, the source generates 200 items/second, each worker handles 30 items/second, and the DB sustains at most 150 items/second:

| Workers | Theoretical capacity N × 30 | DB-capped throughput | Expected backlog growth at arrival=200/s |
| --- | ---: | ---: | ---: |
| 2 | 60/s | 60/s | +140/s |
| 4 | 120/s | 120/s | +80/s |
| 5 | 150/s | 150/s | +50/s |
| 8 | 240/s | 150/s | +50/s |

This is purely a **steady-state theoretical illustration**, omitting retries, hot partitions, I/O, batching, or contention. Scaling from 5 to 8 workers cannot push the DB past 150/s and may even increase locks/retries.

### 15.2. Queue depth and backlog age

**Queue depth** tells how many items are waiting; **age of oldest unprocessed item** tells how long the oldest job has waited. Watch both: a queue of 100 messages waiting an hour can be far more dangerous than 1,000 messages that arrived seconds ago.

### 15.3. Prefetch and fairness

- Low prefetch helps the broker spread opportunities among workers, though high round-trip latency may lower throughput.
- High prefetch lowers overhead, yet one worker may hoard unacked messages, creating **unfair distribution** and tail latency.
- Large batches raise efficiency, yet complicate **retry granularity** when a single item in a batch fails.
- Fast and slow workers cause uneven distribution; never make acceptance criteria require “each worker gets exactly 1/N.”

### 15.4. Bounded concurrency

If consumers call a REST API capped at 50 requests/s, do not spin up 100 threads to “push faster.” Choose appropriate **semaphores/bulkheads**, rate limiters, or worker concurrency. On ExecutorChannel, explicitly bound queue capacity and rejection policies; heap queues do not survive process crashes.

### 15.5. When scale-out stops helping

- Fewer Kafka partitions than consumers in the group.
- One hot partition/key carries most traffic.
- DB locks or transaction serialization become the bottleneck.
- Remote APIs return 429/503 due to quota exhaustion.
- Queue/broker network throughput or connection limits saturate.
- Poison messages generate more retries than successful work.
- Handlers hold locks across HTTP calls, stalling all workers.

## 16. Autoscaling and Worker Allocation

Autoscaling is not merely “spin up more pods whenever the queue has items.” You must choose **trigger signals**, **worker caps**, **warmup times**, and **scale-down thresholds** to prevent oscillation.

### 16.1. Choosing signals

| Signal | Where useful? | Pitfall |
| --- | --- | --- |
| **Queue depth** | JMS/AMQP work queues | Does not reflect differing message weights |
| **Oldest message age** | Any queue with creation timestamps | Requires trustworthy work-creation timestamps |
| **Kafka consumer lag** | Per-partition consumer groups | Lag on one hot partition won't drop with more workers |
| **Processing latency** | Handler/DB/HTTP sinks | May indicate sink congestion where scaling out hurts |
| **CPU/memory** | Compute-bound workers | Poor proxy for backlog when I/O-bound |
| **Retry/DLQ growth** | Repeated failures and poison messages | Scaling out can amplify retry storms |

### 16.2. Safe autoscaling workflow

1. Set **minimum replicas** sufficient for availability and recovery.
2. Monitor backlog/age alongside **committed throughput**, not just messages received.
3. Cap replicas within connection pools, DB quotas, API rate limits, and partition counts.
4. Set stabilization windows before scaling up/down to avoid thrashing.
5. On scale-down, stop listeners from taking new work and finish/roll back in-flight work per protocol.
6. Test rebalancing/requeueing and duplicates; verify idempotency before enabling autoscaling.
7. Periodically load-test with realistic message sizes and error rates.

### 16.3. Kafka scaling differs from AMQP

In Kafka, adding consumers beyond partition count does not increase active consumers. When one partition is unusually heavy, tune partitioning/keys/hot keys or optimize processing rather than just adding pods. In RabbitMQ/JMS work queues, adding consumers can raise message intake yet remains capped by broker, prefetch, and target systems.

### 16.4. Never let the autoscaler break correctness

Adding workers means **raising concurrency**. If idempotency uses per-JVM HashSets, two instances share no state and can produce duplicate results. Business keys, unique constraints, and claims/leases must live in appropriately scoped storage.

## 17. Startup, Shutdown, and Connection Lifecycle

In production, workers stop due to deploys, broker outages, expired credentials, or target failures. The pattern only helps if unfinished work recovers cleanly.

### 17.1. Startup checklist

- [ ] Destinations/topics/queues, bindings, permissions, and broker connections are valid.
- [ ] Listeners/containers have lifecycle managed by Spring ApplicationContext.
- [ ] Consumer groups, queue names, and subscription types match fan-out vs. competing needs.
- [ ] Schemas/deserializers and business idempotency stores are ready before taking load.
- [ ] Concurrency/prefetch are bounded within real resource limits.
- [ ] Error handlers, DLQs/retries, backoff, and alerts are configured and tested.
- [ ] If DB-claimed: leases/owners/versions have safe post-crash reclaim paths.
- [ ] If File/SFTP: producer file-ready contracts, persistent metadata, and locks/claims cover multi-instance runs.
- [ ] Dev/test environments never accidentally subscribe to production queues.

### 17.2. Graceful shutdown

~~~text
Shutdown signal
    ↓
Listeners stop accepting new work (per container capabilities)
    ↓
In-flight work completes or rolls back/requeues per contract
    ↓
Ack / commit offsets only for work meeting completion criteria
    ↓
Close broker sessions, DB pools, and resources
~~~

If shutdown timeout kills the process, **unacked messages may be redelivered**. That is expected under at-least-once; tests must prove business state is not unintentionally duplicated. Never delete source data before business outcomes are persisted.

### 17.3. Lifecycle failure table

| Scenario | Symptom | Action needed |
| --- | --- | --- |
| JMS broker restart | Listeners drop sessions | Reconnect, verify redelivery and in-flight state |
| RabbitMQ connection close | Unacked messages handled per broker policy | Reconnect, check ack/requeue/DLQ |
| Kafka rebalance | Assignments shift, processing pauses | Commit/ack accurately, avoid duplicates, handle stale workers |
| DB pool exhaustion | Handler timeouts, growing backlog | Reduce concurrency, tune pools/transactions |
| Slow HTTP sink | Held threads, 429/503 | Rate limits/bulkheads/circuit breakers |
| Stale SFTP session | File polls make no progress | Reconnect, reconcile metadata/claims |
| Pod killed with active work | Unfinished work may redeliver | Idempotency, recovery, graceful shutdown windows |
| Credential rotation | Connection/auth failures | Secret lifecycle, alerts, controlled reconnect |

### 17.4. Zombie workers and fencing

With lease mechanisms (especially DB/custom polling), worker A may keep running after its lease expires while worker B already reclaimed the task. If both commit, side effects can repeat. **Fencing tokens or conditional version checks at commit time** reject stale workers that lost ownership, and must be enforced at the final write store—locking solely at pickup is insufficient.

### 17.5. Topology and connection counts

Multiple containers/consumers create multiple broker sessions/connections and DB connections. Compute total limits, not just per-worker numbers. Configuring 10 pods × 8 listener threads can open dozens or more connections/sessions depending on the container. Size alongside pools, broker quotas, and resource limits.

## 18. Observability: Measuring Real Progress in Competing Consumers

A multi-consumer system can look healthy because messages are **delivered very fast**, while DB writes stay flat because handlers keep retrying. Monitor **end-to-end**, not just consumption counts.

### 18.1. Metrics table

| Metric | Meaning | Suggested alert |
| --- | --- | --- |
| **published messages** | New work entering source | Abnormal rate or publishing stopped |
| **deliveries / receives** | Messages handed by broker/channel to consumers | Rising while processed stays flat |
| **in-flight/unacked** | Work held/unacked by consumers | High count, skewed distribution |
| **committed success rate** | Business completion rate | Dropping while backlog grows |
| **processing latency P50/P95/P99** | Handler/side-effect duration | Tail latency climbing |
| **queue depth / Kafka lag** | Unprocessed work per transport | Steady growth under normal load |
| **oldest unprocessed age** | Delay of oldest pending item | Exceeds business SLA |
| **retry/redelivery rate** | Failures or repeat processing | Sustained high rate or repeating business keys |
| **duplicate suppressed** | Duplicate work caught | Spikes after restarts/rebalances |
| **DLQ/DLT count + age** | Work needing manual intervention | Missing owner or overdue |
| **worker active/idle** | Actual work-sharing health | One worker hoarding unacked work or lacking partitions |
| **DB/HTTP sink latency, saturation** | Downstream bottlenecks | Scale-out fails to raise throughput |
| **last business commit** | Verified business progress | Source has work yet no recent commits |

**Metric labels** should use flow name, target, consumer group, queue/partition, environment, and error class; never put full businessKeys, eventIds, or payloads into labels due to cardinality and leak risks.

### 18.2. Safe audit log example

~~~json
{
  "flow": "invoice-jobs-consumer",
  "workId": "WORK-LAB-0041",
  "consumerName": "invoice-generation",
  "workerInstance": "worker-lab-b",
  "source": "invoice.jobs",
  "attempt": 2,
  "stage": "BUSINESS_COMMIT",
  "result": "SUCCESS",
  "durationMs": 193,
  "traceId": "TRACE-LAB-0041",
  "committedAt": "2026-11-23T14:00:13+07:00"
}
~~~

This is an **illustrative** format, not Spring Integration's default log output. In real environments, minimize PII, omit secrets, and apply proper access controls and retention policies.

### 18.3. Is uneven distribution always a bug?

Not necessarily. Worker A processing 800 messages while B processes 200 in the same window can stem from handler speed or prefetch. Check:

- Is any worker **stuck**?
- Is there a **hot partition/key**?
- Is overdue work growing?
- Is one worker holding many **unacked** messages while others sit idle?
- Do overall throughput and latency meet targets?

If performance is healthy and there is no strict fairness requirement, uneven distribution can be acceptable.

### 18.4. Three alerts that catch failures early

1. **No progress:** queue has pending work yet no new business commits occur within threshold.
2. **Oldest work age exceeded:** workers are running yet critical work is stalled.
3. **Failure loop:** retries/DLQ grow faster than successful throughput, especially from one schema or remote sink.

## 19. Common Incident Runbooks

An operational template must answer **where it is failing, which work is impacted, whether loss/duplication risks exist, who owns it, and how to verify recovery**.

### 19.1. Runbook A — Rapidly growing backlog

1. Check arrival rate and **business commits/s**, not just broker delivery rate.
2. Check processing latency, retries, DB pools, API quotas, and lock contention.
3. Verify **actually active** workers: Kafka partition assignments or JMS/AMQP listener health.
4. Inspect prefetch/unacked counts and slow workers hoarding work.
5. Increase concurrency cautiously **only if the sink has headroom**; otherwise shed load/rate-limit.
6. Re-measure queue depth, oldest age, and commit throughput after changes.

### 19.2. Runbook B — Message processed twice

1. Grab **workId/businessKey** and check audits across both workers.
2. Identify whether it was redelivery, manual retry, ACK timeout, or producer duplicate.
3. Check unique constraints/idempotency transactions in the business layer.
4. If duplicate side effects occurred, execute authorized business remediation/compensation.
5. Add a regression test for **commit succeeds, ack fails, redelivery**.
6. Never “fix” this by disabling broker redelivery, which causes failed work to vanish.

### 19.3. Runbook C — Poison message blocking the queue

1. Find the repeating workKey, message schema, and error class.
2. Classify permanent vs. transient; never replay schema errors into unsupported code.
3. Enforce retry budgets and move to DLQ/quarantine per policy.
4. Inspect the isolated payload, root cause, and owner.
5. Run controlled replay after fixing and record outcomes.

### 19.4. Runbook D — Worker receives no messages

Check queue/topic, consumer group, partition assignments, subscriptions, credentials, network, listener startup, health, and environment configuration. If workers A and B belong to **two different groups**, both may receive every event (logical fan-out) instead of sharing work; check before scaling replicas.

### 19.5. Runbook E — Mid-flight stop/redeploy

Record in-flight/unacked counts, last business commit timestamp, open transactions, listener/offset states, queue lag, and post-restart results. Run kill-process tests in authorized environments; verify unfinished work is safely re-claimed without double charges/invoices.

### 19.6. Runbook F — Two SFTP pollers grab the same file

Inspect remote file ID/path, each replica's filter metadata, shared locks/claims, producer rename/markers, post-crash processing state, and business keys. Fix via shared/persistent metadata and end-to-end idempotency; never recklessly delete source files to stop duplicates before verifying business commit.

## 20. Hands-on Lab: Processing Invoices with Multiple Workers

**Goal:** demonstrate progressing from an internal work queue to a test broker with multiple consumers receiving distinct work items, and prove **business effects occur only once** even after redelivery.

### 20.1. Context

**InvoiceJob Producer** creates work items to generate invoices. Each item carries **workId**, **tenantId**, **orderId**, and **invoiceType**. The system accepts many independent jobs, yet must never create two invoices of the same type for the same order due to retries/crashes.

~~~json
{
  "workId": "WORK-LAB-0041",
  "type": "GenerateInvoice",
  "tenantId": "TENANT-LAB-01",
  "orderId": "ORDER-LAB-0088",
  "invoiceType": "STANDARD",
  "schemaVersion": 1
}
~~~

**Assumed lab business rule:** each key tuple (**tenantId, orderId, invoiceType**) has at most one valid active invoice. This is a lab choice, not a universal rule for all billing systems (e.g., adjustment invoices may need separate versions and types).

### 20.2. Two-tier architecture

~~~mermaid
flowchart TD
    P["Producer"] --> IN["API / Application Service"]
    IN --> Q1["Phase A: QueueChannel in JVM"]
    Q1 --> W1["PollingConsumer A"]
    Q1 --> W2["PollingConsumer B"]
    W1 --> BIZ["Validate + Idempotent Invoice Service"]
    W2 --> BIZ
    IN --> Q2["Phase B: Durable Broker Queue"]
    Q2 --> A["Listener instance A"]
    Q2 --> B["Listener instance B"]
    A --> BIZ
    B --> BIZ
    BIZ --> DB["Test Database + unique key"]
    BIZ --> AUDIT["Test evidence"]
~~~

**Phase A and Phase B are two separate exercises**, not a producer simultaneously sending the same work to both branches unless the lab explicitly tests duplication.

### 20.3. Step 1 — Build internal QueueChannel

Use the Java DSL config from section 6. Set capacity=100 with two polling consumers sharing QueueChannel. Producer sends **WORK-LAB-001 through WORK-LAB-010**. Log workId and workerId in the handler.

Expectations:

- On each dequeue, one endpoint receives the job; never broadcast to both.
- Both may receive unequal counts.
- Work has no guaranteed cross-consumer completion order.
- Do not infer post-crash exactly-once since QueueChannel is in memory.

### 20.4. Step 2 — Replace logging with a business handler

Create a test repository persisting invoices using a DB unique key:

~~~sql
CREATE TABLE invoice_lab (
    invoice_id VARCHAR(120) PRIMARY KEY,
    tenant_id VARCHAR(120) NOT NULL,
    order_id VARCHAR(120) NOT NULL,
    invoice_type VARCHAR(60) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_invoice_business
        UNIQUE (tenant_id, order_id, invoice_type)
);
~~~

When receiving new work:

1. Validate schema, tenant, and command source authorization.
2. Derive the business key and check if a valid invoice already exists.
3. Insert the invoice inside a transaction with a unique constraint; two racing workers must resolve conflicts safely.
4. Audit-log workId, result, and commit timestamp.
5. Do not treat duplicate-key exceptions as severe data errors if they indicate already-completed work; still check payloads do not conflict.

**Note:** an in-memory HashSet is only useful to start learning; proving dedupe across restarts and instances requires durable storage.

### 20.5. Step 3 — Simulate two workers handling the same business key

Send two messages with **different workIds** yet identical invoice business keys; then resend the first message itself. Proper handling protects by business key:

~~~text
WORK-LAB-0041 → (TENANT-01, ORDER-88, STANDARD)
WORK-LAB-0042 → (TENANT-01, ORDER-88, STANDARD)
WORK-LAB-0041 → (TENANT-01, ORDER-88, STANDARD) [redelivery]

Expected: 1 invoice per lab rules; subsequent arrivals are recognized
          as duplicates/existing results or payload conflicts.
~~~

The distinction between **workId duplicates** and **business key collisions** matters: in other domains, two valid workIds might target the same entity with two distinct actions. Always define keys per business contract.

### 20.6. Step 4 — Add a test broker

Pick an authorized **JMS test broker or RabbitMQ test container**—no need for both immediately. Create queue `invoice.jobs` with two subscribing listeners/instances. In Spring Integration, wire a message-driven inbound adapter into the business handler. Configure ack/transactions, retries, and DLQ per broker choice.

Observe the differences:

| Aspect | Internal QueueChannel | Broker queue |
| --- | --- | --- |
| Where pending work lives | Inside JVM per sample config | Broker/store per configured durability |
| When one worker crashes | Dequeued work can be lost without custom recovery | Broker can redeliver unacked items per semantics |
| When whole JVM crashes | In-memory queue vanishes | Work persists depending on broker/durability |
| Multiple replicas | Cannot share one JVM QueueChannel | Can share one queue |
| Ack | No broker acknowledgment | Has ack/transaction/redelivery mechanisms |
| Ordering | Per queue receive + worker scheduling | Per broker/concurrency/prefetch |

### 20.7. Step 5 — Fault injection

Run sequentially:

- **DB timeout before commit:** must not record false success; message retries per contract.
- **DB commit then worker dies before ack:** broker redelivers; unique key/idempotency prevents double invoices.
- **Schema-invalid JSON:** after bounded retries, moves to quarantine/DLQ without blocking valid work.
- **Worker A stops abruptly:** worker B processes broker-redistributed work; verify failover via readback.
- **Worker B runs slowly:** observe distribution, prefetch/unacked counts, and queue age.
- **Two instances hit key conflict concurrently:** DB still contains exactly one invoice per business rule.

### 20.8. Step 6 — Measure throughput and backlog

Generate 100 or 1,000 mock jobs; scale consumers from 1 to 2, 4, 8. Keep DB limits constrained to observe the **saturation point**. Record **committed** messages/second, not just receives. Also measure queue depth, oldest age, retries, and CPU/DB pools.

### 20.9. Step 7 — Try Kafka with consumer groups

Optionally create a test topic with **three partitions**, group `billing-workers`, and run **1, 2, 3, 4 consumer instances** in turn. Record:

1. Partition assignments.
2. Active consumers actually holding partitions.
3. Consumer lag and commit throughput.
4. Behavior after killing/restarting one instance.
5. Ordering by **orderId** and post-rebalance duplicates.

**Do not expect a fourth consumer to raise throughput** when the group only has three partitions to assign.

### 20.10. Lab deliverables

| Deliverable | Contents |
| --- | --- |
| Topology | Producer, queue/topic, workers, business DB, DLQ |
| Message contract | workId, tenant, order, business key, version |
| Worker implementation | Spring Integration endpoints and handlers |
| Test DB schema | Unique keys/idempotency and business state |
| Fault injection | Pre-commit, post-commit/pre-ack, poison message, worker crash |
| Observability | Commit rate, queue depth/lag, retries, DLQ age |
| Runbook | Retries, duplicates, backlog, worker restart, and DLQ replay |
| Limitations | What was simulated vs. verified on a real broker |

## 21. Competing Consumers Test Matrix

Every test case must record **Input, Expected, Actual, PASS/FAIL/UNKNOWN, Evidence**. The Expected column is the design criterion; never mark PASS just from writing code without executing tests.

| ID | Scenario | PASS condition |
| --- | --- | --- |
| **CC-01** | One QueueChannel, two PollingConsumers | Single receive never broadcasts the same message to both |
| **CC-02** | Empty QueueChannel | Business handler not called with null payloads |
| **CC-03** | Send 10 work items | Every valid job produces a clear result or error; even split not required |
| **CC-04** | QueueChannel at capacity | Producer encounters controlled backpressure/failure |
| **CC-05** | Handler after QueueChannel throws | Broker redelivery not assumed; explicit recovery mechanism exists |
| **CC-06** | Restart JVM while in-memory queue holds messages | Durability limit documented; no false zero-loss claim |
| **CC-07** | JMS Queue with three listeners | Work split across listeners per broker contract |
| **CC-08** | JMS Topic with two independent subscriptions | Fan-out distinguished from competing consumers |
| **CC-09** | JMS listener fails before commit | Redelivery/rollback verified per configuration |
| **CC-10** | RabbitMQ two consumers on one queue | Deliveries shared, not broadcast |
| **CC-11** | RabbitMQ high prefetch + one slow worker | Unacked/imbalance observable, no false claims |
| **CC-12** | RabbitMQ repeated nack/requeue | Bounded retry/DLQ, no infinite loop |
| **CC-13** | Kafka 3-partition topic, 2-consumer group | Valid partition assignment, no duplicate active owners |
| **CC-14** | Kafka 3 partitions, 4 consumers in group | Extra consumer does not increase active partitions |
| **CC-15** | Kafka two consumer groups | Each group gets events per its own contract |
| **CC-16** | Kafka rebalance before offset commit | Safe redelivery, no doubled business effects |
| **CC-17** | Kafka hot partition | Per-partition lag measured, scaling limit identified |
| **CC-18** | File/SFTP two replicas without shared metadata | Duplicate file processing risk detected |
| **CC-19** | SFTP with shared claim and worker crash | Valid recovery without losing work |
| **CC-20** | JDBC two workers claim one READY row | Only one claim succeeds at a time |
| **CC-21** | DB lease expires while old worker still runs | Fencing/version blocks stale worker from bad commit |
| **CC-22** | HTTP caller retries to a different instance | Shared idempotency store prevents duplicate side effects |
| **CC-23** | Business commit succeeds, broker ack lost | Redelivery creates no extra invoice |
| **CC-24** | Two distinct workIds share one business key | Unique constraint protects per policy |
| **CC-25** | Same workId with conflicting payload | Not silently ignored; conflict reported or version handled |
| **CC-26** | Invalid schema | Quarantine/DLQ with owner and reason |
| **CC-27** | DB timeout before commit | Safe retry without premature processed mark |
| **CC-28** | Worker A dies, worker B alive | Unacked work redistributed per contract |
| **CC-29** | Event v10 processed after v11 | Never overwrites newer state |
| **CC-30** | Consumers scaled from 2 to 8 while DB saturated | Metrics reveal bottleneck; no fake throughput claims |
| **CC-31** | Backlog age crosses threshold | Alert flags overdue unprocessed work |
| **CC-32** | DLQ replay after schema fix | Idempotent replay without duplicate side effects |
| **CC-33** | Shutdown with unacked messages | Rollback/requeue/commit per contract without silent loss |
| **CC-34** | Sink API returns 429 | Concurrency lowered/backoff applied, avoiding retry storms |
| **CC-35** | Unauthorized tenant | No side effects executed; safe audit recorded |
| **CC-36** | Logs contain tokens/private keys | Redaction active; no secrets exposed |

### 21.1. Sample test report for CC-23

~~~yaml
testCase: CC-23
workId: WORK-LAB-0041
scenario: "DB commit succeeds, worker dies before broker ack"
expected: "Broker redelivers; exactly one business invoice remains"
actual: "Fill after running the lab"
result: PENDING
evidenceRef: "lab://tests/CC-23"
owner: invoice-lab
verifiedAt: null
~~~

**Actual and evidenceRef must come from real test execution.** If tests cannot trigger a crash at that exact instant, mark **UNKNOWN/PENDING** and document the missing reproduction steps rather than filling in PASS.

### 21.2. Especially important negative tests

1. **Duplicate after commit:** redelivery after DB commit.
2. **Poison-message loop:** unfixable schema error where DLQ must intervene.
3. **Stale event:** older version message finishes after a newer message.
4. **Shared storage race:** two workers attempting to claim the same task.
5. **Wrong subscriber topology:** accidentally sharing one queue across two domains that both need every message.
6. **Ack before async business completion:** listener returns while an ExecutorChannel worker is still running.

Passing these six tests is usually far more valuable than simply proving four workers print to the console.

## 22. Anti-Patterns and Production Checklist

### 22.1. Common mistakes

| Anti-pattern | Why it is dangerous | How to improve |
| --- | --- | --- |
| **Confusing fan-out with competing consumers** | One domain may miss events | Separate queues/subscriptions/groups per domain; compete within each |
| **Treating multiple @ServiceActivators on DirectChannel as a durable queue** | Lacks broker persistence/redelivery | Use a broker or durable state store when durability is needed |
| **Using in-memory QueueChannel for critical financial transactions** | Crashes can lose queued/dequeued work | Durable queues + idempotency + failure testing |
| **Adding workers when DB is already saturated** | Increases contention, retries, and latency | Measure sink throughput, bound workers, optimize DB |
| **Adding more Kafka consumers than partitions expecting speedup** | Consumers without partitions sit idle | Adjust partitions/keys or handlers, not just replicas |
| **Using one Kafka group for Billing and Analytics** | Events get split; neither domain sees all events | Separate groups per logical subscriber |
| **Using in-memory metadata across SFTP replicas** | Two instances pull the same file | Shared persistent metadata/claims + business idempotency |
| **SELECT READY then process immediately** | Two DB workers pick up the same task | Transactional claims/locks/leases |
| **Acking broker before business commit** | Crashes lose work while broker thinks it succeeded | Ack after completion conditions or durable handoff |
| **Trusting ack/commit proves exactly-once** | Post-commit redelivery can repeat side effects | Inbox/idempotency/unique business keys |
| **Unbounded retries** | Poison messages/retry storms clog queues | Backoff, retry budgets, DLQs, owners |
| **Excessive prefetch without monitoring unacked** | One worker hoards messages, poor fairness | Tune to latency, load, and recovery needs |
| **Increasing concurrency when key ordering is required** | Old events overwrite new ones | Partition keys, version checks, or per-key serialization |
| **Counting only receives as throughput** | Handlers may be failing and never committing | Measure committed successes and backlog age |
| **Using per-instance HashSets for production dedupe** | Lost on restart and unshared across replicas | Durable unique constraints/idempotency stores |
| **Failing to separate business rejections and technical failures** | Wrong retries or dropped valid work | Explicit error taxonomy and outcomes |
| **Treating HTTP load balancers like brokers** | No durable acks/redelivery | Persist jobs/queues before returning accepted |
| **Skipping graceful shutdown tests** | In-flight work left in ambiguous states | Kill/restart tests and runbooks |
| **Logging full payloads/credentials** | Data and secret leaks | Redaction, data minimization |

### 22.2. Checklist for choosing Competing Consumers

- [ ] Unit of work clearly defined with a stable business key.
- [ ] Identified which business groups must **all receive every event** vs. **share work**.
- [ ] Appropriate topology selected: JMS Queue, RabbitMQ queue, Kafka consumer group, or custom claim mechanism.
- [ ] When using in-JVM QueueChannel, persistence/redelivery limits are explicitly understood.
- [ ] When using File/SFTP/JDBC, shared claims/locks/metadata cover multi-instance runs.
- [ ] Message contracts define schema versions, sources, tenants, and authn/authz checks.
- [ ] Ack, offset commits, or processed marks occur at appropriate milestones.
- [ ] Business idempotency is shared across workers and restarts.
- [ ] Work key reuse and payload conflicts are handled.
- [ ] Ordering and stale versions are checked when jobs mutate stateful entities.
- [ ] Retry budgets, backoff, DLQs/quarantine, and replay policies have owners.
- [ ] Prefetch/batching/concurrency are bounded and empirically measured.
- [ ] Downstream capacity matches; rate limits and DB saturation are accounted for.
- [ ] Multi-instance/consumer group/partition assignments are verified.
- [ ] Startup, graceful shutdown, and broker reconnect have runbooks.
- [ ] Metrics distinguish delivered, processed, committed, acked, and duplicated.
- [ ] Alerts exist for backlog age, no progress, retry loops, and overdue DLQs.
- [ ] Tests cover post-commit/pre-ack crashes and stale events.
- [ ] Unnecessary tokens/secrets/PII are excluded from logs and headers.
- [ ] Responsibility map exists from source to handler, business store, and on-call operator.

### 22.3. Design decision tree

~~~mermaid
flowchart TD
    START{"Do multiple domains need every event?"}
    START -->|Yes| FAN["Create subscription / queue / group per domain"]
    START -->|No| Q{"Is source already a durable work queue?"}
    FAN --> Q2["Competing workers within each subscription"]
    Q -->|JMS/AMQP| BROKER["Competing listeners on same queue"]
    Q -->|Kafka| K["Same group; partition assignment"]
    Q -->|File/SFTP/DB| CLAIM["Shared claim / leader / durable broker stage"]
    Q -->|QueueChannel in JVM| LOCAL["Local PollingConsumers; document durability limits"]
    Q2 --> SAFE["Ack + idempotency + ordering + errors"]
    BROKER --> SAFE
    K --> SAFE
    CLAIM --> SAFE
    LOCAL --> SAFE
    SAFE --> SCALE["Measure sink capacity + prefetch + backlog"]
    SCALE --> TEST["Crash/retry/rebalance tests before production"]
~~~

If you cannot yet answer **“when is a job considered complete and who proves it?”**, do not raise consumer counts. Define the completion contract before scaling.

## 23. Summary and Self-Assessment Questions

### 23.1. Eight things to remember

1. **Competing Consumers** is a pattern for **dividing work** among workers, not broadcasting every message to all of them.
2. Multiple consumers on a **JMS/AMQP queue** compete for work; with **Kafka**, you must understand **consumer groups and partition assignments**.
3. **QueueChannel + PollingConsumers** illustrate the pattern inside one JVM without providing broker-grade durability/acks.
4. **Event-driven Consumer and Polling Consumer** describe how reception triggers, whereas Competing Consumers describes work distribution; these patterns can coexist.
5. **File/SFTP/JDBC** require shared claims/locks/metadata or broker staging when running multiple instances; scanning the same source does not prevent duplicates.
6. **Ack/offsets** and **business commits** are not the same milestone. Redelivery is normal and must be absorbed via idempotency.
7. **Ordering and concurrency** can conflict; business versioning and key-based partitioning protect critical state.
8. **Scale-out** helps only until hitting broker, partition, DB, API rate-limit, or domain constraints.

### 23.2. Self-check questions

1. Why do three consumers on the same RabbitMQ queue **not** deliver every event to Billing, Analytics, and Email independently?
2. If JMS listener A commits to the DB and crashes before acking, what can JMS listener B do and how must the DB protect itself?
3. When are two PollingConsumers on a QueueChannel sufficient for a lab yet unsuitable for critical production financial processing?
4. How does a DirectChannel with multiple subscribers differ from a PublishSubscribeChannel?
5. With a three-partition Kafka topic, does adding a fourth consumer to the same group increase work parallelism?
6. Why can high prefetch let one worker hold many unacked jobs while another worker sits idle?
7. Why do two SFTP pollers both using **in-memory** accept-once filters still duplicate-process files?
8. Does `SELECT status=READY` prevent two workers from grabbing the same DB row?
9. If AccountDisabled v11 commits and AccountRoleChanged v10 arrives late, what check is needed?
10. How do you tell whether rising queue depth is caused by too few workers or a saturated DB/HTTP sink?
11. What does a DLQ need besides a queue holding failed messages?
12. During a rolling deploy, what happens to in-flight unacked messages?

**Hints:** (1) shared queue divides work; fan-out needs separate subscriptions/queues; (2) redelivers, rely on idempotency/unique keys; (3) durability, recovery, and multi-instance limits; (4) one handler selected vs. broadcast; (5) usually no without extra partitions to assign; (6) unacked prefetch reservation; (7) JVMs don't share memory metadata; (8) no, requires transactional claim; (9) version/order check; (10) measure committed throughput, latency, and sink saturation; (11) retention, owner, triage/replay; (12) commit or requeue/redeliver per contract.

### 23.3. Conclusion

The **Competing Consumers Pattern** is a key tool for scaling throughput and resilience in integration systems: multiple workers share a queue or consumer group to process **distributable** work items. In **Spring Integration Adapters**, this pattern appears in **PollingConsumers reading QueueChannel**, **JMS/AMQP message-driven inbound adapters**, and **Kafka consumer groups**, as well as File, SFTP, HTTP, and Database flows once data is staged as durable work or safely claimed.

However, adding workers only solves **part of reception and execution capacity**. Reliable outcomes depend on **message contracts, idempotency, transactions, acknowledgments, dead-lettering, ordering, backpressure, lifecycles, and observability**. When you can prove **a worker killed after business commit but before ack causes safe redelivery with accurate, non-duplicated business state**, you have moved from understanding the pattern to operating a production-ready competing consumers flow.

**Closing principle:** *Splitting work to go faster is easy; proving every job completes accurately, without loss and without duplicate side effects after failures, is the true measure of a sound Competing Consumers design.*
