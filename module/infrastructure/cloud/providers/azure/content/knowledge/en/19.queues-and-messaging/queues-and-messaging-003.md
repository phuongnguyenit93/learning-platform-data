# Service Bus Namespace, Queue, Topic, and Subscription

An e-commerce application on Azure receives orders over HTTP. If the API had to synchronously call the payment system, deduct inventory, send emails, and write reports before responding, users would face long wait times; when one downstream service fails, the entire order request risks failing. One way to decouple these components is by sending a **message** to **Azure Service Bus** so workers can process it **asynchronously**.

However, the messaging structure must match business semantics. A **Queue** fits when a job needs to be processed by one of several competing workers. A **Topic** and its **subscriptions** fit when an event must be distributed independently to multiple receiving groups. Both queues and topics live inside a **Service Bus namespace**—the resource, configuration, permission, and network boundary for the service.

This lesson belongs to the **Queues and Messaging** chapter of the `CLOUD_PROVIDERS_AZURE` module. The module walks you through Microsoft Azure from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute, storage, and data; then deploying, monitoring, securing, and controlling costs for an application architecture. Here, the focus is designing the **core building blocks of Azure Service Bus** and operating them as part of a reliable application architecture.

> Resource names, SKUs, quotas, networking features, SDKs, and CLI syntax may vary by version and region. Examples use mock data without real passwords or connection strings. Any commands that create resources or send messages should only be run in an authorized subscription/lab.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the purpose of a **Service Bus namespace**, **queue**, **topic**, **subscription**, and **subscription rule/filter**.
2. Diagram **point-to-point** and **publish/subscribe** processing flows with accurate message-delivery boundaries.
3. Choose between a queue and a topic for a business scenario, distinguishing **competing consumers** from **multiple independent subscribers**.
4. Describe a message's lifecycle: **send → enqueue → receive → complete/abandon/dead-letter/defer**.
5. Distinguish **Peek-Lock** from **Receive-and-Delete**, explaining redelivery and the need for idempotency.
6. Identify the role of **TTL, dead-letter queues, duplicate detection, sessions, filters**, and tier-based support limits.
7. Design identities and authorization using **Microsoft Entra ID / managed identities** instead of embedding SAS connection strings wherever feasible.
8. Create namespaces, queues, topics, and subscriptions in the Azure Portal or via controlled Azure CLI commands.
9. Use the SDK to send/receive messages and observe operational telemetry.
10. Troubleshoot message backlogs, routing to wrong subscriptions, failing workers, or dead-lettered messages.
11. Plan retention, monitoring, security, DR, and cost controls for a messaging system.

## 2. Why Is Asynchronous Messaging Needed?

Compare two order-processing flows.

**Synchronous processing:**

```text
Customer
    |
    v
Orders API
    ├── call Payment API ────── wait
    ├── call Inventory API ──── wait
    ├── call Email API ──────── wait
    └── return response
```

If one dependency is slow or unavailable, the customer's request can time out. All components are also forced to be available simultaneously.

**Asynchronous processing via Service Bus:**

```text
Customer
    |
    v
Orders API
    |
    +-- save order in source system
    |
    +-- publish message/event
    |
    +-- return accepted status
               |
               v
          Service Bus
               |
       +-------+--------+
       |       |        |
     Billing  Inventory  Notifications
      worker    worker      worker
```

Potential benefits:

- API and workers do not need to be online at the exact same moment.
- Messages can wait in queues when workers are busy.
- Workers can scale independently based on backlog.
- Producers do not need to know the concrete addresses of every consumer.
- Settlement and dead-lettering provide controlled handling for failed messages.

However, asynchrony **does not automatically guarantee business completion** the moment the API responds. You must distinguish **order accepted** from **payment captured, inventory reserved, or email sent**. The design must manage final state, failures, retries, and reconciliation.

## 3. Azure Service Bus Resource Hierarchy

A namespace serves as the container boundary for messaging entities. Inside it live queues and topics; each topic can have multiple subscriptions, and each subscription can define rules to filter messages.

```text
Azure subscription (management and billing unit)
└── Resource group: rg-orders-prod
    └── Service Bus namespace: sb-orders-prod
        ├── Queue: charge-command
        │   └── Dead-letter subqueue (DLQ)
        │
        ├── Queue: refunds-command
        │   └── Dead-letter subqueue (DLQ)
        │
        └── Topic: order-events
            ├── Subscription: billing
            │   ├── Rules / filters
            │   └── Dead-letter subqueue
            ├── Subscription: inventory
            │   ├── Rules / filters
            │   └── Dead-letter subqueue
            └── Subscription: audit
                ├── Rules / filters
                └── Dead-letter subqueue
```

**Two different meanings of "subscription":**

- **Azure subscription:** the account/resource, billing, quota, and Azure RBAC boundary.
- **Service Bus topic subscription:** an entity that receives matching messages from **a topic**, with its own backlog and processing policies.

A Service Bus subscription is **not** an Azure subscription, nor is it a Kubernetes subscription or an Event Grid event subscription.

### Configuration Levels

| Level | What Do You Manage? | Example |
|---|---|---|
| Azure subscription / resource group | Resource creation rights, region, policies, budgets. | `rg-orders-prod` |
| **Service Bus namespace** | SKU/tier, endpoint, auth, networking, namespace-level settings, and aggregate metrics. | `sb-orders-prod.servicebus.windows.net` |
| **Queue** | Point-to-point message destination, TTL, lock, DLQ, and entity policies. | `charge-command` |
| **Topic** | Publish endpoint for producers sending to multiple receiving streams. | `order-events` |
| **Topic subscription** | An independent "receiving stream" with its own backlog, consumers, and DLQ. | `inventory` |
| **Rule/filter** | Determines which messages are routed into a subscription. | `eventType = 'OrderPlaced'` |

## 4. Namespace: Management and Connectivity Boundary

A **Service Bus namespace** has its own DNS endpoint, is deployed in a region, and uses a chosen pricing tier. Clients typically connect to an endpoint formatted as:

```text
<NAMESPACE_NAME>.servicebus.windows.net
```

At the namespace level, you typically decide:

1. **Region and tier:** feature availability, cost, and performance predictability.
2. **Application/environment boundary:** Should Production and Development use separate namespaces?
3. **Identity and permissions:** Who can send, receive, and manage?
4. **Network connectivity:** public access, IP restrictions/private endpoints when supported by tier, DNS, and app outbound traffic.
5. **Monitoring and operations:** Azure Monitor, diagnostic logs, alerts, and retention.
6. **DR policy:** impact if the namespace or region becomes unavailable.
7. **Budget:** message volume, throughput, entity count, and cost under the pricing model.

### A Namespace Is Not a Queue

Creating a namespace **does not mean queues or topics exist to receive messages**. Messaging entities must be created explicitly. An application sending to `queue_name="charge-command"` when that queue does not exist will receive an entity-not-found error even if namespace connectivity works.

### Separating Namespaces by Environment

Example:

```text
sb-orders-dev   → Development data and permissions
sb-orders-test  → Integration/performance testing within budget
sb-orders-prod  → Live orders, stricter permissions and alerts
```

You do not necessarily need one namespace per microservice. Splitting namespaces is a decision about **blast radius, quotas, isolation, networking, permissions, and cost**. Multiple queues/topics can share a namespace if security and operational requirements align; however, a development team should never have permission to delete Production queues.

## 5. Choosing a Tier: Basic, Standard, and Premium

Azure Service Bus offers tiers with different features and billing models. Choose the tier **before finalizing your messaging diagram**.

| Criterion | Basic | Standard | Premium |
|---|---|---|---|
| Queue messaging | Yes. | Yes. | Yes. |
| Topic/subscription | **Does not support** Service Bus topic/subscription model. | Yes. | Yes. |
| Resource model | Shared tier environment. | Shared tier environment. | More dedicated resources, Messaging Units capacity model. |
| Throughput/latency predictability | Fits simple needs. | Fits many application workloads. | Typically fits critical workloads needing better isolation/predictable throughput. |
| Networking, advanced messaging, DR | Check feature limits. | Different limits from Premium. | Generally offers more enterprise capabilities, depending on supported features. |
| Target use | Simple queues, minimal requirements. | Queues + publish/subscribe. | Critical workloads, high throughput, or strict network isolation. |

**Rule:** if your workload needs **topics and multiple subscriptions**, do not pick Basic just for its lower price. Conversely, a simple queue does not automatically require Premium. Features such as **sessions, duplicate detection, private endpoints, partitioning, and large messages** have tier/SKU/version constraints; never assume they are supported simply because a namespace exists.

### Premium Does Not Mean Unlimited

Premium provides more dedicated resources but still has **limits on throughput, entity size, concurrent connections, namespace scale, and provisioning capacity**. When scaling Messaging Units or other performance settings, benchmark realistically using your payload size, client count, batching, and latency; do not assume throughput scales linearly for every workload.

## 6. Queue: The Point-to-Point Model

A queue accepts messages from producers and lets one of the consumers process each message once from a business perspective. Multiple workers can **compete for different messages** from the same queue to increase throughput.

```text
Orders API / Producer
        |
        v
Queue: charge-command
        |
        +--> Worker A receives message M1
        +--> Worker B receives message M2
        +--> Worker C receives message M3
        |
        +--> DLQ when message cannot be processed per policy
```

If three workers listen on `charge-command`, Service Bus **does not intentionally send a separate copy of the same message to all three workers** like a broadcast mechanism. A message is delivered to **one consumer at a time under a valid lock**, though it can still be redelivered if the lock expires or processing is not settled.

### When Is a Queue Appropriate?

- Workers processing image transformation requests by job ID.
- Systems executing payment requests with retry and idempotency.
- Services handling report generation, invoice issuance, or data sync jobs.
- Multiple worker instances sharing a backlog to increase throughput.

### Queues Should Not Be Used for Fan-Out

Suppose Billing, Inventory, and Audit teams must each receive **every order event**. If all three listen to the **same queue**, each message normally goes to only one of the groups—there is no guarantee all three receive it. That is why you need a **topic with three subscriptions**.

## 7. Topic: Producer Publishes Once, Multiple Streams Receive Independently

A topic is an ingestion point for messages from publishers. Subscriptions attached to the topic receive **matching copies of messages** according to each subscription's filters.

```text
Orders API
    |
    | publish OrderPlaced
    v
Topic: order-events
    |
    +--- Subscription: billing ------> Billing workers
    |       |                             (competing within group)
    |       +--- DLQ
    |
    +--- Subscription: inventory ----> Inventory workers
    |       +--- DLQ
    |
    +--- Subscription: audit --------> Audit workers
            +--- DLQ
```

This is the **publish/subscribe (pub/sub)** pattern:

- The publisher does not send separate copies directly to three workers.
- The topic routes each message to subscriptions whose rules match.
- Each subscription has its own **backlog, consumers, retry/settlement, and DLQ**.
- A slowdown in Billing does not force Inventory to stop processing messages in its own subscription.
- Within **a single subscription**, multiple workers can still compete for messages to scale throughput.

### Topics Do Not Keep Infinite History

If a subscription **did not exist when a message was published**, a subscriber created later will not automatically receive all historical messages. Service Bus is not an offset-replayable event log like some streaming platforms.

If you need **multi-month historical replay**, persist events separately in durable storage per policy (such as an event archive, database/outbox, or event store). A new subscription only receives matching messages according to its configuration from the time it exists onward.

### Things Not to Mix Up

A Topic is a **publish endpoint**; there is no shared queue where consumers read directly from a topic. Workers receive from a **subscription**, not by calling `get_topic_receiver` the way they call `get_queue_receiver`.

## 8. Subscription: An Independent Logical Queue per Consumer Group

A **topic subscription** receives messages from a topic that match its rules. It shares many operational properties with a queue: message counts, lock duration, TTL, dead-letter handling, and support for competing workers.

Example with three subscriptions:

| Subscription | Event Types Received | Consumer | Impact on Failure |
|---|---|---|---|
| `billing` | `OrderPlaced`, `OrderCancelled` | Billing/invoicing system. | Backlog grows independently in billing; may populate DLQ. |
| `inventory` | `OrderPlaced` | Inventory management system. | Independent inventory backlog; billing keeps running. |
| `audit` | All order events requiring an audit trail. | Audit worker / archiver. | Must monitor retention and ensure archives are actually written. |

A subscription is **not** an email notification account. It is a messaging entity with filters, state, and data that must be managed.

### Subscription Lifecycle

- Create subscriptions before publishing starts if you cannot afford to miss initial events.
- Verify filters/rules immediately after creation.
- Configure receivers and dead-letter handling per subscription.
- Never delete a subscription just to "clear backlog" unless you confirm pending messages can be safely lost.
- With `auto-delete-on-idle` enabled, assess the risk of low-traffic subscriptions being deleted after inactivity.

## 9. Subscription Rules and Filters

Service Bus allows subscriptions to define **rules** using filters that decide which messages enter each subscription. Common filter types include:

- **True filter:** accepts every message.
- **SQL filter:** conditional expressions evaluated against system/application properties using supported syntax.
- **Correlation filter:** matches specific property values for efficient routing in certain scenarios.
- **SQL rule action:** certain configurations allow mutating properties of matched message copies within service limits.

Example publisher sending a message with application properties:

```json
{
  "messageId": "order-1042-event-1",
  "subject": "OrderPlaced",
  "applicationProperties": {
    "eventType": "OrderPlaced",
    "region": "vn-south"
  },
  "body": {
    "orderId": "1042",
    "amount": 250000
  }
}
```

This is a **logical illustration of message components**, not a required Service Bus JSON wire format; in the SDK, `messageId`, `subject`, and `applicationProperties` are set as **message metadata**, not necessarily inside the JSON body.

Illustrative SQL filters:

```sql
-- Inventory receives new orders.
eventType = 'OrderPlaced'

-- South region team receives new orders for its region.
eventType = 'OrderPlaced' AND region = 'vn-south'
```

### The `$Default` Trap

When creating a new topic subscription via normal operations, a default **`$Default`** rule with a true filter may exist—meaning it accepts **all** messages.

If you later **add** a rule like `OnlyOrderPlaced` **without removing `$Default`**, the subscription can still receive every message because rules evaluate as matching if **any** rule matches. When a subscription must receive only a subset of messages, inspect the entire rule list and remove the broad default rule once approved.

### Filters Are Not Retroactive

Editing a rule today **does not retroactively re-filter or remove** messages already sitting in the subscription's backlog. For routing changes, plan a transition window, handling of older messages, and parallel consumer versions if needed.

## 10. Choosing Queue or Topic: Decision Table

| Requirement | Recommended Choice | Reason |
|---|---|---|
| One report-export request must be handled by one worker. | **Queue** | Competing consumers share the work. |
| Every order-created event must reach Billing, Inventory, and Audit. | **Topic + 3 subscriptions** | Fan-out, with an isolated backlog per group. |
| An event goes only to a regional team. | **Topic + subscription filters** | Metadata-based routing. |
| Dozens of identical workers process CPU tasks. | **One queue + multiple receivers** | Scale throughput without broadcasting. |
| Isolate messages per partner while giving each partner full events. | **Topic + subscription per partner**, if entity/RBAC limits fit. | Isolation and per-partner filtering. |
| Need to replay all events from three years ago. | **Evaluate an additional event store / streaming / archive.** | Service Bus subscriptions are not infinite history. |
| Just need to push Azure resource state changes to subscriber endpoints. | **Evaluate Event Grid.** | Different event-distribution model. |
| Need ultra-high-volume telemetry streaming. | **Evaluate Event Hubs.** | Stream and consumer-group architecture differs from queues/topics. |

Service Bus, Storage Queue, Event Grid, and Event Hubs all transport messages/events, yet **their semantics are not interchangeable**. Choose by delivery guarantees, retention, filtering, workflow, ordering, and throughput—not just the word "queue."

## 11. Message Lifecycle in a Queue or Subscription

Service Bus supports multiple receive modes. Reliable workloads commonly use **Peek-Lock** so consumers receive a message, process it, and then settle it.

```text
Producer
   |
   | Send
   v
Active message in Queue / Topic Subscription
   |
   | Receive with Peek-Lock
   v
Message temporarily locked to receiver
   |
   +--- Processing OK ---------> Complete ------> Message leaves entity
   |
   +--- Retryable error -------> Abandon -------> Returns to available state
   |
   +--- Unprocessable ---------> DeadLetter ----> DLQ
   |
   +--- Process later ---------> Defer ---------> Deferred, retrieved by sequence number
   |
   +--- Lock expires / client dies -------------> Can be redelivered
```

### Settlement Operations

| Operation | When to Use | Consequence |
|---|---|---|
| **Complete** | Business logic succeeded; ready to confirm. | Message is removed from the queue/subscription. |
| **Abandon** | Transient error; want message eligible for redelivery. | Message returns to available state per receive mechanics. |
| **DeadLetter** | Poison message, invalid schema, unprocessable, or needs quarantine. | Moves message to the queue/subscription's DLQ. |
| **Defer** | Must postpone processing per application logic. | Message is skipped by normal receives; must be fetched by **sequence number**. |
| **Peek** | Inspect messages without consuming/settling them. | Useful for diagnostics; does not replace normal receive flow. |

**Never use Defer as "retry in 10 minutes" without tracking sequence numbers and scheduling retrieval.** Deferred messages must be explicitly fetched by the application; otherwise, they sit forgotten.

## 12. Peek-Lock vs. Receive-and-Delete

### Peek-Lock

Flow:

1. Receiver pulls a message and acquires a **lock** for a configured duration.
2. The message is temporarily withheld from other receivers while the lock is valid.
3. Worker executes business logic.
4. Worker calls `Complete` on success.
5. If the worker crashes, loses its lock, or fails to complete, the message can reappear for processing.

Peek-Lock suits **workloads requiring reliability and retries**. Because the same message can be redelivered, **idempotency** is required.

### Receive-and-Delete

In this mode, the broker considers the message consumed as soon as it is delivered to the receiver per mode semantics, with no subsequent `Complete` call needed. If the consumer crashes right after receiving and before finishing business logic, the message can be **lost from the queue without completing successfully**.

Only consider Receive-and-Delete when the business tolerates message loss or has a separate compensation/recovery mechanism. It is not a safe default for payments, invoicing, or critical state updates.

### Lock Duration Does Not Guarantee Completion Time

If a task takes longer than the lock duration, the receiver may need to **renew the lock** via supported API/processor features. Even with auto-renewal, connection drops or max renewal bounds can cause the lock to expire. When that happens, `Complete` can fail and the message is redelivered to another worker.

**A message whose business logic finished while `Complete` failed** is the classic case causing duplicate execution unless the application is idempotent.

## 13. Delivery Count, Retries, TTL, and Dead-Letter Queue

Azure Service Bus helps govern failure handling, though applications must still classify errors accurately.

### Delivery Count and MaxDeliveryCount

Each time a message is redelivered under Service Bus rules, its delivery count increments. If it exceeds the entity's **MaxDeliveryCount** policy, Service Bus can move the message to the **dead-letter subqueue** instead of retrying forever.

Do not rely blindly on a default number without checking actual configuration; queues and subscriptions may be tuned differently. Permanent errors such as a missing required field should not be retried with the same payload until max attempts if they can be detected early and explicitly dead-lettered.

### TTL (Time to Live)

Messages have a validity lifetime; TTL can be set per message or bounded by entity configuration where supported. Upon expiration, a message is no longer valid work for normal delivery. Depending on configuration, expired messages can be **dead-lettered on expiration** or expired per service behavior.

**TTL is not an execution SLA.** Setting a 1-hour TTL does not mean workers will finish within an hour; if backlogs grow too large, messages can expire before a receiver ever touches them.

### Where Does the DLQ Live?

- Every **queue** has a **dead-letter subqueue** attached to that queue.
- Every **topic subscription** has a **dead-letter subqueue** attached to that subscription.
- A **Topic itself** does not have a single shared DLQ replacing all subscriptions.

A DLQ isolates messages that failed processing; it **does not automatically repair** messages, auto-replay them, or act as an indefinite dumping ground to ignore.

## 14. Designing Responsible DLQ Operations

A solid DLQ runbook covers:

1. **Detection:** alert when dead-letter message counts rise.
2. **Classification:** invalid schema, missing data, permission error, missing dependency, poison message, or exceeded delivery count.
3. **Data protection:** never print payloads containing PII/secrets into unsecured logs or tickets.
4. **Root-cause fix:** code, config, DB schema, permissions, or target system.
5. **Decision:** discard with approval, fix/normalize and resend, or process manually.
6. **Controlled replay:** avoid duplicates and avoid looping messages straight back into the same DLQ.
7. **Reconciliation:** verify business state after replay.
8. **Incident closure:** record message count, root cause, resolution, and impact.

Example of a message missing `orderId`:

```json
{
  "schemaVersion": 1,
  "eventType": "OrderPlaced",
  "amount": 250000
}
```

If the consumer needs `orderId` to update the right order, retrying this exact payload 50 times will never conjure an `orderId`. Send it to the DLQ with a clear reason rather than inventing fake transactions.

### Clues for Root-Cause Investigation

| DLQ Reason or Symptom | Investigation Direction |
|---|---|
| `MaxDeliveryCountExceeded` | Worker crashes, lock lost, recurring code/dependency errors. |
| Expired or dead-lettered on expiration | TTL too short, backlog, downtime, or no active receivers. |
| Explicitly dead-lettered by application | Validation/schema/business rule failure or data protection guard. |
| One subscription has DLQ messages while others do not | Subscriber-specific failure; not a system-wide outage. |
| DLQ spikes during a new rollout | Compare schema versions, worker images, filters, secrets, and dependencies. |

## 15. Idempotency: Essential for At-Least-Once Delivery

In a Service Bus architecture using Peek-Lock, **at-least-once** is the delivery model applications must expect: the same message can be redelivered after a failure or lock timeout.

Example:

```text
Worker receives message M:
  1. Writes invoice to DB successfully
  2. Worker crashes before Complete
  3. Lock expires
  4. Service Bus redelivers message M
  5. Another worker receives M
```

If step 5 creates a second invoice, that is a business defect. Handlers must be **idempotent**: processing the same request multiple times applies the desired business effect only once.

### An Idempotency Strategy

- Every message carries a **stable MessageId** tied to the business operation.
- Store processed messages/business operations in a table (inbox) with a **unique constraint**.
- Within the same database transaction where applicable: check ID, apply business changes, and insert the processed marker.
- On redelivery of the same ID, the worker sees it is already completed and simply calls `Complete`.
- When both publishing messages and updating a DB, consider a **transactional outbox** to mitigate dual-write risks.

**Service Bus duplicate detection does not replace consumer idempotency.** It can drop duplicate sends with the same MessageId within a configured window when supported by tier/entity, but it does not guarantee exactly-once business execution across all failure scenarios.

## 16. Sessions and Ordered Processing

Sometimes message order matters: an order needs to progress `Created → Paid → Shipped`. Azure Service Bus **sessions**, when supported and enabled on an entity, group messages sharing a **SessionId** for ordered processing within a session.

Example:

```text
SessionId = order-1042
  1. OrderCreated
  2. PaymentCaptured
  3. OrderShipped

SessionId = order-1043
  1. OrderCreated
  2. PaymentFailed
```

A worker holds a **session lock** and processes messages in that session using appropriate session-receive semantics. Different sessions can still run in parallel.

### Key Considerations

- Queues/subscriptions must be created with sessions enabled; it is not on by default for every entity.
- Producers must set `SessionId` consistently by business key, e.g., `orderId`.
- Receivers must use a **session receiver**.
- Ordering is scoped **within each session**, not across the whole namespace or all topics.
- Sessions do not automatically solve duplicate side effects, cross-service transactions, or out-of-order sends from producers.
- One session with a very slow message can head-of-line block later messages in that same session; design partitioning keys and processing capacity carefully.

**If you have no genuine ordering requirement, do not enable sessions just to "be extra safe"**: they increase complexity and can constrain parallelism per key.

## 17. Other Entity-Level Capabilities to Know

| Feature | Meaning | Caution |
|---|---|---|
| **Scheduled messages** | Schedules when a message enters the receive stream via supported APIs. | Not a hard real-time timer with millisecond SLA guarantees. |
| **Duplicate detection** | Detects duplicate sends by MessageId within a configured window and conditions. | Does not replace inbox/idempotency. |
| **Transactions** | Groups certain messaging operations into a transaction per SDK/tier support. | Does not automatically span external databases or HTTP APIs. |
| **Auto-forwarding** | Forwards messages from a queue/subscription to a target entity per supported config. | Requires proper permissions, topology, and awareness of forwarding/dead-letter limits. |
| **Auto-delete on idle** | Automatically deletes an entity after an idle period. | Can lose backlogs or consumer bindings if misused in Production. |
| **Partitioning** | Distributes storage/processing under tier-supported models. | Does not guarantee global ordering; support varies by tier/SKU. |
| **Message deferral** | Holds messages aside to be fetched by sequence number. | Requires tracking sequence numbers and managing lifecycle. |

Some features have combination constraints. Before picking a tier and creating entities, verify the **support matrix**, message size limits, entity counts, lock durations, TTLs, and current quotas in your namespace's region.

## 18. Designing Message Contracts: Body and Metadata

Producers and consumers need a clearly versioned **message contract**. Do not dump entire database entities as unbounded objects or include sensitive fields.

Example **event body**:

```json
{
  "schemaVersion": 1,
  "eventType": "OrderPlaced",
  "eventId": "evt-1042-001",
  "occurredAtUtc": "2026-11-20T08:30:00Z",
  "orderId": "1042",
  "customerReference": "cust-ref-81",
  "totalAmount": 250000,
  "currency": "VND"
}
```

**Service Bus Message metadata** can carry:

```text
message_id       = evt-1042-001
subject          = OrderPlaced
correlation_id   = checkout-req-889
content_type     = application/json
application_properties:
  eventType      = OrderPlaced
  schemaVersion  = 1
  region         = vn-south
```

### Contract Principles

- Include a **schema version** and compatibility rules for adding/removing fields.
- Include a stable **event/business ID** for correlation and idempotency.
- Use UTC timestamps and document what the timestamp represents.
- Never put passwords, access tokens, private keys, or unnecessary sensitive data in bodies or logs.
- Messages should be **self-sufficient for processing** or carry an explicit reference to authoritative source data.
- For large payloads, consider the **claim-check pattern**: store objects in Blob Storage and send a message with a properly authorized URI/ID rather than a long-lived SAS.
- Define TTL policies and handle events arriving past their useful window.
- If filters inspect `eventType`, producers must populate **application properties** properly—not just put the field inside the JSON body.

## 19. Security: Entra ID, Managed Identity, and Azure RBAC

To send or receive messages, applications need **data-plane permissions** on the namespace or relevant entity. Whenever feasible, prefer **Microsoft Entra ID and managed identities** over embedding SAS keys or connection strings in containers or source code.

Common roles:

| Role | Key Permissions | Used For |
|---|---|---|
| **Azure Service Bus Data Sender** | Send messages. | Orders API / producers. |
| **Azure Service Bus Data Receiver** | Receive messages. | Billing / Inventory / Audit workers. |
| **Azure Service Bus Data Owner** | Broader data-plane rights to manage and use messaging entities. | Controlled special operational tasks; do not grant by default. |

Assign roles at the narrowest **scope** supported by the scenario—namespace, queue, or topic/subscription per Azure RBAC and SDK support. For multi-app environments, grant senders access only to target send entities and receivers only to target receive entities rather than granting Data Owner across namespaces.

### Illustrative Role Assignment

Once a managed identity exists and you have verified its principal ID and target scope, Sender access can be granted through an approved workflow:

```bash
az role assignment create \
  --assignee-object-id "<PRINCIPAL_ID>" \
  --assignee-principal-type ServicePrincipal \
  --role "Azure Service Bus Data Sender" \
  --scope "<QUEUE_OR_NAMESPACE_RESOURCE_ID>"
```

**This command modifies Azure RBAC** and must not be run without authorization and approval. Role assignments also take time to propagate; verify how the app authenticates instead of hastily granting broader permissions right after a change.

### SAS Policies and Connection Strings

Service Bus also supports **Shared Access Signatures (SAS)** depending on namespace/entity features and settings. Permissions typically split into **Send, Listen, Manage**. For new systems:

- Prefer identity-based authentication whenever SDK/runtime supports it.
- If SAS is required, create least-privilege, narrowly scoped policies and rotate keys.
- Never share the namespace's **RootManageSharedAccessKey** across applications.
- Never store connection strings in Git, plaintext Kubernetes ConfigMaps, logs, or tickets.
- Once migration is complete, evaluate disabling local/SAS authentication per tier capabilities and organizational policy.

**Azure control-plane Contributor** is not equivalent to Azure Service Bus Data Sender/Receiver: resource management RBAC and message send/receive permissions must be evaluated separately.

## 20. Network Security and Private Access

To connect to Service Bus, a runtime needs **DNS resolution, network reachability, TLS, and Service Bus authorization**. A valid identity will not work if a firewall or VNet policy blocks the connection.

Checklist:

1. Does the namespace permit the designed public or private network path?
2. If using a **Private Endpoint**, do the tier, region, and features support it? Are the Private DNS zone and VNet links configured properly?
3. Do clients on Azure VM/AKS/Container Apps have routes to the endpoint?
4. Do NSGs, Azure Firewall, NAT, UDRs, and corporate proxies allow outbound traffic?
5. Does the SDK use **AMQP over TLS** (typically TCP 5671) or **AMQP over WebSockets** (typically TCP 443) as configured?
6. Are TLS certificate validation and system clock synchronization healthy?
7. Does the app hold valid Entra RBAC or SAS permissions for the target entity?
8. Do retries/backoff avoid overwhelming the namespace during transient unavailability?

### Why TCP 443 Does Not Automatically Fix Everything

Some SDKs can use WebSockets transport over TCP 443 when networks block 5671, but **transport must be configured in the SDK**. Allowing TCP 443 in a firewall does not magically convert an AMQP/TCP connection into WebSockets; hostname, private DNS, and Service Bus authorization must still be correct.

**Private Endpoints do not increase messaging throughput or grant send/receive rights.** They strictly control the network access path.

## 21. Deployment Workflow via the Azure Portal

Example scenario requiring one queue and one topic with three subscriptions.

### Phase A: Create Namespace

1. Sign in to the [Azure Portal](https://portal.azure.com/) and verify the right tenant/subscription.
2. Open **Service Bus** → **Create**.
3. Choose resource group, valid namespace name, region, and pricing tier.
4. Select **Standard or Premium** if topics/subscriptions are required.
5. Review network/auth settings and organizational policies before creating.
6. Wait for provisioning to complete and open the namespace to verify its endpoint.

### Phase B: Create Queue

1. Inside the namespace, select **Queues** → **Create**.
2. Enter the name `charge-command`.
3. Configure TTL, lock duration, MaxDeliveryCount, and supported options as needed.
4. Do not enable sessions or duplicate detection unless the application already implements matching receivers and MessageId/SessionId logic.
5. Create and review entity settings.

### Phase C: Create Topic and Subscriptions

1. Select **Topics** → **Create**, named `order-events`.
2. Create three subscriptions: `billing`, `inventory`, `audit`.
3. Inspect existing rules. If filtering is needed, create the proper rules and handle `$Default` appropriately.
4. Configure DLQ, TTL, MaxDeliveryCount/lock, and per-subscription capabilities.
5. Configure separate receivers; each must connect to the matching **topic + subscription**.
6. Send lab messages; verify each subscription receives only the intended event types.

### Phase D: Security and Operations

1. Assign least-privilege Sender/Receiver roles to managed identities.
2. Configure network endpoints, firewalls, and private DNS per design.
3. Set up Azure Monitor metrics, diagnostic logs, alerts, and dashboards.
4. Test retries and failed messages in the lab, verifying DLQ behavior.
5. Assign owners, budgets, and change procedures for schemas and rules.

## 22. Azure CLI: Inspecting Namespaces and Entities (Read-Only)

The commands below read Azure Resource Manager configuration and **do not create or delete messages**. Replace placeholders with your organization's resources.

### Verify Context

```bash
az account show \
  --query "{Subscription:id,Tenant:tenantId,Name:name}" \
  --output table
```

### Inspect Namespace

```bash
az servicebus namespace show \
  --name "<NAMESPACE_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --query "{Name:name,Location:location,Sku:sku.name,State:provisioningState}" \
  --output json
```

### List Queues and Topics

```bash
az servicebus queue list \
  --namespace-name "<NAMESPACE_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --output table

az servicebus topic list \
  --namespace-name "<NAMESPACE_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --output table
```

### List Subscriptions on a Topic

```bash
az servicebus topic subscription list \
  --namespace-name "<NAMESPACE_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --topic-name "order-events" \
  --output table
```

### Show Queue / Subscription Details

```bash
az servicebus queue show \
  --namespace-name "<NAMESPACE_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --name "charge-command" \
  --output json

az servicebus topic subscription show \
  --namespace-name "<NAMESPACE_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --topic-name "order-events" \
  --name "billing" \
  --output json
```

Output may include runtime/metadata properties depending on API/CLI version. Before drawing conclusions about exact backlog or DLQ counts, check metric freshness in the Portal or Azure Monitor; some counts can lag.

### Inspect Subscription Rules

```bash
az servicebus topic subscription rule list \
  --namespace-name "<NAMESPACE_NAME>" \
  --resource-group "<RESOURCE_GROUP>" \
  --topic-name "order-events" \
  --subscription-name "billing" \
  --output json
```

Check for `$Default` or true-filter rules when filtering is expected. Flags and response schemas may differ across Azure CLI versions; run `az servicebus topic subscription rule list --help` if needed.

## 23. Azure CLI: Controlled Creation of Lab Resources

**Commands in this section modify resources and may incur costs.** Run only in an approved lab resource group. They are a reference sequence; actual accounts require appropriate quotas, RBAC, and SKU availability.

### Standard Namespace

```bash
az servicebus namespace create \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --name "<UNIQUE_NAMESPACE_NAME>" \
  --location "southeastasia" \
  --sku Standard
```

The namespace name must follow naming rules and be **globally unique** within the service's DNS scope. `southeastasia` is an example; choose a region fitting data residency, latency, and policy.

### Point-to-Point Queue

```bash
az servicebus queue create \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --namespace-name "<UNIQUE_NAMESPACE_NAME>" \
  --name "charge-command"
```

### Topic and Three Subscriptions

```bash
az servicebus topic create \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --namespace-name "<UNIQUE_NAMESPACE_NAME>" \
  --name "order-events"

az servicebus topic subscription create \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --namespace-name "<UNIQUE_NAMESPACE_NAME>" \
  --topic-name "order-events" \
  --name "billing"

az servicebus topic subscription create \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --namespace-name "<UNIQUE_NAMESPACE_NAME>" \
  --topic-name "order-events" \
  --name "inventory"

az servicebus topic subscription create \
  --resource-group "<LAB_RESOURCE_GROUP>" \
  --namespace-name "<UNIQUE_NAMESPACE_NAME>" \
  --topic-name "order-events" \
  --name "audit"
```

After creation, list subscriptions and rules again. Never send sensitive data in tests. When filtering is needed, create and verify rules via the Portal or supported SDK/CLI while checking the default rule.

**Lab cleanup:** delete resources via your team's governance process only after verifying no needed messages/objects remain and no other systems share the namespace. Never delete a shared namespace just because you finished an exercise.

## 24. Python SDK: Producer Sending a Message to a Queue

This example uses the **Azure SDK for Python** with **`DefaultAzureCredential`**; the runtime must authenticate as an identity granted **Azure Service Bus Data Sender** on the target entity/scope.

Install libraries inside an authorized lab virtual environment:

```bash
python -m pip install azure-servicebus azure-identity
```

Script to send a mock request:

```python
import json
import os
from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient, ServiceBusMessage

namespace = os.environ["SERVICEBUS_NAMESPACE"]
queue_name = "charge-command"

payload = {
    "schemaVersion": 1,
    "commandType": "ChargeOrder",
    "orderId": "lab-order-1042",
    "amount": 250000,
    "currency": "VND",
}

credential = DefaultAzureCredential()
with ServiceBusClient(
    fully_qualified_namespace=f"{namespace}.servicebus.windows.net",
    credential=credential,
) as client:
    with client.get_queue_sender(queue_name=queue_name) as sender:
        message = ServiceBusMessage(
            json.dumps(payload, ensure_ascii=False),
            message_id="charge-lab-order-1042-v1",
            subject="ChargeOrder",
            content_type="application/json",
            correlation_id="checkout-lab-1042",
            application_properties={"commandType": "ChargeOrder"},
        )
        sender.send_messages(message)
        print("Sent lab request to queue.")
```

Run with an environment variable containing only the **namespace name**, not a SAS secret:

```bash
export SERVICEBUS_NAMESPACE="<UNIQUE_NAMESPACE_NAME>"
python send_queue.py
```

`export` uses Unix shell syntax. On Windows PowerShell, environment variable assignment syntax differs; adjust for your shell. The script neither creates the queue nor grants Entra permissions. If the queue does not exist or the principal lacks Sender permission, sending will fail.

### Send Success Does Not Mean Payment Completed

`send_messages` completing means the broker accepted the message per SDK call—**not that the Billing worker finished business processing**. The API must record `Accepted/Pending` and provide a way to track business outcomes.

## 25. Python SDK: Receiver with Peek-Lock and Complete

A typical worker uses Peek-Lock, runs business logic, and then calls Complete.

```python
import json
import os
from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient, ServiceBusReceiveMode

namespace = os.environ["SERVICEBUS_NAMESPACE"]

def handle_command(body):
    data = json.loads(body)
    order_id = data["orderId"]
    # REPLACE with idempotent business logic inside your DB/transaction.
    print(f"Validated lab order request {order_id}")
    # Do not execute real payment transactions in this example.

credential = DefaultAzureCredential()
with ServiceBusClient(
    fully_qualified_namespace=f"{namespace}.servicebus.windows.net",
    credential=credential,
) as client:
    with client.get_queue_receiver(
        queue_name="charge-command",
        receive_mode=ServiceBusReceiveMode.PEEK_LOCK,
        max_wait_time=10,
    ) as receiver:
        messages = receiver.receive_messages(
            max_message_count=5,
            max_wait_time=10,
        )
        for message in messages:
            body = b"".join(message.body).decode("utf-8")
            try:
                handle_command(body)
            except (KeyError, ValueError, json.JSONDecodeError) as exc:
                # Invalid data: align with real system's DLQ policy.
                receiver.dead_letter_message(
                    message, reason="InvalidCommand",
                    error_description=type(exc).__name__,
                )
            except Exception:
                # Simple example: allow the message another processing attempt.
                receiver.abandon_message(message)
                raise
            else:
                receiver.complete_message(message)
```

**Important notes on this example:**

- This is a pattern **illustrating the settlement flow**, not a production-ready processor.
- `ServiceBusReceivedMessage.body` may be exposed or read differently depending on message type and SDK version; verify the API body type and decoding in your environment.
- `Complete` can fail if the lock is lost; workers must handle `MessageLockLost` and idempotency rather than assuming no retries occur.
- Distinguish permanently malformed data from transient dependency errors.
- Messages can contain sensitive details; log only **message ID, correlation ID, and sanitized error codes**, never full raw bodies.
- For high-throughput workloads, use an appropriate Service Bus processor/SDK pattern with concurrency limits, auto-lock renewal, and graceful shutdown.

### A Safer Body Validation Pattern

If your application standardizes payloads on UTF-8 JSON, wrap decoding, parsing, and schema validation. Some libraries expose `body` as iterable byte sections; avoid assuming every message is UTF-8 text if the system might also receive binary payloads.

## 26. Python SDK: Publishing to a Topic and Receiving from a Subscription

### Publisher

In the publisher, choose a **topic sender** instead of a queue sender:

```python
import json
import os
from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient, ServiceBusMessage

namespace = os.environ["SERVICEBUS_NAMESPACE"]
event = {
    "schemaVersion": 1,
    "eventType": "OrderPlaced",
    "eventId": "evt-lab-1042-1",
    "orderId": "lab-order-1042",
}

credential = DefaultAzureCredential()
with ServiceBusClient(
    fully_qualified_namespace=f"{namespace}.servicebus.windows.net",
    credential=credential,
) as client:
    with client.get_topic_sender(topic_name="order-events") as sender:
        sender.send_messages(ServiceBusMessage(
            json.dumps(event),
            message_id=event["eventId"],
            subject=event["eventType"],
            content_type="application/json",
            application_properties={"eventType": event["eventType"]},
        ))
        print("Published OrderPlaced to topic.")
```

### Subscriber

A subscription receiver connects using **topic name + subscription name**:

```python
import os
from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient

namespace = os.environ["SERVICEBUS_NAMESPACE"]

credential = DefaultAzureCredential()
with ServiceBusClient(
    fully_qualified_namespace=f"{namespace}.servicebus.windows.net",
    credential=credential,
) as client:
    with client.get_subscription_receiver(
        topic_name="order-events",
        subscription_name="inventory",
        max_wait_time=10,
    ) as receiver:
        for message in receiver:
            print(
                "Received event:",
                message.message_id,
                "from inventory subscription",
            )
            # For production: process idempotently before Complete.
            receiver.complete_message(message)
```

When testing, create the `billing`, `inventory`, and `audit` subscriptions **before publishing**. Read each subscription separately to confirm the event arrives as expected. When multiple receivers listen on `inventory`, each message in the **inventory subscription** is normally handled by one receiver, not duplicated to every receiver in that pool.

## 27. Observability and Alerting: Pinpointing Bottlenecks

A queue with 10,000 active messages can be normal during a batch spike, or indicate an outage if the API expects sub-second latency. Metrics must be tied to **business SLOs**.

| Metric / Signal | Meaning | Response |
|---|---|---|
| **Active messages** | Messages waiting to be received/processed in queue/subscription per metric state. | Compare producer vs. consumer rates; check receiver health. |
| **Dead-lettered messages** | Quarantined messages requiring investigation. | Follow DLQ runbook, check reasons and schemas. |
| **Incoming messages** | Publish traffic into namespace/entity per metric definition. | Compare inbound load and scaling needs. |
| **Outgoing messages** | Outbound/delivery volume per metric definition. | Does not mean all business work succeeded. |
| **Server errors / user errors** | Service-side errors or request/authorization/config errors. | Classify by status/error code and client state. |
| **Throttled requests** | Hit capacity/quota limits or tier bounds. | Check SKU, workload, retry/backoff, and throughput. |
| **CPU/memory/namespace utilization** | Depends on tier and exposed metrics. | Size capacity, especially Premium Messaging Units. |
| **Age of oldest message** | Signals whether backlog delays breach SLOs. | May require app/consumer measurement; not guaranteed built-in on all tiers. |
| **Receiver exceptions and lock lost** | Worker crashes or processing outlasts lock. | Inspect handlers, dependencies, concurrency, lock renewal. |

### Three Log Types That Do Not Replace One Another

1. **Application logs/traces:** producer sends, receiver handling, business outcomes, MessageId, CorrelationId.
2. **Azure Service Bus diagnostics/metrics:** resource health, errors, operations across supported diagnostic categories.
3. **Azure Activity Log:** control-plane changes to namespaces/entities, networking, RBAC, and configuration; **not a full history of every message body**.

Enable Azure Monitor diagnostic settings to Log Analytics, Event Hubs, or Storage per policy. Log Analytics table and column names can differ between resource-specific tables and `AzureDiagnostics`; do not copy a sample KQL query from another workspace and conclude zero messages exist.

### Minimum Alerts

- DLQ count > 0 or rising abnormally on critical business flows.
- Backlog or queue length/processing age exceeds allowed thresholds.
- Spikes in throttled requests, server errors, or unauthorized errors.
- Unusual zero activity from producers/consumers during active business hours.
- Repeated worker exceptions/restarts and database dependency errors.
- Sustained high Premium capacity utilization where metrics are supported.
- Namespace network/RBAC/rule changes outside maintenance windows.

A message dropped upfront by a subscription filter **will never appear** in any backlog to trigger an alert; therefore, pair telemetry with **end-to-end business monitoring** and event routing tests.

## 28. Throughput, Scaling, and Cost

### Factors Affecting Throughput

- Payload size and messages per second.
- Producer/consumer connection counts, concurrency, and batch sizes.
- Worker business processing duration.
- Prefetch, receive batching, lock duration, and auto-renewal.
- Sessions, filters, duplicate detection, and ordering constraints.
- Namespace, entity, and tier quotas/limits.
- Network latency, AMQP transport, CPU, and connection pooling.
- Database or downstream services—often the true bottleneck.

**Adding consumers will not necessarily increase throughput** if the downstream database only sustains 100 transactions/second or a single session serializes execution.

### Simple Backlog Estimation

Suppose:

- Producer sends 500 messages/minute.
- Total consumers successfully process 400 messages/minute.
- Initial backlog is 0.

After 60 minutes:

```text
Backlog growth/min = 500 - 400 = 100 messages
Backlog after 60 min ≈ 100 × 60 = 6,000 messages
```

If the producer stops and consumers maintain 400 messages/minute, draining takes roughly:

```text
Drain time ≈ 6,000 / 400 = 15 minutes
```

This is an illustrative calculation ignoring retries, expired messages, batch efficiency, throughput fluctuations, and downtime.

### Cost Estimation by Workload Profile

| Line Item | What to Measure |
|---|---|
| Namespace tier | Basic/Standard by supported operations/model; Premium by Messaging Units/capacity. |
| Message volume | Sends/receives, operations, and actual message counts. |
| Storage footprint | Backlog, TTL, size, DLQ, and fan-out subscriptions. |
| Network | Private endpoints, VNet, DNS, NAT, firewalls, and related traffic. |
| Monitoring | Log Analytics ingestion, retention, alerts, metrics. |
| Workload compute | VM/Functions/AKS/Container Apps workers draining the backlog. |
| Operations | On-call effort, DLQ replays, incidents, DR drills. |

**A topic with three subscriptions** can generate **three storage and processing streams** for matching messages, so do not count only a single producer publish when sizing capacity and backlogs. Use the **Azure Pricing Calculator** with your region, tier, and real metrics; never infer real pricing from examples.

## 29. Troubleshooting: Common Failure Modes

| Symptom | Possible Cause | Check in Order |
|---|---|---|
| `MessagingEntityNotFound` | Wrong queue/topic/subscription name, wrong namespace, or entity not created. | Context, namespace, entity list, exact spelling. |
| `Unauthorized` / `AuthorizationFailed` | Managed identity/SAS lacks permission or wrong scope. | Entra token, Sender/Receiver role, policy, propagation, endpoint. |
| `ServiceBusException: ServiceTimeout` | Network, service issue, throttling, or connection saturation. | Region health, SDK retries, AMQP transport, firewall, metrics. |
| Cannot send on Basic tier | Trying to use topics/subscriptions or unsupported tier features. | Namespace SKU and support matrix. |
| Publish succeeds, subscriber gets nothing | Subscription missing at publish time, filtered out, or wrong receiver subscription. | Rules (including `$Default`), timeline, entity metadata. |
| One subscriber backlog grows | That group's workers are failing or slow. | Subscription active count, consumer logs, DLQ. |
| Messages redelivered repeatedly | Lock timeout, `Complete` failed, or `Abandon`/worker crash. | Delivery count, lock duration, worker latency, idempotency. |
| DLQ grows continuously | Poison messages, max delivery count, TTL, or explicit dead-lettering. | DLQ reason, schema, dependencies, and handler. |
| Messages expire before processing | TTL shorter than queue wait/backlog. | TTL, ingestion rate, consumer capacity, SLO. |
| Messages out of order | Multiple producers/receivers without proper session design. | SessionId, message timeline, handler architecture. |
| Failures when deploying new consumer | Incompatible contract or missing metadata. | Schema version, tolerant reader, rollout strategy. |
| Cannot reach namespace Private Endpoint | DNS, routing, NSG/firewall, or tier/private feature mismatch. | FQDN, private IP resolution, outbound ports, TLS. |
| Excessive retries overload DB | Retry storm, thundering herd, missing backoff/jitter. | Concurrency, downstream metrics, retry policy. |
| Client reads message, `Complete` fails | Lock lost, link detach, receiver reconnect. | Lock renewal, processing duration, SDK errors. |

### Isolation Methodology

1. **Right resource?** Azure subscription, resource group, namespace, tier, entity/subscription.
2. **Right permissions?** Azure RBAC/SAS and scope.
3. **Right network path?** DNS, TCP/TLS, firewall, private endpoint.
4. **Message accepted?** Producer logs/operation outcomes and metrics.
5. **Routed properly?** Topic filters, default rule, and subscription creation timing.
6. **Receiver healthy?** App health, consumer group, and dependencies.
7. **Settlement working?** Complete, retries, lock lost, DLQ.
8. **Business side effects right?** DB transaction/idempotency and reconciliation.
9. **Recoverable?** Backlog, DLQ, event archive, and replay plan.

Never change namespace networking, filters, and consumer code simultaneously without evidence; doing so obscures root causes and risks losing more messages.

## 30. Reliable Architecture: Transactional Outbox and Inbox

Service Bus does not automatically participate in atomic transactions with an external application database.

### The Dual-Write Problem

Suppose Orders API:

1. Writes an order to the database.
2. Publishes `OrderPlaced` to Service Bus.

If step 1 succeeds and step 2 fails, the DB has the new order with no event. If reversed, the event may be published while the DB transaction rolls back.

### Transactional Outbox

```text
Orders API
    |
    +-- Single DB transaction:
    |      - INSERT Order
    |      - INSERT OutboxEvent(OrderPlaced)
    |
    v
Outbox dispatcher
    |
    +-- read unsent events
    +-- publish to Service Bus
    +-- mark as sent
    |
    v
Topic: order-events
    |
    +--> Billing subscription
    +--> Inventory subscription
```

The outbox reduces the risk of losing events between DB commit and publish. The dispatcher can still send duplicates if publishing succeeds before marking the outbox row sent, so **idempotent consumers** remain essential.

### Consumer Inbox

The consumer records `ProcessedMessageId` alongside business changes in a single transaction where supported. If the same `MessageId` arrives again, skip side effects and call `Complete`.

**Outbox + inbox + retries** is a far more reliable architecture than claiming "the broker guarantees exactly-once business transactions." Service Bus messaging transactions do not automatically extend atomicity to external databases.

## 31. Managing Topic/Subscription and Schema Changes

Every new subscriber or filter can impact business behavior.

**Pre-deployment checklist:**

1. Is a queue or a new topic/subscription needed?
2. Do namespace tier/capacity cover the new entity and message throughput?
3. Was the subscription created **before publishers begin emitting events**?
4. Were rules/filters tested against both matching and non-matching samples?
5. Should `$Default` be removed to avoid receiving everything?
6. Is there existing backlog data using an older schema?
7. Can consumers still read the previous schema version?
8. Are DLQ retention, MaxDeliveryCount, and TTL set appropriately?
9. Are Sender/Receiver roles and private networking deployed?
10. Are dedicated dashboards/alerts configured for the new subscription?
11. Is there a rollback path if a filter is too broad or too narrow?
12. Has a business owner verified events are actually processed end-to-end?

### Schema Evolution

Prefer **backward-compatible** changes whenever possible—such as adding optional fields while preserving existing field semantics. For breaking changes, consider:

- New event type or schema version.
- Running two consumer versions side-by-side during transition.
- Contract tests for producers and consumers.
- Handling older messages still sitting in the backlog.
- Not deleting old subscriptions until their backlogs and processing have drained.

## 32. Incident Runbook: Order Events Not Reaching Inventory

**Context:** Orders API sends `OrderPlaced` to topic `order-events`. Billing processes normally, while Inventory sees no events.

### Phase A — Scope the Incident

1. Collect `eventId` / `MessageId` and UTC timestamp from producer logs.
2. Confirm target namespace and topic.
3. Verify the publisher logged send acceptance rather than only "about to send."
4. Confirm Billing processed that **exact `eventId`**, not another event.

### Phase B — Inspect the Subscription

1. Did the `inventory` subscription exist when the event was published?
2. Is there a rule `eventType = 'OrderPlaced'`?
3. Does `$Default` or another rule alter routing?
4. Did the producer set `eventType` in **application properties** or only inside the JSON body?
5. Does the subscription show active messages, dead-lettered messages, or TTL expirations?
6. Is the consumer actually connected to the `inventory` subscription on this topic?

### Phase C — Inspect the Receiver

1. Is the worker running with a Data Receiver identity at the right scope?
2. Are there schema-parsing, DB-update, or `Complete` errors?
3. Is delivery count high, or are messages landing in the DLQ?
4. Is the worker receiving messages while business side effects roll back?
5. With multiple workers, is one instance failing or running a mismatched version?

### Phase D — Remediate

- If a rule is wrong: fix the rule with approval **for new publishes**; do not expect filtered-out historical events to replay automatically.
- If messages sit in backlog: fix the receiver and resume consumption.
- If in DLQ: follow the DLQ runbook, verify payloads, and replay idempotently.
- If events never entered the subscription: recover from source data / outbox / event archive and republish safely without duplicate side effects.
- If identity/network failed: apply the narrowest permission/route fix instead of opening the whole namespace unconditionally.

### Phase E — Verify Recovery

- New test events arrive and process cleanly across Billing, Inventory, and Audit per rules.
- `MessageId` / correlation IDs trace end-to-end.
- Zero duplicate side effects created.
- Backlog/DLQ are stable and latency meets SLO.
- Rules and contract docs are updated.
- Any temporary access grants are revoked.

## 33. Hands-On Exercise: Building a Queue and Publish/Subscribe Model

**Context:** an online store wants to separate command-style payment processing from broadcasting order-creation events.

Requirements:

| Component | Sample Name |
|---|---|
| Resource group | `rg-messaging-lab` |
| Service Bus namespace | `sb-shop-lab-unique` |
| Namespace tier | Standard |
| Work queue | `charge-command` |
| Event topic | `order-events` |
| Billing subscription | `billing` |
| Inventory subscription | `inventory` |
| Audit subscription | `audit` |
| Event types | `OrderPlaced`, `OrderCancelled` |
| Producer permission | Azure Service Bus Data Sender |
| Consumer permission | Azure Service Bus Data Receiver |
| Lab constraints | No real data, never print secrets |

### Tasks

1. Diagram the namespace, queue, topic, three subscriptions, and DLQs.
2. Explain why `charge-command` is a queue while `order-events` is a topic.
3. Compare one queue with three workers against one topic with three subscriptions.
4. Pick the right tier and explain why Basic cannot be used.
5. Create the namespace, queue, topic, and subscriptions in the lab via Portal or approved CLI.
6. Inspect the `$Default` rule on each subscription.
7. Configure filters so `inventory` receives only `OrderPlaced` and `audit` receives all events.
8. Send a mock command to the queue and use two workers to observe competing consumers.
9. Publish `OrderPlaced` to the topic and read separately from Billing, Inventory, and Audit.
10. Publish `OrderCancelled` and predict which subscriptions receive it after filter setup.
11. Send a malformed-schema lab message and observe failure settlement / DLQ per policy.
12. Describe how to handle a lock-timeout redelivery without double-charging payment.
13. Configure at least two alerts for backlog and DLQ.
14. Document three architectural risks if a subscription is deleted or filters are changed in live Production.
15. Confirm lab cleanup per approved permissions, retention, and budget.

### Guided Answers

**Queue:** `charge-command` holds commands processed once from a business standpoint; multiple workers compete to pull them and must enforce idempotency on `orderId`/`MessageId` to prevent duplicate side effects.

**Topic:** `order-events` broadcasts each event to multiple business groups. Each subscription holds an independent backlog, so slow Billing workers do not stall Inventory on Billing's backlog.

**Filters:** Inventory should have a rule matching only `OrderPlaced`; if `$Default` (true filter) remains, the restriction will not work as expected. Audit can keep a catch-all rule. Billing can accept both event types depending on business contract.

**Schema error:** a message missing `orderId` must be quarantined and investigated—never invent an `orderId` or retry infinitely.

**Acceptance:** demonstrate that one command in the queue is processed once by one worker; one event in the topic reaches each matching subscription; malformed messages reach the DLQ via tested handling; consumers run with least-privilege permissions and logs expose no sensitive data.

## 34. Self-Check Questions

**Question 1.** What is the core difference between a namespace, a queue, and a topic?

**Answer:** A namespace is the resource/configuration and endpoint boundary; a queue stores point-to-point tasks; a topic accepts publishes and distributes them to subscriptions.

**Question 2.** Is a Service Bus topic subscription the same as an Azure billing subscription?

**Answer:** No. A topic subscription is an entity receiving messages from a topic. An Azure subscription is the account, resource, and billing boundary.

**Question 3.** Why cannot one queue with three workers replace a topic with three subscriptions?

**Answer:** Three workers on one queue act as competing consumers; each message is normally handled by one worker. A topic delivers matching copies to each independent subscription.

**Question 4.** Can the Basic tier be used to create topics and subscriptions?

**Answer:** No. When Service Bus topic-based publish/subscribe is needed, choose a supporting tier such as Standard or Premium.

**Question 5.** A publisher sent messages yesterday, and a subscription is created today. Does the new subscription automatically receive all older messages?

**Answer:** No. Service Bus does not replay historical messages published before a subscription existed.

**Question 6.** If you add a SQL filter to a subscription while keeping the `$Default` true filter, are you guaranteed to receive only messages matching the SQL filter?

**Answer:** No. The default rule can still allow the subscription to accept every message; inspect the entire rule set.

**Question 7.** A queue receiver pulls a message with Peek-Lock and crashes before calling Complete. What can happen?

**Answer:** After the lock expires, the message can be redelivered, so handlers must be idempotent.

**Question 8.** What risk does Receive-and-Delete carry if a worker dies right after receiving?

**Answer:** The message may already be treated as consumed before business work completes, causing lost work.

**Question 9.** Is the dead-letter queue a single queue on a topic shared across all subscriptions?

**Answer:** No. Each queue and each individual subscription has its own dead-letter subqueue.

**Question 10.** Does a 1-hour TTL guarantee a message will be processed successfully within one hour?

**Answer:** No. TTL defines validity lifetime, not a processing SLA. Backlogs can cause messages to expire before a receiver ever processes them.

**Question 11.** Does duplicate detection guarantee the database will never record two invoices?

**Answer:** No. Duplicate detection operates within specific scopes/windows; consumers still need idempotency and proper transactions.

**Question 12.** When should `SessionId` be used?

**Answer:** When messages sharing a business key (such as `orderId`) must be processed in order, and senders, receivers, and entities are designed for sessions.

**Question 13.** Can a sender holding only the `Azure Service Bus Data Sender` role receive messages?

**Answer:** Not by default. Send and receive permissions are separate and require the appropriate data-plane roles.

**Question 14.** Does `Azure Service Bus Data Receiver` allow creating or deleting the entire namespace?

**Answer:** No. Azure control-plane resource management is a separate permission scope.

**Question 15.** When using a Private Endpoint, can Azure RBAC/SAS be omitted?

**Answer:** No. A Private Endpoint restricts the network path; Service Bus still requires authentication and authorization.

**Question 16.** A topic message appears in Billing but not in Inventory. What should you check?

**Answer:** Whether the Inventory subscription existed at publish time, rules/filters, `$Default`, application properties, TTL, DLQ, and receiver health.

**Question 17.** Why should access tokens or full customer records be kept out of message bodies unless necessary?

**Answer:** Messages persist across backlogs, retries, DLQs, and logs; unnecessary sensitive data increases leak surface and storage cost.

**Question 18.** Does `send_messages` returning success mean the order payment is complete?

**Answer:** No. It only indicates the broker accepted the send operation; business completion must be tracked separately.

**Question 19.** What risk does the outbox pattern reduce?

**Answer:** It reduces the risk of a DB commit succeeding while event publishing fails (or vice versa), typically by writing business data and an outbox record in one DB transaction and dispatching later.

**Question 20.** Backlog keeps growing even after adding workers. What could be causing it?

**Answer:** Downstream DB bottlenecks, slow consumer logic, single-session serialization, lock failures, quota/throttling, or network issues. Measure actual performance and bottlenecks.

**Summary:** An Azure Service Bus **namespace** is the governance and connectivity boundary; a **queue** distributes tasks across competing consumers; a **topic** broadcasts messages to independent **subscriptions**, each with its own rules, backlog, and DLQ. A reliable messaging system does more than just send messages—it **routes accurately, enforces least-privilege permissions, handles redeliveries idempotently, monitors backlogs, and verifies end-to-end business completion**.
