# EHLO, HELO, MAIL FROM, RCPT TO, and DATA in SMTP

## 1. The Five Foundational Commands of an SMTP Session

**Simple Mail Transfer Protocol (SMTP)** is the protocol used to submit and relay email between a mail-sending application and a mail server, or between mail servers themselves. In an application using **Spring Framework Mail**, developers usually call `JavaMailSender.send(...)` instead of handling each command directly. Even so, understanding SMTP commands is important for distinguishing the connection setup phase, sender/recipient declaration, and content transmission; it also helps read SMTP server logs and error responses accurately.

The five core commands:

| Command | Role | State transition |
| --- | --- | --- |
| `EHLO` | Greets the server using Extended SMTP (ESMTP) and receives supported extensions | Begins an ESMTP conversation and retrieves the server's capability list |
| `HELO` | Greets the server using basic SMTP | Establishes a traditional SMTP conversation |
| `MAIL FROM` | Specifies the **envelope sender**, also known as the reverse-path | Starts a message delivery transaction |
| `RCPT TO` | Specifies an **envelope recipient**; may be called multiple times | Adds each recipient accepted by the server |
| `DATA` | Transmits the email's **headers and body** | After a `354` response, transmits content lines and terminates with `CRLF . CRLF` |

The key point is distinguishing an **SMTP session** from a **single email delivery transaction**. One connection can be greeted once with `EHLO` and then execute multiple separate transactions, each typically structured as:

~~~text
MAIL FROM:<sender@example.com>
RCPT TO:<recipient-1@example.net>
RCPT TO:<recipient-2@example.net>
DATA
[Headers, blank line, body/MIME]
<CRLF>.<CRLF>
~~~

`EHLO` or `HELO` usually precedes transactions. `STARTTLS` and `AUTH` commands may appear after `EHLO` to upgrade the connection and authenticate per server policy. The session ends with `QUIT`. The lines above show the high-level structure; during execution, the client must read and handle **the server's response after each step**.

## 2. Why Does Command Order Matter?

SMTP is a stateful conversational protocol. You cannot send `DATA` immediately upon TCP setup and expect the server to deduce the sender and recipients on its own. A client typically must:

1. Open a TCP connection; wait for the server to send the `220` greeting.
2. Send `EHLO` (or `HELO` when appropriate); read the response.
3. If needed and supported, perform `STARTTLS`, greet again; then `AUTH`.
4. Send `MAIL FROM` to open a new transaction.
5. Send one or more `RCPT TO` commands; track each accepted or rejected address.
6. When there is a valid recipient, send `DATA`; wait for `354` and then send the entire message.
7. End the data; wait for the final response, typically `250` when the server accepts the message.
8. Start the next transaction or send `QUIT` to close the session.

~~~mermaid
sequenceDiagram
    participant App as Spring / Jakarta Mail SMTP client
    participant Server as SMTP submission server
    App->>Server: TCP connection
    Server-->>App: 220 Ready
    App->>Server: EHLO app.example.com
    Server-->>App: 250 + ESMTP extensions
    opt TLS required or selected
        App->>Server: STARTTLS
        Server-->>App: 220 Start TLS
        Note over App,Server: TLS handshake
        App->>Server: EHLO app.example.com
        Server-->>App: 250 + new capabilities
    end
    opt Server requires authentication
        App->>Server: AUTH via supported mechanism
        Server-->>App: Authentication result
    end
    App->>Server: MAIL FROM:<sender@example.com>
    Server-->>App: 250 Sender accepted
    App->>Server: RCPT TO:<lan@example.net>
    Server-->>App: 250 Recipient accepted
    App->>Server: DATA
    Server-->>App: 354 Continue
    App->>Server: Headers + body + CRLF . CRLF
    Server-->>App: 250 Accepted for delivery
    App->>Server: QUIT
    Server-->>App: 221 Closing
~~~

In the example, `220`, `250`, `354`, and `221` are **SMTP reply codes**. They are not HTTP status codes. Code `503 Bad sequence of commands` may appear when the client sends a command at the wrong stage of the transaction.

## 3. EHLO: Greeting and Negotiating Server Capabilities

**`EHLO`** is the greeting command of **Extended SMTP (ESMTP)**. The client passes its hostname or a valid address literal to introduce itself:

~~~text
C: EHLO app.example.com
S: 250-smtp.example.net Hello app.example.com
S: 250-SIZE 10485760
S: 250-8BITMIME
S: 250-STARTTLS
S: 250-PIPELINING
S: 250 AUTH PLAIN LOGIN
~~~

Here `C:` is a line sent by the client; `S:` is a line returned by the server. Note the multi-line response:

- `250-` with a hyphen indicates **more response lines follow**.
- `250 ` with a space indicates **the final line** of that response.
- The client must read the complete response to learn all extensions before proceeding.

Common capabilities:

| Extension | Meaning |
| --- | --- |
| `SIZE 10485760` | Server advertises the message size limit in octets; e.g., 10,485,760 octets |
| `STARTTLS` | Supports upgrading the current SMTP connection to TLS |
| `AUTH PLAIN LOGIN` | Advertises the SMTP authentication mechanisms available in the current context |
| `PIPELINING` | Allows sending certain commands consecutively without waiting for each reply, per extension rules |
| `8BITMIME` | Supports transmitting bodies containing 8-bit octets under the extension's conditions |
| `SMTPUTF8` | Supports internationalized SMTP subject to the extension's constraints |
| `DSN` | Supports delivery status notification parameters |
| `CHUNKING` | Supports the `BDAT` command as an alternative to standard `DATA` transfer |

A server may advertise a different set, and not every extension appears in every session. A client must not assume all the extensions above are present by default. For example, if the server does not advertise `SMTPUTF8`, the client cannot arbitrarily request sending internationalized addresses that require that extension.

### 3.1. Is the Name in EHLO the Mail Sender?

No. In:

~~~text
EHLO app.example.com
~~~

`app.example.com` is the identity of the **connecting host/client**, not the sender's email address. It differs from `MAIL FROM:<bounce@example.com>` and the `From: notifications@example.com` header inside the message content.

Normally the client uses an appropriate fully qualified domain name (FQDN); when a suitable name cannot be used, the protocol also specifies an address literal form. You should not put a user's email address into the EHLO field as a way to set the sender.

### 3.2. EHLO After STARTTLS

A mail submission session over port 587 may proceed as follows:

~~~text
S: 220 smtp.example.net ESMTP ready
C: EHLO app.example.com
S: 250-smtp.example.net
S: 250-STARTTLS
S: 250 SIZE 10485760
C: STARTTLS
S: 220 Ready to start TLS
   [TLS handshake complete]
C: EHLO app.example.com
S: 250-smtp.example.net
S: 250-SIZE 10485760
S: 250 AUTH PLAIN LOGIN
   [Client authenticates; auth details omitted]
~~~

After STARTTLS succeeds, the client **must discard previous EHLO capabilities and send EHLO again**. This is important because the server may advertise a different set of capabilities once the connection is encrypted. Some servers only advertise `AUTH` after TLS is established.

`STARTTLS` means *upgrading* an already open connection. It differs from TLS right from the start of the connection (implicit TLS), commonly used on port 465. Use the exact mechanism required by the SMTP provider; never send passwords over a channel that does not meet security requirements.

## 4. HELO: Traditional SMTP Greeting

**`HELO`** is the basic greeting:

~~~text
S: 220 smtp.example.net SMTP ready
C: HELO app.example.com
S: 250 smtp.example.net Hello app.example.com
~~~

Comparison:

| Aspect | `EHLO` | `HELO` |
| --- | --- | --- |
| Purpose | Greets using ESMTP and discovers extensions | Greets using basic SMTP |
| Success response | May have multiple `250-...` lines listing capabilities | Usually returns a single `250` line |
| STARTTLS / AUTH / SIZE | Can be advertised via EHLO | HELO has no extension advertisement mechanism |
| Modern applications | Usually tried first | Used for compatibility when appropriate |

A client may fall back from `EHLO` to `HELO` when connecting to an older SMTP server that does not support ESMTP. However, falling back is no reason to bypass mandatory encryption, authentication, or required extensions. If the application requires STARTTLS and the server does not support it, an appropriate error should be raised.

In `JavaMailSender`, the greeting step is handled by the Jakarta Mail SMTP transport based on configuration and server responses; business services do not need to send `EHLO`/`HELO` strings themselves.

## 5. MAIL FROM: Opening a Transaction and Identifying the Envelope Sender

After greeting and completing any required security steps, the client starts a transaction:

~~~text
C: MAIL FROM:<bounce@example.com>
S: 250 2.1.0 Sender OK
~~~

`MAIL FROM` declares the **reverse-path** or **envelope sender**. It serves mail transport and delivery failure notification (bounce) handling. This is **SMTP envelope** information and does not have to match the `From` address displayed in an MUA.

For example, a message may contain different addresses:

~~~text
SMTP envelope:
    MAIL FROM:<bounce@example.com>

Message headers:
    From: "Weekly Reports" <reports@example.com>
    Reply-To: support@example.com
~~~

| Field | Role |
| --- | --- |
| `MAIL FROM` | Envelope address used during delivery and error handling |
| `From:` | Author/sender address or name inside the message visible to the recipient |
| `Reply-To:` | Preferred address when the recipient chooses "Reply" |

Bulk email systems often use a dedicated bounce address, whereas the `From:` header uses the service name. This difference by itself does not indicate whether a message is legitimate or spoofed; account authentication, sending permissions, and domain protection mechanisms like SPF/DKIM/DMARC each play distinct roles.

### 5.1. Extended MAIL FROM Parameters

If EHLO advertises `SIZE`, the client can send the size parameter:

~~~text
C: MAIL FROM:<bounce@example.com> SIZE=4096
S: 250 2.1.0 Sender accepted
~~~

`4096` is an example of the message's **octet** count per extension rules, not the length of a Java `String`. Parameters such as `BODY=8BITMIME` and `SMTPUTF8` also depend on extensions and their corresponding conditions.

The empty reverse-path syntax:

~~~text
C: MAIL FROM:<>
~~~

is used for certain delivery status notifications to avoid creating bounce loops. It is not a way for an application to arbitrarily send anonymous mail; nor does it mean the `From:` header inside the message should be empty.

If `MAIL FROM` is not accepted, the transaction cannot proceed to send recipients and data as a valid message. For instance, the server may reject it because the account is not permitted to use that envelope address.

## 6. RCPT TO: One Command per Delivery Recipient

After `MAIL FROM`, the client specifies recipients:

~~~text
C: RCPT TO:<lan@example.net>
S: 250 2.1.5 Recipient OK
C: RCPT TO:<team@example.net>
S: 250 2.1.5 Recipient OK
C: RCPT TO:<unknown@example.net>
S: 550 5.1.1 Mailbox unavailable
~~~

Each address receives its **own response**. The first two recipients are accepted; the third recipient is rejected. One email can have multiple `RCPT TO` commands because the SMTP envelope routes the message to each destination.

### 6.1. How Does RCPT TO Differ from To, Cc, and Bcc?

Suppose the mail composition UI shows:

~~~text
To:  lan@example.net
Cc:  team@example.net
Bcc: quan@example.org
~~~

The envelope can carry all three destinations:

~~~text
RCPT TO:<lan@example.net>
RCPT TO:<team@example.net>
RCPT TO:<quan@example.org>
~~~

Meanwhile, the headers inside `DATA` for the copy sent to Lan and the team may contain only:

~~~text
To: lan@example.net
Cc: team@example.net
~~~

Bcc addresses must be handled so they are not leaked to recipients who should not see them; how Bcc headers are generated and distributed depends on the MUA/mail system. **The `To:` header is not the sole delivery list**: the transport server relies on accepted `RCPT TO` commands. Writing a `To: ...` line in the body will not cause SMTP to send mail to that address either.

### 6.2. Partially Rejected Recipients

| Response | Common interpretation | Meaning for the client |
| --- | --- | --- |
| `250` | Recipient accepted | Can add more recipients or proceed to `DATA` |
| `251` | User not local; server agrees to forward | Treat per server success rules |
| `450` | Mailbox temporarily unavailable | Can consider retrying |
| `451` | Temporary processing error | Needs an appropriate retry policy |
| `550` | Permanent rejection: may be address or policy | Check enhanced status code and message |
| `553` | Mailbox name/address not allowed | Check syntax and sending permissions |

**You cannot always infer `550` = "recipient does not exist"**: many servers return `550` due to policy or relay denial. Read both the enhanced status code (e.g., `5.1.1`, `5.7.1`) and the explanation returned by the server.

If at least one valid `RCPT TO` remains, the client can proceed with `DATA` for the accepted set of recipients. If all are rejected, the client should not proceed to send data for a transaction with no destinations; typically `RSET` or closing the session is needed. Per-recipient outcomes matter when designing error reporting and retries to avoid sending duplicates to recipients who were already accepted.

## 7. DATA: Transmitting Message Headers and Body

Once at least one recipient is accepted, the client sends:

~~~text
C: DATA
S: 354 End data with <CRLF>.<CRLF>
~~~

Code `354` is an intermediate response asking the client to send the content. From this point, the server reads the **message data** consisting of header lines, a blank separator line, and the body. Example:

~~~text
C: DATA
S: 354 Continue
C: From: Reports <reports@example.com>
C: To: lan@example.net
C: Subject: Weekly report
C: MIME-Version: 1.0
C: Content-Type: text/plain; charset=us-ascii
C:
C: The weekly report is ready.
C: .
S: 250 2.0.0 Message accepted for delivery
~~~

The final line containing only a dot in the transcript represents **`CRLF . CRLF`**, which is how SMTP marks the end of content. SMTP uses the CRLF line-ending pair on the wire. After the terminator, the server returns a final response confirming acceptance or rejection of the message.

### 7.1. DATA Transmits Headers Too, Not Just User-Typed Body Text

A structured email message consists of:

1. **Headers**: e.g., `From:`, `To:`, `Subject:`, `Date:`, `Message-ID:`, and MIME fields.
2. **Blank line**: the boundary between headers and body.
3. **Body**: plain text, HTML, or MIME multipart content, possibly containing attachments.

For HTML emails and attachments, Java/Jakarta Mail builds `multipart/alternative`, `multipart/mixed`, boundaries, content types, and appropriate encodings. The `DATA` command merely transports the message stream; it does not understand what a PDF or HTML file means without descriptive MIME headers.

### 7.2. Dot-Stuffing: Why Must One Dot Become Two?

Because a line containing only `.` signals the end of `DATA`, a body line that **actually begins with a dot** must have an extra dot prepended by the client before transmission:

| Original body line | Line transmitted over DATA |
| --- | --- |
| `Hello` | `Hello` |
| `.Warning` | `..Warning` |
| `..Two dots` | `...Two dots` |
| `.` | `..` |

The receiving server strips the extra dot when restoring the data. This mechanism is called **dot-stuffing** or **SMTP transparency**. In Spring Mail, developers do **not** manually add dots to `helper.setText(...)`; Jakarta Mail's SMTP transport handles wire formatting.

Example of a two-line body:

~~~text
Actual body:
.Read this first
See the report

When transmitted in DATA:
..Read this first
See the report
.
~~~

The line `..Read this first` belongs to the content; only the final line containing `.` ends the transaction. Note that the specification defines exact CRLF and byte values; text examples simplify how these bytes are depicted.

### 7.3. Does Server Acceptance of DATA Mean Delivered to the Inbox?

**Not yet.** The response:

~~~text
S: 250 2.0.0 Queued as ABC123
~~~

only indicates that the server has **accepted the message into its processing/delivery responsibility**. This is the result of submitting the message to the server and does not prove that:

- The email is in the recipient's Inbox;
- The email was not filtered into spam;
- The recipient has read the message;
- There is no longer a possibility of failure at a later transport hop.

The message may be delayed in transit, rejected at a downstream step, or generate a DSN/bounce. Applications that want to track final outcomes need corresponding signals from the provider (such as webhooks/status APIs) or handling for subsequently generated error responses.

### 7.4. When Is DATA Not Seen?

If the server advertises the ESMTP **`CHUNKING`** extension, a supporting client may use `BDAT` to transfer the body in chunks instead of `DATA`. Therefore, when reading a trace, do not conclude that the application failed to send mail just because the `DATA` string is missing if both sides are using another extension mechanism.

## 8. Complete SMTP Transcript for Step-by-Step Comparison

The example session below assumes the server supports TLS and has an authentication mechanism after TLS. Text messages and enhanced codes are illustrative; real systems may vary.

~~~text
S: 220 smtp.example.net ESMTP ready
C: EHLO app.example.com
S: 250-smtp.example.net
S: 250-SIZE 10485760
S: 250-STARTTLS
S: 250 8BITMIME

C: STARTTLS
S: 220 Ready to start TLS
   [TLS handshake completed]

C: EHLO app.example.com
S: 250-smtp.example.net
S: 250-SIZE 10485760
S: 250 AUTH PLAIN LOGIN
   [SMTP authentication completed; credentials omitted]

C: MAIL FROM:<bounce@example.com>
S: 250 2.1.0 Sender accepted
C: RCPT TO:<lan@example.net>
S: 250 2.1.5 Recipient accepted
C: RCPT TO:<unknown@example.net>
S: 550 5.1.1 Mailbox unavailable

C: DATA
S: 354 End data with <CRLF>.<CRLF>
C: From: Reports <reports@example.com>
C: To: lan@example.net
C: Subject: Weekly report
C: MIME-Version: 1.0
C: Content-Type: text/plain; charset=us-ascii
C:
C: The report is ready.
C: ..Please read section 2.
C: .
S: 250 2.0.0 Queued as ABC123

C: QUIT
S: 221 2.0.0 Goodbye
~~~

Walkthrough:

- The first `EHLO` receives the `STARTTLS` extension; after TLS, `EHLO` must be sent again.
- `MAIL FROM` is accepted, thereby opening the transaction.
- Recipient `lan@example.net` is accepted; `unknown@example.net` is rejected.
- `DATA` transmits the message for the **accepted** recipients and does not "fix" the rejected recipient.
- The line `..Please read section 2.` is the dot-stuffed form of content starting with a dot.
- `250` after the terminating `.` means the server accepted it for further processing; `QUIT` closes the connection.

A session can send another email transaction over this connection before `QUIT`, but it must declare `MAIL FROM` and the recipients for the new transaction.

## 9. How Does the SMTP Envelope Differ from Message Headers?

This is a particularly important boundary when debugging `From`, `To`, and `Bcc` fields in Spring Mail.

~~~text
SMTP ENVELOPE (control exchange)
  MAIL FROM:<bounce@example.com>
  RCPT TO:<lan@example.net>
  RCPT TO:<quan@example.org>

MESSAGE (transmitted inside DATA)
  From: Reports <reports@example.com>
  To: lan@example.net
  Reply-To: support@example.com
  Subject: Weekly report

  Here is your weekly report.
~~~

| Question | Basis for the answer |
| --- | --- |
| Who is the SMTP system delivering the message to? | The `RCPT TO` addresses accepted by the server |
| What is the envelope address for delivery failure replies? | `MAIL FROM` |
| Which sender name does the recipient see? | The `From:` header inside `DATA` |
| Where does a reply go when clicking Reply? | The `Reply-To:` header if present; otherwise usually based on `From:` |
| Where do subject, text, HTML, and attachments reside? | Inside the message headers/body/MIME transmitted via `DATA` |
| Must Bcc addresses appear in headers visible to recipients? | No; the envelope can contain Bcc recipients while headers remain appropriately hidden |

This distinction explains why a message with a `To:` field still requires `RCPT TO` commands, and why setting `From:` inside the content does not mean the SMTP reverse-path has changed.

## 10. Reading Response Codes and Handling Errors per Command

SMTP uses three-digit response codes. The first digit indicates the outcome category:

| Category | Basic meaning | Examples |
| --- | --- | --- |
| `2xx` | Success | `220` server ready; `250` command accepted; `221` closing connection |
| `3xx` | Server waiting for client to supply more data | `354` waiting for `DATA` message payload |
| `4xx` | Temporary error | `421` service unavailable; `450` temporary mailbox error |
| `5xx` | Permanent error or unacceptable request | `500` syntax error; `503` bad sequence; `550` rejected |

Specific scenarios:

**EHLO succeeds without STARTTLS.** If configuration requires TLS, the client must stop or raise an error and not send authentication credentials over a connection that fails policy.

**MAIL FROM receives `550`/`553`.** The server may disallow the envelope address, the account may lack sending permission, or the syntax is invalid. You cannot conclude a recipient error because the `RCPT TO` step has not been reached.

**RCPT TO receives `450`.** This is usually a temporary error; the application can schedule a retry per policy rather than marking the address permanently invalid.

**RCPT TO receives `550`.** Either the recipient does not exist or the server rejected it due to policy. Read the enhanced status code and response details.

**DATA receives `354` and then returns `552` or `554` after the terminator.** The server allowed transmission to start but **did not accept the final message**. Never mark an email as sent just because `354` was seen.

**Connection lost before the final DATA response.** The client may not know whether the server recorded the message. Blind retrying risks duplicate sends. For critical workflows, design a request identifier and send-state tracking mechanism to handle uncertain outcomes.

### 10.1. RSET and QUIT Help Control Transactions

`RSET` aborts the state of the **current transaction**, such as the chosen sender and recipients, while normally keeping the SMTP session open. The client can start over with `MAIL FROM`.

~~~text
C: MAIL FROM:<bounce@example.com>
S: 250 OK
C: RCPT TO:<invalid@example.net>
S: 550 Recipient rejected
C: RSET
S: 250 Reset OK
C: MAIL FROM:<bounce@example.com>
S: 250 OK
~~~

`QUIT` requests closing the session and the server typically returns `221`. `RSET` does not mean "recall an already sent email", because a message accepted in a previous transaction is not deleted just by an `RSET` in a subsequent transaction.

## 11. Connection to Spring Framework Mail

When using **`JavaMailSender`**, the application works with email objects; the Jakarta Mail SMTP transport handles the underlying SMTP session.

~~~mermaid
flowchart LR
    A["Spring service"] --> B["JavaMailSender + MimeMessage"]
    B --> C["Jakarta Mail SMTP transport"]
    C --> D["EHLO / HELO"]
    D --> E["MAIL FROM"]
    E --> F["RCPT TO for each recipient"]
    F --> G["DATA with headers + body"]
    G --> H["SMTP server accepts"]
~~~

| In Spring code | Corresponding responsibility |
| --- | --- |
| Configuring `host`, `port`, TLS, auth | Establishes connection and SMTP negotiation, including `EHLO`, possibly `STARTTLS` and `AUTH` |
| `MimeMessageHelper.setFrom(...)` | Sets the `From:` header; the envelope sender may be derived from the message or separate transport config |
| `setTo(...)`, `setCc(...)`, `setBcc(...)` | Prepares message recipients so the transport generates `RCPT TO` when sending |
| `setSubject(...)`, `setText(...)`, `addAttachment(...)` | Builds header/body/MIME content transmitted inside `DATA` |
| `mailSender.send(message)` | Triggers connection/transport execution and receives server responses or errors |

Not every setter on `MimeMessageHelper` immediately sends an SMTP command: they mainly mutate the in-memory message object; transport begins when actually sending.

### 11.1. Example of Sending a Message via JavaMailSender

~~~java
package com.example.mail;

import java.nio.charset.StandardCharsets;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class ReportMailService {

    private final JavaMailSender mailSender;

    public ReportMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReport(String recipient, String text) {
        MimeMessage message = mailSender.createMimeMessage();

        try {
            MimeMessageHelper helper = new MimeMessageHelper(
                    message, false, StandardCharsets.UTF_8.name());
            helper.setFrom("reports@example.com");
            helper.setTo(recipient);
            helper.setSubject("Weekly report");
            helper.setText(text, false); // plain text
        } catch (MessagingException ex) {
            throw new IllegalStateException("Cannot prepare email", ex);
        }

        mailSender.send(message);
    }
}
~~~

With `sendReport("lan@example.net", "Your report is ready")`:

1. The service prepares a `MimeMessage` containing From, To, Subject, and body.
2. `JavaMailSender` uses the configured Jakarta Mail transport to open a connection to the SMTP server.
3. The transport performs `EHLO`, negotiates capabilities, and handles security/authentication if needed.
4. The transport declares `MAIL FROM`, `RCPT TO`, and transmits the message via `DATA` or an appropriate extension.
5. If the server rejects or the connection fails, Spring Mail may throw runtime exceptions in the `MailException` hierarchy, such as `MailAuthenticationException` or `MailSendException`.

This snippet only illustrates Spring Mail interaction. In real applications, the `From` address must be authorized, client-supplied values must be validated, and the system needs anti-abuse policies, rate limits, and appropriate retries. A `MessagingException` when building the message differs from a transport failure at `send(...)`.

### 11.2. SMTP Submission Configuration with Spring Boot

In Spring Boot with `spring-boot-starter-mail`, a sample configuration:

~~~yaml
spring:
  mail:
    host: smtp.example.net
    port: 587
    username: smtp-user-from-environment
    password: smtp-secret-from-environment
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 5000
      mail.smtp.writetimeout: 5000
~~~

The `username`/`password` fields here are **illustrative values**, not usable login credentials; real deployments must obtain credentials from environment variables or a secrets store and never commit them to the repository.

- Port **587** is typically used for SMTP submission with STARTTLS per provider policy.
- `mail.smtp.starttls.enable` allows upgrading the connection when the server supports it.
- `mail.smtp.starttls.required` requires STARTTLS to succeed before proceeding.
- `mail.smtp.auth` enables SMTP authentication when required by the server and an account is configured.
- Timeouts are in milliseconds, preventing network operations from hanging indefinitely.

The `spring.mail.*` properties are **Spring Boot** configuration conveniences. In plain Spring Framework, you can declare a `JavaMailSenderImpl` bean yourself with Jakarta Mail properties. If the provider requires implicit TLS over port **465**, configure the corresponding TLS mode rather than applying port 587 STARTTLS settings as-is.

### 11.3. Do You Need to Implement EHLO, MAIL FROM, and DATA Yourself?

Normally **no**. Jakarta Mail handles:

- Reading the `220` greeting and multi-line ESMTP responses;
- `EHLO`, `HELO`, and extension capabilities;
- STARTTLS, re-greeting, and authentication mechanisms;
- Generating the envelope sender, recipients, and invoking `DATA` or extended mechanisms;
- CRLF, MIME encoding, dot-stuffing, and the end-of-data line;
- Server responses, rejection statuses, and network errors.

The Spring layer should focus on authorized sender identities, email content, user permissions, sending timing, load limits, and how transaction status is reported. When investigating sending errors, look at the SMTP stage where the failure occurred instead of rewriting the protocol.

## 12. Safe Operations and Interpreting Send Status

### 12.1. Distinguishing Accepted, Delivered, and Read

`250` after `DATA` normally only means **server accepted/queued**, not **delivered to mailbox**, and certainly not **read by user**. Actual delivery status can depend on downstream relay hops, spam policies, or provider-specific outcomes. To display full status, the application needs corresponding information sources beyond the initial SMTP response.

### 12.2. Handling Temporary and Permanent Errors

The `4xx` group typically warrants retrying after a reasonable delay; the `5xx` group typically requires reviewing the address, content, sending permissions, or configuration. Do not retry infinitely or resend to the entire recipient list if only one recipient was rejected. A business request should have an identifier, retry limits, and per-destination result tracking if needed.

### 12.3. Do Not Let SMTP Logs Leak Data

When enabling Jakarta Mail debug/protocol tracing, observed data can contain email addresses, headers, message bodies, and authentication details depending on the mechanism and log level. Enable it only to the extent needed, restrict access, mask sensitive data, and avoid leaving credentials/tokens in logs or documentation.

### 12.4. Unicode in the Body and SMTPUTF8 Are Two Separate Issues

Vietnamese body text can be represented via MIME with `charset=UTF-8` and an appropriate encoding. However, internationalized email addresses require `SMTPUTF8` in certain cases: merely declaring a charset for the body does **not** mean all forms of internationalized addresses are allowed over SMTP.

### 12.5. Comprehension Check Questions

**"If the email already has To, why does SMTP still need RCPT TO?"**  
`To:` is a message header, whereas `RCPT TO` is the delivery address in the envelope. The two lists do not have to match, especially with Bcc.

**"If the server returns 354, can sending be considered successful?"**  
No. `354` only asks to transmit data. You must complete the message and read the response after the terminator.

**"If EHLO fails, should you always send HELO and continue?"**  
No. HELO is only a compatibility fallback when appropriate; requirements for TLS, authentication, and extensions must still be met.

**"Is MAIL FROM the same as From inside the email?"**  
Not necessarily. `MAIL FROM` is the reverse-path in the SMTP envelope; `From:` is the displayed header inside the message.

**"Is Spring JavaMailSender an SMTP server?"**  
No. It is an application-side API calling Jakarta Mail to **connect to a server** and send messages. The SMTP server infrastructure is responsible for accepting and relaying.

## 13. Applying This in a Real-World Scenario

A Spring service sends weekly reports to three members. The backend creates a `MimeMessage` with an authorized sender address, subject, and attachment. When calling `send(...)`, the SMTP transport sends `EHLO` to learn server capabilities, performs TLS/authentication per configuration, opens a `MAIL FROM` transaction, issues each `RCPT TO`, and finally transfers the MIME message via `DATA`.

If one recipient is rejected while the other two are accepted, the application should record the partial-send situation according to library behavior and system sending policy. If the server returns `250` after `DATA`, the application can record the status "provider accepted the send request" while continuing to track delivery outcomes if the business workflow requires it.

**Sequence to remember:** `EHLO/HELO` establishes the conversation, `MAIL FROM` identifies the envelope sender, `RCPT TO` determines delivery destinations, and `DATA` transmits the email itself. Understanding each boundary helps troubleshoot SMTP errors, avoid confusing email headers with the SMTP envelope, and use Spring Framework Mail accurately.
