# Timezones for Scheduled Email Sending

An application using **Spring Framework Mail** may send order-confirmation emails immediately, yet also need to send reports at **09:00 AM in the user's local time**, pre-meeting reminders, or multi-country campaigns. At that point, the problem goes well beyond calling `JavaMailSender.send(...)`. You must define **09:00 in which timezone**, store the send timestamp without depending on the server's timezone, handle **Daylight Saving Time (DST)** transitions, recover schedules after restarts, and avoid duplicate sends across multiple workers.

For example, "09:00 on 2026-12-01" does not pinpoint a single moment on the global timeline. The same string can mean:

- 09:00 in **Asia/Ho_Chi_Minh**: 02:00 UTC.
- 09:00 in **Europe/Berlin** in winter: 08:00 UTC.
- 09:00 in **America/New_York** in winter: 14:00 UTC.

A system storing only `LocalDateTime` and assuming the server's default timezone can send hours off schedule. A system storing only UTC can compute a **single specific send** accurately, yet still lacks the metadata to continue a **recurring schedule at 09:00 local time** when offsets shift seasonally.

This lesson covers Java's time model (`java.time`), the difference between **instants, offsets, and timezones**, resolving local times under DST, schedule data design for Spring Mail, `@Scheduled`/cron, transactional outbox, retries/expiration, testing with mock clocks, and multi-region operations.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain `Instant`, `LocalDateTime`, `OffsetDateTime`, `ZonedDateTime`, `ZoneId`, and `Clock`.
2. Distinguish an **absolute point in time** from **local wall-clock time governed by timezone rules**.
3. Persist a one-shot send schedule independent of JVM or database-session timezones.
4. Persist recurring schedules using **IANA time-zone IDs** rather than only a static current offset.
5. Define policies for local times that **do not exist** or **occur twice** during DST transitions.
6. Configure `@Scheduled(cron = ..., zone = ...)` and understand cron's limits across multiple replicas.
7. Compute upcoming occurrences from local time in the user's timezone.
8. Use a **due-job poller** to find jobs with `send_at <= now` and send them via `JavaMailSender`.
9. Design states: `PENDING`, `SENDING`, `SMTP_ACCEPTED`, `RETRY_WAIT`, `CANCELLED`, and `UNKNOWN`.
10. Distinguish **when submission may start** from **when the provider delivers the email to the recipient**.
11. Test DST boundaries, clock skew, timezone mismatches, and restarts using `Clock.fixed(...)`.
12. Handle timezone updates, quiet-hours policies, deadlines, cancellations, and timezone-rule changes.

## 2. Which Parts of the Sending Flow Do Timezones Affect?

```text
User:
"2026-12-01 at 09:00 in Vietnam"
                    |
                    v
Schedule API:
localDateTime + ZoneId + policy
                    |
                    v
Resolve to Instant:
2026-12-01T02:00:00Z
                    |
                    v
Database scheduled_email:
due_at (UTC instant)
zone_id + local input (preserves intent)
                    |
                    v
Due-job dispatcher:
WHERE due_at <= now
                    |
                    v
Claim job + worker
                    |
                    v
JavaMailSender / SMTP relay
                    |
                    v
SMTP submission accepted
                    |
                    v
Provider delivery (may be delayed)
```

There are **three layers of time** to keep separate:

- **User intent:** "09:00 AM in Ho Chi Minh City", "every Monday at 09:00 Berlin time".
- **Technical execution timestamp:** a concrete `Instant`, e.g., `2026-12-01T02:00:00Z`.
- **Actual event timestamps:** when a worker starts sending, SMTP accepts, and provider delivers; these can lag behind schedule.

An accurate scheduling system persists both the intent and the execution instant, while recording when submission actually happened. Never treat "email scheduled for 09:00" as a guarantee the recipient receives it at 09:00 sharp.

## 3. java.time Fundamentals: Choosing the Right Type

Java 8+ provides the `java.time` API for dates and times. Using semantically precise types reduces timezone bugs.

| Type | Holds | Identifies one instant? | Use in mail scheduling |
|---|---|---|---|
| `Instant` | Absolute point on the UTC timeline | Yes | `sendAt`, `createdAt`, `claimedAt`, `nextAttemptAt` |
| `LocalDate` | Calendar date without time/zone | No | Business date or recurring start date |
| `LocalTime` | Time of day without date/zone | No | "09:00 daily" |
| `LocalDateTime` | Local date and time, **no zone/offset** | No | "2026-12-01 09:00" intent before resolution |
| `ZoneOffset` | Fixed UTC offset, e.g., `+07:00` | Yes when paired with local datetime | Offset at one instant; holds no future DST rules |
| `OffsetDateTime` | Local datetime + offset | Yes | API accepting a concrete instant with offset |
| `ZoneId` | Rule region like `Europe/Berlin` | No, on its own | Stores user/recurring-schedule timezone |
| `ZonedDateTime` | Local datetime + `ZoneId` + resolved offset | Yes | Displaying and computing one send in a zone |
| `Clock` | Replaceable time source | Via `instant()` | Testing due times, deadlines, retries, and schedulers |

### 3.1. Instant is the unified point in time

```java
import java.time.Instant;

Instant dueAt = Instant.parse("2026-12-01T02:00:00Z");
```

An `Instant` carries no "Berlin time" or "Saigon time" inside it. It represents the exact same moment across every system.

### 3.2. LocalDateTime does not imply UTC

```java
import java.time.LocalDateTime;

LocalDateTime requested =
    LocalDateTime.of(2026, 12, 1, 9, 0);
```

This value is **not yet enough to send**. It does not know whether 09:00 is in Vietnam, Germany, or the US. Never call `toInstant(ZoneOffset.UTC)` on every `LocalDateTime` unless the user truly chose UTC.

### 3.3. ZoneId holds time rules

```java
import java.time.ZoneId;

ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
ZoneId berlin = ZoneId.of("Europe/Berlin");
ZoneId newYork = ZoneId.of("America/New_York");
```

These IDs come from the **IANA Time Zone Database (tzdb)** used by the Java runtime. A `ZoneId` encodes offset rules and DST transitions across historical and future dates.

### 3.4. Offset does not replace ZoneId

`Europe/Berlin` uses:
- `+01:00` in winter;
- `+02:00` in summer.

If you only save `+01:00` for "09:00 Berlin time daily", in summer the system will keep sending at `+01:00` and miss 09:00 Berlin by an hour.

**Use an offset for a single resolved timestamp; use `ZoneId` for local schedule intents that must survive rule changes.**

## 4. Example: Converting a Schedule in Vietnam

A user picks "2026-12-01, 09:00" in `Asia/Ho_Chi_Minh`.

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

LocalDateTime local = LocalDateTime.of(
    2026, 12, 1, 9, 0
);

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime zoned = local.atZone(zone);
Instant sendAt = zoned.toInstant();

System.out.println(sendAt);
// 2026-12-01T02:00:00Z
```

Vietnam currently observes UTC+07:00 year-round without DST, so current conversions are straightforward. Even so, still store `Asia/Ho_Chi_Minh` instead of hardcoding `+07:00`: the zone ID captures user intent and handles historical or future legal changes.

### 4.1. Same instant, multiple displays

```java
Instant sendAt = Instant.parse(
    "2026-12-01T02:00:00Z"
);

System.out.println(
    sendAt.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
);
// 2026-12-01T09:00+07:00[Asia/Ho_Chi_Minh]

System.out.println(
    sendAt.atZone(ZoneId.of("Europe/Berlin"))
);
// 2026-12-01T03:00+01:00[Europe/Berlin]
```

Both representations denote the **exact same instant**. If the UI renders in a viewer's timezone without showing the zone label, users may think the schedule shifted.

### 4.2. Database rules

To execute a send, store an absolute instant like `Instant`. To explain or update schedules, also store:
- `local_send_time`;
- `zone_id`;
- DST handling policy;
- creator metadata and schedule kind.

Never store only the string "09:00" or only the current offset.

## 5. Timezones Across Layers: Server, JVM, Database, Browser

One system can simultaneously involve:

```text
Browser: America/New_York
API server JVM: UTC
Worker JVM: Asia/Ho_Chi_Minh
Database connection session: UTC
SMTP relay: Europe/Berlin
Recipient: Asia/Tokyo
```

These timezones **do not have to match**. Bugs arise when code silently treats one layer's "default zone" as the source of truth:

```java
// May change meaning depending on host configuration:
ZoneId zone = ZoneId.systemDefault();
```

When the business requirement is "user's local time", `systemDefault()` has no basis to represent that choice.

### 5.1. Browser timezone is not always a confirmed choice

A browser can report the device's current timezone, but:
- the user may be traveling;
- the device clock/timezone may be misconfigured;
- the schedule may belong to a store/branch rather than the creator;
- an admin may schedule on behalf of someone in another country.

Display the timezone explicitly in the UI and persist the confirmed/authorized value.

### 5.2. Running servers and databases in UTC is a strong operational practice

Setting infrastructure defaults to UTC keeps logs, monitoring, and cross-node communication consistent. Still, **even when every server runs UTC, business scheduling still requires the user's `ZoneId`**.

### 5.3. Never infer recipient timezone from an email address

You cannot deduce from `user@example.com` which timezone the recipient lives in. Nor should you infer timezone solely from UI language or nationality. Obtain it from explicit preferences, intentional location/business settings, or an explicit field in the request.

## 6. Two Schedule Types: One-Shot and Recurring

This is the single most important design decision.

### 6.1. One-shot schedule

> Send an email at 09:00 on 2026-12-01 Vietnam time.

Once resolved, there is exactly one `Instant`:

```text
local = 2026-12-01T09:00
zone = Asia/Ho_Chi_Minh
sendAt = 2026-12-01T02:00:00Z
```

If the user changes their display timezone after scheduling, `sendAt` can remain unchanged. It is an **appointment at a fixed instant**, unless product rules allow editing the schedule.

### 6.2. Recurring schedule in local time

> Send a report every business day at 09:00 Berlin time.

Do not merely add `Duration.ofDays(1)` to the prior `Instant`. When Berlin shifts from +01 to +02, local wall-clock time remains 09:00 while the UTC instant shifts by one hour.

```text
Winter (Berlin +01):
09:00 local -> 08:00 UTC

Summer (Berlin +02):
09:00 local -> 07:00 UTC
```

Store a **recurrence rule** and `ZoneId`, then derive each occurrence from the zone's **local date**.

### 6.3. Periodic schedule by absolute duration

> Send a technical report every 24 hours from the first run.

This is a **fixed duration**, distinct from "every day at 09:00". Adding `Duration.ofHours(24)` fits when the requirement is literally a 24-hour interval rather than wall-clock time.

**Document the contract clearly: "every 24 hours" and "every day at 09:00" diverge in DST-observing regions.**

## 7. Understanding Daylight Saving Time (DST)

Some countries adjust clocks in spring and autumn, creating two edge cases:

1. **Gap:** a local time range **does not exist** when clocks jump forward.
2. **Overlap:** a local time range **occurs twice** when clocks fall back.

In `Europe/Berlin` in 2026:

- On **2026-03-29**, clocks jump from 02:00 to 03:00. `02:30` does not exist.
- On **2026-10-25**, clocks fall back from 03:00 to 02:00. `02:30` occurs twice.

### 7.1. Spring forward: nonexistent time

```text
Europe/Berlin — 2026-03-29

01:58 +01
01:59 +01
03:00 +02   <-- 02:00 to 02:59 does not exist
03:01 +02
```

A schedule for "2026-03-29 02:30 Berlin" cannot be represented by a `ZonedDateTime` preserving 02:30 wall time in that zone.

You must define an explicit policy:
- **REJECT:** reject a one-shot schedule at a nonexistent time.
- **SKIP:** skip that day's occurrence for a recurring schedule.
- **NEXT_VALID_TIME:** send at the first valid local time after the gap, e.g., 03:00.
- **SHIFT_BY_GAP:** shift forward by the gap duration, e.g., 02:30 → 03:30.

Each option yields a different result. Never let a library pick implicitly without checking requirements.

### 7.2. Fall back: repeated time

```text
Europe/Berlin — 2026-10-25

02:30 +02 -> 2026-10-25T00:30:00Z
...
02:30 +01 -> 2026-10-25T01:30:00Z
```

If a user chooses "02:30", two valid instants exist. Policies can be:
- **EARLIER_OFFSET:** first occurrence.
- **LATER_OFFSET:** second occurrence.
- **BOTH:** send twice (only if explicitly required).
- **REJECT:** require the user to choose explicitly.

For transactional emails or periodic reports, **sending twice during an overlap is usually a bug**, so lock down the rule before dispatch.

### 7.3. LocalDateTime.atZone has default behavior

```java
LocalDateTime local =
    LocalDateTime.of(2026, 3, 29, 2, 30);

ZonedDateTime result = local.atZone(
    ZoneId.of("Europe/Berlin")
);
```

For a time inside a gap, `atZone` typically pushes forward to a valid post-gap time. For an overlap, it typically picks the earlier offset. This is convenient Java behavior, but **must not be assumed as business policy** if your product requires confirmation, skipping, or another choice.

## 8. Detecting Gaps and Overlaps With ZoneRules

`ZoneRules.getValidOffsets(local)` tells how many valid offsets exist for a local time:

- `1 offset`: normal.
- `0 offsets`: gap.
- `2 offsets`: overlap (under standard transitions).

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.zone.ZoneRules;
import java.util.List;

ZoneId zone = ZoneId.of("Europe/Berlin");
ZoneRules rules = zone.getRules();

LocalDateTime gap =
    LocalDateTime.of(2026, 3, 29, 2, 30);

LocalDateTime overlap =
    LocalDateTime.of(2026, 10, 25, 2, 30);

List<ZoneOffset> gapOffsets =
    rules.getValidOffsets(gap);       // empty

List<ZoneOffset> overlapOffsets =
    rules.getValidOffsets(overlap);   // +02:00, +01:00
```

### 8.1. Defining explicit policies

```java
public enum GapPolicy {
    REJECT,
    SKIP,
    NEXT_VALID_TIME,
    SHIFT_BY_GAP
}

public enum OverlapPolicy {
    EARLIER_OFFSET,
    LATER_OFFSET,
    REJECT
}
```

For **one-shot** schedules, `REJECT` on nonexistent times is often clearest since the UI can ask the user to pick another time. For **recurring** schedules, define a policy that works deterministically across every DST transition.

### 8.2. Example resolver for a send timestamp

```java
package com.example.mail.schedule;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.zone.ZoneOffsetTransition;
import java.time.zone.ZoneRules;
import java.util.List;

public final class MailScheduleTimeResolver {

    public Instant resolve(
            LocalDateTime requestedLocal,
            ZoneId zone,
            GapPolicy gapPolicy,
            OverlapPolicy overlapPolicy) {

        ZoneRules rules = zone.getRules();
        List<ZoneOffset> offsets =
            rules.getValidOffsets(requestedLocal);

        if (offsets.size() == 1) {
            return ZonedDateTime.ofLocal(
                requestedLocal, zone, offsets.get(0)
            ).toInstant();
        }

        if (offsets.isEmpty()) {
            ZoneOffsetTransition transition =
                rules.getTransition(requestedLocal);

            if (gapPolicy == GapPolicy.REJECT
                    || gapPolicy == GapPolicy.SKIP) {
                throw new IllegalArgumentException(
                    "Scheduled local time does not exist"
                );
            }

            LocalDateTime adjusted;

            if (gapPolicy == GapPolicy.NEXT_VALID_TIME) {
                adjusted = transition.getDateTimeAfter();
            } else {
                adjusted = requestedLocal.plus(
                    transition.getDuration()
                );
            }

            return adjusted.atZone(zone).toInstant();
        }

        if (overlapPolicy == OverlapPolicy.REJECT) {
            throw new IllegalArgumentException(
                "Scheduled local time is ambiguous"
            );
        }

        ZoneOffset chosen =
            overlapPolicy == OverlapPolicy.EARLIER_OFFSET
                ? offsets.get(0)
                : offsets.get(offsets.size() - 1);

        return ZonedDateTime.ofLocal(
            requestedLocal, zone, chosen
        ).toInstant();
    }
}
```

Semantics:
- `NEXT_VALID_TIME` picks the first valid local instant after the gap.
- `SHIFT_BY_GAP` adds the gap duration to local time, preserving minute offset for a one-hour gap.
- `EARLIER_OFFSET`/`LATER_OFFSET` picks one unambiguous occurrence.
- `SKIP` in this example signals no instant exists; the recurrence layer should catch it and **skip that day's occurrence** rather than treating it as an SMTP failure requiring retry.

For `BOTH` on overlap, the resolver should return a **list of two instants** instead of a single `Instant`; implement this only if the product genuinely needs two sends.

### 8.3. A timezone library still does not know business intent

Java solves "which offsets are valid", but does not know:
- whether a report should skip the DST day or run at 03:00;
- whether an urgent alert should fire on the earlier or later occurrence;
- whether a user expects two emails during an overlap.

Record decisions in a **schedule policy**, test them, and surface them in the UI when needed.

## 9. Designing the Scheduling API

An ergonomic API for a one-shot send in local time:

```json
{
  "recipient": "customer@example.net",
  "templateId": "order-reminder",
  "localSendTime": "2026-12-01T09:00:00",
  "timeZone": "Asia/Ho_Chi_Minh",
  "gapPolicy": "REJECT",
  "overlapPolicy": "EARLIER_OFFSET",
  "idempotencyKey": "order-123-reminder-1"
}
```

The backend should:
1. Authenticate the caller and authorization to send to the recipient.
2. Validate `localSendTime` and `timeZone`.
3. Parse `ZoneId.of(timeZone)`; never guess a timezone when missing.
4. Use the resolver to compute `Instant`.
5. Verify the send time is valid, not expired, and within scheduling bounds.
6. Check idempotency.
7. Persist the job and return the message key plus the resolved timestamp.

### 9.1. Java DTO

```java
package com.example.mail.schedule;

import java.time.LocalDateTime;

public record CreateScheduledMailRequest(
    String recipient,
    String templateId,
    LocalDateTime localSendTime,
    String timeZone,
    GapPolicy gapPolicy,
    OverlapPolicy overlapPolicy,
    String idempotencyKey
) {}
```

Jakarta Bean Validation can validate required fields and lengths, while **timezone business validation** still requires dedicated logic.

### 9.2. Reject ambiguous timezone abbreviations

Strings like `CST`, `IST`, or `PST` are ambiguous or map unpredictably. Prefer IANA IDs:
- `Asia/Ho_Chi_Minh`;
- `Europe/Berlin`;
- `America/New_York`;
- `Asia/Tokyo`.

Never accept arbitrary strings and fall back to the server timezone on parse failure. Return an explicit validation error for invalid timezones.

### 9.3. An ISO 8601 instant can also be an input

A service-to-service API may accept:

```json
{
  "sendAt": "2026-12-01T02:00:00Z"
}
```

This specifies an unambiguous absolute instant. However, if users also need to **reschedule in local time** or use **recurring schedules**, the API still needs the corresponding `ZoneId`/recurrence policy. Never accept instant-only input and try to guess local wall-clock intent from IP or locale.

## 10. Validating Timezones, Send Times, and Deadlines

Useful validations:

| Condition | Recommended rule |
|---|---|
| `ZoneId` absent from tzdb | Return error; never fall back silently |
| Schedule in the past | Reject or follow an explicit "send immediately" policy |
| Schedule too far in the future | Enforce a product-appropriate horizon |
| Local time does not exist | Apply gap policy |
| Local time occurs twice | Apply overlap policy |
| Recipient not permitted to receive | Reject before persisting |
| Marketing lacks consent | Do not create send job |
| Verification token expires before `sendAt` | Reject or generate token closer to send time |
| User has quiet hours | Adjust/defer per policy |
| Schedule cancelled or job already accepted | Do not edit as if unsent |

Do not check only `sendAt.isAfter(Instant.now())` in the controller while skipping the remaining business constraints.

### 10.1. Guard simultaneously against clock skew

A request targeting right now may validate at 08:59:59.900 and commit at 09:00:00.200. If the rule is "never send early", accepting an already-due job may be fine; if the API forbids immediate/past schedules, enforce an explicit minimum lead-time rule.

### 10.2. Persist a decision snapshot

After resolving, record:
- which local date/time the user chose;
- which timezone;
- offset at calculation time;
- gap/overlap policy;
- resolved UTC instant;
- schedule version.

This lets you explain later why a job fired at a specific UTC instant.

## 11. Storing Timestamps in PostgreSQL

In PostgreSQL, `TIMESTAMPTZ` is the right type for an absolute instant. It **does not store the `ZoneId` name**.

Example schema:

```sql
CREATE TABLE scheduled_mail (
    message_key UUID PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    recipient VARCHAR(320) NOT NULL,
    template_id VARCHAR(120) NOT NULL,
    schedule_kind VARCHAR(24) NOT NULL,
    local_send_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    zone_id VARCHAR(100) NOT NULL,
    gap_policy VARCHAR(32) NOT NULL,
    overlap_policy VARCHAR(32) NOT NULL,
    send_at TIMESTAMPTZ NOT NULL,
    next_attempt_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    lease_token UUID,
    lease_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_scheduled_mail_due
    ON scheduled_mail(next_attempt_at, send_at)
    WHERE status IN ('PENDING', 'RETRY_WAIT');
```

This is a minimal illustrative schema. Production may also need:
- unique constraint for business idempotency key;
- audit and change history;
- expiration/deadline;
- provider/tenant routing;
- attempt and dead-letter tables;
- encryption and retention for recipient/payload;
- recurrence definitions in a separate table.

### 11.1. TIMESTAMPTZ does not mean "stores the timezone"

PostgreSQL `TIMESTAMPTZ` stores an absolute instant and **displays** it in the database session's timezone. It does not retain `Asia/Ho_Chi_Minh`, `Europe/Berlin`, or the offset the user entered.

For instance, the same `send_at` renders as 02:00 UTC or 09:00 +07 depending on session timezone. Both displays represent the exact same instant.

Therefore, to preserve local schedule intent, store **`zone_id` in its own column** along with `local_send_time`—not `TIMESTAMPTZ` alone.

### 11.2. When is TIMESTAMP WITHOUT TIME ZONE used?

`TIMESTAMP WITHOUT TIME ZONE` holds only local date and time with no offset. It fits storing **local intent** or local event fields, but is **insufficient alone** for querying "which jobs are due on the global timeline".

Never write:

```sql
WHERE local_send_time <= NOW()
```

without explicit timezone conversion, because the two sides have incompatible semantics.

### 11.3. Mapping in Java

`Instant` fits `send_at` at the domain layer. With JDBC, you can pass an `OffsetDateTime` in UTC for unambiguous `TIMESTAMPTZ` mapping:

```java
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

OffsetDateTime utcDateTime =
    sendAt.atOffset(ZoneOffset.UTC);
```

When reading back, convert to `Instant`. Verify driver/ORM mapping for your exact versions and test against the production database type rather than inferring from H2.

### 11.4. Database timezone and JDBC

Running the JVM in UTC, database sessions in UTC, and ISO 8601 serialization keeps operations consistent, yet the most critical rule is **never converting `LocalDateTime` to an instant using an undocumented default timezone**.

## 12. Separate Schema for Recurring Schedules

A schedule like "every Monday at 09:00 Berlin time" is a **schedule definition**; each send is an **occurrence**. Separating them allows recalculation when timezone rules change.

```sql
CREATE TABLE recurring_mail_schedule (
    schedule_id UUID PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    template_id VARCHAR(120) NOT NULL,
    zone_id VARCHAR(100) NOT NULL,
    local_time TIME WITHOUT TIME ZONE NOT NULL,
    recurrence_rule VARCHAR(180) NOT NULL,
    gap_policy VARCHAR(32) NOT NULL,
    overlap_policy VARCHAR(32) NOT NULL,
    start_local_date DATE NOT NULL,
    end_local_date DATE,
    status VARCHAR(24) NOT NULL,
    schedule_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE mail_occurrence (
    occurrence_id UUID PRIMARY KEY,
    schedule_id UUID NOT NULL
        REFERENCES recurring_mail_schedule(schedule_id),
    occurrence_local_date DATE NOT NULL,
    occurrence_slot VARCHAR(40) NOT NULL,
    send_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(24) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_mail_occurrence
        UNIQUE (
            schedule_id,
            occurrence_local_date,
            occurrence_slot
        )
);
```

`recurrence_rule` can be a simple enum like `WEEKDAYS` or an application-supported DSL/cron rule. Never accept arbitrary cron expressions from users unless your product controls cost and semantics.

### 12.1. Why separate occurrences?

- Avoid regenerating yesterday's email after a restart.
- Track independent status per send period.
- Allow cancelling one occurrence without cancelling the whole schedule.
- Allow retrying one occurrence on SMTP errors.
- Preserve a record of what was actually planned.
- Enforce a unique key stopping multiple scheduler replicas from creating two jobs for one period.

### 12.2. Overlap policy BOTH needs a distinct key

If a schedule permits **sending twice** on a DST overlap day, a unique key of just `(schedule_id, local_date)` blocks the second occurrence. Add an explicit slot/offset/occurrence index such as `first` and `second`.

For single-send policies, `occurrence_slot="single"` suffices.

## 13. Computing an Occurrence From a Local Date

Example daily report schedule at 09:00:

```java
import java.time.*;

public final class DailyScheduleCalculator {

    private final MailScheduleTimeResolver resolver;

    public DailyScheduleCalculator(
            MailScheduleTimeResolver resolver) {
        this.resolver = resolver;
    }

    public Instant occurrenceAt(
            LocalDate localDate,
            LocalTime localTime,
            ZoneId zone,
            GapPolicy gapPolicy,
            OverlapPolicy overlapPolicy) {

        LocalDateTime localDateTime =
            LocalDateTime.of(localDate, localTime);

        return resolver.resolve(
            localDateTime,
            zone,
            gapPolicy,
            overlapPolicy
        );
    }
}
```

If the schedule runs only on business days, apply an appropriate `DayOfWeek`/holiday calendar filter. Never implement recurring wall-clock schedules with:

```java
// Wrong goal if 09:00 local time must be preserved:
Instant next = previous.plus(Duration.ofDays(1));
```

### 13.1. Correct way to compute "next day"

```java
LocalDate nextLocalDate =
    previousLocalDate.plusDays(1);

Instant nextDue = calculator.occurrenceAt(
    nextLocalDate,
    LocalTime.of(9, 0),
    ZoneId.of("Europe/Berlin"),
    GapPolicy.NEXT_VALID_TIME,
    OverlapPolicy.EARLIER_OFFSET
);
```

The application advances to the **next local date** and resolves again using that day's timezone rules, so the UTC offset adjusts automatically across DST.

### 13.2. Never simply add months to an Instant

For "1st of every month at 09:00", increment `YearMonth` or `LocalDate.plusMonths(...)` per policy, then resolve the new instant. Never add a fixed 30 days to an `Instant`: months have 28–31 days and DST can shift.

### 13.3. End-of-month schedules

A "31st of every month" schedule has no occurrence in February, April, June, September, or November. Policies may:
- skip months without a 31st;
- clamp to the last day of the month;
- reject at creation time.

This is a **business calendar policy** distinct from DST, yet equally important to specify and test.

## 14. Spring @Scheduled With Cron and Zone

Spring supports specifying a timezone on cron triggers:

```java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class VietnamMorningDigestTrigger {

    private final DigestJobCreator creator;

    public VietnamMorningDigestTrigger(
            DigestJobCreator creator) {
        this.creator = creator;
    }

    @Scheduled(
        cron = "0 0 9 * * MON-FRI",
        zone = "Asia/Ho_Chi_Minh"
    )
    public void createDailyDigest() {
        creator.createForCurrentBusinessDate();
    }
}
```

`DigestJobCreator` is an application-defined service responsible for checking the business date and **persisting an email occurrence/job with an idempotency key**—never sending real emails directly inside the cron method.

### 14.1. Enable scheduling

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
public class SchedulingConfiguration {}
```

Auto-configuration or another component may already enable scheduling; align with existing configuration to avoid duplicate triggers.

### 14.2. Spring cron typically uses six fields

Example:

```text
0 0 9 * * MON-FRI
| | | | | |
| | | | | +--- day of week
| | | | +----- month
| | | +------- day of month
| | +--------- hour
| +----------- minute
+------------- second
```

Never copy a five-field cron expression from another system without checking Spring's parser format.

### 14.3. zone applies to the **trigger**, not the server's timezone

`zone = "Asia/Ho_Chi_Minh"` evaluates the cron in that zone. It does not:
- change `ZoneId.systemDefault()`;
- change the database's timezone;
- change the recipient's timezone;
- guarantee emails are delivered on time;
- automatically persist schedules to the database.

### 14.4. Cron does not automatically catch up after downtime

If the service is down at cron fire time:
- never assume missed sends will magically run after restart;
- use a **catch-up scheduler** or recurrence materializer querying business dates missing occurrences;
- check expirations, quotas, and prevent sending all stale notices at once.

## 15. Never Create Unbounded Per-User Fixed Crons

A SaaS product may have 100,000 users, each picking a custom timezone and schedule. Never create one `@Scheduled` method or `TaskScheduler` bean **per user** without explicit lifecycle, persistence, and resource bounds.

A better model:

```text
recurring_mail_schedule (user-defined)
            |
            v
Materializer / periodic scheduler
            |
            | create occurrences for next interval
            v
mail_occurrence / scheduled_mail
            |
            v
Due-job dispatcher
            |
            v
JavaMailSender
```

A single scheduler with a few technical jobs can drive vast numbers of business schedules through the database.

### 15.1. How far ahead should occurrences materialize?

For example, materializing occurrences 7 days ahead:
- gives the due dispatcher enough lookahead;
- avoids creating millions of unnecessary future rows;
- makes recalculating future occurrences feasible when users change timezone/rules;
- still requires catch-up materialization after downtime.

Pick the horizon based on volume, timezone-rule stability, and operational needs. For marketing schedules edited frequently, materializing too far ahead wastes rows and complicates cancellation.

### 15.2. When timezone rules change

If tzdb updates, **not-yet-executed** occurrences of "09:00 local" may need their UTC instants recalculated. That differs from "send at fixed `Instant` X", which normally should not shift merely because tzdb updated.

Document clearly:
- whether the schedule is wall-clock or fixed-instant;
- whether future occurrences update;
- schedule versioning and auditing;
- rollout handling when multiple JVMs run different tzdb versions.

## 16. Due-Job Dispatcher: Compare Instants, Never Time Strings

Once schedules are resolved, workers only ask "is this timestamp due yet?":

```java
Instant now = clock.instant();

boolean due = !job.sendAt().isAfter(now);
```

Never compare:
- the string `"09:00"`;
- timezone-less `LocalDateTime.now()`;
- browser clock time;
- locale-formatted strings;
- text timestamps.

### 16.1. Polling query

```sql
SELECT message_key
FROM scheduled_mail
WHERE status IN ('PENDING', 'RETRY_WAIT')
  AND send_at <= :now
  AND next_attempt_at <= :now
ORDER BY next_attempt_at, send_at
LIMIT :batchSize;
```

In a production database with multiple workers, a standalone `SELECT` is not enough to stop two workers from grabbing the same job. Use atomic claiming or equivalent broker semantics.

### 16.2. Spring scheduler waking the due dispatcher

```java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class DueMailTick {

    private final ScheduledMailDispatcher dispatcher;

    public DueMailTick(
            ScheduledMailDispatcher dispatcher) {
        this.dispatcher = dispatcher;
    }

    @Scheduled(
        fixedDelayString =
            "${app.mail.dispatch.fixed-delay-ms:1000}"
    )
    public void dispatch() {
        dispatcher.dispatchDueBatch();
    }
}
```

`ScheduledMailDispatcher` is an application-defined service. `fixedDelay` here is not a business schedule timezone; it is only the technical pause between scan cycles.

### 16.3. Send-at means **do not send before**

Design the contract clearly:
- Jobs must not submit **before** `send_at`.
- Once due, workers attempt submission within a conditional SLA.
- SMTP acceptance may occur later due to queues or networks.
- Never guarantee provider delivery at the exact instant.

Make these semantics explicit in UI and API docs.

## 17. Atomic Claiming and Preventing Duplicates Across Instances

A PostgreSQL example:

```sql
WITH due AS (
    SELECT message_key
    FROM scheduled_mail
    WHERE status IN ('PENDING', 'RETRY_WAIT')
      AND send_at <= :now
      AND next_attempt_at <= :now
    ORDER BY next_attempt_at, send_at, created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE scheduled_mail s
SET status = 'SENDING',
    attempt_count = attempt_count + 1,
    lease_token = :leaseToken,
    lease_expires_at = :leaseExpiresAt,
    updated_at = :now
FROM due
WHERE s.message_key = due.message_key
RETURNING
    s.message_key, s.send_at, s.attempt_count,
    s.lease_token;
```

Claims should run inside a **short transaction** and commit before calling SMTP. Insert attempt history in the same claim transaction if your guarantees require it.

### 17.1. Never hold row locks across SMTP sends

`JavaMailSender.send(...)` can take seconds or time out. Holding a DB transaction across network calls can:
- hold locks;
- raise contention;
- exhaust thread/connection pools;
- roll back DB state after SMTP already received the email;
- cause duplicate retries.

Pattern:

```text
TX 1: claim + attempt (commit)
    |
    v
SMTP submission (no DB transaction)
    |
    v
TX 2: save outcome (commit)
```

### 17.2. Lease tokens and fencing

When persisting outcomes, update only if the worker still owns the lease:

```sql
UPDATE scheduled_mail
SET status = 'SMTP_ACCEPTED',
    lease_token = NULL,
    lease_expires_at = NULL,
    updated_at = :now
WHERE message_key = :messageKey
  AND status = 'SENDING'
  AND lease_token = :leaseToken;
```

If 0 rows updated, the worker likely lost ownership. Never silently overwrite a job already processed by another worker.

Fencing protects **database state** only. If SMTP already accepted the email, a database rollback or lease expiry **cannot recall** it.

## 18. Worker Sending Emails Once Due

A worker can use Spring's `JavaMailSender`:

```java
package com.example.mail.schedule;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public final class ScheduledMailSubmitter {

    private final JavaMailSender sender;

    public ScheduledMailSubmitter(JavaMailSender sender) {
        this.sender = sender;
    }

    public void submit(ScheduledMailContent content)
            throws MessagingException {

        MimeMessage mime = sender.createMimeMessage();

        MimeMessageHelper helper =
            new MimeMessageHelper(mime, true, "UTF-8");

        helper.setFrom(content.from());
        helper.setTo(content.recipient());
        helper.setSubject(content.subject());
        helper.setText(
            content.plainText(),
            content.htmlText()
        );

        mime.setHeader(
            "X-Application-Message-Key",
            content.messageKey()
        );

        sender.send(mime);
    }
}
```

`ScheduledMailContent` is an application-defined DTO holding the relevant fields, not a Spring API.

Timezone handling **does not live inside the SMTP adapter**: before reaching the adapter, the scheduler and due dispatcher already determined the job is eligible. The SMTP sender simply submits content.

### 18.1. Never block an HTTP request "waiting until send time"

Avoid:

```java
// Never do this in a request handler:
Thread.sleep(durationUntilSendAt);
mailSender.send(message);
```

Because it:
- ties up threads indefinitely;
- loses schedules on process restarts;
- lacks durable cancellation/rescheduling;
- breaks timezone/DST management;
- lacks backpressure;
- lacks reliable auditing/retries.

Persist jobs to the DB and let workers handle them later.

### 18.2. Do not build MimeMessages too early for long schedules

If an email is scheduled a month ahead, do not hold a mutable `MimeMessage` in memory for a month. Store template/content snapshots and attachment references with clear lifecycles, and compose MIME near submission time.

For verification emails with expiring tokens, decide when the token is generated. Generating a token at schedule creation when sending happens past token expiry yields a useless email.

## 19. Retries Must Still Obey Deadlines and Timezones

Suppose a user schedules a notice for 09:00:
- 09:00: worker tries sending; SMTP returns a temporary error.
- 09:05: retry.
- 09:15: retry again.
- 10:00: email is past its business validity window.

Distinguish:

- `send_at`: earliest time first submission is allowed.
- `next_attempt_at`: earliest time a retry is allowed.
- `expires_at`: time after which the email is no longer useful or permitted.

All execution timestamps should be `Instant`/`TIMESTAMPTZ`.

### 19.1. Retries do not change the original schedule intent

A retry at 09:05 does not turn `send_at` into 09:05. It is another attempt for the **same logical email**. Store attempt IDs and history to explain the gap between desired send time and actual SMTP submission.

### 19.2. Never retry every timeout blindly

If the connection drops after the SMTP relay may have accepted DATA, the outcome is `UNKNOWN`. Retrying at 09:05 can produce two emails—especially dangerous for payment confirmations, invoices, or appointment reminders.

You need:
- error classification;
- bounded retries with backoff for safe errors;
- reconciliation for `UNKNOWN`;
- dead-lettering or manual review for non-recoverable failures;
- business idempotency keys to avoid creating two logical emails.

## 20. Quiet Hours and Convenient Send Windows

Many products avoid sending marketing emails or non-urgent notices outside appropriate local hours:

```text
Allowed window (user zone):
09:00–20:00
```

If a job becomes due at 23:30 in the recipient's time, policy may defer it until 09:00 the next day. Distinguish:
- whether critical transactional emails may send overnight;
- what marketing consent/suppressions apply;
- whether windows follow tenant or recipient timezone;
- which regional holiday calendar applies;
- DST gap/overlap boundary behavior.

### 20.1. Evaluating quiet hours in the recipient's ZoneId

```java
import java.time.*;

Instant now = clock.instant();
ZoneId recipientZone =
    ZoneId.of("America/New_York");

LocalTime localNow =
    now.atZone(recipientZone).toLocalTime();

boolean insideWindow =
    !localNow.isBefore(LocalTime.of(9, 0))
    && localNow.isBefore(LocalTime.of(20, 0));
```

This example works only for a window **not crossing midnight**. Windows like 22:00–06:00 need different logic accounting for local dates and potential DST boundaries.

### 20.2. Recomputing the next-eligible instant

When deferring:
1. Convert current time to recipient local time.
2. Find the earliest valid local date/time.
3. Apply weekend/holiday/business policies.
4. Resolve via `ZoneRules` and gap/overlap policies.
5. Persist the next eligible `Instant`.
6. Never send before that new timestamp.

Never "add 8 hours" or "add one UTC day" assuming it lands on 09:00 local time.

### 20.3. Never infer quiet hours from country

Someone working night shifts may prefer different hours. If your product supports it, let users configure preferences and document defaults rather than hardcoding one rigid window per country.

## 21. Cancelling, Rescheduling, and Changing Timezones

An already-created job might be:
- cancelled before sending;
- moved to another date/time;
- switched to a different display timezone without changing the instant;
- changed to a different schedule timezone;
- updated with a new recurrence rule.

These actions are **all distinct**.

### 21.1. Changing display timezone

Suppose a job has:

```text
sendAt = 2026-12-01T02:00Z
```

User switches UI timezone from `Asia/Ho_Chi_Minh` to `Europe/Berlin`:
- UI displays 03:00 Berlin;
- `sendAt` stays 02:00Z;
- the email is not rescheduled.

### 21.2. Changing the schedule's wall-clock timezone

If the user wants "still send at 09:00, but in Berlin time instead of Vietnam time":
- keep local time 09:00;
- update `ZoneId` to `Europe/Berlin`;
- re-resolve the instant;
- increment schedule version;
- audit reason plus old and new timestamps.

This kind of timezone change **genuinely changes `sendAt`**.

### 21.3. Cancel vs. worker claim race

If a user cancels right as a worker claims:
- the cancellation transaction must check status/version;
- workers must re-check send permission before external side effects;
- once SMTP accepted, changing DB status cannot recall the email;
- the API must return an accurate outcome: "cancelled before sending" vs. "already sent/sending, cancellation cannot be guaranteed".

Never write `CANCELLED` if SMTP already accepted and display it as if the message never left.

## 22. Scheduling and Multiple SMTP Providers

A scheduled job may route to Provider A or B. Timezone resolution decides **when the job is eligible**, while provider routing decides **where to send it**.

```text
schedule(local + zone)
         |
         v
resolve/sendAt instant
         |
         v
due-job dispatcher
         |
         v
route by tenant + category + policy
         |
         +--> SMTP A
         |
         +--> SMTP B
```

Notes:
- providers enforce quotas/rate limits, so accepted time may lag `sendAt`;
- failing over to Provider B does not alter the intended timezone;
- successful SMTP AUTH does not prove SPF/DKIM/DMARC alignment;
- when A returns `UNKNOWN`, never automatically send through B just to "stay on time";
- Provider A may have accepted and still be retrying downstream delivery.

Separate scheduling SLAs from deliverability SLAs.

## 23. Clock Injection: Foundation of Deterministic Tests

Never scatter `Instant.now()` across controllers, repositories, and workers if you need to test near send times or retries. Inject `Clock`.

### 23.1. Production Clock bean

```java
import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ClockConfig {

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

Service:

```java
import java.time.Clock;
import java.time.Instant;

public class DuePredicate {

    private final Clock clock;

    public DuePredicate(Clock clock) {
        this.clock = clock;
    }

    public boolean isDue(Instant sendAt) {
        return !sendAt.isAfter(clock.instant());
    }
}
```

You do not need to change the system clock's timezone to test Berlin time; because `Instant` is always absolute, test the resolver and pass fixed instants.

### 23.2. Clock.fixed for due-time tests

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

class DuePredicateTest {

    @Test
    void jobIsNotDueBeforeItsInstant() {
        Clock clock = Clock.fixed(
            Instant.parse("2026-12-01T01:59:59Z"),
            ZoneOffset.UTC
        );

        DuePredicate predicate = new DuePredicate(clock);

        assertThat(predicate.isDue(
            Instant.parse("2026-12-01T02:00:00Z")
        )).isFalse();
    }

    @Test
    void jobIsDueExactlyAtSendAt() {
        Clock clock = Clock.fixed(
            Instant.parse("2026-12-01T02:00:00Z"),
            ZoneOffset.UTC
        );

        DuePredicate predicate = new DuePredicate(clock);

        assertThat(predicate.isDue(
            Instant.parse("2026-12-01T02:00:00Z")
        )).isTrue();
    }
}
```

These tests need no SMTP server, never wait in real time, and never depend on CI host timezones.

## 24. Testing Vietnam-to-UTC Conversion

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.*;
import org.junit.jupiter.api.Test;

class VietnamScheduleTest {

    private final MailScheduleTimeResolver resolver =
        new MailScheduleTimeResolver();

    @Test
    void nineAmVietnamIsTwoAmUtc() {
        Instant sendAt = resolver.resolve(
            LocalDateTime.of(2026, 12, 1, 9, 0),
            ZoneId.of("Asia/Ho_Chi_Minh"),
            GapPolicy.REJECT,
            OverlapPolicy.EARLIER_OFFSET
        );

        assertThat(sendAt).isEqualTo(
            Instant.parse("2026-12-01T02:00:00Z")
        );
    }
}
```

Tests must assert on **exact instant values**; never assert merely that a formatted string contains "09:00", as that does not verify conversion.

## 25. Testing DST Gaps and Overlaps

### 25.1. Rejecting nonexistent times

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Test
void rejectsNonexistentBerlinTime() {
    assertThatThrownBy(() -> resolver.resolve(
        LocalDateTime.of(2026, 3, 29, 2, 30),
        ZoneId.of("Europe/Berlin"),
        GapPolicy.REJECT,
        OverlapPolicy.EARLIER_OFFSET
    )).isInstanceOf(IllegalArgumentException.class);
}
```

### 25.2. Moving to the first valid time

```java
@Test
void gapCanMoveToFirstValidLocalTime() {
    Instant due = resolver.resolve(
        LocalDateTime.of(2026, 3, 29, 2, 30),
        ZoneId.of("Europe/Berlin"),
        GapPolicy.NEXT_VALID_TIME,
        OverlapPolicy.EARLIER_OFFSET
    );

    assertThat(due).isEqualTo(
        Instant.parse("2026-03-29T01:00:00Z")
    );
}
```

Note this timestamp represents **03:00 Berlin** after shifting to +02. If the product chooses `SHIFT_BY_GAP`, the result is 03:30 Berlin (`2026-03-29T01:30:00Z`). Both are valid when defined by business policy.

### 25.3. Picking the earlier or later occurrence

```java
@Test
void overlapHasTwoDistinctInstants() {
    LocalDateTime local =
        LocalDateTime.of(2026, 10, 25, 2, 30);

    ZoneId zone = ZoneId.of("Europe/Berlin");

    Instant first = resolver.resolve(
        local, zone,
        GapPolicy.REJECT,
        OverlapPolicy.EARLIER_OFFSET
    );

    Instant second = resolver.resolve(
        local, zone,
        GapPolicy.REJECT,
        OverlapPolicy.LATER_OFFSET
    );

    assertThat(first).isEqualTo(
        Instant.parse("2026-10-25T00:30:00Z")
    );

    assertThat(second).isEqualTo(
        Instant.parse("2026-10-25T01:30:00Z")
    );
}
```

The test protects the **occurrence selection rule**, preventing accidental double emails when a local time repeats.

## 26. Testing Recurring Schedules in Local Time

For `Europe/Berlin`:
- 2026-03-28 at 09:00 is 08:00 UTC (CET +01).
- 2026-03-29 at 09:00 is 07:00 UTC (CEST +02).

```java
@Test
void dailyNineAmKeepsWallTimeAcrossDst() {
    ZoneId berlin = ZoneId.of("Europe/Berlin");

    Instant beforeChange = resolver.resolve(
        LocalDateTime.of(2026, 3, 28, 9, 0),
        berlin,
        GapPolicy.REJECT,
        OverlapPolicy.EARLIER_OFFSET
    );

    Instant afterChange = resolver.resolve(
        LocalDateTime.of(2026, 3, 29, 9, 0),
        berlin,
        GapPolicy.REJECT,
        OverlapPolicy.EARLIER_OFFSET
    );

    assertThat(beforeChange).isEqualTo(
        Instant.parse("2026-03-28T08:00:00Z")
    );

    assertThat(afterChange).isEqualTo(
        Instant.parse("2026-03-29T07:00:00Z")
    );

    assertThat(
        Duration.between(beforeChange, afterChange)
    ).isEqualTo(Duration.ofHours(23));
}
```

**23 hours between two sends is still "every day at 09:00"** in a spring-forward DST zone. Similarly, at fall-back, the gap between two consecutive days can be 25 hours.

A test forcing every occurrence to be 24 hours apart fails the requirement for a **daily wall-clock schedule**.

## 27. Database Integration Tests: Timezones and Due Predicates

Resolver unit tests can pass while the database still misbehaves if:
- the driver translates `Instant` through an unintended JVM default zone;
- the schema uses `TIMESTAMP WITHOUT TIME ZONE` for absolute instants;
- queries compare local timestamps with `now()` in the wrong timezone;
- `next_attempt_at` is ignored;
- multiple workers claim the same job.

With PostgreSQL Testcontainers, verify:

1. Persist `send_at = 2026-12-01T02:00:00Z`.
2. Read it back through the repository as the exact same `Instant`.
3. Switch DB session timezone between UTC and `Asia/Ho_Chi_Minh`.
4. Confirm the stored instant does not change.
5. At T−1 second: not claimed.
6. At T: claimed cleanly once.
7. Two concurrent workers: never both claim.
8. After restart: future jobs remain intact.
9. After cancellation: never claimed.
10. When `SMTP_ACCEPTED`: never claimed again.

No real SMTP provider is needed to test timezone persistence and claim logic. Swap the sender for a mock/test gateway, and test SMTP separately in a sandbox.

### 27.1. Should test queries use Java Clock or DB clock?

Two designs exist:

- Application passes `clock.instant()` into queries, convenient for deterministic tests.
- Database uses `CURRENT_TIMESTAMP` as the claim clock.

Both work, provided you pick **one consistent time source** for due and lease checks. If using the DB clock, integration tests need relative fixture data or a deliberate test-clock strategy—avoid mixing app `now` and DB `now` unpredictably.

### 27.2. Clock skew between nodes

If Worker A runs 3 minutes fast relative to real time, it can send emails before `sendAt`. Proper NTP/PTP sync and clock-skew monitoring are infrastructure essentials.

For sensitive systems:
- use DB server time for claiming;
- configure time sync on all nodes;
- monitor drift;
- log `claimedAt`/`sentAt` for auditing.

## 28. Idempotency of Recurring Schedules and Multiple Replicas

A daily schedule can be evaluated concurrently by multiple scheduler instances.

This alone is insufficient:

```java
@Scheduled(cron = "0 0 9 * * *", zone = "Asia/Ho_Chi_Minh")
public void sendDigest() {
    mailSender.send(...);
}
```

With three pods, the method can run on all three, creating three submissions.

### 28.1. Generating jobs with a unique business key

```text
tenantId + scheduleId + occurrenceLocalDate + slot
```

Example:

```text
tenant-9|digest-weekdays|2026-12-01|single
```

A DB unique constraint guarantees the same occurrence is created once per policy. Then the due dispatcher claims jobs atomically so only one worker attempts each.

### 28.2. Idempotency does not mean SMTP deduplicates automatically

Repeating `messageKey` in a custom header does not force SMTP to drop duplicate emails. Database idempotency prevents duplicate **job creation/claims**; `UNKNOWN` network errors after SMTP DATA still need reconciliation.

### 28.3. Catching up after downtime

If the scheduler was off for three days:
- compute missing occurrences from the recurrence rule and local date range;
- apply the catch-up policy;
- insert only occurrences still valid;
- do not send 3 days of stale reports if no longer useful;
- use unique keys so catch-up can rerun safely.

A cron tick is not a durable event log; applications must design recovery explicitly.

## 29. tzdb Updates: Why Does ZoneId Matter Long-Term?

DST and timezone laws can change by government decree. Java uses tzdb to convert between local time and instants.

If a recurring schedule is stored months ahead:
- tzdb may update;
- the UTC instant of a future occurrence may shift;
- `ZoneId` still expresses "09:00 local time";
- a static offset saved at creation cannot reflect new rules.

### 29.1. Distinguishing two time contracts

**Contract A: Absolute instant**
> Send at 2027-01-01T02:00:00Z.

When tzdb updates, generally **do not recalculate** a fixed instant.

**Contract B: Local wall-clock time**
> Send at 09:00 daily in the region's official local time.

When regional rules change, future occurrences must use the new rules. If already materialized far ahead, you may need to **recalculate** unaccepted/pending jobs.

### 29.2. Multi-region running different tzdb versions

If Pod A runs a JDK with an older tzdb and Pod B runs a newer tzdb, the same future local time can resolve to two different instants.

Mitigations:
- align JDK/tzdb versions across rollouts;
- record schedule version or resolved-at metadata;
- centralize materialization in one canonical service;
- audit rule changes;
- test critical timezones after runtime upgrades.

Never rely on `ZoneId.of` assuming every pod at every point runs identical rules.

## 30. Common Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Email sent 7 hours off | `LocalDateTime` treated as UTC | Resolve using user's `ZoneId` before storing `Instant` |
| Berlin schedule shifts 1 hour in summer | Stored `+01:00` only | Store `Europe/Berlin` and compute occurrences per local date |
| Double send on DST fall-back day | Cron/logic lacks overlap policy | Pick EARLIER/LATER or unique occurrence key |
| Email dropped because 02:30 didn't exist | Missing gap policy | Explicit REJECT/SKIP/SHIFT |
| Changing UI timezone moves send time | UI treats local string as source of truth | Keep `Instant` when only display changes |
| Daily schedule stays 24h apart but drifts local hour | Added `Duration(24h)` to wall-clock schedule | Derive from local date + `ZoneId` |
| Cron sends multiple copies | Multiple pods running `@Scheduled` | Durable jobs + unique keys/distributed owner |
| Missed run after deploy | Cron does not auto-catch-up skipped ticks | Catch-up materialization |
| Jobs lost on restart | Used only timers or memory queues | Durable outbox/database |
| Sent before target time | Fast app clock or missing due predicate | Clock sync, authoritative clock, SQL predicate |
| Retries send expired links | Missing `expiresAt` | Deadline/expiration policy |
| SMTP accepted late despite accurate `sendAt` | Provider/network/backlog | Separate scheduled vs. accepted; monitor lag |
| Cancelled schedule still sends | Race with worker claim | Conditional updates, version/lease, re-checks |
| DB UTC differs from UI | Database session timezone altered display | Store `Instant` and `ZoneId` separately; format in UI |
| Invalid timezone silently falls back to UTC | Sloppy error handling | Return validation error |
| User picks 09:00 while traveling | Inferred timezone from browser | Display and confirm `ZoneId` |
| Same daily digest creates two jobs | Missing occurrence idempotency | `Unique(schedule, date, slot)` |
| Provider A timed out then tried B | Did not preserve `UNKNOWN` | Reconcile instead of blind retry |
| Log timestamps hard to correlate | Formatted locally without offset/zone | Structured UTC timestamps plus schedule zone metadata |
| Future schedules shift after JDK upgrade | tzdb rules changed | Manage tzdb/versions and future occurrence recalculation |

## 31. Checklist for Designing Multi-Timezone Send Schedules

### 31.1. Input and intent

- [ ] UI/API specifies timezone explicitly, preferring IANA `ZoneId`.
- [ ] Fixed-instant schedules are distinguished from local wall-clock schedules.
- [ ] Local input, zone ID, and gap/overlap policies are persisted where needed.
- [ ] Zone is never guessed from server, email address, or locale.
- [ ] Horizon bounds, recipient permissions, and consent are validated.
- [ ] Policies exist for DST nonexistent and repeated times.
- [ ] Quiet-hours/holiday rules exist where required by business logic.

### 31.2. Persistence and dispatch

- [ ] `send_at` and `next_attempt_at` are stored as absolute instants.
- [ ] `ZoneId` is stored in its own column.
- [ ] Bare local timestamps are never used as due predicates.
- [ ] Unique business/occurrence idempotency keys exist.
- [ ] Atomic claims with leases/fencing exist for multiple workers.
- [ ] SMTP calls never hold long DB transactions.
- [ ] Deadlines, cancel/reschedule, and audit history are supported.
- [ ] Retry/`UNKNOWN`/dead-letter states are clearly defined.

### 31.3. Recurrence and cron

- [ ] Each occurrence is calculated from local date/time in `ZoneId`.
- [ ] Never add 24h UTC for "same time every day" schedules.
- [ ] Cron specifies `zone` explicitly.
- [ ] Never spawn unbounded scheduler beans per user.
- [ ] Catch-up policy exists for downtime.
- [ ] Prevent multiple pods from generating the same occurrence.
- [ ] Overlap behavior is explicit: once or twice.
- [ ] Process exists for tzdb upgrades and materialized future jobs.

### 31.4. Testing and operations

- [ ] Inject `Clock` and use fixed/mutable clocks in tests.
- [ ] Test Vietnam UTC+07 and at least one DST-observing timezone.
- [ ] Test gaps, overlaps, and dates around DST transitions.
- [ ] Test persisted `Instant` across differing DB session timezones.
- [ ] Test due boundary T−1s/T and no early sends.
- [ ] Test restarts, catch-up, and concurrency.
- [ ] Test cancel/reschedule races, expiration, and retries.
- [ ] Monitor schedule lag, SMTP submit time, and delivery events.
- [ ] Never conclude delivered solely from `JavaMailSender.send(...)`.

## 32. Practical Exercises

### Exercise 1 — One-shot send in Vietnam

Given `localSendTime=2026-12-01T09:00` and `zone=Asia/Ho_Chi_Minh`, compute `Instant`, store it in the DB, and render it back in the original `ZoneId`.

### Exercise 2 — Two timezones on the same day

Two users both pick 09:00 on 2026-12-01, one in Berlin and one in Vietnam. Determine the two distinct UTC `sendAt` values and explain why storing only `LocalDateTime` fails.

### Exercise 3 — Offset vs. ZoneId

Compare `ZoneOffset.ofHours(1)` and `ZoneId.of("Europe/Berlin")` for a recurring schedule on 2026-03-28 and 2026-03-29. Show how a fixed offset drifts local time after DST.

### Exercise 4 — DST gap

Request sending at 02:30 Berlin on 2026-03-29. Test `REJECT`, `NEXT_VALID_TIME`, and `SHIFT_BY_GAP` and list the expected instants.

### Exercise 5 — DST overlap

Request sending at 02:30 Berlin on 2026-10-25. Produce both valid instants, select one via `EARLIER_OFFSET`/`LATER_OFFSET`, and test avoiding accidental double sends.

### Exercise 6 — Clock.fixed

Write `DuePredicate` with an injected `Clock`. Test T−1s not due, T exactly due, and T+1s still due.

### Exercise 7 — Daily 09:00 schedule

Generate occurrences for one week spanning DST in Berlin. Assert local time is always 09:00 while UTC spacing between consecutive days can be 23 or 25 hours.

### Exercise 8 — Every 24 hours schedule

Build a contrasting schedule: "every 24 hours from the initial `Instant`". Compare results against daily wall-clock time and identify which requirement calls for each.

### Exercise 9 — PostgreSQL TIMESTAMPTZ

Persist an `Instant` to `TIMESTAMPTZ`, then read it back under DB session timezones UTC and `Asia/Ho_Chi_Minh`. Confirm the instant stays identical while formatted strings may differ.

### Exercise 10 — Cancelling a one-shot send

Create a `PENDING` job, cancel before `sendAt`, then run the due dispatcher. Confirm `CANCELLED` cannot be claimed. Also test concurrent worker claiming and specify what the API returns.

### Exercise 11 — Multi-replica daily digest

Use `@Scheduled(cron, zone)` to create jobs by business date. Run two instances and use unique `(tenant, schedule, localDate, slot)` to ensure only one occurrence is created.

### Exercise 12 — Catch-up after downtime

The app was down for 3 days. Design a catch-up policy for weekly reports, skipping expired notices and preventing duplicate jobs if catch-up runs twice.

### Exercise 13 — Quiet hours

A user in New York wants notifications only between 09:00 and 20:00. A job becomes due at 23:30 local. Compute the next eligible local time and resolve via `ZoneId`; test on a DST day too.

### Exercise 14 — Token deadlines

A verification email embeds a token expiring 15 minutes after creation. A user schedules sending an hour later. Design validation or late token generation near submission so the email never ships an expired token.

### Exercise 15 — Multi-tenant timezones

Tenant A uses `Asia/Tokyo`, Tenant B uses `America/New_York`. Write a resolver selecting `ZoneId` from authenticated configuration without letting clients pick another tenant's zone.

### Exercise 16 — Retries and UNKNOWN

Simulate an SMTP timeout after DATA at the scheduled send time. Verify the job moves to `UNKNOWN`, does not auto-failover/resend, and preserves the original `sendAt` for auditing.

### Exercise 17 — tzdb updates

A country changes DST rules while the system already materialized recurring jobs three months out. Design a process identifying which jobs must recalculate, which keep their `Instant`, and how audits/versions are recorded.

### Exercise 18 — Observing send schedules

Design metrics for `dueAt → claimedAt → smtpAcceptedAt → deliveredAt`, separating scheduler lag from provider delivery lag. Propose an alert when due jobs go unclaimed beyond SLA.

## 33. Summary

**The timezone of a send schedule** is part of the **business contract**, not just a display formatting detail. In Spring Framework Mail, `JavaMailSender` performs submission, while the application must determine send timing according to user intent before SMTP is ever called.

Principles to remember:

1. **Store `Instant` for a concrete send**, and store `ZoneId`/local time when needed to explain or continue a local-time schedule.
2. **`LocalDateTime` has no timezone**; never implicitly assume UTC or the server's timezone.
3. **IANA `ZoneId` differs from a fixed offset**: DST rules and legal changes can make future offsets differ from today's.
4. **DST gaps/overlaps need explicit policies**: reject, skip occurrence, move to valid time, or pick one of the two occurrences.
5. **Wall-clock recurring schedules** must compute each occurrence from local date/time + `ZoneId`; never simply add 24 hours to a UTC instant.
6. **`@Scheduled(cron, zone)` is a trigger**, not a substitute for durable scheduling, catch-up, and idempotency across multiple replicas.
7. **Persist jobs in an outbox**, claim atomically via `send_at <= now`, and submit only when eligible—never use `sleep` or in-memory timers for critical long-term schedules.
8. **Distinguish `sendAt`, `nextAttemptAt`, and `expiresAt`** so retries never fire early or past deadlines.
9. **Never confuse scheduling with delivery**: SMTP acceptance can trail `sendAt` and does not prove Inbox placement.
10. **Test with `Clock` and DST-observing timezones**, verifying databases, restarts, concurrency, cancellations, and tzdb updates.

By explicitly separating **local time intent**, **UTC execution instants**, and **actual SMTP submission state**, a Spring application can send accurately on schedule across countries, avoid DST drift, and recover reliably after failures.
