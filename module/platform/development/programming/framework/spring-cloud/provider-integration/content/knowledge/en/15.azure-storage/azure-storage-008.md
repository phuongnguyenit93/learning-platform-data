# Sending and Receiving Azure Storage Queue Messages and Limits Compared to Azure Service Bus

## 1. Context and Objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, we practice integrating Spring Boot with managed services from AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries. The module covers identity and permission configuration, storage/messaging/data access, secret protection, integration testing, and evaluating differences across cloud providers. This lesson belongs to the **Azure Storage** chapter and focuses on **Azure Queue Storage** and the question: when is a simple storage queue sufficient, and when should you choose **Azure Service Bus**?

Running example: an API accepts PDF resumes, stores the file in Azure Blob Storage, and sends a message for an OCR worker to process. The API needs to dispatch the job quickly without waiting for OCR to finish; workers can pause, restart, or scale out to multiple instances. The system must handle a worker receiving the same message twice, processing longer than the visibility timeout, and failing repeatedly.

After this lesson, you will be able to:

- Explain the producer/consumer model and send, receive, and delete message operations in Azure Queue Storage.
- Understand **visibility timeout**, **pop receipt**, **dequeue count**, TTL, and why messages can be redelivered.
- Integrate Queue Storage with Spring Boot via Spring Cloud Azure and the Azure Storage Queue SDK for Java.
- Design idempotent consumers, bounded retries, and poison queues.
- Compare Queue Storage with Service Bus on ordering, topics/subscriptions, sessions, dead-lettering, transactions, and message limits.
- Choose the right service based on business semantics, operational requirements, and total cost.

## 2. How Does Azure Queue Storage Work?

**Azure Queue Storage** is a service for storing messages in a simple queue model. Producers send messages to a queue; consumers receive messages, process them, and delete them once done.

~~~mermaid
flowchart LR
    API[Spring Boot API / Producer] -->|sendMessage| Q[(Azure Storage Queue)]
    Q -->|receiveMessages| W1[Worker A]
    Q -->|receiveMessages| W2[Worker B]
    W1 -->|deleteMessage after success| Q
    W2 -->|deleteMessage after success| Q
~~~

Components:

- **Storage account:** the Azure resource containing the Queue service.
- **Queue:** a named queue, e.g., `document-jobs`.
- **Message:** job payload, typically small JSON holding a job ID and a reference to data.
- **Producer:** the component creating messages via enqueue operations.
- **Consumer/worker:** the component receiving, processing, and deleting messages.

Queue Storage fits a **work queue**: multiple workers concurrently pull different jobs from one queue. The service decouples job submission time from processing time, though it does not itself manage business job state in a database.

### 2.1. Why Doesn't a Message Disappear Immediately When a Consumer Receives It?

When a consumer receives a message, Azure Queue Storage temporarily **hides the message for a duration** called the visibility timeout. During that window, other consumers will not receive that message via standard receive operations. The first consumer must process and delete the message using its current **message ID and pop receipt**.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant Q as Storage Queue
    participant W as Worker
    P->>Q: Enqueue message
    W->>Q: Receive message
    Q-->>W: Message + messageId + popReceipt
    Note over Q: Message temporarily invisible
    W->>W: Process job
    W->>Q: Delete using messageId + popReceipt
    Q-->>W: Delete succeeded
~~~

If the worker crashes, the timeout expires, or the worker fails to delete the message, the message can reappear for another consumer to pick up. This mechanism enables failure recovery, but also means **the same job can be delivered multiple times**.

## 3. Concepts You Must Understand Before Writing a Consumer

| Concept | Meaning | What the Consumer Must Do |
|---|---|---|
| **Message ID** | Service-assigned identifier for a message | Pass when deleting or updating a message |
| **Pop receipt** | Token representing the current receive/update lease | Pair with message ID; older receipts may no longer be valid |
| **Visibility timeout** | Duration a message stays hidden after receipt | Ensure it is long enough for processing, or renew as needed |
| **Dequeue count** | Number of times the message has been received from the queue | Track retries and detect persistently failing messages |
| **TTL (time to live)** | How long a message may stay in the queue | Set a lifetime matching job SLAs |
| **Approximate message count** | Estimated number of messages in the queue | Monitor backlog, never use as an exact transactional figure |

### 3.1. Visibility Timeout Is Not a Hard Maximum Processing Limit

Suppose a worker receives a message with a 60-second visibility timeout:

- If processing finishes in 20 seconds and deletion succeeds, the message disappears from the queue.
- If processing runs longer than 60 seconds without renewing visibility, the message can become visible again and another worker may pick it up.
- If processing finishes but the delete call fails due to a network error or stale pop receipt, the message can be redelivered.

For long-running jobs, consumers can **update the message to extend its visibility timeout** and must retain the new pop receipt returned. Design a heartbeat or bounded renewal mechanism—avoid renewing indefinitely when a worker is hung.

### 3.2. Pop Receipt Changes Across Receives

Each receive or message update can issue a **new pop receipt**. When deleting, you must use the most recent valid receipt:

~~~text
Receive 1: messageId = M42, popReceipt = R1
    Worker processing exceeds visibility timeout.

Receive 2: messageId = M42, popReceipt = R2
    R2 is the current receipt; R1 is stale.

Delete(M42, R1) -> may fail.
Delete(M42, R2) -> matches the current receive.
~~~

Do not persist pop receipts as long-lived business keys; they are protocol details of a single receive attempt. If a worker needs to resume after a restart, persist the **job ID and business state**, then receive messages via the queue mechanism.

### 3.3. TTL and Message Size

Azure Queue Storage caps message size at **64 KiB**. If a producer Base64-encodes payloads, the raw data must be smaller because Base64 adds overhead. Validate the limit against the **post-encoding message** and keep producer and consumer encoding settings consistent.

TTL controls how long a message can remain in the queue. Choose a lifetime appropriate for the job type; expiring messages are not a long-term storage mechanism. Azure Queue Storage offers API versions supporting non-expiring messages, but verify service/SDK version compatibility and operational policies before relying on it. For jobs requiring audit history, persist state in a database or appropriate storage.

**Do not put PDFs, videos, or large JSON inside queue messages.** Store payloads in Blob Storage and send references such as `documentId`, `blobName`, and `jobId`. A queue is a job-coordination channel, not a bulk payload store.

## 4. Message Structure and Producer Design

A message should carry enough information for the consumer to locate data and verify state without embedding full file contents.

Example payload:

~~~json
{
  "jobId": "ocr-42",
  "documentId": "doc-2026-0042",
  "blobName": "incoming/2026/doc-2026-0042.pdf",
  "operation": "OCR",
  "schemaVersion": 1,
  "createdAt": "2026-11-24T09:30:00Z"
}
~~~

Fields and their purposes:

- `jobId`: stable identifier for a business processing run; supports idempotency and auditing.
- `documentId`: document key in the database, used to verify owner/tenant and state.
- `blobName`: object reference inside the container; not an access permission.
- `operation`: type of task the consumer should perform.
- `schemaVersion`: enables evolving the message format without breaking older consumers.
- `createdAt`: job creation timestamp for measuring queue wait times and SLAs.

### 4.1. Maven and application.yml Configuration

Declare a Spring Cloud Azure BOM compatible with your project's Spring Boot version and the Queue Storage starter:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-queue</artifactId>
    </dependency>
</dependencies>
~~~

In `application.yml`:

~~~yaml
spring:
  cloud:
    azure:
      storage:
        queue:
          account-name: ${AZURE_STORAGE_ACCOUNT_NAME}

app:
  queue:
    document-jobs: ${DOCUMENT_JOBS_QUEUE:document-jobs}
~~~

`spring-cloud-azure.version` must follow your project's Spring Boot/Spring Cloud Azure compatibility matrix. The example assumes the `document-jobs` queue is pre-provisioned; runtime apps need no subscription admin rights to create storage accounts.

For credentials, prefer **Microsoft Entra ID and managed identity** when running on Azure. Local developers can use Azure CLI login per organizational policy. Never commit account keys, connection strings, or SAS tokens to Git.

### 4.2. Producer Using QueueServiceClient

The Spring Cloud Azure Storage Queue starter can auto-configure Azure Queue clients for injection into Spring beans. Example using `QueueServiceClient`:

~~~java
import com.azure.storage.queue.QueueClient;
import com.azure.storage.queue.QueueServiceClient;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class DocumentJobProducer {
    private final QueueClient queue;
    private final ObjectMapper objectMapper;

    public DocumentJobProducer(
            QueueServiceClient queueServiceClient,
            ObjectMapper objectMapper,
            @Value("${app.queue.document-jobs}") String queueName) {
        this.queue = queueServiceClient.getQueueClient(queueName);
        this.objectMapper = objectMapper;
    }

    public void enqueue(DocumentJob job) {
        try {
            String json = objectMapper.writeValueAsString(job);
            queue.sendMessage(json);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException(
                    "Unable to serialize document job", ex);
        }
    }
}
~~~

`DocumentJob` is an application DTO, for example:

~~~java
import java.time.Instant;

public record DocumentJob(
        String jobId,
        String documentId,
        String blobName,
        String operation,
        int schemaVersion,
        Instant createdAt) {
}
~~~

`getQueueClient(queueName)` creates a handle referencing the queue; it does not create the queue on Azure. Provision queues via IaC or migrations. For test environments, the SDK offers `createIfNotExists()`, which should not run on every production request.

### 4.3. Blob + Queue: Common Integration Pattern

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Spring Boot API
    participant B as Blob Storage
    participant D as Database
    participant Q as Storage Queue
    participant W as OCR Worker
    C->>A: Upload PDF
    A->>B: Store blob
    A->>D: Create PENDING document/job
    A->>Q: Enqueue jobId + blobName
    A-->>C: 202 Accepted
    Q-->>W: Worker receives job
    W->>B: Read PDF
    W->>D: Save OCR result / COMPLETED
    W->>Q: Delete message
~~~

Blob and Queue do not share a transaction. If Blob upload succeeds but Queue send fails, an unprocessed document can remain. If DB commit succeeds but enqueue fails, business state can get stuck. For critical flows, use a **transactional outbox** in the database, controlled retries, or a reconciliation job instead of assuming all three steps always succeed together.

## 5. Consumer: Receiving, Processing, and Deleting Messages

### 5.1. Basic Consumer

The consumer deletes a message **only after business work is complete and results are durably saved**:

~~~java
import com.azure.storage.queue.QueueClient;
import com.azure.storage.queue.QueueServiceClient;
import com.azure.storage.queue.models.QueueMessageItem;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class DocumentJobConsumer {
    private final QueueClient queue;
    private final ObjectMapper objectMapper;
    private final DocumentProcessor processor;

    public DocumentJobConsumer(
            QueueServiceClient queueServiceClient,
            ObjectMapper objectMapper,
            DocumentProcessor processor,
            @Value("${app.queue.document-jobs}") String queueName) {
        this.queue = queueServiceClient.getQueueClient(queueName);
        this.objectMapper = objectMapper;
        this.processor = processor;
    }

    public void pollOnce() {
        for (QueueMessageItem message : queue.receiveMessages(5)) {
            try {
                DocumentJob job = objectMapper.readValue(
                        message.getMessageText(), DocumentJob.class);

                processor.processIdempotently(job);

                queue.deleteMessage(
                        message.getMessageId(),
                        message.getPopReceipt());
            } catch (Exception ex) {
                // Do not delete the message when processing fails.
                // After the visibility timeout, the message may be redelivered.
                // Log job/message ID and error code, never sensitive data.
            }
        }
    }
}
~~~

This is a single-poll method; a scheduler or worker lifecycle must invoke it on an appropriate cadence or use application-managed polling. `receiveMessages(5)` uses the API/SDK default visibility timeout; for long-running tasks, pick an overload accepting an explicit timeout and implement message renewal. Never run a tight unbounded poll loop that spikes CPU when the queue is empty.

`DocumentProcessor.processIdempotently` is the business logic you must implement. Deletion alone cannot guarantee exactly-once execution; a worker can crash right after saving results and before deleting the message.

### 5.2. Processing Order Matters

1. Receive message and extract `messageId`, `popReceipt`, and `dequeueCount`.
2. Parse/validate schema and inspect `jobId`.
3. Claim the job in the database using a unique key/optimistic update to prevent duplicate execution.
4. Process data from Blob; persist results durably.
5. Mark the job `COMPLETED`.
6. Delete the message using the **latest pop receipt**.

Deleting the message before saving results risks losing the job if the worker crashes right after deletion. Saving results before deleting means a crash causes redelivery—hence the processor must be idempotent.

### 5.3. Renewing Visibility for Long-Running Work

If a task may exceed the visibility timeout, the consumer must update the message to push back when it becomes visible again. After updating, use the **new pop receipt** returned for the next delete/update:

~~~text
Receive(message, visibility = 60s) -> popReceipt R1
    45s elapsed, still running
UpdateMessage(messageId, R1, visibility = 60s)
    -> popReceipt R2
    Continue processing
DeleteMessage(messageId, R2)
~~~

Do not renew indefinitely. If a job exceeds its SLA or a worker stops heartbeating, allow the message to reappear, record the attempt, and route to failure handling. For multi-hour jobs, consider splitting into smaller steps or using a workflow engine/Service Bus.

## 6. Delivery Semantics: Why Idempotency Is Essential

Azure Queue Storage can redeliver messages. For example:

1. A worker completes processing and saves OCR results to the database.
2. The worker loses connectivity before deleting the message.
3. The visibility timeout expires; the message becomes receivable again.
4. Another worker processes the same job a second time.

This is why consumers must be designed for **at-least-once processing** with **idempotent handlers**. Never promise exactly-once execution based solely on the queue.

### 6.1. Job State Table

| State | Meaning | Action |
|---|---|---|
| PENDING | Request recorded, awaiting worker | Eligible to be claimed for processing |
| PROCESSING | Currently handled by a worker | Record worker ID/business lease and heartbeat timestamp |
| COMPLETED | Result durably stored | If redelivered, skip side effects and delete message |
| FAILED_RETRYABLE | Transient failure | Allow retry per policy |
| FAILED_FINAL | Unrecoverable automatic failure | Move to poison queue or require intervention |

### 6.2. Idempotency via Unique Keys

For example, a database table `processed_jobs` with a unique constraint on `job_id`:

~~~sql
CREATE TABLE processed_jobs (
    job_id        VARCHAR(100) PRIMARY KEY,
    document_id   VARCHAR(100) NOT NULL,
    status        VARCHAR(30) NOT NULL,
    result_ref    VARCHAR(500),
    completed_at  TIMESTAMP
);
~~~

Processing flow:

- Worker attempts to insert/claim a record by `jobId` inside a transaction.
- If the job is already `COMPLETED`, the worker skips side effects and simply deletes the message.
- If the job is `PROCESSING` under another worker, apply claim/timeout logic so two workers don't run concurrently.
- Upon completion, persist the result and `COMPLETED` status in the appropriate transaction.

A unique key prevents duplicate job rows, yet **does not automatically make external side effects idempotent**. Calls to payment APIs, email senders, or Blob writes still need idempotency keys or target-state checks.

### 6.3. Handling Poison Messages

A **poison message** is one that fails repeatedly due to malformed payloads, missing data, incompatible schemas, or unrecoverable business errors.

Azure Queue Storage has no built-in dead-letter queue like Service Bus. Applications typically create a dedicated queue, e.g., `document-jobs-poison`:

~~~mermaid
flowchart TD
    Q[(document-jobs)] --> W[Worker]
    W --> S{Processing succeeded?}
    S -->|Yes| D[Delete original message]
    S -->|Transient error| R[Let message reappear / retry]
    R --> Q
    S -->|Exceeded dequeue count threshold| P[(document-jobs-poison)]
    P --> O[Alert + investigate + controlled replay]
~~~

Safe poison-routing workflow:

1. Read `dequeueCount` and evaluate against the retry threshold.
2. Write the original message along with error details, timestamp, and correlation ID to the poison queue or error store.
3. **Delete the original message only after** the poison write succeeds.
4. Emit alerts and provide a controlled replay tool after fixing root causes.

If writing to the poison queue fails, leave the original message intact so it retries after visibility timeout. Avoid copying sensitive data or full file contents into logs/poison messages unnecessarily.

## 7. Spring Cloud Azure and Azure Storage Queue SDK

### 7.1. Auto-Configuration and Credentials

The `spring-cloud-azure-starter-storage-queue` starter integrates Spring Boot with Azure Queue Storage. When the starter and configuration are valid, the app can inject an auto-configured `QueueServiceClient`:

~~~java
import com.azure.storage.queue.QueueServiceClient;
import org.springframework.stereotype.Component;

@Component
public class QueueClientHolder {
    private final QueueServiceClient client;

    public QueueClientHolder(QueueServiceClient client) {
        this.client = client;
    }
}
~~~

`QueueServiceClient` represents the Queue service in a storage account; `QueueClient` represents one specific queue. SDK clients are reusable across requests—do not recreate them per message.

### 7.2. Azure Identity and RBAC

When running on Azure, prefer **managed identity**. Common data-plane roles:

| Producer/Consumer Role | Role to Consider |
|---|---|
| Send-only producer | **Storage Queue Data Message Sender** |
| Receive and process messages | **Storage Queue Data Message Processor** |
| Broad Queue data read/write operations | **Storage Queue Data Contributor** |
| Queue/resource administration | Appropriate management role, scoped separately to infra pipelines |

Assign roles to the **managed identity principal** at the appropriate storage account/queue scope. Azure Resource Manager resource-management permissions do not automatically grant Queue data send/receive permissions. If local developer runs work yet production gets 403, verify the workload's effective identity and assigned data-plane roles.

### 7.3. Queue Naming and Provisioning

Queue names must follow Azure Queue Storage rules: lowercase letters, digits, and hyphens, starting with a letter/digit and within valid length (typically **3–63 characters**), e.g., `document-jobs`, `invoice-events`.

Provision queues via IaC or controlled migrations. In tests, `createIfNotExists()` is convenient; in production runtime, grant only the permissions required for sending/receiving. If a queue does not exist, SDK calls return resource-not-found errors on send/receive.

## 8. Azure Queue Storage vs. Azure Service Bus

Both services provide queues, yet serve **different levels of messaging complexity**. Queue Storage is part of Azure Storage; Service Bus is a dedicated message broker with richer enterprise semantics.

| Criterion | Azure Queue Storage | Azure Service Bus |
|---|---|---|
| Goal | Simple work queue storing messages in Storage | Enterprise messaging, service decoupling with rich semantics |
| API/protocol | Azure Storage Queue REST/SDK over HTTPS | AMQP 1.0 and supported protocols/APIs |
| Message size | Max **64 KiB** | Significantly larger, tier/protocol-dependent; verify current limits |
| Queue model | Single queue, competing consumers | Queues, Topics, and Subscriptions |
| Publish/subscribe | No native topic/subscription | Topics broadcast messages to multiple subscriptions |
| Ordering | No strict FIFO guarantee | Sessions support ordered processing within a session when configured |
| Duplicate detection | App implements idempotency/deduplication | Built-in MessageId duplicate detection within a window; not end-to-end exactly-once |
| Dead-letter | DIY poison queue/error store | Built-in dead-letter queue |
| Lock/visibility | Visibility timeout and pop receipt | Peek-Lock, lock duration, renew lock, complete/abandon/dead-letter |
| Transactions | No multi-operation messaging transactions like Service Bus | Supports transactions across service-permitted operations |
| Scheduled/deferred messages | No comparable rich feature set | Supports scheduled and deferred messages |
| Sessions/grouping | No session semantics | Sessions group messages and enforce sequential per-session processing |
| Filtering/routing | App routes manually or uses separate queues | Topic subscription filters/rules |
| Operations | Simple, lives inside Storage account | Dedicated broker requiring namespace/tier configuration and monitoring |

### 8.1. When Does Queue Storage Fit?

Choose Queue Storage if:

- You only need **a single work queue** for producers and competing workers.
- Payloads are small, mostly carrying IDs/Blob references.
- You do not need FIFO/sessions, topics/subscriptions, or messaging transactions.
- The app already uses Azure Storage and prefers a simpler operational footprint.
- You can implement idempotency, retries, and a poison queue at the application layer.

Example: after uploading an image, enqueue a thumbnail job; multiple workers process independent images while the database tracks job state.

### 8.2. When Does Service Bus Fit?

Choose Service Bus when requirements include one or more of:

- One event must fan out to **multiple independent subscribers** via Topics/Subscriptions.
- **Sessions** are needed to process messages sequentially per group/aggregate, e.g., all commands for one order.
- A built-in **dead-letter queue**, scheduled/deferred messages, or messaging transactions are required.
- MessageId duplicate detection or rich correlation/filtering/routing is needed.
- A dedicated broker is needed to coordinate communication across multiple business systems.

Example: an `OrderPlaced` event must reach billing, fulfillment, and notifications, each with its own subscription, retry policy, and DLQ. A single Storage Queue cannot fan out one message to all three consumers natively.

### 8.3. Duplicate Detection Is Not Exactly-Once

Service Bus can discard duplicate messages by MessageId within a configured duplicate-detection window. That reduces producer-retry duplicates, yet does not turn the whole workflow into exactly-once:

- Consumers can still receive redeliveries when locks expire or processing fails.
- External side effects outside the broker still require idempotency.
- Duplicate detection applies only within configured windows and service semantics.

With either service, design consumers to be safe under redelivery.

## 9. Example Sending and Receiving with the Azure Service Bus SDK

To illustrate the code difference, Service Bus uses dedicated sender/receiver clients. Add the `spring-cloud-azure-starter-servicebus` starter for Spring Cloud Azure integration, or use the Azure Service Bus SDK directly for explicit client control.

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusSenderClient;
import com.azure.messaging.servicebus.ServiceBusMessage;

String namespace = System.getenv("AZURE_SERVICEBUS_NAMESPACE");
TokenCredential credential =
        new DefaultAzureCredentialBuilder().build();

ServiceBusSenderClient sender = new ServiceBusClientBuilder()
        .credential(namespace, credential)
        .sender()
        .queueName("document-jobs")
        .buildClient();

sender.sendMessage(new ServiceBusMessage(
        "{\"jobId\":\"ocr-42\",\"documentId\":\"doc-42\"}"));
~~~

This sends a message to a **Service Bus queue**, not a Storage Queue. The namespace typically looks like `<namespace>.servicebus.windows.net`; the identity needs the appropriate Service Bus data-plane role, e.g., **Azure Service Bus Data Sender**. Close sender clients on application shutdown (e.g., managed Spring bean lifecycle) rather than creating/closing per request.

With a Service Bus receiver in **Peek-Lock** mode, consumers receive messages and invoke:

~~~java
// Pseudocode illustrating processing flow; receiver is ServiceBusReceiverClient.
for (var message : receiver.receiveMessages(10)) {
    try {
        processIdempotently(message.getBody());
        receiver.complete(message);
    } catch (Exception ex) {
        receiver.abandon(message);
    }
}
~~~

`complete` acknowledges processing and removes the message from the queue/subscription. `abandon` releases the lock so the message can be redelivered. Messages can also be dead-lettered on unrecoverable errors. In real code, pick body-type overloads and manage receiver/processor lifecycles properly; the pseudocode highlights **Peek-Lock/complete/abandon** compared to Queue Storage's **visibility timeout/pop receipt/delete**.

## 10. Integration Testing

### 10.1. Azurite for Queue Storage

**Azurite** emulates Azure Queue Storage for testing basic local send/receive logic. It does not fully emulate managed identity/RBAC, firewalls/private endpoints, scale, throttling, or all production Azure behaviors. Testing data-plane permissions and networking requires a dedicated integration-test Azure storage account.

Never use production account keys in test fixtures. Isolate test queues by run/job ID and clean up messages/queues according to the test lifecycle.

### 10.2. Storage Queue Test Matrix

| Test Case | Expected Verification |
|---|---|
| Producer sends JSON job | Queue receives exact payload and schemaVersion |
| Consumer receives and succeeds | Result persisted durably and message deleted using current pop receipt |
| Worker crashes before delete | Message reappears after visibility timeout |
| Long-running worker | Visibility is properly renewed; new receipt is used |
| Same jobId sent twice | Processor produces no duplicate side effects |
| Malformed schema payload | Bounded retries or routed to poison queue |
| Poison queue write fails | Original message retained for retry |
| Empty queue | Polling avoids busy loops/CPU spikes |
| Missing RBAC | 403 diagnosed by principal and scope |
| Message exceeds 64 KiB | Producer rejects or offloads large payload to Blob |
| TTL expires | Message is no longer treated as pending work |
| Multiple competing workers | No FIFO assumed; job state updated safely |

### 10.3. Testing Against Real Service Bus

Azurite does not emulate Azure Service Bus. If choosing Service Bus, use a dedicated test namespace to verify:

- Peek-Lock, complete, abandon, lock renewal, and lock expiry.
- Dead-letter queue and message replay.
- Sessions, ordering within a session, and concurrency across sessions.
- MessageId duplicate detection.
- Topics/Subscriptions, filters/rules, and fan-out.
- Messaging transactions within service-supported operations.

Testing each service directly avoids building overly broad abstractions that inadvertently hide critical broker semantics.

## 11. Common Errors and Diagnostics

| Symptom | Possible Cause | Remediation |
|---|---|---|
| HTTP 403 on send/receive | Managed identity lacks Queue Data role or storage firewall blocks | Verify principal, role/scope, endpoint, and network |
| HTTP 404 | Queue not provisioned or wrong name/account | Verify queue name, storage account, and environment |
| Message reappears | Worker failed to delete, visibility timeout too short, or stale pop receipt used | Check processing duration, visibility updates, and latest receipt |
| Message processed twice | At-least-once delivery, producer retry, or worker crash post-commit | Use jobId/unique keys and idempotent processors |
| Queue backlog grows | Insufficient worker capacity, slow processing, or looping failing messages | Monitor approximate count, latency, dequeue count, and scale workers |
| Message vanishes before processing | TTL expired or consumer deleted too early | Review TTL and delete only after durable persistence |
| Queue message too large | Large payload/file stuffed into message | Store payload in Blob and send a reference |
| Poison queue loses messages | Original deleted before poison enqueue succeeded | Persist poison message before deleting original |
| Expected FIFO missing | Queue Storage does not guarantee strict ordering | Use Service Bus Sessions if per-group ordering is required |
| Need one message delivered to multiple systems | Single queue uses competing consumers, not pub/sub | Choose Service Bus Topics/Subscriptions or another fan-out design |

## 12. Security and Operations

### 12.1. Identity and Least Privilege

- Send-only producers: consider **Storage Queue Data Message Sender**.
- Message-processing consumers: consider **Storage Queue Data Message Processor**.
- Use **Storage Queue Data Contributor** only when a workload needs broader operations without a narrower role fit.
- Assign roles to managed identities at the appropriate storage account/queue scope; management-plane permissions do not grant data-plane access.
- Never put account keys, connection strings, or SAS tokens in source code, logs, or messages.

### 12.2. Messages Are Not Secret Stores

Never put passwords, access tokens, long-lived SAS URLs, or sensitive content inside queue messages unnecessarily. Queue messages can be read by any authorized principal, land in poison queues/logs, and persist until TTL expiry. When a message must point to a private document, send the blob name/document ID; let the worker use its managed identity with Blob read access.

### 12.3. Observability and Scaling

Monitor:

- Approximate message count/backlog and age of the oldest message (apps can compute from `createdAt`).
- Receive/delete counts, dequeue counts, and poison-routing rate.
- Per-job processing duration, remaining visibility time, and renewal counts.
- Active worker counts, 403/404/429/5xx errors, latency, and throughput.
- PENDING/PROCESSING jobs exceeding SLAs in the database.

Scale workers based on backlog and processing duration while capping concurrency to avoid overwhelming Blob Storage, databases, or OCR services. Never use approximate message count as the sole basis for financial or transactional decisions.

## 13. Decision Tree: Queue Storage vs. Service Bus

~~~mermaid
flowchart TD
    A[App needs async work dispatch] --> B{Payload exceeds queue limit?}
    B -->|Yes| C[Store payload in Blob, send reference only]
    B -->|No| D{Need topic/subscription fan-out?}
    C --> D
    D -->|Yes| SB[Azure Service Bus]
    D -->|No| E{Need sessions, built-in DLQ, transactions, or scheduled/deferred?}
    E -->|Yes| SB
    E -->|No| F{Is a simple work queue enough?}
    F -->|Yes| Q[Azure Queue Storage]
    F -->|No| SB
~~~

This serves as an initial guide, not a substitute for evaluating load, cost, SLAs, and operability. When new requirements emerge such as per-aggregate ordering, built-in DLQ, or multi-subscriber fan-out, re-evaluate Service Bus before layering custom broker mechanics on top of Storage Queue.

## 14. Practice Scenarios and Self-Check Questions

**Scenario A — Document OCR:** The API uploads PDFs to Blob and sends jobs to Queue Storage. Workers take 2 minutes while visibility timeout is only 30 seconds. Explain why messages can be redelivered, how to extend visibility, and how to protect results with idempotency.

**Scenario B — Duplicate message sends:** A producer times out after sending, unsure whether Azure received it, and retries the same job. Use a stable job ID and a database unique constraint to avoid producing two OCR results.

**Scenario C — Poison messages:** Schema-invalid JSON fails repeatedly. Design a dequeue count threshold, poison queue, alerting, and replay workflow; explain why poison persistence must succeed before deleting the original message.

**Scenario D — Fan-out:** A contract event must reach billing, audit, and notifications independently. Choose Service Bus Topics/Subscriptions and explain why three competing consumers on one Storage Queue fail this requirement.

**Scenario E — Per-order sequential processing:** Every message for the same order must run sequentially, while distinct orders run in parallel. Evaluate Service Bus Sessions and compare against Queue Storage lacking session semantics.

**Scenario F — Multi-cloud selection:** Compare Azure Queue Storage against Amazon SQS and Google Cloud Pub/Sub on delivery, visibility/acknowledgement, retries/dead-lettering, ordering, and fan-out. Never assume identical API names or message limits across providers.

### Self-Check Questions

1. **Why doesn't receive delete a message immediately?** Because the message stays hidden during the visibility timeout while the consumer processes it; the consumer deletes it only after finishing.
2. **What is the pop receipt used for?** Confirming that a delete/update targets the current receive attempt; older receipts may be invalid.
3. **Does Queue Storage guarantee exactly-once processing?** No; messages can be redelivered, so consumers must be idempotent.
4. **When is a poison queue needed?** When messages fail repeatedly or cannot be processed automatically and must be isolated for investigation.
5. **Why shouldn't PDFs be sent directly inside a queue?** The 64 KiB message limit; Blob is built for large payloads.
6. **Does Queue Storage have topics/subscriptions?** Not natively like Service Bus; multiple consumers on one queue compete for messages.
7. **What do Service Bus Sessions solve?** Grouping messages by session and processing sequentially within a session when configured.
8. **Does Service Bus duplicate detection replace idempotency?** No; it reduces duplicate sends within a configured window, while consumers still must handle redeliveries safely.
9. **Can Azurite test Service Bus?** No; a dedicated integration-test Azure Service Bus namespace is required.

## 15. Summary

Azure Queue Storage is a clean choice for **simple work queues**: producers send small messages, consumers receive with a visibility timeout, process, and delete using the message ID and current pop receipt. Because redelivery can occur, applications need **idempotency, bounded retries, poison queues, and durable job state**. For large payloads, store content in Blob and put only references in the queue.

When you need **topics/subscriptions, sessions, per-group ordering, built-in dead-letter queues, scheduled/deferred messages, or messaging transactions**, evaluate **Azure Service Bus**. Spring Cloud Azure offers separate starters for Storage Queue and Service Bus; base your choice on business semantics rather than the mere fact that both have the word "queue".

### Official References

- [Microsoft Learn — Introduction to Azure Queue Storage](https://learn.microsoft.com/azure/storage/queues/storage-queues-introduction)
- [Microsoft Learn — Get started with Azure Queue Storage using Java](https://learn.microsoft.com/azure/storage/queues/storage-quickstart-queues-java)
- [Microsoft Learn — Queue Storage REST API: Get Messages](https://learn.microsoft.com/rest/api/storageservices/get-messages)
- [Microsoft Learn — Queue Storage REST API: Update Message](https://learn.microsoft.com/rest/api/storageservices/update-message)
- [Microsoft Learn — Azure Service Bus messaging overview](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-messaging-overview)
- [Microsoft Learn — Message sessions](https://learn.microsoft.com/azure/service-bus-messaging/message-sessions)
- [Microsoft Learn — Dead-letter queues](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-dead-letter-queues)
- [Microsoft Learn — Spring Cloud Azure](https://learn.microsoft.com/azure/developer/java/spring-framework/)
