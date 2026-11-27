# Choosing Between Azure Queue Storage and Azure Service Bus

When an API has to concurrently handle many order requests, email notifications, thumbnail generation, or report calculations, performing every task inside the HTTP request itself easily causes timeouts and makes the system hard to scale. A **message queue** decouples the sender from the processor: the API sends a short message, and a worker retrieves the message and processes it asynchronously. When workers are slow or temporarily unavailable, messages can remain in the queue according to configured limits and retention policies.

Microsoft Azure offers two popular options: **Azure Queue Storage** and **Azure Service Bus**. Both connect components asynchronously, but they differ in business capabilities, delivery mechanisms, routing, operational complexity, and pricing models. Choosing the right service depends not only on messages per second, but also on key questions: **Do you need ordering within a business group, publish/subscribe, a built-in dead-letter queue, transactions, duplicate detection, or reliable workflows?**

This lesson belongs to the **Queues and Messaging** chapter in the **CLOUD_PROVIDERS_AZURE** module. Its content connects Azure Storage, Microsoft Entra ID, Azure Functions, Java applications, virtual networks, monitoring, security, and cost optimization for an Azure application architecture.

> **Scope:** message size limits, quotas, tier-specific features, and unit pricing may vary by region, service version, and deployment time. The examples provide decision models and integration patterns; in real operations, always verify the current limits of the **exact SKU, namespace/storage account, and SDK version**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the **producer → queue → consumer** model and the difference between storing data and sending messages.
2. Compare Azure Queue Storage and Azure Service Bus in terms of features, scale, ordering, retry, dead-lettering, and security.
3. Choose **Service Bus Queue**, **Service Bus Topic/Subscription**, or **Queue Storage** for real-world scenarios.
4. Distinguish Queue Storage's **visibility timeout + pop receipt** from Service Bus's **Peek-Lock + settlement**.
5. Design message payloads, idempotency keys, retries, backoff, poison-message handling, and processing state.
6. Send, receive, and settle messages using the Azure SDK for Java with identity-based authentication.
7. Identify when **sessions, duplicate detection, dead-lettering, scheduling, and transactions** are needed.
8. Design access control, private networking, monitoring, alerts, cost controls, and resiliency.
9. Build a checklist to evaluate, test, and migrate messaging backends when requirements change.

## 2. The Essence of a Queue

A simple queue has three roles:

- **Producer:** an application, API, or event source that sends messages.
- **Queue/Broker:** accepts and holds messages within retention limits and dispatches them to consumers.
- **Consumer:** a worker that retrieves messages, processes them, and confirms the result.

~~~mermaid
flowchart LR
  U["HTTP client"] --> A["Order API (producer)"]
  A --> Q["Message queue"]
  Q --> W1["Worker 1"]
  Q --> W2["Worker 2"]
  W1 --> DB["Database / Blob Storage"]
  W2 --> DB
  A --> RESP["202 Accepted + jobId"]
~~~

In this architecture, the API can respond quickly once the **message has been successfully sent**; the actual work happens later. If workers need maintenance, the queue helps reduce temporal coupling between producer and consumer. However, a queue does not replace ensuring that the API validated the input, the backend has sufficient capacity, job state is updated, and users can look up results.

### A Message Is Not the Entire Business Payload

A message should contain the information needed to locate or process a task, for example:

~~~json
{
  "schemaVersion": 1,
  "messageId": "order-1024-created",
  "jobId": "job-7f23",
  "orderId": "order-1024",
  "occurredAt": "2026-11-20T08:15:00Z",
  "blobRef": "orders/input/order-1024.json"
}
~~~

If the payload is a 500 MiB video file, you should not embed the entire file directly into the message. Store it in **Blob Storage**, send a **reference, ID, checksum, or credential-free URI**, and let the worker download the data using its granted permissions.

Note that the **message body** is not automatically encrypted at the business level beyond platform-level encryption; do not include passwords, tokens, card data, or sensitive information exceeding policy in message contents or logs.

## 3. What Is Azure Queue Storage?

**Azure Queue Storage** is a queue service within an Azure Storage account. It provides a durable, relatively simple mechanism for one or more consumers to process messages asynchronously.

Key concepts:

- **Storage account:** the parent resource containing the queue, sharing the Azure Storage monitoring and security ecosystem.
- **Queue:** a named storage area for messages, such as `image-jobs`.
- **Message:** the payload sent to the queue, along with service-managed metadata.
- **Visibility timeout:** the period during which a message retrieved by a consumer is temporarily hidden from other consumers.
- **Pop receipt:** a value provided by the service to authorize operations on a specific message retrieval; required when deleting or updating the message via the corresponding API.
- **Time-to-live (TTL):** how long a message is retained before expiring according to configuration and service limits.
- **Dequeue count:** the number of times a message has been retrieved for processing; useful for detecting repeatedly failing messages.

### Typical Processing Flow

1. The producer sends a message to the queue.
2. The consumer receives the message and a **pop receipt**.
3. The message becomes hidden during the visibility timeout.
4. The worker processes it and persists the result to durable storage.
5. If successful, the worker calls **delete message** using the message ID and current pop receipt.
6. If the worker crashes or fails to delete the message, after the visibility timeout expires, the message can reappear for further processing.

~~~mermaid
flowchart TD
  P["Producer sends message"] --> Q["Azure Queue Storage"]
  Q --> R["Receive + pop receipt"]
  R --> V["Message temporarily hidden during visibility timeout"]
  V --> O{"Worker succeeded?"}
  O -->|Yes| D["Delete with messageId + popReceipt"]
  O -->|No / worker lost| X["Timeout expires, message can be received again"]
  X --> R
~~~

**This is at-least-once processing from an application design perspective:** the same message can be received again. You must never assume exactly-once processing simply because a client received it successfully.

### Suitable Characteristics

Queue Storage is attractive when you need a **simple queue, easy integration with Azure Storage, and no complex broker features**, or when a pipeline has a single stream of tasks processed by competing consumers.

Several features often needed in business systems—such as broker-level topics/subscriptions, message sessions, or a dead-letter subqueue—**are not equivalent built-in features in Queue Storage**; if you need them, you must build custom logic or choose Service Bus.

## 4. What Is Azure Service Bus?

**Azure Service Bus** is a managed **enterprise message broker** service. In addition to point-to-point queues, it provides a **Topic/Subscription** model to distribute an event to multiple consumer groups, along with advanced message-processing features depending on the tier.

Concepts:

- **Namespace:** the management scope for queues, topics, subscriptions, policies, networking, and permissions.
- **Queue:** a message is placed into a queue to be processed by one consumer in a competing consumer group.
- **Topic:** a publish endpoint for sending messages to multiple receiving groups.
- **Subscription:** a logical queue attached to a topic; each subscription receives messages matching supported rules/filters.
- **Peek-Lock:** the consumer receives a message in a locked state without the broker deleting it yet; the consumer then calls **complete/abandon/dead-letter/defer** via the appropriate API.
- **Dead-letter queue (DLQ):** a secondary subqueue managed by the service to store messages that cannot be processed under defined rules.
- **Session:** groups messages with the same session ID to support ordered, exclusive processing at the session level within supported mechanisms.
- **Duplicate detection:** an optional feature enabling the broker to detect duplicate messages by MessageId within a configured window when supported by the tier/entity.

~~~mermaid
flowchart LR
  API["Order API"] --> TOP["Topic: order-events"]
  TOP --> SUB1["Subscription: billing"]
  TOP --> SUB2["Subscription: notifications"]
  TOP --> SUB3["Subscription: analytics"]
  SUB1 --> B["Billing worker"]
  SUB2 --> N["Notification worker"]
  SUB3 --> A["Analytics worker"]
~~~

**A Topic is not the same as a Queue:** with a queue, consumers compete to pull work from the same queue; with a topic, each matching subscription receives its own logical copy for that consumer group to process. A consumer in the `billing` subscription does not remove the message from `notifications`.

## 5. Quick Comparison Table

| Criterion | Azure Queue Storage | Azure Service Bus |
|---|---|---|
| Primary goal | Simple task queue | Enterprise messaging, workflows, and event fan-out |
| Parent resource | Storage account | Service Bus namespace |
| Point-to-point, competing consumers | Yes | Yes, via a queue or within the same subscription |
| Topic/Subscription pub-sub | No built-in broker topics | Yes, on supported tiers |
| Receiving and holding messages | Visibility timeout + pop receipt | Peek-Lock + lock token/settlement |
| Confirming success | Delete message | Complete message under Peek-Lock |
| Reprocessing | Message reappears after visibility timeout | Abandon, lock expiry, retry/settlement |
| Built-in DLQ | No separate Queue Storage DLQ | Has dead-letter subqueue |
| FIFO within business group | Strict FIFO not guaranteed with parallelism/retries | Sessions can support ordering within a session |
| Broker duplicate detection | No equivalent built-in feature | Yes, when enabled and supported by tier |
| Scheduled messages | Application must manage scheduling | Supports scheduled messages |
| Broker transactions | No equivalent Service Bus mechanism | Supports certain transaction operations within defined scope |
| Filtering/rules | Implemented by the application | Subscription filters/rules |
| Authorization | Entra ID/RBAC or Storage authorization | Entra ID/RBAC or SAS depending on configuration |
| Network | Storage firewalls/private endpoints | Network controls/private access depending on tier/features |
| Cost model | Storage + operations/transactions + traffic | Messaging tier/operations/capacity + traffic |
| Complexity | Lower for simple workloads | Higher, with many additional features |

**Neither service is universally better.** Queue Storage can be the right solution for millions of simple jobs; Service Bus may be necessary even at low traffic if the business requires sessions, dead-lettering, pub-sub, or reliable processing workflows.

## 6. Choosing Queue Storage or Service Bus Based on Requirements

### Start with Azure Queue Storage When

1. You have a relatively independent job type where each message needs one worker to process it.
2. You do not need broker-level topics/subscriptions or message filters.
3. Strict ordering is not required under retries and parallel processing.
4. You can handle poison messages, idempotency, and job tracking yourself.
5. Your application infrastructure already uses Azure Storage and you want to minimize complexity.
6. You have properly evaluated message size, queue size, request rate, SLA, and cost.

**Example:** an image upload service sends a `resize-image` message; multiple workers fetch the image from Blob Storage, generate thumbnails, and delete the message on success. If an image fails, the app can move it to a separate error queue or update its status in a database.

### Evaluate Azure Service Bus When

1. One event needs to be received independently by **multiple systems** via topic/subscription.
2. You need a **built-in DLQ** to analyze unprocessable messages.
3. You need **sessions** for sequential processing per `orderId` or `accountId`.
4. You need duplicate detection, scheduled messages, or broker transaction capabilities.
5. You want explicit complete/retry/defer/dead-letter control via settlement.
6. The system requires an enterprise messaging model with subscription filters and retention/retry policies.

**Example:** when an order is created, billing, warehouse, and email systems must each receive the event separately. A Service Bus Topic allows three subscriptions so each team can deploy and scale consumers independently while monitoring the DLQ per subscription.

### Decision Tree

~~~mermaid
flowchart TD
  A["Need to send asynchronous work/events"] --> B{"Does one event need multiple independent receiver groups?"}
  B -->|Yes| T["Service Bus Topic + Subscriptions"]
  B -->|No| C{"Need sessions, broker DLQ, duplicate detection, scheduling, or transactions?"}
  C -->|Yes| S["Service Bus Queue"]
  C -->|No| D{"Simple task, app-managed retry/idempotency?"}
  D -->|Yes| Q["Azure Queue Storage"]
  D -->|Unclear| E["Run a PoC: check features, quotas, cost, latency, security"]
~~~

This diagram is an initial selection guide. For specialized requirements involving event routing, streaming, telemetry, or millions of subscribers, you should also compare other services such as **Event Grid** or **Event Hubs**; they do not inherently replace a task queue.

## 7. Queue, Topic, and Subscription: Do Not Confuse Distribution Models

### Queue: One Consumer Group Shares the Work

~~~text
                +--> Worker A
Producer -> Q --+
                +--> Worker B
                +--> Worker C
~~~

A message is typically processed by one consumer at a time via a locking/hiding mechanism. If the consumer fails to finish, the message can be reprocessed. **It is not broadcast** to all of A, B, and C.

### Topic: Multiple Consumer Groups Receive Independently

~~~text
Producer -> Topic -> Subscription billing -> Billing worker pool
                  -> Subscription email   -> Email worker pool
                  -> Subscription audit   -> Audit worker pool
~~~

**Rules/filters** on a subscription allow it to receive messages matching supported conditions. An incorrect filter can prevent events from reaching the intended subscription; test with real event types.

### Manual Fan-Out on Queue Storage

You can implement a producer that sends copies to three different queues, but the producer must then ensure all three sends succeed, retry each destination individually, and avoid partial success. As the number of consumers grows or the organization needs subscription filters, Service Bus Topic is usually easier for governing consistent messaging behavior.

## 8. Delivery Semantics: There Is No Free End-to-End Exactly-Once

Three commonly misunderstood concepts:

- **At-most-once:** a message may be lost if processing fails under an unsafe receive/delete mechanism.
- **At-least-once:** a message is redelivered if unacknowledged; duplicate processing can occur.
- **Exactly-once business effect:** an order or invoice is created only once despite retries; requires business-level idempotency/transactions.

Both Azure Queue Storage with visibility timeout and Service Bus with Peek-Lock require **idempotent consumers**. Even when Service Bus duplicate detection is enabled, the broker only deduplicates repeated sends with the same **MessageId within the detection window**; it does not replace database transactions or prevent duplicates in external systems.

### The Classic Failure Window

1. The consumer receives `order-1024`.
2. The consumer writes the invoice successfully.
3. The process is killed **before** deleting/completing the message.
4. The message is redelivered.
5. If the handler blindly creates a new invoice, a duplicate invoice occurs.

Solution: use a stable business key and a unique constraint, conditional write, or transaction when writing the invoice. Then, a redelivered message simply confirms that the work is already done.

## 9. Queue Storage: Visibility Timeout and Pop Receipt

Example of a Queue Storage consumer:

~~~text
10:00:00  Receive message M, popReceipt R1, invisible 60s
10:00:20  Worker processes
10:00:45  Result written successfully
10:00:46  Delete message M with R1

If worker crashes at 10:00:30:
10:01:00  Message M may become visible again
10:01:01  Another worker receives -> popReceipt R2
~~~

A **pop receipt** is tied to the current valid receive/update operation. If a worker holds an old receipt and tries to delete the message after it has been received again or the receipt has changed, the operation can fail. Therefore, do not write code that attempts to delete with an expired receipt.

### Visibility Timeout Must Be Sufficient, Not Excessive

- Too short: the job is still running, the message reappears, and another worker processes it concurrently.
- Too long: the worker crashes, and the job must wait a long time before retrying.
- Long jobs: break into smaller steps or update message visibility via the appropriate API/SDK, saving the new pop receipt if returned.
- Updating visibility can also fail on timeouts or network drops; the application must safely retry or recover.

Do not use visibility timeout as a **permanent distributed lock**. For operations with side effects, concurrency control in the database or data store is still required.

### Message Ordering

Queue Storage can allow messages to be processed in a different order than they were sent when there are multiple consumers, retries, timeouts, or visibility changes. **Do not design business logic relying on strict FIFO** from a simple queue.

## 10. Service Bus: Peek-Lock, Settlement, and Lock Renewal

With **Peek-Lock**, Service Bus delivers a message to the receiver without removing it from the queue yet. The receiver decides:

| Settlement | Meaning |
|---|---|
| `complete` | Marks processing successful and removes the message from normal delivery |
| `abandon` | Abandons this processing attempt; the message can be redelivered |
| `deadLetter` | Moves the message to the DLQ for separate investigation/handling |
| `defer` | Defers the message using deferred message mechanics; requires appropriate retrieval |

### Lock Timeout

While a message is locked, the receiver must finish the work before the lock expires or **renew the lock** using supported SDK/feature mechanisms. If the lock expires before completion, the receiver may encounter settlement errors and the message may be redelivered.

Example:

~~~text
T0      Receive M with lock
T0+10s  Process and write output
T0+20s  Complete M successfully

If worker stops or lock expires:
        M may be received again afterward
~~~

**Lock renewal is not infinite.** Set deadlines and use checkpoints for long-running work. When using the Service Bus processor SDK, configurable auto-lock renewal is available, but you must understand its limits and error states.

### Receive-and-Delete

Service Bus also provides **Receive-and-Delete** mode, in which the broker treats the message as received/deleted without waiting for `complete`. This mode may suit low-value telemetry where loss is acceptable, but **should not be used for orders, payments, or jobs requiring retries** because a consumer crash after receiving can lose the message.

### Delivery Count and Max Delivery

Service Bus tracks delivery attempts and enforces **max delivery count** per entity settings. When the threshold or related conditions are exceeded, the message can be automatically dead-lettered by supported mechanisms. Do not assume tier/SDK defaults are always appropriate: define retry/dead-letter policies for your workload and verify through testing.

## 11. Poison Messages and Dead-Lettering: A Major Difference

A **poison message** is a message that cannot be processed successfully after reasonable attempts—for example, a JSON payload missing a field, an unsupported schema version, or a referenced record that has been deleted.

### In Queue Storage

Storage Queue **does not have a built-in dead-letter subqueue like Service Bus**. A custom worker can:

1. Read `dequeueCount`.
2. If it exceeds a threshold, record an error entry or move the message to a separate queue, such as `image-jobs-failed`.
3. Log a sanitized failure reason and correlation ID.
4. Delete the original message only after moving it to the error queue succeeds.
5. Maintain an operational runbook to fix and replay failed jobs.

**Azure Functions Queue trigger** uses a poison queue convention such as `<queue-name>-poison` when `maxDequeueCount` is exceeded per the extension; this is behavior of the **Functions trigger extension**, not a default DLQ of the Azure Queue Storage REST API.

### In Service Bus

Service Bus has a **built-in DLQ** per queue or per topic subscription. Messages can enter the DLQ due to policy or when the consumer explicitly calls dead-letter. Operators inspect the DLQ via the appropriate SDK/tools, identify root causes, and decide whether to replay or discard according to retention/policy.

**A DLQ does not fix broken messages by itself.** If you take a message with an invalid schema from the DLQ and send it straight back to the main queue, it will keep failing. Validation, code/schema/dependency fixes, and replay rate limiting are required.

### Error Queue Checklist

- Distinguish transient errors (timeouts, 503) from permanent errors (invalid payload).
- Enforce a **retry limit** and appropriate backoff.
- Record error reason, messageId, operation ID, attempt count, and timestamp.
- Do not log PII or secrets beyond policy.
- Assign an owner and SLA for DLQ/poison queue handling.
- Provide selective, idempotent retry/replay without triggering mass cascading failures.
- Set alerts when DLQ depth or oldest message age increases.

## 12. Service Bus Sessions: Ordering Within a Business Group

A banking system may want operations on the **same account** processed sequentially, while two different accounts still run in parallel. This is a good scenario to **evaluate Service Bus Sessions**.

The producer assigns the same `SessionId` to messages belonging to a group:

~~~text
Account A: A-1 -> A-2 -> A-3   (SessionId="account-A")
Account B: B-1 -> B-2          (SessionId="account-B")
~~~

The Service Bus session receiver uses a session lock to coordinate one consumer processing messages in that session in available order, within the limits of the mechanism and consumer implementation. Different sessions can be processed in parallel.

**Do not interpret sessions as a global guarantee that the entire queue is strict FIFO.** Ordering must be evaluated **within each session**, alongside sending conditions, retries, settlement, deferred messages, transactions, and application concurrency.

### Prerequisites for Use

- The entity must have session support enabled at creation time and be supported by the tier/features.
- The sender sets an appropriate `SessionId`.
- The receiver uses a **session-enabled receiver/processor**, not a standard queue receiver.
- Account for partitioning, session count, and workload skew; an overly hot session can reduce parallelism.
- Do not derive session IDs directly from unvalidated user input without length and format constraints.

### When Are Sessions Unnecessary?

If tasks are completely independent and already idempotent, adding sessions can increase complexity and unnecessarily reduce throughput. Do not use sessions just to "make the queue look more enterprise."

## 13. Duplicate Detection, Scheduled Delivery, and Transactions

### Duplicate Detection

When enabled on a supported Service Bus entity, the broker tracks **MessageId** values for a configured time window. If a producer resends a message with the same ID within that window, the broker can accept the send request while discarding the duplicate per service behavior.

Important limitations:

- Requires a stable producer-managed MessageId.
- Applies only within the **duplicate detection window**, not forever.
- Does not protect against side effects from consumer reprocessing if delivery allows retries.
- Interactions with partition keys, sessions, and transactions must follow tier and entity rules.

For payment or accounting workloads, **database-level idempotency** with unique keys/transactions is still required.

### Scheduled Messages

Service Bus supports scheduling when a message becomes available for delivery in the future via supported APIs. This fits reminders, delayed retries, or simple workflows; it does not replace a general-purpose multi-step workflow scheduler.

With Queue Storage, you can use an initial visibility delay via API capabilities or application-managed scheduling, but do not assume the two services have equivalent scheduling semantics.

### Transactions

Service Bus can group certain messaging operations within a **Service Bus-scoped transaction** subject to tier/API and feature support. For example, a receiver may need to complete an incoming message while sending the next message through the broker in a service-supported atomic unit of work.

**A broker transaction does not automatically include SQL database, Blob Storage, or partner API transactions.** To coordinate database writes and event publishing, consider the **transactional outbox** pattern.

## 14. Transactional Outbox: Avoiding Lost Events After Database Writes

A common architectural bug:

1. The API updates the order in the database successfully.
2. The API attempts to send an `OrderCreated` message.
3. The process crashes between the two steps.
4. The database has the order, but the queue/topic never received the event.

If you reverse the order (send the message first, write to DB later), consumers may receive an event for an uncommitted order or one that gets rolled back.

### Conceptual Solution

~~~mermaid
flowchart LR
  API["Order API"] --> TX["Database transaction"]
  TX --> ORDER["Orders table"]
  TX --> OUT["Outbox table"]
  OUT --> P["Outbox publisher"]
  P --> BUS["Queue Storage / Service Bus"]
  BUS --> C["Idempotent consumer"]
~~~

The same database transaction writes both **business state** and the **outbox event**. A publisher periodically reads unsent outbox rows, sends the message, and marks them as sent. If the publisher crashes after sending but before marking, the message may be sent again; the consumer must still be idempotent.

Outbox is an **application pattern**, not an automatic feature enabled with Queue Storage or Service Bus. It is especially important to consider when messages represent critical business events.

## 15. Payload Design and Versioning

Messages should be small, clear in purpose, and safe to reprocess.

### Suggested Envelope

~~~json
{
  "schemaVersion": 2,
  "messageId": "evt-order-1024-created-v2",
  "eventType": "OrderCreated",
  "correlationId": "request-8b91",
  "subjectId": "order-1024",
  "occurredAt": "2026-11-20T08:15:00Z",
  "payloadRef": "orders/events/order-1024.json"
}
~~~

Recommended fields:

- **messageId:** stable identifier for the message/event, used for deduplication and telemetry.
- **correlationId:** links steps across APIs, producers, and consumers.
- **schemaVersion:** allows producers and consumers to deploy with skewed versions.
- **eventType/jobType:** tells the consumer what kind of work is requested.
- **subjectId/jobId:** business key for idempotency.
- **occurredAt:** event timestamp; do not treat as an absolute synchronized clock.
- **payloadRef:** path to large data in durable storage, omitting SAS/secrets whenever possible.

### Message Size Limits

Both services enforce payload and quota limits; **exact numbers vary by REST/API, tier, and configuration**. In particular, Service Bus Standard and Premium have different capabilities and limits. For large payloads, prefer the **claim-check pattern**: store data in Blob Storage and put only a pointer and checksum in the message; define who has read permissions to the pointer and data retention periods.

### Schema Evolution

Producers should not abruptly remove fields required by older consumers. Add optional fields, version the schema, or deploy consumers that support both formats during a transition period. Messages can sit in a queue for hours or days and later be processed by newer code versions.

## 16. Java SDK: Connecting with Microsoft Entra ID

Two commonly used Azure SDKs for Java:

| Resource | Maven Artifact | Client |
|---|---|---|
| Queue Storage | `com.azure:azure-storage-queue` | `QueueClient`, `QueueServiceClient` |
| Service Bus | `com.azure:azure-messaging-servicebus` | `ServiceBusSenderClient`, `ServiceBusReceiverClient`, processor |
| Credential | `com.azure:azure-identity` | `DefaultAzureCredential` |

Add dependencies with **compatible organization-managed versions**. Example `dependencies` block in Maven (properties must be declared in a parent POM or project):

~~~xml
<dependencies>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-storage-queue</artifactId>
    <version>${azure.storage.queue.version}</version>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-messaging-servicebus</artifactId>
    <version>${azure.messaging.servicebus.version}</version>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
    <version>${azure.identity.version}</version>
  </dependency>
</dependencies>
~~~

This is an illustrative snippet, not a complete POM. Use the Azure SDK BOM or pin versions per your dependency policy to avoid conflicts. `DefaultAzureCredential` can use the Azure CLI identity locally and a managed identity in Azure; **always verify which credential is actually used** to avoid environment permission mix-ups.

### Least-Privilege Data-Plane RBAC

- Queue Storage producer: a role such as **Storage Queue Data Message Sender** at the required scope.
- Queue Storage consumer: a role such as **Storage Queue Data Message Processor** according to needed operations.
- Service Bus producer: **Azure Service Bus Data Sender**.
- Service Bus consumer: **Azure Service Bus Data Receiver**.
- Creating queues or namespaces requires **management-plane permissions**, separate from send/receive permissions.

Custom roles and resources may require broader or narrower permissions. Having `Contributor` on a resource group does not automatically grant permission to send/receive messages via the Entra data-plane unless a data-plane role is assigned.

## 17. Java: Sending and Receiving with Azure Queue Storage

The example below assumes the `image-jobs` queue **already exists**, the Java project has the appropriate SDKs, and the runtime identity has send/receive/delete permissions. The storage address is a placeholder.

### Creating a QueueClient

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.queue.QueueClient;
import com.azure.storage.queue.QueueClientBuilder;

public final class StorageQueueClients {
    private StorageQueueClients() {}

    public static QueueClient connect(String account, String queue) {
        String endpoint = "https://" + account
            + ".queue.core.windows.net/" + queue;

        return new QueueClientBuilder()
            .endpoint(endpoint)
            .credential(new DefaultAzureCredentialBuilder().build())
            .buildClient();
    }
}
~~~

Using `DefaultAzureCredential` avoids embedding account keys in code. For production, verify RBAC and connectivity through firewalls/private endpoints. Do not log credentials or connection strings.

### Producer Sending a Message

~~~java
QueueClient queue = StorageQueueClients.connect(
    "<STORAGE_ACCOUNT>", "image-jobs");

String body = "{\"jobId\":\"job-1024\","
    + "\"blobRef\":\"incoming/image-1024.jpg\"}";

queue.sendMessage(body);
System.out.println("Message submitted");
~~~

The producer above lacks production-grade retries, timeouts, and metrics. If sending fails or times out, **you cannot safely infer the message was not saved**: the broker may have received it while the response to the client was lost. Use a stable job ID and handle duplicates.

### Consumer Receive, Process, Delete

~~~java
import com.azure.storage.queue.QueueClient;
import com.azure.storage.queue.models.QueueMessageItem;

QueueClient queue = StorageQueueClients.connect(
    "<STORAGE_ACCOUNT>", "image-jobs");

for (QueueMessageItem msg : queue.receiveMessages(1)) {
    String jobId = extractAndValidateJobId(
        msg.getBody().toString());

    // Idempotent: only write the result if jobId is not yet completed.
    processSafely(jobId);

    // Delete only after the business result is durably saved.
    queue.deleteMessage(msg.getMessageId(), msg.getPopReceipt());
}
~~~

**The two methods `extractAndValidateJobId` and `processSafely` are application logic you must implement**; this snippet is not a standalone runnable class. If any step fails, do not delete the message. Workers must handle exceptions, timeouts, concurrency, backoff, and poison queues according to policy; never call `deleteMessage` unconditionally in a `finally` block.

If the SDK or encoding mechanism uses Base64 for messages, the consumer must decode according to the producer and SDK convention. Do not assume every message-sending tool uses the same encoding mode.

## 18. Java: Sending and Receiving with Azure Service Bus

The Service Bus SDK uses a fully qualified namespace, such as `orders-bus.servicebus.windows.net`, and provides sender/receiver clients.

### Producer Sending to a Queue

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusMessage;
import com.azure.messaging.servicebus.ServiceBusSenderClient;

public class OrderSender {
    public static void main(String[] args) {
        String namespace = "<NAMESPACE>.servicebus.windows.net";

        try (ServiceBusSenderClient sender =
                new ServiceBusClientBuilder()
                    .credential(namespace,
                        new DefaultAzureCredentialBuilder().build())
                    .sender()
                    .queueName("order-jobs")
                    .buildClient()) {

            ServiceBusMessage message =
                new ServiceBusMessage(
                    "{\"orderId\":\"order-1024\",\"version\":1}");

            message.setMessageId("order-1024-process");
            message.setCorrelationId("request-8b91");
            sender.sendMessage(message);
        }
    }
}
~~~

**Note:** `MessageId` here is a stable key for the job, useful for idempotency. If a producer wants to emit multiple distinct events for the same order, it should generate `MessageId` per **event ID**, rather than reusing the same ID and causing valid events to be dropped when duplicate detection is enabled.

### Consumer Using Peek-Lock and Complete

~~~java
import java.time.Duration;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusReceiveMode;
import com.azure.messaging.servicebus.ServiceBusReceivedMessage;
import com.azure.messaging.servicebus.ServiceBusReceiverClient;

public class OrderReceiver {
    public static void main(String[] args) {
        String namespace = "<NAMESPACE>.servicebus.windows.net";

        try (ServiceBusReceiverClient receiver =
                new ServiceBusClientBuilder()
                    .credential(namespace,
                        new DefaultAzureCredentialBuilder().build())
                    .receiver()
                    .queueName("order-jobs")
                    .receiveMode(ServiceBusReceiveMode.PEEK_LOCK)
                    .buildClient()) {

            for (ServiceBusReceivedMessage msg :
                    receiver.receiveMessages(5, Duration.ofSeconds(10))) {
                try {
                    // TODO: deserialize, validate, use stable idempotency key.
                    processOrderSafely(
                        msg.getBody().toString());
                    receiver.complete(msg);
                } catch (Exception ex) {
                    // TODO: classify permanent vs transient errors.
                    receiver.abandon(msg);
                }
            }
        }
    }
}
~~~

`processOrderSafely` is business logic you must implement. This example illustrates settlement, **not a complete retry policy**. For unrecoverable errors (bad schema, invalid data), consider `deadLetter` via the appropriate API/SDK; for transient errors, you can `abandon` or let the lock expire. Do not process a message longer than the lock duration without renewing or checkpointing.

### Long Tasks and Lock Renewal

With the Service Bus processor API, applications can configure concurrent call limits, auto-complete, auto-lock-renewal, and error handlers according to SDK version. When using a synchronous receiver as shown above, you must proactively plan processing time and lock renewal. **Do not increase concurrency without limits** just to clear a backlog; the downstream database or APIs may become throttled.

## 19. Azure CLI: Creating Lab Resources

Examples use **Azure Cloud Shell (Bash)** or a signed-in CLI. Creating resources and sending messages may incur costs. Run only in an authorized test subscription/resource group; **do not** use production names, regions, or credentials.

### Verify Subscription

~~~bash
az account show \
  --query "{subscription:name,id:id,tenant:tenantId}" \
  -o table
~~~

Declare variables:

~~~bash
RG="rg-messaging-lab"
LOC="southeastasia"
STORAGE="<UNIQUE_STORAGE_ACCOUNT>"
SBNS="<UNIQUE_SERVICEBUS_NAMESPACE>"
~~~

Assume the resource group already exists. For Storage and namespace names, use **realistic, valid, globally unique** names.

### Create Storage Account and Queue

~~~bash
az storage account create \
  --name "$STORAGE" \
  --resource-group "$RG" \
  --location "$LOC" \
  --sku Standard_LRS \
  --kind StorageV2
~~~

If your identity has the appropriate data-plane role:

~~~bash
az storage queue create \
  --name "image-jobs" \
  --account-name "$STORAGE" \
  --auth-mode login
~~~

Creating a queue may require different roles/permissions than just sending messages. If the CLI in your environment does not support `--auth-mode login` for a given command, check `az storage queue create --help` and permitted authentication methods. Do not fall back to printing storage account keys just to work around RBAC issues.

### Create Service Bus Namespace and Queue

~~~bash
az servicebus namespace create \
  --resource-group "$RG" \
  --name "$SBNS" \
  --location "$LOC" \
  --sku Standard

az servicebus queue create \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --name "order-jobs"
~~~

The Standard namespace here illustrates queues and topics; when Premium is needed, check its separate capacity model, pricing, and support conditions. Afterward, configure data-plane permissions so the Java sender/receiver can operate.

### Create Topic and Subscriptions

~~~bash
az servicebus topic create \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --name "order-events"

az servicebus topic subscription create \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --topic-name "order-events" \
  --name "billing"

az servicebus topic subscription create \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --topic-name "order-events" \
  --name "notifications"
~~~

**Do not equate CLI resource creation with runtime delivery.** You must configure sender/receiver identities, permissions, connections, event filters, and retention/retry policies before production use.

### Verify Resources

~~~bash
az storage queue list \
  --account-name "$STORAGE" \
  --auth-mode login \
  -o table

az servicebus queue show \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --name "order-jobs" \
  -o json
~~~

These commands only inspect resource properties, not proof that messages are being processed successfully. Send test messages and observe workers and telemetry.

## 20. Integrating Azure Functions, Container Apps, and AKS

Queues can be consumed by multiple compute options:

| Compute | Suitable Model | What to Verify |
|---|---|---|
| **Azure Functions Queue trigger** | Auto-triggered from Azure Queue Storage | Queue extension, connection, poison queue, concurrency |
| **Azure Functions Service Bus trigger** | Broker message handlers | Lock/retry, DLQ, session support, identity-based settings |
| **Azure Container Apps worker** | Container consumer scaling on queue backlog via appropriate scale rules | Identity, trigger/scaler, max replicas, graceful shutdown |
| **AKS/VMSS workers** | Deeper control over runtime, batching, and networking | Backlog-based autoscaling, SDK reconnect, concurrency, probes |
| **Batch jobs** | Heavy tasks with deadlines/schedules | Checkpointing, partitioning, retry, resource lifecycle |

Azure Functions has separate bindings for Queue Storage and Service Bus. **These bindings do not share the same config, retry, or poison semantics** just because they share naming patterns or a "queue trigger" concept.

### Pipeline Examples

~~~text
HTTP API -> Queue Storage -> Azure Functions resize worker -> Blob Storage
~~~

Suitable when each image is an independent, retryable job without ordering or fan-out needs.

~~~text
HTTP API -> Service Bus Topic -> Billing subscription -> Billing worker
                             -> Email subscription   -> Notification worker
                             -> Audit subscription   -> Audit worker
~~~

Suitable when one event requires multiple business consumers, each with its own DLQ/retry policy and owner.

### Scaling Is Not Just Adding Consumers

If producers send faster than consumers process, the backlog grows. Scaling out replicas too aggressively can also bottleneck the underlying Storage or Database. You need to define:

- Actual worker throughput and cost per job.
- Concurrency limits, prefetch/batching, and lock duration or visibility timeout.
- Downstream API rate limits.
- Number of waiting messages and age of the oldest message.
- Job deadlines/SLOs.
- Scaling capability and quota limits of the hosting plan, namespace, or storage account.

## 21. Security: Identity, RBAC, and Network

### Prefer Microsoft Entra ID

Use **managed identity** in Azure Functions, Container Apps, AKS workload identity, or VMs/VMSS where supported. Grant appropriate send/receive roles and scopes:

- Producers do not need receive/delete permissions if they only send.
- Consumers do not need permissions to create/delete queues or modify namespaces.
- Administrators may need management permissions, but that does not mean applications do.
- Scope roles at the queue, namespace, or storage account level according to the operational role model.

**Shared Access Signature (SAS)** still has valid use cases and service-specific constraints, but requires lifecycle management, key/authorization rule rotation, expiration limits, and keeping tokens out of logs. For new Azure designs, identity-based auth usually reduces the need to distribute long-lived secrets.

### Private Connectivity

- Queue Storage honors Storage account network/firewall rules and private endpoints when enabled.
- Service Bus provides firewall, private connectivity, or network restriction options **depending on tier and deployment type**.
- Verify that DNS resolves to the intended private or public IP, along with routes, NSGs/firewalls, outbound ports, and relevant service endpoints.
- If producers/consumers run on-premises, evaluate VPN/ExpressRoute and private DNS resolvers.
- Do not assume enabling a Private Endpoint automatically disables all public access; inspect the exact configuration and policies.

A `403 Unauthorized` error may be caused by RBAC/SAS or network firewalls depending on the error code and service; a timeout may indicate DNS, routing, or proxy issues. Always collect the **request ID, error code, and context** instead of guessing.

### Payload Security

- Do not allow consumers to deserialize arbitrary types from untrusted sources.
- Validate schemas, payload sizes, field limits, event types, and access rights to referenced data.
- Encrypt sensitive fields when policy requires, beyond platform encryption at rest and in transit.
- Avoid writing full message bodies containing PII into Application Insights or DLQ troubleshooting logs.
- Configure TTL/retention and delete data per compliance requirements.

## 22. Monitoring and Alerting for Queues

A healthy queue system is more than "the queue exists." You must prove messages **are processed successfully within deadlines** and errors are not piling up.

### Minimum Metric Set

| Group | Data to Observe | Meaning |
|---|---|---|
| Queue depth | Waiting/active messages per metric scope | Is the backlog growing? |
| Oldest message age | Age of the oldest unprocessed message (if supported by telemetry) | Are deadlines being breached? |
| Enqueue/dequeue rate | Messages in/out over time | Is the producer faster than the consumer? |
| Success rate | Number of **completed business jobs** | Broker operations do not replace business outcomes |
| Retry/dequeue/delivery count | How many times messages are retried | Transient failures or poison messages? |
| DLQ/poison depth | Quarantined messages | Need manual handling or code fixes? |
| Processing latency | Time from enqueue to completion | End-to-end SLO |
| Exceptions/throttling | Error codes, timeouts, 429/503, lock lost | Service limits or network issues |
| Cost | Broker/storage, operations, transfer, logs, compute | Cost per successful job |

Actual metric names in Azure Monitor differ between **Storage Queue** and **Service Bus Namespace/Queue/Topic/Subscription**. Check metric definitions on the exact resource; do not create alerts on unverified metric names.

### Combining with Application Telemetry

The broker knows to some extent that a message was sent, received, or completed, but it does not know whether **the invoice was generated accurately**, the processed image has the right checksum, or the user received the notification. Therefore, consumers should log:

- Stable `messageId` and `jobId`.
- Correlation ID from the originating request.
- Processing outcome and standardized error codes.
- Attempt count, processing duration, and external dependency status.
- Checkpoint/version for long-running jobs.
- Never log secrets or sensitive payloads.

### Actionable Alerts

1. Queue backlog grows continuously above a defined threshold and duration.
2. Oldest job age exceeds the SLO.
3. DLQ/poison queue receives new messages or grows rapidly.
4. Consumers fail to process messages within the expected window.
5. Unusually high retries, lock losses, or visibility timeouts.
6. Producers experience high send errors or unauthorized responses.
7. Operations/compute costs rise disproportionately relative to completed jobs.

## 23. Costs and Limits to Verify

### Queue Storage

Costs may include:

- Storage capacity for queue data under the Storage pricing model.
- Read/write/list/delete operations and associated requests/transactions.
- Data transfer, private/network connectivity, and configured monitoring.
- Producer/consumer compute: Azure Functions, Container Apps, VMs, or AKS.

A simple queue can be economical, but **excessive polling when the queue is empty** still drives up operations and resource usage. Choose appropriate polling intervals/backoff and leverage triggers/SDK features sensibly.

### Service Bus

Costs vary by tier, operations/message volume, provisioned capacity/resources, features, and region. Premium uses a different resource capacity model than Standard, serving workloads with stricter performance, isolation, or networking requirements per service design.

**Do not simply multiply "number of messages × a fixed unit price"** if the workload uses topics with multiple subscriptions, filters, transactions, forwarding, or Premium capacity. A single message sent to a topic can generate multiple logical deliveries and operations across matching subscriptions.

### Quotas to Check Before Production

- Message and batch sizes by API and SKU/tier.
- Supported number of queues, topics, subscriptions, connections/receivers, and sessions.
- Maximum retention/TTL and queue/entity/namespace size limits.
- Throughput/request rates and network limits.
- Duplicate detection history window.
- Lock duration/renewal, delivery count, and DLQ limits.
- Producer/consumer hosting capacity and scaling limits.
- Availability and private endpoint support for the chosen tier.

### Cost per Successful Outcome

~~~text
Total pipeline cost
  = broker/storage + producer/consumer compute
  + network + monitoring + retries/rework
  + additional operational overhead

Cost per valid completed job
  = Total pipeline cost / number of valid completed jobs
~~~

Compare services using **realistic load scenarios**: polling frequency, subscription counts, retry rates, payload sizes, and deadlines—not just list message prices.

## 24. Scenario A: Batch Image Processing

A website uploads images to Blob Storage and needs thumbnails generated in three sizes. Tasks are independent, retryable, and outputs are named by `imageId` and size variant.

**Suggested Design:**

~~~text
Client -> Upload API -> Blob Storage
                    -> Queue Storage: image-jobs
Queue Storage -> Functions/Container Apps workers
Workers -> thumbnails container
Workers -> job-status store
~~~

Reasons for choosing Queue Storage:

- No broker topics/filters needed.
- Each image is an easily splittable unit of work.
- Outputs can be idempotent by `imageId` and size.
- Workers can retry after visibility timeout.
- Poison messages can be moved to a separate error queue or Functions poison queue.

**Pitfalls:** sending the message before blob upload finishes, embedding long-lived SAS tokens in queue messages, workers finishing work without deleting the message, overly short visibility timeouts, duplicate output files, and lacking backlog alerts.

If multiple independent systems later need notifications when image processing finishes, an appropriate event flow can be added or Service Bus Topic evaluated for the business event step. You do not necessarily have to replace the initial Queue Storage used for thumbnail processing.

## 25. Scenario B: Broadcasting Order Events to Multiple Services

An e-commerce system emits `OrderPlaced`. Three separate systems process it:

- **Billing:** generates invoices; requires idempotency and a DLQ.
- **Fulfillment:** creates warehouse tasks; requires per-order ordering in certain workflows.
- **Notifications:** sends emails; transient failures can retry independently.

**Suggested Design:**

~~~mermaid
flowchart LR
  APP["Order API + transactional outbox"] --> PUB["Outbox publisher"]
  PUB --> TOPIC["Service Bus Topic: order-events"]
  TOPIC --> BILL["Subscription: billing"]
  TOPIC --> FUL["Subscription: fulfillment"]
  TOPIC --> NOTI["Subscription: notifications"]
  BILL --> BW["Billing processor"]
  FUL --> FW["Fulfillment processor"]
  NOTI --> NW["Notification processor"]
  BILL --> DLQ["Billing DLQ for actionable failures"]
~~~

Reasons for choosing Service Bus:

- Topic/subscriptions reduce coupling between the producer and business teams.
- Each subscription can define independent error handling/retention per service capability.
- DLQ supports investigation workflows.
- Sessions can be considered for message groups requiring ordering.
- Duplicate detection can help reduce duplicate sends, **but does not replace Billing idempotency**.

**Pitfalls:** assuming completing a message in billing removes it from notifications, assigning the same session ID to all orders and throttling throughput, using unstable MessageIds, skipping outbox on DB updates, and bulk-replaying the DLQ without fixing the underlying bug.

## 26. Troubleshooting Matrix

| Symptom | Possible Cause | Remediation |
|---|---|---|
| Producer fails to send | RBAC, SAS, DNS/firewall, quota, or oversized payload | Check response code, identity, network, size |
| Queue Storage message processed twice | Visibility timeout expired, worker crashed, delete failed | Idempotency, timeout/renewal, fresh pop receipt |
| Queue Storage message never disappears | Worker did not delete, stale pop receipt | Check logs and delete with valid receipt |
| Queue Storage backlog grows | Too few workers, slow polling, downstream bottleneck | Inspect enqueue/dequeue rates, scale processing carefully |
| Service Bus `MessageLockLost` | Processing too slow, lock expired, connection dropped | Renew lock, shorten processing time, checkpoint |
| Service Bus message moves to DLQ | Max delivery count, TTL/rules, or explicit dead-lettering | Read reason, fix root cause, selectively replay |
| Service Bus consumer receives no messages | Wrong queue/topic/subscription, filter, sessions, or permissions | Verify entity, rule, receiver type, and RBAC |
| Messages for same order out of order | Multiple consumers, retries, no session | Design session key and use session-enabled receiver |
| Duplicate detection does not filter duplicates | Changing MessageId, expired window, or feature disabled | Check entity settings, MessageId, time window |
| Queue has messages but Functions do not trigger | Connection setting, extension, managed identity, or trigger error | Host logs, extension, bindings, role, and queue name |
| HTTP API created order but event is missing | DB committed then publish failed | Transactional outbox, publisher retry |
| Processing latency rises while queue is empty | Slow downstream, SDK retries, or consumer cold starts | App traces, dependency metrics, concurrency |
| Private Endpoint not working | Private DNS/route/NSG/firewall or unsupported tier | Check DNS, network path, policy, resource settings |
| Bill spikes sharply | Empty polling, many subscriptions, retries/logs | Cost Management and operations breakdown |

## 27. Capstone Exercise: Two Architectures for One Requirement

### Problem Statement

An application receives PDF files, extracts content, and sends post-processing notifications. Initially there is one consumer group; six months later, two more independent groups are needed: analytics and compliance.

**Functional Requirements:**

- The API responds quickly after accepting the request.
- PDFs reside in Blob Storage.
- Each task has a stable `jobId`, status, and correlation ID.
- Workers may lose connectivity or restart.
- Schema errors must be classified differently from timeouts.
- Users must be able to query processing results.
- The system enforces security, logging, and cost controls.

### Part A — Initial Design with Queue Storage

1. Diagram the producer, Storage Queue, consumer, and Blob Storage.
2. Define a small message schema containing only the job ID and PDF reference.
3. Choose a visibility timeout based on processing **a single step**, not the total duration of a huge job.
4. Build idempotency: one `jobId` never produces two separate business outcomes.
5. Document the flow when a worker crashes before deleting the message.
6. Choose how to handle poison messages when `dequeueCount` exceeds a threshold.
7. Define metrics for queue depth, oldest job age, successful completions, and retries.
8. Identify the Entra ID permissions needed for producers, consumers, and operators.

### Part B — Design When Fan-Out Is Needed with Service Bus

1. Distinguish how the `DocumentProcessed` event differs from the `ProcessDocument` command.
2. Choose a Queue for command processing and a Topic for events broadcast to multiple departments where appropriate.
3. Diagram Topic `document-events` with subscriptions `analytics`, `compliance`, and `notifications`.
4. Identify where DLQs are used and who owns handling them.
5. Choose appropriate `MessageId`, `correlationId`, `schemaVersion`, and retention values.
6. Evaluate whether sessions or duplicate detection are truly necessary.
7. Describe an outbox if updating document status in a database while publishing an event.
8. Design per-subscription send/receive permissions without sharing full-access connection strings.
9. Compare cost, complexity, and benefits against using three separate Queue Storage queues.
10. Describe rollback steps if a new Service Bus consumer misbehaves.

### Part C — Java / Azure CLI Lab

In a test subscription/resource group with the required SDKs and permissions configured:

1. Create a Storage account and queue `image-jobs` (or a lab-appropriate name).
2. Create a Standard Service Bus namespace and queue `order-jobs`.
3. Create a topic and two subscriptions to test fan-out.
4. Use the Java SDK to send a message to Queue Storage.
5. Receive the message with its pop receipt, simulate processing, and delete on success.
6. Simulate stopping the consumer **before delete** in the lab; observe the message being redelivered.
7. Use the Service Bus Java SDK to send and receive a message in Peek-Lock mode.
8. Succeed with `complete`, and simulate a transient error with `abandon`.
9. Create a safe test error message for the lab and practice the DLQ workflow per policy.
10. Observe logs/metrics and calculate the job success rate.
11. Revoke any test secrets if created, check for cost-incurring resources, and clean up lab resources as approved.

**Note:** never use production queues or topics to test retries or dead-lettering, never send PII or secrets in practice messages, and never delete a resource group containing shared resources.

### Self-Check Questions

**Question 1.** What is the core difference between Azure Queue Storage and Azure Service Bus when a workload has only one consumer group?

**Question 2.** Should a Queue Storage message be deleted immediately upon receipt? When is a pop receipt required?

**Question 3.** What can happen if the visibility timeout expires while a worker is still processing?

**Question 4.** How do Service Bus `complete`, `abandon`, `deadLetter`, and `defer` differ?

**Question 5.** Why does a Service Bus Topic require Subscriptions for multiple systems to receive the same event?

**Question 6.** For an order workflow, why might sessions be useful without being needed for the entire message queue?

**Question 7.** Does broker duplicate detection replace database unique constraints and idempotency?

**Question 8.** Does Queue Storage have a built-in DLQ like Service Bus? Which layer owns the Azure Functions Queue trigger poison queue?

**Question 9.** If a DB commit succeeds and the producer crashes before sending the event, what pattern should be evaluated?

**Question 10.** Why is it necessary to measure oldest message age and business completions rather than only queue depth?

**Question 11.** Does a managed identity granted Blob read permissions automatically have permission to send messages to Service Bus or Queue Storage?

**Question 12.** How should large messages be designed, and why shouldn't the entire file be placed inside the message body?

**Question 13.** What are the benefits and costs of migrating from one Queue Storage queue to a Service Bus Topic with multiple subscriptions?

**Question 14.** For a payment workload, should you choose Receive-and-Delete or Peek-Lock? Why?

**Completion Criteria:** the learner can explain messaging fundamentals, choose between Queue Storage and Service Bus based on features and constraints, design idempotency and poison/DLQ handling, implement safe send/receive in Java, and evaluate security, operations, and cost for both options.

## Conclusion

**Azure Queue Storage** is well suited for **simple task queues** where multiple workers process independent jobs, integrate easily with Azure Storage, and manage idempotency and poison handling in application code. **Azure Service Bus** is worth considering when an application needs an **advanced message broker**: topics/subscriptions, built-in dead-lettering, sessions, duplicate detection, scheduling, lock/settlement control, or transaction operations within supported scopes.

Whichever service you choose, messages can be retried, consumers can crash right after writing results, payloads can be malformed, and backlogs can grow when downstream dependencies slow down. Resilient design requires **stable message IDs, schema-defined payloads, idempotent processing, bounded retries/backoff, dead-letter/poison runbooks, Entra ID/RBAC, network security, job-level telemetry, and cost control**. Evaluating both services against those criteria—rather than product names alone—will help you build Azure systems that scale cleanly and operate reliably.
