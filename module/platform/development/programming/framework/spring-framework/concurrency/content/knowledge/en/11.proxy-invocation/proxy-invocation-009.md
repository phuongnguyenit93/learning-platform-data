# Recognizing AspectJ Mode and Weaving Requirements When Another Option Is Needed

In the Spring Framework, `@Async` normally works through a **Spring AOP proxy**. When another bean calls a method annotated with `@Async` **through the proxy**, advice dispatches the work to an executor; however, when a method in the same bean calls `this.asyncMethod()`, the internal call does not pass through the proxy, so the advice is not triggered. This is an important limitation of `AdviceMode.PROXY`.

Spring also supports **`@EnableAsync(mode = AdviceMode.ASPECTJ)`**. In this mode, `@Async` advice does not reside solely on a proxy object; AspectJ can intercept at the **method execution join point** once application code **has been woven**. Consequently, self-invocation can be intercepted. Yet merely changing the `mode` enum is not enough: you need the `spring-aspects` module, actual compile-time or load-time weaving, and tests verifying that the required classes' bytecode was transformed.

This lesson belongs to the **Proxy and Invocation** group, focusing on how to **recognize when AspectJ is warranted**, its technical dependencies, and practical limits—without assuming every Spring application needs weaving.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the default `AdviceMode.PROXY` and why `this.method()` does not trigger Spring AOP proxy advice.
- Distinguish JDK dynamic proxies, class-based proxies, and AspectJ bytecode weaving.
- Describe `AdviceMode.ASPECTJ`, how attaching advice to method execution differs, and why self-invocation can work.
- Identify the minimum requirements: `@EnableAsync(mode=AdviceMode.ASPECTJ)`, `spring-aspects`, a compatible compiler/weaver, and target classes actually being woven.
- Distinguish compile-time weaving (CTW), post-compile weaving, and load-time weaving (LTW).
- Recognize that `@EnableAspectJAutoProxy`, `proxyTargetClass=true`, or merely adding dependencies is **not equivalent** to weaving.
- Build examples and tests without `Thread.sleep`, verifying executing threads and completion timing.
- Weigh refactoring into separate beans or using `TaskExecutor` directly before increasing build/deployment complexity.

## 2. How @Async Works with Spring Proxies

In a common configuration:

~~~java
@Configuration
@EnableAsync
public class AppAsyncConfig {
}
~~~

This is a **Spring configuration snippet** (requiring imports for `Configuration` and `EnableAsync`), not a standalone runnable Java program. `@EnableAsync` without specifying `mode` uses **`AdviceMode.PROXY`**, Spring's default mechanism.

Execution flow when one component calls another bean:

~~~text
Caller (thread A)
       |
       v
Spring-managed reference -> proxy
       |
       +-- @Async interceptor
               |
               +-- submit work -> TaskExecutor
                       |
                       +-- worker thread B runs target method
~~~

In practice it also depends on the executor: `SyncTaskExecutor` runs on the caller, and `CallerRunsPolicy` can run on the caller when the pool is saturated. Therefore, even when advice intercepts the call, never promise there will always be a different physical thread.

### Self-Invocation: Why Does Calling Yourself Bypass the Proxy?

~~~text
Caller -> proxy -> target.outer()
                        |
                        +-- this.innerAsync()
                                   |
                                   +-- directly target.innerAsync()
                                       DOES NOT go through proxy
~~~

In Java, `this.innerAsync()` happens inside the target object. The Spring proxy is not invoked again, so `@Async` on `innerAsync` has no opportunity to take effect on that call path.

Example:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ExportService {
    public CompletableFuture<String> begin(String exportId) {
        return perform(exportId); // self-invocation
    }

    @Async("exportExecutor")
    public CompletableFuture<String> perform(String exportId) {
        return CompletableFuture.completedFuture("done:" + exportId);
    }
}
~~~

This is a **Spring service**, not a standalone runnable file because it requires a Spring context. If another bean calls `exportService.perform("A")` through the proxy, advice can hand the body off to the executor. If another bean calls `exportService.begin("B")`, `begin` calls `perform` on itself; in `PROXY` mode, the body of `perform` runs directly on `begin`'s thread.

Because the body is very fast, `CompletableFuture.isDone()` may be `true` on both paths; **do not use status immediately after the call as your sole test**. Hold the body with a latch or record thread identity when verifying.

## 3. JDK Proxies, CGLIB Proxies, and AspectJ Are Three Different Concepts

| Component | Role | Does It Fix @Async Self-Invocation? |
| --- | --- | --- |
| JDK dynamic proxy | Interface-based proxy | No: self-calls still bypass the proxy |
| Class-based proxy (typically CGLIB) | Subclass-based proxy | Does not solve internal self-calls inside the target |
| AspectJ weaving | Transforms class bytecode, attaches advice at join points | Potentially yes: when the method is woven and matches the pointcut |
| `@EnableAspectJAutoProxy` | Enables Spring AOP using `@AspectJ` syntax | **Not sufficient** to perform AspectJ bytecode weaving |
| `@EnableAsync(mode=AdviceMode.ASPECTJ)` | Selects AspectJ advice mode for async | **Not sufficient** without compiler/weaver and aspect |

`proxyTargetClass=true` applies when Spring is **using proxy mode**: it chooses subclass proxies over interface proxies where appropriate. With `AdviceMode.ASPECTJ`, Spring explicitly documents that `proxyTargetClass` **is ignored** for async advice. That attribute cannot substitute for weaving.

Similarly, `@EnableAspectJAutoProxy` is easily misunderstood because it contains the word "AspectJ", yet that infrastructure primarily uses **proxy-based Spring AOP** to execute advice written with `@Aspect` syntax. It does not turn every class into bytecode modified by the AspectJ compiler/weaver.

## 4. How Does AspectJ Mode Intercept?

`@EnableAsync(mode = AdviceMode.ASPECTJ)` selects the mechanism using the `org.springframework.scheduling.aspectj.AnnotationAsyncExecutionAspect` aspect from the `spring-aspects` module. Once weaving has actually been applied to the target class, advice intercepts at the method execution join point. Both external calls and calls inside the object reach the woven execution join point.

~~~text
Caller -> calls WorkService.outer()
                    |
                    +-- this.innerAsync()
                               |
                               +-- woven EXECUTION join point
                                      |
                                      +-- async advice / executor
                                             |
                                             +-- worker executes body
~~~

This differs fundamentally from a Spring proxy that only intercepts calls **going through a proxy reference**. That is why AspectJ mode is the solution documented by Spring for cases needing advanced interception, such as self-invocation.

However, mandatory requirements still apply:

- `@Async` must have a supported signature: `void` or an appropriate `Future` type, including `CompletableFuture`.
- The annotation and method execution point must match the pointcut supported by `AnnotationAsyncExecutionAspect`.
- The class containing the method must actually be woven, not merely Spring component-scanned.
- The aspect must be able to locate the executor and/or be properly configured by Spring.
- The executor must still accept work; overload, shutdown, and task errors can still occur.
- `@Async` is not supported on methods declared inside `@Configuration` classes under Spring's annotation contract.

**Do not extrapolate:** AspectJ does not make every constructor, lifecycle callback, or arbitrary Java method asynchronous. It only adds advice at woven join points matching the aspect definition. Spring also warns against combining `@Async` directly with lifecycle callbacks such as `@PostConstruct`.

## 5. What Is Weaving, and Why Can It Not Be Skipped?

**Weaving** is the process of inserting aspects/advice into the bytecode of target classes. For Spring `@Async` in AspectJ mode, simply putting `spring-aspects.jar` on the classpath **is not enough**: a weaving tool must run to modify the class files executed by the JVM.

There are three mechanisms worth knowing:

| Mechanism | When Does Weaving Happen? | Pros | Caveats |
| --- | --- | --- | --- |
| Compile-time weaving (CTW) | At build/compile time via the AspectJ compiler `ajc` | Woven artifacts are fixed and easy to verify before deployment | Build tool and compiler must support the Java bytecode version |
| Post-compile / binary weaving | After `javac` produces classes, run `ajc` on classes/JARs | Can separate the weaving step from regular compilation | Must ensure the final artifact is the woven version |
| Load-time weaving (LTW) | When the JVM loads classes, via agent/transformer | No need to produce woven classes at build time if runtime supports it | Classloaders, startup, load timing, and deployment are more complex |

### CTW: Weaving During Build

~~~text
Java source + annotations + Spring aspects
                  |
                  v
          AspectJ compiler / ajc
                  |
                  v
            Woven classes
                  |
                  v
        Package, deploy, run
~~~

Plain `javac` **does not** perform AspectJ weaving. If a project only runs the standard Maven Java compiler plugin, `@EnableAsync(mode=ASPECTJ)` will not modify `.class` files on its own. For CTW, you must configure `ajc`/an AspectJ build plugin with the proper aspect path and weave targets.

An advantage of CTW is that `.class` files in the final artifact can be verified before deployment. In exchange, the pipeline must ensure the AspectJ compiler understands the source/class target in use; especially when upgrading Java versions, verify `ajc` compatibility.

### LTW: Weaving When the JVM Loads Classes

~~~text
JVM startup
   |
   +-- AspectJ weaver/agent active
   |
   +-- discovers META-INF/aop.xml and aspect definitions
   |
   +-- classloader loads com.example.ExportService
                 |
                 +-- transforms bytecode at load time
                 |
                 +-- JVM defines woven class
~~~

If a class needing weaving was already loaded **before** the weaver became active, enabling an annotation or adding an agent afterward will not automatically ensure the class is rewritten. Normally the JVM must be started with the proper configuration from the beginning, or use a separately supported and verified instrumentation/retransformation solution.

A common LTW invocation uses the AspectJ Java agent:

~~~bash
java -javaagent:/opt/app/lib/aspectjweaver.jar -jar app.jar
~~~

This is a **sample command for a system that already has `aspectjweaver.jar` at that path**, not an automatic installation command. The `-javaagent` flag is a **JVM option** and must appear before `-jar`. `spring-aspects` must be on the application's runtime classpath; the classloader must see both the aspect and the woven classes.

Spring also provides `@EnableLoadTimeWeaving` and classloader-based `LoadTimeWeaver` mechanisms; in some environments `spring-instrument.jar` may be used to supply instrumentation. Distinguish the Spring instrumentation agent from the AspectJ weaver, and do not claim that merely adding `@EnableLoadTimeWeaving` makes all AspectJ `@Async` work.

## 6. Required Components When Choosing ASPECTJ

Four conditions must align:

1. **Advice mode:** configure `@EnableAsync(mode = AdviceMode.ASPECTJ)` in the appropriate Spring `ApplicationContext`.
2. **Spring aspect:** the `org.springframework:spring-aspects` module, containing `AnnotationAsyncExecutionAspect` and aspect metadata.
3. **Weaving tool:** the `ajc` AspectJ compiler for CTW or a compatible AspectJ weaver/agent for LTW; weaving must target **the exact target class**.
4. **Executor/configuration/tests:** the executor is resolved, classes are not loaded too early, the aspect genuinely intercepts, and tests verify the self-call path works.

Maven dependency example—**only a fragment inside `<dependencies>` of a project whose versions are managed by a Spring Boot BOM/parent**:

~~~xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-aspects</artifactId>
</dependency>
<dependency>
    <groupId>org.aspectj</groupId>
    <artifactId>aspectjweaver</artifactId>
</dependency>
~~~

Without dependency management, each dependency needs a version compatible with the project's Spring and JDK versions. With CTW, an AspectJ build plugin/compiler and weave configuration are also required; merely adding these two dependencies does not replace that step.

`spring-aspects.jar` ships `META-INF/aop.xml` to register common Spring aspects, including `AnnotationAsyncExecutionAspect`. With LTW, AspectJ typically reads `META-INF/aop.xml` metadata from the runtime classpath. If you supply your own config file with include/exclude filters, ensure your classes **are not excluded from weaving** and aspects are not arbitrarily registered twice.

## 7. Spring Example Using Default PROXY Mode

File **DefaultAsyncConfig.java**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class DefaultAsyncConfig {

    @Bean(name = "exportExecutor")
    public ThreadPoolTaskExecutor exportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("export-");
        return executor;
    }
}
~~~

File **ExportService.java** (as in the earlier example):

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ExportService {
    public CompletableFuture<String> begin(String exportId) {
        return perform(exportId);
    }

    @Async("exportExecutor")
    public CompletableFuture<String> perform(String exportId) {
        return CompletableFuture.completedFuture("done:" + exportId);
    }
}
~~~

These are **two classes of a Spring application**, requiring a Spring context and libraries; they cannot run standalone with `java ExportService`. Do not redundantly call `initialize()` on an executor managed by the container.

Call-path outcome:

| Call from Another Bean | PROXY Mode |
| --- | --- |
| `exportService.perform("A")` | Called through proxy; async advice can submit the task to `exportExecutor` |
| `exportService.begin("B")` | `begin` runs and calls `perform` on target itself; `@Async` is not intercepted via proxy |

In this example, the `Future` may finish very quickly, so do not measure the call path using an immediate `future.isDone()`; record thread identity or add a latch with a controlled timeout.

### Usually Better Alternative: Split Beans

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.stereotype.Service;

@Service
public class ExportStarter {
    private final ExportWorker worker;

    public ExportStarter(ExportWorker worker) {
        this.worker = worker;
    }

    public CompletableFuture<String> begin(String exportId) {
        return worker.perform(exportId);
    }
}
~~~

File **ExportWorker.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ExportWorker {
    @Async("exportExecutor")
    public CompletableFuture<String> perform(String exportId) {
        return CompletableFuture.completedFuture("done:" + exportId);
    }
}
~~~

These are **two classes in separate files** with Spring libraries. `ExportStarter` injects the Spring-managed `ExportWorker`, so `worker.perform(...)` goes through the bean's proxy reference instead of self-invocation. If the issue is just an internal method, this refactoring is usually simpler, more transparent, and avoids introducing AspectJ weaving into build/deployment.

Another option is submitting a `Runnable` or `Callable` directly to a `TaskExecutor` at the point where you want a thread switch; that does not depend on proxy interception, though you must actively manage the `Future`, exceptions, and lifecycle.

## 8. Alternative Configuration: ASPECTJ Mode

When refactoring is unsuitable and interception inside a class is genuinely needed, configuration can look like:

File **AspectJAsyncConfig.java**:

~~~java
import org.springframework.context.annotation.AdviceMode;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync(mode = AdviceMode.ASPECTJ)
public class AspectJAsyncConfig {

    @Bean(name = "exportExecutor")
    public ThreadPoolTaskExecutor exportExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("export-");
        return executor;
    }
}
~~~

Choose only **one appropriate `@EnableAsync` configuration** in the `ApplicationContext` for a test scenario; do not load both sample config classes side by side as competing configurations. `@EnableAsync(mode=ASPECTJ)` is meaningful once **Spring aspects + real weaving** are in place. If `ExportService` has been woven, `begin("B")` can trigger advice on `perform`'s execution even though called inside the same bean.

There is no proxy **for async interception under AspectJ mode**, yet other Spring AOP features can still create proxies independently. Enabling AspectJ for `@Async` does not mean `@Transactional` or all other advice automatically switches to AspectJ mode.

Likewise, this configuration:

~~~java
@EnableAsync(mode = AdviceMode.ASPECTJ, proxyTargetClass = true)
~~~

is an **annotation fragment**; `proxyTargetClass` is ignored in AspectJ mode and does not create "stronger weaving." To verify AspectJ, inspect build agent settings, weave-info output, and integration test results, rather than relying on a proxy flag.

## 9. Standalone Java 17+ Example: Self-Call Bypassing a Wrapper

This example illustrates the **proxy call-path principle using a plain Java wrapper**, without depending on Spring/AspectJ. The wrapper submits `work()` to an executor when a caller invokes it through the wrapper, yet `Target.entry()` calls `work()` on `this` and bypasses the wrapper. This is not a full Spring AOP implementation; it solely demonstrates why self-invocation produces a different outcome.

File **ProxyBoundaryDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public final class ProxyBoundaryDemo {
    interface WorkPort {
        void entry();
        void work();
    }

    static final class Target implements WorkPort {
        final CountDownLatch done = new CountDownLatch(1);
        final AtomicReference<Thread> executedBy = new AtomicReference<>();

        @Override
        public void entry() {
            work(); // this.work(), does not pass through wrapper
        }

        @Override
        public void work() {
            executedBy.set(Thread.currentThread());
            done.countDown();
        }
    }

    static final class DispatchWrapper implements WorkPort {
        private final Target target;
        private final ExecutorService executor;

        DispatchWrapper(Target target, ExecutorService executor) {
            this.target = target;
            this.executor = executor;
        }

        @Override
        public void entry() {
            target.entry();
        }

        @Override
        public void work() {
            executor.execute(target::work);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        Thread caller = Thread.currentThread();

        try {
            Target first = new Target();
            WorkPort wrapper1 = new DispatchWrapper(first, executor);

            wrapper1.work(); // passes through wrapper -> executor
            if (!first.done.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Async task timed out");
            }
            System.out.println(
                    "externalUsesWorker=" + (first.executedBy.get() != caller));

            Target second = new Target();
            WorkPort wrapper2 = new DispatchWrapper(second, executor);

            wrapper2.entry(); // wrapper -> target.entry -> this.work
            if (!second.done.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Self-call timed out");
            }
            System.out.println(
                    "selfCallUsesCaller=" + (second.executedBy.get() == caller));
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Compile/run with Java 17 or later:

~~~bash
javac ProxyBoundaryDemo.java
java ProxyBoundaryDemo
~~~

Stdout of a successful run:

~~~text
externalUsesWorker=true
selfCallUsesCaller=true
~~~

Explanation:

1. `wrapper1.work()` calls `executor.execute(target::work)`; `Target.work()` runs on a worker thread different from the main thread. `CountDownLatch` proves the task ran before reading the result.
2. `wrapper2.entry()` simply delegates to `target.entry()`. Inside `entry()`, `work()` is called directly on `Target` without passing through `DispatchWrapper.work()` at all; it runs on the caller.
3. No `Thread.sleep` is used to guess thread scheduling. We compare **Thread objects** and wait on a latch, so the result does not depend on thread names or machine speed.

After weaving, AspectJ can place interception at the `execution` of `work()`, unlike the wrapper model. Therefore, you need a **dedicated integration test with Spring + weaver** to verify real behavior, rather than treating this plain Java example as proof that AspectJ is configured successfully.

## 10. Testing Real Self-Invocation with Spring

A proper test should cover two separate scenarios: **PROXY mode** and **woven ASPECTJ mode**. Do not attempt to toggle modes continuously inside the same running `ApplicationContext`.

File **AsyncProbeService.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncProbeService {

    public CompletableFuture<String> callInside(
            CountDownLatch entered, CountDownLatch release) {
        return asyncWork(entered, release); // self-invocation
    }

    @Async("exportExecutor")
    public CompletableFuture<String> asyncWork(
            CountDownLatch entered, CountDownLatch release) {
        entered.countDown();
        try {
            if (!release.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Wait timed out");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", ex);
        }
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName());
    }
}
~~~

This is a **Spring test service**, requiring an `ApplicationContext` and having no `main` method of its own. Pass two latches per invocation so no per-test mutable state is stored in the singleton bean.

### Testing PROXY Mode

- Another bean/test injects `AsyncProbeService`; calling `asyncWork(entered, release)` externally through the proxy dispatches to the executor if properly configured.
- With `callInside(entered, release)`, the body of `asyncWork` is invoked directly inside the same bean. Because it awaits `release`, the `callInside` call **blocks** until the test releases the latch.
- To prevent the test thread itself from hanging, call `callInside` from a test helper thread, await `entered`, and then open `release`. Verify the returned thread name matches the helper thread.
- Use timeouts on every wait and shut down the helper executor in `finally`.

### Testing Woven ASPECTJ Mode

- Create another `ApplicationContext` with `@EnableAsync(mode=ASPECTJ)`; ensure `AsyncProbeService` is woven via CTW/LTW and `exportExecutor` has capacity.
- Call `callInside(entered, release)` from the test thread. The execution of `asyncWork` is woven, so it can dispatch to the executor and return a `CompletableFuture` before the body exits `release.await()`.
- Wait on `entered.await(timeout)` to confirm the worker entered the body; before opening `release`, the future should not be done yet.
- Open `release`, retrieve the result via `future.get(timeout)`, and compare the thread name against the calling thread; even better, record/pass thread identity via a test fixture.
- Enable weave-info in the test environment or inspect woven classes to prove the class/method was genuinely advised.

**Avoid misreading results:** an executor like `SyncTaskExecutor` or a saturated `CallerRunsPolicy` can execute the body directly on the caller **even when AspectJ advice already ran**. Therefore, tests should use a true asynchronous executor with available queue space, and clearly separate "advice intercepted" from "which thread executed it."

## 11. Things AspectJ Does Not Solve Automatically

### Return Types and Exceptions

Methods annotated with `@Async` must follow supported signatures: `void` or an appropriate `Future`, including `CompletableFuture`. Inside the worker, the target method can return `CompletableFuture.completedFuture(value)`; the caller holds the `Future` managed by the advice. A method returning `String` annotated with `@Async` does not become a valid asynchronous method merely through weaving. `AnnotationAsyncExecutionAspect` also flags weaving errors/warnings for incompatible signatures.

With `@Async void`, exceptions in the body normally go to `AsyncUncaughtExceptionHandler`. With `Future`/`CompletableFuture`, callers have a way to observe exceptional completion. If the executor rejects immediately on submit, `TaskRejectedException` can appear at the submission boundary. Do not confuse submission rejection with body failure.

### Executor Overload and Shutdown

Both `PROXY` and `ASPECTJ` require a real executor. When the queue fills up, `AbortPolicy` raises a rejection; `CallerRunsPolicy` can run on the caller; a discard policy can drop tasks silently. AspectJ does not automatically raise `maxPoolSize`, retry tasks, or guarantee an async call always returns fast.

### Transactions and Thread Context

Async work on another thread does not automatically inherit transactions, security context, MDC, or `ThreadLocal` values from the caller. If work is submitted before a transaction commits, the worker may see uncommitted data or the request may later roll back. Define transaction boundaries and after-commit/outbox mechanisms where required.

Enabling AspectJ for `@Async` **does not** automatically switch `@Transactional` to AspectJ mode; each advice subsystem has its own configuration. If an application combines multiple advice types, test composition/ordering and thread context for the exact scenario.

### Durability and Multiple Replicas

A task waiting in an in-memory queue of one JVM can be lost if the process crashes. AspectJ weaving is not a durable queue and does not migrate jobs across replicas. For work that must complete across restarts, use a job store/message queue, retries, idempotency, and observable status.

## 12. Operational Cost and Version Compatibility

When choosing weaving, plan for:

- **Version matrix:** the AspectJ compiler/weaver must support the bytecode of the JDK in use; Spring modules and `spring-aspects` must be compatible. Upgrading the JDK may require upgrading AspectJ.
- **Build reproducibility:** with CTW, the release artifact must actually contain the woven classes; do not let packaging accidentally pick plain Java-compiled output.
- **Classloaders:** with LTW, the agent/weaver must be active when target classes load; Boot executable JARs, WARs, app servers, and test runners can handle classloading differently.
- **Weave scope:** restrict to necessary packages where possible to avoid touching too many classes, without accidentally excluding target classes.
- **Other instrumentation:** code coverage tools, profilers, tracing agents, and other bytecode enhancers may transform the same classes; test them together.
- **Startup/debugging:** LTW can slow down class loading and CTW lengthens build time; stack traces and woven bytecode can be harder to debug.
- **Deployment/rollback:** keep identical JVM flags, dependencies, and artifacts across CI, staging, and production; run smoke tests when updating runtimes.

Do not rely merely on seeing `spring-aspects` in the dependency tree to conclude weaving occurred. Combine **weave-info + integration tests + runtime artifact inspection**.

## 13. Common Mistakes and Misconceptions

1. **Adding only `mode=ASPECTJ` and assuming it is done.** Real aspects and actual weaving are required.
2. **Adding only `spring-aspects`.** Aspect definitions on the classpath do not modify bytecode on their own.
3. **Adding `aspectjweaver` dependency without running the agent/CTW.** The library does not activate itself.
4. **Treating `@EnableAspectJAutoProxy` as a weaving switch.** In normal usage that is proxy-based Spring AOP.
5. **Enabling `proxyTargetClass=true` to fix self-calls.** Neither JDK nor CGLIB changes `this.method()` calls inside the target.
6. **Using `javac` instead of `ajc` in a CTW pipeline.** Produces unwoven classes.
7. **Placing `-javaagent` in the wrong position on the JVM command line.** Startup options must precede `-jar` or the main class name.
8. **Forgetting `spring-aspects` at runtime or aspect metadata.** The weaver cannot find the Spring async aspect to apply.
9. **Wrong package/classloader or include/exclude rules.** Target classes are skipped by weaving.
10. **Classes loaded before LTW activates.** Changing configuration afterward does not retroactively weave already-loaded classes.
11. **Annotating only an interface without verifying implementation execution.** With AspectJ, annotate implementation methods/classes directly when needed.
12. **Expecting private/final/constructors/lifecycle callbacks to work unconditionally.** Weaving reaches farther than proxies, yet pointcuts and the `@Async` contract still impose limits.
13. **Assuming AspectJ creates a worker pool itself.** Executors still need configuration, sizing, and overload monitoring.
14. **Assuming `@Transactional` switches modes alongside `@Async`.** Each advice subsystem has independent configuration.
15. **Testing with `Thread.sleep` or `isDone()` on ultra-fast tasks.** Use latches and thread identity.
16. **Putting multiple competing `@EnableAsync` configs in the same test.** Verify one explicit mode per context.
17. **Ignoring `CallerRunsPolicy` when checking thread identity.** Successful advice can still run the task on the caller.
18. **Switching to AspectJ just to fix one simple self-invocation.** Splitting beans is usually easier to maintain.
19. **Not testing startup configuration on production packaging.** Different agents/classloaders can break LTW.
20. **Equating `@Async` with durable jobs.** Weaving does not guarantee completion across crashes/restarts.

## 14. Practical Decision Process

Start from the least complex option:

1. **Prove the problem.** Determine whether it is truly self-invocation, a call missing the proxy, or merely an executor policy running work on the caller.
2. **Check Spring-managed beans.** Is the method called via an injected reference? Is `@EnableAsync` in the right context? Does the method have a valid return type?
3. **Evaluate refactoring.** Extract the async method into another bean, or use an explicit `TaskExecutor` right at the dispatch site.
4. **Define advanced requirements.** Only if you must intercept many self-calls in classes that cannot reasonably be refactored should you consider AspectJ.
5. **Choose CTW or LTW.** CTW favors fixed woven artifacts at build time; LTW requires managing agents/classloaders/runtime flags.
6. **Control dependencies.** Match `spring-aspects` to the Spring version and match the AspectJ weaver/compiler to the bytecode level.
7. **Verify actual weaving.** Use weave-info and integration tests covering both external calls and self-calls; do not just read annotations.
8. **Measure operations.** Startup time, memory, thread pools, queues, p95/p99, submit/worker errors, and interactions with transactions and tracing.
9. **Keep a rollback path.** Keep bean structure clean enough to revert to proxy mode if operating weaving proves unsuitable.

| Context | Recommendation |
| --- | --- |
| Beans invoke each other through Spring injection | Keep `AdviceMode.PROXY` |
| Only one self-call is not running asynchronously | Split beans or use an explicit executor first |
| Many self-calls need interception and refactoring is infeasible | Consider `ASPECTJ` + weaving + integration tests |
| Cannot control JVM agents and the build pipeline | Avoid depending on `ASPECTJ` mode |
| Actual problem is full queues / high latency | Redesign executor/backpressure; do not switch advice modes |
| Need durable job processing across restarts | Job table/durable queue, not AspectJ |
| Multiple bytecode agents or custom classloaders exist | Test deployment compatibility before committing |
| Want easy-to-read and easy-to-debug code | Proxy mode with clear bean boundaries is usually preferable |

## 15. Self-Check Questions

1. What does `@EnableAsync` use by default when `mode` is omitted?
2. Why can `this.perform()` inside the same bean fail to run asynchronously even when `perform` has `@Async`?
3. Does enabling `proxyTargetClass=true` fix self-invocation? Why or why not?
4. Why is `@EnableAspectJAutoProxy` not synonymous with compile-time/load-time weaving?
5. Which conditions must all hold for `@EnableAsync(mode=ASPECTJ)` to actually intercept internal calls?
6. When does CTW differ from LTW, and what must you watch out for if classes load before the weaver is active?
7. Are `spring-aspects` and `aspectjweaver` merely appearing in the dependency tree enough to confirm self-calls are woven?
8. Why is placing `@Async` on the implementation method clearer when using AspectJ?
9. How do you use latches and thread identity to test self-calls under proxy vs. AspectJ?
10. Why does AspectJ not automatically alter `@Transactional`, executor policies, or guarantee survival across restarts?
11. When `CallerRunsPolicy` triggers, can a woven method still run on the caller?
12. If there is only a single self-invocation issue, which option generally carries lower operational risk than AspectJ?

## 16. References

- [Spring Framework — @EnableAsync API: PROXY and ASPECTJ](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — Using AspectJ with Spring Applications](https://docs.spring.io/spring-framework/reference/core/aop/using-aspectj.html)
- [Spring Framework — AOP Concepts](https://docs.spring.io/spring-framework/reference/core/aop/introduction-defn.html)
- [Spring source — AnnotationAsyncExecutionAspect.aj](https://github.com/spring-projects/spring-framework/blob/main/spring-aspects/src/main/java/org/springframework/scheduling/aspectj/AnnotationAsyncExecutionAspect.aj)
- [Spring source — spring-aspects META-INF/aop.xml](https://github.com/spring-projects/spring-framework/blob/main/spring-aspects/src/main/resources/META-INF/aop.xml)
- [AspectJ — Official Documentation](https://eclipse.dev/aspectj/doc/latest/index.html)

**Key takeaway:** `AdviceMode.PROXY` handles calls passing through the Spring proxy, so self-invocation normally bypasses `@Async`. `AdviceMode.ASPECTJ` can intercept at method execution including self-calls **if the bytecode has been woven**. It is an advanced solution requiring AspectJ tooling, Spring aspects, build/runtime configuration, and integration tests; if extracting a bean solves the problem, proxy mode remains clearer and lighter.