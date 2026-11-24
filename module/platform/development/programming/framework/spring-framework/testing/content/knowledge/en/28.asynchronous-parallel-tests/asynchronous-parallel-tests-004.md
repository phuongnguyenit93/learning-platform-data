# Replacement Clocks and Virtual Time for Helper Code

## Time is a dependency to control in tests

Many application behaviors depend on the current time: token expiration, overdue order payment, login session timeout, daily reports, retry windows, or tasks that only run after a delay. If code reads the system clock directly, test results will depend on when the test actually runs.

Example:

~~~java
boolean isExpired(Instant expiresAt) {
    return Instant.now().isAfter(expiresAt);
}
~~~

Tests for this method must construct data based on the real clock. When tests run slowly, cross midnight, or execute near the expiration timestamp, results can change. To test the exact moments just before, right at, and right after a deadline, the time source must be controlled.

In Java, the appropriate abstraction for wall-clock time is **java.time.Clock**. You can inject Clock into services instead of calling Instant.now(), LocalDate.now(), or ZonedDateTime.now() directly without passing a clock.

For reactive tasks with delays, intervals, or timeouts, the scheduler also needs to be controlled. Reactor provides **VirtualTimeScheduler** and **StepVerifier.withVirtualTime(...)** to advance simulated time without real waiting.

These two mechanisms answer two different questions:

- Clock answers: "What is the application's current point in time?"
- Scheduler decides: "When is a task executed or a signal emitted?"

Replacing Clock does not automatically make timers run faster. Reactor's virtual time also does not automatically change values returned by Clock or the OS clock.

## Introducing Clock into application code

### Declaring Clock as a Spring bean

A shared Clock can be registered in configuration:

~~~java
import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class TimeConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

Clock.systemUTC() provides the current time in UTC. Using UTC for Instant prevents timestamps from depending on the host machine's default timezone. When a business date or time in a specific timezone is needed, convert the clock to the corresponding ZoneId where the conversion takes place.

The service receives Clock via its constructor:

~~~java
import java.time.Clock;
import java.time.Instant;

import org.springframework.stereotype.Service;

@Service
class ReservationService {

    private final Clock clock;

    ReservationService(Clock clock) {
        this.clock = clock;
    }

    boolean isExpired(Instant expiresAt) {
        return !clock.instant().isBefore(expiresAt);
    }
}
~~~

The comparison here treats the reservation as expired at the exact deadline: if now equals expiresAt, isExpired returns true. If the business rule requires it to remain valid through the exact deadline instant, a different comparison can be chosen; what matters is expressing the boundary rule clearly.

Do not create a new Clock inside each method. Injecting one dependency lets production code use the system clock while tests can substitute a fixed or controllable clock.

### Using clock for different time types

The factory methods in java.time support passing a Clock:

~~~java
Instant instant = Instant.now(clock);
LocalDate date = LocalDate.now(clock);
LocalTime time = LocalTime.now(clock);
ZonedDateTime dateTime = ZonedDateTime.now(clock);
~~~

These calls use the instant and timezone of the Clock. Avoid parameterless overloads in code requiring time testing, as they fall back to reading the default system clock.

For business dates, timezone is part of the rule. For example, an end-of-day report for a branch's timezone must obtain LocalDate using the branch's ZoneId rather than defaulting to UTC or the server's timezone:

~~~java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate businessDate = LocalDate.now(clock.withZone(businessZone));
~~~

Clock.withZone(...) keeps the same underlying time source but returns a clock with the requested timezone. Instant still represents the exact same moment; only how it converts to LocalDate, LocalTime, or ZonedDateTime changes.

## Built-in Clocks in Java

| Factory | Behavior | Use case |
| --- | --- | --- |
| Clock.systemUTC() | Reads system time in UTC | Timestamps and Instant-based logic |
| Clock.system(zone) | Reads system time with a specified ZoneId | Logic requiring calendar conversions by timezone |
| Clock.systemDefaultZone() | Uses the JVM default timezone | Only when behavior truly must follow machine configuration |
| Clock.fixed(instant, zone) | Always returns the same Instant | Testing at a deterministic point in time |
| Clock.offset(baseClock, duration) | Shifts the base clock's instant by a fixed offset | Creating a clock that sees time in the future or past |
| Clock.tick(baseClock, duration) | Observes time only in rounded tick increments | Code needing lower time resolution |

### Clock.fixed for deterministic tests

Clock.fixed(...) is the simplest choice when a test needs an unchanging point in time:

~~~java
Instant now = Instant.parse("2026-04-15T10:00:00Z");
Clock clock = Clock.fixed(now, ZoneOffset.UTC);

assertThat(clock.instant()).isEqualTo(now);
assertThat(Instant.now(clock)).isEqualTo(now);
~~~

Every read from the clock returns the same Instant. Thus a test can accurately check branches before, at, or after the deadline without being affected by test execution duration.

Example testing an expiration rule:

~~~java
@Test
void expiresReservationAtTheDeadline() {
    Instant deadline = Instant.parse("2026-04-15T10:00:00Z");
    Clock clock = Clock.fixed(deadline, ZoneOffset.UTC);
    ReservationService service = new ReservationService(clock);

    assertThat(service.isExpired(deadline)).isTrue();
}
~~~

To test just before the deadline, create a fixed clock earlier by an appropriate time unit:

~~~java
Clock justBeforeDeadline = Clock.fixed(
        deadline.minusNanos(1),
        ZoneOffset.UTC
);
~~~

With Clock.fixed, time does not advance on its own while the test waits. If multiple time steps need to be simulated within a single test, use a controllable clock or create multiple fixed clocks for each step.

### Clock.offset to shift time

Clock.offset(baseClock, duration) creates a clock whose time equals the base clock's time plus a Duration:

~~~java
Clock productionClock = Clock.systemUTC();
Clock tomorrowView = Clock.offset(productionClock, Duration.ofDays(1));
~~~

If the base clock keeps advancing, the offset clock advances with it, always shifted by a fixed interval. Offset is useful when a component needs to observe a relative reference point. For tests needing absolute, repeatable values, Clock.fixed is usually clearer.

### Clock.tick to limit resolution

Clock.tick(baseClock, duration) creates a clock that only observes instants aligned to the specified tick interval, such as every second or every minute:

~~~java
Clock secondClock = Clock.tick(Clock.systemUTC(), Duration.ofSeconds(1));
~~~

Clock.tick fits when an application only needs a certain time granularity. It is not a timer simulation tool and does not make tasks run at a faster pace. Do not use it to measure elapsed time accurately or as a replacement for a scheduler.

## Creating an advanceable clock in tests

Clock.fixed cannot advance. If a test needs to verify multiple states over time, you can build a small Clock specifically for tests. Using AtomicReference ensures threads read consistent values and updates remain safe when asynchronous tasks are involved.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

final class AdjustableClock extends Clock {

    private final AtomicReference<Instant> current;
    private final ZoneId zone;

    AdjustableClock(Instant initial, ZoneId zone) {
        this(new AtomicReference<>(Objects.requireNonNull(initial)),
                Objects.requireNonNull(zone));
    }

    private AdjustableClock(
            AtomicReference<Instant> current,
            ZoneId zone) {
        this.current = current;
        this.zone = zone;
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId zone) {
        return new AdjustableClock(current, Objects.requireNonNull(zone));
    }

    @Override
    public Instant instant() {
        return current.get();
    }

    void advance(Duration duration) {
        current.updateAndGet(value -> value.plus(duration));
    }

    void set(Instant instant) {
        current.set(Objects.requireNonNull(instant));
    }
}
~~~

This is a test fixture, not a default clock for production. advance(...) changes the instant observed by all consumers using the same instance. withZone(...) creates a view with a different timezone while still sharing the same Instant source.

Tests can control the expiration boundary inside a single method:

~~~java
@Test
void becomesExpiredWhenTheClockReachesTheDeadline() {
    Instant start = Instant.parse("2026-04-15T09:59:59Z");
    Instant deadline = Instant.parse("2026-04-15T10:00:00Z");
    AdjustableClock clock = new AdjustableClock(start, ZoneOffset.UTC);
    ReservationService service = new ReservationService(clock);

    assertThat(service.isExpired(deadline)).isFalse();

    clock.advance(Duration.ofSeconds(1));

    assertThat(service.isExpired(deadline)).isTrue();
}
~~~

The test does not have to wait a real second. It updates the clock value immediately, so it runs fast and deterministically.

If a mutable clock is not needed, avoid writing a heavy abstraction. Clock.fixed is usually sufficient for unit tests. Only use AdjustableClock when a test genuinely needs to move forward or backward across multiple timestamps.

## Testing timezones and date rollovers

Instant represents a global point in time; LocalDate and LocalDateTime are calendar values that do not carry a timezone by themselves. The same Instant can correspond to two different calendar dates in two different timezones.

To test date rules, fix both the Instant and the ZoneId:

~~~java
Instant instant = Instant.parse("2026-04-15T23:30:00Z");

Clock utcClock = Clock.fixed(instant, ZoneOffset.UTC);
Clock tokyoClock = utcClock.withZone(ZoneId.of("Asia/Tokyo"));

assertThat(LocalDate.now(utcClock))
        .isEqualTo(LocalDate.of(2026, 4, 15));
assertThat(LocalDate.now(tokyoClock))
        .isEqualTo(LocalDate.of(2026, 4, 16));
~~~

This helps catch bugs where the machine's default timezone is used when computing settlement dates, expiration dates, or notification dates.

For timezones with daylight saving time, transitions into summer time or back to standard time can cause local time to skip forward or repeat. Test with concrete Instants on both sides of the transition and a ZoneId with the corresponding DST rules. Avoid manually adding an hour to LocalDateTime to simulate DST; let the timezone's ZoneRules perform the conversion.

If business logic requires an exact point in time, store and compare Instant. Convert to ZonedDateTime or LocalDate only when regional calendar rules need to be applied. LocalDateTime does not contain enough information to uniquely identify an instant across multiple timezones or DST transitions.

## Virtual time for Reactor

Clock controls calls that read the current time. Operators like Mono.delay, Flux.interval, timeout, or delayElements depend on a scheduler instead. In Reactor, VirtualTimeScheduler lets you advance the scheduler clock without waiting in real time.

Reactor Test provides StepVerifier.withVirtualTime(...) to install a virtual scheduler for a publisher in a test scenario:

~~~java
import java.time.Duration;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void emitsThreeTicksWithoutWaitingThreeRealSeconds() {
    StepVerifier.withVirtualTime(
                    () -> Flux.interval(Duration.ofSeconds(1)).take(3))
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(3))
            .expectNext(0L, 1L, 2L)
            .verifyComplete();
}
~~~

Flux.interval emits the first item after one second, and then one more item each second. thenAwait(Duration.ofSeconds(3)) advances the virtual scheduler by three seconds, causing all three items to be emitted without the test needing Thread.sleep.

### Creating the publisher inside the supplier

The publisher must be created inside the supplier passed to withVirtualTime:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofSeconds(1)).take(2))
        .thenAwait(Duration.ofSeconds(2))
        .expectNext(0L, 1L)
        .verifyComplete();
~~~

Do not create a timer-based publisher beforehand and pass that variable into the supplier:

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1));

StepVerifier.withVirtualTime(() -> ticks)
        .thenAwait(Duration.ofSeconds(2))
        .expectNext(0L, 1L)
        .thenCancel()
        .verify();
~~~

In this flawed virtual-time setup example, Flux.interval already selected its scheduler when the publisher was created. When the supplier is invoked, the publisher still holds the old scheduler, so installing the virtual scheduler cannot control that timer. Create scheduler-dependent operators inside the supplier.

### Using an explicitly injected scheduler

For a service that accepts a Scheduler via constructor, you can supply a VirtualTimeScheduler directly to the service. In that case, StepVerifier needs to use the same scheduler:

~~~java
import java.time.Duration;

import reactor.core.publisher.Flux;
import reactor.core.scheduler.Scheduler;

class HeartbeatService {

    private final Scheduler scheduler;

    HeartbeatService(Scheduler scheduler) {
        this.scheduler = scheduler;
    }

    Flux<Long> heartbeats() {
        return Flux.interval(Duration.ofSeconds(1), scheduler).take(2);
    }
}
~~~

Test:

~~~java
import reactor.test.StepVerifier;
import reactor.test.scheduler.VirtualTimeScheduler;

@Test
void advancesTheInjectedScheduler() {
    VirtualTimeScheduler scheduler = VirtualTimeScheduler.create();

    try {
        HeartbeatService service = new HeartbeatService(scheduler);

        StepVerifier.withVirtualTime(
                        service::heartbeats,
                        () -> scheduler,
                        Long.MAX_VALUE)
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(2))
                .expectNext(0L, 1L)
                .verifyComplete();
    } finally {
        scheduler.dispose();
    }
}
~~~

When a scheduler is created and injected separately, the test must ensure both the publisher and StepVerifier use that same VirtualTimeScheduler instance. Calling dispose() in finally frees the scheduler after the test, even if an assertion fails.

## Clock and virtual scheduler do not advance together automatically

A pipeline might both wait on a timer and read business time:

~~~java
Mono<Instant> timestampAfterDelay(
        Clock clock,
        Scheduler scheduler) {
    return Mono.delay(Duration.ofSeconds(5), scheduler)
            .map(ignored -> clock.instant());
}
~~~

If only VirtualTimeScheduler advances, the timer fires after five virtual seconds, but Clock.systemUTC() still returns real system time. If only an AdjustableClock advances, the value of now changes, but Mono.delay will not emit until the scheduler advances.

When a test needs to control both, inject both Clock and Scheduler and advance each dependency explicitly:

~~~java
AdjustableClock clock = new AdjustableClock(
        Instant.parse("2026-04-15T10:00:00Z"),
        ZoneOffset.UTC
);
VirtualTimeScheduler scheduler = VirtualTimeScheduler.create();

try {
    Mono<Instant> result = timestampAfterDelay(clock, scheduler);

    StepVerifier.withVirtualTime(
                    () -> result,
                    () -> scheduler,
                    Long.MAX_VALUE)
            .expectSubscription()
            .then(() -> clock.advance(Duration.ofSeconds(5)))
            .thenAwait(Duration.ofSeconds(5))
            .expectNext(Instant.parse("2026-04-15T10:00:05Z"))
            .verifyComplete();
} finally {
    scheduler.dispose();
}
~~~

This example illustrates the control order: the test updates Clock and then advances the scheduler so the timer emits its signal. In real code, create the publisher inside the supplier if creating the publisher might capture the default scheduler. With an explicitly injected scheduler as shown above, ensure the service uses that exact virtual instance.

Do not expect a thenAwait(...) call to update Clock automatically. It only controls the scheduler used by StepVerifier.

## Distinguishing wall-clock time from elapsed time measurement

Clock represents wall-clock time. The system clock can be adjusted by the OS, NTP synchronization, or configuration changes. Therefore, it is not a suitable choice for accurately measuring an elapsed duration.

For example, do not call Instant.now() twice to measure an internal timeout if the system time might change between the two reads:

~~~java
long started = System.nanoTime();
doWork();
long elapsedNanos = System.nanoTime() - started;
~~~

System.nanoTime() is designed for relative duration measurements within the same JVM. Its value is not a calendar timestamp and cannot be converted into a date and time. Use Clock for business deadlines or stored timestamps; use a monotonic source like System.nanoTime() for execution duration, internal timeouts, and performance measurement.

In testable code, consider wrapping the monotonic source behind a separate interface as well if elapsed time needs to be controlled. Do not force Clock to act as a monotonic timer.

## Spring TaskScheduler and @Scheduled

Reactor's VirtualTimeScheduler controls Reactor operators that use the corresponding scheduler. It does not automatically replace the scheduler Spring uses to run @Scheduled methods or tasks registered with TaskScheduler.

Similarly, replacing the Clock bean does not make an @Scheduled task fire immediately. Clock provides the time observed by code; TaskScheduler decides when the task is triggered.

For scheduled helper code, separate the two responsibilities:

- The business part that computes deadlines, due dates, or whether work should run receives Clock via constructor.
- The scheduling coordination part uses TaskScheduler or the corresponding scheduling mechanism.

Unit tests can invoke business methods directly with Clock.fixed or AdjustableClock to verify time conditions. Integration tests for scheduling should control the scheduler, trigger, or completion signals rather than just swapping Clock and waiting for the @Scheduled annotation to run.

Example service separating the business decision from the trigger mechanism:

~~~java
class CleanupService {

    private final Clock clock;

    CleanupService(Clock clock) {
        this.clock = clock;
    }

    boolean shouldRemove(Instant expiresAt) {
        return !clock.instant().isBefore(expiresAt);
    }

    void runCleanup() {
        // Perform data cleanup operations.
    }
}
~~~

A test can verify shouldRemove(...) at multiple points in time without starting a scheduler thread. A separate test verifies that the trigger or scheduling mechanism invokes runCleanup() on schedule.

## Common mistakes

### Calling Instant.now() directly in services

Code depends on the real system clock, making time boundaries hard to reproduce in tests. Inject Clock and use Instant.now(clock) or clock.instant().

### Using Clock.fixed and expecting time to pass

Clock.fixed always returns the same Instant. If multiple points in time need to be simulated, create a new clock per step or use AdjustableClock in tests.

### Using a virtual scheduler to replace business time

VirtualTimeScheduler only controls scheduler timers. Calls to Instant.now(), LocalDate.now(), or Clock.systemUTC() still read their wall-clock time.

### Creating Flux.interval before withVirtualTime

The publisher may have already captured the real scheduler before StepVerifier installs the virtual scheduler. Create timer-dependent publishers inside the supplier of withVirtualTime.

### Creating a custom scheduler without passing it into the virtual test

An explicitly created scheduler is not automatically replaced just because the test uses withVirtualTime. Inject VirtualTimeScheduler into the service and provide the exact same instance to StepVerifier.

### Using Thread.sleep to wait for timers

Sleep makes tests slow and dependent on machine scheduling. With Reactor, use thenAwait or expectNoEvent on the virtual scheduler; with Clock-based code, adjust the clock directly.

### Using Clock to measure elapsed time

System wall-clock time can jump. Use System.nanoTime() or a monotonic abstraction for timeouts and execution durations.

### Using the default timezone for business rules

Tests may run on machines with different timezones. Specify ZoneId explicitly and fix the Instant when testing dates, times, or DST.

### Forgetting to dispose custom schedulers

A standalone VirtualTimeScheduler should be disposed after the test. Put it in finally so the scheduler is cleaned up even if an assertion fails.

## Choosing a tool by the type of time to control

| Need | Tool | How to control |
| --- | --- | --- |
| Verify token or reservation expiration | Clock | Inject Clock.fixed before, at, and after the deadline |
| Verify business dates by timezone | Clock + ZoneId | Fix Instant and specify zone |
| Advance time across multiple steps in one test | AdjustableClock | Call advance(...) or set(...) |
| Simulate relative time offset from a base time | Clock.offset | Create a clock with a Duration offset |
| Test Mono.delay or Flux.interval | VirtualTimeScheduler | StepVerifier.withVirtualTime and thenAwait |
| Test reactive service with its own Scheduler | Injected Scheduler + VirtualTimeScheduler | Supply the same scheduler to service and StepVerifier |
| Test @Scheduled or TaskScheduler | Spring's scheduler mechanism | Control the trigger/scheduler or test business logic separately |
| Measure duration or internal timeouts | Monotonic time source | System.nanoTime() or corresponding abstraction |

## Workflow for building deterministic time tests

1. Identify whether the code asks for the current time, waits for a timer, or measures elapsed duration.
2. Inject Clock for calendar logic and Scheduler for scheduled tasks.
3. Choose Clock.fixed for a fixed timestamp; only create AdjustableClock if time must change during the test.
4. Fix ZoneId when testing LocalDate, LocalTime, ZonedDateTime, or DST rules.
5. For Reactor, create the publisher inside the supplier of withVirtualTime or inject VirtualTimeScheduler explicitly.
6. Advance Clock and scheduler independently in the exact order required by the behavior under test.
7. Assert both time boundaries (before, at, and after deadline) and business results.
8. Dispose custom schedulers and ensure no background tasks or subscriptions remain running after the test.

Replacement clocks make point-in-time business decisions reproducible; virtual time makes reactive timers fast and deterministic to test. Separating Clock from Scheduler lets tests know exactly which dependency is being controlled and avoids confusing changing wall-clock time with triggering a task.
