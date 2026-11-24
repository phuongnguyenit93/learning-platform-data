# SpEL in @Scheduled and configuration values

## 1. Overview

Spring Framework allows declaring a schedule for a method using the `@Scheduled` annotation. Schedule values can be written directly in code or retrieved from external configuration such as `application.properties`, `application.yml`, environment variables, and other PropertySources.

In annotation configuration, two common syntaxes are:

| Syntax | Role | Example |
|---|---|---|
| `${...}` | Property placeholder: retrieves a value from external configuration. | `${jobs.cleanup.cron}` |
| `#{...}` | SpEL expression: evaluates an expression, reads beans/properties, or calls allowed methods. | `#{@jobScheduleProperties.syncRate}` |

Property placeholders can be used to vary schedules across deployment environments without modifying source code. For String attributes of `@Scheduled`, Spring also supports SpEL to compute or retrieve values from beans in the ApplicationContext.

Example:

```java
@Scheduled(cron = "${jobs.report.cron}")
public void generateReport() {
    // ...
}
```

Example using SpEL with an interval value:

```java
@Scheduled(fixedDelayString = "#{@jobScheduleProperties.cleanupDelay}")
public void cleanup() {
    // ...
}
```

For the annotation to be processed, the application must enable scheduling and the method must reside on a Spring-managed bean.

## 2. Enabling @Scheduled with @EnableScheduling

Place `@EnableScheduling` on a configuration class:

```java
@Configuration
@EnableScheduling
public class SchedulingConfiguration {
}
```

Spring registers the mechanism for processing `@Scheduled` methods and creates corresponding tasks in the ApplicationContext. Without `@EnableScheduling` (or equivalent XML configuration), the annotation alone does not make methods run on a schedule.

Example of a bean with a scheduled method:

```java
@Component
public class ReportJob {

    @Scheduled(fixedDelay = 5000)
    public void generateReport() {
        // Generate report.
    }
}
```

The method is invoked by Spring's scheduler. Typically, the method has a `void` return type and takes no parameters. If the method returns a value in synchronous cases, that value is ignored.

Dependencies that the job needs should be injected into the bean via constructor or standard dependency injection mechanisms.

## 3. Trigger types in @Scheduled

For recurring tasks, `@Scheduled` provides three main trigger types:

| Attribute | Meaning | How the interval is calculated |
|---|---|---|
| `fixedRate` | Runs at a fixed period. | From the start time of this execution to the start time of the next. |
| `fixedDelay` | Runs after a fixed rest interval. | From when the previous execution finishes to when the next begins. |
| `cron` | Runs according to a calendar/clock schedule. | By second, minute, hour, day-of-month, month, and day-of-week fields. |

Example of a 5-second fixed rate:

```java
@Scheduled(fixedRate = 5, timeUnit = TimeUnit.SECONDS)
public void pollQueue() {
    // Poll queue.
}
```

Example of a 5-second fixed delay:

```java
@Scheduled(fixedDelay = 5, timeUnit = TimeUnit.SECONDS)
public void refreshCache() {
    // Refresh cache.
}
```

If execution duration varies each run, the two types have different meanings. Fixed rate maintains cadence from the start time; fixed delay always waits the full delay interval after the previous run finishes.

### 3.1. Initial delay

With fixed rate or fixed delay, a wait time before the first run can be specified:

```java
@Scheduled(
    initialDelay = 10,
    fixedRate = 30,
    timeUnit = TimeUnit.SECONDS
)
public void synchronize() {
    // ...
}
```

In the example, the first run starts after 10 seconds; subsequent runs follow a 30-second fixed rate.

A task that only runs once after a wait period can declare only initial delay:

```java
@Scheduled(initialDelay = 60_000)
public void runOnceAfterStartup() {
    // ...
}
```

Do not combine `initialDelay` with a cron trigger. Initial delay only applies to fixed rate and fixed delay.

## 4. Reading cron expressions from application.properties

Place the cron expression in the configuration file:

```properties
jobs.report.cron=0 0 2 * * MON-FRI
```

Use a placeholder in the annotation:

```java
@Scheduled(cron = "${jobs.report.cron}")
public void generateDailyReport() {
    // ...
}
```

When Spring processes the scheduled method, the placeholder is resolved to the configuration value. The same artifact can use different schedules in each environment through profiles or PropertySources.

Example:

```properties
# application.properties
jobs.report.cron=0 0 2 * * MON-FRI
```

```properties
# application-dev.properties
jobs.report.cron=0 */10 * * * *
```

```properties
# application-prod.properties
jobs.report.cron=0 0 2 * * MON-FRI
```

If the active profile is `dev`, the report schedule runs every 10 minutes. In production, the schedule runs at 02:00 on weekdays.

Verify that the actual profile and configuration sources have been loaded. If the property does not exist and has no default value, the placeholder may fail to resolve and scheduled task initialization will fail.

## 5. Default values and disabling a cron task

Placeholders support a default value after the `:` sign:

```java
@Scheduled(cron = "${jobs.cleanup.cron:-}")
public void cleanupExpiredData() {
    // ...
}
```

If `jobs.cleanup.cron` is not configured, the placeholder returns `-`.

Spring defines `Scheduled.CRON_DISABLED` with the value `-` to disable a cron trigger. This is useful when you want to toggle a task on/off from configuration without changing code.

Example:

```properties
# Disable task
jobs.cleanup.cron=-
```

```properties
# Enable task at 01:30 every day
jobs.cleanup.cron=0 30 1 * * *
```

The value `-` is a sentinel for cron triggers; do not use it as a valid delay interval for fixed rate or fixed delay.

In Spring Framework, the cron disabled sentinel has been supported since 5.1. When using an older version, check the exact version's documentation before relying on this behavior.

## 6. Spring cron syntax

Spring's cron expression uses six fields in order:

```text
second minute hour day-of-month month day-of-week
```

| Field | Common range | Example |
|---|---|---|
| Second | 0–59 | `0` |
| Minute | 0–59 | `30` |
| Hour | 0–23 | `2` |
| Day of month | 1–31 | `1` |
| Month | 1–12 or JAN–DEC | `*` |
| Day of week | 0–7 or MON–SUN | `MON-FRI` |

Example:

| Cron | Meaning |
|---|---|
| `0 0 2 * * *` | 02:00 every day. |
| `0 */5 * * * *` | Every 5 minutes, at second 0. |
| `0 0 9-17 * * MON-FRI` | Every hour from 09:00 to 17:00, Monday through Friday. |
| `0 30 8 1 * *` | 08:30 on the first day of every month. |
| `0 0 0 * * SUN` | 00:00 every Sunday. |

Spring cron also supports symbols and macros such as `L`, `W`, `#`, `@daily`, `@hourly`, `@weekly`, `@monthly`, and `@yearly`.

Example:

```java
@Scheduled(cron = "@daily")
public void dailyTask() {
    // Runs at midnight every day.
}
```

Cron expressions can be hard to read when they contain many fields. Document the meaning of the schedule and verify the expression using `CronExpression.parse(...)` in Java or with tests before deploying.

## 7. Setting the timezone for cron

The `zone` attribute specifies the time zone used to interpret the cron expression:

```java
@Scheduled(
    cron = "${jobs.report.cron}",
    zone = "${jobs.report.zone:Asia/Ho_Chi_Minh}"
)
public void generateReport() {
    // ...
}
```

Configuration:

```properties
jobs.report.cron=0 0 8 * * MON-FRI
jobs.report.zone=Asia/Ho_Chi_Minh
```

The job runs at 08:00 Vietnam time on weekdays. If zone is not specified, the scheduler uses its default timezone.

Use a valid Zone ID, such as `UTC`, `Asia/Ho_Chi_Minh`, or `Europe/Paris`. Do not assume the server's timezone matches the business timezone. When the application runs across multiple environments or geographic regions, explicit zone configuration makes schedules more predictable.

The `timeUnit` attribute does not apply to cron expressions.

## 8. Using fixedDelayString and fixedRateString with placeholders

The numeric attributes `fixedDelay`, `fixedRate`, and `initialDelay` accept numeric values in the annotation. When values need to come from configuration, use the String variants:

- `fixedDelayString`
- `fixedRateString`
- `initialDelayString`

Example:

```properties
jobs.cache.fixed-delay=PT30S
jobs.sync.fixed-rate=10s
jobs.sync.initial-delay=5s
```

```java
@Scheduled(fixedDelayString = "${jobs.cache.fixed-delay}")
public void refreshCache() {
    // ...
}

@Scheduled(
    fixedRateString = "${jobs.sync.fixed-rate}",
    initialDelayString = "${jobs.sync.initial-delay}"
)
public void synchronize() {
    // ...
}
```

These String attributes support Spring property placeholders and SpEL expressions. Interval values can use integers (defaulting to milliseconds unless timeUnit is changed), ISO-8601 Duration format such as `PT30S`, or simple durations such as `10s` depending on the Spring version in use.

If using an integer and wanting a unit other than milliseconds, `timeUnit` can be set:

```java
@Scheduled(
    fixedDelayString = "${jobs.cache.delay:30}",
    timeUnit = TimeUnit.SECONDS
)
public void refreshCache() {
    // ...
}
```

If the string is a Duration with an explicit unit such as `30s` or ISO-8601 `PT30S`, `timeUnit` is not used to override the unit in that Duration.

## 9. Using SpEL to retrieve values from configuration beans

SpEL is useful when a schedule value needs to be retrieved from a Spring bean rather than simply reading a plain property.

Example of a configuration-holding bean:

```java
@Component("jobScheduleProperties")
@ConfigurationProperties(prefix = "jobs")
public class JobScheduleProperties {

    private String cleanupDelay = "PT30S";

    public String getCleanupDelay() {
        return cleanupDelay;
    }

    public void setCleanupDelay(String cleanupDelay) {
        this.cleanupDelay = cleanupDelay;
    }
}
```

Scheduled method referencing the bean using SpEL:

```java
@Component
public class CleanupJob {

    @Scheduled(
        fixedDelayString = "#{@jobScheduleProperties.cleanupDelay}"
    )
    public void cleanup() {
        // ...
    }
}
```

In the expression:

- `#{...}` instructs SpEL evaluation.
- `@jobScheduleProperties` references the bean with that name in the ApplicationContext.
- `.cleanupDelay` reads the property from the bean.
- The result must have a duration format accepted by `@Scheduled`.

Permitted methods on the bean can be called:

```java
@Scheduled(
    fixedRateString = "#{@jobScheduleProperties.getSyncRate()}"
)
public void synchronize() {
    // ...
}
```

For simple configuration, `${jobs.sync.rate}` is usually easier to understand and operate. Use SpEL when you genuinely need to read a bean, call a method, or compute a value via an expression.

## 10. Combining property placeholders and SpEL

The two syntaxes have different goals:

- Placeholders retrieve an already-configured value.
- SpEL computes or accesses a value through an expression context.

Example retrieving duration from a bean:

```java
@Scheduled(fixedDelayString = "#{@scheduleSettings.cleanupDelay}")
public void cleanup() {
    // ...
}
```

Example reading cron directly from configuration:

```java
@Scheduled(cron = "${jobs.cleanup.cron:-}")
public void cleanupExpiredData() {
    // ...
}
```

For cron, the common practice is using a placeholder to retrieve the cron string from configuration and using `-` to disable the trigger. For fixed rate, fixed delay, and initial delay in String form, the annotation Javadoc explicitly states that both placeholders and SpEL are supported.

Do not arbitrarily nest `${...}` and `#{...}` without understanding the context's resolution order. If an expression is complex, move the calculation logic into a clearly named configuration bean and have the annotation simply read a single property.

## 11. When values are resolved

Annotation values are resolved when Spring processes and registers scheduled methods during ApplicationContext initialization. Afterward, the scheduler uses the created trigger.

This means changing a property or bean value after the task has been registered does not automatically guarantee the current schedule is recalculated. For example, updating `jobs.cleanup.cron` in a configuration source does not by default replace an already-registered trigger.

If the requirement is to change schedules while the application is running, use programmatic scheduling mechanisms such as `SchedulingConfigurer`, `TaskScheduler`, and manage `ScheduledFuture`/task registration to cancel and reschedule according to the new configuration.

Do not confuse SpEL in an annotation with an expression re-evaluated on every method execution. In the normal case, the expression provides metadata for schedule registration; the scheduler does not re-evaluate the annotation before each invocation.

## 12. Choosing fixed rate, fixed delay, or cron

Choose the trigger based on the nature of the work:

| Need | Suitable choice | Reason |
|---|---|---|
| Poll a queue at a fixed cycle | Fixed rate | Maintains cadence based on start times. |
| Wait for processing to finish then rest for an interval | Fixed delay | The rest interval is measured after the previous run finishes. |
| Run at 02:00 every day | Cron | Schedule tied to wall-clock time. |
| Run during business hours on weekdays | Cron | Clearly expresses date/time schedules. |
| Wait a while after startup then run once | Initial delay | No recurring trigger needed. |
| Toggle schedule via profile/config | Placeholder in cron or duration string | No code changes needed between environments. |

If a method might run longer than its period, consider the scheduler, overlap potential, and idempotency of the job. Fixed rate does not mean the job is guaranteed to finish before the next start time in every scheduler configuration.

## 13. Configuring the scheduler and multiple scheduled methods

If the application has many tasks or long-running tasks, a custom TaskScheduler can be configured:

```java
@Configuration
@EnableScheduling
public class SchedulingConfiguration {

    @Bean
    public ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler =
                new ThreadPoolTaskScheduler();

        scheduler.setPoolSize(4);
        scheduler.setThreadNamePrefix("scheduled-");
        scheduler.initialize();

        return scheduler;
    }
}
```

Since Spring Framework 6.1, the `scheduler` attribute of `@Scheduled` can select a scheduler bean or qualifier:

```java
@Scheduled(
    fixedRateString = "${jobs.metrics.rate:10s}",
    scheduler = "metricsScheduler"
)
public void collectMetrics() {
    // ...
}
```

When there are multiple `@Scheduled` annotations on the same method (the annotation is repeatable), each declaration creates a separate trigger. Schedules can overlap or invoke the method nearly concurrently. Check carefully to avoid accidentally registering two overlapping schedules.

When using `SimpleAsyncTaskScheduler` with virtual threads, current Spring documentation recommends fixed rate and cron over fixed delay because fixed-delay tasks operate on a single scheduler thread in that configuration.

## 14. Rules and limitations of scheduled methods

A standard synchronous scheduled method:

- Takes no parameters.
- Usually returns `void`; synchronous return values are ignored.
- Must reside on a Spring-managed bean.
- Should avoid creating multiple instances of the same bean that could cause the same schedule to be registered multiple times.
- Should handle exceptions, logging, and job status inside the method according to application requirements.

Spring Framework 6.1 and later also support certain reactive methods returning a Publisher or a type convertible to a Publisher. The Publisher is created once, and then the scheduler subscribes to it according to the trigger. This differs from standard synchronous methods; ensure the Publisher supports multiple consecutive subscriptions and understand how errors are logged.

## 15. Testing configuration values and cron expressions

Do not wait for an actual scheduled run in unit tests to detect configuration errors. Cron expressions can be verified directly:

```java
@Test
void reportCronIsValid() {
    CronExpression cron =
            CronExpression.parse("0 0 2 * * MON-FRI");

    assertNotNull(cron);
}
```

Duration values can be verified by parsing:

```java
@Test
void cleanupDelayHasExpectedDuration() {
    Duration delay = Duration.parse("PT30S");

    assertEquals(Duration.ofSeconds(30), delay);
}
```

For property placeholders, check each profile or test context with the corresponding PropertySource. Ensure required properties are present or have valid default values.

For SpEL bean references, initialize a test ApplicationContext containing the required configuration bean and verify the expression resolves to a valid duration.

Scenarios that should be tested:

- Property is not declared.
- Placeholder with default value.
- Cron expression with wrong field count or invalid values.
- Cron disabled sentinel `-`.
- Invalid Zone ID or one not matching business requirements.
- Negative, zero, or malformed duration.
- SpEL referencing a nonexistent bean.
- SpEL reading a nonexistent property or returning a value unparseable as a duration.
- Two triggers accidentally declared on the same method.

## 16. Common errors and how to handle them

| Symptom | Common cause | How to handle |
|---|---|---|
| Method does not run | `@EnableScheduling` not enabled or bean not managed by Spring. | Check scheduling configuration and component scan. |
| Placeholder is not resolved | Missing property or PropertySource/profile not loaded. | Check key, profile, and default value. |
| Cron task is disabled | Cron value is `-`. | Check environment configuration and enable a valid cron expression if needed. |
| Invalid cron expression | Wrong field count, order, or values. | Use Spring's six-field format and verify with CronExpression. |
| Job runs at the wrong hour | Zone is not set or server timezone differs from business timezone. | Configure `zone` explicitly with a Zone ID. |
| Fixed delay differs from expectations | Confusing post-completion rest interval with fixed rate. | Choose the right fixedDelay/fixedRate for the timing point to measure. |
| Duration string fails to parse | Using unsupported unit or format. | Use integer with timeUnit, simple duration, or valid ISO-8601. |
| `#{...}` fails to evaluate | Bean does not exist, wrong name, or expression does not return a valid duration value. | Check bean name, property/method, and result type. |
| Changing property does not change schedule | Task was already registered with the resolved trigger. | Use programmatic scheduling APIs to cancel and re-register the task. |
| Method runs multiple times | Multiple triggers, multiple bean instances, or multiple schedule configurations. | Check repeatable annotations and bean lifecycle. |
| Overlapping jobs | Execution time is longer than period or multiple triggers exist. | Check scheduler, concurrency, and idempotency. |

## 17. Workflow for configuring @Scheduled

1. Enable `@EnableScheduling` in Spring configuration.
2. Identify which Spring bean owns the method and ensure the method takes no parameters.
3. Choose cron, fixed rate, or fixed delay according to timing requirements.
4. If the schedule is environment-dependent, place the value in application properties/YAML or the corresponding configuration source.
5. Use `${...}` to read the property and set a default value when the task can be disabled.
6. Use `fixedRateString`, `fixedDelayString`, or `initialDelayString` when placeholders or SpEL are needed for durations.
7. Use `#{...}` to read a configuration bean when an expression is genuinely needed.
8. For cron, specify all six fields and the timezone.
9. Verify defaults, disabled sentinel, duration format, and profiles.
10. If the schedule must change at runtime, use TaskScheduler/SchedulingConfigurer to manage task re-registration.
11. Check the scheduler pool, overlap potential, and execution logs.
12. Write tests for expressions, properties, and triggers instead of only waiting for the job to run in a real environment.

## 18. Key takeaways

- `@EnableScheduling` enables processing of `@Scheduled` annotations.
- `${...}` retrieves properties from configuration; `#{...}` evaluates SpEL.
- `fixedDelayString`, `fixedRateString`, and `initialDelayString` support placeholders and SpEL.
- Use placeholders to externalize cron; the value `-` disables the cron trigger.
- Spring cron has six fields: second, minute, hour, day-of-month, month, and day-of-week.
- `zone` determines the cron timezone.
- Fixed rate measures between start times; fixed delay measures from when the previous run finishes.
- Initial delay applies to fixed rate/fixed delay; cron does not support initial delay.
- Annotation values are resolved when the task is registered; changing config does not automatically reschedule running tasks.
- Use TaskScheduler/SchedulingConfigurer when dynamic schedule management is needed.
- Verify profiles, properties, durations, cron, timezone, scheduler, and overlap potential.

## References

- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework Javadoc — @Scheduled](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/Scheduled.html)
- [Spring Framework Javadoc — ScheduledAnnotationBeanPostProcessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/ScheduledAnnotationBeanPostProcessor.html)
- [Spring Framework Javadoc — CronExpression](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/support/CronExpression.html)
- [Spring Framework Javadoc — TaskScheduler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/TaskScheduler.html)
