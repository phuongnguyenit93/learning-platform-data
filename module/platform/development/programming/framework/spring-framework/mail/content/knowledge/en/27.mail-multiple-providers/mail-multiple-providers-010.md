# Monitoring Deliverability Differences Across Providers

When an application uses Spring Framework Mail to send email through multiple providers, calling `JavaMailSender.send(...)` successfully **does not mean the recipient saw the email in their Inbox**. Spring Mail primarily provides an API to build MIME messages and hand content off to a mail transport. After the first SMTP server accepts the message, the email can still be delayed, rejected by the destination server, placed in spam, blocked by policy, or reported by the provider via asynchronous events.

This becomes more complex with **multiple providers**: each system has different terminology, statuses, APIs, webhooks, suppression mechanisms, domain configurations, and reporting granularity. Provider A may call an event `processed`, provider B uses `accepted`, and provider C only has SMTP replies. A dashboard that sums statuses without unifying definitions can report an impressive delivery rate while messages are actually still `deferred` or bouncing.

This lesson builds an approach for **multi-provider deliverability monitoring** in Spring Framework Mail: distinguishing submission, acceptance, delivery, and engagement; normalizing events; correlating each notification with a provider message ID and recipient; receiving webhooks safely; handling duplicates/out-of-order events; computing metrics with explicit denominators; reconciling missing events; and using that information to govern routing, retries, failover, and sending quality.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why `JavaMailSender.send(...)` cannot by itself confirm that an email reached the Inbox.
2. Distinguish events from the **application**, **SMTP transport**, **email provider**, **destination mailbox**, and **user**.
3. Recognize differences in event taxonomy across providers without hard-coding dependencies on a single product's labels.
4. Model sending state by **notification**, **attempt**, **provider**, and **recipient**.
5. Build a normalized event model and per-provider adapters.
6. Process webhooks safely, idempotently, durably across crashes, and tolerantly of out-of-order events.
7. Measure delivered/bounced/deferred/complaint rates with clearly defined denominators, scopes, and time windows.
8. Distinguish missing observability data from actual delivery failure.
9. Investigate deliverability discrepancies by provider, recipient domain, email type, and time.
10. Choose retry/failover strategies that avoid duplicate emails, respect suppression, and protect sending reputation.

## 2. Where Spring Framework Mail Sits in the Email Sending Chain

`JavaMailSender` is Spring Mail's abstraction for applications to submit email messages. When using `JavaMailSenderImpl` with SMTP, a call typically passes through these stages:

```text
Business service
      |
      v
Notification/Outbox (PENDING)
      |
      v
MimeMessage + JavaMailSender
      |
      v
SMTP provider A / B / C
      |
      +-- Local acceptance / queue
      |
      v
Receiving mail server (remote MTA)
      |
      +-- Accepted / delayed / rejected
      |
      v
Mailbox filters / spam placement
      |
      v
Mail client / user interaction
```

Each layer answers a different question:

| Layer | Question It Can Answer | Source of Evidence |
| --- | --- | --- |
| Application | Was the send request recorded and processed? | Notification/outbox record |
| SMTP submission | Did the first mail server respond accepting the submission operation? | `JavaMailSender` and transport exceptions |
| Provider processing | Did the provider queue, delay, or reject it? | Provider events/API/logs |
| Remote delivery | Did the destination mail server accept the message? | Provider delivery event |
| Mailbox placement | Did the message land in Inbox, Promotions, spam, or get filtered by a rule? | Seed tests, mailbox signals, specialized tools |
| Engagement | Did the recipient open/click/interact with it? | Tracking events with measurement limitations |

**Do not collapse these six layers into a single `sent=true` flag.** Such a flag cannot express an email that was submitted but is still retrying, an email that bounced after provider acceptance, or a message accepted by the destination server that never appeared in the Inbox.

## 3. Terms to Distinguish

### 3.1. Submitted

In a Spring SMTP context, `SUBMITTED` should mean **the send attempt was confirmed complete by the SMTP transport based on the evidence it observed**. Typically, returning without an exception from `JavaMailSender.send(...)` for a message allows the application to record the submission result for that attempt.

However, that result does not guarantee final delivery, says nothing about Inbox placement, and may not yet include a provider message ID.

### 3.2. Accepted or processed

Many providers emit a status or event indicating they **received the send request and are processing/queuing it**. Exact event names and conditions vary by provider: never treat every `accepted`, `processed`, or `queued` event as equivalent to remote `delivered`.

### 3.3. Delivered

In many email services, `delivered` means the provider handed off the message to or received an acceptance response from the **destination mail server**. This is stronger evidence than `submitted`, yet still **does not prove the user saw the email in their Inbox**.

A message can still be routed to spam or another folder after SMTP acceptance.

### 3.4. Deferred or delayed

Some events indicate the provider could not deliver immediately but may still retry on its own schedule. `DEFERRED` is not always a terminal failure, nor does it mean the application should send another copy.

### 3.5. Bounce

`Bounce` typically indicates an unsuccessful delivery attempt, which may relate to a nonexistent mailbox, domain/policy rules, temporary resources, or other causes. Distinguish hard/soft bounces according to provider definitions and SMTP evidence rather than just a text string.

### 3.6. Complaint

A complaint typically relates to a signal that the recipient marked a message as spam or to a mailbox/provider feedback loop. It affects sending reputation and suppression. Complaint rate should be observed per policy/provider with a consistent denominator.

### 3.7. Rejected, dropped, suppressed

A provider may reject or drop a message **before attempting delivery to the destination server**, for example due to a suppression list, content policy, account status, or quota. Do not label this a remote bounce if no corresponding delivery attempt occurred.

## 4. State Map from Business to Provider

An observability model:

```text
PENDING
   |
   v
PROCESSING
   |
   +---- build/validation error ---> PREPARATION_FAILED
   |
   +---- SMTP known failure ------> RETRY_WAIT / FAILED
   |
   +---- SMTP outcome uncertain --> UNKNOWN
   |
   v
SUBMITTED
   |
   +---- provider accepted/queued --> PROVIDER_ACCEPTED
   |
   +---- delayed ------------------> DEFERRED
   |                                   |
   |                                   +--> DELIVERED_REMOTE
   |                                   +--> BOUNCED
   |
   +---- delivered ----------------> DELIVERED_REMOTE
   |
   +---- rejected/dropped ---------> REJECTED / SUPPRESSED
   |
   +---- bounce -------------------> BOUNCED
   |
   +---- complaint ---------------> COMPLAINED
```

The diagram intentionally does **not** represent a rigid linear state machine. A provider may emit a delivered event and later emit complaint signals; other events may arrive at the webhook **late, duplicated, or out of order**.

Therefore, in a multi-provider system, store an **immutable event ledger** alongside aggregated status rather than using a single status column overwritten in webhook arrival order.

## 5. Why Do Event Names Differ Across Providers?

Email providers may offer different feedback channels:

- **SMTP relay:** direct reply at submission time, sometimes plus DSN/bounce mailbox.
- **HTTP Email API:** response includes request/message ID and status query capability.
- **Event webhook:** HTTP callbacks for accepted, delivered, bounce, complaint, unsubscribe, or engagement.
- **Message event API/log search:** lookup by message ID, account, tag, or time range.
- **Notification bus:** publishes events to a topic/queue you integrate with.
- **Bounce mailbox:** sends DSNs to a return-path or bounce-handling address.

They also use different labels. For instance, when reading documentation for Amazon SES, SendGrid, Mailgun, or Postmark, you may encounter groups like **send/delivery/bounce/complaint**, **processed/delivered/deferred/dropped**, **accepted/delivered/failed**, or **delivery/bounce/spam complaint**. These are only **illustrative examples**, not an official event list or immutable contract for any product.

**Always read the documentation for the exact API, account configuration, and provider version you are integrating** before mapping labels. Never write code assuming all providers share the same event names, payload schemas, granularity, or definition of `delivered`.

## 6. Capability-Level Comparison Table, Not Coupled to a Single API

| Capability | Standard SMTP Relay | Provider with Event Webhooks | Provider with HTTP API + Event Log |
| --- | --- | --- | --- |
| Submission confirmation at send time | Usually via SMTP reply | Possibly via SMTP/API response | Yes via API response |
| Provider-specific message ID | Not always available or returned via SMTP | Integration-dependent | Often has query/correlation support |
| Delivered event | Not by default | Depends on configuration/event subscription | API-dependent |
| Bounce/complaint feedback | DSN/mailbox, or unavailable | May support webhooks | May support logs and callbacks |
| Suppression information | Relay-dependent | Provider/account-dependent | Provider/account-dependent |
| Historical lookup | Depends on logs and retention | Webhooks stored by the application | Query API may be available |
| Reconciliation after downtime | Difficult without logs | Requires replay/query if supported | Easier with a query API |
| Delivery to Inbox | Cannot be inferred from SMTP alone | Delivered webhooks usually do not confirm Inbox | Delivered API usually does not confirm Inbox |

This table compares **capability tiers** rather than scoring specific brands. The same provider can support very different capabilities across SMTP, REST API, sandbox, deployment regions, and service plans.

## 7. "Deliverability" Must Have a Measurable Definition

In practice, the word deliverability is used for at least three questions:

1. **Submission success:** how reliably does the application hand messages off to the provider?
2. **Remote delivery:** how many recipients were confirmed by the provider as handed off to the destination mail server?
3. **Inbox placement:** how many messages actually appear in the Inbox rather than spam/Promotions/other folders?

The third metric **cannot be determined accurately from normal delivered events**. Inbox placement requires mailbox/seed testing or authorized supplementary data; and even with a seed list, results are only a sample.

Do not label a dashboard chart "Inbox delivery rate" when the formula calculates `delivered_count / submitted_count` from webhooks. A more accurate name is typically "provider-reported remote delivery rate".

## 8. Measurement Scope: Per Message or Per Recipient?

One message can have multiple recipients:

```text
MimeMessage X
  To: a@example.net
  Cc: b@example.net
  Bcc: c@example.net
       |
       v
SMTP RCPT TO A / B / C
       |
       v
Provider deliverability events per recipient
```

If you only store `message.status=DELIVERED`, you lose visibility when A was accepted by the remote MTA, B bounced, and C was deferred.

**The most important unit of observation for deliverability is usually one notification/recipient on one attempt/provider.** You can keep a shared message for multiple recipients, but event correlation must be designed at the right granularity.

| Metric | Unit to Declare |
| --- | --- |
| Message submission | Message attempt |
| Provider send event | Provider event or message attempt |
| Remote delivered | Recipient delivery outcome |
| Bounce | Recipient delivery outcome |
| Complaint | Recipient feedback/event |
| Retry | Notification/recipient attempt |
| Unique notification sent | Notification ID |

If a provider only emits message-level aggregate events, do not infer that separate per-recipient outcomes exist for every recipient.

## 9. Data Structures to Track

A multi-provider system should separate four ID types:

| ID | Created By | Purpose |
| --- | --- | --- |
| `notificationId` | Application | Durable identifier for the send intent |
| `attemptId` | Application | A specific submission attempt, possibly using a different provider |
| `providerMessageId` | Provider (when available) | Correlating events or API lookups |
| `providerEventId` | Provider (when available) | Deduplicating webhooks/events |

You also need an internal `recipientId` to distinguish outcomes per recipient, and `providerKey` to know which route was used.

### Why Are Both notificationId and attemptId Needed?

```text
Notification N-100
  |
  +-- Attempt A-1: Provider A, SMTP timeout -> UNKNOWN
  |
  +-- Attempt A-2: Provider B, accepted -> SUBMITTED
  |
  +-- Late event from Provider A: delivered
  |
  +-- Event from Provider B: delivered
```

If you only have one `notificationId` and overwrite the current `provider`, a late event from Provider A could be misattributed to attempt B, skewing dashboard counts and masking a **duplicate send incident across two providers**.

**An event must be tied to the exact provider + attempt + recipient**, or marked uncorrelated for investigation—never guessed by subject/body.

## 10. Data That Should Not Be Used as a Unique Key

The fields below can be helpful for tracing, but should not be treated as global unique keys:

- `MimeMessage.getMessageID()`: Message-ID may be generated or rewritten by a library or relay and is not guaranteed unique across all dimensions.
- `To`/`Cc`/`Bcc`: a recipient can receive multiple identical notifications.
- `Subject`: many emails share a subject, and it can contain personal data.
- Timestamp: multiple events can occur at the same instant with different precision/clocks.
- Provider event type: a message can be deferred multiple times.
- **Un-namespaced** provider message ID: may only be unique within one provider/account/region.

Durable correlation keys should be namespaced:

```text
providerKey + account/region scope + providerMessageId
                                    |
                                    v
                             attemptId
                                    |
                                    v
                       notificationId + recipientId
```

If SMTP does not return a provider message ID, store the evidence you **actually have**, such as the application attempt ID and send timestamp. You can attach provider-supported custom metadata/headers where permitted, but do not assume every provider echoes custom headers back in delivery events.

## 11. Storage Model Separating Notification, Attempt, and Event

A reference design:

```text
mail_notification
  notification_id (PK)
  message_type / template_version
  recipient_id / created_at
          |
          | 1 -> N
          v
mail_attempt
  attempt_id (PK)
  notification_id (FK)
  provider_key / provider_scope
  submission_outcome / provider_message_id
          |
  | 1 -> N (when correlation is established)
          v
mail_delivery_event
  ingest_id (PK)
  provider_key / provider_scope
  event_dedupe_key
  provider_event_type / canonical_event_type
  attempt_id / recipient_id
  occurred_at / received_at
```

Three tables serve three distinct purposes:

- **Notification** records the send intent and exists independently of providers.
- **Attempt** records each application submission try and the provider chosen at that time.
- **Delivery event** records asynchronous feedback data, including late-arriving information.

You can add a `mail_recipient_outcome` table as a current-state **projection** per recipient, but the projection never replaces the event history.

### Illustrative PostgreSQL Schema

```sql
CREATE TABLE mail_notification (
    notification_id UUID PRIMARY KEY,
    recipient_id UUID NOT NULL,
    message_type VARCHAR(80) NOT NULL,
    template_version VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE mail_attempt (
    attempt_id UUID PRIMARY KEY,
    notification_id UUID NOT NULL
        REFERENCES mail_notification(notification_id),
    provider_key VARCHAR(60) NOT NULL,
    provider_scope VARCHAR(100) NOT NULL,
    provider_message_id VARCHAR(300),
    submission_outcome VARCHAR(40) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    failure_category VARCHAR(60)
);

CREATE INDEX ix_mail_attempt_provider_message
    ON mail_attempt(
        provider_key, provider_scope, provider_message_id
    );

CREATE TABLE mail_delivery_event (
    ingest_id UUID PRIMARY KEY,
    provider_key VARCHAR(60) NOT NULL,
    provider_scope VARCHAR(100) NOT NULL,
    event_dedupe_key VARCHAR(300) NOT NULL,
    attempt_id UUID NULL REFERENCES mail_attempt(attempt_id),
    recipient_id UUID NULL,
    provider_message_id VARCHAR(300),
    provider_event_type VARCHAR(120) NOT NULL,
    canonical_event_type VARCHAR(60) NOT NULL,
    occurred_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    correlation_state VARCHAR(40) NOT NULL,
    UNIQUE (
        provider_key, provider_scope, event_dedupe_key
    )
);
```

This is a **teaching schema** and omits production indexes, partitioning, migrations, and security policies. `event_dedupe_key` must be constructed by the adapter according to **each provider's uniqueness contract**; never assume every webhook includes a globally unique `id` field.

`recipient_id` can be `NULL` in the event inbox when not yet mapped; keep the event in `UNMATCHED` state to retry correlation later rather than attributing it to the wrong recipient.

### Do Not Store Entire Payloads in Main Tables Unless Needed

Webhooks sometimes contain email addresses, diagnostic strings, IPs, or account details. If you must retain raw payloads for investigation:

- Consider a separate encrypted store with a short TTL.
- Attach a reference or authorized hash/HMAC to the record.
- Restrict access permissions and audit reads.
- Never expose raw payloads in general dashboards/logs.
- Comply with applicable data retention and deletion policies.

## 12. Event Normalization: Keeping Both Canonical and Raw Types

A normalized enum might include:

```java
public enum CanonicalMailEventType {
    PROVIDER_ACCEPTED,
    DEFERRED,
    DELIVERED_REMOTE,
    BOUNCED,
    COMPLAINED,
    PROVIDER_REJECTED,
    SUPPRESSED,
    UNSUBSCRIBED,
    OPENED,
    CLICKED,
    UNKNOWN
}
```

**Not every provider has to support every type.** `UNKNOWN` is for unmapped events or insufficient evidence; never silently drop a new event and report everything as normal.

Alongside the canonical type, keep:

- `providerKey`: the provider that sent the event.
- `providerScope`: account/subaccount/region or route namespace.
- `providerEventType`: original event name.
- `eventDedupeKey`: normalized scoped deduplication key.
- `providerMessageId`: if present.
- `attemptId` and `recipientId`: after correlation, if evidence exists.
- `occurredAt`: when the provider says the event occurred, if available.
- `receivedAt`: when the system received it.
- `failureCategory`: bounce, suppression, or policy category, if parseable.
- `providerDiagnosticCode`: controlled code, avoiding raw PII storage.

### Java DTO for the Normalization Layer

```java
import java.time.Instant;
import java.util.UUID;

public record NormalizedMailEvent(
        String providerKey,
        String providerScope,
        String eventDedupeKey,
        String providerEventType,
        CanonicalMailEventType canonicalType,
        String providerMessageId,
        UUID attemptId,
        UUID recipientId,
        Instant occurredAt,
        Instant receivedAt,
        String failureCategory
) {}
```

In a real design, add schema version, channel, event actor/source, confidence, and whether an event is message-level or per-recipient if the provider supports it. Never force a non-null `recipientId` by searching subjects or fuzzy-matching email addresses in the database.

## 13. Mapping Is a Versioned Contract

A mapping table can start like this:

| Provider Event Meaning | Canonical Type | What to Verify Before Mapping |
| --- | --- | --- |
| Provider accepted the request | `PROVIDER_ACCEPTED` | Accepted into account/queue or by the remote server? |
| Provider delayed/retrying | `DEFERRED` | Will it continue retrying? |
| Remote MTA accepted the message | `DELIVERED_REMOTE` | At which stage is delivered defined? |
| Delivery failed | `BOUNCED` | Is this final or temporary? |
| Recipient reported spam | `COMPLAINED` | Which recipient did the signal originate from? |
| Provider rejected before delivery | `PROVIDER_REJECTED` | Rejected or bounced? |
| Suppression policy blocked sending | `SUPPRESSED` | Global, account, or domain suppression? |
| User unsubscribed | `UNSUBSCRIBED` | Which mail types does it apply to? |
| Open/click tracking | `OPENED` / `CLICKED` | Is tracking enabled, and how does privacy affect it? |

Keep mappings in adapters or version-controlled config instead of scattering `if` chains on event names inside business services.

### Do Not Collapse All Negative Events into BOUNCED

For example, "dropped because suppressed" may mean the provider never attempted delivery to the remote MTA. Collapsing it into `BOUNCED` inflates bounce metrics when the real cause is suppression or policy.

Conversely, dropping unmappable negative events can cause dashboards to count only delivered messages and miss pipeline dropouts.

## 14. Per-Provider Adapters

The architecture should place provider differences at the system edge:

```text
Provider A callback ---+
                       |
Provider B callback ---+--> Verify + Parse + Normalize
                       |             |
Provider C callback ---+             v
                                Event Inbox
                                      |
                                      v
                               Correlate/Dedup
                                      |
                                      v
                             Projection + Metrics
```

An illustrative interface:

```java
public interface ProviderWebhookAdapter {

    String providerKey();

    VerifiedProviderPayload verify(
            byte[] rawPayload,
            Map<String, List<String>> headers
    );

    List<NormalizedMailEvent> normalize(
            VerifiedProviderPayload verifiedPayload
    );
}

public record VerifiedProviderPayload(
        String providerKey,
        byte[] originalBytes
) {}
```

This is an **application-defined API**, not a built-in Spring Mail API. Real implementations may combine the two steps or discard the raw byte array after parsing; the key point is **verifying before trusting data, and mapping per provider**.

Each adapter is responsible for:

- Verifying the callback belongs to the configured provider/account.
- Verifying signatures/tokens/auth mechanisms per provider documentation.
- Parsing events according to the specific schema and version.
- Constructing scoped deduplication keys with accurate semantics.
- Normalizing timestamps, event types, and error codes.
- Extracting correlation metadata guaranteed by the provider.
- Never logging secrets or raw payloads.

A new adapter can be added without forcing the business layer to learn new vendor event names.

## 15. JavaMailSender Does Not Automatically Create Event Listeners for Every Provider

In Spring Mail:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message, false, "UTF-8"
);

helper.setFrom("notice@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Request confirmation");
helper.setText("Test notification.");

mailSender.send(message);
```

This code **only performs submission**. Spring does not automatically emit "delivered/bounced/complained" callbacks for all SMTP providers.

If follow-up telemetry is needed:

1. Configure the provider's event publication mechanism (webhook, topic/queue, API, or DSN mailbox).
2. Ensure the provider/account/domain actually has permissions and the required event types enabled.
3. Attach correlation `attemptId` or provider-supported metadata.
4. Deploy a receiver and event store outside `JavaMailSender`.
5. Define retention and reconciliation when events do not arrive.

If a provider only supports SMTP replies and provides no delivery feedback, the dashboard should display **"no delivery signal available"** rather than treating `SUBMITTED` as delivered.

## 16. Provider Message IDs and Custom Headers

To correlate an event back to an attempt, options may include:

- Provider API returns a message/request ID.
- Provider allows custom arguments/tags/metadata and echoes them in events.
- Provider exposes a message ID via an SMTP extension/header or searchable logs.
- Application stores the MIME `Message-ID` and searches via provider tools if supported.
- Another system ingests inbound DSNs and links via authorized fields.

**No universal solution is guaranteed to work across every SMTP provider.** In particular, an SMTP `250 queued` reply may not expose a machine-readable message ID under a stable contract.

### Example Application-Set Header

```java
message.setHeader(
        "X-App-Attempt-Id",
        attemptId.toString()
);
```

A header like this can be useful in some setups or when investigating test messages. However:

- It can appear in the email delivered to the recipient; never put PII or secrets in its value.
- A provider may strip, rewrite, or fail to echo the header in events.
- It is not an official correlation interface for every provider.
- Message-ID/headers can change during forwarding or relaying.
- Setting a header does not make SMTP idempotent.

When a provider offers an official metadata mechanism, prefer that mechanism and test that metadata **actually comes back** in events.

## 17. SMTP Provider Routing Must Persist the Decision Before Sending

Consider a system with three routes:

```text
Transactional -> Provider A
Bulk campaign -> Provider B
Fallback      -> Provider C (only when permitted)
```

`ProviderRouter` can select a provider based on:

- Email type and SLA.
- Country/region or data residency requirements.
- Authorized tenant/account.
- Quota, throttling, and route health.
- Warm-up/capacity and sending domain reputation.
- Cost and required capabilities (webhooks, suppression, template metadata).

The routing decision must be persisted in `mail_attempt`:

```text
attemptId = A-1001
notificationId = N-500
providerKey = provider-a
providerScope = transactional-prod
routingReason = primary-transactional
startedAt = ...
```

When an event arrives hours later, the system must know **which attempt** it belongs to without inferring from whichever provider happens to be active when the webhook arrives.

## 18. Webhooks Are Asynchronous Data Sources, Not Synchronous Send Callbacks

A common flow:

```text
JavaMailSender.send(message)
        |
        +---- SMTP accepted ---> mark attempt SUBMITTED
        |
        v
Application returns result to caller

(seconds/minutes/hours later)

Provider event sender
        |
        v
HTTPS POST /webhooks/mail/provider-a
        |
        v
Verify authenticity + request limits
        |
        v
Persist durable event inbox
        |
        v
Return HTTP 2xx
        |
        v
Async correlate / normalize / project
        |
        v
Deliverability dashboard + remediation
```

Webhooks **can** be delivered more than once, delayed, or out of order. In some systems, providers retry callbacks when the endpoint does not acknowledge success; retry timing and counts vary. Receivers must be designed for **at-least-once delivery whenever possible**, never assuming exactly-once.

### Do Not Block Webhooks by Sending Other Emails

Inside the HTTP webhook handler, avoid:

1. Querying hundreds of tables.
2. Generating a new batch of emails.
3. Calling provider APIs repeatedly.
4. Waiting for an SMTP sender to send a new notification.
5. Only returning HTTP `200` afterward.

A secondary SMTP failure would cause the provider to retry the webhook, creating duplicates and bottlenecks. Instead, verify, durably persist the event, acknowledge, and run business processing in an independent worker.

## 19. Webhook Verification Must Match the Exact Provider

Never trust a payload merely because the request hit `/webhooks/mail/provider-a` or carried `X-Provider: A`. Anyone on the public Internet can send HTTP requests to that endpoint.

Depending on the provider, verification mechanisms may include:

- HMAC signature over payload and timestamp.
- Asymmetric signature using a provider-supplied public key.
- Endpoint token or credentials.
- Message-bus notifications with IAM and dedicated signatures.
- Subscription/URL confirmation workflow before receiving events.

**No single signature formula works across all providers.** Follow canonicalization, algorithms, headers, key rotation, and timestamp tolerance exactly per the specific provider's documentation.

### Verification Principles

1. Use HTTPS and sensible network access restrictions.
2. Verify signatures/tokens on **raw bytes** before modifying JSON.
3. Do not reserialize JSON with altered whitespace/key order before verifying signatures if the provider signs raw bytes.
4. If the auth protocol includes timestamp/tolerance checks, apply them strictly to limit replay.
5. Scope keys per provider/account/scope and support key rotation.
6. Use constant-time comparison for MACs when the provider uses MACs and docs require it.
7. Bound request body size, event batch item count, and request rate.
8. Do not rely on IP allowlists as sole proof when the provider offers verifiable signatures.
9. Process content only after authentication and schema validation.
10. Record metrics for invalid signatures without logging raw secrets or full payloads.

If events arrive via an IAM-protected queue/topic, authenticating the source and publish/subscribe permissions at the message bus remains mandatory in the trust model.

## 20. Spring Boot Webhook Controller Example

This is an **integration skeleton** for a provider posting JSON webhooks over HTTP; it is not a drop-in endpoint for every provider. `ProviderWebhookAdapter` is implemented per each provider's documentation.

```java
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/webhooks/mail")
public class MailProviderWebhookController {

    private final ProviderWebhookRegistry registry;
    private final DeliveryEventInbox inbox;

    public MailProviderWebhookController(
            ProviderWebhookRegistry registry,
            DeliveryEventInbox inbox
    ) {
        this.registry = registry;
        this.inbox = inbox;
    }

    @PostMapping(
            path = "/{provider}",
            consumes = "application/json"
    )
    public ResponseEntity<Void> receive(
            @PathVariable String provider,
            @RequestHeader HttpHeaders headers,
            @RequestBody byte[] rawBody
    ) {
        ProviderWebhookAdapter adapter =
                registry.require(provider);

        VerifiedProviderPayload verified =
                adapter.verify(rawBody, headers);

        List<NormalizedMailEvent> events =
                adapter.normalize(verified);

        // Persist durably and idempotently before returning 2xx.
        // A separate worker will handle projection/metrics.
        inbox.persist(events);

        return ResponseEntity.noContent().build();
    }
}
```

`ProviderWebhookRegistry` and `DeliveryEventInbox` are application-implemented abstractions. `verify(...)` must throw a dedicated auth exception on invalid signatures. The global exception handler/security layer should respond appropriately—such as `401/403` for authentication failures and `400` for malformed payloads—rather than turning every error into `200`.

### Limitations of This Controller Skeleton

- Only handles `application/json` as an example; a provider may send form-encoded data, queue messages, or another envelope.
- Must enforce a **request body size limit before loading the full body into memory**.
- Must bound batch event counts and parser depth.
- Endpoints need short timeouts, autoscaling/rate limits, and durable ingestion.
- If the database/event inbox experiences a transient failure, do not report false success; return an HTTP response that lets the provider retry per its contract.
- Some providers require subscription handshakes or challenges; adapters and endpoints must support them.

Never return `2xx` and only start persisting the event on an unguaranteed background thread: the process could crash right after HTTP acknowledgment and permanently lose the feedback.

## 21. Why Have a Durable Event Inbox?

An event inbox decouples provider callback rate from internal processing speed:

```text
Provider HTTP request
       |
       v
Signature verification
       |
       v
Insert event inbox (transaction)
       |
       +-- Duplicate event -> no-op, ack
       |
       +-- New event -> stored, ack
       |
       v
Background projector
       |
       +-- correlate attempt/recipient
       +-- normalize outcome
       +-- update recipient projection
       +-- emit metrics/audit
```

Benefits:

- Tolerates duplicate incoming events.
- Preserves events across restarts.
- Allows retrying projection if another database or downstream service fails.
- Retains unmatched events for later reconciliation.
- Enables auditing raw types and mapping versions.
- Avoids forcing the provider to wait on lengthy business processing.

To handle worker concurrency, inbox consumers need claim/lease or appropriate message queue acknowledgment. If using a database queue, keep transactions and row locks short with proper isolation.

## 22. Deduplicating Events in the Right Scope

A webhook may carry an event ID, yet not every provider guarantees unique IDs at the event level. A batch can contain multiple recipients or multiple statuses sharing a message ID.

Principles:

1. Prefer the **provider event ID** if the provider's contract guarantees stability across retries.
2. Namespace by provider/account/region or event source.
3. Verify whether event IDs are unique per **message**, **recipient**, **event**, or only within a time window.
4. If building a key from composite fields, document potential collision risks.
5. Never use `providerMessageId` alone as the event key: one message has multiple events.
6. Never use `timestamp` alone: multiple events can share timestamps or clock precision.
7. Never use body text or recipient email as keys to avoid PII exposure and ambiguous matching.

### Idempotent Insert Example

```sql
INSERT INTO mail_delivery_event (
    ingest_id,
    provider_key,
    provider_scope,
    event_dedupe_key,
    attempt_id,
    recipient_id,
    provider_message_id,
    provider_event_type,
    canonical_event_type,
    occurred_at,
    received_at,
    correlation_state
)
VALUES (
    :ingestId,
    :providerKey,
    :providerScope,
    :dedupeKey,
    :attemptId,
    :recipientId,
    :providerMessageId,
    :providerEventType,
    :canonicalType,
    :occurredAt,
    now(),
    :correlationState
)
ON CONFLICT (
    provider_key, provider_scope, event_dedupe_key
)
DO NOTHING;
```

This PostgreSQL example relies on the unique constraint from the earlier schema. For providers without stable event IDs, adapters must build appropriate dedupe keys; **perfect distinction of every duplicate event is not guaranteed**.

### Why Hashing the Raw Payload May Not Suffice

A raw JSON hash can change when a provider resends an event with different property ordering or envelope metadata. Conversely, two distinct events can have identical bodies, particularly periodic temporary deferrals.

When fingerprinting is required, base it on provider-guaranteed meaningful fields—scope, message, recipient, event type, and a reliable sequence/event timestamp. Where confidence is insufficient, document incomplete deduplication rather than claiming "exactly-once event ingestion".

## 23. Events Can Arrive Out of Order

Example:

```text
Actual at provider:
  10:00:00 ACCEPTED
  10:00:03 DEFERRED
  10:00:28 DELIVERED

Webhook arrivals at application:
  10:00:29 DELIVERED
  10:00:31 ACCEPTED
  10:00:33 DEFERRED
```

If handled via:

```java
notification.setStatus(event.canonicalType().name());
```

the final status could be recorded as `DEFERRED` even though the provider already reported delivery.

### Handling Out-of-Order Events Safely

- Append every valid event to the ledger.
- Use `occurredAt` as signal, though not absolute truth if provider/clock guarantees are weak.
- Identify terminal outcomes based on **per-provider rules** and attempt context.
- Keep `receivedAt` to measure event delay and debug issues.
- Never let a late `PROVIDER_ACCEPTED` event erase an already observed delivery.
- If events conflict, flag `CONFLICT/NEEDS_RECONCILIATION` rather than arbitrarily deleting evidence.

A `COMPLAINED` event arriving **after** `DELIVERED_REMOTE` is not necessarily a conflict; delivery and complaint belong to **different observation dimensions**.

## 24. Do Not Use a Single Enum Order to Decide Every State

Wrong example:

```java
if (incoming.ordinal() > current.ordinal()) {
    current = incoming;
}
```

Enum ordinals reflect source code declaration order, not temporal or business models.

A reasonable projection separates:

```text
submission_state:
  PENDING | SUBMITTED | FAILED | UNKNOWN

delivery_state:
  NOT_OBSERVED | QUEUED | DEFERRED |
  DELIVERED_REMOTE | BOUNCED | REJECTED |
  UNRESOLVED

feedback_state:
  NONE | COMPLAINED | UNSUBSCRIBED

engagement_state:
  NOT_MEASURED | OPEN_OBSERVED | CLICK_OBSERVED
```

As a result:

- A message can be both `DELIVERED_REMOTE` and `COMPLAINED`.
- A message can be delivered while engagement remains `NOT_MEASURED`.
- Seeing no webhook does not automatically mean `BOUNCED`.
- An `UNKNOWN` submission outcome can be clarified by late-arriving provider evidence.

Each provider adapter can attach vendor-specific details, while the shared projection avoids lossy overwrites of past facts.

## 25. UNMATCHED State Is Not Garbage Data

A webhook can arrive before the `providerMessageId -> attemptId` mapping is committed or returned in the API response. Or a provider may omit a metadata field you assumed was always present.

```text
Webhook DELIVERED
   providerMessageId = X
   recipient metadata available
             |
             v
No matching attempt yet
             |
             v
Persist event as UNMATCHED
             |
             v
Async reconciliation later
```

Do not discard an event simply because it does not match immediately. You can:

- Retry correlation after a short delay.
- Look up by namespaced provider/scope/message ID.
- Use an application-attached ID if the provider genuinely echoes it by contract.
- Route to a queue/manual review if insufficient data exists.
- Measure `unmatched_event_count` and unmatched event age.

However, do not match events by "recipient email + subject + nearby timestamp" if it could misattribute identical-content notifications. If fallback matching is ever necessary, require confidence thresholds, tight scoping, and auditing.

## 26. Never Assume Webhooks Always Arrive

A callback may fail to appear because:

- The subscription did not enable the right event types.
- The endpoint had temporary downtime or TLS/certificate/routing errors.
- The provider stopped retrying after its retry window.
- Callbacks were blocked by rate limits or body limits.
- The message took a sending path without configured feedback.
- Delivery feedback does not exist for that SMTP relay type.
- The provider sent the event, but the application failed before persisting it.
- Another account/region was not integrated.
- The provider applies sampling or limited retention.

Therefore, missing events are an **observability gap**, not automatically a bounce or a successful delivery. Dashboards must track both **event coverage** and **delivery outcomes**.

## 27. Reconciliation When Events Are Lost or Delayed

A reconciliation flow:

```text
Attempt SUBMITTED > configured age threshold
                |
                v
No terminal delivery evidence
                |
                +--> Provider has query API?
                |       |
                |       +--> Query by supported IDs/scope
                |       +--> Normalize returned evidence
                |       +--> Persist as source-labeled observation
                |
                +--> DSN/bounce mailbox supported?
                |       |
                |       +--> Parse trusted feedback safely
                |
                +--> No evidence available?
                        |
                        +--> Mark as STALE_UNOBSERVED
                        +--> Alert only per business SLA
```

Not every provider supports querying by message ID or replaying webhooks; you may need to mark data unavailable after a threshold. Even after an hour, **`STALE_UNOBSERVED` does not mean FAILED**.

If using API reconciliation, ensure:

- Dedicated rate limits and backoff.
- Least-privilege token scopes and rotation.
- Batching aligned with API capabilities.
- Not polling past-retention messages indefinitely.
- Tagging observations with `source=RECONCILIATION_API` rather than masquerading as original webhooks.
- Idempotency between query results and real webhooks.

## 28. The Denominator Defines What Delivery Rate Means

A dashboard easily misleads when it only shows:

```text
delivered_count / sent_count
```

Two unanswered questions:

- Does `delivered_count` count **events** or **unique recipient-attempts**?
- Does `sent_count` count send requests, SMTP attempts, provider-accepted items, or observable recipient deliveries?

If a recipient receives two duplicate delivered events, counting both can push the rate above 100%. If a notification retries across two providers, an inconsistent denominator also distorts metrics.

### A Comparable Definition

For a **cohort of provider-accepted recipient-attempts** with sufficient observation time:

\[
\text{Remote delivery rate} =
\frac{\text{Unique recipient-attempts with DELIVERED\_REMOTE evidence}}
{\text{Eligible recipient-attempts in the cohort}}.
\]

Explicitly declare:

1. Whether the cohort is sliced by `submittedAt` or `providerAcceptedAt`.
2. Whether the denominator excludes provider-rejected/suppressed items.
3. Whether the unit is recipient-attempt or unique notification-recipient.
4. How late events update the original cohort.
5. How a multi-recipient attempt is expanded.
6. Whether filters apply for transactional/bulk, tenant, region, or recipient domain.
7. How unmatched or provider-unsupported events are handled.

A formula useful for provider A is **not automatically valid** for provider B if coverage and event semantics differ.

## 29. Event Coverage Is an Independent Metric

If provider A emits rich delivery telemetry while provider B only reports submission, B can appear near 0% delivered **not because emails failed to arrive**, but because the application lacks feedback.

Example metric:

\[
\text{Outcome coverage} =
\frac{\text{Recipient-attempts with at least one meaningful outcome}}
{\text{Observable eligible recipient-attempts}}.
\]

`Outcome` must be defined: e.g., delivered, final bounce, rejected, suppressed, or another terminal state. `opened` events should not substitute for delivery proof.

Also monitor:

- `webhook_ingest_requests_total`: volume of HTTP callbacks.
- `webhook_signature_failure_total`: verification failures.
- `webhook_duplicate_events_total`: deduplicated events.
- `webhook_unmatched_events_total`: events not yet mapped to an attempt.
- `event_processing_lag_seconds`: delay from receipt to projection.
- `provider_event_delay_seconds`: `receivedAt - occurredAt` when both timestamps are trustworthy.
- `stale_unobserved_attempts`: attempts without outcomes beyond the SLA threshold.

A provider with healthy remote delivery can still look like a "deliverability incident" if your application's webhook endpoint breaks on a dashboard that hides coverage.

## 30. Use Mature Cohorts to Avoid Right-Censoring

Imagine looking at a dashboard at 10:05:

```text
10:00 - 10:05: 1,000 messages just submitted
10:05:        600 delivered events have arrived
               400 messages are still being processed by the provider
```

Taking 600/1,000 and concluding "deliverability dropped to 60%" confuses **insufficient delivery time** with **delivery failure**.

A sound approach:

- Group cohorts by `submittedAt`.
- Evaluate only after an appropriate age—e.g., emails submitted at least 1 hour or 24 hours ago depending on SLA.
- Separate `DEFERRED`, `BOUNCED`, `SUPPRESSED`, and `UNOBSERVED`.
- Allow late events to update prior cohort results.
- Retain "as-of time" snapshots if you need to reconstruct what dashboards showed during an incident.

"1 hour/24 hours" are only examples; actual email delivery depends on providers, receiving domains, server load, and retry policies. No single threshold fits all email types.

## 31. Example Comparing Two Providers Under Identical Definitions

Suppose **synthetic** data for two transactional cohorts after 24 hours, classified per unique recipient-attempt:

| Outcome After 24 Hours | Provider A | Provider B |
| --- | ---: | ---: |
| Eligible in cohort | 1,000 | 1,000 |
| `DELIVERED_REMOTE` | 920 | 955 |
| `BOUNCED` | 35 | 20 |
| `DEFERRED` still open | 20 | 10 |
| `PROVIDER_REJECTED` | 10 | 5 |
| `UNOBSERVED` | 15 | 10 |
| Total across groups | 1,000 | 1,000 |

In this **illustrative example**, remote delivered rates are 92.0% and 95.5% under the chosen denominator. Yet you still cannot conclude B is "better for all traffic", because:

- Both providers might serve traffic to different destination domains.
- Providers may differ in retry windows and feedback delays.
- The cohort may be too small for certain subgroups.
- Email content, domain authentication, reputation, or list hygiene may differ.
- An `UNOBSERVED` bucket might reflect missing telemetry rather than bounces.

**Fair comparisons** require identical notification types, recipient eligibility criteria, observation durations, outcome semantics, and controls for traffic mix.

### Do Not Simply Sum All Events

The table above intentionally uses **mutually exclusive snapshot states** per recipient-attempt. In a real event ledger, one recipient may have `DEFERRED`, then `DELIVERED_REMOTE`, and later `COMPLAINED`. Summing raw events instead of building a projection can exceed the attempt count.

## 32. Rates to Calculate Separately

| Metric | One Way to Define It | Notes |
| --- | --- | --- |
| Submission success rate | Successful SMTP/API attempts / attempted tries | Not delivery |
| Provider acceptance rate | Provider-accepted recipient attempts / attempted recipient submissions | Requires provider accepted event or response |
| Remote delivery rate | Unique delivered recipients / eligible recipient attempts in mature cohort | Depends on event coverage |
| Final bounce rate | Unique bounced recipient attempts / eligible recipient attempts | Definition of final must be consistent |
| Temporary deferral rate | Unique attempts with a deferral / eligible attempts | Can overlap with eventual delivery |
| Suppression rate | Unique suppressed recipients / attempted recipients | Separate compliance/policy |
| Complaint rate | Unique complaints / clearly defined denominator | Differs across providers and feedback loops |
| Webhook coverage rate | Attempts with outcome feedback / eligible attempts | Measures observability |
| Unknown submission rate | Attempts with ambiguous SMTP outcome / attempted tries | Measures retry/duplicate risk |

Some rates like "ever deferred" are **not mutually exclusive** with "eventually delivered"; dashboards must clearly note when one recipient contributes to multiple metrics.

### Complaint Rate Is Especially Sensitive to the Denominator

Some systems divide complaints by delivered, others by accepted, or follow provider-specific definitions. When comparing:

- Do not mix two denominators.
- Record event timestamps and cohorts.
- Distinguish complaint event count from unique complaining recipients.
- Account for feedback sources not covering every mailbox provider.

Never compare an internal rate against a public reputation threshold unless the formula matches how that provider computes it.

## 33. Delivery Time Matters as Much as Delivery Success Rate

For OTPs, password resets, or security alerts, an email delivered 30 minutes later may be useless even if the provider reports `DELIVERED_REMOTE`.

You can measure:

\[
\text{Delivery latency} =
\text{provider delivery occurredAt}
- \text{submission started/acceptedAt}.
\]

Timestamp definitions must stay consistent:

- `submissionStartedAt`: when the application started the attempt.
- `providerAcceptedAt`: when the provider confirmed acceptance (if available).
- `deliveredAt`: when the provider reported remote acceptance.
- `receivedAt`: when the webhook reached the application.

**Never unconditionally treat webhook `receivedAt` as `deliveredAt`.** If an event sat in a queue for two hours before arriving, latency computed from `receivedAt` measures webhook lag rather than delivery speed.

Dashboards should display p50/p95/p99 delivery latency alongside:

- A mature cohort.
- Observation count.
- Missing timestamp rate.
- Clear separation between event-time and ingest-time.
- Provider/recipient-domain/traffic-class segmentation.

Measuring latency only among delivered items creates **survivorship bias**. A provider with 10% permanently stuck messages might show a great p95 across the remaining 90%; always view latency **together with** delivered and unobserved rates.

## 34. Recipient Domain Can Matter More Than Overall Provider

Suppose:

```text
Provider A: traffic mostly to domain X
Provider B: traffic mostly to domain Y
```

If domain X has many nonexistent mailboxes or aggressive throttling, A may show higher bounce/deferral rates even when route quality between both providers is identical for the same domain.

Segment by:

- Provider and provider account/scope.
- Recipient domain group (with bounded cardinality).
- Transactional vs. marketing/bulk.
- Template/message class.
- Region or business flow, when relevant.
- Cohort time and event age.

Never create time-series labels for **every email address**, **every rare domain**, **unbounded tenant IDs**, or **notification IDs**. High cardinality makes metrics expensive and increases PII exposure risk.

### Avoiding Simpson's Paradox

A provider with a lower overall delivery rate might actually perform better within each individual domain if it carries a larger share of harder-to-deliver domains. Before shifting all traffic based on a single aggregate number, compare within comparable segments.

## 35. Opens and Clicks Are Not Reliable Proof of Reading

Some providers supply engagement events:

- `OPENED`: signal from tracking pixel load or open-measurement mechanism.
- `CLICKED`: signal from accessing a provider-tracked link.
- `UNSUBSCRIBED`: opt-out feedback.

However, they have limitations:

- Privacy proxies or mail clients may prefetch pixels before a user actually reads the message.
- Clients blocking images can result in read emails with no open event.
- Security scanners or link prefetchers can trigger clicks without human interaction.
- A provider may have tracking disabled; transactional emails often should not be pixel-tracked.
- Using tracking must comply with privacy notices and product policies.

Never use `openRate` to directly assert Inbox placement, and never treat `click` as absolute proof a human clicked.

## 36. Measuring Inbox Placement Is a Separate Problem

Remote delivery does not tell you whether a message landed in:

```text
Inbox
Promotions / Other tab
Junk / Spam
Quarantine
Mailbox rule folder
```

To assess Inbox placement, you can use:

- Seed mailboxes across multiple mailbox providers for sampling.
- Authorized test inboxes with proper consent and access.
- Dedicated placement/reputation evaluation tools.
- Permitted recipient/provider diagnostic signals.

This is **sample-based estimation** and cannot be inferred solely from `JavaMailSender` or `delivered` events. Nor should you build mechanisms that log into customers' personal mailboxes to inspect Inbox placement without explicit permission and legitimate purpose.

## 37. A Useful Multi-Provider Dashboard

A three-layer layout is recommended:

### Submission Operations Layer

```text
Provider A/B/C
  - attempts/s
  - SMTP/API acceptance errors
  - p95 submit duration
  - 4xx/5xx groups
  - unknown outcomes
  - queue age / worker utilization
```

### Deliverability Feedback Layer

```text
By mature cohort, message class, provider, domain group
  - remote delivered %
  - bounced %
  - deferred %
  - rejected/suppressed %
  - unobserved %
  - delivery latency p50/p95
  - sample size
```

### Telemetry Quality Layer

```text
  - incoming webhooks / invalid signatures
  - provider event coverage
  - duplicate rate
  - unmatched event count and age
  - processing lag
  - reconciliation backlog
```

Dashboards should display **units, denominators, cohort age, sample sizes, and source reliability**. Charts lacking that context invite bad provider-switching decisions.

## 38. Alerts and SLOs Should Align With Business Goals

For time-sensitive transactional mail, monitor:

- Submission success rate over short time windows.
- `p95` time from request to SMTP accepted.
- `p95` time to remote delivered when feedback is trustworthy.
- Share of notifications past SLA age without an outcome.
- Count of OTP emails that expired before submission/delivery.

For bulk campaigns:

- Bounce/complaint rate over larger cohorts.
- Suppression and unsubscribe compliance.
- Throttling/deferral per recipient domain.
- Capacity/rate limits per provider route.

### Avoiding Alert Noise

A 10% bounce rate across 10 emails does not carry the same statistical weight as 10% across 100,000 emails. Alerts should enforce:

1. Minimum sample size.
2. Mature cohort age.
3. Baselines by provider and message class.
4. Multiple windows or meaningful thresholds.
5. Cross-checks with coverage to detect webhook outages.
6. Severity tiers aligned with business impact.

Never automatically fail over all traffic over a brief blip in a low-sample metric.

## 39. When Should You Switch Providers?

Multiple providers enable alternate routing, yet **failover does not mean every failed email should be resent through another provider**.

Classify by evidence:

| State at Provider A | Try B Immediately? | Reason |
| --- | --- | --- |
| Failed to open TCP connection, DATA never sent | Possibly, per policy | Evidence shows no submission happened over the failed connection |
| SMTP AUTH wrong credentials | Do not retry blindly | Fix config/route; B may work if authorized |
| Provider returned temporary 421/4xx before acceptance | Conditionally | Respect throttling, rate limits, and route health |
| Recipient rejected 550 due to address/policy | Usually no | Provider B won't make an invalid recipient valid; could be policy evasion |
| Provider reported suppressed/unsubscribed | No | Respect suppression and recipient preferences |
| Provider A already accepted, currently deferred | Not automatically | A may still deliver; B raises duplicate risk |
| Lost final reply after DATA | Not automatically | A may have received it; outcome is `UNKNOWN` |
| Provider A accepted, delivery event delayed | Not merely due to missing webhook | Missing feedback is not proof of failure |
| Provider A has verified outage before submission | Can reroute **new attempts** | Persist decision and prevent duplicates |

Routing can immediately optimize **future notifications** when route A degrades, whereas retrying earlier attempts requires checking each message's state.

## 40. Difference Between Routing and Failover

**Routing**: selecting a provider before sending a new notification.

```text
New notification
        |
        +-- category=transactional -> Provider A
        +-- category=bulk          -> Provider B
        +-- region=restricted      -> Approved regional route
```

**Failover**: an attempt already tried via provider A did not reach its goal, so the system considers a subsequent attempt via B.

```text
Notification N-100
        |
        v
Attempt A-1 -> Provider A
        |
        +-- outcome is definitely NOT SUBMITTED
                    |
                    v
              Policy allows retry
                    |
                    v
Attempt A-2 -> Provider B
```

These two operations carry different risks. Pre-attempt routing normally does not create duplicates; failover after an `UNKNOWN` attempt can.

## 41. Example Router Abstraction for Multiple JavaMailSenders

An application can instantiate a dedicated `JavaMailSender` per SMTP provider with corresponding host/port, credentials, and TLS properties:

```java
import org.springframework.mail.javamail.JavaMailSender;
import java.util.Map;

public record SelectedMailRoute(
        String providerKey,
        String providerScope,
        JavaMailSender sender
) {}

public final class MailProviderRouter {

    private final Map<String, SelectedMailRoute> routes;

    public MailProviderRouter(
            Map<String, SelectedMailRoute> routes
    ) {
        this.routes = Map.copyOf(routes);
    }

    public SelectedMailRoute require(String routeKey) {
        SelectedMailRoute route = routes.get(routeKey);
        if (route == null) {
            throw new IllegalArgumentException(
                    "Unknown approved mail route");
        }
        return route;
    }
}
```

This is an application-defined abstraction, not a built-in Spring Mail class. It accepts only **authorized routes**.

### Sender Selected Before Creating MimeMessage

```java
public void submit(
        UUID notificationId,
        String routeKey,
        String recipient,
        String subject,
        String body
) throws MessagingException {

    SelectedMailRoute route = router.require(routeKey);

    // Persist attemptId + providerKey + scope before sending.
    UUID attemptId = startAttempt(
            notificationId, route.providerKey(),
            route.providerScope());

    MimeMessage message = route.sender().createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message, false, "UTF-8");

    helper.setFrom("notice@example.org");
    helper.setTo(recipient);
    helper.setSubject(subject);
    helper.setText(body, false);

    try {
        route.sender().send(message);
        recordSubmitted(attemptId);
    } catch (MailException error) {
        recordSubmissionFailure(attemptId, error);
        throw error;
    }
}
```

`startAttempt`, `recordSubmitted`, and `recordSubmissionFailure` are application-implemented methods. This example omits full transactional outbox, leasing, exception classification, and recipient-level outcomes.

**Never hold a database transaction open across SMTP I/O.** Persist the attempt in a short transaction, submit outside the transaction, then record the outcome in another short transaction. Crashes after SMTP acceptance but before recording `SUBMITTED` create ambiguous state that must be handled as a real reliability concern.

## 42. Separating Deliverability from Route Health

A provider can exhibit:

- **Healthy route:** fast SMTP connect/auth/submit with low immediate error rate.
- **Poor deliverability:** remote MTAs frequently defer or reject messages for certain domains.

Or the reverse:

- **High route latency:** slow SMTP submission.
- **Good remote delivery:** once accepted, most messages deliver successfully.

If a router only tracks `JavaMailSender.send` latency, it might pick the fastest route even if it delivers poorly to a recipient segment. If it only reacts to bounce events from hours earlier, it responds too slowly to a current SMTP outage.

A routing system should consider multiple signals:

| Group | Examples | Time Horizon |
| --- | --- | --- |
| Submission health | Connect failures, SMTP 4xx/5xx, p95 submit latency | Seconds/minutes |
| Provider processing | Accepted/deferred backlog, provider status | Minutes |
| Remote delivery | Cohort delivered/bounced/unobserved | Hours/days |
| Sender reputation | Complaint/suppression, authentication and domain signals | Days/weeks |
| Capacity | Quota, connections, rate limits | Near real-time |

Do not blend signals of different latencies and scopes into an unexplainable single "provider score".

## 43. Suppression Must Be Managed Across Providers

Each provider may maintain its own suppression list to avoid resending to bounced or complaining addresses. If an application uses A and B:

```text
Provider A receives complaint for recipient R
                  |
                  v
Provider A suppression list
                  |
                  v
Application switches to Provider B
                  |
                  v
Provider B might not know suppression on A
```

That is a serious risk. If B does not know a recipient unsubscribed or complained via A, failover can keep sending unwanted emails.

### Centralized Policy

The application should maintain a unified policy source of truth for:

- Opt-out or unsubscribe per content category.
- Complaints/suppression per recipient and consent scope.
- Unrecoverable bounces per policy.
- Tenant/account-specific do-not-contact rules.
- Legal requirements or customer commitments.

Before choosing a route:

```text
Notification
     |
     v
Recipient eligibility / suppression check
     |
     +-- not allowed --> SUPPRESSED (no SMTP send)
     |
     +-- allowed --> route selection --> attempt
```

Not every email category shares the same suppression policy: transactional, security, and marketing emails have distinct requirements and legal bases. Define rules explicitly per business and applicable regulations; **never switch providers to evade spam complaints or opt-outs**.

## 44. DNS Authentication When Sending Through Multiple Providers

Deliverability is not determined by APIs/webhooks alone. Each provider or route may require domain setup:

- SPF and envelope/return-path configuration.
- DKIM signing keys/selectors.
- DMARC alignment with the visible From domain.
- Custom tracking domains, if used.
- Bounce domains and feedback mailboxes.
- TLS policy during SMTP submission.

When onboarding a new provider with incomplete DNS/authentication, messages may be accepted by the provider yet scored poorly by remote servers.

### Per-Route Verification Table

| Item | Provider A | Provider B | Meaning |
| --- | --- | --- | --- |
| Approved sender domain | Configured? | Configured? | Authority to send the From domain |
| DKIM signing | Verified? | Verified? | Message authentication signal |
| SPF/envelope alignment | Matches route? | Matches route? | Prevents misconfigured return-path |
| DMARC policy/alignment | Checked | Checked | Domain authentication evaluation |
| Bounce/complaint feedback | Active? | Active? | Adequate telemetry and suppression |
| Tracking/links | Right domain and privacy policy? | Right? | Affects trust and measurement |
| Rate limits/warm-up | Understood? | Understood? | Avoids throttling and reputation damage |

Never assume simply copying `spring.mail.host` to another host produces equivalent deliverability.

## 45. Reputation and Warm-Up Differ by Provider

Two providers can have different reputation histories, IP/domain pools, throughput limits, and enforcement policies. When shifting large traffic:

- Sudden volume spikes can trigger throttling at recipient servers.
- Low-quality recipient lists can generate bounces/complaints on the new route.
- Shared IP pools vs. dedicated IPs carry different trade-offs.
- A warming-up route should not absorb full peak load immediately.
- Identical domain authentication and content still do not guarantee identical delivery outcomes.

**Shifting 100% of traffic immediately because a dashboard shows A trailing B by a few percentage points** invites side effects. Roll out gradually, cap volume, observe mature cohorts, and compare identical traffic types.

## 46. Controlled Experiments to Compare Providers

To genuinely evaluate which provider fits a category of email, design an experiment:

1. Select eligible notifications with valid consent and uniform content type.
2. Split traffic **randomly under control** across providers without sending two copies to the same person.
3. Keep template, content, From domain, and recipient criteria stable when possible.
4. Verify DNS/authentication on both routes.
5. Balance recipient-domain distributions.
6. Use identical cohort definitions and denominators.
7. Observe long enough for deferred/bounce feedback.
8. Check event coverage and missing events per provider.
9. Measure submission latency, remote delivery, complaints, and cost.
10. Halt or throttle back if real risk signals appear.

### Never Send Two Identical Test Emails to the Same Recipient

If a recipient receives two emails just to "benchmark provider A vs. B", results get skewed by duplicate filtering, spam classifiers, and poor user experience. For business emails or OTPs, experiments must ensure only one authorized attempt runs at a time.

### Compare Segments, Not Just Totals

Pay special attention to:

- Recipient domain group.
- Transactional vs. campaign content.
- MIME payload size.
- Send hour and load distribution.
- Account/provider pool.
- Cohort age and event coverage.

A good experiment records both **sampling methodology and data limitations**, not just headline percentages.

## 47. Failover After UNKNOWN: The Duplicate Send Window

Scenario:

```text
Attempt 1: Provider A
  - Application transmits MIME DATA
  - Connection drops before final response
  - Application records UNKNOWN

Immediately:
Attempt 2: Provider B
  - B accepts the same notification

Later:
  - Provider A sends DELIVERED event
  - Provider B sends DELIVERED event
```

Both providers may have submitted the same notification. As a result, the recipient may receive **two copies**, even though each `JavaMailSender` attempt was invoked once.

### Mitigations

- Do not automatically fail over `UNKNOWN` attempts unless policy explicitly accepts duplicate risk.
- Use provider query/reconciliation APIs where supported.
- Maintain separate attempt history and event correlation for A and B.
- Do not assume a shared `Message-ID` guarantees provider-side deduplication.
- When resending intentionally, record `resendReason` and actor/policy.
- For time-sensitive emails, weigh delay against duplicate risk per business policy.
- If a provider supports API idempotency, apply it within that API's exact scope and conditions.

Exactly-once **SMTP delivery** is not universally guaranteed by Spring Mail or a transactional outbox.

## 48. Do Not Fail Over While a Provider Is Retrying Deferred Mail

`DEFERRED` means the provider may still keep retrying delivery. If the application immediately sends another copy through B:

```text
A deferred + A retries later
B submitted now
        |
        v
Recipient may receive both
```

To handle this properly, determine:

1. Is the provider still retrying or is it terminal?
2. Is the event a temporary deferral or final failure?
3. Can the application cancel the queued attempt at the provider?
4. Does the provider guarantee cancellation took effect before submitting via B?
5. Is the recipient/business willing to tolerate duplicate risk?

In most cases, let the provider finish its contract retry lifecycle, and reroute only **new notifications** or attempts proven not to have been submitted.

## 49. Identical Raw Event Names May Not Mean the Same Thing

A hypothetical example across two providers:

| Provider Event | Verified Integration Meaning | Mapping |
| --- | --- | --- |
| A: `processed` | Accepted into internal queue | `PROVIDER_ACCEPTED` |
| A: `delivered` | Destination server accepted | `DELIVERED_REMOTE` |
| B: `accepted` | Provider received the request | `PROVIDER_ACCEPTED` |
| B: `sent` | Provider handed to send pipeline, no remote proof yet | Do not map directly to `DELIVERED_REMOTE` |
| B: `temporary_failure` | Delivery incomplete, still retrying | `DEFERRED` |
| B: `final_failure` | Terminal outcome per policy | `BOUNCED` or `PROVIDER_REJECTED` depending on stage |

This table is a **synthetic taxonomy illustrating adapter design**, not a verified mapping for any named commercial provider. In real projects, the exact provider and endpoint contract governs mapping.

### Retain Raw Event Types for Traceability

If a provider renames events or adds classifications, storing only the canonical enum makes it hard to audit how past events were translated.

Retain:

```text
providerKey
providerScope
providerEventType
canonicalEventType
mappingVersion
sourceSchemaVersion
```

When mapping logic changes, projections can be rebuilt from the stored event ledger if retention and contracts permit. Never silently rewrite history under a new mapping without version tracking.

## 50. Metric Naming to Avoid Confusing Events and Messages

Example with Micrometer:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public final class MailFeedbackMetrics {

    private final MeterRegistry registry;

    public MailFeedbackMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordAcceptedEvent(
            String approvedProviderLabel,
            CanonicalMailEventType type
    ) {
        Counter.builder("mail.feedback.events.accepted")
                .tag("provider", approvedProviderLabel)
                .tag("canonical_type", type.name())
                .register(registry)
                .increment();
    }
}
```

In this example, `approvedProviderLabel` must come from a configured allowlist of routes rather than arbitrary webhook strings. `type.name()` has bounded cardinality because the enum is controlled.

**This counter counts valid events accepted into the pipeline**, not unique delivered emails. Unless invoked after deduplication, retried webhooks can increment it multiple times.

To compute delivery rates, query **distinct recipient-attempt outcomes from the projection or cohort queries** rather than dividing a raw event counter by `JavaMailSender.send` calls.

## 51. Count by Event-Time or Receive-Time?

Two dashboards can disagree even on identical underlying data:

```text
Event happened: 10:00 yesterday
Webhook received: 11:00 today
```

- Dashboards by **receivedAt** show when the system ingested feedback.
- Dashboards by **occurredAt** show when the provider reported the event occurred.
- Dashboards by **submittedAt cohort** show outcomes for notifications sent during a given period.

Each serves a distinct purpose:

| Timestamp | Used For |
| --- | --- |
| `submittedAt` | Delivery/SLO cohorts per notification batch |
| `occurredAt` | Provider timeline when timestamps are trustworthy |
| `receivedAt` | Webhook ingestion health and event delay |
| `projectedAt` | Internal processing lag |
| `reconciledAt` | When the system supplemented evidence |

Never mix time axes on one unlabeled chart; when late events arrive, earlier cohort reports can shift upon recomputation.

## 52. A Pipeline Has Two Distinct Kinds of Retries

**Email send retries** and **webhook processing retries** are independent operations:

```text
Outbound retry:
Notification -> Provider submit attempt 1
             -> Provider submit attempt 2 (if permitted)

Inbound retry:
Provider sends DeliveryEvent E
          -> Webhook request retry E
          -> Inbox projector retry E
```

Inbound retries **never mean resend the email**. Duplicate webhooks must be deduplicated or handled idempotently without triggering extra `JavaMailSender.send(...)` calls.

Wrong example:

```java
if (event.canonicalType() == CanonicalMailEventType.DEFERRED) {
    mailSender.send(originalMimeMessage);
}
```

The provider may already be retrying on its own. Applications must not create new submission attempts simply upon receiving `DEFERRED`; enforce explicit rules for terminal outcomes, cancellation, suppression, and duplicates.

## 53. Handling Event Batches and Partial Failures

A single callback can carry multiple events. Example:

```json
[
  {"event_id":"e-1","type":"delivered","message_id":"m-1"},
  {"event_id":"e-2","type":"deferred","message_id":"m-2"},
  {"event_id":"e-3","type":"bounced","message_id":"m-3"}
]
```

This JSON is a **synthetic fixture** illustrating batching, not a universal schema for any provider.

Verify against each provider's contract:

- How many events can one request contain?
- Does the signature cover the entire raw request or individual events?
- Is acknowledgment per batch or per item?
- If one item fails schema validation, should the entire batch be rejected?
- Does the provider retry the whole batch when a request fails?
- Can multiple recipients of one message appear in a single event?

To prevent data loss, store a **raw verified envelope reference** alongside normalized event entries in an appropriate transaction. With all-or-nothing semantics, failed callbacks are retried by the provider; if partial acceptance is supported, design per-item acknowledgment per contract. Never invent per-item acknowledgments when the API only checks the request-level HTTP status.

## 54. Contract Tests for Each Adapter

Every provider adapter should be tested with **synthetic fixtures verified against documentation or sandbox output** from that provider.

Key tests:

1. Valid payload, valid signature: parses and normalizes into the expected canonical event.
2. Invalid signature: rejected before writing state.
3. Payload modified by one byte: no longer accepted if the signature scheme covers that byte.
4. Expired/replayed timestamp: rejected when the provider supports timestamped signatures.
5. Unknown event type: kept as `UNKNOWN` with raw type preserved for investigation, never turned into DELIVERED.
6. Missing message ID: stored uncorrelated unless a reliable correlation key exists.
7. Multi-recipient event: produces the expected number of observations per contract.
8. Duplicate event ID: event inbox persists/applies only once per dedupe key.
9. Identical event IDs across accounts: never deduplicated across accounts.
10. Varying timezone/precision timestamps: normalized accurately or marked missing.
11. Sensitive diagnostic text: omitted from metrics and general logs.
12. Key rotation: valid keys accepted during the transition window per contract.

Mapper unit tests do not require calling live providers. Integration/sandbox tests additionally verify endpoints, auth, and event publication for configured accounts.

## 55. Testing Webhook Idempotency and Out-of-Order Delivery

A scenario:

```text
Event E1 = DELIVERED_REMOTE
Event E2 = PROVIDER_ACCEPTED
Event E3 = DEFERRED

Delivery order to webhook:
E1, E1 again, E3, E2
```

Expectations:

- Event E1 is stored once when the provider event ID is stable.
- Repeated E1 callback is acknowledged safely.
- E2/E3 do not erase delivered evidence.
- Projection reflects delivered according to policy.
- Event history still shows late arrivals of E3/E2.
- Unique recipient-attempt remote delivered metric does not double-count.
- Duplicate webhook counts can be tracked separately.

### Assertion Pseudocode

```java
// Pseudocode: eventFixtures, inbox, and projector are provided by the test harness.
deliver(eventFixtures.delivered("e-1", "m-1"));
deliver(eventFixtures.delivered("e-1", "m-1"));
deliver(eventFixtures.deferred("e-3", "m-1"));
deliver(eventFixtures.accepted("e-2", "m-1"));

assertEquals(3, inbox.uniqueEventCount());
assertEquals(
        DeliveryState.DELIVERED_REMOTE,
        projector.outcomeFor("m-1")
);
assertEquals(1, projector.uniqueDeliveredCount());
```

This snippet illustrates expectations, not standalone compilable code. In real systems, `projector.outcomeFor(...)` must use a namespaced key and correlate recipient/attempt accurately; passing bare `"m-1"` here simply keeps the fixture brief.

## 56. Testing Unmatched Message IDs

A provider event:

```json
{
  "event_id": "event-demo-104",
  "type": "delivered",
  "message_id": "unknown-demo-message"
}
```

Expectations:

- When the signature is valid, the event is stored durably.
- `correlation_state=UNMATCHED`.
- Does not randomly update a nearby notification by timestamp.
- Correlation retry and `unmatched_events` metric exist.
- An incident/review policy handles events that remain unmatched past retention.

A thorough test also verifies that an event from `provider-a/account-1` never matches an attempt in `provider-b/account-2` even if their `providerMessageId` values happen to collide.

## 57. Testing Failover When Proven Not Submitted

Configure two SMTP test servers:

```text
Provider A test endpoint: refused connection
Provider B test endpoint: accepts MAIL/RCPT/DATA
```

Expectations:

1. Attempt A-1 records provider A and the pre-submission connection failure.
2. Retry policy confirms rerouting is permitted (without bypassing suppression).
3. Attempt A-2 records provider B without overwriting A-1.
4. B receives exactly one DATA transaction for the notification.
5. Recipient outcome can update from B's simulated events.
6. Dashboard counts **two submit attempts**, yet **one notification**.

With multiple recipients, distinguish recipient-attempts from message attempts; do not turn "two attempts" into two recipients.

## 58. Testing No Failover on UNKNOWN Outcome

Configure server A to finish reading `DATA` and drop the connection before the final reply; server B can accept mail, yet must **not be called automatically** when policy forbids it.

Expectations:

- Attempt A is recorded as `UNKNOWN`.
- No automatic submission request goes to B.
- Reconciliation or operational handling occurs.
- If A's event later reports delivery, the projection updates attempt A.
- If an operator deliberately triggers a policy-approved resend, a distinct attempt B is created with an explicit reason.

This is especially vital for OTPs, invoices, or transactional notices: a duplicate can confuse users or cause side effects outside email.

## 59. Testing Cross-Provider Suppression

A business test:

```text
Provider A event: COMPLAINED for recipient R
        |
        v
Central recipient policy updated
        |
        v
New notification for R tries route B
        |
        v
Suppressed before SMTP send
```

Expectations:

- Complaint event is tied to the right recipient.
- Policy for the relevant email category reflects suppression.
- Router does not call `JavaMailSender.send` via B when policy forbids it.
- Audit record explains `SUPPRESSED`.
- Unsent messages are not counted as `BOUNCED` on B.

Exemptions/exceptions for transactional, security, or marketing mail must be clearly defined by business and applicable rules; tests must match **actual policy**, not an unvetted blanket rule.

## 60. Testing Provider API Reconciliation

If a provider offers a message-status query API, integration tests should verify:

1. An attempt is `SUBMITTED`, yet no webhook arrived.
2. Reconciliation worker selects attempts **old enough** and lacking an outcome.
3. Adapter queries using valid provider/account/scope and message ID.
4. Test response reports `DELIVERED_REMOTE`.
5. Evidence is persisted with `source=PROVIDER_QUERY`.
6. When a `DELIVERED_REMOTE` webhook arrives later, the projection does not increment delivered count again.
7. If the provider API returns `NOT_FOUND` due to expired retention or indexing lag, do not assume the email failed.
8. HTTP 429/5xx responses are retried with backoff and quota limits.

Providers without a query API need another strategy, such as observation timeouts labeled `UNOBSERVED`, or DSN/bounce feedback if supported. Do not write a "universal reconciler" assuming every provider offers a query endpoint.

## 61. DSNs and Bounce Mailboxes When Providers Lack Webhooks

Some systems rely on **Delivery Status Notifications (DSNs)** or a bounce mailbox instead of webhooks:

```text
Application -> SMTP relay
     |
     v
Remote delivery fails
     |
     v
DSN/bounce to configured return-path
     |
     v
Bounce mailbox processor
     |
     v
Parse + correlate + normalize event
```

Keep in mind:

- `Return-Path` relates to the envelope sender, not merely an arbitrary application header.
- Not every failure produces a DSN accessible to the application.
- DSNs can arrive very late or omit metadata the application expects.
- Bounce emails may contain full or partial original headers/bodies, making them sensitive data.
- Parsers must handle diverse MIME structures and untrusted mail sources; avoid single-line regexes.
- Verify feedback authenticity/trustworthiness to prevent spoofed bounces from falsely suppressing recipients.

Without reliable feedback, dashboards must disclose the limitation rather than turning SMTP submission into remote delivered.

## 62. A Provider Can Have Multiple Accounts, Regions, or Subaccounts

A simple provider key may not suffice:

```text
provider-a
    |
    +-- account-transactions / region-1
    +-- account-marketing / region-1
    +-- account-support / region-2
```

Each account/scope can differ in:

- Credentials and webhook signing secrets.
- Sending domains and return-paths.
- Suppression and feedback settings.
- Event retention and query API permissions.
- Quotas, rate limits, and reputation.
- Endpoints and data residency.

Correlation must namespace provider message IDs with `providerScope`; the event receiver must also know **which signing keys/credentials are valid for that scope**.

Never take an account/scope from an unverified webhook header and use it to look up arbitrary secrets. Endpoint registries and verification policies must constrain accepted values.

## 63. Multi-Provider Secret and Key Rotation

Each route typically involves at least two secret groups:

- Credentials to **submit** via SMTP/API.
- Keys/tokens to **verify feedback** from webhook/event sources.

These two groups do not necessarily share mechanisms or lifecycles. A safe setup:

| Secret | Where Used | Rules |
| --- | --- | --- |
| SMTP password/API key | Outbound sender | Never log, restrict send permissions |
| Webhook verification key | Inbound receiver | Never reuse as outbound credential |
| Reconciliation API token | Background query worker | Read-only scope where possible |
| Internal HMAC key | Sensitive correlation/hashes if used | Manage separately, rotate regularly |

During rotation:

1. Determine whether the provider supports a key-overlap window.
2. Rotate keys according to provider contract.
3. Verify valid signatures under active keys.
4. Avoid breaking webhook ingestion while older callbacks are still retrying.
5. Do not leave revoked tokens active indefinitely.
6. Audit who modified configurations and routes.

Never commit credentials in `application.yml` to repositories. Use a controlled secret manager or environment configuration and avoid printing full configuration in error handlers.

## 64. Recipient Privacy and Event Data

Webhooks may contain email addresses, bounce diagnostics, user agents, IPs, or URLs. These fields can constitute personal or sensitive data under policy.

Principles:

- Use internal `recipientId` in projections; resolve email addresses only inside authorized services.
- Never put raw recipient emails into metric labels.
- Never log full callback bodies or SMTP diagnostics.
- If retaining raw events, enforce encryption, access controls, and retention limits.
- For open/click tracking, assess purpose, notice/consent, and usage policies.
- Protect Bcc privacy; never expose hidden recipients on broad dashboards.
- Support deleting user data from event stores/analytics when required by regulations and commitments.

A provider may require processing data within a specific region; routing through another provider changes the data processing scope. Failover must respect **legal and contractual constraints**, not just health metrics.

## 65. Example Dashboard Query from Projection

Suppose the system maintains a `mail_recipient_outcome` projection table, **one row per recipient-attempt**, containing:

```text
attempt_id
recipient_id
provider_key
message_class
submitted_at
delivery_state
feedback_coverage_state
```

An illustrative PostgreSQL query for cohorts at least 24 hours old:

```sql
SELECT
    provider_key,
    COUNT(*) AS recipient_attempts,
    COUNT(*) FILTER (
        WHERE delivery_state = 'DELIVERED_REMOTE'
    ) AS delivered,
    COUNT(*) FILTER (
        WHERE delivery_state = 'BOUNCED'
    ) AS bounced,
    COUNT(*) FILTER (
        WHERE delivery_state = 'DEFERRED'
    ) AS deferred,
    COUNT(*) FILTER (
        WHERE feedback_coverage_state = 'UNOBSERVED'
    ) AS unobserved
FROM mail_recipient_outcome
WHERE message_class = 'TRANSACTIONAL'
  AND submitted_at >= :cohortStart
  AND submitted_at < :cohortEnd
  AND submitted_at < now() - interval '24 hours'
GROUP BY provider_key
ORDER BY provider_key;
```

This is **illustrative SQL**; the projection table and statuses must be implemented by the application. If a notification has multiple attempts or recipients, the denominator here is recipient-attempts, not unique notifications.

To measure **unique notifications eventually delivered**, write a separate query aggregating over `notificationId + recipientId` after resolving attempts and duplicates. Never compute per-attempt metrics and rename them as per-notification metrics.

### What Should Accompany the Numbers Table?

- Cohort start and end timestamps.
- Minimum elapsed time since submission.
- Number of unmatched events.
- Which providers lack certain feedback types.
- Whether outcomes are measured per attempt or per notification.
- Account/region scope.
- Late or replayed events within the measurement window.

This metadata is mandatory so operators do not misinterpret differences across providers.

## 66. Runbook When One Provider's Delivered Rate Drops

Suppose a dashboard shows Provider A dropping noticeably below baseline. Do not immediately shift all routes to B.

### Step 1 — Check Telemetry First

- Are webhook callbacks arriving?
- Did invalid signature failures spike suddenly?
- Is the inbox event queue backed up?
- Were signing keys or endpoints rotated recently?
- Is data missing for a single account or region?
- Did event coverage drop, or did actual bounces/rejections rise?

If only event coverage dropped, the issue likely lies in feedback ingestion rather than the sending path.

### Step 2 — Check Submission Health

- Are `JavaMailSender.send` errors or timeouts rising?
- Which SMTP command is returning 4xx/5xx?
- Did auth/TLS/connectivity change?
- Is queue age growing?
- Were provider quotas or rate limits hit?

If submission looks healthy while remote delivery fell, investigate feedback/destinations rather than blindly changing connection settings.

### Step 3 — Compare Similar Cohorts

- Same notification category.
- Same recipient domain group.
- Same send window and observation period.
- Same sender domain/authentication.
- Same definition of delivered.
- Sufficient sample size.

Never declare a provider worse if it carries a far higher share of hard-to-deliver domains.

### Step 4 — Inspect Detailed Feedback

- Bounces/deferrals by reason category.
- Complaints and suppressions.
- Pre-delivery provider rejections.
- Delayed or missing events.
- Recent changes to domains, accounts, or templates.

### Step 5 — Decide on Throttling or Rerouting

Only move **eligible** traffic to provider B over an authenticated, sufficiently provisioned route that respects suppression. For `UNKNOWN` attempts or messages still deferred at provider A, do not automatically resend.

### Step 6 — Monitor After Action

- Are routing decisions and attempt histories persisted?
- Are queue/SMTP errors decreasing?
- Is provider B hitting throttling?
- Is event coverage on B complete?
- Are complaints/suppressions rising?
- Are there duplicate-send alerts from failover?

A solid runbook fixes the immediate metric without causing a secondary incident.

## 67. Scenario: Dashboard Reports 0% Deliverability

A new provider was added and `JavaMailSender.send(...)` succeeds, yet the dashboard shows zero delivered events.

**Correct diagnosis:**

1. Verify whether delivery event subscriptions are enabled.
2. Verify webhook URL, routing, TLS, and secrets.
3. Verify callbacks are reaching the receiver.
4. Check signature/parse/inbox/dedupe pipeline.
5. Verify provider metadata suffices to correlate attempts.
6. Check the event query API or logs if supported by the provider.

Without feedback, the conclusion is **"remote delivery unobserved"**, not that 0% of emails reached destination servers.

## 68. Scenario: A Reports Delivered, B Reports Only Accepted

A dashboard divides `A.delivered` by A's send volume and `B.accepted` by B's send volume, labeling both "delivery rate".

**What is wrong?** The two numerators represent different stages. Normalize event semantics, or display them as separate metrics annotated with provider coverage. Never conclude B outperforms A merely because B shows 99% accepted vs. A's 95% delivered.

## 69. Scenario: Duplicate Webhooks Push Delivered > 100%

A provider retries a delivered webhook because the first callback failed to receive an acknowledgment. The app increments the delivered counter on every receipt.

**Fix:** durably store event ID/scope, deduplicate in the event inbox, and build projections over unique recipient-attempts. Count webhook requests and duplicate events separately from unique delivery outcomes.

## 70. Scenario: Complaint on A Still Sends via B

Provider A receives a complaint and adds the recipient to A's suppression list. The router switches to B because A hit a rate limit.

**Risk:** B is unaware of A's suppression and keeps sending. Maintain a centralized suppression/eligibility policy checked before routing, and store feedback events accordingly. Never use failover to bypass unsubscribes or complaints.

## 71. Scenario: Webhook Arrives Before API Response Is Persisted

A delivered webhook arrives with a provider message ID before the attempt's mapping is saved. The app finds no matching record and drops the event.

**Fix:** persist the event as `UNMATCHED`, retry correlation once mappings commit, and alert on aging backlogs. Never auto-match by subject or nearby recipient timestamp without reliable keys.

## 72. Scenario: Provider A Retries Deferred After Failover to B

A reports deferred; the system immediately resends the same email via B. Later, both A and B report delivered.

**Fix:** distinguish deferrals from final failures. While A is still retrying, do not automatically submit to B. If both ran, the ledger must link both events to the two attempts of the same notification so duplicates can be audited.

## 73. Scenario: Delivered Yet Recipient Reports Missing Email

Provider reports `DELIVERED_REMOTE`, while the user says the email is not in their Inbox.

**Questions to separate:**

- Did the remote server accept the email?
- Were there subsequent bounce, complaint, or policy events?
- Could the message be in spam/Promotions/quarantine?
- Were the recipient address and alias accurate?
- Does the mailbox have a filtering rule moving the message?
- Can a test mailbox or seed list reproduce the behavior?

Do not assume the provider is lying or the user is mistaken; remote acceptance and Inbox placement are distinct layers. Accessing personal mailboxes requires appropriate authorization and purpose.

## 74. Common Mistakes in Multi-Provider Monitoring

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Treating error-free `JavaMailSender.send` as delivered | Misreports sending layer | Record `SUBMITTED`, await provider/remote evidence |
| Mapping every `accepted/processed/sent` to `DELIVERED_REMOTE` | Inflated delivery rate | Verify per-provider semantics |
| Storing a single `status` on notification | Loses attempt history and distinct signals | Event ledger + multi-dimensional projection |
| Omitting `providerKey`/`providerScope` | Miscorrelates message IDs across accounts | Namespace correlation keys |
| Matching via Subject + email | Misattribution and PII exposure | Use reliable provider metadata/attempt IDs |
| Counting every webhook retry as a new delivery | Delivered count exceeds reality | Durable event inbox + deduplication |
| Overwriting status in callback arrival order | Delivered overwritten by stale deferred | Project from history with clear rules |
| Dropping unmatched events | Breaks reconciliation, loses feedback | Store `UNMATCHED` and retry correlation |
| Skipping webhook signature verification | Enables forged delivery/bounce/complaint events | Verify per provider before processing |
| Returning `200` before persisting | Crash loses acknowledged events | Durable write before `2xx` |
| Treating missing events as failures | Falsely blames provider | Separate coverage from outcomes |
| Comparing providers using different numerators | Skewed rankings | Align cohort, unit, and semantics |
| Comparing metrics on immature cohorts | Misclassifies deferred mail as failed | Require mature observation windows |
| Relying solely on overall aggregate rates | Masks recipient-domain mix effects | Compare comparable segments |
| Treating opens/clicks as proof of reading | Distorted by proxies/scanners/clients | Track engagement separately, note caveats |
| Treating delivered as Inbox placement | Misjudges folder placement | Use authorized seed/mailbox signals |
| Failing over immediately on DATA timeout | Risks duplicate sends via two providers | Record `UNKNOWN` and reconcile |
| Failing over while A is still deferred | Both A and B may deliver | Check finality and retry policy |
| Bypassing suppression on failover | Violates opt-outs, raises complaints | Centralized eligibility policy |
| Switching providers without DKIM/DMARC setup | Hurts authentication and reputation | Validate domain route before rollout |
| Putting PII into metric labels | High cardinality and data leakage | Allowlisted labels, internal IDs |
| Testing only happy-path webhooks | Breaks on invalid/duplicate/out-of-order callbacks | Contract/integration test matrix |
| Assuming infinite provider event retention | Reconciliation fails past retention | Define polling policy and observation cutoff |

## 75. Checklist for Onboarding a New Provider

### A. Sending Path

- [ ] Confirmed SMTP/API endpoint, region, TLS, and authentication.
- [ ] Authorized sending domain and From address configured.
- [ ] SPF, DKIM, DMARC, and return-path verified for route configuration.
- [ ] Message size, recipient, throughput, and connection limits understood.
- [ ] Account and quota provisioned for the appropriate traffic class.
- [ ] Defined when `send(...)` counts as submission success.
- [ ] Defined how `attemptId` and `providerMessageId` (when available) are stored.

### B. Feedback Path

- [ ] Which events the provider offers and their exact semantics?
- [ ] Event publication enabled on the right account/region/subaccount?
- [ ] Uses webhooks, queues, status API, or DSN?
- [ ] Callback authentication implemented per provider docs?
- [ ] Key rotation and request limits in place?
- [ ] Stable event ID available for deduplication?
- [ ] Reliable metadata available for message/recipient correlation?
- [ ] Can callbacks carry batched events or multiple recipients?
- [ ] Callback retry policies and event retention limits documented?
- [ ] Reconciliation API available if webhooks are lost?

### C. Data Normalization

- [ ] Raw types mapped to canonical types with mapping version.
- [ ] Raw types and source scopes preserved for audit.
- [ ] `UNKNOWN/UNMATCHED/UNOBSERVED` states used when evidence is missing.
- [ ] Deduplication scoped by provider + scope + event identity.
- [ ] Feedback state separated from delivery state.
- [ ] Stale out-of-order webhooks never overwrite newer outcomes.

### D. Security and Compliance

- [ ] Outbound credentials and webhook verification keys managed separately.
- [ ] Recipient/Subject/body/tokens excluded from event diagnostics logs.
- [ ] Raw payloads have encryption, access controls, and retention if stored.
- [ ] Centralized suppression/opt-out policy enforced.
- [ ] Failover respects suppression and data residency.
- [ ] Provider approved for relevant data classes and tenants.

### E. Testing and Operations

- [ ] Happy-path submission and feedback verified in sandbox.
- [ ] Invalid signatures/payloads rejected.
- [ ] Duplicate/out-of-order events do not corrupt projections.
- [ ] Unmatched events stored and reconciled.
- [ ] Timeout after DATA does not trigger blind failover.
- [ ] Provider-specific and event-coverage dashboards exist.
- [ ] Alerts require minimum sample size and mature cohorts.
- [ ] Traffic rollout has volume caps and a kill switch.

## 76. Checklist for Comparing Deliverability Across Two Providers

Before concluding "Provider B is better than Provider A", answer:

1. Do both routes send the same email types to comparable recipient groups?
2. Do they share comparable sender domains, authentication, and reputation conditions?
3. Do both providers offer **equivalent remote delivery evidence**?
4. Is the denominator unique recipients, recipient-attempts, or message-attempts?
5. Have retries and duplicate webhooks been excluded/reconciled?
6. Have cohorts aged long enough for delivery feedback?
7. How many recipients remain deferred or unobserved?
8. How much does feedback event coverage differ?
9. Were templates, content, send times, or routing changed recently?
10. Are bounces/complaints classified under identical semantics?
11. Have results been segmented by recipient domain group and traffic class?
12. Is sample volume large enough to drive operational decisions?
13. Are Inbox placement and opens/clicks separated from remote delivered?
14. Is a webhook outage being mistaken for a deliverability drop?
15. If switching routes, is there risk of losing suppression or sending duplicates?

If several answers are missing, treat results as **provisional observations with data limitations**, not an absolute ranking.

## 77. Self-Study Exercises

### Exercise 1 — Two Providers With Different States

Provider A reports `DELIVERED_REMOTE` for 900/1,000 recipient-attempts. Provider B reports `PROVIDER_ACCEPTED` for 990/1,000 attempts without remote-delivered feedback.

**Question:** Can you say B delivers better than A?

**Hint:** No. The numerators measure different layers; B lacks remote delivery instrumentation. Compare submission separately from remote-delivered, and report event coverage.

### Exercise 2 — Duplicate Events

A delivered webhook with the same event ID arrives three times. The database inserts three rows and the dashboard reports over 100% delivered.

**Hint:** Unique constraint/idempotent inbox on provider + scope + event identity; projection over distinct recipient-attempts; count duplicate callbacks separately.

### Exercise 3 — Deferred Arriving After Delivered

A provider sends `DEFERRED` then `DELIVERED_REMOTE`, but the system receives the delivered webhook first.

**Hint:** Avoid last-arrival-wins. Use an event ledger and semantic projection rules so stale deferrals cannot overwrite delivered.

### Exercise 4 — Lost Webhooks

SMTP submission succeeds, then no webhook arrives within 24 hours. The dashboard automatically marks it `FAILED`.

**Hint:** Missing feedback is `UNOBSERVED` or `STALE_UNOBSERVED`, not confirmed failure; inspect event coverage and query API/DSN if available.

### Exercise 5 — Cross-Provider Duplicates

Attempt A transmits DATA then loses the final reply, and the app immediately fails over to provider B. Later, both A and B emit delivered events.

**Hint:** A must be recorded as `UNKNOWN`; reconcile before failover when policy forbids duplicates. Both events belong to two distinct attempts of one notification and must not overwrite each other.

### Exercise 6 — Cross-Route Suppression

Provider A records a complaint from recipient R. Provider B does not have R in its suppression list. The router prepares to send marketing mail via B.

**Hint:** Check central eligibility/opt-out before routing. Never use B to circumvent complaints or suppression.

### Exercise 7 — Domain Skew

Provider A shows a lower aggregate delivered rate than B, yet A carries most traffic to a domain currently throttling.

**Hint:** Segment by cohort/domain/message class and balance traffic mix before attributing the gap to the provider.

### Exercise 8 — Complaint After Delivery

A recipient reached `DELIVERED_REMOTE` and later triggered `COMPLAINED`.

**Hint:** Do not erase delivery evidence. Keep delivery state and feedback state separate; update suppression per policy.

### Exercise 9 — Identical Message ID Across Two Accounts

A provider issues message ID `m-123` in account A and also `m-123` in account B. The application uses a global unique key on message ID alone.

**Hint:** Namespace by provider + account/region + message ID; event ID/dedupe keys must likewise be properly scoped.

### Exercise 10 — Open/Click Tracking

A provider reports a sharp rise in open rate while clicks and customer replies remain flat.

**Hint:** Open pixels may be fetched by privacy proxies or automated scanners; do not infer improved Inbox placement or actual human reads from this signal alone.

### Exercise 11 — Webhook Storage Failure Test

Webhook signature is valid, yet the event inbox database cannot write. The controller still returns `204` before persisting.

**Hint:** Risks losing feedback after acknowledgment. Return success only once data is durably persisted or accepted by a durable queue per contract.

### Exercise 12 — Bounce vs. Suppression

Provider A emits `dropped` due to suppression; the mapper records it as `BOUNCED`.

**Hint:** Distinguish stage and semantics: pre-delivery suppression differs from a remote bounce. Use a versioned mapping contract and keep raw types.

## 78. Key Principles to Remember

1. **Spring Mail handles MIME and SMTP submission**; it does not automatically provide deliverability events across providers.
2. **Submitted, provider-accepted, remote-delivered, Inbox, and engagement are distinct layers.**
3. **Provider event naming is inconsistent**; map by semantics and version rather than name alone.
4. **Recipient-attempt is usually the right unit of observation**; do not confuse messages with recipients or webhook events.
5. **Persist notification ID, attempt ID, provider scope, provider message ID, and event ID** according to what each source supplies.
6. **An immutable event ledger + projection** is safer than a single status overwritten in callback arrival order.
7. **Webhooks require verification, limits, durable storage, and idempotent processing**; duplicate and out-of-order arrivals are normal.
8. **Unmatched or missing events are observability gaps**, not automatic proof of delivery success or failure.
9. **Denominators, cohort age, event coverage, and traffic mix** are prerequisites for comparing deliverability rates.
10. **Opens/clicks do not prove a user read the email**, and remote delivered does not prove Inbox placement.
11. **Failover after `UNKNOWN` or `DEFERRED` risks duplicates** and must rely on policy and reconciliation.
12. **Suppression/consent must be enforced across providers**; never reroute to bypass negative feedback.
13. **DNS authentication, reputation, quotas, and regions** belong to each route's quality, not merely the SMTP host.
14. **Measure telemetry quality before drawing conclusions about deliverability quality.**
15. **Never place PII/secrets/raw payloads into metric labels or general logs**, even while investigating errors.

## 79. Conclusion

Monitoring deliverability across multiple providers in Spring Framework Mail is an **observability and semantic-unification problem**, not merely wrapping `JavaMailSender.send(...)` in extra `try/catch` branches. A successful send call only proves SMTP submission according to transport evidence; from there to provider acceptance, remote delivery, bounces, complaints, suppression, Inbox placement, and engagement lie multiple stages backed by distinct data sources.

A reliable architecture stores **notifications and per-provider attempts**, identifies recipients explicitly, ingests callbacks/feedback securely, normalizes events via per-provider adapters, and persists a durable event ledger. Projections must tolerate duplicate, delayed, unmatched, or completely missing webhooks. Dashboards must disclose **denominators, cohorts, observation age, coverage, and traffic scope**, while separating submission health from deliverability and Inbox placement.

Ultimately, deliverability metrics are only useful when they drive **correct action**: fixing SPF/DKIM/DMARC configuration, honoring suppression, pacing rates, reconciling lost events, improving list hygiene, and routing under clear controls. Never use failover to bypass opt-outs or blindly resend an attempt whose outcome is unknown. By combining clean event semantics, provenance-tracked data, and disciplined operational processes, a multi-provider system can compare real sending quality without sacrificing accuracy, privacy, or business email reliability.
