# Dependencies Injected into Aspects and Thread-Safety Requirements in Spring AOP

## 1. The Problem to Solve

In a Spring application, an `@Aspect` is typically a singleton bean of the `ApplicationContext`. When multiple requests invoke proxied Spring beans, advice methods can run concurrently on the **same aspect instance**. Spring successfully injecting a dependency only confirms that the bean was found and wired into the aspect; it **does not prove** that the dependency or its usage is thread-safe.

This lesson focuses on **Spring-managed aspects, Spring AOP proxies, DI, and Spring bean scopes**, without repeating general AOP concepts.

A `@Before`, `@AfterReturning`, or `@Around` advice may call a repository, recorder, clock, policy service, tracer, and HTTP client. Every interaction with shared state of these dependencies must be reviewed against the same standards as Java concurrency.

## 2. Three Types of State to Distinguish

| Type | Examples | Rule |
| --- | --- | --- |
| Data for **a single call** | `JoinPoint`, arguments, user ID, start time, stopwatch, exception | Keep in an advice local variable or a local context object |
| **Intentional shared** state | Total call count, metric counters, concurrent cache | Use appropriate concurrency primitives/abstractions: `AtomicInteger`, `LongAdder`, `ConcurrentHashMap`, or synchronization when needed |
| Injected dependency | Logger, repository, singleton service, custom recorder | Inspect its contract and implementation; injection, `final`, and singleton **do not automatically create** thread-safety guarantees |

An **incorrect** example in a singleton aspect:

~~~java
@Aspect
@Component
class UnsafeTraceAspect {
    private Object[] lastArgs;
    private long startedAt;

    @Around("execution(* demo.CatalogService.quote(..))")
    public Object trace(ProceedingJoinPoint pjp) throws Throwable {
        lastArgs = pjp.getArgs();
        startedAt = System.nanoTime();
        try {
            return pjp.proceed();
        } finally {
            // Another thread may have already changed lastArgs and startedAt.
            System.out.println(lastArgs[0] + ":" + (System.nanoTime() - startedAt));
        }
    }
}
~~~

The danger lies in the shared fields, not in `ProceedingJoinPoint` as a concept. Call B can overwrite the fields between two steps of call A, causing A to record the wrong request, log the wrong identifier, or even leak information.

The right fix:

~~~java
@Around("execution(* demo.CatalogService.quote(..))")
public Object trace(ProceedingJoinPoint pjp) throws Throwable {
    Object[] argsForThisCall = pjp.getArgs().clone();
    long startedForThisCall = System.nanoTime();
    try {
        return pjp.proceed();
    } finally {
        long elapsed = System.nanoTime() - startedForThisCall;
        record(argsForThisCall, elapsed);
    }
}
~~~

`record(...)` in the example is only an illustrative call; the recorder's own implementation must also be safe under concurrent access. Cloning the array only protects the **array structure**, not mutable objects inside it.

## 3. How Does Spring Create and Inject an Aspect?

With `@EnableAspectJAutoProxy` configuration or equivalent Spring Boot AOP infrastructure, Spring takes beans annotated with `@Aspect` and turns matching advice into advisors for proxies.

- `@Component` + `@Aspect` can be discovered by component scanning; alternatively, a `@Bean` method can return the aspect instance.
- Constructor injection is the most convenient choice: required dependencies are verified at construction time and their references can be `final`.
- A Spring aspect uses the singleton model by default; the proxied target bean can have a different scope. Target scope and dependency scope must be examined separately.
- Spring AOP applies at **method execution through a proxy**. A self-invocation like `this.quote(...)` inside the target goes straight to the target and bypasses advice on that call.

Constructor injection example:

~~~java
@Aspect
@Component
public class TraceAspect {
    private final MetricRecorder recorder;

    public TraceAspect(MetricRecorder recorder) {
        this.recorder = recorder;
    }

    @Before("execution(* demo.CatalogService.quote(..))")
    public void before(JoinPoint joinPoint) {
        Object[] invocationArgs = joinPoint.getArgs().clone();
        recorder.increment();
        // invocationArgs exists only within the current advice invocation.
    }
}
~~~

`final` keeps the `recorder` reference unchanged after construction; if `recorder.increment()` uses `count++` on a plain `int`, races/lost updates still occur.

## 4. Runnable Example: Spring 6.2, Java 17, Maven

Minimal project, with all required files:

~~~text
spring-aspect-dependency-concurrency/
  pom.xml
  src/main/java/demo/App.java
  src/main/java/demo/CatalogService.java
  src/main/java/demo/MetricRecorder.java
  src/main/java/demo/TraceAspect.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-aspect-dependency-concurrency</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.19</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-aop</artifactId>
      <version>6.2.19</version>
    </dependency>
    <dependency>
      <groupId>org.aspectj</groupId>
      <artifactId>aspectjweaver</artifactId>
      <version>1.9.25</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
        <configuration><release>17</release></configuration>
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

**CatalogService.java**

~~~java
package demo;

import org.springframework.stereotype.Component;

@Component
public class CatalogService {
    public String quote(String sku) {
        return "quote:" + sku;
    }
}
~~~

**MetricRecorder.java**

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class MetricRecorder {
    private final AtomicInteger calls = new AtomicInteger();

    public void increment() {
        calls.incrementAndGet();
    }

    public int count() {
        return calls.get();
    }
}
~~~

**TraceAspect.java**

~~~java
package demo;

import org.aspectj.lang.JoinPoint;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TraceAspect {
    private final MetricRecorder recorder;

    public TraceAspect(MetricRecorder recorder) {
        this.recorder = recorder;
    }

    @Before("execution(public * demo.CatalogService.quote(..))")
    public void beforeQuote(JoinPoint jp) {
        Object[] localArgs = jp.getArgs().clone();
        if (localArgs.length != 1) {
            throw new IllegalStateException("Unexpected method signature");
        }
        recorder.increment();
    }
}
~~~

**App.java**

~~~java
package demo;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan("demo")
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class App {
    public static void main(String[] args) throws Exception {
        try (var ctx = new AnnotationConfigApplicationContext(App.class)) {
            CatalogService catalog = ctx.getBean(CatalogService.class);
            MetricRecorder recorder = ctx.getBean(MetricRecorder.class);

            ExecutorService pool = Executors.newFixedThreadPool(4);
            CountDownLatch start = new CountDownLatch(1);
            try {
                List<Future<String>> futures = new ArrayList<>();
                for (int i = 0; i < 20; i++) {
                    final int index = i;
                    Callable<String> task = () -> {
                        start.await();
                        return catalog.quote("sku-" + index);
                    };
                    futures.add(pool.submit(task));
                }
                start.countDown();
                Set<String> distinct = new HashSet<>();
                for (Future<String> future : futures) {
                    distinct.add(future.get());
                }
                System.out.println("distinctResults=" + distinct.size());
                System.out.println("recordedCalls=" + recorder.count());
            } finally {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.App
~~~

Expected application output (ignoring Maven-specific messages if any):

~~~text
distinctResults=20
recordedCalls=20
~~~

This result confirms a thread-safe counter and independent task data. It **does not prove that every arbitrary dependency** is also thread-safe. This code has been statically reviewed against Spring/Java APIs; no Maven execution result is claimed.

## 5. Which Dependencies Need Careful Inspection?

### Singleton services with mutable state

A singleton `@Service` holding an `ArrayList`, `HashMap`, `int counter`, `StringBuilder`, or request ID in a field risks races when the aspect calls it concurrently. Do not treat `private final HashMap` as safe just because the reference is final. Use concurrent structures, locks, or a stateless design depending on the invariant.

### Spring Data repositories, transactions, and persistence contexts

Repository beans are typically Spring proxies designed for shared injection. However, specific JPA entity/persistence contexts, transaction resources, and returned mutable objects are not inherently shareable across threads. Keep transactions along proper business boundaries; do not store an `EntityManager` bound to one invocation in an aspect field for use by the next request.

### Request-scoped beans and scoped proxies

If a singleton aspect needs a request-scoped dependency, design a scoped proxy or `ObjectProvider` per Spring conventions. Switching threads via `@Async` or `CompletableFuture` may lose the request context needed to resolve the dependency. Do not cache a newly resolved request-scoped target in a singleton field.

### HTTP clients, metrics, loggers, and tracing

Read the contract of the specific library. Many client/metric abstractions allow concurrent reuse, while specific builders, requests, responses, or sessions can be mutable. Use per-invocation builders, messages, and spans. For thread-bound tracing contexts, close the scope in `finally` on the right thread and avoid mixing requests.

## 6. Atomic Does Not Mean Every Algorithm Is Correct

`AtomicInteger.incrementAndGet()` guarantees incrementing the count without lost updates. It **does not** guarantee a check-then-act sequence across multiple fields:
 
~~~java
if (active.get() < limit) {
    active.incrementAndGet(); // Can exceed limit when multiple threads run simultaneously.
}
~~~

If the invariant requires the entire operation to be atomic, use a CAS loop, `Semaphore`, lock, or a data mechanism with the corresponding atomic operation. For very high-frequency metrics, `LongAdder` may be better suited than `AtomicInteger` if the goal is throughput and an exact linearizable snapshot at every instant is not required.

## 7. Which Thread Does Advice Run On?

Synchronous Spring AOP advice runs on the thread making the call through the proxy, unless advisors such as `@Async`, schedulers, or reactive pipelines change the time or thread of observation.

- `@Async`: advice outside the async interceptor may run on the caller thread, while the target executes on an executor thread. Advisor order and proxy configuration determine the observation boundary.
- `Future`/`CompletionStage`: a method returning a future successfully **differs** from the async work completing successfully. Do not treat `@AfterReturning` as a terminal result callback.
- Reactor `Mono`/`Flux`: a method may return a publisher before the pipeline is subscribed to. To track terminal signals, integrate Reactor operators intentionally rather than sharing mutable fields in the aspect.
- ThreadLocal: do not store data in a field as a "replacement" for ThreadLocal; if using ThreadLocal, maintain a set/restore/remove contract and check thread pools and self-invocation.

## 8. How to Test for Races and Spring Boundaries

Concurrent testing should use barriers/latches to create contention, run multiple iterations, and assert invariants. Avoid comparing log ordering across threads because the scheduler is nondeterministic. With the demo above, you can assert `recordedCalls == N` and that each response matches its input; intentionally using `int++` does not guarantee every run will fail, because races are nondeterministic.

Verify that the bean actually goes through a proxy using `AopUtils.isAopProxy(bean)`, and run tests with both JDK proxies and class-based proxies when the application uses both models. Test self-invocation, `final`/`private` methods, and targets created with `new` to distinguish proxy boundary issues from concurrency bugs.

## 9. Spring Application Checklist

1. Verify the aspect's lifecycle in the `ApplicationContext`, target type, and proxy configuration.
2. Keep arguments, `JoinPoint`, user ID, start time, result, and exceptions within the invocation's scope.
3. Inspect every injected dependency: does it have mutable state, what is its thread-safety contract, and what is its scope?
4. Use constructor injection and `final` references to make dependencies explicit, while verifying the safety of their implementations separately.
5. Measure/test real concurrency, checking multi-field invariants and event ordering rather than relying on a single test run.
6. Review `@Async`, transactions, request scope, reactive contexts, and cleanup before deployment.

## 10. Official Documentation

- Spring Framework Reference — Core AOP, `@AspectJ` support, advice, and Spring proxies: https://docs.spring.io/spring-framework/reference/core/aop.html
- Spring Framework Reference — Bean scopes: https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html
- Java API — AtomicInteger: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html

**Remember:** In Spring, a dependency injected into an aspect can be **used concurrently by multiple proxy calls**. Keep per-call state in local variables and prove thread safety for every genuinely shared state.