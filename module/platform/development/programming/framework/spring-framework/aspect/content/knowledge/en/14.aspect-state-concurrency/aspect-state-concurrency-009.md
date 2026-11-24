# Measuring Nested and Recursive Calls Through Spring AOP Proxies

## 1. Objectives and Scope

In Spring AOP, timing advice runs only when a method call **passes through a Spring proxy** and matches the pointcut. This determines whether a nested call, a recursive step, or only the outermost call appears in your observed metrics.

After this lesson, you will be able to:
- Distinguish internal Java calls within the same bean from calls going through a Spring-managed proxy.
- Explain why one external call into a bean can trigger `@Around` multiple times, or only once despite multiple methods executing.
- Measure each proxy crossing, preserve return values/exceptions, and track nesting depth per thread.
- Choose between aggregating **inclusive time**, **exclusive time**, and outermost-only timing based on your observability goal.
- Avoid misinterpreting metrics when combining Spring AOP with transactions, async execution, reactive flows, or calls running on another thread.

This lesson focuses on **Spring AOP proxy and advice mechanics**; it does not re-teach general AspectJ/AOP theory.

## 2. Exactly When Does Timing Advice Run?

Suppose a Spring bean has two public methods `outer()` and `inner()`. There are three distinct cases:

| Call path | Goes through Spring proxy at that call site? | Does advice matching `inner()` run? |
| --- | --- | --- |
| Another bean calls `service.inner()`, where `service` is a Spring proxy | Yes | Yes |
| `outer()` calls `this.inner()` or directly calls `inner()` inside the same target object | No | No |
| `outer()` obtains the bean's proxy and calls `proxy.inner()` | Yes | Yes |

When external code calls `proxy.outer()`, the `outer()` call is handled by advice. Afterward, if the body of `outer()` calls `inner()` directly, the inner call **does not automatically re-enter the proxy**. Therefore, adding a pointcut for `inner()` does not cause that internal call to be measured separately.

The same applies to recursion:

~~~text
otherBean -> proxy.outer()        => advice outer
                  |
                  +-> this.inner() => no inner advice
                         |
                         +-> this.inner() => no inner advice

otherBean -> proxy.outer()        => advice outer
                  |
                  +-> proxy.inner(2) => advice inner(2)
                           |
                           +-> proxy.inner(1) => advice inner(1)
                                    |
                                    +-> proxy.inner(0) => advice inner(0)
~~~

A method can recurse many times while the advice sees only **one invocation** if every step after the first calls `this` directly. This does not mean Spring AOP "missed" proxied calls: those nested calls never went through the proxy.

Here Spring AOP uses JDK proxies or class-based proxies (typically CGLIB), depending on configuration. With JDK proxies, calls must go through an interface exposed by the proxy; with class-based proxies, `final` methods cannot be overridden to apply advice. `private` calls, constructors, and code not passing through a Spring proxy also do not become method join points measured by proxy-based Spring AOP.

## 3. Runnable Spring Boot Example: Direct vs Through-Proxy

This example uses **Java 17+**, **Spring Boot 3.3.x**, Spring AOP, and a `WorkService` bean. Using `ObjectProvider<WorkService>` solely illustrates obtaining the **Spring-managed proxy at invocation time** without manually instantiating objects via `new`.

Project structure:

~~~text
pom.xml
src/main/java/com/example/aopdemo/
    DemoApplication.java
    WorkService.java
    TimingAspect.java
~~~

### 3.1. Maven dependencies

File `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>aop-recursion-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
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

`spring-boot-starter-aop` provides the required AOP dependencies and Spring AOP auto-configuration in a Spring Boot app. The examples below assume Spring Boot's default proxy configuration using class-based proxies; `WorkService` and its methods are not declared `final`.

### 3.2. Service: two recursion paths

File `src/main/java/com/example/aopdemo/WorkService.java`:

~~~java
package com.example.aopdemo;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class WorkService {
    private final ObjectProvider<WorkService> self;

    public WorkService(ObjectProvider<WorkService> self) {
        this.self = self;
    }

    public void direct() {
        recurseDirect(2); // called on this, bypasses proxy
    }

    public void recurseDirect(int remaining) {
        if (remaining > 0) {
            recurseDirect(remaining - 1); // still on this
        }
    }

    public void throughProxy() {
        self.getObject().recurseProxy(2); // goes through Spring proxy
    }

    public void recurseProxy(int remaining) {
        if (remaining > 0) {
            self.getObject().recurseProxy(remaining - 1);
        }
    }
}
~~~

In `direct()`, all `recurseDirect` calls are self-invocations. In `throughProxy()`, each `recurseProxy` call uses the bean fetched from the container; when Spring applies an aspect to this bean, that is the proxy. Calling `getObject()` at runtime avoids forcing Spring to resolve a direct self-reference in the constructor.

**Design note:** Self-calling through a proxy is useful to demonstrate AOP behavior, yet makes the service indirectly dependent on proxy mechanics. In business code, prefer extracting the operation needing advice into **another Spring bean** and calling that bean via injection. Avoid manual instantiation with `new WorkService(...)` because that object is not managed by Spring AOP.

### 3.3. Aspect: measuring each proxy call into the service

File `src/main/java/com/example/aopdemo/TimingAspect.java`:

~~~java
package com.example.aopdemo;

import java.util.Arrays;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TimingAspect {
    private final ThreadLocal<Integer> depth =
            ThreadLocal.withInitial(() -> 0);

    @Around("execution(public * com.example.aopdemo.WorkService.*(..))")
    public Object measure(ProceedingJoinPoint joinPoint) throws Throwable {
        int currentDepth = depth.get();
        depth.set(currentDepth + 1);
        long started = System.nanoTime();

        try {
            return joinPoint.proceed();
        } finally {
            long elapsed = System.nanoTime() - started;

            if (currentDepth == 0) {
                depth.remove();
            } else {
                depth.set(currentDepth);
            }

            System.out.printf(
                    "depth=%d | %s%s | %.3f ms%n",
                    currentDepth,
                    joinPoint.getSignature().getName(),
                    Arrays.toString(joinPoint.getArgs()),
                    elapsed / 1_000_000.0
            );
        }
    }
}
~~~

Intentional design choices:

1. `@Around` wraps `proceed()` to measure execution time at the **corresponding proxied call**. `return joinPoint.proceed()` preserves the return value, even when the current example uses `void`.
2. `finally` still runs when business code throws an exception, and the original exception continues propagating outward. The aspect does not silently turn a failed execution into a success.
3. `System.nanoTime()` measures elapsed time, unlike `System.currentTimeMillis()` which gives wall-clock time.
4. `ThreadLocal` tracks nesting depth **on the same thread**. Before exiting the advice, the previous depth must be restored; at the root level `remove()` is called so state is not retained on a reused thread.
5. `depth=0` is the outermost advice invocation **in the measured call chain on this thread**; `depth=1` is a proxied call nested inside it. This is advice depth, not Java call-stack depth or actual recursion count.
6. `System.out.printf` is appropriate for practice exercises; in real applications, prefer a metrics/tracing system and avoid logging every hot call.

The pointcut selects only `public` methods of `WorkService`, making the exact four method names visible in the example. When multiple aspects exist, `@Order` and interceptor ordering can change where timing starts and stops; measurements describe only the execution span inside this advice.

### 3.4. Running both scenarios

File `src/main/java/com/example/aopdemo/DemoApplication.java`:

~~~java
package com.example.aopdemo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner run(WorkService service) {
        return args -> {
            System.out.println("== DIRECT ==");
            service.direct();

            System.out.println("== THROUGH PROXY ==");
            service.throughProxy();
        };
    }
}
~~~

From the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Ignoring Spring Boot startup logs, the example's log lines have the following **order**; actual timing values differ on each run:

~~~text
== DIRECT ==
depth=0 | direct[] | <elapsed> ms
== THROUGH PROXY ==
depth=3 | recurseProxy[0] | <elapsed> ms
depth=2 | recurseProxy[1] | <elapsed> ms
depth=1 | recurseProxy[2] | <elapsed> ms
depth=0 | throughProxy[] | <elapsed> ms
~~~

`recurseDirect(2)`, `recurseDirect(1)`, and `recurseDirect(0)` **do execute**, yet have no separate measurement lines. By contrast, `recurseProxy(2)`, `recurseProxy(1)`, and `recurseProxy(0)` all pass through the proxy; each call triggers one advice execution. Logs are printed in `finally`, so they appear in **completion order from deepest to outermost**, not start order.

Note: `<elapsed>` above is an **illustrative placeholder**, not literal stdout. The program will print a floating-point number with three decimal places there, depending on the machine and run.

## 4. Understanding How to Add and Subtract Timings Properly

Let `T(X)` be the duration measured at the advice wrapping call `X`.

- **Inclusive time** of `outer`: counts time spent inside `outer`, including the duration of synchronous child calls running inside it.
- **Exclusive/self time** of `outer`: approximately inclusive time minus the inclusive times of **measured, non-overlapping direct child calls**.
- **Advice invocation count**: the number of times a *proxy boundary is crossed* matching the pointcut, not necessarily the number of Java calls or actual recursion depth.

Illustrative timing example: if `outer` takes 12 ms and one measured direct child call takes 7 ms, then `outer`'s exclusive time is roughly 5 ms. When `outer` contains nested `childA` and `childB`, avoid subtracting grandchild time once directly and again via the child's time.

**Common mistake:** summing all inclusive times of recursive calls and calling the result total processing time. When a parent call contains child calls, summing them **double-counts** child time inside the parent. To measure latency of the whole task, take the outermost advice's duration or a timer wrapping the entire task; to analyze each layer, keep separate metrics per invocation.

One way to compute exclusive time in synchronous single-thread calls is using `ThreadLocal<Deque<Frame>>`:

~~~text
When entering advice:
    create frame {startedAt, childInclusiveNanos=0}
    push frame onto stack

When exiting advice (in finally):
    inclusive = nanoTime() - frame.startedAt
    exclusive = inclusive - frame.childInclusiveNanos
    pop frame
    if stack still has parent frame:
        parentFrame.childInclusiveNanos += inclusive
    record metric for completed frame
    if stack is empty: remove ThreadLocal
~~~

This is an **illustrative algorithm**, not a standalone compilable Java class. Subtract only direct child frame durations. Decide whether child advice metric/logging overhead counts inside the parent's measured time; subtracting using inconsistent timestamps introduces skew. This calculation also cannot be applied verbatim to parallel branches.

## 5. Three Measurement Policies and How to Choose

| Policy | Collected data | When to use | What to control |
| --- | --- | --- | --- |
| Measure every proxy crossing | One sample per intercepted child/recursive call | Hotspot analysis, per-method or per-layer latency | Sample count can grow rapidly under recursion |
| Measure only outermost advice (`depth == 0`) | One sample for a nested call chain on the same thread | End-to-end latency of the proxy entry call | No separate breakdown for inner layers |
| Record both inclusive and exclusive | Shows total latency and estimates self time per call | Synchronous call-hierarchy profiling | Needs stack frames and non-overlapping addition rules |

If using Micrometer's `Timer`, specify clearly whether the metric represents **one method call**, **one request**, or **one root task**. Good tags are usually a bounded set of method names and outcome (success/error). Avoid putting dynamic inputs, request IDs, full stacks, or unbounded recursion depths into tags: such values cause metrics cardinality explosions.

You can choose a root-only policy using a guard before recording the metric, while still maintaining `depth` on every advice entry and restoring state in `finally`. A "measured" flag that never resets will cause subsequent independent calls on a thread pool to be skipped.

## 6. Practical Pitfalls and Proxy Limitations

### 6.1. Advice does not appear for internal calls

**Symptom:** `outer()` logs appear, yet `inner()` logs do not, even though debugging proves `inner()` ran.

**Cause:** `this.inner()` / bare `inner()` did not go through the proxy. Also verify the bean truly came from the Spring container and the pointcut matches the method/class.

**Preferred fix:** move the logic needing advice to a method on another bean and call that bean via an injected Spring dependency. If keeping it in the same bean and coupling is acceptable, you can obtain a self proxy as in the example. `AopContext.currentProxy()` works only when expose-proxy is configured and during a proxy-intercepted call; it couples code directly to Spring AOP and is not the default choice.

### 6.2. Multiple advice layers around the same call

When `@Transactional`, security advice, caching, or another `@Around` also applies, **advisor ordering** affects the actual span the timer wraps. For instance, a timer outside transaction advice can include transaction start/commit time, whereas a timer inside might miss part of that cost. If measurement semantics matter, configure explicit ordering with `@Order`, verify with tests, and document the boundary.

### 6.3. Deep recursion, exceptions, and instrumentation overhead

- Every proxy interception runs the interceptor chain, adding overhead and stack frames; deep recursion still risks `StackOverflowError`.
- `finally` should record both success and failure while still propagating the original `Throwable`. If adding outcome tags, keep cardinality bounded; avoid putting raw exception messages in tags.
- Do not use `System.currentTimeMillis()` for short measurements needing monotonicity; `nanoTime()` provides elapsed time resolution, not absolute accuracy or CPU time measurement.
- Avoid logging or capturing stack traces on every recursive step in hot paths. Benchmark with realistic workloads to inspect advice overhead.

### 6.4. Thread boundaries and asynchronous calls

`ThreadLocal` only tracks calls running on the **same thread**. With `@Async`, thread pools, or parallel tasks, nested call trees are not automatically stitched together by `ThreadLocal` alone. An `@Around` timing a method that returns `CompletableFuture` may measure only **future creation/return**, not completion. Measure task lifecycles with appropriate instrumentation, or propagate tracing context deliberately across thread boundaries.

With Spring WebFlux/Reactor, a method can return `Mono` or `Flux` immediately; `proceed()` finishing does not mean the publisher has been subscribed to or finished processing. To measure subscription-to-termination, use operators like `doOnSubscribe` and `doFinally` or an appropriate observability system, instead of interpreting method return time as full reactive processing time.

## 7. How to Verify Measurement Results

When a dashboard shows "too few calls" or unusually high total latency, check in order:

1. **Actual call path:** does the caller hold a Spring proxy or a manually instantiated object? Do subsequent calls go through the proxy or are they self-invocations?
2. **Pointcut and interceptability:** does the method match the class/interface, modifier, and scope? With class-based proxies, are `final` or `private` involved?
3. **Counts and order:** in this example, `direct()` produces one measurement line; `throughProxy()` produces four lines, finishing from deepest outward. If wrong, re-check the code and AOP configuration.
4. **Timing semantics:** are you summing inclusive samples causing double-counting, or do you need root-only/exclusive? Are other advisors wrapping outside/inside?
5. **Async boundaries:** are you measuring method return, future completion, or publisher completion? Is trace context propagated across threads?
6. **State health:** after exceptions, does `ThreadLocal` depth return to 0 / get removed? Do method/tag counts stay bounded under load?

## 8. Key Takeaways

In Spring AOP, **the proxy boundary is what creates an advice invocation**. Self-invocation and direct recursion execute normally without being intercepted per layer; going through a Spring proxy on each call triggers advice per layer. Once the right call path is chosen, state clearly whether a metric is inclusive, exclusive, or outermost-only, because summing nested call durations double-counts time. For async and reactive flows, always verify **which lifecycle** is actually being measured.
