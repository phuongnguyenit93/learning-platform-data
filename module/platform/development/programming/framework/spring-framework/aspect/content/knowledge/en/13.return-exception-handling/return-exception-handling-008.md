# Testing Result Transformation or Exception Mapping with `@Around` in Spring AOP

## 1. The problem and success criteria

In Spring Framework, `@Around` is the advice type with the greatest ability to intervene in a method execution on a **Spring-managed bean**: the advice decides whether to call `ProceedingJoinPoint.proceed()`, which arguments to pass, which result to return to the caller, and how to handle exceptions. Consequently, testing `@Around` cannot stop at "the advice was invoked." You must test **the contract the caller actually observes** and the effects on the target.

This lesson focuses on two **intentional** behaviors:

1. **Result transformation**: the target method produces a value, the advice transforms it, and returns a value of *the same contract type* to the caller. For example, target returns `100`, policy subtracts `10`, caller receives `90`.
2. **Exception mapping**: the target method throws a known infrastructure or low-level error; the advice converts it into an exception belonging to the published service-boundary contract while preserving the **original cause**. For example, `IllegalArgumentException("unknown:missing")` is mapped to `CatalogException("catalog-missing")` with `getCause()` pointing to the original error.

At the same time, you must prove **what must not be altered**:

- Methods returning normally without needing transformation still show the caller that exact result.
- Exceptions outside the mapping rules pass straight through, without being arbitrarily wrapped or replaced by fallbacks.
- Methods not matching the pointcut do not automatically get advised.
- Internal `this.method()` calls and objects instantiated with `new` outside Spring do not automatically go through a Spring proxy.
- The target is called **exactly once** when there is no retry or short-circuit policy.
- No "test passed" solely from printed logs: assertions must verify **values, types, exceptions, causes, and side effects**.

**Scope:** Spring Aspects applied via Spring AOP proxies; `@AspectJ` syntax is supported by Spring, but this lesson does not require AspectJ compile-time or load-time weaving.

## 2. The power of @Around and why you must test at the boundary

When a caller retrieves a service from `ApplicationContext`, Spring can create an AOP proxy if an advisor matches. `@Around` wraps the remainder of the interceptor chain:

~~~text
Caller invokes service.total(100)
       |
       v
Spring AOP proxy
       |
       v
@Around: before
       |
       | pjp.proceed()
       v
Target.total(100) --> 100
       |
       v
@Around: transforms 100 into 90
       |
       | return Integer.valueOf(90)
       v
Caller receives int 90
~~~

Another example with exceptions:

~~~text
Caller invokes service.load("missing")
       |
       v
Spring AOP proxy
       |
       v
@Around: try { pjp.proceed(); }
       |
       v
Target.load(...) throws IllegalArgumentException
       |
       v
@Around: catch (IllegalArgumentException original)
       |
       | throw new CatalogException("catalog-missing", original)
       v
Caller catches CatalogException
       |
       +-- getMessage() = "catalog-missing"
       +-- getCause()   = IllegalArgumentException
       +-- cause message = "unknown:missing"
~~~

In Spring AOP, `pjp.proceed()` proceeds through **inner interceptors/advice** before reaching the target, so an exception caught by `@Around` can originate from an inner interceptor rather than solely from the target body. If an application has multiple advisors, check advisor position and exception-mapping responsibility against the actual chain.

### Rule for choosing advice

`@AfterReturning` is suitable when **only observing** a successful return value; it does not replace the returned reference. `@AfterThrowing` is suitable when **only recording** an exception, without changing it into another error type or a normal return. `@Around` is used here because the requirement is genuinely to **alter the return value and map exceptions**. Do not use `@Around` for every logging task just because it has broad power.

An advice that only needs to observe should be written:

~~~java
@Around("execution(* demo.PricingService.*(..))")
public Object observe(ProceedingJoinPoint pjp) throws Throwable {
    return pjp.proceed();
}
~~~

This is an illustrative snippet inside an `@Aspect` Spring bean, not a standalone runnable class. It preserves the chain's return/exception. If the requirement does not need "before and after" logic across the same invocation, consider a narrower advice type.

## 3. Requirements matrix before writing tests

We have a `PricingService` and two separate pointcuts: one for `total(int)`, one for `load(String)`. The matrix is defined **before running the program**:

| Call | Target behavior | Expected Spring `@Around` behavior | What caller must see |
| --- | --- | --- | --- |
| `service.total(100)` | Returns primitive `100` | `proceed()` once, subtract 10 | `int 90` |
| `service.load("ready")` | Returns `"item:ready"` | Do not transform result | `String "item:ready"` |
| `service.load("missing")` | Throws `IllegalArgumentException("unknown:missing")` | Map exact known error, keep cause | `CatalogException("catalog-missing")` |
| `service.load("down")` | Throws `IllegalStateException("backend-down")` | Does not match catch rule | Remains `IllegalStateException` |
| `service.peek()` | Returns `"peek-ok"` | No pointcut matches | No advice markers |
| `service.loadInside("missing")` | `this.load("missing")` throws original error | Internal call bypasses Spring proxy | Unmapped `IllegalArgumentException` |
| `new PricingService(trace).total(100)` | Returns 100 | No Spring auto-proxy | `int 100` |
| `new PricingService(trace).load("missing")` | Throws original error | No advice | `IllegalArgumentException` |

Positive cases verify proper transformation/mapping, while negative cases verify **the scope of modification does not spill beyond requirements**. If you only check `total(100) == 90`, an exception-swallowing bug might remain; if you only assert `CatalogException`, you might lose the original stack/cause.

## 4. Complete Java 17+ Maven project

Plain Spring Framework project requiring no Spring Boot, server, database, or mocking library.

~~~text
spring-around-contract-test/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── App.java
    │   ├── EventTrace.java
    │   ├── PricingService.java
    │   ├── CatalogException.java
    │   └── ResultMappingAspect.java
    └── test/java/demo/
        └── AroundContractTest.java
~~~

Requirements: Java 17+, Maven 3.9+, and dependency access. Pinned illustrative versions: **Spring Framework 6.2.0**, **AspectJ Weaver 1.9.22**, **JUnit Jupiter 5.11.0**. These are versions for the example, with no claim that they are the latest.

### 4.1. Maven pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-around-contract-test</artifactId>
    <version>1.0-SNAPSHOT</version>
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
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.0</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` provides the bean container/Java config. `spring-aop` provides proxies, advisors, and `AopUtils`. `aspectjweaver` is used by Spring for `@AspectJ` expressions; adding that dependency alone **does not enable AspectJ weaving**. JUnit Jupiter and Surefire allow running automated tests.

### 4.2. EventTrace: observing both advice and target

Create `src/main/java/demo/EventTrace.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.List;

public class EventTrace {
    private final List<String> events = new ArrayList<>();

    public void add(String event) {
        events.add(event);
    }

    public List<String> snapshot() {
        return List.copyOf(events);
    }
}
~~~

In the example, each test creates its own context/trace and runs sequentially, so `ArrayList` is appropriate. If real code records audits concurrently across threads, use a thread-safe collector or logging framework. `snapshot()` lets assertions compare trace contents without mutating the original list.

Traces are recorded **inside both advice and target methods**, allowing you to distinguish "advice ran" from "target ran"; using `AopUtils.isAopProxy` alone does not prove a specific advisor matched.

### 4.3. Contract-level error: CatalogException

Create `src/main/java/demo/CatalogException.java`:

~~~java
package demo;

public class CatalogException extends RuntimeException {
    public CatalogException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

`CatalogException` is the example's runtime exception, **not a built-in Spring exception**. Taking `cause` in the constructor is mandatory under the stated policy: callers and observability can trace back to the original failure. Do not stringify the error into a message and lose the stack/cause.

A good contract should explain why mapping `IllegalArgumentException` to `CatalogException` at the service boundary makes sense. In this learning example, `IllegalArgumentException("unknown:missing")` stands for a "not found" error from an internal layer; production code should not catch **every `IllegalArgumentException`** across every service because it can also signify a **programming bug**. Narrow the pointcut and use a more specific error type if the module has an explicit error-code scheme.

### 4.4. Target PricingService

Create `src/main/java/demo/PricingService.java`:

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

public class PricingService {
    private final EventTrace trace;
    private final AtomicInteger totalCalls = new AtomicInteger();
    private final AtomicInteger loadCalls = new AtomicInteger();

    public PricingService(EventTrace trace) {
        this.trace = trace;
    }

    public int total(int base) {
        totalCalls.incrementAndGet();
        trace.add("TARGET:total:" + base);
        return base;
    }

    public String load(String code) {
        loadCalls.incrementAndGet();
        trace.add("TARGET:load:" + code);

        if ("missing".equals(code)) {
            throw new IllegalArgumentException("unknown:missing");
        }
        if ("down".equals(code)) {
            throw new IllegalStateException("backend-down");
        }
        return "item:" + code;
    }

    public String peek() {
        trace.add("TARGET:peek");
        return "peek-ok";
    }

    public String loadInside(String code) {
        trace.add("TARGET:loadInside");
        return this.load(code);
    }

    public int totalCalls() {
        return totalCalls.get();
    }

    public int loadCalls() {
        return loadCalls.get();
    }
}
~~~

Intentional methods:

- `total(int)` returns the exact `base` argument. If the caller receives 90 when passing 100, that proves **the return transformation came from the advice**, not the target.
- `load("ready")` returns normally; `load("missing")` throws a policy-covered error; `load("down")` throws a different error type to test passthrough.
- `peek()` matches no pointcut in section 4.5.
- `loadInside(String)` calls `this.load(code)` **inside the same target**, demonstrating self-invocation bypassing the Spring proxy.
- `totalCalls()/loadCalls()` count **target method executions**. A test can assert a count of 1 to catch unintended retries or double proceeds.

The code runs on Java 17; the class and methods are non-`final`, so Spring can use a CGLIB class proxy. Avoid thinking `new PricingService(...)` outside the context gets advised; being a Spring-managed bean and calling through the proxy are prerequisites.

### 4.5. Spring @Aspect: transforming values and mapping exceptions

Create `src/main/java/demo/ResultMappingAspect.java`:

~~~java
package demo;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class ResultMappingAspect {
    private final EventTrace trace;
    private final AtomicInteger adviceCalls = new AtomicInteger();

    public ResultMappingAspect(EventTrace trace) {
        this.trace = trace;
    }

    @Around("execution(int demo.PricingService.total(int))")
    public Object discount(ProceedingJoinPoint point) throws Throwable {
        adviceCalls.incrementAndGet();
        trace.add("ADVICE:total:before");

        int original = (Integer) point.proceed();
        int transformed = original - 10;

        trace.add("ADVICE:total:after");
        return transformed;
    }

    @Around("execution(String demo.PricingService.load(String))")
    public Object mapLoadError(ProceedingJoinPoint point) throws Throwable {
        adviceCalls.incrementAndGet();
        trace.add("ADVICE:load:before");

        try {
            Object result = point.proceed();
            trace.add("ADVICE:load:return");
            return result;
        } catch (IllegalArgumentException original) {
            trace.add("ADVICE:load:map");
            throw new CatalogException("catalog-missing", original);
        }
    }

    public int adviceCalls() {
        return adviceCalls.get();
    }
}
~~~

Mechanics and testing significance:

1. `@Around` returns `Object`, takes `ProceedingJoinPoint` as its first parameter, and declares `throws Throwable` so the chain can propagate exceptions.
2. `discount(...)` intercepts specifically `int PricingService.total(int)`. Since the target returns primitive `int`, the result of `proceed()` inside advice is boxed as `Integer`, so the `(Integer)` cast/unbox is valid in **this project**.
3. `return transformed;` is auto-boxed to `Integer` on the AOP interceptor path; callers of `int total(int)` receive `int` after unboxing. Do not return `String "90"` or `null`.
4. `point.proceed()` is called **once**, not twice. If the target writes to a DB or sends notifications, calling proceed twice creates unwanted side effects.
5. `mapLoadError(...)` is scoped **exclusively to `PricingService.load(String)`**, applying neither to `peek` nor to all Spring beans. When no exception occurs, it returns **the exact result** from `proceed()`.
6. Only `IllegalArgumentException` is mapped to `CatalogException`. `IllegalStateException` does not match `catch`, so it **propagates automatically** through the advice to the caller.
7. The constructor `CatalogException("catalog-missing", original)` preserves the original cause; it does not force errors into normal returns or replace them with causeless exceptions.
8. `adviceCalls` counts advice entries, including invocations that throw exceptions. Each test verifies both counters and traces rather than relying solely on logs.
9. Ambiguous multi-advice interactions **do not exist here**: there are only two `@Around` methods on two distinct target methods. Thus there is no ordering ambiguity across multiple advice methods on the same target method.
10. In real applications, subtracting 10 from prices and mapping exceptions require an **explicit business contract**. This example is intentionally simple to verify Spring AOP mechanics, not a complete production pricing or error-mapping solution.

### 4.6. Java configuration and main

Create `src/main/java/demo/App.java`:

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class App {
    @Bean
    public EventTrace eventTrace() {
        return new EventTrace();
    }

    @Bean
    public PricingService pricingService(EventTrace trace) {
        return new PricingService(trace);
    }

    @Bean
    public ResultMappingAspect resultMappingAspect(EventTrace trace) {
        return new ResultMappingAspect(trace);
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            PricingService service = context.getBean(PricingService.class);
            ResultMappingAspect aspect =
                    context.getBean(ResultMappingAspect.class);

            boolean proxy = AopUtils.isAopProxy(service);
            System.out.println("PROXY: " + proxy);

            int total = service.total(100);
            System.out.println("TOTAL: " + total);

            String loaded = service.load("ready");
            System.out.println("LOAD_OK: " + loaded);

            boolean mapped = false;
            try {
                service.load("missing");
            } catch (CatalogException error) {
                Throwable cause = error.getCause();
                mapped = "catalog-missing".equals(error.getMessage())
                        && cause instanceof IllegalArgumentException
                        && "unknown:missing".equals(cause.getMessage());
                System.out.println(
                        "MAPPED: " + error.getClass().getSimpleName()
                        + " <= " + cause.getClass().getSimpleName());
            }

            boolean passedThrough = false;
            try {
                service.load("down");
            } catch (IllegalStateException error) {
                passedThrough = "backend-down".equals(error.getMessage());
                System.out.println(
                        "PASSTHROUGH: " + error.getClass().getSimpleName());
            }

            int calls = aspect.adviceCalls();
            int totalTargets = service.totalCalls();
            int loadTargets = service.loadCalls();

            System.out.println(
                    "COUNTS: advice=" + calls
                    + ",total=" + totalTargets
                    + ",load=" + loadTargets);

            if (!proxy
                    || total != 90
                    || !"item:ready".equals(loaded)
                    || !mapped
                    || !passedThrough
                    || calls != 4
                    || totalTargets != 1
                    || loadTargets != 3) {
                throw new IllegalStateException(
                        "Spring AOP contract verification failed");
            }
            System.out.println("CHECK: PASS");
        }
    }
}
~~~

This runs inside `AnnotationConfigApplicationContext`, requiring neither Spring TestContext nor Spring Boot.

- `@EnableAspectJAutoProxy(proxyTargetClass = true)` enables the Spring AOP proxy infrastructure and requests class-based proxies for matching beans. The target is not `final`.
- `@Bean` factories produce service/aspect/trace as Spring-managed beans; the aspect must also be **registered as a bean**, as `@Aspect` alone is insufficient.
- `context.getBean(PricingService.class)` returns a Spring reference; `AopUtils.isAopProxy` confirms a proxy exists.
- `total(100)` proves the caller receives **90** from the advice rather than **100** from the target.
- `load("ready")` proves normal results are unaltered when the advice only has an exception-mapping policy.
- `load("missing")` proves the **new exception type, message, and original cause**.
- `load("down")` proves **unmapped exception types** still pass straight through.
- `adviceCalls=4` and the target counters show all four advice invocations reached the target exactly once: one `total` and three `load` calls.
- Only when every condition holds does the code print `CHECK: PASS`. A return-type bug, bad mapping, omitted `proceed()`, or duplicate proceed will cause the program to fail.

### 4.7. Running Maven and expected stdout

In the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Lines printed by the code in `App.main`:

~~~text
PROXY: true
TOTAL: 90
LOAD_OK: item:ready
MAPPED: CatalogException <= IllegalArgumentException
PASSTHROUGH: IllegalStateException
COUNTS: advice=4,total=1,load=3
CHECK: PASS
~~~

Maven or logging frameworks may print additional notices. This is the **expected stdout per code**, not a report of Maven having been executed on a real machine. If dependency resolution fails or a condition fails, the program cannot print `CHECK: PASS` via the success path.

## 5. JUnit 5 integration tests: cases that change vs. cases that do not

This is the most important part. The tests actually **invoke the service bean through the Spring proxy** and assert outputs, exceptions, and traces. Each test creates a dedicated context so recorders/counters never leak between tests.

Create `src/test/java/demo/AroundContractTest.java`:

~~~java
package demo;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AroundContractTest {
    @Test
    void transformsReturnValueAndCallsTargetOnce() {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            PricingService service = context.getBean(PricingService.class);
            ResultMappingAspect aspect =
                    context.getBean(ResultMappingAspect.class);
            EventTrace trace = context.getBean(EventTrace.class);

            assertTrue(AopUtils.isAopProxy(service));
            assertEquals(90, service.total(100));
            assertEquals(1, service.totalCalls());
            assertEquals(1, aspect.adviceCalls());
            assertEquals(
                    List.of("ADVICE:total:before",
                            "TARGET:total:100",
                            "ADVICE:total:after"),
                    trace.snapshot());
        }
    }

    @Test
    void successfulReturnPassesThroughUnchanged() {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            PricingService service = context.getBean(PricingService.class);
            ResultMappingAspect aspect =
                    context.getBean(ResultMappingAspect.class);
            EventTrace trace = context.getBean(EventTrace.class);

            assertEquals("item:ready", service.load("ready"));
            assertEquals(1, service.loadCalls());
            assertEquals(1, aspect.adviceCalls());
            assertEquals(
                    List.of("ADVICE:load:before",
                            "TARGET:load:ready",
                            "ADVICE:load:return"),
                    trace.snapshot());
        }
    }

    @Test
    void knownExceptionIsMappedAndCauseIsPreserved() {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            PricingService service = context.getBean(PricingService.class);
            ResultMappingAspect aspect =
                    context.getBean(ResultMappingAspect.class);
            EventTrace trace = context.getBean(EventTrace.class);

            CatalogException mapped = assertThrows(
                    CatalogException.class,
                    () -> service.load("missing"));

            assertEquals("catalog-missing", mapped.getMessage());
            IllegalArgumentException cause =
                    assertInstanceOf(IllegalArgumentException.class,
                            mapped.getCause());
            assertEquals("unknown:missing", cause.getMessage());
            assertEquals(1, service.loadCalls());
            assertEquals(1, aspect.adviceCalls());
            assertEquals(
                    List.of("ADVICE:load:before",
                            "TARGET:load:missing",
                            "ADVICE:load:map"),
                    trace.snapshot());
        }
    }

    @Test
    void unrelatedExceptionIsNotMapped() {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            PricingService service = context.getBean(PricingService.class);
            ResultMappingAspect aspect =
                    context.getBean(ResultMappingAspect.class);
            EventTrace trace = context.getBean(EventTrace.class);

            IllegalStateException original = assertThrows(
                    IllegalStateException.class,
                    () -> service.load("down"));

            assertEquals("backend-down", original.getMessage());
            assertEquals(1, service.loadCalls());
            assertEquals(1, aspect.adviceCalls());
            assertEquals(
                    List.of("ADVICE:load:before",
                            "TARGET:load:down"),
                    trace.snapshot());
        }
    }

    @Test
    void nonMatchingMethodIsNotInterceptedByTheseAdvices() {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            PricingService service = context.getBean(PricingService.class);
            ResultMappingAspect aspect =
                    context.getBean(ResultMappingAspect.class);
            EventTrace trace = context.getBean(EventTrace.class);

            assertEquals("peek-ok", service.peek());
            assertEquals(0, aspect.adviceCalls());
            assertEquals(List.of("TARGET:peek"), trace.snapshot());
        }
    }

    @Test
    void selfInvocationDoesNotApplyTheMappingAdvice() {
        try (var context = new AnnotationConfigApplicationContext(App.class)) {
            PricingService service = context.getBean(PricingService.class);
            ResultMappingAspect aspect =
                    context.getBean(ResultMappingAspect.class);
            EventTrace trace = context.getBean(EventTrace.class);

            IllegalArgumentException raw = assertThrows(
                    IllegalArgumentException.class,
                    () -> service.loadInside("missing"));

            assertEquals("unknown:missing", raw.getMessage());
            assertEquals(1, service.loadCalls());
            assertEquals(0, aspect.adviceCalls());
            assertEquals(
                    List.of("TARGET:loadInside",
                            "TARGET:load:missing"),
                    trace.snapshot());
        }
    }

    @Test
    void manualObjectOutsideSpringDoesNotGetAutoProxy() {
        EventTrace trace = new EventTrace();
        PricingService plain = new PricingService(trace);

        assertFalse(AopUtils.isAopProxy(plain));
        assertEquals(100, plain.total(100));

        IllegalArgumentException raw = assertThrows(
                IllegalArgumentException.class,
                () -> plain.load("missing"));

        assertEquals("unknown:missing", raw.getMessage());
        assertEquals(1, plain.totalCalls());
        assertEquals(1, plain.loadCalls());
        assertEquals(
                List.of("TARGET:total:100",
                        "TARGET:load:missing"),
                trace.snapshot());
    }
}
~~~

We have **seven test methods**. Key point: the tests do not only assert "seemingly right" results, they also assert **target call counts, advice call counts, and event sequences**:

- Test 1 proves transformation succeeds and calls the target once; the transformation was not performed inside the target.
- Test 2 proves `@Around` **does not alter results** when there is no reason to alter them.
- Test 3 proves exception mapping has the right type/message/cause; original error details are not lost.
- Test 4 proves other exceptions pass through; catches bugs where `catch(Throwable)` maps everything.
- Test 5 proves `peek()` is untouched by out-of-scope pointcuts.
- Test 6 proves **self-invocation** is a proxy-based Spring AOP limitation, not a pointcut parser bug.
- Test 7 proves ordinary objects outside Spring are not auto-proxied, even when calling the same Java methods.

Run:

~~~bash
mvn clean test
~~~

When all tests pass, the Maven Surefire report will include a line equivalent to:

~~~text
Tests run: 7, Failures: 0, Errors: 0, Skipped: 0
~~~

The report file is typically located at:

~~~text
target/surefire-reports/demo.AroundContractTest.txt
~~~

If a test fails, read the **assertion failure and root cause**. Never edit expected values to match wrong output; find the bug in pointcuts, bean registration, return contracts, exception mapping, and proceed counts. This is the **expected** result, not confirmation that tests were executed in the current environment.

## 6. Why must you assert the exact return type and cause?

### 6.1. Returning a value that looks right but has the wrong declared type

For the method:

~~~java
public int total(int base) {
    return base;
}
~~~

Spring AOP `@Around` normally returns `Object`, yet callers invoke **a method declared `int`**. `return "90";` from advice is a `String`, incompatible with `int`; `return null;` is also invalid because primitives have no `null`. The framework can raise `AopInvocationException`, an unboxing error, or a type-incompatibility error depending on proxy/chain handling.

Correct example for the illustrative contract:

~~~java
@Around("execution(int demo.PricingService.total(int))")
public Object discount(ProceedingJoinPoint point) throws Throwable {
    int raw = (Integer) point.proceed();
    return raw - 10;  // Auto-boxed to Integer; caller receives int.
}
~~~

This snippet is a **shortened alternative** of the main project's advice; do not add both to the same aspect. If a wildcard `@Around` matches `String`, `boolean`, `Optional`, and `int`, you cannot cast every result to `Integer`. Narrow the pointcut or handle each method's declared return type properly.

### 6.2. Transformed value is right, yet the target never ran

An around advice:

~~~java
@Around("execution(int demo.PricingService.total(int))")
public Object misleading(ProceedingJoinPoint point) {
    return 90;
}
~~~

Can make `assertEquals(90, service.total(100))` pass, yet **never called `proceed()`**. This breaks target side effects if the business method truly needed to run. Our test also checks `service.totalCalls() == 1` and the `TARGET:total:100` event, because the requirement is **transforming the result after the target runs**, not short-circuiting.

Short-circuiting is sometimes a valid design (such as a cache hit), but it must be stated explicitly in the contract and tests. You cannot verify it with a test that only compares values.

### 6.3. New exception has the right type, yet loses the cause

Wrong pattern:

~~~java
catch (IllegalArgumentException original) {
    throw new CatalogException("catalog-missing", null);
}
~~~

The caller sees the right `CatalogException`, yet `getCause() == null`. That makes tracing errors from lower layers difficult. Right pattern:

~~~java
catch (IllegalArgumentException original) {
    throw new CatalogException("catalog-missing", original);
}
~~~

If a module has a more detailed error-code API mapping, include request IDs/status codes per contract (without logging sensitive data). You do not have to copy raw low-level error messages verbatim to end users; preserving `cause` is different from **exposing all internal details**.

### 6.4. Overly broad catch turns unrelated errors into "known" errors

~~~java
try {
    return point.proceed();
} catch (Throwable error) {
    throw new CatalogException("catalog-missing", error);
}
~~~

This pattern is **inappropriate** when policy specifies mapping one error type. It can disguise `IllegalStateException`, programming bugs, and severe `Error`s under a fake category. The `unrelatedExceptionIsNotMapped` test catches that bug.

Sometimes an application needs to map multiple error types to a common API exception; **explicitly specify the permitted error set**, preserve `cause`, and write integration tests verifying each branch. Never put a broad catch on every service merely for convenience.

### 6.5. Turning an error into a normal return outside requirements

~~~java
try {
    return point.proceed();
} catch (IllegalArgumentException error) {
    return "item:unknown";
}
~~~

This snippet does not throw `CatalogException`; it returns a normal `String`. That is a **fallback**, not **exception mapping**. When business policy allows fallback it can make sense, yet it hides the error from the caller and can cause transaction/cache/metrics layers to treat the request as successful. Tests must distinguish **map-to-exception** from **recover-to-value**.

In this lesson, mapping means **throw new CatalogException(...)**, not returning a fallback.

## 7. Test design method for catching regressions

To miss no bugs, build a matrix across **call paths** and **outcomes**:

| Axis | Positive case to prove | Negative case to prove |
| --- | --- | --- |
| Result transform | Target returns 100, caller receives 90 | Target must actually run; other methods must stay unchanged |
| Error map | Known error converts to right API exception | Out-of-policy errors are not mapped |
| Success passthrough | `load("ready")` returns exact value normally | Do not wrap result in wrong container type |
| Cause preservation | `CatalogException.getCause()` is original error | Do not drop `cause` or replace with unrelated error |
| Proxy boundary | Spring bean is proxied; advice runs | Raw `new` object is not auto-proxied |
| Self-invocation | External caller invoking `load` gets mapped | `this.load` inside target bypasses proxy |
| Invocation count | Each call hits target exactly once | Do not omit `proceed()` or retry infinitely |
| Advice scope | `total` and `load` are advised | `peek` is not advised |
| Error semantics | Exception propagates to caller | Do not turn thrown exits into normal returns |

The test suite does not need every combination across the entire application. Yet when a requirement has **two independent conditions** (matching the pointcut and handling the outcome right), include at least one case verifying each condition and a separate negative case guarding against unintended expansion.

When multiple `@Around`/transaction/cache advisors match the same method, watching the **event trace** and target call counts is crucial because `proceed()` delegates through the rest of the advisor chain. For a cached target, a cache hit may skip running the target; in that case **test expected invocation counts must follow the cache contract** rather than assuming one target call for every invocation.

## 8. Manual mutation testing: intentionally breaking code to see tests fail

The following changes are made **one at a time**, for learning only. After each trial, revert `ResultMappingAspect.java` and re-run `mvn clean test`.

### Mutation A: forgetting to call proceed

Replace the transformation block with:

~~~java
trace.add("ADVICE:total:before");
trace.add("ADVICE:total:after");
return 90;
~~~

If you only asserted `service.total(100)==90`, the mutation slips through. In our real test suite, `service.totalCalls()==1` and `TARGET:total:100` vanish, so the positive test fails.

### Mutation B: returning the wrong type

~~~java
return "90";
~~~

For `int total(int)`, this violates the contract. The proxy call can throw an exception instead of returning an integer. Testing the caller-facing result catches it, whereas merely checking whether advice was invoked would not.

### Mutation C: mapping every exception

~~~java
catch (Throwable original) {
    throw new CatalogException("catalog-missing", original);
}
~~~

The `load("down")` case must receive `IllegalStateException`; the mutation turns it into `CatalogException`, so `unrelatedExceptionIsNotMapped` fails.

### Mutation D: losing cause

~~~java
throw new CatalogException("catalog-missing", null);
~~~

The exception-mapping test still catches the right `CatalogException` and message, yet `assertInstanceOf(IllegalArgumentException.class, mapped.getCause())` fails. This is why you should never assert only the exception class.

### Mutation E: widening the pointcut too broadly

Change:

~~~java
@Around("execution(String demo.PricingService.load(String))")
~~~

into an expression matching other `String`-returning methods too, such as:

~~~java
@Around("execution(String demo.PricingService.*(..))")
~~~

`peek()`, which does not belong to the policy, gets `ADVICE:load:before` and increments the advice counter, causing `nonMatchingMethodIsNotInterceptedByTheseAdvices` to fail. If future methods have different String arguments, the pointcut would also intercept them unexpectedly.

### Mutation F: swallowing the exception and returning a fallback

~~~java
catch (IllegalArgumentException original) {
    return "item:unknown";
}
~~~

`knownExceptionIsMappedAndCauseIsPreserved` fails because it never receives `CatalogException`. The contract changed from a thrown exit to a normal return, completely different from the requested mapping.

Common thread: **one positive test is not enough**. Negative tests guard the exact *scope and intervention type*, preventing accidental contract shifts when refactoring pointcuts or advice.

## 9. Distinguishing @AfterThrowing and @Around when mapping exceptions

In Spring AOP:

~~~java
@AfterThrowing(
    pointcut = "execution(String demo.PricingService.load(String))",
    throwing = "error",
    argNames = "error"
)
public void logError(IllegalArgumentException error) {
    System.out.println(error.getMessage());
}
~~~

`@AfterThrowing` is the right choice **if you only want to log** when the target invocation throws. It **has no mechanism to replace the propagating exception with a different exception object** the way the pattern above declares it. To actively catch and throw a new exception, `@Around` is the proper advice type when the real requirement is mapping.

On the other hand, `@Around` can wrap inner advisors; an error caught from `point.proceed()` can come from an **inner interceptor/advice**, not necessarily just the target method. Determine order/precedence whenever error mapping interacts with transactions, security, or caching. Never broadly catch `Throwable` and assume every failure came from the target.

If you need consistent exception mapping at the HTTP API boundary, Spring MVC provides `@ExceptionHandler`/`@ControllerAdvice` for presentation-level exception translation. That is a **different mechanism** from Spring AOP, not something to use merely to prove `@Around` can map errors. This lesson focuses on **Spring bean method boundaries**.

## 10. Constraints regarding checked exceptions and proxy types

The main example maps `IllegalArgumentException` to the **runtime `CatalogException`**. This was an intentional choice to avoid another issue muddying the lesson.

If `@Around` throws a **checked exception** that the method declared through a JDK proxy **forbids in its throws declaration**, callers can encounter a wrapper like `UndeclaredThrowableException` under Java proxy mechanics. With CGLIB and other adapters, symptoms may differ. Therefore:

- If an API needs mapped checked exceptions, check **throws declarations on the interface/implementation** and the proxy strategy;
- Test against the real Spring context (JDK vs. CGLIB), not just by invoking the raw target;
- Do not change exception classes assuming callers always see that exact class when the method signature does not publish it;
- If mapping aims to unify business API errors without checked-exception wrappers, a well-designed runtime exception is usually simpler, though contracts should be consistent application-wide.

`@Around` declares `throws Throwable` because that is the `ProceedingJoinPoint.proceed()` API; this **does not alter the `throws` clause** of the interface method callers invoke. Having `throws Throwable` on an advice signature does not mean the target method can throw arbitrary checked exceptions through a proxy without consequences.

## 11. Advisor ordering and transactions

If a Spring bean also uses transaction, cache, or security advisors, new advice may sit **outside or inside** those advisors. With Spring `@Order`, lower numbers have higher precedence, so outer advice enters earlier and exits later than inner advice in the nesting model.

Example:

~~~text
Caller
  |
  v
ResultMapping @Around (outer)
  | proceed()
  v
Transaction advisor (inner)
  | proceed()
  v
Target throws IllegalArgumentException
  |
  v
Transaction advisor handles error per rollback rules
  |
  v
ResultMapping catches -> throws CatalogException
  |
  v
Caller
~~~

In another case, the transaction advisor may sit **outside** the mapping advice; then transaction logic sees the already-mapped exception. That can affect rollback, metrics, or status policies. Do not assert a fixed order for transaction advisors without verifying configuration.

To test the interaction properly:

1. Build a context containing the application's **actual advisors**.
2. Declare order explicitly if business logic requires it.
3. Call through the Spring proxy, verifying both mapping output and transaction/rollback state with an appropriate integration test.
4. Do not assume "any new exception extending RuntimeException always rolls back every transaction": Spring transactions have their own rollback rules.
5. Avoid calling `method.invoke(target, ...)` inside advice because it can bypass advisors further down the chain; use `point.proceed()`.

## 12. Common testing mistakes

**Mistake 1: Test instantiates `new PricingService` expecting the aspect to run.**  
Manually created objects outside the container are not auto-proxied. `manualObjectOutsideSpringDoesNotGetAutoProxy` is the negative test; main tests must fetch beans from `AnnotationConfigApplicationContext`.

**Mistake 2: Using only `AopUtils.isAopProxy`.**  
A proxy might exist because of another advisor. You must assert **markers inside the advice under test**, caller-facing results, and target invocation counts.

**Mistake 3: Checking only the new exception class.**  
If `cause` is dropped, tests might still pass. Assert **message/error code, cause type, and cause message** per contract.

**Mistake 4: Not testing unmapped exceptions.**  
A broad catch turns every error into a known error. The `IllegalStateException` control case is an essential negative test.

**Mistake 5: Misinterpreting self-invocation as a mapping bug.**  
`this.load("missing")` inside the target bypasses the Spring proxy so mapping does not run; do not switch `@Around` to another advice type trying to fix self-invocation. When policy must apply, move the method to a collaborator bean and invoke via an injected proxy.

**Mistake 6: Forgetting to check proceed count.**  
Advice could call `proceed()` twice and return only the last result, creating duplicate side effects. Assert the target counter to enforce the exactly-once requirement in the example.

**Mistake 7: Sharing test state across cases.**  
Using static counters or reusing contexts without resetting lets tests interfere with one another. The example creates a fresh context and trace instance per test.

**Mistake 8: Logging throwing an exception changes the outcome.**  
If logging inside `catch` fails, callers may receive the logger's exception instead of the designed mapped exception. In production, define an error policy for logging/metrics; test logging failures too if required.

**Mistake 9: Wrong mapping type or return contract.**  
`@Around` returns `Object`, yet an `int` method needs a compatible numeric wrapper and `String` needs a valid String/reference; never return `null` for primitives or return an error string instead of an exception when policy forbids it.

**Mistake 10: Tests relying solely on console output.**  
The console contains Maven/framework stdout and is not a stable interface. Assert results, exceptions, traces, and counters; use the console only for observation while learning.

## 13. Extension exercises

### 13.1. Make the transformation conditional

Change the requirement from "subtract 10 every time" to "discount only if the result is greater than or equal to 10." Then `discount` can inspect the result after `proceed()`, but must define the contract for negative numbers, overflow, and any business-invalid transformations.

Write a positive test for `total(100)` → `90` and a negative test `total(5)` → `5`. Do not alter the target method when what you are testing is **result transformation by the aspect**.

### 13.2. Map a specialized exception type

Instead of using `IllegalArgumentException`, create a dedicated `ItemNotFoundException` in the internal layer and `catch(ItemNotFoundException original)` only. This is a more meaningful production contract because it avoids accidentally mapping `IllegalArgumentException`s caused by programming bugs.

Write a test ensuring an `IllegalArgumentException` unrelated to "item not found" still propagates, while the specialized error is mapped. Keep the cause.

### 13.3. Test returning an intentional fallback

If the requirement changes from **throwing a mapped exception** to **returning fallback `"item:unknown"`**, write a new `@Around` with an explicit contract and tests verifying:
- Whether the target method was called;
- The caller receives the exact fallback String;
- The exception no longer reaches the caller **due to the new policy**, not accidental swallowing;
- Out-of-policy exceptions still propagate.

Do not just edit one line in `catch` and leave the test named `knownExceptionIsMappedAndCauseIsPreserved` misleading.

### 13.4. Add multiple advisors to the same join point

Create a `@Before` audit aspect and an `@Around` mapping aspect both matching `load`, set explicit `@Order`, and record traces in both directions. Try both orderings. Observe which exceptions pass through each advisor and ensure code does not accidentally map errors thrown by the **audit advice** when requirements call for mapping only errors from the business target.

This is a Spring AOP advice-chain exercise, requiring no AspectJ weaving.

## 14. QA checklist before shipping @Around to production

- [ ] Concrete requirement exists for **result transformation** or **exception mapping**; `@Around` is not used for logging alone.
- [ ] Target and aspect are Spring-managed beans; callers use the proxy.
- [ ] Pointcuts are narrow enough per result/exception kind; they do not match unintended methods.
- [ ] `@Around` returns `Object` and declares `throws Throwable` when calling `proceed()`.
- [ ] Normal returns after transformation match declared type, nullability, and primitives/generics.
- [ ] One invocation calls `proceed()` the exact designed number of times; no accidental skipping or retrying.
- [ ] No broad catch converting unrelated errors into known errors.
- [ ] Mapping preserves type/message/error code/cause per contract without leaking unintended internal details.
- [ ] Known exceptions are mapped; unrelated exceptions pass through unchanged; successful results are untouched unless needed.
- [ ] Integration tests assert **caller-facing output**, target counters, advice counters, and traces.
- [ ] Negative tests cover non-matching methods, raw objects, and self-invocation where those are realistic risks.
- [ ] Impacts on transaction/cache/security advisors and chain ordering have been evaluated.
- [ ] Logging/metrics in advice cannot inadvertently throw exceptions that break the contract.
- [ ] If the API uses checked exceptions, interface `throws` declarations and proxy types have been checked.
- [ ] `Method.invoke(target)` is not used in place of `ProceedingJoinPoint.proceed()` when the Spring AOP chain must stay intact.

## 15. Official documentation

- [Spring Framework 6.2 — Declaring Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html): `@Around`, `proceed()`, return/exception handling, and the power to alter return values.
- [Spring Framework 6.2 — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): JDK/CGLIB proxies, self-invocation, and invocation boundaries.
- [Spring Framework 6.2 — Declaring a Pointcut](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/pointcuts.html): scoping method executions and designing pointcut expressions.
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html): registering Spring aspect beans and auto-proxying.
- [Spring Framework 6.2 — Advice Ordering](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html#advice-ordering): precedence when multiple advice methods match.
- [JUnit 5.11.0 — User Guide](https://junit.org/junit5/docs/5.11.0/user-guide/): JUnit Jupiter `@Test`, `assertThrows`, `assertInstanceOf`, and test lifecycle.
