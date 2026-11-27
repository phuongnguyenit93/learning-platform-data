# Sending, Receiving, and Managing Visibility Timeout with Queue Storage

An API that accepts invoice-generation requests may need to call a PDF service, save the file to Azure Blob Storage, send an email, and update status. Forcing the client to wait for all these steps within a single HTTP request easily causes slow responses, timeouts, or failures when a dependent service is temporarily overloaded. A better design is for the API to write a message to **Azure Queue Storage**, return a job tracking ID, and let one or more **workers** process it asynchronously.

Putting a task into a queue is only half the problem. If a worker pulls a message and crashes, does the task vanish? If the worker runs longer than the **visibility timeout**, can another worker receive the same message? When a task succeeds, why must you call `Delete Message` with the exact **pop receipt**? And if writing data succeeds while deleting the message fails, how do you avoid creating two invoices?

This lesson answers those questions through the **send → receive → process → delete** mechanism, combined with **visibility timeout**, `dequeue_count`, retries, idempotency, and poison-message handling. It belongs to the **Queues and Messaging** chapter in the **CLOUD_PROVIDERS_AZURE** module: the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute, storage, and data; deploying, monitoring, securing, and controlling costs for an application architecture on Azure.

After this lesson, you will be able to:

- Explain Queue Storage, messages, producers, consumers/workers, TTL, visibility timeout, dequeue count, and pop receipts.
- Distinguish `Peek Message`, `Get/Receive Messages`, `Update Message`, and `Delete Message`.
- Describe exactly what happens when a worker crashes, exceeds the visibility window, or processes duplicates.
- Write Python SDK examples using Microsoft Entra ID to send, receive, extend visibility, and delete messages.
- Design retries, idempotency, poison queues, worker scaling, and monitoring.
- Secure queues with RBAC, managed identities, Private Endpoints where needed, and sensitive-data minimization.
- Determine when to use Storage Queue, Azure Service Bus, or Event Grid instead of misusing each service's capabilities.

## 1. What Is Azure Queue Storage Used For?

**Azure Queue Storage** is a message queuing service within Azure Storage. Producers place small messages into a queue; consumers pull those messages for asynchronous processing. A queue decouples the producer's request rate from the worker's processing speed, helping applications absorb traffic spikes and retry when tasks fail.

~~~mermaid
flowchart LR
    USER[User] --> API[Invoice Creation API]
    API -->|Send message| Q[(Azure Queue Storage)]
    API -->|202 Accepted + job ID| USER
    Q -->|Receive, temporarily invisible| W1[Worker 1]
    Q -->|Receive, temporarily invisible| W2[Worker 2]
    W1 --> DB[(Azure SQL)]
    W2 --> DB
    W1 --> BLOB[(Azure Blob Storage)]
    W2 --> BLOB
    W1 -. Success: delete message .-> Q
    W2 -. Error/crash: message visible again .-> Q
~~~

For example, the producer writes a message describing the work to be done, **not** the entire PDF file:

~~~json
{
  "eventId": "invoice-request-98421",
  "type": "GenerateInvoice",
  "invoiceId": "INV-98421",
  "blobName": "source/invoices/INV-98421.json",
  "schemaVersion": 1,
  "correlationId": "req-fd42b"
}
~~~

The worker reads the message, fetches source data from Blob Storage/SQL, generates the PDF, stores the output, and **confirms completion by deleting the message**. Large and sensitive data should live in an appropriate data store; the message should only carry safe identifiers or references.

### When to Use a Queue?

| Scenario | How a Queue Helps | Additional Design Needed |
|---|---|---|
| Background report/PDF generation | API responds quickly; worker processes later | Job state, retries, idempotency |
| Post-upload file processing | Decouples upload from resize/scan/index | Blob access protection, event ordering |
| Sending emails/notifications | Absorbs traffic bursts | Deduplication, rate limiting, delivery state |
| Batch data updates | Workers scale independently | Transactions, checkpointing, poison handling |
| Slow system integration | Buffers and retries on downstream errors | Backoff, circuit breaker, timeouts |

**Do not use Queue Storage as a database or sole transaction log.** A queue holds messages waiting to be processed; it does not provide arbitrary queries, guaranteed global ordering, or ACID transactions spanning both a database and the queue.

## 2. Service Structure and Key Limits

A **StorageV2** storage account can host queues in the Queue Storage service:

~~~text
Azure subscription
  Resource group
    Storage account: mystorageaccount
      Queue endpoint: https://mystorageaccount.queue.core.windows.net
      Queue: invoice-jobs
        Message A
        Message B
      Queue: invoice-jobs-poison
        Failed Message X
~~~

A **Queue** and a **Blob container** are distinct resources. The Queue endpoint has the form `https://<account>.queue.core.windows.net`, which differs from `https://<account>.blob.core.windows.net`. When configuring private DNS or RBAC, make sure you target the right service.

### Key Characteristics to Remember

| Property | Meaning | Consequence |
|---|---|---|
| **Message size** | Each Queue Storage message supports up to **64 KiB** in modern service versions | Do not embed large files; account for Base64 size expansion |
| **TTL (time-to-live)** | How long a message is allowed to exist after sending | When TTL expires, the message may be deleted even if unprocessed |
| **Initial visibility delay** | Delays when a newly sent message becomes visible to workers | Not the same as TTL or processing duration |
| **Receive visibility timeout** | Temporarily hides a message after a worker receives it | If it expires before deletion, the message may be received again |
| **Pop receipt** | Token tied to a receive/update operation needed for update/delete | Stale receipts are not guaranteed to remain valid |
| **Dequeue count** | Number of times a message has been retrieved for processing per the service | Useful for retry/poison policies |
| **Approximate message count** | Estimated number of messages in the queue provided by the service | Not an exact count or queue latency metric |

Storage Queue **does not guarantee strict FIFO**. An invisible message can be overtaken by a message sent later; multiple workers, retries, and varying processing times also change completion order. If your business logic requires strict ordering/session semantics, design a different service or partitioning strategy.

### TTL and Version-Dependent Limits

By default, messages typically have a **7-day TTL** if unspecified. With modern API versions, you can set a TTL longer than 7 days or `-1` for no automatic expiration where supported; limits depend on the API/SDK and service configuration, so never assume all older clients behave identically. **Visibility timeout does not extend TTL**: when a message expires, extending its visibility window will not keep it alive.

For long-lived backlogs—especially those with legal retention requirements—do not rely on infinite TTL as a system of record. Store business records and job states in a database/Blob Storage, and use the queue only to signal pending work.

### Content and Encoding

Messages sent via the Queue Storage REST API sit inside an XML payload, so characters and encoding must be compatible. Modern Python SDKs may **not Base64-encode every message by default**. When sending JSON with Unicode or special characters, you can configure `TextBase64EncodePolicy` and `TextBase64DecodePolicy` on both producer and consumer. **All senders and receivers on the same queue must agree on the encoding policy.**

Base64 typically expands content size by about **one-third**. Because the 64 KiB limit applies to the encoded content as received by the service, the safe raw JSON size can be substantially smaller than 64 KiB. For payloads exceeding the threshold, store them in Blob Storage and pass only an identifier or blob name; check the actual encoded size before sending.

## 3. Message Lifecycle: Send, Receive, Process, Delete

A message sent to a queue receives a **message ID**, insertion time, expiration time, and time next visible. When a worker calls **receive**, the service returns the content along with metadata and a **pop receipt**, while temporarily hiding the message so other workers normally do not receive it for a period.

~~~mermaid
stateDiagram-v2
    [*] --> Visible: Send (once initial delay elapses)
    Visible --> Invisible: Receive / Get Messages
    Invisible --> Deleted: Delete with valid pop receipt
    Invisible --> Visible: Visibility timeout expires
    Invisible --> Invisible: Update visibility + new receipt
    Visible --> Expired: TTL expires
    Invisible --> Expired: TTL expires
    Deleted --> [*]
    Expired --> [*]
~~~

These states describe the logical mechanism. In real operations, a worker can experience network drops, request timeouts, or retries; therefore, **messages can be redelivered** and you must never assume exactly-once execution.

### Standard Processing Flow

1. **Producer** generates a unique event/job ID, validates input, and sends the message to the queue.
2. **Worker** calls receive with an appropriate visibility timeout and obtains the message ID and pop receipt.
3. **Worker** validates the schema, verifies required data, executes business logic, and saves the result to durable storage.
4. If processing takes long, the worker **updates message visibility** before the timeout expires and keeps the new receipt.
5. **Only after the result is durably persisted** does the worker call delete using the message ID and current pop receipt.
6. If the worker fails before delete, the message reappears after the visibility timeout or updated time; another worker can reprocess it.
7. If a message fails repeatedly, application policy moves it to an investigation area/poison queue instead of retrying forever.

### "Receive" Does Not Mean "Delete"

In Queue Storage, `Receive Messages` (often `Get Messages` in REST) is a **temporary hide** operation, not an automatic delete. If a worker calls receive and exits without calling delete, the message stays in the queue until its visibility timeout or TTL expires. This enables retries when a worker crashes, and it is also why **idempotent processing** is mandatory.

## 4. Queue Storage Operations and Easily Confused Differences

| Operation | Typical API/SDK | Changes Visibility? | Deletes Message? | When to Use |
|---|---|---|---|---|
| **Send** | `send_message` / Put Message | Can set initial visibility delay | No | Producer enqueues work |
| **Peek** | `peek_messages` / Peek Messages | **No** | No | Inspect some visible messages, diagnostics |
| **Receive** | `receive_messages` / Get Messages | **Yes**, temporarily hides and returns pop receipt | No | Worker pulls work |
| **Update** | `update_message` / Update Message | **Yes**, updates next visible time; can change content per API | No | Extend visibility / defer during processing |
| **Delete** | `delete_message` / Delete Message | Not applicable after deletion | **Yes** | Acknowledge after successful processing |
| **Clear** | `clear_messages` / Clear Messages | No | **Deletes all messages in queue** | Only when intentionally purging the entire backlog |

**Peek does not lock messages.** Two systems peeking simultaneously can see similar contents without ownership or a pop receipt to process/delete. Never build a worker based on peek assuming it can acknowledge completion like receive.

**Delete is not the same as "complete" in Azure Service Bus.** Azure Queue Storage requires passing a **message ID + valid pop receipt**. A pop receipt acts like an update guard token, not a permanent lease. The receipt can change on receive/update; using a stale receipt can cause deletion to fail.

**Clear queue** is a broad, destructive backlog purge, not a way to remove one poison message. Never run clear in production just because workers are reporting errors; isolate or recover failing messages in a controlled manner first.

## 5. Visibility Timeout: Reasoning on a Timeline

Visibility timeout is the duration during which a message is **temporarily unavailable for new receive calls**, measured from the corresponding receive or update operation. It gives a worker a window to process without other workers concurrently pulling the same message during that window. However, it is **not an exclusive lock guaranteeing a full end-to-end transaction**.

Suppose a message has a 1-hour TTL and worker A receives it at 10:00:00 with a **60-second** visibility timeout:

~~~text
10:00:00   A receives message M → invisible until roughly 10:01:00
10:00:05   A begins processing, calls database
10:00:40   A is waiting on the invoice rendering service
10:01:00   Visibility timeout expires; M can be received by worker B
10:01:05   B receives M, gets a new pop receipt
10:01:10   A finishes the earlier work and calls delete with the old receipt
10:01:10   A's delete may be rejected because the receipt is stale
10:01:20   B may be executing the exact same job again
~~~

**Conclusion:** worker A can keep running **after losing exclusive receipt ownership of the message**. If A sends an email or writes an invoice to the database, B may do the same. Thus, visibility timeout **reduces unintended concurrent processing but does not eliminate duplicate processing**.

### 5.1. Default Visibility Timeout

For a normal receive operation, the default visibility timeout in Azure Queue Storage is **30 seconds** if no other value is requested in the API/SDK. For jobs taking only a few seconds, the default may suffice. For jobs lasting 2–5 minutes, set an appropriate initial timeout or renew it during processing.

### 5.2. Avoid Timeouts That Are Too Short or Too Long

| Visibility Timeout | Benefit | Risk |
|---|---|---|
| **Too short** relative to processing time | Crashed workers are retried sooner | Message may reappear while job is still running, increasing duplicates |
| **Matched** to typical processing time | Reduces timeout-induced duplicates | Still must handle crashes, retries, and long-tail latency |
| **Too long** | Reduces cases where slow jobs outlast timeout | If a worker dies, retry is delayed for a long time |
| **With heartbeat/renewal** | Balances short initial timeout and long jobs | Requires logic for receipt tracking, renewal failures, shutdown, and monitoring |

Suppose p99 processing time is around 90 seconds: a fixed 30-second timeout easily creates overlap. Yet setting 2 hours for every job slows recovery when a worker crashes. One approach is receiving with 90–120 seconds, measuring actual latency, and renewing up to a bounded cap while work continues. Never pick numbers by guesswork.

### 5.3. Initial Visibility Delay Differs from Receive Visibility

**Initial visibility delay** on send **postpones the first time a message can be received**. For example, a producer sends a job at 10:00 with a 120-second delay; normal workers cannot receive it until about 10:02. Once a worker receives it, a new **receive visibility timeout** governs how long it stays hidden during processing.

TTL keeps ticking during both initial delay and invisibility windows. If the initial delay is too close to or exceeds TTL, the message can expire before it ever has a chance to be processed. Queue Storage is not a complex business scheduler: for distant schedules, recurrence, or multi-step workflows, consider Azure Functions timers, Logic Apps, or an appropriate orchestrator.

### 5.4. Visibility Timeout Bounds

Minimum and maximum values depend on REST version, SDK, and operation. In modern Queue Storage versions, receive/update visibility timeouts can be configured up to **days** (commonly up to 7 days), but **must not exceed remaining TTL** and must follow API contracts. Do not use extremely long timeouts as a substitute for job progress management.

Timeline calculations in this lesson are **illustrative timelines**, not an SLA guaranteeing delivery at the exact millisecond. When the timeout expires, the message **becomes eligible** to be received again; there is no guarantee a worker will immediately pick it up at that exact instant.

## 6. Pop Receipt: Why Must You Store and Update the Right Token?

When a consumer receives a message, the service returns a **message ID** and a **pop receipt**. The message ID identifies the target message; the pop receipt proves the consumer holds the token version from a recent receive or update operation.

### 6.1. Receive → Renew → Delete Sequence

~~~mermaid
sequenceDiagram
    participant W as Worker A
    participant Q as Azure Queue Storage
    W->>Q: Receive M (visibility 60s)
    Q-->>W: M.id + popReceipt R1
    Note over W: Still processing, still holds update authority
    W->>Q: Update M + R1, visibility 90s
    Q-->>W: popReceipt R2 + nextVisibleOn
    Note over W: Business output persisted
    W->>Q: Delete M + R2
    Q-->>W: Success
~~~

**Common bug:** calling update successfully but still using `R1` to delete. After an update, the service issues a **new pop receipt `R2`**; attempting to delete with `R1` can be rejected. Clients must store the **latest receipt** for subsequent steps.

### 6.2. A Receipt Is Not Permanent Ownership

If the visibility timeout expires and worker B receives the message again, B gets a new pop receipt. A can no longer assume permission to update or delete that message. If A is still executing business logic, its output writes can happen concurrently with B. The pop receipt only controls **message operations within Queue Storage**; it does not lock SQL rows, Blob files, or external APIs.

**Safe design:** pair a *business operation ID* with a unique constraint or durable state in the data store. When two workers process the same job concurrently, only one business outcome is accepted or repeated executions yield the same result.

### 6.3. Extending Visibility Timeout

A long-running worker can call `Update Message` before expiry to set a new invisibility interval. The update request's visibility timeout is typically measured **from the moment the service accepts the update**, not added on top of the previous expiry timestamp.

Example:

~~~text
10:00:00 Receive with 60s         → visible around 10:01:00
10:00:45 Update with 120s         → visible around 10:02:45
10:02:00 Update with 120s         → visible around 10:04:00
10:02:30 Processing succeeded     → Delete using the receipt from the 10:02 update
~~~

No renewal is needed after deletion. If an update fails because the receipt is invalid, the message expired, or the queue is unreachable, the worker must assume it **no longer reliably owns the message**. Do not keep performing non-idempotent side effects and blindly deleting with an old receipt.

### 6.4. Can Update Message Change Message Content?

The update API can replace message content along with the visibility timeout under supported conditions. However, for critical workflows, avoid modifying message content for every progress update. Keeping the **job ID** in the queue and updating **job status** in a database is usually clearer, queryable, and better audited. If message content is updated, producers and consumers must agree on schema/encoding, and the updated message size still obeys service limits.

## 7. Delivery Semantics: At-Least-Once, Duplicates, and Ordering

Storage Queue fits an **at-least-once-style** processing model. Applications should assume a message can be received multiple times, including when senders or receivers encounter network timeouts. Never design business logic that is only correct if a message is processed **exactly once**.

### Situations That Cause Duplicate Processing

1. A worker finishes processing but **crashes before calling delete**.
2. A worker writes to the database successfully, but the delete request times out; it is uncertain whether the service processed the delete.
3. Visibility timeout expires while the worker is still running; another worker receives the message again.
4. A producer sends a message, the request times out, and the producer—unsure if it was accepted—**retries the send**, creating two messages with different IDs for the same business event.
5. A worker receives a message again after retry/backoff and repeats side effects if completion state was not recorded.

### At-Least-Once Does Not Guarantee Redelivery on Every Failure

If a message's **TTL expires**, an administrator deletes it, the queue is cleared, or it is purged, it will no longer be available for retry. More accurately: the architecture must **tolerate redelivery**, while managing TTL, deletions, monitoring, and persistent job state so results are never lost.

### FIFO and Completion Order

Message A may be sent before B, yet A is received and hidden for 120 seconds while B finishes immediately. B finishes before A. With multiple workers, do not rely on Queue Storage for:

- Every message being processed strictly in send order.
- Only one consumer across the entire system ever handling a given business key.
- Session-locked ordering for messages belonging to the same customer/order.
- Atomic transactions spanning multiple messages and multiple data stores.

If you genuinely need **sessions, duplicate detection, a native dead-letter queue, or messaging transactions**, consider **Azure Service Bus** per supported SKU/features; Queue Storage stays simple and fits asynchronous workloads that do not require those semantics.

## 8. Idempotency: Preventing Duplicate Invoices on Redelivery

An **idempotent operation** is one where executing it multiple times with the same business identifier produces the same final state as executing it once. For message-driven systems, this is a foundational requirement.

### 8.1. Distinguishing Message ID from Business Event ID

| Identifier | Issued By | Used For |
|---|---|---|
| **Queue message ID** | Azure Queue Storage on send | Receiving/updating/deleting a specific message in the queue |
| **Pop receipt** | Azure Queue Storage on receive/update | Authenticating a specific update/delete message session |
| **Business event/job ID** | Producer or business system | Deduplicating across multiple messages, send retries, recovery |
| **Correlation ID** | Distributed observability | Linking logs/traces across API, queue, worker, and database |

If a producer retries and creates two Queue messages with **two different message IDs** but the same `eventId=invoice-request-98421`, deduplicating solely on Queue message ID is **insufficient**. You need a stable business-level idempotency key.

### 8.2. Database as the Duplicate Guard

Example data model:

~~~sql
-- SQL pseudocode: transaction/upsert syntax depends on the database.
CREATE TABLE ProcessedJobs (
    EventId VARCHAR(128) PRIMARY KEY,
    State VARCHAR(32) NOT NULL,
    ResultLocation VARCHAR(1024),
    UpdatedAtUtc DATETIME2 NOT NULL
);
~~~

Recommended processing flow:

1. Parse the message, extract `eventId`, and validate the schema.
2. Within an appropriate database transaction, check/record status by `EventId` using a **unique constraint** or conditional claim mechanism.
3. If the job is already `Completed`, skip side effects and consider deleting the current message.
4. If the job is claimed for processing, execute the task passing downstream **idempotency keys** (where supported).
5. Durably commit the result and `Completed` status, ensuring only one valid outcome exists.
6. After commit, delete the Queue message using the current receipt.

**Do not naively "mark Processed before executing side effects."** If the worker dies between those two steps, the job could be skipped without producing output. Use a state machine (`Pending`, `Processing`, `Completed`, `Failed`), appropriate ownership/lease expiry, transactions or an outbox where needed, and ensure safe resumption.

### 8.3. One Transaction Cannot Span SQL + Storage Queue

Committing to SQL and deleting a message are **two operations across two services**—they do not belong to a single default ACID transaction.

~~~mermaid
sequenceDiagram
    participant W as Worker
    participant DB as Azure SQL
    participant Q as Queue Storage
    W->>Q: Receive M (receipt R)
    Q-->>W: eventId E
    W->>DB: Commit invoice result for E
    DB-->>W: Success
    Note over W: Worker crash/network failure
    Q-->>W: Message M may reappear
    Note over DB: Result for E already exists
~~~

If another worker reprocesses E, the database should return the existing result and **not** create a new invoice. For external side effects (sending SMS, charging payments), use idempotency keys, outbox/inbox tables, or verifiable partner state. **Visibility timeout does not replace data-layer deduplication.**

### 8.4. Producer Retries

When `send_message` times out, the producer does not always know whether Azure received the message. Retrying the same business event can create a duplicate copy. Therefore, the producer must attach a durable event ID, track publish state according to the architecture, and workers must deduplicate by event ID rather than assuming each HTTP send creates one job.

When consistency between a **database commit and message publication** is required, use a **transactional outbox**: write both the business change and the outbox event in the same database transaction, then have a publisher read the outbox and send a Queue message with a stable event ID. An outbox can also send duplicates if it crashes after sending; workers still require idempotency.

## 9. Python SDK Practice: Configuring Identity and Queues

The following examples use **`azure-storage-queue`** and **`azure-identity`** on Python 3. These snippets are illustrative and **were not executed during authoring**. You need a test Azure Storage account, permissions to create queues and handle messages, and a signed-in Azure CLI/credential.

### 9.1. Install Libraries and Prepare

~~~bash
python -m pip install azure-storage-queue azure-identity

# Sign in in the lab environment when using Azure CLI credentials.
az login
~~~

Locally, `DefaultAzureCredential` can use supported developer sign-in sources. On Azure App Service, Functions, AKS, or VMs, prefer **managed identity / Workload Identity** as supported by the platform rather than hardcoded keys. Assign the identity the appropriate Azure Storage Queue data-plane role; the storage account and network must allow access.

Example environment variable setup:

~~~bash
export AZURE_STORAGE_ACCOUNT="<lab-storage-account-name>"
export AZURE_QUEUE_NAME="invoice-jobs"
~~~

In PowerShell, use `$env:AZURE_STORAGE_ACCOUNT="..."` and `$env:AZURE_QUEUE_NAME="invoice-jobs"`. Values in `<...>` are placeholders—do not run them literally.

### 9.2. Create QueueClient with Entra ID

~~~python
import os

from azure.identity import DefaultAzureCredential
from azure.storage.queue import (
    QueueClient,
    TextBase64EncodePolicy,
    TextBase64DecodePolicy,
)

account_name = os.environ["AZURE_STORAGE_ACCOUNT"]
queue_name = os.environ.get("AZURE_QUEUE_NAME", "invoice-jobs")

credential = DefaultAzureCredential()
queue = QueueClient(
    account_url=f"https://{account_name}.queue.core.windows.net",
    queue_name=queue_name,
    credential=credential,
    message_encode_policy=TextBase64EncodePolicy(),
    message_decode_policy=TextBase64DecodePolicy(),
)
~~~

**Important:** this example uses Base64 for text messages. If the producer uses a Base64 encode policy but the worker omits the decode policy, the worker will read a Base64 string instead of JSON. Conversely, using a decode policy on a queue holding raw non-Base64 messages can fail. Align encoding across producer/consumer contracts and plan schema migration before changing it.

In production, reuse clients/credentials across the worker lifecycle instead of recreating them per message. Never write connection strings containing storage account keys, SAS tokens, or bearer tokens into source code or logs.

### 9.3. Controlled Lab Queue Creation

~~~python
from azure.core.exceptions import ResourceExistsError

try:
    queue.create_queue()
    print("Queue created:", queue_name)
except ResourceExistsError:
    print("Queue already exists:", queue_name)
~~~

This snippet requires **queue creation** permission (management of queue objects), which may be broader than a send-only producer's permissions. In production, use **IaC / a platform team** to provision queues and grant applications only the send or process roles they need. Workers generally should not have permission to create or delete queues.

An existing queue **should never be deleted and recreated just to run an example**, as it may hold another application's backlog.

## 10. Sending Messages: Producer and Initial Visibility Delay

Continuing with the `queue` variable created in section 9.2.

### 10.1. Sending a JSON Job

~~~python
import json
import uuid

job = {
    "schemaVersion": 1,
    "eventId": f"invoice-request-{uuid.uuid4()}",
    "invoiceId": "INV-98421",
    "type": "GenerateInvoice",
    "sourceBlob": "source/invoices/INV-98421.json",
}

payload = json.dumps(job, ensure_ascii=False, separators=(",", ":"))
result = queue.send_message(
    payload,
    time_to_live=3600,      # TTL = 1 hour
    visibility_timeout=0,   # Message can be received immediately
)
print("Sent message ID:", result.id)
~~~

The client's `TextBase64EncodePolicy` encodes the text before sending. `time_to_live=3600` is in seconds; `visibility_timeout=0` on send is an **initial visibility delay of 0**, not a receive lock of 0.

**Idempotency note:** this example generates a `uuid4` on each run to illustrate a new job. In real business logic, if retrying the **same request** after a timeout, you must **preserve the eventId originally assigned to that request**. Generating a new UUID on every retry prevents workers from recognizing two messages belong to one logical job.

### 10.2. Sending a Delayed Job

~~~python
delayed_job = {
    "schemaVersion": 1,
    "eventId": "invoice-reminder-98421",
    "invoiceId": "INV-98421",
    "type": "SendReminder",
}

queue.send_message(
    json.dumps(delayed_job),
    visibility_timeout=120,  # Delay initial visibility by about 2 minutes
    time_to_live=1800,       # Message lives at most 30 minutes
)
~~~

The service starts counting TTL at send time. Never set initial delay greater than or equal to TTL in a way that expires the message before it can be processed. For multi-week schedules or recurring jobs, use a dedicated workflow scheduler rather than very long visibility delays.

### 10.3. A Good Producer Tracks State

| Checkpoint | Why Does It Matter? |
|---|---|
| Stable `eventId` across retries | Prevents duplicate messages and side effects |
| `schemaVersion` | Consumers know how to parse and stay compatible during rollouts |
| `correlationId` | Traces logs across API → queue → worker |
| Reasonable `time_to_live` | Prevents jobs from expiring before processing |
| Small payload, no secrets | Respects 64 KiB limit and reduces data exposure |
| Persist job status to DB when needed | Lets users query Pending/Completed/Failed |
| Retry sends by policy | Distinguishes transient errors from auth/network/config issues |

Do not return `200 Completed` to the client right after enqueueing if the business flow expects work completion. APIs usually return **202 Accepted** with a job ID so clients can poll progress or receive a callback per application design.

## 11. Peek and Receive: Observing vs. Processing

### 11.1. Peek Does Not Hide Messages

~~~python
for m in queue.peek_messages(max_messages=3):
    print("Visible message:", m.id, m.content)
~~~

`peek_messages` reads a few visible messages without making them invisible or incrementing `dequeue_count` like a receive. It is a quick inspection tool—**not a mechanism for scanning the entire backlog** or guaranteeing visibility of every message. It also does not return a pop receipt for deletion.

Do not use peek to accurately count active jobs: invisible messages are excluded, multiple workers may be processing in parallel, and approximate counts are not transactionally consistent.

### 11.2. Receive with a 60-Second Visibility Timeout

~~~python
received = queue.receive_messages(
    messages_per_page=1,
    visibility_timeout=60,
)
message = next(iter(received), None)

if message is None:
    print("No visible message currently")
else:
    print("ID:", message.id)
    print("Dequeue count:", message.dequeue_count)
    print("Next visible at:", message.next_visible_on)
    print("Content:", message.content)
    print("Pop receipt received:", bool(message.pop_receipt))
~~~

Receiving **temporarily hides** the message. Because this example does not call delete, the message will **become eligible to be received again** after the visibility timeout expires, unless deleted, expired by TTL, or processed by another worker. When testing in a lab, remember that calling receive itself mutates message state and dequeue count.

When reading a page of messages, Queue Storage limits how many messages can be fetched in one request—typically up to **32 messages per request** in modern APIs. The SDK provides pagination/iterators; do not assume every SDK call always returns the exact requested count if fewer visible messages exist.

### 11.3. Acknowledge with Delete After Success

~~~python
import json

received = queue.receive_messages(
    messages_per_page=1,
    visibility_timeout=60,
)
message = next(iter(received), None)

if message is not None:
    job = json.loads(message.content)

    # LAB: simulate successful processing by printing output.
    # PRODUCTION: replace with idempotent processing and durable commit.
    print("Would process:", job["eventId"], job["type"])

    queue.delete_message(
        message.id,
        message.pop_receipt,
    )
    print("Deleted message:", message.id)
~~~

**Warning:** the snippet above calls delete after `print` to illustrate the API, **not as a safe production worker**. In production, run the actual work, persist results durably, ensure idempotency, and only then delete. If an error occurs, **never delete just to make the queue look clean**.

### 11.4. When Receive Succeeds but Processing Is Not Finished

If a worker cannot finish within the granted time, there are three options:

1. **Extend invisibility** with Update Message while the job is still making progress.
2. **Let it time out** to retry on transient failures or worker crashes; enforce backoff and poison policies.
3. **Move to a poison queue** when a message cannot succeed after reasonable attempts, then delete the original in safe order.

Option 3 should not be triggered on a single network error. Distinguish permanent errors (bad schema, unrecoverable missing reference) from transient errors (database unavailable, API rate limited).

## 12. Updating Visibility During a Long Job

Suppose generating a report takes 4 minutes, while the worker receives the message with an initial 90-second timeout. Without renewal, the message can reappear before the job finishes. The solution is calling `update_message` before expiry and **saving the new pop receipt**.

### 12.1. Update Example with the Python SDK

~~~python
received = queue.receive_messages(
    messages_per_page=1,
    visibility_timeout=90,
)
message = next(iter(received), None)

if message is not None:
    current_receipt = message.pop_receipt

    # Suppose the app finished one stage and needs more time.
    update_result = queue.update_message(
        message.id,
        current_receipt,
        visibility_timeout=120,
    )
    current_receipt = update_result.pop_receipt
    print("Extended visibility until:", update_result.next_visible_on)

    # Only after processing has committed successfully and the receipt is valid:
    # queue.delete_message(message.id, current_receipt)
~~~

Here, `update_message` **does not delete the message**. The lab snippet leaves delete commented out because no business work occurred. Without deletion, the message will reappear after the new timeout.

### 12.2. Heartbeat for Long-Running Work

A production worker must track both processing progress and invisibility expiration. Conceptual model:

~~~text
Receive message with visibility_timeout = 90 s
    receipt = message.pop_receipt
    deadline = next_visible_on

While job is not completed:
    process one bounded, recoverable chunk
    if approaching deadline:
        response = UpdateMessage(message_id, receipt, 90 s)
        receipt = response.new_pop_receipt
        deadline = response.next_visible_on
    if lease/receipt update fails:
        stop unsafe side effects; checkpoint and investigate

If business result committed:
    DeleteMessage(message_id, latest_receipt)
Else:
    keep retryable state and let message reappear
~~~

This is **pseudocode**, not a runnable script. For jobs with blocking calls longer than the timeout, run the heartbeat separately from blocking work or break the work into short checkpointed steps. Heartbeats can also fail due to process crashes, network timeouts, or expired receipts.

### 12.3. When Should You Renew?

For example, with 90-second visibility and 30-second processing chunks, a worker can renew with roughly **30–45 seconds** remaining before `nextVisibleOn` to allow margin for network latency, retries, and scheduling jitter. Rely on synchronized clocks and returned timestamps rather than logic like "sleep exactly 89 seconds then update."

Do not renew a stalled job indefinitely. Enforce a **maximum processing duration**, a max heartbeat count, and a business deadline, transitioning to failed/investigation state once exceeded.

### 12.4. Delete Can Fail Even When the Job Succeeded

In real execution paths:

~~~text
T1: Worker finishes writing PDF to Blob Storage
T2: Worker commits Completed status to SQL
T3: Worker calls Delete Message
T4: Delete request times out / invalid receipt
T5: Message may be received again
~~~

The next worker must recognize that `eventId` is already Completed and **avoid regenerating or double-billing**. It can then delete the current message with its valid receipt after verifying state. This is the clearest illustration of why **delete acknowledges message delivery**, while **idempotency is the business system's responsibility**.

## 13. Dequeue Count, Retry Policy, and Poison Messages

When a worker receives a message, `dequeue_count` indicates how many times the service has delivered it for processing. If a message repeatedly fails and reappears, the count climbs. Applications combine this count with **error category** and job age to decide whether to retry or quarantine.

### 13.1. Transient Errors vs. Unrecoverable Errors

| Error Type | Examples | Suggested Policy |
|---|---|---|
| **Transient** | SQL timeout, HTTP 503 from external service | Retry with backoff/jitter and bounded attempts |
| **Rate limit** | Partner API returns 429 with `Retry-After` | Honor backoff guidance and quotas |
| **Dependency outage** | Storage/Key Vault temporarily unreachable | Circuit breaker, reduce worker concurrency, alert |
| **Schema invalid** | Missing `eventId` or unsupported `schemaVersion` | Do not retry indefinitely; quarantine after verification |
| **Reference invalid** | Blob does not exist due to fixed wrong ID | Check eventual dependency race; if truly unrecoverable, quarantine |
| **Business rejection** | Invoice already canceled, must not recreate | Record valid terminal state; delete rather than retry |
| **Credential/RBAC error** | Worker consistently gets 403 | Fix identity/permissions; do not high-speed retry |

**Do not treat every exception as "retry."** A JSON parsing error on the 100th attempt will still fail on the same payload if the schema has not changed.

### 13.2. What Is a Poison Message?

A **poison message** is a message that cannot be processed successfully under policy after multiple attempts or due to malformed content/business errors. For instance, `eventId=invoice-request-98421` points to a corrupt file that always crashes the worker.

An application using Queue Storage directly typically creates a quarantine queue, such as `invoice-jobs-poison`:

~~~mermaid
flowchart TD
    MAIN[(invoice-jobs)] --> WORKER[Worker receives message]
    WORKER --> CHECK{Content & state?}
    CHECK -->|Valid| PROCESS[Idempotent processing]
    PROCESS -->|Success| DELETE[Delete original message]
    PROCESS -->|Transient error| RETRY[Backoff / visibility timeout]
    RETRY --> MAIN
    CHECK -->|Permanent error or max attempts exceeded| POISON[(invoice-jobs-poison)]
    POISON --> ACK[Delete original only after poison write succeeds]
    ACK --> REVIEW[Alert + investigate + approved replay]
~~~

Azure Queue Storage **does not provide a native dead-letter queue** like Azure Service Bus. A `-poison` queue here is an ordinary queue created and managed by the application or framework. **Azure Functions Queue Storage trigger** implements its own poison queue behavior per trigger configuration, typically naming it `<original-queue>-poison` after `maxDequeueCount`; do not assume Storage Queue moves messages automatically when using the SDK directly.

### 13.3. Pattern for Moving to a Poison Queue

When quarantining a message, ordering matters:

1. Identify the message by `eventId`; capture message ID, dequeue count, error category, and timestamp.
2. Send a record **with enough context for investigation without exposing secrets** to the poison queue or status store.
3. Verify the poison write succeeded.
4. **Only then** delete the original message using its current pop receipt.
5. Trigger an alert with an owner and remediation runbook.

If writing to poison succeeds while deleting the original fails, two copies can exist. Because moving across queues is **not an atomic transaction**, poison processing must also be idempotent by `eventId`.

**Simplified** Python example (requires `queue` and `poison_queue` configured with the same encoding policy):

~~~python
import json
from datetime import datetime, timezone

def move_to_poison(main_queue, poison_queue, message, reason):
    payload = {
        "originalMessageId": message.id,
        "eventId": None,
        "dequeueCount": message.dequeue_count,
        "reason": reason,
        "failedAtUtc": datetime.now(timezone.utc).isoformat(),
        "content": message.content,
    }
    try:
        parsed = json.loads(message.content)
        payload["eventId"] = parsed.get("eventId")
    except (ValueError, TypeError):
        pass

    # Strip sensitive data and enforce the 64 KiB limit
    # before using in production.
    poison_queue.send_message(json.dumps(payload))
    main_queue.delete_message(message.id, message.pop_receipt)
~~~

**This is not an "exactly once" queue transfer algorithm.** If payloads are large or contain PII/secrets, safely store the original in RBAC-protected Blob Storage and send **a reference** to the poison queue. Production code also needs retry/exception handling, idempotency, and retention limits for poison records.

### 13.4. Do Not Retry Forever with Dequeue Count

Example policy:

~~~text
Max attempts: 5 (application rule)
Attempt 1: normal processing
Attempt 2: ~30s delay if transient
Attempt 3: ~60s delay if transient
Attempt 4: ~120s delay if transient
Attempt 5: if still failing, quarantine + alert
~~~

These numbers are examples only. If a Queue message has 90 seconds of TTL left, you cannot apply multi-minute retry delays without risking expiration. Never extend indefinitely or reset attempt counts just to avoid marking a message as poison. For severe errors involving financial or data loss, alert earlier than the standard retry threshold.

## 14. Retry, Backoff, and Polling When the Queue Is Temporarily Empty

A worker should not hammer receive hundreds of times per second when the queue is empty: it wastes transactions, network bandwidth, and creates monitoring noise. Instead, use **bounded polling** with backoff/jitter—process when messages arrive, and back off up to a cap when empty.

### 14.1. Worker Loop Pseudocode

~~~text
pollDelay = 1 second
while service is running:
    messages = Receive(maxBatch, visibilityTimeout)
    if no messages:
        sleep(min(pollDelay + jitter, 15 seconds))
        pollDelay = min(pollDelay * 2, 15 seconds)
        continue

    pollDelay = 1 second
    for each received message:
        if event already Completed:
            Delete using current pop receipt
        else:
            process with idempotency + bounded timeout
            if success committed:
                Delete using current pop receipt
            else:
                retry by controlled visibility/backoff
                or move to poison after policy threshold
~~~

Avoid sleeping across the entire worker pool in a way that blocks healthy messages. You can run multiple worker instances or appropriate async I/O, while capping concurrency according to downstream DB/API limits—not CPU count alone.

### 14.2. Per-Message Backoff vs. Polling Backoff

- **Polling backoff:** reduces receive calls when the queue is empty or experiencing service errors.
- **Message retry backoff:** delays a failed message before its next receive, using `Update Message` with a new visibility timeout or letting the set timeout expire.

Confusing these two leads to workers polling infrequently while immediately re-picking up a failing message, or delaying all healthy jobs because one job failed.

### 14.3. Timeouts and Cancellation

A production worker must handle:

- **Graceful shutdown** when App Service, Container Apps, or AKS terminates an instance.
- Maximum duration per job and checkpointing support.
- `Processing`/`Completed` database records for safe recovery.
- Preventing infinite retries in HTTP clients or SDKs past the job deadline.
- Capping concurrent message processing and downstream connections.
- Pausing/throttling consumers during widespread database or partner API outages.

If a worker receives a batch of 32 messages with a 60-second timeout but processes them sequentially on a single thread, later messages may become visible again **before their turn**. Batch size, concurrency, and visibility timeout must be designed together.

## 15. Creating Azure Queue Storage with Azure CLI in a Lab

This section creates a **test storage account and queue**, which the SDK examples above can then interact with. **Not executed during authoring.** Creating real resources can incur charges; confirm subscription and permissions before running.

### 15.1. Preparation

- Azure CLI installed and signed into Microsoft Entra ID for the right tenant/subscription.
- Permissions to create resource groups/storage accounts per organizational policy.
- Appropriate **Queue Storage data-plane** role to create queues or send/receive messages.
- Network access to `https://<account>.queue.core.windows.net`.
- Valid, globally unique storage account name; queue name following Storage Queue naming rules.

~~~bash
az login

SUBSCRIPTION_ID="<lab-subscription-id>"
RG="rg-queue-lab"
LOCATION="southeastasia"
ACCOUNT="<globallyuniquestorageaccount>"
QUEUE="invoice-jobs"

az account set --subscription "$SUBSCRIPTION_ID"
az account show --query "{id:id, name:name, tenantId:tenantId}" -o table
~~~

Do not run `<...>` placeholders literally. Names and regions are examples; if your organization uses a landing zone or pre-provisioned resource groups, **do not create extra resource groups outside your scope**.

### 15.2. Create a StorageV2 Account

~~~bash
az group create \
  --name "$RG" \
  --location "$LOCATION"

az storage account create \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --https-only true \
  --min-tls-version TLS1_2
~~~

`Standard_LRS` suits a **simple lab**, not a default recommendation for workloads needing availability-zone resilience or regional disaster recovery. For production, choose redundancy/replication based on RPO/RTO, supportability, and actual cost. Never alter network/key settings on a shared storage account just to run this exercise.

### 15.3. Create a Queue Using Microsoft Entra Authentication

~~~bash
az storage queue create \
  --account-name "$ACCOUNT" \
  --name "$QUEUE" \
  --auth-mode login
~~~

If your Azure CLI version differs in command syntax or options, check `az storage queue create --help`. If you hit `AuthorizationPermissionMismatch`, verify **data-plane roles**, scope, role assignment propagation time, tenant/subscription, and network rules. Control-plane permissions on a storage account **do not implicitly grant** read/write access to queue messages via Entra tokens.

Verify with a read command (where supported by CLI):

~~~bash
az storage queue list \
  --account-name "$ACCOUNT" \
  --auth-mode login \
  --output table
~~~

Sending, receiving, renewing, and deleting use the Python SDK because it clearly demonstrates pop receipts and visibility timeouts. You do not need storage account keys or key-based connection strings to run this lab with Entra ID when roles and features are supported.

### 15.4. Check RBAC Before Blaming the SDK

Someone with `Contributor` can create a StorageV2 account and still get 403 when sending a Queue message. This is the separation of **control plane** and **data plane**. Request **Storage Queue Data Message Sender/Processor/Contributor** at the required scope per current Azure configuration, and wait for role propagation before retrying.

Never grant subscription-wide `Owner` or enable Shared Key permanently just to bypass RBAC errors in a lab.

## 16. Securing Queue Storage with Entra ID, RBAC, and Private Endpoints

Queue Storage sits as an intermediary between APIs and workers running on Azure App Service, Azure Functions, Azure Container Apps, AKS, or VMs. Security design must answer:

1. **Who can send** messages?
2. **Who can receive and delete** messages?
3. **Who can create/delete queues or clear backlogs?**
4. **Which network paths** can reach the queue endpoint?
5. **What does the message contain**, and how is sensitive data protected?

### 16.1. Least-Privilege Data-Plane Roles

Azure Storage Queue supports Microsoft Entra authorization and dedicated data roles.

| Principal | Need | Role/Mechanism to Consider |
|---|---|---|
| **API producer** | Send messages to a specific queue | `Storage Queue Data Message Sender` at the smallest supported scope |
| **Worker consumer** | Peek/receive/delete messages | `Storage Queue Data Message Processor` at the required processing scope |
| **Provisioning pipeline** | Create queues and manage metadata/permissions via IaC | Queue management role such as `Storage Queue Data Contributor` when truly required |
| **Monitoring team** | View metrics/logs; does not process messages | Azure Monitor/Reader roles and minimal data-plane permission only if peek is needed |
| **Poison investigator** | Read and decide whether to replay poison messages | Restricted role on poison queue with approval workflow |

Exact role names and `DataActions` must be verified against Azure RBAC at deployment time. A **send role** should not automatically grant **clear queue** permission. Likewise, workers rarely need permission to delete the entire queue resource.

**Microsoft Entra ID / managed identity** reduces the need for long-lived account keys or SAS tokens. On Azure Functions, App Service, VMs, Container Apps, or AKS, choose the platform-supported workload identity mechanism. Producers and consumers can use **separate managed identities** so one principal cannot unnecessarily both send and delete all messages.

### 16.2. Shared Key and SAS

Azure Storage supports alternative authentication mechanisms depending on configuration, including account keys and Shared Access Signatures (SAS). If used:

- Never embed keys/SAS in Docker images, source code, logs, repositories, or public URLs.
- Restrict permissions, lifetime, scope, and SAS conditions as tightly as supported.
- Prefer short-lived credentials or managed identities whenever the workload supports them.
- Plan key rotation, revocation, and anomaly detection.
- Consider disabling Shared Key authorization if appropriate for the workload and all dependent apps; never change a shared account without checking impact first.

**A SAS URL is a bearer credential** within its validity window. Even with send-only permissions, leaking a SAS allows attackers to flood thousands of junk messages, driving up costs or jamming workers.

### 16.3. Network Isolation and Private DNS

A storage account can be protected using network rules and a **Private Endpoint** for the `queue` subresource. When using a private endpoint:

~~~text
API / Worker in VNet
         |
         | HTTPS + managed identity
         v
Private DNS: mystorageaccount.queue.core.windows.net
         |
         v
Private Endpoint (subresource: queue)
         |
         v
Azure Queue Storage
~~~

The associated Private DNS zone is typically `privatelink.queue.core.windows.net`. However, the hostname used by the application normally stays `<account>.queue.core.windows.net` so TLS/SNI and routing align with the service contract; DNS resolves it to a private IP when private networking is configured properly.

**A Private Endpoint for Blob does not protect the Queue endpoint.** If the system needs both Blob Storage and Queue Storage over a private network, configure **both subresources** and their respective DNS records. Also distinguish App Service outbound VNet Integration from inbound Storage Private Endpoints; placing a Private Endpoint in a subnet does not grant data permissions.

Items to test:

- DNS from the **actual worker runtime**, not just an admin workstation, resolves the queue endpoint as intended.
- Routes, NSGs, firewalls, and proxies allow HTTPS 443 from the workload to the queue.
- Storage account public network access matches policy.
- Workers hold valid Entra tokens and data-plane roles.
- Azure Monitor and operational tooling retain required access per design.
- After DNS or private endpoint changes, Pods, VMs, or App Service instances may need connection/DNS cache refreshes depending on client behavior.

### 16.4. Protecting Message Contents

Queues may hold customer IDs, order IDs, Blob paths, and correlation IDs. Ensure you:

- Send only minimal fields required to execute the job; never put passwords, access tokens, or unnecessary PII into messages.
- Use HTTPS/TLS and encryption at rest provided by Azure Storage.
- Classify data in main and poison queues, and enforce TTLs and log access controls.
- For large or sensitive payloads, store them in restricted Blob Storage and pass only a reference/ID in the message.
- Avoid logging entire bodies on parse or poison errors if they might contain sensitive data.
- Audit operator permissions for queue deletion/clearing and log administrative changes.

**Base64 is not security encryption.** It only encodes bytes as text for protocol transport. Confidential data must be protected through authorization, network controls, TLS, encryption, and proper key management.

## 17. Monitoring Queues, Workers, and Business Outcomes

A queue pipeline can report "no errors" while accumulating hundreds of thousands of delayed jobs. Monitoring must look beyond queue size to measure **wait time, processing rate, retry count, poison count, and business success rate**.

### 17.1. Observability Sources

| Source | Questions It Can Answer |
|---|---|
| **Azure Monitor metrics for Storage Queue** | Are request rate, transactions, latency, availability, or ingress/egress abnormal? |
| **Storage diagnostic/resource logs** | Which requests returned 403/404/5xx, who called them, and at what latency? |
| **Queue properties** | Is the approximate message count trending up or down? |
| **Worker application logs** | Which event IDs were received, how many retries/extensions/deletes occurred, and why did failures happen? |
| **Application Insights / OpenTelemetry** | End-to-end traces across API → queue → worker → SQL/Blob/partner API |
| **Business database** | Which jobs are Pending/Processing/Completed/Failed, and what is actual processing duration? |
| **Azure Activity Log** | Who modified the storage account, network policies, roles, or queue control plane? |
| **Azure Cost Management** | How are transactions, storage, egress, logging, and worker compute accruing costs? |

Creating a Log Analytics workspace does not automatically stream Queue Storage logs into it: you must configure diagnostic settings, workspace targets, retention, and access permissions as supported. Depending on Azure Monitor metrics, Queue service dimensions may vary; verify exact metric names and schemas before writing KQL queries or alerts.

### 17.2. Approximate Count Is Not Backlog Age

Reading the approximate count via the SDK:

~~~python
properties = queue.get_queue_properties()
print("Approximate message count:", properties.approximate_message_count)
~~~

This number is an **estimate**, may lag behind real-time changes, and does not tell you **how long the oldest message has been waiting**, how many messages are invisible, or how many finished jobs have not yet been deleted.

To measure meaningful queue latency, producers stamp UTC time and event ID; workers record receive and completion timestamps, then compute:

~~~text
Time to start = firstProcessingStartedAt - enqueuedAt
Processing duration = completedAt - firstProcessingStartedAt
End-to-end latency = completedAt - API acceptedAt
Retry count ≈ dequeueCount - 1, but interpret alongside context and send retries
~~~

**Do not blindly trust unsynchronized client clocks** when measuring SLAs. Use synchronized server/reliable log timestamps, and distinguish Queue Storage enqueue time from the upstream event creation time.

### 17.3. Minimum KPIs and Alerts

| KPI / Alert | Meaning | Response |
|---|---|---|
| **Sustained rise in approximate backlog** | Producer outpacing consumers or workers dead | Check worker health, throughput, dependencies |
| **Oldest job age exceeds SLA** | Messages waiting too long | Scale workers, inspect poison/priority |
| **Retry/dequeue count rising** | Repeated job failures or too-short visibility | Classify errors, check receipt/timeouts |
| **Poison queue growing** | Corrupt data or code regression | Alert owner, review schema, controlled replay |
| **Delete failures rising** | Stale receipts, network errors, or lost visibility | Check visibility extension and idempotency |
| **Processor success rate dropping** | Business operations failing | Check SQL/Blob/downstream and recent deploys |
| **Worker CPU/memory saturated** | Workers cannot keep up | Scale or tune batch size/concurrency |
| **Storage 403 transactions rising** | Identity/RBAC/firewall policy failure | Check tokens, scope, private network |

**Alerts must have an owner and a runbook.** For example, a "poison queue > 0" alert should explain how to inspect messages, protect PII, fix producer/worker bugs, and replay safely—not tell operators to purge the entire poison queue.

### 17.4. Structured Logs

A worker log record should include:

~~~json
{
  "eventId": "invoice-request-98421",
  "queueName": "invoice-jobs",
  "messageId": "<storage-message-id>",
  "dequeueCount": 2,
  "operation": "GenerateInvoice",
  "status": "Completed",
  "processingMs": 1842,
  "correlationId": "req-fd42b",
  "errorCategory": null
}
~~~

Never log `pop_receipt`, SAS tokens, account keys, customer details, or sensitive payloads into widely accessible log stores unnecessarily. For tracing by message ID, IDs and status fields are sufficient in most cases.

## 18. Capacity, Batch Size, and Cost

Queue Storage lets producers and workers scale independently, yet scaling up workers aggressively can bottleneck SQL, Redis, Key Vault, or partner APIs. The goal is optimizing **throughput with correctness**, not merely maximizing messages received per second.

### 18.1. Capacity Estimation

Suppose:

- Producer generates an average of **300 jobs/minute**.
- One worker processes **1 job in 2 seconds** given sufficient resources.
- One worker processes one job at a time.

Theoretical throughput of one worker:

\[
\frac{60\ \text{seconds}}{2\ \text{seconds/job}} = 30\ \text{jobs/minute}.
\]

To match average load, you need at least:

\[
\frac{300}{30} = 10\ \text{worker lanes}.
\]

However, **10 is only a theoretical minimum**; account for networking, retries, long-tail latency, database limits, and burst headroom. Load-test realistically, leave capacity headroom, and cap autoscaling to protect downstream services from overload.

### 18.2. Batch Receive Is Not a Batch Transaction

One receive call can return multiple messages, yet **each message has its own pop receipt and processing state**. Never treat a batch of 32 messages as an atomic transaction: one job in the batch may succeed and get deleted while another fails and reappears.

When a worker pulls multiple messages and processes them sequentially, ensure total batch processing time does not exceed the visibility timeout of queued messages waiting in memory. Options include smaller batches matched to concurrency, or receiving only when worker capacity is available.

### 18.3. Cost per Task

Total operational cost can include:

| Component | Cost Driver |
|---|---|
| **Queue Storage** | Stored message volume and transactions such as send/peek/receive/update/delete per pricing model |
| **Compute workers** | Azure Functions, App Service Plans, Container Apps, AKS nodes, or VMs |
| **Network** | Egress, NAT Gateway, Firewall, Private Endpoints, cross-region traffic |
| **Data services** | Azure SQL/Blob Storage/Redis and associated operations |
| **Observability** | Application Insights, Log Analytics, metrics/alerts, retention |
| **Recovery** | Poison handling, replay, backups, incident engineering effort |

Do not confuse **Hot/Cool/Archive blob tiers** with queue messages as if they were Blob Storage objects. Queues and Blobs have different data models, pricing, and features even inside the same storage account.

For cost estimates, use Azure Pricing/Cost Management based on region, redundancy, account type, and current rates; avoid hardcoding per-transaction prices in documentation since pricing changes.

### 18.4. Practical Optimizations

- Have producers send **small payloads** instead of large files.
- Reuse `QueueClient` and HTTP connections where the SDK supports it.
- Receive batches **sized to worker capacity** to avoid premature visibility expiry.
- Back off polling when the queue is empty instead of tight receive loops.
- Base visibility timeouts on real latency distributions plus bounded heartbeats.
- Use backoff/jitter retries and poison policies to prevent retry storms.
- Scale workers by backlog, queue age, and CPU while capping downstream concurrency.
- Emit metrics per queue, job type, and environment without dumping raw JSON payloads into logs.

## 19. Comparing Queue Storage, Service Bus, Event Grid, and Event Hubs

Azure messaging services solve different problems. Do not choose based solely on "they all pass messages."

| Requirement | Queue Storage | Azure Service Bus | Event Grid | Event Hubs |
|---|---|---|---|---|
| **Simple task queue** | Great fit | Fits when advanced semantics needed | Not a traditional worker queue | Not a default choice |
| **Receive, hide temporarily, then delete** | Yes, via visibility/pop receipt | Has receive modes/locks per Service Bus model | Own event delivery/retry model | Consumers read stream by offsets |
| **Native dead-letter queue** | No; app-managed poison or framework | Yes, where supported | Configurable dead-letter destination | Not a traditional queue DLQ |
| **Duplicate detection / sessions** | Designed at application layer | Native features per SKU/conditions | Not equivalent to queue sessions | Partition/consumer/event semantics |
| **Service event pub/sub** | Producer manually sends to queues | Topics/subscriptions if needed | Built specifically for event routing | High-throughput streaming to multiple consumers |
| **Retain and replay event streams** | No offset replay like event streams | Per message retention/lifecycle | Not a long-term analytical event log | Built for streaming retention/replay |
| **Strict ordering requirements** | Not strict FIFO | Session/sequence mechanisms available | No global ordering by default | In-partition ordering per stream model |

### Quick Selection Rules

- **Queue Storage:** simple background jobs, tight integration with Azure Storage, lean cost and operations; application manages retries/idempotency/poison handling.
- **Service Bus:** enterprise workflows needing **sessions, native dead-letter queues, duplicate detection, scheduled messages, or messaging transactions** per supported SKU/features.
- **Event Grid:** "an event happened" (BlobCreated, resource changed) and needs routing to an endpoint, Function, queue, or subscribing service.
- **Event Hubs:** ingesting high-volume event/telemetry streams with multiple consumer groups and offset/checkpoint replay.

For example, when a Blob is uploaded, **Event Grid** can deliver a `BlobCreated` event to **Queue Storage** or an Azure Function, and workers then process the Blob content. Services are often combined rather than forcing one product to do everything.

## 20. Troubleshooting: Sent Successfully but Unprocessed, Delete Fails, or Jobs Repeat

When a pipeline breaks, split the path into four layers: **producer send → Queue Storage store/hide → worker receive and process → worker acknowledge/delete**. Never change permissions, visibility timeouts, code, and firewall rules all at once, or root-cause isolation becomes impossible.

### 20.1. Common Symptoms Matrix

| Symptom | Possible Cause | Inspection and Fix |
|---|---|---|
| `403 AuthorizationPermissionMismatch` | Missing data-plane RBAC, wrong tenant/principal/scope | Check managed identity, Queue Data role, propagation delay, private network |
| `401 AuthenticationFailed` or token errors | Invalid/expired credentials or SDK misconfiguration | Verify `DefaultAzureCredential`, tenant, token source; never log tokens |
| Queue endpoint timeout | Firewall/DNS/Private Endpoint/route/proxy error | Test worker DNS to `<account>.queue.core.windows.net` and HTTPS 443 |
| Send fails on size | JSON or Base64 exceeds 64 KiB | Measure encoded size; offload payload to Blob Storage and send reference |
| Send fails on characters/XML | Producer uses invalid encoding | Align text Base64 policy on both sides |
| Producer sends OK, worker sees nothing | Initial visibility delay, wrong queue, invisible message, expired TTL | Verify queue/account, timestamps, delay, receive/peek semantics |
| Peek shows message, receive misses it | Another worker received it, poll race, visibility, or wrong environment | Compare logs and storage accounts; never treat peek as receive ownership |
| Worker finishes but message reappears | Forgot delete, delete failed, stale receipt, timeout too short | Audit receipt lifecycle, update/delete status, idempotency |
| Delete reports invalid pop receipt | Stale receipt after update/receive or expired message | Store latest receipt; never delete with old tokens or retry forever |
| Dequeue count climbs rapidly | Message crashes repeatedly, no backoff, short visibility | Add retry policy/poison queue, fix exception |
| Duplicate invoices/emails | Producer retried send or worker received redelivery | Use business `eventId`, unique constraint/idempotency |
| Backlog grows continuously | Under-provisioned consumers, downstream errors, workers down | Monitor queue age, worker health, DB/API bottlenecks |
| Poison queue balloons | Schema regression or permanent job errors | Classify errors, fix producer/worker, controlled replay |
| Messages expire before processing | TTL too short or severe backlog/delay | Tune SLA/TTL, alert on queue age, persist durable job state |
| Zero logs despite worker failures | Diagnostics disabled or logs dropped | Check worker stdout, App Insights, diagnostic settings, sampling |

### 20.2. Step-by-Step Runbook

**Step 1 — Verify the environment.** Gather subscription, storage account, queue name, worker instance, UTC timestamp, and business event ID. Never guess by queue name alone because dev/staging/prod may reuse queue names across different storage accounts.

**Step 2 — Inspect the producer.** Did the API record enqueue success or timeout? Did it log `eventId` and timestamp? Did retries emit duplicate messages? Does the sending identity have send permissions?

**Step 3 — Inspect the queue.** Does the queue exist, are storage network rules valid, and are TTL/delays reasonable? Is approximate count rising or falling? Use peek only for observation, not as a substitute for receive.

**Step 4 — Inspect the worker.** Is the worker running? Are CPU/memory healthy, and can it reach SQL/Blob/Key Vault? Does its SDK Base64 decode policy match the producer?

**Step 5 — Inspect visibility and receipts.** Log receive timestamps, `nextVisibleOn`, dequeue count, renewal count, and delete outcomes. If processing routinely outlasts visibility, reduce batch size or adjust heartbeats.

**Step 6 — Inspect idempotency.** Look up business job status by `eventId`. If already Completed while the message remains in the queue, perform no new side effects and safely acknowledge with the current receipt.

**Step 7 — Classify errors.** Apply backoff/jitter for transient errors; quarantine + alert for permanent errors; fix configuration for auth/network errors instead of infinite retries.

**Step 8 — Recover and verify.** Drain backlog and verify business completion counts—not just decreasing message counts. Document the incident and add tests/alerts.

### 20.3. Specific Investigation Scenario: Receipt Changed

~~~text
Worker A receives M, receipt R1, timeout 60s.
Worker A calls update visibility 120s → receives new receipt R2.
Worker A processes successfully.
Worker A calls delete using R1 → pop receipt mismatch error.
At new expiry, M may reappear.
~~~

The fix is **using R2 to delete** while the receipt is still valid; there is no need to resend the message. If the worker lost R2 and is unsure of state, let the message reappear and run the idempotent check/ack flow—never try brute-forcing tokens or clearing the queue.

### 20.4. Investigation Scenario: Slow Workers Scaled Out Further

A queue holds 100,000 jobs; the platform scales workers from 5 to 50, yet the database only handles 20 heavy concurrent connections. Scaling workers further can trigger SQL timeouts, more retries, expired visibility timeouts, and even worse queue age.

Remediation:

- Cap concurrent jobs to match database capacity.
- Scale workers cautiously based on **downstream capacity** and queue-age targets.
- Use retry backoff/circuit breakers to avoid retry storms.
- Consider batching or splitting tasks into smaller units keyed stably.
- Tune SQL indexes, transaction duration, and connection pools instead of scaling compute blindly.

## 21. Real-World Architecture: Invoice API with Two Workers and Azure SQL

**Hypothetical Context:** A company hosts its API on Azure App Service. When a user requests an invoice, the API writes metadata to Azure SQL and enqueues a Queue message. Two workers on Azure Container Apps or supported Azure Functions/VMs generate the PDF, save it to Blob Storage, and update job status.

### 21.1. Components

~~~mermaid
flowchart TB
    CLIENT[Customer] --> API[Azure App Service API]
    API --> SQL[(Azure SQL: job state + unique EventId)]
    API -->|Entra identity: Send| QUEUE[(Queue Storage: invoice-jobs)]
    QUEUE -->|Receive 90s + pop receipt| WA[Worker A]
    QUEUE -->|Receive 90s + pop receipt| WB[Worker B]
    WA -->|Idempotent update| SQL
    WB -->|Idempotent update| SQL
    WA --> BLOB[(Blob Storage: output PDF)]
    WB --> BLOB
    WA -. Delete after commit .-> QUEUE
    WB -. Delete after commit .-> QUEUE
    WA -->|After max attempts| POISON[(invoice-jobs-poison)]
    WB -->|After max attempts| POISON
    API -. Request traces .-> MON[Azure Monitor + App Insights]
    WA -. Metrics / logs .-> MON
    WB -. Metrics / logs .-> MON
~~~

Networking and identity:

- Producer only gets **send**, workers only get **receive/delete** on the main queue plus other task-specific roles.
- Workers need appropriate Azure SQL/Blob Storage permissions; avoid sharing broad account keys when managed identities are suitable.
- Queue, SQL, and Blob can be connected via private endpoints and DNS/VNet Integration per network architecture.
- Poison queue access is limited to authorized operators/workers for investigation and replay; never expose contents publicly.
- Attach `eventId` and `correlationId` to logs, and persist `Pending/Processing/Completed/Failed` states in SQL.

### 21.2. Happy Path

1. Client submits an invoice creation request with an HTTP/API-level **idempotency key**.
2. API validates, inserts a job row in SQL under a unique key, and stores large payloads in Blob if needed.
3. Publisher sends a small message containing `eventId`, `invoiceId`, `sourceBlob`, and `schemaVersion`.
4. Worker A receives message M with 90s invisibility and gets receipt R1.
5. Worker A validates the schema, looks up the job in SQL, and claims it atomically/idempotently.
6. Worker reads source data, builds the PDF, and writes it to Blob under a deterministic path like `invoices/INV-98421.pdf`, guarding concurrent writes with appropriate conditions/versioning.
7. Worker commits `Completed` and the output URL/reference to SQL.
8. Worker deletes M using R1 (or the latest receipt if renewed); the API returns Completed when queried by the client.

For long runs, the worker can renew visibility after step 5 or during PDF generation; always update the stored receipt after each renewal.

### 21.3. Worker A Crashes After Writing the PDF

~~~mermaid
sequenceDiagram
    participant Q as Queue Storage
    participant A as Worker A
    participant B as Worker B
    participant DB as Azure SQL / Blob
    A->>Q: Receive M, receipt R1
    Q-->>A: Hidden during visibility window
    A->>DB: Write PDF + commit Completed(eventId)
    DB-->>A: Success
    Note over A: Crash before Delete
    Note over Q: Visibility timeout expires
    B->>Q: Receive M again, receipt R2
    Q-->>B: Same business eventId, higher dequeue count
    B->>DB: Check Completed(eventId)
    DB-->>B: Already Completed
    B->>Q: Delete M using R2
~~~

Expected result: the system neither generates a second invoice nor sends two emails. If a downstream step sends emails, add an idempotency/outbox mechanism for email as well. Having SQL `Completed` while email is unsent must be modeled as explicit steps/states rather than letting one boolean `Completed` imply every side effect succeeded.

### 21.4. Worker A Runs Too Slowly

Suppose A takes four minutes with a 90-second receive timeout. Without visibility renewal, B can pull the same job at minute two. Even if B sees SQL `Processing`, B should not skip forever blindly: use a **processing owner/deadline/lease in the database** to distinguish whether A crashed or is still working.

Design:

- Split jobs into small checkpointed steps where feasible.
- Renew message visibility before expiry and keep the newest pop receipt.
- Maintain durable processing ownership/expiry in SQL to prevent concurrent writes.
- When ownership or renewal fails, A stops non-idempotent side effects.
- When processing limits are exceeded, mark Failed or move to poison per runbook.

### 21.5. Post-Deployment Operations

| Layer | Verification Question |
|---|---|
| API | Are `202 Accepted` rates and enqueue/SQL errors normal? |
| Queue | Are approximate backlog and oldest job age growing? |
| Workers | Jobs/minute, p95 duration, retry/dequeue count, CPU/memory? |
| SQL | Unique EventId enforcement, Pending/Completed/Failed counts, transaction failures? |
| Blob | Do files exist with expected checksums/contents and proper read permissions? |
| Security | Are managed identities/RBAC and private DNS/firewalls configured properly? |
| FinOps | What are the costs for queue transactions, worker scale, DB, logging, and network? |
| Recovery | Can poison jobs be replayed, data restored, and zero-duplicate behavior proven? |

### 21.6. Choosing a Worker Runtime

**Azure Functions Queue Storage trigger** automatically polls, receives messages, and manages retries/poison queues per extension settings—ideal for many short asynchronous tasks. **Azure Container Apps / AKS / VMs** let you run custom, long-running workers with the SDK to directly control visibility, receipts, and concurrency. Choose based on job duration, scaling requirements, networking, operational overhead, and cost.

Do not mix manual SDK receive/delete logic with the Queue-trigger runtime on the same message in a way that creates **two competing coordinators** without explicit concurrency and idempotency design.

## 22. Hands-On Exercise: Verifying Visibility Timeout and Pop Receipt

**Scenario:** You have an `invoice-jobs` queue where each message carries `eventId` and `invoiceId`. A worker processes each invoice in 75–180 seconds. The system runs three worker instances and must avoid generating two PDFs or sending two emails for the same invoice.

Complete these tasks in a **dedicated lab storage account** using test messages with no real data:

1. Create a `QueueClient` using `DefaultAzureCredential` and align Base64 encode/decode across producer and worker.
2. Create the queue if permitted, or verify it was provisioned via IaC.
3. Send a message with `time_to_live=3600` and initial `visibility_timeout=0`. Record `eventId` and message ID.
4. Call `peek_messages` before and after one receive; observe the difference in visibility and explain why peek does not grant delete rights.
5. Receive the message with a 60-second visibility timeout; record `next_visible_on` and `dequeue_count`.
6. Intentionally skip deleting the message, wait for visibility expiry, and receive it again in the lab; note the updated dequeue count.
7. Receive another message with a 90-second timeout, call update to set 120 seconds, and save the **new pop receipt**.
8. Explain why deleting with the old receipt can fail; once lab processing finishes, delete using the current receipt.
9. Simulate a worker crash after SQL commit but before delete; show how a unique constraint/idempotency key prevents duplicate invoices.
10. Design a poison policy for a malformed-schema message received 5 times.
11. Calculate worker capacity if the system receives 600 jobs/minute and one worker lane processes 20 jobs/minute, excluding overhead.
12. Explain how to scale workers without exceeding SQL connection quotas.
13. Design Azure RBAC for a send-only producer, a receive/delete consumer, and a platform team creating queues.
14. If the storage account is private-only, diagram the network path from App Service/AKS to the Queue Private Endpoint and DNS.
15. List at least five KPIs/alerts to track backlog, retries, poison messages, slow processing, and authorization errors.
16. Plan lab cleanup without deleting queues or resource groups holding shared data or resources.

### 22.1. Timeline Questions

Message M has a 1-hour TTL and an initial visibility delay of 0:

~~~text
10:00:00  Worker A receives M with 45s visibility, receipt R1
10:00:30  Worker A updates visibility to 90s, new receipt R2
10:01:00  Worker A writes result to SQL
10:01:10  Worker A calls delete using R1
10:02:00  Worker B attempts to receive M
~~~

Answer the following:

- When is M expected to become visible again if not deleted?
- Is the delete call using R1 guaranteed to succeed?
- If B receives M, what must B do before creating an invoice?
- If A successfully deleted using R2 at 10:01:15, would B still receive M under normal flow?

### 22.2. Reference Answers

**Timeline:** A updated at 10:00:30 with 90s visibility, so M can reappear **around 10:02:00** if not deleted or expired. Deleting with the **stale R1** can be rejected because the update issued **R2**. When B receives M afterward, B holds a new receipt; it must check SQL by `eventId` to see if the job is already Completed. If Completed, do not create a second invoice and delete using B's receipt. If A already deleted validly with R2 beforehand, M is no longer in the queue for B to receive in normal flow.

**Capacity:** 600 jobs/minute at 20 jobs/minute per worker lane:

\[
\frac{600}{20}=30\ \text{minimum theoretical worker lanes}.
\]

Add headroom for retries, spikes, variable processing durations, and SQL capacity. If SQL only supports 15 heavy concurrent operations, jumping to 30 lanes will cause overload; optimize jobs/DB, cap concurrency, adjust backlog SLAs, or scale downstream appropriately.

**Poison:** after policy-defined failed attempts, write sanitized metadata to the poison queue, emit an alert, and delete the original **only after the poison write is confirmed**, while supporting deduplication since those two operations are not atomic. Never clear the entire queue.

### 22.3. Mistakes Learners Should Catch Themselves

| Design Mistake | Why Is It Wrong? |
|---|---|
| Processing a 3-minute job with 30s visibility and no renewal | Can be redelivered while worker A is still running |
| Using `peek_messages` to fetch jobs then delete | Peek does not issue a pop receipt or lock the message |
| Renewing a message while keeping the old receipt | Subsequent delete/update may fail |
| Retrying the same business event with a new UUID | Prevents deduplicating by a stable business key |
| Deleting the message before writing the result | Worker crash after delete leaves no message to retry |
| Assuming SQL write alone suffices without idempotency | Crash before delete causes reprocessing/duplicates |
| Running clear queue when `dequeue_count >= 5` | Destroys all other healthy messages |
| Assuming Queue Storage has a native DLQ | Poison queues must be managed by app/framework |
| Giving producers broad Storage Account keys | Violates least privilege and expands blast radius |
| Watching queue count without measuring job age | Hides how badly processing SLAs are breached |

## 23. Operational Checklist for Producers, Consumers, and Queues

### Before Deployment

- [ ] Confirmed whether Queue Storage or Service Bus/Event Grid/Event Hubs fits requirements better.
- [ ] API/job contract includes stable `eventId`, `schemaVersion`, correlation ID, and small payload.
- [ ] Producer and consumer use identical encoding policies.
- [ ] TTL, initial delay, visibility timeout, and maximum job duration are compatible.
- [ ] Workers implement idempotency, transactions/unique keys, and checkpointing for long jobs.
- [ ] Retry policy classifies errors, applies backoff/jitter, and enforces poison thresholds.
- [ ] Poison queue, remediation runbook, and access controls for sensitive data are in place.
- [ ] Producer and consumer managed identities/RBAC follow least privilege.
- [ ] VNet, Private Endpoint, private DNS, and firewalls are reachable from the runtime.
- [ ] Monitoring tracks backlog age, retries, delete errors, poison count, worker health, and cost.
- [ ] Tested worker crashes before delete and timeout-induced duplicate deliveries.

### At Runtime

- [ ] Measure actual p50/p95/p99 processing times and tune visibility from data.
- [ ] Whenever extending visibility, always store the **latest receipt**.
- [ ] Delete only after the business outcome is durably committed.
- [ ] Keep batches small enough that messages do not expire visibility before processing.
- [ ] Never scale consumer concurrency past database or partner capacity.
- [ ] Separate transient and permanent errors; never endlessly retry 403 or schema errors.
- [ ] Ensure graceful shutdown and total processing time caps.
- [ ] Review poison queues, expired messages, and SLA breaches daily or as required.

### During an Incident

- [ ] Confirm the exact subscription, storage account, queue, and worker runtime.
- [ ] Capture event IDs, correlation IDs, timestamps, dequeue counts, and error categories.
- [ ] Check network paths and credentials before tweaking timeouts.
- [ ] Cross-check SQL/Blob state to avoid replay-induced duplicate side effects.
- [ ] Throttle or pause consumers when downstream outages cause retry storms.
- [ ] Never clear the queue or wipe the poison backlog just to clean up dashboards.
- [ ] Recover messages via an idempotent, audited procedure.
- [ ] Report root cause, impact, and preventive actions.

## 24. Lab Cleanup and Preventing Data Loss

After practicing, verify **which resources are safe to delete**. A storage account may contain not only lab queues, but also Blob containers, file shares, or queues for other apps; deleting an entire resource group can destroy unrelated resources.

### 24.1. Inventory Before Deleting

~~~bash
az account show --query "{id:id,name:name}" -o table

az resource list \
  --resource-group "$RG" \
  --output table

az storage queue list \
  --account-name "$ACCOUNT" \
  --auth-mode login \
  --output table
~~~

When checking backlogs, use queue properties/monitoring within permitted rights. **Do not treat a near-zero approximate count as proof no critical jobs remain**: messages may be invisible or producers may still be sending. Pause producers/consumers, verify business state, and confirm ownership before deletion.

### 24.2. Reference-Only Cleanup Commands

~~~bash
# ONLY for dedicated lab resources, after approval and inventory.
# Commands below are commented out—DO NOT execute blindly:

# az storage queue delete \
#   --account-name "$ACCOUNT" \
#   --name "$QUEUE" \
#   --auth-mode login

# Only delete the resource group if 100% of its resources belong to the lab.
# az group delete --name "$RG" --yes
~~~

Deleting a queue permanently drops all messages inside it, including messages hidden by visibility timeouts; data may be unrecoverable. If a queue serves production or has evidence-retention requirements, follow retention runbooks and get owner approval. Never delete a poison queue before handling remaining failed jobs.

Remember associated billable resources: Storage accounts, App Service/Functions/Container Apps/VM workers, Private Endpoints, NAT/Firewalls, Azure SQL/Blob Storage, logs, and backups. **Deleting the worker app does not stop all charges** if underlying infrastructure remains provisioned.

## 25. Key Takeaways

**Azure Queue Storage** decouples producers and workers in a simple asynchronous architecture, but safe operation requires understanding that **messages are temporarily hidden—not deleted—when received**.

Core principles:

1. **Send:** producers send small messages with `eventId`, schema version, appropriate TTL, and initial visibility delay—never large payloads or secrets.
2. **Peek vs. Receive:** peek only observes visible messages; receive hides messages and returns **message ID + pop receipt**.
3. **Visibility timeout:** if it expires before deletion, the message can be received again; it is not an exclusive lock guaranteeing exactly-once processing.
4. **Update visibility:** renew before expiry, store the **new pop receipt**, and respect TTL and service limits.
5. **Delete after commit:** delete only once the business outcome is durably persisted, using the current receipt; failed deletes must be handled idempotently upon redelivery.
6. **At-least-once / duplicates:** Queue Storage does not guarantee strict FIFO or exactly-once processing; rely on business event IDs, unique constraints, transactions/outbox, and idempotency.
7. **Retries and poison:** classify errors, apply backoff/jitter, cap attempts; Storage Queue has no native dead-letter queue.
8. **Security:** prefer Entra/managed identities, task-scoped data-plane RBAC, network rules/private endpoints for `queue`, and secret-free payloads.
9. **Operations:** track queue age, approximate backlog, dequeue count, poison queue, worker errors, delete failures, throughput, and cost.
10. **Architecture:** choose Queue Storage for simple background jobs; use Service Bus, Event Grid, or Event Hubs when different messaging semantics are required.

A queuing system is operationally complete only when you can answer **which messages were sent, who is processing them, when a message will reappear, whether the business outcome was durably persisted, and how duplicates are handled on redelivery**.
