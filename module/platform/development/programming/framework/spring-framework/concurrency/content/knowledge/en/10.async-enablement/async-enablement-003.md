# Placing @Async on a Method or Class in Spring Framework

## 1. Problem and Key Outcome

In the Spring Framework, `@Async` marks a **candidate method for asynchronous execution**. There are two common placements:

- Place `@Async` **directly on a method** so only that method is dispatched to an executor when called through a Spring proxy.
- Place `@Async` **on a class** so eligible business methods in the class are treated as async methods; a specific method's executor can be overridden with a method-level annotation.

For example: a service has `generateReport()` taking several seconds and `getDescription()` just reading local data. Placing the annotation on `generateReport()` keeps the two behaviors separate; placing it on the entire class may inadvertently pull `getDescription()` into the async mechanism even though its API still returns `String`. That can lead to a runtime error because the async method's return type is invalid.

**Core point:** annotation placement decides **which methods are intercepted by the proxy**, whereas `@EnableAsync` and the executor decide **how execution actually runs**. Having the annotation alone does not guarantee code runs on another thread: the call must go through a proxy and the chosen executor must actually be capable of offloading work to another thread.

Example scope: Spring Framework 6.x, Spring Boot 3.3.x, Java 17, default proxy mode. AspectJ weaving behavior is mentioned separately because it follows different self-invocation rules than proxies.

## 2. Conditions for @Async to Take Effect

### 2.1. Enable Support

In a Java-configured application, enable `@EnableAsync` once in an appropriate configuration class:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

This is an illustrative configuration snippet, not a complete program. `@SpringBootApplication` can sit on the same class as `@EnableAsync`. `@EnableAsync` applies to the `ApplicationContext` where it is declared; it does not automatically activate for another independent context.

Spring applies an advisor/interceptor to managed beans with eligible async annotations. When external code invokes the method through the proxy, the interceptor resolves the executor, submits the work, and returns control to the caller per the async contract. Without `@EnableAsync` enabled (and without another mechanism activating async), the annotation is merely metadata and the call executes like regular Java.

### 2.2. The Call Must Go Through a Spring Proxy

~~~mermaid
flowchart LR
    Caller["Controller / another bean"] --> Proxy["Spring proxy"]
    Proxy -->|"submits task"| Executor["Selected executor"]
    Executor --> Worker["Worker thread"]
    Worker --> Target["Method on target bean"]
    Self["this.someMethod() inside same bean"] -.->|"bypasses proxy"| Target
~~~

With `@EnableAsync` defaulting to `mode = AdviceMode.PROXY`:

1. **Calling from another bean through a proxy:** the annotation applies if the method is eligible.
2. **Calling `this.asyncMethod()` within the same object:** bypasses the proxy; the method typically runs synchronously on the current thread.
3. **Instantiating `new ReportService()` yourself instead of getting a Spring bean:** no proxy exists; the annotation does not create asynchronicity.
4. **Calling in a constructor, `@PostConstruct`, or too early before the proxy is ready:** not a reliable way to trigger async. To launch after startup, have another bean call the proxied service.

With subclass-based proxies, `private` and `final` methods cannot be overridden by a subclass proxy for interception; `final` classes also get in the way. With JDK interface proxies, only calls going through the interface proxy are intercepted. For predictable code, place `@Async` on **public methods of a Spring-managed service**, injected and called by another caller.

`@EnableAsync(mode = AdviceMode.ASPECTJ)` combined with weaving can intercept internal calls too, but requires AspectJ configuration and is not the default in these examples.

## 3. Placing @Async on Individual Methods

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    @Async("reportExecutor")
    public CompletableFuture<String> generate(String id) {
        String path = "reports/" + id + ".csv";
        return CompletableFuture.completedFuture(path);
    }

    public String description() {
        return "Report service";
    }
}
~~~

This class can be placed in a Spring application with async enabled and an executor named `reportExecutor` declared; callers must invoke it through a Spring proxy.

- `generate(id)` is an async candidate on `reportExecutor` because the annotation sits directly on the method.
- `description()` has no annotation and the class has no `@Async`, so normal calls still run synchronously.
- Returning `CompletableFuture.completedFuture(path)` **inside the executing method** does not conflict with async: the Spring proxy returns a Future representing the work run by the executor, while the implementation must conform to the declared signature.
- This snippet builds a quick path string purely for illustration; turning it into real report generation requires state persistence, backpressure, timeouts, and resource controls.

You can use `@Async` without specifying an executor name:

~~~java
// Illustrative snippet in a Spring-managed bean:
@Async
public void refreshCache() {
    // Async method returning no result to the caller.
}
~~~

In that case, Spring uses the default executor configured or found in the context. Do not guess thread counts solely from the presence of `@Async`; Spring Framework has its own fallback, and Spring Boot has its own auto-configuration layer.

## 4. Placing @Async on the Entire Class

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
@Async("batchExecutor")
public class BatchService {
    public CompletableFuture<String> rebuildIndex() {
        return CompletableFuture.completedFuture("index");
    }

    public CompletableFuture<String> publishSnapshot() {
        return CompletableFuture.completedFuture("snapshot");
    }

    @Async("reportExecutor")
    public CompletableFuture<String> urgentRebuild() {
        return CompletableFuture.completedFuture("urgent");
    }
}
~~~

When a caller in another bean invokes through the Spring proxy:

- `rebuildIndex()` and `publishSnapshot()` get async applied with `batchExecutor`, because `@Async("batchExecutor")` is placed on the class.
- `urgentRebuild()` has its own `@Async("reportExecutor")` annotation, **giving precedence to the method qualifier** over the class qualifier.
- If a method-level `@Async` has an empty value, it indicates selecting the default executor per resolution rules, rather than necessarily inheriting the class's executor name. When designing multiple pools, specify qualifiers explicitly on methods that need to differ.
- A class-level annotation does not turn constructors, field initializers, internal calls, or all private methods into independent tasks.

Placing the annotation on the class makes sense when most of a service's public API is designed from the start to be async. However, future edits easily introduce side effects: someone adds a helper method returning `String` or `long` to the class and accidentally makes it an async candidate with an invalid return type.

### Scope Comparison

| Placement | Which Methods Are Affected? | Pros | Risks |
| --- | --- | --- | --- |
| `@Async` on one method | That method when called via proxy | Precise control, easy to review | Easy to forget annotating a newly added async method |
| `@Async` on class | Eligible business methods of the class when called via proxy | Concise when the whole service is async | Easy to affect newly added methods with incompatible return types |
| Class `@Async("batchExecutor")` + method `@Async("reportExecutor")` | Class default, overridden by specific method | Separates pools for priority tasks | Requires checking qualifiers and executor configuration |
| Unannotated class + unannotated method | No async interceptor from these annotations | Clear synchronous behavior | Requires another mechanism to run asynchronously |

**Example to avoid:**

~~~java
// Illustrative anti-pattern; do not call this method through an @Async proxy.
@Service
@Async("batchExecutor")
public class MixedPurposeService {
    public String status() {
        return "READY";
    }
}
~~~

In a standard async proxy, Spring only supports return types `void`, `Future<T>`, or `CompletableFuture<T>`. If `status()` is handled by the async interceptor, returning `String` does not match and may fail with `IllegalArgumentException` instead of returning the string as before. Separate synchronous status/query methods into another bean, or annotate only individual async methods.

## 5. Runnable Project: Method-Level vs. Class-Level

The Java 17 + Spring Boot 3.3.5 application below has two executors with different prefixes. We observe the **actual thread of the intercepted method** and avoid relying on `Thread.sleep` or arbitrary execution ordering.

### 5.1. Structure

~~~text
async-placement-demo/
├── pom.xml
└── src/main/java/com/example/async/
    ├── AsyncPlacementApplication.java
    ├── MethodOnlyService.java
    └── ClassWideService.java
~~~

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>async-placement-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-aop` ensures AOP proxy infrastructure is on the demo's classpath; `@Async` is activated via `@EnableAsync`. This is a command-line application with no web server needed.

### 5.3. AsyncPlacementApplication.java

~~~java
package com.example.async;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@SpringBootApplication
@EnableAsync
public class AsyncPlacementApplication {
    public static void main(String[] args) {
        // ApplicationRunner runs inside SpringApplication.run() before returning the context.
        SpringApplication.run(AsyncPlacementApplication.class, args).close();
    }

    @Bean("reportExecutor")
    ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(1);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("report-");
        return pool;
    }

    @Bean("batchExecutor")
    ThreadPoolTaskExecutor batchExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(1);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("batch-");
        return pool;
    }

    @Bean
    ApplicationRunner verifyPlacement(
            MethodOnlyService methodService, ClassWideService classService) {
        return args -> {
            String caller = Thread.currentThread().getName();

            // Submit through the proxy first, then wait, to read the actual thread name inside the task.
            CompletableFuture<String> method = methodService.generateReport();
            CompletableFuture<String> cls1 = classService.rebuildIndex();
            CompletableFuture<String> cls2 = classService.publishSnapshot();
            CompletableFuture<String> override = classService.urgentRebuild();

            System.out.println("METHOD_LEVEL_REPORT_POOL="
                    + method.get(5, TimeUnit.SECONDS).startsWith("report-"));
            System.out.println("UNANNOTATED_STAYS_CALLER="
                    + methodService.descriptionThread().equals(caller));
            System.out.println("CLASS_METHOD_1_BATCH_POOL="
                    + cls1.get(5, TimeUnit.SECONDS).startsWith("batch-"));
            System.out.println("CLASS_METHOD_2_BATCH_POOL="
                    + cls2.get(5, TimeUnit.SECONDS).startsWith("batch-"));
            System.out.println("METHOD_OVERRIDES_CLASS="
                    + override.get(5, TimeUnit.SECONDS).startsWith("report-"));
            System.out.println("SELF_INVOCATION_STAYS_CALLER="
                    + methodService.selfInvocationThread().equals(caller));
        };
    }
}
~~~

Both executor beans are managed, initialized, and cleaned up across their lifecycle by Spring. Each pool has only one worker so thread names are easy to trace; `queueCapacity=8` does not mean eight workers. Do not rely on Spring Framework or Boot default thread counts in this test.

### 5.4. MethodOnlyService.java

~~~java
package com.example.async;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class MethodOnlyService {
    @Async("reportExecutor")
    public CompletableFuture<String> generateReport() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName());
    }

    // No @Async on method or class -> runs directly on caller.
    public String descriptionThread() {
        return Thread.currentThread().getName();
    }

    public String selfInvocationThread() {
        // Called via this, bypassing Spring proxy, so it runs inline.
        return generateReport().join();
    }
}
~~~

Note that `selfInvocationThread()` is **not** annotated with `@Async`; since the call from ApplicationRunner targets a synchronous method, it runs on the caller. Inside it, `generateReport()` is invoked directly via `this`, so the annotated method runs inline. If replaced by a call from another bean through a proxy, `generateReport()` will be dispatched to `reportExecutor`.

### 5.5. ClassWideService.java

~~~java
package com.example.async;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
@Async("batchExecutor")
public class ClassWideService {
    // No @Async needed on the method because the class already has it.
    public CompletableFuture<String> rebuildIndex() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName());
    }

    public CompletableFuture<String> publishSnapshot() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName());
    }

    @Async("reportExecutor")
    public CompletableFuture<String> urgentRebuild() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName());
    }
}
~~~

### 5.6. Running and Verifying stdout

In the directory containing `pom.xml`, with JDK 17+ and Maven:

~~~bash
mvn spring-boot:run
~~~

Ignoring Spring startup/shutdown logs, the program prints **six lines** in order (all booleans; no assumptions about thread name suffixes):

~~~text
METHOD_LEVEL_REPORT_POOL=true
UNANNOTATED_STAYS_CALLER=true
CLASS_METHOD_1_BATCH_POOL=true
CLASS_METHOD_2_BATCH_POOL=true
METHOD_OVERRIDES_CLASS=true
SELF_INVOCATION_STAYS_CALLER=true
~~~

Explanation: `get(5, TimeUnit.SECONDS)` is only called **after** obtaining the future handles, so the program makes no assertions about completion order between executors; it simply awaits each bounded result. Method-level `generateReport` runs in `report-*`, the two class-level methods run in `batch-*`, and `urgentRebuild` overrides to use `report-*`. `descriptionThread()` and internal `selfInvocationThread()` both run on the caller and thus match the recorded thread name.

**This test verifies annotation placement and proxy routing**, not throughput limits or actual load capacity. To test overlapping execution, use a `CountDownLatch`/barrier with a multi-worker pool and assert invariants rather than merely looking at thread names.

## 6. Method Contracts When Deciding Annotation Placement

The placement of `@Async` must match the signature of **every intercepted method**: `void`, `Future<T>`, or `CompletableFuture<T>`. When placing the annotation at class level, inspect all public business methods; a getter returning `String` added later can inadvertently get async advice applied and fail due to an unsupported return type.

| Method Kind | Recommended Placement | Observation Channel |
| --- | --- | --- |
| Background execution, no result | Method-level `@Async` | Handler/logging for `void` errors |
| Produces result and requires coordination | Method-level or controlled class-level | Future/CompletableFuture, timeout, and errors |
| Synchronous query/getter returning `String`/DTO | Must not be covered by class-level `@Async` | Direct result on caller |

A caller calling `get()`/`join()` right after submission can still block; callbacks on `CompletableFuture` allow more flexible task chaining. When a task fails, the future completes exceptionally; when an executor rejects at submission time, rejection must be handled at the call boundary. Detailed composition, cancellation, and exception mechanics belong to the return type's own contract, separate from the decision of **method vs. class placement**.

## 7. Understanding the Executor When Attaching the Annotation

`@Async("reportExecutor")` specifies a **bean name or qualifier**, not a thread count. You must declare the corresponding executor bean and monitor queue/rejection policies.

If `@Async` has no qualifier:

1. `@EnableAsync` may use the executor provided by `AsyncConfigurer`.
2. In the Spring Framework, the default mechanism looks for a unique `TaskExecutor` bean; if none is selected, it checks an `Executor` bean named `taskExecutor`.
3. If no suitable candidate exists, the Spring Framework falls back to `SimpleAsyncTaskExecutor`. This is not a reusable worker pool like `ThreadPoolTaskExecutor`.
4. Spring Boot may provide an executor via auto-configuration when conditions match; in a Boot environment, the actual outcome also depends on existing beans and properties.

When using multiple executors, **explicitly specify qualifiers for methods with special requirements**. For class-level annotations, note both the class default and method overrides during reviews. Do not assume that adding an arbitrarily named bean will make every `@Async` use that bean automatically.

In production applications, configure `corePoolSize`, `maxPoolSize`, `queueCapacity`, thread name prefix, timeouts, and overload behavior; never leave queues unbounded. A 4-worker pool does not guarantee four CPU-bound tasks run faster than one core or that the DB has enough connections; measure in practice.

## 8. Request State, Transactions, and Cross-Thread Effects

Async calls offloading work to another thread (when using a truly asynchronous executor) alter context assumptions:

- **Transactions:** the HTTP/request thread's transaction does not transfer automatically to the worker. If an async method needs a transaction, establish the boundary on a service called by the worker on that thread, such as `@Transactional` via a proxy call, and scope transactions around DB operations. Do not hold a transaction open during slow API calls or file generation.
- **Request scope:** `@RequestScope` beans and `RequestContextHolder` are normally bound to the request thread. Do not assume workers can always access request context. Extract needed values (request ID, user ID, immutable DTOs) before dispatching.
- **SecurityContext/MDC/ThreadLocal:** not present on workers by default. Use an appropriate context propagation mechanism or pass data explicitly, and clear thread-local state when threads are reused.
- **Mutable inputs:** if the caller continues mutating a list/DTO after submitting work, the worker may see inconsistently changing data. Pass immutable snapshots or use proper synchronization.
- **Errors/side effects:** the worker may write results after the caller times out or the client retries. Design idempotency keys and job states to prevent duplicate processing.

Placing `@Async` on an entire class **does not make singleton fields thread-safe**. Multiple workers can invoke the same instance concurrently, so `count++` on a mutable field still loses updates. Prefer stateless services, `AtomicLong`/locks for in-JVM state, or transactions/optimistic locking for data shared across pods.

## 9. Common Mistakes When Choosing @Async Placement

| Symptom | Common Cause | How to Verify/Fix |
| --- | --- | --- |
| Has `@Async` yet still runs on caller | Missing `@EnableAsync`, manually `new`-ing object, or self-invocation | Check bean proxy and thread name; call from another bean |
| Method in `@Async` class returning `String` fails | Class-level annotation covered a synchronous getter/query | Split beans or annotate only async methods; return a valid Future |
| Special method runs on wrong pool | Class-level qualifier is active; method did not override properly | Use `@Async("executorName")` and check thread name |
| `private`/`final` method not intercepted | Default proxy limitation | Use public, non-final methods called from outside the proxy |
| Exception in `void` never reaches caller | Task ran on worker with no result handle | Configure `AsyncUncaughtExceptionHandler`, logging, and metrics |
| Future never completes | Task lost under overload/shutdown or stuck on I/O | Use signaling rejection, deadlines, timeouts, and job status |
| HTTP responds slowly despite using async | Caller immediately invokes `future.join()/get()` | Return job ID/202 early, add separate status endpoint |
| Reading request/transaction context fails on worker | Context is thread-bound, not transferred automatically | Pass required IDs/data; open transaction on worker |
| Tests with synchronous executor still pass | `SyncTaskExecutor` does not switch threads and hides races/context bugs | Also test with production-like executor and controlled concurrency |
| Placed `@Async` on `@PostConstruct` | Lifecycle callback is not a suitable async trigger point | Have another initializing bean call through proxy after context is ready |

## 10. Decision Guide and Review Checklist

**Prefer method-level placement when:** the class has both synchronous queries and async commands, few methods need background execution, or each job needs its own executor. This is usually the easiest option to control for controllers/services with mixed APIs.

**Class-level placement can be used when:** every public business method on the class is intentionally async, return types are all compatible, and the team agrees that newly added methods automatically obey async rules. To prevent accidental contract changes, document the constraint on the class and keep synchronous utilities/queries in another bean.

Before shipping code to production, check:

1. The bean is Spring-managed and `@EnableAsync` is enabled in the right context; `new` is not called in place of the bean.
2. Callers invoke through a proxy from another bean; do not rely on `this.method()` or constructors/`@PostConstruct`.
3. Annotation placement on method vs. class is intentional; for class-level, **all public business methods** and return types have been audited.
4. The executor name/qualifier is accurate and available; pools/queues are bounded, rejection policies signal failure, and graceful shutdown is reasonable.
5. Callers know how to observe outcomes: `void` has logging/metrics; `Future/CompletableFuture` has error handling and timeouts; HTTP requests are not blocked unnecessarily.
6. Tasks receive safe inputs and manage transactions, request context, security context, and MDC properly across thread boundaries.
7. Tests verify method-level/class-level/method overrides; real concurrency tests cover shared state and saturation tests verify rejection.
8. When running multiple instances, critical job state lives in a reliable DB/broker with appropriate retries/idempotency.

### Self-Check Questions

1. If only `generateReport()` needs background execution while `getSummary()` must return `String` immediately, where should you place `@Async` and why?
2. `@Async("batchExecutor")` on the class and `@Async("reportExecutor")` on a method coexist: which executor does that method use?
3. Within the same bean, is `this.generateReport()` caught by the default `@EnableAsync` interceptor? How do you trigger it properly?
4. Why should a method in an `@Async` class not return `List<Report>` directly when intercepted by a proxy?
5. What is the difference between an exception in a worker returning `CompletableFuture` and an exception in an `@Async void` method?
6. If tests use `SyncTaskExecutor` while production uses `ThreadPoolTaskExecutor`, what can change regarding transactions, ThreadLocals, ordering, and errors?
7. For an endpoint meant to return 202 immediately after accepting a request, why shouldn't you call `future.get()` directly on the request thread?

**Remember:** place `@Async` on a **method** to explicitly identify what runs in the background; place it on a **class** when every eligible business method is designed to be async. Both depend on `@EnableAsync`, proxies, executors, and valid return types. Having the annotation present in source code is not proof that tasks actually run on workers.

## Official Documentation

- [Spring Framework 6.2 — The @Async Annotation](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html#scheduling-annotation-support-async)
- [Spring Framework 6.2 — EnableAsync Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Spring Framework 6.2 — Async Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/annotation/Async.html)
