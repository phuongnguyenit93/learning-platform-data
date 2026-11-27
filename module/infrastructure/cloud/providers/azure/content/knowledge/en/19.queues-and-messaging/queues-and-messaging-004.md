# Designing Message Filters and Routing in Service Bus

> **Chapter:** Queues and Messaging  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Explore the Microsoft Azure ecosystem from subscriptions, resource groups, and Entra ID to virtual networks, compute services, storage, and data. Learn how to deploy, monitor, secure, and control costs for an application architecture on Azure.

## Lesson Objectives

After this lesson, you will be able to:

1. Distinguish **queue**, **topic**, **subscription**, **rule/filter**, and **SQL rule action** in Azure Service Bus.
2. Design a publish/subscribe model so an event reaches the right consumer groups without duplicating routing logic in the publisher.
3. Write and read **SQL filters** on application properties, distinguishing `AND`/`OR` conditions, data types, and missing properties.
4. Use **correlation filters** when the condition is exact equality matching across properties.
5. Understand the default **`$Default`** rule, how multiple rules combine, overlapping rules, and the risk of over-receiving.
6. Build and test three subscriptions—fulfillment, fraud review, and audit—using a message set with deterministic expected outcomes.
7. Govern **rule lifecycle**, secure communication, authorization, dead-lettering, idempotency, and auto-forwarding.
8. Monitor, diagnose, and optimize performance/costs before taking a Service Bus system into production.

## 1. Context: One Event, Multiple Consumers

An e-commerce system emits an event whenever a new order arrives:

~~~json
{
  "orderId": "ORD-1001",
  "customerId": "CUS-21",
  "totalAmount": 12500000,
  "items": [{"sku": "A1", "quantity": 1}]
}
~~~

Downstream systems have different requirements:

- **Fulfillment** only accepts orders created in the Vietnam market to prepare shipping.
- **Fraud detection** accepts high-value orders for review.
- **Audit** wants a trail of all order events.

If the publisher sends three separate requests to three services, the publisher must know all recipients, manage multiple endpoints, and handle partial-send retries. This is *point-to-point coupling*, making every new consumer require changes to the sending application.

Instead, the publisher sends **one message to an Azure Service Bus Topic**. Each consumer group owns **its own subscription** and defines its own filter rules:

~~~mermaid
flowchart LR
    P["Order API\nPublisher"]
    T["Topic\norders.events"]
    F["Subscription\nfulfillment-vn\nVN + OrderCreated"]
    R["Subscription\nfraud-review\nHigh-value orders"]
    A["Subscription\naudit-all\nAll events"]
    C1["Fulfillment Worker"]
    C2["Fraud Worker"]
    C3["Audit Worker"]
    P -->|"1 event + properties"| T
    T -->|"SQL/Correlation rule"| F --> C1
    T -->|"SQL rule"| R --> C2
    T -->|"$Default True"| A --> C3
~~~

Key point: **a topic is not a shared queue read competitively by three consumers**. With a topic, **each subscription is a separate storage/delivery stream**, independent in progress and dead-lettering. One message can be delivered to **multiple subscriptions** if it matches multiple filters.

## 2. Distinguishing Queue, Topic, Subscription, Rule, and Message

| Component | Role | Key Point to Remember |
| --- | --- | --- |
| **Queue** | Point-to-point: one queue, multiple competing consumers | Normally one message is processed by one receiver at a time via lock |
| **Topic** | Publish endpoint where producers send events for fan-out | Producers do not send directly to individual subscriptions |
| **Subscription** | Independent message stream attached to a topic | Has its own rules, TTL, lock, DLQ, and consumers |
| **Rule** | Filter condition and optional action | Determines which messages are selected into a subscription |
| **SQL filter** | Logical expression over supported message properties | Uses `AND`/`OR`, comparisons, `IN`, `LIKE` as needed |
| **Correlation filter** | Equality matching on specified properties | Efficient for simple matching; does not query JSON bodies |
| **Application properties** | Publisher-supplied metadata | E.g., `eventType`, `region`, `amount` |
| **System properties** | Standard message metadata | E.g., `MessageId`, `CorrelationId`, `Subject`, `SessionId` |
| **SQL action** | Mutates properties on matched messages | Does not replace consumer business logic |
| **DLQ** | Dead-letter subqueue for unprocessable messages | *Not matching a rule* does not send a message to the DLQ |

### 2.1. Topic/Subscription Differs from Event Hubs Consumer Groups

Azure Service Bus Topics target brokered business messaging: queue semantics, sessions, duplicate detection, dead-lettering, locks, transactions, and routing rules. Azure Event Hubs focuses on streaming with partitions, offsets, and consumer groups; do not treat the two concepts as interchangeable.

### 2.2. Tier-Dependent Features

Azure Service Bus offers **Basic, Standard, and Premium** tiers. **Topics and subscriptions are not available in Basic**; choose Standard or Premium as needed. Premium provides a dedicated capacity/resource model suited for isolation and predictable performance, with corresponding pricing and quotas.

Limits on rule counts, subscriptions, message size, throughput, networking, and feature availability must be checked against your **current tier, region, and API/SDK**. Never design around limits taken from another tier.

### 2.3. A Message Has Separate Body and Metadata

In Service Bus, the body can be JSON, Avro, Protobuf, or raw bytes; **subscription SQL filters do not arbitrarily inspect the JSON body**. To route by region or business type, the publisher must place routing values into typed **application properties**.

Example of the same message:

~~~text
Body:
  {"orderId":"ORD-1001","totalAmount":12500000}

Application properties:
  eventType = "OrderCreated"         (string)
  region    = "VN"                   (string)
  amount    = 12500000               (integer)
  priority  = 9                      (integer)
  schemaVer = 1                      (integer)

System properties:
  MessageId = "evt-ORD-1001-created-v1"
  CorrelationId = "checkout-9ab"
  Subject = "OrderCreated"
~~~

If `region` and `amount` are only inside the body, a rule `region = 'VN'` will not match because the broker does not parse JSON to synthesize application properties.

## 3. Routing Flow at the Broker

~~~mermaid
sequenceDiagram
    participant PUB as Publisher
    participant TOPIC as orders.events Topic
    participant RULES as Filter engine
    participant F as fulfillment-vn
    participant R as fraud-review
    participant A as audit-all
    participant CON as Consumer
    PUB->>TOPIC: Send(body + application properties)
    TOPIC->>RULES: Evaluate subscriptions/rules
    RULES->>F: Copy if fulfillment matches
    RULES->>R: Copy if fraud matches
    RULES->>A: Copy if audit matches
    CON->>F: Receive PeekLock
    F-->>CON: Message
    CON->>F: Complete after processing
~~~

There are three distinct phases:

1. **Publish time:** the broker decides whether to copy the message into each subscription based on existing rules.
2. **Receive time:** consumers read messages already selected into the subscription. Filters are not re-evaluated like a database query on receive.
3. **Settlement:** consumers `Complete`, `Abandon`, `DeadLetter`, or let the lock expire per workflow. This is separate from routing filters.

**Changing a rule today does not retroactively scan and re-filter messages already sitting in a subscription.** For routing policy changes, plan a clear cutover, monitor backlogs, and handle older messages explicitly.

### 3.1. Routing Is Conditional Fan-Out

A high-value Vietnam order can match fulfillment, fraud, and audit all at once. That is the **expected** outcome when three subscriptions serve three independent purposes.

### 3.2. Not Matching a Rule Is Not a Consumer Error

If a message matches no rules on `fulfillment-vn`, the broker does not enqueue it into that subscription. Zero messages at the receiver **does not necessarily mean Service Bus lost messages**; the filter may have excluded them by design.

Distinguish clearly:

- No match: excluded from the subscription.
- Matched but unreceived: backlog, permissions, connectivity, consumer, or session issue.
- Received but processing failed: retries, delivery count, and DLQ per policy.
- **Filter evaluation error**: handled separately; check `dead-letter on filter evaluation exceptions` settings and diagnostic logs where supported.

## 4. Designing Metadata Before Writing Filters

### 4.1. A Minimal Message Contract

Define the metadata schema upfront, for example:

| Property | Expected Type | Example | Used in Rules? |
| --- | --- | --- | --- |
| `eventType` | string | `OrderCreated` | Yes |
| `region` | string | `VN` | Yes |
| `amount` | integer | `12500000` | Yes |
| `priority` | integer | `9` | Yes |
| `schemaVer` | integer | `1` | Possibly |
| `tenantKey` | string | `tenant-02` | Possibly for tenant routing |
| `correlationId` (app-defined if any) | string | `flow-123` | Usually tracing; avoid confusing with system CorrelationId |
| `MessageId` (system) | string | `evt-...` | Dedup/tracing |
| `CorrelationId` (system) | string | `checkout-9ab` | Tracing / correlation filters when needed |

**The metadata contract is part of the event contract.** Producers and consumers must agree on property names, casing, data types, allowed values, and business meaning.

### 4.2. Data Types Change Filter Outcomes

Two seemingly similar messages can behave differently:

~~~text
Message A: amount = 12500000      (integer)
Message B: amount = "12500000"    (string)
~~~

The filter `amount >= 10000000` is written for **numeric comparison**. If a publisher sends a string, evaluation can fail to match as expected or raise a type error depending on expression semantics. Never rely on unverified implicit type coercion.

**Good practice:** normalize metadata in the publisher; write integration tests for every variant; never let publishers emit `amount` as a string sometimes and an integer other times.

### 4.3. Versioning Metadata

Changing `eventType="OrderCreated"` to `event_type="order.created"` can break existing rules. An upgrade plan:

1. Include an explicit schema version (`schemaVer`).
2. Update rules to accept both old and new events during transition.
3. Deploy producers emitting the new metadata.
4. Monitor message counts per subscription by version.
5. Clean up old rules once all consumers have upgraded and the transition window closes.

Never mutate metadata silently without migration, because routing mistakes usually **do not surface as HTTP 500 errors** in the producer.

## 5. SQL Filters: Conditional Expressions on Message Properties

**SQL filters** use Service Bus's SQL-like expression language—**not SQL queries executed against a database**; they do not inspect JSON bodies and do not support full SQL Server T-SQL capabilities.

Examples below assume the publisher sends application properties matching Section 4.

| Goal | Sample SQL Filter | Meaning |
| --- | --- | --- |
| All new orders | `eventType = 'OrderCreated'` | Selects the right event type |
| New orders in Vietnam | `eventType = 'OrderCreated' AND region = 'VN'` | Both conditions must hold |
| High-value orders | `eventType = 'OrderCreated' AND amount >= 10000000` | Numeric comparison |
| Select two markets | `region IN ('VN', 'TH')` | Region in set |
| High priority or special | `priority >= 8 OR eventType = 'ManualReviewRequested'` | Either condition |
| Branch by version | `schemaVer = 1 AND eventType = 'OrderCreated'` | Filters v1 contract |
| Match all | `1 = 1` or true rule/filter | Audit subscription |
| Exclude all | `1 = 0` or false filter | Pause intake; evaluate pending backlog |

### 5.1. AND, OR, and Parentheses

The following rule:

~~~sql
eventType = 'OrderCreated'
AND region = 'VN'
AND amount >= 10000000
~~~

selects **new, high-value orders in VN**.

Another rule:

~~~sql
eventType = 'OrderCreated'
AND (region = 'VN' OR region = 'TH')
~~~

selects new orders in VN or TH. Parentheses prevent operator-precedence bugs:

~~~sql
(eventType = 'OrderCreated' AND region = 'VN')
OR eventType = 'ManualReviewRequested'
~~~

**Do not equate** the expression above with:

~~~sql
eventType = 'OrderCreated'
AND (region = 'VN' OR eventType = 'ManualReviewRequested')
~~~

The two expressions match different sets of messages.

### 5.2. NULL, Missing Properties, and Mismatched Types

A message lacking `region` is not automatically equivalent to `region = ''` or `region = 'VN'`. Under SQL-like **three-valued logic**, comparisons involving missing/NULL properties evaluate to non-TRUE states, so the message fails to match the desired rule.

Example:

~~~text
message:
  eventType = "OrderCreated"
  region    = (missing)

filter:
  eventType = 'OrderCreated' AND region = 'VN'

expected:
  NOT selected into fulfillment-vn
~~~

Use **explicit required metadata validation at the publisher** rather than assuming missing values will be fixed by the broker. Expressions checking NULL or existence must be tested against Service Bus's supported syntax and semantics.

### 5.3. LIKE, IN, and Pitfalls to Avoid

SQL filter operators such as `LIKE` and `IN` can be used within supported bounds. However:

- Wildcard `LIKE` patterns easily over-match and raise filter evaluation cost.
- Overly long expressions hinder auditing and migration.
- Property names and values must be standardized, especially casing and data types.
- Never concatenate raw user input into SQL rule expressions without strict validation/escaping.
- Do not abuse SQL filters to query entire message bodies or run heavy business logic.

If routing only needs equality checks across a few properties, evaluate **correlation filters** instead of complex SQL filters.

## 6. Correlation Filters: Fast Exact-Field Matching

A **correlation filter** selects messages when specified system properties and/or application properties have **exact matching values** per supported model. When multiple conditions are configured inside one correlation rule, they combine with **AND** semantics.

Example logical condition:

~~~text
eventType == "OrderCreated"
region    == "VN"
~~~

This fits `fulfillment-vn` when only one event type and one fixed region are needed.

### 6.1. How Do SQL Filters and Correlation Filters Differ?

| Aspect | SQL Filter | Correlation Filter |
| --- | --- | --- |
| Expression style | SQL-like conditional expression | Equality across declared properties |
| Complex `AND`/`OR` | Expressible within one expression | Cannot express OR within a single correlation filter |
| Range comparisons | Fits, e.g. `amount >= 10000000` | Not designed for ranges |
| Multi-field equality | Yes | Yes, often cleaner |
| Testability | Must watch parser, types, NULLs, logic | Easy to read when fields and values are fixed |
| Performance | Incurs expression evaluation cost | Typically more optimized for equality matching |
| Best fit | Fraud thresholds, multi-condition branching | Event type + region + tenant |

### 6.2. Wanting OR with Multiple Correlation Filters?

Suppose fulfillment wants new orders in **VN or TH**:

- Rule `vn-orders`: `eventType=OrderCreated` AND `region=VN`.
- Rule `th-orders`: `eventType=OrderCreated` AND `region=TH`.

Rules within the **same subscription** combine with **OR** logic for message selection. This is why it is vital to distinguish **AND inside one correlation filter** from **OR across multiple rules**.

If you want a single expression, a SQL filter `eventType = 'OrderCreated' AND region IN ('VN','TH')` expresses the same business goal.

### 6.3. When Not to Use a Correlation Filter

- You need numeric checks like `amount >= 10000000`.
- You need nested OR groups inside **one expression**.
- You need string pattern matching.
- You need logic spanning complex data types.

In those cases, choose a SQL filter or simplify the metadata contract at the producer first.


## 7. The `$Default` Rule and How Multiple Rules Interact

### 7.1. What Is `$Default`?

When a subscription is created with default settings, Service Bus typically includes a rule named **`$Default`** using a **TRUE** filter—meaning the subscription accepts **every message** on the topic regardless of metadata.

Example of a broken configuration:

~~~text
Topic orders.events
  Subscription fulfillment-vn
    $Default                 TRUE
    vn-orders                eventType='OrderCreated' AND region='VN'
~~~

Intended: only receive `OrderCreated`/`VN`. Actual: `$Default` still lets all other messages enter the subscription.

**Mandatory takeaway:** after creating custom rules, **inspect the rule list** and remove `$Default` if the subscription should only receive messages matching custom filters. Delete `$Default` **only on the intended subscription**—do not accidentally delete it on `audit-all`.

### 7.2. Rules Combine with OR Logic at Selection Time

Suppose a subscription has two rules:

~~~text
Rule A: region = 'VN'
Rule B: eventType = 'OrderCreated'
~~~

A message `region='VN', eventType='OrderCancelled'` matches Rule A. A message `region='TH', eventType='OrderCreated'` matches Rule B.

Thus the subscription can receive **both**, whereas requiring "`OrderCreated` **and** `VN`" needs:

~~~sql
eventType = 'OrderCreated' AND region = 'VN'
~~~

Creating **two separate rules** is not equivalent to an `AND` condition.

### 7.3. Overlapping Rules and SQL Actions

Suppose:

~~~text
Rule A: eventType = 'OrderCreated'
Rule B: eventType = 'OrderCreated' AND region = 'VN'
~~~

An `OrderCreated`/`VN` message matches both. When **rule actions** or logic sensitive to delivery counts are present, overlapping rules make behavior harder to predict and must be verified against the exact semantics of your Service Bus/API version. Never design on the assumption that matching multiple rules always yields one copy with identical metadata.

Operational principles:

- Structure rules to be **mutually exclusive** when the business intent is distinct streams.
- If overlapping conditions are intentional, write tests verifying both message counts and post-action properties.
- Keep **consumers idempotent**, since message redelivery can still occur even without overlapping rules.
- Dedicate **each subscription to one clear business purpose** rather than multiplexing unrelated consumers onto one subscription.

### 7.4. How to Create Rules Safely

When switching from catch-all to selective filtering:

1. Confirm the exact namespace, topic, subscription, and environment.
2. Record existing rules and expected routing behavior.
3. Create the custom rule with a tested filter.
4. Verify the saved rule and expression.
5. Only then **delete `$Default`** if the subscription must stop accepting all messages.
6. Send a test batch and verify counts.
7. Monitor events no longer entering the subscription, especially during transition.

If migrating a busy production system, consider a **new subscription + cutover** for easy rollback rather than modifying critical live rules during peak traffic.

## 8. Designing Three Business Subscriptions

Deployment target:

~~~text
Namespace: sb-orders-lab-<unique>
Topic:     orders.events

Subscriptions:
  fulfillment-vn:
    rule only-vn-new:
      eventType = 'OrderCreated' AND region = 'VN'

  fraud-review:
    rule high-value-new:
      eventType = 'OrderCreated' AND amount >= 10000000

  audit-all:
    rule $Default:
      TRUE
~~~

### 8.1. Why Split Into Three Subscriptions?

- Fulfillment handles VN shipping with its own processing rate, retries, and dead-letter queue.
- Fraud review inspects high-value orders, which may take longer or involve human review.
- Audit receives every event for logging without blocking fulfillment.
- If Fraud pauses, backlog grows in `fraud-review` while `fulfillment-vn` keeps processing independently.
- Each consumer can scale, enforce permissions, and monitor metrics independently.

### 8.2. Deterministic Test Dataset

| Event | `eventType` | `region` | `amount` | Fulfillment VN | Fraud | Audit |
| --- | --- | --- | ---: | :---: | :---: | :---: |
| E1 | OrderCreated | VN | 12,500,000 | Yes | Yes | Yes |
| E2 | OrderCreated | TH | 2,000,000 | No | No | Yes |
| E3 | OrderCreated | VN | 900,000 | Yes | No | Yes |
| E4 | OrderCancelled | VN | 15,000,000 | No | No | Yes |
| E5 | OrderCreated | *(missing)* | 20,000,000 | No | Yes | Yes |
| E6 | PaymentCaptured | SG | 50,000,000 | No | No | Yes |

**Expected results for these 6 valid events:**

~~~text
fulfillment-vn = 2 messages  (E1, E3)
fraud-review   = 2 messages  (E1, E5)
audit-all      = 6 messages  (E1, E2, E3, E4, E5, E6)
~~~

E1 appearing in **all three subscriptions** is correct. E5 lacks `region` yet still matches the fraud rule because the fraud rule only checks `eventType` and `amount`.

### 8.3. Negative Test Cases

Do not only send "happy-path" events. Also test:

| Invalid or Abnormal Input | Risk |
| --- | --- |
| `amount="12500000"` as a string | SQL numeric comparison may fail to match or trigger an evaluation error |
| Missing `eventType` | Subscriptions filtering by event type receive nothing |
| `eventType="ordercreated"` instead of `OrderCreated` | Misroutes when casing contract is violated |
| `region="V N"` or `region="Vietnam"` | Unnormalized metadata fails to match `VN` |
| Negative `amount` or out-of-range business value | Consumers receive nonsensical data without validation |
| Valid message body but missing metadata | Filters do not automatically inspect the body |
| Message reaches topic, but subscription is disabled or auto-forwarding | Receiver reads the wrong endpoint |

Tests should explicitly specify **expected matches, expected non-matches, and expected error handling**. If metadata is malformed, the producer should reject it before publishing rather than relying on broker evaluation errors.

## 9. Creating Resources and Rules via the Azure Portal

### 9.1. Prerequisites

- Authorized Azure subscription/namespace with sufficient permissions.
- Service Bus namespace in **Standard or Premium** tier for topics/subscriptions.
- Unique namespace name and compliant region for data/policy requirements.
- Approved billing, Azure RBAC, and authentication method.
- A topic `orders.events` or another compliant name.
- Account permissions to **manage rules** and **send/receive test messages** if practicing.

Do not create resources or alter rules in production without a change process, test plan, and rollback strategy. **Creating a Premium namespace/tier can incur significant costs**; consider Standard for labs if required features are supported.

### 9.2. Create the Topic

In the Azure portal:

1. Select the right subscription/resource group and open the **Service Bus namespace**.
2. Confirm the namespace tier supports topics.
3. Under **Topics**, create `orders.events`.
4. Configure TTL, duplicate detection, partitioning, or other properties according to requirements **and tier support**. Do not enable options just because they appear in the UI without understanding their impact.
5. Verify the topic is created, active, and publisher permissions are configured.

### 9.3. Create the Fulfillment Subscription

1. Inside topic `orders.events`, create subscription `fulfillment-vn`.
2. Review lock duration, max delivery count, TTL, and DLQ policy per team standards.
3. Open **Rules / Filters** on the subscription.
4. Create a rule named `only-vn-new` of type **SQL filter**:

~~~sql
eventType = 'OrderCreated' AND region = 'VN'
~~~

5. Verify the saved expression displays properly.
6. **Delete the `$Default` rule** if it exists and is set to TRUE.
7. Confirm only the intended rule remains.

Alternatively, you can create the subscription with the custom rule directly via a supported API/SDK; even then, inspect the resulting rule list rather than assuming `$Default` disappeared.

### 9.4. Create the Fraud Subscription

Create `fraud-review` with custom SQL rule `high-value-new`:

~~~sql
eventType = 'OrderCreated' AND amount >= 10000000
~~~

After creation, inspect and delete `$Default` so the subscription **only receives high-value `OrderCreated` events**.

### 9.5. Create the Audit Subscription

Create `audit-all` and **keep the `$Default` (True) rule** if you truly want to audit every event on the topic.

If you only want to audit specific event families, use a custom rule, update your expectation table, and define separate policies. Audit data may contain sensitive information; access control, retention, and logging must comply with data governance rules.

### 9.6. Pre-Publish Verification

| Subscription | Expected Rule Set | `$Default` |
| --- | --- | --- |
| `fulfillment-vn` | `only-vn-new` | **Absent** |
| `fraud-review` | `high-value-new` | **Absent** |
| `audit-all` | `$Default` | **Present, TRUE** |

Capture and document rule expressions and test environment details per internal procedures—never include secrets or connection strings in screenshots.

## 10. Managing Rules with Azure CLI and API/SDK

### 10.1. Inspect Subscriptions Before Making Changes

Read-only Azure CLI examples:

~~~bash
az login
az account show \
  --query "{name:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

# Select the assigned subscription.
az account set --subscription "<SUBSCRIPTION_ID>"

RG="rg-messaging-lab"
SBNS="sb-orders-lab-unique"
TOPIC="orders.events"

# List subscriptions and rules of one subscription.
az servicebus topic subscription list \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --topic-name "$TOPIC" \
  --output table

az servicebus topic subscription rule list \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --topic-name "$TOPIC" \
  --subscription-name fulfillment-vn \
  --output json
~~~

`list` commands only read configuration and do not consume messages. Rule management syntax and filter-type flags can vary across Azure CLI versions; run `az servicebus topic subscription rule --help` before running create/delete commands.

### 10.2. Create a Rule via CLI (Run Only in Authorized Labs)

Example command structure for a CLI supporting the SQL expression parameter:

~~~bash
az servicebus topic subscription rule create \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --topic-name "$TOPIC" \
  --subscription-name fulfillment-vn \
  --name only-vn-new \
  --filter-sql-expression "eventType = 'OrderCreated' AND region = 'VN'"
~~~

**This is a write operation.** Check help/schema for your installed Azure CLI version and default filter type before running, as syntax requirements may vary. If the command reports an unrecognized argument, **do not experiment blindly in production**; use the portal or an explicit SDK/ARM API deployment.

Verify after creation:

~~~bash
az servicebus topic subscription rule list \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --topic-name "$TOPIC" \
  --subscription-name fulfillment-vn \
  --output json
~~~

Delete `$Default` only after confirming the custom filter works, rollback is available, and you have approval:

~~~bash
az servicebus topic subscription rule delete \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --topic-name "$TOPIC" \
  --subscription-name fulfillment-vn \
  --name '$Default'
~~~

**Quoting warning:** in Bash, `'$Default'` is a literal string; `"$Default"` expands an environment variable and may delete the wrong target or nothing at all. PowerShell has its own quoting rules; use the proper literal syntax for your active shell.

Repeat similarly for the fraud subscription. **Do not delete `$Default` on `audit-all`.**

### 10.3. .NET Administration SDK Example for a SQL Rule

A rule management utility can use `Azure.Messaging.ServiceBus` and `Azure.Identity`:

~~~csharp
using Azure.Identity;
using Azure.Messaging.ServiceBus.Administration;

string fullyQualifiedNamespace = "sb-orders-lab-unique.servicebus.windows.net";
string topic = "orders.events";
string subscription = "fulfillment-vn";

var admin = new ServiceBusAdministrationClient(
    fullyQualifiedNamespace,
    new DefaultAzureCredential());

var filter = new SqlRuleFilter(
    "eventType = 'OrderCreated' AND region = 'VN'");

var rule = new CreateRuleOptions("only-vn-new", filter);

// Only create if the rule does not exist yet, in an authorized environment.
await admin.CreateRuleAsync(topic, subscription, rule);

// Inspect all rules before deleting $Default.
await foreach (RuleProperties item in admin.GetRulesAsync(topic, subscription))
{
    Console.WriteLine($"Rule: {item.Name}");
}

// After verifying configuration and authorization, delete the default rule.
// await admin.DeleteRuleAsync(topic, subscription, "$Default");
~~~

**Prerequisites:** the subscription already exists, the admin identity has appropriate entity/rule management permissions, SDK/API versions are compatible, and network rules permit access to the namespace. Creating a rule is not idempotent if the rule name already exists; handle conflicts and change management in real code.

### 10.4. .NET Correlation Rule Example

For exact equality routing on `eventType` + `region`:

~~~csharp
var correlation = new CorrelationRuleFilter();
correlation.ApplicationProperties["eventType"] = "OrderCreated";
correlation.ApplicationProperties["region"] = "VN";

var rule = new CreateRuleOptions("only-vn-correlation", correlation);

// THIS IS AN ALTERNATIVE TO THE SQL RULE—do not create both
// unless you have intentionally verified overlapping rules.
// await admin.CreateRuleAsync(topic, subscription, rule);
~~~

This replaces the Fulfillment SQL rule—do not add both side-by-side in production without testing. When creating correlation rules for system properties, use the SDK's dedicated fields such as `CorrelationId` and `Subject` per API support rather than guessing arbitrary property names.

### 10.5. Managing Configuration with IaC

For production, store names, filter expressions, subscription settings, and ownership in **Bicep/ARM/Terraform or an appropriate IaC tool**. Best practices:

- Peer-review every expression change.
- Maintain version and rollback history.
- Roll out cleanly across Dev → Staging → Prod.
- Use desired-state drift detection with alerts if live resources diverge.
- Never allow both ad-hoc portal edits and automated pipelines to mutate rules without unified governance.
- Monitor existing backlogs during rule changes; changing IaC does not retroactively move queued messages.

## 11. Sending Messages and Inspecting Results with the Python SDK

### 11.1. Prerequisites

- `pip install azure-servicebus azure-identity` inside a **dedicated lab environment**.
- Namespace already contains the topic, subscriptions, and accurate rules.
- Sending identity holds `Azure Service Bus Data Sender` or equivalent data-plane permissions.
- Receiving identity holds `Azure Service Bus Data Receiver` on each target subscription.
- Network and Service Bus endpoints allow connectivity; TLS/network settings comply with policy.
- Sample message bodies contain **mock data only**.

Do not run examples against a production namespace without approval, and never put PII or credentials into test messages.

### 11.2. Publisher: JSON Body and Typed Metadata

~~~python
import json
import os
from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient, ServiceBusMessage

namespace = os.environ["SERVICEBUS_NAMESPACE"]
topic = "orders.events"

test_events = [
    ("E1", "OrderCreated", "VN", 12500000),
    ("E2", "OrderCreated", "TH", 2000000),
    ("E3", "OrderCreated", "VN", 900000),
    ("E4", "OrderCancelled", "VN", 15000000),
    ("E5", "OrderCreated", None, 20000000),
    ("E6", "PaymentCaptured", "SG", 50000000),
]

credential = DefaultAzureCredential()

with ServiceBusClient(
    fully_qualified_namespace=namespace,
    credential=credential,
) as client:
    with client.get_topic_sender(topic_name=topic) as sender:
        for event_id, event_type, region, amount in test_events:
            properties = {
                "eventType": event_type,
                "amount": amount,  # integer, not a string
                "schemaVer": 1,
            }
            if region is not None:
                properties["region"] = region

            payload = {
                "eventId": event_id,
                "orderId": f"TEST-{event_id}",
                "amount": amount,
            }

            message = ServiceBusMessage(
                body=json.dumps(payload),
                message_id=f"lesson-004-{event_id}",
                correlation_id=f"lab-batch-{event_id}",
                subject=event_type,
                content_type="application/json",
                application_properties=properties,
            )
            sender.send_messages(message)
            print("Published:", event_id)
~~~

This example uses **Microsoft Entra ID** via `DefaultAzureCredential` without storing SAS connection strings in code. `SERVICEBUS_NAMESPACE` holds the **fully qualified namespace**, e.g., `sb-orders-lab-unique.servicebus.windows.net`.

**Duplicate detection note:** if duplicate detection is enabled on the namespace/topic and you resend the same `message_id` within the detection window, the broker may drop repeats as duplicates. To test repeatedly, use a **fresh lab batch identifier** in message IDs and record that batch, or reset in a controlled lab. Never disable duplicate detection in production just to run tests.

### 11.3. Subscription Receiver

~~~python
import os
from azure.identity import DefaultAzureCredential
from azure.servicebus import ServiceBusClient

namespace = os.environ["SERVICEBUS_NAMESPACE"]
topic = "orders.events"
subscription = "fulfillment-vn"

with ServiceBusClient(
    fully_qualified_namespace=namespace,
    credential=DefaultAzureCredential(),
) as client:
    with client.get_subscription_receiver(
        topic_name=topic,
        subscription_name=subscription,
        max_wait_time=5,
    ) as receiver:
        messages = receiver.receive_messages(
            max_message_count=20,
            max_wait_time=5,
        )

        for message in messages:
            print("MessageId:", message.message_id)
            print("Properties:", message.application_properties)
            print("Body:", str(message))
            # In the lab, complete after verifying contents.
            receiver.complete_message(message)
~~~

This is a **consuming receiver**: calling `complete_message` removes the message from the subscription after processing. If you only want to inspect **without consuming**, use **Service Bus Explorer Peek** in the portal or `peek_messages` in the SDK.

Never run a consuming receiver against a production subscription just to test filters. If `receive_messages` returns an empty list, it may be because another consumer already processed the messages, the filter did not match, the entity is wrong, nothing was sent yet, or permissions/networking failed—not necessarily a broken SDK.

### 11.4. Verifying All Three Subscriptions

Send the batch to a **clean test namespace/topic** with no other traffic. Then inspect using peek or lab receivers in order:

~~~text
fulfillment-vn: E1, E3
fraud-review:   E1, E5
audit-all:      E1, E2, E3, E4, E5, E6
~~~

If results do not match:

1. Check `$Default` on each subscription.
2. Check saved SQL/correlation rules.
3. Check application property names and data types on received messages.
4. Check duplicate detection and message IDs.
5. Check TTL, auto-forwarding, DLQ, and whether another consumer is running.
6. Check publish timestamp against when rules took effect.

**Do not draw wrong conclusions about filters solely from queue counts** in environments with active consumers or pre-existing messages.


## 12. Advanced Routing Patterns

### 12.1. Responsibility-Based Fan-Out and Event Filtering

A topic `business.events` can serve:

~~~text
business.events
  ├── billing-sub         eventType IN ('InvoiceCreated', 'InvoicePaid')
  ├── shipping-sub        eventType = 'OrderReadyToShip'
  ├── notifications-sub   eventType IN ('OrderCreated', 'OrderDelivered')
  └── audit-sub           TRUE
~~~

**Pros:** the publisher only knows the event contract and topic. When notifications evolve, the publisher does not have to call new endpoints.

**Cons:** requires governing metadata schemas and route ownership; consumers cannot assume messages across all subscriptions share identical payloads.

### 12.2. Tenant-Based Routing

A multi-tenant system might use a `tenantKey` property:

~~~sql
eventType = 'UsageReported' AND tenantKey = 'tenant-02'
~~~

However, **a filter is not a security boundary replacing RBAC**. If a principal holds Receive permissions on a subscription containing another tenant's data, a misconfigured filter can leak data to an unauthorized consumer.

When strict isolation is required:

- Separate namespaces, topics, or subscriptions along appropriate trust boundaries.
- Assign least-privilege roles and scopes.
- Encrypt and minimize sensitive data inside messages.
- Gate rule changes through peer review and IaC.
- Add automated tests asserting **zero cross-tenant delivery**.

Do not assume "one subscription per tenant" scales optimally if tenant counts are huge; evaluate quotas, management overhead, ownership, and throughput.

### 12.3. Schema-Version Routing

Suppose a producer is migrating from `eventType='OrderCreated'` with `schemaVer=1` to version 2.

You can write a transition rule:

~~~sql
eventType = 'OrderCreated'
AND (schemaVer = 1 OR schemaVer = 2)
~~~

Or run two subscriptions/rules for consumers supporting different versions. Key rules:

1. Producer, filter, and consumer agree on version semantics.
2. Retire the old version only after old backlog data is drained.
3. Never alter the meaning of an existing property without bumping the version.
4. Run contract tests checking body and metadata together.

### 12.4. Priority Routing

You can define two subscriptions:

~~~text
priority-review:
  eventType = 'OrderCreated' AND priority >= 8

standard-fulfillment:
  eventType = 'OrderCreated' AND priority < 8
~~~

Here, the rules are **mutually exclusive** for messages with a valid numeric `priority`. If `priority` is missing or wrong-typed, a message could match neither.

**Note:** these two subscriptions are two independent streams—they do not magically create a single strict priority queue. Consumer scheduling, scaling, and downstream capacity must be managed separately. If all orders still need fulfillment, having `fulfillment-all` plus `priority-review` makes more sense.

### 12.5. Routing on System Properties

Correlation filters can match SDK-supported system properties such as `CorrelationId`, `Subject`, or `SessionId` within their respective scopes. SQL filters can also reference **system properties via Service Bus's dedicated syntax**, which differs from reading application properties.

Do not assume property names inside SQL expressions always match the property names exposed by the .NET/Python SDK. For instance, `Subject` in modern SDKs can correspond to the historical `Label` naming in certain API/filter contexts. Pick **one convention and test it live** rather than blindly copying SDK field names into SQL filters.

### 12.6. Auto-Forwarding from a Subscription to Another Queue/Topic

A subscription can be configured to **auto-forward** to a supported Service Bus entity, typically within the **same namespace**:

~~~mermaid
flowchart LR
    P["Producer"]
    T["Topic orders.events"]
    S["Subscription high-value"]
    Q["Queue manual-review"]
    W["Review worker"]
    P --> T -->|"filter amount >= threshold"| S
    S -->|"auto-forward"| Q --> W
~~~

Benefits:

- The broker automatically forwards matching messages into the queue needed by consumers.
- Separates subscription routing from a consolidated processing queue.
- The producer still remains unaware of the final queue.

Things to verify:

- Forwarding only applies to messages that **entered the subscription**; a broken filter cannot be "rescued" by auto-forwarding.
- The target entity must exist, support the feature, and have sufficient permissions and capacity.
- Respect limits and constraints on forwarding chains.
- Monitor delivery count, TTL, transfer dead-lettering, and error handling.
- Never create forwarding loops or unmanageable chains.
- Once forwarding is enabled, **messages may no longer stay in the source subscription for direct receivers to read**, depending on configuration.

Do not attach topic-style rules to a target queue expecting it to route like another topic; verify target entity type and consumer semantics.

### 12.7. SQL Rule Actions Mutate Metadata, Not Business Bodies

A SQL rule action can **modify supported message properties** on matched copies before placing them into a subscription—for example, tagging a route or category.

Conceptual example:

~~~text
Filter:
  eventType = 'OrderCreated' AND amount >= 10000000

Action (business intent):
  attach property routeCategory = "high-value-review"
~~~

This is a **behavioral description**, not deployable SQL action syntax verbatim. When implementing, use the exact **Service Bus SQL action** syntax and property limits in the corresponding API/SDK.

Avoid using actions to:

- Mutate JSON bodies or schemas without a consumer contract.
- Assume changes affect the original message on the topic or other subscriptions.
- Perform heavy logic like calling databases or APIs (broker filters/actions do not run arbitrary business code).
- Modify disallowed system properties or embed opaque logic that is hard to audit.

If multiple overlapping rules carry actions, test **message counts, resulting properties, and evaluation order** under exact service semantics. Usually, splitting subscriptions or enriching metadata at the producer is cleaner.

## 13. Dead-Lettering, TTL, Duplicate Detection, and Sessions

### 13.1. Filter Non-Match Is Not Dead-Lettering

| Case | Result on Subscription |
| --- | --- |
| Message matches no rules | Not selected into the subscription |
| Message matches, consumer succeeds | Can be `Complete`d and removed from subscription |
| Message matches, consumer repeatedly fails | Retried, then DLQ per max delivery/policy |
| Message TTL expires | Expired or dead-lettered depending on policy and feature support |
| Filter evaluation exception | Check `dead-letter-on-filter-evaluation-exceptions` and entity behavior |
| Auto-forwarding failure | Check transfer DLQ and target entity state |
| Duplicate detection on topic | Publisher retries may not produce another subscription copy if broker drops duplicate |

**Do not use the DLQ to count messages rejected by filters.** The DLQ only reflects conditions dead-lettered by the broker or receivers per supported mechanics.

### 13.2. Settlement Operations Under PeekLock

In `PeekLock` mode, a receiver can:

- `Complete`: confirm processing succeeded.
- `Abandon`: return the message for redelivery.
- `DeadLetter`: intentionally move a failing message to the DLQ.
- `Defer`: postpone the message for retrieval by sequence number / supported mechanism.
- Fail to finish before lock expiry: the message can be redelivered.

**Routing into the subscription** happens before any of these operations. A consumer cannot "fix a SQL filter" by calling `Complete` or `Abandon` on an already-delivered message.

### 13.3. Consumers Must Be Idempotent

Suppose message E1 enters `fraud-review`. A worker persists the check result successfully but crashes before `Complete`. After lock timeout, the message can be redelivered.

Ensure you:

1. Derive an idempotency key from the business event ID / `MessageId` per contract.
2. Persist processing state in a durable store.
3. Execute business side effects only once.
4. Log error codes and trace IDs for investigation.
5. Maintain a poison/DLQ runbook and dedicated handling permissions.

SQL filters do not guarantee exactly-once consumer processing.

### 13.4. Duplicate Detection vs. Idempotency

Service Bus supports **duplicate detection** by `MessageId` over a configurable window on supported tiers/entities. This reduces duplicate messages at the broker, yet:

- Does not prevent consumer redelivery after receive.
- Does not protect business logic if the same order is sent with two different message IDs.
- Carries window, quota, and throughput trade-offs.
- Interacts with partitioning and session settings at the entity level.

Keep **consumer-side idempotency** even when broker duplicate detection is enabled.

### 13.5. Sessions and Ordered Processing

If messages for an order must be processed sequentially:

~~~text
OrderCreated  (SessionId = ORD-1001)
OrderPaid     (SessionId = ORD-1001)
OrderShipped  (SessionId = ORD-1001)
~~~

Service Bus **sessions** help enforce ordering and exclusive processing **within one session** when both the entity and receiver are configured appropriately. However:

- There is no global ordering across an entire topic or across subscriptions.
- Each subscription progresses independently.
- Filters must be designed so they never drop a step required by the state machine.
- A session-enabled subscription requires a session-aware receiver.
- Do not put an ID in `CorrelationId` instead of `SessionId` and expect session locking to work.

### 13.6. TTL and Backlogs When Changing Filters

Messages already sitting in a subscription can persist until processed or until TTL expires per policy. Removing a rule does not purge pre-existing backlogs.

If you apply a new `region = 'VN'` filter at 10:00, non-VN messages routed into the subscription before 10:00 may **still appear in the backlog**. When testing, use **batch IDs and publish timestamps** to avoid confusion.

## 14. Security: Publishing, Receiving, and Managing Rules

### 14.1. Separating Three Permission Groups

| Group | Responsibility | Required Permission |
| --- | --- | --- |
| Publisher | Send messages to topic | Data-plane `Azure Service Bus Data Sender` or equivalent |
| Consumer | Receive/Complete/DeadLetter on subscription | `Azure Service Bus Data Receiver` or equivalent |
| Administrator / IaC | Create topics, subscriptions, rules; edit filters | Scoped management-plane / rule management permissions, or admin API role where applicable |

**Send permission does not grant rule-editing permission.** Receive permission on one subscription should not be broadened to read every other subscription unnecessarily.

### 14.2. Managed Identity Before SAS Connection Strings

On Azure VMs, App Service, Functions, AKS, or Container Apps, prefer managed identities with scoped RBAC whenever supported by the SDK. Benefits:

- No namespace keys stored in code.
- Permissions can be revoked or rotated per identity.
- Separates publisher, fraud worker, and audit worker privileges.

If SAS must be used, avoid sharing broad `RootManageSharedAccessKey` credentials with a single consumer. Store secrets in Key Vault with a rotation plan.

### 14.3. Network Security Is a Separate Layer

A client with a valid RBAC role can still fail to connect when:

- Namespace firewall blocks the egress IP.
- Private Endpoint / Private DNS is misconfigured.
- VNet routing or NSGs block ports/protocols.
- TLS hostname or certificate validation fails.

Check RBAC and network routing independently. Never weaken network security when the actual bug is in a filter expression.

### 14.4. Metadata Can Leak Sensitive Information

Never place payment card numbers, passwords, access tokens, or unnecessary PII in `application_properties` just for filtering. The broker needs enough metadata to route—**not full business data**.

If routing by order value, consider an `isHighValue` flag or `amountBucket` under a clear contract rather than exposing sensitive or overly granular data unnecessarily.

### 14.5. Filters Are Business Routing, Not Authorization

A subscription with `tenantKey='A'` does not guarantee absolute tenant isolation on its own. You must control:

- Who can edit rules?
- Who can publish messages with a spoofed `tenantKey`?
- Who holds Receive permissions on the subscription?
- Who could re-enable `$Default` or add a TRUE rule?
- Are filter changes protected by policies, reviews, and audit logs?

Publishers must be authenticated and metadata validated from trusted sources rather than accepting arbitrary `tenantKey` values supplied by public clients.


## 15. Observability: Tracking Routing and Subscription Health

### 15.1. Metrics and Signals to Watch

When deploying filters/rules, do not just verify that the publisher's `send` call succeeded. Observe **the topic and every individual subscription**.

| Signal | What to Verify |
| --- | --- |
| Incoming messages on topic | How many messages the publisher actually sent |
| Active messages per subscription | Messages selected into the subscription awaiting processing |
| Outgoing / completed messages | Whether consumers are processing and settling work |
| Dead-lettered messages | Whether processing, filter, or forwarding failures occurred |
| Scheduled / transfer messages (when used) | Whether messages are queued or auto-forwarding has issues |
| Server errors / user errors / throttling | Errors experienced by broker or clients |
| Consumer success/failure and latency | Whether valid messages are slow to process |
| SQL filter/rule inventory | Whether `$Default`, TRUE rules, or overlapping rules crept in |
| Application trace IDs | Whether requests trace end-to-end from producer to each consumer |
| Cost / throughput / capacity | Whether complex filters or high fan-out add excessive load |

Metric names, entity dimensions, and availability can vary across Azure Monitor resource types and tiers. Verify available metric definitions on your namespace/entities before building dashboards.

### 15.2. Distinguishing Broker Metrics from Application Logs

A topic receiving 1,000 incoming messages while three subscriptions total 2,200 selected messages is completely normal: **fan-out makes total subscription deliveries larger than publish counts**.

However, if `fulfillment-vn` suddenly doubles after adding a rule, check:

1. Was `$Default` accidentally left in place?
2. Was an overlapping rule/action added?
3. Are consumer retries causing logs to count invocations instead of unique `MessageId`s?
4. Is the publisher sending duplicate messages?
5. Is the dashboard measuring active, completed, incoming, or total traffic?

**Never assume "3 subscribers" always equals 3 copies for every event**; only subscriptions with matching rules receive copies.

### 15.3. Inspecting Rules via CLI

Read-only commands:

~~~bash
az servicebus topic subscription rule list \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --topic-name "$TOPIC" \
  --subscription-name fulfillment-vn \
  --output json

az servicebus topic subscription rule list \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --topic-name "$TOPIC" \
  --subscription-name fraud-review \
  --output json

az servicebus topic subscription rule list \
  --resource-group "$RG" \
  --namespace-name "$SBNS" \
  --topic-name "$TOPIC" \
  --subscription-name audit-all \
  --output json
~~~

In production workflows, automate drift checks comparing "live applied rules" against your IaC source of truth. These commands do not replace testing with real messages.

### 15.4. Azure Monitor and Application Insights

Publishers and consumers can emit structured telemetry with fields like:

~~~json
{
  "service": "fraud-worker",
  "topic": "orders.events",
  "subscription": "fraud-review",
  "eventId": "E1",
  "messageId": "lesson-004-E1",
  "correlationId": "lab-batch-E1",
  "eventType": "OrderCreated",
  "result": "processed",
  "durationMs": 120
}
~~~

Omit full message bodies if they contain sensitive data. With Application Insights, propagate trace context/correlation IDs across publish and receive. Never assume messaging transport automatically links full distributed traces when producer and consumer use different SDKs or runtimes.

### 15.5. Reading Counts in Context

To test filters accurately:

- Use a **dedicated lab topic/subscriptions**, with unrelated consumers stopped or coordinated.
- Record `MessageId`, batch ID, and publish timestamps.
- Peek each subscription before calling `Complete`.
- Compare **sets of IDs**, not just a single aggregate number.
- Record backlog counts before and after the test.
- Account for TTL, duplicate detection, auto-forwarding, and sessions.

If live production consumers are running, `ActiveMessageCount` can stay near 0 even when routing works because consumers drain messages right away.

## 16. Filter Performance, Complexity, and Cost

### 16.1. Complex SQL Filters Have Evaluation Cost

The more complex a rule and the more subscriptions/rules evaluated per message, the more work the broker must perform. This affects throughput and latency depending on tier and load.

**Optimization principles:**

- For simple equality checks, evaluate correlation filters.
- Use short, strongly typed, standardized metadata properties.
- Avoid hundreds of long `OR`/`LIKE` clauses when event taxonomy can be simplified.
- Never stuff an entire JSON body into one string property for filter pattern matching.
- Minimize overlapping rules and retire unowned rules.
- Load-test latency and throughput at **expected production scale**, not just a handful of messages.

### 16.2. Fan-Out Consumes Resources

If a publisher emits 1 million events/day and each event matches 2.5 subscriptions on average, the broker and consumers handle roughly 2.5 million **subscription message deliveries** in this illustrative model. Storage footprint and consumer activity scale accordingly.

Actual cost depends on tier, operation counts, compute/broker capacity, network, Log Analytics, and retention. Do not treat 2.5 million as an exact Service Bus billing operation count; consult current pricing rules for your tier and region.

### 16.3. Standard vs. Premium?

| Criterion | Standard | Premium |
| --- | --- | --- |
| Topics/subscriptions | Yes | Yes |
| Workload profile | Business workloads fitting Standard's shared model | Workloads needing resource isolation / predictable capacity |
| Compute model | Standard tier model | Dedicated capacity via Premium model |
| Baseline cost | Standard pricing structure | Can carry significant provisioned capacity cost |
| Throughput and predictability | Must load-test under realistic traffic | Requires sizing Messaging Units/resources and load testing |
| Networking, quotas, and dedicated capabilities | Dependent on SKU/features | Dependent on tier and configuration |

Do not pick Premium solely because "we use SQL filters": **Standard also supports topics, subscriptions, and rules**. Conversely, never assume Standard meets every throughput or latency SLO simply because filters work functionally.

### 16.4. Estimating from Business Workload

Suppose 50,000 events/hour, on average:

- 20% match fulfillment VN.
- 8% match fraud review.
- 100% match audit-all.

Simple model:

~~~text
Published events/hour = 50,000

fulfillment-vn        = 10,000 selected/hour
fraud-review          =  4,000 selected/hour
audit-all             = 50,000 selected/hour

Total across subscriptions ≈ 64,000 selected deliveries/hour
~~~

Sets can overlap; the sum **counts per subscription**, not unique event IDs. Validate estimates against actual event distributions, rules, duplicate detection, TTLs, and consumer behavior.

## 17. Runbook: Messages "Missing," Misrouted, or Duplicated

### 17.1. Quick Isolation Matrix

| Symptom | Possible Cause | Inspection Steps |
| --- | --- | --- |
| Publisher reports send success, consumer sees nothing | Rule mismatch | Property names/types/casing, rules, `$Default`, publish timestamp |
| Consumer gets all events despite VN-only goal | `$Default` still TRUE | List rules and delete default rule if approved |
| VN `OrderCreated` not received | Bad `AND` expression or missing property | Inspect actual `eventType`/`region` values |
| Fraud misses high-value orders | `amount` sent as string or wrong threshold | Verify numeric metadata and filter expression |
| Same message appears in multiple subscriptions | Fan-out working as designed | Verify against expected routing matrix |
| Consumer sees duplicate events | Retries, redelivery, duplicate publishes, overlapping rules/actions | Check IDs, delivery count, lock logs, filters |
| Messages appear in DLQ | Processing error, TTL, or rule/forwarding policy | Inspect DLQ reason, max delivery, transfer DLQ |
| Messages vanish from source subscription | Auto-forwarding enabled | Check target entity and transfer status |
| New rules do not affect old backlog | Filters evaluate at route/publish time | Check message enqueue timestamps |
| Cannot create topic | Namespace is Basic tier or missing permissions | Verify SKU, role, and quota |
| SQL filter fails to parse | Invalid syntax or escaping | Review expression and API/SDK diagnostics |
| Queue receiver works, topic subscription receiver fails | Wrong entity type, subscription, or permissions | Check namespace, topic/subscription names |
| Azure SDK Unauthorized | Missing or unpropagated data-plane RBAC/SAS | Verify identity/scope and network |
| Messages delayed or timing out | Throttling, slow consumers, scaling/backlog | Inspect Azure Monitor and consumer traces |

### 17.2. Layered Diagnostic Procedure

**Step 1 — Identify the message**

Capture `MessageId`, `CorrelationId`, `eventType`, `region`, `amount`, UTC timestamp, and topic name. Do not dump full payloads containing sensitive data.

**Step 2 — Verify the publisher**

Did it send to the right namespace/topic? Did it authenticate with Sender rights? Was the `MessageId` reused inside a duplicate detection window? Were body and application properties set separately?

**Step 3 — Read the target subscription's rules**

List rule names, types, SQL expressions, actions, and check whether `$Default` is present. Verify `AND`/`OR` logic and data types.

**Step 4 — Evaluate expected match manually**

Example:

~~~text
Message:
  eventType = OrderCreated
  region = TH
  amount = 15000000

fulfillment-vn:
  OrderCreated AND VN  → FALSE

fraud-review:
  OrderCreated AND amount>=10000000 → TRUE

audit-all:
  $Default TRUE → TRUE
~~~

Expected: Fraud + Audit only. If Fulfillment also received it, check `$Default`, overlapping rules, or older backlog.

**Step 5 — Inspect entity state**

Check active/dead-letter counts, TTL, auto-forwarding, and receiver activity. If the subscription is session-enabled, verify receivers are handling sessions properly.

**Step 6 — Inspect the consumer**

Check `PeekLock`/completion, delivery count, exceptions, idempotency, connection pools, and concurrency. If the message shows up in peek yet workers fail to receive it, the issue is almost certainly in the receiver, permissions, or processing rather than the filter.

**Step 7 — Fix the root cause and re-test**

Never delete an entire topic or purge a DLQ just to clear counters. Rule changes must go through IaC/review and be tested with an isolated batch. Verify both **matched** and **excluded** results.

### 17.3. Note on Testing Negative Cases

If you send E2 (TH) and confirm it does not appear in `fulfillment-vn`, that is expected. However, to prove E2 was not "lost" by the publisher, verify that the same `MessageId` arrived in `audit-all`. That is a major benefit of keeping a catch-all audit subscription in test environments.

## 18. Production Rule-Change Process

### 18.1. Before Changing Anything

- Document ticket, owner, objective, and impacted subscriptions.
- Snapshot existing rule configs, including `$Default`, SQL actions, and forwarding.
- Identify affected producers/consumers and event schema versions.
- Write a **routing truth table** covering both happy paths and negative cases.
- Assess existing backlogs, TTLs, DLQs, and active traffic.
- Assess cost/throughput impact if adding subscriptions or rules.
- Pick a change window, rollback plan, and monitoring signals.

### 18.2. Canarying with a New Subscription

A lower-risk alternative to editing live production rules in place:

1. Create `fulfillment-vn-v2` on the same topic with the new rule.
2. Send test events tagged with a dedicated batch ID.
3. Compare messages in v1 and v2 using **peek** or a test-only consumer.
4. Once the new rule passes, deploy the updated consumer or switch readers per plan.
5. Drain v1's backlog; do not delete v1 until cutover is complete.
6. Clean up the old entity per retention policy and change approval.

**Caution:** creating a v2 subscription on a live production topic immediately starts receiving **matching production messages from creation time onward**. Coordinate with data owners and never let a test consumer trigger production side effects.

### 18.3. When In-Place Rule Changes Are Necessary

- Create the new custom rule first and verify it works.
- Only then remove the old rule per runbook; note that during transition, more messages may match temporarily.
- If temporary overlap is unacceptable, use a new-subscription cutover or dedicated maintenance window.
- Never bundle unrelated changes into the same deployment.
- After applying, send both positive and negative test batches and verify traces + counts.
- Alert if an unexpected `$Default` rule or rule drift appears.

### 18.4. Rollback Must Account for Already-Routed Messages

Rolling back a filter expression neither deletes messages misrouted during the incident nor recreates messages that were excluded from a subscription. You may need to **replay** from an event store, audit subscription, or reliable event log.

Safe replay requires:

- Durable source data with valid read access.
- Fresh batch IDs compatible with duplicate detection policy.
- Idempotent consumers.
- Recording replay reason and owner.
- Preventing sensitive events from entering unauthorized subscriptions.

Do not assume `audit-all` permanently replaces a full event store: an audit subscription still has TTL, quotas, and consumers that may `Complete` messages.

## 19. Routing Design Practice Exercises

### 19.1. Part A: Define the Rules

Given the specification:

- Fulfillment processes only `OrderCreated` in `VN`.
- Fraud reviews newly created orders with `amount >= 10000000`.
- Audit receives every event.

**Task:** write the rule for each of the three subscriptions and decide whether to keep `$Default`.

**Solution:**

~~~text
fulfillment-vn:
  SQL: eventType = 'OrderCreated' AND region = 'VN'
  Do not keep $Default

fraud-review:
  SQL: eventType = 'OrderCreated' AND amount >= 10000000
  Do not keep $Default

audit-all:
  TRUE / $Default
  Keep default rule
~~~

### 19.2. Part B: Compute the Result Set

Given the events:

| ID | eventType | region | amount |
| --- | --- | --- | ---: |
| A | OrderCreated | VN | 10,000,000 |
| B | OrderCreated | VN | 9,999,999 |
| C | OrderCreated | TH | 10,000,000 |
| D | OrderCancelled | VN | 12,000,000 |
| E | OrderCreated | *(missing)* | 12,000,000 |

Calculate which messages belong to each subscription, then check:

- Fulfillment: **A, B**.
- Fraud: **A, C, E**.
- Audit: **A, B, C, D, E**.

### 19.3. Part C: Spotting an AND/OR Bug

A teammate creates two rules inside `fulfillment-vn`:

~~~text
Rule 1: eventType = 'OrderCreated'
Rule 2: region = 'VN'
~~~

**Question:** what happens to an event with `OrderCancelled`, `region='VN'`?

**Answer:** it will still be selected because Rule 2 matches. To require both conditions, combine them in **one SQL rule** using `AND` or in one correlation rule specifying both equality properties.

### 19.4. Part D: Spotting a `$Default` Bug

You inspect `fulfillment-vn` and find both the right custom rule and `$Default` = TRUE.

**Question:** what should you do?

**Answer:** verify the namespace and subscription, record existing rules, verify the custom rule, and **remove `$Default` from `fulfillment-vn`** if it should only receive new VN orders. Do not delete `audit-all`'s default rule.

### 19.5. Part E: Wrong Metadata Type

A publisher sends:

~~~json
{
  "application_properties": {
    "eventType": "OrderCreated",
    "region": "VN",
    "amount": "25000000"
  }
}
~~~

**Question:** can you be certain Fraud will receive this because 25,000,000 is greater than 10,000,000?

**Answer:** No. `amount` is a **string**, not an integer. Fix the contract/publisher, test filter behavior, and verify evaluation exception handling; never rely on implicit type casting.

### 19.6. Part F: Rule Change vs. Existing Backlog

At 09:00, `fulfillment-vn` still had a TRUE rule. At 09:15, the team deleted `$Default` and kept only the VN rule. At 09:20, a consumer reads the subscription and sees a TH event sent at 09:05.

**Question:** does that mean the new rule is broken?

**Answer:** not necessarily. The TH event was likely routed into the subscription before the rule changed. Check enqueue timestamps and older backlog; new filters do not retroactively filter pre-existing messages.

### 19.7. Part G: Cross-Tenant Leak

A subscription for tenant A has SQL filter `tenantKey='A'`, yet Receive permissions were granted to a principal belonging to tenant B.

**Question:** is tenant isolation secure?

**Answer:** no. Filters do not replace authorization; enforce scoped RBAC, identity/source validation, network isolation, and change reviews.

### 19.8. Part H: Designing a Repeatable Test Suite

A test plan should cover:

| Test Case | Input Data | Expected Outcome |
| --- | --- | --- |
| Happy path VN | OrderCreated/VN/12.5m | All 3 subscriptions |
| Happy path small non-VN | OrderCreated/TH/2m | Audit |
| Boundary threshold | OrderCreated/TH/10m | Fraud + Audit |
| Non-matching event type | OrderCancelled/VN/15m | Audit |
| Missing region | OrderCreated/missing/20m | Fraud + Audit |
| Wrong amount type | OrderCreated/VN/"20m" | Blocked at publisher or handled by malformed policy |
| Default rule regression | Any small TH event | Absent from Fulfillment |
| Consumer crash | OrderCreated/VN/12.5m | Processed idempotently on retry |
| Midstream rule change | Messages before/after cutover | Matches publish timestamp / active rules |
| Auto-forwarding | Rule-matching message | Target receives properly; source behaves per config |

## 20. Self-Check Questions

**Question 1.** How does a topic differ from a queue?

**Answer:** A topic supports publish/subscribe with multiple subscriptions independently receiving matching copies; a queue uses a competing-consumers model on one entity.

**Question 2.** Can you filter the JSON body directly with `amount > 10000000`?

**Answer:** Not with standard subscription SQL filters; place numeric `amount` in application properties or filter inside the consumer.

**Question 3.** Are two rules `region='VN'` and `eventType='OrderCreated'` equivalent to one rule using `AND`?

**Answer:** No. Subscription rules combine like `OR` conditions at message selection; use a single rule with `AND` when both must hold.

**Question 4.** Why might a subscription receive every message even when a custom filter selects only VN?

**Answer:** The `$Default` TRUE rule—or another catch-all rule—is likely still present.

**Question 5.** When is a correlation filter most appropriate?

**Answer:** When matching exact equality on one or a few properties like `eventType`/`region`/`tenantKey`, without needing range or pattern comparisons.

**Question 6.** Does a message that fails to match any rule automatically go to the DLQ?

**Answer:** No. Non-match simply means the broker does not select the message into that subscription; the DLQ reflects processing or dead-letter policy failures.

**Question 7.** Does changing a filter re-filter messages already sitting in a subscription?

**Answer:** No. Routing evaluates rules at the time a message is routed into subscriptions.

**Question 8.** Message E1 matches both Fulfillment and Fraud. Is that a duplicate bug?

**Answer:** No, if the two subscriptions serve independent purposes. One business event can fan out to multiple subscribers.

**Question 9.** Why is idempotency still needed when duplicate detection is enabled?

**Answer:** Broker duplicate detection does not stop consumer redeliveries or separate publishes with different IDs.

**Question 10.** Does Service Bus Basic support topics and subscriptions?

**Answer:** No; Standard or Premium is required for topic/subscription features.

**Question 11.** Do `SessionId` and `CorrelationId` serve the same function?

**Answer:** No. `SessionId` drives session-ordered locking/processing when enabled; `CorrelationId` links related messages/traces and can also be matched by correlation filters.

**Question 12.** Can a `tenantKey` filter replace Azure RBAC?

**Answer:** No. Filters only route based on publisher-supplied properties; send, receive, and admin permissions must still be enforced.

**Question 13.** Why might a receiver reading a source subscription see no messages when auto-forwarding is enabled?

**Answer:** Matching messages may be forwarded by the broker to the configured target; check the destination queue/topic and transfer status.

**Question 14.** If a new rule unintentionally excludes messages, does rolling back the filter recover them?

**Answer:** Not automatically. You need a reliable replay source, access permissions, fresh batch IDs, and idempotent consumers.

**Question 15.** Why shouldn't you rely solely on total message counts to verify routing?

**Answer:** Counts are skewed by fan-out, pre-existing backlogs, duplicate detection, other consumers, TTLs, and retries. Always verify exact `MessageId` sets and publish timestamps.

## Key Takeaways

- **Topic → Subscription → Rule** is the core chain for routing messages by event metadata in Azure Service Bus.
- **SQL filters** fit logical expressions, numeric comparisons, and `IN`/`LIKE`; **correlation filters** fit simple equality matching.
- **One rule with `AND`** differs from **multiple `OR` rules** on the same subscription. Always inspect and manage the **`$Default`** rule intentionally.
- **Application properties** must have standardized names, types, and values; SQL filters do not parse JSON bodies.
- **Filter non-match is not DLQ**, and rule changes **do not re-filter existing backlogs**.
- One event can legitimately reach multiple subscriptions, yet consumers still require **idempotency, retries, DLQs, and monitoring**.
- **Filters do not replace RBAC/authentication.** Manage lifecycles with IaC, test full routing matrices, and prepare rollback/replay plans.
- The best designs deliver to **the right receivers, at the right time, with the right data types**, while upholding security, performance, cost, and operability.
