# Envelope Sender and Bounce Address

## 1. What Is an Envelope Sender and Why Does It Affect Deliverability?

When building email sending functionality with **Spring Framework Mail**, we usually start by calling **MimeMessageHelper.setFrom(...)**, setting **To**, **Subject**, text or HTML content, and then calling **JavaMailSender.send(...)**. However, the **From** address displayed in the email is not necessarily the address the mail system uses to return undeliverable notifications.

SMTP has two layers of information to distinguish:

- **SMTP envelope**: communication data between SMTP servers, including the sender address in the **MAIL FROM** command (also called the **reverse-path**, **envelope sender**) and the recipient addresses in the **RCPT TO** commands.
- **Message headers**: headers inside the email content in message format, including **From**, **Sender**, **Reply-To**, **To**, **Cc**, **Subject**, and other headers.

**Envelope sender** primarily specifies where notifications about delivery failures are sent after the email has been accepted by a server. That address is commonly used as the **bounce address**, helping the system detect nonexistent recipients, full mailboxes, unresponsive receiving domains, or other delivery errors.

Example:

~~~text
Spring application
  |
  | SMTP envelope:
  |   MAIL FROM:<bounce+order-981@bounces.example.com>
  |   RCPT TO:<customer@recipient.example>
  |
  | Email content:
  |   From: Example Shop <notifications@example.com>
  |   Reply-To: support@example.com
  |   To: customer@recipient.example
  |   Subject: Order has been shipped
  v
SMTP provider -> email network -> mailbox
  |
  +-- Success: message continues to be delivered
  |
  +-- Undeliverable:
           |
           v
      Bounce / DSN sent back to
      bounce+order-981@bounces.example.com
~~~

Here, **notifications@example.com** is the address the recipient sees in From, while **bounce+order-981@bounces.example.com** is the technical address in the SMTP envelope.

A reliable mail-sending system does not only care about successfully submitting messages. It also needs to manage the bounce address, asynchronous feedback, and domain authentication factors to maintain recipient list quality.

## 2. Addresses That Are Easy to Confuse

An email message can contain many different types of addresses, each serving its own purpose:

| Component | Where Is It Located? | Role |
|---|---|---|
| **SMTP MAIL FROM** | SMTP envelope | Reverse-path; destination for subsequent delivery failure notifications |
| **SMTP RCPT TO** | SMTP envelope | Recipient to which the SMTP server is asked to deliver |
| **From** | Header in MIME message | Author/sender address displayed by the email client |
| **Sender** | Header in MIME message | Agent sending on behalf of the author, when distinction is needed |
| **Reply-To** | Header in MIME message | Address receiving replies when the user clicks Reply |
| **Return-Path** | Header typically added during delivery | Records the SMTP reverse-path at a delivery point |
| **To / Cc** | Header in MIME message | List of recipients presented in the email |
| **Bcc** | Application/SMTP recipient address, not exposed like To/Cc | Secretly send to additional recipients |

Distinguish three questions:

1. **Who is the displayed sender?** — check the **From** header.
2. **Where will replies go when the recipient clicks Reply?** — check **Reply-To** when present, otherwise usually From.
3. **Where will delivery failure notifications return?** — check **SMTP MAIL FROM** of the sending hop, typically reflected in **Return-Path** of the delivered email.

Do not use Reply-To as a bounce collection mechanism. A mailbox for human replies and a place for automated delivery error handling usually have very different responsibilities.

## 3. SMTP Conversation Example: The Envelope Is Not in the Body

A simplified SMTP session looks like:

~~~smtp
S: 220 smtp.provider.example ESMTP ready
C: EHLO application.example.com
S: 250-smtp.provider.example
S: 250 SIZE 52428800
C: MAIL FROM:<bounce+evt-789@bounces.example.com>
S: 250 2.1.0 Sender OK
C: RCPT TO:<person@recipient.example>
S: 250 2.1.5 Recipient OK
C: DATA
S: 354 End data with <CRLF>.<CRLF>
C: From: Example Shop <notifications@example.com>
C: To: person@recipient.example
C: Reply-To: support@example.com
C: Subject: Order confirmation
C:
C: Your order has been recorded.
C: .
S: 250 2.0.0 Message accepted for delivery
~~~

The snippet above only illustrates the protocol sequence. In real sending, the connection requires TLS and non-ASCII MIME headers must be encoded appropriately. **MAIL FROM** and **RCPT TO** are SMTP commands, not regular header lines inside the DATA content.

A very important point:

**SMTP returning 250 for DATA does not mean the email has been delivered to the Inbox.** That response usually only means the current server has accepted responsibility for further processing. If subsequent hops fail to deliver, an asynchronous failure notification may be sent to the reverse-path.

## 4. Envelope Sender and RFC 5322 From Are Two Different Identities

The name **MAIL FROM** is quite misleading because it looks like the **From** header. However:

- **RFC 5321 MAIL FROM**: belongs to the SMTP protocol and the delivery failure return path. The commonly used term is **RFC5321.MailFrom**.
- **RFC 5322 From**: belongs to the message content and represents the author of the email. The commonly used term is **RFC5322.From**.

Example:

~~~text
RFC5321.MailFrom:
  bounce+abc123@bounces.example.com

RFC5322.From:
  Example Shop <receipts@example.com>

RFC5322.Reply-To:
  customer-care@example.com
~~~

This is a reasonable configuration: users see **Example Shop**, reply to customer care, while delivery failure notifications are processed by the system at a subdomain dedicated to bounces.

Do not ask buyers to reply to **bounce+abc123@...**. Bounce addresses are usually processed by software or by the SMTP provider service, not a mailbox read by staff.

## 5. Return-Path: The Trace of the Envelope Sender

When an email is delivered to a mailbox, you may see headers such as:

~~~text
Return-Path: <bounce+abc123@bounces.example.com>
From: Example Shop <receipts@example.com>
Reply-To: support@example.com
To: customer@recipient.example
~~~

**Return-Path** is a header used to record the message's reverse-path upon delivery according to SMTP rules. Typically, the **mail server at the final delivery stage** adds Return-Path based on the SMTP envelope it receives.

That leads to two consequences:

1. Return-Path can help operators observe the envelope sender of a sending hop, but in systems with relays or forwarding, the visible value may reflect changes along the route.
2. **Manually setting a Return-Path header in MimeMessage is not a reliable way to control SMTP MAIL FROM.** The header may be ignored, replaced, or handled differently by the transport/server.

In Spring Mail, configure the **envelope sender at the SMTP transport/provider layer**. When verifying results, use MAIL FROM information from SMTP/provider logs and Return-Path from the delivered email as cross-check signals.

### Conceptually Incorrect Configuration Example

~~~java
// Do not expect the following call to change SMTP MAIL FROM on its own.
message.setHeader(
        "Return-Path",
        "<bounces@example.com>"
);
~~~

The call above only manipulates the **message header**; it does not guarantee that the SMTP client uses that address in the MAIL FROM command.

## 6. What Is a Bounce?

**Bounce** usually refers to a notification indicating that an email could not be delivered or encountered a problem during delivery. In SMTP systems, standard reports are commonly called **Delivery Status Notification (DSN)**; in practice, email providers may also deliver **bounce events** via API or webhook.

Common cases:

- The recipient address does not exist.
- The recipient's mailbox cannot receive more mail.
- The receiving domain experiences prolonged temporary issues.
- The email is rejected by anti-spam, authentication, or reputation policies.
- The destination server cannot receive the message within the retry window.
- The content or size does not comply with the receiving side's policy.

Bounces help the sender decide whether to continue sending to that recipient, but they are **not a comprehensive delivery confirmation mechanism**. Not receiving a bounce does not prove the message landed in the Inbox; not every receiving system emits DSNs in the same way.

## 7. Asynchronous Bounces Differ from Immediate SMTP Errors When Sending

Suppose Spring calls:

~~~java
mailSender.send(mimeMessage);
~~~

There are at least two outcome groups to distinguish:

### A. SMTP Server Rejects While the Application Is Submitting the Email

~~~text
Spring / SMTP client           Submission server
         |                           |
         | RCPT TO:<bad@example> --->|
         |<------- 550 rejected -----|
         |
    JavaMailSender may throw MailException
~~~

This error happens **within the same sending session**. The application can catch Spring Mail exceptions and analyze the SMTP response or recipient status if the provider supports it.

### B. Server Accepted the Email, but a Later Hop Fails

~~~text
Spring application       Submission server      Receiving server
       |                         |                      |
       | DATA ------------------>|                      |
       |<----- 250 accepted -----|                      |
       |                         | ---- relay --------> |
       |                         | <---- failure -------|
       |                         |                      |
       |     DSN / bounce event  |                      |
       |<------------------------|                      |
~~~

The initial **send(...)** call may have succeeded. Seconds or hours later, a bounce arrives. Therefore, **try/catch MailSendException** cannot be used as the sole solution for collecting bounces.

A deliverability system needs both:

- **Submission result**: the result of the application submitting the message at the first hop.
- **Asynchronous delivery feedback**: DSNs, bounce events, webhooks, or dashboards from the SMTP provider.

## 8. Hard Bounce, Soft Bounce, and Intermediate States

Many ESPs distinguish:

| Common Category | Example | Reference Action |
|---|---|---|
| **Hard bounce** | Recipient does not exist, permanently invalid address | Suppress/do not continue sending to that address until corrected or verified |
| **Soft bounce** | Mailbox full, receiving server temporarily busy | Retry according to a bounded policy |
| **Policy rejection** | Anti-spam, sender reputation, or authentication requirements | Investigate root cause before continuing |
| **Deferred** | Server delays acceptance or delivery | Monitor wait duration and final outcome |
| **Unknown** | Insufficient data to determine status | Keep unknown status; do not infer as delivered |

The terms **hard** and **soft** are operational labels and do not always map one-to-one with SMTP codes:

- 4xx codes usually indicate a temporary error on the current command, but an email may be deferred multiple times and eventually become a permanent failure.
- 5xx codes usually indicate permanent rejection on the current command, but the cause may be policy, capacity, routing, or authentication, not only a nonexistent address.
- A provider may define its own bounce type using metadata and enhanced status codes.

You must use **reliable result sources and each provider's context** to decide suppression or replay. Do not just search for the string "550" in the body and delete the recipient address.

## 9. Why Separate the Bounce Address from From and Reply-To?

There are three different goals:

**User experience.** From should properly represent the brand or service; Reply-To directs responses to a team that can answer.

**Email operations.** Bounces need to be processed automatically by a system that tracks notifications, logs reasons, and updates recipient statuses. Funneling all bounces into the customer support mailbox makes filtering and correlation difficult.

**Security and data.** A bounce address may contain technical tokens or identifiers; it should not be used as a customer communication address. A dedicated domain/subdomain also makes managing DNS and provider permissions easier.

Model:

~~~text
Header From:
    invoices@example.com
    -> brand identity address

Header Reply-To:
    support@example.com
    -> handles human replies

SMTP MAIL FROM:
    bounce+event-42@bounces.example.com
    -> bounce/DSN collection system
~~~

The domain names here are only examples. Actual design also depends on whether the provider supports configuring a custom MAIL FROM or custom bounce domain.

## 10. Configuring the Envelope Sender in Spring Boot

When using Spring Boot with **spring-boot-starter-mail**, Jakarta Mail SMTP transport properties can be passed via **spring.mail.properties**.

Example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

~~~yaml
spring:
  mail:
    host: smtp.provider.example
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      mail:
        smtp:
          auth: true
          from: bounces@bounces.example.com
          starttls:
            enable: true
            required: true
          ssl:
            checkserveridentity: true
          connectiontimeout: 5000
          timeout: 10000
          writetimeout: 10000
~~~

In this Spring Boot configuration:

- **spring.mail.host / port**: the SMTP server the application connects to.
- **spring.mail.username / password**: credentials issued by the provider, which should not be stored directly in source code.
- **spring.mail.properties.mail.smtp.from**: Jakarta Mail's SMTP transport property used to select the **envelope sender** for messages sent using the corresponding session/transport.
- **starttls.enable + starttls.required**: enables and requires TLS upgrade.
- **ssl.checkserveridentity**: verifies the TLS certificate against the hostname.
- **connectiontimeout, timeout, writetimeout**: connection, read, and write timeouts in milliseconds.

When Spring Boot maps nested YAML into mail properties, the key **mail.smtp.from** is the key that needs to be passed down to the transport. Do not confuse it with:

~~~yaml
spring:
  mail:
    from: something@example.com
~~~

The property **spring.mail.from** is not a standard property for setting the SMTP envelope sender in Spring Boot Mail configuration. Similarly, **helper.setFrom(...)** does not have the same meaning as **mail.smtp.from**.

### Distinguishing Values in Code and Configuration

~~~text
MimeMessageHelper.setFrom("orders@example.com")
    -> From header displayed in the message

mail.smtp.from=bounces@bounces.example.com
    -> SMTP MAIL FROM for this transport
~~~

**Important note:** the SMTP provider may validate, restrict, rewrite, or ignore the envelope sender requested by the client. Some ESPs manage MAIL FROM and bounce domains via verified account/domain settings instead of letting the client set them arbitrarily. Therefore, check the provider's documentation, message traces, and the actual MAIL FROM value after submission.

## 11. Sending Email with Clear From and Reply-To

After configuring the envelope sender at the SMTP transport layer, message creation code can keep recipient-appropriate headers intact:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderEmailService {

    private final JavaMailSender mailSender;

    public OrderEmailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderNotice(
            String recipient,
            String orderCode
    ) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                false,
                StandardCharsets.UTF_8.name()
        );

        helper.setFrom("orders@example.com");
        helper.setReplyTo("support@example.com");
        helper.setTo(recipient);
        helper.setSubject("Order update " + orderCode);

        helper.setText(
                "Order " + orderCode + " has been updated.",
                false
        );

        mailSender.send(message);
    }
}
~~~

In the example:

- **orders@example.com** appears in the From header.
- **support@example.com** receives user replies when they click Reply.
- **bounces@bounces.example.com** from the **mail.smtp.from** setting is the reverse-path requested by the transport.
- **recipient** is the recipient determined by business rules.

The example only sends plain text to make the addresses easy to observe. It can be replaced with HTML or **MimeMessageHelper.setText(plainText, htmlText)** without changing the envelope sender principle.

Addresses and hostnames used in the example must be replaced with verified domains/credentials authorized to send in a real environment.

## 12. Manual JavaMailSenderImpl Configuration

In a plain Spring Framework application or when you want to configure the sender manually, you can create a **JavaMailSenderImpl** bean:

~~~java
import java.util.Properties;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class EmailTransportConfiguration {

    @Bean
    public JavaMailSender mailSender(MailAccountProperties config) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();

        sender.setHost(config.smtpHost());
        sender.setPort(587);
        sender.setUsername(config.username());
        sender.setPassword(config.password());
        sender.setDefaultEncoding("UTF-8");

        Properties properties = sender.getJavaMailProperties();
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.from", "bounces@bounces.example.com");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.ssl.checkserveridentity", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "10000");
        properties.put("mail.smtp.writetimeout", "10000");

        return sender;
    }
}
~~~

**MailAccountProperties** is an application abstraction for the host and credentials, not a default Spring class. Credentials should be supplied through protected configuration or a secret manager. Configuring **mail.smtp.from** is a request to send an envelope sender to the SMTP transport, not a guarantee that the provider accepts that address.

### What Happens When mail.smtp.from Is Not Configured?

The Jakarta Mail SMTP transport has an implementation-dependent mechanism to choose MAIL FROM from the message/session and environment. In many configurations, it may use the address in the From header or a local address inferred from the session if no envelope sender is specified.

Do not rely on inferred values if the application needs a **deterministic bounce domain, SPF alignment, or correlation**. Configure it explicitly and verify the result with the SMTP provider.

## 13. Shared Envelope Sender or Per-Notification Envelope Sender?

**mail.smtp.from** is an SMTP transport/session property. If a **JavaMailSenderImpl** is shared, setting this property to a fixed value will cause multiple messages to use the same envelope sender.

Example:

~~~text
One JavaMailSender
  mail.smtp.from = bounces@bounces.example.com

Notification A -> MAIL FROM bounces@bounces.example.com
Notification B -> MAIL FROM bounces@bounces.example.com
Notification C -> MAIL FROM bounces@bounces.example.com
~~~

This approach can be sufficient when the ESP provides webhooks containing a message ID to correlate bounces, or when the bounce mailbox is processed by a parser using available information.

If **each notification needs its own bounce address**, do not dynamically mutate a property of a singleton **JavaMailSenderImpl** right before each send:

~~~java
// Anti-pattern when multiple threads share the same JavaMailSenderImpl.
sender.getJavaMailProperties().put(
        "mail.smtp.from",
        "bounce+" + notificationId + "@bounces.example.com"
);
sender.send(message);
~~~

Two threads can overwrite each other's property and send with another notification's envelope sender. It also makes testing and auditing difficult.

Better options:

1. Use the **per-message envelope sender mechanism of the SMTP provider/transport** if the implementation supports it.
2. Use the **ESP's sending API** with an officially provider-supported return-path/bounce identity or metadata.
3. Use separate **JavaMailSender** instances for domains or streams with fixed envelope senders.
4. If a dedicated sender is needed per job, design an explicit session/transport lifecycle and manage resources rather than sharing an arbitrarily mutable configuration.

Some Jakarta Mail SMTP implementations provide an **SMTPMessage** class or a dedicated API to set the envelope sender per message. This is an **implementation-dependent API**, not a generic method on **MimeMessageHelper** or **JavaMailSender**. Package names and support must be confirmed according to the Jakarta Mail provider in use.

## 14. Bounce Addresses and SPF

**SPF (Sender Policy Framework)** is a mechanism that helps receivers check whether the sending IP/host is authorized by the domain according to the SPF policy.

For regular emails with a non-empty reverse-path, the SPF identity is checked based on the **domain of RFC5321.MailFrom**. When the reverse-path is empty (e.g., DSN), the SPF mechanism may fall back to the HELO/EHLO identity according to SPF rules.

Example:

~~~text
RFC5322.From:
  receipts@example.com

RFC5321.MailFrom:
  bounces@bounces.example.com

Connecting SMTP IP:
  192.0.2.25
~~~

The receiver may check SPF for **bounces.example.com** to determine authorized sending IPs. The address **192.0.2.25** is an IP reserved for documentation examples.

### SPF Must Match the MAIL FROM Domain in Use

If the ESP sends mail with an envelope sender belonging to **bounces.example.com**, ensure that domain's SPF/DNS is configured according to the ESP's instructions. Illustrative SPF TXT record structure:

~~~dns
bounces.example.com. IN TXT "v=spf1 include:_spf.provider.example -all"
~~~

The value **_spf.provider.example** is only a placeholder. Do not copy this TXT record to real DNS without verified instructions from the provider. Some ESPs use CNAME, MX, or dedicated domain configurations; strictly follow the requirements of the system in use.

Note: **SPF pass only speaks to authorization of the checked domain**; it does not by itself guarantee the email passes DMARC or lands in the Inbox.

## 15. Envelope Sender, DKIM, and DMARC Alignment

**DMARC** checks the relationship between the **displayed From** (RFC5322.From) and identities authenticated via SPF and/or DKIM. A message can pass DMARC when at least one of **SPF or DKIM** both passes and has its domain **aligned** with From according to the configured alignment mode.

Example:

~~~text
Header From:
  notifications@example.com

Envelope MAIL FROM:
  bounce+id@bounces.example.com

DKIM signature:
  d=example.com
~~~

In **relaxed alignment** mode, **bounces.example.com** and **example.com** usually share the same organizational domain, so the SPF identity can align with From if SPF passes and other conditions are met. If DMARC is configured for **strict SPF alignment**, two non-identical domains may not align.

DKIM with **d=example.com** can align with **From: notifications@example.com** when the signature is valid. Therefore:

- Do not assume **SPF pass = DMARC pass** in all cases.
- Do not think **Return-Path must have the exact same email address as the From header** to be able to send.
- Do not assume the ESP is signing DKIM with the brand's domain; you must verify the actual **d=**.
- When using multiple brand domains or tenants, inspect alignment per domain.

### Mismatch Example

~~~text
Header From: invoices@example.com
MAIL FROM: bounce@provider-mail.example.net
SPF: pass for provider-mail.example.net
DKIM: signature d=provider-mail.example.net
~~~

If both SPF and DKIM are only authenticated under **provider-mail.example.net** without aligning with **example.com**, DMARC may fail even though the SPF check on the sending IP passed. Solutions may include a **verified custom MAIL FROM domain**, an **aligned DKIM signing domain**, or both depending on ESP policy.

In operations, inspect **Authentication-Results**, **Return-Path**, and **DKIM-Signature** from a delivered test email to understand the actual identities.

## 16. Designing a Dedicated Domain or Subdomain for Bounces

A common architecture is using the main domain for the From header and a subdomain for the reverse-path:

~~~text
Brand:
  example.com

Header From:
  notifications@example.com

Bounce domain:
  bounces.example.com

SMTP MAIL FROM:
  bounce+event123@bounces.example.com
~~~

This organization helps:

- Keep the From address clear for recipients.
- Separate the delivery failure notification stream from the customer support mailbox.
- Configure DNS and ESP permissions specifically for bounces.
- Potentially use a correlation token in the local-part of the envelope sender.
- Maintain SPF alignment capability with the From domain in relaxed DMARC configurations if conditions are met.

However, a new subdomain **does not automatically act as a bounce receiver**. Email/DSN receiving infrastructure or a provider handling it is required.

### Components to Determine Upfront

1. **Does the SMTP provider allow custom MAIL FROM?** Some providers require using a return-path belonging to their own domain.
2. **Does the provider receive bounces on behalf of the application?** If so, there is usually an event webhook/API or dashboard.
3. **Which DNS records need configuration?** This may include SPF TXT, MX, CNAME, or verification records specified by the provider.
4. **How does the system correlate bounces?** Based on provider message ID, notification metadata, or VERP address.
5. **Can the bounce address receive mail?** Passing SPF does not mean the domain has a mailbox to receive DSNs.
6. **Are webhook and log access permissions protected?** Bounce events contain email addresses and delivery information.

Do not add an MX record for a server that has no mail receiving service. Conversely, do not delete the bounce subdomain's MX if the provider requires MX to accept feedback. The exact configuration depends on the service contract in use.

## 17. MX for Bounces and the Difference Between Sending and Receiving

SPF and MX address different needs:

| Component | Role |
|---|---|
| **SPF TXT on MAIL FROM domain** | Allows receivers to verify authorization of the sending IP/host |
| **MX on bounce domain** | Specifies mail servers that can receive mail sent to the bounce domain |
| **DKIM signing domain** | Allows receivers to verify the message signature |
| **ESP webhook** | Delivers bounce/delivery events to the application over an API protocol |

A diagram illustrating when the **application receives DSNs itself via a mailbox**:

~~~text
Outbound:
  Spring -> SMTP provider
      MAIL FROM:<bounce+N100@bounces.example.com>
                   |
                   v
         Mail recipient domain

If DSN is generated:
  Receiving MTA
      |
      | DNS MX lookup: bounces.example.com
      v
  Inbound mail server for bounces.example.com
      |
      v
  DSN parser -> notification N100
~~~

In an **ESP-managed bounce** model, the application may not receive DSNs directly into a mailbox. The ESP receives and processes the event, then sends a webhook or provides an API for the application to fetch results:

~~~text
Spring -> ESP SMTP
            |
            v
       Recipient MTA
            |
         bounce event
            |
            v
          ESP
            |
          webhook
            |
            v
  Application bounce endpoint
~~~

Both models can be useful; choose based on ESP capabilities and operational requirements. Do not deploy an additional inbound SMTP server if the provider already offers an authenticated bounce mechanism sufficient for application needs.

## 18. VERP: Return Addresses That Can Carry Correlation Tokens

**VERP (Variable Envelope Return Path)** is a technique that uses different envelope senders to help identify the email or recipient corresponding to a bounce.

For example, instead of all messages using:

~~~text
bounces@bounces.example.com
~~~

We use:

~~~text
bounce+N100@bounces.example.com
bounce+N101@bounces.example.com
bounce+N102@bounces.example.com
~~~

Where **N100**, **N101**, **N102** are notification IDs or tokens mapped to notifications in the database.

When a bounce arrives at:

~~~text
bounce+N101@bounces.example.com
~~~

the application can look up the corresponding record to identify the related send attempt. That is the principle of VERP; it is not built into **MimeMessageHelper** by default.

### Conditions for VERP to Work

- The SMTP sender or ESP must support a per-message envelope sender or provide an equivalent mechanism.
- The bounce domain/inbound route must accept the generated addresses.
- The parser must extract the token from the **envelope recipient receiving the DSN** or trusted metadata, not just from free-form text.
- You must know which recipient a multi-recipient message is associated with for a given token.
- Tokens must avoid collisions and must not expose sensitive information.

**Plus addressing is not a mechanism that every receiving server supports identically.** If using the **bounce+token@domain** syntax, verify that the inbound server/ESP routes that local-part as required.

### Do Not Put Personal Data in VERP

Avoid:

~~~text
bounce+customer-email-at-gmail.com@bounces.example.com
bounce+phone-0901234567@bounces.example.com
~~~

Such addresses can leak PII in SMTP logs, headers, DSNs, or monitoring systems. Use **random/opaque IDs**, and if token validation is needed, use a signature/HMAC or check record existence along with processing authorization.

## 19. Standard DSN: What Does a Returned Message Look Like?

A MIME-formatted DSN can use the structure:

~~~text
Content-Type: multipart/report;
    report-type=delivery-status
    |
    +-- text/plain
    |      Human-readable explanation
    |
    +-- message/delivery-status
    |      Structured status fields
    |
    +-- message/rfc822-headers or message/rfc822
           Original message information, if present
~~~

In the **message/delivery-status** part, fields like these may appear:

~~~text
Reporting-MTA: dns; mx.receiver.example
Arrival-Date: Thu, 12 Nov 2026 08:00:00 +0000

Final-Recipient: rfc822; customer@recipient.example
Action: failed
Status: 5.1.1
Diagnostic-Code: smtp; 550 5.1.1 User unknown
~~~

This is an illustrative example, not a real report. Some fields are optional or server-dependent.

Useful fields:

| Field | Meaning |
|---|---|
| **Reporting-MTA** | System that generated the status report |
| **Final-Recipient** | Recipient associated with the delivery outcome |
| **Original-Recipient** | Original recipient if reported |
| **Action** | Status such as failed, delayed, delivered, relayed, or expanded |
| **Status** | Enhanced mail system status code |
| **Diagnostic-Code** | Original diagnostic, typically an SMTP response |
| **Original-Envelope-Id** | Envelope identifier if the DSN mechanism passed and reported it back |

Not every bounce contains all fields. Some ESPs convert feedback into proprietary JSON events that carry equivalent meaning without preserving the raw MIME format.

### Do Not Classify by Free-Form Body Text

For example, do not rely solely on:

~~~java
if (bounceText.contains("user unknown")) {
    suppressRecipient();
}
~~~

DSN bodies can vary in language, content, or phrasing, and a spoofed email could also contain that string. Prefer **DSN structures properly understood by a parser**, **reliable status codes**, or **signature-verified ESP events**.

## 20. DSN and Empty Reverse-Path: MAIL FROM:<>

A DSN itself is also an email. If sending a DSN to an undeliverable address triggers another DSN, two mail servers could create an error-reporting loop.

To prevent loops, delivery failure notifications are sent with a **null reverse-path**:

~~~smtp
MAIL FROM:<>
RCPT TO:<bounce+N100@bounces.example.com>
~~~

The **<>** notation here means an empty reverse-path, **not a missing email address due to misconfiguration**. When such a DSN cannot be delivered, the server should not generate another DSN to send to a new reverse-path.

In a delivered DSN email, Return-Path may show:

~~~text
Return-Path: <>
~~~

**Do not configure an empty MAIL FROM for normal transactional emails** just to avoid bounces. Doing so makes error management difficult and violates provider policies. Null reverse-path has a special purpose in error-reporting protocols.

## 21. Bounces When Email Passes Through a Forwarder

A recipient may automatically forward mail from mailbox A to mailbox B. This complicates the delivery path and domain authentication:

~~~text
Spring -> ESP -> Mailbox A -> Forwarder -> Mailbox B
~~~

At the forwarding hop, a system may rewrite the reverse-path using **SRS (Sender Rewriting Scheme)** to support SPF during forwarding. Therefore:

- The envelope sender/Return-Path at a later hop may differ from the value initially set by the application.
- SPF pass at the forwarding hop does not automatically guarantee DMARC SPF alignment with the original From.
- Valid and aligned DKIM can help DMARC survive forwarding, though the signature can break if content/headers are modified.
- A bounce may pass through a forwarder or intermediary system and need to be correlated with the original ID.

Do not assume a given envelope sender address will appear intact at every hop. When debugging, inspect ESP message traces and Received/Authentication-Results headers, not just a single Return-Path field in the final mailbox.

## 22. When Do Bounces Not Reach the Configured Address?

Several cases:

- The provider rewrites MAIL FROM to a managed bounce domain.
- The receiving system rejects the message during the SMTP session before accepting it, so there is no asynchronous DSN.
- A relay hop does not emit a DSN despite a message problem, due to policy or failure.
- The bounce is blocked by anti-spam, quota, or routing of the bounce domain.
- The ESP records the bounce in a dashboard/webhook instead of sending a DSN to the application's mailbox.
- DNS or the mailbox of the bounce subdomain is misconfigured.
- A forwarder/relay altered the reverse-path.
- The recipient mailbox files the message into Spam or quarantine without generating a bounce.

Therefore, to know whether the bounce address actually works, you must **test through a controlled end-to-end send/receive flow**, not merely inspect properties in Spring.

## 23. Building Storage Data for Notifications and Bounces

A deliverability tracking system can store the following key fields:

| Field | Purpose |
|---|---|
| **notification_id** | Application's notification identifier |
| **business_event_id** | Business event that generated the notification |
| **recipient_id / recipient_ref** | Recipient reference |
| **recipient_email** | Actual email if needed and permitted to store |
| **header_from** | Displayed From that was used |
| **envelope_from_requested** | MAIL FROM requested by the application |
| **envelope_from_actual** | Actual MAIL FROM if provided by the provider |
| **provider_message_id** | ID issued by the ESP to link events |
| **message_id** | Message-ID header if present |
| **submission_status** | PENDING, SUBMITTED, RETRY, UNKNOWN... |
| **delivery_status** | DELIVERED, BOUNCED, DEFERRED, UNKNOWN... |
| **bounce_type / reason_code** | Normalized bounce category |
| **smtp_status_code** | SMTP diagnostic / enhanced status code |
| **attempt_count** | Number of processing/sending attempts |
| **last_event_at** | Timestamp of the latest event |

In many cases where **envelope_from_actual** is unknown, store **null/unknown** instead of copying the requested value and treating it as truth.

### One Notification Can Have Multiple Events

~~~text
Notification N100
   |
   +-- 09:00 Submitted
   +-- 09:01 Deferred
   +-- 09:04 Deferred
   +-- 09:09 Delivered
~~~

Or:

~~~text
Notification N101
   |
   +-- 09:00 Submitted
   +-- 09:08 Bounced (hard)
~~~

Do not derive the final status by simply taking the first event and ignoring subsequent ones. Ordering, event type, and provider policies must be handled.

## 24. Handling Bounce Events via ESP Webhooks

If the provider supports webhooks for bounces/delivery, the application can split into two components:

~~~text
                    SMTP submission
Spring mail worker ------------------------> ESP
      |                                       |
      | save notificationId, providerId       |
      v                                       |
Notification database                        |
                                              |
                                     Delivery / Bounce
                                              |
                                              v
                                      Webhook HTTPS
                                              |
                                              v
                                  Validate signature / source
                                              |
                                              v
                                    Persist provider event
                                              |
                                              v
                                  Resolve notification/recipient
                                              |
                                              v
                                  Update delivery + suppression
~~~

**A webhook is input from an external system**; do not trust its contents simply because a request hits the right URL. When implementing, you need to:

1. **Verify the sender source** using the method published by the ESP: signature, HMAC, authentication mechanism, or mTLS if supported.
2. Verify against the **raw request body** if required by the provider's signature, before transforming JSON.
3. Check timestamp/nonce or replay limits when the provider offers a corresponding mechanism.
4. Validate the event ID and event type.
5. Correlate the provider message ID with an existing notification while confirming the recipient.
6. Persist the event durably before returning HTTP success if the application requires zero event loss.
7. Handle duplicates and out-of-order delivery.
8. Do not add addresses from unverified payloads to the suppression list.

### Spring MVC Skeleton for Webhooks

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MailDeliveryWebhookController {

    private final MailWebhookSignatureVerifier verifier;
    private final MailDeliveryEventInbox inbox;

    public MailDeliveryWebhookController(
            MailWebhookSignatureVerifier verifier,
            MailDeliveryEventInbox inbox
    ) {
        this.verifier = verifier;
        this.inbox = inbox;
    }

    @PostMapping(
            path = "/webhooks/mail/delivery",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<Void> receive(
            @RequestHeader HttpHeaders headers,
            @RequestBody byte[] rawBody
    ) {
        if (!verifier.isValid(headers, rawBody)) {
            return ResponseEntity
                    .status(HttpStatus.UNAUTHORIZED)
                    .build();
        }

        // Persist event idempotently before acknowledging.
        inbox.persistIfNew(rawBody);

        return ResponseEntity.accepted().build();
    }
}
~~~

This is an **architectural skeleton**, not an endpoint already integrated with a specific ESP:

- **MailWebhookSignatureVerifier** must implement the exact signing/verification scheme of the provider in use.
- **MailDeliveryEventInbox.persistIfNew(...)** must parse/validate the payload against the official schema, persist in a durable transaction, and enforce a unique constraint on the provider event ID.
- The endpoint needs request size limits, rate limiting, and web-layer security controls.
- Do not write the raw body to logs.
- Return 2xx once the event is safely persisted per the webhook contract; if persistence fails, rely on the provider's retry mechanism.

Do not use any arbitrary webhook endpoint as a source of truth for bounce status without verifying the provider and the corresponding notification.

## 25. Idempotency and Event Ordering When Receiving Bounces

Webhooks often resend events when they do not receive an HTTP success, on network errors, or when the ESP retries. Thus an event can arrive multiple times.

Example:

~~~text
Provider event E456 (BOUNCED)
         |
         +--> Request #1 -> timeout on provider side
         |
         +--> Request #2 -> same event E456
~~~

The application should record **event E456 once** at the inbox layer:

~~~sql
CREATE TABLE mail_provider_event (
    provider_event_id VARCHAR(200) PRIMARY KEY,
    provider_message_id VARCHAR(200),
    event_type VARCHAR(50) NOT NULL,
    received_at TIMESTAMP NOT NULL,
    processed_at TIMESTAMP
);
~~~

This DDL is illustrative only. In multi-ESP systems you may need a composite key **provider + provider_event_id**, partitioning by tenant, and controlled payload storage for investigation.

If there is no stable event ID, use a provider-supported deduplication strategy or appropriate business key; do not infer on your own that two events with the same type/timestamp are identical.

### Avoiding State Overwrites from Out-of-Order Events

~~~text
09:00 SUBMITTED
09:10 BOUNCED
09:11 Late-arriving DELIVERED webhook from an older event
~~~

You cannot simply treat the latest-arriving webhook as the latest status without checking event time, event type, and provider semantics. You may need to:

- Store an immutable event history.
- Map events to valid state transitions.
- Use provider sequences or meaningful timestamps when supplied.
- Hold statuses that require reconciliation when results conflict.

Do not assume every provider sends webhooks in order of occurrence or delivers them only once.

## 26. Classifying Bounces to Decide Suppression

A **suppression list** is a list of addresses or recipients to which sending should not continue under one or more policies. The goal is to reduce sends to invalid addresses, protect reputation, and avoid bothering recipients.

An example policy:

| Situation | Suggested Action |
|---|---|
| Confirmed user unknown, permanent error | Suppress address until corrected/re-verified |
| Mailbox temporarily full | Retry or defer with a limit |
| Receiving domain temporarily unreachable | Backoff, monitor |
| Provider temporarily rejects due to rate limit | Throttle rate; do not automatically suppress recipient |
| Provider rejects due to SPF/DKIM/DMARC | Fix domain authentication; do not treat all recipients as nonexistent |
| Verified spam complaint | Handle per complaint/consent policy; may suppress |
| Valid user unsubscribe | Handle consent/marketing; do not conflate with hard bounce |
| Bounce without clear evidence | Reconcile; do not automatically mark as hard bounce |

A 5xx error due to **policy rejection** from a receiving domain is not proof that every mailbox at that domain does not exist. Disabling all recipients because of an SPF misconfiguration will cause the application to lose valid recipients.

### Suppression by Address and by Email Type

Example:

~~~text
recipientId = R123
email = person@recipient.example

suppression:
  reason = HARD_BOUNCE
  scope = EMAIL_ADDRESS
  createdAt = ...
~~~

Depending on policy, suppression may apply system-wide, per tenant, per stream, or per notification type. Distinguish **business-mandatory transactional emails** from **consent-based marketing emails**, and do not arbitrarily bypass legal requirements based on a single unverified event.

If a user updates their email and verifies the new address, do not keep the old address's suppression and blindly apply it to the new address.

## 27. Preventing Backscatter and Spoofed Bounces

**Backscatter** occurs when a mail system sends failure notifications to an address that was spoofed as the envelope sender of the original message. Attackers can exploit this to flood innocent people with unrelated bounces.

If the application has a public bounce mailbox:

- Do not trust every message arriving at the mailbox as a valid bounce of the application itself.
- Do not update suppression solely from the bounce's From address.
- Correlate notification ID, provider ID, and recipient.
- Validate standard DSN format when present; still treat received data as untrusted.
- Avoid generating another bounce when handling malformed DSNs.
- Apply rate limits, filtering, and retention.
- Do not automatically send a "bounce rejected" email to any address contained in the notification.

Even with VERP, tokens in addresses can be observed or forged if designed predictably. Use opaque tokens and verify correlation against issued records.

If using ESP webhooks, enforce signature verification and replay protection properly. Do not treat a webhook as trustworthy simply because a request has a header named after the provider.

## 28. Protecting Personal Data in Bounces

A DSN can contain:

- Recipient email.
- Headers of the original email.
- Part or all of the original email content, depending on the mail server.
- Message-ID, transaction ID, or URLs in the content.
- Diagnostic strings from the receiving system.

Therefore, the bounce handling system needs to:

- Minimize storing raw DSNs when unnecessary.
- Apply appropriate access permissions and retention periods.
- Mask/encrypt PII in logs.
- Do not log password reset tokens, OTPs, invoice contents, or paths containing secrets.
- Do not display verbatim external Diagnostic-Code in uncontrolled admin UIs.
- Only log fields needed for deliverability processing and tracing.
- Protect tables containing suppression/recipient history.

Bounces are external data entering the application. Parsers must enforce size limits, avoid unnecessary attachment processing, and guard against issues from complex or malicious MIME content.

## 29. Verifying the Actual Envelope Sender After Sending

Configuring **mail.smtp.from** only indicates which address the application **requests** to use. To confirm that the provider actually used that address, check sources with appropriate reliability.

### Method 1: Inspect the SMTP Trace at the Submission Hop

If the provider and test environment allow observing the SMTP session, confirm the command:

~~~smtp
MAIL FROM:<bounces@bounces.example.com>
~~~

That is direct evidence that the client requested this reverse-path at the observed hop. It does not confirm that the server will preserve it when relaying through another hop.

Do not enable SMTP debug in production just to read the address if the logging system could expose AUTH or sensitive information. Prefer an SMTP test server or the ESP's trace tools.

### Method 2: Inspect Return-Path of a Delivered Message

Send a test email to a mailbox controlled by the operations team, then inspect the raw headers:

~~~text
Return-Path: <bounces@bounces.example.com>
From: Example Shop <notifications@example.com>
Reply-To: support@example.com
~~~

If Return-Path differs from the configuration, check whether the provider rewrote the envelope sender, whether there is an intermediate forwarder, and whether the server has verified the custom MAIL FROM. Return-Path can be affected by the forwarding route, so it is an observational signal, not a replacement for the provider's message trace.

### Method 3: Inspect Authentication-Results

A received email may contain information such as:

~~~text
Authentication-Results: mx.receiver.example;
  spf=pass smtp.mailfrom=bounces.example.com;
  dkim=pass header.d=example.com;
  dmarc=pass header.from=example.com
~~~

This is an illustrative example. Each receiving system may format headers differently, and headers supplied by external servers should not be treated as immutable proof without knowing the trust boundary.

This information helps check:

- The actual domain used in SPF.
- The DKIM signing domain.
- DMARC alignment with From.

### Method 4: Use the Provider Dashboard/API

If the ESP supports custom return-path, bounce domains, or message traces, cross-check:

- Verified domain.
- DNS validation status.
- The envelope sender the provider reports using.
- Provider message ID and bounce routing.
- SPF/DKIM/DMARC results.

Some providers only allow a bounce address pattern they manage; in that case, use official events/webhooks rather than trying to set arbitrary MAIL FROM values in Spring.

## 30. Testing the Bounce Flow in a Controlled Environment

To validate both the sending path and the feedback path, testing must go beyond mocking **JavaMailSender**.

| Scenario | What to Verify |
|---|---|
| Successful send via SMTP sandbox | Correct From/Reply-To headers; SMTP MAIL FROM matches configuration |
| Custom MAIL FROM disallowed by provider | Error occurs or envelope sender is rewritten; system records it properly |
| Recipient rejected immediately at RCPT TO | Synchronous error is classified; do not wait for a nonexistent bounce |
| Provider accepts DATA then delivery fails | Asynchronous bounce/DSN is correlated with the notification |
| Duplicate bounce event sent | Same event ID is not processed twice |
| Bounce events arrive out of order | Delivery status is not arbitrarily overwritten |
| Spoofed/invalid bounce event | Suppression or recipient is not updated |
| Confirmed hard bounce | Recipient is suppressed according to policy |
| Temporary deferral | Not automatically suppressed permanently |
| User changes email and re-verifies | Old suppression is not wrongly applied to the new email |
| Notification has multiple recipients | One recipient's result is not assigned to another recipient |
| ESP webhook loses connection | Provider can retry; application handles idempotently |

### How to Generate Test Failures

Prefer **SMTP sandboxes, test servers, or simulator addresses published by the provider**. Addresses like **invalid@recipient.example** in documentation are purely illustrative and do not guarantee any mail system will produce the desired bounce.

Do not send bulk emails to strangers' addresses to "test hard bounces." Doing so can harm reputation, be flagged as spam, or violate ESP policies.

### Testing at the Java Level

**Unit tests** can:

- Verify that the service calls **MimeMessageHelper.setFrom(...)** and sets Reply-To properly.
- Verify that the renderer does not use the bounce address as From.
- Check policy mapping from bounce codes to retry/suppression.
- Check that the webhook signature verifier is called before processing events.
- Check that one event ID does not update the database twice.

However, **mocking JavaMailSender does not open an SMTP session** and thus does not prove the actual **MAIL FROM**. That part requires integration tests with an SMTP test server or provider sandbox capable of observing the envelope.

## 31. Common Mistakes

| Mistake | Consequence | Improvement |
|---|---|---|
| Using helper.setFrom to configure bounces | Only changes From header; MAIL FROM may differ | Use mail.smtp.from property or ESP configuration |
| Setting Return-Path header manually | Does not guarantee changing SMTP envelope | Observe actual MAIL FROM and let the MTA handle Return-Path |
| Using Reply-To as the bounce address | Mixes human replies with DSNs | Separate Reply-To and bounce routing |
| Using an envelope sender assuming provider always keeps it | Bounces do not go where expected | Verify custom MAIL FROM and message traces |
| Changing mail.smtp.from without configuring DNS | SPF/bounce routing may fail | Set up domain, DNS, and inbound per ESP requirements |
| Mutating MAIL FROM property on singleton sender across threads | Race condition, sending with wrong reverse-path | Use official per-message support or separate senders |
| Assuming SPF pass is enough for DMARC | May not align with From header | Check DMARC SPF/DKIM alignment |
| Assuming mail.smtp.from must match From header | Unnecessary design restriction | Use an appropriate bounce subdomain and verify the domain |
| Treating SMTP 250 as delivered | Misreports recipient status | Separate SUBMITTED from delivery feedback |
| Assuming catching MailSendException catches all bounces | Misses failures occurring after submission | Collect asynchronous DSNs or webhooks |
| Retrying the entire batch on a single failure | Successful recipients may receive duplicates | Track per notification/recipient |
| Parsing only DSN body text to suppress | Error-prone and exploitable | Parse structured fields, authenticate source |
| Trusting every webhook as a valid bounce | Attackers can suppress recipients | Verify signature, event ID, and notification |
| Treating every SMTP 5xx as nonexistent recipient | False suppression due to policy/authentication | Classify by phase, enhanced status, and provider |
| Using email/phone directly in VERP | Exposes personal data in headers/logs | Use opaque tokens |
| Equating null MAIL FROM with missing config | Easy to misunderstand DSNs and cause loops | Recognize MAIL FROM:<> as a special case |

## 32. Runbook for Troubleshooting Missing Bounces

When an email is rejected by the receiving side but the system sees no bounce, investigate systematically:

1. **Identify the original notification** using notification ID, provider message ID, and recipient.
2. **Check submission result:** did the server actually return 250 after DATA, or did the error happen during the sending session?
3. **Check the requested envelope sender** via mail.smtp.from or ESP configuration.
4. **Check the actual envelope sender** via provider trace and Return-Path of a test email.
5. **Identify where bounces are received:** mailbox/DSN parser or ESP event webhook.
6. **Check bounce domain DNS** per provider instructions, including SPF, MX/CNAME, and related records.
7. **Check the inbound route:** are DSNs received, or is the mail server/ESP holding or filtering events?
8. **Check the webhook:** is the signature valid, is the event persisted, does the HTTP response match the retry contract?
9. **Verify correlation:** do provider message ID, recipient, and VERP token match the record?
10. **Check final status:** was it overwritten by out-of-order events or suppression logic?
11. **Consider missing reports:** not every failure produces a bounce observable by the application.
12. **Add metrics/alerts** for bounce ingestion failures rather than only tracking send success rate.

A bounce issue does not necessarily lie in JavaMailSender code. The SMTP provider may have rewritten the reverse-path, inbound DNS may be misconfigured, or the webhook may not be receiving events.

## 33. Monitoring Deliverability Quality

Beyond successful **send(...)** calls, track these metrics:

| Metric | Meaning |
|---|---|
| **mail_submitted_total** | Number of submissions accepted by SMTP/provider |
| **mail_bounce_total** | Number of verified bounce events |
| **mail_hard_bounce_total** | Number of bounces classified as permanent |
| **mail_soft_bounce_total** | Number of bounces classified as temporary |
| **mail_deferred_total** | Number of deferred deliveries |
| **mail_suppressed_recipient_count** | Number of recipients currently suppressed |
| **mail_webhook_invalid_signature_total** | Number of webhooks rejected due to authentication |
| **mail_delivery_event_lag** | Latency from submission to event receipt |
| **mail_bounce_unmatched_total** | Number of bounces not correlated to a notification |
| **mail_unknown_delivery_count** | Number of notifications with unknown outcome |

### Bounce Rate

A reference reporting formula:

~~~text
Bounce rate = number of bounced notifications / number of submitted notifications
~~~

Clearly define the **counting unit, observation window, and denominator**. One notification with multiple defer/bounce events should not be counted as multiple bounced notifications if the goal is to report notification rate. In addition, bounce events may arrive later than the submission window, so comparing two different intervals without accounting for lag can be misleading.

Break down by:

- SMTP provider and sender account.
- Domains of the From header and envelope MAIL FROM.
- Email type: transactional, marketing, system notification.
- Recipient domain at an appropriate aggregate level.
- Time, environment, and error code patterns.

Do not record high-cardinality labels like individual email addresses in metrics. Use notification IDs in protected logs/tracing when per-record investigation is needed.

## 34. Frequently Asked Questions

### Must the envelope sender match From?

No. **MAIL FROM** is the SMTP reverse-path, while **From** is the displayed author in the header. However, their domains affect **SPF/DMARC alignment**, ESP policies, and sending reputation. Different addresses are normal when properly configured and authenticated.

### If Reply-To is set to bounces@example.com, will bounces go there?

Do not assume that. **Reply-To** instructs email clients where to send user replies; **bounce/DSN** typically uses the SMTP envelope sender and server/provider mechanisms.

### Can I set Return-Path directly in MimeMessage?

You can manipulate the header as a string, but that is **not the standard mechanism for controlling SMTP MAIL FROM**. Use transport configuration like **mail.smtp.from** or the ESP's custom MAIL FROM support.

### When is VERP needed?

VERP is useful if the application needs to know which notification/recipient a bounce belongs to and the inbound system can handle per-send addresses. If the ESP already provides a provider message ID and reliable webhooks, the application may not need to build VERP itself.

### Does SPF pass guarantee DMARC pass?

No. SPF must pass and the **SPF domain** must align with the From header per DMARC policy to contribute to a DMARC pass. A passing and aligned DKIM signature can also satisfy DMARC.

### If JavaMailSender.send does not throw an exception, do I still need to listen for bounces?

Yes, if the business needs to know delivery outcomes and maintain a valid recipient list. **A successful send(...) does not mean the email reached the mailbox**.

### Why does a DSN have Return-Path: <>?

That is a **null reverse-path**, preventing error notifications from triggering an infinite chain of error notifications when the DSN itself cannot be delivered.

## 35. Key Takeaways

**Envelope sender** is the **MAIL FROM** address in the SMTP envelope, whereas **From**, **Sender**, and **Reply-To** are headers serving specific meanings in the email content. When an email cannot be delivered after being accepted by an MTA, **bounces/DSNs** are typically sent along the reverse-path. **Return-Path** is the trace of the reverse-path recorded into the email upon delivery, not a header the application should set manually to control the envelope.

In Spring Framework Mail, you can request an envelope sender via the **mail.smtp.from** property on the Jakarta Mail SMTP transport, or use custom MAIL FROM/return-path mechanisms supported by the ESP. **MimeMessageHelper.setFrom(...)** only sets the From header. In multithreaded systems, do not dynamically mutate mail.smtp.from on a singleton sender to create per-notification bounce addresses.

For better deliverability, verify the **bounce domain and DNS**, check **SPF/DKIM/DMARC alignment**, choose a verified DSN or webhook ingestion approach, correlate events by notification/recipient, and handle suppression carefully. Separate synchronous SMTP errors from asynchronous bounces; do not infer delivery solely from send(...) results, nor automatically suppress all recipients over a single 5xx response.

**Core principle: From is the displayed identity, Reply-To serves human replies, and MAIL FROM is the return path for delivery errors.** Configuring, verifying, and monitoring all three forms the foundation of a reliable email-sending system.




