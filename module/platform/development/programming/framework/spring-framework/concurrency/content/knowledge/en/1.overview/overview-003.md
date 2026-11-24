# Tasks, Caller Threads, Worker Threads, and Results in Spring Framework

## Objective

After this lesson, you can distinguish between **task**, **caller thread**, **execution/worker thread**, and **result**; trace a synchronous or asynchronous call; recognize the roles of `TaskExecutor`, `@Async`, and `CompletableFuture`; and explain when the caller thread still has to wait, where errors go, and which data does not automatically follow onto a new thread.

The scope of this lesson is the execution model and result flow in Spring Framework. Periodic scheduling techniques, deep thread pool tuning, and reactive programming are mentioned only for contrast, not as the main focus.

## 1. Four Concepts to Separate

| Component | Nature | Question to Answer |
| --- | --- | --- |
| **Task** | A unit of work that can be executed, such as generating a report, calling an external service, or performing a calculation. In Java it is typically represented by a `Runnable`, `Callable<T>`, or a method body. | *What work needs to be done?* |
| **Caller thread** | The thread running the code that calls the method or submits the task to an executor; it may be `main`, an HTTP request thread, or another worker. | *Who initiates the work?* |
| **Execution/worker thread** | The thread that actually executes the body of the work after the execution mechanism decides; it may be a pooled thread, a new thread, or the caller thread itself if a synchronous executor is used. | *Where does the work actually run?* |
| **Result** | The return value, completion status, exception, or cancellation; with asynchrony it can be represented by a `Future<T>`/`CompletableFuture<T>` before the value is ready. | *What does the caller receive, when, and how?* |

**A task is not synonymous with a thread.** One thread can run multiple tasks sequentially; an executor can queue tasks, reuse threads, or reject tasks when overloaded. Creating a `CompletableFuture` also does not by itself prove the work is running on another thread: you must look at where the task is executed.

**An asynchronous result has two layers:** the object representing the future result is returned first; the actual value or error only appears when the task completes. A `CompletableFuture` may already be completed at the moment the caller receives it; you must not rely on an "incomplete" state to determine whether a call is asynchronous.

## 2. The Path of a Call

### Synchronous Call

```text
Caller thread
  -> calls service.process()
  -> caller itself executes the method body
  -> receives value or exception
  -> only then proceeds to the next statement
```

For example, `String value = service.process();` runs directly in the standard way: if `process()` takes 500 ms, the caller must wait for it to finish. Even if the method internally performs I/O or `Thread.sleep`, the call is still synchronous if control has not been returned to the caller.

### Asynchronous Call via an Executor

```text
Caller thread            Executor / queue                Worker thread
  | submit(task)  -------------> |                            |
  | <--- Future/handle           | ---- assigns task -------> |
  | continues other work         |                            | runs task
  |                              |                            | produces value/error
  | Future is completed <------------------------------------ |
  | waits only if calling get()/join() or on a dependent waiting step
```

A typical sequence:

1. The caller prepares input data and submits the work; submission itself can take time or be rejected.
2. The executor chooses when and where to run the task according to its configured policy.
3. The caller receives a handle, typically a `Future`/`CompletableFuture`, and *can* do other work.
4. The worker runs the task, then records the value or exception into the handle.
5. The caller observes the result using callbacks/composition or via `get()`/`join()` if waiting is acceptable.

**Asynchronous does not mean nothing ever blocks.** `join()` blocks the thread calling it if the result is not yet ready; blocking I/O inside a worker still occupies that worker. Asynchrony is about decoupling the timing/location of processing from the caller thread, whereas non-blocking is a property of a specific operation.

## 3. Where Does Spring Place the Execution Mechanism?

Spring provides `TaskExecutor` as an abstraction for task execution. `ThreadPoolTaskExecutor` is a commonly used implementation with a thread pool and queue; depending on the executor, work does not necessarily always run on another thread. There is no rule saying "every task creates a thread."

| Invocation Style | Execution Path | How the Result Is Received |
| --- | --- | --- |
| Normal Java method call | The method body runs directly on the caller, unless it delegates work itself. | Direct value or exception. |
| `taskExecutor.execute(runnable)` | The executor receives the `Runnable` and selects the thread/timing for execution. | `execute` returns no value-holding handle; you must organize signals/results yourself if needed. |
| Calling an `@Async` bean **via Spring proxy** | The interceptor routes the call to the selected executor; the method body runs inside the executor. | Usually uses `CompletableFuture<T>`/`Future<T>` or `void`; errors must be observed through the right channel. |
| `CompletableFuture.supplyAsync(supplier, executor)` | Java submits the `Supplier` to the specified executor. | A JDK-managed `CompletableFuture<T>`, allowing processing steps to be composed. |

Typical `@Async` path:

```text
Bean A (caller)
  -> Spring proxy of Bean B
     -> @Async interceptor selects executor
        -> submits work to executor
        -> caller receives CompletableFuture
           -> worker runs the actual method of Bean B
              -> completes result or error
```

For `@Async` to take effect under the default proxy mechanism, support must be enabled with `@EnableAsync`, the method must be called through a Spring-managed bean, and a suitable executor must be present. Calling `this.someAsyncMethod()` within the same bean is **self-invocation**: it does not pass through the proxy, so it usually runs synchronously on the current thread. Methods that cannot be properly proxied/intercepted will also not produce the expected result.

`@Async("lessonExecutor")` explicitly selects the executor bean named `lessonExecutor`. When unspecified, Spring selects according to the active async configuration; do not rely on a particular thread name or default executor without checking the actual configuration.

## 4. Runnable Spring Framework Example with Java 17+

This standalone example pins Spring Framework 6.2.0 for reproducibility. It intentionally stores the `Thread` object in the result **solely to verify the execution path**, not as a data pattern to return from real business logic.

Structure:

```text
async-flow-demo/
├── pom.xml
└── src/main/java/example/AsyncFlowDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>async-flow-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>example.AsyncFlowDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/example/AsyncFlowDemo.java`:

```java
package example;

import java.util.concurrent.CompletableFuture;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncFlowDemo {
    public record WorkResult(String value, Thread executedBy) {}

    public static class WorkService {
        @Async("lessonExecutor")
        public CompletableFuture<WorkResult> process(String input) {
            WorkResult value = new WorkResult(
                "done:" + input,
                Thread.currentThread()
            );
            return CompletableFuture.completedFuture(value);
        }
    }

    @Configuration
    @EnableAsync
    public static class Config {
        @Bean
        public WorkService workService() {
            return new WorkService();
        }

        @Bean("lessonExecutor")
        public ThreadPoolTaskExecutor lessonExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(16);
            executor.setThreadNamePrefix("lesson-");
            return executor;
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {
            WorkService service = context.getBean(WorkService.class);
            Thread caller = Thread.currentThread();

            CompletableFuture<WorkResult> handle = service.process("A");
            // Here the caller already has the handle; the task may be running or already done.
            WorkResult result = handle.join();

            System.out.println("differentThread="
                + (result.executedBy() != caller));
            System.out.println("result=" + result.value());
        }
    }
}
```

Run from the `async-flow-demo` directory with JDK 17+ and Maven:

```bash
mvn -q compile exec:java
```

Two lines printed by the program:

```text
differentThread=true
result=done:A
```

Meaning of each stage:

1. `main` keeps a `caller` reference to the thread that called the service.
2. `context.getBean(WorkService.class)` retrieves the Spring-processed bean; the `process("A")` call goes through the proxy to `lessonExecutor`.
3. A pool worker runs the `process` body, creating `WorkResult("done:A", currentThread)`. Calling `completedFuture(...)` **inside the worker** merely wraps the computed value; it does not make execution synchronous on the caller.
4. `handle` is the result object held by the caller. `handle.join()` waits if the worker is not done yet, then retrieves `WorkResult`.
5. `differentThread=true` confirms that in this specific configuration, the worker is a different thread from the caller. Actual execution order is still determined by the executor and scheduler.

If you need to observe thread names, temporarily add `System.out.println(Thread.currentThread().getName())` in both the caller and the `process` body. Exact names and interleaving timing of log lines depend on the runtime, so you should not write tests that depend on log ordering across threads.

## 5. Results, Errors, and Next Processing Steps

### Values and Waiting

- `Future<T>.get()` retrieves the result when ready; it can block and declares checked exceptions, including `InterruptedException` and `ExecutionException`.
- `CompletableFuture<T>.join()` also waits when needed but reports completion errors via `CompletionException` (unchecked).
- `thenApply` transforms the value after completion; `thenCompose` chains a step returning another `CompletionStage`; `thenCombine` combines two independent results.
- `thenApply` does not guarantee that the callback runs on a separate thread: it may run on the thread completing the stage or the registering thread if the stage is already done. The `...Async` variants choose asynchronous execution; explicitly pass an executor when resource control is needed.

The following snippet illustrates usage inside a method that already has `WorkService service` (not a standalone Java program):

```java
CompletableFuture<String> displayName = service.process("A")
    .thenApply(work -> "Output = " + work.value());

displayName.whenComplete((value, error) -> {
    if (error != null) {
        System.err.println("Task failed: " + error.getMessage());
    } else {
        System.out.println(value);
    }
});
```

`whenComplete` observes both success and failure; if you need to *recover* with a fallback value, consider `exceptionally` or `handle`. Do not swallow errors by returning a dummy value without recording the cause.

### Exceptions, Timeouts, Cancellation

With `@Async` returning `Future`/`CompletableFuture`, exceptions from the work are recorded in the asynchronous result and only surface when you observe the stage (e.g., `join`, `get`, `whenComplete`). With `@Async void` methods, the caller cannot receive errors via the return value; configure `AsyncUncaughtExceptionHandler` when centralized handling is needed, avoiding "fire-and-forget" for critical tasks.

`orTimeout(2, TimeUnit.SECONDS)` can cause a `CompletableFuture` to complete with a timeout error; **timing out the result does not automatically guarantee stopping the background task**. Canceling a `CompletableFuture` is also not a guarantee of interrupting the running thread. True cancellation requires designing cooperative tasks that check state, I/O timeouts, and an appropriate cancellation mechanism.

If the executor runs out of capacity to accept tasks, *submission* can fail with a rejection error (e.g., `TaskRejectedException` in Spring). This case differs from exceptions thrown after the worker starts processing; both must be accounted for in error design.

## 6. HTTP Threads and Task Threads Are Not the Same

Example in a Spring MVC Servlet application:

```text
HTTP request -> servlet request thread -> Controller
                 |                        |
                 | calls @Async service   | can receive CompletableFuture
                 |----------------------> | then return / join / other work
                                          |
                                 worker thread processes service
```

If the controller calls `service.process(...).join()` immediately, the thread executing the controller still waits for the result. Having the service run on a worker **does not automatically release the HTTP request thread** during the wait.

Spring MVC has its own asynchronous request processing mechanisms, such as a controller returning `Callable<T>`, `DeferredResult<T>`, or a supported `CompletionStage<T>`/`CompletableFuture<T>`. With `Callable`, Spring MVC submits the computation to `AsyncTaskExecutor`, releases the Servlet thread serving the request, and dispatches again when the result is ready. With `DeferredResult`, an external source completes the result and MVC dispatches again to send the response. The HTTP response still completes only when appropriate data or an error/timeout is available.

Therefore, **two separate contracts** should be clearly stated in the design: (1) which executor the service method runs on, and (2) whether the HTTP request is held waiting or managed by the framework in async mode. Do not treat `@Async` as a way to automatically make the entire controller non-blocking; a worker running blocking JDBC is still a thread occupied for that duration.

## 7. Data Crossing Thread Boundaries

**Parameters and shared objects:** data passed to a task still obeys Java's thread-safety rules. If the caller modifies an `ArrayList` or mutable DTO while the worker reads it, race conditions easily occur. Prefer immutable data, snapshots before submission, or proper synchronization.

**`ThreadLocal` and context:** MDC logging, `SecurityContext`, request/locale context, and thread-bound transaction resources do not inherently transfer to workers. If needed, choose a deliberate context-propagation mechanism, such as `TaskDecorator` for logging data and executors supporting security context. Do not use HTTP request context after the request has ended if it is no longer valid.

**Transactions:** a transaction bound to the caller thread does not automatically "follow" `@Async`. A data write operation on a worker needs its own transaction boundary if required; transactional handling is usually placed on a bean called from the worker via a Spring proxy. Avoid relying on the caller's transaction to guarantee atomicity for background work.

**Lifecycle:** `@Async` tasks run inside the application process. If the process stops, unfinished tasks can be lost; critical tasks must be designed for durability, retry/idempotency, and may need a queue/broker or job store. Shut down executors and handle shutdown in a controlled manner.

## 8. Common Mistakes and How to Verify

| Mistake | Consequence | How to Check/Fix |
| --- | --- | --- |
| Thinking `@Async` always runs on another thread without checking the proxy | Calls may still be synchronous due to missing `@EnableAsync` or self-invocation. | Call through an injected Spring bean; verify configuration, threads, and proxies. |
| Assuming task = thread | Expecting each call to get its own thread; unpredictable under load. | Measure worker count, queue, and executor behavior. |
| Calling `join()` immediately and claiming the caller "doesn't wait" | The caller is blocked until the task finishes. | Log submission time, join time, and completion time. |
| Guessing execution order from submission statement order | Different tasks can complete out of submission order. | Correlate results by ID or stages, not by log order. |
| Using `@Async void` for work that must succeed | No handle to know errors/results. | Return `CompletableFuture<T>` or persist durable job state. |
| Setting an overly small executor, unbounded queue, or lacking a rejection policy | Latency spikes, memory bloat, tasks dropped during peak traffic. | Set appropriate bounds, monitor queue/active threads/rejections, design backpressure. |
| Sharing state or assuming thread-bound transactions/context are inherited | Race conditions, lost logging/security info, incorrect transactions. | Use thread-safe data and explicit context propagation/transaction boundaries. |

A short diagnostic flow: assign an ID to the task → log timestamp/caller thread at submission → log worker thread at task start/end → observe handle status/completion → identify where `get`/`join` or the HTTP response is waiting → record success, errors, timeouts, and rejections. Use `Thread.currentThread().getName()` to observe; do not infer solely from annotation names.

## 9. Self-Check

1. **A controller calls an `@Async` service and calls `join()` immediately.** The service may run on a worker, but the controller thread still waits; making the HTTP request asynchronous also requires an appropriate Spring MVC return contract.
2. **An executor with only one worker receives three tasks.** They are still three independent tasks, but they may have to run sequentially; "submitted" does not mean "executed in parallel."
3. **An `@Async` method is called via `this.method()` in the same bean.** Under default proxy mode, the internal call bypasses the interceptor, so there is no offload to the executor via the annotation.
4. **The caller receives a `CompletableFuture` where `isDone() == true`.** That does not prove the call ran synchronously; the task may have completed very quickly before being checked.
5. **The worker throws an exception.** For a method returning `CompletableFuture`, you must observe the asynchronous result to see the error; the exception is not necessarily thrown right at the line where the caller invokes the proxy.

### Takeaway

Every call involves four independent questions: **what work needs to run, who submits the work, which thread actually runs it, and when the result is observed**. When reading Spring concurrency code, trace all four before concluding whether the system runs in parallel, releases threads, or handles errors safely.

### References

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `TaskExecutor`, `ThreadPoolTaskExecutor`, `@EnableAsync`, `@Async`, executor selection, and errors.
- [Spring Framework — Asynchronous Requests (Spring MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html): distinguishing service task execution from the asynchronous Servlet request lifecycle.
