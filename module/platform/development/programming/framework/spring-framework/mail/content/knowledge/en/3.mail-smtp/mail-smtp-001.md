# SMTP Session from Connection to Session Close

When a Spring application calls `JavaMailSender.send(...)`, developers usually only see the "send email" operation. At the network layer, that process consists of multiple ordered steps: opening a connection, receiving the SMTP greeting, negotiating server capabilities, establishing TLS, authenticating (if required), declaring the sender and recipients, transmitting the message content, receiving the result, and closing the connection.

Understanding the **SMTP session lifecycle** helps diagnose errors accurately: a connection error differs from a login error, a recipient error differs from a content error, and an "accepted" response is completely different from a "delivered to Inbox" notification.

## 1. Where Does SMTP Operate in Spring Framework Mail?

**SMTP (Simple Mail Transfer Protocol)** is the protocol for sending and relaying electronic mail. In a Spring application, the typical sending flow is:

```text
Spring Application
    |
    | JavaMailSender.send(...)
    v
JavaMailSenderImpl
    |
    | Jakarta Mail / SMTP Transport
    v
SMTP submission server or SMTP relay
    |
    | queuing and relaying per server policy
    v
Receiving email infrastructure -> recipient's mailbox
```

An application normally connects to a **configured SMTP host**, such as `smtp.example.com`. It does not need to look up MX records itself for each recipient address when sending through an SMTP relay. Subsequent routing is handled by the server infrastructure.

Three concepts that are easy to confuse:

| Concept | Meaning |
|---|---|
| **SMTP session** | The protocol exchange over a network connection between an SMTP client and an SMTP server, from connection establishment until close. |
| **Mail transaction** | A sending unit consisting of `MAIL FROM`, one or more `RCPT TO` commands, and `DATA`. One SMTP session can process multiple mail transactions. |
| **`jakarta.mail.Session`** | Jakarta Mail's configuration object holding properties and resources; it is **not** an open TCP socket or active SMTP session. |

In Spring, `JavaMailSenderImpl` and Jakarta Mail handle most SMTP commands. However, the outcome of those commands determines whether the email is accepted by the server.

## 2. Choosing an SMTP Port and How TLS Is Established

| Port | Common use case | When TLS is established |
|---|---|---|
| **587** | Application submitting mail to a submission server | TCP connection first, then uses `STARTTLS` to upgrade to TLS. |
| **465** | Submission over implicit TLS | TLS handshake occurs immediately after TCP connect, before the SMTP `220` greeting. |
| **25** | Relay between email servers or internal infrastructure | May support STARTTLS; not the default port to choose for applications sending user emails. |

Some providers use custom ports. Always verify the **host, port, encryption method, and authentication mechanism** against the documentation of the actual service.

**STARTTLS (typically on port 587):**

```text
TCP connect -> SMTP 220 -> EHLO -> STARTTLS
            -> TLS handshake -> second EHLO -> AUTH / send mail
```

**Implicit TLS (typically on port 465):**

```text
TCP connect -> TLS handshake -> SMTP 220
            -> EHLO -> AUTH / send mail
```

The main difference is whether TLS starts **before** or **after** the SMTP greeting. With STARTTLS, after TLS negotiation succeeds, the client must send `EHLO` again to discover the extensions available over the encrypted connection. If policy requires TLS and the upgrade fails, the client must stop sending.

## 3. Overview of an SMTP Session Sequence

```text
SMTP client (Spring/Jakarta Mail)             SMTP server
              |                                   |
              |---------- TCP connect ----------->|
              |<---------- 220 greeting ----------|
              |-------------- EHLO -------------->|
              |<--------- 250 extensions ---------|
              |                                   |
              |----------- STARTTLS ------------->|  (if used)
              |<------------- 220 ----------------|
              |<========== TLS handshake ========>|
              |-------------- EHLO -------------->|
              |<--------- 250 extensions ---------|
              |                                   |
              |------------- AUTH --------------->|  (if needed)
              |<------------- 235 ----------------|
              |----------- MAIL FROM ------------>|
              |<------------- 250 ----------------|
              |------------ RCPT TO ------------->|
              |<-------- 250 or error ------------|
              |-------------- DATA -------------->|
              |<------------- 354 ----------------|
              |------ Headers + blank line ------>|
              |------------ Body ---------------->|
              |------- <CRLF>.<CRLF> ------------>|
              |<------ 250 accepted / error ------|
              |                                   |
              |-------------- QUIT -------------->|
              |<------------- 221 ----------------|
              |--------- TCP/TLS close ---------->|
```

This is a successful sending flow with STARTTLS and AUTH. Those two steps depend on configuration. If the connection fails or the server closes the session mid-way, there may be no `QUIT` and `221`.

## 4. Stage-by-Stage from Connection to Session Close

### 4.1. Opening a TCP Connection and Receiving the `220` Greeting

The client opens a socket to the SMTP host/port. With implicit TLS, the TLS handshake takes place right here. When the SMTP server is ready, it sends a greeting line:

```text
S: 220 smtp.example.com ESMTP service ready
```

In illustrative transcripts, `C:` represents the client and `S:` represents the server. These prefixes make the conversation easier to read and **are not actually sent** over the wire.

Code **220** indicates that the SMTP server is ready. If it fails at this stage, check the host DNS, port, firewall, network, connection timeout, and the port's TLS setting. Being able to connect via TCP does not mean the account is authorized to send mail.

### 4.2. `EHLO` and Server Capabilities

The client sends `EHLO` to introduce itself and request the list of SMTP extensions:

```text
C: EHLO app.example.com
S: 250-smtp.example.com
S: 250-STARTTLS
S: 250-SIZE 10485760
S: 250 AUTH PLAIN LOGIN
```

`EHLO` belongs to Extended SMTP (ESMTP). In a multi-line response, `250-` means another line follows, and `250 ` (with a space) marks the final line.

| Extension | Practical meaning |
|---|---|
| `STARTTLS` | The server supports upgrading the current SMTP session to TLS. |
| `AUTH PLAIN LOGIN` | Advertises the authentication mechanisms the server supports at that moment. |
| `SIZE 10485760` | The server advertises the message size limit, in bytes. |
| `8BITMIME` | Supports transmitting 8-bit content per the corresponding extension. |
| `SMTPUTF8` | Supports internationalized addresses/headers per SMTPUTF8 rules. |
| `PIPELINING` | Allows optimizing by issuing certain commands without waiting for each individual response, if the client complies with the extension. |

Never assume all servers have the same extensions. Only use features matching the advertised list and application policy.

### 4.3. `STARTTLS`: Security Upgrade

On port 587, when the server advertises `STARTTLS`, the client can request an upgrade:

```text
C: STARTTLS
S: 220 Ready to start TLS
[TLS handshake succeeded]
C: EHLO app.example.com
S: 250-smtp.example.com
S: 250-AUTH PLAIN LOGIN
S: 250 SIZE 10485760
```

Commands after a successful handshake travel over the encrypted connection. **You must send `EHLO` again** because the set of extensions may change—for example, `AUTH` may only be advertised after TLS is enabled.

Configuring STARTTLS as "use if available" differs from "required to use". For applications that need to protect credentials, require TLS rather than allowing fallback to an unencrypted connection when the server does not support it.

On port 465, there is no `STARTTLS` command in the conversation; TLS is already established before `220`.

### 4.4. `AUTH`: Authenticating the Sending Account

Many SMTP submission servers require the client to authenticate:

```text
C: AUTH PLAIN <credentials-redacted>
S: 235 2.7.0 Authentication successful
```

The bracketed string is a placeholder, not a valid authentication command. In the `PLAIN` mechanism, authentication data is represented in Base64; **Base64 is not a security encryption mechanism**. Use TLS and safeguard credentials as secrets.

Commonly seen response codes:

- **235**: authentication successful.
- **535**: authentication rejected; check the username, password/token, and authentication policy.
- **454**: temporary authentication failure; handle according to a bounded retry policy.

Internal SMTP relays sometimes grant permission by network or IP and do not require `AUTH`. The client must follow the mechanism permitted by the server rather than assuming every SMTP server uses a username and password.

### 4.5. `MAIL FROM`: Starting a Transaction and Declaring the Sender

Once ready to send, the client starts a mail transaction with the command:

```text
C: MAIL FROM:<bounce@example.com>
S: 250 2.1.0 Sender OK
```

`MAIL FROM` is the sender address in the **SMTP envelope (envelope sender/reverse-path)**, used for handling bounce return paths. It can differ from the `From:` header seen by the recipient. The server may reject at this step due to an invalid sender, the account lacking permission to use that address, or anti-abuse policies.

Certain special messages such as delivery failure notifications may use an empty reverse-path (`MAIL FROM:<>`) to prevent bounce loops. Normal transactional email applications do not need to alter this value unless explicitly required.

### 4.6. `RCPT TO`: Declaring Each Recipient

Each recipient in the envelope has a separate command:

```text
C: RCPT TO:<alice@example.net>
S: 250 2.1.5 Recipient OK
C: RCPT TO:<bob@example.org>
S: 250 2.1.5 Recipient OK
```

The server responds **for each address**. One recipient may be accepted while another is rejected:

```text
C: RCPT TO:<alice@example.net>
S: 250 2.1.5 Recipient OK
C: RCPT TO:<unknown@example.org>
S: 550 5.1.1 User unknown
```

Do not interpret a `250` for Alice as meaning all recipients are valid. Whether the client proceeds to send to the accepted addresses or aborts the entire send depends on the library, configuration, and transaction state. If all addresses are rejected, the client has no valid recipients to proceed to data transfer.

### 4.7. `DATA`: Transmitting Headers and Content

After the server accepts at least one recipient, the client sends `DATA`:

```text
C: DATA
S: 354 End data with <CRLF>.<CRLF>
```

Code **354** means the server is ready to receive data. The client transmits **headers**, a **blank line**, and then the **body**. Illustrative example only:

```text
C: From: "System" <no-reply@example.com>
C: To: alice@example.net
C: Subject: Registration confirmation
C: MIME-Version: 1.0
C: Content-Type: text/plain; charset=UTF-8
C:
C: Hello Alice,
C: Your account has been created.
C: .
```

On the wire, the end-of-data marker is **`<CRLF>.<CRLF>`**. If a content line starts with a dot, the client must apply **dot-stuffing**: prepending an extra dot so it is not mistaken for the end of `DATA`. Jakarta Mail handles this protocol detail.

After receiving the full content, the server may return:

```text
S: 250 2.0.0 Queued as ABC123
```

This usually means the **SMTP server has accepted responsibility for processing the message** or placed it into a queue. It **does not guarantee** that the mail has reached the final mailbox, landed in the Inbox, or been read by the recipient.

HTML emails, attachments, and multipart content (MIME multipart) change the message structure after `DATA`; the control commands `MAIL FROM` → `RCPT TO` → `DATA` remain the same in principle.

### 4.8. Another Transaction or `QUIT` to Finish

After a mail transaction completes, the client can start a **new transaction on the same connection** with `MAIL FROM` if needed and the server keeps the session open. When there is no more work:

```text
C: QUIT
S: 221 2.0.0 Bye
[Close TCP/TLS connection]
```

`QUIT` ends the session cleanly; `221` confirms the server side is about to close. On network errors, timeouts, or server disconnects, the client may fail to send `QUIT` or fail to receive `221`.

## 5. Complete SMTP Conversation Example on Port 587

The conversation below uses dummy addresses and redacted AUTH data. Notes in square brackets are not actual SMTP commands:

```text
[TCP connect smtp.example.com:587]
S: 220 smtp.example.com ESMTP ready

C: EHLO app.example.com
S: 250-smtp.example.com
S: 250-STARTTLS
S: 250 SIZE 10485760

C: STARTTLS
S: 220 Ready to start TLS
[TLS handshake successful]

C: EHLO app.example.com
S: 250-smtp.example.com
S: 250-AUTH PLAIN LOGIN
S: 250 SIZE 10485760

C: AUTH PLAIN <redacted>
S: 235 2.7.0 Authentication successful

C: MAIL FROM:<no-reply@example.com>
S: 250 2.1.0 OK

C: RCPT TO:<alice@example.net>
S: 250 2.1.5 OK

C: DATA
S: 354 End data with <CRLF>.<CRLF>
C: From: no-reply@example.com
C: To: alice@example.net
C: Subject: Welcome
C:
C: Hello, Alice!
C: .
S: 250 2.0.0 Message queued as ABC123

C: QUIT
S: 221 2.0.0 Closing connection
[TCP/TLS close]
```

The wording and enhanced status codes (`2.0.0`, `2.1.5`, etc.) vary by provider. SMTP responses are the result of **each individual step**, so the same `250` code appears in multiple places with a specific meaning tied to the command just sent.

## 6. Envelope and Message Header Are Two Separate Parts

The SMTP envelope is transmitted via the commands:

```text
MAIL FROM:<bounce@example.com>
RCPT TO:<alice@example.net>
RCPT TO:<audit@example.org>
```

Email headers, on the other hand, reside **inside `DATA`**:

```text
From: "Shop" <sales@example.com>
To: alice@example.net
Subject: Your order

...content...
```

Therefore:

- `MAIL FROM` can differ from `From:`. This is often tied to the bounce return address, sender configuration, and sending service policies.
- `RCPT TO` describes actual recipients at the transport layer; `To:` and `Cc:` headers describe displayed recipients.
- **Bcc** recipients can exist in the envelope without appearing in the `To:` or `Cc:` headers of the sent message.

When analyzing SMTP logs or "sender address rejected" errors, you need to know whether the error belongs to the **envelope** or the content/header. Changing the displayed `From:` does not always change the actual `MAIL FROM`.

## 7. How Does Spring Mail Execute These Steps?

With Spring Boot, the `spring-boot-starter-mail` dependency and `spring.mail.*` configuration are usually enough for Boot to create a `JavaMailSender` backed by Jakarta Mail:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
```

In a Spring Framework application without Boot, you need to create and configure `JavaMailSenderImpl` along with the appropriate mail libraries yourself.

### 7.1. Configuring SMTP 587 with STARTTLS

`application.yml`:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
```

| Jakarta Mail Property | Purpose |
|---|---|
| `mail.smtp.auth=true` | Enables SMTP authentication. |
| `mail.smtp.starttls.enable=true` | Allows using STARTTLS if the server supports it. |
| `mail.smtp.starttls.required=true` | Requires STARTTLS to succeed. |
| `mail.smtp.connectiontimeout` | Maximum time to wait when establishing a connection. |
| `mail.smtp.timeout` | Maximum time to wait when reading data/responses from the socket. |
| `mail.smtp.writetimeout` | Maximum time for a socket write operation. |

The three timeouts in the example are in **milliseconds**. Configuring timeouts prevents send operations from hanging indefinitely when the network or server stalls. Appropriate values depend on the deployment environment.

`SMTP_USERNAME` and `SMTP_PASSWORD` are supplied from environment variables, a secret store, or secure deployment configuration; never commit real values to Git.

### 7.2. Configuring Implicit TLS on Port 465

If the provider requires TLS immediately upon opening the connection:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 465
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail:
        smtp:
          auth: true
          ssl:
            enable: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
```

`mail.smtp.ssl.enable=true` uses TLS from the start of the SMTP connection instead of starting in plaintext and sending `STARTTLS`. The port and security mode must match the server-side configuration.

### 7.3. Sending Mail with JavaMailSender

```java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class RegistrationMailService {
    private final JavaMailSender mailSender;

    public RegistrationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmation(String recipient, String link) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("no-reply@example.com");
        message.setTo(recipient);
        message.setSubject("Registration confirmation");
        message.setText("Open the link to confirm your account: " + link);

        mailSender.send(message);
    }
}
```

Here, the application only calls `send(...)`. Spring Mail and Jakarta Mail build the message, manage the SMTP transport, and execute the required commands. To send HTML or attachments, you can create a `MimeMessage` with `MimeMessageHelper`; the SMTP control lifecycle remains fundamentally unchanged.

**Do not confuse a reused `JavaMailSender` bean with an always-open SMTP socket.** When the transport opens and closes depends on the implementation and how it is invoked. A batch send of multiple messages may reuse an open connection; you should not assume each email always opens a separate connection or always reuses a single long-lived connection.

## 8. Analyzing Errors by Stage

General meaning of SMTP codes:

- **2xx**: the corresponding command succeeded, e.g., `220`, `235`, `250`, and `221`.
- **3xx**: intermediate response requiring further action, commonly `354`.
- **4xx**: temporary failure; can be retried under a controlled policy.
- **5xx**: permanent failure in the current request context; do not retry unconditionally.

| Stage | Error examples | Troubleshooting approach |
|---|---|---|
| TCP/DNS connection | Unknown host, connection refused, connection timeout | Check SMTP host, port, DNS, firewall, network, and service health. |
| TLS | STARTTLS not supported, handshake failure, invalid certificate | Match port/TLS mode, hostname, and certificate trust; do not disable certificate verification to bypass errors. |
| `EHLO` | Required extension missing | Verify server capabilities and client configuration. |
| `AUTH` | `535` or `454` | Check credentials/policy for 535; consider bounded retries for temporary error 454. |
| `MAIL FROM` | Sender rejected | Check sender address, relay permissions, and domain policy. |
| `RCPT TO` | `450`, `550 5.1.1` | Distinguish between a temporarily unavailable mailbox and a non-existent address. |
| `DATA` | `552`, `554` | Check message size, content, formatting, and server policy. |
| After end of `DATA` | Timeout before receiving `250` response | Delivery status **may be indeterminate**; avoid retries that cause duplicate emails. |
| `QUIT` | Connection lost before `221` | Check whether the post-`DATA` response was received before deciding the status. |

### 8.1. Tricky Case: Content Sent but `250` Not Yet Received

For example, the client sent the terminating dot but was disconnected before reading the final response:

```text
C: DATA
S: 354 End data with <CRLF>.<CRLF>
C: [headers + body + terminating dot]
[Timeout or connection lost before final response]
```

The client cannot confirm whether the server accepted the message. The server **may** have queued the message, with the response failing to reach the client. Immediate retrying risks duplicate emails; critical systems should store a business event ID, attempt count, timestamp, and reconciliation status to handle this case.

Similarly, a **250 response after `DATA`** only confirms that the current-hop SMTP server has accepted the message. If you need to know whether the email was delivered, bounced, rejected later, or opened, you need data from the delivery infrastructure or an appropriate email provider.

### 8.2. Multiple Recipients and Partial Success

SMTP returns a response for each `RCPT TO`. A sending library may reject the whole call if any address is invalid, or continue with valid recipients depending on implementation and configuration. When per-recipient status tracking is required, manage sending at the recipient level, persist detailed results, or use event/provider APIs.

Do not use a single boolean "send succeeded" flag to represent all recipients if the business requirement demands per-email accuracy.

## 9. Monitoring and Operating SMTP Sessions

A useful log should show **which stage was reached**: connect, TLS, AUTH, MAIL FROM, RCPT TO, DATA, or QUIT. Example:

```text
220 smtp.example.com ESMTP
250-STARTTLS
250 SIZE 10485760
220 Ready to start TLS
[TLS established]
235 2.7.0 Authentication successful
250 2.1.0 Sender OK
550 5.1.1 User unknown
```

If a send ends at `550 5.1.1` while declaring a recipient, connection and AUTH have already succeeded, so check the recipient address first. Changing the SMTP password will not fix the right issue.

Operational practices should include:

- Logging timestamp, SMTP host, failure stage, response code, job ID, or internal message ID.
- Avoiding logging passwords, AUTH data, tokens in message bodies, and unnecessary recipient data.
- Enabling protocol debug logging only in controlled environments; SMTP logs may contain message bodies or sensitive metadata.
- Applying timeouts, retry/backoff, and send rate limits per provider policies.
- Distinguishing SMTP relay acceptance from downstream actual delivery events.

## 10. Self-Check Questions

1. On port 587, order `220`, `EHLO`, `STARTTLS`, TLS handshake, second `EHLO`, and `AUTH`.
2. Why can `MAIL FROM` differ from the `From:` header?
3. The server returns `250` for `RCPT TO` but returns `554` after `DATA`. Can the email be considered accepted for delivery?
4. When the server returns `354`, what must the client send and with what sequence does it end data?
5. The client times out right after sending the terminating dot without receiving `250`. Why can retrying cause the recipient to receive two emails?
6. What is the difference between `mail.smtp.starttls.enable=true` and `mail.smtp.starttls.required=true`?
7. For port 465, does the TLS handshake occur before or after the SMTP `220` greeting?

**Hints:** (1) `220` → `EHLO` → `STARTTLS` → TLS handshake → `EHLO` again → `AUTH`; (2) one belongs to the delivery envelope, the other to the message header; (3) no, the transaction was rejected after DATA; (4) headers, blank line, body, terminated with `<CRLF>.<CRLF>`; (5) the server may have accepted it while the response was lost; (6) allowing STARTTLS vs requiring the upgrade to succeed; (7) before `220`.

## 11. Conclusion

An SMTP session from connection to session close typically follows the order **TCP/TLS → `220` → `EHLO` → additional TLS if needed → `AUTH` → `MAIL FROM` → `RCPT TO` → `DATA` → final response → `QUIT`/close connection**. Spring Mail and Jakarta Mail spare the application from writing those commands directly, yet each step can still fail with its own meaning.

When diagnosing issues, rely on **the command being executed, the SMTP response code, and the connection state**. Always distinguish "the SMTP server accepted the message" from "the recipient received the message"; those two states belong to different stages of the email system.
