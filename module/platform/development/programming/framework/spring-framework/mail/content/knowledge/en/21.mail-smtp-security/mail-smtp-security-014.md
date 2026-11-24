# Assessing Risks When Logging SMTP Debug

When emails fail to send, enabling **SMTP debug** looks like the fastest way to find the cause. Protocol logs can reveal which host the client connected to, which extensions the server advertised after EHLO, whether STARTTLS ran, whether AUTH was rejected, and which error code the server returned at MAIL FROM, RCPT TO, or DATA.

However, **SMTP debug is also a source of sensitive data leaks**. An overly verbose transcript can contain recipient addresses, sending accounts, internal domain names, server error messages, email metadata, authentication details, or even message contents depending on the provider, version, and logging configuration. Once logs ship to centralized collectors, print to container stdout, persist in CI artifacts, or get pasted into tickets, data exposure reaches far beyond the original email system.

With Spring Framework Mail, distinguish between **Jakarta Mail protocol debug**, **Spring/application logging**, and **JSSE/TLS handshake debug**. Each source provides different visibility and introduces distinct risks. Connecting to SMTP over TLS **does not protect copies of data written by the application into logs**.

Safe deployment principles:

- **Disable SMTP debug transcripts in production by default.**
- Enable detailed diagnostics only for a specific purpose, narrow scope, restricted access, and a strict end time.
- Never enable options that log AUTH credentials or OAuth tokens.
- Prefer **structured logging based on an allowlist of fields** instead of raw transcripts.
- Keep MIME bodies, attachments, password-reset links, OTPs, and customer data out of logs.
- Restrict retention, permissions, encryption, and forwarding to observability platforms.
- When exposure is suspected, treat the logs as a data incident and rotate/revoke credentials if needed.

This lesson explains how to identify, assess, and mitigate SMTP debug logging risks in Spring Mail applications, with configuration examples and a controlled incident-investigation workflow.

## 1. What is SMTP debug?

SMTP is a command-and-response protocol. When an application uses **JavaMailSender**, the Jakarta Mail transport executes steps like:

~~~text
Application                         SMTP server
     |                                   |
     |------------- TCP connect ------->|
     |<------------- 220 ---------------|
     |------------- EHLO -------------->|
     |<---------- 250 extensions -------|
     |------------- STARTTLS ---------->|
     |<------------- 220 ---------------|
     |=========== TLS handshake ========|
     |------------- EHLO -------------->|
     |------------- AUTH -------------->|
     |------------- MAIL FROM --------->|
     |------------- RCPT TO ----------->|
     |------------- DATA -------------->|
     |------------- MIME content ------>|
     |<---------- Final response -------|
~~~

**Protocol debug** lets you observe part of this exchange. What appears in a specific transcript depends on the Jakarta Mail provider, debug settings, authentication method, and sending flow.

### 1.1. Which issues is debug useful for?

Examples:

- The application connects to the wrong SMTP host or port.
- The server does not advertise STARTTLS.
- TLS handshake or certificate verification fails.
- The server does not permit SMTP AUTH.
- The server rejects the envelope sender.
- A recipient is rejected at RCPT TO.
- The message is rejected at DATA.
- The provider enforces rate limiting.
- The connection closes mid-session.

Most of these issues can be diagnosed using **error codes, SMTP phase, and metadata** without retaining the entire protocol dialogue.

### 1.2. Debug is not the sole source of truth

A client-side transcript may not show what the mail server does after accepting the message. Even when the application sees SMTP accepted, the provider can still bounce the email during downstream delivery.

Similarly, if the connection drops after DATA before the final response arrives, the application may not know whether the server accepted the message. An incomplete transcript is not enough to declare “definitely not sent”.

## 2. Three log sources that are often confused

| Source | Common activation | What may appear | Scope to control |
| --- | --- | --- | --- |
| **Jakarta Mail debug** | `mail.debug` or `Session.setDebug(...)` | SMTP commands/responses, provider states; details vary by implementation | Session, transport, and stdout/debug stream |
| **Spring/application logging** | SLF4J, Logback, Spring Boot `logging.level` | Exceptions, event IDs, metadata explicitly logged by code | Loggers, application, log pipelines |
| **JSSE/TLS debug** | JVM property `javax.net.debug` | TLS handshake, certificates, protocols, ciphers, and potentially more sensitive data depending on debug mode | Typically affects TLS connections across the JVM |

These three mechanisms do not replace one another.

### 2.1. Jakarta Mail protocol debug

Example in Spring Boot:

~~~yaml
spring:
  mail:
    properties:
      "[mail.debug]": "true"
~~~

Depending on the provider, debug output is often written to **Session debug output**, not necessarily through the SLF4J logger configured by the application.

Therefore, merely setting:

~~~yaml
logging:
  level:
    org.springframework.mail: WARN
~~~

does not guarantee disabling output emitted by **`mail.debug`**. Control the Jakarta Mail `Session` configuration and where the debug stream writes.

### 2.2. Spring/application logging

Example:

~~~java
log.warn(
        "mail.send.failed eventId={} category={}",
        eventId,
        failureCategory
);
~~~

Application logs can be designed more safely because developers explicitly pick which fields to emit. Still, if a developer directly logs **`exception.getMessage()`**, a `MimeMessage` object, or a request payload, the application can still leak data.

### 2.3. JSSE/TLS debug

Example JVM option:

~~~text
-Djavax.net.debug=ssl,handshake
~~~

JSSE debug focuses on TLS handshakes and certificate processing. It is not a full SMTP transcript. Deeper diagnostic modes can expose sensitive TLS details or key material; never enable them broadly in environments with real users.

Thus, when inspecting a STARTTLS failure, choose the narrowest debug level required and control output across the entire JVM.

## 3. Categories of data that can leak

An SMTP transcript may contain many kinds of data. Actual exposure depends on the provider and logging sink.

| Data category | Examples | Risk |
| --- | --- | --- |
| **Authentication data** | Username, AUTH payload, OAuth bearer token | Account takeover or abuse for spam |
| **Contact addresses** | MAIL FROM, RCPT TO | Exposes customer/recipient lists |
| **Message headers** | Subject, From, To, Message-ID | Exposes transactions, identities, conversation topics |
| **Body** | Transactional emails, HTML, plain text | Exposes business or personal data |
| **Attachments** | Invoices, reports, payroll sheets | Bulk exposure of sensitive data |
| **Links/tokens in email** | Account recovery links, magic links | Can lead to account takeover |
| **Infrastructure metadata** | SMTP hostname, port, IP, extensions | Reveals system topology or operational info |
| **Certificate/TLS details** | SANs, chains, handshake data | May reveal PKI structure; deep debug modes are especially sensitive |
| **Provider diagnostics** | Reply text, account/domain policies | May contain addresses, domains, or internal references |
| **Correlation metadata** | Event ID, tenant ID, account alias | Still needs protection if linkable to individuals |

Not every SMTP debug setup prints all of the items above. When assessing risk, inspect **what your current provider version actually emits**, while never building policies assuming future provider versions will mask every sensitive field.

## 4. Authentication data is the most severe risk

SMTP AUTH can use a username/password, app password, or token across different mechanisms.

Conceptual example:

~~~text
C: AUTH PLAIN <base64-payload>
S: 235 Authentication successful
~~~

**Base64 is encoding, not security encryption.** If a payload containing credentials is printed to logs, anyone with log read access can decode and abuse the credential.

### 4.1. AUTH PLAIN and AUTH LOGIN

Some authentication mechanisms encode data in Base64. Never conclude that data “looks unreadable” and is therefore safe.

Never retain:

- Real usernames/passwords.
- App passwords.
- AUTH challenge/responses carrying login data.
- Base64 of credentials.
- Headers or objects holding secrets.

### 4.2. OAuth2 and XOAUTH2

If the application uses OAuth2 for SMTP, an access token is still a **bearer credential**. Anyone holding a valid token can exercise its granted permissions until it expires.

Do not mask only passwords while letting raw OAuth2 tokens slip through debugging. Prevent logging tokens, refresh tokens, and reusable authentication payloads.

### 4.3. Special AUTH debug modes

Some Jakarta Mail/SMTP providers have options like **`mail.debug.auth`** affecting whether authentication details print during debugging. Exact details vary by implementation and version.

**Never enable settings that reveal AUTH transcripts just to diagnose a 535 error.** Even if a version masks AUTH info by default, treat that as a helper guardrail, not a guarantee that raw debug contains zero secrets.

### 4.4. AUTH errors usually do not need credentials in logs

For investigation:

~~~text
smtpAccountAlias=outbound-primary
phase=AUTH
smtpReplyCode=535
enhancedStatus=5.7.8
errorCategory=AUTH_REJECTED
~~~

This information is far more useful than logging the wrong password itself or the rejected OAuth token.

## 5. Risk of exposing recipient addresses

The SMTP envelope includes commands such as:

~~~text
MAIL FROM:<notifications@example.org>
RCPT TO:<customer01@example.net>
RCPT TO:<customer02@example.net>
~~~

If transcripts are logged verbatim, the log system becomes a repository of email recipients.

### 5.1. Bcc can still appear in the envelope

An outgoing MIME message may omit the `Bcc` header, yet Bcc recipients must still be passed to the SMTP server via envelope recipients.

Therefore, **omitting or not logging the `Bcc` header does not mean SMTP transcripts hide Bcc addresses**. `RCPT TO` can reveal them.

### 5.2. Recipient lists are valuable data

For transactional notification systems, `RCPT TO` lists can expose:

- Users registered with the service.
- Customer-to-product relationships.
- Tenants or organizational groups.
- Transaction timing.
- Non-public contacts.

No body content is needed for an SMTP log to impact privacy.

### 5.3. Replace full addresses with references

Log:

~~~text
recipientRef=customer-42
recipientCount=1
~~~

instead of:

~~~text
recipientEmail=customer01@example.net
~~~

If stable correlation across records is needed, use tokenization or **HMAC with a securely managed secret key**. Plain unsalted/unkeyed hashes of email addresses can be guessed against common address lists and are not reliable anonymization.

## 6. Risks to Subject and email content

The **`Subject`** header may contain financial, medical, legal, account-status, or order-number information. The body may carry even finer details.

Hypothetical email example:

~~~text
Subject: Password recovery
Body: Use link https://example.org/reset?token=<secret-token>
~~~

If the body or URL is written to logs, anyone reading logs can steal the account-recovery token before it expires. This is especially dangerous when logs ship to monitoring platforms with broad read access.

### 6.1. OTP codes and magic links

Never log:

- OTP codes.
- Password-reset links.
- Magic login URLs.
- Email verification tokens.
- One-time access codes.
- URLs containing sensitive signed query parameters.

Keeping an event ID and template key suffices for most diagnostic needs.

### 6.2. HTML can contain private URLs

A URL inside an HTML email may carry a recipient token, unsubscribe token, signed URL, or reference to a personal document. Even when visible prose looks harmless, the full HTML may contain secrets.

Never copy HTML bodies into logs merely assuming they are public templates.

### 6.3. Attachments can carry large volumes of sensitive data

MIME messages can hold PDFs, CSVs, images, or reports. In certain capture/debug modes, raw content or Base64 representations of attachments risk being stored.

Base64 of a PDF/CSV does not count as masked content. Anyone holding the data can decode it back into the attachment.

## 7. Metadata risks even without body content

Even a transcript showing only SMTP commands and responses can reveal:

- SMTP provider and host.
- Involved domains.
- When the system sends.
- IPs or routing information.
- Authentication outcomes.
- Sender/recipient addresses.
- Sending rates or retry patterns.
- Internal hostnames inside certificates or greetings.

This can help attackers map infrastructure or craft phishing campaigns.

Accordingly, assess **metadata as potentially sensitive data**, not only bodies and passwords.

## 8. TLS debug does not mean safer logging

An SMTP connection over TLS is encrypted on the wire. However, once the library decrypts data for processing, debug hooks can emit pre-TLS or post-TLS details to output according to their capabilities.

~~~text
SMTP server
     |
     | TLS encrypted traffic
     v
Jakarta Mail / JSSE inside JVM
     |
     +-- Application processes message
     |
     +-- Debug / log output
                |
                v
       stdout / file / log collector
~~~

**TLS protects the network path; it does not automatically encrypt or control access to log files.**

### 8.1. JSSE handshake debug

Example:

~~~text
-Djavax.net.debug=ssl,handshake
~~~

Handshake details can suffice to pinpoint certificate mismatches or protocol negotiation issues. Yet it affects the runtime's JSSE globally, not just a single SMTP send.

Never enable modes that dump TLS key material or ultra-verbose debugging in production without dedicated security procedures.

### 8.2. Certificate chains also contain information

Certificates may contain domains, SANs, or organization names. While mostly non-secret in public certificates, they can still expose internal infrastructure or endpoints when aggregated into centralized logs.

### 8.3. Do not use debug as a substitute for hostname verification

When hitting TLS certificate errors, fix the trust chain, SAN, hostname, or TLS configuration. Never disable hostname verification or enable trust-all just to make connections succeed.

## 9. A short threat model for SMTP debug

A risk assessment should answer four questions:

1. **Assets:** what data can enter the logs?
2. **Actors:** who can read, edit, copy, or export the logs?
3. **Leak paths:** through which systems and storage locations do logs flow?
4. **Impact:** if data is accessed without authorization, what is the consequence?

### 9.1. Actors to consider

| Actor | Access potential |
| --- | --- |
| Developer with app-log read access | Can triage incidents, though not necessarily authorized to see secrets/PII |
| Operations/support staff | May access collectors, dashboards, or dump files |
| CI/CD pipelines | May retain logs in artifacts or job outputs |
| Observability vendors | May retain copies under contract and retention settings |
| User accessing a compromised dashboard | Can search historical log data |
| Attacker stealing a log-API token | Can download or query logs remotely |
| Screenshot/ticket recipients | May inadvertently receive shared log snippets |

A log incident does not have to start with an external attacker. **Overly broad read permissions or pasting transcripts into tickets** are also data-exposure paths.

### 9.2. Commonly overlooked paths

~~~text
Jakarta Mail debug
       |
       +-- System.out / stderr
       |       |
       |       +-- Container logs
       |       +-- Kubernetes logging agent
       |
       +-- File log
       |       |
       |       +-- Rotation archive
       |       +-- Backup / snapshot
       |
       +-- Central log pipeline
               |
               +-- Search dashboard
               +-- Alert payload
               +-- Ticket / incident report
               +-- Third-party retention
~~~

Once data enters a collector, deleting it from current stdout rarely removes historical copies.

## 10. Illustrative risk matrix

You can use a qualitative **likelihood × impact** model to prioritize safeguards. The levels below are examples for a transactional email system; adjust them to your actual data, architecture, and access controls.

| Scenario | Likelihood if broad raw debug is on | Impact | Priority |
| --- | --- | --- | --- |
| AUTH payload leaks active credentials | Depends on provider/debug settings; assume critical if enabled | Very high: sending account takeover | Very high |
| Password-reset token in body captured | Depends on whether body is logged | Very high: account takeover risk | Very high |
| `RCPT TO` leaks customer list | High when logging raw SMTP commands | High: personal data leak | High |
| `Subject` contains transaction details | Depends on header capture | Medium–high | High |
| Attachments written to transcript/capture | Depends on implementation/capture mode | Can be very high | High |
| Host/port and TLS capabilities logged | Often appears | Low–medium depending on infrastructure | Medium |
| Logs forwarded to multiple providers | Depends on pipeline | Expands access scope and retention | High |
| Debug left on after incident resolution | Likely without expiry/owner | Increases accumulated sensitive data | High |
| Unredacted logs only in synthetic test env | Lower if strictly zero real data | Depends on environment controls | Needs governance |

Never treat this table as a claim that all providers log bodies or credentials. Assess against the actual output of your active version and treat **unknown** as a reason to restrict debug rather than assuming it is harmless.

## 11. Access scope is part of the risk level

The exact same transcript carries different impact when:

- Only one engineer receives temporary access.
- Every engineering employee can search it on a dashboard.
- Logs upload to a SaaS tool with sharing permissions.
- Contents are pasted into a public issue.
- Files remain indefinitely inside build artifacts.

A safe policy applies **least privilege**:

- Grant access only to personnel directly resolving the incident.
- Audit log access.
- Every export must have a clear purpose and policy approval.
- Never treat deploy permission as implicit permission to read user email contents.
- Separate metadata visibility from sensitive data access.
- Revoke temporary access once the investigation closes.

## 12. Retention and log copies

A system might turn debug on for ten minutes while logs remain retained for months.

Determine:

- Retention on container nodes.
- Retention in log collectors.
- Retention in backups.
- Whether alerts or tickets copy log lines.
- Whether exports sit on personal laptops.
- Deletion or retention enforcement capabilities at third-party vendors.
- Who is authorized to request deletion and how it is verified.

**Turning debug off only stops new collection; it does not erase data already recorded.** If credentials or tokens leaked, evaluate revocation/rotation independently of log deletion.

### 12.1. Do not keep raw transcripts longer than troubleshooting needs

If a transcript is truly needed to crack a hard bug, enforce short retention and assign an owner responsible for ending access. Never use transcripts as default operational reporting logs.

### 12.2. Even sanitized logs require limits

Even event IDs or recipient references can still link back to users via another database. Pseudonymization reduces direct exposure, yet does not make data completely anonymous.

## 13. Secure-by-default Spring Boot configuration

Baseline configuration:

~~~yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "10000"
      "[mail.smtp.writetimeout]": "10000"
      "[mail.debug]": "false"
      "[mail.debug.auth]": "false"
~~~

**`mail.debug=false`** explicitly states the intent not to emit Jakarta Mail transcripts by default.

**`mail.debug.auth=false`** is a defensive setting on providers that support it; do not treat it as the sole filter or a guarantee that every sensitive detail is hidden. Versions vary, so the safe policy remains **do not enable raw protocol debugging in normal production traffic**.

Host, port, and timeout values are illustrative; tune them to your provider and SLAs.

### 13.1. `application.properties` format

~~~properties
spring.mail.host=smtp.example.org
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}

spring.mail.properties[mail.smtp.auth]=true
spring.mail.properties[mail.smtp.starttls.enable]=true
spring.mail.properties[mail.smtp.starttls.required]=true
spring.mail.properties[mail.smtp.ssl.checkserveridentity]=true

spring.mail.properties[mail.debug]=false
spring.mail.properties[mail.debug.auth]=false

spring.mail.properties[mail.smtp.connectiontimeout]=5000
spring.mail.properties[mail.smtp.timeout]=10000
spring.mail.properties[mail.smtp.writetimeout]=10000
~~~

Never store real usernames/passwords or tokens in repositories. Use a secret manager or your deployment environment's secret mechanism.

### 13.2. Changing `logging.level` alone is not enough

An easy mistake:

~~~yaml
logging:
  level:
    org.springframework.mail: INFO
~~~

This controls loggers in the Spring namespace, **without reliably disabling Jakarta Mail `Session` debug if `mail.debug=true`**.

Check JavaMail properties, `Session` debug, JVM TLS debug, and runtime stdout/stderr collectors together.

## 14. Risks of enabling debug via the Java API

Jakarta Mail `Session` has a debug API:

~~~java
Session session = Session.getInstance(properties);
session.setDebug(true);
~~~

And some applications may obtain `JavaMailSenderImpl`'s `Session` to toggle debug at runtime.

Proceed cautiously because a `Session` may be shared across multiple messages or threads. A debug toggle meant “just for the current email” can affect other emails processing concurrently.

### 14.1. Do not turn on global debug to investigate one recipient

If an SMTP `Session` is shared, enabling debug while sending can record transcripts for many recipients and unrelated business flows.

Better options:

- Reproduce the bug with a test SMTP account and synthetic data.
- Spin up an isolated diagnostic environment.
- Log metadata tied to a correlation ID.
- If raw debug is strictly required, isolate scope with a separate process/configuration.
- End debugging and purge diagnostic data per retention rules.

### 14.2. Do not swap `System.out` arbitrarily

When debug writes to stdout, container logging infrastructure may collect it. Swapping streams inside the JVM affects other code and is not a durable redaction strategy.

Control log emission at the source and collection paths rather than trying to “post-filter” everything on stdout.

## 15. Redaction: what to do and where its limits are

**Redaction** removes or masks sensitive data before storage or sharing.

Sanitized log example:

~~~text
eventId=mail-456
senderAlias=outbound-primary
recipientRef=user-42
phase=AUTH
smtpReply=535
enhancedStatus=5.7.8
category=AUTH_REJECTED
~~~

Instead of:

~~~text
AUTH PLAIN <encoded-credentials>
MAIL FROM:<notifications@example.org>
RCPT TO:<customer01@example.net>
~~~

### 15.1. Prefer never generating sensitive log data

The best control is **keeping raw transcripts out of the logging pipeline**. When the app logs only allowlisted fields from the start, redaction burden drops sharply.

### 15.2. Regex redaction is insufficient to clean SMTP transcripts

A regex matching `@` signs or the word `password` cannot reliably handle:

- Base64 AUTH payloads.
- OAuth2 tokens in varying payload structures.
- Tokens inside URLs.
- Multi-line folded headers.
- Quoted-printable/Base64 MIME bodies.
- Escape sequences or new log formats.
- Partial lines or multiple commands in one buffer.
- Changing provider diagnostics.

Therefore, **never rely on regexes over raw debug as your sole security barrier**.

### 15.3. If raw logs must be processed

Follow a strict workflow:

1. Isolate the source and access permissions.
2. Never send unredacted originals into broad-access collectors.
3. Classify and strip secrets/PII with parsers built for the actual format.
4. Test multi-line, Base64, token, and malformed payload cases.
5. Inspect sanitized outputs before sharing.
6. Retain originals only under special policy and short retention if strictly necessary.

Never label logs “sanitized” until actual scrubbing effectiveness is verified.

## 16. Structured logging as an alternative to raw SMTP debug

Instead of dumping every SMTP command, the service can emit structured events. Fields typically sufficient for operations include:

~~~text
eventId
smtpAccountAlias
smtpProvider
smtpPhase
smtpReplyCode
enhancedStatusCode
errorCategory
attemptNumber
nextAttemptAt
durationMillis
connectionMode
outcomeStatus
~~~

A recipient reference can be included instead of a full email address, while considering linkability back to users.

### 16.1. Minimal Spring logging service example

~~~java
import jakarta.mail.internet.MimeMessage;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.mail.MailAuthenticationException;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class ObservedMailDeliveryService {

    private static final Logger log =
            LoggerFactory.getLogger(ObservedMailDeliveryService.class);

    private final JavaMailSender mailSender;

    public ObservedMailDeliveryService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void submit(
            MimeMessage message,
            String eventId,
            String smtpAccountAlias,
            int attempt
    ) {
        long start = System.nanoTime();

        try {
            mailSender.send(message);

            log.info(
                    "mail.submit eventId={} account={} attempt={} "
                  + "result=SMTP_SUBMIT_OK durationMs={}",
                    eventId,
                    smtpAccountAlias,
                    attempt,
                    elapsedMillis(start)
            );
        } catch (MailAuthenticationException ex) {
            log.warn(
                    "mail.submit eventId={} account={} attempt={} "
                  + "result=FAILED category=AUTH durationMs={}",
                    eventId,
                    smtpAccountAlias,
                    attempt,
                    elapsedMillis(start)
            );
            throw ex;
        } catch (MailException ex) {
            log.warn(
                    "mail.submit eventId={} account={} attempt={} "
                  + "result=FAILED category=NEEDS_CLASSIFICATION durationMs={}",
                    eventId,
                    smtpAccountAlias,
                    attempt,
                    elapsedMillis(start)
            );
            throw ex;
        }
    }

    private static long elapsedMillis(long start) {
        return java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - start
        );
    }
}
~~~

This example never logs recipients, subjects, bodies, attachments, passwords, or exception messages. **`SMTP_SUBMIT_OK`** only reflects that the send call completed normally—it does not guarantee the email reached the inbox or was read.

### 16.2. Deep error classification does not require printing exception messages

An adapter can extract **reply codes**, **enhanced status codes**, and **phase** from structured Jakarta Mail provider exceptions. Log only required fields after confirming they contain no PII.

Avoid doing this:

~~~java
log.error("SMTP failed: {}", ex.getMessage());
~~~

assuming error messages are always harmless. Some messages embed addresses, hostnames, server responses, or other details.

### 16.3. Do not disable all logging

You do not have to choose between **full raw transcripts** and **knowing nothing about the system**. Structured logs, metrics, and tracing provide better observability for most common issues while limiting sensitive data.

## 17. Which metrics can be collected with lower risk?

Useful aggregate metrics:

| Metric | Purpose |
| --- | --- |
| Successful SMTP submit count | Monitor traffic volume |
| AUTH failure rate by account alias | Detect misconfigurations or bad credentials |
| 4xx/5xx rate by provider | Detect throttling and policy rejections |
| Connection timeouts | Monitor network stability |
| TLS handshake failures | Detect certificate/protocol issues |
| Send completion duration | Locate bottlenecks |
| Outbox backlog | Monitor unsent task counts |
| Average retry count | Assess reliability |
| `UNKNOWN_OUTCOME` count | Monitor duplicate-risk windows |
| Accepted-by-relay vs. later bounce | Distinguish SMTP acceptance from delivery |

Avoid putting full emails, tokens, or ultra-high-cardinality event IDs into metric labels. Metric platforms are generally unsuitable for user-identifying fields or per-message unique values.

## 18. Correlation IDs and reconciliation

A stable **event ID** connects steps across the pipeline:

~~~text
Business transaction
       |
       v
Outbox eventId=mail-456
       |
       v
Worker attempt=1
       |
       v
SMTP AUTH / RCPT TO / DATA
       |
       v
Accepted-by-relay or failure status
~~~

Benefits:

- No need to log `Subject` and body to know which email failed.
- Can compare retries of the same job.
- Supports reconciliation with the provider when it supplies message references.
- Helps manage duplicate windows.

Event IDs must not directly embed credentials or sensitive details. If an ID can be traced back to an individual, enforce access controls on it as well.

### 18.1. `Message-ID` can help, yet is not enough

MIME `Message-ID` helps identify messages at the email layer. However:

- It does not guarantee exactly-once SMTP delivery.
- Some providers rewrite the header or supply their own IDs.
- `Message-ID` must not be treated as proof a recipient read the email.

Store both the application correlation ID and provider-returned IDs when available.

## 19. Using fake SMTP or capture servers to lower risk

When full protocol visibility is needed, the safer option is usually **reproducing with synthetic data on an SMTP test server**.

Example test setup:

~~~text
Spring application (test profile)
            |
            v
Local/test SMTP capture server
            |
            +-- Dummy sender data
            +-- example.net addresses
            +-- Unprivileged dummy token
            +-- Dummy attachment
            |
            v
Investigation
~~~

Benefits:

- Uses no production credentials.
- Sends to no real recipients.
- Tests STARTTLS, AUTH, RCPT TO, or DATA scenarios cleanly.
- Lets you capture entire messages using non-sensitive data.
- Avoids turning debug on across production traffic.

### 19.1. Do not copy raw production data into tests

If reproducing from a production snapshot, data may still be sensitive. Replace recipients, tokens, content, and attachments with structurally equivalent synthetic data.

A dummy token must genuinely carry zero permissions—never an expired real token lifted verbatim from logs.

### 19.2. When a test server cannot reproduce a provider bug

Some failures occur only against the real provider, such as rate limiting or tenant policies. You may need to log metadata from real responses while still avoiding raw transcripts and secrets. Enable broader diagnostics only via an approved exception workflow.

## 20. Controlled debug-enablement procedure when truly needed

If structured logging is insufficient and the issue cannot be reproduced in test environments, follow a clear procedure.

### 20.1. Before enabling

1. Document the **investigation goal**: e.g., STARTTLS negotiation failure.
2. Identify the **source to observe**: Jakarta Mail or JSSE; do not turn on every debug mode.
3. Assign an **owner** and authorized log viewers.
4. Scope **account, host, time window, and environment** to diagnose.
5. Confirm which data may appear and its sensitivity.
6. Set an **auto-off deadline** or configuration rollback plan.
7. Check log pipelines and retention of every copy.
8. Prepare a restricted storage channel instead of broad dashboards.
9. Whenever feasible, use test accounts and dummy recipients.
10. Define clear stop conditions for ending collection.

### 20.2. While enabled

- Trigger only the minimum sends needed.
- Do not launch bulk retries.
- Avoid emails carrying live tokens, sensitive attachments, or real user data whenever possible.
- Watch output live and stop immediately if credentials or sensitive info appear.
- Never paste raw transcripts into broad-access chat, tickets, or issues.
- Avoid enabling debug across multiple instances simultaneously if one instance suffices.

### 20.3. After enabling

1. Disable the debug flag and verify on the running runtime.
2. Check stdout/stderr, files, collectors, and created exports.
3. Save needed findings strictly as sanitized notes.
4. Purge raw copies per policy and verify deletion scope where feasible.
5. Revoke temporary access permissions.
6. If credentials/tokens appeared, execute rotation/revocation.
7. Update runbooks so future incidents rely less on raw debug.

**Without a closing step, “temporary debug” easily turns into a permanent configuration.**

## 21. Incident response if logs already captured secrets

Upon discovering that SMTP debug may have recorded credentials or tokenized links:

~~~text
Detect potential leak
        |
        v
Disable debug / stop further exposure
        |
        v
Identify log sinks and access scope
        |
        v
Contain access / exports
        |
        v
Revoke or rotate affected secrets
        |
        v
Assess data exposure and obligations
        |
        v
Remove retained copies where possible
        |
        v
Document incident and improve controls
~~~

### 21.1. Prioritize stopping further exposure

Do not merely delete one log file while leaving debug running. Shut off the emitting source and block new writes to unsuitable sinks.

### 21.2. Credentials must be revoked/rotated

If an SMTP password, app password, or OAuth token was written to an untrusted location, deleting the log does not guarantee the secret wasn't copied. Evaluate rotation or revocation per policy.

For password-reset or magic-login links, invalidate active tokens and issue fresh links if legitimate need remains.

### 21.3. Determine the blast radius

Questions:

- From when to when was debug enabled?
- Which instances were affected?
- Which collectors ingested the logs?
- Who viewed or downloaded them?
- What data could reside in the transcripts?
- Do backups, alerts, tickets, or attachments hold copies?
- Are there legal, policy, or contractual incident-reporting obligations?

Never claim “nothing leaked” merely because a record isn't visible on today's dashboard.

## 22. Debug policies across environments

| Environment | Suggested policy |
| --- | --- |
| **Local with dummy data** | May enable under control; avoid real credentials |
| **Unit/integration tests** | Prefer fake transports or SMTP capture; test secrets only |
| **Staging** | Off by default; case-by-case, synthetic data, limited retention |
| **Production** | Off by default; intentional, narrow, time-bounded exceptions only |
| **Incident environment** | Isolated, temporary access, audited, managed outputs |
| **CI/CD** | Never print secrets; block broad debug and protect build artifacts |

A staging profile is not automatically safe if it connects to a real provider or uses production data. Evaluate actual data and access rights, not merely environment names.

## 23. Practical configurations and anti-patterns

### 23.1. Anti-pattern: leaving raw debug on permanently in shared config

~~~yaml
spring:
  mail:
    properties:
      "[mail.debug]": "true"
~~~

If this config applies across all environments, every instance continuously emits transcripts containing metadata or sensitive data.

### 23.2. Anti-pattern: enabling extra AUTH debugging

~~~properties
spring.mail.properties[mail.debug.auth]=true
~~~

Where supported by providers, this option can reveal authentication details normally masked. Never use it as a routine way to troubleshoot SMTP AUTH errors.

### 23.3. Anti-pattern: logging whole objects or raw MIME

~~~java
log.debug("Message: {}", message);
~~~

Object formatting depends on implementation and is not a redaction contract. Nor should you call **`writeTo(...)`** to dump an entire MIME message into a logger just to confirm the email was built.

### 23.4. Anti-pattern: logging every exception message

~~~java
log.error("SMTP error: " + exception.getMessage());
~~~

Provider-returned diagnostic text may contain recipients, hosts, or other details. Extract and allowlist needed fields; never assume every error string is safe.

### 23.5. Anti-pattern: disabling TLS to make debugging easier

Turning off STARTTLS/hostname verification changes real security behavior and can send authentication data over an insecure channel. If you need to inspect handshakes, use scoped JSSE debug rather than intentionally downgrading connections.

## 24. Checklist for designing a safe log event

A diagnostic log event for email sending should answer:

- **Which task?** Non-sensitive event ID.
- **Which account/host?** Permitted alias or ID.
- **Which phase?** `CONNECT`, `TLS`, `AUTH`, `MAIL FROM`, `RCPT TO`, `DATA`, `AFTER_DATA`.
- **Which outcome?** Accepted by relay, temporary failure, permanent failure, unknown.
- **Which code?** SMTP 4xx/5xx and enhanced code if reliable.
- **How many attempts?** Attempt count.
- **When to retry?** Next attempt time.
- **How long?** Duration.
- **Redacted?** No credentials, bodies, or unnecessary PII.
- **Who can view?** Read permissions and auditing.
- **How long retained?** Explicit retention.

Not every event needs every field; the goal is recording **just enough information to decide the next action**.

### 24.1. Success log example

~~~text
mail.submit
eventId=mail-456
accountAlias=primary
result=SMTP_SUBMIT_OK
durationMs=812
~~~

### 24.2. Authentication error log example

~~~text
mail.submit
eventId=mail-456
accountAlias=primary
phase=AUTH
smtpReply=535
enhancedStatus=5.7.8
category=AUTH_CONFIGURATION
decision=PAUSE_ACCOUNT
~~~

### 24.3. Recipient error log example

~~~text
mail.submit
eventId=mail-457
recipientRef=customer-42
phase=RCPT_TO
smtpReply=550
enhancedStatus=5.1.1
category=RECIPIENT_REJECTED
decision=NEEDS_ADDRESS_CORRECTION
~~~

### 24.4. Indeterminate outcome example

~~~text
mail.submit
eventId=mail-458
phase=AFTER_DATA
category=UNKNOWN_OUTCOME
decision=REVIEW_DUPLICATE_RISK
~~~

These normalized field names are application design patterns, not built-in properties or enums in `JavaMailSender`.

## 25. Testing logging policies before deployment

A test suite should focus on **actual log emission behavior**, not merely inspecting config files:

1. Run a successful send flow with synthetic data.
2. Trigger an AUTH error using a fake SMTP server.
3. Trigger an `RCPT TO` error for a dummy recipient.
4. Trigger a STARTTLS/certificate error against a test TLS endpoint.
5. Inspect output from application loggers, stdout/stderr, and test collectors.
6. Confirm dummy secrets and canary tokens never appear in logs.
7. Confirm event IDs, phases, categories, and error codes suffice for diagnosis.
8. Verify disabling debug actually stops new transcripts.
9. Check log paths in containers and build artifacts.
10. Verify retention/permissions align with environment policy.

### 25.1. Canary secrets must be dummy values

Create test-only dummy passwords/tokens—such as a string with a distinct marker carrying **zero real permissions**. Never use production credentials as canaries.

### 25.2. Do not test only a single pattern

A secret can appear:

- Verbatim.
- Base64-encoded.
- URL-encoded.
- In MIME quoted-printable.
- Split across multiple lines/chunks.
- Inside stack traces or provider diagnostics.

The goal is **preventing unnecessary data from entering logs**, not only catching a single raw string after it was written.

### 25.3. Log emission tests are not email-content QA

Logging tests protect secrets/PII and observability. They are separate from verifying how email clients render HTML or whether providers deliver to inboxes.

## 26. Practical scenario: SMTP AUTH returns 535

Suppose the service records:

~~~text
MailAuthenticationException
SMTP AUTH rejected
Reply: 535 5.7.8
~~~

**You do not need `mail.debug.auth=true` to find out which password is being sent.** If configuration is wrong, printing passwords to logs only creates extra risk.

A sound workflow:

1. Identify the sender account alias and environment.
2. Check whether the secret reference points to the right version.
3. Confirm SMTP AUTH is permitted at the provider.
4. Check the right authentication method: app password, OAuth2, or another mechanism.
5. Check whether STARTTLS/implicit TLS works for the endpoint.
6. If token refresh is involved, check token status via a separate secure channel.
7. Pause blind retries on the account if the error is persistent.
8. Once fixed, retry under control.
9. Log the event category and outcome, never credentials.

If the provider returns a temporary error, such as AUTH 454, you can retry with backoff. Yet a 535 AUTH rejection is never fixed by logging or repeatedly hammering real passwords.

## 27. Practical scenario: recipient error

Suppose SMTP returns:

~~~text
550 5.1.1 User unknown
~~~

You do not need to store the full address at `RCPT TO` to know which recipient needs handling if the system already tracks correlation IDs and recipient references.

Workflow:

1. Link the response to the mail event and recipient reference.
2. Confirm the phase is `RCPT TO` and the enhanced code is reliable.
3. Distinguish user unknown from policy errors like `550 5.7.1`.
4. Update the recipient/mail job status appropriately.
5. Never retry as-is an address confirmed nonexistent.
6. Keep real addresses out of broad-access dashboards when unnecessary.

Do not suppress every recipient solely based on the three-digit SMTP code `550`. Inspect the enhanced status code and provider context.

## 28. Practical scenario: STARTTLS handshake fails

Suppose Spring Mail reports:

~~~text
MailSendException
    |
    v
MessagingException
    |
    v
SSLHandshakeException
    |
    v
PKIX path building failed
~~~

A full SMTP transcript may not even be needed. You can:

1. Verify host, port, and TLS mode.
2. Inspect the certificate chain and SAN using an authorized TLS tool.
3. Identify the actual truststore used by the JDK/container.
4. Enable minimal JSSE handshake debug in an isolated environment if needed.
5. Never disable certificate verification or enable trust-all.
6. Log the outcome as error category, host alias, and TLS phase.

TLS handshake debugging must also be governed because it can expose certificates/internal topology and generate huge JVM-wide log volume.

## 29. Frequently asked questions

**1. Is enabling `mail.debug` dangerous?**

It can be. It may emit SMTP session details and metadata depending on provider and configuration. If output goes into broad-access logs or captures secrets/PII, risk is high. Disable it by default in production.

**2. Does SMTP debug always print passwords?**

Not every provider or setup prints passwords. Some have AUTH masking mechanisms. Still, never treat that as a guarantee. Especially avoid options that reveal authentication details.

**3. Is Base64-encoded `AUTH PLAIN` safe to log?**

No. Base64 is trivially decoded. A payload holding credentials remains a secret.

**4. What is `mail.debug.auth=true` for?**

Some SMTP providers use this property to control debugging of AUTH details. It can expose sensitive data and should never be enabled as routine troubleshooting.

**5. Once STARTTLS is enabled, are logs encrypted?**

Not automatically. STARTTLS protects the SMTP network hop. Logs written by the app/transport flow through a different pipeline with its own protection policies.

**6. Can lowering Spring's `logging.level` turn off transcripts?**

Not reliably. Jakarta Mail `Session` debug and JSSE debug can bypass Spring/SLF4J loggers.

**7. Why can `RCPT TO` expose Bcc?**

Bcc recipients must still be sent as envelope recipients to the SMTP server even though the `Bcc` header is omitted from the outgoing message body. Thus transcripts can expose Bcc addresses.

**8. Should `Subject` be logged to debug emails?**

Usually unnecessary. `Subject` may contain personal or business data. Use template keys and event IDs instead whenever possible.

**9. Can a full Base64 `MimeMessage` be logged?**

No. Base64 MIME can still be decoded and contains attachments, personal data, or tokens.

**10. Should `exception.getMessage()` be logged?**

Be cautious. Provider messages may contain recipients, accounts, or other details. Prefer extracting security-reviewed structured fields.

**11. Should `javax.net.debug` be enabled in production?**

Only in exceptional diagnostic cases with minimal scope and strict controls. This property affects the JVM broadly. Never enable ultra-verbose TLS debugging or key-material logging without specialized security procedures.

**12. Is regex redaction enough?**

Insufficient to guarantee safety because data can appear Base64-encoded, URL-encoded, multi-line, or in provider-specific formats. Prefer never emitting raw secrets in the first place.

**13. Can SHA-256 of an email be used instead of the full address?**

Plain hashes of addresses can be dictionary-attacked. If stable correlation is required, consider HMAC with a managed secret or dedicated mapping IDs alongside access control and retention limits.

**14. Does turning debug off delete old logs?**

No. Check files, stdout collectors, backups, alerts, and exports across your actual pipelines.

**15. What should be done if an SMTP password was accidentally logged?**

Stop new writes, scope copies and viewers, evaluate credential rotation/revocation, handle logs per policy, and review incident-reporting obligations if applicable.

**16. Can AUTH 535 be diagnosed without logging the AUTH payload?**

Yes. Usually account alias, AUTH phase, code 535, enhanced status, and provider config suffice, followed by checking the secret via a protected channel.

**17. Does SMTP debug prove the recipient read the email?**

No. It covers only the client–server connection and SMTP responses. Delivery and reads are separate milestones.

**18. Is there any completely risk-free way to view raw protocol traffic?**

No absolute guarantee exists. You can reduce risk via synthetic data, isolated environments, restricted permissions, short durations, blocking secrets, and purging copies after investigation.

## 30. Key takeaways when assessing SMTP debug risks

**SMTP debug is a diagnostic tool, not default operational logging.** Depending on provider and configuration, transcripts may capture commands/responses, senders, recipients, domains, authentication data, or message content. In particular, Base64 AUTH payloads, OAuth tokens, password-reset links, OTPs, and attachments do not become safe merely by being encoded or sent over TLS.

In Spring Framework Mail, distinguish **`mail.debug`**, **application logging**, and **`javax.net.debug`**. Toggling Spring loggers does not automatically govern `Session` debug. TLS protects the connection to the SMTP server, yet does not automatically protect stdout, log files, collectors, tickets, or exports.

Prefer **allowlist-based structured logging** containing event ID, account alias, SMTP phase, reply code, error category, attempt count, and duration. Avoid storing raw MIME, credentials, and recipient data unnecessarily. For tough bugs, use an SMTP test server with dummy data first; enable real debugging only under a workflow with a clear owner, narrow scope, restricted access, defined retention, and explicit cutoff time.

If logs have captured secrets, **stop the leak source, restrict access, locate copies, and evaluate revoking/rotating credentials**. The goal of safe diagnostics is gathering enough signal to fix SMTP errors without turning your logging system into a channel leaking email data and authentication credentials.
