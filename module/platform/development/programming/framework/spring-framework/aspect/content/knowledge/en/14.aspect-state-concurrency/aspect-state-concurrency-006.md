# ThreadLocal in Aspects and Data Cleanup Responsibilities in Spring AOP

## 1. The Problem to Solve

A Spring `@Aspect` used for logging, profiling, or attaching operation context is typically registered as a **singleton Spring bean**. Many requests on multiple threads pass through that same aspect instance. Storing invocation info in an ordinary mutable field can cause a **race condition**. Storing it in a `ThreadLocal<T>` gives each thread access to its own value, yet it does not mean Spring automatically creates, propagates, or cleans up context per request.

Two bugs occur frequently:

1. **Not calling `remove()`:** a thread in a pool retains the previous request's data, causing a later request to see the wrong operation, tenant, or correlation ID.
2. **Unconditionally calling `remove()` in nested advice:** when one Spring proxy calls another Spring proxy on the same thread, the inner advice can clear context that the outer advice still needs.

The safe pattern for a scope owned by a Spring `@Around` advice is:

~~~java
String previous = context.get();
context.set(operation);
try {
    return pjp.proceed();
} finally {
    if (previous == null) {
        context.remove();
    } else {
        context.set(previous);
    }
}
~~~

This pattern **saves the previous state before setting, advances the interceptor chain once, and always restores/removes when the invocation exits**, while preserving the return value or exception provided by `proceed()`.

This lesson focuses on **Spring Aspects and proxy-based Spring AOP** per the module's Special Note, without repeating general Aspect knowledge. The goal is to explain ThreadLocal lifecycle, nested interception, cleanup on exceptions, self-invocation, thread reuse, and context propagation with Spring async/reactive.

## 2. How Does ThreadLocal Work Inside a Singleton Aspect?

Concurrency-broken aspect:

~~~java
@Aspect
public class UnsafeAspect {
    private String activeOperation;
}
~~~

If two threads run the same advice, T1 can set `activeOperation="pay"` and then T2 can set `"report"` before T1 reads it. A singleton aspect object has **one shared field** across all threads.

With:

~~~java
@Aspect
public class ScopedAspect {
    private final ThreadLocal<String> activeOperation = new ThreadLocal<>();
}
~~~

The aspect still has one shared `ThreadLocal` field, yet each thread accesses an entry bound to that thread alone. T1 and T2 can observe independent values.

This **does not** turn ThreadLocal into:

- A Spring-managed request scope;
- A transaction scope;
- An authenticated security context;
- Context for `CompletableFuture` or `@Async` tasks;
- A Reactor subscriber context;
- A distinct value per nested method on the same thread;
- A mechanism that auto-cleans when a Spring method returns.

Key APIs:

| API | Meaning |
| --- | --- |
| `get()` | Read the ThreadLocal value on the current thread |
| `set(value)` | Set or overwrite the value on the current thread |
| `remove()` | Delete the current entry on the calling thread |
| `ThreadLocal.withInitial(...)` | Create an initial value when a thread has no entry; requires managing the lifetime of the allocated object |

If you set a value and never remove it, the entry can persist across multiple uses of the **same thread**. With a web server or pooled executor, that is a contamination and memory retention risk.

## 3. Why Must Cleanup Be in finally?

Wrong approach:

~~~java
@Around("execution(* example.work..*.*(..))")
public Object track(ProceedingJoinPoint pjp) throws Throwable {
    operation.set(pjp.getSignature().getName());
    Object result = pjp.proceed();
    operation.remove();
    return result;
}
~~~

If the target or an inner advisor throws a `Throwable`, the `remove()` statement after `proceed()` is skipped. The caller still sees the error, while the ThreadLocal can retain the stale value.

Simple fix when there is **no prior scope to preserve**:

~~~java
operation.set(pjp.getSignature().getName());
try {
    return pjp.proceed();
} finally {
    operation.remove();
}
~~~

`finally` executes on normal returns and normal exceptional exits once the `try` block is entered. However, if there is a **nested invocation on the same ThreadLocal**, an unconditional remove in the inner advice wipes out the outer advice's context.

**Rule:** Cleanup is not just "deleting". Cleanup means **restoring the thread's state to what it was before the scope opened**; removing is simply the case where no prior value existed.

## 4. Nested Spring Proxy Calls: The Unconditional-Remove Bug

Suppose:

~~~text
Caller -> Spring proxy of PrimaryService.process()
           @Around outer: set("process")
             target PrimaryService.process()
               -> Spring proxy SecondaryService.check()
                    @Around inner: set("check")
                      target SecondaryService.check()
                    @Around inner: finally
               target PrimaryService needs "process" again
           @Around outer: finally
~~~

Both calls use the same thread and the same `OperationContext` bean.

If the inner `finally` calls `remove()`, upon returning to the outer target, `get()==null` instead of `"process"`. The outer call is still running, yet its scope has been destroyed.

Correct approach:

~~~java
String previous = context.get();  // Inner remembers "process".
context.set("check");
try {
    return pjp.proceed();
} finally {
    if (previous == null) {
        context.remove();
    } else {
        context.set(previous);      // Inner restores "process".
    }
}
~~~

Outer enters from an empty thread so `previous=null`, and eventually calls `remove()`. Inner enters while outer is active so `previous="process"`, and eventually restores previous. This structure preserves **both normal and exceptional exits**.

If null is a valid domain value, do not arbitrarily equate `null = no entry`; use a separate presence representation or scope stack. In this lesson null means "no current operation".

## 5. How Important Are Spring AOP Proxy Boundaries?

Spring AOP uses **JDK dynamic proxies or CGLIB class-based proxies**. When a client calls a method through a Spring-managed proxy and the pointcut matches, the around advice can run; conversely:

- Objects created with `new Service()` outside Spring are **not** automatically advised.
- Calls like `this.someMethod()` inside the target **do not go back through the proxy**, so no new advice invocation is created for that method.
- Switching from JDK to CGLIB **does not fix self-invocation** in Spring AOP.
- Another outer `@Around` advisor can short-circuit without calling `proceed()`, so the inner advice is never entered.
- A bean having a Spring AOP proxy does not mean **every method** matches the same advisor.
- `final` and `private` methods are not overridden/intercepted by CGLIB like normal methods.

**Ownership:** An advice cleans up only state it set itself. If an inner advice was never entered due to an outer short-circuit, the inner advice has no duty to clean up state it never created. If another component set a value, this scope must restore that component's exact previous value.

## 6. Complete Maven/Java 17+ Example

The demo uses **Spring Framework 6.2.19**, Java **17+**, AspectJ Weaver **1.9.25.1**. Two Spring-managed services both match the same aspect, so they can produce **nested interception**. Four scenarios are verified:

1. Normal nested call;
2. Inner target throws an exception, error propagates to caller;
3. Inner throws an error, yet outer target catches and recovers;
4. Self-invocation `this.local()` does not create a new nested advice.

The project uses an `OperationContext` bean holding a ThreadLocal. `ScopeAspect` is a Spring-managed `@Aspect`, using save/restore in `try/finally`. Stdout lines are deterministic and `Main` has assertions verifying the caller thread has no leftover context after each call.

### 6.1. Project structure

~~~text
spring-aop-threadlocal-demo/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── Main.java
    ├── aop/ScopeAspect.java
    ├── context/OperationContext.java
    └── work/
        ├── PrimaryService.java
        └── SecondaryService.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-aop-threadlocal-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework</groupId>
                <artifactId>spring-framework-bom</artifactId>
                <version>6.2.19</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.25.1</version>
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
            </plugin>
        </plugins>
    </build>
</project>
~~~

In a real Spring Boot application, let the Spring Boot parent/BOM manage Spring dependency versions rather than copying the demo versions directly.

### 6.3. OperationContext.java

~~~java
package example.context;

public final class OperationContext {
    private final ThreadLocal<String> value = new ThreadLocal<>();

    public String get() {
        return value.get();
    }

    public void set(String operation) {
        value.set(operation);
    }

    public void remove() {
        value.remove();
    }

    public String label() {
        String current = get();
        return current == null ? "(none)" : current;
    }
}
~~~

This is a singleton bean created via `@Bean` in AppConfig. It owns the ThreadLocal and does not set or clean up outside its published methods. The aspect manages the scope, while services can read the context while executing.

### 6.4. ScopeAspect.java

~~~java
package example.aop;

import example.context.OperationContext;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class ScopeAspect {

    private final OperationContext context;

    public ScopeAspect(OperationContext context) {
        this.context = context;
    }

    @Around("execution(public * example.work..*.*(..))")
    public Object withOperation(ProceedingJoinPoint pjp) throws Throwable {
        String operation = pjp.getSignature().getName();
        String previous = context.get();

        context.set(operation);
        try {
            System.out.println("aspect enter " + operation
                + " previous " + (previous == null ? "(none)" : previous));
            return pjp.proceed();
        } finally {
            if (previous == null) {
                context.remove();
            } else {
                context.set(previous);
            }
            System.out.println("aspect exit " + operation
                + " restored " + context.label());
        }
    }
}
~~~

Notes:

- `@Around` receives `ProceedingJoinPoint` and calls `proceed()` exactly **once**.
- The advice returns the original result or rethrows exceptions unmodified (without catching/altering).
- The pointcut applies only to **public method executions in package `example.work`**; it does not intercept `OperationContext` getters/setters or `ScopeAspect` advice methods.
- `finally` restores/removes before printing the exit log.
- Method names are used as operation labels to keep demo stdout simple. In production, use a clearly scoped key and avoid user input or PII.

### 6.5. SecondaryService.java

~~~java
package example.work;

import example.context.OperationContext;

public class SecondaryService {

    private final OperationContext context;

    public SecondaryService(OperationContext context) {
        this.context = context;
    }

    public String check() {
        System.out.println("secondary check sees " + context.label());
        return "CHECKED";
    }

    public void crash() {
        System.out.println("secondary crash sees " + context.label());
        throw new IllegalStateException("boom");
    }
}
~~~

Because it is injected by Spring, `SecondaryService` is a proxied bean when the advisor matches. Other callers can also call `check`/`crash` directly through the proxy; in the demo, calls come from `PrimaryService`.

### 6.6. PrimaryService.java

~~~java
package example.work;

import example.context.OperationContext;

public class PrimaryService {

    private final SecondaryService secondary;
    private final OperationContext context;

    public PrimaryService(SecondaryService secondary, OperationContext context) {
        this.secondary = secondary;
        this.context = context;
    }

    public String process() {
        System.out.println("primary process sees " + context.label());
        String result = secondary.check();
        System.out.println("primary resumed sees " + context.label());
        return "DONE:" + result;
    }

    public void fail() {
        System.out.println("primary fail sees " + context.label());
        secondary.crash();
    }

    public String recover() {
        System.out.println("primary recover sees " + context.label());
        try {
            secondary.crash();
        } catch (IllegalStateException ex) {
            System.out.println("primary caught " + ex.getMessage()
                + " sees " + context.label());
        }
        return "RECOVERED";
    }

    public String selfCall() {
        System.out.println("primary selfCall sees " + context.label());
        return this.local();
    }

    public String local() {
        System.out.println("primary local sees " + context.label());
        return "LOCAL";
    }
}
~~~

Important difference:

- `secondary.check()` passes through another Spring-managed bean (proxy), producing a **nested advice invocation**: state transitions `process → check → process`.
- `this.local()` inside the target **bypasses the proxy**, so there is no nested enter/exit for `local`; it still reads the current thread's `selfCall` context.

### 6.7. AppConfig.java

~~~java
package example;

import example.aop.ScopeAspect;
import example.context.OperationContext;
import example.work.PrimaryService;
import example.work.SecondaryService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public OperationContext operationContext() {
        return new OperationContext();
    }

    @Bean
    public SecondaryService secondaryService(OperationContext context) {
        return new SecondaryService(context);
    }

    @Bean
    public PrimaryService primaryService(
            SecondaryService secondary,
            OperationContext context) {
        return new PrimaryService(secondary, context);
    }

    @Bean
    public ScopeAspect scopeAspect(OperationContext context) {
        return new ScopeAspect(context);
    }
}
~~~

Spring AOP discovers the aspect bean registered via `@Bean`. `@EnableAspectJAutoProxy(proxyTargetClass = true)` enables Spring AOP and uses CGLIB class-based proxies when needed, allowing target bean lookup by concrete class. **CGLIB does not automatically intercept self-invocation**.

### 6.8. Main.java

~~~java
package example;

import example.context.OperationContext;
import example.work.PrimaryService;
import example.work.SecondaryService;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    private static void assertClean(OperationContext context) {
        if (context.get() != null) {
            throw new AssertionError("ThreadLocal leaked: " + context.get());
        }
    }

    public static void main(String[] args) {
        try (var spring =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {
            PrimaryService primary = spring.getBean(PrimaryService.class);
            SecondaryService secondary = spring.getBean(SecondaryService.class);
            OperationContext context = spring.getBean(OperationContext.class);

            System.out.println("primary proxy: " + AopUtils.isAopProxy(primary));
            System.out.println("secondary proxy: " + AopUtils.isAopProxy(secondary));

            System.out.println("-- normal nested --");
            System.out.println("caller: " + primary.process());
            assertClean(context);
            System.out.println("caller context: " + context.label());

            System.out.println("-- exceptional nested --");
            try {
                primary.fail();
            } catch (IllegalStateException ex) {
                System.out.println("caller caught: " + ex.getMessage());
            }
            assertClean(context);
            System.out.println("caller context: " + context.label());

            System.out.println("-- caught inside outer --");
            System.out.println("caller: " + primary.recover());
            assertClean(context);
            System.out.println("caller context: " + context.label());

            System.out.println("-- self invocation --");
            System.out.println("caller: " + primary.selfCall());
            assertClean(context);
            System.out.println("caller context: " + context.label());
        }
    }
}
~~~

Run in the project directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
~~~

### 6.9. Expected Stdout

~~~text
primary proxy: true
secondary proxy: true
-- normal nested --
aspect enter process previous (none)
primary process sees process
aspect enter check previous process
secondary check sees check
aspect exit check restored process
primary resumed sees process
aspect exit process restored (none)
caller: DONE:CHECKED
caller context: (none)
-- exceptional nested --
aspect enter fail previous (none)
primary fail sees fail
aspect enter crash previous fail
secondary crash sees crash
aspect exit crash restored fail
aspect exit fail restored (none)
caller caught: boom
caller context: (none)
-- caught inside outer --
aspect enter recover previous (none)
primary recover sees recover
aspect enter crash previous recover
secondary crash sees crash
aspect exit crash restored recover
primary caught boom sees recover
aspect exit recover restored (none)
caller: RECOVERED
caller context: (none)
-- self invocation --
aspect enter selfCall previous (none)
primary selfCall sees selfCall
primary local sees selfCall
aspect exit selfCall restored (none)
caller: LOCAL
caller context: (none)
~~~

Other Maven/JVM logs may appear depending on the environment; the block lists only the `System.out.println` lines in the example. If context leaks on the caller thread, `assertClean()` throws `AssertionError` instead of continuing to print subsequent lines.

### 6.10. Explaining the Four Call Paths

**Normal:** outer sets `process`; inner sets `check`; inner finally restores `process`; outer reads `process`; finally outer removes, caller sees `(none)`.

**Exception:** outer sets `fail`; inner sets `crash` and throws `boom`; inner finally restores `fail`; outer finally removes; caller then catches `boom`. Cleanup does not mean the exception was handled by the aspect.

**Recover:** inner `crash` throws an exception; inner finally restores `recover` before the outer target catches it. The outer target has context `recover` for logging/recovery; outer finally removes.

**Self-call:** target `selfCall` calls `this.local()` directly. Context remains `selfCall` and there is no separate enter/exit pair for `local`. Outer finally removes upon completion.

## 7. Pitfall and Fix Table

| Pattern | Normal return | Exceptional exit | Nested |
| --- | --- | --- | --- |
| Only set then proceed | Can leave stale value | Can leave stale value | Can corrupt context |
| Set, proceed, remove afterward | Cleans up on success | **Skips cleanup** on error | Inner remove wipes outer |
| Set, try/finally, always remove | Cleans up at top-level | Cleans up on error | **Deletes outer state when inner exits** |
| **Capture previous, set, try/finally, restore/remove** | Preserves pre-scope state | Preserves state on error | **Correct for nested calls on the same thread** |

No pre-scope value means `remove()`; a pre-scope value means restoring it. The ownership rule matters more than counting `remove()` calls.

## 8. Stack-Based Alternative

If you need a **list of nested operations** rather than just the current operation, you can use a per-thread stack:

~~~java
// Illustrative snippet; not a file in the runnable project in section 6.
private final ThreadLocal<Deque<String>> stack =
    ThreadLocal.withInitial(ArrayDeque::new);

public void enter(String value) {
    stack.get().push(value);
}

public void exit() {
    Deque<String> values = stack.get();
    values.pop();
    if (values.isEmpty()) {
        stack.remove();
    }
}
~~~

Requires importing `java.util.Deque` and `java.util.ArrayDeque`. `exit()` must run in the `finally` of the matching scope after `enter` succeeds. Production code needs guards for empty pop, mismatched nesting, double-close, and thread switches; even better, provide a `Scope implements AutoCloseable` closed exactly once.

**Do not pass a mutable Deque reference to another thread** just because it was stored in a ThreadLocal. And when the stack is empty, remove the entire ThreadLocal entry so empty objects are not held on pooled threads indefinitely.

## 9. @Async and ThreadPoolTaskExecutor Do Not Automatically Propagate ThreadLocal

Flow example:

~~~text
HTTP thread T1:
  aspect sets "submit"
    method creates or submits @Async task
    method returns Future/handle
  aspect finally restores/removes

Worker thread T2:
  task executes later
  ThreadLocal of T2 is independent from ThreadLocal of T1
~~~

A task on T2 does not automatically inherit the right value from T1. Conversely, if T2 retains stale state because a prior task forgot cleanup, it can see the **wrong value**.

Spring provides `org.springframework.core.task.TaskDecorator` to decorate tasks on executors like `ThreadPoolTaskExecutor`. When you need to propagate a self-managed context, you must **capture at submit time** and **restore worker context in finally**.

~~~java
// Supplementary snippet, not part of the demo project in section 6.
@Bean
public ThreadPoolTaskExecutor decoratedExecutor(OperationContext context) {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);

    executor.setTaskDecorator(task -> {
        String submittedContext = context.get();
        return () -> {
            String workerPrevious = context.get();
            if (submittedContext == null) context.remove();
            else context.set(submittedContext);

            try {
                task.run();
            } finally {
                if (workerPrevious == null) context.remove();
                else context.set(workerPrevious);
            }
        };
    });
    return executor;
}
~~~

This snippet needs Spring imports for `@Bean` and `ThreadPoolTaskExecutor`, plus proper executor configuration/lifecycle. It illustrates **one type of OperationContext**, and does not automatically handle Spring Security context, transactions, or all MDC keys.

**Do not use `InheritableThreadLocal` as a default fix for thread pools.** It inherits at thread creation time, not per task submission, so reused workers can retain outdated info.

## 10. Reactive Spring: ThreadLocal Is Not Subscription Context

A Spring service returning `Mono<T>` or `Flux<T>` can finish **method execution** before the pipeline is subscribed to. An `@Around` advice around that method runs `finally` when the method returns the publisher, not waiting by default for the stream to complete.

In Reactor, operators can run across multiple threads. A `ThreadLocal` set during publisher assembly does not automatically follow the subscriber to every signal. When per-stream data is needed, use **Reactor Context** or a context propagation/observation mechanism appropriate for your Spring/Reactor version.

Test completion, failure, cancellation, and thread hopping separately. Do not infer "Spring `@Around` finally ran" means "the reactive task completed and all state on other workers was cleaned up".

## 11. Spring Logging MDC and Key Ownership

SLF4J MDC is often used to attach `requestId`, `traceId`, or `operation` to logs on the current thread. If a custom aspect owns only the `operation` key, it must not clear the entire MDC in `finally` because that would erase keys set by other components.

**Supplementary snippet** example, requiring SLF4J API/logging implementation and imports; not part of the Maven demo project:

~~~java
@Around("execution(* com.acme.service..*.*(..))")
public Object withLoggingKey(ProceedingJoinPoint pjp) throws Throwable {
    String previous = MDC.get("operation");
    MDC.put("operation", pjp.getSignature().getName());

    try {
        return pjp.proceed();
    } finally {
        if (previous == null) MDC.remove("operation");
        else MDC.put("operation", previous);
    }
}
~~~

Prefer `MDC.remove("operation")` and restoring previous; **do not call `MDC.clear()` indiscriminately** when the aspect manages only one key.

Do not put passwords, bearer tokens, sensitive tenant data, customer IDs, or raw request bodies into MDC/logs. MDC also does not automatically move to other threads; selective context propagation is needed if using executors.

## 12. @Before + @After vs @Around

Two separate advice methods:

~~~java
@Before("serviceOperations()")
public void before() {
    operation.set("current");
}

@After("serviceOperations()")
public void after() {
    operation.remove();
}
~~~

risk ownership mismatches when multiple aspects have different orders, nesting, mismatched pointcuts, or an outer interceptor throws before the after advice is entered. It is also hard to pass a per-invocation `previous` variable if that variable were stored in a singleton field.

For a context opened and closed within the **same invocation**, a single `@Around` method containing `try/finally` makes pairing much clearer. Of course, that around advice itself must actually be invoked by Spring AOP; if an outer advisor short-circuits before entering around, there is no state from that around needing cleanup.

## 13. @Order, Transactions, and Actual Context Scope

When Spring transaction/cache/security advisors are present, a method can traverse multiple layers:

~~~text
Caller -> ScopeAspect @Around
            -> TransactionInterceptor
               -> TargetService
            <- TransactionInterceptor completes
         <- ScopeAspect finally cleans up context
~~~

If `ScopeAspect` is outside the transaction interceptor, it covers the transaction handling **inside**; if the order is reversed, some transaction work may occur outside `ScopeAspect`. An order number alone does not prove context is present at every layer. Check the actual advisor chain and Spring transaction configuration when scope is a functional requirement.

If an inner advisor short-circuits without calling `proceed`, the outer scope's `finally` **still cleans up after the inner returns**. But if the outer does not proceed so an inner scope is never entered, the inner sets no state and needs no cleanup.

## 14. Testing Cleanup on the Same Worker Thread

A test that only checks:

~~~java
assertNull(context.get());
~~~

after a job completes on the **test thread** is insufficient to prove a worker thread cleaned up its state. ThreadLocal belongs to the **thread executing the code**, so it must be checked on that exact worker thread.

A test matrix should include:

| Case | Inside the call | After exiting the call |
| --- | --- | --- |
| Normal return | Sees correct operation | Restores/removes properly |
| Throwable exits target | Sees operation before throw | Finally runs, original error still propagates |
| Nested service proxy | Inner sees inner name | Outer sees outer name again |
| Inner throws, outer catches | Inner sees inner name | Outer catch sees outer name |
| Self-invocation | Inner Java method reads outer context | No separate nested AOP scope |
| Caller has prior context | Scope temporarily overrides | Restores exact previous value |
| Two concurrent threads | Each thread's own value | Independent cleanup per thread |
| Single-worker pool, two sequential requests | Request 1 has its own value | Request 2 does not see Request 1's state |
| Executor TaskDecorator | Worker sees captured permitted context | Worker restores previous after task |
| Reactive/async completion | Method boundary differs from task completion | Measure lifecycle at the right abstraction |

You can use `Executors.newSingleThreadExecutor()` in tests to submit two consecutive jobs and check `context.get()` **directly on the worker thread** after each job. With multiple threads, a global mutable event list without correlation IDs is insufficient to prove ordering/ownership.

## 15. When Should You Not Use ThreadLocal?

Do not use ThreadLocal as a default solution if:

- Data is business input that should be passed explicitly through service methods.
- Authentication/authorization/tenant isolation with a critical security contract is required.
- Data must survive across multiple threads, futures, message queues, or processes.
- The system uses Reactor/WebFlux and logical flow moves across subscriptions.
- You cannot control cleanup boundaries or multiple teams mutate the same key.
- Data is large or contains secrets/PII and risks being retained on worker threads.
- A library such as Micrometer Observation/context propagation already provides the right abstraction, avoiding incomplete custom propagation.

Instead, consider Spring request-scoped dependencies, explicit parameter/context objects, Reactor Context, or a suitable observability library. **ThreadLocal is a per-thread tool, not a cross-layer Spring contract.**

## 16. Common Pitfalls

| Symptom | Likely cause | How to fix |
| --- | --- | --- |
| Later request sees prior request's state | Missing `remove()` on thread pool thread | Clean up in finally, test thread reuse |
| Outer loses context after inner call | Inner unconditionally removes | Capture previous and restore |
| Context remains after target throws | Cleanup placed after proceed, not in finally | Use try/finally |
| Two requests overwrite same aspect field | Shared mutable singleton field | Use local state / scoped context / ThreadLocal when valid |
| `@Async` does not see value | ThreadLocal does not automatically cross to worker | TaskDecorator or context propagation |
| Worker sees unexpected value | Previous worker task failed to clean up | Restore/remove on worker side |
| MDC `traceId` disappears | Custom aspect called `MDC.clear()` | Remove/restore only owned key |
| WebFlux result completes after cleanup | `@Around` cleans up when method returns Publisher | Reactor Context and reactive lifecycle |
| Self-call does not create inner scope | `this.method()` bypasses proxy | Call through another Spring bean when advice is needed |
| Bean is a proxy yet method skips advice | Pointcut does not match that method | Check eligible advisors |
| Non-null state after method | Valid context existed before scope | Restoring previous is correct; do not clear blindly |
| Memory retention grows | Thread pool holds large value/object | Reduce lifetime and remove |
| Finally logging masks target exception | Instrumentation itself throws | Design failure policy for logging/metrics |
| Scoped stack throws empty pop | Unbalanced push/pop | Scope ownership and close exactly once |
| Used InheritableThreadLocal for pool propagation | Inherits on thread creation, not task submission | Explicit propagation with cleanup |

## 17. Review Quiz

**Q1.** Why can a singleton `@Aspect` hold a `ThreadLocal<String>` field without all threads seeing the same String?

**Answer:** ThreadLocal stores a separate entry per current thread. However, it does not auto-clean when a method/request ends, so its lifetime must be managed.

**Q2.** Inner advice calls `remove` in `finally`, causing outer to see `null`. Why?

**Answer:** Outer and inner share the same ThreadLocal entry on the same thread; inner deleted outer's context. Inner must restore `previous` on exit.

**Q3.** A target method throws `IllegalStateException`. Does cleanup placed right after `proceed` run?

**Answer:** No, not on an exceptional exit. Put cleanup in `finally`; the exception still propagates if the advice does not swallow it.

**Q4.** Does `this.local()` inside the target create a nested AOP scope?

**Answer:** Not by default. Self-invocation bypasses the Spring AOP proxy. The `local` method can still read the outer context on the same thread.

**Q5.** Thread T1 submits a task running on T2; does T2 automatically read T1's ThreadLocal?

**Answer:** No. Selective propagation at the task boundary and restore/remove on T2 are required.

**Q6.** An aspect manages MDC key `operation` but calls `MDC.clear()` in `finally`. What is wrong?

**Answer:** It can wipe out `requestId`/`traceId` keys owned by other components. Restore/remove only the owned key.

**Q7.** A method returns `Mono` and completes, the around advice's `finally` has run, yet the publisher has no subscriber yet. Is there a contradiction?

**Answer:** No. Spring AOP method execution finishes when returning the publisher object, which differs from the reactive subscription lifecycle.

**Q8.** When the caller already had context `"request"` before the method, should after advice always call `remove`?

**Answer:** No. After the invocation it must restore `"request"` per ownership. Call `remove` only if it was empty beforehand.

**Q9.** Can you check ThreadLocal on the main thread alone to prove a worker pool does not leak?

**Answer:** No. You must check on the reused worker thread itself.

**Q10.** Why shouldn't tenant/authorization policy rely solely on an unvalidated ThreadLocal?

**Answer:** It does not verify provenance on its own, risks stale/missing data, and does not automatically propagate across async boundaries. Security/tenant state must be authenticated and managed by appropriate mechanisms.

## 18. Official Documentation

- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): Spring proxy boundaries, JDK/CGLIB, and self-invocation.
- [Spring Framework — Declaring @Around Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): `ProceedingJoinPoint.proceed()`, try/finally, and per-invocation state boundaries.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): aspect must be a Spring bean, enabling `@EnableAspectJAutoProxy`.
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): TaskDecorator, ThreadPoolTaskExecutor, and async execution.
- [Oracle Java 17 — ThreadLocal API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): get/set/remove and per-thread values.
- [Spring Framework — Observability](https://docs.spring.io/spring-framework/reference/observability.html): boundaries of observation/context propagation.
- [Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): per-subscription context, not bound to a fixed thread.
