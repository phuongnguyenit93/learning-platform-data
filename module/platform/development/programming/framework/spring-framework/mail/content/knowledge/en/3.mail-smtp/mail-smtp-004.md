# 2xx, 4xx, and 5xx Response Codes in SMTP

When an application uses **Spring Framework Mail** to send email, it usually connects to an **SMTP (Simple Mail Transfer Protocol)** server. During this conversation, the application sends commands such as `EHLO`, `MAIL FROM`, `RCPT TO`, and `DATA`; the server returns **three-digit response codes** to report how the just-sent command was processed.

Three code groups to distinguish when implementing mail-sending features are:

| Code group | Meaning in SMTP | Common handling approach |
| --- | --- | --- |
| **2xx** | Positive completion: the request at the **current step** succeeded | Proceed to the next SMTP step or record that the message was accepted by the server after `DATA` finishes |
| **4xx** | Transient negative completion: the server **temporarily could not complete** the request | Consider retrying after a wait interval, bounded and consistent with transaction state |
| **5xx** | Permanent negative completion: the request **is not accepted under current conditions** | Find the root cause and fix the address/configuration/content/policy before resending |

This is an **SMTP protocol convention**, not HTTP status codes. In particular, SMTP `4xx` denotes errors considered temporary; `5xx` usually requires changing conditions before retrying. Never apply HTTP's "4xx = client error, 5xx = server error" mental model to SMTP.

> There is another very important group: **3xx**, such as `354 Start mail input`. This is a *positive intermediate* reply, meaning the server is ready to receive subsequent data. This lesson focuses on 2xx, 4xx, and 5xx while using 354 to understand the complete sending flow.

## 1. How Is an SMTP Response Structured?

A response line typically has the form:

~~~text
<three-digit-code><separator><explanatory-text>

250 2.0.0 Message accepted for delivery
451 4.3.0 Temporary processing error
550 5.1.1 User unknown
~~~

Where:

- **The three-digit code** at the beginning of the line, such as `250`, `451`, or `550`, is the basic SMTP reply code.
- **Strings like `2.0.0`, `4.3.0`, `5.1.1`** that may appear after the primary code are *enhanced status codes*, providing more detailed information. Not every server or every response includes this code.
- **The text portion** provided by the server aids diagnostics, though phrasing varies by provider and is not as stable as a structured API.

### 1.1. Meaning of the First Digit

| First digit | Group name | Meaning |
| --- | --- | --- |
| `2` | Positive completion | The command completed successfully at the current stage |
| `3` | Positive intermediate | The command was initially accepted; the server requests more data |
| `4` | Transient negative completion | The command could not be completed due to a condition considered temporary |
| `5` | Permanent negative completion | The command was rejected; resending as-is usually will not resolve it |

The remaining two digits help identify the specific situation. For instance, `250` and `251` both belong to the success group but do not carry identical semantics. Never assume all codes with the same leading digit can be handled identically.

### 1.2. Multi-Line Responses

SMTP allows the server to reply with multiple lines, commonly seen after `EHLO`:

~~~text
S: 250-smtp.example.net Hello app.example.org
S: 250-PIPELINING
S: 250-SIZE 10485760
S: 250 STARTTLS
~~~

The **hyphen** immediately after the code (`250-`) indicates another line of the same response follows; a **space** (`250 `) marks the final line. The client must read the entire related response instead of treating each line as the result of a different command.

## 2. The 2xx Group: Server Accepts the Current Processing Step

**2xx does not mean the email has definitely reached the recipient's mailbox.** The degree of success depends on which command is being answered:

| Code | Common meaning | When it may occur |
| --- | --- | --- |
| **220** | Service ready: SMTP server is ready | At connection start; also used for ready-to-start TLS reply after `STARTTLS` |
| **221** | Service closing transmission channel | When ending the session with `QUIT` |
| **235** | Authentication successful | After SMTP AUTH succeeds, if the server supports this extension |
| **250** | Requested mail action okay, completed | After `EHLO`, `MAIL FROM`, `RCPT TO`, or after the server accepts the full `DATA` payload |
| **251** | User not local; will forward | Server agrees to forward to another address; less common |
| **252** | Cannot verify user, but will accept message and attempt delivery | A reply that may appear in `VRFY` context; does not prove the recipient exists |

### 2.1. Code `250` at Different Stages

This code appears frequently in SMTP logs, but it must be **read alongside the command immediately preceding it**:

- `250` after `MAIL FROM`: the server accepted the **envelope sender address** for the current transaction.
- `250` after `RCPT TO`: the server accepted the corresponding **envelope recipient** at this step.
- `250` after the terminating dot of `DATA`: the server **accepted responsibility for processing/relaying** the message sent in the transaction.

Even in the last case, the message can still be delayed, returned (*bounce*), rejected by a downstream server, or filtered into spam. To learn those states, you usually have to monitor asynchronous feedback such as bounces, DSN (*Delivery Status Notification*), or provider webhooks.

### 2.2. Example of a Successful Sending Session

`C` denotes the client (application/mail library), and `S` denotes the SMTP server:

~~~text
S: 220 smtp.example.net ESMTP ready
C: EHLO app.example.org
S: 250-smtp.example.net
S: 250-PIPELINING
S: 250 SIZE 10485760

C: MAIL FROM:<no-reply@example.org>
S: 250 2.1.0 Sender OK

C: RCPT TO:<reader@example.net>
S: 250 2.1.5 Recipient OK

C: DATA
S: 354 End data with <CRLF>.<CRLF>
C: From: no-reply@example.org
C: To: reader@example.net
C: Subject: Welcome
C:
C: Hello, this is a test message.
C: .
S: 250 2.0.0 Message queued as Q12345

C: QUIT
S: 221 2.0.0 Bye
~~~

Key progression points:

1. **220:** server is ready to communicate.
2. **250 after `EHLO`:** server responds to the greeting and may list extensions.
3. **250 after `MAIL FROM` and `RCPT TO`:** envelope sender and recipient are accepted.
4. **354:** server asks the client to transmit email content; it **has not confirmed receipt of the whole message yet**.
5. **250 after the terminating dot `.`:** server accepts the message for processing/relaying.
6. **221:** SMTP session ends normally.

The example omits authentication and TLS to focus on reply codes. On real systems, the client may have to perform `STARTTLS`, send `EHLO` again after upgrading to TLS, and then `AUTH` per provider policy.

## 3. The 4xx Group: Temporary Errors, Retry May Be Needed

**4xx** indicates the server cannot fulfill the request **at the current time**. Usually it can be retried later, though the situation must be evaluated and never retried infinitely.

| Code | Common meaning | Handling approach |
| --- | --- | --- |
| **421** | Service temporarily unavailable; transmission channel closing/about to close | End the session and open a new connection after a wait |
| **450** | Mailbox temporarily unavailable, e.g., locked/busy | Retain the request and retry later |
| **451** | Local error while server processed the request | Bounded retry; log the cause/stage where the error occurred |
| **452** | System lacks resources/storage to process | Reduce load and wait before retrying |
| **454** | SMTP authentication temporarily unavailable | Check auth/provider status and retry when appropriate |

The server's descriptive text often explains further, for example:

~~~text
421 4.7.0 Too many connections, try later
450 4.2.0 Mailbox temporarily unavailable
451 4.7.1 Greylisted, please try again later
452 4.3.1 Insufficient system storage
454 4.7.0 Temporary authentication failure
~~~

These are **illustrative examples**; actual messages and enhanced status codes are determined by each server. Never build retry rules solely by searching for words like "greylisted" or "temporary" in the descriptive text.

### 3.1. Example: Server Temporarily Rejects a Recipient

~~~text
C: RCPT TO:<recipient@example.net>
S: 450 4.2.0 Mailbox temporarily unavailable
~~~

The server has not accepted this recipient in the current transaction. The sending system must persist the appropriate state and retry per policy rather than marking it "sent successfully".

### 3.2. Example: Temporary Error After Sending Content

~~~text
C: DATA
S: 354 End data with <CRLF>.<CRLF>
C: Subject: Monthly report
C:
C: Report body...
C: .
S: 451 4.3.0 Temporary local processing error
~~~

In the case above, **there is no `250` after the message content**, so you cannot conclude the server accepted the mail. The client can retry later per sending policy. However, distinguish a different scenario: if the client **loses connection before receiving the final reply**, it cannot be sure whether the server accepted it, so retrying risks sending duplicates.

### 3.3. How to Retry?

A sound strategy for 4xx:

1. Persist the send request and failure reason (SMTP code, processing phase, timestamp).
2. Schedule retries after increasing wait intervals, such as **exponential backoff** with **jitter** to prevent many workers from retrying simultaneously.
3. Bound the number of attempts or total wait duration; once exceeded, transition the task to a state needing monitoring/intervention.
4. Respect the provider's specific rate limits and guidance.
5. Monitor spikes in 4xx rates to detect system outages or sending policy issues.

Exact wait times should come from business requirements and provider recommendations rather than hardcoding one number for all cases. In particular, `454` often relates to authentication infrastructure and may require operational alerts alongside retries.

## 4. The 5xx Group: Request Rejected Under Current Conditions

**5xx** means the server considers the request **cannot succeed by resending identically**. Many causes are not server crashes: invalid command syntax, non-existent recipient address, missing authentication, denied sending policy, or unacceptable content type.

| Code | Common meaning | What to check |
| --- | --- | --- |
| **500** | Command syntactically invalid or unrecognized | Client command name/protocol |
| **501** | Invalid syntax in command parameters or arguments | Formatting of addresses/arguments |
| **502** | Command not implemented/supported | Compatibility with the SMTP server |
| **503** | Bad sequence of commands | Order of `EHLO`, `MAIL FROM`, `RCPT TO`, `DATA` |
| **504** | Command parameter not supported | Extension, AUTH mechanism, or options |
| **530** | Authentication required before performing action | SMTP AUTH config and relay policy |
| **535** | Authentication failed | Credentials, account, AUTH method, provider policy |
| **550** | Mailbox unavailable, address non-existent, or rejected by policy | Recipient address, domain, relay permission, spam block |
| **551** | User not local; must use specified forwarding path | Appropriate delivery path/address |
| **552** | Exceeded storage/size allocation | Message size, mailbox quota |
| **553** | Mailbox name not allowed | Sender or recipient format/address |
| **554** | Transaction failed or rejected | Filtering rules/policy/server and specific reason |

Common examples:

~~~text
535 5.7.8 Authentication credentials invalid
550 5.1.1 Recipient address rejected: User unknown
550 5.7.1 Relay access denied
552 5.2.2 Mailbox full
554 5.7.1 Message rejected by policy
~~~

Code `550` appears in **many different kinds of errors**. You cannot look at `550` alone and conclusively state "email does not exist". You must combine the enhanced status code, the provider's reply text, the command being sent, and the corresponding policy.

### 4.1. Example: Recipient Address Does Not Exist

~~~text
C: RCPT TO:<typo@example.net>
S: 550 5.1.1 User unknown
~~~

The application should flag this address for correction or stop trying to send to it. Repeatedly retrying the same address will not solve an error the server declared permanent.

### 4.2. Example: Authentication Failed

~~~text
C: AUTH ...
S: 535 5.7.8 Authentication credentials invalid
~~~

This is usually a sign to check the username, credentials, account status, AUTH method, or provider settings. Do not print AUTH data or passwords to logs. Also avoid repeatedly retrying, as it can lock the account or trigger rate limits.

### 4.3. Example: Rejected Due to Policy

~~~text
C: RCPT TO:<recipient@external.example>
S: 550 5.7.1 Relay access denied
~~~

This message typically suggests the client is attempting to relay mail through a server that disallows it: unauthenticated, using the wrong SMTP host, account lacking permission, or unapproved sender address/domain. Fix the configuration or sending permissions instead of automatically repeating the request.

## 5. Enhanced Status Codes: Why Do `550 5.1.1` and `550 5.7.1` Differ?

In addition to the three-digit code, the server may send an **enhanced status code** following the pattern:

~~~text
X.Y.Z

550 5.1.1 User unknown
550 5.7.1 Message rejected by policy
451 4.7.1 Temporary policy deferral
~~~

High-level meaning:

- **X (class):** `2` is success, `4` is temporary error, `5` is permanent error.
- **Y (subject):** problem category, such as addressing, mailbox, mail system, network/routing, protocol, or security/policy.
- **Z (detail):** specific condition within that category.

Easy-to-distinguish examples:

| Observed reply | Useful interpretation |
| --- | --- |
| `550 5.1.1` | Recipient address invalid/non-existent per server response |
| `550 5.7.1` | Rejected due to policy, relay permissions, or security issue |
| `535 5.7.8` | Authentication credentials not accepted |
| `451 4.7.1` | Temporarily deferred by policy; may be greylisting or temporary throttling |
| `452 4.3.1` | Server temporarily low on resources/storage |
| `250 2.0.0` | Current sending step completed; after `DATA` usually means the mail was accepted for processing |

**Not every server emits the same enhanced status string or interpretation.** For accurate diagnosis, prioritize standard codes and provider documentation while storing raw replies in a bounded way with sensitive data stripped.

## 6. At Which Step in the SMTP Session Do Error Codes Appear?

The same code can be returned at different stages; each stage leads to a different remediation.

~~~mermaid
flowchart TD
    A["SMTP Connection"] --> B{"Banner"}
    B -->|"220"| C["EHLO / STARTTLS / AUTH"]
    B -->|"421"| X["Pause and reconnect later"]
    C --> D{"Session prep result"}
    D -->|"2xx"| E["MAIL FROM"]
    D -->|"4xx"| R["Schedule appropriate retry"]
    D -->|"5xx"| F["Fix config / auth"]
    E --> G["RCPT TO per recipient"]
    G --> H{"Recipient accepted?"}
    H -->|"250"| I["DATA"]
    H -->|"4xx"| R
    H -->|"5xx"| J["Fix address / permissions / policy"]
    I --> K{"354 then send content, terminating dot"}
    K -->|"250 after content"| L["SMTP accepted message for processing"]
    K -->|"4xx"| R
    K -->|"5xx"| J
~~~

| Where error occurred | Diagnostic questions |
| --- | --- |
| **Connection / banner** | Is the server available? Are there overload, connection limit, or network issues? |
| **`EHLO` / `STARTTLS`** | Does the server support the extensions and TLS mode required by the client? |
| **`AUTH`** | Are credentials right? Is the AUTH mechanism supported? Is sending permission valid? |
| **`MAIL FROM`** | Does the server permit that envelope sender address? |
| **`RCPT TO`** | Is the recipient address valid? Does the server allow sending to this domain? |
| **`DATA` and after terminating dot** | Did size, content, resource limits, or filtering policies cause the mail to be rejected? |

### 6.1. One Message with Multiple Recipients

SMTP can call `RCPT TO` multiple times in a single transaction:

~~~text
C: RCPT TO:<alice@example.net>
S: 250 2.1.5 Recipient OK
C: RCPT TO:<bob@example.net>
S: 550 5.1.1 User unknown
C: RCPT TO:<carol@example.net>
S: 450 4.2.0 Mailbox temporarily unavailable
~~~

In this example, the addresses have **different outcomes**. Whether the library continues sending, skips failed recipients, or throws an exception depends on the SMTP client/provider's configuration and handling rules. Mail-sending software should track outcomes **per recipient** if the business needs accuracy, avoiding marking the entire list "succeeded" or "failed" when only some addresses are rejected.

### 6.2. Timeout Does Not Equal 4xx

If the client encounters `SocketTimeoutException`, a dropped connection, or a TLS error before receiving a response, **there may be no SMTP code at all** to classify as 2xx/4xx/5xx. In particular, losing the connection after sending the terminating dot of `DATA` creates an ambiguous situation where it is unknown whether the server accepted the mail. The retry system must weigh the risk of duplicate emails and attach a business ID/idempotency key to send tasks on the application side.

## 7. Interpreting SMTP Codes in Spring Framework Mail

In Java, Spring provides `JavaMailSender` to send mail. When using Spring Boot with `spring-boot-starter-mail`, applications usually inject this interface into a service; SMTP connectivity is handled by the underlying implementation and Jakarta Mail library.

Simple example:

~~~java
import org.springframework.mail.MailException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class MailSubmissionService {
    private final JavaMailSender sender;

    public MailSubmissionService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void submit(String from, String to, String subject, String body) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(to);
        message.setSubject(subject);
        message.setText(body);

        try {
            sender.send(message);
            // Send call returned normally:
            // mail submission via transport is complete.
            // Cannot yet assert the mail reached the Inbox.
        } catch (MailException failure) {
            // Persist error details at the appropriate orchestrator/job layer.
            // Inspect nested causes to find the SMTP code,
            // if the server actually returned one.
            throw failure;
        }
    }
}
~~~

This is an example of **API boundaries**, not a complete retry mechanism. Key exceptions to know:

- `MailAuthenticationException`: Spring reports a mail authentication failure; inspect the root cause and SMTP response if present (e.g., temporary `454` or rejected credentials `535`).
- `MailSendException`: failure during sending; may hold per-message failure details via methods such as `getFailedMessages()`, along with underlying causes.
- `MailException`: parent class of Spring mail exceptions. Relying solely on the exception class name is usually **insufficient** to conclude whether it is 4xx or 5xx.
- Underlying Jakarta Mail/SMTP provider exceptions may carry the raw reply code. How to extract the exact code varies by implementation and error type; inspect the relevant exception chain, including Jakarta Mail's nested and linked exceptions.

Avoid writing code like:

~~~java
// Error-prone inference:
// catch (MailSendException e) { retryForever(); }
// catch (MailAuthenticationException e) { neverRetry(); }
~~~

Because `MailSendException` can include permanent errors, while authentication issues are sometimes temporary. Classify based on **actual SMTP reply code + processing phase + connection state + provider policy** before deciding retry schedules or alerts.

### 7.1. Result-Handling Flow at the Application Layer

In a system that persists job states, you can use a conceptual classification like:

~~~text
Call JavaMailSender.send(...)
  |
  +-- Returns normally
  |      -> SUBMITTED_TO_SMTP
  |         (not yet DELIVERED_TO_RECIPIENT)
  |
  +-- Has SMTP reply 4xx
  |      -> TEMPORARY_FAILURE
  |         (retry with backoff/limits)
  |
  +-- Has SMTP reply 5xx
  |      -> PERMANENT_FAILURE
  |         (fix data/config/policy before resending)
  |
  +-- Timeout / connection drop / no SMTP reply
         -> UNKNOWN_OUTCOME or TRANSPORT_FAILURE
            (evaluate failure phase and duplicate risk)
~~~

The state names above are **application design examples**, not an enum provided out of the box by Spring Mail. If the provider supports webhooks, `SUBMITTED_TO_SMTP` can be supplemented by `DELIVERED`, `BOUNCED`, or other post-send events.

## 8. Practical Handling Strategy by Code Group

| Scenario | Classification | What the application should do | What to avoid |
| --- | --- | --- | --- |
| `250` after `DATA` ends | SMTP accepted message | Store timestamp, transaction/provider ID if available; continue tracking delivery when needed | Claiming with certainty that the user received/read the mail |
| `421`, `450`, `451`, `452` | Temporary failure | Retry with wait intervals, limits, and diagnostic logs | Immediate unbounded resending |
| `454` | Temporary auth failure | Check provider health, alert if prolonged | Treating immediately as permanently wrong credentials |
| `535` | Auth rejected | Check credentials, permissions, and AUTH mechanism | Repeatedly failing and locking the account |
| `550 5.1.1` | Recipient invalid per server | Record failed address, request correction | Retrying with the exact same unchanged address |
| `550 5.7.1` | Rejected due to permissions/policy | Check SPF/DKIM/DMARC if relevant, From, relay, and provider config | Blindly concluding the mailbox does not exist |
| `552` or size rejection | Message/quota exceeded limit | Reduce size/split attachments or handle quota | Increasing retry count when payload is unchanged |
| Connection dropped after `DATA`, no final reply | Indeterminate outcome | Check provider status if available, apply deduplication and cautious retry rules | Asserting with certainty that the mail was not sent |

### 8.1. Information to Persist for Investigation

For each send attempt, you can store:

- Job ID/business ID and email type;
- SMTP host or provider used (never log credentials);
- SMTP phase where failure occurred, three-digit code, and enhanced status if obtainable;
- Internal error code, attempt count, failure timestamp, and next retry schedule;
- Message/provider ID (if available) and later-updated delivery status.

Never log passwords, authentication tokens, full email bodies, password reset codes, or sensitive user data. If email addresses must be stored to support operations, apply access controls and masking/encryption per system policy.

### 8.2. Distinguishing Protocol Errors from Actual Deliverability

Four situations are often conflated:

1. **Client receives `250` after `RCPT TO`:** the recipient address was accepted at the envelope step, but message content has not been sent yet.
2. **Client receives `250` after the terminating dot of `DATA`:** the server accepted the message for processing/relaying.
3. **Provider reports "delivered":** usually means the message was accepted by the destination receiving server per the provider's definition; it does not prove the mail landed in the Inbox.
4. **User has read the mail:** cannot be asserted from SMTP results alone; open-tracking mechanisms also have reliability and privacy limitations.

## 9. Interpreting Sample Responses Yourself

Read each line together with its context:

| Observed response | Interpretation |
| --- | --- |
| `220 smtp.example.net ready` on connect | SMTP connection reached a ready server; no email has been sent yet |
| `235 2.7.0 Authentication successful` after AUTH | Authentication succeeded; mail-sending steps still have to run |
| `250 2.0.0 Queued as ABC` after DATA ends | Server accepted the mail for relaying; save ID ABC for lookup if the provider supports it |
| `451 4.7.1 Try again later` at RCPT TO | Address is temporarily deferred; consider retry per policy |
| `550 5.1.1 User unknown` at RCPT TO | Server rejected the recipient; check/fix address |
| `550 5.7.1 Relay denied` at RCPT TO | Server refused relaying; check configuration/sending permissions |
| `535 5.7.8 Invalid credentials` at AUTH | Check account, secrets, and authentication mechanism |
| No code because connection timed out after DATA dot | Transaction outcome is unknown; handle duplicate risk when retrying |

When reading SMTP logs of a Spring Mail module, identify in order **the command being answered**, **the three-digit code**, **the enhanced status code if present**, and **what the system can validly assert**. From there, the 2xx group shows which stage succeeded; the 4xx group points toward controlled retries; and the 5xx group points toward fixing data, configuration, or policy. Reading logs this way avoids both major mistakes: reporting "mail delivered" too early and infinitely retrying SMTP requests that are being permanently rejected.
