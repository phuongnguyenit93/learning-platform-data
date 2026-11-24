# Provider and Email Gateway Header Rules in Spring Framework Mail

An email can be constructed validly with `JavaMailSender` and still be rejected by an SMTP provider, modified by an email gateway, or arrive in a mailbox with headers different from what the application created. The reason is that **email headers pass through multiple systems, each entitled to enforce its own protocol, security, and policy rules**.

In Spring Framework Mail, developers usually focus on `From`, `To`, `Cc`, `Bcc`, `Reply-To`, and `Subject`. In real-world deployments, however, emails also involve headers for identification, MIME, authentication, unsubscribe lists, tracking, and transport traces. This lesson explains how to read those headers, the boundary between application and provider, typical modifications gateways perform, and how to design Java code to prevent compatibility failures.

## 1. Which Layers Do Email Headers Pass Through?

Consider an order-notification email system:

```text
Spring Application
  |
  | JavaMailSender builds MimeMessage
  | From, To, Subject, Reply-To, MIME, custom headers
  v
SMTP submission / Email Service Provider (ESP)
  |
  | Authenticates account, checks sender, rate limits,
  | accepts/blocks certain headers, may add or rewrite
  v
Outbound email gateway
  |
  | DLP policies, antivirus, disclaimers, DKIM signing,
  | routing, logging, adds Received or internal headers
  v
Internet SMTP / receiving MX
  |
  | SPF / DKIM / DMARC, anti-spam/phishing, MIME checks,
  | adds Received, Authentication-Results per policy
  v
Inbound email gateway
  |
  | Quarantine, attachment filtering, URL rewriting, content inspection
  v
Mailbox / Email client
  |
  | Displays From, Subject, Reply-To, and content
  v
Recipient
```

Not every environment includes every separate gateway. Some systems use an ESP as SMTP relay, filter, and DKIM signer combined; others route through an internal relay before reaching a public ESP. **The header set can change at every hop**, and rules governing header names, lengths, values, and mutability depend on provider configuration.

A real-world workflow must separate three categories of data:

1. **Message headers**: inside the RFC 5322/MIME message content, such as `From`, `Subject`, and `Message-ID`.
2. **SMTP envelope**: protocol-session metadata such as `MAIL FROM` and `RCPT TO`. These are not the displayed headers sharing similar names.
3. **Provider metadata / events**: request IDs, tags, campaigns, provider message IDs, and accepted/delivered/bounced events, which may live in dedicated APIs rather than headers.

Confusing these three categories causes many bugs around reply addresses, bounces, and email tracing.

## 2. Headers Under the Internet Message Format Standard

An email transmitted over SMTP has the general structure:

```text
From: "Store" <orders@example.com>
To: "Customer" <customer@example.net>
Reply-To: support@example.com
Subject: Order notification
Date: Thu, 12 Nov 2026 08:30:00 +0000
Message-ID: <example-123@example.com>
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8
X-App-Correlation-ID: 3fa85f64-5717-4562-b3fc-2c963f66afa6

Hello,

Your order has been received.
```

The example above uses plain ASCII to illustrate raw header syntax. For Vietnamese text, Jakarta Mail encodes required fields via MIME/SMTPUTF8 depending on context and server support.

**The header section ends at the first blank line.** Everything after that blank line is the body. Headers are `field-name: field-value` lines delimited per email standards by CRLF (`\r\n`).

### Syntax Constraints to Keep in Mind

- Header field names use valid ASCII characters; spaces or colons must never appear inside the field name.
- At the protocol level, header names are **case-insensitive**: `Subject` and `subject` refer to the same field.
- Values have field-specific grammars: `To` must hold valid addresses; `Date` follows email date syntax; `Message-ID` follows identifier syntax.
- Header lines have format length limits: a hard maximum of **998 octets excluding CRLF**, with **78 characters** recommended for compatibility and readability. Long headers may need to be **folded** onto continuation lines using valid syntax.
- Never inject raw `\r` or `\n` from external input into headers: doing so causes **header injection**.
- Long headers use specialized encoding and folding. Never build strings and append CRLFs manually; let Jakarta Mail/Spring APIs handle it.
- Standard and MIME headers define rules on whether a field may appear multiple times. In particular, never emit two `From` or two `Subject` headers hoping a gateway interprets them as you wish.

SMTP providers may impose stricter rules than the RFCs: maximum header count, total header size, value length, banned field names, or accepted address formats. Always verify those limits in your specific provider's documentation.

### Common Headers

| Header | Role | Notes |
| --- | --- | --- |
| `From` | Sender identity presented in the email | Usually required to use a verified domain/address |
| `Sender` | Actual transmitting agent when distinct from `From` | Not always needed; has specific syntax and semantics |
| `To` | Displayed recipients | Does not reflect every address in the SMTP envelope |
| `Cc` | Displayed carbon-copy recipients | Can expose the recipient list |
| `Bcc` | Blind carbon-copy recipients | Must not leak in copies delivered to other recipients |
| `Reply-To` | Destination address when the user clicks Reply | Does not control bounce address or DKIM identity |
| `Subject` | Message subject | Use proper MIME encoding for Vietnamese characters |
| `Date` | Message origination timestamp | May be populated when saved/sent |
| `Message-ID` | Standards-based message identifier | Distinct from provider message ID and delivery ID |
| `MIME-Version` | Signals MIME usage | Normally added by Jakarta Mail |
| `Content-Type` | Media type or multipart structure | Set by helper and MIME packaging |
| `Content-Transfer-Encoding` | Transfer encoding for MIME content | Should not be manually altered arbitrarily |
| `Received` | Trace entry for one relay hop | Added by MTAs during transit |
| `Authentication-Results` | Authentication check outcome recorded by receiving system | Trustworthy only inside an established trust boundary |
| `DKIM-Signature` | Cryptographic signature over selected headers and body | Requires attention to signing order and gateway edits |
| `List-Unsubscribe` | Provides unsubscribe mechanism for list emails | ESPs may generate it or enforce specific syntax |

In Spring code, prefer dedicated `MimeMessageHelper` methods for fields with explicit APIs; reserve `setHeader` for truly necessary supplementary headers.

## 3. Distinguishing Address Headers from the SMTP Envelope

This is the single most critical distinction when working with email gateways.

```text
SMTP Envelope:
MAIL FROM:<bounces@mailer.example.com>
RCPT TO:<customer@example.net>

Inside message content:
From: "Shop Example" <orders@example.com>
To: customer@example.net
Reply-To: helpdesk@example.com
Subject: Order update
```

These values serve different functions:

- `From`: what users normally see as the sender.
- `Reply-To`: where email clients suggest sending replies.
- `MAIL FROM` (envelope sender, reverse-path): the address used for **undeliverable/bounce** handling in traditional SMTP; ESPs may control or replace it.
- `RCPT TO`: transport-layer recipients; need not match addresses visible in `To` or `Cc`.

`Return-Path` is a return-route header typically added by the final delivery system at delivery time. **Setting `Return-Path` yourself does not change SMTP `MAIL FROM`.** Gateways/ESPs may strip, overwrite, or replace it based on the actual envelope.

For instance, to receive replies at `support@example.com`, set `Reply-To`. To receive bounces at `bounces@mailer.example.com`, configure the **envelope sender** via a provider-supported mechanism; setting `Return-Path` alone is insufficient.

Configurations using Jakarta Mail's `smtp` transport offer the property:

```properties
spring.mail.properties.mail.smtp.from=bounces@mailer.example.com
```

This sets the transport's `MAIL FROM` and typically applies at the session/transport scope. SMTP providers may still mandate their own bounce domain or require domain verification. When sending on behalf of multiple domains or tenants, design per-send configuration carefully so you do not accidentally share one envelope sender across unrelated accounts.

### Why Doesn't `To` Reveal All Recipients?

SMTP delivery can transmit one message to multiple `RCPT TO` addresses, including Bcc. A gateway may also expand mailing lists, forward recipients, or rewrite destinations per internal policy. Consequently, counting accepted/delivered recipients must rely on **per-recipient send events**, never solely on the `To` header.

## 4. What Rules Do SMTP Providers and Gateways Enforce?

Filters can run at three points: before accepting the message, during relay processing, and upon delivery to the receiving system.

| Rule Category | What Can Happen | Impact on Spring Mail |
| --- | --- | --- |
| Sender checks | Requires `From` to match a verified domain or address | Message rejected or `From` rewritten |
| SMTP / account auth | Account restricted from sending as other senders | Align account, domain, and `From` |
| Syntax validation | Missing colon, malformed address, invalid newlines | Pre-send error or SMTP rejection |
| Data limits | Too many recipients, oversized headers, message too large | Blocked, split, or reprocessed by provider |
| Anti-spoofing policy | Domain alignment or authentication fails | Rejected, quarantined, flagged, or routed to spam |
| Organizational policy | Disclaimers inserted, content filtered, `Subject` modified | Post-gateway headers/content differ from original |
| Link protection | URLs rewritten, links scanned, tracking added | Visible link targets and telemetry change |
| Metadata rules | Reserved headers blocked, tracking IDs added, custom headers stripped | Cannot assume every app-set header survives |
| DKIM signing | Signature added after message is built | Post-signing modifications break verification |
| List rules | `List-Unsubscribe` added or required for marketing mail | Must align API, email type, and ESP policy |

Never assume every provider behaves identically. One ESP might silently rewrite an unverified sender to an authorized one, while another rejects the request outright. One corporate gateway might prepend `[EXTERNAL]` to `Subject`, while another only injects a body banner.

### Outcomes You Must Distinguish

1. **Client-side validation**: application or Jakarta Mail rejects invalid values before sending.
2. **SMTP/API rejection**: provider returns an error, usually with an SMTP/HTTP code and message.
3. **Accepted then filtered**: relay accepts the message yet later blocks or drops it per policy.
4. **Accepted and rewritten**: message continues onward, yet post-gateway headers/body differ from the original.
5. **Delivered to receiving MTA**: destination server accepted the message; does not guarantee inbox placement or reading.

Each outcome implies different error handling and operational observability. Never treat a successful `JavaMailSender.send(...)` call as proof that headers survived intact to the recipient's mailbox.

## 5. Which Headers Should the App Set vs. Library/Provider?

Clear ownership prevents conflicts:

| Field | Appropriate Owner | Why |
| --- | --- | --- |
| `From`, `To`, `Cc`, `Reply-To`, `Subject` | Application, via helper | Directly tied to business semantics |
| `MIME-Version`, `Content-Type`, MIME encodings | Jakarta Mail / `MimeMessageHelper` | Depends on body structure and attachments |
| `Date`, `Message-ID` | Mail library or controlled Message-ID strategy | Requires strict formatting; may be generated on save/send |
| `Received` | SMTP relays / MTAs at each hop | Records actual transport path |
| `Authentication-Results` | Receiving authentication verifier | Meaningful only inside a trusted boundary |
| `DKIM-Signature` | Configured signing infrastructure | Must sign finalized content |
| `Return-Path` | Final delivery system from SMTP envelope | App cannot control it via manual headers |
| `List-Unsubscribe` | App / ESP depending on stream and policy | Requires a valid unsubscribe URL/flow |
| Custom correlation header | Application if permitted by provider | Carries technical IDs for tracing |

Never add trace headers such as `Received` or `Authentication-Results` yourself to "make an email look more trustworthy." They cannot replace SPF/DKIM/DMARC checks and may be stripped, misleading, or treated as untrusted input.

## 6. Building Headers Properly with JavaMailSender and MimeMessageHelper

Spring Framework Mail provides `JavaMailSender` to create `MimeMessage` instances and `MimeMessageHelper` to populate common headers.

Spring Boot 3+ / Spring Framework 6+ example with Jakarta Mail:

```java
package example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderMailService {

    private final JavaMailSender mailSender;

    public OrderMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderNotification(
            String recipient,
            UUID deliveryId,
            String orderCode) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
            message, StandardCharsets.UTF_8.name()
        );

        helper.setFrom("orders@example.com", "Example Store");
        helper.setTo(recipient);
        helper.setReplyTo("support@example.com");
        helper.setSubject("Order confirmation");
        helper.setText(
            "Order " + orderCode + " has been received.",
            false
        );

        // Server-generated ID, containing no secret information.
        message.setHeader(
            "X-App-Delivery-ID",
            deliveryId.toString()
        );
        message.setHeader(
            "X-App-Message-Category",
            "transactional"
        );

        mailSender.send(message);
    }
}
```

Key highlights of the example:

- `helper.setFrom(address, personalName)` supports Vietnamese display names; the helper handles proper encoding.
- `helper.setTo(...)` and `setReplyTo(...)` set addresses through library APIs with built-in parsing rules.
- `helper.setSubject(...)` lets the library encode Vietnamese text instead of building raw headers manually.
- `message.setHeader(...)` is used only for supplementary headers with **safe, fixed-format data**.
- `setHeader` replaces existing values of the same field name; `addHeader` appends another value. Never create duplicate entries for single-value headers.
- `deliveryId` is an application-generated UUID containing no access tokens or sensitive data.

`mailSender.send(...)` dispatches the message via SMTP transport; subsequent modifications at a provider or gateway are outside `MimeMessageHelper`'s direct control.

### Minimal Spring Boot Configuration

```properties
spring.mail.host=smtp.example.com
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}
spring.mail.default-encoding=UTF-8

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true

spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000
```

This configuration is illustrative only. SMTP host, port, account, TLS mode, and sender domain must match your real provider's requirements. A provider may allow sending only from verified domains and enforce its own bounce domain regardless of the `From` configured by your application.

## 7. Validating Address Headers and Preventing Header Injection

A critical risk is constructing raw headers from user input, especially when that input contains newline characters.

**Unsafe** example:

```java
String unsafeName = request.getParameter("displayName");

// Never do this:
message.setHeader("From", unsafeName + " <orders@example.com>");
```

If `unsafeName` contains a newline sequence followed by a new header name, building raw headers via string concatenation can be exploited or rejected by libraries/providers. Depending on the library and transport, risks include header injection, syntax failures, or unintended rendered content.

### Handling Principles

1. **Email addresses**: use address-accepting APIs like `MimeMessageHelper#setTo` or `InternetAddress`. Enforce business checks on length, recipient count, and permitted addresses/domains.
2. **Display names**: use `setFrom(address, personalName)` or APIs with personal-name encoding rather than concatenating raw headers.
3. **Subject**: use `helper.setSubject(...)`; enforce length limits and text normalization suited to business intent.
4. **Custom headers**: allow only tightly structured values such as UUIDs, enums, or short opaque IDs. Reject CR/LF and inappropriate control characters.
5. **Sensitive data**: never embed passwords, JWTs, OTPs, access tokens, private transaction details, or unnecessary personal data in headers.

Example helper validating a value for an internal custom header:

```java
package example.mail;

import java.util.regex.Pattern;

public final class MailHeaderValues {
    private static final Pattern SAFE_ID =
        Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private MailHeaderValues() {}

    public static String requireSafeId(String value) {
        if (value == null || !SAFE_ID.matcher(value).matches()) {
            throw new IllegalArgumentException("Invalid mail header ID");
        }
        return value;
    }
}
```

Then:

```java
message.setHeader(
    "X-App-Trace-ID",
    MailHeaderValues.requireSafeId(traceId)
);
```

This rule is designed for **short opaque ASCII identifiers**, not as a universal validator for every header. Subjects, email addresses, MIME parameters, and other standard fields each have their own syntax; the same regex cannot apply to all of them.

### The Bcc Field and Privacy

`Bcc` is for blind carbon copies. In copies delivered to ordinary recipients, the Bcc list must never be exposed as a header showing all hidden addresses. Use `helper.setBcc(...)` and library mechanisms; never inject raw `Bcc` headers and hand-craft SMTP requests.

When sending bulk emails to recipients who should not see one another's addresses, prefer creating separate per-recipient deliveries or using your ESP's bulk-email recipient-isolation feature. Beyond headers, ensure tracking URLs, template content, and attachments do not leak other recipients' data either.

## 8. Custom Headers and Provider Metadata

Applications sometimes need to pass correlation values: notification type, delivery ID, campaign code, or correlation ID.

Example:

```text
X-App-Delivery-ID: a6741f5e-3b53-4f99-9d27-3f6ab58310e6
X-App-Message-Category: transactional
X-App-Environment: production
```

`X-*` fields appear widely in existing mail systems. In modern standards design, prefixing new headers with `X-` is no longer recommended as a standardization rule; nevertheless, providers may still require or support `X-` prefixed fields. **Header names must follow your actual provider's contract.**

### Why Not Rely Absolutely on Custom Headers?

- Some providers maintain **reserved** headers that they manage and forbid applications from overriding.
- Custom headers may be stripped to minimize personal data or satisfy gateway policy.
- Some ESPs ingest metadata via specialized API/SMTP headers and then **strip those headers from the final email**.
- Gateways may rename or normalize headers; field names are case-insensitive.
- Observing a custom header at SMTP submission does not guarantee it appears when the recipient views the raw message.

If your provider supports **tags, categories, custom arguments, metadata, or correlation IDs** through an official API, prefer that dedicated channel and store mappings to your internal `deliveryId`. If a provider requires a specific header for metadata, follow its documented format exactly rather than guessing syntax from another provider.

### Fields to Avoid Conflicting With

Never arbitrarily overwrite fields owned by Jakarta Mail or the provider, especially:

- `Message-ID`, `Date`, `MIME-Version`, and `Content-*` fields tied directly to MIME structure.
- `DKIM-Signature`: the signature must reflect the finalized signed content and headers.
- `Authentication-Results`, `Received`: reserved for MTA transport traces and verification results.
- `Return-Path`: must align with SMTP envelope/delivery logic.
- Provider-specific `X-...` headers marked as reserved.

Before adding any custom header, verify whether the provider allows it, whether it travels to the mailbox or only serves the API, what size/type limits apply, and whether DKIM signs it.

## 9. From, Reply-To, and Sender Verification Policies

A common scenario: an application authenticates to SMTP using `smtp-account@example.net` yet wants to display:

```text
From: "Service A" <orders@shop.example.com>
Reply-To: support@shop.example.com
```

This is **not automatically permitted** merely because the application can write the header. A provider may require:

- Verifying `shop.example.com` or the `orders@shop.example.com` address.
- Configuring DNS/sender identities per policy.
- Delegated permission on that SMTP account to send on behalf of that address or domain.
- Using a provider-mandated `MAIL FROM`/bounce domain.
- Avoiding display names that impersonate another organization.

If requirements are not met, the provider may reject at SMTP/API, replace `From` with an authorized address, or enforce `Sender` per policy. Never resort to "setting `Reply-To` to our desired address and `From` to the provider's address" without checking UX impact and authentication policies.

**`Reply-To` does not determine SPF, DKIM, or DMARC alignment.** It only indicates the reply address. A `Reply-To` pointing to another domain does not authenticate `From`.

## 10. SPF, DKIM, DMARC, and Email Gateway Impacts

Header rules are tightly bound to sender authentication. Three core mechanisms:

| Mechanism | Relies On | What It Checks |
| --- | --- | --- |
| SPF | Sending IP and SMTP envelope/HELO identity per SPF rules | Whether the sending server is authorized by the corresponding domain |
| DKIM | Signature in `DKIM-Signature`, a set of headers, and body | Whether signed headers and content still match the signature |
| DMARC | Domain in `From` header and aligned SPF/DKIM results | Whether at least one aligned authentication mechanism passes per domain policy |

Example:

```text
From: orders@shop.example.com
MAIL FROM: bounces@mailer.example.net
DKIM-Signature: v=1; d=shop.example.com; ...
```

In this situation, SPF may pass for `mailer.example.net` yet **fail alignment** with the `From` domain. If DKIM verifies with `d=shop.example.com` aligned to `From`, DMARC can still pass. Outcomes depend on strict/relaxed alignment policies and real configuration.

That is why a message accepted over SMTP is not guaranteed to pass identity checks at the destination mailbox.

### When Do Gateway Header Edits Break DKIM?

A DKIM signature lists the signed headers and includes a body hash. If a gateway **modifies signed content** or alters parts not ignored by canonicalization, verification can fail.

Example:

```text
Spring application builds message
    |
    v
Gateway A signs DKIM
    |
    v
Gateway B prepends "[EXTERNAL]" to Subject
    |
    v
Receiving server checks DKIM
    |
    +--> DKIM may fail if Subject was signed and modified
```

Likewise, appending a disclaimer to the body after signing invalidates the body hash. Rewriting MIME boundaries, re-encoding content, or modifying HTML can also break signatures. Certain whitespace changes may survive DKIM canonicalization, so not *every* technical adjustment causes failure.

Sound architectural patterns:

1. Run all planned content transformations (templates, tracking links, disclaimers, MIME packing) **before DKIM signing**.
2. Place DKIM signing at the final controllable outbound hop.
3. If relays/gateways sit downstream of the signer, configure them not to alter signed parts or re-sign under an authorized policy.
4. Monitor `Authentication-Results` from trusted receivers instead of assuming seeing an added `DKIM-Signature` guarantees verification passes.

### Forwarding and ARC

When emails are forwarded via mailing lists or gateways, SPF may fail at the forwarding IP, and DKIM may break if content is altered. **ARC (Authenticated Received Chain)** lets participating intermediaries record authentication states across hops. However, ARC does not guarantee acceptance and never overrides the receiving server's policy.

Never forge ARC headers in Spring to boost trust; an ARC chain has value only when properly signed and evaluated by participating intermediaries.

## 11. MIME Headers and Gateway Effects on HTML/Attachments

Gateways process MIME headers too, not just `From` and `Subject`.

Example message with two body alternatives and a PDF:

```text
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="outer"

--outer
Content-Type: multipart/alternative; boundary="inner"

--inner
Content-Type: text/plain; charset=UTF-8

Notification: please review the document.
--inner
Content-Type: text/html; charset=UTF-8

<p>Notification: please review the document.</p>
--inner--

--outer
Content-Type: application/pdf; name="guide.pdf"
Content-Disposition: attachment; filename="guide.pdf"
Content-Transfer-Encoding: base64

[base64 data]
--outer--
```

This structure is a conceptual sketch, not a complete MIME message to send verbatim. In application code, let `MimeMessageHelper` build the tree and supply content via `DataSource`/`Resource`.

An email gateway may:

- Scan attachments and block risky file types.
- Rename files or strip attachments per DLP rules.
- Inject warning banners into HTML or plain-text bodies.
- Rewrite links inside HTML for anti-phishing protection.
- Convert encodings or MIME structure during content inspection.

Consequently, when debugging "missing attachments" or "broken HTML," inspect the message **before and after the gateway**—not only your Spring code. If DKIM runs in between, check the signing/transformation order as well.

## 12. The `List-Unsubscribe` Header and Bulk Emails

Promotional emails, newsletters, or list streams normally need clear unsubscribe mechanisms. Common headers:

```text
List-Unsubscribe: <https://example.com/unsubscribe/opaque-token>,
 <mailto:unsubscribe@example.com>
List-Unsubscribe-Post: List-Unsubscribe=One-Click
```

`List-Unsubscribe` lists unsubscribe endpoints; `List-Unsubscribe-Post` with the value above supports RFC 8058 one-click unsubscribe when implemented properly. Check exact syntax, authentication requirements, per-sender rules, and provider behavior in your ESP and mailbox provider docs.

Important considerations:

- **Transactional** and **marketing/bulk** streams obey different rules. Do not apply identical unsubscribe flows to all emails regardless of purpose.
- Some ESPs automatically inject or manage `List-Unsubscribe` via their unsubscribe features; adding duplicates yourself can cause unwanted behavior.
- One-click endpoints must follow the specified HTTP method and contract; do not confuse them with arbitrary webpage links.
- Unsubscribe tokens should be scoped and bounded properly, without exposing raw sensitive data.
- A mailbox client's one-click POST must be idempotent and must not force a user login when the one-click design/protocol authorizes unsubscribing via a valid token.
- Never build an unsubscribe flow that inadvertently toggles subscription back on when link scanners prefetch URLs.

Spring Mail only helps construct and send messages; subscription management, suppression lists, and unsubscribe workflows must live in your application or mail service.

## 13. Message-ID, Provider Message ID, and Correlation ID

One challenge when tracing through gateways is that systems use similarly named identifiers:

```text
Application:
  deliveryId = "f62a4acd-7f44-41ae-9c3f-2460feac42c9"

Raw email header:
  Message-ID: <98765.abc@example.com>

ESP:
  providerMessageId = "esp-msg-100245"

Webhook:
  providerEventId = "evt-20091"
  eventType = "delivered"
```

These IDs do not have to match:

- **Delivery ID**: application-generated identifier for one email to be delivered to a recipient.
- **Message-ID**: Internet message ID header, possibly generated by Jakarta Mail on save/send or rewritten downstream.
- **Provider message ID**: ESP's internal identifier for locating the message in its system.
- **Event ID**: identifier for an event such as accepted, delivered, bounced, opened, or clicked, used to deduplicate webhook processing.

A single multi-recipient email may share one `Message-ID` while having different delivery outcomes per recipient. Therefore, never use `Message-ID` as the sole unique key for all delivery/recipient records.

### Attaching IDs Durably

If your ESP supports custom metadata, store `deliveryId` there; if it only supports custom headers, use a safe header like:

```text
X-App-Delivery-ID: f62a4acd-7f44-41ae-9c3f-2460feac42c9
```

In your database, also persist mappings linking `deliveryId`, provider ID, and attempt ID. Never rely on a custom header surviving intact across every gateway.

To inspect which hops a message traversed, `Received` headers in the mailbox can be helpful, yet **never trust every `Received` line blindly**, because lines below the trusted-system boundary may have been forged by the sender. During investigations, establish where your trusted boundary begins.

## 14. How Providers Handle Malformed or Disallowed Headers

Common real-world examples:

| Symptom | Cause to Investigate | Resolution |
| --- | --- | --- |
| SMTP rejects sender | `From` not on verified address/domain or lacks permission | Verify sender and account settings |
| Mail sends yet `From` is altered | ESP applies sender-rewriting policy | Check policy for sending on behalf of domains |
| User replies go to wrong inbox | Missing or wrong `Reply-To` | Use helper to set the proper address |
| Bounces miss expected inbox | Confusing `Return-Path` header with SMTP `MAIL FROM` | Use provider-supported bounce/envelope sender |
| Provider reports invalid header | Control characters, invalid field name, malformed value | Validate inputs, use typed APIs |
| Corrupted Vietnamese Subject | Incorrect header encoding or charset | Use UTF-8 and `helper.setSubject` |
| Custom header missing in mailbox | ESP/gateway stripped or consumed it as metadata | Check provider policy, persist mappings separately |
| DKIM fails after gateway | Signed headers/body were modified | Run signing after transformations |
| Lands in spam despite accepted | Sender reputation, content, SPF/DKIM/DMARC, receiver policy | Inspect authentication and receiver results |
| Bulk email lacks unsubscribe option | Missing List-Unsubscribe/suppression integration | Configure per email type and provider |
| Bcc exposed | Manually built raw headers or mismanaged recipient list | Use Bcc API / recipient isolation |

A provider may return SMTP `550`, `553`, `554`, or another code depending on context; **never hardcode one SMTP code for all header errors**. Read enhanced status codes, error messages, and provider docs. Email APIs often return HTTP `400`/`422` for invalid inputs, though exact contracts differ across providers.

## 15. Inspecting Headers Before and After Sending

During development, you can inspect a Spring-constructed `MimeMessage`. For example, reading values via the API:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
    new MimeMessageHelper(message, "UTF-8");

helper.setFrom("orders@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Notification");
helper.setText("Content", false);
message.setHeader("X-App-Delivery-ID", "delivery-123");

// Save changes so Jakarta Mail-generated headers are populated.
message.saveChanges();

// Example reading a specific header locally:
String[] values = message.getHeader("X-App-Delivery-ID");
```

This is **local inspection before passing through any provider**. After `send`, downstream systems may add, drop, or rewrite headers. To verify the true delivery path, use a test mailbox or development SMTP capture tool and inspect the actual received raw message where permitted.

For real traffic, avoid printing full headers into production logs: `To`, `Cc`, `Message-ID`, tracking tokens, and custom values may contain sensitive data.

### Data Layers Worth Recording

| Source | Appropriate Data | Limitation |
| --- | --- | --- |
| Spring service | Delivery ID, notification type, sender domain, send time | Cannot see post-gateway changes |
| SMTP submission | Success/failure transmitting to relay | Does not prove mailbox delivery |
| ESP API/webhook | Provider ID, rejected, delivered, bounce, suppression | Follows provider's event definitions |
| Mailbox raw headers | `Received`, `Authentication-Results`, final `From` | Reflects one received copy; verify trust boundary |
| Gateway logs | Modified headers, rule ID, policy decision | Available only if your org has gateway access |

When troubleshooting an incident, join data across layers using your `deliveryId` and `providerMessageId`. For example, if the app set `From` correctly yet the mailbox received another address, SMTP relay/ESP logs and receiver raw headers reveal where rewriting happened.

## 16. Real-World Scenario: Spring Sending Through a Corporate Gateway

Suppose an e-commerce platform must send confirmation emails meeting these requirements:

- Display `From: orders@shop.example.com`.
- Users reply to `help@shop.example.com`.
- Bounces are processed via the ESP.
- Every email carries a `deliveryId` for reconciliation.
- The corporate gateway adds a disclaimer and signs DKIM.
- Recipients may use Gmail, Outlook, or other corporate mail servers.

A sound implementation workflow:

**Step 1 — Verify sender identity.** Configure and verify `shop.example.com` and sending addresses at the ESP; set up SPF/DKIM/DMARC and bounce domains per provider capabilities and guidance.

**Step 2 — Build the email in Spring.** Use `MimeMessageHelper` to set `From`, `To`, `Reply-To`, `Subject`, and body. Attach a safe correlation ID via provider metadata APIs or a supported custom header.

**Step 3 — Finalize content transformations before signing.** If the gateway appends disclaimers, banners, or rewritten links, ensure those edits happen before the DKIM signer computes the final signature.

**Step 4 — Submit via SMTP.** `JavaMailSender.send(...)` hands the message to the relay. Record submission status only, never assuming delivered.

**Step 5 — Handle provider policies.** Monitor errors for unverified senders, reserved headers, header size limits, DLP rules, or attachments. On rejection, fix configuration or content rather than retrying blindly unchanged.

**Step 6 — Reconcile on the receiving side.** When issues occur, inspect raw headers and SPF/DKIM/DMARC results—especially `From`, `Return-Path`, `Message-ID`, `Received`, and `Authentication-Results` at your trust boundary.

**Step 7 — Feed data into dashboards.** Store accepted/delivered/bounce events from the ESP keyed by provider message ID and recipient while keeping internal correlation IDs. Do not require a custom header to survive untouched in the final email for your system to function.

### Core Architectural Principles

- **Message headers differ from the SMTP envelope.** `Reply-To` does not replace the bounce address, and `Return-Path` does not configure `MAIL FROM`.
- **Providers/gateways are part of the final email pipeline.** They may inspect, reject, add, strip, or rewrite headers per policy.
- **Spring helps format valid headers, not bypass provider rules.** `setFrom` and `setHeader` do not grant permission to send from unverified domains.
- **DKIM depends on signing order.** Appending disclaimers or editing subjects after signing can break verification.
- **Treat custom tracing headers as supplementary.** Keep correlation mappings in your database or ESP APIs rather than depending entirely on headers that may be stripped.
- **Trust only traces created inside your trust boundary.** Arbitrary `Received` or `Authentication-Results` headers supplied by a sender prove neither routing nor authentication.

Understanding these rules helps Spring Framework Mail applications send with consistent identity, reduce gateway rejections, preserve authentication across transformations, and maintain reliable end-to-end observability from application to receiving mailbox.
