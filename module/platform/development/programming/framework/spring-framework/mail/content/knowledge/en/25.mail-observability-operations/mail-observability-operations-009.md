# Dashboards by sender, tenant, and email type

In a system using **Spring Framework Mail**, calling `JavaMailSender.send(...)` is only one part of the email lifecycle. The application may create a mail job, store it in an outbox, retry after SMTP errors, and receive delivery/bounce events from the provider. When there are multiple sending accounts, multiple organizational customers (*tenants*), and multiple notification types, a dashboard showing only "how many emails were sent" is not enough to operate the system.

For example, a SaaS platform uses three senders:

~~~text
tx-primary        -> OTP, password reset, order confirmation, invoice
tx-backup         -> backup for transactional notifications
marketing-primary -> newsletters and promotional campaigns
~~~

If OTPs slow down, operators need to identify **which sender is failing, which tenant is affected, and which email type needs priority**. A multi-dimensional dashboard helps separate an SMTP authentication failure from a tenant hitting quota, a backed-up worker queue, or a rate-limited marketing campaign.

Three core questions:

1. **Sender:** which sending identity or infrastructure has an issue?
2. **Tenant:** which organizational customer is impacted and to what extent?
3. **Email type:** which use case is affected—OTP, invoice, order confirmation, or newsletter?

**Key principle:** distinguish **logical jobs**, **SMTP/API attempts**, **accepted submissions**, and **final delivery**. They are not the same unit of measurement and must not be collapsed into a single "email success rate."

## 1. Why a multi-dimensional dashboard is needed

Suppose the entire system has 4,200 attempts in 5 minutes, with 200 errors:

~~~text
Total:
  Attempts:   4,200
  Exceptions:   200

By sender:
  tx-primary:         200 errors / 200 attempts
  marketing-primary:    0 errors / 4,000 attempts
~~~

The system-wide exception rate is around 4.8%, yet **every email from the transactional sender failed**. An aggregate number can hide a critical outage behind high marketing volume.

The dashboard should support all three perspectives:

| Perspective | Question | Actions supported |
| --- | --- | --- |
| By sender | Does `tx-primary` have a credentials error? | Check auth, TLS, provider, and failover |
| By tenant | Is Tenant A the only tenant blocked? | Check quota, custom config, From permissions |
| By email type | Is OTP slow while newsletters run normally? | Prioritize workers, queues, SLOs |

An investigation flow:

~~~text
Overview
  -> Sender health: tx-primary
       -> Mail type: OTP
            -> Tenant impact: tenant-a
                 -> Job detail: job-752 / attempt-2
~~~

In practice, **do not put all three dimensions into every time series without controlling cardinality**. Sender profile and mail type can be low-cardinality tags; tenant ID often has very high cardinality and is better suited for database/analytics drill-down.

## 2. Defining sender accurately

The word "sender" has several meanings in Spring Mail:

| Identity | Example | Role |
| --- | --- | --- |
| `From` header | `orders@notify.example.com` | Address visible to recipients |
| Sender profile | `tx-primary` | Stable sending configuration in the application |
| SMTP auth identity | `smtp-transactional-account` | Credential/mailbox used for authentication |
| SMTP host | `smtp.vendor.example` | Server accepting connections |
| DKIM domain | `notify.example.com` | Domain signing the email |
| Provider/stream | `provider-a/transactional` | Infrastructure or sending stream |

Choose **`sender_profile`** as the primary operational dimension:

~~~text
sender_profile = tx-primary
  From aliases:
    orders@notify.example.com
    security@notify.example.com
    billing@notify.example.com
  SMTP provider = provider-a
  Provider stream = transactional
~~~

One SMTP credential error can affect multiple From aliases under the same sender profile. If a dashboard only groups by individual From address, operators may miss the shared root cause.

### 2.1. Sender profiles must be stable

Name them by role:

~~~text
tx-primary
tx-backup
marketing-primary
~~~

Do not use hostnames with random pod numbers, passwords, tokens, personal email addresses, or deploy timestamps as sender profiles. When rotating providers or credentials, keep the application-level identity stable and record provider/version as separate metadata.

### 2.2. One job can be tried across multiple providers

Failover example:

~~~text
job-752 / messageKey=invoice:INV-123

attempt-1: sender=tx-primary, provider=provider-a, timeout
attempt-2: sender=tx-backup,  provider=provider-b, accepted
~~~

The dashboard needs to separate:

- **logical job:** a single send request;
- **per-attempt sender profile:** identifies the adapter/credential used;
- **per-attempt provider:** identifies which external system failed.

Do not treat two attempts as two new business emails. And if attempt 1 timed out after the provider may already have accepted the message, retrying via provider B still carries duplicate risk.

## 3. Tenant is an investigation dimension, not necessarily a metric label

A tenant represents an organization/customer in a multi-tenant application:

~~~text
tenantId: company-4821
tenantTier: enterprise
region: ap-southeast
senderProfile: tx-primary
~~~

In a SaaS with 10,000 tenants, putting `tenant_id` on every Counter/Timer can explode the number of series:

~~~text
sender × tenant × mail_type × result × provider × pod × histogram_bucket
~~~

For instance, 4 senders × 10,000 tenants × 10 email types × 5 statuses × 12 buckets creates 24 million potential combinations, before even counting provider and pod. Not every combination occurs, but this clearly signals cardinality cost risk.

### 3.1. Two data tiers

| Need | Suitable tool |
| --- | --- |
| Fast alerting by sender, stream, mail type | Low-cardinality Prometheus/Micrometer metrics |
| Error rate by tenant tier | Bounded `tenant_tier` metric label |
| List Top N affected tenants | SQL/analytics/event store |
| Find jobs for a specific tenant | Authorized DB query by `tenant_id` |
| Investigate a single message | Job timeline, attempt events, logs/traces |

For applications with a small fixed tenant list, a tenant label may be considered if cardinality is verified. For dynamic tenants, prefer **aggregated metrics + drill-down from job/event data**.

### 3.2. Do not use tenant name or recipient address as labels

Customer names can change, collide, and contain sensitive information. Recipient emails have very high cardinality and are personal data. Do not place those values in Prometheus labels or public dashboards.

Store an immutable tenant ID in the event store; detail screens can resolve the display name via an access-controlled service.

## 4. Standardizing email types

Do not use the subject as `mail_type`:

~~~text
OTP code 483921
OTP code 729104
Invoice INV-2026-000123
~~~

Subjects vary per email and easily contain sensitive data. Use a bounded taxonomy instead:

| Mail type | Stream | Characteristics |
| --- | --- | --- |
| `otp` | Transactional | Short TTL, latency-critical |
| `password_reset` | Transactional | Expiring link/token |
| `order_confirmation` | Transactional | Tied to order event |
| `invoice` | Transactional | May include PDF |
| `security_alert` | Transactional | Account alert |
| `newsletter` | Marketing | Campaign-based sending |
| `promotion` | Marketing | Consent/opt-out critical |
| `other` | Per policy | Should be reclassified once sufficient info exists |

### 4.1. Mail type differs from template and campaign

| Attribute | Cardinality | Metrics label? |
| --- | --- | --- |
| `mail_type` | Finite, stable | Usually yes |
| `stream` | Transactional/marketing | Usually yes |
| `sender_profile` | Configuration catalog | Usually yes |
| `tenant_tier` | Small number of plans | Possibly |
| `template_version` | Changes per release | Usually unnecessary |
| `campaign_id` | One value per campaign | Event/analytics |
| `subject` | Nearly unbounded | No |
| `message_key` | Unique per logical job | No |
| `recipient_address` | Nearly unbounded, PII | No |

One mail type can use different templates by tenant or language while remaining the same mail type. If a template version causes errors, use job logs/events to drill down rather than emitting separate series per version.

## 5. Understand the lifecycle before defining metrics

~~~mermaid
flowchart LR
    A["Business event"] --> B["Mail job created"]
    B --> C["Outbox/queue"]
    C --> D["Transport attempt"]
    D --> E{"SMTP/API response"}
    E -->|Accepted| F["SUBMITTED"]
    E -->|Error| G["Retry / Final / Unknown"]
    F --> H["Provider processing"]
    H --> I["DELIVERED"]
    H --> J["BOUNCED"]
    H --> K["COMPLAINT"]
    G --> D
~~~

| State/event | Meaning |
| --- | --- |
| `CREATED` | Application durably recorded the send request |
| `QUEUED` | Job waiting for processing |
| `ATTEMPT_STARTED` | Worker started a send attempt |
| `SUBMITTED` | SMTP/API reported accepting the message per contract |
| `SUBMISSION_EXCEPTION` | Transport threw an error; partial or full submission may be unknown |
| `RETRY_WAIT` | Scheduled for retry |
| `FAILED_FINAL` | No further retries per policy |
| `DELIVERED` | Provider reported delivery according to its definition |
| `BOUNCED` | Provider reported post-submission delivery failure |
| `COMPLAINT` | Recipient reported spam per provider feedback |

**`SUBMITTED` is not `DELIVERED`.** `JavaMailSender.send(...)` returning normally usually only means the SMTP submission step finished. The email can still bounce or land in a spam folder.

### 5.1. One job can have multiple attempts

~~~text
job-752
  attempt 1 -> SMTP 451
  attempt 2 -> SMTP timeout
  attempt 3 -> accepted
~~~

Result:

- logical jobs = 1;
- transport attempts = 3;
- failed attempts = 2;
- eventual submitted job = 1.

**Attempt success rate** and **eventual job success rate** differ. Using attempts as the denominator for transactional SLOs will misreport user impact on the dashboard.

### 5.2. Partial sends and unknown outcomes

When sending a `MimeMessage` with multiple To/Cc/Bcc recipients, Jakarta Mail may report partial failures: some recipients were accepted and some rejected. A `MailSendException` alone does not prove zero recipients received the submission.

A connection can also drop after `DATA` but before the final reply, leaving the result uncertain. Record `UNKNOWN` or an equivalent state. Do not automatically mark `NOT_SENT` just because an exception occurred.

If the product needs a per-recipient dashboard, job data must store **recipient-level outcomes**; a single message-level `sent` boolean is insufficient.

## 6. Metrics catalog for Spring Mail

Common Micrometer metric names and typical Prometheus exports:

| Micrometer Metric | Typical Prometheus Name | Type | Meaning |
| --- | --- | --- | --- |
| `mail.jobs.created` | `mail_jobs_created_total` | Counter | Logical jobs created |
| `mail.submission.attempts` | `mail_submission_attempts_total` | Counter | Transport attempts |
| `mail.submission.duration` | `mail_submission_duration_seconds_*` | Timer | Duration of a single SMTP/API call |
| `mail.retry.scheduled` | `mail_retry_scheduled_total` | Counter | Retries scheduled |
| `mail.jobs.terminal` | `mail_jobs_terminal_total` | Counter | Jobs reaching a terminal state |
| `mail.outbox.pending` | `mail_outbox_pending` | Gauge | Non-terminal jobs count |
| `mail.outbox.oldest.pending.age` | `mail_outbox_oldest_pending_age_seconds` | Gauge | Age of oldest pending job |
| `mail.delivery.events` | `mail_delivery_events_total` | Counter | Provider events processed |
| `mail.suppressed` | `mail_suppressed_total` | Counter | Jobs blocked by policy before sending |
| `mail.provider.throttled` | `mail_provider_throttled_total` | Counter | Provider rate-limits/deferrals |

Actual Prometheus names depend on the registry and naming conventions. Inspect the application's metrics endpoint instead of guessing exact exported names.

### 6.1. Choose bounded labels

~~~text
sender_profile = tx_primary | tx_backup | marketing_primary
stream         = transactional | marketing
mail_type      = otp | invoice | order_confirmation | newsletter | other
tenant_tier    = free | standard | enterprise | internal
provider       = provider_a | provider_b
result         = submitted | exception
error_class    = auth | network | timeout | policy | recipient | unknown
~~~

Not every metric needs every label. Adding dimensions is not free, especially on histograms with many buckets.

**Do not attach:**

~~~text
tenant_id = customer-4821              // high cardinality
message_key = order-confirmed:evt-123  // nearly unique
recipient = alice@example.net          // PII and high cardinality
subject = "Login code 483921"          // PII/secret and high cardinality
error_message = "550 bob@example.net" // unstable, contains PII
~~~

### 6.2. Counter, Gauge, and Timer

- Counter measures occurrences, monotonically increasing (attempts, retries, events).
- Gauge measures current state, can go up or down (queue depth, worker claims).
- Timer measures duration and can export histograms for p95/p99.

Do not use a Counter for pending queue depth; likewise, do not use a Gauge instead of total emails ever sent.

## 7. Telemetry collection architecture

~~~mermaid
flowchart TD
    A["Business services"] --> B["Outbox / job store"]
    B --> C["Mail worker / JavaMailSender"]
    C --> D["SMTP/API provider"]
    D --> E["Provider webhook"]
    A --> F["Micrometer"]
    C --> F
    E --> F
    F --> G["Prometheus / metrics backend"]
    G --> H["Grafana dashboard + alerts"]
    B --> I["Job/attempt event store"]
    C --> I
    E --> I
    I --> J["Tenant drill-down / analytics"]
    J --> H
~~~

There are two main data streams:

1. **Aggregated metrics:** fast, bounded labels, used for health, alerts, and SLO trends.
2. **Event/job store:** granular to tenant, message, attempt, and timestamp; used for investigation, reporting, and role-based audits.

Logs/traces add correlation context when needed. Do not use trace counts as total email counts because tracing systems may sample.

### 7.1. Instrument at the right points

| Event | Good recording point | What to avoid |
| --- | --- | --- |
| Job created | After outbox/job commit | Counting before transaction rollback |
| Attempt started | Worker begins sending | Counting idle queued jobs |
| Submission result | SMTP/API adapter | Renaming to delivered |
| Retry scheduled | After retry schedule is persisted | Incrementing multiple times on tx retry |
| Pending gauge | Current DB/queue state | Summing identical snapshots across all replicas |
| Delivery event | After webhook verification/dedup | Double-counting duplicate webhooks |
| Suppression | Policy layer | Treating suppression as a transport error |

In-memory counters do not roll back with the database. If you need **exact counts of unique committed jobs**, query durable storage or deduplicated events; in-process metrics are better suited for operational monitoring than strict accounting.

## 8. Using Micrometer in Spring Boot

With Spring Boot Actuator and the Prometheus registry:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Configuration example:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  metrics:
    tags:
      application: mail-platform
~~~

The `/actuator/prometheus` endpoint should not be exposed to the open Internet. Restrict access and apply TLS/network policies/authorization per infrastructure standards.

### 8.1. Use enums to bound cardinality

~~~java
public enum SenderProfile {
    TX_PRIMARY,
    TX_BACKUP,
    MARKETING_PRIMARY
}

public enum TenantTier {
    FREE, STANDARD, ENTERPRISE, INTERNAL
}

public enum MailType {
    OTP, PASSWORD_RESET, ORDER_CONFIRMATION,
    INVOICE, SECURITY_ALERT, NEWSLETTER, PROMOTION, OTHER
}
~~~

A profile ID is distinct from the physical sender address. These enums are code-managed; never create labels directly from user input.

### 8.2. Recording metrics with Counter and Timer

~~~java
package com.example.mail.metrics;

import java.time.Duration;
import java.util.Locale;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class MailAttemptMetrics {
    private final MeterRegistry registry;

    public MailAttemptMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void record(
            SenderProfile sender,
            TenantTier tier,
            MailType type,
            boolean transportReturnedNormally,
            Duration elapsed) {

        Tags base = Tags.of(
                "sender_profile", tag(sender),
                "tenant_tier", tag(tier),
                "mail_type", tag(type));

        String result = transportReturnedNormally
                ? "submitted" : "exception";

        Counter.builder("mail.submission.attempts")
                .tags(base)
                .tag("result", result)
                .description("SMTP/API submission attempts")
                .register(registry)
                .increment();

        Timer.builder("mail.submission.duration")
                .tags(base)
                .description("Transport attempt duration")
                .publishPercentileHistogram()
                .register(registry)
                .record(elapsed);
    }

    private static String tag(Enum<?> value) {
        return value.name().toLowerCase(Locale.ROOT);
    }
}
~~~

When exported to Prometheus, `mail.submission.attempts` typically becomes `mail_submission_attempts_total`. `publishPercentileHistogram()` can generate `_bucket` series for p95 while multiplying series count; avoid enabling histograms with unbounded tags.

### 8.3. Wrapping JavaMailSender at the transport boundary

~~~java
import jakarta.mail.internet.MimeMessage;
import java.time.Duration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;

@Component
public class InstrumentedSmtpAdapter {
    private final JavaMailSender sender;
    private final MailAttemptMetrics metrics;

    public InstrumentedSmtpAdapter(
            JavaMailSender sender,
            MailAttemptMetrics metrics) {
        this.sender = sender;
        this.metrics = metrics;
    }

    public void submit(
            MimeMessage message,
            SenderProfile profile,
            TenantTier tier,
            MailType type) {

        long started = System.nanoTime();
        boolean returnedNormally = false;
        try {
            sender.send(message);
            returnedNormally = true;
        } finally {
            long nanos = System.nanoTime() - started;
            metrics.record(
                    profile,
                    tier,
                    type,
                    returnedNormally,
                    Duration.ofNanos(Math.max(0L, nanos)));
        }
    }
}
~~~

Key points:

- Each `submit(...)` call is **one attempt**.
- `submitted` only indicates that the transport call returned normally.
- `exception` does not prove no recipient received the message; partial/unknown outcomes require deeper analysis.
- `finally` ensures duration is recorded even on failure; the exception still propagates to retry orchestration.
- This snippet does not persist job state or solve outbox/idempotency; those are separate responsibilities.

If multiple `JavaMailSender` beans exist, inject the right sender/adapter per profile using `@Qualifier` or a router. Do not allow external clients to assign arbitrary profiles and distort telemetry.

### 8.4. Do not count jobs created before commit

Suppose a service does:

~~~text
BEGIN DB transaction
  UPDATE order
  INSERT mail_outbox
  Increment jobs_created_total
ROLLBACK
~~~

The counter incremented, yet the job does not exist. Therefore, when exact counts of durable logical jobs are needed, query committed DB/event data or emit events post-commit under a clear contract. Do not treat in-memory metrics as an exactly-once accounting ledger.

## 9. Backlog gauges and multiple replicas

An operational dashboard typically needs:

~~~text
Pending: 720 jobs
Retry wait: 64 jobs
Oldest eligible pending: 82 seconds
Active worker claims: 24
~~~

PostgreSQL query example against the outbox table:

~~~sql
SELECT
    sender_profile,
    mail_type,
    COUNT(*) FILTER (
        WHERE status IN ('PENDING', 'RETRY_WAIT')
    ) AS pending_jobs,
    MIN(created_at) FILTER (
        WHERE status IN ('PENDING', 'RETRY_WAIT')
    ) AS oldest_created_at
FROM mail_outbox
GROUP BY sender_profile, mail_type;
~~~

This is an aggregation example, not a built-in Spring Mail method. If no pending jobs exist, the oldest timestamp is `NULL`. When exporting an age metric, you can compute:

~~~text
age_seconds = now - oldest_created_at
~~~

while handling empty results and using consistent time zones.

### 9.1. Do not triple-count the same database snapshot

If three pods query the same shared outbox:

~~~text
mail_outbox_pending{instance="pod-a"} 720
mail_outbox_pending{instance="pod-b"} 720
mail_outbox_pending{instance="pod-c"} 720
~~~

`sum(mail_outbox_pending)` returns 2,160 instead of 720.

Solutions:

- designate a single exporter responsible for measuring global backlog;
- or have each exporter measure **disjoint** shards/partitions before summing;
- if replicas genuinely export the same global snapshot, `max` can work temporarily while accounting for lag/staleness;
- better yet, define one explicit owner for global metrics.

### 9.2. "Oldest pending" differs from "Overdue for retry"

A job created 2 hours ago whose `next_attempt_at` is in the future may **not be overdue**. Distinguish:

- age since `created_at`;
- age since `next_attempt_at` passed without a worker claiming the job;
- time stuck in `PROCESSING` or with an expired lease.

For "stalled worker" alerts, **eligible-but-unclaimed age** usually reflects trouble better than total age across all jobs waiting in backoff.

## 10. Prometheus queries by sender and email type

These examples assume metrics/tags exported with the names from section 6.

### 10.1. Submitted throughput by sender

~~~promql
sum by (sender_profile) (
  rate(mail_submission_attempts_total{result="submitted"}[5m])
)
~~~

The result is **submitted attempts/second**, not unique delivered emails/second.

### 10.2. Submitted attempts over one hour by email type

~~~promql
sum by (mail_type) (
  increase(mail_submission_attempts_total{result="submitted"}[1h])
)
~~~

`rate` suits measuring speed, while `increase` estimates the total increment over a window. Both handle counter resets better than subtracting raw counter values at two arbitrary timestamps.

### 10.3. Exception rate by sender

~~~promql
sum by (sender_profile) (
  rate(mail_submission_attempts_total{result="exception"}[10m])
)
/
clamp_min(
  sum by (sender_profile) (
    rate(mail_submission_attempts_total[10m])
  ),
  0.001
)
~~~

This is the exception ratio **over attempts**. A zero denominator makes the ratio undefined; `clamp_min` prevents division by zero, though panels should still show **N/A** when sample volume is too small. Alerts need a minimum-attempts guard.

### 10.4. Sender × mail type heatmap

~~~promql
sum by (sender_profile, mail_type) (
  rate(mail_submission_attempts_total{result="exception"}[10m])
)
/
clamp_min(
  sum by (sender_profile, mail_type) (
    rate(mail_submission_attempts_total[10m])
  ),
  0.001
)
~~~

This feeds a heatmap or error-rate table for each sender/type pair. Cells with no attempts should show N/A rather than assuming 0% errors or 100% success.

### 10.5. p95 submission latency

If the Timer enables histograms:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, sender_profile) (
    rate(mail_submission_duration_seconds_bucket[10m])
  )
)
~~~

Histogram percentiles are bucket-based estimates. If the exporter emits no `_bucket` series, the query returns nothing; verify registry/exporter settings. Here p95 measures **SMTP/API attempt duration**, excluding queue wait time.

### 10.6. Do not use rate on backlog Gauges

~~~promql
mail_outbox_pending{stream="transactional"}
~~~

Gauges are read directly or aggregated over true shards. Calling `rate(...)` on a Gauge does not represent pending job counts.

## 11. Suggested dashboard layout

A dashboard should offer multiple levels:

### 11.1. Executive/operations overview

~~~text
EMAIL OPERATIONS — Last 1 hour
---------------------------------------------------------
Logical jobs created | SMTP attempts | Exception rate
Oldest eligible job  | p95 submit    | Provider throttles
---------------------------------------------------------
Submission throughput by stream / sender
Outbox depth + queue age
Error classes by provider
Recent deploy / credential rotation markers
~~~

Panels must clearly state units, time window, time zone, metric source, and update lag.

### 11.2. Sender health table

| Sender | Stream | Attempts/5 min | Exception rate | p95 submit | Pending |
| --- | --- | ---: | ---: | ---: | ---: |
| `tx-primary` | Transactional | 420 | 0.2% | 380 ms | 12 |
| `tx-backup` | Transactional | 0 | N/A | N/A | 0 |
| `marketing-primary` | Marketing | 2,900 | 3.1% | 1.4 s | 1,500 |

Figures are illustrative. Do not display "0% errors" for a sender with zero attempts; that means **no samples**, not proof of health.

### 11.3. Mail type view

| Mail type | Jobs created | Oldest eligible | Final failed | Priority focus |
| --- | ---: | ---: | ---: | --- |
| `otp` | 1,200 | 6 s | 2 | Submission before token expires |
| `order_confirmation` | 900 | 10 s | 5 | Alignment with order status |
| `invoice` | 500 | 20 s | 4 | Attachment prep and size limits |
| `newsletter` | 20,000 | 4 min | 70 | Complaints, deferrals, campaign pacing |

Values are illustrative. OTP and newsletter should not share one SLO just because both use SMTP.

### 11.4. Tenant impact view

Role-restricted page:

~~~text
Tenant: company-4821
Period: 24 hours

Jobs by type:
  OTP                 80
  Order confirmation 150
  Invoice             10
  Newsletter         500

Health:
  Retry wait           12
  Failed final          3
  Hard bounced          4

Recent jobs:
  jobId | type | sender | status | attempts | createdAt
~~~

Numbers are illustrative. With many tenants, show a Top N impacted table or search by tenant ID in analytics. Do not emit per-tenant metrics solely to render this view.

### 11.5. Job timeline

~~~text
job-752 / type=invoice / sender=tx-primary
10:00:00 CREATED
10:00:01 CLAIMED
10:00:02 ATTEMPT_STARTED #1
10:00:03 SMTP 451 / RETRY_WAIT
10:01:03 ATTEMPT_STARTED #2
10:01:04 SUBMITTED
10:01:08 DELIVERED (provider event)
~~~

This page can link to logs/traces by job ID and correlation ID, exposing only authorized metadata. Never expose OTPs, email bodies, or full recipient lists publicly.

## 12. Tenant drill-down via SQL

Prometheus shows the system has a problem; SQL/event storage identifies which tenants and jobs are impacted.

### 12.1. Minimal schema

~~~sql
CREATE TABLE mail_job (
    job_id         VARCHAR(64) PRIMARY KEY,
    tenant_id      VARCHAR(64) NOT NULL,
    sender_profile VARCHAR(80) NOT NULL,
    mail_type      VARCHAR(80) NOT NULL,
    stream         VARCHAR(30) NOT NULL,
    status         VARCHAR(30) NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    submitted_at   TIMESTAMP
);

CREATE TABLE mail_attempt (
    attempt_id   VARCHAR(64) PRIMARY KEY,
    job_id       VARCHAR(64) NOT NULL REFERENCES mail_job(job_id),
    provider     VARCHAR(80) NOT NULL,
    result       VARCHAR(30) NOT NULL,
    error_class  VARCHAR(50),
    started_at   TIMESTAMP NOT NULL,
    completed_at TIMESTAMP
);

CREATE TABLE mail_delivery_event (
    id                VARCHAR(64) PRIMARY KEY,
    job_id            VARCHAR(64) NOT NULL REFERENCES mail_job(job_id),
    provider          VARCHAR(80) NOT NULL,
    provider_event_id VARCHAR(150),
    event_type        VARCHAR(40) NOT NULL,
    occurred_at       TIMESTAMP,
    received_at       TIMESTAMP NOT NULL
);
~~~

This schema illustrates the model, not a complete production migration. Production needs indexes, UTC/timezone-aware timestamps, retention, properly scoped unique constraints on provider events, PII policies, and recipient-level rows when one message targets multiple recipients.

### 12.2. Top tenants by logical jobs

PostgreSQL example:

~~~sql
SELECT
    tenant_id,
    COUNT(*) AS created_jobs
FROM mail_job
WHERE created_at >= :from_time
  AND created_at < :to_time
GROUP BY tenant_id
ORDER BY created_jobs DESC
LIMIT 20;
~~~

This counts logical job rows, not attempts. Whether a logical job represents one message or one recipient must be defined in the application model.

### 12.3. Authorized detail query

~~~sql
SELECT
    job_id,
    sender_profile,
    mail_type,
    status,
    created_at,
    submitted_at
FROM mail_job
WHERE tenant_id = :authorized_tenant_id
  AND sender_profile = :sender_profile
  AND mail_type = :mail_type
  AND created_at >= :from_time
  AND created_at < :to_time
ORDER BY created_at DESC
LIMIT 100;
~~~

`authorized_tenant_id` must be verified on the backend against user/role permissions, never trusted from a UI dropdown. Use prepared parameters to prevent SQL injection.

### 12.4. Status snapshot by cohort

~~~sql
SELECT
    tenant_id,
    sender_profile,
    mail_type,
    COUNT(*) AS jobs_created,
    COUNT(*) FILTER (
        WHERE status = 'SUBMITTED'
    ) AS jobs_submitted,
    COUNT(*) FILTER (
        WHERE status = 'FAILED_FINAL'
    ) AS jobs_failed_final,
    COUNT(*) FILTER (
        WHERE status IN ('PENDING','PROCESSING','RETRY_WAIT')
    ) AS jobs_nonterminal
FROM mail_job
WHERE created_at >= :from_time
  AND created_at < :to_time
GROUP BY tenant_id, sender_profile, mail_type;
~~~

This is a **creation-time cohort** showing status **at query time**. It is not "emails submitted during the hour," because a job created earlier might submit now. To count submissions by submission time, query `submitted_at` or the attempt/event table for the corresponding window.

### 12.5. Backlog must not drop old jobs

If a backlog query filters `created_at` to only the last 24 hours, a job stuck for 3 days disappears from the dashboard while still pending.

~~~sql
SELECT
    tenant_id,
    COUNT(*) AS pending_count,
    MIN(created_at) AS oldest_created_at
FROM mail_job
WHERE status IN ('PENDING','PROCESSING','RETRY_WAIT')
GROUP BY tenant_id;
~~~

Separate current backlog from historical cohort reports. With large tenant/job volumes, use materialized views or an analytics store instead of full-table scans on every dashboard refresh.

## 13. Delivery, bounces, and provider webhooks

A provider may send events after SMTP/API accepts the message:

~~~text
provider_message_id=provider-abc-123
event_type=DELIVERED
occurred_at=2026-11-12T09:00:15Z
~~~

Later events may include `BOUNCED`, `DEFERRED`, or `COMPLAINT`. The definition of "delivered" varies by provider and usually does not prove the recipient read the message.

### 13.1. Webhooks can duplicate, lag, and arrive out of order

~~~text
T1 Provider generates DELIVERED event
T2 Provider generates COMPLAINT event
T3 COMPLAINT webhook arrives first
T4 DELIVERED webhook arrives later
~~~

Therefore you need to:

- verify webhook signatures/authorization;
- correlate provider message ID with local job/attempt;
- deduplicate events by provider event ID or provider-defined identity;
- distinguish `occurred_at` from `received_at`;
- enforce explicit state transitions;
- store event history when auditing is required;
- detect when provider webhook delivery stops.

### 13.2. Event count differs from unique deliveries

One message can produce multiple deferred events, or a `DELIVERED` webhook may be retried. `mail_delivery_events_total{event_type="delivered"}` counts processed events under your instrumentation contract, not necessarily unique delivered emails unless deduplicated.

When calculating bounce/complaint rates, clarify:

- is the denominator unique submissions, unique recipient submissions, or jobs?
- are results grouped by send cohort or event receipt date?
- does the provider support complete reporting?
- are duplicates removed?

Do not compare provider A with full webhooks against provider B without tracking and conclude B has a 0% delivery rate.

### 13.3. Missing data must be shown explicitly

If webhooks are not configured:

~~~text
Delivery tracking: N/A
Reason: Provider events not configured
~~~

Never fill in "0 delivered" and treat it as a sending failure. Missing telemetry is an **observability coverage** gap, not proof that messages failed.

## 14. SLOs by email type and sender

An **SLI** is a service quality indicator. An **SLO** is the target set for that SLI over a time window.

Illustrative example targets:

| Subject | SLI | Illustrative SLO |
| --- | --- | --- |
| OTP | Ratio of logical jobs submitted within 30 seconds of creation | ≥ 99% / 30 days |
| Order confirmation | Job submitted within 2 minutes | ≥ 99.5% / 30 days |
| Invoice | Submitted within business window | Per contract |
| Newsletter | Campaign completed on schedule | Per deadline |
| Transactional sender | SMTP exception rate over attempts | Threshold set by ops team |

These numbers are not mandatory standards. An SLO must define:

- whether it starts at business event commit or job creation;
- whether it ends at submitted or provider delivered;
- whether multiple retries count once or multiple times;
- how suppressions and valid cancellations are treated;
- how missing provider events affect the denominator.

### 14.1. Separate the latency segments

~~~text
Business event committed
  | A. event -> job persisted
Mail job created
  | B. queue waiting time
Worker begins attempt
  | C. SMTP/API submission duration
SUBMITTED
  | D. delivery delay (if provider events exist)
DELIVERED
~~~

A very fast SMTP adapter cannot hide a queue backed up by 10 minutes. For OTPs, track **job creation -> submission**, not transport duration alone.

### 14.2. Do not substitute attempt success rate for job SLO

An OTP job taking 3 attempts and submitting after 8 seconds can still meet a 30-second SLO. Attempt success rate is 1/3, yet the logical job completed on time.

If an SLO measures **completion of send requests**, use logical jobs and deadlines as units—not raw attempts.

## 15. Context-aware alerting

### 15.1. Alert types

| Alert | Initial diagnosis | Action |
| --- | --- | --- |
| Authentication failures rising | Credential/OAuth/SMTP policy | Check auth and sender |
| Oldest eligible pending rising | Stalled worker/queue | Check claims, scheduler, backlog |
| OTP deadline misses | Critical notifications delayed | Escalate as incident |
| Provider throttling 4xx | Quota/rate limit | Slow down, check account usage |
| Marketing complaint spike | Bad campaign or list | Pause campaign, investigate |
| Provider event webhook stopped | Lost delivery visibility | Check webhook ingestion |
| Single tenant failing abnormally | Custom config/quota/sender policy | Drill down by tenant |
| Repeated failover | Unstable primary sender/provider | Investigate root cause, prevent duplicates |

### 15.2. Example alert rule

~~~yaml
groups:
  - name: mail-operations
    rules:
      - alert: TransactionalMailBacklogOld
        expr: mail_outbox_oldest_pending_age_seconds{stream="transactional"} > 120
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Transactional mail backlog is aging"
          description: "Check eligible jobs, workers, provider throttling."
~~~

The 120-second / 5-minute thresholds are illustrative; OTPs may need lower thresholds. Ensure the metric truly reflects **eligible pending jobs**, excluding jobs legitimately waiting in backoff so it does not fire false alarms.

### 15.3. Ratios need a volume guard

A sender with 1 attempt and 1 error has a 100% error rate. That does not prove a widespread outage.

An alert policy can require:

~~~text
error rate > threshold
AND attempts within 10m >= minimum sample count
AND condition persists for N minutes
~~~

Conversely, if business events keep creating jobs with zero attempts, the exception rate may be 0 or absent. Alert on **silent failure** using created jobs, pending depth, and oldest eligible age.

### 15.4. Never push PII into alerts

Alerts should contain sender profile, stream, type, region, job count, and dashboard links. Never embed OTPs, message bodies, raw recipient lists, SMTP passwords, bearer tokens, or full provider responses containing sensitive data.

## 16. Investigation runbook by sender, tenant, and mail type

Suppose `tx-primary` shows an increasing SMTP exception rate:

1. **Isolate sender:** only `tx-primary`, or `tx-backup` and marketing too?
2. **Isolate mail type:** OTP/password reset only, or all transactional types?
3. **Isolate tenant:** one tenant, one tier, or system-wide?
4. **Read error class:** auth, TLS, timeout, provider policy, recipient reject, or payload size?
5. **Correlate recent changes:** deployments, credential rotations, OAuth scopes, DNS, or queue settings?
6. **Inspect backlog:** pending/eligible age, active workers, retry schedule, quota.
7. **Check provider:** status page, throttling, account suspension, webhook data.
8. **Mitigate:** throttle marketing if sharing quota, fix configuration, fail over per tested runbook.
9. **Protect idempotency:** never retry blindly when submission outcome may already have succeeded.
10. **Verify recovery:** errors drop, backlog drains, logical jobs meet deadlines.

### 16.1. When only one tenant fails

Check:

- tenant-specific SMTP identity or `From`/Send-As permissions;
- tenant quota and provider quota;
- recipient list with high hard bounces;
- tenant-specific template rendering or attachment failures;
- suppression policy and consent;
- wrong sender-profile/tenant mapping.

Never blame the tenant solely because errors appear on one tenant; verify job/attempt evidence first.

### 16.2. When only marketing fails

Check campaign spikes, list hygiene, complaints, rate limits, deferrals, suppression, tracking domains, and the ESP marketing stream. You can pause campaigns while protecting transactional capacity. However, if both streams share one provider account quota, impact can still spill over to OTPs.

## 17. Pitfalls that break dashboards

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Counting retries as new mail jobs | Inflates email volume | Separate job ID from attempt ID |
| Treating `send` return as Inbox delivered | Overly optimistic reporting | Track provider delivery events separately |
| Assuming every exception reached zero recipients | Wrong for partial/unknown sends | Record recipient-level outcome/`UNKNOWN` |
| Counting duplicate webhooks | Double-counted deliveries | Idempotent event processing |
| Histograms labeled with `tenant_id` or `job_id` | Extreme cardinality/cost | Bounded labels + drill-down store |
| Summing pending across all DB-querying pods | Queue depth multiplied by replicas | Single exporter or disjoint shards |
| Omitting time zone/time window | Misleading "today" totals | Store UTC, label UI time zones clearly |
| Filtering backlog by `created_at` | Hides stuck old jobs | Query all non-terminal jobs |
| Comparing providers with/without webhooks | Skewed delivery rates | Show data coverage indicator |
| Incrementing Counter before DB commit | Counts rolled-back jobs | Measure post-commit or query DB |
| Mixing retry wait with overdue jobs | False backlog alerts | Track eligible backlog separately |
| Error-rate alert without sample guard | Pages on 1 tiny failure | Add volume + duration guard |
| Error-rate alert without silent-failure alert | Misses dead workers | Track created-vs-attempted and oldest age |
| Tenant filter missing backend authorization | Cross-tenant data leak | Enforce permissions at query/API layer |
| Putting full exception text into metrics | PII leak + high cardinality | Use error-class enum and controlled logs |

### 17.1. Counter resets and scrape gaps

Prometheus `rate`/`increase` handles counter resets across process restarts. However, prolonged scrape gaps or lost exporters still cause missing samples. Do not use in-memory Counters as an absolute billing/audit ledger.

### 17.2. Time zones and late-arriving data

A job created at 23:59 UTC may fall on the next day in a tenant's local time zone. Delivered events can arrive minutes or hours later. Dashboards must state clearly:

- whether grouping uses `occurred_at` or `received_at`;
- whether dates use UTC or tenant local time zone;
- that numbers may shift as late events arrive;
- whether a query shows a creation cohort or an observation window.

### 17.3. Sampled traces

Traces may capture only a fraction of requests. Use traces to inspect one mail job's path; never treat trace counts as total emails sent.

## 18. Multi-tenant dashboard security

A dashboard can inadvertently expose:

- which tenants are active;
- order/invoice volume;
- recipient email addresses;
- failure details containing personal data;
- provider details and sending-account permissions.

Illustrative access control:

| Group | Permissions |
| --- | --- |
| Internal on-call | View sender/stream and role-scoped drill-down |
| Support | Only assigned tenants |
| Tenant admin | Only their own tenant's data |
| Marketing team | Campaign/marketing data, no OTP inspection |
| Security team | Audits and sender authentication anomalies |

### 18.1. A UI dropdown is not authorization

If an API accepts `tenant_id` from the URL and queries freely, users can edit the ID to view other tenants. The backend must validate principal/role/tenant membership via row-level security or service-layer enforcement.

### 18.2. Privacy in metrics and logs

Never place:

- SMTP passwords/API keys/OAuth tokens;
- OTPs or reset tokens;
- message bodies/attachments;
- raw recipient addresses;
- arbitrary subjects;
- restricted tenant names;

into metric tags or alerts. Job IDs/correlation IDs may appear in access-controlled logs; reveal real recipients only on audited support views when required.

### 18.3. Retention and cost

Aggregated metrics can be kept long-term for trend analysis. Recipient-level event stores need appropriate retention, access controls, and deletion mechanisms. Never retain raw MIME or PDF attachments merely to power a dashboard.

## 19. Testing instrumentation

### 19.1. Unit testing with SimpleMeterRegistry

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.time.Duration;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class MailAttemptMetricsTest {

    @Test
    void recordsAttemptWithBoundedTags() {
        try (SimpleMeterRegistry registry =
                new SimpleMeterRegistry()) {
            MailAttemptMetrics metrics =
                    new MailAttemptMetrics(registry);

            metrics.record(
                    SenderProfile.TX_PRIMARY,
                    TenantTier.ENTERPRISE,
                    MailType.ORDER_CONFIRMATION,
                    true,
                    Duration.ofMillis(250));

            double count =
                    registry.get("mail.submission.attempts")
                            .tags(
                                    "sender_profile", "tx_primary",
                                    "tenant_tier", "enterprise",
                                    "mail_type", "order_confirmation",
                                    "result", "submitted")
                            .counter()
                            .count();

            assertEquals(1.0, count);
        }
    }
}
~~~

This test checks in-memory metrics only; no SMTP connection is needed. Also test:

- exceptions from `JavaMailSender.send(...)` increment `result=exception`;
- exceptions still propagate to callers rather than being swallowed;
- timers record duration even on failure;
- a second retry increments attempts without creating a new logical job;
- no dynamic tags outside the approved vocabulary exist.

### 19.2. Integration testing

Use GreenMail/Mailpit or a test SMTP server to:

1. Send a message to a real test server.
2. Verify attempt counters/timers.
3. Simulate submission failures and error classification.
4. Verify outbox job states and retries.
5. Ensure duplicate events do not increment logical jobs twice.
6. Clean up mailboxes/outbox so subsequent tests stay isolated.

A mock sender does not prove provider delivery. Provider webhooks need dedicated tests for duplicate event IDs, late/out-of-order events, and signature verification.

### 19.3. Verifying Prometheus/Grafana

- `/actuator/prometheus` exports exact metric names and is access-protected.
- Histogram buckets actually exist before querying `histogram_quantile`.
- `rate`/`increase` queries target Counters, while backlog panels query Gauges.
- Multiple pods do not inflate total pending counts.
- Zero-traffic senders show N/A where appropriate.
- Alerts include volume guards rather than paging on a single sample.
- Tenant drill-down enforces authorization.
- Dashboards clearly display time frame, time zone, source, and freshness.

## 20. End-to-end scenario: OTP failures after credential rotation

Suppose the application has:

~~~text
Sender profiles: tx-primary, tx-backup, marketing-primary
Mail types: otp, order_confirmation, invoice, newsletter
Tenants: company-a, company-b, ...
~~~

At an illustrative point in operations, the dashboard shows:

~~~text
Overall exception rate: 2.1%

By sender:
  tx-primary:         45% exception
  marketing-primary:  0.2% exception

By mail type:
  otp:                60% exception
  newsletter:          0.2% exception
~~~

These numbers are purely illustrative.

### 20.1. Investigation

1. Filter `sender=tx-primary`.
2. Notice `error_class=auth` rising.
3. Correlate with the "SMTP credentials rotated" marker near the error onset.
4. Check the OTP backlog and tenants with overdue pending jobs.
5. Inspect tokens/credentials, SMTP AUTH policy, and `From`/Send-As permissions.
6. If a tested backup sender with proper permissions exists, consider failing over per runbook.
7. Do not blindly resend all jobs in `unknown` status since the server may have received them.

### 20.2. Confirming recovery

Verify:

- exception rate returns to normal baseline;
- oldest eligible pending drops;
- OTP logical jobs reach `SUBMITTED` within deadline;
- final failures stop rising;
- attempts/job do not spike abnormally from retries;
- provider delivery events are monitored separately.

**With dashboards segmented by sender, tenant, and email type, operators pinpoint the exact failing component and affected user group**, instead of guessing from one system-wide ratio.

## 21. Implementation checklist

### Identity

- [ ] `sender_profile` is stable and contains no credentials.
- [ ] `mail_type` uses a finite catalog.
- [ ] Tenant ID is stored in the job/event store without creating unbounded metric cardinality.
- [ ] Provider/stream/tenant tier are attached appropriately.

### Semantics

- [ ] Logical jobs, attempts, submissions, and delivery events are separated.
- [ ] Unknown/partial states exist when SMTP outcomes are uncertain.
- [ ] Queue wait and SMTP submission duration are measured separately.
- [ ] Backlog gauges are not multiplied across replicas.
- [ ] Provider webhooks are authenticated and processed idempotently.
- [ ] Ratios specify clear denominators and time windows.

### Dashboards and operations

- [ ] Overview, sender health, mail type, and tenant drill-down views exist.
- [ ] Job timelines link through attempts and events.
- [ ] Priority SLOs/alerts exist for OTP and transactional mail.
- [ ] Alerts include volume guards and silent-failure detection.
- [ ] Runbooks exist for auth, quota, throttling, backlog, and failover.
- [ ] Panels with missing telemetry display N/A instead of fake 0%.

### Security and testing

- [ ] Metrics endpoints are not exposed publicly without controls.
- [ ] OTPs, raw bodies, secrets, and unnecessary PII are excluded from logs.
- [ ] Backend validates tenant query authorization.
- [ ] Unit tests cover metric names/tags and exception paths.
- [ ] Integration tests cover SMTP, outbox, webhooks, and cleanup.
- [ ] Metrics/events/logs retention matches operational requirements.

## 22. Key takeaways

- A Spring Framework Mail dashboard should slice by **sender**, **tenant**, and **email type** to isolate incidents rapidly.
- A sender profile is a configuration identity; do not confuse it with `From`, SMTP host, credentials, or DKIM domain.
- Mail type is a finite business taxonomy; never use dynamic subjects or campaign IDs as metric labels.
- Tenant ID is crucial for support yet explodes metric cardinality: use aggregated metrics plus authorized DB/analytics drill-downs.
- **Jobs, attempts, submissions, and deliveries** carry distinct semantics and must be counted separately.
- Micrometer Counters/Timers fit attempts and latency; Gauges fit backlogs; event stores hold tenant/job details.
- PromQL queries must account for resets, histograms, sample sizes, and duplicated gauges across replicas.
- Provider webhooks can repeat, lag, and arrive out of order; event counts do not automatically equal unique delivered messages.
- OTPs and newsletters differ in criticality, so their SLOs and alerts must differ too.
- Dashboards must connect to runbooks, tests, and authorization—not just look pretty.

An effective dashboard answers not merely "how many emails did we send today" but **which sender is failing, which tenants are impacted, which email types take priority, and where in the sending pipeline the evidence lies**. Combining cardinality-bounded metrics with granular job/event records lets you monitor, alert on, and investigate Spring Framework Mail accurately.

### References

- **Spring Framework Reference — Email:** `JavaMailSender`, `MimeMessageHelper`, and transport errors.
- **Spring Boot Reference — Production-ready Features / Actuator:** Metrics and endpoint configuration.
- **Micrometer Documentation:** Counter, Timer, Gauge, tags/cardinality, and histograms.
- **Prometheus Documentation:** Counter/Gauge, `rate`, `increase`, `histogram_quantile`, and alerting rules.
- **Grafana Documentation:** dashboard variables, panel queries, permissions, and alerting.
- **OpenTelemetry Documentation:** trace/metric/log correlation.
- **Jakarta Mail SMTP provider documentation:** submission, exceptions, and partial recipient sends.
- **RFC 5321 — Simple Mail Transfer Protocol:** SMTP transactions and acceptance.
- **Documentation for your email service provider:** delivery/bounce/complaint events, rate limits, and webhook contracts.
