# Reply-To, Return-Path, and Actual Recipient Addresses

In email architecture, **the address the reader sees**, **the address they reply to**, and **the address servers use to handle bounced messages** can all be completely different. A message also has a recipient list at the SMTP protocol layer that does not necessarily match the addresses displayed in **To** or **Cc**.

When building mail-sending functionality with **Spring Framework Mail**, distinguishing these addresses prevents subtle bugs: users replying to an unmonitored mailbox, delivery failure notices going to the wrong place, hidden recipients being exposed, or the application assuming an email reached the right person merely because **To** contained a valid address.

This lesson focuses on three concepts:

1. **Reply-To**: suggests where mail should go **when a human chooses to reply**.
2. **Return-Path**: a trace of the **envelope sender** used for delivery failure notices; usually added by the receiving server at final delivery.
3. **Actual recipients**: destinations processed by SMTP via **RCPT TO** and subsequent relays, which can differ from addresses in **To/Cc/Bcc** headers.

To understand them properly, first separate **email content** from the **SMTP envelope**.

## 1. An Email Has Two Layers of Addresses

When mailing a paper letter, we separate the letter written inside from the address written on the envelope. Email has a similar separation:

- **Message headers** are part of the message in email format (RFC 5322), such as **From**, **To**, **Cc**, **Reply-To**, and **Subject**.
- **SMTP envelope** is information exchanged by SMTP parties to transfer mail, notably **MAIL FROM** and one or more **RCPT TO** commands (RFC 5321).

~~~text
Spring Application
   |
   |  Build MIME message
   |  From: notifications@example.test
   |  Reply-To: support@example.test
   |  To: lan@customer.test
   |
   v
SMTP client (Jakarta Mail)
   |
   |  MAIL FROM:<bounce@bounces.example.test>
   |  RCPT TO:<lan@customer.test>
   |  DATA: [headers + MIME body]
   |
   v
SMTP server / email provider
   |
   |  Forward, route, expand aliases if any
   v
Receiving server and destination mailbox
   |
   |  May prepend Return-Path from envelope sender
   v
Reader views From / To and clicks Reply or Reply All
~~~

**Addresses inside headers do not directly govern SMTP routing.** Rather, **RCPT TO** commands specify the destination addresses proposed for that SMTP transfer. Conversely, the SMTP envelope is usually not shown intact in mail-reading UIs because it serves the delivery infrastructure.

### Common Fields and Roles

| Component | Where It Lives | Primary Purpose |
| --- | --- | --- |
| **From** | Email header | Author/sender identity visible to the reader |
| **Sender** | Email header, when needed | Agent transmitting on behalf of the author in certain situations |
| **Reply-To** | Email header | Address mail clients should use when the reader replies |
| **To** | Email header | Publicly presented primary recipient list |
| **Cc** | Email header | Publicly presented copy recipient list |
| **Bcc** | Recipient info during compose/send | Blind copy recipient list; must be kept secret from other recipients |
| **MAIL FROM** | SMTP envelope | Return address (reverse-path), used for delivery failure reporting |
| **RCPT TO** | SMTP envelope | Recipient address proposed by the SMTP client for that transfer |
| **Return-Path** | Header usually added at delivery | Record of the envelope's reverse-path when the message reaches final delivery |

The name **From** can easily mislead: the **From header** answers "who does this email appear to be from?", whereas **SMTP MAIL FROM** answers "if a nondelivery notice arises, which address should receive it?" They can legitimately differ.

## 2. Reply-To: Where Readers Send Replies

The **Reply-To** header indicates the address mail software should direct a regular reply toward. Example:

~~~text
From: "Learning Platform" <notifications@example.test>
Reply-To: "Support Team" <support@example.test>
To: "Lan" <lan@customer.test>
Subject: Course registration confirmation
~~~

Readers see the email from **notifications@example.test**, yet when clicking **Reply**, their mail client typically places **support@example.test** in the reply recipient field. This lets **notifications@** be dedicated to automated alerts while **support@** receives user questions.

Without **Reply-To**, mail clients usually default to **From** as the reply address. However, final behavior is determined by the email client and user actions: readers can still edit the address, choose **Reply All**, or forward.

### Reply, Reply All, and Forward Are Not the Same

**Reply** typically responds to **Reply-To**, or **From** if no Reply-To exists. **Reply All** may add addresses from **To** and **Cc** depending on client behavior, removing the replier's own address and applying other rules. **Forward** creates a new message sent by the user to addresses they choose, not necessarily related to Reply-To.

**Reply-To is not the address for receiving bounce notices.** An email that fails during delivery is handled via SMTP/DSN mechanics and the envelope sender, not automatically sent to Reply-To simply because that header exists.

### Reply-To Can Be a Mailbox, Group, or Support Workflow

Examples:

- **support@example.test** for customer inquiries.
- **ticket-582@example.test** if a help desk routes replies by ticket ID.
- **sales@example.test** for quotes, scheduling, or consultations.
- **replies@example.test** for a monitored and auto-triaged mailbox.

The Reply-To address must actually receive and handle emails. Setting Reply-To to a nonexistent mailbox misleads users into thinking they can reply while messages go unhandled. For "no-reply" emails, communicate support instructions clearly in the body instead of merely putting a **no-reply@** address and assuming all replies are unimportant.

## 3. Return-Path: Trace of the Bounce-Receiving Address

**Return-Path** is a header used to record the SMTP envelope's **reverse-path** where the message is delivered to the destination mailbox. In normal sending, the reverse-path originates from:

~~~text
MAIL FROM:<bounce@bounces.example.test>
~~~

If the message cannot be delivered, systems may generate a **Delivery Status Notification (DSN)**, or **bounce**, and send the error notice to the appropriate reverse-path. This is an infrastructure mechanism, separate from human "Reply" actions.

For example, after a receiving server delivers the message, the raw message viewed by the recipient may start with:

~~~text
Return-Path: <bounce@bounces.example.test>
Received: from ... by ...
From: "Learning Platform" <notifications@example.test>
Reply-To: <support@example.test>
To: <lan@customer.test>
Subject: Course registration confirmation
~~~

Here there are **three addresses with three purposes**:

- **notifications@example.test**: sender presented to the reader.
- **support@example.test**: where the reader is directed when replying.
- **bounce@bounces.example.test**: where infrastructure sends nondelivery notices when using that reverse-path.

### Return-Path Is Not a Field to Hardcode Manually to Control SMTP

A common mistake is manually adding:

~~~text
Return-Path: <another-bounce@example.test>
~~~

into a MIME message and thinking servers will send bounces to that address. **The Return-Path header and SMTP MAIL FROM are not equivalent in how they are configured**: setting the header manually is not guaranteed to alter the envelope sender. Receiving servers may strip, overwrite, or insert Return-Path themselves based on the actual transport path.

To control the bounce-receiving address, configure the **envelope sender** using mechanisms supported by the SMTP client or email service. On some services, this is a **custom MAIL FROM domain**, **bounce domain**, or **return-path domain** setting; providers may also rewrite the envelope sender to manage bounces.

### What Happens If the Reverse-Path Is Empty?

For system-generated delivery failure notices, SMTP often uses a **null reverse-path**:

~~~text
MAIL FROM:<>
~~~

Leaving the return path empty prevents a bounce message from triggering yet another bounce if undeliverable, avoiding error loops. When such a message is delivered to a mailbox, you may see **Return-Path: <>**. This is normal protocol behavior, not a sign that a programmer forgot to set an address.

## 4. Actual Recipient Addresses: RCPT TO and Routing

The **To** header primarily describes **displayed recipients**. Yet SMTP decides whom to deliver to via individual **RCPT TO** commands. Example:

~~~text
MAIL FROM:<bounce@bounces.example.test>
RCPT TO:<lan@customer.test>
RCPT TO:<archive@internal.test>
DATA
From: "Learning Platform" <notifications@example.test>
Reply-To: <support@example.test>
To: "Lan" <lan@customer.test>
Subject: Course registration confirmation

Hello Lan, ...
.
~~~

This is a simplified SMTP session for illustration. Server responses, TLS, authentication, MIME encoding, and other control commands are omitted.

The message can be sent to **two envelope recipients**, even though the **To** header only contains **lan@customer.test**. The address **archive@internal.test** might come from a **Bcc** setting in the application and not appear in the headers Lan receives. Not seeing an address in the To field does not prove that address never received the message.

### How Do To, Cc, and Bcc Relate to the Envelope?

When an application uses Jakarta Mail or Spring Mail to send a MIME message to **To**, **Cc**, and **Bcc** addresses, the sending layer typically gathers the recipient list to issue corresponding **RCPT TO** commands. The **To/Cc** portion is kept as visible headers. **Bcc** is hidden recipient information that must be handled so it is not disclosed to other recipients.

| Case | What Does the Reader See? | Addresses SMTP May Process |
| --- | --- | --- |
| **To: lan@customer.test** | Lan appears in To | lan@customer.test |
| Add **Cc: minh@customer.test** | Lan and Minh see To/Cc addresses | Lan and Minh |
| Add **Bcc: audit@internal.test** | Lan and Minh must not see audit in their copies | Lan, Minh, and audit |
| Send to a **mailing list** | To may show only the group address | List server may expand to many members |
| Send to an **alias** | To may still show the original alias | Server may map to another mailbox |
| Message is auto-**forwarded** | Original To may remain unchanged | Message travels onward to a new destination |

**Bcc is a recipient-hiding feature of message formatting and sending, not an absolute security guarantee.** Use proper APIs and verify how your sending system generates copies for Bcc. If a task requires every recipient to remain completely unaware of others, sending **separate messages to each person** is usually easier to control.

### Does "RCPT TO Succeeded" Mean the Message Is in the Inbox?

No. Each SMTP server can accept, reject, or temporarily defer a recipient, then route further according to aliases, forwarding rules, or internal policies. Even with a success reply upon submission, spam filtering, final address checks, and mailbox delivery can still occur downstream.

A batch sent to multiple recipients can have **partial** outcomes depending on responses and SMTP client/provider policies. Do not infer every person's status solely from a generic "email sent" label.

## 5. Tracing an Email from Spring to the Mailbox

Suppose a consultation booking notification system sends:

~~~text
From:        notifications@study.example.test
Reply-To:    consultant@study.example.test
To:          customer@recipient.test
Bcc:         audit@study.example.test
Envelope:    bounce+booking-782@bounces.study.example.test
~~~

The application builds a MIME message with **From**, **Reply-To**, **To**, and **Bcc**. The SMTP client runs a session with **MAIL FROM** set to the bounce address and **RCPT TO** commands for both customer and audit. Accepting servers process each address, possibly routing customer through multiple intermediate steps before reaching the mailbox.

After delivery:

1. **The customer opens the email** and sees sender **notifications@...**, without necessarily seeing the envelope address.
2. **The customer clicks Reply**: the mail client usually sets **consultant@...** as the reply target per Reply-To.
3. **Delivery to the customer fails**: infrastructure may send a DSN to **bounce+booking-782@...** if bounce generation policies allow.
4. **The audit department** also receives the message because their address was used as an **envelope recipient**, despite not being publicly listed in To/Cc of the customer's copy.
5. **If customer@... is an alias**, the actual receiving mailbox may have a different address; the original email may still show **To: customer@recipient.test**.

The key point is that **one message carries multiple address identities, each answering a different question**. When trouble occurs, identify whether you are tracing user replies, bounce notifications, or delivery routing.

## 6. Setting From, Reply-To, and Recipients in Spring Framework Mail

Spring provides the **JavaMailSender** interface and **MimeMessageHelper** class to set common headers:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class BookingMailService {

    private final JavaMailSender mailSender;

    public BookingMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmation(String recipient) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                false,
                "UTF-8"
        );

        helper.setFrom("notifications@example.test");
        helper.setReplyTo("support@example.test");
        helper.setTo(recipient);
        helper.setSubject("Booking confirmation");
        helper.setText("Your consultation booking has been recorded.", false);

        mailSender.send(message);
    }
}
~~~

In the example:

- **setFrom(...)** sets the **From** header.
- **setReplyTo(...)** sets the **Reply-To** header.
- **setTo(...)** declares **To** recipients.
- **setCc(...)** and **setBcc(...)** can be used for public or blind copies.
- **send(...)** instructs the mail layer to perform sending; it does not prove the final recipient saw the email in their Inbox.

The code uses **jakarta.mail** classes suited for modern Spring lines built on Jakarta Mail. Older Spring versions based on **javax.mail** require the corresponding namespace.

### Setting Reply-To with SimpleMailMessage

If only plain-text email is needed, **SimpleMailMessage** also supports setting standard addresses:

~~~java
import org.springframework.mail.SimpleMailMessage;

SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("notifications@example.test");
mail.setReplyTo("support@example.test");
mail.setTo("customer@recipient.test");
mail.setSubject("Confirmation");
mail.setText("Your request has been recorded.");

mailSender.send(mail);
~~~

The difference between message-building objects does not alter protocol semantics: Reply-To remains a header for replies; the envelope is governed by the SMTP client/transport and its configuration.

## 7. Configuring MAIL FROM in the SMTP Transport

With a Jakarta Mail-based SMTP transport, the **mail.smtp.from** property is commonly used to set the **envelope sender**. In Spring Boot, this property can be passed via **spring.mail.properties**:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: "smtp-user"
    password: "<load-secret-from-environment>"
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.from]": "bounces@bounces.example.test"
      "[mail.smtp.connectiontimeout]": 3000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000
~~~

This is an **illustrative** configuration; host, port, TLS, authentication, and sending policies must follow your provider. In real apps, username/password must come from environment variables or a secret manager; the placeholder string above is not a usable password.

Specifically:

- The **mail.smtp.from** property instructs the SMTP client to use the specified envelope sender address for that transport.
- It **does not replace** the **From** header set via **helper.setFrom(...)**.
- It **does not replace** **Reply-To**.
- It **does not mean** you directly created or control the final **Return-Path** header.

If no envelope sender is configured, the default depends on how the SMTP transport derives the sender address and environment configuration. Do not rely on guesswork when a fixed bounce-receiving address is needed.

The property above is shared configuration for the configured SMTP transport. If different flows need different envelope senders or per-message bounce identifiers, check **per-message envelope sender** mechanisms supported by your implementation/provider, or use a provider API with that feature. **Do not manually set the Return-Path header as a substitute for configuring MAIL FROM.**

### Providers May Rewrite MAIL FROM

Some services allow only bounce addresses/domains they manage, or require sending-domain verification. They may accept a message with the app's proposed envelope sender and then use another address on subsequent SMTP hops to collect bounces.

Therefore, when verifying Return-Path in practice, combine application-side SMTP configuration, provider logs or send metadata, and the raw message in the receiving mailbox. Each source observes **different stages**; a value in Spring's configuration does not necessarily appear unchanged at every hop.

## 8. SPF, DKIM, and DMARC: Why Does From Differing from Return-Path Matter?

Email addresses do more than display names and routing; their domains also tie into sender authentication.

### SPF Typically Checks the SMTP MAIL FROM Domain

**SPF (Sender Policy Framework)** lets receiving servers verify whether the sending server's IP is authorized by the relevant domain. In standard cases, the domain checked by SPF comes from **RFC 5321 MAIL FROM** (the envelope sender). With a null reverse-path, checking may rely on the **HELO/EHLO** identity per SPF rules.

Example:

~~~text
From: notifications@company.example
MAIL FROM:<bounce@bounces.provider.example>
~~~

SPF may pass for **bounces.provider.example**, yet that result **does not automatically prove** the message was sent on behalf of **company.example** in the From header.

### DKIM Uses the Signing Domain's Signature

**DKIM** places a signature in headers so receivers can verify the integrity of signed parts and the signing domain (**d=** parameter). The signing domain need not match Reply-To or the envelope sender.

### DMARC Ties Back to the From Header

**DMARC** uses the domain in the **From** header as the anchor for **alignment** against SPF or DKIM identities. Depending on relaxed/strict alignment policy, DMARC can pass when at least one mechanism authenticates and aligns properly with the From header.

In other words:

- Changing **Reply-To** does not magically make SPF/DKIM/DMARC pass.
- Changing **Return-Path** or **MAIL FROM** can affect which domain SPF checks and whether SPF aligns with From.
- The **From** header is the key identity for DMARC; Return-Path is not a substitute for From.
- A provider using its own bounce domain and a DKIM domain aligned with From can still pass DMARC via DKIM, even if the envelope domain's SPF does not align.

Hence, when sending from a corporate domain through a third party, treat **SPF, DKIM, DMARC, and bounce domain setup** as one coherent system rather than merely changing addresses in Java code.

## 9. Bounces, User Replies, and Auto-Responders Are Separate Flows

Suppose a customer does not exist or a mailbox is blocked; the system may receive a nondelivery notice. That notice differs from a reply actively written by a recipient:

| Scenario | Related Signal or Address | What the Application Must Handle |
| --- | --- | --- |
| User clicks **Reply** | Reply-To or From | Read, support, or route the reply to the right conversation |
| SMTP fails to deliver | MAIL FROM / Return-Path, DSN, or provider event | Record delivery failure, avoid blindly resending to bad addresses |
| Provider reports deferred | SMTP response or delivery event | Wait/retry per policy; do not assume permanent failure yet |
| User enabled auto-reply | Mail client/server rules | Do not assume it always goes to Reply-To |
| Provider sends bounce webhook | Provider event data | Verify webhook, correlate back to the right message/job |
| User forwards the email | Address chosen by user or forward rule | Do not infer final recipient solely from original To |

A **bounce mailbox** needs a way to collect and parse DSNs, or the email service may provide equivalent events. Simply setting a **bounces@...** address without monitoring leaves the application unaware of which messages failed delivery.

### Per-Send-Job Bounce Addresses

Using per-message addresses such as:

~~~text
bounce+booking-782@bounces.example.test
bounce+booking-783@bounces.example.test
~~~

lets you correlate failure notices to individual send jobs, provided the domain and email infrastructure support routing that address. Generating distinct envelope senders to correlate per recipient or per message is called **Variable Envelope Return Path (VERP)**. Ensure the syntax, domain, and bounce collection work with your provider; do not assume every SMTP server implements this automatically.

When a bounce arrives, an application can use the job code to classify it: nonexistent address, mailbox full, policy block, or temporary error. Not every DSN contains all needed details, and providers may deliver status via webhooks rather than returning a message to a separate mailbox.

## 10. Reading Raw Emails to Investigate: What You See and What You Don't

When troubleshooting, depending on the email client, you can view **Show original**, **View source**, or **View message headers**. A raw message typically contains:

~~~text
Return-Path: <bounce@bounces.example.test>
Received: from outbound.example.test by mx.recipient.test ...
From: "Course Updates" <notifications@example.test>
Reply-To: <helpdesk@example.test>
To: "Lan" <lan@customer.test>
Subject: Course notification
Message-ID: <some-id@example.test>
Date: ...
~~~

How to read it:

- **From**: identity shown inside the email.
- **Reply-To**: suggested target for replies.
- **Return-Path**: reverse-path recorded at delivery time, if present and preserved in the copy.
- **Received**: processing trace across mail servers; read in context and assess trustworthiness of each hop.
- **Message-ID**: header-level message identifier, useful for log correlation but not synonymous with a single delivery or single recipient.

Some systems add headers like **Delivered-To** or **X-Original-To** to record the recipient or pre-routing address. These fields **do not appear uniformly across all providers** and cannot serve as a universal source of truth for every `RCPT TO` traversed.

### Can You Infer the Full Envelope from a Raw Message?

**Not reliably.** A raw message in a recipient's mailbox has traversed multiple mail servers; it typically does not retain all historical SMTP **RCPT TO** commands. The **To** header is display content, not a log of server recipient acceptances. Many people can receive copies of one MIME message while seeing only the same original To field.

To know which addresses were targeted at the application-controlled stage, rely on recipient-generation data, SMTP logs, or provider logs. To know which mailbox a recipient actually landed in after forwarding, you may need logs or assistance from the receiving mail infrastructure.

When logging, record send job IDs, message IDs, statuses, and essential operational info per data policy; avoid logging full message bodies, SMTP passwords, tokens, or personal addresses beyond what is needed.

## 11. Common Mistakes When Integrating Spring Mail

### Mistake 1: "I set Reply-To to receive bounces"

**Wrong mechanism.** Reply-To is for human-initiated replies. Bounces are handled by the SMTP delivery chain, usually based on the envelope reverse-path or provider events.

**Right mental model:** configure the reply-receiving address and bounce handler/address as two independent flows of responsibility.

### Mistake 2: "Setting Return-Path as a header is enough"

**No guarantee.** Return-Path on the final message relates to SMTP MAIL FROM; manually writing the header may not affect the envelope and can be overwritten by servers.

**Right mental model:** use the transport/provider's envelope-sender configuration and observe actual results.

### Mistake 3: "To has one address, so the email goes only to that person"

**Insufficient evidence.** Cc, Bcc, aliases, mailing lists, forwarding, and downstream routing steps can make actual recipients differ from the To list.

**Right mental model:** separate **display recipients** from **envelope recipients** and subsequent delivery steps.

### Mistake 4: "Bcc is just a UI hiding trick"

**Incomplete.** Done properly, Bcc must be handled when creating copies and sending so hidden recipients are not exposed in visible data. If assembling MIME messages manually or passing through incompatible gateways, unwanted headers risk leaking.

**Right mental model:** use proper APIs, test received copies across different addresses, and send individual emails when strict privacy is required.

### Mistake 5: "Return-Path looks like From, so just use the same one"

They **can** share the same address in very simple setups, yet they serve different purposes. At high email volumes or when bounce management is needed, a dedicated domain for the envelope sender makes sense. Configuration must follow authentication policies and authorized sending domains.

### Mistake 6: "Calling JavaMailSender.send() means the recipient got it"

**Cannot be inferred.** Success on the Spring side usually indicates only that submission to the mail transport/server completed at that stage. The message may still be delayed, bounced, classified as Spam, or forwarded.

**Right mental model:** define **SUBMITTED**, **DELIVERED**, and **BOUNCED** states from real data; use provider events if post-submission monitoring is needed.

## 12. Designing Addresses for a Real-World Application

Suppose a system sends confirmation emails, course notifications, and customer support messages. They can be divided as:

| Purpose | Example | Reason |
| --- | --- | --- |
| From header | **notifications@example.test** | Clear notification identity shown to readers |
| Reply-To | **support@example.test** | User replies are read and handled |
| SMTP MAIL FROM | **bounce@bounces.example.test** | Separates nondelivery notices from the support mailbox |
| To/Cc/Bcc | Per-job addresses | Target recipients determined by business logic |
| Job identifier | **MAIL-JOB-782** | Correlates send logs, retries, and provider events |

In environments with multiple email types, Reply-To can be scoped per team or ticket, while the envelope sender follows the provider's domain and bounce-handling setup. Example addresses are illustrative only; real addresses must belong to an organizational domain authorized and configured on the infrastructure.

An operable design should answer:

1. **Who is permitted to appear in From?** Are the domain, display name, and authentication policies valid?
2. **Who handles Reply-To?** Is there a real mailbox, support workflow, or ticket routing?
3. **Who receives and parses bounces?** Is there a webhook/API/provider event or monitored mailbox?
4. **Who are the envelope recipients?** Where does the list come from, and are there Bcc, group lists, or aliases?
5. **What status can the application prove?** Only successful submission, or verified delivery and bounce evidence?

Separating these questions reduces reliance on the false assumption that a single address field can simultaneously handle display, replies, error handling, and routing.

## 13. Reasoning Exercise

Examine this illustrative message:

~~~text
SMTP MAIL FROM:<bounce+order-15@bounces.shop.test>
SMTP RCPT TO:<accounting@shop.test>
SMTP RCPT TO:<client@customer.test>

From: "Shop" <orders@shop.test>
Reply-To: <help@shop.test>
To: <client@customer.test>
Subject: Order confirmation
~~~

**1. When client@customer.test clicks Reply, which address is usually selected?**

**help@shop.test**, because it is in **Reply-To**. The user or mail client can still override that choice.

**2. If the mail server fails to deliver to client@customer.test, where should the error notice be expected to go?**

Under reverse-path mechanics, the error notice can be sent to **bounce+order-15@bounces.shop.test**, or reported by the provider via its event system. Do not assume it goes to **help@shop.test**.

**3. Why can accounting@shop.test receive the message even though it does not appear in To?**

Because the SMTP transaction includes **RCPT TO** for that address. It could be a recipient added via Bcc or sending policy; visible headers do not reflect the entire envelope list.

**4. Can you assert the email reached client's Inbox merely because RCPT TO succeeded?**

**No.** An SMTP server accepting a recipient at one step does not confirm final delivery finished or landed in the Inbox.

**5. If you read the raw message on the client, are you guaranteed to find the RCPT TO command for accounting?**

**No.** Raw messages usually contain MIME headers and traces added by servers, not the full SMTP transcript. Hidden recipient lists should not appear publicly in copies delivered to clients.

## 14. Remembering the Right Boundaries

When writing Spring Mail code, ask questions at the right technical layer:

~~~text
Who does the reader see the email is from?
    -> From

Where will the reader be directed when clicking Reply?
    -> Reply-To (or From when Reply-To is absent)

If infrastructure fails to deliver, where do errors go?
    -> SMTP MAIL FROM / reverse-path, reflected by Return-Path

Who is the SMTP server asked to deliver the message to?
    -> RCPT TO (may have multiple addresses)

Who ultimately receives a copy in their mailbox?
    -> Outcome of routing, aliases, forwarding, and delivery policies
~~~

**Reply-To, Return-Path, and actual recipient addresses solve three different problems**: user replies, transport error handling, and message routing. Separating them clearly from the start leads to more accurate Spring Framework Mail configuration, clearer log interpretation, and email systems built for support, tracking, and failure recovery.
