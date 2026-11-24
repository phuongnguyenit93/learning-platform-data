# Testing Cross-Request State Isolation Under Concurrent Calls in Spring AOP

## 1. Objectives and Scope

When multiple HTTP requests or service calls go through the same Spring AOP proxy, **each call must preserve its own context data**: request ID, user ID, tenant, audit metadata, timing labels, correlation ID, and processing outcome. This lesson focuses on **how to design and test state isolation in a Spring Aspect**, especially when the aspect is managed by Spring as a singleton bean. It does not go deeply into general AOP theory.

After this lesson, you will be able to:

- Distinguish data living in **advice local variables** from data placed in **shared aspect fields**.
- Reproduce a cross-request state corruption bug between two concurrent calls using JUnit and synchronization primitives, rather than hoping a bug shows up by running a test many times.
- Properly test **Spring AOP proxies/advice**, covering success paths, exception paths, and context cleanup.
- Identify boundaries when an application uses thread pools, async tasks, or Spring WebFlux.

**Scenario:** request A carries correlation ID `A`, request B carries `B`. If the advice writes the current ID into a `currentId` field of a singleton aspect, B can overwrite it while A is executing. When A resumes, A's log or audit receives B's ID. This is a context isolation bug; the system can return the right business result while auditing is still wrong.

## 2. Why Are Spring Aspects Prone to This Bug?

Buggy example:

~~~java
@Aspect
@Component
class AuditAspect {
    private String currentRequestId; // shared state on singleton aspect

    @Around("execution(* com.example.orders.OrderService.*(..))")
    public Object audit(ProceedingJoinPoint pjp) throws Throwable {
        currentRequestId = getRequestId();
        try {
            Object result = pjp.proceed();
            writeAudit(currentRequestId, result);
            return result;
        } finally {
            currentRequestId = null;
        }
    }

    // getRequestId and writeAudit are application functions, omitted in this illustrative example.
}
~~~

Advice invocations run on different threads yet typically operate on **one aspect object**. The `currentRequestId` field is shared state. `volatile`, if added, only provides visibility; it **does not** make data private to each request. Putting `synchronized` on the entire advice serializes the business segment, reduces concurrency, and is not a sound audit design.

Appropriate fix for data living only within a single call:

~~~java
@Aspect
@Component
class AuditAspect {
    @Around("execution(* com.example.orders.OrderService.*(..))")
    public Object audit(ProceedingJoinPoint pjp) throws Throwable {
        String requestId = getRequestId(); // local variable separate for each invocation
        try {
            Object result = pjp.proceed();
            writeAudit(requestId, result);
            return result;
        } catch (Throwable error) {
            writeFailureAudit(requestId, error);
            throw error;
        }
    }

    // getRequestId, writeAudit, and writeFailureAudit are implemented by the application.
}
~~~

This is **illustrative code showing how to structure advice**, not a standalone runnable program because the audit integration helpers have no body. The core point is never keeping per-request data in an aspect field. Fields should hold only collaborators safe for shared use (services, repositories, meter registries, immutable config), or state specifically synchronized with clear shared semantics.

| State location | Actual lifetime scope | Assessment |
| --- | --- | --- |
| Local variable inside one advice run | Private to that invocation | Best suited for correlation ID, start time, temporary results |
| Mutable field of singleton `@Aspect` | Shared across concurrent invocations | Risk of overwriting, misreading, and races |
| `ThreadLocal` / MDC | Bound to the current thread | Usable in synchronous flows, **must be cleaned up**; does not automatically follow one request across all threads |
| Spring MVC request-scoped context | Bound to the active request | Useful in HTTP servlet requests, requires proper scope/proxy access |
| Reactor `Context` in WebFlux | Follows the reactive chain/subscription | Right approach for reactive context; do not treat ThreadLocal as a general request context |

## 3. Designing a Test Case Capable of Reproducing the Bug

Conventional tests calling A then B sequentially rarely expose the bug. A concurrent test needs an explicit execution schedule:

1. Create **one service proxy and one shared aspect instance**.
2. Run two calls `execute("A")` and `execute("B")` on two worker threads.
3. Inside the target service, use `CyclicBarrier(2)` to hold both threads until **both have passed the advice's write step**.
4. Release the barrier so both return to the advice and read the data the advice holds.
5. Assert that the data returned for A is still A and for B is still B. Run the same test against advice using only local variables.

A barrier creates an execution schedule guaranteed to expose the race by design. `Thread.sleep(...)` does not guarantee two calls actually overlap, leading to flaky tests.

Note: the sample below calls the service **through a Spring AOP proxy created with `AspectJProxyFactory`**, without creating real HTTP requests. It directly tests state-sharing bugs in Spring advice. The next section covers testing through an application context and HTTP boundaries.

## 4. JUnit 5 Example: Proving the Bug and Verifying the Fix

For a Spring Boot 3.x / Java 17+ app, include the following dependencies in the existing Spring Boot module's Gradle configuration:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-aop` supplies the Spring AOP and AspectJ integration needed for `@Aspect`; `spring-boot-starter-test` supplies JUnit Jupiter and testing utilities. The dependency snippet above assumes the project already configures the Spring Boot plugin and appropriate version management.

Create file **`src/test/java/demo/AspectStateIsolationTest.java`**:

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.junit.jupiter.api.Test;
import org.springframework.aop.aspectj.annotation.AspectJProxyFactory;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

class AspectStateIsolationTest {

    // Target service for testing only: both invocations reach the barrier together.
    static class WorkService {
        private final CyclicBarrier bothInsideTarget = new CyclicBarrier(2);

        public String execute(String requestId) throws Exception {
            bothInsideTarget.await(10, TimeUnit.SECONDS);
            return requestId;
        }
    }

    @Aspect
    static class LeakyAspect {
        // Intentionally wrong: field belongs to a shared aspect instance.
        private volatile String currentRequestId;

        @Around("execution(* *..*.execute(..))")
        public Object around(ProceedingJoinPoint pjp) throws Throwable {
            String requestId = (String) pjp.getArgs()[0];
            currentRequestId = requestId;
            pjp.proceed();
            return currentRequestId;
        }
    }

    @Aspect
    static class IsolatedAspect {
        @Around("execution(* *..*.execute(..))")
        public Object around(ProceedingJoinPoint pjp) throws Throwable {
            String requestId = (String) pjp.getArgs()[0];
            pjp.proceed();
            return requestId; // local value of this exact invocation
        }
    }

    private static WorkService proxyWith(Object aspect) {
        AspectJProxyFactory factory = new AspectJProxyFactory(new WorkService());
        factory.addAspect(aspect);
        return factory.getProxy();
    }

    private static Map<String, String> twoConcurrentCalls(WorkService service)
            throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<String> a = pool.submit(() -> service.execute("A"));
            Future<String> b = pool.submit(() -> service.execute("B"));

            return Map.of(
                    "A", a.get(15, TimeUnit.SECONDS),
                    "B", b.get(15, TimeUnit.SECONDS));
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    void mutableAspectFieldLeaksBetweenConcurrentCalls() throws Exception {
        Map<String, String> actual = twoConcurrentCalls(proxyWith(new LeakyAspect()));

        // After the barrier, both advice invocations read the same field holding the last-written ID.
        // Because A and B differ, at least one result must be wrong.
        assertNotEquals(Map.of("A", "A", "B", "B"), actual);
    }

    @Test
    void methodLocalStateStaysIsolated() throws Exception {
        Map<String, String> actual = twoConcurrentCalls(proxyWith(new IsolatedAspect()));

        assertEquals(Map.of("A", "A", "B", "B"), actual);
    }
}
~~~

Run:

~~~bash
./gradlew test --tests demo.AspectStateIsolationTest
~~~

On Windows you can use `gradlew.bat test --tests demo.AspectStateIsolationTest`.

**Expected verifiable outcome:** both tests **PASS** if Spring AOP advice is applied accurately. The first test **actively expects to catch the bug** using `assertNotEquals`: if B is the last writer, the observed map is `{A=B, B=B}`; if A is the last writer, the map is `{A=A, B=A}`. Neither the last-writing thread nor `Map` iteration order is predicted. The second test asserts the map is always `{A=A, B=B}`. Exact Gradle timings/log paths vary by environment and are not treated as fixed stdout.

Because the test uses `AspectJProxyFactory`, it tests a real AOP proxy without starting a web server. The target class and method are non-`final` so Spring can create a class-based proxy. In real applications, pointcuts should be tightly scoped to service packages/annotations; the broad wildcard here simply keeps the small test independent of module names.

## 5. Testing Through a Spring Application Context and HTTP Requests

The unit test in section 4 cleanly exposes field-sharing bugs. When integrating into an application, also test through real beans to confirm wiring is right:

- Enable Spring AOP with the proper dependency and configuration (such as Spring Boot AOP auto-configuration or `@EnableAspectJAutoProxy` in non-Boot setups).
- Fetch the service from `ApplicationContext`; check `AopUtils.isAopProxy(service)` in test setup and prove the pointcut actually runs, e.g., counting invocations or recording controlled events.
- Call the injected bean from the context; avoid `new Service()` and avoid a bean method calling another method on itself if you expect the Spring proxy to intercept self-invocation.
- Verify both returned data and advice-handled metadata (correlation ID, tenant, audit event, or MDC), not just HTTP 200 status.
- In HTTP tests, send two concurrent requests with distinct headers like `X-Correlation-ID: A` and `X-Correlation-ID: B`; pass the service through a timed barrier to force overlap. Verify both the responses and the audit events tied to each request.
- Use `@SpringBootTest(webEnvironment = RANDOM_PORT)` with an appropriate HTTP client if testing the full filter/controller/service/aspect stack; `MockMvc` can also be invoked concurrently to test multiple servlet calls, though it does not replace testing all components of a real web server.

A good test must confirm **the advice actually ran**. If a pointcut fails to match or a call bypasses the proxy, a test checking only business output can PASS even when the aspect did not execute at all.

With more than two requests, you can run 10–100 tasks through one proxy, assign unique IDs, collect data per ID, and verify a one-to-one mapping. That is a complementary stress test to uncover other paths; it does not replace a controlled barrier test.

## 6. Testing Cleanup on Exceptions and Thread Pool Reuse

Another bug is advice setting `ThreadLocal` or MDC and forgetting to clear it. In synchronous servlet MVC, a pooled thread can serve the next request; stale metadata can appear in the new request's logs. The standard pattern should restore the **previous value**, even when the target throws an exception:

~~~java
@Aspect
@Component
class CorrelationAspect {
    @Around("execution(* com.example.orders.OrderService.*(..))")
    public Object withCorrelation(ProceedingJoinPoint pjp) throws Throwable {
        String previous = org.slf4j.MDC.get("requestId");
        String current = resolveRequestId(); // application integration function
        try {
            org.slf4j.MDC.put("requestId", current);
            return pjp.proceed();
        } finally {
            if (previous == null) {
                org.slf4j.MDC.remove("requestId");
            } else {
                org.slf4j.MDC.put("requestId", previous);
            }
        }
    }

    // resolveRequestId is implemented by the application.
}
~~~

This is **illustrative code**. It demonstrates cleanup scope in `finally`, not an automatic mechanism to propagate MDC to async tasks.

The test suite should include these cases:

| Test case | Setup | What must be verified |
| --- | --- | --- |
| Two concurrent successful calls | A, B, and a barrier in the target | No ID/tenant/audit mix-up between A and B |
| A succeeds, B throws exception | Two interleaved requests, one failure path | Advice preserves exception, failure audit has the right ID |
| Two sequential tasks on **the same worker thread** | Single-thread executor; first request has ID, second does not | No leftover MDC/ThreadLocal after first request |
| Nested advice calls | Outer context value exists; inner advice temporarily changes it | Outer value is restored on exit |
| Target cancelled or timed out | Controlled failure, thread returns to pool | Cleanup in `finally` still runs if control flow actually exits advice |
| Proxy-bypassed call | Self-invocation or direct `new` object | Test detects advice did not run instead of reporting a false isolation pass |

Do not write a test that only reads MDC on the JUnit thread and infers MDC on another worker: MDC is typically thread-bound. Observe on the processing thread itself or capture events with request IDs before the worker finishes. For thread-reuse tests, pick a single-thread executor, capture MDC again in the second callable, and shut down the executor in `finally`.

## 7. ThreadLocal, @Async, and WebFlux: Choosing the Right Test Boundary

**Synchronous Servlet MVC:** one request usually executes on one worker thread through the synchronous pipeline; ThreadLocal/MDC can work for logging, provided scope is clear, async dispatches are handled, and cleanup always runs.

**`@Async`, `CompletableFuture`, executors:** execution can switch to another thread. The calling thread's ThreadLocal/MDC does not automatically propagate to the worker. When propagation is truly needed, use a controlled mechanism like `TaskDecorator`/wrappers that capture and restore context; tests must prove both propagation **and** cleanup on the executing thread. Using virtual threads does not eliminate the need to define context lifetimes.

**Spring WebFlux/Reactor:** a request does not map to a single fixed thread. Do not rely on mutable aspect fields or MDC ThreadLocal as the primary context source for the entire reactive chain. For reactive context, prefer `Reactor Context` and official context propagation mechanisms; test across subscription, scheduler switches, errors, and subscription cancellation when relevant. An `@Around` advice returning `Mono`/`Flux` can finish when **the publisher is created**, before the pipeline runs; to record final outcomes, use appropriate operators on the publisher rather than assuming `pjp.proceed()` is when data was emitted.

**Request scope:** a `@RequestScope` bean creates an object per active web request; if a singleton aspect needs a per-request collaborator, typically inject a scoped proxy/provider instead of copying the request ID into a field. Request-scope tests must run in an environment with a valid request context.

## 8. Common Mistakes When Writing Tests

1. **Calling the target directly** skips advice; if testing Spring AOP, calls must go through the proxy.
2. **Creating a new aspect per task** loses the shared-singleton scenario under test; at least one case must run multiple tasks on the same proxy/aspect instance.
3. **Relying only on sleep or increasing thread counts** without controlled overlap; tests easily pass by luck.
4. **Seeing the bug disappear after adding `volatile` and concluding it is safe**: visibility does not create isolation.
5. **Not checking MDC/ThreadLocal after exceptions**, allowing bugs to appear on the next request in a thread pool.
6. **Asserting only the business response** when the bug sits in logging, audit, tenant routing, or tracing metadata.
7. **Using an untimed barrier**, which can hang CI if one branch fails before reaching the sync point.
8. **Confusing reactive models with servlet models**: thread/scheduler switches invalidate current-thread assumptions.

## 9. Project Application Checklist

- Identify whether any `@Aspect` has mutable fields storing invocation- or request-dependent data; those fields are top-priority candidates to inspect.
- Document the source of request ID/tenant and where advice reads, passes, logs, audits, and cleans it up.
- Write at least one deterministic test with 2 concurrent calls going through the **same Spring AOP proxy**, using a timed barrier or latch.
- Assert results **per request ID**, including audit/logging metadata; verify the advice actually matches the pointcut.
- Add exception, nested-invocation, and worker-thread-reuse cases if the system uses ThreadLocal/MDC.
- If `@Async` or Reactor is present, build context-propagation tests tailored to that execution model.
- Ensure thread pools are shut down and all synchronization primitives have timeouts so tests fail fast on errors.

**Definition of done:** With a correct aspect, two requests carrying contexts A and B produce data belonging to A and B accurately even when interleaved; when errors occur, the advice preserves exceptions and cleans up context; when threads switch, context propagation is tested against the exact mechanism the application actually uses.
