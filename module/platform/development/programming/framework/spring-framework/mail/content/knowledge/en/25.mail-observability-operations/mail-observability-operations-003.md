# Monitoring Queues, Retry Counts, and Dead Letters

## 1. Why successful mail sends are not enough to operate a system

In an application using **Spring Framework Mail**, `JavaMailSender` creates, connects, and sends emails over SMTP. If an HTTP request waits on SMTP, the system slows down whenever the mail provider responds slowly. Therefore, transactional emails are commonly moved to a **queue, message broker, or transactional outbox** for asynchronous processing.

Once emails are queued, however, a new operational problem appears: the application accepted the send request, yet **operators cannot easily tell whether the email is being processed, retried, stuck, or sitting in a dead-letter queue**.

Some common scenarios:

- A user just placed an order, but the confirmation email waits in the queue for 20 minutes.
- The SMTP provider temporarily rejects connections; the same job is retried many times.
- A consumer dies mid-processing, leaving a job in `PROCESSING` state without returning it to the queue.
- A mailbox does not exist: infinite retries only increase bounces and hurt sender reputation.
- The system repeatedly throws template errors, but the software only logs exceptions without a `FAILED` state for remediation.
- Queue depth is near 0 yet emails are not going out: workers claimed all jobs and hung while connecting to SMTP.
- The broker accepted the message, but the worker disconnected before acking; the message may be redelivered and sent twice.

To handle these scenarios, monitor at least three dimensions:

1. **Queue:** How many emails are waiting, due, in-flight, and how long have they waited?
2. **Retry count:** How many attempts have occurred, why did they fail, when is the next retry, and has the limit been reached?
3. **Dead letter:** Where are the unrecoverable jobs, and do they have failure reasons, evidence, and a reprocessing workflow?

This lesson focuses on **observability and operations** for the email-sending pipeline. The goal is not just drawing dashboards, but defining accurate measurements, building actionable alerts, and establishing safe recovery procedures.

> **Technical boundary:** Spring Framework Mail does not include a built-in queue, retry store, or dead-letter queue for all applications. `JavaMailSender.send(...)` is the sending API; queues/outboxes, retries, DLQs, and metrics must be managed by the application or infrastructure such as RabbitMQ, Kafka, or a database.

## 2. Reference architecture

A transactional email pipeline can be structured as:

~~~text
HTTP API / Business service
          |
          v
Database transaction
  +--> Save business state
  +--> Save mail_outbox(PENDING)
          |
          v
       COMMIT
          |
          v
Queue or outbox dispatcher
          |
          +--> Claim / consume job
          |
          v
Mail worker (PROCESSING)
          |
          +--> Render template / build MIME
          |
          +--> JavaMailSender.send(...)
          |
     +----+--------------------+
     |                         |
     v                         v
  Success                   Failure
     |                         |
     v                         v
  SENT/SMTP_ACCEPTED     Classify exception
                               |
                   +-----------+-------------+
                   |                         |
                   v                         v
               Retryable                Terminal / limit
                   |                         |
                   v                         v
            RETRY + nextAttemptAt        FAILED / DLQ
                   |                         |
                   v                         v
             Queue when due              Operator runbook
                   |                         |
                   +-------------+-----------+
                                 |
                                 v
                       Metrics / traces / alerts
~~~

The **queue** can be a database table polled by workers, a message broker queue, or both. How metrics are collected must reflect the actual architecture.

### 2.1. Milestones to distinguish

| Milestone | What the system knows | What can be concluded? |
| --- | --- | --- |
| Request accepted | The API received the request | Does not guarantee the job was durably persisted |
| Job persisted/enqueued | Outbox row or broker message is confirmed | There is a send request waiting to be processed |
| Job claimed/delivered | A worker started an attempt | Does not guarantee SMTP was called yet |
| SMTP accepted | `JavaMailSender.send` returned normally | The SMTP relay accepted the message as observed by the app |
| Retry scheduled | The system saved `next_attempt_at` or routed to a delay queue | Not yet sent successfully; automatic recovery remains possible |
| Dead-lettered | The system stopped automatic retries | Needs investigation/fix or a decision not to resend |
| Provider delivered/bounced | Provider sent post-submission feedback | Reflects a post-SMTP delivery stage, not necessarily inbox |

Never use a single metric named `mail_sent_total` and increment it even when “a job was just queued”. Metrics must have clear semantics and boundaries.

## 3. Queue states to observe

In a database outbox model, common states include:

| Status | Meaning | Worker Behavior |
| --- | --- | --- |
| `PENDING` | Job persisted, not yet processed | Eligible to claim when due |
| `PROCESSING` | Worker holds a lease/claim token | Must not be reclaimed while lease is valid |
| `RETRY` | Retryable error with scheduled retry time | Claim only when `next_attempt_at <= now()` |
| `SENT` | SMTP send completed successfully | No further automatic processing |
| `FAILED` | Automatic retries stopped: permanent error, max attempts, or deadline | Retained for investigation/redrive |
| `UNKNOWN` (optional) | Uncertain whether SMTP accepted the message | Reconcile or retry per duplicate policy |
| `CANCELLED` (optional) | Business canceled delivery | Do not dispatch anymore |

With RabbitMQ, physical states differ: messages are **ready**, **unacked**, sitting in a **retry/delay queue**, or routed to a **dead-letter queue**. With Kafka, monitoring typically relies on **consumer lag, offsets, retry topics, and DLQ topics**, rather than queue depth in the RabbitMQ sense.

### 3.1. One job may appear across multiple layers

If the application writes an outbox row and also publishes to a broker:

~~~text
outbox PENDING/PROCESSING
        |
        v
broker ready/unacked
        |
        v
consumer processing
~~~

You cannot simply add outbox row counts and broker message counts and call that “total emails waiting”, because **one delivery can be represented at multiple layers simultaneously**. Pick one source of truth for delivery state, and use broker metrics for infrastructure diagnostics.

### 3.2. Do not mistake an empty queue for a healthy system

`queue_depth = 0` can occur when:

- Workers are keeping up and there is genuinely no backlog.
- Workers claimed a batch of jobs and are hung on SMTP.
- The publisher/outbox relay is failing and not pushing jobs into the queue.
- Consumers acked too early and dropped jobs before sending.
- Upstream stopped generating events due to an upstream outage.

Therefore, dashboards must combine **queue depth, in-flight jobs, oldest age, throughput, error rate, and producer activity**.

## 4. Defining key queue metrics

A dashboard should answer “how many”, “how long waiting”, and “is it making progress”.

| Logical Metric | Measurement Type | Meaning |
| --- | --- | --- |
| `mail_queue_ready` | Gauge | Jobs eligible now and waiting for a worker |
| `mail_queue_delayed` | Gauge | Jobs waiting until retry time or scheduled send |
| `mail_queue_inflight` | Gauge | Jobs claimed/received by consumers without a final outcome |
| `mail_queue_oldest_ready_age_seconds` | Gauge | Age of the oldest due job not yet processed |
| `mail_queue_oldest_unfinished_age_seconds` | Gauge | Age of the oldest unfinished job |
| `mail_queue_enqueue_total` | Counter | Total requests durably written to queue/outbox |
| `mail_queue_claim_total` | Counter | Total job claims / processing starts |
| `mail_queue_complete_total` | Counter | Total deliveries completed by outcome type |
| `mail_queue_claim_latency_seconds` | Timer/Histogram | Time from enqueue/eligible until worker claim |
| `mail_dispatch_duration_seconds` | Timer/Histogram | Processing time of one attempt |
| `mail_worker_active` | Gauge | Workers currently active |
| `mail_worker_heartbeat_age_seconds` | Gauge | Time since last heartbeat |

You do not need every metric on day one. However, **depth without age** misses starved jobs; **age without completion rate** cannot tell whether the system is recovering.

### 4.1. Ready vs. delayed

Example at 10:00:

~~~text
12 rows status=PENDING, next_attempt_at <= 10:00
18 rows status=RETRY, next_attempt_at <= 10:00
70 rows status=RETRY, next_attempt_at > 10:00
 4 rows status=PROCESSING, lease still valid
~~~

We can define:

~~~text
ready   = 12 + 18 = 30
delayed = 70
inflight = 4
~~~

If a dashboard only reports total `PENDING + RETRY = 100`, operators cannot tell that 30 jobs need immediate processing while 70 are legitimately waiting on retry schedules.

### 4.2. Oldest age and backlog growth

Suppose workers process 100 emails/minute while producers create 130 emails/minute. Queue depth grows by 30/minute; if this continues, wait times grow even with zero exceptions.

To detect this:

- Track **enqueue** rate and **completion** rate.
- Track queue depth over time.
- Measure the age of the oldest waiting delivery and p95/p99 latency from enqueue to completion.
- Monitor worker count and provider rate limits.

A rough estimate for backlog drain time:

\[
T_{\mathrm{drain}} \approx
\frac{\mathrm{ready\ backlog}}{\mathrm{completion\ rate}-\mathrm{new\ arrival\ rate}}
\]

Use this only when the completion rate exceeds the arrival rate and rates are relatively stable; never treat this formula as an exact completion time in systems with retries, quotas, and batching.

## 5. Measuring queues with a transactional outbox in PostgreSQL

Suppose the `mail_outbox` table has these columns:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    delivery_key VARCHAR(180) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    max_attempts INT NOT NULL DEFAULT 5,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    claimed_at TIMESTAMPTZ,
    lease_owner VARCHAR(100),
    lease_until TIMESTAMPTZ,
    last_error_code VARCHAR(100),
    last_error_kind VARCHAR(30),
    last_failed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at TIMESTAMPTZ
);

CREATE INDEX ix_mail_outbox_due
    ON mail_outbox (status, next_attempt_at);

CREATE INDEX ix_mail_outbox_lease
    ON mail_outbox (status, lease_until);
~~~

This is a **minimal schema to explain metrics**, not a complete production migration. Multi-worker systems need atomic claims, claim tokens/versions, unique idempotency keys, retention, and database-appropriate transaction boundaries. In PostgreSQL, `FOR UPDATE SKIP LOCKED` is a common pattern for concurrent row claiming.

### 5.1. Counting ready, delayed, processing, and failed

~~~sql
SELECT
    COUNT(*) FILTER (
        WHERE status IN ('PENDING', 'RETRY')
          AND next_attempt_at <= now()
    ) AS ready_count,
    COUNT(*) FILTER (
        WHERE status IN ('PENDING', 'RETRY')
          AND next_attempt_at > now()
    ) AS delayed_count,
    COUNT(*) FILTER (
        WHERE status = 'PROCESSING'
          AND lease_until > now()
    ) AS inflight_count,
    COUNT(*) FILTER (
        WHERE status = 'PROCESSING'
          AND (lease_until <= now() OR lease_until IS NULL)
    ) AS expired_lease_count,
    COUNT(*) FILTER (
        WHERE status = 'FAILED'
    ) AS failed_count,
    COUNT(*) FILTER (
        WHERE status = 'UNKNOWN'
    ) AS unknown_count
FROM mail_outbox;
~~~

This query gives a **snapshot at database execution time**, not an invariant count. Workers may claim or finish jobs immediately afterward, so dashboards must not expect charts from separate snapshots to reconcile to the exact millisecond.

### 5.2. Calculating the age of the oldest due job

~~~sql
SELECT COALESCE(
    EXTRACT(EPOCH FROM (
        now() - MIN(next_attempt_at)
    )),
    0
) AS oldest_ready_age_seconds
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY')
  AND next_attempt_at <= now();
~~~

This is the **overdue age relative to `next_attempt_at`**. If an email is scheduled for tomorrow, it must not inflate today's “waiting too long” metric.

To observe age since initial enqueue for unfinished jobs:

~~~sql
SELECT COALESCE(
    EXTRACT(EPOCH FROM (
        now() - MIN(created_at)
    )),
    0
) AS oldest_unfinished_age_seconds
FROM mail_outbox
WHERE status IN ('PENDING', 'PROCESSING', 'RETRY', 'UNKNOWN');
~~~

This metric has a different meaning: it can grow while jobs legitimately wait for retry. Display both **oldest ready age** and **oldest unfinished age** without sharing the same name for both calculations.

### 5.3. Detecting expired leases

~~~sql
SELECT id, attempt_count, lease_owner,
       lease_until, last_error_code
FROM mail_outbox
WHERE status = 'PROCESSING'
  AND (lease_until < now() OR lease_until IS NULL)
ORDER BY lease_until NULLS FIRST
LIMIT 100;
~~~

An overdue `PROCESSING` row can result from:

- Worker crash or kill.
- SMTP transport hanging due to overly long timeouts.
- Lease duration shorter than p99 latency.
- State-write failure after SMTP success.
- Missing worker heartbeats or DB failing to receive updates.

Do not blindly delete rows or resend immediately. You need controlled reclaim logic, fencing tokens, and awareness of the duplicate window if SMTP may already have received the email.

### 5.4. Query cost considerations

On a large outbox table, running full-table `COUNT(*)` multiple times per second can strain the database. Options include:

- Collecting at a sensible cadence instead of per HTTP request.
- Using appropriate indexes or partial indexes for status and `next_attempt_at`.
- Partitioning or archiving old `SENT` rows per retention policy.
- Using event-updated counters/gauges at very high scale, combined with periodic reconciliation.
- Limiting tenant/metric labels to prevent cardinality explosion.

Test `COUNT(*) FILTER` queries against your PostgreSQL version and realistic data volume; the dashboard must never become the bottleneck for the mail queue.

## 6. Retry count: definition and how to read the numbers

**Retry count** is easily misunderstood because it can mean at least three different things:

1. **Total attempts for a delivery:** `attempt_count` on the outbox row.
2. **Number of retries already performed:** `max(attempt_count - 1, 0)` when the first attempt counts as the initial send.
3. **Number of retries scheduled over a time window:** counter `mail_retry_scheduled_total` incremented when the system commits a retry decision.

These are not interchangeable. If a job is in `RETRY` after attempt #3, you can describe it as:

~~~text
attempt_count = 3
completed attempt #1 = initial attempt
completed attempt #2 = retry 1
completed attempt #3 = retry 2
next_attempt_at = ...
~~~

On dashboards, name columns accurately:

| Field / Metric | Unit | Example |
| --- | --- | --- |
| `attempt_count` | Claimed dispatch attempts | 3 |
| `retry_attempts_used` | Dispatch attempts after the first attempt | 2 |
| `max_attempts` | Maximum total attempts allowed | 5 |
| `mail_retry_scheduled_total` | Counter of persisted retry decisions | 1,256 since counter started |
| `mail_retry_due_count` | Gauge of due RETRY jobs | 42 |
| `mail_retry_delayed_count` | Gauge of future-scheduled RETRY jobs | 87 |
| `mail_retry_exhausted_total` | Counter of jobs stopped due to max attempts | 19 |

Never use a cumulative counter metric to show “how many jobs are currently retrying” without computing a rate or range. Counters keep growing and reset on process restart; gauges represent point-in-time counts.

### 6.1. Counting attempts by distribution

A query for backlog/retry analysis:

~~~sql
SELECT attempt_count, status, COUNT(*) AS deliveries
FROM mail_outbox
WHERE status IN ('PENDING', 'PROCESSING', 'RETRY', 'FAILED')
GROUP BY attempt_count, status
ORDER BY attempt_count, status;
~~~

Or a summary report:

~~~sql
SELECT
    COUNT(*) FILTER (
        WHERE status = 'RETRY'
    ) AS retry_jobs,
    COUNT(*) FILTER (
        WHERE status = 'RETRY'
          AND next_attempt_at <= now()
    ) AS retry_due_jobs,
    COUNT(*) FILTER (
        WHERE status = 'FAILED'
          AND attempt_count >= max_attempts
    ) AS failed_at_attempt_limit,
    COALESCE(MAX(attempt_count), 0) AS max_attempts_seen
FROM mail_outbox;
~~~

**Note:** `FAILED AND attempt_count >= max_attempts` only tells you which jobs hit the ceiling, not that all of them failed **because** of the ceiling. A permanent error may occur on the final attempt. To distinguish accurately, record a `terminal_reason` column or event history such as `MAX_ATTEMPTS_EXHAUSTED`.

### 6.2. Attempt count must increment at a well-defined boundary

An operationally clean convention:

- Increment `attempt_count` **once inside the claim transaction** when the worker begins a dispatch attempt.
- Persist attempt history with `attempt_no`, `started_at`, `claim_token`, and `worker_id`.
- When sending succeeds or fails, finalize the attempt record with its outcome.
- If the process dies, the attempt may remain `STARTED`; this serves as an audit trail for reconciliation rather than assuming SMTP did or did not receive it.

~~~text
Claim transaction:
  outbox.attempt_count += 1
  outbox.status = PROCESSING
  INSERT mail_attempt(outcome=STARTED)
  COMMIT
                 |
                 v
       JavaMailSender.send
                 |
            +----+----+
            |         |
            v         v
         Success     Exception
            |         |
            v         v
      mark SENT    mark RETRY/FAILED/UNKNOWN
            |         |
            +----+----+
                 |
                 v
       Commit outcome + attempt history
~~~

Do not increment the counter only inside `catch (MailException)`. If a worker crashes after claiming but before `catch`, that attempt goes uncounted and skews dispatch numbers.

### 6.3. Attempt history matters more than a single counter

Example `mail_delivery_attempt` table:

~~~sql
CREATE TABLE mail_delivery_attempt (
    id UUID PRIMARY KEY,
    outbox_id UUID NOT NULL REFERENCES mail_outbox(id),
    attempt_no INT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    outcome VARCHAR(40) NOT NULL DEFAULT 'STARTED',
    failure_kind VARCHAR(30),
    failure_stage VARCHAR(50),
    error_code VARCHAR(100),
    safe_summary VARCHAR(400),
    worker_id VARCHAR(100),
    UNIQUE (outbox_id, attempt_no)
);

CREATE INDEX ix_mail_attempt_error_code
    ON mail_delivery_attempt(error_code, started_at);
~~~

A useful timeline:

| Attempt | Time | Outcome | Error Code |
| --- | --- | --- | --- |
| #1 | 10:00:01 | `RETRYABLE_FAILURE` | `SMTP_CONNECTION_TIMEOUT` |
| #2 | 10:01:02 | `RETRYABLE_FAILURE` | `SMTP_SERVER_BUSY` |
| #3 | 10:03:06 | `SMTP_ACCEPTED` | — |

The outbox is in `SENT` with `attempt_count = 3`; the history still reveals two failures prior to success. If you only keep `last_error_code` on the outbox row and clear it on success, diagnostic history is lost.

### 6.4. Retry scheduled and retry execution are distinct metrics

When an attempt fails and transitions to `RETRY`, increment:

~~~text
mail_retry_scheduled_total{reason="smtp_temporary"}
~~~

When a worker actually re-claims a job that already had a prior attempt, increment:

~~~text
mail_retry_started_total{trigger="due"}
~~~

The two counters can differ due to future retry schedules, canceled jobs, or instance shutdowns. Never treat `scheduled` as the number of times SMTP was actually called again.

## 7. Classifying errors so retry counts are meaningful

Knowing a job retried many times is not enough to decide what action to take. Classify both **cause** and **stage**:

| Failure | Example | Common Strategy |
| --- | --- | --- |
| Template/MIME preparation | Missing template, invalid data | Usually terminal; fix code/data |
| SMTP authentication | `MailAuthenticationException` | Stop aggressive retries; check secret/provider policy |
| Transient SMTP connection | Connection refused, network outage | Retry with backoff |
| Provider rate limit | SMTP temporary response, quota | Backoff and reduce throughput |
| Permanent recipient rejection | Non-existent address | Terminal/suppression after verification |
| Ambiguous SMTP outcome | Timeout after DATA transmitted | `UNKNOWN`/reconcile or retry with duplicate policy |
| Worker/executor error | Task rejected, worker killed | Restore capacity, conditional reclaim |
| Database state-write failure | SMTP accepted but `markSent` failed | Alert state-write failure; do not assume SMTP failed |

In Spring Mail:

- `MailAuthenticationException` indicates an authentication error.
- `MailSendException` can wrap various transport/message errors, not all of which are transient.
- `MailPreparationException` and `MailParseException` usually relate to preparation/parsing.
- `MailException` is the base class and is insufficient alone to decide retries.
- `jakarta.mail.MessagingException` can occur when building a `MimeMessage` or during Jakarta Mail operations.

A classifier should return structured data:

~~~java
public enum FailureKind {
    TRANSIENT, PERMANENT, UNKNOWN
}

public record FailureDecision(
        FailureKind kind,
        String errorCode,
        String stage,
        String safeSummary) {
}
~~~

Never pass raw `exception.getMessage()` into metric labels or dashboards without controlling sensitive data. Nested SMTP exceptions can contain email addresses, hostnames, or other details.

### 7.1. Soft failures do not always need application retries

Distinguish between:

1. **SMTP submission not yet accepted:** the application may retry delivery when the error is clearly retryable.
2. **SMTP relay accepted and is attempting delivery:** the provider may retry on its own; the application should not create a new email just upon receiving `DEFERRED` feedback.
3. **Provider reports a final soft bounce:** business policy decides whether to issue another delivery.

Do not lump all of these into `mail_retry_total` and interpret it as “retry on every 4xx”. Provider retries after SMTP acceptance and outbox retries before acceptance are two separate loops.

### 7.2. Backoff, jitter, and queue age

An illustrative retry policy:

\[
d_n = \min(d_{\max}, d_0 \times 2^{n-1})
\]

With `d_0 = 30 seconds` and `max_attempts = 5`:

| Failed Attempt | Base Delay After Failure | Decision |
| --- | --- | --- |
| 1 | 30 seconds | RETRY if transient |
| 2 | 60 seconds | RETRY |
| 3 | 120 seconds | RETRY |
| 4 | 240 seconds | RETRY |
| 5 | — | FAILED/dead letter if attempts exhausted |

Jitter prevents workers from retrying simultaneously in a “retry storm”. Actual delay thresholds depend on SLAs, email type, provider quotas, and business deadlines. An email containing a 10-minute verification token should not be resent after the token has already expired.

When measuring queue age, **delayed retries** must have their own metric; do not fire a “ready backlog too old” alert for jobs that have not yet reached `next_attempt_at`.

## 8. What is a dead letter?

A **dead-letter queue (DLQ)** receives messages that consumers or the system can no longer handle under automatic policy. In a database model, the equivalent may be:

- An outbox record with `status = FAILED`.
- A dedicated `mail_dead_letter` or `mail_failure_archive` table.
- A broker queue/topic named `mail.dead-letter` / `mail.dlq`.

The common trait: these deliveries **stop automatic retries**, yet remain stored for investigation, root-cause remediation, and controlled redrive.

### 8.1. Common causes leading to dead letters

- Exhausting `max_attempts`.
- Unrecoverable template or data errors.
- Prolonged SMTP authentication failures due to bad credentials.
- Permanently rejected recipient or domain.
- Unparseable payload or schema violations.
- Business deadline expiration: the email is no longer meaningful.
- Retries still failing after circuit breaker/recovery windows.
- Operator explicitly moving a job to a terminal state.

Not every failure should be automatically redriven once in the DLQ. Re-sending an expired verification email can confuse users or deliver broken links.

### 8.2. Dead letter vs. lost message

| State | Durable Audit Trail? | Can Be Investigated? |
| --- | --- | --- |
| RETRY | Yes, job is rescheduled | Yes |
| FAILED/DLQ | Yes, job awaits explicit action | Yes |
| UNKNOWN | Yes, SMTP outcome needs reconciliation | Yes if evidence is saved |
| Lost message | No remaining job/event to send | Difficult or impossible |

A healthy system neither “hides” errors by catching exceptions and dropping jobs, nor “masks” errors with infinite retries. **A dead letter is a signal for structured recovery.**

### 8.3. Fields needed in a dead-letter record

| Field | Role |
| --- | --- |
| `delivery_id` | Identifies the delivery in the system |
| `business_event_id` / `delivery_key` | Business link and idempotency key |
| `failed_at` | Terminal failure timestamp |
| `attempt_count` and `max_attempts` | Shows how many attempts were made |
| `terminal_reason` | Why automatic retries stopped |
| `last_error_code` / `failure_kind` | Normalized root cause |
| `failure_stage` | Failing step: MIME, SMTP, state update, etc. |
| `next_action` (optional) | Fix template, rotate credential, review address, etc. |
| `safe_summary` | Diagnostic info free of secrets |
| `created_at` / `updated_at` | Audit timeline |
| `owner/worker` or correlation | Log/trace investigation |

Never automatically store raw exception objects, full MIME bodies, or SMTP passwords in dead letters. Payloads may contain email addresses, tokens, and customer data; enforce retention and strict access controls.

## 9. Dead letters in an outbox database

If the main queue is the `mail_outbox` table, the simplest approach is transitioning `status` to `FAILED`:

~~~sql
UPDATE mail_outbox
SET status = 'FAILED',
    last_error_code = :error_code,
    last_error_kind = :failure_kind,
    last_failed_at = now(),
    lease_owner = NULL,
    lease_until = NULL,
    updated_at = now()
WHERE id = :outbox_id
  AND status = 'PROCESSING'
  AND lease_owner = :worker_id;
~~~

This SQL **illustrates a terminal transition**. In concurrent systems, also verify `claim_token`/version and updated row count, so a worker that lost its lease cannot overwrite a newer worker's decision.

### 9.1. Use a separate terminal reason

Compare two failures:

~~~text
Delivery A:
  last_error_code = SMTP_TEMPORARY_UNAVAILABLE
  last_error_kind = TRANSIENT
  terminal_reason = MAX_ATTEMPTS_EXHAUSTED

Delivery B:
  last_error_code = TEMPLATE_MISSING_FIELD
  last_error_kind = PERMANENT
  terminal_reason = NON_RETRYABLE_FAILURE
~~~

Both are `FAILED`, yet their **operational causes differ**. Do not overwrite `last_error_kind=PERMANENT` on delivery A just because retries ran out; the latest error was still transient, while the stop policy was attempt exhaustion.

If `terminal_reason` needs to be stored, add that column or a corresponding event table to the schema. Do not conflate error class with terminal state.

### 9.2. Counting dead letters and tracking growth

~~~sql
SELECT
    COALESCE(last_error_code, 'UNKNOWN') AS error_code,
    COUNT(*) AS failed_jobs
FROM mail_outbox
WHERE status = 'FAILED'
GROUP BY COALESCE(last_error_code, 'UNKNOWN')
ORDER BY failed_jobs DESC;
~~~

With attempt history, you can count jobs **newly entering `FAILED` in the last 15 minutes** rather than viewing only cumulative totals. If the table only has `last_failed_at`, keep in mind that timestamp may be the most recent failed attempt rather than the terminal transition time. Having `failed_at` or a state-transition event is better.

A dashboard should display all of:

- **Current DLQ depth:** how many terminal jobs currently await handling.
- **New DLQ arrivals:** how many jobs enter dead letter per time interval.
- **DLQ oldest age:** oldest terminal job not yet triaged.
- **DLQ by cause:** error type, template, provider.
- **Redrive success/failure:** how many jobs recovered successfully after fixing the cause.

## 10. Dead-letter queues in RabbitMQ and broker systems

If the application uses RabbitMQ, you can configure a **dead-letter exchange (DLX)**. The broker routes messages to the DLX when rejected/nacked without requeue, when TTL expires, or under other dead-lettering conditions supported by the broker version and policy.

Example flow:

~~~text
mail.work queue
    |
    +--> Consumer ack success -> complete
    |
    +--> Transient failure -> retry policy
    |       |
    |       +--> Delayed/retry queue (TTL/backoff)
    |               |
    |               +--> Re-route to mail.work
    |
    +--> Terminal failure / retries exhausted
            |
            v
       DLX routing
            |
            v
       mail.dead-letter queue
            |
            v
        Operator / redrive service
~~~

`mail.work`, `mail.retry`, and `mail.dead-letter` are example names. Spring AMQP provides abstractions such as listeners, queue/exchange bindings, and error handling, but **Spring Mail does not create a DLQ automatically** just by adding `spring-boot-starter-mail`.

### 10.1. Ack, nack, requeue: avoid infinite loops

In broker consumers:

- **Ack after completing work per contract** so the broker does not redeliver unnecessarily.
- **Nack/reject with requeue** when policy permits retry, but never requeue immediately in an infinite tight loop.
- **Nack/reject without requeue** when you want the broker to dead-letter via the configured DLX.
- **Never ack before persisting required outcomes**, or a process crash can lose the processing trace.

Always setting `requeue=true` on a permanent error causes the same message to be picked up repeatedly, burning CPU/network without ever reaching the DLQ.

### 10.2. Broker retry counters are not business attempt counters

A broker may provide redelivery headers, dead-letter history, or similar metadata (such as RabbitMQ `x-death` across dead-lettering paths). However:

- Redelivery can happen due to consumer disconnects even when `JavaMailSender.send` was never called.
- A message may pass through multiple retry exchanges/queues.
- Headers can vary by broker, policy, and republish mechanism.
- When an application republishes a new message, original metadata may be lost unless explicitly copied.

When you need the exact number of **dispatch attempts for a delivery**, store attempt history and idempotency state in a controlled database or durable source of truth rather than relying solely on `redelivered=true`.

### 10.3. Kafka DLQ is an application-layer pattern

Kafka typically exposes consumer lag and offsets; a “DLQ” is usually a **separate topic** where consumers or framework error handlers route failed records after retries exhaust.

Considerations:

- When is the consumer offset committed?
- Is the DLQ record durably written before advancing past the original record?
- How does the retry topic implement delay/backoff?
- Must key/ordering guarantees be preserved on reprocessing?
- What retention, ACLs, and encryption are required for DLQ payloads?

Do not equate Kafka consumer lag with an absolute “unsent email count”: a single topic may carry multiple event types, partitions track offsets, or deliveries may have moved to a retry or DLQ topic.

### 10.4. One source of truth for delivery state

In a system using both an outbox and a broker, decide explicitly:

~~~text
Business delivery state -> database/outbox record
Broker queue depth      -> infrastructure backlog
Attempt history         -> dispatch execution
Dead letter event       -> terminal outcome
~~~

Use broker metrics for fast capacity diagnostics, and combine them with application metrics/database state to answer **which emails were sent, which need retries, and which failed terminally**.

## 11. Collecting metrics with Micrometer and Spring Boot Actuator

Spring Boot integrates **Micrometer** to record counters, gauges, timers, and publish metrics to monitoring systems like Prometheus. For queues/outboxes, distinguish:

- **Gauge:** current point-in-time counts at scrape: ready, delayed, in-flight, failed.
- **Counter:** cumulative event occurrences: claimed, retry scheduled, attempt failed, dead-letter arrived.
- **Timer/Histogram:** latencies and durations: enqueue-to-claim, dispatch time, time-to-SMTP-accepted.
- **Long task / heartbeat:** are workers still processing or stuck overtime?

Conceptual Maven dependencies:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Versions should be managed by your Spring Boot BOM. Never mix incompatible Micrometer versions arbitrarily with your project's Spring Boot version.

Example configuration:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,prometheus"
  endpoint:
    health:
      show-details: when-authorized

app:
  mail:
    metrics:
      refresh-ms: 30000
~~~

The Prometheus endpoint is typically at `/actuator/prometheus` when dependencies and configuration enable it. **Do not expose management endpoints publicly**: protect them with network policies, authentication/authorization, internal ingress, and least privilege.

### 11.1. Recording counters when an attempt finishes

A metrics helper class for workers:

~~~java
package com.example.mail.ops;

import java.time.Duration;
import java.util.concurrent.Callable;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class MailDispatchMeters {

    private final MeterRegistry registry;

    public MailDispatchMeters(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordAttemptOutcome(
            String outcome,
            String failureKind,
            String errorCode) {

        Counter.builder("mail.dispatch.attempts")
                .description("Completed mail dispatch attempts")
                .tag("outcome", outcome)
                .tag("failure_kind", failureKind)
                .tag("error_code", errorCode)
                .register(registry)
                .increment();
    }

    public void recordDispatchDuration(
            Duration duration, String outcome) {

        Timer.builder("mail.dispatch.duration")
                .description("Mail dispatch attempt duration")
                .tag("outcome", outcome)
                .register(registry)
                .record(duration);
    }
}
~~~

Example using normalized label values:

~~~text
outcome = smtp_accepted | retry | failed | unknown
failure_kind = transient | permanent | unknown | none
error_code = smtp_timeout | smtp_auth | mime_invalid | none
~~~

In production:

- Never pass arbitrary text from exception messages into `error_code`.
- Keep tag catalogs **bounded**: never use recipient, delivery ID, UUID, or raw SMTP responses as tags.
- In-memory counters can lose recent events on process crash; metrics do not replace attempt history/outbox state in the database.
- With multiple instances, Prometheus aggregates counters per instance and window; account for restarts/resets.

**Note:** Do not measure “attempt succeeded” solely from whether `JavaMailSender.send` threw an exception while ignoring state persistence. You can emit two separate metrics: one for **SMTP result** (transport returned normally) and one for **state persistence result** (`SENT` committed). If updating the database fails after SMTP acceptance, those two signals diverge—and that divergence is critical operational information.

### 11.2. Queue depth gauges from database snapshots

With a PostgreSQL outbox, you can periodically query metrics and store them in an object backing gauges:

~~~java
package com.example.mail.ops;

import java.util.concurrent.atomic.AtomicLong;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
public class MailQueueGauges {

    private final AtomicLong ready = new AtomicLong();
    private final AtomicLong delayed = new AtomicLong();
    private final AtomicLong inflight = new AtomicLong();
    private final AtomicLong failed = new AtomicLong();
    private final AtomicLong oldestReadyAgeSeconds = new AtomicLong();

    public MailQueueGauges(MeterRegistry registry) {
        Gauge.builder("mail.queue.ready", ready, AtomicLong::doubleValue)
                .register(registry);
        Gauge.builder("mail.queue.delayed", delayed, AtomicLong::doubleValue)
                .register(registry);
        Gauge.builder("mail.queue.inflight", inflight, AtomicLong::doubleValue)
                .register(registry);
        Gauge.builder("mail.deadletter.current", failed, AtomicLong::doubleValue)
                .register(registry);
        Gauge.builder("mail.queue.oldest.ready.age.seconds",
                oldestReadyAgeSeconds, AtomicLong::doubleValue)
                .register(registry);
    }

    public void update(MailQueueSnapshot value) {
        ready.set(value.ready());
        delayed.set(value.delayed());
        inflight.set(value.inflight());
        failed.set(value.failed());
        oldestReadyAgeSeconds.set(value.oldestReadyAgeSeconds());
    }
}

public record MailQueueSnapshot(
        long ready,
        long delayed,
        long inflight,
        long failed,
        long oldestReadyAgeSeconds) {
}
~~~

When placed in a real Java project, `public record MailQueueSnapshot` must reside in its own file per Java rules. This pattern illustrates **holding strong references to `AtomicLong`** so gauges observe stable objects; never register a new gauge with a `deliveryId` tag every time the queue changes.

A separate scheduler/collector can run the earlier SQL every 30–60 seconds:

~~~java
@Component
public class MailQueueSnapshotCollector {

    private final MailQueueSnapshotRepository repository;
    private final MailQueueGauges gauges;

    public MailQueueSnapshotCollector(
            MailQueueSnapshotRepository repository,
            MailQueueGauges gauges) {
        this.repository = repository;
        this.gauges = gauges;
    }

    @Scheduled(fixedDelayString =
            "${app.mail.metrics.refresh-ms:30000}")
    public void refresh() {
        MailQueueSnapshot snapshot = repository.readSnapshot();
        gauges.update(snapshot);
    }
}
~~~

This example assumes `@EnableScheduling` is enabled and a repository reads the snapshot. In production, the collector must handle database outages: **never reset all gauges to 0 when the query fails**, as that falsely tells dashboards “the queue is empty”. Retain the previous snapshot, increment `mail_queue_snapshot_refresh_failure_total`, and track the last successful collection timestamp to distinguish stale readings.

### 11.3. Counters and gauges may not align instantaneously

Suppose `mail.retry.scheduled` increments as soon as a worker decides to retry, and then the DB transaction rolls back. The dashboard may show an unpersisted retry. If you want metrics to reflect **committed decisions**, increment after transaction commit or derive metrics from committed outbox events.

Even after commit, a process can crash before incrementing the counter. **The database/event log is the durable audit source; Micrometer metrics are operational telemetry.** Never base financial or compliance invariants solely on in-process counters.

### 11.4. Which SMTP timings should be measured?

If possible, break down the time from claim to SMTP accepted:

~~~text
Enqueue wait time
  created_at -> claimed_at

Message preparation time
  render start -> MIME built

SMTP transport duration
  send start -> send return/error

State update duration
  result commit start -> commit complete

Total end-to-end time
  created_at -> SENT commit
~~~

If `send` is very fast while end-to-end latency is high, the issue is likely queue backlog; if the queue is nearly empty while `send` is slow, inspect network/provider/timeouts. A single combined timer cannot pinpoint the cause.

## 12. Prometheus/Grafana: panels to display

When Micrometer exports metrics to Prometheus, dots are typically converted to underscores and counters receive a `_total` suffix. **Exact names depend on registry conventions and versions**; verify `/actuator/prometheus` output before writing PromQL.

An operational dashboard can be organized into four sections:

### 12.1. Queue health

| Panel | Question |
| --- | --- |
| Ready depth | How many emails need immediate worker processing? |
| Delayed/retry depth | How many emails are legitimately waiting for retry? |
| In-flight / unacked | Are workers holding too many jobs for too long? |
| Oldest ready age | How long has the oldest due email been waiting? |
| Enqueue vs completed rate | Is the backlog growing or draining? |
| Worker active / heartbeat | Are workers alive and making progress? |

Sample PromQL (assuming metrics are exported with matching names):

~~~promql
# Jobs waiting at scrape time
sum(mail_queue_ready)

# Largest overdue age across instances/services
max(mail_queue_oldest_ready_age_seconds)

# Jobs currently being processed by workers
sum(mail_queue_inflight)
~~~

If every instance queries **the same database** to update a global gauge, `sum(mail_queue_ready)` will **multiply the count** by the number of replicas. In that setup, take `max` per group/queue, use a single collector, or use a recording rule selecting one authoritative source. Never apply `sum` to global database gauges without checking their scope.

### 12.2. Retry health

| Panel | Meaning |
| --- | --- |
| Retry scheduled rate | At what rate is the system scheduling retries? |
| Retry started rate | How many retries are workers actually executing? |
| Retryable failure rate | Is the SMTP/provider experiencing transient issues? |
| Attempts per delivery | How many emails require multiple attempts? |
| Retry exhaustion rate | How many deliveries hit the attempt limit? |
| Next-attempt overdue | Are due retry jobs going unprocessed? |

PromQL examples (using verified naming conventions):

~~~promql
sum by (error_code) (
  rate(mail_dispatch_attempts_total{outcome="retry"}[5m])
)

sum(
  increase(mail_retry_exhausted_total[1h])
)
~~~

A rise in retry rate does not automatically prove a network error. Inspect `error_code` and provider: if `smtp_auth` spikes across the board, fix credentials or configuration instead of raising `max_attempts`.

### 12.3. Dead-letter health

| Panel | Operational Action |
| --- | --- |
| DLQ current depth | Are many terminal jobs awaiting triage? |
| New DLQ arrivals by error code | Is this a new incident or recurring error? |
| Oldest dead-letter age | Has a ticket or incident been forgotten? |
| Redrive attempts/success/failure | Is recovery working effectively? |
| Terminal reasons | Failed due to max attempts or permanent errors? |

Example:

~~~promql
# FAILED jobs currently sitting in the dead-letter area
max(mail_deadletter_current)

# Dead-letter arrival rate by error category
sum by (reason) (
  rate(mail_deadletter_arrivals_total[15m])
)
~~~

These metric names are **instrumentation suggestions**. Export the `mail.deadletter.arrivals` counter from your application or corresponding broker adapter before using the PromQL above. Dashboards should not plot a fake flat zero if the underlying metric is not actually exported.

### 12.4. SMTP health

Separate charts for:

- SMTP accepted per minute.
- SMTP authentication failures.
- Transport timeout/connect errors.
- SMTP send duration p95/p99.
- Provider/relay-specific rate limit errors.
- Message preparation failures.
- Database state-update failures after SMTP acceptance.

If the provider supplies delivery/bounce events, create a separate **deliverability** dashboard. SMTP accepted rate is not delivered rate; queue monitoring does not replace bounce/complaint tracking.

## 13. Designing actionable alerts

An email system's queue depth can rise during traffic peaks while still meeting SLAs. Alerting solely on `queue_depth > 100` creates noisy false alarms.

Prioritize **due backlog age, forward progress, terminal failures, and meaningful error rates**.

| Signal | Example Condition | What to Check |
| --- | --- | --- |
| Oldest ready age breaches SLA | Oldest due job waiting > 5 minutes | Worker availability, provider throttling, backlog |
| Ready backlog growing steadily | Queue depth rising for 15 minutes | Enqueue vs. completion rate, capacity |
| No progress | Ready jobs exist yet completions = 0 for 10 min | Worker hang, scheduler, queue consumer |
| Expired leases | Multiple overdue `PROCESSING` jobs | Crash, SMTP timeout, lease duration |
| Auth failure spike | Sudden surge in auth errors | Secret rotation, SMTP account, provider policy |
| Retry exhaustion | Surge in jobs newly entering `FAILED` | Error type, max attempts, network/provider |
| Untriaged dead letters | Oldest DLQ age exceeds policy | Triage, owner, ticket |
| `UNKNOWN` results | Jobs uncertain whether SMTP accepted | Duplicate risk, DB failure, reconciliation |
| Metrics freshness | No fresh snapshot or scrape failed | Monitoring collector / DB access |

Threshold values such as “5 minutes”, “10 minutes”, and “15 minutes” are illustrative. Base alerts on **each email type's SLO**. Password reset emails have a short useful window unlike monthly invoices or newsletters.

### 13.1. Per-email-type SLOs

Example internal SLO:

~~~text
Transactional email:
  99% of accepted requests reach SMTP_ACCEPTED
  within 2 minutes, excluding provider-wide incident policy.

Password reset:
  99% of eligible jobs are submitted within 30 seconds,
  with expiry-aware handling.
~~~

These are illustrative assumptions; Spring Mail has no default SLO. When measuring, define:

- Does “Request accepted” mean durably persisted or merely HTTP received?
- Is the completion milestone SMTP accepted or provider delivered?
- Does the deadline start at request arrival, transaction commit, or job due time?
- Are suppressed/canceled jobs included in the denominator?
- Does the system handle future scheduled sends?

A good SLO ties to real user experience and avoids equating “worker threw no exception” with “user received the email”.

### 13.2. Rate- and ratio-based alerts

An error ratio:

\[
\mathrm{failureRate} =
\frac{\mathrm{failed\ attempts\ in\ window}}
{\mathrm{completed\ attempts\ in\ window}}
\]

If only 1 attempt occurred in 5 minutes and failed, the ratio is 100%, yet its severity differs vastly from 10,000 consecutive failures. Alerts need a **minimum traffic floor** or absolute error count paired with the ratio.

Example:

~~~text
Alert if:
  auth_failures >= 10 over 5 minutes
  AND auth_failure_rate > 20%
  AND environment = production
~~~

For high-signal critical conditions such as secret leakage or zero live workers, alert immediately on system state without waiting for high traffic volume.

### 13.3. Do not page on-call for every FAILED job

A nonexistent email address can legitimately produce a `FAILED` job without being an incident requiring a page. Distinguish between:

- Isolated failures handled via tickets or address verification workflows.
- Broad failure spikes caused by SMTP auth/TLS/network affecting multiple tenants.
- Sudden DLQ growth after a deploy, indicating a likely template regression.
- Security/invoice jobs missing deadlines with clear user impact.

Classify severity by **business impact**, not merely exception class name.

## 14. Monitoring producer, worker, and broker together

End-to-end observability requires visibility into both job production and consumption:

~~~text
Producer                                Worker
   |                                      |
   +-- enqueue_total                      +-- claim_total
   |                                      |
   +-- enqueue_error_total                +-- active_workers
   |                                      |
   +-- business_event_to_enqueue_time     +-- send_success_total
                                          |
                                          +-- send_failure_total
                                          |
                                          +-- state_update_failure_total
                                          |
                                          +-- heartbeat / last_success_time
                          |
                          v
                      Queue/Broker
                       ready
                       delayed
                       inflight
                       dead letter
~~~

A symptom like “ready queue empty, completion rate = 0” only makes sense when you know whether producers are creating jobs.

### 14.1. Worker heartbeats do not prove progress

A worker may send heartbeats steadily yet:

- Fail to claim jobs due to a SQL bug.
- Hang on a single delivery.
- Catch and swallow exceptions while continuing to loop.
- Poll the wrong queue partition or tenant.
- Poll successfully but fail to commit results.

Track **heartbeat**, **last successful claim**, **last SMTP accepted**, and **last state commit** separately when needed. An “alive” worker does not guarantee useful work.

### 14.2. Align timeouts and leases under one policy

Suppose:

~~~text
SMTP connection timeout = 5s
SMTP read timeout = 10s
SMTP write timeout = 10s
outbox lease duration = 2s
~~~

A 2-second lease can expire while an SMTP call is still running, causing another worker to reclaim the same job and send a duplicate.

Good configuration accounts for:

- Worst-case / p99 end-to-end processing.
- SMTP connect/read/write timeouts.
- Template/attachment rendering duration.
- Queue scheduling jitter and GC pauses.
- Heartbeats/lease extensions for long-running jobs.
- Concurrency and fencing tokens.

There is no universal “lease = exact SMTP timeout” rule. However, **leases must cover the workflow or be renewed by heartbeats**, and stale workers must never overwrite a newer claim's state.

## 15. Structured logs and correlation IDs

Metrics reveal trends; logs and traces locate a specific delivery.

A structured log event:

~~~json
{
  "event": "mail.dispatch.retry_scheduled",
  "deliveryId": "opaque-id",
  "template": "order-confirmation",
  "attempt": 3,
  "worker": "mail-worker-2",
  "errorCode": "SMTP_TEMPORARY",
  "failureKind": "TRANSIENT",
  "nextAttemptAt": "2026-11-12T10:30:00Z"
}
~~~

This example omits recipient addresses, passwords, body content, and verification tokens. `deliveryId` is an opaque identifier; if the system treats even IDs as sensitive, restrict log read access accordingly.

### 15.1. Useful fields for investigation

| Field | Reason |
| --- | --- |
| `deliveryId` / `outboxId` | Correlates every step of a send request |
| `businessEventType` | Identifies notification category |
| `attemptNo` | Identifies which attempt an event belongs to |
| `claimToken` (restricted access) | Investigates concurrency / stale workers |
| `workerId` / `instanceId` | Pinpoints failing instance |
| `provider` | Distinguishes multiple SMTP relays |
| `smtpResult` | Accepted / rejected / unknown |
| `errorCode` / `failureStage` | Investigates errors without raw exceptions |
| `queueWaitMs` / `smtpDurationMs` | Latency breakdown |
| `stateWriteResult` | Detects SMTP success followed by DB failure |

Never log raw `MimeMessage` payloads, full email content, SMTP credentials, password reset tokens, `To/Cc/Bcc` lists, or raw exception messages in general logs.

### 15.2. Tracing across API, outbox, and worker

With observability tracing, spans can look like:

~~~text
HTTP request span
   |
   +--> business transaction
            |
            +--> outbox insert
                      |
                      +-- (asynchronous boundary)
                                |
                                v
                        worker claim span
                           |
                           +--> render MIME
                           +--> SMTP send
                           +--> state update
~~~

Trace context across queues must be propagated explicitly per your tracing library; never assume `ThreadLocal` state from an HTTP request carries over automatically to a worker thread. Store minimal trace/correlation metadata in the outbox to link spans.

Never put message bodies or tokens into span attributes. Traces diagnose latency, but **never replace durable state**.

## 16. Runbook: unusual queue growth

When receiving `oldest ready age > SLO` or `queue ready depth increasing`:

**Step 1 — Verify the measurement.** Check metric freshness, snapshot timestamp, and tenant/queue scope. If gauges are exported by multiple replicas querying one DB, do not double-count.

**Step 2 — Check producer and consumer.** Compare enqueue rate against completion rate; are workers running, or heartbeating without progress?

**Step 3 — Inspect recent errors.** Check `mail_dispatch_attempts_total` by `error_code`, especially auth, TLS, connection timeouts, and rate limits.

**Step 4 — Check in-flight/leases.** If ready is low while `PROCESSING` or unacked is high, workers may be stalled or SMTP may be slow.

**Step 5 — Check provider quotas.** The system may be sending faster than SMTP limits allow; adding workers will not help if the provider is throttling.

**Step 6 — Choose the right remediation.**

- Worker crash: restore workers and conditionally reclaim expired leases.
- SMTP auth/TLS: fix secrets, certificates, or config; do not increase retry rates.
- Provider rate limit: reduce concurrency/throughput and increase backoff.
- Producer surge: apply backpressure or scale workers if safe under quota.
- Systemic template bug: roll back or patch deployment; route terminal jobs through redrive.
- Monitoring outage: restore the collector; never assume the queue is empty from stale metrics.

**Step 7 — Verify recovery.** Ready age drops, completion rate rises, error rate returns to baseline, DLQ growth stabilizes, and critical jobs drain before their deadlines.

### 16.1. Actions to avoid when a queue grows

- Scaling thread pools without checking SMTP quotas.
- Purging queues or resetting the DB to zero out dashboards.
- Resetting all `FAILED` rows back to `PENDING` without checking root causes.
- Retrying immediately with invalid credentials.
- Reclaiming `PROCESSING` rows that still hold a valid lease.
- Marking jobs `SENT` just to “clear the backlog”.
- Ignoring expired emails or suppression policies.

Queue operations mean fixing root causes, not merely making a dashboard number go down.

## 17. Runbook: sudden spike in retries

When `mail_retry_scheduled_total` or `RETRY` rows spike:

1. **Group by error code:** `smtp_auth`, `smtp_timeout`, `smtp_busy`, `mime_invalid`, `provider_policy`, `state_conflict`, etc.
2. **Check recent changes:** secret rotation, recent deploys, template updates, DNS/network changes, or provider limits.
3. **Evaluate transience:** automatically retry only errors that have a real chance of recovering.
4. **Inspect backoff and jitter:** are too many workers retrying every 1 second in lockstep?
5. **Check max attempts and deadlines:** are many jobs close to exhausting retries or expiring?
6. **Check rate limiting / circuit breakers:** should dispatch temporarily slow down to protect the provider?
7. **Assess duplicate risk:** were there timeouts after `DATA` or state-update errors after SMTP acceptance?
8. **Monitor post-fix:** due retries drop, SMTP accepted rises, and new DLQ arrivals stop spiking.

### 17.1. Credential incident example

~~~text
09:00 Old SMTP secret revoked
09:01 mail_auth_failures spikes sharply
09:02 Workers retry 1,000 jobs with the old credential
09:03 Queue + retry_count surge, provider flags abuse
~~~

Proper response:

- Check which secret version the application has loaded.
- Restore valid credential access or rotate/reload secrets.
- Pause aggressive retries once confirmed as an auth error.
- Record `SMTP_AUTH_FAILED` and hold in pending/terminal state per policy.
- After fixing, redrive or allow due jobs to resume in a controlled manner.

Never hammer an SMTP server thousands of times with invalid credentials just because `max_attempts=10` is configured.

## 18. Runbook: rapid dead-letter growth

Rising DLQ volume usually signals **an unrecoverable error class** or **a misconfigured retry policy**. Procedure:

1. Identify scope: template, provider, environment, tenant, start time.
2. Sample a few deliveries from the DLQ; inspect attempt history and sanitized error codes.
3. Separate **permanent** failures from **transient failures that exhausted attempts**.
4. Check deployments, secret changes, and provider incidents around the spike.
5. Fix the root cause: invalid template, wrong secret, quota policy, or recipient data.
6. Verify payloads are still valid; security emails may have expired.
7. Decide whether to redrive the same delivery or issue an audited new request.
8. Dispatch redrives with rate limiting; watch success rates and new errors.
9. Close the incident only when the backlog drains within SLA, not merely when DLQ rows are deleted.

### 18.1. Triage by error category

| DLQ Cause | Typical Appropriate Action |
| --- | --- |
| `SMTP_AUTH_FAILED` | Rotate/fix credentials, verify all instances, then redrive |
| `SMTP_RATE_LIMIT` retries exhausted | Tune throughput/backoff/quotas; redrive with rate limit |
| `MAIL_TEMPLATE_INVALID` | Fix template/model, validate payload schema before redrive |
| `RECIPIENT_INVALID` | Verify/correct address; do not resend as-is |
| `BUSINESS_DEADLINE_EXPIRED` | Usually do not resend expired emails |
| `SMTP_OUTCOME_UNKNOWN` | Reconcile duplicate risk before sending again |
| `STATE_UPDATE_CONFLICT` | Investigate lease/fencing and SMTP history before redrive |

### 18.2. Never redrive directly from a dashboard with a bare “Retry all” button

A redrive feature should require:

- Role-based authorization.
- Explicit scope: delivery IDs, template, time range, error type.
- Suppression, deadline, and idempotency policy checks.
- Dry-run preview: how many messages qualify and how many are ineligible.
- Rate limits and batch sizes.
- Audit trail of `who/when/why`.
- Post-redrive status verification.

Some messages must be **intentionally skipped**; not everything in a DLQ should be resent. Redrive results should distinguish “requeued”, “SMTP accepted”, “blocked by suppression”, and “ineligible”.

## 19. Designing controlled redrives

**Redrive** returns a terminal/quarantined message to active processing following an authorized operational decision. With a database outbox, never manually edit a `FAILED` row and wipe its history; with a broker, never bulk-republish DLQ messages while stripping origin metadata.

### 19.1. Two redrive models

**Model A — Continue the same delivery record:**

~~~text
delivery_id = D1
attempt history: 1, 2, 3 (FAILED)
operator approves redrive
retry_cycle = 2
attempt history: 4, 5...
~~~

Pros: preserves one continuous history. Cons: you must clearly define whether `max_attempts` caps **one retry cycle** or the delivery's lifetime; never arbitrarily reset `attempt_count` to 0.

**Model B — Create a new delivery linked to the old one:**

~~~text
original_delivery_id = D1 (FAILED)
redrive_delivery_id  = D2 (PENDING)
redrive_of = D1
reason = "SMTP credentials fixed"
~~~

Pros: keeps `D1` immutable for auditing; `D2` is an explicitly authorized new request. Cons: requires careful idempotency-key design to separate legitimate resends from accidental duplicates.

No single model fits every system. What is mandatory is **preserving the audit trail and preventing resends outside business policy**.

### 19.2. Illustrative SQL to redrive a FAILED record

Assuming separate auditing and a policy permitting a new retry cycle:

~~~sql
UPDATE mail_outbox
SET status = 'RETRY',
    next_attempt_at = now(),
    lease_owner = NULL,
    lease_until = NULL,
    updated_at = now()
WHERE id = :delivery_id
  AND status = 'FAILED'
  AND :redrive_authorized = TRUE;
~~~

This is an **illustrative** state transition; production requires:

- Authenticating/authorizing the redrive request at the service layer.
- Checking that the recipient is not suppressed and the event has not expired.
- Defining how `attempt_count >= max_attempts` is handled: unless new attempts or a new retry cycle are granted, workers still cannot claim it.
- Writing the audit event in the same transaction.
- Preserving prior failure reasons in attempt history.
- Preventing two operators from redriving the same message concurrently.
- Checking updated row count and version to avoid races.

Never accept a client-supplied boolean `redrive_authorized` as a security control. In the snippet above, it merely represents a **decision verified by the service layer**; real enforcement must rely on trusted authentication/authorization.

### 19.3. Audit table

An audit table can record:

~~~sql
CREATE TABLE mail_redrive_audit (
    id UUID PRIMARY KEY,
    delivery_id UUID NOT NULL,
    actor_id VARCHAR(120) NOT NULL,
    action VARCHAR(40) NOT NULL,
    reason VARCHAR(300) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    previous_status VARCHAR(40),
    next_status VARCHAR(40)
);
~~~

Never store passwords or tokens in `reason`. If an operator needs to link a ticket, store an incident/ticket ID instead of pasting raw logs or credentials into the audit table.

### 19.4. Broker redrives must avoid duplicates

For a physical DLQ:

1. Read the message and origin metadata.
2. Identify the delivery ID and inspect business state.
3. Validate redrive eligibility, suppression, and deadlines.
4. Publish the message back to the work queue or retry topic **with publisher confirms**.
5. Only ack/delete the source DLQ message once publishing is confirmed per broker contract.
6. Write the audit record and update delivery state within an appropriate transaction/outbox boundary.

If publishing succeeds but the redrive worker crashes before acking/deleting from the DLQ, the message may be redriven again. That is why **idempotency by delivery ID** is necessary, rather than assuming a “move” operation is atomic across every broker.

## 20. Handling outages: pause, circuit breaker, and rate limiting

During an SMTP provider outage, retrying every job simultaneously can overload the system. An architecture can combine three mechanisms:

1. **Rate limiter:** controls requests/second and concurrency per provider/account.
2. **Circuit breaker:** pauses SMTP calls during sustained failures to avoid making the outage worse.
3. **Backoff/jitter:** spreads out retry times across deliveries.

~~~text
Ready queue
    |
    v
Rate limiter
    |
    v
Circuit breaker
    |
    +--> CLOSED: allow send
    |
    +--> OPEN: do not invoke SMTP
                |
                v
          Schedule retry / wait
~~~

When the circuit is open, **never** mark jobs as `SENT`. Depending on design, jobs stay in `RETRY` or are requeued with a delay; avoid claiming excessive jobs only to let their leases expire while the circuit is open.

### 20.1. Metrics that guide scaling decisions

- `mail_queue_ready` and oldest ready age increasing.
- High `mail_dispatch_duration_seconds` p95.
- Active worker count near maximum.
- Queue claim rate below enqueue rate.
- Whether SMTP error codes indicate rate limiting or auth failures.
- Broker unacked count or Kafka consumer lag.

Scaling workers helps only when the bottleneck is actually worker capacity. If the provider limit is 100 emails/minute, scaling from 4 to 40 workers will simply get more requests throttled.

### 20.2. When should producers slow down?

If backlog exceeds processing capacity or queue storage nears limits, apply backpressure:

- Rate-limit non-essential notifications.
- Batch non-urgent emails if business rules permit.
- Return appropriate overload responses if requests have not been durably accepted yet.
- Defer non-urgent notifications to later send windows.
- Protect critical transactional emails with appropriate priority.

Never silently drop important business events without recording state; a full queue must be an **explicit operational signal and API contract**, not a swallowed error.

## 21. Incident: SMTP accepted but state update failed

This is one of the hardest operational failure modes:

~~~text
Worker claims delivery #D1
       |
       v
JavaMailSender.send returns successfully
       |
       v
Database commit markSENT fails
       |
       v
Outbox still PROCESSING/RETRY after lease expiry
       |
       v
New worker may dispatch again
       |
       v
Duplicate email possible
~~~

A database failure after SMTP acceptance **does not** mean transport failed. Emit dedicated metrics and logs:

~~~text
mail.smtp.accepted.total
mail.state.update.failures.total{operation="mark_sent"}
mail.outbox.unknown.current
mail.outbox.lease.reclaimed.total
~~~

In practice, metric names follow your Micrometer/Prometheus conventions, while keeping their semantics strictly distinct.

### 21.1. Never claim exactly-once with plain SMTP

A transactional outbox ensures business changes and send intent commit together, but it does not create a distributed transaction between SMTP and the database. Dispatch normally has **at-least-once semantics**, meaning a duplicate window exists.

`Message-ID` helps correlation, though not every SMTP server deduplicates on it. If an email provider offers an API with an idempotency key, you can follow their contract; plain SMTP provides no global exactly-once guarantee.

On dashboards, separate:

- **SMTP accepted count:** `send` method completed.
- **SENT state commit count:** persisted by the database.
- **Potential duplicate count:** ambiguous outcomes or state conflicts after `send`.

For deliveries in `UNKNOWN` state, a runbook may require reconciling with provider logs/API (if supported) before an operator chooses to retry. Never handle this by “retrying everything until the dashboard is green”.

## 22. Securing metrics, queues, and dead letters

Queues and DLQs can contain email payloads: recipients, subjects, bodies, invoice data, reset tokens, or verification URLs. This data can be sensitive even in internal environments.

**Required safeguards:**

- Grant workers access only to their designated queues/outboxes.
- Enforce RBAC/ACL on broker queues, DLQ topics, databases, and dashboards.
- Encrypt connections between producers, brokers, workers, and databases as required by policy.
- Never put SMTP passwords, OAuth tokens, or email bodies into metric tags.
- Never log the full message when a consumer throws an exception.
- Restrict DLQ read access and redrive permissions.
- Configure retention, archiving, and deletion policies.
- Limit display of email addresses/PII in operational UIs; use opaque IDs and audited lookups.
- Exercise caution when exporting DLQ payloads into support bundles or tickets.
- Audit permission changes and bulk redrive operations.

### 22.1. Metric cardinality

Avoid:

~~~text
mail_retry_total{recipient="alice@example.com",deliveryId="uuid-1"}
mail_retry_total{recipient="bob@example.com",deliveryId="uuid-2"}
...
~~~

Each delivery creates its own time series and can leak PII. Instead use:

~~~text
mail_retry_total{template="order_confirmation",error_code="smtp_timeout"}
mail_retry_total{template="password_reset",error_code="smtp_auth"}
~~~

If template counts are huge or user-defined, normalize/bound categories as well. Balance diagnostic detail against label cardinality.

### 22.2. DLQs must not retain data indefinitely

An email verification token may expire in minutes yet its payload sits in a DLQ for months without a retention policy. Define:

| Data Type | Management Suggestion |
| --- | --- |
| Delivery ID / error code | Retain per audit policy |
| Recipient email | Restrict access, retain only as long as needed |
| Message body / attachment | Omit if unnecessary, encrypt and purge on schedule |
| Verification / password reset token | Keep out of logs/DLQ beyond necessity; use references/expiry |
| Raw exception | Avoid serializing into DB; mask in logs |
| Redrive audit | Retain actor/reason/time per organizational policy |

No single retention day count fits every product; consider security, business needs, and applicable regulations.

## 23. Testing queue, retry, and dead-letter flows

Observability must be tested at two levels:

1. **Actual business state:** does the outbox/broker progress properly, without losing jobs or retrying past policy?
2. **Operational metrics:** do metrics accurately reflect occurred events and do alerts catch key failures?

Do not only test that `meterRegistry.counter(...).increment()` was called. If state-transition logic is wrong, metrics may look clean while real emails fail.

### 23.1. Unit testing retry policy

Suppose a policy classifies transient errors and limits attempts to three:

~~~java
@Test
void transientFailureSchedulesRetryBeforeMaxAttempts() {
    MailRetryPolicy policy = new MailRetryPolicy(
            3,
            Duration.ofSeconds(30),
            Duration.ofMinutes(5));

    FailureDecision failure = new FailureDecision(
            FailureKind.TRANSIENT,
            "SMTP_TIMEOUT",
            "SMTP_CONNECT",
            "Connection timed out");

    RetryDecision result = policy.decide(
            1, failure, Instant.parse("2026-11-12T10:00:00Z"));

    assertThat(result.action()).isEqualTo(NextAction.RETRY);
    assertThat(result.nextAttemptAt())
            .isAfter(Instant.parse("2026-11-12T10:00:00Z"));
}
~~~

`MailRetryPolicy`, `RetryDecision`, and the enums used here are **illustrative application abstractions**, not built-in Spring Mail APIs. Real tests must exercise the implemented policy and verify max attempts, deadlines, and jitter using a fake `Clock` where appropriate.

### 23.2. Integration testing atomic claim and attempt count

With PostgreSQL/Testcontainers:

1. Insert a row with `PENDING, attempt_count=0`.
2. Have two workers attempt to claim concurrently.
3. Verify only one worker claims the row while the lease is valid.
4. Verify `attempt_count=1` and attempt history has exactly one `STARTED` record.
5. Have a fake SMTP server reject temporarily.
6. Verify `status=RETRY` and `next_attempt_at` is in the future.
7. Before that timestamp, workers cannot claim it.
8. Once due, the next attempt increments the counter exactly once.
9. Never use separate `SELECT` followed by `UPDATE` when production requires atomicity.

Run concurrency tests against a **production-compatible database engine**, because H2 or mock repositories may not accurately simulate `FOR UPDATE SKIP LOCKED`, row locking, or transaction isolation.

### 23.3. Testing SMTP accepted + state write failure

Scenario:

~~~text
Fake SMTP accepts message
          |
          v
markSent() throws database exception
          |
          v
Expected:
  - do not immediately resend SMTP
  - record state-write failure / UNKNOWN risk
  - preserve delivery ID and attempt history
  - alert/reconciliation path is available
~~~

This is a critical test for retry/idempotency. Tests that only mock `JavaMailSender` throwing an exception miss the case where **SMTP succeeded while the database update failed**.

### 23.4. Testing max attempts → dead letter

With `max_attempts=3`:

| Attempt | SMTP Outcome | Post-Processing State |
| --- | --- | --- |
| 1 | Temporary failure | RETRY |
| 2 | Temporary failure | RETRY |
| 3 | Temporary failure | FAILED/DLQ |

Assert:

- Counter increments once per claim.
- No automatic attempt #4 is created.
- `terminal_reason=MAX_ATTEMPTS_EXHAUSTED`.
- `last_error_code` remains the real SMTP cause (if classified).
- Dead-letter arrival event is recorded once.
- The DLQ/outbox record retains enough data for operator investigation.

If the first error is permanent, tests can verify an immediate transition to `FAILED` without consuming all attempts.

### 23.5. Testing broker redelivery idempotency

A broker may redeliver a message if a consumer dies before acking. Tests should verify:

- The same business delivery ID does not create multiple outbox rows against policy.
- A worker receiving redelivery does not resend if the delivery is already `SENT` with durable evidence.
- Consumers do not ack before required results are committed.
- Retried messages preserve/restore attempt count and correlation data accurately.
- Repeated DLQ redrives do not spawn uncontrolled duplicate jobs.

Never claim exactly-once just because an integration test receives one message on the happy path. A crash between SMTP acceptance and DB commit can still produce duplicates.

### 23.6. Testing metrics with SimpleMeterRegistry

Micrometer can be tested with `SimpleMeterRegistry`:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

@Test
void recordsRetryAttemptWithBoundedTags() {
    try (SimpleMeterRegistry registry =
                 new SimpleMeterRegistry()) {
        MailDispatchMeters meters = new MailDispatchMeters(registry);

        meters.recordAttemptOutcome(
                "retry",
                "transient",
                "smtp_timeout");

        double count = registry.get("mail.dispatch.attempts")
                .tag("outcome", "retry")
                .tag("failure_kind", "transient")
                .tag("error_code", "smtp_timeout")
                .counter()
                .count();

        assertThat(count).isEqualTo(1.0);
    }
}
~~~

This test verifies the **instrumentation** and tag schema of the helper shown earlier; it does not replace database-state integration tests. Use JUnit 5/AssertJ and import the corresponding classes.

### 23.7. Testing metrics freshness

Suppose the collector exports:

~~~text
ready = 42
snapshotCollectedAt = T1
~~~

Then the database becomes unreachable for 10 minutes. Proper behavior should surface:

~~~text
last ready snapshot = 42 (stale)
snapshot age = 600 seconds
snapshot refresh failures > 0
~~~

Never pretend `ready=0` just because the query failed. Alerts must distinguish **“the queue drained”** from **“the queue is no longer observable”**.

### 23.8. Scenario-based alert testing

Suitable scenarios for integration/staging:

| Scenario | Expected Signal |
| --- | --- |
| Stop workers with 100 due jobs in queue | Ready age rises; no-progress alert |
| Speed up producers beyond consumers | Backlog depth and age grow |
| Widespread SMTP auth failures | Auth failure rate spikes; retries do not storm |
| Prolonged SMTP timeouts | Dispatch duration rises; leases/`UNKNOWN` tracked |
| Template broken for all deliveries | DLQ arrivals for `mime_invalid` surge |
| Consumer dies before ack | Redelivery occurs without losing business delivery |
| Metrics collector loses DB access | Snapshot freshness alert, no fake `queue=0` |
| Operator redrives after fix | Audit event recorded, DLQ drops, accepted rises |

Tests should include timeouts and isolated data. Never send real emails to public recipients just to “induce errors” in automated tests.

## 24. Dashboard walkthrough of a concrete incident

Suppose one morning an SMTP provider temporarily throttles throughput:

~~~text
10:00
  enqueue rate           200 messages/min
  SMTP accepted rate     180 messages/min
  ready depth             80
  retry due               12
  dead letter              0

10:10
  enqueue rate           200 messages/min
  SMTP accepted rate      40 messages/min
  ready depth          1,200
  retry due              300
  oldest ready age         6 min
  error_code=smtp_throttle spike

10:20
  worker rate limit reduced
  backoff with jitter enabled
  SMTP accepted rate      80 messages/min
  retry due              220
  dead letter             10
~~~

**Reading the dashboard:**

- The fault is not in producers, because enqueues are still flowing.
- Ready depth and oldest age rise because throughput fell below arrival rate.
- `retry due` grows because the provider returns transient errors.
- Adding more workers during provider throttling can make the situation worse.
- Newly created dead letters must be categorized: attempt exhaustion or an independent permanent error?
- As long as acceptance rate remains below enqueue rate, the backlog will not drain on its own even if retry counts begin stabilizing.

### 24.1. Post-remediation evaluation

Once quotas increase or the provider recovers:

- `smtp_throttle` error rate drops.
- SMTP accepted rate rises.
- Ready depth steadily declines.
- Oldest ready age drops back below SLO.
- DLQ stops growing.
- Operators handle the remaining 10 dead-lettered deliveries after verifying cause and deadlines.

Do not look solely at rising total sent emails. Check **latency, unfinished work, and terminal failures** before declaring recovery.

## 25. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Measuring only queue depth | Misses workers hung in-flight | Monitor in-flight, oldest age, throughput |
| Summing DB-wide gauges from every replica | Multiplies backlog by N on dashboards | Use one authoritative collector or proper aggregation |
| Treating scheduled retries as attempted retries | Inflates reported send attempts | Separate scheduled/started/finished |
| Incrementing retry count only in `catch` | Crashes before `catch` go uncounted | Increment attempt count in claim transaction |
| Retrying every exception infinitely | Overloads SMTP, risks duplicates | Classifier, backoff, max attempts |
| Dead-lettering without saving `last_error_code` | No triage information | Record error code, stage, terminal reason |
| Merging transient errors + max attempts as permanent | Obscures real root cause | Separate failure kind from terminal reason |
| Confusing SMTP accepted with inbox delivered | Inaccurate delivery reporting | Separate submission from delivery feedback |
| Acking broker before saving results | Crashes can lose jobs | Follow durable ack/transaction contract |
| Immediately requeuing every nack | Hot loop, broker/SMTP overload | Delay/backoff/DLX |
| No leases/fencing | Concurrent duplicate sends, state races | Atomic claim + claim token/version |
| Redriving entire DLQ blindly | Sends expired emails or bad recipients | Eligibility, suppression, audit, rate limit |
| Using raw exceptions as tags | High cardinality, PII leakage | Finite error taxonomy |
| Setting gauge=0 when metrics query fails | Falsely reports empty queue | Mark stale and increment refresh failure metric |
| Deleting `FAILED` rows to zero dashboards | Loses audit trail without fixing incident | Structured retention/triage/redrive |
| Scaling workers regardless of provider quota | Causes more rate limits and retry storms | Rate limiter, circuit breaker, backpressure |

## 26. Frequently asked questions

**“Does Spring Framework Mail include a built-in queue and DLQ?”**  
No. `JavaMailSender` is an email-sending API. Queues/retries/DLQs are typically implemented by the application via a database outbox or integrated with a message broker such as RabbitMQ or Kafka. Broker libraries provide their own features; do not confuse them with Spring Mail.

**“Does queue depth = 0 mean all emails were sent?”**  
No. Jobs could be `PROCESSING`, waiting for retry in another queue, sitting in a DLQ, or lost due to premature acks. Inspect in-flight, delayed, failed, producer activity, and completion state.

**“Should alerts target queue depth or queue age?”**  
Usually both. Queue depth shows volume; oldest ready age directly reflects emails waiting too long. Looking only at depth can miss a single starved old job; looking only at age without throughput makes scaling decisions hard.

**“Should retry count start at 0 or 1?”**  
Either convention works if consistent. An intuitive model starts `attempt_count=0` before processing, increments to `1` on first claim, and computes retries used as `max(attempt_count-1,0)`. Never mix meanings across modules.

**“Why are scheduled retries higher than started retries?”**  
Jobs may still be waiting in backoff, not yet due, canceled, moved to DLQ, or waiting for worker capacity. Scheduled is a future decision; started is an execution actually begun.

**“Should `MailSendException` always be retried?”**  
No. `MailSendException` can wrap transient errors, permanent errors, or uncertain outcomes. Inspect the nested cause, SMTP code, failure stage, and provider policy.

**“Should SMTP authentication errors be retried immediately?”**  
Usually no. If passwords or permissions are wrong, repeating with the same credentials will not fix the error and can trigger account lockouts or provider throttling. Fix/rotate credentials first and then redrive.

**“If an email times out, is it definitely unsent?”**  
No. If a timeout occurs after message `DATA` reaches the relay, the server may have accepted it while the client missed the final reply. Retrying risks duplicates; apply `UNKNOWN`/reconciliation policy.

**“Why were there three retries yet `attempt_count` equals four?”**  
Because the initial attempt is not a retry; three retries plus the initial attempt equal four dispatch executions. Name fields clearly and explain this to dashboard readers.

**“Must a dead letter be a physical queue?”**  
No. In a database outbox, `status=FAILED` or a dead-letter table can act as the terminal store. In a broker, the DLQ can be a separate queue or topic. Both stop automatic retries and retain data for investigation.

**“Should a `FAILED` message be deleted right away?”**  
Not if you need auditing, redrive, or investigation. Archive or purge according to retention policy, never just to make dashboards look clean.

**“When does a job transition from `RETRY` to `DEAD LETTER`?”**  
When policy stops retries: permanent error, max attempts exhausted, business deadline expired, or operator cancellation. Store `terminal_reason` separately from error code.

**“Should the entire DLQ be redriven right after fixing an SMTP password?”**  
Not automatically. Filter to jobs that failed from that cause, check expiration, suppression, and payload/recipient validity. Redrive with rate limiting and auditing.

**“Should the delivery ID stay the same on retry?”**  
Usually yes when it remains **the same send request**. Attempt IDs or claim tokens change per attempt, while the delivery/business idempotency key stays stable. If issuing a legitimate new send request, link its origin for auditability.

**“Does RabbitMQ `x-death` equal total SMTP send attempts?”**  
No. It reflects broker dead-lettering mechanics, not actual `JavaMailSender.send` executions. Track business attempt counts separately if needed.

**“Does Kafka have queue depth like RabbitMQ?”**  
Kafka is typically monitored via consumer lag/offsets per topic and partition. With retry/DLQ topics, monitor each stream; never sum all offsets and call it unsent emails without a clear model.

**“Should I add workers when the queue backlog is high?”**  
Only after confirming worker capacity is the bottleneck. If the SMTP provider is throttling throughput, adding workers can cause more errors. Check provider quotas, send durations, error rates, and CPU/threads first.

**“Why do queue metrics and database queries disagree?”**  
Because of different snapshot timestamps, a job existing across multiple layers, process-local counter resets, or dashboards double-summing global gauges across replicas. Align scopes and sampling.

**“Should delivery IDs be added as Prometheus tags?”**  
No. That creates huge time-series cardinality and can expose sensitive info. Delivery IDs belong in access-controlled structured logs/traces; metrics should use bounded tags like template category, provider, and error code.

**“Does outbox `SENT` mean the email landed in the inbox?”**  
Not if `SENT` means SMTP accepted. Bounces, spam filtering, recipient mailboxes, and provider delivery feedback belong to a separate deliverability layer.

**“Should we alert whenever a single job enters the DLQ?”**  
It depends on email type and impact. One bad address can be an isolated error; a sudden DLQ surge from authentication or template failures requires higher-severity alerting.

**“How do you distinguish a dead worker from a slow worker?”**  
Combine heartbeats, last progress timestamp, in-flight count, lease expirations, SMTP timeouts, and trace durations. A ticking heartbeat alone does not prove forward progress.

**“Should tripping a circuit breaker mark jobs as `FAILED`?”**  
Not by default. A circuit breaker signals a temporary pause in calling the provider due to systemic errors, not that individual deliveries are permanently undeliverable. Usually keep jobs waiting/retrying with backoff.

**“If DB monitoring fails, should dashboards display queue depth = 0?”**  
No. Treat the data as stale, alert on collector failures, and distinguish unobservability from a genuinely empty queue.

**“After a redrive, should `attempt_count` be reset to 0?”**  
Never silently reset if auditing matters. Open a new retry cycle or create a linked delivery; preserve prior history and record operator/reason.

## 27. Implementation checklist for mail queue observability and operations

### State definitions

1. Choose the source of truth for deliveries: database outbox, broker, or hybrid.
2. Define `PENDING`, `PROCESSING`, `RETRY`, `SENT`, `FAILED`, and `UNKNOWN` where applicable.
3. Distinguish enqueue, claim, SMTP accepted, state committed, and provider delivered.
4. Define attempt count and retry count consistently.
5. Enforce atomic claims and leases/fencing tokens for multi-worker setups.

### Queue dashboard

6. Track ready, delayed, in-flight, expired lease, and terminal counts.
7. Separate oldest ready age from oldest unfinished age.
8. Track enqueue, claim, and completion rates.
9. Track SMTP duration, queue wait, and total time.
10. Know whether each gauge is per-instance, per-queue, or database-wide to avoid double counting.
11. Monitor metric freshness and collector error rates.

### Retry

12. Store attempt history and normalized error codes.
13. Classify transient/permanent/unknown rather than inspecting only exception class names.
14. Implement durable backoff, jitter, max attempts, deadlines, and retry scheduling.
15. Track retry scheduled, started, and exhausted separately.
16. Avoid aggressive retries on auth errors or provider throttling.
17. Establish a reconciliation policy for uncertain SMTP outcomes.

### Dead letter

18. Provide storage for terminal jobs along with reasons and history.
19. Track DLQ depth, arrivals, oldest age, and terminal reasons.
20. Never drop messages on consumer crashes or premature acks.
21. Maintain triage runbooks and role-authorized redrive workflows.
22. Enforce suppression, deadline, idempotency, and rate limits during redrives.
23. Record actor/time/reason audit entries on redrive.
24. Apply retention and protect sensitive data inside DLQs.

### Testing and operations

25. Test SMTP success, transient/permanent errors, max attempts, and timeouts.
26. Test concurrency, lease expiry, broker redelivery, and crash windows.
27. Test SMTP success followed by database state-update failure.
28. Test alerts for stalled workers and queue age breaching SLOs.
29. Verify metrics do not leak recipients/secrets or create high-cardinality tags.
30. Establish clear dashboard and escalation ownership for queues/DLQs.

## 28. Complete observability architecture

~~~text
                     Business service
                           |
                           v
                    Outbox / broker
                    PENDING / ready
                           |
                +----------+-----------+
                |                      |
                v                      v
        Queue snapshots          Broker telemetry
        depth + age              ready/unacked/lag
                |                      |
                +----------+-----------+
                           |
                           v
                        Worker
                           |
                  +--------+--------+
                  |                 |
                  v                 v
             JavaMailSender     Error classifier
                  |                 |
            +-----+-----+     +-----+------+
            |           |     |            |
            v           v     v            v
      SMTP accepted   Unknown RETRY       FAILED/DLQ
            |           |     |            |
            v           v     v            v
      SENT state   Reconcile Next time  Triage/redrive
            |           |     |            |
            +-----------+-----+------------+
                            |
                            v
                  Durable state + attempt history
                            |
                            v
                  Micrometer / Prometheus
                            |
                    +-------+---------+
                    |                 |
                    v                 v
                 Grafana          Alert manager
                    |                 |
                    v                 v
             On-call dashboard   Runbooks / tickets
~~~

### Principles to remember

- Queue depth must be paired with **queue age, throughput, in-flight counts, and worker progress**.
- Retry count is not merely an error count; distinguish **attempt, retry scheduled, and retry started**.
- A dead letter is where **stopped failures are held for action**, not a trash bin to purge unconditionally.
- Metrics are operational signals; **outbox/attempt history and broker state** remain the durable evidence for reconciliation.
- For SMTP, a normal `send` return only proves transport acceptance from the app's perspective, **not inbox delivery**.
- Retries can create duplicates if SMTP accepts a message before the database commits `SENT`.
- Alerts must tie to SLOs and clear actions, not just cosmetic numbers.
- Logs, metrics, and DLQs must be protected against leaking email addresses, message bodies, and credentials.

## Conclusion

**Monitoring queues, retry counts, and dead letters** is foundational to reliably operating an asynchronous email-sending system with Spring Framework Mail. Queues show pending work and forward progress; retry counts and attempt history explain why sends failed; dead letters retain unrecoverable deliveries so operators can remediate safely.

An effective solution combines **durable state, well-defined metrics, correlation-ID logs/traces, latency-based alerts, and retry/DLQ runbooks**. With those in place, the application not only sends email when everything works smoothly, but also detects issues early, explains root causes, and recovers under control when SMTP, workers, databases, or brokers fail.
