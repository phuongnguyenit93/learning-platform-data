# Evaluating Scalability and Limits of the Project

## 1. Practice Lesson Goals

In earlier lessons on **Spring Framework Mail**, we often judged functionality by asking: "Can the application send an email?" When completing a **practice project**, that question is no longer enough. A system can send 10 emails cleanly in development yet struggle under 10,000 concurrent requests, large PDF attachments, three running pods, or several minutes of SMTP provider throttling.

The goal of this lesson is to **evaluate a Spring Boot / Spring Mail sending project with technical evidence**, answering:

- What traffic volume can the project handle **within acceptable latency**?
- Are limits imposed by application code, memory, database, worker count, or the SMTP provider?
- When backlogs grow, does the project lose work or send duplicate emails?
- Does one high-volume tenant starve other tenants?
- How do large attachments or multi-recipient emails impact heap memory and quotas?
- When a provider slows down, disconnects, or lowers limits, how does the application recover?
- Does the system have enough metrics, logs, and persisted states to explain failures?
- As load grows, what should be optimized first, and which **limits must be accepted**?

The expected deliverable is not a vague claim like "the system is scalable", but a **report documenting assumptions, measurement methodology, numbers, observed bottlenecks, and an upgrade roadmap**.

> **Illustrative scope:** This lesson uses a reference Spring Boot project generating business emails, building MIME with `MimeMessageHelper`, sending via `JavaMailSender`, and optionally using a transactional outbox and worker. It is a reference model for learners to apply to their own practice projects, **not benchmark results from an actually executed repository**. All numbers in examples are hypothetical assumptions or illustrative calculations, not verified measurements.

## 2. Defining "Scalable" Before Measuring

Scalability means a system can increase useful work when adding resources or improving architecture **within explicit bounds** on latency, reliability, cost, security, and provider limits.

Distinguish these dimensions:

| Property | Question |
|---|---|
| **Throughput** | How many emails/recipients per second or minute are accepted by the provider? |
| **Latency** | How long from creating an intent until sending starts or SMTP accepts? |
| **Capacity** | For the current workload and SLO, what maximum request/job rate is sustainable? |
| **Burst tolerance** | How long can the system absorb sudden spikes before backlogs lose control? |
| **Elasticity** | Does scaling workers up/down improve throughput while honoring quotas? |
| **Reliability** | Do failures drop intents, duplicate attempts, or strand jobs? |
| **Recovery** | How fast does the system drain backlogs after an outage? |
| **Fairness** | Are low-volume tenants or urgent mail types starved by bulk campaigns? |
| **Operational scalability** | Does growing scale make incident investigation and support impossible? |
| **Cost efficiency** | What is DB/Redis/worker/provider/observability cost per useful unit? |

Never confuse:

- **HTTP requests returning `202 Accepted`** with SMTP messages actually submitted.
- **SMTP accepted** with emails landing in the recipient's Inbox.
- **Thread counts** with emails/second.
- **Messages** with **SMTP envelope recipients**.
- **Pushing a job to Redis/a queue** with guaranteeing exactly-once delivery.

A rigorous evaluation names every milestone and measurement unit precisely.

## 3. Reference Project Models and Measurement Boundaries

A Spring Mail practice project typically follows one of two architectures.

### Option A: Synchronous Sending

~~~text
HTTP request
    |
    v
Spring Controller
    |
    v
Business/Notification Service
    |
    v
MimeMessageHelper + JavaMailSender
    |
    v
SMTP provider
    |
    v
HTTP response
~~~

Simple and easy to demo, yet requests hold threads/connections until the SMTP call finishes or times out. If SMTP slows down, web thread pools and response latency suffer directly.

### Option B: Durable Intent Ingestion, Asynchronous Sending

~~~mermaid
flowchart TD
    A[Business operation or API] --> B[Validate intent and authorization]
    B --> C[Commit business data + mail outbox]
    C --> D[Return queued notification ID]
    C --> E[Due-job scheduler]
    E --> F[Atomic claim and eligibility]
    F --> G[Rate / concurrency gate]
    G --> H[Create MIME and SMTP submit]
    H --> I[Persist outcome and attempts]
    I --> J[Metrics / audit / status query]
    H --> K[Provider feedback if available]
    K --> J
~~~

Option B decouples HTTP response time from SMTP, at the cost of needing a database/outbox, scheduler/workers, ownership, retries, and backlog alerts. **Going asynchronous does not increase your provider's quota**; it mainly smooths load, reduces coupling, and improves recovery.

If your project sends synchronously today, you can still evaluate all its limits. Outbox sections here present an **expansion path**, without assuming every project already built one.

### Components Inside Evaluation Scope

| Component | Responsibility | Signals to Observe |
|---|---|---|
| API/application | Auth, creating notification intents | Request rate, latency, errors, idempotency |
| Template/renderer | Rendering text/HTML, generating PDFs | CPU, memory, render latency |
| Outbox/database | Persisting durable state | Insert/claim latency, backlog, locks |
| Dispatcher | Selecting jobs and coordinating | Claim rate, age, in-flight jobs |
| Rate limiter | Protecting account/tenant quotas | Permits, denials, wait time |
| SMTP adapter | Building and submitting MIME | Connect/read/write latency, accepts, rejects |
| SMTP provider | Accepting and relaying mail | Published quotas, throttling, traces |
| Delivery feedback | Bounces/delivery when available | Event delay, dedup, state updates |
| Operations | Metrics, tracing, logs, recovery | Time to detect/recover, alert quality |

## 4. Before Measuring: Inventory Capacity and Constraints

An evaluation report can start with a baseline table:

| Question | Data to Collect |
|---|---|
| How many Spring Boot replicas? | Pod/process count, CPU/memory limits |
| How many SMTP workers per replica? | Executor size, queue capacity, in-flight limits |
| Which mail formats are used? | `SimpleMailMessage` vs. `MimeMessage`, HTML, attachments |
| Which SMTP provider? | Host/API route, actual contractual limits |
| One account or multiple accounts? | Quota scope shared across credentials |
| What unit does the provider meter? | Messages, recipients, daily recipients, connections |
| How large are messages? | P50/P95/P99 attachment and payload bytes |
| Sync send or outbox? | API contract and persistence state |
| Which DB or broker? | PostgreSQL/MySQL/Redis/RabbitMQ, durability guarantees |
| How do tenants send? | Service tiers, traffic distribution, burst profiles |
| Where do retries happen? | Worker, interceptor, scheduler, provider |
| Are duplicates checked? | Business idempotency keys, attempt history |
| Are delivery webhooks available? | Ability to observe delivered/bounced states |

Actual facts must come from the evaluated project's own configuration and telemetry. **Never guess SMTP quotas from a provider's brand name**; limits vary by account, plan, reputation, region, and policy.

### Assumptions Sheet Template

~~~text
Project/version      : mail-practice / git revision ...
Environment          : staging, isolated
Date/time range      : ...
App replicas         : ...
CPU/RAM per replica  : ...
DB / broker          : ...
Provider/sink        : ...
Account quota scope  : ...
Rate units           : messages/s + recipients/day
Message mix          : 80% text, 15% HTML, 5% PDF
Avg recipients/msg   : ...
Payload size P95     : ...
Warm-up time         : ...
Observation window   : ...
Data privacy         : synthetic recipients/content only
~~~

Document assumptions upfront so readers understand why the same system performs differently on a laptop vs. staging.

## 5. Describing Workloads by Load Shape, Not Just Daily Totals

Two projects sending 100,000 emails/day can experience vastly different loads:

~~~text
Workload A:
  100,000/day distributed evenly
  ~1.16 messages/s on average

Workload B:
  100,000/day
  80,000 submitted over a 10-minute campaign window
  ~133.33 messages/s during the burst
~~~

If a provider account permits only 20 messages/s, Workload B **cannot finish submitting within 10 minutes** on that account even with 100 worker threads. You must adjust schedules, raise approved quotas, or distribute across policy-compliant routes.

Dimensions to model:

1. **Arrival rate:** requests/second or jobs/second.
2. **Peak factor:** burst ratio relative to average.
3. **Message mix:** plain text, HTML, multiple attachments.
4. **Recipient fan-out:** 1, 10, or 100 recipients per message.
5. **Payload distribution:** P50/P95/P99 byte sizes, not just averages.
6. **Tenant distribution:** one dominant tenant vs. balanced tenants.
7. **Priority:** OTP/transactional vs. marketing/bulk.
8. **Schedule:** many jobs sharing one `scheduled_at` vs. staggered.
9. **Failure mix:** temporary rejections, auth outages, timeouts.
10. **Recovery pattern:** backlog drain after restarts or rolling deploys.

### Building Representative Test Datasets

~~~text
Small transactional:
  1 recipient, text+HTML, no attachment

Medium transactional:
  1 recipient, PDF 300 KiB

Large report:
  1 recipient, XLSX 8 MiB

Multi-recipient:
  20 envelope recipients in one message

Bulk tenant:
  5,000 messages arriving almost simultaneously
~~~

These sizes and ratios are illustrative fixture patterns. Never use real customer data or production SMTP accounts in load tests.

## 6. Defining SLIs and SLOs Before Benchmarking

An **SLI** (*Service Level Indicator*) is a measured quantity; an **SLO** (*Service Level Objective*) is the target set for that SLI over a window.

For mail systems, track multiple timestamps:

~~~text
intentCreatedAt
     |
     v
outboxCommittedAt
     |
     v
attemptStartedAt
     |
     v
submittedAt (if SMTP accepted)
     |
     v
deliveredAt (only if trustworthy event exists)
~~~

| SLI | Formula / Definition | Interpretation |
|---|---|---|
| API accept latency | `responseAt - requestAt` | How long clients wait to enqueue |
| Queue delay | `attemptStartedAt - scheduledAt` | Delay from eligible time until attempt starts |
| SMTP submission latency | `smtpCallCompletedAt - smtpCallStartedAt` | Transport call duration |
| End-to-submission | `submittedAt - intentCreatedAt` | Total time until provider accepts |
| Due backlog age | `now - scheduledAt` for due jobs | Age of the oldest overdue job |
| Acceptance ratio | accepted attempts / definitive attempts | Submission health (keep UNKNOWN separate) |
| Expiry ratio | expired jobs / eligible jobs | Notifications rendered useless by delay |
| Duplicate intent rate | duplicate business intents / total intents | Effectiveness against request/event retries |

Illustrative **hypothetical** targets:

~~~text
Transactional:
  99% eligible jobs begin SMTP attempt <= 30 seconds
  after scheduledAt (under stated provider quota condition).

Bulk:
  95% jobs begin SMTP attempt within agreed campaign window.

Reliability:
  No durable mail intent lost during application restart test.
~~~

Never assume "SMTP `send()` threw no exception" equals *delivered*. `JavaMailSender` is an outbound submission API; inbox delivery depends on the provider and receiving domain. Without trustworthy delivery events, do not claim SLOs like "99.9% in Inbox within 5 seconds" as measured fact.

### Stating SLO Conditions Explicitly

A meaningful SLO specifies:

- Which traffic classes count.
- Evaluation window (e.g., 7 days).
- Exact start and end timestamps.
- Whether unscheduled, user-cancelled, or consent-revoked jobs are excluded.
- Whether provider quota exhaustion is excluded, and if stakeholders agreed.
- Data sources and sampling rates.

If you exclude every outage and quota denial from your SLO, numbers look great on paper while hiding user pain.

## 7. Converting Request Rate, Message Rate, and Recipient Rate

This is one of the easiest places to miscalculate when sizing a mail project.

Suppose each notification intent generates a set of SMTP messages. Let:

- `λ`: notification intents/second.
- `m`: average SMTP messages per intent.
- `r`: average envelope recipients per message.

Then:

\[
\text{messageDemandPerSecond} = \lambda \times m
\]

\[
\text{recipientDemandPerSecond}
 = \lambda \times m \times r
\]

If:

~~~text
lambda = 12 intents/s
m      = 1 SMTP message/intent
r      = 3 recipients/message
~~~

then:

~~~text
message demand   = 12/s
recipient demand = 36/s
~~~

If the provider caps at 20 recipients/s, the bottleneck is **recipient quota**, not message count. Bcc recipients also count as envelope recipients. When providers enforce multiple quota dimensions, convert every limit into its **exact metered unit** before estimating capacity.

**Note:** `m` and `r` are averages for planning; for per-job admission control, use the job's **actual cost** rather than rounding to averages.

## 8. Capacity Model: The Bottleneck Sets Sustainable Throughput

For a workload with one recipient per message, an initial upper bound is:

\[
\mu_{\mathrm{effective}}
 \le \min(\mu_{\mathrm{app}},
         \mu_{\mathrm{DB}},
         \mu_{\mathrm{provider}},
         \mu_{\mathrm{quota}})
\]

Where:

- `μapp`: messages/second the application can prepare and submit.
- `μDB`: jobs/second the database/outbox can claim and update.
- `μprovider`: provider/transport processing capacity.
- `μquota`: account, tenant, or recipient rate limits.

This is a **simple ceiling model**, not an exact predictor. With multi-recipient fan-out, normalize units first; with multiple provider accounts, total capacity also depends on routing permissions, global quotas, and load balance.

Illustrative example:

| Component | Assumed Capacity |
|---|---:|
| Template + MIME rendering | 180 messages/s |
| Database claim + status persistence | 95 jobs/s |
| SMTP adapter at configured concurrency | 45 messages/s |
| Provider account safe rate | 30 messages/s |
| Tenant aggregate policies | 27 messages/s |

Assuming 1 job = 1 message and 1 recipient, the initial ceiling is:

\[
\min(180,95,45,30,27)=27\ \text{messages/s}
\]

Adding CPU to boost rendering from 180 to 400/s **does nothing to raise the 27/s ceiling**. Examine quota/tenant distribution or workflows before scaling app pods.

### Real Throughput Can Fall Below the Ceiling

Variance in latency, connection handshakes, mixed job costs, large attachments, head-of-line blocking, retries, quotas, GC pauses, DB lock contention, fairness policies, and reserved capacity all drag down actual throughput. **A theoretical ceiling is a hypothesis to test**, never a measured benchmark.

## 9. Little's Law and Estimating In-Flight Work

In a stable system with consistent boundaries:

\[
L = \lambda W
\]

Where:

- `L`: average jobs inside a pipeline stage.
- `λ`: actual throughput through that stage (jobs/second).
- `W`: average residence time in that stage (seconds).

For example, if SMTP calls average 0.4 seconds and steady throughput is 20 submissions/second:

\[
L = 20 \times 0.4 = 8\ \text{in-flight submissions}
\]

That implies roughly 8 concurrent operations **on average**, plus headroom for tail latency, CPU scheduling, TLS setup, and network jitter. Never set concurrency = 8 and expect a guaranteed 20/s.

### When the Queue Is Unstable

If:

~~~text
Arrival demand = 40 jobs/s
Accepted service rate = 25 jobs/s
~~~

backlog grows at roughly:

\[
\Delta Q / \Delta t \approx 40-25=15\ \text{jobs/s}
\]

After 10 minutes at steady rates (ignoring expiry or cancellations):

\[
Q \approx 15 \times 600 = 9000\ \text{jobs}
\]

**Never blindly apply Little's Law to an unboundedly growing queue**; its steady-state assumption does not hold. For bursts, analyze accumulation and drain phases separately.

## 10. Estimating Post-Incident Backlog Drain Time

Suppose the SMTP provider goes down for 20 minutes while the app keeps ingesting 10 jobs/s. Backlog can grow to:

\[
10 \times 20 \times 60=12\,000\ \text{jobs}
\]

When the provider recovers:

~~~text
New demand         = 10 jobs/s
Safe send capacity = 25 jobs/s
Net drain rate     = 15 jobs/s
Backlog            = 12,000 jobs
~~~

Estimated drain time:

\[
t_{\mathrm{drain}}
=\frac{12\,000}{25-10}=800\ \text{s}
\]

or about 13 minutes and 20 seconds, **assuming no daily quota exhaustion, retries, job expirations, or demand shifts**.

In practice, daily quotas can run dry before the backlog clears; providers may throttle burst drains; and bulk vs. transactional lanes follow distinct policies. Drain forecasts therefore require **quota windows, job cost, and priority**—not merely dividing jobs by worker count.

### Why a Large Backlog Does Not Always Mean "Add More Workers"

If the provider caps at 25/s and workers already hit 25/s, adding replicas does not raise accepted throughput. Instead, it increases DB claim contention, Redis rate-gate calls, open SMTP sockets, and expired leases when workers claim more jobs than they can send.

Scale workers only when evidence proves **valid provider capacity remains unused** and the bottleneck truly sits in worker CPU or concurrency.

## 11. Limits of Synchronous Sending Designs

With a controller calling SMTP directly:

~~~java
@PostMapping("/send")
public ResponseEntity<String> sendMail(
        @RequestBody MailRequest request) {
    mailService.send(request);
    return ResponseEntity.ok("submitted");
}
~~~

Request/response lifetime couples directly to SMTP duration.

Example:

~~~text
50 concurrent web threads
SMTP call latency = 2 seconds
~~~

With no other bottlenecks, concurrency caps throughput at:

\[
\text{theoretical rate} \approx \frac{50}{2}
=25\ \text{requests/s}
\]

This is an illustrative calculation omitting overhead and tail latency. If SMTP latency climbs to 10 seconds, the same thread pool handles ~5 requests/s while queued requests stall or time out.

### Consequences During an SMTP Outage

- HTTP latency spikes and web threads tie up.
- Other endpoints sharing the same web/executor pool can stall.
- Clients time out and retry, creating duplicate business intents.
- Database transactions stay locked if sending runs inside `@Transactional`.
- API responses may claim "email failed" even when provider outcome is uncertain.

### When Is Synchronous Sending Still Reasonable?

Low-traffic internal tools with no coupled business DB transaction, needing immediate SMTP submission feedback and tolerating latency, can use direct sends—provided they enforce timeouts, concurrency bounds, authorization, acceptance-vs.-delivery clarity, and keep DB transactions closed across SMTP.

## 12. Asynchronous Sending with a Durable Outbox

A common improvement:

~~~text
POST /notifications
        |
        v
Validate + store mail intent in DB
        |
        v
Return HTTP 202 Accepted
        |
        v
Scheduler/worker polls due jobs
        |
        v
Acquire ownership and quota permit
        |
        v
JavaMailSender.send(...)
        |
        v
Persist submission outcome
~~~

### Benefits

- HTTP responses do not wait on SMTP.
- Unprocessed jobs survive worker restarts when stored durably.
- Retries honor backoff and deadlines, with queryable status for support.
- Web replicas scale independently from mail workers.
- Supports transactional vs. bulk lanes, quotas, and tenant fairness.

### New Costs

- Requires a database/broker, scheduler/dispatcher, and transactional consistency.
- Requires ownership, leases, and attempt state tracking.
- Requires retention policies, schema migrations, and cleanup.
- Requires backlog metrics and alerts to catch stuck queues.
- APIs must communicate `QUEUED` rather than `DELIVERED`.
- Introduces eventual consistency: users see "accepted for delivery" before SMTP submission runs.

**Never write `@Async void send(...)` and call it an outbox.** An in-memory executor loses queued jobs on crashes or redeploys.

## 13. Transactional Outbox Prevents Losing Intents in Business Transactions

Wrong:

~~~java
@Transactional
public void completeOrder(OrderId orderId) {
    orders.markCompleted(orderId);
    sender.send(buildReceipt(orderId));
}
~~~

SMTP does not roll back with the database. If SMTP accepts and the DB rolls back, an invalid email goes out; an SMTP timeout holds DB locks too long.

A better pattern when sharing a database:

~~~text
BEGIN
  UPDATE orders SET status='COMPLETED'
  INSERT INTO mail_outbox (
      id, business_key, status, scheduled_at, ...
  ) VALUES (...)
COMMIT

Worker:
  select due jobs
  submit SMTP outside business transaction
  update outcome in short transaction
~~~

Contract example:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class OrderCompletionService {
    private final OrderRepository orders;
    private final MailOutboxRepository outbox;

    public OrderCompletionService(
            OrderRepository orders,
            MailOutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void completeOrder(OrderId id) {
        Order order = orders.complete(id);
        outbox.insertIfAbsent(
                MailIntent.forCompletedOrder(
                        order.id(),
                        order.customerId(),
                        order.version()));
    }
}
~~~

`OrderRepository`, `OrderId`, `MailOutboxRepository`, and `MailIntent` are illustrative abstractions, not built-in Spring Mail APIs. `insertIfAbsent` needs a unique constraint/UPSERT on the business event key to prevent races under retried requests.

If business data and the outbox live in separate databases, plain `@Transactional` does not provide cross-store atomicity. Use a local outbox beside the business DB, CDC, or a durable handoff/reconciliation design.

## 14. Outbox Schema and Indexes Needed When Scaling

Illustrative PostgreSQL schema:

~~~sql
CREATE TABLE mail_outbox (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    notification_type VARCHAR(80) NOT NULL,
    provider_account_id VARCHAR(100) NOT NULL,
    business_key VARCHAR(180) NOT NULL,
    payload_ref VARCHAR(255) NOT NULL,
    recipient_count INT NOT NULL
        CHECK (recipient_count > 0),
    status VARCHAR(24) NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ,
    attempt_count INT NOT NULL DEFAULT 0,
    claim_token UUID,
    lease_until TIMESTAMPTZ,
    submitted_at TIMESTAMPTZ,
    last_error_code VARCHAR(80),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT uq_mail_business_intent UNIQUE
        (tenant_id, business_key),
    CONSTRAINT chk_mail_status CHECK (status IN (
        'PENDING', 'CLAIMED', 'PROCESSING',
        'RETRY', 'SUBMITTED', 'FAILED',
        'CANCELLED', 'EXPIRED', 'UNKNOWN'
    )),
    CONSTRAINT chk_attempt_count CHECK (attempt_count >= 0)
);

CREATE INDEX idx_mail_outbox_due
    ON mail_outbox (available_at, id)
    WHERE status IN ('PENDING', 'RETRY');

CREATE INDEX idx_mail_outbox_lease
    ON mail_outbox (lease_until)
    WHERE status IN ('CLAIMED', 'PROCESSING');
~~~

Depending on workload, you may add indexes on `provider_account_id`, tenant, lane, or priority; never add every possible index just from an example, since each index adds INSERT/UPDATE write overhead.

### What Can Be Observed from the Table?

- `status`: current stage of the job.
- `scheduled_at`: when business logic wanted the email sent.
- `available_at`: earliest eligible time after quota deferral or retry backoff.
- `attempt_count`: how many submissions actually started per contract.
- `claim_token`/`lease_until`: temporary worker ownership.
- `submitted_at`: when provider accepted per adapter semantics.
- `last_error_code`: normalized failure code without raw SMTP diagnostics.

Never populate `submitted_at` on intent creation, and never equate `submitted_at` with delivered.

## 15. Multi-Worker Claiming Must Never Be Just SELECT Then Send

Once a project runs two replicas, this pattern:

~~~sql
SELECT id FROM mail_outbox
WHERE status = 'PENDING'
  AND available_at <= CURRENT_TIMESTAMP;
~~~

followed by sending SMTP can cause two workers to **read and send the exact same job**. Scaling from 1 to 10 workers without ownership does not double useful throughput—often it just multiplies duplicate emails.

With PostgreSQL, claim atomically in a short transaction:

~~~sql
WITH chosen AS (
    SELECT id
    FROM mail_outbox
    WHERE status IN ('PENDING', 'RETRY')
      AND scheduled_at <= CURRENT_TIMESTAMP
      AND available_at <= CURRENT_TIMESTAMP
      AND (expires_at IS NULL
           OR expires_at > CURRENT_TIMESTAMP)
    ORDER BY available_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE mail_outbox AS job
SET status = 'CLAIMED',
    claim_token = :claim_token,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '2 minutes',
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
FROM chosen
WHERE job.id = chosen.id
RETURNING job.id, job.claim_token;
~~~

After committing the claim, run SMTP outside the transaction; then persist the outcome conditionally:

~~~sql
UPDATE mail_outbox
SET status = 'SUBMITTED',
    submitted_at = CURRENT_TIMESTAMP,
    claim_token = NULL,
    lease_until = NULL,
    updated_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE id = :id
  AND claim_token = :claim_token
  AND status = 'PROCESSING'
RETURNING id;
~~~

If 0 rows update, the worker lost ownership or state changed; never drop the token condition to force a write.

### Limitations of SKIP LOCKED

- Prevents workers from claiming the same row **inside the claim transaction**.
- Does not guarantee strict FIFO or tenant fairness.
- Does not merge DB and SMTP into a single atomic transaction.
- Does not stop duplicates caused by a crash **after provider acceptance**.
- Can incur scanning cost when table size and poll frequency grow large.

Benchmark actual query plans and indexes before raising batch sizes or poll rates. Oversized batches leave claimed jobs idling in memory until their leases expire.

## 16. State Machine and Retries Must Be Explicit to Measure Reliability

A workflow might look like:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> CLAIMED: due and claim
    PENDING --> CANCELLED: user cancel
    PENDING --> EXPIRED: deadline
    CLAIMED --> PROCESSING: attempt recorded
    CLAIMED --> PENDING: released before send
    PROCESSING --> SUBMITTED: SMTP accepted
    PROCESSING --> RETRY: definitive temporary rejection
    PROCESSING --> FAILED: definitive permanent failure
    PROCESSING --> UNKNOWN: ambiguous provider outcome
    RETRY --> CLAIMED: backoff elapsed
    RETRY --> EXPIRED: deadline
    UNKNOWN --> SUBMITTED: provider reconciliation
    UNKNOWN --> RETRY: explicit approved retry policy
~~~

State names are **application-defined enums**; Spring Mail does not manage this lifecycle.

During scale testing, measure:

- Average attempts per job.
- Rates of `RETRY`, `FAILED`, and `UNKNOWN`.
- Jobs returned to `PENDING` or `UNKNOWN` due to lease expiry.
- Stale-worker finalizations rejected by fencing.
- Any jobs stuck in `CLAIMED`/`PROCESSING` past expected timeouts.
- Whether max retries and expiry deadlines enforce correctly per mail type.

**High `SUBMITTED` counts alone do not prove reliability** if jobs are duplicated or stuck retrying forever.

### Backoff and Jitter

For temporary failures, e.g.:

\[
d_n = \min(d_{\max},d_0 2^{n-1})
\]

then apply jitter so 10,000 failed jobs do not wake up on the exact same second:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ThreadLocalRandom;

public final class RetryPlanner {
    private RetryPlanner() { }

    public static Instant nextAt(
            Instant now,
            int failedAttemptNumber,
            Duration base,
            Duration max) {
        if (failedAttemptNumber < 1
                || base.isZero()
                || base.isNegative()
                || max.compareTo(base) < 0) {
            throw new IllegalArgumentException("Invalid retry inputs");
        }

        long ceiling = base.toMillis();
        long maximum = max.toMillis();
        for (int i = 1; i < failedAttemptNumber; i++) {
            ceiling = ceiling > maximum / 2
                    ? maximum
                    : Math.min(maximum, ceiling * 2);
        }

        long waitMillis = ThreadLocalRandom.current()
                .nextLong(ceiling + 1);
        return now.plusMillis(waitMillis);
    }
}
~~~

This is an illustrative helper. With full jitter, delays can approach 0; production can add a floor, honor provider cooldowns, and always check `expiresAt` and max attempts. If `base.toMillis() == 0` or `max.toMillis() == 0`, validate explicitly rather than calling `nextLong(0)`, and use sensible Duration bounds.

Never retry authentication or config errors as temporary throttling, and never auto-refund quota/attempts when provider outcomes are uncertain.

## 17. Hard Limits: SMTP Provider and Recipient Quotas

Applications can scale compute, yet **cannot manufacture extra contractual quota** from an SMTP provider:

~~~text
Application produces 100 messages/s
Provider permits 20 messages/s

Sustainable accepted rate <= 20/s
Backlog grows unless source demand is controlled
~~~

Limits to inspect for each specific account:

| Limit | What to Distinguish |
|---|---|
| Messages/s | Per MIME message vs. per API request |
| Recipients/s | Total envelope recipients, not just `send()` calls |
| Recipients/day | Calendar day vs. rolling 24-hour window |
| Messages/day | May differ from recipient quota |
| Concurrent connections | Maximum simultaneous open SMTP connections |
| RCPT per message | Maximum addresses inside one envelope |
| Size per message | Measured after MIME/Base64 encoding vs. raw file |
| Domain/reputation throttle | Provider may throttle dynamically |
| Organization vs. credential quota | Multiple credentials may share one account budget |

In your assessment, state **unit, window, and scope** for every limit. Multiple API keys under one provider organization do not necessarily hold independent quotas; rotating credentials does not reset budgets.

### Never Run Quotas at 100% of Published Caps

Other streams may share the account, and providers apply cooldowns, reputation rules, daily windows, and jitter. Maintain **intentional headroom** tuned by measurement rather than assuming one universal percentage rule fits every provider.

## 18. Rate Limiters and Concurrency Limiters Are Separate Controls

Suppose the app configures:

~~~java
var executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(5);
executor.setMaxPoolSize(10);
executor.setQueueCapacity(100);
~~~

That is an **executor pool config**—it does not prevent exceeding 100 messages/second when SMTP responds quickly, nor does it protect 3 replicas of 10 workers sharing one account.

Separate:

1. **Rate:** tokens per second/minute.
2. **Daily/rolling budget:** recipients/messages per window.
3. **Concurrency:** simultaneous active SMTP operations.
4. **Batch size:** jobs claimed at once.
5. **Queue capacity:** jobs waiting in process memory (distinct from DB backlog).
6. **Tenant fairness:** service order and allocated shares.

### A Job Must Pass Multiple Gates

~~~text
Due job
  |
  +-- tenant policy allowed?
  +-- provider account quota available?
  +-- recipient cost available?
  +-- active SMTP slot available?
  +-- still before deadline?
  |
  v
Begin submission
~~~

If no quota permit is granted, update `available_at` and release the claim **without incrementing SMTP attempt count**, since no provider call occurred.

### Do Not Deduct Account and Tenant Quotas Unatomically

If the account bucket deducts a token and then the tenant bucket denies, account budget is wasted without sending. Distributed limiters need atomic multi-bucket admission or an explicit reservation/refund protocol—never two non-atomic Redis GET/SET calls.

## 19. Fairness Across Tenants and Notification Lanes

A single FIFO queue:

~~~text
A1, A2, A3, ..., A100000, B1, C1
~~~

can stall tenants B and C even when overall capacity remains or A is throttled. Per-tenant rate limiters **do not guarantee fairness during job selection**.

Strategies:

| Strategy | When Useful | Limitation |
|---|---|---|
| Round robin | Simple turn allocation | Ignores varying recipient costs |
| Weighted round robin | Differentiated tenant tiers | Requires tuning weights properly |
| Deficit round robin | Varying job costs | Requires maintaining deficit state |
| Priority lanes | OTP/transactional vs. bulk | Strict priority can starve bulk |
| Reserved rate/capacity | Protects critical email SLOs | May leave reserved slice idle when empty |

An essential test:

~~~text
Tenant A: 10,000 newsletter jobs arriving at once
Tenant B: 10 password reset jobs arriving later

Expected:
  Tenant B has bounded dispatch lag under quota assumptions.
  Tenant A remains within its allocated share.
  Aggregate account quota is not exceeded.
~~~

A system with high aggregate throughput that strands OTPs behind thousands of newsletters **fails user expectations**.

## 20. Backpressure: Never Claim More Than You Can Process

When producers outpace SMTP, apply **backpressure** upstream or across workflow stages:

~~~text
Producer > Outbox > Dispatcher > Rate gate > SMTP provider
                             ^
                             |
                         Bottleneck
~~~

If the dispatcher claims 10,000 jobs and dumps them into an unbounded executor queue:

- Heap grows rapidly.
- Leases on queued jobs expire while waiting.
- Cancellations and reschedules become hard to synchronize.
- Other workers reclaim and retry active work.
- Sudden shutdowns leave ambiguous states everywhere.

Better:

- Claim batches sized to real in-flight capacity.
- Use bounded executor queues with explicit full-queue handling.
- When quota denies, **defer the job in the DB** rather than sleeping on worker threads.
- Throttle bulk campaign producers or stagger `scheduled_at`.
- Enforce priority and fairness across tenants and lanes.
- Alert on queue age rather than raw queue count alone.

### Handling Overload at the API

An HTTP API can:

- Accept and persist durable jobs while storage capacity and SLAs allow.
- Return `429 Too Many Requests` when callers exceed product limits.
- Return `503 Service Unavailable` when the system cannot safely persist intents.

Never return `202 Accepted` if the outbox insert failed. When clients time out after DB commit, idempotency keys and status endpoints prevent duplicate intents.

## 21. Connection Setup, TLS, and SMTP Timeouts

An outbound email spends time across multiple steps:

~~~text
DNS lookup
   -> TCP connect
   -> TLS/STARTTLS negotiation
   -> AUTH
   -> MAIL FROM
   -> RCPT TO
   -> DATA / MIME transfer
   -> final SMTP response
~~~

Evaluate with **end-to-end** timings, not just MIME serialization time.

In Spring Boot, mail config commonly sets:

~~~yaml
spring:
  mail:
    host: smtp.example.test
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 15000
      mail.smtp.writetimeout: 15000
~~~

These timeouts are **illustrative assumptions**, not universal recommendations for every provider. Tune them from observed latency, network paths, and business deadlines. Failure modes:

- Too short: false temporary failures.
- Too long: ties up in-flight slots and worker threads.
- Missing timeouts: hung sockets slowly drain capacity to zero.

### Connection Reuse

With `JavaMailSenderImpl`, never assume individual `send(...)` calls automatically reuse a persistent connection pool as desired. Jakarta Mail/SMTP connection reuse and batching depend on version and implementation—verify them directly. Careful batching and sender lifecycles can cut handshake overhead, balanced against partial failures, memory, fairness, and quotas.

**Never mutate SMTP host, username, or password on a shared multi-threaded singleton sender** to switch providers per job. Use dedicated sender adapters per account/route with controlled credentials.

## 22. Large Attachments and Memory Pressure

A tiny plain-text job has a vastly different resource footprint than a 20 MiB PDF job. With `ByteArrayResource`, bytes sit in `byte[]`, and MIME serialization allocates extra buffers. Base64 encoding inflates attachments by roughly 4/3 before line breaks and headers.

Example:

~~~text
50 concurrently prepared attachments
each raw file = 12 MiB

Raw byte[] alone:
  50 * 12 MiB = 600 MiB
~~~

And that is **still not total heap footprint**, which also includes:

- Bytes allocated by document generators.
- Intermediate `byte[]` copies across layers.
- `MimeMessage` and attachment object graphs.
- Base64 and line-wrapping buffers.
- Template models.
- Caches, connection pools, and HTTP payloads.
- Heap fragmentation and GC overhead.

A benchmark using only 2 KiB text emails **cannot predict** memory behavior with PDFs and spreadsheets.

### Mitigations

1. Enforce max attachment size before enqueue and submission.
2. Never preload attachments for due jobs until send capacity is ready.
3. Limit concurrent large-attachment SMTP jobs.
4. Use `FileSystemResource` or a reopenable `InputStreamSource` for large payloads where lifecycles permit.
5. For very large documents, prefer authorized expiring download links over email attachments.
6. Define file retention and versioning across retries.
7. Check your provider's **encoded MIME message-size cap**, not just raw attachment bytes.

### Repeatable Streams Are Essential

`ByteArrayResource` can open fresh streams over its byte array. `InputStreamResource` usually wraps a one-shot stream and fails if MIME serialization reads twice. With object storage, custom `InputStreamSource` implementations must open **a fresh stream pinned to the exact object version** rather than a consumed one-shot stream.

### Testing Edge-Case Files

Tests should cover:

~~~text
0-byte attachment
Small PDF < 100 KiB
Medium PDF ~1 MiB
Large XLSX ~10 MiB
Near provider size limit
Above allowed size (must be rejected before SMTP)
Invalid MIME type/extension
Unavailable storage object during retry
~~~

Never load-test with real customer documents or dump raw attachments into logs.

## 23. Template, HTML, and CSV Rendering Also Has Limits

Email processing time spans:

~~~text
Load business data
   -> resolve recipient/locale
   -> template rendering
   -> HTML escaping
   -> PDF/CSV generation
   -> MIME composition
   -> SMTP submission
~~~

A template interpolating 10 variables behaves completely differently from one querying 1,000 rows to build an Excel file. If the app is CPU-bound in PDF generation, adding SMTP workers only grows memory queues.

Metrics to track:

- Template rendering P50/P95/P99 latency.
- PDF/XLSX generation latency and allocated bytes.
- Cache hit/miss rates and template versions.
- N+1 DB queries while hydrating template models.
- Object storage read durations.
- MIME serialization duration and output bytes.
- GC pauses and heap pressure.

### Split Heavy Work When Warranted

When document generation is expensive, consider:

~~~text
Business event
  -> document generation job
  -> durable immutable attachment reference
  -> notification job
  -> SMTP worker
~~~

Splitting pipelines adds state and consistency complexity, so base the decision on measurements rather than "microservices are always better".

### CSV Formula Injection, HTML, and Filenames

Scalability never excuses security shortcuts:

- Escape and sanitize HTML variables properly.
- Guard spreadsheet CSV cells against formula injection.
- Strip internal paths, control characters, and unnecessary PII from attachment filenames.
- Never log raw email bodies or MIME just to debug throughput.

## 24. Database: Bottlenecks in Claiming, Updates, and Retention

An outbox database handles multiple operations per email:

~~~text
INSERT new mail intent
SELECT/UPDATE due jobs for claim
UPDATE attempt started
UPDATE submitted/retry/failure
INSERT status event/history
SELECT status for customer support
DELETE/archive terminal jobs
~~~

At 1,000 jobs/s, each job multiplies into many **DB operations**, not one INSERT. Secondary indexes and audit tables amplify write load further.

### Inspect Execution Plans and Row Contention

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY')
  AND scheduled_at <= CURRENT_TIMESTAMP
  AND available_at <= CURRENT_TIMESTAMP
ORDER BY available_at, id
LIMIT 100;
~~~

This query is illustrative for plan analysis; real claim queries also carry locking and update semantics. Because `EXPLAIN ANALYZE` executes the query, assess cost and use safe environments before running in production. Check:

- Index scan vs. sequential scan?
- Scan duration as backlogs grow?
- Temp-disk sort spills?
- Rows filtered out because `scheduled_at` is still future?
- Lock waits across concurrent workers?
- Connection pool saturation?

### Indexes Are Trade-Offs

A partial index for due states:

~~~sql
CREATE INDEX idx_mail_outbox_active_due
ON mail_outbox (available_at, id)
WHERE status IN ('PENDING', 'RETRY');
~~~

speeds up due-job selection, yet every index increases write amplification. If queries always filter by `provider_account_id`, leading with that column may fit better. Decide from query plans and real data rather than creating every index variant "just in case".

### Retention

If you keep all `SUBMITTED` jobs and raw MIME forever:

- Tables grow unboundedly.
- Indexes lose cache efficiency.
- Backups and restores slow down.
- PII lingers beyond necessity.
- Compliance and deletion become complex.

Define separate retention windows for active jobs, terminal records, attempts, delivery events, and payloads. Never delete `RETRY` jobs or payloads not yet due, and never archive `PROCESSING` rows whose outcome is still unknown.

## 25. PostgreSQL Queue, Message Broker, or Dedicated Scheduler?

Options:

| Approach | Pros | Limits |
|---|---|---|
| DB outbox + polling | Atomic with business DB; easy status queries | DB scans, locks, write load, polling overhead |
| DB outbox + CDC relay | Reduces active-table polling; feeds brokers cleanly | Operational CDC complexity; still needs status/idempotency |
| RabbitMQ / Kafka consumers | High consumer throughput and buffering | Redelivery, ordering, retries/expiry/consumer idempotency |
| Delayed broker messages | Handy for scheduled sends | Cancellation, durable state, and status queries need care |
| Quartz JDBC JobStore | Calendars, crons, persistent triggers | Does not manage SMTP attempts or delivery |
| Managed notification provider | Built-in queues, templates, tracking | Vendor semantics, quotas, compliance, lock-in |

None of these options alone guarantees an exactly-once SMTP side effect. Databases anchor transactional intent well; brokers help scale consumers once paired with **durable handoffs** from business transactions, deduplication, and state tracking.

### Pick Based on Measured Bottlenecks

If the database is nowhere near saturation and mail volume is modest, adding Kafka or Redis merely "for scale" adds failure modes without payoff. If claim polling loads the DB or many independent consumers need events, an outbox relay/broker becomes worthwhile. Plan cutovers carefully so jobs are never dispatched on two paths at once.

## 26. Horizontal Scaling: Throughput Does Not Scale Linearly Forever

Suppose one worker replica processes 30 messages/s while the provider account allows only 60/s:

| Replicas | Raw App Potential | Account Accepted Cap | Notes |
|---|---:|---:|---|
| 1 | 30/s | 60/s | App-side bottleneck |
| 2 | 60/s | 60/s | Ideally meets cap |
| 4 | 120/s | 60/s | Extra replicas do not raise accepted rate |
| 8 | 240/s | 60/s | Increases contention without a rate gate |

All numbers are hypothetical examples. Real account quotas may meter recipients/day rather than messages/s and shift over time.

### Scaling Without a Distributed Limiter

~~~text
Pod A: local 30 messages/s
Pod B: local 30 messages/s
Pod C: local 30 messages/s

One shared provider account cap = 60/s
Potential aggregate = 90/s
~~~

Per-pod local limiters are **insufficient** for a shared provider account quota. You need shared admission control or partitioned budgets that guarantee the sum stays bounded.

### Downstream Constraints Still Cap Scaling

- Database max connections.
- Concurrent SMTP connections.
- Redis rate-gate throughput.
- Object storage read bandwidth.
- Network egress bandwidth.
- Provider reputation and recipient acceptance.
- CPU/heap for template and MIME generation.

Whenever adding replicas, measure **useful throughput, tail latency, DB waits, Redis latency, SMTP throttling, and cost**—not just pod CPU.

## 27. Vertical Scaling: What Does More CPU/RAM Solve?

Adding CPU/RAM to a JVM helps when:

- HTML/PDF rendering is CPU-bound.
- Attachments drive GC pressure.
- Many concurrent MIME objects coexist.
- Executors lack enough workers to hide SMTP latency.

It **does not solve**:

- Provider account quotas.
- Daily recipient limits.
- Network partitions.
- Exactly-once SMTP delivery.
- Tenant fairness.
- DB row/key lock contention.

### Inspect the JVM Before Increasing Heap

Questions to ask:

- Does heap usage climb alongside concurrent attachments?
- Do GC pauses/CPU correlate with throughput drops?
- Which allocations dominate?
- Are `byte[]` buffers retained after sends in caches or queues?
- Are executor queues unbounded?
- How many threads sit blocked on socket I/O?

An OOM during large attachments is often solved better by **bounded concurrency** and file-backed resources than by endlessly inflating the heap.

## 28. If the Bottleneck Is Not Spring Mail, Do Not "Optimize Spring Mail"

Symptom table:

| Symptom | First Hypothesis | Evidence Required |
|---|---|---|
| Rising SMTP 4xx throttles | Account/recipient quota, burst, reputation | SMTP reply codes, rate per scope |
| 100% CPU, low SMTP rate | Template/PDF/MIME rendering CPU-bound | CPU profiles, render timers |
| Long GC pauses, high heap | Attachment buffers, in-memory queues | Heap/allocations, in-flight count |
| High DB CPU or locks | Outbox query, missing index, hot updates | Query plans, lock metrics |
| High HTTP latency when SMTP slows | Synchronous send inside requests | Endpoint spans, thread dumps |
| High Redis latency | Distributed rate-gate contention | Redis op metrics, key hotness |
| Backlog rises with zero SMTP errors | Quota gate denials or fairness rules | Permit metrics, due backlog |
| One tenant uniquely slow | Head-of-line blocking or fairness config | Per-tier backlog age |
| Duplicate send attempts | Claim race, broken replay/UNKNOWN handling | Attempt history, claim tokens |
| Accepted by provider, unread by user | Delivery, bounce, or spam filtering | Provider traces, delivery events |

**Always find the bottleneck by measuring.** Switching `SimpleMailMessage` to `MimeMessage` or spawning more threads will not automatically raise throughput.

## 29. Designing Repeatable Performance Experiments

A solid load test answers clearly:

> Under configuration X, message mix Y, observation window Z, and quota Q, what throughput, latency, error profile, and bottleneck appear?

### Recommended Protocol

1. **Pin build/version:** record Git SHA, Java version, Spring Boot/framework versions, config, and dependencies.
2. **Isolate the environment:** staging or dedicated test deployment with explicit CPU/RAM/DB/Redis allocations.
3. **Use an SMTP sink / test double:** never email real customers or hit production provider accounts.
4. **Prepare synthetic payloads:** representative text, HTML, and PDF/XLSX fixtures.
5. **Establish baseline:** 1 replica with no artificial quota cap to measure app-side capacity.
6. **Warm up:** let JVM/JIT, connection pools, and caches stabilize before recording.
7. **Ramp load cleanly:** step up offered rates (e.g., 5, 10, 20, 40, 80 jobs/s).
8. **Hold each step long enough:** measure steady state, not just the first few seconds.
9. **Capture SLIs together:** HTTP, DB, workers, SMTP sink, OS/JVM.
10. **Repeat runs:** report variance and distributions rather than one cherry-picked run.
11. **Enable simulated provider quotas:** verify rate gates and backlogs when demand exceeds supply.
12. **Inject crashes/restarts:** prove zero durable intents are lost.
13. **Record assumptions and results:** charts, tables, and explicit limit explanations.

### Never Mix Capacity Tests with Provider Reputation Tests

A local SMTP sink can swallow 1,000 messages/s while a real provider allows 20/s or throttles on reputation. Sink tests measure only **application-to-sink transport capacity**. Real provider limits come from docs, account policies, and approved controlled tests—never bulk spam to "discover the ceiling".

## 30. Setting Up a Safe SMTP Sink and Benchmark Environment

Diagram:

~~~text
Synthetic load generator
         |
         v
Spring Boot API / event producer
         |
         v
PostgreSQL outbox / queue
         |
         v
N mail worker replicas
         |
         v
SMTP sink (Mailpit/GreenMail or controlled stub)
         |
         v
Message/recipient counters and MIME inspection
~~~

Tools like Mailpit or GreenMail capture test SMTP mail without relaying to real recipients. Depending on tool and version, you can simulate latency, errors, or stub responses; otherwise build an appropriate test stub/adapter.

### Data Must Be Synthetic

- Recipients: synthetic addresses on reserved test domains like `user001@example.test`.
- Senders: test profiles with zero production credentials.
- Bodies: dummy content with no accounts, tokens, or PII.
- Attachments: synthetic PDF/CSV/XLSX files without sensitive data.
- Object storage: isolated test buckets with retention and access controls.
- Never turn on raw-message SMTP debug logs in shared environments.

### Test Sinks Have Their Own Limits

A sink storing every message can itself hit CPU, disk, or memory bottlenecks. If the sink slows down, results no longer measure your application's limits. Monitor sink metrics and consider controlled discard/counter modes for raw throughput runs, paired with separate tests checking MIME correctness.

## 31. Minimum Load Test Suite

| ID | Scenario | Evaluation Goal |
|---|---|---|
| LT-01 | Plain text, 1 recipient, 1 replica | Baseline app-side throughput |
| LT-02 | HTML/template, 1 recipient | Rendering overhead |
| LT-03 | PDF 300 KiB | Moderate attachment overhead |
| LT-04 | XLSX 8 MiB | Heap, GC, and memory stress |
| LT-05 | 20 recipients/message | Recipient-cost and SMTP envelope semantics |
| LT-06 | 10x burst for 30 seconds | Backlog growth and backpressure |
| LT-07 | Load exceeding simulated quota | Rate gates, deferrals, zero provider flooding |
| LT-08 | Scale 1→2→4→8 worker replicas | Horizontal scaling curve |
| LT-09 | 1 huge tenant + 1 OTP tenant | Lane fairness and latency isolation |
| LT-10 | 10x slower SMTP sink | Timeouts, concurrency, queue age |
| LT-11 | Simulated temporary 4xx errors | Backoff/jitter without retry storms |
| LT-12 | Authentication failure | Route pause without tight retries |
| LT-13 | App restart with PENDING backlog | Intent durability |
| LT-14 | Worker crash after claim | Lease recovery |
| LT-15 | Unknown outcome after DATA | Zero blind resends |
| LT-16 | Transient database outage | No lost states and steady backpressure |
| LT-17 | Redis limiter outage | Fail-closed or bounded approved fallback |
| LT-18 | Rolling deploy under backlog | Ownership stability and duplicate risk |
| LT-19 | 1-hour steady load | Leaks, retention, GC, and DB growth |
| LT-20 | Attachments near size limit | Pre-SMTP validation |

Define **pass/fail criteria before running each test**. For instance, LT-07 passes when accepted submit rate stays within the safe cap across target windows, denied jobs remain in the outbox, and no-permit deferrals do not increment SMTP attempt counts.

### Open-Loop vs. Closed-Loop Testing

- **Closed-loop:** each virtual user waits for a response before issuing the next request. When the server slows down, offered load drops automatically, masking overload.
- **Open-loop:** the generator emits at a fixed arrival rate even when responses lag. Use open-loop to test bursts and overload while ensuring the generator itself is not bottlenecked.

Always document the generator model and **offered load**, not merely completed request counts.

## 32. Benchmark Results Table Template

A report can use this layout:

| Run | Replicas | Offered jobs/s | Accepted messages/s | API p95 | Queue p95 | Error/deny | Bottleneck |
|---|---:|---:|---:|---:|---:|---|---|
| B01 | 1 | … | … | … | … | … | … |
| B02 | 2 | … | … | … | … | … | … |
| B03 | 4 | … | … | … | … | … | … |
| B04 | 4 | … + PDF | … | … | … | … | … |
| B05 | 4 | … + quota | … | … | … | … | … |

**Never enter estimated numbers as measured results.** Leave unexecuted cells blank or mark `NOT_MEASURED`. Report p50/p95/p99, sample counts, durations, and measurement methodology.

### Questions to Ask When Reading Results

1. Did accepted throughput keep rising as offered load grew?
2. Did p95/p99 latency spike well before throughput saturated?
3. Did queue age grow despite low CPU because of quotas?
4. Why did SMTP accepted rate differ from rate-gate permits?
5. Did attempt counts exceed intent counts?
6. Did DB pool/lock waits climb with replica count?
7. Did expired job ratios climb?
8. Did one tenant consume most capacity?
9. Was durability verified across restarts?
10. Did repeated runs show wide variance?

## 33. Example: Measuring Latency with Spring Boot Micrometer

With Spring Boot Actuator/Micrometer, add timers at clear boundaries. Measure **exactly which processing stage** each timer covers rather than calling everything "send latency".

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.concurrent.TimeUnit;
import org.springframework.stereotype.Component;

@Component
public final class MailMetrics {
    private final MeterRegistry registry;

    public MailMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordSmtpSubmission(
            String providerGroup,
            String outcome,
            long elapsedNanos) {
        Timer.builder("mail.smtp.submission.duration")
                .description("Duration of one SMTP submission attempt")
                .tags(
                        "provider_group", providerGroup,
                        "outcome", outcome)
                .register(registry)
                .record(elapsedNanos, TimeUnit.NANOSECONDS);
    }

    public void recordQuotaDenied(
            String scopeType,
            String reasonCode) {
        registry.counter(
                "mail.rate.denied",
                "scope_type", scopeType,
                "reason", reasonCode).increment();
    }
}
~~~

Illustrative utility. In production:

- Restrict `providerGroup`, `outcome`, and `reasonCode` to enums or allowlists—avoid arbitrary labels.
- Measure elapsed durations with a monotonic clock such as `System.nanoTime()`.
- Never attach recipient emails, subjects, job IDs, or raw exception messages to metric tags.
- Configure histograms/percentiles compatible with traffic and cardinality budgets.
- Classify SMTP exceptions safely rather than treating every error as temporary.

### Timing Around the SMTP Adapter

~~~java
long started = System.nanoTime();
String outcome = "UNKNOWN";
try {
    mailSender.send(message);
    outcome = "ACCEPTED";
} finally {
    metrics.recordSmtpSubmission(
            "PRIMARY",
            outcome,
            System.nanoTime() - started);
}
~~~

This snippet only marks where elapsed time is measured. Real systems classify exceptions into temporary, permanent, or unknown by SMTP phase and persist the **attempt result** in the state store. A `finally` block recording latency does not decide retries.

## 34. Dashboards Need Three Views: Demand, Admission, and Completion

An overview dashboard:

~~~text
DEMAND
  intents created/s
  outbox PENDING/RETRY jobs
  oldest due job age
  job payload size distribution

ADMISSION
  jobs claimed/s
  rate gate permits/denials
  SMTP in-flight operations
  DB claim latency and contention

SUBMISSION / FEEDBACK
  SMTP accepted/s
  temporary/permanent errors
  unknown outcomes
  retries, expired jobs
  delivered/bounced if provider events exist
~~~

An outbox holding 1 million jobs **scheduled for next month** is not currently overloaded. Separate:

~~~text
future scheduled:
  scheduled_at > now

due waiting:
  scheduled_at <= now
  available_at <= now
  status in PENDING/RETRY

deferred due to quota/retry:
  scheduled_at <= now
  available_at > now
~~~

Watching only total `PENDING` triggers false alarms; watching only currently due jobs hides jobs pushed out repeatedly by quota deferrals.

## 35. SQL Queries Supporting Backlog Analysis

Illustrative PostgreSQL queries.

**Count due jobs:**

~~~sql
SELECT COUNT(*) AS due_jobs
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY')
  AND scheduled_at <= CURRENT_TIMESTAMP
  AND available_at <= CURRENT_TIMESTAMP;
~~~

**Measure oldest due job age:**

~~~sql
SELECT EXTRACT(
    EPOCH FROM (
        CURRENT_TIMESTAMP - MIN(scheduled_at)
    )
) AS oldest_due_age_seconds
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY')
  AND scheduled_at <= CURRENT_TIMESTAMP
  AND available_at <= CURRENT_TIMESTAMP;
~~~

When no rows match, `MIN` returns null. Never convert null to "0 seconds" if that blurs the absence of backlog with stale metrics.

**Count jobs by status:**

~~~sql
SELECT status, COUNT(*) AS jobs
FROM mail_outbox
GROUP BY status
ORDER BY jobs DESC;
~~~

**Count quota/retry-deferred jobs per provider account:**

~~~sql
SELECT provider_account_id, COUNT(*) AS deferred_jobs
FROM mail_outbox
WHERE status IN ('PENDING', 'RETRY')
  AND scheduled_at <= CURRENT_TIMESTAMP
  AND available_at > CURRENT_TIMESTAMP
GROUP BY provider_account_id;
~~~

Running `COUNT(*)` over huge tables every few seconds adds DB load. Production systems use materialized/aggregated counters or volume-tuned queries while measuring observability overhead itself.

## 36. Percentiles Matter More Than Average Latency

Example:

~~~text
990 SMTP attempts complete in 100 ms
10 attempts hang for 30 seconds
~~~

The mean looks reasonable for some workloads, yet that 1% tail ties up worker slots for tens of seconds. Inspect:

- p50: typical experience.
- p95/p99: tail under load.
- Timeout rate: attempts exceeding caps or ending unclearly.
- In-flight saturation: how many SMTP slots remain occupied.
- Queue delay p95/p99 per lane.
- Oldest due job age.

Never compare percentiles from two runs with **different load mixes, durations, tags, or warm-up conditions** as if they came from the same population.

### Coordinated Omission

When a load generator waits for one request before sending the next, severe slowdowns are **undersampled**. Closed-loop runs report artificially rosy latencies relative to fixed arrival rates. Use open-loop arrivals or coordinated-omission-aware tooling when measuring bursts.

## 37. Stress Testing: How Does the System Degrade Past Limits?

**Load tests** ask how the system behaves at target load. **Stress tests** intentionally push past capacity to observe breaking points and recovery.

A stepped ramp:

~~~text
0-5 minutes:     5 jobs/s
5-10 minutes:   10 jobs/s
10-15 minutes:  20 jobs/s
15-20 minutes:  40 jobs/s
20-25 minutes:  80 jobs/s
25-30 minutes:  step down to 10 jobs/s
~~~

This profile is illustrative; tune it to avoid impacting shared infrastructure.

Observe:

- At what point does accepted throughput stop climbing?
- When and why does the API shift from `202` to 429/503?
- How steeply does queue age climb?
- How do HTTP and SMTP p95/p99 latencies shift?
- Does the executor queue stay bounded?
- How do CPU, heap, GC, DB locks, and Redis latency behave?
- Do job counts and state transitions remain exact once load drops?
- Are any duplicate submissions or lost intents observed?

### Expected Behavior Under Overload

A system that "fails predictably" should:

1. Preserve all committed intents.
2. Never breach hard provider quotas.
3. Never exhaust all thread or connection pools.
4. Return honest overload signals when unable to accept more.
5. Prioritize critical lanes per policy.
6. Recover cleanly once offered load subsides.
7. Never tightly retry config or provider failures.

An OOM or crash loop the moment load hits 2x target signals missing backpressure or isolation—even if normal-load throughput looks great.

## 38. Soak Testing: Is It Stable Over Hours or Days?

A 2-minute run rarely catches:

- Slow memory leaks retaining `MimeMessage` or `byte[]`.
- Unclosed connections or streams.
- Continuously growing outbox tables/indexes.
- Retention/cleanup falling behind.
- Unbounded caches keyed by template keys or tenant IDs.
- Growing log volumes or high-cardinality metric series.
- Clock drift, cron bugs, or broken daily quota resets.

A soak test holds steady realistic load for hours while watching trends:

~~~text
Heap after GC over time
DB table/index bytes growth
Outbox terminal state count
Open connections, file handles
SMTP in-flight count
Worker queue length
GC pause P99
CPU trend at constant throughput
Rate gate latency
~~~

Ideally, resource curves **stay bounded or follow predictable cycles** under steady offered load and workload mix. Never demand a flat line for heap memory—JVMs, GC, and caches oscillate naturally.

### Checking Retention with Synthetic Data

If a soak test creates one million terminal jobs, verify older jobs archive or purge per policy instead of growing forever. Never purge `PENDING/RETRY` rows solely by old `created_at`, since they may be future-scheduled or retrying jobs.

## 39. Failure Injection: Testing Real-World Faults

Scalability testing is incomplete if it only measures the happy path.

| Failure Injection | What to Observe |
|---|---|
| SMTP connect timeout | Bounded duration, retry policy |
| SMTP read/write timeout | Slots freed cleanly, outcome classified |
| Provider temporary 4xx | Backoff/jitter, zero retry storm |
| Provider permanent 5xx | FAILED/suppression per policy |
| Invalid auth credentials | Route paused, alert fired, no hot retries |
| TLS negotiation failure | Never silently weakens security |
| DB connection lost before outbox commit | Never returns accepted if intent unsaved |
| DB lost after SMTP accepted | UNKNOWN/reconciliation, zero blind resends |
| Redis rate gate unavailable | Fail closed or bounded approved fallback |
| Worker killed after claim | Lease recovery |
| Worker killed after SMTP DATA | Duplicate-risk handling |
| Broker redelivers event | Business intent idempotency |
| Provider sends duplicate webhook | Delivery event deduplication |
| Provider callbacks arrive out of order | State never regresses arbitrarily |
| Object storage temporarily down | Phase-aware preparation retry; never sends empty |
| Clock skew | Due/lease checks stay safe |
| Rolling deployment | Zero double claims or resurrected jobs |

### Keep Fault Injection Contained

Simulate failures against SMTP sinks/stubs, test databases, and isolated accounts. Never disrupt a real provider or email unconsenting recipients. Network-drop tests **after SMTP DATA** require a test double capable of modeling protocol phases; mocks throwing before `send()` never exercise ambiguous outcomes.

## 40. Recovery Testing: Proving No Lost Intents or Blind Replays

A key recovery test:

~~~text
Given:
  1000 PENDING jobs committed in DB

When:
  worker process is killed
  and a new worker starts

Then:
  all eligible jobs remain discoverable
  no job disappears from durable store
  no job is submitted twice solely because two workers raced
~~~

And a separate test for ambiguity:

~~~text
Given:
  provider accepted job #583
  worker crashed before DB status commit

When:
  lease expires

Then:
  job is reconciled or handled via explicit UNKNOWN policy
  not automatically treated as certainly unsent
~~~

**Never claim exactly-once SMTP delivery** simply because a restart test produced no duplicates. Without a distributed atomic transaction spanning SMTP and DB, an ambiguous outcome window always exists. Document acceptable duplicate bounds in requirements.

### Replay and DLQ Planning

When retries run out, jobs enter `FAILED` or dead-letter workflows:

- Standardized reasons and full attempt histories.
- Role-restricted replay authorization.
- Block bulk replays until underlying config bugs are fixed.
- Never automatically send expired OTPs.
- Never resend emails already accepted by the provider merely because delivery webhooks are missing.
- Audit the operator or automation triggering every replay.

A full DLQ with nobody watching provides zero real reliability—assign owners and runbooks.

## 41. Testing Multi-Tenant Fairness and Security Boundaries

Multi-tenant SaaS apps must evaluate **isolation**, not only aggregate throughput.

~~~text
Tenant A: burst 50,000 newsletter jobs
Tenant B: 10 password-reset jobs
Tenant C: 200 order receipts
~~~

Questions:

1. Do Tenant B and C dispatch latencies stay within SLA?
2. Does Tenant A stay within its tenant cap?
3. Does the sum across tenants stay inside provider account quota?
4. Does credential rotation accidentally reset quotas?
5. Can one tenant pick another tenant's sender profile?
6. Can one tenant inspect another tenant's jobs, statuses, or payloads?
7. Can Tenant A explode metric cardinality unboundedly?
8. If the quota gate errors, does failing open let all tenants flood the provider?

### Measure Fairness in the Right Unit

Message-count round robin is unfair if Tenant A sends 20 recipients per message while Tenant B sends 1. Enforce shares by **recipient cost** when providers meter recipients, using weighted or deficit round robin where costs vary.

### Protecting Data

- Derive tenant ID from authenticated context, never untrusted request bodies.
- Apply ACLs and versioning to payload/attachment references.
- Never let callers pick arbitrary SMTP hosts, passwords, or From addresses.
- Keep raw recipients, bodies, and MIME out of logs.
- Audit all replay, cancel, reschedule, and quota-override actions.
- Restrict metric labels to allowlisted provider, lane, and tier values; keep per-tenant breakdowns in access-controlled stores if needed.

## 42. Cost Model: Scaling Must Account for Whole-System Cost

Raising throughput with more replicas increases costs across multiple layers:

| Cost Component | Observed Unit | As Load Grows |
|---|---|---|
| App worker CPU/RAM | vCPU-hour / GiB-hour | MIME/PDF rendering, concurrency slots |
| Database | CPU, IOPS, storage, connections | Inserts, updates, claims, audits |
| Redis | Ops/s, memory, network | Shared quotas and locks |
| Message broker | Throughput, storage, retention | Durable event buffering |
| SMTP provider | Messages, recipients, bytes | Billable volume and quotas |
| Object storage | GB stored, reads, egress | Attachments and retries |
| Monitoring | Time series, log GB, traces | High cardinality and log volume |
| Support/operations | Incident handling time | Bounces, replays, investigations |

A helpful economic metric:

\[
\text{costPerAcceptedMessage} =
\frac{\text{cost in measurement window}}
{\text{definitively accepted messages}}
\]

If your provider bills per recipient, also track `costPerAcceptedRecipient`. Never divide by total intents when many jobs sit queued, as that disguises backlogs.

### Headroom Is an Intentional Cost

Keeping spare capacity for OTP bursts or provider failovers lowers average utilization. That is not automatically waste—it may be the explicit price of meeting SLOs during bursts and outages. Document that trade-off rather than blindly maximizing messages/s.

## 43. Risk Register: Limits to Accept or Remediate

A practice project does not have to eliminate every production limitation. What matters is **naming remaining limits explicitly**.

| Risk | Impact | Signal | Mitigation / Trade-Off |
|---|---|---|---|
| Sync send on web thread | Latency/timeouts spill into HTTP | HTTP p99 tracks SMTP | Outbox/workers or bounded concurrency |
| No SMTP quota gate | Provider throttling, account limits | Per-account 4xx/5xx | Shared admission control and headroom |
| No durable outbox | Intents lost on crash | Restart test fails | Transactional outbox or durable queue |
| No idempotency key | Client retries duplicate jobs | 2 intents per event | Unique business keys |
| No state ownership | Multiple workers send duplicates | Duplicate attempts | Atomic claim, leases, fencing |
| Ambiguous SMTP outcome | Retries cause duplicates | Unknown after DATA | UNKNOWN state and reconciliation |
| Unbounded task queue | Heap/GC/OOM | Queue depth climbs endlessly | Bounded queues and backpressure |
| Large in-memory attachments | Heap pressure | OOM / high GC P99 | File-backed reopenable sources, size caps |
| No tenant fairness | OTPs stalled by bulk | High lane lag | Fair scheduling and reserved capacity |
| Missing cleanup | DB/storage grow forever | Table/index bloat | Retention and archiving |
| Credentials in code/logs | Security compromise | Secret-scan findings | Secret manager, RBAC, rotation |
| No delivery feedback | Inbox outcome unseen | Stops at SUBMITTED | Provider event integration or state limit |
| Incomplete observability | Hard incident diagnosis | HTTP metrics only | Job/attempt/provider metrics and runbooks |
| Single-provider reliance | Outage halts all sends | Accepted rate hits zero | Backoff, buffering, approved failover |

### Prioritization

Never label every risk "High". Rank by **likelihood, impact, detectability, and remediation cost** in your real context:

~~~text
Risk priority = impact + likelihood + detectability concerns
                considered with implementation cost
~~~

This is not a rigid numerical formula; teams should adopt an explicit risk matrix. A learning demo lacking multi-provider failover can be fine; a production OTP system lacking timeouts and audits is a critical hazard.

## 44. Roadmap from Learning Project to Production

You do not need every capability on day one. Sequence improvements by real risks and bottlenecks:

### Stage 0: Solidify Core Functionality and Visibility

**Goal:** know where every email sits and which stage failed.

- Decouple business code from `JavaMailSender` behind a mail transport adapter.
- Validate senders, recipients, filenames, MIME types, and attachment sizes.
- Configure SMTP timeouts and provider-matched TLS/auth.
- Add correlation/job IDs and baseline metrics.
- Use an SMTP sink in tests.
- Document quota scopes and workload assumptions.

**Exit criteria:** explain whether a failure occurred during preparation, network submission, or downstream delivery without logging raw MIME.

### Stage 1: Protect Transactions and Persist Intents Durably

**Goal:** never lose committed send requests across worker restarts.

- Build a mail outbox sharing the business DB transaction.
- Enforce business idempotency keys with unique constraints.
- Return queued status from APIs, never claiming delivered.
- Add a due-job dispatcher, state machine, and attempt history.
- Define basic retention policies.

**Exit criteria:** restarts after enqueue lose zero intents; request retries create zero duplicate intents for one event.

### Stage 2: Handle Load and Provider Constraints

**Goal:** stay stable when demand exceeds supply.

- Bound SMTP worker pools and enforce backpressure.
- Add distributed rate gates per account and tenant.
- Track message rate, recipient cost, daily quotas, and concurrency separately.
- Defer denied jobs in the outbox instead of sleeping threads.
- Implement backoff/jitter retries and per-type expiry deadlines.
- Enforce fair scheduling between bulk and transactional traffic.

**Exit criteria:** rising offered load never causes provider flooding, OOMs, or SLA starvation.

### Stage 3: Production Reliability and Operations

**Goal:** handle failures and backlogs proactively.

- Atomic claims, leases, and fencing across replicas.
- `UNKNOWN` state and reconciliation workflows.
- Fault-injection and soak testing.
- Oldest due age dashboards and SLO alerts.
- Authorized DLQ/replay flows.
- Runbooks for provider outages and credential rotation.

**Exit criteria:** simulated faults demonstrate verified recovery paths reflected in metrics and state stores.

### Stage 4: Organizational and Multi-Provider Scale

**Goal:** support multiple domains, teams, and providers cleanly.

- Typed notification contracts and API versioning.
- Separate worker deployments or dedicated Notification Service when warranted.
- Multi-provider routing honoring sender permissions and quotas.
- Provider delivery feedback integration where needed.
- Cost, retention, and privacy governance.
- Regular capacity planning and review cycles.

**Exit criteria:** onboard new tenants, templates, or providers without altering core business code or broadening SMTP secret access unnecessarily.

## 45. Sample Evaluation Scenario: End-of-Project Report

Suppose a Spring Boot project has:

~~~text
Project      : Mail Notification Practice
Flow         : API creates jobs -> DB outbox -> worker -> SMTP
App replicas : 2
Workers/pod  : 4
Provider cap : 40 recipients/s
Daily quota  : 50,000 recipients/day
Message mix  : 90% 1-recipient text/HTML
               10% 1-recipient PDF attachment
Target       : up to 15,000 notifications in 15 minutes
~~~

All values are **illustrative assumptions**, not a benchmarked environment.

### Step 1: Compute Peak Demand

\[
\text{requested rate}
 = \frac{15000}{15\times60}
 \approx 16.67\ \text{jobs/s}
\]

If each job sends one message to one recipient, average campaign demand is 16.67 recipients/s.

### Step 2: Check Account Quotas

The assumed safe provider cap is 40 recipients/s, so average rate/s alone does not bottleneck 16.67/s. Still check:

- Does remaining daily quota cover 15,000?
- Are other apps sharing the same account simultaneously?
- Could a spike exceed 40/s if all 15,000 share one `scheduled_at`?
- Does the provider enforce separate concurrency or message-size caps?

### Step 3: Estimate Concurrent Workers

Assuming a **hypothetical mean** SMTP call duration of 0.3 seconds:

\[
L \approx 16.67\times0.3\approx5
\]

With two pods × four workers = eight slots, theoretical worker count looks sufficient for the average. Yet if p99 SMTP latency hits 10 seconds, tail pressure climbs sharply. Test with realistic latency distributions instead of trusting averages alone.

### Step 4: Check the PDF Workload Slice

If 10% of jobs generate ~3 MiB PDFs, peak memory usage can spike. Never average across text and PDF bytes and ignore P99 size. Benchmark mixed workloads with bounded in-flight attachments.

### Step 5: Measure Real Metrics

An unfilled measurement table:

| Metric to Measure | Current Value |
|---|---|
| HTTP enqueue p95 | NOT_MEASURED |
| SMTP call p95/p99 | NOT_MEASURED |
| Accepted recipients/s | NOT_MEASURED |
| Maximum due backlog | NOT_MEASURED |
| Oldest due age | NOT_MEASURED |
| CPU peak / heap peak / GC p99 | NOT_MEASURED |
| Provider throttle responses | NOT_MEASURED |
| Unknown outcomes | NOT_MEASURED |
| Duplicate business intents | NOT_MEASURED |
| Time to drain after 5-minute outage | NOT_MEASURED |

Never declare "handles 16.67/s" before running tests. Math shows the goal **is plausible under stated assumptions**; benchmarks and failure tests prove it.

### Step 6: State a Conditional Conclusion

An honest report might state:

> "Under our assumed load model, average demand of 16.67 recipients/s sits below the 40 recipients/s safe provider cap. However, because p95 SMTP latency, attachment memory overhead, and concurrency behavior remain unmeasured, SLO compliance is not yet confirmed. Mixed-load benchmarks and fault-injection tests are required before scaling or production rollout."

That conclusion carries far more engineering value than fabricated capacity numbers or claiming "Spring Mail handles millions of emails".

## 46. Final Project Evaluation Report Template

Learners can structure their final report as:

~~~markdown
# Mail Project Scalability Assessment

## 1. System under test
- Project/build revision:
- App architecture:
- Infrastructure:
- SMTP sink/provider:

## 2. Scope and assumptions
- Workload classes:
- Provider/account limits:
- Tenant and lane policies:
- Exclusions/known unknowns:

## 3. SLO / acceptance criteria
- HTTP enqueue latency:
- SMTP submission latency:
- Oldest due backlog:
- Loss / duplication constraints:
- Security requirements:

## 4. Test design
- Data generation:
- Load pattern:
- Warm-up/duration/repetitions:
- Metrics collection:
- Failure injections:

## 5. Observed results
- Throughput and p50/p95/p99:
- CPU/memory/DB/Redis/SMTP:
- Error and retry counts:
- Backlog and recovery:

## 6. Bottlenecks
- Primary bottleneck:
- Supporting evidence:
- Whether provider quota or app capacity:

## 7. Limitations and risks
- Not measured:
- Remaining design risks:
- Security/privacy/operational limits:

## 8. Recommendations
- Short-term:
- Medium-term:
- Long-term:
- Expected trade-offs/costs:

## 9. Decision
- Supported workload envelope:
- Unsupported scenarios:
- Next review trigger:
~~~

Under **Observed results**, enter only actually measured data. Mark unrun items `NOT_MEASURED`. When real mail sending is restricted by account rules, benchmark app-side capacity against an SMTP sink and cite contractual provider quotas as an **un-stress-tested external constraint**.

### Results Must Be Reproducible by Others

Never drop a bare screenshot of a chart. Include:

- Environment names and versions.
- Load generator configuration.
- Exact metric queries and definitions.
- Offered load alongside accepted load.
- Run counts, durations, and warm-up periods.
- Workload mix and attachment sizes.
- Observed failure modes and limits.
- Unmeasured or unverified boundaries.

## 47. Practice Project Self-Assessment Rubric

Use the rubric below to gauge **readiness** of an email project. Scores serve as a learning rubric, not production certification.

| Area | Assessment Question | Expected Evidence |
|---|---|---|
| Functionality | Accurate To/Subject/body and MIME/attachments? | MIME unit tests, SMTP sink |
| Boundaries | Is business code decoupled from SMTP? | Module/dependency graph |
| Sync impact | Do slow providers block HTTP threads/DB locks? | Endpoint spans and fault tests |
| Durability | Do committed requests survive restarts? | Outbox persistence tests |
| Idempotency | Do retried events/requests avoid duplicate intents? | Unique constraints + retry tests |
| Worker ownership | Can two workers claim the same job? | Concurrency tests |
| Retries | Are temporary/permanent/unknown outcomes separated? | Classification tests |
| Provider quota | Are messages/recipients/windows metered accurately? | Quota policies and tests |
| Concurrency | Are in-flight SMTP operations bounded? | Runtime metrics and load tests |
| Backpressure | Does overload avoid unbounded RAM/queue growth? | Stress tests |
| Fairness | Does bulk delay OTPs/transactional mail? | Multi-tenant mixed tests |
| Attachments | Do large files strain the heap? | P95/P99 sizes and GC metrics |
| Observability | Can operators spot backlogs, attempts, and unknowns? | Dashboards and alerts |
| Recovery | Do worker/DB/provider outages have runbooks? | Failure injection drills |
| Security | Are secrets, recipients, and payloads protected? | RBAC and logging reviews |
| Cost | Is cost per message/recipient known? | Cost model |
| Evidence | Are metrics and observed limits documented? | Conditional benchmark report |

### Simple Scoring Guide

For each row, pick:

- **0 — Missing:** not implemented or no evidence.
- **1 — Partial:** works on happy path; lacks fault tests or measurements.
- **2 — Evidenced:** tested or measured appropriately for the stated workload.

Never sum scores and claim "production-grade" if a severe flaw remains—such as leaked SMTP credentials or uncontrolled duplicates in sensitive workflows. One **blocking issue** outweighs a high score.

### Practice Assignment

Create an evaluation for your own project across three load levels:

~~~text
Level 1: Normal load
  1 recipient/message, no attachment

Level 2: Peak traffic
  10x baseline for 5 minutes, mixed HTML/PDF

Level 3: Degraded provider
  SMTP latency increases and 20% temporary rejections
~~~

For each level, record offered jobs/s, accepted messages/s, p95 queue delay, oldest due age, CPU/heap, attempt outcomes, and backlog drain. Then explain whether the bottleneck is provider quota, worker capacity, database, template rendering, or elsewhere.

The 20% failure rate is a **test-double assumption**, not any real provider's actual failure rate. Never induce real failures against production SMTP accounts.

## 48. Common Scalability Misconceptions

### "Adding 10 Pods Makes Sending 10x Faster"

Not when all pods share one provider quota, database bottleneck, or SMTP connection cap. Measure accepted throughput after scaling, not theoretical CPU capacity.

### "How Many Emails per Second Can Spring Mail Send?"

There is no universal number. It depends on the provider, network, MIME size, connection behavior, CPU/DB, worker pools, quotas, and workload mix. Measure **your specific project**.

### "Async Sending Alone Prevents Losing Email"

`@Async` does not survive restarts. Only a durable outbox/broker with proper transaction boundaries preserves send intents.

### "SKIP LOCKED Guarantees Exactly-Once Sending"

`SKIP LOCKED` keeps workers from claiming the same row during DB contention, not across SMTP calls. Crashing right after acceptance still carries duplicate risk.

### "MailSender.send Returning Cleanly Means the Recipient Read It"

No. SMTP accepted is not inbox delivery, and delivered is not opened/read. State only what your evidence proves.

### "Setting Pool Size to 100 Gives 100 Emails/Second"

Pool size sets concurrency; actual rate depends on call duration, quotas, and overhead.

### "HTTP 202/s Equals Email Sending Throughput"

HTTP 202 usually means intents were accepted for processing. Measure SMTP accepted/recipient rates and queue lag separately.

### "Over Quota? Just Keep Retrying"

Retry storms add load and invite stricter provider throttling. Use backoff/jitter, rate gates, attempt limits, and deadlines.

### "A Per-Pod Limiter Using Redis Is Distributed"

No. Independent per-pod budgets can exceed shared caps when summed. Enforce shared atomic admission scoped to account/tenant.

### "One Message Equals One Recipient"

Not when To/Cc/Bcc list multiple envelope recipients. Meter cost in the provider's exact units.

### "A 10 MiB Attachment Uses Exactly 10 MiB of Heap"

Unlikely. Generators, buffer copies, MIME/Base64 expansion, and concurrent in-flight messages multiply usage. Measure heap under realistic payloads.

### "Zero SMTP Errors Means the Pipeline Is Healthy"

Workers might be idle due to quota denials or stalled queues. Watch demand, admission, backlog age, and accepted throughput together.

### "Tracking Average Latency Is Enough"

Tail p95/p99 latency, timeouts, and oldest due age expose problems hidden by averages.

### "Store Full Raw MIME Everywhere for Debugging"

Unsuitable as a default because PII, attachments, and credentials leak easily. Use job/attempt IDs, reason codes, synthetic fixtures, and governed retention.

### "More Database Indexes Always Make It Faster"

Indexes slow down writes and add bloat. Choose indexes from query plans, update rates, and retention needs.

### "Having a DLQ Means Zero Lost Emails"

A DLQ without owners, monitoring, replay rules, or expiry policies still strands critical work.

### "Adding a Backup Provider Gives Full High Availability"

Failover requires verified senders/domains, independent quotas, consistent payloads, and never failing over when the primary route's outcome is UNKNOWN. Two providers can still share dependencies or suffer simultaneous reputation impact.

### "Benchmarking an SMTP Sink Proves Production Deliverability"

Sinks only prove your pipeline reaches a test fixture. Real deliverability depends on spam filtering, reputation, DNS records, and recipient policies—never infer it from sink acceptance.

## 49. Frequently Asked Questions

**How many workers does a Spring Framework Mail project need?** There is no fixed number. Estimate from target accepted rate and SMTP latency, then benchmark under real provider quotas and tail latency. Claim only as many jobs as workers can handle.

**Should we measure emails/second or recipients/second?** Measure both whenever providers enforce limits on both. A multi-recipient email carries a different cost than a single-recipient one.

**Is `SimpleMailMessage` faster than `MimeMessage`?** Plain text avoids MIME multipart/attachment overhead, yet accepted throughput still depends on SMTP, providers, and networks. Pick based on content needs and measure each workload rather than assuming a fixed speedup.

**Do we need Kafka as soon as volume passes 1,000 emails/day?** No. Daily volume alone does not dictate a broker. Consider burstiness, durability, ownership, DB headroom, and multi-consumer needs; a DB outbox suffices at many scales.

**When should we use a transactional outbox?** Whenever a business update and send intent must commit atomically and losing an email on process death is unacceptable.

**Is `@TransactionalEventListener(AFTER_COMMIT)` durable enough?** Not by default; crashing right after commit before the listener writes durable state loses the intent. It fits best-effort cases or designs paired with reconciliation.

**When HTTP returns 202, might the email still be unsent?** Yes. Return a notification/job ID and status endpoint, and never label queued work as delivered.

**When a provider throttles, does adding pods help?** Usually not once you hit the provider cap. Smooth bursts, use an account-wide limiter, stagger schedules, or request higher approved quotas.

**Should we create multiple SMTP credentials to bypass quotas?** Not by default. Multiple credentials often share one account/organization budget; never use credential rotation to evade limits.

**How do we stop one large tenant from starving others?** Combine account and tenant budgets, lane/cost-aware fair scheduling, bounded worker queues, and reserved capacity.

**Can we pass a one-shot InputStream for attachments?** Avoid doing so when MIME serialization may read multiple times. Use byte arrays for small files or reopenable stream sources backed by immutable payloads.

**Is counting total PENDING rows an accurate backlog metric?** Not alone. Separate future-scheduled, currently due, and quota/retry-deferred rows, and measure oldest due age.

**Why track p99?** Even a small fraction of hanging SMTP calls can occupy worker slots and stall queues despite a low average.

**How do we confirm the DB is the bottleneck?** Inspect query plans, lock waits, connection pool saturation, insert/claim/update latency, CPU/IOPS, and scaling trends—never guess from row counts alone.

**Should raw MIME be stored in the database?** Only with clear justification and strict security/retention; normally store intents, payload references, and submission metadata to minimize PII exposure.

**Can we guarantee exactly-once email delivery?** Not strictly over plain SMTP across all network and DB failures. You can prevent duplicate business intents and minimize duplicates through reconciliation and provider idempotency APIs where supported.

**If SMTP times out, did the email definitely fail to send?** No. Disconnecting after DATA means the provider may have accepted it. Track phases and use UNKNOWN whenever uncertain.

**How many times should we retry?** It depends on mail type, failure class, deadlines, and provider policy. Never retry infinitely and never send expired OTPs.

**Can `submitted_at` measure delivery time?** No. `submitted_at` marks SMTP acceptance; only provider delivery feedback supports `delivered_at`.

**Why do SMTP sink load tests differ from production?** Sinks lack real reputation checks, spam filters, and quotas, and have different latency profiles. Report app-side capacity separately from provider-constrained capacity.

**Is a single benchmark run sufficient?** Rarely. Include warm-ups, sustained durations, repeated runs, realistic mixes, p95/p99, variance, and documented environment conditions.

**Do we need a 24-hour load test?** Risk-dependent—especially when validating daily quotas, retention jobs, memory leaks, or recurring schedules. Long soak tests catch issues short benchmarks miss.

**Should the app fail open if the Redis rate limiter goes down?** Not by default. With a durable outbox, failing closed preserves intents and avoids flooding providers; any fallback needs a cluster-wide bounded budget.

**Does scaling SMTP workers separately help?** Yes when web traffic and mail workloads have different CPU or failure profiles, though accepted throughput rises only if provider, DB, and rate gates still have headroom.

**How do we know when to switch providers?** Measure quotas, acceptance ratios, bounce/delivery rates, latency, outage behavior, cost, and SLA compliance—never decide from thread counts or a single 4xx.

**If overloading drops zero jobs, did the system pass?** Not necessarily. If OTPs expire from delay, backlogs fail to drain, or fairness breaks, SLOs still fail.

**What should a report write for unmeasured metrics?** Write `NOT_MEASURED`, state assumptions and analytical estimates, list needed measurements, and refrain from claiming verified capacity.

## 50. Summary: Claim Scalability Only with Evidence

Evaluating the scalability of a **Spring Framework Mail project** goes far beyond counting `JavaMailSender.send(...)` calls per second. Examine the full lifecycle:

~~~text
Business demand / scheduled arrivals
                  |
                  v
    API / notification intent
                  |
                  v
         Durable outbox
                  |
                  v
      Claim / dispatch / queue
                  |
                  v
      Eligibility + fair policy
                  |
                  v
      Account/tenant rate gates
                  |
                  v
         SMTP concurrency
                  |
                  v
   MIME rendering + JavaMailSender
                  |
                  v
       Provider SMTP accepted
                  |
                  v
   Delivery feedback if available
~~~

At every stage, define **units, limits, failure states, and data sources**:

| Final Question | Evidence-Based Answer |
|---|---|
| How much work can the project sustain? | Offered load, accepted throughput, and SLOs per workload |
| Where is the primary bottleneck? | Compare component metrics, quotas, saturation, query plans |
| Does scaling replicas help? | Compare throughput, p95/p99, and cost across 1, 2, 4 replicas |
| Do bursts lose jobs? | Durable outbox + stress and restart tests |
| Are duplicates sent? | Idempotency, ownership, and ambiguous-outcome tests |
| Can provider quotas be exceeded? | Account/tenant admission control in exact cost units |
| Does bulk block critical mail? | Fairness/lane tests and oldest due age |
| Are large attachments safe? | Heap/GC trends, size caps, streaming, retention |
| Do provider outages recover cleanly? | Fault injection and backlog drain measurements |
| Can operations support it? | Explicit states, audits, metrics, alerts, and runbooks |
| Which limits remain unknown? | Explicit `NOT_MEASURED` list and verification plan |

Three guiding principles:

1. **Scalability exists only within a stated workload envelope.** An app handling single-recipient text cleanly may crumble under large attachments, fan-out, or bulk tenant bursts.
2. **Real bottlenecks dictate capacity.** If provider quota is 20 recipients/s, adding CPU and replicas adds zero quota. If template rendering saturates CPU, adding mail providers will not fix CPU-bound code.
3. **Throughput never trades away reliability or safety.** Fast pipelines that drop committed intents, blindly retry UNKNOWN SMTP outcomes, deliver expired OTPs, or leak PII fail the requirements.

### Practice Deliverable

Conclude with a **verifiable assessment report**, not just a brief opinion:

- Actual architecture diagram and boundaries.
- Table of load assumptions, provider quotas, and test environment.
- SLOs with crisp SLI definitions.
- Benchmark, load, stress, and failure-injection scenarios.
- Measured results tables and charts where collected.
- Bottleneck analysis and conditional backlog/capacity forecasts.
- Risk register and unverified limits.
- Improvement roadmap prioritized by impact and cost.

If your project is currently a demo lacking an outbox, multi-worker ownership, or delivery feedback, state those explicitly as **current limits**, outline the upgrade path, and define measurements before scaling. That transparency delivers far greater engineering value than slapping on a "production-ready" label.

**Conclusion:** A well-scaling Spring Mail project does more than send emails faster; it knows **when sending is allowed**, **holds work safely while waiting**, **recovers cleanly after incidents**, **protects quotas and every tenant**, and **backs every throughput, latency, and reliability claim with evidence**.
