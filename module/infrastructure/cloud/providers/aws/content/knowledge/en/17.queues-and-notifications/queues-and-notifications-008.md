# SNS Topics, Subscriptions, and Delivery Protocols

> **Chapter:** Queues and Notifications  
> **Module:** CLOUD_PROVIDERS_AWS — explore AWS across Regions/AZs, IAM, VPC, compute, storage, databases, integration, and serverless; practice choosing services, deploying securely, monitoring, recovering, and controlling costs.

## Learning Objectives

An e-commerce system needs to send `order.created` events to inventory, shipping, customer notifications, auditing, and analytics. If the order API synchronously calls every system, a single slow dependency increases latency or triggers cascading failures. **Amazon Simple Notification Service (Amazon SNS)** provides a **publish/subscribe (pub/sub)** model: applications publish messages to a **topic**, and **subscriptions** define the destination endpoints and transport protocols.

Three central concepts:

- **Topic:** shared publishing point with an ARN, Standard/FIFO type, resource policy, encryption, and message size limits.
- **Subscription:** link between a topic and a specific endpoint, with a protocol, filter policy, confirmation state, raw delivery setting, retry behavior, and optional DLQ.
- **Delivery protocol:** how SNS pushes messages to SQS, Lambda, HTTP(S), email, SMS, mobile push, or Amazon Data Firehose.

After this lesson, you will be able to:

1. Describe the producer → SNS topic → subscription → consumer flow and why fan-out is needed.
2. Distinguish SNS **Standard** and **FIFO**, including ordering/deduplication guarantees and supported targets.
3. Choose destination protocols based on backlog, latency, user notification, and analytics requirements.
4. Configure or inspect subscription confirmation, filter policies, and raw message delivery.
5. Distinguish **SNS delivery failures** from **consumer processing failures** and pick the right DLQ.
6. Design IAM, topic policies, SQS queue policies, KMS, and HTTPS signature verification.
7. Inspect configurations using the AWS CLI; understand IaC examples and sandbox lab workflows.
8. Explain monitoring, event schemas, idempotency, replay, costs, and updated limits.

## 1. From Synchronous Integration to Publish/Subscribe

### 1.1. The fan-out problem

An Order API creates an order, and several independent workflows must react:

~~~mermaid
flowchart LR
    API[Order API] -->|Publish: order.created| SNS[(SNS Standard Topic)]
    SNS -->|subscription inventory| Q1[SQS queue inventory]
    SNS -->|subscription shipping| Q2[SQS queue shipping]
    SNS -->|subscription notify| L[Lambda notifications]
    SNS -->|subscription analytics| FH[Amazon Data Firehose]
    Q1 --> INV[Inventory worker]
    Q2 --> SHIP[Shipping worker]
    L --> EMAIL[Email/SMS service]
    FH --> LAKE[(S3 data lake)]
~~~

The **publisher** only needs to know the topic and event contract. **Subscribers** can add new branches without forcing the publisher to modify API call sites. Each destination has independent delivery status, filtering, and retries.

Even when `Publish` returns a `MessageId`, you **do not yet know whether every consumer succeeded**. Distinguish these stages:

~~~text
Producer calls sns:Publish successfully
   -> SNS accepts the message
      -> SNS delivers to each endpoint
         -> Endpoint receives/persists the message
            -> Consumer executes business logic
               -> Persists data and acks/commits
~~~

A failure at the final step does not retroactively fail the initial publish call.

### 1.2. SNS and SQS do not replace each other

| Aspect | SNS | SQS |
|---|---|---|
| Connection model | Pub/sub: one message can reach multiple endpoints | Queue: consumers actively poll for messages |
| Fan-out | Yes, across multiple subscriptions | Typically paired as multiple SQS queues behind SNS/EventBridge |
| Worker backlog storage | Not the primary purpose of a Standard topic | Provides queue retention and visibility timeouts |
| Primary retries | SNS retries **delivery to the subscription endpoint** | Consumer retries via visibility timeout/redrive |
| Delivery targets | SQS, Lambda, HTTPS, email, SMS, push, Firehose, etc. | Workers/SDK/Lambda ESM poll the queue |
| Failure capture | SNS subscription DLQ when delivery fails | SQS source-queue DLQ when processing fails repeatedly |
| Ordering | Standard: best effort; FIFO: per conditions | Standard: best effort; FIFO: per `MessageGroupId` |

A common pattern is **SNS topic → one SQS queue per team/service**. If inventory goes down for 30 minutes, inventory's queue retains its work within the retention window while shipping keeps running smoothly.

**When not to add SNS:** if there is only a single consumer and no fan-out or notification branches are needed, using SQS directly can be simpler and cheaper.

### 1.3. SNS vs. EventBridge

**SNS** excels at pub/sub fan-out across diverse protocols, attribute/body filtering, and low-latency delivery. **Amazon EventBridge** fits event-bus routing by event patterns, SaaS integrations, schema-driven architectures, and broader event integration workflows. Both services differ in retries, quotas, pricing, and security controls. Do not pick solely by the word “event”; start from your subscribers' **delivery contracts**.

## 2. Standard Topics vs. FIFO Topics

### 2.1. Standard

**SNS Standard** fits most applications wanting multi-protocol fan-out:

- High availability and massive throughput;
- **At-least-once** delivery where supported by the service, so duplicates can occur;
- **Best-effort** delivery ordering—never rely on it for strict transactional ordering;
- Supports SQS, Lambda, HTTP(S), email, SMS, mobile push, and Firehose subject to protocol limits.

Example notifications: profile updates, order events, operational alarms, and analytics. When out-of-order events are dangerous, consumers need versions/sequence numbers so stale data never overwrites newer state.

### 2.2. FIFO

**SNS FIFO topics** provide ordering and deduplication per **message group**:

- Require `MessageGroupId` for events belonging to the same ordered stream.
- Use `MessageDeduplicationId` or content-based deduplication per configuration.
- **SNS FIFO → SQS FIFO** fits when strict per-group ordering is required.
- SNS FIFO can also deliver to **SQS Standard**, though Standard queues do not maintain strict ordering or deduplication at consumption.
- SNS FIFO **cannot subscribe Lambda, email, HTTP(S), SMS, or mobile push directly**.
- If Lambda must process FIFO events: **SNS FIFO → SQS FIFO → Lambda event source mapping**.
- Filtering, expiration, retries, and external duplicate sources still require analysis; **never assume exactly-once business side effects**.

~~~mermaid
flowchart LR
    P[Publisher] -->|MessageGroupId=order-123| T[(SNS FIFO)]
    T --> Q1[SQS FIFO accounting]
    T --> Q2[SQS FIFO shipping]
    T --> Q3[SQS Standard analytics]
    Q1 --> F[Lambda via SQS ESM]
    Q2 --> W[Worker]
~~~

Within group `order-123`, publishing created → paid → shipped in the right order is the publisher's responsibility. SNS does not reorder events emitted out of sequence by the source.

### 2.3. Selection table

| Requirement | Choice |
|---|---|
| Fan-out across multiple protocols including HTTPS/email | Standard |
| Per-order sequencing into queues | FIFO topic + FIFO queue |
| Single simple worker queue, no fan-out | SQS directly |
| Need both FIFO and webhooks/emails | Split streams: FIFO → SQS for ordered workflows; Standard topic for notifications |
| Immediate processing without durable endpoint backlog | Standard → Lambda if appropriate |
| Streaming reporting / archiving | Standard → Data Firehose |

### 2.4. FIFO publish example

~~~bash
# ILLUSTRATIVE ONLY, do not run on a production topic
aws sns publish \
  --topic-arn arn:aws:sns:ap-southeast-1:111122223333:order-events.fifo \
  --message '{"eventId":"evt-001","orderId":"order-123","eventType":"order.created"}' \
  --message-group-id "order-123" \
  --message-deduplication-id "evt-001" \
  --region ap-southeast-1
~~~

Use a **stable business event ID** when retrying the same event, rather than generating a new ID per retry. SNS/SQS deduplication windows are finite, so consumers still require idempotency if events are replayed outside that window.

## 3. Topics, Subscription ARNs, and Endpoints

### 3.1. Identifiers

~~~text
TopicArn:
arn:aws:sns:ap-southeast-1:111122223333:orders-events

SubscriptionArn:
arn:aws:sns:ap-southeast-1:111122223333:orders-events:550e8400-e29b-41d4-a716-446655440000

Endpoint (SQS queue):
arn:aws:sqs:ap-southeast-1:111122223333:inventory-events
~~~

**`TopicArn`** is used with `sns:Publish` and topic policies; **`SubscriptionArn`** is used with `Get/SetSubscriptionAttributes` and `Unsubscribe`; **`Endpoint`** ARN/URL identifies the queue, Lambda, Firehose, HTTP URL, email address, or phone number per protocol.

### 3.2. Subscription attributes

| Attribute | Purpose | Constraints |
|---|---|---|
| `Protocol` | Delivery mechanism | Supported protocols depend on topic type |
| `Endpoint` | Target address | Must be valid and authorized to receive |
| `PendingConfirmation` | Awaiting confirmation | Does not receive regular notifications until confirmed |
| `FilterPolicy` | Selects a subset of messages | Not a security mechanism |
| `FilterPolicyScope` | `MessageAttributes` or `MessageBody` | Defaults to `MessageAttributes` |
| `RawMessageDelivery` | Sends raw payload to SQS/HTTP(S)/Firehose where supported | Affects parsers and message attribute limits |
| `DeliveryPolicy` | HTTP(S) retries/backoff | Does not control SQS consumer retries |
| `RedrivePolicy` | SNS delivery-failure DLQ | Queue must be in same account/Region per docs |
| `SubscriptionRoleArn` | Role used to deliver to Firehose | Needs proper IAM permissions |

### 3.3. Subscription confirmation

Email and HTTP(S) endpoints typically require **confirmation by the endpoint owner**:

~~~mermaid
sequenceDiagram
    participant O as Topic owner
    participant SNS as Amazon SNS
    participant E as Email / HTTPS endpoint
    O->>SNS: Subscribe
    SNS->>E: SubscriptionConfirmation
    E->>E: Verify sender/signature + TopicArn
    E->>SNS: ConfirmSubscription / trusted link
    SNS-->>O: Confirmed
    O->>SNS: Publish
    SNS->>E: Notification
~~~

For **email**, a recipient with mailbox access must click the confirmation link. For **HTTP(S)**, SNS posts a `SubscriptionConfirmation` payload containing `Token` and `SubscribeURL`. **Never automatically fetch arbitrary externally supplied URLs**; verify the cryptographic signature, `TopicArn`, certificate, and genuine AWS SNS domain before confirming to prevent SSRF and subscription hijacking.

If a subscription remains in `PendingConfirmation`, resolve confirmation before troubleshooting message filtering or consumers.

### 3.4. One topic with multiple subscribers

~~~text
SNS Standard topic: orders-events
├── subscription protocol=sqs, endpoint=inventory-events
├── subscription protocol=sqs, endpoint=billing-events
├── subscription protocol=lambda, endpoint=notification-worker
├── subscription protocol=https, endpoint=partner.example.com
└── subscription protocol=firehose, endpoint=orders-data-stream
~~~

Each subscription can have its own **filter policy**, DLQ, and settings. **Never let an unauthorized principal subscribe to a sensitive topic** assuming a filter policy they can edit will keep sensitive events hidden.

## 4. Delivery Protocols

### 4.1. Overview

| Protocol | Endpoint | When to use | Specific responsibilities |
|---|---|---|---|
| `sqs` | SQS queue ARN | Work queues, backlogs, consumer decoupling | Queue resource policy, visibility, redrive |
| `lambda` | Lambda function ARN | Serverless handling, lightweight side effects | Lambda permissions, async errors/destinations |
| `http` / `https` | URL | Webhooks, partner integrations | Confirmation, signatures, retries/backoff |
| `email` | Email address | Simple notifications / on-call alerts | Mailbox confirmation; no read guarantee |
| `email-json` | Email address | Receives SNS JSON via email | Not a durable queue |
| `sms` | Phone number | Alerts / user SMS | Consent, country rules, sender registration, fees |
| `application` | Platform endpoint ARN | Mobile push via APNs/FCM | Device tokens, credentials, endpoint state |
| `firehose` | Firehose stream ARN | Storing events in S3 / analytics | Subscription role and streaming config |

**Note:** the table above describes **Standard topic** capabilities in supported configurations. FIFO delivers directly only to SQS. When `MaximumMessageSize > 256 KiB`, SNS supports only **SQS, Lambda, and Data Firehose subscriptions** with a cap of ≤ 100 subscriptions/topic; FIFO-to-SQS constraints still apply.

### 4.2. SQS — the most common choice for durable processing

~~~mermaid
flowchart LR
    T[(SNS Topic)] -->|delivered| Q[SQS Source Queue]
    Q --> W[Worker/Lambda ESM]
    Q -->|redrive on processing failure| D[SQS Consumer DLQ]
    T -->|SNS delivery fails| SD[SNS Subscription DLQ]
~~~

**An SQS queue policy is mandatory** to let the SNS principal call `sqs:SendMessage` from the exact topic ARN. For SSE-KMS queues, matching KMS permissions are also required. If the queue receives the message cleanly but the worker throws an error, retries belong to the **SQS consumer** (visibility timeout/redrive), not SNS.

**When to use:** inventory, shipping, billing, email workers, retryable jobs, batching, or consumer-controlled rate pacing.

### 4.3. Lambda — direct from SNS Standard

SNS can push to a Lambda function, invoking Lambda **asynchronously**. Distinguish two cases:

- SNS **cannot invoke** Lambda (missing function, resource policy denial): SNS delivery error → SNS retries → **SNS subscription DLQ**.
- SNS invoked Lambda successfully, but the handler throws or times out: Lambda manages **async retries**, `OnFailure` destinations, or a **Lambda DLQ** per its own configuration.

The Lambda function needs a resource-based policy allowing `sns.amazonaws.com` constrained by topic `SourceArn`. SNS FIFO cannot subscribe Lambda directly; route through SQS instead.

### 4.4. HTTPS — authenticated webhooks

SNS sends HTTP POST requests to HTTPS endpoints with `Type=SubscriptionConfirmation`, `Notification`, or `UnsubscribeConfirmation`.

Minimum controls:

1. Verify the **SNS message signature** using the SDK or AWS-documented procedure (prefer `SignatureVersion` 2 / SHA-256 where supported).
2. Verify `TopicArn` against an allowlist and confirm the certificate URL genuinely belongs to SNS over HTTPS.
3. Guard against SSRF when fetching `SigningCertURL` and confirming subscriptions.
4. Enforce additional application-level authorization if needed; HTTPS alone **does not replace** signature verification.
5. Persist the event **durably** before returning 2xx; never accept and crash before saving.
6. Handle duplicates using the business `eventId`.
7. Offload to a queue/worker so heavy work never runs inside the webhook HTTP request.

SNS treats HTTP(S) **5xx and 429** responses as retryable under the delivery policy; most other 4xx codes are treated as permanent failures. Do not assume an HTTP endpoint can auto-scale infinitely while SNS retries.

### 4.5. Email and email-json

Both `email` and `email-json` require mailbox confirmation and fit only content permitted over email:

- `email`: human-readable messages, such as simple operational alarms.
- `email-json`: emails carrying SNS JSON for downstream parsing.

**Do not treat SNS email as a full transactional email service.** If you need templates, bounce/complaint handling, unsubscribe compliance, campaigns, or deliverability metrics, consider **Amazon SES** or a dedicated email platform.

### 4.6. SMS

With `sms`, SNS delivers short text messages to phone numbers. Account for the **SMS sandbox**, user consent, opt-in/opt-out, origination identities, sender IDs, registrations, and country regulations. Pricing depends on country and SMS segment count; UTF-8 Unicode payloads can increase billable segments.

Never fan out PII, long tokens, or secrets over SMS. An SMS marked “delivered” does not guarantee the recipient read it.

### 4.7. Mobile push — application

`application` subscriptions target a **platform endpoint ARN** representing a device/app, with SNS pushing via APNs/FCM using platform credentials.

Operational duties include handling expired/rotated tokens, disabled endpoints, credential rotation, platform-specific payloads, error feedback, registration scale, and data minimization. Push alerts can appear on lock screens, so keep sensitive data out of them.

### 4.8. Amazon Data Firehose

`firehose` subscriptions stream events to **Amazon Data Firehose** for delivery into S3/data lakes or downstream targets per stream config. This requires a `SubscriptionRoleArn` with appropriate IAM permissions, failure/buffering monitoring, schema/cost tracking, and encryption.

Example:

~~~text
SNS orders-events → Firehose → S3 analytics bucket → Athena
~~~

Avoid sending full customer records if analytics only needs aggregated or pseudonymized fields.

## 5. Message Body, Attributes, and Raw Delivery

### 5.1. Event schema

An event might carry:

~~~json
{
  "schemaVersion": 1,
  "eventId": "evt-2026-001",
  "eventType": "order.created",
  "occurredAt": "2026-11-20T09:00:00Z",
  "orderId": "order-123",
  "tenantId": "shop-7",
  "amount": 250000,
  "currency": "VND"
}
~~~

Use `eventId` and `schemaVersion` for deduplication and compatibility; omit full payment card data, access tokens, and secrets. IDs and amounts can still be sensitive, so classify data and restrict subscribers.

### 5.2. Message attributes

SNS supports message attributes, for example:

~~~json
{
  "eventType": {
    "DataType": "String",
    "StringValue": "order.created"
  },
  "channel": {
    "DataType": "String",
    "StringValue": "fulfillment"
  },
  "priority": {
    "DataType": "Number",
    "StringValue": "2"
  }
}
~~~

Supported data types include `String`, `String.Array`, `Number`, and `Binary`. For `Number`, values are still passed via the API's `StringValue` field. Attribute names are case-sensitive: `eventType` differs from `EventType`. Attributes are routing metadata, not cryptographic proof of producer identity.

### 5.3. Default SNS JSON envelope

When an SQS subscription has `RawMessageDelivery=false`, the SQS body typically contains an SNS JSON wrapper:

~~~json
{
  "Type": "Notification",
  "MessageId": "sns-message-id-placeholder",
  "TopicArn": "arn:aws:sns:ap-southeast-1:111122223333:orders-events",
  "Subject": "order.created",
  "Message": "{\"eventId\":\"evt-2026-001\",\"orderId\":\"order-123\"}",
  "Timestamp": "2026-11-20T09:00:00.000Z",
  "SignatureVersion": "2",
  "Signature": "EXAMPLE",
  "SigningCertURL": "https://sns.ap-southeast-1.amazonaws.com/EXAMPLE.pem"
}
~~~

This JSON is **illustrative only** and has no valid signature. The SQS consumer must unwrap **SQS body → SNS envelope → JSON inside the `Message` field**.

### 5.4. `RawMessageDelivery`

| Endpoint | `Raw=false` | `Raw=true` |
|---|---|---|
| SQS | SNS envelope wrapping message | **SQS body is the original message** |
| HTTP(S) | SNS JSON notification | Raw payload plus raw-delivery headers |
| Firehose | SNS-formatted per config | Raw payload where supported |
| Lambda | SNS Lambda event envelope | Does not use SQS-style raw option |
| Email/SMS | Delivered per protocol | Does not apply SQS-style raw option |

With **SQS subscriptions using `RawMessageDelivery=true`**, SNS supports at most **10 message attributes**. If a published message carries more than 10 attributes, SNS may **discard delivery to that subscription as a client-side error**. Keep schemas lean, monitor failed deliveries, or disable raw delivery if more attributes are needed.

When toggling raw mode, **consumer parsers must change**. Messages already sitting in the queue retain the old format, so rollouts must handle both formats during the transition window.

### 5.5. Protocol-specific payloads

SNS `Publish` with `MessageStructure=json` allows tailored payloads per protocol:

~~~json
{
  "default": "Order 123 created",
  "email": "Order 123 has been created.",
  "sms": "Order 123 created.",
  "sqs": "{\"eventId\":\"evt-2026-001\",\"orderId\":\"order-123\"}"
}
~~~

Each protocol value must be a **JSON string** per the SNS API. Validate parsers and quotas, and keep sensitive fields out of email/SMS branches.

## 6. Subscription Filter Policies

### 6.1. Default full fan-out

Without a filter policy, a subscription receives every message subject to delivery rules. With a filter, SNS delivers only **matching** messages.

~~~mermaid
flowchart TD
    P[Publish event] --> T[(SNS Topic)]
    T --> A{Filter eventType=order.created?}
    T --> B{Filter eventType=payment.received?}
    T --> C[No filter]
    A -->|true| Q1[SQS inventory]
    B -->|true| Q2[SQS billing]
    C --> Q3[SQS analytics]
~~~

### 6.2. Default `MessageAttributes` scope

Filter policy:

~~~json
{
  "eventType": ["order.created", "order.updated"],
  "channel": ["fulfillment"]
}
~~~

Logic:

~~~text
(eventType = order.created OR order.updated)
AND (channel = fulfillment)
~~~

Filters support operators such as numeric ranges, prefix, anything-but, and existence. If a message omits `channel`, the filter above will not match. Verify data types and JSON syntax, and avoid attribute casing typos.

### 6.3. `MessageBody` scope

If producers only populate the JSON body, set:

~~~text
FilterPolicyScope = MessageBody
~~~

with an example policy:

~~~json
{
  "eventType": ["order.created"],
  "metadata": {
    "region": ["ap-southeast-1"]
  }
}
~~~

The payload must be a valid JSON object with matching fields and types. Nested body filtering differs from attribute filtering. **Never confuse `FilterPolicy` with access control:** an untrusted endpoint must never subscribe to a topic carrying secrets simply because its current filter doesn't match them.

### 6.4. Eventual consistency

Per AWS, filter policy updates can take **up to 15 minutes** to propagate fully. Therefore, when rolling out new event types, consider publishing compatible forms during the transition window and monitoring filtering metrics rather than changing a filter and immediately relying on it for transactional routing.

### 6.5. Filter test matrix

| Message attributes | Inventory filter | Billing filter | Analytics (no filter) |
|---|---|---|---|
| `eventType=order.created`, `channel=fulfillment` | Received | No | Received |
| `eventType=payment.received`, `channel=finance` | No | Received | Received |
| Missing `eventType` | No | No | Received |
| Key `EventType` instead of `eventType` | No | No | Received |

## 7. SNS Retries vs. Consumer Retries

### 7.1. Delivery retries

| Protocol | Sample errors | Mechanism to monitor |
|---|---|---|
| HTTP(S) | 429, 5xx, timeouts | SNS `DeliveryPolicy`/backoff |
| SQS | Queue denied, deleted, service error | SNS managed retries, queue policy/KMS |
| Lambda | Permission denied, missing function | SNS delivery retries to Lambda |
| Email/SMS/mobile | Delivery endpoint error | SNS managed retries per protocol |
| Firehose | IAM/stream unavailable | SNS delivery/retries, feedback logs |

For HTTP(S), SNS supports a `DeliveryPolicy` with no-delay, pre-backoff, backoff, and post-backoff phases plus average `maxReceivesPerSecond`. Do not treat this as a strict hard rate limiter: bursts can still occur. Webhooks should verify signatures, **persist durably** to a queue/DB, and return 2xx quickly while workers run heavy processing asynchronously.

### 7.2. Two retry tiers

~~~text
SNS Standard topic
  -> SQS queue: SNS delivery succeeds
     -> worker processing fails, does not delete message
        -> SQS visibility timeout
        -> SQS source-queue DLQ when maxReceiveCount is reached

SNS Standard topic
  -> SQS queue: SNS delivery fails due to queue policy
     -> SNS retries, then routes to SNS subscription DLQ if configured
~~~

Similarly with Lambda, SNS delivery success only means Lambda **accepted the async invocation**. If the handler fails afterward, inspect **Lambda async retries / `OnFailure` destination / Lambda DLQ**, not SNS HTTP delivery policies.

## 8. SNS Subscription DLQs vs. SQS Consumer DLQs

### 8.1. Subscription-level DLQ

An SNS subscription carries a `RedrivePolicy`:

~~~json
{
  "deadLetterTargetArn": "arn:aws:sqs:ap-southeast-1:111122223333:orders-delivery-dlq"
}
~~~

SNS sends messages there when **it cannot deliver the notification to the endpoint** under its retry semantics. The DLQ must reside in the **same account and Region as the SNS subscription**, using a Standard DLQ for Standard subscriptions and a FIFO DLQ for FIFO topic subscriptions per AWS guidance.

The SQS DLQ must allow SNS `sqs:SendMessage` from the exact topic ARN. For encrypted queues, configure the KMS key policy accordingly.

### 8.2. Three commonly confused scenarios

| Symptom | Where to find the failed event |
|---|---|
| SNS cannot deliver to SQS due to broken queue policy | **SNS subscription DLQ** |
| SQS received it, worker throws repeatedly | **SQS source-queue DLQ** |
| SNS cannot invoke Lambda | **SNS subscription DLQ** |
| Lambda accepted event, then handler timed out | **Lambda `OnFailure` destination or Lambda DLQ** |
| HTTP(S) webhook fails after all retries | **SNS subscription DLQ** |
| Email delivered, user never opened it | No DLQ triggered just for “unread” |

Different DLQ layers have **different owners and different runbooks**. Every DLQ needs retention, alarms, encryption, an assigned investigator, and an idempotent replay procedure.

### 8.3. SQS DLQ retention and metrics

An SNS subscription DLQ is simply an SQS queue by **role**. Configure appropriate SQS retention—often up to 14 days when investigation time is needed. Never assume infinite retention.

Per AWS, `ApproximateNumberOfMessagesVisible` is the right metric to monitor DLQ backlog. Do not rely solely on SQS `NumberOfMessagesSent` to count messages moved automatically via redrive.

## 9. IAM and End-to-End Security

### 9.1. Three permission layers for SNS → SQS

1. **Producer identity policy:** allows calling `sns:Publish` on the topic.
2. **SNS topic access policy:** permits authorized principals/accounts to publish, subscribe, or manage.
3. **SQS queue resource policy:** allows the SNS service principal to call `sqs:SendMessage` from the exact `aws:SourceArn`.

For SSE-KMS, **KMS key policies** and permissions must also permit the services per encryption rules.

### 9.2. Publisher IAM policy

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sns:Publish",
      "Resource": "arn:aws:sns:ap-southeast-1:111122223333:orders-events"
    }
  ]
}
~~~

Assign IAM roles to Lambda/EC2/ECS workloads instead of embedding AWS access keys in source code.

### 9.3. SQS queue policy

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowOneSnsTopic",
      "Effect": "Allow",
      "Principal": {"Service": "sns.amazonaws.com"},
      "Action": "sqs:SendMessage",
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:inventory-events",
      "Condition": {
        "ArnEquals": {
          "aws:SourceArn": "arn:aws:sns:ap-southeast-1:111122223333:orders-events"
        }
      }
    }
  ]
}
~~~

`aws:SourceArn` mitigates confused-deputy risks. Never open a queue with `Principal: "*"` or permit every topic just to work around `AccessDenied`.

### 9.4. Lambda permission

A Lambda subscription requires a resource-based permission for SNS:

~~~bash
# ILLUSTRATIVE ONLY - use only on an approved sandbox function
aws lambda add-permission \
  --function-name aws-lab-notification-worker \
  --statement-id AllowOrdersTopic \
  --action lambda:InvokeFunction \
  --principal sns.amazonaws.com \
  --source-arn arn:aws:sns:ap-southeast-1:111122223333:orders-events \
  --region ap-southeast-1
~~~

### 9.5. Cross-account, encryption, and PrivateLink

Cross-account SQS subscriptions require matching **topic policies and queue policies** on both sides, plus **KMS key policies** if encrypted. For SNS publishers inside a private VPC, an **SNS interface VPC endpoint / PrivateLink** can be used where supported, though it covers only the **producer → SNS API** hop—it neither turns HTTP(S) webhooks into private-network calls nor replaces IAM.

Separate topics by **trust boundary**. Subscription filters **do not replace access control**; never let an external principal subscribe to a topic containing PII solely because its filter currently excludes those events.

## 10. SNS Message Size and 2026 Quotas

### 10.1. AWS update from September 2026

On **September 18, 2026**, AWS announced that SNS accepts messages up to **1 MiB** when `MaximumMessageSize` is configured on a topic.

| Property | Value |
|---|---|
| Default | **256 KiB (262,144 bytes)** |
| Configurable maximum | **1 MiB (1,048,576 bytes)** |
| Attribute name | `MaximumMessageSize` |
| When > 256 KiB | Only **SQS, Lambda, and Data Firehose** subscriptions; max **100 subscriptions/topic** |
| When ≤ 256 KiB | Other protocols like HTTPS/email/SMS/mobile supported per topic type |
| Size calculation | Both body and message attributes count toward the configured maximum |

**FIFO limitation remains unchanged:** FIFO topics still deliver directly only to SQS, even when `MaximumMessageSize` is raised.

### 10.2. Should you send large payloads?

Large payloads increase publish/delivery fees, processing duration, log volume, PII exposure, and DLQ storage. Usually it is better to emit **event metadata + an S3 reference**:

~~~json
{
  "eventType": "report.ready",
  "eventId": "evt-report-123",
  "reportId": "report-123",
  "s3Bucket": "private-report-bucket",
  "s3Key": "reports/report-123.json",
  "versionId": "s3-version-example"
}
~~~

Consumers use IAM to read the private S3 object at the exact version, backed by encryption and retention. Never push payment data or tokens through SNS merely because the size ceiling increased.

### 10.3. Cost

Costs can include SNS requests (message size affects billing units), per-protocol deliveries, SQS requests/DLQs, Lambda invocations/duration, Firehose ingestion, country-specific SMS/telecom fees, KMS requests, CloudWatch, and networking. One message sent to 10 subscriptions generates **10 deliveries** and downstream costs; use filters to eliminate unnecessary deliveries and track budgets.

## 11. Practice 1 — Inspecting SNS with AWS CLI (Read-Only)

> This section neither creates nor modifies resources. You need AWS CLI v2, a sandbox account/Region, and permissions such as `sns:ListTopics`, `sns:GetTopicAttributes`, `sns:ListSubscriptionsByTopic`, and `sns:GetSubscriptionAttributes`. Do not read messages from shared SQS queues.

### 11.1. Verify identity

Bash / AWS CloudShell:

~~~bash
export AWS_PROFILE=aws-lab-dev
export AWS_DEFAULT_REGION=ap-southeast-1
REGION=ap-southeast-1

aws sts get-caller-identity --profile "$AWS_PROFILE"
~~~

If CloudShell already provides IAM credentials without this profile, omit `AWS_PROFILE` and `--profile`. Verify `Account` and `Arn` so you never operate in the wrong environment.

### 11.2. List topics

~~~bash
aws sns list-topics \
  --region "$REGION" \
  --query 'Topics[].TopicArn' \
  --output table
~~~

Results may be empty depending on Region, account, or permissions. Use AWS CLI pagination when needed; never create production topics just for practice.

### 11.3. Read topic attributes

~~~bash
TOPIC_ARN="arn:aws:sns:ap-southeast-1:111122223333:orders-events"

aws sns get-topic-attributes \
  --topic-arn "$TOPIC_ARN" \
  --region "$REGION" \
  --query 'Attributes.{FifoTopic:FifoTopic,ContentBasedDeduplication:ContentBasedDeduplication,MaximumMessageSize:MaximumMessageSize,SubscriptionsConfirmed:SubscriptionsConfirmed,SubscriptionsPending:SubscriptionsPending,KmsMasterKeyId:KmsMasterKeyId}' \
  --output json
~~~

All ARNs are **illustrative**. Check topic type, max message size, confirmed/pending counts, and encryption. Avoid printing full topic resource policies into public logs if they contain internal role/account metadata.

### 11.4. List subscriptions

~~~bash
aws sns list-subscriptions-by-topic \
  --topic-arn "$TOPIC_ARN" \
  --region "$REGION" \
  --query 'Subscriptions[].{Protocol:Protocol,SubscriptionArn:SubscriptionArn}' \
  --output table
~~~

`Endpoint` is intentionally omitted from output because it can expose emails, phone numbers, webhook URLs, or internal resource ARNs. If `PendingConfirmation` appears, the subscriber must confirm through a secure channel.

Read attributes of a confirmed subscription:

~~~bash
SUB_ARN="arn:aws:sns:ap-southeast-1:111122223333:orders-events:550e8400-e29b-41d4-a716-446655440000"

aws sns get-subscription-attributes \
  --subscription-arn "$SUB_ARN" \
  --region "$REGION" \
  --query 'Attributes.{Protocol:Protocol,Raw:RawMessageDelivery,FilterScope:FilterPolicyScope,Filter:FilterPolicy,Redrive:RedrivePolicy,DeliveryPolicy:DeliveryPolicy}' \
  --output json
~~~

**Analyze:** Does the subscription have a filter policy? Is `FilterPolicyScope` set to `MessageAttributes` or `MessageBody`? Does `RawMessageDelivery` match the parser? Is a DLQ configured in `RedrivePolicy`?

### 11.5. Inspect SQS queue metadata

~~~bash
QUEUE_URL="https://sqs.ap-southeast-1.amazonaws.com/111122223333/inventory-events"

aws sqs get-queue-attributes \
  --queue-url "$QUEUE_URL" \
  --attribute-names QueueArn RedrivePolicy KmsMasterKeyId \
  --region "$REGION" \
  --output json
~~~

If checking the queue resource policy, use `get-queue-attributes --attribute-names Policy` per authorized permissions and **never publish internal policies publicly**. Notice how the consumer's SQS DLQ differs from the SNS subscription DLQ.

**Never call `ReceiveMessage` on a production queue**: receiving makes messages temporarily invisible and interferes with live workers.

## 12. Practice 2 — SNS Standard → SQS Standard (Optional Sandbox)

> This section **mutates state and may incur charges**. Run it only in a sandbox account on resources you own with approval. Never subscribe other people's email addresses, phone numbers, or HTTPS endpoints. You can complete this section simply by analyzing the IaC without deploying it.

### 12.1. Architecture

~~~text
SNS Standard topic: aws-lab-orders-events
    |
    | Subscription protocol=sqs
    v
SQS Standard queue: aws-lab-inventory-events
    |
    v
Test consumer
~~~

Steps:

1. Create an isolated sandbox topic and queue.
2. Add a queue policy allowing `sns.amazonaws.com` with `aws:SourceArn` matching the topic ARN.
3. Subscribe the queue ARN to the topic.
4. Set filter `eventType=order.created`.
5. Publish a test message with attributes.
6. Inspect the SQS message body/wrapper in the lab queue.
7. Clean up topic, queue, and subscription via IaC once no needed data remains.

### 12.2. Reference CloudFormation template

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: SNS Standard to SQS Standard lab, sandbox only

Resources:
  EventsTopic:
    Type: AWS::SNS::Topic
    Properties:
      TopicName: aws-lab-orders-events

  InventoryQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: aws-lab-inventory-events

  InventoryQueuePolicy:
    Type: AWS::SQS::QueuePolicy
    Properties:
      Queues:
        - !Ref InventoryQueue
      PolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Sid: AllowOnlyEventsTopic
            Effect: Allow
            Principal:
              Service: sns.amazonaws.com
            Action: sqs:SendMessage
            Resource: !GetAtt InventoryQueue.Arn
            Condition:
              ArnEquals:
                aws:SourceArn: !Ref EventsTopic

  InventorySubscription:
    Type: AWS::SNS::Subscription
    DependsOn: InventoryQueuePolicy
    Properties:
      TopicArn: !Ref EventsTopic
      Protocol: sqs
      Endpoint: !GetAtt InventoryQueue.Arn
      RawMessageDelivery: false
      FilterPolicy:
        eventType:
          - order.created

Outputs:
  TopicArn:
    Value: !Ref EventsTopic
  QueueUrl:
    Value: !Ref InventoryQueue
~~~

This is a **minimal training configuration**. Production setups must consider SNS/SQS SSE-KMS, subscription DLQs, metrics/alarms, resource tags, queue retention, deployment permissions, and quotas. Use distinct stack/resource names in shared learning accounts, and never deploy onto existing shared resources.

### 12.3. Inspect stack and publish a test message

Assuming the stack was created through an approved process:

~~~bash
STACK="aws-lab-sns-sqs"

aws cloudformation describe-stacks \
  --stack-name "$STACK" \
  --region "$REGION" \
  --query 'Stacks[].{Status:StackStatus,Outputs:Outputs}' \
  --output json
~~~

Grab the topic ARN and queue URL from Outputs, substituting for the placeholders below:

~~~bash
TOPIC_ARN="arn:aws:sns:ap-southeast-1:111122223333:aws-lab-orders-events"

aws sns publish \
  --topic-arn "$TOPIC_ARN" \
  --message '{"schemaVersion":1,"eventId":"training-001","eventType":"order.created","orderId":"test-123"}' \
  --message-attributes '{"eventType":{"DataType":"String","StringValue":"order.created"}}' \
  --region "$REGION"
~~~

If you just configured a filter, account for **up to 15 minutes of eventual consistency** before judging success or failure.

### 12.4. Inspect the message in the lab queue

~~~bash
QUEUE_URL="https://sqs.ap-southeast-1.amazonaws.com/111122223333/aws-lab-inventory-events"

aws sqs receive-message \
  --queue-url "$QUEUE_URL" \
  --max-number-of-messages 1 \
  --wait-time-seconds 5 \
  --message-attribute-names All \
  --region "$REGION" \
  --output json
~~~

**This command changes visibility** and must only be run on your own lab queue. With `RawMessageDelivery=false`, the SQS body wraps the SNS JSON envelope; `Message` inside it holds the original order JSON string.

If switching `raw=true`, consumers receive the raw body directly and must update their parser:

~~~bash
SUB_ARN="arn:aws:sns:ap-southeast-1:111122223333:aws-lab-orders-events:subscription-id-placeholder"

aws sns set-subscription-attributes \
  --subscription-arn "$SUB_ARN" \
  --attribute-name RawMessageDelivery \
  --attribute-value true \
  --region "$REGION"
~~~

Never flip raw mode on a production subscription without a backward/forward-compatible rollout plan for queued messages.

### 12.5. Clean up the sandbox

Delete only stacks you own after confirming no shared resources or business messages remain:

~~~bash
# STATE-MUTATING: run only when authorized
aws cloudformation delete-stack \
  --stack-name "$STACK" \
  --region "$REGION"
~~~

Verify stack deletion status, confirm no lingering SNS/SQS resources remain, and check KMS/CloudWatch/NAT charges if created. Never delete a queue holding real business data.

## 13. HTTPS Subscriptions: Authentication and Safe Responses

### 13.1. Three message types

An HTTPS endpoint can receive:

- `SubscriptionConfirmation`: confirms the endpoint is under your control.
- `Notification`: the actual event payload.
- `UnsubscribeConfirmation`: notification that the subscription was canceled.

Example JSON **without a valid signature**:

~~~json
{
  "Type": "SubscriptionConfirmation",
  "MessageId": "placeholder-message-id",
  "TopicArn": "arn:aws:sns:ap-southeast-1:111122223333:orders-events",
  "Token": "placeholder",
  "SubscribeURL": "https://sns.ap-southeast-1.amazonaws.com/?Action=ConfirmSubscription&...",
  "Timestamp": "2026-11-20T09:00:00.000Z",
  "SignatureVersion": "2",
  "Signature": "EXAMPLE",
  "SigningCertURL": "https://sns.ap-southeast-1.amazonaws.com/EXAMPLE.pem"
}
~~~

### 13.2. HTTP webhook runbook

~~~text
POST received
  |
  | 1. Enforce body size limit, validate JSON.
  | 2. Verify SNS signature and trusted TopicArn.
  | 3. Verify certificate URL/chain, prevent SSRF.
  |
  +-- SubscriptionConfirmation -> confirm only approved topics
  |
  +-- Notification -> validate eventId + schema
  |                   persist event durably to queue/DB
  |                   return 2xx after commit
  |
  +-- UnsubscribeConfirmation -> audit/restore receiving flow
~~~

Never trust just `User-Agent` or a source IP. AWS recommends verifying the cryptographic signature; with `SignatureVersion=2`, validate SHA-256 per SNS rules. Never fetch a certificate URL from an untrusted payload without validating its hostname and trust anchor.

**A webhook returning 200 before committing risks losing messages:** SNS considers delivery complete, yet the process could crash before persisting internally. When unable to persist, return a retryable status per policy rather than swallowing errors.

## 14. Monitoring SNS and Downstream Targets

### 14.1. Key metrics

| Metric/signal | Source | Question answered |
|---|---|---|
| `NumberOfMessagesPublished` | SNS | How many messages entered the topic? |
| `NumberOfNotificationsDelivered` | SNS | Did SNS deliver successfully to endpoints? |
| `NumberOfNotificationsFailed` | SNS | Are deliveries failing? |
| `NumberOfNotificationsFilteredOut` | SNS | Are abnormally many messages filtered out? |
| `NumberOfNotificationsRedrivenToDlq` | SNS | Are events routing to the SNS DLQ? |
| `ApproximateNumberOfMessagesVisible` | SQS | Is backlog or DLQ depth climbing? |
| `ApproximateAgeOfOldestMessage` | SQS | Is processing latency high? |
| `Errors`, `Throttles`, `AsyncEventsDropped` | Lambda | Are handlers or async queues failing? |
| 4xx/5xx, request duration | HTTPS endpoint | Is the webhook slow or rejecting? |
| Firehose delivery metrics | Firehose | Is analytics persisting successfully? |

Metric availability, dimensions, and costs vary by configuration. **SNS `Delivered` does not prove business consumer commits succeeded**.

### 14.2. Delivery status logging

SNS integrates with **CloudWatch Logs** to log delivery status for supported protocols when feedback roles and settings are configured. Log minimal data, mask PII, and set retention. Configure alerts for failed deliveries and DLQ age; dashboards never replace an on-call owner.

### 14.3. Incident runbook

~~~text
1. Confirm account, Region, TopicArn, MessageId.
2. Standard or FIFO topic? Is the protocol supported?
3. Is subscription Confirmed or PendingConfirmation?
4. Do FilterPolicyScope and attributes/body match?
5. Check SNS Published / FilteredOut / Delivered / Failed metrics.
6. Check Queue/Lambda/Firehose: policies, ARNs, Region, KMS.
7. For HTTPS: signature, certificate, TopicArn, HTTP status, latency.
8. If SNS delivered, check SQS/Lambda consumer processing and DLQ.
9. Reconcile business eventId: did side effects commit?
10. Fix the right layer, replay carefully, and record an audit trail.
~~~

## 15. Idempotency, Event Contracts, and Outbox

### 15.1. At-least-once vs. exactly-once

An SQS worker can process an order and crash before `DeleteMessage`. The message reappears after the visibility timeout and executes a second time. The fix is idempotency:

~~~text
operationId = order-123:reserve-inventory

if operationId already COMPLETED:
    acknowledge without side effects
else:
    atomic claim in DynamoDB/DB
    execute inventory operation
    mark completed transactionally
    acknowledge message
~~~

Never use Lambda's `awsRequestId` as a business key if each attempt creates a new ID. `SNS MessageId` can also differ if the producer republishes the same business event. Use a stable producer-issued `eventId`/`operationId`.

### 15.2. Transactional outbox

Risk:

~~~text
Order database commit succeeds
Process crashes before SNS Publish
=> no consumer gets notified
~~~

Outbox pattern:

~~~mermaid
flowchart LR
    API[Order API] --> TX[Database transaction]
    TX --> ORD[(Order table)]
    TX --> OUT[(Outbox table)]
    OUT --> PUB[Publisher / CDC]
    PUB --> SNS[(SNS topic)]
    SNS --> SQS[SQS queues]
~~~

Order and outbox record commit in the same transaction as supported by the DB. The publisher can double-publish if it crashes before marking dispatched, so consumers still require idempotency.

### 15.3. Safe replay

Never redrive every DLQ message back into the topic blindly. Doing so can trigger a second full fan-out and double charges. Before replaying:

1. Identify which subscription/consumer failed and confirm the root cause is fixed.
2. Reconcile business state using stable event IDs.
3. Verify schema versions and validity windows.
4. Target only the affected destination, not the whole topic unnecessarily.
5. Rate-limit the replay and watch for duplicates or side effects.
6. Record an audit entry and clear the DLQ only after verification.

## 16. Cost, Limits, and Data Classification

| Component | Costs to include |
|---|---|
| SNS | Publishes and deliveries, message size/chunks |
| SQS | Queue requests, retention, DLQs, consumers |
| Lambda | Invocations, duration, memory, retries |
| HTTP(S)/mobile | Receiver infrastructure, traffic, retries, vendor fees |
| SMS | Country rates, sender registration, message segments, opt-in |
| Firehose/S3 | Streaming ingestion, storage, transforms, queries |
| KMS | Key storage and requests per configuration |
| CloudWatch | Metrics, logs, alarms, retention |
| Networking | VPC endpoints, data transfer per architecture |

A message sent to 8 subscribers is not billed like a single isolated notification. Use filters to prune unneeded deliveries, **never drop required business messages** just to cut bills.

**Never place secrets, access tokens, payment card details, or unnecessary PII** onto broad topics; emails, webhooks, analytics, and CloudWatch logs each carry different trust boundaries. For large data, store a private S3 object and publish a reference event guarded by IAM/KMS.

## 17. Common Errors

| Symptom | Common cause | Where to check |
|---|---|---|
| Publish returns `MessageId`, yet SQS is empty | Filter mismatch, policy, wrong ARN, or missing subscription | `ListSubscriptionsByTopic`, filter, SNS metrics |
| Subscription stuck in `PendingConfirmation` | Endpoint owner hasn't confirmed | Email/HTTPS confirmation workflow |
| `AccessDenied` on publish | Producer IAM, topic policy, SCP, or KMS | Principal, Resource, Conditions |
| SQS does not receive messages | Queue policy missing `sns.amazonaws.com`/`SourceArn` | Resource policy, KMS |
| Lambda not invoked | Lambda resource policy missing permission | `lambda:InvokeFunction` with `SourceArn` |
| SNS delivered, yet Lambda reports `Errors` | Handler fails after invocation | Lambda logs, async retries/destinations |
| HTTPS 403 | Bad signature, `TopicArn`, or app policy | Signature verification, HTTP logs |
| HTTPS 429/5xx | Overload / outage | `DeliveryPolicy`, queue ingress, scaling |
| Email not arriving | Pending, spam, mailbox rules | Subscription status, email route |
| SMS not arriving | Sender registration / sandbox / consent | SMS settings, Region, pricing |
| Raw mode breaks parser | Consumer expects SNS envelope | Support raw body and legacy format |
| Raw SQS drops messages | Message has > 10 attributes | Reduce attributes / disable raw, alert failures |
| FIFO topic won't subscribe Lambda | FIFO delivers directly only to SQS | Intermediate SQS FIFO/Standard queue |
| FIFO → SQS Standard loses order | Standard queue is best effort | Use a FIFO queue for strict order |
| New filter has no effect yet | Eventual consistency up to 15 minutes | Wait and test with correlation IDs |
| SNS DLQ empty despite worker errors | Delivery succeeded; processing failed | SQS consumer DLQ |
| Message exceeds size limit | `MaximumMessageSize` not raised / incompatible | Body + attributes, protocol, 1 MiB cap |
| Duplicated side effects | Retries / replay / at-least-once | Business idempotency |
| Rising costs | Fan-out, retries, SMS, logging | Cost Explorer / Budgets |
| Old messages lingering in DLQ | No owner / runbook | Alarms, retry/replay workflow |

## 18. Applied Exercise

### 18.1. Context

An online learning platform has:

- `enrollment.created`: must send an email and grant course access.
- `payment.received`: accounting must process strictly in order per `enrollmentId`.
- Analytics stores all events but **must never receive tokens or PII**.
- If the email worker stops for 30 minutes, no jobs may be lost.
- Learners might click enroll twice, yet must never be charged twice.

### 18.2. Reference design

~~~mermaid
flowchart TD
    API[Enrollment API] --> DB[(DB + Outbox)]
    DB --> PUB[Outbox publisher]
    PUB --> STD[(SNS Standard)]
    PUB --> FIFO[(SNS FIFO finance)]
    STD -->|filter enrollment.created| SQ1[SQS notification]
    STD -->|sanitized events| FH[Firehose -> S3]
    FIFO -->|group=enrollmentId| SQF[SQS FIFO finance]
    SQ1 --> W1[Notification worker]
    SQF --> W2[Finance worker]
    SQ1 -. processing fail .-> DLQ1[SQS consumer DLQ]
    STD -. delivery fail .-> DLQ2[SNS subscription DLQ]
~~~

Because email templates and a durable backlog are required, let SNS deliver to an SQS queue so the notification worker can call an appropriate email service. Finance FIFO sets `MessageGroupId` to `enrollmentId`, while idempotency still verifies business operation IDs.

### 18.3. Self-check questions

1. How do a topic, subscription, and endpoint differ?
2. Does `Publish` returning a `MessageId` mean all consumers succeeded?
3. Why does SNS Standard not guarantee strict ordering?
4. Does SNS FIFO support direct subscriptions to Lambda, HTTPS, or email?
5. If Lambda must process FIFO events, what architecture works?
6. What is the default `FilterPolicyScope`?
7. What message body format does `MessageBody` filtering require?
8. If `eventType` is omitted, will a filter requiring that field receive the message?
9. Why can't a filter replace tenant authorization?
10. How does `RawMessageDelivery` change the SQS body?
11. Why is raw SQS with > 10 attributes dangerous?
12. How does an HTTPS webhook verify SNS requests?
13. What can happen when a webhook returns HTTP 200 before committing?
14. Does a `PendingConfirmation` subscription receive regular notifications?
15. How does an SNS subscription DLQ differ from an SQS source-queue DLQ?
16. When SNS delivers to Lambda and the handler throws, which service handles retries?
17. Does a publisher's IAM role automatically permit SNS to write to SQS?
18. Does FIFO → SQS Standard preserve strict ordering?
19. What are SNS's default and maximum message sizes in 2026?
20. Why are business idempotency keys and outboxes necessary?

**Suggested answers:** 1. Topic publishes, subscription links, endpoint receives. 2. No. 3. Best-effort ordering and at-least-once delivery. 4. No, FIFO delivers directly only to SQS. 5. SNS FIFO → SQS → Lambda ESM. 6. `MessageAttributes`. 7. Valid JSON object. 8. No. 9. Filtering does not enforce trustworthy access control. 10. Body becomes the raw original message. 11. Delivery may be discarded as a client-side error. 12. Signature, `TopicArn`, signing certificate URL/chain. 13. Events can be lost if the process crashes. 14. No. 15. Endpoint delivery failures vs. consumer processing failures. 16. Lambda async retries. 17. No; requires SQS queue resource policy and KMS grants. 18. No. 19. 256 KiB default, configurable up to 1 MiB subject to protocol/subscription limits. 20. Prevent duplicates and prevent lost events after DB commits.

## 19. Pre-Production Checklist

### Topic/subscription

- [ ] Selected Standard vs. FIFO based on ordering/deduplication and supported protocols.
- [ ] Aligned FIFO groups, dedup IDs, and target SQS queues.
- [ ] Every subscription has a clear owner, confirmed status, endpoint, and purpose.
- [ ] Tested filter policies against attributes/body and accounted for propagation delay.
- [ ] Verified `RawMessageDelivery` compatibility with parsers and the 10-attribute SQS limit.
- [ ] Verified `MaximumMessageSize`, supported protocols, and quotas when > 256 KiB.
- [ ] Defined stable `schemaVersion`, `eventId`, and `operationId` fields.

### Security/reliability

- [ ] Producer IAM grants only `sns:Publish` to required topics.
- [ ] SNS topic access policy restricts publish, subscribe, and update permissions.
- [ ] SQS queue policy scopes `sns.amazonaws.com` with `aws:SourceArn`.
- [ ] Lambda resource policy restricts invocation to the exact topic.
- [ ] KMS permissions, encryption, and VPC endpoint policies are verified.
- [ ] HTTPS endpoints validate signatures, certificates, and `TopicArn` with SSRF defenses.
- [ ] Configured SNS subscription DLQs for critical delivery failures.
- [ ] SQS/Lambda consumers have separate retries and DLQs for processing failures.
- [ ] Consumers are idempotent; replays verify downstream side effects.
- [ ] PII and secrets are never fanned out across trust boundaries.

### Monitoring/cost

- [ ] CloudWatch metrics/alarms cover published, failed, filtered, and redriven counts.
- [ ] SQS backlog/DLQs, Lambda `Errors`, and HTTP endpoint statuses are monitored.
- [ ] On-call owner, retention, runbooks, and auditing are established.
- [ ] Tested queue denials, webhook failures, filter mismatches, and duplicates.
- [ ] Budgeted SNS/SQS/Lambda/SMS/Firehose/KMS/CloudWatch costs.
- [ ] Applied tags, AWS Budgets, lifecycle rules, and sandbox cleanup.
- [ ] Infrastructure changes go through IaC/change approval with rollback plans.

**Expected outcome:** learners can design SNS topics and subscriptions with the right delivery protocols, understand fan-out, filtering, confirmation, retries, and DLQs at each layer, implement secure access controls and encryption, and observe, recover, and manage costs.

## Official AWS Documentation

- [What is Amazon SNS?](https://docs.aws.amazon.com/sns/latest/dg/welcome.html)
- [SNS features and capabilities](https://docs.aws.amazon.com/sns/latest/dg/welcome-features.html)
- [Creating SNS topics](https://docs.aws.amazon.com/sns/latest/dg/sns-create-topic.html)
- [Creating topic subscriptions](https://docs.aws.amazon.com/sns/latest/dg/sns-create-subscribe-endpoint-to-topic.html)
- [SNS message delivery](https://docs.aws.amazon.com/sns/latest/dg/message-delivery.html)
- [SNS FIFO message delivery](https://docs.aws.amazon.com/sns/latest/dg/fifo-message-delivery.html)
- [FIFO ordering](https://docs.aws.amazon.com/sns/latest/dg/fifo-topic-message-ordering.html)
- [SNS message filtering](https://docs.aws.amazon.com/sns/latest/dg/sns-message-filtering.html)
- [Message filtering scope](https://docs.aws.amazon.com/sns/latest/dg/sns-message-filtering-scope.html)
- [Raw message delivery](https://docs.aws.amazon.com/sns/latest/dg/sns-large-payload-raw-message-delivery.html)
- [SNS message attributes](https://docs.aws.amazon.com/sns/latest/dg/sns-message-attributes.html)
- [SNS delivery retry](https://docs.aws.amazon.com/sns/latest/dg/sns-message-delivery-retries.html)
- [SNS dead-letter queues](https://docs.aws.amazon.com/sns/latest/dg/sns-dead-letter-queues.html)
- [Configuring SNS subscription DLQ](https://docs.aws.amazon.com/sns/latest/dg/sns-configure-dead-letter-queue.html)
- [Verifying SNS message signature](https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message.html)
- [Subscribe an SQS queue to SNS](https://docs.aws.amazon.com/sns/latest/dg/subscribe-sqs-queue-to-sns-topic.html)
- [Using Lambda with SNS](https://docs.aws.amazon.com/lambda/latest/dg/with-sns.html)
- [Publishing SNS messages up to 1 MiB](https://docs.aws.amazon.com/sns/latest/dg/large-message-payloads.html)
- [AWS SNS 1 MiB announcement (September 18, 2026)](https://aws.amazon.com/about-aws/whats-new/2026/09/amazon-sns-1mib-support/)
- [SNS pricing](https://aws.amazon.com/sns/pricing/)
- [AWS Pricing Calculator](https://calculator.aws/)

> **Usage note:** All ARNs, account IDs, URLs, SNS topics, SQS queues, code, and IaC in this lesson are **training examples**. AWS may update message sizes, quotas, protocol support, IAM/KMS requirements, and Regional pricing. Before deploying to production, verify current AWS documentation, test in a sandbox, classify fanned-out data, and follow change-approval processes.
