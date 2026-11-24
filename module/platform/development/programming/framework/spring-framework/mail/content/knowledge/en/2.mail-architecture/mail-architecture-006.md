# SMTP Envelope and Message Headers & Body

When a Spring application sends an email, the data traveling over SMTP is not just a single string of sender, recipient, subject, and body. There are **two distinct layers of information**:

1. **SMTP envelope:** information exchanged between the SMTP client and server to *transport* the email.
2. **Email message:** data sent after the `DATA` command, consisting of **headers** and **body**, for the recipient and mail software to read.

This distinction explains many real-world scenarios: sending an email with a `From` address different from the SMTP account; a `Bcc` address still receiving the email without appearing in the message; clicking **Reply** sending to a different address from the one receiving bounce notifications; or an email accepted by the SMTP server yet later returned as undeliverable.

In Spring Framework Mail, developers primarily work with `JavaMailSender`, `SimpleMailMessage`, `MimeMessage`, and `MimeMessageHelper`. The library handles SMTP connections and building the proper wire format, yet understanding envelope, headers, and body accurately remains essential for configuration, error handling, and security checks.

## 1. Big Picture: The Envelope Sits Outside the Message Content

An SMTP session has this high-level structure:

```text
Connect and SMTP authenticate (if required)
    |
    +-- MAIL FROM:<bounce@example.com>     <- Envelope sender
    |
    +-- RCPT TO:<lan@example.org>          <- Envelope recipient #1
    |
    +-- RCPT TO:<archive@example.net>      <- Envelope recipient #2
    |
    +-- DATA
          |
          +-- Headers: From, To, Subject, Reply-To, ...
          +-- Blank line separator
          +-- Body: text, HTML, or MIME multipart
          |
          +-- End DATA
    |
    +-- SMTP server returns acceptance or rejection result
```

**The envelope is not inside the content after `DATA`.** If you only open an `.eml` file or view "Show original" in a mailbox, you are typically viewing the stored headers and body, not the complete `MAIL FROM` and `RCPT TO` commands of the original SMTP session.

Core differences:

| Aspect | SMTP Envelope | Message Headers and Body |
|---|---|---|
| Purpose | Instructs servers where to route the mail and where to send error notices | Describes sender, recipients, subject, and content for mail clients |
| Protocol position | `MAIL FROM`, `RCPT TO` commands before `DATA` | Content transmitted inside `DATA` |
| Underlying standard | SMTP / RFC 5321 | Internet Message Format / RFC 5322; MIME extensions for content |
| Actual recipients | Addresses accepted via `RCPT TO` | `To:`, `Cc:` are display fields; `Bcc:` must be kept confidential |
| Sending address | Envelope sender, typically used when generating bounces | `From:` states the author/displayed sending address of the message |
| Possibility of differing | Can differ from headers | Headers may exist without matching each transport address one-to-one |

An email can pass through multiple servers. Each SMTP hop uses an envelope appropriate for that hop; intermediate servers may also add trace headers. You should not assume the envelope stays strictly identical across an entire relay chain.

## 2. SMTP Envelope: Who Sends for Transport, and Where Does It Go?

### 2.1. `MAIL FROM` — Envelope Sender

Example command:

```smtp
MAIL FROM:<bounce@example.com>
```

This is the **reverse-path**, usually the address mail systems use to send non-delivery reports (NDRs, bounces). This address can be completely different from `From:` in the headers:

```text
SMTP envelope: MAIL FROM:<bounce@example.com>
Message header: From: "Shop Demo" <news@example.com>
```

Users see the email "from Shop Demo"; the mail infrastructure can send failure notices to `bounce@example.com`.

Things to distinguish:

- `MAIL FROM` is not the SMTP login account. The authenticated username (`AUTH`) is only the identity authorized to submit; a provider may require the envelope sender or `From` header to belong to an authorized domain.
- `MAIL FROM` does not necessarily match `Reply-To`: replying to an email and reporting transport errors are two separate tasks.
- When systems generate automated delivery failure notices, SMTP may use a **null reverse-path**: `MAIL FROM:<>`. This prevents infinite loops of error emails bouncing back and forth. Normal applications do not choose this value themselves for notification emails.

Some servers support extended SMTP parameters such as `SIZE` or `SMTPUTF8` in the transaction. Those parameters belong to the transport layer, not normal header fields.

### 2.2. `RCPT TO` — Recipient List for Transport

Example:

```smtp
RCPT TO:<lan@example.org>
RCPT TO:<archive@example.net>
```

Each `RCPT TO` declares **one envelope recipient address**. Addresses accepted at this step are what the server uses to forward the email.

This **does not mean** each `RCPT TO` must have a corresponding line in the `To:` header. For instance, in the same message:

```text
Envelope recipients:
  lan@example.org
  archive@example.net

Message headers:
  To: Lan <lan@example.org>
  Subject: Registration result
```

`archive@example.net` could be a blind carbon copy (`Bcc`) recipient, or another recipient specified at send time. Their name does not need to appear in `To:`.

The server may accept one address and reject another. Per-recipient error handling depends on SMTP responses and how the library/client proceeds with the transaction; you should not infer that all recipients succeeded merely because one recipient was accepted.

### 2.3. `DATA` and Separation from the Envelope

After the SMTP server allows content input with a `354` response, the client sends the **message headers and body** and terminates data using the SMTP rule (the `<CRLF>.<CRLF>` sequence). Leading dots on lines in the body are handled by the client using *dot-stuffing* so they are not mistaken for the end marker.

This mechanism is an SMTP transport detail. When using `JavaMailSender`, the application does not have to insert the terminating dot or write `DATA` commands manually.

The server returning `250` after finishing `DATA` means it has **accepted the message for further processing**. This response does not confirm the email appeared in the Inbox, does not mean the recipient opened it, and does not guarantee it will not bounce later.

## 3. Message Headers: Metadata Describing the Message

**Headers** are the lines preceding the first blank line in the message. Each field has the general form `Field-Name: value`. Standard headers define the structure of an email; MIME adds headers describing content types.

A simple message:

```text
From: "Demo App" <notifications@example.com>
To: "Lan" <lan@example.org>
Reply-To: support@example.com
Date: Thu, 12 Nov 2026 08:00:00 +0000
Message-ID: <welcome-123@example.com>
Subject: Welcome to Demo App
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

Your account is ready.
```

The blank line after `Content-Type` is the boundary between **headers** and **body**. Header lines are not SMTP commands; they are transmitted as message data inside `DATA`.

### 3.1. Common Headers

| Header | Role | Key Point to Remember |
|---|---|---|
| `From:` | Identifies the author/displayed sender address | Does not by itself determine where bounces go and does not by itself prove the sender is authenticated. |
| `Sender:` | Identifies the agent performing the send when distinct from the author | Has specific meaning in message structure; not synonymous with `MAIL FROM`. |
| `To:` | Displayed primary recipients | Not the sole list governing transport. |
| `Cc:` | Displayed copy recipients | Usually also has corresponding `RCPT TO` entries. |
| `Bcc:` | Blind copy recipients | Addresses must still be passed to SMTP, but must not be exposed in copies sent to other recipients. |
| `Reply-To:` | Preferred address when the user replies | Does not change `MAIL FROM` or `RCPT TO` of the outgoing email. |
| `Subject:` | Subject line | Display metadata, not a transport command. |
| `Date:` | Message creation/send timestamp per header | Differs from when a server receives or delivers the message. |
| `Message-ID:` | Message identifier | Helps with tracing/referencing; not a delivery confirmation code. |
| `MIME-Version:` | Indicates the message uses MIME | Usually `1.0`. |
| `Content-Type:` | Content type of the body or each MIME part | E.g., `text/plain`, `text/html`, `multipart/alternative`. |
| `Content-Transfer-Encoding:` | Byte representation of a body part | E.g., `quoted-printable` or `base64`. |
| `Received:` | Trace of a transport hop | Typically added by mail servers; may appear multiple times. |
| `Return-Path:` | Trace of the bounce address when delivered | Usually inserted by mail infrastructure based on reverse-path, not a way for apps to replace `MAIL FROM`. |

Authentication filters may also add headers like `Authentication-Results`; signing services may insert `DKIM-Signature`. Consider which system produced each header when analyzing a message, as not all headers were originally set by Spring or the application.

### 3.2. `From`, `Sender`, and `Reply-To` Do Not Replace Each Other

Suppose a business sends a notification on behalf of its support team:

```text
From: "Demo Support" <notice@example.com>
Reply-To: helpdesk@example.com
```

When clicking **Reply**, mail clients typically prefer `helpdesk@example.com`. Yet if the message is undeliverable, mail systems rely on the envelope sender to handle bounces. Setting `Reply-To` does not change the address used for error reporting.

`Sender` also has a specific meaning in emails with multiple authors in `From` or when the transmitting agent needs to be represented separately. In a simple notification system, usually only `From` is needed, plus `Reply-To` if required.

### 3.3. Why Is `Bcc` the Clear Illustration of Two Layers?

When sending:

```text
To: lan@example.org
Bcc: auditor@example.net
```

The recipient list passed to SMTP includes both `lan@example.org` and `auditor@example.net`. However, **the message delivered to Lan must not disclose the blind recipient list**. Under common sending behavior, the `Bcc` header is stripped from copies delivered to other recipients; other valid approaches may generate a separate copy for Bcc recipients.

Therefore, you cannot infer all actual recipients solely from `To:` and `Cc:` in a delivered raw message. When building raw MIME yourself or proxying mail, ensure Bcc hiding is handled properly; do not simply assume adding a `Bcc:` header line will automatically keep it secret.

### 3.4. Headers Are Not Free-Form Input

Vietnamese display names, Unicode subjects, or long header lines must be encoded and folded according to mail standards. The Jakarta Mail library handles most of this work when building a `MimeMessage`.

Do not concatenate headers using raw strings from user input. In particular, CR/LF characters in unsanitized values can lead to *header injection* in flawed custom implementations. Use APIs like `setFrom`, `setRecipients`, `setSubject`, and `MimeMessageHelper`, and validate address formats appropriately.

## 4. Message Body: Text, HTML, and MIME

The **body** is the content following the blank line that separates headers. The body can be plain text, HTML, or a hierarchy of MIME (Multipurpose Internet Mail Extensions) parts.

### 4.1. Plain-Text Body

```text
From: no-reply@example.com
To: lan@example.org
Subject: Account notification
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

Hello Lan,
Your account has been created.
```

Here, the body is the text after the blank line. The `Content-Type` header tells mail clients how to interpret the content and character set.

### 4.2. HTML Body

```text
From: no-reply@example.com
To: lan@example.org
Subject: Account notification
MIME-Version: 1.0
Content-Type: text/html; charset=UTF-8

<h1>Welcome</h1>
<p>Your account has been created.</p>
```

Even when HTML, the content is still only the **message body**, having no direct effect on `MAIL FROM` or the `RCPT TO` list. Complex HTML emails often include a plain-text alternative so mail readers and assistive tools have a fallback option.

### 4.3. Multipart Body with `multipart/alternative`

When sending both plain text and HTML, the body is a MIME structure containing parts separated by a boundary. Condensed example:

```eml
From: no-reply@example.com
To: lan@example.org
Subject: Account notification
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="demo-boundary"

--demo-boundary
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: 7bit

Hello Lan. Your account has been created.
--demo-boundary
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: 7bit

<html><body><p>Hello <strong>Lan</strong>.</p></body></html>
--demo-boundary--
```

Mail clients usually choose an appropriate representation. The `boundary` only separates MIME parts inside the **body**; it is neither the SMTP envelope nor the end-of-`DATA` marker.

Common combinations:

| MIME content type | Used When |
|---|---|
| `text/plain` | Plain text content. |
| `text/html` | HTML content. |
| `multipart/alternative` | Multiple representations of the same content, typically plain text and HTML. |
| `multipart/mixed` | Combines message content with independent parts such as file attachments. |
| `multipart/related` | Related parts needed to render one representation, such as HTML and embedded images referenced by CID. |

Each MIME part can have its **own headers**, such as `Content-Type`, `Content-Disposition`, `Content-ID`, and `Content-Transfer-Encoding`. Do not confuse them with message-level headers at the top of the email.

### 4.4. Body Encoding Differs from Transport Encryption

`Content-Transfer-Encoding: base64` or `quoted-printable` is a **data representation** so bytes can safely travel across mail infrastructure. It is not security encryption.

- **UTF-8 / charset:** defines how characters map to bytes.
- **Quoted-printable / base64:** defines how bytes are represented inside MIME content.
- **TLS on SMTP connections:** protects a single network hop's connection.
- **End-to-end encryption:** a separate problem, typically requiring technologies like S/MIME or OpenPGP.

Sender and recipient addresses still belong to the envelope/headers accordingly, whether the body uses HTML, base64, or attachments.

## 5. Example of a Complete SMTP Transaction

Example: the application sends a notification to Lan while also sending a blind copy to an archiving system. The bounce address is set separately.

```text
S: 220 smtp.example.com ESMTP
C: EHLO app.example.com
S: 250-smtp.example.com
S: 250-STARTTLS
S: 250 AUTH PLAIN LOGIN
C: STARTTLS
S: 220 Ready to start TLS
   [Both sides establish TLS connection]
   [Re-send EHLO and SMTP authenticate if required by server]
C: MAIL FROM:<bounce@example.com>
S: 250 2.1.0 Sender OK
C: RCPT TO:<lan@example.org>
S: 250 2.1.5 Recipient OK
C: RCPT TO:<archive@example.net>
S: 250 2.1.5 Recipient OK
C: DATA
S: 354 End data with <CRLF>.<CRLF>
C: From: "Demo App" <notice@example.com>
C: To: Lan <lan@example.org>
C: Reply-To: support@example.com
C: Subject: Account notification
C: MIME-Version: 1.0
C: Content-Type: text/plain; charset=UTF-8
C:
C: Hello Lan,
C: Your account is ready.
C: .
S: 250 2.0.0 Accepted for delivery
C: QUIT
S: 221 Bye
```

This is an illustrative transcript: actual server responses, capabilities, and AUTH steps depend on the provider. Notice the three addresses serve **three different roles**:

- `bounce@example.com` is the **envelope sender**, where non-delivery notices may be sent.
- `notice@example.com` is the **From header**, the address the recipient sees as the sender.
- `support@example.com` is **Reply-To**, the preferred address when the recipient clicks reply.

`archive@example.net` is in `RCPT TO` so the mail gets transferred there, yet **does not appear in the `To:` header** of the message delivered to Lan. The body starts only after the blank line and does not include the envelope lines.

## 6. Mapping Concepts to Spring Framework Mail

### 6.1. Choosing the Right API

| Spring/Jakarta Mail API | What It Helps the Application Control |
|---|---|
| `SimpleMailMessage` | Common mail fields and plain-text body; suitable for simple notifications. |
| `JavaMailSender` | Creates/sends `MimeMessage` or sends `SimpleMailMessage` to an SMTP server. |
| `MimeMessage` | Message content consisting of headers and MIME body. |
| `MimeMessageHelper` | Sets `From`, `To`, `Cc`, `Bcc`, `Reply-To`, `Subject`, text/HTML body, and attachments. |
| `JavaMailSenderImpl` | Sending implementation via Jakarta Mail; uses SMTP properties to configure connections and some envelope characteristics. |

**`MimeMessageHelper.setFrom(...)` sets the `From` header; do not mistake it for a standalone API to configure the envelope sender.** `setTo`, `setCc`, and `setBcc` build recipient headers/metadata that the mail layer uses to assemble the SMTP recipient list per Jakarta Mail mechanics.

### 6.2. Spring Boot Configuration

Spring Framework Mail can be used in plain Spring applications. The example below uses **Spring Boot** auto-configuration with the `spring-boot-starter-mail` dependency, as that is the common integration case:

```yaml
# application.yml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000
      "[mail.smtp.from]": bounce@example.com

app:
  mail:
    from: notice@example.com
    reply-to: support@example.com
```

Explanation:

- `spring.mail.host` and `port` select the SMTP server the application connects to.
- `mail.smtp.auth` and the STARTTLS properties govern authentication and connection security per server requirements.
- `mail.smtp.from` is a **Jakarta Mail SMTP property** commonly used to specify the `MAIL FROM` envelope address when sending through the corresponding SMTP transport.
- `app.mail.from` and `app.mail.reply-to` are **application-defined properties**, used to build the `From` and `Reply-To` headers in the code below.

Configuring `mail.smtp.from` at the mail sender level typically applies to sends using that configuration. If each message type needs a different envelope sender, you must design a per-message/transport selection mechanism; do not mutate shared properties on a singleton bean while multiple threads send concurrently.

Envelope/header addresses must be authorized by the SMTP provider. Real credentials should come from environment variables or a secret manager.

### 6.3. Building a Message with `MimeMessageHelper`

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class AccountNotificationMailService {
    private final JavaMailSender mailSender;
    private final String from;
    private final String replyTo;

    public AccountNotificationMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String from,
            @Value("${app.mail.reply-to}") String replyTo) {
        this.mailSender = mailSender;
        this.from = from;
        this.replyTo = replyTo;
    }

    public void sendAccountReady(String recipient) throws MessagingException {
        MimeMessage mimeMessage = mailSender.createMimeMessage();

        // multipart=true allows creating both text/plain and text/html.
        MimeMessageHelper helper =
                new MimeMessageHelper(mimeMessage, true, "UTF-8");

        // Message headers:
        helper.setFrom(from, "Demo App");
        helper.setTo(recipient);
        helper.setBcc("archive@example.net");
        helper.setReplyTo(replyTo);
        helper.setSubject("Account is ready");

        // Two parts representing the same content.
        helper.setText(
                "Hello! Your account is ready.",
                "<p>Hello! <strong>Your account is ready.</strong></p>"
        );

        mailSender.send(mimeMessage);
    }
}
```

With the example configuration:

1. `helper.setFrom(...)` creates the header `From: "Demo App" <notice@example.com>`.
2. `helper.setTo(...)` sets the displayed recipient. `helper.setBcc(...)` adds a blind recipient; the mail-sending layer handles delivering the email to these recipients.
3. `helper.setReplyTo(...)` sets the reply address without altering the SMTP envelope.
4. `helper.setText(plain, html)` sets the body using a MIME structure with both plain text and HTML.
5. `mailSender.send(mimeMessage)` hands off to the Jakarta Mail SMTP transport to transmit the message; in the example, `mail.smtp.from` sets the envelope sender to `bounce@example.com`.

The program only sets essential headers. Other headers such as `Date`, `Message-ID`, or MIME fields may be added/completed by the library before sending.

When `send(...)` finishes successfully, that normally only confirms the SMTP submission completed per server response. Onward delivery to the destination mailbox lies outside what this API directly confirms.

### 6.4. When to Use `SimpleMailMessage`?

If sending plain text only, complexity can be reduced:

```java
import org.springframework.mail.SimpleMailMessage;

SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("notice@example.com");
message.setTo("lan@example.org");
message.setReplyTo("support@example.com");
message.setSubject("Account notification");
message.setText("Your account is ready.");

mailSender.send(message);
```

`SimpleMailMessage` is convenient for simple content, but does not directly support complex HTML/attachment structures like `MimeMessage`. Setting the envelope sender still depends on the SMTP transport configuration; `setFrom(...)` is the address in the message header.

## 7. Real-World Points Often Confused

### 7.1. Setting `From` Successfully Does Not Guarantee Permission to Send

The `From` header can be set in code, yet the SMTP provider may restrict which domains or addresses are permitted. Authenticating an SMTP account does not automatically allow sending on behalf of arbitrary domains. Receiving mail software also evaluates the authenticity of the displayed address.

Three related mechanisms to know:

| Mechanism | Data Used | What It Helps Verify |
|---|---|---|
| **SPF** | Sending server IP and SMTP-layer identities such as the envelope sender domain | Whether the sending server is authorized by the relevant domain. |
| **DKIM** | Cryptographic signature over selected headers and body of the message | Whether the signed content is intact and the signature matches the signing domain. |
| **DMARC** | `From` domain in headers and SPF/DKIM results with alignment rules | Whether authentication results align with the displayed `From` domain per policy. |

Thus, `MAIL FROM` and `From:` differing can be completely valid. However, if domains are misconfigured, emails may be judged as spoofed or rejected. SPF/DKIM/DMARC belong to domain and mail service configuration, not just adding an arbitrary header in Spring.

### 7.2. Changing `Reply-To` Does Not Change Where Bounces Go

If a message has:

```text
MAIL FROM:<bounce@example.com>
From: billing@example.com
Reply-To: support@example.com
```

- The user sees the email from `billing@example.com`.
- When the user replies, the new email is typically sent to `support@example.com`.
- If a mail server sends an automated failure report regarding the original transport session, the address is typically `bounce@example.com`.

These are three separate workflows; header addresses alone are insufficient to reconstruct the full behavior.

### 7.3. `Return-Path` Is Not How You Set the Envelope

When reading a received message, you may see:

```text
Return-Path: <bounce@example.com>
Received: from relay.example.com ...
From: "Demo App" <notice@example.com>
```

`Return-Path` is typically added to the message when mail is delivered, based on the reverse-path present in SMTP. It is a **trace in the received message**. If you want to control the outgoing envelope with the Jakarta Mail SMTP transport, use the appropriate envelope mechanism, such as `mail.smtp.from`, rather than setting `Return-Path` yourself and hoping the server uses it.

### 7.4. `.eml` Files Do Not Show the Full Envelope

An email file can store full headers and body, including `Received` or `Return-Path` traces if added by systems. However, it typically **does not store each `RCPT TO` command** used during sending. With Bcc emails, reading only `.eml` may not identify all actual recipients. You must trace SMTP logs or provider metadata to know for sure.

### 7.5. Headers and Body Can Both Be Large

Attachments belong to the MIME body and are typically base64-encoded, causing the transmitted size to be larger than the original file. SMTP servers enforce limits on message size, recipient counts, and sending rates. These limits apply to the transfer transaction, not merely the subject length.

### 7.6. Security When Inspecting Raw Emails

SMTP logs and raw messages can contain personal addresses, sensitive content, verification codes, attachments, and even authentication traces if debugging is misconfigured. Enable trace/debug logging only in appropriate environments, redact secrets, and control log access.

## 8. Quick Troubleshooting Reference Table

| Observation | What to Check First? | Reason |
|---|---|---|
| Email shows wrong sender name | `From` header / display name | This is display information. |
| Replies go to the wrong address | `Reply-To` header, then `From` | Mail clients determine reply targets from headers. |
| Bounces go to the wrong mailbox | SMTP `MAIL FROM`, `Return-Path` trace, and relay config | Transport error reporting uses the envelope sender. |
| Bcc does not receive the email | Message recipient list and `RCPT TO`/SMTP logs | Blind recipients must still be passed to SMTP. |
| Other recipients can see Bcc | How the message is built/written/relayed and `Bcc` header removal | This is a recipient disclosure bug to fix at the construction/sending layer. |
| HTML renders as raw markup | MIME `Content-Type`, how body is built | Client did not interpret the body as HTML properly. |
| Accented/Vietnamese text has garbled characters | Charset, `Content-Transfer-Encoding`, and header encoding | Usually a MIME formatting issue, not an envelope issue. |
| Server reports invalid recipient | `RCPT TO` and SMTP response | Error occurred when passing recipient address via transport. |
| `send(...)` succeeds yet nothing in Inbox | SMTP acceptance, relay logs, bounces, Spam | SMTP acceptance is not delivery to the mailbox. |

## 9. Summary Through a Side-by-Side Comparison

Suppose the system sends an email with these values:

```text
AUTH username: service-account
MAIL FROM:     bounce@example.com
RCPT TO:       lan@example.org
RCPT TO:       archive@example.net

From:          Demo App <notice@example.com>
To:            Lan <lan@example.org>
Reply-To:      support@example.com
Subject:       Account notification
Content-Type:  multipart/alternative; ...
Body:          text/plain + text/html
```

Read it in order:

- **AUTH** is the identity used for authorization to send via SMTP.
- **MAIL FROM** is the envelope sender used for transport and error handling.
- **RCPT TO** are the addresses the server is asked to transfer the message to, including blind recipients.
- **From, To, Reply-To, Subject** are headers describing the message and guiding mail client behavior.
- **Content-Type** explains how to interpret the body; the body holds the content and MIME parts.

In Spring Framework Mail, message-building APIs let developers represent **headers and body** cleanly, while `JavaMailSender` and the SMTP transport transfer the email with an **envelope** determined by the recipient list and sending configuration. Separating these two layers clearly helps you understand Bcc behavior, trace bounces, set up domain security, and diagnose delivery issues.
