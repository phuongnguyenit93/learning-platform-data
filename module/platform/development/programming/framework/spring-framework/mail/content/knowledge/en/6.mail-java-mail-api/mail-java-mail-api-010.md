# Sending One Message to Multiple Recipients

A Spring system needs to notify three engineers of a maintenance schedule and copy the team lead. Because the outgoing content is identical, the application does not necessarily have to create four separate emails. It can build **one email message**, add multiple addresses to the recipient list, and call `JavaMailSender.send(...)` once. The SMTP infrastructure handles delivering the message to each address.

In **Spring Framework Mail**, sending one message to multiple recipients is common for group announcements, internal newsletters, shared reports, or group invitations. However, "one message" does not mean "every recipient sees the same address list", "every mailbox receives it successfully", or "only one copy travels over the network". To implement this properly, you must understand how **To, Cc, and Bcc** fields work, the difference between **headers** and the **SMTP envelope**, and how to manage privacy and partial failures.

## 1. What Are One Message and Multiple Recipient Addresses?

In the Java ecosystem, `MimeMessage` represents an email with information such as sender, recipients, subject, body, and attachments. One `MimeMessage` can hold multiple recipient addresses.

Example of a shared announcement email:

~~~text
From: system@example.org
To: an@example.net, binh@example.net
Cc: lead@example.net
Subject: System maintenance schedule

The system will undergo maintenance on Saturday night.
~~~

Recipients in **To** are the direct recipients. Those in **Cc** receive a copy and typically see the To/Cc addresses in the headers as well. If the application adds `audit@example.net` to **Bcc**, that address can also receive the message, yet is not disclosed to other recipients in the Bcc field of the delivered email under standard mail flow.

~~~mermaid
flowchart LR
    A["Spring application"] --> B["One MimeMessage"]
    B --> C["JavaMailSender"]
    C --> D["SMTP relay"]
    D --> E["an@example.net"]
    D --> F["binh@example.net"]
    D --> G["lead@example.net"]
    D --> H["audit@example.net — Bcc"]
~~~

This is a conceptual model: the SMTP relay may make multiple connections, queue, or fan out copies to deliver to each mailbox. On the application side, only **one message object and one send method call** are needed for this request.

### How Does One Message Differ from Multiple Messages?

| Approach | Objects created | Suitable scenarios |
| --- | --- | --- |
| One `MimeMessage` with multiple To/Cc/Bcc | **One** message carrying shared content for multiple addresses | Shared announcements with identical subject and body |
| Multiple `MimeMessage`s, one recipient per message | **Many** independent messages | Personalized emails, per-user tokens, per-person status |
| Calling `JavaMailSender.send(MimeMessage...)` with multiple objects | Sends **multiple messages** through the same API | Sending a batch of independent messages |

A common misconception on the last point: `send(MimeMessage... mimeMessages)` takes **an array of messages**, not an array where each element is one recipient address. To send one message to multiple recipients, configure the recipient list **inside the message**.

## 2. What Do To, Cc, and Bcc Express?

Recipient addresses are not just a list for SMTP routing. The three types To/Cc/Bcc also carry **communication semantics** and govern **who sees which recipient information**.

| Field | Common meaning | Address visible to other recipients? | Related API |
| --- | --- | --- | --- |
| **To** | Primary recipients of the notice | Usually **yes**, in the To header | `setTo(...)`, `addTo(...)` |
| **Cc** (*carbon copy*) | Copied recipients for visibility or coordination | Usually **yes**, in the Cc header | `setCc(...)`, `addCc(...)` |
| **Bcc** (*blind carbon copy*) | Recipients hidden from the publicly displayed list | Usually **no** in copies delivered to other recipients via standard sending | `setBcc(...)`, `addBcc(...)` |

Example send request with:

~~~text
To:  an@example.net, binh@example.net
Cc:  lead@example.net
Bcc: audit@example.net
~~~

In business terms, all four addresses may be **delivery destinations**. In terms of visibility, however, the copy delivered to An/Binh/lead normally discloses only **To** and **Cc**. Bcc recipients can still read the message body; they are not restricted from the email content.

**Bcc is not an encryption mechanism and does not guarantee absolute anonymity.** The sending application, email provider, administrative systems, or outbound logs can still see Bcc addresses. If application code exports raw MIME, forwards emails manually, or logs Bcc headers, that information can leak. Keeping a recipient list confidential requires governing the entire creation, sending, tracking, and logging pipeline.

### Which Type Should You Use?

- Sending a task for An and Binh to handle, with the team lead kept informed: use **To** for An/Binh and **Cc** for the team lead.
- Sending a shared announcement to a list whose members **should not see one another's addresses**: consider **Bcc** or, even better when personalization/privacy matters, **one message per person**.
- Sending OTP codes, password reset links, personal reports, or private data: **one separate message per recipient**, never put the whole list into To/Cc.
- Sending a copy to an audit mailbox: use Bcc only if security policy and retention rules allow it; many systems record event logs instead of automatically emailing extra copies.

**A Bcc recipient can still reveal that they received the email** by forwarding or replying. Bcc only controls whether that address field is disclosed in normal delivered message copies, not downstream user behavior.

## 3. How Does SMTP Actually Deliver to Multiple Recipients?

An email has two layers of recipient information:

1. **Message headers**: `To`, `Cc`, and sometimes `Bcc` while the object is being built in the application; these describe the message's recipients.
2. **SMTP envelope**: addresses used by the SMTP relay in `RCPT TO` commands to specify delivery destinations.

An illustrative SMTP session might look like this:

~~~text
C: EHLO application.example.org
S: 250 smtp-relay.example.org
C: MAIL FROM:<system@example.org>
S: 250 Sender accepted
C: RCPT TO:<an@example.net>
S: 250 Recipient accepted
C: RCPT TO:<binh@example.net>
S: 250 Recipient accepted
C: RCPT TO:<lead@example.net>
S: 250 Recipient accepted
C: RCPT TO:<audit@example.net>
S: 250 Recipient accepted
C: DATA
S: 354 Send message content
C: From: system@example.org
C: To: an@example.net, binh@example.net
C: Cc: lead@example.net
C: Subject: Maintenance schedule
C:
C: The system will undergo maintenance on Saturday night.
C: .
S: 250 Message accepted for delivery
~~~

This is only an example of command ordering; in practice a session may use STARTTLS and AUTH before `MAIL FROM`, responses differ across providers, and the envelope sender address may differ from the `From` header.

In the example there are **four `RCPT TO` commands**, matching four delivery destinations, including the Bcc address. Yet the `DATA` block is transmitted **once** in this illustrative session. The Bcc address does not appear in the `To` or `Cc` headers sent to other recipients.

This explains three key points:

- **One message can have multiple SMTP destinations.** SMTP destinations cannot be inferred solely by reading the `To` line once delivered.
- **Bcc can receive the email even though it is hidden in outgoing headers.** The mail system uses envelope recipient info to route the message.
- **A single send call does not mean delivery succeeded for everyone.** The SMTP server may accept or reject individual addresses at processing time, or an accepted email can still bounce later.

With Jakarta Mail, standard SMTP transport reads the recipient set from the message to handle delivery. When you need lower-level control over the envelope or to integrate a custom relay, you must understand `Transport.sendMessage(...)` and transport policies; that goes beyond a Spring application simply calling `JavaMailSender.send(...)`.

## 4. Sending to Multiple Recipients with SimpleMailMessage

If you only need to send **plain-text** content without attachments, `SimpleMailMessage` is a concise choice.

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class MaintenanceNoticeService {

    private final JavaMailSender mailSender;

    public MaintenanceNoticeService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendCommonNotice() {
        SimpleMailMessage message = new SimpleMailMessage();

        message.setFrom("system@example.org");
        message.setTo(
                "an@example.net",
                "binh@example.net"
        );
        message.setCc("lead@example.net");
        message.setBcc("audit@example.net");
        message.setSubject("Maintenance schedule notice");
        message.setText(
                "The system will undergo maintenance on Saturday night."
        );

        mailSender.send(message);
    }
}
~~~

`SimpleMailMessage`'s `setTo(String...)`, `setCc(String...)`, and `setBcc(String...)` methods accept multiple addresses via varargs or string arrays. Spring Mail sends this object using the configured `MailSender`/`JavaMailSender` component.

The example uses placeholder addresses to demonstrate API usage. In a real application, `From` must be authorized by the SMTP provider, and recipient lists must be validated per business rules.

### When Should You Switch to MimeMessage?

`SimpleMailMessage` only models simple email fields. If you need HTML, dual plain-text/HTML versions, inline images, Unicode with an explicit charset, or attachments, use `MimeMessage` and `MimeMessageHelper`.

Crucially, **how you declare multiple recipients is similar**, whether the email body is built with the simple API or complex MIME.

## 5. Sending One MimeMessage to Multiple Recipients with MimeMessageHelper

`MimeMessageHelper` provides methods accepting string addresses or `InternetAddress`, convenient when building MIME messages. For emails using accented Vietnamese text, you can specify `UTF-8` explicitly.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class TeamAnnouncementService {

    private final JavaMailSender mailSender;

    public TeamAnnouncementService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendAnnouncement() throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom("system@example.org");
        helper.setTo(new String[] {
                "an@example.net",
                "binh@example.net"
        });
        helper.setCc(new String[] {
                "lead@example.net"
        });
        helper.setBcc(new String[] {
                "audit@example.net"
        });

        helper.setSubject("This week's system maintenance schedule");
        helper.setText(
                "The system will undergo maintenance on Saturday night.",
                false
        );

        mailSender.send(message);
    }
}
~~~

`helper.setTo(String[])`, `setCc(String[])`, and `setBcc(String[])` replace **the entire corresponding address group**. The `addTo(...)`, `addCc(...)`, and `addBcc(...)` variants append one address at a time, suited when building a recipient list incrementally.

Example:

~~~java
helper.setTo("an@example.net");
helper.addTo("binh@example.net");
helper.addCc("lead@example.net");
helper.addBcc("audit@example.net");
~~~

If the list is already assembled, it is usually cleaner and easier to manage to convert it into a typed array and call the setter once per field. If you want to append to an already-set list, use `addTo` instead of calling `setTo` a second time so you do not accidentally overwrite earlier entries.

### How Do setTo and addTo Differ?

| Call | Meaning |
| --- | --- |
| `helper.setTo("an@example.net")` | Sets the message's To list to a single address. |
| `helper.setTo(new String[]{"an@example.net", "binh@example.net"})` | Sets the To list to two addresses. |
| `helper.addTo("binh@example.net")` | Appends one address to the existing To list. |
| `helper.setCc(new String[]{"lead@example.net"})` | Sets the Cc recipient list. |
| `helper.addBcc("audit@example.net")` | Appends a Bcc recipient. |

Do not pass a combined string like `"an@example.net,binh@example.net"` to a method expecting **a single address** and expect the library to always split it as desired. When inputs contain multiple addresses, use **arrays, validated lists, or an address-parsing API** properly.

## 6. Configuring Spring Boot to Send Through an SMTP Relay

If using Spring Boot with Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Example configuration in `application.properties`:

~~~properties
spring.mail.host=smtp.provider.example
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}
spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true
spring.mail.properties.mail.smtp.ssl.checkserveridentity=true
spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=5000
spring.mail.properties.mail.smtp.writetimeout=5000

app.mail.from=${APP_MAIL_FROM}
~~~

`smtp.provider.example` is a placeholder hostname. For real sending, use the host, port, authentication mechanism, and TLS settings matching your email service. Credentials should come from environment variables or a secrets manager rather than source code.

SMTP configuration **is not where To/Cc/Bcc are declared** for individual emails. Recipient lists are placed on `SimpleMailMessage` or `MimeMessage` when building the message.

Sending to multiple recipients via a relay also does not mean the application must query DNS MX records for each domain itself. The SMTP provider typically resolves receiving domains and handles downstream routing.

## 7. Loading Recipient Lists from Business Data

In practice, recipient lists can come from a database, a team roster, or event processing. Applications must validate data before constructing the message:

1. Identify addresses authorized to receive the notification.
2. Assign each address to To, Cc, or Bcc according to purpose.
3. Filter out empty or malformed entries.
4. Handle duplicate addresses per a clear policy.
5. Enforce recipient-count and content-type limits.
6. Then construct `MimeMessage` and call `send(...)`.

### Example Service Accepting Dynamic Lists

Suppose business logic supplies three lists from a controlled source. The following service requires at least one address, validates syntax, and preserves recipient groups.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.AddressException;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class GroupMailService {

    private final JavaMailSender mailSender;
    private final String from;

    public GroupMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String from) {

        this.mailSender = mailSender;
        this.from = from;
    }

    public void sendToGroup(
            List<String> to,
            List<String> cc,
            List<String> bcc,
            String subject,
            String body) throws MessagingException {

        String[] toAddresses = parseMailboxes(to);
        String[] ccAddresses = parseMailboxes(cc);
        String[] bccAddresses = parseMailboxes(bcc);

        if (toAddresses.length + ccAddresses.length
                + bccAddresses.length == 0) {
            throw new IllegalArgumentException(
                    "At least one recipient is required"
            );
        }

        if (subject == null || subject.isBlank()) {
            throw new IllegalArgumentException(
                    "Subject cannot be blank"
            );
        }

        if (body == null || body.isBlank()) {
            throw new IllegalArgumentException(
                    "Body cannot be blank"
            );
        }

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom(from);

        if (toAddresses.length > 0) {
            helper.setTo(toAddresses);
        }
        if (ccAddresses.length > 0) {
            helper.setCc(ccAddresses);
        }
        if (bccAddresses.length > 0) {
            helper.setBcc(bccAddresses);
        }

        helper.setSubject(subject);
        helper.setText(body, false);

        mailSender.send(message);
    }

    private static String[] parseMailboxes(List<String> input)
            throws AddressException {

        if (input == null || input.isEmpty()) {
            return new String[0];
        }

        String[] addresses = new String[input.size()];

        for (int i = 0; i < input.size(); i++) {
            String raw = input.get(i);

            if (raw == null || raw.isBlank()) {
                throw new IllegalArgumentException(
                        "List contains a blank address"
                );
            }

            if (raw.indexOf('\r') >= 0
                    || raw.indexOf('\n') >= 0) {
                throw new IllegalArgumentException(
                        "Address contains newline characters"
                );
            }

            // Each item must be a single mailbox.
            InternetAddress[] parsed =
                    InternetAddress.parse(raw.trim(), true);

            if (parsed.length != 1 || parsed[0].isGroup()) {
                throw new IllegalArgumentException(
                        "Each item must be a single address"
                );
            }

            parsed[0].validate();
            addresses[i] = parsed[0].getAddress();
        }

        return addresses;
    }
}
~~~

The example only covers **input address validation**, and does not yet handle duplicate addresses across To/Cc/Bcc, notification consent, total recipient caps, or per-recipient sending policies. Add those at the business layer according to real requirements.

`InternetAddress.parse(..., true)` and `validate()` mainly check address syntax. They **do not confirm the mailbox exists**, do not check recipient opt-in, and do not guarantee the destination mail server will accept the message.

### Should Duplicate Addresses Be Removed?

For example, An appears in both To and Cc. Duplicates can produce confusing messages or affect how the SMTP provider processes recipients. Therefore, the application should enforce a clear policy, typically **preventing the same address from appearing across multiple groups simultaneously**.

Still, do not blindly call `toLowerCase()` on **the entire address** as an absolute canonical rule: the email **domain** is case-insensitive, yet equivalence of the local-part before `@` can depend on the receiving system. Likewise, plus-addressed (`+`) emails, aliases, or alternative forms do not always map to the same mailbox.

Normalize according to organizational and provider policy, preserve the original address to explain deduplication decisions, and avoid unintentionally altering the destination.

## 8. Inspecting Recipients Attached to a MimeMessage

After using the helper to set addresses, you can read the fields back via Jakarta Mail APIs:

~~~java
import jakarta.mail.Address;
import jakarta.mail.Message;
import jakarta.mail.internet.MimeMessage;

Address[] to = message.getRecipients(
        Message.RecipientType.TO
);
Address[] cc = message.getRecipients(
        Message.RecipientType.CC
);
Address[] bcc = message.getRecipients(
        Message.RecipientType.BCC
);
Address[] all = message.getAllRecipients();
~~~

A getter can return `null` when the corresponding field is not present. `getAllRecipients()` returns the list of destination addresses on the message, useful to **confirm at least one address exists** before sending:

~~~java
Address[] recipients = message.getAllRecipients();

if (recipients == null || recipients.length == 0) {
    throw new IllegalStateException(
            "Message has no recipients"
    );
}
~~~

This check only confirms **addresses have been assigned to the object**. It does not verify mailboxes exist, guarantee the provider can deliver to all of them, or prove notification permission.

When a message contains Bcc, `getRecipients(BCC)` on the constructed object can return the Bcc list. **Never write this result to logs or return it in user-facing APIs** if the list contains private data. Just because the message holds addresses for sending does not mean that list is safe to expose publicly.

### Recipient Addresses in MIME Differ from the SMTP Envelope

At the lower Jakarta Mail layer, you can call:

~~~java
Transport.send(message);
~~~

On the common sending path, the transport takes addresses from the message for SMTP submission. For special cases, the API:

~~~java
transport.sendMessage(message, recipients);
~~~

lets the caller pass a specific `recipients` target array for the send operation. That set can differ from what appears in the To/Cc header fields; using it directly makes you responsible for specifying valid addresses and handling transport outcomes. In typical Spring applications, `JavaMailSender.send(message)` is simpler and more consistent.

## 9. Sending the Same HTML Content or Attachment to Multiple People

Recipient-list rules remain unchanged when a message becomes multipart. Example sending the same PDF file:

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setFrom("report@example.org");
helper.setTo(new String[] {
        "an@example.net",
        "binh@example.net"
});
helper.setSubject("Weekly report");

helper.setText(
        "<p>The weekly report is attached.</p>",
        true
);

helper.addAttachment(
        "weekly-report.pdf",
        new ClassPathResource("mail/weekly-report.pdf"),
        "application/pdf"
);

mailSender.send(message);
~~~

The application needs `src/main/resources/mail/weekly-report.pdf` on the classpath, a provider-authorized sender, and a properly configured SMTP relay. `MimeMessageHelper` organizes MIME parts and lets Jakarta Mail handle encoding/boundaries.

**Every recipient of the message receives the exact same content and attachment**, unless an intermediary relay or provider policy alters delivery. Never use one shared message if the PDF may only be viewed by one specific recipient.

### What About HTML Personalized with Each Person's Name?

Suppose you want:

~~~text
Hello An, your invoice is INV-101.
Hello Binh, your invoice is INV-102.
~~~

One `MimeMessage` has only **one Subject/body/attachment set**. If you put both An and Binh in To, they receive the exact same body, so you cannot personalize content per person by substituting a variable inside one shared message.

The right approach is creating **one message per recipient**, with content built from that person's own data:

~~~java
for (InvoiceNotice notice : notices) {
    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper =
            new MimeMessageHelper(message, false, "UTF-8");

    helper.setFrom("billing@example.org");
    helper.setTo(notice.email());
    helper.setSubject("Invoice " + notice.invoiceCode());
    helper.setText(
            "Your invoice " + notice.invoiceCode()
                    + " is ready.",
            false
    );

    mailSender.send(message);
}
~~~

This is a conceptual example assuming `InvoiceNotice` is an application-defined type with `email()` and `invoiceCode()`. In real systems, guard private content, track outcomes, and manage retries per notification.

Sending many messages can be optimized with queues, batching, or multi-message APIs, yet **never trade personal data isolation** for fewer method calls.

## 10. Does One send() Guarantee All Recipients Succeed?

**No.** This is one of the most critical distinctions between an API operation and a business outcome.

In SMTP, the server can respond differently to each `RCPT TO` command. For example:

~~~text
C: RCPT TO:<an@example.net>
S: 250 2.1.5 Recipient OK

C: RCPT TO:<binh@example.net>
S: 550 5.1.1 User unknown

C: RCPT TO:<lead@example.net>
S: 250 2.1.5 Recipient OK
~~~

Here, one address is rejected while two addresses are accepted during recipient checking. **Subsequent behavior depends on the SMTP client, transport configuration, and server response**. One configuration may abort submitting the message upon finding a bad destination; another may deliver to valid recipients while reporting errors for invalid addresses.

### Partial Delivery in Jakarta Mail

Jakarta Mail SMTP has transport options such as `mail.smtp.sendpartial` to govern cases where **some addresses are valid and others are rejected**.

- With a policy disallowing partial sends, the transport may abort message submission upon encountering an invalid address.
- When configured to allow partial sends, the transport may deliver to valid addresses while reporting errors for invalid ones.
- A server can accept multiple addresses at submission time and still bounce an email later due to an error at the final destination. That outcome cannot be determined from the initial reply alone.

Related Jakarta Mail exceptions may include `SendFailedException` carrying address sets such as `validSentAddresses`, `validUnsentAddresses`, and `invalidAddresses`, depending on context and how the transport reports errors. In Spring Mail, send exceptions are typically wrapped in `MailSendException` or the corresponding `MailException` subclass.

**Never automatically infer that an error means "nobody received it" or that a send returning without exception means "everyone received it in their Inbox".** Tracking per-person status requires recording responses or events from mail infrastructure, including possible *bounces*.

### Avoid Claiming Atomicity

An SMTP send to multiple recipients **is not an atomic transaction** like a database transaction. Some addresses may be accepted by infrastructure while others are rejected, or the message may be received while the final reply is lost, leaving the application unsure of the outcome.

In particular, if you retry **the entire message** after an indeterminate failure, some recipients may receive duplicate emails. Design retries with an explicit policy rather than assuming "resending the whole list is safe".

## 11. Tracking Send Results per Recipient

If the product needs to know exactly who was submitted, who was rejected, and who received delivery, separate two concepts:

- **Overall send request:** notification ID, subject, content template, creation time.
- **Per-recipient state:** address, To/Cc/Bcc role, attempt count, submission outcome, and delivery events.

An application-layer data model might look like:

~~~text
mail_request:
  request_id: notif-2026-001
  template: maintenance-notice
  status: SUBMITTING

mail_recipient:
  - address: an@example.net
    role: TO
    delivery_status: SUBMITTED
  - address: binh@example.net
    role: TO
    delivery_status: FAILED
  - address: lead@example.net
    role: CC
    delivery_status: SUBMITTED
~~~

This is an **application-defined model**, not a built-in Spring Mail schema. The name `SUBMITTED` should only signify submitted or accepted by the relay per current evidence; use `DELIVERED` only when the system has sufficiently trustworthy delivery data.

If detailed per-recipient feedback is unavailable from the SMTP transport or provider, statuses should reflect **what is actually known**, such as `UNKNOWN` or `PENDING_CONFIRMATION`. Never invent a definitive status simply because a send call returned.

### Retries and Duplicate Prevention

Practices suited for applications requiring reliability:

1. Assign a unique `requestId` to each send intent and track each recipient.
2. Persist template references or enough data to reconstruct the message on retry.
3. Separate configuration errors, transient errors, and invalid-address errors.
4. Bound retry attempts and wait intervals; never retry forever.
5. When per-address feedback exists, consider retrying **only unconfirmed destinations** while still accepting that some outcomes may remain uncertain.
6. Use an outbox or queue when decoupling mail sending from business transactions.

If **personalized statuses and independent per-recipient retry control** are mandatory, the **one message per recipient** model is usually far easier to manage than one shared message with hundreds of destinations.

## 12. Operational Limits When Sending to Large Lists

An email sent to three people and one sent to three thousand differ operationally. SMTP providers may enforce limits:

| Possible limit | Impact |
| --- | --- |
| Maximum recipients per message | Server may reject part or all of an oversized list |
| Messages / send rate per account | Emails get delayed, throttled, or temporarily rejected |
| Message size | Attachments and MIME encoding can exceed limits |
| Anti-abuse / broadcast policies | May be flagged as bulk mail, spam, or a terms-of-service violation |
| Sender-address verification rules | `From` or envelope sender rejected |
| Quotas and sending-domain reputation | Impacts acceptance and inbox placement |

Exact limits are **provider-specific policies**, not standardized by Spring Framework Mail. Therefore, never hardcode a magic number like "every message can always send to 100 people" without knowing your provider's rules.

### Should You Split Lists into Multiple Groups?

When many recipients share identical content, the application can split them into batches sized within provider limits. However, each batch generally needs **its own separate message**, managed as an independent send—not merely splitting a list in memory and still feeding everyone into one `MimeMessage`.

Conceptual model example:

~~~mermaid
flowchart TD
    A["Authorized recipient list"] --> B["Apply security / limit policies"]
    B --> C["Split into batches"]
    C --> D["Batch 1 message"]
    C --> E["Batch 2 message"]
    C --> F["Batch N message"]
    D --> G["SMTP relay"]
    E --> G
    F --> G
~~~

When batching, account for someone appearing in multiple batches, avoid duplicates, and decide who is allowed to see the To/Cc list. If a large group must keep addresses private, Bcc can hide headers, though you must still comply with consent, unsubscribe options, and send quotas.

## 13. Privacy and Content Control

### 13.1. Do Not Put Customer Lists into To/Cc of Bulk Emails

Suppose a website wants to send a general notice to 500 customers. Creating:

~~~text
To: customer1@example.net, customer2@example.net, ...
~~~

lets recipients see the email addresses of hundreds of other people. That is a privacy risk even when the body holds no sensitive data. **Never use public To/Cc for recipient lists whose members are not authorized to see one another.**

Consider sending individually per person or using a dedicated bulk-email platform. Even with Bcc, control who can view lists in internal systems, logs, and provider dashboards.

### 13.2. Do Not Send Personalized Content in a Shared Message

Emails containing OTP codes, account confirmation links, password-reset tokens, invoices, account balances, or personal data must be built per recipient. If a body contains a token and multiple addresses are added to Bcc, **every recipient sees the exact same token**, creating a business security flaw.

Each person should receive their own content/token and their own message, or use a provider personalization mechanism that guarantees recipient isolation.

### 13.3. Bcc Addresses Can Still Surface Elsewhere

Even though the Bcc header is omitted from messages sent to other recipients, Bcc addresses can still appear in send-request databases, application logs, SMTP logs, "Sent" copies, or admin tools. Do not treat Bcc as a substitute for access control.

When logging, log request IDs, recipient counts, and error categories, avoiding dumping full To/Cc/Bcc arrays or raw MIME. If addresses must be stored for troubleshooting, enforce strict access-control and retention policies.

## 14. Common Mistakes When Sending One Message to Many Recipients

### 14.1. Calling setTo Multiple Times and Losing Earlier Recipients

~~~java
helper.setTo("an@example.net");
helper.setTo("binh@example.net");
~~~

`setTo` **resets** the To field. The result is not equivalent to adding both addresses. Instead, write:

~~~java
helper.setTo(new String[] {
        "an@example.net",
        "binh@example.net"
});
~~~

Or:

~~~java
helper.setTo("an@example.net");
helper.addTo("binh@example.net");
~~~

### 14.2. Confusing Bcc with Visually Hidden To

Putting recipients into To and hiding the field in your app's admin UI **does not alter the email's To header**. Recipients still see the To addresses. To send a blind copy per standard email flow, actually use `Bcc` or create separate messages.

### 14.3. Expecting One Message to Produce Custom Content per Recipient

A `MimeMessage` has one Subject and one serialized body. To vary names, invoices, tokens, or languages per recipient, build a corresponding message for each person.

### 14.4. Having Only Bcc Recipients and Assuming the Message Has No Recipients

If you inspect only `getRecipients(TO)`, it can return `null` even when valid Bcc addresses exist. If business policy allows Bcc-only messages, use `getAllRecipients()` to check total destinations; if To is mandatory, check To explicitly.

Some mail clients render messages without a public To header specially. Depending on requirements, the application can set a syntactically valid descriptive To header or send individually per recipient.

### 14.5. Assuming send() Returning Means Everyone Landed in the Inbox

`JavaMailSender.send(...)` does not produce final receipts from individual mailboxes. The SMTP server can accept a message and destination systems can bounce it later; messages can also land in spam. Track provider status separately if the product needs delivery outcomes.

### 14.6. Retrying the Entire Message After a Partial Send Failure

Some addresses may already have been accepted while others were rejected or left in an unknown state. Resending the entire list can produce duplicate emails. For critical requests, record per-recipient results or send per person to simplify management.

### 14.7. Believing InternetAddress.validate() Verifies Remote Mailboxes

`InternetAddress.validate()` validates address syntax within Jakarta Mail's supported scope, without sending test probes or verifying mailbox existence. Handle SMTP errors and bounces according to business rules.

### 14.8. Reusing a MimeMessage While It Is Being Mutated

`MimeMessage` is a **mutable** object. Do not let multiple threads concurrently modify the same object to add recipients and send. That can mix To/Cc/Bcc, Subject, body, and attachments across unrelated requests. Creating a fresh message per independent send request is far cleaner.

## 15. How to Inspect During Development and Testing

In a test environment, you can use a test SMTP server to capture messages without delivering them to the Internet. You can then verify:

- How many messages a send call produced.
- Which addresses were submitted via the SMTP envelope.
- Whether To/Cc headers in the received copy match the expected list.
- Whether Bcc was routed as a delivery target without appearing in displayed headers.
- Whether HTML, Unicode, and attachments were built properly.

In application unit tests, replace `JavaMailSender` with a mock or fake to capture the `MimeMessage` object passed to `send(...)`. For instance, assert values returned by:

~~~java
message.getRecipients(Message.RecipientType.TO);
message.getRecipients(Message.RecipientType.CC);
message.getRecipients(Message.RecipientType.BCC);
message.getAllRecipients();
message.getSubject();
~~~

When inspecting the object **before sending**, the Bcc header may still exist internally on the message; that is normal so the transport knows the destination. To verify **Bcc is not leaked during delivery**, inspect the actual email generated by the relay and the headers visible to the receiving mailbox, rather than only inspecting the pre-send MIME object.

These checks support feature development, yet do not replace operating a properly configured SMTP service or monitoring bounces in production.

## 16. Practice Questions

**Question 1.** To send a shared notice to An and Binh while keeping the team lead informed, how many `MimeMessage` objects must be created?

You can create **one `MimeMessage`** with To containing An/Binh and Cc containing the team lead, provided all three are allowed to see the recipient list and receive **identical content**.

**Question 2.** If you want the team lead to receive a copy without An and Binh seeing the lead's address in headers, what should you use?

Use **Bcc** or send a separate copy per an appropriate workflow. Bcc hides the address in normally delivered message copies, though it does not encrypt or erase traces of the address inside the sending system.

**Question 3.** Why can one message need multiple `RCPT TO` commands but only one `DATA` command?

Because `RCPT TO` declares the recipients in the **SMTP envelope**, whereas `DATA` carries **one message's** content. The mail server handles delivery to each destination according to its policies.

**Question 4.** Do two sequential calls `helper.setTo("an@example.net")` and `helper.setTo("binh@example.net")` keep both addresses?

No. `setTo` replaces the value of the To field. Pass a two-element array or call `addTo` for the second address.

**Question 5.** If each recipient must get a different OTP code, should you add everyone to Bcc on one email?

No. Bcc only hides the recipient list in headers; **the body remains identical**. Send separate messages with each recipient's own token.

**Question 6.** An email is sent to three addresses and `send(...)` returns without error. What has been confirmed?

Submission of the message to the sending infrastructure completed per the response available to the client. You cannot conclude every receiving mailbox succeeded or that users read the email.

**Question 7.** When an error occurs for one recipient, should you automatically resend the whole message to everyone?

Do not treat that as an always-safe retry. Understand the error and the possibility of partial delivery; when the outcome is uncertain, resending can create duplicate copies.

## 17. Mental Model to Remember

Sending one message to multiple recipients in Spring Framework Mail spans three layers:

~~~mermaid
flowchart TD
    A["Business rule: who receives identical content?"] --> B["MimeMessage: To / Cc / Bcc"]
    B --> C["JavaMailSender.send(message)"]
    C --> D["SMTP envelope: multiple RCPT TO"]
    D --> E["SMTP relay accepts and routes mail"]
    E --> F["Track per-recipient status if needed"]
~~~

Remember four core principles:

1. **One `MimeMessage` can target multiple addresses.** Use `setTo`/`addTo`, `setCc`/`addCc`, and `setBcc`/`addBcc` to build lists matching each role.
2. **To/Cc/Bcc carry visibility semantics.** To and Cc are normally public; Bcc must be handled carefully across the pipeline and does not replace recipient data-privacy policies.
3. **Everyone on one message shares identical content.** When personalized content, strict privacy, or independent state tracking is needed, create separate messages.
4. **A single send call does not guarantee delivery to the entire list.** SMTP can reject individuals, fail after acceptance, or bounce later; the system must record and handle outcomes at a realistic level of reliability.

Clearly understanding the relationship among **message – recipient headers – SMTP envelope – delivery status** lets you decide when to leverage one shared message and when to design an individual per-recipient sending flow for business correctness.

