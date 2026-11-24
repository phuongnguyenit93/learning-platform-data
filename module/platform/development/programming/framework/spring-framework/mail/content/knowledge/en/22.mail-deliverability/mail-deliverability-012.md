# Tracking Accepted, Bounced, Deferred, and Complained Events in Spring Framework Mail

A successful email send command in an application does not mean the email reached the recipient's mailbox. With Spring Framework Mail, calling **JavaMailSender.send(...)** typically tells the application that sending to the SMTP relay completed or failed at the stage directly observed by the application. Afterward, the relay and other mail-routing systems can still process, retry, reject, bounce, or record a recipient spam report.

In email operations, four signal groups are especially important: **accepted**, **bounced**, **deferred**, and **complained**. They describe different stages in the delivery chain:

- **Accepted:** a party assumes responsibility for processing the message at a specific boundary, such as an SMTP relay accepting the send request. Always specify *accepted by whom*.
- **Bounced:** there is evidence the message could not be delivered and was returned/failed at some delivery stage.
- **Deferred:** delivery was delayed or temporarily rejected; the system may retry according to policy.
- **Complained:** there is a signal that the recipient reported the message as spam or an equivalent complaint, typically from a feedback loop or provider.

These signals are neither four completely independent labels nor a strictly linear one-way status list. A message can be accepted first, deferred multiple times, and finally delivered; or accepted and later hard-bounced; or delivered before a complaint appears. A deliverability tracking system must store **an event history and derived state**, rather than merely overwriting one status column based on whichever webhook arrived last.

## 1. Deliverability Differs from Submitting an Email

**Delivery** is the acceptance of a message by a receiving system at some point on its journey. **Deliverability** is used more broadly to refer to the likelihood an email lands where intended, such as the Inbox rather than Spam. An SMTP 250 signal or a provider "delivered" event does not necessarily confirm the recipient saw the email in their Inbox.

Example:

~~~text
Spring application
       |
       | JavaMailSender.send(...)
       v
Outbound SMTP relay
       |   <-- accepted by sender's relay
       |
       | Queue / routing / retries
       v
Recipient mail server (MX)
       |   <-- may accept, defer, or reject
       |
       v
Mailbox / spam folder / policy filters
       |
       | Feedback loop / user action
       v
Complaint signal (if any)
~~~

Normally there are at least three distinct outcome layers:

1. **Submission result:** did the application successfully submit the message to the transport/relay?
2. **Provider/remote delivery result:** did the relay and receiving mail server accept, delay, or bounce the message?
3. **Recipient interaction/reputation result:** were there complaints or other recipient signals?

Calling JavaMailSender alone is insufficient to observe all three. You also need provider events, a DSN/bounce mailbox, or corresponding feedback loop mechanisms.

### An Easily Misleading Example

~~~java
mailSender.send(message);
log.info("Email delivered to recipient");
~~~

The log above overclaims. Prefer logging:

~~~java
mailSender.send(message);
log.info("Email submitted to configured SMTP transport");
~~~

Even a "submitted" message must be tied to a specific transaction/notification and the SMTP transport's returned outcome. If the connection drops at an uncertain point, the application may be unable to tell whether the relay received the message.

## 2. Defining Accepted at the Exact Boundary

**Accepted** must always answer *accepted by whom?* and *accepted at which stage?*. For example:

| Signal | What It Confirms | What It Does Not Prove |
|---|---|---|
| SMTP relay returns success after DATA | That relay accepted responsibility to process the message per reply | Inbox receipt |
| Email sending API returns request accepted/queued | Provider received API request per service contract | Remote SMTP acceptance |
| Provider event ACCEPTED | An acceptance milestone defined by the provider | Identical meaning across all providers |
| Provider event DELIVERED | Per provider definition, delivery to destination reached a milestone | User read it or it is guaranteed in Inbox |

Some providers use **accepted** for API request intake while others use **processed/queued**; the word **delivered** may also refer to a remote server returning a success code. Therefore, **never assign meaning to an event name without confirming the source and the provider's event contract**.

### Accepted Is Not Terminal Success for the Entire Journey

A relay may accept a message and still return a DSN minutes or hours later. Causes can include:

- Remote recipient address does not exist.
- Mailbox or receiving system rejects per policy.
- Remote server stays temporarily unavailable until retry window expires.
- Content rejected at an intermediate hop.
- Other routing or delivery failures.

Thus an application can record submission accepted first and bounced later. Never treat accepted as "reached the customer."

### Is Accepted at the Message or Recipient Level?

One MIME message can list multiple To/Cc/Bcc recipients. Providers may emit one message-level event, whereas bounces and complaints occur **per recipient**. Storing one shared status for the whole message lets one recipient's failure corrupt another's status.

For personalized transactional emails, sending separately per recipient usually simplifies correlation, content privacy, and suppression management. If submitting multiple recipients together, design projections keyed by message-recipient.

## 3. Bounced: Returned or Undeliverable Messages

A **bounce** is a delivery-failure signal. In operations, two groups are commonly distinguished:

- **Hard bounce:** hard-to-recover or permanent failure for the current address/request, such as a nonexistent mailbox.
- **Soft bounce:** temporary failure, such as a full inbox or temporarily unavailable destination system.

This is a common business classification, **not an absolute mapping of every SMTP code**. Some providers emit a "bounce" event as the final outcome after multiple deferrals; some emit soft bounces separately; some use other categorization fields. Normalize from the provider's raw data.

### Common Bounce Causes

| Group | Example | Handling Approach |
|---|---|---|
| Address invalid | Mailbox does not exist | Stop retrying repeatedly to that address |
| Domain invalid | Unresolvable domain or no valid route | Verify address, error type, and recoverability |
| Policy rejection | Destination server rejects by policy | Inspect SMTP reply, domain auth, and reputation |
| Mailbox full | Mailbox over quota | May be temporary; follow provider retry policy |
| Temporary unavailable | MX temporarily unavailable | Deferred/retried before becoming final bounce |
| Message/content rejected | Size or content disallowed | Fix content/policy; do not retry blindly |
| Sender authentication/reputation | Rejected due to SPF/DKIM/DMARC or sending reputation policy | Investigate configuration and sending quality |

Do not assume every bounce is caused by a bad email address. A simultaneous spike in bounces across many domains can indicate a sender-side issue, authentication bug, DNS misconfiguration, or provider change.

### Bounce After Accepted Is Normal

Example:

~~~text
09:00:00  SMTP relay accepts message
09:00:02  Provider emits ACCEPTED
09:00:30  Recipient MX returns temporary failure
09:00:31  Provider emits DEFERRED
10:20:00  Retry policy expires
10:20:01  Provider emits BOUNCED
~~~

Here, accepted is a real event, yet not the final outcome. Bounced indicates final delivery failed per the provider.

### Permanent Bounces and Suppression

For addresses confirmed permanently invalid, applications should usually:

1. Record the bounce by recipient and provider event.
2. Add the address to a suppression list per policy.
3. Stop further ungrounded sending attempts.
4. Provide a way to fix/update to a valid address.
5. Do not erase bounce history the moment a user re-enters the same email.

A single soft bounce does not necessarily warrant permanent suppression. Thresholds, cooldowns, reasons, and provider-specific rules can apply. Avoid turning every transient error into a permanently blocked address.

## 4. Deferred: Temporary Delay Does Not Mean Final Failure

**Deferred** typically describes a delivery attempt that has not succeeded yet still has opportunities to retry. For instance, the remote MX returns SMTP 4xx, and the provider holds the message in its queue and schedules retries.

~~~text
Provider relay
     |
     | Try delivery to recipient MX
     v
SMTP 451 / temporary response
     |
     v
DEFERRED
     |
     +-- provider retries later --> delivered/accepted by recipient
     |
     +-- retry limit exhausted --> bounced/expired/failed
~~~

**Crucial point:** If a provider already accepted a message and is retrying downstream itself, the application should normally **not send a brand-new message just because a deferred event arrived**. Doing so creates two parallel delivery streams, raising duplicate risk and worsening throttling.

### Who Owns Retries?

| Stage | Component That Usually Retries |
|---|---|
| Application could not submit to outbound relay | Application outbox/worker per policy |
| Outbound relay received message yet remote MX returned 4xx | Relay/provider on its own schedule |
| Provider emitted deferred and indicates ongoing retries | Monitor provider; do not create new messages |
| Provider reports final retry exhaustion | Application marks bounce/failure and handles business flow |
| Unknown SMTP submission outcome | Reconcile or apply duplicate policy before retrying |

A system must document these responsibility boundaries; otherwise two independent retry loops can trigger a retry storm.

### Deferrals Can Occur Multiple Times

A message may undergo dozens of delivery attempts before concluding. Webhooks may emit multiple DEFERRED events with varying reasons. Do not flip status from DEFERRED to FAILED merely because one temporary error occurred.

For each deferral, it is useful to store:

- Occurrence timestamp.
- SMTP response code and enhanced status if supplied by the provider.
- Recipient domain/remote MX if supplied and permitted to store.
- Provider attempt count, if available.
- Next retry hint or next attempt time, if supplied by the provider.
- Provider message ID and internal notification ID.

Do not guess the next retry time if the provider does not publish it; display "awaiting provider retry" rather than inventing an ungrounded ETA.

## 5. Complained: Recipient Reported Spam

A **complaint** is a signal that a recipient reported unwanted mail, typically forwarded to the sender via a feedback loop, abuse reporting, or provider events. In email marketing systems, high complaint rates are a severe indicator of list quality, recipient expectations, and sending reputation.

A complaint is not a bounce:

- Bounce: the message could not be delivered or failed in transit.
- Complaint: negative feedback after the message was processed/delivered to the point a recipient could flag it.

Not every mailbox provider emits per-recipient complaint details to senders. Some provide only aggregate numbers or restrict details for privacy. **Zero complaint events does not prove no recipient clicked Report spam**.

### Upon Receiving a Credible Complaint

For marketing or optional emails, the workflow typically involves:

1. Authenticating the event source.
2. Storing the complaint with provider, message, recipient (if available), and timestamp.
3. Suppressing the recipient from relevant campaigns per policy.
4. Stopping queued marketing emails if policy requires.
5. Investigating causes: cadence, content, consent, list source, unsubscribe usability.
6. Monitoring complaint rates by campaign, sender domain, and provider.

Complaints can happen after a DELIVERED event. Thus a delivered message can still have **complained=true**; never overwrite all historical info with a single status.

### Complaints Differ from Unsubscribes

A user clicking unsubscribe is an opt-out request within a specific scope. A complaint is an unwanted-mail report, potentially arriving via the provider with different implications. Both can lead to marketing suppression, yet:

- Sources and reliability differ.
- Suppression scopes can differ.
- Timing of visibility differs.
- Regulations and handling workflows may differ by policy.

Do not clear complaint status merely because a user did not click unsubscribe. Nor treat every unsubscribe click as a spam complaint.

### Security Emails and Transactional Notifications

If an address generated a complaint, stop sending promotions to it. However, policies for security or mandatory transactional emails must be designed separately—covering address re-verification, alternative channels, or limiting harmful repeat sends. Never use one vague boolean `mailEnabled` across all mail types.

## 6. Comparison Table of the Four Signal Groups

| Signal | Finality? | Common Observation Sources | Appropriate Response |
|---|---|---|---|
| ACCEPTED | Not necessarily; often an intermediate milestone | SMTP submission reply or provider event | Record acceptance milestone; keep monitoring |
| BOUNCED | Usually a failure outcome for a delivery attempt | Provider bounce event, DSN/NDR | Classify permanent/temporary; suppress when needed |
| DEFERRED | Not final; awaiting retry or processing | SMTP 4xx / downstream event | Monitor; do not resend while provider retries |
| COMPLAINED | Negative feedback with long-term impact | Feedback loop, provider complaint event | Suppress optional mail and investigate reputation |

Never build a system around "accepted good, bounced bad, deferred wait, complained bad" while discarding reasons, recipients, and timelines. **An event stripped of source and context can lead to wrong decisions.**

## 7. Full Event Flow for One Notification

An application can maintain internal states:

~~~text
CREATED
   |
   v
PENDING_SUBMISSION
   |
   +-- SMTP submit fails before acceptance --> RETRY_PENDING
   |
   +-- accepted by outbound relay --> SUBMITTED
                                            |
                                            v
                                     PROVIDER_ACCEPTED
                                            |
                         +------------------+-------------------+
                         |                  |                   |
                         v                  v                   v
                      DEFERRED           DELIVERED            BOUNCED
                         |                  |
                         +---- retry ------>|
                                            |
                                            v
                                         COMPLAINT
~~~

This diagram shows common branches, not every possible order. Providers can deliver events with lag, duplicates, or out of order; complaints can follow delivered; bounces can follow an accepted milestone. Some events are historical facts rather than a new state that "regresses" success.

### Separate Transport State from Feedback Flags

Example model:

~~~java
public enum SubmissionStatus {
    NOT_STARTED,
    RETRY_PENDING,
    SUBMITTED,
    SUBMISSION_UNKNOWN,
    FAILED
}

public enum DeliveryStatus {
    UNKNOWN,
    ACCEPTED_BY_PROVIDER,
    DEFERRED,
    DELIVERED,
    BOUNCED
}

public record RecipientDeliveryView(
        SubmissionStatus submission,
        DeliveryStatus delivery,
        boolean complained,
        boolean suppressed,
        String latestReasonCode
) {
}
~~~

These are application-defined enums/records. **JavaMailSender does not directly provide delivered or complained states**. Those states must come from provider events or other data sources and map into the internal model.

### Why Not Use One Single Enum?

A single enum struggles to represent:

- SUBMITTED then BOUNCED.
- DELIVERED then COMPLAINED.
- DEFERRED multiple times before DELIVERED.
- A multi-recipient message where one recipient DELIVERED and another BOUNCED.
- SUPPRESSED due to a complaint before other queued jobs submitted.

Keep the event timeline, build a current projection for UI/alerts, and store flags/states needed for future sending decisions.

## 8. Which Data Sources Supply Events?

Spring Mail primarily handles building and submitting emails. Post-submission events usually come from other components:

| Source | Signals It Can Supply | Limitations |
|---|---|---|
| JavaMailSender/Jakarta Mail | Submit outcome, exceptions, readable SMTP replies | Cannot know delivery outcome after relay acceptance |
| SMTP relay logs | Receipt time, forwarding, defer/reject, queue IDs | Requires log access; format varies by relay |
| Email service provider webhooks | Accepted, delivered, bounce, defer, complaint per contract | May lag, duplicate, drop events, or lack recipient detail |
| Provider event API/export | Message history, events, error codes | Requires polling, pagination, quotas, and retention awareness |
| Bounce mailbox/DSN | Non-delivery reports or message statuses | Can be missing, late, hard to correlate; can be spoofed |
| Complaint feedback loop | Spam reports from participating mailboxes/providers | Does not cover all mailboxes; may be aggregate only |
| Admin/user actions | Unsubscribes, reports, support tickets owned by system | Not equivalent to all complaints recorded by mailbox providers |

Never build a "100% delivered" dashboard solely from `JavaMailSender` calls not throwing exceptions. Without provider event/DSN integration, label the metric **submission accepted** or **submitted**, and document observability limits clearly.

### Choosing the Event Ingestion Path

If the application uses an email provider with webhooks, that is usually the most convenient source for delivery lifecycle events. With an internal SMTP relay, use relay logs or bounce/feedback mailboxes. With only SMTP AUTH and no event exports, the application must accept that downstream outcomes remain **unknown**.

Never synthesize a delivered event after a fixed timeout simply because no bounce arrived. **Absence of failure evidence is not proof of successful delivery.**

## 9. SMTP Replies, DSNs, and Provider Webhooks Are Different Layers

### SMTP Submission Outcome

An SMTP session has representative steps:

~~~text
Client        SMTP relay
  |  EHLO         |
  |-------------->|
  |  STARTTLS     |
  |-------------->|
  |  AUTH         |
  |-------------->|
  |  MAIL FROM    |
  |-------------->|
  |  RCPT TO      |
  |-------------->|
  |  DATA         |
  |-------------->|
  |  message      |
  |-------------->|
  |  .            |
  |-------------->|
  |<----- 250 ----|  Accepted by this relay
~~~

A success code after DATA confirms that relay accepted responsibility for processing the message. Reply codes at MAIL FROM or RCPT TO reflect sending/recipient issues at submission time; never conflate them with asynchronous bounces after relay acceptance.

### DSN: Delivery Status Notification

DSN is the email transport outcome reporting mechanism. A DSN can indicate actions such as failed, delayed, or delivered per the DSN-emitting system, with diagnostic codes/statuses if present. Some systems emit non-standard or incomplete reports.

Conceptual example:

~~~text
Reporting-MTA: dns; relay.example.net
Final-Recipient: rfc822; buyer@example.org
Action: failed
Status: 5.1.1
Diagnostic-Code: smtp; 550 5.1.1 User unknown
~~~

This illustrates part of a DSN, not a complete message. Parsing real DSNs requires reading MIME `multipart/report` and `message/delivery-status` parts with an appropriate library; never treat every email with subject "Undelivered" as a trusted DSN.

### Feedback Loops and Complaints

Complaints may arrive via feedback reports email providers receive from mailbox providers or via provider event APIs. Data coverage can be limited. Not all complaints include recipient identifiers or original message IDs.

### Return-Path and the SMTP Envelope

Bounces typically tie to the **envelope sender/MAIL FROM** address. The From header shown to readers can differ from the envelope sender. Return-Path is a header added/shaped during delivery, not something the application should assemble itself to route bounces.

When operating your own relay, use envelope senders or VERP/tokenized mechanisms to identify recipients on bounces. With managed email providers, use provider-supported tracking/correlation IDs and bounce handling. Never assume editing Return-Path works identically across all providers.

## 10. Identifying and Correlating an Email Across the System

To join accepted, deferred, bounced, and complained events back to one notification, plan a correlation strategy from request creation.

### Common Identifiers

| ID | Origin | Role |
|---|---|---|
| Internal notification ID | Application | Durable ID representing the business request |
| Delivery attempt ID | Worker/outbox | Distinguishes individual submit attempts |
| RFC Message-ID | MIME message/header | Aids tracing messages across systems |
| Provider message ID | Email provider/relay | Correlates events to provider-managed messages |
| Provider event ID | Event system | Deduplicates redelivered webhooks |
| Recipient ID | Application | Internal recipient identity and preferences/suppression |
| Recipient address snapshot | At send time | Records the exact address used for the attempt |
| SMTP queue ID | Relay | Looks up transfer logs if exposed |

**Do not assume all IDs are identical.** Providers may generate a new message ID different from RFC Message-ID. Webhooks may carry provider message IDs while app logs hold only notification IDs; without saving the mapping, correlation becomes very difficult.

### Storing Mappings per Attempt

Example:

~~~text
notificationId:  notif-184
attemptId:       attempt-2
recipientId:     customer-42
recipient:       buyer@example.org
messageId:       <notif-184-attempt-2@mail.example.com>
providerMessageId: provider-msg-9901
provider:        primary-smtp
~~~

IDs are illustrative data. Whenever the provider returns an ID in an API response, store it with the attempt. With SMTP relays, provider message IDs may not appear as expected; inspect real logging/tracing capabilities before designing.

### Custom Correlation Headers

When tracing is needed, the application can add an internal header:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, "UTF-8");

helper.setFrom("notifications@example.com");
helper.setTo("buyer@example.org");
helper.setSubject("Order confirmation");
helper.setText("Your order has been recorded.");

message.setHeader("X-Notification-ID", "notif-184");
mailSender.send(message);
~~~

Custom headers can appear in raw emails and traverse external systems; **never put PII, email addresses, credentials, tokens, or sensitive IDs** into headers. Never let users directly control header values. Some providers offer superior metadata/tag mechanisms and may strip custom headers.

### One Message, Multiple Recipients

If provider events carry individual recipients, correlation keys must include recipient or recipient ID. One provider message ID can map to multiple recipients; never put a unique constraint solely on provider message ID if that prevents storing per-recipient outcomes.

### Message-ID Does Not Guarantee Exactly-Once

When the final SMTP reply is lost after DATA, the application may retry and create duplicates. Keeping a stable Message-ID aids tracing yet does not force relays/mailboxes to deduplicate. Internal idempotency keys prevent duplicate business requests; they do not guarantee recipients receive a message strictly once.

## 11. Designing Tables for Events and Current State

A clean design can separate three datasets:

1. **Notification/outbox:** who needs which message and why.
2. **Delivery attempts:** each submission to SMTP/API, with timestamps and provider IDs.
3. **Provider events:** each accepted/bounced/deferred/complained or delivered signal from outside.

A recipient-level projection aggregates events into current state for dashboards and suppression logic.

### Illustrative SQL Schema

~~~sql
CREATE TABLE email_notification (
    id                  VARCHAR(100) PRIMARY KEY,
    notification_type   VARCHAR(100) NOT NULL,
    recipient_id        VARCHAR(100) NOT NULL,
    recipient_address   VARCHAR(320) NOT NULL,
    created_at          TIMESTAMP NOT NULL
);

CREATE TABLE email_delivery_attempt (
    id                  VARCHAR(100) PRIMARY KEY,
    notification_id     VARCHAR(100) NOT NULL,
    provider_key        VARCHAR(100) NOT NULL,
    provider_message_id VARCHAR(250),
    smtp_message_id     VARCHAR(250),
    submission_status   VARCHAR(40) NOT NULL,
    started_at          TIMESTAMP NOT NULL,
    finished_at         TIMESTAMP,
    FOREIGN KEY (notification_id)
        REFERENCES email_notification(id)
);

CREATE TABLE email_provider_event (
    id                   VARCHAR(100) PRIMARY KEY,
    provider_key         VARCHAR(100) NOT NULL,
    provider_event_id    VARCHAR(250),
    attempt_id           VARCHAR(100),
    recipient_address    VARCHAR(320),
    event_type           VARCHAR(50) NOT NULL,
    reason_code          VARCHAR(100),
    occurred_at          TIMESTAMP,
    received_at          TIMESTAMP NOT NULL,
    raw_payload_ref      VARCHAR(400),
    FOREIGN KEY (attempt_id)
        REFERENCES email_delivery_attempt(id)
);

CREATE TABLE email_recipient_delivery (
    notification_id      VARCHAR(100) PRIMARY KEY,
    delivery_status      VARCHAR(40) NOT NULL,
    complained           BOOLEAN NOT NULL,
    suppressed           BOOLEAN NOT NULL,
    last_event_at        TIMESTAMP,
    updated_at           TIMESTAMP NOT NULL,
    FOREIGN KEY (notification_id)
        REFERENCES email_notification(id)
);
~~~

This is an abbreviated illustrative schema; add indexes, provider-appropriate unique constraints, multi-recipient columns if supported, real time-zone types, tenant isolation, retention, and access controls. With multiple recipients per notification, projection keys must include recipient ID or use a separate email-recipient record.

### Unique Key for Provider Events

If the provider supplies a stable event ID, enforce a unique constraint on **provider + event ID**, plus account scope if IDs are only unique per account. Provider-defined IDs are sometimes not globally unique. Never use event timestamp or type as a unique key since multiple valid events can share identical timestamps.

Example:

~~~sql
CREATE UNIQUE INDEX uq_provider_event
ON email_provider_event(provider_key, provider_event_id);
~~~

When `provider_event_id` can be null, define explicit deduplication rules and account for your database's unique/null behavior. Events lacking reliable IDs cannot be strictly deduplicated by arbitrarily concatenating fields; you can store a payload hash plus a scoped key while understanding the risk of colliding two valid events.

### Why Keep Events Append-Only?

If a webhook arrives late or a bug occurs in projection logic, event history lets you:

- Rebuild state.
- Investigate deferral/bounce timelines.
- Distinguish redelivered events from multiple actual retries.
- Verify whether the system processed a complaint.
- Reconcile provider exports and metrics.

You do not need to keep raw payloads indefinitely. If retaining raw payloads, enforce retention policies, encryption, access controls, and PII scrubbing. A properly protected event log can suffice to recompute projections without keeping full raw JSON.

## 12. Normalized Event Model in Java

Each provider uses its own field names and event types. Map them to a neutral model, and let business logic operate on that model.

~~~java
package com.example.mail.delivery;

import java.time.Instant;

public enum DeliveryEventType {
    ACCEPTED,
    DELIVERED,
    DEFERRED,
    BOUNCED,
    COMPLAINED,
    UNKNOWN
}

public record MailDeliveryEvent(
        String providerKey,
        String providerEventId,
        String providerMessageId,
        String internalNotificationId,
        String recipientAddress,
        DeliveryEventType type,
        String providerReasonCode,
        Instant occurredAt,
        Instant receivedAt
) {
}
~~~

This record and enum are application-defined types; Spring Mail does not include a built-in `MailDeliveryEvent` class with this structure. If a provider emits events like `processed`, `dropped`, `blocked`, or `spamreport`, the mapper must explicitly define conversions and `UNKNOWN` cases.

### Do Not Lose the Raw Reason

Normalizing into `BOUNCED` helps dashboards, yet keeping only that label prevents operators from distinguishing:

- Permanent mailbox not found.
- Sender policy violation.
- Message too large.
- Domain DNS issue.
- Reputation-based provider block.

Retain sanitized error codes/families and source event types from the provider, plus time-bounded pointers to raw payloads if truly needed for investigation.

## 13. Receiving Events via Webhooks

An email provider can send HTTP POSTs to an application endpoint when messages are accepted, delivered, deferred, bounced, or complained. Webhooks are **external data sources**, so verify before trusting events.

### Event Ingestion Flow

~~~mermaid
flowchart TD
    A["Email provider webhook"] --> B["HTTPS endpoint"]
    B --> C["Verify signature / timestamp"]
    C --> D{"Valid?"}
    D -- "No" --> E["Reject and record safe audit"]
    D -- "Yes" --> F["Parse and normalize"]
    F --> G["Durably store event / inbox"]
    G --> H["Ack provider"]
    G --> I["Async event consumer"]
    I --> J["Deduplicate + correlate"]
    J --> K["Update timeline / projection"]
    K --> L["Suppression / metrics / alert"]
~~~

Returning HTTP 2xx must be tied to **durable storage** of the event or successful handoff to a durable queue, not merely receiving the payload in controller memory. If the database/broker fails transiently, HTTP response behavior must align with the provider's retry contract; never acknowledge success if the event could be lost right afterward.

### Edge Webhook Verification

Verify per the provider's contract:

- HTTPS and endpoints exposing no unnecessary data.
- Provider's signature or authentication scheme.
- Integrity of the **raw request body** per provider rules.
- Replay-prevention timestamp/tolerance if supported by provider.
- Key rotation and multiple valid signing keys during transition windows.
- Limits on body size, events per batch, and timeouts.
- Distinction between test/staging and production accounts.
- Handling invalid signatures before ever touching suppression.

Never invent a header like `X-Provider-Signature` and assume every email provider uses it. Header names, encoding, canonicalization, HMAC/public-key verification, and status codes must match the integrated provider's documentation.

### Illustrative Spring Boot Controller Code

~~~java
package com.example.mail.delivery;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/internal/webhooks/email-provider")
public class MailProviderWebhookController {

    private final ProviderWebhookVerifier verifier;
    private final ProviderEventInbox inbox;

    public MailProviderWebhookController(
            ProviderWebhookVerifier verifier,
            ProviderEventInbox inbox) {
        this.verifier = verifier;
        this.inbox = inbox;
    }

    @PostMapping(consumes = "application/json")
    public ResponseEntity<Void> receive(
            @RequestBody byte[] rawBody,
            @RequestHeader("X-Provider-Signature")
                    String signature,
            @RequestHeader("X-Provider-Timestamp")
                    String timestamp) {

        if (!verifier.isAuthentic(
                rawBody, signature, timestamp)) {
            return ResponseEntity
                    .status(HttpStatus.UNAUTHORIZED).build();
        }

        // Must be a durable store operation with dedup or
        // an appropriate inbox/outbox transaction.
        inbox.storeVerifiedPayload(rawBody);

        return ResponseEntity.accepted().build();
    }
}
~~~

**Example assumptions:** a specific provider is configured with those two hypothetical headers and `ProviderWebhookVerifier` implements that provider's signature/timestamp algorithm. This is not a copy-paste snippet for all providers; in real systems, adapt headers, authentication, and event schemas to integration docs.

### Verifier and Inbox Interfaces

~~~java
public interface ProviderWebhookVerifier {
    boolean isAuthentic(
            byte[] rawBody,
            String signature,
            String timestamp);
}

public interface ProviderEventInbox {
    void storeVerifiedPayload(byte[] rawBody);
}
~~~

When `storeVerifiedPayload` fails, exceptions must map to server error responses per retry mechanics rather than silently returning 202. An already-stored duplicate event may be acknowledged cleanly as long as deduplication remains consistent.

### What If Webhooks Use Forms or Event Batches?

Do not assume every webhook is a single-event JSON object. Providers may send form data, JSON arrays, multiple events per request, or cloud event buses/queues. Controllers, verifiers, and parsers must match the exact format; in particular, signatures must be computed over the exact representation defined by the provider. Parsing and re-serializing JSON before verification can break signatures.

## 14. Handling Duplicate, Late, and Out-of-Order Webhooks

Webhook providers normally deliver under **at-least-once** semantics: without an acknowledgment response, providers redeliver events. Even if a provider promises ordering, networks, retries, and distinct workers can still scramble processing order.

Example original timeline:

~~~text
09:00:00  ACCEPTED
09:01:00  DEFERRED
09:03:00  DELIVERED
09:10:00  COMPLAINED
~~~

Yet webhook arrival order at the application might be:

~~~text
09:03:02  DELIVERED
09:03:04  ACCEPTED (late-arriving older event)
09:03:05  DEFERRED (late-arriving older event)
09:10:03  COMPLAINED
09:10:10  COMPLAINED (duplicate delivery)
~~~

Simply writing `status = event.type` on every webhook can **regress state from DELIVERED back to DEFERRED** when an older event arrives late. Or two duplicate complaint webhooks can be counted as two separate complaints.

### Two Independent Rules

1. **Deduplication:** record a unique event only once per the provider-guaranteed key.
2. **Projection ordering:** update current state using business rules, never simply taking the most recently received event.

Deduplication does not solve ordering: ACCEPTED and BOUNCED have distinct event IDs and both are valid. Ordering does not solve deduplication: the same COMPLAINED event can be delivered twice.

### Conceptual Processing Algorithm

~~~text
receive verified event:
    persist raw/normalized event durably

process event in transaction:
    if provider event key already handled:
        ACK duplicate, do not reapply side effects

    correlate provider ID, attempt, and recipient
    if no matching attempt:
        store UNMATCHED for bounded reconciliation
        do not attach to another recipient by guess

    append immutable event
    rebuild/update projection with source-specific rules
    if newly observed complaint or permanent bounce:
        apply suppression policy idempotently
    commit
~~~

**Note:** Ensure recording the event and marking it "processed" stay consistent. If dedup state commits yet suppression fails to commit, replays might skip the event and never suppress. If suppression triggers work in another system, use a durable outbox or separate event so the task is never lost.

### Use occurredAt or receivedAt?

- **occurredAt:** when the provider says the event actually happened.
- **receivedAt:** when your system received and persisted the event.

Both timestamps are useful. Never assume provider and application clocks are perfectly synchronized; never treat `occurredAt` as infallible or sufficient to resolve ties when a provider only gives second-level precision.

With multi-source data, event ordering may require provider-specific sequence IDs, terminal-state semantics, event timestamps, and attempt history. Never invent one universal timestamp comparison and assume it holds across every source.

## 15. Projection Update Rules

A projection must clearly show what is known, what is unknown, and when investigation is needed. Suggested principles:

- ACCEPTED: record provider/relay acceptance milestone; never erase an already-recorded final delivery outcome.
- DEFERRED: record deferral and reason; may set waiting status if no newer terminal outcome exists.
- DELIVERED: record remote delivery milestone as defined by provider; do not infer inbox/read.
- BOUNCED: record bounce and classification; if terminal for that attempt/recipient, show failure.
- COMPLAINED: set feedback flag, apply suppression per policy; do not erase DELIVERED history.

### Why Is There No Simple Global Precedence Order?

"BOUNCED always beats DELIVERED" or "DELIVERED always beats BOUNCED" can both be wrong if:

- Two events belong to two different delivery attempts.
- A delayed bounce event concerns a message accepted at one relay while a delivery event refers to another step.
- The provider defines soft bounces differently from final bounces.
- Event timestamps are unreliable or recipient IDs are missing.

Compare within **provider + attempt + recipient**, then apply source semantics. If conflicting events cannot be resolved, flag for reconciliation and keep both events rather than deleting a valid event to "tidy up" a dashboard.

### Example Event Processing Service

~~~java
package com.example.mail.delivery;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DeliveryEventProcessor {

    private final DeliveryEventRepository eventRepository;
    private final AttemptResolver attemptResolver;
    private final DeliveryProjectionRepository projectionRepository;
    private final SuppressionPolicyService suppressionPolicy;

    public DeliveryEventProcessor(
            DeliveryEventRepository eventRepository,
            AttemptResolver attemptResolver,
            DeliveryProjectionRepository projectionRepository,
            SuppressionPolicyService suppressionPolicy) {
        this.eventRepository = eventRepository;
        this.attemptResolver = attemptResolver;
        this.projectionRepository = projectionRepository;
        this.suppressionPolicy = suppressionPolicy;
    }

    @Transactional
    public void handle(MailDeliveryEvent event) {
        // Insert-if-absent must have a unique constraint / atomicity.
        boolean inserted = eventRepository.insertIfAbsent(event);
        if (!inserted) {
            return;
        }

        var resolution = attemptResolver.resolve(event);
        if (resolution.isEmpty()) {
            eventRepository.markUnmatched(
                    event.providerKey(), event.providerEventId());
            return;
        }

        var key = resolution.get();
        var view = projectionRepository.lockByRecipientKey(key);

        view.applyAccordingToProviderSemantics(event);
        projectionRepository.save(view);

        if (event.type() == DeliveryEventType.COMPLAINED
                || view.isPermanentBounceNewlyObserved()) {
            suppressionPolicy.applyIfRequired(key, event);
        }
    }
}
~~~

Interfaces and methods here are **Java-shaped pseudocode**, not built-in Spring Mail APIs. Real projects must define resolution/projection types, unique constraints, and per-provider semantics. `suppressionPolicy` must write data inside the same transaction or emit a durable outbox event, avoiding non-rollbackable external side effects.

### Never Force-Match Unmatched Data

An event with an unfamiliar `providerMessageId` can stem from:

- Messages sent by another account.
- Events arriving before attempt mapping committed.
- Providers transforming IDs.
- Emails sent outside the application.
- Webhooks misconfigured across environments/accounts.
- Corrupted or spoofed payloads.

Store as UNMATCHED for a bounded period, run controlled reconciliation, and alert when unmatched rates rise. Never guess matches using only email address + approximate timestamp to alter random messages.

## 16. Syncing State with the Sending Outbox

An application may use an outbox for durable email sending. Outbox state and delivery events are two layers:

~~~text
OUTBOX / SUBMISSION           PROVIDER DELIVERY

PENDING
   |
   v
PROCESSING
   |
   v
SUBMITTED ------------------> ACCEPTED
                                |
                                +--> DEFERRED
                                |       |
                                |       +--> DELIVERED
                                |       +--> BOUNCED
                                |
                                +--> BOUNCED
                                +--> DELIVERED
                                         |
                                         +--> COMPLAINED
~~~

If JavaMailSender succeeds, the outbox record can move to SUBMITTED. Never move it straight to DELIVERED. Conversely, if a provider DELIVERED event arrives before the worker wrote SUBMITTED due to a transient DB error, record the event and reconcile rather than discarding it because "the outbox hasn't sent yet."

### Uncertain SMTP Submission

Example:

1. Worker sends DATA to relay.
2. Relay accepts message.
3. Client loses connection before receiving final response.
4. Worker marks `SUBMISSION_UNKNOWN`.
5. Provider event ACCEPTED or DELIVERED arrives later.

Authenticated provider events can assist reconciliation when mappings are trustworthy. Without events or provider lookup support, duplicate risk remains on retries. Do not immediately resend simply because the outbox lacks SUBMITTED.

### Retry Ownership by Boundary

When the outbox has not submitted yet, application workers can retry. When the provider accepted and is DEFERRED, the provider normally owns retries to the remote MX. If the application sends a brand-new message, it can create duplicates for both recipient and provider.

**One message should not have two independent retry mechanisms for the same transport leg without state coordination.**

## 17. Designing the Suppression List

A suppression list tracks recipients or recipient scopes the system **must not send to** under specific rules. A suppression record may contain:

| Field | Meaning |
|---|---|
| recipientKey | User/recipient ID or policy-normalized address |
| tenant/providerScope | Applicable scope |
| reason | HARD_BOUNCE, COMPLAINT, UNSUBSCRIBE, ADMIN_BLOCK... |
| sourceEventId | Triggering event |
| categoryScope | Marketing, product updates, or other policy |
| createdAt | Effective timestamp |
| expiresAt | If suppression expires per policy |
| reviewStatus | Whether intervention or re-verification is needed |

### Do Not Use One Boolean for Everything

If a user unsubscribes from newsletters, the app may still need to send security emails per policy; if a mailbox hard-bounced as nonexistent, trying to send OTPs there is pointless too. Complaints require strict rules around send limits and recipient verification. Apply suppression by **reason, category, recipient validity, and policy**, never one global variable.

### Hard Bounces

A credible hard bounce can suppress the address from further sends. Users can be prompted to update/re-verify their address per business workflow. Never lift suppression merely because a user edited their display name.

### Repeated Soft Bounces

Consecutive soft bounces within a period may trigger temporary suppression, though thresholds and durations must match policy and provider behavior. Never "permanently ban" all soft bounces under one blanket rule.

### Complaints

Credible complaints typically require stopping marketing/optional emails for the affected recipient. Do not wait for daily batch analytics before suppressing if events can be processed promptly. Also re-check preferences at worker dispatch so jobs queued prior to the complaint are stopped.

### Never Suppress from Unauthenticated Webhooks

If anyone can POST a COMPLAINED event to a public endpoint, attackers can make the application stop sending critical emails. Verify signatures, account scope, and valid recipient correlation before updating suppression.

## 18. Separating Deliverability Metrics and Quality Metrics

Some metrics describe transport; others describe list quality and recipient feedback:

| Metric | Question Answered |
|---|---|
| Submission success | How many requests did the relay/provider accept? |
| Provider accepted | How many messages did the provider confirm accepting/queuing? |
| Deferred count/rate | How many messages hit temporary obstacles? |
| Bounce count/rate | How many messages had failure outcomes? |
| Hard bounce rate | Rate of permanent address/policy failures by category |
| Complaint count/rate | How many spam reports occurred within observed sources? |
| Delivered count/rate | How many messages have provider delivery confirmation? |
| Time to delivery | How long from accepted to delivered per provider? |
| Delivery event lag | How long until events reach the system? |
| Unmatched event rate | How many events could not be correlated? |
| Suppression count | How many recipients are currently blocked by reason/category? |

### Define the Denominator Before Computing Rates

A rate is meaningful only when specifying:

- Is the unit **message**, **recipient**, or **attempt**?
- Is the denominator **submitted**, **accepted**, **delivered**, or **eligible recipients**?
- Is the time window based on createdAt, acceptedAt, event occurredAt, or receivedAt?
- Did you wait long enough for delayed bounces/complaints to arrive?
- Does the provider emit complete event types for the recipient set?

Do not take "complaint webhooks / all emails across every channel" as a single ratio and compare providers when observability and definitions differ.

### Illustrative Formulas

Within the same cohort, same provider, and consistent definitions:

\[
\text{Bounce Rate} =
\frac{\text{Bounced recipient-messages}}
{\text{Accepted recipient-messages}}
\times 100\%
\]

\[
\text{Deferral Incidence} =
\frac{\text{Recipient-messages that ever had deferred}}
{\text{Accepted recipient-messages}}
\times 100\%
\]

\[
\text{Complaint Rate} =
\frac{\text{Recipient-messages with observed complaint}}
{\text{Recipient-messages in published denominator}}
\times 100\%
\]

**The complaint rate denominator has no single choice valid for every provider.** One dashboard may use accepted or delivered depending on reporting standards. A limited-coverage feedback loop must not be presented as the complaint rate across all mailboxes without a caveat. A message deferred three times counts as **one deferred message** in deferral incidence, not three messages.

### Never Divide by Zero

If a cohort has zero accepted messages, the bounce rate under the formula above is *undefined*, not 0%. UIs should display "N/A" or missing denominator rather than falsely reporting 0% to look healthy.

## 19. Cohorts and Event Latency

Measuring bounce rate as bounces received today divided by emails sent today introduces skew:

- Messages sent yesterday have bounces arriving today.
- Messages sent today have not had time for providers to report outcomes.
- Complaints can arrive days after delivery.
- Provider webhooks can lag due to outages or queue backlogs.

One approach is grouping by **submit/accept time cohort**, then observing outcomes over an appropriate maturation window. Real-time dashboards can display provisional figures and update as late events arrive.

### Cohort Example

~~~text
Cohort creation date: 2026-11-10
Accepted recipient-messages: 10,000
    |
    +-- day 10: 70 bounce events
    +-- day 11: 20 bounce events
    +-- day 12: 10 bounce events
    |
    +-- by cohort: 100 unique recipient-messages bounced
~~~

This example illustrates cohort thinking, not a deliverability benchmark. If all 100 events were webhook retries for the same message, the actual unique bounce count is much lower; deduplicate before counting.

### Real-Time vs. Matured Reports

Distinguish:

- **Provisional:** numbers close to send time, possibly missing late bounces/complaints.
- **Matured:** numbers after a defined observation waiting period.
- **Reconciled:** numbers reconciled against provider exports or other authoritative sources.

Do not advertise a 100% delivered rate seconds after submission while the provider still holds many messages in queues.

## 20. Dashboards by Email Type and Recipient Group

A useful deliverability dashboard typically slices by:

- Provider/account/SMTP route.
- Sender domain/verified identity.
- Notification category: security, transactional, marketing.
- Campaign/template version.
- Recipient domain or sensible domain group.
- Country/region where legally grounded and appropriate.
- Time/cohort.
- Bounce and complaint reasons.

### Conceptual Overview Layout

~~~text
Provider: transactional-primary       Period: last 24 hours

Accepted                    18,420
Deferred (unique messages)      310
Bounced (unique messages)       128
Complained (observed)            12
Delivered (provider events)   17,802

Oldest accepted without terminal event: 2h 14m
Provider webhook lag p95: 42s
Unmatched events: 8
Hard bounce reason top: mailbox unavailable / address rejected
~~~

All numbers above are examples, not real data or benchmarks. Sets can **overlap**: one message can be both deferred and delivered; one message can be delivered and then complained. Therefore rows **do not necessarily sum to accepted**. UIs must clearly label whether numbers are event counts, unique message counts, or current-status counts.

### Do Not Use Full Email Addresses as Metric Labels

Micrometer/Prometheus labels explode in cardinality if you add recipient IDs or email addresses. That wastes memory and risks exposing personal data. Use bounded labels like provider, category, domain group, and reason family. Look up specific notification IDs in access-controlled logs/event stores.

### Suggested Metrics

~~~text
mail_provider_events_total{provider,type}
mail_provider_event_duplicates_total{provider}
mail_provider_event_unmatched_total{provider}
mail_bounces_total{provider,reason_family}
mail_deferrals_total{provider,reason_family}
mail_complaints_total{provider,category}
mail_delivery_event_lag_seconds{provider}
mail_accepted_without_terminal_age_seconds{provider}
mail_suppression_new_total{reason,category}
~~~

Metric names are application-defined, not built-in Spring Mail metrics. For "accepted without terminal age," define which event sources have terminal semantics; never assume every provider's ACCEPTED is terminal.

## 21. Monitoring and Anomaly Alerting

Deliverability monitoring is more than storing events. Detect shifts early enough to stop feeding a systemic failure or damaging sender reputation.

### Signals Worth Alerting On

| Signal | What May Be Happening | Initial Action |
|---|---|---|
| Sharp rise in hard bounce rate | Low-quality address list or provider rejecting | Slice by sender/recipient domain and reason |
| Rising deferral rate | Recipient MX throttling, DNS error, temporary outage | Inspect SMTP codes and provider queues |
| Rising complaints | Unwanted email, wrong content/cadence | Pause or throttle campaign; inspect consent/suppression |
| Accepted rises while delivered lags | Queues backing up, webhook errors, or provider delay | Check event lag, provider status, and backlog |
| No webhooks seen for a long period | Endpoint, auth, or provider event delivery broken | Check webhook health and dead-letter queues |
| Rising unmatched events | Broken provider message ID mapping or external sends | Check integration/account/environment |
| Rising duplicate webhooks | Provider retries or slow/failing endpoint ACKs | Check responses, idempotency, and latency |
| Many bounces at one domain | Local issue at one receiving domain or domain policy | Investigate domain-specifically; do not block globally |
| Sudden drop in accepted | SMTP AUTH, quota, provider API failure, or drop in demand | Cross-check submission attempts and business sources |

### Do Not Set Thresholds with One Absolute Value

A system sending 20 emails per day can hit a 5% bounce rate from a single failed email. A system sending millions of emails can affect huge numbers of users from a tiny percentage shift. Account for:

- Minimum denominator size.
- Baselines by day of week, campaign, and category.
- Rate of change relative to history.
- Absolute counts.
- Criticality of the email.
- Observability coverage per provider/recipient domain.

For OTP emails, high delivery latency can be severe even with low bounce counts. For marketing, a complaint spike may require pausing campaigns before a full cohort matures.

### Actionable Alerts

Alerts should tell on-call responders what to do:

- "SMTP accepted dropped; check AUTH and upstream provider."
- "Deferrals spiked at one recipient domain; inspect 4xx codes and throttling."
- "Complaints spiked for campaign X; pause campaign and audit consent."
- "Webhook lag increased; check queue consumers and provider retries."

Do not page on every individual deferral as a widespread outage. Deferrals are normal behavior in SMTP systems; what matters are **rates, duration, and final outcomes**.

## 22. Analyzing Bounce and Deferral Root Causes

Provider reason codes and text are valuable diagnostics. However, they vary across providers and can contain recipient info. Map them into an internal taxonomy for reporting.

### A Minimal Taxonomy

~~~java
public enum DeliveryReasonFamily {
    INVALID_ADDRESS,
    MAILBOX_FULL,
    TEMPORARY_UNAVAILABLE,
    RATE_LIMIT_OR_THROTTLING,
    AUTHENTICATION_OR_POLICY,
    CONTENT_REJECTED,
    MESSAGE_TOO_LARGE,
    DNS_OR_ROUTING,
    SPAM_OR_REPUTATION,
    UNKNOWN
}
~~~

Do not treat the taxonomy as an SMTP standard definition. It is purely an internal classification model. An enhanced status code like `5.1.1` commonly suggests a nonexistent mailbox, yet rely on the specific source. Version mapping rules so historical numbers remain explainable when rules change.

### Step-by-Step Analysis

When seeing BOUNCED, check:

1. Which relay initially accepted it?
2. Did the remote MX return a specific SMTP code?
3. Was there a prior DEFERRED, and for how long?
4. How many times did the provider retry?
5. Was the bounce hard, soft, or provider-specific?
6. Was the recipient address verified or freshly entered by a user?
7. Is the issue concentrated in one sender domain, IP, tenant, or campaign?
8. Were there recent SPF/DKIM/DMARC or sender policy changes?

### Example: Many Deferrals at One Recipient Domain

~~~text
Provider: relay-a
Recipient domain: example.net
Symptoms: 4.7.x responses, increasing deferrals
Other recipient domains: normal
~~~

Focus remediation on that provider/domain, inspecting send rate and throttling causes. Do not mark recipients across all domains as invalid. If the provider is retrying accepted messages, monitor rather than firing duplicate `send()` calls.

### Example: Hard Bounces Spike After a List Import

If bounces spike after importing a list, audit address quality, consent collection, list provenance, and unverified addresses. Pause the campaign if needed; never use retries to hammer permanently rejected addresses.

## 23. Email Authentication Supports Deliverability but Does Not Replace Event Tracking

A sound sending configuration attends to sender identity, DNS, and reputation:

- **SPF:** publishes authorized sending sources for a domain in the right envelope identity context.
- **DKIM:** signs selected headers/body so receivers verify integrity and signing-domain identity.
- **DMARC:** sets policy and alignment based on From header domain with SPF or DKIM, plus reporting.
- **TLS:** protects transport connections when properly established and verified.

These factors affect whether receiving mail servers accept or reject messages; they **do not replace tracking accepted, bounced, deferred, and complained events**.

### Avoid Over-Inferring

- Passing SPF/DKIM/DMARC does not guarantee Inbox placement.
- Working STARTTLS does not guarantee recipients never complain.
- Failing DKIM does not automatically mean every message bounces; it depends on receiving server policy.
- Successful SMTP AUTH only confirms submission permission at the relay, not remote deliverability.

When bounces/deferrals shift after a deployment or DNS update, compare sender configs, From alignment, DKIM signing, IP/domain reputation, and provider responses. Never change DNS records randomly over a few isolated error events.

## 24. Complaint Rates and Optional Email Sending Policy

Complaints are an ultra-sensitive list quality signal. When complaints rise, look beyond transport:

- Did the address genuinely opt into this content?
- Does the email match expectations at signup time?
- Is unsubscribe easy to find and working?
- Is sending frequency too high?
- Did a retry/replay bug send the same campaign repeatedly?
- Has content drifted far from the consented purpose?
- Is the provider supplying full complaint data or only from a subset of mailboxes?

### Do Not "Fix" Complaint Rate by Changing the Denominator

If complaint counts rise, switching the denominator from delivered to all attempted or adding unsent messages to shrink the ratio destroys consistency. Dashboards need one versioned definition with explicitly documented observation scope.

### Should an Unsubscribe Confirmation Email Be Sent?

Sending an action confirmation notice depends on product and policy. Never treat it as an excuse to keep sending marketing. If sending a confirmation notice, include only preference-change info and avoid adding promotions.

### Complaints Are Not Individual Metrics

Do not try guessing who reported spam when providers supply only aggregate data. Restricted feedback scope may reflect mailbox provider privacy policies.

## 25. Security and Protecting Deliverability Data

Provider events can include recipient addresses, reason text, message subjects, provider IDs, IPs, or other personal fields. Applications must manage them as sensitive operational data.

### Securing Webhooks

- Verify signatures/authentication before trusting events.
- Limit body size and event counts per request.
- Enforce anti-replay within provider-supported windows.
- Never use staging signing keys in production.
- Rotate webhook signing keys via formal processes.
- Rate-limit requests and check sources where helpful, without relying solely on IP allowlists.
- Never display raw webhook payloads directly in unprotected UIs.
- Keep dependencies/parsers updated to prevent vulnerabilities on untrusted data.

### Preventing Spoofed Bounces

DSN/NDR emails arriving in a mailbox can be spoofed. When running an inbound bounce processor, validate format, source, and sufficiently trustworthy correlation tokens/identifiers before suppressing addresses. Never remove recipients from lists simply because an external sender sent an email with subject "Mail Delivery Failed."

### Retention

Classify data:

| Data | Example Policy |
|---|---|
| Normalized provider events | Retain as long as needed for operations/audits |
| Raw provider webhook bodies | Keep briefly or only for active investigation; secure and purge per retention |
| Complaint/suppression records | Retain long enough to avoid accidental resends; check privacy requirements |
| Aggregate metrics | Retain longer if PII-free and permitted |
| Email bodies/attachments | Do not copy into event stores by default |
| SMTP diagnostic text | Sanitize or restrict access since it may hold recipients/identifiers |

No single retention period fits every organization; follow business purposes, applicable regulations, and data-protection policies.

### Structured Logging

A safe log entry can look like:

~~~json
{
  "event": "mail_delivery_event_processed",
  "notificationId": "notif-184",
  "providerKey": "primary-mail",
  "type": "BOUNCED",
  "reasonFamily": "INVALID_ADDRESS",
  "duplicate": false,
  "correlated": true
}
~~~

Never put full recipient addresses, tokens, SMTP passwords, or raw payloads in logs unnecessarily. When lookup by recipient is required, use internal IDs and role-restricted tools.

## 26. Handling Events During Provider Outages

When provider webhooks are disrupted, messages may still be processed while the application fails to receive events on time.

### Never Automatically Replace UNKNOWN with DELIVERED

If events are missing, keep status as UNKNOWN or ACCEPTED_BY_PROVIDER and surface event lag/reconciliation state. Never fabricate positive outcomes to shrink UNKNOWN counts on dashboards.

### Reconciliation via Provider API/Export

If the provider offers an event lookup API:

1. Identify the time range or set of message IDs to reconcile.
2. Call the API with appropriate rate limits, pagination, and retries.
3. Pass events through the exact same dedup/projection pipeline as webhooks.
4. Never maintain conflicting state logic between webhooks and polling.
5. Record reconciliation outcomes and counts of still-unknown records.

Provider APIs may retain events only for a limited window; schedule reconciliation before external retention expires.

### Provider Sending Batch Events After Outages

When webhooks recover, tens of thousands of events may arrive at once. The inbox must persist durably, consumers must process in batches, protect databases, and keep latency reasonable. If complaints surged in the backlog, prioritize suppression processing so marketing stops going to complainants.

### Switching Providers

When switching SMTP providers, IDs and event names may change. Never join events across two providers solely by Message-ID without guaranteeing uniqueness and accurate mapping. Keep `providerKey`, account scope, and attempts; normalize events into the common model while storing source-specific fields needed for investigation.

## 27. Event-Driven Test Scenarios

Testing requires both unit tests for projections and integration tests for webhooks/inboxes:

| ID | Scenario | Expected Result |
|---|---|---|
| E01 | ACCEPTED then DELIVERED | Persist both events; projection reflects delivered milestone |
| E02 | ACCEPTED then DEFERRED then DELIVERED | Preserves deferral history; final delivery outcome not erased |
| E03 | ACCEPTED then BOUNCED | Bounce outcome and reason persisted |
| E04 | DELIVERED then COMPLAINED | Preserves delivery evidence; sets complained and suppression per policy |
| E05 | DELIVERED webhook arrives before ACCEPTED | Late accepted does not regress projection |
| E06 | DEFERRED arrives after DELIVERED | Does not flip current outcome to deferred merely due to arrival order |
| E07 | Same complaint event delivered twice | Single logical complaint; idempotent suppression |
| E08 | Two deferred events with distinct IDs | Retain both; incidence counts unique recipient-message |
| E09 | Event lacking valid provider ID | UNMATCHED/reconciliation; never guess-match |
| E10 | Webhook with invalid signature | Neither processed nor suppressed |
| E11 | Inbox persistence fails | Never falsely acknowledge success to provider |
| E12 | Worker crashes after persist before projection | Event can replay without losing side effects |
| E13 | Multi-recipient message with one bounce | Only the affected recipient updates |
| E14 | Provider accepted then deferred | Do not call JavaMailSender again while provider retries |
| E15 | Message outcome unknown then provider event arrives | Reconciles right attempt and recipient |
| E16 | Complaint after user unsubscribed | Retain both reasons if appropriate; do not erase history |
| E17 | Soft bounce followed by successful delivery | Not permanently suppressed over transient event |
| E18 | Hard bounce then another email to same recipient | Dispatch policy suppresses/re-validates in right scope |
| E19 | Large provider webhook backlog | Dedup, batching, and metrics stay accurate |
| E20 | Unknown/new provider event type | Recorded for handling without crashing pipeline |

### Unit Testing Projections with Late Events

~~~java
@Test
void delayedAcceptedEventDoesNotUndoDeliveredOutcome() {
    DeliveryProjection projection =
            DeliveryProjection.empty("notif-184", "recipient-42");

    projection.apply(deliveredEvent(
            "evt-2", "2026-11-10T09:03:00Z"));
    projection.apply(acceptedEvent(
            "evt-1", "2026-11-10T09:00:00Z"));

    assertEquals(
            DeliveryStatus.DELIVERED,
            projection.deliveryStatus());
    assertEquals(2, projection.eventCount());
}
~~~

This is JUnit-style pseudocode using project-defined helpers/domain classes. This unit test verifies projection rules, not webhook signatures or database unique constraints.

### Testing Idempotency with the Database

Run two consumers concurrently on one provider event ID. With proper unique constraints and transactions, they must never create two logical events or apply suppression twice. Simple mock repositories do not prove atomicity; run integration tests against a real database or equivalent.

### Testing Webhook Signatures

For the chosen provider, use payloads and signing schemes in authorized test fixtures, covering:

- Valid signature.
- Tampered signature.
- Payload altered by a single byte.
- Expired timestamp beyond tolerance.
- Rotated signing keys.
- Missing required headers.
- Validly redelivered duplicate event.

Do not "test HMAC" by using the same self-written helper to both sign and verify and then assume provider compatibility. Whenever possible, use official test vectors/SDKs to prove interoperability.

## 28. Runbook: Unusual Spike in Bounces

When hard bounces surge:

1. Slice changes by provider, sender domain, template, campaign, and recipient domain.
2. Separate hard bounces from soft bounces/deferrals and duplicate deliveries.
3. Inspect sanitized SMTP reply groups or provider reason codes.
4. Check list sources, email verification rigor, and recent imports.
5. Check sender authentication (SPF/DKIM/DMARC) and From identity if relevant.
6. Pause high-error sending sources if needed to limit damage.
7. Suppress confirmed hard-bounced addresses per policy.
8. Never retry infinitely or swap providers to force sends to confirmed invalid addresses.
9. Monitor fresh cohorts after remediation; never declare recovery solely because bounce counts dropped after stopping all sends.
10. Document the incident, policy changes, and remediation outcome.

### When Bounces Cluster at One Receiving Domain

Check for localized domain outages, policy rejections, or throttling. Never mark every recipient at that domain invalid without sufficient evidence. You can throttle sending toward that domain when errors are rate-related and supported by the provider.

## 29. Runbook: Rising Deferrals or Slow Delivery

When deferrals or delivery latency rise:

1. Check whether the provider owns retries or the application failed to submit.
2. Identify 4xx codes, enhanced statuses, and affected domains.
3. Inspect provider spool/queue age and accepted messages awaiting outcomes.
4. Check quotas, send rates, and connection concurrency.
5. If throttled, lower throughput and avoid resends that create duplicates.
6. If DNS/network/provider outage, escalate infrastructure per owning team.
7. Monitor the ratio of deferrals resolving to delivered vs. bounced.
8. Alert when critical emails exceed SLAs; consider alternative channels per policy.
9. When the provider recovers, do not flood the whole backlog via fresh `send()` calls.

A single DEFERRED event is not enough reason to flag an address bad. Wait for a terminal failure reported by the provider, or explicit business-policy thresholds, before acting.

## 30. Runbook: Rising Complaints

On a complaint spike, react swiftly based on data:

1. Verify event sources and strip duplicate webhooks.
2. Identify campaign/template, sender domain, audience, and list source.
3. Suppress marketing for recipients with confirmed complaints.
4. Pause or throttle the offending campaign when needed.
5. Audit consent and unsubscribe usability.
6. Review content, cadence, personalization level, and recipient expectations.
7. Check whether retry/replay bugs emailed recipients multiple times.
8. Monitor complaint rate by fixed cohort/denominator within provider-reported scope.
9. Document changes and approval steps before resuming campaigns.

Never try to "fix" metrics by deleting complaint data or hiding events from dashboards. Complaints are real feedback requiring policy action.

## 31. Common Mistakes

### 31.1. Logging Delivered Right After JavaMailSender.send()

This conflates SMTP submission with recipient delivery. Record SUBMITTED/ACCEPTED_BY_RELAY and track downstream events.

### 31.2. Treating Accepted as Terminal Success

Providers can accept and still bounce later. Always specify which hop accepted.

### 31.3. Treating Deferred as Bounced

Deferred messages may retry and deliver. Keep temporary status and wait for final outcomes.

### 31.4. Sending a New Message on Deferred

While the provider retries, resending creates parallel streams and duplicate risk. Define retry ownership at each leg.

### 31.5. Counting Events as Messages

One message can have multiple deferrals or duplicate webhooks. Compute incidence rates over unique recipient-messages.

### 31.6. Updating Status by Last Webhook Received

Out-of-order webhooks can regress DELIVERED back to DEFERRED. Maintain event timelines and semantic projections.

### 31.7. Collapsing Status Across Multiple Recipients

A multi-recipient email can bounce for just one address. Projections and suppression need recipient scope.

### 31.8. Not Storing Provider Message IDs

Correlating webhooks with only subject and address is brittle. Store attempt-to-provider-ID mappings whenever available.

### 31.9. Trusting Unauthenticated Webhooks

Attackers can forge COMPLAINED or BOUNCED events to suppress addresses. Verify signatures and account scope.

### 31.10. Returning 200/202 Before Durable Persistence

Process crashes can drop events. Acknowledge only after meeting contractual persistence guarantees.

### 31.11. Permanently Suppressing All Soft Bounces

Temporary issues can recover. Base policies on reason, count, time window, and provider.

### 31.12. Ignoring Complaints After Delivered

Complaints are independent feedback and can arrive after delivery confirmation. Keep both.

### 31.13. Not Rechecking Unsubscribe Before Marketing Dispatch

Recipients may unsubscribe/complain while jobs wait in queues. Workers must check current preferences/suppression.

### 31.14. Using Today's Counts for Both Numerator and Denominator Without Cohorts

Today's bounces may come from yesterday's emails. Measure by cohorts and defined time windows.

### 31.15. Ignoring Feedback Loop Coverage

Complaint data may come from only certain mailbox providers. Never claim it represents all recipients.

### 31.16. Using Unreliable Event Times to Overwrite State

Ordering across providers/attempts cannot always be inferred from timestamps alone. Use correlation and source semantics.

### 31.17. Retaining Full Raw Events Forever

Payloads may contain PII. Set retention, access controls, and store only what is needed.

### 31.18. Treating Delivered as Recipient Read

Delivered marks a receiving-system milestone per provider, not Inbox or reading behavior. Open tracking is also imperfect due to proxies/caches/image blocking.

## 32. End-to-End Implementation Workflow

To build deliverability observability in Spring Framework Mail:

1. **Choose feedback sources:** provider webhooks, export APIs, relay logs, or DSN/bounce mailboxes.
2. **Read semantics carefully:** define accepted/delivered/deferred/bounced/complained per provider.
3. **Design correlation:** notification ID, attempt ID, provider message ID, and recipient key.
4. **Separate outbox/submission:** never use provider events to mutate business transaction state directly.
5. **Build secure ingress:** verify webhooks on raw payloads; limit sizes and prevent replays.
6. **Persist events durably:** acknowledge only after durable storage succeeds.
7. **Deduplicate:** use scoped provider event IDs and proper unique constraints.
8. **Handle out-of-order events:** retain event history, source-specific projections, and unmatched reconciliation.
9. **Enforce suppression:** hard bounces/complaints/unsubscribes by reason and category with audits.
10. **Design metrics:** unique recipient-messages, clear denominators, cohorts, and event lag.
11. **Test thoroughly:** duplicate delivery, reordering, conflicting outcomes, multi-recipient, provider outages.
12. **Establish runbooks:** alerts for bounces, deferrals, complaints, and webhook health.
13. **Review privacy:** PII in events/logs, retention, and access permissions.
14. **Operate with reconciliation:** use provider exports when needed to catch missing or delayed events.

### Quick Decision Table Template

| When Receiving | Call JavaMailSender Again Immediately? | Primary Action |
|---|---|---|
| ACCEPTED | No | Record milestone and await downstream outcome |
| DEFERRED with provider retrying | No | Track reason, duration, provider queue |
| Permanent BOUNCED | No | Record failure/suppression and investigate |
| Temporary/final BOUNCED per provider | Do not retry blindly | Check provider policy and cause before deciding |
| COMPLAINED | No | Suppress marketing and handle feedback |
| Failed to submit at app SMTP step | May retry per outbox policy | Backoff, rate limits, and idempotency |
| SUBMISSION_UNKNOWN | Do not auto-retry blindly | Reconcile or handle duplicate risk |

## 33. Self-Check Questions

**1. Does JavaMailSender.send() succeeding prove the email reached the inbox?**

No. Normally it only indicates SMTP submission to the relay succeeded per the reply received by the application. Remote delivery, spam filtering, and recipient reading are separate stages.

**2. Can accepted occur before bounced?**

Yes. The outbound relay can accept a message and later emit a DSN/bounce after failing to deliver to the destination system.

**3. Is deferred a final failure?**

Not necessarily. It is usually a temporary delivery delay where the provider may retry automatically.

**4. Why not resend immediately upon receiving deferred?**

Because the provider likely still owns the accepted message and is retrying. Resending creates duplicates or unnecessary load.

**5. How does a hard bounce differ from a soft bounce?**

Hard bounces are usually unrecoverable errors for the current address/request; soft bounces are usually temporary. Exact classification must follow provider events and semantics.

**6. Does a complaint mean the email was undelivered?**

No. Complaints are usually recipient feedback flagging unwanted mail and can happen after an email was delivered.

**7. If webhooks emit zero COMPLAINED events, can we conclude nobody reported spam?**

No. Feedback loops do not cover every mailbox and some providers supply aggregate figures only.

**8. Why store provider message IDs?**

To correlate later events with the exact delivery attempt; subject and email address alone are not uniquely identifying.

**9. Can the same webhook event arrive multiple times?**

Yes. Providers may retry under at-least-once delivery. Idempotency keys/unique constraints are required.

**10. What should happen if DELIVERED arrives before ACCEPTED?**

Persist both, and the projection must not regress from DELIVERED back to ACCEPTED merely because the accepted webhook arrived later.

**11. Why is recipient-level tracking important?**

Because in a multi-recipient message, each recipient can have a distinct outcome; one recipient's bounce should not apply to all recipients.

**12. Should one message deferred three times count as three deferred emails?**

For unique deferral incidence, no: it is one deferred recipient-message. If counting raw deferral events, it may be three; state the definition clearly.

**13. What denominator should bounce rate use?**

A clearly defined, consistent denominator by cohort/unit, such as accepted recipient-messages. No single formula fits every provider.

**14. Why use cohorts instead of dividing by events received today?**

Because bounces and complaints can arrive hours or days after sending; numerator and denominator on a single receipt day may not represent the same email set.

**15. What must webhooks verify before suppressing a recipient?**

Source authenticity, payload integrity, event type, account/provider scope, and recipient/attempt correlation.

**16. Is it safe to buffer webhooks in memory and return 202?**

Not guaranteed. The process can crash after acknowledging. Persist events or enqueue durably before returning success.

**17. When should SUBMISSION_UNKNOWN be marked?**

When unsure whether the relay received the message, such as a connection drop after DATA before the final reply.

**18. How does delivered differ from opened?**

Delivered is a receiving-system milestone per provider; opened is an unreliable engagement/display signal that does not prove a human actually read it.

**19. Must complained stop all security emails too?**

There is no universal rule. Suppress marketing/optional mail per policy while evaluating permissions, address verification, notice obligations, and alternative channels for transactional/security emails.

**20. When a provider renames events, where should logic change?**

In the provider adapter/mapper, rather than scattering event-name checks across business services. Store source event types and mapping versions for troubleshooting.

## Conclusion

**Tracking accepted, bounced, deferred, and complained events means tracking the email lifecycle after the Spring Mail application submits, not merely checking whether JavaMailSender.send() threw an exception.** Accepted must be tied to the exact relay/provider boundary; bounced requires classifying reason and recipient; deferred is a temporary signal usually retried by the provider; complained is negative feedback driving suppression and sending-quality review. For reliable operations, store notification IDs, attempt IDs, provider message IDs, and recipients; ingest webhooks/DSNs via trusted channels; persist events durably; deduplicate and handle late/out-of-order events via timelines and projections. Dashboards must define clear cohorts, denominators, data sources, and event lag; runbooks must respond differently to bounces, deferrals, and complaints. **A sound deliverability system never claims delivery without evidence, never resends while the provider is still retrying, and never ignores unwanted-mail signals from recipients.**
