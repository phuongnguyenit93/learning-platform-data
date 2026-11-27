# Transactions, Scheduling, and Deferred Messages

In cloud application architectures, messages rarely just get sent and immediately received. An order may need to **commit a recording step before emitting follow-up events**, a payment reminder email might only need to appear **after 30 minutes**, or a "payment confirmed" event must be **set aside** until the corresponding order details arrive in the system. These three needs correspond to **transactions**, **scheduled messages**, and **deferred messages** in **Azure Service Bus**.

This is a lesson in the **Queues and Messaging** chapter of the **CLOUD_PROVIDERS_AZURE** module. Alongside Microsoft Azure subscriptions, resource groups, Microsoft Entra ID, networking, compute, and storage, learners must understand how to guarantee consistency across asynchronously communicating services, schedule future work, and orchestrate out-of-order events without losing data.

**Three non-interchangeable concepts:**

- **Transaction:** groups **supported Service Bus operations** into a single **commit or rollback** unit.
- **Scheduling:** places a message into a **waiting state until an eligible enqueue time** when normal consumers can receive it.
- **Deferral:** a consumer already received a message yet intentionally **leaves it inside the queue/subscription**, retrieving it later only by **sequence number** once business prerequisites are met.

> **Design principle:** A Service Bus transaction is **not a distributed transaction** that automatically includes Azure SQL Database, Cosmos DB, Blob Storage, HTTP APIs, or email. A scheduled message is **not** a promise that processing completes on time. A deferred message **does not automatically reappear** in normal receives at some future time.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish queues, topics/subscriptions, messages, delivery modes, and settlement in Azure Service Bus.
2. State the atomicity scope, timeouts, prerequisites, and limits of Service Bus transactions.
3. Design multi-message transactional sends, transactional settlement, and handling of ambiguous commit outcomes.
4. Use the **Azure SDK for Java** to create, commit, and roll back transactions via supported APIs.
5. Schedule messages using UTC timestamps, persist sequence numbers, and cancel schedules before activation.
6. Distinguish scheduled messages from in-app delays, cron jobs, Service Bus Sessions, and deferral.
7. Defer messages in **PeekLock**, persist sequence numbers durably, and receive deferred messages to complete processing.
8. Combine these mechanisms into workflows with idempotency, duplicate detection, TTL, dead-letter queues (DLQs), and sensible retries.
9. Provision lab namespaces/queues and manage identities and least-privilege permissions.
10. Inspect logs/metrics and diagnose lock errors, transaction timeouts, missing messages, and backlogs.
11. Evaluate trade-offs across performance, throughput, operational cost, and reliability of a messaging system.

## 2. Illustrative Architecture: An Orders System on Azure

Suppose there are three applications:

- **Orders API:** captures purchase requests.
- **Payment Worker:** processes payment results and requires the corresponding order record.
- **Reminder Worker:** sends reminders if a customer has not paid after a set period.

A simple design:

~~~mermaid
flowchart LR
    USER["Customer"] --> API["Orders API<br/>App Service / AKS"]
    API -->|"OrderCreated"| SB["Azure Service Bus<br/>Namespace"]
    SB --> QUEUE1["orders-events"]
    SB --> QUEUE2["payment-events"]
    SB --> QUEUE3["payment-reminders"]
    QUEUE1 --> ORDER["Order Worker"]
    QUEUE2 --> PAY["Payment Worker"]
    QUEUE3 --> REM["Reminder Worker"]
    ORDER --> DB["Azure SQL / Cosmos DB"]
    PAY --> DB
    REM --> DB
    API -. "Entra ID / managed identity" .-> SB
~~~

This diagram only shows high-level components. In practice, each queue/topic/subscription is a **messaging entity** under the namespace. Producers and consumers can receive distinct identities and roles.

### 2.1. Required Terminology

| Term | Meaning | Example |
|---|---|---|
| **Namespace** | Management boundary for Azure Service Bus entities, networking, identity, and tier | `sb-orders-lab` |
| **Queue** | Destination where competing consumers pull individual messages | `orders-events` |
| **Topic / subscription** | Publish/subscribe; each subscription receives copies matching rules/filters | `orders-topic` / `billing` |
| **Producer / Sender** | Application sending messages | Orders API |
| **Consumer / Receiver** | Application reading and settling messages | Payment Worker |
| **PeekLock** | Receives without deleting yet; must complete/abandon/defer/dead-letter | Controlled processing |
| **ReceiveAndDelete** | Message removed from entity on delivery per service mechanics | Workloads tolerating data-loss risk |
| **Lock token** | Represents one lock instance for settling a message | Authority over a received delivery |
| **Sequence number** | Broker-assigned identifier within an entity | Retrieve deferred / cancel scheduled |
| **MessageId** | Producer-supplied identifier; useful for correlation/dedup | `order-481-payment` |
| **SessionId** | Groups messages coordinated by session | `order-481` |
| **TTL** | Message lifetime per entity/message config | 24 hours |
| **DLQ** | Subqueue holding unprocessable or explicitly dead-lettered messages | `orders-events/$DeadLetterQueue` |

Never confuse **`MessageId`**, **`SequenceNumber`**, **`SessionId`**, and **`LockToken`**. They serve different purposes and cannot be swapped arbitrarily.

### 2.2. PeekLock Is the Foundation for Settlement

~~~mermaid
flowchart TD
    A["Queue: Active message"] --> B["Receiver: PeekLock"]
    B --> C{"How to handle?"}
    C -->|"Success"| D["Complete → delete from queue"]
    C -->|"Transient error"| E["Abandon → eligible for redelivery"]
    C -->|"Unrecoverable error"| F["Dead-letter → DLQ"]
    C -->|"Missing prerequisites"| G["Defer → retrieve only by sequence number"]
~~~

**`ReceiveAndDelete`** is unsuitable when transactional settlement or post-receive deferral is needed: the message is already removed from the queue as soon as the broker delivers it in that mode.

## 3. Comparison Table: Transaction, Scheduled Message, and Deferred Message

| Criterion | Transaction | Scheduled Message | Deferred Message |
|---|---|---|---|
| Question solved | Do multiple broker operations succeed or fail together? | When does a message **enter the normal receive stream**? | When will an already-received message be fetched back for processing? |
| Initiator | Sender/receiver creating a transaction context | Sender scheduling a message | Receiver in PeekLock deferring a message |
| Scope | Supported Service Bus operations | Message scheduled before becoming active | Message already inside the queue/subscription |
| How accessed next | Commit/rollback transaction | Normal receiver after activation time | Receiver must know the **sequence number** |
| Artifact to remember | Transaction context and outcome | Sequence number of the scheduled message | Sequence number of the deferred message |
| Built-in timer? | No | **Yes** | **No** |
| Atomic with database? | No | No | No |
| Notable risks | Timeouts, ambiguous commit, unsafe retries | Race near activation time, delayed delivery | Lost sequence number, forgotten message |
| Use case | Send two events atomically or roll back both | Send payment reminder in 30 minutes | Wait for `OrderCreated` before processing `PaymentConfirmed` |

Reasoning exercise: if the requirement is "`PaymentConfirmed` arrived before `OrderCreated`," **defer** fits. If the requirement is "wait 15 minutes before sending a reminder," use **schedule**. If the requirement is "send both messages or neither," use a **transaction** within supported broker bounds.

## 4. Environment Preparation and Tier Selection

### 4.1. Service Bus Basic, Standard, and Premium

Azure Service Bus offers multiple tiers. **Standard** adds topics/subscriptions, sessions, transactions, and duplicate detection over Basic. **Premium** provides more isolated messaging resources, supporting advanced networking and performance capabilities such as Private Link within supported configurations.

For labs involving **transactions**, use **Standard or Premium** rather than assuming advanced features exist on Basic. Before production deployment, verify scheduling/deferral features, queue options, and limits for your exact tier and API version.

| Criterion | Basic | Standard | Premium |
|---|---|---|---|
| Basic queues | Yes | Yes | Yes |
| Topics/subscriptions | No | Yes | Yes |
| Transactions | Do not use Basic for this lab | Yes | Yes |
| Sessions / duplicate detection | Tier-limited | Yes | Yes |
| Dedicated capacity, scale/SLA | Fewer features | Shared capacity | Dedicated Messaging Units |
| Private Link / VNet capabilities | Limited | Limited | Advanced capabilities per feature set |
| Pricing | Per tier/usage | Per operations/usage | Per Messaging Units/usage and related components |

### 4.2. Lab Prerequisites

- Authorized subscription and resource group.
- Standard/Premium Service Bus namespace in an appropriate region.
- Three sample queues, or one dedicated queue per experiment.
- Java 17+ and Maven if practicing with the Java SDK; choose supported SDK versions.
- Azure CLI, Azure Cloud Shell, or an environment able to reach the namespace.
- Microsoft Entra identity with appropriate permissions: **Azure Service Bus Data Sender** or **Data Receiver**, using **Data Owner** only when truly required and approved.
- Network, DNS, TLS, and AMQP/TCP or WebSockets ports per environment configuration.
- Safe testing policy: never use real customer messages; enforce quotas/TTLs, DLQs, and a cleanup plan.

Commands in this lesson are **guidance only** and did not provision resources on your subscription during authoring.

### 4.3. Creating a Lab Namespace and Queues via Azure CLI

~~~bash
az login
az account set --subscription "<subscription-id>"
az account show --output table

RG="rg-servicebus-messaging-lab"
REGION="southeastasia"
NS="<globally-unique-servicebus-namespace>"

az group create \
  --name "$RG" \
  --location "$REGION"

az servicebus namespace create \
  --resource-group "$RG" \
  --name "$NS" \
  --location "$REGION" \
  --sku Standard
~~~

Create separate queues so complete, defer, and schedule experiments do not mix messages:

~~~bash
az servicebus queue create \
  --resource-group "$RG" \
  --namespace-name "$NS" \
  --name "tx-lab"

az servicebus queue create \
  --resource-group "$RG" \
  --namespace-name "$NS" \
  --name "scheduled-lab"

az servicebus queue create \
  --resource-group "$RG" \
  --namespace-name "$NS" \
  --name "deferred-lab"
~~~

Inspect:

~~~bash
az servicebus namespace show \
  --resource-group "$RG" \
  --name "$NS" \
  --query "{name:name,location:location,sku:sku.name,status:status}" \
  --output json

az servicebus queue list \
  --resource-group "$RG" \
  --namespace-name "$NS" \
  --output table
~~~

If namespaces/queues already exist, **never modify or recreate production entities**. Advanced options such as duplicate detection, sessions, DLQs, auto-forwarding, and partitioning must be decided **before** using a real entity, as some settings cannot easily change later.

## 5. Java Identity and SDK Configuration

For new apps, prefer **Microsoft Entra ID / managed identity** rather than baking Service Bus connection strings into repositories or container images.

### 5.1. Maven Dependencies

Example for a Java project; align versions via a project BOM or dependency management:

~~~xml
<dependencies>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-messaging-servicebus</artifactId>
    <version>7.18.0</version>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
    <version>1.18.7</version>
  </dependency>
</dependencies>
~~~

**Note:** the two SDK versions in this Maven snippet are illustrative released versions, not a promise they are always the latest pair. In real projects, use current compatible versions or an approved Azure SDK BOM/dependency management, pinning versions for reproducible builds. This snippet belongs inside your project's POM, not as a standalone complete POM.

### 5.2. Creating Sender and Receiver with DefaultAzureCredential

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.core.credential.TokenCredential;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusSenderClient;
import com.azure.messaging.servicebus.ServiceBusReceiverClient;
import com.azure.messaging.servicebus.models.ServiceBusReceiveMode;

TokenCredential credential =
        new DefaultAzureCredentialBuilder().build();

String fqdn = System.getenv("SERVICEBUS_FQDN");
// Example: sb-orders-lab.servicebus.windows.net
String queue = "tx-lab";

ServiceBusSenderClient sender = new ServiceBusClientBuilder()
        .credential(fqdn, credential)
        .sender()
        .queueName(queue)
        .buildClient();

ServiceBusReceiverClient receiver = new ServiceBusClientBuilder()
        .credential(fqdn, credential)
        .receiver()
        .queueName(queue)
        .receiveMode(ServiceBusReceiveMode.PEEK_LOCK)
        .buildClient();

// When finished: sender.close(); receiver.close();
~~~

This is a **configuration fragment inside a Java method**, not a standalone class. In real projects, validate environment variables before building clients and manage client lifetimes. SDK clients should generally be reused rather than reopened per message.

**The FQDN has no `https://` prefix**; use the form **`your-namespace.servicebus.windows.net`**.

### 5.3. Separate Permissions for Sender and Receiver

- Producer: **Azure Service Bus Data Sender** on the target queue/namespace.
- Consumer: **Azure Service Bus Data Receiver**.
- Queue/namespace provisioner: scoped Azure management-plane permissions.
- Apps needing both send and receive: assign the two least-privilege roles needed rather than Data Owner unless required.

Role assignments can take time to propagate. Distinguish **401/403 authorization errors** from DNS, TLS, or message settlement errors.

### 5.4. Networking

The Azure Service Bus SDK normally connects via **AMQP over TLS**. If your environment blocks direct AMQP ports, evaluate configuring **AMQP over WebSockets** as supported by the SDK documentation.

When a namespace uses a **Private Endpoint**, ensure accurate routing and private DNS from App Service/AKS/VMs to the namespace. **Never disable firewalls or open public access casually** just to make a lab run faster.

## 6. Transactions: Atomicity Scope

A Service Bus transaction groups one or more **broker-supported operations** into one unit: committing applies them together, while rolling back discards effects inside the transaction scope.

### 6.1. Supported Operations

Messaging operations documented by Service Bus for transactions include:

- **Send** messages.
- **Complete** received messages.
- **Abandon** received messages.
- **Dead-letter** received messages.
- **Defer** received messages.
- **Renew lock** where supported by the API.

Some sender APIs in the Azure SDK for Java also offer **`scheduleMessage(..., transactionContext)`** or **`scheduleMessages(..., transactionContext)`**. Check limits and behavior for your current SDK/broker; never assume entity management APIs participate in transactions.

**Receive itself does not happen inside a transaction.** Common flow:

1. Consumer receives a message in **PeekLock**.
2. Executes work that belongs outside the transaction.
3. Starts a transaction.
4. Sends follow-up events and settles the received message using the transaction context as supported.
5. Commits or rolls back.

### 6.2. Atomic Send Example

~~~mermaid
flowchart TD
    S["Begin transaction"] --> A["Send Event A"]
    A --> B["Send Event B"]
    B --> D{"Commit?"}
    D -->|Yes| C["Both A and B take effect"]
    D -->|Rollback| R["Neither A nor B applied in transaction"]
~~~

Meaning: if two messages must appear together in an entity and one send fails before commit, the application can roll back the whole group.

Never cram **thousands of messages or slow business processing** into one transaction just because it sounds safer. Transactions have strict timeouts, quotas, locks, and throughput limits.

### 6.3. Transaction Timeout

A Service Bus transaction has a **timeout of roughly 2 minutes** from the first operation in the transaction per service documentation. Keep transactions short; never run slow SQL/HTTP calls or wait on user input while a transaction remains open.

An easily missed detail: the SDK **does not automatically retry operations inside a transaction the way it retries normal sends**, since mid-transaction retries risk settlement deadlocks or ambiguous outcomes. On error, evaluate the outcome and use idempotency instead of blindly retrying.

### 6.4. Cross-Entity Transactions

Service Bus supports transaction patterns spanning **multiple messaging entities within the same namespace** under specific SDK settings and rules, including **send-via / transfer entity** workflows that coordinate settling an inbound message with sending outbound messages.

However:

- Never assume sending from a queue in namespace A to a queue in namespace B forms one transaction.
- Explicitly configure **cross-entity transactions** where required by the SDK and design; Java provides a builder option for this.
- Verify same namespace, entity paths, transfer routes, and permissions.
- Account for differences when transferring between queues, topics, and subscriptions.
- Avoid assuming every operation or topic filter shares identical atomicity without checking exact documentation.

This lesson provides a **single-queue** transaction example next to illustrate atomicity clearly; cross-entity transfer workflows must be designed and tested separately.

## 7. Java Hands-On: Sending Two Messages in One Transaction

The complete example below uses the Java SDK's **`ServiceBusSenderClient.createTransaction`**, **`sendMessage(message, transaction)`**, **`commitTransaction`**, and **`rollbackTransaction`**.

Use queue **`tx-lab`**, credentials holding **Data Sender**, and environment variable **`SERVICEBUS_FQDN`**.

### 7.1. Class TransactionSendDemo

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusMessage;
import com.azure.messaging.servicebus.ServiceBusSenderClient;
import com.azure.messaging.servicebus.ServiceBusTransactionContext;

import java.util.UUID;

public final class TransactionSendDemo {
    public static void main(String[] args) {
        String fqdn = System.getenv("SERVICEBUS_FQDN");
        if (fqdn == null || fqdn.isBlank()) {
            throw new IllegalArgumentException("Missing SERVICEBUS_FQDN");
        }

        try (ServiceBusSenderClient sender = new ServiceBusClientBuilder()
                .credential(fqdn,
                        new DefaultAzureCredentialBuilder().build())
                .sender()
                .queueName("tx-lab")
                .buildClient()) {

            String batchId = UUID.randomUUID().toString();
            ServiceBusMessage first =
                    new ServiceBusMessage("reserve-stock")
                    .setMessageId(batchId + "-stock");

            ServiceBusMessage second =
                    new ServiceBusMessage("record-audit")
                    .setMessageId(batchId + "-audit");

            ServiceBusTransactionContext transaction =
                    sender.createTransaction();

            try {
                sender.sendMessage(first, transaction);
                sender.sendMessage(second, transaction);
                sender.commitTransaction(transaction);
                System.out.println("Committed batchId=" + batchId);
            } catch (RuntimeException error) {
                try {
                    sender.rollbackTransaction(transaction);
                } catch (RuntimeException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }
}
~~~

**Expected lab result:** if the transaction commits cleanly, both messages appear in **`tx-lab`**. If it rolls back before commit, neither send is applied.

### 7.2. Limitations of This Example

- This only gives **send atomicity to the broker**, not "inventory deducted" in a database.
- **`BatchId`** aids lookup and correlation. **`MessageId`** is explicitly set to support correlation/dedup where configured.
- If **`commitTransaction`** times out or drops connectivity mid-response, the app may **not know whether commit succeeded**. Calling rollback after an error cannot undo an already-completed commit.
- Therefore **never blindly retry with brand-new `MessageId`s** when outcomes are ambiguous. Reconcile business state, and rely on duplicate detection/outboxes and idempotency.
- Never start a new transaction expecting an old transaction's rollback to affect it.

### 7.3. Testing Pattern

1. In the lab, run the demo with healthy networking and read messages from **`tx-lab`**.
2. Inject a controlled error **before commit** to verify rollback.
3. Simulate a network failure on the producer without assuming outcome from the exception alone.
4. Record **`MessageId`**, **`batchId`**, and timestamps for reconciliation.
5. Check message counts and logs—never delete production messages for testing.
6. Note transaction timeouts and SDK retry behaviors.

## 8. Transactions with Settlement of Received Messages

Once a consumer receives a message in **PeekLock**, **`Complete`** can join a transaction via supported APIs. In the Azure SDK for Java, receivers use **`CompleteOptions.setTransactionContext(...)`**.

### 8.1. Illustrative Code Sample

~~~java
import com.azure.messaging.servicebus.*;
import com.azure.messaging.servicebus.models.*;
import com.azure.identity.DefaultAzureCredentialBuilder;
import java.time.Duration;
import java.util.Iterator;

public final class TransactionCompleteDemo {
    public static void main(String[] args) {
        String fqdn = System.getenv("SERVICEBUS_FQDN");

        try (ServiceBusReceiverClient receiver =
                 new ServiceBusClientBuilder()
                   .credential(fqdn,
                     new DefaultAzureCredentialBuilder().build())
                   .receiver()
                   .queueName("tx-lab")
                   .receiveMode(ServiceBusReceiveMode.PEEK_LOCK)
                   .buildClient()) {

            Iterator<ServiceBusReceivedMessage> it =
                receiver.receiveMessages(
                    1, Duration.ofSeconds(20)).iterator();

            if (!it.hasNext()) {
                System.out.println("No message received");
                return;
            }

            ServiceBusReceivedMessage message = it.next();
            // Demonstrates settlement only; no real business processing yet.
            ServiceBusTransactionContext tx =
                    receiver.createTransaction();

            try {
                receiver.complete(
                    message,
                    new CompleteOptions().setTransactionContext(tx));
                receiver.commitTransaction(tx);
                System.out.println(
                    "Completed MessageId=" + message.getMessageId());
            } catch (RuntimeException error) {
                try {
                    receiver.rollbackTransaction(tx);
                } catch (RuntimeException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }
}
~~~

Run this code only against **test messages**. Never complete a production message merely to test API calls without actually processing its business payload.

### 8.2. Why Does Receive Happen Before the Transaction?

Service Bus expects the app to have already received and locked the message before opening a settlement transaction. A transaction does not stay open across multi-minute business work; it wraps the final broker operations.

For example, "receive from queue A, send to queue B, complete message A" can be atomic **within Service Bus's supported scope**, provided cross-entity transactions are configured properly. Never swap the single-queue client in this snippet for two queues and assume it stays atomic automatically.

### 8.3. Lock Lost Before Commit

A PeekLock message holds a time-limited lock. If work takes too long, the lock can expire and another consumer can receive the message again. Subsequent complete/defer calls then fail with **`MessageLockLost`** or matching settlement errors.

To avoid this:

- Never open a transaction while long HTTP/SQL calls remain unfinished.
- Use auto-lock renewal or SDK lock renewal within bounded limits when needed.
- Tune max delivery count, timeouts, and retries appropriately.
- Keep handlers idempotent since lock renewal can still fail.
- For very long work, persist external state, complete early, and orchestrate subsequent steps via a suitable workflow model.

## 9. A Service Bus Transaction Is Not a Distributed Transaction with Databases

This is a widespread architectural misconception.

~~~mermaid
flowchart LR
    A["Orders API"] --> DB["Azure SQL: INSERT order"]
    A --> SB["Service Bus: SEND OrderCreated"]
    X["An error occurs between the two calls"] -. "Does not auto-rollback both DB and broker" .-> DB
    X -. "Does not auto-rollback both DB and broker" .-> SB
~~~

If the app writes SQL successfully and fails sending to Service Bus, the SQL transaction **does not automatically roll back** the broker—and if sending succeeds before SQL rolls back, an event describes an order that does not exist.

### 9.1. Transactional Outbox

A common solution:

1. Within **one database transaction**, write **`Orders`** and a row to **`Outbox`**.
2. Commit the database.
3. A background worker reads the Outbox.
4. The worker sends the message to Service Bus with a stable `MessageId`.
5. Once the send is acknowledged, mark the Outbox row as sent.
6. Consumers process idempotently and persist completion markers.

~~~mermaid
flowchart TD
    API["Orders API"] --> TX["DB transaction"]
    TX --> O["Orders table"]
    TX --> OUT["Outbox table"]
    OUT --> RELAY["Outbox publisher"]
    RELAY --> SB["Service Bus"]
    SB --> WORKER["Idempotent consumer"]
~~~

An outbox closes the gap of "DB committed without recording intent to publish." Still, the publisher can resend if it crashes between **send success** and **mark sent**. Therefore duplicate detection/idempotency at consumers remains essential; never treat an outbox as magic end-to-end exactly-once for external side effects.

### 9.2. Saga / Compensating Actions

For flows spanning Orders, Payments, Inventory, and Shipping, a brief Service Bus transaction cannot wrap external APIs and databases. Use stateful workflows and **sagas/compensations** if a late step fails after earlier steps committed.

Never hold a Service Bus transaction open while waiting on a bank gateway; it will almost certainly time out.

## 10. Scheduling: Sending Messages for Future Activation

A **scheduled message** is sent ahead of time yet held by Service Bus in a **scheduled** state until its **scheduled enqueue time**.

~~~mermaid
flowchart LR
    P["Producer"] -->|"Schedule: 15:30 UTC"| Q["Service Bus scheduled store"]
    Q -->|"Activation time reached"| A["Active queue/subscription"]
    A -->|"Normal receive"| C["Consumer"]
~~~

Common uses:

- Send a payment reminder if an order remains unpaid after 30 minutes.
- Re-evaluate transaction status after 10 minutes.
- Trigger a compensation step on workflow timeout.
- Schedule an audit/reconciliation message for a specific business date.

### 10.1. Scheduled Time Is an Activation Timestamp, Not a Completion Deadline

If a message is scheduled for 15:30 UTC:

- The broker makes the message eligible for delivery **starting at that time** per service mechanics.
- Consumers might receive it **after** 15:30 due to backlogs, capacity limits, network issues, throttling, or offline workers.
- The system **does not guarantee** the email actually goes out at exactly 15:30.
- A scheduled message does not turn into a **recurring cron schedule**; each scheduled execution is its own message.

For recurring daily/weekly runs, use an orchestrator/scheduler to emit individual sends or a service designed for recurring schedules.

### 10.2. Two Ways to Schedule

- Send a normal message with **`ScheduledEnqueueTimeUtc`** / corresponding SDK property set.
- Call **`scheduleMessage`** / **`scheduleMessages`** with the target timestamp.

In the Azure SDK for Java, **`scheduleMessage`** returns the **scheduled message's sequence number**, used to cancel it before activation. If setting the property directly on a message instead, verify how you obtain sequence numbers if cancellation may be needed.

### 10.3. Time and Timezones

Service Bus uses UTC/offset timestamps on the wire. In Java, prefer:

~~~java
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

OffsetDateTime when = OffsetDateTime.now(ZoneOffset.UTC)
    .plusMinutes(30);
~~~

For requirements like "remind at 09:00 Vietnam time," convert from the proper timezone (such as **`Asia/Ho_Chi_Minh`**) to UTC before scheduling. Never hardcode fixed hour offsets if the app also serves regions observing daylight saving time.

### 10.4. TTL and Scheduled Messages

For scheduled messages, the **active message TTL countdown** ties to when the message is enqueued/activated per service rules, not simply when the producer submitted the schedule request.

Example: scheduled 5 minutes ahead with a 10-minute TTL—the message can expire roughly 15 minutes after the producer called schedule if still unprocessed. That is conceptual only; check queue TTL, message TTL, and entity expiry/DLQ behavior.

## 11. Java Hands-On: Scheduling and Canceling Messages

Using queue **`scheduled-lab`** and an authorized sender:

### 11.1. Class ScheduleDemo

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusMessage;
import com.azure.messaging.servicebus.ServiceBusSenderClient;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.UUID;

public final class ScheduleDemo {
    public static void main(String[] args) {
        String fqdn = System.getenv("SERVICEBUS_FQDN");
        String orderId = "order-lab-" + UUID.randomUUID();

        try (ServiceBusSenderClient sender =
                 new ServiceBusClientBuilder()
                   .credential(fqdn,
                     new DefaultAzureCredentialBuilder().build())
                   .sender()
                   .queueName("scheduled-lab")
                   .buildClient()) {

            ServiceBusMessage reminder =
                    new ServiceBusMessage(
                        "{\"type\":\"PaymentReminder\",\"orderId\":\""
                          + orderId + "\"}")
                    .setMessageId("reminder-" + orderId);

            reminder.getApplicationProperties().put(
                    "orderId", orderId);

            OffsetDateTime when =
                    OffsetDateTime.now(ZoneOffset.UTC).plusMinutes(5);

            long scheduledSequence =
                    sender.scheduleMessage(reminder, when);

            System.out.printf(
                "Scheduled order=%s, sequence=%d, when=%s%n",
                orderId, scheduledSequence, when);

            // Production: durably PERSIST scheduledSequence
            // alongside namespace, entity, orderId, and schedule state.
        }
    }
}
~~~

Expected result: the message sits in scheduled state and does not show up in normal **`receiveMessages`** calls prior to activation. Once activated, consumers receive it like any active message.

### 11.2. Canceling a Schedule

Assuming **`scheduledSequence`** was saved earlier and the message has not activated yet:

~~~java
// sender is connected to the exact namespace and queue used for scheduling.
long scheduledSequence = Long.parseLong(
        System.getenv("SCHEDULED_SEQUENCE"));

sender.cancelScheduledMessage(scheduledSequence);
~~~

This is a **code fragment inside a method holding a sender**, not a complete class. The environment variable **`SCHEDULED_SEQUENCE`** is for lab convenience; production code should store sequence numbers in a database/workflow store alongside entity and business key.

**Once activated, the old scheduled sequence number cannot reliably cancel the active message.** Service Bus assigns a new sequence number when a scheduled message transitions to active.

### 11.3. Race Condition Between Cancel and Activation

If an app calls cancel right around activation time, both operations can race. Per service behavior, there is no guarantee an in-flight cancel reverts an activation already underway.

Therefore, workflows must never rely solely on **`cancelScheduledMessage`** to ensure "no reminder email sent":

1. When the customer pays, set order status = `PAID` in the database.
2. Attempt to cancel the scheduled message if still pending.
3. When the reminder consumer receives the message, re-read order status.
4. If `PAID`, **complete the message without sending an email**.
5. If `UNPAID` and still within business validity, send the reminder idempotently.
6. Audit the decision to send or skip.

**Business state is the final source of truth**; cancellation is simply an optimization to avoid unnecessary work.

### 11.4. Sequence Numbers Are Not MessageIds

| Value | Created By | Purpose |
|---|---|---|
| `MessageId` | Producer | Correlation, duplicate detection per entity/config |
| Scheduled sequence | Service Bus on schedule | Cancel message before activation |
| Active sequence | Service Bus when message activates | Identify message once enqueued |
| `SessionId` | Producer | Group workflow/session |
| Lock token | Broker/receiver | Settle one PeekLock delivery |

Never pass a `MessageId` to **`cancelScheduledMessage`**, or mistake an active sequence number for a pending schedule handle.

## 12. Deferral: Intentionally Setting Aside a Received Message

A **deferred message** arises when **a consumer already received a message**, sees a prerequisite is missing, and wants to handle it later.

Example:

1. Worker receives **`PaymentConfirmed(orderId=481)`**.
2. No `OrderCreated` / order 481 record exists yet in the target system.
3. Worker **defers** `PaymentConfirmed`.
4. Worker durably stores the **sequence number** keyed by `orderId`.
5. Once `OrderCreated` arrives, the worker retrieves the deferred message by sequence number.
6. Processes and completes it.

~~~mermaid
flowchart TD
    A["PaymentConfirmed arrives in queue"] --> B["Receiver acquires PeekLock"]
    B --> C{"OrderCreated exists?"}
    C -->|Yes| D["Process + Complete"]
    C -->|No| E["Defer + persist sequence number"]
    E --> F["OrderCreated signal arrives"]
    F --> G["receiveDeferredMessage(sequence)"]
    G --> H["Process + Complete"]
~~~

### 12.1. Where Do Deferred Messages Live?

Deferred messages **remain inside the main queue or subscription**—they do not move to a separate DLQ. They are excluded from **normal receives**, though they can still be inspected via **peek/browse** where supported.

To retrieve one, call the **sequence number** receive API. There is no automatic "un-defer after 10 minutes" timer.

### 12.2. Why Not Use Abandon?

**Abandon** returns the message to normal delivery and increments delivery count per service mechanics. If the prerequisite is still missing, workers repeatedly receive and abandon, causing:

- Unnecessary hot loops and traffic.
- `MaxDeliveryCount` breaches sending messages into the DLQ.
- Higher operation fees and throttling.
- One message stalling healthy messages behind it.

**Defer** fits when a specific missing condition prevents immediate processing yet requires intentional retention.

### 12.3. When Not to Use Defer

If a **shared database needed by every message goes down**, never defer every incoming message and build a massive list of sequence numbers. Instead, **pause receiving**, use backoff retries / circuit breakers, and monitor dependency health.

If you simply want processing **10 minutes later regardless of whether it was received yet**, scheduling or delayed retry queues fit better. Deferred messages require **a stateful wake-up mechanism**, not a built-in timer.

## 13. Java Hands-On: Deferring and Retrieving by Sequence Number

Using **`deferred-lab`** with a receiver in PeekLock mode. For easy testing, this demo supports two run modes:

- Without **`DEFERRED_SEQUENCE`** set: receives one message and defers it.
- With **`DEFERRED_SEQUENCE`** set: retrieves the deferred message and completes it after checks.

### 13.1. Class DeferralDemo

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.messaging.servicebus.ServiceBusClientBuilder;
import com.azure.messaging.servicebus.ServiceBusReceivedMessage;
import com.azure.messaging.servicebus.ServiceBusReceiverClient;
import com.azure.messaging.servicebus.models.ServiceBusReceiveMode;

import java.time.Duration;
import java.util.Iterator;

public final class DeferralDemo {
    public static void main(String[] args) {
        String fqdn = System.getenv("SERVICEBUS_FQDN");
        String savedSequence = System.getenv("DEFERRED_SEQUENCE");

        try (ServiceBusReceiverClient receiver =
                 new ServiceBusClientBuilder()
                   .credential(fqdn,
                     new DefaultAzureCredentialBuilder().build())
                   .receiver()
                   .queueName("deferred-lab")
                   .receiveMode(ServiceBusReceiveMode.PEEK_LOCK)
                   .buildClient()) {

            if (savedSequence == null || savedSequence.isBlank()) {
                Iterator<ServiceBusReceivedMessage> it =
                    receiver.receiveMessages(
                        1, Duration.ofSeconds(20)).iterator();

                if (!it.hasNext()) {
                    System.out.println("No active message available");
                    return;
                }

                ServiceBusReceivedMessage message = it.next();
                long sequence = message.getSequenceNumber();

                // DEMO: assume prerequisite data is not ready yet.
                receiver.defer(message);
                System.out.println(
                    "Deferred sequenceNumber=" + sequence);
                // Production: persist sequence + entity + business key.
            } else {
                long sequence = Long.parseLong(savedSequence);
                ServiceBusReceivedMessage message =
                        receiver.receiveDeferredMessage(sequence);

                if (message == null) {
                    throw new IllegalStateException(
                        "Deferred message not found: " + sequence);
                }

                // Real system: verify prerequisites,
                // then execute idempotent business operation.
                System.out.println(
                    "Received deferred MessageId="
                        + message.getMessageId());
                receiver.complete(message);
            }
        }
    }
}
~~~

**Before running**, send a test message into **`deferred-lab`** and verify no other consumer grabs it first. The first run prints the sequence number; pass that value as **`DEFERRED_SEQUENCE`** on the next test run.

### 13.2. Sending a Test Message

~~~java
// Fragment inserted into a method holding a sender for deferred-lab.
ServiceBusMessage message =
    new ServiceBusMessage(
        "{\"type\":\"PaymentConfirmed\",\"orderId\":\"lab-481\"}")
    .setMessageId("payment-lab-481");

sender.sendMessage(message);
~~~

This is a **code fragment**, not a complete class. Never send mock payment events into a production queue.

### 13.3. Why Persist the Sequence Number Durably?

If a consumer defers a message and then crashes, a sequence number held only in memory or local logs is lost. The message stays in the queue while the workflow has no clue which number to pass to **`receiveDeferredMessage`**.

Persist a record in a database or workflow store:

~~~text
DeferredWork {
    namespace: "sb-orders-lab"
    entity: "deferred-lab"
    messageId: "payment-lab-481"
    orderId: "lab-481"
    sequenceNumber: 34751
    state: "WAITING_FOR_ORDER"
    createdAtUtc: "..."
    nextCheckAtUtc: "..."
}
~~~

The sequence number above is **illustrative**, not from a live queue.

Guard consistency between **persisting the record and calling defer**: they touch two systems with no shared transaction. If a crash happens between them, rely on **reconciliation** via message browsing, correlation IDs, safe retries, or stateful workflows so messages are never orphaned.

### 13.4. Deferred Messages Past TTL

An important detail: **deferred messages are not necessarily moved to the DLQ immediately when TTL expires** the way active messages are. Expiration checks can occur when a client attempts to retrieve by sequence number, at which point the service handles the expired message per entity/DLQ settings.

Therefore:

- Never keep deferred messages indefinitely.
- Enforce business timeouts in your workflow store.
- Run reconciliation jobs to spot forgotten sequence numbers.
- Define handling when a deferred message vanishes or expires past TTL.
- Monitor DLQs and workflow tables, not just `ActiveMessageCount`.

## 14. Scheduling and Deferral Are Not the Same Waiting Queue

A common design error is calling **`deferMessage`** expecting the message to "wake back up" after a fixed delay.

| Scenario | What to Use | Reason |
|---|---|---|
| "Remind on order after 30 minutes" | Scheduled message | Broker activates after timestamp |
| "Payment arrived; waiting for `OrderCreated`" | Deferral | Waiting on an external business event |
| "API failed transiently; retry in 5 minutes" | Scheduled retry/new message or orchestrator | Time-based retry with bounded attempts |
| "Two messages must commit to two entities atomically" | Appropriate transaction | Atomic broker operations |
| "All messages for an order must run sequentially" | Sessions by design | Sequence numbers alone do not enforce cross-consumer ordering |
| "Run report every day at 09:00" | Scheduler/cron + message | Scheduling one message does not recur |

**Combining deferral with scheduling** works nicely: when deferring a message, schedule **a wake-up/check message** a few minutes ahead. When that signal activates, the worker uses the stored sequence number to retrieve the deferred message.

Wake-up messages can also arrive twice, arrive late, or fail cancellation. Keep idempotency and workflow state to handle them safely.

## 15. Combining All Three Features in a Payment Workflow

Suppose upon creating order 481, the system needs to:

1. Emit **`OrderCreated`**.
2. Schedule **`PaymentReminder`** 30 minutes later.
3. If **`PaymentConfirmed`** arrives downstream ahead of **`OrderCreated`**, defer the payment.
4. Once `OrderCreated` arrives, retrieve the deferred payment and update state.
5. Once paid, cancel the reminder if still pending.
6. If the reminder already activated, its consumer checks order state before sending.

~~~mermaid
flowchart TB
    API["Orders API"] --> OUTBOX["Database Outbox"]
    OUTBOX --> PUB["Publisher"]
    PUB --> ORDER["Service Bus: OrderCreated"]
    PUB --> SCHED["Scheduled PaymentReminder"]
    PAYMENT["PaymentConfirmed"] --> WORKER["Payment Worker"]
    WORKER --> READY{"Order record exists?"}
    READY -->|No| DEFER["Defer PaymentConfirmed<br/>Save sequence"]
    ORDER --> CREATE["Order projection updated"]
    CREATE --> RECV["Receive deferred by sequence"]
    RECV --> DONE["Process payment idempotently"]
    READY -->|Yes| DONE
    DONE --> CANCEL["Try cancel reminder"]
    SCHED --> REM["Reminder consumer"]
    REM --> STATE{"Order is paid?"}
    STATE -->|Yes| SKIP["Complete without reminding"]
    STATE -->|No| SEND["Send reminder idempotently"]
~~~

### 15.1. Order State Table

| Order State | Payment Event | Scheduled Reminder | Behavior |
|---|---|---|---|
| CREATED / UNPAID | None yet | Pending | Await payment; remind when due |
| CREATED / UNPAID | CONFIRMED | Pending | Record `PAID`, attempt to cancel reminder |
| No order projection yet | CONFIRMED | Unrelated | Defer `PaymentConfirmed`, store sequence |
| PAID | Reminder active | Activated | Complete reminder without sending |
| CANCELLED | Reminder pending | Pending | Attempt cancel; check state if reminder fires |
| CANCELLED | Reminder active | Active | Complete/audit without sending |

Every step updating DB and broker must tolerate crashes. A Service Bus transaction never syncs **`Orders`** state with SQL automatically; combine outbox, idempotency, workflow state, and compensation per design.

### 15.2. Crashing After DB Update but Before Complete

If Payment Worker updates **`Orders.state=PAID`** and crashes before **`complete`**:

- The lock expires and the message is redelivered.
- The consumer recognizes **the payment event was already processed** via event ID / order state.
- It completes the redelivered message **without recording a second payment**.
- When using an outbox for follow-up events, ensure outbox rows and business state commit in the same DB transaction.

This highlights the difference between "at-least-once delivery" and "effectively-once business effect."

### 15.3. Reminder Already Active When Cancel Runs

The reminder consumer must still inspect **business state** before sending. To prevent two workers from simultaneously sending the same reminder, guard with a unique-keyed notification record or atomic transition like **`PENDING → SENDING → SENT`**, backed by timeouts, reconciliation, and bounded retries.

Canceling a scheduled message is never an absolute distributed lock or universal side-effect cancellation token.

## 16. Duplicate Detection, MessageId, and Idempotency

### 16.1. Duplicate Detection

Azure Service Bus supports **duplicate detection** on compatible tiers/entities, typically keyed on **`MessageId`** over a configured window (with additional rules when partitioning/sessions apply).

For example, if a producer is unsure whether **`OrderCreated(orderId=481)`** reached Service Bus, resending with the same `MessageId` when duplicate detection is enabled lets the broker drop the duplicate within the window.

### 16.2. What Duplicate Detection Does NOT Solve

- Does not prevent double charges in SQL or external payment gateways.
- Does not detect duplicates after the dedup window expires.
- Cannot rescue producers that mint a new random `MessageId` on every retry.
- Does not prevent two different event types on the same order from processing out of order.
- Does not replace database unique constraints or consumer idempotency.
- Does not turn Service Bus transactions into distributed transactions.

### 16.3. Designing MessageId

Examples:

~~~text
OrderCreated:
  MessageId = "order-481-created-v1"

PaymentConfirmed:
  MessageId = "payment-provider-event-9c5..."

PaymentReminder:
  MessageId = "order-481-reminder-30m"
~~~

Never put sensitive PII in `MessageId` if it appears in logs or telemetry. For workflows emitting multiple reminders, include **`reminder type + attempt/run key`** intentionally so valid reminders are not silently dropped.

## 17. Sessions, Ordering, and Deferred Messages

### 17.1. Sequence Numbers Do Not Guarantee Completion Order

Service Bus assigns sequence numbers to identify messages and reflect ingest order within entity/partition bounds. Two consumers can still process and complete messages **out of order** due to differing execution times.

If a sequence of messages for the same order must run serially, evaluate **Service Bus Sessions**:

~~~text
Order 481:
   OrderCreated (SessionId=order-481)
   PaymentConfirmed (SessionId=order-481)
   PrepareShipment (SessionId=order-481)
~~~

Sessions provide lock/affinity per session in supported models. Yet **sessions do not guarantee every event arrives in business order**: events can still be emitted out of order from multiple sources. Deferral may still be required when prerequisites are missing, alongside session/workflow state.

### 17.2. Session-Aware Deferral

On session-enabled entities, receiving deferred messages must use the matching session receiver context. Never use a non-session receiver to fetch a sequence number belonging to a session. Verify **`ServiceBusSessionReceiverClient`/`ServiceBusReceiverClient`** APIs and session-lock rules in your SDK version.

### 17.3. When to Avoid Sessions?

If every message is fully independent and throughput is paramount, session affinity adds coordination overhead and unnecessary concurrency constraints. Do not enable sessions on every queue just because you want sequence numbers or deferral.

## 18. TTL, DLQ, and MaxDeliveryCount Across the Three Mechanisms

### 18.1. Active Message TTL

Messages carry a TTL bounding retention if unprocessed. Upon expiration, Service Bus either discards the message or moves it to the DLQ if dead-letter-on-expiration is enabled.

### 18.2. Scheduled TTL

A scheduled message becomes meaningful for delivery only after its scheduled enqueue/activation time. Thus **TTL evaluates relative to scheduled enqueue time** per service mechanics, not just the time the schedule request was sent.

This matters for reminders: an overly short TTL can expire a reminder before a backed-up consumer ever pulls it.

### 18.3. Deferred TTL

Deferred messages have special expiry behavior: they can sit inside the entity past TTL and only get checked/moved when a client tries to receive them by sequence number. Pair with reconciliation and an expired-deferred handling strategy.

### 18.4. MaxDeliveryCount and DLQ

Repeatedly abandoning or expiring locks increments delivery count. Once it exceeds **`MaxDeliveryCount`**, the message can move to the DLQ.

| Scenario Type | Appropriate Handling |
|---|---|
| Brief transient error | Abandon or bounded backoff retries |
| Prolonged outage | Scheduled retry with state/attempt tracking, per workflow |
| Missing prerequisite event | Defer + persist sequence and trigger |
| Invalid / poison message | Dead-letter with reason and correlation ID |
| Ambiguous transaction commit | Reconcile outcome + idempotent retry |
| Cannot finish before TTL | Adjust TTL, capacity, or workflow policy |

Never dump every failing message into the DLQ and ignore it. Build inspection/reprocessing runbooks, retention policies, alerts, and DLQ access controls.

## 19. Combining Transactions with Scheduling: Principles and Risks

Some Service Bus SDKs, including **`ServiceBusSenderClient`** in the Azure SDK for Java, support passing **`ServiceBusTransactionContext`** into `scheduleMessage`.

Java API example:

~~~java
ServiceBusTransactionContext tx = sender.createTransaction();

try {
    sender.sendMessage(
        new ServiceBusMessage("OrderCreated"), tx);

    sender.scheduleMessage(
        new ServiceBusMessage("PaymentReminder"),
        OffsetDateTime.now(ZoneOffset.UTC).plusMinutes(30),
        tx);

    sender.commitTransaction(tx);
} catch (RuntimeException error) {
    try {
        sender.rollbackTransaction(tx);
    } catch (RuntimeException rollbackError) {
        error.addSuppressed(rollbackError);
    }
    throw error;
}
~~~

This is a **snippet inside a class/method with an existing sender and imports**, illustrating operations on **one queue** within the broker. If sending a message to queue A while scheduling a reminder on queue B, verify and configure cross-entity transactions where supported.

### 19.1. Note on Scheduled Sequence Numbers Inside Transactions

To cancel later, the app must persist the **sequence number** returned by **`scheduleMessage`** along with business key and entity. Yet **writing the sequence number to SQL and committing the Service Bus transaction are not mutually atomic**.

Appropriate handling plan:

- Use outbox/workflow state and result confirmation.
- Transition **`SCHEDULE_REQUESTED → SCHEDULED`** once broker commit confirms.
- On ambiguous commit outcome, reconcile before rescheduling.
- Reminder consumers still inspect order state instead of relying blindly on cancellation.
- Never delete tracking records merely because cancel threw an exception.

### 19.2. Never Hold a Transaction Open Until Activation

A transaction lives briefly to commit the **schedule** operation—never open until the reminder fires 30 minutes later. The broker stores schedules independently; no connection or transaction needs to stay open for 30 minutes.

## 20. Deferred Message + Scheduled Wake-Up

This workflow pattern combines both features while keeping responsibilities distinct:

1. Consumer receives **`PaymentConfirmed`**.
2. Order not yet present → persist deferred sequence number in workflow store and defer message.
3. Schedule a **`WakeDeferredPayment`** 5 minutes ahead.
4. When the wake-up activates, a worker checks the order.
5. If the order now exists → receive the deferred message by sequence, process, and complete.
6. If still missing → schedule the next check with an attempt counter and deadline.
7. Past deadline → transition business state to **`NEEDS_REVIEW`** or emit an error event.
8. Run a reconciliation job scanning unresolved deferred records.

~~~mermaid
flowchart TD
    P["Payment message"] --> D["Defer + store sequence"]
    D --> W["Schedule WakeUp in 5 min"]
    W --> Q{"Order ready?"}
    Q -->|Yes| R["Receive deferred by sequence"]
    R --> OK["Idempotent processing + complete"]
    Q -->|No and within deadline| W2["Schedule next check"]
    Q -->|Past deadline| DL["Alert / manual review"]
~~~

**Never create infinite wake-up loops**: enforce attempt caps, business deadlines, and correlation IDs. Failed wake-up messages also need their own retry/DLQ policy.

## 21. Designing Safely Against Network Faults and Crashes

### 21.1. Five Common Failure Gaps

| Crash Point | Possible Outcome | Mitigation |
|---|---|---|
| After SQL commit, before Service Bus send | Order exists in DB with no event | Transactional outbox |
| After Service Bus send, before marking outbox sent | Event sent, yet publisher will retry | Stable `MessageId` + dedup / idempotent consumer |
| After defer, before persisting sequence | Message sits in queue with unknown sequence | Controlled state persistence, reconciliation/peek |
| After canceling reminder, before DB update | Uncertain cancel outcome | Business state as source of truth; consumer re-checks |
| After completing message, before writing external audit | Audit lost if stored separately | Outbox or persist audit prior to settlement per design |

### 21.2. Idempotent Processing Protocol

A consumer can follow:

~~~text
function process(message):
    eventId = message.messageId

    begin DB transaction
        if processedEvents contains eventId:
            result = ALREADY_PROCESSED
        else:
            validate business preconditions
            apply state change once
            insert processedEvents(eventId)
            insert outbox follow-up events
    commit DB transaction

    complete Service Bus message

    # Separate publisher dispatches outbox events with stable MessageId.
~~~

This is **pseudocode**, not runnable Java. If `complete` fails after DB commit, the message redelivers, the consumer sees `eventId` in `processedEvents`, and it completes cleanly without duplicating business effects.

### 21.3. Preventing Lost Messages from Long Processing

- Use PeekLock and renew locks when necessary.
- Set sensible timeouts; avoid unbounded blocking calls.
- Never treat lock duration as an SLA for multi-hour business transactions.
- Break long processing into workflow states.
- Scale worker concurrency cautiously, adding sessions if ordering is required.
- Implement graceful shutdown and clean client closing.
- Classify transient, permanent, authorization, quota, and poison errors.

## 22. Observability and Operations

### 22.1. Metrics to Track

| Metric | Meaning |
|---|---|
| Active messages | Receivable messages; detects backlogs |
| Scheduled messages | Pending scheduled volume; catches abnormal spikes |
| Dead-letter messages | Messages quarantined in DLQ needing triage |
| Incoming / outgoing messages | Producer/consumer traffic rates |
| Successful requests / server errors / user errors | Categorized broker call health |
| Throttled requests | Throughput/credit and capacity limits hit |
| Transaction failures / timeouts | Impact on atomic operations |
| Lock lost / delivery count | Slow handlers, retries, or contention |
| Deferred records in workflow store | Unresolved deferred messages awaiting prerequisites |
| Schedule cancel failures | Risk of reminders still activating |
| Time from scheduled activation to processed | Measures real processing lag past target time |

Not every KPI is exposed **out of the box** by Azure Monitor; metrics like business deferred backlogs, ambiguous transaction commits, or activation-to-process lag normally require **application telemetry / workflow stores**.

### 22.2. Logs and Traces to Emit

A log record should look like:

~~~json
{
  "event": "PAYMENT_MESSAGE_DEFERRED",
  "traceId": "trace-example",
  "orderId": "lab-481",
  "messageId": "payment-lab-481",
  "entity": "deferred-lab",
  "sequenceNumber": 34751,
  "timestampUtc": "2026-11-20T11:00:00Z",
  "reason": "ORDER_NOT_FOUND"
}
~~~

This uses **sample data**; never write PII or sensitive payment payloads to logs. Log only needed attributes and enforce retention and access controls per policy.

Important lifecycle events to capture:

- `TRANSACTION_BEGIN` / `COMMIT_SUCCEEDED` / `COMMIT_UNKNOWN` / `ROLLBACK_FAILED`.
- `MESSAGE_SCHEDULED` / `SCHEDULE_CANCEL_ATTEMPTED` / `REMINDER_SKIPPED`.
- `MESSAGE_DEFERRED` / `DEFERRED_RETRIEVED` / `DEFERRED_EXPIRED`.
- `DEAD_LETTERED` / `REPROCESSED`.
- `LOCK_RENEWED` / `LOCK_LOST`.
- `RETRY_SCHEDULED` / `RETRY_EXHAUSTED`.

### 22.3. Azure Monitor and Azure Cost Management

Open **Service Bus namespace → Monitoring / Metrics** in the Azure Portal to inspect message counts, request metrics, and errors/throttling. For detailed logs, enable **Diagnostic settings** for supported categories targeting Log Analytics, Storage, or Event Hubs per policy.

Messaging observability goes beyond raw message counts. Define **business SLOs**, for example:

- 99% of `PaymentConfirmed` events process within 2 minutes once prerequisites exist.
- Zero unresolved deferred records older than 2 hours without an alert.
- Scheduled reminders are evaluated by consumers within 5 minutes of activation.
- Zero ambiguous transaction outcomes left unreconciled past a set window.
- DLQs are triaged on an operational schedule.

These numbers are **illustrative SLOs**, not Azure-guaranteed SLAs.

## 23. Symptom-Driven Troubleshooting Guide

| Symptom | Common Causes | Remediation |
|---|---|---|
| Transaction fails / times out | Processing too slow, wrong entity/client, lock lost | Shorten transaction, check timeout and SDK |
| Sent two messages, only one appears | Missing transaction, ambiguous commit, consumer already read, differing filters | Check transaction logs, entity, `MessageId`, consumer/DLQ |
| Commit errored yet message appeared | Ambiguous outcome on network drop | Reconcile via idempotency/dedup; never resend with new ID |
| Scheduled message absent in receive | Activation timestamp not yet reached | Verify UTC time and scheduled count |
| Scheduled message processed late | Consumer offline, backlog, or capacity limits | Check activation time, receiver health, queue depth |
| Cancel had no effect | Message already active, raced activation, or wrong sequence | Inspect business state, sequence/entity; guard side effects |
| Deferred message absent in normal receive | Expected deferral behavior | Retrieve via `receiveDeferredMessage(sequence)` |
| Lost deferred sequence number | State not saved, consumer crashed | Reconcile via peek/browse and correlation ID |
| Cannot retrieve deferred message | Wrong queue/session/sequence, TTL, or lock/auth error | Verify entity, session, expiration, and permissions |
| Message dead-lettered by `MaxDeliveryCount` | Excessive retries, abandons, or lock expirations | Read DLQ reason, fix consumer and retry policy |
| 401 / 403 | Wrong RBAC, SAS, or identity | Check Data Sender/Receiver roles and propagation |
| Service Bus connection timeout | Firewall, DNS, Private Endpoint, AMQP/WebSockets | Verify network path and TLS |
| Backlog grows despite many consumers | Throttling, hot session key, slow database | Inspect throughput, locks, capacity, and dependencies |
| Total cost climbs | High operations, retries, scheduled churn, Premium units/logs | Check Cost Management, metrics, and workflow retries |

### 23.1. Steps to Debug a Scheduled Message

1. Confirm namespace, entity, and `MessageId`.
2. Confirm Service Bus accepted the schedule call.
3. Capture the **scheduled sequence number** and scheduled enqueue time.
4. Check UTC clocks and timing around activation.
5. Check whether any cancel or replacement occurred.
6. After activation time, inspect active counts and consumer logs.
7. Check TTL/DLQ if the message vanished.
8. Inspect business state to decide whether to reprocess or ignore.

### 23.2. Steps to Debug a Deferred Message

1. Identify the order/workflow key and where the deferred sequence number was stored.
2. Confirm the right namespace/queue or topic subscription.
3. On session-enabled entities, verify `SessionId` and session receiver context.
4. Try **`receiveDeferredMessage(sequence)`** in an authorized environment.
5. If missing, check TTL, DLQ, prior completion, and reconciliation logs.
6. Process prerequisites and side effects idempotently.
7. Complete the message and mark the workflow finished.
8. Clean up/update the deferred tracking row only after confirmation—never unconditionally on ambiguous outcomes.

### 23.3. Steps to Debug a Transaction

1. Identify the transaction context and participating operations.
2. Confirm the tier, namespace, and entity support transactions.
3. Verify PeekLock receives did not lose locks.
4. Check timeouts and latency of each step.
5. If cross-entity, verify SDK configuration and transfer routing.
6. Inspect error messages and correlation/diagnostic IDs.
7. On ambiguous commit outcomes, **reconcile**—never assume rollback occurred.
8. Verify duplicate detection and idempotency before retrying.
9. Shrink transaction duration or batch size if hitting limits.
10. Document findings and data-plane status in the runbook.

## 24. Cost, Quotas, and Performance

### 24.1. Why Do These Three Mechanisms Affect Cost?

- Transactions add coordination/commit steps and can increase latency across grouped calls.
- Scheduling holds pending messages in the broker and activates them later, increasing operations.
- Deferral adds extra settlement and explicit receive calls, plus workflow state storage and reconciliation.
- Excessive retries amplify requests, network traffic, DLQ volume, and log ingestion.
- Premium bills via Messaging Units; Standard includes per-operation charges per pricing tables.
- Azure Monitor, Log Analytics, and Storage/SQL workflow stores carry their own charges.

There is no universal fixed formula like "every deferred message costs X" across all tiers and regions. Use official pricing tables and real metrics.

### 24.2. Illustrative Load Estimation

A system processes **100,000 orders/day**. Each order generates:

- 1 `OrderCreated` event.
- 1 scheduled `PaymentReminder`.
- 1 cancel attempt for early-paid orders, say 80%.
- 1 `PaymentConfirmed` handling, some fraction triggering deferral.
- 1–2 retries on failure paths.

Raw business event counts differ substantially from total **broker requests** once you sum sends, receives, completes, schedules, cancels, defers, retrieves, retries, and DLQs.

Sample workload table:

| Operation Type | Estimated Ops/Day | Notes |
|---|---:|---|
| `OrderCreated` send | 100,000 | Excludes publish retries |
| Schedule reminder | 100,000 | 1 per order |
| Cancel attempts | 80,000 | Assuming 80% pay early |
| `PaymentConfirmed` receive/settle | Scales with payment traffic | May include retries |
| Defer + retrieve | Scales with out-of-order rate | Counts two broker ops plus state store |
| DLQ / monitoring | Scales with failure rate | Adds operational overhead |

This model is **illustrative**, not an Azure billing quote. Estimate using **Service Bus pricing**, message sizes, Premium units / Standard operations, tier, entity counts, throughput, and retention.

### 24.3. Performance

- Prefer long-lived clients rather than opening/closing per message.
- Use batching/async where appropriate while checking batch sizes and transaction limits.
- Keep transactions short; avoid slow network calls inside open transactions.
- Tune concurrency to downstream databases and session constraints.
- Watch lock duration, renewals, prefetch, and max concurrent calls.
- Guard against hot partitions/sessions when partitioning or sessions are used.
- Never schedule millions of messages without checking quotas, storage limits, and cost.
- Configure timeouts/retries/backoff for transient failures; inside transactions, follow SDK-specific retry rules.

## 25. Security and Production Operations

### 25.1. IAM and Permissions

- Producers use **Azure Service Bus Data Sender**; receivers use **Data Receiver**.
- Managed identities / Workload Identities grant zero permissions on their own; assign scoped roles explicitly.
- Keep connection strings, SAS keys, and tokens out of logs and Git.
- Separate namespace admin, send, receive, DLQ, and read-only monitoring roles.
- Evaluate Azure RBAC separately from application-level business authorization.

### 25.2. Networking and Encryption

- Enforce TLS, DNS, and connectivity per Service Bus requirements.
- With Private Endpoints, configure private DNS, VNet integration/peering, and firewalls properly.
- Restrict client networks and egress where required.
- Never leak sensitive queue payloads into metrics or logs.
- Check AMQP-over-WebSockets proxy support if port 5671 is blocked in your environment.

### 25.3. Schema and Version Governance

Messages should include:

~~~json
{
  "eventType": "PaymentConfirmed",
  "schemaVersion": 1,
  "eventId": "payment-event-xyz",
  "orderId": "lab-481",
  "occurredAtUtc": "2026-11-20T11:00:00Z"
}
~~~

Consumers must handle schema versions, unknown fields, idempotency, and correlation IDs. Never place payment card details, access tokens, or unnecessary PII into message bodies.

### 25.4. Production Runbook

Before going live:

1. Document all entities, owners, TTLs, `MaxDeliveryCount`, and DLQs.
2. Document transaction boundaries and external data dependencies.
3. Persist scheduled/deferred state in a durable store.
4. Provide tooling to trace workflows by `orderId` / `MessageId` / sequence number.
5. Alert on overdue deferred records and growing scheduled backlogs.
6. Define reconciliation procedures for ambiguous commit outcomes.
7. Test cancel/activation races, post-defer crashes, and lost locks.
8. Prepare code and schema rollback plans.
9. Audit identities, networking, retention, and cost.

## 26. Design Checklist

- [ ] Distinguished transactions, scheduling, and deferral by exact purpose.
- [ ] Verified namespace and tier support every required feature.
- [ ] Producers/consumers use current SDKs with Entra ID and least-privilege RBAC.
- [ ] Receivers needing settlement run in **PeekLock**, never ReceiveAndDelete.
- [ ] Transactions contain only supported Service Bus operations and stay short.
- [ ] Cross-entity transactions configured per SDK only when truly required.
- [ ] Service Bus transactions are never mistaken for SQL/Cosmos/HTTP transactions.
- [ ] Transactional outbox and idempotency protect data stored outside the broker.
- [ ] Stable `MessageId`s and properly sized duplicate detection windows configured.
- [ ] Scheduled enqueue times computed in UTC with proper timezone conversion.
- [ ] Scheduled sequence numbers persisted with entity and business key.
- [ ] Handled races between schedule cancellation and activation.
- [ ] Reminder consumers always check business state before firing side effects.
- [ ] Deferred sequence numbers durably persisted with reconciliation.
- [ ] Deferral never mistaken for a self-waking timer.
- [ ] TTL, `MaxDeliveryCount`, DLQ, and lock renewal designed.
- [ ] Bounded retries and poison-message handling in place.
- [ ] Monitoring tracks active/scheduled/DLQ counts plus deferred workflow states.
- [ ] Runbooks cover ambiguous commits, expired deferred messages, and redeliveries.
- [ ] Tested network faults, rollbacks, concurrency, restarts, and scaling.
- [ ] Estimated costs for operations/Premium units, storage, and logging.

## 27. Hands-On Exercises

### Exercise 1: Pick the Right Mechanism

Classify each scenario:

1. "Send `OrderCreated` and `AuditRequested` so both succeed or both roll back."
2. "Send a reminder 30 minutes later if the customer hasn't paid."
3. "Received `PaymentConfirmed`, yet the corresponding order record doesn't exist yet."
4. "Run a report every day at 09:00."
5. "Three messages for one order must be processed sequentially by consumers."
6. "After committing SQL, guarantee the event still publishes even if the app crashes."

Explain why each requires transactions, scheduling, deferral, a scheduler, sessions, or an outbox respectively.

### Exercise 2: Transaction Send and Rollback

In a Standard lab namespace:

1. Create queue `tx-lab`.
2. Create a Java sender using `DefaultAzureCredential`.
3. Open a transaction, send two messages, and commit.
4. Inspect the queue for both messages.
5. Inject an error before commit and roll back.
6. Describe how to handle a commit timeout with an ambiguous outcome.

### Exercise 3: Scheduling and Cancellation

1. Schedule a message 5 minutes ahead.
2. Record its sequence number and UTC timestamp.
3. Cancel it prior to activation to verify.
4. Schedule another message and allow it to activate.
5. Explain why the scheduled sequence number may no longer cancel the message after activation.
6. Design a business-state check guarding against race conditions.

### Exercise 4: Deferred Messages

1. Send a test `PaymentConfirmed` into `deferred-lab`.
2. Receive it in PeekLock mode.
3. Defer it and save its sequence number.
4. Confirm normal receives do not return that deferred message.
5. Retrieve it via `receiveDeferredMessage(sequence)`.
6. Complete it and update the workflow store.
7. Describe how to recover if the sequence number was lost.

### Exercise 5: Inspecting TTL and DLQ

Set up a test environment with short TTL and `MaxDeliveryCount` to observe:

- An active message expiring.
- A message abandoned repeatedly.
- A deferred message sitting past TTL and then retrieved.
- A message landing in the DLQ after dead-lettering.

Run strictly on a lab queue and document exact observed behavior per entity settings.

### Exercise 6: Transactions Outside Service Bus

Orders API writes SQL and sends `OrderCreated`. Diagram two crash cases:

- SQL committed, yet Service Bus send never ran.
- Service Bus send succeeded, yet outbox was not marked published.

Propose a transactional outbox + stable `MessageId` + idempotent consumer design.

### Exercise 7: Combined Workflow

Design a payment system:

- `PaymentConfirmed` can arrive ahead of `OrderCreated`.
- Remind after 30 minutes if unpaid.
- The customer might pay right as the reminder activates.
- Any worker can crash at any step.

Draw the state machine, sequence-number storage, committed states, and duplicate-reminder guards.

### Exercise 8: Capacity and Cost Estimation

A system receives 50,000 orders/day, averaging 2 messages per order, 70% reminder cancellations, and 5% of payment events deferred.

Estimate rough send, schedule, cancel, defer, and retrieve counts, then explain why those numbers **do not equal billed operations** once completes, retries, TTLs, DLQs, batching, and tiers are factored in.

### Self-Check Questions

1. Does a Service Bus transaction include an Azure SQL transaction?
2. Is the receive operation itself part of a Service Bus transaction?
3. Why shouldn't a transaction stay open while waiting on slow HTTP responses?
4. When a transaction commit times out, can you be sure a rollback happened?
5. How does a transaction differ from duplicate detection?
6. Does scheduling guarantee a consumer finishes processing at that exact timestamp?
7. What is a scheduled sequence number used for?
8. Can canceling a scheduled message close to activation race with activation?
9. Can `MessageId` replace sequence numbers when canceling?
10. Does a deferred message live in the DLQ or the main queue?
11. Why does `receiveMessages` skip deferred messages?
12. What should you do if a deferred sequence number is lost?
13. Does calling defer automatically redeliver the message after 5 minutes?
14. When should you pause receiving instead of deferring every message?
15. Are expired deferred messages automatically purged the instant TTL passes?
16. Why are sessions needed when strict processing order is required?
17. What can repeated `Abandon` calls lead to?
18. How do you prevent double charges even when messages redeliver?
19. Why is canceling a reminder alone insufficient to guarantee no reminder is sent?
20. Which metric reveals forgotten deferred workflows?

## 28. References

- [Azure Service Bus messaging overview — Microsoft Learn](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-messaging-overview)
- [Transactions in Azure Service Bus](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-transactions)
- [Azure Service Bus message sequencing and scheduled messages](https://learn.microsoft.com/azure/service-bus-messaging/message-sequencing)
- [Azure Service Bus message deferral](https://learn.microsoft.com/azure/service-bus-messaging/message-deferral)
- [Message expiration and TTL](https://learn.microsoft.com/azure/service-bus-messaging/message-expiration)
- [Message transfers, locks and settlement](https://learn.microsoft.com/azure/service-bus-messaging/message-transfers-locks-settlement)
- [Dead-letter queues in Service Bus](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-dead-letter-queues)
- [Service Bus duplicate detection](https://learn.microsoft.com/azure/service-bus-messaging/duplicate-detection)
- [Message sessions](https://learn.microsoft.com/azure/service-bus-messaging/message-sessions)
- [Azure SDK for Java — Service Bus client library](https://learn.microsoft.com/java/api/overview/azure/messaging-servicebus-readme)
- [ServiceBusSenderClient Java API](https://learn.microsoft.com/java/api/com.azure.messaging.servicebus.servicebussenderclient)
- [ServiceBusReceiverClient Java API](https://learn.microsoft.com/java/api/com.azure.messaging.servicebus.servicebusreceiverclient)
- [Service Bus pricing tiers](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-premium-messaging)
- [Azure Service Bus pricing](https://azure.microsoft.com/pricing/details/service-bus/)
