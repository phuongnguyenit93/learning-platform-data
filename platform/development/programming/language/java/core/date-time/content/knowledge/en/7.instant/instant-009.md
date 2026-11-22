# Using Instant for Logging, Creation Timestamps, and Expiration

In Java, `Instant` represents **an absolute point in time on the timeline**, unattached to a country's display time or a server's time zone. It is typically the right choice for recording **when an event occurred** (`occurredAt`), **when an object was created** (`createdAt`), and **when data or access expires** (`expiresAt`).

For example, a login session created at `2024-06-01T12:00:00Z` with a 30-minute lifetime:

~~~text
createdAt = 2024-06-01T12:00:00Z
expiresAt = 2024-06-01T12:30:00Z

12:29:59.999999999Z -> valid
12:30:00Z           -> expired
12:30:00.000000001Z -> expired
~~~

Both values point to a definite instant and can be compared directly without guessing "is 12:30 Vietnam time or New York time?". However, `Instant` only solves **representing a point in time**; clock accuracy, expiration policies, and cross-machine consistency still need to be designed separately.

## 1. Why is Instant suitable for event timestamps?

The types in `java.time` serve different purposes:

| Type | Meaning | Suitable for |
|---|---|---|
| `Instant` | A point on the UTC/Java Time-Scale timeline, consisting of seconds and nanoseconds. | `createdAt`, `updatedAt`, `occurredAt`, `expiresAt`, audit timestamps. |
| `LocalDateTime` | Date and time on a calendar, **without a time zone or offset**. | Representing local time when regional context is stored separately. |
| `ZonedDateTime` | Date-time with a `ZoneId` and a resolved offset. | Scheduled appointments at 09:00 in a region, displaying time according to regional rules. |
| `OffsetDateTime` | Date-time with a fixed UTC offset. | Data with an explicit offset in APIs or records. |
| `Duration` | Exact length of time in seconds/nanoseconds. | 15-minute TTL, 30-second timeout, elapsed time between two `Instant`s. |
| `Clock` | Time source for the program. | Reading current time consistently, unit tests independent of real wall-clock time. |

For example, the same event:

~~~text
Original Instant:              2024-06-01T12:00:00Z
Displayed in Asia/Ho_Chi_Minh: 2024-06-01T19:00+07:00[Asia/Ho_Chi_Minh]
Displayed in America/New_York: 2024-06-01T08:00-04:00[America/New_York]
~~~

These are **three representations of the exact same point in time**. `Instant` does not lose the actual time when a user changes time zones; changing the zone only changes how it is presented.

Java provides:

~~~java
Instant now = Instant.now();
Instant nowFromClock = Instant.now(clock);
Instant parsed = Instant.parse("2024-06-01T12:00:00Z");
~~~

This is **illustrative code** that requires `import java.time.Instant;`, a valid `Clock clock` variable, and placement inside a method/class. In production, you should generally **inject `Clock` into business components** so unit tests can control the outcome.

`Instant.now()` reflects the system clock at the time of reading; it **does not promise absolute nanosecond accuracy** and does not guarantee monotonic progression across reads. The data type supports nanosecond precision, but the resolution and drift of the clock source are a separate matter.

## 2. Logging: recording when an event occurred properly

Suppose the system receives an order. There may be several distinct timestamps to tell apart:

- `occurredAt`: when the event actually occurred according to the event producer.
- `recordedAt` or `receivedAt`: when the current system recorded/received the event.
- `processedAt`: when the processing task completed.
- `createdAt` on the order entity: when the entity was created according to system convention.

These timestamps **do not have to match**. Events can pass through queues, experience network delays, retries, or replays. Do not arbitrarily overwrite `occurredAt` with the latest receipt time and lose its original meaning.

A structured application log might contain:

~~~json
{
  "eventType": "ORDER_CREATED",
  "eventId": "evt-1001",
  "occurredAt": "2024-06-01T11:59:58.125Z",
  "recordedAt": "2024-06-01T12:00:00Z",
  "orderId": "order-42"
}
~~~

Each field has its own value:

- `eventId` identifies the event for reconciliation and idempotency.
- `orderId` points to the related entity.
- `occurredAt` and `recordedAt` preserve both points in time with their respective meanings.
- Do not use `Instant` as a **unique ID**: two events can share the same timestamp, especially when the clock has limited effective resolution.
- Do not assume sorting timestamps from **multiple machines** gives the exact causal order; clock skew and network transport can reverse the order.

### Standalone Java example: two timestamps of one event

File `AuditEventDemo.java`:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

public class AuditEventDemo {
    record AuditEvent(String type, Instant occurredAt, Instant recordedAt) {}

    public static void main(String[] args) {
        Instant occurred = Instant.parse("2024-06-01T11:59:58.125Z");
        Clock clock = Clock.fixed(
                Instant.parse("2024-06-01T12:00:00Z"),
                ZoneOffset.UTC);

        AuditEvent event = new AuditEvent(
                "ORDER_CREATED", occurred, Instant.now(clock));

        System.out.println("Type: " + event.type());
        System.out.println("Occurred: " + event.occurredAt());
        System.out.println("Recorded: " + event.recordedAt());
        System.out.println("Difference ms: "
                + Duration.between(
                        event.occurredAt(), event.recordedAt()).toMillis());
        System.out.println("ISO round-trip: "
                + Instant.parse(event.occurredAt().toString())
                        .equals(event.occurredAt()));
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac AuditEventDemo.java
java AuditEventDemo
~~~

Stdout:

~~~text
Type: ORDER_CREATED
Occurred: 2024-06-01T11:59:58.125Z
Recorded: 2024-06-01T12:00:00Z
Difference ms: 1875
ISO round-trip: true
~~~

`Clock.fixed` makes the output deterministic in the example; it does **not** mean real clocks have absolute accuracy. The difference between two timestamps in real data can also include error from inter-machine offset or the event's time source.

### Distributed logs and event ordering

Timestamps are useful for querying and stitching timelines together, but they are not enough to determine every relationship:

- Two events can share the same `Instant` or be recorded from machines with skewed clocks.
- An event sent earlier may arrive later due to queuing or retries.
- For systems requiring strict ordering, add a `sequenceNumber`, broker log offset, version/transaction order, or appropriate causal metadata.
- Keep a trace ID/correlation ID to link processing steps; do not rely solely on time as a join key.
- When using logs for investigation, use a consistent display time zone/unit and ensure server clocks are synchronized, monitoring offset and drift.

## 3. createdAt: when is a creation timestamp assigned?

`createdAt` should usually represent the **initial creation instant**, remaining unchanged on subsequent updates or reloads of the object. For application-managed entities, a common convention is:

1. Choose the system or database clock source and standardize its meaning.
2. Capture the timestamp **once** in the creation flow.
3. Assign `createdAt` and persist it with the data.
4. On subsequent edits, keep `createdAt` unchanged and only update `updatedAt` if needed.

Illustrative code example:

~~~java
Instant createdAt = clock.instant();
Order order = new Order(orderId, createdAt);
repository.save(order);
~~~

This snippet is **not standalone**; it assumes `clock`, `Order`, `orderId`, and `repository` are already defined. The key point is that the timestamp is determined once before saving; do not call `Instant.now()` repeatedly for fields meant to represent the same instant.

### Choosing the time source and defining "created"

Be explicit about "when it was created":

- **When request processing starts:** captured by the application upon receiving the request.
- **When the entity is instantiated in the application:** captured by the service layer.
- **When the row is written or the transaction commits:** determined by database/transaction logic depending on what is supported.

These three moments can differ. An `Instant.now()` taken right before `save` **does not prove** the transaction committed at that exact instant. In systems with multiple writers, standardize on an authoritative source and conversion rules to avoid clock skew between the application and database data.

For retry/idempotent operations, if a creation request already succeeded earlier, the retry should **return the existing record and its original `createdAt`** rather than generating a new timestamp. For updates, consider adding a `version` for concurrency control; a timestamp alone does not prevent lost updates.

### Differences between createdAt and updatedAt

| Field | When is it set? | Does it change on update? |
|---|---|---|
| `createdAt` | Once upon creation per business definition. | Normally **no**. |
| `updatedAt` | When a tracked change occurs. | Yes; following a consistent rule. |
| `deletedAt` | When a soft delete is performed (if applicable). | When deletion state changes; not necessarily physical deletion time. |
| `publishedAt` | When the entity is actually published. | Per business logic; may differ from `createdAt`. |

Do not derive all of the above fields from the same `now` if they represent **different stages**. If two fields are intentionally set to the same instant in a single action, **capture the clock once** to ensure they match exactly.

## 4. expiresAt: expiration timestamp and boundary rules

A common TTL (*time to live*) policy:

~~~java
Instant issuedAt = clock.instant();
Instant expiresAt = issuedAt.plus(Duration.ofMinutes(30));
~~~

This is an illustrative snippet assuming `Clock clock` is provided. Under the rule "valid from creation, expired right at `expiresAt`", the validity window is typically defined as a **half-open** interval:

~~~text
[createdAt, expiresAt)

activeAt(now)  = !now.isBefore(createdAt) && now.isBefore(expiresAt)
expiredAt(now) = !now.isBefore(expiresAt)
~~~

This means **at `expiresAt` itself, the object is already expired**. Do not use `now.isAfter(expiresAt)` as the sole check, because it treats a timestamp **equal** to `expiresAt` as still valid.

If business logic does not care about times prior to issuance, checking `now.isBefore(expiresAt)` suffices. If the full validity window is required, check `createdAt` as well.

### Why choose Duration for TTL calculations?

`Duration.ofMinutes(30)` or `Duration.ofHours(24)` represents **elapsed duration**, suitable for temporary sessions, verification links, and operation timeouts.

By contrast, "expires at the **end of the local day**" is a calendar rule that requires `LocalDate` + `ZoneId` to find the exact day boundary. Across DST transitions, a calendar day can be 23 or 25 hours long. Do not assume "expires at the end of tomorrow" is equivalent to "`now` plus 48 hours".

Example of expiring at the **start of the next day**, as an exclusive bound:

~~~java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate businessDate = LocalDate.of(2024, 6, 1);
Instant expiresAt = businessDate.plusDays(1)
        .atStartOfDay(zone)
        .toInstant();
~~~

This is an illustrative snippet; inside a method it requires importing `java.time.*`. It sets expiration at the start of `2024-06-02` on the Vietnam calendar. To expire "30 minutes after creation", use `Duration`, not calendar arithmetic.

## 5. Java 17+ example: issuing and checking a session with TTL

The file `ExpiryPolicyDemo.java` is a standalone program independent of the real clock. It uses `Clock.fixed` and `Clock.offset` to test before, at, and after expiration.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

public class ExpiryPolicyDemo {
    record Session(String id, Instant createdAt, Instant expiresAt) {
        boolean isActiveAt(Instant now) {
            return !now.isBefore(createdAt) && now.isBefore(expiresAt);
        }

        boolean isExpiredAt(Instant now) {
            return !now.isBefore(expiresAt);
        }
    }

    static Session issue(String id, Clock clock, Duration ttl) {
        if (ttl.isNegative() || ttl.isZero()) {
            throw new IllegalArgumentException("TTL must be positive");
        }

        Instant created = clock.instant();
        Instant expiry = created.plus(ttl);
        return new Session(id, created, expiry);
    }

    public static void main(String[] args) {
        Clock origin = Clock.fixed(
                Instant.parse("2024-06-01T12:00:00Z"),
                ZoneOffset.UTC);

        Session session = issue("session-1", origin,
                Duration.ofMinutes(30));

        Instant before = Clock.offset(origin,
                Duration.ofMinutes(29)).instant();
        Instant at = Clock.offset(origin,
                Duration.ofMinutes(30)).instant();
        Instant after = Clock.offset(origin,
                Duration.ofMinutes(31)).instant();

        System.out.println("Created: " + session.createdAt());
        System.out.println("Expires: " + session.expiresAt());
        System.out.println("Active before: " + session.isActiveAt(before));
        System.out.println("Active at: " + session.isActiveAt(at));
        System.out.println("Expired at: " + session.isExpiredAt(at));
        System.out.println("Expired after: " + session.isExpiredAt(after));
    }
}
~~~

Compile and run:

~~~bash
javac ExpiryPolicyDemo.java
java ExpiryPolicyDemo
~~~

Deterministic stdout:

~~~text
Created: 2024-06-01T12:00:00Z
Expires: 2024-06-01T12:30:00Z
Active before: true
Active at: false
Expired at: true
Expired after: true
~~~

**Explanation:**

- `issue` validates that TTL is positive to prevent creating an immediately expired or backward-in-time session if a caller passes an invalid value.
- `clock.instant()` is called **once** to create `createdAt`, from which `expiresAt` is computed using TTL.
- `isActiveAt` checks whether `now` falls within `[createdAt, expiresAt)`.
- At the exact instant equal to `expiresAt`, `now.isBefore(expiresAt)` is `false`, so it is expired.
- `Clock.offset` is used for unit testing. No `Thread.sleep` is needed, keeping tests fast and reliable.
- If TTL is so large that `created.plus(ttl)` overflows `Instant`'s range, Java can throw an exception; production code should enforce policy bounds on TTL before adding.

## 6. Real clocks can skew or jump: Instant does not fix this automatically

An `Instant` value has an absolute meaning, but the **source generating the timestamp** is not necessarily accurate. `Instant.now()` depends on the environment's *wall clock*; the system clock can be stepped forward/backward manually or via time synchronization.

Suppose there are two machines:

~~~text
Machine A: clock fast +300 ms
Machine B: clock slow -200 ms

Two real events 100 ms apart may have
displayed timestamps in reversed order when generated on two machines.
~~~

Causal order cannot be concluded from timestamps alone without controlling clock error. For security expirations, if the verifying machine runs slow, it may treat a token as valid longer than intended relative to a reference clock. If it runs fast, the token may be rejected prematurely.

Practical measures:

- Synchronize and monitor server clock offset/drift; do not assume "many fractional digits" means the clock is accurate.
- Define an **authoritative time source** for issuance/verification, especially when a system spans multiple services or databases.
- Do not trust `createdAt` or `expiresAt` **self-reported by the client** in workflows requiring server-side control.
- If a token/protocol standard allows a clock skew (*leeway*), apply it deliberately with tight bounds; leeway shifts the effective acceptance boundary and cannot replace clock synchronization.
- For tokens that can be revoked early, `expiresAt` is only a **time bound**, not a replacement for revocation/logout/authorization checks.

### Instant and System.nanoTime() have two different jobs

`Instant.now()` produces a wall-clock point in time suitable for **logging or storing createdAt**. `System.nanoTime()` has an arbitrary origin and is suited for measuring **elapsed intervals** within a process, such as benchmarks or execution duration. `nanoTime()` values cannot be stored directly in a database as an epoch timestamp.

To enforce session limits that must **persist** across restarts, store an `Instant` or an epoch with an explicit unit. For short internal timeouts where elapsed duration must not be affected by wall-clock adjustments, use `System.nanoTime()` differences as appropriate.

Do not mix epoch millis and `nanoTime()` in the same formula because they **do not share a common origin**.

## 7. Database storage and API serialization

### 7.1. Standardizing timestamps

In JSON, represent instants in ISO-8601 with `Z` or an explicit offset:

~~~json
{
  "id": "session-1",
  "createdAt": "2024-06-01T12:00:00Z",
  "expiresAt": "2024-06-01T12:30:00Z"
}
~~~

`Z` indicates UTC. The string `2024-06-01T12:00:00` **has no offset**, so it cannot be assumed to be an absolute point in time.

In Java:

~~~java
Instant createdAt = Instant.parse("2024-06-01T12:00:00Z");
String iso = createdAt.toString();
~~~

This is illustrative code requiring `import java.time.Instant` inside a method. For timestamps with nanoseconds, `Instant` retains the fractional part, but **DB column types, drivers, serialization, and formatters** may round or truncate it. Test round-trip behavior with nanosecond values to verify storage resolution.

### 7.2. Epoch seconds vs. epoch milliseconds

If an API uses integers, name them clearly:

~~~text
epochSecond: number of seconds since 1970-01-01T00:00:00Z
epochMillis: number of milliseconds since that epoch

epochMillis ≈ epochSecond * 1000
(if there is no fractional part; also consider long limits)
~~~

For sub-second precision, `Instant.getEpochSecond()` and `Instant.getNano()` split into whole seconds and nanoseconds; `Instant.toEpochMilli()` returns milliseconds and discards sub-millisecond precision. Do not use `System.nanoTime()` as a substitute for epoch nanoseconds.

For example, `2024-06-01T12:00:00.123456789Z` stored as milliseconds cannot accurately recover the trailing `456789` nanoseconds.

### 7.3. Schema and query boundaries

A schema for auditing/expiration might look like this (**illustrative SQL; exact column types depend on the DBMS**):

~~~sql
CREATE TABLE sessions (
    id          VARCHAR(100) PRIMARY KEY,
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at  TIMESTAMP WITH TIME ZONE NOT NULL
);
~~~

Not every database uses the same type names or resolution definitions. Check the driver, session time zone, mapper, and UTC storage conventions explicitly. In particular, do not confuse a timezone-less timestamp type with a well-defined `Instant`.

A validity query following the `now < expiresAt` policy:

~~~sql
SELECT *
FROM sessions
WHERE id = :sessionId
  AND created_at <= :nowInstant
  AND expires_at > :nowInstant;
~~~

This is **illustrative SQL** using bound parameters and compatible DB types. The conditions verify that the session has started and has not yet expired. Pass `nowInstant` from the **same agreed time source** for the entire check; if the DB uses its own time function, the rule must align with how `expiresAt` is created.

For querying logs within a range, use half-open boundaries:

~~~sql
SELECT *
FROM audit_events
WHERE occurred_at >= :fromInstant
  AND occurred_at <  :untilInstant
ORDER BY occurred_at, event_id;
~~~

The `[from, until)` interval avoids duplicate records at window edges when stitching windows together. `event_id` in `ORDER BY` is only a tie-breaker for deterministic ordering; **it does not prove causal order across machines**.

### 7.4. Logical expiration vs. physical deletion

A record past `expiresAt` must be treated as expired **at check time**, even if a scheduled cleanup job has not deleted it yet. Database TTL indexes/jobs may delete records **asynchronously** and do not guarantee a record disappears at the exact nanosecond of `expiresAt`. Therefore:

- Enforce the time condition on the protected processing path.
- Treat deletion jobs as cleanup/retention mechanisms, not as a substitute for validity checks.
- When updating or confirming critical state, apply the expiration condition inside an appropriate transactional operation to reduce races between "checking validity" and "performing the action".

For example, a read-then-update across two concurrent requests can encounter a state change between steps; reading `expiresAt` once and assuming it **will** remain valid throughout a long operation is a dangerous assumption.

## 8. Avoiding common mistakes when designing expiration

| Mistake | Problem | How to avoid |
|---|---|---|
| Calling `LocalDateTime.now()` and storing it as if it were UTC. | Value lacks an offset and depends on the environment's time zone. | Store `Instant.now(clock)` when an absolute timestamp is needed. |
| Overwriting `createdAt` on every update. | Loses the original creation time and corrupts audit trails. | Set only at creation; use a separate `updatedAt`. |
| `expiresAt = createdAt.plus(1, DAYS)` when business means "end of day in zone". | A 24-hour TTL differs from calendar day boundaries that may cross DST. | Compute start of next day using `LocalDate` and `ZoneId`. |
| Treating `now.isAfter(expiresAt)` as the complete expiration check. | An instant equal to `expiresAt` is not treated as expired. | Use `!now.isBefore(expiresAt)`. |
| Calling `Instant.now()` multiple times for fields of the same event. | Introduces unnecessary skew within a single action. | Capture the clock once and reuse it. |
| Trusting client-supplied `expiresAt`. | Clients can extend their own lifetime. | Compute TTL and validate state on the server. |
| Assuming log timestamps always establish causal order. | Clocks can skew and events can be delayed/retried. | Use IDs, sequence/transaction order, or trace metadata. |
| Sending epoch seconds when the API expects millis. | Timestamps are severely misinterpreted. | Define units explicitly in names/contracts. |
| Assuming storing `Instant` always preserves full nanoseconds in every DB. | Schemas/drivers may truncate resolution. | Test round-trip persistence and column precision. |
| Assuming a record is valid as long as cleanup hasn't deleted it. | Cleanup can lag behind logical expiration. | Check `expiresAt` on the processing path. |
| Using `Thread.sleep` in unit tests to wait for expiration. | Tests become slow and flaky. | Inject `Clock.fixed` and `Clock.offset`. |

## 9. Unit testing: verifying boundaries and time semantics

You should cover these test groups:

1. **Creation:** `createdAt` is captured once, `expiresAt = createdAt + TTL`, and empty/negative/invalid TTLs are rejected per policy.
2. **Boundaries:** invalid before `createdAt`; valid right at `createdAt`; valid before `expiresAt`; **expired right at `expiresAt`**.
3. **Creation immutability:** updating an entity does not alter `createdAt`, only `updatedAt` per rules.
4. **Serialization:** parsing ISO-8601 `Z` and JSON round-trips preserve the same `Instant`; test seconds/milliseconds, nanoseconds, pre-1970 timestamps, and column type limits.
5. **Time source:** application uses an injected `Clock`, tests run deterministically, independent of default time zone and without waiting for real time.
6. **Distributed behavior:** simulate clock skew, late-arriving events, idempotent retries, and races at the expiration boundary.
7. **Display:** converting the same instant to multiple `ZoneId`s yields different local times without changing the underlying point in time.

### Runnable Java example: testing the exact last nanosecond

File `ExpiryBoundaryDemo.java`:

~~~java
import java.time.Instant;

public class ExpiryBoundaryDemo {
    static boolean active(Instant createdAt, Instant expiresAt,
                          Instant now) {
        return !now.isBefore(createdAt) && now.isBefore(expiresAt);
    }

    public static void main(String[] args) {
        Instant created = Instant.parse("2024-06-01T12:00:00Z");
        Instant expires = Instant.parse("2024-06-01T12:30:00Z");

        Instant justBefore = expires.minusNanos(1);

        System.out.println("Before created: "
                + active(created, expires, created.minusNanos(1)));
        System.out.println("At created: "
                + active(created, expires, created));
        System.out.println("Just before expiry: "
                + active(created, expires, justBefore));
        System.out.println("At expiry: "
                + active(created, expires, expires));
        System.out.println("One nano after: "
                + active(created, expires, expires.plusNanos(1)));
    }
}
~~~

Compile/run:

~~~bash
javac ExpiryBoundaryDemo.java
java ExpiryBoundaryDemo
~~~

Stdout:

~~~text
Before created: false
At created: true
Just before expiry: true
At expiry: false
One nano after: false
~~~

This example does not rely on real clock resolution: all instants are constructed explicitly and nanosecond arithmetic operates on **data**, so the output is deterministic.

## 10. Self-check questions

**1.** Why should `Instant` be used instead of `LocalDateTime` for `createdAt` in a multi-timezone system?

**Answer:** `Instant` identifies an absolute point in time; `LocalDateTime` lacks an offset/zone and can map to multiple different instants. Storing and exchanging event timestamps as instants removes ambiguity in distributed systems.

**2.** If `createdAt=12:00Z` and TTL is 30 minutes, is `12:30Z` still valid?

**Answer:** No, under the half-open rule `[createdAt, expiresAt)`. The validity condition is `now.isBefore(expiresAt)`; at the exact expiration instant, the result is `false`.

**3.** Why might `Instant.now()` not be enough to strictly order events across two servers?

**Answer:** Clocks can skew or be adjusted, and network-transmitted events can be delayed. An ordering/version/sequence mechanism or causal metadata is needed when ordering is a strict requirement.

**4.** Should `createdAt` change after a retry of creating the same entity?

**Answer:** If the retry is for the same creation request that already succeeded, you should normally reuse the original creation timestamp and ensure idempotency; do not generate a new `createdAt` just because the request was resent.

**5.** Can a session be considered expired only when the database automatically deletes the record?

**Answer:** No. Logical expiration must be checked on the processing path; record cleanup/deletion can happen later.

**6.** What should be used to represent a token expiring exactly 24 hours after issuance?

**Answer:** `Instant issuedAt` plus `Duration.ofHours(24)`. If the requirement is to expire at the **end of a regional calendar day**, use a calendar date and `ZoneId` to compute the boundary.

## Key takeaways

- **`Instant` is the right type for occurred event timestamps, creation timestamps, and expiration timestamps**, because it identifies a point on the timeline independent of display time zones.
- For audit logs, distinguish **occurred time**, **recorded time**, and **processed time** when they carry different semantics. Timestamps are neither IDs nor guarantees of causal order.
- **`createdAt` is typically assigned once**; update timestamps belong in a separate field.
- **`expiresAt` is usually computed from an `Instant` plus a `Duration`**, using a half-open validity interval `[createdAt, expiresAt)`; at the exact expiration boundary, access must be rejected.
- Use an **injected `Clock`** for deterministic time testing and boundary simulation. Managing clock synchronization, precision, serialization, database storage, and concurrency is essential in real-world implementations.
