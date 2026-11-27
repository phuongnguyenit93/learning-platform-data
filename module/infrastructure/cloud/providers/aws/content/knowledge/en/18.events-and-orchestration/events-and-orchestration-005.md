# Archive, replay, and cross-account event delivery

> **Chapter:** Events and Orchestration  
> **Module:** CLOUD_PROVIDERS_AWS — exploring AWS across Region/Availability Zone (AZ) infrastructure, IAM, VPC, compute, storage, databases, integration, and serverless. This lesson focuses on service selection, secure application deployment, observability, recovery, and cost control.

## Learning objectives

After this lesson, learners will be able to:

1. Distinguish **EventBridge default/Custom Event Bus – Classic** from the **new Custom Event Bus**, especially how events are stored and replayed.
2. Explain **archives**, event patterns, retention, encryption, and the mechanism preventing archives from re-archiving replayed events in Classic.
3. Design a **replay** selecting the right time window and rules with side-effect/idempotency controls.
4. Apply **cross-account event delivery** designs via IAM delivery roles and resource-based policies or **AWS RAM**, depending on the bus model.
5. Understand limitations of bus-to-bus routing, rules for receiving events from other accounts, and direct delivery to cross-account targets.
6. Monitor **CloudWatch metrics, DLQs, retries, IAM/KMS, CloudTrail**, and ingest, storage, and replay costs.
7. Use **read-only** AWS CLI commands to inspect configurations and diagnose failures.
8. Apply these concepts to an Orders → Billing → Analytics architecture, projection rebuilds, and duplicate-free replays.

## 1. When do you need archive, replay, and cross-account delivery?

Suppose a Java Spring Boot order management application runs in **Account A**. When a user places an order, the application emits an **OrderCreated** event. **Billing in Account B** issues invoices; **Analytics in Account C** updates reports.

Possible scenarios:

- The Billing consumer fails due to a buggy new Lambda release.
- An IAM policy change prevents some events from reaching the target.
- Analytics needs to add a new data field and **rebuild projections from history**.
- The system needs account isolation for IAM least privilege, data ownership, and billing boundaries.
- A runtime failure causes a consumer to process the same event twice.

**EventBridge archive/replay** lets you store and re-emit history within a specific event bus model; **cross-account delivery** decouples event producers from event consumers. Yet neither feature guarantees by itself that a consumer processes a transaction exactly once.

~~~mermaid
flowchart LR
  O["Orders service - Account A"] --> BUS["EventBridge bus"]
  BUS --> B["Billing - Account B"]
  BUS --> A["Analytics - Account C"]
  BUS -.-> H["Archive / Retention"]
  H -.->|"Replay"| BUS
  B --> DB[("Invoice database")]
  A --> PROJ[("Analytics projection")]
~~~

Note: this diagram shows logical relationships. **How buses/rules/subscribers are implemented** depends on the EventBridge bus type, not just the service name.

## 2. Two types of EventBridge buses: do not mix APIs

AWS currently has two important models:

| Criterion | **Default / Custom Event Bus – Classic** | **New Custom Event Bus** |
| --- | --- | --- |
| Routing | **Rule** + one or more targets. | **Subscriber** + filter + one target. |
| History storage | Add a separate **Archive**; Classic buses do not retain history for replay by default. | **Built-in retention on the bus**, **1 day** default, configurable **1–365 days**. |
| Replay | Create a **Replay** from an archive back to the same source bus; select specific rules or all rules. | Subscribers read from a **starting position** within retention; no Classic-style `StartReplay`. |
| Cross-account | Resource policy on receiver bus, IAM role when forwarding; direct `PutEvents` if allowed. | **AWS RAM share** the bus so other accounts create subscribers/publish per managed permissions. |
| Ordering | No strict replay ordering guaranteed. | **FIFO per event group, per subscriber** when configured. |
| Deduplication | Consumers design their own idempotency. | Publish deduplication within a documented window; consumers still need idempotency. |
| Format | JSON events via Classic `PutEvents`. | `PutEvents` or `PutRawEvents` with additional formatting support per service. |
| CLI | **`aws events`**. | **`aws eventsv2`**. |
| Metrics | **`AWS/Events`**. | **`AWS/EventsV2`**. |

**Study rule:** if your docs/labs use **`aws events create-archive`**, **`aws events start-replay`**, **`list-rules`**, and **`put-targets`**, that is **Classic**. If they use **`aws eventsv2 create-subscriber`**, **`RetentionPeriodInDays`** on the bus, and **AWS RAM shares**, that is the **new Custom Event Bus**.

Both models coexist, but their logic and limits differ. AWS currently recommends considering the new Custom Event Bus for greenfield applications; existing Classic systems can continue operating or migrate gradually.

### 2.1. Comparison with SQS, SNS, and Step Functions

- **EventBridge:** filters and routes events from producers to consumers; does not store business workflow state.
- **SQS:** durable queue with visibility timeouts, polling, consumer retries, DLQs, and backlog metrics.
- **SNS:** push pub/sub notifications and fan-out.
- **Kinesis:** stream with retention/shards and shard-level read semantics.
- **Step Functions:** stateful orchestration with retries/catches and workflow execution history.

If an order requires a **reserve inventory → charge → ship** chain with compensation, **Step Functions** is better suited for orchestration than emitting three standalone events. If the goal is broadcasting **OrderPaid** to multiple independent accounts, EventBridge fits event routing.

## 3. Event structure and event contract

An illustrative Classic event:

~~~json
{
  "version": "0",
  "id": "eventbridge-generated-id-example",
  "detail-type": "OrderCreated",
  "source": "shop.orders",
  "account": "111122223333",
  "time": "2026-11-20T03:00:00Z",
  "region": "ap-southeast-1",
  "resources": [],
  "detail": {
    "schemaVersion": 2,
    "eventId": "evt-order-10023-v3",
    "orderId": "ORDER-10023",
    "orderVersion": 3,
    "tenantId": "TENANT-42",
    "occurredAt": "2026-11-20T02:59:58Z",
    "currency": "VND",
    "amount": 125000
  }
}
~~~

| Field | Meaning | Notes for replay and cross-account |
| --- | --- | --- |
| **id** | EventBridge event ID. | Does not replace a business idempotency key across all republish paths. |
| **source** | Logical event source. | Use a consistent namespace, e.g., `shop.orders`. |
| **detail-type** | Event type. | Pick a stable name; version when schemas change. |
| **account** | Source AWS account in the envelope. | Useful for cross-account filtering; does not replace IAM authorization. |
| **time** | Event timestamp. | Not when the consumer processed it or when a replay ran. |
| **detail** | Business payload provided by the producer. | Never assume every field has already been verified. |
| **resources** | Related ARNs, may be empty. | Not all AWS service events populate `resources`. |

**Good contract design:** include an **immutable `eventId`**, **`schemaVersion`**, aggregate ID, **`orderVersion`/sequence**, `occurredAt`, and minimal data. Replaying a schema v1 event six months later requires new consumers to **parse the older format** or apply controlled upcasting.

**Never send** passwords, access tokens, secrets, raw payment card details, or unnecessary PII in EventBridge `detail`: data may be archived, forwarded to multiple accounts, logged, and replayed.

## 4. Classic Archive: storing events from one source bus

With the **default event bus** and **Custom Event Bus – Classic**, an archive is a separate resource capturing events from **one source event bus**.

~~~mermaid
flowchart TB
    P["Producer"] --> BUS["Classic EventBridge bus"]
    BUS --> RULE1["Rule: billing-events"]
    BUS --> RULE2["Rule: analytics-events"]
    BUS --> ARC["Archive: orders-history"]
    RULE1 --> SQS["SQS billing"]
    RULE2 --> LAMBDA["Lambda analytics"]
    ARC -.->|"Replay to same bus"| BUS
~~~

Key properties:

- **ArchiveName**: archive name.
- **EventSourceArn**: source event bus ARN; **cannot be changed** after creation.
- **EventPattern**: filters which events enter the archive.
- **RetentionDays**: how many days to keep events; if omitted, Classic archives can **retain indefinitely** by default.
- **KmsKeyIdentifier**: encrypted with an AWS owned key or customer-managed key per supported capabilities.
- **EventCount/SizeBytes**: counts and sizes reconciled by the service.

A bus can have **multiple archives** with different filters/retention periods. Each archive should have an operational owner, tags, retention reviews, logging/auditing, and a clear budget.

### 4.1. Choosing an event pattern for purposeful retention

Example archive keeping only order events emitted from Account A:

~~~json
{
  "account": ["111122223333"],
  "source": ["shop.orders"],
  "detail-type": ["OrderCreated", "OrderPaid", "OrderCancelled"]
}
~~~

This is a **JSON event pattern**, not the full `CreateArchive` payload. Too narrow a filter may omit data needed for recovery; too broad a filter can store sensitive data or inflate costs.

### 4.2. Retention and data deletion rights

| Goal | Example retention | Key considerations |
| --- | --- | --- |
| Short-term consumer failure recovery | 7–14 days. | Enough time to detect and fix bugs. |
| Rebuild reporting | 30–90 days. | Supports recomputing projections from history. |
| Audit purposes | Per internal/legal policy. | An archive is not automatically an immutable audit ledger. |
| Long-term storage | Evaluate dedicated storage/retention. | Watch costs, GDPR/PII, and key lifecycle. |

The timeframes in this table are **illustrative suggestions**, not AWS defaults or legal advice.

### 4.3. Archive ingestion delay and reconciliation

Per AWS:

- Events can reach the archive slightly after the bus receives them; **wait roughly 10 minutes** before replaying newly ingested events so none are missed.
- `DescribeArchive` **`EventCount`/`SizeBytes`** can have a **24-hour reconciliation period**.
- A newly created archive can take time before it starts capturing events.
- Do not conclude "the archive is empty" merely because `EventCount` has not updated immediately.

### 4.4. Encryption and KMS

Archives are encrypted by default with an **AWS owned key**. When using a **customer-managed KMS key**:

- IAM/key policies must permit EventBridge to encrypt/decrypt per documentation.
- Disabling/deleting the key can render the archive inaccessible.
- Manage key rotation, encryption context, and KMS costs.
- Encryption at rest **does not replace** controlling event content, read/log permissions, or forwarding.

## 5. Classic Replay: prerequisites and behavior

A Classic Replay **reads events from an archive** within a time window and **re-injects them into the original source event bus**.

Key parameters:

1. **ReplayName:** unique name for the replay operation.
2. **EventSourceArn:** archive ARN.
3. **EventStartTime / EventEndTime:** filters events by event timestamp.
4. **Destination.Arn:** must be the **archive's source bus**, not any arbitrary bus.
5. **Destination.FilterArns:** optional list of rule ARNs to receive the replay; if omitted, the replay can traverse **all rules** on the bus.

**There is no "Replay directly to another account" option in Classic `StartReplay`.** To reach a downstream account, replay to the source bus and use authorized forwarding rules/targets, or a separate controlled export/import process.

### 5.1. Replay metadata and managed rule

EventBridge adds a **`replay-name`** metadata field to replayed events:

~~~json
{
  "replay-name": "orders-rebuild-2026-11-20"
}
~~~

Archives use an AWS-managed rule to **avoid re-archiving replayed events**, typically using filter logic equivalent to:

~~~json
{
  "replay-name": [
    {"exists": false}
  ]
}
~~~

Consumers can inspect **`replay-name`** to recognize backfills and route to safe code paths, or use replay-only rules. **Never delete the archive's managed rule** to work around routing bugs.

### 5.2. Replay does not guarantee strict ordering

- Events are processed by **event time** in **one-minute buckets**.
- Events within a bucket are **not guaranteed to replay in their exact original order**.
- Replays can interleave with live incoming traffic.
- Replays take time depending on volume and quotas—100,000 events will not arrive instantaneously.
- **`DescribeReplay.EventLastReplayedTime`** tracks progress across the time range.

If a consumer receives `OrderCancelled` v7 and then a replayed `OrderCreated` v3, it must not revert order state to Created. Use **aggregate versions, conditional writes**, or a dedicated rebuild pipeline.

### 5.3. Lifecycle and limits

- AWS docs specify a limit of up to **10 active replays/account/Region**.
- A replay can be canceled while in `STARTING` or `RUNNING` state.
- Replay **does not delete** events from the archive; multiple runs are allowed.
- EventBridge **deletes replay resource records after 90 days**; this is separate from archive retention.
- For recently published events, account for the roughly **10-minute archive lag**.

## 6. Safe replay: production checklist

A replay is an action with **side effects and potential costs**, not a read-only query. Before running:

1. **Goal:** rebuild a report, recover a consumer, or test new code?
2. **Scope:** which event types, accounts, tenants, and UTC start/end times?
3. **Source:** did the archive capture those events, and are they still within retention?
4. **Rules:** target **one specific rule** or all rules?
5. **Side effects:** could it send emails, charge cards, fire webhooks, or corrupt data?
6. **Idempotency:** do consumers enforce `eventId`, aggregate version, and conditional writes?
7. **Schema:** can current code parse historical v1/v2 events?
8. **Capacity:** can Lambda/SQS/RDS/HTTP APIs handle replay + live traffic?
9. **Monitoring:** are CloudWatch, DLQs, progress, and business outcomes watched?
10. **Rollback:** is there a plan to stop/cancel, disable secondary consumers, or restore projections?
11. **Approval:** owner/incident ticket/change window and least-privilege IAM?

### 6.1. Test replay with a small window

Suppose the **`rebuild-analytics`** target is idempotent, and the archive holds events from 10:00–11:00 UTC on the incident day:

- Run a pilot for **10:00–10:05** targeting only the rebuild rule.
- Compare order record counts against projected rows.
- Check DLQs, stale versions, and exception logs.
- Check database load.
- Once verified, proceed through the remaining time windows.

If a production rule **`charge-credit-card`** also matches `OrderPaid`, **do not** replay to all rules until you prove cards cannot be double-charged.

### 6.2. Replay does not restore original upstream data

Historical events may reference S3 objects that were deleted or schemas that changed. An archive does not restore those objects or database states. For major data loss, **backup/restore** and reconciliation are needed alongside or instead of replay.

Replay also does not alter Step Functions execution history; it cannot automatically repair failed workflows when underlying business state has moved on.

## 7. Idempotency, schema evolution, and ordering

### 7.1. Why is a business `eventId` critical?

A single business event may:

- Be republished by the producer if an ACK was lost.
- Arrive twice due to target retries.
- Be replayed from an archive multiple times.
- Cross accounts via another bus.
- Be backfilled by a separate producer with a new transport event ID.

Therefore, you need a stable **`detail.eventId`** or **`operationId`**, not just reliance on the EventBridge envelope **`id`**.

~~~json
{
  "detail": {
    "schemaVersion": 2,
    "eventId": "order-10023-paid-v4",
    "orderId": "ORDER-10023",
    "orderVersion": 4,
    "paymentTransactionId": "PAYMENT-TXN-EXAMPLE"
  }
}
~~~

### 7.2. Conditional writes and transactional inbox

With DynamoDB, you can use **`ConditionExpression attribute_not_exists(eventId)`** to avoid inserting duplicate markers. However, if you write the marker first and the side effect fails, a retry sees the marker and **skips unfinished work**.

A stronger design:

- Use **`TransactWriteItems`** to write the dedup marker and business state in the same transaction when both live in DynamoDB.
- With SQL databases, wrap a **`processed_event`** unique key insert and the business update in one transaction.
- With external payment providers, use a provider-supported **idempotency key**, not just an internal DB transaction.
- Across disparate systems, use **transactional outbox/inbox + reconciliation** per your architecture.

### 7.3. Guarding with aggregate version

A consumer tracks **`lastAppliedVersion`** per `orderId`:

~~~text
If incomingVersion <= lastAppliedVersion:
  Duplicate or stale event; do not overwrite state.
If incomingVersion == lastAppliedVersion + 1:
  Apply the update accordingly.
If incomingVersion > lastAppliedVersion + 1:
  Gap detected; buffer/retry or query the source of truth.
~~~

Exact logic depends on the domain; events that do not increment strictly by one per aggregate need a different ordering model.

**Example:** Do not let a replayed `OrderCreated` v3 arriving after a live `OrderShipped` v8 make the system revert to "order just created." That is why replay and event ordering must be designed together.

### 7.4. Side effects that cannot be blindly re-run

- Sending email: use a **notification dispatch key**.
- Charging credit cards: use a **payment idempotency key and ledger**.
- Calling webhooks: verify whether the partner deduplicates.
- Analytics projections: upsert with event version/checkpoint.
- Inventory updates: use atomic conditional updates so stock is never deducted twice.

**Replay does not equal exactly-once business processing.**

## 8. Classic: sending events to another AWS account

**Classic pattern:** Account A emits `OrderCreated` on its source bus; a rule targets **Account B's bus**; Account B uses its own rule to route events to an SQS/Lambda consumer.

~~~mermaid
flowchart LR
    subgraph A["Account A — Orders"]
        PUB["Orders Spring Boot / outbox publisher"] --> BA["Classic bus orders-events"]
        BA --> RA["Rule forward-to-billing"]
        RA --> ROLE["IAM delivery role"]
    end
    subgraph B["Account B — Billing"]
        POLICY["Bus resource-based policy"] --> BB["Classic bus billing-events"]
        BB --> RB["Rule accept-order-created"]
        RB --> SQS["Billing SQS + DLQ"]
        SQS --> JAVA["Java consumer"]
        JAVA --> DB[("Billing RDS")]
    end
    ROLE -->|"events:PutEvents"| BB
~~~

**Both sides must grant permissions and configure routing:**

1. Account B creates the destination bus and a **resource-based policy** allowing Account A/its role to publish.
2. Account A creates a rule matching `OrderCreated` with the destination bus ARN as target.
3. Account A attaches an IAM **delivery role** for EventBridge with **`events:PutEvents`** on the destination bus ARN.
4. Account B creates a rule matching **`account`/`source`/`detail-type`** and attaches its target.
5. For SQS/Lambda targets, resource policies/execution permissions must be configured per target type.
6. Monitor both buses, rule target delivery, queue backlogs, and consumers.

### 8.1. Example IAM role for a forwarding rule

Trust policy allowing EventBridge to assume the role:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "events.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Identity policy attached to Account A's delivery role:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PutOnlyToBillingEvents",
      "Effect": "Allow",
      "Action": "events:PutEvents",
      "Resource": "arn:aws:events:ap-southeast-1:444455556666:event-bus/billing-events"
    }
  ]
}
~~~

These are illustrative policy fragments; production trust policies should evaluate **`aws:SourceArn`/`aws:SourceAccount`** conditions as supported by AWS to mitigate confused deputy risks, alongside IAM permissions boundaries/SCPs where applicable.

AWS requires **new cross-account event bus targets** to attach an IAM role; legacy targets created before the 2023 change may differ. Do not follow an old CLI snippet and omit the role in new architectures.

### 8.2. Resource policy on Account B's destination bus

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowOrdersAccount",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:root"
      },
      "Action": "events:PutEvents",
      "Resource": "arn:aws:events:ap-southeast-1:444455556666:event-bus/billing-events"
    }
  ]
}
~~~

Here Account A's root ARN **represents the account principal** in the policy; it does not mean using root access keys to publish. For tighter security, scope the principal to a specific delivery role or use AWS-supported conditions.

**Never set `Principal = "*"` on a production bus** unless guarded by strict policy conditions and an approved business justification.

### 8.3. Using AWS Organizations

You can allow an AWS Organization to publish using **`aws:PrincipalOrgID`**, e.g.:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": "*",
      "Action": "events:PutEvents",
      "Resource": "arn:aws:events:ap-southeast-1:444455556666:event-bus/billing-events",
      "Condition": {
        "StringEquals": {
          "aws:PrincipalOrgID": "o-exampleorg"
        }
      }
    }
  ]
}
~~~

The organization ID value is a placeholder. If the Organization contains hundreds of accounts, this access may be broader than intended; narrow by **account/role/source** and SCP boundaries. **Organization membership does not remove the sender's need for an IAM delivery role.**

### 8.4. Receiver rule filtering the exact account

~~~json
{
  "account": ["111122223333"],
  "source": ["shop.orders"],
  "detail-type": ["OrderCreated"]
}
~~~

Do not write **`account: ["*"]`** expecting EventBridge to match any account; that literal string never appears as an account ID. To match all incoming accounts permitted by the bus policy, omit the `account` field, though weigh that risk carefully.

An event arriving on a bus is not inherently valid in business terms: a producer may emit bad payloads, or an authorized account may be compromised. Consumers must still validate schemas, trusted sources, aggregate IDs, and data permissions.

## 9. Classic: multi-hop forwarding and cross-Region limits

### 9.1. Do not build an A → B → C chain via consecutive rule forwarding

AWS explicitly states:

- If **Account A** forwards to **Account B**'s bus, a rule in B **will not automatically forward that event received from A** onward to **Account C**'s bus via the same Classic bus-to-bus mechanism.
- Similar restrictions apply to certain bus-to-bus chains within the same account.

**Consequence:** Do not design an **Orders A → Billing B → Analytics C** pipeline relying on endless rule-to-bus forwarding. Instead:

- **Account A** can route separately to B and C if authorized.
- Use a **central event bus** with appropriate rules/targets.
- For greenfield designs, consider a **shared Custom Event Bus + consumer-owned subscribers**.
- If a consumer needs to emit a **business-new event**, it can publish a **new event** with a distinct event type/operation rather than trying to relay the raw original event across multiple buses.

### 9.2. Cross-Region does not mean every Region is permitted

Classic bus-to-bus cross-account:

- Works **within the same Region** in supported Regions.
- Cross-Region requires the destination Region to be in the **AWS-supported set of Regions for cross-Region event delivery**.
- Requires IAM roles/resources in the right Regions, exact endpoint ARNs, quotas, and network/data-residency review.
- Cross-Region delivery impacts **latency, cost, and data-residency rules**.

Do not hardcode `ap-southeast-1` in code and swap only the account ID when the destination bus actually lives in `ap-northeast-1`. Verify ARNs/Regions and feature limits.

### 9.3. Watch out for loops

A rule can send an event to another bus and have it return via application logic. Even though the service has product/version loop guards, **never design applications assuming AWS automatically catches every loop**.

Safeguards:

- Be specific in **`source`/`detail-type`** and `account` event patterns.
- Ensure consumer outputs do not unintentionally match the input trigger.
- Maintain business operation IDs/idempotency.
- Monitor **`PutEvents` rate**, target invocations, DLQs, and cost anomalies.
- With S3/SQS/Lambda handlers, guard against infinite self-triggers.

## 10. Classic: direct cross-account service targets

AWS also supports **EventBridge Classic rules sending events directly to certain AWS service targets in another account**, rather than always hopping through a destination bus.

Per current documentation, **same-Region** cross-account direct targets include supported services such as:

- **Amazon SQS queue**.
- **AWS Lambda function**.
- **Amazon SNS topic**.
- **Amazon Kinesis Data Streams**.
- **Amazon API Gateway API**.

This is a **cross-account target service** pattern, distinct from the "bus-to-bus" pattern in section 8.

~~~mermaid
flowchart LR
    subgraph A["Account A"]
      BUS["Classic EventBridge bus"] --> RULE["Rule: order-created"]
      RULE --> ROLE["EventBridge delivery role"]
    end
    subgraph B["Account B"]
      RESOURCE_POLICY["Target resource policy"] --> Q["SQS billing queue"]
    end
    ROLE -->|"sqs:SendMessage (IAM)"| Q
~~~

### 10.1. Two permission layers for direct delivery

1. The rule's **execution role** lives in the **same account as the source bus** and has action permissions on the target, e.g., **`sqs:SendMessage`**.
2. The destination target's **resource policy** permits invocation from that principal/role per that service's documentation.
3. Verify the target service/Region is in the supported list for direct cross-account delivery.
4. For customer-managed KMS keys, configure sufficient KMS policies.
5. Add a DLQ or on-failure path to capture failed deliveries.

**Do not confuse** a role needing `events:PutEvents` when the target is an **event bus** with a role needing **`sqs:SendMessage`/`lambda:InvokeFunction`** when targeting a service directly.

### 10.2. When to choose bus-to-bus vs. direct service target?

| Requirement | **Classic bus-to-bus** | **Direct service target** |
| --- | --- | --- |
| Account B defines multiple rules/consumers itself. | Strong: event lands on bus B, B owns routing. | Less flexible; source defines the target. |
| Only one SQS queue in Account B needs the event. | Extra bus/rule may be unnecessary. | Clean if same Region and supported service. |
| Decouple producer from target implementation. | Decouples cleanly. | Sender knows the target ARN type. |
| Need cross-Region delivery. | Check supported destination Regions. | Direct cross-account service targets are documented as **same Region** only. |
| Consumer accounts should own subscriptions on a shared bus. | Classic is not the best fit. | Consider new Custom Event Bus + AWS RAM. |

## 11. New Custom Event Bus: retention and subscriber-owned routing

The new **Custom Event Bus** differs from Classic: the bus ingests and **retains events**, and consumers create **subscribers** to receive filtered events.

~~~mermaid
flowchart TB
    subgraph OWNER["Account A — Bus owner"]
      PUB["Orders producer"] --> BUS["Custom Event Bus: orders"]
      BUS -.-> RET["Built-in retention 1–365 days"]
    end
    subgraph BILL["Account B — Billing"]
      SB["Subscriber billing"] --> SQS["SQS billing"]
    end
    subgraph ANA["Account C — Analytics"]
      SA["Subscriber analytics"] --> L["Lambda analytics"]
    end
    BUS -->|"AWS RAM share + subscriber"| SB
    BUS -->|"AWS RAM share + subscriber"| SA
    RET -.->|"Historical starting position"| SB
    RET -.->|"Historical starting position"| SA
~~~

**Major ownership difference:**

- Account A owns the **bus** and can share it with other accounts.
- Account B creates and owns **B's subscriber** on the shared bus.
- Account C creates and owns **C's subscriber**.
- The bus owner can view subscribers on the bus; each consumer account generally manages only its own subscribers.
- Account B cannot update/delete the bus or another account's subscribers.
- To forcibly terminate an existing subscriber, the bus owner has **`RevokeResource`** per documentation.

### 11.1. Custom Event Bus retention

A custom bus retains events according to **`StorageConfiguration.RetentionPeriodInDays`**, from **1 to 365 days**, defaulting to **1 day** if omitted. This retention lives on the bus itself, with no Classic Archive required.

**`DescribeEventBus.RetentionWindowStartTime`** indicates the earliest timestamp available to read retained events. Do not apply Classic's "indefinite default archive retention" rule to the new Custom Event Bus.

Longer retention expands replay capability while increasing **storage charges** and PII/data-retention obligations.

### 11.2. Starting a subscriber from the past

Subscribers have two main starting position modes:

- **`LATEST`:** receives only new events emitted after the subscriber starts.
- **`POINT_IN_TIME`:** receives retained events starting from a chosen point inside the retention window.

With `POINT_IN_TIME`:

- **`PointType = HORIZON`:** earliest available point in the retention window.
- **`PointType = TIMESTAMP`:** `StartingPoint` at a specific timestamp.
- You can set an **`EndPoint`** to replay up to a stop time; otherwise, the subscriber **catches up to live traffic and keeps receiving new events**.
- `StartingPoint` must fall inside the retention window and not in the future.
- For open-ended starts, documentation requires **`StartingPoint` to be at least 5 minutes in the past**; exceptions apply when `EndPoint` is specified.

**This is replay via subscriber starting position**, not calling Classic `StartReplay`. Replays take time to initialize; do not declare failure if events do not appear instantaneously.

### 11.3. Distinguishing live vs. replay on the new Custom bus

Events delivered to a subscriber include **`SystemMetadata.aws:DeliveryType`**:

~~~json
{
  "SystemMetadata": {
    "aws:DeliveryType": "REPLAY"
  }
}
~~~

Values are **`LIVE`** for new events and **`REPLAY`** for re-read retained events. The snippet shows only part of the metadata, not the full payload.

**Do not confuse** Classic's **`replay-name`** field with Custom bus's **`aws:DeliveryType`**. If a consumer needs idempotency across both, use a business `eventId`/aggregate version independent of the transport mechanism.

### 11.4. FIFO and deduplication do not equal exactly-once

Custom buses support:

- FIFO per **event group** on each subscriber under matching configurations.
- Publish-time deduplication by content or key within a documented **5-minute window**.
- Retention and subscriber pause/resume.

However:

- Duplicates can still occur outside the dedup window or during downstream retries.
- Any event with side effects requires business idempotency.
- FIFO within an event group is **not global ordering** across all accounts/tenants.
- Target retries, transformations, and consumer bugs still must be handled.

### 11.5. Schemas and payload formats

Custom Event Bus provides **`PutRawEvents`** to support payloads like JSON, Avro, Protobuf/raw bytes per feature/schema registry capabilities. Do not push raw binary bytes via Classic `PutEvents` expecting subscribers to parse them as raw events.

When a consumer filters on fields, verify whether payloads are deserialized under supported settings; event filters do not automatically understand arbitrary binary schemas.

## 12. Cross-account on the new Custom Event Bus: AWS RAM

With the new Custom Event Bus, AWS recommends **sharing the bus via AWS Resource Access Manager (RAM)** instead of Classic's required forwarding to a separate receiving bus.

### 12.1. Common RAM permission types

| AWS RAM permission | What can the consumer account do? |
| --- | --- |
| **`AWSRAMEventBridgeEventBusV2PublishOnly`** | Publish events and describe the bus. |
| **`AWSRAMEventBridgeEventBusV2SubscribeOnly`** | Create/manage its own subscribers and describe the bus. |
| **`AWSRAMEventBridgeEventBusV2EventSourceAccess`** | Attach and manage its own event sources per permissions. |
| **`AWSRAMEventBridgeEventBusV2FullAccess`** | Combined publish, subscriber, and event source actions allowed by the managed permission. |

Apply **least privilege**: if Billing only consumes Orders events, grant **`SubscribeOnly`**, not `FullAccess`.

When sharing a bus:

1. The bus owner picks the new Custom Event Bus ARN, target accounts/OUs, and RAM permission.
2. When sharing outside AWS Organizations, the consumer may need to **accept the invitation**.
3. The consumer still needs its own **IAM identity policy** alongside the RAM grant; both sides must allow access.
4. The consumer creates a subscriber on the shared bus in the same Region.
5. The bus owner monitors delivery/egress by subscriber account and can revoke access when needed.

### 12.2. Regional boundary

A Custom Event Bus is shared with consumer accounts in the **same Region and partition** as the bus. It is not a protocol for cross-Region subscriber sharing.

Do not copy **Classic bus-to-bus cross-Region** rules onto the RAM subscriber model.

### 12.3. Removing a RAM share may not stop existing subscribers

Important security caveat:

- Removing a resource share/permission stops another account from **creating new subscribers or publishing new events**.
- However, subscribers already created while the share was active **may continue receiving deliveries** per Custom bus authorization behavior.
- To fully terminate an existing consumer, the bus owner must call **`RevokeResource`** or manage subscriber lifecycle per AWS guidance.

Therefore, partner/account offboarding needs a full checklist: **unshare → revoke resource(s) → verify delivery stopped → review access logs/CloudTrail**.

### 12.4. Resource policies and conditions

A Custom bus can use a custom resource policy when RAM managed permissions cannot express **explicit Deny**, conditions, or special scopes.

A Custom bus can have both an owner-managed policy and an **`AWS_RAM`** policy written by RAM. An **explicit Deny** in either policy overrides Allows from the other. Never inspect only one policy and assume access succeeds.

**Do not** copy Classic EventBridge bus resource-policy JSON onto an **`event-busv2` ARN** without checking allowed IAM actions and ARN formats for Custom buses.

## 13. When to choose Classic vs. the new Custom Event Bus?

| Context | Initial choice |
| --- | --- |
| Using AWS service events on the default bus, rules/targets, and archives. | **Classic** and existing archive/replay workflows. |
| Multiple new accounts where each team wants to own its subscribers on a shared bus. | **New Custom Event Bus + RAM**. |
| Need independent per-consumer replay with built-in retention. | **New Custom Event Bus**. |
| System deeply relies on Classic rule `InputTransformer` and routing semantics. | Keep Classic or plan a structured migration; equivalent Custom bus features need proper configuration. |
| Route one rule to Lambda/SQS in another account (same Region) with no destination bus. | **Classic direct cross-account service target** if supported. |
| Need traditional JSON `PutEvents` API on the default bus. | **Default / Classic**. |
| Want per-entity-group FIFO and publish-time deduplication in the new feature set. | **Custom Event Bus**, still implementing consumer idempotency. |

### 13.1. Do not migrate simply by renaming ARNs

AWS allows Classic and Custom buses to run side by side per documentation, yet their **resource models differ**:

- Classic **rule + target** maps to one or more **subscribers**.
- Classic **archive + replay** maps to **retention + starting position**.
- Classic event patterns translate into appropriate subscriber filters.
- Classic input transformers and target configurations must migrate to the new transformer/invocation configuration model.

A safe migration requires contract tests, shadow consumption or controlled dual-reads, business deduplication, and test budget. You cannot transfer historical events simply by renaming a bus.

## 14. IAM, Organizations, KMS, and responsibility boundaries

### 14.1. Distinguishing principals

| Principal | Required permissions | Do not confuse with |
| --- | --- | --- |
| **Producer app IAM role** | Publish to allowed bus: `events:PutEvents` or `PutRawEvents` per bus. | Consumer role. |
| **Classic rule delivery role** | Assumed by EventBridge to send to target bus/service. | App user allowed to edit bus policies. |
| **Destination Classic bus policy** | Allows accounts/roles to publish. | Rule filter or backend authorization. |
| **Custom RAM share** | Grants another account publish/subscribe permissions. | That account's own IAM identity policy. |
| **Custom subscriber delivery role** | Lets EventBridge send events to target and failure destination. | Bus owner admin role. |
| **Consumer runtime role** | Reads SQS, writes DB/S3 per business logic. | Broad permissions to create/delete archives. |
| **Operator role** | Describes/reads metrics and starts replays per procedure. | Permissions to deploy all services. |

Never use wildcard `events:*` across all accounts for debugging convenience. Separate roles for **publisher, subscriber, operator, and security auditor**.

### 14.2. Least-privilege practices

- Scope destination ARNs, accounts, and Regions.
- Use **`aws:PrincipalOrgID`**, **`events:source`**, and appropriate conditions where supported.
- Grant **`events:StartReplay`** only to operators, not every application role.
- For KMS CMKs, configure key policies for exact service principals and encryption contexts.
- Audit `CreateArchive`, `DeleteArchive`, `StartReplay`, `PutPermission`, `PutRule`, `PutTargets`, and RAM share/subscriber changes.
- Prevent operators from replaying historical PII to consumers outside approved scope.
- Test **explicit Deny/SCPs** and account ownership, not just `Allow` statements.

### 14.3. Payload security

Before sending events cross-account:

1. Minimize payloads: pass `orderId` instead of full street addresses/payment cards when unneeded.
2. Classify data: PII, sensitive fields, and retention periods.
3. Encrypt at rest/in transit per service; use CMKs when policy dictates.
4. Govern consumer accounts and roles via organization policies.
5. Establish schema compatibility and validation.
6. Prevent accidental republishing back to external accounts.
7. Track contract/data deletion obligations when replaying history.

**Splitting AWS accounts does not remove data-protection obligations**; cross-account delivery is real data sharing and must be governed.

## 15. Monitoring archive, replay, and cross-account delivery

You cannot resolve incidents knowing only that the producer called `PutEvents`. Monitor **producer → source bus → filter/rule → target/receiver bus → consumer → business state**.

### 15.1. CloudWatch metrics for Classic buses

Classic EventBridge uses the **`AWS/Events`** namespace, with key metrics:

| Metric | Interpretation | Check when |
| --- | --- | --- |
| **`PutEventsEntries`** | Entries sent to the event bus via API. | Unusual spike/drop in producer event volume. |
| **`PutEventsFailedEntries`** | Events rejected by `PutEvents`. | Publish errors, quotas, schema/payload issues. |
| **`MatchedEvents`** | Events matching rules per dimension. | Events sent yet rules do not trigger. |
| **`TriggeredRules`** | Rules triggered/matched. | Wrong event pattern/account. |
| **`Invocations`** | Target invocations from rules. | Match occurs yet target is not called. |
| **`InvocationAttempts`** | Attempts by EventBridge to invoke targets. | Slow delivery or heavy retries. |
| **`RetryInvocationAttempts`** | Number of target retries. | Downstream throttled/unavailable. |
| **`FailedInvocations`** | Permanently failed invocations. | Target, policy, or quota needs fixing. |
| **`InvocationsSentToDlq`** | Failure records sent to DLQ. | Needs triage and redrive. |
| **`InvocationsFailedToBeSentToDlq`** | Failed to write failed delivery to DLQ. | Risk of losing recovery path. |
| **`IngestionToInvocationSuccessLatency`** | Time from ingest to successful target call. | Retries or slow backend. |

**Note:** Some metrics emit datapoints only on errors/invocations. "No datapoints" does not guarantee "zero errors" if time range, Region, dimensions, or activity are mismatched.

### 15.2. Observing archive/replay

- **`DescribeArchive.State`**, `EventSourceArn`, `EventPattern`, `RetentionDays`, and `KmsKeyIdentifier`.
- **`EventCount`/`SizeBytes`**, remembering reconciliation can take up to **24 hours**.
- **`DescribeReplay.State`**, `EventStartTime`, `EventEndTime`, `EventLastReplayedTime`, and `StateReason`.
- **Consumer logs** tagged with business `eventId`, `aggregateVersion`, `replay-name`, and processing result.
- **DLQ/target health** and actual rows rebuilt.

Replay state **`COMPLETED`** confirms only the EventBridge replay operation—it **does not prove** Billing recorded invoices accurately.

### 15.3. Consumer-side monitoring

| Consumer | Metrics |
| --- | --- |
| SQS worker | `ApproximateNumberOfMessagesVisible`, `ApproximateAgeOfOldestMessage`, DLQ depth. |
| Lambda | `Invocations`, `Errors`, `Duration`, `Throttles`, `ConcurrentExecutions`. |
| Step Functions | `ExecutionsFailed`/`TimedOut`, business execution status. |
| Database | Connections, write errors, latency, conditional check failures, row counts. |
| Business | `OrdersCreated`, `InvoicesIssued`, `DuplicateOperationsSkipped`, `RebuildCheckpoint`. |

A rule forwarding to SQS successfully while workers fail to poll causes backlog growth with **EventBridge `FailedInvocations` still at 0**.

## 16. Observability for the new Custom Event Bus

Custom Event Bus uses the **`AWS/EventsV2`** metrics namespace, distinct from Classic.

| Metric | Explanation |
| --- | --- |
| **`FilterEvaluated`** | Events evaluated against subscriber filters. |
| **`FilterMatched`** | Events matching all filters. |
| **`EventDeliveryAttempts`** | Delivery attempts, including retries. |
| **`TargetInvocations`** | Target API calls (one call may carry a batch). |
| **`EventsDelivered`** | Number of events accepted by the target. |
| **`RetryInvocationAttempts`** | Number of delivery retry attempts. |
| **`EventTransformationFailures`** | Transform/filter-related expression failures. |
| **`EgressBytes`** | Delivery byte volume. |
| **`IngestionToInvocationStartTime`** | Latency from ingest to start of target invocation. |
| **`OnFailureDestinationDelivered`** | Failure records delivered to the on-failure destination. |
| **`OnFailureDestinationFailed`** | Failures delivering to the on-failure destination. |
| **`EventsDropped`** | Events whose retries exhausted with no on-failure destination. |
| **`ApproximateBacklogAge`** | Age of the oldest undelivered subscriber event. |

Dimensions like **`EventBus`/`Subscriber`** and **`SubscriberAccount`** track consumption by account. For subscriber logs, configure log levels and payload retention carefully: logging full customer data increases cost and PII exposure.

Never add **`TargetInvocations`** as business event counts: one target call can carry a batch. Never treat **`EventsDelivered`** as committed business transactions: target acceptance and business execution are two separate steps.

## 17. Retry, DLQ, and archive: three distinct roles

### 17.1. Classic target retries

EventBridge Classic has a **`RetryPolicy`** for target delivery. Under common defaults, EventBridge retries for **up to 24 hours or 185 attempts**, with backoff/jitter. Actual behavior depends on policy settings and target type.

- **Retry**: handles transient errors when a target is throttled or temporarily unavailable.
- **DLQ**: captures failed deliveries once retries are exhausted and a DLQ is configured.
- **Archive**: retains event history from a bus for future replay.

A DLQ holding failed deliveries **is not a complete copy of all events**. An archive holding events **does not replace redriving failures** per a runbook.

### 17.2. Custom subscriber retries

The new Custom Event Bus has subscriber **`RetryPolicy`** and **`OnFailureConfiguration`**; defaults/limits differ from Classic—check **`DescribeSubscriber`**. Current documentation states defaults of **5 attempts and 300 seconds** for subscribers.

When deliveries fail repeatedly:

1. Fix IAM/KMS/target errors.
2. Verify the on-failure destination is writable.
3. While events remain in retention, consider creating a subscriber replay for the exact time/IDs.
4. Never blindly replay the entire bus when only a few messages failed.

### 17.3. Sample DLQ runbook

1. Alarm triggers on **`InvocationsSentToDlq`/`OnFailureDestinationDelivered`**.
2. Operator reads failure metadata to identify `errorCode`, target ARN, and source event.
3. Separate **permanent** errors (invalid schema/permission denied) from **transient** ones (throttle/timeout).
4. Fix config/code and test with one event.
5. Redrive/replay in subsets with checkpoints.
6. Verify business outcomes and delete/mark processed messages in the DLQ.
7. Write an incident summary and improve metrics/alerts.

**Never leave a DLQ unmonitored without alert owners**, as that only delays addressing data loss.

### 17.4. Multi-layer retries multiply attempts

An event routed to Lambda can be retried by:

- EventBridge target delivery retries.
- Lambda async invocation retries.
- SDK HTTP retries.
- Consumer-level DB/3rd-party API retries.

Account for total attempts and side effects. For payments, use idempotency keys and a transaction ledger; never trust "having one `eventId`" alone to prevent double charges.

## 18. Cost and capacity control

### 18.1. Cost drivers

| Item | What to estimate |
| --- | --- |
| **Classic `PutEvents`** | Custom event ingest and metered size. |
| **Classic cross-account bus-to-bus** | Per Classic pricing, the sender pays the **custom event** charge, while the receiver is not billed again for receiving that cross-account event itself. |
| **Classic Archive** | Archival processing and storage by data/retention. |
| **Classic Replay** | Replay traffic and downstream deliveries per pricing schedule. |
| **New Custom Event Bus** | Publish, delivery to subscribers, and built-in retention. |
| **SQS/Lambda/Step Functions** | Requests, compute, queue calls, executions, and retries. |
| **CloudWatch/KMS** | Logs, metrics, alarms, key calls, and data visibility. |
| **Cross-Region transfer** | Where architecture/capabilities span Regions, measure transfer fees and latency separately. |

This table lists **cost components**, not fixed unit prices. Check AWS EventBridge Pricing for your Region, event type, payload size, and bus model.

### 18.2. Capacity estimation

Suppose Orders emits **500,000 events/day**, averaging **2 KiB** per event, retained for **30 days**:

\[
500{,}000\times2\ \text{KiB}\times30
=30{,}000{,}000\ \text{KiB}
\approx28.6\ \text{GiB}
\]

This is raw payload data before overhead/metering, not the exact GB AWS bills.

Replaying all 30 days feeds **15 million events** into consumers. With three targets, deliveries, retries, and downstream costs can be much higher. Load-test DBs, queues, and quotas before replaying large volumes.

### 18.3. Optimizing costs properly

- Write event patterns/filters to capture only truly needed events.
- Align retention to business needs; avoid unreviewed indefinite Classic archives.
- Specify **`FilterArns`** on Classic replays rather than All rules when rebuilding a single consumer.
- Avoid replaying workflows with unintended side effects.
- Track **cost per successful business outcome**, not just cost per event.
- Use AWS Budgets/Cost Anomaly Detection, remembering budget alerts are not hard caps.
- Cap concurrency/retries and alert on abnormal event volume spikes.
- Govern IAM/KMS so archives/retention cannot be deleted or opened arbitrarily.

## 19. Read-only AWS CLI: Classic event bus, archive, replay

The commands below **do not modify resources**, start replays, or emit real events. Replace illustrative account/ARN/Region values with authorized resources.

### 19.1. Identify account and buses

~~~bash
aws sts get-caller-identity

aws events list-event-buses \
  --region ap-southeast-1

aws events describe-event-bus \
  --name orders-events \
  --region ap-southeast-1
~~~

Inspect **`Name`, `Arn`, `Policy`, `KmsKeyIdentifier`** and confirm the exact account/Region. One user may access multiple AWS accounts; never assume based on bus name alone.

### 19.2. Inspect rules and targets

~~~bash
aws events list-rules \
  --event-bus-name orders-events \
  --region ap-southeast-1

aws events describe-rule \
  --name forward-to-billing \
  --event-bus-name orders-events \
  --region ap-southeast-1

aws events list-targets-by-rule \
  --rule forward-to-billing \
  --event-bus-name orders-events \
  --region ap-southeast-1
~~~

Check **`EventPattern`, `Rule State`, `Targets[].Arn`, `Targets[].RoleArn`, `RetryPolicy`, and `DeadLetterConfig`**. The bus target's `RoleArn` needs permissions in the sending account; the receiving bus needs a resource policy.

### 19.3. Inspect archives

~~~bash
aws events list-archives \
  --region ap-southeast-1

aws events describe-archive \
  --archive-name orders-history \
  --region ap-southeast-1
~~~

Key fields: **`EventSourceArn`, `EventPattern`, `RetentionDays`, `State`, `EventCount`, `SizeBytes`, `KmsKeyIdentifier`**. Counts/sizes update asynchronously; never treat them as real-time metrics.

### 19.4. Inspect replay progress

~~~bash
aws events list-replays \
  --region ap-southeast-1

aws events describe-replay \
  --replay-name orders-rebuild-2026-11-20 \
  --region ap-southeast-1
~~~

Check **`EventLastReplayedTime`, `EventStartTime`, `EventEndTime`, `Destination.FilterArns`, `StateReason`**. `State = COMPLETED` does not prove consumers processed all business records.

### 19.5. Test patterns safely

**`aws events test-event-pattern`** validates a JSON pattern against a sample event without publishing a real event. Use it to catch **`account`/`source`/`detail-type`** mismatches, while verifying IAM and target delivery separately.

## 20. Read-only AWS CLI: new Custom Event Bus

Requires AWS CLI with the **`eventsv2`** namespace. If an older CLI lacks these commands, upgrade per organizational procedure—do not switch to `aws events` and mix API models.

### 20.1. List owned/shared buses

~~~bash
aws eventsv2 list-event-buses \
  --region ap-southeast-1

aws eventsv2 list-event-buses \
  --event-bus-account-id 111122223333 \
  --region ap-southeast-1
~~~

Check **`EventBusArn`, `EventBusAccountId`, and `State`**; RAM-shared buses appear as owned by another account.

### 20.2. Bus retention and retention window

~~~bash
aws eventsv2 describe-event-bus \
  --event-bus-arn arn:aws:events:ap-southeast-1:111122223333:event-busv2/orders/EXAMPLE1234567890abcdef1234567 \
  --region ap-southeast-1
~~~

The ARN is a **placeholder**. Use the real ARN from `list-event-buses`. Inspect **`StorageConfiguration.RetentionPeriodInDays`, `RetentionWindowStartTime`, `State`**.

### 20.3. Subscribers and replay status

~~~bash
aws eventsv2 list-subscribers \
  --event-bus-arn arn:aws:events:ap-southeast-1:111122223333:event-busv2/orders/EXAMPLE1234567890abcdef1234567 \
  --region ap-southeast-1

aws eventsv2 describe-subscriber \
  --subscriber-arn arn:aws:events:ap-southeast-1:444455556666:subscriber/billing/EXAMPLE1234567890abcdef1234567 \
  --region ap-southeast-1
~~~

Inspect **`StartingPosition`, `PointInTimeConfiguration`, `FilterConfiguration`, `InvokeConfiguration`, `RetryPolicy`, `OnFailureConfiguration`, and `State`**. Consumer accounts may only see their own subscribers; the bus owner has broader visibility per documentation.

### 20.4. Mutating commands excluded from read-only labs

Do not run these commands in a read-only lab because they alter history, routing, IAM, or costs:

~~~text
aws events start-replay
aws events cancel-replay
aws events create-archive
aws events delete-archive
aws events put-rule
aws events put-targets
aws eventsv2 create-event-bus
aws eventsv2 create-subscriber
aws eventsv2 revoke-resource
aws ram create-resource-share
~~~

Creating/modifying real resources requires a lab account, IAM approval, IaC review, monitoring, and rollback.

## 21. Runbook: investigating events missing at consumer

~~~mermaid
flowchart TD
    S["Events not reaching Billing"] --> A{"Producer PutEvents succeeded?"}
    A -->|"No"| A1["Check IAM, payload, FailedEntryCount, quotas"]
    A -->|"Yes"| B{"Source rule / subscriber filter matched?"}
    B -->|"No"| B1["Test event pattern, source, detail-type, account"]
    B -->|"Yes"| C{"Target delivery succeeded?"}
    C -->|"No"| C1["Check IAM role, bus policy, target KMS, DLQ"]
    C -->|"Yes"| D{"Consumer actually processed it?"}
    D -->|"No"| D1["Check SQS queue age, Lambda errors, DB transactions"]
    D -->|"Yes"| E["Reconcile business eventId, orderVersion, and projection"]
~~~

### 21.1. Scenario A — Producer returns errors

- Read **`FailedEntryCount`/`Entries[].ErrorCode`** from the `PutEvents` response in application/safe logs.
- Check the app IAM role has `events:PutEvents` on the bus ARN.
- Check `EventBusName`/Region and valid JSON event payload.
- Check Service Quotas and throttling.
- Retry with idempotency; never republish endlessly.

### 21.2. Scenario B — Cross-account target `AccessDenied`

- Account A: rule target ARN, delivery role trust policy, and `events:PutEvents` permission.
- Account B: bus resource policy/organization conditions.
- If the role has IAM Allow but an SCP has explicit Deny, requests still fail.
- If the destination uses a customer-managed KMS key, verify KMS requirements.
- Check CloudWatch `FailedInvocations`, retries, and DLQ—do not stop at checking `State=ENABLED`.

### 21.3. Scenario C — Replay produces no business records

- Verify the right archive/source bus and retention.
- Did you wait roughly 10 minutes for archive ingestion lag?
- Does the UTC time range match event timestamps?
- Did the replay select the right **`FilterArns`**, or does a rule not match replayed events?
- Did the consumer intentionally skip `replay-name` events or hit a stale-version guard?
- Did target delivery succeed while the DB transaction failed?

### 21.4. Scenario D — Custom subscriber cannot replay from 45 days ago

- Is bus retention large enough and does **`RetentionWindowStartTime`** cover that time?
- Is the subscriber using **`POINT_IN_TIME`** instead of `LATEST`?
- Are `PointType` (`TIMESTAMP`/`HORIZON`) and `StartingPoint` valid?
- For open-ended replay, does it satisfy the minimum lookback distance from the current time?
- Are the shared bus and subscriber in the **same Region/partition**?
- Are target permissions, on-failure destination, and subscriber state valid?

**You cannot replay events outside the retention window** simply by picking an older timestamp. You need backups or another historical source if the data has expired.

## 22. Real-world scenarios

### Case A — Billing deployment broken for 40 minutes

**Context:** Orders kept emitting `OrderCreated`, while the Billing consumer ran buggy code from 09:00 to 09:40; a Classic archive exists.

**Solution:**

1. Confirm events exist in the archive within retention.
2. Fix the Billing consumer and enable idempotency by **`eventId`/`orderId`**.
3. Create/verify a rule dedicated to Billing rebuild without re-triggering payment charges.
4. Replay 09:00–09:40 UTC using `FilterArns` for that exact rule.
5. Watch SQS backlog and DB concurrency.
6. Reconcile order/invoice counts, `eventId` dedup counts, and DLQ.
7. Document postmortem, add alarms, and test replays.

**Mistake:** replaying All rules and accidentally sending order-confirmation emails a second time or double-charging cards.

### Case B — Analytics building a new projection

**Context:** Analytics wants to compute customer lifetime value from historical `OrderPaid` events.

**Solution:** If a Classic archive holds sufficient data, add a rule target for the new projection and replay **only to that rule**. If a new Custom Event Bus retains the history, create a **subscriber with `POINT_IN_TIME` starting position** and monitor the replay-to-live transition.

**Mistake:** treating event history as a complete database state while ignoring `OrderRefunded`/`OrderCancelled` or older `schemaVersion` formats.

### Case C — Multiple AWS Organization accounts

**Context:** Separate Orders, Inventory, Billing, and Support accounts; each team wants to manage its own subscribers.

**Choice:** **New Custom Event Bus + AWS RAM `SubscribeOnly`**, configured retention, KMS, and owner auditing. If Classic buses/rules already exist, plan a gradual migration rather than switching everything overnight.

**Mistake:** using one `events:*` IAM role and sharing across the entire organization with no publisher/consumer boundaries.

### Case D — A → B → C does not work

**Context:** A Classic rule forwards A to B, and a rule in B targets bus C, yet C receives nothing.

**Cause:** Classic bus-to-bus **does not automatically chain forwarded events as hoped**. Split into independent A → B and A → C routes, or use a central bus/subscribers on the new Custom bus.

### Case E — Offboarding a consumer account

**Context:** The Analytics account no longer needs access to a Custom Event Bus shared via RAM.

**Procedure:** Remove/update share permissions, list existing subscribers, call **`RevokeResource`** when needed to cut off delivery completely, then confirm `EventDeliveryAttempts`/`EventsDelivered` drop to zero and audit permission removal.

**Mistake:** removing only the RAM share and assuming all pre-existing subscribers stop immediately.

## 23. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "Every EventBridge bus retains events by default." | Classic requires an Archive; the new Custom bus has built-in retention. |
| "Classic Archive can replay to any bus." | Classic replays back to **the same source bus**. |
| "`StartReplay` works on the new Custom bus." | Custom bus replays via **subscriber starting position**. |
| "Classic Replay preserves exact ordering for all events." | Not guaranteed; processes in one-minute time buckets and may be out of order. |
| "Replay invokes only one consumer." | Without `FilterArns`, it hits all matching rules. |
| "Replay deletes events from the archive." | No; archive retention still governs lifetime. |
| "Replay resources expiring after 90 days means the archive only keeps 90 days." | Replay record lifecycle is separate from archive retention. |
| "`EventCount = 0` right after creating an Archive means it isn't capturing." | `DescribeArchive` counters can take up to 24 hours to reconcile. |
| "Transport `eventId` alone always prevents duplicates." | Business `eventId` and transaction-safe idempotency protect side effects. |
| "Having a DLQ means you don't need an archive." | DLQs hold failed deliveries; archives retain broader event history. |
| "Granting `events:PutEvents` on the source role is enough for Classic cross-account." | The receiver bus policy must allow it too, plus target roles and downstream policies. |
| "Just forward A to B and have B forward to C." | Classic does not support chaining forwarded bus events that way. |
| "WAF or MFA is required for cross-account event bus delivery." | This uses IAM/event policies; WAF/MFA belong to other architectural layers when used. |
| "Deleting a Custom bus RAM share stops all subscribers instantly." | Existing subscribers may require explicit revocation. |
| "Custom Event Bus has strict global FIFO." | FIFO applies per event group/subscriber when supported, not globally across the system. |
| "`EventsDelivered` = invoices committed." | Delivery to a target is separate from the business transaction. |
| "Increasing retries is always better." | Can amplify duplicates, cost, and downstream overload. |
| "Indefinite Archive retention adds no extra cost." | Storage retention incurs cost and data exposure risk. |
| "Cross-account always implies cross-Region works." | Depends on bus model, Regional support, and ARNs/quotas. |

## 24. Practical exercises with solutions

### Exercise 1 — Choosing a history retention mechanism

**Prompt:** A company uses the default EventBridge bus and wants to retain `OrderCreated` for 30 days to rebuild reports.

**Solution:** This is the **Classic default bus**. Create an **Archive** attached to the source bus with an event pattern scoping `source`/`detail-type`/`account`, `RetentionDays` per requirement, IAM/KMS, and monitor `EventCount`/`SizeBytes`. Do not attempt to set `StorageConfiguration.RetentionPeriodInDays` as on the new Custom Event Bus.

### Exercise 2 — Choosing a safe replay

**Prompt:** An archive holds `OrderPaid` events and the bus has three rules: `charge-credit-card`, `send-email`, and `analytics-update`. Only analytics needs recomputing.

**Solution:** With **Classic Replay**, restrict **`Destination.FilterArns`** to the analytics rule—never replay all rules. First verify the analytics consumer is idempotent, event versions are supported, and the replay time window and business checkpoints are ready.

### Exercise 3 — Events not yet visible in archive

**Prompt:** A producer just emitted 500 events, and `DescribeArchive.EventCount` is still 0 after 30 seconds.

**Solution:** Do not assume the archive is broken. AWS has archive ingestion delay and an **`EventCount`/`SizeBytes` reconciliation period of up to 24 hours**. Verify event patterns, source bus, and archive `State`, and wait appropriately before replaying.

### Exercise 4 — Event ordering

**Prompt:** During a Classic Replay, a consumer receives `OrderCancelled` v7 before `OrderPaid` v5.

**Solution:** Do not rely on delivery order. Use **aggregate version**, conditional writes, stale-event skipping logic, or a controlled sequential rebuild. If per-entity ordering is needed in a new architecture, evaluate **Custom Event Bus event groups/FIFO** where supported, while keeping idempotency.

### Exercise 5 — Quick storage calculation

**Prompt:** 200,000 events/day, average 4 KiB/event, 15-day retention. Estimate raw data size.

**Solution:**

\[
200{,}000 \times 4\,\text{KiB}\times15
=12{,}000{,}000\,\text{KiB}
\approx11.44\,\text{GiB}
\]

This is not the actual AWS bill because overhead, metering, pricing tiers, Regions, and other usage also apply.

### Exercise 6 — Classic cross-account IAM

**Prompt:** Account A has a rule forwarding to Account B's event bus. CloudWatch shows `FailedInvocations`; Account A's role has `events:PutEvents`, yet Account B has not granted access.

**Solution:** Configure a **destination bus resource policy** in B allowing the source role/account, along with accurate IAM role/target/Region settings. If using Organization permissions, verify SCPs and condition keys. Never "fix" it by granting `AdministratorAccess` to the service.

### Exercise 7 — Cross-account chaining

**Prompt:** Rule A → B succeeds, while rule B → C fails to forward those events onward.

**Solution:** Classic bus-to-bus does not support chaining forwarded events like that. Configure independent A → B and A → C rules, or use a shared new Custom Event Bus where B and C each subscribe directly.

### Exercise 8 — Shared bus with three consumers

**Prompt:** Orders account owns the bus; Billing and Analytics want to write their own filters/targets without asking Orders to deploy rules for them.

**Solution:** Evaluate **new Custom Event Bus + AWS RAM `SubscribeOnly`**, allowing each consumer to manage subscribers in its own account within the same Region/partition. The bus owner tracks `EventsDelivered`/`EgressBytes` by `SubscriberAccount`.

### Exercise 9 — Consumer needs data from 60 days ago

**Prompt:** A Custom bus retains 30 days. Analytics creates a `POINT_IN_TIME` subscriber targeting 60 days ago.

**Solution:** You cannot read events outside the retention window. You need an existing retained source, backup, Classic archive, or historical store if saved elsewhere, and must increase retention before future events are emitted. Increasing retention today does not resurrect already-expired data.

### Exercise 10 — Replay to recover billing errors

**Prompt:** Billing consumer receives one `OrderPaid` event twice after replay. Two invoices are created.

**Solution:** Design a **transactional inbox/unique business `eventId`**, or transactional idempotency and API idempotency keys. For payment charges, use a provider idempotency key and ledger. Never rely solely on transport event IDs.

### Exercise 11 — Revoking subscriber access

**Prompt:** Consumer Account C must no longer read a shared Custom bus. The team deletes the AWS RAM share.

**Solution:** Inspect existing subscribers; removing a share does not guarantee stopping delivery to already-created subscribers. The bus owner must call **`RevokeResource`** per procedure and confirm metrics/logs show delivery stopped.

### Exercise 12 — Distinguishing DLQ and archive

**Prompt:** An SQS DLQ holds only 23 failed events, yet you need to rebuild all 50,000 events from that day.

**Solution:** A DLQ is not full history; use a **Classic archive** or **Custom bus retention** if retained properly. Identify the source of truth and time range, then perform an idempotent consumer replay.

## 25. Self-check questions

**Question 1.** Does Classic EventBridge retain events long-term on the default bus automatically?  
**Answer:** Not in the archive/replay model; you must create a separate **Archive**.

**Question 2.** What is the default retention in days on the new Custom Event Bus?  
**Answer:** **1 day** if unconfigured; configurable from 1–365 days per current documentation.

**Question 3.** Can Classic Replay send events to any arbitrary bus?  
**Answer:** No; the destination must be **the archive's source bus**.

**Question 4.** Which Classic Replay parameter limits target rules?  
**Answer:** **`Destination.FilterArns`**.

**Question 5.** Which field does EventBridge add to mark Classic replayed events?  
**Answer:** **`replay-name`**.

**Question 6.** Why do replayed events not loop continuously back into the same archive?  
**Answer:** An AWS-managed archive rule filters out events containing `replay-name`.

**Question 7.** Does Classic Replay guarantee original ordering?  
**Answer:** No; it replays by event time in one-minute buckets without guaranteeing exact event ordering.

**Question 8.** Why wait roughly 10 minutes when replaying recently arrived events?  
**Answer:** Classic archives have ingestion lag; waiting reduces the risk of missing recent events.

**Question 9.** Does a Classic archive's `EventCount` update instantaneously?  
**Answer:** No; reconciliation can take up to **24 hours**.

**Question 10.** Does replaying delete events from the archive?  
**Answer:** No. Events expire per retention or when the archive is deleted.

**Question 11.** How many concurrent active Classic replays are allowed per AWS limits?  
**Answer:** **10 per account/Region**.

**Question 12.** Is an IAM role in Account A alone enough for Classic cross-account bus-to-bus delivery?  
**Answer:** No; Account B's destination bus also needs a resource policy permitting it.

**Question 13.** Which field should a Classic receiving rule include to avoid accepting the wrong account?  
**Answer:** **`account`** alongside `source`/`detail-type` per the trust model.

**Question 14.** Should you use `account: ["*"]` to match all accounts?  
**Answer:** No; specify concrete account IDs or intentionally omit the field per policy.

**Question 15.** Is Classic A → B → C via consecutive forwarding rules supported by default?  
**Answer:** No; AWS restricts re-forwarding events that were already forwarded between buses.

**Question 16.** Do Classic direct cross-account service targets require the same Region?  
**Answer:** Yes in the documented model; verify the supported targets list and Region.

**Question 17.** How is a new Custom Event Bus shared with consumers?  
**Answer:** **AWS RAM** or an appropriate resource policy, typically granting the `SubscribeOnly` managed permission to consumers.

**Question 18.** Does removing an AWS RAM share always terminate existing subscribers?  
**Answer:** No. Check **`RevokeResource`/subscriber lifecycle** to stop delivery completely.

**Question 19.** Does Custom bus replay call `aws events start-replay`?  
**Answer:** No. Subscribers use **`POINT_IN_TIME`** and a starting point within retention.

**Question 20.** Where does a Custom bus mark a replayed delivery?  
**Answer:** **`SystemMetadata.aws:DeliveryType = REPLAY`**.

**Question 21.** Does Custom FIFO guarantee exactly-once business side effects?  
**Answer:** No; idempotency and transaction guards are still required.

**Question 22.** What is the difference between `AWS/Events` and `AWS/EventsV2`?  
**Answer:** Two metric namespaces for **Classic** and the **new Custom Event Bus**, respectively.

**Question 23.** Does `EventsDelivered` on a Custom subscriber mean the invoice committed successfully?  
**Answer:** No; target delivery acceptance differs from the business transaction.

**Question 24.** Why does a DLQ not replace an archive?  
**Answer:** A DLQ holds configured failed deliveries, whereas an archive/retention stores broader history for replay.

**Question 25.** When replaying payment events, what must you verify first?  
**Answer:** Idempotency keys/ledgers, target rule selection, and duplicate-charge risk.

**Question 26.** Which CLI command group is used for the new Custom Event Bus?  
**Answer:** **`aws eventsv2`** with a supported AWS CLI version.

## 26. Summary and deployment checklist

**Two design paths to remember:**

- **Classic default/Custom Event Bus – Classic:** routes via **rules/targets** and requires an **Archive** to keep history; **Replay** sends back to the same source bus and can scope rules via `FilterArns`. Cross-account routing uses a destination bus policy + sender delivery role, or direct cross-account service targets where supported.
- **New Custom Event Bus:** **built-in 1–365 day retention**, consumers create **subscribers** and read history via **`POINT_IN_TIME` starting positions**; cross-account sharing uses **AWS RAM** with separate owner/consumer permissions.

Pre-production checklist:

1. Clearly choose the **bus model**, API/CLI, and workflow type.
2. Design the **event contract**, `schemaVersion`, business `eventId`, and aggregate version.
3. Size **retention** to real needs and protect sensitive data.
4. Scope permissions across **publisher, forwarding role, bus policy/RAM share, subscriber delivery role, and target**.
5. Verify **Region/partition** and cross-account support.
6. Configure **DLQ/on-failure paths, bounded retries, alerts, and runbooks**.
7. Implement consumer **idempotency, transactional writes, and stale-event guards**.
8. For replays, use **small time windows and specific target rules/subscribers**, avoiding side effects.
9. Monitor the right **`AWS/Events`** or **`AWS/EventsV2`** metrics and business outcomes.
10. Control archive/retention, replay traffic, Lambda/SQS/DB, and full-pipeline costs.
11. Establish cross-account revoke/offboarding procedures and CloudTrail auditing.
12. Rehearse consumer outages, IAM `AccessDenied`, expired history, duplicates, and rollbacks.

Amazon EventBridge enables AWS applications to **emit events flexibly across services and accounts**, yet resilience never comes from storing history alone. **Clear event contracts, proper permissions, thorough observability, side-effect controls, and idempotent consumers** are what turn archive/replay into a reliable recovery strategy.

### Official AWS documentation

- [EventBridge default and Custom Event Bus – Classic](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-event-bus.html) — rules/targets and the classic model.
- [Archiving and replaying events](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-archive.html) — retention, `replay-name`, ingestion lag, and limits.
- [Creating archives](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-archive-event.html) — archive patterns and retention.
- [Creating replays](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-replay-archived-event.html) — time windows and rule selection.
- [Cross-account Classic event buses](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-cross-account.html) — IAM, resource policies, forwarding limitations.
- [Event bus permissions](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-event-bus-perms.html) — publish/rule/target permissions.
- [Cross-account service targets](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-service-cross-account.html) — cross-account target services.
- [New Custom Event Bus](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-custom-bus-what-is.html) — retention, subscribers, ordering, and dedup.
- [Custom Event Bus retention](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-custom-bus-create.html) — `StorageConfiguration` 1–365 days.
- [Replaying retained events to subscribers](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-custom-bus-replay.html) — `POINT_IN_TIME`, `HORIZON`, `REPLAY` metadata.
- [Sharing Custom Event Bus](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-custom-bus-sharing.html) — AWS RAM and revocation.
- [Custom Event Bus observability](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-custom-bus-observability.html) — `AWS/EventsV2` metrics.
- [Monitoring Classic EventBridge](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-monitoring.html) — `AWS/Events` metrics.
- [Amazon EventBridge pricing](https://aws.amazon.com/eventbridge/pricing/) — ingest, delivery, archive/replay, and retention costs.
