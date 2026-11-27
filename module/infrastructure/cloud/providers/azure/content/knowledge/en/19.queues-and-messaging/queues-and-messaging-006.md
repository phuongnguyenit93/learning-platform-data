# Dead-Letter Queues and Failed-Message Handling Workflows

## 1. Why Do Queues Need a Place to Store Unprocessable Messages?

An order-processing system on Microsoft Azure might work like this: an API accepts an order, sends a message to a queue, and a worker picks up the message, validates data, writes to a database, and calls a payment service. If the database is temporarily unresponsive, the worker can retry. However, if the message contains an invalid product SKU or follows an obsolete schema, retrying hundreds of times will never make it succeed.

If an application repeatedly pulls the exact same failing message, a **poison message** scenario can occur: a message that wastes compute resources, stalls processing progress, and triggers a retry storm. Conversely, silently discarding the message destroys the business's ability to investigate and recover the transaction.

A **dead-letter queue (DLQ)** isolates messages that cannot be processed successfully under defined conditions. From there, operations teams can investigate root causes, fix bugs, and decide whether to replay or close out processing under a controlled workflow.

This lesson belongs to the **Queues and Messaging** chapter in the Microsoft Azure ecosystem learning path. It focuses on **Azure Service Bus dead-letter subqueues** and **Azure Functions Queue Storage trigger poison queues**, while connecting to Functions, App Service/AKS workers, Microsoft Entra ID, data stores, security, monitoring, and cost management.

**Key takeaway right away:** Azure Service Bus has a built-in DLQ mechanism for queues and subscriptions; Azure Queue Storage **has no equivalent broker-native DLQ**. When using the Azure Functions Queue trigger, the Functions runtime can move repeatedly failing messages to a conventionally named **poison queue**. These two mechanisms differ in behavior and operational tooling.

## 2. Learning Objectives

After this lesson, you will be able to:

1. Distinguish transient errors, permanent errors, and poison messages.
2. Explain a message's lifecycle from enqueue, receive, and retry to completion or dead-lettering.
3. Compare Azure Service Bus DLQs with Azure Functions poison queues on Azure Queue Storage.
4. Understand **Peek-Lock**, **Complete**, **Abandon**, **DeadLetter**, **delivery count**, TTL, and **MaxDeliveryCount** in Service Bus.
5. Distinguish a queue/subscription's DLQ from the **transfer dead-letter subqueue** used during forwarding.
6. Design bounded retries, exponential backoff, jitter, and idempotency.
7. Build a runbook for **detect → classify → fix root cause → replay/quarantine → verify → audit**.
8. Prevent replays from causing duplicate processing, out-of-order execution, infinite loops, or downstream overload.
9. Use Azure CLI/Portal and the Java SDK to configure and inspect DLQ metadata in authorized environments.
10. Set up monitoring, alerts, RBAC, data protection, and cost governance for failed-message workflows.

## 3. How Does a Normal Message Flow Through the System?

A common architecture:

~~~mermaid
flowchart LR
    API[Java API] --> SB[(Azure Service Bus Queue)]
    SB --> WORKER[Azure Function / AKS Worker]
    WORKER --> VALID{Processing succeeded?}
    VALID -->|Yes| DB[(Database / Storage)]
    DB --> ACK[Complete message]
    VALID -->|Transient error| RETRY[Abandon / retry per policy]
    RETRY --> SB
    VALID -->|Unprocessable error| DLQ[(Dead-letter queue)]
    DLQ --> OPS[Investigate and remediate]
~~~

Ideal workflow:

1. Producer builds a message matching an agreed contract, with a **messageId**, event type, schema version, and correlation ID.
2. Broker persists the message for asynchronous consumption.
3. Consumer receives the message using an appropriate settlement model.
4. Once processing succeeds and outcomes are durably persisted, the consumer confirms completion.
5. On transient errors, the consumer retries within safe bounds.
6. When unprocessable after the retry policy or on permanent errors, the message is quarantined.
7. Support teams have the telemetry and tooling to remediate without blocking the main queue.

A DLQ is an **evidence-preservation and recovery tool**, not a place to dump failing messages and forget them.

## 4. Distinguishing Service Bus, Queue Storage, and Event Services

| Service / Usage | Failed-Message Handling Mechanism | Key Point |
|---|---|---|
| **Azure Service Bus queue** | Built-in **dead-letter subqueue** | `MaxDeliveryCount`, TTL, and explicit dead-lettering |
| **Azure Service Bus topic subscription** | Each subscription has its own DLQ | Fan-out: one failing subscriber does not necessarily impact others |
| **Azure Queue Storage** used via SDK directly | No broker-native DLQ like Service Bus | App must implement its own error/quarantine queue if needed |
| **Azure Queue Storage** via **Azure Functions Queue trigger** | Functions runtime can move messages to **`<queue-name>-poison`** after dequeue limit | Behavior of the Functions extension, not native Storage DLQ |
| **Azure Event Grid** | Supports dead-lettering to a supported destination, often Blob Storage, when configured | Not a Service Bus DLQ by default |
| **Azure Event Hubs** | No built-in dead-letter subqueue equivalent to Service Bus | Consumers implement quarantine/checkpoint/replay in streaming architecture |

**Never make a blanket statement like "Azure Queues automatically have a DLQ" for every service.** Before writing a runbook, document the exact broker name, entity type, trigger extension, retry policy, and the actual destination holding failed messages.

## 5. What Is an Azure Service Bus DLQ?

Azure Service Bus provides a **dead-letter subqueue** attached to queues and topic subscriptions. It is not a standalone Azure queue resource that you create manually. Messages move from the main delivery path to the subqueue when the broker or application triggers a dead-letter condition.

Queue example:

~~~text
Service Bus namespace
└── queue: orders
    ├── Active messages
    └── Dead-letter subqueue
~~~

Topic example:

~~~text
Service Bus namespace
└── topic: order-events
    ├── subscription: accounting
    │   ├── Active messages
    │   └── Dead-letter subqueue
    └── subscription: notifications
        ├── Active messages
        └── Dead-letter subqueue
~~~

This structure gives each consumer group (via its subscription) an isolated failure log. A message can succeed in the **notifications** subscription while being dead-lettered in **accounting** due to different business rules.

### 5.1. What an Azure Service Bus DLQ Does NOT Do Automatically

- Does not understand why a message failed business validation.
- Does not repair data or transform schemas.
- Does not auto-retry messages from the DLQ back to the active queue after a delay.
- Does not generate a root-cause categorization dashboard on its own.
- Does not guarantee a replay will not create duplicate transactions.
- Does not automatically delete failed messages after a set number of days unless configured/handled.

Therefore, enabling a DLQ without a runbook and alerts can still leave thousands of unresolved transactions piling up.

## 6. When Do Messages Enter a Service Bus DLQ?

Common causes:

| Cause | Mechanism | Investigation Direction |
|---|---|---|
| **`MaxDeliveryCountExceeded`** | Delivery count exceeds entity limit per broker mechanics | Consumer crashes, repeated abandons, or lock expirations |
| **`TTLExpiredException`** or matching expiration reason | Message TTL expires when dead-letter on expiration is enabled | Overload, backlog, or TTL set too short |
| **Explicit dead-letter** | Application calls dead-letter API upon detecting an unprocessable condition | Malformed payload, contract violation, missing data |
| **Filter evaluation error** (certain subscription settings) | Broker fails evaluating a filter per configured feature | Topic subscription rules |
| **Forwarding/transfer failure** | Failures during auto-forwarding can route to a transfer DLQ | Forward destination, quotas, link config |

Not every consumer exception immediately sends a message to the DLQ. Under **Peek-Lock**, if a consumer abandons or loses a lock, the message can be redelivered. Automatic dead-lettering occurs only once broker-defined conditions are met.

### 6.1. MaxDeliveryCount

A Service Bus queue/subscription configures **`MaxDeliveryCount`**, capping how many times the broker delivers a message before dead-lettering per policy. Labs often use **5** for easy observation.

This does not mean a message is guaranteed to invoke your handler exactly 5 times: crashes, lock renewals, prefetching, client behavior, and settlement timing all influence the real trace.

### 6.2. TTL Expiration

**Time-to-live (TTL)** defines how long a message stays valid per the broker. On entities with dead-letter-on-expiration enabled, expired messages can appear in the DLQ. If disabled, expired messages are discarded without entering the DLQ per entity behavior.

Do not set TTL too short when legitimate backlogs can occur; equally, do not retain transactional messages indefinitely without a clear data policy.

### 6.3. Explicit Dead-Letter

The application actively calls dead-letter when data or conditions are **unrecoverable by normal retries**—for example, an unsupported schema or a verified invalid tenant reference.

Always supply a clear **dead-letter reason** and a concise **description** free of sensitive data.

## 7. Peek-Lock, Complete, Abandon, and DeadLetter

Service Bus supports receive modes such as **Peek-Lock** and **Receive-and-Delete**.

### 7.1. Peek-Lock

When receiving in Peek-Lock mode:

1. The consumer acquires the message with a time-bounded lock.
2. The broker does not immediately delete the message.
3. The consumer processes it and performs settlement.
4. On success, **`Complete`** removes the message from the delivery stream.
5. If the consumer calls **`Abandon`** or the lock expires, the message becomes eligible for redelivery.
6. If the consumer calls **`DeadLetter`**, the message moves to the DLQ.
7. If redeliveries exceed `MaxDeliveryCount`, the broker can dead-letter it automatically.

~~~mermaid
flowchart TD
    READY[Active message] --> RECEIVE[Receive with Peek-Lock]
    RECEIVE --> WORK{Process}
    WORK -->|Success| COMPLETE[Complete]
    WORK -->|Retryable error| ABANDON[Abandon / lock expires]
    ABANDON --> READY
    WORK -->|Permanent error| DEAD[Explicit DeadLetter]
    READY --> CHECK{Delivery count exceeded limit?}
    CHECK -->|Yes| DLQ[Dead-letter subqueue]
    DEAD --> DLQ
~~~

### 7.2. Receive-and-Delete

With Receive-and-Delete, the broker removes the message upon delivery without waiting for `Complete`. If the consumer crashes right after receiving, data can be lost. This mode is unsuitable whenever business logic requires retries or dead-lettering after processing failures.

**For payments, orders, invoicing, or critical jobs, prefer a recoverable settlement mode** and design idempotency to handle redeliveries.

### 7.3. Lock Duration and Renewal

Long processing can expire the lock before `Complete`, causing another worker to pick up the message. The Service Bus SDK supports auto-renewing locks under supported configurations.

Do not treat lock renewal as infinite. For long or multi-step jobs, split the work, use checkpoints, or hand off to an appropriate workflow orchestrator.

## 8. Dead-Letter Subqueue vs. Transfer DLQ Are Not the Same

In Service Bus:

- The **normal dead-letter subqueue** holds failed messages for a queue/subscription: max delivery, TTL, or application dead-lettering.
- The **transfer dead-letter subqueue** relates to forwarding/transfer failures when using auto-forwarding or transfers—do not lump these together with consumer business errors.

In a namespace using auto-forwarding, runbooks should distinguish:

~~~text
Message failed business validation
  -> Receiving entity's DLQ

Message failed to forward to destination
  -> Investigate transfer DLQ / forwarding path
~~~

If the transfer DLQ grows, fixing business handlers at the destination will not solve the problem. Check the forward target, permissions, forwarding config, hop/size/quota limits, and entity state.

## 9. When Does Azure Queue Storage Have a Poison Queue?

**Azure Queue Storage itself does not provide a dead-letter subqueue like Service Bus.** It stores messages, supports receive, visibility timeouts, dequeue counts, and deletion on completion. Apps using the SDK directly must build their own quarantine logic if they want a separate store for failing messages.

When processing Azure Queue Storage via the **Azure Functions Queue trigger**, the Functions runtime extension implements:

1. Reading messages from the input queue.
2. Invoking the function.
3. On failure, retrying the message per configuration.
4. Once **`maxDequeueCount`** is exceeded, moving the message into a conventionally named queue: **`<original-queue-name>-poison`**.

Example:

~~~text
Azure Storage account
├── queue: orders
└── queue: orders-poison
~~~

**`orders-poison`** is not a Service Bus DLQ. It is a regular Azure Storage queue used by the Functions runtime by convention. Your team must still monitor, inspect, classify, and decide how to handle those messages.

### 9.1. Sample host.json for Queue Trigger

~~~json
{
  "version": "2.0",
  "extensions": {
    "queues": {
      "batchSize": 4,
      "newBatchThreshold": 2,
      "visibilityTimeout": "00:00:30",
      "maxDequeueCount": 5
    }
  }
}
~~~

In a compatible Functions Queue extension:

- **`maxDequeueCount`** limits receive/execution attempts before moving to the poison queue.
- **`visibilityTimeout`** governs the delay before a failed message reappears per runtime mechanics.
- **`batchSize`/`newBatchThreshold`** control fetching and parallel processing, not directly retry counts.

When **dynamic concurrency** is enabled or across extension versions, concurrency settings can behave differently. Check the documentation for your exact extension version.

### 9.2. Critical Operational Difference

You cannot use the Service Bus SDK's **`SubQueue.DEAD_LETTER_QUEUE`** to read Azure Storage's **`orders-poison`**. For a Storage poison queue, use Azure Queue Storage APIs/SDKs or Azure Portal/Storage Explorer with Storage permissions.

## 10. Why Are Repeatedly Failing Messages Called Poison Messages?

A poison message is one that causes consumers to repeatedly fail or make zero progress under current processing conditions.

Examples:

- Unparseable JSON.
- Legacy schema missing required fields.
- Referenced ID that does not exist and will never appear.
- Malformed string that throws a parser exception.
- Payload exceeding application processing bounds.
- Message requesting an action forbidden to that user/tenant.
- Handler bug that always crashes on a specific event type.
- Downstream dependency that never becomes ready within policy bounds.

**A message failing on its first attempt is not automatically poison.** Database timeouts or brief network blips can succeed on retry. Classify the root cause before concluding it is poison.

### 10.1. How Poison Messages Stall a System

If a consumer keeps pulling message A, failing, immediately receiving it again, and looping infinitely, it burns CPU/requests, inflates bills, and delays healthy messages behind it.

A DLQ pulls A out of the main lane so healthy messages keep flowing, while a runbook ensures A is not forgotten.

## 11. Classifying Errors: Transient, Permanent, and Unknown

| Error Category | Examples | Sensible Policy |
|---|---|---|
| **Transient** | Brief timeout, HTTP 503, DB failover, temporary rate limit | Bounded retry with backoff/jitter |
| **Permanent / data** | Invalid JSON, unsupported schema, business-rule violation | Dead-letter or quarantine for investigation |
| **Permanent / authorization** | Unauthorized due to genuinely invalid tenant/data | Do not retry forever; verify permissions and close/quarantine |
| **Infrastructure / config** | Missing Key Vault permission, bad DNS, wrong connection setting | Alert and fix configuration; controlled retries |
| **Unknown** | Unclassified exception | Small retry budget, telemetry, quarantine if unresolved |
| **Processing conflict** | Order already processed, duplicate key, data contention | Check idempotency; `Complete` if already done instead of treating as error |

Avoid rigid rules like "dead-letter all 4xx, retry all 5xx" because API contracts vary. For example, HTTP 409 can mean an operation already succeeded idempotently, or a conflict needing retry with a fresh version.

### 11.1. Distinguish Message-Level Errors from System-Wide Errors

If a Function App loses database access, **every message** will fail. Bulk dead-lettering everything complicates recovery without fixing the root cause. Trigger alerts, throttle throughput, trip circuit breakers, or pause consumers per runbook.

### 11.2. Watch Out for Malicious Payloads

A message could be crafted to exploit parsers, exhaust memory, or inject payloads. Never replay unvalidated payloads from untrusted sources; inspect them in safe sandboxes with strict size limits.

## 12. Good Retry Policies Must Be Bounded

For transient errors, retries help when failures can self-recover. Yet unbounded retries amplify load and cost.

A backoff model:

\[
d_n = \min(d_{\max}, d_0 \times 2^{n-1})
\]

Where \(d_0\) is the initial delay, \(d_{\max}\) is the maximum cap, and \(n\) is the retry attempt. Add **jitter** so multiple consumers do not retry in lockstep.

Example schedule:

| Attempt | Wait Before Retry (Illustrative) |
|---|---:|
| 1 | 0 seconds |
| 2 | ~2 seconds |
| 3 | ~4 seconds |
| 4 | ~8 seconds |
| 5 | ~16 seconds |

This is illustrative only. With Service Bus Peek-Lock, **`Abandon`** can make a message available again right away per broker behavior rather than waiting for your calculated backoff. To enforce delays between attempts, use scheduled retries or an application scheduling pattern—never use `Thread.sleep` inside handlers to simulate long backoffs.

### 12.1. Multi-Layer Retries Multiply Attempts

If the SDK retries 3 times, the handler retries 4 times, and the broker redelivers 5 times, downstream systems can receive a huge multiplier of calls.

Define a **total retry budget**, assigning clearly which layer owns retries and capping each layer.

### 12.2. Retries Should Not Outlive Business Value

An order command valid for only 5 minutes may be meaningless to retry 2 hours later. TTLs and retry windows must reflect business validity.

## 13. Business State Machine for Failed Messages

Do not rely solely on broker states. A business workflow often needs its own operational states:

~~~text
RECEIVED
  -> PROCESSING
  -> COMPLETED

PROCESSING
  -> RETRY_SCHEDULED
  -> FAILED_PERMANENT
  -> QUARANTINED
  -> UNDER_INVESTIGATION
  -> READY_TO_REPLAY
  -> REPLAYED
  -> VERIFIED
  -> CLOSED
~~~

These states can live in an audit/operations table or ticketing system, independent of the broker.

A message marked **REPLAYED** does not mean the business outcome is **COMPLETED**. Track the new execution until real completion is confirmed.

### 13.1. Separate Technical State from Business Outcome

Example:

- Service Bus DLQ count drops from 10 to 9.
- The message is sent back to the active queue.
- The worker fails again and sends it right back to the DLQ.

A dashboard tracking only DLQ count might falsely imply recovery. Cross-check business status, correlation IDs, and replay history.

## 14. Designing Message Envelopes for Easier Investigation

Messages should carry metadata for tracing:

~~~json
{
  "eventType": "OrderSubmitted",
  "schemaVersion": 2,
  "eventId": "evt-demo-001",
  "correlationId": "corr-demo-001",
  "occurredAt": "2026-11-20T08:30:00Z",
  "tenantId": "tenant-demo",
  "data": {
    "orderId": "ORD-1001",
    "customerId": "C-50",
    "amount": 125000
  }
}
~~~

This example uses mock data. In Azure Service Bus, fields like **`MessageId`**, **`CorrelationId`**, **`Subject`**, and **`ApplicationProperties`** live in dedicated message metadata rather than needing duplication inside the JSON body.

### 14.1. Fields Worth Preserving

- **`MessageId`/`eventId`**: identifies the message/business event.
- **`CorrelationId`/`traceId`**: links flows from API through consumers.
- **`SchemaVersion`/`eventType`**: clarifies parser and contract expectations.
- **Enqueued time**: reveals backlogs and latency.
- **Delivery count**: shows how many times the broker delivered the message.
- **`DeadLetterReason`**: short, standardized classification code.
- **`DeadLetterErrorDescription`**: sanitized error description.
- **Source entity/subscription**: where the message originated.
- **Producer version / consumer version** if tracked consistently.

### 14.2. Data That Must Stay Out of Reason/Description

Never store access tokens, connection strings, passwords, card numbers, full emails, or sensitive user content in error fields. These fields surface in operations tools, logs, and support tickets.

### 14.3. Schema Versions and Compatibility

A common cause of DLQ spikes is a producer shipping a new schema before consumers update. Proper versioning and backward/forward compatibility prevent widespread parsing failures.

## 15. DeadLetterReason and DeadLetterErrorDescription in Service Bus

When dead-lettering manually, use a **controlled set of reason codes**.

Examples:

| Reason Code | When to Use | Owning Team |
|---|---|---|
| **`InvalidSchema`** | Malformed JSON/schema or unsupported version | Producer/consumer team |
| **`BusinessRuleRejected`** | Data violates verified business rules | Business/consumer team |
| **`UnknownEntity`** | Required reference ID not found | Data owner |
| **`DependencyUnavailable`** | Retry budget exhausted while downstream unavailable | Platform/dependency owner |
| **`UnauthorizedTenant`** | Tenant unauthorized to perform action | Security/business |
| **`UnclassifiedFailure`** | Root cause not yet identified | On-call team |

Never dump an entire stack trace into the reason field. Stack traces are verbose, may expose sensitive details, and change across builds—making root-cause aggregation harder.

Example of useful information to store:

~~~text
DeadLetterReason: InvalidSchema
DeadLetterErrorDescription:
  EventType=OrderSubmitted; SchemaVersion=9 is not supported;
  ContractVersionSupported=1..2; IncidentRef=INC-1042
~~~

When a reason is generated automatically by the broker, preserve the original metadata to diagnose the fault. Never overwrite everything claiming all dead-lettered messages were invalid application payloads.

## 16. Configuring a Service Bus Queue in Azure CLI

The following example is for an authorized lab environment only, requiring an Azure subscription, permissions to create resource groups/Service Bus, and a unique namespace name.

~~~bash
az login
az account set --subscription "<subscription-id>"

az group create \
  --name rg-messaging-lab \
  --location southeastasia

az servicebus namespace create \
  --resource-group rg-messaging-lab \
  --name sb-messaging-lab-unique \
  --location southeastasia \
  --sku Standard
~~~

Create a queue with a low `MaxDeliveryCount` for testing:

~~~bash
az servicebus queue create \
  --resource-group rg-messaging-lab \
  --namespace-name sb-messaging-lab-unique \
  --name orders \
  --max-delivery-count 5 \
  --enable-dead-lettering-on-message-expiration true
~~~

**Notes:**

- **`sb-messaging-lab-unique`** is a placeholder; the namespace name must be valid and globally available.
- Verify CLI flags and features against your installed Azure CLI/extension version. If a flag is unsupported, check `--help` for your environment rather than switching queue types or bypassing policies.
- **`MaxDeliveryCount=5`** makes lab behavior easy to observe and is not necessarily optimal for production.
- Enabling dead-letter-on-expiration moves expired messages to the DLQ via broker mechanics, though expired messages still need an operational workflow rather than being treated automatically as real-time business events.

Inspect the queue:

~~~bash
az servicebus queue show \
  --resource-group rg-messaging-lab \
  --namespace-name sb-messaging-lab-unique \
  --name orders \
  --output json
~~~

Review properties such as **`maxDeliveryCount`**, **`deadLetteringOnMessageExpiration`**, **`countDetails`**, and other fields available in the output.

## 17. Inspecting a DLQ via the Azure Portal

A non-destructive inspection workflow:

1. Open **Azure Portal → Service Bus namespaces**.
2. Select your test namespace.
3. Open **Queues** or **Topics → Subscriptions**.
4. Select the entity under investigation.
5. Check **Active messages**, **Dead-lettered messages**, and displayed monitoring charts.
6. Open **Service Bus Explorer** in the Portal if features and permissions allow.
7. Select the target **dead-letter subqueue** on the queue or subscription.
8. Use **Peek** to inspect metadata and authorized fields under data controls.
9. Record `messageId`, `reason`, `deliveryCount`, enqueue time, and `correlationId`.
10. **Do not click Complete/Delete/Resubmit** simply because messages look old; obtain approval and evaluate first.

Menu labels and Service Bus Explorer capabilities can evolve. If an account only holds metadata read access and lacks data-plane rights to read message bodies, request proper RBAC via workflow rather than taking shortcuts with privileged connection strings.

### 17.1. Peek vs. Receive

**Peek** reads for inspection without acquiring a lock or triggering settlement—ideal for investigation. **Receive** in Peek-Lock pulls the message for consumer processing/settlement, affecting delivery/lock state.

For production DLQs, always prefer **Peek** when your goal is pure observation.

## 18. Java SDK: Non-Destructive Reading of DLQ Metadata

This example uses the Azure SDK for Java and **`DefaultAzureCredential`** to inspect message metadata from the **`orders`** queue's DLQ. Your project needs compatible versions of **`azure-messaging-servicebus`** and **`azure-identity`**.

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusReceiverClient;
import com.azure.messaging.servicebus.models.ServiceBusReceiveMode;
import com.azure.messaging.servicebus.models.SubQueue;
import com.azure.messaging.servicebus.models.ServiceBusReceivedMessage;

public class InspectDeadLetters {
    public static void main(String[] args) {
        String namespace = "sb-messaging-lab-unique.servicebus.windows.net";

        try (ServiceBusReceiverClient receiver =
                 new ServiceBusClientBuilder()
                     .credential(
                         namespace,
                         new DefaultAzureCredentialBuilder().build())
                     .receiver()
                     .queueName("orders")
                     .subQueue(SubQueue.DEAD_LETTER_QUEUE)
                     .receiveMode(ServiceBusReceiveMode.PEEK_LOCK)
                     .buildClient()) {

            for (ServiceBusReceivedMessage message :
                    receiver.peekMessages(10)) {
                System.out.println("MessageId: " + message.getMessageId());
                System.out.println("Reason: " + message.getDeadLetterReason());
                System.out.println("Description: "
                        + message.getDeadLetterErrorDescription());
                System.out.println("DeliveryCount: "
                        + message.getDeliveryCount());
            }
        }
    }
}
~~~

Explanation:

- **`credential(namespace, credential)`** authenticates using Microsoft Entra identity per SDK mechanics.
- **`SubQueue.DEAD_LETTER_QUEUE`** targets the Service Bus dead-letter subqueue.
- **`peekMessages(10)`** only views messages—it neither `Complete`s nor deletes them.
- Only metadata is printed for illustration; raw bodies and secrets are omitted.
- The caller needs appropriate **data-plane receive/read permissions** on the entity. Azure ARM Reader alone does not grant read access to message contents.

**Version note:** verify exact API and enum names against your dependency version. This targets the modern Azure Service Bus Java SDK, not legacy SDKs.

### 18.1. Why Not Use Connection Strings in the Main Example?

SAS connection strings contain sensitive credentials easily leaked into logs or source control. In Azure, prefer managed identities and scoped role assignments; locally, use Azure CLI sign-in via `DefaultAzureCredential` per setup.

If SAS must be used in testing, store it in a secret store and keep it out of Git and chat.

## 19. Java SDK: Explicit Dead-Lettering on Bad Data

A Peek-Lock consumer can explicitly move unrecoverable messages to the DLQ.

Snippet illustrating **only the settlement portion after receiving a message**:

~~~java
import com.azure.messaging.servicebus.ServiceBusReceiverClient;
import com.azure.messaging.servicebus.models.DeadLetterOptions;
import com.azure.messaging.servicebus.models.ServiceBusReceivedMessage;

public final class MessageSettlement {
    private MessageSettlement() {}

    public static void rejectInvalidPayload(
            ServiceBusReceiverClient receiver,
            ServiceBusReceivedMessage message) {
        DeadLetterOptions options = new DeadLetterOptions()
            .setDeadLetterReason("InvalidSchema")
            .setDeadLetterErrorDescription(
                "Message body does not match supported schema version");

        receiver.deadLetter(message, options);
    }
}
~~~

Prerequisites:

- Receiver fetched the message in **Peek-Lock** mode and still holds a valid lock.
- Application verified the error is permanent or policy requires quarantine.
- Do not call `Complete` after `deadLetter` succeeds.
- If the `deadLetter` API fails due to lock loss or broker errors, log and handle the exception properly—never assume the message reached the DLQ.
- Never put the full message body into the error description.

If an Azure Functions Service Bus trigger manages settlement automatically for your consumer, **do not blindly copy this snippet**. Check your Functions SDK version's trigger/binding behavior and manual settlement support before calling complete/dead-letter.

## 20. Azure Functions Service Bus Trigger and DLQ

Azure Functions can use a **Service Bus trigger** to receive messages. When an invocation throws, abandon/retry/lock-renewal behavior is governed by the runtime, extension, and handler configuration. Once delivery count exceeds the entity's limit, Service Bus can move the message to the DLQ.

Minimal Java Functions trigger example:

~~~java
import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.annotation.FunctionName;
import com.microsoft.azure.functions.annotation.ServiceBusQueueTrigger;

public class OrdersConsumer {
    @FunctionName("processOrder")
    public void run(
        @ServiceBusQueueTrigger(
            name = "message",
            queueName = "orders",
            connection = "ServiceBusConnection")
        String message,
        ExecutionContext context) {

        context.getLogger().info("Received order message");
        // Validate and run business logic.
        // When throwing an exception, settlement/retry depends on the extension.
    }
}
~~~

**`ServiceBusConnection`** is only an app setting name. In Azure Functions/extension versions supporting identity-based connections, configuration can use matching app-setting prefixes instead of a SAS connection string; confirm runtime, extension, and SDK support.

### 20.1. Does Throwing an Exception Always Dead-Letter Immediately?

No. A function failure typically results in abandoning the message or letting its lock expire so the broker can redeliver it. Only once conditions like **`MaxDeliveryCountExceeded`** trigger—or the app explicitly dead-letters via a supported API—does the message enter the DLQ.

### 20.2. Manual Settlement

Some bindings/runtimes/extensions expose message objects alongside **message actions** to manually call Complete/Abandon/DeadLetter. Availability depends on language and version. When using manual settlement, disable or adjust auto-complete per documentation to prevent double settlement.

### 20.3. Do Not Blindly Retry Across Three Layers at Once

The Azure SDK, Functions runtime, and Service Bus broker can all participate in retries. Uncoordinated retries across code, `host.json`, and broker redelivery can produce excessive attempts.

## 21. Azure Functions Queue Trigger and Poison Messages

With an Azure Queue Storage trigger in Functions, after `maxDequeueCount` failed dequeues, the runtime moves the message to **`<queue-name>-poison`**.

Sample Java handler:

~~~java
import com.microsoft.azure.functions.ExecutionContext;
import com.microsoft.azure.functions.annotation.FunctionName;
import com.microsoft.azure.functions.annotation.QueueTrigger;

public class QueueOrderConsumer {
    @FunctionName("processStorageOrder")
    public void run(
        @QueueTrigger(
            name = "message",
            queueName = "orders",
            connection = "AzureWebJobsStorage")
        String message,
        ExecutionContext context) {

        context.getLogger().info("Queue message received");
        // When processing fails, throw an exception per contract.
    }
}
~~~

Notes:

- This is an **Azure Storage Queue** trigger, not a Service Bus trigger.
- **`orders-poison`** is a real queue in the Storage account created by runtime convention, not a Service Bus subqueue.
- Messages are moved to the poison queue by extension behavior; metadata preservation differs from Service Bus DLQs.
- If using the Queue Storage SDK directly **without the Functions trigger**, you must build poison/quarantine handling yourself.
- Do not apply identical deletion workflows and permissions to Service Bus and Storage Queue—they are distinct services.

### 21.1. Poison Queues Have Their Own Lifecycle

A poison queue keeps growing if unmonitored. It is also subject to Azure Storage Queue TTLs, permissions, and limits. Never assume entering a poison queue means permanent retention or backup.

## 22. Failed-Message Handling Workflow: Eight Steps

A reliable runbook follows this sequence:

~~~mermaid
flowchart TD
    ALERT[1. Detect DLQ growth] --> FREEZE[2. Assess blast radius / stop spread]
    FREEZE --> PEEK[3. Peek, safely gather metadata]
    PEEK --> CLASS[4. Classify errors]
    CLASS --> FIX[5. Fix root cause / data / code]
    FIX --> APPROVE[6. Approve remediation plan]
    APPROVE --> ACTION{Decision}
    ACTION -->|Replay| REPLAY[7a. Rate-limited replay]
    ACTION -->|Quarantine| HOLD[7b. Hold for further investigation]
    ACTION -->|Close| CLOSE[7c. Close per policy]
    REPLAY --> VERIFY[8. Verify outcome and audit]
    HOLD --> VERIFY
    CLOSE --> VERIFY
~~~

### Step 1 — Detect

Alert on abnormal DLQ growth, rising age, or incomplete business operations exceeding SLOs. Do not watch absolute counts alone.

### Step 2 — Assess Scope

Determine whether failures affect one message, a single partition/subscription, a specific producer version, or the whole system. During widespread outages, stop generating more poison messages by fixing the producer/consumer or pausing intake per runbook rather than deleting data.

### Step 3 — Non-Destructive Metadata Inspection

Prefer Peek; record correlation ID, reason, `eventType`, schema version, source, and timestamp. Never paste customer data into public tickets.

### Step 4 — Classify

Distinguish transient, permanent, configuration, data, duplicate, or unknown errors. Separate sender faults from receiver faults.

### Step 5 — Fix Root Cause

Fix handler bugs, schema compatibility, permissions, DNS, configuration, or missing reference data. Replaying before fixing the root cause simply loops messages back into the DLQ.

### Step 6 — Approve

Explicitly decide which messages are eligible for replay, whether payloads need transformation, who approves, and how side effects like payments or invoicing are reconciled.

### Step 7 — Replay / Quarantine / Close

Execute in small, rate-limited batches with an immediate stop trigger if errors rise. For unrecoverable errors, archive audit records and close per retention/compliance policy.

### Step 8 — Verify

Reconcile real business outcomes, not just DLQ counts. Record timestamp, operator, source message ID, target message ID, and outcome.

## 23. What Must Be Checked Before Replaying?

Minimum checklist:

- Which entity and environment does the message belong to: dev/staging/prod?
- Does the message still carry business value, or has it expired?
- Did another consumer already process it successfully?
- Did any payment, email, inventory, or workflow side effect already happen?
- Does the current consumer version still support the source schema?
- Does the message depend on processing order or Service Bus sessions?
- Do referenced database IDs still exist in the right tenant?
- Has the root cause been confirmed fixed?
- Is the target queue/topic/subscription accurate?
- Should replay keep the `MessageId`/`CorrelationId` or generate a new `MessageId`?
- Could Service Bus duplicate detection drop the resent message?
- Are budget, rate limits, alerts, and rollback/recovery plans ready?
- Who approves, who executes, and who verifies?

**Never replay thousands of messages just because one sample message succeeded.** Group by reason, schema version, timestamp, tenant, and risk level; test a small batch first.

## 24. Safe Replay: Why Send First, Complete After?

A standard replay algorithm for a Service Bus DLQ:

1. Receive message from DLQ using Peek-Lock.
2. Validate metadata and confirm replay eligibility.
3. Build a **new message** for the target queue/topic with valid body and application properties.
4. Attach trace metadata such as `originalMessageId` and `replayAttempt`.
5. Send the new message and await broker acknowledgment.
6. **Only then `Complete`** the locked source message in the DLQ.
7. Write audit logs and track the new message to its business outcome.

~~~mermaid
sequenceDiagram
    participant O as Replay worker
    participant DL as Service Bus DLQ
    participant Q as Active Queue
    participant A as Audit Store
    O->>DL: Receive message (Peek-Lock)
    DL-->>O: Original message + metadata
    O->>O: Validate policy, idempotency, target
    O->>Q: Send new message
    Q-->>O: Send acknowledged
    O->>DL: Complete original DLQ message
    O->>A: Record replay result
~~~

**Never delete or `Complete` the source message before the send succeeds.** If sending fails after the source was completed, your recovery copy is gone.

### 24.1. Yet Send-First, Complete-After Is Still Not Exactly-Once

An important failure window:

~~~text
Send to active queue succeeds
   -> Process crashes before Completing DLQ
   -> Original remains in DLQ
   -> Re-running replay may send a second copy
~~~

Therefore, consumer-layer idempotency or durable audit/coordination state is mandatory. Never claim a simple replay script guarantees end-to-end exactly-once execution.

### 24.2. Do Not Blindly Copy All System Properties

When constructing the new message, selectively set valid properties: `MessageId`, `CorrelationId`, `Subject`, application properties, and TTL/session per contract. Metadata like `DeliveryCount`, `LockToken`, `EnqueuedTime`, or `DeadLetterReason` belong to the prior delivery and cannot all be copied onto a newly sent message.

### 24.3. Duplicate Detection Impacts Replay

If the target entity has duplicate detection enabled, resending the exact same `MessageId` inside the deduplication window may be silently dropped by the broker. Yet changing `MessageId` arbitrarily can break consumers relying on it for deduplication.

Explicitly separate:

- **Business idempotency key** preserved across replays;
- **Transport message ID** respecting broker deduplication policy;
- **Replay attempt ID** for auditing.

## 25. Replay Tools Should Have Dry-Run and Rate Limiting

A production replay tool should provide:

| Capability | Purpose |
|---|---|
| **List/Peek** | Inspect messages and metadata only |
| **Filter** | Select by reason, event type, time range, or tenant |
| **Dry-run** | Print the plan without sending or completing |
| **Approve** | Record approver and ticket reference |
| **Batch size** | Cap messages per run |
| **Rate limit** | Protect consumers and downstream systems from overload |
| **Idempotency** | Prevent duplicate transactions |
| **Audit** | Log source/target IDs and outcomes |
| **Pause/Stop** | Halt immediately if errors or latency spike |
| **Resume checkpoint** | Resume cleanly if the replay tool stops |
| **Verification** | Reconcile business outcomes |

Illustrative pseudocode (**not directly runnable**):

~~~text
for each selected DLQ message:
    if !policyAllows(message):
        quarantine(message)
        continue

    if businessAlreadyCompleted(message.businessKey):
        closeAccordingToPolicy(message)
        continue

    newMessage = reconstructSafely(message)
    newMessage.replayAttempt = message.replayAttempt + 1
    newMessage.correlationId = message.correlationId

    sendAndAwaitAcknowledgement(targetEntity, newMessage)
    completeOriginalDlqMessage(message)
    writeAuditRecord(message, newMessage)
~~~

This pattern does not by itself make broker operations and audit database writes atomic. Critical systems add transactional outbox/inbox tables, idempotent state transitions, or broker transactions within supported limits.

**Dry-run must never send messages or complete sources.** A "Preview" button that still acknowledges messages is a severe design bug.

## 26. Idempotency: More Important Than Retry Counts

In message-driven systems, this can happen:

1. Worker writes the order to the database successfully.
2. Worker dies before calling `Complete`.
3. Broker redelivers the message.
4. Worker processes it again; without checks, it creates a duplicate order or double charge.

**Idempotency** ensures processing the same event multiple times never corrupts the business outcome.

### 26.1. Use a Business Key

Order workflow example:

~~~text
BusinessOperationId = "CreateInvoice:ORD-1001"
~~~

In the database, enforce a unique constraint or inbox table on `BusinessOperationId`. When a duplicate arrives:

- If already completed, acknowledge the message without recreating the invoice.
- If currently in progress, use proper locking/transactions to prevent races.
- If not yet processed, execute inside an atomic transaction and record completion.

### 26.2. Do Not Rely Only on Service Bus Duplicate Detection

Broker duplicate detection governs **message ingestion into the entity** over a configured window; it does not replace consumer-side handling of redeliveries or multi-day replays.

### 26.3. External Side Effects Require Special Care

Payment charges, emails, and inventory updates are hard to reverse cleanly. Use partner API idempotency tokens or reconcile state before replaying. Often the right decision is **closing the dead-lettered message after verifying business completion**, rather than resending it.

## 27. Message Ordering, Sessions, and Replay

Service Bus supports **sessions** when grouped, ordered processing per session is required. Yet when one failing message lands in the DLQ, subsequent messages may continue processing depending on how consumers and session logic are built.

### 27.1. Risk of Out-of-Order Replay

Consider the event sequence:

~~~text
OrderCreated -> OrderPaid -> OrderCancelled
~~~

If `OrderPaid` went to the DLQ while `OrderCancelled` already processed, replaying `OrderPaid` later can corrupt state if handlers ignore state-machine versions or valid transitions.

### 27.2. Procedure for Sessions / Ordering

1. Group DLQ messages by `SessionId` or business aggregate key.
2. Check completed events and current business state.
3. Decide whether ordered replay or a compensating action is needed.
4. On new messages, preserve `SessionId` if required by the contract and supported by the target.
5. Verify consumers tolerate out-of-order events safely.

**Replaying never inserts a message back into its historical queue position.** It is a fresh send at current wall-clock time; business state machines must guard ordering.

## 28. Topic Subscriptions: One Event, Multiple DLQs

When using a Service Bus topic:

~~~mermaid
flowchart TB
    PUB[OrderSubmitted producer] --> TOPIC[(Topic: order-events)]
    TOPIC --> S1[Subscription: accounting]
    TOPIC --> S2[Subscription: email]
    TOPIC --> S3[Subscription: analytics]
    S1 --> C1[Accounting consumer]
    S2 --> C2[Email consumer]
    S3 --> C3[Analytics consumer]
    C1 --> DLQ1[(Accounting DLQ)]
    C3 --> DLQ3[(Analytics DLQ)]
~~~

An event may succeed in `email` yet fail in `accounting`. Monitor DLQs **per subscription**, not just at the namespace level.

### 28.1. Targeted Replay

When replaying from the **accounting DLQ**, republishing the raw event to the topic can cause **email and analytics to receive it a second time**, even though they already succeeded.

Options to evaluate:

- Replay into a dedicated delivery path serving only the failed consumer, if supported by architecture.
- Use a replay topic/route with explicit subscription filters.
- Enforce consumer idempotency across all subscriptions.
- Apply controlled compensating actions instead of re-broadcasting.

**Never assume you can "send directly back to a subscription"**, because a Service Bus subscription receives from a topic rather than acting as a queue send endpoint. Design valid broker replay paths upfront.

## 29. Message TTL, Retention, and Data Compliance

A common misconception: **messages inside a Service Bus DLQ normally do not expire via the active queue's TTL mechanism**; dead-lettered messages typically remain until read and explicitly completed or deleted. Thus, DLQ capacity and retention must be managed operationally.

### 29.1. A DLQ Is Not Long-Term Storage

- Messages may hold sensitive customer data.
- Growing DLQs count toward entity storage limits.
- Unmanaged DLQs inflate costs and violate data-retention policies.
- A DLQ never replaces Azure Backup, databases, or archival stores.

### 29.2. When to Archive Before Deleting?

If forensic evidence must be kept without bloating the broker, export sanitized metadata and payloads to Storage or a database with dedicated access controls, encryption, retention, and auditing. Verify archival succeeded before completing/deleting the DLQ message.

### 29.3. Never Auto-Purge by Age Before Business Resolution

A 30-day-old unresolved message could represent a critical invoice. Retention policies must involve SLAs, legal rules, security, and business owners—not storage size alone.

## 30. Monitoring DLQs and Poison Queues with Azure Monitor

Useful indicators:

| Metric | Meaning | Action |
|---|---|---|
| **DLQ message count** | Messages awaiting resolution | Alert on growth or backlog thresholds |
| **DLQ arrival rate** | New messages entering DLQ over time | Detect active regressions quickly |
| **Oldest DLQ message age** | Longest-waiting unresolved message | Enforce resolution SLAs |
| **Active backlog** | Messages remaining in main queue | Detect consumers falling behind |
| **Delivery count distribution** | Attempts/retries before DLQ | Tune `MaxDeliveryCount` |
| **Reason distribution** | Share of schema, timeout, auth errors | Prioritize root-cause fixes |
| **Replay success rate** | Replayed messages completing business goals | Measure recovery quality |
| **Repeated DLQ / replay loops** | Same business event bouncing back to DLQ | Halt replay and investigate |
| **Dependency error rate** | External DB/API/Storage failure rates | Prevent mass dead-lettering |
| **Queue/consumer throughput** | Completed messages over time | Track recovery velocity |

Azure Monitor provides metrics and diagnostic logs for Service Bus and Storage depending on resource configuration. Not every metric—such as **reason distribution** or **oldest DLQ message age**—is exposed natively; a **DLQ inspector** or custom telemetry pipeline may be needed.

### 30.1. Total Counts Are Not Enough

If a DLQ stays at 100 messages while 100 new failures arrive and 100 old ones are deleted each day, a flat count hides an ongoing outage. Track arrival rate, age, resolution rate, and business impact.

### 30.2. Using Azure Monitor Alerts

Configure alerts on verified available metrics or custom DLQ-inspector metrics:

- Continuous DLQ count growth.
- New DLQ arrivals from a specific producer version.
- Oldest age breaching SLA.
- Replay failure rate exceeding threshold.
- Active queue backlog growing alongside DLQ.
- Entity approaching capacity limits.
- Spikes in consumer exceptions or lost locks.

Every alert needs an **owner** and an action—never send unactionable emails into a void.

## 31. Logging and Correlation for Investigation

Minimal structured log entry:

~~~json
{
  "level": "ERROR",
  "event": "MessageProcessingFailed",
  "entity": "orders",
  "messageId": "evt-demo-001",
  "correlationId": "corr-demo-001",
  "schemaVersion": 2,
  "errorCategory": "InvalidSchema",
  "retryable": false,
  "consumerVersion": "orders-worker-1.4.2",
  "attempt": 3
}
~~~

Never log full payloads or raw exceptions if they contain secrets or PII. When forensics require payload capture, use a tightly restricted store with strict retention and masking.

### 31.1. Cross-Service Tracing

Trace chain:

~~~text
HTTP request
  -> Producer send
  -> Service Bus message
  -> Consumer invocation
  -> Database operation
  -> Dead-letter event or Complete
  -> Replay operation
  -> Final business state
~~~

Application Insights / OpenTelemetry supports distributed correlation when properly instrumented. Preserve `correlationId` across replays while adding a separate **`replayAttemptId`** to distinguish replay executions from originals.

### 31.2. Errors Needing Data to Reproduce

When privacy prevents logging payloads, still capture `schemaVersion`, event type, safe validation error codes, and a controlled reference ID to source data. This enables debugging without spreading copies of sensitive records.

## 32. Security and Authorization for DLQ Operations

DLQs often hold malformed records that still contain sensitive production data. Enforce:

- **Microsoft Entra ID / managed identities** for inspection and replay tools where supported.
- Least-privilege Azure RBAC data-plane roles: separate read/peek observers from Complete/replay operators.
- Explicit approval workflows for bulk replays or deletions.
- Tight access controls on Azure Portal, Service Bus Explorer, Storage Explorer, and CI runners.
- TLS, Private Endpoints/VNets, and firewalls per system architecture.
- Masking/redaction of payloads and error descriptions.
- Audit logs for peek, receive, delete, and replay actions where supported.
- Keep SAS connection strings out of source control and tickets.
- Verify tenant boundaries and target environments before replaying.

### 32.1. Metadata Read Rights Do Not Equal Body Read Rights

An Azure Resource Manager `Reader` can view resource configuration without automatically having permission to read message bodies. Grant explicit data-plane roles such as `Azure Service Bus Data Receiver` per your security model.

### 32.2. Permissions for Replaying Messages

A replay utility typically needs **receive/settle** on the source DLQ and **send** on the target queue/topic. Treat these as sensitive privileges—scope narrowly and run only in approved environments.

### 32.3. Never Blindly Replay Untrusted Data

If a message contains malicious content, replaying it can trigger repeated crashes or unsafe execution paths. Validate schema, size, event type, and origin beforehand.

## 33. DLQ Cost, Performance, and Capacity

DLQs protect failing data yet still create indirect costs:

| Cost Source | Explanation |
|---|---|
| Broker resources | Message storage, entity size limits, operations, and tier |
| Consumer invocations | Repeated retries burn compute |
| Queue polling | Frequent checks increase request volume |
| Replay process | Compute, send/receive operations, and downstream calls |
| Logging/monitoring | Log ingestion, metrics, alerts, and retention |
| Archive storage | Controlled retention of failed payloads |
| Operational labor | Manual investigation and approvals |

An unbounded DLQ can exhaust Service Bus entity storage quotas. Even with low message counts, large payloads or repeated replay copies add up.

### 33.1. Do Not Optimize by Immediately Purging Every DLQ

Purging a DLQ reduces message count and storage usage at the cost of permanently losing transaction recovery. Cleanup decisions must come from business owners, state verification, and retention policy.

### 33.2. Set Impact-Based Thresholds

For payment flows, even 1 dead-lettered message may warrant a high-priority alert. For low-priority batch jobs, error-rate or time-based thresholds may make more sense.

## 34. Scenario 1: Malformed JSON Schema

**Context:** producer version 2 sends:

~~~json
{
  "eventType": "OrderSubmitted",
  "schemaVersion": 9,
  "data": {
    "orderId": "ORD-1001"
  }
}
~~~

The consumer only supports `schemaVersion` 1 and 2.

Workflow:

1. Consumer parses the envelope and detects an unsupported `schemaVersion`.
2. Classifies it as **permanent schema incompatibility**.
3. Explicitly dead-letters with reason **`InvalidSchema`**.
4. Alert detects multiple messages with `schemaVersion=9`.
5. Engineering decides: upgrade consumer to support v9, fix producer, or run a tested converter.
6. After deploying the fix, test replaying mock messages in staging.
7. Verify version compatibility for production.
8. Replay a small batch and verify business records persisted cleanly.
9. Audit and close the incident.

**Never edit payloads directly in a DLQ using an unversioned, unapproved script.** When transformation is needed, emit a new message recording source ID, transformation version, and result.

## 35. Scenario 2: Database Temporarily Unresponsive

**Context:** workers process `OrderSubmitted`, yet Azure SQL times out for several minutes.

Handling:

1. Classify as **transient infrastructure/dependency** error.
2. Retry with bounded backoff to prevent retry storms.
3. Inspect database CPU/DTU/vCore, connection pools, locks, and service health.
4. During widespread outages, throttle concurrency or pause intake per runbook.
5. If messages hit `MaxDeliveryCountExceeded` and land in the DLQ, do not assume their payloads are corrupt.
6. Once the database recovers, select timeout-related DLQ messages and replay gradually.
7. Check for transactions that committed before settlement failed to prevent duplicate writes.

**Lesson:** `MaxDeliveryCountExceeded` alone never proves a payload is invalid. Always inspect logs and downstream state.

## 36. Scenario 3: Duplicate Emails When Replaying a Topic Event

An **`OrderSubmitted`** event is published to a topic with three consumers: accounting, email, and analytics.

- The email subscription sent the email successfully.
- The accounting subscription dead-lettered due to a config bug.
- Ops republishes the original event to the topic.
- The email consumer receives it again and risks sending a duplicate email.

Safe design:

1. Never blindly re-broadcast DLQ messages back to the topic.
2. Check which subscriptions already processed the event.
3. Enforce idempotency keys in the email consumer.
4. Replay only along architecturally approved paths with accurate filtering.
5. Audit that only accounting required recovery.
6. After replay, reconcile both accounting outcomes and sent email counts.

**A DLQ on one subscription does not mean every subscriber on the topic failed.**

## 37. Scenario 4: Azure Functions Queue Storage Poison Queue

Suppose Function **`processInvoices`** reads from Azure Queue Storage queue **`invoices`**. A malformed message causes the function to throw exceptions up to the configured limit.

Expected behavior of the Functions Queue trigger:

~~~text
invoices
    |
    | repeated processing failures
    v
invoices-poison
~~~

Runbook:

1. Check App Insights / Functions logs for failure reasons and attempt counts.
2. Open Storage Explorer / Portal and confirm **`invoices-poison`** holds the message.
3. Read messages carefully; note metadata does not match Service Bus `DeadLetterReason`.
4. Verify whether the invoice was already created beforehand.
5. Fix the handler or underlying data.
6. To replay, enqueue a new message into **`invoices`** under your idempotency policy.
7. Delete from **`invoices-poison`** only after sending and verifying appropriately; accept duplicate delivery risk and guard with idempotency.
8. Watch whether the poison queue keeps growing.

Never try to use Service Bus Explorer or Service Bus SDKs to manage `invoices-poison`—it is an Azure Storage Queue.

## 38. Hands-On Exercise: Service Bus DLQ from Fault Injection to Replay

**Goal:** in a lab subscription, create a Service Bus queue, send mock messages, intentionally trigger failures to observe the DLQ, and execute a controlled recovery plan.

### Part A — Preparation

1. Confirm permissions and budget to create a Service Bus namespace/queue in the lab.
2. Create a dedicated resource group, namespace, and queue **`orders`**.
3. Set `MaxDeliveryCount=5` and inspect dead-letter-on-expiration settings.
4. Choose an appropriate identity and grant only required data-plane roles.
5. Never use real customer data.

### Part B — Create Test Messages

Send three messages using an authorized SDK app or tool:

| Message | Content | Expected Outcome |
|---|---|---|
| **M1** | Valid `OrderSubmitted` schema | `Complete`d |
| **M2** | Invalid JSON/schema | Explicit dead-letter |
| **M3** | Valid message simulating dependency failure | Retried then dead-lettered after limit |

Assign clear `MessageId`, `CorrelationId`, and `schemaVersion`.

### Part C — Processing

1. Run the lab consumer in Peek-Lock mode.
2. For M1, record mock output and `Complete`.
3. For M2, set `DeadLetterReason=InvalidSchema` and call `DeadLetter`.
4. For M3, simulate bounded failures to observe redelivery and `MaxDeliveryCount`.
5. Avoid infinite loops in test scripts.
6. Check Active/DLQ counts in the Portal.

### Part D — Investigation

1. **Peek** the DLQ.
2. Record message IDs, reasons, delivery counts, enqueue time, and producer version.
3. Distinguish explicit reasons from broker-generated `MaxDeliveryCount` entries.
4. Create an incident record documenting root causes.
5. Never print message bodies containing sensitive data to shared logs/terminals.

### Part E — Test Replay

1. Resolve the simulated dependency failure.
2. Select only M3 for replay; do not replay M2 while its schema remains invalid.
3. Run a dry-run displaying source/target IDs and policy checks.
4. Obtain owner sign-off.
5. Send the new message to the active queue.
6. `Complete` the DLQ copy only after the broker acknowledges the new send.
7. Verify consumer outcome and audit log.
8. Test stopping the process between send and `Complete` to observe duplicate risk.

### Part F — Cleanup

1. Confirm no lab workflows still need recovery.
2. Verify queues/DLQs, logs, and background scripts are stopped.
3. Clean up lab messages/resources as approved.
4. Never delete namespaces or resource groups containing shared resources.
5. Review incurred charges in Azure Cost Management.

**Completion criteria:** explain why M2 and M3 entered the DLQ via two different mechanisms, distinguish peeking from receiving, and demonstrate a replay flow that never completes the source before sending succeeds.

## 39. Bonus Exercise: Poison Queues with Azure Functions

If your environment has a test Azure Function App and Azure Storage account:

1. Create queue **`demo-jobs`**.
2. Configure a Queue trigger with a small `maxDequeueCount` suitable for learning.
3. Send both valid and malformed-schema messages.
4. Observe invocation retries and Functions logs.
5. Inspect **`demo-jobs-poison`** after exceeding the limit.
6. Compare poison queue metadata with the Service Bus DLQ from the previous exercise.
7. Build a read-only **Peek/read** helper to summarize contents without deleting messages.
8. Design an idempotent resend workflow.
9. Clean up lab resources and secrets.

**Never simulate poison queues by intentionally injecting failures into production apps.** Protect quotas, costs, and data in shared environments.

## 40. Production DLQ Design Checklist

- [ ] Identified the exact queue/broker service and its DLQ/poison mechanism.
- [ ] Service Bus queues/subscriptions configure an appropriate `MaxDeliveryCount`.
- [ ] TTL and dead-letter-on-expiration match business requirements.
- [ ] Consumers classify transient, permanent, and unknown errors.
- [ ] Retries are bounded with backoff/jitter and a total retry budget.
- [ ] Widespread dependency outages trigger load shedding or safe pausing.
- [ ] Messages include `MessageId`, `CorrelationId`, `schemaVersion`, and business keys.
- [ ] Standardized `DeadLetterReason` values; descriptions omit secrets/PII.
- [ ] Never use Receive-and-Delete where safe retries are required.
- [ ] Consumers are idempotent across broker redeliveries and replays.
- [ ] Dashboards track DLQ count, arrival rate, age, and reason distribution.
- [ ] Alerts have assigned owners and failed-message SLAs.
- [ ] Runbook covers peek, classify, root-cause fix, approve, replay, verify, audit.
- [ ] Replay tooling supports dry-run, batch size, rate limit, pause, and checkpointing.
- [ ] Never `Complete` a DLQ message before the new send succeeds.
- [ ] Accounted for the send-success / complete-failure duplicate window.
- [ ] Service Bus session data and ordering evaluated before replay.
- [ ] Topic subscription replays avoid unintended broadcasts to healthy subscribers.
- [ ] Retention/archival policies meet data and legal requirements.
- [ ] RBAC separates read-only observers from replay/delete operators.
- [ ] Secrets/keys kept out of code, logs, and error descriptions.
- [ ] Practiced database outage drills and small-batch replays.
- [ ] Audit trail captures incidents, operators, and business outcomes.
- [ ] Budget covers broker operations, retries, logs, and archival storage.
- [ ] Tested resilience when the replay worker itself crashes.

## 41. Self-Check Questions

1. What problem does a dead-letter queue solve in an event-driven system?
2. How does a Service Bus DLQ differ from an Azure Functions Queue Storage poison queue?
3. If using the Azure Queue Storage SDK directly, does the service automatically create a `-poison` queue?
4. How do `Complete`, `Abandon`, and `DeadLetter` actions differ?
5. Why is Peek-Lock preferred over Receive-and-Delete for critical transactions?
6. Does `MaxDeliveryCountExceeded` always prove the payload is malformed?
7. Does TTL expiration automatically send every expired message into the Service Bus DLQ?
8. How does one topic subscription's DLQ impact other subscriptions?
9. What causes messages to enter a transfer DLQ rather than a business DLQ?
10. Why classify transient vs. permanent errors before retrying?
11. Why can unbounded retries worsen an outage?
12. Why shouldn't you use multi-minute `Thread.sleep` calls to delay retries inside a Function?
13. Which metadata fields should be preserved to investigate dead-lettered messages?
14. Should `Reason` and `ErrorDescription` contain full payloads or stack traces?
15. Why can replaying a message after sending an email or charging a card be dangerous?
16. How does a business-level idempotency key differ from Service Bus duplicate detection?
17. Why does send-first, complete-after still not guarantee end-to-end exactly-once?
18. If a business event belongs to a Service Bus session, how can replay break ordering?
19. Why can republishing an event to a topic cause duplicate side effects?
20. Which metrics are missing from a dashboard that only tracks total DLQ count?
21. Does someone with only ARM `Reader` automatically have access to read message bodies?
22. When should DLQ messages be archived before deletion?
23. If a queue accumulates thousands of `DeadLetterReason=DependencyUnavailable` messages, what must happen before replay?
24. With an Azure Functions Queue trigger, how does `host.json`'s `maxDequeueCount` relate to the poison queue?
25. Beyond a lower DLQ count, what must a successful recovery exercise prove?

## 42. Summary

A **dead-letter queue** is essential for retaining and investigating messages that cannot be processed normally. In **Azure Service Bus**, queues and topic subscriptions include built-in dead-letter subqueues governed by **`MaxDeliveryCount`**, TTL policies, and explicit dead-lettering. In **Azure Queue Storage**, there is no equivalent broker-native DLQ; the **Azure Functions Queue trigger** uses **`<queue-name>-poison`** under runtime retry behavior.

Proper design does not stop at creating a DLQ. You need **error classification, bounded retries, idempotency, sanitized metadata, monitoring, and an approved replay workflow**. Replays must prevent data loss, duplicate transactions, ordering corruption, and repeat failures. Always fix root causes first, send the new message before completing the source, and verify final business outcomes.

Combine **Service Bus/Queue Storage**, **Azure Functions or AKS workers**, **Microsoft Entra ID/managed identities**, **Azure Monitor/Application Insights**, **databases**, and **Cost Management** to build message-processing pipelines that are secure, recoverable, and cost-controlled. **A message leaving the DLQ does not mean the problem is solved**; the ultimate goal is a verified business outcome—or transparent, audited, approved closure.
