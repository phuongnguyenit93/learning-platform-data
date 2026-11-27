# Task Scheduling, Time Zones, and Handling Duplicate Schedule Runs

A serverless system often needs to run time-based work: sending morning reports, syncing data hourly, sending reminders a day ahead, or closing periods at month-end. With Java functions, a scheduling service typically emits an event or message to trigger the function. The function handles that run and exits; the scheduler and queue are responsible for maintaining the schedule, delivering work, and retrying failures.

Schedule design is more than writing a cron expression. The application must define which time zone governs timing, what happens when local clocks shift for daylight saving time (DST), how to handle delayed runs, and how to prevent double-processing when a scheduler or queue redelivers the same occurrence. These decisions directly affect business correctness.

## 1. Distinguishing One-Time, Calendar-Based, and Fixed-Interval Schedules

There are three common scheduling patterns:

| Type | Meaning | Example |
|---|---|---|
| One-time | Runs at a specific point in time | Send a reminder at `2026-12-01T02:00:00Z` |
| Calendar-based | Runs by date/week/month and local time | Every day at 09:00 in the customer's time zone |
| Fixed interval | Runs after every fixed elapsed duration | Trigger a sync every 15 minutes |

Do not equate "every day at 09:00" with "every 24 hours." A calendar day can be 23 or 25 hours long in regions observing DST. Local-time schedules must preserve wall-clock time, whereas fixed-interval schedules are typically computed on an absolute timeline.

Examples:

- "Every day at 09:00 in Paris" is calendar-based, bound to the `Europe/Paris` time zone.
- "Every 24 hours" is a 24-hour `Duration`, which is not guaranteed to always land on 09:00 local time.
- "Every 15 minutes from start time" is a fixed-interval schedule.
- "At 00:00 on the first day of every month" is calendar-based; it cannot be replaced with a fixed day count.

Write down the business requirement before choosing a cron or rate expression. Phrases like "every day," "every 24 hours," "business days," "end of month," and "user's local time" carry distinct meanings.

## 2. How Schedulers, Queues, and Java Functions Work Together

The scheduler tracks when runs come due. When an occurrence is due, the scheduler emits an event or enqueues a message. The queue holds work for worker functions to pick up and execute. This separates timing determination from business execution.

~~~mermaid
sequenceDiagram
    participant S as Scheduler
    participant Q as Queue
    participant F as Java Function
    participant D as Database
    S->>Q: Emit occurrence event
    Q->>F: Deliver message
    F->>D: Check / claim occurrence
    D-->>F: Proceed or already processed
    F->>D: Write result and state
    F-->>Q: Acknowledge message
~~~

Each component has a distinct role:

- **Scheduler:** stores schedules, computes the next occurrence, emits events when due, and retries per service policy.
- **Queue:** holds messages, distributes to workers, manages visibility/acknowledgement, and redelivers on worker failures.
- **Java function:** validates the event, verifies the occurrence, executes business logic, writes state, and acknowledges the message per protocol.
- **Database or state store:** persists schedules, runs, idempotency keys, checkpoints, and business outcomes.

Do not use a thread inside a Java function to sleep until run time. Execution environments can be frozen or reclaimed; functions can scale to zero; and multiple instances can create duplicate schedules. An in-process `ScheduledExecutorService` suits only internal tasks tied to process lifetime, never durable scheduling in serverless systems.

Nor is a scheduler a precision clock guaranteeing a function starts at the exact target second. Delays can occur from load, retries, queue backlogs, concurrency caps, or service disruptions. Applications should distinguish scheduled time from actual execution time.

## 3. Storing Time Properly

### 3.1. Instant, LocalDateTime, and ZonedDateTime

Java provides distinct temporal types for distinct purposes:

| Type | Representation | When to Use |
|---|---|---|
| `Instant` | A single point on the UTC timeline | Execution instants, event timestamps, logs, and persisting occurrences |
| `LocalDateTime` | Local date and time without a time zone | User-entered wall-clock times, e.g., 09:00 on Dec 1 |
| `LocalDate` | A calendar date without time or time zone | Billing dates or holidays |
| `ZoneId` | Time-zone rules, e.g., `Asia/Ho_Chi_Minh` | Resolving local time per regional rules |
| `ZonedDateTime` | Local date-time paired with `ZoneId` and resolved offset | Computing and displaying an occurrence in a region |

An `Instant` always identifies a unique moment in time. `LocalDateTime` does not: 09:00 on Dec 1 maps to different `Instant`s across time zones. Therefore, never store local time as a bare `"09:00"` string assuming every server interprets it identically.

For one-time schedules, typically store the resolved `Instant`. For recurring local-time schedules, store both the recurrence rule and `ZoneId`, for example:

~~~text
schedule_id: monthly-report-tenant-42
recurrence: 0 9 1 * *
zone_id: Europe/Paris
misfire_policy: COALESCE
overlap_policy: SKIP_IF_RUNNING
enabled: true
~~~

This example illustrates data structure only; cron syntax and policy names must match your actual scheduler. Storing only a numeric offset like `+01:00` leaves the application unaware of DST rules and future time-zone changes.

### 3.2. Use ZoneId Instead of Fixed Offsets

`ZoneId` relies on the IANA time-zone database, containing historical rules and announced changes. A zone like `Europe/Paris` shifts offsets seasonally; `Asia/Ho_Chi_Minh` follows different rules. Never manually add or subtract a fixed number of hours to convert between UTC and local time.

Example converting an `Instant` to local time:

~~~java
Instant scheduledAt = Instant.parse("2026-12-01T08:00:00Z");
ZoneId zone = ZoneId.of("Europe/Paris");

ZonedDateTime localTime = scheduledAt.atZone(zone);
System.out.println(localTime);
~~~

To schedule in a user's local time, store the user-selected `ZoneId`. If a user changes residence or profile time zone, decide whether existing schedules update or keep the zone chosen when created. That is a business decision and should never be inferred from a server's time zone.

### 3.3. Never Rely on the Server Default Time Zone

Default time zones can differ across developer laptops, containers, cloud environments, and regions. Code calling `LocalDateTime.now()` or `ZoneId.systemDefault()` can behave differently across deployments.

Inject `Clock` or `ZoneId` explicitly into business logic. For logs and actual event timestamps, prefer `Instant`. For local-time schedules, use the `ZoneId` stored in the schedule configuration. In tests, pass a fixed `Clock` rather than depending on the system clock.

## 4. Daylight Saving Time: Missing Hours and Repeated Hours

In regions observing DST, local clocks jump forward or fall back. This creates two situations that recurring schedules must handle explicitly.

### 4.1. Missing Hours (DST Gap)

When clocks spring forward from 01:59 to 03:00, times from 02:00 up to 03:00 do not exist on that day. A schedule set to "run at 02:30" has no valid local timestamp.

The application must choose a policy:

- Skip that day's occurrence.
- Run at the first valid time after the gap, such as 03:00.
- Shift forward by the gap duration, e.g., 02:30 becomes 03:30.
- Follow the scheduler or cron library's built-in rule.

No single rule fits every domain. Reports may tolerate running an hour late; reminders may need the nearest valid time; payment runs may require stricter rules.

### 4.2. Repeated Hours (DST Overlap)

When clocks fall back, a local hour occurs twice. For example, 02:30 can map to two different `Instant`s and two different UTC offsets.

The application must decide:

- Run only on the first occurrence.
- Run only on the second occurrence.
- Run on both occurrences.
- Pick one occurrence per local calendar day and skip the other.

If the system needs one run per local day, the idempotency key can use the schedule ID and local calendar date. If business rules want both physical instants to run, the key must distinguish the two `Instant`s or offsets.

### 4.3. Checking DST with ZoneRules in Java

The Java Time API lets you inspect how many valid offsets exist for a `LocalDateTime` in a `ZoneId`:

- Zero valid offsets: local time falls in a DST gap.
- One valid offset: unambiguous timestamp.
- Two valid offsets: local time falls in a DST overlap.

The following example illustrates a policy: during a gap, shift to the first valid time after the gap; during an overlap, select the earlier or later instant by configuration.

~~~java
enum OverlapPolicy {
    EARLIER,
    LATER
}

static ZonedDateTime resolveLocalTime(
        LocalDate date,
        LocalTime time,
        ZoneId zone,
        OverlapPolicy overlapPolicy) {

    LocalDateTime local = LocalDateTime.of(date, time);
    ZoneRules rules = zone.getRules();
    List<ZoneOffset> offsets = rules.getValidOffsets(local);

    if (offsets.size() == 1) {
        return ZonedDateTime.ofLocal(local, zone, offsets.get(0));
    }

    if (offsets.isEmpty()) {
        ZoneOffsetTransition transition = rules.getTransition(local);
        return transition.getDateTimeAfter().atZone(zone);
    }

    ZoneOffset selected = overlapPolicy == OverlapPolicy.EARLIER
            ? offsets.get(0)
            : offsets.get(offsets.size() - 1);

    return ZonedDateTime.ofLocal(local, zone, selected);
}
~~~

This snippet requires imports from `java.time`, `java.time.zone`, and `java.util`. It implements one specific policy; applications should add skip or shift options if required by business rules.

Never hand-roll offset arithmetic. Use `ZoneRules` to apply regional rules. Also keep time-zone database versions updated across runtimes and schedulers, as DST laws can change by legislative action.

## 5. Cron, Rate Expressions, and Calendar Schedules

Cron typically describes fields like minute, hour, day of month, month, and day of week. Yet cron has no single universal dialect. Schedulers differ on:

- Presence or absence of a seconds field.
- Syntax for day-of-month and day-of-week.
- Wildcards for "unspecified" or "last day of month."
- Behavior when both day-of-month and day-of-week are specified.
- How time zones are specified.
- Behavior when an occurrence falls in a DST gap or overlap.

Never copy a cron expression from one system to another without checking documentation. Validate expressions at schedule creation time and store the time zone alongside the policy version.

Conceptual examples:

| Requirement | Expression or Representation |
|---|---|
| Every day at 09:00 | Hour/minute cron bound to `ZoneId` |
| Monday to Friday at 08:30 | Day-of-week cron bound to `ZoneId` |
| Every 15 minutes | Rate/fixed interval or minute cron |
| First day of month at 00:00 | Day-of-month cron |
| Exactly 24 hours after the previous run | Fixed interval over `Instant` |

For calendar-based schedules, schedulers typically compute occurrences using the calendar and time zone. For fixed intervals, clarify whether intervals measure from actual start time, prior scheduled time, or after the prior run completes. These three approaches diverge whenever a function runs long or starts late.

## 6. Misfires: What Happens When a Schedule Is Missed?

A misfire is an occurrence that came due without firing on time. Causes include scheduler outages, queue unavailability, function throttling, concurrency limits, or maintenance windows.

Upon recovery, the system needs an explicit policy:

| Policy | Behavior | Best Fit |
|---|---|---|
| Catch up all | Fire all missed occurrences | Every period must run, e.g., daily accounting entries |
| Coalesce | Merge multiple missed occurrences into one run | Only latest state matters, e.g., snapshot sync |
| Skip missed | Ignore old occurrences and wait for the next one | Stale work no longer holds value |
| Expire after deadline | Run only if within allowed staleness window | Time-sensitive reminders or promotions |
| Manual recovery | Queue missed occurrences for manual review | High-risk business tasks |

"Catch up all" can trigger a heavy post-outage surge. If 30 missed runs fire simultaneously, functions, databases, and external APIs can overload. When choosing catch-up, throttle replay rates, batch sizes, and concurrency.

Not every scheduler supports all misfire modes above. Some drop occurrences if the target is unavailable, some retry for a bounded window, and others only guarantee emission within a window. Check your provider's contract. If business rules mandate running every period, persist schedule occurrences or watermarks in durable storage so workers can reconcile and backfill missing runs.

Coalescing requires defining how runs merge. You may keep only the latest occurrence, or emit one job covering the missed interval. Never coalesce if each occurrence represents a distinct obligation, such as an invoice or billing cycle.

A scheduler event should carry the occurrence's intended scheduled time. Workers use that timestamp to determine which period the work belongs to—never the message receipt timestamp. If a worker receives an event late, actual arrival time must not alter the occurrence's identity.

## 7. Why Can Scheduled Jobs Run Twice?

Duplicate execution is not necessarily a scheduler bug. Duplicates can arise at several layers:

- The scheduler resends an event after missing an acknowledgement.
- The queue redelivers a message when a worker times out or fails to ack promptly.
- The function finishes side effects but fails before acknowledging the message.
- Two separate schedules accidentally represent the same business job.
- An operator creates a new schedule without disabling the old one.
- Two function instances receive or process the same occurrence concurrently.
- A prior run is still executing when the next occurrence becomes due.
- Catch-up replays old occurrences after an outage.

In distributed systems, never assume "each schedule executes strictly once." Schedulers and queues usually favor redelivery to avoid dropping work. Workers must tolerate duplicates and enforce idempotent execution.

### 7.1. Do Not Use Message Receipt Time as an Idempotency Key

Suppose the same occurrence is delivered at 09:00:01 and retried at 09:00:20. If the key uses receipt time, both deliveries produce different keys and both execute business logic.

Use a stable identifier for the scheduled run, such as:

~~~text
occurrence_key = schedule_id + ":" + scheduled_at_utc
~~~

If the business rule is once per local calendar day, combine `scheduleId` and `LocalDate`. If both runs of a repeated DST-overlap hour should execute, use `Instant` or offset to distinguish them.

Events should include fields such as:

~~~json
{
  "scheduleId": "daily-report-tenant-42",
  "occurrenceId": "daily-report-tenant-42:2026-12-01T08:00:00Z",
  "scheduledAt": "2026-12-01T08:00:00Z",
  "scheduleVersion": 3
}
~~~

This is an illustrative payload. A provider's delivery event ID helps trace deliveries, yet is not necessarily the business occurrence identifier. Multiple redeliveries may carry different delivery IDs while belonging to the exact same scheduled occurrence.

## 8. Idempotency and Persisting Occurrence State

### 8.1. Creating Occurrence Records with Unique Keys

A common pattern is storing each occurrence in a state table with a unique key composed of schedule ID and occurrence ID or scheduled instant.

Conceptual schema example:

| Field | Purpose |
|---|---|
| `schedule_id` | Schedule identifier |
| `occurrence_id` | Scheduled run identifier |
| `scheduled_at` | Scheduled `Instant` |
| `status` | `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, or `CANCELLED` |
| `attempt_count` | Attempt counter |
| `lease_owner` | Worker currently holding processing rights |
| `lease_until` | Lease expiration timestamp |
| `fencing_token` | Monotonically increasing ownership token |
| `completed_at` | Completion timestamp |

Create occurrences via an insert enforced by a unique constraint. If the insert fails because the key exists, the worker reads the current state to decide whether to skip, retry, or resume recovery. Never rely on a separate `SELECT` followed by `INSERT`; two workers can both read "not found" before either inserts.

### 8.2. Java Example with an Occurrence Store

This example uses Java 16+ records. `ScheduledEvent` and the `OccurrenceStore` implementation are application-defined components.

~~~java
public record OccurrenceKey(
        String scheduleId,
        Instant scheduledAt
) {}

public record OccurrenceClaim(
        boolean acquired,
        long fencingToken
) {}

public interface OccurrenceStore {
    OccurrenceClaim claim(OccurrenceKey key);
    void markSucceeded(OccurrenceKey key, long fencingToken);
    void markRetryableFailure(
            OccurrenceKey key,
            long fencingToken,
            String reason
    );
}

void handleScheduledEvent(ScheduledEvent event) throws Exception {
    OccurrenceKey key = new OccurrenceKey(
            event.scheduleId(),
            event.scheduledAt()
    );

    OccurrenceClaim claim = occurrenceStore.claim(key);
    if (!claim.acquired()) {
        return;
    }

    try {
        runBusinessWork(event);
        occurrenceStore.markSucceeded(key, claim.fencingToken());
    } catch (Exception error) {
        occurrenceStore.markRetryableFailure(
                key,
                claim.fencingToken(),
                error.getClass().getSimpleName()
        );
        throw error;
    }
}
~~~

This is an architectural illustration; `claim` must be atomic in durable storage. It must distinguish completed occurrences from ones actively running on another worker and ones with expired leases. Skipping every existing record unconditionally would prevent workers from resuming an occurrence that crashed mid-flight.

If business logic involves multiple side effects, such as writing to a database and sending an email, a single claim cannot magically grant exactly-once across both systems. Persist business state and an outbox entry in the same transaction, then have a publisher send the email with an idempotency key. The receiver or email service must support deduplication if preventing duplicate sends is mandatory.

### 8.3. Leases and Fencing Tokens

A worker can crash mid-execution. Without expiration on `RUNNING` state, the occurrence remains stuck forever. A lease grants processing ownership until a deadline; if the lease expires, another worker can reclaim it.

However, a lease alone is not enough. An old worker may pause briefly, lose its lease, and a new worker claims the task. When the old worker resumes, both could write data. A fencing token increments on every claim. Every write checks the current token; stale tokens are rejected from overwriting the newer worker's results.

Renew leases (heartbeats) for long-running work. Lease duration should exceed the heartbeat interval and align with invocation timeouts. As a function nears its deadline, it should stop at a safe checkpoint or yield ownership per the designed protocol.

## 9. Handling Closely Spaced Occurrences

If a task runs longer than the schedule interval, two occurrences can overlap. For instance, a report scheduled every 10 minutes takes 18 minutes on a heavy run.

Choose an explicit overlap policy:

- **Allow overlap:** allow concurrent occurrences. Suitable only when runs are independent and dependencies tolerate combined load.
- **Skip if running:** skip the new occurrence if the previous run is still active.
- **Queue:** queue the new occurrence to run next.
- **Coalesce:** merge multiple pending occurrences into one run.
- **Replace/cancel previous:** cancel or supersede the previous run if business rules allow.

Define the policy per schedule or job type. Never lock using an in-memory boolean flag, as separate execution environments do not share memory. Use database transactions, distributed locks, or scheduler/queue concurrency controls.

When using a queue, visibility timeout or acknowledgement deadline must match processing duration. If a message becomes visible again while the old worker is still running, the queue can deliver the same message to a second worker. Setting the timeout too long delays retries when a worker actually dies. Extend visibility during processing if supported, while always maintaining idempotency.

## 10. Managing Schedule Changes and Versions

Schedules can be created, edited, paused, or deleted while occurrences are being emitted or processed. Maintain a stable schedule ID and increment a version number on every configuration change.

Clarify these edge cases:

- Should occurrences already emitted under an old version continue processing?
- Does a time-zone change take effect immediately or on the next occurrence?
- Does changing the run time cancel already-queued occurrences?
- Does deleting a schedule abort in-flight jobs?
- If paused and re-enabled, are missed occurrences caught up or skipped?
- When updating cron rules, how do you prevent old and new schedulers from firing the same occurrence?

One approach is storing `scheduleVersion` in both events and occurrence records. Workers verify version alongside effective-date policies. When updating a schedule, use a transaction or stateful workflow to create the new version, retire the old version, and reconcile pending occurrences. Never distinguish versions solely by schedule display name.

## 11. Security and Permissions for Scheduled Events

Schedulers typically invoke queues or functions via a service identity. Grant permission to publish only to the required queue or invoke only the required function. Workers should only read from their assigned queues and access business resources needed for the job.

Do not treat scheduler payloads as implicitly trustworthy. Workers still must:

- Validate the event schema and version.
- Verify that the schedule ID exists and is currently enabled.
- Enforce tenant isolation and permissions from authenticated state.
- Reject invalid tenant or resource IDs.
- Never allow events to specify arbitrary URLs or commands to execute.
- Keep secrets out of messages; use a secret manager or service identities.
- Audit schedule changes, creators, editors, and manual triggers.

If an endpoint lets users create schedules, cap schedules per tenant, minimum recurrence frequency, maximum horizon, and supported recurrence types. Otherwise, one account could create millions of schedules or 1-second schedules to exhaust resources.

## 12. Observing Latency, Duplicates, and Misfires

A scheduling system should track at least three timestamps:

- **`scheduledAt`:** when the occurrence was due.
- **`receivedAt`:** when the worker received the event or message.
- **`startedAt`:** when business processing began.

From these, compute `schedule lag = receivedAt - scheduledAt` and `queue wait = startedAt - receivedAt`. Also track processing duration, completion timestamp, and retry counts.

Useful metrics include:

- Scheduled, emitted, and missed occurrence counts.
- p50/p95/p99 schedule lag.
- Age of oldest message in the queue.
- Duplicate event count and idempotency rejections.
- Occurrences stuck in `RUNNING` past their lease.
- Lease expirations, reclaims, and fencing conflicts.
- Catch-up, coalesced, skipped, and expired job counts.
- Success rate, retries, DLQ depth, and processing duration.
- Active schedules per tenant and schedule edit counts.

Logs should include `scheduleId`, `scheduleVersion`, `occurrenceId`, `scheduledAt`, delivery ID, attempt count, and correlation ID. Never log tokens, secrets, or sensitive payloads. During incidents, these fields distinguish duplicate scheduler emissions, queue redeliveries, and worker-induced duplicates.

## 13. Testing Schedules and Time Zones

Do not test schedules only on an ordinary day. Test:

1. One-time schedule at a specific UTC instant.
2. Daily schedule in a DST-observing time zone.
3. Local time falling inside a DST gap.
4. Local time falling inside a DST overlap.
5. Schedule time-zone change while an occurrence is pending.
6. Late scheduler emission after an outage.
7. Multiple missed occurrences catching up together.
8. Two workers receiving the same occurrence nearly simultaneously.
9. Worker crash after side effects but before acknowledgement.
10. Lease expiration while the original worker is still running.
11. Previous run overrunning into the next occurrence.
12. Duplicate schedule creation or stale version still emitting events.
13. Queue visibility timeout shorter than processing duration.
14. Tenant hitting schedule quota or minimum frequency limits.

Use a fixed `Clock` to test temporal logic. Test `ZoneRules` across DST transition dates rather than waiting for those calendar dates in live environments. In integration tests, verify the exact cron dialect and time-zone behavior of your chosen scheduler.

## 14. Process for Designing a Durable Schedule

1. **Clarify time semantics.** Is the schedule by local wall-clock time, UTC, or fixed elapsed duration?
2. **Select `ZoneId`.** Store the IANA zone name and DST rules; never rely on default process time zones.
3. **Define occurrences.** Build a stable identifier from `scheduleId` and scheduled instant or business date.
4. **Pick a misfire policy.** Catch up, coalesce, skip, expire, or manual recovery.
5. **Pick an overlap policy.** Allow parallel, skip, queue, or coalesce when the prior run is active.
6. **Design idempotency.** Unique constraints, occurrence store, state transitions, and lease/fencing if needed.
7. **Configure retries and DLQs.** Cap attempts, add backoff, and document recovery procedures.
8. **Enforce permissions.** Scope scheduler, queue, worker, and schedule-creator permissions.
9. **Measure lag and duplicates.** Track `scheduledAt`, `receivedAt`, `startedAt`, and outcomes.
10. **Test DST and failures.** Simulate gaps, overlaps, backlogs, worker crashes, and concurrent runs.

Treat durable scheduling as an identified work-generation stream. The scheduler decides when an occurrence is due; the queue guarantees delivery to workers; Java functions execute idempotently and persist state for safe retries or recovery.

## 15. Self-Check Questions

- Why does "every day at 09:00" differ from "every 24 hours"?
- How do `Instant`, `LocalDateTime`, and `ZonedDateTime` differ?
- How do DST gaps and DST overlaps affect recurring schedules?
- Why store `ZoneId` instead of just a numeric offset?
- What risk does a catch-up-all misfire policy create after an outage?
- Why is a queue delivery ID not always suitable as an `occurrenceId`?
- How do you prevent two concurrent workers from processing the same occurrence?
- Why does a lease need a fencing token when an old worker might resume?
- What should happen when a previous run overruns into the next occurrence?
- How do you update a schedule without old and new versions firing the same occurrence simultaneously?

Mastering scheduling, time zones, and duplicates enables serverless Java developers to build resilient recurring jobs. Define each occurrence unambiguously, store times with the right types, choose explicit DST and misfire policies, and design idempotent workers so retries never cause duplicate business side effects.
