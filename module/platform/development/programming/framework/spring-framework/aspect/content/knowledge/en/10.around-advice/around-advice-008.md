# Measuring Execution Time Without Altering Business Outcomes in Spring AOP

## 1. The Problem to Solve

You want to know how long a business method takes without scattering timing statements into every service, while **not altering the return value, exception type, or execution count of the method**. In Spring AOP, an `@Around` advice can wrap method execution on a Spring-managed bean, record the timestamp before calling `ProceedingJoinPoint.proceed()`, and record the duration after the invocation completes.

Core pattern:

~~~java
@Around("execution(public * example.TaskService.*(..))")
public Object measure(ProceedingJoinPoint pjp) throws Throwable {
    long startedAt = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        long elapsedNanos = System.nanoTime() - startedAt;
        // Record metrics here without altering the result from proceed().
    }
}
~~~

**Three critical commitments:**

1. **Normal return:** the value returned by the inner interceptor chain is forwarded intact to the caller via `return pjp.proceed()`.
2. **Exceptional exit:** exceptions from the inner chain propagate outward; `finally` runs, yet the advice never turns an exception into a "success" result.
3. **Single invocation:** call `proceed()` **once**; do not retry, modify arguments, or short-circuit if the sole goal is timing.

This lesson focuses strictly on **Spring Aspect and proxy-based Spring AOP**: implementing `@Around`, measurement boundaries, metric metadata, and Spring proxy limits. General Aspect concepts fall outside this scope.

## 2. Why Does `@Around` Fit the Timing Problem?

The Spring Framework documentation describes around advice as the advice type that can perform logic **before and after** method execution while holding per-invocation local state safely across concurrent threads. Timing needs a paired start/end timestamp for the same call, so `@Around` with a local `startedAt` variable expresses that intent cleanly.

| Approach | Characteristics | Suitable for measuring duration? |
| --- | --- | --- |
| Standalone `@Before` | Runs before invocation | No end timestamp within the same advice |
| Standalone `@After` | Runs when method exits normally or throws | No start timestamp within the same advice |
| Two advices `@Before` + `@After` sharing a `long start` field on a singleton aspect | Field can be overwritten by concurrent invocations/threads | **Unsafe** under concurrent calls |
| `@Around` with local `long startedAt` and `try/finally` | Keeps a per-invocation timestamp pair; records both success and failure | **Recommended** |
| `@Around` omitting `proceed()` | Does not forward the call to the inner chain | **Wrong goal** when only observing |
| `@Around` catching errors and returning a default value | Masks business failures | **Wrong goal** when results must stay intact |

**Note:** `@Around` has the power to alter the call flow, yet in a pure timing task we **deliberately refrain from using** that power. Observation is secondary; the method's business contract must remain intact.

### 2.1. Execution Flow Diagram

~~~text
Caller
   |
   v
Spring AOP proxy for TaskService
   |
   +-- @Around starts: startedAt = System.nanoTime()
   |
   +-- pjp.proceed()
   |        |
   |        +-- remaining advisors/interceptors
   |        |
   |        +-- target method, if invocation reaches target
   |        |
   |        +-- returns result or throws Throwable
   |
   +-- finally: elapsed = System.nanoTime() - startedAt
   |            record metrics
   |
   v
Caller receives exact result or Throwable of the wrapped call path
~~~

The phrase "measuring execution time" here should be understood as **measuring the elapsed time as the call passes through the portion of the Spring AOP chain inside the advice**. It can include inner advisor time alongside the target, and is not automatically equal to raw CPU time spent solely executing statements in the method body.

## 3. Choosing the Clock: `System.nanoTime()`, Not `currentTimeMillis()`

When measuring **duration**, use:

~~~java
long start = System.nanoTime();
// Invoke the measured operation.
long elapsedNanos = System.nanoTime() - start;
~~~

`System.nanoTime()` provides a clock source suited for measuring **elapsed time**. Its origin is arbitrary and is **not a calendar/wall-clock timestamp**.

Distinction:

| API | Appropriate purpose | Do not infer |
| --- | --- | --- |
| `System.nanoTime()` | Measuring elapsed intervals within the same JVM | Do not infer wall-clock date/time; does not guarantee single-nanosecond precision |
| `System.currentTimeMillis()` | Calendar time in epoch milliseconds | Suboptimal for duration comparison because the system clock can be adjusted |
| `Instant.now()` | Timestamps for event logs or audit instants | Not the default choice for benchmarking elapsed time |

**Units:** `elapsedNanos` is expressed in nanoseconds per the API; convert to milliseconds via:

~~~java
double elapsedMillis = elapsedNanos / 1_000_000.0;
~~~

Do not truncate to integer milliseconds for a fast method and conclude "0 ms means zero cost." Clocks have finite resolution, and measurement/logging overhead, JIT, GC, and OS scheduling all influence results.

Subtracting `System.nanoTime() - start` is Java's recommended way to measure short intervals; never compare raw `nanoTime` values against another timestamp type. Never use it as a distributed clock across JVMs or hosts.

## 4. Structure of a Business-Preserving Around Advice

Full pattern as a Spring AOP aspect class (snippet; standalone runnable project is in section 6):

~~~java
package example;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class TimingAspect {

    private final TimingMetrics metrics;

    public TimingAspect(TimingMetrics metrics) {
        this.metrics = metrics;
    }

    @Around("execution(public * example.TaskService.*(..))")
    public Object measure(ProceedingJoinPoint pjp) throws Throwable {
        String operation = pjp.getSignature().getName();
        long startedAt = System.nanoTime();

        try {
            return pjp.proceed();
        } finally {
            long elapsed = System.nanoTime() - startedAt;
            metrics.record(operation, elapsed);
        }
    }
}
~~~

In this code, `TimingMetrics` is a bean storing call counts and measured durations; its full definition is in section 6. What matters is the **call-flow structure**:

- `@Around` binds the Spring advice to **method executions** selected by the pointcut.
- The first parameter is `ProceedingJoinPoint`.
- `Object` is the recommended return type for around advice shared across multiple return types.
- `throws Throwable` propagates both checked and unchecked `Throwable` instances thrown by the inner invocation.
- `return pjp.proceed();` returns the exact result object—no `toString()`, no transformation, no wrapping/casting.
- `finally` records metrics on both **normal return** and **exceptional exit**.
- Does not mutate `pjp.getArgs()`, does not call `proceed(Object[])`, and does not call `proceed()` multiple times.
- `startedAt` and `operation` are per-invocation local variables, preventing races on a shared start-time field in a singleton aspect.

**Crucial caveat:** `finally` guarantees that recording code is **attempted** on both branches, yet if `metrics.record(...)` throws an exception itself, it **can alter the behavior observed by the caller**—such as turning a successful method into an error or masking the original exception. To truly observe without altering business contracts, design a safe metrics sink and establish a clear policy for instrumentation failures (see section 8).

## 5. Three Levels of "Not Altering Business Outcomes"

This phrase is often understood too narrowly as "the method still returns the right string." In Spring AOP there are at least three layers to preserve:

### 5.1. Preserving Return Values and Exceptions

~~~java
try {
    return pjp.proceed();
} finally {
    metrics.record(operation, System.nanoTime() - startedAt);
}
~~~

When `metrics.record` completes normally:

- If the inner invocation returns `String "OK"`, the caller receives `"OK"`.
- If the inner invocation returns **the same object instance**, the caller receives that exact instance; timing advice does not create a new result wrapper.
- If the inner invocation throws `IllegalStateException("boom")`, the caller receives the same exception via normal propagation; timing advice does not turn it into `null` or a fake result.
- If the target has return type `void`, `proceed()` at the `Object` layer normally returns `null`; the advice preserves `void` semantics.
- If the target returns a primitive, Spring handles boxing/unboxing at the proper boundary; the advice must never return `null` or another type instead of the primitive result.

### 5.2. Preserving Arguments and Invocation Count

~~~java
Object result = pjp.proceed();
return result;
~~~

This snippet does not replace arguments. Calling `pjp.proceed(modifiedArgs)` alters invocation data. Calling `pjp.proceed()` **twice** can execute the target twice and repeat side effects. Neither is appropriate when the requirement is pure observation.

### 5.3. Keeping Metrics From Becoming Significant Side Effects

An advice meant only to "measure" that writes synchronously to the console, makes network calls per request, throws exceptions when an exporter fails, logs all arguments, or attaches bad thread state can still impact runtime behavior. Therefore:

- Never put sensitive data into labels or logs.
- Never use a metrics backend that can throw arbitrary errors back to callers when business logic must stay independent of observability.
- Never keep a shared mutable start-time field on a singleton aspect.
- Avoid high-cardinality labels from user IDs, full URLs, emails, or request payloads.
- Minimize blocking I/O on hot paths.
- Use metric counters/timers matched to the required accuracy rather than guessing from a handful of runs.

## 6. Complete Java 17+ Example: Timing Three Calls While Preserving Outcomes

The example below runs on **Spring Framework 6.2.19**, **Java 17+**, Maven, and AspectJ Weaver **1.9.25.1**. It is a standalone project (no Spring Boot, web server, database, or test containers required).

Three call paths to observe:

1. `taskService.greet("Lan")` returns `"Hello Lan"` normally.
2. `taskService.fail()` throws `IllegalStateException("boom")`; metrics still record one sample.
3. `taskService.callInternally()` calls `this.greet("Self")`; Spring AOP measures **the outer `callInternally` call** without recording a separate sample for the inner `greet` due to self-invocation.

To keep stdout verifiable, the project **stores real nanosecond values** while printing only **event labels** and sample counts. Actual nanosecond totals live in the registry and vary across runs, so no fabricated duration number is printed.

### 6.1. Directory Layout

~~~text
spring-aop-timing/
├── pom.xml
└── src/main/java/example/
    ├── AppConfig.java
    ├── TaskService.java
    ├── TimingMetrics.java
    ├── TimingAspect.java
    └── Main.java
~~~

### 6.2. Maven: `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-aop-timing</artifactId>
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

The Spring Framework BOM keeps `spring-*` dependencies version-aligned. Real Spring Boot projects should let the Boot BOM or starters manage dependencies rather than copying the demo versions mechanically.

### 6.3. `TaskService.java`

~~~java
package example;

public class TaskService {

    public String greet(String name) {
        System.out.println("target: greet " + name);
        return "Hello " + name;
    }

    public void fail() {
        System.out.println("target: fail");
        throw new IllegalStateException("boom");
    }

    public String callInternally() {
        System.out.println("target: callInternally");
        return this.greet("Self");
    }
}
~~~

`TaskService` is the Spring target bean; there is no timing logic inside the service. `greet` and `fail` test normal/exception flows; `callInternally` demonstrates Spring AOP's self-invocation boundary.

### 6.4. `TimingMetrics.java` — Concurrency-Safe Duration and Sample Count Storage

~~~java
package example;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.LongAdder;

public final class TimingMetrics {

    private final ConcurrentMap<String, LongAdder> counts =
        new ConcurrentHashMap<>();

    private final ConcurrentMap<String, LongAdder> totalNanos =
        new ConcurrentHashMap<>();

    public void record(String operation, long elapsedNanos) {
        counts.computeIfAbsent(operation, key -> new LongAdder()).increment();
        totalNanos.computeIfAbsent(operation, key -> new LongAdder())
            .add(elapsedNanos);

        // Print only the label so the example produces deterministic stdout.
        System.out.println("metric: " + operation + " recorded");
    }

    public long count(String operation) {
        LongAdder value = counts.get(operation);
        return value == null ? 0L : value.sum();
    }

    public long totalNanos(String operation) {
        LongAdder value = totalNanos.get(operation);
        return value == null ? 0L : value.sum();
    }
}
~~~

**Design rationale:**

- `LongAdder` fits concurrent accumulation of counters/total duration in simple concurrent operations, avoiding races on a mutable `long` updated by multiple threads.
- `ConcurrentHashMap` permits concurrent access across multiple operation names.
- `record` is called only by the timing aspect when the invocation enters `finally`.
- `totalNanos(operation)` stores the **real numeric value** of total duration; printing it to the console would differ across runs.
- This is a toy instrumentation registry: updating **two separate maps is not a single atomic transaction**. If you need consistent joint snapshots of count and duration or accurate histograms/percentiles, use a dedicated observability/metrics library.
- Printing inside `record` is for demonstration; **production code should not call `System.out.println` on every invocation**, especially on hot paths.
- An `OutOfMemoryError` or rare exception in the metrics subsystem itself could still affect the contract; this lesson uses a small in-memory sink to illustrate the normal success path without claiming "instrumentation failures are impossible."

### 6.5. `TimingAspect.java` — Measure Only, Never Alter Business Results

~~~java
package example;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class TimingAspect {

    private final TimingMetrics metrics;

    public TimingAspect(TimingMetrics metrics) {
        this.metrics = metrics;
    }

    @Around("execution(public * example.TaskService.*(..))")
    public Object measure(ProceedingJoinPoint pjp) throws Throwable {
        String operation = pjp.getSignature().getName();
        long startedAt = System.nanoTime();

        try {
            return pjp.proceed();
        } finally {
            long elapsedNanos = System.nanoTime() - startedAt;
            metrics.record(operation, elapsedNanos);
        }
    }
}
~~~

Here:

- `@Aspect` marks the class as containing Spring AOP advice; it **does not turn the class into a Spring bean automatically**.
- `@Around` selects **public method executions** on `example.TaskService`, covering `greet`, `fail`, and `callInternally`.
- `pjp.proceed()` is called **once**.
- `return` forwards the inner chain's exact result back to the caller.
- Neither catches exceptions, creates new exceptions, nor modifies arguments or target.
- `finally` records metrics on both exit paths for invocations **that entered the advice**.
- `operation` is only the fixed class method name, containing no arguments or sensitive content. With multiple services or overloaded methods, normalize keys more specifically to avoid merging distinct measurements.

**Measurement boundary:** The end timestamp is taken **before** `metrics.record`, so the duration excludes the advice's own metric-recording overhead. It may still include time spent in interceptors sitting **inside** the advice and target work.

### 6.6. `AppConfig.java`

~~~java
package example;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {

    @Bean
    public TaskService taskService() {
        return new TaskService();
    }

    @Bean
    public TimingMetrics timingMetrics() {
        return new TimingMetrics();
    }

    @Bean
    public TimingAspect timingAspect(TimingMetrics timingMetrics) {
        return new TimingAspect(timingMetrics);
    }
}
~~~

Plain Spring Framework requires enabling `@EnableAspectJAutoProxy` and having the required AspectJ library on the classpath. `TimingAspect` is registered **via `@Bean`**, so `@Component` is unnecessary. The target is Spring-registered and gets a proxy when matching advisors exist.

`proxyTargetClass = true` forces a class-based proxy so the program can retrieve the bean by `TaskService.class`. CGLIB is chosen for demo convenience; it **does not make self-invocation run the timing advice**.

### 6.7. `Main.java`

~~~java
package example;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {
            TaskService task = context.getBean(TaskService.class);
            TimingMetrics metrics = context.getBean(TimingMetrics.class);

            System.out.println("spring AOP proxy: " + AopUtils.isAopProxy(task));

            System.out.println("-- success --");
            System.out.println("caller: " + task.greet("Lan"));

            System.out.println("-- exception --");
            try {
                task.fail();
            } catch (IllegalStateException ex) {
                System.out.println("caller caught: " + ex.getMessage());
            }

            System.out.println("-- self invocation --");
            System.out.println("caller: " + task.callInternally());

            System.out.println("count greet: " + metrics.count("greet"));
            System.out.println("count fail: " + metrics.count("fail"));
            System.out.println("count callInternally: "
                + metrics.count("callInternally"));
            System.out.println("total samples: "
                + (metrics.count("greet") + metrics.count("fail")
                   + metrics.count("callInternally")));
        }
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.Main
~~~

### 6.8. Deterministic Stdout From the Code

~~~text
spring AOP proxy: true
-- success --
target: greet Lan
metric: greet recorded
caller: Hello Lan
-- exception --
target: fail
metric: fail recorded
caller caught: boom
-- self invocation --
target: callInternally
target: greet Self
metric: callInternally recorded
caller: Hello Self
count greet: 1
count fail: 1
count callInternally: 1
total samples: 3
~~~

**Why not print a fixed duration?** `System.nanoTime()` values depend on the runtime environment, JIT, GC, OS scheduling, CPU state, and interceptor layers; they cannot be predicted deterministically. Real values are stored in `TimingMetrics.totalNanos("greet")`, etc., and learners can print them during execution to observe them.

### 6.9. Explaining the Three Call Paths

**Successful call:**

1. Caller invokes `task.greet("Lan")` through the Spring AOP proxy.
2. Timing aspect records `startedAt` and calls `proceed()`.
3. Target prints `target: greet Lan` and returns `"Hello Lan"`.
4. Finally measures elapsed time, calls `metrics.record("greet", ...)`, and prints the metric label.
5. Caller receives the exact `"Hello Lan"`: timing advice **did not alter the return value**.

**Exception-throwing call:**

1. Proxy enters timing aspect and then runs target `fail()`.
2. Target throws `IllegalStateException("boom")`.
3. `finally` still records a `fail` sample.
4. The same exception continues propagating to the caller and is caught in `Main`.
5. Timing aspect **did not turn the failure into a default value**, preserving business error behavior.

**Self-invocation:**

1. Caller invokes `task.callInternally()` through the proxy, so timing aspect starts a measurement for **`callInternally`**.
2. Inside the target, code calls `this.greet("Self")` — **it does not go through the proxy a second time**.
3. Thus there is no second `metric: greet recorded` line; only `metric: callInternally recorded`.
4. Caller receives `"Hello Self"` as returned by the business method itself. After three external calls, counts are `greet=1`, `fail=1`, `callInternally=1`.

The key takeaway: **an internal call still consumes execution time**, yet because it does not create another proxied invocation for the inner method, it **does not produce a separate timing sample** under the pointcut.

## 7. Measuring Both Success and Failure Time Without Altering Exceptions

There are two common ways.

### 7.1. `try/finally` — Measures Both Branches Without Distinguishing Outcome

~~~java
long start = System.nanoTime();
try {
    return pjp.proceed();
} finally {
    metrics.record(operation, System.nanoTime() - start);
}
~~~

Simple and suitable when you only need **duration and the number of times a method passed through the advice**, without success/failure labels. In the example, `fail()` gets a sample even though the target threw an exception.

### 7.2. `try/catch/finally` — When Metrics Also Need Outcome Status

~~~java
// Additional snippet; metrics.record is an illustrative API, not section 6's project.
long started = System.nanoTime();
boolean failed = false;
try {
    return pjp.proceed();
} catch (Throwable error) {
    failed = true;
    throw error;
} finally {
    recordOutcome(operation, System.nanoTime() - started, failed);
}
~~~

In this snippet, `recordOutcome(...)` is a hypothetical metrics-subsystem helper (which must be defined separately). This is **not standalone code** to copy and run as-is. It illustrates the rules:

- If `proceed()` throws `Throwable`, mark `failed = true`.
- **Rethrow that exact `Throwable`**, never creating a different exception if the goal is preserving behavior.
- `finally` still runs once.
- Avoid logging full exception messages or arguments, which may contain sensitive data.

**Nuance:** If the target catches an exception itself and returns normally, then from the outer proxy's perspective `proceed()` returns normally: `failed` in the snippet is `false`. If an inner interceptor catches an exception and returns a fallback, the outer advice also sees the fallback (unaware that an inner error was handled). Distinguishing business-level status requires an explicit status contract rather than inferring solely from `Throwable`.

## 8. Preventing Instrumentation Errors From Altering Business Behavior

Even when `return pjp.proceed()` and `finally` follow the right flow, **measurement/metric-recording code is still Java code** and can fail or block. For example:

~~~java
finally {
    metricsBackend.sendHttp(elapsedNanos); // May time out or throw!
}
~~~

If the metrics backend throws an exception, the caller may see an instrumentation error instead of the target's result or exception. To keep business logic independent, use **best-effort instrumentation** with a sink designed to be non-throwing, well-bounded, and backed by proper backpressure/timeouts.

Illustrative snippet for ordinary errors:

~~~java
finally {
    long elapsed = System.nanoTime() - startedAt;
    try {
        metrics.record(operation, elapsed);
    } catch (RuntimeException instrumentationFailure) {
        // Best effort: report via safe channel without breaking business logic.
        // Do not log unboundedly or perform synchronous network I/O here.
    }
}
~~~

**Important caveats:**

- The snippet above **deliberately does not swallow `Throwable` from `proceed()`**; it handles only errors from metric recording inside `finally`.
- A fatal `Error` such as `OutOfMemoryError` or JVM termination cannot be promised to be handled "completely safely" by `catch (RuntimeException)`.
- An empty catch block should not be copied to production without an observability policy; you need a monitoring channel that does not disrupt business flow yet avoids silently hiding failures.
- Use fast, thread-safe metric recording with minimal side effects. For real Java services, consider **Micrometer Observation/Timer** or your platform's observability SDK instead of hand-rolling production in-memory counters.
- Printing logs inside `record()` in the small example is to teach the mechanics; it is not a performance design for frequently invoked endpoints.

Thus, "not altering business outcomes" is **a conditional design goal**, not something `@Around` guarantees automatically under all circumstances.

## 9. Which Data Should Be Attached to Metrics?

Recommended labels:

| Label | Example | Assessment |
| --- | --- | --- |
| Fixed operation name | `TaskService.greet` | Usually appropriate, bounded cardinality |
| Outcome | `success` / `failure` | Appropriate when clearly defined at the proxy boundary |
| Service/module | `payment`, `checkout` | Appropriate with a bounded set of values |
| Exception type | `IllegalStateException` | Can be considered, while controlling cardinality |
| User email or request payload | `user@example.com`, JSON body | **Never put into metric labels** |
| Customer ID, order ID, full dynamic URL | Unique value per request | Avoid high cardinality and data-exposure risks |
| Raw arguments containing secrets | Token/password/API key | **Never log or attach to metrics** |

In Spring Aspect, `pjp.getSignature().getName()` is a simple way to obtain the method name, yet overloaded methods sharing a name will share one label. In production, normalize keys by **allowlisted class/method** or dedicated business annotations, rather than concatenating `pjp.getArgs()` or input `toString()`.

**Never use full arguments to "distinguish" each metric sample:** that explodes cardinality linearly with requests, overwhelms the metrics backend, and can leak sensitive data.

## 10. Keep Pointcuts Narrow to Avoid Measuring Spring Infrastructure

In the example, the pointcut is:

~~~java
@Around("execution(public * example.TaskService.*(..))")
~~~

It scopes strictly to public method executions on `TaskService`, rather than matching every bean in the context. An overly broad expression such as:

~~~java
@Around("execution(* *(..))")
~~~

can cause Spring to evaluate/match many unintended target methods, adding proxies or unwanted overhead. In large apps, it also mixes business and infrastructure logs/metrics.

Ways to define clearer scopes:

~~~java
// Snippet inside a Spring-managed @Aspect:
@Around(
    "within(com.acme.payment.service..*)"
    + " && execution(public * *(..))"
)
public Object timePaymentService(ProceedingJoinPoint pjp) throws Throwable {
    long started = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        recordPaymentLatency(System.nanoTime() - started);
    }
}
~~~

In this snippet, `recordPaymentLatency` is an illustrative method to be defined on the aspect class; the code is **not a standalone project**.

If only specific methods should be explicitly opted in, use a custom opt-in annotation:

~~~java
@Around("@annotation(com.acme.metrics.TimedOperation)")
~~~

This is only a placeholder annotation expression for a project-defined annotation type (needing `@Target(METHOD)` and `@Retention(RUNTIME)`). When using JDK proxies or annotations on interfaces vs. implementations, **test real matching** in the Spring AOP context; do not infer automatic matching across every proxy strategy merely from seeing the annotation in source code.

**Rule:** Test both positive targets and negative targets. A test verifying only "TaskService.greet is measured" does not prove no other bean was accidentally measured.

## 11. Where in the Advisor Chain Should Timing Sit?

A Spring-managed bean may have multiple advisors:

~~~text
Client
 -> [Timing @Around advisor]
     -> [Transaction interceptor]
         -> [Cache / Security / Other interceptors]
             -> TargetService.method()
~~~

If timing advice sits **outside** the transaction interceptor, the measured duration can include begin/commit/rollback time executed **inside** the transaction interceptor, depending on advisor order.

If timing advice sits **inside** the transaction interceptor:

~~~text
Client
 -> [Transaction interceptor]
     -> [Timing @Around advisor]
         -> TargetService.method()
~~~

then the measurement may **exclude** some transaction setup/teardown overhead outside the advice. Thus, the same service can show different "method duration" and "transaction-inclusive duration" numbers—not because measurement is broken.

### 11.1. `@Order`

Spring AOP allows ordering aspects via `@Order` or `Ordered`:

~~~java
@Aspect
@Order(10)
public class TimingAspect {
    // ...
}
~~~

This is a snippet requiring `import org.springframework.core.annotation.Order` and a valid class body. **Lower** order numbers give higher precedence for aspects; on entry, higher-precedence aspects run earlier, and on exit they run later.

Still, ordering relative to infrastructure advisors such as `@Transactional` and `@Cacheable` also depends on actual Spring configuration. Never assume `@Order(10)` means "always includes transactions" in every context. Document your latency definition, then verify the advisor chain and behavior with integration tests.

### 11.2. Measuring Target Execution Time vs. Caller-Observed Latency?

Distinguish clearly:

- **Target body duration:** ideally counts only time inside business code.
- **Inner chain duration:** counts target plus any interceptors sitting inside timing advice.
- **End-to-end request latency:** can include HTTP routing, authentication, serialization, network waits, and queues outside method advice scope.
- **Async completion latency:** measures until a future/publisher/task truly completes.

`System.nanoTime()` around `pjp.proceed()` in Spring AOP measures **one method call at the proxy boundary**, and does not automatically represent all four metrics. Name metrics to reflect their exact scope so dashboards are not misinterpreted.

## 12. Spring AOP Proxy Boundaries: Cases Not Measured Separately

### 12.1. Self-Invocation via `this`

~~~java
public String outer() {
    return this.inner();
}
~~~

When a caller invokes `outer()` on the Spring proxy, the timing aspect can measure `outer`. Inside the target, however, `this.inner()` **does not go through the proxy again**, so `inner` does not get its own timing sample. Section 6's example demonstrates this clearly with `callInternally()`.

CGLIB **does not cure** self-invocation under proxy-based Spring AOP. If `inner` must be measured separately, a common approach is extracting it to **another Spring bean** and calling it through a Spring-injected proxy; verify the pointcut matches the new bean.

### 12.2. Manually Instantiating With `new` Outside Spring

~~~java
TaskService service = new TaskService();
service.greet("Lan");
~~~

The business method still runs, yet this object is not the Spring AOP proxy bean. Timing advice in the Spring context **never applies automatically** to objects manually constructed outside the container.

### 12.3. Non-Proxyable Methods or Non-Matching Pointcuts

- JDK dynamic proxies primarily intercept public methods exposed on proxied interfaces.
- Class-based CGLIB cannot override `final` methods and cannot intercept `private` methods via subclassing.
- If a pointcut selects `TaskService.greet(..)`, other methods do not automatically receive metrics merely because the bean has a proxy.
- Having an AOP proxy from transaction/cache/other advisors **does not mean** the timing advice matches.

### 12.4. Inner Interceptor Short-Circuit

An `@Around`/cache interceptor sitting **inside** timing advice can return a result without calling the target. Timing aspect still records a sample for **interceptor-chain latency**, because `proceed()` reached the inner interceptor and returned. That **does not prove the target executed**.

If timing advice sits **inside** the short-circuiting interceptor and the inner timing layer is never entered, **no sample is recorded**. This is why you must understand advisor ordering when defining metrics.

## 13. Asynchronous and Reactive Methods: Which Duration Is Recorded?

A Spring bean method may return `CompletableFuture<T>`, `Future<T>`, `Mono<T>`, or `Flux<T>`. In particular:

~~~java
public CompletableFuture<String> startJob() {
    return CompletableFuture.supplyAsync(() -> performBusinessJob());
}
~~~

This is an illustrative snippet assuming `performBusinessJob()` exists. For a method returning a `CompletableFuture` **quickly**, `pjp.proceed()` may return **the future object** before the job actually completes; `finally` in `@Around` immediately records the duration for **the time it took the method to return the future**.

Similarly, a reactive method returning `Mono`/`Flux` may only construct a publisher; work begins when a subscriber subscribes. Duration measured around `proceed()` **does not automatically equal publisher completion time**.

**Decide what you want to measure:**

| Desired metric | Appropriate approach |
| --- | --- |
| Time for method to create/return Future or Publisher | `@Around` around `proceed()` |
| Time until Future completes | Completion hooks such as `whenComplete` or async abstraction instrumentation |
| Time until a reactive pipeline completes/cancels | Lifecycle operators such as Reactor's `doFinally` in the appropriate pipeline |
| End-to-end web request time | HTTP/server observation instead of method advice alone |

Do not attach callbacks to a Future and replace the return object if the business contract requires preserving the exact original object; instrumentation must respect identity and exception/timeout semantics. With Spring `@Async` methods, advisor ordering and proxy type can also shift metric scope from expectations; verify in a real context.

## 14. Performance Thresholds, Time Distributions, and Precision

Timing once is not enough to draw optimization conclusions. Especially for short methods:

- JIT compilation, class loading, and warm-up make initial runs differ from later runs.
- Garbage collection and OS scheduling affect wall-clock elapsed time.
- `System.nanoTime()` has overhead; precision is reported in nanoseconds while actual resolution depends on the platform.
- In multithreaded apps, each invocation has local start/end state, yet aggregating metrics still carries a cost.
- Averages hide tail latency; p95/p99 or histograms may be needed for SLOs.
- Cache hits and cache misses can create vastly different duration distributions; use bounded outcome labels and group semantically.
- Transaction commits, remote I/O, and queueing may fall inside or outside the measured span depending on advisor position.

In production, using a managed library such as **Micrometer Timer/Observation** aligned with the Spring Boot ecosystem is far better than building custom aggregators. Still, the Spring AOP rule remains: `@Around` opens the timer, calls `proceed()`, records in `finally`, and **never alters the return/throw contract**.

## 15. Testing "Without Altering Business Outcomes"

A thorough test suite must verify both **business results** and **sample counts**.

| Test case | Business expectation | Timing expectation |
| --- | --- | --- |
| Caller calls `task.greet("Lan")` via proxy | Exact string `"Hello Lan"` | `count("greet")` increments by one |
| Caller calls `task.fail()` via proxy | `IllegalStateException("boom")` keeps propagating | `count("fail")` increments by one |
| Caller calls `task.callInternally()` | Returns `"Hello Self"` | `count("callInternally")` increments by one; `count("greet")` does **not** increase |
| Caller creates `new TaskService()` and calls `greet()` | Normal Java result | No sample recorded in Spring context metrics |
| Another method outside the pointcut | Normal business result | No timing sample for that method |
| Metrics sink throws error | Expected outcome per instrumentation policy | Test verifies error does not break business logic per policy |
| Concurrent calls | Each call gets accurate result | Sample count matches proxied invocations; counter has no lost updates |
| Future-returning method | Future object/behavior unchanged | Duration around `proceed()` does not inherently span async completion |

### 15.1. Illustrative Assertions Inside Context

After creating `AnnotationConfigApplicationContext` and retrieving `TaskService` and `TimingMetrics` as in section 6, you can verify:

~~~java
String result = task.greet("Mai");
if (!"Hello Mai".equals(result)) {
    throw new AssertionError("return value changed");
}
if (metrics.count("greet") != 1L) {
    throw new AssertionError("wrong timing sample count");
}
~~~

This is an **additional test snippet**, not a standalone program, and should not be mixed directly into `Main.java` if you want to preserve section 6's stdout. For exceptions, use `try/catch` or `assertThrows` in JUnit; verify exception type and message/identity when required by contract.

**Never assert an exact nanosecond value**: duration is a runtime measurement. If you need fully deterministic testing of metric recording, you can inject a mock clock abstraction and an in-memory metrics sink for unit tests, while integration tests should still prove the advice is actually applied by Spring AOP.

## 16. Common Spring AOP Profiling Pitfalls

| Symptom | Common cause | Fix |
| --- | --- | --- |
| Method returns `null` even though target produced a result | `@Around` forgot `return pjp.proceed()` or advice method declared `void` | Return the exact value from proceed |
| Neither metric nor target executes | Around advice returned early without calling proceed | Check shortcut conditions; never short-circuit in timing-only advice |
| Target error turns into a default value | Around advice caught exception without rethrowing | Rethrow original Throwable to preserve exception contract |
| Metric exception replaces original exception | `metrics.record` threw inside `finally` | Design best-effort sink and instrumentation error policy |
| Timings across threads mix up | `startTime` stored in a shared mutable field on singleton aspect | Use a local variable inside around advice |
| Count increments twice for one method | Called `proceed()` twice, duplicate aspect beans, or nested proxies | Check invocation/advisor chain and actual call count |
| Target method did not run yet metric recorded | Inner interceptor/cache short-circuited; timing advice measures chain | Define metric scope and advisor order |
| `this.method()` has no separate timing sample | Spring AOP self-invocation bypassed proxy | Extract method to another bean and call via DI if needed |
| Bean not measured despite `@Aspect` | Aspect not a Spring bean, AOP disabled, or pointcut mismatch | Check `@Bean`/`@Component`, `@EnableAspectJAutoProxy`/Boot auto-config |
| `elapsedMillis` prints as 0 | Integer truncation loses precision for fast operations | Store nanoseconds; use floating-point when converting units |
| Stopwatch using `currentTimeMillis` occasionally goes negative/erratic | System clock adjusted; unsuitable for elapsed timing | Use `System.nanoTime()` |
| Timing placed after `proceed()` without `finally` | Exceptional exit skips recording | Put recording inside `finally` |
| Async task timing is suspiciously tiny | `proceed()` only returned Future/Publisher | Measure completion with appropriate lifecycle callbacks |
| Cardinality explodes uncontrollably | Using user ID/request body as metric label | Standardize bounded labels |
| Latency rises sharply after adding metrics | Synchronous logging/I/O or overly broad pointcut | Reduce overhead, use proper metrics backend, narrow pointcut |

## 17. Applied Questions

**Q1.** Why does `long start=System.nanoTime(); return pjp.proceed();` fail to measure completely when the target can throw an exception?

**Answer:** It has not captured the end timestamp. If recording is placed after proceed without `finally`, exceptional exits skip that statement. Use `try/finally` to record both branches.

**Q2.** A timing aspect returns `"OK"` regardless of what `pjp.proceed()` returns. Does it satisfy "without altering business outcomes"?

**Answer:** No. It changes the caller's return value. Timing-only advice must return the exact result of proceed.

**Q3.** `pjp.proceed()` was called once, yet can a timing sample appear when the target did not run?

**Answer:** Yes. An inner interceptor, such as a cache, may return early. Timing measures the duration of the inner chain the advice traversed, which does not prove the target body ran.

**Q4.** In a singleton aspect, storing `startTime` in a field set by `@Before` and subtracted in `@After`. Is this concurrency-safe?

**Answer:** No if the field is shared across invocations. One thread can overwrite another thread's start time. Use a local variable inside one `@Around` advice.

**Q5.** Target throws `IllegalStateException("boom")`; metrics record succeeds in `finally`. Does the caller still receive the exception?

**Answer:** Yes, if timing advice does not catch/replace the exception. Finally finishes recording and the original exception continues propagating.

**Q6.** `metrics.record(...)` throws `RuntimeException` in `finally` after the target returned normally. Is the caller guaranteed to receive the result?

**Answer:** No. An instrumentation error can replace the result. To preserve contracts, the metrics sink and error-handling policy must avoid propagating unintended measurement errors.

**Q7.** `callInternally()` calls `this.greet()` and is invoked by a caller through the Spring proxy. Does timing separately count the inner `greet`?

**Answer:** No. Self-invocation does not create a new proxied call for `greet`, so only the outer method gets a sample if an advisor matches it.

**Q8.** Should you measure elapsed duration between two `System.currentTimeMillis()` calls when stability is required?

**Answer:** Use `System.nanoTime()` for elapsed duration. Wall-clock time can be adjusted and often has coarser resolution.

**Q9.** If the timing advisor sits outside the transaction interceptor, can the measured sample include transaction commit?

**Answer:** Potentially yes, depending on which interceptors sit inside timing advice. To define "method time" vs. "transaction-inclusive time," inspect advisor order and actual transaction execution.

**Q10.** A method returns `CompletableFuture`, timing `finally` already ran, yet the future is still pending. Is that a bug?

**Answer:** No. It measures the moment the method returned the Future, not necessarily async task completion. Use completion instrumentation if you need full task latency.

## 18. Official Documentation and Further Reading

- [Spring Framework 6.2 — Declaring Advice / Around Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): around advice using `ProceedingJoinPoint`, calling `proceed()`, storing per-invocation state, and preserving return values.
- [Spring Framework — An AOP Example](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/example.html): wrapping methods for profiling and coordinating behavior.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): Spring proxy boundaries, JDK/CGLIB, and self-invocation.
- [Spring Framework — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): enabling Spring AOP, aspect bean requirements, and classpath setup.
- [Spring Framework — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): scoping method executions to avoid out-of-scope overhead.
- [Oracle Java SE API — System.nanoTime()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime()): clock for measuring elapsed time, arbitrary origin, platform-dependent resolution.
