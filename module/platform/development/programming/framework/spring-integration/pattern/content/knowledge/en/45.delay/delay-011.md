# Testing time with a controllable clock

In the **Delay** chapter of **SPRING_INTEGRATION_PATTERN**, many behaviors depend on time: a message is held inside a Delayer, a retry waits until its next attempt, an Aggregator/Resequencer group expires, or a request is valid only before a deadline. If everything is tested with `Thread.sleep()` and wall-clock measurements, tests are usually slow, hard to reproduce, and flaky on CI.

**Testing time with a controllable clock** means turning "what time is it now?" into a dependency injected into business code. Tests can freeze or actively advance time to verify behavior **before, at, and after** a mark. However, merely swapping `java.time.Clock` **does not automatically make Spring Integration Delayer's scheduler run faster**. Distinguish the business clock, the message release scheduler, and actual transport boundaries.

This lesson shows how to model time, write a controllable `Clock`, write sleep-free JUnit tests, relate it to Delayer, and extend it to Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation in Enterprise Integration Patterns flows.

> **Principle:** The business condition "is it due?" should be checked via an injected clock. The condition "has the message been delivered to the channel by Delayer?" also depends on **the scheduler, store, and dispatcher**; those two must be tested at different boundaries.

## 1. Why are real-time tests prone to failure?

For example, a task must only send a notification after 5 seconds:

```java
// Anti-pattern in unit tests: slow and scheduler-dependent.
service.scheduleNotification("order-42");
Thread.sleep(5_100);
assertEquals(1, sentNotifications.size());
```

This test has several weaknesses:

- Runs slowly in real time, multiplied across the test suite.
- Cannot cleanly test **1 ms early**, **on time**, and **past deadline**.
- Busy CI runners may prevent the callback from running even though the test slept long enough.
- Another scheduled task might finish before the assertion or continue after the test ends.
- Sleeping does not prove a business transaction committed, nor does it establish synchronization between threads.
- If `service.scheduleNotification()` creates a task outside the process, `Thread.sleep` does not confirm that task was actually durably persisted.

Increasing sleep from 5.1 to 6 seconds only makes tests slower, without guaranteeing flakiness disappears. **To make tests fast and reliable, replace the time dependency rather than extending the wait.**

## 2. Separating three questions about time

Before picking a tool, know exactly which question the system is asking:

| Question | Example | Tool and test scope |
| --- | --- | --- |
| **What time is it now?** | Has the notification reached `notBefore`? | `Clock` injected into domain service; completely deterministic unit tests |
| **When should the callback run?** | Schedule message delivery after 2 seconds | Controllable `TaskScheduler`/scheduler; schedule and dispatch tests |
| **When is another operation truly complete?** | Did payment commit before emitting the notification? | Completion signal, outbox, transaction, and idempotency; **never** solved by clock |

In particular, distinguish:

- **Absolute point in time:** `Instant`, such as `2026-11-21T09:00:00Z`, suitable for comparing timestamps or processing deadlines.
- **Duration:** `Duration.ofSeconds(5)`, used to compute `dueAt = receivedAt + delay`.
- **Local time:** `LocalDateTime` plus `ZoneId` to interpret "9 AM Hanoi time"; must handle daylight saving transition days in DST zones.
- **Monotonic/elapsed time:** used to measure execution timeouts and performance. `System.nanoTime()` is generally better for measuring elapsed time in the JVM than subtracting two wall-clock values. It **does not replace** `Instant` for business deadlines.

A wall-clock may jump due to system clock sync or administration. Therefore, never build concurrency invariants solely on comparing timestamps.

## 3. Injecting `Clock` into business logic

### 3.1. Wrong: calling `Instant.now()` everywhere

```java
// Hard to test: service directly reads the system clock.
boolean readyToSend(Instant notBefore) {
    return !Instant.now().isBefore(notBefore);
}
```

Test execution time and production code always move forward, making exact deadline boundaries hard to reproduce reliably.

### 3.2. Right: passing `Clock` into the object

Suppose a notification may only be delivered inside the window **[notBefore, expiresAt)**:

- Before `notBefore`: **WAITING**.
- At `notBefore` and before `expiresAt`: **READY**.
- At `expiresAt` or later: **EXPIRED**.

This definition is **an application contract**, not an enum or default of Spring Integration Delayer.

```java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class DeliveryWindowPolicy {

    public enum Decision { WAITING, READY, EXPIRED }

    public record Window(Instant notBefore, Instant expiresAt) {
        public Window {
            Objects.requireNonNull(notBefore, "notBefore");
            Objects.requireNonNull(expiresAt, "expiresAt");
            if (!expiresAt.isAfter(notBefore)) {
                throw new IllegalArgumentException(
                        "expiresAt must be after notBefore");
            }
        }
    }

    private final Clock clock;

    public DeliveryWindowPolicy(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public Decision evaluate(Window window) {
        Objects.requireNonNull(window);
        Instant now = clock.instant();

        if (!now.isBefore(window.expiresAt())) {
            return Decision.EXPIRED;
        }
        if (now.isBefore(window.notBefore())) {
            return Decision.WAITING;
        }
        return Decision.READY;
    }
}
```

Use `Clock.systemUTC()` in production, while supplying a different clock in tests:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

Clock productionClock = Clock.systemUTC();
Clock testClock = Clock.fixed(
        Instant.parse("2026-11-21T09:00:00Z"), ZoneOffset.UTC);

DeliveryWindowPolicy policy = new DeliveryWindowPolicy(testClock);
```

**Benefit:** business code does not have to wait 1 second to take the next branch; tests pick the exact evaluation instant and can verify millisecond boundaries.

## 4. JUnit: checking before, at, and after the deadline

With a window from `09:00:05.000Z` to just before `09:00:10.000Z`, we can test marks right at the boundaries:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class DeliveryWindowPolicyTest {

    private static final DeliveryWindowPolicy.Window WINDOW =
            new DeliveryWindowPolicy.Window(
                    Instant.parse("2026-11-21T09:00:05Z"),
                    Instant.parse("2026-11-21T09:00:10Z"));

    private static DeliveryWindowPolicy.Decision at(String isoInstant) {
        Clock fixed = Clock.fixed(
                Instant.parse(isoInstant), ZoneOffset.UTC);
        return new DeliveryWindowPolicy(fixed).evaluate(WINDOW);
    }

    @Test
    void waitingImmediatelyBeforeNotBefore() {
        assertEquals(
                DeliveryWindowPolicy.Decision.WAITING,
                at("2026-11-21T09:00:04.999Z"));
    }

    @Test
    void readyExactlyAtNotBefore() {
        assertEquals(
                DeliveryWindowPolicy.Decision.READY,
                at("2026-11-21T09:00:05.000Z"));
    }

    @Test
    void readyImmediatelyBeforeExpiry() {
        assertEquals(
                DeliveryWindowPolicy.Decision.READY,
                at("2026-11-21T09:00:09.999Z"));
    }

    @Test
    void expiredExactlyAtExpiry() {
        assertEquals(
                DeliveryWindowPolicy.Decision.EXPIRED,
                at("2026-11-21T09:00:10.000Z"));
    }
}
```

The tests above execute **instantly in logical time**: no `Thread.sleep()`, no dependence on CPU or scheduler. They also force the team to confirm the boundaries are **inclusive** of `notBefore` and **exclusive** of `expiresAt`, preventing off-by-one bugs.

Remember, though, that this test only proves **the READY/EXPIRED decision function**, not that Spring Integration actually emitted a message on time.

## 5. Three ways to build clocks for testing

| Tool | Characteristics | Best suited for |
| --- | --- | --- |
| `Clock.fixed(instant, zone)` | Time does not advance on its own | Testing an exact instant, boundaries, and deadlines |
| `Clock.offset(base, duration)` | Reads time from base plus offset | Comparing a few fixed offsets; or simulating clock skew |
| `Clock.tick(base, duration)` | Time is truncated to discrete steps | Testing coarse-grained time logic, not callback scheduling |
| Test-controllable `Clock` | Tests explicitly call `advance()` | Stepping sequentially through timestamps without sleeping |

Do not assume `Clock.offset(Clock.systemUTC(), ...)` is completely deterministic: the base is still the running real clock. For a fixed origin, use `Clock.fixed(...)` or a controllable clock.

### 5.1. Building `MutableClock` for multi-step time progression

The following Java 17 example stores the instant in an `AtomicReference` so tests can intentionally advance time. It does not wake a scheduler on its own; it is **a time source**, not a timer system.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public final class MutableClock extends Clock {

    private final AtomicReference<Instant> current;
    private final ZoneId zone;

    public MutableClock(Instant initial, ZoneId zone) {
        this(new AtomicReference<>(Objects.requireNonNull(initial)), zone);
    }

    private MutableClock(
            AtomicReference<Instant> current, ZoneId zone) {
        this.current = Objects.requireNonNull(current);
        this.zone = Objects.requireNonNull(zone);
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId newZone) {
        return new MutableClock(current, newZone);
    }

    @Override
    public Instant instant() {
        return current.get();
    }

    public void advance(Duration duration) {
        Objects.requireNonNull(duration);
        if (duration.isNegative()) {
            throw new IllegalArgumentException("Do not rewind in this test");
        }
        current.updateAndGet(now -> now.plus(duration));
    }

    public void set(Instant instant) {
        current.set(Objects.requireNonNull(instant));
    }
}
```

A few details to note:

- `advance(Duration.ZERO)` keeps the mark unchanged; tests advance only when explicitly called.
- `withZone(...)` shares the same `Instant` source while applying a different zone when interpreting calendars.
- `AtomicReference` makes reading/writing `Instant` atomic; **it does not make all business logic thread-safe**.
- Do not share one mutable clock across parallel tests if tests can shift each other's time.
- `set(...)` enables testing backward/forward clock jumps; if business rules disallow rewinding, enforce validation at state boundaries rather than relying on the clock.

## 6. Testing a due queue with a controllable clock

A testable design **separates deciding what is due from executing message release**. In unit tests, a manual scheduler can use `MutableClock` and only execute release when the test calls `drainDue()`.

**This is a pure-Java test model**, not Spring Integration Delayer's implementation. The goal is to verify semantics: computing `dueAt`, not releasing early, releasing at deadline, and ordering messages with the same deadline.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.PriorityQueue;

public final class ManualDueQueue {

    private record Pending(
            Instant dueAt, long ordinal, String eventId) {
    }

    private final Clock clock;
    private final PriorityQueue<Pending> pending =
            new PriorityQueue<>(
                    Comparator.comparing(Pending::dueAt)
                            .thenComparingLong(Pending::ordinal));
    private long nextOrdinal;

    public ManualDueQueue(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    public void schedule(String eventId, Duration delay) {
        if (eventId == null || eventId.isBlank()
                || delay == null || delay.isNegative()) {
            throw new IllegalArgumentException(
                    "Invalid event or delay");
        }
        pending.add(new Pending(
                clock.instant().plus(delay),
                nextOrdinal++,
                eventId));
    }

    public List<String> drainDue() {
        Instant now = clock.instant();
        List<String> due = new ArrayList<>();

        while (!pending.isEmpty()
                && !pending.peek().dueAt().isAfter(now)) {
            due.add(pending.remove().eventId());
        }
        return due;
    }

    public int pendingCount() {
        return pending.size();
    }
}
```

Here, `dueAt` is the absolute timestamp computed when `schedule()` is called. When `now == dueAt`, the message is due. The `ordinal` field lets tests enforce deterministic ordering if two messages share the same `dueAt`.

**Do not use this class as a production scheduler:** it lacks worker threads, persistent storage, transactions, retries, multi-instance locking, and ACKs. In production, all of those aspects must be engineered explicitly.

### 6.1. JUnit advancing time without sleeping

```java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import org.junit.jupiter.api.Test;

class ManualDueQueueTest {

    @Test
    void emitsAtDeadlineAndKeepsDeterministicTieOrder() {
        MutableClock clock = new MutableClock(
                Instant.parse("2026-11-21T09:00:00Z"),
                ZoneOffset.UTC);
        ManualDueQueue queue = new ManualDueQueue(clock);

        queue.schedule("event-A", Duration.ofSeconds(5));
        queue.schedule("event-B", Duration.ofSeconds(5));

        assertEquals(2, queue.pendingCount());
        assertEquals(List.of(), queue.drainDue());

        clock.advance(Duration.ofMillis(4_999));
        assertEquals(List.of(), queue.drainDue());

        clock.advance(Duration.ofMillis(1));
        assertEquals(List.of("event-A", "event-B"),
                queue.drainDue());
        assertEquals(0, queue.pendingCount());

        // Repeated drain does not re-emit the two already-popped events.
        assertEquals(List.of(), queue.drainDue());
    }

    @Test
    void differentDeadlinesReleaseInDeadlineOrder() {
        MutableClock clock = new MutableClock(
                Instant.parse("2026-11-21T09:00:00Z"),
                ZoneOffset.UTC);
        ManualDueQueue queue = new ManualDueQueue(clock);

        queue.schedule("later", Duration.ofSeconds(20));
        queue.schedule("earlier", Duration.ofSeconds(3));

        clock.advance(Duration.ofSeconds(3));
        assertEquals(List.of("earlier"), queue.drainDue());

        clock.advance(Duration.ofSeconds(17));
        assertEquals(List.of("later"), queue.drainDue());
    }
}
```

Test results are completely deterministic for **the simulated queue logic**. The test does not wait 20 real seconds, yet it also **does not verify the real scheduler operated**, since we only invoked `drainDue()` manually.

## 7. Delayer in Spring Integration: clock and scheduler are different

This is the most important boundary when moving from unit tests to integration tests.

A Spring Integration Delayer can be configured as follows (exact APIs and properties should be checked against your project's version):

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class ScheduledNotificationFlow {

    @Bean
    IntegrationFlow delayedNotifications() {
        return IntegrationFlow.from("acceptedNotifications")
                .delay("notificationDelayGroup",
                        spec -> spec.defaultDelay(5_000L))
                .channel("notificationsDue")
                .get();
    }
}
```

Meaning: messages are accepted on `acceptedNotifications` and scheduled by Delayer for forwarding to `notificationsDue` after the configured default delay. Actual behavior also involves the scheduler, group/message store, receipt time, time zones, and error/recovery policies.

**There is no automatic equivalence like this:**

```text
clock.advance(Duration.ofSeconds(5))
    ≠
Spring Integration Delayer immediately invokes callback
```

If business code uses an injected `Clock`, advancing the clock only changes calls to `clock.instant()`. A `TaskScheduler` using system time or its own thread pool will continue waiting in real time.

### 7.1. Three testing layers to keep separate

| Layer | Verification scope | How time advances |
| --- | --- | --- |
| **Unit: due policy** | Computing `dueAt`, deadlines, expiry, offsets, time zones | `Clock.fixed` or `MutableClock.advance` |
| **Component: scheduling/dispatch** | When due, the right callback/message is triggered | Controllable scheduler, or fake scheduling abstraction supplied by the app |
| **Integration: real Spring Integration Delayer** | Channel wiring, delay expression, message store, release output, errors, restarts | Real scheduler/adapter or version-compatible test harness controlling the scheduler |

If you want **virtual time** for a real Delayer, the test must **control the scheduler actually used by the endpoint**, not merely register a `Clock` bean that no endpoint references. Verify how `TaskScheduler` can be replaced/configured in your specific Spring Integration version; API names, recurring scheduling capabilities, and cancellation behavior can vary.

Do not claim "we tested Delayer with a fake clock" if the test actually only called `DeliveryWindowPolicy.evaluate()`.

### 7.2. What must a fake scheduler simulate?

If building a manual/fake scheduler for component integration tests, support the exact operations used by the code under test:

- Enqueue tasks into a queue ordered by `Instant` timestamp.
- Actively advance time past marks and run **due tasks**, including new tasks scheduled while running callbacks.
- Define ordering when multiple tasks share the same deadline.
- Handle cancellation, exceptions, recurring tasks, and completion status when those features are used.
- Guard against infinite loops when a callback immediately reschedules itself at the current timestamp.
- Verify the fake scheduler is **injected into the exact endpoint under test**, not shadowed by another default scheduler.

A fake scheduler missing cancellation, fixed-delay, or trigger semantics can cause tests to diverge from production. Therefore, **fast virtual-time tests should be paired with at least one integration/smoke test using a real scheduler** in a production-like configuration.

## 8. Writing Delayer integration tests without guessing timing

When no controllable scheduler is available, you can still write real integration tests in a less flaky way:

1. Use a relatively short delay for the test environment, without forcing production to use that short delay.
2. Send a message with a unique event ID/correlation ID into the channel.
3. Read output from `PollableChannel.receive(timeout)` with a **finite timeout** suited for CI.
4. Assert payload, headers, emission count, and exception state.
5. Only assert timing boundaries when truly necessary, with **explicitly documented tolerance/margin**.
6. Never rely on a bare `Thread.sleep(50)` to claim a callback has definitely run.

Snippet illustrating an assertion pattern in an integration test that already has `PollableChannel notificationsDue`:

```java
import static org.junit.jupiter.api.Assertions.*;

import org.springframework.messaging.Message;
import org.springframework.messaging.PollableChannel;

// notificationInput is connected to the real flow.
// notificationId is a unique ID for the current test.
Message<?> received = notificationsDue.receive(3_000);

assertNotNull(received, "Delayer did not emit within the test deadline");
// Also verify event ID, payload, headers, and business state.
```

This is only a **test fragment placed inside a test method** with configured channels, not a standalone JUnit test. `receive(3_000)` verifies a message was received **within the wait window**, without proving the message **was not released early**.

To check for early release on a real scheduler, compare timestamps against a clock with a designed tolerance, measure at the same observation point, and avoid turning jitter into false failures. For millisecond-precise boundary requirements, unit/component tests with controllable clocks/schedulers are a better source of boundary verification.

## 9. Edge cases to test with virtual time

| Case | Clock before / after | Invariant to verify |
| --- | --- | --- |
| 1 ms before deadline | `dueAt - 1 ms` | Not released early |
| Exactly at deadline | `dueAt` | Accepted per boundary-inclusive contract |
| 1 ms past deadline | `dueAt + 1 ms` | Due, no longer WAITING |
| Zero delay | `now + Duration.ZERO` | Ready per policy; scheduler handles zero delay properly |
| Negative delay | `Duration.ofMillis(-1)` | Rejected or handled per explicit policy, never silently forwarded |
| Expired deadline | `expiresAt` | Distinguishes `EXPIRED` from `READY` per published rules |
| Two messages with same deadline | `A, B` share `dueAt` | Deterministic order **if** contract requires it |
| Clock jumps backward | `now → now - 1 minute` | No erroneous/duplicate emissions; clear policy on clock shifts |
| Clock jumps forward | `now → now + 2 hours` | Defines how overdue tasks are handled |
| Retry with backoff | Attempt 1 fails; retries only when due | Never retries before allowed timestamp |
| Cancel before deadline | Scheduled then canceled | Canceled message is not released |
| Due while app is stopped | Restart after `dueAt` | Recovered per persistent store policy |
| Simultaneous deadline/expiry | Two marks coincide | Explicit precedence rule (e.g., EXPIRED before READY) |

**Never choose test timestamps based on the developer machine's current time.** Hardcode explicit `Instant` values and evaluate using a test-supplied `Clock`.

### 9.1. Local time and daylight saving time

Suppose the business requirement is "send reminder at 09:00 in the customer's local time":

- Store or pass an explicit `ZoneId`, e.g., `Asia/Ho_Chi_Minh`, without assuming the server's time zone.
- Convert local calendar time to `Instant` according to policy; afterward compare using `Clock.instant()`.
- In DST zones, some local times **do not exist** or **occur twice** on transition days. Tests must specify the policy for shifting to a valid instant or picking an offset.
- Do not equate "24 hours" with "tomorrow at the same local time" across all time zones; `Duration.ofHours(24)` differs from `plusDays(1)` around DST transitions.

A baseline implementation can use `ZonedDateTime` and `ZoneId`; policies for non-existent/ambiguous times must be explicitly designed rather than letting tests depend on environment defaults.

## 10. Testing retry/backoff with a controllable clock and scheduler

Retry with backoff is a form of **delaying the next attempt**, but is not synonymous with Delayer. A good test verifies **attempt count**, **when attempts are permitted**, and **final outcome**:

```text
T=0s     Execute attempt #1 → transient error
T=2s     Attempt #2 allowed to run
T=6s     Attempt #3 allowed to run
T=6s     Succeeds → no further retries scheduled

Test must assert:
  - attempt does not run at T=1.999s;
  - attempt runs when scheduler reaches T=2s;
  - next backoff is calculated from the specified reference mark;
  - after success, no retry tasks remain pending.
```

Do not use `Thread.sleep(2_000)` for every retry in unit tests. Separate the scheduler or `nextAttemptAt` calculation function to test with a fixed clock. If using real Spring Retry, verify the backoff/sleeper mechanism of the library version in use; **injecting `Clock` into a service does not automatically replace the retry library's sleeper**.

Other cases to test: bounded attempts, non-retryable errors, cancellation, stopping/starting endpoints, and exceptions when persisting retry schedules.

**Note on idempotency:** Retry only changes *when to try again*. If the previous attempt committed at an external service but the response was lost, retrying 2 seconds later can still produce a second side effect. You need an idempotency key or outcome lookup, not a longer backoff.

## 11. Testing group timeouts and late arrivals

In Aggregator/Resequencer, a group may wait for all parts carrying the same `correlationId`, or be processed on timeout. Time testing covers both **release conditions** and **group lifecycle**.

Example:

```text
Group G expects #1/3, #2/3, #3/3

T=0s    Receive #1 and #3
T=30s   Group timeout/expiry policy triggers
T=45s   #2 arrives late after retry finishes
```

Tests must verify:

1. For `T < 30s`, the group is not yet marked expired if that is the contract.
2. At or after expiry, the endpoint handles expiry per policy: partial release, discard, fail/recovery, or retain marker.
3. Message `#2` arriving later is classified as a late arrival and does not create another successful batch if business state is already finalized.
4. Duplicate of the same slot and a message arriving right at timeout do not trigger two releases.
5. `MessageGroupStore` retains/cleans state and coordinates with the scheduler as configured.
6. Errors/expiries go to the intended management branch, without assuming every group timeout automatically emits an `ErrorMessage` to the same `errorChannel`.

**Replacing `Clock` in application deadline-checking logic does not make Spring Integration's internal group timeout fire immediately.** To test real expiry with virtual time, control the scheduler and time dependencies used by the endpoint, or run an integration test with a bounded real timeout and explicit tolerance.

For hundreds of expiry policy variations, test a pure-Java *state machine* with a fake clock. Then run a small integration test suite verifying wiring and real timer behavior on the active library version.

## 12. Testing time correctness is not testing concurrency

Controlling the clock lets you test time boundaries, **not fix race conditions**. Two workers can simultaneously see `now >= dueAt` and both emit the message, even with a frozen clock.

Example:

```text
Worker A: reads now >= dueAt → true
Worker B: reads now >= dueAt → true
Worker A: sends message
Worker B: sends message
Result: same logical event emitted twice
```

You also need unique constraints, atomic claims, locks/leases, `PENDING → CLAIMED → SENT` states, or downstream idempotency. With multiple instances, single-JVM locks cannot protect a shared database.

A complete test suite should combine:

- **Virtual clock** to hit exact due boundaries.
- **CountDownLatch/barriers** so two consumers start processing the same task at that boundary.
- **Persistent store/real transactions** to verify only one transition commits.
- **Fault injection** right after claim, at publish, before ACK, and after restart.
- **Observing final outcomes** in the database, broker, or side-effect ledger.

Avoid concluding "the race is fixed" because increasing delay made a test pass. Delay controls timing; it does not replace synchronization or atomicity.

## 13. Test matrix for Delayer and message flows

| Test | Boundary | Expectation |
| --- | --- | --- |
| `notBefore - 1 ms` | Unit business policy | WAITING |
| `notBefore` | Unit business policy | READY |
| `expiresAt - 1 ms` | Unit business policy | READY |
| `expiresAt` | Unit business policy | EXPIRED |
| Two tasks with same deadline | Unit fake scheduler | Deterministic order per sample contract |
| Earlier-due task added later | Unit fake scheduler | Emits by `dueAt`, not merely insertion order |
| Zero/negative delay | Unit policy + scheduler | Zero handled properly, negative rejected per contract |
| Clock jump or DST | Unit date-time policy | Final instant explainable, no unintended duplicates |
| Delayer routes message to right channel | Spring Integration integration | Correct payload, headers, routing, and receive timeout |
| Output appears before deadline | Virtual scheduler component or integration with tolerance | Early release defect detected |
| Scheduler callback fails | Integration scheduling | Error/recovery follows configured mechanism |
| Application restarts before deadline | Integration + persistent store | Recovers or fails intentionally |
| Application restarts after deadline | Integration + persistent store | Catch-up policy, no duplicate emissions |
| Retry requires backoff | Retry policy / fake scheduler | Attempts at right marks, no infinite retries |
| Group expires with missing part | Aggregator/Resequencer integration | Expiry/partial/fail/recovery follows policy |
| Message arrives after group timeout | Integration + lifecycle | Late arrival does not emit a second result |
| Two workers trigger simultaneously | Concurrency integration | Single business side effect via idempotency |
| Transaction commits slower than delay | End-to-end | Does not use elapsed time to assert commit |

Not every case needs to run on a real scheduler. **Many boundary tests using a fake clock plus a small number of wiring and recovery tests using real components** balance speed, accuracy, and integration bug detection.

## 14. Observing and diagnosing timing failures

Useful fields in logs or audits for delayed messages:

```json
{
  "messageKey": "notification:order-42",
  "correlationId": "order-42:run-3",
  "scheduledAt": "2026-11-21T09:00:00Z",
  "dueAt": "2026-11-21T09:00:05Z",
  "releasedAt": "2026-11-21T09:00:05.147Z",
  "delayPolicy": "notify-after-5s",
  "outcome": "RELEASED"
}
```

This is an **application-defined schema**, not a default set of headers/metrics. Never log full sensitive payloads just for timing tests.

Metrics to monitor:

| Suggested metric | Meaning |
| --- | --- |
| `scheduledPendingCount` | Tasks/messages waiting for their deadline |
| `oldestOverdueAge` | Lateness of the oldest overdue unprocessed task |
| `scheduleToReleaseLatency` | Time from scheduling until message release |
| `releaseLateness` | `releasedAt - dueAt`, positive if released late |
| `earlyReleaseCount` | Events released before deadline |
| `schedulerExecutionFailureCount` | Callbacks that failed to execute successfully |
| `retryAttemptCount` | Retry pressure and backoff status |
| `groupExpiryCount` | Groups requiring expiration handling |
| `lateArrivalCount` | Messages arriving after group closed |
| `duplicateSideEffectCount` | Duplicate business effects caused by races/replays |

The metric names above are instrumentation suggestions; do not assume Spring Integration emits these exact names out of the box. Avoid using `messageKey` or `correlationId` as high-cardinality metric labels; keep them in structured logs and traces.

To diagnose a flaky integration test, record **expected `dueAt`, receipt time, scheduler used in the test, release policy, clock source, CI load, and timeout window**. When discrepancies arise, separate business logic bugs from timer, store, or system-time issues.

## 15. Checklist before declaring time tests complete

1. **Specify the time type clearly:** absolute timestamp, duration, local schedule, or deadline.
2. **Never call `Instant.now()` inside domain code requiring exact tests:** use an injected `Clock`.
3. **Test boundaries explicitly:** `t-1 ms`, `t`, `t+1 ms`, and inclusive/exclusive rules.
4. **Use fixed/mutable clocks for unit tests:** tests never sleep and do not depend on machine clocks.
5. **Separate the clock from the scheduler:** advancing `Clock` does not mean Delayer callbacks have executed.
6. **If using a virtual scheduler, inject it into the right component:** support all scheduling APIs actually used.
7. **Keep real integration tests:** verify Spring Integration channel wiring, store, scheduling, errors, and restarts.
8. **Never use `Thread.sleep` as a correctness condition:** wait on real completion signals, `receive(timeout)`, and bounded assertions.
9. **Watch time zones and DST:** store `Instant` and explicit `ZoneId`, test ambiguous local times.
10. **Test retries and deadlines:** backoff does not guarantee idempotency, timeout does not prove permanent loss.
11. **Test group expiry and late arrivals:** never emit batches or final side effects twice.
12. **Test concurrency separately:** latches, transactions/atomic claims, fault injection at due boundaries.
13. **Observe the right boundaries:** schedule persisted, message released, and business effect committed are three distinct stages.
14. **Measure and analyze flakiness:** log clock source, scheduled time, observed time, release jitter, and pending group state.

**Conclusion:** Testing time with a controllable clock lets us verify precisely whether a business rule **is due or not** without waiting in real time. With Spring Integration, add a scheduler-control layer if you want to simulate **Delayer actually releasing messages** in virtual time. Separating policy unit tests, scheduling component tests, and integration tests with real endpoints makes Delay lessons fast and deterministic, without masking race conditions, retry bugs, or message recovery issues.
