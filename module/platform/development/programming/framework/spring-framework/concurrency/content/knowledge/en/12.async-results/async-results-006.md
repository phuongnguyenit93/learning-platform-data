# Do Not Use Normal Synchronous Return Types Assuming You Will Still Receive Results

## 1. The Problem: Writing @Async Does Not Turn String into an Immediately Returned Result

In regular Java, a method declaring `String` and running synchronously gives the caller a value as soon as the method finishes:

```java
public String calculate() {
    return "42";
}

// Synchronous call:
String value = service.calculate();
System.out.println(value);
```

This is an illustrative snippet within existing classes, not a standalone program. The caller proceeds after `calculate()` finishes and receives the exact return value.

When wanting Spring to run a method **asynchronously** via `@Async`, learners easily make the mistake of writing:

```java
import org.springframework.scheduling.annotation.Async;

@Async
public String calculate() {
    return "42";
}
```

**This is an invalid declaration for standard Spring `@Async` mechanics.** `String` is a synchronous return type: it neither represents work that will finish later nor provides a channel for signaling errors, waiting, or cancellation. Spring cannot both return immediately to the caller and preserve the `String calculate()` method contract in the way the `@Async` proxy supports.

According to the Javadoc of `org.springframework.scheduling.annotation.Async`, the supported return types of the target method are **`void` or a `java.util.concurrent.Future` type**, including **`CompletableFuture<T>`**. Plain types such as `String`, `int`, `UserDto`, `List<UserDto>`, `Optional<UserDto>`, or `ResponseEntity<UserDto>` are **not permitted** as direct return types of an `@Async` method under this model.

In an invocation actually intercepted by Spring's async interceptor, an unsupported type typically raises `IllegalArgumentException` with a message like "Invalid return type for async method ..." instead of returning a `String` as expected. If you still observe `String` returning normally, that may be because the method **ran synchronously**, for instance via a `this.calculate()` call bypassing the proxy, or `@Async` processing was not enabled. Never take the symptom of "having data" as proof that asynchronous execution is working.

**Core principle:** When you want to receive results from `@Async` work, design a **return interface representing a future result**, most commonly `CompletableFuture<T>`; when you do not need to return a result to the caller, you can use `void` and design an appropriate error-recording mechanism.

## 2. Why Are Synchronous Return Types Unsuitable?

A synchronous method returning `T` expresses:

```text
Caller --------------------> method()
       waits for method to finish
       <-------------------- T
       continues with value T
```

An `@Async` method processed by Spring through a proxy typically expresses:

```text
Caller -> Spring proxy -> select Executor -> submit work
Caller <---------------- Future<T> / CompletableFuture<T>
    |                          |
    | do other work            | worker executes real method
    |                          |
    +-- observe/wait ----------+--> T or exception upon completion
```

Because the result `T` is not guaranteed to exist when the caller returns, the returned object must represent **incomplete, completed successfully, or completed exceptionally states**. `Future<T>` carries that basic contract, while `CompletableFuture<T>` additionally supports coordination and result-transformation operations.

Do not assume that `@Async` creates a special `T` object for the caller to use as already-available data. If you want `T` immediately, that is a **synchronous contract**: call a normal method, wait for completion, or explicitly decide when to wait via `Future.get()`/`join()`. You cannot have both "immediately" and "the actual outcome of unfinished work" without an abstraction representing future state.

### 2.1. Comparing Return Types

| Method declaration | Works with standard Spring @Async? | What does the caller get? |
|---|---|---|
| `void send()` | Yes | No result handle; needs a separate error/monitoring channel |
| `Future<String> load()` | Yes | `Future` to wait, cancel, and observe status and errors |
| `CompletableFuture<String> load()` | Yes | Future and non-blocking result composition API |
| `String load()` | **No** | Synchronous type, not a task handle |
| `int count()` / `boolean check()` | **No** | Synchronous primitive value |
| `UserDto load()` | **No** | Direct DTO, does not represent unfinished work |
| `List<UserDto> loadAll()` | **No** | Direct collection, not a Future |
| `Optional<UserDto> find()` | **No** | Presence/absence of a current value, not completion state |
| `ResponseEntity<UserDto> response()` | **No** | HTTP wrapper, not a Future |
| `CompletionStage<String> load()` | **No under this declaration** | `CompletionStage` does not extend `Future`; declare `CompletableFuture<String>` if using Spring @Async |
| `Mono<String> load()` / `Flux<String> load()` | **No under this @Async** | Reactive Publisher has a different execution model; not a Future |

**Subtle detail:** `CompletableFuture<T>` implements both `Future<T>` and `CompletionStage<T>`. However, **the declared return type in the signature** is what Spring checks. Writing `CompletionStage<T>` is not the same as writing `CompletableFuture<T>` even though the actual runtime object returned might be a `CompletableFuture`.

These notes apply to Spring's `@Async` annotation with the default interceptor, and do not claim all Java asynchronous systems can only use Future. Reactor, Kotlin coroutines, messaging, and Spring MVC have different contracts; do not mix those mechanisms unconsciously.

## 3. Exact API Rules of Spring @Async

The `@Async` Javadoc states:

- The method can accept normal parameters.
- The return type must be `void` or belong to the supported `Future` family.
- `CompletableFuture<T>` can be declared to compose with subsequent steps.
- The `Future` the caller receives from the Spring proxy is the **real asynchronous handle** to track the result.
- The target method must still return the declared type. Therefore, it can return a `CompletableFuture.completedFuture(value)` after finishing the computation **on the worker**; the Spring proxy creates a separate handle representing the asynchronous execution.

That last point is easy to confuse. Looking at the method body:

```java
@Async("resultExecutor")
public CompletableFuture<Integer> doubleValue(int n) {
    int result = n * 2;
    return CompletableFuture.completedFuture(result);
}
```

Many people see `completedFuture(...)` and conclude "this method isn't actually async." That conclusion **is incorrect if the call goes through the Spring proxy**. The method body is executed by the worker and returns an already completed Future once computation finishes; the proxy provides the caller with a handle to **the entire submitted work**. That differs from:

```java
public CompletableFuture<Integer> doubleValue(int n) {
    return CompletableFuture.completedFuture(n * 2);
}
```

Without `@Async` and without another async mechanism, the `n * 2` calculation runs on the calling thread; the `CompletableFuture` object merely wraps the already computed result. **A `CompletableFuture` return type by itself does not guarantee a background thread.**

You can visualize the two Future layers as follows:

```text
Caller
  |
  | call through @Async proxy
  v
Spring creates/uses outer Future (held by caller)
  |
  | Executor accepts task
  v
Worker executes target method
  |
  | method returns inner Future, usually completedFuture(value)
  v
Spring extracts/transfers result into outer Future
  |
  v
Caller observes outer Future -> value or error
```

With a `void`-returning method, the caller receives no outer Future. With a method declaring `String`, there is no compatible `Future` interface for the proxy to return, and Spring rejects that signature.

## 4. Common Wrong Examples and Correct Fixes

### 4.1. Returning String Directly

**Wrong:**

```java
@Async("resultExecutor")
public String generateCode(String prefix) {
    return prefix + "-123";
}
```

**Correct when a value must be received:**

```java
@Async("resultExecutor")
public CompletableFuture<String> generateCode(String prefix) {
    String code = prefix + "-123";
    return CompletableFuture.completedFuture(code);
}
```

These are illustrative methods inside a Spring bean; not a standalone program. The caller must update to the new signature:

```java
CompletableFuture<String> pending = service.generateCode("INV");
// Do other work or attach a pipeline before observing the result.
String code = pending.join();
```

`join()` can block until the result is ready. If called immediately and always waiting, the caller still blocks even though the method body moved to another executor; see the non-blocking composition section below.

### 4.2. Returning DTO, List, or Optional Directly

**Wrong:**

```java
@Async
public UserDto findUser(String id) {
    return repository.load(id);
}
```

**Valid return design:**

```java
@Async("resultExecutor")
public CompletableFuture<UserDto> findUser(String id) {
    UserDto user = repository.load(id);
    return CompletableFuture.completedFuture(user);
}
```

`UserDto` and `repository` are business types/components supplied by the application; the two snippets above are **not** standalone Java classes. The fixed snippet uses a Future containing **UserDto** instead of returning `UserDto` directly.

If the business logic returns a collection, the corresponding type can be `CompletableFuture<List<UserDto>>`. If the result may be absent, you can use `CompletableFuture<Optional<UserDto>>`. These are Futures holding business results; do not invert them into `List<CompletableFuture<UserDto>>` if the business logic really only has one task producing the entire list, and do not confuse `Optional` with a completion handle.

### 4.3. Returning boolean or int Directly

**Wrong:**

```java
@Async
public boolean sendNotification(String recipient) {
    // Returning boolean when the method finishes is not supported by Spring @Async.
    return true;
}
```

**Correct if the caller needs to know success/failure via business data:**

```java
@Async("resultExecutor")
public CompletableFuture<Boolean> sendNotification(String recipient) {
    boolean delivered = sendThroughProvider(recipient);
    return CompletableFuture.completedFuture(delivered);
}
```

`sendThroughProvider` is a hypothetical service method. If success is represented by the method completing and failure by an exception, you can return `CompletableFuture<Void>` instead of `Boolean`. Still, you must clearly define whether the boolean represents "sent to provider," "provider accepted," or "recipient received"; async does not define the meaning of success on its own.

### 4.4. No Result Needed: Using void Deliberately

```java
@Async("resultExecutor")
public void writeAuditEvent(String eventId) {
    auditRepository.save(eventId);
}
```

This is an example method in a Spring bean, assuming `auditRepository` exists. `void` is valid, but the caller cannot call `get()` or `join()` to retrieve a result, nor directly receive errors inside the task if it runs on a worker. If audit records are critical data that must be saved even if the JVM crashes, using `@Async void` alone is insufficient; an appropriate durable task-storage mechanism is needed.

**Do not pick `void` just to silence a signature error when the caller genuinely needs status.** Choose the return type according to the business contract, not merely to stop the annotation from throwing an error.

## 5. Future<T> and CompletableFuture<T> — How Do They Differ?

Both can represent a computation that will complete later; however, their tracking and composition capabilities differ:

| Need | Future<T> | CompletableFuture<T> |
|---|---|---|
| Wait to retrieve value | `get()` | `get()` or `join()` |
| Wait with time limit | `get(timeout, unit)` | `get(timeout, unit)`, plus dedicated timeout APIs |
| Check completion | `isDone()` | `isDone()` |
| Contract-based cancellation | `cancel(...)` | `cancel(...)` |
| Transform on completion without waiting immediately | No composition API in basic Future interface | `thenApply(...)`, `thenCompose(...)` |
| Coordinate two tasks | Requires custom orchestration | `thenCombine(...)`, `allOf(...)` |
| Error recovery | Usually handled around `get()` | `exceptionally(...)`, `handle(...)`, `whenComplete(...)` |
| Type accepted by Spring @Async | Yes | Yes |

Note: `Future.get()` can throw `InterruptedException` and `ExecutionException`; `get(timeout, unit)` adds `TimeoutException`. `CompletableFuture.join()` typically reports errors via `CompletionException` (unchecked), and may throw `CancellationException` if cancelled. These different error-reporting styles do not make the task itself safer.

### 5.1. Basic Future Usage

```java
@Async("resultExecutor")
public Future<Integer> calculateTax(int amount) {
    int tax = amount / 10;
    return CompletableFuture.completedFuture(tax);
}
```

This is a valid Spring method snippet: the signature declares `Future<Integer>`; the method body returns a `CompletableFuture<Integer>` because that type implements `Future<Integer>`.

Caller:

```java
Future<Integer> pending = service.calculateTax(200);
try {
    Integer tax = pending.get();
    System.out.println(tax);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    // Calling layer decides whether to stop or propagate an appropriate error.
} catch (ExecutionException execution) {
    Throwable rootCause = execution.getCause();
    // Record/handle root cause.
}
```

This is an illustrative code fragment in a caller method, requiring imports for `java.util.concurrent.Future` and `ExecutionException`. `get()` blocks until the task finishes. If you want the UI/request not to block, design future-driven responses rather than calling `get()` immediately.

### 5.2. CompletableFuture Usage

```java
@Async("resultExecutor")
public CompletableFuture<Integer> calculateTax(int amount) {
    int tax = amount / 10;
    return CompletableFuture.completedFuture(tax);
}
```

The caller can attach a transformation:

```java
CompletableFuture<String> description = service
        .calculateTax(200)
        .thenApply(tax -> "Tax: " + tax);
```

Building the pipeline on the caller does not necessarily block waiting for the computation to finish. `thenApply` may run on the thread completing the previous stage or the thread registering the continuation if the result is already ready; **it makes no promise to run on a dedicated executor**. When you need to assign an executor for an asynchronous continuation, use the `thenApplyAsync(action, specificExecutor)` overload and ensure the executor's lifecycle is properly managed.

### 5.3. When Multiple Steps Depend on Each Other

If step B is also async and returns `CompletableFuture<U>`, consider `thenCompose` to chain the pipeline:

```java
CompletableFuture<String> workflow = service.findUserId("A")
        .thenCompose(userId -> service.loadProfile(userId))
        .thenApply(profile -> "Loaded profile: " + profile);
```

This is an architectural code fragment, assuming `service` has two methods returning `CompletableFuture<String>`. `thenCompose` "flattens" step B's future, unlike `thenApply` which would produce `CompletableFuture<CompletableFuture<String>>` if the lambda returns a future.

Do not wrap an extra `CompletableFuture.supplyAsync(...)` layer outside an `@Async` method just to "be sure it's async": that can cause two scheduling hops, move work onto the common pool if no executor is passed, increase context complications, and make errors harder to trace.

## 6. Complete Spring Example with Java 17: @Async Returning Future Properly

This example shows one method returning `CompletableFuture<Integer>`, one method returning `Future<String>`, and an executor with a custom thread prefix. The program retrieves the service from the Spring `ApplicationContext` so invocations **go through the `@Async` proxy**.

This is a minimal Maven example using **Java 17+** and **Spring Framework 6.2.7**. Spring will be downloaded by Maven; you cannot simply run `javac AsyncReturnTypesDemo.java` without dependencies.

### 6.1. Project Structure

```text
async-return-types-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── lesson/
                └── AsyncReturnTypesDemo.java
```

### 6.2. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>lesson</groupId>
    <artifactId>async-return-types-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.7</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.3. File src/main/java/lesson/AsyncReturnTypesDemo.java

```java
package lesson;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Future;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncReturnTypesDemo {

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            ResultService service = context.getBean(ResultService.class);

            CompletableFuture<Integer> number = service.doubleValue(21);
            Future<String> workerName = service.workerName();

            System.out.println("Result: " + number.join());
            System.out.println("Right executor: "
                    + workerName.get().startsWith("result-worker-"));
        }
    }

    @Configuration
    @EnableAsync
    public static class AppConfig {

        @Bean("resultExecutor")
        public ThreadPoolTaskExecutor resultExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(4);
            executor.setThreadNamePrefix("result-worker-");
            return executor;
        }

        @Bean
        public ResultService resultService() {
            return new ResultService();
        }
    }

    public static class ResultService {

        @Async("resultExecutor")
        public CompletableFuture<Integer> doubleValue(int input) {
            int result = input * 2;
            return CompletableFuture.completedFuture(result);
        }

        @Async("resultExecutor")
        public Future<String> workerName() {
            return CompletableFuture.completedFuture(
                    Thread.currentThread().getName());
        }
    }
}
```

### 6.4. Compile/Run

In the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=lesson.AsyncReturnTypesDemo
```

**Two lines printed by the program**, excluding separate Maven messages:

```text
Result: 42
Right executor: true
```

Reasons the output is deterministic:

1. `service` is a bean retrieved from `AnnotationConfigApplicationContext`; calls are processed by the `@Async` interceptor.
2. `@EnableAsync` activates annotation processing in the context containing the service bean.
3. Both methods specify `@Async("resultExecutor")`; the executor bean sets thread prefix `result-worker-`.
4. `doubleValue(21)` computes 42 on the worker; `CompletableFuture.completedFuture(42)` is the target method's temporary handle; the caller holds the proxy-returned `CompletableFuture` to read 42.
5. `workerName()` captures the thread name of **the side executing the method body**, not the caller's name. `startsWith("result-worker-")` verifies the right prefix without depending on worker sequence number.
6. `join()` and `get()` in `main` are used to **observe the demo results**. For real HTTP requests, waiting right after the call can defeat the goal of avoiding blocking the caller.
7. `ThreadPoolTaskExecutor` is a Spring-managed bean, so the demo app does not manually call `shutdown()` on a shared pool inside the service; closing the context ends the bean lifecycle as configured.

This example deliberately contains no network or heavy operations; it illustrates **return types and execution paths**, not a benchmark. Writing `@Async public Integer doubleValue(...)` to "simplify" would result in a signature rejected by the async interceptor unlike the example above.

## 7. Counter-Example: Why Can @Async String Trick You into Thinking It Worked?

Examine the illustrative class:

```java
import org.springframework.scheduling.annotation.Async;

public class WrongReturnService {

    @Async("resultExecutor")
    public String getMessage() {
        return "Hello";
    }

    public String callFromSameClass() {
        return this.getMessage();
    }
}
```

This snippet is not standalone: you need to register the service and executor in Spring to verify proxy behavior. There are **two call paths** to distinguish.

### Path A — Called from Another Bean Through the Proxy

```text
External bean -> WrongReturnService proxy -> @Async interceptor
                                   |
                                   +--> sees declared return type String
                                   |
                                   +--> throws invalid return type error
```

This path produces no `Future<String>` because the API declared by the method is `String`; Spring rejects the invalid signature. This is a **programming contract error**, not data loss or pool overload.

### Path B — Calling this.getMessage() Inside the Same Class

```text
Caller -> WrongReturnService.callFromSameClass()
                                 |
                                 +--> this.getMessage()
                                       (bypasses proxy)
                                 |
                                 +--> returns "Hello" synchronously
```

In default proxy mode, internal calls typically do not go through advice. A `String` result may appear, but **that is not proof Spring ran the method asynchronously**. The fix is not casting `String` to a `Future` at the caller: you must change the `@Async` method's signature appropriately and call it properly through the proxy.

If you use `new WrongReturnService()` instead of retrieving the bean from Spring, the annotation has no effect either because the object is unmanaged. Additionally, a call can run synchronously if an executor deliberately executes directly; what matters is verifying the mechanism and contract rather than guessing from the annotation name.

## 8. CompletableFuture Returned Immediately: What Is Finished, What Isn't?

`CompletableFuture<T>` is a **future result object**, not the value `T`. There are at least three states to distinguish:

- **Incomplete:** the task is queued or running; the future does not yet hold the final result.
- **Completed normally:** a result exists and can be obtained via `join()/get()` or a pipeline.
- **Completed exceptionally/cancelled:** the future has no successful result; the caller must handle the error.

Do not assume every returned `CompletableFuture` is necessarily still waiting: a method may finish very quickly and the caller receives an already completed future. Conversely, just because an `@Async` call returns immediately does not mean the business value is ready.

A safe workflow:

```java
CompletableFuture<String> future = service.loadReport(reportId);

future.thenAccept(report -> {
    System.out.println("Report ready: " + report);
}).exceptionally(error -> {
    System.err.println("Failed to generate report: " + error);
    return null;
});
```

This is an illustrative snippet; `service.loadReport(...)` is assumed to return `CompletableFuture<String>`. The caller **cannot** write `String report = service.loadReport(reportId)` because the types are incompatible right at compile time. Neither should you call `future.getNow(null)` and treat `null` as failure: `null` might merely mean the work is not done yet or the valid result is null, depending on design.

### 8.1. thenApply, thenCompose, thenCombine

- `thenApply(f)` transforms `T` into `U` once a stage has completed successfully.
- `thenCompose(f)` is used when `f` returns another future, so you do not create nested futures.
- `thenCombine(other, f)` waits for two stages to succeed and merges both results.
- `whenComplete(action)` observes results/errors, though it is not a deliberate error-recovery API.
- `handle(f)` can turn both success and failure into a new value.
- `exceptionally(f)` provides a recovery path for a failed stage.

For pipelines with asynchronous steps, note that `thenApply` does not guarantee running on a separate worker: it may run on the thread completing the previous stage or the caller if the stage is already completed. `thenApplyAsync(...)` without an executor may use the common pool; if you need to enforce a specific execution policy, supply an explicitly configured executor.

### 8.2. There Is No Synchronous Value to Cast

Counter-example:

```java
// Wrong: Future<String> cannot be cast to String.
String result = (String) service.loadReport(reportId);
```

This is an intentionally wrong counter-example; if `loadReport` is declared to return `CompletableFuture<String>`, the cast above is invalid and can fail at compile time due to incompatible types. Do not switch to `Object` to sneak past the compiler and cast back; the runtime object is still a future, never turning into a `String`.

If you are forced to wait at a synchronous boundary, **make the waiting explicit**:

```java
String result = service.loadReport(reportId).join();
```

This is only valid if the return type really is `CompletableFuture<String>`; it **blocks** the caller until completion. It is not a way to keep an API "both synchronous and non-blocking."

## 9. Standalone Java 17: Proving a Future Does Not Hold an Immediate Result

This example uses `CountDownLatch` to keep the worker from finishing until the caller decides to open the latch. As a result, `isDone()` is guaranteed to be `false` on the first check and the final result is 42.

**File `FutureIsNotValueDemo.java` — no Spring required:**

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class FutureIsNotValueDemo {

    public static void main(String[] args)
            throws InterruptedException {

        ExecutorService pool =
                Executors.newSingleThreadExecutor();

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch allowFinish = new CountDownLatch(1);

        try {
            CompletableFuture<Integer> future =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            allowFinish.await();
                        } catch (InterruptedException interrupted) {
                            Thread.currentThread().interrupt();
                            throw new IllegalStateException(
                                    "Interrupted", interrupted);
                        }
                        return 21 * 2;
                    }, pool);

            started.await();

            System.out.println("Done before release: "
                    + future.isDone());

            allowFinish.countDown();

            System.out.println("Result after waiting: "
                    + future.join());
        } finally {
            allowFinish.countDown();
            pool.shutdown();
        }
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac FutureIsNotValueDemo.java
java FutureIsNotValueDemo
```

Output:

```text
Done before release: false
Result after waiting: 42
```

Explanation:

1. `supplyAsync(..., pool)` immediately returns a `CompletableFuture<Integer>` representing the computation, not the `int` 42.
2. The worker starts, signals `started.countDown()`, and waits on `allowFinish`. The caller waits on `started.await()` to know the worker has reached the checkpoint.
3. The `future.isDone()` check occurs while the latch is closed, so the exact value is `false`.
4. After `allowFinish.countDown()`, the worker is allowed to finish and return 42.
5. `join()` retrieves 42 once the task completes. If the task is not finished yet, `join()` waits; it does not turn the call into "getting an immediate result."
6. `finally` opens the latch to prevent leaving the worker stuck if main exits early, and calls `shutdown()` on the manually created pool.

This is a standard Java illustration, **not Spring's `@Async` implementation**. It helps learners clearly see two concepts: *receiving a handle immediately* and *receiving the value after work completes*. In Spring, the `@Async` proxy must likewise provide a future-result contract rather than turning a synchronous `String` into an asynchronous computation.

## 10. Errors: How Does a Future Report Errors?

Distinguish **errors during routing/submission** from **errors after the task body has run**.

### 10.1. Unsupported Return Type

`@Async public String get()` is a method contract error. In Spring's default proxy, when the interceptor detects an invalid signature, `IllegalArgumentException` typically occurs right on the calling path. There is no `Future` to extract the error from because the method does not declare a valid Future.

Fix: change the signature and update all relevant callers; do not just remove the annotation or try to catch a generic error and silently return null.

### 10.2. Executor Not Found / Executor Rejects

`@Async("missingExecutor")` can fail when Spring cannot find the matching bean; a closed/full pool can reject work. These are typically **synchronous errors on the submission path**, not proof that the method body ran. Fix the wiring or handle overload per API policy.

### 10.3. Exceptions Inside a Future-Returning Method

A valid method:

```java
@Async("resultExecutor")
public CompletableFuture<Integer> divide(int a, int b) {
    int value = a / b; // b = 0 causes ArithmeticException.
    return CompletableFuture.completedFuture(value);
}
```

Caller:

```java
CompletableFuture<Integer> pending = service.divide(10, 0);

pending.whenComplete((value, error) -> {
    if (error != null) {
        System.err.println("Execution failed: " + error);
    }
});
```

These are illustrative snippets in a Spring service/caller, not a standalone program. If the task runs through the proxy, exceptions inside the worker are reflected by the caller's Future **completing exceptionally**; a created Future cannot be treated as a successful result.

If using `get()`, errors typically appear in `ExecutionException`, with the cause at `getCause()`. If using `join()`, errors are typically wrapped in `CompletionException`; if the future was cancelled, `CancellationException` may occur. Do not ignore the cause or merely log "job failed" without a correlation ID.

### 10.4. Exceptions Inside a void-Returning Method

```java
@Async("resultExecutor")
public void sendMail(String address) {
    throw new IllegalStateException("Simulated send failure");
}
```

The caller has no returned Future to receive `IllegalStateException` if the task runs on a worker. With Spring `@Async void`, unhandled errors inside the method can be passed to `AsyncUncaughtExceptionHandler`; Spring logs them by default. A custom handler can be supplied via `AsyncConfigurer`.

**Do not use `void` for business flows where the caller must know success/failure for certain.** You can use `CompletableFuture<Void>` when no data is needed yet a completion handle is still required.

### 10.5. CompletableFuture<Void> for Operations Returning No Data

```java
@Async("resultExecutor")
public CompletableFuture<Void> updateCache(String key) {
    updateCacheInternal(key);
    return CompletableFuture.completedFuture(null);
}
```

This is an illustrative method snippet, assuming `updateCacheInternal` exists. The caller receives `CompletableFuture<Void>`; `join()` returns `null` upon normal completion, but the crucial point is **being able to wait/observe errors**, unlike `void`.

## 11. Do Not Turn a Spring Controller into a Fake Synchronous Call

Consider a web application with a service taking time to generate a report. An anti-pattern is:

```java
// Wrong signature for Spring @Async:
@Async("resultExecutor")
public ReportDto buildReport(String id) {
    return reportRepository.build(id);
}
```

The method above **cannot** be used as a Spring `@Async` computation returning `ReportDto` directly. Suppose the service is fixed to:

```java
@Async("resultExecutor")
public CompletableFuture<ReportDto> buildReport(String id) {
    ReportDto dto = reportRepository.build(id);
    return CompletableFuture.completedFuture(dto);
}
```

Now the controller has several valid choices depending on the HTTP contract:

- If the API **must return the report content when processing finishes**, in Spring MVC it can return an MVC-supported async result type, such as `CompletableFuture<ReportDto>` or `CompletableFuture<ResponseEntity<ReportDto>>` at the appropriate controller layer. Spring MVC will manage HTTP completion according to the supported abstraction; this differs from the service returning `ReportDto` synchronously.
- If the API **only acknowledges receipt of the request and returns a job ID**, durable job status persistence/lookup capability is needed. Returning HTTP 202 does not by itself prove the background job finished.
- If using `future.join()` in the controller to return `ReportDto` directly, the controller **blocks** until the work is done. This is a deliberate synchronous choice, not a fully asynchronous solution.

Spring MVC controller example code (placed in a valid controller with an injected service):

```java
@GetMapping("/reports/{id}")
public CompletableFuture<ResponseEntity<ReportDto>> getReport(
        @PathVariable String id) {

    return reportService.buildReport(id)
            .thenApply(ResponseEntity::ok);
}
```

This is a **Spring MVC fragment**, assuming `reportService.buildReport` returns `CompletableFuture<ReportDto>` and Spring MVC types/imports are in place. The return type of the **controller** here is handled by Spring MVC under the async web request model; there is no need to put `@Async` directly on the controller method just because it returns a Future. Keep business processing in the service, and let the controller decide the HTTP contract.

**Distinguish wrapper nesting order:** `CompletableFuture<ResponseEntity<ReportDto>>` has the Future on the outside and can be handled asynchronously. `ResponseEntity<CompletableFuture<ReportDto>>` has `ResponseEntity` on the outside; if `@Async` is placed directly on a method returning that type, the declared return type **is not a Future**, so it fails Spring `@Async`'s contract.

## 12. @Async Does Not Guarantee Every Caller Is Non-Blocking

There are two major reasons:

**First — caller code waits on its own:**

```java
int result = service.doubleValue(21).join();
```

Spring may run the computation on a worker, yet `join()` still blocks the caller until 42 is ready. To gain non-blocking benefits at the application boundary, return the Future or attach a pipeline and wait only where the result is genuinely required.

**Second — the executor/design may run on the caller:** `SyncTaskExecutor` runs tasks directly on the submitting thread. Some rejection policies like `CallerRunsPolicy` can make the caller run the task when the pool is overloaded, if not shut down. Thus, "having `@Async`" is not enough to infer "always uses another thread" or "caller always returns immediately."

Furthermore, `CompletableFuture.completedFuture(value)` **inside a method without `@Async`** merely wraps an already computed result; if heavy computation occurs before the `completedFuture` call on the caller, returning a `CompletableFuture` type does not make that computation run in the background automatically.

## 13. Spring Proxy Issues That Can Hide Return-Type Errors

If an `@Async` method has an invalid return type yet you still see it returning a normal `String`, check the infrastructure before concluding "Spring handled it automatically."

### 13.1. @EnableAsync Not Enabled

In Java configuration, you typically need:

```java
@Configuration
@EnableAsync
public class AsyncConfiguration {
    // Register an appropriate Executor/TaskExecutor if needed.
}
```

This is an illustrative Spring configuration class requiring corresponding `Configuration` and `EnableAsync` imports. Without `@Async` processing enabled, the annotation can have no effect in the active context; a regular method keeps returning a synchronous value.

### 13.2. Self-Invocation

```java
public String outer() {
    return this.wrongAsyncMethod();
}

@Async
public String wrongAsyncMethod() {
    return "value";
}
```

This is an **intentionally broken snippet**. In default proxy mode, `this.wrongAsyncMethod()` does not go through the interceptor, so it still receives a synchronous `String`. Yet when another bean calls the method through the proxy, the `@Async String` signature is invalid. Never design programs relying on accidentally bypassing the interceptor.

Solution: extract the method needing async execution into another Spring bean, inject that bean, and use a `CompletableFuture<String>` signature. An advanced option is properly configured AspectJ weaving, though unnecessary for this foundational problem.

### 13.3. Class/Method Not Properly Proxied

`private` methods, internal calls, manually `new`-created objects, `final` methods under subclass proxying, and multi-`ApplicationContext` layouts can prevent advice from applying as intended. While learning, prefer **public non-final methods** on Spring-managed services called from another bean.

Per the `@Async` Javadoc, do not use this annotation on methods declared inside `@Configuration`. Keep executor configuration in `@Configuration`, and business tasks in separate services.

### 13.4. @Transactional and Other Advice

If a method uses both `@Transactional` and `@Async`, you must understand proxy/advice ordering and transaction boundaries. Transactions in the caller **do not automatically transfer intact** to the worker. If business logic needs a transaction when running asynchronously, design a proper transaction along the worker path and verify actual behavior with integration tests.

Do not try to fix a wrong return type by adding `@Transactional`, `@Retryable`, or `@Cacheable`: they have different responsibilities and do not turn `String` into a valid Future type for `@Async`.

## 14. Timeouts, Cancellation, and When Results Remain Valid

With a Future-returning method, the caller can set a wait budget:

```java
Future<String> pending = service.loadReport(id);
try {
    String report = pending.get(2, TimeUnit.SECONDS);
    consume(report);
} catch (TimeoutException timeout) {
    pending.cancel(true);
    // Record timeout and apply business contract.
}
```

This is an illustrative caller fragment, assuming `service`, `consume`, and `java.util.concurrent` imports exist. The enclosing method must also handle or redeclare `InterruptedException`/`ExecutionException`.

**Expiring `get(timeout)` does not automatically cancel the work.** `cancel(true)` is a cancel/interrupt request per the Future/executor mechanism; uncooperative tasks or I/O operations may continue. Moreover, once the caller stops waiting, the backend may already have performed a side effect; cancelling a Future is not a rollback for transactions or external services.

With `CompletableFuture`, Java-version-specific timeout-completion APIs can be used, but distinguish **handle behavior** from **the underlying task actually stopping**. Build deadlines into business requirements if work becomes meaningless after a certain point.

Also avoid waiting on a Future inside the same bounded pool if the awaited task needs resources/workers from that same pool. A worker submitting sub-work and waiting inside a single-worker pool can deadlock due to starvation, unrelated to `String` vs. `CompletableFuture` return types. Having the right type only enables waiting/observing; flow and resource design remain separate responsibilities.

## 15. Thread Safety, Visibility, and Results Outside the Future

Another mistake is trying to use `void` while storing the result in a field, then reading the field right after the call:

```java
private String latestReport;

@Async("resultExecutor")
public void generate() {
    latestReport = "Done";
}

// Another caller:
service.generate();
String value = service.getLatestReport();
```

This is a **counter-example fragment**, not standalone code. It has multiple flaws:

- `generate()` may not have run yet when the caller reads the field.
- If the field is not properly protected, there are visibility issues and data races.
- Concurrent requests sharing one field on a singleton bean can overwrite each other's results.
- There is no ID/handle tying a result to a specific request.

Using `volatile` can improve visibility for a simple written/read value, yet it **does not** create a completion-waiting mechanism, does not tie results to individual requests, and does not make a sequence of updates atomic.

If the caller needs **the result of that specific call**, `CompletableFuture<T>` is the natural contract. If **long-lived job status** queried by multiple clients is needed, design a state store and job ID with a clear lifecycle instead of using a singleton field as an application-wide mailbox.

A successfully completed Future provides synchronization points per the contracts of appropriate concurrent APIs, yet mutable data inside the result still needs clear ownership. For example, returning an `ArrayList` and continuing to mutate it from another worker can cause races; prefer immutable snapshots or proper synchronization mechanisms.

## 16. Future Does Not Make Background Work Durable

`CompletableFuture<T>` tells the caller when *an execution inside the current process* finishes; it **does not** guarantee the work will run to completion if the JVM dies, the application redeploys, the pool closes, or the worker is never scheduled.

If the business process involves payments, critical emails, generating guaranteed documents, or processing that may take several minutes, you must explicitly decide:

- When is a request considered **accepted** and when is it **succeeded**?
- Must the work be persisted in a database/broker before returning acknowledgement to the caller?
- Are retries safe against partially executed operations? Is there an idempotency key?
- How do you query status, report failures, or recover after restarts?
- Are worker/queue bounds, backpressure, and explicit rejection policies in place?

Returning `CompletableFuture<String>` with the right `@Async` signature only solves **tracking the result of a task**, not the entire reliability problem on its own.

## 17. Testing Return Types and Execution Behavior

A unit test merely checking that a method has `@Async` is insufficient. With Spring, at minimum test:

1. The context has `@EnableAsync` actually active.
2. The service is retrieved from Spring, not manually created with `new`.
3. The method properly returns `void`, `Future<T>`, or `CompletableFuture<T>`.
4. For result-returning methods, the caller receives a Future and the exact result upon completion.
5. Exceptions inside the task body cause the Future to fail rather than appear successful.
6. Invalid return-type errors are caught **when invoked through the proxy**, not masked by self-invocation.
7. The thread/executor selected matches configuration; do not merely guess from the annotation.
8. Tests wait using timeouts/latches when needed; do not use `Thread.sleep(...)` to guess task completion.
9. Test pool overload/rejection scenarios and application shutdown policies.
10. Test HTTP/job contracts when callers do not want to wait for the result.

Illustrative assertion example (using JUnit and a real Spring test context):

```java
CompletableFuture<Integer> future = service.doubleValue(21);
assertEquals(42, future.join());
```

This snippet is not standalone because it requires `service` retrieved through the proxy and `assertEquals` from the test library. The point is not using `join()` in production, but having tests verify the Future's type and value.

If you need to test an invalid `@Async String`, create a separate bean, call it from a test bean through the proxy, and verify the contract error; do not "test" by instantiating with `new` or calling `this.invalidMethod()` in the same bean, because that tests a plain Java call rather than Spring's async interceptor.

### 17.1. Signs Worth Investigating in Production

- Runtime reports `Invalid return type for async method`: look for `@Async` signatures returning `String`, DTOs, primitives, `Optional`, `CompletionStage`, or unsupported types.
- Users report results are occasionally null: look for logic reading fields right after `void @Async` or calling `getNow(...)` without distinguishing state.
- API is slow despite `@Async`: look for `join()/get()` directly on the request thread or `CallerRunsPolicy` when the pool is overloaded.
- Method thought to be async always logs the same caller thread name: check proxy, `@EnableAsync`, self-invocation, and executor.
- Caller sees no task errors: check `void` vs. Future, `AsyncUncaughtExceptionHandler`, and whether exceptional completion is being observed.
- Bug "returned 202 yet task was lost": check task persistence guarantees; do not treat an in-memory executor or Future as a durable message queue.

## 18. Practice Exercises with Guided Solutions

### Exercise 1 — Identify Wrong Signatures

Given the signatures:

```java
@Async String a();
@Async void b();
@Async Future<Integer> c();
@Async CompletableFuture<List<String>> d();
@Async Optional<String> e();
@Async CompletionStage<String> f();
```

Question: which ones are valid for standard Spring `@Async`?

**Guidance:** `b`, `c`, and `d` are valid regarding return types. `a`, `e`, and `f` are invalid; specifically, `CompletionStage` does not extend `Future` even though an implementation like `CompletableFuture` can implement both interfaces. The methods also still need to be properly Spring-managed/proxied to run asynchronously.

### Exercise 2 — Fix DTO Usage

An existing service:

```java
@Async
public CustomerDto load(String id) {
    return repository.find(id);
}
```

The caller writes `CustomerDto dto = service.load(id);`. Fix both the service signature and the caller so the caller can do other work while waiting for the result.

**Guidance:** Change the service to `CompletableFuture<CustomerDto>`, compute the DTO inside the worker, and return `CompletableFuture.completedFuture(dto)`. The caller holds `CompletableFuture<CustomerDto>`, attaches `thenApply/thenAccept`, or passes the future to the responsible layer. Do not call `join()` immediately if the goal is avoiding blocking.

### Exercise 3 — Why Is completedFuture Still Correct?

An `@Async` method computes a value and returns `CompletableFuture.completedFuture(value)`. Does that contradict the asynchronous goal?

**Guidance:** No, if the method is called through the proxy. The method body runs inside a Spring executor task; `completedFuture` is the temporary handle from the target method. The proxy gives the caller a Future representing that async execution.

### Exercise 4 — Spot Self-Invocation

`@Async public String get()` returns a normal String when called from `this.get()`. Can we conclude Spring supports String?

**Guidance:** No. Internal calls do not go through the proxy in default mode. You must change the signature and call through the Spring bean proxy before evaluating behavior.

### Exercise 5 — CompletableFuture Yet Still Blocking

The caller invokes `service.calculate().join()` right after submitting the task. Why can the HTTP request still be slow even though the executor runs on a separate worker?

**Guidance:** `join()` blocks the HTTP request thread until the Future completes. Use web-layer async integration or design a job ID/SLO response if you do not want to wait.

### Exercise 6 — No Data Needed, Yet Need to Know Completion

You are using `@Async void saveAudit()`; the caller needs no returned data, yet must know saving succeeded before the next step. Which type should you choose?

**Guidance:** `CompletableFuture<Void>` and handle completion/failure, or design another appropriate business transaction/orchestration. `void` provides no completion handle to the caller.

### Exercise 7 — Run the Examples

Run the `AsyncReturnTypesDemo` project on Spring, then run pure Java 17 `FutureIsNotValueDemo`. Explain why the first example receives 42 through the proxy Future, while the second receives a Future before the task is allowed to finish.

**Guidance:** Both decouple the handle from the value; Spring handles dispatch via the interceptor and `@Async`, while Java SE uses `CompletableFuture.supplyAsync(..., executor)`.

## 19. Checklist When Reviewing a Result-Returning @Async Method

| Question | Desired condition |
|---|---|
| What data does the method intend to return? | `T` is placed **inside** `Future<T>`/`CompletableFuture<T>` |
| Is the return type supported by @Async? | `void` or a compatible `Future` type |
| Does the caller really need the result? | If yes, do not pick `void` and read a shared mutable field |
| Is @EnableAsync enabled in the right context? | Yes, and the method is called through the Spring proxy |
| Is the executor configured clearly? | Selected bean, worker/queue bounds, and rejection policy are known |
| Where is the result retrieved? | `get/join` at a blocking-acceptable boundary or non-blocking pipeline |
| Where are exceptions observed? | Future completion/error or a handler for `void` |
| Are there timeouts/cancellations/deadlines? | Policies match requirements and understand the task may still be running |
| Are state and thread context safe? | Do not assume transactions or ThreadLocals propagate automatically |
| Must results survive restarts? | If yes, use a durable job/log storage mechanism |

## 20. Summary of Principles

- **Do not use synchronous return types like `String`, `int`, DTO, or `List<T>` directly on Spring `@Async` assuming the caller will still receive data.**
- **`@Async` supports `void` or compatible `Future` types**, most commonly `CompletableFuture<T>` when results and multi-step coordination are needed.
- **The Spring proxy returns a Future representing the asynchronous execution**; the target method can use `CompletableFuture.completedFuture(value)` as a temporary handle once computed on the worker.
- **`void` is valid yet gives the caller no completion handle.** If you need to know completion/error without data, consider `CompletableFuture<Void>`.
- **`get()`/`join()` are potential blocking points.** Use pipelines or web-layer async abstractions when wanting to avoid blocking callers.
- **The right type alone is not enough:** `@EnableAsync` must be enabled, calls must go through the Spring bean proxy, an appropriate executor must be chosen, and errors/load/context must be handled as needed.
- **A Future is neither business data nor a durable job queue.** It is a contract for tracking a single execution; reliability still requires separate design.

### Standard Documentation

- [Spring Framework Javadoc — @Async](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/Async.html)
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework Javadoc — @EnableAsync](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Java SE 17 Javadoc — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 17 Javadoc — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java SE 17 Javadoc — CompletionStage](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html)
