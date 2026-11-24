# Controlling Executors and Background Tasks in Testing

When a Spring application offloads work to an executor or thread pool, the moment a task is launched and the moment it completes are two different points in time. A test that simply invokes a method and immediately checks the result often causes flaky failures: sometimes the task has already finished, while other times it is still waiting in the queue or executing on another thread.

Asynchronous testing requires an explicit synchronization mechanism. Wait for a completion signal using Future, CompletableFuture, CountDownLatch, or a tool such as Awaitility; set a finite timeout; and check both the errors and the results of the task. When you need to test logic independently of concurrency, you can replace the executor with a synchronous executor. When you need to verify true parallelism, use a bounded thread pool and synchronize tasks with a latch or barrier.

## 1. Distinguishing executors, thread pools, and background tasks

Spring provides the TaskExecutor abstraction so an application can hand a Runnable to an execution mechanism. Some commonly used interfaces and implementations:

| Component | Role |
|---|---|
| Executor | Standard Java abstraction with the execute(Runnable) method |
| TaskExecutor | Spring's executor abstraction, extending Java's task submission model |
| AsyncTaskExecutor | Supports submitting tasks and receiving a Future to track the result |
| ThreadPoolTaskExecutor | Spring executor based on a thread pool, with configurable thread count, queue, and rejection policy |
| SyncTaskExecutor | Runs tasks immediately on the calling thread; useful when you want to test the processing flow deterministically |
| SimpleAsyncTaskExecutor | Creates a thread for tasks according to configuration; not a thread pool that reuses threads in the same way as ThreadPoolTaskExecutor |

A thread pool typically has three components to pay attention to:

- **Worker threads:** the number of tasks that can run concurrently.
- **Queue:** tasks waiting when workers are busy.
- **Rejection policy:** behavior when no thread or queue slot is left to accept a task.

Basic flow:

~~~text
Thread calling service
       |
       | submit / execute
       v
Executor
       |
       +---- worker free? ---- Yes ----> run task
       |                         |
       |                         +----> complete / signal
       |
       +---- No ----> put in queue
                            |
                            v
                       worker takes task
                            |
                            v
                       run and complete
~~~

Tests need to determine what they are verifying: whether the task was submitted, whether it runs on another thread, whether multiple tasks can run concurrently, what the final result is, or how the executor handles a full queue. A single assertion after the call is usually not enough to prove these behaviors.

## 2. Configuring an executor for @Async

@Async requires Spring to enable async method execution with @EnableAsync. Calls need to pass through the Spring proxy so the interceptor hands the method body off to the executor.

Configuration example:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {

    @Bean("applicationTaskExecutor")
    public ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("background-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }
}
~~~

Service:

~~~java
@Service
public class ReportService {

    @Async("applicationTaskExecutor")
    public CompletableFuture<String> generate(String reportId) {
        String result = doGenerate(reportId);
        return CompletableFuture.completedFuture(result);
    }

    private String doGenerate(String reportId) {
        return "report-" + reportId + "-ready";
    }
}
~~~

When calling generate(...) through the injected Spring bean, the caller receives a CompletableFuture. The method body is run by the executor with qualifier applicationTaskExecutor. The executor name in @Async("...") helps explicitly choose which pool to use when the application has multiple executors.

### 2.1. Why does self-invocation make async tests wrong?

In the default proxy mode, calling an @Async method from another method in the same object does not pass through the proxy:

~~~java
public void start() {
    generate("monthly"); // internal call, does not go through async proxy
}
~~~

This is a direct call on this, so the @Async interceptor is not triggered. When testing, invoke the async method through the Spring-injected bean or move the task into a separate bean. Do not create the instance manually with new if the goal is to verify that Spring's async proxy works.

## 3. Verifying task completion with CompletableFuture

For tasks that produce a result, CompletableFuture is a direct way to synchronize the test with execution completion:

~~~java
@SpringJUnitConfig({AsyncTestConfiguration.class, ReportService.class})
class ReportServiceTest {

    @Autowired
    ReportService reportService;

    @Test
    void completesReportOnBackgroundThread() throws Exception {
        CompletableFuture<String> future =
                reportService.generate("monthly");

        String result = future.get(2, TimeUnit.SECONDS);

        assertThat(result).isEqualTo("report-monthly-ready");
    }
}
~~~

get(timeout, unit) waits for completion up to a maximum duration. If the task does not complete, the test fails with a TimeoutException instead of hanging indefinitely. If the task completes exceptionally, get(...) throws ExecutionException; you can inspect the root cause via getCause().

To check the execution thread, return the thread name in the result or record it using a thread-safe probe:

~~~java
@Async("testExecutor")
public CompletableFuture<String> runAndReportThread() {
    return CompletableFuture.completedFuture(
            Thread.currentThread().getName());
}
~~~

Test:

~~~java
String callerThread = Thread.currentThread().getName();
String workerThread =
        worker.runAndReportThread().get(2, TimeUnit.SECONDS);

assertThat(workerThread).startsWith("test-async-");
assertThat(workerThread).isNotEqualTo(callerThread);
~~~

The thread name prefix should be configured specifically for the test executor so assertions do not depend on default JVM thread names or the CI environment.

## 4. Verifying void tasks with CountDownLatch

An @Async method returning void has no future for the caller to retrieve a result. A test can use a CountDownLatch to receive a signal that the task has reached the verification point:

~~~java
@Component
public class NotificationWorker {

    @Async("testExecutor")
    public void send(
            String recipient,
            CountDownLatch completed,
            AtomicReference<String> executedThread) {

        try {
            executedThread.set(Thread.currentThread().getName());
            // Perform simulated notification sending work.
        }
        finally {
            completed.countDown();
        }
    }
}
~~~

Test:

~~~java
CountDownLatch completed = new CountDownLatch(1);
AtomicReference<String> executedThread = new AtomicReference<>();

notificationWorker.send("test@example.invalid",
        completed, executedThread);

assertThat(completed.await(2, TimeUnit.SECONDS)).isTrue();
assertThat(executedThread.get()).startsWith("test-async-");
~~~

await(...) both waits for the task and enforces a timeout. Using finally to decrement the latch ensures the test does not wait indefinitely if the task body exits early due to an exception. In real tests, prefer passing a fake collaborator or recording state through a thread-safe probe instead of adding too many testing objects into the business API.

Do not use Thread.sleep(...) to wait for a task. Sleep only guesses that the task has had enough time to run; it does not prove the task has completed and can fail when CI is under heavy load.

## 5. Configuring a dedicated executor for tests

Tests should control the thread count, queue, and thread name so behavior is repeatable. A dedicated executor can be provided in a test configuration:

~~~java
@TestConfiguration
@EnableAsync
public class AsyncTestConfiguration {

    @Bean("testExecutor")
    public ThreadPoolTaskExecutor testExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("test-async-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);
        return executor;
    }
}
~~~

Test service using the qualifier:

~~~java
@Component
public class BackgroundWorker {

    @Async("testExecutor")
    public CompletableFuture<String> execute(String value) {
        return CompletableFuture.completedFuture(
                value + "@" + Thread.currentThread().getName());
    }
}
~~~

Tests can use @SpringJUnitConfig or @Import(AsyncTestConfiguration.class) in the test context to load the configuration. Spring manages the executor bean lifecycle and invokes lifecycle callbacks when the context initializes or closes.

If a project already has a production executor with a complex configuration, it is not necessary to use the production configuration for every unit test. A test executor can be smaller, have a bounded queue, and use easily recognizable thread names. For integration tests of the production configuration, load the actual production bean and verify the characteristics that need to be confirmed.

## 6. Using SyncTaskExecutor to test logic independently of concurrency

Not every test that calls @Async code needs to create real threads. When you want to check mapping, validation, or task body logic without caring about concurrency, you can provide a synchronous executor:

~~~java
@TestConfiguration
@EnableAsync
public class SynchronousAsyncTestConfiguration {

    @Bean("testExecutor")
    public TaskExecutor testExecutor() {
        return new SyncTaskExecutor();
    }
}
~~~

In that case the @Async proxy is still invoked, but the executor runs the Runnable immediately on the calling thread. The test can observe the result right away without waiting for a thread pool.

This approach is suitable for testing simple, deterministic logic. It does not prove that the task runs on another thread, nor does it test queueing, rejection, race conditions, or concurrent execution capability. Keep at least one separate group of tests using a real executor for concurrency behaviors the application relies on.

Do not replace the production executor with SyncTaskExecutor in all tests if an important system requirement is isolating requests from background work. Doing so causes tests to skip the very asynchronous behavior that needs protection.

## 7. Testing that multiple tasks truly run in parallel

To confirm a thread pool can run multiple tasks concurrently, use a latch as a synchronization barrier. Each task signals that it has started, then waits for the test to allow it to continue:

~~~java
@Async("testExecutor")
public CompletableFuture<Void> waitAtBarrier(
        CountDownLatch started,
        CountDownLatch release) {

    started.countDown();
    try {
        if (!release.await(2, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Test did not release workers");
        }
        return CompletableFuture.completedFuture(null);
    }
    catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Worker interrupted", ex);
    }
}
~~~

Test with a two-worker pool:

~~~java
CountDownLatch started = new CountDownLatch(2);
CountDownLatch release = new CountDownLatch(1);

try {
    CompletableFuture<Void> first =
            worker.waitAtBarrier(started, release);
    CompletableFuture<Void> second =
            worker.waitAtBarrier(started, release);

    assertThat(started.await(2, TimeUnit.SECONDS)).isTrue();

    release.countDown();
    first.get(2, TimeUnit.SECONDS);
    second.get(2, TimeUnit.SECONDS);
}
finally {
    release.countDown();
}
~~~

If the pool has only one worker and the first task is waiting on release, the second task cannot signal that it has started before the test opens the latch. With a two-worker pool, both can reach the barrier. finally always opens the latch to avoid leaving a test thread waiting if an assertion fails.

Do not test parallelism by comparing log order or assuming task A always finishes before task B. The scheduler can change the order. Check the essential property instead, such as the number of tasks that have started together, the limit on active workers, or the final result of all tasks.

## 8. Testing queues and rejected tasks

A thread pool with a bounded queue needs a policy when it cannot accept more work. If both the queue and the worker count are full, the executor can reject the task. A test can create a small pool to verify this behavior in a controlled way:

~~~java
ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(1);
executor.setMaxPoolSize(1);
executor.setQueueCapacity(0);
executor.setRejectedExecutionHandler(
        new ThreadPoolExecutor.AbortPolicy());
executor.initialize();

CountDownLatch started = new CountDownLatch(1);
CountDownLatch release = new CountDownLatch(1);

try {
    executor.execute(() -> {
        started.countDown();
        try {
            release.await();
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }
    });

    assertThat(started.await(2, TimeUnit.SECONDS)).isTrue();

    assertThatThrownBy(() -> executor.execute(() -> {}))
            .isInstanceOf(TaskRejectedException.class);
}
finally {
    release.countDown();
    executor.shutdown();
}
~~~

Here the pool has only one worker and the queue has no waiting slots. The first task keeps the worker busy; the second task is rejected. AbortPolicy throws an error when a task cannot be accepted, and Spring's ThreadPoolTaskExecutor represents the rejection via TaskRejectedException.

Other policies may run the task on the calling thread or discard the task. Test the exact policy configured by the application. In particular, CallerRunsPolicy can cause the request thread to run background work when the pool is overloaded; that changes latency and can make the behavior appear synchronous.

Queue/rejection tests should use a small pool created specifically inside the test and always release latches and shut down the executor in finally. Do not exhaust the shared pool of the application context to test rejection because that can affect other tests.

## 9. Verifying exceptions from background tasks

How errors are observed depends on the return type of the async method.

### 9.1. Methods returning Future or CompletableFuture

If a method returns CompletableFuture, exceptions can be observed via the future:

~~~java
@Async("testExecutor")
public CompletableFuture<String> executeAndFail() {
    throw new IllegalStateException("background failure");
}
~~~

Test:

~~~java
CompletableFuture<String> future = worker.executeAndFail();

assertThatThrownBy(() -> future.get(2, TimeUnit.SECONDS))
        .isInstanceOf(ExecutionException.class)
        .hasCauseInstanceOf(IllegalStateException.class);
~~~

You can use join() and check CompletionException, but get(timeout, unit) is useful when the test needs a bounded wait time.

### 9.2. Methods returning void

With @Async void, the caller does not receive a future to observe exceptions. Spring forwards exceptions to AsyncUncaughtExceptionHandler. You can configure a handler in AsyncConfigurer or the corresponding async configuration:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration implements AsyncConfigurer {

    @Override
    public AsyncUncaughtExceptionHandler getAsyncUncaughtExceptionHandler() {
        return (exception, method, params) -> {
            // Log, emit metrics, or forward to an error-handling mechanism.
        };
    }
}
~~~

In tests, you can provide a fake handler that records exceptions into a BlockingQueue or CountDownLatch, then wait and assert on the exception. Avoid checking only console logs because logs are not a reliable communication channel between the task and the test.

## 10. Do not use sleep to synchronize tests

Thread.sleep(...) often creates flaky tests:

~~~java
worker.execute();
Thread.sleep(500);
assertThat(repository.findResult()).isNotNull();
~~~

The test above merely assumes 500 ms is enough for the task to finish. When CI is busy, the task might not have run yet; when the machine is fast, the test wastes waiting time. Sleep also does not tell whether the task failed or was never scheduled.

Replace it with a completion signal:

~~~java
CompletableFuture<Result> future = worker.execute();
Result result = future.get(2, TimeUnit.SECONDS);
assertThat(result).isNotNull();
~~~

Or use a latch for void methods:

~~~java
assertThat(completed.await(2, TimeUnit.SECONDS)).isTrue();
assertThat(resultReference.get()).isEqualTo(expected);
~~~

Awaitility is also useful when a test waits for a condition updated across multiple components:

~~~java
await()
        .atMost(Duration.ofSeconds(2))
        .untilAsserted(() ->
                assertThat(repository.findById(id)).isPresent());
~~~

Awaitility fits when a test does not have a direct future or latch and needs to wait for an observable state. Set a finite timeout and a reasonable polling interval; do not use forever() in tests.

## 11. Thread safety and shared data in tests

When multiple tasks run concurrently, shared mutable variables need protection. ArrayList, HashMap, and regular primitive variables are not automatically safe when multiple threads write concurrently.

Common choices:

- AtomicInteger, AtomicReference for a single value requiring atomic updates.
- ConcurrentHashMap for maps accessed concurrently.
- BlockingQueue to pass results from workers back to the test thread.
- CountDownLatch, CyclicBarrier, or Phaser to coordinate execution timing.
- Concurrent collections suited to the actual operations.

Example collecting results from multiple workers:

~~~java
BlockingQueue<String> results = new LinkedBlockingQueue<>();
CountDownLatch completed = new CountDownLatch(3);

for (String id : List.of("A", "B", "C")) {
    executor.execute(() -> {
        try {
            results.add(process(id));
        }
        finally {
            completed.countDown();
        }
    });
}

assertThat(completed.await(2, TimeUnit.SECONDS)).isTrue();
assertThat(results).containsExactlyInAnyOrder(
        "done-A", "done-B", "done-C");
~~~

If completion order is not part of the contract, use an order-independent assertion such as containsExactlyInAnyOrder. Only assert order when the system genuinely must guarantee that order.

## 12. Controlling shared contexts and executors across tests

Spring TestContext can cache an ApplicationContext and reuse it across multiple tests. An executor that is a singleton bean in the context can be shared by multiple tests. This matters when:

- A test actively shuts down the executor.
- A test modifies the configuration or state of the executor.
- Tests concurrently submit tasks to the same queue.
- A test holds a latch or barrier that keeps workers occupied.
- A test uses a mutable mock or probe shared across multiple methods.

Do not call shutdown() on an executor injected from the Spring context inside individual test methods; Spring manages that bean's lifecycle. If you need to test shutdown or rejection, create a separate executor inside the test and close it yourself.

For tests run in parallel by JUnit Jupiter, you can use @Execution(ExecutionMode.CONCURRENT) when tests are independent and thread-safe. If multiple tests must share a stateful resource, use @ResourceLock to serialize access to that resource:

~~~java
@Execution(ExecutionMode.CONCURRENT)
class IndependentAsyncTests {
    // Each test uses its own data and does not modify shared state.
}

@ResourceLock("shared-system-property")
class TestsUsingSharedSystemProperty {
    // Tests sharing this property are coordinated by the resource lock.
}
~~~

JUnit parallel execution must be enabled in the test engine configuration. Adding the @Execution annotation alone does not mean the entire project has parallel execution enabled.

Do not use @DirtiesContext as the default way to fix every contention problem. Only mark the context dirty when a test genuinely alters configuration or state in a way that prevents safe context reuse. For executors, the better approach is usually isolating resources, making tests independent, and letting Spring manage the lifecycle.

## 13. Propagating context across threads with TaskDecorator

Thread-bound information such as the MDC logging context or certain ThreadLocals does not automatically transfer to worker threads. If background tasks need that context, the application can configure a TaskDecorator to capture the context at submission time and restore it in the worker:

~~~java
executor.setTaskDecorator(task -> {
    Map<String, String> contextMap = MDC.getCopyOfContextMap();

    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            if (contextMap == null) {
                MDC.clear();
            }
            else {
                MDC.setContextMap(contextMap);
            }
            task.run();
        }
        finally {
            if (previous == null) {
                MDC.clear();
            }
            else {
                MDC.setContextMap(previous);
            }
        }
    };
});
~~~

If the application has a TaskDecorator, verify that context is propagated to the worker and cleaned up after the task finishes so data does not leak between tasks reusing the thread. Tests should create distinct contexts for tasks and verify that the worker reads each task's corresponding value.

Do not assume every context can be copied with TaskDecorator. Security context, transaction context, and request context have their own rules. A thread-bound transaction does not automatically transfer to a worker; if a task needs a transaction, open an appropriate transaction inside the task. For request-scoped objects, avoid retaining references after the request ends.

## 14. Shutdown and in-flight tasks

An executor is a lifecycle-managed resource. When the application context closes, Spring destroys the executor bean, and ThreadPoolTaskExecutor provides options such as:

- setWaitForTasksToCompleteOnShutdown(true): wait for accepted tasks to complete during shutdown.
- setAwaitTerminationSeconds(...): limit the waiting time before completing shutdown.
- setWaitForTasksToCompleteOnShutdown(false): do not wait for tasks to complete according to graceful shutdown waiting configuration.

Integration tests can verify shutdown behavior with a dedicated executor, a task holding a latch, and a configured wait timeout. Always release the latch in finally so workers are not left hanging if a test assertion fails.

Do not assume graceful shutdown guarantees tasks survive a process or machine crash. A thread pool holds tasks in memory; if work must be redelivered after a restart, a durable queue or business state persistence mechanism is required.

## 15. Choosing a test strategy by goal

| Goal to verify | Suitable strategy |
|---|---|
| Test task body logic without needing real threads | Use SyncTaskExecutor in tests |
| Wait for the result of an async task | Return CompletableFuture and use get(timeout) |
| Wait for a void task to complete | CountDownLatch or a thread-safe completion signal |
| Verify a task ran on a specific executor | Thread name prefix or a thread-recording probe |
| Verify multiple tasks run concurrently | Pool with multiple workers combined with a latch/barrier |
| Test a full queue or rejected task | Dedicated test executor with small pool and queue |
| Verify exceptions from an async method with a result | Assert the future completes exceptionally |
| Verify exceptions from a void async method | Record via AsyncUncaughtExceptionHandler |
| Wait for state updated across multiple components | Awaitility with a finite timeout |
| Verify application cleans up executor | Lifecycle integration test with dedicated executor or controlled context closure |

## 16. Checklist for testing an executor

Before finalizing tests, clearly establish:

1. Is the test verifying task logic, dispatching, or parallel execution capability?
2. Is the executor created specifically for the test or managed by Spring in the context?
3. Is there a mechanism to confirm the task started and completed?
4. Do all wait operations have a finite timeout?
5. Is there a path for the test to observe exceptions?
6. Are shared variables thread-safe?
7. Does the test depend unnecessarily on execution order?
8. Are latches, barriers, and dedicated executors released/closed in finally?
9. Does the test accidentally shut down or exhaust the shared singleton executor?
10. When testing @Async, does the call go through the Spring proxy?

Controlling executors in tests does not mean forcing every task to run synchronously. Use a synchronous executor when you only need to check logic; use an explicitly configured thread pool when you need to test dispatching, concurrency, queueing, or rejection. Combining completion signals, finite timeouts, and thread-safe data keeps background tests reliable and accurately reflects the behavior the application must guarantee.
