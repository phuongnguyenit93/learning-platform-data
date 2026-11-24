# Sending Immediately vs. Sending at a Requested Time in Spring Framework Mail

An application does not always send an email at the exact moment a user clicks a button. Some messages need to be sent **as soon as a business event occurs**, such as a registration confirmation email, an OTP, or a payment notification. However, there are also messages users want to **send at a specific scheduled time**, such as a reminder tomorrow at 9:00 AM, a follow-up email after 7 days, or a periodic report with a chosen release time.

In **Spring Framework Mail**, `JavaMailSender` is responsible for establishing the connection and **submitting** the message to the SMTP relay; it is not a persistent store for send schedules. Therefore, the question of "send immediately or send at a requested time" must be resolved **before the SMTP call**: accepting the request, determining the send time, persisting durable state, dispatching a worker when due, checking that conditions are still valid, and only then calling `JavaMailSender.send(...)`.

This article covers everything from business requirements to Spring Boot implementation: distinguishing immediate sending from scheduled sending; handling `Instant`, timezones, and DST; designing the API; `TaskScheduler` and `@Scheduled`; transactional outbox, database polling, and multiple instances; cancellation/rescheduling; SMTP timeouts, retries, and avoiding duplicates; testing and operations.

> Fundamental principle: **"Send immediately" means placing a valid request into the sending pipeline with appropriate priority; "send at 09:00" means not starting submission before the agreed time.** Neither guarantees that the email will appear in the recipient's Inbox at that exact moment, because the SMTP relay and the receiving system can still queue or delay delivery.

## 1. Two Types of Mail Sending Requests

### 1.1. Send immediately (send now)

A user or a business event requests sending as soon as appropriate:

- Sending a login verification code.
- Sending an order confirmation notification after the transaction commits.
- Sending a password reset email.
- Sending a receipt when a payment occurs.
- Sending an urgent alert based on system rules.

"Immediately" does not necessarily mean calling SMTP directly inside the HTTP request. A good design typically **writes the request to an outbox**, returns a response to the user, and lets a worker send it shortly afterward. This allows the system to still record the transaction even if the SMTP provider is failing.

### 1.2. Send at a requested time (send at)

A user or business service provides a meaningful point in time:

- "Send a reminder at 09:00 tomorrow in the recipient's local time."
- "Send the report when the accounting period closes."
- "Send an appointment reminder email 30 minutes before the meeting."
- "Send the campaign at 08:30 in each region's timezone."
- "Send the approved draft on the publication date."

Unlike send now, the coordinator must **not release the job before its due time**, while also having policies for when a worker is delayed, the application restarts, the date/time is changed, or the message expires.

### 1.3. Comparison table

| Criterion | Send immediately | Send at a scheduled time |
| --- | --- | --- |
| Earliest time sending is allowed to start | As soon as the request is valid and committed | No earlier than `scheduledAt` |
| Need to store a schedule? | Can store in outbox with the current timestamp | Needs a UTC/`Instant` timestamp and time context |
| Depends on synchronous SMTP in HTTP? | Should not be required | No |
| Can it experience queue delay? | Yes | Yes |
| Supports cancel/reschedule? | Depends on state; very short window | Should provide cancel/reschedule APIs before dispatch |
| When the application restarts | The request must be preserved | The schedule must be preserved |
| When SMTP connection is lost | Retry or hold per policy | Retry or hold, while considering deadline/expiry |
| Meaning of `send()` succeeding | Relay accepted submission | Relay accepted submission, not delivered |
| Primary verification milestone | Time from enqueue to submit | No early submission and lateness relative to the planned time |

Do not treat a `202 Accepted` HTTP response as meaning the email has been sent. It only confirms that the system has **accepted the request**, depending on the API contract.

## 2. Three Timestamps That Are Frequently Confused

An email has at least three time milestones:

~~~text
T0: User requests sending (requestedAt)
    |
    v
T1: Due time reached and worker starts sending (dispatchStartedAt)
    |
    v
T2: SMTP relay accepted after DATA (submittedAt)
    |
    v
T3: Provider/remote MX communicates, retries, and may report delivered/bounced
~~~

For send now, `scheduledAt` can equal the time the request is recorded (`requestedAt`). For send later, `scheduledAt` may be minutes or weeks after `requestedAt`. **Do not conflate `scheduledAt`, `submittedAt`, and `deliveredAt`**. 

### What can be guaranteed

An application can be designed to:

- Never proactively start sending a message whose `scheduledAt` is in the future.
- Persist send schedules and recover after a restart.
- Clearly record when a job becomes due, is claimed, and its submission result.
- Enforce limits on lateness, retries, and expiry.
- Ensure only one worker holds a job's lease at any given time.

### What cannot be strictly guaranteed by Spring Mail alone

- That the email reaches the recipient's mailbox down to the exact millisecond.
- That the relay will not queue, defer, or bounce the message.
- Exactly-once end-to-end email delivery in every connection-loss scenario.
- That the recipient actually read the email.

SMTP is a distributed system where outcomes can be uncertain at certain moments. If the final reply after DATA is lost, the relay may have accepted the message even though the application sees an exception. This issue must be factored into retry and scheduling design.

## 3. Defining What "On Time" Means

Users may express requests in different ways:

| Phrasing | Meaning to define |
| --- | --- |
| "Send now" | The queue is ready to process it at the current time |
| "Send on 2026-11-20 at 09:00 Vietnam time" | A local date-time with timezone `Asia/Ho_Chi_Minh` |
| "Send in 30 minutes" | Relative delay calculated from a defined reference point |
| "Send 15 minutes before the appointment" | Time derived from a source event; must update when the event changes |
| "Send at 08:00 in the recipient's local time" | Compute an individual `Instant` per recipient's zone |
| "Send on the last day of the month" | Calendar rule; requires calendar/business timezone |
| "Send before X or do not send" | Has a deadline/expiry; can be cancelled if late |

A system should explicitly specify:

1. `scheduledAt` is the **earliest time submission is allowed**, not an Inbox delivery guarantee.
2. Whether late sending is accepted, and what the maximum allowed lateness is.
3. Whether schedules in the past are accepted.
4. Which timezone the time is interpreted in.
5. Whether rescheduling/cancellation is allowed once a message has been claimed.
6. If SMTP is failing, whether retries can exceed the useful lifetime of the content.
7. Who is authorized to create/modify/cancel schedules for a tenant or recipient.

Answering these questions upfront determines how the API and database are designed, rather than just picking a Spring annotation.

## 4. Using Instant to Store Absolute Send Times

Java Time types serve distinct roles:

| Type | Representation | When to use |
| --- | --- | --- |
| `Instant` | A point on the UTC timeline | Storing `scheduledAt`, comparing due jobs |
| `OffsetDateTime` | Local date-time with an offset like `+07:00` | APIs passing timestamps with an explicit offset |
| `ZonedDateTime` | Date-time bound to zone rules like `Asia/Ho_Chi_Minh` | Interpreting local time, calendar rules |
| `LocalDateTime` | Date and time without timezone/offset | UI forms when passing a separate timezone |
| `LocalDate` | Calendar date | Daily reminders, due dates |
| `Duration` | Absolute elapsed time | "After 30 minutes", retry backoff |
| `Period` | Calendar-based amount of time | "After 1 month", not a fixed number of seconds |
| `Clock` | Injectable time source | Logic and tests decoupled from the system clock |

**Recommendation:** store a single execution timestamp as an `Instant` in the database (using a timestamp column/driver with verified UTC semantics), while also storing `zoneId` and the original local date-time if needed for display or calendar-rule updates.

### Example: sending at 09:00 in Vietnam

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDateTime requested =
        LocalDateTime.of(2026, 11, 20, 9, 0);

Instant scheduledAt =
        requested.atZone(vietnam).toInstant();

System.out.println(scheduledAt);
// 2026-11-20T02:00:00Z
~~~

Storing `2026-11-20T02:00:00Z` means a worker in any server timezone can compare `Instant.now(clock)` against the exact same point in time.

### Do not infer timezone from the server

If an API receives `2026-11-20T09:00:00` (without an offset), the application **cannot know** whether that means 9:00 AM in Vietnam, UTC, or New York unless another contract specifies it. Do not rely on `ZoneId.systemDefault()` to interpret user schedules; deploying to another region could shift send times.

### API using a concrete Instant

~~~json
{
  "mode": "AT",
  "scheduledAt": "2026-11-20T02:00:00Z",
  "recipientId": "recipient-42",
  "templateKey": "appointment-reminder",
  "idempotencyKey": "reminder-appointment-184-v1"
}
~~~

This approach works well when the client has already converted local date-time + timezone into the exact UTC timestamp. The API should also return `zoneId`/local formatting so the user can see the scheduled time clearly.

## 5. Timezones and DST: A Local Time Can Be Ambiguous

Not every timezone has a fixed offset year-round. Some regions observe **Daylight Saving Time (DST)**, causing:

- A local time range **not to exist** when clocks spring forward.
- A local time range **to occur twice** when clocks fall back.

For example, in `America/New_York` in 2026 (under current DST rules):

- `2026-03-08 02:30` does not exist in local time because clocks jump from 02:00 to 03:00.
- `2026-11-01 01:30` can map to two different UTC instants.

If you only call `localDateTime.atZone(zone)`, Java applies default rules to adjust during gaps/overlaps, which may not match user intent. For schedules requiring precision, **require the UI/API to disambiguate**.

### Validating whether a local date-time is valid

~~~java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

public final class ScheduleTimeResolver {

    public static Instant resolve(
            LocalDateTime local,
            ZoneId zone,
            ZoneOffset selectedOffset) {

        List<ZoneOffset> valid =
                zone.getRules().getValidOffsets(local);

        if (valid.isEmpty()) {
            throw new IllegalArgumentException(
                    "Local time does not exist in selected zone");
        }

        if (valid.size() > 1 && selectedOffset == null) {
            throw new IllegalArgumentException(
                    "Local time is ambiguous; select offset");
        }

        ZoneOffset offset =
                selectedOffset == null ? valid.get(0) : selectedOffset;

        if (!valid.contains(offset)) {
            throw new IllegalArgumentException(
                    "Offset is invalid for this local time");
        }

        return local.atOffset(offset).toInstant();
    }
}
~~~

For Vietnam time today, DST is not a daily concern; however, a global email service must not assume every recipient is in UTC+7.

### Relative delay and calendar-based scheduling differ

`Duration.ofHours(24)` is always 24 absolute hours. "Same time tomorrow in local time" may not be exactly 24 hours apart in a timezone with DST. For "tomorrow at 9:00 AM", use local date/time plus timezone rules; for "after exactly 24 hours", use `Instant.plus(Duration.ofHours(24))`.

## 6. Choosing the API Contract: NOW vs. AT

An API should explicitly represent the user's choice instead of using a meaningless `null`:

~~~json
{
  "mode": "NOW",
  "recipientId": "recipient-42",
  "templateKey": "payment-confirmed",
  "templateData": {
    "orderId": "ord-184"
  },
  "idempotencyKey": "payment-confirmed-ord-184"
}
~~~

For a schedule in local time:

~~~json
{
  "mode": "AT",
  "recipientId": "recipient-42",
  "templateKey": "appointment-reminder",
  "localDateTime": "2026-11-20T09:00:00",
  "zoneId": "Asia/Ho_Chi_Minh",
  "idempotencyKey": "reminder-appointment-184-v1"
}
~~~

The server interprets `localDateTime` using `zoneId`, validates DST rules, converts to an `Instant`, and stores the original time too if required by business rules.

### Input validation

| Field | Condition |
| --- | --- |
| `mode` | Only `NOW` or `AT` in this API |
| `recipientId` | Exists, matches tenant, caller has permission to send |
| `templateKey` | In allowlist and permitted for the message category |
| `templateData` | Matches schema, contains no secrets or arbitrary HTML |
| `localDateTime` and `zoneId` | Required for AT, unambiguous |
| `idempotencyKey` | Unique per tenant/business source, reasonable length |
| Scheduling window | Not in the past if forbidden by policy; not too far in the future |
| `expiresAt` | If present, must be later than `scheduledAt` |
| Recipient preference | Not suppressed or missing consent at schedule creation time |

### Do not silently turn a past AT into NOW

If a user picks a time that has already passed, the clear options are:

- Return a validation error so the user can fix it.
- Or allow a small tolerance window per policy (e.g., network/client lag) and record that it was sent as "late send".
- For import/recovery jobs, use a separate privileged and audited API.

Do not silently turn a schedule for "last Monday" into immediate sending, because it could be a timezone mistake or user error.

## 7. Should Send Now Call JavaMailSender Directly Inside HTTP?

An easy-to-understand synchronous example:

~~~java
@PostMapping("/mail/send-now")
public ResponseEntity<Void> sendNow(@RequestBody MailRequest request) {
    mailService.send(request);
    return ResponseEntity.noContent().build();
}
~~~

However, it carries many risks:

- SMTP connect/read/write can take several seconds or time out.
- During an SMTP outage, the HTTP request fails even if the business transaction succeeded.
- HTTP client retries can generate duplicate emails.
- If a database transaction is open, it can hold locks while waiting on the network.
- If the relay accepted the message before the client received a response, the outcome becomes uncertain.

### A more suitable design for business workflows

~~~text
HTTP request / business event
        |
        v
Validate + authorize
        |
        v
Persist notification/outbox in transaction
        |
        v
HTTP 202 Accepted / business transaction committed
        |
        v
Background dispatcher selects due jobs
        |
        v
JavaMailSender.send(...)
        |
        v
Persist submission result / retry policy
~~~

`202 Accepted` can include an ID and a status endpoint. If the send request is tied to a transaction such as a payment, the email request record should be written **in the same transaction** as the business change to avoid recording a successful payment while losing the email request.

### When might direct sending still be acceptable?

For small internal tools that do not require durable scheduling, have low email volume, and accept HTTP waiting on SMTP, direct calls may suffice. Even then, you still need timeouts, concurrency limits, error interpretation, and protection against blind client retries. However, a synchronous model does not solve **sending after a server restart** or **scheduling for a future date**.

## 8. `TaskScheduler` and `@Scheduled`: Different Responsibilities

Spring offers several scheduling mechanisms; pick the right one:

| Tool | Suitable for | Limitations to understand |
| --- | --- | --- |
| `TaskScheduler.schedule(Runnable, Instant)` | Scheduling a single in-process task at a specific time | If the process restarts, in-memory schedules vanish |
| `@Scheduled(fixedDelay=...)` | Periodically polling due jobs | Does not store jobs itself; requires a durable repository |
| `@Scheduled(cron=...)` | Recurring tasks on a fixed calendar schedule | Not suitable for storing millions of distinct user-chosen timestamps |
| Quartz with JDBC JobStore | Durable schedules, complex triggers/recovery | Requires designing JobStore, clustering, and task behavior |
| Delayed message queue | Broker-managed delayed message delivery | Requires verifying delay limits, durability, and redelivery |
| Database outbox + polling | Immediate and scheduled sending with persistence | Requires polling, claim/lease, and retry |

For **sending a single email at a user-chosen time**, `@Scheduled(cron="0 0 9 * * *")` cannot represent a separate `scheduledAt` per recipient. Cron is meant for **recurring schedulers**, not user-specific schedule records that can be cancelled or rescheduled.

### Illustrating an in-memory TaskScheduler

~~~java
import java.time.Instant;
import org.springframework.scheduling.TaskScheduler;

public final class InMemoryMailSchedule {
    private final TaskScheduler scheduler;
    private final Runnable mailTask;

    public InMemoryMailSchedule(
            TaskScheduler scheduler, Runnable mailTask) {
        this.scheduler = scheduler;
        this.mailTask = mailTask;
    }

    public void scheduleOnce(Instant when) {
        scheduler.schedule(mailTask, when);
    }
}
~~~

This code only illustrates the one-shot scheduling API; **do not use it as the sole store for critical email requests**. If the JVM stops before `when`, there is no built-in mechanism to restore the schedule. In a multi-instance setup, each instance also has its own scheduler and can cause duplicates if the same job is re-registered.

## 9. Recommended Model: One Outbox for Both NOW and AT

Instead of two independent systems, you can use the **same send-request table**:

~~~text
Send NOW:
    scheduledAt = clock.instant()
           |
           v
      durable outbox

Send AT:
    scheduledAt = user-selected Instant
           |
           v
      same durable outbox

Worker:
    find records with scheduledAt <= now
    and state is dispatchable
           |
           v
    claim -> validate -> send -> persist result
~~~

Benefits:

- Shared validation, idempotency, retry, suppression, and metrics.
- Future schedules are not lost when the process restarts.
- Schedules can be cancelled/rescheduled via the database before dispatch.
- One worker handles both "immediate" and "scheduled" emails according to priority.
- Supports multi-instance deployment with a safe claiming mechanism.

### Distinguishing `scheduledAt` and `nextAttemptAt`

`scheduledAt` is the business time allowing the **first send attempt**. `nextAttemptAt` is the time a worker may retry after a temporary failure.

A job scheduled for November 20 at 09:00 might look like:

~~~text
scheduledAt     = 2026-11-20T02:00:00Z
firstAttemptAt  = 2026-11-20T02:00:05Z
result          = temporary SMTP error
nextAttemptAt   = 2026-11-20T02:02:05Z
~~~

Do not overwrite `scheduledAt` with the retry time if you want to measure adherence to the user-requested schedule accurately. The worker can use `availableAt = max(scheduledAt, nextAttemptAt)` or store a separate `availableAt` column to query due jobs.

## 10. Designing a Durable Schedule Table

A minimal relational model needs to store:

- Who created the request, and which tenant/message category it belongs to.
- The recipient and content/template to send.
- NOW/AT mode, the original user-selected time, and the UTC timestamp.
- Status: pending/processing/submitted/temporary failure/cancelled/expired.
- Idempotency key.
- Last send attempt, next retry time, lease owner, and version.
- SMTP outcome and stop reason (when applicable).

### Example PostgreSQL schema

~~~sql
CREATE TABLE mail_schedule (
    id                  UUID PRIMARY KEY,
    tenant_id           VARCHAR(100) NOT NULL,
    idempotency_key     VARCHAR(250) NOT NULL,
    recipient_id        VARCHAR(100) NOT NULL,
    template_key        VARCHAR(150) NOT NULL,
    payload_json        JSONB NOT NULL,
    payload_version     INTEGER NOT NULL DEFAULT 1,

    mode                VARCHAR(10) NOT NULL,
    scheduled_at        TIMESTAMPTZ NOT NULL,
    requested_local_at  TIMESTAMP,
    requested_zone_id   VARCHAR(100),
    available_at        TIMESTAMPTZ NOT NULL,
    expires_at          TIMESTAMPTZ,

    status              VARCHAR(40) NOT NULL,
    priority            INTEGER NOT NULL DEFAULT 0,
    attempts            INTEGER NOT NULL DEFAULT 0,
    max_attempts        INTEGER NOT NULL DEFAULT 5,
    lease_owner         VARCHAR(150),
    lease_until         TIMESTAMPTZ,
    generation          BIGINT NOT NULL DEFAULT 0,
    stop_reason         VARCHAR(100),

    created_at          TIMESTAMPTZ NOT NULL,
    updated_at          TIMESTAMPTZ NOT NULL,
    submitted_at        TIMESTAMPTZ,

    CONSTRAINT mail_schedule_idempotent
        UNIQUE (tenant_id, idempotency_key),
    CONSTRAINT mail_schedule_mode_chk
        CHECK (mode IN ('NOW', 'AT')),
    CONSTRAINT mail_schedule_attempts_chk
        CHECK (attempts >= 0 AND max_attempts > 0),
    CONSTRAINT mail_schedule_expiry_chk
        CHECK (expires_at IS NULL OR expires_at > scheduled_at)
);

CREATE INDEX idx_mail_schedule_due
    ON mail_schedule (available_at, priority DESC, created_at)
    WHERE status IN ('PENDING', 'RETRY_PENDING');
~~~

This is an **illustrative schema**, not a schema automatically created by Spring Mail. You need to add authorization/audit, encryption, indexes, retention, and constraints suited to a real system. PostgreSQL `TIMESTAMPTZ` represents a timezone-aware instant; it **does not store the original IANA timezone name**, so if you need to display "09:00 Asia/Ho_Chi_Minh", store `requested_zone_id` and local time when required.

### Do not store raw emails indefinitely in `payload_json`

If the payload contains PII, OTPs, reset URLs, sensitive data, or attachments, consider:

- Storing a template ID and business reference instead of raw secrets.
- Encrypting payloads where needed, with clear access control and retention.
- Separating attachments into immutable object storage, checking permissions and size.
- Never storing plaintext passwords/tokens.
- Avoiding re-rendering mutable data in ways that alter business meaning.

For example, an invoice send request can reference `invoiceVersion` and an immutable document; it should not reference a temporary file that auto-deletes before `scheduledAt`.

### Store timestamps with consistent precision

The database, Java, and frontend may have different precisions (milliseconds, microseconds, etc.). When testing "no early send", define rounding and comparison rules. Do not let the frontend display minute precision while the database stores a timestamp accidentally truncated down by several minutes.

## 11. State Machine: From Send Request to SMTP Outcome

A send schedule typically needs more states than just `SCHEDULED/SENT`:

~~~mermaid
flowchart TD
    A["PENDING"] --> B["PROCESSING"]
    A --> C["CANCELLED"]
    A --> D["EXPIRED"]
    B --> E{"Submission result"}
    E -- "SMTP accepted" --> F["SUBMITTED"]
    E -- "Temporary failure, safe to retry" --> G["RETRY_PENDING"]
    E -- "Permanent failure" --> H["FAILED_PERMANENT"]
    E -- "Outcome unclear" --> I["SUBMISSION_UNKNOWN"]
    G --> B
    G --> C
    G --> D
    I --> J["Reconciliation / manual decision"]
~~~

These states are **application-defined**, not default statuses in Spring Mail. You can use `SCHEDULED` to represent `PENDING` with `scheduledAt > now`, though storing a unified enum and timestamp is usually simpler.

### State transition rules

| Current state | Action | Result |
| --- | --- | --- |
| PENDING, not yet due | Worker polls | Not claimed |
| PENDING, due | Worker claims atomically | PROCESSING |
| PENDING, user cancels | Authorized cancellation | CANCELLED |
| PENDING, rescheduled | Versioned timestamp update | Remains PENDING |
| RETRY_PENDING, not yet due for retry | Worker polls | Not claimed |
| RETRY_PENDING, due | Worker claims | PROCESSING |
| PROCESSING, SMTP accepted | Record final 250 or explicit provider result | SUBMITTED |
| PROCESSING, temporary error before submit | Retry policy | RETRY_PENDING |
| PROCESSING, permanent recipient/content error | Stop | FAILED_PERMANENT |
| PROCESSING, final reply lost after DATA | Unknown | SUBMISSION_UNKNOWN |
| PENDING/RETRY_PENDING, expired | Expiry policy | EXPIRED |
| SUBMITTED, cancel requested | Cannot promise recall | Return conflict / already-sent status |

Some queues and providers can cancel/edit a job that was accepted but not yet actually transmitted; without such proof, **never report "definitely cancelled" once a worker has started SMTP**.

## 12. Creating a Send Request Within a Transaction

A schedule-creation service should:

1. Authenticate the caller and tenant.
2. Verify permission to send to the recipient, template, and email category.
3. Resolve NOW/AT, timezone, expiry, and advance-booking limits.
4. Select the payload version or template data to preserve.
5. Create/check the idempotency key for duplicates.
6. Insert a `PENDING` record within the transaction.
7. Commit before any worker can dispatch it.
8. Return the accepted ID/status.

### Java domain command

~~~java
package com.example.mail.schedule;

import java.time.Instant;
import java.util.Map;

public enum ScheduleMode { NOW, AT }

public record CreateMailSchedule(
        String tenantId,
        String recipientId,
        String templateKey,
        Map<String, Object> templateData,
        ScheduleMode mode,
        Instant scheduledAt,
        Instant expiresAt,
        String idempotencyKey) {
}
~~~

`scheduledAt` in the record above has already been converted from local date-time to `Instant` at the API boundary. In NOW mode, the service uses the time from `Clock` rather than trusting a client-supplied timestamp. `Map<String,Object>` is only illustrative; production should use a constrained DTO/schema and not accept arbitrary objects.

### Separating time-calculation logic

~~~java
package com.example.mail.schedule;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public final class ScheduleValidator {

    private final Clock clock;
    private final Duration maxAdvance;

    public ScheduleValidator(Clock clock, Duration maxAdvance) {
        this.clock = clock;
        this.maxAdvance = maxAdvance;
    }

    public Instant computeScheduledAt(CreateMailSchedule command) {
        Instant now = clock.instant();

        if (command.mode() == ScheduleMode.NOW) {
            return now;
        }
        if (command.mode() != ScheduleMode.AT
                || command.scheduledAt() == null) {
            throw new IllegalArgumentException(
                    "AT mode requires scheduledAt");
        }

        Instant requested = command.scheduledAt();
        if (requested.isBefore(now)) {
            throw new IllegalArgumentException(
                    "Cannot schedule in the past");
        }
        if (requested.isAfter(now.plus(maxAdvance))) {
            throw new IllegalArgumentException(
                    "Requested time is too far away");
        }
        if (command.expiresAt() != null
                && !command.expiresAt().isAfter(requested)) {
            throw new IllegalArgumentException(
                    "expiresAt must be after scheduledAt");
        }
        return requested;
    }
}
~~~

Using `Clock` enables testing boundary times without `Thread.sleep()`. For NOW mode, `expiresAt` and business preconditions must also be checked in the service outside `computeScheduledAt`; this example intentionally illustrates only schedule calculation.

### Writing the outbox alongside business logic

~~~java
@Transactional
public Order confirmPayment(PaymentEvent event) {
    Order order = orderRepository.markPaid(
            event.orderId(), event.paymentId());

    mailScheduleRepository.insertPending(
            MailSchedule.pendingNow(
                    order.getTenantId(),
                    order.getCustomerId(),
                    "payment-confirmed",
                    order.getId().toString(),
                    clock.instant()));

    return order;
}
~~~

Names like `MailSchedule` and `MailScheduleRepository` in the example are application types. The key point is **writing business data and the send request in the same database transaction**, rather than calling SMTP inside a transaction and hoping two systems commit together.

### When a scheduled email originates from a standalone action

For a user-scheduled marketing email, the API may simply insert the `mail_schedule` record and return `202 Accepted`. For a payment confirmation email, the outbox record must stay synchronized with the payment transaction; there is no need to create a separate transaction just to make the HTTP request return faster.

## 13. Idempotency When Creating Schedules

A client may resend the same HTTP request due to a timeout; if each retry creates a new schedule, the recipient receives multiple emails.

Example request:

~~~http
POST /api/mail-schedules
Idempotency-Key: receipt-order-184
Content-Type: application/json

{"mode":"NOW","recipientId":"recipient-42","templateKey":"receipt"}
~~~

Recommended rules:

- Unique key scoped by tenant/operation.
- If the same key and same payload were already accepted, return the existing record's ID.
- If the same key is sent with a different payload, return a conflict (e.g., HTTP 409).
- Do not share one global key namespace across all users/tenants.
- Store a hash of the valid request or version logic to compare.
- If the job is already `SUBMITTED`, a duplicate-key API call must not create a new send.

A database **unique constraint** is the last line of defense when two requests arrive concurrently. A `findByKey()` check before `insert()` is not enough to prevent races without a unique constraint or atomic upsert.

### Idempotency is not exactly-once SMTP

This key prevents duplicate business requests, but if a worker already submitted via SMTP and crashed before persisting the status, recovery may repeat the submission. Separate attempt tracking and a `SUBMISSION_UNKNOWN` policy are required.

## 14. A Spring REST Endpoint for NOW/AT

Example API interface using an already-resolved UTC timestamp:

~~~java
package com.example.mail.schedule;

import java.time.Instant;
import java.util.UUID;

public record ScheduleMailRequest(
        ScheduleMode mode,
        Instant scheduledAt,
        String recipientId,
        String templateKey,
        String idempotencyKey) {
}

public record ScheduleMailResponse(
        UUID id,
        String status,
        Instant scheduledAt) {
}
~~~

~~~java
package com.example.mail.schedule;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/mail-schedules")
public class MailScheduleController {

    private final MailScheduleService service;

    public MailScheduleController(MailScheduleService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<ScheduleMailResponse> create(
            @RequestBody ScheduleMailRequest request) {

        ScheduleMailResponse result = service.create(request);
        return ResponseEntity.accepted().body(result);
    }
}
~~~

`MailScheduleService` is an application class not defined in the example. In a real implementation, `tenantId` must be derived from the authenticated context—never trust a tenant ID sent in the request body. Add Bean Validation, authorization, `Idempotency-Key` policy, request size limits, and meaningful exception-to-HTTP status mapping.

### Meaningful response

~~~json
{
  "id": "a1a6d179-3cb2-47e7-bb2f-d34eebeb5ac1",
  "status": "PENDING",
  "scheduledAt": "2026-11-20T02:00:00Z"
}
~~~

Even for NOW, the response may still be `PENDING` briefly until the worker sends it. The UI should display "Scheduled for sending" or "Queued for sending", not "Delivered successfully" based solely on HTTP 202.

## 15. Polling Worker: Finding Due Jobs

A simple approach uses `@Scheduled(fixedDelayString=...)` to run the worker periodically:

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class DueMailPoller {

    private final MailDispatchService dispatcher;

    public DueMailPoller(MailDispatchService dispatcher) {
        this.dispatcher = dispatcher;
    }

    @Scheduled(fixedDelayString = "PT1S")
    public void dispatchDueMail() {
        dispatcher.dispatchDueBatch();
    }
}
~~~

With Spring scheduling, you must enable scheduling in the appropriate Spring configuration (e.g., `@EnableScheduling`) if the app does not have it yet. Duration string syntax and `@Scheduled` attributes should be checked against your Spring version; you can also use milliseconds like `fixedDelayString = "1000"` to make the unit explicit. **This is merely a timer that triggers the dispatcher**, not the storage for email schedules.

### Fixed delay vs. fixed rate

- `fixedDelay`: waits a specified interval after the previous run finishes.
- `fixedRate`: attempts to run on a cadence from start time, depending on the scheduler/executor.
- `cron`: recurring calendar-based schedule with timezone semantics.

If a poll takes too long because of synchronous SMTP calls, `fixedDelay` can delay discovery of newly due jobs. A better design is to poll to **claim a bounded batch**, then hand off work to a bounded executor/worker pool without holding a database transaction open during SMTP calls.

### Polling every second does not mean exact second-level delivery

Actual latency depends on:

- Poll interval.
- Scheduler thread pool and CPU.
- Database query/lock contention.
- Number of jobs becoming due simultaneously.
- Worker concurrency and provider quota.
- SMTP connection and network.

If stricter guarantees are needed, define SLOs and an appropriate queue/scheduler architecture. A 100 ms timer cannot guarantee Inbox delivery within 100 ms.

## 16. Preventing Two Workers From Sending the Same Job

Production typically runs multiple replicas. If every instance runs a query like:

~~~sql
SELECT *
FROM mail_schedule
WHERE status = 'PENDING'
  AND scheduled_at <= CURRENT_TIMESTAMP;
~~~

and then calls SMTP, **two workers can read the same record and both send it**. Atomic claiming in the database is required.

### PostgreSQL `FOR UPDATE SKIP LOCKED`

One way to claim a batch is:

~~~sql
BEGIN;

WITH due AS (
    SELECT id
    FROM mail_schedule
    WHERE status IN ('PENDING', 'RETRY_PENDING')
      AND available_at <= CURRENT_TIMESTAMP
      AND scheduled_at <= CURRENT_TIMESTAMP
      AND (expires_at IS NULL
           OR expires_at > CURRENT_TIMESTAMP)
    ORDER BY priority DESC, available_at, created_at
    LIMIT 20
    FOR UPDATE SKIP LOCKED
)
UPDATE mail_schedule AS m
SET status = 'PROCESSING',
    lease_owner = 'worker-17',
    lease_until = CURRENT_TIMESTAMP + INTERVAL '45 seconds',
    generation = generation + 1,
    updated_at = CURRENT_TIMESTAMP
FROM due
WHERE m.id = due.id
RETURNING m.id,
          m.tenant_id,
          m.recipient_id,
          m.scheduled_at,
          m.generation;

COMMIT;
~~~

This is PostgreSQL-specific SQL. Other databases have different locking mechanisms. In production, `worker-17` must be the current instance's identity; never hardcode the same name for every worker.

### Why must the claim transaction be short?

1. Begin transaction.
2. Select and update records with a lease.
3. Commit transaction.
4. **After commit**, call SMTP outside any database transaction.
5. Persist the outcome in a separate transaction.

Do not hold row locks and open transactions while communicating over SMTP. SMTP can time out; holding transactions causes lock contention and exhausts the database connection pool.

### SKIP LOCKED does not create exactly-once by itself

It prevents **concurrent claiming of the same record** inside the transaction. However, if a worker sends successfully and crashes before updating `SUBMITTED`, recovery can still cause a duplicate. Leases, `SUBMISSION_UNKNOWN`, and reconciliation must be designed separately.

## 17. Leases, Fencing, and Worker Recovery

A `PROCESSING` job can be abandoned when:

- The JVM/pod is killed or restarts.
- An SMTP socket hangs for too long.
- The worker crashes before recording the outcome.
- The database becomes temporarily unavailable after SMTP returned a result.
- A worker loses lease ownership because it exceeded its deadline.

A lease lets the system detect jobs with no active worker, but **it does not mean every expired-lease job is safe to resend immediately**.

### A critical failure window

~~~text
Worker A                   SMTP relay
   |                           |
   |---- message DATA -------->|
   |<--- 250 accepted ---------|
   |                           |
   X process crashes           |
   |                           |
Database still says PROCESSING
   |
Lease expires
   |
Worker B wants to resend
~~~

If Worker B resets the record to PENDING and calls SMTP without reconciliation, the email can be sent twice. To reduce this risk:

- Store **one attempt record per transport call**.
- Attach `startedAt`, `providerKey`, an attempt ID, and `submissionPhase` if the adapter can track it.
- When recovering stale PROCESSING records, distinguish "send not yet called" from "send may have been called".
- For attempts that may have submitted, transition to `SUBMISSION_UNKNOWN` or run reconciliation before auto-retrying.
- If the provider supports message status lookup/idempotency APIs, use them per contract.

### Fencing tokens protect the database, not recall emails

`generation` can act as a fencing token. When a worker writes the outcome, require:

~~~sql
UPDATE mail_schedule
SET status = 'SUBMITTED',
    submitted_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP,
    lease_owner = NULL,
    lease_until = NULL
WHERE id = :id
  AND status = 'PROCESSING'
  AND lease_owner = :workerId
  AND generation = :generation;
~~~

If the updated row count is 0, the worker **must not overwrite** the new state. However, if the worker already sent the email over SMTP, the token cannot "recall" that transmission. That is why fencing and exactly-once external effects are separate concepts.

### Leases must be long enough without masking dead workers

If an SMTP timeout can last 20 seconds, a 5-second lease will expire while the worker is still sending. Use a sufficiently long lease or a controlled heartbeat. If the heartbeat itself fails to reach the database, do not let the worker lose its lease while another worker concurrently sends the same message. When ownership cannot be ensured before calling the transport, stop/defer instead of risking a duplicate.

## 18. Java Worker: Final Checks Before SMTP

A worker must not rely solely on validation done at schedule creation time. Between `PENDING` and submission time, many conditions can change:

- The user cancelled or rescheduled.
- The recipient unsubscribed/complained.
- The email address was updated or is no longer verified.
- An OTP/reset token expired.
- The template or attachment source was revoked.
- The provider/account was suspended or rate-limit quota ran out.
- Permissions of the schedule creator or tenant changed.

A worker workflow might look like:

~~~java
public void dispatch(MailScheduleJob job) {
    // Job has been claimed atomically with a lease/fencing token.
    if (clock.instant().isBefore(job.scheduledAt())) {
        scheduleRepository.deferWithoutAttempt(job.id());
        return;
    }

    if (job.expiresAt() != null
            && !clock.instant().isBefore(job.expiresAt())) {
        scheduleRepository.markExpired(job.id());
        return;
    }

    if (!recipientPolicy.isAllowed(
            job.tenantId(), job.recipientId(), job.category())) {
        scheduleRepository.markSuppressed(job.id());
        return;
    }

    if (!providerLimiter.tryAcquire(job.providerKey())) {
        scheduleRepository.deferForRateLimit(job.id());
        return;
    }

    // Below is only an illustrative sequence.
    // Production requires a fencing/attempt ledger, locking, and timeout handling.
    try {
        MimeMessage message = renderer.prepare(job);
        mailSenderRegistry.get(job.providerKey()).send(message);
        scheduleRepository.markSubmitted(job.id());
    } catch (MailException error) {
        failureHandler.recordAndDecide(job, error);
    }
}
~~~

**This is Java-style pseudocode**: classes like `MailScheduleJob`, repositories, `recipientPolicy`, `providerLimiter`, renderer, sender registry, and failure handler are application components. Calling `send(MimeMessage)` is valid on `JavaMailSender`; using `MimeMessage` requires `jakarta.mail.internet.MimeMessage` and matching imports. The example intentionally avoids promising that every `MailException` can be fully classified by class alone.

### Apply the same fencing to every state update

In production code, `markExpired`, `markSuppressed`, `deferForRateLimit`, `markSubmitted`, and `failureHandler` must all check `leaseOwner/generation`; never execute a bare `UPDATE ... WHERE id=?`. Otherwise, a stale worker could overwrite a user's cancellation or reschedule decision.

### Race limits between "revalidate" and "send"

Even if suppression is checked right before the SMTP call, a user could unsubscribe a few milliseconds later. You need a consistent model for send authorization:

- Explicitly define the start of dispatch/claim as the "in-flight" boundary.
- Synchronize status changes via transactions and fencing.
- If stricter consent is required, use a versioned permit decision/immediate revalidation.
- Once sending has started and an external side effect may occur, the API must not promise absolute cancellation.

There is no simple way to use a single database transaction to lock both email permissions and an SMTP socket with rollback of external sends; you must accept, measure, and communicate this boundary.

## 19. SMTP Errors and Retries for Scheduled Sends

A due message can fail due to:

| Failure | Example | Typical decision |
| --- | --- | --- |
| Transport failed to connect | DNS, TCP refused, connect timeout | Retry with backoff if not expired |
| SMTP server did not respond at EHLO | Read timeout before envelope | Retry with backoff, monitor provider |
| SMTP `421` / `451` | Service temporarily unavailable | Bounded retry, throttling |
| AUTH `535` | Invalid credentials/account permissions | Hold provider lane; do not continuously retry all jobs |
| RCPT `550 5.1.1` | Recipient demonstrably does not exist | Permanent failure/suppression per policy |
| Explicit DATA `554` | Content/policy rejected | Investigate; do not retry blindly |
| Lost final reply after DATA | Unclear whether relay accepted | `SUBMISSION_UNKNOWN`, reconcile |
| SMTP `250` after DATA | Relay accepted | `SUBMITTED`, track delivery |
| Rate limiter denied permit | SMTP not called | Defer, do not count as a physical SMTP attempt |
| Message expired | OTP/offer no longer valid | EXPIRED, do not send |

### A schedule delayed by retries

Example:

~~~text
User requested: 2026-11-20 09:00 Asia/Ho_Chi_Minh
Scheduled UTC:  2026-11-20T02:00:00Z

09:00:00  worker dispatch, SMTP returns temporary 451
09:02:00  retry eligible
09:02:05  relay accepts

requested send time = 09:00
submitted time      = 09:02:05
lateness            = 2 min 05 s
~~~

Do not overwrite the original schedule with 09:02:05. The dashboard needs to show that the user requested 09:00 and the system submitted late due to a temporary error.

### Retry policy must respect expiry

An OTP email may be valid for only 5 minutes; sending it 2 hours later violates business logic. A meeting reminder may be useless once the meeting has started. An invoice email can retry longer. Do not apply the same retry TTL to every category.

~~~java
public boolean mayRetry(
        Instant nextAttempt,
        Instant expiresAt,
        int attempts,
        int maxAttempts) {

    if (attempts >= maxAttempts) {
        return false;
    }
    return expiresAt == null
            || nextAttempt.isBefore(expiresAt);
}
~~~

This is only part of the policy. You must also consider error type, consent, suppression, provider/account health, and prior submission results. A `SUBMISSION_UNKNOWN` outcome must never automatically enter the retry branch just because attempts remain.

## 20. Backoff and Jitter for Failed Schedules

A common formula:

\[
d_n=\min(d_{\max}, d_0\cdot 2^{n-1})+\text{jitter}
\]

Where `n` is the retryable failure count; `d0` is the initial wait and `dmax` is the cap. Jitter prevents thousands of messages from retrying simultaneously after an outage.

Illustrative example:

| Submit attempt | Outcome | Retry schedule |
| --- | --- | --- |
| 1 | Temporary SMTP failure | Wait 30–45 seconds |
| 2 | Temporary SMTP failure | Wait 60–90 seconds |
| 3 | Temporary SMTP failure | Wait 2–3 minutes |
| 4 | Success | Stop retrying, SUBMITTED |
| Budget exhausted | Stop auto-sending | DEAD_LETTER or HOLD per policy |

Values are illustrative only; production values should reflect provider quotas, SLAs, and expiry. Jitter should use a controllable random source in unit tests; do not assert exact timestamps against production randomness.

### Do not sleep inside a worker waiting to retry

Do not do this:

~~~java
try {
    mailSender.send(message);
} catch (MailException exception) {
    Thread.sleep(60_000);
    mailSender.send(message);
}
~~~

This blocks a thread for 60 seconds, can ignore cancellations/expiry, loses the retry schedule on JVM restart, and fails to control the overall retry budget. Instead, persist `availableAt` for the next attempt and release the worker.

### Multi-layer retries

If the adapter retries 3 times, the dispatcher retries 4 times, and a queue also redelivers, actual SMTP calls can exceed 12. Define one total budget per notification and observe physical submit attempts. If the provider already accepted the message and is retrying downstream, **do not create another SMTP submission** just because a `DEFERRED` event appeared.

## 21. Cancelling a Schedule Before Send Time

A user might schedule an email for tomorrow and cancel it before it becomes due. An API is needed:

~~~http
DELETE /api/mail-schedules/{scheduleId}
~~~

However, you must clearly define which states allow cancellation:

| State | Cancel immediately? | Reasonable response |
| --- | --- | --- |
| PENDING | Yes, if caller is authorized | CANCELLED |
| RETRY_PENDING | Yes, if not yet reclaimed | CANCELLED |
| PROCESSING | Cannot guarantee | Conflict, "currently sending", or cancellation-pending with clear semantics |
| SUBMITTED | Cannot recall over SMTP | Already submitted |
| SUBMISSION_UNKNOWN | Cannot safely promise | Reconciliation required |
| CANCELLED | Idempotent no-op | Already cancelled |
| EXPIRED | No longer needs sending | Already expired |

### Atomic cancellation in SQL

~~~sql
UPDATE mail_schedule
SET status = 'CANCELLED',
    stop_reason = 'USER_CANCELLED',
    generation = generation + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :scheduleId
  AND tenant_id = :tenantId
  AND status IN ('PENDING', 'RETRY_PENDING')
RETURNING id;
~~~

If the update returns 1 row, the request was cancelled while the job was still dispatchable. If it returns 0 rows, read the latest state **scoped to the tenant** to distinguish non-existent, already sent, currently processing, or already cancelled. Never return "cancelled successfully" solely because HTTP received DELETE.

### Race with worker claim

A worker and a cancellation API concurrently update the same record:

~~~text
Time ->

API cancel:  UPDATE status=PENDING -> CANCELLED
Worker:      UPDATE status=PENDING -> PROCESSING
~~~

Only one state transition can win if the database operation is atomic and status predicates are used properly. If cancellation wins, the worker cannot claim that record. If the worker claim wins, the API must report that it is processing rather than promising SMTP recall.

### Do not use `ScheduledFuture.cancel()` as the sole proof

With an in-memory `TaskScheduler`, `ScheduledFuture.cancel(false)` can cancel an unstarted task on a single JVM. In a distributed/durable scheduler, cancellation must update the **durable source of truth**; a cancelled future on one instance does not prove another instance does not still hold the job.

## 22. Rescheduling (Reschedule)

A user may request moving a send from 9:00 to 11:00. An API:

~~~http
PATCH /api/mail-schedules/{scheduleId}
Content-Type: application/json

{"scheduledAt":"2026-11-20T04:00:00Z"}
~~~

For an old schedule at 09:00 in Vietnam (02:00Z), the new value 04:00Z corresponds to 11:00. The change requires:

1. Proper tenant/owner authorization.
2. Checking that the job is not already `PROCESSING` or `SUBMITTED`.
3. Checking that the new time is not in the past or too far in the future.
4. Validating timezone/DST if the user edits in local time.
5. Verifying expiry is still after the new schedule.
6. Updating `scheduledAt` and `availableAt` consistently.
7. Incrementing `generation` or row version.
8. Auditing old schedule, new schedule, and actor.

### Optimistic SQL update

~~~sql
UPDATE mail_schedule
SET scheduled_at = :newScheduledAt,
    available_at = :newScheduledAt,
    status = 'PENDING',
    generation = generation + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = :scheduleId
  AND tenant_id = :tenantId
  AND generation = :expectedGeneration
  AND status = 'PENDING'
RETURNING id, generation, scheduled_at;
~~~

Here rescheduling is allowed only while PENDING; if rescheduling `RETRY_PENDING` is allowed, define whether attempt counts reset. **Do not reset retry schedules and erase error history by default**, as that can exceed attempt budgets or resend when outcomes are uncertain.

### Rescheduling must not accidentally create a new schedule

A PATCH request retried by a client after a timeout must not create multiple schedules. Keep a single record and use `If-Match`/generation to guard against stale updates; return a conflict if the user is editing an outdated version.

## 23. Cancelling After the User Has Seen "Sending"

Right after a worker claims a job, there is a brief window before the SMTP socket actually opens. A system can support **cancellation requested** and have the worker check that flag one last time. However, be clear about the boundaries:

- If the worker has not started the external send yet, it can cancel.
- Once the SMTP socket has started, you may not know whether the relay accepted the message.
- Closing the socket does not guarantee the relay has not already processed DATA.
- If SMTP already accepted it, cancelling in the database will not remove the email from the relay.

**Do not design a UI showing "Email cancelled and guaranteed not to arrive" once a send attempt is already in flight.** If "recall-like" behavior is needed, you must rely on provider-specific features under explicit conditions; SMTP has no universal recall API.

## 24. When a User Changes Their Timezone After Scheduling

A tricky scenario:

1. A user schedules "send at 09:00 on Nov 20 in `Asia/Ho_Chi_Minh`".
2. Later, they change their profile timezone to `America/Los_Angeles`.
3. Should the existing schedule move to 09:00 Los Angeles?

There is no single answer. It must be decided at the business layer:

**Fixed-Instant schedule:** `scheduledAt` does not change; the UI may display it in the new timezone. Suitable for a one-off send booked for a specific point in time.

**Local-civil-time-bound schedule:** a rule like "send at 09:00 in the recipient's current local time" may need recalculation when the timezone changes. Suitable for recurring reminders or long-running rules.

Persist `Instant`, `requestedZoneId`, `requestedLocalDateTime`, and the policy to avoid silent rescheduling. For a **one-time email**, many systems keep the confirmed `Instant`; for recurring local-time schedules, each occurrence should be re-evaluated.

## 25. Recipients Across Multiple Timezones

A campaign wanting to send at "08:00 in each recipient's local time" actually has **many different Instants**:

~~~text
Recipient A: Asia/Ho_Chi_Minh, 2026-11-20 08:00
Recipient B: Europe/London,     2026-11-20 08:00
Recipient C: America/New_York,  2026-11-20 08:00
~~~

If you compute a single `Instant` from the admin's timezone and apply it to everyone, emails will arrive at wildly different local hours.

### How to organize it

- Define where the recipient's verified timezone source comes from.
- Resolve local 08:00 for each recipient according to their IANA zone.
- Create one `scheduledAt` record per recipient or group cohorts by UTC timestamp.
- Pin down DST gap/overlap policies.
- Throttle batch/throughput since many recipients may become due at once.
- Before sending, check consent and suppression at the recipient level.

### Do not send early just to ease queue congestion

If many messages become due at 08:00, workers may process within quota and send some slightly late. **Do not proactively send at 07:45** just to ensure all messages arrive during the 08:00 hour if the contract forbids submitting ahead of time.

If the requirement is "all emails land in Inboxes around 08:00", SMTP cannot guarantee that; communicate realistic SLAs and align campaign/provider design accordingly.

## 26. Recurring Send Rules Are Not One-Shot Scheduled Sends

"Send exactly once at 09:00 on Nov 20" and "send at 09:00 every Monday" are two distinct data models:

- **One-shot schedule:** a single `Instant` milestone; once submitted, that schedule ends.
- **Recurring rule:** a rule generating multiple occurrences, typically involving timezone, holiday calendars, end dates, and DST policies.

Example:

~~~text
Recurring rule:
  tenantId      = t-01
  template      = weekly-report
  dayOfWeek     = MONDAY
  localTime     = 09:00
  zoneId        = Asia/Ho_Chi_Minh

Generated occurrences:
  report-2026-11-16 -> scheduledAt=2026-11-16T02:00:00Z
  report-2026-11-23 -> scheduledAt=2026-11-23T02:00:00Z
  report-2026-11-30 -> scheduledAt=2026-11-30T02:00:00Z
~~~

One architecture can generate **one-shot records** from the recurring rule and reuse the same dispatcher. Each occurrence gets its own idempotency key so scheduler restarts do not regenerate it.

### Do not use server cron as the user's timezone

If you use `@Scheduled(cron = "...", zone = "...")` in Spring, the chosen timezone applies to the **application's** cron execution. It does not automatically create 09:00 schedules per recipient zone. For global users, compute individual occurrences or per-zone cohorts.

### Skip, catch up, or regenerate missed occurrences after an outage?

Suppose the app is down from 08:50 to 11:00, missing a 09:00 recurring occurrence. Upon recovery, the system must have a policy:

- **Catch-up:** still send if within the grace period.
- **Skip missed:** skip and record `MISSED`.
- **Latest only:** send only the most recent period instead of piling up older ones.
- **Hold for review:** for sensitive emails.

Do not let `@Scheduled`'s incidental missed-execution behavior decide; encode business rules explicitly in configuration and state.

## 27. Should Email Content Be Frozen at Schedule Time or Rendered at Send Time?

Scheduling days in advance raises a question: **which payload gets sent on that day?**

### Render immediately at schedule creation

Pros:

- Content is "frozen" exactly as approved by the user.
- Prevents template/data changes from distorting the meaning.
- Easy to audit the approved draft.

Cons:

- Must store HTML/plain text and potentially sensitive metadata for a long time.
- Links/tokens may expire before the send date.
- Dynamic content such as "current balance" becomes stale.
- Rendered attachments may consume substantial storage.

### Render at send time

Pros:

- Data and templates can be updated closer to submission time.
- Fresh links/tokens can be generated per policy.
- Reduces how long rendered content is stored.

Cons:

- What the recipient reads may differ from what the sender previewed.
- The template may have been deleted, the model changed, or resources become inaccessible.
- If business data changes, the email may no longer reflect the original event.

### A hybrid approach

Store `templateKey`, `templateVersion`, `businessSnapshotId`, and immutable attachment object references. At send time:

1. Load the exact approved version.
2. Verify recipient and current eligibility.
3. Inject only well-defined dynamic fields.
4. Render and validate before submitting.
5. Store a hash/version of the sent content for auditing.

Do not blindly pull all latest values if the email represents a finalized invoice: a post-scheduling data change could make the email contradict the recorded transaction.

### Sensitive tokens and expiry

Do not generate an OTP or reset token a week early and schedule it for next week when the token only lives 5 minutes. Possible designs:

- Generate the token at send time if the workflow allows and proper transaction/authorization holds.
- Or restrict scheduling to a window where the token remains valid.
- Or cancel and require the user to initiate a new action when the schedule exceeds validity.

An email containing an expired token should become `EXPIRED`, rather than attempting delivery hoping the user understands.

## 28. Attachments in Scheduled Emails

Sending several days later often fails because attachments were deleted or file paths changed.

### Do not use temporary paths

~~~text
Job created today:
    attachmentPath = /tmp/upload-123.pdf

Scheduled next week:
    /tmp was cleaned
    -> dispatch fails
~~~

Store attachments in storage with sufficient retention, immutable object keys, and tenant-scoped access control:

~~~text
attachmentRef:
  objectId: documents/receipt-184/version-3
  contentSha256: ...
  sizeBytes: ...
  allowedMimeType: application/pdf
  expiresAt: after scheduled send + retry window
~~~

The above is conceptual metadata. When due, the worker verifies the object exists, is authorized, is within size limits, passed security scans if needed, and matches the hash/version. If the object is missing or unauthorized, **do not send the email missing a mandatory attachment and mark it successful**.

### Match retention to retry windows

If an email is scheduled 30 days ahead with a 3-day retry window, the attachment must not be purged after 7 days simply due to a temporary-upload TTL. Deletion policies must still respect privacy regulations; do not keep files forever just in case the scheduler fails.

## 29. Guaranteeing No Early Sends While Handling Lateness Transparently

An AT request may pass through multiple coordinators. At the **execution point**, the worker must still compare `clock.instant()` against `scheduledAt`, even if SQL already filtered `scheduled_at <= now()`.

### Why re-check?

- The worker may have received the job from a queue ahead of time.
- Clocks between the application and database may drift.
- The user just rescheduled while the worker held a stale snapshot.
- A queue delay/visibility mechanism may deliver early under unusual conditions.

For stronger semantics:

1. Configure system time synchronization (NTP or platform mechanism).
2. Maintain one canonical clock source for due decisions, such as the DB clock or a synchronized app `Clock`.
3. Use versions/fencing when workers transition states.
4. Refuse to send if the job is detected to still be in the future.
5. Track **early-send violations** as a critical error.

### Clock skew

If the DB reports 09:00:00 while a worker lags by 20 seconds, a job due by DB time may appear to be in the future to the worker. If the worker runs 20 seconds fast compared to the DB, the opposite risk occurs. Do not "fix" this by permitting sends 20 seconds early. Ensure time synchronization and consistent policies.

### Grace period when workers fall behind

Example reminder email:

~~~text
scheduledAt       = 09:00
maxAllowedLateness = 10 minutes

worker starts 09:04 -> allowed late send
worker starts 09:35 -> mark MISSED / EXPIRED
~~~

A long-term report may be allowed to send hours late; an OTP may expire after just a few minutes. `maxAllowedLateness` must be defined per notification category.

## 30. Priority Tiers and Queue Fairness

If hundreds of thousands of marketing emails become due together, "send now" OTP emails must not get blocked behind them. Possible designs:

- Priority tiers: security, transactional, marketing.
- Dedicated worker pools or queue partitions.
- Reserved throughput for OTP/security.
- Provider/account/tenant quotas.
- Cross-tenant fairness so one tenant cannot monopolize capacity.
- Backpressure when providers return 4xx/quota errors.

### Priority must not starve older jobs

Always running `ORDER BY priority DESC` with continuous high-priority arrivals can starve lower-priority jobs indefinitely. Use weighted fair queues, per-class quotas, or aging policies. However, aging must never permit **sending past expiry** or bypassing suppression.

### Example batch-selection query

~~~sql
SELECT id
FROM mail_schedule
WHERE status IN ('PENDING', 'RETRY_PENDING')
  AND available_at <= CURRENT_TIMESTAMP
  AND scheduled_at <= CURRENT_TIMESTAMP
  AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
ORDER BY priority DESC, available_at, created_at
LIMIT 100;
~~~

This query illustrates priority ordering, **not a multi-worker-safe claiming mechanism**. Actual dispatching needs locking/leases as covered earlier. When storing both `availableAt` and `scheduledAt`, indexes must match the actual query and data patterns.

### "Send now" has no privilege to bypass rules

High-priority emails must still:

- Be permitted for the recipient.
- Use a valid sender identity.
- Respect quotas and legal constraints.
- Have still-valid content.
- Never duplicate an already SUBMITTED notification.

Priority only governs serving order among **valid** requests, never a reason to skip checks.

## 31. Rate Limiting and Concurrency Before SMTP

A scheduler is not only responsible for "waking up on time"; it must also ensure the system does not overload the SMTP provider.

### Common limits

| Limit | Example usage |
| --- | --- |
| Max in-flight connections | Protects SMTP sockets and threads |
| Max messages/sec | Matches provider quota |
| Max messages/day | Matches account/contract limits |
| Per-domain throttling | Avoids flooding a single receiving domain |
| Per-tenant quota | Prevents one tenant from throttling others |
| Per-recipient frequency | Reduces spam/notification fatigue |
| Category reserved capacity | Prioritizes OTP/security during large campaigns |

When a limiter denies a job:

1. Do not call SMTP.
2. Do not increment physical SMTP attempt counts.
3. Set a new `availableAt` or move to an appropriate queue.
4. Preserve the original `scheduledAt`.
5. Measure `rate_limit_deferred` and lateness.

### Multiple instances need shared limiters

A `Semaphore(5)` inside each pod does not limit the cluster to 5 connections across 10 pods; the total can reach 50. For account/provider-level quotas, use a distributed limiter or quota partitioning proven not to exceed the total budget.

## 32. When Multiple SMTP Providers Exist

A system can select a backup provider when the primary route suffers an outage, but **a send schedule does not automatically authorize failing over every error**.

If `RCPT TO` returns a permanent error confirming the mailbox does not exist, sending via Provider B usually will not fix the address. If the template/MIME is invalid, switching providers will not fix the payload. If the recipient unsubscribed, rerouting to send anyway violates policy.

Failover should only be considered when:

- The failure is genuinely specific to that infrastructure/route.
- Provider B is approved for the tenant, category, sender domain, region, and data.
- The message is still valid and the recipient is still allowed to receive it.
- There is no prior accepted submission or unknown outcome awaiting reconciliation.
- Provider B still has budget and quota.

If Provider A already accepted the message and reported `DEFERRED` downstream, A may still be retrying. Do not submit again through B simply because the time passed `scheduledAt` or no delivered event has arrived.

## 33. SMTP Accepted Does Not Mean Delivered

When `JavaMailSender.send(...)` returns normally, you can record **successful submission per transport response**, never immediately label it "delivered to Inbox".

~~~text
09:00:00  scheduledAt reached
09:00:02  worker calls JavaMailSender.send()
09:00:03  relay final 250 accepted
09:00:04  application marks SUBMITTED
09:03:18  provider reports DEFERRED
09:07:40  provider reports DELIVERED
~~~

User-facing statuses can distinguish:

| Status | Displayed meaning |
| --- | --- |
| PENDING (future) | Scheduled |
| PENDING (due) | Queued for sending |
| PROCESSING | Sending |
| SUBMITTED | Submitted to delivery relay |
| DELIVERED (provider event) | Provider reported delivered |
| BOUNCED | Undeliverable according to provider |
| RETRY_PENDING | Temporary send error; will retry if within expiry |
| CANCELLED | Schedule cancelled before sending |
| EXPIRED/MISSED | Skipped due to expiration |
| SUBMISSION_UNKNOWN | Submission outcome needs verification |

In many systems, Delivered is merely a provider-defined term and does not prove the recipient actually read the email. Do not equate open tracking (affected by proxies/caches/image blocking) with a reliable read receipt.

## 34. Using Clock in Tests Instead of Waiting in Real Time

Testing mail schedules should not call `Thread.sleep(60_000)` to wait a minute. Tests need controllable time:

~~~java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfiguration {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

In tests, you can replace it with `Clock.fixed(...)` or a mutable fake clock. In a Spring test context, avoid creating two `Clock` beans that cause ambiguity; use `@Primary`, profiles, or controlled test configurations.

### Unit testing NOW and AT sends

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Map;
import org.junit.jupiter.api.Test;

class ScheduleValidatorTest {
    private static final Instant NOW =
            Instant.parse("2026-11-12T10:00:00Z");

    private final ScheduleValidator validator =
            new ScheduleValidator(
                    Clock.fixed(NOW, ZoneOffset.UTC),
                    Duration.ofDays(90));

    @Test
    void nowModeStartsAsSoonAsEligible() {
        CreateMailSchedule command = new CreateMailSchedule(
                "t1", "recipient-42", "receipt", Map.of(),
                ScheduleMode.NOW, null, null, "receipt-184");

        assertEquals(NOW,
                validator.computeScheduledAt(command));
    }

    @Test
    void atModePreservesFutureInstant() {
        Instant requested =
                Instant.parse("2026-11-20T02:00:00Z");
        CreateMailSchedule command = new CreateMailSchedule(
                "t1", "recipient-42", "reminder", Map.of(),
                ScheduleMode.AT, requested, null, "reminder-184");

        assertEquals(requested,
                validator.computeScheduledAt(command));
    }

    @Test
    void atModeRejectsPastTime() {
        CreateMailSchedule command = new CreateMailSchedule(
                "t1", "recipient-42", "reminder", Map.of(),
                ScheduleMode.AT, NOW.minusSeconds(1),
                null, "reminder-old");

        assertThrows(IllegalArgumentException.class,
                () -> validator.computeScheduledAt(command));
    }

    @Test
    void atModeRejectsTimeBeyondBookingWindow() {
        CreateMailSchedule command = new CreateMailSchedule(
                "t1", "recipient-42", "reminder", Map.of(),
                ScheduleMode.AT, NOW.plus(Duration.ofDays(91)),
                null, "reminder-too-far");

        assertThrows(IllegalArgumentException.class,
                () -> validator.computeScheduledAt(command));
    }
}
~~~

This is a JUnit 5 example for the `ScheduleValidator` component shown earlier, without SMTP or a database. It verifies the `scheduledAt` calculation logic, **not yet proving that the real worker will never send early**.

### Testing DST gap and overlap

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.*;
import org.junit.jupiter.api.Test;

class ScheduleTimeResolverTest {

    private static final ZoneId NEW_YORK =
            ZoneId.of("America/New_York");

    @Test
    void rejectsNonexistentLocalTime() {
        LocalDateTime gap =
                LocalDateTime.of(2026, 3, 8, 2, 30);

        assertThrows(IllegalArgumentException.class,
                () -> ScheduleTimeResolver.resolve(
                        gap, NEW_YORK, null));
    }

    @Test
    void requiresDisambiguationForOverlap() {
        LocalDateTime overlap =
                LocalDateTime.of(2026, 11, 1, 1, 30);

        assertThrows(IllegalArgumentException.class,
                () -> ScheduleTimeResolver.resolve(
                        overlap, NEW_YORK, null));
    }

    @Test
    void selectedOffsetsProduceDifferentInstants() {
        LocalDateTime overlap =
                LocalDateTime.of(2026, 11, 1, 1, 30);

        Instant earlier = ScheduleTimeResolver.resolve(
                overlap, NEW_YORK, ZoneOffset.ofHours(-4));
        Instant later = ScheduleTimeResolver.resolve(
                overlap, NEW_YORK, ZoneOffset.ofHours(-5));

        assertEquals(Duration.ofHours(1),
                Duration.between(earlier, later));
    }
}
~~~

The test checks Java's timezone rules on a specific date; IANA rules can be updated in the future. If an application schedules years in advance, you need a strategy to manage timezone database updates and communicate with users when local rules change.

## 35. Integration Test: No Early Dispatch

To trust the mechanism end-to-end, insert a record in a test database, run the worker, and monitor calls to a fake SMTP server:

~~~text
Given:
  application Clock = 2026-11-12T10:00:00Z
  job.scheduledAt   = 2026-11-12T10:05:00Z
  job.status        = PENDING

When:
  dispatcher.dispatchDueBatch()

Then:
  no SMTP connection attempted
  job remains PENDING
  attempts remains 0

When:
  controlled Clock advances to 10:05:00Z
  dispatcher.dispatchDueBatch()

Then:
  exactly one job is claimed
  exactly one SMTP submission attempt starts
  result is persisted according to server response
~~~

In transport tests, the fake SMTP may return a final 250; that proves **successful submission**, not Inbox delivery.

### Do not inspect only the final state

If you only assert that a job eventually becomes SUBMITTED, buggy code could still send early and fix the status later. Tests must record **connection/attempt timestamps** or spy on the transport and verify no calls occurred before due time.

### Testing clock skew

A deeper suite can simulate an app clock differing from the DB clock and verify the system follows one canonical time source without dispatching before `scheduledAt`. This tests infrastructure coordination, not just unit-testing `Clock`.

## 36. Integration Test: Application Restarts Before Send Time

This is the biggest reason not to rely on an in-memory `TaskScheduler` as the sole schedule store:

~~~text
09:00  User schedules mail for 10:00
09:01  DB commits PENDING record
09:30  Application stops
09:50  Application starts
10:00  Worker claims due record
10:00+ SMTP relay accepted
~~~

The test should:

1. Create the schedule in a real database or Testcontainers.
2. Stop the instance/scheduler.
3. Restart against the same database.
4. Verify the record was not lost and `scheduledAt` remained intact.
5. Run the poller once due.
6. Observe the fake SMTP receiving exactly one logical attempt.
7. Verify status after submission.

Do not rely on an in-memory queue or a `ScheduledFuture` registered prior to restart. If using a broker delay queue, the test must confirm the broker provides persistence and recovery under the active configuration.

## 37. Integration Test: Two Workers Reaching Due Time Together

Two replicas can run their pollers nearly simultaneously:

~~~text
Worker A -> find due notification N
Worker B -> find due notification N
~~~

If code merely SELECTs and then SENDs, both can send. A proper test must:

- Use a real database with transaction isolation/row locking equivalent to production.
- Run two workers concurrently, each with a distinct ID.
- Use a barrier/latch so both reach the claim step simultaneously.
- Verify that **one logical claim wins**.
- Verify the fake SMTP receives one submit attempt if the worker does not crash.
- Persist results along with lease owner/generation.

A Mockito repository cannot prove `FOR UPDATE SKIP LOCKED` works; you must test against a database engine close enough to production.

### Worker loses lease while still running

An advanced test can slow Worker A right before sending so its lease expires and Worker B starts recovery. The flow must be designed so both do not send. Heartbeat/fencing/unknown-state mechanisms must be proven with integration tests, not assumed from a short transaction lock.

## 38. Integration Test: Cancellation and Rescheduling

### Cancelling before due time

~~~text
User creates AT=10:00
User cancels at 09:50
Worker runs at 10:00
Expected: no SMTP submission, state=CANCELLED
~~~

### Rescheduling to a later time

~~~text
User creates AT=10:00
User updates AT=11:00 at 09:55
Worker runs at 10:00
Expected: no SMTP submission
Worker runs at 11:00
Expected: one SMTP submission
~~~

### Race between cancel and claim

Have the DELETE API and worker UPDATE claim race on the same record in a concurrency test. One operation wins:

- If DELETE wins: status is CANCELLED, SMTP is never called.
- If claim wins: DELETE must not report "definitely cancelled"; state is PROCESSING and subsequent outcomes follow the contract.

When claim wins, the test should not blindly promise the message was definitely delivered; simply assert honest cancellation semantics and no unexplainable states.

### Rescheduling while retrying

If a user is allowed to edit a `RETRY_PENDING` email, clarify whether it means "changing the next retry time" or "changing the original schedule meaning" and whether attempts reset. An ambiguous API can make users think they "rescheduled" while the system keeps retrying from old errors.

## 39. SMTP Integration Tests: Temporary, Permanent, and Unknown

A test SMTP server can return:

| Scenario | Response point | Expectation |
| --- | --- | --- |
| 250 after DATA | Accepted | SUBMITTED; do not retry |
| 421 at session start | Server temporarily unavailable | Retry if safe and not expired |
| 451 at RCPT TO | Temporary refusal | Backoff, do not mark DELIVERED |
| 550 5.1.1 at RCPT TO | Recipient invalid | Permanent/suppression per policy |
| 535 at AUTH | Account credentials invalid | Hold provider lane, prevent retry storm |
| Timeout before MAIL FROM | Body not yet submitted | Retry policy with backoff |
| 554 after DATA | Explicit rejection | Investigate content/policy, do not retry blindly |
| Connection lost after DATA before final reply | Outcome unknown | Reconcile, do not automatically create a new send |

In integration tests using a real `JavaMailSenderImpl`, you can run a scripted SMTP server listening on loopback to control EHLO/MAIL FROM/RCPT TO/DATA. Scheduling tests must coordinate **database state** and **transport attempts**: a scheduled record must still react properly when SMTP returns these codes.

### Why does a timeout after DATA matter?

Suppose:

~~~text
09:00:00 worker sends message body
09:00:01 relay receives last DATA marker
09:00:01 connection drops before final reply
09:00:02 JavaMailSender throws
~~~

It is unknown whether the relay accepted the message. If the worker retries immediately, the same email may arrive twice. The system should record the attempt as needing reconciliation; plain `MailException` classes often lack full phase semantics, so SMTP instrumentation or provider status lookup may be required.

## 40. Comprehensive Test Matrix

| ID | Scenario | Primary expectation |
| --- | --- | --- |
| S01 | Valid NOW request | Persist PENDING with current scheduledAt |
| S02 | AT with UTC Instant | Store exact instant |
| S03 | AT in Asia/Ho_Chi_Minh | Convert local time and zone accurately |
| S04 | AT missing zone with local time | Validation rejection |
| S05 | DST gap | Reject or apply approved rule, never shift silently |
| S06 | DST overlap without offset | Require disambiguation |
| S07 | AT in the past | Reject or apply explicit grace policy |
| S08 | AT beyond max advance | Reject |
| S09 | Duplicate idempotency key with same payload | Return existing record, no new send |
| S10 | Same key with different payload | Conflict |
| S11 | Worker runs before scheduledAt | Do not call SMTP |
| S12 | Worker runs at scheduledAt | Eligible to claim and submit |
| S13 | Worker runs late within grace | Send late, measure lateness |
| S14 | Worker runs late past expiry | EXPIRED/MISSED, do not send |
| S15 | App restarts before AT | Schedule preserved |
| S16 | Two workers claim same job | Single logical owner |
| S17 | Lease expires while worker still sending | No automatic duplicate |
| S18 | SMTP accepted but DB update fails | Reconcile/unknown, no blind resend |
| S19 | User cancels before claim | CANCELLED, do not send |
| S20 | Cancel races with claim | Atomic transition, honest response |
| S21 | Reschedule to future | Old time does not send, new time sends |
| S22 | PATCH with stale generation | Conflict, no overwrite |
| S23 | Recipient unsubscribes before send time | SUPPRESSED, do not call SMTP |
| S24 | OTP expired | EXPIRED, do not send |
| S25 | Attachment object deleted | HOLD/FAIL, do not send without mandatory file |
| S26 | Template version missing | Do not substitute alternative content automatically |
| S27 | SMTP 451 | RETRY_PENDING with backoff |
| S28 | SMTP 550 permanent | Do not retry |
| S29 | Widespread SMTP AUTH error | Account lane held, no retry storm |
| S30 | Lost final reply after DATA | SUBMISSION_UNKNOWN |
| S31 | Provider A reports deferred after accepted | Do not create a new submission |
| S32 | Rate limit permit unavailable | Defer, do not increment physical attempts |
| S33 | Many marketing emails due together | Must not starve OTP lane |
| S34 | Tenant unauthorized to send | Reject before enqueue/send |
| S35 | Crash mid-business-transaction | Do not commit outbox across wrong boundary |
| S36 | Recurring cron generator runs repeatedly | Do not create duplicate occurrences |
| S37 | Profile timezone changes | Behave according to defined policy |
| S38 | Already SUBMITTED notification replayed | Do not resend |
| S39 | Delayed provider webhook | Must not regress status or trigger resend |
| S40 | Provider quota exhausted at AT | Defer per policy, measure lateness |

Each test should only claim what the simulated source supports. A fake SMTP returning a final 250 proves submission to the fake relay, **not that real mail reached an Inbox**.

## 41. Monitoring: Immediate vs. Scheduled Send Latency

"Send now" and "send at requested time" have different SLOs:

- For NOW, measure **queue wait time** and **time to submission** from when the request commits.
- For AT, measure **lateness** when the worker starts submitting and when SMTP accepts relative to `scheduledAt`.
- Both must measure error rate, retry/unknown outcomes, backlog, and provider latency.

### Formulas that should be clearly defined

\[
\text{queueWait} =
\text{dispatchStartedAt} - \max(\text{createdAt},\text{scheduledAt})
\]

\[
\text{submissionLateness} =
\text{submittedAt} - \text{scheduledAt}
\]

\[
\text{timeToSubmitNow} =
\text{submittedAt} - \text{createdAt}
\]

The formulas above are notification-level examples; for AT, `submissionLateness` is positive when sent late and 0 when right on time. If `submittedAt` is missing because the message failed, **do not set lateness to 0**; track outcomes and backlog age separately.

### Suggested metrics

| Metric | Meaning |
| --- | --- |
| `mail_schedule_requests_total` | NOW/AT requests accepted |
| `mail_schedule_created_total` | Schedules persisted |
| `mail_schedule_validation_failures_total` | Invalid input/timezone/permissions |
| `mail_schedule_due` | Due jobs not yet processed |
| `mail_schedule_future` | Jobs scheduled in the future |
| `mail_schedule_pending_oldest_age_seconds` | Age of the oldest overdue job |
| `mail_dispatch_delay_seconds` | Delay from due time to dispatch start |
| `mail_submission_lateness_seconds` | Deviation from requestedAt/scheduledAt to accepted submission |
| `mail_submission_attempts_total` | Physical SMTP/API attempts |
| `mail_submission_failures_total` | Failures by provider/category/phase |
| `mail_schedule_retries_total` | Retries scheduled |
| `mail_schedule_cancelled_total` | Schedules cancelled |
| `mail_schedule_rescheduled_total` | Reschedule operations |
| `mail_schedule_expired_total` | Schedules no longer eligible to send |
| `mail_submission_unknown_total` | Attempts needing reconciliation |
| `mail_schedule_claim_conflicts_total` | Claim/fencing contention |
| `mail_rate_limit_deferred_total` | Deferred due to quota before SMTP |
| `mail_worker_inflight` | In-flight SMTP submissions |

The metric names above are implemented by the application via Micrometer/Actuator or another observability stack; **Spring Mail does not provide all of these out of the box**.

### Labels to include and labels to avoid

Bounded labels may include `mode=NOW|AT`, `category`, `providerKey`, `region`, and `failureKind`. Never put full recipient emails, notification UUIDs, subjects, idempotency keys, or tokens into metric labels: it explodes cardinality and can leak sensitive data.

### Critical alerts

| Signal | Possible issue | Action |
| --- | --- | --- |
| AT submitted early | Clock skew, buggy filter query, stale schedule | Isolate worker, inspect clock/claims |
| NOW time-to-submit rising | Queue backlog, slow provider, overly tight limiter | Check throughput and backlog |
| AT lateness rising | Poller not running, too many jobs due simultaneously | Check scheduler and capacity |
| Oldest due age exceeds SLO | Stuck jobs or stalled retries | Inspect states, leases, errors |
| PROCESSING lease expired rising | Worker crashes/socket timeouts | Do not replay blindly; reconcile |
| CANCELLED still sees SMTP attempt | Race or missing worker recheck | Halt affected route and investigate |
| SUBMITTED sent again | Buggy idempotency/lease recovery | Isolate resends, check attempt ledger |
| High EXPIRED count | Scheduling exceeds capacity or TTL too short | Adjust SLA/quota/UX |
| One template version failing en masse | Missing resources in render-at-send | Hold category, fix template safely |

### Illustrative SLOs

A product might target:

- 99% of NOW transactional jobs start submission within an agreed maximum delay.
- 99% of AT jobs do not start before `scheduledAt`.
- A high percentage of AT jobs are submitted within the grace period after `scheduledAt`, excluding provider outages or cancelled requests.
- Zero CANCELLED jobs automatically trigger new sends.

Specific thresholds must reflect load, cost, provider quotas, and business goals. **Do not pick percentages just because they look good on a dashboard**, and do not count CANCELLED/EXPIRED jobs as SMTP failures if they were never submitted.

## 42. Logs and Audit Trail for Send Schedules

A scheduled email evolves across multiple actions:

~~~text
2026-11-12T10:00:00Z CREATE AT=2026-11-20T02:00:00Z
2026-11-18T09:00:00Z RESCHEDULE to 2026-11-20T04:00:00Z
2026-11-20T04:00:03Z CLAIM by worker-2
2026-11-20T04:00:05Z SUBMISSION_ACCEPTED by smtp-primary
~~~

An audit record should contain:

- `scheduleId`, tenant, actor ID/role.
- Event name: CREATED, RESCHEDULED, CANCELLED, CLAIMED, RETRIED, SUBMITTED, EXPIRED.
- Old and new states and timestamps.
- `generation`/version changes.
- Provider key, attempt ID, and normalized error if applicable.
- Event timestamp in UTC.
- Business correlation ID.

### Illustrative structured log

~~~json
{
  "event": "mail_schedule_rescheduled",
  "scheduleId": "a1a6d179-3cb2-47e7-bb2f-d34eebeb5ac1",
  "tenantKey": "tenant-01",
  "actorType": "USER",
  "fromScheduledAt": "2026-11-20T02:00:00Z",
  "toScheduledAt": "2026-11-20T04:00:00Z",
  "newGeneration": 3
}
~~~

Do not log raw email bodies, OTPs, password reset tokens, SMTP passwords, full recipient addresses, or unnecessary attachment data. If detailed forensic/audit logs are needed, use access-controlled storage with retention policies.

## 43. Securing the Mail Scheduling API

If any user can invoke the schedule endpoint with arbitrary recipients and templates, the application risks becoming an **open relay at the business layer**, even if the SMTP relay still requires authentication.

### Security checkpoints

1. Authenticate caller, tenant, and operation permissions.
2. Allow sending only to recipients within permitted scopes.
3. Allow only sender identities/templates the caller is authorized to use.
4. Validate content and attachments against schemas and size limits.
5. Check consent and unsubscribes per email category.
6. Cap future schedule counts, advance-booking windows, and frequency.
7. Rate-limit `CREATE`, `PATCH`, and `CANCEL` APIs.
8. Prevent one tenant from modifying another tenant's schedule, even if a UUID is guessed.
9. Audit schedule creation, edits, and cancellations.
10. Re-check suppression/expiry right before SMTP.

### Authorization is not only at the controller

Background workers have no HTTP user context. Therefore, the record must carry enough tenant/business scope for the service to **verify eligibility** before dispatch, rather than assuming database rows remain authorized forever. Every read/cancel/update API must filter by tenant/owner, never just `WHERE id = ...`.

### Recipient data retention

An email scheduled 6 months out can store email addresses, template data, and attachments for months. Proper retention/encryption/consent is needed; if a user requests data erasure or permissions change, pending schedules may need to be cancelled or updated per policy.

## 44. Runbook: Schedule Reached Due Time Without Sending

When on-call receives a report "I scheduled 9:00 AM, it is 9:30 AM and it still has not sent", follow these steps:

1. Identify the `scheduleId` or business correlation ID.
2. Inspect the UTC `scheduledAt` and confirmed local time/zone from creation.
3. Check status: PENDING, RETRY_PENDING, PROCESSING, SUBMITTED, EXPIRED, CANCELLED, UNKNOWN.
4. If PENDING: check `availableAt`, query index, polling scheduler, and permissions.
5. If RETRY_PENDING: inspect SMTP errors and `nextAttemptAt`/retry budget.
6. If PROCESSING: inspect lease owner, lease age, worker heartbeat, and socket timeouts.
7. If SUBMITTED: check provider events/queues; do not resend solely because it is not yet delivered.
8. If EXPIRED: check expiry/late-send policy; do not reset automatically.
9. If CANCELLED: check actor and audit trail; do not restart.
10. If SUBMISSION_UNKNOWN: reconcile with the relay before replaying.
11. Measure backlog for the same category/tenant/provider.
12. Fix the root cause and recover using a rate limiter—do not drain the entire backlog at once.

### Do not fix by setting every availableAt = NOW

Such a mass update can:

- Send emails that are not yet due.
- Send expired messages.
- Bypass consent/suppression.
- Trigger traffic spikes against the provider.
- Create duplicates for jobs already accepted by the relay.

If you must replay after an incident, build a filtered list based on **known states and reasons**, with dry-run previews, auditing, and proper approval.

## 45. Runbook: Detecting Early-Sent Emails

This is a critical bug because it can violate explicit user choices.

1. Inspect requested local time, zone, and persisted UTC instant.
2. Cross-check CREATE/RESCHEDULE/CLAIM/SUBMITTED events.
3. Audit `LocalDateTime`-to-`Instant` conversion code, especially any use of `systemDefault()`.
4. Check clock skew between the DB and workers.
5. Check stale caches/job snapshots after PATCH.
6. Verify whether an in-memory TaskScheduler still holds an old future after rescheduling.
7. Check queries missing `scheduled_at <= now`.
8. Check whether any direct-send path bypassed the outbox.
9. Isolate the faulty execution path if still active; do not automatically send a "correction email" to compensate.
10. Add no-early-send and cancel/reschedule race tests.

Even when code handles UTC properly, this bug can still come from **a branch bypassing the worker** and calling `mailSender.send()` directly without checking the schedule.

## 46. Runbook: Duplicate Sends After Restart

A typical incident:

~~~text
09:00:00 Worker A sends to SMTP
09:00:01 Relay replies 250
09:00:02 Worker A crashes before DB update
09:02:00 Lease expires
09:02:01 Worker B retries same record
09:02:02 Recipient may receive a duplicate
~~~

Response steps:

1. Pause automatic re-dispatch for the affected cohort.
2. Preserve attempt/provider IDs and timestamps.
3. Reconcile against provider logs/events or APIs when available.
4. Do not treat a DB row still in PROCESSING as proof that it was not sent.
5. Update the record to the appropriate state based on evidence.
6. If a resend is unavoidable while outcomes remain unclear, make an audited business decision.
7. Review worker leases, heartbeats, fencing, and transaction boundaries.
8. Check whether nested retries in adapters/brokers inflated attempts.
9. Add crash-window integration tests.

**Do not promise exactly-once SMTP** solely from database locking. You can achieve idempotent enqueue/claim, but external submission still has an uncertain-outcome window.

## 47. Runbook: Large Backlog After Downtime

Suppose the application was down for 2 hours and tens of thousands of scheduled sends became due. On restart:

- Do not send everything in one second just because `scheduledAt <= now`.
- Prioritize essential categories and apply fairness and quotas.
- Filter out `EXPIRED` messages per deadline before calling SMTP.
- Do not send marketing emails to users who unsubscribed during downtime.
- Do not render all attachments simultaneously and exhaust memory/disk.
- Keep the original `scheduledAt` to measure lateness.
- Use bounded batches/claims and a distributed rate limiter.
- Monitor `pendingOldestAge`, SMTP responses, and completion throughput.

### Clear catch-up policy

| Email type | When 2 hours late |
| --- | --- |
| Short-lived OTP/reset token | Usually EXPIRED, do not send stale codes |
| Pre-appointment reminder | May skip if the appointment time has already passed |
| Transaction receipt | Can send late if still valid |
| Periodic report | Follow skip/catch-up/latest policy |
| Marketing campaign | Check campaign window and consent |

There is no universal answer. Business rules must be defined before implementing the scheduling system.

## 48. Common Mistakes When Scheduling Emails

### 48.1. Using `Thread.sleep()` to wait for send time

Ties up threads, does not survive restarts, and is hard to cancel. Store schedules in a database and use a poller/queue.

### 48.2. Creating a `ScheduledFuture` per email without DB persistence

Process restarts lose schedules; multi-instance coordination is hard. TaskScheduler can act as a trigger, not the sole source of truth for important emails.

### 48.3. Using cron per user

Recurring cron expressions do not cleanly model arbitrary one-off sends per `Instant`. Use one-shot records and a dispatcher.

### 48.4. Storing `LocalDateTime` without a timezone

Users across regions or servers changing timezones will misinterpret timestamps. Store `Instant` and zone metadata.

### 48.5. Ignoring DST gaps/overlaps

Local times may not exist or may repeat. Define a policy/offset instead of silently picking a timestamp.

### 48.6. Accepting past schedules and sending immediately

Can cause unintended sends. Return a validation error or enforce an explicit grace policy.

### 48.7. Calling SMTP directly inside an order transaction

Network timeouts prolong transactions; rollbacks cannot undo accepted SMTP sends. Use a transactional outbox.

### 48.8. Two replicas SELECTing and both SENDing

Without atomic claiming, duplicates occur. Use transactions/leases/fencing.

### 48.9. Automatically resending as soon as a lease expires

The worker may have submitted successfully before updating the DB. Handle unknown outcomes instead of blindly replaying.

### 48.10. Cancelling one ScheduledFuture and reporting system-wide cancellation

Insufficient for distributed/durable schedulers. Cancellation must update the source-of-truth state and account for races.

### 48.11. Rescheduling while leaving the old task running

With an in-memory scheduler, cancel the old future; with an outbox, claims must check the new version/scheduledAt. A single schedule source minimizes bugs.

### 48.12. Not revalidating consent at send time

Recipients can unsubscribe after scheduling. Do not let stale consent decisions bypass checks.

### 48.13. Treating `send()` success as DELIVERED

It only reflects SMTP submission; downstream status requires provider events.

### 48.14. Retrying every `MailException` identically

SMTP AUTH errors, permanent RCPT 550, temporary 451, and unknown-after-DATA need distinct handling.

### 48.15. Sending expired OTPs due to backlog

Causes poor UX and authentication confusion. Enforce expiry and retry deadlines.

### 48.16. Checking attachment size only at schedule creation

Files may change or exceed retention before send day. Use immutable storage/versions and validate at dispatch.

### 48.17. Missing idempotency keys for NOW requests

HTTP client timeout retries can create multiple schedules and duplicate emails.

### 48.18. Limiting concurrency only per pod

Multiple pods combined can exceed provider quotas. Use appropriately scoped limiters.

### 48.19. Sending earlier than scheduledAt when queues slow down

Violates user-selected constraints. Accept lateness, scale capacity, or negotiate a different SLA.

### 48.20. Not measuring lateness or backlog

Counting only `SUBMITTED` emails hides whether users receive mail on time. Measure queue delay, expiry, retries, and outcomes.

## 49. Implementation Checklist for Immediate and Scheduled Sending

### Time and API

- [ ] API contract distinguishes NOW and AT.
- [ ] AT accepts only a resolved `Instant` or local date-time with an explicit `zoneId`.
- [ ] Never uses server default timezone to guess user time.
- [ ] Has a policy for DST gaps/overlaps.
- [ ] Validates past schedules, max advance window, and max lateness.
- [ ] Uses an injectable `Clock` for time-calculation logic.
- [ ] Response only confirms the request was persisted, never assumes DELIVERED.
- [ ] Provides authorized APIs to inspect status, cancel, and reschedule.
- [ ] Reschedule/cancel guards against races via status and generation/version.

### Persistence and dispatcher

- [ ] Send requests are persisted durably, not just in JVM memory.
- [ ] NOW and AT share a pipeline or consistent policy.
- [ ] `scheduledAt` preserves business intent; `availableAt` tracks retry timing.
- [ ] Outbox commits in the same business transaction when needed.
- [ ] Unique idempotency key scoped by tenant/business operation.
- [ ] Indexes cover due jobs and queries prevent early sending.
- [ ] Atomic claim/lease across multiple workers.
- [ ] Fencing/optimistic updates for worker outcomes.
- [ ] No open DB transactions held during SMTP send.
- [ ] Design accounts for worker crash after send before DB update.
- [ ] Reconciliation mechanism for `SUBMISSION_UNKNOWN`.
- [ ] Re-checks status/time immediately before sending.

### Content and sending policy

- [ ] Recipient, consent, suppression, and authorization checked at dispatch time.
- [ ] Tokens/OTPs have expiry aligned with schedules.
- [ ] Template and payload versions are managed.
- [ ] Attachments exist, match versions, and retain until send time.
- [ ] Content is not altered unintentionally when templates/data change.
- [ ] Cancelled or expired jobs never trigger SMTP attempts.
- [ ] System does not resend already-SUBMITTED mail due to missing delivered events.
- [ ] Classifies SMTP temporary/permanent/AUTH/unknown errors.

### Capacity and operations

- [ ] Scheduler/poller resumes after restarts.
- [ ] Batch size and worker concurrency are bounded.
- [ ] Rate limiters apply at the proper provider/account/cluster scope.
- [ ] Backoff, jitter, and retry budgets are configured.
- [ ] Priority and fairness across categories/tenants.
- [ ] Grace/catch-up/skip policies for missed schedules.
- [ ] Metrics for queue wait, submit delay, lateness, and overdue counts.
- [ ] Alerts for early sends, lost schedules, overdue backlogs, and suspected duplicates.
- [ ] Auditing for CREATE/RESCHEDULE/CANCEL/SUBMIT.
- [ ] Tests using fake `Clock`, DB claim tests, and fake SMTP.
- [ ] Runbooks to drain backlogs without sending expired jobs or creating duplicates.

The checklist above is an implementation guide, not proof that a system works correctly. Key invariants such as **no early sending**, **not sending cancelled jobs**, **no duplicates when two workers claim the same record**, and **no blind retries after unknown SMTP outcomes** must be tested in appropriate environments.

## 50. Building Incrementally From Simple Version to Production

A team can roll out incrementally instead of building a full distributed scheduler on day one.

### Phase 1 — Clear request persistence

1. Define NOW/AT and timezone validation.
2. Create `mail_schedule` with `scheduledAt`, `status`, and idempotency key.
3. Use an injectable `Clock`.
4. Add APIs to create/view status/cancel before dispatch.
5. Define expiry policies and authorized senders.

At this stage, you do not need to replace `JavaMailSender`; it remains the transport adapter. The main change is **how the application creates and stores requests**.

### Phase 2 — A durable worker

1. Add a poller with `@Scheduled`.
2. Select due jobs by `scheduledAt`.
3. Claim via transaction and persist state.
4. Dispatch outside the transaction.
5. Persist accepted/failure/unknown outcomes.
6. Retry via `availableAt` and cap attempt counts.
7. Test restarts, timeouts, and no-early-send.

Even in single-worker environments, claim/lease patterns remain valuable to prepare for scaling and crash recovery.

### Phase 3 — Multiple replicas and high throughput

1. Atomic claiming and fencing.
2. Distributed rate limiting or quota partitioning.
3. Priority/fairness across email categories.
4. Attempt ledger/reconciliation.
5. Queue lateness and SLA measurement.
6. Runbooks for backlogs/circuit breakers/provider outages.
7. Test cancellation/restart races, clock skew, and worker lease expiry.

### Phase 4 — Advanced scheduling rules

If supporting recurring sends, per-recipient timezones, holidays, or source-event-driven rescheduling:

- Persist recurring rules and generate durable occurrences.
- Assign an idempotency key to each occurrence.
- Define a DST policy.
- Define rules to skip overdue occurrences.
- Version rules and audit user edits.

You do not need Cron/Quartz for every problem: choose based on complexity and precision requirements, not because "a scheduling library sounds powerful".

## 51. End-to-End Timeline Example: Send Immediately After Payment

Suppose a service receives payment event `payment-184` at 09:00:00.

~~~text
09:00:00.000  payment transaction begins
09:00:00.030  payment marked PAID
09:00:00.035  mail_schedule inserted:
                mode=NOW
                scheduledAt=09:00:00.035
                status=PENDING
                idempotencyKey=payment-receipt-184
09:00:00.040  COMMIT
09:00:00.100  API returns success
09:00:00.950  worker polls due jobs
09:00:00.965  one worker claims record
09:00:01.010  SMTP submit starts
09:00:01.300  relay replies 250
09:00:01.340  status=SUBMITTED
~~~

Key points:

- Never send before the transaction commits.
- Client retries with the same payment ID do not create a second schedule.
- During an SMTP outage, the payment transaction still persists and the mail outbox retains the request.
- Payment API success is never interpreted as Inbox delivery.
- If the relay accepted but the DB update fails, reconciliation/unknown state is required.

### User experience

The UI can display:

~~~text
Payment successful.
The system is sending a receipt to your verified email.
~~~

Once the corresponding provider outcome arrives, the UI/support portal can update the status. Never say "Email delivered" merely because the payment transaction committed.

## 52. End-to-End Timeline Example: Sending an Appointment Reminder

A user wants to send an email at 09:00 on November 20, 2026 in Vietnam:

~~~text
Request created: 2026-11-12
Local request:   2026-11-20 09:00
Zone:            Asia/Ho_Chi_Minh
scheduledAt:     2026-11-20T02:00:00Z
mode:            AT
status:          PENDING
~~~

### Normal case

~~~text
20/11 08:59 local -> polling sees scheduledAt in future, no send
20/11 09:00 local -> record becomes due, worker claims
20/11 09:00+      -> SMTP submits, status SUBMITTED
~~~

### User reschedules to 11:00

~~~text
18/11 16:00 local -> PATCH new scheduledAt=2026-11-20T04:00:00Z
                     version increments
20/11 09:00 local -> no SMTP attempt
20/11 11:00 local -> dispatch if still eligible
~~~

### User cancels

~~~text
19/11 -> DELETE schedule while PENDING
20/11 -> worker does not claim CANCELLED record
~~~

### Application suffers downtime until 11:30

This case depends on the **grace period**:

- If the reminder is only useful before a 10:00 appointment, the record should become EXPIRED/MISSED.
- If it is a notification without a strict deadline, it can be sent late with lateness recorded.
- Never send "at 11:30" and hide the original 09:00 schedule.

All these scenarios share the same `mail_schedule` and worker; the differences lie in **state and business rules**, not building a separate SMTP sender.

## 53. Self-Check Questions

**1. Does `JavaMailSender.send()` natively support sending tomorrow?**

No. It submits the email when invoked. Invocation timing must be controlled by the application's scheduler/queue/outbox.

**2. Must immediate sending call SMTP inside the HTTP request?**

No. You can save to an outbox with `scheduledAt = now`, return an accepted status, and have a worker send shortly per SLA.

**3. Does using `@Scheduled` make individual user schedules durable?**

No. `@Scheduled` triggers a method on a timer; job data must be persisted durably if recovery is needed.

**4. Does `TaskScheduler.schedule(Runnable, Instant)` guarantee schedules survive a JVM restart?**

Not if using only an in-memory scheduler. Persistence/rehydration or a scheduler with a durable job store is required.

**5. Why store `Instant`?**

It represents an absolute UTC point in time, preventing servers in different timezones from misinterpreting dispatch time.

**6. Why still store `zoneId`?**

To display the local schedule accurately and interpret/adjust time rules, especially for recurring schedules or timezone changes.

**7. If an API receives `2026-11-20T09:00:00` without a zone, what should the server do?**

Do not guess the timezone. Require a `zoneId`/offset or enforce an explicit API contract.

**8. What is a DST gap?**

A local time that does not exist when clocks jump forward. The system should reject it or apply an approved policy, never shift silently.

**9. What is a DST overlap?**

A local time that occurs twice with two UTC offsets. If an exact send time matters, require offset selection or an explicit rule.

**10. When a user chooses NOW, should client or server time be used?**

Typically use the system `Clock` when recording the request, rather than trusting an arbitrary client timestamp to decide send time.

**11. Why keep `scheduledAt` and `availableAt` separate?**

`scheduledAt` preserves the user-requested schedule; `availableAt` enables deferring for retries, quotas, or backoff without altering the original schedule.

**12. When SMTP returns 451 at the scheduled time, should it be marked SUBMITTED?**

No. That is a temporary submission failure; it may retry with backoff if not expired, while keeping the original `scheduledAt`.

**13. Can a worker send before 09:00 so the email lands in the Inbox at 09:00?**

No, if the contract forbids submitting before 09:00. SMTP also cannot guarantee when an Inbox receives a message.

**14. Why use a transactional outbox in a payment flow?**

To persist the send request in the same business transaction and call SMTP only after commit, avoiding lost requests or inconsistent rollbacks.

**15. Does HTTP 202 Accepted mean the email was delivered?**

No. It usually only indicates the send request was accepted/stored, depending on the API contract.

**16. What can happen if two workers SELECT the same due record?**

Both may call SMTP. Atomic claiming, leases, and fenced state transitions are required.

**17. Does `FOR UPDATE SKIP LOCKED` guarantee exactly-once SMTP?**

No. It enables atomic claiming in the database, but does not eliminate the window where a worker sends and crashes before updating the DB.

**18. Can you cancel a PROCESSING job and promise the email will not arrive?**

Not if external sending may have already started. Guaranteed cancellation applies only to states and boundaries the system controls.

**19. Why is `generation` needed during PATCH reschedules?**

To prevent stale requests from overwriting newer schedules and to help manage races between user updates and workers.

**20. What should happen if a recipient unsubscribes after scheduling?**

Re-check right before dispatch; if no longer permitted, mark SUPPRESSED and do not call SMTP.

**21. Should an OTP schedule expired due to downtime be caught up?**

Usually no. Follow token expiry/policy, which may require issuing a new OTP.

**22. If a worker is 2 minutes late, should `scheduledAt` be updated to the actual send time?**

No. Record `submittedAt` separately and measure lateness; the original schedule is evidence of the user's choice.

**23. Does a successful SMTP send mean the email is in the Inbox?**

No. Accepted submission and delivery are distinct stages; downstream deferrals or bounces can still occur.

**24. If a provider reports DEFERRED, should a new SMTP submission be created?**

Not automatically if the provider already accepted it and is retrying downstream delivery. Doing so can cause duplicates.

**25. Why store a template version or snapshot?**

So the content at send time still reflects what the user/business approved, rather than changing inadvertently when templates or data change.

**26. Can a file in a temp directory be used for an email scheduled a month out?**

No. The file may be deleted or altered; use immutable storage with appropriate retention.

**27. If the rate limiter denies a permit, should attempts increment?**

Do not increment physical SMTP attempts when the transport was never called; record the defer reason and next retry time.

**28. How does a weekly recurring schedule differ from a one-shot AT schedule?**

A recurring schedule is a rule generating multiple occurrences, each with its own timestamp and idempotency key. A one-shot AT has only one occurrence.

**29. How can schedules be tested without waiting for days?**

Use `Clock.fixed`/mutable clocks, DB claim tests, fake SMTP, and controlled time in tests.

**30. When many marketing emails become due at once, how do you avoid impacting OTPs?**

Apply priority tiers, reserved throughput, fairness, rate limiters, and concurrency caps at the appropriate scopes.

## Conclusion

**Sending immediately and sending at a requested time are orchestration problems before calling Spring Mail, not two different kinds of SMTP messages.** `JavaMailSender` sends when called; the application must decide **when to call it**, based on `scheduledAt`, timezone, status, and send authorization. For NOW, persist the request durably and dispatch promptly after commit. For AT, resolve a valid `Instant` from the user's choice, never send ahead of schedule, preserve schedules across restarts, and make late-send/expiry policies explicit.

A reliable design combines a transactional outbox, `@Scheduled` as a due-job polling trigger, atomic claiming/leases/fencing for multiple workers, backoff retries with a separate `availableAt`, and versioned cancel/reschedule APIs. Before every submission, re-check consent, recipient eligibility, token expiry, template/attachment availability, and quotas. Once SMTP has accepted a message, never treat "not yet delivered" as a reason to resend; when a final reply is lost, handle `SUBMISSION_UNKNOWN` and duplicate risks explicitly. Finally, use `Clock` in tests, measure queue delay/submission lateness, and maintain runbooks for outages, backlogs, and race conditions.

**A good email scheduling system does not merely trigger `send()` on time—it honors the user's time choice, never loses requests, never sends cancelled or expired messages, and never creates duplicates during recovery.**
