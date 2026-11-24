# Why Does Calling a Method Within the Same Bean Not Trigger @Async in Proxy Mode?

## 1. Common Problem: @Async Is Present, Yet the Work Still Runs Synchronously

In the Spring Framework, `@Async` is used to ask Spring to execute a method on an executor rather than continuing to run the method body immediately on the calling thread. A very common source of confusion is:

```java
@Service
public class MailService {

    public void register(String id) {
        validate(id);
        this.sendMail(id); // Self-invocation within the same bean.
    }

    @Async("mailExecutor")
    public void sendMail(String id) {
        // Send email or perform time-consuming work.
    }

    private void validate(String id) {
        // Validate data.
    }
}
```

This is an **illustrative fragment**, not a standalone runnable program; it requires a Spring-managed bean, executor configuration, and async support enabled. Many developers see `@Async`, `@EnableAsync`, and a thread pool all present, yet `sendMail()` still runs on the thread executing `register()`.

**The cause is not that Spring missed the annotation.** In the default AOP proxy mode, Spring only applies the async interceptor when a method call **goes through the proxy**. The call `this.sendMail(id)` is inside the same object/target and **does not pass through the Spring proxy**, so the interceptor is not triggered.

Result:

- The thread calling `register()` runs `sendMail()` directly.
- If sending email waits on the network, the calling thread may be blocked.
- If the method throws an exception, the error propagation path may differ from a call handled by the proxy.
- The bean proxy and executor can be completely configured correctly, yet the self-invocation path alone still fails to be async.

**Short rule:** having `@Async` on a method **does not mean** every call to that method is asynchronous. You must inspect *the call path*.

## 2. How Does @Async Work in Spring Proxy Mode?

When annotation processing is enabled with `@EnableAsync` in Java config or `<task:annotation-driven>` in XML, Spring registers the `@Async` processing infrastructure. In the default `AdviceMode.PROXY` mode, Spring can place a proxy into the `ApplicationContext` at the point where consumers retrieve the bean.

Simple concept:

```text
                         ApplicationContext
                                |
                   bean exposed to callers
                                |
                        Spring AOP proxy
                                |
         external call to @Async method intercepted?
                                |
                    Async interceptor / advice
                                |
                       submit to executor
                                |
                    worker thread invokes target
                                |
                         method body runs
```

When another bean receives a dependency from Spring, that dependency can be a **proxy** rather than the raw target. The proxy is able to receive the call, inspect the advice, and then decide to submit the task to the executor.

The key point is that the proxy does not "rewrite" every Java call appearing inside the class. Once you are already inside the target's code, the expression `this.someMethod()` is a method call on the exact instance currently executing the body, not a new call through a bean reference obtained from the `ApplicationContext`.

### 2.1. Two Call Paths That Look Similar but Have Different Outcomes

```text
PATH A — External call through bean/proxy:

Controller / Facade
      |
      v
Spring proxy (MailWorker)
      |
      +-- @Async interceptor --> mailExecutor.submit(...)
                                   |
                                   v
                              worker thread
                                   |
                                   v
                              MailWorker.deliver()

PATH B — Self-invocation inside the same target:

Controller / Facade
      |
      v
Spring proxy (MailWorker)
      |
      v
MailWorker.selfCall()  [target method body]
      |
      +-- this.deliver() ---------> MailWorker.deliver()
                                     (DOES NOT re-enter proxy)
                                     (NO async interceptor)
```

Even in Path B, the entry point `selfCall()` may be called through the proxy. But because `selfCall()` is not an async advice point in the example, it simply delegates to the target. When the target calls `deliver()` on itself, no new interception round occurs.

### 2.2. Not a CGLIB-Specific Behavior

Spring AOP can use either JDK dynamic proxies or class-based proxies. Both rely on the principle of interception at the **boundary of calls passing through the proxy**.

- With JDK dynamic proxies, eligible calls normally go through the interface implemented by the proxy.
- With class-based proxies, Spring uses a subclass proxy, so clients can retrieve the bean by its concrete class in supported scenarios.
- **Neither approach solves self-invocation simply by switching the proxy type.** Setting `@EnableAsync(proxyTargetClass = true)` does not turn `this.sendMail()` into a call going through the proxy.

A less obvious fact: `AopUtils.isAopProxy(bean) == true` only confirms that the reference you hold is a proxy; it **does not guarantee** that every call inside the target passes through the advice.

## 3. Necessary Conditions for @Async to Actually Be Intercepted

In plain Spring Framework, for a call to run asynchronously under proxy mode, the following conditions must hold simultaneously:

1. **Annotation processing is enabled:** `@EnableAsync` or XML `<task:annotation-driven>` is loaded into the appropriate context.
2. **The bean is Spring-managed:** the client must use the bean created and post-processed by Spring; an object instantiated with `new MailWorker()` outside the container will not receive AOP advice automatically.
3. **The call path passes through the proxy:** another bean invokes an advice-intercepted method, rather than the target calling itself via `this.method()`.
4. **The method fits the proxy mechanism:** do not expect interception on `private` methods, `final` methods with class-based proxies, or calls outside the corresponding interface surface of a JDK proxy.
5. **A suitable executor exists:** if `@Async("mailExecutor")` is specified, a corresponding executor bean must exist; the actual executor must be configured according to operational requirements.
6. **The method is not called too early in the lifecycle:** calling from a constructor or initialization callback such as `@PostConstruct` is not a reliable way to trigger an `@Async` call through the proxy.

Missing any one condition can cause unexpected behavior. However, **self-invocation is a call-path bug**, which cannot be fixed merely by enlarging the pool or adding `@EnableAsync` again.

## 4. Runnable Java 21 + Spring Framework 6.2.1 Example

This standalone example verifies three call paths:

- **Self-invocation:** a bean method calls `this.deliver(...)`.
- **External invocation:** code retrieves the bean from Spring and calls `deliver(...)` through the proxy reference.
- **Cross-bean invocation:** another Spring bean receives the dependency via injection and calls `deliver(...)`.

The program actively checks the calling thread and the executor's prefix rather than using `Thread.sleep(...)` to guess completion timing. Results are printed as booleans so they do not depend on thread names assigned by Maven or the OS.

### 4.1. Structure

```text
async-self-demo/
├── pom.xml
└── src/main/java/demo/SelfInvocationDemo.java
```

### 4.2. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>async-self-demo</artifactId>
  <version>1.0</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.1</version>
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
        <configuration>
          <mainClass>demo.SelfInvocationDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

Spring Boot is not needed to observe the principle. The `spring-context` dependency enables configuring the context, `@EnableAsync`, `ThreadPoolTaskExecutor`, and using the required AOP infrastructure in this lesson.

### 4.3. File src/main/java/demo/SelfInvocationDemo.java

```java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class SelfInvocationDemo {
    public static class MailWorker {
        @Async("mailExecutor")
        public CompletableFuture<String> deliver(String id) {
            return CompletableFuture.completedFuture(
                    Thread.currentThread().getName() + "|" + id);
        }

        public CompletableFuture<String> selfCall(String id) {
            return this.deliver(id);
        }
    }

    public static class MailFacade {
        private final MailWorker worker;

        public MailFacade(MailWorker worker) {
            this.worker = worker;
        }

        public CompletableFuture<String> crossBeanCall(String id) {
            return worker.deliver(id);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class AppConfig {
        @Bean("mailExecutor")
        public ThreadPoolTaskExecutor mailExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(2);
            pool.setQueueCapacity(8);
            pool.setThreadNamePrefix("mail-");
            return pool;
        }

        @Bean
        public MailWorker mailWorker() {
            return new MailWorker();
        }

        @Bean
        public MailFacade mailFacade(MailWorker worker) {
            return new MailFacade(worker);
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            String caller = Thread.currentThread().getName();
            MailWorker worker = context.getBean(MailWorker.class);
            MailFacade facade = context.getBean(MailFacade.class);

            String self = worker.selfCall("S").get(5, TimeUnit.SECONDS);
            String external = worker.deliver("E").get(5, TimeUnit.SECONDS);
            String crossBean =
                    facade.crossBeanCall("C").get(5, TimeUnit.SECONDS);

            System.out.println("proxy=" + AopUtils.isAopProxy(worker));
            System.out.println("selfCallOnCaller=" +
                    self.equals(caller + "|S"));
            System.out.println("externalCallOnPool=" +
                    (external.startsWith("mail-") && external.endsWith("|E")));
            System.out.println("crossBeanCallOnPool=" +
                    (crossBean.startsWith("mail-") && crossBean.endsWith("|C")));

            if (!AopUtils.isAopProxy(worker)
                    || !self.equals(caller + "|S")
                    || !external.startsWith("mail-")
                    || !crossBean.startsWith("mail-")) {
                throw new AssertionError("Async proxy behavior not as expected");
            }
        }
    }
}
```

### 4.4. Execution and Verification Results

Run in the directory containing `pom.xml`, with Maven and JDK 21 or later:

```bash
mvn -q -DskipTests compile exec:java
```

Output actually compiled and executed with Spring Framework 6.2.1 (separate Maven/JVM logs may appear depending on the environment):

```text
proxy=true
selfCallOnCaller=true
externalCallOnPool=true
crossBeanCallOnPool=true
```

Line-by-line interpretation:

- `proxy=true`: the `worker` reference retrieved from the context is a Spring AOP proxy.
- `selfCallOnCaller=true`: calling `worker.selfCall("S")` ends up invoking `this.deliver("S")` inside the target; the body of `deliver` runs on the exact thread that called `selfCall`.
- `externalCallOnPool=true`: calling `worker.deliver("E")` directly from outside the target passes through the proxy, so the interceptor submits the work to the executor whose thread prefix is `mail-`.
- `crossBeanCallOnPool=true`: `MailFacade` has the `MailWorker` bean injected by Spring; calling `worker.deliver("C")` in the facade passes through the proxy and executes on the pool.

This comparison is designed to distinguish the **call path**: the same `deliver` method, the same annotation, and the same configuration, yet one path runs synchronously and the others run asynchronously.

It does not print a fixed thread name like `main` or `mail-1` because the caller thread name when running via Maven may vary; comparing against the runtime caller thread name reference and the configured prefix is the stable check. In addition, `Future.get(timeout)` ensures the program waits for completion cleanly rather than relying on scheduler ordering.

## 5. Detailed Execution Trace of the Example

### 5.1. When Calling worker.selfCall("S")

Caller code:

```java
String self = worker.selfCall("S").get(5, TimeUnit.SECONDS);
```

This is a **fragment extracted from the complete program**. The `worker` reference is the bean proxy, but `selfCall` is not annotated with `@Async`. When the code inside the target reaches:

```java
return this.deliver(id);
```

it invokes the target method directly and bypasses the proxy/`@Async` interceptor. Therefore, `Thread.currentThread().getName()` inside `deliver` equals the caller's initial thread. That the method returns an already completed `CompletableFuture` **does not prove that it executed asynchronously**.

### 5.2. When Calling worker.deliver("E")

Caller code:

```java
String external = worker.deliver("E").get(5, TimeUnit.SECONDS);
```

The call passes through the proxy. The async advice selects the `mailExecutor` bean from the name in `@Async("mailExecutor")` and submits the task. The worker executes the method body, completes the `CompletableFuture`, and then the caller obtains the result via `get()`.

Note that `get()` is a **blocking call on the caller**, even though the task runs on the pool. The example deliberately uses it to observe the result; in latency-sensitive production HTTP paths, you should not submit and immediately wait indefinitely if the goal is to free the request thread.

### 5.3. When Calling facade.crossBeanCall("C")

`MailFacade` receives `MailWorker` via constructor injection:

```java
public MailFacade(MailWorker worker) {
    this.worker = worker;
}
```

This dependency is provided by the container and can be a proxy reference. Therefore, when the facade calls `worker.deliver("C")`, it hits the advice properly. This is a clean way to fix self-invocation because the dependency expresses the **boundary between orchestration and background work**.

### 5.4. Why Not Look Only at the Thread Name?

If an outer `@Async` method was already called through the proxy, it will begin executing on a worker. If *inside that worker* it uses `this.otherAsync()` to invoke another method on itself, the inner method still executes directly on the **same worker**, without creating a new submission.

Therefore, simply seeing logs on `mail-1` is not enough to conclude that every nested async annotation was intercepted. You must distinguish:

- **Who dispatched the first call to the pool?**
- **Did the observed method actually pass through the proxy?**
- **Was a new task/submission created, or was it just a regular Java call inside the worker?**

## 6. Preferred Fix: Extract Async Work into a Separate Bean

When a service both handles requests and needs to dispatch background work, the most maintainable option is **separation of responsibilities**. Design example:

```java
@Service
public class NotificationWorker {
    @Async("mailExecutor")
    public CompletableFuture<Void> send(String id) {
        // Background work: load data, send notification, log appropriately.
        return CompletableFuture.completedFuture(null);
    }
}

@Service
public class RegistrationService {
    private final NotificationWorker notificationWorker;

    public RegistrationService(NotificationWorker notificationWorker) {
        this.notificationWorker = notificationWorker;
    }

    public void register(String id) {
        // Handle registration and validation.
        notificationWorker.send(id); // Call to the injected bean.
    }
}
```

This is an **application fragment**, requiring `@EnableAsync`, the `mailExecutor` bean, imports for `org.springframework.stereotype.Service`, `org.springframework.scheduling.annotation.Async`, and `java.util.concurrent.CompletableFuture`, plus actual business logic.

Benefits:

1. `RegistrationService` only manages the business flow.
2. `NotificationWorker` manages the async processing boundary.
3. Calls from `RegistrationService` to `NotificationWorker` through the Spring-managed dependency have the opportunity to go through the proxy.
4. Easy to test orchestration using a mock/fake worker, and test async behavior with a dedicated integration test.
5. Avoids circular dependencies or calling back into `ApplicationContext` just to retrieve the bean itself.

**Note:** if the caller does not retain and observe the `CompletableFuture`, there must be a proper failure-recording mechanism. Never discard the `Future` of important work while assuming it will succeed.

This is usually the best-balanced solution: clear structure without needing deep intervention in Spring AOP.

## 7. Another Option: Submit Tasks Directly via AsyncTaskExecutor

Not every requirement needs an annotation. If a service is responsible for task orchestration, it can explicitly call `executor.submit(...)` or `submitCompletable(...)`. In that case, asynchrony occurs **right at the submit call**, without relying on Java calling a method through a proxy.

Example:

```java
@Service
public class ReportService {
    private final AsyncTaskExecutor executor;

    public ReportService(
            @Qualifier("reportExecutor") AsyncTaskExecutor executor) {
        this.executor = executor;
    }

    public CompletableFuture<String> startReport(String reportId) {
        return executor.submitCompletable(
                () -> generateReport(reportId));
    }

    private String generateReport(String reportId) {
        // Background work can be a private method because
        // this is a Callable executed by executor submit, not an @Async proxy.
        return "report:" + reportId;
    }
}
```

This is a **fragment**, requiring Spring Framework with `AsyncTaskExecutor.submitCompletable(...)` (Spring 6.1+), a suitable `reportExecutor` bean, `@Service`, `@Qualifier`, and corresponding imports.

Pros:

- Avoids the `@Async` self-invocation problem when calling private `generateReport`: the worker receives a lambda created by `submitCompletable`.
- Clearly separates where tasks are submitted from business methods.
- Can receive a `CompletableFuture<String>` to manage results and exceptions.

Cons:

- Business/orchestration code is aware of the executor API rather than relying solely on annotations.
- Must manage results, timeouts, rejection, and context propagation like any background task.
- Does not automatically turn blocking I/O inside the method into non-blocking I/O; it only shifts where it runs to the executor.

**API note:** basic `TaskExecutor` only has `execute(Runnable)`; if you need `submitCompletable`, use an appropriate `AsyncTaskExecutor`.

## 8. Can You Retrieve the Proxy Yourself or Self-Inject the Bean?

Technically, certain indirect workarounds can route calls through the proxy—such as looking up the bean via `ApplicationContext`, self-injection through an appropriate indirection, or using `AopContext.currentProxy()` when AOP is configured with `exposeProxy` and the call runs inside the proper proxy context.

However, this is **not the recommended default approach**, because:

- The class begins depending directly on the container/AOP infrastructure.
- Self-injection can introduce circular dependencies, is hard to follow in constructors, and depends on Spring configuration.
- `AopContext.currentProxy()` requires extra configuration, does not work for every call, and makes business code harder to reuse outside a proxy context.
- Code readers find it harder to understand business boundaries compared to splitting into two beans.

If a design has to call its own proxy to "activate an annotation," treat that as a signal to re-evaluate the class's responsibilities. **Extracting the worker into a separate bean** is usually simpler and more testable.

## 9. Can AspectJ Handle Self-Invocation?

Yes, but you must understand this is a **different advice mode**, not merely an option to switch proxy types.

With `@EnableAsync(mode = AdviceMode.PROXY)` (default), Spring uses an AOP proxy: method self-calls do not go through the advice.

With `@EnableAsync(mode = AdviceMode.ASPECTJ)`, Spring can apply advice via AspectJ weaving onto classes. When **weaving is actually configured and active** (compile-time or load-time weaving, along with corresponding dependencies such as `spring-aspects`), internal calls can be intercepted because the advice no longer depends on the proxy boundary.

Illustrative declaration:

```java
@Configuration
@EnableAsync(mode = AdviceMode.ASPECTJ)
public class AsyncAspectConfig {
    // Requires actual AspectJ weaving configuration and dependencies.
}
```

This is **not a standalone runnable example**: adding this annotation without properly configured weaving will not automatically make self-invocation asynchronous. Moreover, choosing AspectJ increases build/deploy/debug complexity. Use it when there are AOP requirements across many call sites that truly justify it; do not switch an entire system to weaving just to fix one self-invoked method.

**Do not confuse `proxyTargetClass=true` with AspectJ.** This attribute only selects class-based proxies within `PROXY` mode; self-calls still bypass the advice.

## 10. When Self-Invocation Alters Exception and Future Semantics

Suppose an `@Async` method is designed to return `CompletableFuture<String>`:

```java
@Async("mailExecutor")
public CompletableFuture<String> calculate() {
    // May throw an exception before creating the Future or
    // return a CompletableFuture containing the result.
    return CompletableFuture.completedFuture("ok");
}
```

If the caller goes through the proxy, Spring executes the method on the executor and returns an async handle; exceptions from the method are handled according to the corresponding `Future`/`CompletionStage` contract.

If the target calls `this.calculate()` on itself, the async interceptor **does not run**:

- All code before the `return` statement executes immediately on the calling thread.
- The method returns the exact `CompletableFuture` object created by the body, without going through the async advice's submission step.
- If the body throws a runtime exception directly before returning the `Future`, that exception can escape **synchronously** from the self-call.
- With calls through the proxy, errors in the task are typically observed via `Future.get()`/`CompletableFuture.join()`; if it is a `void` async method, there is no `Future` for the caller to inspect errors, so you must configure an `AsyncUncaughtExceptionHandler` or another recording mechanism.

Therefore, self-invocation does not only affect performance. It can alter **where errors are caught, when errors occur, and request behavior**.

### Distinguishing get() and join()

- `CompletableFuture.get()`: throws `ExecutionException` (along with checked `InterruptedException`).
- `CompletableFuture.join()`: throws `CompletionException` (unchecked) on error.
- Both can **block the caller** if the `Future` has not completed yet, so do not place them casually on an event loop or latency-sensitive request thread.

## 11. Nested @Async: Already Being on a Worker Does Not Make a New Call Async

Look at this fragment:

```java
@Service
public class Pipeline {
    @Async("mailExecutor")
    public CompletableFuture<Void> outer() {
        this.inner();
        return CompletableFuture.completedFuture(null);
    }

    @Async("mailExecutor")
    public void inner() {
        // Inside outer(), this will run directly on the current thread.
    }
}
```

If another bean calls `pipeline.outer()` through the proxy, `outer()` is dispatched to the pool. However, `this.inner()` inside `outer()` still does not pass through the proxy, so `inner()` runs directly on the same thread processing `outer()`.

This is especially important when you want subtasks to be submitted independently, run in parallel, or have separate error handling. Seeing the thread name `mail-1` in both methods does not prove two separate tasks were created. Use instrumentation on submitted task counts, correlation ID logs, conditional timing, and controlled execution tests to verify.

Similarly, if `outer()` throws an exception, inspect the outer `Future`; do not assume an error from an internal self-call is handled as an independent async submission.

## 12. Other Situations Often Mistaken for Self-Invocation

### 12.1. Missing @EnableAsync

Without annotation-processing configuration in plain Spring Framework, `@Async` may remain mere metadata on the method. Enable `@EnableAsync` or the appropriate XML `<task:annotation-driven>`.

### 12.2. Non-Spring-Managed Bean

`new MailWorker().deliver("E")` is an ordinary Java call. It does not go through a container-created proxy.

### 12.3. Private, Final, or Non-Proxy-Interface Methods

Proxy-based AOP cannot intercept calls that are unavailable on the appropriate proxy surface. Private methods and final methods with class proxies are not reliable places for `@Async`. With JDK proxies, verify that the method is exposed via the proxied interface.

### 12.4. Constructors and @PostConstruct

Inside the target's constructor, the bean has not yet gone through all required post-processing. Calling `@Async` on yourself from a constructor or `@PostConstruct` is not an appropriate way to trigger asynchronous initialization. Following Spring's guidance, you can use **another initializing Spring bean** to call the target's `@Async` method through the ready dependency after the container creates the beans.

### 12.5. Synchronously Executing Executor

Although self-invocation bugs are common, there are still cases where the proxy works but the executor is configured synchronously or the caller immediately waits for the result; inspect the actual implementation and caller timing/blocking instead of drawing conclusions from a single log line.

### 12.6. Enlarging the Async Pool Does Not Solve the Root Cause

When a call bypasses the proxy, no task is submitted through the interceptor for that method. Changing `corePoolSize`, `maxPoolSize`, `queueCapacity`, or the thread prefix cannot turn a self-call into a proxy call. Before tuning, measure **task submissions** and confirm the proper AOP boundary.

## 13. ThreadLocal, Transactions, and Data Side Effects

If the call is successfully intercepted and runs on a worker, you must consider the thread switch:

- **ThreadLocal/MDC:** values bound to the HTTP/request thread are not automatically available on the worker; use an appropriate context propagation mechanism or `TaskDecorator` when genuinely needed.
- **Security context:** not copied by default; use a properly designed propagation mechanism rather than sneaking request objects across.
- **Transactions:** the caller's thread-bound transaction does not automatically transfer to the async worker. A `@Transactional` method on the same bean also has the same self-invocation proxy limitation in `PROXY` mode, though you must distinguish transaction semantics from async semantics.
- **JPA persistence context:** entities/lazy-loaded data may no longer be valid when the worker runs after the request/transaction; pass identifiers/DTOs and open an appropriate transaction on the worker side.
- **Consistency:** async work may start before the caller's transaction commits. For post-commit follow-up processing, consider commit-bound events or an outbox when reliability is required.

A notable consequence: in a self-call that accidentally runs synchronously, you might think `@Async` is "carrying transactions/MDC," when in fact no thread switch happened at all. When you fix it into a cross-bean call, suddenly losing context is the **expected behavior at the new thread boundary**. Design intentional context propagation rather than reverting to self-invocation to preserve thread state.

## 14. Proper Testing and Performance Observation

### 14.1. Do Not Check Only isDone()

A method called directly that returns `CompletableFuture.completedFuture(...)` will have `isDone() == true`. A very fast async call can also produce a completed `Future` before you check it. Therefore, `isDone()` **does not prove** whether the method was routed to another thread by the interceptor.

### 14.2. Compare Threads and Use Latches Instead of Sleep

The runnable example in Section 4 captures the thread name when the caller starts, and configures the worker's prefix via `setThreadNamePrefix("mail-")`. This reduces timing dependence compared to `Thread.sleep(100)`.

If a test needs to prove the caller **returns before the worker finishes**, use a `CountDownLatch`, `Phaser`, or a test executor to hold the task at a deterministic point. Use finite timeouts to prevent tests from hanging if logic changes.

### 14.3. Inspecting Proxies with AopUtils

`AopUtils.isAopProxy(bean)` returns true when the reference is an AOP proxy. It aids diagnosis: if false, one of the configuration conditions may not be met. Yet a true result does not confirm that a specific method was selected by the advice, because advisors have pointcuts and self-calls still bypass the proxy.

You must inspect proxy type, method signature, annotation, executor selection, and call path together. An integration test going through the bean reference just like production is more valuable than a unit test instantiating the target with `new`.

### 14.4. Do Not Use Thread Names as Business Logic

An executor's prefix is useful for debugging and illustrative tests. In production, do not use `Thread.currentThread().getName().startsWith(...)` to decide transaction correctness, access permissions, ordering, or completion status. Threads can be reused, reconfigured, or be virtual threads depending on the implementation; business behavior must rely on explicit contracts.

## 15. Common Troubleshooting Reference Table

| Symptom | Possible Cause | Fix / Check |
| --- | --- | --- |
| `this.asyncMethod()` runs immediately inside a method of the same bean | Self-invocation bypasses proxy | Split into another bean or submit via executor |
| `@Async` is on the method, yet all calls are synchronous | Async processing not enabled or bean not Spring-managed | `@EnableAsync`, `ApplicationContext`, proper method visibility |
| `AopUtils.isAopProxy(bean)` is true, yet the call is still synchronous | Call path is inside the target or method is not advised | Trace call graph and method signature |
| `proxyTargetClass=true` is enabled, yet self-calls are still synchronous | Class proxies still require external interception | Do not treat CGLIB as the fix; split beans |
| Private/final `@Async` method does not behave as expected | Proxy cannot intercept the method | Make the method public/accessible via the proxy |
| Called inside constructor or `@PostConstruct` | Bean/proxy not ready for that call | Trigger via another bean after appropriate lifecycle phase |
| Moved to another bean, yet `this.otherAsync()` runs on the worker | Only the outer call went through the proxy | Separate subtasks with clear boundaries; do not equate "already on pool" with a new interception |
| After fixing, MDC or transaction is missing | Worker runs on a different thread | Design context propagation and separate transaction |
| Exception is no longer thrown in the caller | Async exceptions flow through `Future`/handler | Capture `Future`, configure error reporting |
| Increasing the thread pool changes nothing | No async submission happens for self-calls | Verify the proxy boundary before tuning |
| Test always passes because `Future` is already completed | Test does not check thread or concurrency | Use latches and verify the actual call path |

## 16. Self-Check Questions

**Question 1.** `@EnableAsync` and a properly named `ThreadPoolTaskExecutor` bean are configured. Why does `this.sendMail(id)` still run synchronously?

Because in `AdviceMode.PROXY`, internal calls on the target do not go through the proxy. The async interceptor is not applied at this call site, regardless of whether the executor exists.

**Question 2.** Does switching to `@EnableAsync(proxyTargetClass = true)` solve it?

No. That parameter only chooses class-based proxies instead of JDK interface proxies within `PROXY` mode; it does not create interception for self-calls.

**Question 3.** Another bean has `MailWorker` injected and calls `worker.deliver()`. Is that different?

Yes. When the reference provided by Spring is a proxy and the method matches the advice, calls from another bean go through the proxy, so `@Async` can submit the task to the executor.

**Question 4.** If `@Async outer()` is called externally and inside `outer()` it calls `this.innerAsync()`, why do logs from `innerAsync()` still appear on the thread pool?

Because `outer()` was already routed to a worker; `innerAsync()` runs **directly on that same worker**, not because an additional async interception occurred.

**Question 5.** How can you run work asynchronously without relying on Spring AOP proxies?

Inject `AsyncTaskExecutor`/`Executor` and submit a `Runnable` or `Callable` via `execute/submit/submitCompletable`. This is explicit task submission and does not depend on self-invocation proxies.

**Question 6.** Does AspectJ help intercept self-invocation?

Yes, when `AdviceMode.ASPECTJ` is genuinely enabled with full AspectJ weaving and dependencies. Simply changing the annotation without weaving is insufficient. For typical business tasks, splitting into another bean is usually less complex.

## 17. Pre-Production Checklist

- **Entry point:** does the caller get the reference from the Spring `ApplicationContext` or use `new`?
- **Advice enabled:** is `@EnableAsync` or XML `<task:annotation-driven>` registered in the right context?
- **Call path:** is the method called from another bean through the proxy or via `this.method()`?
- **Signature:** can the method be intercepted by the proxy? Does it hit private/final/interface mismatch?
- **Executor:** does `@Async("...")` point to the right bean, with appropriate pool sizing/queue/rejection bounds?
- **Verification:** is there an integration test proving the caller thread differs from the worker thread or showing independent submission, without using `Thread.sleep` to guess timing?
- **Results/errors:** `void` vs `CompletableFuture`, who observes exceptions, timeouts, and cancellation?
- **Context:** are transactions, security, logging MDC, and JPA data handled properly on the new thread?
- **Lifecycle:** are async calls in constructors/`@PostConstruct` avoided, and is there a clear shutdown policy?
- **Durability:** do critical tasks need an outbox/broker instead of only an in-process queue?

## 18. Conclusion

**Core reason:** in Spring `@Async` under the default proxy mode, advice only runs when a call passes through the Spring proxy. Calling `this.asyncMethod()` inside the same target bean is a normal Java call that **does not pass through the proxy**, so it does not trigger the interceptor and does not submit a new task to the executor for that method.

The readable, testable, and usually preferred fix: **move the async method into a separate Spring-managed bean and invoke it through the injected dependency**. If you need an explicit task-submission point, you can use `AsyncTaskExecutor.submit(...)`/`submitCompletable(...)`. AspectJ weaving is an advanced option requiring separate configuration and is not synonymous with `proxyTargetClass=true`.

Do not diagnose solely from annotations, thread names, or `Future.isDone()`. Verify the **proxy boundary, call path, and actual task submission**.

### References

- [Spring Framework — Task Execution and Scheduling: Annotation Support](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework 6.2 — EnableAsync API](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Spring Framework 6.2 — Async API](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/scheduling/annotation/Async.html)
- [Spring Framework — Understanding AOP Proxies](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)