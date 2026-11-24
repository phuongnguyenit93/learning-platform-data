# Testing with a Fake Mail Server and Avoiding Sending to Real Recipients

## 1. Why Does Email Testing Need a Fake Mail Server?

In a **Spring Boot Integration** service, sending email is just one of many integration points: an HTTP request creating an order might write to PostgreSQL, publish an event to Kafka, and then request a confirmation email; a scheduled job might send reports, sync failure alerts, or password-reset links. If development and CI environments connect directly to a real SMTP server, a single test run, event replay, or accidentally triggered scheduler can send emails to customers before behavior is verified.

A **fake mail server** (SMTP sandbox/capture server) accepts mail-sending commands like a real SMTP server at the protocol level, stores the messages for inspection, and **never forwards mail to the Internet** unless a relay is explicitly configured. Two popular choices are:

- **Mailpit:** runs as a separate service in Docker or locally; provides an SMTP endpoint, web UI, and HTTP API to inspect captured emails.
- **GreenMail:** an in-process fake mail server running in the same JVM/test process or as a service; ideal for integration tests that need to start the server programmatically, inspect received messages, and reset state between tests.

MailHog and other SMTP capture servers can also be used if they meet your requirements. Speaking SMTP does not mean they simulate full multi-hop mail delivery, spam filters, real recipient mailboxes, or every authentication policy of a production mail provider.

### Desired Testing Flow

~~~mermaid
flowchart LR
    Test["JUnit / HTTP test / consumer test"] --> Service["Spring Boot: EmailService"]
    Service --> Guard["Recipient guard + enable switch"]
    Guard --> Sender["JavaMailSender"]
    Sender --> Capture["Mailpit SMTP :1025"]
    Capture --> UI["Mailpit UI / API :8025"]
    Guard -. "Reject non-sandbox addresses" .-> Blocked["Invalid To/Cc/Bcc"]
    Capture -. "No outbound relay configured" .-> Internet["Internet / real mailboxes"]
~~~

The testing goal is to prove **the application constructs the right email, delivers it to the fake SMTP server, handles failures properly, and never sends to real people**. Mailpit's UI aids manual inspection; its HTTP API or GreenMail enables automated assertions. For defense in depth, beyond local SMTP settings, add guards in application code and at the network layer.

## 2. Distinguishing Unit Tests, Integration Tests, and Real Delivery Testing

| Level | Method | What It Can Prove | What You Must Not Conclude |
|---|---|---|---|
| Unit test | Mock/fake `JavaMailSender`, template renderer, policy | Input payload, content, recipients, guards, and simulated error cases | Real SMTP connectivity or server MIME acceptance |
| Integration test with SMTP capture | Running Mailpit/GreenMail, app sends over SMTP | SMTP connection, envelope, headers, subject, HTML/text, attachments, simulated faults | Email reached an Internet mailbox or passed spam filters |
| End-to-end with provider sandbox | Dedicated test account on an email provider | Configuration/provider API/SMTP closer to production | Deliverability to all real mailboxes |
| Controlled production delivery check | Organization-owned test mailboxes in an approved environment | Actual delivery to selected target systems | Zero lost/delayed mail across every external provider |

`JavaMailSender.send(...)` returning normally tells you the application handed the message to the SMTP server and it was accepted at that protocol step. **It does not prove the recipient read it or that it reached the Inbox.** That is the contract boundary between your application and the SMTP server.

## 3. Starting an Isolated Mailpit Instance for Local Environments

Example `compose.yaml`:

~~~yaml
services:
  mailpit:
    image: axllent/mailpit:latest
    ports:
      - "127.0.0.1:1025:1025" # SMTP capture
      - "127.0.0.1:8025:8025" # Web UI and HTTP API
~~~

Run in the directory containing the Compose file:

~~~bash
docker compose up -d mailpit
~~~

Open `http://127.0.0.1:8025` to view the captured inbox. The SMTP endpoint for an application running **on the host machine** is `127.0.0.1:1025`. If Spring Boot runs inside **another container on the same Docker network**, the host should be the service name `mailpit` and port `1025` (not `localhost` inside the app container).

Using `latest` is for quick experimentation; in CI/production-like tests, **pin a verified Docker image tag/digest** to avoid unexpected behavior changes across runs.

By default, Mailpit **captures and holds messages for inspection** without requiring a real provider SMTP account or configuring an SMTP relay. Never enable forwarding/relay options in a test environment whose purpose is preventing outbound leakage. Bind the management UI to loopback only in local examples; in CI or shared machines, isolate the network and restrict access to captured emails because contents may include sensitive data.

### Configuring the Spring Boot `email-sandbox` Profile

Maven dependency for Spring Boot versions supporting the mail starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
~~~

`src/main/resources/application-email-sandbox.yml`:

~~~yaml
spring:
  mail:
    host: ${MAIL_CAPTURE_HOST:127.0.0.1}
    port: ${MAIL_CAPTURE_PORT:1025}
    test-connection: false
    properties:
      mail:
        smtp:
          auth: false
          starttls:
            enable: false
          connectiontimeout: 2000
          timeout: 3000
          writetimeout: 3000

app:
  email:
    enabled: true
    sandbox: true
    allowed-domain: example.test
~~~

Activate only for local/test runs, e.g., `SPRING_PROFILES_ACTIVE=email-sandbox`. The domain `example.test` is a **reserved testing domain** by DNS convention, convenient for fixtures such as `customer-1@example.test`. In this environment, do not configure real provider `spring.mail.username` or `spring.mail.password`. The SMTP timeout properties prevent requests from hanging indefinitely when the simulated server is unavailable.

At runtime, a profile only selects a property set. Profiles can be activated by mistake or overridden by environment variables; therefore **a profile alone is not sufficient as the sole protective barrier**.

## 4. Designing an In-App Guard to Block Real Recipients

An email can contain recipients in **To, Cc, and Bcc**, and various integration tasks can invoke sending from HTTP handlers, message consumers, or schedulers. If you only validate the `to` parameter in one controller while another code path sets `bcc` directly, real addresses can still leak.

Design a central gateway: all business code must create and send emails through it. The gateway **disables outbound sending by default**, and when sandbox mode is active it checks **all recipients** right before calling `JavaMailSender.send`.

~~~java
package example.integration.email;

import jakarta.mail.Address;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;
import java.util.Locale;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;

@Component
public final class GuardedMailGateway {
    private final JavaMailSender sender;
    private final boolean enabled;
    private final boolean sandbox;
    private final String allowedDomain;

    public GuardedMailGateway(
            JavaMailSender sender,
            @Value("${app.email.enabled:false}") boolean enabled,
            @Value("${app.email.sandbox:true}") boolean sandbox,
            @Value("${app.email.allowed-domain:example.test}") String allowedDomain) {
        this.sender = sender;
        this.enabled = enabled;
        this.sandbox = sandbox;
        this.allowedDomain = allowedDomain.toLowerCase(Locale.ROOT);
    }

    public MimeMessage newMessage() {
        return sender.createMimeMessage();
    }

    public void send(MimeMessage message) throws MessagingException {
        if (!enabled) {
            throw new IllegalStateException("Email outbound is disabled");
        }
        if (sandbox) {
            Address[] recipients = message.getAllRecipients(); // To + Cc + Bcc
            if (recipients == null || recipients.length == 0) {
                throw new IllegalArgumentException("No recipients");
            }
            for (Address address : recipients) {
                if (!(address instanceof InternetAddress email)) {
                    throw new IllegalArgumentException("Unsupported address type");
                }
                email.validate();
                String raw = email.getAddress();
                int at = raw == null ? -1 : raw.lastIndexOf('@');
                if (at <= 0 ||
                    !raw.substring(at + 1).toLowerCase(Locale.ROOT)
                        .equals(allowedDomain)) {
                    throw new IllegalArgumentException(
                        "Recipient outside email sandbox");
                }
            }
        }
        sender.send(message);
    }
}
~~~

Only an **exact domain match** for `example.test` is allowed; an address like `user@example.test.evil.invalid` is rejected. String checks like `endsWith("test")` or `contains("example.test")` are easily bypassed and unsafe. `InternetAddress.validate()` checks basic syntax, not domain ownership or deliverability.

The safe defaults in this example are `enabled=false` and `sandbox=true`. In production, enabling external sending must be **explicit** and paired with real SMTP configuration, infrastructure permissions, deployment checks, and recipient controls. Do not set "allow real sending" as the default across all profiles.

Business code interacts only with the gateway:

~~~java
package example.integration.email;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderEmailService {
    private final GuardedMailGateway gateway;

    public OrderEmailService(GuardedMailGateway gateway) {
        this.gateway = gateway;
    }

    public void sendConfirmation(String recipient, String orderCode)
            throws MessagingException {
        MimeMessage message = gateway.newMessage();
        MimeMessageHelper helper =
            new MimeMessageHelper(message, false, "UTF-8");
        helper.setFrom("no-reply@example.test");
        helper.setTo(recipient);
        helper.setSubject("Order confirmation " + orderCode);
        helper.setText("Order " + orderCode + " has been recorded.", false);
        gateway.send(message);
    }
}
~~~

The `From` address is a sandbox fixture; real applications must load an approved sender address and verified sender identity per the mail provider. To guarantee **every** flow is protected, do not let other services inject `JavaMailSender` directly and bypass the gateway. Restricting SMTP access via network policies serves as an independent line of defense in case a code path accidentally bypasses the gateway.

### Cases Easily Overlooked

- **Bcc:** does not appear in standard visible email headers yet is still an SMTP envelope recipient; it must be checked before sending.
- **Reply-To:** not an immediate recipient of the outbound send, yet can expose a real address or direct user replies to the wrong place; use fixtures in tests and review separately.
- **Multiple recipients:** if a list contains both `tester@example.test` and `someone@real-domain.invalid`, the entire send must fail rather than partially sending and reporting success.
- **Templates:** addresses pulled from imported test/customer datasets may be real emails; sanitize or anonymize data before generating notifications.
- **Attachments:** invoices, CSVs, images, and reports can contain PII; messages captured in Mailpit also need access control, cleanup policies, and non-sensitive fixtures.
- **Other sending channels:** if the system also calls a third-party email API, the SMTP gateway does not cover that API; enforce equivalent guards at the corresponding integration boundary.

## 5. Inspecting Emails via the Mailpit UI and HTTP API

After the application sends an email to the SMTP sandbox:

1. Open `http://127.0.0.1:8025` and confirm the new message arrived.
2. Inspect **To/Cc/Bcc** from the SMTP/server perspective, plus From, Reply-To, Subject, and content type.
3. Check **plain text** and **HTML** if the message is multipart; verify Vietnamese Unicode and special characters.
4. Check links inside the email, template variables, attachments, filenames, MIME types, and sizes.
5. Clear/clean the captured inbox before each independent test case so you do not read stale messages from an earlier run.

Mailpit provides an HTTP API; for example, to list captured messages:

~~~bash
curl --fail --silent http://127.0.0.1:8025/api/v1/messages
~~~

In automated tests, query the API with a JSON parser and filter messages by `eventId`, test correlation ID, or a unique subject before asserting contents. Do not rely on "fetch the latest email" when multiple tests run concurrently, as tests can read each other's messages. When running in containers, the HTTP API URL must use the published or mapped host/port.

**Note:** the UI/API inspects emails after the SMTP capture server has received them; the UI cannot prove that emails would be delivered to Gmail/Outlook. Clean up messages before or after tests to keep tests isolated and avoid retaining sensitive test data longer than needed.

## 6. Unit Testing the Policy: Non-Sandbox Addresses Are Blocked

A minimal unit test must ensure rejection happens **before invoking the SMTP sender**. Example with JUnit 5 + Mockito:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;

class GuardedMailGatewayTest {

    @Test
    void rejectsExternalBccBeforeSending() throws Exception {
        JavaMailSender sender = mock(JavaMailSender.class);
        GuardedMailGateway gateway =
            new GuardedMailGateway(sender, true, true, "example.test");

        MimeMessage message =
            new MimeMessage(Session.getInstance(new Properties()));
        message.setRecipients(
            Message.RecipientType.TO, "tester@example.test");
        message.setRecipients(
            Message.RecipientType.BCC, "real-person@other.invalid");

        assertThrows(
            IllegalArgumentException.class,
            () -> gateway.send(message));
        verify(sender, never()).send(any(MimeMessage.class));
    }

    @Test
    void outboundIsDisabledByDefault() throws Exception {
        JavaMailSender sender = mock(JavaMailSender.class);
        GuardedMailGateway gateway =
            new GuardedMailGateway(sender, false, true, "example.test");
        MimeMessage message =
            new MimeMessage(Session.getInstance(new Properties()));
        message.setRecipients(
            Message.RecipientType.TO, "tester@example.test");

        assertThrows(
            IllegalStateException.class,
            () -> gateway.send(message));
        verify(sender, never()).send(any(MimeMessage.class));
    }
}
~~~

These two tests do not depend on Mailpit: they prove the guard blocks non-sandbox addresses and blocks sending when outbound is disabled. Add cases for invalid `To`, invalid `Cc`, empty recipients, mixed valid/invalid lists, uppercase domains, addresses with display names, and lookalike domains close to `example.test`.

This is unit-level policy testing. To prove a message **actually travels over SMTP**, write a separate integration test using Mailpit/GreenMail. Never replace those tests with mere verification that `send()` was called on a mock.

## 7. Integration Testing with a Real SMTP Server Inside the Sandbox

### 7.1. Scenario Using Mailpit in CI

An HTTP → email test can proceed as follows:

1. Start an isolated Mailpit instance with no relay configured, allowing the test app access only to the container's SMTP endpoint.
2. Start Spring Boot with the sandbox profile pointing `spring.mail.host/port` to Mailpit; set `app.email.enabled=true`, `sandbox=true`, domain `example.test`.
3. Send a request or trigger a message consumer with a fixture containing recipient `alice@example.test`.
4. Poll Mailpit's API for the matching message with a bounded timeout, avoiding fixed `Thread.sleep` synchronization.
5. Verify the expected content, subject, sender, recipients, HTML/text, MIME, and attachments; match the correlation ID or order code.
6. Repeat the same request/event and verify the deduplication policy: the application does not create a second business notification if the operation is idempotent.
7. Try a recipient outside the sandbox and confirm **no new message** arrives in Mailpit, while the application returns an error or records the blocked state as designed.

With Testcontainers, you can run Mailpit in a `GenericContainer`, retrieve the dynamic SMTP/API ports from the container, and inject them via `@DynamicPropertySource`. Never hardcode `127.0.0.1:1025` in tests if CI maps ports dynamically. Pin the image version in the pipeline and clear captured messages between tests to prevent cross-test interference.

### 7.2. GreenMail for In-JVM Integration Tests

GreenMail can run **in-process**, which is useful when you want each test class to manage its own server lifecycle, retrieve received messages, assert counts, and clean up afterward. High-level example:

~~~java
// Purposeful example: manage lifecycle in the test fixture.
GreenMail greenMail = new GreenMail(
    new ServerSetup(3025, "127.0.0.1", ServerSetup.PROTOCOL_SMTP));
greenMail.start();
try {
    // Configure the application's JavaMailSender:
    // host = 127.0.0.1; port = 3025; no real account.
    // Call the email service and assert:
    // greenMail.waitForIncomingEmail(...);
    // greenMail.getReceivedMessages();
} finally {
    greenMail.stop();
}
~~~

The classes shown are `com.icegreen.greenmail.util.GreenMail` and `ServerSetup`; test libraries and APIs must match the GreenMail version in use. A fixed port is only safe when you are certain no parallel test occupies the same port. In multi-worker CI environments, configure **free/dynamic ports** supported by your framework or give each test suite its own instance.

Mailpit shines when **QA needs a UI to inspect emails** and an API for black-box tests. GreenMail shines when you want **server control inside the test JVM** and varied SMTP/IMAP assertions. You can combine them: unit tests with Mockito, integration tests with GreenMail, and full-system smoke flows with Mailpit.

### 7.3. Integration Cases to Cover

| Test Group | Scenario | Expected Result |
|---|---|---|
| Happy path | Send notification email to `alice@example.test` | SMTP capture contains the exact email with expected subject/body |
| To/Cc/Bcc | Send to multiple test addresses | All recipients correct; Bcc delivered via envelope without leaking into headers |
| Block real people | Non-`example.test` address in To/Cc/Bcc | Gateway rejects before sending; inbox count unchanged |
| Sending disabled | `app.email.enabled=false` | No SMTP connection made and no message sent |
| HTML + text | Send multipart alternative | Both `text/plain` and `text/html` parts present with proper encoding |
| Unicode | Subject/body with Vietnamese accents | Decoded properly as UTF-8 with no garbled glyphs |
| Attachment | Send simulated PDF invoice | Verify filename, MIME type, and fixture content/size |
| SMTP unavailable | Stop Mailpit or use wrong port | Application reports controlled error with finite timeout; job eligible for retry |
| SMTP error response | Simulate 4xx/5xx where supported | Classify transient vs permanent error per policy; never mark sent |
| Duplicate event | Consumer receives same `eventId` again | Does not produce two business notifications per contract |
| Crash between send and status write | SMTP accepted but worker did not commit status | Retry may create duplicate email; track/reduce duplicates via business key |
| Test isolation | Run two tests concurrently/sequentially | No cross-test message reads or dirty shared inbox |

## 8. Avoiding Accidental Sends to Real Recipients: Defense in Depth

An application should never rely on a single `spring.profiles.active` flag or one `if` statement. Combine these barriers:

1. **Isolated SMTP endpoint:** local/CI always points to Mailpit/GreenMail, never using production provider hostnames or tokens.
2. **Email dispatch disabled by default:** enable only when both the SMTP target and protective mode are explicitly configured; do not start mail-sending workers in environments that do not send mail.
3. **Allowlist across all To/Cc/Bcc:** accept only test domains or approved test addresses; reject the entire send if any address falls outside the allowlist.
4. **Clean test data:** use `example.test` emails in fixtures; anonymize production-imported datasets and sensitive action URLs/tokens.
5. **Network restrictions:** block outbound SMTP/HTTP email provider traffic from test jobs via firewall/network policies, allowing only declared SMTP capture endpoints.
6. **Protect capture tools:** disable relays, restrict UI/API access, purge inboxes/attachments after tests, and store no secrets.
7. **Verify the negative path:** actively test a simulated real address `person@other.invalid` and verify zero requests reach real SMTP; run this test in the pipeline.

Do not **silently rewrite every recipient to a shared test mailbox** if the goal of testing is catching incorrect recipient mapping. You may offer a recipient-rewrite mode for QA, provided the original recipient is stored in protected metadata, the message is clearly marked as sandbox, and no real PII/addresses leak into headers or bodies. For automated tests, **rejecting non-allowlisted recipients** catches configuration mistakes much earlier.

### If the Application Has Multiple Sending Channels

An integration service might use:

- `JavaMailSender` over SMTP;
- an email provider REST API;
- a message broker forwarding events to another email worker;
- scheduled retries running email outbox records;
- event handlers fed by external systems.

In that case, enforce the guard at the **final send point** of every channel. Blocking only in a controller is insufficient if consumers or retry workers still receive send requests. With brokers, an event carrying a real recipient address in test data can be picked up by a production consumer if topics/clusters are misconfigured; isolate environments, topics, credentials, and access controls.

## 9. Managing Transactions, Retries, and Duplicate Emails

Email is a **side effect outside database transactions**. If a single request writes to PostgreSQL and sends over SMTP, those two operations do not share an ACID transaction:

~~~mermaid
sequenceDiagram
    participant A as HTTP / Worker
    participant D as PostgreSQL
    participant S as SMTP Sandbox
    A->>D: Save email status PENDING (COMMIT)
    A->>S: SMTP send
    S-->>A: Accepted
    Note over A,D: Worker may crash here
    A->>D: Save email status SENT (COMMIT)
~~~

If the worker dies **after SMTP accepts the message but before saving `SENT`**, a retry can send it again. SMTP has no shared transaction with PostgreSQL to roll back an already accepted email. Even if `@Transactional` wraps the Java method, rolling back the database cannot recall an email already handed over to SMTP.

To avoid losing emails, use an **email outbox**:

1. In the same DB transaction as the business write, insert an `email_outbox` row containing `notification_key`, template/version, reference data, and status `PENDING`.
2. Workers claim batches via locks/leases, compose the email, and invoke the gateway (pointing to the SMTP sandbox in tests).
3. Once SMTP confirms acceptance, record `SENT`; transient failures schedule retries with exponential backoff and a max-attempt limit.
4. Enforce a unique key per business intent (e.g., `orderId + notificationType + version`) to avoid creating two send requests for the same event on HTTP/Kafka retries.
5. Record `eventId`, `notificationKey`, `attempt`, SMTP outcome, and correlation ID for reconciliation.

**Important limitation:** unique keys and outboxes prevent duplicate **send commands created in the database**, but do not guarantee a single **SMTP delivery** if a worker crashes in the post-acceptance window. Some provider APIs support idempotency keys; with plain SMTP, accept the possibility of duplicate emails, keep message content tolerant of retries, and maintain reconciliation/alerting. A stable `Message-ID` can help diagnostics or system-specific handling, but does not guarantee deduplication across all mail servers.

In tests, simulating timeouts **after the server has received the email** is just as important as simulating connection failures before sending. If mocks always throw before `send`, tests will miss real-world duplicate-email scenarios during retries.

## 10. Testing SMTP Error Scenarios and System Observability

Mailpit focuses on capturing and inspecting messages. To accurately simulate SMTP 4xx/5xx errors, post-`DATA` timeouts, connection drops, or recipient rejections, you may need a **programmable SMTP stub/proxy** or a tool that configures fault responses. Do not assume Mailpit can simulate every SMTP failure without verifying your project's version/configuration.

Failure branches to distinguish:

- **Cannot connect to SMTP:** `connection refused`, DNS errors, timeouts; usually suitable for bounded retries.
- **Transient SMTP 4xx:** retry with backoff; avoid immediate high-volume retry bursts.
- **Permanent SMTP 5xx:** e.g., invalid recipient; usually stop unbounded retries and transition to an actionable state.
- **Accepted but client times out/disconnects:** outcome undetermined; retrying may produce duplicates.
- **Malformed email content:** template/MIME/encoding errors should be caught in tests before sending rather than retrying an invalid payload endlessly.

Track metrics and logs with minimal data:

| Signal | Purpose |
|---|---|
| `mail_send_attempts_total{outcome=...}` | Count successes, transient errors, permanent errors, and guard rejections |
| `mail_send_duration_seconds` | Detect slow SMTP or timeouts |
| `mail_outbox_pending`, `mail_outbox_oldest_age` | Detect backlogs and stuck notifications |
| `mail_retry_attempts` | Watch rising retries and avoid retry loops |
| `mail_recipient_rejected_total` | Alert on environment/domain misconfiguration |
| `notificationKey`, `eventId`, `traceId` | Correlate HTTP requests, DB rows, broker events, and emails |

Do not place user email addresses, access tokens, message bodies, SMTP passwords, or attachments into metric labels or logs. High-cardinality metric labels (such as per recipient or per eventId) also drive up cost and hinder monitoring.

To test an HTTP/DB/Kafka → email flow deterministically, define **what state counts as complete**: request created the outbox row, worker submitted to SMTP, or downstream received it? Each milestone can be asserted independently and has different latency characteristics.

## 11. Recommended CI Pipeline

An email-notification testing pipeline for an integration service can include:

1. Provision dedicated PostgreSQL/broker instances and Mailpit or GreenMail **for the test job**; block outbound SMTP/HTTP email provider traffic at the network level.
2. Start the application using the `example.test` domain fixture without providing production email secrets.
3. Run unit tests for templates, recipient guards, disabled mode, and error classification.
4. Run integration tests against fake SMTP, verifying content, headers, MIME, attachments, UTF-8, message count, and correlation keys.
5. Replay duplicate API/job/consumer inputs and simulate network faults; verify outbox/retry/duplicate behavior per contract.
6. Verify no email was sent to domains outside the allowlist; clean up captured inboxes, containers, and message data after tests.
7. Report failures by `notificationKey`, exception type, and processing step; never print credentials or personal data.

When running in parallel, spin up **one SMTP capture server per test worker** or enforce clean data partitioning; avoid sharing one inbox across concurrent pipelines and asserting "only one email on the whole server" while other tests are running.

## 12. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| “Using the test profile means real emails cannot be sent.” | Profiles can be overridden; you still need sandbox endpoints, allowlists, and egress blocking. |
| “Mocking `JavaMailSender` proves SMTP works.” | Mocks only verify method calls; integration tests need an SMTP capture server. |
| “The server accepted the mail, so the customer received it.” | SMTP acceptance and inbox delivery are two separate milestones. |
| “Validating the `To` field is enough.” | You must check `To`, `Cc`, `Bcc`, and all sending pathways. |
| “Mailpit is harmless storage.” | Captured emails and attachments can hold sensitive data; restrict access and purge them. |
| “Marking `SENT` after `send()` guarantees no duplicates.” | Crashes between send and commit can trigger retries and duplicates. |
| “Adding `@Transactional` makes SMTP roll back with the database.” | SMTP is external to database transactions. |
| “Staging can use production SMTP if we put `[TEST]` in the subject.” | Subjects do not stop delivery; separate accounts, endpoints, recipients, and infrastructure. |

## 13. Self-Check Questions

1. Why can a test mocking `JavaMailSender` still pass even when the application's SMTP configuration is completely broken?
2. How does `Bcc` differ from `To` and `Cc` from an SMTP delivery perspective, and why must the recipient guard inspect all three?
3. If CI accidentally points at production SMTP while `app.email.sandbox=true`, which protective layers still stop emails from reaching real people?
4. If a Kafka consumer receives the same `eventId` twice, how do you prevent inserting two email outbox rows?
5. If SMTP accepts an email but the worker dies before updating the status, what can a retry cause?
6. What should you assert on an HTML email containing an attachment and Vietnamese text?
7. Why can an SMTP capture server not confirm external inbox delivery or spam placement by default?

**Technical conclusion:** Testing email in Spring Boot Integration requires combining an **SMTP capture server** to verify actual submission paths, **recipient guards** and egress blocks to protect real recipients, plus tests covering content, failures, and retries at database/broker/SMTP boundaries. Mailpit/GreenMail verify messages without sending real emails; surviving crashes and redeliveries still requires an outbox, idempotency, and clear delivery states.

### References

- [Spring Boot — Sending Email](https://docs.spring.io/spring-boot/reference/io/email.html): `JavaMailSender` auto-configuration, `spring.mail.*`, and SMTP timeouts.
- [Spring Framework — Email Integration](https://docs.spring.io/spring-framework/reference/integration/email.html): `JavaMailSender`, `MimeMessageHelper`, and creating MIME emails.
- [Mailpit Documentation](https://mailpit.axllent.org/): SMTP capture, web UI, and API.
- [GreenMail](https://greenmail-mail-test.github.io/greenmail/): in-memory mail server for Java testing.
- [RFC 2606 — Reserved Top Level DNS Names](https://www.rfc-editor.org/rfc/rfc2606): reserved domain names for examples and testing.
