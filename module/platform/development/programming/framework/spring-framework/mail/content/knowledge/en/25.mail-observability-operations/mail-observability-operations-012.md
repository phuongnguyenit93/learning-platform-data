# Checking health indicators without accidentally sending real emails

In a **Spring Framework Mail** system, operators need to know whether the application can still reach the SMTP server. Spring Boot Actuator supports health indicators for many dependencies, including checking the mail server when compatible configuration is present. However, an automated health check can be invoked repeatedly by load balancers, Kubernetes, monitoring systems, or administrators.

If a health check is implemented by building a `MimeMessage` and calling `JavaMailSender.send(...)`, every probe can **send a real email**. Thinking it is merely a "test email," the system can inadvertently send thousands of messages per day, flood mailboxes, consume quota, trigger rate limits, damage sender reputation, or send data to unintended recipients.

**Core principle: health indicators inspect system state and must never automatically cause real email side effects.** For SMTP, distinguish checking configuration, checking connectivity/authentication, checking worker pipeline capability, and controlled end-to-end delivery tests. Each tier carries distinct costs, meanings, and implementations.

This lesson explains how to use `JavaMailSenderImpl.testConnection()` and Spring Boot Actuator safely, avoid calling `send` inside health endpoints, configure timeouts, separate liveness from readiness, test with mocks and test SMTP servers, and establish operational procedures so monitoring never becomes an accidental email blaster.

## 1. Why a health indicator can send unintended emails

Consider a custom health indicator:

```java
// DO NOT DO THIS: every health() call sends a real email.
@Component("unsafeMail")
public class UnsafeMailHealthIndicator implements HealthIndicator {

    private final JavaMailSender mailSender;

    public UnsafeMailHealthIndicator(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Override
    public Health health() {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setTo("operations@example.org");
        message.setSubject("Mail health check");
        message.setText("Checking email");

        mailSender.send(message);

        return Health.up().build();
    }
}
```

That logic looks like it verifies "can email be sent?" Yet every hit to `/actuator/health` or a health group containing it triggers an outbound send. Some systems probe very frequently, and multiple replicas probe in parallel.

Illustrative example:

```text
3 application replicas
    × 1 health probe every 10 seconds
    × 24 hours

= 25,920 health invocations/day
= up to 25,920 real emails/day if each probe calls send()
```

This number only illustrates the design impact; actual volume depends on the platform and queried endpoints. With multiple systems polling, volume can climb higher still.

The harm extends beyond cost:

- Receiving mailboxes get flooded with automated emails.
- Providers flag abnormal sending and apply throttling or suspension.
- Fake send events pollute metrics and dashboards.
- Health-check emails mix with business traffic, muddying audits.
- Endpoint probing can leak internal recipients or configuration details.
- During an SMTP outage, health probes retry endlessly instead of aiding recovery.
- If emails include environment info, data leakage risk rises.

**Never call `JavaMailSender.send(...)` as a periodic check inside a health endpoint.**

## 2. Distinguish four testing tiers

Not every "is mail healthy" check needs to send an email. Pick the lightest tier sufficient for the operational decision.

| Tier | What it verifies | Sends real email? | Proves Inbox delivery? |
|---|---|---|---|
| **Configuration check** | Host, port, secret references, timeouts, and policy settings are valid | No | No |
| **Connectivity/authentication check** | Whether the app can connect or authenticate to the SMTP server | No | No |
| **Pipeline health check** | Workers, queues, outbox, backlog, and processing are active | Not needed | No |
| **Controlled end-to-end synthetic test** | Real submission followed by observing mailbox/events in a controlled setup | Yes, only on schedule/approval | Confirms only within test evidence and scope |

Standard health endpoints should focus on configuration, connectivity, and pipeline state. End-to-end synthetic testing is a **separate testing workflow** with bounded recipients, quotas, and cadence—not something run every time Kubernetes polls a pod.

### Successful connection does not equal delivery

Even when the SMTP server accepts the connection, authentication succeeds, and `testConnection()` returns normally, it **does not prove**:

- The user and `From` address have rights to send every email type.
- The recipient exists or is permitted to receive mail.
- A message clears size or content limits.
- The destination server accepted the email.
- The email reaches the Inbox rather than spam/quarantine.
- The recipient read the email.

A health indicator accurately serves as a **dependency signal**, not a delivery guarantee.

## 3. How Spring Boot's MailHealthIndicator works in principle

With compatible Spring Boot Actuator configuration, the mail health contributor can invoke `JavaMailSenderImpl.testConnection()` to evaluate SMTP reachability.

`JavaMailSenderImpl.testConnection()` opens a transport connection to the mail server per Jakarta Mail configuration, potentially performing authentication, and closes the connection. It **does not build an email to send**, executes no MIME body submission to recipients, and needs no recipient address.

Expected flow:

```text
GET /actuator/health
        |
        v
Mail health indicator
        |
        v
JavaMailSenderImpl.testConnection()
        |
        +-- TCP connect
        +-- SMTP greeting / protocol negotiation
        +-- STARTTLS or implicit TLS per configuration
        +-- AUTH if configured
        +-- Close transport
        |
        v
UP or DOWN
```

Absent steps:

```text
MAIL FROM
RCPT TO
DATA
Message body
Actual email delivery
```

In practice, exact protocol steps depend on the transport and SMTP server. The decisive point is that `testConnection()` tests connecting and disconnects, **never calling `send(...)` to submit a message**.

### Conditions for the auto-configured indicator

Depending on the Spring Boot version and auto-configuration, the mail health contributor registers when a compatible mail sender bean exists and mail health is enabled. If the application defines a custom sender implementing only the `JavaMailSender` interface, or disables the contributor, the mail indicator may not appear automatically.

Therefore, inspect the live endpoint and your project version's configuration. **Never assume adding `spring-boot-starter-mail` guarantees the mail indicator is active.**

### Distinguishing APIs

| API | Meaning |
|---|---|
| `JavaMailSender.send(...)` | Submits an actual email via transport; can generate outbound mail. |
| `JavaMailSenderImpl.testConnection()` | Tests connection/auth to the SMTP server; sends no message. |
| `MimeMessageHelper` | Builds MIME content; not a health check by itself. |
| `HealthIndicator.health()` | Returns health state at check time. |
| `/actuator/health` | Endpoint aggregating configured indicators. |

A health indicator using `testConnection()` needs no recipient. If health code has to construct a `MimeMessage` and call `setTo(...)` just to run, redesign it immediately.

## 4. Configuring Spring Boot for SMTP connections with timeouts

Example when the mail provider uses STARTTLS on port 587:

```yaml
spring:
  mail:
    host: smtp.example.org
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "mail.smtp.auth": true
      "mail.smtp.starttls.enable": true
      "mail.smtp.starttls.required": true
      "mail.smtp.connectiontimeout": 3000
      "mail.smtp.timeout": 3000
      "mail.smtp.writetimeout": 3000

management:
  health:
    mail:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
```

Timeout values are in milliseconds and illustrative only. Tune them to your network path, provider, and health-check budget.

Key properties:

| Property | Role |
|---|---|
| `spring.mail.host` | SMTP endpoint the app connects to. |
| `spring.mail.port` | Submission port matching the provider. |
| `spring.mail.username/password` | Credentials from managed secret storage. |
| `mail.smtp.auth` | Enables authentication when required by the provider. |
| `mail.smtp.starttls.enable` | Enables STARTTLS upgrade. |
| `mail.smtp.starttls.required` | Refuses to continue insecurely if STARTTLS is required. |
| `mail.smtp.connectiontimeout` | TCP connection setup timeout. |
| `mail.smtp.timeout` | Socket read timeout. |
| `mail.smtp.writetimeout` | Socket write timeout. |
| `management.health.mail.enabled` | Toggles auto-configured mail health contributor when eligible. |

**Never place real passwords in documentation, repositories, or logs.** Use a secret manager, environment variables, or your platform's secret injection.

### When the provider uses implicit TLS

For endpoints requiring TLS immediately on connect:

```yaml
spring:
  mail:
    host: smtp.example.org
    port: 465
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      "mail.smtp.auth": true
      "mail.smtp.ssl.enable": true
      "mail.smtp.connectiontimeout": 3000
      "mail.smtp.timeout": 3000
      "mail.smtp.writetimeout": 3000
```

Ports 587/465 are common conventions, not rigid rules for every provider. Check official documentation rather than guessing ports when an indicator reports `DOWN`.

## 5. Calling testConnection() directly when connectivity needs verification

In plain Spring Framework, or when controlling exact check timing, call `JavaMailSenderImpl.testConnection()`:

```java
import jakarta.mail.MessagingException;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class SmtpConnectivityProbe {

    private final JavaMailSenderImpl mailSender;

    public SmtpConnectivityProbe(
            JavaMailSenderImpl mailSender
    ) {
        this.mailSender = mailSender;
    }

    public void verifyConnectivity()
            throws MessagingException {
        mailSender.testConnection();
    }
}
```

This method passes neither recipient nor message, so it cannot send real email content. Still, it **opens a network connection and may execute AUTH**. Operational impacts to weigh:

- The SMTP provider may log a login event.
- Each check can occupy a connection slot.
- Bad credentials trigger repeated AUTH failures.
- Providers may enforce rate limits, security alerts, or account lockouts.
- Slow DNS/TLS/SMTP slows down health endpoint responses too.

Thus "sends no real email" **does not mean "zero cost."** Control probe frequency and timeouts carefully.

## 6. Writing a safe custom HealthIndicator when custom behavior is needed

If custom behavior is required, build an indicator calling `testConnection()`, never `send(...)`.

Example:

```java
import jakarta.mail.MessagingException;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.stereotype.Component;

@Component("smtpConnectivity")
public class SmtpConnectivityHealthIndicator
        implements HealthIndicator {

    private final JavaMailSenderImpl mailSender;

    public SmtpConnectivityHealthIndicator(
            JavaMailSenderImpl mailSender
    ) {
        this.mailSender = mailSender;
    }

    @Override
    public Health health() {
        try {
            mailSender.testConnection();

            return Health.up()
                    .withDetail("check", "smtp-connect-only")
                    .build();
        } catch (MessagingException exception) {
            return Health.down()
                    .withDetail(
                            "errorType",
                            exception.getClass().getSimpleName()
                    )
                    .build();
        }
    }
}
```

This class only calls `testConnection()`. If TCP, TLS, or AUTH fails, it returns `DOWN`. It contains no recipient addresses and sends no MIME messages.

**Important caveats:**

- The bean injects `JavaMailSenderImpl`, not the `JavaMailSender` interface; this only works when your setup provides that concrete bean.
- If Spring Boot already auto-registers the built-in mail indicator, adding a custom one runs **two identical checks**, doubling connections. Consider disabling the default when replacing it.
- Returning raw exception messages or stack traces in health details can leak hostnames, accounts, policies, or settings. Even returning `errorType` should be access-controlled.
- `Health.down()` here means **the connectivity probe failed right now**, not that all business emails failed to send.
- Every `health()` call can open an SMTP connection; to limit frequency, add caching or a coordinated background probe.

### Keep only one mail health source

If choosing a custom indicator, disable the auto-configured mail contributor:

```yaml
management:
  health:
    mail:
      enabled: false
```

Give the custom indicator its own name such as `smtpConnectivity`. When no custom behavior is needed, prefer the built-in mail indicator to reduce code and avoid extra failure modes.

Never run both built-in and custom indicators simultaneously without clear reason, since every health poll opens two separate connections.

## 7. Never use send() as a periodic health check

Dangerous anti-patterns:

```java
// DO NOT do this in a HealthIndicator:
mailSender.send(new SimpleMailMessage());
```

```java
// DO NOT do this: "emailing yourself" is still a real email.
SimpleMailMessage testMail = new SimpleMailMessage();
testMail.setTo("admin@example.org");
testMail.setSubject("Periodic health check");
testMail.setText("Ping");
mailSender.send(testMail);
```

```java
// DO NOT do this: building and sending a MimeMessage on every readiness probe.
MimeMessage mime = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(mime, false, "UTF-8");
helper.setTo("monitoring@example.org");
helper.setSubject("Health");
helper.setText("Healthy");
mailSender.send(mime);
```

There is no reason to put `To`, `Cc`, or `Bcc` inside a health indicator meant solely to verify SMTP connectivity.

### Why emailing even a test mailbox inside a health endpoint is dangerous

Even an organization-owned test address suffers from:

- Excessive email volume from nonstop polling.
- Provider spam/abuse alerts or quota exhaustion.
- Per-message billing charges.
- Polluted delivery/bounce metrics.
- Unbounded mailbox storage growth.
- Risk of an operator accidentally editing the configured recipient.

When live sending tests are genuinely required, build **deliberate synthetic monitoring** with controlled cadence, recipients, and permissions—never inside a health endpoint anyone or anything can hit at will.

## 8. Preventing accidental sends in architecture

Relying solely on code reviews saying "don't call send in health" breaks down in large codebases with many contributors.

Enforce structural rules:

1. `HealthIndicator` depends only on a narrow `MailConnectivityProbe` interface, never `JavaMailSender` directly.
2. `MailConnectivityProbe` exposes only `check()`/`checkConnectivity()` and no send APIs.
3. Business mail senders reside in a separate layer never injected into the health module.
4. Unit tests mock the sender and verify `send(...)` is never invoked.
5. In deployment, route health checks through controlled endpoints/health groups.
6. If synthetic sending is needed, run it in a workflow completely separate from health probes.

A minimal interface:

```java
public interface MailConnectivityProbe {
    void check() throws Exception;
}
```

Implementation:

```java
import jakarta.mail.MessagingException;
import org.springframework.mail.javamail.JavaMailSenderImpl;

public final class JavaMailConnectivityProbe
        implements MailConnectivityProbe {

    private final JavaMailSenderImpl mailSender;

    public JavaMailConnectivityProbe(JavaMailSenderImpl mailSender) {
        this.mailSender = mailSender;
    }

    @Override
    public void check() throws MessagingException {
        mailSender.testConnection();
    }
}
```

Health layer:

```java
public final class MailConnectionHealthIndicator
        implements HealthIndicator {

    private final MailConnectivityProbe probe;

    public MailConnectionHealthIndicator(
            MailConnectivityProbe probe
    ) {
        this.probe = probe;
    }

    @Override
    public Health health() {
        try {
            probe.check();
            return Health.up().build();
        } catch (Exception exception) {
            return Health.down().build();
        }
    }
}
```

This design restricts health checks to "probe" access only; if anyone tries to send real email, they cannot call `send` through `MailConnectivityProbe` without intentionally changing dependencies.

## 9. Liveness and readiness are not the same

In container environments, two distinct operational questions apply:

- **Liveness:** is the application process alive and capable of making progress?
- **Readiness:** should this instance receive new traffic/work?

SMTP is an **external service**. If SMTP temporarily drops while the application remains healthy, repeatedly restarting pods usually cannot fix SMTP.

### Why not put SMTP into liveness?

Suppose the SMTP provider has a 10-minute outage:

```text
SMTP outage
    |
    v
Mail health DOWN
    |
    v
Liveness DOWN (if wrongly included)
    |
    v
Kubernetes restarts application
    |
    v
SMTP still DOWN
    |
    v
Repeat restart loop
```

Restarting drops in-memory `@Async` tasks, disrupts HTTP requests, and spikes database load—without fixing the external SMTP outage.

**Never include a non-mandatory SMTP dependency in liveness probes.** Liveness should reflect internal process progress.

### When should SMTP affect readiness?

This depends on architecture:

| Architecture | Should SMTP DOWN fail readiness? | Why |
|---|---|---|
| Synchronous mail-submission API unable to serve when SMTP is down | Possibly, per SLO and failover policy | Should not accept traffic if every request is guaranteed to fail. |
| Order API that writes a mail outbox and sends in the background | Usually not | Order creation can still work; the outbox buffers intents for retry. |
| Dedicated mail worker backed by a durable queue | Can expose its own health | Decide whether to pause claiming jobs while the provider fails. |
| App where email is an auxiliary feature | Usually not | Avoid taking the whole product out of traffic over email failures. |

There is no one-size-fits-all answer. The crucial rule is **never let an optional dependency fail overall readiness automatically** without evaluating architecture.

## 10. Organizing health groups for Kubernetes

Spring Boot Actuator can expose dedicated liveness/readiness health probes when configured appropriately.

A basic configuration:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
  endpoints:
    web:
      exposure:
        include: health
```

Common endpoints under Actuator health groups:

```text
/actuator/health/liveness
/actuator/health/readiness
/actuator/health
```

To decouple readiness from SMTP, keep only the application's own readiness indicator and truly mandatory dependencies. Illustrative configuration:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState
```

When adding components like databases or brokers, include them in readiness based on real traffic-serving needs and registered indicator names. Never assume every indicator sits in liveness/readiness automatically; inspect the configuration and live endpoint behavior for your Spring Boot version.

### A dedicated group for SMTP

If an endpoint is needed for manual mail checks, configure a separate health group:

```yaml
management:
  endpoint:
    health:
      group:
        smtp:
          include: smtpConnectivity
```

This assumes a custom indicator with ID `smtpConnectivity`. The SMTP group can then be queried independently without coupling liveness or readiness to SMTP.

Verify your Spring Boot version, contributor names, and group access controls. Protect health groups from public queries that could trigger excessive SMTP logins.

## 11. Startup test-connection differs from periodic health probes

Spring Boot provides an option to test mail connectivity at startup:

```yaml
spring:
  mail:
    test-connection: true
```

Depending on version and auto-configuration, this checks connectivity during startup and can abort startup if SMTP is unreachable.

**This does not send a real email**, yet it can prevent the application from booting during a temporary provider outage.

| Mechanism | Timing | Sends real mail? | Impact if SMTP is DOWN |
|---|---|---|---|
| `spring.mail.test-connection` | At startup per config | No | Can fail application startup. |
| Mail `HealthIndicator` | When endpoint/group is queried | No, with connectivity-only probe | Can return `DOWN`. |
| Custom send test using `JavaMailSender.send` | Whenever code runs | Yes | Sends real email or throws error. |
| Scheduled synthetic E2E | On controlled schedule | Yes | Records separate test outcome; need not fail readiness. |

When email is secondary and backed by a durable outbox, consider **not failing startup** merely because SMTP is down. Workers can wait for recovery as long as send intents stay durable.

When an application exists solely for synchronous SMTP submission with no degraded mode, failing fast may be desirable. That is an SLO choice, not a universal default.

## 12. Health checks need timeouts and time budgets

A health endpoint can stall on slow DNS, TCP, TLS, AUTH, or provider responses. Without timeouts, each probe ties up a web thread for a long time.

Configure explicit timeouts:

```yaml
spring:
  mail:
    properties:
      "mail.smtp.connectiontimeout": 3000
      "mail.smtp.timeout": 3000
      "mail.smtp.writetimeout": 3000
```

Do not assume those three `3000 ms` values enforce a single `3-second` total deadline across all scenarios. One connection performs multiple I/O operations, so total elapsed time can exceed any single timeout.

Budget carefully across:

```text
Probe interval
Probe timeout
Mail connect/auth timeout
Health cache TTL
Failure threshold
Kubernetes liveness/readiness threshold
```

For example, if kubelet expects a reply in 1 second while SMTP handshakes normally take 3 seconds, wiring a direct SMTP probe into readiness causes false failures even when the provider meets mail SLAs.

### Do not let health checks add load during an incident

When SMTP slows down, concurrent health requests can pile up sockets. Any network-backed health indicator needs safeguards:

- Clear timeouts.
- Bounded polling frequency.
- Short status caching when appropriate.
- Concurrency caps for custom probes.
- No tight retry loops inside a single health call.
- No unbounded repetitive stack-trace logging.

## 13. Reducing probe frequency with caching or background probes

`testConnection()` sends no email, yet each invocation may still run AUTH. Across many replicas and monitoring clients, that cost adds up.

Two approaches:

### 13.1. Time-bounded health response caching

Spring Boot Actuator supports caching on health endpoints; for example:

```yaml
management:
  endpoint:
    health:
      cache:
        time-to-live: 20s
```

`20s` is illustrative. Confirm exact caching properties and behavior against your Spring Boot version and health groups.

**Tradeoff:** caching cuts SMTP connection counts, though health responses reflect a result from seconds earlier. Pick a TTL matching observability goals.

### 13.2. Background probe returning last-known status

A scheduled worker can run `testConnection()` at a controlled cadence and store:

```text
lastProbeTime
lastProbeStatus
lastProbeDuration
lastErrorCategory
```

The health endpoint simply reads that snapshot without opening a socket on every HTTP request.

If using this approach, track **result freshness**. An `UP` result from 2 hours ago is not equivalent to an `UP` result from 20 seconds ago.

Example states:

```text
lastProbeStatus = UP
lastProbeAgeSeconds = 18
status = UP

lastProbeStatus = UP
lastProbeAgeSeconds = 7200
status = UNKNOWN or DOWN by explicit policy
```

Never leave an old result stuck at `UP` if the scheduler died. Likewise, never let the background scheduler send real emails: background probes must only connect/authenticate without submitting messages.

## 14. Custom snapshot HealthIndicator without connecting per request

Design can cleanly separate active probing from status reporting.

Example snapshot model:

```java
import java.time.Instant;

public record SmtpHealthSnapshot(
        boolean reachable,
        Instant checkedAt,
        String errorCategory
) {
}
```

The probe scheduler updates the snapshot after each `testConnection()`; Actuator health merely reads it.

Concept:

```java
public Health health() {
    SmtpHealthSnapshot snapshot = probeState.current();

    if (snapshot == null) {
        return Health.unknown()
                .withDetail("reason", "not_checked_yet")
                .build();
    }

    if (snapshot.checkedAt().isBefore(
            clock.instant().minus(maxSnapshotAge))) {
        return Health.unknown()
                .withDetail("reason", "probe_stale")
                .build();
    }

    return snapshot.reachable()
            ? Health.up().build()
            : Health.down()
                    .withDetail(
                            "errorCategory",
                            snapshot.errorCategory()
                    )
                    .build();
}
```

`probeState`, `clock`, and `maxSnapshotAge` are application dependencies, not built-in globals. This illustrates the key benefit of snapshots: **zero `send` calls and zero SMTP connections inside `health()`**.

When returning `UNKNOWN`, the aggregate response and HTTP status code depend on health status mappings; test them so readiness policies behave as intended.

## 15. Classifying health failures: connectivity, TLS, AUTH, and provider outages

When `testConnection()` fails, root causes vary widely.

| Error or symptom | Suspect domain | Action needed |
|---|---|---|
| DNS lookup failure | DNS/network | Check resolvers, hostname, and pod networking. |
| TCP connection refused | Endpoint/port/firewall | Verify provider host/port and egress rules. |
| Connection/read timeout | Slow network/provider | Check timeouts, saturation, and outages. |
| TLS handshake failure | TLS mode/certificates | Check STARTTLS vs implicit TLS, trust, and protocols. |
| Authentication failed/535 | Credentials/AUTH policy | Check secrets, app passwords, OAuth2, and account status. |
| Rate limited by frequent AUTH | Excessive probing/provider policy | Lower probe rate, cache results, check config. |
| Connects cleanly yet business sends fail | Outside connectivity probe scope | Check `From`, recipients, message size, and send policies. |

Health indicators typically emit `UP`/`DOWN` or `UNKNOWN`. Detailed failure categories belong in internal logs and bounded metrics—never expose raw SMTP exceptions on public endpoints.

### An SMTP error is not always MailAuthenticationException

`testConnection()` can throw `MessagingException` with varied underlying causes. Never assume every health failure means a bad password. Check the cause chain, failure stage, transport mode, and provider policies.

Conversely, successful login does not prove an account can send with any arbitrary `From` address, because sender authorization may be enforced at `MAIL FROM` or submission time.

## 16. Securing health endpoints

Actuator endpoints serve operations and should never leak infrastructure details accidentally.

Example configuration exposing only basic status:

```yaml
management:
  endpoint:
    health:
      show-details: never
  endpoints:
    web:
      exposure:
        include: health,info
```

Where detail visibility is needed, restrict it to authenticated operators via Spring Security. Never put usernames/passwords, access tokens, sensitive internal hostnames, or raw exception messages into `Health.withDetail(...)`.

### Never let clients supply recipients or SMTP hosts to "test"

An endpoint shaped like:

```text
GET /actuator/health/mail?recipient=...
GET /actuator/health/mail?host=...
```

is dangerous if the handler actually uses query parameters to send mail or connect to arbitrary hosts. It enables unintended emailing and SSRF/infrastructure scanning.

Health endpoints must check **deployed, approved configuration**, never acting as an open mail relay or network scanner for untrusted callers.

If admins truly need a "send test email" tool, put it on a separate endpoint with authentication, authorization, rate limits, and auditing—never inside Actuator health.

## 17. Designing safe synthetic end-to-end tests when genuinely needed

Sometimes you must verify **actual sending and receiving**, such as validating a new route pre-launch or running controlled periodic deliverability checks. That calls for a dedicated synthetic monitoring pipeline.

```text
Authorized scheduled job
         |
         v
Select approved test mailbox
         |
         v
Create synthetic notification
         |
         v
Submit via production mail route
         |
         v
Record provider/message ID
         |
         v
Observe controlled test mailbox or provider event
         |
         v
Report synthetic outcome
```

Mandatory safeguards:

1. **Send only to an allowlisted test mailbox** owned by the organization.
2. Enforce **fixed cadence and quota**, independent of health endpoint hits.
3. Mark subject/body unmistakably as synthetic, with zero PII or production data.
4. Tag with a distinct synthetic category so marketing/transactional KPIs stay clean.
5. Enforce timeouts, bounded retries, and duplicate prevention.
6. Audit the triggering principal/process.
7. Never accept arbitrary user-supplied recipients or URLs.
8. Halt synthetic runs automatically when the provider degrades or quota runs low.
9. When checking real Inbox arrival, monitor dedicated test mailboxes against clear criteria.
10. Never wire synthetic test latency directly into liveness probes.

A synthetic check verifies one concrete path; it still cannot guarantee every business email reaches every external recipient's Inbox.

### Separate synthetic metrics from business mail

When running real synthetic sends:

```text
mail.synthetic.attempt
mail.synthetic.smtp.accepted
mail.synthetic.delivery.confirmed
mail.synthetic.failure
```

or tag with `type=synthetic` from a bounded vocabulary. Never mix synthetic mail into "transactional emails delivered" KPIs when accuracy matters.

## 18. Testing with Mockito: health() must never call send()

Unit tests provide a vital guardrail whenever a health indicator is modified.

Example using Mockito, JUnit 5, and AssertJ on the custom indicator above:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.Status;
import org.springframework.mail.javamail.JavaMailSenderImpl;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

class SmtpConnectivityHealthIndicatorTest {

    @Test
    void healthyProbeOnlyCallsTestConnection()
            throws Exception {

        JavaMailSenderImpl sender =
                mock(JavaMailSenderImpl.class);

        SmtpConnectivityHealthIndicator indicator =
                new SmtpConnectivityHealthIndicator(sender);

        Health health = indicator.health();

        assertThat(health.getStatus())
                .isEqualTo(Status.UP);

        verify(sender).testConnection();

        // No other interactions, including any send() overload.
        verifyNoMoreInteractions(sender);
    }
}
```

This test verifies that the indicator interacts only with `testConnection()` and never touches `JavaMailSender.send(...)`.

### Test that AUTH failures also send nothing

```java
import jakarta.mail.AuthenticationFailedException;

@Test
void authenticationFailureReturnsDownWithoutSending()
        throws Exception {

    JavaMailSenderImpl sender =
            mock(JavaMailSenderImpl.class);

    doThrow(new AuthenticationFailedException(
            "Synthetic authentication failure"
    )).when(sender).testConnection();

    SmtpConnectivityHealthIndicator indicator =
            new SmtpConnectivityHealthIndicator(sender);

    Health health = indicator.health();

    assertThat(health.getStatus())
            .isEqualTo(Status.DOWN);

    verify(sender).testConnection();
    verifyNoMoreInteractions(sender);
}
```

This test enforces another key point: health checks must **return `DOWN` semantically** when connectivity fails, rather than sending another email as a "retry."

### With a custom probe interface

When using `MailConnectivityProbe`, fake its implementation to test:

- Success → `UP`.
- Failure → `DOWN`.
- Timeout/stale snapshot → `UNKNOWN` or `DOWN` per contract.
- Zero dependencies on a real email-sending sender across all branches.

This catches accidental regressions before deployment.

## 19. Integration testing against an SMTP test server without sending mail

A test SMTP server like GreenMail validates connectivity and authentication without touching production providers.

Scenario:

1. Start a test SMTP server on a random/test-managed port.
2. Point `JavaMailSenderImpl` at the test server.
3. Invoke `testConnection()` or the health endpoint hosting the indicator.
4. Assert health is `UP`.
5. Assert **the message count received by the test server is 0**.
6. Stop the server or supply invalid test credentials.
7. Invoke health again and assert `DOWN`.
8. Assert zero emails were created or sent.

Test idea:

```java
@Test
void connectivityCheckDoesNotSubmitMail()
        throws Exception {

    // Test SMTP server initialized and started in fixture.
    JavaMailSenderImpl sender = testMailSender();

    sender.testConnection();

    assertThat(
            testSmtpServer.receivedMessageCount()
    ).isZero();
}
```

`testMailSender()` and `testSmtpServer` are illustrative fixtures/helpers; counting APIs depend on the chosen test server.

### Also verify connection count under load requirements

A test server can record session counts. Across repeated health checks, verify:

- Zero messages received.
- Connect/AUTH counts match your caching/interval design.
- Connections are closed cleanly.
- Slow servers do not pin health threads indefinitely.

That tests probe overhead, **distinct from** proving zero real emails are sent.

## 20. Testing Actuator endpoints

In Spring Boot applications, component/integration tests can invoke endpoints via `MockMvc` or a test client to verify health responses.

Example idea:

```java
mockMvc.perform(get("/actuator/health"))
        .andExpect(status().isOk());
```

Key considerations:

- Endpoints may return HTTP 503 when overall health is `DOWN`.
- If security is enabled, test authorization rules too.
- Health groups may exclude the mail indicator depending on configuration.
- If health is cached, a single call may not trigger a fresh probe.
- `MockMvc` alone does not prove zero SMTP sends occurred; pair it with a mock/spy sender or a test SMTP server confirming 0 received messages.

Thus a strong test suite pairs **endpoint response assertions** with **zero-send assertions**.

### When all real sending must be blocked in tests

If the test context contains other schedulers or event listeners that might invoke `JavaMailSender.send`, replace the sender with a mock/fake or route all settings to a test SMTP server. Never let unit/integration health tests accidentally use production credentials and SMTP hosts.

## 21. Checking health across multiple SMTP routes

A system may run:

- Primary and backup SMTP relays.
- Transactional and marketing providers.
- Per-tenant or per-region SMTP accounts.
- Email provider APIs alongside SMTP relays.

A single indicator bound to the default sender bean may **not represent** all outbound routes.

Example:

```text
MailService
    |
    +-- transactional-primary -> SMTP A
    |
    +-- transactional-backup  -> SMTP B
    |
    +-- marketing-route       -> Provider C
```

If SMTP A's health goes `DOWN` while B remains healthy, failover policies can keep sending. Conversely, A passing does not prove B and C are ready.

Options:

1. Dedicated health checks per bounded route.
2. Aggregate health stating "at least one eligible route exists for this mail class."
3. Per-route dashboards/metrics while keeping health endpoints simple.
4. Never probe thousands of per-tenant routes or credentials on every health HTTP request.

**Never inject unbounded tenant IDs into health contributor names or metric tags**, which explodes load and cardinality. For large route fleets, use bounded scheduled probes or targeted sampling alongside worker and provider telemetry.

## 22. Mail pipeline health differs from SMTP health

An SMTP connectivity check can return `UP` while zero emails go out because:

- Workers are stopped.
- The outbox queue is backed up.
- Leases are stuck.
- Task executors are saturated.
- Template renderers are failing.
- Notifications are blocked by policy.
- Rate limits caused workers to pause intentionally.

Therefore pair **connectivity health** with **pipeline metrics**:

| Signal | Question |
|---|---|
| `mail.smtp.connectivity` | Can we connect/authenticate on this mail route? |
| `mail.outbox.pending` | How many notifications are currently waiting? |
| `mail.outbox.oldest.age` | How long has the oldest job waited? |
| `mail.send.attempt` | Are workers actually attempting sends? |
| `mail.send.failure` | Are SMTP failures climbing? |
| `mail.send.unknown` | Are many attempts hitting unknown outcomes? |
| `mail.worker.inflight` | How many jobs are actively processing? |
| `mail.provider.bounced` | Is the provider reporting elevated bounces? |

Names in this table are illustrative metric names, not meters exported automatically by Spring Mail.

**`Health UP` does not mean the mail pipeline is meeting SLAs.** Supplement health checks with metrics and alerts to catch stalled queues, bulk failures, and slow deliveries.

## 23. Prevent health indicators from mutating business state

Besides sending no mail, health indicators must avoid unnecessary side effects:

- Never insert outbox rows.
- Never increment business job retry counts.
- Never mark a notification as sent.
- Never dequeue or ACK broker messages.
- Never render templates using real production data.
- Never modify permissions or rotate secrets.
- Never generate attachments or read sensitive files.
- Never switch default mail routes to "self-heal."
- Never call provider webhook handlers to fake delivered states.

A health indicator may **record technical probe metrics** and sanitized status logs; that differs completely from mutating business data.

If checking database/outbox state, run bounded read queries or inspect a worker-maintained snapshot. Never let a health endpoint reprocess failed jobs automatically.

## 24. Protecting against incidents caused by overly aggressive probing

Even when `testConnection()` sends no real mail, poorly configured probes can still cause outages.

### Scenario: wrong SMTP password

If every instance runs `AUTH` with a bad password repeatedly:

1. The provider logs repeated login failures.
2. Security heuristics flag brute-force attempts or lock the account.
3. Real email workers also lose authentication.
4. Health probes keep making the problem worse.

Mitigation:

- Enforce reasonable intervals/caching.
- Never retry tightly inside one health call.
- On sustained AUTH failures, alert and back off probe frequency per policy.
- Fix the secret or auth mechanism before resuming normal checks.
- Distinguish permanent config errors from transient timeouts.

### Scenario: slow SMTP server

Concurrent health requests waiting on SMTP exhaust web threads, making the whole app unresponsive to other traffic.

Mitigation:

- Timeouts.
- Caching or background probes.
- Concurrency caps.
- Keep external SMTP dependencies out of liveness.
- Alert on telemetry instead of hammering connections nonstop.

### Scenario: publicly exposed endpoint

An attacker flooding a public health endpoint forces thousands of outbound SMTP connections even with zero emails sent. Protect health endpoints with network/security policies rather than assuming "there's no sensitive output."

## 25. Runbook when health reports DOWN

### Step 1 — Confirm which indicator is DOWN

Check overall status and health groups per authorized access. Verify whether the failure is mail connectivity, database, queue, or liveness state.

Missing `mail` in the response does not mean SMTP is healthy; the contributor may be disabled or unconfigured.

### Step 2 — Confirm no real test emails are being generated

Verify the health implementation uses `testConnection()` or a zero-send probe. If `send(...)` is found in health code, stop repeated polling immediately and switch to a zero-send design.

### Step 3 — Verify host, port, and TLS mode

Cross-check official provider settings. Verify DNS, network egress, firewalls, certificates, and STARTTLS vs implicit TLS.

### Step 4 — Verify authentication safely

Confirm secrets injected properly at runtime, username format is right, and the account is neither locked nor disabled for SMTP AUTH. Never print passwords/tokens in logs or run tight manual credential guesses.

### Step 5 — Check timeouts and probe cadence

Review probe intervals, cache TTLs, SMTP timeouts, and replica counts. During a provider outage, cut unnecessary probe connection load.

### Step 6 — Check whether business operations can continue

With a durable outbox, the app can keep recording email intents while SMTP is down. Monitor backlog, worker state, and SLAs—do not restart all pods solely because mail health is `DOWN`.

### Step 7 — Controlled recovery

After fixing SMTP, run one safe connectivity check. Then watch workers drain the retry backlog within rate limits. Never fire a flood of synthetic emails to confirm health.

## 26. Common errors and fixes

| Symptom | Possible cause | Fix |
|---|---|---|
| Ops inbox flooded with "Health check" emails | Indicator calls `JavaMailSender.send` | Switch to `testConnection()`; isolate synthetic tests. |
| Health `DOWN` yet mail still delivers via backup | Indicator checks only primary | Define health per route/failover policy. |
| Health `UP` yet users receive no email | Probe checks connect/auth only | Monitor submissions, provider events, spam/bounces. |
| Health endpoint responds very slowly | Slow SMTP handshake/TLS/AUTH | Add timeouts, caching, background probing. |
| SMTP account locked post-deploy | Health probes hammered bad credentials | Reduce cadence, fix secret, classify auth errors. |
| Liveness fails during SMTP outage | External mail dependency inside liveness | Remove SMTP from liveness; design readiness accurately. |
| Readiness `DOWN` drops traffic while outbox works | Readiness depends on optional mail | Scope health groups to real serving requirements. |
| Only custom health shows, built-in missing | Custom sender/auto-config differs from expected | Check beans, contributor IDs, and properties. |
| Health polled twice per request | Built-in and custom both enabled | Keep only the indicator you intend to run. |
| Missing metrics/health post-startup | Lazy registration or disabled indicator | Inspect endpoints and auto-config conditions. |
| Unit test sends production email | Test context uses real credentials and `send` | Mock sender or use test SMTP server; assert zero messages. |
| Health 200 OK while workers stopped | Health checks SMTP connectivity only | Monitor queue lag, outbox depth, and worker metrics. |
| Health response exposes account addresses | Unfiltered exception/detail attached | Sanitize data and restrict `show-details`. |
| Background probe stays `UP` after stalling | Stale snapshot missing age check | Add staleness threshold and probe-age metric. |
| Synthetic mail skews dashboards | Test mail mixed with transactional | Separate type/metrics and bound cadence. |

## 27. Essential test matrix

A mail health indicator test suite should cover:

| Case | Health status | Real emails sent |
|---|---|---:|
| `testConnection()` succeeds | `UP` | 0 |
| `AUTH` rejected | `DOWN` | 0 |
| SMTP host unreachable | `DOWN` | 0 |
| TLS handshake fails | `DOWN` | 0 |
| Mail sender unconfigured | Absent or contract-defined status | 0 |
| 100 consecutive health calls | Matches state/probe cache | 0 |
| Two replicas scraped simultaneously | Each replica's independent state | 0 |
| Health cache hit | No new network connection needed | 0 |
| Background probe stale | `UNKNOWN`/`DOWN` per policy | 0 |
| Liveness during SMTP provider outage | Does not fail over optional SMTP | 0 |
| Readiness while outbox accepts work | Per application contract | 0 |
| Separate scheduled synthetic E2E job | Independent job status | Only approved, bounded test messages |

Key technical assertions:

- `verify(sender).testConnection()` when designed for single-connect probes.
- `verifyNoMoreInteractions(sender)` ensuring no `send` overload runs.
- Test SMTP server receives **0 messages** after health checks.
- Zero outbox rows created by health endpoints.
- No recipient, subject, or body needed for health to run.
- Error branches never fall back to sending real mail.
- Health groups and HTTP status codes verified via component tests.
- Probes never include secrets or raw SMTP debug output in responses.

Never run tests against production SMTP or real credentials; that increases risk and makes tests flaky.

## 28. Pre-production checklist

1. **Clear health goal:** configuration, connectivity, or pipeline state.
2. **Never call `JavaMailSender.send(...)` inside health indicators** or health endpoint handlers.
3. Use either the built-in mail indicator or a custom `testConnection()` indicator—never both unnecessarily.
4. Keep recipients, subjects, and bodies out of health probes.
5. Match SMTP host, port, TLS, and timeouts to provider requirements.
6. Bound connect/AUTH frequency with caching or background probes where needed.
7. Exclude external SMTP from liveness unless truly required by architecture.
8. Tie readiness to SMTP **only if SMTP downtime truly prevents serving**.
9. Keep credentials, tokens, raw exceptions, and sensitive details out of health details.
10. Protect health endpoints with network controls and authorization.
11. Unit-test every health branch to guarantee zero `send` calls.
12. Integration-test against a test SMTP server to confirm zero received messages.
13. Pair health checks with queue lag, attempt, error, and provider-event monitoring.
14. Isolate synthetic sending into a dedicated job with recipient allowlists, quotas, schedules, and audits.
15. Maintain a runbook for mail health `DOWN` without causing restart loops or retry storms.
16. If mail is an optional dependency, use degraded mode/outbox buffering so core business flows survive.

## 29. Key takeaways

- **A health indicator is not an email-sending API.** Calling `JavaMailSender.send(...)` in a health endpoint can dispatch real emails on every monitoring poll.
- `JavaMailSenderImpl.testConnection()` tests connectivity/authentication and closes the transport; it sends no MIME content to recipients.
- Spring Boot's built-in mail health can use connect-only probing when auto-configured; verify against your exact version and beans.
- Successful connect/auth proves only part of SMTP health—**never delivery, Inbox placement, or reads**.
- Even without sending email, every connect/AUTH check carries operational cost and risk of rate limits or account lockouts if misconfigured.
- Apply SMTP timeouts, health time budgets, caching, or background probes under high check frequency.
- External SMTP dependencies do not belong in **liveness** by default; design readiness around true application roles and outbox buffering.
- For custom indicators, narrow dependencies via `MailConnectivityProbe` to prevent accidental `send` calls.
- Tests must verify **zero send calls** and **zero received messages** on both success and failure paths.
- When real end-to-end verification is needed, build separate synthetic monitoring with dedicated test mailboxes, bounded cadence, and audits.
- Combine health status with queue, worker, and provider-event metrics for complete operational visibility.

**Conclusion:** Safe health checking in Spring Framework Mail measures **connectivity or pipeline state without generating real emails**. Use `testConnection()` for SMTP checks, keep health endpoints free of mail-sending side effects, control check frequency, and separate liveness from readiness appropriately. When true end-to-end delivery checks are needed, run an approved synthetic test separately—never turn every health probe into an accidental email blast.
