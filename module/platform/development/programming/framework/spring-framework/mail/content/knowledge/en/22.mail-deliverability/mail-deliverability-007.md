# Bounce Address and Handling Delivery Failure Feedback

## 1. What Is a Bounce and Why Must It Be Handled?

In systems using **Spring Framework Mail**, calling `JavaMailSender.send(...)` successfully does not mean the email reached the recipient's mailbox. The SMTP server the application connects to may accept the message, after which relaying or delivery to the destination server fails. When that happens, the mail system may generate a **delivery status notification (DSN)**, commonly called a **bounce** or **non-delivery report (NDR)**.

Example:

~~~text
OrderService
    |
    v
JavaMailSender
    |
    | SMTP accepted (250)
    v
SMTP relay / email provider
    |
    +--> Receiver MX accepts --> delivery process continues
    |
    +--> Recipient rejected / mailbox unavailable
                     |
                     v
                Bounce / DSN
                     |
                     v
          Bounce mailbox or provider webhook
                     |
                     v
            Application bounce processor
                     |
                     +--> Update delivery status
                     +--> Suppress invalid recipients
                     +--> Decide retry / investigation
                     +--> Update deliverability metrics
~~~

If the application relies solely on `JavaMailSender` exceptions, it typically **cannot see failures that happen after the initial SMTP server accepted the message**. Ignoring bounces can lead to:

- Continuing to send repeatedly to nonexistent addresses.
- Increasing bounce rates and degrading domain/IP sending reputation.
- Sending critical business notifications that users never receive without the system knowing.
- Retrying improperly, sending duplicates, or adding unnecessary load on the mail provider.
- Failing to distinguish temporary errors (full mailbox, busy destination system) from permanent errors (nonexistent address).

The goal of this lesson is to design a **bounce address**, understand the sources and contents of failure feedback, and ingest them into a state-tracking system safely, testably, and in alignment with Spring Mail's capabilities.

> **Important limitation:** Spring Framework Mail provides email sending APIs such as `JavaMailSender`; it does not provide a complete built-in system to receive, verify, classify, and process all bounces. Receiving DSNs via mailbox or webhook must be built/integrated separately.

## 2. Distinguishing Successful Submission from Successful Delivery

An email passes through multiple stages. Accurate status naming requires understanding each stage:

| Stage | What the Application Observes | Does It Mean Inbox Delivery? |
| --- | --- | --- |
| Preparing MIME | Valid message constructed | Not yet |
| Connecting and AUTH with SMTP | Mail server login succeeded | Not yet |
| SMTP server accepts message | `send(...)` returns normally after SMTP exchange | Not yet |
| Provider/relay continues forwarding | May have `processed`/`queued` events | Not yet |
| Receiving server accepts delivery | May have `delivered` event from provider | Does not guarantee Inbox placement |
| Bounce/DSN | A delivery step failed or was delayed | Did not succeed as expected |
| Email opened/read | Separate tracking signal, if present | Cannot be inferred from SMTP/DSN alone |

Even an email provider's `delivered` event usually only means handoff to the receiving system at the level observed by the provider, **not proof that the user saw the message in the inbox**. The message may be in spam, another folder, or filtered after receipt.

### 2.1. Synchronous Errors When Calling JavaMailSender

An SMTP server can reject immediately during the sending session, for example on the `RCPT TO` command:

~~~text
C: EHLO app.example.com
S: 250-mx.example.net
C: MAIL FROM:<bounces@example.com>
S: 250 2.1.0 OK
C: RCPT TO:<nobody@receiver.example>
S: 550 5.1.1 User unknown
~~~

This illustrative response occurs **inside the application's SMTP session**. `JavaMailSender.send(...)` may throw a `MailSendException` wrapping the cause/provider exception. This is an error the application can observe immediately without waiting for a DSN.

### 2.2. Asynchronous Bounces After the Server Accepted

In another case:

~~~text
App --> SMTP relay: DATA
Relay --> App: 250 2.0.0 Message accepted
App: JavaMailSender.send(...) returns successfully

Later:
Relay --> Receiver MX: attempt delivery
Receiver MX --> Relay: permanent failure
Relay --> Bounce address: DSN
~~~

The app completed the send call successfully yet still receives a bounce later. Therefore, **SMTP submission status** and **delivery status** should be tracked separately; do not ambiguously overwrite outbox `SENT` to `FAILED` without clearly defining what each status represents.

## 3. Four Easily Confused Addresses

When sending an email, multiple addresses with different roles can appear:

| Component | Where Is It? | Purpose | Is It the Bounce Address? |
| --- | --- | --- | --- |
| `From:` | RFC 5322 header in message | Sender address visible to recipients | Not by default |
| `Reply-To:` | Header in message | Where users send normal replies | Not by default |
| `MAIL FROM` / reverse-path | SMTP **envelope** of sending session | Destination for DSNs/bounces on failure, unless null reverse-path or provider handles differently | **Usually yes** |
| `Return-Path:` | Header inserted by final delivery system | Records the envelope reverse-path upon delivery | Reflects envelope; should not be set manually |

Example email:

~~~text
SMTP envelope:
  MAIL FROM:<bounces@bounce.example.com>
  RCPT TO:<lan@receiver.example>

Headers in MIME message:
  From: "Order Notifications" <notifications@example.com>
  Reply-To: support@example.com
  To: lan@receiver.example
  Subject: Order confirmation
~~~

The recipient sees `notifications@example.com` as the sender and can reply to `support@example.com`. If delivery fails, the DSN notification may be sent to `bounces@bounce.example.com`.

### 3.1. From Is Not MAIL FROM

In Spring:

~~~java
helper.setFrom("notifications@example.com");
~~~

sets the **From header**. This API does not mean the application configured the bounce envelope address. SMTP envelope `MAIL FROM` may be determined by transport properties, SMTP account, or mail provider policy.

### 3.2. Reply-To Is Not the Bounce Address

~~~java
helper.setReplyTo("support@example.com");
~~~

tells the user where to send normal replies to support. It **does not force SMTP servers to send DSNs to that address**. Using `Reply-To` to change where bounces arrive is a common mistake.

### 3.3. Do Not Overwrite the Return-Path Header Yourself

Do not try to set:

~~~java
// Do not use as a way to configure bounce.
message.setHeader("Return-Path", "<bounces@bounce.example.com>");
~~~

`Return-Path` is typically added upon delivery based on the envelope reverse-path. A manually set header may be stripped, overwritten, or make diagnostics confusing. Configure the **envelope sender** on the transport or via the email provider instead of treating `Return-Path` as an arbitrary header.

### 3.4. DSNs May Use an Empty Reverse-Path

Under SMTP mechanics, a delivery failure notification is normally sent with an empty envelope sender `MAIL FROM:<>` to prevent an error notification from generating a new bounce. This mechanism prevents **bounce loops**.

Do not design a worker that automatically replies to every bounce with a new email; doing so can create loops, especially when recipient addresses do not exist or DSNs pass through multiple relays.

## 4. Designing the Bounce Address

A suitable bounce address should:

- Be an address or domain supported by the mail-sending infrastructure/provider.
- Have a destination to receive and process DSNs, via mailbox or equivalent webhook.
- Stay separate from user reply streams if the application needs automated bounce classification.
- Use a domain/subdomain owned and DNS-controlled by the organization.
- Have appropriate access control, retention, and monitoring because DSNs can contain recipient emails or parts of original messages.

Example separation of functions:

~~~text
notifications@example.com       -> Header From
support@example.com             -> Reply-To
bounces@bounce.example.com      -> SMTP envelope MAIL FROM
~~~

The address `bounces@bounce.example.com` is useful only if a mailbox, route, or provider can actually receive and process the feedback. **Creating an email string does not automatically create a mailbox or MX record**.

### 4.1. Using a Dedicated Subdomain

A subdomain like `bounce.example.com` isolates bounce infrastructure from the organization's regular mailboxes. This helps:

- Route DSNs to a dedicated system.
- Set up MX/CNAME/TXT records required by the provider.
- Manage DNS/SPF alignment and monitor sender reputation.
- Restrict access to bounce data.

The bounce subdomain must be configured per the SMTP relay/email provider's instructions. Some providers **rewrite the envelope sender themselves** and require a custom return-path/bounce domain via their DNS interface; in that case, setting `mail.smtp.from` in the application may not produce the expected final Return-Path if the provider overrides it.

### 4.2. Single Shared Address or Per-Delivery Alias?

**Shared address:**

~~~text
bounces@bounce.example.com
~~~

All DSNs arrive in the same mailbox. The processor must match the corresponding delivery from original message info, recipient, provider ID, or related metadata.

**Dynamic per-send alias (VERP-like):**

~~~text
bounces+e7f4a2@bounce.example.com
bounces+9d103c@bounce.example.com
~~~

The token helps locate the exact delivery without relying solely on subject/recipient. This pattern resembles **Variable Envelope Return Path (VERP)** and is very helpful in high-volume sending systems.

However:

- Infrastructure must support plus-addressing or catch-all/alias routing.
- Tokens should be random opaque identifiers, not embedding email addresses or direct PII.
- Tokens must be validated and linked to delivery IDs in the database.
- Do not trust every DSN carrying a token: attackers can send forged emails to bounce addresses, so check source/trustworthiness and policies before suppression.
- Keep tokens within valid SMTP local-part length/charset limits.

With providers offering custom return-paths and official webhooks, provider event IDs or message IDs can serve as correlation instead of building full VERP yourself.

## 5. Configuring the Envelope Sender in Spring Framework Mail

When using Spring Boot with Jakarta Mail's SMTP transport, the `mail.smtp.from` property can specify the envelope sender used by the transport for `MAIL FROM`, separate from the `From` header set by `MimeMessageHelper`.

Example configuration for a shared bounce address:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.ssl.checkserveridentity]": true
      "[mail.smtp.from]": bounces@bounce.example.com
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000
~~~

Bracket notation in map properties preserves dotted keys when Spring Boot binds `spring.mail.properties`. Addresses and domains in the example are dummy data; production must use domains actually configured/authorized at the SMTP provider.

In sending code:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class OrderMailer {

    private final JavaMailSender mailSender;

    public OrderMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmation(
            String recipient, String subject, String plainText,
            String htmlText) throws MessagingException {

        MimeMessage mimeMessage = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(mimeMessage, true, "UTF-8");

        helper.setFrom("notifications@example.com");
        helper.setReplyTo("support@example.com");
        helper.setTo(recipient);
        helper.setSubject(subject);
        helper.setText(plainText, htmlText);

        mailSender.send(mimeMessage);
    }
}
~~~

This example configures **one fixed envelope sender for the entire application**. `helper.setFrom` and `helper.setReplyTo` only set the corresponding headers; `mail.smtp.from` is used by the SMTP transport when sending.

### 5.1. Do Not Mutate Shared Session Properties per Request

If you want a distinct bounce alias per delivery, do not do the following on a singleton bean:

~~~java
// Unsafe in concurrent sending applications.
javaMailSenderImpl.getJavaMailProperties().put(
        "mail.smtp.from", "bounces+tokenA@bounce.example.com");
mailSender.send(messageA);
~~~

If two requests mutate the same property, message A may be sent with message B's envelope sender. Use a **per-message** solution supported by the SMTP provider/API, or design separate transports/factories that do not share mutable state. Some Jakarta Mail implementations include an `SMTPMessage` class supporting per-message envelope senders, though the package and integration depend on implementation/version (e.g., Eclipse Angus Mail) and require checking corresponding documentation.

If the SMTP relay manages return-paths and webhooks, it is usually better to use the provider-supported **custom bounce domain + event correlation** mechanism rather than interfering with a shared `JavaMailSenderImpl`.

### 5.2. Verifying the Actual Envelope Sender

Do not look only at source code or the `From` header. To verify the bounce path:

1. Send a test message to an authorized mail server/provider.
2. Confirm the SMTP transport uses the reverse-path permitted by the infrastructure.
3. Inspect Return-Path when the email is delivered, if the test environment exposes it.
4. Simulate a failure scenario and verify the bounce routes to the right collection channel.
5. If the provider overrides the envelope sender, configure the custom return-path/bounce domain inside the provider itself.

Do not use real third-party addresses to generate test bounces. Use controlled mailboxes or an SMTP sink/test environment.

## 6. How Does Delivery Status Notification (DSN) Work?

DSN is the mail system's mechanism for reporting delivery status. When an MTA cannot deliver a message, it may send an error notification to the **envelope reverse-path** of the original message.

Typical flow:

~~~text
Original SMTP message
  MAIL FROM: bounces@bounce.example.com
  RCPT TO: invalid@receiver.example
          |
          v
Relay accepts message
          |
          v
Later delivery fails
          |
          v
MTA generates DSN
  MAIL FROM: <>      (null reverse-path)
  RCPT TO: bounces@bounce.example.com
          |
          v
Bounce mailbox / inbound handler
~~~

A DSN can describe:

- **Failed:** Final delivery failure.
- **Delayed:** Delivery is delayed; the MTA may continue retrying.
- **Delivered:** Information on successful delivery within DSN-supported scope.
- **Relayed/Expanded:** The MTA forwarded or expanded a recipient list.

Not every provider delivers DSNs in the same format. Some providers notify via webhooks; some offer dashboards and event APIs; some receiving systems do not generate complete feedback. Therefore, bounce handling must accommodate **missing information, non-standard data, and uncertain outcomes**.

### 6.1. Machine-Readable DSN Format

Under MIME/DSN conventions, a standard notification is typically `multipart/report`, containing a human-readable part and a machine-readable `message/delivery-status` part.

Simplified example:

~~~text
Content-Type: multipart/report;
    report-type=delivery-status; boundary="dsn-boundary"

--dsn-boundary
Content-Type: text/plain; charset=UTF-8

Delivery failed for one or more recipients.

--dsn-boundary
Content-Type: message/delivery-status

Reporting-MTA: dns; mx.sender.example
Arrival-Date: Thu, 12 Nov 2026 08:30:00 +0000

Final-Recipient: rfc822; invalid@receiver.example
Action: failed
Status: 5.1.1
Diagnostic-Code: smtp; 550 5.1.1 User unknown

--dsn-boundary--
~~~

This is an **abbreviated illustration**: boundaries, headers, and original content may differ. A real DSN may contain multiple recipient blocks and part of the original message/headers, or the provider may emit feedback in a different format.

### 6.2. Important DSN Fields

| Field | Meaning |
| --- | --- |
| `Reporting-MTA` | Mail transfer agent that generated the notification |
| `Original-Envelope-Id` | Envelope ID if supported and preserved by the SMTP/DSN system |
| `Original-Recipient` | Original recipient, if present |
| `Final-Recipient` | Recipient address to which the status applies |
| `Action` | `failed`, `delayed`, `delivered`, `relayed`, or `expanded` |
| `Status` | Enhanced mail status code, e.g. `5.1.1` |
| `Diagnostic-Code` | Details from transport/provider, e.g. SMTP `550` |
| `Last-Attempt-Date` | Timestamp of the MTA's last delivery attempt, if present |
| `Will-Retry-Until` | Final timestamp until which the MTA expects to retry, if present |

`Final-Recipient` and `Action` are especially important when a message has multiple recipients: **a single DSN may report errors for only some recipients**, while others had no error or were delivered.

Do not use the DSN's `Subject` or `From` as the sole key to identify the original message; those fields are not unique and can be spoofed.

### 6.3. Requesting DSN over SMTP Does Not Guarantee Receiving DSNs

Some Jakarta Mail SMTP implementations support properties to request DSNs when the server advertises the relevant extension:

~~~yaml
spring:
  mail:
    properties:
      "[mail.smtp.dsn.notify]": FAILURE,DELAY
      "[mail.smtp.dsn.ret]": HDRS
~~~

In supporting implementations, `mail.smtp.dsn.notify` requests notifications for specific outcomes, while `mail.smtp.dsn.ret` chooses how much of the original message content is returned, such as `HDRS` or `FULL`. Actual values and behavior must be checked against the SMTP implementation in use.

Important limitations:

1. The mail server must support the corresponding DSN extension.
2. The relay/provider may ignore, alter, or restrict the request.
3. Not every failure produces a parseable notification.
4. `notify=FAILURE,DELAY` does not compel the server to send webhooks to your application.
5. Returning `FULL` can include raw email content with sensitive data in the DSN; usually avoid unless truly needed.

DSN parameters are merely a **protocol request**, not a deliverability guarantee. When reliable event-level tracking is needed, prefer integrating the provider's official API/webhook when available.

## 7. Enhanced Status Codes and Bounce Classification

DSNs and SMTP responses can contain status codes:

- Basic SMTP reply codes: e.g. `421`, `450`, `550`.
- Enhanced status codes: e.g. `4.2.2`, `5.1.1`, or `5.7.1`.

Enhanced status codes have the form `class.subject.detail`. The first digit generally describes the class:

| Class | General Meaning | Handling Guidance |
| --- | --- | --- |
| `2.x.x` | Success | Record corresponding event once verified |
| `4.x.x` | Temporary error | Check provider retries and soft-bounce policy |
| `5.x.x` | Permanent error | Consider hard bounce/suppression or data correction |

Common codes:

| Example | Common Interpretation | Initial Classification |
| --- | --- | --- |
| `5.1.1` | Destination mailbox address does not exist or is invalid | Hard bounce |
| `5.1.2` | Destination system/domain invalid in delivery context | Permanent; check address |
| `4.2.2` | Mailbox full or temporary limit exceeded | Soft bounce |
| `5.2.2` | Mailbox full but reported as permanent failure | Needs dedicated policy; do not treat all "mailbox full" as transient |
| `4.4.1` | No response received from destination host | Transient network/delivery |
| `5.4.4` | Unable to route to destination | Permanent routing issue |
| `5.7.1` | Delivery not authorized or rejected by policy | May require investigating authentication/reputation |

The descriptions above are **code-based guidance**, not a guarantee that every provider uses the same granularity or wording. Some bounces carry free-form text or non-standard codes; keep raw evidence in a secure location for investigation while storing only normalized error codes in delivery state.

### 7.1. Hard Bounce

**Hard bounce** typically indicates a failure judged permanent for the address or current delivery conditions, such as:

- Nonexistent mailbox.
- Invalid destination domain.
- Permanently rejected recipient.
- A provider policy blocking delivery that requires changing conditions before retrying.

For addresses confirmed nonexistent, repeatedly sending the same content raises bounce rates, hurts sending reputation, and wastes resources. A deliverability system typically **suppresses** the address for subsequent sends until corrected or re-verified.

Not every `5xx` means "address permanently broken." For example, `5.7.1` may be a domain authentication or sender policy issue; analyze root cause and scope before disabling recipients en masse.

### 7.2. Soft Bounce

**Soft bounce** typically indicates a temporary condition:

- Full inbox.
- Destination server temporarily unresponsive.
- Temporary rate limiting or greylisting.
- Self-recovering routing or network issues.

Sometimes the provider continues retrying after reporting `delayed` without the application needing to resend. If the application also creates a new email immediately upon receiving a temporary notice, the recipient can receive duplicates if the provider succeeds on the original message.

Therefore, distinguish:

- **Delay event:** message is still held by relay/provider for retry.
- **Final soft bounce:** provider stopped attempting delivery after retries and reported undeliverable.
- **Temporary SMTP rejection before acceptance:** application failed to submit the message and can retry from outbox if the outcome is certain.

Do not automatically turn every `4.x.x` into an immediate resend from the application.

### 7.3. Complaints Are Not Bounces

A **spam complaint** is a signal that the recipient or mailbox provider marked the message as spam. Some providers forward complaints via a feedback loop (FBL) or webhook. This is not necessarily a delivery failure; the message may have reached the receiving system.

Complaints require their own suppression/consent policy, typically stricter than soft bounces. Do not lump complaints into an `SMTP_550` code or treat them as unsent emails.

### 7.4. Unknown and Incomplete Feedback

A DSN lacking a clear `Status`, a message forwarded across multiple hops, or a provider event that cannot be mapped to a delivery should be placed in **UNKNOWN/NEEDS_REVIEW** rather than automatically deleting the recipient.

Misclassifying a hard bounce can cause the system to stop sending important notifications to a still-valid address. A safe policy must prioritize source authenticity and correlation reliability.

## 8. Deliverability and the Relationship to SPF, DKIM, and DMARC

The bounce address is not only for receiving DSNs. The domain of the SMTP envelope sender also affects SPF and domain authentication results:

| Component | Related Domain | Role |
| --- | --- | --- |
| SPF | Domain of envelope `MAIL FROM` (or HELO when reverse-path is empty) | Indicates which IPs/servers are permitted to send for that domain |
| DKIM | Domain in signature `d=` | Signature authenticating message headers/body |
| DMARC | Domain displayed in header `From` | Requires SPF and/or DKIM alignment, plus domain policy |
| Reply-To | Domain of reply address | Does not replace SPF/DKIM/DMARC alignment |
| Return-Path | Reflects envelope sender on delivery | Should not be written manually as an arbitrary header |

Example:

~~~text
Header From: notifications@example.com
Envelope MAIL FROM: bounces@bounce.example.com
DKIM d=example.com
~~~

Under DMARC relaxed alignment, subdomain `bounce.example.com` can be considered aligned with organizational domain `example.com` if SPF passes and alignment conditions are met. A DKIM signature whose domain aligns with Header From can also enable DMARC to pass. Actual outcomes depend on DNS, organizational domain boundaries, alignment mode, and whether the provider actually signs/sends as configured.

**Do not merely name a subdomain similarly and assume SPF passes.** The bounce domain must have SPF/DNS records matching the sending infrastructure and provider; DKIM must be properly configured/authorized. With a custom return-path, follow the provider's DNS instructions and inspect real authentication results.

### 8.1. Do Not Change the Bounce Domain Arbitrarily

Switching the envelope sender to a domain without configured SPF/MX/catch-all or without provider ownership verification can cause the application to:

- Have `MAIL FROM` rejected by the SMTP relay.
- Receive no DSNs because the bounce domain is misrouted.
- Produce unexpected SPF/DMARC alignment results.
- Make deliverability reports hard to reconcile due to shifting domains.

Bounce domain changes should be managed like mail infrastructure changes: configure DNS, test routing, verify SPF/DKIM/DMARC, and roll out with monitoring.

## 9. Two Approaches to Collecting Bounces: Webhooks and Mailboxes

Once the bounce address is configured, the application needs a **feedback ingestion path**. Two patterns are commonly used:

| Criterion | Email Provider Webhook/API | DSN Mailbox via IMAP |
| --- | --- | --- |
| Ingestion path | Provider POSTs HTTP(S) events | Application polls or receives mailbox |
| Format | Provider-specific JSON/event schema | Email/MIME, typically `multipart/report` |
| Correlation | Provider message ID, event ID, recipient, metadata | VERP token, original envelope ID, DSN recipient/header |
| Source security | Webhook signature/token/identity defined by provider | Mailbox credentials; DSN payload can still be spoofed |
| Format stability | Follows provider contract | Standard DSN and many real-world variants |
| Operations | Endpoint, event retries, signature verification | Mailbox storage, UIDs, polling, MIME parsing |
| When to use | Provider supports reliable event delivery | Traditional SMTP relay or NDR via mailbox required |

If using an email service with official webhooks, webhook integration usually avoids writing parsers for numerous MIME/DSN variations. If using a self-managed SMTP server without webhooks, a DSN mailbox over IMAP or an inbound mail gateway may fit better.

Both approaches require **source verification**, correlation, history storage, deduplication, and idempotent processing.

### 9.1. Provider Webhook Flow

~~~text
Provider detects delivery failure
                |
                v
HTTPS POST to /webhooks/mail-provider
                |
                v
Verify signature / timestamp / replay
                |
                v
Parse provider-specific schema
                |
                v
Normalize to internal delivery event
                |
                v
Persist event idempotently
                |
                v
Update delivery state + suppression policy
                |
                v
Return 2xx after durable receipt
~~~

Webhooks can be redelivered if the provider does not receive HTTP 2xx or times out. Thus **duplicate events are normal**. Do not repeatedly increment bounce counts or reapply suppression just because the same event was redelivered.

### 9.2. DSN Mailbox Flow

~~~text
SMTP reverse-path -> bounce mailbox
                         |
                         v
                 IMAPS / inbound gateway
                         |
                         v
                  Read MIME message
                         |
                         v
          Locate message/delivery-status part
                         |
                         v
           Extract recipient/action/status
                         |
                         v
            Match delivery by trusted token
                         |
                         v
             Persist normalized event
                         |
                         v
              Mark processing checkpoint
~~~

With IMAP, **the SEEN flag should not be the sole durable checkpoint**: the process can crash after marking SEEN yet before committing the event, or vice versa. Store UID/UIDVALIDITY and processing status in the database, with idempotent reprocessing if needed.

## 10. Receiving Webhooks in Spring

Spring MVC can expose an endpoint to receive delivery/bounce events from a provider. Unlike `JavaMailSender` APIs, webhook schemas are **not standardized across providers**, so write dedicated adapters.

An interface defining verification and normalization:

~~~java
package com.example.mail.feedback;

import org.springframework.http.HttpHeaders;
import java.util.List;

public interface ProviderWebhookVerifier {
    boolean verify(byte[] rawBody, HttpHeaders headers);
}

public interface ProviderBounceDecoder {
    List<NormalizedDeliveryEvent> decode(byte[] verifiedBody);
}
~~~

`verify` is where the provider-published verification algorithm (e.g., HMAC or asymmetric signature) runs using the **raw body**, signature header, and timestamp/anti-replay when available. Do not assume every provider uses the same header or signing formula.

Illustrative controller:

~~~java
package com.example.mail.feedback;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/webhooks/mail-provider")
public class MailProviderWebhookController {

    private final ProviderWebhookVerifier verifier;
    private final ProviderBounceDecoder decoder;
    private final BounceEventIngestService ingestService;

    public MailProviderWebhookController(
            ProviderWebhookVerifier verifier,
            ProviderBounceDecoder decoder,
            BounceEventIngestService ingestService) {
        this.verifier = verifier;
        this.decoder = decoder;
        this.ingestService = ingestService;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Void> receive(
            @RequestBody byte[] rawBody,
            @RequestHeader HttpHeaders headers) {

        if (!verifier.verify(rawBody, headers)) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
        }

        ingestService.persistVerifiedEvents(decoder.decode(rawBody));
        return ResponseEntity.accepted().build();
    }
}
~~~

`BounceEventIngestService` is the application service defined below, responsible for **durably persisting** events or enqueuing them to a durable queue before the HTTP handler returns a success code. If persistence fails, return an error response so the provider can retry per its contract; never return 2xx before data is safely received.

### 10.1. Mandatory Webhook Requirements

- Use HTTPS; never accept sensitive events over plain public HTTP.
- Verify signatures/tokens strictly per **provider instructions**; do not treat caller domain/host alone as sufficient proof.
- If the provider signs with a timestamp, validate the time window and store/block replays per their supported mechanism.
- Do not parse and re-serialize JSON **before** checking HMAC over raw body bytes when the provider signs raw bytes.
- Enforce request size limits at the gateway/web server before reading into memory.
- Apply rate limits, timeouts, and per-batch event caps.
- Use IP allowlists only as an extra layer when provided by the provider; IP allowlists do not replace signature verification.
- Accept only supported event types; route unknown types to safe handling/logging.
- Avoid logging raw payloads since they may contain recipients, subjects, message IDs, or personal data.

**Never take any random webhook with a `recipient` field and immediately block sending to that address.** Apply policy only after verifying source, event, correlation, and valid tenant/delivery scope.

### 10.2. Why Return 2xx Only After Persisting Events?

Many providers resend webhooks if requests time out or receive non-2xx. If the application returns 2xx first and processes in a non-durable thread, a crash can permanently lose bounce events. Therefore, use one of two patterns:

1. Persist events to the database inside a transaction, then return 2xx.
2. Push verified events onto a durable queue with acknowledgment before returning 2xx.

When using an at-least-once queue, consumers must still be idempotent. Webhook redelivery and queue redelivery can both produce duplicates; deduplication must be enforced at state-update time.

## 11. Reading DSNs from a Mailbox Using Jakarta Mail

If sending infrastructure delivers bounces to a mailbox, the application can use **Jakarta Mail** to connect via IMAPS or integrate with an inbound mail service. Spring Framework Mail primarily supports sending; the application must manage reading mail, MIME parsing, and checkpointing.

Example mailbox polling skeleton:

~~~java
import jakarta.mail.Folder;
import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.Store;
import java.util.Properties;

public class BounceMailboxPoller {

    public void poll(
            String imapHost,
            String username,
            String password) throws Exception {

        Properties props = new Properties();
        props.put("mail.store.protocol", "imaps");
        props.put("mail.imaps.ssl.checkserveridentity", "true");

        Session session = Session.getInstance(props);
        Store store = null;
        Folder folder = null;

        try {
            store = session.getStore("imaps");
            store.connect(imapHost, username, password);
            folder = store.getFolder("INBOX");
            folder.open(Folder.READ_ONLY);

            for (Message dsn : folder.getMessages()) {
                // Production: use IMAP UID/UIDVALIDITY checkpoint,
                // filter unprocessed records and limit batch size.
                // Parse multipart/report + message/delivery-status.
                // Normalize / correlate / persist idempotently.
            }
        } finally {
            if (folder != null && folder.isOpen()) {
                folder.close(false);
            }
            if (store != null && store.isConnected()) {
                store.close();
            }
        }
    }
}
~~~

This is an **illustrative skeleton**, not a complete production poller: it lacks batching, checkpointing, size limits, DSN parsing, and rate limiting. IMAP passwords must come from a secret manager/runtime config, never hard-coded or logged. For mailboxes with many messages, do not rescan all of `getMessages()` every cycle; use UIDs and appropriate filters.

### 11.1. DSN Parsers Must Understand the MIME Tree

A standard bounce can contain:

~~~text
multipart/report
├── text/plain                      human-readable notice
├── message/delivery-status         machine-readable recipient status
└── message/rfc822 or text/rfc822-headers (optional)
~~~

Do not extract a few lines from the body with ad-hoc regex and treat them as reliable. A parser workflow should:

1. Identify `multipart/report` and `report-type=delivery-status` when present.
2. Locate the `message/delivery-status` part, including valid nested MIME levels.
3. Read per-message fields and per-recipient blocks.
4. Normalize `Action`, `Status`, `Final-Recipient`, and `Diagnostic-Code`.
5. Correlate to an actual delivery in the system.
6. Persist controlled evidence and normalized status.

If using a dedicated parser library tied to a Jakarta Mail implementation, verify the version/package of DSN extensions (DSN packages across implementations can differ). Do not assume every `message/delivery-status` is automatically converted by JavaMail into the exact same Java object across all versions.

### 11.2. One DSN Can Cover Multiple Recipients

Example:

~~~text
Final-Recipient: rfc822; a@receiver.example
Action: failed
Status: 5.1.1

Final-Recipient: rfc822; b@receiver.example
Action: delayed
Status: 4.2.2
~~~

Do not collapse both recipients into a single result. Recipient A may need hard suppression, while the MTA is still retrying B. This is a strong reason for applications to maintain **one delivery record per recipient** rather than one status for an entire To/Cc/Bcc list.

### 11.3. Authenticity of DSNs Received via Mailbox

Receiving an email with `From: MAILER-DAEMON` or MIME type `message/delivery-status` **does not prove the event is genuine**. Attackers can send forged emails to a bounce mailbox if the address is guessable.

Reduce risk by:

- Hosting the bounce mailbox on controlled domains/infrastructure.
- Preferring provider events with verification mechanisms when available.
- Using opaque correlation tokens in envelopes or verifiable provider IDs.
- Matching delivery ID, recipient, domain, and recorded system state.
- Not triggering automatic suppression on unmatched events or untrusted sources.
- Limiting MIME recursion depth, message size, and recipient block counts to prevent DoS.
- Never writing arbitrary attachments from DSNs to the filesystem unnecessarily.

If source authenticity cannot be established with sufficient confidence, route the event to an investigation queue rather than automatically disrupting communication with recipients.

## 12. Data Model: Separating Send Outbox and Delivery Feedback

In transactional applications, an outbox table may already track email workers. That table typically has states such as `PENDING`, `PROCESSING`, `RETRY`, `SENT`, or `FAILED`.

After a successful SMTP call, **bounces can arrive minutes or hours later**. Therefore, using a single `status` column for both outbox and deliverability easily causes confusion:

~~~text
Outbox lifecycle:
PENDING -> PROCESSING -> SENT

Delivery feedback (after SMTP acceptance):
SUBMITTED -> DEFERRED -> RECEIVER_ACCEPTED
                     \-> HARD_BOUNCED / SOFT_BOUNCED
                     \-> UNKNOWN
~~~

Do not automatically flip outbox `SENT` to `FAILED` upon receiving a bounce if `SENT` is defined as "SMTP submission completed." Instead, store a separate **delivery status** or event history representing post-SMTP stages.

### 12.1. One Delivery Record per Recipient

PostgreSQL table example:

~~~sql
CREATE TABLE mail_delivery (
    id UUID PRIMARY KEY,
    outbox_id UUID,
    tenant_id UUID NOT NULL,
    recipient VARCHAR(320) NOT NULL,
    template_name VARCHAR(120) NOT NULL,
    envelope_sender VARCHAR(320),
    provider VARCHAR(80),
    provider_message_id VARCHAR(250),
    submit_status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    feedback_status VARCHAR(40) NOT NULL DEFAULT 'AWAITING_FEEDBACK',
    smtp_accepted_at TIMESTAMPTZ,
    receiver_accepted_at TIMESTAMPTZ,
    last_feedback_at TIMESTAMPTZ,
    last_bounce_code VARCHAR(30),
    last_bounce_category VARCHAR(40),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_mail_delivery_provider_message
    ON mail_delivery(provider, provider_message_id);

CREATE INDEX ix_mail_delivery_recipient
    ON mail_delivery(tenant_id, recipient);
~~~

`outbox_id` links the internal send task, while `provider_message_id` correlates provider events. If one provider ID represents a multi-recipient message, that ID is **not unique per delivery**; combine it with recipient or delivery metadata.

The `feedback_status` field can use:

| Value | Meaning |
| --- | --- |
| `AWAITING_FEEDBACK` | Submitted to transport; no post-send event received yet |
| `DEFERRED` | Provider/MTA is delaying or continuing retries |
| `RECEIVER_ACCEPTED` | Provider reported the receiving side accepted delivery |
| `HARD_BOUNCED` | Confirmed permanent failure per policy |
| `SOFT_BOUNCED` | Confirmed temporary/final soft failure per policy |
| `COMPLAINED` | Spam complaint feedback received |
| `UNKNOWN` | Insufficient data to decide |

Receiving no event **does not prove** delivery failed. Many systems lack complete delivery receipts, so `AWAITING_FEEDBACK` can persist long-term; enforce retention and clear presentation rather than assuming `DELIVERED` after a timeout.

### 12.2. Event History for Reconciliation

Store events arriving from providers/mailboxes in append-only fashion:

~~~sql
CREATE TABLE mail_delivery_feedback_event (
    id UUID PRIMARY KEY,
    delivery_id UUID NOT NULL REFERENCES mail_delivery(id),
    source VARCHAR(80) NOT NULL,
    source_event_id VARCHAR(250) NOT NULL,
    recipient VARCHAR(320) NOT NULL,
    feedback_type VARCHAR(40) NOT NULL,
    enhanced_status VARCHAR(20),
    smtp_reply_code VARCHAR(10),
    safe_reason VARCHAR(300),
    occurred_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ux_mail_feedback_event UNIQUE (
        source, source_event_id, recipient
    )
);

CREATE INDEX ix_mail_feedback_delivery_time
    ON mail_delivery_feedback_event(delivery_id, received_at);
~~~

The schema assumes the adapter supplies a `source_event_id` stable within the source scope. If a provider lacks event IDs, the application must define a careful fingerprint/deduplication scheme; never generate a fresh UUID for the same event on each webhook retry and expect the unique constraint to block duplicates.

Keeping event history lets you analyze timelines such as:

~~~text
09:00 submitted_to_provider
09:01 deferred (4.2.2 mailbox full)
09:11 deferred (4.2.2 mailbox full)
10:15 receiver_accepted
~~~

A `DEFERRED` event does not mean final failure. If a success event arrives later, the aggregate record should update according to ordering rules and each provider's reliability semantics.

## 13. Normalizing Events from Multiple Sources

Provider A may call an event `bounce`, provider B distinguishes `temporary_failure` and `permanent_failure`, while DSNs use `Action: failed` alongside `Status`. The application should translate them into a **common model**, keeping raw/provider-specific metadata in adapters or protected audit areas if needed.

~~~java
package com.example.mail.feedback;

import java.time.Instant;
import java.util.UUID;

public enum DeliveryFeedbackType {
    RECEIVER_ACCEPTED,
    DELAYED,
    HARD_BOUNCE,
    SOFT_BOUNCE_FINAL,
    COMPLAINT,
    UNKNOWN
}

public record NormalizedDeliveryEvent(
        String source,
        String sourceEventId,
        UUID deliveryId,
        String recipient,
        DeliveryFeedbackType type,
        String enhancedStatus,
        String smtpReplyCode,
        String safeReason,
        Instant occurredAt) {
}
~~~

These examples describe an **internal contract**; in Java, `public enum` and `public record` must live in their respective files per language rules.

Normalization principles:

1. Determine the true event type per schema/provider, not just searching for the word "bounce" in text.
2. If action is `delayed`, do not turn it directly into a hard bounce.
3. If the event is a permanent failure `5.1.1`, classify as hard bounce after validating source and recipient.
4. If it is a policy block `5.7.1`, do not assume the recipient does not exist; inspect sender/domain error scope.
5. Preserve enhanced status and basic SMTP codes when present in source data.
6. Record provider timestamps when available, alongside the system's ingestion timestamp.
7. Never store raw diagnostic messages in publicly displayed columns; map to normalized `safeReason`.
8. If delivery or recipient cannot be correlated, route to `UNMATCHED/NEEDS_REVIEW` instead of updating the wrong recipient.

### 13.1. Correlation Is Mandatory

Usable correlation keys:

- Opaque delivery ID embedded in a VERP token.
- Provider message ID paired with the exact recipient.
- Original envelope ID when supported by provider/MTA.
- Provider metadata/custom arguments if the API supports them and guarantees round-trip.

`Message-ID` in MIME headers helps tracing yet is not always unique per recipient and can appear in forwarded DSNs. Never treat a single header value as sufficient proof to remove an address from sending lists.

### 13.2. Do Not Trust Recipient Emails in DSNs Without Mapping to a Delivery

Suppose a DSN claims:

~~~text
Final-Recipient: rfc822; customer@example.net
Status: 5.1.1
~~~

If the application never sent a matching message to `customer@example.net` or cannot verify the DSN source, never block this address immediately. An attacker could send forged DSNs to disrupt someone else's notifications.

Even when the recipient exists in the database, correlate against the **specific delivery, tenant, timeframe, and trusted ingestion channel**.

## 14. Idempotent Processing and Transactions When Receiving Events

Both webhooks and consumers can redeliver. A bounce delivered twice must not increment counters or apply suppression twice.

Safe update flow:

~~~text
Verify + normalize event
          |
          v
Start database transaction
          |
          +--> Validate delivery + recipient + tenant
          |
          +--> Insert event with unique event key
          |      |
          |      +--> Duplicate? stop, no side effect
          |
          +--> Update delivery feedback projection
          |
          +--> Update suppression if policy says so
          |
          v
Commit transaction
          |
          v
Ack provider / mailbox checkpoint
~~~

Example service using repository abstractions:

~~~java
package com.example.mail.feedback;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BounceEventIngestService {

    private final DeliveryRepository deliveries;
    private final FeedbackEventRepository events;
    private final SuppressionPolicyService suppressions;

    public BounceEventIngestService(
            DeliveryRepository deliveries,
            FeedbackEventRepository events,
            SuppressionPolicyService suppressions) {
        this.deliveries = deliveries;
        this.events = events;
        this.suppressions = suppressions;
    }

    @Transactional
    public void persistVerifiedEvents(
            java.util.List<NormalizedDeliveryEvent> input) {

        for (NormalizedDeliveryEvent event : input) {
            DeliveryRecord delivery =
                    deliveries.lockById(event.deliveryId())
                            .orElseThrow(
                                    () -> new UnknownDeliveryException(
                                            event.deliveryId()));

            if (!delivery.recipient()
                    .equalsIgnoreCase(event.recipient())) {
                throw new InvalidDeliveryFeedbackException(
                        "Event recipient does not match delivery");
            }

            // DB unique constraint prevents the same event
            // from creating duplicate side effects.
            if (!events.insertIfAbsent(event)) {
                continue;
            }

            deliveries.applyFeedback(delivery, event);

            if (event.type() == DeliveryFeedbackType.HARD_BOUNCE) {
                suppressions.applyVerifiedHardBounce(
                        delivery.tenantId(),
                        delivery.recipient(),
                        event);
            }
        }
    }
}
~~~

`DeliveryRepository`, `FeedbackEventRepository`, `SuppressionPolicyService`, and application exceptions are **illustrative abstractions**, not built-in Spring Mail APIs. `insertIfAbsent` must execute atomically at the database; never merely check `existsById` then `save`, as two concurrent requests can pass simultaneously.

A production implementation must also define policy for mismatched events, batches mixing valid and invalid events, and state update rules when events arrive late or out of order. Using one transaction for an entire batch risks rolling back all events on one bad event; process each event in its own transaction or route anomalous events to dead-letter so others are not blocked.

### 14.1. Guarding Against Out-of-Order Events

Providers may redeliver or deliver events out of chronological order:

~~~text
Provider emits: DEFERRED -> RECEIVER_ACCEPTED
Application receives: RECEIVER_ACCEPTED -> DEFERRED
~~~

If workers update `feedback_status` strictly by HTTP request arrival order, the final status could regress to `DEFERRED` despite already receiving proof of receiver acceptance.

Define a **state transition policy**:

- `DEFERRED` does not overwrite `RECEIVER_ACCEPTED` merely by arriving later.
- `HARD_BOUNCED` and `COMPLAINED` are critical events to retain in history even if the current projection differs.
- If a provider sends conflicting events, preserve the full timeline and flag for reconciliation rather than arbitrarily dropping an event.
- Use provider event timestamps when available, while not trusting timestamps from unverified sources or assuming clocks across systems are always synchronized.

Ordering policies should align with each **provider's definitions** and per delivery. A single fixed priority across all providers may misbehave across delayed, final bounce, and delivered edge cases.

### 14.2. Do Not Turn One Recipient's Bounce into a Batch Failure

If a message goes to multiple recipients, SMTP responses or DSNs may report:

~~~text
a@receiver.example -> delivered
b@receiver.example -> hard bounced
c@receiver.example -> delayed
~~~

Update only each corresponding `mail_delivery`; never mark the entire business event `FAILED` because one address bounced. For important transactional emails, **one delivery row per recipient** is usually the easiest architecture to audit and retry.

## 15. Suppression Policy: When to Stop Sending?

A **suppression list** is a list of addresses or identities to which the system should stop sending under a defined policy scope. Suppression triggers can include:

- Verified hard bounce.
- Spam complaint.
- Marketing email unsubscribe.
- A sequence of soft bounces exceeding a threshold within a time window.
- Decisions by a user, administrator, or anti-abuse system.

Do not collapse all reasons into a single `isBlocked` flag. Store **source, type, and scope** so the system knows why a recipient was suppressed and when it may be restored.

Example:

~~~sql
CREATE TABLE mail_suppression (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    recipient VARCHAR(320) NOT NULL,
    reason VARCHAR(40) NOT NULL,
    source_delivery_id UUID,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    CONSTRAINT ux_mail_suppression UNIQUE (
        tenant_id, recipient, reason
    )
);
~~~

This schema is illustrative only. If a product distinguishes marketing and transactional emails, add channel/scope or a separate policy layer. A hard bounce from a nonexistent mailbox may affect all mail types to that address, whereas a marketing unsubscribe must not necessarily block mandatory security alerts.

### 15.1. Hard Bounce: Blocking Invalid Addresses

With high-confidence evidence that a mailbox does not exist (e.g., enhanced status `5.1.1`, verified event mapped to the right delivery), you can:

1. Record the `HARD_BOUNCE` event.
2. Update `mail_delivery.feedback_status = HARD_BOUNCED`.
3. Create or update the suppression record per scope.
4. Record timestamp and event source for audit.
5. For important user accounts, prompt the user to verify or provide a new email address through a trusted channel.

Do not immediately resend to a confirmed invalid address just to "test if it works now." If the user updates their email or re-verifies mailbox ownership, lift suppression through a defined workflow.

### 15.2. Soft Bounce: Threshold and Time Window Tracking

A single soft bounce does not prove the recipient no longer exists. You can use a policy like:

~~~text
If DELAYED event received:
  -> Wait for provider to keep retrying; do not send a new message immediately.

If FINAL SOFT BOUNCE received:
  -> Record failure for the current delivery.
  -> Increment soft-bounce score/count per recipient within time window.
  -> Temporarily suppress only if defined threshold is exceeded.
  -> Allow re-evaluation after the cooldown window expires.
~~~

Hypothetical policy example: three final soft bounces within seven days temporarily pause marketing sends to that address for 48 hours. This is only a **business configuration example**, not a universal standard. Thresholds should weigh volume, provider, mail type, and delivery risk.

Do not count every `delayed` webhook or internal attempt as a final soft bounce; a provider may emit dozens of delay events for a single message being retried.

### 15.3. Complaints and Consent

Spam complaints and unsubscribes typically relate to email consent. A verified complaint may require stopping marketing emails immediately under applicable policies and legal obligations.

Do not use `Reply-To` or the bounce address as a substitute for an unsubscribe mechanism. Bounces reflect **delivery failures**; unsubscribes reflect **recipient intent**. Both can feed into suppression, yet they are two distinct signals.

### 15.4. Balancing Suppression with Critical Transactional Emails

For account verification emails, invoices, or security alerts, do not silently skip sending and mark the task successful when a recipient is suppressed.

You can:

- Mark the delivery `SUPPRESSED` or `NOT_ATTEMPTED` with an explicit reason.
- Display an in-app notice that the email address needs verification/correction.
- Prompt for an address update through an appropriately secured flow.
- Use an alternative user-authorized channel when necessary.
- Keep an audit record showing the system **did not attempt sending** due to suppression, rather than reporting SMTP accepted.

For addresses required to receive notices under operational/legal obligations, discuss policies with product owners and compliance teams; do not enable a blanket block across all mail types by default.

## 16. Retries and Bounces: Avoiding Overlapping Retry Loops

When calling SMTP, the application may need to retry transient errors **before the message is accepted**. Yet once the message is accepted by the provider, the provider itself handles delivery retries to the destination mailbox.

The two retry loops have distinct boundaries:

~~~text
Application -> SMTP provider
    |
    +--> Connection refused / reject before acceptance
    |       |
    |       v
    |   Application outbox retry
    |
    +--> 250 message accepted
            |
            v
       Provider attempts delivery
            |
            +--> temporary deferral
            |       |
            |       v
            |   Provider retries internally
            |
            +--> final failure
                    |
                    v
                Bounce / DSN
~~~

**Do not create a new message simply because the provider emitted a `DEFERRED` event.** Doing so puts the same notification in both the provider's queue and the application's queue.

### 16.1. Retrying Synchronous Errors

When `JavaMailSender.send(...)` throws `MailException`, classify as follows:

| Situation | Typically Appropriate Decision |
| --- | --- |
| Cannot open connection to SMTP | Retry with backoff and limit |
| SMTP rejects AUTH | Alert on configuration; stop retrying quickly |
| Invalid recipient address explicitly rejected | Fix data or suppress; do not retry as-is |
| SMTP provider temporarily busy/throttled | Retry per provider guidance/rate limit |
| Timeout after DATA was sent | Outcome may be unknown; duplicate/UNKNOWN policy |

A timeout does not always prove the provider never accepted the message; check the SMTP stage and nested exceptions.

### 16.2. Retrying After a Final Bounce

When the provider reports a **final soft bounce**, resending a new message may be permitted after a cooldown depending on business rules. However:

- Be certain it is a final event, not merely a temporary deferral.
- Do not retry if the email contains an expired token.
- Do not exceed attempt caps or provider quotas.
- Check the suppression list before creating a new delivery.
- Assign a distinct delivery ID/event key for the valid resend and audit the link to the previous message.

For verified hard bounces, immediately resending to the same address rarely helps. For complaints, retrying marketing can violate recipient wishes and sending policies.

### 16.3. Duplicate Window in Transactional Outboxes

Even before bounces, an outbox system has a failure window:

~~~text
Worker sends to SMTP -> SMTP accepts message
          |
          v
Worker crashes before marking outbox SENT
          |
          v
Another worker retries -> duplicate submission possible
~~~

A typical outbox provides **at-least-once** semantics, not guaranteed exactly-once SMTP delivery. Correlation ID/`Message-ID` aids tracing yet does not force every SMTP server to deduplicate messages. If the provider offers an API idempotency key, use it per provider contract; with plain SMTP, accept and manage duplicate risk.

## 17. Common Design Mistakes

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Thinking `helper.setFrom` sets the bounce address | DSN goes elsewhere or is rewritten by provider | Configure envelope `MAIL FROM`/custom return-path |
| Using `Reply-To` as bounce address | Users reply fine, yet bounces never arrive | Separate Reply-To and envelope sender |
| Manually adding `Return-Path` header | Does not change actual envelope; may be overwritten | Use SMTP transport/provider config |
| Creating bounce mailbox without route/MX | DSNs never reach processor | Configure DNS/inbound routing properly |
| Mutating `mail.smtp.from` on singleton Session per request | Race condition under concurrent sending | Per-message mechanism/provider correlation |
| Catching only `MailSendException` | Misses bounces occurring after `send` succeeds | Add webhook/IMAP feedback pipeline |
| Treating every `4xx` as immediate retry | Provider is also retrying, causing duplicates | Distinguish deferral from final soft bounce |
| Treating every `5xx` as nonexistent address | False suppression when sender is policy-blocked | Classify by stage/subject/status/provider |
| Relying on `From: MAILER-DAEMON` for verification | Spoofed DSNs can suppress valid recipients | Source verification + correlation |
| Ignoring duplicate webhooks | Counts bounces multiple times, wrong suppression | Unique event key + idempotent transaction |
| Relying solely on `Message-ID` for all recipients | Partial bounce misattributed across deliveries | Provider ID + recipient/delivery token |
| Single status for both outbox and feedback | Loses distinction between `SMTP_ACCEPTED` and `BOUNCED` | Separate submission and delivery status |
| Updating feedback by arrival order | Stale event overwrites newer event | State transition + timeline policy |
| Logging raw DSNs or full original emails | Leaks personal data/tokens | Safe diagnostics + retention |
| Retrying on `DELAYED` | Duplicate sends while provider is still trying | Wait for final outcome or explicit policy |
| Treating complaints like soft bounces | Continues unwanted marketing sends | Dedicated complaint suppression |

## 18. Security and Privacy of the Bounce Channel

A DSN does not contain only status codes. It may include recipient addresses, subjects, message headers, or part/all of the original email depending on transport settings. For account verification emails, the original message may contain tokenized URLs.

Key safeguards:

1. **Minimize collected data:** Prefer `HDRS` rather than requesting full message return if the application does not need the body.
2. **Verify sources:** Webhooks need provider signatures/auth; mailbox DSNs need correlation and trustworthiness checks.
3. **Least privilege:** Bounce workers only need permissions to read mailboxes/events and update delivery/suppression within scope.
4. **Protect credentials:** IMAP passwords, webhook signing secrets, API tokens, and SMTP credentials must come from secure runtime sources.
5. **Prevent replays:** Unique source event IDs, timestamps, provider signatures, and idempotent logic.
6. **Bound load:** HTTP request size, MIME size, recursion depth, and recipient/event counts.
7. **Do not log raw:** Avoid logging raw webhook payloads, DSNs, recipient lists, or original MIME.
8. **Retention:** Delete/anonymize sensitive data after the window needed for deliverability and auditing.
9. **Do not suppress from unverified events:** Hold in an investigation queue when inconclusive.
10. **Dashboard permissions:** Support staff do not need to read full original emails to see bounce reasons.

### 18.1. Avoiding Mail Loops and Backscatter

Never implement an automated mechanism that sends "undeliverable mail" notices to the `From` address of an untrusted message. This can generate **backscatter**: failure notifications sent to victims whose addresses were spoofed.

If an application were an actual mail transfer agent required to generate DSNs, it would have to obey SMTP rules on null reverse-path and notification limits; however, typical Spring Mail business notification apps **should not reinvent an MTA**. Let the provider/SMTP server generate DSNs, while the application only ingests and processes events.

## 19. Metrics and Deliverability Observability

A system storing bounces should expose metrics so operators detect problems early:

| Metric | Interpretation |
| --- | --- |
| `mail_submission_accepted_total` | Deliveries accepted by SMTP transport/provider |
| `mail_submission_failed_total` | Deliveries failing before submission succeeded |
| `mail_delivery_feedback_total` | Feedback events by type/status code |
| `mail_hard_bounce_total` | Deliveries with verified hard bounces |
| `mail_soft_bounce_final_total` | Deliveries with final soft bounces |
| `mail_delivery_deferred_total` | Delivery deferral events |
| `mail_feedback_unmatched_total` | Events that could not map to a delivery |
| `mail_feedback_duplicate_total` | Duplicate webhooks/DSNs skipped |
| `mail_suppression_active_count` | Recipients currently suppressed by scope |
| `mail_complaint_total` | Verified complaints |
| `mail_feedback_processing_duration_seconds` | Event processing duration |
| `mail_delivery_event_lag_seconds` | Delay from provider event time to ingestion |

Never use recipient email, Message-ID, delivery UUID, or raw diagnostic messages as **metric labels**: this blows up cardinality and risks leaking PII. Use bounded dimensions such as provider, template category, tenant tier, bounce category, error code, and environment.

### 19.1. How Is Bounce Rate Calculated?

A baseline formula:

\[
\text{Bounce rate} =
\frac{\text{Final bounced deliveries in cohort}}
{\text{Accepted deliveries sent in cohort}}
\times 100\%
\]

Clearly define:

- Cohort by send time or by bounce receipt time?
- Unit is **message** or **recipient delivery**?
- Only final hard/soft bounces, or also deferrals?
- Does the provider deliver complete events or only partial coverage?
- Are duplicate webhooks and test emails excluded?

Measuring bounce rate as events arriving today divided by emails sent today can skew when bounces arrive days later. For stable dashboards, cohort by SMTP-accepted date and update results over a defined observation window.

### 19.2. Alerts by Root Cause

Examples of useful alerts:

- Unusual rise in `5.1.1` hard bounces: audit address quality and onboarding.
- Simultaneous rise in `5.7.1` across multiple domains: check SPF/DKIM/DMARC and sender reputation, rather than suppressing mailboxes en masse.
- Rise in `4.2.2` for one domain: possible temporary throttling or full mailboxes; check provider policies.
- Rising webhook processing lag: inspect endpoint/queue and database.
- Rising unmatched feedback: check correlation keys, provider message IDs, or event schema changes.
- Empty bounce mailbox despite delivery failures: inspect reverse-path, MX, relay rewriting, and IMAP access.
- Spike in duplicate events: check processing/ACK latency and provider webhook retry policy.

Separate **SMTP submission errors**, **post-submission bounces**, and **complaints** into three distinct observation categories.

## 20. Testing Bounce Addresses and Feedback Processing

Testing should span multiple layers; a single `JavaMailSender.send(...)` call does not prove the bounce pipeline works.

### 20.1. Unit Testing Enhanced Status Classification

Example of an application-built classifier:

~~~java
public enum BounceCategory {
    HARD,
    SOFT,
    UNKNOWN
}

public class BounceClassifier {

    public BounceCategory classify(
            String action,
            String statusCode) {

        if ("delayed".equalsIgnoreCase(action)) {
            return BounceCategory.SOFT;
        }
        if (!"failed".equalsIgnoreCase(action)
                || statusCode == null) {
            return BounceCategory.UNKNOWN;
        }
        if (statusCode.startsWith("5.1.1")) {
            return BounceCategory.HARD;
        }
        if (statusCode.startsWith("4.")) {
            return BounceCategory.SOFT;
        }
        return BounceCategory.UNKNOWN;
    }
}
~~~

This is a **minimal, intentionally conservative classifier**. It treats only `5.1.1` as a definite hard bounce in the example, does not classify many other codes, and does not incorporate provider policy; it cannot substitute for a complete production classifier. In particular, action `delayed` is grouped under soft for analytical clarity only—**it does not mean final soft bounce or permission to resend immediately**.

Testing with JUnit:

~~~java
@Test
void classifiesInvalidMailboxAsHardBounce() {
    BounceClassifier classifier = new BounceClassifier();
    assertEquals(
            BounceCategory.HARD,
            classifier.classify("failed", "5.1.1"));
}

@Test
void doesNotTreatUnknownFailureAsHardBounce() {
    BounceClassifier classifier = new BounceClassifier();
    assertEquals(
            BounceCategory.UNKNOWN,
            classifier.classify("failed", "5.7.1"));
}
~~~

These tests verify a small classifier, not a live SMTP server. Add DSN/provider fixtures for `4.2.2`, `5.2.2`, missing `Status`, invalid recipients, and non-standard responses.

### 20.2. Testing Webhook Authentication and Idempotency

Scenarios to cover:

1. Valid signature, valid payload → event persisted.
2. Invalid signature → 401, no delivery/suppression written.
3. Replayed payload with same event ID → no second side effect.
4. Nonexistent delivery ID in event → does not update any other recipient.
5. Recipient mismatches delivery → rejected or routed to investigation queue.
6. Out-of-order events → feedback projection not wrongly overwritten.
7. Provider sends batch with duplicate event → retains only one record per key.
8. Database fails before commit → endpoint does not ack success so provider can retry.

For raw-body signature schemes, tests must use exact raw bytes rather than assuming re-serialized JSON produces the same signature. Real algorithms/signatures must follow the provider's documentation.

### 20.3. Testing the DSN Parser

Use `.eml` email fixtures created in a test environment:

- `multipart/report` with one recipient `failed 5.1.1`.
- One DSN containing two recipients with different outcomes.
- Event `delayed 4.2.2`.
- DSN with a `message/rfc822` part containing the original.
- DSN missing `Status` or missing `Final-Recipient`.
- Deeply nested or malformed MIME boundary DSN.
- Forged DSN or one unmappable to any delivery.
- Very large DSN blocked by resource limits.

Never send failing emails to real uncontrolled addresses to build tests. Use an inbound mailbox or test SMTP relay configured to emit controlled DSNs.

### 20.4. SMTP Sinks and Their Limitations

An SMTP sink like Mailpit/MailHog is useful for verifying:

- Spring Mail produces the right `From`, `Reply-To`, subject, and MIME.
- The SMTP sender can submit messages to the test environment.
- Message transformations do not corrupt plain text/HTML parts.

However, an SMTP sink **does not prove** Internet bounces or production SPF/DKIM/DMARC work. A simple sink accepts and displays emails rather than delivering to destination mail servers; testing DSNs requires simulating events or using a mail relay configured to generate bounces.

### 20.5. Testing Domain/Return-Path in Staging

In an authorized staging environment:

1. Configure a dedicated bounce domain for staging without using production credentials.
2. Verify DNS and corresponding inbound routing.
3. Submit a message to a valid test recipient.
4. Observe the actual Return-Path and provider metadata.
5. Trigger a controlled failure on a team-owned mail server/test provider.
6. Confirm the DSN/webhook reaches the system, passes verification, and maps to the right delivery.
7. Verify status and suppression apply to the right scope.
8. Replay the same webhook/DSN to confirm idempotency.

Never use an "apparently nonexistent address" belonging to a real person to test hard bounces in production; that can harm sender reputation and affect unrelated recipients.

## 21. Real-World Scenario: Invoice Sent Successfully Yet Bounces Late

Suppose the system needs to email an invoice after an order completes.

### Step 1 — Create Delivery

~~~text
delivery_id: 73f...
recipient: customer@receiver.example
header_from: billing@example.com
envelope_from: bounces+73f@bounce.example.com
submit_status: PENDING
feedback_status: AWAITING_FEEDBACK
~~~

The application writes the outbox/delivery record inside the business transaction, and a worker picks up the send task.

### Step 2 — JavaMailSender Submits Message

~~~text
SMTP relay -> 250 2.0.0 accepted
~~~

Worker records:

~~~text
submit_status: SMTP_ACCEPTED
smtp_accepted_at: [timestamp]
feedback_status: AWAITING_FEEDBACK
~~~

At this point, the email is **not yet guaranteed delivered to the mailbox**.

### Step 3 — Provider Attempts Delivery and Receives Error

Minutes later, the provider receives feedback:

~~~text
Final-Recipient: rfc822; customer@receiver.example
Action: failed
Status: 5.1.1
Diagnostic-Code: smtp; 550 5.1.1 Mailbox does not exist
~~~

A provider webhook or mailbox DSN delivers the event to the application. The processor verifies the source, correlates `delivery_id = 73f...`, and normalizes `HARD_BOUNCE`.

### Step 4 — Persist Feedback and Suppression

Inside a transaction:

~~~text
mail_delivery:
  submit_status: SMTP_ACCEPTED
  feedback_status: HARD_BOUNCED
  last_bounce_code: 5.1.1

mail_delivery_feedback_event:
  delivery_id: 73f...
  feedback_type: HARD_BOUNCE
  enhanced_status: 5.1.1

mail_suppression:
  recipient: customer@receiver.example
  reason: HARD_BOUNCE
  status: ACTIVE
~~~

`submit_status` still accurately reflects that the SMTP relay accepted the message; `feedback_status` reflects **later delivery failure**. The two statuses do not conflict.

### Step 5 — When the User Fixes Their Address

The user updates their email address in the application. The system verifies the new address per product policy, then creates a new delivery if the invoice email still needs to be sent.

Do not infinitely resend to the old address. If the user re-verifies the old address itself, lifting suppression must go through an evidenced, audited workflow.

### Step 6 — If the Webhook Duplicates

The provider sends the same event a second time because the first HTTP response timed out. The unique event key ensures the processor does not create a second suppression or increment hard bounce counts again.

This allows the system to tolerate redeliveries while accurately reflecting a single verified bounce.

## 22. Frequently Asked Questions

**"Why did `JavaMailSender.send()` throw no exception yet the recipient never got the email?"**  
The send method only knows the outcome of the SMTP session the application participated in. The relay server may accept the message and encounter an error later while relaying or delivering to the destination server. Webhooks/DSNs or provider APIs are needed to track post-submission feedback.

**"Does calling `helper.setFrom("bounces@...")` configure bounces?"**  
Not necessarily. `setFrom` sets the From header; the DSN destination is usually determined by SMTP envelope `MAIL FROM` and the provider. Configure `mail.smtp.from` or custom return-path per sending infrastructure.

**"Can I use `helper.setReplyTo(...)` as the bounce address?"**  
No. Reply-To is for email readers' human replies, not where SMTP servers are required to send delivery failure notices.

**"Should I set the `Return-Path` header manually?"**  
No. Return-Path is inserted by the delivery system based on the envelope reverse-path; editing headers does not replace SMTP envelope configuration.

**"Why is Return-Path still different even after configuring `mail.smtp.from`?"**  
The SMTP relay or email provider may override the envelope sender per policy, especially when using an email service with its own custom bounce domain. Check provider configuration and domain verification status.

**"Should one bounce mailbox be used for all emails?"**  
Possibly, if the mailbox/processor can correlate accurately by delivery/recipient. At higher volume, VERP-like aliases or provider metadata usually allow more accurate reconciliation.

**"Does VERP guarantee a DSN is authentic?"**  
No. Opaque tokens in the bounce address aid correlation, yet someone knowing the address can still send forged emails. Protect ingestion sources and act only after validating the event/delivery.

**"Does a bounce mailbox need an MX record?"**  
To receive mail directly over SMTP, the receiving domain must have valid mail routing per infrastructure. Some providers use CNAMEs, custom return-paths, or dedicated routes; follow the provider's mechanism rather than setting arbitrary DNS records.

**"Are bounces always emails from MAILER-DAEMON?"**  
No. Some providers send webhooks or API events, and DSNs come from various MTAs with differing headers. Sender display name is insufficient to verify authenticity.

**"Can a single DSN report on multiple recipients?"**  
Yes. A message sent to multiple addresses can produce different feedback per recipient. Read per-recipient fields and update each delivery accurately.

**"What does code `5.1.1` mean?"**  
Usually bad destination mailbox address, such as a nonexistent mailbox. After verifying source and correlation, this is a classic signal to hard-suppress the address.

**"Should code `4.2.2` be retried immediately?"**  
Not necessarily. It typically relates to full mailbox/temporary conditions. If the provider is still attempting delivery, the application should not submit a new message just because a delay event arrived. Wait for a final outcome or follow provider policy.

**"Are all 5xx codes hard bounces due to nonexistent recipients?"**  
No. `5.7.1` can stem from policy, authentication, or sender reputation. Classify by response, stage, and provider before deciding suppression.

**"Should spam complaints be handled just like hard bounces?"**  
Not entirely. Complaints express unwanted receipt and typically drive consent-based suppression. Hard bounces indicate delivery failure. Both need separate policies and statistics.

**"If there is no bounce, does that mean the email reached the inbox?"**  
No. The provider may not supply complete feedback, the email may be filtered, or the bounce may be delayed/lost. Absence of events is not proof of delivery.

**"If the provider reports `delivered`, did the recipient read the email?"**  
No. Delivered usually reflects the handoff level observed by the provider, not proof the user opened or saw it in the inbox.

**"Should a single `sent` field be used for both sending and bounces?"**  
No. Separate SMTP submission status from delivery feedback status so you do not lose the history of "server accepted, yet delivery failed afterward."

**"How should a webhook arriving twice be handled?"**  
Use the provider event ID/recipient as an idempotency key per provider contract, insert atomically into event history, and update state/suppression only once.

**"What if webhooks arrive out of order?"**  
Keep the full event history and apply a state transition policy. Do not let an older `DEFERRED` event overwrite a newer accepted/delivered outcome simply because its HTTP request arrived later.

**"Should any DSN be trusted to remove an address from sending lists?"**  
No. DSN emails can be spoofed; require correlation and source verification where feasible. Untrusted events should be stored for investigation, not trigger automatic suppression.

**"Do I have to write my own MIME parser for DSNs?"**  
When using official provider webhooks, you can usually avoid parsing numerous DSN variants yourself. With a mailbox, use Jakarta Mail and/or an implementation-appropriate DSN parser with resource limits and fixture tests.

**"Does enabling `mail.smtp.dsn.notify` guarantee the provider will send bounces?"**  
No. It is an SMTP transport extension request when supported by the server. Providers may enforce their own policies and not every failure emits a complete DSN.

**"How does the bounce address affect SPF/DMARC?"**  
SPF checks the envelope sender's domain, while DMARC evaluates alignment with the From header via SPF and/or DKIM. A custom bounce domain must have DNS configured, authenticated, and tested against the provider in practice.

**"Should an email that hard-bounced be retried?"**  
Usually not for an address confirmed nonexistent. If the user fixes/verifies their address or the actual cause was sender policy, the system can create a new valid delivery per workflow.

**"Can Message-ID guarantee single delivery?"**  
No. Message-ID aids tracing yet does not force SMTP servers to deduplicate messages. Outbox+SMTP always has a duplicate window; provider APIs offer idempotency if officially supported.

## 23. Bounce System Implementation Checklist

### Sending Infrastructure and Addresses

1. Clearly define Header From, Reply-To, and envelope MAIL FROM.
2. Have a bounce address/subdomain under the organization's control.
3. Ensure the provider permits and routes that bounce address.
4. Configure DNS, MX/custom return-path, and SPF/DKIM/DMARC per provider.
5. If using VERP, keep tokens secure, free of PII, and backed by inbound routing.

### Feedback Ingestion

6. Choose provider-supported webhooks or a checkpointed DSN mailbox.
7. Verify webhook signatures/raw body and replay protection per provider contract.
8. For DSN mailboxes, parse MIME with size/depth limits and process per-recipient.
9. Never trust an email claiming MAILER-DAEMON without source/correlation checks.
10. Maintain a dead-letter/needs-review queue for unmatched or unclassifiable events.

### Data and Business Logic

11. Separate SMTP submission status from delivery feedback status.
12. Maintain one delivery record per recipient when individual retry/audit is needed.
13. Store feedback events append-only with deduplication keys.
14. Correlate by delivery ID/provider ID/recipient rather than subject alone.
15. Enforce a state transition policy for late or out-of-order provider events.
16. Distinguish hard bounce, final soft bounce, delayed, delivered, and complaint.
17. Apply appropriate suppression policies for verified hard bounces.
18. Never auto-retry a new message while the provider is still retrying the old one.
19. For critical transactional emails, provide clear alternative/recovery paths for suppressed recipients.

### Operations and Testing

20. Use safe error categories/correlation IDs in logs/metrics; never log raw DSNs with sensitive data.
21. Provide dashboards for bounce rate, unmatched events, webhook lag, and suppression.
22. Test invalid signatures, duplicate webhooks, multi-recipient DSNs, and out-of-order events.
23. Test bounce addresses/Return-Path using authorized staging infrastructure.
24. Have processes for address correction, re-verification, redrive, and retention.

## 24. End-to-End Processing Summary

A deliverability system using Spring Framework Mail can follow this chain of responsibility:

~~~text
Business event / Outbox
          |
          v
Build MIME message
  From: notifications@example.com
  Reply-To: support@example.com
          |
          v
SMTP envelope
  MAIL FROM: bounces+deliveryToken@bounce.example.com
  RCPT TO: customer@receiver.example
          |
          v
JavaMailSender.send(...)
          |
      +---+------------------------+
      |                            |
      v                            v
Sync SMTP failure             SMTP accepted
      |                            |
      v                            v
Classify/retry outbox        Later delivery attempt
                                   |
                                   v
                       DSN mailbox or provider webhook
                                   |
                                   v
                      Verify source + normalize event
                                   |
                                   v
                     Match delivery ID + recipient
                                   |
                                   v
                       Idempotent database update
                                   |
                        +----------+----------+
                        |          |          |
                        v          v          v
                    Hard bounce  Soft bounce  Complaint
                        |          |          |
                        v          v          v
                    Suppression  Wait/policy  Consent policy
                        |          |          |
                        +----------+----------+
                                   |
                                   v
                         Metrics / audit / alerts
~~~

### Principles to Remember

- `JavaMailSender.send` returning successfully **does not guarantee inbox delivery**.
- Bounces typically return to the **SMTP envelope sender**, not Header From or Reply-To.
- `Return-Path` is the envelope trace written upon delivery, not a header for the application to edit itself.
- DSNs can arrive late, be incomplete, cover multiple recipients, and even be spoofed.
- Webhooks need verification and idempotent handling; IMAP DSNs need MIME parsers and checkpoints.
- `DELAYED` is not `FAILED`; do not create a new send while the provider is still retrying.
- Hard bounces, soft bounces, and spam complaints require distinct suppression policies.
- Submission state, delivery feedback, and audit events should be stored separately.

**Conclusion:** In Spring Framework Mail, properly designing a bounce address means designing the **SMTP envelope failure-feedback path**, not just putting an email into a header. A complete solution configures a provider-accepted bounce domain/return-path, ingests verified DSNs or webhooks, classifies feedback per recipient, and updates state idempotently. Done right, the application knows which messages failed delivery, stops sending to confirmed invalid addresses, avoids duplicate-causing retries, and collects reliable data to improve deliverability.
