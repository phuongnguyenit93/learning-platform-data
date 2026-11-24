# Separating Asynchronous Task Tests from Trigger Schedule Tests

A background task can be triggered in several ways: a user submits a request, a message arrives on a queue, or a `@Scheduled` schedule reaches its run time. Performing the work and deciding when to trigger it are two distinct responsibilities. If both are tested in the same test by waiting for the clock to reach the scheduled time, the test becomes slow, dependent on real time, and hard to diagnose when failing between business logic and scheduling.

In Spring, the business logic should be separated into a service that can be called directly, `@Async` or `TaskExecutor` should be used to test asynchronous execution, and the `@Scheduled` method should stay thin so registration and triggering can be tested separately. This separation lets business logic tests run without a scheduler, and scheduler tests run without executing the entire background job.

## Distinguishing three responsibilities

A background workflow typically has three parts:

| Part | Responsibility | Typical Spring mechanism |
|---|---|---|
| Business task | Performs the actual work: reading data, computing, updating state | Plain service, independent of schedules or threads |
| Async execution | Offloads work to another thread/executor and manages completion results | `@Async`, `TaskExecutor`, `CompletableFuture` |
| Schedule trigger | Determines when to request that the work run | `@Scheduled`, `TaskScheduler`, `Trigger` |

`TaskExecutor` and `TaskScheduler` solve two different problems. An executor executes a submitted task; a scheduler decides when to invoke a `Runnable` based on cron, fixed rate, fixed delay, or a `Trigger`. A scheduled method can call an async launcher and return quickly so the scheduler can continue managing subsequent triggers.

The processing flow is organized as follows:

```text
Cron / fixed delay
        |
        v
Scheduled method (@Scheduled)
        |
        v
Async launcher (@Async)
        |
        v
Business task service
        |
        v
Repository / external system
```

Business task tests call the service directly. Async execution tests call the launcher through the Spring proxy and wait for the `Future` to complete. Scheduler tests only verify that the schedule is registered and that firing the runnable invokes the launcher.

## Separating business logic from background annotations

Do not put all business logic inside a method that both carries `@Scheduled` and performs multiple queries and updates. Move the work into a plain service:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class ExpiredSessionCleanup {

    private final SessionRepository sessionRepository;

    ExpiredSessionCleanup(SessionRepository sessionRepository) {
        this.sessionRepository = sessionRepository;
    }

    @Transactional
    int removeExpiredSessions() {
        return sessionRepository.deleteExpiredSessions();
    }
}
```

This service does not know who calls it or when. It can be invoked from an HTTP handler, message listener, async launcher, scheduler, or unit test. The transaction boundary also sits at the business processing layer, so tests can verify repository behavior without waiting for a scheduler.

### Testing the business task directly

Test the business logic with JUnit and mocked dependencies:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ExpiredSessionCleanupTest {

    @Mock
    private SessionRepository sessionRepository;

    @InjectMocks
    private ExpiredSessionCleanup cleanup;

    @Test
    void removesExpiredSessions() {
        when(sessionRepository.deleteExpiredSessions()).thenReturn(3);

        int removed = cleanup.removeExpiredSessions();

        assertThat(removed).isEqualTo(3);
        verify(sessionRepository).deleteExpiredSessions();
    }
}
```

This test checks what actually needs to be right: the service calls the repository and returns the number of deleted records. It does not need `@EnableScheduling`, does not need `@EnableAsync`, and does not need to wait for a future moment in time. Business branches such as skipping unexpired records, handling invalid data, or rolling back on repository failure should also be tested at this layer.

If the task logic requires transactions or other Spring beans, use an appropriate test context for the service. Even then, keep the test independent of trigger timing; whether a transaction commits or rolls back is a separate responsibility that can be tested with data-layer integration tests.

## Offloading tasks to an executor with @Async

`@Async` marks a method to be invoked through an executor. Enable this feature with `@EnableAsync` and declare an explicitly named executor:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import java.util.concurrent.Executor;

@Configuration
@EnableAsync
class AsyncExecutionConfig {

    @Bean("cleanupExecutor")
    Executor cleanupExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("cleanup-");
        return executor;
    }
}
```

The launcher is only responsible for handing the execution request to the executor:

```java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

import java.util.concurrent.CompletableFuture;

@Component
class AsyncCleanupLauncher {

    private final ExpiredSessionCleanup cleanup;

    AsyncCleanupLauncher(ExpiredSessionCleanup cleanup) {
        this.cleanup = cleanup;
    }

    @Async("cleanupExecutor")
    public CompletableFuture<Integer> launch() {
        int removed = cleanup.removeExpiredSessions();
        return CompletableFuture.completedFuture(removed);
    }
}
```

When called through the Spring proxy, the executor runs the method body on a dedicated thread. With a `CompletableFuture<T>` return type, the caller can observe both the result and any exception once the work completes. With a `void` return type, exceptions cannot be returned to the caller; configure an `AsyncUncaughtExceptionHandler` if you need to handle exceptions thrown by async void methods.

`@Async` works through a proxy. Therefore, calling an `@Async` method from another method on the same instance (`this.launch()`) normally bypasses the proxy and does not create an async dispatch. Call the launcher through the Spring-injected bean.

## Testing async execution separately

Async tests should verify that the launcher is invoked through the proxy, the work is dispatched to the executor, and the result completes. No scheduler is needed in this test.

Example test configuration using a small executor with a deterministic thread name prefix and a mock collaborator:

```java
import static org.mockito.Mockito.mock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
class AsyncLauncherTestConfig {

    @Bean("cleanupExecutor")
    ThreadPoolTaskExecutor cleanupExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("cleanup-test-");
        return executor;
    }

    @Bean
    ExpiredSessionCleanup cleanup() {
        return mock(ExpiredSessionCleanup.class);
    }

    @Bean
    AsyncCleanupLauncher launcher(ExpiredSessionCleanup cleanup) {
        return new AsyncCleanupLauncher(cleanup);
    }
}
```

The test obtains the launcher from the application context, so the call passes through the Spring proxy:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringJUnitConfig(AsyncLauncherTestConfig.class)
class AsyncCleanupLauncherTest {

    @Autowired
    private AsyncCleanupLauncher launcher;

    @Autowired
    private ExpiredSessionCleanup cleanup;

    @Test
    void runsCleanupOnConfiguredExecutor() throws Exception {
        when(cleanup.removeExpiredSessions())
                .thenAnswer(invocation -> {
                    assertThat(Thread.currentThread().getName())
                            .startsWith("cleanup-test-");
                    return 3;
                });

        int removed = launcher.launch().get(2, TimeUnit.SECONDS);

        assertThat(removed).isEqualTo(3);
        verify(cleanup).removeExpiredSessions();
    }
}
```

`get(timeout, unit)` waits with a time bound and returns the result when the async task completes. If the task does not finish within the allowed time, the test fails instead of hanging indefinitely. Checking the thread name confirms the method ran on the designated executor. You can replace this with a `CountDownLatch` or a `CompletableFuture` completed by a collaborator when the test needs multi-step coordination.

Do not use `Thread.sleep()` to wait for tasks. Sleep only delays the test; it does not prove the work completed and can fail intermittently when CI is slow. Use a future, latch, or waiting library with a timeout to synchronize on a real condition.

### Testing exceptions in async tasks

For methods returning `CompletableFuture`, exceptions can be observed via the future:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.when;

when(cleanup.removeExpiredSessions())
        .thenThrow(new IllegalStateException("repository unavailable"));

CompletableFuture<Integer> future = launcher.launch();

assertThatThrownBy(() -> future.get(2, TimeUnit.SECONDS))
        .hasCauseInstanceOf(IllegalStateException.class);
```

When using `join()`, exceptions are typically wrapped in `CompletionException`; with `get()`, exceptions are wrapped in `ExecutionException`. Choose the assertion matching the wrapper returned by the API and check the actual cause.

If the launcher returns `void`, the caller has no future to await or receive exceptions from. In that case, use a latch/test observer or configure an `AsyncUncaughtExceptionHandler` to verify errors are handled per application policy.

## Keeping scheduled methods thin

A scheduled method should only decide that it is time to request the work to run. It should not contain all the business logic:

```java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
class CleanupSchedule {

    private final AsyncCleanupLauncher launcher;

    CleanupSchedule(AsyncCleanupLauncher launcher) {
        this.launcher = launcher;
    }

    @Scheduled(cron = "${cleanup.cron}")
    public void triggerCleanup() {
        launcher.launch();
    }
}
```

Declare the schedule in configuration:

```properties
cleanup.cron=0 0/15 * * * *
```

This example requests triggering every 15 minutes. `@EnableScheduling` enables processing of `@Scheduled` annotations. The scheduled method calls the launcher and returns; the actual work runs on `cleanupExecutor` thanks to `@Async`.

When the work can take longer than the schedule period, decide explicitly whether overlapping executions are allowed. If not, use a lock, job state, or appropriate coordination mechanism. Do not rely on assuming the scheduler will automatically wait for a `CompletableFuture` that the scheduled method ignored.

If async results or errors need tracking, the launcher can record job status or attach a `whenComplete(...)` callback. Define clearly how failures are recorded so a failed task is not lost just because the scheduled method already returned.

## Testing the scheduler without waiting for the real clock

Scheduler tests need to verify two things: Spring registers the task according to configuration, and when the runnable is triggered, the scheduled method calls the launcher. There is no need to actually wait 15 minutes or run a continuously ticking schedule executor.

One controllable approach is replacing `TaskScheduler` with a mock that records registered runnables. When Spring processes `@Scheduled(cron = ...)`, it calls the `schedule(Runnable, Trigger)` overload. The test can store the runnable and invoke it directly at a moment chosen by the test.

Example test configuration:

```java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ScheduledFuture;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.Trigger;
import org.springframework.scheduling.annotation.EnableScheduling;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class CapturedScheduledTasks {
    private final List<Runnable> tasks = new CopyOnWriteArrayList<>();

    void add(Runnable task) {
        tasks.add(task);
    }

    List<Runnable> all() {
        return List.copyOf(tasks);
    }
}

@Configuration
@EnableScheduling
class SchedulerTestConfig {

    @Bean
    CapturedScheduledTasks capturedScheduledTasks() {
        return new CapturedScheduledTasks();
    }

    @Bean
    TaskScheduler taskScheduler(CapturedScheduledTasks captured) {
        TaskScheduler scheduler = mock(TaskScheduler.class);
        when(scheduler.schedule(any(Runnable.class), any(Trigger.class)))
                .thenAnswer(invocation -> {
                    captured.add(invocation.getArgument(0));
                    return mock(ScheduledFuture.class);
                });
        return scheduler;
    }

    @Bean
    AsyncCleanupLauncher cleanupLauncher() {
        return mock(AsyncCleanupLauncher.class);
    }

    @Bean
    CleanupSchedule cleanupSchedule(AsyncCleanupLauncher launcher) {
        return new CleanupSchedule(launcher);
    }
}
```

The test initializes the context, verifies that the task was registered, and invokes the runnable manually:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.context.TestPropertySource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;

@SpringJUnitConfig(SchedulerTestConfig.class)
@TestPropertySource(properties = "cleanup.cron=0 0 * * * *")
class CleanupScheduleTest {

    @Autowired
    private CapturedScheduledTasks captured;

    @Autowired
    private AsyncCleanupLauncher launcher;

    @Test
    void registeredTriggerDelegatesToAsyncLauncher() {
        assertThat(captured.all()).hasSize(1);

        captured.all().get(0).run();

        verify(launcher).launch();
    }
}
```

This test does not run the real business task because the launcher is a mock. It only confirms that the scheduled runnable was registered and delegates to the launcher when triggered. That is the exact boundary to test at the scheduler layer.

In this example, the mock `TaskScheduler` only needs to support the cron overload `schedule(Runnable, Trigger)`. If the application uses `fixedRate`, `fixedDelay`, or another overload, capture the exact `TaskScheduler` method used by that configuration. Also ensure the test context has only one scheduler selected so Spring does not pick another scheduler.

## Testing cron expressions separately

When you need to verify the meaning of a cron expression, test it as a deterministic time rule rather than waiting for the scheduler to fire. Spring provides `CronExpression` to calculate the next execution from a known point in time:

```java
import java.time.ZonedDateTime;

import org.junit.jupiter.api.Test;
import org.springframework.scheduling.support.CronExpression;

import static org.assertj.core.api.Assertions.assertThat;

class CleanupCronExpressionTest {

    @Test
    void calculatesNextQuarterHour() {
        CronExpression cron = CronExpression.parse("0 0/15 * * * *");
        ZonedDateTime after = ZonedDateTime.parse("2030-01-01T10:07:00Z");

        assertThat(cron.next(after))
                .isEqualTo(ZonedDateTime.parse("2030-01-01T10:15:00Z"));
    }
}
```

This test checks the cron expression calculation against a fixed timestamp. If the `@Scheduled` annotation has a `zone` attribute, use `ZonedDateTime` in that timezone to verify behavior around day, month, or daylight saving boundaries. The cron expression and runnable registration are two separate concerns; they can be tested independently.

## Distinguishing fixedRate, fixedDelay, and cron

Scheduling modes do not mean the same thing:

| Configuration | How the next trigger is calculated | When to use |
|---|---|---|
| `fixedRate` | By the interval between the start times of consecutive runs | When a steady trigger cadence is desired |
| `fixedDelay` | Waits a fixed delay after the previous run finishes | When waiting an interval after completion is desired |
| `cron` | According to a calendar date/time expression | When running at specific clock/calendar points |

With an `@Async` launcher, the scheduled method may finish immediately after submitting the task to the executor. In that case, `fixedDelay` on the scheduled method measures the interval after the trigger method returns, not after the async business task finishes. If the requirement is to wait for the actual work to finish before starting the delay, coordinate the future or job state explicitly.

## Do not combine async and scheduler into a real-time test

An integration test can enable both `@EnableAsync` and `@EnableScheduling`, but the bulk of a test suite should not depend on real schedules. A test waiting for cron to fire and then asserting repository updates can fail because:

- The test started just after the cron tick passed and had to wait for the next cycle.
- Slow CI or a busy thread pool prevented the task from finishing before timeout.
- The task fired multiple times and the test could not tell which run produced the side effect.
- The cached test context kept the scheduler alive longer than the test method lifecycle.
- A bug in the business task was mistaken for a schedule failing to fire, or vice versa.

If an end-to-end smoke test for the whole flow is needed, use a short test schedule while still controlling the executor, enforcing a finite timeout, waiting on a specific completion signal, and cleaning up the context after the test. These should be just a few supplemental integration tests; most logic should be verified in the independent tests above.

## Avoiding common mistakes

| Symptom | Possible cause | How to handle |
|---|---|---|
| `@Async` runs synchronously | Missing `@EnableAsync`, self-invocation, or calling a manually constructed object instead of the Spring bean | Enable async support and call through the injected proxy |
| Test finishes before async task completes | Not waiting on future/latch | Use `Future#get(timeout)` or `CountDownLatch#await(timeout, ...)` |
| Test passes sometimes and fails other times | Using `Thread.sleep()` or relying on real schedules | Control executor/scheduler and wait for signals with timeouts |
| Scheduled method ran but business task is not done | The method only submitted work to an executor and returned | Await the future in a separate async test; track completion in production if needed |
| Scheduled task was not captured | Test mocked the wrong `TaskScheduler` overload | Capture the overload matching cron, fixed rate, or fixed delay |
| Multiple runs overlap | Task duration exceeds trigger period | Use a lock, job state, or overlap prevention policy |
| Async exception is lost | Method returns `void` or future was ignored | Return `CompletableFuture`, observe completion, or configure an async exception handler |
| Executor threads keep running after test | Executor was not shut down when context ended | Use a Spring bean with shutdown lifecycle and configure await termination appropriately |
| `fixedDelay` does not wait for async job completion | Scheduled method returns immediately after submitting task | Coordinate futures or use a synchronous model if delay must count after business completion |

## Recommended test matrix

| Test | What is verified | What does not need to run |
|---|---|---|
| Business service test | Business rules, repository calls, transaction behavior | Async executor and scheduler |
| Async launcher test | `@Async` proxy, executor, results, and exceptions | Cron or trigger timing |
| Scheduler registration test | `@Scheduled` is registered and runnable invokes launcher | Real repository and business task |
| Cron expression test | Next trigger time from a fixed reference timestamp | Thread pool and real clock |
| One smoke integration test (if needed) | Wiring components together in a real context | Should not replace the independent tests above |

When business tasks, async execution, and schedule triggers have clear boundaries, each test can control the exact conditions it needs. Business tests run fast and deterministically; async tests wait for completion with futures or latches; scheduler tests fire runnables on demand without waiting for real time. This isolates failures to the right layer and reduces the test suite's dependence on clocks, thread pools, and CI speed.
