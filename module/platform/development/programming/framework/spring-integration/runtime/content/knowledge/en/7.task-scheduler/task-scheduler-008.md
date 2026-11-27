# Clock, Time Zones, and Schedule Testing

A poller can run at the right cadence yet still fire at the wrong business hour if the application uses the server's time zone instead of the operating locale's time zone. Cron schedules are also affected by Daylight Saving Time (DST) transitions, the duration of the previous poll, and how the scheduler handles missed triggers.

To make schedules reliable and testable, distinguish between an absolute instant, a time zone, the clock supplying current time, and trigger rules. In Java, `Instant` represents a point on the timeline; `ZoneId` represents time-zone rules; `Clock` provides the current instant in a zone; and `CronTrigger` computes the next execution according to a schedule expression.

## 1. Instant, LocalDateTime, ZoneId, and Clock

Time types in `java.time` serve distinct purposes:

| Type | Meaning | Usage Example |
|---|---|---|
| `Instant` | An absolute point on the UTC timeline | Storing timestamps, comparing instants across systems |
| `LocalDateTime` | Date and time on a local wall clock, without a time zone | Schedule data not yet bound to a location or zone |
| `ZoneId` | Time-zone rules, including offsets and historical changes | `Asia/Ho_Chi_Minh`, `Europe/Berlin` |
| `ZonedDateTime` | Local date and time bound to a `ZoneId` | Interpreting "09:00 local time" into an instant |
| `Clock` | Provider of current instant and zone | Injecting time into code for deterministic testing |

Do not use `LocalDateTime` as an interchange timestamp between services because that value does not indicate its offset or corresponding instant. When recording when a message was received or processed, normally store an `Instant`. When describing a schedule such as "run at 09:00 every weekday in Vietnam," store both the cron expression and the time-zone ID such as `Asia/Ho_Chi_Minh`.

Example creating clocks:

~~~java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");

Clock utcClock = Clock.systemUTC();
Clock businessClock = Clock.system(businessZone);

Instant now = Instant.now(utcClock);
LocalDate todayInBusinessZone = LocalDate.now(businessClock);
~~~

`Clock` can be injected into services instead of calling `Instant.now()` or `LocalDate.now()` directly in many places. During testing, replace the system clock with `Clock.fixed(...)` or `Clock.offset(...)` to control the current instant.

## 2. A Schedule's Time Zone Is Not Necessarily the Server's Time Zone

`TaskScheduler` provides a `Clock` via `getClock()`. A scheduler's default clock typically uses the system clock and the JVM's default time zone. A `CronTrigger` without its own zone uses the zone from `TriggerContext.getClock()`. Consequently, deploying the same application on servers with different time-zone configurations can cause default-based cron schedules to run at different local hours.

There are two ways to specify time zones explicitly:

1. Configure the `TaskScheduler`'s `Clock` so triggers using that clock share a consistent zone.
2. Pass a specific `TimeZone` or `ZoneId` to `CronTrigger`/the poller DSL when individual schedules have their own time zones.

Example configuring a scheduler with an explicit zone:

~~~java
@Bean
ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(2);
    scheduler.setThreadNamePrefix("integration-scheduler-");
    scheduler.setClock(Clock.system(ZoneId.of("Asia/Ho_Chi_Minh")));
    return scheduler;
}
~~~

`setClock(...)` sets the clock the scheduler uses for schedule calculations. This sets the default zone for triggers relying on the scheduler's `TriggerContext`. If a poller follows its own zone, pass the zone directly to the trigger so that intent does not depend on global configuration.

With Spring Integration Java DSL, you can pass `TimeZone` to `Pollers.cron`:

~~~java
@Configuration
public class ReportFlowConfiguration {

    private final TimeZone reportTimeZone =
            TimeZone.getTimeZone(ZoneId.of("Asia/Ho_Chi_Minh"));

    @Bean
    IntegrationFlow weekdayReportFlow(ReportService reportService) {
        return IntegrationFlow.from(reportService::loadPendingReports,
                        endpoint -> endpoint.poller(
                                Pollers.cron("0 0 9 * * MON-FRI", reportTimeZone)))
                .handle(reportService, "sendDailyReport")
                .get();
    }
}
~~~

The expression above uses Spring cron with six fields: second, minute, hour, day of month, month, and day of week. `0 0 9 * * MON-FRI` means 09:00:00 Monday through Friday in the supplied time zone. This is a schedule based on local wall-clock time, not a fixed 24-hour interval from the previous run.

You can configure `CronTrigger` directly if you want to use the trigger API:

~~~java
CronTrigger trigger = new CronTrigger(
        "0 0 9 * * MON-FRI",
        ZoneId.of("Asia/Ho_Chi_Minh"));

PollerSpec poller = Pollers.trigger(trigger);
~~~

Use IANA zone IDs such as `Asia/Ho_Chi_Minh` or `Europe/Berlin`. Avoid hard-coding fixed offsets like `UTC+7` for long-lived schedules if a location's legal rules could change. `ZoneId.of(...)` also catches invalid IDs at configuration time.

## 3. Cron, Fixed Delay, and Fixed Rate Describe Different Schedule Types

Not every schedule needs a time zone:

| Trigger | Description | Suitable Example |
|---|---|---|
| Fixed delay | Re-run after an interval measured from when the previous execution completed | Periodic queue check, resting 10 seconds after each processing pass |
| Fixed rate | Maintain trigger cadence at regular time intervals | Periodic status measurement every 30 seconds |
| Cron | Run at times according to local calendar date/time | Send report at 09:00 on business days |

Example:

~~~java
Pollers.fixedDelay(Duration.ofSeconds(10));
Pollers.fixedRate(Duration.ofSeconds(30));
Pollers.cron("0 0 9 * * MON-FRI", timeZone);
~~~

Fixed delay and fixed rate use `Duration`; they describe elapsed time, not local wall-clock time. Changing the server's time zone does not turn a 24-hour fixed delay into "09:00 every day." If the requirement is a fixed local calendar hour, use cron with an explicit zone.

With fixed rate, if work runs longer than the period, subsequent execution depends on the scheduler and execution policy. With cron, Spring's default `CronTrigger` uses lenient execution: the next run is computed from the previous completion time, so cron marks can be skipped when a task runs too long. Starting in Spring Framework 6.1.3, `CronTrigger.forFixedExecution(...)` computes from the previous scheduled time and catches up missed triggers while the scheduler retains the trigger context; this can produce consecutive late runs after a slow task. Trigger context state is not automatically persisted across JVM restarts. Choose fixed execution only when business requirements genuinely call for catch-up.

## 4. Daylight Saving Time and Local Schedules

Some time zones change their offset seasonally. When clocks spring forward to summer time, a local hour span can cease to exist. When clocks fall back to standard time, a local hour span can occur twice.

For example, in `Europe/Berlin`, a schedule running at 02:30 can encounter two situations:

- **Spring forward:** on transition day, the clock skips over a local hour; 02:30 may not exist.
- **Fall back:** the clock turns back; 02:30 may occur twice with two different offsets.

Do not assume a cron expression in every time zone always produces exactly one run per local day. Behavior during gaps/overlaps also depends on how `CronExpression` computes `ZonedDateTime`, trigger type, and execution policy. Test around DST transitions for every zone your application supports.

If business schedules cannot tolerate skipped or duplicate runs, explicitly define the rule: skip nonexistent hours, run at the next valid instant, pick the first or second occurrence during an overlap, or enforce once-per-business-day execution with an idempotency key. The scheduler only generates triggers; business uniqueness should still be protected at the processing layer.

One way to guard against duplicates is persisting an execution key by business date and schedule identifier:

~~~java
LocalDate businessDate = LocalDate.now(clock.withZone(businessZone));
String executionKey = "daily-report:" + businessDate;

if (executionRepository.tryMarkStarted(executionKey)) {
    reportService.generateFor(businessDate);
}
~~~

`tryMarkStarted` must be implemented atomically, such as via a unique constraint or insert-if-absent in the database. Checking with an `if` followed by a separate insert can let two instances run simultaneously when triggered nearly at the same moment.

## 5. Configuring the Clock on TaskScheduler

When an application has many cron schedules sharing the same zone, you can configure the scheduler's clock as the default:

~~~java
@Configuration
public class SchedulerConfiguration {

    @Bean
    ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("si-scheduler-");
        scheduler.setClock(Clock.system(ZoneId.of("Asia/Ho_Chi_Minh")));
        return scheduler;
    }
}
~~~

When using `Pollers.cron(expression)` without passing a time zone, `CronTrigger` reads the zone from `TriggerContext`'s clock—the clock supplied by the scheduler. When using `Pollers.cron(expression, timeZone)`, the zone is specified directly on the trigger. The second form is clearer when a schedule belongs to a specific location; the first is useful when setting a single shared rule for the whole scheduler.

`TaskScheduler` can be shared across many pollers and other tasks. Size the pool to match the number of scheduled tasks and their execution profile. If a scheduled task runs long on a scheduler thread, it can delay other tasks when the pool is too small. If a poller hands work off to another executor, distinguish scheduler threads from poller worker threads.

## 6. Testing Triggers Deterministically

Do not test cron schedules by waiting until real 09:00 or relying on the developer machine's time zone. Test next-execution calculations using a fixed clock.

Example using `CronTrigger` and `SimpleTriggerContext`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;

import org.junit.jupiter.api.Test;
import org.springframework.scheduling.support.CronTrigger;
import org.springframework.scheduling.support.SimpleTriggerContext;

class ReportScheduleTests {

    @Test
    void calculatesNextWeekdayRunInVietnamTime() {
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        Clock clock = Clock.fixed(
                Instant.parse("2026-11-20T01:00:00Z"), zone);

        CronTrigger trigger = new CronTrigger(
                "0 0 9 * * MON-FRI", zone);
        SimpleTriggerContext context = new SimpleTriggerContext(clock);

        Instant nextExecution = trigger.nextExecution(context);

        assertEquals(Instant.parse("2026-11-20T02:00:00Z"), nextExecution);
    }
}
~~~

The fixed clock in this example corresponds to 08:00 on Friday, 2026-11-20 in `Asia/Ho_Chi_Minh`. The next execution is 09:00 the same day, which is 02:00 UTC. The test requires no sleep and does not depend on the test runner's default time zone.

To test cron expressions directly without `TaskScheduler`, you can use `CronExpression` with a `ZonedDateTime` baseline. That helps verify weekdays, end-of-month dates, custom holiday rules, or DST transition points.

## 7. A Fixed Clock Is Not a Simulated Scheduler Clock

`Clock.fixed(...)` makes time-reading code and trigger calculations return the same instant throughout a test. It does not speed up JVM wall-clock time or scheduler threads. If you pass a fixed clock to `ThreadPoolTaskScheduler`, schedule calculations may keep seeing the same instant while the executor still waits in real OS time.

Therefore, divide testing into layers:

1. **Business-time unit tests:** inject `Clock.fixed` to verify business dates, cutoff times, and idempotency keys.
2. **Trigger unit tests:** use `CronTrigger.nextExecution(...)` with `SimpleTriggerContext(clock)` to verify the next instant.
3. **DST and time-zone tests:** use fixed instants before/after gaps or overlaps to confirm desired rules.
4. **Scheduler integration tests:** use short intervals, `CountDownLatch`/Awaitility, or a fake scheduler to verify tasks fire and flows are invoked. Set explicit timeouts; never wait hours for production schedules.
5. **Restart tests:** verify schedules re-register and catch-up/skip policies match requirements after downtime.

An integration test with a 100 ms schedule only proves the scheduler triggers under those test conditions. It does not prove cron works properly across DST, when the JVM changes time zones, or when tasks outlast their period.

## 8. Testing DST and Calendar Boundaries

For each supported `ZoneId`, build tests for these cases:

- Instants just before and after midnight to verify date rollovers.
- End-of-month dates and short months to verify day-of-month rules.
- Weekends and start-of-week days to verify day-of-week expressions.
- DST spring-forward start, when a local hour does not exist.
- DST fall-back end, when a local hour occurs twice.
- Tasks running longer than the gap between two cron marks to verify lenient vs. fixed execution.
- Application restart after missing one or more marks; verify whether the latest scheduled time is persisted and the trigger context restored.

Example creating instants around a DST transition day:

~~~java
ZoneId berlin = ZoneId.of("Europe/Berlin");

Instant beforeTransition = Instant.parse("2026-03-29T00:30:00Z");
Instant afterTransition = Instant.parse("2026-03-29T01:30:00Z");

ZonedDateTime before = beforeTransition.atZone(berlin);
ZonedDateTime after = afterTransition.atZone(berlin);
~~~

Compare `before` and `after` to confirm the local offset changed per the JDK's time-zone database. For real schedules, test `nextExecution` results for each instant and explicitly assert expectations when a calendar hour is missing or occurs twice.

Do not hard-code summer or winter offsets. `ZoneId` uses the time-zone database bundled with the JDK; when time-zone laws change, update the JDK/runtime to get the new rules. For long-running systems, log both instant and zoned time when investigating schedule drift.

## 9. Lenient Execution, Fixed Execution, and Downtime

Cron does not only specify "what time to run"; it also needs rules for when the previous execution has not finished yet or the application was down across multiple marks.

| Policy | Next Execution Calculation | Consequence |
|---|---|---|
| Lenient execution (default for `CronTrigger`) | Based on completion time of the previous execution | Cron marks occurring while the task is still running may be skipped |
| Fixed execution (`CronTrigger.forFixedExecution`, Spring Framework 6.1.3+) | Based on the previous scheduled time in the current trigger context | Marks missed while a task runs long are caught up, which may cause consecutive late executions |

Example using fixed execution in Java DSL:

~~~java
@Bean
IntegrationFlow catchUpFlow(ReportService reportService) {
    CronTrigger trigger = CronTrigger.forFixedExecution("0 0 9 * * MON-FRI");

    return IntegrationFlow.from(reportService::loadPendingReports,
                    endpoint -> endpoint.poller(Pollers.trigger(trigger)))
            .handle(reportService, "sendDailyReport")
            .get();
}
~~~

The `forFixedExecution` factory in Spring Framework 6.1.3+ uses the zone from the `TaskScheduler` clock. If a specific zone is needed, configure the scheduler's clock with `Clock.system(zone)` and verify the poller uses that scheduler. For schedules needing an explicit time zone directly, `Pollers.cron(expression, timeZone)` creates a cron trigger for that zone with default lenient semantics.

If catch-up across JVM restarts is required, the application must durably persist the latest scheduled timestamp and restore it with `CronTrigger.resumeFixedExecution(expression, resumptionTimestamp)` (or the corresponding lenient resume policy). Calling `forFixedExecution(...)` alone after a restart initializes the trigger from the current clock if the context lacks a prior timestamp; it does not automatically know which marks were missed during downtime. Persisting and updating timestamps must be consistent with business outcomes to avoid missed or duplicate runs.

Catch-up can be useful for data synchronization that must process every mark, but it can cause traffic spikes after downtime. If only the latest state matters, skipping stale marks and running once may make more sense. Regardless of policy, tasks should still be idempotent and use business keys to prevent duplicate runs when multiple instances start together.

## 10. Clock Synchronization and Runtime Schedule Observability

`Clock.system(...)` relies on the system clock. In production environments, synchronize server clocks with NTP or the platform's time-management service. If the system clock jumps significantly, wall-clock calculations and triggers can be affected.

To diagnose schedules, record:

- The cron expression and actual `ZoneId` of the trigger.
- The `Instant` computed for the next execution.
- Scheduled time, actual start time, and completion time of the most recent run.
- Execution duration, skipped count, or catch-up count if applicable.
- Scheduler status, active task count, and errors submitting/executing tasks.
- Spring Framework/Spring Integration versions and the JDK time-zone database version.

Do not log bare `LocalDateTime` alone when correlating across multiple servers. Log ISO-8601 with offset or UTC instants, such as `2026-11-20T09:00:00+07:00` and `2026-11-20T02:00:00Z`. When measuring execution duration, use a Micrometer Timer or monotonic time such as `System.nanoTime()` rather than subtracting two wall-clock timestamps that can be adjusted.

## 11. Schedule Design and Testing Checklist

- [ ] Choose `Instant` for timestamps and `ZoneId` for local schedules.
- [ ] Inject `Clock` into business code instead of calling `now()` directly in many places.
- [ ] Do not depend on the JVM's default time zone for production schedules.
- [ ] Use cron when requirements specify local hours/days; use `Duration` for elapsed time intervals.
- [ ] Pass zones explicitly via `Pollers.cron(expression, timeZone)` or configure the scheduler's clock.
- [ ] Verify Spring cron expressions have six fields, starting with seconds.
- [ ] Test end-of-month dates, weekdays, and DST transitions.
- [ ] Choose lenient or fixed execution based on long-running task policy; if catch-up across JVM restarts is needed, persist and restore the scheduled timestamp.
- [ ] Use `Clock.fixed` for trigger unit tests; do not treat it as a mock scheduler thread clock.
- [ ] Test idempotency when multiple instances run the schedule concurrently.
- [ ] Log instant, zone, scheduled time, and actual time to investigate schedule drift.

By separating clock, time zone, and trigger, Spring Integration schedules maintain consistent meaning across development, staging, and production. Testing with fixed instants validates schedule calculations; testing DST, downtime, and idempotency validates operational behavior that a single unit test cannot cover.

## References

- [Spring Integration API: Pollers](https://docs.spring.io/spring-integration/docs/6.4.x/api/org/springframework/integration/dsl/Pollers.html)
- [Spring Framework API: CronTrigger](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/support/CronTrigger.html)
- [Spring Framework API: SimpleTriggerContext](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/support/SimpleTriggerContext.html)
- [Spring Framework API: TaskScheduler](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/TaskScheduler.html)
- [Spring Framework API: ThreadPoolTaskScheduler](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html)
