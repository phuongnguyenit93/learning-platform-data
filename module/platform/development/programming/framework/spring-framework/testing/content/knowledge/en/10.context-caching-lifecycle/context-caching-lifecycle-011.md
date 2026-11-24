# Closing the Context, Background Tasks, and In-Use Resources

An `ApplicationContext` does not merely hold beans for injection. In a running Spring application, beans can also own connection pools, HTTP clients, message consumers, thread pools, schedulers, file handles, or sockets. When the context closes, these components must stop in an appropriate order so the application no longer accepts new work, running tasks have a chance to finish, and resources are released safely.

This is especially important in integration testing. The TestContext Framework can cache and reuse a context across multiple test classes. When a test marks the context dirty or closes a context directly, Spring must destroy beans and the resources they manage. If background tasks keep running or beans spawn unmanaged threads, subsequent tests can fail intermittently, hold network ports open, write data after the test has ended, or prevent the test process from exiting.

## 1. Lifecycle of `ApplicationContext`

An `ApplicationContext` is typically created when the application starts and exists until the application stops or the test framework evicts the context from the cache. The general steps when closing a context include:

1. The context transitions to a closing state and publishes `ContextClosedEvent`.
2. Spring instructs beans participating in lifecycle mechanisms to stop operating.
3. Spring invokes destruction callbacks on managed singleton beans.
4. The bean factory closes and the context releases internal structures.

During shutdown, Spring coordinates with `LifecycleProcessor` to stop `Lifecycle`/`SmartLifecycle` beans, then destroys singleton beans. As a result, components receiving work can stop before the dependencies they use are closed.

A context can be closed directly via `ConfigurableApplicationContext.close()`:

```java
ConfigurableApplicationContext context =
        new AnnotationConfigApplicationContext(AppConfiguration.class);

try {
    MyService service = context.getBean(MyService.class);
    service.performWork();
} finally {
    context.close();
}
```

For a context created in a standalone application, a shutdown hook can be registered so the JVM instructs Spring to close the context when the process exits:

```java
ConfigurableApplicationContext context =
        new AnnotationConfigApplicationContext(AppConfiguration.class);
context.registerShutdownHook();
```

A shutdown hook handles closing the context during normal JVM shutdown. It does not replace lifecycle management in long-running applications, and does not guarantee cleanup when the process is forcibly killed or the machine shuts down abruptly.

## 2. Bean Destruction Mechanisms

Spring provides multiple ways for beans to release resources when the context closes. You can use annotations, interfaces, or destroy method declarations in bean definitions.

### 2.1. `@PreDestroy`

`@PreDestroy` marks a method invoked during the bean destruction phase:

```java
@Component
class LocalCache {
    private final Map<String, String> entries = new ConcurrentHashMap<>();

    @PreDestroy
    void clear() {
        entries.clear();
    }
}
```

This is a common way to close clients, clear internal resources, or record shutdown state. In modern Spring Framework, the annotation belongs to the Jakarta namespace (`jakarta.annotation.PreDestroy`), so the project needs the appropriate annotation dependency if the runtime does not supply it.

Cleanup methods should be short, safe to invoke, and independent of any specific test method. Avoid letting exceptions in cleanup mask the original test failure; when releasing multiple resources, attempt to close all of them and log errors appropriately.

### 2.2. `DisposableBean`

A bean can implement `DisposableBean` and define `destroy()`:

```java
class LegacySocketClient implements DisposableBean {
    private final Socket socket;

    LegacySocketClient(Socket socket) {
        this.socket = socket;
    }

    @Override
    public void destroy() throws IOException {
        socket.close();
    }
}
```

Spring calls `destroy()` when destroying managed singleton beans. This couples the class directly to Spring APIs, so `@PreDestroy` or a destroy method on the bean definition usually keeps domain classes less dependent on Spring.

### 2.3. Declaring `destroyMethod` on `@Bean`

For third-party library classes that we cannot modify, you can declare the closing method on `@Bean`:

```java
@Configuration
class ClientConfiguration {
    @Bean(destroyMethod = "close")
    ExternalClient externalClient() {
        return new ExternalClient();
    }
}
```

When the context closes, Spring calls `close()` on the bean. You can specify `shutdown` or a cleanup method matching the library's API:

```java
@Bean(destroyMethod = "shutdown")
MessageProducer messageProducer() {
    return new MessageProducer();
}
```

Spring has a mechanism to infer common destroy methods like `close` or `shutdown` for beans declared via `@Bean`, yet an explicit declaration makes resource management responsibility clear to readers. When a library has no cleanup method, you can use `destroyMethod = ""` to disable automatic inference if needed.

### 2.4. Comparing Cleanup Approaches

| Mechanism | How it is declared | Appropriate when |
|---|---|---|
| `@PreDestroy` | Annotation on a bean method | You can edit the class and want standard Jakarta callbacks |
| `DisposableBean` | Implement `destroy()` | The bean integrates directly with Spring lifecycle |
| `@Bean(destroyMethod = ...)` | Declared on a bean factory method | Managing third-party libraries or choosing a cleanup method |
| `Lifecycle` / `SmartLifecycle` | Implement `stop()` or `stop(Runnable)` | The bean needs a start/stop flow and coordination with other components |
| `ContextClosedEvent` | Listener receiving context close event | Reacting to a context-wide event or recording shutdown state |

There is no need to implement multiple cleanup mechanisms for the same resource if they might close it twice. Identify a single owner for closing and make the cleanup operation safe when invoked according to the actual lifecycle.

## 3. Bean Destruction Order and Dependency Relationships

If bean A depends on bean B, Spring must destroy A before B so A can still use B during cleanup. For example, a message consumer depends on a connection factory; the consumer must stop and close its subscription before the connection factory is closed.

```java
@Configuration
class MessagingConfiguration {
    @Bean(destroyMethod = "close")
    BrokerConnection brokerConnection() {
        return new BrokerConnection();
    }

    @Bean(destroyMethod = "close")
    MessageConsumer messageConsumer(BrokerConnection connection) {
        return connection.createConsumer();
    }
}
```

Spring learns dependency relationships through `@Bean` parameters and bean creation. When destroying singletons, dependent beans are released before the dependencies they require. Declare dependencies via constructors or `@Bean` parameters instead of looking up beans via a static registry; explicit relationships help Spring manage lifecycle ordering more accurately.

If a bean starts background work without declaring a dependency on the resource that the work uses, Spring may not know the required order. Design the bean graph to express relationships clearly or use `SmartLifecycle` to coordinate start/stop.

## 4. `Lifecycle` and `SmartLifecycle`

`Lifecycle` provides `start()`, `stop()`, and `isRunning()`. Beans implementing this interface can participate in the context lifecycle:

```java
class MessageListenerContainer implements Lifecycle {
    private boolean running;

    @Override
    public void start() {
        running = true;
        // Start receiving messages.
    }

    @Override
    public void stop() {
        // Stop receiving messages and release resources.
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}
```

`SmartLifecycle` extends `Lifecycle`, adding auto-startup, phase-based ordering, and a callback to signal completion of asynchronous stopping:

```java
class BackgroundConsumer implements SmartLifecycle {
    private volatile boolean running;

    @Override
    public void start() {
        running = true;
        // Start worker or register consumer.
    }

    @Override
    public void stop(Runnable callback) {
        running = false;
        // Stop accepting new work, wait for in-flight work to finish.
        callback.run();
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 100;
    }
}
```

In the example, `callback.run()` is only called after the bean has finished stopping. If stopping needs to wait for workers, the callback must be invoked on the actual completion path after workers finish; calling the callback immediately after issuing a stop command leads Spring to believe the bean has stopped while resources are still in use.

### 4.1. Phases Control Start/Stop Ordering

`SmartLifecycle` uses phases to order beans. On startup, lower phases start first; on shutdown, the order reverses, so higher phases stop first.

This is useful when a consumer needs a connection factory:

1. On startup, the connection factory must be ready before the consumer.
2. On shutdown, the consumer must stop before the connection factory closes.

You can assign a higher phase to the consumer and a lower phase to the connection factory. Use dependency injection to express bean relationships, and use phases when coordinating lifecycle components whose order cannot be fully inferred from the dependency graph.

Beans in the same phase may be processed in groups by the lifecycle processor. Do not rely on class declaration order or component scan order to control shutdown.

### 4.2. `stop(Runnable)` and Asynchronous Stopping

A worker may need time to finish a message currently being processed. `SmartLifecycle.stop(Runnable callback)` allows a bean to stop asynchronously and report back once complete:

```java
@Override
public void stop(Runnable callback) {
    acceptingMessages = false;
    workerExecutor.shutdown();

    Thread waiter = new Thread(() -> {
        try {
            if (!workerExecutor.awaitTermination(10, TimeUnit.SECONDS)) {
                workerExecutor.shutdownNow();
            }
        } catch (InterruptedException exception) {
            workerExecutor.shutdownNow();
            Thread.currentThread().interrupt();
        } finally {
            callback.run();
        }
    }, "consumer-shutdown-waiter");
    waiter.start();
}
```

This illustrates the completion callback; in a real application, use a managed executor or lifecycle mechanism to perform the wait instead of creating an ad-hoc thread. Ensure every termination path invokes the callback exactly once, even when the worker encounters an error or times out.

## 5. Managing Thread Pools With `TaskExecutor`

Spring provides `TaskExecutor` so applications submit tasks to a container-managed executor. `ThreadPoolTaskExecutor` is a common implementation:

```java
@Configuration
@EnableAsync
class AsyncConfiguration {
    @Bean
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("app-worker-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }
}
```

`ThreadPoolTaskExecutor` is managed by Spring as a bean and has lifecycle cleanup. Two notable settings:

- `setWaitForTasksToCompleteOnShutdown(true)` instructs the executor to wait for accepted tasks to complete during shutdown according to the executor's policy.
- `setAwaitTerminationSeconds(10)` sets the wait interval for termination before shutdown proceeds.

The wait timeout must suit the workload and the application's shutdown limits. If tasks can hang indefinitely, waiting indefinitely will prevent the context from finishing shutdown; if the timeout is too short, tasks may be interrupted while writing data or releasing resources.

### 5.1. `@Async` and In-Flight Tasks

`@Async` dispatches calls to an executor instead of running on the original calling thread:

```java
@Service
class ReportService {
    @Async("applicationTaskExecutor")
    public CompletableFuture<Report> generateAsync(ReportCommand command) {
        Report report = generate(command);
        return CompletableFuture.completedFuture(report);
    }
}
```

When the context closes, the executor must stop accepting new tasks and handle running tasks per its shutdown policy. Do not assume calling `close()` on the context automatically completes all background work in every configuration. Configure the executor and write tests verifying the appropriate wait or cancellation policy.

An important note: `@Async` works through a Spring proxy. Calling an async method from another method in the same instance (self-invocation) usually bypasses the proxy and may run synchronously. If a test does not observe tasks being submitted to the executor, inspect how the bean is invoked and the `@EnableAsync` configuration.

### 5.2. Tasks Rejected During Shutdown

Once the executor begins shutting down, submitting new tasks may be rejected. The application should handle `TaskRejectedException` or the corresponding exception, depending on the executor and abstraction used.

Do not submit new work from `@PreDestroy` to the very executor being shut down unless a policy allows it. Doing so can cause a shutdown loop or rejected tasks. If a final step must complete, perform it in a clearly ordered lifecycle stop step and ensure dependencies remain active.

## 6. Managing Schedulers and Periodic Tasks

`@Scheduled` registers methods to run on a schedule. A scheduler can continue waking up tasks while the context is shutting down if its lifecycle is not managed properly.

```java
@Configuration
@EnableScheduling
class SchedulingConfiguration {
    @Bean
    ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(2);
        scheduler.setThreadNamePrefix("scheduled-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(10);
        return scheduler;
    }
}
```

A Spring-managed scheduler can be closed via bean lifecycle. On shutdown, the application needs to stop scheduling new runs, handle or cancel already scheduled runs according to the chosen policy, and wait for running tasks to finish.

With custom schedulers, check implementation policies such as continuing periodic tasks after shutdown or executing scheduled delayed tasks. Do not assume every `ScheduledExecutorService` behaves identically.

### 6.1. Do Not Use `Thread.sleep` to Test Schedulers

Testing schedulers with fixed sleeps is usually slow and flaky. Prefer:

- Using a controllable test scheduler if provided by the framework.
- Using a latch/future to wait for the task to actually execute with a timeout.
- Extracting business logic out of `@Scheduled` methods to unit test the logic directly.
- Verifying that the scheduler stopped via lifecycle or resource state instead of waiting a long interval hoping no next run occurs.

## 7. Resources Owned by Beans

A bean can own resources that, if left unclosed, leak sockets, file descriptors, threads, or connections. Common examples:

| Resource | Action needed on shutdown |
|---|---|
| JDBC connection pool / datasource | Stop issuing new connections and close the pool |
| HTTP client with connection pool | Close the client/pool and release the event loop if owned by the client |
| Kafka/JMS producer or consumer | Stop receiving messages, flush if needed, close client |
| File or stream | Flush data to preserve, then close stream |
| Socket/server | Stop accepting new connections and close socket |
| Executor/scheduler | Stop accepting tasks, wait for or cancel tasks per policy, then release threads |
| Cache or registry | Stop access and release internal resources if any |

A resource should have one bean responsible for owning and closing it. Other beans use it via dependency injection. Avoid letting multiple beans call close on a shared object without clear ownership rules.

### 7.1. `AutoCloseable` and try-with-resources

For local resources inside a single test or operation, `try-with-resources` is usually simplest:

```java
@Test
void readsFileAndClosesStream() throws IOException {
    try (InputStream input = Files.newInputStream(testFile)) {
        assertThat(input.read()).isNotEqualTo(-1);
    }
}
```

For resources with a context-wide lifecycle, register them as beans and declare a destroy method:

```java
@Configuration
class FileClientConfiguration {
    @Bean(destroyMethod = "close")
    FileClient fileClient() {
        return new FileClient();
    }
}
```

Choose the ownership scope based on actual lifetime: resources used only in one test should be closed in the test; resources shared across the context should be managed by Spring until the context closes.

## 8. `ContextClosedEvent` and Reacting to Shutdown

Spring publishes `ContextClosedEvent` when the context begins closing. Beans can listen to this event:

```java
@Component
class ShutdownAuditListener {
    @EventListener
    void onContextClosed(ContextClosedEvent event) {
        // Record that the context began closing.
    }
}
```

The event is suitable for application-wide reactive behavior, such as logging shutdown or signaling a management component. For managing the lifecycle of workers, executors, or resources, `SmartLifecycle`, destroy callbacks, or bean ownership usually express responsibility more directly.

Do not assume an asynchronous listener will finish before the context closes. If the listener uses `@Async`, it depends on an executor that is shutting down. Critical cleanup steps should run synchronously or be managed by lifecycle callbacks with completion waiting.

## 9. Closing the Context in Integration Tests

The Spring TestContext Framework caches `ApplicationContext` instances to avoid restarting the same configuration for each test class. Consequently, a context's lifetime is usually longer than a single test method and may span multiple test classes.

### 9.1. Do Not Manually Close a Cached Context Inside a Test Method

If a test injects `ApplicationContext` and calls `close()` directly, the Spring TestContext cache may still hold a reference to the closed context. The next test class with the same cache key could retrieve a context that is no longer active.

When a test dirties the context and needs Spring to evict it from the cache, use `@DirtiesContext`:

```java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ContextShutdownIntegrationTest {
    // Test mutates context-level state and requests closure after the class.
}
```

`@DirtiesContext` marks the context dirty so the TestContext Framework removes it from the cache and closes it at the appropriate time. Method/class modes let you choose before or after a method/class.

Do not use `@DirtiesContext` merely to delete records in a database or messages in a broker. Use rollback, uniquely identified data, or corresponding resource cleanup.

### 9.2. Verifying Destroy Callbacks

You can use a test bean that records closure to verify Spring invokes cleanup when the context closes:

```java
class CloseTracker {
    private boolean closed;

    void close() {
        closed = true;
    }

    boolean isClosed() {
        return closed;
    }
}

@Configuration
class CloseTrackerConfiguration {
    @Bean(destroyMethod = "close")
    CloseTracker closeTracker() {
        return new CloseTracker();
    }
}

@Test
void invokesBeanDestroyMethodWhenContextCloses() {
    AnnotationConfigApplicationContext context =
            new AnnotationConfigApplicationContext(CloseTrackerConfiguration.class);
    CloseTracker tracker = context.getBean(CloseTracker.class);

    context.close();

    assertThat(tracker.isClosed()).isTrue();
}
```

The test uses a self-created context, not a context cached by the TestContext Framework. That allows closing directly and testing destroy callbacks without corrupting the suite's shared context.

### 9.3. Checking Background Tasks Before Closing

If a test dispatches asynchronous tasks, wait for tasks to complete before assertions or resource cleanup:

```java
@Test
void waitsForAsyncWorkToComplete() throws Exception {
    CompletableFuture<Result> result = service.processAsync(command);

    Result completed = result.get(2, TimeUnit.SECONDS);

    assertThat(completed.status()).isEqualTo(Status.COMPLETED);
}
```

`get(timeout, unit)` ensures the test finishes within a bounded time if the worker hangs. Once the future completes, the test can verify side effects or updated state.

If an API only returns when the task is queued without returning a future, use a `CountDownLatch` or a test observer. Avoid `Thread.sleep` to guess whether the worker finished.

## 10. Tasks Still Using Resources When the Context Closes

A tricky problem is a worker still using a datasource, HTTP client, or file stream while the context starts destroying beans. If resources close first, the worker can throw errors mid-flight or write incomplete data.

Organize shutdown in order:

1. Stop accepting new requests or messages.
2. Stop scheduling new work.
3. Wait for running tasks to complete within a bounded duration.
4. If the timeout expires, request cancellation or interruption per task policy.
5. Close clients, connection pools, and resources used by workers.

To have Spring enforce this order, use the dependency graph and `SmartLifecycle` phases. Beans processing work must stop before beans supplying resources to them. For executors, configure appropriate wait/await termination and ensure tasks respond to interruption or cancellation.

Not every task can stop immediately. An in-progress data write transaction may need to complete or roll back; a message consumer may need explicit ack/nack; a file writer may need to flush. Shutdown policies must match the type of work and the application's consistency requirements.

### 10.1. Tasks Must Support Cancellation

Long-running tasks should check interrupt or cancellation status at safe points:

```java
void processLargeBatch(List<Item> items) throws InterruptedException {
    for (Item item : items) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("Batch processing interrupted");
        }

        process(item);
    }
}
```

Do not swallow `InterruptedException`. If catching the exception for cleanup or error translation, restore the interrupt status when appropriate via `Thread.currentThread().interrupt()`. This lets the executor and shutdown logic know the task was asked to stop.

### 10.2. Timeouts and Unstoppable Work

Choose wait timeouts based on shutdown SLAs and actual task duration. If a task cannot be safely interrupted, you may need to let it finish or hand work off to a durable queue mechanism so another process continues. Do not wait indefinitely in a shutdown hook, or the JVM may be held open and fail to exit.

## 11. Context Hierarchies and Shared Resources

An application can have a parent context and child contexts. When a child closes, Spring destroys beans belonging to the child context. The parent context has its own lifecycle and may be shared by other children.

This matters in test hierarchies: closing a child context does not mean all parent resources are closed. If the parent owns a shared datasource, let the component owning the parent manage closing the datasource. Avoid letting a child close a resource that the parent or a sibling context is still using.

If multiple contexts reference a resource outside Spring, establish a single owner and manage references/lifecycles explicitly. Do not let every context close the same shared client unless the client supports that.

## 12. Common Mistakes When Closing Contexts

### Threads Keep Running After Tests End

Common causes are manually created threads, unmanaged executors, or shutdown not waiting for tasks. Register executors as beans, configure shutdown, and ensure tasks have termination/cancellation points.

### Context Closes Yet Sockets Stay Open

The bean owning the client/socket lacks a destroy callback or the resource was created outside the container. Register the bean with `destroyMethod = "close"`, `@PreDestroy`, or an explicit lifecycle owner.

### Subsequent Test Receives a Closed Context

A test manually called `close()` on a context cached by the TestContext Framework. Use `@DirtiesContext` so the framework evicts and closes the context properly, or use a separate self-created context when testing shutdown.

### Worker Uses an Already Closed Datasource

Shutdown order is wrong or tasks have not completed before the datasource is destroyed. Stop workers first, wait for tasks, and only then close dependencies.

### `SmartLifecycle` Callback Called Too Early

The bean invokes the callback immediately after issuing a stop command. Spring proceeds to destroy dependencies while the worker is still running. Only invoke the callback after stopping has actually completed.

### `@PreDestroy` Submits More Tasks to a Shutting-Down Executor

Tasks may be rejected or not awaited. Move stop steps into an appropriately ordered lifecycle phase or perform synchronous cleanup before the executor closes.

### Using `@DirtiesContext` to Clean Everything

Closing the context does not delete external databases, files, or messages. Clean each resource via its own ownership mechanism.

## 13. Comprehensive Example: Worker Depending on a Client

Suppose an application has a worker processing messages using a client. When the context closes, the worker must stop before the client. You can express the relationship via bean dependencies and use `SmartLifecycle` for the worker:

```java
@Configuration
class WorkerConfiguration {
    @Bean(destroyMethod = "close")
    RemoteClient remoteClient() {
        return new RemoteClient();
    }

    @Bean
    MessageWorker messageWorker(RemoteClient remoteClient) {
        return new MessageWorker(remoteClient);
    }
}

class MessageWorker implements SmartLifecycle {
    private final RemoteClient client;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private volatile boolean running;

    MessageWorker(RemoteClient client) {
        this.client = client;
    }

    @Override
    public void start() {
        running = true;
        // Start accepting and submitting work to executor.
    }

    @Override
    public void stop(Runnable callback) {
        running = false;
        executor.shutdown();
        Thread waiter = new Thread(() -> {
            try {
                if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
                    executor.shutdownNow();
                }
            } catch (InterruptedException exception) {
                executor.shutdownNow();
                Thread.currentThread().interrupt();
            } finally {
                callback.run();
            }
        }, "message-worker-stop");
        waiter.start();
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return 100;
    }
}
```

The example illustrates lifecycle ordering; in production, make the executor a Spring-managed bean or use `ThreadPoolTaskExecutor` to avoid creating waiter threads and managing shutdown manually. If a worker uses its own executor, the worker must own and close that executor explicitly. The `RemoteClient` dependency is constructor-injected so Spring knows the worker needs the client and can destroy the worker before its dependency.

Tests can use a fake client recording `close()` and a worker with a completion signal to verify the worker stops before the client closes. When testing cleanup order, observe actual callbacks/lifecycles rather than only checking constructor invocation order.

## 14. Shutdown Design Workflow for Integration Tests

When tests or the application create background resources, determine:

1. Which bean owns the resource and which beans merely use it?
2. Is the resource created per test method, per test class, or per `ApplicationContext`?
3. Are any thread pools, schedulers, or consumers continuing to accept work as the context closes?
4. Do running tasks need to complete, roll back, or be cancellable?
5. Which destroy callback closes each resource, and is the callback safe when errors occur mid-way?
6. Does shutdown order guarantee workers stop before their dependencies?
7. Does the test use the context cache, and must context closure go through `@DirtiesContext`?
8. Are there resources outside the context such as databases, brokers, or files needing separate cleanup?
9. Is there a bounded timeout so the suite does not hang if a worker fails to stop?

A test should finish once the work it initiated has completed or been cancelled per policy. Do not let tasks from one test continue writing data after another test has started.

## 15. Principles to Remember

- Closing `ApplicationContext` triggers close events, stops bean lifecycles, and invokes destruction callbacks for managed beans.
- Use `@PreDestroy`, `DisposableBean`, or `@Bean(destroyMethod = ...)` to release resources.
- Use `Lifecycle`/`SmartLifecycle` when beans need ordered start/stop or asynchronous stop completion.
- Beans processing work should stop before the dependencies they use.
- Register executors and schedulers as beans; configure waiting for or cancelling running tasks.
- Long-running tasks need timeout/cancellation mechanisms and proper interruption handling.
- The context cache can retain contexts across multiple tests; do not manually close a context managed by the TestContext Framework.
- Use `@DirtiesContext` when a context must be evicted from the cache; clean up databases, brokers, files, and external resources with dedicated mechanisms.
- Suppliers, event listeners, or `@PreDestroy` should not silently submit additional work to an executor that is shutting down.

Good shutdown management helps Spring close beans in the right order, gives background tasks a chance to finish, and releases resources without leaving threads or connections lingering after tests. In integration tests, clearly defining ownership, lifecycles, and completion waiting is essential for a stable context cache and a clean suite exit.
