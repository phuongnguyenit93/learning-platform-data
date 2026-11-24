# Inspecting a backed-up outbox

In an application using **Spring Framework Mail**, writing an email job to a **transactional outbox** decouples business transactions from SMTP operations. However, a committed outbox record **does not mean the email has been sent**. If workers stop, SMTP slows down, retries back up, or a queue stalls, records accumulate. Users may fail to receive order confirmations, receipts, or security alerts on time even though HTTP APIs still return success.

**Inspecting a backed-up outbox** is the observability and operational practice of answering: how many notifications are due but unprocessed, how long the oldest notification has waited, whether the queue is growing or draining, whether workers are actually delivering mail, and whether any jobs are stuck in an unknown outcome state.

This lesson builds mail outbox observability around **state, age, arrival/processing rates, leases, retries, and SMTP outcomes**, providing **PostgreSQL** and **Spring Boot/Micrometer** examples, dashboards, alerts, root-cause workflows, and duplicate-safe recovery. The tables, services, and metrics named here are **illustrative application designs**, not a built-in outbox feature created automatically by `JavaMailSender`.

> **Operational rule:** Never look only at the total outbox row count. Distinguish **not-yet-due jobs**, **due waiting jobs**, **in-flight jobs**, **failed jobs awaiting retry**, and **jobs whose SMTP acceptance is unknown**. Never clear a backlog by resetting all rows to `PENDING` and resending them.

## 1. Why monitor the outbox if you already have one?

A typical transactional mail flow:

~~~text
OrderService / AccountService
             |
             v
       BEGIN TRANSACTION
             |
        +----+----+
        |         |
        v         v
    Save Order   Insert MailOutbox(PENDING)
        |         |
        +----+----+
             |
             v
           COMMIT
             |
             v
       Mail dispatcher
             |
             v
      SMTP / mail provider
             |
       +-----+------+
       |            |
       v            v
    ACCEPTED       ERROR
                    |
               RETRY / UNKNOWN
~~~

The outbox guarantees that **the mail send intent is persisted alongside the business change**, provided the same database transaction is configured properly. After commit, everything depends on:

- Whether worker schedulers or consumers are running.
- Whether the database lets workers claim jobs correctly and fast enough.
- Whether the SMTP server responds and whether credentials/TLS are valid.
- Rate limits, connection pools, retry/backoff, and queue capacity.
- Whether state-transition logic records outcomes accurately.
- Whether jobs are stalled due to dead workers, expired leases, or unreconciled outcomes.

A system can persist outbox rows accurately while **stopping all outbound email for hours** if it lacks metrics and alerts.

### Backed up does not automatically mean failed

Suppose:

~~~text
12:00 Create renewal reminder email scheduled for 17:00
12:01 Outbox holds a PENDING record
12:05 Dashboard shows 1 unsent record
~~~

That record is **not stuck** because its scheduled time has not arrived. Conversely:

~~~text
12:00 Create login verification email for immediate delivery
12:01 Outbox status=PENDING, available_at=12:00
12:20 No worker has claimed it
~~~

That is a **due backlog** requiring investigation. Therefore, clearly define "due" and SLAs per mail purpose.

## 2. State model for observability

A mail outbox state machine can include:

| Status | Meaning | Operational action |
| --- | --- | --- |
| **PENDING** | Notification recorded, waiting for send time | Check schedule, workers, backlog |
| **RETRY_WAIT** | Previous attempt hit a retryable error; waiting in backoff | Inspect error reason, retry schedule, attempt count |
| **IN_FLIGHT** | Worker claimed the job and holds temporary processing rights | Track elapsed time, lease/heartbeat |
| **ACCEPTED** | SMTP/provider confirmed submission acceptance | Do not retry as backlog |
| **UNKNOWN** | Uncertain whether the server accepted the attempt | Reconcile; avoid blind resend |
| **SUPPRESSED** | Not sent due to opt-out/complaint/bounce or policy | Do not count as a retryable worker error |
| **PERMANENT_FAILED** | Error that cannot or must not be retried automatically | Route to data/config fix or ops handling |
| **CANCELLED** | Notification cancelled by business logic | Do not send |

State names are illustrative. A project might use **SENT** instead of **ACCEPTED**, **FAILED_RETRYABLE** instead of **RETRY_WAIT**, or store retries in a separate attempt table. What matters is consistent semantics: **ACCEPTED** here means transport/provider acceptance, **not proof of Inbox placement or user read**.

### State transition diagram

~~~text
PENDING --due/claim--> IN_FLIGHT
   ^                      |
   |                      +-- SMTP accepted ------------> ACCEPTED
   |                      |
   |                      +-- retryable error ----------> RETRY_WAIT
   |                      |                                  |
   |                      |                                  v
   |                      |                             retry time due
   |                      |                                  |
   |                      +-- permanent error ---------> PERMANENT_FAILED
   |                      |
   |                      +-- ambiguous / crash --------> UNKNOWN
   |
   +--- safe retry decision after reconciliation ------- UNKNOWN

PENDING / RETRY_WAIT --no longer eligible to send--> SUPPRESSED
PENDING / RETRY_WAIT --cancelled by business-------> CANCELLED
~~~

An email can be created immediately yet only become eligible to send later. Thus a `PENDING` row sitting in the table for hours is not necessarily delayed; compare against **`available_at`** or **`scheduled_at`**.

## 3. Precisely defining "outbox backlog"

Divide the queue into distinct buckets:

| Group | Reference condition | Why measure separately |
| --- | --- | --- |
| **Due backlog** | `PENDING`/`RETRY_WAIT` and `available_at` is due | Work that should be claimed but is still waiting |
| **Scheduled future** | `PENDING`/`RETRY_WAIT` with `available_at` in the future | Valid work not yet ready to send |
| **Active in-flight** | `IN_FLIGHT`, lease still valid | Work currently executing |
| **Expired in-flight** | `IN_FLIGHT`, `lease_until` passed | Possible dead worker or hung process |
| **Unknown outcomes** | `UNKNOWN` | Needs confirmation whether provider accepted |
| **Permanent failures** | `PERMANENT_FAILED` | Needs deliberate remediation, not auto-retry |
| **Terminal outcomes** | `ACCEPTED`/`SUPPRESSED`/`CANCELLED` | Not pending outbound backlog |

### Three distinct questions

1. **How many jobs are waiting?** Count jobs that are due.
2. **How long has the oldest job waited?** Measure age of due jobs and SLA breaches.
3. **Is processing keeping up with arrivals?** Compare incoming rate against successful/terminal processing rate.

A raw **`COUNT(*)`** on `mail_outbox` is misleading because it includes millions of historical `ACCEPTED` rows kept for audit. Similarly, **`COUNT(status=PENDING)`** can climb simply because future scheduled campaigns were enqueued early, not because workers failed.

### Distinguishing two age concepts

For a notification:

~~~text
created_at   = 08:00
available_at = 13:00
now          = 13:03
~~~

- **Age since creation:** 5 hours 3 minutes. Useful for total lag since the business event occurred.
- **Delay after eligible:** 3 minutes. Useful for seeing how long workers lagged after the job became due.

For immediate emails, these two values are close. For scheduled emails, using age since `created_at` as the primary backlog alert causes false alarms.

## 4. The most important metrics

<table>
  <tr><th>Metric</th><th>Question answered</th><th>Action when abnormal</th></tr>
  <tr><td>Due backlog count</td><td>How many jobs are past their eligible time?</td><td>Check workers and throughput</td></tr>
  <tr><td>Oldest due age</td><td>How old is the longest-waiting due job?</td><td>Prioritize old jobs, check for starvation</td></tr>
  <tr><td>P95/P99 queue delay</td><td>How long do most jobs wait before claim?</td><td>Analyze tail latency, break down by purpose</td></tr>
  <tr><td>Enqueue rate</td><td>How fast are jobs being created?</td><td>Compare against processing capacity</td></tr>
  <tr><td>Accept/terminal rate</td><td>How fast are jobs leaving the queue?</td><td>Inspect SMTP, workers, errors</td></tr>
  <tr><td>Retry due count</td><td>How many due retries have not run yet?</td><td>Inspect scheduler/backoff</td></tr>
  <tr><td>Expired leases</td><td>Were attempts claimed without finishing?</td><td>Check workers, crashes, network</td></tr>
  <tr><td>UNKNOWN count/age</td><td>How many outcomes are uncertain and for how long?</td><td>Reconcile; never replay blindly</td></tr>
  <tr><td>SMTP latency/error rate</td><td>How slow is transport and what errors occur?</td><td>Check TLS/AUTH, rate limits, timeouts</td></tr>
  <tr><td>Suppressed/failed count</td><td>Were jobs dropped intentionally or unsendable?</td><td>Handle by reason; do not retry blindly</td></tr>
</table>

Concrete metric names will be designed in the Micrometer section. There is no built-in "outbox backlog" meter provided by **`JavaMailSender`**: the application must measure its own outbox/worker state.

## 5. Example PostgreSQL schema for mail outbox

To keep queries consistent, use this illustrative table:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    notification_key VARCHAR(250) NOT NULL,
    purpose VARCHAR(80) NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100,
    status VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_attempt_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    lease_owner VARCHAR(120),
    lease_token BIGINT NOT NULL DEFAULT 0,
    lease_until TIMESTAMPTZ,
    accepted_at TIMESTAMPTZ,
    provider VARCHAR(80),
    last_error_category VARCHAR(80),
    CONSTRAINT uq_mail_business_notification
        UNIQUE (tenant_id, notification_key)
);
~~~

Design notes:

- **id**: outbox record identifier, useful for tracing; never use email addresses as metric labels.
- **notification_key**: stable logical key preventing duplicate notifications for the same event.
- **purpose/priority**: SLA grouping and processing order; requires fairness policies to avoid starvation.
- **available_at**: earliest claimable time, including scheduled sends and retry backoff.
- **created_at**: when the notification was recorded, used for end-to-end age.
- **lease_owner/lease_token/lease_until**: supports claiming and detecting orphaned attempts.
- **status**: state with clear semantics.
- **last_error_category**: operationally safe classification code, not raw SMTP transcripts.

This is a **custom application schema**, not Spring Mail DDL. Adapt it to your PostgreSQL version, ORM, partitioning, retention rules, and multi-tenant needs. It also omits recipient PII and MIME payloads to focus on backlog monitoring; real applications may store those in separate tables/storage under security policies.

### Indexes supporting due-job queries

~~~sql
CREATE INDEX idx_mail_outbox_due
ON mail_outbox (priority, available_at, id)
WHERE status IN ('PENDING', 'RETRY_WAIT');

CREATE INDEX idx_mail_outbox_due_time
ON mail_outbox (available_at, id)
WHERE status IN ('PENDING', 'RETRY_WAIT');

CREATE INDEX idx_mail_outbox_lease_expired
ON mail_outbox (lease_until, id)
WHERE status = 'IN_FLIGHT';

CREATE INDEX idx_mail_outbox_unknown_age
ON mail_outbox (updated_at, id)
WHERE status = 'UNKNOWN';
~~~

Not every system needs both due indexes. If workers always claim by **priority then available_at**, the first index helps; if dashboards primarily query by `available_at`, the second may fit better. Evaluate **`EXPLAIN ANALYZE`**, write overhead, and data distribution in your real environment. Indexes support a workload; they do not replace bottleneck analysis.

## 6. Overview status query without mixing scheduled and overdue

PostgreSQL supports the **`FILTER`** aggregate clause to summarize multiple groups in a single scan:

~~~sql
SELECT
    COUNT(*) FILTER (
        WHERE status IN ('PENDING', 'RETRY_WAIT')
          AND available_at <= CURRENT_TIMESTAMP
    ) AS due_backlog,
    COUNT(*) FILTER (
        WHERE status IN ('PENDING', 'RETRY_WAIT')
          AND available_at > CURRENT_TIMESTAMP
    ) AS scheduled_future,
    COUNT(*) FILTER (
        WHERE status = 'IN_FLIGHT'
          AND lease_until > CURRENT_TIMESTAMP
    ) AS active_in_flight,
    COUNT(*) FILTER (
        WHERE status = 'IN_FLIGHT'
          AND (
              lease_until IS NULL
              OR lease_until <= CURRENT_TIMESTAMP
          )
    ) AS expired_or_invalid_lease,
    COUNT(*) FILTER (WHERE status = 'UNKNOWN') AS unknown_count,
    COUNT(*) FILTER (
        WHERE status = 'PERMANENT_FAILED'
    ) AS permanent_failed_count
FROM mail_outbox;
~~~

**Note:** this query is for dashboards/investigation; do not run **`COUNT(*)` over a huge table every second** without evaluating load. For large datasets, use worker-aggregated metrics, bucketed stats tables, periodic indexed/partitioned queries, or an event stream, reconciling with SQL when needed.

### Querying the oldest due jobs

~~~sql
SELECT
    id,
    tenant_id,
    purpose,
    status,
    priority,
    created_at,
    available_at,
    CURRENT_TIMESTAMP - available_at AS overdue_duration,
    attempt_count,
    last_error_category
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND available_at <= CURRENT_TIMESTAMP
ORDER BY available_at ASC, id ASC
LIMIT 20;
~~~

This query prioritizes the oldest **`available_at`** to surface jobs that have been eligible longest. It avoids selecting recipient emails or message bodies, keeping PII out of operational screens.

### Computing max overdue age in seconds

~~~sql
SELECT COALESCE(
    EXTRACT(EPOCH FROM (
        CURRENT_TIMESTAMP - MIN(available_at)
    )),
    0
) AS oldest_due_age_seconds
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND available_at <= CURRENT_TIMESTAMP;
~~~

When no due jobs exist, **`MIN(available_at)`** is NULL, so the example falls back to 0. Dashboards must distinguish **empty backlog** from **database query failure**; never emit 0 when the query fails.

### Breakdown by status and purpose

~~~sql
SELECT
    purpose,
    status,
    COUNT(*) AS job_count,
    MIN(available_at) AS oldest_available_at,
    MAX(attempt_count) AS max_attempts
FROM mail_outbox
WHERE status NOT IN (
    'ACCEPTED', 'SUPPRESSED', 'CANCELLED'
)
GROUP BY purpose, status
ORDER BY purpose, status;
~~~

Grouping reveals scenarios where all marketing emails back up due to rate limits while security emails proceed normally—or conversely, where login confirmations starve because workers are consumed by a massive campaign.

## 7. Viewing latency by purpose and SLA

Not every mail type needs the same turnaround time:

| Notification type | Examples | Impact when delayed |
| --- | --- | --- |
| **Security-critical** | Verification codes, password resets | Login flows break; tokens may expire |
| **Transactional** | Order confirmations, receipts | User confusion or support tickets |
| **Operational** | Customer operational notices | Important updates delayed |
| **Product update** | Feature announcements | Usually higher tolerance for delay |
| **Marketing scheduled** | Newsletters, campaigns | Scheduled send time; pre-schedule time is not backlog |

Specific SLAs must be defined per product; Spring Framework Mail has no built-in global threshold. For example, **`oldest_due_age_seconds`** above 120 seconds may be critical for OTPs but benign for a batch newsletter.

### Querying delay by purpose

~~~sql
SELECT
    purpose,
    COUNT(*) AS due_jobs,
    COALESCE(
        EXTRACT(EPOCH FROM (
            CURRENT_TIMESTAMP - MIN(available_at)
        )),
        0
    ) AS oldest_due_seconds,
    COALESCE(
        EXTRACT(EPOCH FROM (
            CURRENT_TIMESTAMP - MIN(created_at)
        )),
        0
    ) AS oldest_end_to_end_seconds
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND available_at <= CURRENT_TIMESTAMP
GROUP BY purpose
ORDER BY oldest_due_seconds DESC;
~~~

Interpret results alongside send schedules and retry policies. A **`RETRY_WAIT`** job that just became eligible after multiple backoffs may have an old `created_at`, meaning high end-to-end age even though workers only became overdue recently.

### Queue delay vs end-to-end latency

For a single job:

~~~text
T0 created_at
     |
T1 available_at
     |
T2 first_claimed_at
     |
T3 SMTP accepted_at
~~~

- **Eligibility wait:** `T2 - T1`, reflects scheduler/worker backlog.
- **Processing duration:** `T3 - T2`, reflects rendering and SMTP time.
- **End-to-end latency:** `T3 - T0`, reflects experience from business event to SMTP acceptance.

For scheduled messages, end-to-end latency includes intentional waiting time. When measuring immediate-send SLOs, use `T3 - T0`; for scheduled mail, measure **`T3 - T1`** or compare against an explicit deadline.

### Records should capture meaningful timestamps

Useful timestamps include `created_at`, `available_at`, `first_claimed_at`, `last_attempt_at`, `accepted_at`, and `updated_at`. Never rely solely on **`updated_at`** to infer backlog age, because heartbeats/leases or retries can refresh it without real delivery progress.

If a job can be claimed multiple times, maintain a separate **`mail_attempt`** table to record each attempt's history, capturing queue delay, SMTP duration, and error per attempt. A single `last_attempt_at` field cannot replace full attempt history.

## 8. Detecting whether backlog is growing or draining

A snapshot may show 10,000 due jobs. Is the system processing 20,000 jobs/minute and about to drain, or only processing 100 jobs/minute while creating 5,000 new jobs/minute?

To answer that, compare **arrival rate** and **completion rate**:

~~~text
incoming_rate  = notifications created / second
terminal_rate  = notifications reaching a terminal state / second
net_growth     ~= incoming_rate - terminal_rate
~~~

When **`incoming_rate` exceeds `terminal_rate`** over a sustained window, total non-terminal work tends to grow. However, **due backlog** may not track that simple equation linearly due to future scheduling, retry backoffs, suppression, or state transitions. Use the formula as a trend signal rather than replacing state-bucket measurements.

### Illustrative example

~~~text
Enqueued:    2,000 notifications/minute
Accepted:    1,100 notifications/minute
Suppressed:    100 notifications/minute
Failed final:   50 notifications/minute

Net outstanding growth ≈ 750 notifications/minute
~~~

If this pace holds for 20 minutes, non-terminal notifications may grow by roughly 15,000 (ignoring schedule shifts and special states). That signals a need to investigate worker capacity or upstream issues.

### Do not equate attempts with notifications

If one job fails and retries five times, **`attempts_total`** increments five times while **`notifications_created_total`** increments once. For true throughput, count **notifications reaching `ACCEPTED` for the first time**, not total `JavaMailSender.send(...)` calls. Otherwise, a system failing continuously can look like it is "processing lots of mail."

### Capacity and backlog drain estimation

Suppose the due backlog is **B** and effective terminal processing rate exceeds new due-job arrivals by **D = processing_rate - due_arrival_rate**, where `D > 0`. You can estimate:

\[
\text{estimated drain time} \approx \frac{B}{D}
\]

This is only an approximation when rates are steady, jobs have similar cost, and no major swings occur from retries, provider throttling, or schedule spikes. If `D <= 0`, the backlog will not drain under current load.

Example: 6,000 due jobs, processing capacity 150 jobs/minute, and 50 new due jobs/minute. Net drain capacity is roughly 100 jobs/minute, or about 60 minutes. Never present this estimate as a guaranteed delivery promise.

## 9. Analyzing P95/P99 delay instead of averages alone

A low average queue delay does not guarantee no jobs are stuck. For instance, 99% of emails may process in 1 second while 1% wait 30 minutes; averages can mask tail latency under certain load distributions.

Metrics to separate:

- **Oldest due age:** identifies the worst currently stalled case.
- **P50/P95/P99 queue delay:** shows the delay distribution for claimed jobs.
- **P95/P99 end-to-end acceptance latency:** shows delay from eligibility to transport acceptance.
- **Count of jobs beyond SLA:** current jobs exceeding purpose-specific thresholds.

### SQL example counting SLA-breaching jobs by purpose

Assume application policy defines thresholds in seconds via a table or trusted configuration. Quick investigative query with an illustrative threshold:

~~~sql
SELECT
    purpose,
    COUNT(*) AS overdue_over_5_minutes
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND available_at <= CURRENT_TIMESTAMP - INTERVAL '5 minutes'
GROUP BY purpose
ORDER BY overdue_over_5_minutes DESC;
~~~

Do not assume 5 minutes is the SLA for every purpose. OTP may need a much tighter threshold, while batch marketing may differ. A policy table mapping `purpose` to `maximum_due_delay` is generally better than hardcoding thresholds across dashboards.

### Measure percentiles on completion events

P95 delay from eligibility to claim can be recorded directly in a **Micrometer Timer** or histogram. Avoid computing percentiles by fetching a huge set of `PENDING` rows to the application; that burdens the database and shifts while rows change.

Histograms/metrics need proper retention and bounded labels. Avoid putting recipient IDs or notification IDs into tags because cardinality explodes rapidly.

## 10. Querying overdue IN_FLIGHT jobs and lost workers

A job stuck in `IN_FLIGHT` may indicate slow SMTP, a crashed process, or a failed lease renewal. Query:

~~~sql
SELECT
    id,
    tenant_id,
    purpose,
    lease_owner,
    lease_token,
    lease_until,
    last_attempt_at,
    attempt_count,
    last_error_category
FROM mail_outbox
WHERE status = 'IN_FLIGHT'
  AND (
      lease_until IS NULL
      OR lease_until <= CURRENT_TIMESTAMP
  )
ORDER BY lease_until NULLS FIRST, id
LIMIT 100;
~~~

**`lease_until IS NULL`** while `IN_FLIGHT` indicates an invalid state if every claim requires a lease. Do not miss it simply because SQL `NULL` comparisons do not evaluate to true.

### An expired lease does not prove the email was not sent

A worker can:

1. Claim the job and commit `IN_FLIGHT`.
2. Send the message; SMTP server accepts it.
3. Crash before saving `ACCEPTED`.
4. Let the lease expire.

Blindly resetting all expired leases to `PENDING` and retrying can send the recipient a second email. Therefore:

~~~text
IN_FLIGHT + expired lease
           |
           v
          UNKNOWN
           |
           v
  Reconcile / safe retry policy
~~~

`UNKNOWN` is not "a lost job"; it is an explicit state telling the system to stop guessing and either find evidence or apply a clear risk decision.

### Leases do more than set deadlines

**`lease_owner`**, **`lease_token`**, and **`lease_until`** help:

- Let one worker claim a job for a bounded period.
- Detect workers that fail to finish.
- Prevent stale workers from overwriting newer outcomes via **`lease_token`** checks.
- Identify which worker/instance repeatedly loses leases.

**Fencing tokens only protect storage updates**; they cannot undo an external SMTP submission that already occurred. Never claim that lease policies yield exactly-once email delivery.

### Worker statistics query

~~~sql
SELECT
    lease_owner,
    COUNT(*) AS active_jobs,
    MIN(last_attempt_at) AS oldest_attempt_started
FROM mail_outbox
WHERE status = 'IN_FLIGHT'
GROUP BY lease_owner
ORDER BY active_jobs DESC;
~~~

If a worker holds many concurrent active jobs, compare against **worker concurrency**, SMTP connection count, and executor queue capacity. `lease_owner` must not contain secrets; an instance name or opaque ID suffices for operations.

## 11. The UNKNOWN status needs its own observability view

An email may time out after sending SMTP `DATA`; the server may have accepted the message while the client missed the final reply. If `JavaMailSender` throws an error, there is no proof the message was not accepted.

For the outbox, **`UNKNOWN`** needs:

- Count of notifications awaiting reconciliation.
- Age of the oldest `UNKNOWN`.
- Latest exception reason/category.
- Provider used on that attempt.
- Correlation ID or `Message-ID` for lookup if the provider supports it.
- Counts of `UNKNOWN` jobs recently confirmed `ACCEPTED`, safely retried, or escalated.

### Querying old UNKNOWN records

~~~sql
SELECT
    id,
    tenant_id,
    purpose,
    provider,
    updated_at,
    last_attempt_at,
    CURRENT_TIMESTAMP - updated_at AS unknown_duration,
    attempt_count,
    last_error_category
FROM mail_outbox
WHERE status = 'UNKNOWN'
ORDER BY updated_at ASC, id
LIMIT 100;
~~~

This query assumes **`updated_at`** was set upon transitioning to `UNKNOWN` and is not continuously overwritten by heartbeats/monitoring. If your application modifies `UNKNOWN` records often, add a dedicated **`unknown_since`** column so `UNKNOWN` age stays accurate.

### Reconciliation differs from retry

~~~text
UNKNOWN
  |
  v
Look up evidence in mail provider / SMTP logs / webhooks
  |
  +-- Proof of acceptance ---------> ACCEPTED
  |
  +-- Proof not accepted ----------> RETRY_WAIT / PENDING
  |
  '-- Insufficient evidence -------> Keep UNKNOWN / NEEDS_REVIEW
~~~

Plain SMTP has no standard API to ask "was the message with key K accepted?" **`Message-ID`** aids correlation but is not a universal idempotency key. A provider API offering lookup/idempotency can resolve `UNKNOWN`, provided you honor its documented guarantees and key retention window.

If the system decides to retry `UNKNOWN` to avoid missing emails, it must explicitly acknowledge and document the **duplicate send risk**. You cannot guarantee exactly-once SMTP delivery with an outbox and retries alone.

## 12. Retry schedules and backoff can also create a "backlog"

An SMTP outage can push thousands of jobs into `RETRY_WAIT`. Once the provider recovers, jobs may become due simultaneously:

~~~text
10:00 Provider fails
10:01 10,000 jobs hit temporary errors
10:02 Retries scheduled for 10:07
10:07 10,000 jobs become eligible together
      -> retry storm
~~~

Instead of scheduling every next retry at the same timestamp, use **exponential backoff + jitter**, capping both attempts and total retry duration.

~~~text
base delay: 10s
max delay: 10m
delay: min(max delay, base * 2^(attempt-1))
actual delay: delay * random factor
~~~

This is an example policy, not a Spring Mail default. Confirmed **4xx errors** can retry per provider policy; permanent **5xx errors** require classification; **ambiguous timeouts** require `UNKNOWN`/reconciliation rather than blind retry.

### Distinguish backoff waiting from overdue retries

~~~sql
SELECT
    COUNT(*) FILTER (
        WHERE available_at > CURRENT_TIMESTAMP
    ) AS retry_not_due,
    COUNT(*) FILTER (
        WHERE available_at <= CURRENT_TIMESTAMP
    ) AS retry_due
FROM mail_outbox
WHERE status = 'RETRY_WAIT';
~~~

Do not alert on **`retry_not_due`** rising alone when policy is intentionally shedding load after an outage. Do monitor **`retry_due`**, overdue retry age, and provider recovery rate.

### Never clear a backlog by deleting backoff

Setting every row to **`available_at = CURRENT_TIMESTAMP`** can trigger a burst that breaches rate limits or triggers spam blocks. To speed recovery, raise throughput safely while preserving jitter and respecting provider quotas.

## 13. Tracing from database to SMTP transport

When backlog climbs, identify which layer holds the bottleneck:

~~~text
Outbox SQL / database
        |
        v
Claim worker
        |
        v
Executor / concurrency
        |
        v
Render template / MIME
        |
        v
JavaMailSender
        |
        v
SMTP network + TLS/AUTH
        |
        v
SMTP server acceptance
~~~

An issue at any stage can push up the due backlog:

| Symptom | Likely cause | Data to check |
| --- | --- | --- |
| Due backlog rising, zero claims | Dead scheduler, query matching nothing, locks | Worker heartbeats, poll count, DB locks |
| High claim rate, accepted rate 0 | SMTP error, render exception, AUTH | Error categories, SMTP latency, exception logs |
| `IN_FLIGHT` rising, worker threads busy | Slow SMTP or missing timeouts | Thread dumps, socket timeouts, executor stats |
| `RETRY_WAIT` rising | Provider throttle, network outage | SMTP 4xx, retry distribution |
| `UNKNOWN` rising | Ambiguous timeouts or crash post-submission | Last stage, provider evidence, lease expiry |
| One tenant's jobs waiting long | Noisy neighbor, priority starvation | Due age by tenant/purpose/priority |
| Database CPU/locks spiking | Poorly indexed claim query or long tx | `EXPLAIN`, `pg_stat_activity`, lock waits |
| Accepted rate rising, users missing mail | Post-provider delivery/bounce/spam | ESP webhooks, bounce events, deliverability |

**`JavaMailSender.send(...)` succeeding** is only one observation point. If providers accept emails that never reach mailboxes, shift investigation to **delivery status**, suppression, bounces, and sender reputation—do not assume the outbox worker is stuck.

## 14. Inspecting worker schedulers and claim mechanics

An outbox worker typically loops:

~~~text
poll due jobs
     |
     v
claim atomically
     |
     v
commit claim
     |
     v
execute SMTP outside DB transaction
     |
     v
commit outcome in separate transaction
     |
     v
repeat
~~~

If workers fail to claim jobs despite many `PENDING` records in the database, distinguish:

- **Workers not running:** scheduler disabled, instance down, leader election/feature flag.
- **Workers running but seeing no jobs:** wrong `WHERE` condition, `available_at` not due yet, wrong tenant/priority filter, time zone mismatch.
- **Worker queries failing:** database connection pool exhaustion, timeouts, deadlocks, permissions, or schema mismatch.
- **Workers constantly hitting `SKIP LOCKED`:** another transaction holds locks on many rows.
- **Workers claiming without sending:** executor full, template rendering error, open circuit breaker, or unavailable SMTP.

### Multi-worker claim SQL using SKIP LOCKED

Reference PostgreSQL statement:

~~~sql
WITH candidate AS (
    SELECT id
    FROM mail_outbox
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND available_at <= CURRENT_TIMESTAMP
    ORDER BY priority ASC, available_at ASC, id ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE mail_outbox AS m
SET
    status = 'IN_FLIGHT',
    lease_owner = :worker_id,
    lease_token = m.lease_token + 1,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    last_attempt_at = CURRENT_TIMESTAMP,
    attempt_count = m.attempt_count + 1,
    updated_at = CURRENT_TIMESTAMP
FROM candidate
WHERE m.id = candidate.id
RETURNING
    m.id,
    m.tenant_id,
    m.purpose,
    m.notification_key,
    m.attempt_count,
    m.lease_token,
    m.lease_until;
~~~

**:worker_id** is bound by the application. The example assumes lower priority integers mean higher priority. The claim transaction must be short and **commit before opening an SMTP connection**, because database row locks must not be held across network waits.

### Do not treat SKIP LOCKED returning 0 rows as proof of no jobs

When **`SKIP LOCKED`** is active, a worker skips rows locked by other transactions. A **`0 rows returned`** result can mean:

- No due jobs exist.
- All eligible jobs are currently locked.
- Worker filters do not match.

Dashboards must count due jobs from status/`available_at` independently of claim outcomes to surface discrepancies. If due count is large while claim count is zero, inspect locks/transactions and query predicates.

### Query plans and indexes

Use **`EXPLAIN (ANALYZE, BUFFERS)`** carefully during investigation:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND available_at <= CURRENT_TIMESTAMP
ORDER BY priority ASC, available_at ASC, id ASC
LIMIT 100;
~~~

Running a plain `SELECT` first observes filter/sort cost safely before testing write statements in a controlled environment. **`EXPLAIN ANALYZE` executes the query**; avoid running it on `UPDATE`/`DELETE` directly in production without proper transaction/rollback control and permissions.

When tables hold millions of terminal records, lacking a partial index forces expensive scans/sorts. Adding indexes also increases write amplification and storage, so choose based on workload.

### Claiming fast does not mean sending fast

A worker might claim 1,000 jobs/minute while submitting only 50 emails/minute due to SMTP latency or small pools. Over-claiming ahead of processing capacity leaves many jobs `IN_FLIGHT`, risking lease expiration before sending even begins.

Therefore:

- Cap claimed jobs to real worker concurrency.
- Avoid pre-claiming large batches inside a single transaction.
- Monitor **`claimed_jobs`**, **`executor_queue_depth`**, and **`smtp_submission_duration`**.
- Only increase batch size when metrics prove database polling is the bottleneck.

## 15. Worker heartbeats, leases, and zombie workers

A worker process may stay alive while doing no mail work because its scheduler thread died, a circuit breaker opened, or DB connections ran out. Thus **`process_up`** alone never proves the dispatcher is healthy.

Useful signals:

- **Last successful poll timestamp:** most recent successful due-job query.
- **Last successful claim timestamp:** most recent job claim.
- **Last terminal transition timestamp:** most recent `ACCEPTED`/`SUPPRESSED`/`PERMANENT_FAILED`.
- **Poll errors total:** database read/claim failure count.
- **Active worker threads:** tasks currently executing.
- **Lease renewals/expirations:** whether workers exceed deadlines.
- **Last SMTP success timestamp:** last time the provider accepted a message.

### When zero claims is normal

If **`due_backlog = 0`**, going 30 minutes with no successful claims can be completely normal. Do not fire a "worker dead" alert simply because no emails needed sending. A better alert:

~~~text
due_backlog > 0
AND no successful claim for N minutes
AND scheduler should be active
~~~

### Lease duration must match SMTP timeouts

Suppose:

~~~text
Lease duration            = 15s
SMTP connection timeout   = 10s
SMTP read timeout         = 30s
SMTP write timeout        = 30s
~~~

A message can be processing validly yet expire its lease before the network operation finishes. To prevent false lease expirations:

- Size leases generously enough for task work and load conditions.
- Add safe heartbeats/renewals if operations are legitimately long.
- Never claim beyond worker capacity.
- Bound SMTP timeouts.
- Preserve **`lease_token`** to block stale DB updates.
- Still transition ambiguous outcomes to `UNKNOWN` when delivery cannot be verified.

There is no single universal lease duration formula; observe processing-time distributions plus worst-case/GC pauses.

### Stale worker finishes after losing its lease

If worker A stalls until its lease expires, worker B or a recovery job may alter the state. Worker A must never overwrite it with an unguarded `UPDATE`.

~~~sql
UPDATE mail_outbox
SET
    status = 'ACCEPTED',
    accepted_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :id
  AND status = 'IN_FLIGHT'
  AND lease_owner = :worker_id
  AND lease_token = :lease_token;
~~~

If the statement affects **0 rows**, the worker lost ownership or the state moved on. The system can log a late outcome in the attempt table for reconciliation, but must never bypass fencing checks just to "fix" state.

## 16. Instrumentation with Spring Boot Actuator and Micrometer

**Spring Boot Actuator** and **Micrometer** export application metrics to Prometheus or your observability backend. For the outbox, most meters must be **defined by the application**.

Suggested metric set:

| Logical name | Type | Meaning |
| --- | --- | --- |
| **mail_outbox_due_jobs** | Gauge | Due `PENDING`/`RETRY_WAIT` jobs |
| **mail_outbox_oldest_due_seconds** | Gauge | Max delay since `available_at` |
| **mail_outbox_scheduled_jobs** | Gauge | Future scheduled jobs |
| **mail_outbox_inflight_jobs** | Gauge | `IN_FLIGHT` jobs |
| **mail_outbox_expired_leases** | Gauge | `IN_FLIGHT` jobs with expired/missing leases |
| **mail_outbox_unknown_jobs** | Gauge | `UNKNOWN` jobs needing reconciliation |
| **mail_outbox_notifications_enqueued** | Counter | Notifications persisted to outbox |
| **mail_outbox_notifications_terminal** | Counter | Notifications entering a terminal state |
| **mail_outbox_attempts** | Counter | Worker send attempts |
| **mail_outbox_queue_wait_seconds** | Timer/histogram | Delay from `available_at` to claim |
| **mail_smtp_submission_seconds** | Timer/histogram | SMTP transport call duration |
| **mail_outbox_status_refresh_failures** | Counter | Metric snapshot refresh errors |

These are Micrometer-layer names; when exported to Prometheus, names may be normalized and Counters receive a **`_total`** suffix per registry rules. Check the actual metrics endpoint before writing PromQL instead of assuming every registry formats names identically.

### Single data snapshot to update Gauges

Instead of running SQL `COUNT(*)` on every Prometheus scrape, refresh a snapshot periodically and update in-memory Gauges:

~~~java
public record OutboxMonitoringSnapshot(
        long dueJobs,
        long scheduledJobs,
        long inflightJobs,
        long expiredLeases,
        long unknownJobs,
        double oldestDueSeconds
) {
}

public interface OutboxMonitoringRepository {
    OutboxMonitoringSnapshot loadSnapshot();
}
~~~

This repository is implemented by your project with JDBC/JPA. It should read a consistent snapshot sized for dashboards, avoid scanning excessive rows, and never read MIME bodies or PII during aggregation.

### Bean exporting Gauges on a schedule

~~~java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class OutboxMetricsReporter {

    private final OutboxMonitoringRepository repository;
    private final MeterRegistry registry;

    private final AtomicLong dueJobs = new AtomicLong();
    private final AtomicLong scheduledJobs = new AtomicLong();
    private final AtomicLong inflightJobs = new AtomicLong();
    private final AtomicLong expiredLeases = new AtomicLong();
    private final AtomicLong unknownJobs = new AtomicLong();
    private final AtomicLong oldestDueSeconds = new AtomicLong();
    private final AtomicLong lastSuccessEpoch = new AtomicLong();

    public OutboxMetricsReporter(
            OutboxMonitoringRepository repository,
            MeterRegistry registry
    ) {
        this.repository = repository;
        this.registry = registry;

        registry.gauge("mail_outbox_due_jobs", dueJobs);
        registry.gauge("mail_outbox_scheduled_jobs", scheduledJobs);
        registry.gauge("mail_outbox_inflight_jobs", inflightJobs);
        registry.gauge("mail_outbox_expired_leases", expiredLeases);
        registry.gauge("mail_outbox_unknown_jobs", unknownJobs);
        registry.gauge("mail_outbox_oldest_due_seconds",
                oldestDueSeconds);
        registry.gauge("mail_outbox_metrics_last_success_epoch_seconds",
                lastSuccessEpoch);
    }

    @Scheduled(fixedDelayString =
            "${app.mail.outbox.metrics.refresh-ms:30000}")
    public void refresh() {
        try {
            OutboxMonitoringSnapshot s = repository.loadSnapshot();
            dueJobs.set(s.dueJobs());
            scheduledJobs.set(s.scheduledJobs());
            inflightJobs.set(s.inflightJobs());
            expiredLeases.set(s.expiredLeases());
            unknownJobs.set(s.unknownJobs());
            oldestDueSeconds.set(
                    Math.max(0L, (long) Math.ceil(s.oldestDueSeconds()))
            );
            lastSuccessEpoch.set(Instant.now().getEpochSecond());
        } catch (Exception ex) {
            registry.counter(
                    "mail_outbox_status_refresh_failures"
            ).increment();
            // Log carefully; do not log recipient addresses or raw MIME.
            // Do not reset Gauges to 0 when the database query fails.
        }
    }
}
~~~

This sample uses **`@Scheduled`**, so enable scheduling in the Spring context (such as **`@EnableScheduling`**) if not already enabled. **Gauges start at 0 before the first refresh**; **`last_success_epoch_seconds`** shows whether data has ever loaded successfully. Values can lag by up to one refresh interval, so configure a dedicated stale-metrics alert.

In multi-instance deployments, every replica querying the same database emits identical global snapshots; **never blindly sum those gauges**, or you will double/triple-count. Dedicate a single exporter/leader for global backlog, or aggregate with **`max by (...)`** / select one designated instance. Per-worker metrics like active tasks should be handled differently from database-wide metrics.

### Increment event counters at state transitions

When writing an outbox notification or transitioning to `ACCEPTED` for the first time, the service can increment a Counter:

~~~java
registry.counter(
        "mail_outbox_notifications_terminal",
        "outcome", "accepted"
).increment();
~~~

Be careful **not to increment a counter before a transaction that might roll back** if the counter should reflect durable events. Conversely, crashing after DB commit before incrementing the counter can miss an event. For strict auditing/reconciliation, use the database/event stream as source of truth; application metrics are near-real-time operational signals, not a ledger.

### Keep tag cardinality low

Use bounded tags like **`purpose`**, **`status`**, **`provider`**, **`result`**, or **`worker_role`**. Never put recipient emails, notification IDs, order IDs, or raw exception text into tags. High-cardinality metrics inflate memory/storage costs and risk leaking personal data.

## 17. Mail outbox monitoring dashboard

A dashboard should communicate **current state**, **trend**, and **cause** without forcing operators straight into a SQL console.

### Suggested layout

~~~text
MAIL OUTBOX — OVERVIEW

Due jobs        Oldest due        UNKNOWN        Expired lease
   1,240          08m 12s           12                3

Due backlog over time           Enqueued vs terminal / minute
          /\                             incoming  --__
      ___/  \___                         terminal  ---_
  ___/          \__                      backlog trend

By purpose                      SMTP results
SECURITY     25                 accepted      85%
TRANSACTION  215                temp failure  11%
MARKETING    1,000              unknown        2%
                                permanent      2%

Workers                          Top error categories
active      8                    RATE_LIMIT     750
last claim  3s ago               AUTH_ERROR     220
leases      3 expired            READ_TIMEOUT    20
~~~

Numbers above are illustrative layout examples, not live telemetry. Display the **metric update timestamp** and data-source health prominently.

### Minimum panels

| Panel | Data type | Purpose |
| --- | --- | --- |
| Due backlog count | Single value + timeline | Detect due waiting jobs |
| Oldest due age | Single value + timeline | Detect SLA breaches |
| Due count by purpose | Grouped bar/stack | Separate security from marketing |
| Enqueue/terminal rate | Two line series | Spot growing backlog early |
| In-flight and expired leases | Gauge/time series | Detect stalled workers |
| Retry due vs future | Stacked series | Separate intentional backoff from lag |
| Unknown count and oldest age | Single value + table | Drive reconciliation |
| SMTP latency/error rate | Histogram/time series | Identify transport bottlenecks |
| Worker poll/claim/heartbeat | Time series | Distinguish dead worker vs idle queue |
| Metric snapshot age | Single value | Distinguish live data from stale data |

A dashboard showing only total **`PENDING`** and **`ACCEPTED`** is insufficient during an incident because it hides future schedules, retries, and `UNKNOWN` states.

### Do not double-count multi-instance metrics

When every Spring Boot replica queries the same `mail_outbox` table, global gauges repeat across pods. For example, three pods reporting **`due_jobs=100`** sum to **300** in Prometheus even though the database holds 100.

Mitigations:

- Dedicate one **metrics collector leader** for global backlog metrics.
- Scrape global gauges from a single designated exporter job/instance.
- Use **`max`** aggregation when all replicas report identical global state.
- Reserve **`sum`** across pods/instances for genuinely **per-worker** metrics representing combined capacity.

Aggregation rules depend on metric semantics. There is no blanket rule to "always sum every gauge" or "always max every gauge."

## 18. PromQL examples for backlog inspection

Assume the registry exports:

~~~text
mail_outbox_due_jobs
mail_outbox_oldest_due_seconds
mail_outbox_unknown_jobs
mail_outbox_expired_leases
mail_outbox_metrics_last_success_epoch_seconds
mail_outbox_notifications_enqueued_total
mail_outbox_notifications_terminal_total
~~~

These are **example post-export names**. Check the actual names at the Actuator/Prometheus endpoint because registries may transform dots, underscores, unit suffixes, and Counter naming.

### Inspecting current backlog

~~~promql
mail_outbox_due_jobs
~~~

### Age of the oldest due job

~~~promql
mail_outbox_oldest_due_seconds
~~~

### Queue is both large and significantly overdue

~~~promql
(mail_outbox_due_jobs > 100)
and
(mail_outbox_oldest_due_seconds > 300)
~~~

This expression assumes both series share **matching label sets**. If one metric carries a `purpose`/`tenant` label that the other lacks, adjust vector matching or aggregation appropriately to avoid empty results from label mismatches.

### Notification creation rate

~~~promql
rate(mail_outbox_notifications_enqueued_total[5m])
~~~

### Terminal completion rate

~~~promql
rate(mail_outbox_notifications_terminal_total[5m])
~~~

If the terminal metric includes an **`outcome`** label and you want the total across outcomes, use:

~~~promql
sum without (outcome) (
    rate(mail_outbox_notifications_terminal_total[5m])
)
~~~

Never put **`attempts_total`** into notification throughput comparisons because one notification can produce multiple attempts.

### Detecting stale metric snapshots

~~~promql
time() - mail_outbox_metrics_last_success_epoch_seconds > 180
~~~

This example assumes snapshots refresh more frequently than every 180 seconds. Before the first refresh after startup, `last_success` is 0 and the expression evaluates as stale—keep startup behavior in mind. If the exporter is down or Prometheus cannot scrape it, this expression may return no series; add separate alerts for **`up == 0`** or **`absent(...)`**.

### Tracking UNKNOWN and expired leases

~~~promql
mail_outbox_unknown_jobs
~~~

~~~promql
mail_outbox_expired_leases
~~~

For `UNKNOWN`/expired leases, many teams alert as soon as anomalies persist rather than waiting for thousands of rows. Exact thresholds depend on RTO, reconciliation tooling, and on-call coverage.

## 19. Designing alerts without false positives

If each campaign inserts 100,000 **`scheduled future`** rows, an alert on total `PENDING` fires even when the system is healthy. Alerts should bind to **due conditions** and **persistence duration**, separated by purpose.

### Suggested alerts

| Alert | Illustrative condition | Action |
| --- | --- | --- |
| **Due backlog growing** | Due count large and rising steadily | Compare processing vs arrival rate |
| **Oldest due SLA breach** | Oldest due age exceeds SLA | Prioritize affected purpose |
| **No progress** | `Due > 0` with zero claim/terminal progress | Inspect scheduler/workers |
| **Expired leases** | Multiple `IN_FLIGHT` jobs past lease | Check worker crashes and `UNKNOWN` |
| **UNKNOWN backlog** | `UNKNOWN` above count/age threshold | Run controlled reconciliation |
| **Retry storm** | Due retries spike sharply | Apply rate limits, backoff/jitter |
| **Metrics stale** | Snapshot too old or exporter down | Never trust stale gauges |
| **SMTP error spike** | Transport errors spiking | Diagnose AUTH/TLS/rate-limit/network |
| **Database claim failure** | Poll/claim errors rising | Check DB health, pool, indexes/locks |

### Example Prometheus alert rules

~~~yaml
groups:
  - name: mail-outbox
    rules:
      - alert: MailOutboxDueBacklog
        expr: >
          (mail_outbox_due_jobs > 100)
          and
          (mail_outbox_oldest_due_seconds > 300)
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Mail outbox has due jobs waiting to be sent"
          description: "Check workers, retries, and SMTP transport."

      - alert: MailOutboxUnknownNotResolved
        expr: mail_outbox_unknown_jobs > 0
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Notifications exist with unknown SMTP outcome"

      - alert: MailOutboxMetricsStale
        expr: >
          time() -
          mail_outbox_metrics_last_success_epoch_seconds > 180
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Outbox metrics snapshot is not updating"
~~~

These are **illustrative rules**, not universal thresholds. Tune 100 jobs, 300 seconds, or 15 minutes to your throughput, purpose, volume, and operating hours. If multiple replicas emit duplicated global gauges, normalize/aggregate series before alerting so one incident does not trigger N alerts.

### Principles to reduce alert noise

- Use **`for:`** to filter brief fluctuations during burst arrivals.
- Set different alert severities for **security/transactional** vs **marketing**.
- Alert when metrics go stale rather than treating failed DB queries as zero backlog.
- Group/silence downstream symptom alerts during a known root cause like an SMTP provider outage.
- Confirm recovery only when backlog and oldest age actually fall, not merely when the provider comes back online.
- Link runbooks and relevant panels; omit tokens, email addresses, and payloads from annotations.

### Base SLOs on eligible time

An illustrative SLO might be: "99% of transactional notifications are SMTP accepted within X seconds of `available_at`." Products define their own targets. For asynchronous provider APIs, **`ACCEPTED`** means the provider accepted the request, while mailbox delivery is a separate downstream state.

A sound SLO specifies start/end events, included notification types, how `SUPPRESSED`/`UNKNOWN` are handled, and how intentional future schedules are treated.

## 20. Multi-tenancy, partitioning, and starvation prevention

When an application serves multiple tenants or email categories, one large campaign can starve small critical notifications.

Example:

~~~text
Tenant A marketing  = 100,000 batch emails
Tenant B security   = 20 login verification emails

Shared workers: 10 concurrent SMTP connections
~~~

With pure FIFO and one shared queue, Tenant B's notifications can wait far too long. Options:

- Split queues or worker pools by **purpose**.
- Reserve concurrency slots for critical notifications.
- Apply **priority** paired with aging/fairness to prevent starvation.
- Enforce per-tenant throughput limits and provider quotas.
- Measure **oldest due age** separately for critical purposes/tenants.
- Run suppression checks before sending so blocked mail does not waste SMTP capacity.

### Priority indexes alone do not solve fairness

Workers running:

~~~sql
ORDER BY priority ASC, available_at ASC
~~~

can starve lower-priority jobs indefinitely if high-priority jobs keep arriving. Add weighted scheduling, quota reservations, or aging policies aligned with product requirements.

### Measuring per-tenant just enough for operations

In a system with tens of thousands of tenants, adding **`tenant_id`** to every metric label creates huge cardinality. Instead:

- Use SQL/drill-down dashboards filtered by tenant when needed.
- Aggregate by low-cardinality **`tier/region/purpose`**.
- Emit per-tenant metrics only for select tenants requiring dedicated SLOs under clear cardinality rules.
- Use access-controlled logs/traces when investigating an individual notification.

Never put recipient email addresses in metric labels to inspect per-user backlogs.

## 21. At massive database scale: observe without adding a bottleneck

A high-volume mail system may retain millions of outbox rows for audit. Constantly scanning the full table to count pending jobs can become a new bottleneck.

### Optimization strategies

1. **Partial indexes** covering active processing states.
2. **Retention/archival** of terminal rows per policy.
3. **Periodic snapshots** instead of `COUNT(*)` on every scrape.
4. **Batched `LIMIT` queries** for investigative views.
5. **Summary tables or counters** if dashboards refresh heavily.
6. **`EXPLAIN ANALYZE` and DB monitoring** before adding indexes.
7. **Partitioning** when volume/retention truly demands it, after weighing tradeoffs.

### Partitioning and unique key caveats

In PostgreSQL, unique constraints on partitioned tables impose rules tied to the partition key. If you partition by time yet require **`UNIQUE(tenant_id, notification_key)`** across the entire lifecycle, do not assume the original unique constraint works unchanged across partitions. You may need a dedicated deduplication table or an appropriate partition key design.

When archiving `ACCEPTED` outbox records, also preserve duplicate protection in case upstream events replay later. Deleting records and unique keys too early can recreate old notifications as brand-new jobs.

### Separate operational DB from analytics

If dashboards require long-term breakdowns across hundreds of dimensions, stream events/state transitions to an analytics store or metrics backend rather than scanning transactional history on every scrape. Keep in mind analytics can lag slightly, so retain direct operational DB checks for severe incidents.

## 22. Runbook when the outbox backlog alert fires

A runbook guides the on-call engineer from **symptom** to **root cause** and safe action. Never start an incident with a bulk `UPDATE` on job statuses.

### Step 1 — Verify telemetry freshness

Check:

- Is the Prometheus/metrics exporter healthy?
- Is **`last_success_epoch_seconds`** still updating?
- Do read-only queries against the operational DB roughly match the gauges?
- Are you looking at the right cluster/environment, tenant, or schema?

If metrics are stale, never conclude the backlog is zero or errors stopped. A flat chart often means telemetry stopped updating, not that workers recovered.

### Step 2 — Assess scope and priority

Classify:

- Due job count and oldest due age.
- Whether **`SECURITY`**, **`TRANSACTIONAL`**, or only scheduled marketing jobs are affected.
- `UNKNOWN` and expired lease counts.
- Whether impact hits one tenant, one provider, one cluster, or the whole fleet.
- Incident duration and affected mail-type SLAs.

If immediate security/transactional emails are delayed, raise their priority over scheduled marketing backlogs. However, prioritization never bypasses suppression, retry policies, or provider quotas.

### Step 3 — Separate new spikes from persistent backlogs

Inspect at least:

~~~text
Due count now
Due count 5 minutes ago
Oldest due age now
Enqueued/s
Terminal/s
Unknown count
Expired leases
~~~

If both due count and oldest due age are dropping, the system may be draining on its own. If accepted rate is 0 while due count rises, the pipeline is more likely completely blocked.

### Step 4 — Inspect worker progress

Check the worker dashboard:

- Are schedulers/consumers started?
- Was the last successful poll/claim recent?
- Are there connection pool errors or DB permission errors?
- Are workers crash-looping, OOMing, or hitting high CPU/GC?
- Are executor queues full with rising rejections?
- Does `IN_FLIGHT` match expected worker concurrency?
- Are expired leases climbing?

If **`poll rate = 0`**, investigate service lifecycle/scheduling before checking SMTP. If **poll/claim looks healthy while accepted rate is low**, drill into transport or rendering.

### Step 5 — Analyze SMTP and provider errors

Signal groups:

| Error/signal | Suspect | Investigative action |
| --- | --- | --- |
| `AUTH 535` or auth failures | Rotated credentials, wrong account, missing AUTH | Check secret rotation, provider status |
| `STARTTLS`/certificate exception | TLS trust/hostname, protocol mismatch | Verify chain, SAN, TLS policy |
| Connection refused/timeout | Network, DNS, firewall, SMTP outage | Check endpoint and egress policy |
| 4xx/rate limit | Provider throttling | Check quota, backoff, concurrency |
| 5xx/permanent recipient rejection | Bad address or sender policy | Classify per recipient; never retry blindly |
| Timeout after SMTP `DATA` | Ambiguous outcome | Mark `UNKNOWN` and reconcile |
| MIME render failure | Invalid template/model | Inspect template ID without dumping sensitive body |

Never disable TLS verification, point to unapproved SMTP servers, or swap arbitrary credentials to "clear" a backlog fast. That creates security holes and new deliverability failures.

### Step 6 — Check the database

When workers fail to claim despite high due counts:

- Are enough DB connections available?
- Does the claim query use the partial index?
- Are long-running transactions or row locks making `SKIP LOCKED` skip everything?
- Did a recent migration/schema change cause a mismatch?
- Is the outbox table bloating or filling disk?
- Are monitoring queries adding excessive load?
- Is a transaction hitting read-only mode or missing grants?

In PostgreSQL, **`pg_stat_activity`**, **`pg_locks`**, query plans, and DB metrics help—with proper access and caution against running heavy queries on an overloaded DB.

### Step 7 — Choose controlled remediation

Depending on root cause:

- Restart workers/schedulers if genuinely dead and claim recovery is safe.
- Roll back a bad deployment if the incident started right after a release.
- Fix credential/TLS/host settings via proper secret/config workflows.
- Throttle/pause marketing to free capacity for transactional mail.
- Reduce concurrency or increase backoff when providers rate-limit.
- Scale worker capacity **only if** the provider and DB can handle it, not blindly by bumping thread pools.
- Add/fix indexes when measurements prove a query bottleneck and migrations are safe.
- Reconcile `UNKNOWN` and expired leases before deciding on retries.

There is no single "reprocess all pending" command that is safe in all situations.

### Step 8 — Confirm full recovery

Do not close the incident solely because the SMTP endpoint came back. Verify:

- Due backlog drops back to normal levels.
- Oldest due age falls below each purpose's SLA threshold.
- Incoming and terminal rates balance.
- `UNKNOWN` and expired leases stop rising.
- No duplicate wave or suppressed-recipient sends occurred.
- Worker/DB/provider error rates return to normal.

If the backlog remains sizable while draining steadily, document progress and next check-in milestones rather than declaring complete recovery before SLAs are met.

## 23. Recovering a backlog without sending duplicates

Dangerous scenario: the SMTP provider just recovered from an outage; the dashboard shows 20,000 `PENDING`/`RETRY_WAIT` jobs and 200 `UNKNOWN` jobs. Someone runs:

~~~sql
-- DO NOT run this as a recovery fix:
UPDATE mail_outbox
SET status = 'PENDING',
    available_at = CURRENT_TIMESTAMP
WHERE status <> 'ACCEPTED';
~~~

That statement can:

- Turn `UNKNOWN` into retries even when the server already accepted the mail.
- Re-send `SUPPRESSED` or `CANCELLED` mail.
- Retry permanent/invalid recipient errors.
- Erase backoff and ignite a retry storm.
- Corrupt future scheduled send times.
- Violate opt-out or do-not-contact rules.

**Never treat every non-`ACCEPTED` state as safely resendable.**

### Recovery playbook by state bucket

| Bucket | Safer action |
| --- | --- |
| Due `PENDING` | Let workers claim normally within capacity and priority |
| Scheduled `PENDING` | Keep `available_at`; do not pull forward to now |
| Future `RETRY_WAIT` | Respect backoff; adjust only under controlled pacing |
| Due `RETRY_WAIT` | Retry per policy after rechecking suppression |
| `IN_FLIGHT` with valid lease | Let the active worker finish; monitor deadline |
| `IN_FLIGHT` with expired lease | Move via recovery to `UNKNOWN` or reconciliation state |
| `UNKNOWN` | Inspect provider/logs; never retry blindly |
| `PERMANENT_FAILED` | Fix underlying data/config or handle deliberately |
| `SUPPRESSED`/`CANCELLED` | Do not send |
| `ACCEPTED` | Never re-enqueue the same notification just because telemetry lagged |

### Safer recovery query for expired leases

When policy requires moving expired leases to `UNKNOWN` for reconciliation:

~~~sql
UPDATE mail_outbox
SET
    status = 'UNKNOWN',
    last_error_category = 'LEASE_EXPIRED',
    lease_owner = NULL,
    lease_until = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE status = 'IN_FLIGHT'
  AND (
      lease_until IS NULL
      OR lease_until <= CURRENT_TIMESTAMP
  )
RETURNING id, tenant_id, purpose, attempt_count;
~~~

This is an **example of a recovery service state transition**, not advice to run ad-hoc SQL manually in production. Implement it with transactions, authorization, batch bounds, auditing, race protection, and monitoring. A worker may still be mid-SMTP when its lease expires; late outcomes must be handled during reconciliation.

### Conditional requeue by ID

An administrative **`requeue(jobId, reason)`** endpoint should:

1. Verify operator authorization and write an audit log.
2. Read current status and full attempt history.
3. Verify the notification is still business-valid and not suppressed.
4. Permit transition only if prior outcome is proven safe to retry.
5. Use compare-and-set on status/version or lease token.
6. Never mint a new `notification_key` for the same logical event just to bypass deduplication.
7. Preserve retry limits, rate limits, and scheduling constraints.

If SMTP acceptance cannot be ruled out, warn explicitly that requeuing carries **duplicate risk** and may require product-owner sign-off.

### Retries after opt-out

A recipient might unsubscribe from a newsletter while the backlog sat waiting. As workers recover, re-check **mail delivery policy/suppression** before every marketing attempt. Never treat a recipient list snapshotted before the incident as proof the user still consents.

## 24. Reconciling UNKNOWN using concrete evidence

Helpful sources:

- Mail provider status APIs keyed by request ID or idempotency key, **if supported by the provider**.
- SMTP server logs containing queue ID, timestamp, recipient, or correlation ID.
- Provider webhooks reporting accepted/delivered/bounced.
- Local event/attempt history and timestamped logs.

### Limitations to acknowledge

Plain SMTP has no standard command to ask whether a previously attempted message was accepted. **`Message-ID`** helps tracing but does not force SMTP servers to deduplicate.

Not finding a message in a provider dashboard can simply reflect indexing lag or retention limits. **Not found** does not always equal **proven not accepted**.

### Suggested UNKNOWN investigation record

~~~text
notification_id:     6b91...
event_type:          ORDER_CONFIRMED
provider:            primary-smtp
attempt_id:          001...
attempt_started_at:  ...
last_error_category: SMTP_READ_TIMEOUT
outbox_status:       UNKNOWN
provider_evidence:   NOT_YET_AVAILABLE
reconciliation:      OPEN
operator_action:     HOLD
~~~

Never store plaintext passwords, OTPs, reset links, or raw MIME payloads in investigation records. Mask PII such as recipient addresses according to access controls.

### Post-reconciliation state transitions

~~~text
UNKNOWN
   |
   +-- Proof provider accepted it
   |       -> ACCEPTED
   |
   +-- Proof provider definitely did not accept it
   |       -> RETRY_WAIT (if still eligible)
   |
   +-- No conclusive proof
           -> HOLD / NEEDS_REVIEW
           -> retry only under explicit risk-acceptance policy
~~~

When a provider offers an official idempotency API, reuse the exact key within its documented retention window; never attribute idempotency guarantees to SMTP `Message-ID` that the protocol does not enforce.

## 25. Severity-based incident response planning

Incident tiers vary by product, but a practical framework looks like:

| Level | Illustrative scenario | Goal |
| --- | --- | --- |
| **High** | Due login/password-reset emails stalled broadly | Restore critical sending path; scope user impact |
| **Medium** | Transactional mail slow, backlog rising, provider throttling | Stabilize throughput, protect SLAs, prevent duplicates |
| **Low** | Small scheduled marketing backlog still inside send window | Monitor trends, tune capacity safely |
| **Investigate** | `UNKNOWN` rising even with small due backlog | Reconcile and resolve ambiguous outcomes |

No single backlog number maps to the same severity across all systems. **10 OTP emails delayed by 20 minutes** can be far worse than **20,000 newsletters not yet due**.

### Response roles

Responsibilities during an incident:

- **On-call/application owner:** checks workers, queue metrics, and recent releases.
- **Database operator:** analyzes locks, connection pools, query plans, and indexes.
- **Mail/provider owner:** checks SMTP health, credentials/TLS, rate limits, and provider events.
- **Product/support:** prioritizes high-impact notifications and handles user communications.
- **Security/privacy:** joins if credential leakage, misdirected mail, or opt-out violations are possible.

Small teams may combine roles, yet runbooks must remain explicit about who may **mutate job states** versus who holds **read-only** access.

## 26. Testing backlog detection

A system whose metrics look fine on the happy path can silently drop jobs when workers die. Test both **queue state transitions** and **metric/alert accuracy**, not merely whether `mailSender.send(...)` was called.

### Case 1 — A due PENDING job

~~~text
Given:
    status=PENDING
    available_at=now - 10 minutes
When:
    monitoring snapshot runs
Then:
    due_jobs increases by 1
    oldest_due_age >= 10 minutes (approximately)
~~~

Test timestamps can be anchored relative to a fixed **`Clock`** or database time. Avoid boundary timestamps right on `now` that cause flaky tests.

### Case 2 — A future scheduled job

~~~text
Given:
    status=PENDING
    available_at=now + 2 hours
Then:
    scheduled_jobs increases by 1
    due_jobs does not increase
    oldest_due_age is unaffected
~~~

This prevents false alarms when campaigns are pre-loaded hours before launch.

### Case 3 — Retry with backoff

~~~text
Given:
    status=RETRY_WAIT
    available_at=now + 15 minutes
Then:
    retry_not_due increases
    due_jobs does not increase

Once available_at becomes due:
    retry_due increases
    due_jobs increases
~~~

Tests should verify that schedulers never reset `available_at` to now just because a worker restarted.

### Case 4 — IN_FLIGHT job with valid lease

~~~text
Given:
    status=IN_FLIGHT
    lease_until=now + 30 seconds
Then:
    inflight_jobs increases
    expired_leases does not increase
~~~

### Case 5 — Expired lease

~~~text
Given:
    status=IN_FLIGHT
    lease_until=now - 30 seconds
Then:
    expired_leases increases
    recovery marks UNKNOWN per policy
    worker does not resend automatically
~~~

Specifically, simulate a server accepting the message while the process crashes before `markAccepted`. This test proves **recovery does not turn an ambiguous outcome into a blind retry**.

### Case 6 — Accumulated UNKNOWN jobs

~~~text
Given:
    status=UNKNOWN
    updated_at=now - 20 minutes
Then:
    unknown_jobs increases
    oldest_unknown_age reflects stalled duration
    job is not claimed as PENDING
~~~

In the illustrative schema, if `updated_at` can change during reconciliation, use a separate `unknown_since`. Tests reflect whichever timestamp semantics you choose.

### Case 7 — Metric refresh failure

~~~text
Given:
    previous snapshot: due_jobs=50
When:
    database query throws an exception
Then:
    refresh_failure counter increases
    last_success_epoch stays unchanged
    gauge is not forced to 0
    stale alert can fire past deadline
~~~

Never make a dashboard display "zero backlog" simply because the database temporarily failed a query.

### Case 8 — Two workers claiming concurrently

In a database integration test, seed one due row and race two transactions using **`FOR UPDATE SKIP LOCKED`**. Only one worker may claim the row; the other must not send the same notification simultaneously.

Concurrency tests should run against a database with production-matching locking semantics. If production uses PostgreSQL, Testcontainers PostgreSQL is far better than assuming an in-memory map simulates row locks accurately.

### Case 9 — One tenant creates a large campaign

Seed a massive marketing backlog alongside security emails; verify schedulers/priorities/quotas keep security mail within SLA. Pure priority systems can starve marketing jobs indefinitely, so test whichever fairness policy you designed.

### Case 10 — Unsubscribe after enqueue

~~~text
T0: Marketing notification PENDING
T1: Recipient opts out
T2: Worker claims job
Expected: SUPPRESSED, JavaMailSender never called
~~~

Backlog recovery must never accidentally bypass delivery policies.

### Case 11 — SMTP timeout after DATA

A fake transport simulates server acceptance while withholding the client ACK. The worker must record `UNKNOWN` and not auto-retry when policy requires hold-on-unknown.

This test is far stronger than mocking `JavaMailSender` to throw before external side effects, because it exercises real duplicate risk.

### Case 12 — Multi-replica metrics

Have three metrics exporters read the same table holding 100 due jobs. Verify dashboard/alert aggregation evaluates to **100**, not **300**, when gauges have global scope.

### Case 13 — ACCEPTED jobs stay out of due backlog

A job accepted by the SMTP server sits in a terminal state. Test that SQL does not count every record created in the last 24 hours instead of truly due records.

### Case 14 — Idle period is not worker-down

During a quiet period with no emails:

~~~text
due_jobs=0
last_claim_at=30 minutes ago
scheduler polling normally
~~~

Test that alert rules do not fire merely because no recent claims happened. Conversely, when `due_jobs > 0` and poll/claim stalls, the alert must fire meaningfully.

### JUnit example for the timing classifier

Small pure logic can be unit-tested independently of the database:

~~~java
import java.time.Instant;

public record OutboxForMonitoring(
        String status,
        Instant availableAt,
        Instant leaseUntil
) {
}

public final class OutboxClassification {

    private OutboxClassification() {
    }

    public static boolean isDue(
            OutboxForMonitoring job,
            Instant now
    ) {
        return ("PENDING".equals(job.status())
                || "RETRY_WAIT".equals(job.status()))
                && !job.availableAt().isAfter(now);
    }

    public static boolean isExpiredLease(
            OutboxForMonitoring job,
            Instant now
    ) {
        return "IN_FLIGHT".equals(job.status())
                && (job.leaseUntil() == null
                    || !job.leaseUntil().isAfter(now));
    }
}
~~~

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class OutboxClassificationTest {

    private static final Instant NOW =
            Instant.parse("2026-01-01T12:00:00Z");

    @Test
    void scheduledMailIsNotDue() {
        OutboxForMonitoring job = new OutboxForMonitoring(
                "PENDING",
                NOW.plusSeconds(3600),
                null
        );
        assertFalse(OutboxClassification.isDue(job, NOW));
    }

    @Test
    void retryBecomesDueAtItsAvailableTime() {
        OutboxForMonitoring job = new OutboxForMonitoring(
                "RETRY_WAIT",
                NOW,
                null
        );
        assertTrue(OutboxClassification.isDue(job, NOW));
    }

    @Test
    void expiredLeaseRequiresInvestigation() {
        OutboxForMonitoring job = new OutboxForMonitoring(
                "IN_FLIGHT",
                NOW.minusSeconds(60),
                NOW.minusSeconds(1)
        );
        assertTrue(
                OutboxClassification.isExpiredLease(job, NOW)
        );
    }
}
~~~

This example uses records and `java.time` to keep logic focused. **Unit-testing the classifier never replaces SQL integration tests**, because databases apply transaction timestamps, isolation levels, and null semantics differently from Java. Whenever due counts are computed in multiple places, keep one consistent definition so metrics and claim queries agree.

## 27. Real-world investigation scenarios

### Scenario A — 50,000 PENDING rows yet zero alerts

Queries show every `available_at` is tomorrow.

**Conclusion:** this is scheduled workload, not due backlog. If alerts inspect `COUNT(PENDING)`, fix the measurement.

### Scenario B — Due backlog 500, oldest due age rising steadily

Worker heartbeats stay green, yet `last successful claim` never moves.

**Investigation:** inspect the claim query, feature flags, DB locks, failing transactions, or whether the scheduler actually polls.

### Scenario C — High claim rate, ACCEPTED rate near 0

Dashboards show high `IN_FLIGHT` and surging SMTP latency.

**Investigation:** are workers stuck on sockets, missing SMTP timeouts, hitting provider throttling, or overloading executors? Do not rush to add workers, which can overload the provider further.

### Scenario D — SMTP provider returns bulk 4xx

`RETRY_WAIT` climbs with `available_at` spaced via backoff.

**Action:** verify transient failure vs rate limit, preserve backoff and jitter, and avoid resetting all `available_at` to `now`.

### Scenario E — UNKNOWN climbs after a wave of read timeouts

Some attempts may have been SMTP-accepted.

**Action:** never retry blindly; query provider logs/APIs and reconcile before changing states. Alert on `UNKNOWN` age.

### Scenario F — IN_FLIGHT hangs after a deployment

The new release crashes workers between SMTP and state updates.

**Action:** roll back/fix the app, transition expired leases to `UNKNOWN` via audited recovery, never replay everything.

### Scenario G — OTP emails slow while marketing keeps flowing

Worker pools are saturated by a campaign.

**Action:** partition capacity by purpose, prioritize security/transactional mail, verify fairness—never rely solely on priority inside one starvable queue.

### Scenario H — Metrics report zero backlog while users receive no mail

`last_success_epoch` is stale; the exporter lost DB connectivity.

**Action:** verify metric freshness and query the DB read-only; never trust stale gauges.

### Scenario I — Doubled workers without higher throughput

The SMTP provider caps total requests/connections.

**Action:** inspect rate limits, retry policies, and SMTP latency. Adding workers when the provider is the bottleneck only generates more errors and retries.

### Scenario J — Claim query crawls on a ten-million-row outbox

Most rows are `ACCEPTED`, yet queries still scan the whole table.

**Action:** evaluate partial indexes, retention/archival, batched queries, and query plans. Never run full-table `COUNT(*)` on every scrape.

### Scenario K — Worker logs show sent, yet outbox stays IN_FLIGHT

The provider may have accepted the mail while `UPDATE ACCEPTED` failed.

**Action:** check DB outcome writes, fencing tokens, and attempt logs. Never treat an expired lease as proof the mail was unsent.

### Scenario L — User unsubscribes while sitting in a backlog

A campaign enqueued the job yesterday.

**Action:** workers verify suppression pre-send and move jobs to `SUPPRESSED`—never "drain" a backlog by sending everything blindly.

### Scenario M — Noisy neighbor in multi-tenant setup

One tenant consumes most concurrency and slows everyone else down.

**Action:** measure due age per tenant/tier when needed, enforce quotas, and design fairness. Never blow up Prometheus cardinality by labeling every tenant/user.

### Scenario N — An import spikes enqueue rate 20x

No worker bugs exist, yet throughput falls behind.

**Action:** verify import legitimacy, schedule windows, batch/admission control, load shedding, and provider caps. Never scale workers unboundedly by reflex.

### Scenario O — SMTP accepted, yet mail never reaches the Inbox

Outbox rows are `ACCEPTED` and due backlog is low.

**Action:** pivot to provider delivery events, bounces, suppression, and spam placement; this is no longer an un-dispatched outbox backlog.

## 28. Common mistakes when inspecting backed-up outboxes

### Mistake 1 — Counting every row in the table

Millions of audited `ACCEPTED` rows make the chart rise endlessly even when mail sends smoothly.

**Fix:** separate due, scheduled, in-flight, `UNKNOWN`, and terminal states. Never use overall `COUNT(*)` to measure waiting backlog.

### Mistake 2 — Treating every PENDING row as stuck

`PENDING` can represent future scheduled emails.

**Fix:** check **`available_at <= CURRENT_TIMESTAMP`** before labeling a job due.

### Mistake 3 — Using created_at as scheduled backlog age

A newsletter created a week ago and due today has an ancient `created_at`.

**Fix:** measure overdue age from **`available_at`** and track end-to-end age separately.

### Mistake 4 — Using updated_at to mask aging jobs

A repeatedly retried job keeps refreshing `updated_at`, making it look brand new.

**Fix:** track `created_at`, `available_at`, and `last_attempt_at` distinctly. Use `unknown_since` for `UNKNOWN` if needed.

### Mistake 5 — Measuring attempts instead of accepted notifications

One job retrying 10 times boosts attempt throughput while zero emails succeed.

**Fix:** maintain separate counters for enqueued/terminal notifications versus attempts.

### Mistake 6 — Lumping non-due RETRY_WAIT into due backlog

Backoff works as intended, yet dashboards keep screaming overdue.

**Fix:** separate `retry_due` from `retry_not_due` via `available_at`.

### Mistake 7 — Treating expired leases as unsent

Workers can trigger SMTP side effects before disconnecting or dying.

**Fix:** expired leases go to recovery/`UNKNOWN` and reconciliation, never straight back to `PENDING`.

### Mistake 8 — Bulk-resetting statuses to "rerun"

Bulk resets cause duplicates, send suppressed mail, and wreck retry backoff.

**Fix:** recover by state bucket, concrete evidence, and policy with audit logs and idempotency keys.

### Mistake 9 — Skipping suppression checks before retries

A marketing job was enqueued while subscribed, then the recipient opted out.

**Fix:** check delivery policy on every submission, even during backlog recovery.

### Mistake 10 — Ignoring database polling failures

Gauges hold 0 because the reporter caught an exception and zeroed them out.

**Fix:** preserve last known values with a `last_success` timestamp, increment a refresh-failure counter, and alert on stale metrics.

### Mistake 11 — Summing global gauges across all replicas

Three workers reporting `due_jobs=100` plot 300.

**Fix:** designate one global metric owner or aggregate without multiplying DB state.

### Mistake 12 — Scaling thread pools without finding the bottleneck

If the provider is rate-limiting or the DB pool is saturated, adding threads worsens backlogs.

**Fix:** inspect claim rate, SMTP latency, error categories, worker concurrency, and provider quotas before scaling.

### Mistake 13 — Missing indexes for due queries

Workers scan and sort millions of terminal rows.

**Fix:** add partial indexes matching your query predicates, verify query plans, and enforce retention.

### Mistake 14 — Giving every campaign top priority

Without fairness, critical transactional notifications starve.

**Fix:** isolate capacity by purpose/tier and enforce quotas/aging.

### Mistake 15 — Enabling raw SMTP debug in production during a backlog

Logs expose PII, credentials, or MIME payloads while adding heavy I/O load.

**Fix:** rely on structured error categories, metrics, and correlation IDs; keep debug scoped, redact sensitive fields, and never log raw `AUTH`.

### Mistake 16 — Equating SMTP accepted with delivered

Outbox submission finished, yet bounces or spam filters still block inbox delivery.

**Fix:** monitor outbox acceptance separately from provider mailbox delivery events.

### Mistake 17 — Deleting terminal rows and losing deduplication

Replayed upstream events recreate already-sent mail once outbox rows and unique keys vanish.

**Fix:** design retention and dedicated dedup tombstones covering your replay horizon.

### Mistake 18 — Alerting on silence when traffic is zero

A "no claims in 5 minutes" alert pages overnight despite `due_backlog=0`, causing alert fatigue.

**Fix:** require `due_backlog > 0` for no-progress alerts and use dedicated scheduler health checks.

### Mistake 19 — Ignoring deployment logs during post-deploy stalls

A single claim-SQL tweak or SMTP property change can back up the whole queue.

**Fix:** annotate deployments/config changes on dashboards and compare incident onset against releases.

### Mistake 20 — Debugging by pulling full raw payloads

Running `SELECT *` or logging raw MIME leaks emails, auth tokens, and invoices.

**Fix:** query minimal metadata, enforce least-privilege access, and read payloads only when legitimately necessary.

## 29. Sample outbox incident record

A concise incident record streamlines handoffs between on-call engineers:

~~~text
Incident: MAIL-OUTBOX-LAG
Environment: production / cluster-a
Observed at: ...
Purpose affected: ORDER_RECEIPT
Due backlog count: 8,200
Oldest due age: 00:18:30
Scheduled future: 120,000 (excluded from due backlog)
In-flight: 24
Expired leases: 2
Unknown count: 4
Enqueue rate: 180/min
Terminal rate: 45/min
Top error: SMTP_RATE_LIMIT
Worker poll: healthy
Database claim: healthy
Provider status: throttled

Mitigation:
  - Reduced marketing concurrency
  - Preserved retry backoff + jitter
  - Held UNKNOWN without retrying
  - Monitored quota and accepted rate

Next check:
  - Are due backlog and oldest due age dropping?
  - Are UNKNOWN records reconciled?
  - Has transactional SLA recovered?

Owner / reason / timestamps: ...
~~~

Numbers above are illustrative. Real incident records must use verified metric/DB data, explicit timestamps with time zones, and zero personal data or SMTP credentials.

### Post-incident root cause analysis

Once the backlog stabilizes:

1. Pinpoint the **exact time** incoming rate first exceeded terminal rate or accepted rate dropped.
2. Correlate with deployments, credential rotations, provider outages, quotas, and DB faults.
3. Evaluate why alerts fired or missed; were any metrics stale?
4. Scope which emails were delayed and user impact.
5. Verify no duplicates, unsafe retries, or bypassed suppressions occurred.
6. Tune capacity, retries, indexes, SLAs, or ownership per confirmed root cause.
7. Add integration/fault-injection tests covering the observed failure mode.
8. Update runbooks and dashboards so future triage is faster.

Never stop at "workers were slow" if the true root cause was provider rate limiting or database lock contention.

## 30. Quick backlog triage flowchart

~~~text
Outbox alert firing?
         |
         v
Metrics still fresh?
   |             |
  No            Yes
   |             |
   v             v
Fix exporter    Due backlog > 0?
                 |             |
                No            Yes
                 |             |
                 v             v
            Check scheduled/  Oldest due age > SLA?
            UNKNOWN separately   |             |
                                No            Yes
                                 |             |
                                 v             v
                           Monitor trend     Workers polling/claiming?
                                                  |          |
                                                 No         Yes
                                                  |          |
                                                  v          v
                                             Scheduler/DB   SMTP/Executor?
                                                            |         |
                                                          Error     Healthy
                                                            |         |
                                                            v         v
                                                       TLS/AUTH/     Capacity,
                                                       timeout/     priority,
                                                       rate limit   fairness
                                                            |
                                                            v
                                                   Controlled mitigation
                                                            |
                                                            v
                                              Reconcile UNKNOWN/expired leases
                                                            |
                                                            v
                                             Due age and count dropping steadily?
                                                            |
                                                            v
                                                 Document incident + follow-ups
~~~

This is a triage guide, not a state machine. Real incidents can combine causes—such as slow DB claims alongside SMTP rate limits. Always let telemetry guide each step.

## 31. Core principles summary

~~~text
COUNT(outbox rows)               != due backlog
PENDING                           != always stuck
Scheduled future                  != overdue
available_at due                  -> due job
Oldest due age                    -> lag past eligibility
Enqueued rate > terminal rate     -> backlog tending to grow
High claim rate                   != high accepted rate
Expired lease                     != proven unsent by SMTP
UNKNOWN                           -> reconcile before retrying
SMTP accepted                     != Inbox delivered
Stale metrics                     != zero backlog
Multiple exporters on same DB     -> never blindly sum gauges
Bulk requeue                      -> duplicate, spam, and policy risk
Marketing retry                   -> must still recheck suppression
~~~

**Inspecting a backed-up outbox** must rest on **due job counts, oldest due age, enqueue/terminal rates, retry schedules, expired leases, and `UNKNOWN` outcomes**. In Spring Framework Mail, **`JavaMailSender`** handles transport, whereas measuring queues, claiming jobs, instrumenting Micrometer, and building dashboards/alerts belong to application design. A well-run platform not only detects backlogs early but explains **why they grow**, scopes impact by purpose, restores workers/providers/databases safely, and confirms latency truly drops. During incidents, preserve **idempotency**, **suppression**, and **`UNKNOWN`** states until proven otherwise—never flip every job back to `PENDING` just to make a chart look clean.
