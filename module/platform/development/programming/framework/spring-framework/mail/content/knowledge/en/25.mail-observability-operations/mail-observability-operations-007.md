# Alerting on Rising Error Rates, Timeouts, and Bounces

## 1. Why an email-sending system needs proactive alerting

In an application using **Spring Framework Mail**, calling **JavaMailSender.send(...)** is one technical step in the notification pipeline. For operations, the key question is not merely “did the send method run?” but also:

- How many email submissions to the SMTP server failed?
- Are errors concentrated on one provider, one notification stream, or one environment?
- Are **connect timeouts**, **read timeouts**, or **write timeouts** spiking abnormally?
- Did the SMTP server accept the message, yet many recipients later reported **bounces**?
- Is the system retrying endlessly without addressing the root cause?
- Are notifications backing up in the outbox longer than acceptable?
- Is alerting noisy at low traffic, skewed by webhook delays, or distorted because one email was attempted multiple times?

An email outage can linger silently: web APIs still return success, business transactions commit, yet notifications go unsent or bounce continuously. Waiting for customer complaints makes it hard to determine impact scope and start time.

This lesson focuses on designing **metrics, dashboards, alert rules, and incident response workflows** for three signals:

1. **Rising send error rates** — increasing failed or uncertain SMTP submissions.
2. **Rising timeouts** — slow DNS/TCP/SMTP, unresponsive connections, or lost replies after `DATA`.
3. **Rising bounces** — server/provider accepted initial submission but later reported undeliverability.

Examples use Spring Boot, `JavaMailSender`, **Micrometer**, **Prometheus**, **Alertmanager**, and a notification/outbox system. Specific tools may change, while the principles of signal definition and error classification remain constant.

## 2. Observing the email journey accurately

A notification typically traverses multiple stages:

~~~text
Business event
      |
      v
Notification / outbox record
      |
      v
Mail worker / renderer
      |
      v
JavaMailSender + Jakarta Mail
      |
      | DNS, TCP, TLS, SMTP AUTH, MAIL FROM, RCPT TO, DATA
      v
Submission SMTP server / ESP
      |
      | Initial acceptance or rejection response
      v
Provider queue / relay
      |
      | Transfer to receiving mail servers
      v
Receiving system
      |
      +-- Delivered
      +-- Deferred
      +-- Bounced
      +-- No clear response
      |
      v
Webhook / DSN / provider event
      |
      v
Delivery-state processor
~~~

Two key observation points:

**Submission:** did the app successfully submit the message to the SMTP server/ESP? A normal return from **send(...)** generally indicates initial acceptance at the submission hop, without guaranteeing Inbox delivery.

**Delivery:** what did the provider or receiving system report—delivered, deferred, or bounced? Most of this feedback arrives **asynchronously** via webhooks, APIs, or **Delivery Status Notifications (DSN)**.

An “email success rate” chart counting only **send() not throwing an exception** actually measures **SMTP submission acceptance**, not the percentage of emails seen by recipients.

## 3. Define states before defining metrics

Without standardized states, dashboards easily double-count a message or mix unrelated outcomes.

### Submission states

| State | Meaning |
|---|---|
| **PENDING** | Send intent persisted, not yet attempted over SMTP |
| **PROCESSING** | Worker claimed and actively processing |
| **ACCEPTED / SUBMITTED** | SMTP server/ESP accepted message at submission stage |
| **RETRY_WAIT** | Unsuccessful attempt with retry scheduled |
| **FAILED** | Confirmed unable to continue per policy |
| **UNKNOWN** | Uncertain whether server accepted the message |

### Delivery states

| State | Meaning |
|---|---|
| **DELIVERED** | Provider/receiving system reported delivery per its definition |
| **DEFERRED** | Delivery is temporarily delayed |
| **BOUNCED** | Evidence of unsuccessful delivery |
| **COMPLAINED** | Provider reported spam complaint feedback |
| **UNKNOWN** | No reliable final status yet |

**SUBMITTED does not equal DELIVERED**. **DEFERRED does not equal BOUNCED**. A retried message can generate multiple submission attempts while representing **one business notification**.

That is why the system should separately store **notification ID**, **attempt ID**, **provider message ID**, and **event ID** where needed.

## 4. Classify errors before creating alerts

A `MailException` can wrap many root causes. If a dashboard lumps everything under `mail_error`, operators cannot tell whether to fix configuration, networking, recipient data, or provider policy.

| Normalized Error Category | Examples | Recoverability |
|---|---|---|
| **dns** | `UnknownHostException`, DNS resolver failure | Possibly transient or bad hostname |
| **connection_refused** | `ConnectException` before SMTP session | Service down or wrong port |
| **connect_timeout** | TCP failed to connect within timeout | Network, firewall, routing |
| **read_timeout** | Waited too long for SMTP reply | Phase-dependent; outcome may be uncertain |
| **write_timeout** | Timed out writing socket data | Phase-dependent; outcome may be uncertain |
| **tls** | `SSLHandshakeException`, invalid certificate | Usually inspect endpoint/truststore |
| **auth** | `MailAuthenticationException` | Usually fix credentials/permissions |
| **smtp_4xx** | Temporary SMTP rejection | Retry with policy-driven backoff |
| **smtp_5xx** | Permanent SMTP rejection | Check recipient, sender, policy |
| **mime_preparation** | `MailParseException`, template/MIME error | Usually fix data or code |
| **provider_policy** | Rate limit, account quota, reputation | Depends on response and provider contract |
| **unknown** | Insufficient evidence of cause/phase | Requires investigation or reconciliation |

These are **application-defined error categories**, not a built-in Spring Mail enum. Actual SMTP codes and exception classes must be analyzed in context.

Specifically:

- Never assume **every SMTP 5xx means nonexistent recipient**.
- Never assume **every `SocketTimeoutException` is safely retryable**.
- Never classify TCP connection failures as SMTP 4xx/5xx responses.
- When a batch has partial outcomes, account per message/recipient or explicitly mark uncertainty.

## 5. Three key metrics do not share the same denominator

To compute ratios accurately, first establish **what unit is counted**.

### Submission failure rate by attempt

~~~text
Submission failure rate =
  SMTP submission attempts resulting in failure
  ----------------------------------------------
  total SMTP submission attempts in same window
~~~

Example with 100 SMTP attempts: 91 accepted, 7 failed, 2 unknown.

- **Confirmed failure** rate = 7 / 100 = 7%.
- **Unhealthy-or-unknown** rate = (7 + 2) / 100 = 9%.
- **Confirmed acceptance** rate = 91 / 100 = 91%.

Display **UNKNOWN** separately instead of folding it silently into confirmed failures and losing semantics. You can create an “unhealthy submission” alert combining `FAILED + UNKNOWN`, provided it is named clearly.

### Timeout rate by attempt

~~~text
Timeout attempt rate =
  attempts that timed out
  -------------------------
  total attempts in window
~~~

This is an **attempt-level rate**, not the rate of undelivered recipients. If one notification times out three times, it creates three timeout attempts.

### Bounce rate by submitted notification

~~~text
Bounce rate (by notification) =
  submitted notifications with matching bounces
  ---------------------------------------------
  submitted notifications in the same cohort
~~~

Crucial distinction: bounces arrive **after submission**, delayed from seconds to many hours or longer. Dividing bounces received in 10 minutes by emails sent in the same 10 minutes does not always reflect that batch's true bounce rate.

## 6. Never mix notification counts and attempt counts

Example notification **N100**:

~~~text
N100
 |
 +-- Attempt 1 -> Connect timeout
 |
 +-- Attempt 2 -> SMTP 451
 |
 +-- Attempt 3 -> SMTP accepted
 |
 +-- Delivery event -> BOUNCED
~~~

Counting attempts:

- Total attempts: **3**.
- Failed attempts: **2**.
- Accepted attempts: **1**.

Counting notifications:

- Business notifications: **1**.
- Accepted submissions: **1**.
- Bounced: **1**.

For transport error alerts, counting attempts reveals SMTP pressure. For reporting customer impact, count **unique notifications/recipients**. Never claim “200 customers failed” just because 200 failed attempts occurred; that could be 20 notifications retried 10 times each.

If a single `MimeMessage` targets multiple recipients, outcomes can vary per recipient. To measure bounces accurately, track a **notification-recipient identity** or per-recipient delivery record rather than relying solely on `Message-ID` and assuming all recipients share one status.

## 7. Choosing time windows and minimum sample thresholds

Ratio-based alerts require both a **ratio threshold** and a **minimum sample condition**.

Example:

~~~text
In 10 minutes:
  2 failures / 4 attempts = 50%

In 10 minutes:
  200 failures / 4,000 attempts = 5%
~~~

50% sounds severe, yet reflects only 4 attempts. 5% across 4,000 attempts affects far more notifications and warrants attention.

An illustrative policy:

| Signal | Short Window | Long Window | Trigger Condition |
|---|---|---|---|
| Submission failures | 5–10 min | 30–60 min | Ratio exceeds threshold **and** sufficient attempts |
| Timeouts | 5–10 min | 30 min | Ratio spikes or absolute count spikes |
| Bounces | 1–6 hours | 24 hours or matured cohort | Bounce ratio rises with sufficient sample |
| Outbox backlog | 5–15 min | 1 hour | Pending age / queue depth exceeds target |
| Worker liveness | 2–5 min | Per poll schedule | Missing expected heartbeats or scrapes |

Numbers are illustrative, not Spring Mail defaults. Calibrate to traffic volume, campaign schedules, SLAs, and real baselines.

### Why bounces need a separate window

When a campaign sends thousands of emails at 09:00, many bounces may arrive at 09:30. Dividing bounces in 09:30–09:40 by submissions in that same 09:30–09:40 window gives a denominator near 0 and a meaningless ratio.

For bounces, **submission-time cohorts** are far more reliable. Sections below explain using both event-arrival proxy alerts and mature cohort ratios.

## 8. Recommended monitoring architecture

One organizational layout:

~~~text
Spring Mail application
    |
    +-- Mail submission metrics
    |       attempts, accepted, failed, unknown, duration
    |
    +-- Worker / outbox metrics
    |       pending, retry, oldest age, expired lease
    |
    v
Micrometer -> /actuator/prometheus
    |
    v
Prometheus ----> Alert rules ----> Alertmanager
    |                                  |
    v                                  v
Grafana dashboards              On-call / incident routing

ESP/SMTP provider
    |
    +-- Bounce / delivery / deferral webhooks
    |
    v
Verified webhook receiver
    |
    +-- Persist provider events idempotently
    +-- Update delivery state
    +-- Emit delivery metrics
    |
    v
Prometheus and/or cohort analytics
~~~

**Never create a single `email_failed_total` counter fed by every source**, as it easily double-counts one notification: once on SMTP failure and once on webhook bounce. Maintain separate metric names and states per stage.

## 9. Core metric set

A minimal set can include:

| Logical Metric | Type | Meaning |
|---|---|---|
| **mail.submissions** | Counter | SMTP send attempts split by result/category |
| **mail.submission.duration** | Timer | Execution duration of submission attempts |
| **mail.notification.submitted** | Counter | Notification-recipients confirmed submitted for the first time |
| **mail.delivery.events** | Counter | Valid delivery events received by type |
| **mail.notification.bounced** | Counter | Notification-recipients confirmed bounced for the first time |
| **mail.outbox.pending** | Gauge | Notifications waiting to be processed |
| **mail.outbox.oldest.due.age** | Gauge | Wait time of the oldest due item |
| **mail.outbox.retry** | Gauge | Notifications awaiting retry |
| **mail.worker.last.poll** | Gauge | Unix timestamp of last poll |
| **mail.webhook.rejected** | Counter | Webhooks rejected due to auth/schema |

These follow **Micrometer dotted naming**. When exported to Prometheus, names convert per naming conventions—for example, **mail.submissions** may export as **mail_submissions_total**, and **mail.submission.duration** as timer series in seconds.

Never assume every library, registry, and version emits identical suffixes without checking actual exported metrics. Subsequent PromQL examples assume the exporter emits the illustrative names shown.

## 10. Label design: enough detail to diagnose without exploding cardinality

A metric can be sliced by useful dimensions:

| Label | Example | Purpose |
|---|---|---|
| **provider** | `primary-smtp`, `backup-smtp` | Identify failing ESP or mail config |
| **stream** | `transactional`, `security`, `marketing` | Distinguish notification streams |
| **result** | `accepted`, `failed`, `unknown` | Separate submission outcomes |
| **category** | `none`, `connect_timeout`, `smtp_4xx`, `auth` | Group root causes |
| **environment** | `production`, `staging` | Separate environments |
| **region** | `region-a`, `region-b` | Spot regional incidents |

Labels must come from a **finite, controlled value set**. Never use:

- Recipient email addresses or usernames.
- Subjects, `Message-ID`s, notification IDs, or attempt IDs.
- Full exception messages or SMTP reply text.
- URLs containing tokens or personal info.
- Arbitrary file paths or attachment names from requests.
- Tenant IDs with hundreds of thousands of values without a cardinality plan.

To investigate an individual notification, use **structured logs, trace IDs, and databases** with proper access controls. Metrics are for aggregate calculations.

### Why cardinality matters

Each distinct label combination creates a time series:

~~~text
provider(3)
  x stream(4)
  x result(3)
  x category(12)
  x instance(20)
  = 8,640 potential series
~~~

That is just one metric. Adding **recipient email** with millions of values can massively inflate Prometheus storage, query cost, and operational instability.

Classify errors into **normalized codes** like `smtp_4xx` or `read_timeout` instead of putting `exception.getMessage()` into labels.

## 11. Adding Micrometer and Spring Boot Actuator

In a Spring Boot application, add dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Library versions should be managed compatibly with your Spring Boot version. Example exposure config:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  metrics:
    tags:
      application: mail-notification-service
~~~

Once Actuator and the Prometheus registry are active, the endpoint is typically:

~~~text
GET /actuator/prometheus
~~~

Allow only **Prometheus or authorized monitoring systems** to access this endpoint, using a management port, network policy, authentication, or reverse proxy depending on infrastructure. **Never expose internal-structure metrics endpoints publicly to the Internet.**

### Why inspect actual exporter output?

Prometheus naming conventions translate Micrometer dots to underscores and add suffixes like `_total`, `_seconds`, or histogram series. Before deploying alert rules to production, verify:

- Exact exported metric names and labels.
- That counters increment during a test email send.
- That timers emit `_count`, `_sum`, and `_bucket` series when histograms are enabled.
- That metrics are not filtered out by Spring profiles or registry filters.
- That Prometheus successfully scrapes the target endpoint.

Avoid copying a PromQL query that does not match exporter names and concluding “zero errors” just because a dashboard stays at 0.

## 12. Recording metrics for SMTP submission attempts

A wrapper around **JavaMailSender** can record **one outcome per `MimeMessage` submission**.

Application-managed classification model:

~~~java
public record MailFailure(
        String result,    // failed or unknown
        String category   // dns, auth, read_timeout, ...
) {
}

public interface MailFailureClassifier {
    MailFailure classify(
            org.springframework.mail.MailException exception
    );
}
~~~

**MailFailureClassifier** is not a built-in Spring API. It is an abstraction separating retry/status decisions from metric recording.

A metrics recorder class:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.time.Duration;
import org.springframework.stereotype.Component;

@Component
public class MailSubmissionMetrics {

    private final MeterRegistry registry;

    public MailSubmissionMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(
            String provider,
            String stream,
            String result,
            String category,
            long elapsedNanos
    ) {
        registry.counter(
                "mail.submissions",
                "provider", provider,
                "stream", stream,
                "result", result,
                "category", category
        ).increment();

        Timer.builder("mail.submission.duration")
                .tag("provider", provider)
                .tag("stream", stream)
                .tag("result", result)
                .register(registry)
                .record(Duration.ofNanos(elapsedNanos));
    }
}
~~~

This code assumes **provider**, **stream**, **result**, and **category** are normalized to finite sets. Never pass raw values from requests or exception messages.

**The counter increments once per attempt**, while the timer records that attempt's duration. If a notification retries three times, the counter increments three times—that is intentional.

### Instrumented sender

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class ObservedMailTransport {

    private final JavaMailSender sender;
    private final MailSubmissionMetrics metrics;
    private final MailFailureClassifier classifier;

    public ObservedMailTransport(
            JavaMailSender sender,
            MailSubmissionMetrics metrics,
            MailFailureClassifier classifier
    ) {
        this.sender = sender;
        this.metrics = metrics;
        this.classifier = classifier;
    }

    public void submit(
            MimeMessage message,
            String provider,
            String stream
    ) {
        long started = System.nanoTime();
        String result = "unknown";
        String category = "unclassified";

        try {
            sender.send(message);
            result = "accepted";
            category = "none";
        } catch (MailException exception) {
            MailFailure failure = classifier.classify(exception);
            result = failure.result();
            category = failure.category();
            throw exception;
        } finally {
            metrics.record(
                    provider,
                    stream,
                    result,
                    category,
                    System.nanoTime() - started
            );
        }
    }
}
~~~

The code above handles **one `MimeMessage` per submit**. If the application calls an API sending an array of messages or a message with multiple recipients and partial outcomes, instrument per message/recipient and actual error info; never treat a batch exception as meaning everything failed.

### Meaning of `result` in this example

- **accepted:** `send(...)` returned normally at the SMTP submission hop.
- **failed:** the classifier found evidence the server rejected or never sent, and the operation clearly failed.
- **unknown:** insufficient evidence to confirm acceptance, such as losing the reply at the final phase of SMTP `DATA`.

This example assumes the classifier **does not classify every `MailException` as `failed`**. When phase/SMTP reply is unknown, keep `unknown`. Production systems must ensure the wrapper never loses the original exception if secondary metrics logic throws, and should instrument content-preparation errors separately if covering the full pipeline.

**The timer measures submission duration**, not time to reach the mailbox. If end-to-end latency is required, measure from business event to delivery event with a separate metric having clear semantics.

## 13. Micrometer metrics and the database share no transaction

In an outbox-based application, a worker may:

1. Send the email; SMTP accepts it.
2. Increment the `accepted` counter.
3. Open a transaction to update the outbox row to `SUBMITTED`.
4. Fail on the database update.

The `accepted` metric still increments even though the database was not updated. That is not necessarily a metric bug: it reflects the **SMTP attempt** outcome, whereas the database reflects business processing state that failed to persist.

**Micrometer counters do not participate in database transactions.** Never assume the two systems update atomically.

Therefore, if you need **mail.notification.submitted** to count unique notifications:

- Trigger it on a conditional/idempotent transition—for example, prior state was not `SUBMITTED` and the update succeeded.
- Keep attempt counters and notification counters separate.
- Understand that metric exporters/counters can drop an increment on process crash.
- Use database queries or provider data as the durable reconciliation source when high accuracy is required.

Metrics are operational and alerting signals; they **do not replace audit logs or notification ledgers**.

## 14. Status views to separate on dashboards

A useful dashboard splits into multiple charts instead of one “Email success” tile.

| Chart | How to Read It |
|---|---|
| Submission attempts/s | Actual load pushed into SMTP |
| Accepted / failed / unknown rates | Immediate status at submission stage |
| Failure ratio by provider/stream | Blast radius of errors |
| Timeout ratio and absolute timeout count | Network or SMTP slowness/breakage |
| Submission latency p50 / p95 / p99 | Latency degradation before errors spike |
| Outbox pending / retry / oldest age | Queue backlog issues |
| Bounce events/s | Asynchronous feedback volume |
| Mature-cohort bounce ratio | Bounce rate for notifications given enough observation time |
| Hard vs. soft bounces | Recipient list quality vs. temporary disruptions |
| Webhook lag and rejected events | Health of delivery-ingestion pipeline |

Keep units explicit:

- **Attempts/s** is not users/s.
- **Timeout attempts** are not lost notifications.
- **Bounce events** are not unique bounced notifications.
- **p95 seconds** is attempt latency, not delivery latency.

## 15. PromQL: viewing submission failure rates

Assume metric:

~~~text
mail_submissions_total{
  provider="primary-smtp",
  stream="transactional",
  result="failed",
  category="smtp_4xx"
}
~~~

Total attempts over 10 minutes, by provider/stream:

~~~promql
sum by (provider, stream) (
  increase(mail_submissions_total[10m])
)
~~~

Attempts resulting in FAILED:

~~~promql
sum by (provider, stream) (
  increase(mail_submissions_total{result="failed"}[10m])
)
~~~

Ratio of FAILED or UNKNOWN:

~~~promql
sum by (provider, stream) (
  increase(
    mail_submissions_total{result=~"failed|unknown"}[10m]
  )
)
/
clamp_min(
  sum by (provider, stream) (
    increase(mail_submissions_total[10m])
  ),
  1
)
~~~

These example queries do not change metric semantics:

- **FAILED + UNKNOWN** computes the “unhealthy submission” ratio; do not call it “confirmed failure rate”.
- If you want confirmed failure rate, filter strictly on **result="failed"**.
- If there is no data because the app stopped or scrapes failed, the expression may return no series rather than 0. Add separate liveness/scrape alerts.
- **increase()** can yield fractional values due to Prometheus extrapolation across samples in a window, even though counters increment by integers.

### Choosing windows

**[5m]** reacts quickly but is noisy; **[30m]** is smoother but alerts later. Use short windows for high-severity alerts and longer windows for warnings or trend comparisons.

## 16. Alerting on rising error rates: filtering low-traffic noise

Suppose the alerting policy is:

> Alert when the FAILED + UNKNOWN ratio exceeds 5% over 10 minutes, with at least 100 submission attempts, sustained for at least 5 minutes.

Example Prometheus recording/alert rule:

~~~yaml
groups:
  - name: spring-mail-submission
    rules:
      - alert: MailSubmissionUnhealthyRateHigh
        expr: |
          (
            sum by (provider, stream) (
              increase(
                mail_submissions_total{result=~"failed|unknown"}[10m]
              )
            )
            /
            clamp_min(
              sum by (provider, stream) (
                increase(mail_submissions_total[10m])
              ),
              1
            )
          ) > 0.05
          and on (provider, stream)
          sum by (provider, stream) (
            increase(mail_submissions_total[10m])
          ) >= 100
        for: 5m
        labels:
          severity: warning
          service: spring-mail
        annotations:
          summary: "Unhealthy submission rate elevated"
          description: "Provider and stream failed/unknown rate exceeded 5%."
          runbook_url: "https://runbooks.example.com/mail/submission"
~~~

In this example, **runbook_url** is an illustrative doc URL, not a live deployed page.

### What does the AND condition solve?

Checking only ratio > 5% lets 3 failures out of 4 attempts trigger an alert. Requiring **at least 100 attempts** suppresses noise from tiny samples.

However, if a security stream sends only 20 emails/day, a floor of 100 prevents ratio-based alerting altogether. For low-volume critical streams, add dedicated alerts for:

- Consecutive failures.
- Notifications permanently failed after retries.
- Outbox age breaching SLA.
- Critical configuration errors such as authentication failures.
- Missing worker polls when the system should be running.

**Ratio thresholds must pair with volume thresholds and stream criticality.**

### Why use `for`?

**for: 5m** requires the expression to stay true continuously across evaluations before firing. This filters out brief blips. For severe outages like total SMTP loss, use a shorter duration while checking against pager flapping.

## 17. Alerting on rising timeouts by ratio and count

Timeouts deserve dedicated monitoring because they signal network issues or slowing SMTP providers before overall submission failure rates visibly climb.

### Timeout count

Assume `category` has three timeout values:

- **connect_timeout**
- **read_timeout**
- **write_timeout**

Query timeout attempts over 10 minutes:

~~~promql
sum by (provider, stream) (
  increase(
    mail_submissions_total{
      category=~"connect_timeout|read_timeout|write_timeout"
    }[10m]
  )
)
~~~

### Timeout ratio

~~~promql
sum by (provider, stream) (
  increase(
    mail_submissions_total{
      category=~"connect_timeout|read_timeout|write_timeout"
    }[10m]
  )
)
/
clamp_min(
  sum by (provider, stream) (
    increase(mail_submissions_total[10m])
  ),
  1
)
~~~

Illustrative alert:

~~~yaml
- alert: MailSmtpTimeoutRateHigh
  expr: |
    (
      sum by (provider, stream) (
        increase(
          mail_submissions_total{
            category=~"connect_timeout|read_timeout|write_timeout"
          }[10m]
        )
      )
      /
      clamp_min(
        sum by (provider, stream) (
          increase(mail_submissions_total[10m])
        ),
        1
      )
    ) > 0.02
    and on (provider, stream)
    sum by (provider, stream) (
      increase(mail_submissions_total[10m])
    ) >= 100
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "SMTP timeout rate exceeded threshold"
~~~

In environments with only a few attempts/minute, add an absolute-count alert, such as **at least 10 timeouts in 10 minutes**, or a separate rule for critical streams.

### Do not lump all timeouts together

**Connect timeout** indicates a TCP connection could not open in time; usually no message was transmitted.

**Read timeout** can occur while waiting for the greeting, `AUTH`, or the final reply after SMTP `DATA`. When the server received `DATA` but the final reply dropped, the outcome may be **UNKNOWN**, not confirmed `FAILED`.

**Write timeout** can likewise produce an uncertain outcome if partial or full data was transmitted.

If infrastructure or the transport adapter reliably tracks the **failure phase**, add a bounded label **phase=connect|greeting|auth|envelope|data|final_reply|unknown** on a specialized metric. Never guess the phase solely from exception class names.

## 18. Alerting on SMTP latency before timeouts erupt

An SMTP provider often slows down gradually before hard timeouts occur. **Timers** make that visible.

With Micrometer Timer **mail.submission.duration**, a Prometheus registry can export:

~~~text
mail_submission_duration_seconds_count
mail_submission_duration_seconds_sum
mail_submission_duration_seconds_bucket
~~~

The **_bucket** series exists only when histograms are properly configured.

Example enabling percentile histograms:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        mail.submission.duration: true
~~~

After confirming the exporter emits bucket series, compute p95:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, provider, stream) (
    rate(mail_submission_duration_seconds_bucket[10m])
  )
)
~~~

Or compute average latency from the timer:

~~~promql
sum by (provider, stream) (
  rate(mail_submission_duration_seconds_sum[10m])
)
/
clamp_min(
  sum by (provider, stream) (
    rate(mail_submission_duration_seconds_count[10m])
  ),
  0.001
)
~~~

The unit here is **seconds**. Never query p95 without histograms configured and interpret an empty chart as “zero latency”.

### When are latency alerts useful?

- Submissions still succeed, yet p95 rises severalfold over baseline.
- Only one provider/region slows down while others stay normal.
- Outbox age grows because each send takes longer.
- Connection pools, executors, or SMTP queues saturate.

Thresholds like **p95 > 8 seconds for 15 minutes** are merely examples; calibrate against typical message/attachment send durations and configured timeouts.

If emails carry large attachments, categorize sensibly or track size distributions to distinguish payload-driven slowness from infrastructure slowness. Never add exact byte size as a high-cardinality label; use bounded size buckets if needed.

## 19. Zero traffic does not mean a healthy system

An easily misinterpreted case:

~~~text
09:00–09:10
  Attempts: 0
  Error rate on dashboard: no data
~~~

If workers stop completely, error rates can vanish instead of spiking. The system needs additional alerts:

- **Prometheus scrape target down**.
- **Workers not polling on schedule**.
- **Pending outbox growing with zero submission attempts**.
- **Oldest due notification age** breaching SLA.
- **Webhook receiver getting zero delivery events** despite expected traffic.

Example scrape check:

~~~promql
up{job="mail-notification-service"} == 0
~~~

If a target disappears completely from service discovery, the **up** series goes stale and that query stops seeing the target. Configure service discovery alerts, missing-target alerts, or infrastructure checks rather than relying solely on `up == 0`.

### Worker heartbeat

A worker can update its last poll timestamp:

~~~java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;

public final class MailWorkerHeartbeat {

    private final AtomicLong lastPollSeconds =
            new AtomicLong(0L);

    public MailWorkerHeartbeat(MeterRegistry registry) {
        Gauge.builder(
                "mail.worker.last.poll",
                lastPollSeconds,
                value -> (double) value.get()
        ).register(registry);
    }

    public void polled() {
        lastPollSeconds.set(Instant.now().getEpochSecond());
    }
}
~~~

Call **polled()** on every actual polling cycle, not only when an email succeeds. Example query:

~~~promql
time() - mail_worker_last_poll > 300
~~~

Account for initial value 0, newly starting workers, scale-to-zero instances, and clock skew between JVM and Prometheus. For infrequent scheduled jobs or on-demand workers, 300 seconds is inappropriate; match the actual cadence.

## 20. Monitoring the outbox to catch issues that never hit SMTP

A notification may never even reach `JavaMailSender`, for example:

- Workers stopped running.
- Queues are locked by a failing transaction.
- The scheduler is disabled.
- `RETRY` records have wrong `next_attempt_at`.
- Tasks lack executor threads.
- `PROCESSING` leases are not reclaimed.

In those cases **mail.submissions** does not increment, and SMTP error rates reveal nothing.

Useful metrics:

| Metric | Meaning |
|---|---|
| **mail_outbox_pending** | Notifications waiting |
| **mail_outbox_retry** | Notifications awaiting retry |
| **mail_outbox_processing** | Notifications currently claimed |
| **mail_outbox_expired_lease** | `PROCESSING` records with expired leases |
| **mail_outbox_oldest_due_age_seconds** | Wait time since the oldest due record became eligible |
| **mail_worker_claimed_total** | Total records claimed by workers |
| **mail_worker_completed_total** | Total records completed per policy |

**Oldest due age** is usually more informative than pending count alone. A queue of 10,000 records can be normal during a large campaign if throughput and wait age stay within SLA. Conversely, a single critical notification waiting 30 minutes can be a severe incident.

Example alert:

~~~yaml
- alert: MailOutboxProcessingStalled
  expr: |
    mail_outbox_oldest_due_age_seconds > 900
    and on (provider, stream)
    mail_outbox_pending > 0
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Mail outbox has due items waiting too long"
~~~

This assumes both gauges carry matching **provider** and **stream** labels. If they are service-wide metrics or carry different labels, adjust the query accordingly. Never copy alert rules blindly without verifying your deployed metric schema.

### Should pending and retry be summed?

Depends on your state machine. If pending counts only `PENDING`, retry count is separate; a “total backlog” view can sum due states. If pending already includes `RETRY`, summing them double-counts. Document each gauge's exact scope.

## 21. Alert severity, sustain windows, and deduplicating alerts

Not every rising signal warrants waking an engineer immediately.

| Level | When Appropriate | Response |
|---|---|---|
| **Info** | Traffic shifts or trends worth tracking | Dashboards, reports |
| **Warning** | Failures/timeouts/bounces exceed baseline while system still runs | Ticket, investigate during support hours |
| **Critical** | Widespread outage, queue past SLA, critical notifications impacted | Page on-call per procedure |

Example:

- **Warning:** failure + unknown rate > 5% over 10m with >= 100 attempts for 5m.
- **Critical:** nearly all transactional submissions failing at meaningful traffic for 5m.
- **Warning:** bounce rate of a matured cohort rises above baseline.
- **Critical:** security-stream outbox stalls and oldest age breaches SLA severely.

Thresholds must be tuned to organizational SLAs, not treated as product defaults.

### Reducing alert storms

When an SMTP provider goes down, multiple alerts may fire together:

~~~text
Connection timeout high
Submission failure high
Outbox backlog high
Delivery event missing
~~~

These can all stem from **one root incident**. Alertmanager can group by **service/provider/stream**, temporarily inhibit downstream alerts when a high-confidence root alert fires, and throttle repeat notifications.

Never inhibit all bounce alerts just because an SMTP error fired: high bounces can come from bad recipient data or DMARC independently of connection failures.

## 22. Bounces are asynchronous signals, not MailSendException

Suppose an email is accepted by the provider at 09:00:

~~~text
09:00  JavaMailSender.send(...) succeeds
09:01  ESP begins relaying to receiving domain
09:03  Receiver temporarily defers -> deferred
09:20  Receiver returns 550 -> permanent failure
09:21  ESP emits bounce webhook
09:21  Application updates notification to BOUNCED
~~~

The **send(...)** call at 09:00 cannot know the final outcome at 09:21.

Catching only `MailSendException` misses bounces occurring after SMTP acceptance. Conversely, not every `MailSendException` is a bounce: DNS, TLS, or authentication failures before submission are not asynchronous delivery outcomes.

Bounce observation sources can include:

- ESP webhooks for **bounce**, **delivery**, and **deferred** events.
- Provider APIs for querying send and delivery status.
- **DSN (Delivery Status Notification)** messages sent to the envelope sender / bounce mailbox.
- ESP dashboards/exports ingested into data pipelines.

When using multiple providers, each source has its own schema and semantics; normalize them before combining onto one dashboard.

## 23. Classifying hard bounces vs. soft bounces in alerts

| Type | Example | Operational Interpretation |
|---|---|---|
| **Hard bounce** | Confirmed nonexistent address | Likely poor recipient list quality |
| **Soft bounce** | Full mailbox, receiving server temporarily busy | May recover; retry/defer applies |
| **Policy rejection** | Blocked due to authentication, reputation, or anti-spam | Inspect sender/domain/ESP |
| **Deferred** | Message undelivered yet still queued | Do not treat as a final bounce |
| **Spam complaint** | Recipient marked email unwanted | Distinct signal; do not fold into bounces |

**Hard/soft** are operational provider terms, not a strict 1-to-1 mapping from SMTP reply codes:

- An SMTP 4xx error may be retried repeatedly by the provider until finally marked failed.
- A 5xx may reflect sender policy rather than proving the recipient does not exist.
- A **deferred** event does not mean the address should be permanently suppressed.

When bounces spike, distinguish **recipient list quality** from **domain authentication/reputation issues**. If 90% of bounces share an SPF/DMARC policy rejection code, bulk-suppressing recipients is the wrong response.

### Two distinct bounce alerts

1. **Hard-bounce ratio high:** alerts on data quality or recipient list hygiene.
2. **Policy-rejection surge:** alerts on authentication, sender reputation, or provider/receiver policy.

Both may rise simultaneously, yet they need different runbooks and owners.

## 24. Normalize and verify webhooks before counting bounces

An inbound event from the Internet must never automatically become truth.

Recommended pipeline:

~~~text
ESP webhook request
        |
        v
Verify signature / authentication
        |
        v
Validate event schema and size
        |
        v
Check provider event ID (idempotency)
        |
        v
Persist event in database
        |
        v
Resolve provider message ID -> notification-recipient
        |
        v
Update delivery state with transition rules
        |
        v
Increment delivery metrics / update aggregates
~~~

Key requirements:

- Verify signatures **against the raw body** if the ESP contract specifies it.
- Check timestamps/nonces or replay protections when supported by the provider.
- Never trust a caller-supplied provider header without authentication.
- Store event IDs under a unique constraint to absorb webhook retries.
- Match provider message ID and recipient against the submitted notification.
- Handle out-of-order events.
- Never modify suppression lists from unverified data.

### A bounce event can arrive multiple times

~~~text
Provider event: E-7123
   |
   +-- Delivery #1 -> app writes DB successfully
   |                     but response times out
   |
   +-- Delivery #2 -> provider resends same E-7123
~~~

If **mail.notification.bounced** increments both times, bounce rates inflate. Distinguish:

- **Webhook requests received:** may count every HTTP request for endpoint operations.
- **Unique valid provider events:** count only the first successful persistence.
- **Unique bounced notifications:** count only notification-recipients transitioning into final bounced state per app semantics.

When a provider supplies no stable event ID, define deduplication rules aligned with their contract; never assume two events sharing a timestamp are automatically duplicates.

## 25. Webhook lag and skew across statistical windows

A data-analysis trap:

~~~text
09:00–09:10: 1,000 emails accepted
09:10–09:20: only 20 new emails accepted
09:10–09:20: 100 bounces arrive for the 09:00 batch
~~~

Computing:

~~~text
100 bounces / 20 submitted = 500%
~~~

yields a ratio that is **not a cohort bounce rate**. It merely divides two event streams occurring in the same wall-clock window that belong to different sets of notifications.

Therefore, use two distinct views:

**A. Bounce event arrival rate** — newly received bounces per minute. Good for spotting sudden spikes in webhooks or delivery pipelines.

**B. Mature-cohort bounce ratio** — proportion of notifications sent in a defined window after allowing enough time for feedback to arrive. Good for evaluating deliverability quality and long-term trends.

Never label a chart showing **bounce events/s** simply as **bounce rate** without explaining the difference.

## 26. Near-real-time bounce surge alerting

To catch sudden spikes quickly, you can divide **unique bounced notifications** received in 1 hour by newly submitted notifications in that same hour as a **proxy**:

~~~promql
sum by (provider, stream) (
  increase(mail_notification_bounced_total[1h])
)
/
clamp_min(
  sum by (provider, stream) (
    increase(mail_notification_submitted_total[1h])
  ),
  1
)
~~~

This is an **operational proxy**, not an exact cohort bounce rate. Numerator and denominator can represent different notification cohorts; the ratio can exceed 100% if webhooks lag or current send volume drops sharply.

A temporary alert should use this proxy only if you understand provider lag and enforce a denominator floor:

~~~yaml
- alert: MailBounceArrivalRatioHigh
  expr: |
    (
      sum by (provider, stream) (
        increase(mail_notification_bounced_total[1h])
      )
      /
      clamp_min(
        sum by (provider, stream) (
          increase(mail_notification_submitted_total[1h])
        ),
        1
      )
    ) > 0.03
    and on (provider, stream)
    sum by (provider, stream) (
      increase(mail_notification_submitted_total[1h])
    ) >= 200
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "Abnormal bounce event surge; check cohort"
~~~

This assumes **mail_notification_bounced_total** increments once per confirmed bounced notification-recipient, not per HTTP webhook retry. **mail_notification_submitted_total** counts notification-recipients upon first confirmed acceptance.

**Never use this proxy threshold to automatically block recipients or conclude list quality is permanently bad.** It is an investigation trigger requiring cohort checks, provider dashboards, policy error inspection, and event-lag checks.

## 27. Calculating bounce rates more accurately by cohort

A cohort can be defined by **submission timestamp**, such as notifications accepted in a 24-hour window that have had at least one hour to accumulate feedback.

Illustrative PostgreSQL query:

~~~sql
WITH mature_submissions AS (
    SELECT
        notification_id,
        recipient_id,
        provider,
        stream,
        delivery_status
    FROM notification_delivery
    WHERE submitted_at >= CURRENT_TIMESTAMP - INTERVAL '25 hours'
      AND submitted_at <  CURRENT_TIMESTAMP - INTERVAL '1 hour'
      AND submission_status = 'SUBMITTED'
)
SELECT
    provider,
    stream,
    COUNT(*) AS submitted_recipients,
    COUNT(*) FILTER (
        WHERE delivery_status = 'BOUNCED'
    ) AS bounced_recipients,
    COUNT(*) FILTER (
        WHERE delivery_status = 'DELIVERED'
    ) AS delivered_recipients,
    COUNT(*) FILTER (
        WHERE delivery_status = 'UNKNOWN'
    ) AS unknown_recipients
FROM mature_submissions
GROUP BY provider, stream;
~~~

The **notification_delivery** schema is illustrative, not a built-in Spring Mail table. Production schemas must guarantee one row per **notification-recipient**, or use `COUNT(DISTINCT notification_recipient_id)` if storing multiple events/attempts per notification.

From the result:

~~~text
Mature-cohort bounce ratio =
  bounced_recipients / submitted_recipients
~~~

### Why wait one hour?

A **one-hour lag is only an example**. Some providers report bounces rapidly, whereas deferred failures may turn into bounces hours or days later. For each stream, select a **cohort maturity threshold** based on provider feedback latency and retry windows.

Before sufficient maturity time:

- Bounce rates can be underestimated because bounces have not all arrived yet.
- Delivery statuses may remain `PENDING`/`DEFERRED`/`UNKNOWN`.
- Comparing today's cohort to older cohorts can be skewed.

For deep analysis, retain **submission cohort time**, **feedback observation time**, **delivery event time**, status type, and maturity policy.

## 28. Alerting on mature cohort ratios

A periodic aggregation job can export gauges:

~~~text
mail_bounce_cohort_ratio{
  provider="primary-smtp",
  stream="transactional",
  cohort_window="last_24h_matured"
} 0.042

mail_bounce_cohort_size{
  provider="primary-smtp",
  stream="transactional",
  cohort_window="last_24h_matured"
} 2500
~~~

`cohort_window` values must come from a fixed set. Never attach per-cohort timestamps as Prometheus labels, as doing so explodes time series. Store granular historical data in a database or analytics store instead of labels.

Alert:

~~~promql
(
  mail_bounce_cohort_ratio{
    cohort_window="last_24h_matured"
  } > 0.03
)
and on (provider, stream, cohort_window)
(
  mail_bounce_cohort_size{
    cohort_window="last_24h_matured"
  } >= 200
)
~~~

When exporting gauges, also record the **last aggregation timestamp** and alert on stale data. A flat ratio of 0.001 unchanged for two days because the job crashed does not mean the system is healthy.

### Comparing against baseline

Not all streams share the same bounce baseline. A campaign to a fresh list behaves differently from OTP emails to verified accounts.

Compare:

- The same stream/provider across recent matured cohorts.
- Comparable recipient/campaign groupings at safe aggregation levels.
- Matching hard/soft/policy bounce types.
- Identical maturity standards and observation windows.

If denominator calculations or event schemas change, annotate dashboards so data shifts are not mistaken for real deliverability changes.

## 29. Monitoring delivery webhook latency and failures

A system can send over SMTP normally while bounce dashboards look empty because the webhook receiver is broken.

Example:

~~~text
SMTP submissions: normal
Provider dashboard: shows bounces
Application: 0 bounce events

Possible causes:
  webhook endpoint returning HTTP 500
  signature verification misconfigured
  event parser failing on new schema
  message ID failing to correlate
  event inbox/consumer stalled
~~~

Useful metrics:

| Metric | Meaning |
|---|---|
| **mail_webhook_requests_total** | HTTP requests received |
| **mail_webhook_rejected_total** | Requests rejected for signature/schema/auth |
| **mail_delivery_events_total** | Valid events processed by type |
| **mail_delivery_unmatched_total** | Events failing to match a notification |
| **mail_delivery_event_lag_seconds** | Time from provider event occurrence to app persistence |
| **mail_delivery_inbox_oldest_age_seconds** | Age of oldest backlog event in inbox |
| **mail_delivery_inbox_pending** | Events awaiting processing |

### Alerting on missing webhooks

Never alert solely on “zero bounces in 15 minutes”, since a healthy system can genuinely produce zero bounces.

Better alerts:

- Rising HTTP 5xx rates or signature verification failures.
- Growing event inbox backlog and oldest age.
- Provider reporting ongoing delivery events while the app receives or processes none.
- Delivery-state `UNKNOWN` lingering beyond SLA.
- Long-term divergence between provider exports and application records.

If a provider batches events or emits on an intermittent schedule, liveness alerts must account for that cadence. Never compare webhook counts to submissions in the exact same window while ignoring lag.

## 30. Alerting by SLI/SLO instead of arbitrary thresholds

When email is business-critical, define **Service Level Indicators (SLIs)** and **Service Level Objectives (SLOs)** per tier.

Examples:

**Submission SLI:**

~~~text
Proportion of notifications confirmed accepted by the SMTP provider
within T minutes of creation and eligibility.
~~~

**Worker latency SLI:**

~~~text
Proportion of notifications spending no more than X minutes in
PENDING/RETRY once due for processing.
~~~

**Delivery feedback SLI:**

~~~text
Proportion of delivery events ingested and processed within Y minutes
of provider event emission.
~~~

Do not force **Inbox delivery** as an SLO if the application lacks authoritative proof. Choose indicators the system actually measures and owns.

### Error budget burn rate

For a submission SLO, apply **error budgets**: the allowed proportion of attempts/notifications missing the target. Alerting on high burn rate across both short and long windows catches severe incidents early while reducing noise.

Conceptual example:

~~~text
Target SLO: 99.9% success
Allowed failure fraction: 0.1% = 0.001

Observed failure fraction: 2%

Burn rate = 0.02 / 0.001 = 20
~~~

In practice, define:

- Whether the denominator is attempts or unique notifications.
- How `UNKNOWN` is counted.
- Whether the SLO window is 7, 28, or 30 days.
- Whether notifications rejected for invalid input or outside system responsibility are excluded.
- Allowed grace time before counting a notification as a breach.

Never build an SLO out of counters that fail to separate retries from unique notifications, as it may measure retry chatter rather than user impact.

## 31. Comparing against historical baselines and campaign effects

Email traffic typically follows hourly, daily, or campaign cycles:

~~~text
07:00–09:00: low notifications
09:00–12:00: traffic rises
12:00–13:00: traffic dips
18:00: scheduled campaign send
~~~

An absolute threshold like “more than 50 bounces in 10 minutes” might be normal during a large campaign yet abnormal in a security email flow.

Segment by:

- **stream**: `transactional`, `security`, `marketing`.
- **provider**: SMTP provider or sending account.
- **region** when network issues are regional.
- **environment** so test/staging never mixes into production.
- **campaign category** with a bounded value set where needed, avoiding attaching a new campaign ID per run to long-lived metrics.

### Relative-increase alerts

You can compare current rates against baselines from comparable periods, while avoiding pitfalls:

- When baseline is near zero, a 10x jump can be just a handful of emails.
- Changing providers or templates invalidates older baselines.
- A large send shifting recipient demographics can raise bounce ratios without infrastructure faults.
- Late-arriving delivery feedback alters curves after the submission window closes.

Therefore, **baseline** alerts still need minimum sample sizes, proper windows, and business context.

## 32. Runbook when submission error rates rise

A high failure/unknown rate alert should lead to a concrete investigation procedure, not an empty dashboard.

### Step 1: Confirm scope

- Which provider is affected?
- Which stream: transactional, security, or marketing?
- All instances or a single region?
- Did it start right after a deployment, secret change, or network rule update?
- Are real emails affected or only staging/test?

### Step 2: Break down error categories

| Rising Category | First Investigation Target |
|---|---|
| **dns** | SMTP hostname, resolver, DNS cache, container DNS |
| **connection_refused** | Host/port, SMTP listener, firewall rejections |
| **connect_timeout** | Routing, NAT, egress policy, provider availability |
| **read_timeout** | SMTP latency, wait phase, server overload, network path |
| **write_timeout** | Payload size, bandwidth, SMTP socket/network |
| **tls** | STARTTLS/SMTPS mode, certificate chain, truststore, JDK |
| **auth** | Credentials, account permissions, SMTP AUTH policy |
| **smtp_4xx** | Rate limiting, throttling, transient rejections |
| **smtp_5xx** | Sender/recipient policy, message size, reputation |
| **mime_preparation** | Template/recipient validation, content, attachments |

### Step 3: Cross-check logs and provider

- Inspect normalized error codes and representative trace IDs.
- Check SMTP reply codes and **send phase** if known.
- Check the provider's status page/dashboard.
- Compare against other senders or regions.
- Check timeout settings and concurrency.

### Step 4: Protect business flows

- Never continuously retry misconfigured credentials or broken templates.
- If the provider is down, apply backoff/circuit breakers or fail over per policy.
- When a message lands in `UNKNOWN`, never automatically retry blindly.
- If the outbox is backing up, inspect leases, batch sizes, and worker throughput.
- If caused by a recent deploy, roll back or fix configuration cleanly.

### Step 5: Assess impact

Measure:

- Unique notification-recipients not yet submitted.
- Oldest pending age.
- Affected business event groups.
- Recovery lag after the fix.
- Number of notifications requiring replay or reconciliation.

Do not report merely “500 SMTP errors” when that may be 500 attempts from a small set of notifications retried repeatedly.

## 33. Runbook when timeouts increase

Timeouts correlate strongly with network infrastructure and server response times.

### Step 1: Identify timeout type

~~~text
DNS lookup timed out?
     |
TCP connect timed out?
     |
Read timeout waiting for greeting?
     |
Read timeout waiting for SMTP AUTH?
     |
Read timeout waiting for final DATA reply?
     |
Write timeout transmitting payload?
~~~

Not every library exposes full phase details. When evidence is missing, record **unknown phase** and investigate via traces/provider logs rather than guessing.

### Step 2: Inspect the system

- DNS on the exact VM/container/pod running the application.
- TCP connectivity to the exact SMTP `host:port`.
- Firewalls, cloud egress, NAT, proxies, and service meshes.
- STARTTLS on port 587 or implicit TLS on port 465 per config.
- SMTP response times and provider quotas.
- Attachment sizes, concurrent connections, and thread/executor saturation.

### Step 3: Evaluate retry safety

**Connect timeouts before an SMTP session** are usually safe to retry if transient.

**Timeouts after transmitting `DATA` without a final reply** can mean the server accepted the email while the response was lost. Treat this as **UNKNOWN** unless clear rejection evidence exists.

For `UNKNOWN`:

- Look up provider message IDs or searchable traces.
- Reconcile before resending if the provider supports status lookups.
- Note duplicate risk if a replay is unavoidable.
- Use stable event IDs / notification keys to avoid creating duplicate outbox records.

### Step 4: Tune configuration

Common properties:

~~~properties
mail.smtp.connectiontimeout=5000
mail.smtp.timeout=10000
mail.smtp.writetimeout=10000
~~~

Units are **milliseconds**. Increasing timeouts makes sense only after proving current limits are too tight for normal latency; it will not fix broken DNS, blocked ports, or invalid certificates.

### Step 5: Confirm recovery

Monitor:

- Timeout ratio and absolute timeout count.
- p95 SMTP submission duration.
- Accepted/unknown rates.
- Outbox oldest age.
- `UNKNOWN`/potential duplicates needing reconciliation.

Never declare the incident resolved just because timeouts dropped while notifications remain stuck in the queue.

## 34. Runbook when bounces increase

Rising bounces may be a deliverability or recipient-data issue rather than a `JavaMailSender` bug.

### Step 1: Verify the source

- Did bounce events arrive from a verified ESP/DSN source?
- Are webhook replays/duplicates increasing?
- Are provider events and notifications properly deduplicated?
- Did bounce-ratio calculations or cohort definitions change?
- Is there new webhook lag or a backlog in the event inbox?

### Step 2: Classify

- Hard bounce or soft bounce?
- Concentrated on one recipient domain, provider, or stream?
- Which SMTP enhanced status codes appear most often?
- Is it tied to sender reputation, SPF/DKIM/DMARC, or policy rejections?
- Was a new campaign launched or an unverified list imported?

### Step 3: Check domain authentication

These changes can trigger bounces or policy rejections:

- `From` header switched to an unverified domain.
- Envelope sender / `Return-Path` rewritten by the ESP.
- SPF record no longer authorizes the sending IP/provider.
- Invalid DKIM signature or misaligned signing domain.
- DMARC policy or alignment changes.

**Never conclude every bounce is a bad recipient address** when the root cause is domain authentication or sender policy.

### Step 4: Choose mitigations

- Verified hard bounces: suppress addresses per policy and require re-verification upon update.
- Soft bounces: slow down, apply backoff, or let the provider retry.
- Sender reputation/authentication errors: fix domain config or content—do not wipe out the recipient list.
- New campaign causing a spike: pause the campaign per procedure if needed, audit consent and list quality.
- Spoofed webhooks: block and investigate; never update suppressions from untrusted data.

### Step 5: Measure impact

Compute ratios over matured cohorts and check:

- Unique bounced notification-recipients.
- Breakdown of hard/soft/policy bounces.
- Corresponding send volume.
- Suppressed recipients.
- Impact on critical transactional notifications.

If the provider has not finished emitting delivery feedback, report confidence levels and observation lag instead of jumping to premature final conclusions.

## 35. Composite alerting: view one incident across multiple signals

Do not investigate charts in isolation when they reflect the same underlying cause.

### Scenario A: SMTP provider outage

~~~text
09:00  SMTP connect timeouts begin rising
09:03  Submission failed/unknown ratio rises
09:05  Workers retry with backoff
09:10  Outbox pending/retry counts climb
09:15  Oldest due age climbs
~~~

Early signals are **timeouts** and **submission ratios**. Backlog appears later as a downstream symptom. Alerting only on bounces would see nothing because emails never reached the ESP.

Appropriate response:

- Verify SMTP `host:port` reachability from the live environment.
- Check provider status.
- Throttle retries to prevent a retry storm.
- Watch the age of critical notifications.
- Recover and reconcile once the provider stabilizes.

### Scenario B: Invalid customer email list

~~~text
SMTP submissions: accepted normally
SMTP latency: normal
Bounce events: rising
Hard bounce ratio: rising
Outbox: no backlog
~~~

Do not increase SMTP timeouts or scale workers here. Inspect recipient sources, list imports, validation, and suppression.

### Scenario C: Broken domain authentication after deployment

~~~text
Submission: may still be accepted by the ESP
Delivery: receiver policy rejections rise
Bounces: rising across multiple receiving domains
SPF/DKIM/DMARC: starting to fail
~~~

Check DNS changes, signing domains, `From` headers, `MAIL FROM`, and ESP configuration. Do not conclude customers suddenly started mistyping their emails en masse.

### Scenario D: Webhook outage

~~~text
SMTP submissions: normal
Provider dashboard: shows deliveries/bounces
Application delivery events: drop to 0
Delivery inbox backlog / 5xx: rising
~~~

This is an observability/delivery-ingestion pipeline failure, not proof of zero bounces. If webhooks were lost, reconcile via provider APIs/exports after recovery.

## 36. Alertmanager: routing, grouping, and runbooks

An alert helps only if it reaches the right responder with sufficient context.

Conceptual routing example:

~~~yaml
route:
  receiver: mail-platform-oncall
  group_by:
    - alertname
    - provider
    - stream
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - matchers:
        - severity="critical"
      receiver: mail-critical-oncall

receivers:
  - name: mail-platform-oncall
  - name: mail-critical-oncall
~~~

This is an **illustrative structure**; receivers must be configured with real notification channels such as pagers, email, or incident management tools. Never use alert emails sent through **the exact failing SMTP provider** as your sole alerting path. If the mail platform goes down, alert notifications will not arrive either.

An alert should include:

- Service, stream, and provider names.
- Error category or normalized reason.
- Evaluation window and threshold conditions.
- Affected attempts/notifications count.
- Dashboard and runbook links.
- Owning team.
- How to verify recovery.

Never put customer addresses, OTPs, email contents, or credentials into alert annotations to avoid leaking data to third-party alerting tools.

### Grouping must preserve key context

Grouping all alerts by a single `service` label blends an isolated provider issue with unrelated alerts. Grouping per instance/container floods responders with dozens of alerts for one incident. Prefer **service + provider + stream + incident type** where appropriate.

## 37. Testing instrumentation and alerting rules

To catch measurement bugs before production, test across three layers.

### A. Unit tests with a test MeterRegistry

With Micrometer's **SimpleMeterRegistry**, verify:

- An accepted submission increments `result=accepted` once.
- An SMTP failure increments `result=failed` with a normalized `category`.
- An uncertain result increments `result=unknown` without also incrementing `accepted`.
- Timers record positive durations.
- No labels are created from email addresses, exception messages, or notification IDs.

Example:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class MailSubmissionMetricsTest {

    @Test
    void recordsAcceptedAttempt() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        MailSubmissionMetrics metrics =
                new MailSubmissionMetrics(registry);

        metrics.record(
                "primary-smtp",
                "transactional",
                "accepted",
                "none",
                1_000_000L
        );

        double total = registry.get("mail.submissions")
                .tag("provider", "primary-smtp")
                .tag("stream", "transactional")
                .tag("result", "accepted")
                .tag("category", "none")
                .counter()
                .count();

        assertEquals(1.0, total);
    }
}
~~~

This tests that the logical metric was recorded. It does not test the Prometheus registry exporter, so also check scrape format at the integration layer if alert rules reference normalized metric names.

### B. Testing SMTP errors and callbacks/webhooks

- SMTP sandbox explicitly rejects with 4xx.
- SMTP sandbox rejects with 5xx.
- Server hangs on connect or while awaiting reply.
- Failure after `DATA` leads to **UNKNOWN** instead of blind retry.
- Valid bounce webhook transitions the right notification.
- Duplicate delivery of the same provider event yields only one valid event.
- Spoofed webhook is rejected and does not alter suppressions.
- Out-of-order delivered/deferred/bounced events are handled per state-machine contract.

### C. Testing alert rules

Prometheus includes **promtool** for linting syntax and unit-testing alert rules. Use synthetic time-series tests to verify:

- 2/4 failed attempts do not fire below minimum sample floor.
- Sustained 10/100 failed attempts above threshold fire a warning.
- 0 attempts do not produce divide-by-zero / infinite ratios.
- Counter resets on restarts do not create fake error spikes.
- Rising timeouts alert specifically by timeout category.
- Bounce arrival proxy is not misinterpreted as a cohort ratio when feedback lags.
- Worker-down / backlog alerts still fire when submission metrics stop.

Build these scenarios into your test suite. Do not rely on a few manual dashboard queries in place of automated rule tests in your deployment pipeline.

## 38. Worked calculation for an operational window

Suppose a transactional stream has the following in 10 minutes:

| Outcome | Attempts |
|---|---:|
| Accepted | 940 |
| Failed due to SMTP 4xx | 25 |
| Failed due to auth | 5 |
| Failed due to preparation errors in a separate pipeline metric | 10 |
| Unknown due to timeout after DATA | 20 |

Total rows in the table equal **1,000 attempts/pipeline operations**, yet note that the **10 preparation errors** occurred before SMTP submission. If **mail.submissions** counts only `JavaMailSender.send(...)` calls as in the wrapper above, the actual denominator is **990 SMTP attempts**, not 1,000.

For the **mail.submissions** metric itself:

~~~text
accepted      = 940
failed SMTP   = 25 + 5 = 30
unknown       = 20
total SMTP    = 990

confirmed failure rate = 30 / 990 ≈ 3.03%
unhealthy rate         = 50 / 990 ≈ 5.05%
unknown rate           = 20 / 990 ≈ 2.02%
~~~

With an alert for **unhealthy rate > 5%** and minimum sample 100, the condition can trigger depending on exact series/window and `for` duration. Preparation errors need a **separate pipeline preparation metric**, or an explicit redefinition if measuring all operations from rendering onward.

This example shows that **defining the denominator is part of operational accuracy**. Adding pre-SMTP failures to the numerator without including them consistently in the denominator produces wrong ratios.

### Bounces arriving later

If 28 notification-recipients from this batch are reported bounced by the provider 2 hours later, do not add 28 to SMTP failed attempts. Record them under **delivery status/cohort**, where they belong.

## 39. Data security and dashboard access controls

Email operational telemetry can inadvertently leak personal data:

- `To`/`Cc`/`Bcc` headers.
- `Message-ID` or provider message IDs linkable to recipients.
- Subjects containing order IDs or transaction details.
- SMTP replies containing recipient addresses.
- Bounce/DSN payloads containing excerpts of the original email.
- Webhook events carrying emails, names, or private metadata.

Principles to enforce:

1. **Metric labels:** use only finite dimensions such as `provider`, `stream`, `category`.
2. **Structured logs:** use protected notification/trace IDs; avoid bodies and credentials.
3. **Protect metrics endpoints:** restrict network access and authorization.
4. **Protect dashboards:** scope access by environment/tenant if needed.
5. **Never place sensitive data in alert annotations.**
6. **Retention:** enforce retention limits on delivery events and logs per business/legal rules.
7. **Webhooks:** verify signatures, prevent replays, and cap request sizes.
8. **Suppression:** update only from verified events and approved rules.
9. **SMTP debug:** avoid broad protocol tracing in production.
10. **Incident exports:** share aggregate numbers, not raw EML/DSN dumps by default.

### What should be logged on failure?

Example controlled log:

~~~text
notificationId=...
attemptId=...
provider=primary-smtp
stream=transactional
result=unknown
category=read_timeout
phase=final_reply
elapsedMs=12000
~~~

Never log email content, SMTP credentials, or unnecessary identifying data.

## 40. Common misconceptions

| Misconception | Correct Understanding |
|---|---|
| “`send()` succeeded means the customer got the mail” | Only proves submission was accepted at the observed hop |
| “No `MailException` means 0% bounce rate” | Bounces arrive asynchronously |
| “Every timeout is safe to retry” | Data after `DATA` may have been accepted; use `UNKNOWN`/reconcile |
| “Attempt count equals affected customers” | Retries create multiple attempts per notification |
| “When errors rise, just raise timeouts” | Errors may stem from DNS, TLS, auth, or provider policy |
| “Bounces divided by submissions in the same 10m is always accurate” | Feedback lags; cohorts are the proper measure |
| “One bounce webhook equals one new bounced notification” | Providers can retry or duplicate events |
| “Every 5xx means nonexistent recipient” | Can reflect sender policy, size, auth, or reputation |
| “Zero events means healthy” | Workers, collectors, or webhooks may be down |
| “50% error rate is always worse than 5%” | Must check denominator, SLO, and impacted users |
| “One `email_failed_total` metric is enough” | Preparation, submission, and delivery are distinct stages |
| “Metrics counters are an exact audit ledger” | Counters can drop on crash/restart and lack DB transactions |
| “On bounce, auto-suppress the whole domain” | Must classify cause and recipient scope |
| “Putting exception messages in metric labels helps debug” | Explodes cardinality and leaks data |
| “Alerts must go through email to match the domain” | Need an independent alert path when SMTP fails |

## 41. Spring Mail monitoring rollout checklist

To build a complete alerting setup, follow this rollout order:

1. **Choose counting units:** SMTP attempts, notification-recipients, provider events, or unique bounces.
2. **Separate submission and delivery:** never merge `ACCEPTED` with `DELIVERED`.
3. **Define results and categories:** `accepted`, `failed`, `unknown` plus normalized cause categories.
4. **Attach bounded provider/stream tags:** never use emails or IDs as metric labels.
5. **Add Micrometer and Actuator:** instrument counters, timers, and gauges.
6. **Verify Prometheus scrapes:** confirm actual exported series names and labels.
7. **Define windows and thresholds:** rates and minimum sample floors suited to traffic.
8. **Configure failure/timeout alerts:** split DNS, TCP, TLS, auth, SMTP, and send phase.
9. **Monitor outbox backlog:** oldest due age and worker liveness.
10. **Ingest delivery events:** verify webhooks/DSNs, persist durably and idempotently.
11. **Measure bounce arrival and mature cohorts separately:** never treat same-window ratios as absolute truth.
12. **Define SLOs:** submission latency, queue age, or delivery feedback matching real ownership.
13. **Configure Alertmanager:** group and route to owners with runbooks.
14. **Test rules:** low volume, counter resets, scrape loss, lag, and duplicate webhooks.
15. **Protect data:** keep bodies, credentials, and PII out of logs and labels.
16. **Run incident drills:** provider outage, read timeouts, hard bounce surge, webhook outage.
17. **Tune post-rollout:** adjust thresholds to cut false positives without masking real incidents.

## 42. Key takeaways

Email monitoring in Spring Framework Mail must watch **all three signals**: error rates at SMTP submission, timeouts/uncertain outcomes, and bounces occurring after server acceptance. Each signal requires the right **denominator, time window, and data source**.

With **JavaMailSender**, use **Micrometer** to emit counters by **accepted/failed/unknown**, measure latency with Timers, and track retries/outboxes with Gauges. With Spring Boot Actuator and Prometheus, build alerts on rising ratios **gated by minimum samples**, p95 latency, liveness, and backlogs.

For bounces, ingest **DSNs or provider webhooks** securely, deduplicate events, and update state per notification-recipient. Raw bounce arrivals in a short window are merely a spike signal; to assess deliverability quality, compute **ratios on cohorts that have had sufficient time to receive feedback**.

When an alert fires, classify the error before acting: **DNS, TCP, TLS, AUTH, SMTP 4xx/5xx, timeout after DATA, hard/soft bounce, or webhook pipeline failure**. Retry with backoff only when appropriate; reconcile `UNKNOWN` outcomes to reduce duplicate sends.

**A good alerting system does not merely say “emails are failing”; it pinpoints which stage is failing, the scale of impact, how certain the evidence is, and what the safest next action is.**





