# Differences Between Accepted, Delivered, Opened, and Clicked in Email Architecture

When sending an email from a Spring application, a "sent" status usually does not mean the recipient received the email, much less that they read it or clicked a link. An email can be accepted by an SMTP server and later rejected; it can also be delivered successfully to the recipient's mail system yet filtered into spam; or a mail security system may fetch images and visit links before the user ever does.

To design a reliable notification system, separate four common signals:

- **Accepted**: a sending system or SMTP server accepted the message for further processing.
- **Delivered**: the receiving mail server or a hop defined by the provider accepted the message; usually **does not confirm inbox placement**.
- **Opened**: the system recorded a signal that the email content was displayed or a tracking resource was loaded; **does not prove a human read it**.
- **Clicked**: the system recorded a visit to a tracked URL in the email; **does not prove the user performed the intended business action**.

These are **events observable at different layers**, not four values guaranteed to progress linearly from low to high.

## 1. Which Components Does an Email Pass Through?

Suppose a Spring application sends an order confirmation email:

```text
Spring Application
    |
    | JavaMailSender.send(...)
    v
SMTP relay / Email Service Provider (ESP)
    |  accepted: accepts message for queuing and forwarding
    |
    | queue processing, sending policies, retries
    v
Receiving mail server (MX / receiving MTA)
    |  delivered: accepts message per provider's definition
    |
    | spam filtering, folder sorting, delivery into mailbox
    v
Email client / device / image proxy
    |  opened: tracking image load signal (if enabled)
    |
    | user or security scanner visits link
    v
Tracking redirect / Website
       clicked: records link visit (if tracked)
```

In this diagram, "accepted" must be understood by **handoff stage**. For instance, `JavaMailSender.send(...)` succeeding usually indicates the SMTP server the application connected to accepted the send during that session. An ESP may also emit an `accepted` event when its API receives the request or when the message enters a queue. Two events can share the same name yet reflect **two different boundaries of responsibility**.

Similarly, an ESP may report `delivered` when the destination mail server returns a successful SMTP response for the delivery attempt. The sending system does not directly observe whether the email was placed in Primary, Promotions, Spam, or deleted by the user.

### Quick Comparison Table

| Status | What Is Observed | What **Cannot Be Concluded** | Typical Signal Source |
| --- | --- | --- | --- |
| `accepted` | Outgoing server/API agreed to take the send task | Message reached destination server; message landed in inbox | SMTP response or ESP event |
| `delivered` | Receiving hop considered a successful handoff by the ESP | Recipient sees message in inbox, opened it, or read it | Receiving side's SMTP response, ESP webhook |
| `opened` | Tracking image was loaded or client emitted an equivalent signal | A real human read and understood the content | Tracking pixel, image proxy, ESP API |
| `clicked` | A tracked link was accessed | A real human clicked; transaction or confirmation completed | Redirect tracking, ESP webhook |

Event names, milestone placement, and guarantee levels are **provider-specific**. When integrating, read the exact definitions of your ESP, including statuses such as `processed`, `queued`, `deferred`, `dropped`, or `bounce`.

## 2. Accepted: Accepted for Processing, Not Necessarily Delivered

At the SMTP sending step, the server returns a response code for each stage. Code `250` is a success reply for many SMTP commands, so you must check **which command it followed**.

Minimal illustrative example of the sending process:

```text
C: MAIL FROM:<no-reply@example.com>
S: 250 OK

C: RCPT TO:<customer@example.net>
S: 250 Recipient accepted

C: DATA
S: 354 End data with <CRLF>.<CRLF>

C: Subject: Order confirmation
C:
C: Email body
C: .
S: 250 Message queued as 12345
```

Here:

- `250` after `RCPT TO` says the server accepted the recipient address for the transaction; it **does not confirm the message body was received in full**.
- `250` after the end of `DATA` indicates this server accepted the message for further processing. It may enqueue, forward, or retry it later.
- If it is a relay/ESP server, transfer to the destination mail server still lies ahead.
- With an email-sending API, HTTP `202 Accepted` (if used by the ESP) usually means only that the API accepted the request for asynchronous processing; exact semantics follow the API contract.

In Spring Framework Mail:

```java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

public class ConfirmationMailer {
    private final JavaMailSender mailSender;

    public ConfirmationMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmation(String recipient) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom("no-reply@example.com");
        mail.setTo(recipient);
        mail.setSubject("Order confirmation");
        mail.setText("Your order has been recorded.");

        // Success here confirms only the send step to the SMTP/relay the app uses.
        mailSender.send(mail);
    }
}
```

If `send` returns normally, the application can record **SMTP submission succeeded** or `submitted_to_relay`. Do not immediately mark the recipient's status as `delivered`.

If a `MailException` occurs, distinguish errors that definitely happened **before server acceptance** from connection errors occurring **after the server may have already received the message**. The latter carries duplicate-send risk if the system retries unconditionally. Use a stable business notification ID, log send attempts, and design retries to fit the provider.

### Which Outcomes Can Follow Accepted?

```text
accepted
   ├── delivered
   ├── deferred → retry → delivered
   ├── deferred → retry → bounced/failed
   ├── bounced/failed
   └── dropped/suppressed (depends on ESP definition)
```

`Deferred` usually describes a temporary obstacle, such as a busy receiver or rate limit; `bounce` usually describes inability to deliver. Classification into **hard bounce** and **soft bounce** also depends on the provider and error context. An accepted message is not guaranteed to produce `delivered` afterward.

## 3. Delivered: Handed Off to Destination Hop, Not Synonymous with Inbox

The `delivered` status in many email services means **the receiving mail system accepted the email**. A successful SMTP response from the receiving MTA is transport-level handoff evidence, not proof that:

- The email landed in the inbox rather than Spam/Junk or another tab.
- The mailbox will keep the message forever; the destination system may run post-processing or emit asynchronous failure notices.
- The recipient saw a notification on their phone or email client.
- The address belongs to someone actively using a valid account.
- The content was opened or links were clicked.

In SMTP, messages can traverse multiple relays. A `delivered` event from provider A may reflect a different hop than an identically named event from provider B; therefore, internal architecture docs should record the **source and definition of the event**.

For critical flows (verification codes, payment confirmations, security alerts), do not rely on `delivered` to assume the user saw the information. If the business genuinely needs confirmation, design an **in-app** confirmation action, authenticated and recorded separately.

### Do Delivered and Bounce Contradict Each Other?

Not necessarily. A receiving server can accept an email and then emit a **non-delivery report (DSN)** during later processing. An ESP can also reclassify when receiving late signals. Thus, if a `delivered` event appears before a `bounce` event for the same message/recipient, do not automatically assume the data is corrupted.

When displaying a single summary status, define an **explicit aggregation policy**: for example, prioritize a bounce confirming nondelivery over an earlier delivered signal, while retaining both events and timestamps for auditing.

## 4. Opened: A Limited Observation Signal of Rendering

A common way to track email opens is embedding a 1×1 pixel image or a resource URL with a unique identifier in the HTML:

```html
<img
  src="https://mail.example.com/t/open/opaque-token"
  width="1"
  height="1"
  alt=""
>
```

If a mail client loads this URL, the tracking system can record an `opened` event. ESPs usually handle this when open tracking is enabled; Spring's `JavaMailSender` **neither generates tracking pixels automatically nor knows when an email is opened**.

However, many differences lie between loading a pixel and a human reading an email:

1. **Image blocking**: A user may read the entire text while their client blocks the pixel. No open event occurs.
2. **Image proxies and caching**: An email service may fetch images through an intermediate server; IP, device, and load counts may not directly reflect the reader.
3. **Mail Privacy Protection and prefetching**: Some apps/systems prefetch remote content without the user actually opening the message. Events may be recorded without a corresponding read.
4. **Plain-text messages**: Have no HTML `<img>` tag to measure via pixel; a user reading the message creates no open event via this mechanism.
5. **Multiple devices or repeated opens**: One email can be reloaded multiple times; pixel loads do not equal unique readers.
6. **Security scanners**: Some filters inspect content and fetch resources or images to evaluate risk before delivering the message.

Therefore, `opened_at` should be understood as the timestamp of an **open signal** under a specific tracking method, rather than being named `read_at` or treated as legal/business proof of reading.

### Should You Measure Opened?

It can be useful for observing relative trends in email campaigns, though figures easily skew when many users enable privacy protections. For transactional emails, prioritize signals with stronger business meaning: the user verified their account, completed password reset, or viewed the notification in-app.

## 5. Clicked: Link Was Accessed, Not Necessarily by a Human

To record clicks, an ESP may replace original links inside the message body with redirect links:

```text
Original link:
https://example.com/orders/123

Tracking link appearing in email:
https://click.mail.example.com/r/opaque-token

When accessed:
1. Tracking server records "clicked" event.
2. Server returns HTTP redirect to destination URL.
3. Browser or system requests destination URL.
```

Example link in HTML:

```html
<a href="https://click.mail.example.com/r/opaque-token">
  View order
</a>
```

A `clicked` event usually carries message, recipient, timestamp, and clicked link. It may include user-agent, IP, or campaign ID depending on the source, though such data is not necessarily reliable for identifying the user.

**Misleading cases:**

- Anti-phishing filters test-open URLs before delivering the email, generating automated clicks.
- Link scanners or security systems visit multiple links within seconds.
- Preview generators, proxies, or browsers prefetch URLs automatically.
- A user forwards the email to someone else; clicks remain tied to the original email's token.
- Links were not rewritten or tracking is disabled: a real user clicks yet the system receives no event.
- Only the landing page was loaded; the user did not necessarily log in, pay, or accept terms.

Some ESPs classify **bot clicks** or provide quality flags, though accuracy and filtering vary. Do not confidently label every `clicked` event as "the recipient actively clicked."

**Click events do not replace business events.** Example:

```text
Email clicked → Landing page viewed → Authenticated → Order confirmed
        |                |                 |                |
    mail telemetry   web analytics   auth/session     business logic
```

For email verification or password reset features, never make a **GET request to a link** execute a sensitive state-changing action immediately. Link scanners can hit GET before the user does. Design the landing page so the user actively confirms via an appropriate follow-up action; token validation, replay protection, expiration, and business steps must be enforced on the backend.

## 6. Four Statuses Are Not a Linear State Machine

The `accepted → delivered → opened → clicked` model only **illustrates an ideal journey**. Real collected data can differ:

| Observed Event Sequence | Plausible Interpretation |
| --- | --- |
| `accepted`, `delivered` | Delivery evidence exists; no open or click signals |
| `accepted`, `delivered`, `clicked` | User or system visited a link; pixel was blocked or open tracking disabled |
| `accepted`, `delivered`, `opened` | Image load signal observed; no click recorded |
| `accepted`, `bounced` | Accepted by ESP, yet undeliverable to destination |
| `delivered` then `bounced` | Possible asynchronous failure notice after receiving hop accepted |
| `clicked` webhook arrives before `delivered` | Events delivered out of order or clock differences across sources |
| Two identical `opened` events | Possible multiple opens or redelivered webhook; check event ID |
| `clicked` immediately after `delivered` across multiple URLs | Possible bulk access by security scanner; insufficient evidence to conclude human action |

Beyond these four events, email architectures commonly need additional statuses:

- `requested` or `queued`: the application created the request and prepared to send.
- `submitted`: the application sent successfully to SMTP/API.
- `deferred`: the provider postponed delivery attempt; retries may follow.
- `bounced` / `failed`: mail delivery failed.
- `dropped` / `suppressed`: the provider intentionally did not send, e.g., due to a suppression list or policy.
- `complained`: received a spam complaint/feedback.
- `unsubscribed`: request to opt out of that email category.

In particular, `unsubscribed` is a subscription-preference event, not a level higher or lower than `opened` or `clicked`.

### Separating Raw Events from Aggregated Status

A helpful architecture is storing an **immutable event log** and deriving UI-facing labels from it. Example:

```text
email_delivery (one email to one recipient)
    delivery_id = d-001
    business_id = order-123
    provider_message_id = p-555

email_event (multiple records)
    09:00 accepted
    09:00 delivered
    09:02 opened
    09:05 clicked (link=order-details)
    09:06 opened
```

The system can display "accepted by destination server" based on the latest transport-related `delivered` event, while separately displaying "open signal observed" or "link clicked." This avoids overwriting a single `status` field to `clicked` and losing a later `bounced` or `complained` event.

## 7. How Does JavaMailSender Relate to These Events?

In Spring Framework Mail, `JavaMailSender` handles sending over SMTP and constructing `MimeMessage`. It **does not provide built-in ESP delivery lifecycle tracking**, does not listen for delivered/opened/clicked webhooks, and cannot tell whether the recipient read the email.

There are three distinct layers of data sources:

| Layer | Collectible Signals | Typical Owning Component |
| --- | --- | --- |
| Spring Application | Message creation request, `send` success/failure, correlation ID | Mail sending service + database |
| SMTP/ESP | Accepted, deferred, delivered, bounce, complaint | SMTP relay, ESP webhooks/API, DSNs when supported |
| Interaction | Open pixels, link redirects/clicks, and website actions | ESP tracking, tracking endpoint, analytics, or business backend |

If using plain SMTP with a provider that **offers no tracking webhooks**, calling `JavaMailSender#send(...)` will not automatically produce `delivered`, `opened`, or `clicked` events. Integrating an ESP API/webhook or dedicated tracking infrastructure may be required.

### Attaching Correlation IDs to Link Data

One transaction can spawn multiple emails; one email can have multiple recipients; one send can be retried. Distinguish:

- **Business ID**: transaction or order ID, e.g., `order-123`.
- **Delivery ID**: internal ID for **one email sent to one recipient**.
- **Attempt ID**: ID of a send attempt; one delivery can have multiple attempts.
- **Provider message ID**: ID assigned by the ESP, often included in webhooks.
- **RFC Message-ID**: the email's `Message-ID` header; not always identical to the provider message ID.
- **Provider event ID**: unique ID for a webhook event, used for deduplication.

For a `MimeMessage` with multiple recipients, delivered/bounce events can **differ per recipient**. Create separate delivery records per recipient; do not mark the entire message delivered just because one address was accepted.

Correlation info can be attached via metadata or a custom header like `X-Application-Delivery-ID` if supported by the provider. However, **never put secrets or sensitive personal data into tracking headers/URLs**, as intermediaries can observe them.

## 8. Example Spring Architecture Receiving Webhooks from an ESP

With an ESP offering webhooks, the workflow typically includes:

1. The application saves the send request with `delivery_id` and recipient.
2. The application sends the email via SMTP or API and stores submission result/provider message ID.
3. The ESP sends webhooks for events such as accepted, delivered, bounced, opened, and clicked.
4. Spring authenticates the webhook and maps the provider-specific payload to an internal event model.
5. The database stores events **idempotently**; reporting or UI layers read normalized events.

Example webhook payload **normalized internally by the application**, not the default format of any specific ESP:

```json
{
  "provider": "example-esp",
  "providerEventId": "evt-00042",
  "providerMessageId": "msg-0815",
  "deliveryId": "d-001",
  "recipientRef": "customer-27",
  "type": "delivered",
  "occurredAt": "2026-11-12T02:10:35Z",
  "linkId": null
}
```

Here, `occurredAt` is when the source reports the event happened; when the server receives the webhook may be later. `recipientRef` is a privacy-minimized internal reference ID rather than a raw email address.

### Organizing the Webhook Receiver Layer

Skeleton controller example for Spring Boot 3+ / Java 17+:

```java
package example.mail.tracking;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/webhooks/email")
public class EmailWebhookController {
    private final WebhookVerifier verifier;
    private final ProviderEventAdapter adapter;
    private final EmailEventIngestion ingestion;

    public EmailWebhookController(
            WebhookVerifier verifier,
            ProviderEventAdapter adapter,
            EmailEventIngestion ingestion) {
        this.verifier = verifier;
        this.adapter = adapter;
        this.ingestion = ingestion;
    }

    @PostMapping
    public ResponseEntity<Void> receive(
            @RequestHeader("X-Provider-Signature") String signature,
            @RequestHeader("X-Provider-Timestamp") String timestamp,
            @RequestBody String rawBody) {

        // Signature must be verified on rawBody, per the actual ESP standard.
        if (!verifier.isAuthentic(rawBody, timestamp, signature)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
        }

        List<EmailEvent> events = adapter.toInternalEvents(rawBody);
        ingestion.persistIdempotently(events);
        return ResponseEntity.noContent().build();
    }
}
```

Application domain interfaces:

```java
package example.mail.tracking;

import java.time.Instant;
import java.util.List;

public record EmailEvent(
        String provider,
        String providerEventId,
        String deliveryId,
        EventType type,
        Instant occurredAt,
        String linkId) {
}

enum EventType {
    ACCEPTED, DELIVERED, OPENED, CLICKED,
    DEFERRED, BOUNCED, DROPPED, COMPLAINED, UNSUBSCRIBED
}

interface WebhookVerifier {
    boolean isAuthentic(String rawBody, String timestamp, String signature);
}

interface ProviderEventAdapter {
    List<EmailEvent> toInternalEvents(String rawBody);
}

interface EmailEventIngestion {
    void persistIdempotently(List<EmailEvent> events);
}
```

This is a **skeleton illustrating responsibility boundaries**, not a complete ESP integration: headers, signature algorithm, payload structure, retry policy, and delivery lookup keys must all be implemented per your specific provider's documentation. Never replace `WebhookVerifier` with a function that always returns `true` in production.

An implementation must verify the signature over the **raw payload** using the provider-specified algorithm, constant-time comparison, bounded timestamp skew, and replay protection if supported by the protocol. Webhook handling should finish quickly; if queuing is needed, persist the message durably to a queue before returning success. Return HTTP 2xx once the event is durably persisted; if processing fails temporarily, respond per the ESP's retry contract.

### Storing Events Without Duplicate Processing

PostgreSQL table example:

```sql
CREATE TABLE email_delivery (
    delivery_id UUID PRIMARY KEY,
    notification_id UUID NOT NULL,
    recipient_ref VARCHAR(128) NOT NULL,
    provider_message_id VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE email_event (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    delivery_id UUID NOT NULL REFERENCES email_delivery(delivery_id),
    provider VARCHAR(100) NOT NULL,
    provider_event_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    link_id VARCHAR(128),
    UNIQUE (provider, provider_event_id)
);

CREATE INDEX email_event_delivery_type_idx
    ON email_event (delivery_id, event_type, occurred_at);
```

If the provider supplies a stable `provider_event_id`, duplicates can be handled safely with a unique constraint, such as `INSERT ... ON CONFLICT DO NOTHING`. Do not assume every provider supplies an event ID, nor deduplicate on `(delivery_id, event_type)`, since one email can genuinely be opened or clicked multiple times. Choose idempotency keys according to each source's capabilities and contract.

If a payload contains multiple events, persist them in a transaction or queue ensuring appropriate retry semantics. When an event arrives before the provider message ID mapping is saved, temporarily store the unlinked event and reconcile later; do not drop events solely due to unexpected arrival order.

## 9. Event Timestamps and Update Rules

Systems integrating multiple webhooks have at least two timestamps:

- `occurred_at`: when the event source states the action occurred.
- `received_at`: when the backend received and stored the event.

The two timestamps can differ by minutes or more if the ESP retries, networks congest, or systems pause temporarily. Event streams can also be **delayed, duplicated, or out of order**.

Do not rely on a simple rule like "the latest received event overwrites current status", because a delayed `accepted` webhook could accidentally overwrite an already-known `delivered` state. A better approach is:

1. Store raw events along with source and both timestamps.
2. Deduplicate based on event ID/stable key.
3. Build projections for specific questions: ever accepted? ever delivered? terminal bounce? open signal observed? which link clicked?
4. When a single summary status is required, set explicit precedence rules for transport events (e.g., bounced/failed tied directly to delivery), while keeping engagement signals as separate attributes.

Reports and operational tools can represent it like this:

```json
{
  "deliveryId": "d-001",
  "transport": {
    "accepted": true,
    "delivered": true,
    "bounced": false
  },
  "engagement": {
    "openSignalObserved": true,
    "trackedLinkAccessObserved": true
  }
}
```

This structure avoids the artificial contradiction "if it's clicked, is the status still delivered?". Delivered and clicked describe **two different dimensions**: transport and engagement.

## 10. Computing Accepted, Delivered, Opened, and Clicked Metrics

If using telemetry for reporting, choose a consistent **unit of measurement** (one email sent to one recipient), **cohort**, and event definition.

For example, in a campaign with 1,000 deliveries accepted by the ESP, 970 deliveries have a delivered event, 700 deliveries have at least one open signal, and 125 deliveries have at least one tracked click. Assuming counts represent **unique deliveries** in the same cohort:

| Metric | Formula | Illustrative Result |
| --- | --- | --- |
| Delivery rate | `970 / 1,000 × 100%` | `97.0%` |
| Unique open-signal rate | `700 / 970 × 100%` | `72.2%` |
| Unique tracked-click rate | `125 / 970 × 100%` | `12.9%` |
| Click-to-open ratio | `125 / 700 × 100%` | `17.9%` |

**Rates do not substitute for one another.** Delivery rate tracks mail deliverability; open-signal rate is heavily affected by images/proxies/privacy; tracked-click rate can be skewed by scanners or tracking blockers; click-to-open ratio inherits biases from both opens and clicks.

To avoid wrong conclusions:

- Use `COUNT(DISTINCT delivery_id)` for **unique opens/clicks**, distinct from total event counts.
- Clearly define the "denominator": accepted, delivered, attempted, or total send requests; each denominator answers a different question.
- Compute by cohorts of emails initiated in the same window and leave an observation window long enough for late events; avoid counting today's accepted against another day's delivered without linking the same cohort.
- For multiple recipients in one API call, count per delivery/recipient, not one aggregate message as a single delivery.
- Separate bot-detected clicks and auto-prefetched opens if the ESP classifies them; document reliability and filtering methodology.
- Never treat `opened_count > 0` as legal proof of "read", or `clicked_count > 0` as proof of a completed financial action.

### Example Distinguishing Communication Metrics from Business Metrics

An email asking a user to confirm an order produces these events:

```text
delivery accepted
delivery delivered
tracked link clicked
checkout page visited
user authenticated
order confirmation submitted
```

To know whether the email was sent and accepted by the destination system, read `accepted` and `delivered`. To know whether the link was visited, read `clicked`. To prove the user confirmed the order, use **the authenticated confirmation event from the business system**; it follows different data standards and does not depend on pixels or redirects.

## 11. Privacy, Security, and Observability

Open/click tracking involves recipient behavior. Therefore, review measurement purpose, user choices, organizational data policies, and applicable regulations before enabling tracking.

Practical architectural principles:

1. **Data minimization**: store only fields needed for analytics/operations. Avoid putting emails, login tokens, verification codes, or sensitive order details into pixel or redirect URLs.
2. **Unguessable tokens**: use random identifiers or appropriately signed tokens bound to delivery/link on the backend; set retention or expiration where appropriate. Never let tracking links become open redirects to arbitrary URLs.
3. **Separate tracking from authorization**: tracking URLs must never grant business access; the target backend must still authenticate and authorize.
4. **Protect webhooks**: verify signatures, timestamps, and origins per ESP mechanisms; enforce idempotency on retries; restrict public endpoints to accept only valid payloads.
5. **Retention policies**: limit event retention duration and dashboard access; mask PII in logs, reports, and backups per organizational policy.
6. **Measurement transparency**: in reports, label "open signals" or "tracked clicks" if that is what was actually measured, rather than claiming definitive reads/actions.

For features like email verification, passwordless login, or password reset, take special care that an **automated GET from a scanner** never triggers an immediately effective action. The landing page can display safe context first, followed by the user confirming via an active step; validation and anti-replay protections must match the action's sensitivity.

## 12. Real-World Scenario: Tracking an Order Confirmation Email

Suppose a Spring system sends an email after a customer places an order:

**Step A — User places order.** Backend creates `notification_id` and a `delivery_id` for the email to send. The business system knows the order was created; no SMTP evidence exists yet.

**Step B — Spring calls `JavaMailSender.send`.** If it succeeds, the backend records `submitted_at` and the corresponding outcome. This is what the application can observe; do not set `delivered=true`.

**Step C — ESP receives and processes.** An `accepted` webhook confirms per the ESP's definition; if the destination server temporarily refuses, `deferred` may appear. If undeliverable, `bounced` may occur.

**Step D — Receiving mail server returns success.** The ESP reports `delivered`. The dashboard displays "Accepted by recipient mail system", not "Customer read it."

**Step E — Image is loaded.** The ESP reports `opened`. Record `openSignalObserved=true`, but do not use this signal to conclude the customer viewed the content.

**Step F — Link is visited.** The ESP reports `clicked`. The dashboard records a link visit; if the website receives an authenticated order confirmation action, the backend emits a **separate business event**.

In this scenario, four statuses answer distinct questions:

| Question | Most Appropriate Signal |
| --- | --- |
| Did the sending system accept the mail transfer request? | `accepted`, or submission from app depending on boundary |
| Did the receiving side accept the message? | `delivered` per ESP definition |
| Is there a sign the email content was fetched for display? | `opened` |
| Was the tracked link visited? | `clicked` |
| Did the customer actually confirm the order? | **Business event** from authenticated backend |

The design principle is to **measure precisely what each event can prove**, keep raw events for reconciliation, and never equate email transport states with user behavior. In Spring Framework Mail, `JavaMailSender` solves SMTP submission; whereas delivered, opened, and clicked must come from delivery/tracking infrastructure and integrate into the application's event system.
